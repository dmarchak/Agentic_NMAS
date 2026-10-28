"""What SDN › Controllers, SDN › Flows and Settings' SDN controllers card draw (PHASE8_PLAN 17.1
S11; boards SdnControllers, SdnFlows, SdnSettings and SdnPhone, signed off 2026-10-27).

**Controllers and Flows draw a stored read, never a controller call per view** (CLAUDE.md,
"Enterprise scale"): the SDN reader's value (`modules/readers/sdn_controllers.py`), with its
age, beside the network's connection list as Settings holds it now (a local read), so a
connection saved a moment ago is drawn at once, as "not read yet", never missing.

**The Settings card's Test gates its Save** (board SdnSettings: "Save is refused while Test
has not answered for the URL as typed"). A Test that answered hands the form a receipt
(`tested_receipt`): the network, the driver, the URL and the TLS choice as typed, signed with
the installation's secret key (`app.secret_key`, the same in every process), with its time. Save
checks it (`tested_problem`): a receipt for another URL, driver or TLS choice, an altered one,
or one older than `RECEIPT_SECONDS` refuses the save, naming which. The credential is not in
the receipt: what is typed is never echoed back, even as a digest.
"""

import hashlib
import hmac
import json
import logging
import time

log = logging.getLogger(__name__)

#: How long a Test's answer stands for a Save: long enough to fill the rest of the form, short
#: enough that a controller moved since is tested again.
RECEIPT_SECONDS = 1800
OWNER_WORDS = {"mercury": "Mercury's", "mercury_differs": "Mercury's, not as recorded",
               "controller_own": "the controller's own", "unauthorised": "unauthorised"}
OWNER_KIND = {"mercury": "ok", "mercury_differs": "warn", "controller_own": "muted",
              "unauthorised": "danger"}
STATE_WORDS = {"connected": ("connected", "ok"), "partial": ("partly read", "warn"),
               "not_answering": ("not answering", "danger"),
               "not_built": ("driver not built", "muted"),
               "unread": ("not read yet", "muted")}
CAPABILITY_WORDS = {"read_topology": "read topology", "read_flows": "read flows",
                    "read_port_stats": "read port stats", "read_meters": "read meters",
                    "write_flows": "write flows", "write_meters": "write meters",
                    "delete_flows": "delete flows"}
CAPABILITY_ORDER = ("read_flows", "read_port_stats", "read_meters", "write_flows",
                    "write_meters", "delete_flows", "read_topology")
STATUS_WORDS = {"built": "built", "later": "later", "unmaintained": "unmaintained"}


# ───────────────────────────────────────────────────────────────────────────── the region's promise

def redraw_promise(now: float = None) -> dict:
    """How long a drawn SDN region (`#sdn`, every tab) stays current with no redraw (C2003): the
    SDN reader's own page promise, `reader_job.page_promise` (its 3 read intervals of 30 s, 90 s,
    the promise the sidebar's count judges this reader's value by), counted from the moment the
    region is drawn. The reader announces `sdn` at every read, changed or not, so a region that
    is live is redrawn every 30 s; past ``stale_at`` with no redraw, the page says it may be out
    of date (static/js/nmas_v2.js `staleNote`). ``drawn_at`` is the region's "last updated"."""
    from modules import reader_job
    from modules.readers import sdn_controllers

    seconds = reader_job.page_promise(sdn_controllers.READER)
    now = time.time() if now is None else now
    iso = "%Y-%m-%dT%H:%M:%SZ"
    return {"drawn_at": time.strftime(iso, time.gmtime(now)),
            "stale_at": time.strftime(iso, time.gmtime(now + seconds)), "seconds": seconds}


# ───────────────────────────────────────────────────────────────────────────── the stored read

def stored(network: str) -> dict:
    """The SDN reader's value for *network*, in the states a page draws: ``ok`` (with
    ``value``, ``value_at`` and ``failed``, the last attempt's error when it failed),
    ``never`` (no read stored yet), ``not_configured`` (no connection set, so nothing is
    read), ``not_applicable`` or ``unreadable`` (with ``why``)."""
    return _stored(network)[0]


