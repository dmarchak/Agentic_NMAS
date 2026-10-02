"""Does each device's LAB STARTUP FILE hold what its committed golden would
produce? (the operator, 2026-10-01, after the afternoon's redeploy).

A containerlab node boots the file in its lab's ``configs/`` directory, which
the clab sync writes from Oxidized's last copy through the sanitiser
(``scripts/oxidized-to-config.sh``). So a redeploy boots whatever that file
holds, approved or not, and the record the tool keeps is the committed golden.
This compares the two the only way that is exact: the golden is rendered
through the SANITISER'S OWN functions (``kind_for``, ``sanitise``,
``render_device``, lifted from the script as the clab sync test does, one
implementation) and compared line for line with the file's configuration
(the script's ``config_body``: a file written before C313 still opens with a
``! <h> - from Oxidized <ref> <sha>`` header, which is provenance, not
configuration). Measured on the host 2026-10-01: equal on all nine devices,
so any difference is real, never the sanitiser's own rules.

Credentials are compared by presence: a line whose secret slot differs is
named with its slot masked (``redact_positional``), never its value.

Population: every device of every list, its lab from ``clab_target_for()`` (the
one resolver), each lab's directory read ONCE (one SSH command per lab, never
per device). A ``.cfg`` in a lab's directory that no device of that lab owns is
named too: a redeploy boots it for whatever the topology still declares (r5's,
retired).
"""

import logging
import os
import re
import shlex
import subprocess

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANITISER = os.path.join(ROOT, "scripts", "oxidized-to-config.sh")
#: Separates the files in one lab's read: a control character no config holds.
SEP = "\x1e"
#: How many differing lines a result carries per side (the count is always whole).
LINES_SHOWN = 20


class RenderRefused(RuntimeError):
    """The sanitiser has no rules for this platform, or could not run."""


def _function(text: str, name: str) -> str:
    i = text.index(f"\n{name}() {{") + 1
    return text[i:text.index("\n}\n", i) + 3]


def _library() -> str:
    text = open(SANITISER, encoding="utf-8").read()
    return "".join(_function(text, n) for n in ("kind_for", "sanitise", "render_device"))


