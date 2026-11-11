"""A controller taken as it is (C2985, C2986, C2675, C2983): the unit's own command line carried
by every deploy, the install's read of it, and the measured restart bounds.

The controller this was found on (the Lab 9 sitting, 2026-11-10), in neutral stand-ins: its
unit's drop-in `listen.conf` binds Ryu's REST to one address and loads two apps from
/opt/ryu-apps that Mercury does not manage (`unit_line`: the operator's read of the unit's
ExecStart, the addresses replaced). Cases, each planted, IPv6 beside IPv4:
- the apply script reads the unit's own command line from `systemctl cat` without Mercury's
  drop-in, keeps REST's bind, the other flags and the apps, and compares that with the
  request's ``keep``: a request that would drop or widen the bind is refused naming both, and
  nothing is written; a kept file an app of the request replaces is left out; a kept file that
  is not there, an argument that is not one plain word, and a drop-in read after Mercury's that
  sets ExecStart are refused;
- the script's restart bound runs on the monotonic clock: a wall clock that steps years forward
  during the wait (C2982) does not fire it;
- Mercury's plan carries the same, says each kept app and the REST bind in words, and refuses a
  drop-in after that would drop, widen or change the bind, or stop loading an app the unit
  loads now, naming both values; a bind to every address is rendered only when the unit
  already has one, and the plan says so;
- the post-check's two bounds are 2.5 times what was measured, each on its own clock: Ryu's
  start from the outcome's read, the switches' return from Ryu's first answer; each names what
  it read and waited for when it fires;
- the host step takes the unit's name alone, reads REST where it is bound, and makes every
  check before its first change."""

import hashlib
import json
import os
import re
from html import unescape

import pytest

from modules.apps import channel, deploy_op, post_check, transport
from tests.test_controller_apply import (HOST_STEP, MANAGER, UNIT, dropin, load, put_dropin,
                                         put_request, refused, run, stage_app)
from tests.test_controller_deploy import (ALL_BACK, EXPECTED, LISTEN, SWITCH_2_DOWN, Clock,
                                          enabled, eos, ls)
from tests.test_controller_deploy_op import (ALL_BACK_TWO, CTL, NET, FakeSources,  # noqa: F401
                                             _receipts_here)
from tests.test_controller_deploy_op import run as run_op
from tests.test_sdn_apps_v2 import apps, preview  # noqa: F401 - the fixture, and its preview
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture `apps` needs

#: Where REST is bound on the controller, one address of each family (documentation ranges).
REST_HOSTS = ["192.0.2.1", "2001:db8::1"]
LEGACY = "/opt/ryu-apps"


def unit_line(rest_host, folder=LEGACY, manager=MANAGER, listen="192.0.2.10"):
    """The unit's own ExecStart as the operator read it on the controller (2026-11-10), its
    addresses replaced by documentation ones."""
    return (f"{manager} --ofp-listen-host {listen} --ofp-tcp-listen-port 6653 "
            f"--wsapi-host {rest_host} --wsapi-port 8080 --observe-links ryu.app.ofctl_rest "
            f"ryu.app.rest_topology {folder}/of_versions.py {folder}/switch_quirks.py")


def cat_text(line, mercury="[Service]\nUser=ryu\n", root="/etc/systemd/system"):
    """`systemctl cat <unit>`: the unit file, the hand-made drop-in listen.conf that resets
    ExecStart and sets *line*, then Mercury's drop-in."""
    return (f"# /lib/systemd/system/{UNIT}\n[Unit]\nDescription=Ryu\n\n[Service]\n"
            f"ExecStart={MANAGER} ryu.app.simple_switch_13\n\n"
            f"# {root}/{UNIT}.d/listen.conf\n[Service]\nExecStart=\nExecStart={line}\n\n"
            f"# {root}/{UNIT}.d/mercury.conf\n{mercury}")


def show_text(line, user="ryu"):
    return (f"User={user}\nExecStart={{ path={MANAGER} ; argv[]={line} ; ignore_errors=no ; "
            "start_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }\n")


def kept_of(rest_host, folder=LEGACY):
    return {"rest": {"host": rest_host, "port": 8080},
            "apps": [f"{folder}/of_versions.py", f"{folder}/switch_quirks.py"]}


# ── the script: the unit's own command line ───────────────────────────────────────────────────