def _stored(network: str) -> tuple:
    """``(stored's answer, the reader's cached answer as read)``: the second for a caller that
    judges the read further (Flows' answered lost responses, C2077), so it is read once."""
    from modules import reader_job
    from modules.readers.sdn_controllers import READER_NAME

    got = reader_job.read_cached_for(READER_NAME, network)
    state = got.get("state")
    if state in ("not_applicable", "not_configured", "unreadable"):
        return {"state": state,
                "why": got.get("why") or "the reader's store could not be read"}, got
    doc = got.get("doc") or {}
    last = doc.get("last_good") or {}
    attempt = doc.get("last_attempt") or {}
    failed = "" if attempt.get("ok", True) else (attempt.get("error") or "the last read failed")
    if not last:
        return {"state": "never", "failed": failed}, got
    return {"state": "ok", "value": last.get("value") or {},
            "value_at": last.get("value_at", ""), "failed": failed}, got


def _drawn_read(got: dict) -> dict:
    """The stored read as a tab draws it: its state, why, last failure and when it was read.
    The read's ``value`` (every controller's switches, flows, meters and records, as read) is
    what the cards and switches are built from in Python, never drawn whole (C2082)."""
    return {k: v for k, v in got.items() if k != "value"}


def _listed(network: str) -> dict:
    from modules.sdn import connections

    return connections.connections(network)


def _merged(network: str, keep: dict = None) -> tuple:
    """``(listed, stored, controllers)``: each connection as Settings holds it, with what the
    reader last read of it (``unread`` when nothing yet, or when it was read under another
    URL or driver than it has now). *keep*, when given, is handed the reader's cached answer
    as read (``keep["cached"]``), so a caller judging it further reads nothing twice."""
    listed = _listed(network)
    got, cached = _stored(network)
    if keep is not None:
        keep["cached"] = cached
    read = {c.get("name"): c for c in ((got.get("value") or {}).get("controllers") or [])}
    out = []
    for conn in listed.get("connections") or []:
        r = read.get(conn["name"])
        if r and (r.get("url") != conn["url"] or r.get("kind") != conn["kind"]):
            r = None
        entry = dict(r or {}, **{k: conn[k] for k in ("name", "kind", "label", "status", "url",
                                                      "verify_tls", "southbound",
                                                      "own_cookies", "credentials")})
        if not r:
            entry.update(state="not_built" if conn["status"] != "built" else "unread",
                         switches=[], error="")
        out.append(entry)
    return listed, got, out


# ───────────────────────────────────────────────────────────────────────────── Controllers

def _caps(kind: str, status: str) -> dict:
    """What a driver can do, in words: ``have`` and ``lacks`` (of a built driver), and its
    status as a person reads it."""
    from modules.sdn.drivers import DRIVERS

    cls = DRIVERS.get(kind)
    decl = cls.declaration() if cls else {"capabilities": [], "read_first": False}
    have = [CAPABILITY_WORDS[k] for k in CAPABILITY_ORDER if k in decl["capabilities"]]
    lacks = [CAPABILITY_WORDS[k] for k in CAPABILITY_ORDER
             if k not in decl["capabilities"] and decl["capabilities"]]
    return {"have": have, "lacks": lacks,
            "status_words": _status_words(status, decl.get("read_first", False))}


def _status_words(status: str, read_first: bool) -> str:
    if status == "later":
        return "later: read-first, not built yet" if read_first else "later: not built yet"
    return STATUS_WORDS.get(status, status or "unknown")


def _tls_words(url: str, verify: bool) -> str:
    if str(url or "").startswith("https"):
        return "TLS verified" if verify else "TLS not verified"
    return "TLS not used"


def _driver_words(kind: str, label: str) -> str:
    return label + (" (ofctl_rest)" if kind == "ryu" else "")


