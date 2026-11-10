"""False-positive runs on normal traffic (Lab 9 B3: "test for false positives with repeated
normal-traffic runs"; the log B5 needs): the detection rules run over repeated collections of
traffic a person declares normal, and every detection that fires is a false positive, kept
with its rule, its evidence and what Mercury does with it. Run by
``scripts/nmas-sdn-false-positives``; no AI call, nothing written to a switch or to Mercury's
detection state.

**The collections** are either recorded (a series file, the collector's JSONL: a head line with
the network's thresholds and flow intent, then one line a pass with
`closed_loop.collect_threat_data`'s answer and the SDN reader's stored topology; the operator's
captures under tests/fixtures/sdn/recorded/ are of this shape), or read now from a network
(`read_live`, read-only: the loop's own collection, with link status, `--passes` times,
`--interval` apart). Each run is one series; several runs are several series.

**The rules** are the loop's, replayed pass by pass as `detect.observe` carries their state
(`replay`): scan, flood (with its baseline and hold), unauthorised flow against the flow intent
the run recorded, the replies marked, and link down over the links the run held; with no store
read or written.

**What is done with each** (`handled`), in the loop's order: High packet rate is watched and
nothing proposed; a link down is its card (the reroute verified in AUTO); a detection code
decides is benign (C2305, `benign.decide`) is no threat with no AI call and nothing for AUTO;
any other is classified where the background feature is on, else the rule's default is
proposed for a person, and in AUTO an action runs only where the network is marked lab.

**The log** (`write`): ``false_positives.csv`` (one row per false positive: the run, pass,
time, rule, switch, port, source, words, evidence ids, the measurement against its threshold,
what was done) and ``summary.json`` (runs, passes, detections fired, false positives by rule
and per pass).

**The network's record** (`keep`, C2946): each run's summary and its false positives are also
kept in the network's own record of evaluation runs (modules/sdn/evaluations.py), under the
run's id, so History › Export's false-positive and failure log lists them; the ``--out`` files
stay as they are.
"""

import csv
import json
import os
import time
import uuid

#: The columns of the CSV log, in order.
COLUMNS = ("run", "pass", "at", "rule", "switch", "port", "source", "words", "evidence",
           "measured", "threshold", "done")


def load(path: str) -> dict:
    """``{"label", "head", "passes", "unparsed"}`` from a series file; a line that does not
    parse is counted, never guessed."""
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
    label = (head or {}).get("label") or os.path.splitext(os.path.basename(path))[0]
    return {"label": label, "head": head, "passes": passes, "unparsed": bad}


def read_live(network: str, passes: int, interval: float, *, collect=None, sleep=time.sleep,
              topology=None) -> dict:
    """*passes* collections of *network* read now, *interval* seconds apart, as a series:
    read-only (the loop's collection with link status); *collect* and *topology* replace the
    reads (tests). The head carries the network's thresholds and flow intent."""
    from modules.sdn import closed_loop, detect, flow_intent, topology as T

    th = detect.thresholds(network)
    head = {"kind": "head", "label": f"live-{network}", "network": network,
            "thresholds": th, "intent": flow_intent.intent(network)}
    out = []
    for n in range(1, int(passes) + 1):
        c = collect() if collect else closed_loop.collect_threat_data(network, links=True)
        out.append({"kind": "pass", "n": n, "collected": c,
                    "topology": topology() if topology else T.stored(network)})
        if n < passes:
            sleep(interval)
    return {"label": head["label"], "head": head, "passes": out, "unparsed": 0}


def _epoch(text):
    import calendar
    try:
        return float(calendar.timegm(time.strptime(str(text)[:19], "%Y-%m-%dT%H:%M:%S")))
    except ValueError:
        return None


def replay(series: dict) -> list:
    """Each pass's ``{"n", "at", "detections", "collected"}``: the loop's rules over the series
    in order, their state carried as `detect.observe` carries it (see the module's
    docstring)."""
    from modules.sdn import detect, link_failure
    from modules.sdn.closed_loop import rejudge

    head = series.get("head") or {}
    values = dict(detect.THRESHOLDS, **((head.get("thresholds") or {}).get("values") or {}))
    intent = head.get("intent")
    seen, baseline, over, links, out = {}, {}, {}, {}, []
    for p in series.get("passes") or []:
        c, topo = rejudge(p["collected"]), p.get("topology")
        scanned = detect.scan(c, values, seen, topo=topo)
        flooded = detect.flood(c, baseline, values, over, topo=topo)
        unauth = (detect.unauthorised(c, intent, now=_epoch(c.get("collected_at")), topo=topo)
                  if intent is not None else {"detections": []})
        linked = link_failure.rule(c, links, topo=topo)
        out.append({"n": p.get("n"), "at": c.get("collected_at"), "collected": c,
                    "detections": detect.mark_replies(
                        scanned["detections"] + flooded["detections"], c)
                    + unauth["detections"] + linked["detections"]})
        seen, over, links = scanned["seen"], flooded["over"], linked["held"]
        baseline = detect.update_baseline(baseline, c, set(over))
    return out


