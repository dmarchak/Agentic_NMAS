"""Retire a device from NMAS management: the whole exit, not a CSV delete.

OPEN_FINDINGS **C11**. ``POST /device/<ip>/delete`` removes the CSV row and
nothing else, and measured on r5 that leaves the device half-managed in five
places: still bound to its template (every approval keeps validating against
it), still in the clab sync map (reported INCOMPLETE with a false reason, its
file unmapped), still given a heartbeat rule, and its intent and golden in
the working tree. It also destroys the only stored copy of the device's
credential.

**What retire does**, in order, each step skipped if already done so a run
that stops part way is finished by running it again:

1. clears the device's credential override, if it has one;
2. declares its startup config DELIBERATELY UNMAPPED, with who and why
   (``clab_declared_unmapped``), so ``--reconcile`` names a decision instead
   of reporting a gap for ever;
3. removes ``host_vars/<h>.yml`` and ``golden/<h>.cfg`` and releases the
   identity in ONE commit, so history keeps both and the tree does not.
   Releasing changes the template's bound set, which withdraws its approval;
   the plan names each template to re-approve;
4. deletes the CSV row, LAST, and only against a break-glass record that
   holds this device's CURRENT credential.

**The credential is a refusal, not a step.** A sequence whose first step can
be skipped will be skipped, and the CSV row is the only copy NMAS holds of a
rotated password. ``apply`` opens the break-glass record (the passphrase is
read by the CLI from the terminal) and refuses unless it has an entry for
this device in this list whose username and password equal the row's, which
means an export taken before the last rotation does not count.

**What retire does NOT do, stated every time**, because each is correct and
each looks like an omission unless it is named: the NetBox device stays
(NetBox records what exists, not what NMAS manages); Oxidized keeps polling
(NMAS does not write ``router.db``) so config history continues; the
startup config freezes at its last sync; the device's running configuration
is not changed; backups are kept; and a session the app has pooled is not
closed by a command that runs outside it.
"""

import hashlib
import json
import logging
import os
import time

log = logging.getLogger(__name__)


class RetireRefused(Exception):
    pass


