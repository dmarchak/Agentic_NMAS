"""The app SDK's test helper, `mercury_app.testing` (C2644, C2652; the operator's decision 8 of
2026-11-07, option (a)): what an app's tests import, run on the controller's own Python in the
container harness, so written for 3.5 on the standard library alone.

Held here:
- every file an app's tests import (the SDK, its testing module, the app's fixed conftest, a
  new app's stub tests and the worked app's files) passes Mercury's own 3.5 check: the app
  check's parse at 3.5, its grammar check (which finds the f-strings `feature_version` lets
  through) and its standard-library tables; a planted f-string is found;
- its answers equal `modules.jobs.testing`'s and `modules.jobs.authoring`'s on the same inputs
  (`covers`, `refused`, `ContractError`, the fixtures by name, `netbox`, `job_class_in` and the
  recorded Ryu), the one difference by design named: `ctx` given a job;
- it imports neither pydantic nor `modules.jobs`, even where Mercury's Python has them;
- the conftest `mercury app new` writes imports no Mercury module but `mercury_app`, and runs
  under pytest with the SDK on the path alone, giving `ryu` its recording;
- a job's conftest is unchanged: `mercury job new` writes `conftest.py.template`, through
  `modules.jobs.testing`.

No address is parsed here (the recording's datapath ids are integers), so there is no IPv4 or
IPv6 case to give."""

import ast
import os
import subprocess
import sys
import types

import pytest

from modules.apps import allowlist as A
from modules.apps import python_versions as V
from modules.apps.sdk.mercury_app import testing as T
from modules.jobs import Job, JobMeta, Scope, ScopeError
from modules.jobs import authoring as AU
from modules.jobs import scaffold as S
from modules.jobs import testing as J
from tests.fixtures.sdn import ryu_recorded as R
from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDK = os.path.join(ROOT, "modules", "apps", "sdk")
APP_FIXTURE = os.path.join(ROOT, "tests", "fixtures", "apps", "dns_overrides")
OLDEST = V.Target(V.OLDEST, "the oldest controller Python the app check knows")


# ── every file an app's tests import passes Mercury's own 3.5 check ─────────────────────────

