"""The command plan and its runner (C3757, path 2; modules/nsot/command_plan.py,
modules/nsot/command_policy.py, modules/nsot/command_plan_run.py).

- **The template**: the built-in plan parses; the schema refuses what it does not name, a plan
  not net zero, a check or a bound Mercury does not declare, a placeholder no parameter fills.
- **Mercury's rule for raw lines**: the measured shapes on both dialects, the refused words
  (negated too), an object not named by a parameter, an unknown shape refused and listed, a
  provisional shape still refused until an admin approves it, the measurement recorded once.
- **The parameters against Mercury's model**: in committed intent, an access port, never the
  management path, IPv4 and IPv6 alike.
- **The run**, end to end through the deploy pipeline's real stages, on a fake switch that
  answers from s1's captures (tests/fixtures/errdisable/) and from its committed golden: the
  recovery verified and recorded (receipt, run record, measurement, notification), never
  saved; err-disabled again rolled back; a cause not cleared, the switch's own recovery, the
  device disagreeing, no person and another hash each refused with nothing sent; the net-zero
  check (a plan that leaves a line changed is rolled back and refused; a device that departs
  from intent is bounced, the plan being net zero); the pre-apply hook; Mercury's own session
  attributed as Mercury's; the step reached only through its declaration's ``apply``.
- **The run's scope (7b300f39)**: the net-zero check scoped to the plan's interface sections on
  a fake answering the section read, the rollback's compare in the same scope, the whole
  compare when a section cannot be read; each snapshot rule and the device departing from the
  access rule; the spanning-tree verdicts; the pooled session refusing another address or
  account, IPv4 and IPv6.
- **C3847's follow-ups (ec92d62b)**: the pipeline's stage callback; verify recorded as its own
  step with its seconds; stage 7 reading no configuration after a transient run, BGP's hold
  from before; the cosmetic scope per program; the switch's own recovery table read.

No device, no network, no AI.
"""
import dataclasses
import inspect
import json
import os
import types

import pytest

from modules.nsot import command_plan as CP
from modules.nsot import command_plan_run as CR
from modules.nsot import command_policy as POL
from tests import test_errdisable as T

NET = T.NET
ACTOR = T.ACTOR
KEY = "errdisable-recover"
PORT = "GigabitEthernet1/0"
VALUES = {"device": "s1", "interface": "Gi1/0", "cause": "bpduguard"}
INTERFACES_READ = "show interfaces | include (line protocol|Internet address)"
#: s1's captured `show spanning-tree interface` rows (tests/fixtures/diagnose, its Gi0/3).
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "diagnose",
                       "s1__show_spanning_tree_interface_GigabitEthernet0_3.txt"),
          encoding="utf-8") as _fh:
    STP_ROWS = _fh.read()


# ── A fake switch for the whole pipeline: s1's captures and its committed golden ────────────

class Switch:
    """s1 with Gi1/0 err-disabled by BPDU guard (*state*), its running configuration its
    committed golden (*running*). ``shutdown`` shuts the port; ``no shutdown`` brings it up,
    or err-disables it again when its cause is still there (*again*). *admin_down*: the port
    is shut in its running configuration before the plan. *recovery*: its answer to `show
    errdisable recovery`. Premise corrected (ec92d62b, the operator, 2026-11-16: errdisable-recover
    reads the switch's own recovery table): s1's captured table by default (bpduguard
    Disabled: the switch does not recover it itself), where an empty answer stood for "no
    recovery"; an empty table refuses now, naming it."""

    def __init__(self, state="err-disabled", again=False, cause="bpduguard", recovery=None,
                 running=None, admin_down=False, macs=None, sticky=""):
        if recovery is None:
            recovery = T.text("s1_errdisable_recovery.txt")
        self.state, self.again, self.cause, self.recovery = state, again, cause, recovery
        self.base = T.s1_golden() if running is None else running
        self.admin_down, self.macs = admin_down, macs
        #: A line the port learns as it comes up (a sticky MAC), which no rollback of the
        #: plan's own lines removes.
        self.sticky = sticky
        self.batches, self.reads, self.sessions = [], [], 0

    def running(self) -> str:
        if not self.admin_down:
            return self.base
        return self.base.replace(f"interface {PORT}\n", f"interface {PORT}\n shutdown\n", 1)

    def status(self) -> str:
        row = {"err-disabled": T.ROW_ERR, "connected": T.ROW_OK, "disabled": T.ROW_OFF}[
            self.state]
        return row + "\n" + T.text("s1_status.txt").splitlines()[1] + "\n"

    def interfaces(self) -> str:
        words = {"connected": "up, line protocol is up (connected)",
                 "err-disabled": "down, line protocol is down (err-disabled)",
                 "disabled": "administratively down, line protocol is down (disabled)"}
        return (f"{PORT} is {words[self.state]}\n"
                "GigabitEthernet1/1 is up, line protocol is up (connected)\n")

    def answer(self, command: str) -> str:
        self.reads.append(command)
        if command == "show running-config":
            return self.running()
        if command == T.E.RECOVERY_READ:
            return self.recovery
        if command == T.E.CONFIRM_READ:
            return (T.ROW_REASON.replace("bpduguard", self.cause) + "\n"
                    if self.state == "err-disabled" else "")
        if command == T.E.STATUS_READ:
            return self.status()
        if command == INTERFACES_READ:
            return self.interfaces()
        if command.startswith("show mac address-table") or command == T.E.PSEC_READ:
            return self.macs if self.macs is not None else T.text("s5_mac_table_gi03.txt")
        if command == f"show spanning-tree interface {PORT}":
            # Premise corrected (ec92d62b: the recovery's verify reads the port's spanning tree):
            # a port up forwards in its VLANs, s1's captured rows (Gi0/3's, the same table on
            # vIOS-L2 for any port); a port down holds none.
            return STP_ROWS if self.state == "connected" else ""
        return ""

    def apply(self, lines):
        self.batches.append([ln for ln in lines])
        for ln in lines:
            w = ln.strip()
            if w == "shutdown":
                self.state, self.admin_down = "disabled", True
            elif w == "no shutdown":
                self.admin_down = False
                self.state = "err-disabled" if self.again else "connected"
                if self.sticky and self.sticky not in self.base:
                    self.base = self.base.replace(f"interface {PORT}\n",
                                                  f"interface {PORT}\n{self.sticky}\n", 1)


class Conn:
    def __init__(self, sw):
        self.sw = sw

    def enable(self):
        pass

    def send_config_set(self, lines, **_kw):
        self.sw.apply(list(lines))
        return ""

    def disconnect(self):
        pass


class Model(CP.Sources):
    """Mercury's model for s1: its inventory row, committed intent and golden."""

    def __init__(self, network=NET, mgmt="192.0.2.11", golden=None, intent=None, name="s1"):
        super().__init__(network)
        self.mgmt, self._golden, self._intent, self.name = mgmt, golden, intent, name

    def device(self, host):
        return ({"hostname": host, "ip": self.mgmt, "device_type": "cisco_ios"}
                if host == self.name else {})

    def intent(self, host):
        return (self._intent if self._intent is not None else T.s1_intent()), ""

    def golden(self, host):
        return (self._golden if self._golden is not None else T.s1_golden()), ""


@pytest.fixture
def lab(monkeypatch, tmp_path):
    """The network's store under *tmp_path*, the fake switch behind every session the
    pipeline and the read engine open, and the clock moving only when the run sleeps."""
    from tests.test_sdn_connections import make_networks
    make_networks(tmp_path, monkeypatch)
    sw = Switch()
    state = {"sw": sw, "saved": [], "events": [], "t": T.AT + 600}

    def switch():
        return state["sw"]

    def temp(dev, fn):
        switch().sessions += 1
        return fn(Conn(switch()))
    monkeypatch.setattr("modules.connection.get_persistent_connection",
                        lambda dev, pool, lock: (setattr(switch(), "sessions",
                                                         switch().sessions + 1),
                                                 Conn(switch()))[1])
    monkeypatch.setattr("modules.connection.close_persistent_connection",
                        lambda *a, **k: None)
    monkeypatch.setattr("modules.connection.with_temp_connection", temp)
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, cmd, **k: conn.sw.answer(cmd))
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda *_a, **_k: [{"hostname": "s1", "ip": "192.0.2.11",
                                            "device_type": "cisco_ios"}])
    monkeypatch.setattr("modules.neighbours.committed_intents_of",
                        lambda network: ({"s1": T.s1_intent()}, ""))
    monkeypatch.setattr("modules.nsot.onboard.persist_on_device",
                        lambda *a, **k: (state["saved"].append(a), {"ok": True})[1])
    # The row's fields as given (the fake row holds no encrypted token), so a save the
    # pipeline asked for would reach the counted one above.
    monkeypatch.setattr("modules.device.decrypt_field", lambda v: v)
    monkeypatch.setattr("modules.heal.errdisable.Sources.notify",
                        lambda self, network, event: (state["events"].append(event),
                                                      {"ok": True, "sent": 1})[1])
    state["lines"] = T.loki()
    monkeypatch.setattr("modules.heal.errdisable.Sources.lines",
                        lambda self, dev, since, until: {
                            "error": "", "cut": False,
                            "lines": [ln for ln in state["lines"]
                                      if since <= ln["epoch"] <= until]})
    return state


def sources(lab, **model):
    def sleep(s):
        lab["t"] += float(s)
    return CR.Sources(NET, clock=lambda: lab["t"], sleep=sleep, model=Model(**model))


def go(lab, values=None, key=KEY, **over):
    src = over.pop("sources", None) or sources(lab)
    vals = dict(values or VALUES)
    p = CP.preview(NET, key, vals, sources=src.model)
    kw = dict(actor=ACTOR, actor_verified="access", person=True,
              confirmed=p["hash"], reason="recover the port for the test", sources=src)
    kw.update(over)
    return CR.run(NET, key, vals, **kw)


def receipts_of() -> list:
    from modules.nsot import receipts
    return receipts.read(NET, "s1")["rows"]


# ── The template ────────────────────────────────────────────────────────────────────────────

