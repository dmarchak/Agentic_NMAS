"""How to fix it is never blank once the AI answered with no plan (the operator, 2026-11-15,
C3797: "It declines only when the reads available to it can't settle the question; then it
names the read it lacked (missing capability) and "How to fix it" shows the best next step as
a button, never blank"; `modules/fixit/section.py` `lacked_read`, `_contract`'s next action,
`templates/v2/_fixit_section.html`).

- **A lacked read** (the answer's ``shown["lacked_read"]``, kept on its proposal line): the fix
  is a button, "Run <read> in Show commands", opening Show commands on the incident's device
  with the command in its first row (nothing is read until a person presses Run there), and
  Ask the AI again beside it, not the primary. Past the cap the read is still offered (it costs
  no AI call), and Ask the AI again is not.
- **No lacked read** (or one a person's Show commands would refuse, or none named): Ask the AI
  again while it is offered, else Hand over…; never nothing.

Through tests/test_fixit_troubleshoot.py's world (the real app, records and page), the answer
written by the troubleshooting record's own writer (`incident.record_proposal`). No device, no
network, no AI call.
"""
import re
from html import unescape

from modules.ai import calls
from modules.fixit import incident as F
from modules.fixit import section as S
from tests.test_fixit_section_v2 import (DEV, bluf_of, outside_modals, primaries_of,
                                         section_of, setting)
from tests.test_fixit_section_v2 import NET, web  # noqa: F401 (the fixture `ai` builds on)
from tests.test_fixit_troubleshoot import ai, incident, page, stopped  # noqa: F401
# Past the cap: a cap under the least one AI call costs (7b0bb884: the cap compares the least
# call, $0.0576, so the old $0.10 no longer refuses the AI).
from tests.test_fixit_troubleshoot import UNDER_THE_LEAST
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

#: A read Mercury's allowlist holds whole but the AI's families do not (C3797's shape).
LACKED = "show tcp brief all"
CALL = "ai-0000000000000b01"


def _answered(iid: str, **shown) -> None:
    """The AI's answer with no plan, on a call about this incident, its *shown* kept."""
    calls.record({"id": CALL, "feature": "fixit_troubleshoot", "verdict": "ok",
                  "prompt": "fixit_troubleshoot.v10", "cost_usd": 0.03,
                  "subject": {"kind": "heal_incident", "id": iid, "devices": [DEV["hostname"]]}})
    F.record_proposal(incident(iid), "ai", words="The AI named no fix: the reads it holds "
                      "cannot say whether the collector still holds the old session.",
                      calls=[CALL], prompt="fixit_troubleshoot.v10",
                      shown=dict({"rationale": "The collector's side was not read.",
                                  "hypotheses": []}, **shown))


def _fix(iid: str) -> dict:
    from modules import incident_page
    return S.view(NET, incident_page.resolve(NET, iid))["bluf"]["fix"]


def _fix_line(html: str) -> str:
    """The BLUF's How to fix it line, outside its modals. Premise corrected (board R5,
    becced07: the card's next action is its `<div data-bluf="fix">`, the press's answer under
    it and the card's Details after, where it was a `<dd>`): the line ends where the answer's
    space begins, so Details (its feedback form among it) is not read as the line."""
    line = bluf_of(section_of(html)).split('data-bluf="fix"', 1)[1]
    return outside_modals(line.split('<div class="bluf-answer"', 1)[0])


def _controls(line: str) -> list:
    return [" ".join(re.sub(r"<[^>]+>", " ", w).split())
            for _t, a, w in re.findall(r"<(a|button)\b([^>]*)>(.*?)</\1>", line, re.S)
            if "how-btn" not in a and "data-help" not in a]


def test_a_lacked_read_is_the_fix_a_show_commands_button_with_its_command(ai):  # noqa: F811
    iid = stopped(ai)
    _answered(iid, lacked_read=LACKED)
    fix = _fix(iid)
    host = DEV["hostname"]
    assert fix == {"kind": "button", "label": f"Run {LACKED} in Show commands",
                   "href": S.show_commands_href(NET, host, LACKED), "read": LACKED}, fix
    _r, html = page(ai.client, iid)
    line = _fix_line(html)
    (prim,) = primaries_of(line)
    assert prim[1] == f"Run {LACKED} in Show commands", prim
    href = unescape(re.search(r'href="([^"]+)"', prim[0]).group(1))
    assert href == fix["href"]
    controls = _controls(line)
    assert "Ask the AI again Asking the AI…" in controls, controls
    assert "Ask the AI again" not in " ".join(w for _a, w in primaries_of(line))
    # The button opens Show commands on the incident's device with the read in its first row.
    r = ai.client.get(href)
    body = r.get_data(as_text=True)
    assert r.status_code == 200, body[:300]
    assert f'name="command" class="mono sc-input" value="{LACKED}"' in body
    assert re.search(rf'<input[^>]*name="q"[^>]*value="{host}"', body), "the device's filter"


def test_past_the_cap_a_lacked_read_is_still_offered_and_ask_again_is_not(ai):  # noqa: F811
    iid = stopped(ai)
    _answered(iid, lacked_read=LACKED)
    setting(ai_cap_usd_per_incident=UNDER_THE_LEAST)
    assert _fix(iid)["read"] == LACKED
    _r, html = page(ai.client, iid)
    controls = _controls(_fix_line(html))
    assert controls[0] == f"Run {LACKED} in Show commands", controls
    assert not [c for c in controls if c.startswith("Ask the AI again")], controls


def test_no_lacked_read_asks_the_ai_again(ai):  # noqa: F811
    iid = stopped(ai)
    _answered(iid)
    fix = _fix(iid)
    assert fix["kind"] == "button" and fix["label"] == "Ask the AI again", fix
    _r, html = page(ai.client, iid)
    assert [w for _a, w in primaries_of(_fix_line(html))] == ["Ask the AI again Asking the AI…"]


def test_a_read_show_commands_would_refuse_is_no_button(ai):  # noqa: F811
    iid = stopped(ai)
    _answered(iid, lacked_read="show running-config | redirect flash:x")
    fix = _fix(iid)
    assert fix["label"] == "Ask the AI again" and "read" not in fix, fix


def test_with_neither_a_plan_nor_ask_again_the_fix_is_hand_over_never_blank(ai):  # noqa: F811
    iid = stopped(ai)
    _answered(iid, lacked_read="")
    setting(ai_cap_usd_per_incident=UNDER_THE_LEAST)
    fix = _fix(iid)
    assert fix["kind"] == "hand_over" and fix["label"] == "Hand over", fix
    _r, html = page(ai.client, iid)
    line = _fix_line(html)
    assert "Nothing to press" not in line and "No action is offered" not in line
    assert [w for _a, w in primaries_of(line)] == ["Hand over…"], _controls(line)
