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
from typing import Optional

from .analyzer import AnalysisResult
from .indexer import LibraryIndex
from .models import CompletionSuggestion

log = logging.getLogger(__name__)


_SKIDL_IMPORT_RE = re.compile(r'(?:from\s+skidl\s+import|import\s+skidl)')


def get_suggestions(
    source: str,
    line: int,
    character: int,
    analysis: AnalysisResult,
    index: LibraryIndex,
) -> Optional[list[CompletionSuggestion]]:
    """Return completion items as plain dataclasses, or None if no pattern matched."""
    if not analysis.is_skidl_file and not _SKIDL_IMPORT_RE.search(source):
        return None

    lines = source.splitlines()
    if line >= len(lines):
        return []
    line_text = lines[line]
    prefix = line_text[:character]

    items: list[CompletionSuggestion] = []

    # --- Part("  -> library names ---
    m = re.search(r'Part\(\s*"([^"]*?)$', prefix)
    if m:
        typed = m.group(1)
        for lib in index.all_symbol_lib_names:
            if lib.lower().startswith(typed.lower()):
                items.append(CompletionSuggestion(
                    label=lib, kind="module",
                    detail="KiCad symbol library", insert_text=lib,
                ))
        return items

    # --- Part("Lib", "  -> symbol names ---
    m = re.search(r'Part\(\s*"([^"]+)"\s*,\s*"([^"]*?)$', prefix)
    if m:
        lib = m.group(1)
        typed = m.group(2)
        for sym in index.get_symbols_in_lib(lib):
            if sym.lower().startswith(typed.lower()):
                info = index.get_symbol(lib, sym)
                detail = info.description if info else ""
                items.append(CompletionSuggestion(
                    label=sym, kind="class",
                    detail=detail, insert_text=sym,
                ))
        return items

    # --- footprint="  -> footprint lib:name ---
    m = re.search(r'footprint\s*=\s*"([^"]*?)$', prefix)
    if m:
        typed = m.group(1)
        if ":" in typed:
            fp_lib, fp_partial = typed.split(":", 1)
            for fp in index.get_footprints_in_lib(fp_lib):
                if fp.lower().startswith(fp_partial.lower()):
                    full = f"{fp_lib}:{fp}"
                    items.append(CompletionSuggestion(
                        label=full, kind="value",
                        detail="KiCad footprint", insert_text=fp,
                    ))
        else:
            for lib in index.all_footprint_lib_names:
                if lib.lower().startswith(typed.lower()):
                    items.append(CompletionSuggestion(
                        label=lib, kind="module",
                        detail="Footprint library", insert_text=lib + ":",
                    ))
        return items[:100]

    # --- part["  -> pin names ---
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
                        items.append(CompletionSuggestion(
                            label=label, kind="field",
                            detail=f"Pin {pin.number} ({pin.electrical_type})" if pin.electrical_type else f"Pin {pin.number}",
                            insert_text=label,
                        ))
        return items

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
                        items.append(CompletionSuggestion(
                            label=num, kind="field",
                            detail=f"Pin {pin.name} ({pin.electrical_type})" if pin.name else f"Pin {num}",
                            insert_text=num,
                        ))
        if items:
            return items

    return None
