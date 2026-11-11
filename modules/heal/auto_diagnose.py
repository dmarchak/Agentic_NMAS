"""The automatic diagnosis (board H's amendment, item 1, part H17; docs/HEAL_TO_INTENT.md 19.3,
N14 and N24): a diagnosis runbook run by self-healing itself, on an Alert incident before its
notice is sent and on a Propose incident before a person approves it, its diagnosis attached to
the incident. Read-only and deterministic, as every diagnosis is (`modules/heal/diagnose.py`):
it sends no command that is not a read, changes nothing and calls no model.

**Which incidents** (N14):
- **Alert** (`ALERT`): the decision stopped at can't fix at Tier 3 (`is_alert`: down while
  administratively up with the configuration at intent, or a symptom with no cause found). The
  notifier runs it before it sends (`modules/heal_notice.py`), and waits for it up to `WAIT_S`.
- **Propose** (`PROPOSE`): a Tier 2 proposal waiting for a person (`decisions.proposals`).
  The runner starts it once the decision is recorded (`proposals_step`), so the proposal's card
  draws it running, then drawn, beside Approve… (artboard E's insert).
- **Never** and the other can't-fix outcomes run none: Diagnose… on their rows runs one.

**Its runbook and target, from what raised the incident** (`target_for`, its triggers in order,
the first that names one): a lost telemetry stream (an alert of the stream rules, by its
subscription label or its rule's title) runs "a telemetry stream lost" on the device, first
whatever else raised it, with its likely cause read from the heal records (C2828,
`modules/heal/diagnose_stream.py`); an alert whose rule is the device unreachable runs "A can't reach
B" toward the device's intended loopback from its first neighbour by intent; an alert naming
an interface, or a routing adjacency down or logged naming its other end, runs "adjacency down
with both ends at intent" on the adjacency intent holds over that interface or toward that
end, and only on it: a named interface intent holds no adjacency over is not diagnosed, said,
never swapped for another link. Anything else is not diagnosed, said, with Diagnose… on its
row.

**Its bounds** (N24): one automatic diagnosis per incident (`claim`, under the store's lock
across processes); at most `MAX_AT_ONCE` (3) at once per network (`AutoSlots`, three exclusive
`flock` slots the kernel releases with their holder), the rest "not diagnosed: 3 diagnoses
already running on <network>"; and the diagnosis's own (one at a time per device, 70 commands,
14 a device). A diagnosis not made is recorded too, attached to its incident with its words,
so its row says why and offers Diagnose… (never a silent absence).

**What it ends with:** the ``diagnosis`` row in the step log (`steplog.record_diagnosis`,
through `diagnose.run`), and the announcement ``diagnosis`` (C2584: a Diagnose… card waiting
on a device this run held reads again) with ``drift`` (the Needs attention rows the heal
raises). "Diagnosed" is not a fix: it clears nothing.

**What leaves the host, by kind** (`said`): a hypothesis is said by its rule's words, its
strength and the ends or hops it read ("the MTU differs between the ends: edge1 Gi4, edge2 Gi4,
decisive"), never the values it compared, an access list's entries, a key or a configuration
line (section 10's messages; N23 for the AI analysis's pack section, the values held back
until the device state class exists, C2419). The screens in Mercury draw the claims whole.
"""

import json
import logging
import os
import re
import threading
import time

log = logging.getLogger(__name__)

ALERT, PROPOSE = "alert", "propose"
KINDS = (ALERT, PROPOSE)
#: At most this many automatic diagnoses at once per network (N24).
MAX_AT_ONCE = 3
#: How long the notice waits for its diagnosis: 2.5 times the top of 19.3's 30 to 60 s
#: estimate, until H18 measures the runbook's run time in the lab (C2546).
WAIT_S = 150.0
#: Who an automatic diagnosis is recorded as.
ACTOR = "Mercury (self-healing)"
#: The claims store's file, in the network's heal folder.
FILE = "auto_diagnoses.jsonl"
SLOT_DIR = os.path.join("heal", "diagnosis")
#: The steps, in order, for the manual's How it works page (H10).
STEPS = (("which", "An Alert incident before its notice, or a Propose incident before its "
                   "approval"),
         ("claim", "Take it once, under the store's lock"),
         ("target", "Choose the runbook and its target from what raised it"),
         ("slot", "Take one of the network's three automatic slots, or say they are taken"),
         ("diagnose", "Run the diagnosis: reads only, through the reads engine"),
         ("record", "Attach the diagnosis to the incident, or why none was made"),
         ("announce", "Announce it, so every card waiting on it reads again"))
