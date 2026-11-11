"""What each SDN switch can do (Lab 9 B3, board F's capability matrix): per switch, read from the
switch's own answers through its controller, never assumed from its vendor; and the fallback a
response takes where the switch cannot (the handout: "if a vendor switch cannot support an
action, for example meters, document the limit and your fallback").

**What is read, per switch** (`read`, three driver calls a switch, every switch at once,
`fanout.read_each`): what it says it is (`switch_desc`), its meter features (`meter_features`)
and its table features (`table_features`). Each column is one of `STATES`, and **not read and
none are different states**: a switch that did not answer a request is never shown as lacking
the feature.
- **OpenFlow** (``version``): ``1.3`` or later where it answered table features (an OpenFlow
  1.3 message), ``1.0`` where the controller answered that the switch's version does not
  support the request (Ryu's 501, `drivers/ryu.py`), else not read.
- **Tables**: how many tables its table features list (the harness's recording keeps three of
  Open vSwitch's 254: tests/fixtures/sdn/harness/README.md).
- **Meters**: yes where it reports at least one meter and a DROP band (the band a rate limit
  uses, `closed_loop.build_response`), its band types and units named; none where it reports
  no meter, no DROP band, or its version has no meters; else not read.
- **Group actions**: yes where a table's actions list GROUP; none where every table's are read
  and none does; else not read. **Fast-failover groups** need the switch's group features,
  which no driver reads yet, so that column is always not read, said.
- **Rewrite** (``set_field``): yes where a table's apply or write set-field lists a field; none
  where every table's are read and none does; else not read.

**The fallback** (`fallback`): a rate limit is a meter, so on a switch whose meters are
**none** the response is a drop instead (`closed_loop.CATALOGUE`'s ``drop_source``, under the
network's response policy, which may refuse it: then a person decides), said in words on the
response and its line; on a switch whose meters were **not read**, the rate limit stays and
its preview reads the meters itself, refusing (and saying why) if they cannot be read. Any
other action is unchanged.

**The store** (``sdn_capabilities.json`` in the network's folder): the last read, written
atomically and owner-only under a cross-process lock; absent (never read) and unreadable are
different answers. It is read again by the loop's start (a job) and by Read again on SDN ›
Responses (a person), never by a page view (CLAUDE.md, "Enterprise scale").
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

STORE_FILE = "sdn_capabilities.json"
SCHEMA = 1
STATES = ("yes", "none", "not_read")
#: The words a column's state carries where nothing more specific is known.
NOT_READ_WORDS = "not read"
GROUP_FEATURES_WORDS = ("not read: no driver reads a switch's group features yet, so whether "
                        "it offers fast-failover groups is not known")
#: The actions a fallback replaces, by what each needs.
NEEDS = {"rate_limit_source": "meters"}
FALLBACK = {"rate_limit_source": "drop_source"}


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _unsupported(error: str) -> bool:
    """Whether a read's *error* is the controller saying the switch's version does not support
    it (Ryu's 501, `drivers/ryu.py`)."""
    return "HTTP 501" in str(error or "")


def summarise(dpid: int, desc: dict, meters: dict, tables: dict) -> dict:
    """One switch's row from its three answers (each a driver call's ``{"ok", ...}``):
    ``{"dpid", "dpid_hex", "name", "desc", "version", "tables", "meters", "groups",
    "fast_failover", "set_field", "cannot"}``, each column ``{"state", "words"}``."""
    from modules.sdn.drivers.base import dpid_hex

    d = (desc or {}).get("desc") or {}
    row = {"dpid": dpid, "dpid_hex": dpid_hex(dpid),
           "name": str(d.get("dp_desc") or "").strip(),
           "desc": " ".join(str(d.get(k) or "").strip() for k in ("mfr_desc", "hw_desc",
                                                                 "sw_desc")).strip()
           if (desc or {}).get("ok") else f"not read: {(desc or {}).get('error') or 'no answer'}"}
    t_ok = bool((tables or {}).get("ok"))
    t_list = list((tables or {}).get("tables") or []) if t_ok else []
    if t_ok:
        row["version"] = {"state": "yes", "value": "1.3",
                          "words": "1.3 or later (it answers table features, a 1.3 request)"}
        row["tables"] = {"state": "yes", "value": len(t_list),
                         "words": f"{len(t_list)} table{'s' if len(t_list) != 1 else ''}"}
    elif _unsupported((tables or {}).get("error")):
        row["version"] = {"state": "yes", "value": "1.0", "words": (
            "1.0 (the controller answers that its version does not support table features)")}
        row["tables"] = {"state": "not_read", "value": None,
                         "words": "not read: OpenFlow 1.0 has no table features request"}
    else:
        why = (tables or {}).get("error") or "no answer"
        row["version"] = {"state": "not_read", "value": None, "words": f"not read: {why}"}
        row["tables"] = {"state": "not_read", "value": None, "words": f"not read: {why}"}
    m_ok = bool((meters or {}).get("ok"))
    feat = (meters or {}).get("features") if m_ok else None
    if m_ok:
        bands = list((feat or {}).get("band_types") or [])
        units = [c for c in (feat or {}).get("capabilities") or [] if c in ("KBPS", "PKTPS")]
        if feat and (feat.get("max_meter") or 0) > 0 and "DROP" in bands:
            row["meters"] = {"state": "yes", "value": feat.get("max_meter"), "words": (
                f"{feat.get('max_meter'):,} meters, {', '.join(bands)} band"
                f"{'s' if len(bands) != 1 else ''}"
                + (f", {' and '.join(u.lower() for u in units)}" if units else ""))}
        elif feat and (feat.get("max_meter") or 0) > 0:
            row["meters"] = {"state": "none", "value": feat.get("max_meter"), "words": (
                f"none usable: {feat.get('max_meter'):,} meters but no DROP band "
                f"({', '.join(bands) or 'no band types'})")}
        else:
            row["meters"] = {"state": "none", "value": 0, "words": (
                "none: it reports no meter" if feat else "none: it reports no meter features")}
    elif _unsupported((meters or {}).get("error")):
        row["meters"] = {"state": "none", "value": 0,
                         "words": "none: its OpenFlow version has no meters"}
    else:
        row["meters"] = {"state": "not_read", "value": None, "words": (
            f"not read: {(meters or {}).get('error') or 'no answer'}")}
    if t_ok:
        actions = {a for t in t_list for k in ("apply_actions", "write_actions")
                   for a in t.get(k) or []}
        fields = sorted({f for t in t_list for k in ("apply_setfield", "write_setfield")
                         for f in t.get(k) or []})
        row["groups"] = ({"state": "yes", "words": "yes (a table's actions list GROUP)"}
                         if "GROUP" in actions else
                         {"state": "none", "words": "none: no table's actions list GROUP"})
        row["set_field"] = ({"state": "yes", "value": len(fields),
                             "words": f"yes, {len(fields)} field{'s' if len(fields) != 1 else ''}"}
                            if fields else
                            {"state": "none", "value": 0,
                             "words": "none: no table lists a set-field"})
    else:
        why = row["tables"]["words"]
        row["groups"] = {"state": "not_read", "words": why}
        row["set_field"] = {"state": "not_read", "value": None, "words": why}
    row["fast_failover"] = {"state": "not_read", "words": GROUP_FEATURES_WORDS}
    row["cannot"] = cannot_words(row)
    return row


def cannot_words(row: dict) -> list:
    """What the switch cannot do and what Mercury does instead, each in words (board F's
    "When it cannot")."""
    out = []
    m = (row.get("meters") or {}).get("state")
    if m == "none":
        out.append("rate-limit → drop: a rate limit needs a meter, so a response here drops "
                   "the source instead (where the network's response policy allows a drop)")
    elif m == "not_read":
        out.append("meters not read: a rate limit reads them at its preview and is refused, "
                   "saying why, if they cannot be read; a drop is offered")
    if (row.get("set_field") or {}).get("state") == "none":
        out.append("no rewrite: a flow that rewrites a field is refused at its preview here")
    out.append("link failure: the forwarding app's reroute is verified by the trace; "
               "fast failover is not read")
    return out


# ───────────────────────────────────────────────────────────────────────────── read and store

def _path(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), STORE_FILE)


