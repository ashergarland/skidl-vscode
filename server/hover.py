"""Hover provider for SKiDL files.

Provides hover documentation when the cursor is over:
- A Part() call → symbol description, pin list, default footprint
- A pin reference like led1["A"] → pin name, number, electrical type
- A footprint string → footprint description and pad count
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from lsprotocol.types import (
    Hover,
    MarkupContent,
    MarkupKind,
    Position,
    Range,
)

from .analyzer import AnalysisResult
from .indexer import LibraryIndex
from .models import HoverResult

log = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Pure-data hover generation (no LSP types)
# -------------------------------------------------------------------

def get_hover_data(
    source: str,
    line: int,
    character: int,
    analysis: AnalysisResult,
    index: LibraryIndex,
) -> Optional[HoverResult]:
    """Return hover info as a plain dataclass (no LSP dependency)."""
    if not analysis.is_skidl_file:
        return None

    # --- Hover over Part() call ---
    for pc in analysis.part_calls:
        # Check if cursor is on the symbol span
        if pc.symbol_span:
            sl, sc, el, ec = pc.symbol_span
            if sl <= line <= el and sc <= character <= ec:
                sym = index.get_symbol(pc.library, pc.symbol)
                if sym:
                    return _symbol_hover_data(sym, pc.symbol_span)

        # Check if cursor is on the library span
        if pc.library_span:
            sl, sc, el, ec = pc.library_span
            if sl <= line <= el and sc <= character <= ec:
                if index.symbol_lib_exists(pc.library):
                    symbols = index.get_symbols_in_lib(pc.library)
                    count = len(symbols)
                    preview = ", ".join(symbols[:15])
                    if count > 15:
                        preview += f", ... ({count} total)"
                    md = f"**KiCad Library: {pc.library}**\n\n{count} symbols\n\n`{preview}`"
                    return HoverResult(
                        markdown=md,
                        start_line=pc.library_span[0], start_col=pc.library_span[1],
                        end_line=pc.library_span[2], end_col=pc.library_span[3],
                    )

        # Check if cursor is on the footprint span
        if pc.footprint_span and pc.footprint and ":" in pc.footprint:
            sl, sc, el, ec = pc.footprint_span
            if sl <= line <= el and sc <= character <= ec:
                fp_lib, fp_name = pc.footprint.split(":", 1)
                fp = index.get_footprint(fp_lib, fp_name)
                if fp:
                    return _footprint_hover_data(fp, pc.footprint_span)

    # --- Hover over pin access ---
    for pa in analysis.pin_accesses:
        if pa.pin_span:
            sl, sc, el, ec = pa.pin_span
            if sl <= line <= el and sc <= character <= ec:
                pc = analysis.var_to_part.get(pa.variable)
                if pc:
                    sym = index.get_symbol(pc.library, pc.symbol)
                    if sym:
                        pin_info = None
                        for p in sym.pins:
                            if p.name == pa.pin or p.number == pa.pin:
                                pin_info = p
                                break
                        if pin_info:
                            md = (
                                f"**Pin: {pin_info.name}** (#{pin_info.number})\n\n"
                                f"Symbol: `{pc.library}:{pc.symbol}`\n\n"
                                f"Type: `{pin_info.electrical_type}`"
                            )
                            return HoverResult(
                                markdown=md,
                                start_line=pa.pin_span[0], start_col=pa.pin_span[1],
                                end_line=pa.pin_span[2], end_col=pa.pin_span[3],
                            )

    return None


def _symbol_hover_data(sym, span: tuple[int, int, int, int]) -> HoverResult:
    from .kicad_parser import SymbolInfo
    s: SymbolInfo = sym

    lines = [f"**{s.library}:{s.name}**"]
    if s.description:
        lines.append(f"\n{s.description}")
    if s.default_footprint:
        lines.append(f"\nDefault footprint: `{s.default_footprint}`")
    if s.pins:
        pin_list = ", ".join(
            f"{p.name}(#{p.number})" if p.name else f"#{p.number}"
            for p in s.pins
        )
        lines.append(f"\nPins: {pin_list}")
    if s.keywords:
        lines.append(f"\nKeywords: {s.keywords}")

    return HoverResult(
        markdown="\n".join(lines),
        start_line=span[0], start_col=span[1],
        end_line=span[2], end_col=span[3],
    )


def _footprint_hover_data(fp, span: tuple[int, int, int, int]) -> HoverResult:
    from .kicad_parser import FootprintInfo
    f: FootprintInfo = fp

    lines = [f"**{f.library}:{f.name}**"]
    if f.description:
        lines.append(f"\n{f.description}")
    lines.append(f"\nPads: {f.pad_count}")

    return HoverResult(
        markdown="\n".join(lines),
        start_line=span[0], start_col=span[1],
        end_line=span[2], end_col=span[3],
    )


# -------------------------------------------------------------------
# LSP wrapper (converts HoverResult → lsprotocol Hover)
# -------------------------------------------------------------------

def _make_range(span: tuple[int, int, int, int]) -> Range:
    return Range(
        start=Position(line=span[0], character=span[1]),
        end=Position(line=span[2], character=span[3]),
    )


def get_hover(
    source: str,
    position: Position,
    analysis: AnalysisResult,
    index: LibraryIndex,
) -> Optional[Hover]:
    """Return LSP hover info for the given position, or None."""
    result = get_hover_data(source, position.line, position.character, analysis, index)
    if not result:
        return None

    return Hover(
        contents=MarkupContent(kind=MarkupKind.Markdown, value=result.markdown),
        range=_make_range((result.start_line, result.start_col, result.end_line, result.end_col)),
    )
