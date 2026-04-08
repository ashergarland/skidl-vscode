"""Extended tests for indexer.py — cache round-trip, force rebuild."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.indexer import LibraryIndex, build_index

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fresh_index():
    return build_index(
        symbol_dir_override=str(FIXTURES),
        footprint_dir_override=str(FIXTURES),
        force=True,
    )


class TestCacheRoundTrip:
    def test_to_dict_and_from_dict(self):
        idx = _fresh_index()
        data = idx.to_dict()
        restored = LibraryIndex.from_dict(data)

        assert set(restored.symbols.keys()) == set(idx.symbols.keys())
        assert set(restored.footprints.keys()) == set(idx.footprints.keys())

        # Spot-check a symbol
        r_orig = idx.get_symbol("Device", "R")
        r_rest = restored.get_symbol("Device", "R")
        assert r_orig is not None and r_rest is not None
        assert r_orig.name == r_rest.name
        assert len(r_orig.pins) == len(r_rest.pins)

    def test_to_dict_is_json_serializable(self):
        idx = _fresh_index()
        data = idx.to_dict()
        # Should not raise
        serialized = json.dumps(data)
        assert len(serialized) > 0

    def test_from_dict_preserves_pin_info(self):
        idx = _fresh_index()
        data = idx.to_dict()
        restored = LibraryIndex.from_dict(data)
        led = restored.get_symbol("Device", "LED")
        assert led is not None
        pin_names = {p.name for p in led.pins}
        assert "A" in pin_names
        assert "K" in pin_names

    def test_from_dict_preserves_footprint_info(self):
        idx = _fresh_index()
        data = idx.to_dict()
        restored = LibraryIndex.from_dict(data)
        assert restored.footprint_exists("Resistor_SMD", "R_0805_2012Metric")
        fp = restored.get_footprint("Resistor_SMD", "R_0805_2012Metric")
        assert fp is not None
        assert fp.name == "R_0805_2012Metric"


class TestForceRebuild:
    def test_force_skips_cache(self):
        # Build once to populate cache
        idx1 = build_index(
            symbol_dir_override=str(FIXTURES),
            footprint_dir_override=str(FIXTURES),
        )
        # Force rebuild should still work
        idx2 = build_index(
            symbol_dir_override=str(FIXTURES),
            footprint_dir_override=str(FIXTURES),
            force=True,
        )
        assert set(idx2.symbols.keys()) == set(idx1.symbols.keys())


class TestLookupMethods:
    def test_symbol_lib_exists(self):
        idx = _fresh_index()
        assert idx.symbol_lib_exists("Device") is True
        assert idx.symbol_lib_exists("NonexistentLib") is False

    def test_footprint_lib_exists(self):
        idx = _fresh_index()
        assert idx.footprint_lib_exists("Resistor_SMD") is True
        assert idx.footprint_lib_exists("NonexistentLib") is False

    def test_get_symbols_in_lib(self):
        idx = _fresh_index()
        syms = idx.get_symbols_in_lib("Device")
        assert "R" in syms
        assert "LED" in syms

    def test_get_footprints_in_lib(self):
        idx = _fresh_index()
        fps = idx.get_footprints_in_lib("Resistor_SMD")
        assert "R_0805_2012Metric" in fps

    def test_get_symbol_nonexistent(self):
        idx = _fresh_index()
        assert idx.get_symbol("Device", "FAKE") is None
        assert idx.get_symbol("FAKELIB", "R") is None

    def test_get_footprint_nonexistent(self):
        idx = _fresh_index()
        assert idx.get_footprint("Resistor_SMD", "FAKE") is None
        assert idx.get_footprint("FAKELIB", "R_0805_2012Metric") is None
