"""The container harness's compose file holds the operator's conditions (2026-11-06; the SDN
platform design revision 6, section 15: "tests/containers/compose.yml states each condition,
and a test reads the compose file and fails if one is missing").

The conditions, each checked here in the file (and on the running containers by
`scripts/nmas-harness`'s `verify`, which the harness's own run exercises):
1. one network, `internal: true` (no route off the machine), and every service on it alone;
2. no host networking (no `network_mode` at all);
3. no privileged container: `privileged: false`, `cap_drop: [ALL]`, no `cap_add`, no device,
   `no-new-privileges`, a read-only root filesystem;
4. Open vSwitch's userspace datapath: every bridge `datapath_type=netdev`, OVS's own dummy
   ports, no kernel datapath package in the image;
5. a published port only on 127.0.0.1.

Each condition's check is shown able to fail on a planted compose document. Also held here:
the interpreter is a parameter with no default (the compose file's `:?`, the Dockerfile's bare
`ARG`, the script's required `--python`), every measured version pins Ryu 4.34, the runner sees
only `modules/` and the harness's own folder (never `data/`), and the harness's checks are not
collected by the suite.
"""

import copy
import configparser
import importlib.machinery
import importlib.util
import os
import re

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "tests", "containers")
COMPOSE = os.path.join(HERE, "compose.yml")


def _read(*parts) -> str:
    with open(os.path.join(HERE, *parts), encoding="utf-8") as fh:
        return fh.read()


def compose() -> dict:
    return yaml.safe_load(_read("compose.yml"))


def condition_problems(doc: dict) -> list:
    """Every operator condition the compose document *doc* breaks, in words."""
    out = []
    networks = doc.get("networks") or {}
    if len(networks) != 1:
        out.append(f"condition 1: one network, not {sorted(networks)}")
    for name, net in networks.items():
        if (net or {}).get("internal") is not True:
            out.append(f"condition 1: network {name} is not internal: true")
    for name, svc in (doc.get("services") or {}).items():
        if sorted(svc.get("networks") or []) != sorted(networks):
            out.append(f"condition 1: {name} is on {svc.get('networks')}, not the harness "
                       f"network alone")
        if "network_mode" in svc:
            out.append(f"condition 2: {name} sets network_mode {svc['network_mode']!r}")
        if svc.get("privileged") is not False:
            out.append(f"condition 3: {name}'s privileged is {svc.get('privileged')!r}, not "
                       f"false")
        if svc.get("cap_drop") != ["ALL"] or svc.get("cap_add"):
            out.append(f"condition 3: {name} drops {svc.get('cap_drop')} and adds "
                       f"{svc.get('cap_add')}; ALL dropped and none added")
        if svc.get("devices"):
            out.append(f"condition 3: {name} maps devices {svc['devices']}")
        if "no-new-privileges:true" not in (svc.get("security_opt") or []):
            out.append(f"condition 3: {name} lacks no-new-privileges:true")
        if svc.get("read_only") is not True:
            out.append(f"condition 3: {name}'s root filesystem is not read_only")
        for port in svc.get("ports") or []:
            if not str(port).startswith("127.0.0.1:"):
                out.append(f"condition 5: {name} publishes {port!r}, not on 127.0.0.1")
    return out


def test_the_compose_file_holds_every_condition():
    doc = compose()
    assert sorted(doc["services"]) == ["ovs", "runner", "ryu"]
    assert condition_problems(doc) == []


