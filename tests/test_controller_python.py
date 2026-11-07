"""The controller's Python, measured per network (the operator's decision, 2026-11-07):
`mercury app check` holds an app to the minor version its network's controller runs apps on,
read from the network's record (`modules/sdn/controller_runtime.py`), never a constant; the
grammar and standard-library names that version lacks are refused (`modules/apps/
python_versions.py`), and a version not known is "can't tell" and fails.

Each rule planted: an f-string refused for a 3.5 controller and accepted for 3.9 (the
operator's T-case), at the gate and through the CLI; a variable annotation, a numeric
underscore and an async generator refused for 3.5; `dataclasses` refused for 3.5 and allowed
for 3.7; a name of an allowed module and a builtin newer than the controller refused; no
record, an unreadable one and no network named each "can't tell" and failing; the verdict
following the record when the record changes. The record's one write refuses what is not a
measurement, and the host's capture list declares the interpreter read.

No address is parsed here (a record names a host by its label, a read by its command), so
there is no IPv4 or IPv6 case to give."""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import stat

import pytest

from modules import attention as ATT
from modules.apps import allowlist as A
from modules.apps import gate as app_gate
from modules.apps import python_versions as V
from modules.jobs import runner
from modules.jobs import scaffold as S
from modules.sdn import controller_runtime as CR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS = os.path.join(ROOT, "tests", "fixtures", "apps")
APP = "dns_overrides"
STUB = os.path.join(ROOT, "modules", "apps", "sdk", "mercury_app", "__init__.py")
READ = "/opt/app-venv/bin/python --version"
AT = "2026-11-05T18:00:00Z"
#: The Needs attention source as defined (a test below replaces it on the module).
SOURCE = ATT.controller_python_source
F_STRING_APP = ('"""An app that formats with an f-string."""\n\n\n'
                'def label(dpid, port):\n    return f"{dpid}:{port}"\n')


@pytest.fixture
def networks(tmp_path, monkeypatch):
    """A data folder of the test's own; `measure(network, answer)` records what the
    network's controller app runtime answered, as the host's read will."""
    from modules import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "data" / "lists"))

    def measure(network, answer):
        return CR.record_python(network, answer=answer, read_command=READ, host="ctl-1",
                                at=AT, by="read-run-1")
    return measure


def problems(code: str, python) -> list:
    found = A.check(runner.Sources("planted", {"app": code}, {}), (), python=python)
    return found.problems


def app_folder(tmp_path, code: str = None) -> str:
    folder = str(tmp_path / APP)
    shutil.copytree(os.path.join(APPS, APP), folder)
    if code is not None:
        with open(os.path.join(folder, f"{APP}.py"), "a", encoding="utf-8") as fh:
            fh.write("\n\n" + code)
    return folder


def load_cli():
    loader = importlib.machinery.SourceFileLoader("mercury_cli_python",
                                                  os.path.join(ROOT, "scripts", "mercury"))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name,
                                                                             loader))
    loader.exec_module(module)
    return module


# ── the operator's T-case: an f-string on a 3.5 controller ──────────────────────────────────

def test_an_f_string_is_refused_for_a_3_5_controller_and_accepted_for_3_9(tmp_path, networks):
    networks("lab-old", "Python 3.5.2")
    networks("lab-new", "Python 3.9.18")
    folder = app_folder(tmp_path, 'def label(dpid, port):\n    return f"{dpid}:{port}"\n')
    old = app_gate.check(folder, python=CR.target("lab-old")).check("static")
    assert not old.passed and old.summary == "1 uses refused"
    assert len(old.details) == 2
    assert old.details[0].startswith(f"{APP}.py line ")
    assert old.details[0].endswith(": an f-string needs Python 3.6, and the controller's "
                                   "Python is 3.5: use str.format or %")
    assert old.details[1] == (f"checked against Python 3.5 on lab-old's controller, measured "
                              f"by `{READ}` on ctl-1 at {AT} (it answered 'Python 3.5.2')")
    new = app_gate.check(folder, python=CR.target("lab-new")).check("static")
    assert new.passed, new.details
    assert new.summary == "1 modules and 1 test files allowed on Python 3.9, 0 egress calls"
    assert new.details == (f"checked against Python 3.9 on lab-new's controller, measured by "
                           f"`{READ}` on ctl-1 at {AT} (it answered 'Python 3.9.18')",)