@pytest.mark.parametrize("rest_host", REST_HOSTS)
def test_the_unit_s_own_command_line_is_read_without_mercury_s_drop_in(tmp_path, rest_host):
    m = load(tmp_path)
    line = unit_line(rest_host)
    rendered = ("[Service]\nUser=ryu\nExecStart=\n"
                f"ExecStart={MANAGER} --observe-links ryu.app.ofctl_rest\n")
    got = m.unit_command(cat_text(line, mercury=rendered, root=m.DROPIN_ROOT), UNIT)
    assert got["argv"] == line.split() and got["later"] == []
    assert got["file"].endswith(f"{UNIT}.d/listen.conf")
    keep, listen = m.keep_from(got["argv"])
    assert keep == kept_of(rest_host)
    assert listen == {"host": "192.0.2.10", "port": "6653"}


def test_a_unit_with_nothing_but_mercury_s_own_keeps_nothing():
    s = channel.script()
    argv = [MANAGER, "--observe-links", "--ofp-listen-host", "192.0.2.10",
            "--ofp-tcp-listen-port", "6653", "ryu.app.ofctl_rest", "ryu.app.rest_topology"]
    assert s.keep_from(argv)[0] is None
    assert s.unit_command("", UNIT) == {"argv": None, "file": "", "later": []}


def test_other_flags_are_kept_with_their_values_in_the_unit_s_order():
    s = channel.script()
    keep, _ = s.keep_from([MANAGER, "--verbose", "--config-file", "/etc/ryu/ryu.conf",
                           "--wsapi-port=8081", "ryu.app.simple_switch_13"])
    assert keep == {"rest": {"port": 8081},
                    "flags": ["--verbose", "--config-file", "/etc/ryu/ryu.conf"],
                    "apps": ["ryu.app.simple_switch_13"]}


def kept_unit(tmp_path, rest_host, **kw):
    """The script on a controller whose unit binds REST to *rest_host* and loads two apps of
    its own (files that are there), its first drop-in installed, of_versions staged apart."""
    m = load(tmp_path, **kw)
    put_dropin(m)
    folder = tmp_path / "legacy"
    folder.mkdir()
    for name in ("of_versions", "switch_quirks"):
        (folder / f"{name}.py").write_bytes(f"# {name}\n".encode())
    m.systemctl.dropins["listen.conf"] = (
        f"[Service]\nExecStart=\nExecStart={unit_line(rest_host, folder=str(folder))}\n")
    return m, str(folder)


def request_for(m, apps_, keep=None):
    body = {"apps": apps_, "listen": {"host": "192.0.2.10", "port": 6653}}
    if keep is not None:
        body["keep"] = keep
    put_request(m, [], raw=json.dumps(body).encode())


@pytest.mark.parametrize("rest_host", REST_HOSTS)
def test_the_drop_in_carries_the_unit_s_rest_bind_and_its_apps(tmp_path, rest_host):
    m, folder = kept_unit(tmp_path, rest_host)
    sha = stage_app(m, name="fabric_forwarding", version="0.3.0",
                    files={"fabric_forwarding.py": b"x = 1\n"})
    request_for(m, [{"name": "fabric_forwarding", "version": "0.3.0", "sha256": sha}],
                keep=kept_of(rest_host, folder))
    out = run(m)
    assert out["ok"] is True, out
    managed = os.path.join(m.APPS_ROOT, "fabric_forwarding", "0.3.0", "fabric_forwarding.py")
    assert dropin(m).splitlines()[-1] == (
        f"ExecStart={MANAGER} --observe-links --ofp-listen-host 192.0.2.10 "
        f"--ofp-tcp-listen-port 6653 --wsapi-host {rest_host} --wsapi-port 8080 "
        f"{folder}/of_versions.py {folder}/switch_quirks.py {managed} "
        "ryu.app.ofctl_rest ryu.app.rest_topology")
    # What Ryu loaded that Mercury does not manage is on record, by its bytes.
    assert out["keep"] == kept_of(rest_host, folder)
    assert out["kept_files"] == [
        {"path": f"{folder}/{n}.py", "sha256": hashlib.sha256(f"# {n}\n".encode()).hexdigest()}
        for n in ("of_versions", "switch_quirks")]


@pytest.mark.parametrize("rest_host, wide", [("192.0.2.1", "0.0.0.0"), ("2001:db8::1", "::")])
@pytest.mark.parametrize("plant", ["dropped", "widened", "another address", "an app dropped"])
def test_a_request_that_would_drop_or_widen_the_bind_is_refused_naming_both(
        tmp_path, rest_host, wide, plant):
    m, folder = kept_unit(tmp_path, rest_host)
    sha = stage_app(m, name="fabric_forwarding", version="1.0.0",
                    files={"fabric_forwarding.py": b"x = 1\n"})
    keep = kept_of(rest_host, folder)
    if plant == "dropped":
        keep = None
    elif plant == "widened":
        keep["rest"]["host"] = wide
    elif plant == "another address":
        keep["rest"]["host"] = REST_HOSTS[0] if rest_host != REST_HOSTS[0] else "192.0.2.99"
    else:
        keep["apps"] = keep["apps"][:1]
    request_for(m, [{"name": "fabric_forwarding", "version": "1.0.0", "sha256": sha}],
                keep=keep)
    why = refused(m)
    assert "what the plan kept is not what the unit has, so nothing was written" in why
    # Both values: what the request carries, and what the script read of the unit itself.
    assert f'"host": "{rest_host}"' in why and f"{folder}/switch_quirks.py" in why
    assert ("the request carries nothing" in why) == (plant == "dropped")
    if plant == "widened":
        assert f'"host": "{wide}"' in why


