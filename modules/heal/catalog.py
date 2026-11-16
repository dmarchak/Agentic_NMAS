"""The catalog: the operations a proposal may name (docs/MERCURY_CHARTER.md, "The fix-it path";
docs/HEAL_TO_INTENT.md section 12: the AI may propose one operation from Mercury's catalog,
with its parameters; code validates it against intent and the guards, and a person approves it
before it runs).

**Data in code.** Each `Operation` declares:
- its ``key``, the operation's own (`resubscribe.KEY`), never a second name for it;
- its ``params``, a strict schema: every parameter it takes, each with the shape it is held
  to (`Param.refusal`). A parameter the schema does not name is refused because the schema
  does not name it, whatever it holds (a command, a program, a flag): nothing is matched as a
  pattern;
- its ``plan``, the function that builds its preview: the operation's OWN plan, called and
  never copied, which is where committed intent and the operation's guards are asked (for
  Re-subscribe, `resubscribe.plan`: the device in the network's inventory, each subscription
  declared by the device's committed intent, the removal's measured shape, the program
  sendable);
- its ``drawn``, the plan as the operation's preview route draws it, every line masked;
- ``preview_endpoint`` and ``confirm_endpoint``, the route that draws the preview and the one
  a verified person confirms it at, by endpoint name (the confirm is a row of
  `route_gates.GATES`, its preview the one `operation_stages.STAGES` names for it);
- ``runs``, the NAME of the function the confirm route runs, a dotted text the tests hold the
  rule by (tests/test_ai_fix_rule.py). This module never resolves it, imports it or calls it.

**Nothing here sends.** `preview` validates a named operation and its parameters and asks the
operation's plan, which reads Mercury's records alone (the inventory, committed intent): it
opens no session, holds no device, starts no job and writes nothing to a store. The collector
step's preview here names the step and never runs the close helper, not even its dry run: a
proposal causes nothing on Mercury's host (the operator, 2026-11-14); the dry run runs only on
the person's own card preview, whose hash the confirm is bound to. From its answer to a run
is the confirm route's work: the previewed hash, sent back by a verified person.

**Who calls it:** the one door an AI answer comes through (`modules/ai/fix_proposal.py`), which
records each refusal with the call that made the answer, and the fix-it path's check of a
proposal in an incident (`modules/fixit/proposals.py`: whoever proposed it, held to what the
incident names and to the heal guards before this module's preview). This module knows nothing
of where a proposal came from, and holds no reference to the AI modules or to the fix-it path's
records (section 12's scan of `modules/heal/`, tests/test_heal_analysis_never_read.py).

Today the catalog holds three operations, each Re-subscribe's (C2838): the telemetry
Re-subscribe; its one-step Re-add the receiver, which adds back a receiver a run left
removed (`resubscribe.apply` with ``readd``; its card's own button posts it); and the
re-subscribe with the collector step (C3078, `resubscribe.apply` with ``collector``: "Close
the collector's stale session for <device>, then re-subscribe"), whose proposal never runs the close
helper (its dry run runs on the person's own card preview). All run the same function, and each is previewed by the
same card, bound to its own hash.

**A proposal may also name a built-in command plan** (`COMMAND_PLANS`; C3757, path 2: "One
execution path: G7's recovery becomes the first built-in command plan"): each template that
ships with Mercury (`modules/nsot/command_plan.py`, `builtin`), by its key, its parameters its
template's typed ones held by shape here (`command_plan.checked`), its preview the plan's own
(`command_plan.preview`: the parameters validated against Mercury's model, Mercury's rule for
raw lines), run by the command-plan runner (`command_plan_run.run`) on the deploy pipeline's
engine. It is not an operation of the catalog: it sends nothing of its own. It is approved on
its incident's page, as a step of the incident's plan (`plan_engine`'s command-plan step);
Recover an err-disabled interface (G7, C3712) is the first.
"""

import logging
from dataclasses import dataclass

from modules.heal import resubscribe

log = logging.getLogger(__name__)

#: A device's name: at most a DNS name's 253 characters.
NAME_CHARS = 253
#: The most subscriptions one proposal names: what the card's own form takes
#: (`routes/resubscribe_v2.py`, `_subs`).
IDS_AT_MOST = 20
#: An IOS-XE telemetry subscription id is 0 to 2147483647: at most ten digits (the plan
#: checks the value, `diagnose.render`).
ID_DIGITS = 10
#: How much of a refused value is said back.
SAID_CHARS = 60


