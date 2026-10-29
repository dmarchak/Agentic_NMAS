"""A change record and rollback plan, drafted in the deploy preview (PHASE8_PLAN 16.11 item 3,
Decision 5; 18.1 A2.3; board CR, `ChangeRecordDraft.dc.html`).

**What it is.** A document in a change board's format (Summary, Scope, Risk, Implementation,
Verification, Rollback plan, Window and approver, Status), drafted on a person's press from the
deploy preview they are reading. Every fact code knows is filled by Mercury and marked so: the
device, the program and its hash, the stated reasons, Verify's scope and checks, the rollback's
lines (`deploy.rollback_commands`, the function the pipeline's rollback runs, over the same
program and the same captured configuration), the risk's level by a stated rule. The model
writes only the words around them: the Summary and the Risk's reading, marked AI.

**Its effect on checks: neither stricter nor looser** (16.11): it is a document. The program and
the preview stay what is confirmed; the confirm never reads the draft, and Deploy is the same
button, bound to the same hash, with or without one. It never commits, deploys or approves.

**What leaves the host** (15.11; the decision recorded in docs/STANDING_APPROVAL_LOG.md, the
board's "from this preview's program (masked)" made stricter): **no configuration value, and no
line but its leading keywords** (a line that is keywords alone, ``lldp run``, ``shutdown``, is
sent as those keywords). A deploy's program is the configuration class, off on every network
until C1720, so
the model is sent the program's SHAPE in Mercury's words (:func:`shape`): each section it
touches by kind and name (an interface by its canonical name, any other section by at most two
leading keywords), the settings each line sets by at most two leading keywords, never a value
(a token holding a digit, a capital, a dot, a colon or a slash ends the keywords; a free-text
command keeps its first word only), and a line that would be masked on its way out (a secret's
position or shape) left out whole and counted. With it: the device and its platform, Verify's
scope and the management families it names, the preview's derived effects and verify checks in
the preview's own words, counts, and Mercury's risk level with its rule. These are the
topology class (interfaces, adjacencies), so the call is made only where the network's
topology class is allowed (`egress_classes.topology_allowed`), and never for a network carrying
a classification marking. The gateway's egress mask covers every byte as ever.

**What Mercury checks before anything is drawn** (:func:`check`): the words must not name an
interface the program does not touch, nor a device of the network other than the one deployed,
unless the preview's own words sent with it name that interface or device (a verify check reads
an adjacency to a neighbour over another interface); `mentions` likewise; a quoted
configuration line is refused outright, since the model was sent none. A refused draft is never
drawn: "Couldn't draft: …", the call kept in History.

**One person's press, one recorded call** (PHASE8_PLAN 18.3: trigger person); never a
background feature.
"""
import functools
import json
import logging
import re
from enum import Enum

from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)

FEATURE = "change_record"
PROMPT = ("change_record", 1)
#: The kind of subject a call is about (`history_sources.SUBJECT_WORDS`).
SUBJECT_KIND = "deploy_preview"

#: The steps a press runs, each named on the manual's page (`modules/manual.py`).
STEPS = (
    ("plan", "the deploy preview planned again with the card's own form (the reasons typed, the "
             "lines ticked), exactly as the card draws it; refused, naming both hashes, when its "
             "program is not the one the card drew"),
    ("facts", "Mercury's facts filled by code: the program and its hash, the stated reasons, "
              "Verify's scope and checks, the rollback's lines as the pipeline's rollback "
              "computes them from the program and the captured configuration, and the risk's "
              "level by its stated rule"),
    ("shape", "what is sent built from them: the program's shape in keywords, never a value, a "
              "line carrying a secret left out whole and counted; refused with nothing sent "
              "where the network's topology class is off"),
    ("ask", "one recorded, capped call through the AI gateway, as the person who pressed"),
    ("check", "the words refused, never drawn, when they name an interface the program does "
              "not touch, another device of the network, or quote a configuration line"),
    ("draw", "the draft drawn in the preview, each section marked Mercury or AI, labelled a "
             "draft; Deploy below unchanged; a re-planned program marks it stale"),
)


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


@register("change_record", 1)
class ChangeRecordWords(StrictModel):
    """The model's part of a change record: the Summary, the Risk's reading, and every
    interface and device its words name (which Mercury checks against the change)."""
    summary: str
    risk: str
    mentions: list[str]


#: The longest each of the model's sections may be (characters); longer is refused at check.
MAX_SUMMARY = 600
MAX_RISK = 900

