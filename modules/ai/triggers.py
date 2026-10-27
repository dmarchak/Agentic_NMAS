"""Every AI call names its trigger (PHASE8_PLAN 18.3 rules 1 and 5; CLAUDE.md, "AI cost safety";
C1843).

A call reaches the gateway for one of three reasons, and says which; the gateway refuses a
call that names none before it reads or sends anything, and records the trigger it was given
on the call's row (`ai_calls`), so spend is attributed by what started it, never guessed from
an actor's spelling:

- **person** ``{"kind": "person", "by": <actor>}``: a person's press. The route passes the
  request's verified actor (`identity.request_actor()`). The gateway refuses one outside a
  request (a script or a job never spends under a person's name), and one whose ``by`` is not
  the request's verified actor; the row records how the person was established
  (`identity.actor_verification`: ``access`` in a verified request).
- **evaluation** ``{"kind": "evaluation", "run": <run id>}``: an evaluation script's run, its
  actor ``evaluation:<run id>`` (`cases.evaluation_actor`), counted against the caps under its
  run (rule 9).
- **background** ``{"kind": "background", "feature", "job", "network", "finding": {"kind",
  "id"}}``: a job's call for a background feature (`background.FEATURES`), its actor
  ``job:<job id>``. It names the FINDING deterministic code made that caused it (rule 5: a
  detection's id, an incident's id, the day for a digest), of a kind its feature declares; one
  without is refused. Whether its feature is on for its network, and within its caps, is
  `background`'s question, asked by the gateway after this one.

`check` is the gateway's question; the constructors are what callers use.
"""
import re

PERSON, EVALUATION, BACKGROUND = "person", "evaluation", "background"
KINDS = (PERSON, EVALUATION, BACKGROUND)
#: A background call's actor: the job's id after this.
JOB_PREFIX = "job:"
#: A job's id: the shape `cases.evaluation_actor` takes for a run, so an id is never a sentence
#: or a path.
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
#: A finding's id may be a little longer (an incident's or a detection's key).
_FINDING_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$")

#: The refusal's words when no trigger is named: what each kind is.
NONE_WORDS = ("names no trigger: every AI call says what started it, a person's press "
              "(person), an evaluation run (evaluation) or a background job on a finding "
              "(background); nothing was read or sent")


def person(actor: str) -> dict:
    """A person's press, as *actor* (the request's verified actor)."""
    return {"kind": PERSON, "by": actor}


def evaluation(actor: str) -> dict:
    """An evaluation run, from its actor ``evaluation:<run id>`` (`cases.evaluation_actor`'s
    answer); any other actor gives a trigger `check` refuses."""
    from modules.ai import cases

    actor = actor or ""
    run = actor[len(cases.EVALUATION):] if actor.startswith(cases.EVALUATION) else ""
    return {"kind": EVALUATION, "run": run}


def background(feature: str, job: str, network: str, finding_kind: str,
               finding_id: str) -> dict:
    """A background job's call for *feature* on *network* (a list's name or folder name; kept
    as its folder name), caused by the finding (*finding_kind*, *finding_id*)."""
    from modules.config import list_slug

    return {"kind": BACKGROUND, "feature": feature, "job": job,
            "network": list_slug(network) if network else "",
            "finding": {"kind": finding_kind, "id": finding_id}}


def actor_of(trigger: dict) -> str:
    """The actor a call with *trigger* records: the person, ``evaluation:<run>`` or
    ``job:<job>``."""
    from modules.ai import cases

    kind = trigger.get("kind")
    if kind == PERSON:
        return str(trigger.get("by") or "")
    if kind == EVALUATION:
        return f"{cases.EVALUATION}{trigger.get('run') or ''}"
    return f"{JOB_PREFIX}{trigger.get('job') or ''}"


def _refused(why: str) -> dict:
    return {"ok": False, "why": why, "trigger": None}


