"""The AI day cap has no program maximum (the operator's order of 2026-10-27, a freeze
exception: "ai_cap_usd_per_day: 80.0 is greater than the maximum of 50" refused an enterprise's
own limit). Limits belong to the customer, not the program.

- **The schema** takes a positive amount or null (no cap) for the day cap, with no maximum, and
  refuses 0 and negatives; the retiring per-call cap has no maximum either; a rotation
  policy's days and devices a run have none, their minimums kept.
- **The card** (Settings › Installation › AI, AI (hosted), through the real route as a
  verified person) saves $80 and $5,000; refuses $0 and a negative, saying so, writing nothing.
- **History**: a card's Save records each field's old and new value, and History draws it:
  "AI (hosted): Cap per day $50 → $80", who and when.
- **A large increase** (`installation_settings.is_large`: at least double, or at least $50
  more) draws its confirmation, "Up to $X a day, about $Y a month at full use", and writes
  nothing until its Save; the confirmation carries what the card drew (R17), so a change
  another person made meanwhile is still refused.
- **No cap** is a control of its own, confirmed only by typing "no cap": without the words it
  is drawn and refused, writing nothing; with them the key is stored as null, the card says so,
  and `ai.controls.cap_state` answers no cap for the toolbar's chip.
- **The gateway** with no cap sends a call whatever today's spend (no day-cap refusal) and
  says "no day cap is set" in a cap refusal; with a cap it refuses as before.
"""
import json
import re
from html import unescape

import pytest

from modules import installation_settings as I
from modules import settings_schema as S
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

SAVE = "/v2/settings/installation/card/ai/save"


def _post(n, data):
    r = n["client"].post(SAVE, data=data, headers={"HX-Request": "true"})
    return r, re.sub(r"\s+", " ", unescape(r.get_data(as_text=True)))


def _text(html):
    """What a person reads: the markup's tags removed."""
    return re.sub(r"<[^>]+>", "", html)


def _page(n):
    return n["client"].get("/v2/settings/installation?tab=ai").get_data(as_text=True)


def _loaded(n):
    m = re.search(r'id="form-ai".*?name="loaded" value=\'([^\']*)\'', _page(n), re.S)
    assert m, "the AI card draws no loaded field"
    return unescape(m.group(1))


def _record(n):
    p = n["dir"] / "settings_record.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def _cap():
    return S.get_setting("ai_cap_usd_per_day")


def _set(n, value):
    """The day cap stored as *value*, through the one write path (not the card)."""
    assert S.write_settings({"ai_cap_usd_per_day": value})["ok"]


def _save(n, cap, **extra):
    return _post(n, dict({"ai_cap_usd_per_day": cap, "ai_cap_day_boundary": "UTC",
                          "loaded": _loaded(n)}, **extra))


