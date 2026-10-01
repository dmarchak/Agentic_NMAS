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
    lines = [l for l in text.splitlines() if not l.lstrip().startswith("snmp")
             # r6 carries neither discovery protocol (the operator, measured on
             # Default's repository, 2026-09-30), so it is missing from the
             # LLDP-built topology.
             and l.strip() not in ("lldp run", "cdp run")]
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
    assert "lldp run" not in r6 and "lldp run" in lab["captured"]
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
        assert {"device": "r6", "inherits": ["lldp", "snmp"]} in p["effect"]
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
        # The profile's lines only: SNMP, and the discovery flags r6 lacks.
        assert sent and all(c.startswith("snmp") or c in ("lldp run", "cdp run") for c in sent), sent
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


# ------------------------------------------------ LLDP, CDP and platform defaults

FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
#: Each section's presence, read from the CONFIG TEXT, never through the parser
#: or the detector under test (the control's expectation must not share their source).
MARKER = {"snmp": r"^snmp-server ", "syslog": r"^logging host ", "ntp": r"^ntp server ",
          "telemetry": r"^telemetry ietf subscription ", "lldp": r"^lldp run$",
          "cdp": r"^cdp run$"}


class TestEveryDetectorReadsWhatTheParserWrites:
    """The operator, 2026-09-30: "Not proposed, LLDP: no device's committed
    intent holds it", while eight devices' intent held `lldp run: true`. The
    detector read `intent["lldp"]`, a key from the design document that no
    parser writes (they store `flags: {"lldp run": True}`). So every
    section's detector is held to the REAL intent of the nine real configs."""

    def test_each_detector_finds_exactly_the_devices_whose_config_has_it(self):
        from modules.nsot.parsers import get_parser
        from modules.nsot.profile_propose import DERIVED, section_value
        seen, bad = {s: 0 for s in DERIVED}, []
        for name in sorted(os.listdir(FLEET)):
            text = open(os.path.join(FLEET, name), encoding="utf-8").read()
            intent = get_parser("cisco_iosxe" if name.startswith("r") else "cisco_ios").parse(text)
            for sec in DERIVED:
                has = bool(re.search(MARKER[sec], text, re.M))
                seen[sec] += has
                if has != (section_value(sec, intent) is not None):
                    bad.append((name, sec, has))
        assert bad == []
        # The floor: every section is on some real device, so none passes vacuously.
        assert all(n >= 1 for n in seen.values()), seen
        assert seen["lldp"] == 9 and seen["cdp"] == 5          # r1-r5 and s1-s4; r1-r5

    def test_an_explicit_no_is_its_own_version(self):
        from modules.nsot.profile_propose import section_value
        assert section_value("lldp", {"flags": {"lldp run": False}}) == {"flags": {"lldp run": False}}
        assert section_value("cdp", {"flags": {"aaa new-model": True}}) is None

    def test_lldp_is_proposed_and_r6_inherits_it(self, lab):
        from modules.nsot import profile_propose as pp
        p = pp.propose("Lab")
        rows = {s["section"]: s for s in p["sections"]}
        assert rows["lldp"]["proposed"] and rows["lldp"]["inherit"] == ["r6"]
        assert p["doc"]["sections"]["lldp"]["data"] == {"flags": {"lldp run": True}}

    def test_cdp_is_not_proposed_where_its_line_enables_nothing(self, lab):
        """Measured (C254): on IOS-XE `cdp run` alone enables no interface (r1:
        'cdp enabled interfaces : 0'), so "r6 gains CDP" would claim a feature
        that does not run (the operator, 2026-09-30)."""
        from modules.nsot import profile_propose as pp
        cdp = next(s for s in pp.propose("Lab")["sections"] if s["section"] == "cdp")
        assert not cdp["proposed"] and "alone enables nothing on cisco_iosxe" in cdp["why"]
        assert "cdp enabled interfaces : 0" in cdp["why"]

    def test_the_scoped_apply_to_r6_sends_lldp_and_not_cdp(self, lab):
        _commit_proposal()
        d = lab["client"].post("/deploy/plan", json={"devices": ["r6"], "scope": "profile",
                                                     "list_name": "Lab"}).get_json()["devices"][0]
        sent = [c.strip() for c in d["commands"]]
        assert "lldp run" in sent and "cdp run" not in sent and "snmp ifmib ifindex persist" in sent
        # Location and contact are PER-DEVICE: never in the profile, never sent.
        assert not [c for c in sent if c.startswith(("snmp-server location", "snmp-server contact"))]


