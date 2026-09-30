"""P.9 step (b): PROPOSE the network's monitoring profile, and APPLY it (the
deploy plan scoped to the profile's lines), through the real routes.

The lab is r2's REAL config and committed intent (`test_capture`'s lab), plus
r6 in its real shape: r2's config with its `snmp-server` lines removed
(test_monitoring_coverage's fixture rule), its intent parsed from that. So r2
holds the fleet's SNMP and r6 lacks it: the situation P.9 exists for.
"""

import json
import os
import re
import subprocess

import pytest

from tests.test_capture import R2, build_capture_lab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _r6_config():
    text = open(R2, encoding="utf-8").read()
    # Every SNMP line, `snmp ifmib ifindex persist` included: a partial section
    # is a second VERSION of the fleet's SNMP, which the proposal (rightly)
    # refuses to reconcile (measured: it did, on the first run of this test).
    lines = [l for l in text.splitlines() if not l.lstrip().startswith("snmp")]
    return "\n".join(l.replace("hostname r2", "hostname r6") if l.startswith("hostname") else l
                     for l in lines) + "\n"


@pytest.fixture
def lab(monkeypatch, tmp_path):
    from modules.nsot import approval, hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars

    monkeypatch.setattr(approval, "is_approved", lambda repo, t: True)
    lab = build_capture_lab(monkeypatch, tmp_path)
    r6 = _r6_config()
    assert "snmp" not in r6 and "snmp-server" in lab["captured"]
    save_golden("Lab", [GoldenItem("r6", r6, "203.0.113.16", platform="cisco_iosxe")],
                source="onboarding", actor="t", allow_new=True, baseline=False)
    hostvars.write_committed(lab["repo"], get_parser("cisco_iosxe").parse(r6))
    assert save_host_vars("Lab", ["r6"], actor="t", source="extraction")["ok"]
    devices = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
                "platform": "cisco_iosxe"},
               {"hostname": "r6", "ip": "203.0.113.16", "device_type": "cisco_xe",
                "platform": "cisco_iosxe"}]
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(d) for d in devices])
    settings = {"nsot_git_author_name": "NMAS", "nsot_git_author_email": "nmas@localhost",
                "prometheus_url": "http://prometheus.invalid:9090"}
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: settings.get(key, default))
    from modules import credentials
    device_secret = credentials.get_template_secret
    monkeypatch.setattr("modules.credentials.get_template_secret",
                        lambda key: None if ":@profile:" in key else device_secret(key))
    stored = {}
    monkeypatch.setattr("modules.nsot.profile.set_secret",
                        lambda ln, ref, value: stored.__setitem__(ref, value))
    lab.update(settings=settings, stored=stored, r6=r6)
    return lab


def _secret_values(lab):
    """Every stored secret value r2's intent references (what must never leave)."""
    from modules.credentials import get_template_secret, template_secret_key
    from modules.nsot import hostvars
    refs = hostvars.read_committed(lab["repo"], "r2").get("secret_refs") or []
    vals = [get_template_secret(template_secret_key("Lab", "r2", r)) for r in refs]
    return [v for v in vals if v and len(v) >= 4]