def controllers_view(network: str) -> dict:
    """SDN › Controllers (board SdnControllers): the summary, then a card per connection with
    its operating state, from the stored read. Each card carries only what it draws."""
    listed, got, conns = _merged(network)
    cards = []
    for c in conns:
        switches = c.get("switches") or []
        cards.append({
            "name": c["name"], "state": c.get("state"),
            "words": STATE_WORDS.get(c.get("state"), (c.get("state"), "muted")),
            "driver": _driver_words(c["kind"], c["label"]),
            "caps": _caps(c["kind"], c["status"]),
            "northbound": c["url"], "tls": _tls_words(c["url"], c["verify_tls"]),
            "southbound": c["southbound"], "version": c.get("version"),
            "version_note": c.get("version_note", ""), "error": c.get("error", ""),
            "failing_since": c.get("failing_since"), "failures": c.get("failures") or 0,
            "last_good_at": c.get("last_good_at"),
            "switch_count": len(switches),
            "switches_failed": sum(1 for s in switches if s.get("state") != "ok"),
            "dpids": [s.get("dpid_hex") for s in switches],
            "cookies": [_cookie_hex(k) for k in c.get("own_cookies") or []],
            "meters_read": any(s.get("meters_read") for s in switches)})
    return {"network": network, "tab": "controllers", "listed": listed["state"],
            "listed_error": listed.get("error", ""), "read": _drawn_read(got),
            "controllers": cards,
            "summary": {
                "controllers": len(cards),
                "connected": sum(c["state"] in ("connected", "partial") for c in cards),
                "not_answering": sum(c["state"] == "not_answering" for c in cards),
                "unread": sum(c["state"] in ("unread", "not_built") for c in cards),
                "switches": sum(c["switch_count"] for c in cards
                                if c["state"] != "not_answering")}}


def _cookie_hex(cookie) -> str:
    """A cookie as the boards write it: hexadecimal, and 0 as ``0`` (a learning switch's)."""
    if isinstance(cookie, int) and not isinstance(cookie, bool):
        return f"{cookie:#x}" if cookie else "0"
    return str(cookie)


# ───────────────────────────────────────────────────────────────────────────── Flows

def ask(values) -> dict:
    """The Flows view's question: ``q`` (a filter over switch, match, action or cookie) and
    ``own`` (``hide`` by default: the controller's own flows are hidden; ``show``)."""
    q = " ".join(str(values.get("q") or "").split())[:120]
    own = values.get("own") if values.get("own") in ("hide", "show") else "hide"
    return {"q": q, "own": own}


def _match_words(match: dict) -> str:
    if not match:
        return "any (the match-all)"
    return ", ".join(f"{k}={_value_words(k, v)}" for k, v in match.items())


def _value_words(key, value) -> str:
    if key == "eth_type" and isinstance(value, int):
        return f"{value:#06x}"
    return str(value)


def _timeouts(flow: dict) -> str:
    hard, idle = flow.get("hard_timeout") or 0, flow.get("idle_timeout") or 0
    parts = []
    if hard:
        age = flow.get("duration_sec")
        left = f", {max(0, hard - age)} s left" if isinstance(age, int) else ""
        parts.append(f"hard {hard} s{left}")
    if idle:
        parts.append(f"idle {idle} s")
    return ", ".join(parts) or "none"


#: The order a switch's flows are drawn in: what is wrong first.
OWNER_ORDER = {"unauthorised": 0, "mercury_differs": 1, "mercury": 2, "controller_own": 3}


def _flow_row(f: dict) -> dict:
    from modules.sdn import flow_intent

    import hashlib
    import json

    owner = f.get("owner") or ""
    # What Edit… and Remove… name (flow_form.target_of): OpenFlow's identity of the flow.
    target = json.dumps({"table_id": f.get("table_id", 0), "priority": f.get("priority"),
                         "match": f.get("match") or {}, "cookie": f.get("cookie")},
                        sort_keys=True, default=str)
    slot = "sdn-op-" + hashlib.sha256(f"{f.get('dpid')}|{target}".encode()).hexdigest()[:12]
    return {"target": target, "slot": slot,
            "owner": owner or "none", "owner_words": OWNER_WORDS.get(owner, "not classified"),
            "owner_kind": OWNER_KIND.get(owner, "muted"), "words": f.get("words", ""),
            "priority": f.get("priority"), "match": _match_words(f.get("match")),
            "actions": flow_intent.action_words(f.get("actions")),
            "packets": f.get("packet_count"), "timeouts": _timeouts(f),
            "cookie": _cookie_hex(f.get("cookie"))}


def _record_row(r: dict) -> dict:
    from modules.sdn import flow_intent

    hard, idle = r.get("hard_timeout") or 0, r.get("idle_timeout") or 0
    times = ", ".join([f"hard {hard} s"] * bool(hard) + [f"idle {idle} s"] * bool(idle)) \
        or "none"
    return {"state": r.get("state"), "words": r.get("words", ""),
            "priority": r.get("priority"), "match": _match_words(r.get("match")),
            "actions": flow_intent.action_words(r.get("actions")), "timeouts": times,
            "cookie": r.get("cookie_hex") or _cookie_hex(r.get("cookie"))}


