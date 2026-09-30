"""Prometheus's SNMP scrape targets, generated from the inventory (C232, C229).

Measured 2026-09-30 on the host: Prometheus (installed 2026-08-30, its oldest
sample) has never carried a `device` label with a device's name, nor any
`role` label. Its SNMP jobs list addresses by hand in `static_configs`, with
the names only in comments (`- 10.255.1.13 #r3`). So `rcn-lab1-snmp`'s device
panels, which select `device="$device"`, have been empty in Grafana since the
install; r6 was never scraped; retired r5 still is. The fix is at the source:
the targets come from the inventory, every one labelled.

**Three kinds of file, each a population the tool already records:**

- ``nmas-snmp-<dialect>.json``: the devices of one platform dialect, for the
  per-platform jobs (the platform decides the SNMP module);
- ``nmas-snmp-all.json``: every device, for fleet-wide jobs (`lldp`);
- ``nmas-snmp-ipsla.json``: the devices whose COMMITTED golden defines an
  `ip sla <n>` operation. Measured: exactly the five the hand-kept
  `cisco_ipsla` job lists, so the population is derived, not copied.

Each file is a `file_sd` list: one group per device, `targets: [address]`,
`labels: {device, role}`. An empty role is omitted, never invented, and said.
Prometheus re-reads a `file_sd` file when it changes, so a new file takes
effect with no reload. Installing the files is the operator's one-time step
(docs/PROMETHEUS_TARGETS.md); `check()` is the job-health row saying whether
the RUNNING Prometheus scrapes exactly what this would generate now.
"""

import json
import logging
import os
import re
import tempfile

log = logging.getLogger(__name__)

PREFIX = "nmas-snmp-"
ALL = "all"
IPSLA = "ipsla"
DEFAULT_DIR = "/etc/prometheus/nmas"
_IPSLA_OP = re.compile(r"^ip sla \d+\s*$", re.M)


def _file(kind: str) -> str:
    return f"{PREFIX}{kind}.json"


def _golden_text(ref, hostname: str) -> str:
    from modules.nsot import manifest
    from modules.nsot import repo as R

    try:
        _ident, entry = manifest.find_by_name(ref.repo_dir, hostname)
        return (R.committed_golden_for(ref.repo_dir, entry).get("text") or "") if entry else ""
    except Exception as exc:                            # noqa: BLE001
        log.info("prometheus targets: no golden read for %s (%s)", hostname, type(exc).__name__)
        return ""


def inventory(lists=None) -> list:
    """Every device of every registered list: (list ref, device row)."""
    from modules.device import get_device_lists, load_saved_devices
    from modules.nsot import listref

    out = []
    names = lists if lists is not None else [l["name"] for l in get_device_lists()]
    for name in names:
        ref = listref.resolve(name)
        for dev in load_saved_devices(ref.csv_path):
            out.append((ref, dev))
    return out


