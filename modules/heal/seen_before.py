"""Seen before, and Mercury's own diagnosis, for a lost telemetry stream's Needs attention row
(docs/MERCURY_CHARTER.md, "The fix-it path": its Step 1, the notification, and the fallback of
its Step 2, with no AI). Deterministic: it reads Mercury's own records and, for one question,
the device's log; it reads no device and calls no model.

**What it answers,** for each device with a lost-stream alert firing (`lost_now`):
- **Seen before:** the past incident that matches this one, how it ended and how long that
  held, or that none is found, or that a store which would hold it could not be read;
- **Mercury's diagnosis:** the newest "a telemetry stream lost" diagnosis recorded for THIS
  loss (`modules/heal/diagnose_stream.py`), in plain words with when it was read; or that none
  is recorded (absent), that one was asked for and not made, or that the record could not be
  read. A diagnosis recorded before this loss began is never drawn as this loss's.

**Where it runs, and why there** (CLAUDE.md, "Enterprise scale: no per-device work per
request"): in the `grafana-alerts` reader's read (`modules/readers/grafana_alerts.read`, which
calls `context`), stored in the reader's value as ``streams``, beside ``bands``.
`attention.grafana_source` builds the row from that stored value on every page request and
reads nothing more: the search is a job's, once per read of Grafana's alerts, never a page's.

**The signature** of an incident: the device, the symptom kind (a lost-stream alert, by its
rule's own title, `diagnose_stream.TITLE`) and the cause class (the first hypothesis's rule of
the stream runbook's diagnosis recorded during it, `diagnose_stream.STREAM_RULES`; none when
no diagnosis was recorded then). **The match** (`pick`): the past incidents of the same device
and symptom whose cause class is this loss's, the most recent of them; when none has it (or
either cause is not recorded), the nearest in time of the same device and symptom. Which one
matched is said under Details for the record. Another device's incidents are never matched:
the line is "Seen before on <device>".

**The stores read, and what each can say** (each named when it cannot be read: an absence is
a finding only where the store that would hold it was read):
- the alert history (`modules/alert_history.py`): each lost-stream alert's episodes, their
  start and end in Grafana's time. It says WHEN a past loss began, cleared and returned; it
  never says what cleared it. Its window is its retention (90 days by default);
- the operations' record (`privileged.runs`: a re-subscribe, a re-add, a Tier 2 command), the
  deploy receipts (`receipts.read`) and the rotation commits: a Mercury operation that sent
  something to the device during the incident. Only a re-subscribe or re-add whose own verify
  read the stream back says it FIXED it; any other is said as an operation that ran during it;
- the device's log (`device_logs.change_lines`, from Loki, the device page's own change log):
  a configuration-change line received during the incident, attributed by
  `attribution.attribute` over the stores above; one made on the console is said as that,
  with its time. That nothing was changed is said only when the log holds other lines of the
  device from then (`device_logs.lines_held`); a log that holds nothing from then, or cannot
  be asked, is said, and the incident is then "cleared with no Mercury operation recorded";
- the heal step log (`steplog.diagnoses`): the stream runbook's diagnoses of the device;
- the planned-restart windows (`restarts.explained_by`): a past loss that began inside one
  (the device restarting, or cut off as its operation predicted) was held then and never
  raised, so it is no past incident and is left out, counted in the record.

**Not read, and why:** the acknowledgements hold nothing of a lost stream (its row is not one
a person acknowledges); the heal incidents' own configuration-change triggers are kept only
where self-healing is on and only the newest (`incidents.CLOSED_KEPT`), so their silence is
no finding, and the device's log is asked instead; an operation on ANOTHER device (a
neighbour's change put back) is not searched for, so "cleared by itself" speaks of this
device's records alone, as its words say.

**Its bound** (CLAUDE.md, "Built for large fleets"): at most `MAX_DEVICES` devices per read
(`context`'s *limit*, which the reader leaves at that),
the ones lost longest first (the rest say they were not searched); one read of the alert
history per read of Grafana's alerts, and only while a lost-stream alert fires and a device's
answer is not held; each device's answer held for `HELD_S` once every store it needs was read
(`RETRY_S` while one could not be, then asked again);
the newest `attribution.RECEIPTS_READ` receipts and operation runs of the device; one read of
its network's step log; the device's log asked only for a matched incident with no Mercury
operation in it.

**IPv4 and IPv6:** every address said here is one a record holds (the collector's session, a
log line's source), in the form `ipaddress` gave it there; nothing is parsed or compared by
family in this module.
"""

import logging
import threading
import time

log = logging.getLogger(__name__)