def _hit(q: str, sw: dict, row: dict) -> bool:
    q = q.lower()
    return any(q in str(x).lower() for x in (sw.get("dpid_hex"), sw.get("name"), row["match"],
                                             row["actions"], row["cookie"]))


def _meter_words(m: dict) -> str:
    unit = "kbit/s" if "KBPS" in (m.get("flags") or []) else "packets/s"
    bands = m.get("bands") or []
    if not bands:
        return "no band"
    out = []
    for b in bands:
        what = {"DROP": "drop above", "DSCP_REMARK": "remark above"}.get(b.get("type"),
                                                                          b.get("type"))
        out.append(f"{b.get('rate', 0):,} {unit}, {what}")
    return "; ".join(out)


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _lost_row(x: dict, newer: dict = None) -> dict:
    """A lost response on its switch (C2018): Not in force with Re-apply…, or, when *newer*
    (`reapply.answered_by`'s hold: a newer response in force answering the same threat on that
    switch, C2070) is given, answered by it, naming it, with no Re-apply… (C2077)."""
    from modules.sdn import reapply

    answered = None
    if newer is not None:
        answered = {"id": newer.get("id") or newer.get("key"), "operation": newer.get("key"),
                    "label": reapply.response_words({
                        "action": newer.get("action"),
                        "detection": {"source": ", ".join(newer.get("sources") or [])}}),
                    "until": _iso(newer["until"])}
    return {"key": x["key"], "label": x["label"], "missing_words": x["missing_words"],
            "left_words": reapply.left_words(x["left"]), "expires_at": _iso(x["expires_at"]),
            "answered": answered,
            "slot": "sdn-ra-" + hashlib.sha256(
                f"{x['connection']}|{x['dpid_hex']}|{x['key']}".encode()).hexdigest()[:12]}


