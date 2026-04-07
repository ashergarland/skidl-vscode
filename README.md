# SKiDL Language Server — VS Code Extension

Real-time language intelligence for [SKiDL](https://github.com/devbisme/skidl) Python files. Validates KiCad symbol names, footprint names, and pin names against your installed KiCad libraries **before you ever run the script**.

## Features

### Diagnostics (Error Squiggles)

The extension underlines errors in real-time:

- **Library validation** — `Part("Devce", ...)` → `KiCad symbol library 'Devce' not found. Did you mean: Device?`
- **Symbol validation** — `Part("Device", "Resistor")` → `Symbol 'Resistor' not found in library 'Device'. Did you mean: R?`
- **Footprint validation** — `footprint="Resistor_SMD:R_9999"` → `Footprint 'R_9999' not found in footprint library 'Resistor_SMD'`
- **Pin validation** — `led1["X"]` → `Pin 'X' not found on symbol 'LED'. Available pins: A, K, 1, 2`

### Autocomplete

Trigger smart completions as you type:

- **Library names** — inside `Part("` → suggests `Device`, `Connector`, `Switch`, …
- **Symbol names** — inside `Part("Device", "` → suggests `R`, `C`, `LED`, …
- **Footprints** — inside `footprint="` → suggests `Resistor_SMD:R_0805_2012Metric`, …
- **Pin names** — inside `part["` → suggests pin names for that specific symbol

### Hover Documentation

Hover over any SKiDL construct to see documentation:

- **Part() calls** — symbol description, pin list, default footprint
- **Pin references** — pin name, number, electrical type
- **Footprint strings** — description and pad count

### Quick-Fix Code Actions

- "Did you mean?" replacements when a name is close to a valid one
- Powered by fuzzy matching (Levenshtein distance)

## Requirements

- **VS Code** 1.85+
- **Python** 3.10+ with `pygls` and `lsprotocol` installed
- **KiCad** 7, 8, 9, or 10 installed (for symbol/footprint libraries)
- SKiDL is **not** required — the extension parses `.kicad_sym` files directly

## Installation

### From VSIX

1. Build the extension (see Development below)
2. In VS Code: `Extensions` → `…` → `Install from VSIX…`
3. Select the generated `.vsix` file

### Python Server Dependencies

Install the language server dependencies into your Python environment:

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
| `SKiDL: Rebuild KiCad Library Index` | Re-scan KiCad libraries and rebuild the index |

## Development

### Prerequisites

- Node.js 18+
- Python 3.10+
- npm

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

```
src/extension.ts     — Thin TypeScript client (launches Python server, connects LSP)
server/server.py     — pygls Language Server entry point
server/indexer.py    — KiCad library discovery and indexing
server/analyzer.py   — Python AST analysis for SKiDL patterns
server/diagnostics.py — Diagnostic provider (error squiggles)
server/completions.py — Completion provider (autocomplete)
server/hover.py      — Hover documentation provider
server/kicad_parser.py — .kicad_sym / .kicad_mod S-expression parser
```

The **TypeScript side** is a minimal LSP client that launches the Python server over stdio. The **Python side** does all the heavy lifting: parsing KiCad files, analyzing Python ASTs, and providing language features.

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
