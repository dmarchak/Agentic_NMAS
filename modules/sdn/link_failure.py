"""Link failure on an SDN fabric (Lab 9 B3; board F of docs/boards/lab9-sdn.html): the fifth
detection rule, ``link_down``, and its response, which verifies the reroute. Deterministic: no
AI call is made for a link that went down (it is a fact the switches report, not a judgement).

**The rule** (`rule`, run by `detect.observe` over the loop's collection, which asks for link
status: `closed_loop.collect_threat_data(links=True)`, each switch's port descriptions and each
connection's discovered links; the same read the analyst's collection makes, C2903). A link is
one the topology HELD: listed by the controller's link discovery in this collection or an
earlier one (kept in the detection state, ``links``, per connection; `held`). It is **down**
when, in a collection that read its ends:
- either end's port reports its link down (the state's LINK_DOWN bit, never LIVE, C2602) or is
  administratively down (the config's PORT_DOWN bit), or is no longer listed by its switch, or
  its switch is no longer connected to the controller: confidence high, at once;
- or the controller no longer lists the link while both ports report up, for `GONE_READS`
  collections in a row (one read without it can be link discovery's own timing): confidence
  lower, saying so.
A link one of whose switches' port descriptions could not be read, or a connection whose links
could not be read, is not judged: it keeps firing if it was, and resolves only when a
collection that read it shows it listed and both ports up. A collection that did not ask for
link status (the SDN reader's, an older one) judges no link. One link is one detection, its
ends in one order (`link_key`), whichever end reported it: never one per side.

**What a detection carries** beyond the other rules' fields: ``link`` (its key, both ends with
each one's state in words, and how it went: ``down`` or ``gone``) and ``affected``: the hosts
the controller's topology lists on each end's switch, each by its address (its first IPv4,
else its first global IPv6, `detect.host_address`: IPv4 and IPv6 alike) and MAC.

**The response** (`verify`): the network's forwarding application (Lab 9's fabric_forwarding,
lab/lab9/apps/fabric_forwarding: "rerouting on link down") recomputes every path at once when
a port goes down, overwriting its own flows. So Mercury does not install a second reroute: two
writers of one flow would fight, and the app owns its flows by cookie. Mercury's automated
response is to **verify** that the reroute happened, from the trace over the controller's flow
tables (`modules/sdn/trace.py`, the SDN reader's stored read: no controller call), for every
pair of hosts the fabric lists (at most `MAX_PAIRS`, the rest counted): each must be delivered,
on a path that does not leave by either end of the failed link. The outcome is one of
`OUTCOMES`:
- ``rerouted``: every pair checked is delivered on another path;
- ``not_rerouted``: a pair is not delivered (the trace's words name where it ended);
- ``cannot_tell``: none failed, and the trace cannot follow at least one (a group, NORMAL);
- ``pending``: the stored read is from before the failure, or still lists the link: Mercury
  waits for the next read (every 30 s), never judging the old tables as the new;
- ``no_pairs``: fewer than two hosts are listed, so there is no path to check.
**Nothing is written by the response, so nothing is rolled back:** a verify that fails, or is
not answered within `VERIFY_WINDOW_S`, is the person's (the card says what the trace found),
never retried as a write.

**The modes** (`modes.decide`, the same guard as every response): in AUTO (on, on a network
marked lab), the loop verifies at each pass from the detection until the outcome is final
(``rerouted``, or anything else once `VERIFY_WINDOW_S` has passed), and records each outcome
as Mercury's; in HITL (the default) the card awaits a person, whose Verify the reroute runs the
same check (`sdn_v2.link_verify`). Either way the card stays until the link is listed and up
again (``restored``, the detection resolving) or a person dismisses it with a reason.

**The store** (``sdn_links.jsonl`` in the network's folder): append-only, owner-only, under a
cross-process lock: ``down`` (the detection, the mode decided and why), any number of
``verified`` (who, the outcome, its words, the pairs and the read's time), then one of
``restored`` or ``dismissed`` (who and why). `open_rows` reads the cards still open.
"""

import json
import logging
import os
import secrets
import time

log = logging.getLogger(__name__)

