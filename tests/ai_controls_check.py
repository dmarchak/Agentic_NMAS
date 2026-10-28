"""One check for every AI control's screen (PHASE8_PLAN 15.13; modules/ai/controls.py). Not a
test module: each screen's own test file renders its control through the real route and calls
`check_screen`, so the check runs in that screen's own world (its fixtures), and
tests/test_ai_controls.py fails when a drawn control has no such call.

`check_screen(monkeypatch, get_html, name, parity)` draws the page through *get_html* in each
state and reads the control's markup:

- **ready** (hosted AI allowed, a key stored, today's spend plus the task's per-call cap within
  the day cap): the AI mark, its hover naming the task, its pinned model and its per-call cap;
  the button not disabled by AI and its input fillable; no reason drawn;
- **hosted AI off**, **no key**, **the provider's workspace usage limit held** (C2084),
  **the day cap reached** and **the record of AI calls unreadable**: the mark still drawn
  (never hidden), the button disabled with the state's kind, its input disabled, the reason
  drawn in place in that state's words (the limit's: "AI is unavailable: ...", its moment in
  the viewer's time with UTC's beside it), and the link to Settings › Installation, the AI
  (hosted) card, for a viewer who may configure; *parity* is called on each, the path beside
  it that needs no AI asserted usable. The AI card's Test is ready while the limit is held:
  it is how an admin tells Mercury the limit was raised;
- **off, for a viewer who may not configure**: the same, with no link.

The states are set at `modules.ai.controls`' own seams (`_hosted`, `_key_set`, `_limit`,
`_spent`): the
chain beneath them (the gateway's allowance, the secrets store's presence, the record's spend)
is tests/test_ai_controls.py's.
"""
import re
from html import unescape

#: Each drawn control's button and input in the page, as its template draws them.
MARKUP = {
    "ask_in_words": {"button": r'<button\b[^>]*\bdata-op="ask-in-words"[^>]*>',
                     "input": r'<input\b[^>]*\bid="lq-words"[^>]*>'},
    "explain": {"button": r'<button\b[^>]*\bdata-op="alert-evidence"[^>]*>', "input": None},
    "ai_card_test": {"button": r'<button\b[^>]*\bhx-post="[^"]*/installation/card/ai/test"[^>]*>',
                     "input": None},
    "intent_in_words": {"button": r'<button\b[^>]*\bdata-op="intent-in-words"[^>]*>',
                        "input": r'<input\b[^>]*\bid="iw-words"[^>]*>'},
    "sdn_classify": {"button": r'<button\b[^>]*\bid="sdn-classify-[^"]*"[^>]*>', "input": None},
}

#: Each state that cannot answer, and words its reason must hold.
NOT_READY = {
    "ai_off": "hosted AI is off",
    "no_key": "no Anthropic API key is set",
    # C2084: the provider's workspace usage limit, its moment in the viewer's time (drawn in the
    # browser from `datetime`) with UTC's beside it.
    "workspace_limit": ("AI is unavailable: the provider's workspace usage limit is reached, "
                        'until <time class="clock" datetime="2026-11-01T00:00:00Z" '
                        'data-clock="date" title="1 November 2026 00:00 UTC">1 November 2026 '
                        "00:00 UTC</time> (1 November 2026 00:00 UTC); an admin raises it in "
                        "the provider's console."),
    "day_cap": "is over the day cap",
    "unreadable": "the record of AI calls cannot be read",
}
#: How each state's reason begins: "Not available now:", but for the provider's limit, whose
#: words every AI screen shares (modules/ai/provider_limit.py).
LEADS = {"workspace_limit": "AI is unavailable:"}
#: The provider's workspace limit as `provider_limit.holding` answers while it holds: the
#: provider's real refusal of 2026-10-28.
HOLD = {"since": "2026-10-28T12:00:00Z", "until": "2026-11-01T00:00:00Z",
        "recheck_at": "2026-11-01T00:00:00Z", "status": 400, "call_id": "ai-planted",
        "feature": "explain",
        "said": ("invalid_request_error: You have reached your specified workspace API usage "
                 "limits. You will regain access on 2026-11-01 at 00:00 UTC.")}


def rechecks(name: str) -> bool:
    """Whether *name*'s task is one the provider's limit never disables: the AI card's Test,
    how an admin tells Mercury the limit was raised (`provider_limit.RECHECKS`)."""
    from modules.ai import controls, provider_limit

    return controls.CONTROLS[name]["task"] in provider_limit.RECHECKS

SETTINGS_LINK = 'href="/v2/settings/installation?tab=connections#card-ai"'


def set_state(m, state: str) -> None:
    """Put the controls' three questions in *state* ("ready" or a NOT_READY kind)."""
    from modules.ai import controls, gateway

    per_day = gateway.caps("connection_check")["per_day"]
    m.setattr(controls, "_hosted", lambda: {"allowed": state != "ai_off"})
    m.setattr(controls, "_key_set", lambda: state != "no_key")
    m.setattr(controls, "_limit", lambda: dict(HOLD) if state == "workspace_limit" else None)

    def spent(day):
        if state == "unreadable":
            return {"state": "unreadable", "usd": None, "calls": 0,
                    "error": "planted: the store did not answer"}
        return {"state": "ok", "usd": per_day if state == "day_cap" else 0.0, "calls": 0,
                "error": ""}
    m.setattr(controls, "_spent", spent)