class TestThePropose:
    def test_the_section_the_fleet_agrees_on_is_proposed_and_r6_inherits_it(self, lab):
        from modules.nsot import profile_propose as pp
        p = pp.propose("Lab")
        snmp = next(s for s in p["sections"] if s["section"] == "snmp")
        assert snmp["proposed"] and snmp["holders"] == ["r2"] and snmp["inherit"] == ["r6"]
        assert p["doc"]["sections"]["snmp"]["source"] == "prometheus"
        assert {"device": "r6", "inherits": ["snmp"]} in p["effect"]
        assert "secrets" not in pp.public(p)

    def test_a_connector_not_configured_proposes_nothing_for_it_and_says_why(self, lab):
        from modules.nsot import profile_propose as pp
        lab["settings"]["prometheus_url"] = ""
        snmp = next(s for s in pp.propose("Lab")["sections"] if s["section"] == "snmp")
        assert not snmp["proposed"] and snmp["why"].startswith("prometheus_url is not configured")

    def test_two_versions_are_never_reconciled_by_the_tool(self, lab):
        from modules.nsot import hostvars, profile_propose as pp
        from modules.nsot.repo import save_host_vars
        r2 = hostvars.read_committed(lab["repo"], "r2")
        r6 = hostvars.read_committed(lab["repo"], "r6")
        r6["snmp"] = json.loads(json.dumps(r2["snmp"]))
        r6["snmp"]["location"] = "a different closet"
        hostvars.write_committed(lab["repo"], r6)
        assert save_host_vars("Lab", ["r6"], actor="t", source="extraction")["ok"]
        snmp = next(s for s in pp.propose("Lab")["sections"] if s["section"] == "snmp")
        assert not snmp["proposed"] and "2 different versions" in snmp["why"]
        assert sorted(d for v in snmp["variants"] for d in v["devices"]) == ["r2", "r6"]

    def test_the_preview_route_draws_it_and_returns_no_secret_value(self, lab):
        r = lab["client"].post("/templatize/profile/propose/preview", json={"list_name": "Lab"})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        body = r.get_json()
        (w,) = body["preview"]["what"]["targets"]
        assert w["selectable"] and w["select_data"]["list"] == "Lab"
        (t,) = body["preview"]["targets"]
        assert any("snmp" in l for l in t["program"]["lines"])
        text = r.get_data(as_text=True)
        assert _secret_values(lab) and not [v for v in _secret_values(lab) if v in text]

    def test_apply_commits_as_the_person_and_a_moved_proposal_is_refused(self, lab):
        from modules.nsot import profile, profile_propose as pp
        p = pp.propose("Lab")
        assert pp.apply("Lab", "0" * 16, "op@example.invalid")["outcome"] == "moved"
        assert profile.read_committed(lab["repo"]) is None           # nothing committed
        out = pp.apply("Lab", p["hash"], "op@example.invalid")
        assert out["outcome"] == "committed", out
        msg = subprocess.run(["git", "-C", lab["repo"], "log", "-1", "--format=%B"],
                             capture_output=True, text=True).stdout
        assert "Source: profile" in msg and "Actor: op@example.invalid" in msg
        assert "snmp" in profile.read_committed(lab["repo"])["sections"]
        assert lab["stored"], "the agreed secret was stored under the network's key"
        assert pp.apply("Lab", pp.propose("Lab")["hash"], "op@example.invalid")["outcome"] == "nothing"

    def test_the_apply_route_draws_the_result_and_opens_the_apply_next(self, lab):
        c = lab["client"]
        h = c.post("/templatize/profile/propose/preview",
                   json={"list_name": "Lab"}).get_json()["preview"]["what"]["targets"][0]["select_data"]["hash"]
        r = c.post("/templatize/profile/propose/apply", json={"list_name": "Lab", "hash": h})
        res = r.get_json()["result"]
        assert res["level"] == "success"
        assert res["next"]["open"] == "profile_apply"
        assert res["next"]["args"] == {"list": "Lab", "devices": ["r6"]}
        # The lab's list is the current one (C51 refuses a named list the registry lacks).
        got = c.get("/templatize/profile").get_json()
        assert got["profile"]["sections"]["snmp"] and got["commit"]["subject"].startswith("profile:")

    def test_the_apply_needs_its_list_and_a_hash(self, lab):
        c = lab["client"]
        assert c.post("/templatize/profile/propose/apply", json={"hash": "x"}).status_code == 400
        assert c.post("/templatize/profile/propose/apply", json={"list_name": "Lab"}).status_code == 400


def _commit_proposal():
    from modules.nsot import profile_propose as pp
    assert pp.apply("Lab", pp.propose("Lab")["hash"], "op@example.invalid")["outcome"] == "committed"


