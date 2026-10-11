"""Devices › Onboard devices › Discovered (board L, `ZtpDiscovery.dc.html`; docs/fidelity/
onboard-discovered.md): what the page draws, from the discovery reader's stored value
(`modules/readers/ztp_discovery.py`), never a Kea call per view.

Three groups, each collapsed but the first (board L): asking now, picked and not taken, gone
quiet; a summary of their counts leads; a filter by vendor class and a search by MAC, client-id
or hostname narrow every group, and the page says when it shows a subset. Each device's cadence
is read from its own gaps (board L: "never a number written into the tool"); a device seen once
has none yet, and says so.
"""

import time
from urllib.parse import urlencode

from modules import dhcp_page
from modules.readers.ztp_discovery import QUIET_S, READER_NAME

VENDORS = (("", "Any vendor class"), ("ciscopnp", "ciscopnp"), ("none", "none sent"))
GROUPS = (("asking", "Asking now", "a request in the last 10 minutes"),
          ("picked", "Picked, not taken", "reserved, and still asking without taking it"),
          ("quiet", "Gone quiet", "no request for over 10 minutes; listed for 24 hours, then "
                                  "dropped"))


def ask(values) -> dict:
    v = (values.get("vendor") or "").strip()
    return {"vendor": v if v in dict(VENDORS) else "", "q": (values.get("q") or "").strip()[:64]}


def qs(list_name: str, s: dict, over=None) -> str:
    want = dict(s, **(over or {}))
    pairs = [("list", list_name)] + [(k, want[k]) for k in ("vendor", "q") if want.get(k)]
    return "?" + urlencode(pairs)


def ago(seconds) -> str:
    """"1 h 42 min", "6 min", "40 s"."""
    seconds = max(0, int(seconds or 0))
    if seconds >= 3600:
        return f"{seconds // 3600} h {seconds % 3600 // 60} min"
    if seconds >= 60:
        return f"{seconds // 60} min"
    return f"{seconds} s"


def cadence(gaps) -> dict:
    """``{words, next}``: the device's own rhythm from the gaps between its requests."""
    gaps = [g for g in gaps or [] if g and g > 0]
    if not gaps:
        return {"words": "one request seen: its cadence is not known yet", "next": ""}
    lo, hi = min(gaps), max(gaps)
    span = ago(lo) if lo == hi else f"{ago(lo)}–{ago(hi)}"
    return {"words": f"its cadence {span}", "next": f"within {ago(hi)}"}


def view(list_name: str, values, now: float = None) -> dict:
    """Everything the Discovered tab draws for one network and question."""
    s = ask(values)
    now = time.time() if now is None else now
    out = {"list": list_name, "s": s, "qs": lambda over=None: qs(list_name, s, over),
           "vendors": VENDORS, "groups": [], "ago": ago}
    st = dhcp_page.stored(list_name, READER_NAME)
    out.update(state=st["state"], why=st.get("why", ""), failed=st.get("failed", ""),
               value_at=st.get("value_at", ""))
    if st["state"] != "ok":
        return out
    value = st["value"]
    out["range"] = value.get("range") or {}
    out["not_listed"] = value.get("not_listed") or {}
    needle = s["q"].lower()

    def keep(d):
        if s["vendor"] == "ciscopnp" and d.get("vendor") != "ciscopnp":
            return False
        if s["vendor"] == "none" and d.get("vendor"):
            return False
        hay = " ".join(str(d.get(k) or "") for k in ("mac", "client_id", "hostname",
                                                     "picked_as")).lower()
        return not needle or needle in hay

    devices = value.get("devices") or []
    shown = 0
    for key, title, words in GROUPS:
        rows = []
        for d in devices:
            if d.get("state") != key or not keep(d):
                continue
            age = now - (d.get("last_asked_ts") or 0)
            rows.append(dict(d, cadence=cadence(d.get("gaps")), quiet_words=ago(age),
                             asking_for=ago((d.get("last_asked_ts") or 0)
                                            - (d.get("first_seen_ts") or 0))))
        shown += len(rows)
        out["groups"].append({"key": key, "title": title, "words": words, "rows": rows,
                              "total": sum(1 for d in devices if d.get("state") == key)})
    out["summary"] = {g["key"]: g["total"] for g in out["groups"]}
    out["total"], out["shown"] = len(devices), shown
    out["subset"] = bool(s["vendor"] or s["q"])
    out["quiet_after"] = ago(QUIET_S)
    return out
