"""P.9 step (c): a NEW device receives the network's monitoring profile before
its first golden, so it is monitored at promotion (the operator, 2026-10-01;
docs/MONITORING_PROFILE.md section 8).

A device being onboarded or adopted has no full intent: onboarding's is the
bootstrap, adopt's is nothing. So the profile's program is computed from the
device's CAPTURE (`profile_apply.for_capture`): its own parse rendered alone
and with the profile, the profile's missing lines what `scoped()` keeps, the
way `template_report` measures a template.

The lab is test_profile_apply's: r2's REAL config and intent, and r6 in its
real shape (r2's config without its SNMP and discovery lines).
"""

import json

import pytest

from tests.test_profile_apply import _commit_proposal, lab  # noqa: F401 (the fixture)


class TestTheProgramFromACapture:
    def test_r6_receives_the_profiles_lines_and_nothing_else(self, lab):
        from modules.nsot import profile_apply
        _commit_proposal()
        out = profile_apply.for_capture("Lab", "r6", "cisco_iosxe", "router", lab["r6"])
        assert out["applies"] is True, out["why"]
        sent = [c.strip() for c in out["commands"] if c.strip() != "exit"]
        assert sent and all(c.startswith("snmp") or c == "lldp run" for c in sent), sent
        masked = {c.strip() for c in out["masked"] if c.strip() != "exit"}
        assert {r["line"].strip() for r in out["to_send"]} == masked
        assert out["fingerprint"] and out["capture_hash"]

    def test_the_masked_program_holds_no_secret_value(self, lab):
        from modules.nsot import profile_apply
        _commit_proposal()
        out = profile_apply.for_capture("Lab", "r6", "cisco_iosxe", "router", lab["r6"])
        community = next(c.split()[2] for c in out["commands"]
                         if c.startswith("snmp-server community"))
        assert community not in json.dumps({k: v for k, v in out.items() if k != "commands"})
        assert any("<redacted" in m for m in out["masked"])

    def test_a_device_already_holding_the_profile_sends_nothing_and_says_so(self, lab):
        from modules.nsot import profile_apply
        _commit_proposal()
        out = profile_apply.for_capture("Lab", "r2", "cisco_iosxe", "router", lab["captured"])
        assert out["applies"] is True and out["commands"] == []
        assert "already holds every line" in out["why"]

    def test_no_profile_is_not_an_error_and_says_what_to_do(self, lab):
        from modules.nsot import profile_apply
        out = profile_apply.for_capture("Lab", "r6", "cisco_iosxe", "router", lab["r6"])
        assert out["applies"] is False and "no committed monitoring profile" in out["why"]
        assert out["commands"] == []

    def test_a_template_that_does_not_reproduce_the_device_is_not_trusted(self, lab):
        """The network's library template invents a line r6 lacks (test_one_
        template_resolver's edit): the program would be computed from a render
        that is not the device, so nothing is sent, and the template is named."""
        import os
        from modules.nsot import profile_apply, templates_repo
        _commit_proposal()
        mark = "ip tcp synwait-time 12"
        assert mark not in lab["r6"]
        path = os.path.join(templates_repo.templates_dir(lab["repo"]), "cisco_iosxe", "base.j2")
        first, rest = open(path, encoding="utf-8").read().split("\n", 1)
        open(path, "w", encoding="utf-8").write(f"{first}\n{mark}\n{rest}")
        out = profile_apply.for_capture("Lab", "r6", "cisco_iosxe", "router", lab["r6"])
        assert out["applies"] is False and "does not reproduce r6" in out["why"]
        assert "cisco_iosxe/base.j2" in out["why"] and "1 line(s) it invents" in out["why"]
        assert out["commands"] == []

    def test_a_line_the_parser_does_not_model_is_named_and_does_not_block(self, lab):
        """Measured: an unmodelled line counts as `unmodeled`, never as a render
        gap, and the program never touches it."""
        from modules.nsot import profile_apply
        _commit_proposal()
        odd = lab["r6"].replace("hostname r6", "hostname r6\nalias exec sib show ip int brief")
        out = profile_apply.for_capture("Lab", "r6", "cisco_iosxe", "router", odd)
        assert out["applies"] is True and out["commands"]
        assert out["unmodeled"] == ["alias exec sib show ip int brief"]

    def test_the_fingerprint_moves_with_the_capture_and_with_the_profile(self, lab):
        from modules.nsot import profile_apply
        _commit_proposal()
        a = profile_apply.for_capture("Lab", "r6", "cisco_iosxe", "router", lab["r6"])
        b = profile_apply.for_capture("Lab", "r6", "cisco_iosxe", "router",
                                      lab["r6"].replace("hostname r6", "hostname r6\n!"))
        assert a["fingerprint"] == profile_apply.for_capture(
            "Lab", "r6", "cisco_iosxe", "router", lab["r6"])["fingerprint"]
        assert a["fingerprint"] != b["fingerprint"]


# --------------------------------------------------------------- phase two

