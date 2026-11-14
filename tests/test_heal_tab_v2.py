"""The Self-healing tab (board H, artboard A; part H9; docs/HEAL_TO_INTENT.md sections 5 to 7,
9 and 10), through the real app, its routes (routes/heal_v2.py), its templates and
modules/heal/policy.py, on a temporary store of four networks. No device, no network.

- **The tab is drawn** under the strict policy, beside Integrations and Network, with every
  control the board draws: Change mode…, Turn off, History of this policy, Change fix kinds…,
  an Edit… per hard stop, Who is told's Save and Stop self-healing everywhere….
- **A change is previewed in place and confirmed by hash:** a choice draws What this changes and
  the confirm naming its work, writing nothing; the confirm, as htmx sends it, saves and draws
  the tab with its answer; a confirm after the policy moved is refused in the change card,
  what was typed kept. AUTO is drawn disabled on a network not marked lab, and on a lab
  network its expiry is typed as people write a time ("2026-11-20 18:00 UTC").
- **The fix kinds and a hard stop** are changed the same way.
- **Turn off** is one press; **Who is told** names a team and its events, refused when the team
  does not exist or another person changed it since the card drew it.
- **The kill switch:** Stop asks why and stops every network; the tab then says so on every
  network with Resume…, previewed, and confirmed with a reason.
"""

import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from modules import heal_notify
from modules.heal import policy as H
from modules.sdn import modes as MD
from tests.test_sdn_connections import make_networks

HX = {"HX-Request": "true"}


@pytest.fixture
def networks(tmp_path, monkeypatch):
    """Default, Branch and Lab-3 under *tmp_path* (tests/test_sdn_connections.py's store),
    and the real app's client."""
    import app as A

    make_networks(tmp_path, monkeypatch)
    return {"client": A.app.test_client(), "dir": tmp_path}
BASE = "/v2/settings/network/{n}/heal"


def _get(n, path):
    r = n["client"].get(path, headers=HX)
    return r, r.get_data(as_text=True)


def _post(n, path, data=None):
    r = n["client"].post(path, data=data or {}, headers=HX)
    return r, r.get_data(as_text=True)


def _hidden(html, name):
    m = re.search(rf'<input type="hidden" name="{name}" value=(["\'])(.*?)\1>', html, re.S)
    assert m, f"no hidden {name}"
    import html as h
    return h.unescape(m.group(2))


def _mark_lab(network="Default"):
    MD.set_stage(network, "lab", actor="admin@example.com", actor_verified="access",
                 reason="the course lab's network")


def _until(hours=24):
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(time.time() + hours * 3600))


def modal_of(html, mid):
    """The body of the modal *mid* the tab draws (`_heal_change.html`), or None."""
    m = re.search(rf'<dialog class="modal[^"]*" id="{re.escape(mid)}"[^>]*>(.*?)</dialog>',
                  html, re.S)
    return m.group(1) if m else None


def dialog_tag(html, mid):
    m = re.search(rf'<dialog class="modal[^"]*" id="{re.escape(mid)}"[^>]*>', html)
    return m.group(0) if m else ""


def outside_modals(html):
    """The tab without its modals: what a person sees before pressing anything."""
    return re.sub(r"<dialog\b.*?</dialog>", "", html, flags=re.S)


def _preview_and_confirm(n, network, data, reason="Lab 10's walk"):
    base = BASE.format(n=network)
    r, html = _post(n, base + "/preview", data)
    assert r.status_code == 200, html
    fp, seen = _hidden(html, "fingerprint"), _hidden(html, "seen")
    return _post(n, base, dict(data, fingerprint=fp, seen=seen, reason=reason))


# ── The tab ───────────────────────────────────────────────────────────────────────────────

def test_the_tab_draws_every_control_the_board_draws(networks):
    from modules import csp

    r = networks["client"].get("/v2/settings/network/Default?tab=heal")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
    assert 'aria-current="page">Self-healing</a>' in html
    assert "Self-healing is each network's own: no network inherits it." in html
    tab = html.split('id="heal-tab"', 1)[1]
    for words in ("Self-healing on Default", "History of this policy",
                  "Fix kinds", "Change fix kinds…", "Hard stops and guards", "Who is told",
                  "Stop self-healing everywhere…", "Production's bar", "Policy fingerprint",
                  "Network stage", "A rolled-back heal", "4 never"):
        assert words in tab, words
    # Premise corrected (C3158, the operator's rule of 2026-11-12: "The mode is a dropdown
    # (Off / Dry run / Auto) opening the same modal"): Change mode… is the mode's dropdown.
    assert '<select id="heal-mode-pick" data-modal-select' in tab
    # Ten, as the board draws them: section 6's eight and the amendment's flap and bounce rows
    # (19.4, H19); each a button opening its modal (C3158: never a card in the right column).
    assert outside_modals(tab).count(">Edit…</button>") == 10
    assert "A flap: transitions of one interface within" in tab and "3 in 10 min" in tab
    # Premise corrected (2026-11-13): the port bounce is built (H20, `actions.NOT_BUILT` empty),
    # so the row names what a second need becomes and never says it is unbuilt.
    assert "a second need within the repeat window is a dampening proposal for a person" in tab
    assert "no bounce is built" not in tab
    # Off by default: nothing heals, so no Turn off; the defaults heal nothing.
    assert ">Turn off<" not in tab and "never confirmed: the defaults are in force" in tab
    for kind in H.TIER1_KINDS + H.TIER2_KINDS:
        # The kinds are changed in their modals, never by a field drawn on the tab itself.
        assert f'value="{kind}"' not in outside_modals(tab), kind
    # Pressed: Change mode…'s confirm puts dry run in force, and the tab drawn again offers
    # Turn off, which one press then takes back to off.
    r, again = _preview_and_confirm(networks, "Default", {"part": "mode", "heal_mode": "dry_run"})
    assert r.status_code == 200 and H.current("Default")["mode"] == "dry_run"
    assert ">Turn off<" in again
    r, _off = _post(networks, BASE.format(n="Default") + "/off")
    assert r.status_code == 200 and H.current("Default")["set"] == "off"


