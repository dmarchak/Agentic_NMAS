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
import logging
import os
import re
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


#: The record's store on the records database (K31: one file for the installation).
STORE = "heartbeat_rules"


def records() -> dict:
    """Every re-measure written from the app, oldest first: ``{"rows", "error"}``; an
    unreadable record is its error, never no rows (C360: History's source). From its file or,
    once moved, the records database (K31)."""
    from modules import records_migrate

    got = records_migrate.store_rows(STORE, _record_path())
    if got["state"] == "unreadable":
        return {"rows": [], "error": f"the record cannot be read ({got['error']})"}
    return {"rows": got["rows"], "error": ""}


def last_written() -> dict:
    """The newest record of a re-measure written from the app, or {}."""
    got = records()
    if got["error"]:
        return {"error": got["error"]}
    return got["rows"][-1] if got["rows"] else {}


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
    from modules.device_logs import NoSyslogJob

    try:
        job = H.syslog_job(loki)                      # C963: measured, never named
    except NoSyslogJob as exc:
        raise Refused(f"the syslog job could not be measured from {loki}: {exc} (a window "
                      "measured from a guessed job is a guess)") from exc
    restarts, note = H.prometheus_restarts(hosts)
    got = read_each(lambda h: H.gaps_from(H.loki_arrivals(loki, h, query=H.query_for(h, job)),
                                          H.loki_arrivals(loki, h,
                                                          query=H.config_query_for(h, job)),
                                          restarts.get(h, ())),
                    hosts, name="heartbeat-remeasure")
    failed = next((g for g in got if isinstance(g, Failed)), None)
    if failed is not None:
        raise Refused(f"Loki could not be read for every device ({failed.error}): a window "
                      "computed from the devices that answered is a guess about the rest")
    fresh = H.windows(dict(zip(hosts, got)), heartbeat)
    try:
        doc = H.build(fresh, uid, heartbeat, job)
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
            "bound": {r["device"]: _bound(r["new"]) for r in rows if r["new"]},
            "installed_text": installed_text,
            "installed_sha": _sha(installed_text), "written_path": H.OUT,
            "installed_path": installed_path}


def _bound(new: dict) -> str:
    """What a confirm of one device is bound to: the window it writes and its basis, never the
    gap counts in the rule's description, which move on every heartbeat (C1482: with ten devices
    at 300 s one arrives about every 30 s, and a measure takes 10 to 15 s, so a confirm bound to
    the whole file never matched)."""
    return f"{(new or {}).get('window')} s {(new or {}).get('basis')}"


def _picked_text(fresh: dict, picked: list, H) -> str:
    """The rules file for a PICKED write: each picked device's new rule, every other device's
    INSTALLED rule as Grafana runs it now (byte for byte through the YAML), and no rule for a
    device the generator no longer measures (retired, or no longer told to heartbeat), as the
    whole-file write drops it. A device neither picked nor installed gets no rule."""
    import yaml

    new_doc = yaml.safe_load(fresh["text"]) or {}
    old_doc = yaml.safe_load(fresh.get("installed_text") or "") or {}

    def by_device(doc):
        return {r.get("labels", {}).get("device"): r
                for g in doc.get("groups") or [] for r in g.get("rules") or []}

    new_rules, old_rules = by_device(new_doc), by_device(old_doc)
    rules = [new_rules[d] if d in picked else old_rules[d]
             for d in sorted(new_rules) if d in picked or d in old_rules]
    group = dict((new_doc.get("groups") or [{}])[0], rules=rules)
    return H.render(dict(new_doc, groups=[group]))


#: Every heartbeat rule's uid starts so (`nmas-heartbeat-rules`' `rule_for`): the range a
#: written delete file may name (C1419).
UID_PREFIX = "nmas-hb-"
#: The one install step for a generated rules file and its delete file (C1419).
from modules.grafana_rule_deletes import INSTALL_STEP  # noqa: E402


def host_step(written_path: str, installed_path: str = "") -> str:
    """The ONE host step, every value filled in: install the written file over the one Grafana
    loads, and its delete file when there is one (C1419), restart Grafana, prove the deleted
    rules gone and every generated rule present, then remove the delete file."""
    installed_path = installed_path or INSTALLED
    return f"bash {INSTALL_STEP} heartbeat {written_path} {installed_path}"