def test_a_kept_file_an_app_of_the_request_replaces_is_left_out(tmp_path):
    m, folder = kept_unit(tmp_path, "192.0.2.1")
    sha = stage_app(m)                                   # Mercury's own of_versions 1.0.0
    request_for(m, [{"name": "of_versions", "version": "1.0.0", "sha256": sha}],
                keep=kept_of("192.0.2.1", folder))
    out = run(m)
    assert out["ok"] is True, out
    line = dropin(m).splitlines()[-1]
    assert f"{folder}/of_versions.py" not in line, "two apps of one name cannot load"
    assert f" {folder}/switch_quirks.py {m.APPS_ROOT}/of_versions/1.0.0/of_versions.py " in line
    assert [f["path"] for f in out["kept_files"]] == [f"{folder}/switch_quirks.py"]


def test_a_kept_app_s_file_that_is_not_there_is_refused_before_anything_is_written(tmp_path):
    m, folder = kept_unit(tmp_path, "192.0.2.1")
    os.remove(os.path.join(folder, "switch_quirks.py"))
    sha = stage_app(m, name="fabric_forwarding", version="0.3.0",
                    files={"fabric_forwarding.py": b"x = 1\n"})
    request_for(m, [{"name": "fabric_forwarding", "version": "0.3.0", "sha256": sha}],
                keep=kept_of("192.0.2.1", folder))
    why = refused(m)
    assert f"the kept app {folder}/switch_quirks.py cannot be read" in why
    assert "Ryu would not start with it" in why


@pytest.mark.parametrize("word", ['"--verbose"', "$OPTIONS", "%i", "a\\b", "'x'"],
                         ids=["quoted", "expanded", "specifier", "escaped", "single-quoted"])
def test_an_argument_that_is_not_one_plain_word_is_refused_by_its_position(tmp_path, word):
    m = load(tmp_path)
    put_dropin(m)
    m.systemctl.unit_file = f"[Service]\nExecStart={MANAGER} --observe-links {word}\n"
    sha = stage_app(m)
    put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": sha}])
    why = refused(m)
    assert f"argument 2 of {UNIT}'s ExecStart (/lib/systemd/system/{UNIT}) is not one plain " \
           "word" in why
    assert word not in why, "named by its position, never its text"


def test_a_drop_in_read_after_mercury_s_that_sets_execstart_is_refused(tmp_path):
    m = load(tmp_path)
    put_dropin(m)
    m.systemctl.dropins["zz-local.conf"] = f"[Service]\nExecStart=\nExecStart={MANAGER}\n"
    sha = stage_app(m)
    put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": sha}])
    why = refused(m)
    assert f"{UNIT}.d/zz-local.conf sets ExecStart and is read after mercury.conf" in why
    assert f"Mercury's drop-in would not be the command line {UNIT} runs" in why


def test_a_unit_whose_own_command_line_cannot_be_read_is_never_a_pass(tmp_path):
    m = load(tmp_path)
    put_dropin(m)
    m.systemctl.unit_file = "[Service]\nUser=root\n"
    sha = stage_app(m)
    put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": sha}])
    assert f"systemctl cat {UNIT} shows no ExecStart outside mercury.conf" in refused(m)


@pytest.mark.parametrize("keep, words", [
    ('"plantedvalue"', "keep is not an object of rest, flags and apps"),
    ('{"rest": {"host": "plantedvalue.example"}}', "does not parse as an IPv4 or IPv6 address"),
    ('{"rest": {"host": "192.0.2.1", "port": 70000}}', "keep.rest.port"),
    ('{"rest": {"host": "192.0.2.1", "path": "plantedvalue"}}', "keep.rest is not an object"),
    ('{"flags": ["plantedvalue;reboot"]}', "keep.flags[0] is not one plain word"),
    ('{"apps": ["plantedvalue.py"]}', "keep.apps[0] is neither a file by its absolute path"),
    ('{"apps": ["ryu.app.ofctl_rest"]}', "keep.apps[0] is one of Ryu's own apps"),
    ('{"apps": ["/srv/a.py", "/srv/a.py"]}', "keep.apps[1] names an app listed before it"),
    ('{"cmd": "plantedvalue"}', "keep is not an object of rest, flags and apps")],
    ids=["not-an-object", "a-name", "a-port", "another-field", "a-flag", "a-relative-file",
         "a-built-in", "twice", "another-key"])