def test_another_networks_tab_is_its_own(networks):
    """A policy confirmed on Default leaves Branch's tab at the defaults (never inherited)."""
    r, html = _preview_and_confirm(networks, "Default", {"part": "mode", "heal_mode": "dry_run"})
    assert r.status_code == 200, html
    _r, branch = _get(networks, BASE.format(n="Branch") + "/tab")
    assert "Self-healing on Branch" in branch and "never confirmed" in branch


# ── A change: preview in place, confirm by hash ────────────────────────────────────────────

def test_change_mode_previews_in_place_then_confirms_and_records(networks):
    base = BASE.format(n="Default")
    r, html = _get(networks, base + "/tab")
    # C3158: the dropdown's Dry run names its modal, which holds the mode as a hidden field
    # (nothing left to choose) and previews as it opens; Off, in force, opens nothing.
    assert r.status_code == 200
    pick = re.search(r'<select id="heal-mode-pick".*?</select>', html, re.S).group(0)
    assert '<option value="off" selected>Off</option>' in pick
    assert '<option value="dry_run" data-modal-choice="heal-mode-dry_run">Dry run</option>' in pick
    # Default is not lab: Auto is offered disabled, saying why, and has no modal.
    assert re.search(r'<option value="auto" disabled title="[^"]*marked lab[^"]*">Auto '
                     r'\(a network marked lab only\)</option>', pick), pick
    assert modal_of(html, "heal-mode-auto") is None and modal_of(html, "heal-mode-off") is None
    dry = modal_of(html, "heal-mode-dry_run")
    assert '<h3 class="modal-h" id="heal-mode-dry_run-h">Set Default to dry run</h3>' in dry
    assert '<input type="hidden" name="heal_mode" value="dry_run">' in dry
    assert 'hx-trigger="change, nmas:modal-open from:closest dialog"' in dry
    assert re.search(r"<button[^>]*data-modal-close[^>]*>Cancel</button>", dry)
    r, pv = _post(networks, base + "/preview", {"part": "mode", "heal_mode": "dry_run"})
    assert r.status_code == 200 and "What this changes" in pv
    assert "Set Default to dry run" in pv and "Dry run</strong>" in pv
    assert H.current("Default")["set"] == "off"                       # the preview wrote nothing
    fp, seen = _hidden(pv, "fingerprint"), _hidden(pv, "seen")
    r, tab = _post(networks, base, {"part": "mode", "heal_mode": "dry_run", "fingerprint": fp,
                                    "seen": seen, "reason": "dry run every kind first"})
    assert r.status_code == 200, tab
    assert "Confirmed:" in tab and "is dry run" in tab
    assert "settings" in r.headers["X-NMAS-Invalidates"]
    cur = H.current("Default")
    assert cur["mode"] == "dry_run" and cur["confirmed"]["reason"] == "dry run every kind first"
    assert ">Turn off<" in tab and "“dry run every kind first”" in tab
    # History of this policy lists the record just written.
    assert "confirmed dry_run" in tab.split('id="heal-history"', 1)[1]


def test_a_confirm_after_the_policy_moved_is_refused_in_the_card_keeping_what_was_typed(
        networks):
    base = BASE.format(n="Default")
    _r, pv = _post(networks, base + "/preview", {"part": "mode", "heal_mode": "dry_run"})
    fp = _hidden(pv, "fingerprint")
    # Another person changes a hard stop meanwhile.
    p = H.plan("Default", {"heal_max_per_network_hour": 4})
    H.apply("Default", {"heal_max_per_network_hour": 4}, p["fingerprint"], reason="other",
            actor="other@example.com", actor_verified="access", person=True)
    r, tab = _post(networks, base, {"part": "mode", "heal_mode": "dry_run", "fingerprint": fp,
                                    "reason": "my reason, kept", "modal": "heal-mode-dry_run"})
    assert r.status_code == 409, tab
    # C3158: the tab drawn again with the change's own modal marked to open again, the
    # refusal and what was typed inside it, and nothing said at the tab's head.
    assert "data-modal-reopen" in dialog_tag(tab, "heal-mode-dry_run"), tab
    body = modal_of(tab, "heal-mode-dry_run")
    assert "Not saved:" in body and "moved since the preview" in body
    assert "my reason, kept" in body
    assert "Not saved:" not in outside_modals(tab) and tab.count("data-modal-reopen") == 1
    assert H.current("Default")["set"] == "off"


def test_a_refused_confirm_whose_modal_is_no_longer_offered_is_said_at_the_tabs_head(
        networks):
    """Another person put the same mode in force meanwhile: the dropdown no longer offers it,
    so no modal opens again, and the refusal is said at the tab's head instead."""
    base = BASE.format(n="Default")
    _r, pv = _post(networks, base + "/preview", {"part": "mode", "heal_mode": "dry_run"})
    fp = _hidden(pv, "fingerprint")
    p = H.plan("Default", {"heal_mode": "dry_run"})
    H.apply("Default", {"heal_mode": "dry_run"}, p["fingerprint"], reason="other",
            actor="other@example.com", actor_verified="access", person=True)
    r, tab = _post(networks, base, {"part": "mode", "heal_mode": "dry_run", "fingerprint": fp,
                                    "reason": "mine", "modal": "heal-mode-dry_run"})
    assert r.status_code == 409 and "data-modal-reopen" not in tab
    assert "Not done:" in outside_modals(tab)


