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

**The collector step** (C3078, C3111; the operator, 2026-11-14: "Close the collector's stale
session for <device>, then re-subscribe"). A half-open stream can stay lost through a
re-subscribe: the collector on Mercury's host still holds the device's TCP session established
and idle while the device's own connection reads Disconnecting (a lab router, measured 2026-11-14:
connection 496 "Disconnecting", the collector's session from it idle 2,130 s), and the device
cannot dial again until that socket is closed. The same operation with the step on
(`COLLECTOR_KEY`, ``collector`` in `plan`, `apply` and `start`; one home for the receivers'
writes) first closes that one session:
- **its preview** (`plan`) reads the collector's sessions on the receiver's port from the
  device's addresses (`diagnose_stream.read_collector`, Mercury's own host, no device) and
  asks the root-owned close helper's DRY RUN (`collector_close.request` with ``dry_run``) to
  name the one session it would close, both ends and ports; refused, with nothing sent, unless
  exactly one established session stands and is idle (nothing received inside the stream's
  window) and the dry run answers ``would_close``;
- **its hash** binds that session's two ends with the program (`close_id`, in the selection's
  hash): a session that moved before the confirm (the device dialled again on another port)
  is another hash, refused, naming both sessions;
- **its apply**, holding the device and before any receiver is touched: the close through the
  helper (`collector_close.request`, its code, exit code and words kept as the run's receipt,
  ``collector_close``), the helper reading it back gone; then the device's connection to the
  collector read until the one that read Disconnecting is gone (`show telemetry internal
  connection`, C3640, within `GONE_BOUND_S`); then the re-subscribe as above. A close the
  helper does not answer ``closed`` stops the run there, nothing sent to the device
  (``not_closed``). The closed socket cannot be put back, and needs no undo: the device dials
  a new session, which the verify reads.
