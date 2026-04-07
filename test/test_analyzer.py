"""Tests for analyzer.py — AST analysis of SKiDL Python files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.analyzer import analyze


SMOKE_TEST = '''\
from skidl import Net, Part, generate_netlist, set_default_tool, KICAD

set_default_tool(KICAD)

r1 = Part("Device", "R", value="330", footprint="Resistor_SMD:R_0805_2012Metric")
led1 = Part("Device", "LED", footprint="LED_SMD:LED_0805_2012Metric")

vcc = Net("VCC")
gnd = Net("GND")

vcc += r1[1]
r1[2] += led1["A"]
led1["K"] += gnd
'''

NON_SKIDL = '''\
import os
x = 42
'''


class TestSkidlDetection:
    def test_detects_skidl_import(self):
        result = analyze(SMOKE_TEST)
        assert result.is_skidl_file is True

    def test_rejects_non_skidl(self):
        result = analyze(NON_SKIDL)
        assert result.is_skidl_file is False


class TestPartExtraction:
    def test_finds_part_calls(self):
        result = analyze(SMOKE_TEST)
        assert len(result.part_calls) == 2

    def test_first_part_fields(self):
        result = analyze(SMOKE_TEST)
        r1 = result.part_calls[0]
        assert r1.variable == "r1"
        assert r1.library == "Device"
        assert r1.symbol == "R"
        assert r1.footprint == "Resistor_SMD:R_0805_2012Metric"

    def test_second_part_fields(self):
        result = analyze(SMOKE_TEST)
        led = result.part_calls[1]
        assert led.variable == "led1"
        assert led.library == "Device"
        assert led.symbol == "LED"

    def test_library_span(self):
        result = analyze(SMOKE_TEST)
        r1 = result.part_calls[0]
        assert r1.library_span is not None
        # "Device" is on the line: r1 = Part("Device", ...
        assert r1.library_span[0] == 4  # 0-indexed line

    def test_var_to_part_map(self):
        result = analyze(SMOKE_TEST)
        assert "r1" in result.var_to_part
        assert "led1" in result.var_to_part


class TestPinAccess:
    def test_finds_pin_accesses(self):
        result = analyze(SMOKE_TEST)
        assert len(result.pin_accesses) >= 3

    def test_numeric_pin(self):
        result = analyze(SMOKE_TEST)
        # r1[1]
        numeric = [pa for pa in result.pin_accesses if pa.pin == "1"]
        assert len(numeric) >= 1
        assert numeric[0].variable == "r1"

    def test_string_pin(self):
        result = analyze(SMOKE_TEST)
        # led1["A"]
        named = [pa for pa in result.pin_accesses if pa.pin == "A"]
        assert len(named) >= 1
        assert named[0].variable == "led1"
