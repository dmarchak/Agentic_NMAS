"""Measure, on a real device, what the AI's read-only account may and may not run (C2657).

**One home** (board R's R8, provisional, operator review pending): this module is the probe.
`scripts/nmas-read-account-probe` is its command line (`main`), and Credentials' **Probe…**
(`modules/nsot/read_account_op.py`) is its Mercury operation; both plan, run and record through
the functions below. The record is kept by the device's identity (`record_dir`), never by its
name alone, and retirement removes it (`modules/nsot/retire.py`, ``probes``).

The AI's reads sign in to a device as its credential profile's read-only account
(`credentials.resolve_read`, through the reads engine's own `reads.read_account_for`), never the
deploy account, and never escalate (no ``enable``). C2657 adds that account to a device through
intent, at the privilege its ``users`` entry names (1, or a custom level whose reads intent's
``privilege_exec`` lines name, `modules/nsot/privilege_exec.py`). Before the AI relies on it,
this probe signs in AS that account, holding the device for the whole run, and asks:

  a. every AI read shape (`router_reads.SHAPES` of the device state class, the set the AI
     analysis and AI troubleshooting ask for, `fixit_reads.FAMILY`'s CLI reads), each argument
     filled from what Mercury holds and each request judged by the AI's own check
     (`read_loop.check`), so what is sent is what the AI would send: expected ANSWERED. A
     form that is another platform's on this device (`router_reads.other_platform`: a
     dialect's own form on the other dialect; spanning tree, a switch's read, on a device
     declared or measured to have no VLAN database) is never asked, and neither is a form
     the AI asks only under the installation choice "Let the read-only account ping and
     traceroute" while that choice is off (`router_reads.choice_off`: its sourced ping and
     its traceroute; the plain ping is asked either way). Each is listed with its reason;
  b. ``show running-config``: expected REFUSED (the configuration class's read, never the
     account's);
  c. ``configure terminal``: expected REFUSED. A configuration prompt in its answer is answered
     ``end`` at once, and the result is FAIL ("accepted: the account can configure");
  d. ``clear counters``: expected REFUSED. A ``[confirm]`` is answered ``n``, typed without
     Enter (never Enter, which confirms), and the result is FAIL; any other question is never
     answered: the run stops and the session is closed, abandoning it;
  e. ``debug ?``: NEVER a real debug command. It is typed WITHOUT Enter (a line left after the
     help would otherwise be sent), its answer read, and the session closed, which discards the
     line. A refusal is PASS; anything listed in its place (help) is FAIL;
  f. ``enable``, in a session of its own (the operator, 2026-11-13: "plus `enable` refused"):
     expected REFUSED. A ``Password:`` prompt is NEVER answered: the session is closed, which
     abandons it, and that is refused, PASS (the account holds no enable password, and the
     probe types none). A ``%`` error is refused, PASS. A privileged prompt with nothing asked
     (``#``, as a console with no enable secret answers) is FAIL; anything else is UNREADABLE.

**A session is closed with nothing typed** (`_abandon`): Netmiko's own close types Enter and
``exit`` first (its ``cleanup``), which at a ``Password:`` prompt, a question or a line left
after ``debug ?`` would be an answer. The probe's sessions close their transport only, so the
device receives exactly the program's lines and the two answers below.

**Refused is recognised only by the device's own refusal shapes** (`REFUSAL`): ``% Invalid input
detected`` (captured on both platforms, tests/fixtures/operational/*__show_foobar.txt),
``% Incomplete command`` and ``% Unrecognized command`` (`pipeline.IOS_ERROR_PATTERN`'s
family), ``% Unknown command or computer name`` (`console_profiles.REFUSAL_EXAMPLES`) and
``% Authorization failed`` (the operator's list, 2026-11-13; no capture of it yet). For b to e,
an answer is PASS only when its first line after the echo is one of them; a configuration
prompt, a ``[confirm]``, a listing or any other text is FAIL; nothing, or another ``%`` line, is
UNREADABLE (allowing by resemblance is not safe). For a, a refusal shape, or any line naming an
authorisation failure, is FAIL (refusing by resemblance is safe); ``% BGP not active``, whole
and alone, is ANSWERED (`NOT_RUNNING`: the read was accepted, the protocol is not running);
another device error is UNREADABLE; an answer with neither is ANSWERED.

**When the account misses a read, the record says which**, and the next proposal is ``privilege
exec level <n> <command>`` lines for exactly those reads at a custom level (2 to 14), through
intent's ``privilege_exec`` (the operator, 2026-11-13): never a parser view (it needs ``aaa
new-model``, an AAA change with lockout risk on every device) and never privilege 15.

**Preview, confirm by hash, record.** Without ``--confirm`` nothing connects: the preview names
the account (its name from the credential store and the profile `resolve_read` picks; never its
password), every command in the order it is sent, the shapes not measured and why, and the
program's hash (`deploy.command_fingerprint`: the commands, and as declared effects whom it signs
in as and the two answers it may type). ``--confirm <hash>`` runs exactly that program, and is
refused, naming both hashes, when the program has moved. The person running it is named
(``--actor``) and recorded. The record (JSON, every answer masked by `redact_text`, the
account's password added to the values masked) is written owner-only (`config.open_secure`)
under the data directory's ``probes/read-account/``. The password is read from the store at the
sign-in and never printed, logged or recorded.

**Refused before anything connects:** a run inside one of the installation's no-change windows
(`no_change_now`, the installation's own setting; the command line adds the lab's nightly
backup window, its own tooling's), and a device with no read-only account. Nothing here names a device: the
operator's choice of device is the run's.

    nmas-read-account-probe --network Default --device edge1                  # the preview
    nmas-read-account-probe --network Default --device edge1 --confirm <hash> \\
        --actor you@example.com

The arguments a shape needs default to what Mercury holds for the device (the first interface
its committed golden holds; its own first IPv4 and IPv6 addresses in committed intent; the first
BGP peer intent names; the first telemetry subscription intent declares); ``--interface``,
``--address``, ``--address6``, ``--peer``, ``--peer6``, ``--mac`` and ``--subscription`` name
others, each still judged by the AI's own check. **CDP's and LLDP's interface is one a
neighbour is cabled to**: the first interface of the golden that a cable plugs into
(`ifnames.cabled`) and that committed intent gives a neighbour on (`neighbours.link_interfaces`:
an OSPF or OSPFv3 adjacency's local interface, or one sharing a network with another
device's), never a loopback, which the device refuses for every account (measured
2026-11-13); ``--link-interface`` names another. A shape with no
argument to fill is NOT MEASURED, said why, which keeps the verdict from PASS.

Exit 0 the run finished (the verdict, PASS or not, printed and recorded), 1 refused before
anything connected, 2 the device does not accept the read-only account, 3 the run stopped on an
answer it would not decide (the session closed).
"""