"""

import logging
import time

log = logging.getLogger(__name__)

KEY, READD_KEY = "telemetry-resubscribe", "telemetry-readd"
#: The re-subscribe with the collector step (C3078): its catalog key and its runs' record key.
COLLECTOR_KEY = "telemetry-collector-resubscribe"
#: Every key this module records a run under (History, the run card, the fix-it attempts).
RUN_KEYS = (KEY, READD_KEY, COLLECTOR_KEY)
#: The hold's operation words (`device_ops.hold`), each a device-changing operation.
OPERATION, READD_OPERATION = "telemetry re-subscribe", "telemetry receiver re-add"
COLLECTOR_OPERATION = "telemetry collector close and re-subscribe"
#: The collector step's title, in the operator's words (2026-11-14).
COLLECTOR_TITLE = "Close the collector's stale session for {device}, then re-subscribe"
#: After the close, the device's connection to the collector is read until the one that read
#: Disconnecting is gone, every `GONE_POLL_S`, for at most `GONE_BOUND_S`. UNMEASURED: no close
#: has been run on a device, so the bound is reasoned (the device's own TCP stack sees the
#: collector's reset at once; 60 s is six of its polls); the measurement that sets it is the
#: first run's time from the close to the connection gone, kept in its record (the ``gone``
#: step's ``took_s``), then 2.5 times that (C3643).
GONE_BOUND_S = 60
GONE_POLL_S = 5
GONE_WHY = ("reasoned, not measured: no close has been run on a device yet; the first run's "
            "time to the connection gone sets it (C3643)")
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
#: The reads engine's kind for the operation's device reads (`reads.run`'s *by*,
#: `reads.OPERATION`): the operation asks them, never the person as a Show commands run of
#: their own (the operator, 2026-11-11). Each is the run's (`reads.within`, in `apply`), and
#: the run's record names the person.
READS_BY = "operation"
#: Where the run's record is kept, as its reads name it (`reads.part`'s *record*).
RECORD = "privileged"
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
#: Each step in two to four words, for its column on the stepper (the operator, 2026-11-11:
#: "short labels (2-4 words: 'Read intent', 'Hold <device>', 'Remove 101', 'Wait 10 s', 'Re-add',
#: 'Verify 101', 'Record') ... No full sentences in the step columns"); the long words above
#: are its hover. `{device}` and `{subs}` are the run's own (`step_labels`).
STEP_LABELS = {"plan": "Read intent", "hash": "Check hashes", "hold": "Hold {device}",
               "started": "Record start", "before": "Read before", "remove": "Remove {subs}",
               "wait": f"Wait {WAIT_S} s", "re-add": "Re-add", "verify": "Verify {subs}",
               "rollback": "Roll back", "record": "Record", "close": "Close session",
               "gone": "Await device"}
#: The re-subscribe with the collector step (C3078): the close and the wait for the device's
#: connection, between the reads before and the first removal.
COLLECTOR_STEPS = (
    ("plan", "Read each subscription's receiver from committed intent, the collector's one "
             "stale session from the device, and the close helper's dry run naming it"),
    ("hash", "Recompute each subscription's program and the session to close, and compare "
             "the hashes"),
    ("hold", "Hold the device for the whole operation"),
    ("started", "Record the run before anything is sent"),
    ("before", "Read before: the receiver's state and connection, the device's telemetry "
               "connections, the collector's sessions, the running configuration"),
    ("close", "Close the collector's one stale session through the root-owned close helper, "
              "which reads it back gone"),
    ("gone", f"Read the device's telemetry connections until the one that read Disconnecting "
             f"is gone, for at most {GONE_BOUND_S} s"),
    ("remove", "Remove every chosen receiver, one held send each; read back after each that "
               "exactly the lines removed so far left"),
    ("wait", f"Wait {WAIT_S} s, once, after the last removal"),
    ("re-add", "Add every receiver back, one held send each, once more if it did not land; "
               "read back the configuration as before"),
    ("verify", "Verify each within 290 s: the device's state, the stream's series, the "
               "collector's session"),
    ("rollback", "A removal that fails stops the removals and those removed are added back; a "
                 "receiver that did not come back is said, with Re-add the receiver"),
    ("record", "Record the outcome, each subscription's own, and the close helper's receipt"))


def steps_for(key: str) -> tuple:
    """The steps a run of *key* declares (`RUN_KEYS`)."""
    return {READD_KEY: READD_STEPS, COLLECTOR_KEY: COLLECTOR_STEPS}.get(key, STEPS)
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
            "partial", "moved", "readded", "failed", "refused", "not_closed")
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
                 "refused": "nothing was sent",
                 "not_closed": "the collector's session was not closed; nothing was sent to "
                               "the device"}
#: A run's record state, as History's operations source names it (`privileged.runs`).
RECORD_STATE = {"resubscribed": "done", "readded": "done", "unverified": "unverified",
                "not_back": "failed", "removed": "failed", "not_removed": "failed",
                "not_sent": "failed", "partial": "failed",
                "moved": "failed", "failed": "failed", "refused": "refused",
                "not_closed": "failed"}
#: A subscription's outcomes, worst first: the run's outcome is its worst subscription's, and
#: its words lead with it (`_overall`).
WORST_FIRST = ("removed", "moved", "not_removed", "not_sent", "not_back", "unverified")


def step_labels(device: str, subs) -> dict:
    """`STEP_LABELS` for one run: its device, and its subscriptions by id where one or two
    were chosen, else by how many (a column's label stays within four words)."""
    from modules import run_stepper

    subs = [str(s) for s in subs or [] if str(s)]
    named = (", ".join(subs) if 0 < len(subs) <= 2 else
             f"{len(subs)} streams" if subs else "streams")
    return run_stepper.labels_for(STEP_LABELS, device=device, subs=named)


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


def close_id(close: dict) -> str:
    """The collector step's selection, as its hash names it: the one session to close, both
    ends and ports, as the close helper's dry run named them (`plan`'s ``close``)."""
    return f"collector-close:{close['local']}<-{close['remote']}"


def _selected(units: list, readd: bool, close: dict = None) -> list:
    return [unit_id(u["sub"], readd) for u in units] + ([close_id(close)] if close else [])


def program_hash(units: list, readd: bool = False, close: dict = None) -> str:
    """The SELECTION's hash, as the card carries it: the whole program in its order and the ids
    chosen, and with the collector step the one session it closes (`close_id`). One
    subscription more, one fewer, another order, or another session is another hash."""
    from modules.nsot.deploy import command_fingerprint

    return command_fingerprint(program_of(units, readd), [], _selected(units, readd, close))


def run_hash(units: list, reason: str, readd: bool = False, close: dict = None) -> str:
    """The run's hash: the whole program, in order, each removal authorised with the reason,
    and the session the collector step closes."""
    from modules.nsot.deploy import command_fingerprint

    return command_fingerprint(program_of(units, readd), authorised(units, reason, readd),
                               _selected(units, readd, close))


def receiver_line(settings) -> str:
    """The subscription's receiver line exactly as committed intent holds it (stripped), the
    last one `diagnose_stream.RECEIVER` reads; ``""`` when intent holds none."""
    from modules.heal.diagnose_stream import RECEIVER

    found = [str(s).strip() for s in settings or [] if RECEIVER.match(str(s).strip())]
    return found[-1] if found else ""


def plan(network: str, device: str, subs, *, readd: bool = False, collector: bool = False,
         sources=None) -> dict:
    """What the operation would send on *device* for *subs*, and why it would refuse, read from
    Mercury's records alone (the inventory and committed intent), never the device; with
    *collector* (the collector step, C3078), also the collector's sessions on Mercury's host and
    the close helper's dry run, which closes nothing (``close``, `_close_plan`):
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
           "words": "", "dev": {}, "hv": {}, "collector": collector is True, "close": {}}

    def refuse(words):
        out["refusals"].append(words + ". Nothing was sent")
        return out

    asked = list(dict.fromkeys(str(s).strip() for s in subs or [] if str(s).strip()))
    if not asked:
        return refuse("no subscription was chosen")
    if readd and collector:
        return refuse("Re-add the receiver adds one receiver back, and takes no collector step")
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
    if collector:
        close, why = _close_plan(network, device, out["units"], hv, src)
        if why:
            return refuse(why)
        out["close"] = close
    out["hash"] = program_hash(out["units"], readd, out["close"] or None)
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
                               f"close the collector's stale session for {device}, then "
                               f"re-subscribe its telemetry {noun} {subs_w}" if collector else
                               f"re-subscribe {device}'s telemetry {noun} {subs_w}"))
    return out


def _close_plan(network: str, device: str, units: list, hv: dict, src) -> tuple:
    """``(close, refusal)``: the one session the collector step would close, or why there is
    none to close, read on Mercury's host alone (no device): the collector's sessions on the
    chosen receivers' one address and port, from the device's addresses
    (`diagnose_stream.read_collector`), exactly one ESTABLISHED and idle (nothing received
    inside the stream's window, `receiving_now`), and the close helper's DRY RUN naming it
    (`collector_close.request` with ``dry_run``: it closes nothing). *close* is ``{"peer",
    "port", "local", "remote", "collector", "quiet_s", "dry_run"}``: the device's address and
    port, the two ends as the helper named them, and the dry run's own answer."""
    import ipaddress

    from modules.heal.diagnose_stream import ESTABLISHED, receiving_now
    from modules.nsot import reads

    ends = sorted({(u["address"], u["port"]) for u in units})
    if len(ends) != 1:
        return {}, (f"the collector step closes one session, to one receiver, and the chosen "
                    f"subscriptions send to {len(ends)} receivers "
                    f"({_and(f'{a} port {p}' for a, p in ends)}): choose those of one")
    address, port = ends[0]
    where = f"{address} port {port}"
    if ipaddress.ip_address(address).version != 4:
        return {}, (f"the collector at {where} is an IPv6 address, and the close helper serves "
                    "IPv4 only (C3118), so the collector step is not offered for it")
    got = src.collector(address, port, src.addresses(hv)) or {}
    if got.get("state") != "read":
        return {}, (f"the collector's sessions on {where} could not be read "
                    f"({got.get('why') or 'not read'}), and the step closes one it read")
    if not got.get("listening"):
        return {}, f"nothing on Mercury's host listens on {where}, so no session stands there"
    est = [s for s in got.get("sessions") or [] if s.get("state") == ESTABLISHED]
    if not est:
        return {}, (f"the collector holds no established session from {device} on {where}: "
                    "there is nothing to close, and Re-subscribe alone is the fix")
    live = [s for s in est if receiving_now(s) is True]
    unread = [s for s in est if receiving_now(s) is None]
    idle = [s for s in est if receiving_now(s) is False]
    if live:
        s = live[0]
        return {}, (f"the collector's session from {s['remote']} port {s['rport']} on {where} "
                    f"received data {int(s['lastrcv_ms']) // 1000} s ago: it carries data, so "
                    "it is not stale and is never closed")
    if unread:
        s = unread[0]
        return {}, (f"the collector's session from {s['remote']} port {s['rport']} on {where} "
                    "has no last receive read (the kernel's socket diagnostics were not read), "
                    "so whether it is stale cannot be told")
    if len(idle) > 1:
        each = _and(f"{x['remote']} port {x['rport']}" for x in idle)
        return {}, (f"the collector holds {len(idle)} idle sessions from {device} on {where} "
                    f"({each}), and the step closes exactly one")
    s = idle[0]
    dry = src.close(s["remote"], s["rport"], dry_run=True, run_id=reads.new_id())
    pair = dry.get("tuple") if isinstance(dry.get("tuple"), dict) else {}
    if dry.get("code") != "would_close" or dry.get("ok") is not True or not (
            pair.get("local") and pair.get("peer")):
        return {}, (f"the close helper's dry run for the session from {s['remote']} port "
                    f"{s['rport']} answered {dry.get('code') or 'nothing'} (exit "
                    f"{dry.get('exit')}): {dry.get('words') or 'no words'}")
    return {"peer": s["remote"], "port": int(s["rport"]), "local": pair["local"],
            "remote": pair["peer"], "collector": where, "address": address,
            "collector_port": int(port),
            "quiet_s": int(s["lastrcv_ms"]) // 1000,
            "dry_run": {k: dry.get(k) for k in ("code", "exit", "words", "at")}}, ""


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
            previewed: str = "", previewed_close: str = "") -> str:
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
    close = p.get("close") or {}
    if close:
        # The collector step: the session the person confirmed closing (*previewed_close*, the
        # device's end as the card drew it) against the one the collector holds now, and the
        # selection's hash, which holds the session's two ends, against the one confirmed.
        was = str(previewed_close or "").strip()[:60]
        was = was if was and all(ch in "0123456789abcdefABCDEF.:[]" for ch in was) else ""
        if was != close["remote"] or str(program or "") != p["hash"]:
            return (f"the collector's session is not the one previewed: you confirmed closing "
                    f"the session from {was or 'no session named'} (program {program or 'no '
                    'hash'}), and the one the collector holds now is from {close['remote']} to "
                    f"{close['local']} (program {p['hash']}). Nothing was sent; preview again")
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
        """(a)'s read, through THE reads engine (masked and kept in its store, as the run's:
        `reads.within` in `apply`), in this thread so the operation's own hold covers it:
        ``{"state": "read"|"unread", "rows", "why", "run"}``, *run* the reads store's id the
        run's record names the read by."""
        from modules.heal import diagnose_parse as P
        from modules.nsot import reads

        cmd = receiver_command(dialect, sub)
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

    def close(self, peer: str, port: int, *, dry_run: bool, run_id: str) -> dict:
        """The collector step's one request to the root-owned close helper
        (`collector_close.request`: ``sudo -n`` and its request file), a dry run or the close."""
        from modules.heal import collector_close

        return collector_close.request(peer, port, dry_run=dry_run, run_id=run_id)

    def connections(self, host: str, actor: str, dialect: str) -> dict:
        """The device's telemetry connections (C3640's read, `show telemetry internal
        connection`), through THE reads engine as the operation's, in this thread so its hold
        covers it: ``{"state": "read"|"unread", "rows", "why", "run"}``."""
        from modules.heal import diagnose as D
        from modules.heal import diagnose_parse as P
        from modules.nsot import reads

        cmd = D.render("telemetry_connection", dialect)
        try:
            rec = reads.run(self.network, [host], [cmd], actor, by=READS_BY, inline=True,
                            session=self.session,
                            purpose="the collector step: the device's telemetry connections")
        except reads.Refused as exc:
            return {"state": "unread", "rows": None, "why": str(exc), "run": ""}
        r = (rec.get("results") or {}).get(host) or {}
        ans = next((a for a in r.get("answers") or [] if a.get("command") == cmd), None)
        if not ans or ans.get("state") != reads.ANSWERED:
            return {"state": "unread", "rows": None, "run": rec.get("id", ""),
                    "why": (ans or {}).get("why") or r.get("why") or r.get("state") or
                    "not answered"}
        got = P.parse("telemetry_connection", ans.get("answer") or "")
        if got["state"] != P.PARSED:
            return {"state": "unread", "rows": None, "why": got["why"], "run": rec.get("id", "")}
        return {"state": "read", "rows": got["facts"]["connections"], "why": "",
                "run": rec.get("id", "")}

    def values(self) -> dict:
        from modules.redact import known_secret_values

        return known_secret_values()