def _write_deletes(text: str, written_path: str, installed_path: str, live=...) -> dict:
    """Write the delete file beside *written_path* for the rules *text* no longer generates
    (`grafana_rule_deletes`, C1419). ``{"uids", "path", "said"}``."""
    import yaml

    from modules import grafana_rule_deletes as GD

    got = GD.plan(yaml.safe_load(text) or {}, UID_PREFIX, installed_path, live=live)
    return {"uids": got["uids"], "path": GD.write(written_path, got["uids"]),
            "said": got["said"]}


def apply(fingerprint: str, actor: str, H=None, installed_path: str = "",
          picked=None, bound=None) -> dict:
    """Measure again, refuse a moved plan, write the generated file and record
    it. Returns the host step that installs it.

    *picked* (C1482, the page's ticks): only those devices' new windows are written, each bound
    to the window and basis the preview showed (*bound*), and every other device keeps its
    installed rule. Without it the whole file is written, bound to the whole preview."""
    from modules.filestore import write_atomic

    if not actor:
        raise Refused("a re-measure records who made it, and no actor was given")
    installed_path = installed_path or INSTALLED
    H = H or _script()
    fresh = plan(H, installed_path)
    if picked is None:
        if fresh["fingerprint"] != fingerprint:
            raise Refused("the measurement moved since the preview (a heartbeat arrived, or a "
                          "device changed): nothing was written; preview again")
        if not fresh["needs"]:
            raise Refused("every installed window still tells one missed heartbeat from two: "
                          "nothing was written (a write costs a Grafana restart)")
        text, written = fresh["text"], {r["device"] for r in fresh["rows"] if r["new"]}
    else:
        picked = sorted({str(p) for p in picked if str(p).strip()})
        if not picked:
            raise Refused("no device was ticked: nothing was written")
        bound = bound or {}
        for device in picked:
            if device not in fresh["bound"]:
                raise Refused(f"{device} is not measured now (not told to heartbeat, or gone): "
                              "nothing was written; preview again")
            if bound.get(device) != fresh["bound"][device]:
                raise Refused(f"{device}'s window moved since the preview: previewed "
                              f"{bound.get(device) or 'nothing'}, measured now "
                              f"{fresh['bound'][device]}; nothing was written; preview again")
        text, written = _picked_text(fresh, picked, H), set(picked)
    os.makedirs(os.path.dirname(fresh["written_path"]), exist_ok=True)
    write_atomic(fresh["written_path"], text)
    deletes = _write_deletes(text, fresh["written_path"], installed_path)
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "actor": actor,
           "fingerprint": fingerprint if picked is None else _sha(text),
           "path": fresh["written_path"],
           "windows": {r["device"]: (r["new"] or {}).get("window") for r in fresh["rows"]
                       if r["device"] in written},
           "picked": picked, "changes": fresh["changes"], "deletes": deletes["uids"]}
    recorded = True
    try:
        from modules import records_migrate

        records_migrate.store_append(STORE, _record_path(), row)
    except Exception as exc:                          # noqa: BLE001 (said: recorded False)
        log.error("heartbeat re-measure: the file was written and the record could not be: %s", exc)
        recorded = False
    return {"outcome": "written", "path": fresh["written_path"], "changes": fresh["changes"],
            "recorded": recorded, "host_step": host_step(fresh["written_path"], installed_path),
            "deletes": deletes["uids"], "deletes_said": deletes["said"]}


def device_uid(hostname: str) -> str:
    """The uid `nmas-heartbeat-rules` gives *hostname*'s rule (its `rule_for`)."""
    return (UID_PREFIX + re.sub(r"[^A-Za-z0-9_-]", "-", hostname))[:40]


