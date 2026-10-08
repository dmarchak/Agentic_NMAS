"""Text a request supplies that becomes PART of a command sent to a device (C570).

A free-form command is judged whole by the read-only allowlist (`readonly_commands`). A
filename, a filesystem or a TFTP server typed into a form is not a command; it is spliced into
one (`delete {filesystem}{filename}`, `copy tftp: {filesystem}`, the answers to a copy's
prompts). Spliced, a line break in it is a second command the device runs ("x\\nreload"), and a
filename with a path writes the upload outside the TFTP root. So each such field is ONE token
of a known shape, checked before any device is asked, and refused naming the field, what it
held and the shape it must have.
"""

import re

#: field kind -> (pattern, the shape in words). Refusing by resemblance is safe: a value that
#: does not match is refused, never repaired.
SHAPES = {
    "filesystem": (re.compile(r"[A-Za-z0-9_-]{1,32}:\Z"),
                   "a filesystem name ending in a colon, such as flash: or bootflash:"),
    "filename": (re.compile(r"[A-Za-z0-9_+.-]{1,128}\Z"),
                 "one file name of letters, digits and . _ + - (no path, no spaces)"),
    "server": (re.compile(r"[A-Za-z0-9.:-]{1,253}\Z"),
               "an address or host name (letters, digits, . : -)"),
}


def refusal(value, kind: str, field: str = "") -> str:
    """``""`` when *value* is one token of *kind*'s shape, else why, naming the field."""
    pattern, words = SHAPES[kind]
    name = field or kind
    if value is None or value == "":
        return f"Refused: {name} is empty; it must be {words}."
    text = str(value)
    if not pattern.match(text) or text.strip(".") == "":
        shown = text.encode("unicode_escape").decode("ascii")[:80]
        return f"Refused: {name} {shown!r} is not {words}. Nothing was sent."
    return ""


def first_refusal(**fields) -> str:
    """The first refusal among ``name=(value, kind)`` pairs, or ``""``."""
    for name, (value, kind) in fields.items():
        why = refusal(value, kind, name)
        if why:
            return why
    return ""