def receiver_command(dialect: str, sub: str) -> str:
    """(a)'s read of one subscription's receiver, as the reads engine is asked it and the
    run's record names it."""
    from modules.heal import diagnose as D

    return D.render("telemetry_receiver", dialect, sub=sub)


# ── The record ──────────────────────────────────────────────────────────────────────────────

#: The field of a run's record naming the incident its confirm was pressed in, the attempt's
#: number and the proposal it runs (C3106), as the incident page's section carries it
#: (`modules/fixit/section.confirm_link`): its keys, each one's kind. This module reads nothing
#: of the fix-it path (section 12's scan of modules/heal/): it keeps what the confirm sent,
#: held to this shape.
FIXIT_FIELD = "fixit"
FIXIT_KEYS = {"incident": str, "attempt": int, "proposal": str, "different": str,
              "repeats": int}


def fixit_field(fixit) -> dict:
    """*fixit*, what a confirm pressed on an incident's page sent, as the run's record keeps it
    (`FIXIT_KEYS`, each of its kind, the texts cut to 500 characters), or ``{}`` for none or
    anything of another shape: a run is never refused for it, and keeps only what is its own."""
    if not isinstance(fixit, dict) or not isinstance(fixit.get("incident"), str) \
            or not fixit.get("incident"):
        return {}
    out = {}
    for key, kind in FIXIT_KEYS.items():
        value = fixit.get(key)
        if isinstance(value, bool) or not isinstance(value, kind):
            continue
        out[key] = value[:500] if isinstance(value, str) else value
    return out


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
    return bool(h) and h.get("operation") in (OPERATION, READD_OPERATION, COLLECTOR_OPERATION)


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
        if r.get("key") not in RUN_KEYS or not r.get("config_change"):
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