import argparse
import contextlib
import json
import os
import re
import sys
import time

def no_change_now(now: float = None) -> str:
    """The installation's no-change window holding *now*, in its words, or ``""``
    (`change_windows`, the installation's own setting: nothing in the product names a lab's
    window). A probe is a measurement, and one taken inside a window the installation keeps
    free of changes (a nightly backup, a freeze) measures that instead, so it is refused then.
    The command line adds the lab's backup window of its own (`scripts/nmas-read-account-probe`)."""
    from modules import change_windows

    held = change_windows.holding(now)
    return change_windows.words(held, now) if held else ""

#: The device's own refusal shapes, each at a line's start (see the docstring for where each is
#: known from). Only these make a refused command PASS.
REFUSAL = re.compile(r"^%\s*(?:Invalid input detected|Incomplete command|Unrecognized command"
                     r"|Unknown command or computer name|Authorization failed)")
#: For a READ only: a line naming an authorisation failure, in any form, is a refusal too
#: (refusing by resemblance is safe; AAA command authorisation's words are not captured here).
AUTH_WORDS = re.compile(r"(?i)\bauthori[sz]ation failed\b")
#: For a READ only: the device's own answer, whole and alone, that the read was accepted and
#: its protocol is not running. An answer, never a refusal of the account: the command's own
#: code prints it, after the parser took the command at the account's privilege (measured on an
#: IOS-XE router running no BGP, 2026-11-13: both BGP summary reads, as the read-only account
#: at privilege 1). One exact line, never a resemblance; any other ``%`` line stays UNREADABLE.
NOT_RUNNING = re.compile(r"% BGP not active\Z")
#: A prompt line: a name, an optional mode in brackets, then ``#`` or ``>``.
PROMPT = re.compile(r"[A-Za-z0-9_.:/-]{1,64}(\([A-Za-z0-9_-]{1,32}\))?[#>]")
CONFIG_PROMPT = re.compile(r"\(config[A-Za-z0-9_-]{0,24}\)#\s*$")
CARET = re.compile(r"\^")