#: Section headers whose name is an interface (canonicalised), everything else by keywords.
_INTERFACE_HEADER = re.compile(r"^interface\s+(\S+)", re.I)
#: A keyword: lower case letters and hyphens, nothing that can hold a value, but for a version
#: or a standard's digits inside a word (ipv6, ospfv3, snmpv3, dot1q).
_KEYWORD = re.compile(r"^[a-z][a-z-]*(?:v\d|\d[a-z]+)?$")
#: Free-text commands: their words after the first are a person's text, never sent.
_FREE_TEXT = ("description", "banner", "remark", "name", "alias", "contact", "location")
#: The routing protocols a section or a line can touch, by its keywords.
_PROTOCOLS = (("ospfv3", re.compile(r"^(router ospfv3|ospfv3|ipv6 ospf)\b")),
              ("ospf", re.compile(r"^(router ospf|ip ospf)\b")),
              ("bgp", re.compile(r"^(router bgp|neighbor|bgp)\b")),
              ("eigrp", re.compile(r"^(router eigrp|ip eigrp|ipv6 eigrp)\b")),
              ("rip", re.compile(r"^(router rip|ip rip|ipv6 rip)\b")),
              ("isis", re.compile(r"^(router isis|ip router isis|isis)\b")),
              ("static routes", re.compile(r"^(ip route|ipv6 route)\b")))


def keywords(line: str, most: int = 2) -> str:
    """At most *most* leading keywords of *line* (``ipv6 ospf 1 area 0`` → ``ipv6 ospf``), never
    a value: a token holding a digit (but a version's inside a word, `_KEYWORD`), a capital, a
    dot, a colon or a slash ends them; a free-text
    command keeps its first word only; ``no`` is kept as the line's own form."""
    words = (line or "").strip().split()
    out, neg = [], False
    if words and words[0] == "no":
        neg, words = True, words[1:]
    for w in words:
        if len(out) >= most or not _KEYWORD.match(w):
            break
        out.append(w)
        if w in _FREE_TEXT:
            break
    return ("no " if neg and out else "") + " ".join(out)


def _sections(commands) -> list:
    """``[(header or "", [leaf lines])]`` for a program, in its order (`program_structure`)."""
    from modules.nsot.deploy import program_structure

    out, index = [], {}
    for e in program_structure(list(commands or [])):
        line = (e.get("line") or "").strip()
        if not line or line in ("exit", "end", "!"):
            continue
        chain = list(e.get("chain") or [])
        if not e.get("leaf"):
            if not chain and line not in index:
                index[line] = len(out)
                out.append((line, []))
            continue
        top = chain[0].strip() if chain else ""
        if top not in index:
            index[top] = len(out)
            out.append((top, []))
        out[index[top]][1].append(line)
    return out


def _masked(line: str, values=None) -> bool:
    """Whether *line* would be masked on its way out (a secret's position, shape or value)."""
    from modules import redact
    return redact.redact_egress(line, values) != line


def shape(commands, values=None) -> dict:
    """``{"sections": [{"kind", "name", "settings", "lines"}], "left_out", "interfaces",
    "protocols"}``: the program's SHAPE, what the model is sent in its place. An interface
    section is named by its canonical name; any other by at most two leading keywords; each
    line by its keywords (:func:`keywords`), the settings de-duplicated in order. A line that
    would be masked on its way out (its header included) is left out whole and counted in
    ``left_out``. PURE but for the known secret values *values* (`redact.known_secret_values`)."""
    from modules.nsot import ifnames

    sections, left_out, interfaces, protocols = [], 0, [], []
    for header, leaves in _sections(commands):
        if header and _masked(header, values):
            left_out += 1 + len(leaves)
            continue
        m = _INTERFACE_HEADER.match(header)
        if m:
            kind, name = "interface", ifnames.canonical(m.group(1))
            if name not in interfaces:
                interfaces.append(name)
        elif header:
            kind, name = "section", keywords(header)
        else:
            kind, name = "global", ""
        settings, n = [], 0
        for leaf in leaves or ([header] if kind == "global" else []):
            if _masked(leaf, values):
                left_out += 1
                continue
            n += 1
            k = keywords(leaf)
            if k and k not in settings:
                settings.append(k)
        if kind != "global" and not leaves:
            n = 1
        if kind == "global" and not n:
            continue
        for words in [name if kind == "section" else ""] + settings:
            plain = words[3:] if words.startswith("no ") else words
            for proto, rx in _PROTOCOLS:
                if plain and rx.match(plain) and proto not in protocols:
                    protocols.append(proto)
        sections.append({"kind": kind, "name": name, "settings": settings, "lines": n})
    return {"sections": sections, "left_out": left_out, "interfaces": interfaces,
            "protocols": protocols}


