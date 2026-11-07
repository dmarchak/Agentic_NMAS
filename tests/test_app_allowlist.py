"""T27, the app allowlist (C2635; the SDN platform design revision 7, section 11c.6; the operator,
2026-11-07): `modules/apps/allowlist.py`, separate from the job allowlist, and the app gate
(`modules/apps/gate.py`) that runs no app code.

Each rule planted: `import ryu` accepted for an app and refused for a job; a network, process,
file or interpreter module refused for an app, named; a refused name of an allowed module
refused; an egress call to an undeclared destination, a computed one, or `egress` used as a
value refused, and a declared one accepted and listed for the reviewer; code that is not
Python 3.9 refused; and the app gate executing nothing of the app's (a planted test that would
log if it ran is never run, and the runner and the mutation engine are never called).

No address is parsed here: an egress destination is a name, its address the network's config
(the manifest's tests cover its key, tests/test_app_manifest.py)."""

import ast
import logging
import os
import shutil

import pytest
import yaml

from modules.apps import allowlist as A
from modules.apps import gate as app_gate
from modules.jobs import gate as job_gate
from modules.jobs import mutate, runner
from modules.jobs import scaffold as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS = os.path.join(ROOT, "tests", "fixtures", "apps")
APP = "dns_overrides"
STUB = os.path.join(ROOT, "modules", "apps", "sdk", "mercury_app", "__init__.py")
DECLARED = ("verdict_service",)


def sources(code: str = "", test: str = "", module: str = "app") -> runner.Sources:
    """A folder's sources in memory: *code* as `<module>.py`, *test* as `test_app.py`."""
    return runner.Sources(folder="planted", job={module: code} if code else {},
                          tests={"test_app.py": test} if test else {})


def problems(code: str = "", test: str = "", declared=DECLARED) -> list:
    return A.check(sources(code, test), declared).problems


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ── imports: ryu for an app, never for a job ─────────────────────────────────────────────────

RYU_APP = '''from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import ethernet, packet
from ryu.ofproto import ofproto_v1_3
import collections.abc
import logging
import time

LOG = logging.getLogger(__name__)


class App(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(App, self).__init__(*args, **kwargs)
        self.seen = collections.abc.Mapping
        self.worker = hub.spawn(self.loop)

    def loop(self):
        while True:
            hub.sleep(time.monotonic() % 1)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in(self, ev):
        pkt = packet.Packet(ev.msg.data)
        LOG.info("from %s", pkt.get_protocol(ethernet.ethernet))
'''


def test_a_ryu_app_is_allowed_for_an_app_and_refused_for_a_job():
    assert problems(RYU_APP) == []
    job = job_gate.static_problems(sources(RYU_APP))
    assert "app.py line 1: `from ryu.base import ...` is not allowed: a job imports its own " \
           "modules" in job[0]
    assert any("`from ryu.lib import ...` is not allowed" in p for p in job)


