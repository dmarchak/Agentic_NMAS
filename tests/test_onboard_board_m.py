"""Board M, revised on the operator's decision (canvas v113, 2026-10-11): first boot is the
management plane only, and the device's intent follows as an ordinary deploy.

- the pending page draws five steps, from its row and ZTP's progress: identity (by MAC, or by
  its address), the first-boot config, the confirm (the reservation for ZTP), waiting (Kea's and
  the responder's sub-state), arrival;
- Verify's result names the next step: Deploy its intent… (the device page's Deploy) when its
  committed intent says more than its first golden, where to write it when it does not, and
  "could not be read" with why otherwise;
- `_next_intent` maps intent_match's answer: adds -> deploy, none -> write, unknown and a
  missing golden -> unknown.
"""

import html as _h

import pytest

from tests.test_onboard_v2 import TestAPendingDevice as P
from tests.test_onboard_v2 import client, person  # noqa: F401 (the fixtures)


def _text(page):
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _h.unescape(page)))


class TestTheFiveSteps:

    def test_a_ztp_device_by_its_mac_and_its_reservation(self, client, monkeypatch):  # noqa: F811
        row = dict(P.PENDING, address_source="ztp", mgmt_ip="",
                   mgmt_mac="aa:bb:cc:00:02:60", reserved_address="192.0.2.60")
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [dict(row)])
        monkeypatch.setattr("modules.nsot.ztp.progress", lambda entry, **_k: {
            "stage": "leased_not_fetched", "summary": "leased 192.0.2.60; it has not asked yet"})
        html = client.get("/v2/device/bp1").get_data(as_text=True)
        text = _text(html)
        assert "bp1 onboarding progress" in text          # its title since C1193
        # On THE stepper (2026-10-12): three done, waiting for it running with the ZTP stage as
        # its note, the arrival waiting.
        import re
        assert re.findall(r'class="run-step run-step-(\w+)" data-step="(\w+)"', html) == [
            ("done", "identity"), ("done", "first_boot"), ("done", "confirmed"),
            ("running", "waiting"), ("waiting", "arrival")]
        assert "leased 192.0.2.60; it has not asked yet" in html[html.index('data-step="waiting"'):]
        assert "Identity: by MAC, aa:bb:cc:00:02:60" in text
        assert "the management plane only" in text and "nothing else is sent at first boot" in text
        assert "reserved in Kea ( aa:bb:cc:00:02:60 → 192.0.2.60 )" in text
        assert "leased not fetched leased 192.0.2.60; it has not asked yet" in text
        assert "its intent follows as an ordinary deploy" in text

    def test_a_static_device_by_its_address(self, client, monkeypatch):  # noqa: F811
        monkeypatch.setattr("modules.nsot.manifest.pending_devices",
                            lambda repo: [dict(P.PENDING)])
        text = _text(client.get("/v2/device/bp1").get_data(as_text=True))
        assert "Identity: by its address, 203.0.113.31" in text
        assert "committed, its one-time credential staged" in text
        assert "Waiting for it: boot it with its bootstrap config" in text


def _verify(client, monkeypatch, nxt):  # noqa: F811
    from routes import onboard
    monkeypatch.setattr(onboard, "verify_run", lambda name, data, ident: ({"ok": True, "result": {
        "level": "success", "happened": {"summary": "bp1 is onboarded"},
        "did_not": {"items": []}}}, 200))
    monkeypatch.setattr("routes.onboard_v2._next_intent", lambda list_name, name: nxt)
    return client.post("/v2/onboard/bp1/verify", data={
        "list_name": "probe", "fingerprint": "f" * 64}).get_data(as_text=True)