RULE = "link_down"
#: Collections in a row the controller may not list a link whose ports report up before it is
#: called down (board F: "a link gone for 2 reads").
GONE_READS = 2
STORE_FILE = "sdn_links.jsonl"
#: The response's one action: a read, so its risk is the least (AUTO's low class allows it).
ACTION = "verify_reroute"
RISK = "low"
OUTCOMES = ("rerouted", "not_rerouted", "cannot_tell", "pending", "no_pairs")
#: The outcomes after which AUTO stops verifying (the rest wait for the deadline).
FINAL = ("rerouted",)
#: The most host pairs one verify traces (ordered pairs: 4 hosts make 12); the rest counted.
MAX_PAIRS = 12
#: How long AUTO keeps verifying a link's reroute before leaving it to a person: about 2.5
#: times the SDN reader's interval (30 s, `readers/sdn_controllers.INTERVAL_SECONDS`), so its
#: stored read has been taken at least twice after the failure. Not measured on the lab's
#: hardware yet: the five-minute run measures it.
VERIFY_WINDOW_S = 75
#: An end's states that make a link down, each in words.
DOWN_STATES = {"link_down": "reports its link down (LINK_DOWN)",
               "admin_down": "is administratively down (PORT_DOWN)",
               "port_gone": "is no longer listed by its switch",
               "switch_gone": "is on a switch no longer connected to the controller"}
CLOSED = ("restored", "dismissed")


# ───────────────────────────────────────────────────────────────────────────── the rule

def _end(port: dict) -> dict:
    from modules.sdn.drivers.base import dpid_hex, parse_dpid

    dpid = parse_dpid(port.get("dpid"))
    return {"dpid": dpid, "dpid_hex": dpid_hex(dpid), "port_no": port.get("port_no"),
            "name": str(port.get("name") or "")}


def _end_key(end: dict) -> str:
    return f"{end['dpid_hex']}:{end['port_no']}"


def link_key(a: dict, b: dict) -> str:
    """One link's key whichever way it is listed: its two ends in order."""
    return "-".join(sorted((_end_key(a), _end_key(b))))


def discovered(links: list) -> dict:
    """``{key: {"ends": [a, b]}}``: the links a controller lists, each direction one link."""
    out = {}
    for l in links or []:
        try:
            a, b = _end(l["src"]), _end(l["dst"])
        except Exception:                             # noqa: BLE001 (a link not read is no link)
            continue
        key = link_key(a, b)
        if key not in out:
            out[key] = {"ends": sorted([a, b], key=_end_key)}
    return out


def end_words(end: dict) -> str:
    port = f"port {end['port_no']}" + (f" ({end['name']})" if end.get("name") and
                                        str(end["name"]) != str(end["port_no"]) else "")
    return f"{end['dpid_hex']} {port}"


def link_words(ends: list) -> str:
    return " to ".join(end_words(e) for e in ends)


def _port_state(ctl: dict, end: dict) -> tuple:
    """``(state, words)`` of one end in this collection: ``up``, one of `DOWN_STATES`, or
    ``unread`` (its switch's port descriptions not read, said why)."""
    sw = next((s for s in ctl.get("switches") or [] if s.get("dpid") == end["dpid"]), None)
    if sw is None:
        return "switch_gone", DOWN_STATES["switch_gone"]
    if "port_desc" not in sw:
        return "unread", "its switch's port descriptions were not asked for"
    if sw.get("port_desc_error"):
        return "unread", f"its switch's port descriptions could not be read: " \
                         f"{sw['port_desc_error']}"
    port = next((p for p in sw.get("port_desc") or []
                 if str(p.get("port_no")) == str(end["port_no"])), None)
    if port is None:
        return "port_gone", DOWN_STATES["port_gone"]
    if not port.get("link_up", True):
        return "link_down", DOWN_STATES["link_down"]
    if not port.get("admin_up", True):
        return "admin_down", DOWN_STATES["admin_down"]
    return "up", "reports its link up"


def affected(topo, connection: str, ends: list) -> list:
    """The hosts the controller's topology (*topo*, `topology.stored`'s) lists on each end's
    switch: ``[{"address", "mac", "dpid_hex", "port_no"}]``, by `detect.host_address` (IPv4
    first, else a global IPv6), sorted; a host with no such address is named by its MAC."""
    from modules.sdn import detect
    from modules.sdn.drivers.base import dpid_hex

    dpids = {e["dpid"] for e in ends}
    ctl = next((c for c in (topo or {}).get("controllers") or []
                if c.get("name") == connection), None) or {}
    out = []
    for h in ctl.get("hosts") or []:
        try:
            dpid = int(h.get("dpid"))
        except (TypeError, ValueError):
            continue
        if dpid not in dpids:
            continue
        out.append({"address": detect.host_address(h), "mac": str(h.get("mac") or "").lower(),
                    "dpid_hex": dpid_hex(dpid), "port_no": h.get("port_no")})
    return sorted(out, key=lambda h: (h["dpid_hex"], str(h["port_no"]), h["address"], h["mac"]))


