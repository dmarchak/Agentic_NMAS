"""Re-subscribe a telemetry stream (C2838; C2890 and C2892 for its verify): a dial-out IETF
telemetry subscription on an IOS-XE device whose stream stays lost after its path came back is
re-established by removing its receiver and adding it back, the operator's recovery, as one
Mercury operation a person starts from the lost stream's Needs attention row.

**Why it exists** (C2838, the operator's hand fix of 2026-11-08 and its recurrence): a router
read its subscriptions Valid and its receiver Connected on connection 496, sent nothing, and
never redialled, while the collector held its TCP session ESTABLISHED (Telegraf's gRPC dial-out
was cancelled and the session stood on both ends: a stale dial-out session). Removing and
re-adding the receiver, one subscription at a time with about 10 s between, made it dial again.
Doing that by hand on the console is a terminal step; this module is its one home.

**One home** (CLAUDE.md, "One owner per piece of state; one home per action"): the fixed
program, its hash and authorisation, its held sends, its reads and verify, its rollback and its
record live here; the route (`routes/resubscribe_v2.py`) and the card call it. Its sends go
through the port bounce's held session (`bounce.Session.send`: one batch, holding the device,
refusing a save shape), so no second send path exists.

**The program** (`program_of`), each receiver line read from the device's COMMITTED intent
(`host_vars` ``telemetry``, `diagnose_stream.receiver_of` and its `RECEIVER` shape), never
typed. One subscription is two held sends with `WAIT_S` between::

    configure terminal                       configure terminal
    telemetry ietf subscription <id>         telemetry ietf subscription <id>
     no receiver ip address <a> <p> ...       receiver ip address <a> <p> ...
    end                                      end

**Several subscriptions are a batch** (decided 2026-11-11, C2838): the removals first, EVERY
chosen subscription's (each its own held send of the four lines above, in the order chosen,
each read back before the next), then one wait of `WAIT_S`, then every re-add (each its own
held send, each retried once), then each subscription's verify. Why the order: a device's
subscriptions to one receiver share ONE connection (two subscriptions of a lab router both read
Connected on connection 496 while neither streamed, 2026-11-10), and the device keeps that
connection while any subscription still refers to it. Removed and re-added one at a time, the
re-added one rejoins the stale connection the other still holds. Only with every chosen
receiver removed first is there a moment when no chosen subscription refers to it. A
subscription that was NOT chosen and sends to the same receiver address and port can keep it
alive too: the plan names each (`sharing`), and the card says so and offers it.

The configuration ends exactly as it began, and nothing is saved to startup: every send refuses
a save shape (`bounce.assert_no_save`), and the read-back compares the running configuration
with the one read before, line for line (`roundtrip.configs_equivalent`).

**A removal is Mode B** (CLAUDE.md, "Merge-only; a removal is Mode B"): a person selects each
subscription, with a stated reason, which is in the hash and the record (`authorised`); the
shape `telemetry.receiver` is allowed only where measured (`removal.shape_refusal`: the
operator's hand run on a lab C8000v, 2026-11-08, C2838's amendment), and every run measures it
again: after each removal the configuration read back must differ from before by exactly the
receiver lines removed so far, or nothing more is removed.

**The hashes** (`deploy.command_fingerprint`). Each subscription has its own hash, over its two
sends and its selection (`unit_hash`), the same whatever else is chosen. The SELECTION has one
too (`program_hash`): over the whole program in the order it is sent and the ids chosen, so it
differs with every change of the ticks; the card draws the program for exactly the ticks it
shows and carries that hash, and a tick changed redraws both. The confirm recomputes each from
intent for the subscriptions it was sent and refuses one that moved, naming both hashes and,
for the selection, both sets of subscriptions. The run's hash is over the same program with
each removal's authorisation and the reason (`run_hash`), kept in the record.

**Who confirms** (`person_refusal`): a verified PERSON, by either way a request's identity is
established (`identity.REQUEST_VERIFICATIONS`: the access proxy's assertion, or the
installation's local account). The kind is the one the identity states, read in the request
(`identity.actor_verification`), named in the record (``actor_verified``) and carried into the
job by the one job starter (`capture_job.start`, `identity.carried`); anything else (nobody, a
service, ``none``, an empty kind, a kind this table does not hold) is refused before the plan
is read, with nothing sent, by `start` and again by `apply`.

**The verify, per subscription, within `VERIFY_BOUND_S`** (2.5 times the 116 s measured on
2026-11-08: the receiver re-added at 20:59:41 UTC, the stream's data at 21:01:37), three checks,
each ``pass``, ``fail`` or ``cant_tell`` (an unreadable read neither passes nor fails, named):
(a) the device: `show telemetry ietf subscription <id> receiver` through the reads engine
    (`diagnose_parse.telemetry_receiver`), State Connected on a connection id that differs from
    the one read before the operation (a Connected receiver is not a stream: C2890's capture);
(b) the stream: its series in Prometheus by the lost-stream alert's own query
    (`diagnose_stream.series_of`);
(c) the collector: an ESTABLISHED session from the device's addresses on the stream's port that
    was not there before (by remote port), receiving inside the stream's window when the
    kernel's socket diagnostics are read (`diagnose_stream.read_collector`, `receiving_now`);
    a session that was there before and still stands without receiving is flagged "stale
    half-open" (a flag, not a failure).

**Rollback, and each subscription's own state.** A removal that does not land, takes more than
its line, or cannot be read back stops the REMOVALS there: the subscriptions after it are never
touched (``not_sent``), and every receiver already removed is still added back. A re-add that
does not land is sent once more; still not landed, that subscription's state is the danger
"<device>'s receiver for <id> is removed", the record says so, and the card offers the one-step
**Re-add the receiver** for each one (`apply` with ``readd``: the re-add alone, through the
same preview and confirm); the other re-adds are still sent. A run that fails part-way marks
every receiver whose removal was sent and whose re-add was not read back as removed too, so
none is left removed unsaid. A verify that fails with the re-add landed leaves the
configuration at intent, and says "re-subscribed; the stream did not come back". The run's
outcome is its worst subscription's, never green over a partial (`_overall`).

**Self-healing sees its own change as Mercury's** (`attribution`, rule 4): the record is written
with ``config_change`` once the device is held and before the first session is sent, so the
device's configuration lines during it are Mercury's own, never an outside change.
"""

import logging
import time

log = logging.getLogger(__name__)

