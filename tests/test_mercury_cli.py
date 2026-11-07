"""`scripts/mercury` (the SDN platform design rev. 6, section 11a, items 3 and 4; T24): `job|app
check` print the one verdict and exit by it, `job|app new` write a folder from a spec card or
`--blank`, and write nothing else (a job or app never lives in a network's configuration
repository: the SDN design revision 7). AUTHORING.md, the guide `new` writes, is held to the gate's own
tables and to the fixtures it quotes.

No address is parsed anywhere here (the CLI takes paths and a card's file),
so there is no IPv4 or IPv6 case to give; the fixtures' domains are documentation names."""

import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from modules.apps import gate as app_gate
from modules.apps.manifest import load_manifest
from modules.jobs import gate as G
from modules.jobs import scaffold as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "scripts", "mercury")
JOBS = os.path.join(ROOT, "tests", "fixtures", "jobs")
APPS = os.path.join(ROOT, "tests", "fixtures", "apps")
FIXTURE_JOBS = ("switch-links", "arp-guard", "tautology")
APP = "dns_overrides"


def _load_cli():
    loader = importlib.machinery.SourceFileLoader("mercury_cli", CLI)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("mercury_cli",
                                                                             loader))
    loader.exec_module(module)
    return module


CLI_MODULE = _load_cli()


def run(capsys, *argv):
    """`mercury <argv>` in this process: (exit code, stdout, stderr)."""
    code = CLI_MODULE.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def copy(tmp_path, source: str, name: str = None) -> str:
    target = tmp_path / (name or os.path.basename(source))
    shutil.copytree(source, target)
    return str(target)


def without_timings(verdict: dict) -> dict:
    verdict = json.loads(json.dumps(verdict))
    verdict.pop("timings")
    return verdict


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def rewrite(path: str, old: str, new: str) -> None:
    text = read(path)
    assert old in text, f"{old!r} is not in {path}"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace(old, new, 1))


# ── check: the one verdict, printed and exited by ────────────────────────────────────────────

@pytest.mark.parametrize("name, code", [("switch-links", 0), ("arp-guard", 1),
                                        ("tautology", 1)])
def test_job_check_exits_by_the_verdict_on_each_fixture(tmp_path, capsys, name, code):
    folder = copy(tmp_path, os.path.join(JOBS, name))
    got, out, _err = run(capsys, "job", "check", folder)
    assert got == code
    verdict = G.check(folder)
    assert verdict.passed is (code == 0)
    for c in verdict.checks:
        assert re.search(rf"^  {'passed' if c.passed else 'FAILED'}  {c.name} +"
                         rf"{re.escape(c.summary)}$", out, re.M), (c.name, out)
    head = out.splitlines()[0]
    assert head.startswith(f"mercury job check {folder}: ")
    assert ("passed, every check" in head) is (code == 0)


def test_a_failed_check_prints_its_details_and_the_action_that_clears_it(tmp_path, capsys):
    folder = copy(tmp_path, os.path.join(JOBS, "tautology"))
    _code, out, _err = run(capsys, "job", "check", folder)
    survivors = G.check(folder).check("survivors")
    assert out.splitlines()[0].endswith("NOT PASSED: 1 of 7 checks did not pass (survivors)")
    for detail in survivors.details:
        assert f"  - {detail}\n" in out
    assert f"To clear it: {G.ACTIONS['survivors']}" in out
    assert out.count("To clear it:") == 1, "a passed check names no action"


@pytest.mark.parametrize("name", FIXTURE_JOBS)
def test_t24_the_cli_json_is_the_gates_verdict_whole(tmp_path, capsys, name):
    """One home: the CLI's JSON is `gate.check(folder).as_dict()`, check by check, the
    timings aside (they are measured, and differ run to run)."""
    folder = copy(tmp_path, os.path.join(JOBS, name))
    _code, out, _err = run(capsys, "job", "check", folder, "--json")
    printed = json.loads(out)
    assert set(printed["timings"]) >= {"run_seconds", "run_bound", "tests"}
    assert without_timings(printed) == without_timings(G.check(folder).as_dict())


def test_t24_the_app_cli_json_is_the_app_gates_verdict_whole(tmp_path, capsys):
    folder = copy(tmp_path, os.path.join(APPS, APP))
    code, out, _err = run(capsys, "app", "check", folder, "--json")
    assert code == 1
    assert without_timings(json.loads(out)) == without_timings(app_gate.check(folder).as_dict())


