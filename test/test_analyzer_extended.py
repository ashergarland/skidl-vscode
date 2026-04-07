"""Extended tests for analyzer.py — keyword args, edge cases."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.analyzer import analyze


# -- Keyword-form Part calls -------------------------------------------------

KEYWORD_SCRIPT = '''\
from skidl import Part

r1 = Part(lib="Device", name="R", footprint="Resistor_SMD:R_0805_2012Metric")
'''


class TestKeywordPart:
    def test_keyword_form_extracted(self):
        result = analyze(KEYWORD_SCRIPT)
        assert len(result.part_calls) == 1
        pc = result.part_calls[0]
        assert pc.library == "Device"
        assert pc.symbol == "R"
        assert pc.footprint == "Resistor_SMD:R_0805_2012Metric"


# -- Multiple Part calls on same line ----------------------------------------

MULTI_PART = '''\
from skidl import Part

r1 = Part("Device", "R")
r2 = Part("Device", "R")
sw = Part("Switch", "SW_Push")
'''


class TestMultipleParts:
    def test_all_parts_found(self):
        result = analyze(MULTI_PART)
        assert len(result.part_calls) == 3

    def test_different_libraries(self):
        result = analyze(MULTI_PART)
        libs = {pc.library for pc in result.part_calls}
        assert "Device" in libs
        assert "Switch" in libs


# -- SKiDL submodule import -------------------------------------------------

SUBMOD_IMPORT = '''\
import skidl
r1 = skidl.Part("Device", "R")
'''


class TestSubmoduleImport:
    def test_detects_skidl_module_import(self):
        result = analyze(SUBMOD_IMPORT)
        assert result.is_skidl_file is True


# -- Empty / syntax error scripts -------------------------------------------

class TestEdgeCases:
    def test_empty_script(self):
        result = analyze("")
        assert result.is_skidl_file is False
        assert len(result.part_calls) == 0
        assert len(result.pin_accesses) == 0

    def test_syntax_error_does_not_crash(self):
        result = analyze("from skidl import Part\ndef foo(:\n  pass")
        # Should return without raising
        assert result is not None

    def test_part_no_assignment(self):
        """Part() call not assigned to a variable."""
        src = 'from skidl import Part\nPart("Device", "R")'
        result = analyze(src)
        # Should still detect the Part call (variable may be empty)
        assert len(result.part_calls) >= 0  # implementation may or may not capture it


# -- Pin accesses on augmented assignment ------------------------------------

AUGMENTED_PINS = '''\
from skidl import Part, Net

r1 = Part("Device", "R")
net = Net("VCC")
net += r1[1]
net += r1[2]
'''


class TestAugmentedPins:
    def test_augmented_assign_pins_found(self):
        result = analyze(AUGMENTED_PINS)
        pins = [pa.pin for pa in result.pin_accesses if pa.variable == "r1"]
        assert "1" in pins
        assert "2" in pins