def read(network: str, *, driver=None, now: float = None) -> dict:
    """Read every switch's capabilities on *network* (see the module's docstring) and keep
    them: ``{"ok", "error", "read_at", "controllers": [{"connection", "error", "switches"}]}``.
    *driver* is ``driver(network, name)`` (a test's fakes). Never raises: a connection that
    fails is its error, its switches not read."""
    from modules import fanout
    from modules.filestore import PathLock, write_atomic
    from modules.sdn import closed_loop

    now = time.time() if now is None else now
    out = {"ok": False, "error": "", "read_at": _iso(now), "controllers": []}
    listed = closed_loop._connections(network)
    if listed["state"] == "unreadable":
        out["error"] = f"{network}'s controller connections could not be read: {listed['error']}"
        return out
    make = driver or closed_loop._driver
    for conn in listed.get("connections") or []:
        entry = {"connection": conn.get("name"), "error": "", "switches": []}
        out["controllers"].append(entry)
        try:
            got = make(network, conn["name"])
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            got = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if not got.get("ok"):
            entry["error"] = got.get("error") or "no driver"
            continue
        drv = got["driver"]
        sws = drv.switches()
        if not sws.get("ok"):
            entry["error"] = f"the switch list could not be read: {sws.get('error')}"
            continue

        def one(dpid, drv=drv):
            return summarise(dpid, drv.switch_desc(dpid), drv.meter_features(dpid),
                             drv.table_features(dpid))

        dpids = [s["dpid"] for s in sws.get("switches") or []]
        rows = fanout.read_each(one, dpids, name="sdn-capabilities")
        for dpid, row in zip(dpids, rows):
            entry["switches"].append(row if not isinstance(row, fanout.Failed) else
                                     summarise(dpid, {"ok": False, "error": str(row)},
                                               {"ok": False, "error": str(row)},
                                               {"ok": False, "error": str(row)}))
    out["ok"] = True
    path = _path(network)
    try:
        with PathLock(path):
            write_atomic(path, json.dumps({"schema": SCHEMA, **out}, sort_keys=True,
                                          default=str))
    except OSError as exc:
        out.update(ok=False, error=f"{STORE_FILE} could not be written: {exc}")
    return out


