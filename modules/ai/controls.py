"""The AI controls: one registry, and whether each could answer now (PHASE8_PLAN 15.13;
NSOT_GUI_BRIEF section 6, "AI controls"; the operator, 2026-10-25).

**The rule.** Every control that needs AI carries one shared **AI** mark (the macro `mark` in
templates/v2/_ai.html), whose hover names the task, its pinned model and its per-call cap. When
hosted AI cannot answer (it is off, no key is set, or today's cap is reached), the control is
drawn disabled, its input not fillable, with the reason in place and, for a viewer who may
configure, a link to Settings › Installation, the AI (hosted) card. It is never hidden, and
never an error after the fact. The path beside it that needs no AI stays usable (the builder,
the evidence pack, the intent editor, the card's Save, Replace… and Allow).

**This module only reads.** `readiness` asks the same questions as the gateway, in the
gateway's order, before anything would be sent: is hosted AI allowed (`gateway.hosted_allowed`),
is a key set (presence only: `secrets_store.is_set`, which never decrypts; the key's value is
never read, returned or logged here), and do today's spend plus the task's per-call cap fit
the day cap (`calls.spent_usd`, `gateway.caps`). The gateway still decides every call itself
and refuses one that cannot be made; this draws the control so a person is not offered it.

**One registry.** `CONTROLS` names each AI control: its task (a `profiles.TASKS` pin), the
endpoints that reach the gateway when it is pressed, the template that draws it, and the path
beside it that needs no AI. `ALSO_REACHES` names an endpoint that reaches the gateway without
being an AI control of its own, with why. tests/test_ai_controls.py fails on a route that
reaches the gateway and is in neither, and on a template that posts to a registered endpoint
without the mark.
"""
import logging

from modules.ai import calls, gateway, profiles

log = logging.getLogger(__name__)

#: Each AI control: its task's pin, the endpoints its press reaches the gateway through, the
#: template that draws it (None while no screen draws it), the screen, and the path beside it
#: that needs no AI and stays usable when hosted AI cannot answer (offline parity).
CONTROLS = {
    "ask_in_words": {
        "task": "nl_query",
        "words": "Ask in words",
        "endpoints": ("v2.history_ask_metrics_words", "v2.history_ask_logs_words"),
        "template": "v2/_history_ask_words.html",
        "screen": "History › Query › Ask your own (metrics and logs)",
        "beside": "the builder: its choices and Ask",
    },
    "explain": {
        "task": "explain",
        "words": "Explain",
        "endpoints": ("v2.monitoring_alert_explain",),
        # Drawn in each pack's card (_evidence_pack.html includes it) and as Explain's own
        # answer, with the answer kept with the pack (C1853).
        "template": "v2/_explain_block.html",
        # A past alert with no pack yet draws it too, disabled beside Build evidence, its mark
        # and reason as ever (Monitoring › Alerts › History, C1808).
        "also": ("v2/_alert_history.html",),
        "screen": "Monitoring › Alerts, an alert's card",
        "beside": "the evidence pack",
    },
    "ai_card_test": {
        "task": "connection_check",
        "words": "Test (the AI card)",
        "endpoints": ("settings_v2.install_test",),
        "template": "v2/_install_card.html",
        "screen": "Settings › Installation › Connections, AI (hosted)",
        "beside": "the card's Save, Replace… and Allow",
    },
    "intent_in_words": {
        "task": "intent_patch",
        "words": "An intent change in words",
        "endpoints": ("intent_v2.words",),
        "template": "v2/_intent_words.html",
        "screen": "a device's Intent tab, Change it in words (board F7)",
        "beside": "the intent editor: Edit",
    },
    "sdn_classify": {
        "task": "sdn_classify",
        "words": "Classify (an SDN detection)",
        "endpoints": ("sdn_v2.response_classify",),
        "template": "v2/_sdn_responses.html",
        "screen": "SDN › Responses, a response awaiting a person",
        "beside": "the response's Preview, its hard timeout and Dismiss with this reason",
    },
}

#: Endpoints that reach the gateway without being an AI control of their own, each with why.
ALSO_REACHES = {
    "sdn_v2.loop_set": (
        "Start runs the SDN loop's job (PHASE8_PLAN 17.1 S10), whose classify step is a "
        "BACKGROUND call on each detection that fires (modules/sdn/loop.py), never a press: the "
        "gateway refuses it, records the refusal and sends nothing unless an admin turned the "
        "feature sdn_classify on for the network in Settings › AI, after its estimate, and it "
        "is within its caps (PHASE8_PLAN 18.3). Start and Stop themselves need no AI and stay "
        "usable; the person's own Classify is the sdn_classify control"),
    "settings_v2.install_replace": (
        "Replace… stores the AI card's key, then runs the card's Test "
        "(installation_settings.replace_secret, the irreversible tier); Replace… itself needs "
        "no AI and stays usable, since it is how a key is set. Its Test's refusal after the "
        "fact while hosted AI is off is C1678"),
}

