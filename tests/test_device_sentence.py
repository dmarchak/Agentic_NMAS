"""A device's Overview as C's document (the operator's GUI pick, 2026-11-25; Stage 5 step 5): its
one sentence (`device_page.sentence`), from the same reachability answer, intent state and
checks the tab draws under it.

- Whether it answers (or the operation it is under, or that it is not probed yet) and how it
  stands against its intent, the Intent check's answer now before the Devices list's measured
  one; then the checks that need a look and those not known yet; "every other check passes"
  only when each said so.
- On the page: the Overview's first line is the sentence of the same answer, records and checks,
  and it moves with them (a check that turns, the sentence after).
"""
import re

from modules import device_page as D
from tests.test_device_v2 import _get, lab  # noqa: F401 (the fixture)

DEV = {"hostname": "r2"}


def _c(name, state, unreadable=False):
    return {"name": name, "state": state, "unreadable": unreadable, "text": ""}


def test_a_reachable_device_at_its_intent_with_every_check_passing():
    got = D.sentence(DEV, {"state": "ok"}, {"intent_state": {"state": "departs"}},
                     [_c("Intent", "ok"), _c("Reboot-safe", "ok"), _c("Alerts", "ok")])
    assert got == {"lead": "r2 is reachable and runs its intent.",
                   "rest": "Every other check passes."}


def test_the_checks_to_look_at_and_those_not_known_are_named():
    got = D.sentence(DEV, {"state": "danger"}, {},
                     [_c("Intent", "warn"), _c("Reboot-safe", "warn"), _c("Credential", "ok"),
                      _c("Alerts", "unknown"), _c("Since last capture", "unknown"),
                      _c("Logs", "unknown", unreadable=True)])
    assert got == {"lead": "r2 is not reachable and differs from its intent.",
                   "rest": "Reboot-safe and Logs need a look; Alerts and Since last capture are "
                           "not known yet."}


def test_not_probed_and_no_intent_say_so_and_never_claim_a_pass():
    got = D.sentence(DEV, {"state": "unknown", "text": "not probed yet"},
                     {"intent_state": {"state": "no_intent"}},
                     [_c("Intent", "unknown"), _c("Alerts", "unknown")])
    assert got == {"lead": "r2 has not been probed yet and has no committed intent.",
                   "rest": "Alerts is not known yet."}
    assert "passes" not in got["rest"]


def test_a_check_that_is_off_is_never_counted_as_passing():
    """The Credential check is "off" with no rotation policy: neither a pass nor a fault."""
    got = D.sentence(DEV, {"state": "ok"}, {}, [_c("Intent", "ok"), _c("Alerts", "ok"),
                                                _c("Credential", "off")])
    assert got == {"lead": "r2 is reachable and runs its intent.",
                   "rest": "Credential is not checked."}


def test_under_an_operation_it_says_the_operation():
    got = D.sentence(DEV, {"state": "planned", "text": "restarting as planned"}, {}, [])
    assert got == {"lead": "r2: restarting as planned.", "rest": ""}


def test_the_overview_opens_with_the_sentence_of_what_it_draws(lab):  # noqa: F811
    import app as A
    from modules.device import load_saved_devices
    from modules.nsot import listref
    from routes import device_v2
    _r, html = _get(lab, "/v2/device/r3/overview")
    said = re.search(r'<p class="doc-summary overview-said" data-sentence><strong>(.*?)</strong>'
                     r'(?: (.*?))?</p>', html)
    assert said, html[:1500]
    ref = listref.resolve("Lab")
    dev = next(d for d in load_saved_devices(ref.csv_path) if d["hostname"] == "r3")
    with A.app.test_request_context("/"):
        ctx = device_v2._overview_ctx(ref, dev)
    assert ctx["checks"] and ctx["said"] == D.sentence(dev, ctx["answer"], ctx["records"],
                                                       ctx["checks"])
    assert (said.group(1), said.group(2) or "") == (ctx["said"]["lead"], ctx["said"]["rest"])
    # Each check drawn below as not known yet is named so in the sentence.
    for c in ctx["checks"]:
        if c["name"] != "Intent" and c["state"] == "unknown" and not c.get("unreadable"):
            assert c["name"] in said.group(2), (c["name"], said.group(2))