def test_check_refuses_what_is_not_a_folder(tmp_path, capsys):
    code, out, err = run(capsys, "job", "check", str(tmp_path / "absent"))
    assert code == 2 and out == ""
    assert err == f"mercury job check: {tmp_path / 'absent'} is not a folder\n"


def test_the_script_starts_and_answers_as_a_program(tmp_path):
    """Run the way the guide says, a program of its own: the verdict's JSON and its exit."""
    folder = copy(tmp_path, os.path.join(JOBS, "tautology"))
    done = subprocess.run([sys.executable, CLI, "job", "check", folder, "--json"],
                          capture_output=True, text=True, cwd=str(tmp_path), timeout=120)
    assert done.returncode == 1, done.stderr
    assert json.loads(done.stdout)["passed"] is False


# ── app check: the manifest, the job gate's checks, and the reconcile test ───────────────────

def test_app_check_runs_the_manifest_and_every_job_check_and_waits_for_the_harness(tmp_path,
                                                                                  capsys,
                                                                                  monkeypatch):
    """C2635: an app's tests run in the container harness, never in the job sandbox, so the
    checks that run its code say so and fail; the ones that read its source pass, against the
    network's measured controller Python."""
    from modules import config
    from modules.sdn import controller_runtime

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "data" / "lists"))
    controller_runtime.record_python("lab9", answer="Python 3.5.2",
                                     read_command="/opt/app-venv/bin/python --version",
                                     host="ctl-1", at="2026-11-05T18:00:00Z", by="read-run-1")
    folder = copy(tmp_path, os.path.join(APPS, APP))
    code, out, _err = run(capsys, "app", "check", folder, "--network", "lab9")
    verdict = app_gate.check(folder, python=controller_runtime.target("lab9"))
    assert code == 1 and not verdict.passed
    assert [c.name for c in verdict.checks] == list(app_gate.APP_CHECKS)
    assert [c.name for c in verdict.checks if not c.passed] == [
        "tests", "mutation", "survivors", "reconcile"]
    for name in ("tests", "mutation", "survivors", "reconcile"):
        assert verdict.check(name).summary == ("not run: app tests run in the container "
                                               "harness, which lands with P2a")
        assert verdict.check(name).action == app_gate.HARNESS_ACTION
    assert out.splitlines()[0].endswith("NOT PASSED: 4 of 9 checks did not pass (tests, "
                                        "mutation, survivors, reconcile)")
    assert verdict.check("static").summary == "1 modules and 1 test files allowed on Python " \
                                              "3.5, 0 egress calls"
    assert verdict.check("asserts").summary == "every one of 5 tests asserts"


def test_an_app_whose_manifest_names_another_app_is_refused_by_name(tmp_path):
    folder = copy(tmp_path, os.path.join(APPS, APP))
    rewrite(os.path.join(folder, "manifest.yml"), "name: dns_overrides", "name: dns_other")
    manifest = app_gate.check(folder).check("manifest")
    assert not manifest.passed
    assert manifest.details == ("manifest.yml's name 'dns_other' is not spec.yml's "
                                "'dns_overrides': one app, one name",)


@pytest.mark.parametrize("listed, words", [
    ("lib/test_app.py", "'lib/test_app.py' is not at the folder's root or in its tests/ "
                        "subfolder, where tests sit"),
    ("tests/unit/test_app.py", "'tests/unit/test_app.py' is not at the folder's root or in "
                               "its tests/ subfolder, where tests sit"),
    ("app_test.py", "'app_test.py' is not a test_*.py file"),
    ("test_missing.py", "'test_missing.py' is not in the folder"),
    ("tests/test_missing.py", "'tests/test_missing.py' is not in the folder"),
])
def test_a_manifest_test_the_gate_never_runs_is_refused(tmp_path, listed, words):
    folder = copy(tmp_path, os.path.join(APPS, APP))
    rewrite(os.path.join(folder, "manifest.yml"), "  - test_app.py", f"  - {listed}")
    manifest = app_gate.check(folder).check("manifest")
    assert not manifest.passed and manifest.details == (f"tests: {words}",)


def test_an_apps_tests_in_a_tests_subfolder_are_listed_and_read(tmp_path):
    """C2636: the conventional tests/ subfolder is accepted, in the manifest and by the gate's
    static, examples and asserts checks."""
    folder = copy(tmp_path, os.path.join(APPS, APP))
    os.mkdir(os.path.join(folder, "tests"))
    os.rename(os.path.join(folder, "test_app.py"), os.path.join(folder, "tests", "test_app.py"))
    rewrite(os.path.join(folder, "manifest.yml"), "  - test_app.py", "  - tests/test_app.py")
    verdict = app_gate.check(folder, python=(3, 5))
    assert verdict.check("manifest").passed, verdict.check("manifest").details
    assert verdict.check("static").passed and verdict.check("asserts").passed
    examples = verdict.check("examples")
    assert examples.passed and all("tests/test_app.py::test_a_" in d for d in examples.details)