def test_the_cli_refuses_the_f_string_for_the_3_5_network_and_prints_the_gates_verdict(
        tmp_path, networks, capsys):
    """T24 with --network: the CLI's JSON is the gate's verdict on the network's target."""
    networks("lab-old", "Python 3.5.2")
    folder = app_folder(tmp_path, 'def label(dpid, port):\n    return f"{dpid}:{port}"\n')
    cli = load_cli()
    assert cli.main(["app", "check", folder, "--network", "lab-old", "--json"]) == 1
    printed = json.loads(capsys.readouterr().out)
    printed.pop("timings")
    want = app_gate.check(folder, python=CR.target("lab-old")).as_dict()
    want.pop("timings")
    assert printed == want
    static = next(c for c in printed["checks"] if c["name"] == "static")
    assert not static["passed"] and "an f-string needs Python 3.6" in static["details"][0]
    assert cli.main(["app", "check", folder, "--network", "lab-old"]) == 1
    out = capsys.readouterr().out
    assert f"  - {static['details'][0]}\n" in out


def test_the_verdict_follows_the_networks_record_when_it_changes(tmp_path, networks):
    """The version is the record's, not a constant: the same folder, the same network,
    another measurement, another verdict."""
    folder = app_folder(tmp_path, 'def label(dpid, port):\n    return f"{dpid}:{port}"\n')
    networks("lab9", "Python 3.9.18")
    assert app_gate.check(folder, python=CR.target("lab9")).check("static").passed
    networks("lab9", "Python 3.5.2")
    assert not app_gate.check(folder, python=CR.target("lab9")).check("static").passed
    networks("lab9", "Python 3.6.15")
    assert app_gate.check(folder, python=CR.target("lab9")).check("static").passed


# ── the grammar a 3.5 controller lacks ──────────────────────────────────────────────────────

@pytest.mark.parametrize("code, words", [
    ("y: int = 1\n", "Variable annotation syntax is only supported in Python 3.6"),
    ("n = 1_000\n", "Underscores in numeric literals are only supported in Python 3.6"),
    ("async def f(a):\n    return [x async for x in a]\n", "Async comprehensions are only "
                                                           "supported in Python 3.6"),
])
def test_grammar_the_parser_refuses_for_3_5_is_named_as_the_controllers(code, words):
    got = problems(code, (3, 5))
    assert len(got) == 1, got
    assert ": does not parse as Python 3.5, the controller's interpreter (" in got[0]
    assert words in got[0]
    assert problems(code, (3, 6)) == []


@pytest.mark.parametrize("code, feature", [
    ('x = f"{1}"\n', V.F_STRING),
    ("x = f'plain'\n", V.F_STRING),
    ("async def f():\n    yield 1\n", V.ASYNC_GENERATOR),
    ("async def f(a):\n    return [await x for x in a]\n", V.AWAIT_IN_COMPREHENSION),
])
def test_grammar_the_parser_lets_through_for_3_5_is_refused_by_mercurys_check(code, feature):
    got = problems(code, (3, 5))
    assert got == [f"app.py line {2 if 'def' in code else 1}: {feature.words} needs Python "
                   f"3.6, and the controller's Python is 3.5: {feature.instead}"]
    assert problems(code, (3, 6)) == []


def test_an_f_string_with_a_nested_spec_is_one_finding():
    assert len(problems('w = 3\nx = f"{1:{w}}"\n', (3, 5))) == 1


