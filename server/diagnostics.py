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

log = logging.getLogger(__name__)

DIAG_SOURCE = "skidl"


def _range_from_span(span: tuple[int, int, int, int]) -> Range:
    return Range(
        start=Position(line=span[0], character=span[1]),
        end=Position(line=span[2], character=span[3]),
    )


def _close_matches(word: str, candidates: list[str], n: int = 3, cutoff: float = 0.6) -> list[str]:
    return difflib.get_close_matches(word, candidates, n=n, cutoff=cutoff)


def compute_diagnostics(analysis: AnalysisResult, index: LibraryIndex) -> List[Diagnostic]:
    """Return diagnostics for the given analysis result."""
    diags: list[Diagnostic] = []

    if not analysis.is_skidl_file:
        return diags

    for pc in analysis.part_calls:
        diags.extend(_validate_part(pc, index))

    for pa in analysis.pin_accesses:
        diags.extend(_validate_pin(pa, analysis, index))

    return diags


def _validate_part(pc: PartCall, index: LibraryIndex) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    # --- Library name ---
    if pc.library:
        if not index.symbol_lib_exists(pc.library):
            span = pc.library_span or (pc.line, pc.col, pc.end_line, pc.end_col)
            suggestions = _close_matches(pc.library, index.all_symbol_lib_names)
            msg = f"KiCad symbol library '{pc.library}' not found"
            if suggestions:
                msg += f". Did you mean: {', '.join(suggestions)}?"
            diags.append(Diagnostic(
                range=_range_from_span(span),
                message=msg,
                severity=DiagnosticSeverity.Error,
                source=DIAG_SOURCE,
                data={"kind": "library", "value": pc.library, "suggestions": suggestions},
            ))
            return diags  # Can't check symbol if library is wrong

    # --- Symbol name ---
    if pc.library and pc.symbol:
        if not index.symbol_exists(pc.library, pc.symbol):
            span = pc.symbol_span or (pc.line, pc.col, pc.end_line, pc.end_col)
            candidates = index.get_symbols_in_lib(pc.library)
            suggestions = _close_matches(pc.symbol, candidates)
            msg = f"Symbol '{pc.symbol}' not found in library '{pc.library}'"
            if suggestions:
                msg += f". Did you mean: {', '.join(suggestions)}?"
            diags.append(Diagnostic(
                range=_range_from_span(span),
                message=msg,
                severity=DiagnosticSeverity.Error,
                source=DIAG_SOURCE,
                data={"kind": "symbol", "library": pc.library, "value": pc.symbol, "suggestions": suggestions},
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
            diags.append(Diagnostic(
                range=_range_from_span(span),
                message=msg,
                severity=DiagnosticSeverity.Error,
                source=DIAG_SOURCE,
                data={"kind": "fp_library", "value": fp_lib, "suggestions": suggestions},
            ))
        elif not index.footprint_exists(fp_lib, fp_name):
            span = pc.footprint_span or (pc.line, pc.col, pc.end_line, pc.end_col)
            candidates = index.get_footprints_in_lib(fp_lib)
            suggestions = _close_matches(fp_name, candidates)
            msg = f"Footprint '{fp_name}' not found in footprint library '{fp_lib}'"
            if suggestions:
                msg += f". Did you mean: {', '.join(suggestions)}?"
            diags.append(Diagnostic(
                range=_range_from_span(span),
                message=msg,
                severity=DiagnosticSeverity.Error,
                source=DIAG_SOURCE,
                data={"kind": "footprint", "library": fp_lib, "value": fp_name, "suggestions": suggestions},
            ))

    return diags


def _validate_pin(pa: PinAccess, analysis: AnalysisResult, index: LibraryIndex) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    pc = analysis.var_to_part.get(pa.variable)
    if not pc or not pc.library or not pc.symbol:
        return diags

    sym = index.get_symbol(pc.library, pc.symbol)
    if not sym:
        return diags

    # Check pin by name or number
    valid_names = {p.name for p in sym.pins}
    valid_numbers = {p.number for p in sym.pins}

    if pa.pin not in valid_names and pa.pin not in valid_numbers:
        span = pa.pin_span or (pa.line, pa.col, pa.end_line, pa.end_col)
        all_pins = sorted(valid_names | valid_numbers)
        available = ", ".join(all_pins[:20])
        if len(all_pins) > 20:
            available += ", ..."
        msg = f"Pin '{pa.pin}' not found on symbol '{pc.symbol}'. Available pins: {available}"
        diags.append(Diagnostic(
            range=_range_from_span(span),
            message=msg,
            severity=DiagnosticSeverity.Error,
            source=DIAG_SOURCE,
            data={"kind": "pin", "symbol": pc.symbol, "value": pa.pin},
        ))

    return diags
