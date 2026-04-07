"""SKiDL Language Server — pygls entry point.

Launch with:  python server/server.py
Communicates over stdio using the LSP protocol.
"""

from __future__ import annotations

import logging
import os
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


server = SkidlLanguageServer()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@server.feature("initialize")
def on_initialize(params: InitializeParams):
    opts = params.initialization_options or {}
    if isinstance(opts, dict):
        server._settings = opts

    sym_dir = server._settings.get("kicadSymbolDir", "")
    fp_dir = server._settings.get("kicadFootprintDir", "")

    log.info("Building KiCad library index...")
    server.index = build_index(
        symbol_dir_override=sym_dir,
        footprint_dir_override=fp_dir,
    )
    log.info(
        "Index ready: %d symbol libs, %d footprint libs",
        len(server.index.symbols),
        len(server.index.footprints),
    )


# ---------------------------------------------------------------------------
# Custom requests
# ---------------------------------------------------------------------------

@server.feature("skidl/rebuildIndex")
def on_rebuild_index(params=None):
    sym_dir = server._settings.get("kicadSymbolDir", "")
    fp_dir = server._settings.get("kicadFootprintDir", "")
    server.index = build_index(
        symbol_dir_override=sym_dir,
        footprint_dir_override=fp_dir,
    )
    log.info("Index rebuilt")
    # Re-validate all open documents
    for uri, analysis in list(server._analyses.items()):
        doc = server.workspace.get_text_document(uri)
        _validate(doc.uri, doc.source)
    return {"status": "ok"}


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


def _validate(uri: str, source: str):
    analysis = analyze(source)
    server._analyses[uri] = analysis

    if not analysis.is_skidl_file:
        server.publish_diagnostics(uri, [])
        return

    enabled = server._settings.get("enableDiagnostics", True)
    if not enabled:
        server.publish_diagnostics(uri, [])
        return

    diags = compute_diagnostics(analysis, server.index)
    server.publish_diagnostics(uri, diags)


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
            edit = TextEdit(range=diag.range, new_text=suggestion)
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