@pytest.mark.parametrize("line, words", [
    ("import socket", "`import socket`: `socket` is refused: a network module"),
    ("import ssl", "`import ssl`: `ssl` is refused: a network module"),
    ("import urllib.request", "`import urllib.request`: `urllib.request` is refused: a network "
                              "module"),
    ("from urllib import request", "`from urllib import ...`: `urllib` is refused: a network "
                                   "module"),
    ("from http import client", "`from http import ...`: `http` is refused: a network module"),
    ("import requests", "`import requests`: `requests` is refused: a network module"),
    ("import subprocess", "`import subprocess`: `subprocess` is refused: a process or thread "
                          "module"),
    ("import threading", "`import threading`: `threading` is refused: a process or thread "
                         "module"),
    ("import os", "`import os`: `os` is refused: a file or operating-system module"),
    ("from os import system", "`from os import ...`: `os` is refused: a file or "
                              "operating-system module"),
    ("import importlib", "`import importlib`: `importlib` is refused: it reaches the "
                         "interpreter's internals"),
    ("import csv", "`import csv`: `csv` is not on the app allowlist"),
    ("import json.decoder", "`import json.decoder`: `json.decoder` is refused: the app "
                            "allowlist allows json itself, not its submodules"),
    ("import logging.handlers", "`import logging.handlers`: `logging.handlers` is refused: it "
                                "writes files and sends to sockets"),
    ("from ryu import services", "`from ryu import services`: `ryu.services` is refused: "
                                 "protocol speakers"),
    ("import ryu.lib.ovs.vsctl", "`import ryu.lib.ovs.vsctl`: `ryu.lib.ovs.vsctl` is refused: "
                                 "it connects to an OVSDB server itself"),
    ("from ryu.lib.hub import StreamServer", "`from ryu.lib.hub import StreamServer`: "
                                             "`ryu.lib.hub.StreamServer` is refused: it opens a "
                                             "connection"),
    ("from logging import FileHandler", "`from logging import FileHandler`: "
                                        "`logging.FileHandler` is refused: it writes a file"),
    ("from json import _default_encoder", "`json._default_encoder` is refused: a private name "
                                          "of json"),
    ("from mercury_app import secret", "`mercury_app.secret` is not among mercury_app's "
                                       "published names"),
    ("from . import helper", "a relative import"),
    ("from json import *", "`from json import *` hides what is imported"),
    ("from modules.jobs import covers", "modules.jobs is for the app's tests, not its code"),
    ("from modules.nsot.repo import list_goldens", "an app imports no Mercury module"),
])
def test_a_refused_import_is_named_with_its_file_line_and_why(line, words):
    got = problems(f"\n{line}\n")
    assert len(got) == 1, got
    assert got[0].startswith("app.py line 2: ") and words in got[0], got


@pytest.mark.parametrize("code, words", [
    ("from ryu.lib import hub\nhub.connect(('x', 1))\n",
     "`ryu.lib.hub.connect` is refused: it opens a connection"),
    ("import ryu.lib.hub\nryu.lib.hub.listen(('x', 1))\n",
     "`ryu.lib.hub.listen` is refused: it opens a connection"),
    ("import logging\nlogging.basicConfig(filename='x')\n",
     "`logging.basicConfig` is refused: it can open a file"),
    ("import uuid\nuuid.getnode()\n", "`uuid.getnode` is refused: it reads the host's hardware"),
    ("import json\njson._default_decoder\n", "`json._default_decoder` is refused: a private "
                                             "name of json"),
    ("import json\nx = json\n", "the module `json` used as a value"),
    ("open('/etc/passwd')\n", "`open` is not allowed: an app reaches the network only by "
                              "mercury_app.egress, reads no file"),
    ("eval('1')\n", "`eval` is not allowed"),
    ("exec('1')\n", "`exec` is not allowed"),
    ("getattr(1, 'real')\n", "`getattr` is not allowed"),
    ("x = (1).__class__\n", "the attribute `.__class__` is not allowed"),
    ("try:\n    pass\nexcept:\n    pass\n", "`except:` is not allowed"),
])
def test_a_refused_use_of_an_allowed_module_or_builtin_is_named(code, words):
    got = problems(code)
    assert len(got) == 1 and words in got[0], got
    assert got[0].startswith("app.py line ")


def test_the_tests_alone_take_pytest_raises_and_covers():
    test = ("import pytest\nfrom app import decide\nfrom modules.jobs import covers, refused\n\n\n"
            "@covers('x')\ndef test_x():\n    with pytest.raises(ValueError):\n"
            "        decide()\n")
    assert problems("def decide():\n    raise ValueError()\n", test) == []
    got = problems("", "from modules.jobs.testing import plan_run\nimport pytest\n"
                       "pytest.fixture\n")
    assert any("test_app.py line 1: `from modules.jobs.testing import ...`: an app imports no "
               "Mercury module" in p for p in got), got
    assert any("test_app.py line 3: `pytest.fixture`: the runner's pytest offers raises alone"
               in p for p in got), got


