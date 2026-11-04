"""scripts/nmas-skip-check and tests/skip_reasons.py (C2412, the operator's declared skip list,
2026-11-04): every skip in a run's JUnit files is one declared for its place, matched whole, or
the run fails naming the test and its reason. The skip messages are the real ones (CI run
#1418's browser3 JUnit, the board shots' marker, and C2436's and C2412's left-off reasons)."""
import ast
import importlib.machinery
import importlib.util
import os
import re
import subprocess
import sys

import pytest

from tests import skip_reasons

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-skip-check")

DENYLIST = ("/srv/ci/checkout/data/publication_denylist.txt is absent "
            "on this machine (it is local by design), so the denylist rule checked NOTHING here; "
            "the other rules ran")
LAB_HOSTS = ("/srv/ci/checkout/data/lab_hosts.json is absent on this "
             "machine; nothing to compare")
BOARD = "board shots run only when asked (NMAS_BOARD_SHOTS, NMAS_BOARDS_DIR)"
UID = ("root's files read as another uid here (the confined runner's user namespace); this runs "
       "under plain pytest, in CI and on the host")
FIREFOX = "no real browser here (Firefox could not start in this runner: Process unexpectedly closed)"
FIRST_DAY = "the month's first day has no earlier day to plant on"


def _junit(path, skips, xfail=()):
    cases = "".join(f'<testcase classname="tests.t" name="s{i}"><skipped type="pytest.skip" '
                    f'message="{m}">x</skipped></testcase>' for i, m in enumerate(skips))
    cases += "".join(f'<testcase classname="tests.t" name="x{i}"><skipped type="pytest.xfail" '
                     f'message="{m}"/></testcase>' for i, m in enumerate(xfail))
    path.write_text(f'<testsuites><testsuite name="pytest">{cases}'
                    f'<testcase classname="tests.t" name="ok"/></testsuite></testsuites>')
    return str(path)


def _run(*args):
    return subprocess.run([sys.executable, "-I", SCRIPT, *args], capture_output=True, text=True)


def test_the_declared_reasons_pass_where_they_are_declared(tmp_path):
    f = _junit(tmp_path / "j.xml", [BOARD, DENYLIST, LAB_HOSTS])
    r = _run("--where", "ci", f)
    assert r.returncode == 0, r.stdout
    assert "3 skip(s) in 1 file(s), 0 undeclared for ci" in r.stdout


@pytest.mark.parametrize("reason", [UID, FIREFOX, FIRST_DAY, "some reason nobody declared"])
def test_a_reason_the_operator_left_off_fails_naming_the_test_and_the_reason(tmp_path, reason):
    f = _junit(tmp_path / "j.xml", [reason])
    r = _run("--where", "ci", f)
    assert r.returncode == 1
    assert "REFUSED: tests.t::s0: skipped for " in r.stdout and reason[:40] in r.stdout


@pytest.mark.parametrize("reason", [DENYLIST, LAB_HOSTS])
def test_the_local_files_absent_are_allowed_in_ci_only_and_refused_in_the_gate(tmp_path, reason):
    f = _junit(tmp_path / "j.xml", [reason])
    assert _run("--where", "ci", f).returncode == 0
    r = _run("--where", "gate", f)
    assert r.returncode == 1 and "declared for ci, not for gate" in r.stdout


@pytest.mark.parametrize("where", ["ci", "gate", "local"])
def test_the_board_shots_are_allowed_everywhere(tmp_path, where):
    assert _run("--where", where, _junit(tmp_path / "j.xml", [BOARD])).returncode == 0


def test_a_reason_matches_whole_never_as_a_phrase_inside_another(tmp_path):
    f = _junit(tmp_path / "j.xml", [BOARD + "; and also Firefox could not start"])
    assert _run("--where", "ci", f).returncode == 1


def test_an_xfail_is_not_a_skip(tmp_path):
    assert _run("--where", "gate", _junit(tmp_path / "j.xml", [], xfail=[UID])).returncode == 0


def test_an_absent_or_unreadable_file_judges_nothing_and_refuses(tmp_path):
    (tmp_path / "bad.xml").write_text("not xml")
    for name in ("absent.xml", "bad.xml"):
        r = _run("--where", "ci", str(tmp_path / name))
        assert r.returncode == 2
        assert f"REFUSED: {tmp_path / name} is absent or not JUnit XML; nothing judged" in r.stdout


def test_every_entry_names_its_places_from_the_known_ones_and_compiles():
    assert len(skip_reasons.DECLARED) >= 3
    for name, pattern, places in skip_reasons.DECLARED:
        re.compile(pattern)
        assert name and places and set(places) <= set(skip_reasons.PLACES), name


def test_the_board_shots_entry_matches_the_markers_own_reason():
    """The entry matches the marker's real words, parsed from tests/test_board_shots.py's
    `pytestmark` (its skipif's `reason`), so an edit to either is seen."""
    tree = ast.parse(open(os.path.join(ROOT, "tests", "test_board_shots.py"),
                          encoding="utf-8").read())
    mark = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                and any(getattr(t, "id", "") == "pytestmark" for t in n.targets))
    reasons = [k.value.value for c in ast.walk(mark) if isinstance(c, ast.Call)
               for k in c.keywords if k.arg == "reason" and isinstance(k.value, ast.Constant)]
    assert reasons == [BOARD]
    assert any(re.fullmatch(p, reasons[0]) for _n, p, _w in skip_reasons.DECLARED)


def test_the_left_off_reasons_are_gone_from_the_suite_s_sources():
    """C2436 and C2455: the month's first day and the uid skip no longer skip anywhere."""
    for rel in ("tests/test_ai_background.py", "tests/test_update_button.py"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "pytest.skip(\"the month's first day" not in src
        assert 'pytest.skip("root\'s files read as another uid' not in src


def test_the_script_s_judge_reads_the_list_it_imports():
    loader = importlib.machinery.SourceFileLoader("nmas_skip_check", SCRIPT)
    spec = importlib.util.spec_from_loader("nmas_skip_check", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    counts, refusals = mod.judge([("t::a", BOARD), ("t::b", UID)], "gate")
    assert counts == {skip_reasons.DECLARED[0][0]: 1} and len(refusals) == 1
