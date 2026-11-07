"""The one declaration of data folders (C2633; tests/data_folders.py) is read the same way by
everything that reads it: the operator's words, 2026-11-06, "their path is declared once and
pytest collection, red-green and the test-weakening check all read that one declaration".

Three scripts parse it (each its own copy of the parser, since two of them are protected guards
and may not depend on an unprotected module): scripts/nmas-red-green, scripts/nmas-test-
weakening-check and scripts/nmas-fast-checks. Held here: on the real file and on planted ones
(a well-formed tuple, an entry outside tests/fixtures/, a `..`, a non-string, a missing "/",
the root itself, two assignments, none), the three agree on the folders accepted; the two
guards agree on what they refuse; and tests/conftest.py's `collect_ignore` is the real
declaration's folders.
"""
import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"),
                                                  str(ROOT / "scripts" / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def readers():
    return _load("nmas-red-green"), _load("nmas-test-weakening-check"), _load("nmas-fast-checks")


PLANTED = {
    "well formed": ('DATA_FOLDERS = ("tests/fixtures/jobs/", "tests/fixtures/apps/")\n',
                    ("tests/fixtures/jobs/", "tests/fixtures/apps/"), 0),
    "outside fixtures": ('DATA_FOLDERS = ("tests/fixtures/jobs/", "tests/")\n',
                         ("tests/fixtures/jobs/",), 1),
    "a dot-dot": ('DATA_FOLDERS = ("tests/fixtures/../x/",)\n', (), 1),
    "not a string": ('DATA_FOLDERS = (1, "tests/fixtures/jobs/")\n', ("tests/fixtures/jobs/",), 1),
    "no slash": ('DATA_FOLDERS = ("tests/fixtures/jobs",)\n', (), 1),
    "the root itself": ('DATA_FOLDERS = ("tests/fixtures/",)\n', (), 1),
    "twice": ('DATA_FOLDERS = ("tests/fixtures/a/",)\nDATA_FOLDERS = ("tests/fixtures/b/",)\n',
              (), 1),
    "none": ("X = 1\n", (), 1),
}


@pytest.mark.parametrize("case", sorted(PLANTED))
def test_the_three_readers_agree_on_a_planted_declaration(readers, tmp_path, case):
    text, folders, problems = PLANTED[case]
    rg, wk, fc = readers
    got_rg, why_rg = rg.data_folders(text)
    got_wk, why_wk = wk.data_folders(text)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "data_folders.py").write_text(text)
    assert got_rg == got_wk == fc.data_folders(str(tmp_path)) == folders
    assert why_rg == why_wk and len(why_rg) == problems, why_rg


def test_no_file_declares_nothing_and_refuses_nothing(readers, tmp_path):
    rg, wk, fc = readers
    assert rg.data_folders(None) == wk.data_folders(None) == ((), [])
    assert fc.data_folders(str(tmp_path)) == ()


def test_the_real_declaration_is_what_conftest_and_the_readers_read(readers):
    from tests import conftest
    from tests.data_folders import DATA_FOLDERS
    rg, wk, fc = readers
    text = (ROOT / "tests" / "data_folders.py").read_text()
    assert rg.data_folders(text) == wk.data_folders(text) == (DATA_FOLDERS, [])
    assert fc.data_folders(str(ROOT)) == DATA_FOLDERS
    assert DATA_FOLDERS, "a floor: at least the job gate's fixture jobs are declared"
    assert conftest.collect_ignore == [f.removeprefix("tests/").rstrip("/") for f in DATA_FOLDERS]
