"""SKiDL Language Server â€” pygls entry point.

Launch with:  python server/server.py
Communicates over stdio using the LSP protocol.
"""

from __future__ import annotations

import logging
import os
import threading
import sys

# Ensure the extension root is on sys.path so "from server.xxx" imports work
# regardless of the working directory when the server is launched.
_ext_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ext_root not in sys.path:
    sys.path.insert(0, _ext_root)

from lsprotocol.types import (
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_CODE_ACTION,
    CodeAction,
    CodeActionKind,
    CodeActionParams,
    CompletionList,
    CompletionOptions,
    CompletionParams,
    DidChangeTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    Hover,
    HoverParams,
    InitializeParams,
    Position,
    PublishDiagnosticsParams,
    Range,
    TextEdit,
    WorkspaceEdit,
)
from pygls.lsp.server import LanguageServer

from server.analyzer import AnalysisResult, analyze
from server.completions import get_completions
from server.diagnostics import compute_diagnostics
from server.hover import get_hover
from server.indexer import LibraryIndex, build_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("skidl-lsp")


class SkidlLanguageServer(LanguageServer):
    def __init__(self):
        super().__init__("skidl-language-server", "0.1.0")
        self.index = LibraryIndex()
        self._analyses: dict[str, AnalysisResult] = {}
        self._settings: dict = {}
        self._index_ready = False


server = SkidlLanguageServer()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@server.feature("initialize")
def on_initialize(params: InitializeParams):
    log.info("on_initialize called")
    opts = params.initialization_options or {}
    if isinstance(opts, dict):
        server._settings = opts
    log.info("Settings captured: %s", list(server._settings.keys()))


@server.feature("initialized")
def on_initialized(params):
    log.info("on_initialized called, starting index build in background...")
    sym_dir = server._settings.get("kicadSymbolDir", "")
    fp_dir = server._settings.get("kicadFootprintDir", "")

    def _build():
        try:
            server.protocol.notify("skidl/indexStart")
        except Exception:
            log.debug("Failed to send indexStart notification", exc_info=True)

        try:
            idx = build_index(
                symbol_dir_override=sym_dir,
                footprint_dir_override=fp_dir,
            )
            server.index = idx
            server._index_ready = True
            msg = f"{len(idx.symbols)} symbol libs, {len(idx.footprints)} footprint libs"
            log.info("Index ready: %s", msg)

            try:
                server.protocol.notify("skidl/indexEnd", {"message": msg})
            except Exception:
                log.debug("Failed to send indexEnd notification", exc_info=True)

            # Re-validate all open documents now that the index is ready
            for uri, analysis in list(server._analyses.items()):
                doc = server.workspace.get_text_document(uri)
                _validate(doc.uri, doc.source)
        except Exception:
            log.exception("Failed to build index")
            try:
                server.protocol.notify("skidl/indexEnd", {"message": "Failed"})
            except Exception:
                pass

    threading.Thread(target=_build, daemon=True).start()


# ---------------------------------------------------------------------------
# Custom requests
# ---------------------------------------------------------------------------

@server.feature("skidl/refreshIndex")
def on_refresh_index(params=None):
    """Cache-aware refresh: only re-parses if libraries changed on disk."""
    _do_rebuild(force=False)


@server.feature("skidl/rebuildIndex")
def on_rebuild_index(params=None):
    """Force full re-parse, ignoring cache."""
    _do_rebuild(force=True)


def _do_rebuild(force: bool):
    sym_dir = server._settings.get("kicadSymbolDir", "")
    fp_dir = server._settings.get("kicadFootprintDir", "")

    def _rebuild():
        server._index_ready = False
        try:
            server.protocol.notify("skidl/indexStart")
        except Exception:
            pass

        try:
            idx = build_index(
                symbol_dir_override=sym_dir,
                footprint_dir_override=fp_dir,
                force=force,
            )
            server.index = idx
            server._index_ready = True
            msg = f"{len(idx.symbols)} symbol libs, {len(idx.footprints)} footprint libs"
            log.info("Index rebuilt (force=%s): %s", force, msg)
            try:
                server.protocol.notify("skidl/indexEnd", {"message": msg})
            except Exception:
                pass
            # Re-validate all open documents
            for uri, analysis in list(server._analyses.items()):
                doc = server.workspace.get_text_document(uri)
                _validate(doc.uri, doc.source)
        except Exception:
            log.exception("Failed to rebuild index")
            try:
                server.protocol.notify("skidl/indexEnd", {"message": "Failed"})
            except Exception:
                pass

    threading.Thread(target=_rebuild, daemon=True).start()