def test_an_app_module_named_like_an_import_is_refused():
    got = A.check(runner.Sources("planted", {"ryu": "x = 1\n"}, {}), DECLARED).problems
    assert got == ["ryu.py: an app's module is named like one it may import or is refused "
                   "('ryu'); name it for the app"]


def test_every_module_the_table_allows_is_imported_clean_and_every_other_refused():
    """The table read whole: each allowed entry imports without a problem; each refused one
    is refused by name, with its reason."""
    assert len(A.IMPORTS) >= 60, "the table reads almost nothing"
    for module, rule in A.IMPORTS.items():
        got = problems(f"import {module}\n")
        if rule.allowed:
            assert got == [], (module, got)
        else:
            assert len(got) == 1 and f"`{module}` is refused: {rule.why}" in got[0], got


# ── egress: only to a destination the manifest declares ──────────────────────────────────────

@pytest.mark.parametrize("code", [
    "from mercury_app import egress\negress('verdict_service', 'POST', '/verdict', {}, 0.5)\n",
    "from mercury_app import egress\negress(destination='verdict_service')\n",
    "import mercury_app\nmercury_app.egress('verdict_service')\n",
    "from mercury_app import egress as ask\nask('verdict_service')\n",
])
def test_an_egress_call_to_a_declared_destination_is_allowed_and_listed(code):
    found = A.check(sources(code), DECLARED)
    assert found.problems == []
    assert found.egress == ["app.py line 2: egress to 'verdict_service'"]


@pytest.mark.parametrize("code, words", [
    ("from mercury_app import egress\negress('elsewhere')\n",
     "an egress call to 'elsewhere', which is not a destination the manifest declares "
     "(manifest.yml declares 'verdict_service')"),
    ("from mercury_app import egress\nname = 'verdict_service'\negress(name)\n",
     "an egress call's destination is `name`, not a string literal naming a declared "
     "destination"),
    ("from mercury_app import egress\negress(f'verdict_{1}')\n",
     "an egress call's destination is `f'verdict_{1}'`, not a string literal"),
    ("from mercury_app import egress\negress()\n", "an egress call names no destination"),
    ("from mercury_app import egress\nask = egress\nask('verdict_service')\n",
     "`egress` used as a value (passed, stored or wrapped)"),
    ("import functools\nfrom mercury_app import egress\n"
     "ask = functools.partial(egress, 'verdict_service')\n", "`egress` used as a value"),
    ("import mercury_app\nsdk = mercury_app\n", "the module `mercury_app` used as a value"),
])
def test_an_undeclared_or_computed_egress_is_refused(code, words):
    got = problems(code)
    assert len(got) == 1 and words in got[0], got


def test_egress_reached_through_the_apps_own_module_is_refused():
    found = A.check(runner.Sources("planted", {
        "helper": "from mercury_app import egress\n",
        "app": "from helper import egress\nimport helper\nhelper.egress('verdict_service')\n"},
        {}), DECLARED)
    assert found.problems == [
        "app.py line 1: `from helper import egress`: mercury_app.egress is imported from "
        "mercury_app itself, where each call is read",
        "app.py line 3: `.egress` reached through the app's own module: mercury_app.egress is "
        "called from mercury_app itself, where each call is read"]


def test_with_the_manifest_refused_no_destination_is_declared():
    got = problems("from mercury_app import egress\negress('verdict_service')\n",
                   declared=None)
    assert got == ["app.py line 2: an egress call to 'verdict_service', which is not a "
                   "destination the manifest declares (manifest.yml is refused, so it declares "
                   "no destination)"]


