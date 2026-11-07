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
                       "ryu": ["${HARNESS_APPS"]}  # the `:?` message follows the colon
    text = _read("compose.yml")
    assert "data/" not in text and "key.key" not in text


def test_the_harness_checks_are_not_collected_by_the_suite():
    ini = configparser.ConfigParser()
    ini.read(os.path.join(ROOT, "pytest.ini"))
    assert ini["pytest"]["python_files"].strip() == "test_*.py"
    assert sorted(f for f in os.listdir(HERE) if f.endswith(".py")) == [
        "harness_checks.py", "record_answers.py"]
