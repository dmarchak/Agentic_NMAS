"""Lab 9 B4's evaluation: the analyst without tools (B1, the baseline) against the analyst with
the trace tool (the technique), on fixed snapshots, each with its planted issues, N runs each
(docs/HEAL_TO_INTENT.md 19.13; the TA's approval of 2026-11-10: "compared on findings, misses,
false positives and API cost"). `scripts/nmas-sdn-b4-eval` runs it, a person's explicit action
behind ``--yes-spend``; never CI. This module scores and reports, and asks nothing itself: the
two arms are handed in (`run`'s *arms*), so no code path here reaches the AI gateway.

**The cases are 19.13's, unedited** (`SETS`): the sdn_classify case files' Lab 8 detections
(Ryu 4.34 over Open vSwitch, 2026-10-27), each case's evidence pack section as Mercury kept it,
and its expectation as its file holds it now. Each becomes a fixed snapshot (`case_snapshot`)
through the analyst's own `build_snapshot`, with these edits, the same for every case:

1. **The switch's facts are the pack's pieces**: each ``flow`` and ``displaced_flow`` piece a
   flow (no actions: a drop flow), its id kept; each ``port`` piece the port's rates (its
   ``rate:`` row); the ``coverage`` piece the flow granularity. The pack holds part of the
   table, so the switch is said to hold part of it (``partial``), and the trace says so.
2. **The detection piece is not sent**: the analyst reads state, never Mercury's verdict.
3. **A cookie written as hex text is its integer** (the format, not the value).
4. **The hosts are Lab 8's** (lab/sdn/lab8_topology.py and tests/fixtures/sdn/lab8/README.md:
   host n at 192.0.2.<n> and 2001:db8:8::<n>, MAC 00:00:00:00:00:0<n>; hosts 1 and 2 on the
   first switch's ports 1 and 2, hosts 3 and 4 on the second's, the switches joined by port 3,
   datapath ids 1 and 2), which the run's collection did not
   read: each host on the case's switch at its own port, each host beyond it at the case's port
   3, where its packets enter the switch the case holds.
5. No port description and no link was captured: none is invented.

**A case's planted issue** (`case_issues`): a threat case's is its name, found by any of its
``cites_any`` ids (a ``port:`` id also by its ``rate:`` id, where the snapshot keeps a port's
counters); a benign case has none. A case whose alternatives disagree is ``either``, reported
and kept out of the pass rule.

**The lab hardware's snapshots** (`load_hardware`, the role ``hardware``; C2965): a copy of a
network's analyst folder (``sdn_analyst/``, `analyst.snapshot_in` and `analyst.planted_in`; read,
never written), each snapshot kept there by SDN › Flows' Collect now on the lab's switches a
case as it was sealed, unedited. A snapshot whose seal fails, that another network collected or
whose collection time cannot be read is skipped, each said with why, never dropped unsaid. Its
planted issues are the sheet's standing at its collection (`standing`: planted at or before it;
an issue a person removed is a correction, as in B1 (C2913), and stands for no snapshot,
whenever it was removed), each found by B1's own rule (`analyst.marks`: a kept finding citing
an id the issue names), and every one must be found for the run to be correct, at any
severity (the sheet names none). A snapshot the person names clean (``--clean``: every planted
issue restored, the sheet left as it is, or collected before any was planted) is a benign
case, with the benign cases' own severities (``none``, ``low``): a finding of medium or above
answers it as a threat, as for 19.13's. Its name says why it is clean (`clean_name`, C3029):
every planted issue restored, collected before any issue was planted, or no issue on the
sheet. One with issues still standing on the sheet is said so in the report and its JSON
(``clean_with_issues``), and scored benign. A snapshot neither clean nor holding a planted
issue is skipped, said. The role is reported beside the others; the pass
rule stays 19.13's, on the blind role alone.

**The Lab 9 sitting's cases** (the role ``sitting``; tests/fixtures/ai_cases/sdn_analyse/
lab9_sitting.json): what the analyst got wrong on the lab's hardware on 2026-11-10, each
modelled on the test fabric (the analyst tests' recorded controller, flows planted; nothing of
the lab's), never blind, reported as their own role. A case here holds a whole ``collection``
(`closed_loop.collect_threat_data`'s answer with its links and hosts), and its snapshot is the
analyst's own of it (`case_snapshot`), with no edit. Two kinds: a planted flow whose output
port leads away from its destination (a threat case, found by its ``cites_any``), and a pair of
flows whose matches are disjoint (a drop of DHCP replies beside a forward of DHCP requests: a
benign case). A benign case may name ``disjoint`` groups in its expectation: a kept finding
above info that cites every id of a group sets those flows against each other, and answers the
case as a threat (`false_conflicts`), whatever its severity.

**The measures** (`score_run`, `summary`, 19.13's), per technique, the difference and its
uncertainty: correct (a threat case's issue found by a kept finding at a severity its
expectation names; a benign case answered with no finding above its expected severities), each
case reliable when every run is correct; McNemar's exact test on the cases that flip; a 95%
bootstrap interval for the difference in the share reliable; the findings, the misses, the
false positives by `sdn_analyst_tools.judge`'s rule, the benign runs answered as a threat; the cost
from the record of AI calls (the gateway's recorded cost of each call the run made); the time to
an answer. **The pass rule, frozen (19.13):** the technique improves results only if more blind
cases are reliable with it, and no more benign runs are answered as a threat.

**Where it was wrong is kept** (`wrong_row`, C2943): each run that missed its planted issue,
kept a false-positive finding or answered a benign case as a threat is also kept in the
network's record of evaluation runs (modules/sdn/evaluations.py), so History › Export's
false-positive and failure log lists it; the report files are unchanged.
"""

import ipaddress
import json
import math
import os
import random
import statistics
import time