@pytest.mark.parametrize("plant, words", [
    (lambda d: d["networks"]["harness"].__setitem__("internal", False),
     "condition 1: network harness is not internal: true"),
    (lambda d: d["networks"].__setitem__("outside", {}), "condition 1: one network"),
    (lambda d: d["services"]["ryu"].__setitem__("networks", ["harness", "outside"]),
     "condition 1: ryu is on"),
    (lambda d: d["services"]["ovs"].__setitem__("network_mode", "host"),
     "condition 2: ovs sets network_mode 'host'"),
    (lambda d: d["services"]["ovs"].__setitem__("privileged", True),
     "condition 3: ovs's privileged is True"),
    (lambda d: d["services"]["ovs"].pop("privileged"), "condition 3: ovs's privileged is None"),
    (lambda d: d["services"]["ovs"].__setitem__("cap_add", ["NET_ADMIN"]),
     "condition 3: ovs drops ['ALL'] and adds ['NET_ADMIN']"),
    (lambda d: d["services"]["ryu"].__setitem__("cap_drop", ["NET_RAW"]),
     "condition 3: ryu drops ['NET_RAW']"),
    (lambda d: d["services"]["ovs"].__setitem__("devices", ["/dev/net/tun"]),
     "condition 3: ovs maps devices"),
    (lambda d: d["services"]["runner"].__setitem__("security_opt", []),
     "condition 3: runner lacks no-new-privileges"),
    (lambda d: d["services"]["ryu"].__setitem__("read_only", False),
     "condition 3: ryu's root filesystem is not read_only"),
    (lambda d: d["services"]["ryu"].__setitem__("ports", ["8080:8080"]),
     "condition 5: ryu publishes '8080:8080'"),
    (lambda d: d["services"]["ryu"].__setitem__("ports", ["0.0.0.0:8080:8080"]),
     "condition 5: ryu publishes '0.0.0.0:8080:8080'"),
])
def test_each_condition_is_found_missing_in_a_planted_file(plant, words):
    doc = copy.deepcopy(compose())
    plant(doc)
    assert any(p.startswith(words) for p in condition_problems(doc)), condition_problems(doc)


def test_a_published_port_on_loopback_passes():
    doc = copy.deepcopy(compose())
    doc["services"]["ryu"]["ports"] = ["127.0.0.1:18080:8080"]
    assert condition_problems(doc) == []


# ───────────────────────────────────────────────────────────── condition 4: the userspace datapath

def _lines(text: str) -> list:
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def test_every_bridge_is_made_on_the_userspace_datapath_and_checked():
    start = _read("ovs", "ovs-start")
    add_br = [line for line in _lines(start) if line.startswith("$VSCTL add-br ")]
    assert len(add_br) == 1 and "set bridge \"$a\" datapath_type=netdev" in add_br[0]
    assert re.search(r'^\s*if \[ "\$kind" != netdev \]; then$', start, re.M)
    assert [line for line in _lines(start) if line.startswith("ovs-vswitchd ")] == [
        'ovs-vswitchd "unix:$RUN/db.sock" --enable-dummy=override '
        '--pidfile="$RUN/ovs-vswitchd.pid" \\']
    assert "datapath_type" not in _read("ovs", "bridges.conf").replace(
        "datapath_type=netdev", "")


def test_the_switch_image_installs_no_kernel_datapath():
    docker = _read("ovs", "Dockerfile")
    installs = re.findall(r"apt-get install[^\n]*", docker)
    assert installs == ["apt-get install -y --no-install-recommends openvswitch-switch \\"]
    assert not re.search(r"dkms|datapath|dpdk|modprobe|insmod", docker.replace(
        "datapath_type=netdev", "").replace("USERSPACE datapath", "").replace(
        "kernel datapath's", ""), re.I)


# ───────────────────────────────────────────────────────────── the interpreter, never a constant

