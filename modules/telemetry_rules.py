"""A retired device's telemetry rules, removed from the generated rules file (C1419 part 2).

`scripts/nmas-telemetry-rules` generates one Grafana rule per device and subscription from the
committed goldens, and Grafana keeps a provisioned rule its file has dropped unless a file names
it under ``deleteRules`` (`grafana_rule_deletes`). Retirement removes the device's golden, so
the next generation drops its rules; until this step, nothing ran that generation, and the
rules fired under the device's name after it left (Lab 8 step 1, 2026-10-20, until the
stopgap host step). Retire's ``telemetry`` step does what the heartbeat step does for the
heartbeat rule (`heartbeat_windows.drop_plan`): the device's rules leave the written rules file,
they are named in its delete file, and the one install step
(`scripts/host-steps/c1419-install-alert-rules.sh telemetry`) installs both and proves them
gone. Reads only, but for :func:`drop_device`."""

import hashlib
import logging
import os
import re

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-telemetry-rules")
#: Where Grafana loads the telemetry rules from.
INSTALLED = "/etc/grafana/provisioning/alerting/nmas-telemetry.yaml"
#: Every telemetry rule's uid starts so (the generator's `rule_for`).
UID_PREFIX = "nmas-tel-"


def _script():
    """The generator, loaded as a module (its `OUT`, `render`): one loader."""
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("nmas_telemetry_rules", SCRIPT)
    spec = importlib.util.spec_from_loader("nmas_telemetry_rules", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _read(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16] if text else ""


def device_prefix(hostname: str) -> str:
    """The start of every uid the generator gives *hostname*'s rules (`nmas-tel-<d>-<sub>`)."""
    return f"{UID_PREFIX}{re.sub(r'[^A-Za-z0-9_-]', '-', hostname)}-"


def host_step(written_path: str, installed_path: str = "") -> str:
    """The one install step, every value filled in (C1419)."""
    from modules.grafana_rule_deletes import INSTALL_STEP

    return f"bash {INSTALL_STEP} telemetry {written_path} {installed_path or INSTALLED}"


def drop_plan(hostname: str, T=None, written_path: str = "", installed_path: str = "",
              live=...) -> dict:
    """What removing *hostname*'s telemetry rules would do, reading only: the rules are read
    from the file written for installing when there is one, else from the file Grafana loads.
    ``{"state", "rules", "uids", "written_path", "installed_path", "source", "text",
    "fingerprint", "host_step", "error"}``; *state* is ``names`` (rules name it: *text* is
    the file without them), ``grafana`` (no file names it and Grafana still runs its rules:
    *text* is the file as it is, the delete file is the work), ``none``, ``last`` (they are the
    file's only rules: the generator never writes an empty population, so neither does this),
    ``absent`` (neither file is here) or ``unreadable``. *live* (tests) replaces the read of
    Grafana's own rules: a set, or None."""
    import yaml

    T = T or _script()
    written_path = written_path or T.OUT
    installed_path = installed_path or INSTALLED
    out = {"state": "absent", "rules": 0, "uids": [], "written_path": written_path,
           "installed_path": installed_path, "source": "", "text": "", "fingerprint": "",
           "host_step": host_step(written_path, installed_path), "error": ""}
    source = written_path if os.path.exists(written_path) else installed_path
    text = _read(source)
    if text is None:
        return out
    out["source"] = source
    try:
        doc = yaml.safe_load(text) or {}
        rules = [r for g in doc.get("groups") or [] for r in g.get("rules") or []]
    except Exception as exc:                          # noqa: BLE001 - said as unreadable
        return dict(out, state="unreadable", error=f"{source}: {type(exc).__name__}: {exc}")
    mine = [r for r in rules if (r.get("labels") or {}).get("device") == hostname]
    if not mine:
        if live is ...:
            from modules import grafana_rule_deletes as GD
            live, _why = GD.live_uids(UID_PREFIX)
        held = sorted(u for u in (live or ()) if u.startswith(device_prefix(hostname)))
        if held:
            return dict(out, state="grafana", uids=held, text=text,
                        fingerprint=_sha(text + ",".join(held)))
        return dict(out, state="none")
    uids = sorted(str(r.get("uid")) for r in mine if r.get("uid"))
    if len(mine) == len(rules):
        return dict(out, state="last", rules=len(mine), uids=uids)
    for group in doc.get("groups") or []:
        group["rules"] = [r for r in group.get("rules") or []
                          if (r.get("labels") or {}).get("device") != hostname]
    new = T.render(doc)
    return dict(out, state="names", rules=len(mine), uids=uids, text=new,
                fingerprint=_sha(new))


def drop_device(hostname: str, fingerprint: str, *, T=None, written_path: str = "",
                installed_path: str = "") -> dict:
    """Remove *hostname*'s telemetry rules as :func:`drop_plan` previewed them: planned again
    and refused when it moved, written where the generator writes (never the installed file,
    which is root's), with the delete file beside it. ``{"ok", "error", "path", "deletes",
    "deletes_said", "host_step"}``."""
    import yaml

    from modules import grafana_rule_deletes as GD
    from modules.filestore import write_atomic

    got = drop_plan(hostname, T, written_path, installed_path)
    if got["state"] == "none":
        return {"ok": True, "error": "", "path": got["written_path"], "deletes": [],
                "deletes_said": "", "host_step": got["host_step"]}
    if got["state"] not in ("names", "grafana") or got["fingerprint"] != fingerprint:
        return {"ok": False, "error": (
            f"the telemetry rules moved since the preview ({got['state']}, "
            f"{got['fingerprint'] or 'no file'} against {fingerprint}): nothing was written")}
    os.makedirs(os.path.dirname(got["written_path"]), exist_ok=True)
    write_atomic(got["written_path"], got["text"])
    # What Grafana or the installed file holds, never a rule only ever written (C1419).
    plan = GD.plan(yaml.safe_load(got["text"]) or {}, UID_PREFIX, got["installed_path"])
    return {"ok": True, "error": "", "path": got["written_path"],
            "deletes": plan["uids"], "delete_path": GD.write(got["written_path"], plan["uids"]),
            "deletes_said": plan["said"], "host_step": got["host_step"]}
