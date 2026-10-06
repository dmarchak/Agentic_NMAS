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
    ("modules/commands.py", "_run"): ("typed",),
    ("modules/bulk_ops.py", "_run_single_enable_command"): ("typed",),
    ("modules/nsot/credential_rotation.py", "push_rotation"): ("rotation",),
}

#: Config-mode sends, by the task each serves: config mode is a CHANNEL, not an
#: effect, so a send is keyed by what it is for (C191, 2026-09-29, when the
#: population widened to config mode and the scripts).
CONFIG_TASKS = {
    ("modules/bulk_ops.py", "_execute_remove_static_routes"): ("config", "static route removal"),
    ("modules/bulk_ops.py", "_execute_worker"): ("config", "bulk config"),
    ("modules/pipeline.py", "_push_via_netmiko"): ("config", "deploy push"),
    ("modules/pipeline.py", "_restore_config"): ("config", "rollback"),
    ("modules/nsot/onboard.py", "remove_rw_communities"): ("config", "RW community removal"),
    # P.9 step (c): a PENDING device is in no inventory, so the deploy pipeline
    # cannot target it; phase 2 sends the confirmed profile program itself.
    ("modules/nsot/onboard.py", "send_profile_program"): ("config", "monitoring profile at onboarding"),
    ("scripts/nmas-removal-probe", "main"): ("config", "removal probe"),
}

#: Measured 2026-09-27 (section 6a's retroactive pass). Each effect with more
#: than one implementation, and exactly which. This list only SHRINKS: 7.3
#: merges each into one.
KNOWN_DUPLICATES = {
    # Widened 2026-09-29 (C191): the scan now counts Netmiko's save_config, and
    # found three more saves (after a push, after a rollback, onboarding's).
    # C103 (2026-09-29): Save Device Config and Save to Startup REMOVED, the
    # operator's decision: Persist is the one save a person reaches, and the two
    # that went could report success without proving it.
    # ("save_startup",) LEFT this list 2026-10-05 (C501): the push and the rollback no longer
    # save (the push saved before verify, so a failed change reached startup), and the
    # deploy's save after verify calls `persist_on_device`, the one home.
    ("delete", "file"): {"app.py:delete_file", "modules/bulk_ops.py:_execute_delete_file"},
    ("copy", "file", "tftp"): {"app.py:download_device_file",
                               "modules/bulk_ops.py:_execute_tftp_download"},
    ("copy", "tftp", "file"): {"app.py:upload_file", "modules/bulk_ops.py:_execute_tftp_upload"},
    ("typed",): {"modules/commands.py:_run",
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


#: Verbs IOS accepts by unique prefix; `wr` is write and `w` alone is not.
_VERBS = ("copy", "delete", "erase", "reload", "write", "clear", "configure")


def _verb(word: str) -> str:
    hits = [v for v in _VERBS if v.startswith(word)] if len(word) >= 2 else []
    return hits[0] if len(hits) == 1 else word


def _abbrev_of(word: str, full: str, floor: int = 3) -> bool:
    return len(word) >= floor and full.startswith(word)


def _kind(word: str) -> str:
    """An operand's KIND, as IOS reads it: `run`, `running-config` and
    `system:running-config` are one place; `start` and `nvram:startup-config`
    another. Keyed on spelling, `copy run start` read as a file-to-file copy
    and a third save went unseen (item 3, 2026-09-27)."""
    w = word.lower()
    if w.startswith("tftp:"):
        return "tftp"
    bare = w.split(":", 1)[1] if w.startswith(("system:", "nvram:")) else w
    if _abbrev_of(bare, "running-config"):
        return "running"
    if _abbrev_of(bare, "startup-config"):
        return "startup"
    return "file"


def effect(text: str) -> tuple:
    """A command's effect: what it does to the device, whatever the spelling.
    Saving the running config to startup is ONE effect however it is typed:
    `write memory`, `write`, `wr`, `write mem`, `copy running-config
    startup-config`, `copy run start`, `copy system:running-config
    nvram:startup-config`."""
    words = text.split()
    verb = _verb(words[0].lower())
    rest = [w.lower() for w in words[1:]]
    if verb == "write":
        if not rest or _abbrev_of(rest[0], "memory", 1):
            return ("save_startup",)
        if _abbrev_of(rest[0], "erase", 1):
            return ("erase_startup",)
        return ("write", rest[0])
    if verb == "copy":
        kinds = tuple(_kind(w) for w in rest[:2])
        if kinds == ("running", "startup"):
            return ("save_startup",)
        return ("copy",) + kinds
    if verb == "erase" and rest and (_kind(rest[0]) == "startup"
                                     or rest[0].startswith("nvram")):
        return ("erase_startup",)
    if verb == "delete":
        return ("delete", "file")
    return (verb,)


def implementations() -> dict:
    """{effect: {"file:outermost function"}} over every device-writing send."""
    by_func, _raw = {}, {}
    for rel, chain, text, line in _writer_sites():
        _raw.setdefault((rel, chain[-1].name if chain else "<module>"), []).append((line, text))
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
            text = next((t for l, t in _raw.get((rel, outer), []) if l == line), None)
            if text == "<save_config>":
                out.setdefault(("save_startup",), set()).add(f"{rel}:{outer}")
                continue
            if text and text.startswith("<"):
                task = CONFIG_TASKS.get((rel, outer))
                assert task, (f"{rel}:{line} ({outer}) sends in config mode: declare the "
                              "task it serves in CONFIG_TASKS")
                out.setdefault(task, set()).add(f"{rel}:{outer}")
                continue
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
    # Moved, still ONE home: bulk reload calls it (C153).
    assert found[("reload",)] == {"modules/device_reload.py:reload_device"}
    # The save to startup: ONE home since C501 (the deploy's save after verify calls it).
    assert found[("save_startup",)] == {"modules/nsot/onboard.py:persist_on_device"}


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


def test_one_save_however_it_is_spelled():
    """Item 3 (2026-09-27): `copy run start` was keyed as a file copy, and a
    third save written that way passed. Every spelling IOS accepts is one."""
    spellings = ["write memory", "write", "wr", "write mem", "wr mem",
                 "copy running-config startup-config", "copy run start",
                 "copy system:running-config nvram:startup-config",
                 "cop run sta"]
    assert {effect(s) for s in spellings} == {("save_startup",)}
    # And the distinctions stay: a reverse copy, an erase, a file copy.
    assert effect("copy start run") == ("copy", "startup", "running")
    assert effect("write erase") == effect("erase startup-config") == ("erase_startup",)
    assert effect("copy flash:x tftp:") == ("copy", "file", "tftp")