KEY, READD_KEY = "telemetry-resubscribe", "telemetry-readd"
#: The hold's operation words (`device_ops.hold`), each a device-changing operation.
OPERATION, READD_OPERATION = "telemetry re-subscribe", "telemetry receiver re-add"
#: Mode B's measured shape for the receiver's removal (`removal.SHAPES`).
SHAPE = "telemetry.receiver"
#: Between the removal and the re-add: the operator's sequence (C2838's amendment: 13 s on the
#: hand run that brought subscription 102 back, "about 10 s").
WAIT_S = 10
#: Measured 2026-11-08 (C2838): the receiver re-added at 20:59:41 UTC, the stream's data at
#: 21:01:37 UTC, 116 s; the verify's bound is 2.5 times that, 290 s.
MEASURED_BACK_S = 116
VERIFY_BOUND_S = 290
#: The verify reads again this often while it waits.
POLL_S = 10
#: The reads engine's kind for the verify's device reads (`reads.run`'s *by*).
READS_BY = "person"
ANNOUNCE_KEYS = ("privileged",)
ANNOUNCER = "privileged"

#: The operation's steps, in order, for the manual's How it works page.
STEPS = (("plan", "Read each subscription's receiver from committed intent; refuse what is "
                  "not measured"),
         ("hash", "Recompute each subscription's program and compare its hash"),
         ("hold", "Hold the device for the whole operation"),
         ("started", "Record the run before anything is sent"),
         ("before", "Read before: the receiver's state and connection, the collector's "
                    "sessions, the running configuration"),
         ("remove", "Remove every chosen receiver, one held send each; read back after each "
                    "that exactly the lines removed so far left"),
         ("wait", "Wait 10 s, once, after the last removal"),
         ("re-add", "Add every receiver back, one held send each, once more if it did not "
                    "land; read back the configuration as before"),
         ("verify", "Verify each within 290 s: the device's state, the stream's series, the "
                    "collector's session"),
         ("rollback", "A removal that fails stops the removals and those removed are added "
                      "back; a receiver that did not come back is said, with Re-add the "
                      "receiver"),
         ("record", "Record the outcome, each subscription's own"))
#: The one-step Re-add the receiver.
READD_STEPS = (("plan", "Read the receiver from committed intent"),
               ("hash", "Recompute the program and compare its hash"),
               ("hold", "Hold the device"),
               ("started", "Record the run before anything is sent"),
               ("before", "Read before: the receiver's state, the collector's sessions"),
               ("re-add", "Add the receiver back, once more if it did not land"),
               ("verify", "Verify within 290 s, as the re-subscribe does"),
               ("record", "Record the outcome"))

OUTCOMES = ("resubscribed", "unverified", "not_back", "removed", "not_removed", "not_sent",
            "partial", "moved", "readded", "failed", "refused")
OUTCOME_WORDS = {"resubscribed": "re-subscribed; the stream is back",
                 "readded": "the receiver added back; the stream is back",
                 "unverified": "re-subscribed; whether the stream is back could not be told",
                 "not_back": "re-subscribed; the stream did not come back",
                 "removed": "THE RECEIVER IS REMOVED",
                 "not_removed": "the receiver was not removed; nothing changed",
                 "not_sent": "nothing was sent for it",
                 "partial": "stopped part-way; not every chosen subscription was re-subscribed",
                 "moved": "the configuration is not as before",
                 "failed": "failed during the run: read the device",
                 "refused": "nothing was sent"}
#: A run's record state, as History's operations source names it (`privileged.runs`).
RECORD_STATE = {"resubscribed": "done", "readded": "done", "unverified": "unverified",
                "not_back": "failed", "removed": "failed", "not_removed": "failed",
                "not_sent": "failed", "partial": "failed",
                "moved": "failed", "failed": "failed", "refused": "refused"}
#: A subscription's outcomes, worst first: the run's outcome is its worst subscription's, and
#: its words lead with it (`_overall`).
WORST_FIRST = ("removed", "moved", "not_removed", "not_sent", "not_back", "unverified")


class Refused(ValueError):
    """Nothing was sent; the words say why."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _and(items) -> str:
    items = list(items)
    return " and ".join([", ".join(items[:-1]), items[-1]]) if len(items) > 1 else (
        items[0] if items else "")


# ── The program, its hash and its authorisation ─────────────────────────────────────────────

def header(sub: str) -> str:
    return f"telemetry ietf subscription {sub}"


def session_lines(sub: str, line: str) -> list:
    """One session's batch: *line* (the receiver, or its ``no``) under its subscription."""
    return ["configure terminal", header(sub), f" {line}", "end"]


def unit_id(sub: str, readd: bool = False) -> str:
    """What a subscription's selection is named in its hash (Mode B's selected ids)."""
    return f"{'readd' if readd else 'resubscribe'}:{header(sub)}"


def unit_hash(unit: dict, readd: bool = False) -> str:
    """One subscription's hash as the preview shows it: its sessions and its selection."""
    from modules.nsot.deploy import command_fingerprint

    return command_fingerprint(_unit_program(unit, readd), [], [unit_id(unit["sub"], readd)])


def _unit_program(unit: dict, readd: bool) -> list:
    return list(unit["readd"]) if readd else list(unit["remove"]) + list(unit["readd"])


def authorised(units: list, reason: str, readd: bool = False) -> list:
    """Each removal's ``no receiver`` line with the person's reason (a re-add removes nothing,
    so it authorises nothing)."""
    from modules.nsot.authorisation import key

    if readd:
        return []
    return [{"line": key(f"no {u['line']}"), "reason": (reason or "").strip()} for u in units]


def program_of(units: list, readd: bool = False) -> list:
    """The whole program in the order it is sent: every chosen subscription's removal, in the
    order chosen, then every re-add (one subscription: its removal, then its re-add; a Re-add
    the receiver: its re-add alone). The wait between the two is not a line."""
    if readd:
        return [ln for u in units for ln in u["readd"]]
    return [ln for u in units for ln in u["remove"]] + [ln for u in units for ln in u["readd"]]


def program_hash(units: list, readd: bool = False) -> str:
    """The SELECTION's hash, as the card carries it: the whole program in its order and the ids
    chosen. One subscription more, one fewer, or another order is another hash."""
    from modules.nsot.deploy import command_fingerprint

    return command_fingerprint(program_of(units, readd), [],
                               [unit_id(u["sub"], readd) for u in units])


def run_hash(units: list, reason: str, readd: bool = False) -> str:
    """The run's hash: the whole program, in order, each removal authorised with the reason."""
    from modules.nsot.deploy import command_fingerprint

    return command_fingerprint(program_of(units, readd), authorised(units, reason, readd),
                               [unit_id(u["sub"], readd) for u in units])


def receiver_line(settings) -> str:
    """The subscription's receiver line exactly as committed intent holds it (stripped), the
    last one `diagnose_stream.RECEIVER` reads; ``""`` when intent holds none."""
    from modules.heal.diagnose_stream import RECEIVER

    found = [str(s).strip() for s in settings or [] if RECEIVER.match(str(s).strip())]
    return found[-1] if found else ""


