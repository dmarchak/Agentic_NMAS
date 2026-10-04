"""Grafana's dashboards, as a reader job: every dashboard Grafana holds and
each one's model, trimmed to what the app draws from (NSOT_GUI_BRIEF 14.2).

The Monitoring page and the device page render every panel from the
dashboard's OWN definition, never a chosen few, so a panel added in Grafana
appears in the app with no code change. Reading those models is an outside
read, so it is never done on a page load (reader rule 1): this job reads
`api/search?type=dash-db` and each dashboard's `api/dashboards/uid/<uid>`, and
the pages read the stored value.

**Referenced by UID, never by title** (the operator, 2026-09-30): the value is
keyed by UID, so a renamed dashboard is still found, and a configured UID the
value does not hold is a named state, never a blank panel.

**A search answer exactly the size of its page is partial** (rule 5): the
search is asked for at most `SEARCH_LIMIT`, and an answer of exactly that many
is refused rather than stored as the whole set.
"""

import time

from modules import reader_job

SEARCH = "api/search"
DASHBOARD = "api/dashboards/uid/<uid>"
FRONTEND = "api/frontend/settings"
DATASOURCES = "api/datasources"
SEARCH_LIMIT = 500
INTERVAL_SECONDS = 300


def _field_mappings(p: dict) -> dict:
    """``{field name: mappings}`` from the panel's `byName` overrides."""
    out = {}
    for o in ((p.get("fieldConfig") or {}).get("overrides") or []):
        m = o.get("matcher") or {}
        if m.get("id") != "byName" or not m.get("options"):
            continue
        for prop in o.get("properties") or []:
            if prop.get("id") == "mappings" and prop.get("value"):
                out[str(m["options"])] = prop["value"]
    return out


def _organize(p: dict) -> dict:
    """The panel's `organize` transformation: ``{exclude: [...], rename: {...}}``,
    or ``{}`` when it has none."""
    for t in p.get("transformations") or []:
        if t.get("id") == "organize":
            opt = t.get("options") or {}
            return {"exclude": sorted(k for k, v in (opt.get("excludeByName") or {}).items() if v),
                    "rename": dict(opt.get("renameByName") or {})}
    return {}


def _panels(model: dict) -> list:
    """Every panel, rows included, in the dashboard's order, each trimmed to
    what a renderer reads: type, title, grid position, targets, unit, and the
    row it sits in."""
    out, row = [], ""

    def add(p, row_title):
        defaults = ((p.get("fieldConfig") or {}).get("defaults") or {})
        out.append({
            "id": p.get("id"), "type": p.get("type"), "title": p.get("title") or "",
            "gridPos": p.get("gridPos") or {}, "row": row_title,
            "datasource": p.get("datasource"),
            "unit": defaults.get("unit") or "",
            "min": defaults.get("min"), "max": defaults.get("max"),
            "thresholds": (defaults.get("thresholds") or {}).get("steps") or [],
            "targets": [{"refId": t.get("refId"), "expr": t.get("expr") or "",
                         "legendFormat": t.get("legendFormat") or "",
                         "datasource": t.get("datasource"),
                         "instant": bool(t.get("instant")), "format": t.get("format") or ""}
                        for t in p.get("targets") or []],
            "transformations": len(p.get("transformations") or []),
            # VALUE MAPPINGS (the operator, 2026-09-30: "Yes"/"up" instead of 1):
            # the panel's own, and each field override's by the field's name.
            "mappings": defaults.get("mappings") or [],
            "no_value": defaults.get("noValue") or "",
            "description": p.get("description") or "",
            "field_mappings": _field_mappings(p),
            # The one transformation drawn natively: `organize` (drop and rename
            # columns). Any other is counted above and not applied.
            "organize": _organize(p),
        })

    for p in model.get("panels") or []:
        if p.get("type") == "row":
            row = p.get("title") or ""
            out.append({"id": p.get("id"), "type": "row", "title": row,
                        "gridPos": p.get("gridPos") or {}, "row": row, "targets": [],
                        "collapsed": bool(p.get("collapsed"))})
            for inner in p.get("panels") or []:        # a collapsed row holds its panels
                add(inner, row)
            continue
        add(p, row)
    return out


def _variables(model: dict) -> list:
    out = []
    for v in (model.get("templating") or {}).get("list") or []:
        q = v.get("query")
        out.append({"name": v.get("name"), "type": v.get("type"),
                    "query": q if isinstance(q, str) else (q or {}).get("query") or "",
                    "current": (v.get("current") or {}).get("value"),
                    "multi": bool(v.get("multi"))})
    return out


