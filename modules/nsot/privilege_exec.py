"""Intent's ``privilege_exec``: the reads a custom privilege level may run (the operator's
decision, 2026-11-13: not a parser view, which needs ``aaa new-model``, an AAA change with
lockout risk on every device; a custom privilege level instead, the read-only account at
privilege 3 with ``privilege exec level 3 <command>`` lines for exactly the reads that need it,
through intent and the template, previewed and approved by hash).

The read-only account at privilege 1 was refused eight of the AI's reads on an IOS-XE router
(measured 2026-11-13, `scripts/nmas-read-account-probe`): the two telemetry reads at the word
``telemetry``, and ping's and traceroute's at their first option after the address. IOS and
IOS-XE move a command to a level with one global line each, which this key holds::

    privilege_exec:
    - {level: 3, command: show telemetry ietf subscription, all: false}
    - {level: 1, command: show, all: false}

renders, at top level before the ``username`` lines (`_common.j2`'s ``privilege_exec``)::

    privilege exec level 3 show telemetry ietf subscription
    privilege exec level 1 show

**What a line may name is an allowlist, exactly the AI read set's forms** (`forms`, read from
`modules.ai.router_reads.SHAPES`: one home), never a resemblance:

- the **level** is 2 to 14. Level 15 holds every command already, and a line at 0 or 15
  changes what every account may run, so it is never written here;
- **level 1 only as a restore** (the operator, 2026-11-13: "Let level 1 through intent only for
  a leading word of an entry held at a higher level (here just `show`)"). A line for a command
  of several words moves its leading words with it (Cisco's command reference, ``privilege``),
  so ``privilege exec level 3 show telemetry ietf subscription`` raises ``show`` itself to 3
  and every account below 3 loses every ``show`` command; ``privilege exec level 1 show`` puts
  that one word back. A level-1 entry is held only when its command is the leading words (never
  the whole words of a read, never with ``all``) of another entry the same intent holds at 2
  to 14 (`restore_problem`); alone, for ``ping`` or ``traceroute``, or leading nothing held,
  it is refused by name. The render writes every higher line first and the level-1 lines
  after them, whatever their order in intent (`ordered`): the device raises the leading words
  when it takes the higher line, so the restore sent before it would be undone;
- the **command** is the fixed words of a device state read of the AI read set (``show telemetry
  ietf subscription``, ``show ip route``, ``ping``, ``traceroute ipv6``), or the leading words
  of one (``show``, ``show telemetry``): the device prints a line for each leading word of a
  command it moved (Cisco's command reference, ``privilege``: setting ``show ip route`` sets
  ``show`` and ``show ip`` to that level too), so a capture's lines round-trip. Whole words in
  lower case, as the device prints them: an abbreviation would never read back;
- **all** (the line's ``all`` keyword: every option under the command moves with it) only on a
  read's whole fixed words, never on leading words alone: ``all`` on ``show`` would lower every
  ``show`` command, ``show running-config`` among them;
- **never** ``configure``, ``debug``, ``clear``, ``write``, ``copy``, ``reload``, ``enable`` or
  any verb but ``show``, ``ping`` and ``traceroute``; never the configuration class's
  ``show running-config``, nor a form the AI read set leaves out on purpose
  (`router_reads.LEFT_OUT`). Each refusal names the entry, the word and what it was compared
  with (`problem`).

**The parser models a line only when it is one this key may hold and renders back exactly**
(`parse_line`, then `settled` once every line is read: a level-1 line is judged against the
others the config holds); any other ``privilege`` line (another mode, another verb, level 15, a
level-1 line that restores nothing held) stays unmodelled, verbatim, as before. So what a
device already holds is recorded as it is, and nothing this key could not have written is ever
sent from it.

**One entry per command, never text**, so an action can write the key for many devices at once
through the intent editor: `with_entries` gives a document the entries it lacks (a second run
adds nothing; a command held at another level is refused, never changed in passing), and
`hostvars.with_read_account` gives it the account's ``users`` entry at a privilege.

**The read-only account's lines are data here** (`read_account_lines`: the operator's approved
set of 2026-11-13, per config dialect, each line with what it does to every other account), so
a preview and an "Add the read-only account" action write one set and say one thing: on
IOS-XE the telemetry line and the level-1 ``show`` restore; on IOS nothing (not measured
there). Ping and traceroute are **not** in it by default: their two ``all`` lines join only
under the installation choice "Let the read-only account ping and traceroute"
(`router_reads.PING_CHOICE`, off by default), and say that they remove ping and traceroute
from levels 0 to 2 for every account on the device.

**What a line does to other accounts** is the device's, not this module's: a line moves a
command for every account of the device. Lowering a level-15 form to 3 takes nothing from
anyone; a line whose command, or a leading word of it, was level 1 (``show``, ``ping``,
``traceroute``) raises it, and an account below the line's level loses it unless a level-1
line restores the word.

IPv6: nothing here parses or compares an address. The IPv6 read forms (``ping ipv6``,
``traceroute ipv6``, ``show ipv6 route``) are forms of the allowlist like the IPv4 ones.
"""

