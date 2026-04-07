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
npm test               # run all 76 Python server tests
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

## Architecture

| File | Purpose |
|------|---------|
| `src/extension.ts` | TypeScript LSP client (launches the Python server over stdio) |
| `server/server.py` | pygls language server entry point |
| `server/indexer.py` | KiCad library discovery, indexing, and caching |
| `server/analyzer.py` | Python AST analysis for SKiDL patterns |
| `server/diagnostics.py` | Diagnostic provider |
| `server/completions.py` | Completion provider |
| `server/hover.py` | Hover documentation provider |
| `server/kicad_parser.py` | Streaming `.kicad_sym` / `.kicad_mod` parser (regex + bracket counting) |

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