def _imported(tree):
    """`{bound name: dotted module or name}` of *tree*'s imports, and every dotted name read."""
    bound, dotted = {}, []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                bound[a.asname or a.name.partition(".")[0]] = a.name if a.asname \
                    else a.name.partition(".")[0]
                dotted.append(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            dotted.append(node.module)
            for a in node.names:
                bound[a.asname or a.name] = f"{node.module}.{a.name}"
                dotted.append(f"{node.module}.{a.name}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            chain, inner = [], node
            while isinstance(inner, ast.Attribute):
                chain.append(inner.attr)
                inner = inner.value
            if isinstance(inner, ast.Name) and inner.id in bound:
                dotted.append(".".join([bound[inner.id]] + list(reversed(chain))))
        elif isinstance(node, ast.Name) and node.id in V.BUILTINS:
            dotted.append(node.id)
    return dotted


def on_3_5(text: str, file: str) -> list:
    """Mercury's own check of *text* for a 3.5 controller: the app check's parse at 3.5, its
    grammar check, and each module, name or builtin its tables say 3.5 lacks."""
    tree, why = A.parse_problem(text, file, OLDEST)
    if tree is None:
        return [why]
    out = V.grammar_problems(tree, text, file, OLDEST)
    for dotted in _imported(tree):
        parts = dotted.split(".")
        for i in range(1, len(parts) + 1):
            why = V.name_problem(".".join(parts[:i]), OLDEST)
            if why:
                out.append(f"{file}: {why}")
                break
    return out


def app_test_files() -> dict:
    """`{name: text}`: every Python file an app's tests import or are, by the property: the
    tracked files of the app SDK (`modules/apps/sdk/`), the worked app's folder, and the
    Python files `mercury app new` writes."""
    out = {}
    for path in tracked("modules/apps/sdk", os.path.relpath(APP_FIXTURE, ROOT), suffix=".py"):
        with open(path, encoding="utf-8") as fh:
            out[os.path.relpath(path, ROOT)] = fh.read()
    new = S.files("app", name="new_app", blank=True)
    out.update({f"(app new) {n}": t for n, t in new.items() if n.endswith(".py")})
    return out


def test_every_file_an_apps_tests_import_passes_the_3_5_check():
    files = app_test_files()
    assert len(files) >= 8, sorted(files)
    for expected in ("modules/apps/sdk/mercury_app/__init__.py",
                     "modules/apps/sdk/mercury_app/testing.py", "(app new) conftest.py",
                     "(app new) test_app.py", "tests/fixtures/apps/dns_overrides/conftest.py"):
        assert expected in files, expected
    found = {name: on_3_5(text, name) for name, text in files.items()}
    assert {n: p for n, p in found.items() if p} == {}


@pytest.mark.parametrize("planted, words", [
    ('x = 1\nlabel = f"{x}"\n', "an f-string needs Python 3.6"),
    ("import math\nx = math.tau\n", "`math.tau` is refused for this controller"),
    ("y: int = 1\n", "does not parse as Python 3.5"),
])
def test_the_3_5_check_finds_a_planted_use(planted, words):
    got = on_3_5(planted, "planted.py")
    assert len(got) == 1 and words in got[0], got


def test_the_testing_module_imports_no_mercury_module_nor_pydantic():
    """Read from its source, wherever an import sits (a function's body too), and run: a
    fresh interpreter that imports it has loaded neither."""
    with open(T.__file__, encoding="utf-8") as fh:
        tops = {m.split(".")[0] for m in _imports(fh.read())}
    assert tops and tops <= set(sys.stdlib_module_names), tops - set(sys.stdlib_module_names)
    probe = ("import sys; sys.path.insert(0, sys.argv[1]); import mercury_app.testing; "
             "print(sorted(m for m in sys.modules if m.split('.')[0] in "
             "('pydantic', 'modules')))")
    done = subprocess.run([sys.executable, "-c", probe, SDK], capture_output=True, text=True,
                          timeout=60, cwd=SDK)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]", done.stdout


def test_what_an_apps_tests_may_import_from_it_is_published():
    assert A.TEST_ONLY[A.SDK_TESTING] <= set(T.__all__)
    assert "modules.jobs" not in A.TEST_ONLY


# ── the same answers as modules.jobs.testing on the same inputs ─────────────────────────────

def outcome(call, *args, **kwargs):
    """What *call* answered: `("ok", value)` or `("raised", class name, message, what,
    problems)`, so two implementations' answers compare whole."""
    try:
        return ("ok", call(*args, **kwargs))
    except Exception as exc:                # noqa: BLE001 - every refusal is compared
        return ("raised", type(exc).__name__, str(exc), getattr(exc, "what", None),
                getattr(exc, "problems", None))


@pytest.mark.parametrize("examples", [("a",), ("a", "b"), (), ("",), ("  ",), (1,),
                                      ("a", None)])
def test_covers_answers_as_the_job_sdks(examples):
    def test():
        return None
    ours, theirs = outcome(T.covers, *examples), outcome(AU.covers, *examples)
    if ours[0] == "ok":
        assert theirs[0] == "ok" and ours[1](test) is test and theirs[1](test) is test
    else:
        assert ours == theirs


def _block(expect, raise_):
    """`(what the block's exit did, what Raised.match then answered)`."""
    def run():
        with expect as raised:
            if raise_ is not None:
                raise raise_
        return raised.type.__name__, str(raised.value)
    return outcome(run)


@pytest.mark.parametrize("kind, match, raise_", [
    (ValueError, None, None),
    (ValueError, None, ValueError("the value")),
    (ValueError, "val", ValueError("the value")),
    (ValueError, "^nothing", ValueError("the value")),
    ((ValueError, KeyError), None, KeyError("k")),
    (ValueError, None, KeyError("another")),
    (LookupError, "no fixture", LookupError("no fixture named 'x'")),
])
def test_refused_answers_as_the_job_sdks(kind, match, raise_):
    ours = _block(T.refused(match=match, kind=kind), raise_)
    theirs = _block(AU.refused(match=match, kind=kind), raise_)
    assert ours == theirs


@pytest.mark.parametrize("kind", [int, (), "ValueError", (ValueError, 1)])
def test_refused_refuses_what_is_not_an_exception_class_as_the_job_sdks(kind):
    assert outcome(T.refused, kind=kind) == outcome(AU.refused, kind=kind)


def test_refused_by_default_catches_each_sdks_own_contract_error_in_the_same_words():
    assert _block(T.refused(), T.ContractError("the thing", ["a", "b"])) == \
        _block(AU.refused(), J.ContractError("the thing", ["a", "b"]))
    assert _block(T.refused(), None) == _block(AU.refused(), None)
    ours, theirs = T.ContractError("w", ["p1", "p2"]), J.ContractError("w", ["p1", "p2"])
    assert (str(ours), ours.what, ours.problems) == (str(theirs), theirs.what, theirs.problems)
    assert isinstance(ours, ValueError)


def test_raised_match_answers_as_the_job_sdks():
    ours, theirs = T.Raised(), AU.Raised()
    ours.value = theirs.value = ValueError("the refusal")
    for regex in ("refusal", "^nothing"):
        assert outcome(ours.match, regex) == outcome(theirs.match, regex)
    assert outcome(T.Raised().match, "x") == outcome(AU.Raised().match, "x")


class _Scoped(Job):
    meta = JobMeta(name="scoped-read", version="1.0.0", summary="A planted read job.",
                   permission="read", scope=Scope(object_types=["dcim.device"], roles=[]))

    def run(self, ctx, inputs):
        return None


class _Other(Job):
    meta = JobMeta(name="other-read", version="1.0.0", summary="Another planted read job.",
                   permission="read", scope=Scope(object_types=["ipam.prefix"], roles=[]))

    def run(self, ctx, inputs):
        return None


def _module(name, defined=None, imported=None):
    """A folder's module *name*: the classes *defined* in it (each a subclass of the one
    given, defined in this module), and the values *imported* into it as they are."""
    module = types.ModuleType(name)
    for key, base in (defined or {}).items():
        setattr(module, key, type(key, (base,), {"__module__": name}))
    for key, value in (imported or {}).items():
        setattr(module, key, value)
    return module


#: Each folder's modules, as pytest would import them.
FOLDERS = {
    "an app's": [_module("dns_overrides", imported={"decide": lambda config, event: "ask"})],
    "an empty": [],
    "two jobs'": [_module("job", defined={"A": _Scoped, "B": _Other})],
    "a job imported, not defined": [_module("helper", imported={"Imported": _Scoped})],
}


def _answer(value):
    """A fixture's value as compared: the recorded Ryu by its answers, anything else whole."""
    if isinstance(value, T.RecordedRyu):
        return ("RecordedRyu", {p: value.get(p) for p in value.paths})
    return value


@pytest.mark.parametrize("folder", sorted(FOLDERS))
@pytest.mark.parametrize("name", ["ctx", "ryu", "netbox", "flows", ""])
def test_a_fixture_by_name_answers_as_the_job_sdks(folder, name):
    ours = outcome(T.fixture_for, name, FOLDERS[folder])
    theirs = outcome(J.fixture_for, name, FOLDERS[folder])
    assert ours[0] == theirs[0]
    if ours[0] == "ok":
        assert _answer(ours[1]) == _answer(theirs[1])
    else:
        assert ours == theirs


def test_job_class_in_answers_as_the_job_sdks():
    one = [_module("job", defined={"Only": _Scoped})]
    assert T.job_class_in(one) is J.job_class_in(one) is one[0].Only
    for modules in FOLDERS.values():
        assert outcome(T.job_class_in, modules) == outcome(J.job_class_in, modules)


def test_ctx_given_a_job_is_the_one_answer_that_differs_and_says_why():
    """By design: a job's plan-mode context is built on Mercury's Python; an app has none."""
    assert isinstance(J.ctx(_Scoped), J.FakeContext)
    got = outcome(T.ctx, _Scoped)
    assert got[:2] == ("raised", "ContractError")
    assert got[2] == ("the fixture ctx refused: a job's plan-mode context is "
                      "modules.jobs.testing's, on Mercury's Python; an app's tests take ryu "
                      "and netbox")
    one = [_module("job", defined={"Only": _Scoped})]
    assert outcome(T.fixture_for, "ctx", one) == got
    for job in (None, "a job", 7):
        assert outcome(T.ctx, job) == outcome(J.ctx, job)


DEVICES = {"dcim.device": [{"id": 1, "name": "sw1", "role": "openflow-switch"},
                           {"id": 2, "name": "sw2", "role": "core"}],
           "ipam.prefix": [{"id": 9, "prefix": "192.0.2.0/24"},
                           {"id": 10, "prefix": "2001:db8::/32"}]}


@pytest.mark.parametrize("job", [None, _Scoped, _Scoped.meta, "a job", 3])
@pytest.mark.parametrize("objects", [None, {}, DEVICES])
def test_netbox_answers_as_the_job_sdks(job, objects):
    ours, theirs = outcome(T.netbox, job, objects), outcome(J.netbox, job, objects)
    assert ours[0] == theirs[0]
    if ours[0] != "ok":
        assert ours == theirs
        return
    calls = [("get", ("dcim.device",), {}), ("get", ("dcim.device",), {"role": "core"}),
             ("get", ("dcim.cable",), {}), ("one", ("dcim.device", 2), {}),
             ("one", ("dcim.device", 5), {}), ("get", ("ipam.prefix",), {}),
             ("one", ("ipam.prefix", 10), {})]
    for method, args, kwargs in calls:
        assert outcome(getattr(ours[1], method), *args, **kwargs) == \
            outcome(getattr(theirs[1], method), *args, **kwargs), (method, args, kwargs)


def test_a_scoped_netbox_refuses_outside_the_jobs_scope_in_the_job_sdks_words():
    got = outcome(T.netbox(_Scoped, DEVICES).get, "ipam.prefix")
    assert got[:2] == ("raised", ScopeError.__name__)
    assert got == outcome(J.netbox(_Scoped, DEVICES).get, "ipam.prefix")


def test_the_fixtures_offered_are_the_job_sdks():
    assert sorted(T.FIXTURES) == sorted(J.FIXTURES)
    assert outcome(T.fixture, "flows", None) == outcome(J.fixture, "flows", None)


# ── the recorded Ryu: one parser, the same answers ───────────────────────────────────────────

@pytest.mark.parametrize("capture", [R.CAPTURE, R.HARNESS], ids=["capture", "harness"])
def test_the_recorded_ryu_answers_as_the_job_fixtures(capture):
    ours, theirs = T.RecordedRyu(capture), R.RecordedRyu(capture)
    assert isinstance(theirs, T.RecordedRyu)
    assert ours.paths == theirs.paths and len(ours.paths) >= 5
    for path in ours.paths:
        assert ours.get(path) == theirs.get(path)
    dpids = ours.dpids()
    assert dpids and dpids == theirs.dpids()
    for method, path in (("GET", "/stats/flow/1"), ("POST", "/stats/switches")):
        assert outcome(ours.answer, method, path) == outcome(theirs.answer, method, path)
    assert ours.sent == theirs.sent


def test_the_sdks_recordings_are_the_job_fixtures():
    assert os.path.normpath(T.CAPTURE) == os.path.normpath(R.CAPTURE)
    assert os.path.normpath(T.HARNESS) == os.path.normpath(R.HARNESS)
    assert _answer(T.ryu()) == _answer(J.ryu())


@pytest.mark.parametrize("text", ["### flows 4\n[]\n", "### switches\n[1, \n",
                                  "### desc x\n{}\n", "[1]\n"])
def test_a_malformed_capture_is_refused_naming_its_line(text):
    got = outcome(T.parse_capture, text)
    assert got[:2] == ("raised", "ValueError") and got[2].startswith("line ")


# ── the conftest `mercury app new` writes, and a job's ───────────────────────────────────────

def _imports(text):
    tree = ast.parse(text)
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.add(node.module)
    return out


def test_the_app_conftest_imports_no_mercury_module_but_mercury_app():
    conftest = S.files("app", name="new_app", blank=True)["conftest.py"]
    assert conftest == S.template("app_conftest.py.template")
    assert _imports(conftest) == {"importlib", "os", "pytest", "mercury_app"}
    stub = S.files("app", name="new_app", blank=True)["test_app.py"]
    mercury = {m for m in _imports(stub) if m.split(".")[0] in ("modules", "mercury_app")}
    assert mercury == {A.SDK_TESTING}


def test_a_jobs_conftest_is_unchanged():
    """It passes on the parent too, by design: the split must leave a job's conftest the one
    on Mercury's Python, through modules.jobs.testing (its control: `job new` written from
    the app's template fails it)."""
    conftest = S.files("job", name="new-job", blank=True)["conftest.py"]
    assert conftest == S.template("conftest.py.template")
    assert "modules.jobs" in _imports(conftest) and "mercury_app" not in _imports(conftest)
    assert "testing.fixture_for(name, _modules())" in conftest


def test_the_app_conftest_runs_under_pytest_with_the_sdk_alone(tmp_path):
    """The worked app, its conftest the one `app new` writes, and a test asking for `ryu`, run
    by pytest with only the app SDK's folder on the path: Mercury's modules are not reachable
    (the run's working folder and path hold neither the checkout nor its tests)."""
    folder = tmp_path / "dns_overrides"
    folder.mkdir()
    for path in tracked(os.path.relpath(APP_FIXTURE, ROOT), suffix=".py"):
        with open(path, encoding="utf-8") as fh:
            (folder / os.path.basename(path)).write_text(fh.read(), encoding="utf-8")
    (folder / "test_fixture.py").write_text(
        "def test_ryu_is_the_recording(ryu):\n    assert ryu.dpids()\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONSTARTUP")}
    env.update(PYTHONPATH=SDK, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1")
    probe = ("import importlib.util, sys; "
             "sys.exit(importlib.util.find_spec('modules') is not None)")
    assert subprocess.run([sys.executable, "-c", probe], cwd=str(folder), env=env,
                          timeout=60).returncode == 0
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "--rootdir", str(folder), str(folder)], cwd=str(folder), env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "6 passed" in done.stdout, done.stdout