def risk(*, reasons, removals: int, protocols, drops: int, down) -> dict:
    """Mercury's risk level and its rule in words (board CR's Risk, the Mercury part): high when
    an adjacency is expected to drop or a line is removed (Mode B); medium when a line needs a
    stated reason, an interface is shut or a routing protocol is touched; low otherwise.
    *reasons* are the lines needing a stated reason (drawn here, never sent)."""
    level = (RiskLevel.high if drops or removals else
             RiskLevel.medium if reasons or down or protocols else RiskLevel.low)
    n = len(reasons)
    said = [f"{n} line{'' if n == 1 else 's'} needing a stated reason",
            f"{removals} removal{'' if removals == 1 else 's'}",
            f"{len(protocols)} routing protocol{'' if len(protocols) == 1 else 's'} touched"
            + (f" ({', '.join(protocols)})" if protocols else "")]
    if down:
        said.append(f"{len(down)} interface{'' if len(down) == 1 else 's'} shut")
    if drops:
        said.append(f"{drops} adjacenc{'y' if drops == 1 else 'ies'} expected to drop")
    return {"level": level.value, "rule": "Mercury's rule: " + ", ".join(said) + ".",
            "reasons": list(reasons)}


def facts(*, host: str, network: str, platform: str, program_hash: str, lines, commands,
          captured: str, effects: dict, derived, checks, authorised, removals: int,
          intent_commit: str = "", golden: str = "", values=None) -> dict:
    """Mercury's facts for one device's deploy preview, all of them code's: what the draft's
    Mercury sections draw, and what :func:`sent` takes the model's part from. *lines* and
    *authorised* are the preview's (masked); *commands* and *captured* the unmasked program
    and captured configuration, from which the rollback the pipeline would run is computed
    (`deploy.rollback_commands`, everything treated as landed) and then masked; *effects*
    the plan's `expected_effects` (down, up, adjacencies_drop); *derived* and *checks* the
    preview's own words (`preview_confirm.expected_part`)."""
    from modules.nsot import verify_scope
    from modules.nsot.deploy import rollback_commands
    from modules.outbound import mask_payload

    try:
        rollback = rollback_commands(list(commands or []), captured or "")
        rollback_error = ""
    except Exception as exc:                            # noqa: BLE001 (said, never raised)
        log.warning("change record: %s's rollback could not be computed (%s)", host, exc)
        rollback, rollback_error = [], f"{type(exc).__name__}: {exc}"
    v = verify_scope.classify(list(commands or []))
    families = sorted({verify_scope.family(s) for s in v["sections"]} - {""})
    sh = shape(commands, values)
    fx = effects or {}
    reasons = [str(a.get("line", "")) for a in authorised or []]
    needing = list(dict.fromkeys(reasons))
    down = list(fx.get("down") or [])
    drops = len(fx.get("adjacencies_drop") or [])
    touched = list(sh["interfaces"])
    for n in down + list(fx.get("up") or []):
        if n not in touched:
            touched.append(n)
    return mask_payload({
        "host": host, "network": network, "platform": platform or "unknown",
        "program_hash": program_hash, "lines": list(lines or []),
        "intent_commit": (intent_commit or "")[:12], "golden": (golden or "")[:10],
        "reasons": [{"line": str(a.get("line", "")), "reason": str(a.get("reason", ""))}
                    for a in authorised or []],
        "removals": int(removals or 0),
        "verify_scope": {"scope": v["scope"], "why": v["why"], "families": families},
        "derived": list(derived or []), "checks": [dict(c) for c in checks or []],
        "rollback": list(rollback), "rollback_error": rollback_error,
        "shape": sh, "interfaces": touched,
        "risk": risk(reasons=needing, removals=int(removals or 0), protocols=sh["protocols"],
                     drops=drops, down=down),
    })