#: The runbook whose diagnosis this module draws (`diagnose.RUNBOOKS`).
RUNBOOK = "stream_lost"
#: How many devices one read searches: a fleet losing more streams than this at once has one
#: cause (its collector, its path), and the rows say they were not searched.
MAX_DEVICES = 20
#: How long a device's answer is held once every store it needs was read: a past incident does
#: not change, and a late-recorded resolve is seen within this.
HELD_S = 900.0
#: How long an answer is held while a store it needs could not be read: asked again after
#: this, so an unreadable store is neither searched on every read nor believed for long.
RETRY_S = 120.0
#: The answers held, at most (the oldest dropped).
HELD_MAX = 200
#: Each cause class in plain words (`diagnose_stream.STREAM_RULES`' rules that make a finding;
#: held equal by tests/test_seen_before.py).
CAUSE_WORDS = {
    "half_open": "a session that carries nothing (half-open)",
    "no_session": "no session from {host} on its collector",
    "outlived_cause": "the stream outlived its cause",
    "cause_just_cleared": "its cause was put back too recently to tell",
    "cause_stands": "its likely cause, a change on another device, still stands",
    "collector_unreached": "{host} does not reach its collector",
    "collector_down": "nothing listens on the stream's port on the collector",
    "stream_missing": "a lost subscription is missing on {host}",
    "stream_invalid": "a lost subscription is not Valid on {host}",
    "device_unread": "Mercury could not read {host} either",
    "stream_config_changed": "{host}'s configuration was changed in the hour before",
}
#: A telemetry operation's outcomes whose own verify read the stream back
#: (`resubscribe.OUTCOME_WORDS`).
VERIFIED_BACK = ("resubscribed", "readded")

_held: dict = {}
_held_lock = threading.Lock()


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _epoch(text):
    from modules import alert_history

    return alert_history.epoch(text)


def _and(items) -> str:
    items = [str(i) for i in items]
    return " and ".join([", ".join(items[:-1]), items[-1]]) if len(items) > 1 else (
        items[0] if items else "")


def _numeric(subs) -> list:
    return sorted({str(s) for s in subs}, key=lambda x: (len(x), x))


def span_words(seconds) -> str:
    """A length of time in whole words: "45 seconds", "31 minutes", "37 hours", "5 days"."""
    s = max(0, int(seconds or 0))
    if s < 120:
        return f"{s} seconds"
    if s < 7200:
        return f"{s // 60} minutes"
    if s < 72 * 3600:
        return f"{s // 3600} hours"
    return f"{s // 86400} days"


def streams_words(subs, verb: tuple = ("was", "were")) -> str:
    """"Telemetry subscription 101 was" or "Telemetry subscriptions 101 and 102 were"."""
    subs = _numeric(subs)
    return (f"Telemetry subscription{'' if len(subs) == 1 else 's'} {_and(subs)} "
            f"{verb[0] if len(subs) == 1 else verb[1]}")


# ── What is lost now ────────────────────────────────────────────────────────────────────────

def lost_now(value: dict) -> dict:
    """``{device: {"subs", "onset"}}`` from an alerts reader value: each device with a
    lost-stream alert in a state other than pending, the subscriptions its rules' titles name
    and when the earliest began, in Grafana's time (``active_at``, else ``starts_at``; None
    when neither is recorded: never Mercury's clock, never the device's)."""
    from modules.heal.diagnose_stream import TITLE

    out = {}
    for inst in (value or {}).get("instances") or []:
        if inst.get("kind") == "pending":
            continue
        m = TITLE.match(str(inst.get("rule") or "").strip())
        device = inst.get("device") or ""
        if not m or not device or m.group("device") != device:
            continue
        at = _epoch(inst.get("active_at"))
        if at is None:
            at = _epoch(inst.get("starts_at"))
        d = out.setdefault(device, {"subs": set(), "onset": None})
        d["subs"].add(m.group("sub"))
        if at is not None and (d["onset"] is None or at < d["onset"]):
            d["onset"] = at
    return {k: {"subs": _numeric(v["subs"]), "onset": v["onset"]} for k, v in out.items()}


# ── The past incidents, from the alert history ──────────────────────────────────────────────

