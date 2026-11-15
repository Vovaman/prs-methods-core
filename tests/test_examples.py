"""Примеры из examples/ работают так, как описано в README."""
import asyncio
import importlib.util
from pathlib import Path

import yaml

from prs_methods import registry

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def load(name):
    spec = importlib.util.spec_from_file_location(name, EXAMPLES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sum_energy = load("sum_energy")
setpoint_write = load("setpoint_write")


def call(address, *args):
    return asyncio.run(registry[address](*args))


def tag(*points):
    return {"data": [{"tagId": "1", "data": list(points)}]}


def test_sum_energy():
    assert call("acme.energy.sum", 2, 3) == 5
    assert call("acme.energy.sum", tag([10, 1.5, None]), tag([10, 2, 0])) == 3.5
    assert call("acme.energy.sum", tag([10, 1.5, 100]), 2) == {"error": "плохое качество"}


def test_setpoint_write(capsys):
    assert call("acme.hvac.setpoint_write", 30, [[1_700_000_000_000_000, 21, None]]) is True
    assert "уставка 21" in capsys.readouterr().out
    assert call("acme.hvac.setpoint_write", 30, [[1_700_000_000_000_000, 45, None]]) == {
        "error": "уставка 45 вне диапазона 0..30",
    }


def test_examples_probe_arguments_succeed():
    loaded = yaml.safe_load(sum_energy.description_yaml())
    found = {
        item["address"]: item
        for folder in loaded.get("folders", [])
        for item in folder["methods"]
    }
    for address in ("acme.energy.sum", "acme.hvac.setpoint_write"):
        result = call(address, *found[address]["probe"])
        assert not (isinstance(result, dict) and "error" in result), result