#: The commands expected refused of the read-only account, in the order they are sent, each
#: with how its answer is handled. ``bare``: typed without Enter. ``closes``: the session is
#: closed after it with nothing typed (`_abandon`), and the next step opens its own.
#: ``enable``: judged by `judge_enable` (a ``Password:`` prompt is never answered).
REFUSED = (
    {"key": "show-running-config", "command": "show running-config",
     "words": "the configuration class's read, never the account's"},
    {"key": "configure-terminal", "command": "configure terminal",
     "words": "a configuration prompt is answered `end` at once: FAIL"},
    {"key": "clear-counters", "command": "clear counters",
     "words": "a [confirm] is answered `n`, typed without Enter: FAIL"},
    {"key": "debug-help", "command": "debug ?", "bare": True, "closes": True,
     "words": "typed without Enter, read, then the session closed; a listing is FAIL"},
    {"key": "enable", "command": "enable", "enable": True, "closes": True,
     "words": "in its own session; a Password: prompt is never answered (the session is "
              "closed): refused; a privileged prompt with nothing asked is FAIL"},
)
#: The only two answers the probe ever types (send, read, decide).
END, NO = "end", "n"
#: The answers' declared effects, in the hash.
ANSWERS = {"configuration prompt": END, "[confirm]": NO + " (no Enter)"}
#: What the probe never answers, declared in the hash beside the answers.
NEVER_ANSWERED = ["Password:"]
#: The enable password's prompt, alone on the answer's last line.
PASSWORD_PROMPT = re.compile(r"Password:\s*\Z")
#: The AI check's request words (`read_loop._request_text`: one line, at most 200 characters).
WHY = "the read-only account probe (C2657): does the read-only account answer the AI's read"
#: A raw step's answer is read until the device has been quiet this long, up to RAW_WAIT
#: (tier 2's probe's reads, `nmas-tier2-probe`: 2 s quiet within 30 s).
RAW_QUIET, RAW_WAIT = 2.0, 30
PASS, FAIL, UNREADABLE, NOT_MEASURED = "PASS", "FAIL", "UNREADABLE", "NOT MEASURED"
SIGNIN_REFUSED = "SIGN-IN REFUSED"
#: A read the AI asks only under an installation choice that is off: listed, never sent, and
#: no part of the verdict (as another platform's form is not).
NOT_ASKED = "not asked"


# ---------------------------------------------------------------------------- the seams

def OPEN(params: dict):
    """A session signed in as *params*' login, never escalated (tests replace it)."""
    from modules.connection import open_ssh
    return open_ssh(params, plain=True, owner="probe:read-account")


def _inventory(network: str) -> dict:
    """``{hostname: device}``: the network's inventory, as the reads engine loads it."""
    from modules.device import load_saved_devices
    from modules.nsot import listref
    return {d.get("hostname"): d for d in load_saved_devices(listref.resolve(network).csv_path)}


def _committed(network: str, host: str) -> tuple:
    """``(intents, goldens)``: the committed stores the AI's scope reads (`router_reads`)."""
    from modules.ai import router_reads
    return router_reads._committed(network, [host])


# ---------------------------------------------------------------------------- the plan

def _cli_operations() -> list:
    """The AI's device reads, in `router_reads.SHAPES`' order: `fixit_reads.FAMILY`'s CLI
    operations (the AI analysis's `AI_READS` and AI troubleshooting's telemetry reads), those
    of the configuration class left out (step b asks for the running configuration)."""
    from modules.ai.fixit_reads import FAMILY
    return [op for op in FAMILY.operations
            if FAMILY.transport_of(op) == "cli" and FAMILY.class_of(op) != "configuration"]


def _own_addresses(intent: dict) -> tuple:
    """``(ipv4s, ipv6s)``: the device's own interface addresses in committed intent, link-local
    left out."""
    import ipaddress
    from modules.neighbours import _v4

    v4, v6 = [], []
    for iface in (intent or {}).get("interfaces") or []:
        a = _v4(iface.get("ipv4") or "")
        if a is not None:
            v4.append(str(a.ip))
        for text in iface.get("ipv6") or []:
            try:
                ip = ipaddress.ip_interface(text).ip
            except ValueError:
                continue
            if not ip.is_link_local:
                v6.append(str(ip))
    return v4, v6


#: The reads asked of an interface a neighbour is cabled to (`router_reads._cabled_interface`
#: refuses a loopback for them): their interface is a link's, never the first the golden holds.
CABLED = ("cdp", "lldp")


def _link_interfaces(host: str, scope: dict, intents: dict) -> list:
    """The golden's interfaces, in its order, that committed intent gives a neighbour on
    (`neighbours.link_interfaces`: never a loopback) and that a cable plugs into
    (`ifnames.cabled`: an SVI or a tunnel has a routing neighbour and no cable, and whether a
    device answers CDP's form for one is not measured)."""
    from modules import neighbours
    from modules.nsot.ifnames import cabled, same_interface

    held = ((scope.get("devices") or {}).get(host) or {}).get("interfaces") or []
    links = neighbours.link_interfaces(intents or {}, host)
    return [h for h in held if cabled(h) and any(same_interface(h, name) for name in links)]


def _defaults(host: str, scope: dict, intents: dict, given: dict) -> dict:
    """Each argument kind's value: the operator's, else what Mercury holds, else absent."""
    import ipaddress

    dev = (scope.get("devices") or {}).get(host) or {}
    intent = (intents or {}).get(host) or {}
    v4, v6 = _own_addresses(intent)
    net = [ipaddress.ip_address(a) for a in scope.get("addresses") or ()]
    peers = [ipaddress.ip_address(p) for p in dev.get("peers") or ()]

    def first(items):
        return items[0] if items else ""

    return {
        "interface": given.get("interface") or first(dev.get("interfaces") or []),
        "link_interface": given.get("link_interface") or first(
            _link_interfaces(host, scope, intents)),
        "address4": given.get("address") or first(v4) or first(
            [str(a) for a in net if a.version == 4]),
        "address6": given.get("address6") or first(v6) or first(
            [str(a) for a in net if a.version == 6]),
        "peer4": given.get("peer") or first([str(p) for p in peers if p.version == 4]),
        "peer6": given.get("peer6") or first([str(p) for p in peers if p.version == 6]),
        "mac": given.get("mac") or "",
        "subscription": given.get("subscription") or first(dev.get("subscriptions") or []),
    }