@pytest.mark.parametrize("code, feature, ok", [
    ("y: int = 1\n", V.VARIABLE_ANNOTATION, (3, 6)),
    ("n = 1_000\n", V.NUMERIC_UNDERSCORE, (3, 6)),
    ("if (n := 1):\n    pass\n", V.WALRUS, (3, 8)),
    ("def f(a, /):\n    pass\n", V.POSITIONAL_ONLY, (3, 8)),
    ("@a[0].b\ndef f():\n    pass\n", V.DECORATOR_EXPRESSION, (3, 9)),
    ("match x:\n    case 1:\n        pass\n", V.MATCH, (3, 10)),
    ("type X = int\n", V.TYPE_STATEMENT, (3, 12)),
    ("def f[T](x):\n    return x\n", V.TYPE_PARAMETERS, (3, 12)),
])
def test_mercurys_own_check_finds_what_the_parser_also_refuses(code, feature, ok):
    """Belt and braces: each feature the parser refuses today is found by Mercury's own
    check too, so a parser that stops refusing one (feature_version's floor rose to 3.7 in a
    later CPython) does not let it through."""
    import ast

    tree = ast.parse(code)
    older = (ok[0], ok[1] - 1)
    got = V.grammar_problems(tree, code, "app.py", V.Target(older, "planted"))
    assert any(f"{feature.words} needs Python {V.shown(ok)}" in p for p in got), got
    assert V.grammar_problems(tree, code, "app.py", V.Target(ok, "planted")) == []


def test_a_3_5_clean_app_passes(tmp_path, networks):
    networks("lab-old", "Python 3.5.2")
    folder = app_folder(tmp_path, 'def label(dpid, port):\n    return "{}:{}".format(dpid, '
                                  'port)\n')
    static = app_gate.check(folder, python=CR.target("lab-old")).check("static")
    assert static.passed, static.details
    assert static.summary == "1 modules and 1 test files allowed on Python 3.5, 0 egress calls"


# ── the standard library a 3.5 controller lacks ─────────────────────────────────────────────

@pytest.mark.parametrize("line", ["import dataclasses\n",
                                  "from dataclasses import dataclass\n"])
def test_dataclasses_is_refused_for_3_5_and_allowed_for_3_7(line):
    got = problems(line, (3, 5))
    assert len(got) == 1, got
    assert "`dataclasses` is refused for this controller: the module is new in Python 3.7 " \
           "(the docs' \"New in version 3.7\"), and the controller's Python is 3.5" in got[0]
    assert problems(line, (3, 6)) != []
    assert problems(line, (3, 7)) == [] and problems(line, (3, 9)) == []


def test_the_allowlists_modules_are_filtered_by_the_target():
    assert "dataclasses" not in A.allowed_modules((3, 5))
    assert "dataclasses" in A.allowed_modules((3, 7))
    assert set(A.allowed_modules()) - set(A.allowed_modules((3, 5))) == {"dataclasses"}


@pytest.mark.parametrize("code, name, first", [
    ("from datetime import datetime\nx = datetime.fromisoformat('2026-01-01')\n",
     "datetime.datetime.fromisoformat", "3.7"),
    ("import datetime\nx = datetime.datetime.fromisoformat('2026-01-01')\n",
     "datetime.datetime.fromisoformat", "3.7"),
    ("import enum\n\n\nclass C(enum.Enum):\n    A = enum.auto()\n", "enum.auto", "3.6"),
    ("from enum import auto\n", "enum.auto", "3.6"),
    ("import math\nx = math.tau\n", "math.tau", "3.6"),
    ("import re\nx = re.Match\n", "re.Match", "3.7"),
    ("from typing import ClassVar\n", "typing.ClassVar", "3.6"),
    ("import itertools\nx = itertools.pairwise([1, 2])\n", "itertools.pairwise", "3.10"),
    ("try:\n    pass\nexcept ModuleNotFoundError:\n    pass\n", "ModuleNotFoundError", "3.6"),
])
def test_a_name_newer_than_the_controller_is_refused_naming_both_versions(code, name, first):
    got = problems(code, (3, 5))
    assert len(got) == 1, got
    assert f"`{name}` is refused for this controller: the " in got[0]
    assert f"is new in Python {first} " in got[0] and "the controller's Python is 3.5" in got[0]
    assert problems(code, tuple(int(p) for p in first.split("."))) == []