#: 19.13's case files, by role, in its table's order. blind_normal_cases.json (N1, N2) holds a
#: collection, not a pack's section, and is not converted (said in every report).
SETS = (("recorded", "tests/fixtures/ai_cases/sdn_classify/recorded.json"),
        ("recorded", "tests/fixtures/ai_cases/sdn_classify/recorded_from_blind.json"),
        ("recorded", "tests/fixtures/ai_cases/sdn_classify/recorded_walk.json"),
        ("held_out", "tests/fixtures/ai_cases/sdn_classify/held_out.json"),
        ("blind", "tests/fixtures/blind_sets/sdn_classify/blind_cases.json"),
        # Not 19.13's: the Lab 9 sitting's cases (the module's docstring), each a collection.
        ("sitting", "tests/fixtures/ai_cases/sdn_analyse/lab9_sitting.json"))
NOT_CONVERTED = {"tests/fixtures/blind_sets/sdn_classify/blind_normal_cases.json":
                 "its two cases hold a collection, not an evidence pack's section"}
#: Lab 8's hosts (edit 4): the host's number, its switch's datapath id, its port.
LAB8_HOSTS = ((1, 1, 1), (2, 1, 2), (3, 2, 1), (4, 2, 2))
LAB8_LINK_PORT = 3
SEVERITY_RANK = {"none": -1, "info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
DEFAULT_RUNS = 10
BOOTSTRAP = 2000
SEED = 1913
TECHNIQUES = ("baseline", "tools")
#: 19.13's roles; the Lab 9 sitting's cases, read from a case file as they are; and the lab
#: hardware's snapshots (C2965).
ROLES_1913 = ("recorded", "held_out", "blind")
SITTING = "sitting"
FIXTURE_ROLES = ROLES_1913 + (SITTING,)
HARDWARE = "hardware"
ROLES = FIXTURE_ROLES + (HARDWARE,)
#: A clean hardware snapshot's expected severities: 19.13's benign cases' own.
BENIGN_SEVERITIES = ("none", "low")
WORDS = {"baseline": "without tools (B1, sdn_analyse)",
         "tools": "with the trace tool (B4, sdn_analyse_tools)"}


# ───────────────────────────────────────────────────────────────────────────── the cases

def load_cases(root: str, roles=None, keys=None) -> list:
    """Every case of `SETS` (those of *roles*, or of *keys*), each ``dict(case, role, file)``."""
    out = []
    for role, rel in SETS:
        if roles and role not in roles:
            continue
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            data = json.load(fh)
        for c in data.get("cases") or []:
            if keys and c.get("key") not in keys:
                continue
            out.append(dict(c, role=role, file=rel))
    return out


def standing(sheet: dict, at: str) -> list:
    """The planted issues on *sheet* (`analyst.planted_in`'s) standing at *at*, a snapshot's
    collection time: each on the sheet now and planted at or before it (not
    `analyst.planted_after` it), oldest first. An issue a person removed is a correction (B1's
    meaning, C2913: planted by mistake) and stands for no snapshot, whenever it was removed;
    a restored network is said by ``--clean``, never by removing its issues."""
    from modules.sdn import analyst as AN

    when = {"ok": True, "at": at}
    out = []
    for issue in sheet.get("issues") or []:         # the sheet's *removed* never read
        if AN.planted_after(issue, when):
            continue
        out.append(issue)
    return sorted(out, key=lambda i: (str(i.get("at") or ""), str(i.get("id") or "")))


#: What a clean hardware case is called, by why it is clean (C3029): an issue stood on the
#: sheet at its collection and ``--clean`` says the network was restored; every issue on the
#: sheet was planted after it was collected; or the sheet holds no issue at all.
CLEAN_NAMES = {"restored": "clean: every planted issue restored",
               "before": "clean: collected before any issue was planted",
               "none": "clean: no issue is on the sheet"}


def clean_name(sheet: dict, issues: list) -> str:
    """The name of a snapshot ``--clean`` names (`CLEAN_NAMES`): *issues* are those standing on
    *sheet* at its collection (`standing`). With one standing, the network was restored (the
    operator's word, by naming it clean); with none standing and issues on the sheet, each was
    planted after the collection, so nothing was there to restore; a sheet holding no issue
    says so. An issue a person removed is on no sheet (`standing`)."""
    if issues:
        return CLEAN_NAMES["restored"]
    return CLEAN_NAMES["before" if sheet.get("issues") else "none"]


def load_hardware(folder: str, network: str, clean=(), keys=None) -> dict:
    """The lab hardware's snapshots in *folder* (a copy of *network*'s ``sdn_analyst/``), each
    a case of the role `HARDWARE`: ``{"cases", "skipped": [{"id", "why"}], "error"}``. Read
    only. A snapshot whose seal fails (`analyst.snapshot_in`), whose collection time cannot be
    read, or that is neither named in *clean* nor holds a standing planted issue (`standing`)
    is skipped, said; *keys* (snapshot ids) narrows the cases. *error* when the folder holds no
    ``snapshots/``, its sheet cannot be read, or *clean* names a snapshot it does not hold."""
    from modules.sdn import analyst as AN

    out = {"cases": [], "skipped": [], "error": ""}
    folder = os.path.abspath(folder)
    kept = os.path.join(folder, "snapshots")
    if not os.path.isdir(kept):
        out["error"] = (f"{folder} holds no snapshots/ folder: give a copy of a network's "
                        "sdn_analyst/ folder")
        return out
    sheet = AN.planted_in(folder)
    if sheet["state"] == "unreadable":
        out["error"] = f"the planted issues in {folder} cannot be read ({sheet['error']})"
        return out
    clean = set(clean or ())
    seen = set()
    for name in sorted(os.listdir(kept)):
        sid = name[:-len(".json")] if name.endswith(".json") else name
        seen.add(sid)
        if keys and sid not in keys:
            continue
        got = AN.snapshot_in(folder, network, sid) if name.endswith(".json") else {
            "ok": False, "error": f"{name} is not a snapshot's file (<id>.json)"}
        if not got["ok"]:
            out["skipped"].append({"id": sid, "why": got["error"]})
            continue
        snap = got["snapshot"]
        at = snap.get("collected_at") or ""
        if AN._epoch(at) is None:                                    # noqa: SLF001
            out["skipped"].append({"id": sid, "why": f"its collection time {at!r} cannot be "
                                   "read, so its planted issues cannot be told"})
            continue
        issues = standing(sheet, at)
        if sid not in clean and not issues:
            out["skipped"].append({"id": sid, "why": f"no planted issue stood on the sheet at "
                                   f"its collection ({at}) and --clean does not name it"})
            continue
        benign = sid in clean
        out["cases"].append({
            "key": sid, "role": HARDWARE, "file": folder, "snapshot": snap,
            "collected_at": at, "clean": benign,
            "issues": [] if benign else [dict(i) for i in issues],
            "sheet_issues": len(issues),
            "name": (clean_name(sheet, issues) if benign
                     else "; ".join(str(i.get("name")) for i in issues)),
            "expect": ({"threat_detected": False, "severity": list(BENIGN_SEVERITIES)} if benign
                       else {"threat_detected": True, "severity": list(AN.SEVERITIES)})})
    unknown = sorted(clean - seen)
    if unknown:
        out["error"] = (f"--clean names {', '.join(unknown)}, which {folder}/snapshots/ does not "
                        "hold")
    out["cases"].sort(key=lambda c: (AN._epoch(c["collected_at"]), c["key"]))  # noqa: SLF001
    return out


def _alternatives(expect: dict) -> list:
    return list(expect.get("any_of") or [expect])


def kind_of(case: dict) -> str:
    """``threat``, ``benign`` or ``either`` (its alternatives disagree)."""
    seen = {bool(a.get("threat_detected")) for a in _alternatives(case.get("expect") or {})}
    return "threat" if seen == {True} else "benign" if seen == {False} else "either"


def _dpid_of(ident: str) -> str:
    parts = str(ident).split(":")
    return parts[2] if len(parts) > 2 else ""


def _cookie(value) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(str(value or 0), 0)
    except ValueError:
        return 0


def _hosts(conn: str, dpid: int) -> list:
    from modules.sdn.drivers.base import dpid_hex

    out = []
    for n, sw, port in LAB8_HOSTS:
        here = sw == dpid
        out.append({"mac": f"00:00:00:00:00:{n:02x}", "ipv4": [f"192.0.2.{n}"],
                    "ipv6": [str(ipaddress.ip_address(f"2001:db8:8::{n}"))],
                    "dpid": dpid, "dpid_hex": dpid_hex(dpid),
                    "port_no": port if here else LAB8_LINK_PORT,
                    "port_name": "" if here else
                    f"toward {dpid_hex(sw)}, whose table this case does not hold"})
    del conn
    return out


def case_snapshot(case: dict, network: str) -> dict:
    """The case's fixed snapshot (the module's edits 1 to 5), built and sealed by the analyst's
    own `build_snapshot`. A hardware case's is its kept snapshot, as it was sealed. A case that
    holds a whole ``collection`` (the Lab 9 sitting's) is that collection's snapshot, built as
    Collect now builds one, its links and hosts as collected and nothing edited."""
    from modules.sdn import analyst as AN

    if case.get("role") == HARDWARE:
        return case["snapshot"]
    if case.get("collection"):
        return AN.build_snapshot(network, case["collection"], by=f"b4-eval:{case.get('key')}")
    section = case.get("section") or {}
    pieces = section.get("pieces") or []
    det = next((p for p in pieces if p.get("kind") == "detection"), {})
    conn = det.get("connection") or next(
        (str(p["id"]).split(":")[1] for p in pieces if str(p.get("id") or "").count(":") > 2),
        "lab")
    switches = {}

    def switch(dhex):
        return switches.setdefault(dhex, {
            "dpid_hex": dhex, "state": "ok", "error": "", "flows": [], "ports": [],
            "coverage": {"granularity": "not read"},
            "partial": "the case's recorded pieces, not the whole table"})

    for p in pieces:
        kind, ident = p.get("kind"), str(p.get("id") or "")
        if kind in ("flow", "displaced_flow") and ident.startswith("flow:"):
            switch(_dpid_of(ident))["flows"].append({
                "id": ident, "table_id": p.get("table_id", 0), "priority": p.get("priority", 0),
                "cookie": _cookie(p.get("cookie")), "match": dict(p.get("match") or {}),
                "actions": list(p.get("actions") or []),
                "packet_count": p.get("packet_count") or 0,
                "byte_count": p.get("byte_count") or 0,
                "duration_sec": p.get("duration_sec") or 0,
                "idle_timeout": p.get("idle_timeout") or 0,
                "hard_timeout": p.get("hard_timeout") or 0})
        elif kind == "port" and ident.startswith("port:"):
            row = {k: v for k, v in p.items() if k not in ("id", "kind", "sample")}
            sw = switch(_dpid_of(ident))
            sw["ports"].append(row)
            sw["sample"] = {"elapsed_s": (p.get("sample") or {}).get("elapsed_s")}
        elif kind == "coverage" and p.get("dpid"):
            switch(p["dpid"])["coverage"] = {"granularity": p.get("granularity") or "not read"}
    if det.get("dpid_hex"):
        switch(det["dpid_hex"])
    elif isinstance(det.get("dpid"), int) and not isinstance(det.get("dpid"), bool):
        switch(f"{det['dpid']:016x}")
    elif isinstance(det.get("dpid"), str) and len(det["dpid"]) == 16:
        switch(det["dpid"])
    held = sorted(switches)
    hosts = _hosts(conn, int(held[0], 16)) if len(held) == 1 else []
    interval = next(((p.get("sample") or {}).get("interval_s") for p in pieces
                     if p.get("kind") == "port"), None) or 2.0
    collected = {"collected_at": section.get("as_of") or "", "interval_s": interval,
                 "state": "ok", "error": "", "calls": 0,
                 "controllers": [{"connection": conn, "state": "ok", "error": "",
                                  "switches": [switches[d] for d in held], "links": [],
                                  "hosts": hosts}]}
    return AN.build_snapshot(network, collected, by=f"b4-eval:{case.get('key')}")


def case_issues(case: dict) -> list:
    """The case's planted issue (a threat case's), found by its expectation's ``cites_any``; a
    hardware case's, the sheet's issues standing at its collection (`load_hardware`)."""
    if case.get("role") == HARDWARE:
        return [] if kind_of(case) != "threat" else list(case.get("issues") or [])
    if kind_of(case) != "threat":
        return []
    ids = []
    for alt in _alternatives(case.get("expect") or {}):
        for i in alt.get("cites_any") or []:
            ids.append(i)
            if str(i).startswith("port:"):
                ids.append("rate:" + str(i)[len("port:"):])
    return [{"id": f"pl-case-{case.get('key')}", "name": case.get("name") or case.get("key"),
             "evidence": sorted(set(ids)), "why": "", "by": "b4-eval", "at": ""}]


def expected_severities(case: dict) -> set:
    return {s for alt in _alternatives(case.get("expect") or {})
            for s in alt.get("severity") or []}


# ───────────────────────────────────────────────────────────────────────────── one run

def score_run(case: dict, snap: dict, result: dict) -> dict:
    """One run of one technique on one case: ``{"ok", "error", "findings", "found",
    "found_at_severity", "missed", "missed_issues", "false_positives", "real", "notes",
    "threat_answered", "correct", "judged"}``. *found* when every planted issue is found by
    B1's own rule (`analyst.marks`); *missed_issues* names those that were not."""
    from modules.ai import sdn_analyst_tools as AT
    from modules.sdn import analyst as AN

    kind = kind_of(case)
    issues = case_issues(case)
    findings = (result or {}).get("findings") or [] if (result or {}).get("ok") else []
    abnormal = AT.abnormal_ids(snap)
    judged = [AT.judge(f, issues, abnormal) for f in findings]
    allowed = expected_severities(case)
    top = max([SEVERITY_RANK[s] for s in allowed if s in SEVERITY_RANK] or [-1])
    hits = [f for f in findings if any(AN._matches(p, e)                     # noqa: SLF001
                                       for i in issues for p in i["evidence"]
                                       for e in f.get("evidence") or [])]
    # B1's rule, issue by issue; the run's answer is read whenever it was made (never "planted
    # after": a case's issues are those standing when its snapshot was collected).
    marked = AN.marks(issues, {"ok": True, "findings": findings})
    missed = [m for m in marked if m["found"] != "found"]
    missed_issues = [m.get("name") for m in missed]
    found = bool(issues) and not missed
    at_severity = any(f.get("severity") in allowed for f in hits)
    conflicts = false_conflicts(case, findings)
    threat = bool(conflicts) or any(
        SEVERITY_RANK.get(f.get("severity"), 0) > top
        and SEVERITY_RANK.get(f.get("severity"), 0) >= SEVERITY_RANK["medium"]
        for f in findings)
    ok = bool((result or {}).get("ok"))
    correct = ok and (found and at_severity if kind == "threat" else
                      not threat if kind == "benign" else None)
    return {"ok": ok, "error": (result or {}).get("error") or "",
            "findings": len(findings), "found": found, "found_at_severity": at_severity,
            "missed": kind == "threat" and not found,
            "missed_issues": missed_issues if kind == "threat" else [],
            "missed_ids": [m.get("id") for m in missed] if kind == "threat" else [],
            "false_positives": judged.count("false_positive"), "real": judged.count("real"),
            "notes": judged.count("note"), "threat_answered": kind == "benign" and threat,
            "false_conflicts": len(conflicts) if kind == "benign" else 0,
            "correct": correct, "judged": judged}


def disjoint_groups(case: dict) -> list:
    """The groups of flow ids a case's expectation names ``disjoint``: flows whose matches no
    packet can meet together, so one never shadows or contradicts another."""
    return [list(g) for alt in _alternatives(case.get("expect") or {})
            for g in alt.get("disjoint") or [] if g]


def false_conflicts(case: dict, findings: list) -> list:
    """The kept *findings* that set flows the case names disjoint against each other
    (`disjoint_groups`): each cites every id of one group at a severity above info (an info
    finding is a note, as `sdn_analyst_tools.judge` reads one). Judged by the ids cited, never
    by the finding's words. The Lab 9 sitting, 2026-11-10: both techniques reported a drop of
    DHCP replies and a forward of DHCP requests as a conflict."""
    groups = disjoint_groups(case)
    return [f for f in findings or [] if f.get("severity") != "info"
            and any(all(i in (f.get("evidence") or []) for i in g) for g in groups)]


def wrong_row(case: dict, snap: dict, result: dict, scored: dict, *, network: str, actor: str,
              technique: str, n: int, calls: list, at: float) -> dict:
    """The network's record of one run that was wrong (C2943; modules/sdn/evaluations.py), or
    {} when it was not: it missed the case's planted issue, kept a false-positive finding
    (`sdn_analyst_tools.judge`'s rule), or answered a benign case as a threat. The row names
    the run, the case, the technique, the run's number, its calls, the planted issue's
    evidence, the expected severities and each finding as the arm kept it, judged."""
    from modules.sdn import evaluations

    if not (scored["missed"] or scored["false_positives"] or scored["threat_answered"]):
        return {}
    findings = (result or {}).get("findings") or [] if (result or {}).get("ok") else []
    issues = case_issues(case)
    # The evidence of the issues missed (a hardware case may hold several), else of them all.
    named = [i for i in issues if i.get("id") in (scored.get("missed_ids") or [])] or issues
    return {"script": evaluations.B4_EVAL, "kind": "case_run",
            "run": actor.split(":", 1)[1] if ":" in actor else actor, "actor": actor,
            "network": network, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at)),
            "case": case.get("key"), "name": case.get("name") or case.get("key"),
            "role": case.get("role"), "file": case.get("file"), "case_kind": kind_of(case),
            "technique": technique, "n": n, "snapshot": snap.get("id"), "calls": list(calls),
            "error": scored["error"], "missed": scored["missed"],
            "false_positives": scored["false_positives"],
            "threat_answered": scored["threat_answered"],
            "false_conflicts": scored.get("false_conflicts", 0),
            "disjoint": disjoint_groups(case) if scored.get("false_conflicts") else [],
            "issue": [p for i in named for p in i["evidence"]],
            "missed_issues": list(scored.get("missed_issues") or []),
            "severities": sorted(expected_severities(case)),
            "findings": [{"severity": f.get("severity"), "finding": f.get("finding"),
                          "why": f.get("why"), "evidence": list(f.get("evidence") or []),
                          "judged": j}
                         for f, j in zip(findings, scored["judged"])]}