def test_a_job_card_in_an_app_folder_is_refused(tmp_path):
    folder = copy(tmp_path, os.path.join(APPS, APP))
    path = os.path.join(folder, "spec.yml")
    rewrite(path, "kind: app", "kind: job")
    rewrite(path, "name: dns_overrides", "name: dns-overrides")
    details = app_gate.check(folder).check("manifest").details
    assert "spec.yml's kind is 'job', and an app's card says kind: app" in details


def test_a_refused_manifest_names_each_field(tmp_path):
    folder = copy(tmp_path, os.path.join(APPS, APP))
    os.remove(os.path.join(folder, "manifest.yml"))
    manifest = app_gate.check(folder).check("manifest")
    assert not manifest.passed and manifest.action == app_gate.ACTIONS["manifest"]
    assert "is not a file: an app's folder holds its manifest.yml" in manifest.details[0]


# ── new: a folder from a card ────────────────────────────────────────────────────────────────

def stub_tests_of(folder: str, file: str = "test_job.py") -> dict:
    """`{test name: its @covers names}`, read from the written test file."""
    import ast

    out = {}
    for node in ast.parse(read(os.path.join(folder, file))).body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
            out[node.name] = [a.value for d in node.decorator_list for a in d.args]
    return out


@pytest.mark.parametrize("name", FIXTURE_JOBS)
def test_new_from_each_fixtures_card_fails_tests_naming_each_example(tmp_path, capsys, name):
    card = os.path.join(JOBS, name, "spec.yml")
    folder = str(tmp_path / name)
    code, out, _err = run(capsys, "job", "new", folder, "--from", card)
    assert code == 0, out
    assert sorted(os.listdir(folder)) == sorted(["spec.yml", "job.py", "test_job.py",
                                                 "conftest.py", "AUTHORING.md"])
    assert read(os.path.join(folder, "spec.yml")) == read(card)
    verdict = G.check(folder)
    from modules.jobs.spec import load_spec
    examples = load_spec(folder).example_names()
    assert verdict.check("spec").passed and verdict.check("static").passed
    assert verdict.check("examples").passed and verdict.check("asserts").passed
    tests = verdict.check("tests")
    assert not tests.passed
    assert tests.summary == f"{len(examples)} of {len(examples)} tests did not pass"
    for example in examples:
        assert any(f"not written yet: the example {example!r}" in d for d in tests.details), \
            (example, tests.details)
    assert sorted(c for covers in stub_tests_of(folder).values() for c in covers) == \
        sorted(examples)
    assert verdict.check("mutation").summary.startswith("not run: ")


def test_a_new_folder_passes_once_its_code_and_tests_are_written(tmp_path, capsys):
    """The stub's tests are the fixture's by name and by example; with the fixture's code and
    test bodies written in, the folder passes every check."""
    folder = str(tmp_path / "switch-links")
    run(capsys, "job", "new", folder, "--from", os.path.join(JOBS, "switch-links", "spec.yml"))
    stubs = stub_tests_of(folder)
    written = {n: c for n, c in stub_tests_of(os.path.join(JOBS, "switch-links")).items() if c}
    assert stubs == written
    assert not G.check(folder).passed
    for file in ("job.py", "test_job.py"):
        with open(os.path.join(folder, file), "w", encoding="utf-8") as fh:
            fh.write(read(os.path.join(JOBS, "switch-links", file)))
    code, out, _err = run(capsys, "job", "check", folder)
    assert code == 0, out


def test_the_stub_declares_the_cards_contract(tmp_path, capsys):
    folder = str(tmp_path / "arp-guard")
    run(capsys, "job", "new", folder, "--from", os.path.join(JOBS, "arp-guard", "spec.yml"))
    text = read(os.path.join(folder, "job.py"))
    assert 'meta = JobMeta(name="arp-guard", version="0.1.0",' in text
    assert 'permission="write",' in text and "max_changes=1," in text
    assert 'scope=Scope(object_types=["dcim.device"], roles=["openflow-switch"]))' in text
    assert "        priority: int\n" in text
    assert "        limit: int  # at most this many switches (8 if not given)\n" in text


