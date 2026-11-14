"""Board R's 0(a) in a real browser (the operator, 2026-11-14: "I pressed "Preview the rollout"
..., left the page during its read, and the In progress badge disappeared; back on the page, no
result. The rollout preview must be a background operation like every other: shown under In
progress, surviving navigation, its result reopenable (Finished, not opened yet), and never
lost").

On tests/test_read_account_fleet.py's lab and its `planned` programs (nothing sent): the
preview is pressed on Credentials › Profiles, its read held open; the person leaves for
another page, where In progress lists it running with its link; the read ends; In progress
lists it under Finished, not opened yet; its Open the result reopens Credentials with the
plan's card drawn in place, Deploy the canary on it.
"""

import threading
import time

import pytest

from tests.test_read_account_fleet import lab, planned  # noqa: F401

CHIP = "document.querySelector('#nmas-in-progress')"


@pytest.fixture
def served(lab, planned, monkeypatch):  # noqa: F811
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import routes.deploy as rd

    gate = threading.Event()
    real = rd.plan_devices

    def slow(list_name, hosts, **kw):
        gate.wait(30)
        return real(list_name, hosts, **kw)
    monkeypatch.setattr(rd, "plan_devices", slow)
    # The coverage as the reader holds it: three devices whose intent says the account and whose
    # golden does not hold it yet (the rollout's devices).
    from modules.nsot import read_account as RA
    rows = [{"network": "Lab", "device": d, "dialect": "cisco_iosxe", "platform": "IOS-XE",
             "profile": "default", "account": "mercury-ro", "golden": True, "probe": None,
             "intent": {"profile": "default", "level": 3}, "holds": None, "state": "pending",
             "why": "deploy it"} for d in ("a", "b", "c")]
    monkeypatch.setattr(RA, "held", lambda: {"value": {"devices": rows, "networks": {},
                                                       "level": 3},
                                             "at": "2026-11-14T04:00:00Z", "why": ""})
    monkeypatch.setattr("modules.integration_groups.network_names", lambda: ["Lab"])
    import app as A
    with browser.Served(A.app) as s:
        yield {"served": s, "gate": gate}


def _chip_text(b):
    return b.js(f"var c = {CHIP}; return c ? c.textContent : ''") or ""


def test_the_preview_survives_leaving_the_page_and_reopens_from_in_progress(served):
    from tests import browser

    s, gate = served["served"], served["gate"]
    with browser.Browser() as b:
        b.go(s.url("/v2/credentials/profiles?list=Lab"))
        b.wait_for("return !!document.querySelector('[data-op=read-account-rollout]')", 15)
        b.js("document.querySelector('a[data-op=read-account-rollout]').click(); return 1")
        b.wait_for("return !!document.querySelector('[data-ra-roll-form]')", 15)
        b.js("document.querySelector('[data-ra-roll-form] button[type=submit]').click(); "
             "return 1")
        b.wait_for("return /Planning/.test(document.querySelector('#ra-op').textContent)", 15)
        # Leave the page during the read: In progress lists it, with its link.
        b.go(s.url("/v2/devices?list=Lab"))
        b.wait_for(f"return !!{CHIP} && /running/.test({CHIP}.textContent)", 15)
        assert "Open its card" in _chip_text(b)
        gate.set()
        for _ in range(40):
            b.go(s.url("/v2/devices?list=Lab"))
            if "Finished, not opened yet · 1" in _chip_text(b):
                break
            time.sleep(0.5)
        assert "Finished, not opened yet · 1" in _chip_text(b), _chip_text(b)[:400]
        b.js(f"var c = {CHIP}; var d = c.querySelector('details'); if (d) d.open = true; "
             "var a = Array.prototype.find.call(c.querySelectorAll('a, button'), "
             "function (e) { return /Open the result/.test(e.textContent); }); "
             "a.click(); return 1")
        b.wait_for("return location.pathname === '/v2/credentials/profiles' && "
                   "/ra_job=/.test(location.search)", 15)
        b.wait_for("return /Deploy the canary/.test("
                   "(document.querySelector('#ra-op') || {}).textContent || '')", 15)
