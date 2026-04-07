"""KiCad library indexer.

Discovers and indexes all symbol libraries (.kicad_sym) and footprint
libraries (.pretty/) from the user's KiCad installation, providing fast
lookup by library name, symbol name, footprint name, and pins.
"""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .kicad_parser import (
    FootprintInfo,
    SymbolInfo,
    parse_kicad_mod,
    parse_kicad_sym,
)

log = logging.getLogger(__name__)


@dataclass
class LibraryIndex:
    """In-memory index of all KiCad symbols and footprints."""

    # symbol_lib_name -> { symbol_name -> SymbolInfo }
    symbols: Dict[str, Dict[str, SymbolInfo]] = field(default_factory=dict)

    # footprint_lib_name -> { footprint_name -> FootprintInfo }
    footprints: Dict[str, Dict[str, FootprintInfo]] = field(default_factory=dict)

    # Flat lists for quick prefix search
    all_symbol_lib_names: List[str] = field(default_factory=list)
    all_footprint_lib_names: List[str] = field(default_factory=list)

    def symbol_lib_exists(self, lib: str) -> bool:
        return lib in self.symbols

    def symbol_exists(self, lib: str, name: str) -> bool:
        return name in self.symbols.get(lib, {})

    def get_symbol(self, lib: str, name: str) -> Optional[SymbolInfo]:
        return self.symbols.get(lib, {}).get(name)

    def get_symbols_in_lib(self, lib: str) -> List[str]:
        return list(self.symbols.get(lib, {}).keys())

    def footprint_lib_exists(self, lib: str) -> bool:
        return lib in self.footprints

    def footprint_exists(self, lib: str, name: str) -> bool:
        return name in self.footprints.get(lib, {})

    def get_footprint(self, lib: str, name: str) -> Optional[FootprintInfo]:
        return self.footprints.get(lib, {}).get(name)

    def get_footprints_in_lib(self, lib: str) -> List[str]:
        return list(self.footprints.get(lib, {}).keys())


def _detect_symbol_dir(override: str = "") -> Optional[Path]:
    """Find the KiCad symbol library directory."""
    if override:
        p = Path(override)
        if p.is_dir():
            return p
        # Explicit override that doesn't exist — don't fall through
        return None

    # Try environment variables (KiCad 9, 8, 7, generic)
    for var in ("KICAD9_SYMBOL_DIR", "KICAD8_SYMBOL_DIR", "KICAD7_SYMBOL_DIR", "KICAD_SYMBOL_DIR"):
        val = os.environ.get(var)
        if val:
            p = Path(val)
            if p.is_dir():
                return p

    # Platform-specific defaults
    system = platform.system()
    candidates: list[Path] = []
    if system == "Windows":
        pf = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        for ver in ("10.0", "9.0", "8.0", "7.0"):
            candidates.append(pf / "KiCad" / ver / "share" / "kicad" / "symbols")
    elif system == "Darwin":
        for ver in ("10.0", "9.0", "8.0", "7.0"):
            candidates.append(Path(f"/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"))
    else:  # Linux
        for ver in ("10.0", "9.0", "8.0", "7.0"):
            candidates.append(Path(f"/usr/share/kicad/symbols"))

    for c in candidates:
        if c.is_dir():
            return c
    return None


def _detect_footprint_dir(override: str = "") -> Optional[Path]:
    """Find the KiCad footprint library directory."""
    if override:
        p = Path(override)
        if p.is_dir():
            return p
        # Explicit override that doesn't exist — don't fall through
        return None

    for var in ("KICAD9_FOOTPRINT_DIR", "KICAD8_FOOTPRINT_DIR", "KICAD7_FOOTPRINT_DIR", "KICAD_FOOTPRINT_DIR"):
        val = os.environ.get(var)
        if val:
            p = Path(val)
            if p.is_dir():
                return p

    # Try deriving from symbol dir env var's parent
    for var in ("KICAD9_SYMBOL_DIR", "KICAD8_SYMBOL_DIR", "KICAD7_SYMBOL_DIR", "KICAD_SYMBOL_DIR"):
        val = os.environ.get(var)
        if val:
            fp_dir = Path(val).parent / "footprints"
            if fp_dir.is_dir():
                return fp_dir

    system = platform.system()
    candidates: list[Path] = []
    if system == "Windows":
        pf = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        for ver in ("10.0", "9.0", "8.0", "7.0"):
            candidates.append(pf / "KiCad" / ver / "share" / "kicad" / "footprints")
    elif system == "Darwin":
        candidates.append(Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"))
    else:
        candidates.append(Path("/usr/share/kicad/footprints"))

    for c in candidates:
        if c.is_dir():
            return c
    return None


def build_index(
    symbol_dir_override: str = "",
    footprint_dir_override: str = "",
) -> LibraryIndex:
    """Build or rebuild the full library index."""
    index = LibraryIndex()

    # --- Symbols ---
    sym_dir = _detect_symbol_dir(symbol_dir_override)
    if sym_dir:
        log.info("Indexing symbols from %s", sym_dir)
        for sym_file in sorted(sym_dir.glob("*.kicad_sym")):
            try:
                symbols = parse_kicad_sym(sym_file)
                lib_name = sym_file.stem
                lib_dict: dict[str, SymbolInfo] = {}
                for s in symbols:
                    lib_dict[s.name] = s
                if lib_dict:
                    index.symbols[lib_name] = lib_dict
            except Exception:
                log.exception("Failed to parse %s", sym_file)
        index.all_symbol_lib_names = sorted(index.symbols.keys())
        log.info("Indexed %d symbol libraries", len(index.symbols))
    else:
        log.warning("KiCad symbol directory not found")

    # --- Footprints ---
    fp_dir = _detect_footprint_dir(footprint_dir_override)
    if fp_dir:
        log.info("Indexing footprints from %s", fp_dir)
        for pretty_dir in sorted(fp_dir.glob("*.pretty")):
            lib_name = pretty_dir.stem
            lib_dict_fp: dict[str, FootprintInfo] = {}
            for mod_file in pretty_dir.glob("*.kicad_mod"):
                try:
                    info = parse_kicad_mod(mod_file)
                    if info:
                        lib_dict_fp[info.name] = info
                except Exception:
                    log.exception("Failed to parse %s", mod_file)
            if lib_dict_fp:
                index.footprints[lib_name] = lib_dict_fp
        index.all_footprint_lib_names = sorted(index.footprints.keys())
        log.info("Indexed %d footprint libraries", len(index.footprints))
    else:
        log.warning("KiCad footprint directory not found")

    return index