def _doc(**over) -> dict:
    import yaml
    with open(os.path.join(CP.BUILTIN_DIR, f"{KEY}.yml"), encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    doc.update(over)
    return doc


class TestTheTemplate:
    def test_the_built_in_plan_parses_net_zero_its_lines_placeholders(self):
        t = CP.builtin()[KEY]
        assert t.net_zero is True
        assert t.commands == ("interface {interface}", " shutdown", " no shutdown")
        assert [p["name"] for p in t.preconditions] == [
            "The port is err-disabled by the cause now",
            "The switch does not recover the cause itself", "The cause has cleared"]

    def test_the_hash_binds_exactly_its_declared_fields(self):
        t = CP.builtin()[KEY]
        got = CP.bound_fields(NET, t, {"device": "s1"}, ["x"], [])
        assert tuple(got) == CP.BINDS

    @pytest.mark.parametrize("over, said", [
        ({"surprise": 1}, "also gives surprise"),
        ({"net_zero": False}, "net-zero"),
        ({"kind": "script"}, "kind is command_plan"),
        ({"steps": [{"mode": "config", "commands": ["reload"]}]}, "begins with `reload`"),
        ({"steps": [{"mode": "config", "commands": ["interface GigabitEthernet1/0",
                                                    " shutdown"]}]}, "names its interface"),
        ({"steps": [{"mode": "config", "commands": ["interface {port}"]}]}, "not a parameter"),
        ({"verify": [{"name": "x", "read": "show clock", "expect": "anything.at_all",
                      "after": "errdisable-quiet"}]}, "not one of Mercury's checks"),
        ({"verify": [{"name": "x", "read": "show clock", "expect_line": "*",
                      "poll": "errdisable-poll", "within": "a-minute"}]}, "PLAN_BOUNDS"),
    ])
    def test_the_schema_refuses_naming_what(self, over, said):
        with pytest.raises(CP.Refused) as exc:
            CP.parse(_doc(**over))
        assert said in str(exc.value), str(exc.value)

    def test_a_screen_names_the_plan_by_its_title_never_its_key(self):
        from modules.fixit.section import short_words
        assert short_words(KEY, "s1", {"interface": PORT, "cause": "bpduguard"}) == (
            "Recover s1 Gi1/0, err-disabled by bpduguard")

    def test_expect_line_matches_a_whole_line_with_validated_values(self):
        d = {"interface_short": "Gi1/0"}
        assert CP.line_matches("{interface_short} * connected *", T.ROW_OK, d)
        assert not CP.line_matches("{interface_short} * connected *", T.ROW_ERR, d)
        assert not CP.line_matches("{interface_short} connected", T.ROW_OK, d)


# ── Mercury's rule for raw lines ────────────────────────────────────────────────────────────

LAUNCH = ["interface {interface}", " shutdown", " no shutdown"]


class TestThePolicy:
    @pytest.mark.parametrize("dialect", ["cisco_ios", "cisco_iosxe"])
    def test_the_launch_shapes_are_allowed_as_sent_by_g7(self, dialect):
        assert POL.check(dialect, LAUNCH, ("interface",))["ok"]
        assert set(POL.MEASURED[dialect].values()) == {
            "as sent by G7's recovery, measured at its first run"}

    @pytest.mark.parametrize("line", [
        "reload", "no reload", "erase startup-config", "format flash:", "delete flash:x",
        "boot system flash:x", "username a privilege 15 secret 0 x", "aaa new-model",
        "crypto key generate rsa", "line vty 0 4", "write memory", "copy run start",
        "do write", "end", "default username a"])
    def test_a_refused_word_is_refused_whoever_proposed_it(self, line):
        got = POL.check("cisco_ios", [line], ())
        assert not got["ok"] and "never sends" in got["refusals"][0], got

    def test_an_object_not_named_by_a_parameter_is_refused(self):
        got = POL.check("cisco_ios", ["interface GigabitEthernet1/0", " shutdown"],
                        ("interface",))
        assert not got["ok"] and "names its interface as text" in got["refusals"][0]

    def test_an_unknown_shape_is_refused_and_listed(self):
        got = POL.check("cisco_ios", ["interface {interface}", " description x"],
                        ("interface",))
        assert not got["ok"]
        assert [u["shape"] for u in got["unknown"]] == ["interface {interface} > description x"]
        assert "can be proposed" in got["refusals"][0]

    def test_an_unknown_dialect_is_refused(self):
        assert not POL.check("", LAUNCH, ("interface",))["ok"]

    def test_a_provisional_shape_is_refused_until_an_admin_approves_it(self, lab):
        shape = "interface {interface} > description x"
        lines = ["interface {interface}", " description x"]
        assert POL.propose(NET, "cisco_ios", shape, by="the AI (call c-1)",
                           why="a test")["state"] == "provisional"
        got = POL.check("cisco_ios", lines, ("interface",), network=NET)
        assert not got["ok"] and got["provisional"] == [shape]
        assert "held PROVISIONAL" in got["refusals"][0]
        for who in ({"admin": False, "person": True}, {"admin": True, "person": False},
                    {"admin": True, "person": True, "actor_verified": "none"}):
            kw = dict({"actor": ACTOR, "actor_verified": "access"}, **who)
            assert not POL.approve(NET, "cisco_ios", shape, **kw)["ok"], who
        assert not POL.check("cisco_ios", lines, ("interface",), network=NET)["ok"]
        assert POL.approve(NET, "cisco_ios", shape, actor=ACTOR, actor_verified="access",
                           person=True, admin=True)["ok"]
        assert POL.check("cisco_ios", lines, ("interface",), network=NET)["ok"]

    def test_a_refused_word_cannot_be_proposed(self, lab):
        assert not POL.propose(NET, "cisco_ios", "reload", by="x", why="y")["ok"]

    def test_a_check_writes_nothing(self, lab, tmp_path):
        POL.check("cisco_ios", ["interface {interface}", " description x"], ("interface",),
                  network=NET)
        assert not os.path.exists(POL._path(NET))

    def test_a_shape_is_measured_once_by_its_first_run(self, lab):
        shapes = [s for _r, s in POL.shapes(LAUNCH)]
        assert POL.record_measurement(NET, "cisco_ios", shapes, device="s1", run="r1",
                                      outcome="done", answer="ok") == shapes
        assert POL.record_measurement(NET, "cisco_ios", shapes, device="s1", run="r2",
                                      outcome="done", answer="ok") == []
        m = POL.measurement(NET, "cisco_ios", "interface {interface} > shutdown")
        assert (m["run"], m["device"], m["outcome"]) == ("r1", "s1", "done")

    def test_a_person_s_run_hands_its_press_to_the_measurement(self, lab, monkeypatch):
        """C3902's wiring: a person's approved run passes its press (who, the plan's hash, the
        run) to the shapes' measurement, so a provisional shape it sent keeps it."""
        handed = []
        real = POL.record_measurement

        def kept(*a, **kw):
            handed.append(kw.get("approval"))
            return real(*a, **kw)
        monkeypatch.setattr(POL, "record_measurement", kept)
        rec = go(lab)
        assert rec["outcome"] == "done", rec["why"]
        (press,) = handed
        assert (press["by"], press["hash"], press["run"]) == (ACTOR, rec["hash"], rec["id"])
        assert press["at"].endswith("Z")

    def test_a_person_s_approved_run_measures_a_provisional_shape_and_keeps_its_press(self, lab):
        """C3902 (the operator, 2026-11-17: "a person approving a plan with its exact commands
        shown also approves its provisional shapes (one press; the run measures them)"): a
        provisional shape a person's approved run sent is measured and keeps that approval
        (who, when, the plan's hash, the run); it stays provisional, so an Automatic run still
        needs an admin's approval of the shape; a run nobody approved measures nothing."""
        shape = "interface {interface} > description x"
        lines = ["interface {interface}", " description x"]
        POL.propose(NET, "cisco_ios", shape, by="the AI (call c-1)", why="a test")
        assert POL.record_measurement(NET, "cisco_ios", [shape], device="s1", run="r0",
                                      outcome="done", answer="ok") == []
        assert not POL.measurement(NET, "cisco_ios", shape)
        press = {"by": ACTOR, "at": "2026-11-25T06:00:00Z", "hash": "a1b2c3d4", "run": "r1"}
        assert POL.record_measurement(NET, "cisco_ios", [shape], device="s1", run="r1",
                                      outcome="done", answer="ok", approval=press) == [shape]
        assert POL.measurement(NET, "cisco_ios", shape)["run"] == "r1"
        rec = POL.read_store(NET)["shapes"][POL.key_of("cisco_ios", shape)]
        assert rec["state"] == "provisional" and rec["plan_approvals"] == [press], rec
        got = POL.check("cisco_ios", lines, ("interface",), network=NET)
        assert not got["ok"] and got["provisional"] == [shape], "Automatic still needs an admin"


# ── The parameters against Mercury's model ──────────────────────────────────────────────────

class TestTheParameters:
    def test_a_valid_port_is_its_canonical_name(self):
        got = CP.validate(NET, CP.builtin()[KEY], VALUES, sources=Model())
        assert got["ok"], got["refusals"]
        assert got["values"]["interface"] == PORT
        assert got["derived"]["interface_short"] == "Gi1/0"
        assert got["dialect"] == "cisco_ios"

    @pytest.mark.parametrize("over, said", [
        ({"interface": "Gi9/9"}, "holds no interface"),
        ({"interface": "Gi0/3"}, "acts only on an access port"),
        ({"interface": "Gi1/0; reload"}, "not an interface's name"),
        ({"cause": "all"}, "not one of"),
        ({"device": "s9"}, "no device of"),
    ])
    def test_what_the_model_does_not_hold_is_refused(self, over, said):
        got = CP.validate(NET, CP.builtin()[KEY], dict(VALUES, **over), sources=Model())
        assert not got["ok"] and said in " ".join(got["refusals"]), got["refusals"]

    def test_the_dhcp_management_interface_is_refused(self):
        t = CP.parse(_doc(parameters=dict(_doc()["parameters"], interface={
            "type": "interface", "not_management": True})))
        got = CP.validate(NET, t, dict(VALUES, interface="Gi0/0"), sources=Model())
        assert not got["ok"] and "managed through" in got["refusals"][0]

    @pytest.mark.parametrize("mgmt", ["10.10.10.2", "2001:db8:10::2"])
    def test_an_access_port_in_the_management_vlan_is_refused_ipv4_and_ipv6(self, mgmt):
        got = CP.validate(NET, CP.builtin()[KEY], VALUES, sources=Model(mgmt=mgmt))
        assert not got["ok"] and "VLAN 10" in got["refusals"][0], got["refusals"]

    @pytest.mark.parametrize("mgmt", ["192.0.2.11", "2001:db8::11"])
    def test_a_management_address_elsewhere_refuses_nothing(self, mgmt):
        assert CP.validate(NET, CP.builtin()[KEY], VALUES, sources=Model(mgmt=mgmt))["ok"]


# ── The preview ─────────────────────────────────────────────────────────────────────────────

class TestThePreview:
    def test_it_draws_what_its_hash_binds_and_asks_no_device(self, lab):
        p = CP.preview(NET, KEY, VALUES, sources=Model())
        assert p["ok"], p["refusals"]
        assert p["program"] == [f"interface {PORT}", " shutdown", " no shutdown"]
        d = p["drawn"]
        assert d["hash"] == p["hash"] and d["template"] == KEY and "line for line" in d["net_zero"]
        assert [v.get("within") for v in d["verify"]] == [30, None]
        assert d["verify"][1]["after"] == 10
        assert lab["sw"].reads == [] and lab["sw"].sessions == 0
        other = CP.preview(NET, KEY, dict(VALUES, cause="psecure-violation"), sources=Model())
        assert other["hash"] != p["hash"]

    def test_the_switchs_own_recovery_in_the_golden_refuses_at_preview(self):
        p = CP.preview(NET, KEY, VALUES, sources=Model(
            golden=T.s1_golden() + "errdisable recovery cause bpduguard\n"))
        assert not p["ok"] and "does not race it" in " ".join(p["refusals"])


# ── The run, through the pipeline ───────────────────────────────────────────────────────────

class TestTheRun:
    def test_it_recovers_verifies_records_and_is_never_saved(self, lab):
        rec = go(lab)
        sw = lab["sw"]
        assert (rec["outcome"], rec["state"]) == ("done", "done"), rec["why"]
        assert sw.batches == [[f"interface {PORT}", " shutdown", " no shutdown"]]
        assert sw.state == "connected" and lab["saved"] == []
        assert [s["step"] for s in rec["steps"]] == [
            "approve", "hold", "read_before", "preconditions", "send", "verify", "record"]
        assert rec["net_zero"] == {"checked": True, "differs": [], "scope": "full"}
        assert rec["key"] == KEY and rec["kind"] == "command_plan"
        assert rec["params"] == {"device": "s1", "interface": PORT, "cause": "bpduguard"}
        (row,) = receipts_of()
        assert row["action"] == "command_plan" and row["intent_commit"] is None
        assert row["command_plan"]["plan"] == KEY and row["command_plan"]["run"] == rec["id"]
        assert row["golden_commit"] == ""
        from modules.nsot import privileged
        assert privileged.get(NET, rec["id"])["outcome"] == "done"
        assert POL.measurement(NET, "cisco_ios", "interface {interface} > no shutdown")[
            "run"] == rec["id"]
        (ev,) = lab["events"]
        assert ev["event"] == "action" and "Gi1/0" in ev["happened"]

    def test_the_record_keeps_the_digest_of_the_template_it_ran(self, lab):
        """The correctness review's G3-H2 (2026-11-18): Save stores a verified run's plan, so
        the run's record names the template it ran by its digest (the digest the approved hash
        binds), and a Save after the plan changed can tell the two apart."""
        rec = go(lab)
        assert rec["outcome"] == "done", rec["why"]
        from modules.nsot import privileged
        assert rec["template_digest"] == CP.template_of(KEY).digest
        assert privileged.get(NET, rec["id"])["template_digest"] == rec["template_digest"]

    def test_err_disabled_again_is_rolled_back_saying_what_it_achieved(self, lab):
        """Premise corrected (4a8bb0df, the operator, 2026-11-16: "a re-trip is its own outcome
        with no rollback"): the port err-disabled again by its own cause is the run's outcome,
        ``retripped``, said with what it achieved ("Port left err-disabled; nothing more
        sent."), recorded as a recurrence and notified as a can't-fix; nothing more is sent and
        nothing rolled back, where the bounce was rolled back with ``no shutdown``."""
        lab["sw"] = Switch(again=True)
        rec = go(lab)
        assert rec["outcome"] == "retripped", rec["why"]
        assert "Port left err-disabled; nothing more sent." in rec["why"]
        assert "rollback" not in [s["step"] for s in rec["steps"]]
        assert lab["sw"].batches == [[f"interface {PORT}", " shutdown", " no shutdown"]], \
            "the bounce alone was sent"
        assert rec["recurrence"]["port"] == "Gi1/0" and rec["recurrence"]["cause"] == "bpduguard"
        assert lab["events"][0]["event"] == "cant_fix"

    def test_a_bpdu_since_the_err_disable_refuses_with_nothing_sent(self, lab):
        # The incident's own classification gives the err-disable's time (its line at AT+1).
        iid = T.opened("Critical syslog received")["incident"]
        T.opened("Interface down", PORT, at=T.AT + 20)
        T.E.reclassify_step(NET, sources=T.Src(), now=T.AT + 600)
        lab["lines"] = T.loki() + [{"line": T.text("s1_loki_lines.txt").splitlines()[0],
                                    "at": T.E._iso(T.AT + 120), "epoch": T.AT + 120}]
        rec = go(lab, incident=iid, fixit={"incident": iid})
        assert rec["outcome"] == "refused" and lab["sw"].batches == []
        assert "Port stays down" in rec["why"]
        assert lab["events"][0]["event"] == "held"

    def test_the_switchs_running_recovery_is_never_raced(self, lab):
        # Premise corrected (ec92d62b: the switch's own recovery table is read, never its
        # configuration's line): s1's captured table with bpduguard's timer Enabled (one edit).
        enabled = T.text("s1_errdisable_recovery.txt").replace(
            "bpduguard                    Disabled", "bpduguard                    Enabled", 1)
        assert "bpduguard                    Enabled" in enabled
        lab["sw"] = Switch(recovery=enabled)
        rec = go(lab)
        assert rec["outcome"] == "refused" and lab["sw"].batches == []
        assert "does not race it" in rec["why"]

    def test_the_device_disagreeing_with_the_plan_takes_no_action(self, lab):
        lab["sw"] = Switch(cause="psecure-violation")
        rec = go(lab)
        assert rec["outcome"] == "refused" and lab["sw"].batches == []
        assert "disagree" in rec["why"]

    @pytest.mark.parametrize("over", [{"person": False}, {"actor_verified": "none"},
                                      {"confirmed": "0" * 16}, {"confirmed": ""}])
    def test_no_person_or_another_hash_sends_nothing(self, lab, over):
        rec = go(lab, **over)
        assert rec["outcome"] == "refused" and lab["sw"].sessions == 0, over
        assert "Nothing was sent" in rec["why"]


# ── Net zero (the operator, 2026-11-15) ─────────────────────────────────────────────────────

BOUNCE = "bounce-test"


@pytest.fixture
def bounce(monkeypatch):
    """A planted template: a bounce with no precondition, verified by the port connected."""
    t = CP.parse({"kind": "command_plan", "key": BOUNCE, "title": "Bounce {device}",
                  "words": "a bounce for the test", "net_zero": True,
                  "parameters": {"device": {"type": "device"},
                                 "interface": {"type": "interface"}},
                  "steps": [{"mode": "config", "commands": LAUNCH}],
                  "verify": [{"name": "connected", "read": "show interfaces status",
                              "expect_line": "{interface_short} * connected *",
                              "poll": "errdisable-poll", "within": "errdisable-connect"}],
                  "reason": "bounce the port for the test, never saved"})
    monkeypatch.setitem(CP._BUILTIN, BOUNCE, t)
    return {"device": "s1", "interface": "Gi1/0"}


class TestNetZero:
    def test_a_plan_that_leaves_a_line_changed_is_rolled_back_and_refused(self, lab, bounce):
        # The port is shut in its running configuration: the bounce leaves it no-shut.
        lab["sw"] = Switch(state="disabled", admin_down=True)
        rec = go(lab, values=bounce, key=BOUNCE)
        assert rec["outcome"] == "not_net_zero", rec["why"]
        assert rec["net_zero"]["differs"] == ["-  shutdown"], rec["net_zero"]
        assert "-  shutdown" in rec["why"]
        assert lab["sw"].admin_down is True, "rolled back: the port is shut again, as before"
        assert lab["saved"] == []

    def test_a_device_departing_from_intent_is_bounced_the_plan_being_net_zero(
            self, lab, bounce, monkeypatch):
        # edge-a's running configuration holds a line its intent does not: a departure the
        # plan neither made nor changes.
        departs = T.s1_golden().replace("hostname s1\n", "hostname edge-a\n").replace(
            f"interface {PORT}\n", f"interface {PORT}\n description changed by hand\n", 1)
        lab["sw"] = Switch(state="connected", running=departs)
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda *_a, **_k: [{"hostname": "edge-a", "ip": "192.0.2.12",
                                                "device_type": "cisco_ios"}])
        monkeypatch.setattr("modules.neighbours.committed_intents_of",
                            lambda network: ({"edge-a": T.s1_intent()}, ""))
        src = sources(lab, name="edge-a", mgmt="192.0.2.12")
        rec = go(lab, values=dict(bounce, device="edge-a"), key=BOUNCE, sources=src)
        assert rec["outcome"] == "done", rec["why"]
        assert rec["net_zero"] == {"checked": True, "differs": [], "scope": "full"}

    def test_net_zero_compares_line_for_line_without_the_volatile_lines(self):
        before = "! Last configuration change at 1\nhostname a\nntp clock-period 1\n"
        after = "! Last configuration change at 2\nhostname a\nntp clock-period 2\n"
        assert CR.net_zero(before, after) == []
        assert CR.net_zero("hostname a\n", "hostname b\n") == ["- hostname a", "+ hostname b"]

    def test_a_line_the_rollback_cannot_undo_fails_never_rolled_back(self, lab):
        """The review of Gate 1a: the pipeline's rollback inverts only the plan's own lines; a
        sticky MAC the port learned as it came up is still there after it, so the run FAILS,
        naming it, never "rolled back"."""
        sticky = " switchport port-security mac-address sticky aabb.cc00.8099"
        lab["sw"] = Switch(sticky=sticky)
        rec = go(lab)
        assert rec["outcome"] == "failed" and rec["state"] == "failed", rec["why"]
        assert rec["net_zero"]["after_rollback"] == ["+ " + sticky], rec["net_zero"]
        assert "NOT RESTORED" in rec["why"] and sticky.strip() in rec["why"]


