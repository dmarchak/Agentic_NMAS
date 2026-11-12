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
opens no session, holds no device, starts no job and writes nothing. From its answer to a run
is the confirm route's work: the previewed hash, sent back by a verified person.

**Who calls it:** the one door an AI answer comes through (`modules/ai/fix_proposal.py`), which
records each refusal with the call that made the answer, and the fix-it path's check of a
proposal in an incident (`modules/fixit/proposals.py`: whoever proposed it, held to what the
incident names and to the heal guards before this module's preview). This module knows nothing
of where a proposal came from, and holds no reference to the AI modules or to the fix-it path's
records (section 12's scan of `modules/heal/`, tests/test_heal_analysis_never_read.py).

Today the catalog holds two operations, each Re-subscribe's (C2838): the telemetry
Re-subscribe, and its one-step Re-add the receiver, which adds back a receiver a run left
removed (`resubscribe.apply` with ``readd``; its card's own button posts it). Both run the same
function, and each is previewed by the same card, bound to its own hash.
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


def _resubscribe_drawn(p: dict) -> dict:
    """What Re-subscribe's card draws of a plan (`routes/resubscribe_v2.py`, `_masked`: no
    inventory row, no intent, every line masked; ``hash`` the selection's)."""
    from modules.redact import redact_text

    return {"ok": p["ok"], "refusals": [redact_text(x) for x in p["refusals"]],
            "dialect": p["dialect"], "hash": p.get("hash", ""),
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
)}


def checked(key, params) -> tuple:
    """``(operation, parameters)`` for a named operation and its parameters, each held to the
    schema, or raises `Refused`: *key* one of the catalog's; *params* an object giving every
    parameter the operation takes, each of its shape, and nothing else. Reads nothing."""
    if not isinstance(key, str) or key not in CATALOG:
        raise Refused("not_in_catalog", (
            f"a proposal names an operation of the catalog ({listed(sorted(CATALOG))}), and "
            f"this one names {said(key) if isinstance(key, str) else kind_of(key)}"))
    op = CATALOG[key]
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
