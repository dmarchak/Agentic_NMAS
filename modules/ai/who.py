"""WHO, guaranteed in code (the operator's order of 2026-10-29): who made each change, or took
each action, that Explain's answer describes, read from the pack's own records by code, never
from the model, and said as "no record of who" (`NO_RECORD`) where the pack holds none.

**What is a change or an action is decided by what a piece IS, never by words** (`change_of`):
- **a History piece of a kind a person or Mercury does** (`ACTION_KINDS`): a deploy or
  restore's receipt, a Mercury Reload, an intent commit, a golden recorded, a planned-restart
  window declared. Its actor is History's (``who``) with how it was established
  (``verified``, the commit's ``Actor-Verified:``; a pack from schema 7 carries it, an older
  one names the actor only). A restart is not one: it is what happened to the device, and
  Mercury's record of it names who declared the window, never who restarted it.
- **a log line recording a configuration change** (`CONFIG_LOG`): IOS's and IOS-XE's
  ``%SYS-5-CONFIG_I`` ("Configured from console by <user> on vty0 (<address>)", and its forms
  naming only a line, ``by vty0 (<address>)`` or ``by console``), ``%SYS-5-CONFIG_P``
  ("Configured programmatically by process <p> from console as <user> on vty0") and IOS-XE's
  ``%DMI-5-CONFIG_I`` ("Configured from NETCONF/RESTCONF by <user>, transaction-id <n>"). Its
  actor is the user the line names (`config_change`), the device's own account and never a
  verified identity; a line naming only a terminal line is no record of who. An address in it,
  IPv4 or IPv6, is kept as written.
- **the Intent check when it differs:** its actor the device's intent file's last commit
  (``intent_commit``, schema 7: the commit's ``Actor:`` and ``Actor-Verified:``, and when);
  an older pack holds none, so no record of who.

**On the answer** (`mercury_who`, the operator's order (b)): a hypothesis DESCRIBES a change
or an action when it cites one of those pieces (or the section holding it); each such
hypothesis carries ``who`` (`who_of`: the actor of each change it cites, or no record of who).
When its claim does not name that actor (the actor's id, or the part before its ``@``, as a
whole word) or, where none is recorded, does not say "no record of who", Mercury adds it, kept
apart from the model's words (``mercury_who``) and drawn as Mercury's ("who, added by
Mercury"); the model's response stays as received in the call's record. `inserted` is the
sentence as a person reads it on the card, Mercury's words after the model's, and what the
grader grades as kept (`cases.guarded`).

Nothing here reads the pack's text to decide what to do but the configuration-change line's
own fields: a piece's kind and section decide what it is.
"""
import re

#: What is said where the pack holds no actor for a change or an action.
NO_RECORD = "no record of who"
#: History's kinds that are a change or an action someone took (`history_sources.KIND_GROUPS`:
#: deploys and restores, reloads, intent, goldens, planned windows); a restart is not one.
ACTION_KINDS = ("receipt", "reload", "intent", "golden", "window")
#: How an ``Actor-Verified:`` value is said (`history_sources.VERIFIED_WORDS`' meanings); a
#: value it does not name is not verified, as History counts it.
HOW = {"access": "verified sign-in", "host-shell": "host login, not verified",
       "none": "not verified", "": "before verification was recorded"}
#: A log line recording a configuration change, any severity: IOS and IOS-XE's CONFIG_I and
#: CONFIG_P, and IOS-XE's DMI (NETCONF and RESTCONF) CONFIG_I.
CONFIG_LOG = re.compile(r"%(?:SYS|DMI)-\d-CONFIG_[IP]\b")
#: "Configured from <source> by <user or line>[ on <line>][ (<address>)]".
_FROM_BY = re.compile(r"\bConfigured from (?P<source>\S+) by (?P<by>[^\s,()]+)"
                      r"(?: on (?P<line>[^\s,()]+))?(?:\s*\((?P<address>[^()\s]+)\))?", re.I)