class PartialSwitch(Switch):
    """The fake switch whose first config batch stops part-way: its first *landed* lines take
    effect, then the session drops (the push never reaches verify)."""

    def __init__(self, landed=2, sticky_on_shut="", **kw):
        super().__init__(**kw)
        self.landed, self.failed_once = landed, False
        #: A line the port keeps once it is shut (one no rollback of the pushed lines
        #: removes), to tell the compare after the rollback ran.
        self.sticky_on_shut = sticky_on_shut

    def apply(self, lines):
        if self.failed_once:
            return super().apply(lines)
        self.failed_once = True
        super().apply(lines[:self.landed])
        if self.sticky_on_shut:
            self.base = self.base.replace(f"interface {PORT}\n",
                                          f"interface {PORT}\n{self.sticky_on_shut}\n", 1)
        raise OSError("Socket is closed")


class TestTheCompareAfterEveryRollback:
    """17215a95 (the review of 2026-11-16): after EVERY rollback, whether or not the run's own
    net-zero check ran (a push that stopped part-way never reaches verify), the configuration
    is read again and compared with the one before, in the whole where the run's check never
    ran; a line still differing fails the run, NOT RESTORED, never "rolled back"."""

    def test_a_partial_push_is_compared_after_its_rollback(self, lab):
        lab["sw"] = PartialSwitch()
        rec = go(lab)
        nz = rec.get("net_zero") or {}
        assert nz.get("after_rollback") == [] and nz.get("after_rollback_scope") == "full", nz
        assert lab["sw"].admin_down is False, "the rollback undid the shutdown that landed"
        assert rec["outcome"] == "rolled_back", rec["why"]

    def test_a_line_left_after_a_partial_pushs_rollback_is_not_restored(self, lab):
        left = " description left by the stopped push"
        lab["sw"] = PartialSwitch(sticky_on_shut=left)
        rec = go(lab)
        assert rec["outcome"] == "failed", rec["why"]
        assert rec["net_zero"]["after_rollback"] == ["+ " + left], rec["net_zero"]
        assert "NOT RESTORED" in rec["why"] and left.strip() in rec["why"]


