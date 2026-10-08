"""Test the logging path (NSOT_READS.md section 11, the operator, 2026-10-08).

Does a line a device writes to its log reach Mercury? Each chosen device is asked, through the
reads engine (refused first, held, recorded), to `send log` one line carrying a token unique to
the run; then Loki is watched for each device's line, and each device's result says
"received after N s" or "not received within 30 s".

**A line is matched by the device's own name and the token, nothing else.** The device's name
is anchored as the Logs tab anchors it (`device_logs.host_pattern`: `logging origin-id hostname`,
never rsyslog's host field, C13), and the token is the run's. What IOS wraps around a `send log`
line (its mnemonic, the terminal and user it names) is NOT relied on: no such line had ever
reached this Loki when this was written (measured 2026-10-08: 0 `USERLOG` lines among the 23,369
in seven days), so the first real run is its measurement.

**Times are the receiver's.** "After N s" is Loki's receive time of the line less the time the
device's answer to `send log` arrived at Mercury: both clocks are this installation's, never the
device's (its clock may be days off, CLAUDE.md).

**Loki is watched with one query per poll for the whole run, never one per device** (enterprise
scale), every `POLL_SECONDS` until every device's line is found or the last device's
`WAIT_SECONDS` have passed. A query Mercury could not make, or one cut at its page size, decides
nothing: those devices are `unknown`, naming why, never "not received".
"""

import logging
import re
import time

log = logging.getLogger(__name__)

#: The operator's window: a line not seen within 30 s of its send is "not received".
WAIT_SECONDS = 30
#: Loki cannot tell Mercury a line arrived, so the watch asks; every 2 s answers "after N s" to
#: within 2 s, 15 queries in a 30 s window.
POLL_SECONDS = 2
#: informational (6): the level a test line is, never one an alert rule keys on.
LEVEL = 6
TOKEN_WORD = "MERCURY-LOGTEST"
#: The steps, in order, as the manual names them.
STEPS = ("refuse", "send", "watch", "record")

RECEIVED, NOT_RECEIVED, NOT_SENT, UNKNOWN = "received", "not received", "not sent", "unknown"
#: The run's purpose in the reads record: how its page and History know it is this test.
PURPOSE = "test the logging path"


class Refused(ValueError):
    """The test sends nothing; the message names why."""


def token(run_id: str) -> str:
    """The run's own words: its id's random part, so two runs never match each other's lines."""
    return f"{TOKEN_WORD} {run_id.rsplit('-', 1)[-1][:16]}"


def command(run_id: str) -> str:
    return f"send log {LEVEL} {token(run_id)}"


def _loki():
    from modules.integrations.loki import LokiIntegration
    return LokiIntegration()


def loki_configured() -> bool:
    return _loki().is_configured()


def refusal(hosts: list) -> str:
    """``""`` when the test may send, else why: nothing to watch with is a refusal before any
    device is asked, never a run of "not received"."""
    if not hosts:
        return "Refused: no device to test."
    if not loki_configured():
        return ("Refused: Loki is not configured (Settings, Integrations), so nothing could "
                "watch for the line. Nothing was sent.")
    return ""


def _ask(start_ns: int, end_ns: int, tok: str, limit: int):
    """``(lines, why)``: ``[(ns, line)]`` holding *tok* in the network's syslog, or why not."""
    from modules.device_logs import JOB
    r = _loki()._get("loki/api/v1/query_range", query=f'{{job="{JOB}"}} |= "{tok}"',
                     start=start_ns, end=end_ns, limit=limit, direction="forward")
    if not r.get("ok"):
        return None, f"Loki could not be asked: {r.get('error')}"
    try:
        streams = (r["response"].json().get("data") or {}).get("result") or []
    except ValueError as exc:
        return None, f"Loki's answer could not be read: {exc}"
    lines = [(int(ns), line) for s in streams for ns, line in s.get("values") or []]
    if len(lines) >= limit:
        return None, (f"Loki's answer was cut at its page size ({limit} lines), so a device "
                      "missing from it may still have been received")
    return lines, ""


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def watch(sent_at: dict, tok: str, *, wait: float = None, poll: float = None,
          ask=None, clock=time.time, sleep=time.sleep, progress=None) -> dict:
    """``{host: result}`` for each host in *sent_at* (``{host: when its send answered}``).

    *ask* is ``(start_ns, end_ns, token, limit) -> (lines, why)`` (tests); by default Loki.
    *progress* is called with ``{host: after_s}`` each time a poll finds a new line, so the
    run's page shows the lines as they arrive (board F, 7f), never on a timer of its own."""
    from modules.device_logs import host_pattern

    ask = ask or _ask
    wait = WAIT_SECONDS if wait is None else wait
    poll = POLL_SECONDS if poll is None else poll
    if not sent_at:
        return {}
    patterns = {h: re.compile(host_pattern(h)) for h in sent_at}
    start_ns = int((min(sent_at.values()) - 5) * 1e9)
    deadline = max(sent_at.values()) + wait
    limit = max(100, 4 * len(sent_at))
    found, why = {}, ""
    while True:
        now = clock()
        lines, why = ask(start_ns, int(now * 1e9), tok, limit)
        before = len(found)
        for ns, line in lines or []:
            for host, pattern in patterns.items():
                if host not in found and pattern.search(line):
                    found[host] = ns
        if progress is not None and len(found) > before:
            try:
                progress({h: round(ns / 1e9 - sent_at[h], 1) for h, ns in found.items()},
                         deadline)
            except Exception:                         # noqa: BLE001 (a page's progress only)
                log.debug("logging path: progress failed", exc_info=True)
        if len(found) == len(sent_at) or now >= deadline:
            break
        sleep(min(poll, max(0.0, deadline - now)))
    out = {}
    for host, sent in sent_at.items():
        if host in found:
            after = round(found[host] / 1e9 - sent, 1)
            within = after <= wait
            out[host] = {"state": RECEIVED if within else NOT_RECEIVED,
                         "after_s": max(0.0, after), "sent_iso": _iso(sent),
                         "at_iso": _iso(found[host] / 1e9),
                         "words": (f"received after {max(0.0, after):.1f} s" if within else
                                   f"received after {after:.1f} s, past the {wait:g} s window")}
        elif why:
            out[host] = {"state": UNKNOWN, "words": f"not known: {why}", "sent_iso": _iso(sent)}
        else:
            out[host] = {"state": NOT_RECEIVED, "words": f"not received within {wait:g} s",
                         "sent_iso": _iso(sent), "until_iso": _iso(sent + wait)}
    return out


