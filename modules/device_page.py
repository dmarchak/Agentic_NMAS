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


def find_pending(name: str, ref=None):
    """(list reference, pending row) for a device onboarded and not yet
    reached (the manifest's `pending_devices`), matched exactly, or None. A
    pending device is in no inventory BY DESIGN (it has never answered), so
    `find_device` cannot find it and the page draws its onboarding state
    instead (NSOT_GUI_BRIEF 3.3)."""
    from modules.nsot import listref, manifest

    ref = ref or listref.active()
    for p in manifest.pending_devices(ref.repo_dir):
        if (p.get("name") or "").lower() == (name or "").lower():
            return ref, p
    return None


def _cached(reader: str, list_name: str = ""):
    """A reader's last good value and its time, or (None, why). *list_name* reads that
    network's configuration of a reader that reads one per configuration (P.8 step 5)."""
    from modules import reader_job

    got = (reader_job.read_cached_for(reader, list_name) if list_name
           else reader_job.read_cached(reader))
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
    """The committed intent and golden, each its last commit or absent, and
    the network's monitoring profile the intent inherits (the operator,
    2026-09-30: "Committed intent e2703d7, 5 d ago" read as unchanged for five
    days while r6's EFFECTIVE intent changed that day through the profile)."""
    from modules.nsot import profile as _profile

    from modules import device_list

    host = dev.get("hostname")
    golden = _last_commit(ref.repo_dir, f"golden/{host}.cfg")
    # WHEN IT WAS LAST MEASURED, beside when its golden last changed (2026-10-02): a Save
    # All that found it unchanged confirms the golden and moves only this. The same
    # reader as the Devices list; a golden commit is a measurement too.
    measured, err = device_list.last_measured(ref.repo_dir)
    m = measured.get(host)
    g_at = _epoch(golden.get("at") or "") if golden else 0
    if golden and (m is None or g_at > m["at"]):
        m = {"at": g_at, "sha": golden["sha"], "how": device_list.SOURCE_WORDS.get(
            golden.get("source") or "", golden.get("source") or "a save"),
             "changed": True, "baseline": False}
    return {"intent": _last_commit(ref.repo_dir, f"host_vars/{host}.yml"),
            "profile": _last_commit(ref.repo_dir, _profile.PROFILE_REL),
            "golden": golden,
            "measured": ({"iso": _iso(m["at"]), "sha": m["sha"],
                          "words": device_list.measured_words(m)} if m and not err else None),
            "measured_error": err}


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
    committed golden or the device's own sysDescr (`model_of`)."""
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
    model, basis, from_golden = model_of(golden.get("text") or "", dev.get("hostname") or "")
    return {"platform": platform, "platform_from": platform_from if platform else "",
            "model": model, "model_from": basis,
            "model_commit": (golden.get("commit") or "")[:7] if from_golden else ""}


def model_of(text: str, hostname: str, known: tuple = None) -> tuple:
    """``(model, basis, from the golden?)``. A chassis the golden names
    (its capture header, else its udi line) is the most exact; else the
    device's own sysDescr as the platform-facts reader stored it (C426: a
    golden captured without its header names nothing, and an unknown model
    folds no platform rule); else the golden's image line; else why not."""
    from modules.readers import platform_facts

    model, basis = model_from_golden(text)
    if model and not basis.startswith("the golden's image line"):
        return model, basis, True
    seen, seen_why = platform_facts.measured(hostname, known)
    if seen:
        return seen, seen_why, False
    if model:
        return model, basis, True
    return "", f"{basis}, and {seen_why}", False


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

    # Intent: does the committed golden match what the device SHOULD run (its
    # own intent and what it inherits from the profile)? Drift says device
    # against golden; this says golden against intent, and the two together
    # are the difference plan 1c promises (the operator, 2026-09-30: r6 read
    # "Drift: clean" while carrying `cdp run` its intent no longer has).
    out.append(intent_check(ref, dev))

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
                             else (srow.get("detail") or st or "unknown") if st == "not_persisted"
                             else "the hourly check could not read it ("
                                  + startup_check.brief(srow.get("detail") or st or "unknown")
                                  + "); it reads it again at the next run")})

    # Alerts: Grafana's instances naming this device, by label, line or address.
    value, at, why = _cached("grafana-alerts")
    if value is None:
        out.append({"name": "Alerts", "state": "unknown", "text": why})
    else:
        mine = [i for i in value.get("instances") or []
                if i.get("kind") in ("condition", "no_data", "error")
                and (i.get("device") == host or i.get("address") == ip)]
        acked, open_ = _acknowledged_alerts(mine, value.get("bands") or {})
        words = [f"{i.get('rule') or '?'} (acknowledged by {a.get('by')}, within its band: "
                 f"{reading:.3g} at or under {float(a['band']):.3g})" for i, a, reading in acked]
        out.append({"name": "Alerts", "state": "danger" if open_ else "ok", "at": at,
                    "text": ("; ".join(sorted({i.get("rule") or "?" for i in open_}
                                              | set(words))) if mine else "none firing")})
    return out


