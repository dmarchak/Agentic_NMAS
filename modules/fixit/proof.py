"""A verified fix's proof, as the incident's card draws it (the operator, 2026-11-16: ""Fixed"
shows its proof: under Verifying, the actual reads with their output and time"). One line by
default ("Verified: connected, no re-trip, config unchanged"), the reads in full, masked, on
expand. A read of the records the fix already keeps; nothing here asks a device.

- **A command plan's run** (an approved AI plan's step, a saved script's run; `of_run`): its
  verify checks (`command_plan_run.plan_verify`'s ``verify_checks``: each name, result, words
  and seconds), its net-zero check (``net_zero``: the configuration read before the send and
  again after), and every read the run made through the read engine (`modules/nsot/reads.py`),
  each with its time from the run's start and its masked answer. A read is the run's when its
  record names the run (``part_of``) or, as the runner reads today, when it is the runner's
  own read (`READ_ACTOR`) of the run's device inside the run's start and end.
- **An approved plan's run** (`of_plan`): each of its steps' own runs, said in one line.
- **A heal's act** (`of_act`): its verify steps (`act.VERIFY_STEPS`, kept on the incident's
  close as ``fixed.verify``, or the act's own steps in the step log), each step's reads by
  their reference into the read engine.

Each is ``{"line", "checks": [{"name", "result", "words", "took_s"}], "net_zero": {"words",
"lines"}, "reads": [{"command", "at", "offset_s", "answer", "cut", "said"}], "verify_s"}`` or
``{}`` when the record holds nothing to show; *verify_s* the seconds the verify took by its own
checks (the stepper's Verifying, `progress.lines`), None when unknown."""

import calendar
import logging
import os
import time

log = logging.getLogger(__name__)

#: The runner's reads, as the read engine records who asked (`command_plan_run.Sources.read`).
READ_ACTOR = "Mercury (reviewed commands)"
#: A verify check's few words for the one line, by what it expects (the plan's own verify
#: items); a check not here is said by its name.
SHORT = {"errdisable.port_connected": "connected",
         "errdisable.port_not_listed": "no re-trip"}
#: A heal's verify step's few words when it passed.
ACT_SHORT = {"intent": "at intent", "symptom": "symptom gone", "saved": "saved to startup",
             "golden": "matches its new golden"}
#: The most of one read's answer drawn in place; the rest is the read's own record (History).
OUTPUT_CHARS = 4000
#: The most reads one proof lists (a re-subscribe's verify polls up to 90).
READS_MAX = 40


def _epoch(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(calendar.timegm(time.strptime(str(value or "")[:19], "%Y-%m-%dT%H:%M:%S")))
    except (TypeError, ValueError, OverflowError):
        return None


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _stamp(epoch: float) -> str:
    """A read engine id's leading stamp for *epoch* (`reads.new_id`'s shape), for a window."""
    micro = min(999999, int((epoch - int(epoch)) * 1e6))
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime(epoch)) + f"{micro:06d}Z"


def _said(command: str, answer: str, port: str = "") -> str:
    """What a read found, in a few words, where Mercury parses it (a port's port-security)."""
    if command.startswith("show port-security interface"):
        from modules.heal import errdisable
        ps = errdisable.port_security(answer)
        if ps:
            n = ps.get("violations")
            return (f"{ps.get('status') or 'status not read'}, "
                    f"{'violations not read' if n is None else f'{n} violation(s)'}, last "
                    f"source {ps.get('last_mac') or 'none'}")
    if port and command.startswith("show interfaces status"):
        line = next((ln.strip() for ln in (answer or "").splitlines()
                     if ln.strip().lower().startswith(port.lower() + " ")), "")
        return " ".join(line.split()) if line else f"{port} not listed"
    return ""


def _masked(text: str) -> tuple:
    from modules.redact import redact_text

    text = redact_text(str(text or ""))
    return (text[:OUTPUT_CHARS], True) if len(text) > OUTPUT_CHARS else (text, False)