def incidents_of(rows, store: str, device: str) -> list:
    """*device*'s lost-stream incidents in the alert history's *rows*, oldest first: its
    lost-stream episodes that fired (`alert_history.episodes`), those begun within
    `attention.INCIDENT_GAP_SECONDS` of the one before forming one incident, as its Needs
    attention row groups them. Each ``{"started", "ended", "subs", "episodes"}``; *ended* is
    None while any of its episodes has no recorded end (the loss standing now, or a resolve
    the reader did not record). *store* keeps one alerts configuration's episodes ("" keeps
    every one)."""
    from modules import alert_history as AH
    from modules.attention import INCIDENT_GAP_SECONDS
    from modules.heal.diagnose_stream import TITLE

    eps = []
    for e in AH.episodes(rows):
        m = TITLE.match(str(e.get("rule") or "").strip())
        if not m or e.get("device") != device or e.get("outcome") != "fired":
            continue
        if store and (e.get("store") or "") != store:
            continue
        start = _epoch(e.get("started_at"))
        if start is None:
            continue
        eps.append({"start": start, "end": _epoch(e.get("resolved_at")), "sub": m.group("sub")})
    eps.sort(key=lambda e: e["start"])
    groups = []
    for e in eps:
        if groups and e["start"] - groups[-1]["last"] <= INCIDENT_GAP_SECONDS:
            g = groups[-1]
        else:
            g = {"started": e["start"], "last": e["start"], "ends": [], "subs": set(),
                 "episodes": 0}
            groups.append(g)
        g["last"] = e["start"]
        g["ends"].append(e["end"])
        g["subs"].add(e["sub"])
        g["episodes"] += 1
    return [{"started": g["started"], "subs": _numeric(g["subs"]), "episodes": g["episodes"],
             "ended": (None if any(x is None for x in g["ends"]) else max(g["ends"]))}
            for g in groups]


def past_of(groups: list, onset) -> list:
    """The incidents of *groups* that ended, and began before this loss (*onset*; None keeps
    every ended one), oldest first."""
    return [g for g in groups if g["ended"] is not None
            and (onset is None or (g["started"] < onset and g["ended"] <= onset))]


def cause_during(diagnoses, start: float, end: float) -> str:
    """The cause class recorded during an incident: the first hypothesis's rule of the newest
    stream diagnosis that finished inside it; "" when none did."""
    for d in diagnoses or []:                         # newest first
        at = _when(d)
        if d.get("runbook") != RUNBOOK or at is None or not start <= at <= end:
            continue
        hyps = d.get("hypotheses") or []
        if d.get("state") == "done" and hyps:
            return str(hyps[0].get("rule") or "")
    return ""


def pick(past: list, cause: str, causes: dict) -> tuple:
    """``(incident, matched_on)``: the same signature first (*causes* maps each past incident's
    start to its recorded cause class; one equal to this loss's *cause*), the most recent of
    those; else the nearest in time. *matched_on* is ``signature`` or ``nearest``."""
    if not past:
        return None, ""
    same = [g for g in past if cause and causes.get(g["started"]) == cause]
    if same:
        return max(same, key=lambda g: g["ended"]), "signature"
    return max(past, key=lambda g: g["ended"]), "nearest"


def held_for(inc: dict, groups: list, onset) -> dict:
    """How long *inc*'s end held: ``{"seconds", "returned", "now"}``, the start of the next
    incident of the same device and symptom after its end (*now* True when that is this
    loss), or ``{}`` when the records show no return."""
    later = [g["started"] for g in groups if g["started"] > inc["ended"]]
    if onset is not None and onset > inc["ended"]:
        later.append(onset)
    if not later:
        return {}
    back = min(later)
    return {"seconds": back - inc["ended"], "returned": back,
            "now": onset is not None and back >= onset}


# ── Mercury's stores ────────────────────────────────────────────────────────────────────────

