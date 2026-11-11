"""Whose change a configuration-change line records: Mercury's own, or from outside Mercury
(board H, part H2; docs/HEAL_TO_INTENT.md section 3, "The attribution rule", and N12).
Deterministic; it reads Mercury's own records and never a device.

**The rule.** A ``%SYS-5-CONFIG_I`` (or ``CONFIG_P``, or IOS-XE's DMI ``CONFIG_I``: the lines
`ai.who.CONFIG_LOG` names) is MERCURY'S when, at the line's receive time:
1. a Mercury operation held the device (`device_ops.holder`: one operation per device across
   processes, and a session write needs the device held), its hold started no later than the
   line; or
2. a receipt of Mercury's for the device (`receipts.read`: deploy, restore, re-apply, a
   profile apply) is within `attention.DEPLOY_WINDOW_S` before the line's receive time to
   `AFTER_RECEIPT_SECONDS` after it, the window the adjacency log already uses for a deploy;
   or
3. a credential rotation's commit for the device (`scheduled_rotation.committed_rotations`)
   is within that window: a rotation writes no receipt, and its commit is its record; or
4. a run of a Mercury operation that changes the device's configuration and writes no receipt
   (its record says ``config_change``: the telemetry re-subscribe, `modules/heal/resubscribe.py`,
   C2838) spans the line: written before it sends, from its start to `AFTER_RECEIPT_SECONDS`
   after its end. The re-subscribe's own removal and re-add, seconds apart, are each its
   change, never one from outside. Only a FINISHED run spans anything: a run still going
   holds the device, which is rule 1's, and a record left ``running`` by a run that never
   ended (Mercury restarted under it) spans nothing, so it cannot make every later line on
   that device Mercury's own.

Otherwise it is OUTSIDE Mercury: a person at the device's CLI, or another system. A record that
cannot be read makes the answer UNKNOWN, naming it, never Mercury's: a guard that cannot be read
fails closed (section 6), and an unknown change is treated as an outside one.

**Never by the account the line names.** A person may sign in with the account Mercury uses
(an installation's accounts may be shared), so the account is a resemblance, not evidence
(CLAUDE.md, "Refusing by resemblance"). The account, the terminal line and the address the line
names are kept only to NAME the person in the record and the notice (N12: a person's change is
healed after the grace period, the person named), each said as what the line named.

**IPv4 and IPv6.** The address a line names (``(192.0.2.5)`` or ``(2001:db8::5)``) is kept in
its compressed form; `address_of` also reads an alert's polled ``instance`` with its port,
``[2001:db8::1]:161`` included.
"""

import calendar
import ipaddress
import logging
import time

log = logging.getLogger(__name__)

MERCURY, OUTSIDE, UNKNOWN = "mercury", "outside", "unknown"
BY_WORDS = {MERCURY: "Mercury's own", OUTSIDE: "from outside Mercury",
            UNKNOWN: "not known whose"}