# ── A person's Approve covers a plan's provisional shapes (32ad9360) ───────────────────────

PROVISIONAL = "provisional-test"
#: A shape no probe has measured, held provisional by the AI's proposal in each test.
SHAPE = "interface {interface} > description x"


@pytest.fixture
def provisional(monkeypatch, lab):
    """A planted plan holding one provisional shape (`SHAPE`) beside the bounce's measured
    lines, its shape proposed by the AI (held PROVISIONAL)."""
    t = CP.parse({"kind": "command_plan", "key": PROVISIONAL, "title": "Mark {device}",
                  "words": "a bounce with a provisional line, for the test", "net_zero": True,
                  "parameters": {"device": {"type": "device"},
                                 "interface": {"type": "interface"}},
                  "steps": [{"mode": "config", "commands": LAUNCH + [" description x"]}],
                  "verify": [{"name": "connected", "read": "show interfaces status",
                              "expect_line": "{interface_short} * connected *",
                              "poll": "errdisable-poll", "within": "errdisable-connect"}],
                  "reason": "a provisional line for the test, never saved"})
    monkeypatch.setitem(CP._BUILTIN, PROVISIONAL, t)
    assert POL.propose(NET, "cisco_ios", SHAPE, by="the AI (call c-1)",
                       why="a test")["state"] == "provisional"
    return {"device": "s1", "interface": "Gi1/0"}


class TestAPersonsPlan:
    """32ad9360 (the operator, 2026-11-17: "A person's Approve on a shown plan is the only
    approval. It covers any provisional shapes in that plan"): a person's plan previews and
    runs its provisional shapes; refused words, literal objects and unknown shapes still
    refuse; the hash and the program are the same either way."""

    def test_a_provisional_shape_refuses_only_outside_a_persons_plan(self, provisional):
        strict = CP.preview(NET, PROVISIONAL, provisional, sources=Model())
        person = CP.preview(NET, PROVISIONAL, provisional, sources=Model(), person_plan=True)
        assert not strict["ok"] and any("PROVISIONAL" in r for r in strict["refusals"]), \
            strict["refusals"]
        assert person["ok"], person["refusals"]
        # The flag changes no hash: the same plan once an admin approves the shape.
        assert POL.approve(NET, "cisco_ios", SHAPE, actor=ACTOR, actor_verified="access",
                           person=True, admin=True)["ok"]
        approved = CP.preview(NET, PROVISIONAL, provisional, sources=Model())
        assert approved["ok"], approved["refusals"]
        assert person["hash"] == approved["hash"] and person["program"] == approved["program"]

    def test_a_shape_never_proposed_still_refuses_a_persons_plan(self, lab, monkeypatch):
        t = CP.parse({"kind": "command_plan", "key": "unknown-test", "title": "U {device}",
                      "words": "an unknown line, for the test", "net_zero": True,
                      "parameters": {"device": {"type": "device"},
                                     "interface": {"type": "interface"}},
                      "steps": [{"mode": "config",
                                 "commands": LAUNCH + [" ip address 192.0.2.9 255.255.255.0"]}],
                      "verify": [{"name": "connected", "read": "show interfaces status",
                                  "expect_line": "{interface_short} * connected *",
                                  "poll": "errdisable-poll", "within": "errdisable-connect"}],
                      "reason": "an unknown line for the test, never saved"})
        monkeypatch.setitem(CP._BUILTIN, "unknown-test", t)
        got = CP.preview(NET, "unknown-test", {"device": "s1", "interface": "Gi1/0"},
                         sources=Model(), person_plan=True)
        assert not got["ok"] and "not a shape Mercury has measured" in got["refusals"][0], got

    def test_a_refused_word_is_refused_whoever_approves(self):
        with pytest.raises(CP.Refused, match="never sends in a command plan"):
            CP.parse({"kind": "command_plan", "key": "word-test", "title": "W {device}",
                      "words": "a refused word", "net_zero": True,
                      "parameters": {"device": {"type": "device"},
                                     "interface": {"type": "interface"}},
                      "steps": [{"mode": "config", "commands": LAUNCH + [" do reload"]}],
                      "verify": [], "reason": "a refused word for the test"})

    def test_a_persons_approved_plan_sends_its_provisional_line(self, lab, provisional):
        p = CP.preview(NET, PROVISIONAL, provisional, sources=Model(), person_plan=True)
        rec = go(lab, values=provisional, key=PROVISIONAL, confirmed=p["hash"])
        approve = next(s for s in rec["steps"] if s["step"] == "approve")
        assert approve["result"] == "ok", rec["why"]
        assert lab["sw"].batches and " description x" in lab["sw"].batches[0], rec["why"]

    def test_an_automatic_fix_with_a_provisional_shape_sends_nothing(self, lab, provisional,
                                                                     monkeypatch):
        """An Automatic fire runs only the plan shape that was approved (the operator's ruling
        4, 2026-11-18, C4043: "Bring back: ... the approved shape for Automatic fires", which
        70e89a47 had removed): a saved fix's run on its promoter's standing approval
        (*authority*) previews strictly, so a shape held PROVISIONAL refuses, naming it, and
        nothing is sent; once an admin approves the shape the same run sends. Its fire's and
        offer's previews (`saved_plans.fire`, `script_preview`) say the same."""
        from modules.nsot import saved_plans as S
        monkeypatch.setattr(S, "authority_refusal", lambda key, authority, network="": "")
        # The fire's other stops pass (Auto, nothing held): only the shape is judged here.
        monkeypatch.setattr("modules.heal.decide.script_hold", lambda *a, **kw: None)
        monkeypatch.setattr("modules.heal.act.stopped_now", lambda network: "")
        p = CP.preview(NET, PROVISIONAL, provisional, sources=Model(), person_plan=True)
        rec = go(lab, values=provisional, key=PROVISIONAL, confirmed=p["hash"],
                 authority={"script": PROVISIONAL})
        assert rec["outcome"] == "refused" and not lab["sw"].batches, rec["why"]
        assert "PROVISIONAL" in rec["why"] and "Nothing was sent" in rec["why"], rec["why"]
        e = {"key": PROVISIONAL, "network": NET}
        monkeypatch.setattr(S, "fill", lambda entry, prob: dict(provisional))
        prob = types.SimpleNamespace(as_dict=dict)
        assert S._previewed(NET, e, prob) == {}
        assert S._previewed(NET, e, prob, person=True)["hash"] == p["hash"]
        assert POL.approve(NET, "cisco_ios", SHAPE, actor=ACTOR, actor_verified="access",
                           person=True, admin=True)["ok"]
        rec = go(lab, values=provisional, key=PROVISIONAL, confirmed=p["hash"],
                 authority={"script": PROVISIONAL})
        assert lab["sw"].batches and " description x" in lab["sw"].batches[0], rec["why"]

    def test_an_automatic_fire_with_a_provisional_shape_starts_no_run(self, lab, provisional,
                                                                       monkeypatch):
        """The fire itself previews strictly (1d44aea9; the operator's ruling 4, 2026-11-18,
        C4043). The independent review found its mutant (`fire`'s preview back to
        `person_plan=True`) surviving every test, held only by the run's own strict preview:
        an Automatic fire on a PROVISIONAL shape starts no run, and its row says why."""
        from modules.nsot import saved_plans as S
        e = {"key": PROVISIONAL, "network": NET, "mode": "auto", "name": "the fix under test",
             "promoted_by": "p@example.invalid"}
        monkeypatch.setattr(S, "scripts", lambda network: {PROVISIONAL: e})
        monkeypatch.setattr(S, "mode_now", lambda entry, hm: "auto")
        monkeypatch.setattr(S, "_claim", lambda key, inc, m, retry="": ({"id": "row1"}, None))
        monkeypatch.setattr(S, "fill", lambda entry, prob: dict(provisional))
        settled, ran = [], []
        monkeypatch.setattr(S, "_settle", lambda key, rid, **kw: (settled.append(kw), {})[1])
        monkeypatch.setattr(S, "_run_as_job",
                            lambda network, e, values, confirmed, incident, **kw:
                            (ran.append(confirmed), {"outcome": "refused", "id": "r"})[1])
        monkeypatch.setattr("modules.heal.decide.script_hold", lambda *a, **kw: None)
        got = S.fire(NET, PROVISIONAL, None, "inc-1", sources=Model())
        assert ran == [], "an Automatic fire on a provisional shape started a run"
        assert not got["ok"] and "PROVISIONAL" in got["words"], got
        assert settled and "PROVISIONAL" in settled[-1].get("words", ""), settled


# ── Run… on built-in fixes (fc937efe) ───────────────────────────────────────────────────────

def _classified():
    """s1's incident, classified by the recovery's own step from its evidence (an
    err-disable by BPDU guard on Gi1/0): ``incident_page.resolve``'s answer for it."""
    from modules import incident_page
    iid = T.opened("Critical syslog received")["incident"]
    T.opened("Interface down", PORT, at=T.AT + 20)
    T.E.reclassify_step(NET, sources=T.Src(), now=T.AT + 600)
    return incident_page.resolve(NET, iid)


