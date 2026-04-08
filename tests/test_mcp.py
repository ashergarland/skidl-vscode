"""Tests for the MCP server tool functions.

Tests the MCP tool handler functions directly (not over stdio),
using the same fixture libraries as the existing test suite.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.indexer import LibraryIndex, build_index
from mcp_server.server import (
    _get_index,
    generate_bom,
    get_completions,
    get_documentation_at,
    get_footprint_info,
    get_symbol_info,
    list_footprint_libraries,
    list_footprints,
    list_libraries,
    list_symbols,
    search_footprints,
    search_symbols,
    validate_skidl_code,
)
import mcp_server.server as mcp_mod

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _install_fixture_index():
    """Build a fixture index and inject it into the MCP server module."""
    idx = build_index(
        symbol_dir_override=str(FIXTURES),
        footprint_dir_override=str(FIXTURES),
    )
    mcp_mod._index = idx
    return idx


# ---------------------------------------------------------------------------
# validate_skidl_code
# ---------------------------------------------------------------------------

class TestValidateSkidlCode:
    def setup_method(self):
        _install_fixture_index()

    def test_valid_code_no_errors(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R")'
        result = validate_skidl_code(src)
        assert result == []

    def test_bad_library(self):
        src = 'from skidl import Part\nr1 = Part("Devce", "R")'
        result = validate_skidl_code(src)
        assert len(result) >= 1
        d = result[0]
        assert d["kind"] == "library"
        assert d["severity"] == "error"
        assert "Devce" in d["message"]
        assert "Device" in d["suggestions"]

    def test_bad_symbol(self):
        src = 'from skidl import Part\nr1 = Part("Device", "Resistor")'
        result = validate_skidl_code(src)
        assert len(result) >= 1
        assert result[0]["kind"] == "symbol"
        assert "Resistor" in result[0]["message"]

    def test_bad_pin(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R")\nr1["X"]'
        result = validate_skidl_code(src)
        assert len(result) >= 1
        assert result[0]["kind"] == "pin"

    def test_non_skidl_file(self):
        src = 'print("hello")'
        result = validate_skidl_code(src)
        assert result == []

    def test_has_location(self):
        src = 'from skidl import Part\nr1 = Part("Devce", "R")'
        result = validate_skidl_code(src)
        assert len(result) >= 1
        loc = result[0]["location"]
        assert "start_line" in loc
        assert "start_col" in loc


# ---------------------------------------------------------------------------
# Library browsing
# ---------------------------------------------------------------------------

class TestListLibraries:
    def setup_method(self):
        _install_fixture_index()

    def test_returns_list(self):
        result = list_libraries()
        assert isinstance(result, list)
        assert "Device" in result

    def test_contains_known_libs(self):
        result = list_libraries()
        assert "Device" in result


class TestListSymbols:
    def setup_method(self):
        _install_fixture_index()

    def test_lists_symbols_in_device(self):
        result = list_symbols("Device")
        names = [s["name"] for s in result]
        assert "R" in names

    def test_symbol_has_description(self):
        result = list_symbols("Device")
        r = next(s for s in result if s["name"] == "R")
        assert "description" in r

    def test_nonexistent_library_returns_error(self):
        result = list_symbols("FakeLib")
        assert len(result) == 1
        assert "error" in result[0]


class TestGetSymbolInfo:
    def setup_method(self):
        _install_fixture_index()

    def test_returns_symbol_detail(self):
        result = get_symbol_info("Device", "R")
        assert result["name"] == "R"
        assert "pins" in result
        assert len(result["pins"]) > 0

    def test_pins_have_fields(self):
        result = get_symbol_info("Device", "R")
        pin = result["pins"][0]
        assert "name" in pin
        assert "number" in pin
        assert "electrical_type" in pin

    def test_nonexistent_symbol_returns_error(self):
        result = get_symbol_info("Device", "FakePart")
        assert "error" in result


class TestListFootprintLibraries:
    def setup_method(self):
        _install_fixture_index()

    def test_returns_list(self):
        result = list_footprint_libraries()
        assert isinstance(result, list)


class TestListFootprints:
    def setup_method(self):
        _install_fixture_index()

    def test_nonexistent_library_returns_error(self):
        result = list_footprints("FakeLib")
        assert len(result) == 1
        assert "error" in result[0]


class TestGetFootprintInfo:
    def setup_method(self):
        _install_fixture_index()

    def test_nonexistent_footprint_returns_error(self):
        result = get_footprint_info("FakeLib", "FakeFP")
        assert "error" in result


# ---------------------------------------------------------------------------
# Search tools
# ---------------------------------------------------------------------------

class TestSearchSymbols:
    def setup_method(self):
        _install_fixture_index()

    def test_exact_match(self):
        result = search_symbols("R", limit=5)
        assert len(result) > 0
        assert any(r["name"] == "R" for r in result)

    def test_fuzzy_match(self):
        result = search_symbols("LED", limit=5)
        assert len(result) > 0

    def test_limit_respected(self):
        result = search_symbols("R", limit=2)
        assert len(result) <= 2

    def test_returns_library_field(self):
        result = search_symbols("R", limit=1)
        assert "library" in result[0]


class TestSearchFootprints:
    def setup_method(self):
        _install_fixture_index()

    def test_returns_list(self):
        result = search_footprints("R_0805", limit=5)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Completion / documentation tools
# ---------------------------------------------------------------------------

class TestGetCompletions:
    def setup_method(self):
        _install_fixture_index()

    def test_library_completions(self):
        src = 'from skidl import Part\nr1 = Part("D'
        result = get_completions(src, line=1, character=12)
        labels = [c["label"] for c in result]
        assert "Device" in labels

    def test_symbol_completions(self):
        src = 'from skidl import Part\nr1 = Part("Device", "'
        result = get_completions(src, line=1, character=21)
        labels = [c["label"] for c in result]
        assert "R" in labels

    def test_no_context_returns_empty(self):
        src = 'from skidl import Part\nprint("hello")'
        result = get_completions(src, line=1, character=5)
        assert result == []


class TestGetDocumentation:
    def setup_method(self):
        _install_fixture_index()

    def test_doc_on_symbol(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R")'
        result = get_documentation_at(src, line=1, character=22)
        if result:
            assert "markdown" in result
            assert "R" in result["markdown"]

    def test_doc_no_result(self):
        src = 'from skidl import Part\nprint("hello")'
        result = get_documentation_at(src, line=1, character=0)
        assert result is None


# ---------------------------------------------------------------------------
# BOM generation
# ---------------------------------------------------------------------------

class TestGenerateBom:
    def setup_method(self):
        _install_fixture_index()

    def test_simple_bom(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R", footprint="Resistor_SMD:R_0805_2012Metric")\nled1 = Part("Device", "LED")'
        result = generate_bom(src)
        assert len(result) == 2
        symbols = {e["symbol"] for e in result}
        assert "R" in symbols
        assert "LED" in symbols

    def test_grouped_parts(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R")\nr2 = Part("Device", "R")'
        result = generate_bom(src)
        r_entry = next(e for e in result if e["symbol"] == "R")
        assert r_entry["quantity"] == 2

    def test_empty_source(self):
        result = generate_bom('print("hello")')
        assert result == []

    def test_result_fields(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R")'
        result = generate_bom(src)
        entry = result[0]
        assert "reference" in entry
        assert "library" in entry
        assert "symbol" in entry
        assert "footprint" in entry
        assert "description" in entry
        assert "quantity" in entry