class Sources:
    """Where each record is read; a test stands in for any of them."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self._windows = None

    def planned(self, network: str, device: str, at: float) -> str:
        """The planned window that explains a signal from *device* at *at* (`restarts.
        explained_by`: its own restart, a restart it was predicted unreachable for, or a link
        taken down on purpose, each with its settle time), in its words; "" when none does.
        The record is read once; one that cannot be read raises."""
        from modules import restarts as R

        if self._windows is None:
            self._windows = (R.planned_rows(), R.ends())
        got = R.explained_by(device, network, at, planned=self._windows[0],
                             ended=self._windows[1])
        return got["words"] if got else ""

    def history(self) -> dict:
        from modules import alert_history

        return alert_history.read()

    def networks(self):
        """``{device: [network, ...]}`` over every inventory, or None when one is unread."""
        from modules.attention import _device_networks

        return _device_networks()

    def receipts(self, network: str, device: str) -> list:
        from modules.heal import attribution

        return attribution._receipts(network, device)

    def operations(self, network: str, device: str) -> list:
        """*device*'s newest operation runs, whatever they changed; raises when one of the
        records cannot be read (an unread one is never an absence)."""
        from modules.config import list_data_path
        from modules.heal.attribution import RECEIPTS_READ
        from modules.nsot import privileged

        got = privileged.runs(network, device=device, limit=RECEIPTS_READ,
                              data_dir=list_data_path(network))
        if got["unreadable"]:
            raise RuntimeError(f"{len(got['unreadable'])} of {network}'s operation records "
                               f"cannot be read ({', '.join(got['unreadable'][:3])})")
        return got["runs"]

    def rotations(self, network: str) -> dict:
        from modules.heal import attribution

        return attribution._rotations(network)

    def diagnoses(self, network: str, device: str) -> dict:
        """*network*'s recorded diagnoses of *device*, newest first (`steplog.diagnoses`): the
        ones that read it, and the ones asked of it and refused before any read (a refused
        diagnosis names no device it read; its target names the one it was asked of)."""
        from modules.heal import steplog

        got = steplog.diagnoses(network)
        if got.get("state") == "unreadable":
            return got
        return dict(got, diagnoses=[
            d for d in got.get("diagnoses") or []
            if device in (d.get("devices") or [])
            or ((d.get("target") or {}).get("device") == device and not d.get("devices"))])

    def change_log(self, device: str, start: float, end: float) -> dict:
        """*device*'s configuration-change lines received from *start* to *end*, from its log
        (Loki): ``{"state": "read"|"unread", "why", "lines", "held", "whole"}``. *held* is how
        many lines of the device the log holds from then (None: not counted), which is what
        makes "no change was logged" a finding; *whole* is False when the window was cut (a
        full page, or a window longer than the log is asked over)."""
        from modules import device_logs

        dev = {"hostname": device}
        got = device_logs.change_lines(dev, since=start, now=end)
        if not got.get("configured"):
            return {"state": "unread", "why": "Loki is not configured", "lines": [],
                    "held": None, "whole": False}
        if got.get("error"):
            return {"state": "unread", "why": got["error"], "lines": [], "held": None,
                    "whole": False}
        count = device_logs.lines_held(dev, start, end)
        return {"state": "read", "why": count.get("error") or "",
                "lines": [{"epoch": l["ns"] / 1e9, "at": l.get("at_iso") or "",
                           "mnemonic": l.get("mnemonic") or "", "text": l.get("text") or ""}
                          for l in got.get("lines") or []],
                "held": count.get("count"),
                "whole": not got.get("cut") and not got.get("capped")}


def _when(d: dict):
    """When a diagnosis was read: its own finish, else its row's time."""
    at = _epoch((d or {}).get("finished_at"))
    return at if at is not None else _epoch((d or {}).get("at"))


def _network_of(nets, device: str) -> tuple:
    """``(network, why)``: the one network holding *device*, or "" and why it is not decided."""
    if nets is None:
        return "", "the networks' inventories could not be read"
    found = nets.get(device) or []
    if len(found) == 1:
        return found[0], ""
    if not found:
        return "", f"{device} is in no network's inventory"
    return "", (f"{len(found)} networks hold a device named {device} ({_and(found)}), so which "
                "one's records are its own is not decided")


# ── How a past incident ended ───────────────────────────────────────────────────────────────

def _operation_words(op: dict) -> str:
    who = op.get("actor") or "an unrecorded actor"
    return f"{op['what']} by {who}"


def _operations_during(network: str, device: str, inc: dict, src) -> tuple:
    """``(operations, stores, unread)``: each Mercury operation that sent something to
    *device* inside *inc*, oldest first, ``{"at", "what", "actor", "verified", "outcome",
    "ref"}``; *stores* what was read, for the attribution of a log line; *unread* each store
    that could not be read."""
    from modules.heal import resubscribe as R

    start, end = inc["started"], inc["ended"]
    ops, unread = [], []
    stores = {"receipts": [], "runs": [], "rotations": {}}
    try:
        stores["runs"] = list(src.operations(network, device) or [])
    except Exception as exc:                          # noqa: BLE001 (said, never an absence)
        unread.append(str(exc))
    try:
        stores["receipts"] = list(src.receipts(network, device) or [])
    except Exception as exc:                          # noqa: BLE001
        unread.append(str(exc))
    try:
        stores["rotations"] = dict(src.rotations(network) or {})
    except Exception as exc:                          # noqa: BLE001
        unread.append(f"{network}'s rotation commits cannot be read ({exc})")
    for r in stores["runs"]:
        try:
            at = float(r.get("started_at") or 0)
        except (TypeError, ValueError):
            continue
        if r.get("state") == "refused" or not start <= at <= end:
            continue                                   # a refused run sent nothing
        telemetry = r.get("key") in (R.KEY, R.READD_KEY)
        outcome = r.get("outcome") or r.get("state") or ""
        ops.append({"at": at, "what": r.get("command") or "an operation",
                    "actor": r.get("actor") or "", "ref": f"run {r.get('id')}",
                    "verified": telemetry and outcome in VERIFIED_BACK,
                    "outcome": (R.OUTCOME_WORDS.get(outcome, outcome) if telemetry
                                else (r.get("state") or ""))})
    for r in stores["receipts"]:
        at = _epoch(r.get("at"))
        if at is None or not start <= at <= end or not r.get("sent"):
            continue
        ops.append({"at": at, "what": f"a {r.get('action') or 'deploy'} to {device}",
                    "actor": r.get("actor") or "", "ref": f"receipt {r.get('id')}",
                    "verified": False, "outcome": r.get("outcome") or ""})
    rot = stores["rotations"].get(device)
    if rot and start <= float(rot[0]) <= end:
        ops.append({"at": float(rot[0]), "what": f"a credential rotation of {device}",
                    "actor": "", "ref": "its commit", "verified": False,
                    "outcome": "committed"})
    return sorted(ops, key=lambda o: o["at"]), stores, unread