class TestTheBuiltInOffer:
    """fc937efe (the operator, 2026-11-17: Run… on built-in fixes, "the same as saved fixes"):
    a built-in plan offered on its incident takes exactly its declared parameters, filled from
    the incident, previewed as a person's plan, its hash the one the press is held to; a
    parameter the incident does not say is named, nothing offered to run; on a chosen device
    only the types Run… can choose from what Mercury holds."""

    def test_its_values_are_the_incidents_own_and_only_its_declared_ones(self, lab):
        from modules import fix_page
        t = CP.builtin()[KEY]
        values, why = fix_page.builtin_values(t, _classified())
        assert why == "" and set(values) == set(t.parameters), (values, why)
        assert values["device"] == "s1" and values["cause"] == "bpduguard", values
        assert values["interface"] == PORT, values

    def test_the_offer_is_a_persons_preview_its_hash_the_press_is_held_to(self, lab):
        from modules import fix_page
        found = _classified()
        offer = fix_page.builtin_offer(NET, found, KEY)
        assert offer["key"] == KEY and offer["hash"], offer
        values, _why = fix_page.builtin_values(CP.builtin()[KEY], found)
        p = CP.preview(NET, KEY, values, person_plan=True)
        assert offer["hash"] == p["hash"] and offer["values"] == values

    def test_a_parameter_the_incident_does_not_say_is_named(self, lab):
        from modules import fix_page
        found = _classified()
        rec = dict(found["incident"])
        rec[T.E.FIELD] = dict(T.E.of_record(rec), port="")
        got, why = fix_page.builtin_values(CP.builtin()[KEY], dict(found, incident=rec))
        assert got == {} and "does not say which interface" in why, why

    def test_no_plan_or_no_incident_page_is_no_offer(self, lab):
        from modules import fix_page
        found = _classified()
        assert fix_page.builtin_offer(NET, found, "no-such-plan") == {}
        assert fix_page.builtin_offer(NET, dict(found, found="none"), KEY) == {}

    def test_a_chosen_device_takes_only_what_mercury_can_choose(self):
        from modules import fix_page
        got = fix_page.builtin_port(CP.builtin()[KEY])
        assert got == {"iface": True, "choices": {"cause": ["bpduguard", "psecure-violation"]},
                       "subs": []}, got
        free = dataclasses.replace(CP.builtin()[KEY], parameters=dict(
            CP.builtin()[KEY].parameters, note={"type": "text"}))
        assert fix_page.builtin_port(free) is None


# ── The scoped net-zero and the pooled session (7b300f39, C3847) ───────────────────────────

class SectionSwitch(Switch):
    """The fake switch answering an interface's own section read
    (`pipeline.SECTION_READ`) from its running configuration, as IOS frames it (``Building
    configuration...``, ``Current configuration : N bytes``, the section, ``end``); an
    interface the configuration does not hold, or one of *absent* (an interface not created
    yet, as the section read sees it), answers IOS's ``%`` error."""

    def __init__(self, absent=(), **kw):
        super().__init__(**kw)
        self.absent = tuple(absent)

    def answer(self, command: str) -> str:
        from modules.pipeline import SECTION_READ
        prefix = SECTION_READ.format(name="")
        if not command.startswith(prefix):
            return super().answer(command)
        self.reads.append(command)
        name = command[len(prefix):]
        if name in self.absent:
            return ("                          ^\n"
                    "% Invalid input detected at '^' marker.\n")
        lines, keep = [], False
        for ln in self.running().splitlines():
            if ln == f"interface {name}":
                keep = True
            elif keep and not ln.startswith(" "):
                break
            if keep:
                lines.append(ln)
        if not lines:
            return ("                          ^\n"
                    "% Invalid input detected at '^' marker.\n")
        body = "\n".join(lines) + "\n"
        return (f"Building configuration...\n\nCurrent configuration : {len(body)} bytes\n"
                f"!\n{body}end\n")


class TestTheScopedNetZero:
    """7b300f39 (C3847, the operator, 2026-11-16): a plan whose every line is a
    section-confined shape on one interface compares that interface's own section before and
    after, read on the run's session, never the whole configuration; after a rollback, the
    same scope; a section that cannot be read keeps the whole compare."""

    def test_a_plan_on_one_interface_compares_that_section_alone(self, lab):
        lab["sw"] = SectionSwitch()
        rec = go(lab)
        assert rec["outcome"] == "done", rec["why"]
        assert rec["net_zero_scope"] == {"scope": "interfaces", "interfaces": [PORT]}
        assert rec["net_zero"] == {"checked": True, "differs": [], "scope": "interfaces",
                                   "interfaces": [PORT]}, rec["net_zero"]
        assert f"show running-config interface {PORT}" in lab["sw"].reads

    def test_a_partial_push_on_a_scoped_plan_is_compared_in_its_scope(self, lab):
        """C3868 (closed as overtaken): a push that stops part-way never reaches the run's own
        check, and its compare after the rollback still keeps the plan's interface scope, never
        the whole configuration, because stage 4 read the plan's sections alone
        (`running_config_sections`, e400a31f's item 5)."""
        class PartialSectionSwitch(PartialSwitch, SectionSwitch):
            pass
        lab["sw"] = PartialSectionSwitch()
        rec = go(lab)
        nz = rec.get("net_zero") or {}
        assert rec["net_zero_scope"] == {"scope": "interfaces", "interfaces": [PORT]}, rec
        assert nz.get("after_rollback_scope") == "interfaces", nz
        assert nz.get("after_rollback") == [] and rec["outcome"] == "rolled_back", rec["why"]

    def test_a_sticky_line_in_the_section_is_caught_by_the_scoped_compare(self, lab):
        sticky = " switchport port-security mac-address sticky aabb.cc00.8099"
        lab["sw"] = SectionSwitch(sticky=sticky)
        rec = go(lab)
        assert rec["outcome"] == "failed", rec["why"]
        nz = rec["net_zero"]
        assert nz["scope"] == "interfaces" and nz["differs"] == ["+ " + sticky], nz
        # The compare after the rollback keeps the run's own scope.
        assert nz["after_rollback_scope"] == "interfaces", nz
        assert nz["after_rollback"] == ["+ " + sticky], nz
        assert "NOT RESTORED" in rec["why"]

    def test_a_section_that_cannot_be_read_keeps_the_whole_compare(self, lab):
        # The section read answers IOS's `%` error (as for an interface the plan would
        # create): the whole configuration is compared, the reason said, never a pass on a
        # section never read.
        lab["sw"] = SectionSwitch(absent=(PORT,))
        rec = go(lab)
        assert rec["net_zero_scope"] == {
            "scope": "full", "why": "an interface's configuration before could not be read"}
        assert rec["net_zero"]["scope"] == "full", rec["net_zero"]

    @pytest.mark.parametrize("commands, program, scoped", [
        (["interface {interface}", " shutdown", " no shutdown"],
         [f"interface {PORT}", " shutdown", " no shutdown"], [PORT]),
        (["interface {interface}", " no shutdown"], ["interface Vlan99", " no shutdown"],
         ["Vlan99"]),
        (["interface {interface}", " description {interface}"],
         [f"interface {PORT}", f" description {PORT}"], []),
        (["interface {interface}", " shutdown"], [f"interface {PORT} x", " shutdown"], []),
        (["interface {interface}", " shutdown"], [f"interface {PORT}"], [])])
    def test_the_scope_is_the_interfaces_of_section_confined_lines_only(
            self, commands, program, scoped):
        t = dataclasses.replace(CP.builtin()[KEY], commands=tuple(commands))
        assert CR.net_zero_scope(t, program) == scoped


class TestTheSnapshotScope:
    """7b300f39 (the operator's R3 decision, 2026-11-16): the snapshots are scoped by what the
    plan touches: an access port in committed intent reads its own state and spanning tree
    (``access``); a trunk or routed port the full snapshots (``routed``); a port-channel
    member, an interface intent gives no mode, or a line not confined to a section, the full
    (``full``); and a device whose own configuration before departs from intent's access
    mode, or makes the port a member, refuses with nothing sent."""

    @staticmethod
    def scope(interface, intent=None):
        class Src:
            def intent(self, host):
                return (intent if intent is not None else T.s1_intent()), ""

        class Run:
            device, sources = "s1", Src()
        t = CP.builtin()[KEY]
        program = [f"interface {interface}", " shutdown", " no shutdown"]
        return CR.snapshot_scope(NET, t, {"program": program}, Run())

    def test_an_access_port_in_intent_is_the_access_rule(self):
        got = self.scope(PORT)
        assert (got["rule"], got["interfaces"]) == ("access", [PORT]), got
        assert CR.ACCESS_UNSEEN in got["words"]

    def test_a_trunk_is_the_routed_rule(self):
        got = self.scope("GigabitEthernet0/3")
        assert got["rule"] == "routed" and "(trunk)" in got["words"], got

    def test_an_interface_intent_gives_no_mode_is_the_full_rule(self):
        got = self.scope("GigabitEthernet0/1")
        assert got["rule"] == "full" and "no switchport mode" in got["words"], got

    def test_a_port_channel_member_is_the_full_rule(self):
        intent = T.s1_intent()
        for i in intent["interfaces"]:
            if i["name"] == PORT:
                i["channel_group"] = "1"
        got = self.scope(PORT, intent)
        assert got["rule"] == "full" and "port-channel member" in got["words"], got

    @pytest.mark.parametrize("section, said", [
        (" switchport mode trunk", "does not hold `switchport mode access`"),
        (" switchport mode access\n channel-group 1 mode active", "port-channel member")])
    def test_the_device_departing_from_the_access_rule_refuses(self, section, said):
        scope = {"rule": "access", "interfaces": [PORT]}
        running = f"hostname s1\n!\ninterface {PORT}\n{section}\n!\nend\n"
        got = CR._live_mode_refusal(scope, running)
        assert said in got and got.endswith("Nothing was sent"), got
        held = f"hostname s1\n!\ninterface {PORT}\n switchport mode access\n!\nend\n"
        assert CR._live_mode_refusal(scope, held) == ""