def _with_s1(monkeypatch):
    """The lab's fleet plus s1 from its REAL config (cisco_ios, `lldp run`, no
    `cdp run`), so a second platform's absence can be judged."""
    from modules.nsot import profile_propose as pp
    from modules.nsot.parsers import get_parser
    real = pp._fleet
    s1 = get_parser("cisco_ios").parse(open(os.path.join(FLEET, "s1.cfg"), encoding="utf-8").read())

    def fleet(list_name):
        out, skipped = real(list_name)
        return out + [("s1", "cisco_ios", "", s1)], skipped
    monkeypatch.setattr(pp, "_fleet", fleet)


class TestAnAbsentLineMayBeOnByDefault:
    """The operator, 2026-09-30: CDP is written on r1-r4 (IOS-XE) and absent on
    s1-s4 (vIOS); an absent line can mean on by default. The default is
    MEASURED per platform (platform_defaults.json), never assumed, and a
    section applies only where devices write its line, so a default line is
    never pushed onto a platform that never prints it."""

    def test_the_record_measures_before_it_claims(self):
        """Every verdict names its device, time and evidence, and its FIXTURE, a
        real capture that holds the evidence's own words."""
        from modules.nsot import profile_propose as pp
        doc = json.load(open(pp.DEFAULTS_FILE, encoding="utf-8"))
        fixtures = os.path.join(ROOT, "tests", "fixtures", "operational", "platform_defaults")
        states = [v["state"] for plat in doc["by_dialect"].values() for v in plat.values()]
        assert states and set(states) <= {"on", "off", "not_measured"}
        verdicts = 0
        for plat in doc["by_dialect"].values():
            for flag, v in plat.items():
                if v["state"] != "not_measured" or "runs_alone" in v:
                    verdicts += 1
                    for key in ("fixture", "runs_alone_fixture"):
                        if v.get(key):
                            assert os.path.exists(os.path.join(fixtures, v[key])), v[key]
                if v["state"] != "not_measured":
                    assert v.get("evidence") and v.get("device") and v.get("measured_at"), flag
        assert verdicts >= 3 and "nmas-capture-output" in doc["how"]

    def test_the_measured_verdicts_are_what_the_captures_say(self):
        """The record against its own fixtures, read here independently."""
        from modules.nsot import profile_propose as pp
        base = os.path.join(ROOT, "tests", "fixtures", "operational", "platform_defaults")
        s1 = open(os.path.join(base, "set1_2026-09-30T2353Z", "s1__show_cdp_interface.txt")).read()
        r1 = open(os.path.join(base, "set1_2026-09-30T2353Z", "r1__show_cdp_interface.txt")).read()
        assert "cdp enabled interfaces : 6" in s1 and "cdp enabled interfaces : 0" in r1
        assert pp.platform_default("cisco_ios", "cdp run")["state"] == "on"
        assert pp.platform_default("cisco_iosxe", "cdp run")["runs_alone"] is False
        # r6's first capture was DURING its push: never a default.
        assert pp.platform_default("cisco_iosxe", "lldp run")["state"] == "not_measured"

    def test_an_unmeasured_absence_is_said_and_not_applied_there(self, lab, monkeypatch, tmp_path):
        """With a record that has measured nothing, CDP (held on IOS-XE) is not
        applied to the switch, and the preview says the default is not measured."""
        from modules.nsot import profile_propose as pp
        from modules.preview_confirm import profile_propose_preview
        _with_s1(monkeypatch)
        rec = tmp_path / "defaults.json"
        rec.write_text(json.dumps({"version": 1, "how": "x", "by_dialect": {}}))
        monkeypatch.setattr(pp, "DEFAULTS_FILE", str(rec))
        p = pp.public(pp.propose("Lab"))
        cdp = next(s for s in p["sections"] if s["section"] == "cdp")
        assert cdp["platforms"] == ["cisco_iosxe"] and cdp["inherit"] == ["r6"]
        assert cdp["defaults"]["cisco_ios"]["state"] == "not_measured"
        assert cdp["defaults"]["cisco_ios"]["devices"] == ["s1"]
        lldp = next(s for s in p["sections"] if s["section"] == "lldp")
        assert lldp["holders"] == ["r2", "s1"] and not lldp["platforms"]   # both platforms
        import app as A
        with A.app.test_request_context("/"):
            pv = profile_propose_preview(p, pp.document_diff(p), request=__import__("flask").request)
        words = [w["text"] for w in pv["what_not"]["items"] if w["kind"] == "platform_default"]
        assert any("CDP is not written on s1 (cisco_ios): whether it is on by default there is "
                   "NOT MEASURED" in w and "not applied to cisco_ios" in w for w in words), words

    def test_a_measured_default_on_is_said_and_still_never_pushed(self, lab, monkeypatch, tmp_path):
        from modules.nsot import profile_propose as pp
        _with_s1(monkeypatch)
        rec = tmp_path / "defaults.json"
        rec.write_text(json.dumps({"version": 1, "how": "x", "by_dialect": {"cisco_ios": {
            "cdp run": {"state": "on", "device": "s1", "measured_at": "2026-09-30",
                        "evidence": "s1: show cdp: Global CDP information"}}}}))
        monkeypatch.setattr(pp, "DEFAULTS_FILE", str(rec))
        cdp = next(s for s in pp.propose("Lab")["sections"] if s["section"] == "cdp")
        assert cdp["defaults"]["cisco_ios"]["state"] == "on"
        assert cdp["platforms"] == ["cisco_iosxe"] and "s1" not in cdp["inherit"]

    def test_an_unreadable_record_is_not_measured_never_on_or_off(self, tmp_path):
        from modules.nsot import profile_propose as pp
        bad = tmp_path / "broken.json"
        bad.write_text("{")
        got = pp.platform_default("cisco_ios", "cdp run", str(bad))
        assert got["state"] == "not_measured" and "could not be read" in got["why"]