def _outside_changes(network: str, device: str, lines: list, stores: dict) -> list:
    """The configuration-change lines of *lines* that are not Mercury's own
    (`attribution.attribute`, over the stores already read; no hold is asked: these lines are
    past), oldest first, each with what the line names of who made it."""
    from modules.heal import attribution as AT

    cfg = [r for r in stores["runs"] if r.get("config_change")]
    out = []
    for l in lines:
        if not AT.is_change(l.get("mnemonic"), l.get("text")):
            continue
        a = AT.attribute(network, device, float(l["epoch"]),
                         holder=lambda _n, _d: None,
                         receipts=lambda _n, _d: stores["receipts"],
                         rotations=lambda _n: stores["rotations"],
                         operations=lambda _n, _d: cfg)
        if a["by"] == AT.MERCURY:
            continue
        out.append({"epoch": float(l["epoch"]), "at": l.get("at") or _iso(l["epoch"]),
                    "person": AT.person_of(l.get("mnemonic"), l.get("text"))})
    return sorted(out, key=lambda c: c["epoch"])


def ended(network: str, why_no_network: str, device: str, inc: dict, src) -> dict:
    """How *inc* ended, from what a record shows: ``{"how", "words", "at", "tail", "list",
    "record", "settled"}``. *how* is ``fixed`` (a re-subscribe or re-add whose verify read the
    stream back), ``operation`` (another Mercury operation ran during it), ``console`` or
    ``changed`` (no Mercury operation; a configuration change logged during it, on the console
    or elsewhere), ``itself`` (no operation, and the log holds lines from then and no change),
    ``no_operation`` (no operation; whether it was changed is not known, said) or ``unread``.
    *words*, *at* and *tail* are the sentence around its time; *list* is the network whose
    History holds the operation's record; *settled* is False while a store could not be read
    (the answer is asked again)."""
    out = {"how": "unread", "words": "", "at": "", "tail": "", "list": "", "record": "",
           "settled": False}
    if not network:
        return dict(out, words=f"How it ended could not be read: {why_no_network}.",
                    record=why_no_network)
    ops, stores, unread = _operations_during(network, device, inc, src)
    fixed = [o for o in ops if o["verified"]]
    if fixed:
        o = fixed[-1]
        return dict(out, how="fixed", settled=True, list=network, at=_iso(o["at"]),
                    words=f"It was fixed by a Mercury operation: {_operation_words(o)}, at",
                    tail=f" ({o['outcome']}).", record=f"{o['ref']}: {o['outcome']}")
    if ops:
        o = ops[-1]
        return dict(out, how="operation", settled=not unread, list=network, at=_iso(o["at"]),
                    words=(f"It cleared after a Mercury operation on {device} "
                           f"({_operation_words(o)}), at"),
                    tail=(f"; its record says \"{o['outcome'] or 'no outcome'}\", and no record "
                          "says that operation cleared it."),
                    record=(f"{o['ref']}; {len(ops)} Mercury operation(s) during it"
                            + (f"; not read: {'; '.join(unread)}" if unread else "")))
    if unread:
        why = "; ".join(unread)
        return dict(out, words=f"How it ended could not be read: {why}.", record=why)
    try:
        got = src.change_log(device, inc["started"], inc["ended"])
    except Exception as exc:                          # noqa: BLE001 (said, never an absence)
        got = {"state": "unread", "why": f"{type(exc).__name__}: {exc}", "lines": [],
               "held": None, "whole": False}
    none = "It cleared with no Mercury operation recorded"
    if got.get("state") != "read":
        why = got.get("why") or "not read"
        return dict(out, how="no_operation", record=f"the log was not read: {why}",
                    words=(f"{none}; whether {device}'s configuration was changed during it "
                           f"could not be read ({why})."))
    changes = _outside_changes(network, device, got.get("lines") or [], stores)
    if changes:
        last = changes[-1]
        person = last["person"] or {}
        console = (person.get("line") or "").strip().lower() == "console"
        more = (f" ({len(changes)} configuration changes were logged during it; this is the "
                "last)" if len(changes) > 1 else "")
        record = (f"{len(changes)} configuration-change line(s) not Mercury's own in "
                  f"{device}'s log during it; the last: "
                  f"{person.get('words') or 'the line names nobody'}")
        if console:
            return dict(out, how="console", settled=True, at=last["at"], record=record,
                        words=f"{none}. A configuration change was made on its console at",
                        tail=f"{more}.")
        return dict(out, how="changed", settled=True, at=last["at"], record=record,
                    words=f"{none}. A configuration change was made on {device} at",
                    tail=f" ({person.get('words') or 'the line names nobody'}){more}.")
    held = got.get("held")
    if held and got.get("whole"):
        return dict(out, how="itself", settled=True,
                    record=(f"{device}'s log holds {held} line(s) from then, none a "
                            "configuration change"),
                    words=(f"It cleared by itself: no Mercury operation on {device} is "
                           f"recorded during it, and {device}'s log holds no configuration "
                           "change from then."))
    why = (got.get("why") or ("its log holds nothing from then" if held == 0 else
                              "its log from then was not read whole" if held else
                              "how much its log holds from then was not counted"))
    return dict(out, how="no_operation", settled=held == 0,
                record=f"no configuration-change line was read; {why}",
                words=(f"{none}; whether {device}'s configuration was changed during it is "
                       f"not known ({why})."))


