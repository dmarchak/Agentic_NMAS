"""P.9 step (a) through the REAL deploy plan: r2's real config and committed
intent (`tests.test_capture.build_capture_lab`), a profile committed through
the real `profile.commit_profile()`, and `/deploy/plan` itself.

The acceptance: a profile holding what the device already holds changes NO
plan; a line the profile supplies and the device lacks is sent, and attributed
to the profile, never to "this edit".
"""

import copy

import pytest

from tests.test_capture import build_capture_lab


def _intent(repo):
    from modules.nsot import hostvars
    return hostvars.read_committed(repo, "r2")


def _program(list_name="Lab"):
    import routes.deploy as rd

    (artifact, captured, _dev), err = rd._artifact_for(list_name, "r2")
    assert not err, err
    return artifact, rd._current_program(artifact, captured)


def _profile_from(intent, **extra):
    doc = {"version": 1, "sections": {
        "snmp": {"source": "prometheus", "data": {"snmp": copy.deepcopy(intent["snmp"])}}}}
    for name, data in extra.items():
        doc["sections"][name] = {"source": "setting", "data": data}
    return doc


@pytest.fixture
def lab(monkeypatch, tmp_path):
    from modules.nsot import approval

    # Approval is the template's, never this test's subject (as in
    # test_seed_intent): approved, so the plan computes its program.
    monkeypatch.setattr(approval, "is_approved", lambda repo, t: True)
    return build_capture_lab(monkeypatch, tmp_path)


class TestThePlanInherits:
    def test_a_profile_holding_what_the_device_holds_changes_no_plan(self, lab):
        """The acceptance's first half, on r2's real intent."""
        from modules.nsot import profile

        _a, before = _program()
        out = profile.commit_profile("Lab", _profile_from(_intent(lab["repo"])), "op@example.com",
                                     "the fleet's SNMP")
        assert out["ok"] and out["commit"], out
        _a, after = _program()
        assert after == before

    def test_a_line_the_profile_supplies_is_sent_and_attributed_to_it(self, lab):
        """r6's situation on r2's real intent: the device's own intent holds no
        NTP server (r2's is taken out and committed), so the profile's is
        inherited, sent, and attributed to the profile."""
        from modules.nsot import hostvars, profile
        from modules.nsot.repo import save_host_vars

        intent = _intent(lab["repo"])
        assert intent["ntp_servers"] == ["10.255.1.10"]           # r2 holds its own
        intent["ntp_servers"] = []
        hostvars.write_committed(lab["repo"], intent)
        assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
        doc = _profile_from(intent, ntp={"ntp_servers": ["192.0.2.123"]})
        assert profile.commit_profile("Lab", doc, "op@example.com", "NTP")["ok"]
        _a, program = _program()
        assert "ntp server 192.0.2.123" in program
        body = lab["client"].post("/deploy/plan", json={"devices": ["r2"]}).get_json()
        att = None
        notes = [n for t in body["preview"]["targets"] for n in (t.get("program") or {}).get("notes") or []]
        inherited = [l for n in notes for l in n.get("from_profile") or []]
        assert inherited == ["ntp server 192.0.2.123"], (att, notes)
        assert not any("ntp server" in l for n in notes for l in n.get("from_this_edit") or [])

    def test_the_device_value_wins_over_the_profile(self, lab):
        from modules.nsot import hostvars, profile
        from modules.nsot.repo import save_host_vars

        intent = _intent(lab["repo"])
        intent["ntp_servers"] = ["192.0.2.200"]
        hostvars.write_committed(lab["repo"], intent)
        assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
        assert profile.commit_profile("Lab", _profile_from(intent, ntp={"ntp_servers": ["192.0.2.123"]}),
                                      "op@example.com", "NTP")["ok"]
        _a, program = _program()
        assert "ntp server 192.0.2.200" in program and "ntp server 192.0.2.123" not in program

    def test_a_broken_profile_refuses_the_plan_by_name(self, lab):
        """Committed by hand (the writer refuses one): the reader must never
        read it as no profile and plan without the inherited lines."""
        import os
        import subprocess

        import routes.deploy as rd

        path = os.path.join(lab["repo"], "profiles")
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "monitoring.yml"), "w") as fh:
            fh.write("version: 1\nsections: {dns: {data: {x: 1}}}\n")
        subprocess.run(["git", "-C", lab["repo"], "add", "profiles/monitoring.yml"], check=True)
        subprocess.run(["git", "-C", lab["repo"], "-c", "user.email=t@example.com", "-c", "user.name=t",
                        "commit", "-qm", "profile: broken"], check=True)
        built, err = rd._artifact_for("Lab", "r2")
        assert built is None and "monitoring profile cannot be used" in err and "'dns'" in err


