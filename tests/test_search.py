"""Tests for core/search.py -- symbol and footprint search."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.indexer import build_index
from core.search import (
    FootprintSearchResult,
    SymbolSearchResult,
    search_footprints,
    search_symbols,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _build_fixture_index():
    return build_index(
        symbol_dir_override=str(FIXTURES),
        footprint_dir_override=str(FIXTURES),
    )


class TestSearchSymbols:
    def setup_method(self):
        self.index = _build_fixture_index()

    def test_exact_match(self):
        results = search_symbols("R", self.index)
        assert len(results) > 0
        assert isinstance(results[0], SymbolSearchResult)
        assert results[0].name == "R"
        assert results[0].library == "Device"

    def test_substring_match(self):
        results = search_symbols("LED", self.index)
        assert any(r.name == "LED" for r in results)

    def test_fuzzy_match(self):
        results = search_symbols("resistor", self.index, limit=20)
        # Should match R via description
        assert len(results) > 0

    def test_no_match(self):
        results = search_symbols("XYZNONEXISTENT", self.index)
        assert results == []

    def test_limit(self):
        results = search_symbols("R", self.index, limit=2)
        assert len(results) <= 2

    def test_result_fields(self):
        results = search_symbols("R", self.index)
        r = results[0]
        assert r.library
        assert r.name


class TestSearchFootprints:
    def setup_method(self):
        self.index = _build_fixture_index()

    def test_substring_match(self):
        results = search_footprints("0805", self.index)
        assert len(results) > 0
        assert isinstance(results[0], FootprintSearchResult)
        assert "0805" in results[0].name

    def test_no_match(self):
        results = search_footprints("XYZNONEXISTENT", self.index)
        assert results == []

    def test_limit(self):
        results = search_footprints("R_", self.index, limit=1)
        assert len(results) <= 1

    def test_result_fields(self):
        results = search_footprints("0805", self.index)
        r = results[0]
        assert r.library
        assert r.name
        assert isinstance(r.pad_count, int)
