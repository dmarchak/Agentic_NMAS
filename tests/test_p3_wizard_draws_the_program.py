"""P.3 step 4 (register D4): the deploy wizard draws the PROGRAM, authorises
each dangerous line into the confirm hash, and shows the attribution split.
The restore path can now carry an authorisation too.

The wizard drew `to_add`, collapsed: the diff standing in for what is sent.
`commands`, `dangerous` and `attribution` were computed by `/deploy/plan`,
carried to the browser and drawn nowhere, and apply sent no `authorise`, so a
program containing `shutdown` could never be deployed from the GUI at all.

Driven with a REAL `/deploy/plan` payload: the artifact and its intent are
stubbed, and `merge_commands`, `dangerous_in`, `command_fingerprint` and the
authorisation checks are the real ones.
"""

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIZARD = os.path.join(ROOT, "static", "js", "gen", "partials__deploy_wizard.1.js")
GOLDEN_JS = os.path.join(ROOT, "static", "js", "gen", "partials__golden_repo.3.js")

CAPTURE = ("hostname s4\n"
           "interface GigabitEthernet0/1\n"
           " description uplink\n"
           "interface GigabitEthernet0/2\n"
           " description spare\n"
           "end\n")
INTENT = ("hostname s4\n"
          "interface GigabitEthernet0/1\n"
          " description uplink\n"
          "interface GigabitEthernet0/2\n"
          " description spare <unused>\n"
          " shutdown\n"
          "end\n")
ATTRIBUTION = {"intent_commit": "abcdef1234567890", "intent_subject": "host_vars: s4 shut Gi0/2",
               "from_this_edit": ["shutdown"], "pre_existing": [" description spare <unused>"],
               "attributable": True}


@pytest.fixture
def client(monkeypatch):
    import app as nmas
    import routes.deploy as rd
    from modules.nsot.render_artifact import build_artifact

    def _fake(list_name, hostname, cache=None):
        artifact = build_artifact(hostname, CAPTURE, "cisco_ios", template_approved=True)
        return (artifact, CAPTURE, {"hostname": hostname, "ip": "203.0.113.24"}), ""

    monkeypatch.setattr(rd, "_artifact_for", _fake)
    monkeypatch.setattr("modules.nsot.deploy.prepare_device", lambda a: {"config": INTENT})
    monkeypatch.setattr(rd, "_attribute_additions", lambda *a, **k: dict(ATTRIBUTION))
    sent = []

    def _deploy_one(entry, list_name, device_rows, authorise=None, source_ref=""):
        from modules.nsot.deploy import DEPLOYED
        sent.append({"device": entry["artifact"].device, "authorise": authorise})
        return {"device": entry["artifact"].device, "outcome": DEPLOYED}

    monkeypatch.setattr(rd, "_deploy_one", _deploy_one)
    monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {"commit": ""})
    c = nmas.app.test_client()
    c.sent = sent
    return c


def _plan(client, authorise=None):
    body = {"devices": ["s4"]}
    if authorise is not None:
        body["authorise"] = authorise
    out = client.post("/deploy/plan", json=body).get_json()
    assert out["ok"], out
    return out, out["devices"][0]


class TestTheFixtureCanExhibitTheCase:
    def test_the_program_contains_a_dangerous_line(self, client):
        _, d = _plan(client)
        assert " shutdown" in d["commands"]
        # dangerous_in() STRIPS; commands keep indentation. The renderers must
        # compare trimmed text, which is what this fixture can now exhibit.
        assert d["dangerous"] == ["shutdown"]
        assert d["authorisation_ok"] is False