# ------------------------------------------- per-device fields, and choosing a version

def _add_r1(lab, monkeypatch, ifindex=True):
    """r1 in the host's shape (the operator, 2026-09-30): r2's config with its
    OWN location and contact, and (unless *ifindex*) without
    `snmp ifmib ifindex persist`."""
    from modules.nsot import hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars
    lines = []
    for l in lab["captured"].splitlines():
        if l.startswith("hostname"):
            l = "hostname r1"
        elif l.startswith("snmp-server location"):
            l = "snmp-server location rack 4, row B"
        elif l.startswith("snmp-server contact"):
            l = "snmp-server contact netops@example.invalid"
        elif l.startswith("snmp ifmib ifindex persist") and not ifindex:
            continue
        lines.append(l)
    cfg = "\n".join(lines) + "\n"
    save_golden("Lab", [GoldenItem("r1", cfg, "203.0.113.11", platform="cisco_iosxe")],
                source="onboarding", actor="t", allow_new=True, baseline=False)
    hostvars.write_committed(lab["repo"], get_parser("cisco_iosxe").parse(cfg))
    assert save_host_vars("Lab", ["r1"], actor="t", source="extraction")["ok"]
    from modules.nsot import restore
    devs = restore._devices_of("Lab") + [{"hostname": "r1", "ip": "203.0.113.11",
                                           "device_type": "cisco_xe", "platform": "cisco_iosxe"}]
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(d) for d in devs])


class TestPerDeviceFields:
    """The operator, 2026-09-30: `snmp-server location` and `contact` are meant
    to differ per device; only SHARED fields must agree. A per-device field
    never blocks a proposal, is never in the profile, and is never overwritten."""

    def test_a_different_location_and_contact_do_not_block_snmp(self, lab, monkeypatch):
        from modules.nsot import profile_propose as pp
        _add_r1(lab, monkeypatch, ifindex=True)
        snmp = next(s for s in pp.propose("Lab")["sections"] if s["section"] == "snmp")
        assert snmp["proposed"] and snmp["holders"] == ["r1", "r2"], snmp.get("why")
        settings = pp.propose("Lab")["doc"]["sections"]["snmp"]["data"]["snmp"]["settings"]
        assert not [s for s in settings if s.startswith(("location", "contact"))]

    def test_r1_keeps_its_own_and_gains_what_it_lacks(self, lab, monkeypatch):
        """The merge, entry by entry: r1's effective SNMP settings are its own
        location and contact plus the profile's ifindex persist."""
        from modules.nsot import hostvars, profile as P
        _add_r1(lab, monkeypatch, ifindex=False)
        doc = {"version": 1, "sections": {"snmp": {"source": "prometheus", "data": {"snmp": {
            "settings": ["trap-source Loopback0", "enable traps snmp linkdown linkup",
                         "snmp ifmib ifindex persist"]}}}}}
        r1 = hostvars.read_committed(lab["repo"], "r1")
        eff = P.effective(r1, doc, "cisco_iosxe", "")["snmp"]["settings"]
        assert "location rack 4, row B" in eff and "contact netops@example.invalid" in eff
        assert "snmp ifmib ifindex persist" in eff
        assert P.overrides(r1, doc, "cisco_iosxe", "") == []
        kept = P.strip_inherited(r1, doc, "cisco_iosxe", "")["snmp"]["settings"]
        assert kept == ["location rack 4, row B", "contact netops@example.invalid"]