#: Where each argument kind's value comes from when none is given, for NOT MEASURED's words.
_ABSENT = {"interface": "the committed golden holds no interface (--interface names one)",
           "link_interface": "committed intent gives the device no neighbour on a cabled "
                             "interface its golden holds (no OSPF or OSPFv3 adjacency on one, "
                             "and none sharing a network with another device's), and a "
                             "loopback is never asked (--link-interface names one)",
           "address4": "committed intent holds no IPv4 address (--address names one)",
           "address6": "committed intent holds no IPv6 address (--address6 names one)",
           "peer4": "intent names no IPv4 BGP peer for the device (--peer names one)",
           "peer6": "intent names no IPv6 BGP peer for the device (--peer6 names one)",
           "mac": "Mercury holds no MAC address to ask for (--mac names one)",
           "subscription": "intent declares no telemetry subscription (--subscription names one)"}


def _kind(op, arg: str) -> str:
    """The argument kind an operation's argument is filled from."""
    if arg in ("address", "peer"):
        version = getattr(op.args[arg].shape, "version", 4)
        return f"{arg}{version}"
    if arg == "interface" and op.name in CABLED:
        return "link_interface"
    return arg


def plan(network: str, host: str, given: dict = None) -> dict:
    """What a run would send, touching no device: the account, the reads (each judged by the
    AI's own check), the refused commands, and the hash. ``{"refused": why}`` when there is
    nothing to probe."""
    from modules.ai import read_loop as RL
    from modules.ai import router_reads as RR
    from modules.ai.fixit_reads import FAMILY
    from modules.nsot import reads
    from modules.nsot.deploy import command_fingerprint
    from modules.nsot.platform import platform_for_device

    given = dict(given or {})
    dev = _inventory(network).get(host)
    if dev is None:
        return {"refused": f"REFUSED: {host} is not a device of {network}"}
    account = reads.read_account_for(dev)
    if not account.get("ok"):
        return {"refused": (f"REFUSED: no read-only account for {host}: {account.get('error')}; "
                            "nothing to probe")}
    intents, goldens = _committed(network, host)
    scope = RR.scope_for(network, [host], intents=intents, goldens=goldens)
    values = _defaults(host, scope, intents, given)
    rows = []
    for op in _cli_operations():
        row = {"op": op.name, "words": op.words}
        # Another platform's form (a dialect's own on the other dialect, a switch's read on a
        # device with no VLAN database) is one the AI never asks here: by the AI read set's
        # own comparison, before any argument is looked for.
        elsewhere = RR.other_platform(op.name, host, scope)
        if elsewhere:
            rows.append(dict(row, result="other platform", why=elsewhere))
            continue
        # A form asked only under the installation choice, while it is off: the AI's own check
        # refuses it by name, so it is not a read the account is expected to answer.
        unasked = RR.choice_off(op.name, scope)
        if unasked:
            rows.append(dict(row, result=NOT_ASKED, why=unasked))
            continue
        args, missing = {"device": host}, ""
        for arg in op.args:
            if arg == "device":
                continue
            kind = _kind(op, arg)
            if not values.get(kind):
                missing = _ABSENT[kind]
                break
            args[arg] = values[kind]
        if missing:
            rows.append(dict(row, result=NOT_MEASURED, why=missing))
            continue
        verdict = RL.check(FAMILY, [{"op": op.name, "args": args, "why": WHY,
                                     "hypothesis": WHY}],
                           network=network, scope=scope, assume_on=("device_state",))[0]
        reason = verdict.get("reason") or ""
        reason = reason[len(op.name) + 2:] if reason.startswith(f"{op.name}: ") else reason
        if verdict["verdict"] == "allowed":
            rows.append(dict(row, command=verdict["requests"][0]))
        else:
            rows.append(dict(row, result=NOT_MEASURED,
                             why=f"the AI's own check refuses it: {reason}"))
    sent = [r["command"] for r in rows if r.get("command")] + [s["command"] for s in REFUSED]
    signs_in = {"username": account["username"], "source": account["source"]}
    declared = [{"network": network, "device": host, "signs in as": signs_in,
                 "never": "enable", "answers": ANSWERS, "never answered": NEVER_ANSWERED,
                 "not measured": sorted(r["op"] for r in rows if r.get("result") == NOT_MEASURED)}]
    return {"network": network, "device": host, "platform": platform_for_device(dev),
            "account": signs_in, "reads": rows, "refused_steps": [dict(s) for s in REFUSED],
            "program": sent, "hash": command_fingerprint(sent, None, declared=declared)}


