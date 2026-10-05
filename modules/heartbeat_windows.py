"""RE-MEASURE THE HEARTBEAT WINDOWS from the app (the operator, 2026-10-01,
after "STALE RATE s3": the fix was a console command with a placeholder).
NSOT_PLAN P.7, the heartbeat generator's action.

ONE implementation: `scripts/nmas-heartbeat-rules`, LOADED (as the CI verdict
loads `nmas-deploy`): its population, its measurement (restarts, configuration
changes and misses excluded, C299), its rules and its check. This module only
puts a preview, a confirm and a record around it.

- **plan()**: every device's INSTALLED window (the rules file Grafana loads,
  `/etc/grafana/provisioning/alerting/`, world-readable) beside the NEW one,
  with what it is measured from, the check's own verdict on the installed one,
  and a fingerprint of the file that would be written. Writes nothing.
- **apply()**: measured again; a moved plan is refused with nothing written.
  Writes the generated file where the script writes it (the app's checkout,
  gitignored), records who and when, and returns the ONE host step with every
  value filled in: the installed file is root's and the app's Grafana account
  is an Editor, which cannot reload provisioning (measured 2026-10-01), so the
  install and the Grafana restart are a person's, named exactly.
- **state()**: whether the written file is the installed one (hashes of both),
  so the page says "written, not yet installed" until the host step is done.
"""

import hashlib
import json
import logging
import os
import time

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-heartbeat-rules")
#: Where Grafana loads the rules from on the host (NSOT_PLAN P.1 step 5).
INSTALLED = "/etc/grafana/provisioning/alerting/nmas-heartbeat.yaml"
GRAFANA_UNIT = "grafana-server"


class Refused(Exception):
    """Nothing written; the message names why."""


def _script():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("nmas_heartbeat_rules", SCRIPT)
    spec = importlib.util.spec_from_loader("nmas_heartbeat_rules", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _read(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def _sha(text) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:16] if text is not None else ""


def _record_path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, "heartbeat_rules.jsonl")


def last_written() -> dict:
    """The newest record of a re-measure written from the app, or {}."""
    try:
        with open(_record_path(), encoding="utf-8") as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        return {"error": f"the record cannot be read ({exc})"}
    return rows[-1] if rows else {}


def plan(H=None, installed_path: str = "") -> dict:
    """The preview: ``{"rows", "restarts", "fingerprint", "text", "uid",
    "heartbeat", "not_expected", "changes"}``. Raises Refused for what the
    script calls UNPROVEN (no Loki, a failed read, no datasource UID)."""
    import yaml

    from modules.fanout import Failed, read_each

    installed_path = installed_path or INSTALLED
    H = H or _script()
    loki = H._loki_url("")
    if not loki:
        raise Refused("no Loki to measure from: set the Loki integration in Settings "
                      "(a window without a measurement is a guess)")
    from modules.list_settings import default_layer   # the Loki it reads is Default's

    heartbeat = int(default_layer("syslog_heartbeat_seconds") or 0)
    if heartbeat <= 0:
        raise Refused("syslog_heartbeat_seconds is not set: there is no interval to measure against")
    installed_text = _read(installed_path)
    installed = {}
    if installed_text:
        try:
            installed = H.installed(yaml.safe_load(installed_text) or {})
        except Exception as exc:                          # noqa: BLE001
            raise Refused(f"the installed rules ({installed_path}) cannot be read: {exc}") from exc
    # The datasource the rules query: the one the installed rules already
    # use (never a placeholder), else the setting, else refused by name.
    uids = {v[2] for v in installed.values() if v[2]}
    uid = (sorted(uids)[0] if len(uids) == 1 else "") or os.environ.get("NMAS_GRAFANA_LOKI_UID", "")
    if not uid:
        raise Refused("the Loki datasource's UID is not known: the installed rules name "
                      + (f"{len(uids)} different ones" if uids else "none"))
    expected, not_expected = H.expected_devices()
    hosts = sorted(expected)
    if not hosts:
        raise Refused("no device is told to heartbeat: a file with no rules reads like a fleet "
                      "that is all heartbeating, and is never written")
    restarts, note = H.prometheus_restarts(hosts)
    got = read_each(lambda h: H.gaps_from(H.loki_arrivals(loki, h),
                                          H.loki_arrivals(loki, h, query=H.config_query_for(h)),
                                          restarts.get(h, ())),
                    hosts, name="heartbeat-remeasure")
    failed = next((g for g in got if isinstance(g, Failed)), None)
    if failed is not None:
        raise Refused(f"Loki could not be read for every device ({failed.error}): a window "
                      "computed from the devices that answered is a guess about the rest")
    fresh = H.windows(dict(zip(hosts, got)), heartbeat)
    try:
        doc = H.build(fresh, uid, heartbeat)
    except ValueError as exc:
        raise Refused(str(exc)) from exc
    text = H.render(doc)
    _code, lines = H.check(installed, fresh, expected)
    verdict = {l.split(":")[0].split()[-1]: l for l in lines}
    rows = []
    for host in sorted(set(hosts) | set(installed)):
        new = fresh.get(host) or {}
        old = installed.get(host)
        rows.append({
            "device": host,
            "installed": {"window": old[0], "basis": old[1]} if old else None,
            "new": ({"window": new.get("window"), "basis": new.get("basis"),
                     "lo": new.get("lo"), "hi": new.get("hi"), "n": new.get("n"),
                     "rate": new.get("rate"), "assumed_rate": new.get("assumed_rate")}
                    if host in fresh else None),
            "band": ([round(2 * new["hi"]), round(3 * new["lo"])]
                     if "hi" in new and "lo" in new else None),
            "check": verdict.get(host, ""),
            "changes": (not old or host not in fresh
                        or int(old[0]) != int(new.get("window") or 0)
                        or old[1] != new.get("basis")),
            "restarts": len(restarts.get(host) or ()),
            # NEEDS a new window only where the check FAILS (its own rule: a
            # state in capitals). Measured on the host: 7 of 9 windows would
            # move by a few seconds while all 9 were current, and a write
            # costs a Grafana restart.
            "needs": bool(verdict.get(host)) and verdict[host].split()[0].isupper(),
        })
    return {"rows": rows, "restarts": H.restart_words(restarts, note), "uid": uid,
            "heartbeat": heartbeat, "not_expected": list(not_expected), "text": text,
            "fingerprint": _sha(text), "changes": sum(1 for r in rows if r["changes"]),
            "needs": sum(1 for r in rows if r["needs"]),
            "installed_sha": _sha(installed_text), "written_path": H.OUT,
            "installed_path": installed_path}