def run_reads(network: str, rec: dict, port: str = "") -> list:
    """The reads command plan run *rec* made, oldest first (the module's docstring), each
    ``{"command", "at", "offset_s", "answer", "cut", "said"}``. Reads the read engine's
    folder names first, so only the run's window is opened."""
    import json

    from modules.config import list_data_path

    start = _epoch(rec.get("started_at"))
    end = _epoch(rec.get("finished_at")) or time.time()
    device, rid = rec.get("device") or "", str(rec.get("id") or "")
    if start is None or not device:
        return []
    lo, hi = _stamp(start - 1), _stamp(end + 1)
    folder = os.path.join(list_data_path(network), "reads")
    try:
        names = sorted(n for n in os.listdir(folder)
                       if n.endswith(".json") and lo <= n[:22] <= hi)
    except OSError:
        return []
    out = []
    for name in names:
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                r = json.load(fh)
        except (OSError, ValueError):
            continue
        mine = (r.get("part_of") or {}).get("id") == rid or (
            r.get("actor") == READ_ACTOR and device in (r.get("devices") or []))
        if not mine:
            continue
        for a in ((r.get("results") or {}).get(device) or {}).get("answers") or []:
            at = _epoch(a.get("at")) or _epoch(r.get("started_at")) or start
            answer, cut = _masked(a.get("answer") if a.get("state") == "answered"
                                  else f"not read: {a.get('why') or a.get('state')}")
            out.append({"command": a.get("command") or "", "at": _iso(at),
                        "offset_s": max(0, round(at - start)), "answer": answer, "cut": cut,
                        "said": _said(a.get("command") or "", answer, port),
                        "read": r.get("id") or ""})
    out.sort(key=lambda e: e["offset_s"])
    return out[:READS_MAX]


def of_record(network: str, rec: dict) -> dict:
    """A command plan run's proof (the module's docstring); ``{}`` for a record with no
    verify kept."""
    checks = [c for c in rec.get("verify_checks") or [] if isinstance(c, dict)]
    nz = rec.get("net_zero") if isinstance(rec.get("net_zero"), dict) else {}
    if not checks and not nz:
        return {}
    expects = {}
    try:
        from modules.nsot import command_plan as CP
        expects = {i.get("name"): i.get("expect") for i in CP.template_of(rec.get("key")).verify}
    except Exception:                                 # noqa: BLE001 (said by name instead)
        expects = {}
    short = []
    for c in checks:
        word = SHORT.get(expects.get(c.get("name")) or "") or str(c.get("name") or "a check")
        short.append(word if c.get("result") == "pass" else f"{word}: {c.get('result')}")
    nz_words, nz_lines = "", list(nz.get("differs") or [])
    if nz.get("checked"):
        what = ("the configuration of " + ", ".join(nz.get("interfaces") or [])
                if nz.get("scope") == "interfaces" else "the running configuration")
        nz_words = (f"{what} read before the send and again after: identical" if not nz_lines
                    else f"{what} after differs from before ({len(nz_lines)} line(s))")
        short.append("config unchanged" if not nz_lines else "config changed")
    took = [float(c["took_s"]) for c in checks if isinstance(c.get("took_s"), (int, float))]
    port = str((rec.get("params") or {}).get("interface") or "") if isinstance(
        rec.get("params"), dict) else ""
    port = _short_port(port)
    return {"line": "Verified: " + ", ".join(short) if short else "",
            "checks": [{"name": c.get("name") or "", "result": c.get("result") or "",
                        "words": c.get("words") or "", "took_s": c.get("took_s"),
                        "read": c.get("read") or ""} for c in checks],
            "net_zero": {"words": nz_words, "lines": nz_lines},
            "reads": run_reads(network, rec, port),
            "verify_s": round(sum(took)) if took else None}


def _short_port(name: str) -> str:
    """``GigabitEthernet0/3`` as IOS lists it in ``show interfaces status`` (``Gi0/3``)."""
    for full, short in (("GigabitEthernet", "Gi"), ("FastEthernet", "Fa"),
                        ("TenGigabitEthernet", "Te"), ("Ethernet", "Et")):
        if name.startswith(full):
            return short + name[len(full):]
    return name