def flows_view(network: str, values=None, now: float = None) -> dict:
    """SDN › Flows (board SdnFlows): the summary by owner, the switches grouped and folded (a
    switch with something wrong open), the filter and "hide the controller's own", each flow's
    owner (`flow_intent.classify`, done by the reader), the meters, the granularity note, and
    on each switch the responses lost from it with their Re-apply… (`reapply.lost_on_switch`,
    judged at *now*, C2018), or, for one a newer response in force already answers, that
    response named and no Re-apply… (C2077: `reapply.answered_by`, C2070's one judgement,
    over the same stored read, once per view and only when something is lost)."""
    from modules.sdn import loop, reapply

    now = time.time() if now is None else now
    s = ask(values or {})
    keep = {}
    listed, got, conns = _merged(network, keep)
    judged = None
    out = {"network": network, "tab": "flows", "s": s, "listed": listed["state"],
           "listed_error": listed.get("error", ""), "read": _drawn_read(got), "switches": [],
           "meters": [], "granularity": [], "controllers": [c["name"] for c in conns],
           "intent_error": ((got.get("value") or {}).get("intent") or {}).get("error", "")
           if ((got.get("value") or {}).get("intent") or {}).get("state") == "unreadable"
           else ""}
    counts = {"switches": 0, "flows": 0, "mercury": 0, "mercury_differs": 0,
              "controller_own": 0, "unauthorised": 0, "missing": 0,
              "meters": 0, "unclassified": 0}
    supported = known = 0
    for c in conns:
        for sw in c.get("switches") or []:
            counts["switches"] += 1
            flows = sorted((_flow_row(f) for f in sw.get("flows") or []),
                           key=lambda f: OWNER_ORDER.get(f["owner"], 9))
            records = [_record_row(r) for r in sw.get("records") or []]
            n = {k: sum(1 for f in flows if f["owner"] == k) for k in OWNER_WORDS}
            n["unclassified"] = sum(1 for f in flows if f["owner"] not in OWNER_WORDS)
            # An expired record is drawn as its own row ("expired; nothing to do"), never
            # counted: nothing is to be done about it (C2082 found the count drawn nowhere).
            n["missing"] = sum(1 for r in records if r["state"] == "missing")
            for k in n:
                counts[k] += n[k]
            counts["flows"] += len(flows)
            shown = [f for f in flows if s["own"] == "show" or f["owner"] != "controller_own"]
            shown_records = list(records)
            if s["q"]:
                shown = [f for f in shown if _hit(s["q"], sw, f)]
                shown_records = [r for r in records if _hit(s["q"], sw, r)]
            found = reapply.lost_on_switch(c, sw, now)
            if found and judged is None:
                # The loop's own test of what holds a threat off (C2070), against the stored
                # read this page draws: the network's flow intent read once, no controller.
                judged = loop.holds(network, reapply.as_collected(got.get("value") or {}), now,
                                    cached=keep["cached"])
            lost = [_lost_row(x, reapply.answered_by(x, judged)) for x in found]
            wrong = bool(n["unauthorised"] or n["mercury_differs"] or n["missing"] or lost
                         or sw.get("state") != "ok" or c.get("state") == "not_answering")
            named = f"{sw.get('dpid_hex')} {sw.get('name') or ''}".lower()
            if s["q"] and not shown and not shown_records and s["q"].lower() not in named:
                continue
            out["switches"].append({
                "dpid_hex": sw.get("dpid_hex"), "name": sw.get("name") or "",
                "controller": c["name"], "controller_state": c.get("state"),
                "state": sw.get("state"), "error": sw.get("error", ""), "n": n,
                "total": len(flows), "flows": shown, "records": shown_records, "lost": lost,
                "hidden_own": n["controller_own"] if s["own"] == "hide" else 0,
                "wrong": wrong, "open": wrong or bool(s["q"]),
                "as_of": c.get("last_good_at") if c.get("state") == "not_answering" else None})
            cov = sw.get("coverage") or {}
            if cov and not cov.get("scan_by_ports"):
                fields = sorted({k for f in sw.get("flows") or [] for k in (f.get("match") or {})})
                out["granularity"].append({"dpid_hex": sw.get("dpid_hex"),
                                           "granularity": cov.get("granularity"),
                                           "fields": fields, "words": cov.get("words", "")})
            feats = sw.get("meter_features")
            if sw.get("meters_read") or feats is not None:
                known += 1
                if feats and (feats.get("max_meter") or 0) > 0:
                    supported += 1
            for m in sw.get("meters") or []:
                counts["meters"] += 1
                band = (m.get("bands") or [{}])[0]
                owner = m.get("owner")
                out["meters"].append({
                    "dpid_hex": sw.get("dpid_hex"), "meter_id": m.get("meter_id"),
                    "rate": _meter_words(m), "packets": band.get("packet_band_count"),
                    "owner_words": {**OWNER_WORDS, "unused": "no flow uses it"}.get(
                        owner, "not known"),
                    "owner_kind": {**OWNER_KIND, "unused": "muted"}.get(owner, "muted")})
    out["counts"] = counts
    out["meter_support"] = {"supported": supported, "known": known,
                            "switches": counts["switches"]}
    # Something wrong first, then by controller and switch.
    out["switches"].sort(key=lambda x: (not x["wrong"], x["controller"], x["dpid_hex"] or ""))
    return out


# ───────────────────────────────────────────────────────────────────────────── the Settings card

def _cred_words(cred: dict) -> str:
    if cred.get("set") is None:
        return "the credential store could not be read"
    return {"basic": "a user and password set", "token": "a token set"}.get(
        cred.get("auth"), "no credential")


def card(network: str, editing: str = "") -> dict:
    """Settings › Integrations' SDN controllers card for *network* (board SdnSettings): its
    saved connections, each driver with its status, and the form (empty to add, or the
    connection *editing* names, its credential never drawn, only whether one is set). Each
    part carries only what the card draws."""
    from modules.sdn import connections
    from modules.sdn.drivers import declarations

    listed, _got, merged = _merged(network)
    states = {c["name"]: c.get("state", "unread") for c in merged}
    drivers = []
    for d in declarations():
        words = _driver_words(d["kind"], d["label"])
        if d["status"] != "built":
            words += f" ({_status_words(d['status'], d['read_first'])})"
        drivers.append({"kind": d["kind"], "words": words, "built": d["status"] == "built"})
    rows = [{"name": c["name"],
             "read_words": STATE_WORDS.get(states.get(c["name"], "unread"),
                                           STATE_WORDS["unread"]),
             "driver": _driver_words(c["kind"], c["label"]), "northbound": c["url"],
             "cred_words": _cred_words(c["credentials"]),
             "tls": _tls_words(c["url"], c["verify_tls"])}
            for c in listed.get("connections") or []]
    form = {"name": "", "kind": "ryu", "northbound": "", "verify_tls": True, "southbound": "",
            "own_cookies": "0", "cred_set": False, "cred_auth": "none", "loaded": {}}
    if editing:
        c = next((x for x in listed.get("connections") or [] if x["name"] == editing), None)
        if c is not None:
            form = {"name": c["name"], "kind": c["kind"], "northbound": c["url"],
                    "verify_tls": c["verify_tls"], "southbound": c["southbound"],
                    "own_cookies": ", ".join(_cookie_hex(k) for k in c["own_cookies"]),
                    "cred_set": bool(c["credentials"].get("set")),
                    "cred_auth": c["credentials"].get("auth", "none"),
                    "loaded": {k: c[k] for k in connections.FIELDS if k in c}}
        else:
            editing = ""
    return {"network": network, "state": listed["state"], "error": listed.get("error", ""),
            "connections": rows, "drivers": drivers, "form": form, "editing": editing,
            "stage": stage_line(network)}