def sent(f: dict) -> dict:
    """What the model is sent for facts *f*: the program's shape and Mercury's own words, never
    a configuration line or a value (the module's docstring). Its keys are the allowed set
    (`SENT_KEYS`), held by tests/test_ai_change_record.py."""
    r = f["risk"]
    return {
        "device": f["host"], "platform": f["platform"],
        "program": {"lines": len(f["lines"]), "sections": f["shape"]["sections"],
                    "left_out_carrying_a_secret": f["shape"]["left_out"]},
        "interfaces_touched": list(f["interfaces"]),
        "protocols_touched": list(f["shape"]["protocols"]),
        "verify": {"scope": f["verify_scope"]["scope"],
                   "families": f["verify_scope"]["families"]},
        "expected_effects": list(f["derived"]),
        "verify_checks": list(f["checks"]),
        "counts": {"needing_a_stated_reason": len(r["reasons"]), "removals": f["removals"],
                   "rollback_lines": len(f["rollback"])},
        "risk": {"level": r["level"]},
    }


#: The keys :func:`sent` may carry, and no other (the allowed classes, 15.11).
SENT_KEYS = ("device", "platform", "program", "interfaces_touched", "protocols_touched",
             "verify", "expected_effects", "verify_checks", "counts", "risk")


def parts(f: dict) -> dict:
    """The call's own data: the change's shape, as delimited data (`gateway.build_request`)."""
    return {"change": json.dumps(sent(f), indent=1, sort_keys=True)}


def subject(f: dict) -> dict:
    """What the call is about (15.14), with Mercury's facts as drawn (masked): the draft is
    drawn again from its call, never from the page."""
    return {"kind": SUBJECT_KIND, "id": f["program_hash"], "devices": [f["host"]],
            "network": f["network"], "preview": f}


# ── The check: the words name nothing the change does not hold ─────────────────────────────

@functools.lru_cache(maxsize=1)
def _interface_pattern():
    from modules.nsot import ifnames

    abbrevs = sorted({a for _c, al in ifnames.INTERFACE_PREFIXES for a in al},
                     key=len, reverse=True)
    alt = "|".join(re.escape(a) + (r"\s?" if len(a) >= 4 else "") for a in abbrevs)
    return re.compile(r"(?<![\w-])(?:" + alt + r")\d+(?:/\d+)*(?:\.\d+)?(?![\w/])", re.I)


#: A configuration line quoted in the words: inside backticks or quotes, starting as a
#: command does (lower-case keywords then anything).
_QUOTED = re.compile(r"[`\"“‘']\s*((?:no\s+)?[a-z][a-z-]*(?:\s+\S+)+?)\s*[`\"”’']")


def named_interfaces(text: str) -> list:
    """The interfaces *text* names, canonicalised, in order (``Gi3`` is GigabitEthernet3)."""
    from modules.nsot import ifnames

    out = []
    for m in _interface_pattern().finditer(text or ""):
        name = ifnames.canonical(m.group(0).replace(" ", ""))
        if name not in out:
            out.append(name)
    return out


def check(words, f: dict, known=()) -> str:
    """Why the model's *words* (a `ChangeRecordWords`) cannot be drawn for facts *f*, or ``""``.
    *known* is every device name of the network."""
    from modules.ai import explain

    summary, risk_words = words.summary.strip(), words.risk.strip()
    if not summary:
        return "the answer has no summary"
    if len(summary) > MAX_SUMMARY or len(risk_words) > MAX_RISK:
        return (f"the answer is longer than a change record's section may be (summary "
                f"{len(summary)} of {MAX_SUMMARY} characters, risk {len(risk_words)} of "
                f"{MAX_RISK})")
    text = summary + "\n" + risk_words
    # What the words may name: the device deployed, the interfaces the program touches, and the
    # interfaces and devices the preview's own words sent with it name (a verify check reads
    # an adjacency to a neighbour over an interface the program does not touch).
    said = "\n".join(list(f.get("derived") or []) + [
        f"{c.get('check', '')} {c.get('expects', '')}" for c in f.get("checks") or []])
    touched = set(f["interfaces"]) | set(named_interfaces(said))
    named = set(known) | {f["host"]}
    allowed = {f["host"]} | set(explain.named_devices(said, named))
    for name in named_interfaces(text):
        if name not in touched:
            return f"the answer named {name}, which the program does not touch"
    others = [d for d in explain.named_devices(text, named) if d not in allowed]
    if others:
        return f"the answer named {others[0]}, a device this deploy does not change"
    for m in words.mentions:
        m = (m or "").strip()
        if not m:
            continue
        iface = named_interfaces(m)
        if iface and iface[0] not in touched:
            return f"the answer named {iface[0]}, which the program does not touch"
        if not iface and m in named and m not in allowed:
            return f"the answer named {m}, a device this deploy does not change"
    q = _QUOTED.search(text)
    if q:
        return (f"the answer quoted {q.group(1)!r} as a line; it was sent no configuration "
                "line, so a quoted one is not the program's")
    return ""


