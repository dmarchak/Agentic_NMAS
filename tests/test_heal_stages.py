"""A self-heal read as ONE run, in five stages, by Mercury (the operator's F1 self-heal smoke
test of r3 in Auto, 2026-11-12, the headline of Lab 10's video):

1. "The decision's steps (Take incident … Classify change) are drawn grey/italic as if not done.
   They were done by the detection job: draw them done, with their times, as one continuous
   run." (C3159)
2. "ONE stepper: the deploy's stages belong INSIDE "Apply" (expanding), not as a second
   stepper." (C3160)
3. "A self-heal is never "by <person>" or "started by you": the chip, the banner and the card
   read "by Mercury's self-healing · policy set by <display name>"." And: "the card still says
   "Started … as <the operator's email>" for a self-heal": no email anywhere on them. (C3161)
4. "A linear stepper (one row, wrapping cleanly), not a grid with gaps; no "Reopened" label."
   (C3162)
5. "The stepper shows FIVE stages: Detected → Decided → Fixing → Checking → Done, each with one
   plain sentence, its time and its state ... Each stage expands to its detailed steps." (C3163)

Through the real app, the REAL detection job's decision (`decide.run`, which keeps its steps in
the step log, not in the decision's own record) and the real act over tests/test_heal_act.py's
fakes, and in a real browser for the row that wraps. No device, no network.
"""
import re

import pytest

from modules.nsot.device_ops import holder as REAL_HOLDER  # before the lab replaces it
from tests.test_heal_act import SETTER, FakeAct
from tests.test_heal_decide import GOLDEN, ROUTE4, Fake, settle
from tests.test_heal_decide import lab as heal_lab  # noqa: F401
from tests.test_heal_policy import T0, auto
from tests.test_in_flight import no_hold_survives_a_test  # noqa: F401 (autouse)
from tests.test_run_outcomes import (bar, drawn_steps, heal, page, recorded,  # noqa: F401
                                     stage_states)
from tests.test_run_progress import Gated
from tests.test_sdn_connections import networks  # noqa: F401 (the lab builds on it)

FIVE = ("detected", "decided", "fixing", "checking", "done")
MERCURY = "Mercury&#39;s self-healing · policy set by " + SETTER.split("@")[0]


def detected_and_run(c, running=GOLDEN + ROUTE4, sources=None):
    """One heal as the lab runs it: an incident settled and left READY, decided by the real
    detection job's decision (`decide.run`), then started by the real runner as its own job.
    ``(job, decision, src)``."""
    from modules.heal import act, decide, decisions, policy

    auto("Default", now=T0 - 60, kinds=("added_line",))
    settle(running, claim=False)
    got = decide.run("Default", now=T0, sources=Fake(running))
    assert [d["outcome"] for d in got["decided"]] == ["heal"], got
    d = decisions.find("Default", got["decided"][0]["decision"])
    assert not d.get("steps"), "the premise: the decision's own record keeps no steps"
    src = sources or FakeAct(running, mode=lambda _got: policy.current("Default", T0 + 5))
    ran = act.run("Default", now=T0 + 5,
                  starter=lambda network, taken: act.start(network, taken, sources=src))
    assert ran["started"] and not ran["failed"], ran
    job = ran["started"][0]["job"]
    c.state["jobs"].append(job)
    return job, d, src


def card_of(body):
    return body[body.index('id="device-op"'):body.index("</section>")]