def test_auto_on_a_lab_network_takes_the_expiry_as_people_write_it(networks):
    """H1's callers outside the tab still send the expiry as people write a UTC time."""
    _mark_lab()
    base = BASE.format(n="Default")
    _r, html = _get(networks, base + "/tab")
    assert 'data-modal-choice="heal-mode-auto">Auto</option>' in html
    p = H.plan("Default", {"heal_kinds_auto": ["added_line"]})
    H.apply("Default", {"heal_kinds_auto": ["added_line"]}, p["fingerprint"], reason="kinds",
            actor="admin@example.com", actor_verified="access", person=True)
    until = _until(48)
    data = {"part": "mode", "heal_mode": "auto", "heal_mode_until": until}
    _r, pv = _post(networks, base + "/preview", data)
    assert "Turn on Auto for Default until " in pv and "Not confirmable" not in pv
    r, tab = _preview_and_confirm(networks, "Default", data)
    assert r.status_code == 200, tab
    assert H.current("Default")["mode"] == "auto"
    # Eight days away is refused in the preview, naming the limit.
    _r, far = _post(networks, base + "/preview", dict(data, heal_mode_until=_until(8 * 24)))
    assert "at most 7 days" in far


RAW_INSTANT = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")


def _words(html):
    """What a person reads: the tags gone, and with them every attribute (a hover, a
    machine-readable ``datetime=``, a hidden field's value)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_autos_expiry_is_drawn_in_the_viewers_zone_never_as_the_stored_instant(networks):
    """C3158 (the review, 2026-11-13: the confirm read "…until 2026-11-18T11:49:00Z"): the
    preview's confirm button, its summary and its gate draw Auto's expiry through the one
    clock, in the viewer's zone, its UTC on the hover; and the tab the confirm answers with
    (drawn whole inside `times`, C3290) says it the same way in its Confirmed notice, its
    Mode row and its policy history."""
    from tests.test_local_times import kept_zone

    _mark_lab()
    base = BASE.format(n="Default")
    p = H.plan("Default", {"heal_kinds_auto": ["added_line"]})
    H.apply("Default", {"heal_kinds_auto": ["added_line"]}, p["fingerprint"], reason="kinds",
            actor="admin@example.com", actor_verified="access", person=True)
    at = time.time() + 48 * 3600
    at -= at % 60
    kept = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at))
    data = {"part": "mode", "heal_mode": "auto",
            "heal_mode_until": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(at))}
    clock = f'<time class="clock" datetime="{kept}" data-clock="date"'
    with kept_zone("Asia/Kolkata"):
        local = datetime.fromtimestamp(at, ZoneInfo("Asia/Kolkata"))
        said = f"until {local.strftime('%b')} {local.day} {local.strftime('%H:%M')}"
        _r, pv = _post(networks, base + "/preview", data)
        button = re.search(r'<span class="op-idle">(Turn on Auto.*?)</span>\s*<span class="op-busy"',
                           pv, re.S).group(1)
        assert clock in button and said in _words(button), button
        # The preview's own sentences too (its summary, through `times`). Its program, one
        # level down, lists each stored value as it will be stored, the instant among them:
        # a program is quoted, never reworded.
        program = re.compile(r'<ol class="set-steps mono small">.*?</ol>', re.S)
        assert f"heal_mode_until: none -&gt; {kept}" in "".join(program.findall(pv))
        assert f"AUTO {said}" in _words(pv)
        assert not RAW_INSTANT.search(_words(program.sub("", pv))), _words(pv)
        r, tab = _preview_and_confirm(networks, "Default", data)
        assert r.status_code == 200 and H.current("Default")["until"] == kept
        # The Confirmed notice, the Mode row and the policy history's line, each a clock.
        assert tab.count(clock) >= 3, tab.count(clock)
        words = _words(tab)
        assert f"self-healing is Auto {said}" in words, words
        assert f"at the expiry ( {said[len('until '):]}" in words, words
        assert f"confirmed auto {said}" in words, words
        assert not RAW_INSTANT.search(words), RAW_INSTANT.findall(words)


def test_the_fix_kinds_and_a_hard_stop_are_changed_the_same_way(networks):
    base = BASE.format(n="Default")
    _r, tab = _get(networks, base + "/tab")
    card = modal_of(tab, "heal-kinds")
    assert "Change the fix kinds on Default" in card
    assert 'name="heal_kinds_propose" value="qos_policy" checked' in card
    assert ('data-modal-open="heal-kinds" aria-haspopup="dialog" aria-controls="heal-kinds"'
            in outside_modals(tab))
    r, tab = _preview_and_confirm(networks, "Default", {
        "part": "kinds", "heal_kinds_auto": [""],
        "heal_kinds_propose": ["", "process_reset", "secret_added_back"]})
    assert r.status_code == 200, tab
    assert H.current("Default")["kinds_propose"] == ["process_reset", "secret_added_back"]
    card = modal_of(tab, "heal-guard-heal_max_per_network_hour")
    assert "Change “Heals per network per hour” on Default" in card
    assert 'name="heal_max_per_network_hour"' in card
    r, tab = _preview_and_confirm(networks, "Default", {"part": "heal_max_per_network_hour",
                                                        "heal_max_per_network_hour": "4"})
    assert r.status_code == 200, tab
    assert H.current("Default")["guards"]["heal_max_per_network_hour"]["value"] == 4
    # A part that is not one is refused naming the parts there are.
    from modules import heal_page
    with pytest.raises(H.PolicyRefused, match="'nonsense' is not a part of the heal policy"):
        heal_page.change("Default", "nonsense")


def test_a_kind_in_both_lists_is_drawn_once_at_its_networks_tier(networks):
    """The BGP session clear is Auto only on a network marked lab and proposed elsewhere
    (`actions.tier_of`), so it is in both policy lists; Fix kinds draws it once, at the tier
    its network gives it, and the change card carries its other list's setting unchanged
    (the operator's overnight item 9, 2026-11-12: it was listed twice)."""
    words = "BGP session clear: one named neighbour"

    def kinds_card(network):
        tab = networks["client"].get(f"/v2/settings/network/{network}?tab=heal")
        html = tab.get_data(as_text=True)
        fix = html.split('id="h-heal-kinds"', 1)[1].split("</table>")[0]
        return fix, modal_of(html, "heal-kinds").split("</form>")[0]

    fix, card = kinds_card("Branch")
    assert fix.count(words) == 1 and card.count(words) == 1
    row = fix.split(words, 1)[1].split("</tr>")[0]
    assert "2 propose" in row and "Alert only" in row
    assert 'name="heal_kinds_propose" value="session_clear"' in card
    assert 'name="heal_kinds_auto" value="session_clear"' not in card
    # Marked lab, it is Tier 1, and its proposal setting rides in the card as it was.
    p = H.plan("Default", {"heal_kinds_propose": ["qos_policy", "session_clear"]})
    H.apply("Default", {"heal_kinds_propose": ["qos_policy", "session_clear"]},
            p["fingerprint"], reason="kinds", actor="admin@example.com",
            actor_verified="access", person=True)
    _mark_lab()
    fix, card = kinds_card("Default")
    assert fix.count(words) == 1 and card.count(words) == 1
    row = fix.split(words, 1)[1].split("</tr>")[0]
    assert "1 auto" in row and "Dry run only" in row
    assert '<input type="checkbox" name="heal_kinds_auto" value="session_clear">' in card
    assert '<input type="hidden" name="heal_kinds_propose" value="session_clear">' in card
    r, _tab = _preview_and_confirm(networks, "Default", {
        "part": "kinds", "heal_kinds_auto": ["", "session_clear"],
        "heal_kinds_propose": ["", "qos_policy", "session_clear"]})
    assert r.status_code == 200
    assert H.current("Default")["kinds_auto"] == ["session_clear"]
    assert H.current("Default")["kinds_propose"] == ["qos_policy", "session_clear"]


def test_turn_off_is_one_press(networks):
    _preview_and_confirm(networks, "Default", {"part": "mode", "heal_mode": "dry_run"})
    r, tab = _post(networks, BASE.format(n="Default") + "/off")
    assert r.status_code == 200 and "Turned off" in tab
    assert H.current("Default")["set"] == "off" and ">Turn off<" not in tab


# ── Who is told ───────────────────────────────────────────────────────────────────────────

def test_who_is_told_names_a_team_and_its_events_and_refuses_a_stale_card(networks):
    from modules.notify import teams

    team = teams.add_team("Default on-call", by="alex")["team"]
    teams.add_email(team, "noc@example.com", by="alex")
    _r, tab = _get(networks, BASE.format(n="Default") + "/tab")
    loaded = _hidden(tab, "loaded")
    assert f'<option value="{team}">Default on-call</option>' in tab
    r, tab = _post(networks, BASE.format(n="Default") + "/notify",
                   {"team": team, "events": ["cant_fix", "halted"], "loaded": loaded})
    assert r.status_code == 200 and "Saved:" in tab and "1 address, 0 webhooks" in tab
    assert heal_notify.teams_for("Default", "held") == [team]
    assert heal_notify.teams_for("Default", "healed") == []
    assert heal_notify.teams_for("Branch", "cant_fix") == []          # its own, never inherited
    r, tab = _post(networks, BASE.format(n="Default") + "/notify",
                   {"team": "", "events": [], "loaded": loaded})       # drawn before the save
    assert r.status_code == 409 and "another person changed Who is told" in tab
    r, tab = _post(networks, BASE.format(n="Default") + "/notify",
                   {"team": "0123456789ab", "events": [],
                    "loaded": _hidden(tab, "loaded")})
    assert r.status_code == 409 and "no team &#39;0123456789ab&#39;" in tab
    assert heal_notify.teams_for("Default", "cant_fix") == [team]


# ── The kill switch ───────────────────────────────────────────────────────────────────────

def test_stop_everywhere_then_resume_with_a_reason(networks):
    r, tab = _get(networks, "/v2/settings/installation/heal/stop/ask?list_name=Branch")
    assert r.status_code == 200 and "Stop self-healing everywhere?" in tab
    r, tab = _post(networks, "/v2/settings/installation/heal/stop?list_name=Branch",
                   {"why": "drill"})
    assert r.status_code == 200 and "Stopped everywhere" in tab and H.stopped()["stopped"]
    assert "Self-healing on Branch" in tab
    _r, other = _get(networks, BASE.format(n="Lab-3") + "/tab")
    assert "Self-healing is stopped everywhere." in other and "Resume self-healing…" in other
    r, pv = _post(networks, "/v2/settings/installation/heal/resume/preview?list_name=Lab-3")
    assert r.status_code == 200 and "Resume self-healing everywhere" in pv
    fp = _hidden(pv, "fingerprint")
    r, tab = _post(networks, "/v2/settings/installation/heal/resume?list_name=Lab-3",
                   {"fingerprint": fp, "reason": ""})
    assert r.status_code == 409 and "reason" in tab and H.stopped()["stopped"]
    r, tab = _post(networks, "/v2/settings/installation/heal/resume?list_name=Lab-3",
                   {"fingerprint": fp, "reason": "drill over"})
    assert r.status_code == 200 and "Self-healing resumed everywhere" in tab
    assert not H.stopped()["stopped"]


def test_a_request_that_is_not_htmx_is_answered_in_json(networks):
    """H1's callers outside the tab: the preview and the confirm answer JSON, and the confirm
    puts the change in force."""
    r = networks["client"].post(BASE.format(n="Default") + "/preview",
                                data={"heal_mode": "dry_run"})
    body = r.get_json()
    assert r.status_code == 200 and body["confirmable"]
    assert H.current("Default")["set"] == "off"                       # the preview wrote nothing
    r = networks["client"].post(BASE.format(n="Default"),
                                data={"heal_mode": "dry_run", "fingerprint": body["fingerprint"],
                                      "seen": json.dumps(body["operands"]), "reason": "Lab 10"})
    assert r.status_code == 200 and r.get_json()["mode"] == "dry_run"
    assert H.current("Default")["mode"] == "dry_run"


@pytest.mark.parametrize("typed, kept", [("2026-11-20 18:00 UTC", "2026-11-20T18:00:00Z"),
                                         ("2026-11-20 18:00", "2026-11-20T18:00:00Z"),
                                         ("2026-11-20T18:00:00Z", "2026-11-20T18:00:00Z"),
                                         ("next tuesday", "next tuesday")])
def test_autos_expiry_as_typed(typed, kept):
    from modules import heal_page
    assert heal_page.parse_until(typed) == kept


# ── C3158: the toggles are the control, every change a modal, Auto until local ─────────────

def test_each_kinds_toggle_is_a_button_opening_its_own_modal_with_that_kind_flipped(networks):
    """The operator's rule (2026-11-12, C3158): "the Fix kinds table's Heal / Dry run only
    toggle IS the control; pressing it opens that modal (what this changes, reason, Confirm)".
    Each Tier 1 and Tier 2 kind's row draws the setting in force as a pressed button that does
    nothing (disabled, "In force now") and the other as a button opening the kind's own modal,
    whose form carries the policy's lists with that one kind flipped and previews as it
    opens; its preview and confirm, as htmx sends them, put the flip in force."""
    base = BASE.format(n="Default")
    _r, tab = _get(networks, base + "/tab")
    fix = outside_modals(tab).split('id="h-heal-kinds"', 1)[1].split("</table>")[0]
    assert "<span class=\"seg-btn" not in fix                 # no span drawn as a control
    rows = 0
    for kind in dict.fromkeys(H.TIER1_KINDS + H.TIER2_KINDS):   # the session clear in both
        mid = f"heal-kind-{kind}"
        opener = re.search(rf'<button type="button" class="seg-btn" aria-pressed="false" '
                           rf'data-modal-open="{mid}" aria-haspopup="dialog" '
                           rf'aria-controls="{mid}"[^>]*>([^<]+)</button>', fix)
        assert opener, kind
        rows += 1
        assert modal_of(tab, mid) is not None, mid
    assert rows >= 12, rows
    assert fix.count('aria-pressed="true" disabled title="In force now"') == rows
    # Missing line: Dry run only now (the defaults heal nothing); its toggle's Heal opens it.
    body = modal_of(tab, "heal-kind-missing_line")
    assert "Missing line: Heal on Default" in body
    assert "Now: Dry run only. After you confirm: <strong>Heal</strong>" in body
    assert 'hx-trigger="change, nmas:modal-open from:closest dialog"' in body
    sent = re.findall(r'<input type="hidden" name="(heal_kinds_(?:auto|propose))" '
                      r'value="([a-z_]*)">', body)
    assert ("heal_kinds_auto", "missing_line") in sent
    data = {"part": "kinds", "modal": "heal-kind-missing_line",
            "heal_kinds_auto": [v for k, v in sent if k == "heal_kinds_auto"],
            "heal_kinds_propose": [v for k, v in sent if k == "heal_kinds_propose"]}
    _r, pv = _post(networks, base + "/preview", data)
    assert "Save the fix kinds for Default" in pv and "missing_line" in pv
    r, tab = _preview_and_confirm(networks, "Default", data)
    assert r.status_code == 200 and H.current("Default")["kinds_auto"] == ["missing_line"]
    # Drawn again, Missing line's Heal is the one pressed, and Dry run only opens the flip back.
    fix = outside_modals(tab).split('id="h-heal-kinds"', 1)[1].split("</table>")[0]
    row = fix.split("Missing line: re-apply", 1)[1].split("</tr>")[0]
    assert '<button type="button" class="seg-btn on" aria-pressed="true" disabled title="In ' \
           'force now">Heal</button>' in row
    assert "Now: Heal. After you confirm: <strong>Dry run only</strong>" in \
        modal_of(tab, "heal-kind-missing_line")


def test_a_refused_toggle_opens_its_own_modal_again_keeping_the_reason(networks):
    base = BASE.format(n="Default")
    r, tab = _post(networks, base, {"part": "kinds", "modal": "heal-kind-missing_line",
                                    "heal_kinds_auto": ["", "missing_line"],
                                    "heal_kinds_propose": ["", "qos_policy"],
                                    "fingerprint": "0" * 16, "reason": "kept for the retry"})
    assert r.status_code == 409
    assert "data-modal-reopen" in dialog_tag(tab, "heal-kind-missing_line")
    body = modal_of(tab, "heal-kind-missing_line")
    assert "Not saved:" in body and "kept for the retry" in body
    assert H.current("Default")["kinds_auto"] == []


def _lab_with_a_kind():
    _mark_lab()
    p = H.plan("Default", {"heal_kinds_auto": ["added_line"]})
    H.apply("Default", {"heal_kinds_auto": ["added_line"]}, p["fingerprint"], reason="kinds",
            actor="admin@example.com", actor_verified="access", person=True)


def test_auto_until_is_quick_choices_and_a_picker_in_the_viewers_zone(networks):
    """The operator's rule (2026-11-12, C3158): ""Auto until" is never a typed UTC string:
    quick choices (1 h, 2 h, 4 h, 8 h, 24 h, 7 days) plus a date-time picker in local time,
    showing the UTC beside it". Auto's modal draws the six as radios beside a picker in the
    viewer's kept zone, named, and no typed UTC field."""
    from tests.test_local_times import kept_zone

    _lab_with_a_kind()
    with kept_zone("Asia/Kolkata"):
        _r, tab = _get(networks, BASE.format(n="Default") + "/tab")
    body = modal_of(tab, "heal-mode-auto")
    assert body is not None and "Turn on Auto for Default" in body
    assert re.findall(r'<input type="radio" name="heal_mode_for" value="(\d+)" '
                      r'data-quick-of="heal-until-local">\s*([^<]+?)</label>', body) == [
        ("1", "1 h"), ("2", "2 h"), ("4", "4 h"), ("8", "8 h"), ("24", "24 h"),
        ("168", "7 days")]
    assert ('<input type="datetime-local" id="heal-until-local" name="heal_mode_until_local" '
            'value="" step="60"') in body
    assert "Or a time, Asia/Kolkata" in body
    assert 'name="heal_mode_until"' not in body and "UTC</span>" not in body
    assert "its UTC is drawn here once a time is chosen" in body
    # Nothing left to choose is not true of Auto: it previews only once a time is chosen.
    assert "nmas:modal-open" not in body
    # Pressed as drawn (its hidden fields, the 24 h choice, the picker empty), previewed and
    # confirmed with the picker the preview drew: Auto is in force for 24 hours.
    form = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)">', body))
    data = dict(form, heal_mode_until_local="", heal_mode_for="24")
    base = BASE.format(n="Default")
    with kept_zone("Asia/Kolkata"):
        before = time.time()
        _r, pv = _post(networks, base + "/preview", data)
        picker = re.search(r'<span hidden data-quick-for="heal-until-local" '
                           r'data-quick-time="([^"]+)"></span>', pv).group(1)
        r, _tab = _post(networks, base, dict(data, heal_mode_until_local=picker,
                                             fingerprint=_hidden(pv, "fingerprint"),
                                             seen=_hidden(pv, "seen"), reason="24 h"))
    assert r.status_code == 200 and H.current("Default")["mode"] == "auto"
    until = H.parse_until(H.current("Default")["until"])
    assert before + 24 * 3600 - 60 <= until <= time.time() + 24 * 3600, until - before


