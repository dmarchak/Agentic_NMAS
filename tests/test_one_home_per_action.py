"""Minimalism at the EFFECT level: every device-changing command has ONE
implementation (NSOT_STAGE7_PLAN section 6a, the operator's rule, 2026-09-27).

"No function appears in two places." Acting on many devices and acting on one
are different tasks, so the selection and the Device page may both offer an
action, but only THROUGH THE SAME COMPONENT: two entry points into one code
path, never two code paths. Two implementations of one effect is how they
come to differ (one holds the device and the other does not; one masks and
the other does not).

The population is C101's command-string scan (`_writer_sites`): every command
string the program sends that the read-only allowlist refuses. A command is
keyed on its verb and the KIND of each operand (a file, TFTP, the running or
startup config), so `delete {fs}{name}` and `delete flash:{name}` are one
effect. A send with no resolvable text is a prompt's answer when an earlier
send in the same function is a command, and otherwise must be DECLARED below
(a person's typed command, rotation's own program), because the scan cannot
know what it sends.

What this cannot see, stated so it is not read as seen: whether two
DIFFERENT effects serve one task (the Configure forms and the intent editor),
and duplicated VIEWS. Section 6a names both. The route level (which controls
send a route) is measured there and is not a test, because a control's call
graph needs a JavaScript parser this project does not have.
"""

import ast
import re

from tests.test_session_write_guard import _writer_sites

#: Sends whose text the scan cannot resolve, declared by the task they serve.
DECLARED_DYNAMIC = {
    ("modules/commands.py", "run_device_command"): ("typed",),
    ("modules/bulk_ops.py", "_run_single_enable_command"): ("typed",),
    ("modules/nsot/credential_rotation.py", "push_rotation"): ("rotation",),
}

#: Measured 2026-09-27 (section 6a's retroactive pass). Each effect with more
#: than one implementation, and exactly which. This list only SHRINKS: 7.3
#: merges each into one.
KNOWN_DUPLICATES = {
    ("write", "memory"): {"app.py:save_config", "modules/backups.py:save_running_to_startup"},
    ("delete", "file"): {"app.py:delete_file", "modules/bulk_ops.py:_execute_delete_file"},
    ("copy", "file", "tftp"): {"app.py:download_device_file",
                               "modules/bulk_ops.py:_execute_tftp_download"},
    ("copy", "tftp", "file"): {"app.py:upload_file", "modules/bulk_ops.py:_execute_tftp_upload"},
    ("typed",): {"modules/commands.py:run_device_command",
                 "modules/bulk_ops.py:_run_single_enable_command"},
}

_COMMAND = re.compile(r"^[a-z][a-z-]*\b")


def _text(arg, func):
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "X" for v in arg.values)
    if isinstance(arg, ast.Name) and func is not None:
        values = [n.value for n in ast.walk(func) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == arg.id for t in n.targets)]
        if len(values) == 1:
            return _text(values[0], func)
    return None


def _kind(word: str) -> str:
    if word.startswith("tftp:"):
        return "tftp"
    if word.startswith(("running-config", "system:running-config")):
        return "running"
    if word.startswith(("startup-config", "nvram:startup-config")):
        return "startup"
    return "file"


def effect(text: str) -> tuple:
    """A command's effect: its verb and the kind of each operand."""
    words = text.split()
    if words[0] == "copy":
        return ("copy",) + tuple(_kind(w) for w in words[1:3])
    if words[0] == "delete":
        return ("delete", "file")
    if words[0] == "write":
        return tuple(words[:2])
    return (words[0],)


def implementations() -> dict:
    """{effect: {"file:outermost function"}} over every device-writing send."""
    by_func = {}
    for rel, chain, text, line in _writer_sites():
        inner = chain[0] if chain else None
        call = next((n for n in ast.walk(inner) if isinstance(n, ast.Call)
                     and n.lineno == line), None) if inner is not None else None
        resolved = _text(call.args[0], inner) if call is not None and call.args else text
        outer = chain[-1].name if chain else "<module>"
        by_func.setdefault((rel, outer), []).append((line, resolved))
    out = {}
    for (rel, outer), sends in by_func.items():
        seen_command = False
        for line, resolved in sorted(sends, key=lambda s: s[0]):
            if resolved is not None and _COMMAND.match(resolved.strip()):
                seen_command = True
                out.setdefault(effect(resolved.strip()), set()).add(f"{rel}:{outer}")
            elif not seen_command:
                declared = DECLARED_DYNAMIC.get((rel, outer))
                assert declared, (
                    f"{rel}:{line} ({outer}) sends a command this scan cannot "
                    "resolve and no command precedes it, so it is not a prompt's "
                    "answer. Declare the task it serves in DECLARED_DYNAMIC.")
                out.setdefault(declared, set()).add(f"{rel}:{outer}")
    return out


def test_the_scan_finds_something():
    found = implementations()
    assert len(found) >= 8, sorted(found)
    # Positive anchors: a single implementation, and the known duplicate.
    assert found[("reload",)] == {"app.py:bulk_reload"}
    assert found[("write", "memory")] == KNOWN_DUPLICATES[("write", "memory")]


def test_every_device_changing_effect_has_one_implementation():
    dup = {k: v for k, v in implementations().items() if len(v) > 1}
    new = {k: sorted(v) for k, v in dup.items() if v != KNOWN_DUPLICATES.get(k)}
    assert not new, (
        "An effect has more than one implementation. Acting on many devices "
        "and on one may both be offered, but through ONE component "
        f"(NSOT_STAGE7_PLAN section 6a): {new}")


def test_the_known_duplicates_only_shrink():
    found = implementations()
    ghosts = sorted(str(k) for k, v in KNOWN_DUPLICATES.items()
                    if len(found.get(k, ())) < 2)
    assert not ghosts, (
        f"No longer duplicated, so remove from KNOWN_DUPLICATES: {ghosts}")


def test_every_declared_dynamic_send_exists():
    senders = {(rel, chain[-1].name) for rel, chain, _t, _l in _writer_sites() if chain}
    ghosts = sorted(k for k in DECLARED_DYNAMIC if k not in senders)
    assert not ghosts, f"Declared but no longer sending: {ghosts}"


def test_operands_are_keyed_by_kind_not_by_spelling():
    """The page's `delete {fs}{name}` and the selection's `delete flash:{name}`
    are one effect; keying on text would have hidden the duplicate."""
    assert effect("delete XX") == effect("delete flash:X")
    assert effect("copy XX tftp:") == effect("copy flash: tftp:")
    assert effect("copy tftp: X") == effect("copy tftp: flash:")
    assert effect("copy running-config tftp:") != effect("copy startup-config tftp:")