def _acknowledged_alerts(instances: list, bands: dict):
    """``(acknowledged, open)``: each firing instance a person acknowledged within its
    measured band, and inside it now (C433, the same judgement Needs attention makes:
    `attention._without_acknowledged`), with the acknowledgement and the reading; and the
    rest. An unreadable record acknowledges nothing."""
    from modules import acknowledgements as ACK
    from modules.alert_bands import series_key

    got = ACK.read()
    if got["state"] == "unreadable" or not instances:
        return [], list(instances)
    acked, open_ = [], []
    for i in instances:
        series = series_key(i.get("rule_uid"), i.get("labels"))
        a = ACK.covering(f"grafana:series:{series}", series, got["rows"])
        reading = (bands.get(series) or {}) if a else {}
        if a and a.get("band") is not None and not reading and a.get("value") is not None:
            reading = {"value": float(a["value"]), "in_band": float(a["value"]) <= float(a["band"])}
        if a and a.get("band") is not None and reading.get("in_band"):
            acked.append((i, a, float(reading["value"])))
        else:
            open_.append(i)
    return acked, open_


def intent_check(ref, dev: dict) -> dict:
    """The Overview's Intent row, from the deploy plan's own comparison
    (`intent_match`) of the COMMITTED golden against effective intent: each
    line on the device that intent lacks, and each in intent the device lacks,
    masked on the way out."""
    from modules import redact
    from modules.nsot import manifest
    from modules.nsot import repo as R
    from modules.nsot.intent_match import explain, intent_match

    host = dev.get("hostname")
    try:
        _ident, entry = manifest.find_by_name(ref.repo_dir, host)
        golden = R.committed_golden_for(ref.repo_dir, entry) if entry else {}
    except Exception as exc:                     # noqa: BLE001
        return {"name": "Intent", "state": "unknown",
                "text": f"the committed golden could not be read ({type(exc).__name__})"}
    if not golden.get("text"):
        return {"name": "Intent", "state": "unknown",
                "text": "no committed golden to compare with its intent"}
    r = intent_match(ref.repo_dir, ref.name, host, golden["text"],
                     platform=(dev.get("platform") or "").strip())
    on_device = [redact.redact_text(l[2:]) for l in r["lines"] if l.startswith("- ")]
    in_intent = [redact.redact_text(l[2:]) for l in r["lines"] if l.startswith("+ ")]
    return {"name": "Intent", "state": {"match": "ok", "differs": "warn"}.get(r["state"], "unknown"),
            "text": explain(r), "on_device": on_device, "in_intent": in_intent,
            "commit": (golden.get("commit") or "")[:7]}


# ---------------------------------------------------------------- Monitoring

def grafana_client(list_name: str):
    """The Grafana of the network *list_name* (P.8 step 8): every live ask a page makes for
    that network goes to it, never to Default's. Default's is built as it was before lists
    had settings, so a single-network installation asks exactly what it did."""
    from modules.integrations.grafana import GrafanaIntegration
    from modules.list_settings import is_default

    return GrafanaIntegration() if is_default(list_name) else GrafanaIntegration(list_name=list_name)