def plan(network: str, device: str, subs, *, readd: bool = False, sources=None) -> dict:
    """What the operation would send on *device* for *subs*, and why it would refuse, read from
    Mercury's records alone (the inventory and committed intent), never the device:
    ``{"ok", "refusals", "device", "ip", "dialect", "units", "program", "hash", "sharing",
    "words"}``; each unit ``{"sub", "line", "address", "port", "protocol", "remove", "readd",
    "hash"}``. *program* is `program_of`'s (the batch's order) and *hash* the selection's
    (`program_hash`). *sharing* names each subscription intent declares that was NOT chosen and
    sends to the receiver address and port of a chosen one, ``[{"sub", "shares", "address",
    "port"}]``: it may keep the connection the chosen ones share."""
    from modules.heal import diagnose as D
    from modules.heal.diagnose_stream import receiver_of
    from modules.nsot import removal
    from modules.nsot.deploy import UnsendableCommand, assert_sendable

    src = sources or Sources(network)
    out = {"ok": False, "network": network, "device": device, "refusals": [], "units": [],
           "program": [], "hash": "", "sharing": [], "ip": "", "dialect": "", "readd": readd,
           "words": "", "dev": {}, "hv": {}}

    def refuse(words):
        out["refusals"].append(words + ". Nothing was sent")
        return out

    asked = list(dict.fromkeys(str(s).strip() for s in subs or [] if str(s).strip()))
    if not asked:
        return refuse("no subscription was chosen")
    if readd and len(asked) != 1:
        return refuse(f"Re-add the receiver adds one subscription's receiver, and "
                      f"{len(asked)} were given")
    dev = src.device(device) or {}
    if not dev:
        return refuse(f"{device or 'no device'} is not a device of {network}")
    out.update(dev=dev, ip=dev.get("ip", ""))
    intents, err = src.intents()
    if intents is None:
        return refuse(f"{network}'s committed intent could not be read ({err}), and the "
                      "receiver line is intent's, never typed")
    hv = intents.get(device)
    if not hv:
        return refuse(f"{device} has no committed intent in {network}, and the receiver line "
                      "is intent's, never typed")
    out["hv"] = hv
    try:
        dialect = D.dialect_of(hv.get("platform") or dev.get("device_type") or "", device)
    except D.Refused as exc:
        return refuse(str(exc))
    out["dialect"] = dialect
    declared = {str(s.get("subscription")): s.get("settings") or []
                for s in hv.get("telemetry") or [] if isinstance(s, dict)}
    for sub in asked:
        try:
            D.render("telemetry_receiver", dialect, sub=sub)
        except D.Refused as exc:
            refuse(str(exc))
            continue
        if sub not in declared:
            refuse(f"intent declares no telemetry subscription {sub} on {device} "
                   f"({len(declared)} declared)")
            continue
        line = receiver_line(declared[sub])
        r = receiver_of(declared[sub])
        if not line or r.get("why"):
            refuse(f"subscription {sub} on {device}: {r.get('why') or 'no receiver line'}")
            continue
        if not readd:
            why = removal.shape_refusal([header(sub)], " " + line, "leaf", dialect)
            if why:
                refuse(f"removing subscription {sub}'s receiver on {device} ({dialect}) is "
                       f"not measured: {why}")
                continue
        unit = {"sub": sub, "line": line, "address": r["address"], "port": r["port"],
                "protocol": r["protocol"], "vrf": r.get("vrf") or "",
                "remove": session_lines(sub, f"no {line}"), "readd": session_lines(sub, line)}
        unit["hash"] = unit_hash(unit, readd)
        out["units"].append(unit)
    if out["refusals"]:
        return out
    out["program"] = program_of(out["units"], readd)
    try:
        assert_sendable(out["program"])
    except UnsendableCommand as exc:
        return refuse(str(exc))
    out["hash"] = program_hash(out["units"], readd)
    # The subscriptions NOT chosen that send to a chosen one's receiver (intent's own lines:
    # `receiver_of` gives the address in one spelling, IPv4 or IPv6).
    chosen = {}
    for u in out["units"]:
        chosen.setdefault((u["address"], u["port"]), []).append(u["sub"])
    for other in sorted(declared, key=lambda x: (len(x), x)):
        if other in asked:
            continue
        r = receiver_of(declared[other])
        same = chosen.get((r.get("address"), r.get("port"))) if not r.get("why") else None
        if same and receiver_line(declared[other]):
            out["sharing"].append({"sub": other, "shares": list(same), "address": r["address"],
                                   "port": r["port"]})
    subs_w = _and(u["sub"] for u in out["units"])
    noun = "subscription" if len(out["units"]) == 1 else "subscriptions"
    out.update(ok=True, words=(f"add back {device}'s receiver for telemetry {noun} {subs_w}"
                               if readd else
                               f"re-subscribe {device}'s telemetry {noun} {subs_w}"))
    return out


def person_refusal(actor: str, actor_verified: str, person: bool) -> str:
    """Why the confirm is refused because it is not a verified person's, or ``""``.

    An allowlist, never a list of what to refuse: *actor_verified* must be one of the ways a
    request's identity is established (`identity.REQUEST_VERIFICATIONS`), as that identity
    stated it. ``none``, an empty kind, a host shell, a policy and any word this table does not
    hold are all refused, and nothing here assumes a kind that was not given."""
    from modules import identity

    if (person is True and actor and actor != identity.UNVERIFIED
            and isinstance(actor_verified, str)
            and actor_verified in identity.REQUEST_VERIFICATIONS):
        return ""
    return ("a telemetry re-subscribe is confirmed by a verified person, and this request is "
            f"not one (actor {actor or 'none'}, verified {actor_verified or 'none'}, "
            f"{'a person' if person is True else 'not a person'}): it takes a person signed in "
            "through the access proxy or with this installation's local account. Nothing was "
            "sent")


def refusal(p: dict, confirmed: dict, reason: str, readd: bool = False, *, program: str = "",
            previewed: str = "") -> str:
    """Why the confirm is refused with nothing sent, or ``""``: the plan's refusals; each
    subscription's hash against the one previewed (both named); for a re-subscribe, the
    SELECTION's hash (*program*, the one the card carried for the subscriptions it drew,
    *previewed*) against the program of the subscriptions sent now, both hashes and both
    selections named; a removal's reason that is not the shape of one
    (`authorisation.reason_problem`). A Re-add the receiver is one subscription's one send, so
    its own hash is its whole program."""
    from modules.nsot.authorisation import reason_problem

    if not p["ok"]:
        return "; ".join(p["refusals"])
    confirmed = confirmed or {}
    for u in p["units"]:
        was = str(confirmed.get(u["sub"]) or "")
        if was != u["hash"]:
            return (f"subscription {u['sub']}'s program changed since the preview you confirmed "
                    f"(confirmed {was or 'no hash'}, now {u['hash']}): its receiver in "
                    f"{p['device']}'s intent moved. Nothing was sent; preview again")
    if not readd and str(program or "") != p["hash"]:
        now = _and(u["sub"] for u in p["units"])
        # The selection the form said it previewed, said back only as subscription ids.
        was = _and([s.strip() for s in str(previewed or "").split(",")
                    if s.strip().isascii() and s.strip().isdigit()][:20])
        was = f"subscription {was}" if was else "no named selection"
        return (f"the selection is not the one previewed: the program you confirmed was "
                f"{program or 'no hash'}, for {was}, and the one asked for now is {p['hash']}, "
                f"for subscription {now}. The order of the removals and the re-adds is the "
                "selection's, so another selection is another program. Nothing was sent; "
                "preview again")
    if not readd:
        for a in authorised(p["units"], reason):
            why = reason_problem(a)
            if why:
                return f"a removal needs a stated reason: {why}. Nothing was sent"
    return ""


