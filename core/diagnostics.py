"""Validation provider for SKiDL files.

Validates Part() calls (library, symbol, footprint) and pin accesses
against the KiCad library index, producing ValidationIssue dataclasses.
"""

from __future__ import annotations

import difflib
import logging

from .analyzer import AnalysisResult, PartCall, PinAccess
from .indexer import LibraryIndex
from .models import ValidationIssue

log = logging.getLogger(__name__)


def _close_matches(word: str, candidates: list[str], n: int = 3, cutoff: float = 0.6) -> list[str]:
    return difflib.get_close_matches(word, candidates, n=n, cutoff=cutoff)


def compute_validation_data(analysis: AnalysisResult, index: LibraryIndex) -> list[ValidationIssue]:
    """Return validation issues as plain dataclasses (no LSP dependency)."""
    items: list[ValidationIssue] = []

    if not analysis.is_skidl_file:
        return items

    for pc in analysis.part_calls:
        items.extend(_validate_part_data(pc, index))

    for pa in analysis.pin_accesses:
        items.extend(_validate_pin_data(pa, analysis, index))

    return items


def _validate_part_data(pc: PartCall, index: LibraryIndex) -> list[ValidationIssue]:
    items: list[ValidationIssue] = []

    # --- Library name ---
    if pc.library:
        if not index.symbol_lib_exists(pc.library):
            span = pc.library_span or (pc.line, pc.col, pc.end_line, pc.end_col)
            suggestions = _close_matches(pc.library, index.all_symbol_lib_names)
            msg = f"KiCad symbol library '{pc.library}' not found"
            if suggestions:
                msg += f". Did you mean: {', '.join(suggestions)}?"
            items.append(ValidationIssue(
                message=msg, severity="error", kind="library",
                value=pc.library, suggestions=suggestions,
                start_line=span[0], start_col=span[1],
                end_line=span[2], end_col=span[3],
            ))
            return items  # Can't check symbol if library is wrong

    # --- Symbol name ---
    if pc.library and pc.symbol:
        if not index.symbol_exists(pc.library, pc.symbol):
            span = pc.symbol_span or (pc.line, pc.col, pc.end_line, pc.end_col)
            candidates = index.get_symbols_in_lib(pc.library)
            suggestions = _close_matches(pc.symbol, candidates)
            msg = f"Symbol '{pc.symbol}' not found in library '{pc.library}'"
            if suggestions:
                msg += f". Did you mean: {', '.join(suggestions)}?"
            items.append(ValidationIssue(
                message=msg, severity="error", kind="symbol",
                value=pc.symbol, suggestions=suggestions,
                library=pc.library,
                start_line=span[0], start_col=span[1],
                end_line=span[2], end_col=span[3],
            ))

    # --- Footprint ---
    if pc.footprint and ":" in pc.footprint:
        fp_lib, fp_name = pc.footprint.split(":", 1)
        if not index.footprint_lib_exists(fp_lib):
            span = pc.footprint_span or (pc.line, pc.col, pc.end_line, pc.end_col)
            suggestions = _close_matches(fp_lib, index.all_footprint_lib_names)
            msg = f"Footprint library '{fp_lib}' not found"
            if suggestions:
                msg += f". Did you mean: {', '.join(suggestions)}?"
            items.append(ValidationIssue(
                message=msg, severity="error", kind="fp_library",
                value=fp_lib, suggestions=suggestions,
                start_line=span[0], start_col=span[1],
                end_line=span[2], end_col=span[3],
            ))
        elif not index.footprint_exists(fp_lib, fp_name):
            span = pc.footprint_span or (pc.line, pc.col, pc.end_line, pc.end_col)
            candidates = index.get_footprints_in_lib(fp_lib)
            suggestions = _close_matches(fp_name, candidates)
            msg = f"Footprint '{fp_name}' not found in footprint library '{fp_lib}'"
            if suggestions:
                msg += f". Did you mean: {', '.join(suggestions)}?"
            items.append(ValidationIssue(
                message=msg, severity="error", kind="footprint",
                value=fp_name, suggestions=suggestions,
                library=fp_lib,
                start_line=span[0], start_col=span[1],
                end_line=span[2], end_col=span[3],
            ))

    return items


def _validate_pin_data(pa: PinAccess, analysis: AnalysisResult, index: LibraryIndex) -> list[ValidationIssue]:
    items: list[ValidationIssue] = []
    pc = analysis.var_to_part.get(pa.variable)
    if not pc or not pc.library or not pc.symbol:
        return items

    sym = index.get_symbol(pc.library, pc.symbol)
    if not sym:
        return items

    valid_names = {p.name for p in sym.pins}
    valid_numbers = {p.number for p in sym.pins}

    if pa.pin not in valid_names and pa.pin not in valid_numbers:
        span = pa.pin_span or (pa.line, pa.col, pa.end_line, pa.end_col)
        all_pins = sorted(valid_names | valid_numbers)
        available = ", ".join(all_pins[:20])
        if len(all_pins) > 20:
            available += ", ..."
        msg = f"Pin '{pa.pin}' not found on symbol '{pc.symbol}'. Available pins: {available}"
        items.append(ValidationIssue(
            message=msg, severity="error", kind="pin",
            value=pa.pin, symbol=pc.symbol,
            start_line=span[0], start_col=span[1],
            end_line=span[2], end_col=span[3],
        ))

    return items