def read(client=None) -> dict:
    """Ask Grafana. Raises when it could not ask or the answer is partial."""
    from modules.integrations.grafana import GrafanaIntegration

    g = client or GrafanaIntegration()
    got = g._get(SEARCH, type="dash-db", limit=SEARCH_LIMIT)
    if not got.get("ok"):
        raise ConnectionError(f"{SEARCH}: {got.get('error') or 'no answer'}")
    found = got["response"].json() or []
    if len(found) >= SEARCH_LIMIT:
        raise reader_job.Truncated(f"{SEARCH} answered exactly {SEARCH_LIMIT}: a partial list")
    dashboards = {}
    for d in found:
        uid = d.get("uid")
        one = g._get(f"api/dashboards/uid/{uid}")
        if not one.get("ok"):
            raise ConnectionError(f"api/dashboards/uid/{uid}: {one.get('error') or 'no answer'}")
        model = (one["response"].json() or {}).get("dashboard") or {}
        dashboards[uid] = {"uid": uid, "title": model.get("title") or d.get("title") or uid,
                           "folder": d.get("folderTitle") or "", "variables": _variables(model),
                           "panels": _panels(model), "refresh": model.get("refresh") or ""}
    fs = g._get(FRONTEND)
    if not fs.get("ok"):
        raise ConnectionError(f"{FRONTEND}: {fs.get('error') or 'no answer'}")
    # Where each datasource points (the operator, 2026-10-04, host step 14.14: the confirm
    # showed "?"). Front-end settings carry only a proxy path; the list carries the address.
    # A token that cannot read it leaves the addresses unknown and says why, never fails.
    listed = g._get(DATASOURCES)
    if listed.get("ok"):
        urls, urls_why = {d.get("uid"): d.get("url") or ""
                          for d in (listed["response"].json() or []) if isinstance(d, dict)}, ""
    else:
        urls, urls_why = {}, (f"{DATASOURCES} answered "
                              f"{listed.get('status') or listed.get('error') or 'nothing'}: "
                              "the token cannot read data source settings")
    return {"dashboards": dashboards,
            "datasources": datasources(fs["response"].json() or {}, urls, urls_why),
            "read_at": time.time()}


def read_one(uid: str, client=None) -> dict:
    """ONE dashboard, asked LIVE: ``{"state": "found", "dashboard": {...}}``,
    ``{"state": "absent"}`` when Grafana answers 404, or
    ``{"state": "unknown", "error"}`` when it could not be asked.

    Rule 11 (the operator, 2026-09-30): a stored list is for DISPLAY;
    concluding that a configured UID does not exist is a CHECK. After the
    operator imported nmas-device, the device page said Grafana held no such
    dashboard while Grafana listed it: the stored list predated the import.
    So a miss in the stored list is asked of Grafana before anything says the
    dashboard is gone."""
    from modules.integrations.grafana import GrafanaIntegration

    g = client or GrafanaIntegration()
    got = g._get(f"api/dashboards/uid/{uid}")
    if not got.get("ok"):
        if got.get("status") == 404:
            return {"state": "absent", "asked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        return {"state": "unknown", "error": got.get("error") or "no answer", "asked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    model = (got["response"].json() or {}).get("dashboard") or {}
    return {"state": "found", "asked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dashboard": {"uid": uid, "title": model.get("title") or uid, "folder": "",
                          "variables": _variables(model), "panels": _panels(model),
                          "refresh": model.get("refresh") or ""}}


def datasources(frontend: dict, urls: dict = None, urls_why: str = "") -> list:
    """The data sources, from Grafana's front-end settings (which any signed-in
    role reads, so a Viewer token can): uid, type, name, and which is the
    default, which a data-source variable with no current value resolves to.
    *urls* (uid -> address, from `api/datasources`) adds where each points, as
    `url`; an unknown address is "" with `url_why` saying why."""
    default = frontend.get("defaultDatasource")
    out = []
    for name, d in sorted((frontend.get("datasources") or {}).items()):
        if not d.get("uid") or d.get("type") in ("grafana", "dashboard", "mixed"):
            continue
        url = (urls or {}).get(d["uid"], "")
        out.append({"uid": d.get("uid"), "type": d.get("type"), "name": name,
                    "is_default": name == default, "url": url,
                    **({} if url else {"url_why": urls_why or
                                       f"{DATASOURCES} does not list it"})})
    return out


#: The Monitoring tab re-renders on this reader's announcement, so it
#: announces when a dashboard CHANGED, and at least this often regardless
#: (rule 9's keepalive): a redraw every five minutes for nothing would reset
#: every chart on an open page.
KEEPALIVE_SECONDS = 1800


def changed(previous: dict, value: dict) -> bool:
    """Did anything a page draws move? The models and the data sources; never
    the read time, which moves every cycle."""
    def key(v):
        return ((v or {}).get("dashboards"), (v or {}).get("datasources"))
    return key(previous) != key(value)


READER = reader_job.register(reader_job.Reader(
    name="grafana-dashboards",
    what="every dashboard Grafana holds and its model, for the pages that render its panels",
    endpoints=(SEARCH, DASHBOARD, FRONTEND, DATASOURCES),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("a dashboard changes when a person edits it in Grafana, which is rare; five "
                    "minutes makes an edit appear soon without re-reading every model each minute"),
    read=read,
    invalidates=("dashboards",),
    remedy="Check Grafana's URL and token in Settings > Integrations; the error names the endpoint",
    window="the dashboards as they were at the read",
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