#: The rules whose cause is not the configuration: a fix to configuration never changes them
#: (a proposal whose first decisive hypothesis is one says so, 19.3).
NOT_CONFIGURATION = ("down_admin_up", "cabled_elsewhere", "errors_rising", "protocol_down",
                     "hop_down", "hop_errors_rising", "hop_protocol_down")
STRENGTH_WORDS = {"decisive": "decisive", "strong": "strong",
                  "circumstantial": "circumstantial"}
#: An interface name in a read's command, in intent's shape (diagnose's own).
_IFNAME = re.compile(r"[A-Za-z][A-Za-z-]{0,30}[0-9][0-9/.:]{0,15}")


class AllBusy(RuntimeError):
    """Every automatic slot of the network is held: not diagnosed, said, never queued."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


# ── Which incidents ─────────────────────────────────────────────────────────────────────────

#: C2825: each runbook's check that, passed, says the symptom it was run for is itself absent
#: now: "adjacency down with both ends at intent" reading the adjacency up at both ends
#: (`diagnose._r_one_way`'s passed check), "A can't reach B" with every probe answered
#: (`diagnose_reach._reached`).
SYMPTOM_GONE_RULES = {"adjacency_down": "one_way", "cant_reach": "reach",
                      # C2892: a lost stream's every subscription back in Prometheus, by the
                      # lost-stream alert's own query (`diagnose_stream._r_stream_flowing`).
                      "stream_lost": "stream_flowing"}


def symptom_gone(d: dict) -> str:
    """C2825: the words of the check by which Mercury's diagnosis *d* read the symptom it was
    run for gone (`SYMPTOM_GONE_RULES`), or ``""``. Only a diagnosis that finished, stopped at
    no cap, found no hypothesis, and ruled that check out: anything else (refused, busy, not
    finished, a cause found) is not evidence the symptom cleared."""
    d = d or {}
    if (d.get("state") in ("refused", "busy", "running", "not_finished", "failed")
            or d.get("stopped") or d.get("hypotheses")):
        return ""
    rule = SYMPTOM_GONE_RULES.get(d.get("runbook") or "")
    return next((r.get("check") or "" for r in d.get("ruled_out") or []
                 if rule and r.get("rule") == rule), "")


def is_alert(entry: dict) -> bool:
    """Whether the incident's step log *entry* stopped at can't fix at Tier 3 (Alert): the
    decision's outcome, its tier as recorded."""
    return (entry or {}).get("outcome") == "cant_fix" and int(
        (entry or {}).get("tier") or 0) == 3


# ── The claims (one automatic diagnosis per incident) ───────────────────────────────────────

def path(network: str) -> str:
    from modules.heal.incidents import _dir

    return os.path.join(_dir(network), FILE)


