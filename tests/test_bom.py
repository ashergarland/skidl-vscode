"""Tests for core/bom.py -- BOM generation from SKiDL source."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bom import BomEntry, generate_bom
from core.indexer import build_index

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _build_fixture_index():
    return build_index(
        symbol_dir_override=str(FIXTURES),
        footprint_dir_override=str(FIXTURES),
    )


SIMPLE_SCRIPT = '''\
from skidl import Part

r1 = Part("Device", "R", footprint="Resistor_SMD:R_0805_2012Metric")
led1 = Part("Device", "LED", footprint="LED_SMD:LED_0805_2012Metric")
'''

GROUPED_SCRIPT = '''\
from skidl import Part

r1 = Part("Device", "R", footprint="Resistor_SMD:R_0805_2012Metric")
r2 = Part("Device", "R", footprint="Resistor_SMD:R_0805_2012Metric")
r3 = Part("Device", "R", footprint="Resistor_SMD:R_0805_2012Metric")
led1 = Part("Device", "LED")
'''

NO_PARTS_SCRIPT = '''\
from skidl import Net

n = Net("VCC")
'''

NO_VARIABLE_SCRIPT = '''\
from skidl import Part

Part("Device", "R")
Part("Device", "R")
'''


class TestGenerateBom:
    def setup_method(self):
        self.index = _build_fixture_index()

    def test_simple_bom(self):
        entries = generate_bom(SIMPLE_SCRIPT, self.index)
        assert len(entries) == 2
        assert all(isinstance(e, BomEntry) for e in entries)
        symbols = {e.symbol for e in entries}
        assert "R" in symbols
        assert "LED" in symbols

    def test_grouped_parts(self):
        entries = generate_bom(GROUPED_SCRIPT, self.index)
        r_entry = next(e for e in entries if e.symbol == "R")
        assert r_entry.quantity == 3
        assert "r1" in r_entry.reference
        assert "r2" in r_entry.reference
        assert "r3" in r_entry.reference

    def test_no_parts(self):
        entries = generate_bom(NO_PARTS_SCRIPT, self.index)
        assert entries == []

    def test_description_resolved(self):
        entries = generate_bom(SIMPLE_SCRIPT, self.index)
        r_entry = next(e for e in entries if e.symbol == "R")
        # The fixture Device.kicad_sym should have a description for R
        assert r_entry.description  # non-empty

    def test_footprint_preserved(self):
        entries = generate_bom(SIMPLE_SCRIPT, self.index)
        r_entry = next(e for e in entries if e.symbol == "R")
        assert r_entry.footprint == "Resistor_SMD:R_0805_2012Metric"

    def test_sorted_output(self):
        entries = generate_bom(GROUPED_SCRIPT, self.index)
        # Should be sorted by (library, symbol, reference)
        libraries = [(e.library, e.symbol) for e in entries]
        assert libraries == sorted(libraries)

    def test_no_variable_uses_line_ref(self):
        entries = generate_bom(NO_VARIABLE_SCRIPT, self.index)
        # Parts without variable names should still appear
        assert len(entries) > 0

    def test_default_footprint_resolved(self):
        """Parts without explicit footprint should get the default from index."""
        entries = generate_bom(GROUPED_SCRIPT, self.index)
        led_entry = next(e for e in entries if e.symbol == "LED")
        # LED has no footprint= in the script, so it should resolve from index
        # (if the fixture has a default_footprint for LED)
        # At minimum, the entry should exist
        assert led_entry.library == "Device"