class Refused(ValueError):
    """Nothing was previewed; ``code`` names the check and the words say what it compared."""

    def __init__(self, code: str, words: str):
        super().__init__(words)
        self.code = code


def said(value) -> str:
    """A refused value as a refusal says it: its first `SAID_CHARS` characters (a text quoted,
    every control character escaped), and its length when it is longer."""
    text = value if isinstance(value, str) else repr(value)
    shown = repr(text[:SAID_CHARS]) if isinstance(value, str) else text[:SAID_CHARS]
    return shown if len(text) <= SAID_CHARS else f"{shown}… ({len(text)} characters)"


def kind_of(value) -> str:
    """What a value is, in a refusal's words (true/false is never a number)."""
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return "true/false"
    for types, word in (((int, float), "a number"), (str, "text"), (dict, "an object"),
                        ((list, tuple), "a list")):
        if isinstance(value, types):
            return word
    return f"a {type(value).__name__}"


def listed(items) -> str:
    items = [str(i) for i in items]
    return " and ".join([", ".join(items[:-1]), items[-1]]) if len(items) > 1 else (
        items[0] if items else "none")


def _device_refusal(value) -> str:
    if not isinstance(value, str):
        return kind_of(value)
    if not (1 <= len(value) <= NAME_CHARS and value.isascii() and value.isprintable()
            and " " not in value):
        return f"{said(value)} ({len(value)} characters)"
    return ""


def _ids_refusal(value) -> str:
    if not isinstance(value, list):
        return kind_of(value)
    if not 1 <= len(value) <= IDS_AT_MOST:
        return f"a list of {len(value)}"
    for item in value:
        if not isinstance(item, str):
            return f"a list holding {kind_of(item)} ({said(item)})"
        if not (item.isascii() and item.isdigit() and len(item) <= ID_DIGITS):
            return f"a list holding {said(item)}"
    twice = sorted({i for i in value if value.count(i) > 1})
    if twice:
        return f"a list naming {listed(twice)} more than once"
    return ""


def _id_refusal(value) -> str:
    if not isinstance(value, str):
        return kind_of(value)
    if not (value.isascii() and value.isdigit() and 1 <= len(value) <= ID_DIGITS):
        return said(value)
    return ""


@dataclass(frozen=True)
class Param:
    """One parameter of an operation: its name, the shape it takes in words, and the check
    that holds a value to it (``""``, or what the value is instead)."""
    name: str
    takes: str
    refusal: object


@dataclass(frozen=True)
class Operation:
    key: str
    words: str
    params: tuple
    plan: object
    drawn: object
    preview_endpoint: str
    confirm_endpoint: str
    runs: str


def _resubscribe_plan(network: str, params: dict, sources=None) -> dict:
    """Re-subscribe's own plan for the proposal's parameters (`resubscribe.plan`)."""
    return resubscribe.plan(network, params["device"], list(params["subscriptions"]),
                            sources=sources)


def _readd_plan(network: str, params: dict, sources=None) -> dict:
    """Re-add the receiver's own plan for the proposal's one subscription (`resubscribe.plan`
    with ``readd``)."""
    return resubscribe.plan(network, params["device"], [params["subscription"]], readd=True,
                            sources=sources)


def _collector_plan(network: str, params: dict, sources=None) -> dict:
    """The re-subscribe with the collector step, as a PROPOSAL previews it: the receivers from
    committed intent (`resubscribe.plan`), and the step named, never its session. **A proposal
    causes nothing on Mercury's host** (the operator, 2026-11-14): the close helper's dry run,
    which names the session the step would close, runs only on the person's own card preview
    (their click), and the confirm is bound to that preview's hash, never to this one."""
    p = resubscribe.plan(network, params["device"], list(params["subscriptions"]),
                         sources=sources)
    return dict(p, collector_step="named on the card's own preview: the close helper's dry "
                                  "run runs when you open it, never on a proposal")


def _resubscribe_drawn(p: dict) -> dict:
    """What Re-subscribe's card draws of a plan (`routes/resubscribe_v2.py`, `_masked`: no
    inventory row, no intent, every line masked; ``hash`` the selection's; ``close`` the
    collector step's session and its dry run, when it has one)."""
    from modules.redact import redact_text

    close = p.get("close") or {}
    return {"ok": p["ok"], "refusals": [redact_text(x) for x in p["refusals"]],
            "dialect": p["dialect"], "hash": p.get("hash", ""),
            **({"collector_step": p["collector_step"]} if p.get("collector_step") else {}),
            "close": ({"local": close["local"], "remote": close["remote"],
                       "quiet_s": close["quiet_s"],
                       "dry_run": redact_text(str((close.get("dry_run") or {}).get("words")
                                                  or ""))} if close else {}),
            "units": [{"sub": u["sub"], "line": redact_text(u["line"]), "hash": u["hash"],
                       "remove": [redact_text(x) for x in u["remove"]],
                       "readd": [redact_text(x) for x in u["readd"]]} for u in p["units"]]}


