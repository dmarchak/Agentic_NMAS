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
    for words in ("Self-healing on Default", "Change mode…", "History of this policy",
                  "Fix kinds", "Change fix kinds…", "Hard stops and guards", "Who is told",
                  "Stop self-healing everywhere…", "Production's bar", "Policy fingerprint",
                  "Network stage", "A rolled-back heal", "4 never"):
        assert words in tab, words
    # Ten, as the board draws them: section 6's eight and the amendment's flap and bounce rows
    # (19.4, H19).
    assert tab.count(">Edit…</a>") == 10
    assert "A flap: transitions of one interface within" in tab and "3 in 10 min" in tab
    assert "no bounce is built yet: H20" in tab
    # Off by default: nothing heals, so no Turn off; the defaults heal nothing.
    assert ">Turn off<" not in tab and "never confirmed: the defaults are in force" in tab
    for kind in H.TIER1_KINDS + H.TIER2_KINDS:
        assert f'value="{kind}"' not in tab           # the kinds are changed in the change card
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
    r, html = _get(networks, base + "/change?part=mode")
    assert r.status_code == 200 and "Change self-healing on Default" in html
    assert 'name="heal_mode" value="auto" disabled' in html          # Default is not lab
    assert "Auto is turned on only on a network marked lab" in html
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
                                    "reason": "my reason, kept"})
    assert r.status_code == 409, tab
    assert "Not saved:" in tab and "moved since the preview" in tab
    assert "Change self-healing on Default" in tab and "my reason, kept" in tab
    assert H.current("Default")["set"] == "off"


def test_auto_on_a_lab_network_takes_the_expiry_as_people_write_it(networks):
    _mark_lab()
    base = BASE.format(n="Default")
    _r, html = _get(networks, base + "/change?part=mode")
    assert 'name="heal_mode" value="auto" disabled' not in html
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


def test_the_fix_kinds_and_a_hard_stop_are_changed_the_same_way(networks):
    base = BASE.format(n="Default")
    _r, card = _get(networks, base + "/change?part=kinds")
    assert "Change the fix kinds on Default" in card
    assert 'name="heal_kinds_propose" value="qos_policy" checked' in card
    r, tab = _preview_and_confirm(networks, "Default", {
        "part": "kinds", "heal_kinds_auto": [""],
        "heal_kinds_propose": ["", "process_reset", "secret_added_back"]})
    assert r.status_code == 200, tab
    assert H.current("Default")["kinds_propose"] == ["process_reset", "secret_added_back"]
    _r, card = _get(networks, base + "/change?part=heal_max_per_network_hour")
    assert "Change “Heals per network per hour” on Default" in card
    r, tab = _preview_and_confirm(networks, "Default", {"part": "heal_max_per_network_hour",
                                                        "heal_max_per_network_hour": "4"})
    assert r.status_code == 200, tab
    assert H.current("Default")["guards"]["heal_max_per_network_hour"]["value"] == 4
    r, _html = _get(networks, base + "/change?part=nonsense")
    assert r.status_code == 404


def test_a_kind_in_both_lists_is_drawn_once_at_its_networks_tier(networks):
    """The BGP session clear is Auto only on a network marked lab and proposed elsewhere
    (`actions.tier_of`), so it is in both policy lists; Fix kinds draws it once, at the tier
    its network gives it, and the change card carries its other list's setting unchanged
    (the operator's overnight item 9, 2026-11-12: it was listed twice)."""
    words = "BGP session clear: one named neighbour"

    def kinds_card(network):
        tab = networks["client"].get(f"/v2/settings/network/{network}?tab=heal")
        fix = tab.get_data(as_text=True).split('id="h-heal-kinds"', 1)[1].split("</table>")[0]
        _r, card = _get(networks, BASE.format(n=network) + "/change?part=kinds")
        return fix, card.split('id="h-heal-change"', 1)[1].split("</form>")[0]

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

