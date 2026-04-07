"""Tests for hover.py — hover documentation provider."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lsprotocol.types import Position

from server.analyzer import analyze
from server.hover import get_hover
from server.indexer import build_index

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


# -- Symbol hover -----------------------------------------------------------

class TestSymbolHover:
    def test_hover_on_symbol_name(self):
        analysis = analyze(SCRIPT)
        # "R" is at line 2, cols ~20-23 (inside quotes)
        hover = get_hover(SCRIPT, Position(line=2, character=21), analysis, _index())
        assert hover is not None
        assert "R" in hover.contents.value

    def test_hover_on_led_symbol(self):
        analysis = analyze(SCRIPT)
        # "LED" at line 3
        hover = get_hover(SCRIPT, Position(line=3, character=22), analysis, _index())
        assert hover is not None
        assert "LED" in hover.contents.value

    def test_hover_shows_pins(self):
        analysis = analyze(SCRIPT)
        hover = get_hover(SCRIPT, Position(line=3, character=22), analysis, _index())
        assert hover is not None
        assert "A" in hover.contents.value
        assert "K" in hover.contents.value


# -- Library hover ----------------------------------------------------------

class TestLibraryHover:
    def test_hover_on_library_name(self):
        analysis = analyze(SCRIPT)
        # "Device" at line 2, ~col 10-16
        hover = get_hover(SCRIPT, Position(line=2, character=11), analysis, _index())
        assert hover is not None
        assert "Device" in hover.contents.value
        assert "symbols" in hover.contents.value.lower()


# -- Footprint hover --------------------------------------------------------

class TestFootprintHover:
    def test_hover_on_footprint(self):
        analysis = analyze(SCRIPT)
        # footprint="Resistor_SMD:R_0805_2012Metric" at line 2
        # Find the col position of the footprint value
        lines = SCRIPT.splitlines()
        fp_str = 'Resistor_SMD:R_0805_2012Metric'
        fp_col = lines[2].index(fp_str) + 5  # inside the string
        hover = get_hover(SCRIPT, Position(line=2, character=fp_col), analysis, _index())
        assert hover is not None
        assert "R_0805_2012Metric" in hover.contents.value


# -- Pin hover --------------------------------------------------------------

class TestPinHover:
    def test_hover_on_pin_access(self):
        analysis = analyze(SCRIPT)
        # led1["A"] at line 4
        lines = SCRIPT.splitlines()
        pin_col = lines[4].index('"A"') + 1  # on the A
        hover = get_hover(SCRIPT, Position(line=4, character=pin_col), analysis, _index())
        assert hover is not None
        assert "A" in hover.contents.value
        assert "Pin" in hover.contents.value


# -- No hover ---------------------------------------------------------------

class TestNoHover:
    def test_non_skidl_returns_none(self):
        src = 'x = 42'
        analysis = analyze(src)
        hover = get_hover(src, Position(line=0, character=2), analysis, _index())
        assert hover is None

    def test_hover_outside_spans_returns_none(self):
        analysis = analyze(SCRIPT)
        # Line 0 col 0 is "from" keyword
        hover = get_hover(SCRIPT, Position(line=0, character=0), analysis, _index())
        assert hover is None