IP7 = "203.0.113.17"


@pytest.fixture
def pending(lab, monkeypatch):
    """r7, PENDING in the lab's list: r6's real shape (no SNMP, no LLDP), the
    profile proposed and committed, the staged credential in the override."""
    from modules import credentials
    from modules.nsot import manifest as _m
    from modules.nsot.repo import GoldenItem, adopt_identity
    from modules.nsot import profile_apply
    from modules.settings_schema import DEFAULTS
    # The lab's settings stub answers only what it names: give it the real
    # platform map, or no Netmiko driver resolves (stub drift, not the code).
    lab["settings"]["platform_map"] = DEFAULTS["platform_map"]
    _commit_proposal()
    identity = adopt_identity(lab["repo"], GoldenItem("r7", "", IP7))
    _m.upsert_device(lab["repo"], identity, "r7", mgmt_ip=IP7, platform="cisco_iosxe",
                     pending=True)
    credentials.set_device_override(IP7, "admin", "BootStrap7Value", "BootStrap7Value")
    before = lab["r6"].replace("hostname r6", "hostname r7")
    program = profile_apply.for_capture("Lab", "r7", "cisco_iosxe", "", before,
                                        repo=lab["repo"])["commands"]
    lines = [c for c in program if c.strip() != "exit"]
    after = before.replace("\nend", "\n" + "\n".join(lines) + "\nend")
    sent, rotated = [], []

    def _rotate(*a, **k):
        rotated.append(1)
        credentials.set_device_override(IP7, "admin", "R0tatedSeven7", "R0tatedSeven7")
        return {"rotated": True, "state": "rotated", "reason": ""}

    def steps(captures, send=None):
        it = iter(captures)
        return {"online": lambda ip: True, "reach": lambda *a, **k: "r7#",
                "capture": lambda *a, **k: {"ok": True, "config": next(it), "error": ""},
                "rotate": _rotate,
                "remove_rw": lambda *a, **k: {"ok": True, "removed": [], "kept": []},
                "persist": lambda *a, **k: {"ok": True, "detail": "carries it"},
                "netbox": lambda *a, **k: {"ok": True, "created": []},
                "promote": lambda *a, **k: {"ok": True},
                "send_profile": send or (lambda *a, **k: sent.append(a[-1]) or {"ok": True})}
    return {**lab, "before": before, "after": after, "program": program, "sent": sent,
            "rotated": rotated, "steps": steps}


class TestVerifyIsAPreviewAndAConfirm:
    def _plan(self, p):
        from modules.nsot.onboard import phase_two_plan
        s = p["steps"]([p["before"]])
        return phase_two_plan(p["repo"], "r7", "Lab", online=s["online"], reach=s["reach"],
                              capture=s["capture"])

    def test_the_preview_reads_and_names_the_profile_program_masked(self, pending):
        plan = self._plan(pending)
        assert plan["ok"] is True, plan["reason"]
        assert plan["profile"]["applies"] and plan["fingerprint"]
        assert any(l.startswith("snmp-server community <redacted") for l in plan["profile"]["masked"])
        community = next(c.split()[2] for c in pending["program"]
                         if c.startswith("snmp-server community"))
        assert community not in json.dumps(plan) and "commands" not in plan["profile"]
        assert pending["sent"] == [] and pending["rotated"] == []      # it sends nothing

    def test_confirmed_the_profile_is_sent_read_back_and_in_the_first_golden(self, pending):
        from modules.nsot.onboard import run_phase_two
        from modules.nsot.repo import committed_golden_for
        plan = self._plan(pending)
        out = run_phase_two(pending["repo"], "r7", "Lab", actor="op@example.invalid",
                            confirmed=plan["fingerprint"],
                            **pending["steps"]([pending["before"], pending["after"],
                                                pending["after"]]))
        assert out["ok"] is True, out["reason"]
        row = next(s for s in out["steps"] if s["step"] == "profile")
        assert row["ok"] and "sent and read back" in row["detail"]
        assert pending["sent"] == [pending["program"]]
        from modules.nsot import manifest as _m
        golden = committed_golden_for(pending["repo"], _m.find_by_name(pending["repo"], "r7")[1])
        golden = golden.get("text") or ""
        assert "snmp-server community" in golden and "lldp run" in golden

    def test_a_device_or_profile_that_moved_sends_nothing_at_all(self, pending):
        from modules.nsot.onboard import run_phase_two
        plan = self._plan(pending)
        moved = pending["before"].replace("hostname r7", "hostname r7\n!")
        out = run_phase_two(pending["repo"], "r7", "Lab", actor="op@example.invalid",
                            confirmed=plan["fingerprint"],
                            **pending["steps"]([moved]))
        assert out["ok"] is False and plan["fingerprint"] in out["reason"]
        assert "nothing was sent" in out["reason"]
        assert pending["rotated"] == [] and pending["sent"] == []

    def test_unconfirmed_the_profile_is_not_sent_and_says_so(self, pending):
        from modules.nsot.onboard import run_phase_two
        out = run_phase_two(pending["repo"], "r7", "Lab", actor="op@example.invalid",
                            **pending["steps"]([pending["before"], pending["before"]]))
        row = next(s for s in out["steps"] if s["step"] == "profile")
        assert row["ok"] and "not sent: Verify was not previewed" in row["detail"]
        assert pending["sent"] == []

    def test_a_line_that_did_not_land_fails_the_step_and_promotes_nothing(self, pending):
        from modules.nsot.onboard import run_phase_two
        plan = self._plan(pending)
        promoted = []
        steps = pending["steps"]([pending["before"], pending["before"]])
        steps["promote"] = lambda *a, **k: promoted.append(1) or {"ok": True}
        out = run_phase_two(pending["repo"], "r7", "Lab", actor="op@example.invalid",
                            confirmed=plan["fingerprint"], **steps)
        row = next(s for s in out["steps"] if s["step"] == "profile")
        assert out["ok"] is False and not row["ok"] and "not every line landed" in row["detail"]
        assert promoted == [] and out["promoted"] is False
        assert {r["step"] for r in out["remaining"]} >= {"persist", "golden", "promote"}

    def test_a_rejected_program_is_a_failed_step_naming_the_device_s_error(self, pending):
        from modules.nsot.onboard import run_phase_two
        plan = self._plan(pending)
        out = run_phase_two(
            pending["repo"], "r7", "Lab", actor="op@example.invalid",
            confirmed=plan["fingerprint"],
            **pending["steps"]([pending["before"]],
                               send=lambda *a, **k: {"ok": False, "error": "% Invalid input"}))
        row = next(s for s in out["steps"] if s["step"] == "profile")
        assert out["ok"] is False and "% Invalid input" in row["detail"]
        assert "the device is still pending" in out["reason"]