def _script():
    path = os.path.join(ROOT, "scripts", "nmas-harness")
    loader = importlib.machinery.SourceFileLoader("nmas_harness_under_test", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_up_waits_for_every_bridge_before_reading_the_conditions_on_them(tmp_path):
    """CI #1518 (2026-11-07, Python 3.5): `verify` read bridge br3 before OVS's start script had
    made it (`no row "br3" in table Bridge`). `up` waits for every bridge's controller
    connection first, then reads the conditions on the running containers."""
    import types

    harness = _script()
    order = []
    harness.check_python = lambda python: python
    harness.compose_env = lambda python, apps: {}
    harness.compose = lambda env, *a: order.append(("compose",) + a[:1]) or 0
    harness.wait_ready = lambda: order.append(("wait_ready",)) or 1.0
    harness.verify = lambda python: order.append(("verify",)) or []
    harness.say = lambda words: None
    harness.up(types.SimpleNamespace(python="3.5", apps=str(tmp_path), command="up"))
    assert order.index(("wait_ready",)) < order.index(("verify",)), order


def test_the_interpreter_has_no_default_anywhere():
    text = _read("compose.yml")
    assert re.findall(r"\$\{HARNESS_PYTHON[^}]*\}", text) and \
        all(m.startswith("${HARNESS_PYTHON:?") for m in re.findall(r"\$\{HARNESS_PYTHON[^}]*\}",
                                                                   text))
    docker = _read("ryu", "Dockerfile")
    assert re.findall(r"^ARG PYTHON.*$", docker, re.M) == ["ARG PYTHON", "ARG PYTHON"]
    assert re.findall(r"^FROM .*$", docker, re.M) == ["FROM python:${PYTHON}-slim"]
    harness = _script()
    with pytest.raises(SystemExit):
        harness.parse(["up"])
    assert harness.parse(["up", "--python", "3.5"]).python == "3.5"


@pytest.mark.parametrize("given, words", [
    ("3.7", "no measured constraints for Python 3.7: the harness builds Ryu 4.34 on 3.5, 3.9"),
    ("3", "--python is the controller's Python as major.minor (such as 3.5), not '3'"),
    ("", "--python is the controller's Python as major.minor"),
])
def test_a_version_without_measured_constraints_is_refused_naming_both(given, words):
    harness = _script()
    with pytest.raises(harness.Stop) as refused:
        harness.check_python(given)
    assert str(refused.value).startswith(words)


@pytest.mark.parametrize("version", ["3.5", "3.9"])
def test_each_measured_version_pins_ryu_434_and_its_eventlet(version):
    pins = dict(line.split("==") for line in _lines(_read("ryu", f"constraints-{version}.txt")))
    assert pins["ryu"] == "4.34" and pins["eventlet"] == "0.30.2"
    assert {"pip", "setuptools"} <= set(pins)


# ───────────────────────────────────────────────────────────── what the runner sees, what runs

def test_no_container_mounts_anything_but_the_code_and_the_harness_folder():
    sources = {}
    for name, svc in compose()["services"].items():
        for volume in svc.get("volumes") or []:
            sources.setdefault(name, []).append(volume.split(":")[0])
    assert sources == {"runner": ["../../modules", "./"],
                       # the `:?` message follows the colon; the SDK beside the apps (C2852)
                       "ryu": ["${HARNESS_APPS", "../../modules/apps/sdk"]}
    sdk = [v for v in compose()["services"]["ryu"]["volumes"] if "mercury-sdk" in v]
    assert sdk == ["../../modules/apps/sdk:/opt/mercury-sdk:ro"], "read-only, the SDK alone"
    assert "PYTHONPATH=/opt/mercury-sdk" in _read("ryu", "ryu-start")
    text = _read("compose.yml")
    assert "data/" not in text and "key.key" not in text


def test_the_harness_checks_are_not_collected_by_the_suite():
    ini = configparser.ConfigParser()
    ini.read(os.path.join(ROOT, "pytest.ini"))
    assert ini["pytest"]["python_files"].strip() == "test_*.py"
    assert sorted(f for f in os.listdir(HERE) if f.endswith(".py")) == [
        "harness_checks.py", "record_answers.py"]


# ───────────────────────────────────────────────────────────── an app's test run (C2854)
#
# The app's own code runs in its test container (modules/apps/test_run.py), started by
# `docker run`, not by this compose file, so its conditions are held on the command it builds:
# the compose file's, and closer (no network at all where the harness's services share one
# internal network).

def run_problems(argv: list) -> list:
    """Every condition the test run's `docker run` argv *argv* breaks, in words."""
    out = []

    def values(flag):
        return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == flag]

    image_at = next((i for i, a in enumerate(argv) if a.startswith("mercury-harness-apptest:")),
                    len(argv))
    opts = argv[:image_at]
    other_network = [a for a in opts if a == "--net" or a.startswith(("--network=", "--net="))]
    if values("--network") != ["none"] or other_network:
        out.append(f"network: {values('--network')}, not none alone")
    for flag in ("-p", "--publish", "-P", "--publish-all", "--add-host", "--dns", "-v",
                 "--volume", "--volumes-from", "--device", "--cap-add", "--ipc", "--pid",
                 "--uts", "--userns", "--cgroupns", "--privileged", "--privileged=true"):
        if flag in opts or any(a.startswith(flag + "=") and a != "--privileged=false"
                               for a in opts):
            out.append(f"{flag} is given")
    if "--privileged=false" not in opts:
        out.append("--privileged=false is not given")
    if values("--cap-drop") != ["ALL"]:
        out.append(f"capabilities dropped {values('--cap-drop')}, not ALL")
    if values("--security-opt") != ["no-new-privileges:true"]:
        out.append(f"security options {values('--security-opt')}, not no-new-privileges:true")
    if "--read-only" not in opts:
        out.append("the root filesystem is writable (no --read-only)")
    users = values("--user")
    if len(users) != 1 or users[0].split(":")[0] in ("0", "root", ""):
        out.append(f"user {users}, not one unprivileged uid")
    if values("--tmpfs") != ["/tmp:size=16m"]:
        out.append(f"tmpfs {values('--tmpfs')}, not /tmp alone")
    mounts = values("--mount")
    if [m.split(",")[2] for m in mounts] != ["dst=/app", "dst=/opt/mercury-sdk"] or \
            any(not m.startswith("type=bind,") or not m.endswith(",readonly") for m in mounts):
        out.append(f"mounts {mounts}, not the app's folder and the SDK, each read-only")
    if "--rm" not in opts or values("--pull") != ["never"]:
        out.append("not a fresh container removed after (--rm, --pull never)")
    after = argv[image_at + 1:]
    if after[:4] != ["-B", "-m", "pytest", "-p"] or "no:cacheprovider" not in after or \
            "--" not in after:
        out.append(f"pytest's command {after[:6]} keeps a cache or bytecode")
    return out