class TestOneRunFromItsDetection:
    def test_the_decision_s_steps_are_done_with_their_times(self, heal):
        from modules.heal import steplog
        from modules.nsot import capture_job
        job, d, _src = detected_and_run(heal)
        assert capture_job.wait(job, 30)
        body = card_of(page(heal, "edge-b", "Default"))
        # The record the card is drawn from: the step log's decision row holds the steps the
        # detection job took (the decision's own record holds none).
        (row,) = [r for r in steplog.of_decision("Default", d["id"])["rows"]
                  if r.get("row") == "decision"]
        assert [s["step"] for s in row["steps"]] == [
            "claim", "stops", "approved", "guards", "read", "classify", "decide", "record"]
        steps = drawn_steps(body)
        decided = {k: v for k, v in steps.items() if k.startswith("d-")}
        assert len(decided) == 8 and set(decided.values()) == {"done"}, decided
        for key in decided:
            line = body[body.index(f'data-step="{key}"'):]
            assert '<time class="clock"' in line[:line.index("</li>")], f"{key}: its time"
        # One continuous run: what was seen, its decision, the act, in that order.
        assert list(stage_states(body)) == list(FIVE)
        assert set(stage_states(body).values()) == {"done"}, stage_states(body)
        order = [body.index(f'data-step="{k}"') for k in ("x-opened", "d-claim", "d-classify",
                                                          "take", "apply", "record")]
        assert order == sorted(order)

    def test_each_stage_says_one_sentence_its_time_and_its_state(self, heal):
        from modules.nsot import capture_job
        job, d, src = detected_and_run(heal)
        assert capture_job.wait(job, 30)
        body = card_of(page(heal, "edge-b", "Default"))
        # Its effect, as Mercury's record keeps it: healed, the program sent as the policy.
        assert recorded(d) == "healed" and src.apply_kw["actor"] == SETTER
        said = dict(re.findall(r'data-stage="([^"]+)".*?<span class="run-stage-said"[^>]*>'
                               r'(.*?)</span>', body, re.S))
        assert said["detected"] == "edge-b&#39;s configuration changed outside Mercury"
        assert said["decided"].startswith("Heal: remove ")
        assert said["fixing"] == "Applied 1 line to edge-b"
        assert said["checking"].startswith("edge-b at intent")
        assert said["done"].startswith("Healed and verified")
        for key in FIVE:
            block = body[body.index(f'data-stage="{key}"'):]
            block = block[:block.index("</summary>")]
            assert '<span class="run-stage-time"><time class="clock"' in block, key
            assert f"({'done'})" in block, f"{key}: its state, for a reader"


class TestMercurysOwn:
    """C3161: Mercury's own, never a person's, and no email anywhere on it."""

    def test_running_the_chip_the_banner_and_the_card_name_mercury(self, heal, monkeypatch):
        from modules.heal import policy
        heal.state["viewer"] = SETTER                 # the setter looking: still never "you"
        src = Gated(GOLDEN + ROUTE4, mode=lambda _got: policy.current("Default", T0 + 5))
        _job, _d, _src = detected_and_run(heal, sources=src)
        from modules.nsot import device_ops
        try:
            src.reached("apply")
            # The device held as the heal's deploy holds it (the act's fakes send nothing, so
            # the hold the pipeline takes is taken here, as the policy's setter).
            # The lab reads no hold while it decides (guard 7); the page reads them for real.
            monkeypatch.setattr(device_ops, "holder", REAL_HOLDER)
            with device_ops.hold("Default", "edge-b", "deploy", SETTER,
                                 detail="heal to intent"):
                device_ops.note("deploy")
                chip = bar(heal)
                # What the screens are drawn from: the job is the policy's, run as its setter,
                # and the hold the server refuses by is that setter's.
                from modules.nsot import capture_job
                kept = capture_job.get(_job)
                assert (kept["actor"], kept["actor_kind"]) == (SETTER, "policy")
                assert device_ops.holder("Default", "edge-b")["actor"] == SETTER
                row = chip[chip.index('class="ip-row"'):]
                row = row[:row.index("</small>")]
                assert MERCURY in row, row
                full = heal.get("/v2/device/edge-b?list=Default").get_data(as_text=True)
                card = card_of(full)
                held = heal.get("/v2/device/edge-b/held?list=Default").get_data(as_text=True)
                assert "By " + MERCURY + " · started " in card
                assert "is held:" in held and MERCURY in held, held
                for where, html in (("the In progress row", row), ("the card", card),
                                    ("the held banner", held),
                                    ("the page above the card",
                                     full[full.index('id="tab-body"'):
                                          full.index('id="device-op"')])):
                    assert "@" not in html, f"{where} draws an email"
                    assert "by you" not in html and "started by" not in html, where
                    assert "Reopened" not in html, where
                # ONE stepper: the deploy's stages inside Apply, never a second stepper.
                assert card.count("data-run-stepper") == 1
                apply = card[card.index('data-step="apply"'):]
                assert '<ol class="run-sub"' in apply[:apply.index("</li>\n          </ol>")]
        finally:
            src.let_go()

    def test_ended_the_chip_and_the_card_name_mercury(self, heal):
        from modules.nsot import capture_job
        heal.state["viewer"] = SETTER
        job, d, _src = detected_and_run(heal)
        assert capture_job.wait(job, 30)
        chip = bar(heal)
        # Its effect: healed, the job the policy's, its setter the actor.
        kept = capture_job.get(job)
        assert recorded(d) == "healed"
        assert (kept["actor"], kept["actor_kind"]) == (SETTER, "policy")
        row = chip[chip.index('class="ip-row"'):]
        row = row[:row.index("</small>")]
        assert MERCURY in row and "@" not in row and "· you ·" not in row, row
        body = page(heal, "edge-b", "Default")
        assert 'class="op-reopened"' not in body, "the card says who it is by, once"
        card = card_of(body)
        assert card.count(MERCURY) == 1 and "@" not in card