def drop_plan(hostname: str, H=None, written_path: str = "", installed_path: str = "",
              live=...) -> dict:
    """What removing *hostname*'s rule from the generated rules would do, reading only
    (retirement, C1338): the rules are read from the file written for installing (the
    script's OUT) when there is one, else from the file Grafana loads. ``{"state", "window",
    "written_path", "installed_path", "source", "text", "fingerprint", "host_step",
    "error"}``; *state* is ``names`` (a rule names it: *text* is the file without it),
    ``grafana`` (no file names it and Grafana still runs its rule, which it keeps until a
    file names it under ``deleteRules``, C1419: *text* is the file as it is, and the delete
    file is the work), ``none``, ``last`` (it is the only rule: a file with no rules alerts
    on nothing and is never written), ``absent`` (neither file is here) or ``unreadable``.
    *live* (tests) replaces the read of Grafana's own rules: a set, or None."""
    import yaml

    H = H or _script()
    written_path = written_path or H.OUT
    installed_path = installed_path or INSTALLED
    out = {"state": "absent", "window": None, "written_path": written_path,
           "installed_path": installed_path, "source": "", "text": "", "fingerprint": "",
           "host_step": host_step(written_path, installed_path), "error": ""}
    source = written_path if os.path.exists(written_path) else installed_path
    text = _read(source)
    if text is None:
        return out
    out["source"] = source
    try:
        doc = yaml.safe_load(text) or {}
        rules = H.installed(doc)
    except Exception as exc:                          # noqa: BLE001 - said as unreadable
        return dict(out, state="unreadable", error=f"{source}: {type(exc).__name__}: {exc}")
    if hostname not in rules:
        if live is ...:
            from modules import grafana_rule_deletes as GD
            live, _why = GD.live_uids(UID_PREFIX)
        uid = device_uid(hostname)
        if live and uid in live:
            return dict(out, state="grafana", uid=uid, text=text, fingerprint=_sha(text + uid))
        return dict(out, state="none")
    out["window"] = rules[hostname][0]
    if len(rules) == 1:
        return dict(out, state="last")
    for group in doc.get("groups") or []:
        group["rules"] = [r for r in group.get("rules") or []
                          if (r.get("labels") or {}).get("device") != hostname]
    new = H.render(doc)
    return dict(out, state="names", text=new, fingerprint=_sha(new))


def drop_device(hostname: str, fingerprint: str, *, actor: str, why: str, H=None,
                written_path: str = "", installed_path: str = "") -> dict:
    """Remove *hostname*'s rule as :func:`drop_plan` previewed it: planned again and refused
    when it moved, written where the re-measure writes (never the installed file, which is
    root's), and recorded beside the re-measures with who and why. ``{"ok", "error",
    "path", "host_step", "recorded"}``; the host step installs it, as a re-measure's does."""
    from modules.filestore import write_atomic

    if not actor:
        return {"ok": False, "error": "a removal records who made it, and no actor was given"}
    got = drop_plan(hostname, H, written_path, installed_path)
    if got["state"] == "none":
        return {"ok": True, "error": "", "path": got["written_path"], "recorded": False,
                "host_step": got["host_step"]}
    if got["state"] not in ("names", "grafana") or got["fingerprint"] != fingerprint:
        return {"ok": False, "error": (
            f"the heartbeat rules moved since the preview ({got['state']}, "
            f"{got['fingerprint'] or 'no file'} against {fingerprint}): nothing was written")}
    os.makedirs(os.path.dirname(got["written_path"]), exist_ok=True)
    write_atomic(got["written_path"], got["text"])
    deletes = _write_deletes(got["text"], got["written_path"], got["installed_path"])
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "actor": actor,
           "fingerprint": got["fingerprint"], "path": got["written_path"],
           "windows": {}, "changes": 1, "removed": [hostname], "why": why,
           "deletes": deletes["uids"]}
    recorded = True
    try:
        from modules import records_migrate

        records_migrate.store_append(STORE, _record_path(), row)
    except Exception as exc:                          # noqa: BLE001 (said: recorded False)
        log.error("heartbeat rules: %s's rule was removed and the record could not be: %s",
                  hostname, exc)
        recorded = False
    return {"ok": True, "error": "", "path": got["written_path"], "recorded": recorded,
            "host_step": got["host_step"], "deletes": deletes["uids"],
            "deletes_said": deletes["said"]}


def state(written_path: str = "", installed_path: str = "") -> dict:
    """``{"written", "installed", "pending"}``: whether the file the app wrote
    is the one Grafana loads (by hash). Pending until the host step is done."""
    written_path = written_path or _script().OUT
    installed_path = installed_path or INSTALLED
    w, i = _read(written_path), _read(installed_path)
    return {"written": _sha(w), "installed": _sha(i),
            "pending": bool(w) and _sha(w) != _sha(i)}