def _run_argv(tmp_path):
    from modules.apps import test_run

    folder = tmp_path / "app"
    (folder / "tests").mkdir(parents=True)
    (folder / "tests" / "test_one.py").write_text("def test_one():\n    assert True\n")
    return test_run.docker_command(str(folder), "3.5", ["tests/test_one.py"],
                                   "mercury-apptest-0123456789ab")


def test_the_test_run_holds_every_condition(tmp_path):
    assert run_problems(_run_argv(tmp_path)) == []


#: The flags of the test run's command that take no value (the rest take one).
_BARE = ("--rm", "--read-only", "--privileged=false")


def _without(argv, flag):
    i = argv.index(flag)
    return argv[:i] + argv[i + (1 if flag in _BARE else 2):]


def _with(argv, *extra):
    return argv[:3] + list(extra) + argv[3:]


@pytest.mark.parametrize("plant, words", [
    (lambda a: _without(a, "--network"), "network: [], not none alone"),
    (lambda a: _with(a, "--network", "harness"), "network: ['harness', 'none']"),
    (lambda a: _with(a, "--network=host"), "network:"),
    (lambda a: _with(a, "-p", "127.0.0.1:8080:8080"), "-p is given"),
    (lambda a: _with(a, "-v", "/:/host"), "-v is given"),
    (lambda a: _with(a, "--device", "/dev/net/tun"), "--device is given"),
    (lambda a: _with(a, "--cap-add", "NET_ADMIN"), "--cap-add is given"),
    (lambda a: _with(a, "--privileged"), "--privileged is given"),
    (lambda a: _without(a, "--privileged=false"), "--privileged=false is not given"),
    (lambda a: _without(a, "--cap-drop"), "capabilities dropped [], not ALL"),
    (lambda a: _without(a, "--security-opt"), "security options [], not no-new-privileges"),
    (lambda a: _without(a, "--read-only"), "the root filesystem is writable"),
    (lambda a: _without(a, "--user"), "user [], not one unprivileged uid"),
    (lambda a: [("0:0" if x == "10001:10001" else x) for x in a], "user ['0:0']"),
    (lambda a: [x.replace(",readonly", "") for x in a], "mounts"),
    (lambda a: [x.replace("dst=/opt/mercury-sdk", "dst=/srv") for x in a], "mounts"),
    (lambda a: _without(a, "--tmpfs"), "tmpfs [], not /tmp alone"),
    (lambda a: _without(a, "--rm"), "not a fresh container"),
    (lambda a: [x for x in a if x != "no:cacheprovider"], "pytest's command"),
])
def test_each_test_run_condition_is_found_missing_in_a_planted_command(tmp_path, plant, words):
    argv = plant(list(_run_argv(tmp_path)))
    assert any(p.startswith(words) for p in run_problems(argv)), run_problems(argv)