# ── The draft, as drawn ───────────────────────────────────────────────────────────────────

def view(f: dict, words: dict, call: dict) -> dict:
    """The draft as the card draws it: each section, its source (``mercury`` or ``ai``), and
    the call's who, model and cost. *words* is the model's answer as JSON; *call* the call's
    row (its id, actor, trigger, model, cost)."""
    from modules.ai import profiles

    model = call.get("model") or ""
    try:
        model_words = profiles.profile(model)["words"]
    except KeyError:
        model_words = model
    trig = call.get("trigger") or {}
    out = {"facts": f, "summary": (words.get("summary") or "").strip(),
           "risk_words": (words.get("risk") or "").strip(),
           "call_id": call.get("id") or "", "actor": call.get("actor") or "",
           "trigger": trig.get("kind") or "", "by": trig.get("by") or call.get("actor") or "",
           "model": model, "model_words": model_words,
           "cost_usd": float(call.get("cost_usd") or 0.0), "at": call.get("at") or ""}
    # What Copy as text copies, the same text Download (.md) saves.
    out["text"] = markdown(out)
    return out


def markdown(v: dict) -> str:
    """The draft as text, for Copy and Download (.md): every section, its source said."""
    f = v["facts"]
    out = [f"# Change record: {f['host']}, deploy committed intent", "",
           f"DRAFT by AI, not reviewed by anyone. A draft for program {f['program_hash'][:12]}: "
           "it is not the change; the program is.", "",
           "## Summary (AI)", "", v["summary"], "",
           "## Scope (Mercury)", "",
           f"1 device: {f['host']} ({f['platform']}). "
           + (f"Interfaces {', '.join(f['interfaces'])}. " if f["interfaces"] else "")
           + (f"Intent at {f['intent_commit']}." if f["intent_commit"] else ""), "",
           "## Risk (Mercury, AI)", "", f"Level: {f['risk']['level']}. {f['risk']['rule']}", "",
           v["risk_words"], "",
           "## Implementation (Mercury)", "",
           f"Program {f['program_hash'][:12]}, {len(f['lines'])} line(s), sent merge-only "
           f"holding {f['host']}:", "", "```"] + list(f["lines"]) + ["```", ""]
    for r in f["reasons"]:
        out.append(f"The stated reason for `{r['line']}`: \"{r['reason']}\".")
    out += ["", "## Verification (Mercury)", "",
            f"{f['verify_scope']['scope'].upper()}: {f['verify_scope']['why']}."]
    out += [f"- {c.get('check')}: {c.get('expects')} ({c.get('read')})" for c in f["checks"]]
    out += ["", "## Rollback plan (Mercury)", "",
            "On a failed Verify, Mercury undoes what landed, per device, and says what it "
            "achieved:", "", "```"] + list(f["rollback"]) + ["```", ""]
    if f["golden"]:
        out.append(f"A manual back-out: restore {f['host']}'s golden {f['golden']} from its "
                   "History tab.")
    out += ["", "## Window and approver", "", "[your change window] · [your approver]", "",
            "## Status", "",
            f"Drafted by {v['model_words']} ({v['model']}), trigger person ({v['by']}), call "
            f"{v['call_id']}."]
    return "\n".join(out).rstrip() + "\n"


def from_call(call_id: str, network: str, host: str) -> dict:
    """A drafted record read back from its call (``{"ok", "view", "error"}``): the call must be
    this feature's, about *host* on *network*, answered and shown. Never a model call."""
    from modules.ai import calls

    got = calls.find(call_id or "")
    row = got.get("row")
    if got["state"] != "ok" or not row:
        return {"ok": False, "error": f"no AI call {call_id!r} is recorded"
                + (f" (the record cannot be read: {got.get('error')})"
                   if got["state"] == "unreadable" else "")}
    subj = row.get("subject") or {}
    if (row.get("feature") != FEATURE or subj.get("kind") != SUBJECT_KIND
            or subj.get("devices") != [host] or subj.get("network") != network):
        return {"ok": False, "error": f"the call {call_id} is not a change record for {host}"}
    shown = any((u.get("use") or "").startswith("shown") for u in got.get("uses") or [])
    if row.get("verdict") != "ok" or not shown:
        return {"ok": False, "error": f"the call {call_id} drew no change record"}
    words = row.get("output")
    if not isinstance(words, dict):
        try:
            words = json.loads(row.get("response") or "")
        except ValueError:
            words = None
    if not isinstance(words, dict):
        return {"ok": False, "error": f"the call {call_id}'s answer cannot be read"}
    return {"ok": True, "view": view(subj.get("preview") or {}, words, row), "error": ""}