def _person(trigger: dict) -> dict:
    from modules import identity
    from modules.ai import cases

    by = trigger.get("by")
    if (not isinstance(by, str) or not by.strip() or by == identity.UNVERIFIED
            or by.startswith((cases.EVALUATION, JOB_PREFIX))):
        return _refused(f"a person trigger names a verified person; {by!r} is not one "
                        "(an evaluation or a job names its own kind)")
    from flask import has_request_context

    # Only a request a person's access assertion verified spends under a person's name (the
    # parent's decision, 2026-10-27): a script is an evaluation, a job is a background call.
    if not has_request_context():
        return _refused(f"a person trigger ({by!r}) outside a request: only a request that "
                        "verified its person spends under a person's name; a script names an "
                        "evaluation run, a job a background feature")
    verified = identity.request_actor()
    if by != verified:
        return _refused(f"the person trigger names {by!r}, and this request's verified "
                        f"actor is {verified!r}")
    return {"ok": True, "why": "", "trigger": {"kind": PERSON, "by": by,
                                                "verified": identity.actor_verification(by)}}


def _evaluation(trigger: dict) -> dict:
    from modules.ai import cases

    # The run's shape is the evaluation scripts' own (`cases.evaluation_actor`), one owner.
    run = trigger.get("run")
    if not isinstance(run, str) or not cases._RUN.match(cases.EVALUATION + run):
        return _refused(f"an evaluation trigger names its run (letters, digits and . _ : -, at "
                        f"most 80); {run!r} is not one")
    return {"ok": True, "why": "", "trigger": {"kind": EVALUATION, "run": run}}


def _background(trigger: dict, task: str) -> dict:
    from modules.ai import background as B
    from modules.config import list_slug

    name = trigger.get("feature")
    spec = B.FEATURES.get(name) if isinstance(name, str) else None
    if spec is None:
        return _refused(f"{name!r} is not a background feature Mercury knows; known: "
                        f"{', '.join(sorted(B.FEATURES)) or 'none'}")
    if spec["task"] != task:
        return _refused(f"the background feature {name} calls the task {spec['task']}, not "
                        f"{task}")
    job, network = trigger.get("job"), trigger.get("network")
    if not isinstance(job, str) or not _ID.match(job):
        return _refused(f"a background trigger names its job's id; {job!r} is not one")
    if not isinstance(network, str) or not network or list_slug(network) != network:
        return _refused(f"a background trigger names its network by its folder name; "
                        f"{network!r} is not one")
    finding = trigger.get("finding")
    kind = finding.get("kind") if isinstance(finding, dict) else None
    ident = finding.get("id") if isinstance(finding, dict) else None
    if kind not in spec["findings"] or not isinstance(ident, str) \
            or not _FINDING_ID.match(ident):
        return _refused(f"{name} calls the model only on a finding deterministic code made "
                        f"({' or '.join(spec['findings'])}, with its id); this trigger names "
                        f"{finding!r}")
    return {"ok": True, "why": "", "trigger": {
        "kind": BACKGROUND, "feature": name, "job": job, "network": network,
        "finding": {"kind": kind, "id": ident}}}


def check(trigger, actor: str, task: str) -> dict:
    """``{"ok", "why", "trigger"}``: whether a call of *task* as *actor* names a trigger the
    gateway takes, and the trigger its row records (with how a person was established).
    Refused, *why* names what was compared: a kind not one of `KINDS`, a field out of shape,
    or an actor that is not the trigger's (`actor_of`)."""
    if not isinstance(trigger, dict) or trigger.get("kind") not in KINDS:
        return _refused(f"the call {NONE_WORDS}")
    kind = trigger["kind"]
    got = (_person(trigger) if kind == PERSON else _evaluation(trigger) if kind == EVALUATION
           else _background(trigger, task))
    if not got["ok"]:
        return got
    want = actor_of(got["trigger"])
    if actor != want:
        return _refused(f"the call's actor {actor!r} is not its {kind} trigger's ({want!r})")
    return got