def test_the_app_test_image_is_the_controllers_with_pytest_pinned_and_no_default_python():
    docker = _read("apptest", "Dockerfile")
    assert re.findall(r"^ARG PYTHON.*$", docker, re.M) == ["ARG PYTHON", "ARG PYTHON"]
    assert re.findall(r"^FROM .*$", docker, re.M) == ["FROM mercury-harness-ryu:4.34-py${PYTHON}"]
    installs = re.findall(r"pip install[^\n]*", docker)
    assert installs == ["pip install --no-cache-dir -c /etc/harness/constraints.txt pytest \\"]
    assert re.findall(r"^USER .*$", docker, re.M) == ["USER root", "USER 10001"]
    assert not re.search(r"apt-get|curl|wget|EXPOSE|VOLUME", docker)


@pytest.mark.parametrize("version, pytest_pin, measured", [
    ("3.5", "6.1.2", {"attrs": "22.1.0", "importlib-metadata": "2.1.3", "iniconfig": "1.1.1",
                      "packaging": "20.9", "pathlib2": "2.3.7.post1", "pluggy": "0.13.1",
                      "py": "1.11.0", "pyparsing": "2.4.7", "toml": "0.10.2", "zipp": "1.2.0",
                      "six": "1.17.0"}),
    ("3.9", "8.4.2", {"exceptiongroup": "1.3.1", "iniconfig": "2.1.0", "packaging": "26.3",
                      "pluggy": "1.6.0", "Pygments": "2.21.0", "tomli": "2.5.0",
                      "typing_extensions": "4.16.0"}),
])
def test_each_measured_version_pins_pytest_and_everything_it_resolved(version, pytest_pin,
                                                                      measured):
    """Every distribution pip installed beside pytest is pinned (measured 2026-11-09 by `pip
    freeze` before and after, the constraints file's comment), so the image's pytest is the
    one measured, never what an index serves later."""
    pins = dict(line.split("==") for line in _lines(_read("ryu", f"constraints-{version}.txt")))
    assert pins["pytest"] == pytest_pin
    assert {name: pins.get(name) for name in measured} == measured


def test_check_runs_the_app_test_run_after_the_harness_is_down(tmp_path):
    import types

    harness = _script()
    order = []
    harness.up = lambda args: order.append("up")
    harness.compose_env = lambda python, apps: {}
    harness.compose = lambda env, *a: order.append("checks") or 0
    harness.down = lambda: order.append("down")
    harness.app_test_selfcheck = lambda python: order.append(("app", python)) or []
    args = types.SimpleNamespace(python="3.9", apps=str(tmp_path), pytest=[])
    assert harness.check(args) == 0
    assert order == ["up", "checks", "down", ("app", "3.9")]


def _verdict(ok, failed=0, error=""):
    return {"ok": ok, "passed": 4, "failed": failed, "error": error, "seconds": 0.5,
            "python_seen": "3.5", "content_sha256": "ab" * 32, "output": ""}


def test_the_self_check_passes_only_when_the_worked_app_passes_and_its_broken_copy_fails():
    harness = _script()
    seen = []

    def answers(*verdicts):
        it = iter(verdicts)

        def test_app(folder, python):
            with open(os.path.join(folder, "test_app.py"), encoding="utf-8") as fh:
                seen.append((os.path.basename(folder), harness.WORKED_ASSERT in fh.read()))
            return next(it)
        return test_app

    harness.test_app = answers(_verdict(True), _verdict(False, 1, "pytest exited 1"))
    [line] = harness.app_test_selfcheck("3.5")
    assert line.startswith("app test run: the worked app passed 4 on Python 3.5")
    assert seen == [("dns_overrides", True), ("dns_overrides", False)], "the copy is broken"
    harness.test_app = answers(_verdict(False, 0, "no test ran"))
    with pytest.raises(harness.Stop, match="the worked app's tests did not pass on Python 3.5: "
                                           "no test ran"):
        harness.app_test_selfcheck("3.5")
    harness.test_app = answers(_verdict(True), _verdict(True))
    with pytest.raises(harness.Stop, match="with one assert broken did not fail one test"):
        harness.app_test_selfcheck("3.5")


def test_the_test_command_needs_a_python_and_an_app():
    harness = _script()
    with pytest.raises(SystemExit):
        harness.parse(["test", "--app", "x"])
    with pytest.raises(SystemExit):
        harness.parse(["test", "--python", "3.5"])
    args = harness.parse(["test", "--python", "3.5", "--app", "x"])
    assert (args.command, args.python, args.app) == ("test", "3.5", "x")