def read(network: str) -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``, oldest first; a read creates
    nothing."""
    p = path(network)
    if not os.path.exists(p):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(p, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [],
                "error": f"{network}'s automatic diagnoses cannot be read ({type(exc).__name__})"}
    return {"state": "ok", "rows": rows, "error": ""}


def claimed(network: str) -> set:
    """The incidents an automatic diagnosis was taken for. Raises when the store cannot be
    read: nothing is diagnosed twice for want of a read."""
    got = read(network)
    if got["state"] == "unreadable":
        raise RuntimeError(got["error"])
    return {r.get("incident") for r in got["rows"]}


def claim(network: str, incident_id: str, kind: str, now: float = None) -> bool:
    """Take *incident_id* for its one automatic diagnosis: True when this call took it, False
    when it was taken before. Under the store's lock across processes. Raises when the store
    cannot be read, or the network is none."""
    from modules import filestore
    from modules.config import open_secure
    from modules.nsot import listref

    if not network or not listref.exists(network):
        raise ValueError(f"{network or 'no network'} is no network, so nothing is diagnosed")
    if kind not in KINDS:
        raise ValueError(f"an automatic diagnosis is for {' or '.join(KINDS)}, not {kind!r}")
    now = time.time() if now is None else float(now)
    p = path(network)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with filestore.PathLock(p):
        if incident_id in claimed(network):
            return False
        with open_secure(p, "a") as fh:
            fh.write(json.dumps({"incident": incident_id, "kind": kind, "network": network,
                                 "at": _iso(now), "epoch": now}, sort_keys=True) + "\n")
    return True


# ── The storm bound (N24) ───────────────────────────────────────────────────────────────────

class AutoSlots:
    """One of `MAX_AT_ONCE` automatic slots of *network*, across processes: an exclusive
    `flock` on the first free slot's file, released by the kernel with its holder. All taken
    raises `AllBusy` naming the count, never waits."""

    def __init__(self, network: str, size: int = None):
        self.network, self.size, self.fd = network, size or MAX_AT_ONCE, None

    def _path(self, n: int) -> str:
        from modules.config import list_data_path
        return os.path.join(list_data_path(self.network), SLOT_DIR, f"auto-slot-{n}.lock")

    def __enter__(self):
        import fcntl

        for n in range(self.size):
            p = self._path(n)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            fd = os.open(p, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                continue
            self.fd = fd
            return self
        raise AllBusy(f"not diagnosed: {self.size} diagnoses already running on "
                      f"{self.network}, the most self-healing runs at once (N24); Diagnose… "
                      "runs one")

    def __exit__(self, *exc):
        import fcntl

        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None
        return False


# ── The runbook and its target ──────────────────────────────────────────────────────────────

def _heal_records(network: str, every, decided) -> tuple:
    """``(incidents, decisions)`` for the stream runbook's cause: those given, else read (a
    store that cannot be read gives None, and the cause is said not read)."""
    from modules.heal import decisions, incidents

    if every is None:
        try:
            got = incidents.read(network)
            every = got.get("incidents") if got.get("state") != "unreadable" else None
        except Exception as exc:                      # said as the cause not read
            log.info("heal: %s's incidents not read for a stream's cause: %s", network, exc)
    if decided is None:
        try:
            decided = decisions.decisions(network)
        except Exception as exc:                      # said as the cause not read
            log.info("heal: %s's decisions not read for a stream's cause: %s", network, exc)
    return every, decided


def target_for(network: str, incident: dict, *, model: dict = None,
               intents: dict = None, incidents: list = None, decided: list = None) -> dict:
    """``{"runbook", "target", "words"}`` for *incident* (its record, with its triggers), or
    ``{"why"}`` naming why none fits. Reads intent and the network model; a lost telemetry
    stream also reads the heal records for its cause (*incidents*, *decided*: the network's
    incidents and decisions, read when not given)."""
    from modules.heal import diagnose as D
    from modules.heal import diagnose_page as P
    from modules.heal import diagnose_reach as R
    from modules.heal import diagnose_stream as S
    from modules.neighbours import _all_lines

    host = (incident or {}).get("device") or ""
    if not host:
        return {"why": "the incident names no device"}
    # C2828: a lost telemetry stream runs its own runbook, the device to its collector on the
    # stream's port, before any other trigger's: an unreachable alert on the same device is
    # read by it too (the device not read is its own hypothesis, naming Can't reach).
    if any(S.stream_of(t) for t in (incident or {}).get("triggers") or []):
        every, decided = _heal_records(network, incidents, decided)
        target = S.target_from(incident, every, decided)
        return {"runbook": S.RUNBOOK, "target": target,
                "words": (f"\"{D.RUNBOOKS[S.RUNBOOK]}\" on {host} "
                          f"({S._subs_words(target['subscriptions'])})")}
    pick = None
    for t in (incident or {}).get("triggers") or []:
        if not isinstance(t, dict):
            continue
        kind = t.get("kind")
        if kind == "alert" and P.UNREACHABLE in (t.get("rule") or "").lower():
            pick = ("reach", t.get("rule") or "", "")
        elif kind == "alert" and t.get("interface"):
            pick = ("link", str(t["interface"]), "")
        elif kind in ("adjacency", "adjacency_log") and t.get("related"):
            pick = ("link", "", sorted(t["related"])[0])
        if pick:
            break
    if pick is None:
        kinds = sorted({str(t.get("kind")) for t in (incident or {}).get("triggers") or []
                        if isinstance(t, dict)})
        return {"why": ("no runbook fits what raised it (" + (", ".join(kinds) or "nothing")
                        + "): the runbooks read an adjacency, an interface, a device not "
                          "reached or a telemetry stream lost")}
    try:
        if model is None or intents is None:
            model, intents = D._sources(network, model, intents)
    except D.Refused as exc:
        return {"why": str(exc)}
    what, interface, neighbour = pick
    if what == "reach":
        near = P.nearest(model, host)
        if not near:
            return {"why": f"intent cables {host} to no other device to diagnose from"}
        _name, address = R._loopback(_all_lines(intents or {}).get(host) or {})
        if not address:
            return {"why": f"intent gives {host} no loopback address to reach"}
        return {"runbook": "cant_reach", "target": {"device": near[0], "address": address},
                "words": f"{R.named(near[0], address)} ({host})"}
    offered, _not = P.adjacencies(network, host, model, intents)
    if not offered:
        return {"why": f"intent holds no adjacency on {host} whose diagnosis can be planned"}
    value, hint = P._hinted(offered, interface, neighbour)
    if hint:
        named = interface or f"the link toward {neighbour}"
        return {"why": (f"what raised it names {named}, and intent holds no adjacency over it "
                        "that can be diagnosed; no other link is read in its place")}
    target, why = P.target_of(host, "adjacency_down", value, "", "")
    if target is None:
        return {"why": why}
    return {"runbook": "adjacency_down", "target": target,
            "words": f"\"adjacency down with both ends at intent\" on {host} ({value})"}


# ── The run ─────────────────────────────────────────────────────────────────────────────────

def _not_diagnosed(network: str, incident: dict, incident_id: str, words: str, state: str,
                   now: float, record: bool = True) -> dict:
    """A diagnosis not made, as a diagnosis: its words, nothing read, attached to its incident
    so its row says why."""
    from modules.heal import diagnose as D
    from modules.heal import steplog

    host = (incident or {}).get("device") or ""
    out = {"id": D.new_id(), "network": network, "runbook": "", "runbook_words": "",
           "target": {"device": host} if host else {}, "incident": incident_id,
           "actor": ACTOR, "started_at": _iso(now), "finished_at": _iso(now),
           "state": state, "words": words, "steps": [{"step": "plan", "result": "refused",
                                                      "words": words}],
           "hypotheses": [], "more": 0, "ruled_out": [], "not_checked": [], "commands": 0,
           "cap": D.MAX_COMMANDS, "runs": [], "stopped": "", "devices": [host] if host else []}
    if record:
        try:
            steplog.record_diagnosis(network, out, now)
            out["recorded"] = True
        except Exception as exc:                      # said on the result, never raised
            log.error("heal: %s's diagnosis of %s could not be recorded: %s", network,
                      incident_id, exc)
            out["recorded"] = False
    return out


def _announce() -> None:
    try:
        from modules import invalidation
        invalidation.announce(invalidation.ANNOUNCERS["heal-diagnose"], by="heal-diagnose")
    except Exception as exc:                          # the record stands; a page re-reads later
        log.info("heal: an automatic diagnosis recorded, not announced: %s", exc)


def run(network: str, incident_id: str, kind: str, *, diagnose=None, model: dict = None,
        intents: dict = None, now: float = None) -> dict:
    """One incident's automatic diagnosis, once: the diagnosis as recorded (`diagnose.run`'s,
    or one not made, with its words), or ``{"state": "taken"}`` when it was taken before.
    Never raises. *diagnose* replaces `diagnose.run` (tests): ``(network, runbook, target,
    actor, incident=...) -> diagnosis``."""
    from modules.heal import diagnose as D
    from modules.heal import incidents

    now = time.time() if now is None else float(now)
    try:
        if not claim(network, incident_id, kind, now):
            return {"state": "taken", "incident": incident_id}
    except Exception as exc:                          # said; nothing read
        log.error("heal: %s's automatic diagnosis of %s was not taken: %s", network,
                  incident_id, exc)
        return {"state": "failed", "incident": incident_id,
                "words": f"not diagnosed: it could not be taken ({type(exc).__name__}: {exc})"}
    every = None
    try:
        got = incidents.read(network)
        every = got.get("incidents") or []
        incident = next((i for i in every if i.get("id") == incident_id), {})
    except Exception as exc:                          # said on its row
        incident = {}
        why = f"the incident could not be read ({type(exc).__name__}: {exc})"
    else:
        why = "" if incident else "the incident is no longer in the heal incidents' store"
    pick = {"why": why} if why else target_for(network, incident, model=model, intents=intents,
                                               incidents=every)
    if pick.get("why"):
        out = _not_diagnosed(network, incident, incident_id,
                             f"not diagnosed: {pick['why']}", "refused", now)
        _announce()
        return out
    fn = diagnose or D.run
    try:
        with AutoSlots(network):
            kw = {"incident": incident_id}
            if diagnose is None:
                kw.update(model=model, intents=intents)
            out = fn(network, pick["runbook"], pick["target"], ACTOR, **kw)
    except AllBusy as exc:
        out = _not_diagnosed(network, incident, incident_id, str(exc), "busy", now)
    except Exception as exc:                          # said on its row, never raised
        log.exception("heal: %s's automatic diagnosis of %s failed", network, incident_id)
        out = _not_diagnosed(network, incident, incident_id,
                             f"not diagnosed: the run failed ({type(exc).__name__}: {exc})",
                             "refused", now)
    _announce()
    return out


def start(network: str, incident_id: str, kind: str, **kw) -> threading.Thread:
    """`run` in its own thread (a proposal's: the runner never waits on device reads)."""
    t = threading.Thread(target=run, args=(network, incident_id, kind), kwargs=kw,
                         daemon=True, name=f"heal-diagnose-{incident_id}")
    t.start()
    return t


def proposals_step(network: str, starter=None) -> list:
    """The runner's step after the decision (N14): each proposal waiting for a person whose
    incident has no automatic diagnosis yet, started in its own thread (*starter*, `start`
    unless given). Returns the incidents started. A store that cannot be read starts none,
    logged."""
    from modules.heal import decisions

    try:
        waiting = decisions.proposals(network)
        taken = claimed(network)
    except Exception as exc:
        log.error("heal: %s's proposals are not diagnosed this pass: %s", network, exc)
        return []
    out = []
    for d in waiting:
        inc = d.get("incident") or ""
        if not inc or inc in taken or inc in out:
            continue
        (starter or start)(network, inc, PROPOSE)
        out.append(inc)
    return out


# ── What it says: by kind off the host, whole in Mercury ────────────────────────────────────

def _rule_words(d: dict = None) -> dict:
    """Each rule's words; a reach rule's with diagnosis *d*'s own ends (C2878: its target's
    device and address), "the source" and "the destination" where none is given."""
    from modules.heal import diagnose as D
    from modules.heal import diagnose_reach as R
    from modules.heal import diagnose_stream as S

    t = (d or {}).get("target") or {}
    ends = {"source": t.get("device") or "the source",
            "dest": t.get("address") or "the destination"}
    ends["owner"] = ends["dest"]
    return {r.name: (r.words.format(**ends) if isinstance(r, R.PathRule) else r.words)
            for r in tuple(D.RULES) + tuple(R.PATH_RULES) + tuple(S.STREAM_RULES)}


def where(h: dict) -> list:
    """The ends or hops a hypothesis read, in order, each once: each read's device and the
    interface its command names (abbreviated, as intent's links write it), from its evidence's
    references; never a value."""
    from modules.nsot.ifnames import abbreviate

    out = []
    for e in h.get("evidence") or []:
        parts = str(e.get("read") or "").split(":", 3)
        host, command = "", ""
        if len(parts) == 4 and parts[0] == "read":
            host, command = parts[2], parts[3]
        elif len(parts) >= 2 and parts[0] == "log":
            host = parts[1]
        if not host:
            continue
        port = next((w for w in command.split()[1:] if _IFNAME.fullmatch(w)), "")
        said_ = f"{host} {abbreviate(port) or port}" if port else host
        if said_ in out or (said_ == host and any(o.split(" ", 1)[0] == host for o in out)):
            continue
        out.append(said_)
    return out


def said(h: dict, words: dict = None) -> str:
    """One hypothesis by kind: its rule's words, the ends or hops it read, its strength, and
    whether its evidence is incomplete; never the values it compared."""
    words = words if words is not None else _rule_words()
    w = words.get(h.get("rule") or "", "") or f"a {h.get('layer') or 'cause'} fault"
    at = where(h)
    strength = STRENGTH_WORDS.get(h.get("strength") or "", h.get("strength") or "")
    tail = strength + (", evidence incomplete" if h.get("incomplete") else "")
    return f"{w[:1].upper()}{w[1:]}" + (f": {', '.join(at)}" if at else "") + f" ({tail})"


def ruled_out_words(d: dict, words: dict = None) -> list:
    """What was ruled out, by kind: each passed check's rule in its words."""
    words = words if words is not None else _rule_words()
    return [words.get(r.get("rule") or "", "") for r in d.get("ruled_out") or []
            if words.get(r.get("rule") or "", "")]


def summary(d: dict) -> dict:
    """The diagnosis by kind, as a message and the AI analysis's pack carry it: ``{"state",
    "words", "reads", "hypotheses": [{"claim", "strength", "rule", "layer", "incomplete"}],
    "ruled_out"}``. A diagnosis not made is its words alone."""
    words = _rule_words(d)
    if not d:
        return {"state": "none", "words": "", "reads": "", "hypotheses": [], "ruled_out": []}
    state = d.get("state") or ""
    if state in ("refused", "busy", "running", "not_finished"):
        return {"state": state, "words": d.get("words") or "", "reads": "", "hypotheses": [],
                "ruled_out": []}
    devices = list(d.get("devices") or [])
    reads = (f"read-only; {int(d.get('commands') or 0)} reads on "
             + (" and ".join([", ".join(devices[:-1]), devices[-1]]) if len(devices) > 1
                else (devices[0] if devices else "no device")))
    hyps = [{"claim": said(h, words), "strength": h.get("strength") or "",
             "rule": h.get("rule") or "", "layer": h.get("layer") or "",
             "incomplete": bool(h.get("incomplete"))} for h in d.get("hypotheses") or []]
    return {"state": "done", "words": ("no cause found in what Mercury reads" if not hyps else
                                       f"{len(hyps)} hypothes{'i' if len(hyps) == 1 else 'e'}s, "
                                       f"the first {hyps[0]['strength']}"),
            "reads": reads, "hypotheses": hyps, "ruled_out": ruled_out_words(d, words)}


def addresses(d: dict) -> str:
    """What a proposal's card says of its diagnosis (19.3): when the first hypothesis is
    decisive and its cause is not the configuration (`NOT_CONFIGURATION`), that the fix does
    not change it; otherwise nothing (Mercury does not judge that a fix addresses a
    hypothesis)."""
    hyps = (d or {}).get("hypotheses") or []
    if not hyps:
        return ""
    first = hyps[0]
    if first.get("strength") == "decisive" and first.get("rule") in NOT_CONFIGURATION:
        return (f"the diagnosis's first hypothesis is that {first.get('claim') or 'a physical '
                'fault'}, which this fix does not change: a change to configuration never "
                "changes a physical or link fault")
    return ""