def test_a_card_with_an_open_question_writes_nothing_and_names_it(tmp_path, capsys):
    card = tmp_path / "spec.yml"
    card.write_text(read(os.path.join(JOBS, "switch-links", "spec.yml")).replace(
        "permission: read", "permission: {ask: \"read or write?\"}"), encoding="utf-8")
    folder = tmp_path / "out"
    code, out, err = run(capsys, "job", "new", str(folder), "--from", str(card))
    assert code == 2 and out == "" and not folder.exists()
    assert "permission: an open question, 'read or write?'" in err


def test_a_folder_that_exists_and_is_not_empty_is_refused_by_name(tmp_path, capsys):
    folder = tmp_path / "taken"
    folder.mkdir()
    (folder / "notes.txt").write_text("mine\n", encoding="utf-8")
    code, _out, err = run(capsys, "job", "new", str(folder), "--blank")
    assert code == 2
    assert err == (f"mercury job new: {folder} refused:\n  - exists and is not empty (1 "
                   "entries: notes.txt); a new job's folder is new or empty\n")
    assert os.listdir(folder) == ["notes.txt"]


def test_an_empty_folder_is_written_into(tmp_path, capsys):
    folder = tmp_path / "empty-job"
    folder.mkdir()
    code, _out, _err = run(capsys, "job", "new", str(folder), "--blank")
    assert code == 0 and "spec.yml" in os.listdir(folder)


@pytest.mark.parametrize("argv, words", [
    (("job", "new", "Not_A_Job", "--blank"), "'Not_A_Job' is not a job's name"),
    (("app", "new", "not-an-app", "--blank"), "'not-an-app' is not an app's name"),
])
def test_a_blank_folders_name_is_the_kinds_name(tmp_path, capsys, argv, words):
    kind, action, name, flag = argv
    code, _out, err = run(capsys, kind, action, str(tmp_path / name), flag)
    assert code == 2 and words in err and not (tmp_path / name).exists()


def test_a_card_of_another_kind_is_refused(tmp_path, capsys):
    code, _out, err = run(capsys, "job", "new", str(tmp_path / "x"), "--from",
                          os.path.join(APPS, APP, "spec.yml"))
    assert code == 2
    assert "kind is 'app': `mercury job new` writes a job's folder" in err