def test_the_picker_is_read_in_the_viewers_zone_converted_once_and_said_beside_it(networks):
    """A time put in the picker is the viewer's own (Asia/Kolkata, UTC+05:30): the preview
    draws its UTC beside the picker (out of band) and the confirm in the viewer's time naming
    the zone; the policy keeps the one UTC instant the server converted."""
    from tests.test_local_times import kept_zone

    _lab_with_a_kind()
    base = BASE.format(n="Default")
    at = time.time() + 30 * 3600
    at -= at % 60
    kept = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at))
    local = datetime.fromtimestamp(at, ZoneInfo("Asia/Kolkata"))
    data = {"part": "mode", "heal_mode": "auto", "modal": "heal-mode-auto",
            "heal_mode_until_local": local.strftime("%Y-%m-%dT%H:%M")}
    with kept_zone("Asia/Kolkata"):
        _r, pv = _post(networks, base + "/preview", data)
        utc = re.search(r'<output class="set-origin heal-until-utc" id="heal-until-utc" '
                        r'for="heal-until-local" aria-live="polite" hx-swap-oob="true">'
                        r'([^<]*)</output>', pv)
        assert utc and utc.group(1) == time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(at))
        assert "data-quick-time" not in pv                # the picker the person set is left
        button = re.search(r'<span class="op-idle">(Turn on Auto.*?)</span>\s*'
                           r'<span class="op-busy"', pv, re.S).group(1)
        said = f"{local.strftime('%b')} {local.day} {local.strftime('%H:%M')}"
        assert f"until {said}" in _words(button) and button.endswith("(Asia/Kolkata)"), button
        r, _tab = _preview_and_confirm(networks, "Default", data)
    assert r.status_code == 200 and H.current("Default")["until"] == kept