def test_a_name_the_file_binds_itself_is_its_own_not_the_builtin():
    assert problems("def anext(it):\n    return next(it)\n\n\nx = anext(iter([1]))\n",
                    (3, 5)) == []
    assert len(problems("x = anext(iter([1]))\n", (3, 5))) == 1


@pytest.mark.parametrize("docs, first", [("3.7", (3, 7)), ("3.5.3", (3, 6)),
                                         ("3.5.4, 3.6.1", (3, 7)), ("3.5.4, 3.6.0", (3, 6)),
                                         ("3.7.2", (3, 8))])
def test_a_name_added_in_a_patch_release_counts_from_the_next_minor(docs, first):
    assert V.available_from(docs) == first


def test_the_tables_reach_what_an_app_would_use():
    """A floor on the population, and every allowed standard-library module with a name in
    the tables is one the allowlist allows (a typo would check nothing)."""
    assert len(V.NAMES) >= 100 and len(V.GRAMMAR) >= 13
    for dotted in V.NAMES:
        assert A.lookup(dotted)[1] is not None and A.lookup(dotted)[1].allowed, dotted
    for module in ("dataclasses", "secrets", "contextvars"):
        assert module in V.MODULES
    missing = dict(V.missing_at((3, 5)))
    for name in ("dataclasses", "secrets", "contextvars", "enum.auto",
                 "datetime.datetime.fromisoformat", "re.Match", "math.tau"):
        assert name in missing, name
    assert V.missing_at((3, 14)) == []


# ── not known is "can't tell", and fails ─────────────────────────────────────────────────────

def test_no_recorded_version_is_cant_tell_and_fails(tmp_path, networks):
    folder = app_folder(tmp_path)
    static = app_gate.check(folder, python=CR.target("lab9")).check("static")
    assert not static.passed
    assert static.summary == "can't tell: the controller's Python is not measured for lab9"
    assert static.action == app_gate.PYTHON_ACTION and static.details == ()


def test_no_network_named_is_cant_tell_and_fails(tmp_path, capsys):
    folder = app_folder(tmp_path)
    static = app_gate.check(folder).check("static")
    assert not static.passed and static.summary.startswith("can't tell: no network was named")
    cli = load_cli()
    assert cli.main(["app", "check", folder]) == 1
    assert "FAILED  static" in capsys.readouterr().out


def test_cant_tell_still_names_every_other_refusal(tmp_path, networks):
    folder = app_folder(tmp_path, "import socket\n")
    static = app_gate.check(folder, python=CR.target("lab9")).check("static")
    assert not static.passed and static.summary.startswith("can't tell")
    assert len(static.details) == 1 and "`socket` is refused" in static.details[0]
    assert static.action.startswith(app_gate.PYTHON_ACTION) and \
        app_gate.ACTIONS["static"] in static.action


