"""The device page in the redesign (the spike, NSOT_GUI_BRIEF 9b; the operator
approved it 2026-09-30): what its Overview and Monitoring tab read, from
records the app already keeps, never a second copy of them.

Every fact names its source and its age, so a stale one reads as stale:
- **answering** is the reachability reader's stored value (C92);
- **intent** and **golden** are the list repository's commits (C104: what is
  COMMITTED, never the working tree);
- **drift** is the drift checker's last run for this list;
- **freshness** is the freshness reader's stored comparison;
- **reboot-safe** is the startup check's last run (C53);
- **alerts** are the Grafana reader's stored instances naming this device.

A device page reads ONE device, so its git reads are one device's work on a
person's request (the scale rule forbids per-device work per request across a
FLEET). The Monitoring tab's dashboards come from the grafana-dashboards
reader; only its panel queries are asked of Grafana while the page is open.
"""

import logging
import re
import time

from modules import panels

log = logging.getLogger(__name__)


class NoSuchDevice(LookupError):
    """No device by that name in the list."""


def _iso(ts):
    if ts is None:
        return None
    if isinstance(ts, str):
        return ts
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def find_device(name: str, ref=None):
    """(list reference, device row) for *name* in the active list, matched
    exactly (case-insensitive), never a first fuzzy hit."""
    from modules.device import load_saved_devices
    from modules.nsot import listref

    ref = ref or listref.active()
    for dev in load_saved_devices(ref.csv_path):
        if (dev.get("hostname") or "").lower() == (name or "").lower():
            return ref, dev
    raise NoSuchDevice(f"no device named {name!r} in the list {ref.name!r}")


def _cached(reader: str):
    """A reader's last good value and its time, or (None, why)."""
    from modules import reader_job

    got = reader_job.read_cached(reader)
    good = ((got.get("doc") or {}).get("last_good") or {})
    if got["state"] != "ok" or not good:
        return None, None, got.get("why") or "the reader has not stored a value yet"
    return good.get("value") or {}, good.get("value_at"), ""


def answering(dev: dict) -> dict:
    """The reachability reader's word on this device."""
    value, at, why = _cached("reachability")
    if value is None:
        return {"state": "unknown", "text": "not probed yet", "why": why}
    row = (value.get("devices") or {}).get(dev.get("ip"))
    if not row:
        return {"state": "unknown", "text": "not probed yet", "why": "the reader has no row for it"}
    return {"state": "ok" if row.get("answering") else "danger",
            "text": "Answering" if row.get("answering") else "Not answering",
            "since": row.get("since"), "checked_at": row.get("checked_at"),
            "last_result": row.get("last_result"), "value_at": at}


def _last_commit(repo: str, rel: str) -> dict:
    from modules.nsot import repo as R

    rc, out, _ = R.git(repo, "log", "-1", "--format=%h%x1f%cI%x1f%(trailers:key=Source,valueonly)"
                       "%x1f%(trailers:key=Actor,valueonly)", "--", rel)
    if rc != 0 or not out.strip():
        return {}
    parts = out.strip().split("\x1f")
    return {"sha": parts[0], "at": parts[1], "source": (parts[2] if len(parts) > 2 else "").strip(),
            "actor": (parts[3] if len(parts) > 3 else "").strip()}


def records(ref, dev: dict) -> dict:
    """The committed intent and golden, each its last commit or absent."""
    host = dev.get("hostname")
    return {"intent": _last_commit(ref.repo_dir, f"host_vars/{host}.yml"),
            "golden": _last_commit(ref.repo_dir, f"golden/{host}.cfg")}


_CHASSIS = re.compile(r"^! Chassis type: *(\S.*?)\s*$", re.M)
_UDI = re.compile(r"^license udi pid (\S+)", re.M)
_IMAGE = re.compile(r"^! Cisco IOS Software, (\S+) Software", re.M)


