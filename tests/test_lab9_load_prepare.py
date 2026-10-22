"""Lab 9's lab-load preparers (lab/lab9/t1_prepare.py, lab/lab9/hold_queue_prepare.py; docs/
LAB9_PLAN.md, T1 and lever c, C1547): each changes ONLY the one setting it names and keeps every
other byte, checked on a real committed intent (Lab 8's R6, lab/lab8/r6-intent.yml)."""

import importlib.util
import os

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_INTENT = os.path.join(ROOT, "lab", "lab8", "r6-intent.yml")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "lab", "lab9",
                                                                     f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def t1():
    return _load("t1_prepare")


@pytest.fixture(scope="module")
def hq():
    return _load("hold_queue_prepare")


@pytest.fixture(scope="module")
def real():
    with open(REAL_INTENT, encoding="utf-8") as fh:
        return fh.read()


def _subs(text):
    return {s["subscription"]: s["settings"] for s in yaml.safe_load(text)["telemetry"]}


def _changed_lines(old, new):
    a, b = old.splitlines(), new.splitlines()
    return [(x, y) for x, y in zip(a, b) if x != y], len(a) - len(b)


def test_variant_a_narrows_only_101s_filter(t1, real):
    new = t1.variant(real, "A")
    old_subs, new_subs = _subs(real), _subs(new)
    assert "filter xpath /process-cpu-ios-xe-oper:cpu-usage/cpu-utilization/one-minute" \
        in new_subs["101"]
    assert new_subs["102"] == old_subs["102"]
    assert [s for s in new_subs["101"] if not s.startswith("filter")] == \
        [s for s in old_subs["101"] if not s.startswith("filter")]
    changed, length = _changed_lines(real, new)
    assert length == 0 and len(changed) == 1


def test_variant_b_slows_only_101s_period(t1, real):
    new = t1.variant(real, "B")
    old_subs, new_subs = _subs(real), _subs(new)
    assert "update-policy periodic 6000" in new_subs["101"]
    assert "update-policy periodic 1000" in new_subs["102"]      # 102 keeps 10 s
    assert new_subs["102"] == old_subs["102"]
    changed, length = _changed_lines(real, new)
    assert length == 0 and len(changed) == 1


def test_t1_refuses_what_it_cannot_place(t1, real):
    with pytest.raises(ValueError):
        t1.variant("hostname: x\n", "A")
    with pytest.raises(ValueError):
        t1.variant(real, "C")


def test_hold_queue_added_to_the_named_interface_only(hq, real):
    new = hq.add_hold_queue(real, "GigabitEthernet2", "['256 out']")
    old_doc, new_doc = yaml.safe_load(real), yaml.safe_load(new)
    by = {i["name"]: i for i in new_doc["interfaces"]}
    assert by["GigabitEthernet2"]["hold_queue"] == ["256 out"]
    assert {k: v for k, v in by["GigabitEthernet2"].items() if k != "hold_queue"} == \
        {i["name"]: i for i in old_doc["interfaces"]}["GigabitEthernet2"]
    assert [i for i in new_doc["interfaces"] if i["name"] != "GigabitEthernet2"] == \
        [i for i in old_doc["interfaces"] if i["name"] != "GigabitEthernet2"]
    assert {k: v for k, v in new_doc.items() if k != "interfaces"} == \
        {k: v for k, v in old_doc.items() if k != "interfaces"}
    assert len(new.splitlines()) == len(real.splitlines()) + 1


def test_hold_queue_before_an_items_first_key_moves_the_dash(hq):
    # A planted item whose FIRST key sorts after hold_queue: the dash moves to the new key.
    text = ("interfaces:\n- ipv4: 192.0.2.1/30\n  name: Gi0\n  shutdown: false\n"
            "- description: x\n  name: Gi1\nlogging: []\n")
    new = hq.add_hold_queue(text, "Gi0", "['256 out']")
    assert new.startswith("interfaces:\n- hold_queue: ['256 out']\n  ipv4: 192.0.2.1/30\n")
    by = {i["name"]: i for i in yaml.safe_load(new)["interfaces"]}
    assert by["Gi0"] == {"hold_queue": ["256 out"], "ipv4": "192.0.2.1/30", "name": "Gi0",
                         "shutdown": False}
    assert by["Gi1"] == {"description": "x", "name": "Gi1"}


def test_hold_queue_refuses_an_absent_interface_or_a_second_key(hq, real):
    with pytest.raises(ValueError):
        hq.add_hold_queue(real, "GigabitEthernet9", "['256 out']")
    once = hq.add_hold_queue(real, "GigabitEthernet2", "['256 out']")
    with pytest.raises(ValueError):
        hq.add_hold_queue(once, "GigabitEthernet2", "['256 out']")