class TestTheNextStep:

    def test_intent_that_says_more_is_deployed_as_an_ordinary_deploy(self, client, person,  # noqa: F811
                                                                      monkeypatch):
        page = _verify(client, monkeypatch, {"state": "deploy", "adds": 119, "why": ""})
        text = _text(page)
        assert "Next, its intent." in text and "119 lines it does not run" in text
        assert 'href="/v2/device/bp1?list=probe&amp;op=deploy"' in page
        assert "Deploy its intent…" in text and "rolled back on failure" in text

    def test_intent_that_says_nothing_more_says_where_to_write_it(  # noqa: F811
            self, client, person, monkeypatch):
        # "write" is a full intent the device already runs: a first-boot intent is "seed"
        # (C1188), so this one no longer calls itself the first-boot config.
        text = _text(_verify(client, monkeypatch, {"state": "write", "adds": 0, "why": ""}))
        assert "bp1 already runs everything its committed intent says" in text
        assert "Write what it should run first" in text and "Deploy its intent…" not in text
        assert "first-boot config" not in text

    # C1188 (W4 step 42, 2026-10-17): the template's raw exception, verbatim from the walk.
    RAW = ("committed intent could not be rendered: The template (templates/_common.j2 line 6: "
           "{% for s in v.services %}{{ s }}) reads `services`, and the intent does not hold it")

    def test_a_first_boot_intent_names_seed_intent_with_its_detail_behind_a_toggle(  # noqa: F811
            self, client, person, monkeypatch):
        page = _verify(client, monkeypatch, {"state": "seed", "adds": 0, "why": self.RAW})
        text = _text(page)
        assert ("Intent can't be checked yet: bp1's intent is its first-boot config. "
                "Next: Actions › Seed intent…") in text, text
        assert 'href="/v2/device/bp1?list=probe&amp;op=seed"' in page
        notice = page[page.index('id="ob-next"'):]
        notice = notice[:notice.index("</div>")]
        short, _, detail = notice.partition("<details")
        assert "_common.j2" not in short and "Next, its intent." not in short, short
        assert "<summary>Details</summary>" in detail and "_common.j2 line 6" in _h.unescape(
            detail), detail

    def test_not_known_says_why(self, client, person, monkeypatch):  # noqa: F811
        text = _text(_verify(client, monkeypatch, {"state": "unknown", "adds": 0,
                                                   "why": "no golden is recorded for it yet"}))
        assert "could not be read (no golden is recorded for it yet)" in text


@pytest.mark.parametrize("im, want", [
    ({"state": "differs", "adds": 3, "why": ""}, ("deploy", 3)),
    ({"state": "match", "adds": 0, "why": ""}, ("write", 0)),
    ({"state": "differs", "adds": 0, "removes": 2, "why": ""}, ("write", 0)),
    ({"state": "unknown", "adds": 0, "why": "no committed intent"}, ("unknown", 0)),
])
def test_next_intent_maps_intent_match(monkeypatch, im, want):
    from types import SimpleNamespace

    from routes import onboard_v2 as V
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: True)
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: SimpleNamespace(name="probe", repo_dir="/r"))
    monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                        lambda repo, name: ("u", {"golden": "golden/bp1.cfg"}))
    monkeypatch.setattr("modules.nsot.repo.committed_golden_for",
                        lambda repo, entry: {"text": "hostname bp1\n"})
    monkeypatch.setattr("modules.nsot.intent_match.intent_match",
                        lambda repo, ln, name, text: im)
    got = V._next_intent("probe", "bp1")
    assert (got["state"], got["adds"]) == want


@pytest.mark.parametrize("doc, want", [
    # C1188: onboarding's bootstrap intent (`hostvars.is_bootstrap_only`) is Seed intent's,
    # its render's own words carried for the Details toggle.
    ({"hostname": "bp1", "bootstrap": {"source": "ztp"}}, ("seed", "the render's words")),
    # The control: a full intent whose render failed is still "could not be read".
    ({"hostname": "bp1", "interfaces": {"Gi1": {}}}, ("unknown", "the render's words")),
])
def test_next_intent_names_seed_for_a_first_boot_intent(monkeypatch, doc, want):
    from types import SimpleNamespace

    from routes import onboard_v2 as V
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: True)
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: SimpleNamespace(name="probe", repo_dir="/r"))
    monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                        lambda repo, name: ("u", {"golden": "golden/bp1.cfg"}))
    monkeypatch.setattr("modules.nsot.repo.committed_golden_for",
                        lambda repo, entry: {"text": "hostname bp1\n"})
    monkeypatch.setattr("modules.nsot.hostvars.read_committed", lambda repo, name: dict(doc))
    monkeypatch.setattr("modules.nsot.intent_match.intent_match",
                        lambda repo, ln, name, text: {"state": "unknown", "adds": 0,
                                                      "why": "the render's words"})
    got = V._next_intent("probe", "bp1")
    assert (got["state"], got["why"]) == want


def test_no_golden_is_unknown_with_why(monkeypatch):
    from types import SimpleNamespace

    from routes import onboard_v2 as V
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: True)
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: SimpleNamespace(name="probe", repo_dir="/r"))
    monkeypatch.setattr("modules.nsot.manifest.find_by_name", lambda repo, name: (None, None))
    got = V._next_intent("probe", "bp1")
    assert got == {"state": "unknown", "adds": 0, "why": "no golden is recorded for it yet"}