# ── Where it reads and sends (each replaceable in a test) ───────────────────────────────────

class Sources:
    """The inventory, committed intent, the device's sessions, the verify's three reads, the
    clock and the sleep."""

    def __init__(self, network: str, *, clock=time.time, sleep=time.sleep, session=None):
        """*session* (tests) is the reads engine's seam (`reads.run`'s)."""
        self.network, self.clock, self.sleep, self.session = network, clock, sleep, session
        self._read = None

    def device(self, host: str) -> dict:
        from modules import device_page
        from modules.nsot import listref

        try:
            _ref, dev = device_page.find_device(host, listref.resolve(self.network))
        except Exception:                             # noqa: BLE001 (no such device: refused)
            return {}
        return dev or {}

    def intents(self) -> tuple:
        """Committed intent, read once for this object: a card that plans several selections
        (the ticked ones, each one it lists, a removed receiver's re-add) reads it once."""
        from modules.heal.bounce import committed_intents_of

        if self._read is None:
            self._read = committed_intents_of(self.network)
        return self._read

    def opener(self, dev: dict):
        from modules.connection import open_ssh, stored_connection_params

        conn = open_ssh(stored_connection_params(dev), owner="heal:resubscribe")
        conn.enable()
        return conn

    def receiver(self, host: str, sub: str, actor: str, dialect: str) -> dict:
        """(a)'s read, through THE reads engine (recorded on History › Reads), in this thread so
        the operation's own hold covers it: ``{"state": "read"|"unread", "rows", "why",
        "run"}``."""
        from modules.heal import diagnose as D
        from modules.heal import diagnose_parse as P
        from modules.nsot import reads

        cmd = D.render("telemetry_receiver", dialect, sub=sub)
        try:
            rec = reads.run(self.network, [host], [cmd], actor, by=READS_BY, inline=True,
                            session=self.session,
                            purpose=f"telemetry re-subscribe: subscription {sub}'s receiver")
        except reads.Refused as exc:
            return {"state": "unread", "rows": None, "why": str(exc), "run": ""}
        r = (rec.get("results") or {}).get(host) or {}
        ans = next((a for a in r.get("answers") or [] if a.get("command") == cmd), None)
        if not ans or ans.get("state") != reads.ANSWERED:
            return {"state": "unread", "rows": None, "run": rec.get("id", ""),
                    "why": (ans or {}).get("why") or r.get("why") or r.get("state") or
                    "not answered"}
        got = P.parse("telemetry_receiver", ans.get("answer") or "")
        if got["state"] != P.PARSED:
            return {"state": "unread", "rows": None, "why": got["why"], "run": rec.get("id", "")}
        return {"state": "read", "rows": got["facts"]["receivers"], "why": "",
                "run": rec.get("id", "")}

    def series(self, host: str, sub: str) -> dict:
        from modules.heal.diagnose_stream import series_of

        return series_of(host, sub)

    def collector(self, address: str, port: int, addresses: list) -> dict:
        from modules.heal.diagnose_stream import read_collector

        return read_collector(address, port, addresses)

    def addresses(self, hv: dict) -> list:
        from modules.heal.diagnose_stream import _addresses

        return _addresses(hv)

    def values(self) -> dict:
        from modules.redact import known_secret_values

        return known_secret_values()


# ── The record ──────────────────────────────────────────────────────────────────────────────

def _record(network: str, rec: dict) -> dict:
    """Write the run's record in the operations' record History reads (`privileged.record`)."""
    from modules.nsot import privileged

    return privileged.record(network, rec)


def _in_flight(network: str, device: str) -> bool:
    """Whether a re-subscribe or a re-add holds *device* now (its run is going)."""
    from modules.nsot import device_ops

    try:
        h = device_ops.holder(network, device)
    except Exception:                                 # noqa: BLE001 (unread: not said to be)
        return False
    return bool(h) and h.get("operation") in (OPERATION, READD_OPERATION)


def removed_now(network: str, device: str) -> list:
    """The receivers a run left removed on *device* that no later run put back, ``[{"sub",
    "run"}]`` (each one the danger state and its Re-add the receiver). Judged per subscription,
    by the newest of *device*'s last 20 runs that SENT something for it: a refused run, and a
    subscription a run never touched or did not remove, say nothing about it, so a later run
    of ANOTHER subscription (or one refused) never hides a receiver still removed. A run left
    unfinished (Mercury restarted under it) counts each receiver whose removal it sent and
    whose re-add it did not read back; a run still going, holding the device, says nothing
    until it ends."""
    from modules.config import list_data_path
    from modules.nsot import privileged

    got = privileged.runs(network, device=device, limit=20, data_dir=list_data_path(network))
    going = None
    seen, out = set(), []
    for r in got["runs"]:                             # newest first
        if r.get("key") not in (KEY, READD_KEY) or not r.get("config_change"):
            continue
        unfinished = r.get("state") == "running"
        if unfinished:
            going = _in_flight(network, device) if going is None else going
            if going:
                continue
        for s in r.get("subscriptions") or []:
            sub = str(s.get("sub") or "")
            outcome = s.get("outcome") or ""
            if not sub or sub in seen or outcome in ("not_sent", "not_removed"):
                continue
            if not outcome:
                if not unfinished or s.get("removal") not in ("sent", "before"):
                    continue
                outcome = "resubscribed" if s.get("landed") is True else "removed"
            seen.add(sub)
            if outcome == "removed":
                out.append({"sub": sub, "run": r.get("id")})
    return sorted(out, key=lambda x: (len(x["sub"]), x["sub"]))


def _announce() -> None:
    try:
        from modules import invalidation
        invalidation.announce(invalidation.ANNOUNCERS[ANNOUNCER], by=ANNOUNCER)
    except Exception as exc:                          # noqa: BLE001 (a page's freshness only)
        log.info("resubscribe: a run recorded, not announced: %s", exc)


# ── The run ─────────────────────────────────────────────────────────────────────────────────