def run(cases: list, arms: dict, *, runs: int, network: str, actor: str, trigger: dict,
        send=None, clock=time.monotonic, say=None, now=time.time) -> dict:
    """Every case's snapshot asked of each arm (*arms*: ``{"baseline": fn, "tools": fn}``, each
    ``fn(network, snap, actor=, trigger=, send=)``, the analyst's `ask_snapshot` and the trace
    tool's) *runs* times, in turn by run (case 1 baseline, case 1 tools, case 2 ...). Each run
    scored (`score_run`) with its calls, its recorded cost (`recorded_cost`) and its wall time.
    Each run that was wrong (`wrong_row`: a miss, a false-positive finding, a benign case
    answered as a threat) is kept in the network's record of evaluation runs as it is scored
    (C2943, modules/sdn/evaluations.py), so History › Export lists it; the analyst's own store
    is never written. A refusal by Mercury or the gateway before anything is sent
    (``withheld``, ``classified``, ``ai_off``, a cap) stops the run there, with nothing more
    spent, said as ``stopped``."""
    from modules.sdn import evaluations

    out = {"network": network, "actor": actor, "runs": runs, "cases": [], "stopped": ""}
    say = say or (lambda words: None)
    stops = ("withheld", "classified", "ai_off", "no_key", "over_cap", "feature_cap", "trigger",
             "workspace_limit")
    for case in cases:
        snap = case_snapshot(case, network)
        row = {"key": case.get("key"), "name": case.get("name"), "role": case.get("role"),
               "file": case.get("file"), "kind": kind_of(case), "snapshot": snap["id"],
               "issues": len(case_issues(case)), "runs": {t: [] for t in TECHNIQUES}}
        if case.get("role") == HARDWARE:
            row.update(collected_at=case.get("collected_at"), clean=bool(case.get("clean")),
                       planted=[i.get("name") for i in case_issues(case)])
        out["cases"].append(row)
        for n in range(1, runs + 1):
            for technique in TECHNIQUES:
                start = clock()
                result = arms[technique](network, snap, actor=actor, trigger=trigger, send=send)
                took = clock() - start
                calls = ([c for c in result.get("calls") or [] if c] if technique == "tools"
                         else [result.get("call_id")] if result.get("call_id") else [])
                scored = score_run(case, snap, result)
                row["runs"][technique].append(dict(scored, n=n, calls=calls, seconds=took,
                                                   cost_usd=0.0,
                                                   passes=result.get("passes", 1 if calls else 0),
                                                   reads=len(result.get("reads") or [])))
                kept = wrong_row(case, snap, result, scored, network=network, actor=actor,
                                 technique=technique, n=n, calls=calls, at=now())
                if kept:
                    evaluations.keep(network, [kept])
                if not result.get("ok") and result.get("error") in stops:
                    out["stopped"] = (f"case {row['key']} run {n} ({technique}): "
                                      f"{result.get('error')}: {result.get('detail')}")
                    say(f"stopped: {out['stopped']}")
                    return out
            say(f"case {row['key']} run {n}: done")
    return out


