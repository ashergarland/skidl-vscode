"""MCP server for SKiDL -- exposes KiCad library validation and browsing as tools.

Run with:
    python server/mcp_server.py

Or configure as an MCP server in Claude Desktop / VS Code:
    { "command": "python", "args": ["server/mcp_server.py"] }
"""

from __future__ import annotations

import difflib
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# Ensure the server package is importable when run as a script
_SERVER_DIR = Path(__file__).resolve().parent
if str(_SERVER_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR.parent))

from server.analyzer import analyze
from server.completions import get_completions_data
from server.diagnostics import compute_diagnostics_data
from server.hover import get_hover_data
from server.indexer import LibraryIndex, build_index

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "skidl",
    instructions=(
        "SKiDL KiCad library validation server. "
        "Validates SKiDL Python code against locally installed KiCad libraries. "
        "Use validate_skidl_code to check source code for errors. "
        "Use list/get/search tools to browse available parts and footprints."
    ),
)

# The index is built once on first tool call (lazy) and cached.
_index: Optional[LibraryIndex] = None


def _get_index() -> LibraryIndex:
    """Return the cached index, building it on first access."""
    global _index
    if _index is None:
        sym_override = os.environ.get("SKIDL_KICAD_SYMBOL_DIR", "")
        fp_override = os.environ.get("SKIDL_KICAD_FOOTPRINT_DIR", "")
        _index = build_index(
            symbol_dir_override=sym_override,
            footprint_dir_override=fp_override,
        )
    return _index


# ---------------------------------------------------------------------------
# Validation tools
# ---------------------------------------------------------------------------

@mcp.tool()
def validate_skidl_code(source: str) -> list[dict]:
    """Validate SKiDL Python source code against installed KiCad libraries.

    Returns a list of diagnostic objects, each containing:
    - message: human-readable error description
    - severity: "error", "warning", "info", or "hint"
    - kind: "library", "symbol", "footprint", "fp_library", or "pin"
    - value: the invalid name that was found
    - suggestions: list of close matches (may be empty)
    - location: {start_line, start_col, end_line, end_col} (0-based)
    """
    index = _get_index()
    analysis = analyze(source)
    items = compute_diagnostics_data(analysis, index)
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
        for d in items
    ]


@mcp.tool()
def rebuild_index() -> str:
    """Force a full rebuild of the KiCad library index (ignores cache)."""
    global _index
    sym_override = os.environ.get("SKIDL_KICAD_SYMBOL_DIR", "")
    fp_override = os.environ.get("SKIDL_KICAD_FOOTPRINT_DIR", "")
    _index = build_index(
        symbol_dir_override=sym_override,
        footprint_dir_override=fp_override,
        force=True,
    )
    sym_count = sum(len(v) for v in _index.symbols.values())
    fp_count = sum(len(v) for v in _index.footprints.values())
    return f"Index rebuilt: {len(_index.all_symbol_lib_names)} symbol libraries ({sym_count} symbols), {len(_index.all_footprint_lib_names)} footprint libraries ({fp_count} footprints)"


# ---------------------------------------------------------------------------
# Library browsing tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_libraries() -> list[str]:
    """List all available KiCad symbol library names."""
    return _get_index().all_symbol_lib_names


@mcp.tool()
def list_symbols(library: str) -> list[dict]:
    """List all symbols in a KiCad symbol library.

    Args:
        library: Library name (e.g. "Device", "Connector")
    """
    index = _get_index()
    if not index.symbol_lib_exists(library):
        suggestions = difflib.get_close_matches(library, index.all_symbol_lib_names, n=3)
        msg = f"Library '{library}' not found"
        if suggestions:
            msg += f". Did you mean: {', '.join(suggestions)}?"
        return [{"error": msg}]

    results = []
    for name in index.get_symbols_in_lib(library):
        sym = index.get_symbol(library, name)
        results.append({
            "name": name,
            "description": sym.description if sym else "",
            "default_footprint": sym.default_footprint if sym else "",
        })
    return results


@mcp.tool()
def get_symbol_info(library: str, symbol: str) -> dict:
    """Get full details for a KiCad symbol including all pins.

    Args:
        library: Library name (e.g. "Device")
        symbol: Symbol name (e.g. "R", "LED")
    """
    index = _get_index()
    sym = index.get_symbol(library, symbol)
    if not sym:
        candidates = index.get_symbols_in_lib(library) if index.symbol_lib_exists(library) else []
        suggestions = difflib.get_close_matches(symbol, candidates, n=3) if candidates else []
        msg = f"Symbol '{symbol}' not found in library '{library}'"
        if suggestions:
            msg += f". Did you mean: {', '.join(suggestions)}?"
        return {"error": msg}

    return {
        "name": sym.name,
        "library": sym.library,
        "description": sym.description,
        "default_footprint": sym.default_footprint,
        "keywords": sym.keywords,
        "pins": [
            {
                "name": p.name,
                "number": p.number,
                "electrical_type": p.electrical_type,
            }
            for p in sym.pins
        ],
    }


@mcp.tool()
def list_footprint_libraries() -> list[str]:
    """List all available KiCad footprint library names."""
    return _get_index().all_footprint_lib_names


