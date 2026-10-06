"""An authorised line: a deliberate exception to a rule the tool enforces,
with the person's stated reason (register C140, C79; the operator's decision
(a), 2026-09-28).

Two classes of line need one, and they share ONE mechanism:

* a **dangerous** line in a deploy or a restore (`shutdown`, `no router ...`),
  flagged by the CI gate's patterns (`pipeline.dangerous_commands`);
* a **secret-position** line a restore would ADD to a device that does not
  hold it (C79). After a rotation the old value is a different line, so a
  restore lands it beside the new one and nothing else refuses it. "Secret
  position" has ONE definition, the positional redactor's
  (`redact.redact_positional`): a second list of what counts as a secret is
  how C95 happened.

**Every authorisation carries a reason** (C140: the dangerous-line
authorisation recorded which lines and who, never why, so an authorised
`shutdown` read afterwards exactly like a misclick). Three properties, which
the 8.8 second-reading's written override decided first and which it reuses
from here:

* **The minimum is SHAPE, never quality.** Not empty, a few words, not a
  copy of the line. Nothing judges whether a reason is good.
* **It is TESTIMONY, not fact.** Drawn as the person's stated reason, never
  as an established cause.
* **The aggregate matters.** The same line authorised on the same device
  again and again is a pattern worth seeing, so a preview shows how often a
  line was authorised there before (`receipts.prior_authorisations`).

An authorisation is ``{"line": <key>, "reason": <text>}``. The KEY is the
line with its secret positions masked, because the browser only ever sees a
masked program and must be able to name the line it authorises; for a line
with no secret in it, the key is the line itself.
"""

import hashlib
import json
import re

#: A few words: at least this many, and this many characters. Three is 8.8's
#: written-override proposal ("fewer than a handful of words"), which reuses
#: this module rather than building its own.
MIN_WORDS = 3
MIN_CHARS = 8

SHAPE_RULE = ("a reason is a few words saying why this line is deliberate; it "
              "is recorded as your statement and never judged")


class NotAuthorised(RuntimeError):
    """A flagged line is not authorised, an authorisation matches nothing,
    or a reason is missing or not a reason."""


def key(line) -> str:
    """The name an authorisation uses for *line*: stripped, secret positions
    masked by the one redactor."""
    from modules.redact import redact_positional

    return redact_positional(str(line or "").strip())


def secret_lines_in(commands) -> list:
    """The KEYS of the program's lines that hold a secret position: the lines
    the positional redactor would change. The one definition."""
    from modules.redact import redact_positional

    out = []
    for line in commands or []:
        s = str(line).strip()
        if s and redact_positional(s) != s:
            out.append(key(s))
    return out


def normalise(raw) -> list:
    """A request's authorisations for one device, as
    ``[{"line": key, "reason": text}]``. Never raises and never invents a
    reason: a bare string (the old shape) becomes an entry with an EMPTY
    reason, which `problems()` refuses by name."""
    out = []
    for item in raw or []:
        if isinstance(item, dict):
            out.append({"line": key(item.get("line")),
                        "reason": str(item.get("reason") or "").strip()})
        else:
            out.append({"line": key(item), "reason": ""})
    return out


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def reason_problem(entry: dict) -> str:
    """Why *entry*'s reason is not the SHAPE of a reason, or ``""``. Never a
    judgement of its quality."""
    reason, line = entry.get("reason") or "", entry.get("line") or ""
    if not reason:
        return f"{line!r} has no reason: {SHAPE_RULE}"
    if _flat(reason) in (_flat(line), _flat(key(line))):
        return f"{line!r}: the reason is a copy of the line; {SHAPE_RULE}"
    if len(reason.split()) < MIN_WORDS or len(reason) < MIN_CHARS:
        return f"{line!r}: {reason!r} is too short to be a reason; {SHAPE_RULE}"
    return ""


def valid_keys(authorisations) -> list:
    """The keys whose reason has the shape of one. What a gate that runs on
    every path (the pipeline's, a restore target's checks) may honour, so an
    authorisation without a reason cannot pass where the hash is not
    compared."""
    return sorted({a["line"] for a in normalise(authorisations)
                   if not reason_problem(a)})


def flagged(commands, extra=()) -> list:
    """Every line of *commands* that needs an authorisation: the dangerous
    ones, plus *extra* keys (a restore's re-added secret lines)."""
    from modules.pipeline import dangerous_commands

    return sorted({key(l) for l in dangerous_commands(commands)} | set(extra or ()))


def problems(commands, authorisations, extra=()) -> list:
    """Every reason this authorisation set does not cover *commands*, all at
    once: an unauthorised flagged line, an authorisation matching nothing (a
    typo or a leftover), a reason that is not the shape of one."""
    auths = normalise(authorisations)
    need = set(flagged(commands, extra))
    given = {a["line"] for a in auths}
    out = []
    missing = sorted(need - given)
    if missing:
        out.append("%d line(s) need an authorisation with a reason: %s"
                   % (len(missing), ", ".join(repr(m) for m in missing)))
    unused = sorted(given - need)
    if unused:
        out.append("%d authorisation(s) match no line that needs one in this program: %s. "
                   "An authorisation that matches nothing is a typo or a leftover."
                   % (len(unused), ", ".join(repr(u) for u in unused)))
    out += [p for p in (reason_problem(a) for a in auths if a["line"] in need) if p]
    return out


def assert_authorised(commands, authorisations, extra=()) -> None:
    found = problems(commands, authorisations, extra)
    if found:
        raise NotAuthorised("; ".join(found))


def fingerprint(commands, authorisations, selected=(), declared=()) -> str:
    """The program AND what was authorised within it, reasons included: "these
    lines, with these authorised, for these stated reasons" is one decision,
    and changing any part after it was shown makes the confirm describe
    something else. *selected*: the IDs of the lines chosen for removal (Mode
    B), folded in only when there are any, so every hash without a removal
    is unchanged. *declared*: the effects a person declared, each with its reason (C506
    phase 3), folded in the same way: what verify will expect is part of what was confirmed."""
    body = {"commands": list(commands),
            "authorised": sorted((a["line"], a["reason"]) for a in normalise(authorisations))}
    if selected:
        body["removal_ids"] = sorted(selected)
    if declared:
        body["declared"] = sorted(json.dumps(d, sort_keys=True) for d in declared)
    payload = json.dumps(body, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