def recorded_cost(results: dict, rows: list) -> None:
    """Each run's cost from the record of AI calls (*rows*, `calls.read()`'s): the sum of the
    gateway's recorded ``cost_usd`` over the calls the run made."""
    cost = {r.get("id"): float(r.get("cost_usd") or 0.0) for r in rows or []}
    for c in results.get("cases") or []:
        for runs in c["runs"].values():
            for r in runs:
                r["cost_usd"] = round(sum(cost.get(i, 0.0) for i in r["calls"]), 6)


# ───────────────────────────────────────────────────────────────────────────── the measures

def mcnemar_p(b: int, c: int) -> float:
    """McNemar's exact test, two-sided: the binomial probability of a split at least as uneven
    as *b* against *c* among the b + c cases that flip, at one half."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def bootstrap(values, stat, n: int = BOOTSTRAP, seed: int = SEED) -> tuple:
    """A 95% percentile interval of *stat* over *values* resampled *n* times (seeded)."""
    values = list(values)
    if not values:
        return (None, None)
    rng = random.Random(seed)
    draws = sorted(stat([values[rng.randrange(len(values))] for _ in values]) for _ in range(n))
    return (round(draws[int(0.025 * n)], 4), round(draws[int(0.975 * n) - 1], 4))


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _reliable(runs: list):
    if any(r["correct"] is None for r in runs):
        return None
    return bool(runs) and all(r["correct"] for r in runs)


def _role_summary(cases: list) -> dict:
    per = {t: {} for t in TECHNIQUES}
    scored = [c for c in cases if c["kind"] != "either" and all(c["runs"][t] for t in TECHNIQUES)]
    for t in TECHNIQUES:
        runs = [r for c in cases for r in c["runs"][t]]
        threat_runs = [r for c in scored if c["kind"] == "threat" for r in c["runs"][t]]
        cost = [r["cost_usd"] for r in runs]
        secs = [r["seconds"] for r in runs]
        per[t] = {
            "cases": len(scored), "runs": len(runs),
            "reliable": sum(1 for c in scored if _reliable(c["runs"][t])),
            "findings": sum(r["findings"] for r in runs),
            "found": sum(1 for r in runs if r["found"]),
            "misses": sum(1 for r in runs if r["missed"]),
            "false_positives": sum(r["false_positives"] for r in runs),
            "benign_threat_runs": sum(1 for r in runs if r["threat_answered"]),
            "calls": sum(len(r["calls"]) for r in runs),
            "reads": sum(r["reads"] for r in runs),
            "cost_usd": round(sum(cost), 6),
            "cost_per_answer_usd": round(_mean(cost), 6),
            "cost_interval_usd": bootstrap(cost, _mean),
            "found_share": round(_mean(1.0 if r["found"] else 0.0 for r in threat_runs), 4),
            "seconds_median": round(statistics.median(secs), 3) if secs else None,
            "seconds_iqr": (round(statistics.quantiles(secs, n=4)[2]
                                  - statistics.quantiles(secs, n=4)[0], 3)
                            if len(secs) >= 2 else None)}
    flips_up = sum(1 for c in scored if _reliable(c["runs"]["tools"])
                   and not _reliable(c["runs"]["baseline"]))
    flips_down = sum(1 for c in scored if _reliable(c["runs"]["baseline"])
                     and not _reliable(c["runs"]["tools"]))
    pairs = [(1 if _reliable(c["runs"]["tools"]) else 0) - (1 if _reliable(c["runs"]["baseline"])
                                                            else 0) for c in scored]
    return {"techniques": per, "cases": len(scored),
            "either": sum(1 for c in cases if c["kind"] == "either"),
            "difference": {"reliable": per["tools"]["reliable"] - per["baseline"]["reliable"],
                           "share_reliable": round(_mean(pairs), 4),
                           "share_interval": bootstrap(pairs, _mean),
                           "flipped_to_reliable": flips_up, "flipped_from_reliable": flips_down,
                           "mcnemar_p": round(mcnemar_p(flips_up, flips_down), 4),
                           "false_positives": (per["tools"]["false_positives"]
                                               - per["baseline"]["false_positives"]),
                           "benign_threat_runs": (per["tools"]["benign_threat_runs"]
                                                  - per["baseline"]["benign_threat_runs"]),
                           "cost_usd": round(per["tools"]["cost_usd"]
                                             - per["baseline"]["cost_usd"], 6)}}


def summary(results: dict) -> dict:
    """The measures by role (recorded, held_out, blind, hardware) and over all, and the pass
    rule's verdict on the blind role alone (19.13), with its power said."""
    roles = {}
    for role in ROLES:
        cases = [c for c in results.get("cases") or [] if c["role"] == role]
        if cases:
            roles[role] = _role_summary(cases)
    every = _role_summary(results.get("cases") or [])
    blind = roles.get("blind")
    if blind is None:
        verdict = {"improves": None, "words": "no blind case was run: the pass rule cannot be "
                   "judged (19.13: the blind set decides; the recorded and held-out results are "
                   "reported, labelled as not blind)"}
    else:
        b, t = blind["techniques"]["baseline"], blind["techniques"]["tools"]
        rises = t["reliable"] > b["reliable"]
        no_more = t["benign_threat_runs"] <= b["benign_threat_runs"]
        verdict = {"improves": rises and no_more, "rises": rises, "no_more_false_positives": no_more,
                   "words": (f"blind: {t['reliable']} of {blind['cases']} cases reliable with the "
                             f"trace tool against {b['reliable']} without; benign runs answered "
                             f"as a threat {t['benign_threat_runs']} against "
                             f"{b['benign_threat_runs']}: "
                             + ("improves results" if rises and no_more else
                                "does not improve results by the pass rule")
                             + f"; with {blind['cases']} blind cases one case is about "
                             f"{round(100 / max(1, blind['cases']))} points, so the power is low")}
    return {"roles": roles, "all": every, "pass_rule": verdict,
            "not_converted": NOT_CONVERTED, "stopped": results.get("stopped") or "",
            "hardware": results.get("hardware") or {}}