def test_a_quick_choice_is_resolved_once_drawn_into_the_picker_and_confirmed_as_previewed(
        networks):
    """A quick choice is hours from the preview: the preview resolves it once (to the minute
    below), hands that time to the picker in the viewer's zone (`data-quick-time`, which the
    page puts in the picker), and the confirm, which sends the picker beside the still-chosen
    quick choice, keeps exactly the instant previewed, however long after the preview it is
    pressed."""
    from tests.test_local_times import kept_zone

    _lab_with_a_kind()
    base = BASE.format(n="Default")
    data = {"part": "mode", "heal_mode": "auto", "modal": "heal-mode-auto",
            "heal_mode_until_local": "", "heal_mode_for": "4"}
    with kept_zone("America/Denver"):
        before = time.time()
        _r, pv = _post(networks, base + "/preview", data)
        picker = re.search(r'<span hidden data-quick-for="heal-until-local" '
                           r'data-quick-time="([^"]*)"></span>', pv)
        assert picker, pv
        at = datetime.strptime(picker.group(1), "%Y-%m-%dT%H:%M").replace(
            tzinfo=ZoneInfo("America/Denver")).timestamp()
        assert at % 60 == 0 and before + 4 * 3600 - 60 < at <= time.time() + 4 * 3600
        fp, seen = _hidden(pv, "fingerprint"), _hidden(pv, "seen")
        r, _tab = _post(networks, base, dict(data, heal_mode_until_local=picker.group(1),
                                             fingerprint=fp, seen=seen, reason="4 h"))
    assert r.status_code == 200, _tab
    assert H.current("Default")["until"] == time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                         time.gmtime(at))
    # Seven days is the longest choice and is never past the policy's limit.
    _r, week = _post(networks, base + "/preview", dict(data, heal_mode_for="168"))
    assert "Turn on Auto for Default until" in week and "Not confirmable" not in week
    # No time chosen at all is no expiry, refused naming it.
    _r, none = _post(networks, base + "/preview", dict(data, heal_mode_for=""))
    assert "none was given" in none