class TestTheSpanningTreeVerdict:
    """7b300f39: an access port's spanning tree read again after the settle and judged
    (`pipeline._stp_verdict`), on s1's captured rows with one edit each: broken or a guard's
    inconsistency, a role only another bridge gives, forwarding lost are issues; a `%` reply
    or no state neither passes nor fails, or judges nothing."""

    @pytest.mark.parametrize("edit, said", [
        (("Desg FWD 4         128.4    P2p \nVLAN0020", "Desg BKN*4        128.4    P2p \n"
                                                       "VLAN0020"), "broken or held"),
        (("VLAN0020            Desg FWD 4         128.4    P2p ",
          "VLAN0020            Desg FWD 4         128.4    P2p *ROOT_Inc"), "broken or held"),
        (("VLAN0030            Desg FWD", "VLAN0030            Altn BLK"), "a switch is behind"),
        (("VLAN0030            Desg FWD", "VLAN0030            Root FWD"), "a switch is behind"),
        (("VLAN0030            Desg FWD", "VLAN0030            Back BLK"), "a switch is behind"),
        (("VLAN0030            Desg FWD", "VLAN0030            Desg LRN"), "forwarded in")])
    def test_each_issue_is_named(self, edit, said):
        from modules import pipeline as P
        after = STP_ROWS.replace(*edit, 1)
        assert after != STP_ROWS
        got = P._stp_verdict(STP_ROWS, after)
        assert len(got["issues"]) == 1 and said in got["issues"][0], got

    def test_the_same_rows_after_are_no_issue(self):
        from modules import pipeline as P
        got = P._stp_verdict(STP_ROWS, STP_ROWS)
        assert got["issues"] == [] and got["unreadable"] == "", got

    @pytest.mark.parametrize("after", ["% Invalid input detected at '^' marker.\n", None])
    def test_an_unreadable_answer_neither_passes_nor_fails(self, after):
        from modules import pipeline as P
        got = P._stp_verdict(STP_ROWS, after)
        assert got["issues"] == [] and got["unreadable"], got

    def test_no_state_after_judges_nothing(self):
        from modules import pipeline as P
        got = P._stp_verdict(STP_ROWS, "no spanning tree info available for GigabitEthernet1/0")
        assert got == {"before": P._stp_rows(STP_ROWS)["words"],
                       "after": "no spanning-tree state (the port takes part in no instance)",
                       "issues": [], "unreadable": ""}


class TestThePooledSession:
    """7b300f39: the read engine's session rides the run's pooled session, and a read of
    another address or as another account is refused, never sent on it (IPv4 and IPv6, an
    IPv6 address written two ways being one)."""

    @pytest.fixture
    def pooled(self, monkeypatch):
        got = []
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda dev, pool, lock: (got.append(dev["ip"]), "conn")[1])

        class Ctx:
            connections_pool, pool_lock = {}, None
        return Ctx(), got

    @pytest.mark.parametrize("ip, signed", [
        ("192.0.2.11", "192.0.2.11"), ("2001:db8::11", "2001:DB8:0::11")])
    def test_the_same_address_and_account_reads_on_the_session(self, pooled, ip, signed):
        ctx, got = pooled
        session = CR.pool_session(ctx, {"ip": ip, "username": "mercury"})
        assert session({"ip": signed, "username": "mercury"}, lambda c: c) == "conn"
        assert got == [ip]

    @pytest.mark.parametrize("ip, signed, user", [
        ("192.0.2.11", "192.0.2.12", "mercury"), ("192.0.2.11", "192.0.2.11", "other"),
        ("2001:db8::11", "2001:db8::12", "mercury"), ("2001:db8::11", "2001:db8::11", "other")])
    def test_another_address_or_account_is_never_read_on_it(self, pooled, ip, signed, user):
        ctx, got = pooled
        session = CR.pool_session(ctx, {"ip": ip, "username": "mercury"})
        with pytest.raises(ValueError, match="it is not read on that session"):
            session({"ip": signed, "username": user}, lambda c: c)
        assert got == [], "nothing was asked of the pool"

    @pytest.mark.parametrize("ip", ["192.0.2.11", "2001:db8::11"])
    @pytest.mark.parametrize("run_user, read_user", [("", "mercury-ro"), ("mercury", "")])
    def test_an_account_not_named_on_either_side_is_never_read_on_it(
            self, pooled, ip, run_user, read_user):
        """C3852: a run whose row names no account (resolved at connect time) never carries a
        read-only read on its deploy-account session, nor a run's named session a read whose
        account is unknown: an empty name is no match."""
        ctx, got = pooled
        session = CR.pool_session(ctx, {"ip": ip, "username": run_user})
        with pytest.raises(ValueError, match="it is not read on that session"):
            session({"ip": ip, "username": read_user}, lambda c: c)
        assert got == [], "nothing was asked of the pool"


# ── C3847's follow-ups (ec92d62b): the stage callback, verify's own step, stage 7's read ────

def _stub_stages(monkeypatch, order, raise_at=""):
    """Every pipeline stage replaced by one that records its name in *order* (stage
    *raise_at* raising `PipelineStageError`), the rollback and the failure capture too."""
    import modules.pipeline as P

    def stage(ctx, _n):
        order.append(_n)
        if _n == raise_at:
            raise P.PipelineStageError(f"{_n} failed for the test")
    for name in P.STAGE_NAMES:
        monkeypatch.setattr(P, f"_stage_{name}", lambda ctx, _n=name: stage(ctx, _n))
    monkeypatch.setattr(P, "_stage_rollback", lambda ctx: order.append("rollback"))
    monkeypatch.setattr(P, "_capture_failure_state", lambda ctx: None)


class TestTheStageCallback:
    """ec92d62b: `PipelineContext.on_stage` hears each stage's start and its end, or its
    failure before any rollback the stage starts; a callback that raises changes nothing the
    run does; a run with none calls nothing."""

    def test_each_stage_is_told_as_it_starts_and_ends(self, monkeypatch):
        import modules.pipeline as P
        from tests.test_held_save import _ctx

        order = []
        _stub_stages(monkeypatch, order)
        ctx = _ctx()
        ctx.on_stage = lambda stage, event: order.append((stage, event))
        P.PipelineRunner(ctx).run()
        ran = [n for n in order if isinstance(n, str) and n != "audit_log"]
        assert ran and ctx.final_status == "success", order
        told = [e for e in order if isinstance(e, tuple)]
        assert told == [(n, ev) for n in ran for ev in ("start", "end")], told

    def test_a_callback_that_raises_changes_nothing_the_run_does(self, monkeypatch):
        import modules.pipeline as P
        from tests.test_held_save import _ctx

        plain, raising = [], []
        _stub_stages(monkeypatch, plain)
        ctx = _ctx()
        P.PipelineRunner(ctx).run()
        _stub_stages(monkeypatch, raising)
        ctx2 = _ctx()

        def boom(stage, event):
            raise RuntimeError("the callback fails")
        ctx2.on_stage = boom
        P.PipelineRunner(ctx2).run()
        assert raising == plain and ctx2.final_status == ctx.final_status == "success"
        assert ctx2.stages_failed == [] and ctx2.error == ctx.error

    def test_a_stage_error_is_told_before_its_rollback(self, monkeypatch):
        import modules.pipeline as P
        from tests.test_held_save import _ctx

        order = []
        _stub_stages(monkeypatch, order, raise_at="verify")
        ctx = _ctx()
        ctx.push_results = {ctx.device_ips[0]: {"ok": True}}
        ctx.on_stage = lambda stage, event: order.append((stage, event))
        P.PipelineRunner(ctx).run()
        assert ("verify", "failed") in order and "rollback" in order, order
        assert order.index(("verify", "failed")) < order.index("rollback"), order
        assert ("verify", "end") not in order

    def test_a_run_with_no_callback_calls_nothing(self, monkeypatch, caplog):
        import modules.pipeline as P
        from tests.test_held_save import _ctx

        order = []
        _stub_stages(monkeypatch, order)
        ctx = _ctx()
        assert ctx.on_stage is None
        with caplog.at_level("ERROR", logger="modules.pipeline"):
            P.PipelineRunner(ctx).run()
        assert ctx.final_status == "success"
        assert "on_stage callback raised" not in caplog.text


class TestVerifysOwnStep:
    """ec92d62b: a command plan run records verify as its own step as stage 8 ends, with when
    it began and its own seconds, once, after the send's step."""

    def test_verify_is_recorded_with_its_start_and_seconds(self, lab):
        rec = go(lab)
        assert rec["outcome"] == "done", rec["why"]
        steps = [s["step"] for s in rec["steps"]]
        assert steps.count("verify") == 1 and steps.index("send") < steps.index("verify")
        v = next(s for s in rec["steps"] if s["step"] == "verify")
        assert v["began"] and v["started"] == v["began"], v
        assert isinstance(v["took_s"], float) and v["took_s"] >= 0, v


class TestStageSevensRead:
    """ec92d62b (the operator's R3 answer (a)): a transient run with nothing that reads the
    configuration after (no removal, no re-created IP SLA, no IP SLA compare) has stage 7 read
    none, said why; every other run reads it; BGP's hold times are then taken from the
    configuration before."""

    @staticmethod
    def ctx(transient=True, **over):
        from tests.test_held_save import _ctx
        c = _ctx()
        c.transient = transient
        for k, v in over.items():
            setattr(c, k, v)
        return c

    def test_a_transient_run_reads_no_configuration_after(self):
        import modules.pipeline as P
        c = self.ctx()
        assert "net-zero check reads the configuration after" in P._post_config_not_read(
            c, c.device_ips[0])

    def test_an_access_rule_run_says_the_rules_words(self):
        import modules.pipeline as P
        c = self.ctx()
        ip = c.device_ips[0]
        c.snapshot_scope = {ip: {"rule": "access", "interfaces": [PORT], "words": "the rule"}}
        assert P._post_config_not_read(c, ip) == "the rule"

    def test_a_deploy_or_restore_still_reads_it(self):
        import modules.pipeline as P
        c = self.ctx(transient=False)
        assert P._post_config_not_read(c, c.device_ips[0]) == ""

    @pytest.mark.parametrize("what", ["units", "recreates", "ip_sla"])
    def test_a_transient_run_that_reads_it_after_still_reads_it(self, what):
        import modules.pipeline as P
        c = self.ctx()
        ip = c.device_ips[0]
        if what == "ip_sla":
            c.expect_ip_sla = {ip: ["1"]}
        else:
            c.removals = {ip: {what: ["x"]}}
        assert P._post_config_not_read(c, ip) == ""

    def test_bgps_hold_is_read_from_before_when_stage_7_read_none(self):
        import modules.pipeline as P
        pre = {"running_config": "router bgp 65001\n"}
        assert P._hold_config(pre, {"running_config": "",
                                    "running_config_scoped": "a transient run"}) == \
            pre["running_config"]
        assert P._hold_config(pre, {"running_config": "after\n"}) == "after\n"
        assert P._hold_config(pre, {"running_config": "",
                                    "running_config_sections": [PORT]}) == \
            pre["running_config"]

    def test_a_plan_run_reads_the_whole_configuration_once_after(self, lab):
        rec = go(lab)
        assert rec["outcome"] == "done", rec["why"]
        # Stage 4's read before and the net-zero check's after: stage 7 adds none.
        assert lab["sw"].reads.count("show running-config") == 2, lab["sw"].reads