def model_from_golden(text: str) -> tuple:
    """(model, basis) from a committed golden's own lines, or ("", why not).

    The capture header carries the chassis (`! Chassis type: C8000V`); a vIOS
    switch reports only `processor` there, so its image line names it
    (`vios_l2`), said as such. NetBox is not asked: its import records
    `Unknown` for a model it builds from a golden (`_parse_facts_from_config`),
    so reading it back would name nothing."""
    if not text:
        return "", "no committed golden to read it from"
    m = _CHASSIS.search(text)
    if m and m.group(1).lower() != "processor":
        return m.group(1), "the golden's Chassis type line"
    m = _UDI.search(text)
    if m:
        return m.group(1), "the golden's license udi line"
    m = _IMAGE.search(text)
    if m:
        return m.group(1), "the golden's image line (the device reports no chassis model)"
    return "", "the golden names no model"


def hardware(ref, dev: dict) -> dict:
    """Platform and model, each with where it came from: the platform from the
    inventory's `platform` column (else the manifest), the model from the
    committed golden."""
    from modules.nsot import manifest
    from modules.nsot import repo as R

    platform, platform_from = (dev.get("platform") or "").strip(), "the inventory"
    entry = None
    try:
        _ident, entry = manifest.find_by_name(ref.repo_dir, dev.get("hostname"))
    except Exception as exc:                     # noqa: BLE001
        log.info("device page: manifest unreadable for %s (%s)", dev.get("hostname"),
                 type(exc).__name__)
    if not platform and entry and entry.get("platform"):
        platform, platform_from = entry["platform"], "the manifest"
    golden = {"text": None, "commit": ""}
    if entry:
        try:
            golden = R.committed_golden_for(ref.repo_dir, entry)
        except Exception as exc:                 # noqa: BLE001
            log.info("device page: golden unreadable for %s (%s)", dev.get("hostname"),
                     type(exc).__name__)
    model, basis = model_from_golden(golden.get("text") or "")
    return {"platform": platform, "platform_from": platform_from if platform else "",
            "model": model, "model_from": basis,
            "model_commit": (golden.get("commit") or "")[:7] if model else ""}


def checks(ref, dev: dict) -> list:
    """The checks the Overview draws, each with its state, words, source and
    the time of the value it rests on. An unreadable source is its own row,
    never a pass."""
    host, ip = dev.get("hostname"), dev.get("ip")
    out = []

    # Drift: this list's last run.
    try:
        from modules import drift_check
        last = (drift_check._load_state(ref.name) or {}).get("last_result") or {}
    except Exception as exc:                     # noqa: BLE001
        last = {"_error": f"the drift record could not be read ({type(exc).__name__})"}
    if last.get("_error"):
        out.append({"name": "Drift", "state": "unknown", "text": last["_error"]})
    elif not last:
        out.append({"name": "Drift", "state": "unknown", "text": "no drift run recorded for this list"})
    else:
        drifted = {d.get("hostname"): d.get("diff_lines") for d in last.get("drifted_devices") or []}
        skipped = [s if isinstance(s, str) else (s or {}).get("hostname") for s in last.get("skipped") or []]
        if host in drifted:
            out.append({"name": "Drift", "state": "warn", "at": last.get("timestamp"),
                        "text": f"differs from its golden by {drifted[host]} line(s)"})
        elif host in skipped:
            out.append({"name": "Drift", "state": "unknown", "at": last.get("timestamp"),
                        "text": "skipped by the last run"})
        else:
            out.append({"name": "Drift", "state": "ok", "at": last.get("timestamp"),
                        "text": "clean at the last run"})

    # Freshness: is Oxidized's copy the approved one.
    value, at, why = _cached("freshness")
    rows = (((value or {}).get("lists") or {}).get(ref.name) or {}).get("devices") or []
    row = next((r for r in rows if r.get("device") == host), None)
    if value is None or row is None:
        out.append({"name": "Freshness", "state": "unknown",
                    "text": why or "the freshness reader holds no row for this device"})
    else:
        verdict = row.get("verdict") or "?"
        state = {"match": "ok", "poll_race": "ok", "authorised": "ok",
                 "unapproved": "danger"}.get(verdict, "unknown")
        words = {"match": "Oxidized's copy is the approved one",
                 "poll_race": "Oxidized's copy predates the approved change (it corrects at the next poll)",
                 "authorised": "a divergence a person authorised",
                 "unapproved": "Oxidized's copy carries a change nobody approved",
                 "inconclusive": "could not be compared"}.get(verdict, verdict)
        out.append({"name": "Freshness", "state": state, "at": at, "text": words})

    # Reboot-safe: the startup check's last run.
    try:
        from modules.nsot import startup_check
        res = startup_check.read_results()
    except Exception as exc:                     # noqa: BLE001
        res = {"_error": f"the startup check's record could not be read ({type(exc).__name__})"}
    srow = next((d for d in (res or {}).get("devices") or [] if d.get("device") == host), None)
    if res.get("_error"):
        out.append({"name": "Reboot-safe", "state": "unknown", "text": res["_error"]})
    elif srow is None:
        out.append({"name": "Reboot-safe", "state": "unknown", "text": "the hourly startup check has no row for it"})
    else:
        st = srow.get("state")
        out.append({"name": "Reboot-safe",
                    "state": {"persisted": "ok", "not_persisted": "danger"}.get(st, "unknown"),
                    "at": _iso(res.get("at")),
                    "text": ("its startup config carries its credential" if st == "persisted"
                             else (srow.get("detail") or st or "unknown"))})

    # Alerts: Grafana's instances naming this device, by label, line or address.
    value, at, why = _cached("grafana-alerts")
    if value is None:
        out.append({"name": "Alerts", "state": "unknown", "text": why})
    else:
        mine = [i for i in value.get("instances") or []
                if i.get("kind") in ("condition", "no_data", "error")
                and (i.get("device") == host or i.get("address") == ip)]
        out.append({"name": "Alerts", "state": "danger" if mine else "ok", "at": at,
                    "text": (", ".join(sorted({i.get("rule") or "?" for i in mine})) if mine
                             else "none firing")})
    return out