import re

#: The levels a line may name.
LOW, HIGH = 2, 14
#: The level a restore names: where every account starts, held only for the leading words of
#: an entry held at `LOW` to `HIGH` (`restore_problem`).
RESTORE = 1
#: The read-only account's level (the operator's decision, 2026-11-13: privilege 3).
READ_ACCOUNT_LEVEL = 3
#: An entry's keys (`hostvars.INTENT_SECTIONS`' ``privilege_exec[]``).
KEYS = ("level", "command", "all")
#: The verbs a read begins with (`read_loop`'s rule for the ``cli`` transport).
READ_VERBS = ("show", "ping", "traceroute")
#: A modelled line, as the device prints it: single spaces, the optional ``all`` before ``level``.
_LINE = re.compile(r"^privilege exec (?P<all>all )?level (?P<level>[0-9]{1,2}) (?P<command>\S.*)$")
_WORD = re.compile(r"[a-z0-9][a-z0-9-]{0,40}\Z")


def forms() -> dict:
    """``{command: whole}``: every command a line may name. The fixed words of each device
    state read of the AI read set (up to its first argument) are *whole* (True); each shorter
    run of its leading words is a form too (False unless it is another read's whole words).
    The configuration class's reads are not in it."""
    from modules.ai import router_reads

    out = {}
    for _name, send, _args, _against, cls, _words in router_reads.SHAPES:
        if cls is not None:
            continue
        fixed = []
        for word in send.split():
            if word.startswith("{"):
                break
            fixed.append(word)
        for n in range(1, len(fixed) + 1):
            command = " ".join(fixed[:n])
            out[command] = out.get(command, False) or n == len(fixed)
    return out


def _listed(items, most: int = 6) -> str:
    items = [f"`{i}`" for i in items]
    if not items:
        return "none"
    shown = items[:most] + ([f"{len(items) - most} more"] if len(items) > most else [])
    return shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " and " + shown[-1]


def _command_problem(command: str, whole_wanted: bool) -> str:
    from modules.ai import router_reads

    words = command.split()
    verb = words[0] if words else ""
    if verb.lower() not in READ_VERBS:
        return (f"`{command}` is not a read: `{verb}` is never moved to a level through intent "
                f"(a line names a read of the AI read set, beginning "
                f"{', '.join(READ_VERBS[:-1])} or {READ_VERBS[-1]})")
    if " ".join(words) != command or not all(_WORD.match(w) for w in words):
        return (f"{command!r} is not a command as the device prints it: whole words in lower "
                "case, one space between them")
    for left, reason in router_reads.LEFT_OUT:
        if tuple(words[:len(left)]) == tuple(left):
            return (f"`{command}` is left out of the AI read set on purpose ({reason}), so no "
                    "line moves it")
    known = forms()
    if command not in known:
        for _name, send, _args, _against, cls, _words in router_reads.SHAPES:
            if cls is not None and send.split()[:len(words)] == words:
                return (f"`{command}` is the {cls} class's read, never the read-only "
                        "account's: no line moves it")
        same = sorted(c for c in known if c.split()[0] == verb and known[c])
        return (f"`{command}` is not one of the AI read set's forms beginning `{verb}` (they "
                f"are {_listed(same)})")
    if whole_wanted and not known[command]:
        under = sorted(c for c in known if known[c] and c.startswith(command + " "))
        return (f"`all` on `{command}` would move every command under it, not the AI's reads "
                f"alone: `all` is for a read's whole words ({_listed(under)})")
    return ""


def _restore_shape_problem(entry: dict) -> str:
    """Why a level-1 *entry* could restore nothing whatever else is held, or ``""``: its
    command is a form's leading words, never a read's whole words, and it has no ``all``."""
    command = entry["command"]
    why = _command_problem(command, False)
    if why:
        return why
    if entry.get("all", False):
        return (f"`all` at level {RESTORE} on `{command}` would open every command under it to "
                f"every account: a level-{RESTORE} line restores one leading word, never the "
                "commands under it")
    if forms()[command]:
        return (f"level {RESTORE} on `{command}`: it is a read's whole words, and level "
                f"{RESTORE} is held only for the leading words of an entry held at {LOW} to "
                f"{HIGH} (a word that line raised for every account); a read is never opened "
                f"to level {RESTORE}")
    return ""


