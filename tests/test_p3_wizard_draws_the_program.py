"""P.3 step 4 (register D4): the deploy wizard draws the PROGRAM, authorises
each dangerous line into the confirm hash, and shows the attribution split.
The restore path can now carry an authorisation too.

The wizard drew `to_add`, collapsed: the diff standing in for what is sent.
`commands`, `dangerous` and `attribution` were computed by `/deploy/plan`,
carried to the browser and drawn nowhere, and apply sent no `authorise`, so a
program containing `shutdown` could never be deployed from the GUI at all.

Driven with a REAL plan payload: the artifact and its intent are
stubbed, and `merge_commands`, `dangerous_in`, `command_fingerprint` and the
authorisation checks are the real ones.

Today's wizard and its two routes left at 7.8 (2026-10-17, P7-25): the plan and apply here are
the cores v2's deploys run (`tests/deploy_core.py`), and the card is drawn by the shipped
preview component. The two tests that read the wizard's own script (its apply sent the
authorisation from the rendered plan; a ticked box re-planned the batch) left with it; v2's
Deploy… card carries each reason into the hash it binds the confirm to
(tests/test_device_deploy_v2.py, `test_a_reason_plans_again_and_offers_the_confirm_bound_to
_that_program`, `test_a_ticked_line_is_removed_with_its_own_reason_in_the_hash`).
"""

import json
import os
import re

import pytest

from tests import deploy_core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


#: An authorisation, with its stated reason (C140).
SHUT = {"line": "shutdown", "reason": "planned maintenance, port unused"}


def _plan(client, authorise=None):
    body = {"devices": ["s4"]}
    if authorise is not None:
        body["authorise"] = authorise
    out = deploy_core.post_plan(json=body).get_json()
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
        _, d = _plan(client, {"s4": [SHUT]})
        assert d["authorisation_ok"] is True
        out = deploy_core.post_apply(json={
            "confirmations": {"s4": d["capture_hash"]},
            "command_hashes": {"s4": d["command_hash"]},
            "authorise": {"s4": [SHUT]}}).get_json()
        assert "s4" in out.get("deployed", []), out
        assert client.sent == [{"device": "s4", "authorise": {"s4": [SHUT]}}]

    def test_withdrawing_the_authorisation_after_the_plan_is_refused(self, client):
        _, d = _plan(client, {"s4": [SHUT]})
        out = deploy_core.post_apply(json={
            "confirmations": {"s4": d["capture_hash"]},
            "command_hashes": {"s4": d["command_hash"]},
            "authorise": {}}).get_json()
        assert "s4" not in out.get("deployed", [])
        assert client.sent == []

    def test_adding_an_authorisation_the_plan_did_not_cover_is_refused(self, client):
        """A box ticked without a re-plan: the hash is for the UNauthorised
        program, so the apply's recompute with the authorisation disagrees."""
        _, d = _plan(client)
        out = deploy_core.post_apply(json={
            "confirmations": {"s4": d["capture_hash"]},
            "command_hashes": {"s4": d["command_hash"]},
            "authorise": {"s4": [SHUT]}}).get_json()
        assert "s4" not in out.get("deployed", [])
        refusal = next(r for r in out["results"] if r["device"] == "s4")
        assert refusal["outcome"] == "refused" and "confirmed_hash" in refusal, refusal
        assert client.sent == []

    def test_a_confirmed_device_that_cannot_be_built_is_named_not_dropped(self, client, monkeypatch):
        """Register C24: it used to vanish from the report."""
        import routes.deploy as rd
        monkeypatch.setattr(rd, "_artifact_for", lambda *a, **k: (None, "no golden config"))
        out = deploy_core.post_apply(json={"confirmations": {"s4": "x"}}).get_json()
        row = next(r for r in out["results"] if r["device"] == "s4")
        assert row["outcome"] == "refused"
        assert "no golden config" in row["reason"] and "Nothing was sent" in row["reason"]
        assert out["total"] == 1