def device_dashboard_settings(list_name: str) -> dict:
    """The device dashboard role of the network *list_name*: a device page passes its
    device's list (P.8 step 8; the operator, 2026-09-30: the roles are per network)."""
    from modules.list_settings import value

    return {"uid": (value(list_name, "grafana_device_dashboard_uid", "") or "").strip(),
            "variable": (value(list_name, "grafana_device_variable", "device") or "device").strip(),
            "value_from": value(list_name, "grafana_device_variable_value", "hostname")
            or "hostname"}


def variable_value(dev: dict, value_from: str) -> str:
    return dev.get("ip") if value_from == "address" else dev.get("hostname")


_LABEL_VALUES = re.compile(r"^\s*label_values\(\s*(?:(?P<sel>.+?)\s*,\s*)?(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*$")

_VALUES_CACHE: dict = {}
VALUES_CACHE_SECONDS = 60


def device_variable_state(dashboard: dict, variable: str, value: str, values_fill: dict,
                          datasources: list, client=None, clock=time.time,
                          network: str = "") -> dict:
    """Does the dashboard's device variable list this device? Asked of
    Prometheus through Grafana's data-source proxy with the variable's own
    query, cached a minute. Five answers, each drawn in its own words:
    listed, none (the variable lists nothing at all, C232), not_listed,
    unparsed (a query this reads no further), could_not_ask. The cache is keyed by
    *network* too: two Grafanas may hold a data source of the same UID."""
    v = panels.variable_of(dashboard, variable)
    q = (v or {}).get("query") or ""
    m = _LABEL_VALUES.match(q)
    if not m:
        return {"state": "unparsed", "query": q}
    sel = panels.interpolate(m.group("sel") or "", values_fill)
    label = m.group("label")
    ds = panels.default_datasource(datasources, "prometheus")
    key = (network, ds.get("uid"), sel, label)
    hit = _VALUES_CACHE.get(key)
    if hit and clock() - hit[0] < VALUES_CACHE_SECONDS:
        values = hit[1]
    else:
        client = client or grafana_client(network)
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


def streams_telemetry(ref, dev: dict) -> tuple:
    """``(True | False | None, why)``: does this device stream model-driven
    telemetry, decided from its COMMITTED configuration (a subscription),
    never from whether series exist right now: a router whose stream just
    stopped must show the failure, not hide its panels (the operator,
    2026-09-30). None when the configuration could not be read."""
    from modules import prometheus_targets as P
    from modules.monitoring_coverage import configured

    host = dev.get("hostname", "")
    try:
        text = P.read_golden(ref, host)
    except Exception as exc:                            # noqa: BLE001
        return None, f"{host}'s committed configuration could not be read ({type(exc).__name__})"
    if not text:
        return False, f"{host} has no committed configuration"
    if configured(text)["telemetry"]:
        return True, f"{host}'s configuration subscribes model-driven telemetry"
    return False, f"{host} doesn't stream model-driven telemetry (its configuration has no subscription)"


def _dashboard(stored: dict, uid: str, client=None) -> tuple:
    """``(dashboard | None, live)``: from the stored list, or, on a miss, from
    Grafana asked now (`grafana_dashboards.read_one`). *live* is ``{}`` when
    the stored list held it."""
    if uid in stored:
        return stored[uid], {}
    from modules.readers import grafana_dashboards
    try:
        live = grafana_dashboards.read_one(uid, client=client)
    except Exception as exc:                            # noqa: BLE001
        live = {"state": "unknown", "error": f"{type(exc).__name__}: {exc}"}
    return (live.get("dashboard") if live.get("state") == "found" else None), live