def draft(f: dict, *, actor: str, trigger: dict, shown_hash: str, known=(), send=None,
          today: str = None) -> dict:
    """A person's press: facts *f* (this preview, planned again from the card's form) drafted
    into a change record, or why not. ``{"ok", "state", "error", "detail", "view"?,
    "call_id"?}``; *state* is ``drafted``, ``moved`` (the card's program is not the plan's now,
    nothing sent), ``refused`` (a gate or Mercury's check) or ``failed``."""
    from modules.ai import calls, egress_classes, gateway

    if shown_hash and shown_hash != f["program_hash"]:
        return {"ok": False, "state": "moved", "error": "moved",
                "detail": (f"the preview moved: the card drew program {shown_hash[:12]} and "
                           f"the plan is {f['program_hash'][:12]} now; nothing was sent")}
    if not f["lines"]:
        return {"ok": False, "state": "refused", "error": "nothing",
                "detail": "the program sends nothing, so there is no change to record"}
    allowed = egress_classes.topology_allowed(f["network"])
    if not allowed["allowed"]:
        return {"ok": False, "state": "refused", "error": "class_off",
                "detail": f"{allowed['why']}; a change record sends the topology class (the "
                          "interfaces and adjacencies it touches), so nothing was sent"}
    got = gateway.ask(FEATURE, PROMPT, ChangeRecordWords, parts(f), actor=actor,
                      trigger=trigger, subject=subject(f), network=f["network"], send=send,
                      today=today)
    if not got.get("ok"):
        return {"ok": False, "state": "refused", "error": got.get("error") or "failed",
                "detail": got.get("detail") or "", "call_id": got.get("call_id") or ""}
    words = got["output"]
    links = {"page": f"/v2/device/{f['host']}", "anchor": "change-record"}
    why = check(words, f, known)
    if why:
        calls.record_use(got["call_id"], "refused by validation", actor=actor, detail=why,
                         links=links)
        return {"ok": False, "state": "refused", "error": "couldnt_draft",
                "detail": f"Couldn't draft: {why}. The call is in History.",
                "call_id": got["call_id"]}
    calls.record_use(got["call_id"], "shown: drafted", actor=actor, links=links,
                     detail=f"for program {f['program_hash'][:12]}")
    row = {"id": got["call_id"], "actor": actor, "trigger": trigger,
           "model": _pinned_model(), "cost_usd": got.get("cost_usd") or 0.0}
    return {"ok": True, "state": "drafted", "error": "", "detail": "",
            "call_id": got["call_id"],
            "view": view(f, words.model_dump(mode="json"), row)}


def _pinned_model() -> str:
    from modules.ai import profiles
    return (profiles.TASKS.get(FEATURE) or {}).get("model", "")


def carried(call_id: str, f: dict) -> dict:
    """A draft the card carries (its call id) on a re-plan: drawn whole when it is for the
    program planned now, else stale, naming both hashes, its AI words kept; or why not."""
    got = from_call(call_id, f["network"], f["host"])
    if not got["ok"]:
        return {"ok": False, "state": "unreadable", "error": "unreadable",
                "detail": got["error"]}
    v = got["view"]
    was = (v["facts"] or {}).get("program_hash") or ""
    if was != f["program_hash"]:
        return {"ok": True, "state": "stale", "call_id": call_id, "view": v,
                "was": was, "now": f["program_hash"]}
    return {"ok": True, "state": "drafted", "call_id": call_id, "view": v}


def batch_custom_id(case_n: int, run: int) -> str:
    """A batched request's custom_id for recorded case *case_n*, run *run* (`gateway.ask_batch`,
    evaluation only)."""
    return f"c{int(case_n)}-{PROMPT[0]}-v{PROMPT[1]}-r{int(run)}"


def batch_request(case_n: int, run: int, f: dict) -> dict:
    """One evaluation request for facts *f*: exactly what a press sends (`parts`, `subject`)."""
    return {"custom_id": batch_custom_id(case_n, run), "feature": FEATURE, "prompt": PROMPT,
            "schema": ChangeRecordWords, "parts": parts(f), "subject": subject(f)}