# ── Seen before ─────────────────────────────────────────────────────────────────────────────

def _range_for(started: float, now: float) -> str:
    """Monitoring › Alerts › History's smallest range that reaches *started*."""
    from modules.alert_history import RANGES

    for name, span in RANGES.items():
        if span and now - started < span:
            return name
    return "all"


def _searched(hist: dict) -> str:
    from modules import alert_history as AH

    if hist.get("state") == "absent":
        return "the alert history holds nothing yet, so nothing earlier can be found"
    trans = AH.transitions(hist.get("rows") or [])
    oldest = min((r.get("at") for r in trans if r.get("at")), default="")
    return (f"the alert history kept: {len(trans)} transition(s)"
            + (f", the oldest at {oldest}" if oldest else ""))


def seen(store: str, network: str, why_no_network: str, device: str, lost: dict,
         cause: str, hist: dict, diagnoses, src) -> dict:
    """The "Seen before" answer for *device* (the module's docstring): ``{"state", "why",
    "record", ...}``, *state* ``match`` (with the line's parts), ``none`` or ``unreadable``."""
    from modules import alert_history as AH
    from modules.heal.diagnose import RUNBOOKS

    if hist.get("state") == "unreadable":
        why = f"the alert history could not be read ({hist.get('error') or 'no reason given'})"
        return {"state": "unreadable", "why": why, "record": why, "settled": False}
    groups = incidents_of(hist.get("rows") or [], store, device)
    past, planned, settled = [], 0, True
    for g in past_of(groups, lost["onset"]):
        # A loss that began inside a planned window was held then, never raised: the device
        # restarting (or cut off, as predicted) is no incident a person saw, and no match.
        try:
            inside = bool(network) and bool(src.planned(network, device, g["started"]))
        except Exception as exc:                      # noqa: BLE001 (said, never an absence)
            inside, settled = False, False
            left = (f"; the planned-restart record could not be read ({exc}), so a loss "
                    "during a planned restart is not told apart")
        if inside:
            planned += 1
        else:
            past.append(g)
    searched = _searched(hist)
    if settled:
        left = (f"; {planned} loss(es) that began inside a planned window left out (held "
                "then, never raised)" if planned else "")
    if not past:
        return {"state": "none", "why": "", "settled": settled,
                "record": (f"not found: no earlier lost telemetry on {device} in {searched}"
                           + left)}
    causes = {g["started"]: cause_during(diagnoses, g["started"], g["ended"]) for g in past}
    inc, matched = pick(past, cause, causes)
    then = causes.get(inc["started"]) or ""
    end = ended(network, why_no_network, device, inc, src)
    held = held_for(inc, groups, lost["onset"])
    symptom = RUNBOOKS[RUNBOOK]
    if matched == "signature":
        on = (f"the device, the symptom ({symptom}) and the cause "
              f"({CAUSE_WORDS.get(then, then).format(host=device)})")
    else:
        on = (f"the device and the symptom ({symptom}), the nearest in time: "
              + ("its cause then is not recorded" if not then else
                 "this loss's cause is not recorded" if not cause else
                 f"its cause then was another "
                 f"({CAUSE_WORDS.get(then, then).format(host=device)})"))
    back = {}
    if held:
        length = AH.duration_words(held["seconds"])
        if held["now"]:
            back = {"words": f"It held {length}, until this loss began.", "at": "", "tail": ""}
        else:
            back = {"words": f"It held {length}: telemetry was lost again at",
                    "at": _iso(held["returned"]), "tail": "."}
    return {"state": "match", "why": "", "settled": bool(end["settled"]) and settled,
            "from": _iso(inc["started"]), "to": _iso(inc["ended"]),
            "what": (streams_words(inc["subs"]) + " lost for "
                     + AH.duration_words(inc["ended"] - inc["started"]) + "."),
            "cause": (f"Mercury's diagnosis then: "
                      f"{CAUSE_WORDS.get(then, then).format(host=device)}." if then else ""),
            "ended": {k: end[k] for k in ("how", "words", "at", "tail", "list")},
            "held": back, "range": _range_for(inc["started"], src.clock()),
            "record": (f"matched on {on}; {len(past)} earlier incident(s) of this kind on "
                       f"{device} in {searched}; this one {_iso(inc['started'])} to "
                       f"{_iso(inc['ended'])} ({inc['episodes']} alert episode(s)); how it "
                       f"ended ({end['how']}): {end['record'] or 'as said'}" + left)}


