"""Tests for diagnostics.py -- validation against the library index."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analyzer import analyze
from core.diagnostics import compute_validation_data
from core.indexer import LibraryIndex, build_index

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _build_fixture_index() -> LibraryIndex:
    """Build an index from the test fixtures directory."""
    return build_index(
        symbol_dir_override=str(FIXTURES),
        footprint_dir_override=str(FIXTURES),
    )


VALID_SCRIPT = '''\
from skidl import Part, Net

r1 = Part("Device", "R", footprint="Resistor_SMD:R_0805_2012Metric")
led1 = Part("Device", "LED", footprint="LED_SMD:LED_0805_2012Metric")
r1[1]
r1[2]
led1["A"]
led1["K"]
'''

BAD_LIBRARY = '''\
from skidl import Part

r1 = Part("Devce", "R")
'''

BAD_SYMBOL = '''\
from skidl import Part

r1 = Part("Device", "Resistor")
'''

BAD_FOOTPRINT = '''\
from skidl import Part

r1 = Part("Device", "R", footprint="Resistor_SMD:R_9999_Nonexistent")
'''

BAD_PIN = '''\
from skidl import Part

led1 = Part("Device", "LED")
led1["X"]
'''


class TestDiagnostics:
    def test_valid_script_no_errors(self):
        index = _build_fixture_index()
        analysis = analyze(VALID_SCRIPT)
        issues = compute_validation_data(analysis, index)
        assert len(issues) == 0

    def test_bad_library_name(self):
        index = _build_fixture_index()
        analysis = analyze(BAD_LIBRARY)
        issues = compute_validation_data(analysis, index)
        assert len(issues) == 1
        assert "not found" in issues[0].message
        assert "Devce" in issues[0].message

    def test_bad_library_suggests(self):
        index = _build_fixture_index()
        analysis = analyze(BAD_LIBRARY)
        issues = compute_validation_data(analysis, index)
        assert issues[0].suggestions
        assert "Device" in issues[0].suggestions

    def test_bad_symbol_name(self):
        index = _build_fixture_index()
        analysis = analyze(BAD_SYMBOL)
        issues = compute_validation_data(analysis, index)
        assert len(issues) == 1
        assert "Resistor" in issues[0].message

    def test_bad_footprint(self):
        index = _build_fixture_index()
        analysis = analyze(BAD_FOOTPRINT)
        issues = compute_validation_data(analysis, index)
        assert len(issues) == 1
        assert "R_9999_Nonexistent" in issues[0].message

    def test_bad_pin(self):
        index = _build_fixture_index()
        analysis = analyze(BAD_PIN)
        issues = compute_validation_data(analysis, index)
        assert len(issues) == 1
        assert "Pin 'X'" in issues[0].message

    def test_non_skidl_file_no_diags(self):
        index = _build_fixture_index()
        analysis = analyze("import os\nx = 1\n")
        issues = compute_validation_data(analysis, index)
        assert len(issues) == 0
