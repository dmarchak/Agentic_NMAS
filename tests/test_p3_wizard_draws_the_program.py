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


def _card(plan):
    """The wizard's screen: the plan's `preview`, drawn by the one shipped
    renderer with the wizard's hooks (Stage 7.1)."""
    pytest.importorskip("dukpy")
    from tests.payload_render import render_preview

    return render_preview(plan["preview"], {"selectable": True, "onSelect": "_updateDeploySummary",
                                            "authorise": "_reauthoriseDevice"})


def _unesc(html: str) -> str:
    return (html.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            .replace("&#39;", "'").replace("&amp;", "&"))


class TestTheWizardDrawsIt:
    def test_every_line_of_the_program_is_drawn(self, client):
        plan, d = _plan(client)
        html = _unesc(_card(plan))
        assert len(d["commands"]) >= 3
        for line in d["commands"]:
            assert line in html, (line, html)
        assert f"Exactly these {len(d['commands'])} line(s) will be sent" in html

    def test_the_dangerous_line_has_its_own_authorise_box(self, client):
        plan, _d = _plan(client)
        html = _card(plan)
        boxes = re.findall(r'data-auth-device="s4" data-line="([^"]*)"', html)
        assert [_unesc(b) for b in boxes] == ["shutdown"], boxes
        assert "tick to authorise this exact line" in html

    def test_an_unauthorised_device_cannot_be_ticked(self, client):
        plan, _d = _plan(client)
        html = _card(plan)
        device_box = re.search(r'<input [^>]*data-pc-select id="pc_sel_s4"[^>]*>', html).group(0)
        assert "disabled" in device_box
        assert "dangerous line(s) not authorised" in html

    def test_once_authorised_it_can_be_ticked_and_says_so(self, client):
        """Control for the one above."""
        plan, d = _plan(client, {"s4": ["shutdown"]})
        html = _card(plan)
        device_box = re.search(r'<input [^>]*data-pc-select id="pc_sel_s4"[^>]*>', html).group(0)
        assert "disabled" not in device_box
        assert "dangerous: AUTHORISED" in html
        assert f'data-command-hash="{d["command_hash"]}"' in html

    def test_the_attribution_split_is_drawn(self, client):
        plan, _d = _plan(client)
        html = _unesc(_card(plan))
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

    def test_ticking_a_box_re_plans_with_every_box(self):
        """7.1: the whole batch is re-planned with the authorisation map read
        from every box, and redrawn by the one renderer. A device whose command
        hash moved is left unticked, so it is confirmed as now shown."""
        fn = _lift(self.SRC, "_reauthoriseDevice")
        assert "fetch('/deploy/plan'" in fn
        assert "input[data-auth-device]" in fn and "authorise})" in fn
        assert "_renderDeployPlan(d)" in fn
        assert "kept[b.dataset.device] === b.dataset.commandHash" in fn


class TestTheRestorePathCanAuthorise:
    @staticmethod
    def _stub(monkeypatch):
        """A REAL RestoreTarget through the real route and prepare_restore."""
        import routes.golden as golden
        from modules.nsot.deploy import RestoreTarget

        t = RestoreTarget(device="s4", platform="cisco_ios", target_config=INTENT,
                          captured=CAPTURE, ref="HEAD")
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
        monkeypatch.setattr("modules.nsot.restore.build_targets", lambda *a, **k: ([t], []))

    def test_the_preview_folds_the_authorisation_into_the_hash(self, monkeypatch):
        import flask

        import routes.golden as golden

        self._stub(monkeypatch)
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
        assert flow.index("_authoriseDangerous(") < flow.index("_confirmRestorePreview(")

    def test_the_restore_preview_marks_authorised_and_refused_lines(self, monkeypatch):
        """Drawn by the component from the real restore preview, both ways."""
        import flask

        import routes.golden as golden
        from tests.payload_render import render_preview

        self._stub(monkeypatch)
        app = flask.Flask(__name__)
        app.register_blueprint(golden.bp)
        c = app.test_client()
        refused = c.post("/golden/restore/preview", json={"ref": "HEAD"}).get_json()
        authed = c.post("/golden/restore/preview",
                        json={"ref": "HEAD", "authorise": {"s4": ["shutdown"]}}).get_json()
        a_html, r_html = render_preview(authed["preview"]), render_preview(refused["preview"])
        assert "dangerous: AUTHORISED" in a_html
        assert "dangerous: tick to authorise this exact line" in r_html
        assert refused["preview"]["what"]["targets"][0]["state"] == "not_authorised"
        assert refused["preview"]["what"]["targets"][0]["selectable"] is False
        assert authed["preview"]["what"]["targets"][0]["selectable"] is True