#: Where a viewer who may configure fixes it: the AI (hosted) card.
CARD_ANCHOR = "card-ai"


def _hosted() -> dict:
    return gateway.hosted_allowed()


def _key_set() -> bool:
    """Whether the gateway's key is stored: presence only, never decrypted or read."""
    from modules.secrets_store import is_set
    return is_set("anthropic_api_key")


def _spent(day: str) -> dict:
    return calls.spent_usd(day)


def _today() -> str:
    # The gateway's day: its one home (calls.today, the stated boundary's midnight).
    return calls.today()


def mark_title(task: str) -> str:
    """The mark's hover: the task, its pinned model and its per-call cap."""
    pin = profiles.task(task)
    model = profiles.profile(pin["model"])
    return (f"AI: {pin['words']}. Pinned model: {model['words']} ({pin['model']}). "
            f"At most ${profiles.cap_per_call(task):.4f} a call.")


def readiness(task: str, today: str = None, spent=None) -> dict:
    """``{"ready", "kind", "reason", "task", "task_words", "model", "model_words",
    "per_call", "per_day", "title"}``: whether a call of *task* could be made now, and if
    not, why in words. *kind* is "" when ready, else "ai_off", "no_key", "unreadable" or
    "day_cap" (the gateway's order). *spent* reads a UTC day's spend (the record's, unless a
    caller shares one read). A task no pin names raises KeyError."""
    pin = profiles.task(task)
    model = profiles.profile(pin["model"])
    cap = gateway.caps(task)
    out = {"task": task, "task_words": pin["words"], "model": pin["model"],
           "model_words": model["words"], "per_call": cap["per_call"],
           "per_day": cap["per_day"], "title": mark_title(task), "ready": False,
           "kind": "", "reason": ""}
    if not _hosted().get("allowed"):
        return dict(out, kind="ai_off", reason="hosted AI is off: a person who may configure "
                    "allows it, with a recorded reason, on the AI (hosted) card")
    if not _key_set():
        return dict(out, kind="no_key", reason="no Anthropic API key is set: a person types "
                    "it on the AI (hosted) card")
    spent = (spent or _spent)(today or _today())
    if spent.get("state") == "unreadable":
        return dict(out, kind="unreadable", reason="the record of AI calls cannot be read "
                    f"({spent.get('error') or 'no reason given'}), so today's spend is unknown")
    usd = float(spent.get("usd") or 0.0)
    if cap["per_day"] is not None and usd + cap["per_call"] > cap["per_day"]:
        # When the day starts again is drawn by the reason's macro from `resets` (calls'
        # one answer), in the viewer's time and in UTC.
        return dict(out, kind="day_cap", spent=usd, resets=calls.reset_info(),
                    reason=f"today's AI spend ${usd:.4f} plus this task's per-call cap "
                           f"${cap['per_call']:.4f} is over the day cap ${cap['per_day']:.4f}")
    return dict(out, ready=True, spent=usd)


def cap_state() -> dict:
    """``{"day_cap": <US dollars> | None, "no_cap": bool}``: the installation's day cap as the
    gateway reads it (`gateway.day_cap`, its one home). ``no_cap`` is True while an admin has
    chosen no cap (the key stored as null): the one answer the toolbar's spend chip reads to
    say "no cap" for as long as it is set (the operator, 2026-10-27; the chip is not built
    yet, and its label lands with it)."""
    per_day = gateway.day_cap()
    return {"day_cap": per_day, "no_cap": per_day is None}


def _may_configure() -> bool:
    """Whether the viewer may configure: the gate `configure` asks, for the viewer drawn."""
    from modules import identity
    try:
        return bool(identity.may(identity.viewer(), "configure")[0])
    except Exception as exc:                                    # noqa: BLE001
        log.warning("ai controls: could not ask whether the viewer may configure (%s)",
                    type(exc).__name__)
        return False


def control(name: str) -> dict:
    """One registered control as a template draws it (the Jinja global `ai_control`): its
    registry entry, its task's readiness, whether the viewer may configure, and the AI card's
    address. Asked once per request and control (the spend is read once per request)."""
    from flask import g, has_request_context, url_for

    entry = CONTROLS[name]
    in_request = has_request_context()
    once = None
    if in_request:
        cache = g.setdefault("nmas_ai_controls", {})
        if name in cache:
            return cache[name]
        days = g.setdefault("nmas_ai_spent", {})

        def once(day):
            if day not in days:
                days[day] = _spent(day)
            return days[day]
    out = dict(entry, name=name, **readiness(entry["task"], spent=once))
    out["may_configure"] = _may_configure() if in_request else False
    out["settings_url"] = (url_for("settings_v2.installation", tab="connections")
                           + "#" + CARD_ANCHOR) if in_request else ""
    if in_request:
        cache[name] = out
    return out
