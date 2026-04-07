"""Python AST analysis for SKiDL patterns.

Walks the AST of a Python source file and extracts:
- Part() calls with library, symbol, and footprint arguments
- Variable-to-Part assignments
- Pin subscript accesses (part[pin_name] or part[pin_number])
- SKiDL import detection
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


@dataclass
class PartCall:
    """A Part() call found in the source."""
    variable: str          # assigned variable name, or "" if not assigned
    library: str           # first positional arg (string literal)
    symbol: str            # second positional arg (string literal)
    footprint: str         # footprint= kwarg (string literal)
    line: int              # 0-based line number
    col: int               # 0-based column
    end_line: int = 0
    end_col: int = 0

    # Precise spans for each field (line, col, end_line, end_col) — 0-based
    library_span: Optional[Tuple[int, int, int, int]] = None
    symbol_span: Optional[Tuple[int, int, int, int]] = None
    footprint_span: Optional[Tuple[int, int, int, int]] = None


@dataclass
class PinAccess:
    """A subscript access on a Part variable: part["A"] or part[1]."""
    variable: str          # the variable being subscripted
    pin: str               # the string/int literal used as subscript
    line: int
    col: int
    end_line: int = 0
    end_col: int = 0
    pin_span: Optional[Tuple[int, int, int, int]] = None


@dataclass
class AnalysisResult:
    """Complete analysis of a SKiDL source file."""
    is_skidl_file: bool = False
    part_calls: List[PartCall] = field(default_factory=list)
    pin_accesses: List[PinAccess] = field(default_factory=list)
    # variable name -> PartCall for resolving pin accesses
    var_to_part: Dict[str, PartCall] = field(default_factory=dict)


def _get_string_literal(node: ast.expr) -> Optional[str]:
    """Extract a string literal value from an AST node, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _get_int_literal(node: ast.expr) -> Optional[int]:
    """Extract an integer literal from an AST node, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return None


def _span(node: ast.expr) -> Tuple[int, int, int, int]:
    """Return (line, col, end_line, end_col) — 0-based."""
    return (
        node.lineno - 1,
        node.col_offset,
        (node.end_lineno or node.lineno) - 1,
        node.end_col_offset or node.col_offset,
    )


def _extract_part_call(call: ast.Call) -> Optional[PartCall]:
    """If *call* is a Part(...) call, extract fields; else return None."""
    # Check it's Part(...)
    func = call.func
    name: Optional[str] = None
    if isinstance(func, ast.Name) and func.id == "Part":
        name = "Part"
    elif isinstance(func, ast.Attribute) and func.attr == "Part":
        name = "Part"
    if not name:
        return None

    library = ""
    symbol = ""
    footprint = ""
    lib_span = None
    sym_span = None
    fp_span = None

    # Positional args
    if len(call.args) >= 1:
        val = _get_string_literal(call.args[0])
        if val is not None:
            library = val
            lib_span = _span(call.args[0])
    if len(call.args) >= 2:
        val = _get_string_literal(call.args[1])
        if val is not None:
            symbol = val
            sym_span = _span(call.args[1])

    # Keyword args (can override positionals)
    for kw in call.keywords:
        if kw.arg == "lib" or kw.arg == "library":
            val = _get_string_literal(kw.value)
            if val is not None:
                library = val
                lib_span = _span(kw.value)
        elif kw.arg == "name" or kw.arg == "symbol":
            val = _get_string_literal(kw.value)
            if val is not None:
                symbol = val
                sym_span = _span(kw.value)
        elif kw.arg == "footprint":
            val = _get_string_literal(kw.value)
            if val is not None:
                footprint = val
                fp_span = _span(kw.value)

    if not library and not symbol:
        return None

    return PartCall(
        variable="",
        library=library,
        symbol=symbol,
        footprint=footprint,
        line=call.lineno - 1,
        col=call.col_offset,
        end_line=(call.end_lineno or call.lineno) - 1,
        end_col=call.end_col_offset or call.col_offset,
        library_span=lib_span,
        symbol_span=sym_span,
        footprint_span=fp_span,
    )


def analyze(source: str) -> AnalysisResult:
    """Analyze a Python source string for SKiDL patterns."""
    result = AnalysisResult()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return result

    # Detect SKiDL imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "skidl" or alias.name.startswith("skidl."):
                    result.is_skidl_file = True
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "skidl" or node.module.startswith("skidl.")):
                result.is_skidl_file = True

    if not result.is_skidl_file:
        return result

    # Walk top-level statements
    for node in ast.walk(tree):
        # --- Part() calls ---
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                pc = _extract_part_call(node.value)
                if pc:
                    pc.variable = target.id
                    result.part_calls.append(pc)
                    result.var_to_part[target.id] = pc

        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            pc = _extract_part_call(node.value)
            if pc:
                result.part_calls.append(pc)

        # --- Pin accesses: var[...] ---
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                var_name = node.value.id
                sl = node.slice
                pin_val: Optional[str] = None
                pin_sp = None

                s_node = sl
                str_val = _get_string_literal(s_node)
                int_val = _get_int_literal(s_node)

                if str_val is not None:
                    pin_val = str_val
                    pin_sp = _span(s_node)
                elif int_val is not None:
                    pin_val = str(int_val)
                    pin_sp = _span(s_node)

                if pin_val is not None and var_name in result.var_to_part:
                    result.pin_accesses.append(PinAccess(
                        variable=var_name,
                        pin=pin_val,
                        line=node.lineno - 1,
                        col=node.col_offset,
                        end_line=(node.end_lineno or node.lineno) - 1,
                        end_col=node.end_col_offset or node.col_offset,
                        pin_span=pin_sp,
                    ))

    return result
