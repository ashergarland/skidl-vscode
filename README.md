# SKiDL Language Server - VS Code Extension

[![CI](https://github.com/ashergarland/skidl-vscode/actions/workflows/ci.yml/badge.svg)](https://github.com/ashergarland/skidl-vscode/actions/workflows/ci.yml)
[![Version](https://img.shields.io/github/v/release/ashergarland/skidl-vscode?label=version)](https://github.com/ashergarland/skidl-vscode/releases)

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

## Requirements

- VS Code 1.85+
- Python 3.10+ with `pygls` and `lsprotocol` installed
- KiCad 7, 8, 9, or 10 (for the symbol/footprint libraries)
- SKiDL itself is **not** required. The extension parses `.kicad_sym` files directly.

## Installation

### From VSIX

1. Build the extension (see [Development](#development) below)
2. In VS Code, open Extensions, click the `...` menu, and choose "Install from VSIX..."
3. Select the `.vsix` file

The extension will automatically detect and install the required Python dependencies (`pygls`, `lsprotocol`) on first activation. If auto-install fails, you can install them manually:

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

1. Environment variables: `KICAD9_SYMBOL_DIR`, `KICAD8_SYMBOL_DIR`, etc.
2. Default install paths for your OS

### Manual Override

If auto-detection doesn't work, set the paths explicitly:

```json
{
  "skidl.kicadSymbolDir": "C:\\Program Files\\KiCad\\9.0\\share\\kicad\\symbols",
  "skidl.kicadFootprintDir": "C:\\Program Files\\KiCad\\9.0\\share\\kicad\\footprints"
}
```

## Commands

| Command | Description |
|---------|-------------|
| `SKiDL: Rebuild KiCad Library Index` | Re-scan KiCad libraries and rebuild the in-memory index |

## Development

### Prerequisites

- Node.js 18+
- Python 3.10+

### Setup

```bash
# Install Node dependencies
npm install

# Install Python dependencies
pip install -r requirements.txt
```

### Build

```bash
npm run compile
```

### Test

```bash
# Python server tests
npm run test:server

# Or directly
python -m pytest test/ -v
```

### Package

```bash
npm run package
```

This creates a `.vsix` file you can install in VS Code.

## Architecture

| File | Purpose |
|------|---------|
| `src/extension.ts` | TypeScript LSP client (launches the Python server over stdio) |
| `server/server.py` | pygls language server entry point |
| `server/indexer.py` | KiCad library discovery and indexing |
| `server/analyzer.py` | Python AST analysis for SKiDL patterns |
| `server/diagnostics.py` | Diagnostic provider |
| `server/completions.py` | Completion provider |
| `server/hover.py` | Hover documentation provider |
| `server/kicad_parser.py` | .kicad_sym / .kicad_mod S-expression parser |

The **TypeScript side** is a minimal LSP client that launches the Python server over stdio. The Python server does the heavy lifting: parsing KiCad library files, walking the Python AST to find `Part()` calls and pin accesses, and validating everything against an in-memory index.

## How It Works

1. On activation, the server scans your KiCad symbol (`.kicad_sym`) and footprint (`.pretty/`) directories
2. It builds an in-memory index of all libraries, symbols, pins, and footprints
3. When you open or edit a Python file that imports `skidl`, it:
   - Parses the AST to find `Part()` calls and pin accesses
   - Validates library names, symbol names, footprints, and pins against the index
   - Reports errors as LSP diagnostics (red squiggles)
4. Completions and hover use the same index for instant results

## License

MIT
