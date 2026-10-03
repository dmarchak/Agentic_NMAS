"""Source of truth > Credentials, its first piece: the break-glass record (board 7, signed off
2026-10-03; NSOT_GUI_BRIEF 3.6's Credentials page).

The record is fleet-wide (every device's credential in a list, and the application key), so its
home is Credentials, and every way in opens it here: the rotation's result, Needs attention's
break-glass row, and today's Settings button.

**No per-device work per request** (the enterprise-scale rule): whether the record holds the
credentials in use is JOB HEALTH's judgement (`breakglass.currency`, every 5 minutes, which
decrypts each credential once per read), read here from its stored rows; the export log and the
browser's verdicts are one file read each. An export made after job health's last read is said
as such: it held the credentials in use when it was made, and the next read judges it.
"""

import logging
import time

log = logging.getLogger(__name__)


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch))) if epoch else ""


def record(list_name: str, cached=None, exports=None, intact=None) -> dict:
    """``{"list", "state", "words", "stale", "last", "checked_at", "errors"}``. *state*:
    ``current``, ``stale`` (devices the record cannot recover), ``not_intact`` (the last
    download did not arrive intact), ``never`` (no export logged), ``unjudged`` (job health has
    not judged it yet), ``unreadable``."""
    import modules.breakglass as bg
    from modules import reader_job
    from modules.config import DATA_DIR

    exports = bg.last_exports(DATA_DIR) if exports is None else exports
    intact = bg.intact_verdicts(DATA_DIR) if intact is None else intact
    cached = reader_job.read_cached("job-health") if cached is None else cached
    errors = []
    for name, got in (("the export log", exports), ("the download verdicts", intact)):
        if got.get("state") == "unreadable":
            errors.append(f"{name} could not be read ({got.get('error')})")
    last = (exports.get("by_list") or {}).get(list_name)
    verdict = (intact.get("by_sha") or {}).get((last or {}).get("sha256") or "") if last else None
    out = {"list": list_name, "stale": [], "errors": errors, "checked_at": "",
           "last": None, "intact": None if not verdict else bool(verdict.get("ok"))}
    if last:
        out["last"] = {"at": _iso(last.get("at")), "actor": last.get("actor", ""),
                       "via": last.get("via", ""), "sha256": last.get("sha256", ""),
                       "key_fingerprint": last.get("key_fingerprint", ""),
                       "devices": len(last.get("devices") or {})}
    if errors and not last:
        out.update(state="unreadable", words="The export log could not be read: whether a "
                                              "record exists is unknown")
        return out
    if not last:
        out.update(state="never", words=f"No export of {list_name}'s record is logged on this "
                                        "host, so nothing says whether one holds the "
                                        "credentials in use")
        return out
    if out["intact"] is False:
        out.update(state="not_intact", words="The last download did not arrive intact: delete "
                                             "the file you saved and export again")
        return out
    good = ((cached or {}).get("doc") or {}).get("last_good") or {}
    jobs = ((good.get("value") or {}).get("health") or {}).get("jobs") or []
    checked = good.get("value_at") or ""
    out["checked_at"] = checked
    mine = [j for j in jobs if j.get("unit") == f"breakglass:{list_name}"
            or str(j.get("unit", "")).startswith(f"breakglass:{list_name}/")]
    exported_after = (not checked) or float(last.get("at") or 0) > _epoch(checked)
    if exported_after:
        out.update(state="current", words=(
            f"Exported {_iso(last.get('at'))}, holding the credentials in use then; job health "
            "judges it again on its next read"))
        if not checked:
            out["state"] = "unjudged"
            out["words"] = ("Job health has not judged the record yet (it reads every 5 "
                            "minutes); the last export held the credentials in use when made")
        return out
    stale = [j for j in mine if j.get("state") == "breakglass_stale"]
    if stale:
        out["stale"] = sorted(j.get("device", "") for j in stale)
        out.update(state="stale", words=(
            f"The record cannot recover {', '.join(out['stale'])}: rotated since it was "
            f"exported ({_iso(last.get('at'))})"))
        return out
    if any(j.get("state") == "ok" for j in mine):
        out.update(state="current", words=f"Every device's credential in use is in the record "
                                          f"exported {_iso(last.get('at'))}")
        return out
    out.update(state="unjudged", words="Job health has no judgement of this record yet")
    return out


def _epoch(iso: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