def generate(devices=None, golden=None) -> dict:
    """``{"files": {name: [group, ...]}, "notes": [...], "devices": n}`` from
    the inventory. *devices*: (ref, row) pairs, default every list;
    *golden*: (ref, hostname) -> text, default the committed golden.

    Refused and NAMED, never guessed: a device with no address, an address two
    devices hold (one address scraped under two names is two series for one
    thing), a device whose platform does not resolve. Said: a device with no
    role."""
    from modules.nsot.platform import platform_for_device

    devices = inventory() if devices is None else devices
    golden = golden or _golden_text
    files, notes, by_address = {_file(ALL): [], _file(IPSLA): []}, [], {}
    for ref, dev in devices:
        host, ip = (dev.get("hostname") or "").strip(), (dev.get("ip") or "").strip()
        if not host or not ip:
            notes.append(f"{host or '(no name)'} in {ref.name}: no address, not a target")
            continue
        if ip in by_address:
            notes.append(f"{ip} is held by {by_address[ip]} and {host} ({ref.name}): "
                         "neither is scraped under it until one address is one device")
            by_address[ip] = None
            continue
        by_address[ip] = f"{host} ({ref.name})"
    for ref, dev in devices:
        host, ip = (dev.get("hostname") or "").strip(), (dev.get("ip") or "").strip()
        if not host or not ip or by_address.get(ip) != f"{host} ({ref.name})":
            continue
        dialect = platform_for_device(dev)
        if not dialect:
            notes.append(f"{host}: its platform does not resolve, so no platform job scrapes it")
        labels = {"device": host}
        role = (dev.get("role") or "").strip()
        if role:
            labels["role"] = role
        else:
            notes.append(f"{host}: no role in the inventory, so its targets carry no role label")
        group = {"targets": [ip], "labels": labels}
        files[_file(ALL)].append(group)
        if dialect:
            files.setdefault(_file(dialect), []).append(group)
        if _IPSLA_OP.search(golden(ref, host) or ""):
            files[_file(IPSLA)].append(group)
    for groups in files.values():
        groups.sort(key=lambda g: g["labels"]["device"])
    return {"files": files, "notes": notes, "devices": len(files[_file(ALL)])}


def render(groups: list) -> str:
    """The file's text: deterministic, so an unchanged inventory writes the
    same bytes and Prometheus sees no change."""
    return json.dumps(groups, indent=2, sort_keys=True) + "\n"


def _write_644(path: str, text: str) -> None:
    """Atomic, and readable by Prometheus's own user from the first byte (a
    temp per write, `fchmod` 0644 before any content, `os.replace`). The files
    hold device names and addresses, which are inventory, not secrets (the Kea
    fragment's precedent, P.6 D1)."""
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".nmas-", dir=directory)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write(directory: str, generated: dict) -> dict:
    """Write every generated file into *directory*. A file of ours left from a
    platform no device has any more is written EMPTY (a job reading it then
    scrapes nothing), never deleted: a job pointing at a missing file is a
    Prometheus error. Returns what changed."""
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"{directory} does not exist: the one-time install creates it "
                                "(docs/PROMETHEUS_TARGETS.md)")
    wanted = dict(generated["files"])
    for name in os.listdir(directory):
        if name.startswith(PREFIX) and name.endswith(".json") and name not in wanted:
            wanted[name] = []
    changed, same = [], []
    for name, groups in sorted(wanted.items()):
        path, text = os.path.join(directory, name), render(groups)
        try:
            with open(path, encoding="utf-8") as fh:
                if fh.read() == text:
                    same.append(name)
                    continue
        except OSError:
            pass
        _write_644(path, text)
        changed.append(name)
    return {"changed": changed, "unchanged": same}


# ---------------------------------------------------------------- the check

def compare(generated: dict, active: list) -> dict:
    """Does the RUNNING Prometheus scrape exactly what `generate()` says now?

    *active*: Prometheus's `activeTargets`. The SNMP pools are those whose
    targets go to `/snmp`. Per pool: a pool still on `static_configs` is not
    installed; a pool reading one of our files must scrape exactly that file's
    devices, each labelled as generated. Returns ``{ok, static, drift,
    unread}``, every difference named with both operands."""
    pools = {}
    for t in active or []:
        d = t.get("discoveredLabels") or {}
        if d.get("__metrics_path__") != "/snmp":
            continue
        pool = pools.setdefault(t.get("scrapePool") or "?", {"files": set(), "targets": {}})
        pool["files"].add(os.path.basename(d.get("__meta_filepath") or "") or "static")
        labels = t.get("labels") or {}
        pool["targets"][labels.get("instance") or d.get("__address__") or "?"] = labels
    static, drift, read = [], [], set()
    for name, pool in sorted(pools.items()):
        ours = sorted(f for f in pool["files"] if f in generated["files"])
        if not ours:
            static.append(name)
            continue
        read.update(ours)
        expected = {}
        for f in ours:
            for g in generated["files"][f]:
                expected[g["targets"][0]] = g["labels"]
        for ip, labels in sorted(expected.items()):
            got = pool["targets"].get(ip)
            if got is None:
                drift.append(f"{name}: {labels['device']} ({ip}) is in the inventory and not "
                             "scraped (the file on the host predates it)")
            elif any(got.get(k) != v for k, v in labels.items()) or \
                    ("role" not in labels and got.get("role")):
                drift.append(f"{name}: {ip} is labelled {({k: got.get(k) for k in ('device', 'role')})}"
                             f", the inventory says {labels}")
        for ip in sorted(set(pool["targets"]) - set(expected)):
            drift.append(f"{name}: {ip} is scraped and is in no inventory "
                         f"(labelled {pool['targets'][ip].get('device') or 'with no device'})")
        if "static" in pool["files"]:
            drift.append(f"{name}: reads a generated file AND static targets; the static ones "
                         "are outside the inventory's reach")
    unread = sorted(f for f in generated["files"] if generated["files"][f] and f not in read)
    return {"ok": bool(pools) and not static and not drift, "pools": sorted(pools),
            "static": static, "drift": drift, "unread": unread}