# ---------------------------------------------------------------- Monitoring

def device_dashboard_settings() -> dict:
    from modules.settings_schema import get_setting

    return {"uid": (get_setting("grafana_device_dashboard_uid", "") or "").strip(),
            "variable": (get_setting("grafana_device_variable", "device") or "device").strip(),
            "value_from": get_setting("grafana_device_variable_value", "hostname") or "hostname"}


def variable_value(dev: dict, value_from: str) -> str:
    return dev.get("ip") if value_from == "address" else dev.get("hostname")


_LABEL_VALUES = re.compile(r"^\s*label_values\(\s*(?:(?P<sel>.+?)\s*,\s*)?(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*$")

_VALUES_CACHE: dict = {}
VALUES_CACHE_SECONDS = 60


def device_variable_state(dashboard: dict, variable: str, value: str, values_fill: dict,
                          datasources: list, client=None, clock=time.time) -> dict:
    """Does the dashboard's device variable list this device? Asked of
    Prometheus through Grafana's data-source proxy with the variable's own
    query, cached a minute. Five answers, each drawn in its own words:
    listed, none (the variable lists nothing at all, C232), not_listed,
    unparsed (a query this reads no further), could_not_ask."""
    v = panels.variable_of(dashboard, variable)
    q = (v or {}).get("query") or ""
    m = _LABEL_VALUES.match(q)
    if not m:
        return {"state": "unparsed", "query": q}
    sel = panels.interpolate(m.group("sel") or "", values_fill)
    label = m.group("label")
    ds = panels.default_datasource(datasources, "prometheus")
    key = (ds.get("uid"), sel, label)
    hit = _VALUES_CACHE.get(key)
    if hit and clock() - hit[0] < VALUES_CACHE_SECONDS:
        values = hit[1]
    else:
        if client is None:
            from modules.integrations.grafana import GrafanaIntegration
            client = GrafanaIntegration()
        params = {"match[]": sel} if sel else {}
        got = client._get(f"api/datasources/proxy/uid/{ds.get('uid')}/api/v1/label/{label}/values", **params)
        if not got.get("ok"):
            return {"state": "could_not_ask", "query": q, "error": got.get("error")}
        values = (got["response"].json() or {}).get("data") or []
        _VALUES_CACHE[key] = (clock(), values)
    if not values:
        return {"state": "none", "query": q, "label": label, "selector": sel}
    if value not in values:
        return {"state": "not_listed", "query": q, "label": label, "count": len(values)}
    return {"state": "listed", "query": q, "label": label, "count": len(values)}