class TestTheScopedDeploy:
    def test_the_plan_sends_the_profiles_lines_and_nothing_else(self, lab):
        """r6 gains its SNMP from the profile; a change in r6's OWN intent (an NTP
        server it lacks) is held back, never bundled into the profile's apply."""
        from modules.nsot import hostvars
        from modules.nsot.repo import save_host_vars
        _commit_proposal()
        r6 = hostvars.read_committed(lab["repo"], "r6")
        r6["ntp_servers"] = list(r6.get("ntp_servers") or []) + ["192.0.2.99"]
        hostvars.write_committed(lab["repo"], r6)
        assert save_host_vars("Lab", ["r6"], actor="t", source="extraction")["ok"]
        body = lab["client"].post("/deploy/plan", json={"devices": ["r6"], "scope": "profile",
                                                        "list_name": "Lab"}).get_json()
        (d,) = body["devices"]
        assert body["scope"] == "profile" and not d.get("refused"), d.get("refused")
        sent = [c.strip() for c in d["commands"] if c.strip() != "exit"]
        assert sent and all(c.startswith("snmp") for c in sent), sent
        held = [r["line"].strip() for r in d["profile_scope"]["held_back"]]
        assert "ntp server 192.0.2.99" in held
        assert not any("192.0.2.99" in c for c in d["commands"])
        # The unscoped plan WOULD send it: the scope, not the fixture, holds it back.
        whole = lab["client"].post("/deploy/plan", json={"devices": ["r6"]}).get_json()
        assert any("ntp server 192.0.2.99" in c for c in whole["devices"][0]["commands"])

    def test_no_committed_profile_refuses_by_name(self, lab):
        body = lab["client"].post("/deploy/plan", json={"devices": ["r6"], "scope": "profile",
                                                        "list_name": "Lab"}).get_json()
        assert "has no committed monitoring profile" in body["devices"][0]["refused"]

    def test_an_unknown_scope_is_refused_by_name(self, lab):
        c = lab["client"]
        r = c.post("/deploy/plan", json={"devices": ["r6"], "scope": "everything"})
        assert r.status_code == 400 and "unknown deploy scope" in r.get_json()["error"]
        r = c.post("/deploy/apply", json={"confirmations": {"r6": "x"}, "scope": "everything"})
        assert r.status_code == 400 and "nothing sent" in r.get_json()["error"]

    def test_the_apply_holds_the_confirmed_scope(self, lab, monkeypatch):
        """The seam: the scoped plan's command hash is accepted by a SCOPED apply,
        which reaches the device path carrying the scope, and refused by an
        unscoped one, with nothing sent. r6's own intent holds a change of its
        own, so the two programs DIFFER (measured: with none, they were equal
        and the unscoped apply was accepted, so the test could not fail)."""
        import routes.deploy as rd
        from modules.nsot import hostvars
        from modules.nsot.repo import save_host_vars
        _commit_proposal()
        r6 = hostvars.read_committed(lab["repo"], "r6")
        r6["ntp_servers"] = list(r6.get("ntp_servers") or []) + ["192.0.2.99"]
        hostvars.write_committed(lab["repo"], r6)
        assert save_host_vars("Lab", ["r6"], actor="t", source="extraction")["ok"]
        c = lab["client"]
        plan = c.post("/deploy/plan", json={"devices": ["r6"], "scope": "profile",
                                            "list_name": "Lab"}).get_json()
        (d,) = plan["devices"]
        conf = {"confirmations": {"r6": d["capture_hash"]},
                "command_hashes": {"r6": d["command_hash"]}, "list_name": "Lab"}
        reached = []

        def spy(entry, list_name, rows, authorise, **kw):
            reached.append(kw.get("scope", ""))
            return {"device": entry["artifact"].device, "outcome": "deployed"}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        monkeypatch.setattr(rd, "_write_receipts", lambda *a, **k: {})
        unscoped = c.post("/deploy/apply", json=conf).get_json()
        assert reached == [] and "r6" in json.dumps(unscoped)
        c.post("/deploy/apply", json=dict(conf, scope="profile"))
        assert reached == ["profile"]


class TestTheShippedClients:
    def _js(self, rel):
        return open(os.path.join(ROOT, rel), encoding="utf-8").read()

    def test_the_selection_carries_the_list_the_preview_drew(self):
        import dukpy
        got = dukpy.evaljs([self._js("static/js/nmas_profile.js"),
                            "profileSelection([{checked: true, disabled: false, "
                            "dataset: {hash: 'h1', list: 'Lab'}}])"])
        assert got == {"hash": "h1", "list": "Lab"}
        assert dukpy.evaljs([self._js("static/js/nmas_profile.js"), "profileSelection([])"]) is None

    def test_the_next_step_button_opens_the_apply_for_its_devices(self, lab):
        """The SHIPPED result renderer on the REAL apply route's result."""
        import dukpy
        c = lab["client"]
        h = c.post("/templatize/profile/propose/preview",
                   json={"list_name": "Lab"}).get_json()["preview"]["what"]["targets"][0]["select_data"]["hash"]
        res = c.post("/templatize/profile/propose/apply",
                     json={"list_name": "Lab", "hash": h}).get_json()["result"]
        html = dukpy.evaljs("var window = {};\n" + self._js("static/js/nmas_preview_confirm.js")
                            + f"\nwindow.previewConfirmResultHtml({json.dumps(res)}, {{}})")
        assert 'data-nmas-open="profile_apply"' in html and 'data-nmas-device="r6"' in html
        assert 'data-nmas-list="Lab"' in html and "Apply monitoring profile…" in html

    def test_the_apply_opener_takes_several_devices(self):
        src = self._js("static/js/gen/partials__deploy_wizard.1.js")
        assert re.search(r"String\(device \|\| ''\)\.split\(','\)", src)

    def test_the_client_is_loaded_and_a_refusal_is_never_toast_only(self):
        base = open(os.path.join(ROOT, "templates", "base.html"), encoding="utf-8").read()
        assert "js/nmas_profile.js" in base
        assert "showToast" not in self._js("static/js/nmas_profile.js")