def test_the_conversions_one_each_way():
    from modules import heal_page

    denver, kolkata = ZoneInfo("America/Denver"), ZoneInfo("Asia/Kolkata")
    # A picker's time is the viewer's: MST (UTC−7) in November, MDT (UTC−6) in July.
    assert heal_page.parse_until_local("2026-11-18T04:49", denver) == "2026-11-18T11:49:00Z"
    assert heal_page.parse_until_local("2026-07-18T04:49", denver) == "2026-07-18T10:49:00Z"
    assert heal_page.parse_until_local("2026-11-18T04:49", kolkata) == "2026-11-17T23:19:00Z"
    assert heal_page.parse_until_local("tomorrow", denver) == "tomorrow"   # the policy names it
    # And back into the picker, the same minute.
    assert heal_page.local_value("2026-11-18T11:49:00Z", denver) == "2026-11-18T04:49"
    assert heal_page.local_value("not a time", denver) == ""
    # A quick choice: hours from now, to the minute below; anything else is sent on as it is.
    now = 1_800_000_000 + 59
    assert heal_page.until_in("4", now) == time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(1_800_000_000 + 4 * 3600))
    assert heal_page.until_in("3", now) == "3" and heal_page.until_in("x", now) == "x"


# ── In a real browser: the toggle, the dropdown and Auto until, pressed ───────────────────────