# ── Mercury's diagnosis ─────────────────────────────────────────────────────────────────────

def _sentence(text: str) -> str:
    t = str(text or "").strip().rstrip(".")
    return (t[:1].upper() + t[1:] + ".") if t else ""


def finding_words(d: dict, device: str) -> tuple:
    """``(cause, words)``: a recorded stream diagnosis's first hypothesis as its cause class
    and its finding in plain words; ("", words) when it found no cause. A half-open session
    whose facts were kept is said in its three facts; every other finding is its cause class
    and the diagnosis's own claim."""
    hyps = d.get("hypotheses") or []
    if not hyps:
        back = [r.get("check") for r in d.get("ruled_out") or []
                if r.get("rule") == "stream_flowing" and r.get("check")]
        return "", _sentence(back[0] if back else
                             (d.get("words") or "no cause found in what Mercury reads"))
    first = hyps[0]
    rule = str(first.get("rule") or "")
    lead = CAUSE_WORDS.get(rule, "").format(host=device)
    f = first.get("facts") or {}
    if rule == "half_open" and f.get("session") and f.get("connections") and f.get("connected"):
        ids = _and(f["connections"])
        quiet = (f"no data has arrived on it for {span_words(f['quiet_s'])}"
                 if f.get("quiet_s") is not None else
                 "when data last arrived on it was not read")
        noun = "connection" if len(f["connections"]) == 1 else "connections"
        detail = (f"{device} reads Connected on {noun} {ids}, the collector holds "
                  f"{device}'s session ({f['session']}), and {quiet}.")
    else:
        detail = _sentence(first.get("claim"))
    return rule, (f"{_sentence(lead)} {detail}".strip() if lead else detail)


def diagnosis(network: str, why_no_network: str, device: str, onset, got) -> dict:
    """Mercury's diagnosis of THIS loss, as its row draws it: ``{"state", "words", "at", "by",
    "next", "more", "list", "why", "cause", "record"}``. *state* ``read`` (the newest stream
    diagnosis that finished after the loss began), ``not_made`` (one was asked for and
    refused, its words), ``absent`` (none recorded for this loss) or ``unreadable``. *got* is
    the step log's answer for the device (`steplog.diagnoses`), or an exception's words."""
    from modules.heal.diagnose import RUNBOOKS

    out = {"state": "unreadable", "words": "", "at": "", "by": "", "next": "", "more": 0,
           "list": network, "why": "", "cause": "", "record": ""}
    if not network:
        return dict(out, why=why_no_network, record=why_no_network)
    if isinstance(got, str) or (got or {}).get("state") == "unreadable":
        why = (got if isinstance(got, str) else
               f"{network}'s heal step log could not be read ({got.get('error')})")
        return dict(out, why=why, record=why)
    mine = [d for d in got.get("diagnoses") or [] if d.get("runbook") == RUNBOOK]
    named = f"\"{RUNBOOKS[RUNBOOK]}\""
    current = [d for d in mine if onset is not None and (_when(d) or 0) >= onset]
    if not current:
        older = next((d for d in mine if _when(d) is not None), None)
        why = (f"no {named} diagnosis of {device} is recorded since this loss began"
               if onset is not None else
               f"this loss has no recorded start, so no recorded diagnosis can be tied to it")
        if older is not None and onset is not None:
            why += f"; the last one, at {_iso(_when(older))}, was read before it"
        return dict(out, state="absent", why=why, record=why)
    d = current[0]                                    # newest first
    at = _iso(_when(d))
    if d.get("state") != "done":
        why = d.get("words") or f"it ended as {d.get('state') or 'nothing recorded'}"
        return dict(out, state="not_made", why=why, at=at, by=d.get("actor") or "",
                    record=f"diagnosis {d.get('id')}: {why}")
    cause, words = finding_words(d, device)
    hyps = d.get("hypotheses") or []
    first = hyps[0] if hyps else {}
    return dict(out, state="read", words=words, at=at, by=d.get("actor") or "",
                cause=cause, next=str(first.get("todo") or "").rstrip("."),
                more=max(0, len(hyps) - 1) + int(d.get("more") or 0),
                record=(f"diagnosis {d.get('id')} ({named}), read {at}"
                        + (f"; the first of {len(hyps) + int(d.get('more') or 0)} "
                           f"hypotheses, {first.get('strength')}"
                           + ("; its evidence incomplete: "
                              + "; ".join(first.get("incomplete") or [])
                              if first.get("incomplete") else "") if hyps else
                           "; no cause found")))