def not_configuring(m) -> None:
    """The viewer is nobody verified, so may not configure."""
    from modules import identity
    nobody = identity.Identity(outcome="no_header", reason="no access assertion (planted)")
    m.setattr(identity, "identify", lambda _request: nobody)


def _tag(html: str, pattern: str, name: str, what: str) -> str:
    found = re.findall(pattern, html)
    assert len(found) == 1, f"{name}: {len(found)} {what}s drawn, wanted one"
    return found[0]


def _disabled(tag: str) -> bool:
    return re.search(r"\sdisabled(\s|>|=)", tag) is not None


def marks(html: str, name: str) -> list:
    """Each AI mark drawn for *name*, as (title, text)."""
    return [(unescape(t), x) for t, x in re.findall(
        r'<abbr class="ai-mark" title="([^"]*)" data-ai-control="' + re.escape(name)
        + r'">([^<]*)</abbr>', html)]


def assert_mark(html: str, name: str) -> None:
    from modules.ai import controls, profiles

    task = controls.CONTROLS[name]["task"]
    pin = profiles.TASKS[task]
    got = marks(html, name)
    assert len(got) == 1, f"{name}: {len(got)} AI marks drawn, wanted one"
    title, text = got[0]
    assert text == "AI", text
    assert pin["words"] in title, (pin["words"], title)
    assert profiles.MODELS[pin["model"]]["words"] in title and pin["model"] in title, title
    assert f"${profiles.cap_per_call(task):.4f}" in title, title


def reason(html: str, name: str) -> str:
    """The reason drawn for *name*, or "" when none is."""
    got = re.findall(r'<p class="ai-off" role="note" data-ai-off-reason="' + re.escape(name)
                     + r'">(.*?)</p>', html, re.S)
    assert len(got) <= 1, f"{name}: {len(got)} reasons drawn"
    return unescape(got[0]) if got else ""


def assert_ready(html: str, name: str) -> None:
    spec = MARKUP[name]
    assert_mark(html, name)
    button = _tag(html, spec["button"], name, "button")
    assert "data-ai-off" not in button and not _disabled(button), button
    if spec["input"]:
        box = _tag(html, spec["input"], name, "input")
        assert not _disabled(box), box
    assert reason(html, name) == "", "a ready control draws no reason"


def assert_not_ready(html: str, name: str, kind: str, admin: bool) -> None:
    spec = MARKUP[name]
    assert_mark(html, name)
    button = _tag(html, spec["button"], name, "button")
    assert _disabled(button) and f'data-ai-off="{kind}"' in button, button
    assert 'aria-disabled="true"' in button, button
    if spec["input"]:
        box = _tag(html, spec["input"], name, "input")
        assert _disabled(box), f"{name}: its input is fillable while {kind}: {box}"
    said = reason(html, name)
    lead = LEADS.get(kind, "Not available now:")
    assert said.count(lead) == 1 and NOT_READY[kind] in said, (kind, said)
    assert (SETTINGS_LINK in said) is admin, (admin, said)


#: A control a person could press or fill: the tags whose disabled state is compared.
CONTROL_TAG = re.compile(r"<(?:button|input|select|textarea)\b[^>]*>")


def disabled_elsewhere(html: str, name: str) -> list:
    """Every disabled control on the page but *name*'s own button and input."""
    spec = MARKUP[name]
    own = {t for p in (spec["button"], spec["input"]) if p for t in re.findall(p, html)}
    return sorted(t for t in CONTROL_TAG.findall(html) if t not in own and _disabled(t))


def check_screen(monkeypatch, get_html, name: str, parity) -> None:
    """The whole check for one drawn control (the module's docstring). Offline parity is
    checked twice: *parity* names the path beside the control that needs no AI, and nothing
    else on the page is disabled that was not disabled while hosted AI could answer."""
    with monkeypatch.context() as m:
        set_state(m, "ready")
        html = get_html()
        assert_ready(html, name)
        elsewhere = disabled_elsewhere(html, name)
    for kind in NOT_READY:
        with monkeypatch.context() as m:
            set_state(m, kind)
            html = get_html()
            if kind == "workspace_limit" and rechecks(name):
                # The AI card's Test asks the provider while its limit is held (C2084).
                assert_ready(html, name)
                assert disabled_elsewhere(html, name) == elsewhere, kind
                continue
            assert_not_ready(html, name, kind, admin=True)
            parity(html)
            assert disabled_elsewhere(html, name) == elsewhere, \
                f"{kind}: more than the AI control is disabled"
    with monkeypatch.context() as m:
        set_state(m, "ai_off")
        not_configuring(m)
        html = get_html()
        assert_not_ready(html, name, "ai_off", admin=False)
        parity(html)