def monitoring(dev: dict, chosen_uid: str = "", range_text: str = "1h", client=None) -> dict:
    """Everything the Monitoring tab draws, or the state that replaces it:
    no dashboard set, the dashboards not read yet, the configured UID gone,
    no such variable, the variable listing nothing, or the panels."""
    cfg = device_dashboard_settings()
    value, at, why = _cached("grafana-dashboards")
    out = {"settings": cfg, "value_at": at, "range": range_text, "offered": [], "state": "ok"}
    if value is None:
        out.update(state="not_read", why=why)
        return out
    dashboards, datasources = value.get("dashboards") or {}, value.get("datasources") or []
    out["offered"] = [{"uid": d["uid"], "title": d["title"]}
                      for d in panels.dashboards_with_variable(dashboards, cfg["variable"])]
    out["total_dashboards"] = len(dashboards)
    offered = {d["uid"] for d in out["offered"]}
    # The rest, each with why: a one-option selector reads as broken unless it
    # says the others exist and cannot show one device (the operator, 2026-09-30).
    out["not_offered"] = sorted(
        ({"uid": uid, "title": d.get("title") or uid,
          "why": (f"no variable named {cfg['variable']}; its variables: "
                  + (", ".join(v.get("name") or "?" for v in d.get("variables") or []) or "none"))}
         for uid, d in dashboards.items() if uid not in offered),
        key=lambda d: d["title"].lower())
    uid = chosen_uid or cfg["uid"]
    if not uid:
        out.update(state="not_set")
        return out
    dash = dashboards.get(uid)
    if dash is None:
        out.update(state="uid_gone", uid=uid)
        return out
    out.update(dashboard={"uid": uid, "title": dash["title"]}, is_default=(uid == cfg["uid"]))
    if not panels.variable_of(dash, cfg["variable"]):
        out.update(state="no_variable",
                   variables=[v.get("name") for v in dash.get("variables") or []])
        return out
    try:
        seconds = panels.parse_range(range_text)
        panels.check_range(seconds, "prometheus")
    except panels.RangeRefused as exc:
        out.update(state="range_refused", why=str(exc))
        return out
    device_value = variable_value(dev, cfg["value_from"])
    fill = panels.variable_values(dash, cfg["variable"], device_value, datasources)
    out["variable_state"] = device_variable_state(dash, cfg["variable"], device_value, fill,
                                                  datasources, client=client)
    drawn, left_out = panels.split_device_panels(dash, cfg["variable"])
    out.update(device_value=device_value, drawn=drawn, left_out=left_out,
               layout=panels.layout(drawn),
               seconds=seconds, step=panels.step_for(seconds), range_words=panels.describe(seconds))
    return out


def panel_data(dev: dict, uid: str, panel_id: int, range_text: str, client=None) -> tuple:
    """(payload, http status) for one panel, drawn by the browser. Only a panel
    the dashboard holds AND that selects the device; the query is the
    dashboard's, never the browser's."""
    cfg = device_dashboard_settings()
    value, _at, why = _cached("grafana-dashboards")
    if value is None:
        return {"ok": False, "error": f"the dashboards are not read yet: {why}"}, 503
    dash = (value.get("dashboards") or {}).get(uid)
    if dash is None:
        return {"ok": False, "error": f"Grafana holds no dashboard with UID {uid}"}, 404
    drawn, _ = panels.split_device_panels(dash, cfg["variable"])
    panel = next((p for p in drawn if p.get("id") == panel_id), None)
    if panel is None:
        return {"ok": False, "error": f"panel {panel_id} is not a device panel of {uid}"}, 404
    try:
        seconds = panels.parse_range(range_text)
        fill = panels.variable_values(dash, cfg["variable"], variable_value(dev, cfg["value_from"]),
                                      value.get("datasources") or [])
        default_ds = panels.default_datasource(value.get("datasources") or [], "prometheus")
        body = panels.build_request(panel, dash, fill, seconds, default_ds)
    except panels.RangeRefused as exc:
        return {"ok": False, "error": str(exc)}, 400
    if client is None:
        from modules.integrations.grafana import GrafanaIntegration
        client = GrafanaIntegration()
    got = client.query(body)
    if not got.get("ok"):
        return {"ok": False, "error": f"Grafana: {got.get('error')}"}, 502
    errors = panels.answer_errors(got["body"])
    payload = panels.render_payload(panel, got["body"], seconds)
    payload["errors"] = errors
    payload["read_at"] = _iso(time.time())
    return payload, 200