def preview_lines(p: dict) -> list:
    acct = p["account"]
    profile = acct["source"].rsplit(":", 1)[-1]
    out = ["PREVIEW: nothing connects and nothing is sent.",
           f"  network {p['network']}, device {p['device']} "
           f"({p['platform'] or 'platform unknown'})",
           f"  signs in as {acct['username']}, the read-only account of profile {profile} "
           f"({acct['source']}); its password from the credential store, never shown; never "
           "enable",
           "  the device held for the whole run (one operation per device)", "",
           "  The AI's reads, each through the AI's own check: expected ANSWERED"]
    n = 0
    for r in p["reads"]:
        if r.get("command"):
            n += 1
            out.append(f"    {n:2d}. {r['command']}")
    for label, kind in (("  Not measured (the verdict cannot be PASS):", NOT_MEASURED),
                        ("  Another platform's form (the AI never asks it here):",
                         "other platform"),
                        ("  Not asked (the AI's own check refuses it by name):", NOT_ASKED)):
        rows = [r for r in p["reads"] if r.get("result") == kind]
        if rows:
            out += ["", label] + [f"        {r['op']}: {r['why']}" for r in rows]
    out += ["", "  Expected REFUSED of the read-only account:"]
    for s in p["refused_steps"]:
        n += 1
        out.append(f"    {n:2d}. {s['command']}   ({s['words']})")
    out += ["", f"  hash: {p['hash']}",
            f"  --confirm {p['hash']} --actor <you> runs exactly this program."]
    return out


# ---------------------------------------------------------------------------- reading answers

def _meaningful(text: str, command: str) -> list:
    """The answer's lines that say something: not blank, not the echoed command, not IOS's caret
    line, not a prompt."""
    out = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s or CARET.fullmatch(s) or PROMPT.fullmatch(s):
            continue
        if s == command.strip() or (PROMPT.match(s) and s.endswith(command.strip())):
            continue
        out.append(s)
    return out


def _last(text: str) -> str:
    return next((ln.strip() for ln in reversed((text or "").splitlines()) if ln.strip()), "")


def at_exec_prompt(text: str) -> bool:
    """The answer ends at an exec prompt (not a configuration one): the session may go on."""
    last = _last(text)
    return bool(PROMPT.fullmatch(last)) and not CONFIG_PROMPT.search(last)


def judge_read(answer: dict) -> dict:
    """A read's answer (`reads._answer`'s): ANSWERED, refused (FAIL) or UNREADABLE."""
    from modules.heal.bounce import device_errors

    if answer.get("state") != "answered":
        return {"result": UNREADABLE, "why": f"not answered: {answer.get('why') or 'no reason'}"}
    text = answer.get("answer") or ""
    lines = _meaningful(text, answer.get("command") or "")
    refusal = next((ln for ln in lines if REFUSAL.match(ln) or AUTH_WORDS.search(ln)), "")
    if refusal:
        return {"result": FAIL, "why": f"refused: {refusal}"}
    if len(lines) == 1 and NOT_RUNNING.match(lines[0]):
        return {"result": PASS, "why": f"answered: {lines[0]} (the read was accepted; the "
                                       "protocol is not running on the device)"}
    errors = device_errors(text)
    if errors:
        return {"result": UNREADABLE,
                "why": f"a device error that is not a refusal shape: {errors[0]}"}
    return {"result": PASS, "why": f"answered ({answer.get('bytes', len(text))} bytes)"}


def judge_refused(text: str, command: str) -> dict:
    """A command expected refused: PASS only on the device's own refusal shape, first."""
    raw = [ln.strip() for ln in (text or "").splitlines()]
    if any(CONFIG_PROMPT.search(ln) for ln in raw):
        return {"result": FAIL, "why": "accepted: the account can configure"}
    if _last(text).endswith("[confirm]"):
        return {"result": FAIL, "why": f"asked {_last(text)!r}: the account can run it"}
    lines = _meaningful(text, command)
    first = lines[0] if lines else ""
    if first and REFUSAL.match(first):
        return {"result": PASS, "why": f"refused: {first}"}
    if not first:
        return {"result": UNREADABLE, "why": "nothing came back: neither a refusal nor an answer"}
    if first.startswith("%"):
        return {"result": UNREADABLE, "why": f"{first!r} is not one of the refusal shapes"}
    return {"result": FAIL, "why": f"answered, not refused: {first[:120]}"}