def handled(d: dict, collected: dict) -> str:
    """What the loop does with detection *d* (see the module's docstring), in words."""
    from modules.sdn import benign, closed_loop, detect

    rule = d.get("rule")
    if rule in detect.WATCH_ONLY:
        return (f"watched as High packet rate (basis {d.get('basis') or 'rate'}): nothing "
                "proposed, no AI call")
    if rule in detect.LINK_RULES:
        return ("a link-failure card: HITL awaits a person, AUTO verifies the reroute; nothing "
                "is sent")
    section = detect.section(d, collected, detect._switch_of(collected, d))
    got = benign.decide(section)
    if got["decided"]:
        return f"{got['words']}; nothing proposed for AUTO, a person's card"
    default = closed_loop.DEFAULT_ACTION.get(rule, "")
    return (f"classified where sdn_classify's background feature is on (else the rule's "
            f"default, {default}, proposed for a person); HITL waits for a person, AUTO acts "
            "only on a network marked lab")


def judge(series_list: list) -> dict:
    """Every false positive over *series_list* (each `load`'s or `read_live`'s): ``{"runs",
    "passes", "fired", "false_positives": [row], "by_rule", "per_pass"}``, a row per detection
    that fired (new in its pass), with `COLUMNS`."""
    rows, passes, fired = [], 0, 0
    for series in series_list:
        before = set()
        for r in replay(series):
            passes += 1
            keys = {d["key"] for d in r["detections"]}
            for d in r["detections"]:
                if d["key"] in before:
                    continue
                fired += 1
                m, t = d.get("measurement") or {}, d.get("threshold") or {}
                rows.append({
                    "run": series["label"], "pass": r["n"], "at": r["at"], "rule": d["rule"],
                    "switch": d.get("dpid_hex"), "port": d.get("port"),
                    "source": d.get("source") or "", "words": d.get("words"),
                    "evidence": " ".join(d.get("evidence") or []),
                    "measured": f"{m.get('value')} {m.get('unit', '')}".strip(),
                    "threshold": f"{t.get('value')} {t.get('unit', '')}".strip(),
                    "done": handled(d, r["collected"])})
            before = keys
    by_rule = {}
    for row in rows:
        by_rule[row["rule"]] = by_rule.get(row["rule"], 0) + 1
    return {"runs": [s["label"] for s in series_list], "passes": passes, "fired": fired,
            "false_positives": rows, "by_rule": by_rule,
            "per_pass": round(len(rows) / passes, 4) if passes else 0.0}


def keep(network: str, series: dict, *, by: str, now: float = None) -> dict:
    """Keep one run (*series*, `load`'s or `read_live`'s) in *network*'s record of evaluation
    runs (`evaluations.keep`): a ``run`` row with its summary (`judge` over the run alone) and
    one ``false_positive`` row per false positive, each with `COLUMNS` under ``detection`` and
    the run's id. ``{"run_id", "false_positives"}``."""
    from modules.sdn import evaluations

    now = time.time() if now is None else now
    got = judge([series])
    run_id = "fp-" + uuid.uuid4().hex[:16]
    base = {"script": evaluations.FALSE_POSITIVES, "run_id": run_id, "run": series["label"],
            "network": network, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "by": by}
    rows = [dict(base, kind="run", passes=got["passes"], fired=got["fired"],
                 false_positives=len(got["false_positives"]), by_rule=got["by_rule"],
                 per_pass=got["per_pass"], unparsed=series.get("unparsed") or 0)]
    rows += [dict(base, kind="false_positive", detection=row) for row in got["false_positives"]]
    evaluations.keep(network, rows)
    return {"run_id": run_id, "false_positives": len(got["false_positives"])}


def write(result: dict, out_dir: str) -> dict:
    """The log in *out_dir* (created owner-only): ``false_positives.csv`` and
    ``summary.json``. ``{"csv", "summary"}``, their paths."""
    from modules.config import open_secure

    os.makedirs(out_dir, mode=0o700, exist_ok=True)
    path_csv = os.path.join(out_dir, "false_positives.csv")
    # A plain csv.writer, header first: the program's one DictWriter is the inventory's
    # (`modules/device.py`, tests/test_store_integrity_c158_c160.py), and this log is not it.
    with open_secure(path_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        for row in result["false_positives"]:
            w.writerow(["" if row.get(k) is None else row.get(k) for k in COLUMNS])
    path_json = os.path.join(out_dir, "summary.json")
    with open_secure(path_json, "w", encoding="utf-8") as fh:
        json.dump({k: v for k, v in result.items() if k != "false_positives"}
                  | {"false_positives": len(result["false_positives"])}, fh, indent=1,
                  sort_keys=True)
    return {"csv": path_csv, "summary": path_json}