#: The operations a proposal may name, by key.
CATALOG = {op.key: op for op in (
    Operation(
        key=resubscribe.KEY,
        words="Re-subscribe a device's lost telemetry streams",
        params=(
            Param("device", "one name the network's inventory holds (1 to "
                            f"{NAME_CHARS} printable ASCII characters, no space)",
                  _device_refusal),
            Param("subscriptions", f"a list of 1 to {IDS_AT_MOST} subscription ids, each text "
                                   f"of 1 to {ID_DIGITS} digits, each once, that the device's "
                                   "committed intent declares", _ids_refusal),
        ),
        plan=_resubscribe_plan,
        drawn=_resubscribe_drawn,
        preview_endpoint="resubscribe_v2.preview",
        confirm_endpoint="resubscribe_v2.confirm",
        runs="modules.heal.resubscribe.apply",
    ),
    Operation(
        key=resubscribe.READD_KEY,
        words="Add back the receiver of one telemetry subscription a run left removed",
        params=(
            Param("device", "one name the network's inventory holds (1 to "
                            f"{NAME_CHARS} printable ASCII characters, no space)",
                  _device_refusal),
            Param("subscription", f"one subscription id, text of 1 to {ID_DIGITS} digits, that "
                                  "the device's committed intent declares", _id_refusal),
        ),
        plan=_readd_plan,
        drawn=_resubscribe_drawn,
        preview_endpoint="resubscribe_v2.preview",
        confirm_endpoint="resubscribe_v2.readd",
        runs="modules.heal.resubscribe.apply",
    ),
    # C3078: Re-subscribe with the collector step on (one home for the receivers' writes), in
    # the operator's words. Its words say when it applies, the evidence the diagnosis's
    # stale-session rule reads (C3111), so a proposer reading them names it there and nowhere
    # else.
    Operation(
        key=resubscribe.COLLECTOR_KEY,
        words=(resubscribe.COLLECTOR_TITLE.format(device="a device") + ": for a lost stream "
               "whose device's telemetry connection to the collector reads Disconnecting while "
               "the collector still holds an established, idle session from it (`show "
               "telemetry internal connection` on the device; the collector's sessions on "
               "Mercury's host). Mercury closes that one session through its close helper, "
               "then removes and re-adds each subscription's receiver and verifies the "
               "stream"),
        params=(
            Param("device", "one name the network's inventory holds (1 to "
                            f"{NAME_CHARS} printable ASCII characters, no space)",
                  _device_refusal),
            Param("subscriptions", f"a list of 1 to {IDS_AT_MOST} subscription ids, each text "
                                   f"of 1 to {ID_DIGITS} digits, each once, that the device's "
                                   "committed intent declares, all to one receiver",
                  _ids_refusal),
        ),
        plan=_collector_plan,
        drawn=_resubscribe_drawn,
        preview_endpoint="resubscribe_v2.preview",
        confirm_endpoint="resubscribe_v2.close_confirm",
        runs="modules.heal.resubscribe.apply",
    ),
)}


# ── The built-in command plans a proposal may name (C3757, path 2) ──────────────────────────

def _plan_param(name: str, spec: dict) -> Param:
    """A command plan's typed parameter as a proposal's, held by its shape
    (`command_plan.shape_refusal`); Mercury's model is asked by the plan's own preview."""
    from modules.nsot import command_plan

    def refusal(value, _spec=dict(spec)):
        why = command_plan.shape_refusal(_spec, value)
        return "" if not why else (said(value) if isinstance(value, str) else kind_of(value))
    return Param(name, str(spec.get("words") or spec["type"]), refusal)