def host_step(written_path: str, installed_path: str = "") -> str:
    """The ONE host step, every value filled in: install the written file
    over the one Grafana loads, then restart Grafana so it reads it."""
    installed_path = installed_path or INSTALLED
    return (f"sudo install -m 0644 {written_path} {installed_path} && "
            f"sudo systemctl restart {GRAFANA_UNIT}")


def apply(fingerprint: str, actor: str, H=None, installed_path: str = "") -> dict:
    """Measure again, refuse a moved plan, write the generated file and record
    it. Returns the host step that installs it."""
    from modules.config import open_secure
    from modules.filestore import write_atomic

    if not actor:
        raise Refused("a re-measure records who made it, and no actor was given")
    installed_path = installed_path or INSTALLED
    H = H or _script()
    fresh = plan(H, installed_path)
    if fresh["fingerprint"] != fingerprint:
        raise Refused("the measurement moved since the preview (a heartbeat arrived, or a device "
                      "changed): nothing was written; preview again")
    if not fresh["needs"]:
        raise Refused("every installed window still tells one missed heartbeat from two: "
                      "nothing was written (a write costs a Grafana restart)")
    os.makedirs(os.path.dirname(fresh["written_path"]), exist_ok=True)
    write_atomic(fresh["written_path"], fresh["text"])
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "actor": actor,
           "fingerprint": fingerprint, "path": fresh["written_path"],
           "windows": {r["device"]: (r["new"] or {}).get("window") for r in fresh["rows"]},
           "changes": fresh["changes"]}
    recorded = True
    try:
        with open_secure(_record_path(), "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError as exc:
        log.error("heartbeat re-measure: the file was written and the record could not be: %s", exc)
        recorded = False
    return {"outcome": "written", "path": fresh["written_path"], "changes": fresh["changes"],
            "recorded": recorded, "host_step": host_step(fresh["written_path"], installed_path)}


def state(written_path: str = "", installed_path: str = "") -> dict:
    """``{"written", "installed", "pending"}``: whether the file the app wrote
    is the one Grafana loads (by hash). Pending until the host step is done."""
    written_path = written_path or _script().OUT
    installed_path = installed_path or INSTALLED
    w, i = _read(written_path), _read(installed_path)
    return {"written": _sha(w), "installed": _sha(i),
            "pending": bool(w) and _sha(w) != _sha(i)}