@mcp.tool()
def list_footprints(library: str) -> list[dict]:
    """List all footprints in a KiCad footprint library.

    Args:
        library: Footprint library name (e.g. "Resistor_SMD")
    """
    index = _get_index()
    if not index.footprint_lib_exists(library):
        suggestions = difflib.get_close_matches(library, index.all_footprint_lib_names, n=3)
        msg = f"Footprint library '{library}' not found"
        if suggestions:
            msg += f". Did you mean: {', '.join(suggestions)}?"
        return [{"error": msg}]

    results = []
    for name in index.get_footprints_in_lib(library):
        fp = index.get_footprint(library, name)
        results.append({
            "name": name,
            "description": fp.description if fp else "",
            "pad_count": fp.pad_count if fp else 0,
        })
    return results


@mcp.tool()
def get_footprint_info(library: str, footprint: str) -> dict:
    """Get full details for a KiCad footprint.

    Args:
        library: Footprint library name (e.g. "Resistor_SMD")
        footprint: Footprint name (e.g. "R_0805_2012Metric")
    """
    index = _get_index()
    fp = index.get_footprint(library, footprint)
    if not fp:
        candidates = index.get_footprints_in_lib(library) if index.footprint_lib_exists(library) else []
        suggestions = difflib.get_close_matches(footprint, candidates, n=3) if candidates else []
        msg = f"Footprint '{footprint}' not found in library '{library}'"
        if suggestions:
            msg += f". Did you mean: {', '.join(suggestions)}?"
        return {"error": msg}

    return {
        "name": fp.name,
        "library": fp.library,
        "description": fp.description,
        "pad_count": fp.pad_count,
    }


# ---------------------------------------------------------------------------
# Search tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_symbols(query: str, limit: int = 10) -> list[dict]:
    """Fuzzy-search for symbols across all KiCad libraries.

    Args:
        query: Search term (e.g. "resistor", "LED", "ESP32")
        limit: Maximum number of results (default 10)
    """
    index = _get_index()
    # Build flat list of (library, name, description)
    all_syms: list[tuple[str, str, str]] = []
    for lib_name in index.all_symbol_lib_names:
        for sym_name in index.get_symbols_in_lib(lib_name):
            sym = index.get_symbol(lib_name, sym_name)
            desc = sym.description if sym else ""
            all_syms.append((lib_name, sym_name, desc))

    # Score by substring match first, then fuzzy
    query_lower = query.lower()
    scored: list[tuple[float, str, str, str]] = []
    for lib, name, desc in all_syms:
        combined = f"{name} {desc}".lower()
        if query_lower in combined:
            # Exact substring gets high score
            score = 1.0 if query_lower == name.lower() else 0.8
        else:
            ratio = difflib.SequenceMatcher(None, query_lower, name.lower()).ratio()
            if ratio >= 0.5:
                score = ratio * 0.6
            else:
                continue
        scored.append((score, lib, name, desc))

    scored.sort(key=lambda x: -x[0])
    return [
        {"library": lib, "name": name, "description": desc}
        for _, lib, name, desc in scored[:limit]
    ]


@mcp.tool()
def search_footprints(query: str, limit: int = 10) -> list[dict]:
    """Fuzzy-search for footprints across all KiCad libraries.

    Args:
        query: Search term (e.g. "0805", "QFP", "SOT-23")
        limit: Maximum number of results (default 10)
    """
    index = _get_index()
    all_fps: list[tuple[str, str, str, int]] = []
    for lib_name in index.all_footprint_lib_names:
        for fp_name in index.get_footprints_in_lib(lib_name):
            fp = index.get_footprint(lib_name, fp_name)
            desc = fp.description if fp else ""
            pads = fp.pad_count if fp else 0
            all_fps.append((lib_name, fp_name, desc, pads))

    query_lower = query.lower()
    scored: list[tuple[float, str, str, str, int]] = []
    for lib, name, desc, pads in all_fps:
        combined = f"{lib}:{name} {desc}".lower()
        if query_lower in combined:
            score = 1.0 if query_lower == name.lower() else 0.8
        else:
            ratio = difflib.SequenceMatcher(None, query_lower, name.lower()).ratio()
            if ratio >= 0.4:
                score = ratio * 0.6
            else:
                continue
        scored.append((score, lib, name, desc, pads))

    scored.sort(key=lambda x: -x[0])
    return [
        {"library": lib, "name": name, "description": desc, "pad_count": pads}
        for _, lib, name, desc, pads in scored[:limit]
    ]


# ---------------------------------------------------------------------------
# Completion / hover tools (full LSP-equivalent for AI agents)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_completions(source: str, line: int, character: int) -> list[dict]:
    """Get autocomplete suggestions for a position in SKiDL source code.

    Args:
        source: Full Python source code
        line: 0-based line number
        character: 0-based column number
    """
    index = _get_index()
    analysis = analyze(source)
    items = get_completions_data(source, line, character, analysis, index)
    if items is None:
        return []
    return [
        {"label": c.label, "kind": c.kind, "detail": c.detail, "insert_text": c.insert_text}
        for c in items
    ]


@mcp.tool()
def get_hover(source: str, line: int, character: int) -> Optional[dict]:
    """Get hover documentation for a position in SKiDL source code.

    Args:
        source: Full Python source code
        line: 0-based line number
        character: 0-based column number
    """
    index = _get_index()
    analysis = analyze(source)
    result = get_hover_data(source, line, character, analysis, index)
    if not result:
        return None
    return {
        "markdown": result.markdown,
        "location": {
            "start_line": result.start_line,
            "start_col": result.start_col,
            "end_line": result.end_line,
            "end_col": result.end_col,
        },
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