# ── Python 3.9 ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code, words", [
    ("match x:\n    case 1:\n        pass\n", "Pattern matching is only supported in Python "
                                              "3.10"),
    ("try:\n    pass\nexcept* ValueError:\n    pass\n", "Exception groups are only supported"),
    ("type X = int\n", "Type statement is only supported"),
    ("def f[T](x: T) -> T:\n    return x\n", "Type parameter lists are only supported"),
])
def test_code_the_controllers_python_cannot_parse_is_refused(code, words):
    got = problems(code)
    assert len(got) == 1, got
    assert got[0].startswith("app.py line "), got
    assert ": does not parse as Python 3.9, the controller's interpreter (" in got[0], got
    assert words in got[0], got
    assert job_gate.static_problems(sources(code)) == [], "a job runs on Mercury's own Python"


def test_a_test_file_is_held_to_python_3_9_too():
    got = problems("", "match x:\n    case 1:\n        pass\n")
    assert got and got[0].startswith("test_app.py line 3: does not parse as Python 3.9")


def test_python_3_9_syntax_is_allowed():
    assert problems("if (n := len('ab')) > 1:\n    x = {} | {}\n") == []


# ── the SDK's contract stub ─────────────────────────────────────────────────────────────────

def test_the_sdk_stub_publishes_the_names_the_allowlist_accepts_and_parses_as_3_9():
    tree = ast.parse(read(STUB), feature_version=A.PYTHON)
    published = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                     and n.targets[0].id == "__all__")
    assert set(ast.literal_eval(published)) == A.SDK_NAMES


def test_the_sdk_stub_reaches_nothing():
    from modules.apps.sdk import mercury_app

    with pytest.raises(mercury_app.NotDeployed, match="egress\\('verdict_service'\\) was "
                                                      "called on the contract stub"):
        mercury_app.egress("verdict_service", "POST", "/verdict", {"domain": "x"}, 0.5)
    assert issubclass(mercury_app.EgressRefused, Exception)


# ── the authoring guide ─────────────────────────────────────────────────────────────────────

def test_the_guide_holds_the_allowlist_table_exactly_as_generated():
    guide = S.authoring_text()
    begin = guide.index(S.ALLOWLIST_BEGIN)
    end = guide.index(S.ALLOWLIST_END) + len(S.ALLOWLIST_END)
    assert guide[begin:end] == S.app_allowlist_markdown()
    for module in A.allowed_modules():
        assert f"| `{module}`" in guide[begin:end]


def test_the_guides_egress_example_passes_against_the_contract_fixtures_declaration():
    guide = S.authoring_text()
    start = guide.index("```python\nfrom mercury_app import egress")
    block = guide[start + len("```python\n"):guide.index("```", start + 3)]
    with open(os.path.join(APPS, "dns-blacklist", "manifest.yml"), encoding="utf-8") as fh:
        declared = tuple(e["name"] for e in yaml.safe_load(fh)["egress"])
    found = A.check(sources(block), declared)
    assert found.problems == [] and len(found.egress) == 1


# ── the gate: the manifest's destinations shown, and no app code run ─────────────────────────

def app_folder(tmp_path) -> str:
    """The worked app with one egress: its manifest declares the verdict service, and its
    module asks it."""
    folder = str(tmp_path / APP)
    shutil.copytree(os.path.join(APPS, APP), folder)
    path = os.path.join(folder, "manifest.yml")
    data = yaml.safe_load(read(path))
    data["config_schema"]["properties"]["verdict_service"] = {
        "type": "object", "properties": {"url": {"type": "string"}}}
    data["egress"] = [{"name": "verdict_service", "from_config": "verdict_service.url",
                       "purpose": "Asks the verdict service for a domain's verdict."}]
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)
    with open(os.path.join(folder, f"{APP}.py"), "a", encoding="utf-8") as fh:
        fh.write("\n\nfrom mercury_app import egress\n\n\ndef ask(name):\n"
                 "    return egress(\"verdict_service\", \"POST\", \"/verdict\", "
                 "{\"domain\": name})\n")
    return folder


