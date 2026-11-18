"""An err-disabled switch port (C3712, G7; `modules/heal/errdisable.py`): its problem, its
classifier, the device read before any action, and Recover an err-disabled interface.

Every device answer here is a real capture (tests/fixtures/errdisable/README.md: s1's
``show interfaces status err-disabled`` and ``show interfaces status``, s1's lines in Loki, s5's
MAC table row and port-security lines, read through Mercury on 2026-11-14), with the one file
of port-security violation lines in Cisco's documented form, marked "documented, not captured"
until the trial's capture replaces it. s1's committed intent and golden are
tests/fixtures/committed/'s real files. The fake switch answers from those texts and changes a
port's state the way the trials measured: ``shutdown`` then ``no shutdown`` clears an
err-disable, and a cause still connected err-disables it again. No device, no network, no AI.

- **The problem** (the operator's walk items 1 and 3, 2026-11-15): "s1 Gi1/0 err-disabled by
  BPDU guard: h1 is offline" at warning, the same string as the incident's title, its BLUF and
  Needs attention; a port-security cause reads "err-disabled by port security"; the port role
  from intent's switchport mode; whether the cause has cleared (true, false or unknown, with
  when); a saved script's match fields are the problem's, and no alert name is among them.
- **The classifier**: from the device's own lines and the Interface down alert's port, which
  must agree; two ports, or an alert naming another port, classify nothing, said.
- **Re-classified without re-injection**: an open incident opened from "Critical syslog
  received" and "Interface down" is classified from its device's lines by the detect loop's
  step, and the device read (walk item 2) is kept and drawn as its evidence.
- **The recovery** is the built-in command plan (C3757, path 2), tested with its runner in
  tests/test_command_plan.py; here, that a proposal names it held to its schema, and only in
  its incident's confirmed scope.
- **Needs attention** (C3731): one row per incident, its alerts folded under it.
"""
import os
import re

import pytest
import yaml

from modules import bluf as B
from modules import problem as P
from modules.heal import errdisable as E

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "errdisable")
NET = "Default"
#: When s1's err-disable line arrived (its incident opened at 21:02:50 UTC, 2026-11-14).
AT = 1794776570.0
ACTOR = "operator@example.com"