def rule(collected: dict, held: dict = None, topo: dict = None) -> dict:
    """The link-down rule over *collected* (`collect_threat_data(links=True)`'s answer), with
    *held* the links the topology held before (the detection state's ``links``: ``{connection:
    {key: {"ends", "first_seen", "last_seen", "gone"}}}``). ``{"detections", "judged", "held",
    "notes"}``: *judged* each link's scope (``link:<connection>:<key>``) this collection judged;
    *held* the state to keep."""
    from modules.sdn import closed_loop, detect

    held = {c: dict(v) for c, v in (held or {}).items()}
    at = collected.get("collected_at") or ""
    out = {"detections": [], "judged": set(), "held": held, "notes": []}
    for ctl in collected.get("controllers") or []:
        conn = ctl.get("connection") or ""
        if "links" not in ctl:
            continue                                  # link status not asked for: not judged
        mine = {k: dict(v) for k, v in (held.get(conn) or {}).items()}
        if ctl.get("links_error"):
            out["notes"].append(f"{conn}'s links could not be read ({ctl['links_error']}), so "
                                "no link was judged")
            held[conn] = mine
            continue
        listed = discovered(ctl.get("links"))
        for key, link in listed.items():
            entry = mine.setdefault(key, {"ends": link["ends"], "first_seen": at,
                                          "last_seen": at, "gone": 0})
            entry["ends"], entry["last_seen"] = link["ends"], at
        for key in sorted(mine):
            entry = mine[key]
            ends = entry["ends"]
            states = [_port_state(ctl, e) for e in ends]
            if any(s == "unread" for s, _w in states):
                continue
            present = key in listed
            entry["gone"] = 0 if present else int(entry.get("gone") or 0) + 1
            out["judged"].add(scope(conn, key))
            down = [(e, s, w) for e, (s, w) in zip(ends, states) if s in DOWN_STATES]
            if not down and (present or entry["gone"] < GONE_READS):
                continue
            how = "down" if down else "gone"
            first = down[0][0] if down else ends[0]
            sw = next((s for s in ctl.get("switches") or [] if s.get("dpid") == first["dpid"]),
                      None) or next((s for s in ctl.get("switches") or []
                                     if s.get("dpid") in {e["dpid"] for e in ends}), None) \
                or {"dpid": first["dpid"], "dpid_hex": first["dpid_hex"]}
            said = "; ".join(f"{end_words(e)} {w}" for e, w in
                             [(e, w) for e, (s, w) in zip(ends, states) if s in DOWN_STATES])
            listed_words = ("the controller still lists the link" if present else
                            f"the controller no longer lists the link ({entry['gone']} "
                            f"read{'s' if entry['gone'] != 1 else ''})")
            words = (f"link {link_words(ends)} ({conn}) is down: "
                     + (f"{said}; {listed_words}" if down else
                        f"{listed_words}, though both its ports report up"))
            evidence = [closed_loop.port_ref(conn, e["dpid"], e["port_no"]) for e, (s, _w)
                        in zip(ends, states) if s not in ("switch_gone",)]
            out["detections"].append(detect._detection(
                RULE, collected, ctl, sw, subject=("link", key), scope=scope(conn, key),
                words=words, port=first["port_no"],
                measurement={"what": "the link's state", "value": how, "unit": "",
                             "gone_reads": entry["gone"]},
                threshold={"what": "collections in a row a link may be unlisted, its ports up, "
                                   "before it is called down", "value": GONE_READS,
                           "unit": "reads"},
                confidence="high" if down else "lower",
                confidence_why=("the switch's own port description (its LINK_DOWN or "
                                "PORT_DOWN bit, or the port or switch gone)" if down else
                                "the controller's link discovery alone: both ports report up, "
                                "so this may be discovery's own timing"),
                evidence=evidence,
                link={"key": key, "how": how, "since": entry.get("down_since") or at,
                      "ends": [dict(e, state=s, words=w) for e, (s, w) in zip(ends, states)]},
                affected=affected(topo, conn, ends)))
            entry["down_since"] = entry.get("down_since") or at
        for key, entry in mine.items():
            if key in listed and all(_port_state(ctl, e)[0] == "up" for e in entry["ends"]):
                entry.pop("down_since", None)
        held[conn] = mine
    return out


