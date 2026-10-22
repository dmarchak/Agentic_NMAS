"""Lab 9's reseed preparation (lab/lab9/reseed_prepare.py; docs/LAB9_PLAN.md section 7, R1):
the prepared intent replaces ONLY the top-level `lines:` block and keeps every `no_shutdown:
true`, checked on a real committed intent (Lab 8's R6, lab/lab8/r6-intent.yml)."""

import importlib.util
import os

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "lab", "lab9", "reseed_prepare.py")
REAL_INTENT = os.path.join(ROOT, "lab", "lab8", "r6-intent.yml")


@pytest.fixture(scope="module")
def prep():
    spec = importlib.util.spec_from_file_location("reseed_prepare", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def real():
    with open(REAL_INTENT, encoding="utf-8") as fh:
        return fh.read()


def test_only_the_lines_block_changes(prep, real):
    new = prep.replace_lines_block(real)
    old_doc, new_doc = yaml.safe_load(real), yaml.safe_load(new)
    assert set(old_doc) == set(new_doc)
    assert {k: v for k, v in old_doc.items() if k != "lines"} == \
        {k: v for k, v in new_doc.items() if k != "lines"}
    assert new_doc["lines"] == yaml.safe_load(prep.NEW_LINES)["lines"]
    # Byte for byte outside the block: what precedes `lines:` and what follows its last item.
    head = real[:real.index("\nlines:\n") + 1]
    assert new.startswith(head + prep.NEW_LINES)
    tail = real[real.index("\nlogging:\n") + 1:]
    assert new.endswith(tail)


def test_the_prepared_lines_split_vty_and_bound_the_console(prep):
    lines = {b["spec"]: b["settings"] for b in yaml.safe_load(prep.NEW_LINES)["lines"]}
    assert set(lines) == {"con 0", "aux 0", "vty 0", "vty 1", "vty 2 4"}
    assert "exec-timeout 15 0" in lines["con 0"]
    assert not any("exec-timeout 0 0" in s for v in lines.values() for s in v)
    assert "length 0" in lines["vty 1"]


def test_every_no_shutdown_is_kept(prep, real):
    before = prep.no_shutdowns(real)
    assert "GigabitEthernet3" in before          # the real intent declares one: a floor
    assert prep.no_shutdowns(prep.replace_lines_block(real)) == before


def test_a_lines_block_last_in_the_document(prep):
    text = "hostname: x\nlines:\n- settings: []\n  spec: con 0\n"
    new = prep.replace_lines_block(text)
    assert new == "hostname: x\n" + prep.NEW_LINES


def test_a_document_without_lines_is_refused(prep):
    with pytest.raises(ValueError):
        prep.replace_lines_block("hostname: x\ninterfaces: []\n")