def _confirm_form(html):
    """The confirmation's form as the browser sends it: its hidden fields, `loaded` read whole
    (a JSON value)."""
    m = re.search(r'class="notice notice-warn set-result set-confirm".*?</form>', html)
    assert m, "no confirmation drawn"
    form = m.group(0)
    fields = dict(re.findall(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"', form))
    fields["loaded"] = re.search(r'name="loaded" value=\'([^\']*)\'', form).group(1)
    return fields


@pytest.fixture
def no_send(monkeypatch):
    from modules.ai import anthropic_adapter

    def refuse(*a, **k):
        raise AssertionError("a call was sent")
    monkeypatch.setattr(anthropic_adapter, "send", refuse)


# ---------------------------------------------------------------------------- the schema

@pytest.mark.parametrize("value", [None, 0.0001, 1.5, 50.01, 80, 5000, 1_000_000])
def test_the_schema_takes_a_positive_day_cap_or_null_with_no_maximum(value):
    assert S.validate({"ai_cap_usd_per_day": value}) == (True, "")


@pytest.mark.parametrize("value", [0, 0.0, -1, -0.01])
def test_the_schema_refuses_a_day_cap_of_0_or_less(value):
    ok, why = S.validate({"ai_cap_usd_per_day": value})
    assert not ok and "less than or equal to the minimum of 0" in why, why


def test_the_other_spend_and_count_limits_have_no_maximum_their_minimums_kept():
    assert S.validate({"ai_cap_usd_per_call": 500})[0], "the retiring per-call cap: no maximum"
    assert not S.validate({"ai_cap_usd_per_call": -1})[0]
    policy = {"state": "on", "days": 36500, "window_start": 0, "window_end": 24,
              "max_per_run": 5000, "set_by": "a@example.invalid", "set_at": "2026-10-27"}
    assert S.validate({"credential_rotation_policies": {"role:router": policy}})[0]
    for key, low in (("days", 0), ("max_per_run", 0)):
        bad = {"credential_rotation_policies": {"role:router": dict(policy, **{key: low})}}
        assert not S.validate(bad)[0], key
    # A clock's bounds and a protocol's stay: they are not the customer's to raise.
    hour = {"credential_rotation_policies": {"role:router": dict(policy, window_start=24)}}
    assert not S.validate(hour)[0]
    assert not S.validate({"flask_port": 70000})[0]


# ---------------------------------------------------------------------------- the card

def test_80_and_5000_save(networks, no_send):
    """$80 from $60 is not large (neither double nor $50 more): saved at once. $5,000 from $80
    is: saved by its confirmation's Save, the thousands comma taken."""
    _set(networks, 60.0)
    r, html = _save(networks, "80")
    assert r.status_code == 200 and "Saved" in html and "Cap per day $60 → $80" in html, html
    assert _cap() == 80.0
    r, html = _save(networks, "5,000")
    assert r.status_code == 200 and "A large increase" in html and _cap() == 80.0
    r, html = _post(networks, _confirm_form(html))
    assert r.status_code == 200 and "Cap per day $80 → $5,000" in html and _cap() == 5000.0


@pytest.mark.parametrize("typed", ["0", "0.00", "-5", "-0.01"])
def test_0_and_negatives_are_refused_saying_so_and_nothing_is_written(networks, no_send, typed):
    r, html = _save(networks, typed)
    assert r.status_code == 409, html
    assert f"Cap per day '{typed}' is not a positive amount: it must be more than $0" in html
    assert "for no cap, choose No cap" in html and "Nothing was changed" in html
    assert _cap() == 1.5 and _record(networks) == []


def test_the_card_draws_the_no_cap_choice_beside_the_field_unticked(networks, no_send):
    card = re.search(r'id="card-ai".*?</section>', _page(networks), re.S).group(0)
    tick = re.search(r'<input id="f-ai-ai_cap_usd_per_day-none" name="no_cap" type="checkbox"'
                     r' value="on"( checked)?>', card)
    assert tick and not tick.group(1), "No cap is drawn, unticked while a cap is set"
    assert "No cap is set" not in card


# ---------------------------------------------------------------------------- History

def test_a_change_is_recorded_old_and_new_and_history_draws_it_with_who_and_when(networks,
                                                                                no_send):
    from modules import history_sources as H
    _set(networks, 50.0)
    r, _html = _save(networks, "80")
    assert r.status_code == 200 and _cap() == 80.0
    (row,) = [x for x in _record(networks) if x["kind"] == "card_save"]
    assert row["changes"] == [{"key": "ai_cap_usd_per_day", "label": "Cap per day",
                               "kind": "usd", "old": 50.0, "new": 80.0}]
    assert row["fields"] == ["ai_cap_usd_per_day"] and row["actor"] and row["at_iso"]
    (e,) = H.installation_settings({"device": "", "since": None})["events"]
    assert e["kind"] == "setting" and e["devices"] == []
    assert e["what"] == "AI (hosted): Cap per day $50 → $80"
    assert e["who"].startswith(row["actor"]) and e["at"] == row["at_iso"]
    assert ("Changes", "Cap per day $50 → $80") in e["record"]
    # Through the History page, under its kind filter.
    page = networks["client"].get("/v2/history?kind=settings").get_data(as_text=True)
    assert "AI (hosted): Cap per day $50 → $80" in unescape(page)
    assert H.installation_settings({"device": "r1", "since": None})["events"] == [], (
        "the installation's, never one device's")


def test_a_row_recorded_before_values_were_kept_names_its_fields(networks):
    from modules import history_sources as H
    I._record({"kind": "card_save", "card": "netbox", "actor": "a@example.invalid",
               "actor_verified": "access", "fields": ["netbox_url"]})
    (e,) = H.installation_settings({"device": "", "since": None})["events"]
    assert e["what"] == "NetBox connection saved: netbox_url"


def test_an_unreadable_record_is_said_never_read_as_none(networks):
    from modules import history_sources as H
    (networks["dir"] / "settings_record.jsonl").write_text("{torn\n")
    out = H.installation_settings({"device": "", "since": None})
    assert out["events"] == [] and "settings record could not be read" in out["errors"][0]


# ---------------------------------------------------------------------------- a large increase

@pytest.mark.parametrize("old,new,large", [(1.5, 3.0, True), (1.5, 2.99, False),
                                           (100, 150, True), (100, 149.99, False),
                                           (80, 60, False), (None, 5000, False),
                                           (10, None, False)])
def test_large_is_double_or_50_more(old, new, large):
    assert I.is_large(old, new) is large


def test_a_large_increase_shows_its_implication_and_writes_nothing_until_confirmed(networks,
                                                                                  no_send):
    _set(networks, 10.0)
    r, html = _save(networks, "80")
    assert r.status_code == 200 and _cap() == 10.0 and _record(networks) == []
    assert ("A large increase: Cap per day $10 → $80. Up to $80 a day, about $2,400 a month "
            "at full use.") in _text(html)
    sent = _confirm_form(html)
    assert sent["confirm"] == "80.0" and sent["ai_cap_usd_per_day"] == "80.0"
    assert "Save $80 a day" in html and "Cancel" in html
    r, html = _post(networks, sent)
    assert r.status_code == 200 and _cap() == 80.0 and "Cap per day $10 → $80" in html


def test_a_confirm_for_another_amount_asks_again(networks, no_send):
    _set(networks, 10.0)
    r, html = _save(networks, "800", confirm="80")
    assert r.status_code == 200 and "Up to $800 a day, about $24,000 a month" in html
    assert _cap() == 10.0


def test_the_confirmation_keeps_what_the_card_drew(networks, no_send):
    """R17 still holds across the confirmation: another person's change meanwhile refuses the
    Save, naming both values."""
    _set(networks, 10.0)
    _r, html = _save(networks, "80")
    sent = _confirm_form(html)
    _set(networks, 20.0)
    r, html = _post(networks, sent)
    assert r.status_code == 409 and "it was '10.0' when you opened it and is '20.0' now" in html
    assert _cap() == 20.0


# ---------------------------------------------------------------------------- no cap

def test_no_cap_needs_its_words_typed_and_is_refused_without_them(networks, no_send):
    from modules.ai import controls
    r, html = _save(networks, "", no_cap="on")
    assert r.status_code == 200 and _cap() == 1.5 and _record(networks) == []
    words = _text(html)
    assert "No cap: Cap per day $1.50 → no cap" in words and "Type no cap to confirm" in words
    sent = _confirm_form(html)
    assert sent["no_cap"] == "on" and "confirm" not in sent
    for wrong in ("", "yes", "nocap"):
        r, html = _post(networks, dict(sent, no_cap_typed=wrong))
        assert r.status_code == 409 and _cap() == 1.5, wrong
        assert "no cap needs the words 'no cap' typed to confirm" in html
        assert "the cap stays $1.50" in html
    assert controls.cap_state() == {"day_cap": 1.5, "no_cap": False}
    r, html = _post(networks, dict(sent, no_cap_typed=" No  Cap "))
    assert r.status_code == 200 and "Cap per day $1.50 → no cap" in html
    stored = json.loads((networks["dir"] / "user_settings.json").read_text())
    assert "ai_cap_usd_per_day" in stored and stored["ai_cap_usd_per_day"] is None
    assert controls.cap_state() == {"day_cap": None, "no_cap": True}
    card = re.sub(r"\s+", " ", unescape(_page(networks)))
    assert ("No cap is set: Mercury does not stop AI spend; the provider's own limit is the "
            "backstop") in card
    assert re.search(r'name="no_cap" type="checkbox" value="on" checked', card)


def test_from_no_cap_a_cap_is_set_again_without_a_confirmation(networks, no_send):
    _set(networks, None)
    r, html = _save(networks, "5000")
    assert r.status_code == 200 and "Cap per day no cap → $5,000" in html and _cap() == 5000.0
    # No cap kept ticked with nothing else changed writes nothing.
    _set(networks, None)
    r, html = _save(networks, "", no_cap="on")
    assert r.status_code == 200 and "Nothing changed" in html


def test_an_empty_field_is_never_no_cap(networks, no_send):
    r, html = _save(networks, "")
    assert r.status_code == 409 and "is not a positive amount in US dollars" in html
    assert _cap() == 1.5


def test_with_no_cap_an_ai_control_is_ready_whatever_today_s_spend(monkeypatch):
    """The AI controls ask what the gateway asks (`controls.readiness`): no cap refuses
    nothing for the day's spend; the same spend under a cap draws the control disabled."""
    from modules.ai import controls, gateway
    monkeypatch.setattr(controls, "_hosted", lambda: {"allowed": True})
    monkeypatch.setattr(controls, "_key_set", lambda: True)

    def spent(day):
        return {"state": "ok", "usd": 1_000_000.0, "calls": 1}
    monkeypatch.setattr(gateway, "day_cap", lambda: None)
    got = controls.readiness("connection_check", today="2026-10-27", spent=spent)
    assert got["ready"] is True and got["per_day"] is None and got["kind"] == ""
    monkeypatch.setattr(gateway, "day_cap", lambda: 5000.0)
    got = controls.readiness("connection_check", today="2026-10-27", spent=spent)
    assert got["ready"] is False and got["kind"] == "day_cap"
    assert "is over the day cap $5000.0000" in got["reason"]


def test_cap_state_reads_the_gateway_s_day_cap(monkeypatch):
    from modules.ai import controls, gateway
    monkeypatch.setattr(gateway, "day_cap", lambda: 80.0)
    assert controls.cap_state() == {"day_cap": 80.0, "no_cap": False}
    monkeypatch.setattr(gateway, "day_cap", lambda: None)
    assert controls.cap_state() == {"day_cap": None, "no_cap": True}