def judge_enable(text: str, command: str = "enable") -> dict:
    """``enable`` as the read-only account: PASS when the device asks for the enable password
    (never answered: the caller closes the session) or refuses with a ``%`` line; FAIL when it
    answers a privileged prompt with nothing asked; anything else UNREADABLE. A custom level's
    own prompt is ``#`` already, so the prompt alone never says refused: only what stands
    between the command and it."""
    last = _last(text)
    if PASSWORD_PROMPT.match(last):
        return {"result": PASS, "why": "refused: it asks for the enable password, which is "
                                       "never answered (the session closed, nothing typed)"}
    lines = _meaningful(text, command)
    first = lines[0] if lines else ""
    if first.startswith("%"):
        return {"result": PASS, "why": f"refused: {first}"}
    if not first and PROMPT.fullmatch(last) and last.endswith("#"):
        return {"result": FAIL, "why": f"accepted with no password asked: it answered the "
                                       f"privileged prompt {last!r}"}
    if not first:
        return {"result": UNREADABLE, "why": "neither a password prompt, a refusal nor a "
                                             f"privileged prompt came back (it ended {last!r})"}
    return {"result": UNREADABLE, "why": f"{first[:120]!r} is neither a password prompt nor a "
                                         "refusal"}


# ---------------------------------------------------------------------------- the run

def _abandon(conn) -> None:
    """Close *conn* with NOTHING typed. Netmiko's ``disconnect()`` first runs its ``cleanup``,
    which types Enter (its configuration-mode check) and ``exit``: at a ``Password:`` prompt
    that is an answer, at a question it accepts the default, and after ``debug ?`` it sends the
    line left behind. So the cleanup is replaced by nothing on this one session, and the
    transport is closed (which also drops the session from Mercury's count)."""
    conn.cleanup = lambda *args, **kwargs: None
    try:
        conn.disconnect()
    except Exception:                                 # noqa: BLE001 (gone either way)
        pass


def mask_answer(text: str, values: dict) -> str:
    """A device's *text* as the record keeps it: `redact.redact_text`'s masks by position and
    by value, *values* being the run's known secret values with the read-only account's
    password among them."""
    from modules.redact import redact_text

    return redact_text(text or "", values)


def _signin_failure(exc: BaseException, account: dict, values: dict) -> dict:
    from modules.nsot.credential_rotation import AUTH_DENIED, login_failure_kind
    from modules.redact import redact_text

    name, text = type(exc).__name__, str(exc)
    first = redact_text(next((ln for ln in text.splitlines() if ln.strip()), ""), values)[:300]
    profile = account["source"].rsplit(":", 1)[-1]
    if name in AUTH_DENIED and login_failure_kind(name, text) == "refused":
        return {"result": SIGNIN_REFUSED,
                "why": (f"the device does not accept the read-only account {account['username']} "
                        f"(profile {profile}): {name}: {first}")}
    return {"result": UNREADABLE,
            "why": f"could not sign in as {account['username']} (no verdict): {name}: {first}"}