def test_the_manifest_check_lists_each_declared_destination_and_static_each_call(tmp_path,
                                                                                capsys):
    folder = app_folder(tmp_path)
    verdict = app_gate.check(folder)
    manifest, static = verdict.check("manifest"), verdict.check("static")
    assert manifest.passed and manifest.details == (
        "egress 'verdict_service': to the address in the config's verdict_service.url: Asks "
        "the verdict service for a domain's verdict.",)
    assert static.passed and len(static.details) == 1
    assert static.details[0].startswith(f"{APP}.py line ")
    assert static.details[0].endswith(": egress to 'verdict_service'")
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("mercury_cli_allowlist",
                                                  os.path.join(ROOT, "scripts", "mercury"))
    cli = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(cli)
    assert cli.main(["app", "check", folder]) == 1
    out = capsys.readouterr().out
    assert f"  - {manifest.details[0]}\n" in out and f"  - {static.details[0]}\n" in out


def test_an_egress_the_manifest_does_not_declare_fails_the_static_check(tmp_path):
    folder = app_folder(tmp_path)
    path = os.path.join(folder, f"{APP}.py")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n\ndef leak():\n    return egress(\"elsewhere\")\n")
    static = app_gate.check(folder).check("static")
    assert not static.passed and static.action == app_gate.ACTIONS["static"]
    assert len(static.details) == 1 and "egress call to 'elsewhere'" in static.details[0]


PLANTED = '''"""A test that logs if it is ever run: on import and in its body."""

import logging

logging.getLogger("planted.app").error("the app's test module was imported")

from dns_overrides import decide  # noqa: E402 - imported after the log line on purpose
from modules.jobs import covers  # noqa: E402


@covers("a blocked name is blocked even when it is also allowed")
def test_planted():
    logging.getLogger("planted.app").error("the app's test ran")
    assert decide({}, "x") == "ask"
'''


def test_the_app_gate_runs_no_app_code(tmp_path, monkeypatch, caplog):
    """A planted test that passes the app allowlist and logs if it is imported or run is
    never run; and the gate calls neither the runner nor the mutation engine."""
    folder = str(tmp_path / APP)
    shutil.copytree(os.path.join(APPS, APP), folder)
    os.mkdir(os.path.join(folder, "tests"))
    with open(os.path.join(folder, "tests", "test_planted.py"), "w", encoding="utf-8") as fh:
        fh.write(PLANTED)

    def never(*_args, **_kwargs):
        raise AssertionError("the app gate called the job sandbox")

    for owner, name in ((runner, "run"), (runner, "prepare"), (runner, "run_folder"),
                        (mutate, "run_mutants")):
        monkeypatch.setattr(owner, name, never)
    caplog.set_level(logging.DEBUG)
    verdict = app_gate.check(folder)
    assert [r.getMessage() for r in caplog.records if r.name == "planted.app"] == []
    assert verdict.check("static").passed, verdict.check("static").details
    assert "tests/test_planted.py::test_planted" in " ".join(
        verdict.check("examples").details), "the planted test was read, not run"
    for name in app_gate.HARNESS_CHECKS:
        check = verdict.check(name)
        assert not check.passed and check.summary == app_gate.HARNESS_NOT_RUN
        assert check.summary == "not run: app tests run in the container harness, which lands " \
                                "with P2a"
    assert verdict.run is None and verdict.mutation is None and not verdict.passed


def test_a_planted_test_that_writes_a_marker_never_writes_it(tmp_path):
    folder = str(tmp_path / APP)
    shutil.copytree(os.path.join(APPS, APP), folder)
    marker = tmp_path / "ran"
    with open(os.path.join(folder, "test_marker.py"), "w", encoding="utf-8") as fh:
        fh.write(f"def test_marker():\n    open({str(marker)!r}, 'w').write('ran')\n"
                 "    assert True\n")
    verdict = app_gate.check(folder)
    assert not marker.exists()
    assert not verdict.check("static").passed
    assert verdict.check("tests").summary == app_gate.HARNESS_NOT_RUN