def test_from_and_blank_are_one_or_the_other(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_:
        CLI_MODULE.main(["job", "new", str(tmp_path / "x")])
    assert exit_.value.code == 2
    with pytest.raises(S.ScaffoldError):
        S.files("job", name="x", card_text="kind: job\n", blank=True)


# ── --blank: the card refused for its questions ──────────────────────────────────────────────

@pytest.mark.parametrize("kind, name", [("job", "blank-job"), ("app", "blank_app")])
def test_a_blank_cards_every_open_field_is_refused_by_name(tmp_path, capsys, kind, name):
    folder = str(tmp_path / name)
    assert run(capsys, kind, "new", folder, "--blank")[0] == 0
    verdict = app_gate.check(folder) if kind == "app" else G.check(folder)
    spec = verdict.check("spec")
    assert not spec.passed
    asked = [d.split(":")[0] for d in spec.details]
    assert asked == ["summary", "permission", "scope.object_types", "scope.roles", "inputs",
                     "outputs", "examples[0].given", "examples[0].when", "examples[0].then",
                     "examples[0].fixture", "examples[1].given", "examples[1].when",
                     "examples[1].then", "examples[1].fixture"]
    assert all("an open question" in d for d in spec.details)
    tests = verdict.check("tests")
    # A job's stub tests run and fail; an app's run in the container harness, not here (C2635).
    assert not tests.passed and tests.summary == ("2 of 2 tests did not pass" if kind == "job"
                                                  else app_gate.HARNESS_NOT_RUN)
    assert verdict.check("examples").summary.startswith("not run: the spec card is refused")
    code, _out, _err = run(capsys, kind, "check", folder)
    assert code == 1


# ── app new ──────────────────────────────────────────────────────────────────────────────────

def test_app_new_writes_a_valid_manifest_and_failing_tests(tmp_path, capsys):
    folder = str(tmp_path / APP)
    code, _out, _err = run(capsys, "app", "new", folder, "--from",
                           os.path.join(APPS, APP, "spec.yml"))
    assert code == 0
    assert sorted(os.listdir(folder)) == sorted(["spec.yml", "manifest.yml", f"{APP}.py",
                                                 "test_app.py", "conftest.py", "AUTHORING.md"])
    manifest = load_manifest(folder)
    assert manifest.name == APP and manifest.tests == ("test_app.py",)
    assert manifest.summary == "Decides a DNS query by the app's overrides, before any " \
                               "verdict is asked."
    # What `new` writes is written for the oldest controller Python the check knows.
    verdict = app_gate.check(folder, python=(3, 5))
    assert verdict.check("manifest").passed and verdict.check("static").passed
    assert verdict.check("examples").passed
    assert not verdict.check("tests").passed
    assert sorted(stub_tests_of(folder, "test_app.py")) == [
        "test_a_blocked_name_is_blocked_even_when_it_is_also_allowed",
        "test_a_zone_covers_every_name_under_it_but_not_itself"]


# ── the stub's names ─────────────────────────────────────────────────────────────────────────

def test_a_stub_tests_name_is_an_identifier_and_unique():
    taken = set()
    assert S.stub_test_name("A priority: out of range!", taken) == \
        "test_a_priority_out_of_range"
    assert S.stub_test_name("a priority out of range", taken) == \
        "test_a_priority_out_of_range_2"
    assert S.stub_test_name("???", taken) == "test_example"
    long = S.stub_test_name("x " * 100, taken)
    assert long.isidentifier() and len(long) <= len("test_") + S.TEST_NAME_MAX


# ── AUTHORING.md and the fixed files ─────────────────────────────────────────────────────────

def test_new_writes_the_authoring_guide_and_conftest_byte_for_byte(tmp_path, capsys):
    folder = str(tmp_path / "x-job")
    run(capsys, "job", "new", folder, "--blank")
    assert read(os.path.join(folder, "AUTHORING.md")) == \
        read(os.path.join(S.TEMPLATES, "AUTHORING.md"))
    assert read(os.path.join(folder, "conftest.py")) == \
        read(os.path.join(S.TEMPLATES, "conftest.py.template"))


@pytest.mark.parametrize("folder", [os.path.join(JOBS, n) for n in FIXTURE_JOBS]
                         + [os.path.join(APPS, APP)])
def test_every_fixtures_conftest_is_the_one_new_writes(folder):
    assert read(os.path.join(folder, "conftest.py")) == \
        read(os.path.join(S.TEMPLATES, "conftest.py.template"))


def test_every_check_has_its_rule_and_action():
    assert set(G.RULES) == set(G.ACTIONS) == set(G.CHECKS)
    assert set(app_gate.RULES) == set(app_gate.ACTIONS) == set(app_gate.APP_CHECKS)


def test_the_guide_holds_the_gates_checks_exactly_as_generated():
    """A check added to the gate, or an action reworded, fails here until the guide's list is
    regenerated (`scaffold.gate_checks_markdown()`, pasted between its two marker lines)."""
    guide = S.authoring_text()
    generated = S.gate_checks_markdown()
    begin, end = guide.index(S.CHECKS_BEGIN), guide.index(S.CHECKS_END) + len(S.CHECKS_END)
    assert guide[begin:end] == generated
    for name in app_gate.APP_CHECKS:
        assert f"**`{name}`.**" in generated
        action = app_gate.ACTIONS[name].format(ceiling=G.mutate.CEILING)
        assert f"> To clear it: {action}\n" in generated + "\n"


_QUOTED = re.compile(r"<!-- quoted from (\S+) -->\n```[a-z]*\n(.*?)```", re.S)


def test_every_block_the_guide_quotes_is_in_the_file_it_names():
    quoted = _QUOTED.findall(S.authoring_text())
    assert len(quoted) >= 10, "the scan reads almost nothing"
    for path, block in quoted:
        assert block in read(os.path.join(ROOT, path)), path


def _block(marker: str) -> str:
    match = re.search(rf"<!-- {re.escape(marker)} -->\n```[a-z]*\n(.*?)```", S.authoring_text(),
                      re.S)
    assert match, marker
    return match.group(1)


def test_the_worked_failures_words_are_the_gates():
    folder = os.path.join(JOBS, "tautology")
    words = _block("the gate's words on tests/fixtures/jobs/tautology").splitlines()
    assert words == list(G.check(folder).check("survivors").details)


def test_the_worked_failures_fixed_tests_kill_every_survivor(tmp_path):
    folder = copy(tmp_path, os.path.join(JOBS, "tautology"))
    with open(os.path.join(folder, "test_job.py"), "w", encoding="utf-8") as fh:
        fh.write(_block("the fixed tests of tests/fixtures/jobs/tautology"))
    verdict = G.check(folder)
    assert verdict.passed, [(c.name, c.details) for c in verdict.checks if not c.passed]
    assert verdict.check("survivors").summary == "no survivors"
