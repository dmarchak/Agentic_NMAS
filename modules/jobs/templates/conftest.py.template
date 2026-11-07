"""The fixed conftest.py `mercury job new` writes in every job's folder (the SDN platform design
rev. 6, section 11a, item 2; modules/jobs/templates/; an app's is app_conftest.py.template): under pytest, a test's parameter named for one of the
SDK's fixtures (`ctx`, `ryu`, `netbox`) gets what Mercury's runner gives it, through the same
resolver, `modules.jobs.testing.fixture_for`. Mercury's runner ignores this file."""

import importlib
import os

import pytest

from modules.jobs import testing

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
    globals()[f"_fixture_{_name}"] = _make(_name)