def scope(connection: str, key: str) -> str:
    """What the rule judges for one link: its connection and key."""
    return f"link:{connection}:{key}"


# ───────────────────────────────────────────────────────────────────────────── the store

def _path(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), STORE_FILE)


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _epoch(text):
    try:
        import calendar

        return float(calendar.timegm(time.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return None


def _append(network: str, row: dict) -> dict:
    from modules.config import open_secure
    from modules.filestore import PathLock

    path = _path(network)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PathLock(path):
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return row


def _rows(network: str) -> dict:
    path = _path(network)
    if not os.path.exists(path):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"state": "ok", "error": "",
                    "rows": [json.loads(line) for line in fh if line.strip()]}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": f"{STORE_FILE}: {exc}"}


def open_rows(network: str) -> dict:
    """The link-failure cards still open, oldest first: ``{"state", "error", "rows"}``, each
    its ``down`` row with ``verify`` (its latest ``verified`` row, or None) and ``verifies``
    (how many)."""
    got = _rows(network)
    cards = {}
    for r in got["rows"]:
        rid = r.get("id")
        if r.get("kind") == "down":
            cards[rid] = dict(r, verify=None, verifies=0)
        elif rid not in cards:
            continue
        elif r.get("kind") == "verified":
            cards[rid] = dict(cards[rid], verify=r, verifies=cards[rid]["verifies"] + 1)
        elif r.get("kind") in CLOSED:
            cards.pop(rid, None)
    return dict(got, rows=list(cards.values()))


def open_down(network: str, d: dict, *, mode: str, why: str, now: float = None) -> dict:
    """A card for link-down detection *d*, in *mode* (``auto`` or ``hitl``, *why* the mode's
    words); one per detection key: a second for a key already open is that one."""
    for r in open_rows(network)["rows"]:
        if (r.get("detection") or {}).get("key") == d.get("key"):
            return r
    now = time.time() if now is None else now
    return _append(network, {"kind": "down", "id": f"link-{secrets.token_hex(5)}",
                             "at": _iso(now), "detection": d, "mode": mode, "why": why,
                             "action": ACTION})


def record_verify(network: str, rid: str, got: dict, *, actor: str, now: float = None) -> dict:
    """Keep verify's answer *got* on card *rid*, as *actor* (a verified person's, or Mercury's
    in AUTO)."""
    now = time.time() if now is None else now
    return _append(network, {"kind": "verified", "id": rid, "at": _iso(now), "actor": actor,
                             **{k: got.get(k) for k in ("outcome", "words", "pairs", "checked",
                                                       "total", "read_at", "final")}})


def close(network: str, rid: str, how: str, *, actor: str, why: str = "",
          now: float = None) -> dict:
    """Close card *rid*: ``restored`` (the link is listed and up again: the system's) or
    ``dismissed`` (a person's, with a reason)."""
    if how not in CLOSED:
        raise ValueError(f"a link-failure card is restored or dismissed, not {how!r}")
    if how == "dismissed" and not (why or "").strip():
        raise ValueError("a dismissal names its reason")
    if not any(r.get("id") == rid for r in open_rows(network)["rows"]):
        raise ValueError(f"no link-failure card {rid!r} is open on {network}")
    now = time.time() if now is None else now
    return _append(network, {"kind": how, "id": rid, "at": _iso(now), "actor": actor,
                             "why": (why or "").strip()})


# ───────────────────────────────────────────────────────────────────────────── the verify

def _name(h: dict) -> str:
    """A host as the trace is asked for it: its first IPv4, else its first global IPv6, else
    its MAC (`detect.host_address`)."""
    from modules.sdn import detect

    return detect.host_address(h) or str(h.get("mac") or "")


def verify(network: str, d: dict, *, cached=None, now: float = None) -> dict:
    """Whether the fabric rerouted around link-down detection *d*: ``{"outcome" (one of
    `OUTCOMES`), "words", "pairs", "checked", "total", "read_at"}``, each pair ``{"source",
    "destination", "state", "words", "dpids"}``. Reads the SDN reader's stored value once
    (*cached*, a test's), through `trace.fabric` and `trace.trace`; asks no controller and
    writes nothing."""
    from modules import reader_job
    from modules.readers import sdn_controllers as R
    from modules.sdn import trace

    now = time.time() if now is None else now
    got = cached if cached is not None else reader_job.read_cached_for(R.READER_NAME, network)
    link = d.get("link") or {}
    ends = [(e.get("dpid"), e.get("port_no")) for e in link.get("ends") or []]
    out = {"outcome": "pending", "words": "", "pairs": [], "checked": 0, "total": 0,
           "read_at": "", "final": False}
    fab = trace.fabric(network, cached=got, now=now)
    ctl = next((c for c in fab.get("controllers") or [] if c.get("name") == d.get("connection")),
               None)
    if fab.get("state") != "read" or ctl is None:
        out["words"] = ("not yet: the controller's stored read cannot be traced "
                        f"({fab.get('why') or 'its connection is not in it'})")
        return out
    out["read_at"] = ctl.get("read_at") or ""
    read = _epoch(out["read_at"])
    detected = _epoch(d.get("at"))
    if read is None or (detected is not None and read < detected):
        out["words"] = (f"not yet: the stored read ({out['read_at'] or 'no time'}) is from before "
                        f"the failure ({d.get('at')}); the next read is within 30 s")
        return out
    if any(e in ctl["links"] for e in ends):
        out["words"] = (f"not yet: the stored read ({out['read_at']}) still lists the link "
                        f"{link_words(link.get('ends') or [])}")
        return out
    from modules.sdn import detect

    # A host the controller lists with no address but a link-local one is not a trace's end
    # (Ryu keeps a host it learned once until it restarts, C2026): counted, never traced.
    listed = list(ctl["hosts"])
    hosts = sorted((h for h in listed if detect.host_address(h)),
                   key=lambda h: (_name(h), h.get("mac", "")))
    pairs = [(a, b) for a in hosts for b in hosts if a is not b and a.get("mac") != b.get("mac")]
    out["total"] = len(pairs)
    out["unaddressed"] = len(listed) - len(hosts)
    if not pairs:
        out.update(outcome="no_pairs", words=(
            f"nothing to verify: the controller lists {len(hosts)} host"
            f"{'s' if len(hosts) != 1 else ''} with an address, so no path between two hosts "
            "can be traced"))
        return out
    failed, unsure = [], []
    for a, b in pairs[:MAX_PAIRS]:
        src, dst = _name(a), _name(b)
        t = trace.trace(network, src, dst, cached=got, now=now)
        crosses = False
        if t.get("ok") and t.get("state") == "delivered":
            branch = next(x for x in t["branches"] if x["outcome"] == "delivered")
            crosses = any((h["dpid"], h["out_port"]) in ends for h in branch["hops"])
        state = ("error" if not t.get("ok") else
                 "crosses" if crosses else t.get("state"))
        words = t.get("words") if t.get("ok") else f"not traced: {t.get('error')}"
        if crosses:
            words = f"{words}: it still leaves by an end of the failed link"
        row = {"source": src, "destination": dst, "state": state, "words": words,
               "dpids": t.get("dpids") or []}
        out["pairs"].append(row)
        if state in ("not_delivered", "crosses"):
            failed.append(row)
        elif state in ("cannot_tell", "error"):
            unsure.append(row)
    out["checked"] = len(out["pairs"])
    more = (f" ({out['checked']} of {out['total']} pairs checked, the rest not traced)"
            if out["total"] > out["checked"] else "")
    if failed:
        f = failed[0]
        out.update(outcome="not_rerouted", words=(
            f"not rerouted: {len(failed)} of {out['checked']} host pairs not delivered; "
            f"{f['source']} to {f['destination']}: {f['words']}{more}"))
    elif unsure:
        u = unsure[0]
        out.update(outcome="cannot_tell", words=(
            f"cannot tell: {len(unsure)} of {out['checked']} host pairs could not be followed; "
            f"{u['source']} to {u['destination']}: {u['words']}{more}"))
    else:
        out.update(outcome="rerouted", final=True, words=(
            f"rerouted: all {out['checked']} host pairs delivered on paths that avoid "
            f"{link_words(link.get('ends') or [])}, from the controller's flow tables read at "
            f"{out['read_at']}{more}"))
    return out


# ───────────────────────────────────────────────────────────────────────────── the loop's step

def step(network: str, fired: list, resolved: list, *, now: float, line, decide=None,
         cached=None) -> dict:
    """The loop's link-failure step for one pass (`loop.run_pass`): a card for each link-down
    detection that fired (`open_down`, in the mode `modes.decide` answers for it); each open
    card whose detection resolved closed as ``restored``; each AUTO card verified (`verify`)
    until its outcome is final or `VERIFY_WINDOW_S` has passed, each new outcome recorded as
    Mercury's. *line* is the pass's ``line(step, words)``. ``{"opened", "verified",
    "restored"}``."""
    from modules.sdn import modes

    decide = decide or (lambda d: modes.decide(network, RISK, now, detection=d, action=ACTION))
    out = {"opened": [], "verified": [], "restored": []}
    for d in fired:
        decision = decide(d)
        mode = "auto" if decision.get("auto") else "hitl"
        row = open_down(network, d, mode=mode, why=decision.get("words") or "", now=now)
        out["opened"].append(row["id"])
        line("respond", f"{d.get('words')}; " + (
            f"AUTO: Mercury verifies the reroute ({row['id']}), nothing is sent" if mode == "auto"
            else f"HITL, awaiting a person ({row['id']}): {decision.get('words')}"),
            link=row["id"])
    gone = set(resolved)
    for row in open_rows(network)["rows"]:
        key = (row.get("detection") or {}).get("key")
        if key in gone:
            close(network, row["id"], "restored", actor="Mercury", now=now,
                  why="the controller lists the link again and both its ports report up")
            out["restored"].append(row["id"])
            ends = (row["detection"].get("link") or {}).get("ends") or []
            line("respond", f"link {link_words(ends)} restored: its card {row['id']} is closed")
            continue
        if row.get("mode") != "auto" or (row.get("verify") or {}).get("final"):
            continue
        got = verify(network, row["detection"], cached=cached, now=now)
        opened = _epoch(row.get("at")) or now
        if got["outcome"] not in FINAL and now - opened >= VERIFY_WINDOW_S:
            got = dict(got, final=True, words=(
                f"{got['words']}; not rerouted within {VERIFY_WINDOW_S} s of the failure: a "
                "person decides (nothing was sent, so nothing is rolled back)"))
        last = row.get("verify") or {}
        if (last.get("outcome"), last.get("final")) != (got["outcome"], got["final"]):
            record_verify(network, row["id"], got, actor="Mercury (AUTO)", now=now)
            out["verified"].append({"id": row["id"], "outcome": got["outcome"]})
            line("respond", f"AUTO verify of {row['id']}: {got['words']}", link=row["id"])
    return out


def card(row: dict) -> dict:
    """One open card as SDN › Responses draws it (board F's link-failure card)."""
    d = row.get("detection") or {}
    link = d.get("link") or {}
    v = row.get("verify") or {}
    tone = {"rerouted": "ok", "not_rerouted": "danger", "cannot_tell": "warn",
            "pending": "muted", "no_pairs": "warn"}.get(v.get("outcome"), "danger")
    state = ({"rerouted": "rerouted, verified", "not_rerouted": "not rerouted",
              "cannot_tell": "cannot tell", "pending": "verifying",
              "no_pairs": "nothing to verify"}.get(v.get("outcome"))
             or ("verifying" if row.get("mode") == "auto" else "awaiting a person"))
    shown = None
    if v:
        shown = {"words": v.get("words"), "actor": v.get("actor"), "at": v.get("at"),
                 "checked": v.get("checked") or 0, "total": v.get("total") or 0,
                 "pairs": [{k: p.get(k) for k in ("source", "destination", "state", "words")}
                           for p in v.get("pairs") or []]}
    return {"id": row.get("id"), "at": row.get("at"), "mode": row.get("mode"),
            "why": row.get("why"), "title": f"Link down: {link_words(link.get('ends') or [])}",
            "words": d.get("words"), "confidence": d.get("confidence"),
            "affected": d.get("affected") or [], "verify": shown,
            "verifies": row.get("verifies", 0), "state": state, "tone": tone}