def report_markdown(results: dict, meta: dict) -> str:
    """The report for the lab document and B5's cost log."""
    s = summary(results)
    lines = ["# Lab 9 B4: the analyst with the trace tool against the analyst without it", "",
             f"- Run: {meta.get('actor')} on {meta.get('network')}, {meta.get('at')}; "
             f"{results.get('runs')} runs a case and technique",
             f"- Baseline: {WORDS['baseline']}, prompt {meta.get('baseline_prompt')}; technique: "
             f"{WORDS['tools']}, prompts {meta.get('tools_prompts')}; model "
             f"{meta.get('model')}",
             f"- Cases: {sum(c['role'] in ROLES_1913 for c in results.get('cases') or [])} from "
             "19.13's files; not converted: "
             + "; ".join(f"{k} ({v})" for k, v in NOT_CONVERTED.items()),
             f"- Pass rule (frozen, 19.13): {s['pass_rule']['words']}"]
    sitting = [c for c in results.get("cases") or [] if c["role"] == SITTING]
    if sitting:
        lines.append(f"- The Lab 9 sitting's cases: {len(sitting)}, modelled on the test fabric "
                     "after what the analyst got wrong on 2026-11-10 (a planted flow missed; "
                     "disjoint flows reported as a conflict); never blind, and no part of the "
                     "pass rule")
    hw = s["hardware"]
    if hw:
        cases = [c for c in results.get("cases") or [] if c["role"] == HARDWARE]
        lines.append(f"- Hardware: {len(cases)} snapshots kept on the lab's switches, from "
                     f"{hw.get('folder')} ({sum(1 for c in cases if c.get('clean'))} named clean); "
                     f"skipped {len(hw.get('skipped') or [])}"
                     + "".join(f"; {x['id']}: {x['why']}" for x in hw.get("skipped") or [])
                     + "".join(f"; {x['id']} named clean, with {x['standing']} "
                               f"{'issue' if x['standing'] == 1 else 'issues'} standing on the "
                               "sheet: scored benign"
                               for x in hw.get("clean_with_issues") or []))
    if s["stopped"]:
        lines.append(f"- **Stopped:** {s['stopped']}")
    for role, r in list(s["roles"].items()) + [("all (not one measure: blind decides)", s["all"])]:
        label = role if role == "blind" or role.startswith("all") else f"{role} (not blind)"
        lines += ["", f"## {label}", "",
                  "| Measure | Without tools | With the trace tool | Difference |",
                  "|---|---|---|---|"]
        b, t, d = r["techniques"]["baseline"], r["techniques"]["tools"], r["difference"]
        lines += [
            f"| Cases reliable (every run correct) | {b['reliable']} of {r['cases']} | "
            f"{t['reliable']} of {r['cases']} | {d['reliable']:+d} (share {d['share_reliable']:+}, "
            f"95% {d['share_interval']}; McNemar exact p {d['mcnemar_p']}, "
            f"{d['flipped_to_reliable']} up, {d['flipped_from_reliable']} down) |",
            f"| Findings kept | {b['findings']} | {t['findings']} | |",
            f"| Runs finding the planted issue | {b['found']} | {t['found']} | |",
            f"| Misses (runs) | {b['misses']} | {t['misses']} | {t['misses'] - b['misses']:+d} |",
            f"| False positives (findings, by code's rule) | {b['false_positives']} | "
            f"{t['false_positives']} | {d['false_positives']:+d} |",
            f"| Benign runs answered as a threat | {b['benign_threat_runs']} | "
            f"{t['benign_threat_runs']} | {d['benign_threat_runs']:+d} |",
            f"| Calls (reads asked) | {b['calls']} | {t['calls']} ({t['reads']}) | |",
            f"| Cost, recorded | ${b['cost_usd']:.6f} | ${t['cost_usd']:.6f} | "
            f"{d['cost_usd']:+.6f} |",
            f"| Cost per answer (95%) | ${b['cost_per_answer_usd']:.6f} {b['cost_interval_usd']} "
            f"| ${t['cost_per_answer_usd']:.6f} {t['cost_interval_usd']} | |",
            f"| Seconds to an answer, median (IQR) | {b['seconds_median']} ({b['seconds_iqr']}) "
            f"| {t['seconds_median']} ({t['seconds_iqr']}) | |"]
    lines += ["", "## Each case", "", "| Case | Role | Kind | Without tools: correct | "
              "With the trace tool: correct |", "|---|---|---|---|---|"]
    for c in results.get("cases") or []:
        cells = [f"{sum(1 for r in c['runs'][t] if r['correct'])} of {len(c['runs'][t])}"
                 for t in TECHNIQUES]
        lines.append(f"| {c['key']} | {c['role']} | {c['kind']} | {cells[0]} | {cells[1]} |")
    lines += ["", "False positive: a kept finding that cites no planted issue's evidence and no "
              "fact the code measures as abnormal (a port down, a link not up, a drop flow, a "
              "port dropping packets or at 80% or more of its speed), and is not info "
              "(modules/ai/sdn_analyst_tools.py `judge`)."]
    return "\n".join(lines) + "\n"