# ---------------------------------------------------------------------------
# Document sync
# ---------------------------------------------------------------------------

@server.feature(TEXT_DOCUMENT_DID_OPEN)
def on_open(params: DidOpenTextDocumentParams):
    _validate(params.text_document.uri, params.text_document.text)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def on_change(params: DidChangeTextDocumentParams):
    doc = server.workspace.get_text_document(params.text_document.uri)
    _validate(doc.uri, doc.source)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def on_save(params: DidSaveTextDocumentParams):
    doc = server.workspace.get_text_document(params.text_document.uri)
    _validate(doc.uri, doc.source)


def _publish(uri: str, diags: list):
    server.text_document_publish_diagnostics(
        PublishDiagnosticsParams(uri=uri, diagnostics=diags)
    )


def _validate(uri: str, source: str):
    analysis = analyze(source)
    server._analyses[uri] = analysis

    if not analysis.is_skidl_file:
        _publish(uri, [])
        return

    # Don't publish diagnostics until the index is ready
    if not server._index_ready:
        return

    enabled = server._settings.get("enableDiagnostics", True)
    if not enabled:
        _publish(uri, [])
        return

    diags = compute_diagnostics(analysis, server.index)
    _publish(uri, diags)


# ---------------------------------------------------------------------------
# Completions
# ---------------------------------------------------------------------------

@server.feature(
    TEXT_DOCUMENT_COMPLETION,
    CompletionOptions(trigger_characters=['"', "[", ":"]),
)
def on_completion(params: CompletionParams) -> CompletionList | None:
    if not server._settings.get("enableAutocomplete", True):
        return None
    doc = server.workspace.get_text_document(params.text_document.uri)
    analysis = server._analyses.get(doc.uri)
    if not analysis:
        analysis = analyze(doc.source)
        server._analyses[doc.uri] = analysis
    return get_completions(doc.source, params.position, analysis, server.index)


# ---------------------------------------------------------------------------
# Hover
# ---------------------------------------------------------------------------

@server.feature(TEXT_DOCUMENT_HOVER)
def on_hover(params: HoverParams) -> Hover | None:
    if not server._settings.get("enableHover", True):
        return None
    doc = server.workspace.get_text_document(params.text_document.uri)
    analysis = server._analyses.get(doc.uri)
    if not analysis:
        analysis = analyze(doc.source)
        server._analyses[doc.uri] = analysis
    return get_hover(doc.source, params.position, analysis, server.index)


# ---------------------------------------------------------------------------
# Code actions (quick-fix)
# ---------------------------------------------------------------------------

@server.feature(TEXT_DOCUMENT_CODE_ACTION)
def on_code_action(params: CodeActionParams) -> list[CodeAction]:
    actions: list[CodeAction] = []
    for diag in params.context.diagnostics:
        if diag.source != "skidl":
            continue
        data = diag.data
        if not isinstance(data, dict):
            continue
        suggestions = data.get("suggestions", [])
        for suggestion in suggestions:
            # Shrink range by 1 char on each side to preserve surrounding quotes
            r = diag.range
            inner = Range(
                start=Position(line=r.start.line, character=r.start.character + 1),
                end=Position(line=r.end.line, character=r.end.character - 1),
            )
            edit = TextEdit(range=inner, new_text=suggestion)
            actions.append(CodeAction(
                title=f"Replace with '{suggestion}'",
                kind=CodeActionKind.QuickFix,
                diagnostics=[diag],
                edit=WorkspaceEdit(
                    changes={params.text_document.uri: [edit]}
                ),
            ))
    return actions


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    server.start_io()

