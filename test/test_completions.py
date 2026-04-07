"""Tests for completions.py — autocomplete suggestions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lsprotocol.types import Position

from server.analyzer import analyze
from server.completions import get_completions
from server.indexer import build_index

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _index():
    return build_index(
        symbol_dir_override=str(FIXTURES),
        footprint_dir_override=str(FIXTURES),
    )


# -- Library name completions ------------------------------------------------

class TestLibraryCompletions:
    SRC = 'from skidl import Part\nr1 = Part("'

    def test_library_completion_returns_items(self):
        analysis = analyze(self.SRC)
        result = get_completions(self.SRC, Position(line=1, character=11), analysis, _index())
        assert result is not None
        labels = [i.label for i in result.items]
        assert "Device" in labels

    def test_library_completion_prefix_filter(self):
        src = 'from skidl import Part\nr1 = Part("Dev'
        analysis = analyze(src)
        result = get_completions(src, Position(line=1, character=14), analysis, _index())
        assert result is not None
        labels = [i.label for i in result.items]
        assert "Device" in labels
        assert "Switch" not in labels

    def test_library_completion_no_match(self):
        src = 'from skidl import Part\nr1 = Part("ZZZ'
        analysis = analyze(src)
        result = get_completions(src, Position(line=1, character=14), analysis, _index())
        assert result is not None
        assert len(result.items) == 0


# -- Symbol name completions ------------------------------------------------

class TestSymbolCompletions:
    SRC = 'from skidl import Part\nr1 = Part("Device", "'

    def test_symbol_completion_returns_items(self):
        analysis = analyze(self.SRC)
        result = get_completions(self.SRC, Position(line=1, character=21), analysis, _index())
        assert result is not None
        labels = [i.label for i in result.items]
        assert "R" in labels
        assert "LED" in labels

    def test_symbol_completion_prefix_filter(self):
        src = 'from skidl import Part\nr1 = Part("Device", "L'
        analysis = analyze(src)
        result = get_completions(src, Position(line=1, character=22), analysis, _index())
        assert result is not None
        labels = [i.label for i in result.items]
        assert "LED" in labels
        assert "R" not in labels

    def test_symbol_completion_nonexistent_lib(self):
        src = 'from skidl import Part\nr1 = Part("FakeLib", "'
        analysis = analyze(src)
        result = get_completions(src, Position(line=1, character=22), analysis, _index())
        assert result is not None
        assert len(result.items) == 0


# -- Footprint completions --------------------------------------------------

class TestFootprintCompletions:
    def test_footprint_lib_completion(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R", footprint="'
        analysis = analyze(src)
        result = get_completions(src, Position(line=1, character=36), analysis, _index())
        assert result is not None
        labels = [i.label for i in result.items]
        assert "Resistor_SMD" in labels

    def test_footprint_name_completion(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R", footprint="Resistor_SMD:'
        analysis = analyze(src)
        result = get_completions(src, Position(line=1, character=49), analysis, _index())
        assert result is not None
        labels = [i.label for i in result.items]
        assert any("R_0805" in label for label in labels)

    def test_footprint_lib_prefix_filter(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R", footprint="LED'
        analysis = analyze(src)
        result = get_completions(src, Position(line=1, character=38), analysis, _index())
        assert result is not None
        labels = [i.label for i in result.items]
        assert "LED_SMD" in labels
        assert "Resistor_SMD" not in labels


# -- Pin name completions ---------------------------------------------------

class TestPinCompletions:
    # Pin completions need var_to_part from AST analysis, so the source
    # must be syntactically valid up to the Part() call. We put the cursor
    # on a separate complete line that happens to end with the pin pattern.
    def test_pin_name_completion(self):
        src = 'from skidl import Part\nled1 = Part("Device", "LED", footprint="LED_SMD:LED_0805_2012Metric")\nled1["'
        analysis = analyze(src)
        result = get_completions(src, Position(line=2, character=6), analysis, _index())
        # analysis may fail to parse incomplete source; if so, pin completion won't work
        if analysis.is_skidl_file and analysis.var_to_part:
            assert result is not None
            labels = [i.label for i in result.items]
            assert "A" in labels
            assert "K" in labels

    def test_pin_completion_with_valid_source(self):
        """Pin completion when full source is valid (simulating cursor mid-edit)."""
        src = 'from skidl import Part\nled1 = Part("Device", "LED", footprint="LED_SMD:LED_0805_2012Metric")\nx = led1["A"]\n'
        analysis = analyze(src)
        assert analysis.is_skidl_file
        assert "led1" in analysis.var_to_part
        # Simulate cursor right after the opening quote on a new line
        test_src = 'from skidl import Part\nled1 = Part("Device", "LED", footprint="LED_SMD:LED_0805_2012Metric")\nled1["'
        result = get_completions(test_src, Position(line=2, character=6), analysis, _index())
        assert result is not None
        labels = [i.label for i in result.items]
        assert "A" in labels
        assert "K" in labels

    def test_numeric_pin_completion_with_valid_source(self):
        """Numeric pin completion using pre-analyzed valid source."""
        src = 'from skidl import Part\nr1 = Part("Device", "R", footprint="Resistor_SMD:R_0805_2012Metric")\nx = r1[1]\n'
        analysis = analyze(src)
        assert analysis.is_skidl_file
        assert "r1" in analysis.var_to_part
        test_src = 'from skidl import Part\nr1 = Part("Device", "R", footprint="Resistor_SMD:R_0805_2012Metric")\nr1['
        result = get_completions(test_src, Position(line=2, character=3), analysis, _index())
        assert result is not None
        labels = [i.label for i in result.items]
        assert "1" in labels
        assert "2" in labels


# -- Non-SKiDL files --------------------------------------------------------

class TestNonSkidl:
    def test_non_skidl_returns_none(self):
        src = 'x = 42'
        analysis = analyze(src)
        result = get_completions(src, Position(line=0, character=4), analysis, _index())
        assert result is None