class TestAuthorisationEndToEnd:
    def test_an_authorised_shutdown_deploys_and_reaches_the_pipeline(self, client):
        _, d = _plan(client, {"s4": ["shutdown"]})
        assert d["authorisation_ok"] is True
        out = client.post("/deploy/apply", json={
            "confirmations": {"s4": d["capture_hash"]},
            "command_hashes": {"s4": d["command_hash"]},
            "authorise": {"s4": ["shutdown"]}}).get_json()
        assert "s4" in out.get("deployed", []), out
        assert client.sent == [{"device": "s4", "authorise": {"s4": ["shutdown"]}}]

    def test_withdrawing_the_authorisation_after_the_plan_is_refused(self, client):
        _, d = _plan(client, {"s4": ["shutdown"]})
        out = client.post("/deploy/apply", json={
            "confirmations": {"s4": d["capture_hash"]},
            "command_hashes": {"s4": d["command_hash"]},
            "authorise": {}}).get_json()
        assert "s4" not in out.get("deployed", [])
        assert client.sent == []

    def test_adding_an_authorisation_the_plan_did_not_cover_is_refused(self, client):
        """A box ticked without a re-plan: the hash is for the UNauthorised
        program, so the apply's recompute with the authorisation disagrees."""
        _, d = _plan(client)
        out = client.post("/deploy/apply", json={
            "confirmations": {"s4": d["capture_hash"]},
            "command_hashes": {"s4": d["command_hash"]},
            "authorise": {"s4": ["shutdown"]}}).get_json()
        assert "s4" not in out.get("deployed", [])
        refusal = next(r for r in out["results"] if r["device"] == "s4")
        assert refusal["outcome"] == "refused" and "confirmed_hash" in refusal, refusal
        assert client.sent == []

    def test_a_confirmed_device_that_cannot_be_built_is_named_not_dropped(self, client, monkeypatch):
        """Register C24: it used to vanish from the report."""
        import routes.deploy as rd
        monkeypatch.setattr(rd, "_artifact_for", lambda *a, **k: (None, "no golden config"))
        out = client.post("/deploy/apply", json={"confirmations": {"s4": "x"}}).get_json()
        row = next(r for r in out["results"] if r["device"] == "s4")
        assert row["outcome"] == "refused"
        assert "no golden config" in row["reason"] and "Nothing was sent" in row["reason"]
        assert out["total"] == 1