def monitoring(dev: dict, list_name: str, chosen_uid: str = "", range_text: str = "1h",
               client=None, streams: tuple = (None, ""), model: tuple = ("", "")) -> dict:
    """Everything the Monitoring tab draws, or the state that replaces it:
    no dashboard set, the dashboards not read yet, the configured UID gone,
    no such variable, the variable listing nothing, or the panels. All of it is the
    network *list_name*'s: its role settings, its Grafana's stored read and its Grafana."""
    cfg = device_dashboard_settings(list_name)
    client = client or grafana_client(list_name)
    value, at, why = _cached("grafana-dashboards", list_name)
    out = {"settings": cfg, "network": list_name, "value_at": at, "range": range_text, "limit_words": panels.limit_words(panels.stores((value or {}).get("datasources") or [], list_name)), "offered": [], "state": "ok"}
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
    dash, live = _dashboard(dashboards, uid, client)
    if dash is None:
        # Said only on Grafana's LIVE answer (rule 11): "gone" when it
        # answered 404, "not confirmed" when it could not be asked.
        out.update(state="uid_gone" if live.get("state") == "absent" else "uid_unconfirmed",
                   uid=uid, live=live)
        return out
    if live:
        out["live"] = live
    out.update(dashboard={"uid": uid, "title": dash["title"]}, is_default=(uid == cfg["uid"]))
    if not panels.variable_of(dash, cfg["variable"]):
        out.update(state="no_variable",
                   variables=[v.get("name") for v in dash.get("variables") or []])
        return out
    try:
        seconds = panels.parse_range(range_text)
        panels.check_range(seconds, "prometheus", panels.stores(datasources, list_name))
    except panels.RangeRefused as exc:
        out.update(state="range_refused", why=str(exc))
        return out
    device_value = variable_value(dev, cfg["value_from"])
    fill = panels.variable_values(dash, cfg["variable"], device_value, datasources)
    out["variable_state"] = device_variable_state(dash, cfg["variable"], device_value, fill,
                                                  datasources, client=client, network=list_name)
    drawn, left_out = panels.split_device_panels(dash, cfg["variable"])
    if streams[0] is None and streams[1]:
        out["streams_unknown"] = streams[1]
    folds = fold_panels(drawn, dev, dash, fill, datasources, streams=streams, model=model,
                        client=client)
    if folds:
        out["folded"] = fold_summary(dev.get("hostname", ""), folds)
    out.update(device_value=device_value, drawn=[p for p in drawn if p.get("id") not in
                                                 {f["id"] for f in folds}],
               left_out=left_out,
               layout=panels.drawn_elsewhere(panels.layout(drawn, [f["id"] for f in folds]), uid,
                                             _grafana_url(list_name)),
               seconds=seconds, step=panels.step_for(seconds), range_words=panels.describe(seconds))
    # A panel a declared platform rule explains leads, when empty, with its reason (C429).
    for cell in out["layout"]:
        if cell.get("kind") == "panel" and panels.known_limit(cell["panel"], (model or ("",))[0]):
            cell["limit"] = True
    return out


