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
    """Parse a .kicad_sym file and return all symbols with their pins."""
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = parse_sexpr(text)
    if not isinstance(tree, list) or not tree or tree[0] != "kicad_symbol_lib":
        return []

    lib_name = path.stem
    symbols: list[SymbolInfo] = []

    for sym_node in _find_nodes(tree, "symbol"):
        if len(sym_node) < 2:
            continue
        raw_name: str = sym_node[1]

        # Skip sub-units like "R_0_1" — they contain the actual pin geometry
        # but the top-level "R" is the symbol entry we care about for the name.
        # We collect pins from sub-symbols into the parent.
        if "_" in raw_name and raw_name.rsplit("_", 2)[-1].isdigit():
            # Looks like a sub-unit; attach pins to parent
            parent_name = raw_name.split("_")[0]
            parent = next((s for s in symbols if s.name == parent_name), None)
            if parent is not None:
                _collect_pins(sym_node, parent)
            continue

        desc = _prop_value(sym_node, "Description") or _prop_value(sym_node, "ki_description")
        fp = _prop_value(sym_node, "Footprint") or _prop_value(sym_node, "ki_fp_filters")
        kw = _prop_value(sym_node, "ki_keywords")

        info = SymbolInfo(
            name=raw_name,
            library=lib_name,
            description=desc,
            default_footprint=fp,
            keywords=kw,
        )
        _collect_pins(sym_node, info)
        symbols.append(info)

    return symbols


def _collect_pins(tree, symbol: SymbolInfo):
    """Walk *tree* and add any pin nodes to *symbol*.pins (dedup by number)."""
    existing_numbers = {p.number for p in symbol.pins}
    for pin_node in _find_nodes(tree, "pin"):
        # (pin <electrical_type> <graphic_style> (at ...) (length ...) (name "X" ...) (number "1" ...))
        if len(pin_node) < 3:
            continue
        etype = pin_node[1] if len(pin_node) > 1 else ""
        pname = ""
        pnumber = ""
        for child in pin_node:
            if isinstance(child, list) and child:
                if child[0] == "name" and len(child) >= 2:
                    pname = child[1]
                elif child[0] == "number" and len(child) >= 2:
                    pnumber = child[1]
        if pnumber and pnumber not in existing_numbers:
            symbol.pins.append(PinInfo(name=pname, number=pnumber, electrical_type=etype))
            existing_numbers.add(pnumber)


# ---------------------------------------------------------------------------
# .kicad_mod parser  (lightweight — just existence + pad count)
# ---------------------------------------------------------------------------

def parse_kicad_mod(path: Path) -> Optional[FootprintInfo]:
    """Parse a .kicad_mod file, returning footprint metadata."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    tree = parse_sexpr(text)
    if not isinstance(tree, list) or not tree or tree[0] != "footprint":
        # Older format used "module"
        if not isinstance(tree, list) or not tree or tree[0] != "module":
            return None

    fp_name = tree[1] if len(tree) > 1 else path.stem
    lib_name = path.parent.stem.replace(".pretty", "")
    desc = _prop_value(tree, "descr")
    pad_count = sum(1 for _ in _find_nodes(tree, "pad"))

    return FootprintInfo(
        name=fp_name,
        library=lib_name,
        description=desc,
        pad_count=pad_count,
    )
