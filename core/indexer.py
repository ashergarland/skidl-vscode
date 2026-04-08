"""KiCad library indexer.

Discovers and indexes all symbol libraries (.kicad_sym) and footprint
libraries (.pretty/) from the user's KiCad installation, providing fast
lookup by library name, symbol name, footprint name, and pins.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .kicad_parser import (
    FootprintInfo,
    PinInfo,
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

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict for caching."""
        syms = {}
        for lib_name, lib_dict in self.symbols.items():
            syms[lib_name] = {}
            for sym_name, sym in lib_dict.items():
                syms[lib_name][sym_name] = {
                    "d": sym.description,
                    "f": sym.default_footprint,
                    "k": sym.keywords,
                    "p": [[p.name, p.number, p.electrical_type] for p in sym.pins],
                }
        fps = {}
        for lib_name, lib_dict in self.footprints.items():
            fps[lib_name] = {}
            for fp_name, fp in lib_dict.items():
                fps[lib_name][fp_name] = {
                    "d": fp.description,
                    "c": fp.pad_count,
                }
        return {"symbols": syms, "footprints": fps}

    @staticmethod
    def from_dict(data: dict) -> "LibraryIndex":
        """Deserialize from a cached dict."""
        index = LibraryIndex()
        for lib_name, lib_dict in data.get("symbols", {}).items():
            syms: dict[str, SymbolInfo] = {}
            for sym_name, sd in lib_dict.items():
                pins = [PinInfo(name=p[0], number=p[1], electrical_type=p[2])
                        for p in sd.get("p", [])]
                syms[sym_name] = SymbolInfo(
                    name=sym_name, library=lib_name,
                    description=sd.get("d", ""),
                    default_footprint=sd.get("f", ""),
                    keywords=sd.get("k", ""),
                    pins=pins,
                )
            index.symbols[lib_name] = syms
        index.all_symbol_lib_names = sorted(index.symbols.keys())

        for lib_name, lib_dict in data.get("footprints", {}).items():
            fps: dict[str, FootprintInfo] = {}
            for fp_name, fd in lib_dict.items():
                fps[fp_name] = FootprintInfo(
                    name=fp_name, library=lib_name,
                    description=fd.get("d", ""),
                    pad_count=fd.get("c", 0),
                )
            index.footprints[lib_name] = fps
        index.all_footprint_lib_names = sorted(index.footprints.keys())
        return index


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


def _cache_dir() -> Path:
    """Return the cache directory for the index."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    d = base / "skidl-lsp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dir_fingerprint(directory: Path) -> str:
    """Compute a fingerprint for a directory based on file names and sizes.

    This is fast (no file content reads) and changes when libraries are
    added, removed, or updated.
    """
    h = hashlib.sha256()
    h.update(str(directory).encode())
    try:
        for entry in sorted(directory.iterdir()):
            h.update(entry.name.encode())
            try:
                st = entry.stat()
                h.update(str(st.st_size).encode())
                h.update(str(int(st.st_mtime)).encode())
            except OSError:
                pass
    except OSError:
        pass
    return h.hexdigest()[:16]


def _load_cache(sym_dir: Optional[Path], fp_dir: Optional[Path]) -> Optional[LibraryIndex]:
    """Try to load a cached index. Returns None on miss."""
    parts = []
    if sym_dir:
        parts.append(_dir_fingerprint(sym_dir))
    if fp_dir:
        parts.append(_dir_fingerprint(fp_dir))
    if not parts:
        return None

    key = "_".join(parts)
    cache_file = _cache_dir() / f"index_{key}.json"
    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        index = LibraryIndex.from_dict(data)
        log.info("Loaded cached index from %s (%d sym libs, %d fp libs)",
                 cache_file.name, len(index.symbols), len(index.footprints))
        return index
    except Exception:
        log.warning("Failed to load cache, will rebuild", exc_info=True)
        return None


def _save_cache(index: LibraryIndex, sym_dir: Optional[Path], fp_dir: Optional[Path]):
    """Save the index to the cache."""
    parts = []
    if sym_dir:
        parts.append(_dir_fingerprint(sym_dir))
    if fp_dir:
        parts.append(_dir_fingerprint(fp_dir))
    if not parts:
        return

    key = "_".join(parts)
    cache_file = _cache_dir() / f"index_{key}.json"

    try:
        cache_file.write_text(
            json.dumps(index.to_dict(), separators=(",", ":")),
            encoding="utf-8",
        )
        size_mb = cache_file.stat().st_size / 1024 / 1024
        log.info("Saved index cache: %s (%.1fMB)", cache_file.name, size_mb)
    except Exception:
        log.warning("Failed to save cache", exc_info=True)

    # Clean up old cache files (keep only the current one)
    try:
        for old in _cache_dir().glob("index_*.json"):
            if old != cache_file:
                old.unlink()
    except OSError:
        pass


def build_index(
    symbol_dir_override: str = "",
    footprint_dir_override: str = "",
    force: bool = False,
) -> LibraryIndex:
    """Build or rebuild the full library index, using cache when possible."""

    sym_dir = _detect_symbol_dir(symbol_dir_override)
    fp_dir = _detect_footprint_dir(footprint_dir_override)

    # Try cache first (skip when force=True)
    if not force:
        cached = _load_cache(sym_dir, fp_dir)
        if cached is not None:
            return cached

    log.info("Cache miss, building index from scratch...")
    start = _time.time()
    index = LibraryIndex()

    # --- Symbols ---
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

    elapsed = _time.time() - start
    log.info("Index built in %.1fs (%d sym libs, %d fp libs)",
             elapsed, len(index.symbols), len(index.footprints))

    # Save to cache for next time
    _save_cache(index, sym_dir, fp_dir)

    return index
