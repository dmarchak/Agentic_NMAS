"""C2824 (the operator, 2026-11-09, verbatim): "When drift came from outside Mercury and
something broke at the same time, the card never offers Capture. Its two actions are 'Put it
back to intent' and 'Keep it: add it to intent' (through Adopt). Capture stays available
elsewhere for a change that broke nothing."

In H11's W7 (2026-11-08) r6's drift row offered "Capture r6's golden … which closes this" (the
queued drift item's action, attached to the row) while r6's new ACL had taken its adjacency to
r4 down: capturing it would have made the fault r6's approved state, which self-healing then
puts back. The case is read from self-healing's own incidents (`incidents.drift_cases`), each
built here by the real triggers and the real decision on tests/test_heal_standing.py's fold
world (core-b changed by a CONFIG_I from outside Mercury, its blast radius leaf-c):

- **broke** (W2's would-heal and W7's can't-fix, a symptom on a device inside its radius; W3's,
  a symptom on the device itself): the row names whose change it was and what broke, offers Put
  it back to intent… (the device's Deploy) and Keep it: add it to intent… (its Intent tab's
  editor), and no Capture; the queued drift item's Capture does not replace them; the device
  page's drift card offers the same two and no Capture;
- **quiet** (changed from outside Mercury, nothing broke): Capture is offered, as before, and
  the words say so;
- **unknown** (self-healing holds no incident for it): Capture is offered, the words saying who
  made it and whether anything broke are not known here;
- **unread** (the incidents cannot be read): Capture is not offered until they can be.

C2807: the row's Details and the queued item's words count the lines that differ, the count the
row's words say.
"""
import os
import re

import pytest

from tests.test_heal_decide import Fake, I, iso  # noqa: F401
from tests.test_heal_decide import lab  # noqa: F401  (the fixture `fold` builds on)
from tests.test_heal_policy import T0
from tests.test_heal_standing import (R8, TWO, alerted, change, decide,  # noqa: F401
                                      fold, no_host_addresses)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)


def _status(host="core-b", changed=4, diff=21):
    """The drift run's stored record naming *host* drifted, as the checker answers it."""
    last = {"ok": True, "checked": 3, "inventory": 3, "triggered_by": "scheduled",
            "drifted_devices": [{"hostname": host, "diff_lines": diff, "changed_lines": changed,
                                 "read_at": T0 + 300}], "skipped": [], "errors": []}
    return lambda: {"list": "Default", "state": "idle", "disabled": False, "last_run": last,
                    "last_ts": T0 + 300}


def _row(host="core-b"):
    from modules import attention as A

    res = A.drift_source(_status(host), now=T0 + 310)
    (r,) = [x for x in res["rows"] if x["id"] == f"drift:Default:drifted:{host}"]
    return r


def _with_item(r, host="core-b", changed=4):
    """*r* with the drift run's queued item attached, as Needs attention merges them."""
    from modules import attention as A

    item = {"id": "a1", "action_type": "update_golden_config", "device_hostname": host,
            "description": f"Config drift detected on {host} — {changed} changed lines",
            "context": "Detected by scheduled drift check", "created_ts": T0 + 300}
    (q,) = A.approvals_source(read=lambda: ([item], ""))["rows"]
    (merged,) = A._attach([r, q])
    return merged


def _html(r):
    from flask import render_template

    import app as APP
    with APP.app.test_request_context("/v2/"):
        return render_template("v2/_attention.html", a={
            "ok": True, "rows": [r], "sources": [], "headline": "1", "counts": {},
            "badge": {"n": 1, "level": r["level"]}})


def _broke_w2():
    change("core-b", T0)
    assert decide("core-b", R8, T0 + 150)["outcome"] == "would_heal"
    alerted("leaf-c", T0 + 214)


def _broke_w7():
    change("core-b", T0)
    assert decide("core-b", TWO, T0 + 150)["outcome"] == "cant_fix"
    alerted("leaf-c", T0 + 249, rule="Telemetry stream lost")


def _broke_w3():
    change("core-b", T0)
    assert decide("core-b", R8, T0 + 150)["outcome"] == "would_heal"
    alerted("core-b", T0 + 207)