class TestChoosingAVersion:
    """The operator, 2026-09-30: when shared fields differ, the tool never picks;
    a PERSON chooses a version, sees which devices change and how, and the
    choice is confirmed and recorded."""

    def test_two_versions_are_choosable_and_never_picked_by_the_tool(self, lab, monkeypatch):
        from modules.nsot import profile_propose as pp
        _add_r1(lab, monkeypatch, ifindex=False)
        snmp = next(s for s in pp.propose("Lab")["sections"] if s["section"] == "snmp")
        assert not snmp["proposed"] and snmp["choosable"] and "choose a version" in snmp["why"]
        assert sorted(d for v in snmp["variants"] for d in v["devices"]) == ["r1", "r2"]

    def test_the_chosen_version_is_proposed_and_r1_gains_ifindex_persist(self, lab, monkeypatch):
        from modules.nsot import profile_propose as pp
        _add_r1(lab, monkeypatch, ifindex=False)
        vid = next(v["id"] for s in pp.propose("Lab")["sections"] if s["section"] == "snmp"
                   for v in s["variants"] if v["devices"] == ["r2"])
        p = pp.propose("Lab", choose={"snmp": vid})
        snmp = next(s for s in p["sections"] if s["section"] == "snmp")
        assert snmp["proposed"] and snmp["chosen"] == vid
        assert snmp["changes"] == {"r1": {"gains": ["snmp ifmib ifindex persist"], "keeps": []}}
        assert snmp["inherit"] == ["r6"]
        assert p["hash"] != pp.propose("Lab")["hash"]          # the choice is in the hash

    def test_the_choice_is_confirmed_and_recorded_through_the_routes(self, lab, monkeypatch):
        _add_r1(lab, monkeypatch, ifindex=False)
        c = lab["client"]
        first = c.post("/templatize/profile/propose/preview", json={"list_name": "Lab"}).get_json()
        (snmp,) = [x for x in first["choices"] if x["section"] == "snmp"]
        vid = next(v["id"] for v in snmp["versions"] if v["devices"] == ["r2"])
        pv = c.post("/templatize/profile/propose/preview",
                    json={"list_name": "Lab", "choose": {"snmp": vid}}).get_json()
        notes = [n for t in pv["preview"]["targets"] for n in t["program"].get("notes") or []]
        assert any(n["title"].startswith("SNMP: you chose version " + vid) and
                   "r1 gains: snmp ifmib ifindex persist" in n["lines"] for n in notes), notes
        h = pv["preview"]["what"]["targets"][0]["select_data"]["hash"]
        # The hash is bound to the choice: confirmed without it, refused.
        moved = c.post("/templatize/profile/propose/apply",
                       json={"list_name": "Lab", "hash": h}).get_json()
        assert moved["result"]["targets"][0]["outcome"] == "moved"
        done = c.post("/templatize/profile/propose/apply",
                      json={"list_name": "Lab", "hash": h, "choose": {"snmp": vid}}).get_json()
        assert done["result"]["level"] == "success"
        subject = subprocess.run(["git", "-C", lab["repo"], "log", "-1", "--format=%s"],
                                 capture_output=True, text=True).stdout
        assert "chosen: snmp as held by r2" in subject

    def test_the_shipped_client_draws_one_button_per_version(self):
        import dukpy
        src = open(os.path.join(ROOT, "static/js/nmas_profile.js"), encoding="utf-8").read()
        html = dukpy.evaljs([src, "profileChoicesHtml([{section: 'snmp', chosen: '', versions: "
                                  "[{id: 'a1', devices: ['r2', 'r3']}, {id: 'b2', devices: ['r1<x>']}]}])"])
        assert html.count("data-profile-version=") == 2
        assert "Use the version held by r2, r3" in html and "r1&lt;x&gt;" in html
