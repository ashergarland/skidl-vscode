"""SKiDL Language Server -- pygls entry point.

Launch with:  python -m lsp_server.server
Communicates over stdio using the LSP protocol.
"""

from __future__ import annotations

import logging
import os
import threading
import sys

# Ensure the extension root is on sys.path so "from core.xxx" imports work
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
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    CompletionOptions,
    CompletionParams,
    Diagnostic,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    Hover,
    HoverParams,
    InitializeParams,
    MarkupContent,
    MarkupKind,
    Position,
    PublishDiagnosticsParams,
    Range,
    TextEdit,
    WorkspaceEdit,
)
from pygls.lsp.server import LanguageServer

from core.analyzer import AnalysisResult, analyze
from core.bom import generate_bom
from core.completions import get_suggestions
from core.diagnostics import compute_validation_data
from core.documentation import get_documentation
from core.indexer import LibraryIndex, build_index
from core.models import CompletionSuggestion, SymbolDocumentation, ValidationIssue
from core.search import search_footprints, search_symbols

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("skidl-lsp")

DIAG_SOURCE = "skidl"


# ---------------------------------------------------------------------------
# LSP type conversion helpers
# ---------------------------------------------------------------------------

_COMPLETION_KIND_MAP = {
    "module": CompletionItemKind.Module,
    "class": CompletionItemKind.Class,
    "value": CompletionItemKind.Value,
    "field": CompletionItemKind.Field,
}

_SEVERITY_MAP = {
    "error": DiagnosticSeverity.Error,
    "warning": DiagnosticSeverity.Warning,
    "info": DiagnosticSeverity.Information,
    "hint": DiagnosticSeverity.Hint,
}


def _make_range(span: tuple[int, int, int, int]) -> Range:
    return Range(
        start=Position(line=span[0], character=span[1]),
        end=Position(line=span[2], character=span[3]),
    )


def _to_lsp_completions(items: list[CompletionSuggestion]) -> CompletionList:
    return CompletionList(
        is_incomplete=len(items) > 100,
        items=[
            CompletionItem(
                label=d.label,
                kind=_COMPLETION_KIND_MAP.get(d.kind, CompletionItemKind.Text),
                detail=d.detail,
                insert_text=d.insert_text,
            )
            for d in items
        ],
    )


def _to_lsp_hover(result: SymbolDocumentation) -> Hover:
    return Hover(
        contents=MarkupContent(kind=MarkupKind.Markdown, value=result.markdown),
        range=_make_range((result.start_line, result.start_col, result.end_line, result.end_col)),
    )


def _to_lsp_diagnostics(items: list[ValidationIssue]) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for item in items:
        data: dict = {"kind": item.kind, "value": item.value}
        if item.suggestions:
            data["suggestions"] = item.suggestions
        if item.library:
            data["library"] = item.library
        if item.symbol:
            data["symbol"] = item.symbol
        diags.append(Diagnostic(
            range=_make_range((item.start_line, item.start_col, item.end_line, item.end_col)),
            message=item.message,
            severity=_SEVERITY_MAP.get(item.severity, DiagnosticSeverity.Error),
            source=DIAG_SOURCE,
            data=data,
        ))
    return diags


# ---------------------------------------------------------------------------
# Server class
# ---------------------------------------------------------------------------

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

    issues = compute_validation_data(analysis, server.index)
    diags = _to_lsp_diagnostics(issues)
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
    items = get_suggestions(doc.source, params.position.line, params.position.character, analysis, server.index)
    if items is None:
        return None
    return _to_lsp_completions(items)


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
    result = get_documentation(doc.source, params.position.line, params.position.character, analysis, server.index)
    if not result:
        return None
    return _to_lsp_hover(result)


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
# Custom requests: Browse
# ---------------------------------------------------------------------------

@server.feature("skidl/searchSymbols")
def on_search_symbols(params):
    query = params.get("query", "") if isinstance(params, dict) else ""
    limit = params.get("limit", 50) if isinstance(params, dict) else 50
    results = search_symbols(query, server.index, limit)
    return [
        {"library": r.library, "name": r.name, "description": r.description}
        for r in results
    ]


@server.feature("skidl/searchFootprints")
def on_search_footprints(params):
    query = params.get("query", "") if isinstance(params, dict) else ""
    limit = params.get("limit", 50) if isinstance(params, dict) else 50
    results = search_footprints(query, server.index, limit)
    return [
        {"library": r.library, "name": r.name, "description": r.description, "pad_count": r.pad_count}
        for r in results
    ]


@server.feature("skidl/getSymbolInfo")
def on_get_symbol_info(params):
    library = params.get("library", "") if isinstance(params, dict) else ""
    symbol = params.get("symbol", "") if isinstance(params, dict) else ""
    sym = server.index.get_symbol(library, symbol)
    if not sym:
        return None
    return {
        "name": sym.name,
        "library": sym.library,
        "description": sym.description,
        "default_footprint": sym.default_footprint,
        "keywords": sym.keywords,
        "pins": [
            {"name": p.name, "number": p.number, "electrical_type": p.electrical_type}
            for p in sym.pins
        ],
    }


# ---------------------------------------------------------------------------
# Custom requests: BOM + Validate
# ---------------------------------------------------------------------------

@server.feature("skidl/generateBom")
def on_generate_bom(params):
    uri = params.get("uri", "") if isinstance(params, dict) else ""
    doc = server.workspace.get_text_document(uri)
    entries = generate_bom(doc.source, server.index)
    return [
        {
            "reference": e.reference,
            "library": e.library,
            "symbol": e.symbol,
            "footprint": e.footprint,
            "description": e.description,
            "quantity": e.quantity,
        }
        for e in entries
    ]


@server.feature("skidl/validateDesign")
def on_validate_design(params):
    uri = params.get("uri", "") if isinstance(params, dict) else ""
    doc = server.workspace.get_text_document(uri)
    analysis = analyze(doc.source)
    issues = compute_validation_data(analysis, server.index)
    return [
        {
            "message": d.message,
            "severity": d.severity,
            "kind": d.kind,
            "value": d.value,
            "suggestions": d.suggestions,
            "location": {
                "start_line": d.start_line,
                "start_col": d.start_col,
                "end_line": d.end_line,
                "end_col": d.end_col,
            },
        }
        for d in issues
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    server.start_io()