def fold_panels(drawn: list, dev: dict, dash: dict, fill: dict, datasources: list,
                streams: tuple = (None, ""), model: tuple = ("", ""), client=None) -> list:
    """The panels that do NOT APPLY to this device, each with why (the
    operator, 2026-09-30: one rule for "nothing to show here"). Three
    reasons, each declared, never inferred from an empty answer:

    - no source: a panel reading only telemetry, on a device whose COMMITTED
      configuration has no subscription (`streams_telemetry`);
    - not collected on this platform: a measured rule (`panels.PLATFORM_FOLDS`)
      matching the device's model (`model_of`: its golden, else its sysDescr), CHECKED by
      asking whether the panel's selectors match a series for the device in the last hour
      (C412): one that does is drawn, the rule wrong for it;
    - withheld: the panel's own guard holds its value back, decided by asking
      Grafana for both halves now (`panels.withheld`).

    A panel that SHOULD show data and does not never folds: a router whose
    stream stopped, an unknown model, a guard whose value is itself missing,
    or a Grafana that could not be asked. Each stays in place with its own
    words. The explanation is the panel's own sentence (its noValue),
    unchanged: it moves out of the grid, it is not rewritten."""
    host = dev.get("hostname", "")
    model_name, model_from = (model or ("", ""))[:2]
    out = []

    def fold(p, short, kind, basis, words=None, hover=None):
        # ONE visible sentence per item, its provenance on hover (C425, the operator,
        # 2026-10-04: "Up for" showed its raw PromQL; a telemetry entry gave two reasons).
        detail = p.get("no_value") or short
        out.append({"id": p.get("id"), "title": p.get("title") or "", "short": short,
                    "kind": kind, "detail": detail, "basis": basis,
                    "words": words or detail, "hover": hover or basis})

    default_ds = panels.default_datasource(datasources, "prometheus")

    def asker():
        # The device's network's Grafana, passed by `monitoring` (P.8 step 8); never a
        # default built here, which would be Default's for a device of any network.
        return client

    for p in drawn:
        if streams[0] is False and panels.telemetry_only(p):
            # The configuration's reason is the one sentence; the dashboard's, about a stream
            # that stopped, is not this device's case and goes on hover.
            reason = str(streams[1] or "it does not stream").strip()
            fold(p, "not streamed", "no_source", streams[1],
                 words=reason + ("" if reason.endswith(".") else "."),
                 hover=("The dashboard says: " + p["no_value"]) if p.get("no_value") else "")
            continue
        rule = panels.platform_fold(p, model_name)
        if rule is not None:
            # A declared fold is CHECKED, never trusted (C412): if the panel's own selectors
            # match a series for this device in the last hour, the rule is wrong for it and the
            # panel draws. Not asked is said in the fold's basis.
            try:
                got = asker().query(panels.series_request(p, dash, fill, default_ds))
                found = (panels.has_data(got.get("body") or {}, "S") if got.get("ok")
                         else None)
            except Exception as exc:                    # noqa: BLE001
                log.info("device page: %s's fold for %s could not be checked (%s)",
                         p.get("title"), host, type(exc).__name__)
                found = None
            if found:
                log.warning("device page: %s folds %s for %s (%s), and its selectors match a "
                            "series: the panel is drawn", rule.short, p.get("title"), host,
                            model_name)
                continue
            checked = (f"; no series matched {' or '.join(panels.selectors_of(p, fill))} in "
                       "the last hour" if found is False else
                       "; whether a series matches could not be asked now")
            fold(p, rule.short, "platform",
                 f"{host}'s model is {model_name} ({model_from}); {rule.basis}{checked}")
    guarded = [p for p in drawn if p.get("id") not in {f["id"] for f in out}
               and panels.guard_of(p)]
    if guarded:
        client = asker()
        for p in guarded:
            try:
                got = client.query(panels.guard_request(p, dash, fill, default_ds))
            except Exception as exc:                    # noqa: BLE001
                log.info("device page: %s's guard for %s could not be asked (%s)",
                         p.get("title"), host, type(exc).__name__)
                continue
            if got.get("ok") and panels.withheld(got.get("body") or {}):
                g = panels.guard_of(p)
                # The condition with this device's values filled (C425: `$device` showed).
                fold(p, g["short"], "withheld",
                     f"its own condition ({panels.interpolate(g['cond'], fill)}) does not hold "
                     f"for {host} now, while its value does: the dashboard withholds it by "
                     "design")
    where = {p.get("id"): ((p.get("gridPos") or {}).get("y") or 0, (p.get("gridPos") or {}).get("x") or 0)
             for p in drawn}
    return sorted(out, key=lambda f: where.get(f["id"], (0, 0)))


def fold_summary(host: str, folds: list) -> dict:
    """ONE line above the panels: the count and each reason with its panels,
    in the dashboard's order; the full explanations one level down."""
    groups = []
    for f in folds:
        g = next((g for g in groups if g["short"] == f["short"]), None)
        if g is None:
            groups.append({"short": f["short"], "titles": [f["title"]]})
        else:
            g["titles"].append(f["title"])
    parts = [(" and ".join(g["titles"]) if len(g["titles"]) < 3 else
              ", ".join(g["titles"][:-1]) + " and " + g["titles"][-1]) + f" ({g['short']})"
             for g in groups]
    n = len(folds)
    return {"count": n, "panels": folds, "groups": groups,
            "titles": [f["title"] for f in folds],
            "line": f"{n} panel{'' if n == 1 else 's'} hidden for {host}: " + ", ".join(parts)}


