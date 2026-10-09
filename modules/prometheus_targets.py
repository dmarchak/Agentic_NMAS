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
import threading
import time

log = logging.getLogger(__name__)

PREFIX = "nmas-snmp-"
ALL = "all"
IPSLA = "ipsla"
DEFAULT_DIR = "/etc/prometheus/nmas"
_IPSLA_OP = re.compile(r"^ip sla \d+\s*$", re.M)

#: The routing-adjacency files (staged run 5, the operator, 2026-09-30): the
#: devices whose COMMITTED golden runs each protocol, as the IP SLA file
#: follows the goldens. OSPF-MIB answers on both platforms; OSPFV3-MIB on
#: IOS-XE only (vIOS 15 answered "No Such Object"), so the v3 file holds
#: IOS-XE devices alone; BGP is read from CISCO-BGP4-MIB's cbgpPeer2Table,
#: the table that sees an IPv6 peer.
ROUTING = (
    ("ospf", re.compile(r"^router ospf \d+", re.M), None),
    ("ospfv3", re.compile(r"^(ipv6 router ospf|router ospfv3) \d+", re.M), "cisco_iosxe"),
    ("bgp", re.compile(r"^router bgp \d+", re.M), None),
)


def _file(kind: str) -> str:
    return f"{PREFIX}{kind}.json"