class TestTheRoutes:
    @pytest.fixture
    def routed(self, pending, monkeypatch):
        monkeypatch.setattr("modules.nsot.onboard.verify_device", lambda *a, **k: {
            "answered": True, "state": "answered", "mgmt_ip": IP7})
        monkeypatch.setattr("modules.nsot.onboard.capture_config", lambda *a, **k: {
            "ok": True, "config": pending["before"], "error": ""})
        return pending

    def test_the_preview_route_draws_the_program_masked_with_its_fingerprint(self, routed):
        r = routed["client"].post("/onboard/verify/r7/preview", json={"list_name": "Lab"})
        assert r.status_code == 200, r.get_json()
        prev = r.get_json()["preview"]
        (t,) = prev["what"]["targets"]
        assert t["selectable"] and t["select_data"]["list"] == "Lab"
        assert len(t["select_data"]["fingerprint"]) == 16
        lines = prev["targets"][0]["program"]["lines"]
        assert any(l.startswith("snmp-server community <redacted") for l in lines)
        community = next(c.split()[2] for c in routed["program"]
                         if c.startswith("snmp-server community"))
        assert community not in r.get_data(as_text=True)
        assert routed["sent"] == [] and routed["rotated"] == []

    def test_a_preview_of_a_device_that_did_not_answer_says_why(self, routed, monkeypatch):
        monkeypatch.setattr("modules.nsot.onboard.verify_device", lambda *a, **k: {
            "answered": False, "state": "did_not_answer", "error": "no answer on 22",
            "causes": [{"cause": "the management interface", "why": "w", "command": "c"}]})
        r = routed["client"].post("/onboard/verify/r7/preview", json={"list_name": "Lab"})
        d = r.get_json()
        assert r.status_code == 409 and d["error"] == "no answer on 22"
        assert d["causes"][0]["cause"] == "the management interface"

    def test_verify_refuses_with_no_preview_and_carries_the_one_it_was_given(self, routed,
                                                                              monkeypatch):
        c = routed["client"]
        r = c.post("/onboard/verify/r7", json={"list_name": "Lab"})
        assert r.status_code == 400 and "preview" in r.get_json()["error"]
        seen = {}
        monkeypatch.setattr("modules.nsot.onboard.run_phase_two",
                            lambda repo, host, lst, **k: seen.update(k) or {
                                "ok": False, "reason": "x", "steps": []})
        c.post("/onboard/verify/r7", json={"list_name": "Lab", "fingerprint": "abc"})
        assert seen["confirmed"] == "abc"

    def test_the_shipped_refusal_names_the_reason_and_the_causes_escaped(self):
        import os

        import dukpy
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(root, "static", "js", "gen", "partials__onboard_wizard.2.js"),
                   encoding="utf-8").read()
        from tests.payload_render import lift
        js = lift(src, "onboardVerifyRefusalHtml")
        html = dukpy.evaljs(js + "\nonboardVerifyRefusalHtml({error: 'no <answer>', causes: "
                                 "[{cause: 'the interface', why: 'w', command: 'show ip int'}]})")
        assert "no &lt;answer&gt;" in html and "the interface" in html and "show ip int" in html