class _Run:
    def __init__(self, network: str, rec: dict, src, values: dict):
        self.network, self.rec, self.src, self.values = network, rec, src, values

    def mask(self, text: str) -> str:
        from modules.redact import redact_text

        return redact_text(text or "", self.values)

    def step(self, name: str, result: str, words: str, **more) -> None:
        self.rec["steps"].append(dict({"step": name, "result": result,
                                       "words": self.mask(words),
                                       "at": _iso(self.src.clock())}, **more))

    def finish(self, outcome: str, words: str) -> dict:
        self.rec.update(outcome=outcome, state=RECORD_STATE.get(outcome, "failed"),
                        why=self.mask(words), finished_at=self.src.clock())
        self.step("record", "ok", OUTCOME_WORDS.get(outcome, outcome))
        _record(self.network, self.rec)
        _announce()
        log.info("resubscribe: %s on %s/%s: %s", self.rec.get("actor"), self.network,
                 self.rec.get("device"), outcome)
        return self.rec


def apply(network: str, device: str, subs, *, actor: str, actor_verified: str, person: bool,
          confirmed: dict, program: str = "", previewed: str = "", reason: str = "",
          readd: bool = False, run_id: str = "", sources=None) -> dict:
    """Run the confirmed re-subscribe (or, with *readd*, the one-step Re-add the receiver) on
    *device*, holding it, as *actor*, a person verified as *actor_verified* (`person_refusal`:
    neither has a default): the run's record, written. *confirmed* is each subscription's hash
    and *program* the selection's, both as previewed (`refusal`). Never raises; a refusal is a
    record too, with nothing sent."""
    from modules.nsot import device_ops, reads

    src = sources or Sources(network)
    now = src.clock()
    not_a_person = person_refusal(actor, actor_verified, person)
    p = plan(network, device, subs, readd=readd, sources=src)
    rec = {"id": run_id or reads.new_id(), "list": network, "device": device,
           "key": READD_KEY if readd else KEY,
           "command": p["words"] or f"{'re-add' if readd else 're-subscribe'} telemetry on "
                                     f"{device}",
           # How the person was verified, as the request's identity stated it; one that
           # stated nothing is recorded "none", never a kind nobody gave.
           "actor": actor, "actor_verified": (actor_verified if isinstance(actor_verified, str)
                                              and actor_verified else "none"),
           "reason": (reason or "").strip(), "started_at": now,
           "finished_at": None, "state": "running", "outcome": "running",
           "at": _iso(now), "config_change": False, "hash": "", "program": [],
           "subscriptions": [], "steps": []}
    run = _Run(network, rec, src, src.values())
    if not_a_person:
        # Before the plan's refusals or the hash are said: a request that is not a verified
        # person's learns nothing about what a valid confirm would have been.
        run.step("hash", "refused", not_a_person)
        return run.finish("refused", not_a_person)
    why = refusal(p, confirmed, reason, readd, program=program, previewed=previewed)
    if why:
        run.step("hash" if p["ok"] else "plan", "refused", why)
        return run.finish("refused", why)
    run.step("plan", "ok", f"{p['words']}: each receiver from {device}'s committed intent"
                           + ("" if readd else f"; the removal measured on {p['dialect']}"))
    rec["hash"] = run_hash(p["units"], reason, readd)
    rec["program"] = [run.mask(x) for x in p["program"]]
    run.step("hash", "ok", "each subscription's program is the one previewed ("
             + ", ".join(f"{u['sub']}: {u['hash']}" for u in p["units"])
             + ("" if readd else f"), and the selection's is too ({p['hash']}")
             + f"); the run's hash, the reason in it: {rec['hash']}")
    op = READD_OPERATION if readd else OPERATION
    try:
        with device_ops.hold(network, device, op, actor, detail=p["words"], ip=p["ip"]):
            run.step("hold", "ok", f"{device} held for the whole operation")
            return _held(run, p, actor, readd)
    except device_ops.DeviceBusy as exc:
        run.step("hold", "refused", str(exc))
        return run.finish("refused", f"{exc}. Nothing was sent")
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.exception("resubscribe: %s on %s failed", network, device)
        if not rec["config_change"]:
            return run.finish("refused", f"{type(exc).__name__}: {exc}. Nothing was sent")
        left = _unfinished(run, device)
        return run.finish("failed", (f"the run failed once it had begun sending "
                                     f"({type(exc).__name__}: {exc}); whether each receiver is "
                                     "in place is not known: read the device's configuration "
                                     "before anything else"
                                     + (f". Taken as removed until read: {_and(left)}"
                                        if left else "")))


def _unfinished(run: _Run, device: str) -> list:
    """After a run that failed part-way: each subscription with no outcome gets the one its
    sends leave it in, so none is left removed unsaid. One whose removal was sent and whose
    re-add was not read back is ``removed`` (the card then leads with its Re-add the
    receiver); one put back and not verified is ``unverified``; one never sent is
    ``not_sent``. Returns the ids taken as removed."""
    left = []
    for g in run.rec.get("subscriptions") or []:
        if g.get("outcome"):
            continue
        sub = g.get("sub")
        if g.get("removal") in ("sent", "before") and g.get("landed") is not True:
            g.update(outcome="removed", words=run.mask(
                f"{device}'s receiver for {sub} is taken as removed: its removal was sent and "
                "the run failed before its re-add was read back. Re-add the receiver"))
            left.append(str(sub))
        elif g.get("landed") is True:
            g.update(outcome="unverified", words=run.mask(
                f"subscription {sub}'s receiver is back; the run failed before its stream was "
                "checked"))
        else:
            g.update(outcome="not_sent", words=f"subscription {sub}: nothing was sent for it")
    return left