#: "Configured programmatically by process <p> from <source> as <user>[ on <line>]".
_PROGRAMMATIC = re.compile(r"\bConfigured programmatically by process (?P<process>\S+) from "
                           r"(?P<source>\S+) as (?P<by>[^\s,()]+)(?: on (?P<line>[^\s,()]+))?"
                           r"(?:\s*\((?P<address>[^()\s]+)\))?", re.I)
#: A terminal line, or a word no account is, where a user would stand: no record of who.
_NOT_A_USER = re.compile(r"^(?:console|con\d*|vty\d+|tty\d+|aux\d*|unknown)$", re.I)
#: The sections whose pieces can be a change (`change_of`).
SECTIONS = ("history", "logs", "intent")


def config_change(text: str):
    """The configuration change a log line records, ``{"user", "line", "address", "source",
    "process"}`` (each "" when the line does not name it), or None when *text* is no
    configuration-change line (`CONFIG_LOG`)."""
    if not text or not CONFIG_LOG.search(text):
        return None
    m = _PROGRAMMATIC.search(text) or _FROM_BY.search(text)
    g = m.groupdict() if m else {}
    by, line = g.get("by") or "", g.get("line") or ""
    if _NOT_A_USER.match(by):
        by, line = "", line or by
    return {"user": by, "line": line, "address": g.get("address") or "",
            "source": g.get("source") or "", "process": g.get("process") or ""}


def how(piece: dict) -> str:
    """How a History piece's or a commit's actor was established, in words; "" when the piece
    does not say (a pack before schema 7)."""
    if "verified" not in (piece or {}):
        return ""
    return HOW.get(piece.get("verified") or "", "not verified")


def _named(who: str, hw: str) -> str:
    return f"{who} ({hw})" if hw else who


def change_of(section: str, piece: dict) -> dict:
    """The change or action *piece* (of the pack's section *section*) records: ``{"ref",
    "kind", "at", "what", "who", "words"}``, *who* the actor or "", *words* how a person reads
    who it was (the actor with how it was established, or `NO_RECORD`); ``{}`` when the piece
    is no change or action (the module's docstring)."""
    piece = piece or {}
    base = {"ref": piece.get("ref") or "", "at": piece.get("at") or ""}
    if section == "history" and piece.get("kind") in ACTION_KINDS:
        who = (piece.get("who") or "").strip()
        return dict(base, kind="history", what=piece.get("what") or piece.get("kind"),
                    id=piece.get("sha") or "", who=who,
                    words=_named(who, how(piece)) if who else NO_RECORD)
    if section == "logs":
        c = config_change(piece.get("text") or "")
        if c is None:
            return {}
        on = f" on {c['line']}" if c["line"] else ""
        at = f" from {c['address']}" if c["address"] else ""
        only = " and ".join(w for w in (f"the line {c['line']}" if c["line"] else "",
                                        f"the address {c['address']}" if c["address"] else "")
                            if w)
        words = (f"{c['user']}{on}{at}, the device's account as its log line names it"
                 if c["user"] else
                 NO_RECORD + (f" (the log line names only {only})" if only else ""))
        return dict(base, kind="config_log", what="a configuration change the device logged",
                    device=piece.get("device") or "", via=c["source"] or "",
                    who=c["user"], words=words, line=c["line"], address=c["address"])
    if section == "intent" and piece.get("state") == "differs":
        commit = piece.get("intent_commit") or {}
        who = (commit.get("actor") or "").strip() if commit.get("state") == "ok" else ""
        words = (f"intent last committed by {_named(who, how(commit))}" if who else NO_RECORD)
        return dict(base, at=commit.get("at") or "", kind="intent_diff",
                    what="the device departs from its committed intent",
                    id=commit.get("sha") or "", who=who, words=words)
    return {}


def _locate(sections, ref: str) -> tuple:
    """``(section name, [pieces])`` *ref* cites: a piece, or a whole section (each of its
    pieces); ``("", [])`` when it cites none of `SECTIONS`."""
    for s in sections or []:
        if s.get("name") not in SECTIONS:
            continue
        if s.get("ref") == ref:
            return s["name"], list(s.get("pieces") or [])
        for p in s.get("pieces") or []:
            if p.get("ref") == ref:
                return s["name"], [p]
    return "", []


