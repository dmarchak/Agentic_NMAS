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
   Template approvals are NOT withdrawn: scheme 3 approves the template,
   never its devices (P.5), so the plan says so rather than asking for a
   re-approval nobody needs (it did until 2026-09-28, true only before P.5);
0. FIRST, masks the credentials NetBox still holds in the device's stored config
   context, when NetBox writes are on and NMAS recorded writing that context
   (C139: after retire no import reaches the device again, so a credential
   left there stays for good). One implementation with
   `scripts/nmas-netbox-mask-context` (`modules/netbox_context_mask.py`),
   read back after the write. It is the first step, so a failed mask stops
   the retirement with nothing else done;
4. after the commit, deletes the device's file from the deprecated `golden_configs/` store
   (C176), but only when its content survives in the repository (the
   migration's verbatim backup or an equivalent committed golden), and says
   where; a file whose lines exist nowhere else is kept and named;
5. deletes the CSV row, LAST, and only against a break-glass record that
   holds this device's CURRENT credential.

The steps were modelled on r5's retirement (`3592113`, 2026-09-25, the
operator's model for 7.3): its six `Not-Done:` trailers are the list the
screen draws before the confirm and again in the result, and the gaps that
retirement left (the legacy file, the heartbeat rule, the scrape targets,
NetBox's stored credentials) are closed here or named with who closes them.

**The credential is a refusal, not a step.** A sequence whose first step can
be skipped will be skipped, and the CSV row is the only copy NMAS holds of a
rotated password. Two bases, and each says which it is:

- the CLI (``nmas-retire --breakglass <file>``) OPENS the record (the
  passphrase read from the terminal) and refuses unless it has an entry for
  this device in this list whose username and password equal the row's;
- the Device page cannot open a record on the operator's laptop, so it
  trusts the EXPORT LOG (C182): the newest export for this list must have
  recorded this device's current credential digest. The log says what was
  WRITTEN; it cannot show the file still exists or that its passphrase is
  known. The screen states that difference (the operator, 2026-09-28).

Either way an export taken before the last rotation does not count.

**What retire does NOT do, stated every time**, because each is correct and
each looks like an omission unless it is named: the NetBox device stays
(NetBox records what exists, not what NMAS manages); the
startup config freezes at its last sync; the device's running configuration
is not changed; backups are kept; and a session the app has pooled is not
closed by a command that runs outside it. (Oxidized's polling was named here until
Oxidized was retired, Phase 3, 2026-10-08.)

**What watches it afterwards, in two kinds** (board 12, the operator,
2026-10-03; `_watchers`): GENERATED, dropped at the next regeneration and
said with when (Prometheus's scrape targets, generated from the inventory
when a target directory is set, drop a device with no golden at the
keeper's next run; the heartbeat rule, generated from committed intent, is
named EXTRA by the hourly check until the windows are re-measured), and
SURVIVES, named with how it is removed (the NetBox device,
a hand-built dashboard panel, the template's approval).
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
            # NOT CONFIGURED is its own fact: there is no NetBox to hold
            # anything. An unreachable one is not (below, `configured` True).
            return {"checked": False, "configured": False, "reason": err}
        dev = _nb_first(session, base, "dcim/devices/", name=hostname)
        if not dev:
            return {"checked": True, "exists": False}
        return {"checked": True, "exists": True, "id": dev["id"], "device": dev,
                "writes": netbox_guard.writes_allowed(),
                "tags": sorted(t.get("slug", "") for t in dev.get("tags") or []),
                "created_by_nmas": netbox_guard.was_created_by_nmas(
                    list_name, "dcim/devices", dev["id"])}
    except Exception as exc:                   # noqa: BLE001
        return {"checked": False, "configured": True, "reason": str(exc)}


def plan(list_name: str, hostname: str, reason: str = "") -> dict:
    """Everything retire would do, everything it will not, and why it would
    refuse. Reads only."""
    from modules.device import load_saved_devices
    from modules.nsot import approval, credential_rotation, manifest, repo as R
    from modules.nsot import templates_repo
    from modules.settings_schema import get_setting

    out = {"ok": True, "list_name": list_name, "hostname": hostname,
           "reason": reason, "refusals": [], "refused_by": {}, "steps": [],
           "not_doing": [], "advisories": []}
    try:
        list_dir, csv_path = _list_paths(list_name)
    except RetireRefused as exc:
        return {**out, "ok": False, "refusals": [str(exc)], "refused_by": {"list": str(exc)}}
    repo = os.path.join(list_dir, "config_repo")

    def refuse(key, text):
        # Keyed as well as listed: the screen draws each check as a gate by
        # name (REFUSAL_GATES), and a refusal with no gate would be a
        # reason drawn nowhere.
        out["refusals"].append(text)
        out["refused_by"][key] = text

    if not (reason or "").strip():
        refuse("reason", "a reason is required -- it goes into the commit, the "
               "unmapped declaration and the history, and 'retired' on its "
               "own tells the next reader nothing")
    if _is_netbox_sourced(list_dir):
        refuse("source", "this list's inventory is NetBox's: retire the device there")

    row = next((d for d in load_saved_devices(csv_path)
                if d.get("hostname") == hostname), None)
    identity, entry = manifest.find_by_name(repo, hostname)
    from modules.nsot.hostvars import committed_rel
    rel_intent = committed_rel(hostname)      # the one producer (C175)
    rel_golden = f"golden/{hostname}.cfg"
    files = [rel for rel in (rel_intent, rel_golden)
             if os.path.exists(os.path.join(repo, rel))]
    if row is None and identity is None and not files:
        refuse("present", f"{hostname!r} is not in list {list_name!r}: nothing to retire")
    if hostname in {p.get("name") for p in manifest.pending_devices(repo)}:
        refuse("pending", f"{hostname} is pending onboarding: use abandon, which also "
               "reverses what onboarding created")

    rc, dirty, _e = R.git(repo, "status", "--porcelain", "--",
                          "host_vars", "golden", ".nsot/manifest.json")
    if rc != 0 or dirty.strip():
        refuse("clean", "uncommitted changes under host_vars/, golden/ or the "
               "manifest would ride into the retire commit: "
               + (dirty.strip() or "git status failed"))

    ip = (row or {}).get("ip") or (entry or {}).get("mgmt_ip") or ""
    from modules import credentials
    try:
        has_override = bool(ip) and credentials.has_device_override(ip)
    except Exception as exc:                   # noqa: BLE001
        refuse("credentials", f"the credential store could not be checked: {exc}")
        has_override = False

    target = credential_rotation.clab_target_for(list_name, hostname)
    startup = os.path.join(target.get("configs_dir") or "?", f"{hostname}.cfg")
    declared = ((get_setting("clab_declared_unmapped") or {})
                .get(list_name) or {}).get(hostname)

    # Scheme 3 (P.5) approves the TEMPLATE, never its devices: releasing one
    # changes no approval. This listed "this withdraws the approval ...
    # re-approve it" until 2026-09-28, which was true for r5's retirement
    # (2026-09-25, scheme 2) and false from the next day on.
    still_approved = [tpl for tpl in approval.approved_templates(repo)
                      if hostname in {b["device"] for b in
                                      templates_repo.devices_for_template(repo, tpl)}]

    def step(key, text, done):
        out["steps"].append({"key": key, "what": text, "done": done})

    # The mask goes FIRST: a failed mask then stops the retirement with
    # nothing else done (C139).
    nb = _netbox_facts(list_name, hostname)
    mask = _mask_facts(nb)
    if mask.get("refuse"):
        refuse("netbox_mask", mask["refuse"])
    if mask.get("step"):
        step("netbox_mask", mask["step"], mask["done"])
    step("override", f"clear the credential override for {ip}"
         if has_override else "no credential override to clear",
         not has_override)
    step("declare", f"declare {startup} deliberately unmapped: {reason}",
         bool(declared))
    step("commit", "one commit: remove " + (", ".join(files) or "(nothing)")
         + (f" and release identity {identity}" if identity else "")
         + " -- history keeps both",
         identity is None and not files)
    legacy = _legacy_facts(list_name, list_dir, hostname, ip)
    if legacy.get("step"):
        step("legacy", legacy["step"], legacy["done"])
    # Oxidized's router.db row (C398) is no longer a step: Oxidized is retired (Phase 3 step 2,
    # 2026-10-08), and its store goes with it (Phase 3 section 5's host steps).
    step("row", f"delete the CSV row for {ip} -- the only stored copy of its "
         "credential, so a break-glass record holding it is required",
         row is None)

    if not nb.get("checked"):
        out["not_doing"].append(f"NetBox: not changed, and could not be asked "
                                f"({nb.get('reason')})")
    elif nb.get("exists"):
        out["not_doing"].append(
            f"NetBox device {nb['id']} is KEPT: NetBox records what exists, not "
            f"what Mercury manages (tags: {', '.join(nb['tags']) or 'none'}). "
            + ("Mercury created it, so its provenance record stays and Remove "
               "could still delete it -- a separate decision."
               if nb["created_by_nmas"] else
               "Mercury did not create it, so Remove cannot touch it.")
            + (" " + mask["kept"] if mask.get("kept") else ""))
    else:
        out["not_doing"].append("NetBox: no device of this name, nothing kept")
    for tpl in still_approved:
        out["not_doing"].append(
            f"the approval of {tpl} is not withdrawn: an approval is of the template, "
            f"never of its devices (scheme 3), so it stays approved; its recorded "
            f"evidence still names {hostname}, as history")
    out["not_doing"] += [n for n in (mask.get("not_doing"), legacy.get("not_doing")) if n]
    # Board 12: what is GENERATED is dropped at its next regeneration, said with when; what
    # SURVIVES is named with how it is removed. Both are the commit's Not-Done trailers too.
    watchers = _watchers(hostname, ip)
    out["generated"] = [w for w in watchers if w["kind"] == "generated"]
    out["survives"] = [w for w in watchers if w["kind"] == "survives"]
    if nb.get("checked") and nb.get("exists"):
        out["survives"].insert(0, {
            "kind": "survives", "what": f"the NetBox device {nb['id']}",
            "how": ("KEPT, its credential masked: delete it in NetBox if it is gone for good"
                    + (" (Mercury created it, so Remove could also delete it, a separate "
                       "decision)" if nb["created_by_nmas"] else
                       " (Mercury did not create it, so Mercury never deletes it)"))})
    out["survives"] += [{"kind": "survives", "what": f"the approval of {tpl}",
                         "how": "stays: an approval is of the template, never of its devices"}
                        for tpl in still_approved]
    out["not_doing"] += [f"{w['what']}: {w['how']}" for w in watchers]
    out["not_doing"] += [
        f"its startup config {startup} freezes at its last sync, declared "
        "deliberately unmapped",
        "its running configuration is not changed",
        "its backups are kept",
        "a session the app has pooled to it is not closed by this command, "
        "which runs outside the app; the app's idle reaper closes it within "
        "two minutes of its last use (C97)",
    ]
    golden_path = os.path.join(repo, rel_golden)
    if os.path.exists(golden_path):
        with open(golden_path, encoding="utf-8", errors="replace") as fh:
            if "event manager applet NMAS-HEARTBEAT" in fh.read():
                out["advisories"].append(
                    "its golden shows the NMAS-HEARTBEAT applet: the device "
                    "still carries Mercury's configuration after it leaves "
                    "management. The deploy path cannot remove it (C12); take "
                    "it off by hand and save the golden first")

    out["ok"] = not out["refusals"]
    if mask.get("advisory"):
        out["advisories"].append(mask["advisory"])
    out["identity"], out["ip"], out["files"] = identity, ip, files
    out["legacy_path"] = legacy.get("path", "")
    out["startup"], out["lab"] = startup, target.get("lab", "")
    out["breakglass_log"] = (breakglass_logged(list_name, row) if row is not None
                             else {"ok": True, "why": "", "export": None,
                                   "statement": "no CSV row: no credential to protect"})
    out["hash"] = hashlib.sha256(_norm({
        "steps": out["steps"], "reason": reason, "files": {
            rel: _blob(os.path.join(repo, rel)) for rel in files},
        "row": bool(row), "identity": identity}).encode()).hexdigest()[:16]
    return out


def _mask_facts(nb: dict) -> dict:
    """What retire does about the credentials NetBox holds in the device's
    stored context (C139). A step only when NMAS may and can mask them;
    otherwise a Not-Done line saying exactly why they stay."""
    # COULD NOT CHECK REFUSES (the operator's decision, 2026-09-29): "couldn't
    # read it" is not "nothing there", absent against unreadable. A NetBox that
    # is not configured at all holds nothing, and proceeds.
    if not nb.get("checked") and nb.get("configured"):
        return {"refuse": (f"NetBox could not be read ({nb.get('reason')}), so whether it "
                           "still holds this device's credentials cannot be told, and once "
                           "it leaves no import reaches it again (C139). Could not read is "
                           "not nothing there: preview again when NetBox answers")}
    if not nb.get("exists"):
        return {}
    from modules.netbox_context_mask import assess_device

    a = assess_device(nb["device"])
    where = f"NetBox device {nb['id']}"
    if a["holds"] is None:
        return {"refuse": (f"{where}: whether it still holds a credential in its stored "
                           f"config context could not be checked ({a['why']}). Could not "
                           "check is not nothing there: preview again when it can be read")}
    if a["holds"] is False:
        return {"step": f"{where} holds no unmasked credential in its stored context: "
                        "nothing to mask", "done": True,
                "kept": "It holds no unmasked credential."}
    if not a["may"]:
        # PROCEEDS (the operator's decision, 2026-09-29): NMAS cannot mask what
        # it did not write, and refusing would block the retirement with no path
        # forward. The exposure it leaves is a Needs attention row, from the
        # netbox-secrets reader, until someone removes it in NetBox.
        return {"not_doing": (f"{where}'s stored config context is NOT masked: {a['why']}. "
                              "It stays a Needs attention row (NetBox holds a credential) "
                              "until someone removes it in NetBox")}
    if not nb.get("writes"):
        # REFUSED, not proceeded past (the operator's decision, 2026-09-29):
        # reads work with writes off, so the tool knows the credential is
        # there, and once the device leaves no import reaches it again. That
        # is C139 recurring, so the retirement waits for the mask.
        return {"refuse": (
            f"{where} still holds credentials in its stored config context "
            f"({a['why'].split(';')[0].replace('NetBox holds ', '')}), and NetBox writes are "
            "off here (netbox_allow_writes), so retire cannot mask them. Once this device "
            "leaves, no import reaches it again (C139). Turn writes on and preview again, or "
            f"run scripts/nmas-netbox-mask-context --device {nb['device'].get('name')} --apply "
            "and then retire")}
    return {"step": (f"mask the credentials {where} still holds in its stored config "
                     f"context ({a['why']}); written with the import's own masking and "
                     "read back"), "done": False}


def _legacy_facts(list_name: str, list_dir: str, hostname: str, ip: str) -> dict:
    """The device's file in the deprecated `golden_configs/` store (C176):
    deleted only when its content survives in the repository, and the step
    says where; kept and named otherwise (an action that removes data says
    whether the data survives)."""
    from modules.nsot.repo import legacy_only_goldens

    try:
        entries = legacy_only_goldens(list_dir, set())
    except Exception as exc:                   # noqa: BLE001
        return {"not_doing": f"the deprecated golden_configs/ store could not be read ({exc})"}
    entry = next((e for e in entries
                  if (e.get("hostname") or "").lower() == hostname.lower()
                  or (ip and e.get("device_ip") == ip)), None)
    if entry is None:
        return {"step": "no file in the deprecated golden_configs/ store", "done": True}
    path = os.path.join(list_dir, "golden_configs", entry["file"])
    from routes.golden import _legacy_survives        # one survival check (C176)

    surv = _legacy_survives(list_name, hostname, path)
    if surv["state"] == "survives":
        return {"step": f"delete {path} from the deprecated golden_configs/ store: "
                        + surv["words"], "done": False, "path": path}
    return {"not_doing": (f"{path} in the deprecated golden_configs/ store is KEPT: "
                          f"{surv['words']} Keep a copy before deleting it by hand."),
            "path": ""}


def _heartbeat_rules_path(hb) -> str:
    """Where the generator writes its rules: on the host, never committed.
    A seam, so a test reads a real rules document instead of the checkout's
    (which has none)."""
    return hb.OUT


def _watchers(hostname: str, ip: str) -> list:
    """What still watches the device after it leaves, each ``{"kind", "what", "how"}``:
    GENERATED (the tool regenerates it from what retire removes, so it is dropped at the next
    regeneration, said with when) or SURVIVES (nobody regenerates it: named with how it is
    removed). Board 12 (the operator, 2026-10-03). Each names what was READ."""
    out = []

    def item(kind, what, how):
        out.append({"kind": kind, "what": what, "how": how})

    try:
        import importlib.machinery
        import importlib.util

        import yaml

        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "scripts", "nmas-heartbeat-rules")
        loader = importlib.machinery.SourceFileLoader("nmas_heartbeat_rules", path)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        hb = importlib.util.module_from_spec(spec)
        loader.exec_module(hb)
        rules_path = _heartbeat_rules_path(hb)
        if not os.path.exists(rules_path):
            item("generated", "its Grafana heartbeat rule",
                 f"generated from committed intent, which leaves with this commit; the "
                 f"generated rules file ({rules_path}) is not here, so whether one names it is "
                 "unknown: the hourly check names one EXTRA if it does, and re-measuring the "
                 "heartbeat windows (Monitoring, then its host step) removes it")
        else:
            with open(rules_path, encoding="utf-8") as fh:
                rules = hb.installed(yaml.safe_load(fh) or {})
            if hostname in rules:
                item("generated", f"its Grafana heartbeat rule (window {rules[hostname][0]} s)",
                     "generated from committed intent, which leaves with this commit: the "
                     "hourly check names it EXTRA until the windows are re-measured and the "
                     "rules installed without it (Monitoring, then its host step)")
            else:
                item("generated", "its Grafana heartbeat rule",
                     "none names it (the generated rules file was read)")
    except Exception as exc:                   # noqa: BLE001
        item("generated", "its Grafana heartbeat rule",
             f"the generated rules file could not be read ({exc}), so whether one names it is "
             "unknown")
    try:
        from modules import prometheus_targets

        if prometheus_targets.target_dir():
            item("generated", "Prometheus's scrape targets",
                 f"generated from the inventory, and a device with no committed golden is no "
                 f"target: retire's commit removes {hostname}'s golden, so the targets keeper "
                 "drops it at its next run, and the result reads the target files back")
        else:
            from modules.integrations import get_integration

            prom = get_integration("prometheus")
            if prom is None or not prom.is_configured():
                item("survives", "Prometheus's scrape targets",
                     f"not generated here (no target directory is set) and Prometheus is not "
                     f"configured, so whether its targets still poll {ip or hostname} is "
                     "unknown: remove it where Prometheus is configured")
            else:
                t = prom.targets_for(ip)
                if not t["ok"]:
                    item("survives", "Prometheus's scrape targets",
                         f"not generated here (no target directory is set), and Prometheus "
                         f"could not be asked ({t['error']}): remove {ip} where its targets "
                         "are configured")
                elif t["count"]:
                    item("survives", "Prometheus's scrape targets",
                         f"Prometheus still scrapes {ip} ({t['count']} target(s), job "
                         f"{', '.join(t['jobs'])}), and its targets are not generated here "
                         "(no target directory is set): remove them where they are "
                         "configured")
                else:
                    item("survives", "Prometheus's scrape targets",
                         f"Prometheus scrapes nothing at {ip} (its active targets were read): "
                         "nothing to remove")
    except Exception as exc:                   # noqa: BLE001
        item("survives", "Prometheus's scrape targets", f"could not be checked ({exc})")
    item("survives", "a hand-built Grafana dashboard panel naming it",
         "stays until removed in Grafana: Mercury does not edit dashboards")
    return out


def targets_after(hostname: str, ip: str) -> dict:
    """After retire's commit, regenerate Prometheus's targets now (the keeper the commit
    woke does the same) and READ THE FILES BACK: ``{"state", "statement", "at"}``, state one
    of ``dropped``, ``still`` (a file still names it), ``failed`` (the regeneration did not
    happen) or ``not_managed`` (no target directory is set, so the tool writes none)."""
    from modules import prometheus_targets as PT

    directory = PT.target_dir()
    if not directory:
        return {"state": "not_managed", "at": "",
                "statement": "Prometheus's targets are not generated here (no target "
                             "directory is set)"}
    rec = PT.sync(f"retire of {hostname}")
    if not rec.get("ok"):
        return {"state": "failed", "at": rec.get("at", ""),
                "statement": (f"Prometheus's targets were NOT regenerated "
                              f"({rec.get('error') or 'no reason recorded'}): the keeper "
                              "tries again at its next run")}
    still = []
    for name in sorted(os.listdir(directory)):
        if not (name.startswith(PT.PREFIX) and name.endswith(".json")):
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as fh:
            groups = json.load(fh) or []
        if any((g.get("labels") or {}).get("device") == hostname
               or (ip and ip in (g.get("targets") or [])) for g in groups):
            still.append(name)
    if still:
        return {"state": "still", "at": rec["at"],
                "statement": (f"Prometheus's targets were regenerated, and still name "
                              f"{hostname} ({', '.join(still)}, read back at {rec['at']})")}
    return {"state": "dropped", "at": rec["at"],
            "statement": f"Prometheus's targets were regenerated without {hostname} (read "
                         f"back at {rec['at']})"}


def retired_record(repo: str, hostname: str):
    """The newest retire commit of *hostname* in *repo* (its `Retired-Device:` trailer, matched
    exactly), as ``{"sha", "at", "actor", "verified", "reason"}``, or None: what the device's
    address shows once it has left (C185; board 12). A read of git only."""
    from modules.nsot import repo as R

    rc, out, _err = R.git(repo, "log", "--format=%H%x1f%cI%x1f%B%x1e", "--fixed-strings",
                          f"--grep=Retired-Device: {hostname}")
    if rc != 0:
        return None
    for chunk in out.split("\x1e"):
        parts = chunk.strip().split("\x1f")
        if len(parts) != 3:
            continue
        sha, at, body = parts
        trailers = {}
        for line in body.splitlines():
            key, sep, value = line.partition(": ")
            if sep and key in ("Retired-Device", "Actor", "Actor-Verified", "Reason"):
                trailers.setdefault(key, value.strip())
        if trailers.get("Retired-Device") == hostname:
            return {"sha": sha, "at": at, "actor": trailers.get("Actor", ""),
                    "verified": trailers.get("Actor-Verified", ""),
                    "reason": trailers.get("Reason", ""),
                    "ip": _address_before(repo, sha, hostname)}
    return None


def _address_before(repo: str, sha: str, hostname: str) -> str:
    """The device's management address as the manifest held it just before its retire commit
    (the commit releases it), or "" when it cannot be read. A read of git only."""
    from modules.nsot import repo as R

    rc, out, _err = R.git(repo, "show", f"{sha}^:{R.MANIFEST_REL}")
    if rc != 0:
        return ""
    try:
        devices = (json.loads(out) or {}).get("devices") or {}
    except ValueError:
        return ""
    for entry in devices.values():
        if (entry.get("name") or "").lower() == hostname.lower():
            return entry.get("mgmt_ip") or ""
    return ""


def _blob(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def breakglass_covers(payload: dict, list_name: str, row: dict) -> str:
    """"" if *payload* holds this device's CURRENT credential, else why not.
    Compared in memory; nothing is printed or returned but the verdict."""
    from modules.device import open_stored

    want_user = row.get("username", "")
    want_pw, unopened = open_stored(row)
    if unopened:
        return unopened
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


def breakglass_logged(list_name: str, row: dict, exports: dict = None) -> dict:
    """Does the EXPORT LOG say a break-glass record holding this device's
    current credential was written? ``{"ok", "why", "export", "statement"}``.

    The Device page's basis, never the CLI's (which opens the record): the
    page cannot reach a file on the operator's laptop. It compares digests
    only (C182's ``currency_digest``), and the NEWEST export for the list
    decides, because an export writes the whole list and the newest is the
    one the operator holds. What it cannot show is said in ``statement``."""
    import time as _t

    from modules import breakglass as bg
    from modules.config import DATA_DIR, script_command
    from modules.device import open_stored

    limit = ("This trusts the export log on this host: it records what an export WROTE, "
             "and cannot show the file still exists or that its passphrase is known. "
             "`nmas-retire --breakglass <file>` opens the record itself.")
    try:
        exports = exports if exports is not None else bg.last_exports(DATA_DIR)
    except Exception as exc:                   # noqa: BLE001
        exports = {"state": "unreadable", "by_list": {}, "error": str(exc)}
    if exports.get("state") == "unreadable":
        return {"ok": False, "export": None, "statement": limit,
                "why": f"the export log could not be read ({exports.get('error')}): "
                       "an unreadable log is not an absent export"}
    newest = (exports.get("by_list") or {}).get(list_name)
    cmd = script_command("nmas-breakglass", "export", "--list", list_name,
                         "--out", "/dev/shm/nmas-breakglass.bg")
    if not newest:
        return {"ok": False, "export": None, "statement": limit,
                "why": f"no break-glass export of {list_name} is logged on this host. "
                       f"Export one ({cmd}), copy it off the host, then preview again"}
    host = row.get("hostname", "")
    # Opened by the one reader that names an unopenable value (C423: it raised).
    pw, unopened = open_stored(row)
    if unopened:
        return {"ok": False, "export": None, "statement": limit, "why": unopened}
    if not pw:
        return {"ok": False, "export": None, "statement": limit,
                "why": "the CSV row holds no password to compare"}
    when = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(newest.get("at") or 0))
    export = {"at": when, "path": newest.get("path", ""),
              "key_fingerprint": newest.get("key_fingerprint", ""),
              "actor": newest.get("actor", "")}
    logged = (newest.get("devices") or {}).get(host)
    if logged is None:
        return {"ok": False, "export": export, "statement": limit,
                "why": f"the newest export of {list_name} ({when}) did not include {host}. "
                       f"Export again ({cmd})"}
    if logged != bg.currency_digest(host, row.get("username", ""), pw):
        return {"ok": False, "export": export, "statement": limit,
                "why": f"the newest export of {list_name} ({when}) recorded an OLDER "
                       f"credential for {host} than the one it holds now: it was taken "
                       f"before the last rotation. Export again ({cmd})"}
    return {"ok": True, "why": "", "export": export, "statement": limit}


def _holds_the_device(func):
    """Retirement changes the record of a device (its row, its bindings, its
    map entry), so it holds the device like any other change (C98): a
    retirement beside a deploy would remove what the deploy is recording."""
    import functools

    @functools.wraps(func)
    def wrapper(list_name, hostname, *args, **kw):
        from modules.nsot import device_ops

        try:
            with device_ops.hold(list_name, hostname, "retire",
                                 kw.get("actor") or "unknown"):
                return func(list_name, hostname, *args, **kw)
        except device_ops.DeviceBusy as exc:
            return {"ok": False, "error": str(exc)}
    return wrapper


@_holds_the_device
def apply(list_name: str, hostname: str, *, reason: str, actor: str,
          confirmed_hash: str, breakglass: dict = None,
          breakglass_log: bool = False) -> dict:
    """Run the plan's pending steps, in order. Refuses unless the plan is the
    one confirmed, and deletes the CSV row only against *breakglass* (the
    record, opened: the CLI) or, with *breakglass_log*, the export log (the
    Device page). The result names which basis was trusted."""
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
    basis = {"basis": "", "statement": "no CSV row to delete: no credential to protect"}
    if "row" in pending:
        if breakglass is not None:
            why = breakglass_covers(breakglass, list_name, row)
            basis = {"basis": "record", "statement": (
                "The break-glass record was opened and holds this device's current "
                "credential.")}
        elif breakglass_log:
            logged = breakglass_logged(list_name, row)
            why = logged["why"]
            basis = {"basis": "export_log", "export": logged["export"],
                     "statement": ("The export log says the newest export of this list "
                                   f"({(logged['export'] or {}).get('at', '?')}, to "
                                   f"{(logged['export'] or {}).get('path', '?')}) recorded this "
                                   "device's current credential. " + logged["statement"])}
        else:
            return {"ok": False, "plan": p, "error": (
                "a break-glass record holding this device's current "
                "credential is required before its CSV row -- the only "
                "stored copy -- is deleted: scripts/nmas-breakglass export")}
        if why:
            return {"ok": False, "plan": p, "error": "break-glass: " + why}

    from modules.nsot import device_ops

    class _Done(list):
        """Each completed step is progress on the held device (C98)."""

        def append(self, step):
            device_ops.note(f"done: {step}")
            super().append(step)

    done = _Done()

    def fail(step, exc):
        remaining = [s["what"] for s in p["steps"]
                     if not s["done"] and s["key"] not in done]
        log.error("retire: %s failed at %s: %s", hostname, step, exc)
        return {"ok": False, "failed_at": step, "error": str(exc),
                "done": list(done), "remaining": remaining, "commit": commit,
                "breakglass": basis,
                "note": "run retire again: every step already done is skipped"}

    commit = ""
    if "netbox_mask" in pending:
        from modules.netbox_client import _nb_ready
        from modules.netbox_context_mask import assess_device, checker_scan, mask_one
        from modules.netbox_guard import for_list

        try:
            ok, err, session, base = _nb_ready()
            if not ok:
                raise RuntimeError(f"NetBox is not reachable: {err}")
            nb = _netbox_facts(list_name, hostname)
            a = assess_device(nb["device"]) if nb.get("exists") else {"holds": False}
            if a["holds"]:
                if not a["may"]:
                    raise RuntimeError(a["why"])
                from modules.netbox_guard import list_writer

                # One NetBox writer per list at a time, across processes (R21).
                with list_writer(list_name, f"the mask for retiring {hostname}", actor), \
                        for_list(list_name, actor=actor,
                                 authority=(f"retire of {hostname}, confirmed by {actor} "
                                            f"(plan {p['hash']})")):
                    got = mask_one(session, base, a["item"], checker_scan())
                if not got["ok"]:
                    raise RuntimeError(got["why"])
            done.append("netbox_mask")
        except Exception as exc:               # noqa: BLE001
            return fail("netbox_mask", exc)

    if "override" in pending:
        try:
            credentials.clear_device_override(p["ip"])
            done.append("override")
        except Exception as exc:               # noqa: BLE001
            return fail("override", exc)

    if "declare" in pending:
        from modules.config import settings_lock

        # Read and written under ONE hold of the settings lock (R17): read outside it, a
        # declaration made meanwhile for another list or device was put back without it.
        with settings_lock():
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

    if "commit" in pending:
        # The removal, the manifest release, the commit and any undo under the repository
        # lock, across processes (CONCURRENCY_AUDIT R1); the undo puts back ONLY the paths
        # retire touched (R25: it reset whole trees, taking another writer's work too).
        own = list(p["files"]) + [R.MANIFEST_REL]
        with R.repo_lock(repo):
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
                # Exactly what retire removed and the manifest, never the trees
                # (C175): another device's uncommitted edit must not leave with r5.
                result = R._commit_paths(list_name, list(p["files"]) + [R.MANIFEST_REL],
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
                R.git(repo, "reset", "-q", "HEAD", "--", *own)
                R.git(repo, "checkout", "-q", "HEAD", "--", *own)
                return fail("commit", exc)

    if "legacy" in pending:
        try:
            os.remove(p["legacy_path"])
        except FileNotFoundError:
            pass                               # already gone: the step's effect holds
        except Exception as exc:               # noqa: BLE001
            return fail("legacy", exc)
        done.append("legacy")

    if "row" in pending:
        try:
            delete_device(row["ip"], csv_path)
            done.append("row")
        except Exception as exc:               # noqa: BLE001
            return fail("row", exc)

    return {"ok": True, "done": list(done), "commit": commit, "breakglass": basis,
            "not_doing": p["not_doing"], "advisories": p["advisories"]}