def panel_data(dev: dict, list_name: str, uid: str, panel_id: int, range_text: str,
               client=None, streams: tuple = (None, "")) -> tuple:
    """(payload, http status) for one panel, drawn by the browser. Only a panel
    the dashboard holds AND that selects the device; the query is the
    dashboard's, never the browser's, asked of the device's network's Grafana."""
    cfg = device_dashboard_settings(list_name)
    client = client or grafana_client(list_name)
    value, _at, why = _cached("grafana-dashboards", list_name)
    if value is None:
        return {"ok": False, "error": f"the dashboards are not read yet: {why}"}, 503
    dash, live = _dashboard(value.get("dashboards") or {}, uid, client)
    if dash is None:
        if live.get("state") == "absent":
            return {"ok": False, "error": f"Grafana answered, asked now: no dashboard with UID {uid}"}, 404
        return {"ok": False, "error": (f"{uid} is not in the stored dashboard list, and Grafana could "
                                       f"not be asked now: {live.get('error')}")}, 503
    drawn, _ = panels.split_device_panels(dash, cfg["variable"])
    panel = next((p for p in drawn if p.get("id") == panel_id), None)
    if panel is None:
        return {"ok": False, "error": f"panel {panel_id} is not a device panel of {uid}"}, 404
    if panel.get("type") not in panels.NATIVE_TYPES:
        return {"ok": False, "error": (f"panel {panel_id} is a {panel.get('type')} panel: Grafana "
                                       "draws it, this page does not")}, 400
    try:
        seconds = panels.parse_range(range_text)
        fill = panels.variable_values(dash, cfg["variable"], variable_value(dev, cfg["value_from"]),
                                      value.get("datasources") or [])
        default_ds = panels.default_datasource(value.get("datasources") or [], "prometheus")
        st = panels.stores(value.get("datasources") or [], list_name)
        body = panels.build_request(panel, dash, fill, seconds, default_ds, st)
    except panels.RangeRefused as exc:
        return {"ok": False, "error": str(exc)}, 400
    got = client.query(body)
    if not got.get("ok"):
        return {"ok": False, "error": f"Grafana: {got.get('error')}"}, 502
    errors = panels.answer_errors(got["body"])
    payload = panels.render_payload(panel, got["body"], seconds)
    payload["store"] = panels.store_words(seconds, panel, dash, fill, default_ds, st)
    payload["errors"] = errors
    # What was asked, so an empty panel says what matched nothing, the panel's own sentence on
    # hover (C412).
    payload["asked"] = panels.selectors_of(panel, fill)
    if payload.get("implausible") and panels.reads_uptime(panel):
        # A reading outside its range from sysUpTime is a restart: say when.
        try:
            probe = panels.build_request(panels.restart_panel(panel, cfg["variable"]), dash, fill,
                                         max(seconds, 7200), default_ds, st)
            back = client.query(probe)
            at = panels.last_restart(back["body"]) if back.get("ok") else None
        except Exception as exc:                      # noqa: BLE001
            log.info("panel %s: the restart time could not be read: %s", panel_id, exc)
            at = None
        if at:
            payload["implausible"]["words"] = (
                f"Restarted about {time.strftime('%H:%M', time.gmtime(at))} UTC: measuring")
            payload["implausible"]["restarted_at"] = _iso(at)
    payload["read_at"] = _iso(time.time())
    # A STOPPED STREAM STAYS VISIBLE AND RED: a telemetry-only panel with
    # nothing to draw, on a device whose configuration subscribes, is the
    # failure itself, never a neutral "no data".
    empty = (payload.get("value") is None if "value" in payload
             else not (payload.get("series") or payload.get("rows")))
    if streams[0] is True and panels.telemetry_only(panel) and empty:
        payload["no_value"] = (f"No stream: {streams[1]}, and nothing arrived for this panel in "
                               "the last 5 minutes")
        payload["no_value_kind"] = "danger"
    return payload, 200


# ---------------------------------------------------------------------------
# The Monitoring page: the FLEET dashboard (NSOT_GUI_BRIEF 14.2; the operator,
# 2026-10-01: Monitoring opens on the fleet Grafana dashboard, with the
# selector, and Coverage is a tab beside it). The same stored models, the same
# panel logic and the same renderer as the device page, with no device: every
# panel of the chosen dashboard is drawn, its variables at their own values.
# ---------------------------------------------------------------------------

def _grafana_url(list_name: str) -> str:
    """The network's Grafana address, for a link a person opens (reachable from the LAN
    only)."""
    from modules.list_settings import value
    return (value(list_name, "grafana_url", "") or "").strip()


