"""KiCad .kicad_sym and .kicad_mod S-expression parser.

Parses KiCad symbol and footprint library files to extract metadata
used for validation, autocomplete, and hover documentation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Generic S-expression tokeniser / parser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"""
    (?P<OPEN>\()           |
    (?P<CLOSE>\))          |
    (?P<STRING>"[^"]*")    |
    (?P<ATOM>[^\s()]+)     |
    (?P<WS>\s+)
""", re.VERBOSE)


def _tokenize(text: str):
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        if kind == "WS":
            continue
        value = m.group()
        if kind == "STRING":
            value = value[1:-1]  # strip quotes
        yield kind, value


def parse_sexpr(text: str):
    """Parse S-expression text into nested Python lists / strings."""
    tokens = list(_tokenize(text))
    pos = 0

    def _parse():
        nonlocal pos
        if pos >= len(tokens):
            return None
        kind, value = tokens[pos]
        if kind == "OPEN":
            pos += 1
            items: list = []
            while pos < len(tokens) and tokens[pos][0] != "CLOSE":
                item = _parse()
                if item is not None:
                    items.append(item)
            pos += 1  # skip CLOSE
            return items
        elif kind == "CLOSE":
            pos += 1
            return None
        else:
            pos += 1
            return value

    results: list = []
    while pos < len(tokens):
        node = _parse()
        if node is not None:
            results.append(node)
    return results[0] if len(results) == 1 else results


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PinInfo:
    name: str
    number: str
    electrical_type: str = ""  # input, output, passive, power_in, …
    description: str = ""


@dataclass
class SymbolInfo:
    name: str
    library: str
    description: str = ""
    default_footprint: str = ""
    pins: List[PinInfo] = field(default_factory=list)
    keywords: str = ""


@dataclass
class FootprintInfo:
    name: str
    library: str
    description: str = ""
    pad_count: int = 0


# ---------------------------------------------------------------------------
# .kicad_sym parser
# ---------------------------------------------------------------------------

def _find_nodes(tree, tag: str):
    """Yield sub-lists whose first element equals *tag*."""
    if isinstance(tree, list):
        if tree and tree[0] == tag:
            yield tree
        for child in tree:
            yield from _find_nodes(child, tag)


def _prop_value(tree, key: str) -> str:
    """Return the value of a (property "key" "value" ...) node."""
    for node in _find_nodes(tree, "property"):
        if len(node) >= 3 and node[1] == key:
            return node[2]
    return ""


def parse_kicad_sym(path: Path) -> List[SymbolInfo]:
    """Parse a .kicad_sym file and return all symbols with their pins.

    Uses a streaming approach: reads the file line-by-line and tracks
    bracket depth to find symbol boundaries, avoiding building a full
    parse tree in memory.
    """
    lib_name = path.stem
    symbols: list[SymbolInfo] = []
    sym_by_name: dict[str, SymbolInfo] = {}

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if "(kicad_symbol_lib" not in text[:200]:
        return []

    # Strategy: find top-level (symbol "NAME" ...) blocks using bracket depth.
    # The kicad_symbol_lib root is depth 1, top-level symbols are depth 2.
    depth = 0
    i = 0
    text_len = len(text)
    in_string = False

    # Track symbol blocks at depth 2
    sym_start = -1
    sym_depth = 0

    while i < text_len:
        ch = text[i]
        if in_string:
            if ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue

        if ch == '(':
            depth += 1
            # Check if this opens a top-level symbol (depth 2 inside kicad_symbol_lib)
            if depth == 2:
                # Peek ahead to check if it's (symbol "NAME"
                rest = text[i:i+200]
                m = _SYM_OPEN_RE.match(rest)
                if m:
                    sym_start = i
                    sym_depth = depth
        elif ch == ')':
            if depth == 2 and sym_start >= 0:
                # End of a top-level symbol block
                block = text[sym_start:i + 1]
                _process_symbol_block(block, lib_name, symbols, sym_by_name)
                sym_start = -1
            depth -= 1

        i += 1

    return symbols


_SYM_OPEN_RE = re.compile(r'\(symbol\s+"([^"]+)"')
_PROP_RE = re.compile(r'\(property\s+"([^"]+)"\s+"([^"]*)"')


def _process_symbol_block(block: str, lib_name: str,
                          symbols: list, sym_by_name: dict):
    """Process a single top-level symbol block."""
    m = _SYM_OPEN_RE.match(block)
    if not m:
        return
    raw_name = m.group(1)

    # Extract properties via regex (fast, no tree building)
    desc = ""
    fp = ""
    kw = ""
    for pm in _PROP_RE.finditer(block):
        key, val = pm.group(1), pm.group(2)
        if not desc and key in ("Description", "ki_description"):
            desc = val
        elif not fp and key in ("Footprint", "ki_fp_filters"):
            fp = val
        elif not kw and key == "ki_keywords":
            kw = val

    info = SymbolInfo(
        name=raw_name,
        library=lib_name,
        description=desc,
        default_footprint=fp,
        keywords=kw,
    )

    # Extract pins via regex
    _fast_collect_pins(block, info)

    # Merge pins into parent for sub-unit symbols
    # (Sub-units are nested inside the parent at depth 2, so they appear
    #  in the same block. Handle named sub-symbols just in case.)
    symbols.append(info)
    sym_by_name[raw_name] = info


def _fast_collect_pins(block: str, symbol: SymbolInfo):
    """Extract pins from a symbol block text using regex."""
    existing = {p.number for p in symbol.pins}
    # Match (pin <type> <style> with pin-level opening paren
    for pm in re.finditer(r'\(pin\s+(\w+)\s+\w+', block):
        etype = pm.group(1)
        # Find the extent of this (pin ...) via bracket counting
        pin_start = pm.start()
        depth = 0
        i = pin_start
        blen = len(block)
        while i < blen:
            ch = block[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        pin_text = block[pin_start:i + 1]

        nm = re.search(r'\(name\s+"([^"]*)"', pin_text)
        nn = re.search(r'\(number\s+"([^"]*)"', pin_text)
        pname = nm.group(1) if nm else ""
        pnumber = nn.group(1) if nn else ""

        if pnumber and pnumber not in existing:
            symbol.pins.append(PinInfo(name=pname, number=pnumber, electrical_type=etype))
            existing.add(pnumber)


# ---------------------------------------------------------------------------
# .kicad_mod parser  (lightweight — just existence + pad count)
# ---------------------------------------------------------------------------

_FP_NAME_RE = re.compile(r'^\s*\((?:footprint|module)\s+"([^"]+)"', re.MULTILINE)
_FP_DESCR_RE = re.compile(r'\(descr\s+"([^"]*)"')
_FP_PAD_RE = re.compile(r'\(pad\s+')


def parse_kicad_mod(path: Path) -> Optional[FootprintInfo]:
    """Parse a .kicad_mod file, returning footprint metadata.

    Uses regex for speed -- avoids building a full S-expression tree.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    m = _FP_NAME_RE.search(text[:500])
    if not m:
        return None

    fp_name = m.group(1)
    lib_name = path.parent.stem.replace(".pretty", "")

    dm = _FP_DESCR_RE.search(text[:2000])
    desc = dm.group(1) if dm else ""

    pad_count = len(_FP_PAD_RE.findall(text))

    return FootprintInfo(
        name=fp_name,
        library=lib_name,
        description=desc,
        pad_count=pad_count,
    )