def _held(run: _Run, p: dict, actor: str, readd: bool) -> dict:
    """The run, holding the device: the record before any send, the reads before, then the
    removals (every chosen subscription's), one wait, the re-adds, and each one's verify."""
    from modules.heal.bounce import Session

    src, rec, device = run.src, run.rec, p["device"]
    rec.update(config_change=True, started_at=src.clock(), at=_iso(src.clock()))
    run.step("started", "ok", "recorded before anything is sent, so the device's own "
                              "configuration lines during it are Mercury's")
    _record(run.network, rec)
    s = Session(run.network, p["dev"], "", actor, run.values,
                operation=READD_OPERATION if readd else OPERATION, detail=p["words"],
                label="telemetry re-subscribe", opener=src.opener, clock=src.clock)
    addresses = src.addresses(p["hv"])
    before = {}
    for u in p["units"]:
        before[u["sub"]] = {"receiver": src.receiver(device, u["sub"], actor, p["dialect"]),
                            "collector": src.collector(u["address"], u["port"], addresses)}
    running, why = _running(s)
    if running is None:
        run.step("before", "refused", f"{device}'s running configuration could not be read "
                                      f"({why}), and the run compares its end with it")
        rec["config_change"] = False
        return run.finish("refused", f"{device}'s running configuration could not be read "
                                     f"before ({why}). Nothing was sent")
    s.before = running
    run.step("before", "ok", "; ".join(_before_words(device, u, before[u["sub"]])
                                       for u in p["units"])
             + f"; the running configuration, {len(running.splitlines())} lines")
    # Each subscription's own record, kept from the first send on (`removal`: whether its
    # removal was sent; `landed`: whether its re-add was read back), so a run that fails
    # part-way still says which receivers it left removed (`_unfinished`).
    gots = {u["sub"]: {"sub": u["sub"], "line": run.mask(u["line"]), "sessions": [],
                       "verify": {}, "outcome": "", "words": "", "stale": [],
                       "removal": "before" if readd else "", "landed": None}
            for u in p["units"]}
    rec["subscriptions"] = list(gots.values())
    put = list(p["units"]) if readd else _remove_each(run, s, p, gots)
    _record(run.network, rec)
    if put and not readd:
        src.sleep(WAIT_S)
        run.step("wait", "ok", f"waited {WAIT_S} s after the last removal, before the "
                               f"re-add{'s' if len(put) > 1 else ''}")
    after, why = None, ""
    for u in put:
        g = gots[u["sub"]]
        g["landed"], after, why = put_back(run, s, p, u, g)
        if not g["landed"]:
            run.step("rollback", "failed", f"{device}'s receiver for {u['sub']} did not come "
                                           "back after the re-add and its one retry; Re-add "
                                           "the receiver is offered")
            g.update(outcome="removed", words=run.mask(
                f"{device}'s receiver for {u['sub']} is removed"
                + (f" (the configuration could not be read back after the retry: {why}, so it "
                   "may be)" if after is None else "")
                + f": `{u['line']}` did not land after the re-add and its one retry. Re-add "
                  "the receiver"))
        _record(run.network, rec)
    back = [u for u in put if gots[u["sub"]]["landed"]]
    if back:
        _as_before(run, s, p, put, gots, after, why, readd)
    for u in back:
        g = gots[u["sub"]]
        if g["outcome"]:                              # the configuration is not as before
            continue
        _verified(run, p, u, g, before[u["sub"]], addresses, actor, readd)
        _record(run.network, rec)
    outcome, words = _overall(list(gots.values()), bool(put), readd)
    return run.finish(outcome, words)


def _mine(u: dict) -> str:
    """A subscription's receiver line as the configuration comparison names it."""
    return f"{header(u['sub'])} :: {u['line']}"


def _remove_each(run: _Run, s, p: dict, gots: dict) -> list:
    """The removals: every chosen subscription's, one held send each, in the order chosen, the
    configuration read back after each. Returns the units whose removal was SENT, which the
    re-adds then put back. It stops at the first removal that could not be sent, changed
    nothing, could not be read back, or took more than its line: the subscriptions after it
    are never touched, and say so."""
    device, put, gone, halted = p["device"], [], [], ""
    several = len(p["units"]) > 1
    for u in p["units"]:
        sub, g = u["sub"], gots[u["sub"]]
        if halted:
            g.update(outcome="not_sent", words=run.mask(
                f"subscription {sub}: nothing was sent for it (the removals stopped at "
                f"subscription {halted})"))
            continue
        one = _send(s, u["remove"])
        g["sessions"].append({"session": 1, "lines": [run.mask(x) for x in u["remove"]],
                              **{k: one[k] for k in ("sent", "answer", "errors", "lost",
                                                     "why")}})
        if not one["sent"]:
            run.step("remove", "refused", f"subscription {sub}: {one['why']}. Nothing was sent")
            g.update(outcome="not_removed", words=run.mask(
                f"subscription {sub}'s first session could not be opened ({one['why']}): "
                "nothing was sent for it"
                + (f", and {device}'s configuration is as before" if not put else "")))
            halted = sub
            continue
        g["removal"] = "sent"
        after, why = _running(s)
        if after is None:
            run.step("remove", "unknown", f"subscription {sub}: sent; the configuration could "
                                          f"not be read back ({why}), so the re-add is sent "
                                          "to put it back whatever landed"
                     + (", and no further receiver is removed" if several else ""))
            put.append(u)
            halted = sub
            continue
        d = _diff(s, after)
        if sorted(d["only_before"]) == sorted(gone) and not d["only_now"]:
            g["removal"] = "not_landed"
            run.step("remove", "failed", f"subscription {sub}: the configuration read back "
                                         "unchanged"
                     + (f" (the device answered {one['errors'][0]})" if one["errors"] else ""))
            g.update(outcome="not_removed", words=run.mask(
                f"subscription {sub}'s receiver was not removed"
                + (f": {device} answered {one['errors'][0]}" if one["errors"] else
                   ": the configuration read back unchanged")
                + (f"; {device}'s configuration is as before, and nothing more was sent"
                   if not put else "; no further receiver was removed")))
            halted = sub
            continue
        put.append(u)
        exact = sorted(d["only_before"]) == sorted(gone + [_mine(u)]) and not d["only_now"]
        if exact:
            gone.append(_mine(u))
            run.step("remove", "ok", f"subscription {sub}: exactly its receiver line left "
                                     "(read back)")
            continue
        run.step("remove", "failed", (
            f"subscription {sub}: the removal changed more than its line "
            f"({len(d['only_before']) - len(gone)} line(s) gone, {len(d['only_now'])} added); "
            "the re-add is sent to put back what it can"
            + (", and no further receiver is removed" if several else "")))
        halted = sub
    return put


def _as_before(run: _Run, s, p: dict, put: list, gots: dict, after, why: str,
               readd: bool) -> None:
    """After the last re-add: the running configuration against the one read before. It must
    differ only by the receivers that did not come back (a Re-add the receiver: only by the
    line it added). Otherwise every receiver that is back is ``moved``, and is not verified."""
    device = p["device"]
    back = [u for u in put if gots[u["sub"]]["landed"]]
    if after is None:
        after, why = _running(s)
    if after is None:
        for u in back:
            gots[u["sub"]]["unread_after"] = why
        run.step("re-add", "unknown", (f"{_subs(back)}: back (each read back); the "
                                       "configuration could not be read after the last re-add "
                                       f"({why}), so whether it is as before could not be told"))
        return
    d = _diff(s, after)
    if readd:
        missing = list(d["only_before"])
        added = [x for x in d["only_now"] if x not in [_mine(u) for u in put]]
    else:
        still_out = [_mine(u) for u in put if not gots[u["sub"]]["landed"]]
        missing = [x for x in d["only_before"] if x not in still_out]
        added = list(d["only_now"])
    ok = not missing and not added
    run.step("re-add", "ok" if ok else "failed", (
        f"{_subs(back)}: {'its receiver is' if len(back) == 1 else 'their receivers are'} "
        "back; the running configuration "
        + (("is as before, line for line" if len(back) == len(put) else
            "differs from before only by the receivers that did not come back") if ok else
           f"differs from before ({len(missing)} line(s) missing, {len(added)} added)")))
    if ok:
        return
    for u in back:
        g = gots[u["sub"]]
        g["moved"] = {"missing": [run.mask(x) for x in missing],
                      "added": [run.mask(x) for x in added]}
        g.update(outcome="moved", words=run.mask(
            f"subscription {u['sub']}'s receiver is back, but {device}'s running "
            f"configuration is not as before: {len(missing)} line(s) missing, {len(added)} "
            "added. Nothing was saved, so its startup configuration is as it was"))


