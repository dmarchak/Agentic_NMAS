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
        monkeypatch.setattr("modules.nsot.ztp.progress", lambda entry: {
            "stage": "leased_not_fetched", "summary": "leased 192.0.2.60; it has not asked yet"})
        html = client.get("/v2/device/bp1").get_data(as_text=True)
        text = _text(html)
        assert "Where bp1 has got to" in text
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

    def test_intent_that_is_the_first_boot_config_says_where_to_write_it(  # noqa: F811
            self, client, person, monkeypatch):
        text = _text(_verify(client, monkeypatch, {"state": "write", "adds": 0, "why": ""}))
        assert "bp1's committed intent is its first-boot config" in text
        assert "Write its intent first" in text and "Deploy its intent…" not in text

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


def test_no_golden_is_unknown_with_why(monkeypatch):
    from types import SimpleNamespace

    from routes import onboard_v2 as V
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: True)
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: SimpleNamespace(name="probe", repo_dir="/r"))
    monkeypatch.setattr("modules.nsot.manifest.find_by_name", lambda repo, name: (None, None))
    got = V._next_intent("probe", "bp1")
    assert got == {"state": "unknown", "adds": 0, "why": "no golden is recorded for it yet"}