def check(client=None, generated=None) -> dict:
    """Ask the running Prometheus (read-only) and compare. ``state``:
    ``not_configured`` (no Prometheus URL: no row), ``unknown`` (could not
    ask), else the comparison."""
    if client is None:
        from modules.integrations.prometheus import PrometheusIntegration
        client = PrometheusIntegration()
    if not client.is_configured():
        return {"state": "not_configured"}
    got = client._get("api/v1/targets", state="active")
    if not got.get("ok"):
        return {"state": "unknown", "error": got.get("error") or "no answer"}
    try:
        active = (got["response"].json().get("data") or {}).get("activeTargets") or []
    except Exception as exc:                            # noqa: BLE001
        return {"state": "unknown", "error": f"unreadable answer: {type(exc).__name__}"}
    generated = generate() if generated is None else generated
    result = compare(generated, active)
    result["state"] = "ok" if result["ok"] else "mismatch"
    result["notes"] = generated.get("notes") or []
    return result


def health_rows(client=None, generated=None) -> list:
    """The job-health row. No row when Prometheus is not configured (ZTP's
    precedent): an install without Prometheus has nothing to scrape."""
    what = "Prometheus scrapes the inventory's devices, each labelled device and role (C232)"
    try:
        r = check(client, generated)
    except Exception as exc:                            # noqa: BLE001
        return [{"unit": "prometheus-targets", "what": what, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": f"the check raised {type(exc).__name__}: {exc} -- not the same as ok"}]
    if r["state"] == "not_configured":
        return []
    if r["state"] == "unknown":
        return [{"unit": "prometheus-targets", "what": what, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": f"Prometheus could not be asked: {r['error']} -- not the same as ok"}]
    if r["state"] == "ok":
        return [{"unit": "prometheus-targets", "what": what, "state": "ok", "max_age_minutes": 0,
                 "detail": (f"{len(r['pools'])} SNMP job(s) scrape exactly the generated targets"
                            + (f"; {len(r['notes'])} note(s): " + "; ".join(r["notes"])
                               if r["notes"] else ""))}]
    parts = []
    if r["static"]:
        parts.append(f"{len(r['static'])} SNMP job(s) still read their hand-kept static "
                     f"targets ({', '.join(r['static'])}), so no series carries device or "
                     "role and the device dashboards are empty")
    parts += r["drift"]
    if r["static"]:
        action = {"label": "Install the generated targets once (a person's step on the "
                           "Prometheus host)", "reference": "docs/PROMETHEUS_TARGETS.md"}
    else:
        action = {"label": "Regenerate the targets: the inventory moved since they were "
                           "written", "command": f"scripts/nmas-prometheus-targets --write {DEFAULT_DIR}"}
    return [{"unit": "prometheus-targets", "what": what, "state": "mismatch",
             "max_age_minutes": 0, "action": action, "detail": "; ".join(parts)}]
