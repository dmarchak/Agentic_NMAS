"""nsot/read_account_op.py — Probe the read-only account…, as a Mercury operation (board R's R8;
provisional, operator review pending; the operator, 2026-11-13: "the probe as a Mercury action
recorded in History").

The probe itself is `modules/read_account_probe.py`, its one home, which the command line
(`scripts/nmas-read-account-probe`) calls too. This is the operation around it, the device
lifecycle's stages:

- **preview** (`preview`): the probe's own plan, touching no device: whom it signs in as (the
  account's name and profile, never its password), every command in the order it is sent with
  what is expected of it, the shapes not measured or not asked and why, and the program's hash
  (`deploy.command_fingerprint`, the probe's). It says when a run would be refused now: inside
  one of the installation's no-change windows, or while the device is held by another operation;
- **confirm** (`start`): the plan made again and refused, naming both hashes, unless its hash is
  the one confirmed by a verified person; refused inside a no-change window;
- **apply**: the probe's `run`, which holds the device for the whole run (one operation per
  device: another holder refuses it by name, never queued), signed in AS the read-only account,
  never escalating; it configures nothing (a configuration prompt is answered ``end`` at once
  and is a FAIL);
- **verify**: the probe's verdict, PASS, INCOMPLETE, FAIL, UNREADABLE or SIGN-IN REFUSED, judged
  only by the device's own answers;
- **record** (`read_account_probe.write_record`): the record, every answer masked, kept
  owner-only under the device's network and IDENTITY (`record_dir`), read again on History (the
  kind "Read-only account probes", `history_sources.read_account_probes`) and by the coverage's
  Last probe. Retirement removes the device's records (`retire`, ``probes``).

Nothing here parses or connects to an address itself: the probe's reads carry the device's
IPv4 and IPv6 forms alike.
"""

import json
import logging
import os

log = logging.getLogger(__name__)

#: The steps, as the manual's How it works page names each.
STEPS = (
    ("preview", "Preview", "the account it signs in as, every command it sends in order, what "
                           "each is expected to answer, and the program's hash; nothing sent"),
    ("confirm", "Confirm", "the hash confirmed by a verified person; the plan made again and "
                           "refused if it moved, or inside a no-change window"),
    ("hold", "Hold", "the device held for the whole run; another operation on it refuses this"),
    ("reads", "Reads", "each AI read shape sent as the read-only account, never escalating"),
    ("refused", "Refused", "show running-config, configure terminal, clear counters, debug ? and "
                           "enable, each expected refused; nothing is ever answered but end or n"),
    ("verdict", "Verdict", "PASS, INCOMPLETE, FAIL, UNREADABLE or SIGN-IN REFUSED, from the "
                           "device's own answers"),
    ("record", "Record", "the masked record under the device's identity, on History and in the "
                         "coverage's Last probe"),
)
#: What a probe job announces when it ends (`invalidation.ANNOUNCERS`).
ANNOUNCE_KEYS = ("read_account_probe", "device_holds")
ANNOUNCER = "read-account-probe"


def _probe():
    from modules import read_account_probe
    return read_account_probe


def _page_of(network: str) -> str:
    """The page a probe's job reopens from In progress (`read_account.page_of`, one home)."""
    from modules.nsot import read_account
    return read_account.page_of(network)


def preview(network: str, device: str) -> dict:
    """The preview: ``{"ok", "refused", "network", "device", "account", "lines", "hash",
    "now"}``. *lines* are the probe's own preview words (its account, every command and what
    is expected, the shapes not measured or not asked); *now* why a confirm would be refused at
    this moment, or ``""``. Touches no device; writes nothing."""
    from modules.nsot import device_ops

    P = _probe()
    out = {"ok": False, "refused": "", "network": network, "device": device, "account": {},
           "lines": [], "hash": "", "now": ""}
    try:
        p = P.plan(network, device, {})
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        out["refused"] = f"the probe could not be planned: {type(exc).__name__}: {exc}"
        return out
    if p.get("refused"):
        out["refused"] = p["refused"].replace("REFUSED: ", "", 1)
        return out
    out.update(ok=True, hash=p["hash"], lines=P.preview_lines(p),
               account={"username": p["account"]["username"],
                        "source": p["account"]["source"]})
    held = P.no_change_now()
    if held:
        out["now"] = (f"inside {held}: a measurement taken now measures what the window is "
                      "kept for")
    else:
        try:
            who = device_ops.holder(network, device)
        except Exception as exc:                      # noqa: BLE001 (said)
            who = {"operation": f"unknown ({type(exc).__name__})", "actor": ""}
        if who:
            out["now"] = (f"{device} is held by {who.get('operation', 'an operation')}"
                          + (f" ({who.get('actor')})" if who.get("actor") else ""))
    return out