def _norm(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _list_paths(list_name: str) -> tuple:
    """(list dir, csv path). From the REGISTRY: a mistyped name is refused,
    never created by `get_list_data_dir()`."""
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists

    match = next((l for l in get_device_lists() if l["name"] == list_name), None)
    if match is None:
        raise RetireRefused(f"no device list named {list_name!r}")
    base = os.path.join(LISTS_DIR, match["filename"])
    return base, os.path.join(base, "devices.csv")


def _is_netbox_sourced(list_dir: str) -> bool:
    try:
        with open(os.path.join(list_dir, "source.json"), encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("type") == "netbox"
    except (OSError, ValueError):
        return False


def _netbox_facts(list_name: str, hostname: str) -> dict:
    try:
        from modules import netbox_guard
        from modules.netbox_client import _nb_first, _nb_ready

        ok, err, session, base = _nb_ready()
        if not ok:
            return {"checked": False, "reason": err}
        dev = _nb_first(session, base, "dcim/devices/", name=hostname)
        if not dev:
            return {"checked": True, "exists": False}
        return {"checked": True, "exists": True, "id": dev["id"],
                "tags": sorted(t.get("slug", "") for t in dev.get("tags") or []),
                "created_by_nmas": netbox_guard.was_created_by_nmas(
                    list_name, "dcim/devices", dev["id"])}
    except Exception as exc:                   # noqa: BLE001
        return {"checked": False, "reason": str(exc)}


def plan(list_name: str, hostname: str, reason: str = "") -> dict:
    """Everything retire would do, everything it will not, and why it would
    refuse. Reads only."""
    from modules.device import load_saved_devices
    from modules.nsot import approval, credential_rotation, manifest, repo as R
    from modules.nsot import templates_repo
    from modules.settings_schema import get_setting

    out = {"ok": True, "list_name": list_name, "hostname": hostname,
           "reason": reason, "refusals": [], "steps": [], "not_doing": [],
           "advisories": []}
    try:
        list_dir, csv_path = _list_paths(list_name)
    except RetireRefused as exc:
        return {**out, "ok": False, "refusals": [str(exc)]}
    repo = os.path.join(list_dir, "config_repo")
    refuse = out["refusals"].append

    if not (reason or "").strip():
        refuse("a reason is required -- it goes into the commit, the "
               "unmapped declaration and the history, and 'retired' on its "
               "own tells the next reader nothing")
    if _is_netbox_sourced(list_dir):
        refuse("this list's inventory is NetBox's: retire the device there")

    row = next((d for d in load_saved_devices(csv_path)
                if d.get("hostname") == hostname), None)
    identity, entry = manifest.find_by_name(repo, hostname)
    rel_intent = f"host_vars/{hostname}.yml"
    rel_golden = f"golden/{hostname}.cfg"
    files = [rel for rel in (rel_intent, rel_golden)
             if os.path.exists(os.path.join(repo, rel))]
    if row is None and identity is None and not files:
        refuse(f"{hostname!r} is not in list {list_name!r}: nothing to retire")
    if hostname in {p.get("name") for p in manifest.pending_devices(repo)}:
        refuse(f"{hostname} is pending onboarding: use abandon, which also "
               "reverses what onboarding created")

    rc, dirty, _e = R.git(repo, "status", "--porcelain", "--",
                          "host_vars", "golden", ".nsot/manifest.json")
    if rc != 0 or dirty.strip():
        refuse("uncommitted changes under host_vars/, golden/ or the "
               "manifest would ride into the retire commit: "
               + (dirty.strip() or "git status failed"))

    ip = (row or {}).get("ip") or (entry or {}).get("mgmt_ip") or ""
    from modules import credentials
    try:
        has_override = bool(ip) and credentials.has_device_override(ip)
    except Exception as exc:                   # noqa: BLE001
        refuse(f"the credential store could not be checked: {exc}")
        has_override = False

    target = credential_rotation.clab_target_for(list_name, hostname)
    startup = os.path.join(target.get("configs_dir") or "?", f"{hostname}.cfg")
    declared = ((get_setting("clab_declared_unmapped") or {})
                .get(list_name) or {}).get(hostname)

    withdrawn = []
    for tpl in approval.approved_templates(repo):
        bound = [b["device"] for b in templates_repo.devices_for_template(repo, tpl)]
        if hostname in bound:
            withdrawn.append({"template": tpl,
                              "re_approve_against": sorted(d for d in bound
                                                           if d != hostname)})

    def step(key, text, done):
        out["steps"].append({"key": key, "what": text, "done": done})

    step("override", f"clear the credential override for {ip}"
         if has_override else "no credential override to clear",
         not has_override)
    step("declare", f"declare {startup} deliberately unmapped: {reason}",
         bool(declared))
    step("commit", "one commit: remove " + (", ".join(files) or "(nothing)")
         + (f" and release identity {identity}" if identity else "")
         + " -- history keeps both",
         identity is None and not files)
    for w in withdrawn:
        out["steps"].append({
            "key": "approval", "done": False,
            "what": (f"this withdraws the approval of {w['template']} (its "
                     "bound set changes); re-approve it against "
                     + ", ".join(w["re_approve_against"]))})
    step("row", f"delete the CSV row for {ip} -- the only stored copy of its "
         "credential, so a break-glass record holding it is required",
         row is None)

    nb = _netbox_facts(list_name, hostname)
    if not nb.get("checked"):
        out["not_doing"].append(f"NetBox: not changed, and could not be asked "
                                f"({nb.get('reason')})")
    elif nb.get("exists"):
        out["not_doing"].append(
            f"NetBox device {nb['id']} is KEPT: NetBox records what exists, not "
            f"what NMAS manages (tags: {', '.join(nb['tags']) or 'none'}). "
            + ("NMAS created it, so its provenance record stays and Remove "
               "could still delete it -- a separate decision."
               if nb["created_by_nmas"] else
               "NMAS did not create it, so Remove cannot touch it."))
    else:
        out["not_doing"].append("NetBox: no device of this name, nothing kept")
    out["not_doing"] += [
        "Oxidized keeps polling it: NMAS does not write router.db, so its "
        "config history continues",
        f"its startup config {startup} freezes at its last sync, declared "
        "deliberately unmapped",
        "its running configuration is not changed",
        "its backups are kept",
        "a session the app has pooled to it is not closed by this command, "
        "which runs outside the app",
    ]
    golden_path = os.path.join(repo, rel_golden)
    if os.path.exists(golden_path):
        with open(golden_path, encoding="utf-8", errors="replace") as fh:
            if "event manager applet NMAS-HEARTBEAT" in fh.read():
                out["advisories"].append(
                    "its golden shows the NMAS-HEARTBEAT applet: the device "
                    "still carries NMAS configuration after it leaves "
                    "management. The deploy path cannot remove it (C12); take "
                    "it off by hand and save the golden first")

    out["ok"] = not out["refusals"]
    out["identity"], out["ip"], out["files"] = identity, ip, files
    out["startup"], out["lab"] = startup, target.get("lab", "")
    out["hash"] = hashlib.sha256(_norm({
        "steps": out["steps"], "reason": reason, "files": {
            rel: _blob(os.path.join(repo, rel)) for rel in files},
        "row": bool(row), "identity": identity}).encode()).hexdigest()[:16]
    return out


def _blob(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def breakglass_covers(payload: dict, list_name: str, row: dict) -> str:
    """"" if *payload* holds this device's CURRENT credential, else why not.
    Compared in memory; nothing is printed or returned but the verdict."""
    from modules.device import decrypt_field

    want_user = row.get("username", "")
    want_pw = decrypt_field(row.get("password", "")) if row.get("password") else ""
    if not want_pw:
        return "the CSV row holds no password to compare"
    hits = [e for e in payload.get("devices", [])
            if e.get("hostname") == row.get("hostname")]
    if not hits:
        return (f"the break-glass record has no entry for "
                f"{row.get('hostname')} -- export again, including it")
    if not any((e.get("list_name") or payload.get("list_name")) == list_name
               for e in hits):
        return "the record's entry is for another list"
    if not any(e.get("password") == want_pw and e.get("username") == want_user
               for e in hits):
        return ("the record holds an OLDER credential for "
                f"{row.get('hostname')} than the one in the CSV row -- it was "
                "exported before the last rotation. Export again")
    return ""


def apply(list_name: str, hostname: str, *, reason: str, actor: str,
          confirmed_hash: str, breakglass: dict = None) -> dict:
    """Run the plan's pending steps, in order. Refuses unless the plan is the
    one confirmed, and deletes the CSV row only against *breakglass*."""
    from modules import credentials
    from modules.device import delete_device, load_saved_devices
    from modules.nsot import manifest, repo as R
    from modules.settings_schema import get_setting, write_settings

    if not actor:
        return {"ok": False, "error": "an actor is required (who is accountable)"}
    p = plan(list_name, hostname, reason)
    if not p["ok"]:
        return {"ok": False, "error": "; ".join(p["refusals"]), "plan": p}
    if p["hash"] != confirmed_hash:
        return {"ok": False, "plan": p, "error": (
            f"the plan changed since you confirmed it ({confirmed_hash} -> "
            f"{p['hash']}). Nothing was done; re-run the plan")}

    list_dir, csv_path = _list_paths(list_name)
    repo = os.path.join(list_dir, "config_repo")
    row = next((d for d in load_saved_devices(csv_path)
                if d.get("hostname") == hostname), None)
    pending = {s["key"] for s in p["steps"] if not s["done"]}
    if "row" in pending:
        if breakglass is None:
            return {"ok": False, "plan": p, "error": (
                "a break-glass record holding this device's current "
                "credential is required before its CSV row -- the only "
                "stored copy -- is deleted: scripts/nmas-breakglass export")}
        why = breakglass_covers(breakglass, list_name, row)
        if why:
            return {"ok": False, "plan": p, "error": "break-glass: " + why}

    done = []

    def fail(step, exc):
        remaining = [s["what"] for s in p["steps"]
                     if not s["done"] and s["key"] not in done]
        log.error("retire: %s failed at %s: %s", hostname, step, exc)
        return {"ok": False, "failed_at": step, "error": str(exc),
                "done": done, "remaining": remaining,
                "note": "run retire again: every step already done is skipped"}

    if "override" in pending:
        try:
            credentials.clear_device_override(p["ip"])
            done.append("override")
        except Exception as exc:               # noqa: BLE001
            return fail("override", exc)

    if "declare" in pending:
        current = dict(get_setting("clab_declared_unmapped") or {})
        per_list = dict(current.get(list_name) or {})
        per_list[hostname] = {"lab": p["lab"], "reason": reason, "by": actor,
                              "at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime())}
        current[list_name] = per_list
        result = write_settings({"clab_declared_unmapped": current}, actor=actor)
        if not result.get("ok"):
            return fail("declare", result.get("error"))
        done.append("declare")

    commit = ""
    if "commit" in pending:
        try:
            for rel in p["files"]:
                rc, _o, err = R.git(repo, "rm", "--quiet", "--", rel)
                if rc != 0:
                    raise RuntimeError(f"git rm {rel}: {err}")
            if p["identity"]:
                rel = manifest.release(repo, p["identity"], list_name, actor,
                                       against="index", retained=("netbox",))
                if not rel.get("ok"):
                    raise RuntimeError(rel.get("error"))
            trailers = [f"Actor: {actor}", "Tool: nmas-retire",
                        f"Retired-Device: {hostname}", f"Reason: {reason}"]
            trailers += [f"Not-Done: {n}" for n in p["not_doing"]]
            result = R._commit_paths(list_name, ["host_vars", "golden", ".nsot"],
                                     f"retire: {hostname} -- {reason}",
                                     trailers, "retire")
            if not result.get("ok"):
                raise RuntimeError(result.get("error"))
            commit = result.get("commit", "")
            done.append("commit")
        except Exception as exc:               # noqa: BLE001
            # Put the tree back, or the next plan sees no files and no
            # identity, counts this step as done, and refuses on the dirty
            # tree it left: a half-state with no way forward.
            R.git(repo, "reset", "-q", "HEAD", "--", "host_vars", "golden", ".nsot")
            R.git(repo, "checkout", "-q", "HEAD", "--", "host_vars", "golden",
                  ".nsot/manifest.json")
            return fail("commit", exc)

    if "row" in pending:
        try:
            delete_device(row["ip"], csv_path)
            done.append("row")
        except Exception as exc:               # noqa: BLE001
            return fail("row", exc)

    return {"ok": True, "done": done, "commit": commit,
            "not_doing": p["not_doing"], "advisories": p["advisories"],
            "re_approve": [s["what"] for s in p["steps"] if s["key"] == "approval"]}