def read_golden(ref, hostname: str) -> str:
    """The device's COMMITTED golden text; ``""`` when it has none. RAISES
    when it cannot be read: an unreadable golden is not "no SNMP", and reading
    it as one would drop the device from every target file."""
    from modules.nsot import manifest
    from modules.nsot import repo as R

    _ident, entry = manifest.find_by_name(ref.repo_dir, hostname)
    return (R.committed_golden_for(ref.repo_dir, entry).get("text") or "") if entry else ""


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
    *golden*: (ref, hostname) -> text, default the committed golden (raising
    when it cannot be read). A device whose golden configures no SNMP is not a
    target, and is named.

    Refused and NAMED, never guessed: a device with no address, an address two
    devices hold (one address scraped under two names is two series for one
    thing), a device whose platform does not resolve. Said: a device with no
    role."""
    from modules.nsot.platform import platform_for_device

    devices = inventory() if devices is None else devices
    from modules.monitoring_coverage import configured

    golden = golden or read_golden
    files, notes, by_address = {_file(ALL): [], _file(IPSLA): []}, [], {}
    for kind, _rx, _only in ROUTING:
        files[_file(kind)] = []
    excluded = {}
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
        # ONLY A DEVICE CONFIGURED FOR SNMP IS A TARGET (the operator,
        # 2026-09-30): r6 became a target with no SNMP in its configuration and
        # Grafana called it "unreachable", which it was not. Its golden decides,
        # as it does for IP SLA. An unreadable golden raises out of here, so
        # the keeper records a failure and the files stay as they were.
        text = golden(ref, host) or ""
        if not configured(text)["snmp"]:
            why = "its committed golden " + ("configures no SNMP" if text else "does not exist")
            notes.append(f"{host}: {why}, so it is not a target: it is not monitored by SNMP")
            excluded[host] = why
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
        if _IPSLA_OP.search(text):
            files[_file(IPSLA)].append(group)
        for kind, rx, only in ROUTING:
            if rx.search(text) and (only is None or dialect == only):
                files[_file(kind)].append(group)
    for groups in files.values():
        groups.sort(key=lambda g: g["labels"]["device"])
    # `devices` is the TARGETS; `inventory` the devices the inventory holds.
    # The operator read "8 device(s) in the inventory" over nine (r6 held, not
    # a target): one number that changed meaning. Both are carried and said.
    return {"files": files, "notes": notes, "devices": len(files[_file(ALL)]),
            "inventory": len(devices), "excluded": excluded}


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
#
# THREE OPERANDS, AND A DIFFERENCE IS NAMED BY THE ONE THAT MOVED (the
# operator, 2026-09-30). `--check` run seconds after the install's reload said
# "cisco_8000v: still reads its static targets" for all four jobs, while the
# LOADED config already read the generated files: Prometheus had not yet
# discovered them. It inferred "static" from the discovered targets alone, so
# a change not yet discovered and an edit not loaded shared one sentence, and
# the sentence blamed the config. So the check now reads what Prometheus has
# LOADED (`/api/v1/status/config`, and `/api/v1/status/runtimeinfo` for when
# and whether the last reload worked) beside what it has DISCOVERED
# (`/api/v1/targets`), and says which of three it is:
#
# - ``not_loaded``: the loaded config's job reads none of the generated files
#   (the install's edit is not loaded, or its reload failed);
# - ``settling``: the loaded config reads them and discovery has not caught up
#   with the last load or the last write, and it is still inside the job's
#   scrape interval: ask again after the time named;
# - ``differs``: the same difference, past that window.
#
# The window is ONE scrape interval of the job, from the loaded config (30 s
# here, 1 m for `lldp`), the operator's measure. Prometheus's discovery
# manager publishes a changed target set at most every 5 s, so one interval
# holds it with margin; the lag itself is not measured, so a difference inside
# the window is said as "not yet", never as fine.

_DURATION = re.compile(r"(\d+)(ms|s|m|h|d|w|y)")
_UNIT_S = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 31536000}


def seconds(duration: str, default: float = 60.0) -> float:
    """A Prometheus duration (`30s`, `1m`, `1h30m`) in seconds."""
    parts = _DURATION.findall(str(duration or ""))
    return sum(int(n) * _UNIT_S[u] for n, u in parts) if parts else default


def loaded_jobs(config_yaml: str) -> dict:
    """The LOADED config's scrape jobs: ``{job: {snmp, files, static, interval}}``.
    *files* are the basenames its `file_sd_configs` read."""
    import yaml

    doc = yaml.safe_load(config_yaml or "") or {}
    default = seconds((doc.get("global") or {}).get("scrape_interval"), 60.0)
    out = {}
    for job in doc.get("scrape_configs") or []:
        files = [os.path.basename(f) for c in job.get("file_sd_configs") or []
                 for f in c.get("files") or []]
        out[job.get("job_name") or "?"] = {
            "snmp": job.get("metrics_path") == "/snmp", "files": files,
            "static": bool(job.get("static_configs")),
            "interval": seconds(job.get("scrape_interval"), default)}
    return out


def _epoch(iso: str):
    import datetime as _dt

    try:
        return _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _iso(epoch) -> str:
    import datetime as _dt

    return _dt.datetime.fromtimestamp(epoch, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compare(generated: dict, active: list, loaded: dict = None, now: float = None,
            disk_mtimes: dict = None) -> dict:
    """Does the RUNNING Prometheus scrape exactly what `generate()` says now?

    *active*: Prometheus's `activeTargets`; SNMP pools are those whose targets
    go to `/snmp`. *loaded*: ``{"jobs": loaded_jobs(...), "loaded_at": epoch,
    "reload_ok": bool}``, or ``{"error": ...}``, or None (not read).
    *disk_mtimes*: each generated file's mtime where the directory is readable.

    Returns ``{ok, state, pools, by_pool, static, drift, settling, unread,
    config}``; every difference named with both operands. ``static`` lists the
    pools whose loaded config does not read our files (or, when the loaded
    config could not be read, whose discovered targets are all static)."""
    now = time.time() if now is None else now
    disk_mtimes = disk_mtimes or {}
    loaded = loaded or {"error": "not read"}
    jobs = loaded.get("jobs")
    discovered = {}
    for t in active or []:
        d = t.get("discoveredLabels") or {}
        if d.get("__metrics_path__") != "/snmp":
            continue
        pool = discovered.setdefault(t.get("scrapePool") or "?", {"files": set(), "targets": {}})
        pool["files"].add(os.path.basename(d.get("__meta_filepath") or "") or "static")
        labels = t.get("labels") or {}
        pool["targets"][labels.get("instance") or d.get("__address__") or "?"] = labels
    names = set(discovered)
    if jobs is not None:
        names |= {j for j, v in jobs.items() if v["snmp"]}
    by_pool, static, drift, settling, read = {}, [], [], [], set()
    for name in sorted(names):
        pool = discovered.get(name) or {"files": set(), "targets": {}}
        job = (jobs or {}).get(name)
        if jobs is not None and job is None:
            lines = [f"{name}: Prometheus still scrapes this job and the LOADED config has no "
                     "such job (discovery has not caught up with the reload, or a target "
                     "outlived it)"]
            drift += lines
            by_pool[name] = {"state": "differs", "lines": lines}
            continue
        if jobs is not None:
            ours = sorted(f for f in (job or {}).get("files", []) if f in generated["files"])
            if not ours:
                static.append(name)
                by_pool[name] = {"state": "not_loaded", "lines": [
                    f"{name}: the LOADED config (loaded {_iso(loaded['loaded_at']) if loaded.get('loaded_at') else 'at an unread time'}) "
                    f"lists {'static targets' if (job or {}).get('static') else 'no generated file'} "
                    "for this job, so the install's edit is not loaded"]}
                continue
        else:
            ours = sorted(f for f in pool["files"] if f in generated["files"])
            if not ours:
                static.append(name)
                by_pool[name] = {"state": "not_loaded", "lines": [
                    f"{name}: every discovered target is static, and the loaded config could "
                    f"not be read ({loaded.get('error')}), so whether the install's edit is "
                    "loaded is not known"]}
                continue
        read.update(ours)
        lines = _differences(name, pool, ours, generated)
        if not lines:
            by_pool[name] = {"state": "matches", "lines": []}
            continue
        anchors = [(loaded.get("loaded_at"), "the config was loaded")] + \
                  [(disk_mtimes.get(f), f"{f} was written") for f in ours]
        anchors = [(t, what) for t, what in anchors if t]
        interval = (job or {}).get("interval")
        latest = max(anchors, key=lambda a: a[0]) if anchors else None
        if latest and interval and now - latest[0] < interval:
            until = latest[0] + interval
            because = (f"{name}: {latest[1]} at {_iso(latest[0])} and Prometheus has not "
                       f"discovered it yet; ask again after {_iso(until)} (one scrape "
                       f"interval, {int(interval)} s)")
            settling.append({"pool": name, "until": _iso(until), "because": because,
                             "lines": lines})
            by_pool[name] = {"state": "settling", "lines": [because], "until": _iso(until)}
            continue
        if jobs is None:
            lines = lines + [f"{name}: the loaded config could not be read "
                             f"({loaded.get('error')}), so a change Prometheus has not "
                             "discovered yet cannot be told from a difference"]
        drift += lines
        by_pool[name] = {"state": "differs", "lines": lines}
    unread = sorted(f for f in generated["files"] if generated["files"][f] and f not in read)
    ok = bool(names) and not static and not drift and not settling
    state = "ok" if ok else ("settling" if names and not static and not drift else "mismatch")
    config = {"read": jobs is not None, "error": loaded.get("error") if jobs is None else "",
              "loaded_at": _iso(loaded["loaded_at"]) if loaded.get("loaded_at") else None,
              "reload_ok": loaded.get("reload_ok")}
    return {"ok": ok, "state": state, "pools": sorted(names), "by_pool": by_pool,
            "static": static, "drift": drift, "settling": settling, "unread": unread,
            "config": config}


def _differences(name: str, pool: dict, ours: list, generated: dict) -> list:
    expected = {}
    for f in ours:
        for g in generated["files"][f]:
            expected[g["targets"][0]] = g["labels"]
    lines = []
    for ip, labels in sorted(expected.items()):
        got = pool["targets"].get(ip)
        if got is None:
            lines.append(f"{name}: {labels['device']} ({ip}) is in the inventory and not "
                         "scraped (the file on the host predates it)")
        elif any(got.get(k) != v for k, v in labels.items()) or \
                ("role" not in labels and got.get("role")):
            lines.append(f"{name}: {ip} is labelled {({k: got.get(k) for k in ('device', 'role')})}"
                         f", the inventory says {labels}")
    for ip in sorted(set(pool["targets"]) - set(expected)):
        lines.append(f"{name}: {ip} is scraped and is in no inventory "
                     f"(labelled {pool['targets'][ip].get('device') or 'with no device'})")
    if "static" in pool["files"]:
        lines.append(f"{name}: reads a generated file AND static targets; the static ones "
                     "are outside the inventory's reach")
    return lines


def _json_of(got: dict):
    if not got.get("ok"):
        raise RuntimeError(got.get("error") or "no answer")
    return got["response"].json().get("data") or {}


def read_loaded(client) -> dict:
    """What Prometheus has LOADED: its jobs, when, and whether the last reload
    worked. An unreadable answer is ``{"error": ...}``, never an empty config."""
    try:
        cfg = _json_of(client._get("api/v1/status/config"))
        jobs = loaded_jobs(cfg.get("yaml") or "")
    except Exception as exc:                            # noqa: BLE001
        return {"error": f"/api/v1/status/config: {type(exc).__name__}: {exc}"}
    out = {"jobs": jobs, "loaded_at": None, "reload_ok": None}
    try:
        rt = _json_of(client._get("api/v1/status/runtimeinfo"))
        out.update(loaded_at=_epoch(rt.get("lastConfigTime")),
                   reload_ok=rt.get("reloadConfigSuccess"))
    except Exception as exc:                            # noqa: BLE001
        out["runtime_error"] = f"/api/v1/status/runtimeinfo: {type(exc).__name__}: {exc}"
    return out


def disk_state(directory: str, generated: dict) -> dict:
    """The generated files as they are ON DISK: which differ from what the
    inventory generates now, and each file's mtime. ``{"read": False}`` when
    there is no directory to read."""
    if not directory:
        return {"read": False, "why": "no targets directory is set"}
    if not os.path.isdir(directory):
        return {"read": False, "why": f"{directory} does not exist"}
    differs, mtimes = [], {}
    for name, groups in sorted(generated["files"].items()):
        path = os.path.join(directory, name)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            mtimes[name] = os.stat(path).st_mtime
        except OSError as exc:
            differs.append(f"{name}: not readable ({type(exc).__name__})")
            continue
        if text != render(groups):
            differs.append(f"{name}: differs from what the inventory generates now")
    return {"read": True, "dir": directory, "differs": differs, "mtimes": mtimes}


def check(client=None, generated=None, directory=None, now=None) -> dict:
    """Ask the running Prometheus (read-only) and compare. ``state``:
    ``not_configured`` (no Prometheus URL: no row), ``unknown`` (could not
    ask for the discovered targets), else the comparison's ``ok``,
    ``settling`` or ``mismatch``, with the files on disk beside it."""
    if client is None:
        from modules.integrations.prometheus import PrometheusIntegration
        client = PrometheusIntegration()
    if not client.is_configured():
        return {"state": "not_configured"}
    try:
        active = _json_of(client._get("api/v1/targets", state="active")).get("activeTargets") or []
    except Exception as exc:                            # noqa: BLE001
        return {"state": "unknown", "error": str(exc) or type(exc).__name__}
    generated = generate() if generated is None else generated
    directory = target_dir() if directory is None else directory
    disk = disk_state(directory, generated)
    result = compare(generated, active, loaded=read_loaded(client), now=now,
                     disk_mtimes=disk.get("mtimes"))
    result["disk"] = disk
    result["notes"] = generated.get("notes") or []
    return result


# ------------------------------------------------ keeping the files current
#
# THE NMAS REGENERATES THE FILES; NOBODY RUNS A COMMAND (the operator,
# 2026-09-30: "run --write" was a console step, and the rule is no console).
# The one-time install gives the NMAS's own user the directory; from then on
# the app writes it whenever the inventory changes, and `file_sd` picks a
# changed file up with no reload. `prometheus_targets_dir` names the
# directory, and its default is EMPTY: the app writes nothing until a person
# names it (the behaviour that predates the setting), and the test suite's
# store, which never sets it, can never write the live directory.
#
# Senders, each in the app's process:
# - `device.write_devices_csv()`, the one writer of a local list's inventory
#   (onboarding's promotion, adopt, retire, a role edit, Add and Delete);
# - `inventory.refresh_list()`, a NetBox-sourced list's inventory;
# - a golden COMMIT in a list's repository (`golden_hook`, a post-commit
#   hook, so every commit reaches it by construction, C223): a device's
#   eligibility for every group (SNMP at all, OSPF, OSPFv3, BGP, IP SLA) is
#   read from its committed golden, so a deploy or capture that gives r6
#   SNMP or a router OSPF changes the files at once (the operator,
#   2026-09-30: r6 joined only at the backstop);
# - a BACKSTOP every `KEEPER_BACKSTOP_SECONDS`, because a change made by
#   another process (a CLI on the host) has no sender here.
# Every run is recorded (`data/prometheus_targets_sync.json`); the job-health
# row reads it, and compares the files on disk with the inventory, so a run
# that did not happen or failed is a row, never a silence.

#: A burst of inventory writes (a Refresh Hostnames rewriting every row) is
#: one regeneration: the keeper waits this long after the last sender.
KEEPER_DEBOUNCE_SECONDS = 2
#: The backstop's interval. A CLI's change or a golden commit reaches the
#: files within it; 300 s is the job-health reader's own interval, so the row
#: never sits a whole read behind a backstop that has not run.
KEEPER_BACKSTOP_SECONDS = 300

_keeper = {"thread": None, "event": threading.Event(), "reasons": [], "lock": threading.Lock()}


def target_dir() -> str:
    # The Default network's: one targets directory serves every list until P.7.
    from modules.list_settings import default_layer

    return str(default_layer("prometheus_targets_dir", "") or "").strip()


def _record_path() -> str:
    from modules import config

    return os.path.join(config.DATA_DIR, "prometheus_targets_sync.json")


def last_sync() -> dict:
    """The keeper's last run, as recorded. ``{}`` when none is (absent);
    ``{"unreadable": reason}`` when the record exists and cannot be read."""
    path = _record_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        return {"unreadable": f"{type(exc).__name__}: {exc}"}


def sync(reason: str, directory: str = None, generate_fn=None) -> dict:
    """Regenerate the files into the configured directory, and record the run.
    Nothing to do (no directory set) is ``{"state": "not_managed"}`` and is
    not recorded. An inventory with no device is refused and recorded: an
    empty file would tell Prometheus to scrape nothing."""
    from modules.filestore import write_atomic

    directory = target_dir() if directory is None else directory
    if not directory:
        return {"state": "not_managed"}
    rec = {"at": _iso(time.time()), "reason": reason, "dir": directory}
    try:
        generated = (generate_fn or generate)()
        if not generated["devices"]:
            raise RuntimeError(f"of the {generated.get('inventory', 0)} device(s) in the "
                               "inventory, none is configured for SNMP with an address; writing "
                               "would tell Prometheus to scrape nothing")
        out = write(directory, generated)
        # WHEN each device left the targets (the operator, 2026-09-30: "the
        # condition began at a known moment"): the first run that excluded
        # it, carried forward while it stays out, gone when it returns.
        before = (last_sync().get("excluded") or {}) if isinstance(last_sync(), dict) else {}
        rec.update(ok=True, devices=generated["devices"], inventory=generated.get("inventory"),
                   changed=out["changed"], unchanged=out["unchanged"],
                   excluded={h: {"since": (before.get(h) or {}).get("since") or rec["at"], "why": w}
                             for h, w in sorted((generated.get("excluded") or {}).items())})
        if out["changed"]:
            log.info("prometheus targets: wrote %s (%s)", ", ".join(out["changed"]), reason)
    except Exception as exc:                            # noqa: BLE001
        rec.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        log.error("prometheus targets: NOT regenerated for %s: %s", reason, rec["error"])
    try:
        write_atomic(_record_path(), json.dumps(rec, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("prometheus targets: the run could not be recorded: %s", exc)
        rec["record_error"] = f"{type(exc).__name__}: {exc}"
    return rec


def inventory_changed(reason: str) -> None:
    """A sender: the inventory moved. Wakes the keeper when it runs in this
    process; otherwise nothing (the backstop in the app reaches it)."""
    if _keeper["thread"] is None:
        return
    with _keeper["lock"]:
        _keeper["reasons"].append(reason)
    _keeper["event"].set()


def golden_hook(context: dict, run=None) -> dict:
    """The post-commit sender: a commit that changed a golden wakes the
    keeper. Waking on every golden commit, never deciding eligibility here:
    the regeneration writes only files whose content moved, and one owner
    decides eligibility (`generate`)."""
    import subprocess

    repo, sha = context.get("repo") or "", context.get("sha") or ""
    if not repo or not sha:
        return {"ok": True, "message": "no commit to read"}
    p = (run or subprocess.run)(["git", "-C", repo, "diff-tree", "--no-commit-id", "--name-only",
                                 "-r", "--root", sha], capture_output=True, text=True, timeout=15)
    if p.returncode != 0:
        return {"ok": False, "error": f"git diff-tree {sha[:10]} exited {p.returncode}"}
    goldens = [x for x in p.stdout.split() if x.startswith("golden/")]
    if not goldens:
        return {"ok": True, "message": "no golden changed"}
    inventory_changed(f"{context.get('list_name') or 'a list'}: commit {sha[:10]} changed "
                      + ", ".join(os.path.basename(g)[:-4] if g.endswith(".cfg") else g
                                  for g in goldens))
    return {"ok": True, "message": f"woke the targets keeper ({len(goldens)} golden(s))"}


def _keeper_loop(sleep=time.sleep) -> None:
    reasons = ["the app started"]
    while True:
        try:
            if target_dir():
                sync("; ".join(dict.fromkeys(reasons)))
        except Exception as exc:                        # noqa: BLE001
            log.error("prometheus targets: the keeper's run raised: %s", exc)
        woke = _keeper["event"].wait(timeout=KEEPER_BACKSTOP_SECONDS)
        if woke:
            sleep(KEEPER_DEBOUNCE_SECONDS)
        with _keeper["lock"]:
            reasons = list(_keeper["reasons"]) or [f"the {KEEPER_BACKSTOP_SECONDS} s backstop"]
            _keeper["reasons"].clear()
            _keeper["event"].clear()


def start_keeper() -> None:
    """Start the keeper in this process (the app's `_start_background_daemons`)."""
    if _keeper["thread"] is not None:
        return
    t = threading.Thread(target=_keeper_loop, daemon=True, name="prometheus-targets-keeper")
    _keeper["thread"] = t
    t.start()


# ------------------------------------------------------- the job-health row

_WHAT = "Prometheus scrapes the inventory's devices, each labelled device and role (C232)"
_SETTINGS_ACTION = {"label": "Name the targets directory in Settings › Default, the "
                             "Prometheus card (Targets directory), so Mercury regenerates the "
                             "files when the inventory changes",
                    "reference": "docs/PROMETHEUS_TARGETS.md"}


def _row(state: str, detail: str, action: dict = None) -> list:
    row = {"unit": "prometheus-targets", "what": _WHAT, "state": state,
           "max_age_minutes": 0, "detail": detail}
    if action:
        row["action"] = action
    return [row]


def health_rows(client=None, generated=None, directory=None, now=None, record=None) -> list:
    """The job-health row. No row when Prometheus is not configured (ZTP's
    precedent): an install without Prometheus has nothing to scrape.

    Its causes, in the order a person would fix them: the loaded config does
    not read the files (the install); the files on disk are not what the
    inventory generates (the keeper did not run, or failed, or is not given a
    directory); Prometheus differs from the files (past one scrape interval).
    A change inside the window is ``settling``: dated, with when to ask
    again, and nothing to do."""
    try:
        r = check(client, generated, directory=directory, now=now)
    except Exception as exc:                            # noqa: BLE001
        return _row("unknown", f"the check raised {type(exc).__name__}: {exc} -- not the same as ok")
    if r["state"] == "not_configured":
        return []
    if r["state"] == "unknown":
        return _row("unknown", f"Prometheus could not be asked: {r['error']} -- not the same as ok")
    notes = (f"; {len(r['notes'])} note(s): " + "; ".join(r["notes"])) if r["notes"] else ""
    cfg = r["config"]
    reload_failed = cfg.get("reload_ok") is False
    if r["static"]:
        parts = [f"{len(r['static'])} SNMP job(s) do not read the generated targets in the "
                 f"config Prometheus has LOADED ({', '.join(r['static'])})"
                 + (f", loaded {cfg['loaded_at']}" if cfg.get("loaded_at") else "")
                 + ", so no series carries device or role and the device dashboards are empty"]
        if reload_failed:
            parts.append("Prometheus's last reload FAILED, so it still runs the config "
                         "loaded then: `promtool check config` names why")
        if not cfg["read"]:
            parts = [line for p in r["static"] for line in r["by_pool"][p]["lines"]]
        return _row("mismatch", "; ".join(parts),
                    {"label": "Install the generated targets once (a person's step on the "
                              "Prometheus host)", "reference": "docs/PROMETHEUS_TARGETS.md"})
    disk = r.get("disk") or {}
    record = last_sync() if record is None else record
    if disk.get("read") and disk["differs"]:
        return _disk_row(disk, record, r, now)
    if r["drift"]:
        action = _SETTINGS_ACTION if not disk.get("read") else \
            {"label": "The files on disk are current and Prometheus scrapes something else: "
                      "read its targets page for the job named", "known": False}
        lead = ("" if disk.get("read") else
                "the files are not regenerated by Mercury (no targets directory is set); ")
        return _row("mismatch", lead + "; ".join(r["drift"]), action)
    if r["state"] == "settling":
        return _row("settling", "; ".join(s["because"] for s in r["settling"]) + notes)
    kept = (f"; regenerated by Mercury into {disk['dir']}"
            + (f", last run {record['at']} ({record.get('reason')})" if record.get("at") else "")
            if disk.get("read") else "; Mercury does not regenerate them (no targets directory is set)")
    return _row("ok", f"{len(r['pools'])} SNMP job(s) scrape exactly the generated targets"
                + kept + notes)


def _disk_row(disk: dict, record: dict, r: dict, now=None) -> list:
    now = time.time() if now is None else now
    what = "; ".join(disk["differs"])
    if record.get("unreadable"):
        return _row("unknown", f"the files in {disk['dir']} are not current ({what}), and the "
                    f"keeper's record is unreadable ({record['unreadable']}) -- not the same as "
                    "a run that did not happen")
    if record.get("ok") is False:
        return _row("mismatch", f"the files in {disk['dir']} are not current ({what}): the "
                    f"Mercury's last regeneration, at {record.get('at')} for "
                    f"{record.get('reason')}, failed: {record.get('error')}",
                    {"label": "Read the failure above: the directory's owner and mode are "
                              "the install's (docs/PROMETHEUS_TARGETS.md)",
                     "reference": "docs/PROMETHEUS_TARGETS.md"})
    last = _epoch(record.get("at")) if record.get("at") else None
    window = KEEPER_BACKSTOP_SECONDS + KEEPER_DEBOUNCE_SECONDS
    if last and now - last < window:
        return _row("settling", f"the files in {disk['dir']} are not current yet ({what}); "
                    f"Mercury regenerates them by {_iso(last + window)} at the latest "
                    f"(its last run {record.get('at')}, for {record.get('reason')})")
    return _row("mismatch", f"the files in {disk['dir']} are not current ({what}), and the "
                "Mercury has not regenerated them "
                + (f"since {record.get('at')}" if last else "at all")
                + f": its keeper runs in the app at least every {KEEPER_BACKSTOP_SECONDS} s, "
                "so it is not running",
                {"label": "The app's regeneration job is not running: it starts with the app",
                 "reference": "docs/PROMETHEUS_TARGETS.md"})
