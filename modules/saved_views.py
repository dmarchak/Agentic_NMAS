"""modules/saved_views.py — History › Query's saved views (C667; boards A and B): a question as
someone asked it (its address: the question, device, interface, range, your own query), saved
with a title for the whole network, who saved it and when, and pinned or not ("Saved by your
team", board A; "Save this view…", board B).

A view is a LINK to a read, never data: saving, pinning or removing one changes no device, no
history and no other store. Kept beside the network's inventory
(`lists/<slug>/saved_views.json`), written whole and atomically under a lock; an unreadable
store refuses every write (writing would erase the views it holds), and absent and unreadable
are different states. Each save, pin and removal is recorded (`saved_views_log.jsonl`).
"""

import json
import logging
import os
import re
import secrets
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

log = logging.getLogger(__name__)

STORE = "saved_views.json"
LOG = "saved_views_log.jsonl"
#: A network's views at most: a list longer than this is no longer read by anyone.
MAX_VIEWS = 100
TITLE_MAX = 80
#: The pages a view may open, and the address keys each carries (History › Query's own).
PATH = re.compile(r"^/v2/history/query/(?:metric/(?:[a-z]+)|syslog)$")
KEYS = ("d", "i", "range", "q", "lang", "sev", "mn", "text", "from", "to")


def _path(list_name: str) -> str:
    from modules.nsot import listref
    return os.path.join(listref.resolve(list_name).data_dir, STORE)


def read(list_name: str) -> dict:
    """``{"state": "absent"|"ok"|"unreadable", "views": [...], "error"}``: pinned first, then
    the newest saved first."""
    path = _path(list_name)
    if not os.path.exists(path):
        return {"state": "absent", "views": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        views = doc.get("views") if isinstance(doc, dict) else None
        if not isinstance(views, list):
            raise ValueError("it holds no views list")
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "views": [], "error": f"{STORE} could not be read: {exc}"}
    # Newest first; saves in one second keep their order (the later one is newer).
    views = sorted(views[::-1], key=lambda v: v.get("at", ""), reverse=True)
    views.sort(key=lambda v: not v.get("pinned"))
    return {"state": "ok", "views": views, "error": ""}


def history(data_dir: str) -> dict:
    """Every save, pin and removal in the network folder *data_dir*, oldest first:
    ``{"rows", "error"}``. Takes the folder (History holds the network's resolved paths), so a
    read never resolves, or creates, one."""
    path = os.path.join(data_dir or "", LOG)
    if not os.path.exists(path):
        return {"rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"rows": [json.loads(l) for l in fh if l.strip()], "error": ""}
    except (OSError, ValueError) as exc:
        return {"rows": [], "error": f"{LOG} could not be read: {exc}"}


def address(text: str) -> tuple:
    """``(address, error)``: *text* as a view's address, the path and the keys History › Query
    reads, in a fixed order; anything else refused by name."""
    parts = urlsplit((text or "").strip())
    if parts.scheme or parts.netloc:
        return "", "a view is an address on this page, not another site"
    if not PATH.match(parts.path):
        return "", f"{parts.path or 'nothing'} is not a History › Query question"
    asked = dict(parse_qsl(parts.query, keep_blank_values=False))
    unknown = sorted(set(asked) - set(KEYS) - {"list"})
    if unknown:
        return "", "the address carries what a question does not read: " + ", ".join(unknown)
    pairs = [(k, asked[k]) for k in KEYS if asked.get(k)]
    return parts.path + ("?" + urlencode(pairs) if pairs else ""), ""


def save(list_name: str, title: str, text: str, actor: str) -> dict:
    """Save the view at address *text* as *title*: ``{"ok", "error", "view"}``."""
    title = " ".join((title or "").split())
    if not title:
        return {"ok": False, "error": "give the view a title: it is how your team finds it"}
    if len(title) > TITLE_MAX:
        return {"ok": False, "error": f"the title is {len(title)} characters; at most {TITLE_MAX}"}
    where, error = address(text)
    if error:
        return {"ok": False, "error": error}
    view = {"id": secrets.token_hex(6), "title": title, "address": where,
            "by": actor or "unauthenticated", "pinned": False,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    def change(views):
        if len(views) >= MAX_VIEWS:
            return f"the network holds {len(views)} saved views, the most it keeps: remove one first"
        views.append(view)
        return ""
    return _change(list_name, actor, "saved", view, change)


def pin(list_name: str, view_id: str, pinned: bool, actor: str) -> dict:
    """Pin a view (it comes first, for everyone) or unpin it."""
    def change(views):
        hit = _find(views, view_id)
        if hit is None:
            return f"no saved view {view_id!r} in this network"
        hit["pinned"] = bool(pinned)
        return ""
    return _change(list_name, actor, "pinned" if pinned else "unpinned", {"id": view_id}, change)


def remove(list_name: str, view_id: str, actor: str) -> dict:
    """Remove a view: only the saved link goes; the history it asks is untouched."""
    def change(views):
        hit = _find(views, view_id)
        if hit is None:
            return f"no saved view {view_id!r} in this network"
        views.remove(hit)
        return ""
    return _change(list_name, actor, "removed", {"id": view_id}, change)


def _find(views, view_id):
    return next((v for v in views if v.get("id") == view_id), None)


def _change(list_name: str, actor: str, action: str, view: dict, change) -> dict:
    from modules import filestore

    path = _path(list_name)
    with filestore.PathLock(lambda: path):
        got = read(list_name)
        if got["state"] == "unreadable":
            return {"ok": False, "error": got["error"] + ": nothing was written"}
        views = [dict(v) for v in got["views"]]
        before = _find(views, view["id"])
        before = dict(before) if before else None
        error = change(views)
        if error:
            return {"ok": False, "error": error}
        full = _find(views, view["id"]) or before or view
        filestore.write_atomic(path, json.dumps({"views": views}, indent=1, sort_keys=True))
    log.info("saved_views: %s %s view %s in %s", actor, action, view["id"], list_name)
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "action": action,
             "id": view["id"], "title": full.get("title", ""), "address": full.get("address", ""),
             "actor": actor or "unauthenticated", "list": list_name}
    out = {"ok": True, "error": "", "view": full, "action": action, "recorded": True,
           "record_error": ""}
    try:
        with open(os.path.join(os.path.dirname(path), LOG), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("saved_views: COULD NOT RECORD %s of %s by %s (%s)", action, view["id"], actor,
                  exc)
        out.update(recorded=False, record_error=f"{LOG} could not be written: {exc}")
    return out
