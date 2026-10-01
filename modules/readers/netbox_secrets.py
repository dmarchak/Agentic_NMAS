"""Does NetBox hold a credential in any device's stored config context? A
reader job (the operator, 2026-09-29).

**What it answers.** NetBox is a shared system, and a credential in a device's
`local_context_data` is readable by everyone who can read NetBox. The import
masks what it writes (C95), `nmas-netbox-mask-context` masks what NMAS wrote
before that (C139), and retire masks on the way out. What none of them can
touch is a context NMAS never wrote (somebody's data), and retire now proceeds
past one, since refusing would leave no path forward. That exposure must not
then be seen by nobody: this reader finds it, and Needs attention draws it
until someone removes it in NetBox.

**Its population is what NetBox HOLDS**, every device NetBox returns, never a
list's inventory: a retired device leaves every list (C139's lesson), and a
device nobody onboarded was never in one. The judgement is the secret-storage
checker's own scan (`netbox_context_mask.checker_scan`), one implementation,
so this and `nmas-check-secret-storage --netbox` cannot disagree. Slots and
counts only, never a value.
"""

from modules import reader_job

INTERVAL_SECONDS = 3600


def read() -> dict:
    """``{"configured", "scanned", "devices": [{id, name, slots, communities,
    positional, wrote}]}``. Raises when NetBox is configured and cannot be
    read, so the failure is a job-health row, never an empty list."""
    from modules.netbox_client import _nb_ready
    from modules.netbox_context_mask import checker_scan, nmas_wrote_context, read_devices
    from modules.netbox_guard import read_modified

    ok, err, session, base = _nb_ready()
    if not ok:
        # Not configured: there is no NetBox to hold anything. Stated, never
        # read as "nothing held" by a consumer that cannot tell.
        return {"configured": False, "why": err, "scanned": 0, "devices": []}
    devices = read_devices(session, base)
    modified, why = read_modified()
    findings = checker_scan()(devices)["findings"]
    by_key = {d.get("name") or d.get("id"): d for d in devices}
    held = []
    for f in findings:
        d = by_key.get(f["device"]) or {}
        held.append({"id": d.get("id"), "name": d.get("name") or f["device"],
                     "slots": list(f.get("slots") or []),
                     "communities": f.get("communities", 0),
                     "positional": bool(f.get("positional")),
                     # Who may mask it: NMAS only where it recorded writing it.
                     "wrote": (nmas_wrote_context(modified, d.get("id"))
                               if modified is not None and d.get("id") is not None else ""),
                     "record_unreadable": why if modified is None else ""})
    return {"configured": True, "scanned": len(devices), "devices": held}


READER = reader_job.register(reader_job.Reader(
    name="netbox-secrets",
    what="whether NetBox holds a credential in any device's stored config context",
    endpoints=("NetBox: GET /api/dcim/devices/ (every device, paged, with its "
               "local_context_data)", "this host: data/netbox_modified.json"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("one paged read of NetBox's devices per cycle; what it finds changes "
                    "only when an import, a mask or a person edits NetBox, so hourly keeps "
                    "an exposure in front of a person without reading NetBox per request"),
    read=read,
    invalidates=("netbox",),
    remedy="Read the error above: it names what NetBox or the record answered",
    window="NetBox's devices at the read",
))
