"""Does each device's LAB STARTUP FILE hold what the clab sync builds for it?
(the operator, 2026-10-01, after the afternoon's redeploy; its source since
plan item 4, the same night).

A containerlab node boots the file in its lab's ``configs/`` directory, which
the clab sync writes through the sanitiser (``scripts/oxidized-to-config.sh``)
from the list's newest EARNED baseline, every credential taken from the
device's current golden (``modules/nsot/startup_source.py``, the sync's own
helper's computation). So a redeploy boots that file, and this asks two
questions of it: is the file what the sync builds now (a difference is a sync
that has not run since, or could not), and has the device moved since the
baseline (``since_baseline``: a redeploy would return it there). Compared the
only way that is exact: the source is rendered
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


class SourceRefused(RuntimeError):
    """The sync builds no file for this device (no earned baseline, or the
    baseline does not hold it); the reason is the sync's own."""


def baseline_source():
    """``(ref, host) -> {"text", "tag"}``: what the clab sync writes FROM for
    *host* (plan item 4): its golden at the list's newest earned baseline,
    every credential from its current golden (`startup_source`, the sync's
    own helper's computation). Built once per list per check. Raises
    `SourceRefused` with the sync's reason when it builds nothing."""
    from modules.nsot import startup_source

    cache = {}

    def source(ref, host):
        if ref.name not in cache:
            cache[ref.name] = startup_source.build(ref.name)
        got = cache[ref.name]
        if not got.get("ok"):
            raise SourceRefused(got.get("error") or "no startup source")
        d = got["devices"].get(host)
        if d is None:
            got["devices"].update(startup_source.build(ref.name, hosts=[host])["devices"])
            d = got["devices"][host]
        if d["state"] != "ok":
            raise SourceRefused(d["why"])
        return {"text": d["text"], "tag": got["baseline"]["tag"]}

    return source


def check(population=None, golden=None, reader=None, target=None, source=None) -> dict:
    """Every device's startup file against what the sync builds for it.
    Injected for tests: *population* ``() -> [(ref, device)]``, *golden*
    ``(ref, host) -> text`` (the CURRENT golden), *reader* ``(host, dir) ->
    {file: text}``, *target* ``(list, host) -> dict``, *source* ``(ref, host)
    -> {"text", "tag"}`` (``baseline_source()``).

    Each compared device also carries ``since_baseline``: its current golden
    against the baseline's, through the same sanitiser. A difference is a
    device a redeploy returns to the baseline (the sync's cross-check, from
    the record rather than from Oxidized)."""
    from modules.nsot.credential_rotation import clab_target_for
    from modules.nsot.platform import platform_for_device
    from modules.prometheus_targets import inventory, read_golden

    population, golden = population or inventory, golden or read_golden
    reader, target = reader or read_lab, target or clab_target_for
    source = source or baseline_source()
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
                src = source(ref, row["device"])
            except SourceRefused as exc:
                row.update(state="not_built", why=str(exc))
                continue
            except Exception as exc:               # noqa: BLE001
                row.update(state="unknown", why=f"its startup source could not be built: {exc}")
                continue
            dialect = platform_for_device(dev)
            row["baseline"] = src["tag"]
            row.update(compare(row["device"], dialect, src["text"], files[name]))
            try:
                now = golden(ref, row["device"])
                moved = compare(row["device"], dialect, now,
                                render_expected(row["device"], dialect, src["text"]))
            except Exception as exc:               # noqa: BLE001
                row["since_baseline"] = {"state": "unknown", "why": str(exc)}
            else:
                row["since_baseline"] = {k: moved.get(k) for k in
                                         ("state", "only_golden_count", "only_file_count",
                                          "only_golden", "only_file") if k in moved}
        unowned += [{"lab": lab["lab"], "file": f"{cdir}/{f}"}
                    for f in sorted(files) if f not in owned]
    return {"configured": hosted, "devices": devices, "unowned": unowned, "errors": errors,
            "labs": len(labs), "checked": sum(1 for d in devices
                                              if d.get("state") in ("matches", "differs"))}