def restore_problem(entry: dict, held) -> str:
    """Why the level-1 *entry* is not a restore *held* (the other entries of the same intent)
    gives a reason for, or ``""``: its command is the leading words of an entry held at 2 to
    14, itself one the key may hold. Names the command and what it was compared with."""
    why = _restore_shape_problem(entry)
    if why:
        return why
    command = entry["command"]
    # `problem(e)` with nothing held: a level-1 entry leads nothing (it restores nothing by
    # itself), so only an entry at 2 to 14 that the key may hold counts.
    leads = [e for e in held or () if isinstance(e, dict)
             and isinstance(e.get("command"), str) and e["command"].startswith(command + " ")
             and not problem(e)]
    if not leads:
        return (f"level {RESTORE} on `{command}` restores nothing: no entry of this intent at "
                f"level {LOW} to {HIGH} begins `{command} ` (level {RESTORE} is held only for "
                "the leading words of an entry held at a higher level, which that line raised "
                "for every account)")
    return ""


def problem(entry, held=()) -> str:
    """Why *entry* is not one ``privilege_exec`` may hold, or ``""``. Names the value and what
    it was compared with. *held*: the other entries of the same intent, which a level-1 entry
    is judged against (`restore_problem`); with none given, a level-1 entry restores nothing."""
    if not isinstance(entry, dict):
        return f"{entry!r} is not a mapping of level, command and all"
    extra = sorted(str(k) for k in entry if k not in KEYS)
    if extra:
        return f"it holds {', '.join(repr(k) for k in extra)}, and an entry holds {', '.join(KEYS)}"
    level = entry.get("level")
    if isinstance(level, bool) or not isinstance(level, int):
        return f"level {level!r} is not a whole number, {LOW} to {HIGH}"
    if level != RESTORE and not LOW <= level <= HIGH:
        return (f"level {level} is not {LOW} to {HIGH}: 15 holds every command already, and a "
                "line at 0 or 15 changes what every account may run")
    command = entry.get("command")
    if not isinstance(command, str) or not command:
        return f"command {command!r} is not a command"
    every = entry.get("all", False)
    if not isinstance(every, bool):
        return f"all {every!r} is not true or false"
    if level == RESTORE:
        return restore_problem(entry, held)
    return _command_problem(command, every)


def ordered(entries) -> list:
    """*entries* in the order they are rendered and sent: every line at 2 to 14 first, in
    their own order, then the level-1 restores, in theirs. The device raises a command's
    leading words when it takes the higher line, so a restore sent before it would be undone."""
    entries = list(entries or [])
    return ([e for e in entries if not (isinstance(e, dict) and e.get("level") == RESTORE)]
            + [e for e in entries if isinstance(e, dict) and e.get("level") == RESTORE])


def settled(entries) -> tuple:
    """``(kept, dropped)`` for the entries a parser read from one config (`parse_line`, each
    one's own shape already held): *kept* in render order (`ordered`), *dropped* the indexes
    of the level-1 entries that restore nothing the config holds and of a command's second
    line, which stay unmodelled."""
    entries = list(entries or [])
    dropped, seen = [], set()
    for n, e in enumerate(entries):
        # A command a config names twice is modelled once, by its first line: the key holds
        # one line for a command, and the second stays unmodelled where it stood.
        if problem(e, entries[:n] + entries[n + 1:]) or e["command"] in seen:
            dropped.append(n)
        else:
            seen.add(e["command"])
    return ordered(e for n, e in enumerate(entries) if n not in dropped), dropped


def problems(host_vars) -> list:
    """``[message]`` for intent's ``privilege_exec``: each entry that is not one it may hold
    (`problem`, a level-1 entry judged against the others), and a command named twice (two
    lines for one command, where the device keeps the later). ``[]`` when there is none, or no
    key."""
    doc = host_vars if isinstance(host_vars, dict) else {}
    held = doc.get("privilege_exec")
    if held in (None, []):
        return []
    if not isinstance(held, list):
        return [f"privilege_exec is {type(held).__name__}, and it is a list of entries, each "
                f"{', '.join(KEYS)}"]
    out, seen = [], {}
    for n, entry in enumerate(held):
        why = problem(entry, held[:n] + held[n + 1:])
        if why:
            out.append(f"privilege_exec[{n}]: {why}")
            continue
        first = seen.setdefault(entry["command"], (n, entry["level"]))
        if first[0] != n:
            out.append(f"privilege_exec[{n}] names `{entry['command']}` (level "
                       f"{entry['level']}), which privilege_exec[{first[0]}] names already "
                       f"(level {first[1]}): one line for a command, since the device keeps "
                       "the later of two")
    return out