def render_expected(hostname: str, dialect: str, golden: str) -> str:
    """What the clab sync would write from *golden*: the script's own render."""
    script = (_library() + "\nkind=$(kind_for \"$1\") || { echo \"no sanitising rules for "
              "platform $1\" >&2; exit 3; }\nrender_device \"$2\" \"$kind\" \"$(cat)\"\n")
    out = subprocess.run(["bash", "-c", script, "render", dialect, hostname], input=golden,
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RenderRefused((out.stderr or "").strip() or f"rc={out.returncode}")
    return out.stdout


def _body(text: str, hostname: str) -> list:
    """The file's configuration, as the script's ``config_body`` reads it: the
    first three lines dropped when the second is a pre-C313 provenance header."""
    lines = [l.rstrip() for l in (text or "").splitlines()]
    if len(lines) >= 3 and lines[1].startswith(f"! {hostname} - from Oxidized "):
        lines = lines[3:]
    return lines


def compare(hostname: str, dialect: str, golden: str, startup: str) -> dict:
    """``{"state": matches|differs|unknown, ...}`` for one device."""
    from modules.redact import redact_positional

    if not golden:
        return {"state": "unknown", "why": "it has no committed golden to compare with"}
    try:
        expected = _body(render_expected(hostname, dialect, golden), hostname)
    except RenderRefused as exc:
        return {"state": "unknown", "why": f"the sanitiser could not render its golden: {exc}"}
    got = _body(startup, hostname)
    if expected == got:
        return {"state": "matches"}
    only_golden = [l for l in expected if l not in set(got)]
    only_file = [l for l in got if l not in set(expected)]
    # A secret slot whose VALUE differs is one finding, named by its masked line.
    masked_g = {redact_positional(l): l for l in only_golden}
    masked_f = {redact_positional(l): l for l in only_file}
    credentials = sorted(m for m in masked_g if m in masked_f and m != masked_g[m])
    only_golden = [m for m in (redact_positional(l) for l in only_golden) if m not in credentials]
    only_file = [m for m in (redact_positional(l) for l in only_file) if m not in credentials]
    return {"state": "differs", "reordered": not (only_golden or only_file or credentials),
            "credentials": credentials,
            "only_golden": only_golden[:LINES_SHOWN], "only_golden_count": len(only_golden),
            "only_file": only_file[:LINES_SHOWN], "only_file_count": len(only_file)}


def read_lab(host: str, configs_dir: str) -> dict:
    """``{filename: text}`` for every ``*.cfg`` in one lab's directory, in ONE
    SSH read. Raises when the directory cannot be read."""
    from modules.nsot.credential_rotation import _ssh_read

    cmd = (f"cd {shlex.quote(configs_dir)} || exit 3; for f in *.cfg; do "
           f"[ -f \"$f\" ] || continue; printf '{SEP}%s\\n' \"$f\"; cat \"$f\"; done")
    got = _ssh_read(host, cmd)
    if not got["ok"]:
        raise RuntimeError(f"{configs_dir} on {host} could not be read: {got['error']}")
    out = {}
    for chunk in got["text"].split(SEP)[1:]:
        name, _, body = chunk.partition("\n")
        out[name] = body
    return out


def oxidized_lag():
    """``(ref, host, device) -> dict``: whether Oxidized has fetched *host* since
    its golden last changed (C314). The clab sync writes the file from
    Oxidized's copy, so a golden newer than Oxidized's last successful fetch
    explains a difference without anybody's change. Oxidized's index is read
    ONCE per check, each list's request record once; the golden's commit time
    per device, and only for a device whose file differs. ``{}`` when
    Oxidized is not configured or cannot be asked (nothing is claimed)."""
    from modules import oxidized_fetch
    from modules.integrations.oxidized import OxidizedIntegration
    from modules.nsot import manifest
    from modules.nsot.credential_rotation import as_utc

    cache = {}

    def times():
        if "times" not in cache:
            client = OxidizedIntegration(timeout=10)
            got = client.node_times() if client.is_configured() else {"ok": False}
            cache["times"] = got.get("times") if got.get("ok") else None
        return cache["times"]

    def lag(ref, host, dev):
        fetched = times()
        if fetched is None:
            return {}
        _ident, entry = manifest.find_by_name(ref.repo_dir, host)
        if not entry:
            return {}
        rel = os.path.relpath(manifest.golden_path_for(ref.repo_dir, entry), ref.repo_dir)
        p = subprocess.run(["git", "-C", ref.repo_dir, "log", "-1", "--format=%cI", "HEAD",
                            "--", rel], capture_output=True, text=True, timeout=15)
        if p.returncode != 0 or not p.stdout.strip():
            return {}
        golden_at = as_utc(p.stdout.strip())
        node = oxidized_fetch.node_for(host, dev.get("ip") or entry.get("mgmt_ip") or "")
        stamp = fetched.get(node) or ""
        try:
            fetched_at = as_utc(stamp) if stamp else None
        except ValueError:
            fetched_at = None
        if ("req", ref.name) not in cache:
            try:
                cache[("req", ref.name)] = oxidized_fetch.requests_for(ref.name)
            except Exception as exc:                   # noqa: BLE001
                log.warning("lab startup: %s's fetch requests could not be read: %s",
                            ref.name, exc)
                cache[("req", ref.name)] = {}
        req = cache[("req", ref.name)].get(host) or {}
        requested_at = None
        if req.get("ok") and req.get("at"):
            when = as_utc(req["at"])
            requested_at = when if when >= golden_at else None
        iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None      # noqa: E731
        return {"golden_at": iso(golden_at), "fetched_at": iso(fetched_at),
                "requested_at": iso(requested_at),
                "behind": fetched_at is None or fetched_at < golden_at}

    return lag


def check(population=None, golden=None, reader=None, target=None, lag=None) -> dict:
    """Every device's startup file against its golden. Injected for tests:
    *population* ``() -> [(ref, device)]``, *golden* ``(ref, host) -> text``,
    *reader* ``(host, dir) -> {file: text}``, *target* ``(list, host) -> dict``,
    *lag* ``(ref, host, device) -> dict`` (``oxidized_lag()``)."""
    from modules.nsot.credential_rotation import clab_target_for
    from modules.nsot.platform import platform_for_device
    from modules.prometheus_targets import inventory, read_golden

    population, golden = population or inventory, golden or read_golden
    reader, target = reader or read_lab, target or clab_target_for
    lag = lag or oxidized_lag()
    labs, devices, errors, hosted = {}, [], [], False
    for ref, dev in population():
        host = dev.get("hostname") or ""
        t = target(ref.name, host)
        row = {"list": ref.name, "device": host, "lab": t.get("lab", "")}
        hosted = hosted or bool(t.get("host"))
        if not t.get("host"):
            row.update(state="unknown", why="clab_host is not configured: the lab cannot be read")
        elif not t.get("named") or not t.get("configs_dir"):
            row.update(state="unknown", why=t.get("why") or f"lab {t.get('lab')!r} names no configs_dir")
        else:
            key = (t["host"], t["configs_dir"])
            labs.setdefault(key, {"lab": t.get("lab", ""), "devices": []})["devices"].append(
                (ref, dev, row))
            row.update(file=f"{t['configs_dir']}/{host}.cfg")
        devices.append(row)
    unowned = []
    for (host, cdir), lab in sorted(labs.items()):
        try:
            files = reader(host, cdir)
        except Exception as exc:                   # noqa: BLE001
            errors.append(str(exc))
            for _ref, _dev, row in lab["devices"]:
                row.update(state="unknown", why=f"its lab's directory could not be read: {exc}")
            continue
        owned = set()
        for ref, dev, row in lab["devices"]:
            name = f"{row['device']}.cfg"
            owned.add(name)
            if name not in files:
                row.update(state="missing")
                continue
            try:
                text = golden(ref, row["device"])
            except Exception as exc:               # noqa: BLE001
                row.update(state="unknown", why=f"its committed golden could not be read: {exc}")
                continue
            row.update(compare(row["device"], platform_for_device(dev), text, files[name]))
            if row.get("state") == "differs":
                try:
                    row["lag"] = lag(ref, row["device"], dev)
                except Exception as exc:           # noqa: BLE001
                    log.warning("lab startup: %s's Oxidized lag could not be read: %s",
                                row["device"], exc)
        unowned += [{"lab": lab["lab"], "file": f"{cdir}/{f}"}
                    for f in sorted(files) if f not in owned]
    return {"configured": hosted, "devices": devices, "unowned": unowned, "errors": errors,
            "labs": len(labs), "checked": sum(1 for d in devices
                                              if d.get("state") in ("matches", "differs"))}