def start(network: str, device: str, confirmed: str, actor: str) -> str:
    """The confirm, as a job: the plan made again and refused unless its hash is *confirmed*
    (both named) or inside a no-change window; then the probe's run, holding the device, and its
    record. The payload is masked; the job announces `ANNOUNCE_KEYS` when it ends."""
    from modules.nsot import capture_job, device_ops, reads
    from modules.outbound import mask_payload
    from modules.redact import known_secret_values

    P = _probe()

    def work(_job):
        p = P.plan(network, device, {})
        if p.get("refused"):
            return mask_payload({"state": "refused", "network": network, "device": device,
                                 "error": p["refused"].replace("REFUSED: ", "", 1)})
        if p["hash"] != (confirmed or "").strip():
            return mask_payload({"state": "refused", "network": network, "device": device,
                                 "error": (
                f"the probe's program moved since the preview you confirmed "
                f"({(confirmed or 'none')[:12]} -> {p['hash'][:12]}): the account, a read's "
                "argument or what Mercury holds for the device changed. Nothing connected; "
                "preview it again")})
        held = P.no_change_now()
        if held:
            return mask_payload({"state": "refused", "network": network, "device": device,
                                 "error": f"inside {held}: nothing connected"})
        dev = P._inventory(network)[device]
        try:
            rec = P.run(p, dev, actor, known_secret_values(), reads.cap_bytes(network))
        except device_ops.DeviceBusy as exc:
            return mask_payload({"state": "refused", "network": network, "device": device,
                                 "error": f"{exc}: nothing connected"})
        path = P.write_record(rec)
        return mask_payload({"state": "done", "network": network, "device": device,
                             "record": os.path.basename(path), "rec": view(rec)})
    # No `device=`: that names a card the device's page reopens (`device_actions.job_card`), and
    # the probe's card is on Credentials, where it was started and draws its run in place, and
    # its record on History. The device is held by the run itself (`device_ops`, in `P.run`).
    # Its page showing a probe in progress is C3539.
    return capture_job.start(network, f"Probe {device}'s read-only account", actor, work,
                             kind="read-only account probe", announce_keys=ANNOUNCE_KEYS,
                             announcer=ANNOUNCER, page=_page_of(network))


def view(rec: dict) -> dict:
    """What a record's card and History draw: the verdict and why, who and when, and each row
    by its result (answered, refused as expected, FAIL, not measured, not asked)."""
    verdict = rec.get("verdict") or {}
    rows = [{"command": r.get("command") or r.get("op") or "", "result": r.get("result") or "",
             "why": str(r.get("why") or "")[:300]}
            for r in list(rec.get("reads") or []) + list(rec.get("refused") or [])]
    counts = {}
    for r in rows:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    return {"result": verdict.get("result") or "UNREADABLE", "why": verdict.get("why") or "",
            "proposal": verdict.get("proposal") or "", "at": rec.get("at") or "",
            "actor": rec.get("actor") or "", "device": rec.get("device") or "",
            "network": rec.get("network") or "",
            "account": (rec.get("account") or {}).get("username") or "", "rows": rows,
            "counts": sorted(counts.items())}


def _read(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        rec = json.load(fh)
    if not isinstance(rec, dict):
        raise ValueError("not an object")
    return rec


def records(network: str, device: str = "", identity: str = None, repo: str = "") -> dict:
    """``{"records": [record, newest first], "unreadable": [file]}``: *network*'s probe
    records, or one device's: those under its identity's folder (`read_account_probe.
    record_dir`), and those the command line kept flat by name before records were kept by
    identity, for this network. *identity* None resolves the device's own; ``""`` reads only
    the flat ones. Each record carries ``file``."""
    P = _probe()
    root = P.records_root()
    out = {"records": [], "unreadable": []}
    folders = []
    net_dir = os.path.join(root, P.identity_slug(network))
    if device:
        ident = P.identity_of(network, device, repo) if identity is None else identity
        if ident:
            folders.append(P.record_dir(network, ident))
    elif os.path.isdir(net_dir):
        folders += [os.path.join(net_dir, d) for d in sorted(os.listdir(net_dir))]
    folders.append(root)
    for folder in folders:
        try:
            names = sorted(os.listdir(folder))
        except (FileNotFoundError, NotADirectoryError):
            continue
        for name in names:
            path = os.path.join(folder, name)
            if not name.endswith(".json") or not os.path.isfile(path):
                continue
            try:
                rec = _read(path)
            except (OSError, ValueError) as exc:
                out["unreadable"].append(f"{name} ({type(exc).__name__})")
                continue
            if folder == root and (rec.get("network") or "") != network:
                continue
            if device and rec.get("device") != device:
                continue
            out["records"].append(dict(rec, file=name))
    out["records"].sort(key=lambda r: str(r.get("at") or ""), reverse=True)
    return out


def newest(network: str, device: str, identity: str = None) -> dict:
    """The coverage's Last probe: *device*'s newest record as `newest_summary` words, or
    ``{}``."""
    got = records(network, device, identity)
    if got["records"]:
        r = got["records"][0]
        v = r.get("verdict") or {}
        return {"network": network, "at": str(r.get("at") or ""),
                "actor": str(r.get("actor") or ""),
                "result": str(v.get("result") or "UNREADABLE"),
                "why": str(v.get("why") or "")[:300], "file": r["file"]}
    if got["unreadable"]:
        return {"network": network, "at": "", "actor": "", "result": "UNREADABLE",
                "why": f"its probe record could not be read: {got['unreadable'][0]}",
                "file": ""}
    return {}


def device_folders(network: str, device: str, identity: str) -> list:
    """Every record path retirement removes for *device*: its identity's folder and the flat
    records kept by its name in *network* (`retire`, ``probes``)."""
    P = _probe()
    out = []
    if identity:
        folder = P.record_dir(network, identity)
        if os.path.isdir(folder):
            out.append(folder)
    root = P.records_root()
    try:
        names = sorted(os.listdir(root))
    except FileNotFoundError:
        return out
    for name in names:
        path = os.path.join(root, name)
        if not (name.startswith(f"{device}-") and name.endswith(".json")
                and os.path.isfile(path)):
            continue
        try:
            rec = _read(path)
        except (OSError, ValueError):
            out.append(path)
            continue
        if rec.get("device") == device and (rec.get("network") or network) == network:
            out.append(path)
    return out