class TestTheCosmeticScope:
    """ec92d62b: a deploy or restore whose every line is cosmetic (`verify_scope.COSMETIC`)
    reads no routing or interface snapshots; any other line, a transient run, a re-created IP
    SLA, an IP SLA compare, a paired link or a declared effect keeps the full ones."""

    @staticmethod
    def scope(program, transient=False, **over):
        import modules.pipeline as P
        from tests.test_held_save import _ctx
        c = _ctx()
        ip = c.device_ips[0]
        c.transient = transient
        c.rendered_commands = {ip: list(program)}
        for k, v in over.items():
            setattr(c, k, {ip: v})
        return P._cosmetic_scope(c, ip)

    @pytest.mark.parametrize("program, what", [
        (["interface GigabitEthernet0/1", " description uplink"], "descriptions"),
        (["interface GigabitEthernet0/1", " no description"], "descriptions"),
        (["banner motd ^Cauthorised use only^C"], "banners"),
        (["snmp-server location rack 4", "interface GigabitEthernet0/1",
          " description uplink"], "SNMP location")])
    def test_every_line_cosmetic_is_the_cosmetic_rule(self, program, what):
        got = self.scope(program)
        assert got["rule"] == "cosmetic" and what in got["words"], got

    @pytest.mark.parametrize("program", [
        ["interface GigabitEthernet0/1", " description uplink", " shutdown"],
        ["interface Loopback9"],
        ["default interface GigabitEthernet0/1"],
        ["ip sla 5", " icmp-echo 192.0.2.1"],
        []])
    def test_any_other_line_keeps_the_full_snapshots(self, program):
        assert self.scope(program) == {}

    @pytest.mark.parametrize("over", [
        {"transient": True}, {"removals": {"recreates": ["1"]}}, {"expect_ip_sla": ["1"]},
        {"pair_transient": {"peer": "r2"}}, {"expected_effects": {"declared": ["x"]}}])
    def test_a_run_with_its_own_verify_keeps_the_full_snapshots(self, over):
        program = ["interface GigabitEthernet0/1", " description uplink"]
        transient = over.pop("transient", False)
        assert self.scope(program, transient=transient, **over) == {}


class TestTheRecoveryTable:
    """ec92d62b: the errdisable-recover plan reads the switch's own recovery table (`show
    errdisable recovery`, s1's capture): Disabled passes, Enabled fails, anything else is
    unreadable, said; a script saved before keeps its config-filter read, and the check then
    reads the table itself on the run's session."""

    def test_s1s_table_reads_bpduguard_disabled(self):
        got = T.E.recovery_timer(T.text("s1_errdisable_recovery.txt"), "bpduguard")
        assert got["state"] == "disabled" and got["row"].startswith("bpduguard"), got
        assert "psecure-violation" in got["reasons"]

    @pytest.mark.parametrize("text, why", [
        (None, "no answer"),
        ("% Invalid input detected at '^' marker.\n", "the device answered"),
        ("", "the answer is empty"),
        ("errdisable recovery cause bpduguard\n", "holds no `ErrDisable Reason"),
        ("ErrDisable Reason            Timer Status\n-----------------"
         "            --------------\nudld                         Disabled\n",
         "lists no row for bpduguard")])
    def test_each_unreadable_shape_is_said(self, text, why):
        got = T.E.recovery_timer(text, "bpduguard")
        assert got["state"] == "unreadable" and why in got["why"], got

    def test_an_old_scripts_filter_read_reads_the_table_itself(self):
        asked = []

        class Src:
            def read(self, device, commands):
                asked.append((device, tuple(commands)))
                return {T.E.RECOVERY_READ: T.text("s1_errdisable_recovery.txt")}

        class Run:
            device, sources = "s1", Src()
            derived = {"interface": PORT, "cause": "bpduguard", "interface_short": "Gi1/0"}
        result, words = T.E.check_no_recovery("errdisable recovery interval 300\n", Run())
        assert asked == [("s1", (T.E.RECOVERY_READ,))]
        assert result == "pass" and "Disabled" in words, words

    def test_the_tables_own_answer_is_judged_with_no_second_read(self):
        class Src:
            def read(self, device, commands):
                raise AssertionError("the table was already read")

        class Run:
            device, sources = "s1", Src()
            derived = {"interface": PORT, "cause": "bpduguard", "interface_short": "Gi1/0"}
        enabled = T.text("s1_errdisable_recovery.txt").replace(
            "bpduguard                    Disabled", "bpduguard                    Enabled", 1)
        result, words = T.E.check_no_recovery(enabled, Run())
        assert result == "fail" and "does not race it" in words, words


# ── Preconditions batching (f86bcf7f) ───────────────────────────────────────────────────────

@pytest.fixture
def engine_runs(monkeypatch, lab):
    """Each read-engine run (`reads.run`) a plan run makes, with how many batches the switch
    had been sent when it was asked (0: before the send)."""
    from modules.nsot import reads

    real, got = reads.run, []

    def spy(network, hosts, commands, *a, **k):
        got.append({"commands": list(commands), "sent": len(lab["sw"].batches)})
        return real(network, hosts, commands, *a, **k)
    monkeypatch.setattr(reads, "run", spy)
    return got


class TestTheRunReadsLive:
    """55c8a8eb (the operator, 2026-11-16; CLAUDE.md's display-only rule): the approved run
    reads its device live, always: a `Sources` carrying a proposal's kept reads
    (`command_plan_run.Reused`) handed to `run` is replaced by a live one, so not one of its
    reads is answered from the kept store. The kept store here answers every command, so a
    run that took it would read nothing from the switch. The debt pass, 2026-11-18
    (docs/FAST_LANE_DEBT.md's row for 55c8a8eb)."""

    class AnswersAll(CR.Reused):
        def take(self, host, command):
            self.taken = getattr(self, "taken", 0) + 1
            return {"answer": "", "at": 0.0, "run": "", "from": "kept", "command": command,
                    "age_s": 1.0}

    def test_a_run_handed_kept_reads_reads_its_device_live(self, lab):
        src = sources(lab)
        src.reuse = kept = self.AnswersAll(clock=lambda: lab["t"])
        rec = go(lab, sources=src)
        assert (rec["outcome"], rec["state"]) == ("done", "done"), rec["why"]
        assert lab["sw"].reads, "the switch was read"
        assert getattr(kept, "taken", 0) == 0, "no read answered from the kept store"


class TestThePreconditionsBatch:
    """f86bcf7f (the operator, 2026-11-16): a run's preconditions ask every device read in ONE
    read-engine run, each check judged from that run's own answers; a refused run leaves every
    command unanswered and the plan refuses; a read beside the device's (G7's Loki lines) that
    raises or overruns its bound refuses; the run's sources are restored before verify, which
    reads live."""

    def test_the_preconditions_are_one_engine_run(self, lab, engine_runs):
        rec = go(lab)
        assert rec["outcome"] == "done", rec["why"]
        before = [r for r in engine_runs if r["sent"] == 0]
        assert len(before) == 1, before
        asked = before[0]["commands"]
        assert T.E.CONFIRM_READ in asked and T.E.RECOVERY_READ in asked, asked

    def test_each_check_is_judged_from_its_own_answer(self, lab):
        rec = go(lab)
        got = {p["name"]: p for p in rec["preconditions"]}
        assert got["The port is err-disabled by the cause now"]["result"] == "pass"
        assert got["The switch does not recover the cause itself"]["result"] == "pass"
        assert "Disabled" in got["The switch does not recover the cause itself"]["words"]

    def test_a_refused_engine_run_leaves_every_command_unanswered(self, monkeypatch):
        """The review's finding (2026-11-16): one refused run leaves EVERY command unanswered,
        never the rest answered one by one, also when the list is asked in runs of
        `reads.MAX_COMMANDS`."""
        from modules.nsot import reads

        monkeypatch.setattr(reads, "MAX_COMMANDS", 1)
        src = CR.Sources(NET, model=Model())
        monkeypatch.setattr(src, "_engine_run", lambda host, cmds: (
            None if "show b" in cmds else {c: "answered" for c in cmds}))
        assert src.read("s1", ["show a", "show b", "show c"]) == {
            "show a": None, "show b": None, "show c": None}
        monkeypatch.setattr(src, "_engine_run", lambda host, cmds: {c: "answered"
                                                                    for c in cmds})
        assert src.read("s1", ["show a", "show b"]) == {"show a": "answered",
                                                        "show b": "answered"}

    def test_a_read_beside_the_devices_that_raises_refuses(self, lab, monkeypatch):
        lab["sw"] = Switch(state="err-disabled", cause="psecure-violation")

        def raises(self, dev, since, until):
            raise ConnectionError("Loki answered nothing")
        monkeypatch.setattr("modules.heal.errdisable.Sources.lines", raises)
        rec = go(lab, values=dict(VALUES, cause="psecure-violation"))
        assert rec["outcome"] == "refused" and lab["sw"].batches == [], rec["why"]
        assert "Loki answered nothing" in rec["why"], rec["why"]

    def test_a_read_beside_the_devices_that_overruns_refuses(self, lab, monkeypatch):
        import threading
        lab["sw"] = Switch(state="err-disabled", cause="psecure-violation")
        release = threading.Event()

        def slow(self, dev, since, until):
            release.wait(5)
            return {"error": "", "cut": False, "lines": []}
        monkeypatch.setattr("modules.heal.errdisable.Sources.lines", slow)
        monkeypatch.setattr(CR, "AHEAD_JOIN_S", 0.05)
        try:
            rec = go(lab, values=dict(VALUES, cause="psecure-violation"))
        finally:
            release.set()
        assert rec["outcome"] == "refused" and lab["sw"].batches == [], rec["why"]
        assert "did not answer within" in rec["why"], rec["why"]

    def test_verify_reads_live_after_the_preconditions(self, lab, engine_runs):
        rec = go(lab)
        assert rec["outcome"] == "done", rec["why"]
        after = [r for r in engine_runs if r["sent"] > 0]
        assert after, "verify asked the device through the engine after the send"
        # The re-trip check reads `show interfaces status err-disabled` again after the send,
        # live, never the precondition's answer of the same command from before it.
        assert any(T.E.CONFIRM_READ in r["commands"] for r in after), after


