"""Bill of Materials (BOM) generation from SKiDL source code."""

from __future__ import annotations

from dataclasses import dataclass

from .analyzer import analyze
from .indexer import LibraryIndex


@dataclass
class BomEntry:
    reference: str
    library: str
    symbol: str
    footprint: str
    description: str
    quantity: int = 1


def generate_bom(source: str, index: LibraryIndex) -> list[BomEntry]:
    """Generate a BOM from SKiDL source code.

    Parses Part() calls, resolves descriptions from the index,
    and groups identical parts.
    """
    analysis = analyze(source)

    # Group by (library, symbol, footprint) -> list of references
    groups: dict[tuple[str, str, str], list[str]] = {}
    for part in analysis.part_calls:
        footprint = part.footprint
        # Resolve default footprint from index if not specified
        if not footprint and part.library:
            sym_info = index.get_symbol(part.library, part.symbol)
            if sym_info and sym_info.default_footprint:
                footprint = sym_info.default_footprint

        key = (part.library, part.symbol, footprint)
        ref = part.variable or f"U{part.line + 1}"
        groups.setdefault(key, []).append(ref)

    entries: list[BomEntry] = []
    for (library, symbol, footprint), refs in groups.items():
        desc = ""
        sym_info = index.get_symbol(library, symbol) if library else None
        if sym_info:
            desc = sym_info.description

        entries.append(BomEntry(
            reference=", ".join(sorted(refs)),
            library=library,
            symbol=symbol,
            footprint=footprint,
            description=desc,
            quantity=len(refs),
        ))

    entries.sort(key=lambda e: (e.library, e.symbol, e.reference))
    return entries
