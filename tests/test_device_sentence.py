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


def test_under_the_sentence_the_age_of_what_it_stands_on(lab):  # noqa: F811
    """C's as-of line (Stage 5 step 5): right under the sentence, how old its two readings
    are, the reachability probe (or that none has run) and the last measurement of what the
    device runs, each the same timestamp its row below draws."""
    import app as A
    from modules.device import load_saved_devices
    from modules.nsot import listref
    from routes import device_v2
    _r, html = _get(lab, "/v2/device/r3/overview")
    ref = listref.resolve("Lab")
    dev = next(d for d in load_saved_devices(ref.csv_path) if d["hostname"] == "r3")
    with A.app.test_request_context("/"):
        ctx = device_v2._overview_ctx(ref, dev)
    line = re.search(r'</p>\s*<p class="doc-asof overview-asof" data-asof>(.*?)</p>', html, re.S)
    assert line and html.index("data-sentence") < line.start(), "the line is under the sentence"
    words = re.sub(r"<[^>]+>", "", line.group(1))
    measured = ctx["records"].get("measured")
    assert measured, "the fixture's device has a measurement"
    assert f'datetime="{measured["iso"]}"' in line.group(1), line.group(1)
    assert words.startswith("reachability not probed yet" if not ctx["answer"].get("checked_at")
                            else "reachability checked "), words
    assert " · what it runs measured " in words, words


def test_intent_against_what_it_runs_is_its_own_section_under_the_sentence(lab):  # noqa: F811
    """C's "Intent against what it runs" (Stage 5 step 5; design/proposals/C-document/
    device.html): the Intent check is a section of its own across the Overview, under the
    sentence and before Around this device, its answer a badge beside the heading; Checks no
    longer draws it, so the comparison is said once."""
    import app as A
    from modules.device import load_saved_devices
    from modules.nsot import listref
    from routes import device_v2
    _r, html = _get(lab, "/v2/device/r3/overview")
    ref = listref.resolve("Lab")
    dev = next(d for d in load_saved_devices(ref.csv_path) if d["hostname"] == "r3")
    with A.app.test_request_context("/"):
        ctx = device_v2._overview_ctx(ref, dev)
    # The model is unchanged: one Intent check among the checks, with its state and words.
    assert [c["name"] for c in ctx["checks"]].count("Intent") == 1, ctx["checks"]
    intent = next(c for c in ctx["checks"] if c["name"] == "Intent")
    assert intent["state"] in ("ok", "warn", "danger", "unknown") and intent["text"], intent
    sec = re.search(r'<section class="card overview-intent" data-intent-section>(.*?)</section>',
                    html, re.S)
    assert sec, "the section is drawn"
    head = re.sub(r"<[^>]+>", " ", sec.group(1).split("</div>", 1)[0])
    want = {"ok": "matches", "warn": "departs", "danger": "departs"}.get(intent["state"],
                                                                         "not known")
    assert " ".join(head.split()) == f"Intent against what it runs {want}", head
    assert f"<strong>Intent</strong>: {intent['text']}" in sec.group(1), sec.group(1)
    assert html.index("data-sentence") < sec.start() < html.index("<h2>Around this device</h2>")
    checks = html.split("<h2>Checks</h2>", 1)[1].split("</section>", 1)[0]
    assert "<strong>Intent</strong>" not in checks, "said once, in its own section"
    assert [c["name"] for c in ctx["checks"] if c["name"] != "Intent"] == \
        re.findall(r"<strong>([^<]+)</strong>:", checks), checks
