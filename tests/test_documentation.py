"""Tests for documentation.py -- symbol/pin/footprint documentation provider."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analyzer import analyze
from core.documentation import get_documentation
from core.indexer import build_index

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _index():
    return build_index(
        symbol_dir_override=str(FIXTURES),
        footprint_dir_override=str(FIXTURES),
    )


SCRIPT = '''\
from skidl import Part, Net

r1 = Part("Device", "R", value="330", footprint="Resistor_SMD:R_0805_2012Metric")
led1 = Part("Device", "LED", footprint="LED_SMD:LED_0805_2012Metric")
led1["A"]
'''


# -- Symbol documentation ---------------------------------------------------

class TestSymbolDocumentation:
    def test_doc_on_symbol_name(self):
        analysis = analyze(SCRIPT)
        result = get_documentation(SCRIPT, 2, 21, analysis, _index())
        assert result is not None
        assert "R" in result.markdown

    def test_doc_on_led_symbol(self):
        analysis = analyze(SCRIPT)
        result = get_documentation(SCRIPT, 3, 22, analysis, _index())
        assert result is not None
        assert "LED" in result.markdown

    def test_doc_shows_pins(self):
        analysis = analyze(SCRIPT)
        result = get_documentation(SCRIPT, 3, 22, analysis, _index())
        assert result is not None
        assert "A" in result.markdown
        assert "K" in result.markdown


# -- Library documentation --------------------------------------------------

class TestLibraryDocumentation:
    def test_doc_on_library_name(self):
        analysis = analyze(SCRIPT)
        result = get_documentation(SCRIPT, 2, 11, analysis, _index())
        assert result is not None
        assert "Device" in result.markdown
        assert "symbols" in result.markdown.lower()


# -- Footprint documentation ------------------------------------------------

class TestFootprintDocumentation:
    def test_doc_on_footprint(self):
        analysis = analyze(SCRIPT)
        lines = SCRIPT.splitlines()
        fp_str = 'Resistor_SMD:R_0805_2012Metric'
        fp_col = lines[2].index(fp_str) + 5
        result = get_documentation(SCRIPT, 2, fp_col, analysis, _index())
        assert result is not None
        assert "R_0805_2012Metric" in result.markdown


# -- Pin documentation -------------------------------------------------------

class TestPinDocumentation:
    def test_doc_on_pin_access(self):
        analysis = analyze(SCRIPT)
        lines = SCRIPT.splitlines()
        pin_col = lines[4].index('"A"') + 1
        result = get_documentation(SCRIPT, 4, pin_col, analysis, _index())
        assert result is not None
        assert "A" in result.markdown
        assert "Pin" in result.markdown


# -- No documentation -------------------------------------------------------

class TestNoDocumentation:
    def test_non_skidl_returns_none(self):
        src = 'x = 42'
        analysis = analyze(src)
        result = get_documentation(src, 0, 2, analysis, _index())
        assert result is None

    def test_doc_outside_spans_returns_none(self):
        analysis = analyze(SCRIPT)
        result = get_documentation(SCRIPT, 0, 0, analysis, _index())
        assert result is None