def run(p: dict, dev: dict, actor: str, values: dict, cap: int, *, held: bool = False) -> dict:
    """The program *p*, holding the device, signed in as the read-only account. The record.

    *held*: the caller holds the device already, for this run's whole length (the rollout's
    check after verify, inside THE apply's hold, `read_account.probe_after_verify`): the run
    takes no hold of its own, which would refuse it as another holder."""
    from modules.connection import stored_connection_params
    from modules.config_read import spent
    from modules.nsot import device_ops, reads

    host, network = p["device"], p["network"]
    account = reads.read_account_for(dev)
    rec = {"probe": "read-account", "network": network, "device": host,
           "platform": p["platform"], "actor": actor, "hash": p["hash"],
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "account": dict(p["account"]), "reads": [], "refused": []}
    if not account.get("ok") or account["username"] != p["account"]["username"]:
        rec["verdict"] = {"result": UNREADABLE, "why": "the read-only account changed since the "
                          "plan: " + (account.get("error") or account["username"])}
        return rec
    password = account.pop("password")
    if len(password) >= 8:
        values = dict(values, **{password: "the read-only account's password"})
    params = stored_connection_params(reads.as_read_account(dev, dict(account, password=password)))
    del password

    # The two sends, inside the run that holds the device: a line with Enter, and text typed
    # with no Enter after it.
    def _raw(conn, command: str) -> str:
        return conn.send_command_timing(command, strip_prompt=False, strip_command=False,
                                        read_timeout=RAW_WAIT, last_read=RAW_QUIET) or ""

    def _bare(conn, text: str) -> str:
        conn.write_channel(text)
        return conn.read_channel_timing(last_read=RAW_QUIET, read_timeout=RAW_WAIT) or ""

    stopped = ""
    holding = (contextlib.nullcontext() if held else
               device_ops.hold(network, host, "probe", actor, detail="read-only account",
                               ip=dev.get("ip", "")))
    with holding:
        try:
            conn = OPEN(params)
        except Exception as exc:                      # noqa: BLE001 (the verdict)
            rec["verdict"] = _signin_failure(exc, p["account"], values)
            return rec
        try:
            for r in p["reads"]:
                if not r.get("command"):
                    rec["reads"].append({k: r[k] for k in ("op", "result", "why")})
                    continue
                if spent(conn):
                    # A session a failed read spent is never read again (C272): a new one.
                    _abandon(conn)
                    conn = OPEN(params)
                a = reads._answer(conn, r["command"], values, cap, dev.get("device_type", ""))
                got = judge_read(a)
                rec["reads"].append({"op": r["op"], "command": r["command"], **got,
                                     "answer": a.get("answer", ""), "cut": a.get("cut", False)})
            if spent(conn):
                _abandon(conn)
                conn = OPEN(params)
            for s in p["refused_steps"]:
                if stopped:
                    rec["refused"].append({"key": s["key"], "command": s["command"],
                                           "result": "not run",
                                           "why": f"the run stopped at {stopped}"})
                    continue
                row = {"key": s["key"], "command": s["command"]}
                if conn is None:
                    # The step before closed its session: this one opens its own.
                    try:
                        conn = OPEN(params)
                    except Exception as exc:          # noqa: BLE001 (no verdict for the step)
                        why = _signin_failure(exc, p["account"], values)["why"]
                        rec["refused"].append(dict(row, result=UNREADABLE, why=(
                            f"a new session for it could not be opened: {why}")))
                        stopped = s["key"]
                        continue
                answer = _bare(conn, s["command"]) if s.get("bare") else _raw(conn, s["command"])
                judged = judge_enable if s.get("enable") else judge_refused
                row.update(judged(answer, s["command"]), answer=mask_answer(answer, values)[:cap])
                if s.get("enable"):
                    # Whatever it asked is never answered, and a password prompt is no reason
                    # to stop the run: its session is closed below, nothing typed.
                    pass
                elif CONFIG_PROMPT.search(_last(answer)):
                    after = _raw(conn, END)
                    row.update(answered=END, after=mask_answer(after, values)[:cap])
                    if not at_exec_prompt(after):
                        stopped = s["key"]
                        row["why"] += f"; `{END}` did not return it to its exec prompt"
                elif _last(answer).endswith("[confirm]"):
                    after = _bare(conn, NO)
                    row.update(answered=NO, after=mask_answer(after, values)[:cap])
                    if not at_exec_prompt(after):
                        stopped = s["key"]
                        row["why"] += f"; `{NO}` did not return it to its exec prompt"
                elif not s.get("bare") and not at_exec_prompt(answer):
                    # A question, a pager or no prompt: never answered (send, read, decide).
                    stopped = s["key"]
                    row["why"] += (f"; it ended {_last(mask_answer(answer, values))[:120]!r}, not at its exec "
                                   "prompt: not answered, the session closed")
                if s.get("closes") or stopped:
                    _abandon(conn)
                    conn = None
                rec["refused"].append(row)
        finally:
            # Every close types nothing (`_abandon`): a session left at a question, a password
            # prompt or a typed line is never sent Enter by its own closing.
            if conn is not None:
                _abandon(conn)
    rec["stopped"] = stopped
    rec["verdict"] = verdict(rec)
    return rec


def verdict(rec: dict) -> dict:
    """PASS only when every read answered and every refused command was refused."""
    rows = [r for r in rec["reads"]
            if r.get("result") not in ("other platform", NOT_ASKED)] + rec["refused"]
    results = [r.get("result") for r in rows]
    missed = [r["command"] for r in rec["reads"]
              if r.get("result") == FAIL and str(r.get("why", "")).startswith("refused")]
    out = {"missed_reads": missed}
    if missed:
        out["proposal"] = (f"the read-only account misses {len(missed)} of the AI's reads: the "
                           "next proposal is `privilege exec level <n> <command>` lines for "
                           "exactly these at a custom level (2 to 14), through intent's "
                           "privilege_exec, never a parser view (it needs aaa new-model) and "
                           "never privilege 15: " + "; ".join(missed))
    if FAIL in results:
        return dict(out, result=FAIL,
                    why=f"{results.count(FAIL)} FAIL: " + "; ".join(
                        f"{r.get('command') or r.get('op')}: {r['why']}" for r in rows
                        if r.get("result") == FAIL))
    if UNREADABLE in results or "not run" in results or rec.get("stopped"):
        return dict(out, result=UNREADABLE, why="; ".join(
            f"{r.get('command') or r.get('op')}: {r['why']}" for r in rows
            if r.get("result") in (UNREADABLE, "not run")))
    if NOT_MEASURED in results:
        return dict(out, result="INCOMPLETE", why="every measured read answered and every "
                    "refused command was refused, but not every read was measured: " + "; ".join(
                        f"{r['op']}: {r['why']}" for r in rows if r.get("result") == NOT_MEASURED))
    return dict(out, result=PASS, why=(f"every AI read answered ({len(rec['reads'])} shapes) and "
                                       f"every refused command was refused, signed in as "
                                       f"{rec['account']['username']}"))


def records_root() -> str:
    """Where every probe record is kept: the data directory's ``probes/read-account/``."""
    from modules import config
    return os.path.join(config.DATA_DIR, "probes", "read-account")