def estimate(cases: list, network: str, runs: int) -> dict:
    """What a run would spend, before it does, by each arm's own estimate of each case's
    snapshot: ``{"calls", "usd", "cases", "hardware"}`` (the trace tool counted at its two
    calls; *hardware* how many of the cases are the lab hardware's snapshots)."""
    from modules.ai import sdn_analyst_tools as AT
    from modules.sdn import analyst as AN

    usd, calls = 0.0, 0
    for case in cases:
        snap = case_snapshot(case, network)
        usd += runs * (AN.estimate(snap)["usd"] + AT.estimate(snap)["usd"])
        calls += runs * (1 + 2)
    return {"calls": calls, "usd": round(usd, 4), "cases": len(cases),
            "hardware": sum(1 for c in cases if c.get("role") == HARDWARE)}


def asked_prompts(version: int = None) -> tuple:
    """``(what a run asks, refusal)`` for *version* of the analyst's prompt (None: the one in
    use): ``{"version", "in_use", "in_use_words", "baseline_prompt", "tools_prompts"}``, the
    baseline's prompt and the trace tool's two built on it (`sdn_analyst_tools.PASSES_OF`) as
    the record of AI calls names them; a version either arm does not hold is refused, naming
    the versions it does."""
    from modules.ai import sdn_analyst_tools as AT
    from modules.sdn import analyst as AN

    try:
        (name, v), _schema = AN.asked_as(version)
        AT.loop_for(v)
    except ValueError as exc:
        return {}, str(exc)
    first, second = AT.PASSES_OF[v]
    return {"version": v, "in_use": v == AN.PROMPT[1],
            "in_use_words": f"{AN.PROMPT[0]}.v{AN.PROMPT[1]}",
            "baseline_prompt": f"{name}.v{v}",
            "tools_prompts": f"{first[0]}.v{first[1]} and v{second[1]}"}, ""