def stored(network: str) -> dict:
    """The last read: ``{"state": "ok"|"absent"|"unreadable", "error", "read_at",
    "controllers"}``."""
    path = _path(network)
    if not os.path.exists(path):
        return {"state": "absent", "error": "", "read_at": "", "controllers": []}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            raise ValueError(f"not a schema {SCHEMA} capability document")
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "error": f"{STORE_FILE} could not be read: {exc}",
                "read_at": "", "controllers": []}
    return {"state": "ok", "error": "", "read_at": doc.get("read_at") or "",
            "controllers": doc.get("controllers") or []}


def row_for(network: str, connection: str, dpid, got: dict = None) -> dict:
    """The stored row of switch *dpid* on *connection*, or None (never read, or not listed)."""
    from modules.sdn.drivers.base import parse_dpid

    got = stored(network) if got is None else got
    try:
        want = parse_dpid(dpid)
    except Exception:                                 # noqa: BLE001 (no such switch)
        return None
    for c in got.get("controllers") or []:
        if c.get("connection") != connection:
            continue
        for row in c.get("switches") or []:
            if row.get("dpid") == want:
                return row
    return None


def fallback(action: str, row: dict) -> dict:
    """The action a response takes on the switch *row* describes (`row_for`'s, or None):
    ``{"action", "fell_back", "words"}``. A rate limit on a switch whose meters are none is a
    drop; on one whose meters were not read, or not in the matrix, it stays (its preview reads
    them); every other action is unchanged."""
    need = NEEDS.get(action)
    if not need:
        return {"action": action, "fell_back": False, "words": ""}
    col = (row or {}).get(need) or {}
    switch = (row or {}).get("name") or (row or {}).get("dpid_hex") or "the switch"
    if col.get("state") == "none":
        to = FALLBACK[action]
        return {"action": to, "fell_back": True, "words": (
            f"{switch} cannot rate-limit ({col.get('words')}): the fallback is to drop the "
            "source instead (the capability matrix on SDN › Responses)")}
    if row is None:
        return {"action": action, "fell_back": False, "words": (
            "the switch's capabilities are not read: the rate limit's preview reads its meters")}
    return {"action": action, "fell_back": False, "words": ""}


#: The matrix's rows drawn before the rest are counted (CLAUDE.md's large-fleets rule), the
#: switches that cannot do something first.
ROWS_DRAWN = 50
COLUMNS = ("version", "tables", "meters", "groups", "set_field")


def view(network: str) -> dict:
    """Board F's matrix for SDN › Responses, from the store (no controller call): ``{"state",
    "error", "read_at", "rows", "total"}``, each row a switch's with its connection; the
    switches with a column none or not read first, at most `ROWS_DRAWN`."""
    from modules.sdn import known

    got = stored(network)
    # C3010: a switch's row is named as NetBox names it, matched by datapath id (one read for
    # the matrix), else by the description it gives of itself where it gives one.
    names = known.names_for(network)
    rows = [dict({k: v for k, v in r.items() if k != "dpid"}, connection=c.get("connection"),
                 name=known.drawn_name(r.get("dpid_hex"), names, r.get("name")))
            for c in got["controllers"] for r in c.get("switches") or []]
    rows.sort(key=lambda r: (all((r.get(k) or {}).get("state") == "yes" for k in COLUMNS),
                             r.get("name") or "", r.get("dpid_hex") or ""))
    errors = [f"{c.get('connection')}: {c.get('error')}" for c in got["controllers"]
              if c.get("error")]
    return {"state": got["state"], "error": got["error"] or "; ".join(errors),
            "read_at": got["read_at"], "rows": rows[:ROWS_DRAWN], "total": len(rows)}