#: The not-received devices whose last line in Loki is read (one query each, after the watch):
#: what to look at first; more than this are named as not read.
LAST_LINE_FOR = 10
LAST_LINE_HOURS = 24


def last_lines(hosts: list, *, now: float = None, ask=None) -> dict:
    """``{host: iso or ""}``: when Loki last received a line from each of *hosts* (the first
    `LAST_LINE_FOR`), within `LAST_LINE_HOURS`; ``""`` when none, absent when not read."""
    from modules.device_logs import JOB, host_pattern
    now = time.time() if now is None else now
    out = {}
    for host in hosts[:LAST_LINE_FOR]:
        query = f'{{job="{JOB}"}} |= "{host}:" |~ `{host_pattern(host)}`'
        if ask is not None:
            r = ask(query)
        else:
            r = _loki()._get("loki/api/v1/query_range", query=query, limit=1,
                             start=int((now - LAST_LINE_HOURS * 3600) * 1e9), end=int(now * 1e9),
                             direction="backward")
        if not r.get("ok"):
            continue
        try:
            streams = (r["response"].json().get("data") or {}).get("result") or []
        except (ValueError, AttributeError):
            continue
        stamps = [int(ns) for s in streams for ns, _l in s.get("values") or []]
        out[host] = _iso(max(stamps) / 1e9) if stamps else ""
    return out


def outcome(record: dict, *, wait: float = None, **watch_kw) -> dict:
    """The test's result from the reads run *record* that sent the line: each device the send
    reached is watched; one it did not reach is "not sent", naming why."""
    from modules.nsot import reads

    wait = WAIT_SECONDS if wait is None else wait
    tok = token(record["id"])
    sent_at, results = {}, {}
    for host in record.get("devices") or []:
        r = (record.get("results") or {}).get(host) or {}
        answer = next(iter(r.get("answers") or []), None)
        if r.get("state") == reads.ANSWERED and answer and answer.get("state") == reads.ANSWERED:
            sent_at[host] = answer.get("at") or record.get("finished_at") or time.time()
        else:
            why = (answer or {}).get("why") or r.get("why") or r.get("state") or "no answer"
            results[host] = {"state": NOT_SENT, "words": f"not sent: {why}"}
    last_ask = watch_kw.pop("last_ask", None)
    results.update(watch(sent_at, tok, wait=wait, **watch_kw))
    missing = sorted(h for h, r in results.items() if r["state"] == NOT_RECEIVED)
    seen = last_lines(missing, ask=last_ask) if missing else {}
    for host in missing:
        if host in seen:
            results[host]["last_iso"] = seen[host]
        else:
            results[host]["last_unread"] = True
    counts = {}
    for r in results.values():
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return {"state": "done", "token": tok, "wait_s": wait, "results": results,
            "counts": counts}


def run(list_name: str, hosts: list, actor: str, *, run_id: str = "", session=None,
        **watch_kw) -> dict:
    """Send, watch, record: the reads run's record with ``logging_path`` added (also written)."""
    from modules.nsot import reads

    hosts = list(dict.fromkeys(h for h in (hosts or []) if h))
    why = refusal(hosts)
    if why:
        raise Refused(why)
    run_id = run_id or reads.new_id()
    record = reads.run(list_name, hosts, [command(run_id)], actor,
                       purpose=PURPOSE, run_id=run_id, session=session)

    def watching(received, deadline):
        reads.annotate(list_name, run_id, "logging_path",
                       {"state": "watching", "token": token(run_id), "received": received,
                        "until_iso": _iso(deadline)})

    watch_kw.setdefault("progress", watching)
    reads.annotate(list_name, run_id, "logging_path",
                   {"state": "watching", "token": token(run_id), "received": {}})
    result = outcome(record, **watch_kw)
    reads.annotate(list_name, run_id, "logging_path", result)
    record["logging_path"] = result
    log.info("logging path: %s tested %d device(s) in %s: %s", actor, len(hosts), list_name,
             result["counts"])
    return record


def start(list_name: str, hosts: list, actor: str) -> dict:
    """Refuse now, or start the test as a job: ``{"refused": why}`` or ``{"job", "run"}``."""
    from modules.nsot import capture_job, reads

    hosts = list(dict.fromkeys(h for h in (hosts or []) if h))
    why = refusal(hosts) or reads.refusal([command(reads.new_id())], len(hosts))
    if why:
        return {"refused": why}
    run_id = reads.new_id()
    label = "logging path on " + (hosts[0] if len(hosts) == 1 else f"{len(hosts)} devices")
    job = capture_job.start(list_name, label, actor,
                            lambda job_id: {"run": run(list_name, hosts, actor,
                                                       run_id=run_id)["id"]},
                            kind="logging path", announce_keys=reads.ANNOUNCE_KEYS,
                            announcer=reads.ANNOUNCER)
    return {"job": job, "run": run_id}