def main(argv, *, arms: dict, root: str, send=None, now=None, clock=time.monotonic,
         out=print) -> int:
    """The script's body (`scripts/nmas-sdn-b4-eval` hands in the two arms): refuses without
    ``--yes-spend`` (printing what the run would spend), an ``--out`` inside the checkout, a
    person's address as the actor, or a network the gateway cannot name; a ``--snapshots``
    folder inside the checkout, the role ``hardware`` without one or one without it, and
    ``--clean`` without ``--snapshots`` or naming a snapshot the folder does not hold; a
    ``--prompt`` naming a version the analyst does not hold. ``--prompt N`` asks both arms with
    version N of the analyst's prompt (`asked_prompts`), a candidate measured before it is
    adopted; the report names the prompts asked. Exit 0 when the run finished, 3 when a
    refusal stopped it, 2 when nothing was asked."""
    import argparse
    import functools

    from modules.ai import calls, cases as AIC, profiles, triggers

    ap = argparse.ArgumentParser(prog="nmas-sdn-b4-eval", description=__doc__.splitlines()[0])
    ap.add_argument("--list", required=True, help="the network whose AI settings apply")
    ap.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    ap.add_argument("--roles", default=None,
                    help="comma-separated, of " + ", ".join(ROLES) + " (default: "
                         + ",".join(FIXTURE_ROLES) + ", and hardware with --snapshots)")
    ap.add_argument("--cases", default="",
                    help="case keys or snapshot ids, comma-separated (default: every)")
    ap.add_argument("--snapshots", default="",
                    help="a copy of the network's sdn_analyst/ folder, outside the checkout, "
                         "read only: each sealed snapshot a hardware case")
    ap.add_argument("--clean", default="",
                    help="snapshot ids, comma-separated, kept with every planted issue "
                         "restored or collected before any was planted: each a benign "
                         "hardware case")
    ap.add_argument("--out", required=True, help="a folder outside the checkout")
    ap.add_argument("--prompt", type=int, default=0,
                    help="ask both arms with this version of the analyst's prompt (and the "
                         "trace tool's two built on it) in place of the ones in use: a "
                         "candidate measured before it is adopted")
    ap.add_argument("--actor", default="")
    ap.add_argument("--yes-spend", action="store_true",
                    help="spend: without it, the run says what it would spend and stops")
    args = ap.parse_args(argv)
    inside = os.path.realpath(root) + os.sep
    if os.path.realpath(args.out).startswith(inside):
        out(f"nmas-sdn-b4-eval: --out {args.out} is inside the checkout; write it elsewhere")
        return 2
    if args.snapshots and os.path.realpath(args.snapshots).startswith(inside):
        out(f"nmas-sdn-b4-eval: --snapshots {args.snapshots} is inside the checkout; copy the "
            "network's sdn_analyst/ folder elsewhere")
        return 2
    if not 1 <= args.runs <= 50:
        out(f"nmas-sdn-b4-eval: --runs is 1 to 50, not {args.runs}")
        return 2
    roles = ([r for r in args.roles.split(",") if r] if args.roles is not None
             else list(FIXTURE_ROLES) + ([HARDWARE] if args.snapshots else []))
    clean = [k for k in args.clean.split(",") if k]
    shape = (f"--roles names {', '.join(sorted(set(roles) - set(ROLES)))}, not one of "
             f"{', '.join(ROLES)}" if set(roles) - set(ROLES) else
             "--roles names hardware, and no --snapshots folder is given"
             if HARDWARE in roles and not args.snapshots else
             f"--snapshots {args.snapshots} is given, and --roles ({','.join(roles)}) leaves out "
             "hardware" if args.snapshots and HARDWARE not in roles else
             "--clean names snapshots, and no --snapshots folder is given"
             if clean and not args.snapshots else "")
    if shape:
        out(f"nmas-sdn-b4-eval: {shape}")
        return 2
    asked, why_not = asked_prompts(args.prompt or None)
    if why_not:
        out(f"nmas-sdn-b4-eval: --prompt {args.prompt}: {why_not}; nothing was asked")
        return 2
    if args.prompt:
        # Each arm handed the candidate's version; an arm asked without it asks the one in use.
        arms = {t: functools.partial(fn, prompt=args.prompt) for t, fn in arms.items()}
    actor, refusal = AIC.evaluation_actor(args.actor, "sdn-b4-eval", now)
    network, why = AIC.run_network(args.list) if not refusal else ("", "")
    if refusal or why:
        out(f"nmas-sdn-b4-eval: {refusal or why}")
        return 2
    keys = [k for k in args.cases.split(",") if k]
    fixture = [r for r in roles if r in FIXTURE_ROLES]
    picked = load_cases(root, fixture, keys or None) if fixture else []
    hardware = {}
    if HARDWARE in roles:
        hw = load_hardware(args.snapshots, network, clean, keys or None)
        if hw["error"]:
            out(f"nmas-sdn-b4-eval: {hw['error']}; nothing was asked")
            return 2
        for x in hw["skipped"]:
            out(f"nmas-sdn-b4-eval: skipped the snapshot {x['id']}: {x['why']}")
        picked += hw["cases"]
        hardware = {"folder": os.path.abspath(args.snapshots), "clean": clean,
                    "skipped": hw["skipped"],
                    "clean_with_issues": [{"id": c["key"], "standing": c["sheet_issues"]}
                                          for c in hw["cases"]
                                          if c["clean"] and c["sheet_issues"]]}
    if not picked:
        out("nmas-sdn-b4-eval: no case matches --roles and --cases")
        return 2
    est = estimate(picked, network, args.runs)
    out(f"nmas-sdn-b4-eval: {est['cases']} cases ({est['hardware']} of them the lab hardware's "
        f"snapshots) x {args.runs} runs x 2 techniques: at most "
        f"{est['calls']} calls, about ${est['usd']:.4f} by the over-estimate (the tool arm at "
        "its two calls), on " + profiles.task("sdn_analyse")["model"]
        + f"; prompts {asked['baseline_prompt']} and {asked['tools_prompts']}"
        + ("" if asked["in_use"] else f" (a candidate: {asked['in_use_words']} is in use)"))
    if not args.yes_spend:
        out("nmas-sdn-b4-eval: refused: nothing was asked or spent; read the ledger's spend "
            "left first (PHASE8_PLAN 0.5), then run again with --yes-spend")
        return 2
    trig = triggers.evaluation(actor)
    results = run(picked, arms, runs=args.runs, network=network, actor=actor, trigger=trig,
                  send=send, clock=clock, say=lambda w: out(f"nmas-sdn-b4-eval: {w}"))
    if hardware:
        results["hardware"] = hardware
    recorded_cost(results, calls.read().get("rows") or [])
    meta = {"actor": actor, "network": network,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None
                                                                 else now)),
            "model": profiles.task("sdn_analyse")["model"],
            "baseline_prompt": asked["baseline_prompt"], "tools_prompts": asked["tools_prompts"],
            "prompt_in_use": asked["in_use"], "estimate": est}
    os.makedirs(args.out, exist_ok=True)
    stem = os.path.join(args.out, "b4-eval-" + actor.split(":", 1)[1])
    with open(stem + ".json", "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "summary": summary(results), "results": results}, fh,
                  indent=1, sort_keys=True, default=str)
    with open(stem + ".md", "w", encoding="utf-8") as fh:
        fh.write(report_markdown(results, meta))
    out(f"nmas-sdn-b4-eval: wrote {stem}.md and {stem}.json")
    return 3 if results.get("stopped") else 0