@dataclass(frozen=True)
class PlanStep:
    """A built-in command plan as a step a proposal names, declared in the action registry's
    shape (the operator, 2026-11-15: it drops into the generalised registry later without
    rework), beside `Operation`, which it leaves as it is:

    - ``params``: its typed inputs, as `Param`s;
    - ``preflight(network, params, *, reads=False, sources=None)``: at proposal time, the plan's
      own preview (Mercury's rule for raw lines, the parameters against Mercury's model; with
      *reads*, the preconditions read through the read engine too), ``{"ok", "refused",
      "drawn", "hash"}``;
    - ``binds``: the fields its hash binds (`command_plan.BINDS`);
    - ``apply(network, params, confirmed_hash, *, actor, reason, actor_verified="",
      person=False) -> dict``: the one contract, which enters the deploy pipeline
      (`command_plan_run.step_apply`);
    - ``conditions``: its declared special conditions (``net_zero``).

    ``plan`` and ``drawn`` answer the catalog's `preview`; the endpoints are its home, its
    incident's page (C3718), where it is approved as a step of the incident's plan."""
    key: str
    words: str
    params: tuple
    preflight: object
    binds: tuple
    apply: object
    conditions: tuple
    preview_endpoint: str = "incident_v2.incident"
    confirm_endpoint: str = "fixit_v2.approve"
    runs: str = "modules.nsot.command_plan_run.run"

    def plan(self, network: str, params: dict, sources=None) -> dict:
        """The plan's own preview (`command_plan.preview`), as a catalog plan answers."""
        from modules.nsot import command_plan

        return command_plan.preview(network, self.key, params, sources=sources)

    @staticmethod
    def drawn(p: dict) -> dict:
        """What a person reads of the plan before Approve (`command_plan.drawn`, masked)."""
        return dict(p.get("drawn") or {})


def _plan_preflight(key: str):
    def preflight(network: str, params: dict, *, reads: bool = False, sources=None,
                  incident: str = "") -> dict:
        from modules.nsot import command_plan, command_plan_run

        p = command_plan.preview(network, key, params, sources=sources)
        refused = "; ".join(p["refusals"])
        if p["ok"] and reads:
            # *incident*: the one it is proposed in, whose classification a check reads.
            got = command_plan_run.preconditions_now(network, key, p, incident=incident)
            refused = "; ".join(f"{j['name']}: {j['words']}" for j in got
                                if j["result"] not in command_plan_run.HOLDS)
        return {"ok": not refused, "refused": refused, "drawn": p["drawn"],
                "hash": "" if refused else p["hash"]}
    return preflight


def _command_plans(templates=None) -> dict:
    """Each command plan of *templates* (those that ship with Mercury, by default) as a
    `PlanStep`: one declaration's shape for a built-in plan and a saved reusable action."""
    from modules.nsot import command_plan, command_plan_run

    return {t.key: PlanStep(
        key=t.key, words=t.words,
        params=tuple(_plan_param(n, s) for n, s in t.parameters.items()),
        preflight=_plan_preflight(t.key), binds=command_plan.BINDS,
        apply=command_plan_run.step_apply(t.key),
        conditions=("net_zero",) if t.net_zero else ())
        for t in (command_plan.builtin() if templates is None else templates).values()}


class _SavedActions:
    """The reusable actions people saved (`nsot.saved_plans`, an admin's each), registered as
    `PlanStep`s by the same declaration as the built-in plans (`_command_plans`), so each is a
    plan step and an entry a proposal may name. Each ask compares the store's identity
    (`saved_plans.stamp`: inode, size, modification time to the nanosecond) with the one it
    registered from, so a save in any process is seen at the next ask, never cached past a
    change. A store that cannot be read registers none, logged. (A registry the catalog asks
    by attribute: the reference scans of modules/fixit/ and modules/ai/ do not follow it, as
    they do not follow the plan engine's `STEP_KINDS`; a step's run is held by its runner's
    own person or authority check, and the AI scan seeds the plan's run.)"""

    def __init__(self):
        self.seen, self.steps = None, {}

    def current(self) -> dict:
        from modules.nsot import saved_plans

        try:
            now = saved_plans.stamp()
        except OSError:
            now = None
        if now != self.seen:
            try:
                every = saved_plans.templates()
                self.steps = _command_plans({k: every[k] for k in saved_plans.actions()
                                             if k in every})
            except Exception as exc:                  # noqa: BLE001 (said; none registered)
                log.error("catalog: the saved actions could not be registered: %s", exc)
                self.steps = {}
            self.seen = now
        return dict(self.steps)


#: The saved reusable actions' registry (`_SavedActions`).
SAVED = _SavedActions()


def refresh_saved() -> dict:
    """The saved reusable actions as the store holds them now (`SAVED.current`)."""
    return SAVED.current()