def fleet_dashboard_uid(list_name: str) -> str:
    from modules.list_settings import value
    return (value(list_name, "grafana_fleet_dashboard_uid", "") or "").strip()


def _fleet_panels(dash: dict) -> list:
    return [p for p in dash.get("panels") or [] if p.get("type") != "row"]


def fleet_monitoring(list_name: str, chosen_uid: str = "", range_text: str = "1h",
                     client=None) -> dict:
    """Everything the Monitoring page draws for the network *list_name*, or the state that
    replaces it: the dashboards not read yet, no fleet dashboard set, the UID gone, a range
    refused, or the panels. The selector lists EVERY dashboard that network's Grafana holds;
    choosing one changes the view, never the setting."""
    default = fleet_dashboard_uid(list_name)
    client = client or grafana_client(list_name)
    value, at, why = _cached("grafana-dashboards", list_name)
    out = {"default": default, "network": list_name, "grafana_url": _grafana_url(list_name),
           "value_at": at, "range": range_text, "limit_words": panels.limit_words(panels.stores((value or {}).get("datasources") or [], list_name)), "offered": [], "state": "ok"}
    if value is None:
        out.update(state="not_read", why=why)
        return out
    dashboards, datasources = value.get("dashboards") or {}, value.get("datasources") or []
    out["offered"] = sorted(({"uid": uid, "title": d.get("title") or uid}
                             for uid, d in dashboards.items()), key=lambda d: d["title"].lower())
    uid = chosen_uid or default
    if not uid:
        out.update(state="not_set")
        return out
    dash, live = _dashboard(dashboards, uid, client)
    if dash is None:
        out.update(state="uid_gone" if live.get("state") == "absent" else "uid_unconfirmed",
                   uid=uid, live=live)
        return out
    if live:
        out["live"] = live
    out.update(dashboard={"uid": uid, "title": dash["title"]}, is_default=(uid == default))
    try:
        seconds = panels.parse_range(range_text)
        panels.check_range(seconds, "prometheus", panels.stores(datasources, list_name))
    except panels.RangeRefused as exc:
        out.update(state="range_refused", why=str(exc))
        return out
    drawn = _fleet_panels(dash)
    out.update(drawn=drawn, layout=panels.drawn_elsewhere(panels.layout(drawn), uid,
                                                          _grafana_url(list_name)),
               seconds=seconds,
               step=panels.step_for(seconds), range_words=panels.describe(seconds),
               variables={k: v for k, v in panels.variable_values(dash, "", "", datasources).items()})
    return out


def fleet_panel_data(list_name: str, uid: str, panel_id: int, range_text: str,
                     client=None) -> tuple:
    """(payload, http status) for one panel of a fleet dashboard of the network
    *list_name*. Only a panel the dashboard holds; the query is the dashboard's, with its
    variables at their own values, never anything the browser sends."""
    client = client or grafana_client(list_name)
    value, _at, why = _cached("grafana-dashboards", list_name)
    if value is None:
        return {"ok": False, "error": f"the dashboards are not read yet: {why}"}, 503
    dash, live = _dashboard(value.get("dashboards") or {}, uid, client)
    if dash is None:
        if live.get("state") == "absent":
            return {"ok": False, "error": f"Grafana answered, asked now: no dashboard with UID {uid}"}, 404
        return {"ok": False, "error": (f"{uid} is not in the stored dashboard list, and Grafana could "
                                       f"not be asked now: {live.get('error')}")}, 503
    panel = next((p for p in _fleet_panels(dash) if p.get("id") == panel_id), None)
    if panel is None:
        return {"ok": False, "error": f"{uid} holds no panel {panel_id}"}, 404
    if panel.get("type") not in panels.NATIVE_TYPES:
        return {"ok": False, "error": (f"panel {panel_id} is a {panel.get('type')} panel: Grafana "
                                       "draws it, this page does not")}, 400
    datasources = value.get("datasources") or []
    try:
        seconds = panels.parse_range(range_text)
        st = panels.stores(datasources, list_name)
        panels.check_range(seconds, "prometheus", st)
        fill = panels.variable_values(dash, "", "", datasources)
        body = panels.build_request(panel, dash, fill, seconds,
                                    panels.default_datasource(datasources, "prometheus"), st)
    except panels.RangeRefused as exc:
        return {"ok": False, "error": str(exc)}, 400
    got = client.query(body)
    if not got.get("ok"):
        return {"ok": False, "error": f"Grafana: {got.get('error')}"}, 502
    payload = panels.render_payload(panel, got["body"], seconds)
    payload["store"] = panels.store_words(seconds, panel, dash, fill,
                                          panels.default_datasource(datasources, "prometheus"), st)
    payload["errors"] = panels.answer_errors(got["body"])
    payload["read_at"] = _iso(time.time())
    return payload, 200


