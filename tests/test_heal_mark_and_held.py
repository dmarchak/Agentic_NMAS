"""Board H, part H9's rest (docs/HEAL_TO_INTENT.md sections 7 and 9; C2399, C2401, C2441), through
the real app on test_heal_decide's lab: no device, no network.

- **Right / Wrong on a dry-run record** (artboard C's "Was this the right fix?"): a dry-run
  incident's History row carries its decision and its mark (`history_sources.heal`); the page
  draws Right and Wrong… under it, each busy on itself; Right pressed records the mark as the
  verified person and answers in place; Wrong needs why (refused with the reason kept, then
  recorded with it); the dry-run counter counts it and the record's Needs attention item
  leaves; a mark of a decision that is not a dry-run record, a value that is not yes or no, or
  a caller who is not a verified person is refused, nothing recorded; decisions that cannot be
  read are said on the row, never "unmarked". Declared in its tables.
- **The held row** (`heal`/`held`): a device whose newest decision is held by a guard a person
  resolves (4, its golden departs; 9, healed past its rate) is one row naming the guard and both
  operands, with the action that guard needs; guard 6 is one row for the network, naming its
  devices; a hold self-healing checks again itself (an *until*) is no row; a later decision of
  the device replaces it; it is acknowledged here, by its decision.
- **An interrupted heal that halted** names Lift the halt on its own item, and the halted row
  carries it.
"""
import json
import os
import re

import pytest

from tests.test_heal_decide import GOLDEN, ROUTE4, T0, Fake, settle  # noqa: F401
from tests.test_heal_decide import lab  # noqa: F401  (the fixture, named by each test below)
from tests.test_heal_proposal_v2 import app_client  # noqa: F401  (the fixture)
from tests.test_heal_records import _left, _taken
from tests.test_heal_triggers import _Lazy
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

DC, DS, SL, INT = _Lazy("decide"), _Lazy("decisions"), _Lazy("steplog"), _Lazy("interrupted")
HX = {"HX-Request": "true"}
WHY = "the route was a planned change"


def dry_run():
    """A real dry-run decision on edge-b (the lab is in dry run), recorded with its step log."""
    inc = settle(GOLDEN + ROUTE4)
    made = DC.decide_one("Default", inc, now=T0, sources=Fake(GOLDEN + ROUTE4))
    assert made["outcome"] == "would_heal", made["words"]
    steps, phase = made.pop("steps", []), made.pop("phase", "decide")
    d = DS.record("Default", made, T0)
    SL.record_decision("Default", dict(d, steps=steps, phase=phase), T0)
    return d


def _ctx(device=""):
    import types
    return {"ref": types.SimpleNamespace(name="Default"), "device": device, "limit": 50,
            "since": None, "until": None, "members": None, "inventory": set()}


def _event():
    from modules import history_sources as HS
    (e,) = HS.heal(_ctx())["events"]
    return e


def _mark_url(d):
    return f"/v2/network/Default/heal/decision/{d['id']}/mark"


def _rows(kind):
    from modules import attention
    return [r for r in attention.heal_source(now=T0 + 60)["rows"] if r["kind"] == kind]


def _timeline(event):
    """The History row as _timeline.html's `timeline_rows` draws it, for one event."""
    from flask import render_template_string
    import app as A
    with A.app.test_request_context("/v2/history"):
        e = dict(event, id="tl-1", devices_words="edge-b", who_short="", pending=False)
        return render_template_string(
            '{% from "v2/_timeline.html" import timeline_rows with context %}'
            "{{ timeline_rows(h) }}", h={"events": [e], "errors": [], "unreached": [],
                                         "limit": 50})


# ── Right / Wrong ────────────────────────────────────────────────────────────────────────────

