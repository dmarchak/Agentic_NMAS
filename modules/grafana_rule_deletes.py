"""The alert rules Mercury generates leave Grafana only when a file names them (C1419).

Grafana 13.2 keeps a provisioned rule its file has dropped: a retirement in Lab 8 (step 1,
2026-10-20) removed the device's heartbeat rule from the generated file and installed it, and
Grafana kept that rule and the device's telemetry rules running until a one-off file naming
them under ``deleteRules`` was installed and Grafana restarted (C1419's stopgap host step, PASS
11 of 11). That one-off shape is the measured one, so it is the shape here: each generator writes,
beside its rules file, ``<rules>-delete.yaml`` naming every rule in its OWN uid range that
Grafana or the installed file holds and the new file no longer generates; the one install step
(`scripts/host-steps/c1419-install-alert-rules.sh`) installs both, restarts Grafana, proves the
named rules gone and every generated rule present, and then removes the delete file, so a later
restart never deletes a rule of the same uid generated again (a device onboarded again under
the name). Computed afresh at every write, never carried: a rule generated again leaves the list
at once. What Grafana holds is read through its API; when it cannot be read, the installed file
alone decides, and the writer says so."""

import logging
import os

log = logging.getLogger(__name__)

#: Grafana's organisation the generated rules live in (the provisioning files' `orgId`).
ORG_ID = 1
#: Where Grafana loads the generated files from.
ALERTING = "/etc/grafana/provisioning/alerting"
#: Grafana's provisioning API for alert rules (a read).
RULES_API = "api/v1/provisioning/alert-rules"
#: The one install step for a generated rules file and its delete file.
INSTALL_STEP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "scripts", "host-steps", "c1419-install-alert-rules.sh")


def rule_uids(doc) -> set:
    """Every rule uid a provisioning document's groups hold."""
    return {str(r.get("uid")) for g in (doc or {}).get("groups") or []
            for r in g.get("rules") or [] if r.get("uid")}


def _read_doc(path: str) -> dict:
    """The provisioning document at *path*, or ``{}`` when there is none; unreadable raises."""
    import yaml

    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}


def live_uids(prefix: str, client=None) -> tuple:
    """``(uids, why_not)``: the uids starting with *prefix* among Grafana's alert rules, read
    through its API, or ``(None, why)`` when they cannot be read."""
    try:
        from modules.integrations.grafana import GrafanaIntegration

        g = client or GrafanaIntegration()
        if not g.is_configured():
            return None, "Grafana is not configured (grafana_url)"
        got = g._get(RULES_API)                          # noqa: SLF001 - the client's API
        if not got.get("ok"):
            return None, f"Grafana's alert rules could not be read ({got.get('error')})"
        return {str(r.get("uid") or "") for r in got["response"].json()
                if str(r.get("uid") or "").startswith(prefix)}, ""
    except Exception as exc:                          # noqa: BLE001 - said by the caller
        return None, f"Grafana's alert rules could not be read ({type(exc).__name__}: {exc})"


def deletions(new_doc: dict, prefix: str, installed_path: str, live=None) -> list:
    """The uids in *prefix*'s range that Grafana (*live*, None when unread) or the installed
    file holds and *new_doc* no longer generates, sorted."""
    held = set(live or ()) | rule_uids(_read_doc(installed_path))
    keep = rule_uids(new_doc)
    return sorted(u for u in held if u.startswith(prefix) and u not in keep)


def delete_path(rules_path: str) -> str:
    """The delete file beside *rules_path*: ``nmas-heartbeat.yaml`` -> ``nmas-heartbeat-delete.yaml``."""
    base, ext = os.path.splitext(rules_path)
    return f"{base}-delete{ext or '.yaml'}"


def delete_text(uids: list) -> str:
    """The one-off provisioning file naming *uids* under ``deleteRules``."""
    import yaml

    head = ("# GENERATED beside its rules file (C1419): the rules it no longer generates, for\n"
            "# Grafana to delete. Installed once by c1419-install-alert-rules.sh and removed\n"
            "# after; never left where a later restart would read it.\n")
    return head + yaml.safe_dump({"apiVersion": 1, "deleteRules": [
        {"orgId": ORG_ID, "uid": u} for u in uids]}, sort_keys=False)


def write(rules_path: str, uids: list) -> str:
    """Write *rules_path*'s delete file naming *uids*, or remove a stale one when there are
    none. Returns the delete file's path, or ``""`` when none is written."""
    from modules.filestore import write_atomic

    path = delete_path(rules_path)
    if not uids:
        if os.path.exists(path):
            os.remove(path)
        return ""
    write_atomic(path, delete_text(uids))
    return path


def write_beside(doc: dict, prefix: str, rules_path: str, kind: str, live=...) -> list:
    """For a generator script that has just written *rules_path*: write its delete file and
    return the lines to print (what it names, whether Grafana was read, the install step)."""
    installed = os.path.join(ALERTING, os.path.basename(rules_path))
    got = plan(doc, prefix, installed, live=live)
    path = write(rules_path, got["uids"])
    lines = [f"wrote {len(got['uids'])} rule(s) for Grafana to delete to {path}: "
             + ", ".join(got["uids"]) if got["uids"] else
             "no rule for Grafana to delete: every rule Grafana or the installed file holds in "
             "this range is still generated"]
    if got["said"]:
        lines.append("NOTE: " + got["said"])
    lines.append(f"Install with: bash {INSTALL_STEP} {kind} {rules_path} {installed}")
    return lines


def plan(new_doc: dict, prefix: str, installed_path: str, client=None, live=...) -> dict:
    """``{"uids", "live_read", "said"}`` for one write: what the delete file will name, and
    whether Grafana's own rules were read (when not, *said* names why, and only the installed
    file decided). *live* (tests) replaces the read: a set, or None for "could not be read"."""
    why = ""
    if live is ...:
        live, why = live_uids(prefix, client)
    uids = deletions(new_doc, prefix, installed_path, live)
    said = "" if live is not None else (
        f"Grafana's own rules were not read ({why or 'not asked'}): only the installed file "
        "decided which rules to delete, so a rule Grafana kept from an earlier install stays "
        "until this is written with Grafana readable")
    return {"uids": uids, "live_read": live is not None, "said": said}
