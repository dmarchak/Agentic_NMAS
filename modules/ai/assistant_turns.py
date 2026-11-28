"""The assistant's chat: a press of Send run as a job (the operator's order of 2026-11-28: "a
'thinking / running reads' indicator in the conversation, not a frozen box"; "Send turns into
Stop while it's working"), so no request waits on the model (a request held past about 100 s is
cut by the access tunnel, as AI troubleshooting's was before it became a job).

**One path** (`start`): the route has checked the question (`assistant.refusal`) and kept the
turn (`assistant_threads.begin`, one at a time per person); this starts the job
(`capture_job.start`, the verified identity carried into its thread, its work in the press's
request context so the gateway's person trigger is the press's) and returns at once. The job
runs `assistant.answer` with two hooks: *progress*, each step written to the turn
(`assistant_threads.step`) and announced (`STEP_KEYS`), so the open panel re-reads the turn and
draws its step; *stop_if*, the person's Stop as the turn's file holds it (any worker's), which
the gateway reads while it streams and `answer` reads before each call. Its end keeps the
exchange in the conversation (`assistant_threads.finish`) and is announced (`ANNOUNCE_KEYS`).

**The answer does not stream to the page.** The gateway streams each call from the provider,
but what it returns is the whole schema-bound answer (the answer's words, its citations, its
reads, its hand-off), checked by Mercury before anything is drawn (`assistant.check`): a part of
it is not an answer Mercury has checked. The panel draws progress steps instead (the operator's
own fallback); streaming the words would need the gateway changed, which this does not do.

**What Stop does** (the person's words on the control): the gateway closes the model's stream
at its next live check after the stop is read (it bills no further output from there; the
prompt and what streamed before are billed and recorded), and no call or read is made after it.
A round of reads already running finishes its reads. Every call made stays one recorded call in
History, and the stopped exchange is kept in the conversation with those calls' links.
"""
import logging
import time

log = logging.getLogger(__name__)

#: The job's kind, its announcer (`invalidation.ANNOUNCERS`), what its end announces (the AI
#: calls it made and the person's turn), and what each step announces.
KIND = "assistant answer"
ANNOUNCER = "assistant-turn"
ANNOUNCE_KEYS = ("ai_calls", "assistant")
STEP_KEYS = ("assistant",)


def _announce_step() -> None:
    from modules import invalidation
    try:
        invalidation.announce(STEP_KEYS, by=ANNOUNCER)
    except Exception as exc:                            # noqa: BLE001 (the step is still kept)
        log.info("assistant: a step's announcement was not sent: %s", exc)


def drawn_of(got: dict, question: str, place: dict) -> dict:
    """What the panel draws of `assistant.answer`'s result *got*: the route's own fields left
    out, the plan on the network asked from, the question masked and what it was looking at."""
    from modules import redact
    from modules.ai import assistant

    drawn = {k: v for k, v in got.items() if k not in ("ok", "gap", "error")}
    if drawn.get("plan"):
        # The plan acts on the network the person asked from: its preview is that network's.
        drawn["plan"] = dict(drawn["plan"], list=place.get("network") or "")
    drawn["question"] = redact.redact_typed(" ".join(question.split()))[:assistant.MAX_QUESTION]
    drawn["looking_at"] = place.get("label") or ""
    return drawn


def work(actor: str, turn: str, question: str, screen: str, place: dict):
    """The job's work: the answer, its gap recorded, the exchange kept. Returns the turn."""
    from modules.ai import assistant, assistant_threads, triggers

    started = time.monotonic()
    last = {"alive": time.time()}

    def progress(words):
        assistant_threads.step(actor, turn, words)
        last["alive"] = time.time()
        _announce_step()

    def stop_if():
        # Read while the call streams (the gateway's live checks), so the turn's sign of life
        # is written here too, at most every ALIVE_EVERY_S.
        if time.time() - last["alive"] >= assistant_threads.ALIVE_EVERY_S:
            last["alive"] = time.time()
            assistant_threads.alive(actor, turn)
        return assistant_threads.stop_asked(actor, turn)

    try:
        got = assistant.answer(question, screen=screen, place=place, actor=actor,
                               trigger=triggers.person(actor), progress=progress,
                               stop_if=stop_if)
    except Exception as exc:                            # noqa: BLE001 (kept, and said)
        log.exception("assistant: turn %s failed", turn)
        got = {"ok": False, "state": "refused", "error": "failed",
               "detail": f"Couldn't answer: {type(exc).__name__}: {exc}"[:300], "gap": False}
    if got.get("gap"):
        assistant.record_gap(question, screen=screen, state=got["state"], actor=actor,
                             call_id=got.get("call_id") or "")
    took = time.monotonic() - started
    assistant_threads.finish(actor, turn, drawn_of(got, question, place), took_s=took)
    return {"turn": turn, "state": got.get("state")}


def start(actor: str, turn: str, question: str, screen: str, place: dict) -> str:
    """Start *turn*'s job: its id, at once. Called inside the press's request (its context is
    carried into the job, as AI troubleshooting's press carries its own)."""
    from flask import copy_current_request_context

    from modules.nsot import capture_job

    def run(_job_id):
        return work(actor, turn, question, screen, place)

    return capture_job.start(place.get("network") or "", "An assistant answer", actor,
                             copy_current_request_context(run), kind=KIND,
                             announce_keys=ANNOUNCE_KEYS, announcer=ANNOUNCER)