def text(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def s1_intent() -> dict:
    with open(os.path.join(ROOT, "tests", "fixtures", "committed", "s1.yml"),
              encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def s1_golden() -> str:
    with open(os.path.join(ROOT, "tests", "fixtures", "committed", "s1.cfg"),
              encoding="utf-8") as fh:
        return fh.read()


def loki(name: str = "s1_loki_lines.txt", start: float = AT, step: float = 1.0) -> list:
    return [{"line": ln, "at": E._iso(start + n * step), "epoch": start + n * step}
            for n, ln in enumerate(text(name).splitlines())]


# ── A fake switch, answering from the captures ──────────────────────────────────────────────

#: s1's captured rows, by state, for Gi1/0 (`s1_status.txt`; its connected row is Gi1/1's
#: captured row with Gi1/0's name and VLAN: the one edit).
ROW_ERR = text("s1_status.txt").splitlines()[0]
ROW_OK = text("s1_status.txt").splitlines()[1].replace("Gi1/1     h2 - VLAN 20       ",
                                                       "Gi1/0     h1 - VLAN 10       ")
ROW_OK = ROW_OK.replace("connected    20 ", "connected    10 ")
ROW_OFF = ROW_OK.replace("connected   ", "disabled    ")
ROW_REASON = text("s1_status_errdisabled.txt").splitlines()[0]


class Switch:
    """s1 with Gi1/0 err-disabled by BPDU guard, as captured. *again*: the cause is still
    connected, so the port err-disables again on its no shutdown; *recovery*: its running
    configuration holds this errdisable recovery line; *cut*: the session is lost after
    ``shutdown``, leaving the port shut."""

    def __init__(self, again=False, recovery="", cut=False, cause="bpduguard", macs=None):
        self.state, self.again, self.recovery, self.cut = "err-disabled", again, recovery, cut
        self.cause, self.macs = cause, text("s5_mac_table_gi03.txt") if macs is None else macs
        self.batches, self.opened, self.reads = [], 0, []

    def status(self) -> str:
        row = {"err-disabled": ROW_ERR, "connected": ROW_OK, "disabled": ROW_OFF}[self.state]
        return row + "\n" + text("s1_status.txt").splitlines()[1] + "\n"

    def answer(self, command: str) -> str:
        self.reads.append(command)
        if command == E.CONFIRM_READ:
            if self.state != "err-disabled":
                return ""
            return ROW_REASON.replace("bpduguard", self.cause) + "\n"
        if command == E.STATUS_READ:
            return self.status()
        if command == E.RECOVERY_READ:
            return self.recovery
        if command.startswith("show mac address-table") or command == E.PSEC_READ:
            return self.macs
        return ""

    def send(self, lines: list):
        self.batches.append(list(lines))
        if "shutdown" in lines:
            self.state = "disabled"
            if self.cut:
                raise OSError("the session was lost")
        if "no shutdown" in lines:
            self.state = "err-disabled" if self.again else "connected"


class Conn:
    def __init__(self, sw: Switch):
        self.sw = sw

    def send_command_timing(self, command, **kw):
        lines = command.split("\n")
        if len(lines) == 1 and not lines[0].startswith(("configure", "interface")):
            return self.sw.answer(lines[0])
        self.sw.send(lines)
        return ""

    def disconnect(self):
        pass


class Src(E.Sources):
    """Every source the operation reads, from the captures and the fake switch; the clock moves
    only when the operation sleeps."""

    def __init__(self, network=NET, sw=None, lines=None, golden=None, mgmt="192.0.2.11",
                 device_name="s1", **kw):
        super().__init__(network)
        self.sw = sw or Switch()
        self.t = AT + 600
        self.clock = lambda: self.t
        self.sleep = self._sleep
        self._lines = loki() if lines is None else lines
        self._golden = s1_golden() if golden is None else golden
        self.mgmt, self.name, self.events = mgmt, device_name, []

    def _sleep(self, s):
        self.t += float(s)

    def device(self, host):
        return {"hostname": host, "ip": self.mgmt} if host == self.name else {}

    def intent(self, host):
        return s1_intent(), ""

    def golden(self, host):
        return self._golden, ""

    def lines(self, dev, since, until):
        return {"error": "", "lines": [ln for ln in self._lines
                                       if since <= ln["epoch"] <= until], "cut": False}

    def read(self, host, commands):
        return dict({c: self.sw.answer(c) for c in commands}, _run="r-test")

    def open(self, dev):
        self.sw.opened += 1
        return Conn(self.sw)

    def ask(self, conn, command):
        return conn.sw.answer(command)

    def values(self):
        return {}

    def notify(self, network, event):
        self.events.append(event)
        return {"ok": True, "sent": 1}


# ── The device's words ──────────────────────────────────────────────────────────────────────

class TestTheCapturesParse:
    def test_the_err_disabled_view_names_the_port_and_its_reason(self):
        assert E.status_rows(text("s1_status_errdisabled.txt"), reasons=True) == [
            {"port": "Gi1/0", "name": "h1 - VLAN 10", "status": "err-disabled",
             "reason": "bpduguard"}]

    def test_the_status_view_names_each_port_its_state_and_vlan(self):
        assert [(r["port"], r["status"], r["vlan"]) for r in
                E.status_rows(text("s1_status.txt"))] == [
            ("Gi1/0", "err-disabled", "10"), ("Gi1/1", "connected", "20")]

    def test_the_lines_say_the_port_the_cause_and_the_mac(self):
        got = [E.parse_line(ln) for ln in text("s1_loki_lines.txt").splitlines()]
        assert [(g["kind"], g["port"], g["cause"]) for g in got] == [
            ("bpdu", "Gi1/0", "bpduguard"), ("errdisable", "Gi1/0", "bpduguard"),
            ("down", "GigabitEthernet1/0", "")]
        v, e = [E.parse_line(ln) for ln in text("psecure_lines_documented.txt").splitlines()]
        assert (v["kind"], v["mac"], v["port"]) == ("violation", "aabb.cc00.8099",
                                                    "GigabitEthernet0/3")
        assert (e["kind"], e["cause"]) == ("errdisable", "psecure-violation")
        assert E.mac_colon(v["mac"]) == "aa:bb:cc:00:80:99"

    def test_a_line_that_only_resembles_one_is_not_read(self):
        assert E.parse_line("note: bpduguard error detected on Gi1/0, putting Gi1/0 in "
                            "err-disable state") == {}
        assert E.parse_line("%PM-4-ERR_DISABLE: something else on Gi1/0") == {}

    def test_the_mac_and_port_security_tables(self):
        assert E.mac_rows(text("s5_mac_table_gi03.txt")) == [
            {"vlan": "10", "mac": "aabb.cc00.8007", "type": "DYNAMIC", "port": "Gi0/3"}]
        assert E.violator_seen("aa:bb:cc:00:80:07", "GigabitEthernet0/3",
                               "", text("s5_mac_table_gi03.txt")) is True
        assert E.violator_seen("aa:bb:cc:00:80:99", "GigabitEthernet0/3",
                               "", text("s5_mac_table_gi03.txt")) is False
        assert E.violator_seen("aa:bb:cc:00:80:99", "Gi0/3", None, "") is None

    def test_errdisable_recovery_for_the_cause_or_all(self):
        assert E.recovery_for(s1_golden(), "bpduguard") == ""      # measured: none on s1
        assert E.recovery_for("errdisable recovery cause bpduguard\n", "bpduguard")
        assert E.recovery_for("errdisable recovery cause all\n", "psecure-violation")
        assert not E.recovery_for("errdisable recovery cause udld\n", "bpduguard")
        assert "port-security" in text("s5_gi03_running.txt")


# ── The problem ─────────────────────────────────────────────────────────────────────────────

def classified(device="s1", alerts=("GigabitEthernet1/0",), lines=None, **kw) -> dict:
    return E.classify(device, list(alerts), loki() if lines is None else lines,
                      intent=s1_intent(), now=AT + 60, **kw)


def found_for(c: dict, device="s1", confirmed=True) -> dict:
    if confirmed:
        c = dict(c, confirmed=E.confirmation(
            E.status_rows(text("s1_status_errdisabled.txt"), reasons=True), c["port"],
            c["cause"], E._iso(AT + 90)))
    return {"incident": {"device": device, "state": "standing", E.FIELD: c}, "entry": {},
            "decisions": []}


class TestTheProblem:
    def test_s1s_capture_classifies_as_its_port_cause_host_and_role(self):
        c = classified()
        assert (c["state"], c["port"], c["short"], c["cause"], c["host"], c["vlan"],
                c["port_role"]) == ("classified", "GigabitEthernet1/0", "Gi1/0", "bpduguard",
                                    "h1", "10", "access")
        assert (c["cleared"], c["cleared_at"]) == ("true", E._iso(AT + 60))

    def test_the_title_is_the_same_words_everywhere_at_warning(self):
        f = found_for(classified())
        title = "s1 Gi1/0 err-disabled by BPDU guard: h1 is offline"
        assert B.what_of(f) == title
        got = B.bluf(B.model_of(f))
        assert (got["what"], got["severity"]) == (title, "warning")
        from modules import incident_page as IP
        assert IP.title(f["incident"], {}, []) == title
        # s2's, named only by its record: no device is known to the product by name.
        f2 = found_for(classified(), device="s2")
        f2["incident"][E.FIELD]["host"] = "h3"
        assert B.what_of(f2) == "s2 Gi1/0 err-disabled by BPDU guard: h3 is offline"

    def test_port_security_reads_its_own_cause_and_mac(self):
        lines = loki("psecure_lines_documented.txt")
        c = E.classify("s5", ["GigabitEthernet0/3"], lines, intent={"interfaces": [
            {"name": "GigabitEthernet0/3", "description": "h7 - VLAN 10",
             "switchport_mode": "access", "switchport_access_vlan": "10"}]}, now=AT + 60)
        assert (c["cause"], c["mac"], c["host"], c["cleared"]) == (
            "psecure-violation", "aabb.cc00.8099", "h7", "unknown")
        f = {"incident": {"device": "s5", E.FIELD: c}, "entry": {}, "decisions": []}
        assert B.what_of(f) == "s5 Gi0/3 err-disabled by port security: h7 is offline"

    def test_the_schema_carries_port_role_and_cause_cleared_with_when(self):
        p = P.classify(found_for(classified()))
        assert set(p.as_dict()) == set(P.FIELDS)
        assert (p.condition, p.cause, p.port_role, p.cleared, p.cause_cleared) == (
            "err_disabled", "BPDU guard", "access", "true", "no_bpdu_since")
        assert p.cleared_at and p.cleared in P.CLEARED and p.cause_cleared in P.CLEARED_CHECKS
        trunk = dict(s1_intent())
        trunk["interfaces"] = [dict(i, switchport_mode="trunk") for i in trunk["interfaces"]]
        assert E.classify("s1", ["Gi1/0"], loki(), intent=trunk)["port_role"] == "trunk"

    def test_a_saved_script_matches_on_problem_fields_never_an_alert_name(self):
        assert set(P.MATCH_FIELDS) == {"condition", "cause", "port_role", "cleared"}
        assert set(P.MATCH_FIELDS) <= set(P.FIELDS)
        p = P.classify(found_for(classified())).as_dict()
        rules = {"Critical syslog received", "Interface down"}
        assert not rules & {str(p[k]) for k in P.MATCH_FIELDS}
        assert not {"rule", "alert", "line", "mnemonic"} & set(P.MATCH_FIELDS)

    def test_a_bpdu_after_the_err_disable_means_not_cleared(self):
        lines = loki() + [{"line": text("s1_loki_lines.txt").splitlines()[0],
                           "at": E._iso(AT + 30), "epoch": AT + 30}]
        c = classified(lines=lines)
        assert (c["cleared"], c["cleared_at"]) == ("false", E._iso(AT + 30))

    def test_evidence_and_alert_disagreeing_classify_nothing_said(self):
        c = classified(alerts=("GigabitEthernet1/1",))
        assert c["state"] == "unclassified"
        assert "GigabitEthernet1/1" in c["why"] and "Gi1/0" in c["why"]

    def test_two_ports_with_no_alert_naming_one_classify_nothing(self):
        two = loki() + [{"line": "%PM-4-ERR_DISABLE: bpduguard error detected on Gi1/1, "
                                 "putting Gi1/1 in err-disable state",
                         "at": E._iso(AT + 5), "epoch": AT + 5}]
        assert classified(alerts=(), lines=two)["state"] == "unclassified"
        assert classified(lines=two)["port"] == "GigabitEthernet1/0"

    def test_no_err_disable_line_is_no_problem_of_this_kind(self):
        c = classified(lines=loki()[2:])
        assert c["state"] == "unclassified" and "name no port" in c["why"]
        assert P.classify({"incident": {"device": "s1", E.FIELD: c}}).condition != \
            "err_disabled"

    def test_the_device_read_is_the_evidence_drawn_with_when(self):
        ev = P.evidence(found_for(classified()))
        read = [e for e in ev if e["kind"] == "device_read"]
        assert len(read) == 1 and read[0]["at"] == E._iso(AT + 90)
        assert "show interfaces status err-disabled read at" in read[0]["words"]
        assert "Gi1/0 err-disabled by bpduguard" in read[0]["words"]
        assert "agrees" in read[0]["words"]
        assert any(e["kind"] == "log" and "BLOCK_BPDUGUARD" in e["words"] for e in ev)

    def test_a_device_read_that_disagrees_is_said_and_takes_no_action(self):
        conf = E.confirmation([{"port": "Gi1/0", "reason": "psecure-violation"}],
                              "GigabitEthernet1/0", "bpduguard", "t")
        assert conf["agrees"] is False and "psecure-violation" in conf["why"]
        assert E.confirmation([], "GigabitEthernet1/0", "bpduguard", "t")["agrees"] is False


# ── Re-classified without re-injection ──────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path, monkeypatch):
    from tests.test_sdn_connections import make_networks
    return make_networks(tmp_path, monkeypatch)


def opened(rule: str, iface: str = "", at: float = AT + 1, device="s1") -> dict:
    from modules.heal import incidents
    return incidents.sight(NET, device, {
        "kind": "alert", "key": f"alert:{rule}:{iface}", "epoch": at, "at": E._iso(at),
        "source": "grafana-alerts", "rule": rule, "interface": iface,
        "words": f"the alert {rule} fired on {device}"}, now=at)


class TestReclassified:
    def test_a_standing_incident_is_classified_from_its_own_evidence(self, store):
        from modules.heal import incidents
        iid = opened("Critical syslog received")["incident"]
        opened("Interface down", "GigabitEthernet1/0", at=AT + 20)
        src = Src()
        got = E.reclassify_step(NET, sources=src, now=AT + 600)
        assert got["classified"] == [iid]
        inc = next(i for i in incidents.read(NET)["incidents"] if i["id"] == iid)
        c = E.of_record(inc)
        assert (c["port"], c["cause"], c["confirmed"]["agrees"]) == (
            "GigabitEthernet1/0", "bpduguard", True)
        assert src.sw.batches == [] and src.sw.reads == [E.CONFIRM_READ]
        # Once classified and confirmed, the next pass reads nothing again.
        again = Src()
        assert E.reclassify_step(NET, sources=again, now=AT + 700)["read"] == 0
        assert again.sw.reads == []

    def test_an_incident_with_no_err_disable_line_is_tried_again_later(self, store):
        opened("Critical syslog received")
        src = Src(lines=loki()[2:])
        assert E.reclassify_step(NET, sources=src, now=AT + 600)["classified"] == []
        assert E.reclassify_step(NET, sources=src, now=AT + 700)["read"] == 0
        assert E.reclassify_step(NET, sources=src, now=AT + 600 + E.RECHECK_S)["read"] == 1


# The recovery itself (its preview, its run, its refusals) is the built-in command plan's,
# tested where its runner is: tests/test_command_plan.py (C3757, path 2).

class TestTheCatalog:
    def test_a_proposal_names_it_as_a_built_in_command_plan_held_to_its_schema(self):
        from modules.heal import catalog
        op, held = catalog.checked(E.KEY, {"device": "s1", "interface": "Gi1/0",
                                           "cause": "bpduguard"})
        assert catalog.is_command_plan(E.KEY) and E.KEY not in catalog.CATALOG
        assert op.runs == "modules.nsot.command_plan_run.run"
        for bad in ({"interface": "Gi1/0; reload"}, {"cause": "all"},
                    {"interface": "show run"}):
            with pytest.raises(catalog.Refused):
                catalog.checked(E.KEY, dict({"device": "s1", "interface": "Gi1/0",
                                             "cause": "bpduguard"}, **bad))

    def test_a_proposal_acts_only_on_its_incidents_confirmed_port(self, store):
        from modules.heal import incidents
        iid = opened("Critical syslog received")["incident"]
        assert "not classified" in E.scope_refusal(NET, iid, "s1", "Gi1/0", "bpduguard")
        E.reclassify_step(NET, sources=Src(), now=AT + 600)
        assert E.scope_refusal(NET, iid, "s1", "Gi1/0", "bpduguard") == ""
        assert "acts only on what" in E.scope_refusal(NET, iid, "s1", "Gi1/1", "bpduguard")
        assert incidents.read(NET)["state"] == "ok"


# ── Needs attention (C3731) ─────────────────────────────────────────────────────────────────

class TestOneRowPerIncident:
    def rows(self, level="warning"):
        def grafana(rule, iface=""):
            return {"id": f"grafana:{rule}", "source": "grafana", "kind": "incident",
                    "level": level, "devices": ["s1"], "what": f"{rule} is alerting on s1",
                    "operands": {"members": [{"rule": rule, "device": "s1",
                                              "interface": iface}]}}
        parent = {"id": "heal:x", "source": "heal", "kind": "cant_fix", "level": "danger",
                  "devices": ["s1"], "what": "Self-healing could not fix s1",
                  "incident_page": {"id": "hi-e56afd12e1a6", "list": NET}}
        other = grafana("Interface down", "GigabitEthernet1/1")
        return [parent, grafana("Critical syslog received"),
                grafana("Interface down", "GigabitEthernet1/0"), other]

    def listed(self, condition="err_disabled"):
        title = "s1 Gi1/0 err-disabled by BPDU guard: h1 is offline"
        return {"unreadable": [], "rows": [{"id": "hi-e56afd12e1a6", "resolved": False,
                                            "bluf": {"what": title, "severity": "warning",
                                                     "problem": {"device": "s1",
                                                                 "object": "Gi1/0",
                                                                 "condition": condition}}}]}

    def read(self, _net):
        return {"incidents": [{"id": "hi-e56afd12e1a6", "triggers": [
            {"kind": "alert", "rule": "Critical syslog received"},
            {"kind": "alert", "rule": "Interface down", "interface": "GigabitEthernet1/0"}],
            E.FIELD: {"state": "classified", "port": "GigabitEthernet1/0"}}]}

    def test_its_alerts_fold_under_it_at_the_problems_level_and_words(self):
        from modules import attention as A
        got = A._fold_signals_into_problems(self.rows(), NET, self.listed(), read=self.read)
        assert [r["id"] for r in got] == ["heal:x", "grafana:Interface down"]
        top = got[0]
        assert (top["what"], top["level"]) == (
            "s1 Gi1/0 err-disabled by BPDU guard: h1 is offline", "warning")
        assert top["folded_evidence"] == 2
        assert [r["operands"]["members"][0]["rule"] for r in top["folded"]] == [
            "Critical syslog received", "Interface down"]
        # Another port's alert stays a row of its own.
        assert got[1]["operands"]["members"][0]["interface"] == "GigabitEthernet1/1"

    def test_a_proposal_row_under_an_info_incident_keeps_its_own_level(self):
        """A row that needs a person's decision ("needs your decision", warning) is never drawn
        unknown because its incident's severity is info; a folded member's higher one does not
        raise it (C3792)."""
        from modules import attention as A
        listed = self.listed()
        listed["rows"][0]["bluf"]["severity"] = "info"
        rows = self.rows(level="unknown")
        rows[0].update(kind="propose", level="warning",
                       what="s1 has a fix: it needs your decision")
        got = A._fold_signals_into_problems(rows, NET, listed, read=self.read)
        assert got[0]["level"] == "warning" and got[0]["folded_evidence"] == 2
        rows = self.rows(level="danger")
        rows[0].update(kind="propose", level="warning")
        got = A._fold_signals_into_problems(rows, NET, listed, read=self.read)
        # Premise corrected (C3792, the operator, 2026-11-15: "a folded alert's own label ...
        # is shown as evidence under it, never as the row's severity"): a danger alert folded
        # under it raised the row to danger before; the row keeps its own level, and the
        # alert keeps its own, as evidence.
        assert got[0]["level"] == "warning"
        assert [m["level"] for m in got[0]["folded"]] == ["danger", "danger"]

    def test_a_fold_never_hides_a_worse_alert(self):
        """A danger alert folded under a warning incident keeps its own level, marked as the
        incident's evidence, so the fold hides no severity (the review of Gate 1a). Premise
        corrected (C3792, the operator, 2026-11-15: "severity follows impact; one host offline
        is not an outage ... a folded alert's own label is shown as evidence under it, never
        as the row's severity"): it made the incident's row danger before; the row stays at
        its problem's impact, warning."""
        from modules import attention as A
        got = A._fold_signals_into_problems(self.rows(level="danger"), NET, self.listed(),
                                            read=self.read)
        assert got[0]["folded_evidence"] == 2 and got[0]["level"] == "warning"
        assert [(m["level"], m["evidence_of"]) for m in got[0]["folded"]] == [
            ("danger", "hi-e56afd12e1a6")] * 2

    def test_the_row_carries_its_problems_impact_and_draws_warning_over_a_critical_alert(self):
        """C3790 and C3792, drawn: the row's line is its title, then its problem's impact
        (Mercury's table), then the AI's status, each its own element under the title; the row
        is Warning, and each folded alert keeps its Critical label, marked as the incident's
        evidence."""
        from tests.test_needs_attention import _panel

        from modules import attention as A
        impact = B.bluf({"problem": P.Problem(device="s1", object="Gi1/0",
                                              condition="err_disabled", affected="h1")})["impact"]
        assert impact == ("h1 has no network until the port is recovered; the rest of the "
                          "network is unaffected")
        listed = self.listed()
        listed["rows"][0]["bluf"]["impact"] = impact
        rows = self.rows(level="danger")
        for r in rows:          # what the row constructor gives every row (`attention.row`)
            r.update(action={"label": f"Open {r['devices'][0]}"}, cause=r["what"])
        got = A._fold_signals_into_problems(rows, NET, listed, read=self.read)
        assert got[0]["impact"] == impact
        got[0]["ai_status"] = {"state": "ended", "since": "2026-11-15T17:00:00Z",
                               "words": "Mercury's fix failed once. Ask it again, or hand over."}
        html = _panel({"rows": got, "sources": [], "badge": {"n": len(got)}})
        line = html.split('data-attention-row="heal:x"')[1].split("</summary>")[0]
        assert '<span class="att-level">Warning</span>' in line, line
        title = line.index('class="att-what"')
        assert title < line.index('class="att-impact') < line.index('class="att-ai'), line
        assert f'title="{impact}">{impact}</span>' in line.replace("&#39;", "'")
        # The status's source as its label (00c70e0f, C3840: "the status line is one sentence
        # with its source as a label"), never "AI:" run into the words.
        assert re.search(r'<span class="badge badge-info">AI</span> Mercury\'s fix failed once\.',
                         line.replace("&#39;", "'")), line
        # Under the row (the other port's own "Interface down" row stands apart, at Critical).
        parent = html.split('data-attention-row="heal:x"')[1]
        for member in ("grafana:Critical syslog received", "grafana:Interface down"):
            sub = parent.split(f'data-attention-row="{member}"')[1].split("</summary>")[0]
            assert re.search(r'<span class="att-level" data-evidence-of="hi-e56afd12e1a6"'
                             r'[^>]*>Critical</span>', sub), sub
        assert "2 alerts under this incident, as its evidence" in html

    # C3791 (the operator, 2026-11-15, from r7's two rows on the host at 17:09 UTC: "One
    # problem, one row (C3731), and never offer an action that already failed on this
    # incident (R2)").
    IID = "hi-22cfdc299000"

    def stream_and_hold(self):
        ai = {"state": "ended", "since": "2026-11-15T17:00:00Z",
              "words": "Mercury's fix failed twice. Ask the AI again, or hand over."}
        page = {"id": self.IID, "list": NET}
        stream = {"id": "grafana:r7-streams", "source": "grafana", "kind": "incident",
                  "level": "warning", "devices": ["r7"], "networks": {"r7": [NET]},
                  "what": "r7: telemetry streams 101 and 102 lost",
                  "action": {"label": "Re-subscribe r7's telemetry", "open": "resubscribe",
                             "device": "r7", "subs": ["101", "102"]},
                  "operands": {"members": [
                      {"rule": "NMAS telemetry stream lost: r7 subscription 101",
                       "device": "r7", "interface": ""}]},
                  "incident_page": dict(page), "ai_status": dict(ai)}
        hold = {"id": "heal:hd-7080f74e58d2", "source": "heal", "kind": "held",
                "level": "warning", "devices": ["r7"], "networks": {"r7": [NET]},
                "what": "Self-healing holds r7 on Default: the device's golden departs from "
                        "its intent",
                "action": {"label": "Adopt the change into r7's intent"},
                "incident_page": dict(page), "ai_status": dict(ai)}
        # The hold first: a hold is never the problem's row while another row links it.
        return [hold, stream]

    def listed_r7(self):
        return {"unreadable": [], "rows": [{
            "id": self.IID, "resolved": False,
            "href": f"/v2/incident/{self.IID}?list={NET}",
            "bluf": {"what": "r7: telemetry streams 101 and 102 lost", "severity": "warning",
                     "impact": "Mercury can't see r7's interfaces or CPU; traffic is unaffected",
                     "fix": {"kind": "", "label": "Open the incident and decide what to do"},
                     "problem": {"device": "r7", "object": "telemetry streams 101 and 102",
                                 "condition": "telemetry_lost"}}}]}

    def read_r7(self, _net):
        return {"incidents": [{"id": self.IID, "triggers": [
            {"kind": "alert", "rule": "NMAS telemetry stream lost: r7 subscription 101"}]}]}

    def test_an_incidents_hold_folds_under_its_one_row(self):
        from modules import attention as A
        asked = []
        got = A._fold_signals_into_problems(
            self.stream_and_hold(), NET, self.listed_r7(), read=self.read_r7,
            failed=lambda lst, iid: asked.append((lst, iid)) or False)
        assert [r["id"] for r in got] == ["grafana:r7-streams"], [r["id"] for r in got]
        top = got[0]
        assert [m["id"] for m in top["folded"]] == ["heal:hd-7080f74e58d2"]
        assert top["folded"][0]["evidence_of"] == self.IID
        assert "ai_status" in top and "ai_status" not in top["folded"][0], "said once"
        assert asked == [(NET, self.IID)], "asked once, for the incident"
        # Not failed here: Re-subscribe stays its action.
        assert top["action"]["open"] == "resubscribe" and A.first_action(top) == "resubscribe"

    def test_a_resubscribe_that_failed_here_gives_way_to_the_incidents_next_action(self):
        from modules import attention as A
        got = A._fold_signals_into_problems(self.stream_and_hold(), NET, self.listed_r7(),
                                            read=self.read_r7, failed=lambda lst, iid: True)
        top = got[0]
        assert top["action"] == {"label": "Open the incident and decide what to do",
                                 "href": f"/v2/incident/{self.IID}?list={NET}"}, top["action"]
        assert A.first_action(top) not in ("resubscribe", "start"), A.first_action(top)

    def test_whether_a_fix_failed_here_is_the_incident_pages_own_test(self, monkeypatch):
        from modules import attention as A
        from modules import incident_page as IP
        from modules.fixit import incident as F
        from modules.fixit import section

        def attempt(state, passed):
            """One attempt as the troubleshooting record keeps it (`fixit.incident.attempts`)."""
            return {"n": 1, "run": "run-1", "device": "r7", "state": state, "passed": passed,
                    "at": "2026-11-15T17:00:00Z", "finished_at": None, "proposal": "",
                    "operation": "telemetry-resubscribe", "params": {}, "source": "person",
                    "actor": "op@example.com", "outcome": "", "words": ""}
        monkeypatch.setattr(IP, "resolve", lambda lst, iid: {"found": "page", "id": iid})
        monkeypatch.setattr(section, "incident_of", lambda lst, found: {"incident": object()})
        for attempts, want in (([attempt("ended", False)], True),
                               ([attempt("ended", True)], False),
                               ([attempt("running", False)], False), ([], False)):
            monkeypatch.setattr(F, "attempts", lambda inc, resolved, a=attempts: {
                "attempts": a})
            assert A._failed_here(NET, self.IID) is want, attempts

        def boom(inc, resolved):
            raise OSError("the record cannot be read")
        monkeypatch.setattr(F, "attempts", boom)
        assert A._failed_here(NET, self.IID) is False, "not known keeps the row's action"
        monkeypatch.setattr(section, "incident_of", lambda lst, found: {"incident": None})
        assert A._failed_here(NET, self.IID) is False, "no record, no attempt"

    # C3731's widening (the operator, 2026-11-15): every problem kind folds its own signals.
    @pytest.mark.parametrize("condition", ["link_down", "interface_shut", "port_stuck"])
    def test_a_problem_of_another_kind_folds_its_own_objects_signals(self, condition):
        from modules import attention as A
        got = A._fold_signals_into_problems(self.rows(), NET, self.listed(condition),
                                            read=self.read)
        assert [r["id"] for r in got] == ["heal:x", "grafana:Interface down"], condition
        assert got[0]["folded_evidence"] == 2 and got[0]["level"] == "warning"
        assert got[1]["operands"]["members"][0]["interface"] == "GigabitEthernet1/1"

    def test_another_object_or_a_signal_not_the_incidents_still_draws_its_own_row(self):
        from modules import attention as A

        def grafana(rule, iface="", device="r2"):
            return {"id": f"grafana:{rule}:{iface}", "source": "grafana", "kind": "incident",
                    "level": "danger", "devices": [device], "what": f"{rule} on {device}",
                    "operands": {"members": [{"rule": rule, "device": device,
                                              "interface": iface}]}}
        parent = {"id": "heal:y", "source": "heal", "kind": "cant_fix", "level": "danger",
                  "devices": ["r2"], "what": "r2's stream", "incident_page": {"id": "hi-abc123"}}
        rows = [parent, grafana("Telemetry stream lost"), grafana("CPU high"),
                grafana("Interface down", "GigabitEthernet2"), grafana("Telemetry stream lost",
                                                                       device="r3")]
        listed = {"unreadable": [], "rows": [{"id": "hi-abc123", "resolved": False, "bluf": {
            "what": "r2 lost telemetry subscription 101", "severity": "warning",
            "problem": {"device": "r2", "object": "101", "condition": "telemetry_lost"}}}]}

        def read(_net):
            return {"incidents": [{"id": "hi-abc123", "triggers": [
                {"kind": "alert", "rule": "Telemetry stream lost"}]}]}
        got = A._fold_signals_into_problems(rows, NET, listed, read=read)
        assert [r["id"] for r in got] == [
            "heal:y", "grafana:CPU high:", "grafana:Interface down:GigabitEthernet2",
            "grafana:Telemetry stream lost:"], [r["id"] for r in got]
        assert got[0]["folded_evidence"] == 1 and got[0]["what"] == (
            "r2 lost telemetry subscription 101")
        assert [r["devices"] for r in got[3:]] == [["r3"]], "another device's stays its own"


# ── The declared drill exercise (modules/fault_drills.py) ───────────────────────────────────

def _inv(_network, device):
    return {"hostname": device}


class TestTheDrillExercise:
    EXPECTS = "the rehearsal's BPDU guard and port security drills"

    def preview(self, devices=("s1", "s2", "s5"), minutes=60, now=AT):
        from modules import fault_drills as FD
        return FD.exercise_preview(NET, list(devices), minutes=minutes, expects=self.EXPECTS,
                                   now=now, inventory=_inv)

    def declare(self, words, devices=("s1", "s2", "s5"), minutes=60, now=AT):
        from modules import fault_drills as FD
        return FD.record_exercise(NET, list(devices), minutes=minutes, expects=self.EXPECTS,
                                  by=ACTOR, previewed=words, actor_verified="access",
                                  via="test", now=now, inventory=_inv)

    def test_one_declaration_over_several_devices_its_own_hour(self, store):
        from modules import fault_drills as FD
        seen = self.preview()
        assert seen["ok"] and "for 60 minutes" in seen["words"]
        got = self.declare(seen["words"], now=AT + 30)
        assert got["ok"], got
        r = got["record"]
        assert (r["kind"], r["devices"], r["minutes"], r["preview"]) == (
            "exercise", ["s1", "s2", "s5"], 60, seen["words"])
        # Each device's incident inside the hour is a drill; after it, real.
        for d in ("s1", "s2", "s5"):
            assert FD.tag_for(NET, d, AT + 59 * 60)["id"] == r["id"]
            assert FD.tag_for(NET, d, AT + 30 + 61 * 60) is None
        assert FD.tag_for(NET, "s3", AT + 60) is None
        assert FD.open_on(NET, "s2", AT + 120)["id"] == r["id"]

    def test_a_single_drill_keeps_its_fifteen_minutes(self, store):
        from modules import fault_drills as FD
        got = FD.record_declared(NET, "s1", minutes=60, expects="the BPDU guard drill on s1",
                                 by=ACTOR, actor_verified="access", via="test", now=AT,
                                 inventory=_inv)
        assert not got["ok"] and "1 to 15 minutes" in got["error"]
        assert not self.preview(minutes=121)["ok"]

    def test_an_exercise_not_the_one_previewed_is_refused(self, store):
        seen = self.preview(devices=("s1", "s2"))
        got = self.declare(seen["words"], devices=("s1", "s2", "s5"))
        assert not got["ok"] and "not the one previewed" in got["error"]

    def test_a_device_with_a_drill_or_an_incident_open_is_named(self, store):
        from modules import fault_drills as FD
        FD.record_declared(NET, "s2", minutes=10, expects="the BPDU guard drill on s2",
                           by=ACTOR, actor_verified="access", via="test", now=AT,
                           inventory=_inv)
        got = self.preview(now=AT + 60)
        assert not got["ok"] and got["error"].startswith("s2 has a fault drill declared")
        assert not self.preview(devices=("s1",))["ok"]

    def test_its_end_ends_it_on_every_device(self, store):
        from modules import fault_drills as FD
        r = self.declare(self.preview()["words"])["record"]
        got = FD.record_ended(NET, r["id"], by=ACTOR, actor_verified="access", via="test",
                              device="s5", now=AT + 600)
        assert got["ok"], got
        assert FD.open_on(NET, "s1", AT + 700) == {}


# ── Port security's cause cleared, judged while the port is down (the correctness review's
# G1 MEDIUM-1 and G3 M2, 2026-11-18) ─────────────────────────────────────────────────────────

#: s5's port-security view of Gi0/3 err-disabled: its capture (Secure-up, count 0) with the
#: status and the count the err-disable leaves (the two edits).
PSEC_DOWN = text("s5_port_security_gi03.txt").replace("Secure-up", "Secure-shutdown").replace(
    "Security Violation Count   : 0", "Security Violation Count   : 1")


class _PsecSources:
    def __init__(self, answer):
        self.answer = answer

    def read(self, host, commands):
        return {c: self.answer for c in commands}


def psec_run(lines, confirmed=None, answer=PSEC_DOWN):
    """A run of errdisable-recover on s5 Gi0/3 by port security, its lines (*lines*, Loki's
    answer) and the incident's classification read ahead, as a run's preconditions hand them."""
    import types
    c = {"epoch": AT, "mac": "aabb.cc00.8099"}
    if confirmed is not None:
        c["confirmed"] = confirmed
    return types.SimpleNamespace(
        derived={"interface": "GigabitEthernet0/3", "cause": "psecure-violation",
                 "interface_short": "Gi0/3"},
        ahead={"check_cause_cleared": {
            "c": c, "got": {"error": "", "lines": lines, "cut": False},
            "start": AT - E.LOOKBACK_S, "until": AT + 600}},
        sources=_PsecSources(answer), network=NET, incident="i-1", at=AT + 600,
        device="s5", dev={}, found={})


class TestPortSecurityWhileDown:
    """An err-disabled port is down, so no violation line and no count rise can arrive after
    the err-disable: finding none is an absence nothing showed could be found, never a pass.
    BPDU guard's branch already answers it deferred; port security's must too."""

    def test_psecure_cause_cleared_is_deferred_while_the_port_is_down(self):
        # s5's documented pair (violation and err-disable in the same second), nothing after,
        # and the confirmation read's count equal to now's.
        lines = loki("psecure_lines_documented.txt", step=0.0)
        run = psec_run(lines, confirmed={"epoch": AT + 5, "psec": {"violations": 1}})
        result, words = E.check_cause_cleared(None, run)
        assert result == "deferred", (result, words)
        assert "judged after the bounce" in words, words

    def test_psecure_cleared_is_never_passed_when_loki_holds_no_line_for_the_port(self):
        run = psec_run([])
        result, words = E.check_cause_cleared(None, run)
        assert result != "pass", (result, words)
        assert result in ("deferred", "unreadable"), (result, words)

    def test_a_violation_after_the_err_disable_still_fails(self):
        lines = loki("psecure_lines_documented.txt", step=0.0) + [{
            "line": text("psecure_lines_documented.txt").splitlines()[0],
            "at": E._iso(AT + 60), "epoch": AT + 60}]
        result, words = E.check_cause_cleared(None, psec_run(lines))
        assert result == "fail" and "Port stays down" in words, (result, words)


# ── One port's verified fix closes only an incident of that port (the correctness review's
# G3 M3, 2026-11-18) ─────────────────────────────────────────────────────────────────────────

def _standing(incident_id: str) -> None:
    from modules.heal import incidents

    def change(doc):
        inc = next(i for i in doc["incidents"] if i["id"] == incident_id)
        inc.update(state="standing", standing={"decision": "d-1", "outcome": "would_heal",
                                               "words": "a saved script fixes it"})
    incidents._mutate(NET, change)


class TestOnePortsFixClosesOnlyItsPort:
    """Incidents are one per device; a saved script's verified run recovers one port. An
    incident holding another port's symptom is not healed by it, so it stays standing."""

    def close(self, iid):
        from modules.heal import incidents
        from modules.nsot import saved_plans
        got = saved_plans.close_fixed(NET, iid, {"id": "run-00000001", "device": "s1",
                                                 "interface": "Gi1/0"},
                                      {"key": "sp-1", "name": "recover the port"}, "test")
        inc = next(i for i in incidents.read(NET)["incidents"] if i["id"] == iid)
        return got, inc

    def test_a_verified_port_fix_leaves_another_ports_symptom_standing(self, store):
        iid = opened("Critical syslog received")["incident"]
        opened("Interface down", "GigabitEthernet1/0", at=AT + 20)
        opened("Interface down", "GigabitEthernet2/0", at=AT + 25)
        _standing(iid)
        got, inc = self.close(iid)
        assert inc["state"] == "standing", (got, inc.get("closed"))
        assert got == {}, got

    def test_a_verified_port_fix_closes_an_incident_of_that_port_alone(self, store):
        iid = opened("Critical syslog received")["incident"]
        opened("Interface down", "GigabitEthernet1/0", at=AT + 20)
        _standing(iid)
        got, inc = self.close(iid)
        assert inc["state"] == "closed" and got, (got, inc.get("state"))
        assert inc["fixed"]["run"] == "run-00000001", inc.get("fixed")

    def test_a_verified_fix_closes_a_watching_incident_fixed(self, store):
        """Self-healing Off leaves an incident watching (1e49b3a9); a person's saved fix pressed
        on its card and verified closes it Fixed with the run as its fix, as a plan's verified
        run closes a watching one (`detect.close_verified`, ``also_watching``): the review of
        the device-write fixes, "1e49b3a9 and d1ee447f together"."""
        from modules.heal import incidents
        iid = opened("Critical syslog received")["incident"]
        opened("Interface down", "GigabitEthernet1/0", at=AT + 20)
        assert next(i for i in incidents.read(NET)["incidents"]
                    if i["id"] == iid)["state"] == "watching"
        got, inc = self.close(iid)
        assert inc["state"] == "closed" and got, (got, inc.get("state"))
        assert inc["fixed"]["run"] == "run-00000001", inc.get("fixed")