def _card(plan):
    """The screen: the plan's device on v2, the device page's Deploy… card drawn from THE plan
    (`tests/payload_render.render_deploy_card_v2`). Today's deploy wizard drew it until it left
    at 7.8 (P7-25), and today's renderer with it until P7-27."""
    from tests.payload_render import render_deploy_card_v2

    return render_deploy_card_v2(plan, "s4")


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
        assert f"exactly these {len(d['commands'])} line(s) are sent, in order" in html

    def test_the_dangerous_line_has_its_own_authorise_box(self, client):
        plan, _d = _plan(client)
        html = _unesc(_card(plan))
        boxes = re.findall(r'<code>([^<]*)</code> is a dangerous line', html)
        assert boxes == ["shutdown"], boxes
        # C140: a reason field beside the line, and no reason yet.
        assert re.search(r'<input type="text" name="dz::0" value=""', html), html

    def test_an_unauthorised_device_cannot_be_ticked(self, client):
        plan, _d = _plan(client)
        html = _card(plan)
        assert "op-confirm" not in html, "no confirm while the dangerous line waits"
        assert "waits on your stated reason" in html

    def test_once_authorised_it_can_be_ticked_and_says_so(self, client):
        """Control for the one above."""
        plan, d = _plan(client, {"s4": [SHUT]})
        html = _unesc(_card(plan))
        assert "op-confirm" in html
        assert f'"command_hash": "{d["command_hash"]}"' in html

    def test_the_attribution_split_is_drawn(self, client):
        plan, _d = _plan(client)
        html = _unesc(_card(plan))
        assert "From this edit: <strong>1</strong>" in html
        assert "Not from this edit: <strong>1</strong>" in html
        assert "abcdef12" in html and "host_vars: s4 shut Gi0/2" in html


class TestTheRestorePathCanAuthorise:
    @staticmethod
    def _stub(monkeypatch):
        """A REAL RestoreTarget through the real plan and prepare_restore."""
        import routes.golden as golden
        from modules.nsot.deploy import RestoreTarget

        t = RestoreTarget(device="s4", platform="cisco_ios", target_config=INTENT,
                          captured=CAPTURE, ref="HEAD")
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

    @staticmethod
    def _plan(authorise=None):
        """THE restore plan, masked as its v2 callers draw it (today's /golden/restore/preview
        returned it until it left at 7.8, 2026-10-17)."""
        import routes.golden as golden
        from modules.outbound import mask_payload

        return mask_payload(golden.restore_plan("Lab", "HEAD", None, authorise=authorise or {}))

    def test_the_preview_folds_the_authorisation_into_the_hash(self, monkeypatch):
        self._stub(monkeypatch)
        plain = self._plan()["devices"][0]
        authed = self._plan({"s4": [SHUT]})["devices"][0]
        assert plain["dangerous"] == ["shutdown"] and plain["authorisation_ok"] is False
        assert authed["authorisation_ok"] is True and authed["authorised"] == [SHUT]
        assert plain["command_hash"] != authed["command_hash"]

    # Today's re-apply dialog asked for each line's reason in its own modal and sent it on the
    # preview and the apply; it left at 7.8 (2026-10-17, P7-21; C140 (2): one home, the
    # component). The v2 restore card asks in place, plans again, and its confirm carries the
    # reasons (tests/test_device_restore_v2.py).

    def test_the_restore_preview_marks_authorised_and_refused_lines(self, monkeypatch):
        """Drawn by v2's Restore from… card from the real restore plan, both ways (today's
        renderer drew it until P7-27): the dangerous line asks for its reason, and only the
        authorised plan offers the confirm."""
        from tests.payload_render import render_restore_card_v2

        self._stub(monkeypatch)
        refused = self._plan()
        authed = self._plan({"s4": [SHUT]})
        a_html = render_restore_card_v2(authed, "s4")
        r_html = render_restore_card_v2(refused, "s4")
        assert "<code>shutdown</code> a dangerous line. Why (your stated reason" in r_html
        assert "op-confirm" not in r_html and "waits on your stated reason" in r_html
        assert "op-confirm" in a_html
        assert refused["preview"]["what"]["targets"][0]["state"] == "not_authorised"
        assert refused["preview"]["what"]["targets"][0]["selectable"] is False
        assert authed["preview"]["what"]["targets"][0]["selectable"] is True