def with_entries(host_vars: dict, entries) -> tuple:
    """``(document, added)``: *host_vars* (a copy; the caller's is never changed) holding each
    of *entries* it does not hold already, in their order after its own, and the entries
    added. What an action that gives a level its reads on one device, or on many, writes: one
    structured entry per command, never text, so the same call serves every device and the
    result goes through the intent editor's preview and commit like any edit. An entry the
    document holds exactly is not added again (a second run changes nothing). ValueError,
    naming both levels, when the document holds the command at another level or with another
    ``all`` (a held line is never changed in passing), or when an entry is not one the key may
    hold (`problem`, a level-1 restore judged against the document as it would then stand).
    The result is in render order (`ordered`: the restores after the lines they follow)."""
    doc = dict(host_vars or {})
    held = [dict(e) for e in doc.get("privilege_exec") or [] if isinstance(e, dict)]
    by_command = {e.get("command"): e for e in held}
    added = []
    for entry in entries or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("command"), str):
            raise ValueError(problem(entry) or f"{entry!r} is not an entry")
        want = {"level": entry.get("level"), "command": entry["command"],
                "all": entry.get("all", False)}
        have = by_command.get(want["command"])
        if have is None:
            held.append(want)
            by_command[want["command"]] = want
            added.append(want)
        elif (have.get("level"), bool(have.get("all", False))) != (want["level"], want["all"]):
            raise ValueError(
                f"`{want['command']}` is held already as `{render_line(have)}`, and this would "
                f"add `{render_line(want)}`: one line for a command, and a held line is "
                "changed by an edit of its own, never in passing")
    for want in added:
        why = problem(want, [e for e in held if e is not want])
        if why:
            raise ValueError(why)
    if added:
        doc["privilege_exec"] = ordered(held)
    return doc, added


def render_line(entry: dict) -> str:
    """The line *entry* renders, as `_common.j2`'s ``privilege_exec`` writes it (a test holds
    the two equal)."""
    return (f"privilege exec {'all ' if entry.get('all') else ''}level {entry['level']} "
            f"{entry['command']}")


def parse_line(line: str):
    """The entry a device's *line* is, ``{"level", "command", "all"}``, or None when it is not
    one this key may hold and render back exactly: such a line stays unmodelled, verbatim. A
    level-1 line is returned when its own shape could be a restore; whether it restores
    anything the config holds is `settled`'s, once every line is read."""
    m = _LINE.match(line or "")
    if not m:
        return None
    entry = {"level": int(m.group("level")), "command": m.group("command"),
             "all": bool(m.group("all"))}
    why = (_restore_shape_problem(entry) if entry["level"] == RESTORE else problem(entry))
    if why or render_line(entry) != line:
        return None
    return entry


#: The config dialects the read-only account's lines were measured on, and when (the read-only
#: account probe at privilege 1, an IOS-XE router, 2026-11-13). A dialect not here gets no line.
MEASURED = {"cisco_iosxe": "2026-11-13"}


def read_account_lines(dialect: str, level: int = READ_ACCOUNT_LEVEL, *,
                       ping_traceroute: bool = None) -> list:
    """The lines the read-only account's level needs on a device of *dialect*, in render
    order: ``[{"entry", "effect"}]``, *effect* what the line does to every other account of
    the device, in words a preview states. The operator's approved set (2026-11-13):

    - on a dialect the need was measured on (`MEASURED`): the telemetry line at *level*, then
      the level-1 restore of ``show``, its leading word;
    - ping's and traceroute's ``all`` lines only when *ping_traceroute* (None reads the
      installation choice, `router_reads.ping_traceroute_on`; off by default), each saying
      that it removes the command from levels 0 to 2 for every account;
    - on any other dialect: nothing (not measured there, and never guessed)."""
    from modules.ai import router_reads

    if dialect not in MEASURED:
        return []
    if ping_traceroute is None:
        ping_traceroute = router_reads.ping_traceroute_on()
    top = f"{level} to {HIGH}"
    out = [
        {"entry": {"level": level, "command": "show telemetry ietf subscription", "all": False},
         "effect": (f"levels {top} gain `show telemetry ietf subscription`; no level loses "
                    "anything by the line itself, but the device raises its leading word "
                    f"`show` to {level} with it, which the next line puts back")},
        {"entry": {"level": RESTORE, "command": "show", "all": False},
         "effect": (f"puts `show` back at level {RESTORE}, where it was: levels 0 to "
                    f"{level - 1} keep every show command they had; only `show telemetry ietf "
                    f"subscription` (and its leading words `show telemetry` and `show "
                    f"telemetry ietf`) sits at {level}")},
    ]
    if ping_traceroute:
        for command in ("ping", "traceroute"):
            out.insert(len(out) - 1, {
                "entry": {"level": level, "command": command, "all": True},
                "effect": (f"levels {top} gain every option of {command}, IPv4 and IPv6; it "
                           f"REMOVES {command} from levels 0 to {level - 1} for every account "
                           f"on the device, the plain `{command} <address>` too (the "
                           f"installation choice \"{router_reads.PING_CHOICE}\")")})
    return out
