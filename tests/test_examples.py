"""Примеры из examples/ работают так, как описано в README."""
import asyncio
import importlib.util
import logging
from pathlib import Path

import pytest
import yaml

from prs_methods import description_yaml, registry

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
NAMES = (
    "compute_sum",
    "compute_total",
    "read_tariff",
    "read_average",
    "write_setpoint",
    "read_audit",
    "write_alarm",
)


def load(name):
    spec = importlib.util.spec_from_file_location(f"example_{name}", EXAMPLES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


for _name in NAMES:
    load(_name)

T = 1_700_000_000_000_000


def call(address, *args):
    return asyncio.run(registry[address](*args))


def tag(*points, tag_id="1"):
    return {"data": [{"tagId": tag_id, "data": list(points)}]}


def catalog():
    loaded = yaml.safe_load(description_yaml())
    return {
        item["address"]: item
        for folder in loaded.get("folders", [])
        for item in folder["methods"]
    }


def test_compute_sum():
    assert call("acme.energy.sum", 2, 3) == 5
    assert call("acme.energy.sum", tag([T, 1.5, None]), tag([T, 2, 0])) == 3.5
    assert call("acme.energy.sum", tag([T, 1.5, 100]), 2) == {"error": "плохое качество"}


def test_compute_total_accepts_any_number_of_arguments():
    assert call("acme.energy.total", 1) == 1
    assert call("acme.energy.total", tag([T, 1, None]), tag([T, 2, None]), 3, 4) == 10
    assert "error" in call("acme.energy.total")


def test_read_tariff():
    assert call("acme.energy.tariff", {"finish": T}, 6.5, 2.5) == 2.5
    assert call("acme.energy.tariff", {"finish": "2023-11-14T12:00:00+03:00"}, 6.5, 2.5) == 6.5


def test_read_average_skips_bad_sensors():
    several = {"data": [
        {"tagId": "a", "data": [[T, 20, None]]},
        {"tagId": "b", "data": [[T, 99, 100]]},
    ]}
    assert call("acme.climate.average", several, tag([T, 24, 0])) == 22
    assert call("acme.climate.average", tag([T, 1, 102])) == {"error": "нет ни одного годного значения"}


def test_write_setpoint(capsys):
    assert call("acme.hvac.setpoint_write", 30, [[T, 21, None]]) is True
    assert "уставка 21" in capsys.readouterr().out
    assert call("acme.hvac.setpoint_write", 30, [[T, 45, None]]) == {
        "error": "уставка 45 вне диапазона 0..30",
    }


def test_read_audit(caplog):
    with caplog.at_level(logging.WARNING, logger="acme.audit"):
        assert call("acme.audit.read", {"tagId": ["7"], "finish": T}) is True
    assert "['7']" in caplog.text


def test_write_alarm(capsys):
    assert call("acme.alarm.pressure", 6, [[T, 5, None], [T, 6.5, None], [T, 9, 103]]) is True
    out = capsys.readouterr().out
    assert "давление 6.5" in out and "давление 9" not in out


def test_variadic_examples_are_marked_in_the_description():
    found = catalog()
    for address in ("acme.energy.total", "acme.climate.average"):
        assert found[address]["variadic"] is True
        assert "parameters" not in found[address]
    assert "variadic" not in found["acme.energy.sum"]


@pytest.mark.parametrize("address", [
    "acme.energy.sum",
    "acme.energy.total",
    "acme.energy.tariff",
    "acme.climate.average",
    "acme.hvac.setpoint_write",
    "acme.audit.read",
    "acme.alarm.pressure",
])
def test_probe_arguments_succeed(address):
    result = call(address, *catalog()[address]["probe"])
    assert not (isinstance(result, dict) and "error" in result), result
