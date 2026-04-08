"""Shared response models for LSP and MCP interfaces.

These plain dataclasses decouple validation/completion/hover logic from
LSP-specific types, allowing the same core to serve both the Language
Server and the MCP server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DiagnosticItem:
    message: str
    severity: str  # "error" | "warning" | "info" | "hint"
    kind: str  # "library" | "symbol" | "footprint" | "fp_library" | "pin"
    value: str
    suggestions: list[str] = field(default_factory=list)
    start_line: int = 0
    start_col: int = 0
    end_line: int = 0
    end_col: int = 0
    # Optional extra context
    library: str = ""
    symbol: str = ""


@dataclass
class CompletionItemData:
    label: str
    kind: str  # "module" | "class" | "value" | "field"
    detail: str = ""
    insert_text: str = ""


@dataclass
class HoverResult:
    markdown: str
    start_line: int = 0
    start_col: int = 0
    end_line: int = 0
    end_col: int = 0