def test_an_unreadable_record_is_cant_tell_naming_it(tmp_path, networks):
    from modules import config

    folder = os.path.join(config.LISTS_DIR, "lab9")
    os.makedirs(folder)
    with open(os.path.join(folder, CR.FILE_NAME), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    target = CR.target("lab9")
    assert target.version is None
    assert target.words == ("can't tell: the controller's Python for lab9 cannot be read "
                            "(controller_runtime.json could not be read (JSONDecodeError))")
    with pytest.raises(CR.RuntimeRefused, match="cannot be read"):
        networks("lab9", "Python 3.5.2")
    with open(os.path.join(folder, CR.FILE_NAME), encoding="utf-8") as fh:
        assert fh.read() == "{not json", "the unreadable record was replaced"


def test_a_version_older_than_the_tables_is_cant_tell(tmp_path, networks):
    networks("lab-ancient", "Python 3.4.3")
    folder = app_folder(tmp_path)
    static = app_gate.check(folder, python=CR.target("lab-ancient")).check("static")
    assert not static.passed and static.summary.startswith(
        "can't tell: the controller's Python is 3.4 (")
    assert "older than 3.5, where the check's tables start" in static.summary


def test_a_read_of_the_record_writes_nothing_and_makes_no_folder(networks):
    from modules import config

    assert CR.target("nowhere").version is None
    assert not os.path.exists(os.path.join(config.LISTS_DIR, "nowhere"))


# ── the record's one write ───────────────────────────────────────────────────────────────────

def test_the_record_holds_the_minor_and_where_it_was_measured(networks):
    from modules import config

    written = networks("lab9", "Python 3.5.2")
    row = written["python"]
    assert {k: row[k] for k in ("version", "answer", "read", "host", "at", "by",
                                "provisional")} == {
        "version": "3.5", "answer": "Python 3.5.2", "read": READ, "host": "ctl-1", "at": AT,
        "by": "read-run-1", "provisional": False}
    assert written["change"] is None, "the first value recorded changes nothing"
    path = os.path.join(config.LISTS_DIR, "lab9", CR.FILE_NAME)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert CR.read("lab9")["state"] == "measured"
    assert CR.target("lab9").version == (3, 5)
    assert CR.read("other")["state"] == "absent", "each network's record is its own"


@pytest.mark.parametrize("change, words", [
    ({"network": ""}, "no network was named"),
    ({"read_command": "python3 --version"}, "is not the interpreter read"),
    ({"read_command": "/opt/app-venv/bin/python -c 'print(1)'"}, "is not the interpreter "
                                                                   "read"),
    ({"answer": "command not found"}, "is not an interpreter's version"),
    ({"answer": "Python 2.7.12"}, "is Python 2, and an app is checked against Python 3 only"),
    ({"at": "yesterday"}, "is not a UTC time of the shape"),
    ({"host": ""}, "host is empty"),
    ({"by": ""}, "by is empty"),
])
def test_what_is_not_a_measurement_is_refused_by_name(networks, change, words):
    values = {"network": "lab9", "answer": "Python 3.5.2", "read_command": READ,
              "host": "ctl-1", "at": AT, "by": "read-run-1"}
    values.update(change)
    network = values.pop("network")
    with pytest.raises(CR.RuntimeRefused, match=words.replace("(", r"\(")):
        CR.record_python(network, **values)
    assert CR.read("lab9")["state"] == "absent"


@pytest.mark.parametrize("command", [READ, "/opt/ryu/bin/python3 --version"])
def test_the_linux_hosts_capture_list_declares_the_interpreter_read(command):
    from modules import discovery

    assert discovery.command_refusal("linux", command) == ""
    assert discovery.is_python_read(command)


@pytest.mark.parametrize("command", ["/opt/../bin/python --version",
                                     "/opt/a/b/bin/python --version",
                                     "/usr/bin/python3 --version",
                                     "/opt/a/bin/python -c x",
                                     "/opt/a/bin/python --version; reboot",
                                     "/opt/a/bin/pip --version"])
def test_any_other_interpreter_command_is_refused(command):
    from modules import discovery

    assert discovery.command_refusal("linux", command).startswith("REFUSED")
    assert not discovery.is_python_read(command)


# ── what ships to the controller, and the guides ─────────────────────────────────────────────

def test_the_sdk_stub_is_written_for_the_oldest_controller_python():
    import ast

    with open(STUB, encoding="utf-8") as fh:
        text = fh.read()
    tree = ast.parse(text, feature_version=V.OLDEST)
    assert V.grammar_problems(tree, text, "mercury_app", V.Target(V.OLDEST, "planted")) == []


@pytest.mark.parametrize("path", [os.path.join(ROOT, "modules", "jobs", "templates",
                                               "AUTHORING.md"),
                                  os.path.join(ROOT, "docs", "DEVELOPING_JOBS_AND_APPS.md")])
def test_the_guides_hold_the_tables_exactly_as_generated(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    begin, end = text.index(S.PYTHON_BEGIN), text.index(S.PYTHON_END) + len(S.PYTHON_END)
    generated = S.controller_python_markdown()
    assert text[begin:end] == generated
    for feature in V.GRAMMAR:
        assert f"| {feature.words} |" in generated
    for dotted in list(V.MODULES) + list(V.NAMES) + list(V.BUILTINS):
        assert f"`{dotted}`" in generated, dotted


def test_the_guides_3_5_example_passes_for_a_3_5_controller():
    text = S.authoring_text()
    start = text.index("```python\nLOG.info(")
    block = text[start + len("```python\n"):text.index("```", start + 3)]
    assert problems("import logging\n\nLOG = logging.getLogger(__name__)\ndpid = port = 1\n"
                    + block, (3, 5)) == []
    assert problems(F_STRING_APP, (3, 5)) != []


# ── a provisional value, and a measurement replacing it (the operator, 2026-11-07) ──────────

NOTE = ("the 2026-11-05 capture's system python3 on Ubuntu 16.04.5; the app runtime's own "
        "interpreter is unmeasured")


def provisional(network="lab9", answer="Python 3.5.2"):
    return CR.record_python(network, answer=answer, read_command="python3 --version",
                            host="the controller", at="2026-11-05", by="operator",
                            provisional=True, note=NOTE)


def rows_now(network="lab9"):
    return SOURCE(found={network: CR.read(network)}, now=0)["rows"]


def test_a_provisional_record_is_targeted_and_its_provenance_shown(tmp_path, networks,
                                                                    capsys):
    assert provisional()["change"] is None
    assert CR.read("lab9")["state"] == "provisional"
    target = CR.target("lab9")
    assert target.version == (3, 5) and target.provisional
    folder = app_folder(tmp_path)
    static = app_gate.check(folder, python=target).check("static")
    assert static.passed, static.details
    assert static.summary == ("1 modules and 1 test files allowed on Python 3.5 "
                              "(provisional), 0 egress calls")
    assert static.details == (
        f"checked against Python 3.5 on lab9's controller, PROVISIONAL: {NOTE}; `python3 "
        "--version` on the controller at 2026-11-05 (it answered 'Python 3.5.2'); not yet "
        "measured by the interpreter read (/opt/<folder>/bin/python --version)",)
    cli = load_cli()
    assert cli.main(["app", "check", folder, "--network", "lab9"]) == 1
    out = capsys.readouterr().out
    assert "allowed on Python 3.5 (provisional)" in out and f"PROVISIONAL: {NOTE}" in out
    assert "can't tell" not in out
    with open(os.path.join(folder, f"{APP}.py"), "a", encoding="utf-8") as fh:
        fh.write("\n\n" + 'def label(dpid, port):\n    return f"{dpid}:{port}"\n')
    refused = app_gate.check(folder, python=CR.target("lab9")).check("static")
    assert not refused.passed and "an f-string needs Python 3.6" in refused.details[0]
    assert refused.details[-1].startswith("checked against Python 3.5 on lab9's controller, "
                                          "PROVISIONAL")


@pytest.mark.parametrize("change, words", [
    ({"note": ""}, "note is empty"),
    ({"provisional": False, "at": "2026-11-05T18:00:00Z"}, "is not the interpreter read"),
    ({"provisional": False, "read_command": READ}, "is not a UTC time of the shape "
                                                   "YYYY-MM-DDTHH:MM:SSZ$"),
])
def test_a_provisional_value_needs_its_note_and_only_it_takes_another_read_or_a_date(
        networks, change, words):
    values = {"answer": "Python 3.5.2", "read_command": "python3 --version",
              "host": "the controller", "at": "2026-11-05", "by": "operator",
              "provisional": True, "note": NOTE}
    values.update(change)
    with pytest.raises(CR.RuntimeRefused, match=words):
        CR.record_python("lab9", **values)


def test_a_provisional_value_never_replaces_a_measurement(networks):
    networks("lab9", "Python 3.6.15")
    with pytest.raises(CR.RuntimeRefused, match="a provisional value never replaces a "
                                                "measurement"):
        provisional()
    assert CR.read("lab9")["python"]["version"] == "3.6"


def test_a_measurement_of_the_same_minor_replaces_it_and_raises_no_row(networks):
    provisional()
    written = networks("lab9", "Python 3.5.10")
    assert written["change"] is None
    got = CR.read("lab9")
    assert got["state"] == "measured" and got["change"] is None
    assert not CR.target("lab9").provisional
    assert rows_now() == []


def test_a_measurement_of_another_minor_raises_the_row_naming_both(networks):
    from modules import attention

    provisional()
    written = networks("lab9", "Python 3.6.15")
    change = written["change"]
    assert change["from"]["version"] == "3.5" and change["to"]["version"] == "3.6"
    rows = rows_now()
    assert len(rows) == 1
    r = rows[0]
    assert (r["source"], r["kind"], r["level"]) == ("controller_python", "changed", "warning")
    assert r["what"] == ("lab9's controller Python is now 3.6, not 3.5: its apps were checked "
                         "against 3.5")
    assert f"Before: Python 3.5, PROVISIONAL: {NOTE}; `python3 --version`" in r["cause"]
    assert f"Now: Python 3.6, measured by `{READ}` on ctl-1 at {AT}" in r["cause"]
    assert r["action"]["label"] == ("Re-check each of lab9's apps against Python 3.6 (`mercury "
                                    "app check <folder> --network lab9`), then acknowledge "
                                    "with what the checks found")
    assert r["acknowledge"] is True and r["event"] == change["id"]
    assert r["clears"]["ways"] == ["resolves", "acknowledge"]
    assert r["operands"]["from_provisional"] and not r["operands"]["to_provisional"]
    assert attention.CLEARS[("controller_python", "changed")][1].startswith(
        "the network's apps are re-checked against the version now recorded")


def test_a_recheck_against_the_new_version_clears_it_and_another_version_is_refused(networks):
    provisional()
    networks("lab9", "Python 3.6.15")
    with pytest.raises(CR.RuntimeRefused, match="a re-check is against the recorded version"):
        CR.record_recheck("lab9", version="3.5", by="op@example.com")
    assert len(rows_now()) == 1
    CR.record_recheck("lab9", version="3.6", by="op@example.com")
    assert rows_now() == []


def test_a_later_change_raises_it_again_as_a_new_event(networks):
    provisional()
    first = networks("lab9", "Python 3.6.15")["change"]
    CR.record_recheck("lab9", version="3.6", by="op@example.com")
    assert rows_now() == []
    second = networks("lab9", "Python 3.7.17")["change"]
    rows = rows_now()
    assert len(rows) == 1 and rows[0]["event"] == second["id"] != first["id"]


def test_an_acknowledgement_takes_the_row_off_and_a_later_change_brings_it_back(
        networks, monkeypatch):
    from modules import attention as A

    real = A.controller_python_source
    # The handler recomputes the row from its source (never the browser's copy): the source
    # over this network's real record, since the test's registry holds no networks.
    monkeypatch.setattr(A, "controller_python_source",
                        lambda: real(found={"lab9": CR.read("lab9")}))
    provisional()
    networks("lab9", "Python 3.6.15")
    r = rows_now()[0]
    why = "re-checked both apps against 3.6 by hand, both pass"
    got = A.acknowledge(r["id"], r["event"], why, by="op@example.com", verified="access")
    assert got["ok"], got
    kept, gone, problem = A._without_acknowledged(rows_now())  # noqa: SLF001
    assert kept == [] and problem is None and gone[0]["why"] == why
    networks("lab9", "Python 3.7.17")
    kept, _gone, _problem = A._without_acknowledged(rows_now())  # noqa: SLF001
    assert len(kept) == 1, "a later change is a new event, raised again"


def test_no_record_raises_no_row_and_is_cant_tell(networks):
    assert rows_now() == []
    assert CR.target("lab9").problem() == ("can't tell: the controller's Python is not "
                                           "measured for lab9")