def _moved() -> None:
    """The run wrote a step: inside a job, its card and the In progress list are told
    (`op_progress.moved`: the run's own list is what they read); outside one, nothing."""
    from modules import op_progress

    op_progress.moved()


# ── The run ─────────────────────────────────────────────────────────────────────────────────

class _Run:
    def __init__(self, network: str, rec: dict, src, values: dict):
        self.network, self.rec, self.src, self.values = network, rec, src, values
        #: The run its reads name (`reads.within`'s, set by `apply` once the device is held).
        self.part = {}

    def mask(self, text: str) -> str:
        from modules.redact import redact_text

        return redact_text(text or "", self.values)

    def begin(self, name: str, words: str, *, wait_s=None, bound: bool = False,
              **more) -> dict:
        """A step that takes time begins: recorded ``running`` now, with when it began and
        the wait it declares (a fixed length, or with *bound* the longest it waits:
        ``wait_bound``), so the run's newest step is the one it is in (the operator,
        2026-11-11); its own `step` then ends it in place. Returns the record: what the step
        reads while it runs goes under it as it happens (`read`). *more* is kept on it (a
        verify's ``sub`` and its ``reads``)."""
        at = _iso(self.src.clock())
        got = dict({"step": name, "result": "running", "words": self.mask(words), "at": at,
                    "began": at},
                   **({"wait_s": wait_s} if wait_s else {}),
                   **({"wait_bound": True} if wait_s and bound else {}), **more)
        self.rec["steps"].append(got)
        _moved()
        return got

    def step(self, name: str, result: str, words: str, **more) -> dict:
        """A step's record, returned. One `begin` opened (the newest record, of this name,
        still ``running``, with ``began``) is ended in place: it keeps when it began, its
        wait, and whatever it kept while it ran (its reads, its ``sub``); any other is
        appended, as before."""
        ended = dict({"step": name, "result": result, "words": self.mask(words),
                      "at": _iso(self.src.clock())}, **more)
        steps = self.rec["steps"]
        last = steps[-1] if steps else {}
        if last.get("step") == name and last.get("result") == "running" and last.get("began"):
            ended = dict({k: v for k, v in last.items() if k not in ended}, **ended)
            steps[-1] = ended
        else:
            steps.append(ended)
        _moved()
        return ended

    def read(self, step: dict, command: str, got: dict, found: dict, **more) -> None:
        """One read into *step*'s ``reads`` as it happens (`reads.keep_read`: in order, short,
        bounded): what was asked, when, what the operation found in its own words (*found*'s,
        a check's state and words, masked), and whether it passed, was read and did not, or
        could not be read; *got*'s ``run`` names the reads store's run that holds the device's
        masked answer. *more* is kept on the entry (``check``: which of the three it is)."""
        from modules.nsot import reads

        result = {"pass": "pass", "cant_tell": "unreadable"}.get(found.get("state"), "fail")
        reads.keep_read(step, reads.read_entry(
            command, result, self.mask(found.get("words") or ""), at=_iso(self.src.clock()),
            read_id=(got or {}).get("run") or "", **more))

    def finish(self, outcome: str, words: str) -> dict:
        for s in self.rec["steps"]:
            if s.get("result") == "running":
                # A step still going when the run ended (the run failed inside it): said,
                # never left running in a finished record.
                s.update(result="unknown", at=_iso(self.src.clock()),
                         words=f"{s.get('words')}: the run ended before this step did")
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
          readd: bool = False, collector: bool = False, previewed_close: str = "",
          run_id: str = "", sources=None, fixit=None) -> dict:
    """Run the confirmed re-subscribe (or, with *readd*, the one-step Re-add the receiver; with
    *collector*, the re-subscribe with the collector step, C3078) on *device*, holding it, as
    *actor*, a person verified as *actor_verified* (`person_refusal`: neither has a default):
    the run's record, written. *confirmed* is each subscription's hash and *program* the
    selection's, both as previewed (`refusal`); *previewed_close* the device's end of the
    session the card drew for the collector step. *fixit* is the incident, the attempt and the
    proposal its confirm was pressed for on an incident's page, kept in the record
    (`fixit_field`, C3106). Never raises; a refusal is a record too, with nothing sent."""
    from modules.nsot import device_ops, reads

    src = sources or Sources(network)
    now = src.clock()
    not_a_person = person_refusal(actor, actor_verified, person)
    collector = collector is True and not readd
    p = (plan(network, device, subs, readd=readd, collector=collector, sources=src)
         if not not_a_person else plan(network, device, subs, readd=readd, sources=src))
    key = READD_KEY if readd else COLLECTOR_KEY if collector else KEY
    rec = {"id": run_id or reads.new_id(), "list": network, "device": device, "key": key,
           "collector_step": collector,
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
    link = fixit_field(fixit)
    if link:
        rec[FIXIT_FIELD] = link
    run = _Run(network, rec, src, src.values())
    # The run's own steps, live: inside its job this list is what its card and the In
    # progress list read while it runs (`op_progress.attach`), and what its record keeps.
    from modules import op_progress
    op_progress.attach(steps_for(key), rec["steps"], run=rec["id"],
                       labels=step_labels(device, [u["sub"] for u in p["units"]] or subs))
    if not_a_person:
        # Before the plan's refusals or the hash are said: a request that is not a verified
        # person's learns nothing about what a valid confirm would have been.
        run.step("hash", "refused", not_a_person)
        return run.finish("refused", not_a_person)
    why = refusal(p, confirmed, reason, readd, program=program, previewed=previewed,
                  previewed_close=previewed_close)
    if why:
        run.step("hash" if p["ok"] else "plan", "refused", why)
        return run.finish("refused", why)
    close = p.get("close") or None
    run.step("plan", "ok", f"{p['words']}: each receiver from {device}'s committed intent"
                           + ("" if readd else f"; the removal measured on {p['dialect']}")
                           + (f"; the collector's one idle session from {close['remote']} to "
                              f"{close['local']}, named by the close helper's dry run "
                              f"({close['dry_run']['words']})" if close else ""))
    rec["hash"] = run_hash(p["units"], reason, readd, close)
    rec["program"] = [run.mask(x) for x in p["program"]]
    if close:
        rec["collector_close"] = {"previewed": dict(close["dry_run"]),
                                  "session": {"local": close["local"],
                                              "remote": close["remote"]}}
    run.step("hash", "ok", "each subscription's program is the one previewed ("
             + ", ".join(f"{u['sub']}: {u['hash']}" for u in p["units"])
             + ("" if readd else f"), and the selection's is too ({p['hash']}"
                + (", the session to close in it" if close else ""))
             + f"); the run's hash, the reason in it: {rec['hash']}")
    op = READD_OPERATION if readd else COLLECTOR_OPERATION if close else OPERATION
    try:
        # Every read the run makes in this thread is the run's own (`reads.within`): kept in
        # the reads store naming this run and its step, never a Show commands run of the
        # person's.
        with device_ops.hold(network, device, op, actor, detail=p["words"], ip=p["ip"]), \
                reads.within(op, rec["id"], "before", RECORD) as run.part:
            run.step("hold", "ok", f"{device} held for the whole operation")
            return _held(run, p, actor, readd)
    except device_ops.DeviceBusy as exc:
        run.step("hold", "refused", str(exc))
        return run.finish("refused", f"{exc}. Nothing was sent")
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.exception("resubscribe: %s on %s failed", network, device)
        if not rec["config_change"]:
            return run.finish("refused", f"{type(exc).__name__}: {exc}. Nothing was sent")
        if not rec.get("device_sent"):
            # Recorded as a change, but no session reached the device (the collector step's
            # close or its wait failed first): said as that, never as a send begun.
            closed = (rec.get("collector_close") or {}).get("code") == "closed"
            return run.finish("failed", (
                f"the run failed before anything was sent to {device} "
                f"({type(exc).__name__}: {exc})"
                + ("; the collector's session was closed, and the device dials a new one"
                   if closed else "") + ". Nothing was sent to the device"))
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
    close = p.get("close") or {}
    s = Session(run.network, p["dev"], "", actor, run.values,
                operation=(READD_OPERATION if readd else COLLECTOR_OPERATION if close
                           else OPERATION), detail=p["words"],
                label="telemetry re-subscribe", opener=src.opener, clock=src.clock)
    addresses = src.addresses(p["hv"])
    before, asked = {}, {"reads": []}
    for u in p["units"]:
        b = before[u["sub"]] = {
            "receiver": src.receiver(device, u["sub"], actor, p["dialect"]),
            "collector": src.collector(u["address"], u["port"], addresses)}
        _read_before(run, asked, device, u, b, p["dialect"])
    conns_before = None
    if close:
        # The collector step: the device's own connections before the close (C3640), so the
        # wait after it knows which connection is to go.
        conns_before = src.connections(device, actor, p["dialect"])
        run.read(asked, connection_command(p["dialect"]), conns_before,
                 _connections_found(device, close, conns_before), check="device")
    running, why = _running(s)
    if running is None:
        run.step("before", "refused", f"{device}'s running configuration could not be read "
                                      f"({why}), and the run compares its end with it",
                 reads=asked["reads"])
        rec["config_change"] = False
        return run.finish("refused", f"{device}'s running configuration could not be read "
                                     f"before ({why}). Nothing was sent")
    s.before = running
    run.step("before", "ok", "; ".join(_before_words(device, u, before[u["sub"]])
                                       for u in p["units"])
             + (f"; {_connections_found(device, close, conns_before)['words']}" if close
                else "")
             + f"; the running configuration, {len(running.splitlines())} lines",
             reads=asked["reads"])
    if close and not _close_and_wait(run, p, actor, conns_before,
                                     before[p["units"][0]["sub"]]["collector"]):
        # The close did not happen: nothing was sent to the device, so its configuration lines
        # from now on are not Mercury's.
        rec["config_change"] = False
        return run.finish("not_closed", rec["collector_close"].get("words_said") or
                          OUTCOME_WORDS["not_closed"])
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
        run.begin("wait", f"waiting {WAIT_S} s after the last removal", wait_s=WAIT_S)
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
        run.rec["device_sent"] = True
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


def _read_before(run: _Run, step: dict, device: str, u: dict, b: dict, dialect: str) -> None:
    """The two reads before, of one subscription, into the ``before`` step's reads."""
    r, c = b["receiver"], b["collector"]
    run.read(step, receiver_command(dialect, u["sub"]), r, {
        "state": "pass" if r.get("state") == "read" else "cant_tell",
        "words": ("; ".join(f"{x['state']} on connection {x['connection'] or 'none'}"
                            for x in r.get("rows") or []) or "no receiver")
        if r.get("state") == "read" else f"not read ({r.get('why')})"}, check="device")
    run.read(step, _collector_asked(u), None, {
        "state": "pass" if c.get("state") == "read" else "cant_tell",
        "words": (f"{len(c.get('sessions') or [])} session(s) from {device}"
                  if c.get("state") == "read" else f"not read ({c.get('why')})")},
        check="collector")


def _collector_asked(u: dict) -> str:
    """What (c)'s read asks, as the run's record names it: no device command, Mercury's own
    read of the collector's sessions."""
    return f"the collector's sessions on {u['address']} port {u['port']}"


def connection_command(dialect: str) -> str:
    """The device's telemetry connections (C3640), as the reads engine is asked it."""
    from modules.heal import diagnose as D

    return D.render("telemetry_connection", dialect)


def _to_collector(close: dict, rows) -> list:
    """The rows of *rows* (`diagnose_parse.telemetry_connection`'s) to the collector the step
    closes a session of: its address and port."""
    import ipaddress

    address = ipaddress.ip_address(close["address"]).compressed
    return [r for r in rows or [] if r.get("peer") == address
            and r.get("port") == close["collector_port"]]


def _leaving(close: dict, got: dict) -> list:
    """The indexes of the device's connections to the collector that read Disconnecting."""
    return sorted({r["index"] for r in _to_collector(close, (got or {}).get("rows"))
                   if str(r.get("state") or "").lower() == "disconnecting"})


def _connections_found(device: str, close: dict, got: dict) -> dict:
    """The device's connections to the collector, as a read's found words."""
    where = close["collector"]
    if (got or {}).get("state") != "read":
        return {"state": "cant_tell", "words": (f"{device}'s telemetry connections were not "
                                                f"read ({(got or {}).get('why')})")}
    rows = _to_collector(close, got.get("rows"))
    if not rows:
        return {"state": "pass", "words": f"{device} holds no telemetry connection to {where}"}
    return {"state": "pass", "words": "; ".join(
        f"{device}'s connection {r['index']} to {where} from {r['source']} reads {r['state']}"
        for r in rows)}


def _close_and_wait(run: _Run, p: dict, actor: str, before: dict, sessions: dict) -> bool:
    """The collector step, holding the device and before any receiver is touched: the close
    through the helper (`Sources.close`, not a dry run), its receipt kept in the record
    (``collector_close``: the helper's code, exit code and words, the two ends it closed, when);
    then the device's connections read until the one that read Disconnecting is gone. False
    when the helper did not close it (the run stops, nothing sent to the device); True
    otherwise, a connection still there at the bound said, and the re-subscribe follows (its
    removals are what released the connection by hand, C2838). *sessions* is the collector's
    read in the reads before: the close is asked only while it still shows exactly the session
    the plan named, established and idle; anything else is ``not_closed``, nothing asked."""
    from modules.heal import collector_close as CC
    from modules.heal.diagnose_stream import ESTABLISHED, receiving_now

    src, rec, device, close = run.src, run.rec, p["device"], p["close"]
    pair = f"the session from {close['remote']} to {close['local']}"
    run.begin("close", f"closing {pair} through the close helper", wait_s=CC.BOUND_S,
              bound=True)
    # Idle still, just before the close: the reads before, taken holding the device.
    same = [s for s in (sessions or {}).get("sessions") or []
            if s.get("remote") == close["peer"] and int(s.get("rport") or 0) == close["port"]
            and s.get("state") == ESTABLISHED]
    if (sessions or {}).get("state") != "read" or len(same) != 1 or \
            receiving_now(same[0]) is not False:
        why = ("the collector's sessions were not read before the close"
               if (sessions or {}).get("state") != "read" else
               f"the collector no longer holds {pair} established" if not same else
               f"{pair} received data {int(same[0]['lastrcv_ms']) // 1000} s ago, so it is not "
               "stale" if receiving_now(same[0]) else
               f"{pair}'s last receive was not read, so whether it is still stale cannot be told")
        rec["collector_close"].update(code="not_asked", exit=None, words=why)
        rec["collector_close"]["words_said"] = run.mask(
            f"{pair} was not closed: {why}. Nothing was sent to {device}")
        run.step("close", "refused", f"{pair} was not closed: {why}; the close helper was not "
                                     f"asked, and nothing is sent to {device}")
        _record(run.network, rec)
        return False
    got = src.close(close["peer"], close["port"], dry_run=False, run_id=rec["id"]) or {}
    receipt = {k: got.get(k) for k in ("ok", "code", "exit", "words", "tuple", "at")}
    rec["collector_close"].update(receipt)
    closed = got.get("ok") is True and got.get("code") == "closed"
    said = (f"the close helper answered {got.get('code') or 'nothing'} (exit "
            f"{got.get('exit')}): {got.get('words') or 'no words'}")
    if not closed:
        rec["collector_close"]["words_said"] = run.mask(
            f"{pair} was not closed: {said}. Nothing was sent to {device}")
        run.step("close", "refused" if got.get("exit") in (None, 0) else "failed",
                 f"{pair} was not closed: {said}; nothing is sent to {device}")
        _record(run.network, rec)
        return False
    moved = (got.get("tuple") or {}) != {"local": close["local"], "peer": close["remote"]}
    run.step("close", "ok", f"closed {pair}, read back gone by the helper ({said})"
             + (f"; the helper names the session {got.get('tuple')}" if moved else ""))
    _record(run.network, rec)
    leaving = _leaving(close, before)
    if (before or {}).get("state") != "read":
        run.step("gone", "unknown", (f"{device}'s connections were not read before "
                                     f"({(before or {}).get('why')}), so its connection going "
                                     "cannot be told; the re-subscribe follows"))
        return True
    if not leaving:
        run.step("gone", "ok", (f"{device} held no Disconnecting connection to "
                                f"{close['collector']} before the close: nothing to wait for"))
        return True
    run.part["step"] = "gone"
    start = src.clock()
    deadline = start + GONE_BOUND_S
    step = run.begin("gone", (f"reading {device}'s telemetry connections every {GONE_POLL_S} s "
                              f"until connection {_and(map(str, leaving))} is gone, for at "
                              f"most {GONE_BOUND_S} s ({GONE_WHY})"),
                     wait_s=GONE_BOUND_S, bound=True, reads=[])
    while True:
        now = src.connections(device, actor, p["dialect"])
        found = _connections_found(device, close, now)
        still = ([r["index"] for r in _to_collector(close, now.get("rows")) if r["index"] in
                  leaving] if now.get("state") == "read" else None)
        run.read(step, connection_command(p["dialect"]), now,
                 dict(found, state=("pass" if still == [] else "cant_tell" if still is None
                                    else "waiting")), check="device")
        if still == [] or src.clock() >= deadline:
            break
        _record(run.network, rec)
        _moved()
        src.sleep(min(GONE_POLL_S, max(0.0, deadline - src.clock())))
    took = round(src.clock() - start)
    if still == []:
        run.step("gone", "ok", f"{device}'s connection {_and(map(str, leaving))} to "
                               f"{close['collector']} is gone ({took} s); {found['words']}",
                 took_s=took)
    else:
        run.step("gone", "unknown" if still is None else "failed", (
            f"{device}'s connection {_and(map(str, leaving))} to {close['collector']} "
            + ("could not be read" if still is None else "is still there")
            + f" after {took} s ({found['words']}); the re-subscribe follows, whose removals "
              "release it"), took_s=took)
    return True


def _stream_asked(sub: str) -> str:
    """What (b)'s read asks, as the run's record names it: Prometheus, no device."""
    return f"Prometheus: subscription {sub}'s series"


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
        run.rec["device_sent"] = True
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

    The step is in the record from its start (`_Run.begin`: ``running``, with when it began
    and its bound, which the card counts down), and each read goes into its ``reads`` as it
    happens (`_Run.read`), the record written and the card told after every round: a run in
    progress shows the reads made so far, and a finished one each of them, in order, without
    a row of its own anywhere (the operator, 2026-11-11). Its own `_Run.step` ends it in
    place."""
    src, device, sub = run.src, p["device"], u["sub"]
    start = src.clock()
    deadline = start + VERIFY_BOUND_S
    checks = {k: {"state": "cant_tell", "words": "not read"} for k in
              ("device", "stream", "collector")}
    stale = []
    run.part["step"] = "verify"
    step = run.begin("verify", (
        f"subscription {sub}: reading the device, the stream and the collector every "
        f"{POLL_S} s until each says it is back, for at most {VERIFY_BOUND_S} s"),
        wait_s=VERIFY_BOUND_S, bound=True, sub=sub, reads=[])
    asked = receiver_command(p["dialect"], sub)
    while True:
        if checks["device"]["state"] != "pass":
            got = src.receiver(device, sub, actor, p["dialect"])
            checks["device"] = _device_check(device, sub, before["receiver"], got)
            run.read(step, asked, got, checks["device"], check="device")
        if checks["stream"]["state"] != "pass":
            checks["stream"] = _stream_check(device, sub, src.series(device, sub))
            run.read(step, _stream_asked(sub), None, checks["stream"], check="stream")
        if checks["collector"]["state"] != "pass":
            checks["collector"], stale = _collector_check(
                device, u, before["collector"], src.collector(u["address"], u["port"],
                                                              addresses))
            run.read(step, _collector_asked(u), None, checks["collector"], check="collector")
        if all(c["state"] == "pass" for c in checks.values()) or src.clock() >= deadline:
            break
        # The reads so far: kept in the record (a page opened later, or served by another
        # process, reads them there) and the run's card told, by the one path every step's
        # change takes (`_moved`).
        _record(run.network, run.rec)
        _moved()
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
          readd: bool = False, collector: bool = False, previewed_close: str = "",
          fixit=None) -> dict:
    """Refuse now (``{"refused": why}``, nothing sent) or start the run as a job: ``{"job",
    "run"}``. *confirmed* and *program* are the hashes the card carried (each subscription's,
    and the selection's; `refusal`), *collector* the collector step and *previewed_close* the
    session the card drew for it; *fixit* the incident its confirm was pressed for, kept in
    the run's record (`apply`). *actor_verified* and *person* are the request's own
    (`person_refusal`), read there once; the job is started by the one job starter (`capture_job.start`), which carries
    the request's verified identity into its thread (`identity.carried`), so the reads the run
    records and anything it commits name the person as the request verified them."""
    from modules.nsot import capture_job, reads

    why = person_refusal(actor, actor_verified, person)
    if why:
        return {"refused": why, "not_a_person": True}
    collector = collector is True and not readd
    p = plan(network, device, subs, readd=readd, collector=collector)
    why = refusal(p, confirmed, reason, readd, program=program, previewed=previewed,
                  previewed_close=previewed_close)
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
                                                         collector=collector,
                                                         previewed_close=previewed_close,
                                                         run_id=run_id, fixit=fixit)["id"]},
                            kind="telemetry re-subscribe", announce_keys=ANNOUNCE_KEYS,
                            announcer=ANNOUNCER,
                            # Its device and its card (the operator, 2026-11-11): the run is
                            # listed under Finished with its outcome until each person opens
                            # it, and the device's page reopens its card (`run_card`).
                            device=device, card="resubscribe")
    return {"job": job, "run": run_id}