#: What a row and a card draw of a diagnosis (`diagnose_page.result`'s fields): its headline,
#: the ranked hypotheses whole (in Mercury, masked), what was ruled out, where it stopped.
#: Each read, each step and what was not checked are on History, one click away.
SHOWN = ("chip", "level", "words", "runbook_words", "actor", "incident", "finished_at",
         "commands", "devices", "more", "ruled_out", "stopped")
SHOWN_HYPOTHESIS = ("claim", "strength", "layer", "incomplete", "todo")


def shown(result: dict) -> dict:
    """*result* (`diagnose_page.result`) cut to what the row and the card draw (`SHOWN`)."""
    out = {k: result.get(k) for k in SHOWN}
    out["hypotheses"] = [{k: h.get(k) for k in SHOWN_HYPOTHESIS}
                         for h in result.get("hypotheses") or []]
    return out


def drawn(network: str, incident_id: str, host: str = "", d: dict = None,
          read: bool = True) -> dict:
    """The incident's diagnosis as its row and its proposal's card draw it: ``{"state",
    "error", "result", "running", "addresses"}``: ``done`` (`diagnose_page.result` of the
    newest attached), ``not`` (one not made, its words), ``running`` (*host* held by a
    diagnosis now, read from its lock WITHOUT taking it), or ``none``. *d* is the attached
    diagnosis already read (the step log's entry); with none given and *read*, the step log is
    read. *addresses* is what a proposal's card says of it (`addresses`)."""
    from modules.heal import diagnose as D
    from modules.heal import diagnose_page as P
    from modules.heal import steplog

    if not d and read and incident_id:
        got = steplog.diagnoses(network, incident=incident_id)
        if got["state"] == "unreadable":
            return {"state": "unreadable", "error": got["error"], "result": None,
                    "running": None, "addresses": ""}
        d = (got["diagnoses"] or [None])[0]
    if d:
        if d.get("state") in ("refused", "busy"):
            return {"state": "not", "error": "", "result": {"words": d.get("words") or ""},
                    "running": None, "addresses": ""}
        return {"state": "done", "error": "", "result": shown(P.result(d)), "running": None,
                "addresses": addresses(d)}
    busy = D.in_diagnosis(network, [host]).get(host) if host else None
    if busy:
        return {"state": "running", "error": "", "result": None, "addresses": "",
                "running": {"diagnosis": busy.get("diagnosis") or "",
                            "actor": busy.get("actor") or "an unrecorded caller",
                            "since": busy.get("started_at") or ""}}
    return {"state": "none", "error": "", "result": None, "running": None, "addresses": ""}