class TestTheCommit:
    def test_one_commit_of_exactly_the_profile_as_the_person(self, lab):
        import subprocess

        from modules.nsot import profile

        out = profile.commit_profile("Lab", _profile_from(_intent(lab["repo"])), "op@example.com", "SNMP")
        show = subprocess.run(["git", "-C", lab["repo"], "show", "--stat", "--format=%B", out["commit"]],
                              capture_output=True, text=True).stdout
        assert show.startswith("profile: SNMP") and "Actor: op@example.com" in show
        assert "Source: profile" in show and "profiles/monitoring.yml" in show
        assert "host_vars" not in show.split("Source: profile", 1)[1]

    def test_a_document_that_is_not_a_profile_writes_nothing(self, lab):
        import os

        from modules.nsot import profile

        with pytest.raises(profile.ProfileRefused, match="no data"):
            profile.commit_profile("Lab", {"version": 1, "sections": {"snmp": {"data": {}}}}, "op", "x")
        assert not os.path.exists(os.path.join(lab["repo"], "profiles", "monitoring.yml"))


def test_the_shipped_preview_draws_the_inherited_lines_apart(lab):
    """The REAL /deploy/plan preview through the SHIPPED renderer: the
    profile's line is drawn under its own heading, never under this edit."""
    import json
    import os

    import dukpy

    from modules.nsot import hostvars, profile
    from modules.nsot.repo import save_host_vars

    intent = _intent(lab["repo"])
    intent["ntp_servers"] = []
    hostvars.write_committed(lab["repo"], intent)
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    assert profile.commit_profile("Lab", _profile_from(intent, ntp={"ntp_servers": ["192.0.2.123"]}),
                                  "op@example.com", "NTP")["ok"]
    preview = lab["client"].post("/deploy/plan", json={"devices": ["r2"]}).get_json()["preview"]
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "js",
                            "nmas_preview_confirm.js"), encoding="utf-8").read()
    out = dukpy.evaljs("var window = {};\n" + src + f"\nwindow.previewConfirmHtml({json.dumps(preview)}, {{}})")
    assert "data-from-profile" in out and "Inherited from the network&#39;s monitoring profile" in out \
        or "Inherited from the network's monitoring profile" in out
    head, tail = out.split("data-from-profile", 1)
    assert "ntp server 192.0.2.123" in tail.split("From this edit", 1)[0]


def test_intent_match_counts_an_inherited_line_the_device_lacks(lab):
    """A device missing a line its profile supplies does not match what it
    should be (the Intent-Match trailer and the baseline decision)."""
    from modules.nsot import hostvars, profile
    from modules.nsot.intent_match import intent_match
    from modules.nsot.repo import save_host_vars

    intent = _intent(lab["repo"])
    golden = open(__import__("tests.test_capture", fromlist=["R2"]).R2, encoding="utf-8").read()
    assert intent_match(lab["repo"], "Lab", "r2", golden, "cisco_iosxe")["state"] == "match"   # the control
    intent["ntp_servers"] = []
    hostvars.write_committed(lab["repo"], intent)
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    assert profile.commit_profile("Lab", _profile_from(intent, ntp={"ntp_servers": ["192.0.2.123"]}),
                                  "op@example.com", "NTP")["ok"]
    got = intent_match(lab["repo"], "Lab", "r2", golden, "cisco_iosxe")
    assert got["state"] == "differs" and any("ntp server 192.0.2.123" in l for l in got["lines"]), got


def test_every_render_of_intent_merges_the_profile_first():
    """ONE merge, and every reader that hydrates intent to render it calls it
    (the survey of 2026-09-30, made a rule). Named exceptions, each with its
    reason; a new hydrate without the merge fails here."""
    import ast
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    EXEMPT = {
        # The previous commit's intent, for attribution: its profile lines are
        # split out afterwards by `_split_profile`, from the committed profile.
        ("routes/deploy.py", "_attribute_additions"),
        # The device's OWN intent rendered alone, which is the measurement.
        ("routes/deploy.py", "_split_profile"),
    }
    found, bad = [], []
    for rel in ("routes/deploy.py", "routes/templatize.py", "modules/nsot/intent_match.py",
                "modules/nsot/restore.py", "modules/nsot/seed.py", "modules/nsot/bulk_intent.py"):
        tree = ast.parse(open(os.path.join(root, rel), encoding="utf-8").read())
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.unparse(fn)
            if "hydrate_secrets(" not in body or fn.name == "hydrate_secrets":
                continue
            # Nested functions are judged with their parent.
            found.append((rel, fn.name))
            if (rel, fn.name) not in EXEMPT and "effective_for(" not in body and "_eff(" not in body:
                bad.append((rel, fn.name))
    assert len(found) >= 6, found                               # the floor: the survey's readers
    assert bad == [], f"hydrates intent without the profile: {bad}"
