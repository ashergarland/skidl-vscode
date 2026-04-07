"""Completion provider for SKiDL files.

Provides autocomplete suggestions for:
- Library names inside Part("...")
- Symbol names inside Part("Lib", "...")
- Footprint strings inside footprint="..."
- Pin names inside part["..."]
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    InsertTextFormat,
    Position,
)

from .analyzer import AnalysisResult
from .indexer import LibraryIndex

log = logging.getLogger(__name__)


def get_completions(
    source: str,
    position: Position,
    analysis: AnalysisResult,
    index: LibraryIndex,
) -> Optional[CompletionList]:
    """Return completion items for the given position, or None."""
    if not analysis.is_skidl_file:
        return None

    line_idx = position.line
    col = position.character
    lines = source.splitlines()
    if line_idx >= len(lines):
        return None
    line = lines[line_idx]
    prefix = line[:col]

    items: list[CompletionItem] = []

    # --- Part("  → library names ---
    m = re.search(r'Part\(\s*"([^"]*?)$', prefix)
    if m:
        typed = m.group(1)
        for lib in index.all_symbol_lib_names:
            if lib.lower().startswith(typed.lower()):
                items.append(CompletionItem(
                    label=lib,
                    kind=CompletionItemKind.Module,
                    detail="KiCad symbol library",
                    insert_text=lib,
                ))
        return CompletionList(is_incomplete=False, items=items)

    # --- Part("Lib", "  → symbol names ---
    m = re.search(r'Part\(\s*"([^"]+)"\s*,\s*"([^"]*?)$', prefix)
    if m:
        lib = m.group(1)
        typed = m.group(2)
        for sym in index.get_symbols_in_lib(lib):
            if sym.lower().startswith(typed.lower()):
                info = index.get_symbol(lib, sym)
                detail = info.description if info else ""
                items.append(CompletionItem(
                    label=sym,
                    kind=CompletionItemKind.Class,
                    detail=detail,
                    insert_text=sym,
                ))
        return CompletionList(is_incomplete=False, items=items)

    # --- footprint="  → footprint lib:name ---
    m = re.search(r'footprint\s*=\s*"([^"]*?)$', prefix)
    if m:
        typed = m.group(1)
        if ":" in typed:
            fp_lib, fp_partial = typed.split(":", 1)
            for fp in index.get_footprints_in_lib(fp_lib):
                if fp.lower().startswith(fp_partial.lower()):
                    full = f"{fp_lib}:{fp}"
                    items.append(CompletionItem(
                        label=full,
                        kind=CompletionItemKind.Value,
                        detail="KiCad footprint",
                        insert_text=fp,  # lib: already typed
                    ))
        else:
            for lib in index.all_footprint_lib_names:
                if lib.lower().startswith(typed.lower()):
                    items.append(CompletionItem(
                        label=lib,
                        kind=CompletionItemKind.Module,
                        detail="Footprint library",
                        insert_text=lib + ":",
                    ))
        return CompletionList(is_incomplete=len(items) > 100, items=items[:100])

    # --- part["  → pin names ---
    m = re.search(r'(\w+)\[\s*"([^"]*?)$', prefix)
    if m:
        var = m.group(1)
        typed = m.group(2)
        pc = analysis.var_to_part.get(var)
        if pc:
            sym = index.get_symbol(pc.library, pc.symbol)
            if sym:
                for pin in sym.pins:
                    label = pin.name or pin.number
                    if label.lower().startswith(typed.lower()):
                        items.append(CompletionItem(
                            label=label,
                            kind=CompletionItemKind.Field,
                            detail=f"Pin {pin.number} ({pin.electrical_type})" if pin.electrical_type else f"Pin {pin.number}",
                            insert_text=label,
                        ))
        return CompletionList(is_incomplete=False, items=items)

    # --- part[  (numeric pin) ---
    m = re.search(r'(\w+)\[\s*(\d*)$', prefix)
    if m:
        var = m.group(1)
        typed = m.group(2)
        pc = analysis.var_to_part.get(var)
        if pc:
            sym = index.get_symbol(pc.library, pc.symbol)
            if sym:
                for pin in sym.pins:
                    num = pin.number
                    if num.isdigit() and num.startswith(typed):
                        items.append(CompletionItem(
                            label=num,
                            kind=CompletionItemKind.Field,
                            detail=f"Pin {pin.name} ({pin.electrical_type})" if pin.name else f"Pin {num}",
                            insert_text=num,
                        ))
        if items:
            return CompletionList(is_incomplete=False, items=items)

    return None