def test_a_keep_of_any_other_shape_is_refused_without_quoting_it(tmp_path, keep, words):
    m = load(tmp_path)
    put_dropin(m)
    put_request(m, [], raw=b'{"apps": [], "listen": {"host": "192.0.2.1", "port": 6653}, '
                           b'"keep": ' + keep.encode() + b"}")
    why = refused(m)
    assert words in why and "plantedvalue" not in why


def test_a_request_with_no_keep_is_the_shape_hash_and_render_it_always_was(tmp_path):
    m = load(tmp_path)
    req = {"apps": [{"name": "a", "version": "1.0.0", "sha256": "1" * 64}],
           "listen": {"host": "192.0.2.1", "port": 6653}}
    plain = m.parse_request(json.dumps(req).encode())
    assert "keep" not in plain
    assert m.render_dropin(plain, MANAGER, "ryu", "/opt/ryu-apps").splitlines()[-1] == (
        f"ExecStart={MANAGER} --observe-links --ofp-listen-host 192.0.2.1 "
        "--ofp-tcp-listen-port 6653 /opt/ryu-apps/a/1.0.0/a.py ryu.app.ofctl_rest "
        "ryu.app.rest_topology")
    with_keep = m.parse_request(json.dumps(dict(req, keep={"rest": {"host": "2001:db8::1"}}))
                                .encode())
    assert m.request_sha256(with_keep) != m.request_sha256(plain), "the keep is in the hash"
    assert " --wsapi-host 2001:db8::1 /opt/ryu-apps/a/1.0.0/a.py " in m.render_dropin(
        with_keep, MANAGER, "ryu", "/opt/ryu-apps")


# ── the script: the restart bound's clock (C2983) ─────────────────────────────────────────────

class SteppingTime:
    """The script's `time`: a wall clock that steps ten years forward during the script's first
    sleep, while it waits for the unit (NTP correcting a wrong hardware clock, C2982), and a
    monotonic clock that does not."""

    def __init__(self, real):
        self.real, self.stepped, self.mono = real, False, 0.0

    def time(self):
        return 1_500_000_000.0 + (10 * 365 * 86400 if self.stepped else 0)

    def monotonic(self):
        self.mono += 0.01
        return self.mono

    def sleep(self, _s):
        self.stepped = True

    def __getattr__(self, name):
        return getattr(self.real, name)


def test_the_restart_bound_is_counted_on_the_monotonic_clock(tmp_path):
    m = load(tmp_path)
    put_dropin(m)
    sha = stage_app(m)
    put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": sha}])
    m.time = SteppingTime(m.time)
    # The unit is active on the script's third read of it after the restart.
    real, reads = m.systemctl, {"n": 0}

    def slow(*args):
        got = real(*args)
        if args[0] == "show" and "ActiveState" in args:
            reads["n"] += 1
            if reads["n"] < 3:
                return 0, "MainPID=0\nActiveState=activating\nUser=ryu\n", ""
        return got
    slow.calls = real.calls
    m.systemctl = slow
    out = run(m)
    assert m.time.stepped, "the wall clock stepped while the script waited"
    assert out["ok"] is True and out["step"] == "running", out
    assert out["up_after_s"] < 1, "a duration on the monotonic clock, not ten years"


def test_the_script_s_restart_bound_is_2_5_times_the_measured_start():
    s = channel.script()
    assert s.UP_BOUND_S == 75 == 2.5 * 30
    assert "2.5 times the 30 s within which Ryu answered" in s.UP_BOUND_SOURCE
    assert "monotonic clock" in s.UP_BOUND_SOURCE and "placeholder" not in s.UP_BOUND_SOURCE
    assert transport.command_bound_s() == 188 and channel.window()["parts"] == {
        "session": 35, "command": 188, "ryu": 75, "post_check": 55}


# ── the host step's read, and the host step ──────────────────────────────────────────────────

@pytest.mark.parametrize("rest, url", [
    ("--wsapi-host 192.0.2.1 --wsapi-port 8080", "http://192.0.2.1:8080"),
    ("--wsapi-host 2001:db8::1 --wsapi-port 8081", "http://[2001:db8::1]:8081"),
    ("--wsapi-host 0.0.0.0", "http://127.0.0.1:8080"),
    ("--wsapi-host ::", "http://[::1]:8080"),
    ("", "http://127.0.0.1:8080")],
    ids=["ipv4", "ipv6", "every-ipv4-address", "every-ipv6-address", "no-bind"])
