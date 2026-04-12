# Changelog

All notable changes to the SKiDL IntelliSense extension will be documented in this file.

## [0.4.8] - 2026-04-12

### Major Release: MCP Server, Browse/BOM/Validate Commands, Full Restructure

This is a significant release that adds AI agent integration, four new interactive commands, and a complete project restructure for maintainability.

### Added

- **MCP Server** — Full [Model Context Protocol](https://modelcontextprotocol.io/) server exposing 13 tools for AI agents to browse KiCad libraries, validate SKiDL code, and generate BOMs. Supports VS Code Copilot, Claude Desktop, and any MCP-compatible client.
- **MCP setup wizard** — `SKiDL: Enable MCP Integration` command auto-configures the MCP server for VS Code workspace, Claude Desktop, or clipboard. Prompts on first activation.
- **Browse Components** — `SKiDL: Browse Components` command with live fuzzy search across all KiCad symbol libraries. Shows symbol info and offers "Insert Part()" or "Copy" actions.
- **Browse Footprints** — `SKiDL: Browse Footprints` command with live fuzzy search across all KiCad footprint libraries. Copies `Library:Footprint` to clipboard on selection.
- **Generate BOM** — `SKiDL: Generate BOM` command parses `Part()` calls in the active file, resolves descriptions and default footprints from the index, groups identical parts, and opens a formatted markdown table.
- **Validate Design** — `SKiDL: Validate Design` command runs full validation on the active file and displays all issues (invalid libraries, symbols, footprints, pins) with suggestions in the output channel.
- **`core/search.py`** — Extracted fuzzy search logic shared between LSP and MCP servers.
- **`core/bom.py`** — Bill of Materials generation from SKiDL source analysis.
- **47 new tests** — `test_search.py`, `test_bom.py`, `test_mcp.py`, `test_documentation.py` (123 total, up from 76).

### Changed

- **Project restructure** — Reorganized from flat `server/` + `src/` into `core/`, `lsp_server/`, `mcp_server/`, `vscode_extension/` for clear separation of concerns. The `core/` layer has no LSP or MCP dependencies.
- **Hover → Documentation** — Renamed `server/hover.py` to `core/documentation.py` with an expanded provider that covers symbols, pins, footprints, and library names.
- **Shared models** — Added `core/models.py` with `ValidationIssue`, `CompletionSuggestion`, and `SymbolDocumentation` dataclasses used by both LSP and MCP.
- **LSP custom requests** — Added 5 custom LSP request handlers (`skidl/searchSymbols`, `skidl/searchFootprints`, `skidl/getSymbolInfo`, `skidl/generateBom`, `skidl/validateDesign`) used by the new TypeScript commands.

### Fixed

- **pygls Object params** — Custom LSP request params arrive as pygls `Object` (not `dict`) in pygls 2.1.1. All handlers now use `getattr()` with dict fallback.
- **Index timing** — Added `_index_ready` guards to all custom handlers to prevent empty results when requests arrive before the background index finishes loading.
- **Source text handling** — Generate BOM and Validate Design now send source text from the editor, avoiding `PermissionError` on workspace document lookup.

## [0.3.5] - 2026-04-05

- Renamed display name to "SKiDL IntelliSense" for VS Code Marketplace
- Fixed release workflow secrets access

## [0.3.4] - 2026-04-05

- Fixed release workflow secrets configuration

## [0.3.3] - 2026-04-05

- Initial public release
- Real-time diagnostics for library, symbol, footprint, and pin validation
- Autocomplete for library names, symbol names, footprints, and pin names
- Hover documentation for Part() calls, pin references, and footprint strings
- Quick-fix code actions with "Did you mean?" suggestions
- Cached KiCad library index with auto-invalidation
- Status bar progress indicator