def changes_cited(refs, sections) -> list:
    """Each change or action the references *refs* cite in *sections* (the pack as sent), in
    the order cited, each once (`change_of`)."""
    out, seen = [], set()
    for ref in refs or ():
        name, pieces = _locate(sections, ref)
        for p in pieces:
            c = change_of(name, p)
            if c and c["ref"] not in seen:
                seen.add(c["ref"])
                out.append(c)
    return out


def names_who(text: str, who: str) -> bool:
    """Whether *text* names the actor *who* (its id, or the part before its ``@`` when that
    is three characters or more, each as a whole word, any case), or, *who* being "", says
    `NO_RECORD`."""
    low = (text or "").lower()
    if not who:
        return NO_RECORD in low
    forms = {who.lower()}
    local = who.split("@", 1)[0].lower()
    if len(local) >= 3:
        forms.add(local)
    return any(re.search(r"(?<![\w.@'’-])" + re.escape(f)
                         + r"(?![\w@'’-]|\.\w)", low) for f in forms)


def who_of(claim: str, refs, sections) -> list:
    """A hypothesis's ``who``: for each actor of the changes it cites (`changes_cited`),
    grouped by how it is said, ``{"words", "who", "refs", "by"}``, *by* ``"model"`` when the
    claim names it (`names_who`), else ``"mercury"``: Mercury adds it. ``[]`` for a hypothesis
    citing no change or action."""
    groups = {}
    for c in changes_cited(refs, sections):
        g = groups.setdefault(c["words"], {"words": c["words"], "who": c["who"], "refs": []})
        g["refs"].append(c["ref"])
    return [dict(g, by="model" if names_who(claim, g["who"]) else "mercury")
            for g in groups.values()]


def mercury_who(hypotheses, sections) -> list:
    """What Mercury adds to an answer's hypotheses (the operator's order (b)): ``[{"hypothesis",
    "words", "who", "refs"}]``, one for each actor a hypothesis's changes record that its claim
    does not name, *hypothesis* its place (1 first). *hypotheses* are the model's, each with
    ``claim`` and ``evidence_refs`` (a model's object or its JSON)."""
    out = []
    for i, h in enumerate(hypotheses or [], 1):
        claim = h.get("claim") if isinstance(h, dict) else getattr(h, "claim", "")
        refs = h.get("evidence_refs") if isinstance(h, dict) else getattr(h, "evidence_refs", [])
        out += [{"hypothesis": i, "words": w["words"], "who": w["who"], "refs": w["refs"]}
                for w in who_of(claim or "", refs or [], sections) if w["by"] == "mercury"]
    return out


#: Mercury's words as a person reads them after the model's claim.
ADDED = "who, added by Mercury"


def inserted(claim: str, added) -> str:
    """The claim as a person reads it on the card: the model's words, then each actor Mercury
    added (*added*, `mercury_who`'s entries for this hypothesis), marked as Mercury's."""
    if not added:
        return claim or ""
    said = "; ".join(f"{a['words']} [{', '.join(a['refs'])}]" for a in added)
    return f"{(claim or '').rstrip()} ({ADDED}: {said})"


def unattributed(hypotheses, sections) -> list:
    """The places (1 first) of the hypotheses that describe a change or an action and, Mercury's
    additions counted (each hypothesis's ``who`` entries whose *by* is "mercury", as
    `explain.explain_pack` keeps them, or its claim as `inserted`), still lack its actor or
    `NO_RECORD`: none, once Mercury has added what the answer omitted. A check of the property,
    for its tests."""
    out = []
    for i, h in enumerate(hypotheses or [], 1):
        claim = inserted(h.get("claim") or "", [w for w in h.get("who") or []
                                                if w.get("by") == "mercury"])
        if any(w["by"] == "mercury" for w in who_of(claim, h.get("evidence_refs") or [],
                                                    sections)):
            out.append(i)
    return out