def test_the_host_step_s_read_says_where_rest_answers_on_the_host(tmp_path, capsys, rest, url):
    m = load(tmp_path)
    m.systemctl.dropins["listen.conf"] = (
        f"[Service]\nExecStart=\nExecStart={MANAGER} {rest} --observe-links "
        "ryu.app.ofctl_rest /opt/ryu-apps/of_versions.py\n")
    assert m.unit_read([UNIT]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[:3] == [f"manager={MANAGER}", f"rest={url}", "app=/opt/ryu-apps/of_versions.py"]
    assert json.loads(lines[3][len("kept="):])["apps"] == ["/opt/ryu-apps/of_versions.py"]
    assert not [c for c in m.systemctl.calls if c[0] != "cat"], "it reads, and changes nothing"


def test_the_host_step_s_read_refuses_naming_what_it_read(tmp_path, capsys):
    m = load(tmp_path)
    m.systemctl.unit_file = f"[Service]\nExecStart={MANAGER} \"quoted app\"\n"
    assert m.unit_read([UNIT]) == 1
    assert capsys.readouterr().out.startswith(
        f"REFUSED: argument 1 of {UNIT}'s ExecStart (/lib/systemd/system/{UNIT}) is not one "
        "plain word")
    assert m.unit_read(["ryu; reboot"]) == 1
    assert "takes one unit's name" in capsys.readouterr().out


def test_the_host_step_takes_the_unit_alone_and_reads_rest_where_it_is_bound():
    step = open(HOST_STEP).read()
    assert 'echo "Usage: bash $0 <ryu unit>.service [restart]"' in step
    # C2986: no REST address is assumed; the read's is the unit's own (`unit_read`'s rest=).
    assert not re.search(r"127\.0\.0\.1|localhost", step)
    assert 'curl -g -s --max-time 4 "$REST/stats/switches"' in step
    assert "REST=$(printf '%s\\n' \"$READ\" | sed -n 's/^rest=//p')" in step
    # C2985: a unit that loads apps from /opt/ryu-apps is not refused for it.
    assert not re.search(r"grep[^\n]*/opt/ryu-apps\|/home", step)
    # The bounds are the measured ones, on the host's uptime clock, never `date`.
    assert "RYU_BOUND_S=75" in step and "BACK_BOUND_S=55" in step
    assert "/proc/uptime" in step and not re.search(r"\bdate\b|\bSECONDS\b", step)


def test_the_host_step_changes_nothing_before_its_checks_pass():
    step = open(HOST_STEP).read()
    first_change = min(step.index('\nstep "'), step.index("sudo install "))
    for name in ("the release holds the script and the first drop-in",
                 "the accounts mercury and ryu exist",
                 "the sudoers file is absent or exactly the one line, and visudo -c parses "
                 "every file",
                 "the unit's own command line can be carried whole",
                 "the ryu account can read every app the unit loads",
                 "Ryu lists its switches where its REST is bound, before anything changes",
                 "the unit runs as User=ryu already, or this run may restart it"):
        assert step.index(f'check "{name}"') < first_change, name
    # Idempotent: a drop-in that is there is left, and a unit already User=ryu is not restarted.
    assert 'if [ -e "$DROPIN_DIR/mercury.conf" ]; then' in step
    assert step.count("systemctl restart") == 3, "the undo's, the step's and the header's"
    assert step.index('if [ "$USER_NOW" = ryu ]; then\n    echo "== NO RESTART') \
        < step.index('step "restart the unit, so it runs as ryu"')


# ── Mercury's plan ────────────────────────────────────────────────────────────────────────────

def plan(tmp_path, line, cat=None, items=None, show_line=None):
    return channel.plan(
        network="lab9", controller="ctl", unit=UNIT,
        enabled=enabled(tmp_path, names=("fabric_forwarding",)) if items is None else items,
        host={"show": show_text(show_line or line), "ls": ls("mercury"),
              "cat": cat_text(line) if cat is None else cat},
        listen=LISTEN, switches=[eos()], links=[], previous=None)


@pytest.mark.parametrize("rest_host", REST_HOSTS)
def test_the_plan_carries_the_unit_s_rest_bind_and_apps_and_says_each_in_words(
        tmp_path, rest_host):
    got = plan(tmp_path, unit_line(rest_host))
    assert got["ok"] is True, got["refusals"]
    assert got["request"]["keep"] == kept_of(rest_host)
    assert got["dropin_after"].splitlines()[-1] == (
        f"ExecStart={MANAGER} --observe-links --ofp-listen-host 192.0.2.10 "
        f"--ofp-tcp-listen-port 6653 --wsapi-host {rest_host} --wsapi-port 8080 "
        f"{LEGACY}/of_versions.py {LEGACY}/switch_quirks.py "
        "/opt/ryu-apps/fabric_forwarding/1.0.0/fabric_forwarding.py "
        "ryu.app.ofctl_rest ryu.app.rest_topology")
    kept = got["kept"]
    assert kept["rest_words"] == (
        f"Ryu's REST stays bound to {rest_host}, port 8080, as {UNIT} has it: the drop-in "
        f"carries --wsapi-host {rest_host} and --wsapi-port 8080")
    assert [a["words"] for a in kept["apps"]] == [
        f"kept: {LEGACY}/of_versions.py, loaded from {LEGACY}, not managed by Mercury",
        f"kept: {LEGACY}/switch_quirks.py, loaded from {LEGACY}, not managed by Mercury"]
    assert kept["note"].startswith("A kept app is not Mercury's: it is not read, tested or "
                                   "versioned, its OpenFlow versions are not in the "
                                   "conformance check")
    assert kept["listen_words"] == "", "the unit's OpenFlow listen is NetBox's: nothing moves"
    # The keep is what a confirm binds: it is in the request, so in the plan's hash.
    bare = dict(got, request={k: v for k, v in got["request"].items() if k != "keep"})
    assert channel.plan_hash(bare) != got["plan_sha256"]


@pytest.mark.parametrize("rest_host", REST_HOSTS)
def test_a_drop_in_that_would_drop_the_bind_is_refused_naming_both_values(tmp_path, rest_host):
    """The second read against the first: systemd holds the bind now (`systemctl show`), and
    the unit's own files as read (`systemctl cat`) do not name it."""
    line = unit_line(rest_host)
    bare = line.replace(f" --wsapi-host {rest_host}", "")
    got = plan(tmp_path, bare, show_line=line)
    assert got["ok"] is False and "request" not in got
    [why] = got["refusals"]
    assert why.startswith(
        f"the deploy would drop Ryu's REST bind: {UNIT} binds it to {rest_host}, port 8080 now "
        "(`systemctl show`), and the drop-in after would bind it to every address of the "
        "controller (no --wsapi-host), port 8080")
    assert "REST is unauthenticated and writes flows, so nothing is staged" in why


@pytest.mark.parametrize("rest_host, wide", [("192.0.2.1", "0.0.0.0"), ("2001:db8::1", "::")])
def test_a_drop_in_that_would_widen_the_bind_is_refused_naming_both_values(
        tmp_path, rest_host, wide):
    got = plan(tmp_path, unit_line(wide), show_line=unit_line(rest_host))
    [why] = got["refusals"]
    assert why.startswith(
        f"the deploy would widen Ryu's REST bind: {UNIT} binds it to {rest_host}, port 8080 "
        f"now (`systemctl show`), and the drop-in after would bind it to every address of the "
        f"controller ({wide}), port 8080")


@pytest.mark.parametrize("wide", ["0.0.0.0", "::"])
def test_a_bind_to_every_address_is_rendered_only_when_the_unit_has_it_and_said(tmp_path, wide):
    got = plan(tmp_path, unit_line(wide))
    assert got["ok"] is True, got["refusals"]
    assert f" --wsapi-host {wide} --wsapi-port 8080 " in got["dropin_after"]
    assert got["kept"]["rest_words"] == (
        f"Ryu's REST answers on EVERY address of the controller: {UNIT} already binds it to "
        f"{wide} (its own --wsapi-host), and the deploy keeps that as it is and widens "
        f"nothing; the drop-in carries --wsapi-host {wide} and --wsapi-port 8080")
    # A unit that names no bind gets none: nothing is rendered that it did not have.
    none = plan(tmp_path / "none", f"{MANAGER} --observe-links ryu.app.ofctl_rest")
    assert none["ok"] is True and "--wsapi" not in none["dropin_after"]
    assert none["kept"]["rest_words"] == (
        "Ryu's REST answers on every address of the controller (no --wsapi-host), Ryu's own "
        f"port (8080): {UNIT} names no --wsapi-host, and the deploy adds none")


def test_an_app_the_unit_loads_is_never_dropped_without_a_word(tmp_path):
    line = f"{MANAGER} --observe-links ryu.app.ofctl_rest /srv/site/guard.py --verbose"
    got = plan(tmp_path, f"{MANAGER} --observe-links ryu.app.ofctl_rest", show_line=line)
    assert got["ok"] is False
    assert got["refusals"] == [
        f"the deploy would drop --verbose from {UNIT}'s command line: it runs with it now "
        "(`systemctl show`), and the drop-in after would not carry it (the unit's own files, "
        "`systemctl cat`, do not name it). Nothing is staged",
        f"the deploy would stop loading /srv/site/guard.py, which {UNIT} loads now (`systemctl "
        "show`): the drop-in after would not carry it (the unit's own files, `systemctl cat`, "
        "do not name it) and no app of the set replaces it. Nothing is staged"]


def test_deploying_an_app_of_the_same_name_replaces_the_kept_file_and_says_so(tmp_path):
    got = plan(tmp_path, unit_line("192.0.2.1"), items=enabled(tmp_path))   # of_versions
    assert got["ok"] is True, got["refusals"]
    line = got["dropin_after"].splitlines()[-1]
    assert f"{LEGACY}/of_versions.py" not in line and f" {LEGACY}/switch_quirks.py " in line
    assert [a["words"] for a in got["kept"]["apps"]] == [
        f"replaced: {LEGACY}/of_versions.py is no longer loaded; Mercury's of_versions 1.0.0 "
        "takes its place (the file stays on the controller)",
        f"kept: {LEGACY}/switch_quirks.py, loaded from {LEGACY}, not managed by Mercury"]
    # After that deploy the unit runs Mercury's render: the next plan carries the same.
    again = plan(tmp_path / "again", unit_line("192.0.2.1"), items=enabled(tmp_path / "again"),
                 show_line=line[len("ExecStart="):])
    assert again["ok"] is True and again["request"]["keep"] == got["request"]["keep"]


def test_a_unit_s_command_line_that_cannot_be_carried_refuses_the_plan(tmp_path):
    quoted = plan(tmp_path, f'{MANAGER} --observe-links "ryu.app.ofctl_rest"',
                  show_line=f"{MANAGER} --observe-links ryu.app.ofctl_rest")
    assert quoted["refusals"] == [
        f"{UNIT}'s own command line cannot be carried as it is: argument 2 of {UNIT}'s "
        f"ExecStart (/etc/systemd/system/{UNIT}.d/listen.conf) is not one plain word (letters, "
        "digits and _ @ + = : , . / -): a quoted, escaped or expanded argument cannot be "
        "carried as it is. Nothing is staged"]
    line = f"{MANAGER} --observe-links"
    later = plan(tmp_path / "later", line, cat=cat_text(line) + (
        f"\n# /etc/systemd/system/{UNIT}.d/zz-local.conf\n[Service]\nExecStart=\n"
        f"ExecStart={MANAGER}\n"))
    assert later["refusals"] == [
        f"/etc/systemd/system/{UNIT}.d/zz-local.conf sets ExecStart and is read after "
        f"mercury.conf, so Mercury's drop-in would not be the command line {UNIT} runs. "
        "Nothing is staged"]


# ── the post-check's two bounds ───────────────────────────────────────────────────────────────

def test_both_bounds_are_2_5_times_what_was_measured():
    ryu, back = post_check.ryu_bound(), post_check.bound()
    assert (ryu["seconds"], ryu["measured"]) == (75, True) and 75 == 2.5 * 30
    assert (back["seconds"], back["measured"]) == (55, True) and 52.5 == 2.5 * 21
    assert ryu["words"] == (
        "75 s from the moment the apply's outcome was read back, 2.5 times the 30 s measured "
        "(Ryu answered within 30 s of its process starting, at the controller's reboot test of "
        "2026-11-11)")
    assert back["words"] == (
        "55 s after Ryu first answers, 2.5 times the 21 s measured (52.5 s, taken up to a "
        "whole 5 s read; every switch and link was back 21 s after Ryu answered, at the "
        "controller's reboot test of 2026-11-11)")
    assert post_check.limit_s() == 130


NO_ANSWER = {"switches": {"ok": False, "error": "connection refused"},
             "links": {"ok": False, "error": "connection refused"}, "health": {}}


def test_ryu_s_start_bound_fires_naming_what_it_read_and_waited_for():
    clock = Clock()
    got = post_check.wait(lambda: NO_ANSWER, EXPECTED, clock=clock, sleep=clock.sleep)
    assert got["ok"] is False and got["fired"] == "ryu" and got["ryu_answered_s"] is None
    assert got["elapsed_s"] == 75.0 and got["polls"] == 16
    assert got["words"].startswith(
        "Ryu's start bound fired: Ryu did not answer within 75.0 s of the apply's outcome being "
        "read back (16 reads of its switch list, the last saying: connection refused; ")
    assert ("The post-check waited for a read of the switches to answer, on its own time, and "
            "the bound is 75 s from the moment the apply's outcome was read back, 2.5 times "
            "the 30 s measured") in got["words"]


def test_the_switches_bound_counts_from_ryu_s_first_answer_not_from_the_start():
    """Ryu answers 60 s in, with a switch still missing: the switches' bound fires 55 s after
    that answer (115 s of the post-check's own), not 55 s after the start."""
    clock = Clock()
    reads = iter([NO_ANSWER] * 12)
    got = post_check.wait(lambda: next(reads, SWITCH_2_DOWN), EXPECTED, clock=clock,
                          sleep=clock.sleep)
    assert got["ok"] is False and got["fired"] == "switches"
    assert got["ryu_answered_s"] == 60.0 and got["elapsed_s"] == 115.0
    assert "55.0 s after Ryu first answered: switches not back: 2" in got["words"]


def test_a_slow_ryu_start_inside_its_bound_still_passes():
    clock = Clock()
    reads = iter([NO_ANSWER] * 14 + [SWITCH_2_DOWN] * 5)
    got = post_check.wait(lambda: next(reads, ALL_BACK), EXPECTED, clock=clock,
                          sleep=clock.sleep)
    assert got["ok"] is True and got["ryu_answered_s"] == 70.0 and got["elapsed_s"] == 95.0


# ── the operation, the receipt and the page ──────────────────────────────────────────────────

class KeptSources(FakeSources):
    """`FakeSources` on a controller whose unit binds REST to one address and loads two apps
    of its own."""

    line = unit_line("192.0.2.1")

    def host_reads(self, network, controller):
        return {"state": "ok", "show": show_text(self.line), "ls": ls("mercury"),
                "cat": cat_text(self.line), "at": "2026-11-08T05:00:00Z", "error": ""}


def test_the_confirmed_request_carries_the_keep_and_the_receipt_records_it(tmp_path):
    from modules import controller_deploy_receipts as deploy_receipts

    src = KeptSources(tmp_path)
    shown = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    assert shown["ok"] is True, shown["refusals"]
    src.reads = [ALL_BACK_TWO]
    src.outcomes = [{"ok": True, "up_after_s": 3.0, "kept_files": [
        {"path": f"{LEGACY}/switch_quirks.py", "sha256": "5" * 64}]}]
    assert run_op(src, {"of_versions": "1.0.0"}, shown["plan_sha256"])["outcome"] == "deployed"
    [sent] = src.sent
    assert sent["request"]["keep"] == kept_of("192.0.2.1")
    row = deploy_receipts.read(NET)["rows"][0]
    assert row["request"]["keep"] == kept_of("192.0.2.1")
    assert row["kept"]["rest_words"].startswith("Ryu's REST stays bound to 192.0.2.1, port 8080")
    assert [a["state"] for a in row["kept"]["apps"]] == ["replaced", "kept"]
    [applied] = [s for s in row["steps"] if s["step"] == "apply"]
    assert applied["kept_files"] == [{"path": f"{LEGACY}/switch_quirks.py",
                                      "sha256": "5" * 64}]
    assert row["bounds"]["ryu_start"]["seconds"] == 75 and row["bounds"]["unit_up_s"] == {
        "seconds": 75, "measured": True,
        "source": "UP_BOUND_S in the apply script: " + channel.script().UP_BOUND_SOURCE}


def test_the_preview_draws_what_is_kept_and_the_rest_bind(apps):  # noqa: F811
    apps["src"].__class__ = KeptSources
    html = unescape(preview(apps["client"]).get_data(as_text=True))
    assert ("<dt>REST</dt><dd>Ryu's REST stays bound to 192.0.2.1, port 8080, as "
            f"{UNIT} has it: the drop-in carries --wsapi-host 192.0.2.1 and --wsapi-port 8080"
            "</dd>") in html
    assert "From the unit's own command line, carried as it is" in html
    assert (f"replaced: {LEGACY}/of_versions.py is no longer loaded; Mercury's of_versions "
            "1.0.0 takes its place (the file stays on the controller)</li>") in html
    assert (f"kept: {LEGACY}/switch_quirks.py, loaded from {LEGACY}, not managed by Mercury"
            "</li>") in html
    assert "A kept app is not Mercury's: it is not read, tested or versioned" in html
    assert "--wsapi-host 192.0.2.1 --wsapi-port 8080" in html, "the drop-in after, drawn"
    # The effect: a preview sends nothing to the controller and writes no receipt.
    from modules import controller_deploy_receipts as deploy_receipts
    assert apps["src"].sent == [] and deploy_receipts.read("Default")["rows"] == []
