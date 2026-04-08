"""Tests for kicad_parser.py — S-expression parsing of .kicad_sym files."""

import sys
from pathlib import Path

# Ensure the server package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.kicad_parser import parse_kicad_sym, parse_kicad_mod, parse_sexpr

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestSExprParser:
    def test_parse_atom(self):
        result = parse_sexpr("hello")
        assert result == "hello"

    def test_parse_simple_list(self):
        result = parse_sexpr("(a b c)")
        assert result == ["a", "b", "c"]

    def test_parse_nested(self):
        result = parse_sexpr("(a (b c) d)")
        assert result == ["a", ["b", "c"], "d"]

    def test_parse_quoted_string(self):
        result = parse_sexpr('(property "Reference" "R")')
        assert result == ["property", "Reference", "R"]


class TestSymbolParser:
    def test_parse_device_lib(self):
        symbols = parse_kicad_sym(FIXTURES / "Device.kicad_sym")
        names = {s.name for s in symbols}
        assert "R" in names
        assert "C" in names
        assert "LED" in names

    def test_resistor_has_pins(self):
        symbols = parse_kicad_sym(FIXTURES / "Device.kicad_sym")
        r = next(s for s in symbols if s.name == "R")
        pin_numbers = {p.number for p in r.pins}
        assert "1" in pin_numbers
        assert "2" in pin_numbers

    def test_led_has_named_pins(self):
        symbols = parse_kicad_sym(FIXTURES / "Device.kicad_sym")
        led = next(s for s in symbols if s.name == "LED")
        pin_names = {p.name for p in led.pins}
        assert "A" in pin_names
        assert "K" in pin_names

    def test_resistor_description(self):
        symbols = parse_kicad_sym(FIXTURES / "Device.kicad_sym")
        r = next(s for s in symbols if s.name == "R")
        assert "Resistor" in r.description

    def test_switch_lib(self):
        symbols = parse_kicad_sym(FIXTURES / "Switch.kicad_sym")
        names = {s.name for s in symbols}
        assert "SW_Push" in names

    def test_connector_lib(self):
        symbols = parse_kicad_sym(FIXTURES / "Connector.kicad_sym")
        names = {s.name for s in symbols}
        assert "Conn_01x02_Male" in names


class TestFootprintParser:
    def test_parse_resistor_footprint(self):
        fp = parse_kicad_mod(FIXTURES / "Resistor_SMD.pretty" / "R_0805_2012Metric.kicad_mod")
        assert fp is not None
        assert fp.name == "R_0805_2012Metric"
        assert fp.pad_count == 2

    def test_parse_led_footprint(self):
        fp = parse_kicad_mod(FIXTURES / "LED_SMD.pretty" / "LED_0805_2012Metric.kicad_mod")
        assert fp is not None
        assert fp.name == "LED_0805_2012Metric"
        assert fp.pad_count == 2
