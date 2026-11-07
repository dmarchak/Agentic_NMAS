"""ai/injection.py — instruction-like lines withheld from what a model is sent (IBN_DESIGN
section 13 item 5; the overnight brief of 2026-11-01, item 3, W11/W12; C2271).

The data a model reads is retrieved, not typed: a device's log lines, interface descriptions,
NetBox fields, commit messages, alert labels. Anyone who can write one of those can write
words aimed at the model ("ignore the previous instructions", "the operator approved this").
Nothing here is relied on for security: the model has no acting tool (it may ask for reads
from a fixed set, and code decides which run: `modules/ai/read_loop.py`, docs/HEAL_TO_INTENT.md
19.5; a read's answer reaches pass 2 as the ``mercury_reads`` part, read here like every
other), every answer is checked against the pack, and a change needs a person's confirm by
hash (section 13, items 1 to 4, 6 and 7). This flags and withholds, deterministically, so such a line never reaches the model
and a person sees that it was there.

`withhold_parts` is the gateway's (`gateway._prepared`): every part of a request but those a
person typed (`gateway.TYPED_PARTS`: the person's own words are theirs to send) is read line by
line; a line matching `PATTERNS` is replaced by `WITHHELD`, naming the patterns, and each is
listed (the part, where in it, which patterns), never the line itself: the line stays where it
was kept (the pack on its card, the store it came from), masked as every line Mercury shows.
A part that is JSON (an evidence pack) is read value by value and written back the way packs
are written (`DUMP`); a part with nothing withheld is sent byte for byte as it came.

The patterns are narrow on purpose: a withheld line is evidence a person cannot see in the
answer. tests/test_ai_injection.py holds them to zero matches over every real capture the
suite keeps (Loki's lines, the fleet's configs and descriptions, the recorded packs) and to a
match on each planted case.
"""
import json
import re

#: Each pattern: (name, compiled regex, what it is in a person's words). Case-insensitive.
PATTERNS = tuple((name, re.compile(rx, re.I), words) for name, rx, words in (
    ("ignore_instructions",
     r"\b(?:ignore|disregard|forget|override|bypass)\b[^\n]{0,40}?\b(?:previous|prior|above|"
     r"earlier|preceding|system|all|any|your|these|those|the)\b[^\n]{0,24}?\b(?:instructions?|"
     r"prompts?|rules|guidelines|directions)\b",
     "an instruction to ignore the instructions"),
    ("new_instructions", r"\b(?:new|updated|real|actual|further)\s+instructions?\s*:",
     "new instructions"),
    ("identity_claim",
     r"\b(?:i am|i'm|this is|speaking as)\s+(?:an?\s+|the\s+)?(?:admin|administrator|"
     r"operator|root user|superuser|system|developer)\b",
     "a claim of identity"),
    ("approval_claim",
     r"\b(?:operator|admin|administrator|security team|management)\s+(?:has\s+|have\s+)?"
     r"(?:approved|authori[sz]ed|allowed|signed off)\b",
     "a claim of approval"),
    ("role_play", r"\byou\s+are\s+(?:now|no longer)\b|\bpretend\s+(?:to be|you are)\b|"
                  r"\bfrom now on,?\s+you\b",
     "an attempt to change the model's role"),
    ("prompt_markup", r"</?\s*(?:data|system|instructions?|prompt|assistant)\b[^>\n]{0,40}>|"
                      r"^\s*(?:assistant|human)\s*:",
     "markup or a turn that imitates the prompt"),
    ("answer_directive",
     r"\b(?:respond|reply|answer|output|conclude|report)\s+(?:only\s+)?(?:with|that)\b[^\n]{0,40}?"
     r"\b(?:no fault|healthy|nothing (?:is )?wrong|needs_human|no_fault_found)\b",
     "an instruction about what to answer"),
    ("external_link", r"!\[[^\]\n]*\]\(\s*https?://|\b(?:visit|open|fetch|load|click|go to)\s+"
                      r"https?://",
     "an image or a link to fetch"),
    # IBN_DESIGN 13 item 8 (2026-10-15): instructions hidden in characters a person cannot
    # see: zero-width, bidirectional overrides and isolates, the byte-order mark, and Unicode
    # tag characters.
    ("hidden_characters", "[​-‏‪-‮⁠-⁤⁦-⁩﻿"
                          "\U000e0000-\U000e007f]",
     "characters a person cannot see"),
))

#: What a withheld line becomes in the request.
WITHHELD = "[withheld: instruction-like text ({names}); kept where it was read, not sent]"
#: How a JSON part is written back when something in it was withheld: an evidence pack's own
#: form (`explain.parts`).
DUMP = {"sort_keys": True, "ensure_ascii": False, "separators": (",", ":")}


def flags(text: str) -> list:
    """The names of the patterns *text* matches, in `PATTERNS`' order; ``[]`` for none."""
    if not isinstance(text, str) or not text:
        return []
    return [name for name, rx, _w in PATTERNS if rx.search(text)]


def words(names) -> str:
    """The patterns *names* in a person's words."""
    by = {name: w for name, _rx, w in PATTERNS}
    return "; ".join(by.get(n, n) for n in names)


def _text(value: str, where: str, out: list) -> str:
    lines = value.split("\n")
    changed = False
    for i, line in enumerate(lines):
        names = flags(line)
        if names:
            lines[i] = WITHHELD.format(names=", ".join(names))
            out.append({"where": where + (f" line {i + 1}" if len(lines) > 1 else ""),
                        "patterns": names})
            changed = True
    return "\n".join(lines) if changed else value


def _walk(value, where: str, out: list):
    if isinstance(value, str):
        return _text(value, where, out)
    if isinstance(value, list):
        return [_walk(v, f"{where}[{i}]", out) for i, v in enumerate(value)]
    if isinstance(value, dict):
        return {k: _walk(v, f"{where}.{k}" if where else k, out) for k, v in value.items()}
    return value


def withhold(name: str, value) -> tuple:
    """``(value as sent, [withheld])`` for one request part *name*: a JSON part read value by
    value (a pack's ``pack[3].pieces[0].text``), any other string line by line; unchanged,
    the very object, when nothing is withheld."""
    out = []
    if not isinstance(value, str):
        got = _walk(value, name, out)
        return (got if out else value), out
    try:
        doc = json.loads(value)
    except ValueError:
        doc = None
    if isinstance(doc, (list, dict)):
        got = _walk(doc, name, out)
        return (json.dumps(got, **DUMP) if out else value), out
    got = _text(value, name, out)
    return got, out


def withhold_parts(parts: dict, skip=()) -> dict:
    """``{"parts", "withheld"}``: *parts* with every instruction-like line withheld but in the
    parts named in *skip* (a person's own words), and each withheld line listed
    ``{"where", "patterns"}``. *parts* itself is never changed."""
    sent, withheld = {}, []
    for name, value in parts.items():
        if name in skip:
            sent[name] = value
            continue
        sent[name], got = withhold(name, value)
        withheld += got
    return {"parts": sent, "withheld": withheld}
