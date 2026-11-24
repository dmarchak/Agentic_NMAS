"""What the toolbar assistant is looking at (stage 2; docs/design/assistant.md, "Aware of where
the person is"): the page's path, resolved by the server against its own URL map, never parsed
in the browser, into the **screen**, the **network**, the **device** (a device page) and the
**incident** (an incident page), and the words the panel's head draws ("Looking at: edge1
(device) · Default").

**What it reads.** The application's URL map (`flask.current_app.url_map`), the path the panel
was asked with, and the network its request names (`routes/page_network` writes the page's own
network into every request the page makes). Nothing else: no store, no device, no NetBox. A
device or incident a path names is taken by its shape only (`router_reads.DEVICE`,
`fixit.incident.valid_id`); whether it exists is the press's to find (`assistant.scope_of`),
so opening the panel stays a read of the thread and nothing more.

**The screen** is the sidebar's: a device page is Devices, an incident's page Incidents, any
other page the screen of its sidebar item (`NAV_SCREENS`, the page's own ``active_nav``, as
stage 1 ranked it); a path the map does not hold names none.
"""
import logging
import re
from urllib.parse import parse_qsl, urlsplit

log = logging.getLogger(__name__)

#: The sidebar item a page draws as active (`base.html`'s ``active_nav``) and its screen, as the
#: manual names it (`manual.SCREENS`).
NAV_SCREENS = {"attention": "Needs attention", "devices": "Devices", "history": "History",
               "incidents": "Incidents", "fixes": "Fixes", "monitoring": "Monitoring",
               "topology": "Topology", "sdn": "SDN", "show_commands": "Show commands",
               "logs": "Logs", "dhcp": "DHCP", "intent": "Intent", "templates": "Templates",
               "netbox": "NetBox", "credentials": "Credentials", "help": "Help",
               "settings": "Settings"}
#: The pages that are about one device, or one incident, by their blueprint, and the path
#: argument that names it.
DEVICE_BLUEPRINTS = {"device_v2": "name", "intent_v2": "name"}
INCIDENT_BLUEPRINTS = {"incident_v2": "incident_id", "fixit_v2": "incident_id"}
#: The longest path taken: a page's address, never a pasted document.
MAX_PATH = 600


def _blank(network: str, screen: str) -> dict:
    return {"asked": "", "path": "", "endpoint": "", "screen": screen, "network": network,
            "device": "", "incident": "", "tab": ""}


def resolve(path: str, *, network: str = "", nav: str = "") -> dict:
    """``{"asked", "path", "endpoint", "screen", "network", "device", "incident", "tab",
    "label"}`` for the page at *path* (its path and query, as the page's own request named it;
    *asked*, kept for the panel's Ask to send again), on *network* (the panel's request's).
    *nav* is the page's sidebar item (stage 1's), the screen when the path names none of its
    own. A path the URL map does not hold, or one that is not a path on this host, names no
    device or incident; never raises."""
    from flask import current_app
    from werkzeug.exceptions import HTTPException
    from werkzeug.routing import RequestRedirect

    from modules.ai import router_reads as RR
    from modules.fixit import incident as F

    out = _blank(network, NAV_SCREENS.get(nav or "", ""))
    text = str(path or "").strip()[:MAX_PATH]
    parts = urlsplit(text)
    # Only a path on this host: no scheme, no host, one leading slash.
    if not text.startswith("/") or text.startswith("//") or parts.scheme or parts.netloc:
        return dict(out, label=label(out))
    try:
        endpoint, args = current_app.url_map.bind("localhost").match(parts.path, method="GET")
    except (HTTPException, RequestRedirect) as exc:
        log.info("assistant: the path %r is not one of Mercury's pages (%s)", parts.path[:80],
                 type(exc).__name__)
        return dict(out, label=label(out))
    query = dict(parse_qsl(parts.query))
    out.update(asked=text, path=parts.path, endpoint=endpoint)
    blueprint = endpoint.partition(".")[0]
    if blueprint in DEVICE_BLUEPRINTS:
        name = str(args.get(DEVICE_BLUEPRINTS[blueprint]) or "")
        if re.fullmatch(RR.DEVICE, name):
            tab = query.get("tab", "")
            out.update(device=name, screen="Devices",
                       tab=tab if re.fullmatch(r"[a-z]{1,20}", tab or "") else "")
    elif blueprint in INCIDENT_BLUEPRINTS:
        iid = str(args.get(INCIDENT_BLUEPRINTS[blueprint]) or "")
        if F.valid_id(iid):
            out.update(incident=iid, screen="Incidents")
    return dict(out, label=label(out))


def label(place: dict) -> str:
    """The panel head's words: what the assistant is looking at, then the network."""
    if place.get("device"):
        what = f"{place['device']} (device)"
    elif place.get("incident"):
        what = f"incident {place['incident']}"
    else:
        what = place.get("screen") or ""
    net = place.get("network") or ""
    return " · ".join(w for w in (what, net) if w)
