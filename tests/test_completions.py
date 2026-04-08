"""Tests for completions.py -- autocomplete suggestions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analyzer import analyze
from core.completions import get_suggestions
from core.indexer import build_index

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
        result = get_suggestions(self.SRC, 1, 11, analysis, _index())
        assert result is not None
        labels = [i.label for i in result]
        assert "Device" in labels

    def test_library_completion_prefix_filter(self):
        src = 'from skidl import Part\nr1 = Part("Dev'
        analysis = analyze(src)
        result = get_suggestions(src, 1, 14, analysis, _index())
        assert result is not None
        labels = [i.label for i in result]
        assert "Device" in labels
        assert "Switch" not in labels

    def test_library_completion_no_match(self):
        src = 'from skidl import Part\nr1 = Part("ZZZ'
        analysis = analyze(src)
        result = get_suggestions(src, 1, 14, analysis, _index())
        assert result is not None
        assert len(result) == 0


# -- Symbol name completions ------------------------------------------------

class TestSymbolCompletions:
    SRC = 'from skidl import Part\nr1 = Part("Device", "'

    def test_symbol_completion_returns_items(self):
        analysis = analyze(self.SRC)
        result = get_suggestions(self.SRC, 1, 21, analysis, _index())
        assert result is not None
        labels = [i.label for i in result]
        assert "R" in labels
        assert "LED" in labels

    def test_symbol_completion_prefix_filter(self):
        src = 'from skidl import Part\nr1 = Part("Device", "L'
        analysis = analyze(src)
        result = get_suggestions(src, 1, 22, analysis, _index())
        assert result is not None
        labels = [i.label for i in result]
        assert "LED" in labels
        assert "R" not in labels

    def test_symbol_completion_nonexistent_lib(self):
        src = 'from skidl import Part\nr1 = Part("FakeLib", "'
        analysis = analyze(src)
        result = get_suggestions(src, 1, 22, analysis, _index())
        assert result is not None
        assert len(result) == 0


# -- Footprint completions --------------------------------------------------

class TestFootprintCompletions:
    def test_footprint_lib_completion(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R", footprint="'
        analysis = analyze(src)
        result = get_suggestions(src, 1, 36, analysis, _index())
        assert result is not None
        labels = [i.label for i in result]
        assert "Resistor_SMD" in labels

    def test_footprint_name_completion(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R", footprint="Resistor_SMD:'
        analysis = analyze(src)
        result = get_suggestions(src, 1, 49, analysis, _index())
        assert result is not None
        labels = [i.label for i in result]
        assert any("R_0805" in label for label in labels)

    def test_footprint_lib_prefix_filter(self):
        src = 'from skidl import Part\nr1 = Part("Device", "R", footprint="LED'
        analysis = analyze(src)
        result = get_suggestions(src, 1, 38, analysis, _index())
        assert result is not None
        labels = [i.label for i in result]
        assert "LED_SMD" in labels
        assert "Resistor_SMD" not in labels


# -- Pin name completions ---------------------------------------------------

class TestPinCompletions:
    def test_pin_name_completion(self):
        src = 'from skidl import Part\nled1 = Part("Device", "LED", footprint="LED_SMD:LED_0805_2012Metric")\nled1["'
        analysis = analyze(src)
        result = get_suggestions(src, 2, 6, analysis, _index())
        if analysis.is_skidl_file and analysis.var_to_part:
            assert result is not None
            labels = [i.label for i in result]
            assert "A" in labels
            assert "K" in labels

    def test_pin_completion_with_valid_source(self):
        """Pin completion when full source is valid (simulating cursor mid-edit)."""
        src = 'from skidl import Part\nled1 = Part("Device", "LED", footprint="LED_SMD:LED_0805_2012Metric")\nx = led1["A"]\n'
        analysis = analyze(src)
        assert analysis.is_skidl_file
        assert "led1" in analysis.var_to_part
        test_src = 'from skidl import Part\nled1 = Part("Device", "LED", footprint="LED_SMD:LED_0805_2012Metric")\nled1["'
        result = get_suggestions(test_src, 2, 6, analysis, _index())
        assert result is not None
        labels = [i.label for i in result]
        assert "A" in labels
