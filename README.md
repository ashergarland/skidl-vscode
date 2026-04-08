# SKiDL IntelliSense - VS Code Extension

[![CI](https://github.com/ashergarland/skidl-vscode/actions/workflows/ci.yml/badge.svg)](https://github.com/ashergarland/skidl-vscode/actions/workflows/ci.yml)
[![Version](https://img.shields.io/github/v/release/ashergarland/skidl-vscode?label=version)](https://github.com/ashergarland/skidl-vscode/releases)
[![Marketplace](https://img.shields.io/visual-studio-marketplace/v/ashergarland.skidl-lsp?label=marketplace)](https://marketplace.visualstudio.com/items?itemName=ashergarland.skidl-lsp)

A VS Code extension that provides real-time language intelligence for [SKiDL](https://github.com/devbisme/skidl) Python files. Validates KiCad symbol names, footprint names, and pin names against your installed KiCad libraries before you ever run the script.

## Features

### Diagnostics (Error Squiggles)

The extension underlines errors in real-time:

- **Library validation**: `Part("Devce", ...)` flags the library name: `KiCad symbol library 'Devce' not found. Did you mean: Device?`
- **Symbol validation**: `Part("Device", "Resistor")` flags the symbol: `Symbol 'Resistor' not found in library 'Device'. Did you mean: R?`
- **Footprint validation**: `footprint="Resistor_SMD:R_9999"` flags the footprint: `Footprint 'R_9999' not found in footprint library 'Resistor_SMD'`
- **Pin validation**: `led1["X"]` flags the pin: `Pin 'X' not found on symbol 'LED'. Available pins: A, K, 1, 2`

### Autocomplete

Trigger smart completions as you type:

- **Library names**: inside `Part("` suggests `Device`, `Connector`, `Switch`, etc.
- **Symbol names**: inside `Part("Device", "` suggests `R`, `C`, `LED`, etc.
- **Footprints**: inside `footprint="` suggests `Resistor_SMD:R_0805_2012Metric`, etc.
- **Pin names**: inside `part["` suggests pin names for that specific symbol

### Hover Documentation

Hover over any SKiDL construct to see documentation:

- **Part() calls**: symbol description, pin list, default footprint
- **Pin references**: pin name, number, electrical type
- **Footprint strings**: description and pad count

### Quick-Fix Code Actions

- **"Did you mean?"**: one-click replacements when a name is close to a valid one
- **Fuzzy matching**: powered by fuzzy matching (Levenshtein distance)

### Status Bar

- **Progress indicator**: shows indexing status in the status bar while KiCad libraries are loading
- **Click to rebuild**: click the status bar item to rebuild the index at any time

### Performance

- **Cached index**: the KiCad library index is cached to disk, keyed by directory fingerprint (file names, sizes, and modification times)
- **First load**: ~45s for a full KiCad 10 install (222 symbol libs, 155 footprint libs)
- **Cached load**: <1s on subsequent startups
- **Auto-invalidation**: the cache rebuilds automatically when KiCad libraries change (e.g., after a KiCad version update)

## Requirements

- VS Code 1.85+
- Python 3.10+ with `pygls` and `lsprotocol` installed
- KiCad 7, 8, 9, or 10 (for the symbol/footprint libraries)
- SKiDL itself is **not** required. The extension parses `.kicad_sym` files directly.

## Installation

### From GitHub Releases

1. Download the latest `.vsix` from [Releases](https://github.com/ashergarland/skidl-vscode/releases)
2. In VS Code, open Extensions, click the `...` menu, and choose "Install from VSIX..."
3. Select the downloaded `.vsix` file

### From Source

See [Development](#development) below to build from source.

The extension will automatically detect and install the required Python dependencies (`pygls`, `lsprotocol`) on first activation. If auto-install fails, install them manually:

```bash
pip install pygls lsprotocol
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `skidl.kicadSymbolDir` | `""` (auto-detect) | Override path to KiCad symbol libraries |
| `skidl.kicadFootprintDir` | `""` (auto-detect) | Override path to KiCad footprint libraries |
| `skidl.enableDiagnostics` | `true` | Enable/disable error squiggles |
| `skidl.enableAutocomplete` | `true` | Enable/disable completions |
| `skidl.enableHover` | `true` | Enable/disable hover docs |
| `skidl.pythonPath` | `""` (auto-detect) | Path to Python interpreter |

### Auto-Detection

The extension automatically finds KiCad libraries by checking:

1. Environment variables: `KICAD10_SYMBOL_DIR`, `KICAD9_SYMBOL_DIR`, `KICAD8_SYMBOL_DIR`, etc.
2. Default install paths for your OS

### Manual Override

If auto-detection doesn't work, set the paths explicitly:

```json
{
  "skidl.kicadSymbolDir": "C:\\Program Files\\KiCad\\10.0\\share\\kicad\\symbols",
  "skidl.kicadFootprintDir": "C:\\Program Files\\KiCad\\10.0\\share\\kicad\\footprints"
}
```

## Commands

| Command | Description |
|---------|-------------|
| `SKiDL: Refresh KiCad Library Index` | Reload the library index, using the cache if it's still valid |
| `SKiDL: Force Rebuild KiCad Library Index` | Force a full rebuild of the KiCad library index (skips cache) |
| `SKiDL: Enable MCP Integration` | Configure the MCP server for VS Code, Claude Desktop, or clipboard |
| `SKiDL: Browse Components` | Search and browse KiCad symbols with live fuzzy search |
| `SKiDL: Browse Footprints` | Search and browse KiCad footprints with live fuzzy search |
| `SKiDL: Generate BOM` | Generate a Bill of Materials from Part() calls in the active file |
| `SKiDL: Validate Design` | Run full validation on the active file and show results |

## Development

### Prerequisites

- Node.js 18+
- Python 3.10+

### Setup

```bash
npm install
pip install pygls lsprotocol pytest
```

### Build

```bash
npm run build          # compile TypeScript + package VSIX
npm run compile        # compile TypeScript only
npm run package        # package VSIX only
```

### Test

```bash
npm test               # run all 123 Python server tests
```

### Release

```bash
npm run release:patch  # bump patch version, build, commit, tag, push
npm run release:minor  # bump minor version, build, commit, tag, push
npm run release:major  # bump major version, build, commit, tag, push
```

Pushing a `v*` tag triggers the [GitHub Actions release workflow](.github/workflows/release.yml) which runs tests and creates a GitHub Release with the VSIX attached.

To bump version without releasing:

```bash
npm run version:patch  # 0.3.0 -> 0.3.1
npm run version:minor  # 0.3.0 -> 0.4.0
npm run version:major  # 0.3.0 -> 1.0.0
```

## MCP Server (AI Agent Interface)

The extension includes an [MCP](https://modelcontextprotocol.io/) (Model Context Protocol) server that exposes KiCad library validation and browsing to AI agents. This lets an AI generate SKiDL code and validate it against your actual KiCad library installation -- catching hallucinated part names, wrong pin names, and invalid footprints before the code ever runs.

### Who is this for?

- **AI coding agents** (Claude, Copilot, custom agents) that generate SKiDL Python code and need to verify it
- **Agentic workflows** that generate PCB designs programmatically and need a validation oracle
- **Developers** building AI-assisted EDA tooling on top of KiCad

### How it works

The MCP server wraps the same indexer and validation engine used by the VS Code extension. An AI agent connects over stdio, calls tools to browse parts or validate code, and gets structured JSON responses it can act on.

```
AI Agent  <--stdio-->  MCP Server  -->  KiCad Libraries (local)
                            |
                       Cached Index (~1s startup)
```

### Setup

On first activation, the extension prompts you to set up the MCP server. Choose **Configure** to run the setup wizard, **Later** to be reminded next time, or **Don't ask again** to dismiss permanently. You can always run the setup manually from the Command Palette.

**Automatic setup (recommended):**

1. Open the Command Palette (`Ctrl+Shift+P`)
2. Run **SKiDL: Enable MCP Integration**
3. Choose your target: VS Code workspace, Claude Desktop, or clipboard

The command auto-detects your Python path and KiCad library overrides, writes the config file, and merges with any existing MCP server entries.

**Manual setup from source:**

```bash
git clone https://github.com/ashergarland/skidl-vscode.git
cd skidl-vscode
pip install pygls lsprotocol mcp
```

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "skidl": {
      "command": "python",
      "args": ["/path/to/skidl-vscode/mcp_server/server.py"]
    }
  }
}
```

**VS Code Copilot** (`.vscode/mcp.json` in your project):
```json
{
  "servers": {
    "skidl": {
      "command": "python",
      "args": ["${workspaceFolder}/mcp_server/server.py"]
    }
  }
}
```

**3. The server auto-detects your KiCad installation.** Override with environment variables if needed:

| Variable | Description |
|----------|-------------|
| `SKIDL_KICAD_SYMBOL_DIR` | Override auto-detected symbol library path |
| `SKIDL_KICAD_FOOTPRINT_DIR` | Override auto-detected footprint library path |

### Example: AI-assisted PCB design workflow

Once configured, an AI agent can use these tools in conversation:

**"What resistor symbols are available?"**
```
Tool: list_symbols({ library: "Device" })

Response:
[
  { "name": "R", "description": "Resistor", "default_footprint": "Resistor_SMD:R_0402_1005Metric" },
  { "name": "R_Pack04", "description": "4 resistor network", ... },
  ...
]
```

**"What pins does an LED have?"**
```
Tool: get_symbol_info({ library: "Device", symbol: "LED" })

Response:
{
  "name": "LED",
  "description": "Light emitting diode",
  "pins": [
    { "name": "A", "number": "1", "electrical_type": "passive" },
    { "name": "K", "number": "2", "electrical_type": "passive" }
  ]
}
```

**"Find me an 0805 footprint"**
```
Tool: search_footprints({ query: "R_0805", limit: 3 })

Response:
[
  { "library": "Resistor_SMD", "name": "R_0805_2012Metric", "pad_count": 2 },
  { "library": "Resistor_SMD", "name": "R_0805_2012Metric_Pad1.20x1.40mm_HandSolder", "pad_count": 2 },
  ...
]
```

**"Validate this SKiDL code I just wrote"**
```
Tool: validate_skidl_code({
  source: "from skidl import Part\nr1 = Part('Devce', 'R')\nr1['X'] += some_net"
})

Response:
[
  {
    "message": "KiCad symbol library 'Devce' not found. Did you mean: Device?",
    "severity": "error",
    "kind": "library",
    "suggestions": ["Device"],
    "location": { "start_line": 1, "start_col": 10, ... }
  }
]
```

The agent can then fix the code and re-validate -- creating a tight generate/validate/fix loop without ever running the script.

### Available Tools

| Tool | Description |
|------|-------------|
| `validate_skidl_code` | Validate SKiDL Python source against installed KiCad libraries |
| `list_libraries` | List all KiCad symbol library names |
| `list_symbols` | List symbols in a library with descriptions |
| `get_symbol_info` | Full symbol detail including all pins |
| `list_footprint_libraries` | List all footprint library names |
| `list_footprints` | List footprints in a library |
| `get_footprint_info` | Full footprint detail |
| `search_symbols` | Fuzzy-search symbols across all libraries |
| `search_footprints` | Fuzzy-search footprints across all libraries |
| `get_completions` | Autocomplete suggestions for a source position |
| `get_documentation_at` | Documentation for a source position |
| `generate_bom` | Generate a Bill of Materials from SKiDL source code |
| `rebuild_index` | Force rebuild the KiCad library index |

## Architecture

| Directory | Purpose |
|-----------|---------|
| `vscode_extension/` | TypeScript LSP client (launches the Python server over stdio) |
| `core/` | Pure Python analysis, validation, and documentation logic (no LSP/MCP deps) |
| `lsp_server/` | pygls language server entry point + LSP type conversion |
| `mcp_server/` | FastMCP server entry point (AI agent interface) |
| `tests/` | pytest test suite with KiCad fixture libraries |

| File | Purpose |
|------|---------|
| `core/analyzer.py` | Python AST analysis for SKiDL patterns |
| `core/models.py` | Shared response models (`ValidationIssue`, `CompletionSuggestion`, `SymbolDocumentation`) |
| `core/indexer.py` | KiCad library discovery, indexing, and caching |
| `core/diagnostics.py` | Validation provider |
| `core/completions.py` | Completion provider |
| `core/documentation.py` | Symbol/pin/footprint documentation provider |
| `core/kicad_parser.py` | Streaming `.kicad_sym` / `.kicad_mod` parser (regex + bracket counting) |

The **TypeScript side** is a minimal LSP client that launches the Python server over stdio and manages the status bar indicator. The Python server does the heavy lifting: parsing KiCad library files with a streaming parser, walking the Python AST to find `Part()` calls and pin accesses, and validating everything against a cached in-memory index.

## How It Works

1. On activation, the server checks for a cached index matching the current KiCad library directory fingerprint
2. On cache miss, it scans all KiCad symbol (`.kicad_sym`) and footprint (`.pretty/`) files using a streaming parser, builds the index, and saves it to disk
3. When you open or edit a Python file that imports `skidl`, it:
   - Parses the AST to find `Part()` calls and pin accesses
   - Validates library names, symbol names, footprints, and pins against the index
   - Reports errors as LSP diagnostics (red squiggles)
4. Completions and hover use the same index for instant results

## License

MIT