class TestRightWrong:
    def test_a_dry_run_row_carries_its_decision_and_no_mark(self, lab):
        d = dry_run()
        e = _event()
        assert e["outcome"] == "would_heal"
        assert e["heal_mark"] == {"list": "Default", "decision": d["id"], "unreadable": "",
                                  "mark": None}

    def test_a_dry_run_row_names_mercury_as_who_decided_under_the_policy(self, lab):
        """C2808 (the operator, W1, 2026-11-08): the decision is Mercury's under the policy a
        person confirmed, never drawn "By <the confirmer>" as if they made it."""
        d = dry_run()
        e = _event()
        by = (d.get("policy") or {}).get("by")
        assert by, "the test's policy names who confirmed it"
        assert e["who"] == f"Mercury's self-healing, under Default's policy confirmed by {by}"
        from html import unescape
        # Board E2a: the row's By names the confirmer by display name (the part before the
        # "@"); the identity is under it, in the closed "The identity as recorded".
        drawn = unescape(_timeline(e))
        assert "By Mercury's self-healing, under Default's policy confirmed by " \
            f"{by.split('@')[0]}</p>" in drawn
        assert ("<summary>The identity as recorded</summary>Mercury's self-healing, under "
                f"Default's policy confirmed by {by}</details>") in drawn

    def test_history_draws_right_and_wrong_each_busy_on_itself(self, app_client):
        d = dry_run()
        html = _timeline(_event())
        card = html.split(f'id="heal-mark-{d["id"]}"')[1]
        assert "Was this the right fix?" in card
        right, wrong = re.findall(r'<button type="button"[^>]*>', card)[:2]
        for b, value in ((right, "yes"), (wrong, "no")):
            assert f'hx-post="{_mark_url(d)}"' in b and f'"right": "{value}"' in b
            assert 'hx-disabled-elt="this"' in b and 'data-op="heal"' in b
        assert f'hx-include="#heal-mark-{d["id"]}-why"' in wrong
        assert ">Right<" in card and ">Wrong…</summary>" in card and "Mark it wrong" in card
        assert "Marking…" in card and "<form" not in card
        assert 'data-manual="heal#mark"' in card

    def test_right_pressed_is_recorded_as_the_person_and_the_item_leaves(self, app_client):
        from tests.conftest import TEST_PERSON
        d = dry_run()
        assert len(_rows("would_heal")) == 1
        r = app_client.post(_mark_url(d), data={"right": "yes"}, headers=HX)
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "Marked right by you</strong>" in out
        mark = DS.find("Default", d["id"])["mark"]
        assert mark["right"] is True and mark["by"] == TEST_PERSON
        assert DS.dry_run_counts("Default")["added_line"]["right"] == 1
        assert _rows("would_heal") == [], "the record's item leaves"
        assert _event()["heal_mark"]["mark"]["right"] is True
        # Board E2a: who marked it, by display name (the part before the "@").
        drawn = _timeline(_event())
        assert f"Marked right by {TEST_PERSON.split('@')[0]} at <time" in drawn
        assert TEST_PERSON not in drawn

    def test_wrong_needs_why_and_keeps_what_was_typed(self, app_client):
        d = dry_run()
        r = app_client.post(_mark_url(d), data={"right": "no", "why": "  "}, headers=HX)
        out = r.get_data(as_text=True)
        assert r.status_code == 409
        assert "Not marked:</strong> Wrong is recorded with why it was wrong" in out
        assert "mark" not in DS.find("Default", d["id"])
        r = app_client.post(_mark_url(d), data={"right": "no", "why": WHY}, headers=HX)
        assert r.status_code == 200 and "Marked wrong by you</strong>" in r.get_data(as_text=True)
        assert DS.find("Default", d["id"])["mark"]["why"] == WHY
        assert DS.dry_run_counts("Default")["added_line"]["false_positive"] == 1.0
        assert f"“{WHY}”" in _timeline(_event())

    def test_a_refusal_keeps_the_reason_typed_and_wrong_open(self, app_client):
        d = dry_run()
        r = app_client.post(_mark_url(d), data={"right": "maybe", "why": WHY}, headers=HX)
        out = r.get_data(as_text=True)
        assert r.status_code == 409
        assert "a mark is right=yes or right=no, and &#39;maybe&#39;" in out
        assert f'value="{WHY}"' in out
        assert f'<details class="heal-mark-wrong" data-keep="heal-mark-{d["id"]}-wrong" open>' in out
        # The refusal's effect: nothing was marked.
        assert DS.find("Default", d["id"]).get("mark") is None

    def test_only_a_dry_run_record_is_marked(self, app_client):
        d = DS.record("Default", {"outcome": "propose", "device": "edge-b", "kind": "x"}, T0)
        r = app_client.post(_mark_url(d), data={"right": "yes"})
        assert r.status_code == 409 and r.get_json()["error"] == (
            f"{d['id']} is propose, not a dry-run record: only what self-healing would have "
            "done is marked right or wrong")
        r = app_client.post("/v2/network/Default/heal/decision/hd-nothing/mark",
                            data={"right": "yes"})
        assert r.status_code == 409 and "no heal decision hd-nothing" in r.get_json()["error"]

    @pytest.mark.real_identity
    def test_a_caller_who_is_not_a_verified_person_is_refused(self, app_client):
        d = dry_run()
        r = app_client.post(_mark_url(d), data={"right": "yes"}, headers=HX)
        assert r.status_code in (401, 403), r.status_code
        assert "mark" not in DS.find("Default", d["id"])

    def test_the_store_refuses_a_request_that_is_not_a_persons(self, lab):
        d = dry_run()
        with pytest.raises(DS.NotAPerson, match="actor svc, verified token"):
            DS.mark("Default", d["id"], True, by="svc", actor_verified="token", person=False)

    def test_decisions_that_cannot_be_read_are_said_never_unmarked(self, lab, monkeypatch):
        dry_run()

        def torn(network):
            raise RuntimeError("the store is torn")
        monkeypatch.setattr("modules.heal.decisions.decisions", torn)
        e = _event()
        assert e["heal_mark"]["unreadable"] == ("Default's heal decisions could not be read "
                                                "(the store is torn)")
        html = _timeline(e)
        assert "Whether this record is marked cannot be read" in html
        assert "Not the same as unmarked" in html

    def test_it_is_declared_in_its_tables(self):
        from modules.invalidation import DECLARED
        from modules.operation_stages import HISTORY
        from modules.route_gates import GATES
        assert GATES["heal_proposal_v2.mark"].kind == "configure"
        assert DECLARED["heal_proposal_v2.mark"] == ("drift",)
        assert HISTORY["heal_proposal_v2.mark"].startswith("n/a: a mark is kept")