ENTER, ESCAPE, DOWN = "", "", ""


def _keys(b, *keys):
    """Real key presses to whatever has the focus (WebDriver's actions), one after another."""
    acts = []
    for k in keys:
        acts += [{"type": "keyDown", "value": k}, {"type": "keyUp", "value": k}]
    b._call("POST", f"/session/{b.session}/actions",
            {"actions": [{"type": "key", "id": "keyboard", "actions": acts}]})


#: Where a modal is and where its opener is, and what has the focus (the modal's own rule,
#: `_modal.html`: placed by its opener, below it or else above it, its left edge at the
#: opener's, inside the window's 16 px gutters).
PLACE = ("var d = document.getElementById(arguments[0]), o = arguments[1] ?"
         " document.querySelector(arguments[1]) : null;"
         "var r = d.getBoundingClientRect(), a = o ? o.getBoundingClientRect() : null;"
         "return {open: d.open, top: r.top, bottom: r.bottom, left: r.left, width: r.width,"
         " height: r.height, at: a && {top: a.top, bottom: a.bottom, left: a.left},"
         " vw: document.documentElement.clientWidth, vh: window.innerHeight,"
         " inside: d.contains(document.activeElement),"
         " focus: document.activeElement === o};")


def _settled(b, mid):
    """The modal's place once its preview has been drawn and the page has placed it again."""
    b.wait_for("var r = document.getElementById(arguments[0]).getBoundingClientRect();"
               " return r.bottom <= window.innerHeight - 15 || r.top <= 17", 10.0, mid)


def _anchored(p):
    """The modal sits by its opener as the rule says, measured here, not by the page's own
    placing function: left at the opener's (kept inside the gutters), and just below the
    opener, or just above it when below has no room."""
    g, gap = 16, 6
    left = max(g, min(p["at"]["left"], p["vw"] - g - p["width"]))
    below_fits = p["at"]["bottom"] + gap + p["height"] <= p["vh"] - g
    above_fits = p["at"]["top"] - gap - p["height"] >= g
    assert abs(p["left"] - left) <= 1, p
    if below_fits:
        assert abs(p["top"] - (p["at"]["bottom"] + gap)) <= 1, p
    elif above_fits:
        assert abs(p["bottom"] - (p["at"]["top"] - gap)) <= 1, p
    else:                                     # neither: as low as it fits, its foot in view
        assert abs(p["top"] - max(g, p["vh"] - g - p["height"])) <= 1, p
    assert p["bottom"] <= p["vh"] - g + 1 or p["top"] <= g + 1, p