# ---------------------------------------------------------------------------
# The History tab (NSOT_GUI_BRIEF 3.3, step 4): ONE timeline of what was done
# to this device and its record, from the records the app keeps: its golden
# commits (captures, deploys, restores, rotations, onboarding: each names its
# workflow in `Source:`), its intent commits, and the deploy and restore
# receipts. A record that cannot be read is said, never a shorter timeline.
# ---------------------------------------------------------------------------

#: How many of each record the timeline reads; a timeline cut says so.
HISTORY_LIMIT = 30


def _epoch(iso: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def history(ref, dev: dict, limit: int = None) -> dict:
    """The History tab: THE timeline (`history_sources.timeline`, C369) filtered to this
    device, all time, newest first: the History page's reader, the same rows. Each event is
    ``{"at", "kind", "what", "devices", "who", "detail", "sha", "outcome", "marks",
    "record"}``; a store that cannot be read is said, never a shorter timeline."""
    from modules import history_sources

    return history_sources.timeline(ref, device=dev.get("hostname", ""),
                                    limit=limit or HISTORY_LIMIT)


# ---------------------------------------------------------------------------
# The Intent tab (NSOT_GUI_BRIEF 3.3, step 4), READ-ONLY for now: what this
# device is supposed to look like, as COMMITTED (read from git at HEAD, never
# the working tree, C104), its last intent commit, and what the network's
# monitoring profile adds on top or the device excludes. Editing stays on
# today's page until the redesign carries the editor and its form mode.
# ---------------------------------------------------------------------------

def intent_view(ref, dev: dict) -> dict:
    """``{"state", "text", "commit", "note", "bootstrap", "profile"}``. *state*
    is ``committed``, ``never_committed`` or ``unreadable`` (said, never an
    empty document)."""
    from modules.nsot import hostvars
    from modules.nsot import profile as _p
    from modules.nsot.platform import platform_for_device
    from modules.redact import redact_text

    host = dev.get("hostname", "")
    out = {"state": "", "text": "", "commit": {}, "note": "", "bootstrap": False,
           "profile": {"committed": False, "applies": [], "excluded": {}, "error": ""}}
    try:
        text, state = hostvars.committed_at_head(ref.repo_dir, host)
    except Exception as exc:                          # noqa: BLE001
        out.update(state="unreadable", note=f"its committed intent could not be read: {exc}")
        return out
    if text is None:
        gap = hostvars.intent_gap_note(ref.repo_dir, host)
        out.update(state="never_committed", note=str(gap.get("note", "")).replace("**", ""))
        return out
    # Committed intent names secret REFERENCES, never values; masked on the
    # way out all the same, as every config text is.
    out.update(state="committed", text=redact_text(text))
    change = hostvars.intent_change(ref.repo_dir, host)
    out["commit"] = {"sha": change.get("sha", ""), "subject": change.get("subject", "")}
    try:
        doc = hostvars.read_committed(ref.repo_dir, host) or {}
        out["bootstrap"] = bool(hostvars.is_bootstrap_only(doc))
        prof = _p.read_committed(ref.repo_dir)
        out["profile"]["committed"] = bool(prof)
        if prof:
            out["profile"]["applies"] = sorted(_p.sections_for(
                prof, platform_for_device(dev) or "", dev.get("role", ""), doc))
        out["profile"]["excluded"] = _p.excluded(doc)
    except Exception as exc:                          # noqa: BLE001
        out["profile"]["error"] = f"{type(exc).__name__}: {exc}"
    return out
