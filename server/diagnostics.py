"""Diagnostic provider for SKiDL files.

Validates Part() calls (library, symbol, footprint) and pin accesses
against the KiCad library index, producing LSP Diagnostic objects.
"""

from __future__ import annotations

import difflib
import logging
from typing import List

from lsprotocol.types import (
    Diagnostic,
    DiagnosticSeverity,
    Position,
    Range,
)

from .analyzer import AnalysisResult, PartCall, PinAccess
from .indexer import LibraryIndex
from .models import DiagnosticItem

log = logging.getLogger(__name__)

DIAG_SOURCE = "skidl"


def _range_from_span(span: tuple[int, int, int, int]) -> Range:
    return Range(
        start=Position(line=span[0], character=span[1]),
        end=Position(line=span[2], character=span[3]),
    )


def _close_matches(word: str, candidates: list[str], n: int = 3, cutoff: float = 0.6) -> list[str]:
    return difflib.get_close_matches(word, candidates, n=n, cutoff=cutoff)


# -------------------------------------------------------------------
# Pure-data diagnostic generation (no LSP types)
# -------------------------------------------------------------------

def compute_diagnostics_data(analysis: AnalysisResult, index: LibraryIndex) -> list[DiagnosticItem]:
    """Return diagnostics as plain dataclasses (no LSP dependency)."""
    items: list[DiagnosticItem] = []

    if not analysis.is_skidl_file:
        return items

    for pc in analysis.part_calls:
        items.extend(_validate_part_data(pc, index))

    for pa in analysis.pin_accesses:
        items.extend(_validate_pin_data(pa, analysis, index))

    return items


def _validate_part_data(pc: PartCall, index: LibraryIndex) -> list[DiagnosticItem]:
    items: list[DiagnosticItem] = []

    # --- Library name ---
    if pc.library:
        if not index.symbol_lib_exists(pc.library):
            span = pc.library_span or (pc.line, pc.col, pc.end_line, pc.end_col)
            suggestions = _close_matches(pc.library, index.all_symbol_lib_names)
            msg = f"KiCad symbol library '{pc.library}' not found"
            if suggestions:
                msg += f". Did you mean: {', '.join(suggestions)}?"
            items.append(DiagnosticItem(
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
            items.append(DiagnosticItem(
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
            items.append(DiagnosticItem(
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
            items.append(DiagnosticItem(
                message=msg, severity="error", kind="footprint",
                value=fp_name, suggestions=suggestions,
                library=fp_lib,
                start_line=span[0], start_col=span[1],
                end_line=span[2], end_col=span[3],
            ))

    return items


def _validate_pin_data(pa: PinAccess, analysis: AnalysisResult, index: LibraryIndex) -> list[DiagnosticItem]:
    items: list[DiagnosticItem] = []
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
        items.append(DiagnosticItem(
            message=msg, severity="error", kind="pin",
            value=pa.pin, symbol=pc.symbol,
            start_line=span[0], start_col=span[1],
            end_line=span[2], end_col=span[3],
        ))

    return items


# -------------------------------------------------------------------
# LSP wrapper (converts DiagnosticItem → lsprotocol Diagnostic)
# -------------------------------------------------------------------

_SEVERITY_MAP = {
    "error": DiagnosticSeverity.Error,
    "warning": DiagnosticSeverity.Warning,
    "info": DiagnosticSeverity.Information,
    "hint": DiagnosticSeverity.Hint,
}


def compute_diagnostics(analysis: AnalysisResult, index: LibraryIndex) -> List[Diagnostic]:
    """Return LSP diagnostics for the given analysis result."""
    items = compute_diagnostics_data(analysis, index)
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
            range=_range_from_span((item.start_line, item.start_col, item.end_line, item.end_col)),
            message=item.message,
            severity=_SEVERITY_MAP.get(item.severity, DiagnosticSeverity.Error),
            source=DIAG_SOURCE,
            data=data,
        ))
    return diags