def identity_of(network: str, host: str, repo: str = "") -> str:
    """*host*'s identity in *network*'s manifest (Mercury's ``uid:…`` or ``netbox:<id>``, the
    key retirement releases), or ``""`` when it has none recorded. *repo*: the network's
    repository when the caller holds its ref already. A read: a network no list answers to is
    none recorded, and nothing is created (resolving a list's path makes its folders)."""
    from modules.nsot import listref, manifest

    try:
        if not repo:
            if not listref.exists(network):
                return ""
            repo = listref.resolve(network).repo_dir
        identity, _entry = manifest.find_by_name(repo, host)
    except Exception:                                 # noqa: BLE001 (none recorded)
        return ""
    return identity or ""


def identity_slug(identity: str) -> str:
    """An identity as one folder name (``uid:<uuid>`` has a colon)."""
    return re.sub(r"[^A-Za-z0-9._-]", "-", identity or "") or "unrecorded"


def record_dir(network: str, identity: str) -> str:
    """The folder one device's records are kept in: by its network and identity, never its
    name alone, so a new device of the same name inherits none of them."""
    return os.path.join(records_root(), identity_slug(network), identity_slug(identity))


def write_record(rec: dict) -> str:
    """Write *rec* owner-only under the device's identity folder (`record_dir`); a device with
    no identity recorded is kept flat by name, as records were before (`retire` removes both)."""
    from modules.config import open_secure

    identity = rec.get("identity") or identity_of(rec["network"], rec["device"])
    rec["identity"] = identity
    folder = record_dir(rec["network"], identity) if identity else records_root()
    os.makedirs(folder, mode=0o700, exist_ok=True)
    stamp = rec["at"].replace("-", "").replace(":", "")
    path = os.path.join(folder, f"{rec['device']}-{stamp}.json")
    with open_secure(path, "w") as fh:
        fh.write(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    return path


def summary_lines(rec: dict) -> list:
    out = []
    for r in rec["reads"]:
        out.append(f"{r.get('result'):12s} {r.get('command') or r['op']}"
                   + ("" if r.get("result") == PASS else f"  ({r.get('why')})"))
    for r in rec["refused"]:
        out.append(f"{r.get('result'):12s} {r['command']}  ({r.get('why')})")
    v = rec["verdict"]
    out.append(f"{rec['device']} as {rec['account']['username']}: {v['result']}: "
               f"{v.get('why', '')}")
    if v.get("proposal"):
        out.append(v["proposal"])
    return out


# ---------------------------------------------------------------------------- main

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_ARG = re.compile(r"[\x21-\x7e]{1,64}\Z")
GIVEN = ("interface", "link_interface", "address", "address6", "peer", "peer6", "mac",
         "subscription")


def refusal(args, now: float = None) -> str:
    for name in ("network", "device"):
        value = getattr(args, name) or ""
        if not _NAME.match(value):
            return f"REFUSED: --{name} {value!r} is not one name"
    for name in GIVEN:
        value = getattr(args, name, "") or ""
        if value and not _ARG.match(value):
            return f"REFUSED: --{name} {value!r} is not one token of printable characters"
    if args.confirm:
        if not (args.actor or "").strip():
            return "REFUSED: --confirm needs --actor (who is accountable)"
        held = no_change_now(now)
        if held:
            return (f"REFUSED: it is inside {held}; a measurement taken now measures what the "
                    "window is kept for. Run it after the window's end.")
    return ""


def main(argv=None, refuse=None) -> int:
    """The command line: *refuse* is the caller's refusal (`refusal` by default; the script's
    adds the lab's backup window)."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--network", default="")
    ap.add_argument("--device", default="")
    ap.add_argument("--confirm", default="", help="the preview's hash: runs exactly that program")
    ap.add_argument("--actor", default="")
    for name in GIVEN:
        ap.add_argument(f"--{name.replace('_', '-')}", dest=name, default="")
    args = ap.parse_args(argv)

    why = (refuse or refusal)(args)
    if why:
        print(why)
        return 1
    p = plan(args.network, args.device, {k: getattr(args, k) for k in GIVEN})
    if p.get("refused"):
        print(p["refused"])
        return 1
    if not args.confirm:
        print("\n".join(preview_lines(p)))
        return 0
    if args.confirm != p["hash"]:
        print(f"REFUSED: --confirm {args.confirm} and the program's hash now, {p['hash']}, "
              "differ: the program moved since its preview (the account, a read's argument, or "
              "what Mercury holds for the device). Nothing connected; preview it again.")
        return 1

    from modules.nsot import reads
    from modules.redact import known_secret_values

    dev = _inventory(args.network)[args.device]
    rec = run(p, dev, args.actor.strip(), known_secret_values(), reads.cap_bytes(args.network))
    path = write_record(rec)
    print("\n".join(summary_lines(rec)))
    print(f"written: {path}")
    if rec["verdict"]["result"] == SIGNIN_REFUSED:
        return 2
    return 3 if rec.get("stopped") else 0

