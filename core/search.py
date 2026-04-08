"""Search functions for KiCad symbols and footprints."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from .indexer import LibraryIndex


@dataclass
class SymbolSearchResult:
    library: str
    name: str
    description: str


@dataclass
class FootprintSearchResult:
    library: str
    name: str
    description: str
    pad_count: int


def search_symbols(
    query: str, index: LibraryIndex, limit: int = 10
) -> list[SymbolSearchResult]:
    """Fuzzy-search for symbols across all KiCad libraries."""
    all_syms: list[tuple[str, str, str]] = []
    for lib_name in index.all_symbol_lib_names:
        for sym_name in index.get_symbols_in_lib(lib_name):
            sym = index.get_symbol(lib_name, sym_name)
            desc = sym.description if sym else ""
            all_syms.append((lib_name, sym_name, desc))

    query_lower = query.lower()
    scored: list[tuple[float, str, str, str]] = []
    for lib, name, desc in all_syms:
        combined = f"{name} {desc}".lower()
        if query_lower in combined:
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
        SymbolSearchResult(library=lib, name=name, description=desc)
        for _, lib, name, desc in scored[:limit]
    ]


def search_footprints(
    query: str, index: LibraryIndex, limit: int = 10
) -> list[FootprintSearchResult]:
    """Fuzzy-search for footprints across all KiCad libraries."""
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
        FootprintSearchResult(library=lib, name=name, description=desc, pad_count=pads)
        for _, lib, name, desc, pads in scored[:limit]
    ]
