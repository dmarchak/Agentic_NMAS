"""History › Baselines › Re-apply… on v2 (2026-10-10; the `reapply` today's-page gap closed).

The page plans through THE restore plan (`routes.golden.restore_plan`, tested on its own) and
runs through a device Restore's job (`deploy_job.start_restore`); here, replaced at that edge:
- each device falls in one state: will be restored, needs a stated reason (sent to its own
  Restore, never confirmed here), blocked (an error, a refusal, or another operation's hold),
  or already as the baseline holds it; the counts come first; devices the baseline predates
  are listed as left as they are;
- the confirm body carries only the devices that can go, with the hashes drawn;
- what is drawn is masked; a name that is no baseline, and a withdrawn baseline, are said;
- the confirm starts the restore job with exactly the confirmed devices, and refuses a body
  missing a hash or naming no network;
- History's Re-apply… opens it on v2.
"""

import json
import re

import pytest

from tests.test_device_capture_v2 import lab  # noqa: F401 (the fixture)

TAG = "baseline/20261001T000000Z"
PLANTED = "PLANTEDCOMMUNITY55"


def _dev(name, **over):
    d = {"device": name, "deployable": True, "commands": [f"hostname {name}"],
         "capture_hash": f"c-{name}", "command_hash": f"h-{name}", "checks": [],
         "intent": {"action": "restore"}, "residue": [], "excluded_unrenderable": []}
    d.update(over)
    return d


PLAN = {"ok": True, "devices": [
    _dev("r1"),
    _dev("r2", authorisation_ok=False, dangerous=["no ip routing"]),
    _dev("r3", deployable=False, blocking_reasons=["no golden at the baseline"]),
    _dev("r4", commands=[], intent={"action": "unchanged"}),
    _dev("r5", busy="r5 is held by a deploy (ana, 20 s)"),
    _dev("r6", commands=[f"snmp-server community {PLANTED} RO"]),
], "skipped": [{"hostname": "r9", "not_at_ref": True}]}


@pytest.fixture
def planned(lab, monkeypatch):  # noqa: F811
    monkeypatch.setattr("routes.golden.restore_plan", lambda *a, **k: json.loads(
        json.dumps(PLAN)))
    return lab


def _page(lab, tag=TAG):  # noqa: F811
    r = lab["client"].get(f"/v2/history/reapply?list=Lab&tag={tag}")
    return r, r.get_data(as_text=True)


def test_each_device_falls_in_one_state_the_counts_first(planned):
    r, html = _page(planned)
    assert r.status_code == 200
    counts = html[html.index('class="tpl-counts"'):html.index("</p>", html.index("tpl-counts"))]
    assert "will be restored <strong>2</strong>" in counts                 # r1, r6
    assert "needs a stated reason" in counts and "blocked: nothing is sent <strong>2</strong>" \
        in counts                                                          # r3, r5
    assert "already as the baseline holds it <strong>1</strong>" in counts  # r4
    assert "left as they are <strong>1</strong>" in counts and "the baseline predates it" in html
    assert "r5 is held by a deploy" in html
    assert 'href="/v2/device/r2?op=restore&amp;moment=' in html, "r2 is sent to its own Restore"


def test_the_confirm_carries_only_the_devices_that_can_go(planned):
    _r, html = _page(planned)
    body = json.loads(re.search(r"data-body='([^']*)'", html).group(1))
    assert set(body["confirmations"]) == {"r1", "r6"}
    assert body["command_hashes"] == {"r1": "h-r1", "r6": "h-r6"} and body["tag"] == TAG
    assert "Re-apply to 2 device(s)" in html


def test_what_is_drawn_is_masked(planned):
    _r, html = _page(planned)
    assert "snmp-server community" in html and PLANTED not in html


@pytest.mark.parametrize("tag,words", [("golden/r1/x", "is not a baseline"),
                                       ("", "is not a baseline")])
def test_a_name_that_is_no_baseline_is_said(planned, tag, words):
    _r, html = _page(planned, tag)
    assert words in html and 'id="apply-confirm"' not in html


def test_a_withdrawn_baseline_is_said(lab, monkeypatch):  # noqa: F811
    from modules.nsot.restore import WithdrawnBaseline

    def withdrawn(*a, **k):
        raise WithdrawnBaseline({"tag": TAG, "decided": "2026-10-02", "by": "ana",
                                 "why": "a device was not at intent"})
    monkeypatch.setattr("routes.golden.restore_plan", withdrawn)
    _r, html = _page(lab)
    assert "is withdrawn" in html and "a device was not at intent" in html
    assert "Nothing was planned or sent" in html and 'id="apply-confirm"' not in html


class TestTheConfirm:
    def test_it_starts_the_restore_job_with_exactly_the_confirmed_devices(self, lab,  # noqa: F811
                                                                          monkeypatch):
        from modules import deploy_job
        got = {}
        monkeypatch.setattr("modules.nsot.listref.exists", lambda n: n == "Lab")
        monkeypatch.setattr(deploy_job, "start_restore",
                            lambda *a, **k: got.update(args=a, kw=k) or "job9")
        r = lab["client"].post("/v2/history/reapply/confirm", json={
            "list": "Lab", "tag": TAG, "confirmations": {"r1": "c-r1"},
            "command_hashes": {"r1": "h-r1"}})
        assert r.status_code == 202 and r.get_json()["job"] == "job9"
        assert got["args"][:4] == ("Lab", TAG, {"r1": "c-r1"}, {"r1": "h-r1"})
        assert got["kw"]["authorise"] == {} and got["kw"]["un_onboard"] is None

    @pytest.mark.parametrize("body", [
        {"list": "Lab", "tag": TAG, "confirmations": {"r1": "c"}, "command_hashes": {}},
        {"list": "Nope", "tag": TAG, "confirmations": {"r1": "c"},
         "command_hashes": {"r1": "h"}},
        {"list": "Lab", "tag": "golden/x", "confirmations": {"r1": "c"},
         "command_hashes": {"r1": "h"}},
    ])
    def test_a_body_missing_its_binding_starts_nothing(self, lab, monkeypatch, body):  # noqa: F811
        from modules import deploy_job
        monkeypatch.setattr("modules.nsot.listref.exists", lambda n: n == "Lab")
        monkeypatch.setattr(deploy_job, "start_restore", lambda *a, **k: pytest.fail("started"))
        r = lab["client"].post("/v2/history/reapply/confirm", json=body)
        assert r.status_code == 400 and "Nothing was sent" in r.get_json()["error"]


def test_history_s_re_apply_opens_it_on_v2():
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "templates/v2/history.html"), encoding="utf-8").read()
    assert "url_for('v2.history_reapply', list=ref.name, tag=r.tag)" in src
    assert 'data-todays-page="reapply"' not in src