def of_run(network: str, run_id: str) -> dict:
    """The proof of the run *run_id* (`of_record`, or `of_plan` for a plan's), ``{}`` when it
    cannot be read or keeps none."""
    from modules.nsot import privileged

    if not run_id:
        return {}
    try:
        rec = privileged.get(network, run_id)
    except (OSError, ValueError):
        return {}
    if not isinstance(rec, dict):
        return {}
    from modules import plan_engine as PE
    if rec.get("key") == PE.KEY:
        return of_plan(network, rec)
    try:
        return of_record(network, rec)
    except Exception as exc:                          # noqa: BLE001 (drawn without it)
        log.error("proof: %s's run %s could not be read for its proof: %s", network, run_id,
                  exc)
        return {}


def of_plan(network: str, rec: dict) -> dict:
    """An approved plan's proof: each of its steps' own runs' (`of_run`), its reads and checks
    together, the one line each step's in order ("Verified: …; …")."""
    parts = []
    for st in rec.get("plan_steps") or []:
        rid = str((st.get("receipt") or {}).get("run") or "")
        got = of_run(network, rid) if rid and rid != rec.get("id") else {}
        if got:
            parts.append(got)
    if not parts:
        return {}
    if len(parts) == 1:
        return parts[0]
    took = [p["verify_s"] for p in parts if p.get("verify_s") is not None]
    return {"line": "Verified: " + "; ".join(p["line"].removeprefix("Verified: ")
                                             for p in parts if p.get("line")),
            "checks": [c for p in parts for c in p["checks"]],
            "net_zero": {"words": "; ".join(p["net_zero"]["words"] for p in parts
                                            if p["net_zero"]["words"]),
                         "lines": [ln for p in parts for ln in p["net_zero"]["lines"]]},
            "reads": [r for p in parts for r in p["reads"]][:READS_MAX],
            "verify_s": sum(took) if took else None}


def of_act(network: str, verify: list, began=None) -> dict:
    """A heal act's proof from its verify steps (`act.verified_of`'s ``verify``, or the act's
    own steps, `incident_page.acts`): each step's words as a check, its reads' answers from the
    read engine by their reference. ``{}`` with no verify step. Only the checks that decide
    the outcome (`act.DECIDING_STEPS`: the healed units' own check and the symptom's; the
    operator, 2026-11-16: "don't show a check that decides nothing as proof"): the save, the
    golden commit and the read again are the tail's, drawn under Fixed, never its proof."""
    from modules.heal import act
    from modules.nsot import reads

    steps = [s for s in verify or []
             if isinstance(s, dict) and s.get("step") in act.DECIDING_STEPS]
    if not steps:
        return {}
    start = _epoch(began) or _epoch(steps[0].get("at")) or 0
    short, out_reads = [], []
    for s in steps:
        ok = s.get("result") == "ok"
        word = ACT_SHORT.get(s.get("step") or "", str(s.get("step")))
        short.append(word if ok else f"{word}: {s.get('result')}")
        for e in s.get("reads") or []:
            if not isinstance(e, dict):
                continue
            at = _epoch(e.get("at")) or start
            answer, cut = "", False
            if e.get("read_id"):
                try:
                    r = reads.get(network, e["read_id"]) or {}
                except (OSError, ValueError):
                    r = {}
                got = next((a for res in (r.get("results") or {}).values()
                            for a in (res or {}).get("answers") or []
                            if a.get("command") == e.get("command")), None)
                if got:
                    answer, cut = _masked(got.get("answer") or "")
            out_reads.append({"command": e.get("command") or "", "at": _iso(at),
                              "offset_s": max(0, round(at - start)) if start else 0,
                              "answer": answer, "cut": cut, "said": e.get("words") or "",
                              "read": e.get("read_id") or ""})
    return {"line": "Verified: " + ", ".join(short),
            "checks": [{"name": act.STEP_LABELS.get(s.get("step"), s.get("step")),
                        "result": "pass" if s.get("result") == "ok" else s.get("result") or "",
                        # An act recorded before 2026-11-16 said its whole-device compare after
                        # the units' own check ("; intent: ..."): that part decided nothing.
                        "words": (str(s.get("words") or "").split("; intent: ")[0]
                                  if s.get("step") == "intent" else s.get("words") or ""),
                        "took_s": None, "read": ""}
                       for s in steps],
            "net_zero": {"words": "", "lines": []},
            "reads": out_reads[:READS_MAX], "verify_s": None}
