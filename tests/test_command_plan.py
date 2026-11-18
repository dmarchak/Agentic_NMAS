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

No device, no network, no AI.
"""
import dataclasses
import inspect
import json
import os

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