class TestBroke:
    @pytest.mark.parametrize("walk", [_broke_w2, _broke_w7, _broke_w3])
    def test_a_change_from_outside_that_broke_something_is_never_offered_capture(self, fold,
                                                                                 walk):
        walk()
        r = _with_item(_row())
        assert r["action"]["open"] == "drift_back", r["action"]
        assert r["what"] == ("core-b was changed from outside Mercury, and something broke at "
                             "the same time")
        # Whose change, when, and what broke, in the row's own words (the charter's rule 5).
        assert "core-b was changed from outside Mercury at " in r["cause"], r["cause"]
        assert "the account alice" in r["cause"], r["cause"]
        broke = "core-b: a firing alert" if walk is _broke_w3 else "leaf-c: a firing alert"
        assert broke in r["cause"], r["cause"]
        assert "so Capture is not offered" in r["cause"]
        html = _html(r)
        assert ('href="/v2/device/core-b?list=Default&amp;op=deploy">Put it back to intent…</a>'
                in html), html
        assert ('href="/v2/device/core-b?list=Default&amp;tab=intent&amp;edit=1">Keep it: add '
                "it to intent…</a>" in html), html
        assert "op=capture" not in html and "Capture core-b" not in html
        assert "which closes this" not in html, "the queued item's Capture replaced them"
        assert "Also: An approval is waiting: Config drift detected on core-b — 4 changed " \
               "lines" in html

    def test_put_it_back_says_today_s_limit_plainly(self, fold):
        _broke_w7()
        label = _row()["action"]["label"]
        assert label.startswith("Put it back to intent, or keep it: add it to intent")
        assert "its apply refuses with nothing sent" in label and "C2848" not in label

    def test_the_device_page_s_drift_card_offers_the_same_two(self, fold):
        from flask import render_template

        import app as APP
        from modules import attention as A
        _broke_w7()
        case = A.drift_case("core-b", "Default", A._drift_cases("Default"))
        d = {"host": "core-b", "list": "Default", "run_at": "", "golden": {},
             "diff": {"absent": "kept nowhere"}, "logs": {"configured": False},
             "case": {"capture": case["capture"], "words": case["words"]}}
        with APP.app.test_request_context("/v2/device/core-b/drift?list=Default"):
            html = render_template("v2/_drift_detail.html", d=d)
        assert "Put it back to intent…" in html and "Keep it: add it to intent…" in html
        assert "op=capture" not in html and ">Capture<" not in html, html
        assert "Core-b was changed from outside Mercury" in html


class TestCaptureStaysWhereNothingBroke:
    def test_quiet_a_change_from_outside_that_broke_nothing(self, fold):
        change("core-b", T0)
        assert decide("core-b", R8, T0 + 150)["outcome"] == "would_heal"
        r = _row()
        assert r["action"]["open"] == "drift" and r["what"] == "core-b has drifted from its golden"
        assert "core-b was changed from outside Mercury at " in r["cause"]
        assert "nothing broke with it that self-healing saw" in r["cause"], r["cause"]
        html = _html(_with_item(r))
        assert "which closes this" in html, "the queued item's Capture is its action, as before"

    def test_unknown_no_incident_for_the_change(self, fold):
        r = _row()
        assert r["action"]["open"] == "drift", r["action"]
        assert ("self-healing holds no incident for core-b's change, so who made it and "
                "whether anything broke with it are not known here") in r["cause"]
        html = _html(r)
        assert 'op=capture">Capture core-b…</a>' in html

    def test_a_closed_incident_is_not_the_change_s(self, fold):
        change("core-b", T0)
        (inc,) = I.read("Default")["incidents"]
        alerted("core-b", T0 + 30)
        I.close("Default", inc["id"], "a test closes it", now=T0 + 60)
        assert _row()["action"]["open"] == "drift"


class TestUnread:
    def test_unreadable_incidents_offer_no_capture_until_they_can_be_read(self, fold):
        change("core-b", T0)
        with open(I.path("Default"), "w", encoding="utf-8") as fh:
            fh.write('{"incidents": [')
        r = _row()
        assert r["action"]["open"] == "drift_back", r["action"]
        assert "whether anything broke with core-b's change cannot be read" in r["cause"]
        assert "so Capture is not offered until it can" in r["cause"]


class TestTheCounts:
    def test_the_row_s_details_count_the_lines_that_differ(self, fold):
        r = _row()
        assert "by 4 changed line(s)" in r["cause"]
        assert r["operands"]["changed_lines"] == 4 and "diff_lines" not in r["operands"]

    def test_a_run_from_before_says_its_diff_s_length_as_it_was(self, fold):
        from modules import attention as A
        last = {"ok": True, "checked": 1, "inventory": 1,
                "drifted_devices": [{"hostname": "core-b", "diff_lines": 11}]}
        res = A.drift_source(lambda: {"list": "Default", "last_run": last, "last_ts": T0},
                             now=T0 + 10)
        (r,) = res["rows"]
        assert r["operands"]["diff_lines"] == 11 and "changed_lines" not in r["operands"]

    def test_the_queued_item_counts_the_lines_that_differ(self, monkeypatch, tmp_path):
        """Through run_drift_check() (tests/payload_providers.py's real run: r2 gained one
        line): the queued item's words say the run's changed lines."""
        from tests import payload_providers as P
        queued = []

        class _KeepTheQueue:
            """The provider's monkeypatch, but for its queue, which this test reads."""

            def setattr(self, target, value, *rest):
                if target != "modules.approval_queue.add_approval":
                    monkeypatch.setattr(target, value, *rest)

        monkeypatch.setattr("modules.approval_queue.add_approval",
                            lambda **kw: queued.append(kw) or {"ok": True})
        result = P._drift_run(_KeepTheQueue(), tmp_path)
        (d,) = result["drifted_devices"]
        assert d["changed_lines"] == 1 < d["diff_lines"], d
        (item,) = queued
        assert item["description"] == f"Config drift detected on {d['hostname']} — 1 changed lines"


def test_the_manual_says_the_rule():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for page in ("screens/needs-attention.md", "concepts/drift.md"):
        text = open(os.path.join(root, "docs", "manual", page), encoding="utf-8").read()
        flat = re.sub(r"\s+", " ", text)
        assert "Put it back to intent" in flat and "Keep it: add it to intent" in flat, page
        assert re.search(r"never (offers|offered) Capture", flat), page
