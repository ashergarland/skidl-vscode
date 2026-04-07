"""Tests for diagnostics.py — validation against the library index."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.analyzer import analyze
from server.diagnostics import compute_diagnostics
from server.indexer import LibraryIndex, build_index

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
        diags = compute_diagnostics(analysis, index)
        assert len(diags) == 0

    def test_bad_library_name(self):
        index = _build_fixture_index()
        analysis = analyze(BAD_LIBRARY)
        diags = compute_diagnostics(analysis, index)
        assert len(diags) == 1
        assert "not found" in diags[0].message
        assert "Devce" in diags[0].message

    def test_bad_library_suggests(self):
        index = _build_fixture_index()
        analysis = analyze(BAD_LIBRARY)
        diags = compute_diagnostics(analysis, index)
        assert diags[0].data["suggestions"]
        # "Device" should be in suggestions
        assert "Device" in diags[0].data["suggestions"]

    def test_bad_symbol_name(self):
        index = _build_fixture_index()
        analysis = analyze(BAD_SYMBOL)
        diags = compute_diagnostics(analysis, index)
        assert len(diags) == 1
        assert "Resistor" in diags[0].message

    def test_bad_footprint(self):
        index = _build_fixture_index()
        analysis = analyze(BAD_FOOTPRINT)
        diags = compute_diagnostics(analysis, index)
        assert len(diags) == 1
        assert "R_9999_Nonexistent" in diags[0].message

    def test_bad_pin(self):
        index = _build_fixture_index()
        analysis = analyze(BAD_PIN)
        diags = compute_diagnostics(analysis, index)
        assert len(diags) == 1
        assert "Pin 'X'" in diags[0].message

    def test_non_skidl_file_no_diags(self):
        index = _build_fixture_index()
        analysis = analyze("import os\nx = 1\n")
        diags = compute_diagnostics(analysis, index)
        assert len(diags) == 0
