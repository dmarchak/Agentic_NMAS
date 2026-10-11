"""modules/dhcp_subnets.py — Kea's subnets as Mercury's (C529 step 5, board C's section 6; the
operator's decision, 2026-10-06: ONE careful host step, once, moves ALL of Kea's hand-written
subnets into Mercury's own files, previewed, Kea's running configuration compared before and
after so nothing a client sees changes; no per-subnet move and no new root helper).

**The move is text in, text out, per family.** Kea's main configuration's ``"subnet4": [ … ]``
(``"subnet6"``) array is moved VERBATIM, its comments, layout and each subnet's
``"reservations": <?include …?>`` (step 2's files, and ZTP's) kept, into Mercury's file
``<Kea's folder>/nmas/subnets4.json`` (``subnets6.json``), and the main file keeps one
``"subnet4": <?include "<that file>"?>`` in its place. Kea resolves a nested include (measured
on the host's kea-dhcp4 2.4.1 before this was relied on), so every subnet's reservations stay in
the files their writers own. Kea's resolved configuration is then the same, which the host step
proves by comparing `config-get` and every lease before and after.

Refused, naming what was found: a ``"subnet4"`` key found other than once, a value that is
not an array, and a ``"shared-networks"`` key (subnets inside one are not moved by this step).
"""

import logging
import os

log = logging.getLogger(__name__)

FILES = {"IPv4": ("subnet4", "subnets4.json"), "IPv6": ("subnet6", "subnets6.json")}


def subnets_file(main: str, family: str) -> str:
    """Mercury's file holding every subnet of *family*, beside Kea's configuration."""
    return os.path.join(os.path.dirname(main), "nmas", FILES[family][1])


def _skip(text: str, i: int) -> int:
    """The index after a string, a comment or an include directive starting at *i*; *i* when
    none starts there."""
    if text.startswith('"', i):
        j = i + 1
        while j < len(text):
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == '"':
                return j + 1
            j += 1
        raise ValueError("a string is not closed")
    if text.startswith("//", i) or text.startswith("#", i):
        j = text.find("\n", i)
        return len(text) if j < 0 else j + 1
    if text.startswith("/*", i):
        j = text.find("*/", i + 2)
        if j < 0:
            raise ValueError("a /* comment is not closed")
        return j + 2
    if text.startswith("<?", i):
        j = text.find("?>", i + 2)
        if j < 0:
            raise ValueError("a <? directive is not closed")
        return j + 2
    return i


def _keys(text: str, key: str) -> list:
    """Where ``"<key>"`` appears as a KEY (followed by a colon) outside comments and other
    strings: ``[(start of the key, index just after its colon)]``."""
    out, i, quoted = [], 0, f'"{key}"'
    while i < len(text):
        j = _skip(text, i)
        if j != i:
            if text.startswith(quoted, i) and j == i + len(quoted):
                k = j
                while k < len(text) and text[k] in " \t\r\n":
                    k += 1
                if k < len(text) and text[k] == ":":
                    out.append((i, k + 1))
            i = j
            continue
        i += 1
    return out


def _array_end(text: str, i: int) -> int:
    """*i* at a ``[``: the index of its matching ``]``."""
    depth = 0
    while i < len(text):
        j = _skip(text, i)
        if j != i:
            i = j
            continue
        c = text[i]
        if c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("an array is not closed")


def move_plan(main_text: str, main: str, family: str) -> dict:
    """The move for one family: ``{"state": "move"|"done"|"refused", "refused", "subnets_text",
    "candidate", "file"}``. *subnets_text* is the array exactly as Kea's file holds it;
    *candidate* is Kea's file with the array replaced by the include of Mercury's file."""
    key, _f = FILES[family]
    path = subnets_file(main, family)
    out = {"state": "refused", "refused": "", "subnets_text": "", "candidate": main_text,
           "file": path}
    try:
        if _keys(main_text, "shared-networks"):
            out["refused"] = (f"{main} has a \"shared-networks\" key: subnets inside a shared "
                              "network are not moved by this step")
            return out
        hits = _keys(main_text, key)
        if len(hits) != 1:
            out["refused"] = f'"{key}" is found {len(hits)} times as a key in {main}; expected once'
            return out
        _k, after = hits[0]
        i = after
        while i < len(main_text) and main_text[i] in " \t\r\n":
            i += 1
        include = f'<?include "{path}"?>'
        if main_text.startswith(include, i):
            out.update(state="done")
            return out
        if not main_text.startswith("[", i):
            out["refused"] = (f'"{key}" in {main} is not an array (it starts '
                              f"{main_text[i:i + 30]!r}); expected [ … ] or the include of "
                              f"{path}")
            return out
        end = _array_end(main_text, i)
    except ValueError as exc:
        out["refused"] = f"{main} could not be read as Kea's configuration: {exc}"
        return out
    out.update(state="move", subnets_text=main_text[i:end + 1] + "\n",
               candidate=main_text[:i] + include + main_text[end + 1:])
    return out
