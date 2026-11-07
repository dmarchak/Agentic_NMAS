"""The fixed conftest.py `mercury app new` writes in every app's folder (C2652; the SDN platform
design rev. 6, section 11a, item 2; modules/jobs/templates/): under pytest, a test's parameter
named for one of the app SDK's fixtures (`ctx`, `ryu`, `netbox`) gets what
`mercury_app.testing.fixture_for` gives it. An app's tests run in the container harness on
its network's controller Python, so this file is written for 3.5 and imports no Mercury module
but the app SDK, `mercury_app`. Mercury's runner ignores this file."""

import importlib
import os

import pytest

from mercury_app import testing

_HERE = os.path.dirname(os.path.abspath(__file__))


def _modules():
    return [importlib.import_module(name[:-3]) for name in sorted(os.listdir(_HERE))
            if name.endswith(".py") and not name.startswith("test_") and name != "conftest.py"]


def _make(name):
    @pytest.fixture(name=name)
    def _fixture():
        return testing.fixture_for(name, _modules())
    return _fixture


for _name in testing.FIXTURES:
    globals()["_fixture_" + _name] = _make(_name)