def saved_actions() -> dict:
    """The saved reusable actions, by key, as the store holds them now (`SAVED`)."""
    return SAVED.current()


#: The built-in command plans a proposal may name, by key, in the catalog's form.
COMMAND_PLANS = _command_plans()
# The saved reusable actions, registered once at import (each save registers again).
refresh_saved()
#: The problem conditions each catalog operation fixes (`modules/problem.py`): what an
#: investigation that lacked it is restarted on once it exists (C3733, `ai.missing.available`).
FIXES = {resubscribe.KEY: ("telemetry_lost",), resubscribe.READD_KEY: ("telemetry_lost",),
         resubscribe.COLLECTOR_KEY: ("telemetry_lost",)}


def capabilities() -> dict:
    """Every step a proposal may name, by key, with the problem conditions it fixes: the
    catalog's operations (`FIXES`) and the built-in command plans (each template's
    ``fixes``). A read of the code."""
    from modules.nsot import command_plan

    out = {k: tuple(FIXES.get(k, ())) for k in CATALOG}
    out.update({t.key: tuple(t.fixes) for t in command_plan.builtin().values()
                if t.key in COMMAND_PLANS})
    return out


def entries() -> dict:
    """What a proposal may name: the catalog's operations, the built-in command plans and the
    reusable actions people saved (`saved_actions`)."""
    return {**CATALOG, **COMMAND_PLANS, **saved_actions()}


def is_command_plan(key) -> bool:
    return isinstance(key, str) and (key in COMMAND_PLANS or key in saved_actions())


def checked(key, params) -> tuple:
    """``(operation, parameters)`` for a named operation (or built-in command plan) and its
    parameters, each held to the schema, or raises `Refused`: *key* one of `entries`; *params*
    an object giving every parameter it takes, each of its shape, and nothing else. Reads
    nothing."""
    known = entries()
    if not isinstance(key, str) or key not in known:
        raise Refused("not_in_catalog", (
            f"a proposal names an operation of the catalog ({listed(sorted(known))}), and "
            f"this one names {said(key) if isinstance(key, str) else kind_of(key)}"))
    op = known[key]
    names = [p.name for p in op.params]
    if not isinstance(params, dict):
        raise Refused("wrong_type", (
            f"{op.key}'s parameters are an object giving {listed(names)}, and the proposal "
            f"gave {kind_of(params)}"))
    unknown = [k for k in params if k not in names]
    if unknown:
        raise Refused("unknown_parameter", (
            f"{op.key} takes exactly the parameters {listed(names)}, and the proposal also "
            f"gives {listed(said(k) for k in unknown[:8])}"
            + (f" and {len(unknown) - 8} more" if len(unknown) > 8 else "")
            + ": a parameter the schema does not name is refused, whatever it holds"))
    missing = [n for n in names if n not in params]
    if missing:
        raise Refused("missing_parameter", (
            f"{op.key} takes the parameters {listed(names)}, and the proposal gives no "
            f"{listed(missing)}"))
    out = {}
    for p in op.params:
        instead = p.refusal(params[p.name])
        if instead:
            raise Refused("wrong_shape", (
                f"{op.key}'s parameter {p.name} is {p.takes}, and the proposal gave "
                f"{instead}"))
        value = params[p.name]
        out[p.name] = list(value) if isinstance(value, list) else value
    return op, out


def preview(key, params, *, network: str, sources=None) -> dict:
    """A named operation and its parameters, held to the catalog and then to the operation's
    own plan: ``{"ok": True, "operation", "params", "preview", "hash"}`` (*preview* the plan as
    the operation's preview route draws it, *hash* the plan's, which the confirm is bound to),
    or ``{"ok": False, "code", "refused"}``, the words naming what was compared and both
    operands. Sends nothing and writes nothing (the module's docstring). *sources* is the
    plan's own seam (tests)."""
    try:
        op, held = checked(key, params)
    except Refused as exc:
        return {"ok": False, "code": exc.code, "refused": str(exc)}
    p = op.plan(network, held, sources)
    if not p.get("ok") or not p.get("hash"):
        return {"ok": False, "code": "refused_by_plan", "refused": (
            f"{op.key}'s own plan refused the proposal for {network}: "
            + ("; ".join(p.get("refusals") or []) or "it gave no program to preview"))}
    return {"ok": True, "operation": op.key, "params": held, "preview": op.drawn(p),
            "hash": p["hash"]}