def test_the_stages_are_one_row_that_wraps_in_a_real_browser(heal):  # noqa: F811
    """C3162: one row of stages on a desk, each beside the one before with no gap but its
    padding; at phone width each below the one before; nothing past the screen's edge."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as nmas
    from modules.nsot import capture_job
    job, d, _src = detected_and_run(heal)
    assert capture_job.wait(job, 30)
    measure = ("return {inner: window.innerWidth, scroll: document.documentElement.scrollWidth,"
               " boxes: Array.from(document.querySelectorAll('#device-op .run-stage')).map("
               "function(e){var r=e.getBoundingClientRect(); return [Math.round(r.left),"
               " Math.round(r.top), Math.round(r.right), Math.round(r.bottom)];})};")
    # The run named (its result drawn whoever opened it before).
    url = f"/v2/device/edge-b?list=Default&result={job}"
    got = {}
    # A desk at 1280 CSS px, and the narrowest window geckodriver makes (about 500 px,
    # tests/browser.py), where the card is narrower than its row of five.
    with browser.Served(nmas.app) as srv:
        for name, prefs, width in (("desk", None, 1280),
                                   ("phone", None, 500)):
            with browser.Browser(prefs=prefs) as b:
                try:
                    b._call("POST", f"/session/{b.session}/window/rect",
                            {"width": width, "height": 900})
                    b.go(srv.url(url))
                    b.wait_for("return document.querySelectorAll('#device-op .run-stage')"
                               ".length === 5", 15)
                    got[name] = b.js(measure)
                finally:
                    b.go("about:blank")
                    browser.close_socketio_sessions()
    assert recorded(d) == "healed", "the run drawn is the one the record holds"
    desk, phone = got["desk"], got["phone"]
    assert phone["inner"] <= 520, ("as narrow as geckodriver makes a window", phone)
    boxes = desk["boxes"]
    assert len(boxes) == 5 and len({top for _l, top, _r, _b in boxes}) == 1, \
        ("one row on a desk", boxes)
    for (_l, _t, right, _b), (left, _t2, _r2, _b2) in zip(boxes, boxes[1:]):
        assert 0 <= left - right <= 1, ("each stage beside the one before, no gap", boxes)
    assert desk["scroll"] <= desk["inner"], desk
    boxes = phone["boxes"]
    for (_l, _t, _r, bottom), (_l2, top, _r3, _b3) in zip(boxes, boxes[1:]):
        assert top >= bottom - 1, ("each stage below the one before at phone width", boxes)
    assert all(right <= phone["inner"] for _l, _t, right, _b in boxes), phone
    assert phone["scroll"] <= phone["inner"], phone