#: A receipt is written as its operation ends: a line up to a minute after it is the
#: operation's tail (the adjacency log's window, `attention._explained`).
AFTER_RECEIPT_SECONDS = 60
#: How many receipts of one device are read back: the newest fifty, as the adjacency log does.
RECEIPTS_READ = 50


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _epoch(iso) -> float:
    try:
        return float(calendar.timegm(time.strptime(str(iso)[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return 0.0


def before_seconds() -> int:
    """The window before a receipt: the adjacency log's for a deploy (one owner)."""
    from modules.attention import DEPLOY_WINDOW_S

    return int(DEPLOY_WINDOW_S)


def address_of(text) -> str:
    """An address as one compressed form, IPv4 or IPv6, from a line's ``(address)``, an alert's
    polled ``instance`` (``192.0.2.1:161``, ``[2001:db8::1]:161``) or a bare address; "" when it
    is none."""
    t = str(text or "").strip()
    if t.startswith("["):
        host = t[1:t.find("]")] if "]" in t else ""
    elif t.count(":") == 1:
        host = t.split(":", 1)[0]
    else:
        host = t
    try:
        return ipaddress.ip_address(host).compressed
    except ValueError:
        return ""


def is_change(mnemonic: str, text: str) -> bool:
    """Is this a configuration-change line (`who.CONFIG_LOG`: CONFIG_I, CONFIG_P, DMI's)?"""
    from modules.ai.who import CONFIG_LOG

    return bool(CONFIG_LOG.search(f"{mnemonic or ''}: {text or ''}"))


def person_of(mnemonic: str, text: str) -> dict:
    """What the line names of who made the change (`who.config_change`): ``{"user", "line",
    "address", "source", "process", "words"}``, the address compressed; ``{}`` when the line is
    no configuration change. Each part is what the LINE says, never established."""
    from modules.ai.who import config_change

    got = config_change(f"{mnemonic or ''}: {text or ''}")
    if got is None:
        return {}
    got = dict(got)
    got["address"] = address_of(got.get("address")) or got.get("address") or ""
    return dict(got, words=person_words(got))


def person_words(p: dict) -> str:
    """How a record names who the line says made the change, as the line said it."""
    p = p or {}
    console = (p.get("line") or "").strip().lower() == "console"
    if console and not p.get("user") and not p.get("process"):
        # C2819 (the operator, H11 W5): a console line carries no account and names the console
        # as both its line and its source; said once, plainly.
        return "made on the console, no account named"
    parts = []
    if p.get("user"):
        parts.append(f"the account {p['user']}")
    if p.get("process"):
        parts.append(f"the process {p['process']}")
    if p.get("line"):
        parts.append(f"on {p['line']}")
    if p.get("address"):
        parts.append(f"from {p['address']}")
    elif p.get("source") and p.get("source") != p.get("line"):
        parts.append(f"from {p['source']}")
    if not parts:
        return "the line names nobody"
    if not p.get("user") and not p.get("process"):
        parts.insert(0, "no account named")
    return "the line names " + " ".join(parts)


def _holder(network: str, device: str):
    from modules.nsot import device_ops

    return device_ops.holder(network, device)


def _receipts(network: str, device: str) -> list:
    from modules.nsot import receipts as R

    got = R.read(network, device, limit=RECEIPTS_READ)
    if got["state"] == "unreadable":
        raise RuntimeError(f"{network}'s receipts cannot be read ({got.get('error')})")
    return got["rows"]


def _rotations(network: str) -> dict:
    from modules.nsot.scheduled_rotation import committed_rotations

    return committed_rotations(network)


def _operations(network: str, device: str) -> list:
    """*device*'s runs of the operations that change configuration and write no receipt (rule
    4): the newest `RECEIPTS_READ` of the operations' record (`privileged.runs`) that say
    ``config_change``. Raises when a record cannot be read: an unread one is never an absence."""
    from modules.config import list_data_path
    from modules.nsot import privileged

    # Read where the network's records are, creating nothing (a read creates no list).
    got = privileged.runs(network, device=device, limit=RECEIPTS_READ,
                          data_dir=list_data_path(network))
    if got["unreadable"]:
        raise RuntimeError(f"{len(got['unreadable'])} of {network}'s operation records cannot "
                           f"be read ({', '.join(got['unreadable'][:3])})")
    return [r for r in got["runs"] if r.get("config_change")]


def attribute(network: str, device: str, at: float, *, holder=None, receipts=None,
              rotations=None, operations=None) -> dict:
    """Whose change a configuration-change line of *device*'s, received at *at*, records:
    ``{"by", "words", "evidence", "operands"}``. *by* is `MERCURY`, `OUTSIDE` or `UNKNOWN`;
    *evidence* names the hold, receipt, rotation or operation run that made it Mercury's (or
    what could not be read). *holder*, *receipts*, *rotations* and *operations* stand in for
    Mercury's stores in a test."""
    holder = holder or _holder
    receipts = receipts or _receipts
    rotations = rotations or _rotations
    operations = operations or _operations
    before, after = before_seconds(), AFTER_RECEIPT_SECONDS
    operands = {"device": device, "network": network, "line_at": _iso(at),
                "window": f"{before} s before a receipt to {after} s after it"}
    unread = []
    try:
        h = holder(network, device)
    except Exception as exc:
        h = None
        unread.append(f"what holds {device} cannot be read ({exc})")
    if h and float(h.get("started") or 0) <= at:
        what = h.get("operation") or "an operation"
        return {"by": MERCURY, "evidence": {"hold": {k: h.get(k) for k in
                                                     ("operation", "actor", "started")}},
                "operands": operands,
                "words": (f"Mercury's own: {what} by {h.get('actor') or 'an unrecorded actor'} "
                          f"held {device} from {_iso(float(h.get('started') or 0))}, before the "
                          f"line at {_iso(at)}")}
    try:
        rows = receipts(network, device)
    except Exception as exc:
        rows = []
        unread.append(str(exc))
    for r in rows:
        t = _epoch(r.get("at"))
        if t and t - before <= at <= t + after:
            return {"by": MERCURY, "operands": operands,
                    "evidence": {"receipt": {k: r.get(k) for k in ("id", "action", "at",
                                                                   "actor")}},
                    "words": (f"Mercury's own: the {r.get('action') or 'operation'} receipt "
                              f"{r.get('id') or '?'} at {r.get('at')} is within {before} s before "
                              f"to {after} s after the line at {_iso(at)}")}
    try:
        rot = (rotations(network) or {}).get(device)
    except Exception as exc:
        rot = None
        unread.append(f"{network}'s rotation commits cannot be read ({exc})")
    if rot and rot[0] - before <= at <= rot[0] + after:
        return {"by": MERCURY, "operands": operands,
                "evidence": {"rotation": {"at": rot[1]}},
                "words": (f"Mercury's own: a credential rotation of {device} committed at "
                          f"{rot[1]}, within {before} s before to {after} s after the line at "
                          f"{_iso(at)}")}
    try:
        runs = operations(network, device)
    except Exception as exc:
        runs = []
        unread.append(f"{network}'s operation records cannot be read ({exc})")
    for r in runs:
        try:
            start = float(r.get("started_at") or 0)
            end = float(r.get("finished_at") or 0)
        except (TypeError, ValueError):
            continue
        # A finished run only: one still going holds the device (rule 1, above), and one that
        # never ended has no end to span to.
        if start and end and start <= at <= end + after:
            return {"by": MERCURY, "operands": operands,
                    "evidence": {"operation": {k: r.get(k) for k in ("id", "key", "command",
                                                                     "actor", "at")}},
                    "words": (f"Mercury's own: {r.get('command') or 'an operation'} by "
                              f"{r.get('actor') or 'an unrecorded actor'} (run {r.get('id')}), "
                              f"from {_iso(start)} to {_iso(end)}, spans the line at "
                              f"{_iso(at)} (up to {after} s after its end)")}
    if unread:
        return {"by": UNKNOWN, "operands": operands, "evidence": {"unreadable": unread},
                "words": (f"not known whose: {'; '.join(unread)}, so whether Mercury made the "
                          f"change at {_iso(at)} cannot be told, and it is treated as from "
                          "outside Mercury")}
    return {"by": OUTSIDE, "operands": operands, "evidence": {},
            "words": (f"from outside Mercury: no Mercury operation held {device} at "
                      f"{_iso(at)}, and no receipt or rotation of it is within {before} s "
                      f"before to {after} s after")}