# ── The held row ─────────────────────────────────────────────────────────────────────────────

def _held(guard, device="edge-b", until=None, epoch=T0, operands=None):
    from modules.heal.guards import hit
    g = hit(guard, "held", f"planted words for guard {guard}", operands or {"planted": 1})
    return DS.record("Default", {"outcome": "held", "device": device, "until": until,
                                 "guard": {k: g[k] for k in ("guard", "name", "words",
                                                             "operands")},
                                 "words": f"guard {guard}"}, epoch)


class TestHeld:
    @pytest.mark.parametrize("guard,href,said", [
        (4, "/v2/device/edge-b?tab=intent", "Adopt the change into edge-b's intent"),
        (9, "/v2/device/edge-b?tab=history", "Read why edge-b keeps departing")])
    def test_a_hold_a_person_resolves_is_one_row_naming_its_guard(self, lab, guard, href,
                                                                  said):
        from modules.attention import CLEARS, ROW_KINDS
        d = _held(guard, operands={"golden_commit": "c0ffee", "intent_match": "departs"})
        (r,) = _rows("held")
        assert r["level"] == "warning" and r["devices"] == ["edge-b"] and r["event"] == d["id"]
        from modules.heal.policy import GUARDS
        name = next(n for num, n, _k in GUARDS if num == guard)
        assert r["what"] == f"Self-healing holds edge-b on Default: {name}"
        assert r["cause"].startswith(f"Guard {guard}, {name}: planted words for guard {guard}")
        assert r["action"]["href"] == href and r["action"]["label"].startswith(said)
        assert r["operands"]["golden_commit"] == "c0ffee" and r["operands"]["guard"] == guard
        assert ("heal", "held") in ROW_KINDS and r["acknowledge"] is True
        assert r["clears"]["when"] == CLEARS[("heal", "held")][1]

    def test_many_devices_at_once_is_one_row_for_the_network(self, lab):
        for n, host in enumerate(("edge-a", "edge-b", "edge-c", "edge-d")):
            _held(6, device=host, epoch=T0 + n)
        (r,) = _rows("held")
        assert r["devices"] == ["edge-a", "edge-b", "edge-c", "edge-d"]
        assert r["what"] == "Self-healing holds 4 device(s) on Default: many devices at once"
        assert r["action"]["href"] == "/v2/history?kind=heal"

    @pytest.mark.parametrize("guard", [3, 5, 7, 8, 4, 9])
    def test_a_hold_self_healing_checks_again_is_no_row(self, lab, guard):
        _held(guard, until=T0 + 600)
        assert _rows("held") == []

    def test_a_later_decision_of_the_device_replaces_it(self, lab):
        _held(4)
        assert len(_rows("held")) == 1
        DS.record("Default", {"outcome": "nothing", "device": "edge-b"}, T0 + 30)
        assert _rows("held") == []

    def test_a_guard_outside_the_table_is_no_row(self, lab):
        _held(12)
        assert _rows("held") == []


# ── An interrupted heal's halt (C2441) ───────────────────────────────────────────────────────

def test_an_interrupted_heal_that_halted_names_lift_the_halt_and_its_item_carries_it(lab):
    d = _taken()
    SL.record_started("Default", d, [{"step": "apply", "result": "running",
                                      "words": "applying"}], d["program"],
                      d["program_hash"], by="test", now=T0 + 2)
    _left(d)
    INT.reap("Default", now=T0 + 9)
    halt = DS.halted("Default")
    assert halt["guard"] == 14
    (r,) = _rows("interrupted")
    assert r["action"]["label"].endswith(
        "then acknowledge with what you found. Then lift the halt with a reason on its own "
        "item, “Self-healing halted on Default” (Lift the halt…)")
    (h,) = [x for x in _rows("halted") if x["id"] == f"heal:{halt['id']}"]
    assert h["action"]["open"] == "heal_halt" and h["action"]["halt"] == halt["id"]


def test_an_interrupted_heal_that_did_not_halt_names_no_lift(lab):
    d = _taken()
    SL.record_raised("Default", d, "RuntimeError: the session pool is closed")
    INT.reap("Default", now=T0 + 9)
    (r,) = _rows("interrupted")
    assert r["action"]["label"].endswith("then acknowledge with what you found")
    assert "Lift the halt" not in json.dumps(r)


def test_the_heal_manual_page_names_the_mark_and_the_hold():
    from modules import manual
    for section in ("mark", "held"):
        assert manual.section("heal", section)
    assert os.path.exists(os.path.join(manual.MANUAL_DIR, "how-it-works", "heal.md"))