def _lift(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    depth, i, seen = 0, src.index("{", start), False
    while i < len(src):
        if src[i] == "{":
            depth += 1
            seen = True
        elif src[i] == "}":
            depth -= 1
            if seen and depth == 0:
                break
        i += 1
    return src[start:i + 1]


def _card(entry):
    dukpy = pytest.importorskip("dukpy")
    src = open(WIZARD, encoding="utf-8").read()
    fns = "\n".join(_lift(src, n) for n in ("_dEsc", "_programHtml",
                                            "_attributionHtml", "_deviceCard"))
    return dukpy.evaljs(fns + f"\n_deviceCard({json.dumps(entry)})")


def _unesc(html: str) -> str:
    return (html.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            .replace("&#39;", "'").replace("&amp;", "&"))


class TestTheWizardDrawsIt:
    def test_every_line_of_the_program_is_drawn(self, client):
        _, d = _plan(client)
        html = _unesc(_card(d))
        assert len(d["commands"]) >= 3
        for line in d["commands"]:
            assert line in html, (line, html)
        assert f"exactly these {len(d['commands'])} line(s) will be sent" in html

    def test_the_dangerous_line_has_its_own_authorise_box(self, client):
        _, d = _plan(client)
        html = _card(d)
        boxes = re.findall(r'data-auth-device="s4" data-line="([^"]*)"', html)
        assert [_unesc(b) for b in boxes] == ["shutdown"], boxes
        assert "tick to authorise this exact line" in html

    def test_an_unauthorised_device_cannot_be_ticked(self, client):
        _, d = _plan(client)
        html = _card(d)
        device_box = re.search(r'<input class="form-check-input" type="checkbox" id="dep_s4"[^>]*>', html).group(0)
        assert "disabled" in device_box
        assert "dangerous line(s) not authorised" in html

    def test_once_authorised_it_can_be_ticked_and_says_so(self, client):
        """Control for the one above."""
        _, d = _plan(client, {"s4": ["shutdown"]})
        html = _card(d)
        device_box = re.search(r'<input class="form-check-input" type="checkbox" id="dep_s4"[^>]*>', html).group(0)
        assert "disabled" not in device_box
        assert "dangerous: AUTHORISED" in html
        assert f'data-command-hash="{d["command_hash"]}"' in html

    def test_the_attribution_split_is_drawn(self, client):
        _, d = _plan(client)
        html = _unesc(_card(d))
        assert "From this edit: <strong>1</strong>" in html
        assert "Not from this edit: <strong>1</strong>" in html
        assert "abcdef12" in html and "host_vars: s4 shut Gi0/2" in html


class TestTheWizardSendsTheAuthorisationItsHashCovers:
    SRC = open(WIZARD, encoding="utf-8").read()

    def test_apply_sends_authorise_from_the_rendered_plan(self):
        fn = _lift(self.SRC, "applyDeploy")
        assert "command_hashes: commandHashes, authorise}" in fn
        assert "(_deployPlan || {}).devices" in fn
        assert "data-auth-device" not in fn, "read from the plan, never from the boxes"

    def test_ticking_a_box_re_plans_that_device(self):
        fn = _lift(self.SRC, "_reauthoriseDevice")
        assert "fetch('/deploy/plan'" in fn
        assert "authorise: {[device]: lines}" in fn
        assert "card.outerHTML = _deviceCard(entry)" in fn


class TestTheRestorePathCanAuthorise:
    def test_the_preview_folds_the_authorisation_into_the_hash(self, monkeypatch):
        import flask

        import routes.golden as golden
        from tests.test_p3_restore_is_guarded import _Target

        class _T(_Target):
            pass

        t = _T("s4")
        t.captured = CAPTURE
        t.target_config = INTENT
        monkeypatch.setattr(golden, "_active_list", lambda data=None: "Lab")
        # build_targets is stubbed with a made-up list, so coverage() is too: it
        # reads that list's inventory, and resolving a list that does not exist
        # creates it (get_list_data_dir). Coverage is tested on a real repo in
        # TestTheInventoryIsThePopulation.
        monkeypatch.setattr("modules.nsot.restore.coverage",
                            lambda ln, devices=None, skipped=None: {
                                "inventory_size": 0, "partial": False,
                                "denominator": 0, "scope_words": "in this list"})
        monkeypatch.setattr(golden, "_intent_preview", lambda ln, x: {"action": "none"})
        monkeypatch.setattr("modules.nsot.deploy.prepare_restore",
                            lambda target: {"config": target.target_config})
        monkeypatch.setattr("modules.nsot.restore.build_targets", lambda *a, **k: ([t], []))
        app = flask.Flask(__name__)
        app.register_blueprint(golden.bp)
        c = app.test_client()
        plain = c.post("/golden/restore/preview", json={"ref": "HEAD"}).get_json()["devices"][0]
        authed = c.post("/golden/restore/preview",
                        json={"ref": "HEAD", "authorise": {"s4": ["shutdown"]}}).get_json()["devices"][0]
        assert plain["dangerous"] == ["shutdown"] and plain["authorisation_ok"] is False
        assert authed["authorisation_ok"] is True and authed["authorised"] == ["shutdown"]
        assert plain["command_hash"] != authed["command_hash"]

    def test_the_client_asks_then_sends_it_on_both_calls(self):
        src = open(GOLDEN_JS, encoding="utf-8").read()
        flow = _lift(src, "previewBaselineRestore")
        assert flow.count("authorise: from.authorise || {}") == 2, "preview AND apply"
        assert flow.index("_authoriseDangerous(") < flow.index("_confirmProgram(")

    def test_the_restore_text_marks_authorised_and_refused_lines(self):
        dukpy = pytest.importorskip("dukpy")
        src = _lift(open(GOLDEN_JS, encoding="utf-8").read(), "restorePreviewText")
        dev = {"device": "s4", "deployable": True, "commands": ["interface Gi0/2", " shutdown", "exit"],
               "dangerous": ["shutdown"], "replace": [], "residue": []}
        authed = dukpy.evaljs(src + "\nrestorePreviewText(" + json.dumps(
            {"devices": [dict(dev, authorised=["shutdown"])]}) + ", {})")
        refused = dukpy.evaljs(src + "\nrestorePreviewText(" + json.dumps(
            {"devices": [dict(dev, authorised=[])]}) + ", {})")
        assert "A  shutdown" in authed and "AUTHORISED by you" in authed
        assert "!  shutdown" in refused and "will be refused" in refused
