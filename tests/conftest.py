"""Test harness.

The interesting logic here -- brand classification, serial filtering, request
shaping, report redaction -- is deliberately free of Home Assistant imports, so
it can be tested with plain pytest and no HA install. These modules are loaded
directly rather than through the package, which would drag in `homeassistant`
via __init__.py.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pytest

# Loading the component modules here would otherwise litter __pycache__ inside
# the shipped directory -- which test_no_bytecode_is_shipped then rightly fails
# on. Suppress it before any import happens.
sys.dont_write_bytecode = True

COMPONENT = pathlib.Path(__file__).parent.parent / "custom_components" / "smartshade"


def _load(name: str):
    """Import one component module standalone, stubbing aiohttp."""
    if "aiohttp" not in sys.modules:
        stub = types.ModuleType("aiohttp")
        stub.ClientSession = object
        sys.modules["aiohttp"] = stub
    pkg = "smartshade_under_test"
    if pkg not in sys.modules:
        shim = types.ModuleType(pkg)
        shim.__path__ = [str(COMPONENT)]
        sys.modules[pkg] = shim
    full = f"{pkg}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, COMPONENT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def const():
    return _load("const")


@pytest.fixture(scope="session")
def report(const):
    return _load("report")


@pytest.fixture(scope="session")
def api(const):
    return _load("api")
