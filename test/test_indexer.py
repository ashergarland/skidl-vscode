"""Tests for indexer.py — KiCad library discovery and indexing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.indexer import build_index

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestIndexer:
    def test_build_from_fixtures(self):
        index = build_index(
            symbol_dir_override=str(FIXTURES),
            footprint_dir_override=str(FIXTURES),
        )
        assert "Device" in index.symbols
        assert "Switch" in index.symbols
        assert "Connector" in index.symbols

    def test_symbol_lib_names(self):
        index = build_index(symbol_dir_override=str(FIXTURES), footprint_dir_override=str(FIXTURES))
        assert "Device" in index.all_symbol_lib_names

    def test_symbol_lookup(self):
        index = build_index(symbol_dir_override=str(FIXTURES), footprint_dir_override=str(FIXTURES))
        assert index.symbol_exists("Device", "R")
        assert index.symbol_exists("Device", "LED")
        assert not index.symbol_exists("Device", "Nonexistent")

    def test_footprint_indexing(self):
        index = build_index(symbol_dir_override=str(FIXTURES), footprint_dir_override=str(FIXTURES))
        assert "Resistor_SMD" in index.footprints
        assert "LED_SMD" in index.footprints

    def test_footprint_lookup(self):
        index = build_index(symbol_dir_override=str(FIXTURES), footprint_dir_override=str(FIXTURES))
        assert index.footprint_exists("Resistor_SMD", "R_0805_2012Metric")
        assert not index.footprint_exists("Resistor_SMD", "Nonexistent")

    def test_get_symbol_info(self):
        index = build_index(symbol_dir_override=str(FIXTURES), footprint_dir_override=str(FIXTURES))
        r = index.get_symbol("Device", "R")
        assert r is not None
        assert r.name == "R"
        assert len(r.pins) == 2

    def test_nonexistent_dir(self):
        index = build_index(
            symbol_dir_override="C:\\nonexistent\\path",
            footprint_dir_override="C:\\nonexistent\\path",
        )
        assert len(index.symbols) == 0
        assert len(index.footprints) == 0