# ── The review of Gate 1a ───────────────────────────────────────────────────────────────────

class TestTheReview:
    def test_bpdu_guards_cleared_is_deferred_to_verify_never_passed(self, lab):
        rec = go(lab)
        assert rec["outcome"] == "done", rec["why"]
        got = {p["name"]: p for p in rec["preconditions"]}
        cleared = got["The cause has cleared"]
        assert cleared["result"] == "deferred" and "cannot be told while the port is down" in \
            cleared["words"], cleared
        step = next(s for s in rec["steps"] if s["step"] == "preconditions")
        assert "judged by verify" in step["words"] and "The cause has cleared" not in \
            step["words"].split("not told")[0], step["words"]

    @pytest.mark.parametrize("golden_line, mgmt", [
        (" ip address 192.0.2.11 255.255.255.0", "192.0.2.11"),
        (" ipv6 address 2001:DB8::11/64", "2001:db8::11")])
    def test_an_access_port_with_no_vlan_is_in_vlan_1(self, golden_line, mgmt):
        golden = f"interface Vlan1\n{golden_line}\n!\ninterface GigabitEthernet0/1\n"
        assert "VLAN 1" in CP.management_refusal(golden, mgmt, "GigabitEthernet0/1", "",
                                                 "access")
        assert CP.management_refusal(golden, mgmt, "GigabitEthernet0/1", "", "trunk") == ""

    @pytest.mark.parametrize("line, mgmt", [
        (" ip address 192.0.2.11 255.255.255.0", "192.0.2.11"), (" ip address dhcp", ""),
        (" ipv6 address 2001:DB8::11/64", "2001:db8::11"), (" ipv6 address dhcp", ""),
        (" ipv6 address autoconfig", "")])
    def test_mode_b_and_the_plan_read_the_management_path_one_way(self, line, mgmt):
        from modules.nsot import removal
        chains = removal._chains(f"interface GigabitEthernet0/0\n{line}\n!\n")
        assert removal._management_interfaces(chains, mgmt) == {"interface GigabitEthernet0/0"}
        assert "managed through" in CP.management_refusal(
            f"interface GigabitEthernet0/0\n{line}\n!\n", mgmt, "Gi0/0")

    def test_an_interface_name_from_intent_is_held_to_its_shape(self, monkeypatch):
        monkeypatch.setattr(CP, "_intent_iface", lambda intent, v: {
            "name": "GigabitEthernet1/0\nreload", "switchport_mode": "access"})
        got = CP.validate(NET, CP.builtin()[KEY], VALUES, sources=Model())
        assert not got["ok"] and "not an interface's name" in got["refusals"][0]


# ── The pipeline's new parts ────────────────────────────────────────────────────────────────

class TestThePipelinesHooks:
    def test_a_pre_apply_refusal_sends_nothing_and_reads_as_not_sent(self, monkeypatch):
        import modules.pipeline as P
        from modules.nsot import receipts
        from tests.test_held_save import _ctx

        order = []
        for name in P.STAGE_NAMES:
            if name == "audit_log":
                continue
            monkeypatch.setattr(P, f"_stage_{name}",
                                lambda ctx, _n=name: order.append(_n))
        monkeypatch.setattr(P, "_stage_audit_log", lambda ctx: order.append("audit_log"))
        ctx = _ctx()
        ctx.pre_apply = [lambda c: "", lambda c: "a precondition does not hold"]
        P.PipelineRunner(ctx).run()
        assert "deploy" not in order and order[-1] == "audit_log", order
        assert ctx.stages_failed == [P.PRE_APPLY] and ctx.final_status == "failed"
        assert ctx.error == "a precondition does not hold"
        assert not receipts.was_sent({"commands": ["x"], "stage": P.PRE_APPLY})

    def test_a_transient_run_is_never_saved_and_records_no_golden(self, monkeypatch):
        import modules.pipeline as P
        from tests.test_held_save import _ctx

        saves = []
        monkeypatch.setattr("modules.nsot.onboard.persist_on_device",
                            lambda *a, **k: (saves.append(a), {"ok": True})[1])
        ctx = _ctx()
        ctx.transient = True
        ctx.push_results = {ctx.device_ips[0]: {"ok": True}}
        ctx.verify_result = {ctx.device_ips[0]: {"ok": True}}
        P._stage_save_startup(ctx)
        P._stage_save_golden(ctx)
        assert saves == [] and ctx.golden_result.get("transient") is True


class TestAttribution:
    def test_mercurys_own_config_session_is_mercurys(self, lab):
        from modules.heal import attribution

        rec = go(lab)
        mid = (float(rec["started_at"]) + float(rec["finished_at"])) / 2
        got = attribution.attribute(NET, "s1", mid)
        assert got["by"] == attribution.MERCURY, got["words"]


class TestOneWayIn:
    def test_the_step_is_reached_only_through_its_declarations_apply(self, monkeypatch):
        from modules import plan_engine as PE
        from modules.heal import catalog

        called = []

        def spy(network, params, confirmed_hash, *, actor, reason, actor_verified="",
                person=False):
            called.append((network, confirmed_hash, actor))
            return {"ok": True, "outcome": "done", "words": "", "receipt": {}}
        monkeypatch.setitem(catalog.COMMAND_PLANS, KEY,
                            dataclasses.replace(catalog.COMMAND_PLANS[KEY], apply=spy))
        PE.STEP_KINDS[KEY].apply(NET, {"incident": "hi-abcdef", "proposal": "p1"}, "h1",
                                 actor=ACTOR, reason="r", actor_verified="access", person=True)
        assert called == [(NET, "h1", ACTOR)]
        src = inspect.getsource(PE)
        assert "command_plan_run" not in src, "the plan engine reaches the runner only " \
                                              "through the declaration"

    def test_the_declaration_carries_the_registry_fields(self):
        from modules.heal import catalog
        d = catalog.COMMAND_PLANS[KEY]
        assert d.binds == CP.BINDS and d.conditions == ("net_zero",)
        assert [p.name for p in d.params] == ["device", "interface", "cause"]
        params = inspect.signature(d.apply).parameters
        assert list(params)[:3] == ["network", "params", "confirmed_hash"]
        for name in ("actor", "reason"):
            assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
        got = d.preflight(NET, VALUES, sources=Model())
        # Premise corrected (55c8a8eb, the operator, 2026-11-16: a step's preconditions read
        # are kept with the proposal, each said): the preflight answers what it checked too.
        assert set(got) == {"ok", "refused", "drawn", "hash", "checked"} and got["ok"], got

    def test_no_separate_send_path_remains_for_the_recovery(self):
        from modules.heal import errdisable
        for gone in ("apply", "start", "program", "_send", "_held", "_rollback", "_verify"):
            assert not hasattr(errdisable, gone), gone
        # Premise corrected (17215a95, the operator, 2026-11-16: the lost stream's rungs 2 and
        # 3 are built-in command plans beside the recovery, on the same runner): three built-in
        # plans, the recovery among them, and no other send path for it.
        assert json.dumps(sorted(CP.builtin())) == json.dumps(sorted([
            KEY, "telemetry-stack-restart", "telemetry-subscription-recreate"]))


#: What the lost stream's rungs 2 and 3 once promised, and 32ad9360 made untrue: a person's
#: Approve of a shown plan covers its provisional shapes (the operator, 2026-11-17).
NO_LONGER_TRUE = ("admin's approval before it can run", "nothing runs before")


@pytest.mark.parametrize("key", ["telemetry-stack-restart", "telemetry-subscription-recreate"])
def test_a_rung_says_a_person_s_approve_sends_its_provisional_lines(key):
    """The plan card's words and the ladder's (sent to the AI) say what a person's Approve
    does (the correctness review's G1 MEDIUM-2): the rung's lines are shapes no probe has
    measured, and once they are held provisional, Approve of the plan that shows them sends
    them; never that they wait on an admin's approval, or that nothing runs before. The
    policy agrees: with each shape held provisional, the check's every refusal is a
    provisional one, the refusals a person's plan drops (`command_plan.preview`)."""
    from modules.fixit import ladder

    t = CP.builtin()[key]
    for gone in NO_LONGER_TRUE:
        assert gone not in t.words, t.words
    assert "Approve" in t.words and "sends them" in t.words, t.words
    (rung,) = [r for r in ladder.STREAM_LOST if any(
        s.get("operation") == key for s in r["steps"])]
    for gone in NO_LONGER_TRUE:
        assert gone not in rung["why"], rung["why"]
    shapes = [s for _raw, s in POL.shapes(t.commands)
              if s not in POL.MEASURED["cisco_iosxe"]]
    assert shapes, "the rung holds shapes no probe has measured"
    store = {"shapes": {POL.key_of("cisco_iosxe", s): {"dialect": "cisco_iosxe", "shape": s,
                                                       "state": "provisional"}
                        for s in shapes}}
    got = POL.check("cisco_iosxe", t.commands, tuple(CP.command_names(t.parameters)),
                    network=NET, store=store)
    assert got["refusals"] and sorted(got["provisional"]) == sorted(shapes), got
    assert len(got["refusals"]) == len(shapes), "every refusal is a provisional shape's"


class TestTheDevicesOwnIntent:
    """C3869: a plan needs only its own device's committed intent, so another device's file
    that does not parse refuses nothing; the device's own missing behind that error refuses,
    naming it, and a network whose intent reads cleanly answers {} for a device it lacks."""

    BROKEN = "host_vars/s9.yml does not parse: planted"

    def test_its_own_document_is_taken_when_another_file_fails(self, monkeypatch):
        monkeypatch.setattr("modules.neighbours.committed_intents_of",
                            lambda network: ({"s1": T.s1_intent()}, self.BROKEN))
        assert CP.Sources("Lab").intent("s1") == (T.s1_intent(), "")

    def test_its_own_missing_behind_the_error_refuses_naming_it(self, monkeypatch):
        monkeypatch.setattr("modules.neighbours.committed_intents_of",
                            lambda network: ({"s1": T.s1_intent()}, self.BROKEN))
        assert CP.Sources("Lab").intent("s9") == (None, self.BROKEN)

    def test_a_clean_read_answers_nothing_for_a_device_it_lacks(self, monkeypatch):
        monkeypatch.setattr("modules.neighbours.committed_intents_of",
                            lambda network: ({"s1": T.s1_intent()}, ""))
        assert CP.Sources("Lab").intent("s9") == ({}, "")