def stage_line(network: str) -> dict:
    """The network's stage as its SDN controllers card and the Responses Mode card draw it
    (C2009): ``{"stage", "words", "state", "stages"}``, *words* naming an unreadable one's
    reason; *stages* the values a person may mark it."""
    from modules.sdn import modes

    got = modes.stage(network)
    return {"stage": got["stage"], "words": got["words"], "state": got["state"],
            "stages": list(modes.STAGES)}


def form_values(form, loaded: dict = None) -> dict:
    """The card's form as `connections.save_connection` and `test_connection` take it: the
    own cookies as a list (commas or spaces), Verify TLS as the box's presence; a credential
    field sent empty is left out (a blank keeps the stored one). The timeout is the stored
    one on an edit (*loaded*, the connection as the form drew it: the board draws no field
    for it), else the driver's default."""
    cookies = [x for x in str(form.get("own_cookies") or "").replace(",", " ").split() if x]
    out = {"name": (form.get("name") or "").strip(), "kind": (form.get("kind") or "").strip(),
           "url": (form.get("url") or "").strip(), "verify_tls": form.get("verify_tls") == "on",
           "southbound": (form.get("southbound") or "").strip(), "own_cookies": cookies}
    if loaded and loaded.get("timeout") is not None:
        out["timeout"] = loaded["timeout"]
    for k in ("username", "password"):
        if form.get(k):
            out[k] = form.get(k)
    return out


def loaded_of(form):
    """The connection as the form drew it (`card`'s ``loaded``), or None when it sent none."""
    try:
        got = json.loads(form.get("loaded") or "null")
    except ValueError:
        return None
    return got if isinstance(got, dict) else None


def _receipt_key() -> bytes:
    from flask import current_app

    key = current_app.secret_key
    return key if isinstance(key, bytes) else str(key).encode("utf-8")


def _receipt_body(network: str, values: dict, at: int) -> str:
    return json.dumps([network, values.get("kind"), str(values.get("url") or "").rstrip("/"),
                       bool(values.get("verify_tls")), at], separators=(",", ":"))


def tested_receipt(network: str, values: dict, clock=time.time) -> str:
    """The receipt a Test that answered hands its form: when, and a signature over the
    network, driver, URL and TLS choice as typed."""
    at = int(clock())
    sig = hmac.new(_receipt_key(), _receipt_body(network, values, at).encode("utf-8"),
                   hashlib.sha256).hexdigest()
    return f"{at}.{sig}"


def tested_problem(network: str, values: dict, receipt: str, clock=time.time) -> str:
    """Why *receipt* does not let *values* be saved, or "": Save is refused while Test has not
    answered for the URL as typed (board SdnSettings)."""
    url = str(values.get("url") or "").rstrip("/")
    if not receipt:
        return (f"Test connection has not answered for {url or 'the URL'} as typed: press "
                "Test connection, then Save")
    at, _dot, sig = str(receipt).partition(".")
    try:
        at = int(at)
    except ValueError:
        return "the form's Test answer could not be read: press Test connection again"
    want = hmac.new(_receipt_key(), _receipt_body(network, values, at).encode("utf-8"),
                    hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, sig):
        return (f"Test connection answered for another URL, driver or TLS choice than "
                f"{url} as typed now: press Test connection again, then Save")
    if clock() - at > RECEIPT_SECONDS:
        return (f"Test connection answered {int((clock() - at) // 60)} min ago, more than "
                f"{RECEIPT_SECONDS // 60} min: press it again, then Save")
    return ""