def _subs(units: list) -> str:
    return ("subscription " if len(units) == 1 else "subscriptions ") + _and(
        u["sub"] for u in units)


def _verified(run: _Run, p: dict, u: dict, g: dict, before: dict, addresses: list,
              actor: str, readd: bool) -> None:
    """One subscription whose receiver is back: its verify, and its outcome from it."""
    device, sub = p["device"], u["sub"]
    v = verify(run, p, u, before, addresses, actor)
    g["verify"], g["stale"] = v["checks"], v["stale"]
    stale = (f"; flagged: {'; '.join(v['stale'])}" if v["stale"] else "")
    unread = g.get("unread_after")
    if v["outcome"] == "fail":
        g.update(outcome="not_back", words=run.mask(
            f"re-subscribed {sub}; the stream did not come back within {VERIFY_BOUND_S} s "
            f"({v['words']}). {device}'s configuration is as intent holds it" + stale))
    elif v["outcome"] == "cant_tell":
        g.update(outcome="unverified", words=run.mask(f"re-subscribed {sub}; {v['words']}"
                                                      + stale))
    elif unread:
        g.update(outcome="unverified", words=run.mask(
            f"re-subscribed {sub}: {v['words']}; whether {device}'s configuration is as before "
            f"could not be told ({unread})" + stale))
    else:
        g.update(outcome="readded" if readd else "resubscribed",
                 words=run.mask(f"re-subscribed {sub}: {v['words']}" + stale))


def _overall(gots: list, sent: bool, readd: bool) -> tuple:
    """``(outcome, words)`` of the run from its subscriptions': the worst one's outcome, its
    words first, never green over a partial. A removal that stopped the run after others were
    removed and put back is ``partial``; with nothing removed at all it is ``not_removed``."""
    rank = {o: i for i, o in enumerate(WORST_FIRST)}
    ordered = sorted(gots, key=lambda g: rank.get(g["outcome"], len(rank)))
    words = "; ".join(g["words"] for g in ordered if g["words"])
    worst = ordered[0]["outcome"] if ordered else "failed"
    if worst in ("not_removed", "not_sent"):
        return ("partial" if sent else "not_removed"), words
    if worst in rank:
        return worst, words
    return ("readded" if readd else "resubscribed"), words


def _before_words(device: str, u: dict, b: dict) -> str:
    r, c = b["receiver"], b["collector"]
    dev = ("not read (" + r["why"] + ")" if r["state"] != "read" else
           "; ".join(f"{x['state']} on connection {x['connection'] or 'none'}"
                     for x in r["rows"]) or "no receiver")
    col = (f"{len(c.get('sessions') or [])} session(s) from {device}" if c.get("state") == "read"
           else f"not read ({c.get('why')})")
    return f"subscription {u['sub']}: its receiver {dev}; the collector {col}"


def _running(s) -> tuple:
    """``(text, why)``: the running configuration on a new session, or ``(None, why)``."""
    from modules.heal.bounce import _close

    try:
        conn = s.open()
    except Exception as exc:                          # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    try:
        text = s.read(conn, "show running-config")
        return (text, "") if text.strip() else (None, "the device answered nothing")
    except Exception as exc:                          # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    finally:
        _close(conn)


def _send(s, lines: list) -> dict:
    """One session: open, the batch as one held send, close. ``{"sent", "answer", "errors",
    "lost", "why"}``; *sent* False when the session did not open (nothing was sent)."""
    from modules.heal.bounce import _close, device_errors

    try:
        conn = s.open()
    except Exception as exc:                          # noqa: BLE001
        return {"sent": False, "answer": "", "errors": [], "lost": "",
                "why": f"the session could not be opened ({type(exc).__name__}: {exc})"}
    try:
        answer, lost = s.send(conn, lines)
    finally:
        _close(conn)
    return {"sent": True, "answer": s.mask(answer), "errors": device_errors(answer),
            "lost": lost, "why": ""}


def _diff(s, running: str) -> dict:
    from modules.nsot import roundtrip

    got = roundtrip.configs_equivalent(s.before, running)
    return {"equal": got["equal"], "only_before": got["only_left"], "only_now": got["only_right"]}


def put_back(run: _Run, s, p: dict, u: dict, got: dict) -> tuple:
    """The re-add and its rollback: the second session, read back, and sent once more when the
    receiver is not in the configuration read back. ``(landed, running, why)``."""
    device, sub = p["device"], u["sub"]
    landed, after, why = False, None, ""
    for attempt in (1, 2):
        two = _send(s, u["readd"])
        got["sessions"].append({"session": 2, "attempt": attempt,
                                "lines": [run.mask(x) for x in u["readd"]],
                                **{k: two[k] for k in ("sent", "answer", "errors", "lost",
                                                       "why")}})
        after, why = _running(s)
        landed = bool(after is not None and _holds(after, sub, u["line"]))
        if landed:
            break
        run.step("re-add", "failed", (
            f"subscription {sub}: attempt {attempt}: "
            + (two["why"] if not two["sent"] else
               f"the configuration could not be read back ({why})" if after is None else
               "the receiver is not in the configuration read back"
               + (f" ({device} answered {two['errors'][0]})" if two["errors"] else ""))
            + ("; sent once more" if attempt == 1 else "")))
    return landed, after, why


def _holds(running: str, sub: str, line: str) -> bool:
    """Whether the running configuration holds *line* under *sub*'s subscription."""
    head, inside = header(sub), False
    for raw in (running or "").splitlines():
        if raw and not raw[0].isspace():
            inside = raw.strip() == head
            continue
        if inside and raw.strip() == line:
            return True
    return False


# ── Verify ──────────────────────────────────────────────────────────────────────────────────