# ── The whole answer, for the reader ────────────────────────────────────────────────────────

def _held_get(key, now: float):
    with _held_lock:
        got = _held.get(key)
        if got and got[0] > now:
            return dict(got[1])
        _held.pop(key, None)
    return None


def _held_put(key, answer: dict, now: float, seconds: float) -> None:
    with _held_lock:
        if len(_held) >= HELD_MAX:
            for k in sorted(_held, key=lambda k: _held[k][0])[:len(_held) - HELD_MAX + 1]:
                _held.pop(k, None)
        _held[key] = (now + seconds, dict(answer))


def forget() -> None:
    """Drop every held answer (a test's, between its cases)."""
    with _held_lock:
        _held.clear()


def context(value: dict, store: str = "", *, sources=None, limit: int = None) -> dict:
    """What the alerts reader keeps as its value's ``streams``: ``{"state", "at", "why",
    "devices": {device: {"seen", "diagnosis"}}}``, one entry per device with a lost-stream
    alert firing in *value* (the module's docstring; its bound). *limit* is how many devices
    this read searches, the ones lost longest first (`MAX_DEVICES` when none is given, as the
    reader gives none); the rest say they were not searched, naming the number used. Never
    raises: a failure is ``state`` ``unreadable`` with its reason, and every device's line
    then says so."""
    src = sources or Sources()
    try:
        now = float(src.clock())
        lost = lost_now(value)
        cut = MAX_DEVICES if limit is None else max(0, int(limit))
        devices = _answers(lost, store, src, now, cut) if lost else {}
        return {"state": "read", "at": _iso(now), "why": "", "devices": devices}
    except Exception as exc:                          # noqa: BLE001 (the read goes on)
        log.exception("seen_before: the lost streams' records could not be read")
        return {"state": "unreadable", "at": _iso(time.time()),
                "why": f"{type(exc).__name__}: {exc}", "devices": {}}


def _answers(lost: dict, store: str, src, now: float, cut: int) -> dict:
    nets = src.networks()
    # The ones lost longest first; one with no recorded start last.
    order = sorted(lost, key=lambda d: (lost[d]["onset"] is None, lost[d]["onset"] or 0, d))
    out, hist = {}, None
    for device in order[cut:]:
        why = (f"not searched in this read: {len(order)} devices have lost telemetry at "
               f"once, and one read searches the {cut} lost longest")
        out[device] = {"seen": {"state": "unreadable", "why": why, "record": why},
                       "diagnosis": {"state": "unreadable", "why": why, "record": why,
                                     "words": "", "at": "", "by": "", "next": "", "more": 0,
                                     "list": "", "cause": ""}}
    for device in order[:cut]:
        network, no_net = _network_of(nets, device)
        got = None
        if network:
            try:
                got = src.diagnoses(network, device)
            except Exception as exc:                  # noqa: BLE001 (said)
                got = f"{network}'s heal step log could not be read ({exc})"
        diag = diagnosis(network, no_net, device, lost[device]["onset"], got)
        key = (store, network, device, int(lost[device]["onset"] or 0), diag["cause"],
               tuple(lost[device]["subs"]))
        answer = _held_get(key, now)
        if answer is None:
            if hist is None:
                hist = src.history()
            answer = seen(store, network, no_net, device, lost[device], diag["cause"], hist,
                          (got or {}).get("diagnoses") if isinstance(got, dict) else None, src)
            answer = {k: v for k, v in answer.items() if k != "settled"} | {
                "_settled": bool(answer.get("settled"))}
            _held_put(key, answer, now, HELD_S if answer["_settled"] else RETRY_S)
        answer.pop("_settled", None)
        out[device] = {"seen": answer, "diagnosis": diag}
    return out
