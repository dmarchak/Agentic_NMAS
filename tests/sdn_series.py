"""A recorded SDN case from a capture series (C2237, C2238; the operator's non-blind captures of
2026-11-01, `blind-runs/sessions.md`, "Recorded-case captures"): the collector's JSONL
(`lab8_series.py`: a head line with the network's thresholds and flow intent, then one line a
pass with `closed_loop.collect_threat_data`'s answer and the SDN reader's stored topology),
checked for what a case needs, and replayed through the detection rules pass by pass as
`detect.observe` runs them, with no store read or written.

`check` says what a series lacks, naming each requirement, so a capture that cannot hold a
case is refused rather than measured: at least `MIN_PASSES` passes, each read with its
switches; at least `BEFORE` passes before the traffic began, `DURING` inside it and `AFTER`
once it ended (*t0* and *t1*, the operator's `date -u` around the traffic).

`replay` answers, for each pass, the detections the rules made (`scan`, `flood`, then
`mark_replies`, as `observe`), the flood rule's pending ports and the ports with no baseline
yet, carrying the scan rule's sightings, the flood rule's hold and the baseline from pass to
pass exactly as `observe` keeps them (`seen`, `over`, `update_baseline` without the ports over
their threshold).
"""
import json
import time

#: What a case needs of a series (sessions.md: 24 passes asked, at least 18; 6 before the
#: traffic, 4 inside it, 3 after).
MIN_PASSES = 18
BEFORE, DURING, AFTER = 6, 4, 3
#: The switches the lab's fabric has (lab/sdn/lab8_topology.py: s1 and s2).
SWITCHES = 2


def _epoch(text: str) -> float:
    import calendar
    return float(calendar.timegm(time.strptime(str(text)[:19], "%Y-%m-%dT%H:%M:%S")))


def load(path: str) -> dict:
    """``{"head", "passes"}`` from a series file; a line that does not parse is left out and
    counted (``unparsed``), never guessed."""
    head, passes, bad = None, [], 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if row.get("kind") == "head":
                head = row
            elif row.get("kind") == "pass":
                passes.append(row)
    return {"head": head, "passes": passes, "unparsed": bad}


def switches_of(collected: dict) -> int:
    return sum(len(c.get("switches") or []) for c in collected.get("controllers") or [])


def partial(series: dict) -> list:
    """The passes not read whole, each judged as the collector judges now
    (`closed_loop.rejudge`, C2277: a read that answered nothing is not read): ``[n]``. A
    capture keeps them (the operator: change nothing to make a capture look right); they are a
    fact of the case, never counted toward its windows."""
    from modules.sdn.closed_loop import rejudge

    return [p.get("n") for p in series.get("passes") or []
            if rejudge(p.get("collected") or {}).get("state") != "ok"
            or switches_of(p.get("collected") or {}) != SWITCHES]


def check(series: dict, t0: str, t1: str) -> list:
    """What *series* lacks to be a recorded case, one line per requirement unmet; ``[]`` when
    it holds a case. *t0* and *t1*: when the traffic began and ended (UTC). Only passes read
    whole count toward the windows (`partial`)."""
    out = []
    head, passes = series.get("head"), series.get("passes") or []
    if not head:
        out.append("no head line: the thresholds and flow intent the rules ran with are unknown")
    elif not (head.get("thresholds") or {}).get("ok"):
        out.append("the head's thresholds were not read, so no rule can be replayed")
    if series.get("unparsed"):
        out.append(f"{series['unparsed']} line(s) did not parse")
    bad = set(partial(series))
    whole = [p for p in passes if p.get("n") not in bad]
    if len(whole) < MIN_PASSES:
        out.append(f"{len(whole)} passes read whole ({len(passes)} in all), fewer than "
                   f"{MIN_PASSES}")
    start, end = _epoch(t0), _epoch(t1)
    at = [_epoch((p.get("collected") or {}).get("collected_at") or "1970-01-01T00:00:00Z")
          for p in whole]
    for name, n, want in (("before the traffic", sum(1 for t in at if t < start), BEFORE),
                          ("inside it", sum(1 for t in at if start <= t <= end), DURING),
                          ("after it ended", sum(1 for t in at if t > end), AFTER)):
        if n < want:
            out.append(f"{n} pass(es) {name}, fewer than {want}")
    return out


def replay(series: dict, values: dict = None, intent: dict = None) -> list:
    """Each pass's ``{"n", "at", "detections", "pending", "no_baseline"}``: the three rules over
    the series in order (the unauthorised-flow rule against *intent*, by default the flow intent
    the head recorded), their state carried as `detect.observe` carries it."""
    from modules.sdn import detect
    from modules.sdn.closed_loop import rejudge

    values = values or series["head"]["thresholds"]["values"]
    intent = series["head"].get("intent") if intent is None else intent
    seen, baseline, over, out = {}, {}, {}, []
    for p in series["passes"]:
        # Each pass as the collector reads it now (C2277), so a read that answered nothing is
        # not read, as `observe` would be handed it.
        c, topo = rejudge(p["collected"]), p.get("topology")
        scanned = detect.scan(c, values, seen, topo=topo)
        flooded = detect.flood(c, baseline, values, over, topo=topo)
        unauth = (detect.unauthorised(c, intent, now=_epoch(c.get("collected_at")), topo=topo)
                  if intent is not None else {"detections": []})
        out.append({"n": p.get("n"), "at": c.get("collected_at"),
                    "detections": detect.mark_replies(
                        scanned["detections"] + flooded["detections"], c)
                    + unauth["detections"],
                    "pending": flooded["pending"], "no_baseline": flooded["no_baseline"]})
        seen, over = scanned["seen"], flooded["over"]
        baseline = detect.update_baseline(baseline, c, set(over))
    return out