def test_in_a_real_browser_the_toggle_and_the_dropdown_open_their_modal_anchored_to_them(
        networks):
    """In Firefox (skipped naming why where none runs): a fix kind's toggle, pressed from the
    keyboard, opens its modal anchored to it with the focus inside and its preview drawn;
    Escape closes it and gives the toggle the focus back. The mode dropdown, moved by its
    arrow key, opens Dry run's modal anchored to it; Cancel closes it, the dropdown back on
    Off. On a network marked lab, Auto's 4 h quick choice draws its time into the picker in
    the viewer's zone with the UTC beside it, and the confirm names that time and zone; an
    empty reason's refusal opens the modal again with the focus on the refusal; with a reason
    the confirm puts Auto in force until exactly the time drawn."""
    from tests import browser
    from tests.test_local_times import kept_zone

    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tab's own checks above still run")
    import app as APP

    page = "/v2/settings/network/Default?tab=heal"
    toggle = '#heal-kinds button[data-modal-open="heal-kind-missing_line"]'
    with kept_zone("Asia/Kolkata"), browser.Served(APP.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 900})
            b.go(srv.url(page))
            b.wait_for("return !!document.getElementById('heal-tab')")
            # The toggle: a real button, reached and pressed from the keyboard.
            assert b.js(f"var t = document.querySelector('{toggle}');"
                        " return !!t && t.tagName === 'BUTTON' && t.tabIndex === 0"), toggle
            b.js(f"var t = document.querySelector('{toggle}'); t.scrollIntoView({{block: 'center'}});"
                 " t.focus(); return 1")
            assert b.js(f"return document.activeElement === document.querySelector('{toggle}')")
            _keys(b, ENTER)
            b.wait_for("return document.getElementById('heal-kind-missing_line').open")
            b.wait_for("return !!document.querySelector("
                       "'#heal-kind-missing_line-preview .heal-changes')")
            _settled(b, "heal-kind-missing_line")
            opened = b.js(PLACE, "heal-kind-missing_line", toggle)
            assert opened["inside"], opened
            _anchored(opened)
            words = b.js("return document.getElementById('heal-kind-missing_line').innerText")
            assert "Save the fix kinds for Default" in words and "Reason" in words, words
            _keys(b, ESCAPE)
            b.wait_for("return !document.getElementById('heal-kind-missing_line').open")
            assert b.js(PLACE, "heal-kind-missing_line", toggle)["focus"]
            # The dropdown, moved from the keyboard: Dry run's modal, then Cancel.
            b.js("var s = document.getElementById('heal-mode-pick');"
                 " s.scrollIntoView({block: 'center'}); s.focus(); return 1")
            _keys(b, DOWN)
            b.wait_for("return document.getElementById('heal-mode-dry_run').open")
            b.wait_for("return !!document.querySelector('#heal-mode-dry_run-preview .heal-changes')")
            _settled(b, "heal-mode-dry_run")
            dry = b.js(PLACE, "heal-mode-dry_run", "#heal-mode-pick")
            assert dry["inside"], dry
            _anchored(dry)
            b.click("#heal-mode-dry_run [data-modal-close]")
            b.wait_for("return !document.getElementById('heal-mode-dry_run').open")
            back = b.js("var s = document.getElementById('heal-mode-pick');"
                        " return {value: s.value, focus: document.activeElement === s}")
            assert back == {"value": "off", "focus": True}, back
            assert H.current("Default")["set"] == "off"
            # Auto, on a network marked lab: the 4 h quick choice, then the confirm.
            _lab_with_a_kind()
            b.go(srv.url(page))
            b.wait_for("return !!document.querySelector("
                       "'#heal-mode-pick option[data-modal-choice=\"heal-mode-auto\"]')")
            b.js("var s = document.getElementById('heal-mode-pick'); s.value = 'auto';"
                 " s.dispatchEvent(new Event('change', {bubbles: true})); return 1")
            b.wait_for("return document.getElementById('heal-mode-auto').open")
            _anchored(b.js(PLACE, "heal-mode-auto", "#heal-mode-pick"))
            b.click('#heal-mode-auto input[name="heal_mode_for"][value="8"]')
            b.wait_for("return document.getElementById('heal-until-local').value !== '' &&"
                       " /UTC$/.test(document.getElementById('heal-until-utc').textContent)")
            first = b.js("return document.getElementById('heal-until-local').value")
            # Then 4 h: the quick choice chosen last is the answer, the picker's 8 h time
            # emptied before the form is sent and the 4 h one drawn into it.
            b.click('#heal-mode-auto input[name="heal_mode_for"][value="4"]')
            b.wait_for("return document.getElementById('heal-until-local').value !== '' &&"
                       " document.getElementById('heal-until-local').value !== arguments[0]",
                       10.0, first)
            b.wait_for("return !!document.querySelector('#heal-mode-auto-preview .op-idle')"
                       " && /until/.test(document.querySelector("
                       "'#heal-mode-auto-preview .op-idle').textContent)")
            drawn = b.js("return {local: document.getElementById('heal-until-local').value,"
                         " utc: document.getElementById('heal-until-utc').textContent,"
                         " button: document.querySelector('#heal-mode-auto-preview .op-idle')"
                         ".textContent, quick: document.querySelector("
                         "'#heal-mode-auto input[name=heal_mode_for][value=\"4\"]').checked}")
            local = datetime.strptime(drawn["local"], "%Y-%m-%dT%H:%M").replace(
                tzinfo=ZoneInfo("Asia/Kolkata"))
            eight = datetime.strptime(first, "%Y-%m-%dT%H:%M").replace(
                tzinfo=ZoneInfo("Asia/Kolkata"))
            assert 4 * 3600 - 120 <= (eight - local).total_seconds() <= 4 * 3600 + 120, \
                (first, drawn)
            assert drawn["utc"] == local.astimezone(ZoneInfo("UTC")).strftime(
                "%Y-%m-%d %H:%M:%S UTC"), drawn
            said = f"{local.strftime('%b')} {local.day} {local.strftime('%H:%M')}"
            assert drawn["button"] == f"Turn on Auto for Default until {said} (Asia/Kolkata)", \
                drawn
            assert drawn["quick"], drawn
            # Confirmed with no reason: refused, the modal opened again, the focus on why.
            _settled(b, "heal-mode-auto")
            b.click("#heal-mode-auto-preview button.btn-primary")
            b.wait_for("var d = document.getElementById('heal-mode-auto');"
                       " return d && d.open && !!d.querySelector('.set-result')")
            again = b.js("var d = document.getElementById('heal-mode-auto');"
                         " return {said: d.querySelector('.set-result').innerText,"
                         " focus: document.activeElement === d.querySelector('.set-result'),"
                         " local: document.getElementById('heal-until-local').value}")
            assert "Not saved:" in again["said"] and again["focus"], again
            assert again["local"] == drawn["local"], again
            assert H.current("Default")["set"] == "off"
            b.wait_for("return !!document.querySelector('#heal-mode-auto-preview .op-idle')")
            b.type("#heal-mode-auto textarea[name=reason]", "Lab 10's walk")
            _settled(b, "heal-mode-auto")
            b.click("#heal-mode-auto-preview button.btn-primary")
            b.wait_for("return !document.getElementById('heal-mode-auto') ||"
                       " !document.getElementById('heal-mode-auto').open")
            b.wait_for("var s = document.querySelector('#heal-mode .set-result');"
                       " return !!s && document.activeElement === s")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert H.current("Default")["mode"] == "auto"
    assert H.current("Default")["until"] == local.astimezone(ZoneInfo("UTC")).strftime(
        "%Y-%m-%dT%H:%M:%SZ")