def verify(run: _Run, p: dict, u: dict, before: dict, addresses: list, actor: str) -> dict:
    """The three checks of one subscription, read until each passes or `VERIFY_BOUND_S` ends:
    ``{"outcome": "pass"|"fail"|"cant_tell", "words", "checks", "stale"}``. A check whose last
    read could not be read is ``cant_tell``; one read and not passing at the bound is ``fail``.
    """
    src, device, sub = run.src, p["device"], u["sub"]
    start = src.clock()
    deadline = start + VERIFY_BOUND_S
    checks = {k: {"state": "cant_tell", "words": "not read"} for k in
              ("device", "stream", "collector")}
    stale = []
    while True:
        if checks["device"]["state"] != "pass":
            checks["device"] = _device_check(device, sub, before["receiver"],
                                             src.receiver(device, sub, actor, p["dialect"]))
        if checks["stream"]["state"] != "pass":
            checks["stream"] = _stream_check(device, sub, src.series(device, sub))
        if checks["collector"]["state"] != "pass":
            checks["collector"], stale = _collector_check(
                device, u, before["collector"], src.collector(u["address"], u["port"],
                                                              addresses))
        if all(c["state"] == "pass" for c in checks.values()) or src.clock() >= deadline:
            break
        src.sleep(min(POLL_S, max(0.0, deadline - src.clock())))
    took = round(src.clock() - start)
    for c in checks.values():
        if c["state"] == "waiting":
            c["state"] = "fail"
    states = [c["state"] for c in checks.values()]
    outcome = "fail" if "fail" in states else "cant_tell" if "cant_tell" in states else "pass"
    words = "; ".join(f"{name}: {c['words']}" for name, c in checks.items())
    run.step("verify", {"pass": "ok", "fail": "failed", "cant_tell": "unknown"}[outcome],
             f"subscription {sub}, {took} s: {words}", checks=checks, stale=stale)
    return {"outcome": outcome, "words": words if outcome != "pass" else
            f"the device, the stream and the collector each say it is back ({took} s)",
            "checks": checks, "stale": stale}


def _device_check(device: str, sub: str, was: dict, now: dict) -> dict:
    """(a): State Connected on a connection id that is not one read before the operation."""
    if now.get("state") != "read":
        return {"state": "cant_tell", "words": f"{device}'s receiver could not be read "
                                               f"({now.get('why')})"}
    rows = now.get("rows") or []
    if not rows:
        return {"state": "waiting", "words": f"{device} holds no receiver for {sub}"}
    up = [r for r in rows if r.get("connected")]
    if not up:
        r = rows[0]
        return {"state": "waiting", "words": f"{device} reads its receiver {r['state']}"
                + (f" ({r['explanation']})" if r.get("explanation") else "")}
    if was.get("state") != "read":
        return {"state": "cant_tell", "words": (
            f"{device} reads its receiver Connected on connection {up[0]['connection']}, and "
            f"the connection before was not read ({was.get('why')}), so a new one cannot be "
            "told")}
    old = {r.get("connection") for r in was.get("rows") or []}
    new = [r for r in up if r.get("connection") and r["connection"] not in old]
    if new:
        return {"state": "pass", "words": (f"{device} reads its receiver Connected on "
                                           f"connection {new[0]['connection']}, a new one "
                                           f"(before: {_and(sorted(x for x in old if x)) or 'none'})")}
    return {"state": "waiting", "words": (f"{device} reads its receiver Connected on connection "
                                          f"{up[0]['connection']}, the same connection as "
                                          "before: Connected is not a stream")}


def _stream_check(device: str, sub: str, got: dict) -> dict:
    """(b): the subscription's series in Prometheus."""
    state = got.get("state")
    if state == "present":
        return {"state": "pass", "words": f"subscription {sub}'s series is in Prometheus "
                                          f"({got.get('why')})"}
    if state == "absent":
        return {"state": "waiting", "words": f"subscription {sub}'s series is not in Prometheus "
                                             f"({got.get('why')})"}
    return {"state": "cant_tell", "words": f"Prometheus could not be read ({got.get('why')})"}


def _collector_check(device: str, u: dict, was: dict, now: dict) -> tuple:
    """(c): a new ESTABLISHED session from the device on the stream's port (by remote port),
    receiving when its last receive is read; and the stale flags. ``(check, stale)``."""
    from modules.heal.diagnose_stream import ESTABLISHED, receiving_now

    where = f"{u['address']} port {u['port']}"
    if now.get("state") != "read":
        return {"state": "cant_tell", "words": f"the collector at {where} could not be read "
                                               f"({now.get('why')})"}, []
    if was.get("state") != "read":
        return {"state": "cant_tell", "words": (f"the collector at {where} was not read before "
                                                f"({was.get('why')}), so a new session cannot be "
                                                "told")}, []
    old = {(s["remote"], s["rport"]) for s in was.get("sessions") or []}
    est = [s for s in now.get("sessions") or [] if s.get("state") == ESTABLISHED]
    new = [s for s in est if (s["remote"], s["rport"]) not in old]
    stale = []
    for s in est:
        if (s["remote"], s["rport"]) in old and receiving_now(s) is not True:
            stale.append(f"stale half-open: the session from {s['remote']} port {s['rport']}, "
                         "there before the operation, still stands"
                         + (f" with nothing received for {s['lastrcv_ms'] // 1000} s"
                            if s.get("lastrcv_ms") is not None else
                            " (its last receive not read)"))
    live = [s for s in new if receiving_now(s) is not False]
    if live:
        s = live[0]
        rcv = receiving_now(s)
        return {"state": "pass", "words": (
            f"a new session from {s['remote']} port {s['rport']} on {where}"
            + (f", receiving ({s['lastrcv_ms']} ms since its last segment)" if rcv else
               " (its last receive not read)"))}, stale
    if new:
        return {"state": "waiting", "words": (f"a new session from {new[0]['remote']} port "
                                              f"{new[0]['rport']} on {where}, nothing received "
                                              "on it yet")}, stale
    return {"state": "waiting", "words": f"no new session from {device} on {where}"}, stale


# ── Started as a job ────────────────────────────────────────────────────────────────────────

def start(network: str, device: str, subs, *, actor: str, actor_verified: str, person: bool,
          confirmed: dict, program: str = "", previewed: str = "", reason: str = "",
          readd: bool = False) -> dict:
    """Refuse now (``{"refused": why}``, nothing sent) or start the run as a job: ``{"job",
    "run"}``. *confirmed* and *program* are the hashes the card carried (each subscription's,
    and the selection's; `refusal`). *actor_verified* and *person* are the request's own
    (`person_refusal`), read there once; the job is started by the one job starter (`capture_job.start`), which carries
    the request's verified identity into its thread (`identity.carried`), so the reads the run
    records and anything it commits name the person as the request verified them."""
    from modules.nsot import capture_job, reads

    why = person_refusal(actor, actor_verified, person)
    if why:
        return {"refused": why, "not_a_person": True}
    p = plan(network, device, subs, readd=readd)
    why = refusal(p, confirmed, reason, readd, program=program, previewed=previewed)
    if why:
        return {"refused": why}
    run_id = reads.new_id()
    subs = [u["sub"] for u in p["units"]]
    job = capture_job.start(network, f"{p['words']}", actor,
                            lambda job_id: {"run": apply(network, device, subs, actor=actor,
                                                         actor_verified=actor_verified,
                                                         person=person, confirmed=confirmed,
                                                         program=program, previewed=previewed,
                                                         reason=reason, readd=readd,
                                                         run_id=run_id)["id"]},
                            kind="telemetry re-subscribe", announce_keys=ANNOUNCE_KEYS,
                            announcer=ANNOUNCER)
    return {"job": job, "run": run_id}
