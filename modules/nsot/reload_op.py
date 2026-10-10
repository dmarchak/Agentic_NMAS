"""nsot/reload_op.py — Reload, a gated device-page operation (P.14; cutover blocker 6,
2026-10-10; drawn under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md).

P.14's plain form: the device boots the startup configuration it holds, and the first gate
requires that to be what it runs, so no file is sent and nothing in running is lost. Revert by
reload (booting a moment from history, the charter's Phase 2) builds on this with a boot file;
it is not this.

The preview (a job: it reads the device) reads the running and startup configurations, `show
version` and `show boot`, and judges P.14's six gates, each drawn by name with what it found:
1. running against startup (unsaved changes refuse; Persist… saves them first, previewed);
2. running against its golden and its committed intent (a departure is shown, and the stated
   reason is recorded as acknowledging it);
3. the startup configuration carries every account line running holds (the startup check's
   judgement, `onboard.startup_carries`);
4. the image it booted exists, and the boot variable, where the platform has one, names a file
   that exists;
5. no operation holds the device;
6. the blast radius: every device Mercury loses reach to while this one is down
   (`blast_radius`), shown above the confirm.
The confirm carries a stated reason and is bound to the preview's fingerprint (the two
configurations, the image, the departure). The run (a job, holding the device): read again and
compare; declare the planned-restart window BEFORE anything is sent; reload (send, read,
decide: `device_reload`); wait for SSH's port, bounded by the platform's measured boot time;
verify (a login with the credential Mercury holds, and what it runs is what it ran); record the
run. No rollback exists: a reload cannot be undone, and the preview says so.
"""

import hashlib
import json
import logging
import os
import re
import socket
import time

log = logging.getLogger(__name__)

KIND = "reload"
ANNOUNCE_KEYS = ("reload", "restarts", "device_state")
ANNOUNCER = "reload"

#: The run's steps, for the one stepper (`device_actions.stepper`): (key, words, waits, names).
STEPS = (
    ("read", "Read it again",
     "the running and startup configurations read and compared with the preview", ("read",)),
    ("window", "Declare the window",
     "the planned-restart window recorded before anything is sent", ("window",)),
    ("reload", "Reload",
     "reload sent and confirmed; success is the session dropping", ("reload",)),
    ("wait", "Wait for it",
     "its management address asked on SSH's port until it answers, within the bound",
     ("wait",)),
    ("verify", "Verify",
     "a login with the credential Mercury holds, and what it runs compared with what it ran",
     ("verify",)),
    ("record", "Record", "the reload's row: who, why, the window and each step's outcome",
     ("record",)),
)

#: How long a reload takes, per platform, from the reload to SSH answering: MEASURED where
#: known (an emulated IOS-XE router finishes booting in about 6.5 minutes, measured during
#: onboarding, docs/manual/how-it-works/onboard.md). None: not measured yet.
BOOT_SECONDS = {"cisco_iosxe": 390, "cisco_ios": None}
#: The wait's bound is 2.5 times the measured boot; unmeasured, this placeholder, named as one
#: on the card and in the result, until a reload's own record measures it.
PLACEHOLDER_BOUND_S = 900
POLL_S = 10
_IMAGE = re.compile(r'System image file is "([^"]+)"')
_BOOT_VAR = re.compile(r"BOOT variable\s*=\s*([^,;\s]+)", re.I)   # "bootflash:x,12;": the file


def wait_bound(platform: str) -> tuple:
    """``(seconds, words)``: the wait's bound for *platform*, and where it comes from."""
    measured = BOOT_SECONDS.get(platform)
    if measured:
        return int(measured * 2.5), (f"2.5 times the measured boot of {measured // 60} min "
                                     f"{measured % 60} s")
    return PLACEHOLDER_BOUND_S, ("a placeholder: this platform's reload has not been measured; "
                                 "the first reload's record measures it")


def _repo(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _device(list_name: str, host: str):
    from modules.nsot.restore import _devices_of
    return next((d for d in _devices_of(list_name) if d.get("hostname") == host), None)


#: Every read the preview makes, each a whole command on Tier 1's allowlist; `dir` names an
#: image path `show version` or `show boot` printed (`_images`), one token.
_READ = dict(read_timeout=60, strip_prompt=True, strip_command=True)


def read_device(device: dict) -> dict:
    """ONE session: the running configuration (`config_read.read`), then `show
    startup-config`, `show version`, `show boot` (a platform without it says so) and `dir` of
    each image named. ``{"running", "startup", "version", "boot", "dirs": {path: text}}``.
    Reads only, so it takes no hold: the preview's job is a read, and the run that changes the
    device holds it (`run`)."""
    from modules import config_read
    from modules.connection import with_temp_connection

    def read(conn):
        out = {"running": config_read.read(conn, device.get("hostname", ""))}
        out["startup"] = conn.send_command("show startup-config", **_READ) or ""
        out["version"] = conn.send_command("show version", **_READ) or ""
        boot = conn.send_command("show boot", **_READ) or ""
        out["boot"] = "" if "Invalid input" in boot else boot
        out["dirs"] = {}
        for path in _images(out["version"], out["boot"]):
            if re.fullmatch(r"[\w.:/-]+", path):           # one token, as the device printed it
                out["dirs"][path] = conn.send_command(f"dir {path}", **_READ) or ""
        return out

    return with_temp_connection(device, read)


def _images(version: str, boot: str) -> list:
    found = []
    m = _IMAGE.search(version or "")
    if m:
        found.append(m.group(1))
    b = _BOOT_VAR.search(boot or "")
    if b and b.group(1) not in found:
        found.append(b.group(1))
    return found


def _image_gate(reads: dict) -> dict:
    """P.14 gate 4: the image it booted exists, and the boot variable names a file that does."""
    version, boot, dirs = reads.get("version", ""), reads.get("boot", ""), reads.get("dirs", {})
    m = _IMAGE.search(version)
    if not m:
        return {"name": "the boot image", "state": "fail",
                "detail": "`show version` names no system image file, so what it would boot "
                          "is not known"}
    image = m.group(1)

    def exists(path):
        text = dirs.get(path, "")
        return bool(text) and "Error" not in text and "No such file" not in text \
            and os.path.basename(path.split(":")[-1]) in text

    if not exists(image):
        return {"name": "the boot image", "state": "fail",
                "detail": f"it booted {image}, and `dir {image}` does not show it"}
    b = _BOOT_VAR.search(boot)
    if not boot:
        return {"name": "the boot image", "state": "pass",
                "detail": f"{image} exists; the platform has no `show boot`, so the image it "
                          "booted is the one checked"}
    if b and not exists(b.group(1)):
        return {"name": "the boot image", "state": "fail",
                "detail": f"the boot variable names {b.group(1)}, and `dir` does not show it"}
    return {"name": "the boot image", "state": "pass",
            "detail": f"{image} exists" + (f", and the boot variable names {b.group(1)}"
                                           if b else ", and no boot variable is set")}


def judge(list_name: str, host: str, platform: str, reads: dict, *, holding: bool = False) -> dict:
    """The six gates from *reads*, and the fingerprint the confirm is bound to. *holding*: the
    run judging under its own hold, which is not another operation's."""
    from modules.nsot import blast_radius, device_ops, onboard, repo as R, roundtrip
    from modules.nsot.intent_match import explain, intent_match

    repo = _repo(list_name)
    running, startup = reads.get("running", ""), reads.get("startup", "")
    gates = []
    same = roundtrip.stored_is_device(startup, running)
    unsaved = len(same.get("only_left") or []) + len(same.get("only_right") or [])
    gates.append({"name": "running against startup", "key": "unsaved",
                  "state": "pass" if same.get("equal") else "fail",
                  "detail": ("they are the same: it boots what it runs" if same.get("equal")
                             else f"{unsaved} line(s) differ: a reload would boot startup and "
                                  "lose them; save them first (Persist…)")})
    golden = R.golden_at(repo, host, "HEAD") or ""
    drift = roundtrip.stored_is_device(golden, running) if golden else {"equal": False}
    intent = intent_match(repo, list_name, host, running, platform)
    departs = (not drift.get("equal")) or intent.get("state") != "match"
    gates.append({"name": "its golden and its intent", "key": "drift",
                  "state": "ack" if departs else "pass",
                  "detail": ("it matches its golden and its committed intent" if not departs
                             else ("its running configuration differs from its golden; "
                                   if not drift.get("equal") else "") + explain(intent)
                             + ". Your reason is recorded as acknowledging it")})
    carries = onboard.startup_carries(startup, running)
    gates.append({"name": "startup carries Mercury's credential", "key": "credential",
                  "state": "pass" if carries.get("ok") else "fail",
                  "detail": carries.get("detail", "")})
    gates.append(dict(_image_gate(reads), key="image"))
    busy = "" if holding else device_ops.busy_text(list_name, host)   # the run holds it itself
    gates.append({"name": "no other operation holds it", "key": "busy",
                  "state": "fail" if busy else "at_apply",
                  "detail": busy or "checked again when the run takes the device"})
    radius = blast_radius.for_device(repo, host)
    seconds, bound_words = wait_bound(platform)
    shown = json.dumps({"running": _h(running), "startup": _h(startup),
                        "image": _IMAGE.search(reads.get("version", "") or "") and
                        _IMAGE.search(reads.get("version", "")).group(1),
                        "departs": departs}, sort_keys=True)
    return {"ok": True, "gates": gates, "radius": radius,
            "failing": [g for g in gates if g["state"] == "fail"],
            "departs": departs, "bound_s": seconds, "bound_words": bound_words,
            "fingerprint": hashlib.sha256(shown.encode()).hexdigest()[:16],
            "running_hash": _h(running)}


def _h(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:16]


def plan(list_name: str, host: str) -> dict:
    """The preview: read the device, judge the gates. ``{"ok", "gates", "radius", ...}`` or
    ``{"ok": False, "error"}``. Sends nothing that changes the device."""
    device = _device(list_name, host)
    if device is None:
        return {"ok": False, "error": f"{host} is not in {list_name}'s inventory"}
    try:
        reads = read_device(device)
    except Exception as exc:                          # noqa: BLE001 (said on the card)
        return {"ok": False, "error": f"{host} could not be read: {type(exc).__name__}: {exc}"}
    platform = device.get("platform") or ""
    return dict(judge(list_name, host, platform, reads), host=host, list=list_name,
                platform=platform)


def _wait_for_ssh(ip: str, bound: float, *, clock=time.monotonic, sleep=time.sleep,
                  connect=None) -> dict:
    """Ask *ip*:22 every POLL_S until it accepts, within *bound*: ``{"ok", "after_s",
    "attempts"}``. A poll that cannot ask (no address) says so."""
    if not ip:
        return {"ok": False, "after_s": 0, "attempts": 0,
                "detail": "no management address to ask, so its return cannot be seen"}
    connect = connect or (lambda: socket.create_connection((ip, 22), timeout=3).close())
    start, attempts = clock(), 0
    while clock() - start < bound:
        attempts += 1
        try:
            connect()
            return {"ok": True, "after_s": round(clock() - start), "attempts": attempts}
        except OSError:
            sleep(POLL_S)
    return {"ok": False, "after_s": round(clock() - start), "attempts": attempts,
            "detail": f"it did not answer on SSH's port within {round(bound)} s"}


def records_path(repo_dir: str) -> str:
    """Where a network's reloads are recorded, from its repository folder: resolving it
    creates nothing (a READ must not bring a network's folder into being)."""
    return os.path.join(repo_dir, ".nsot", "reloads.jsonl")


def record(list_name: str, row: dict) -> dict:
    """Append one reload's row: ``{"ok", "error"}``. Never raises: the reload happened
    whether or not its record could be written, and the result says which."""
    from modules.config import open_secure

    path = records_path(_repo(list_name))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        return {"ok": True, "error": ""}
    except Exception as exc:                          # noqa: BLE001
        log.error("reload: the record was NOT written for %s: %s", row.get("device"), exc)
        return {"ok": False, "error": str(exc)}


def read_records(repo_dir: str) -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows": [...newest first], "error"}``: every
    reload's row in the network whose repository is *repo_dir*. Absent and unreadable are
    different facts."""
    path = records_path(repo_dir)
    if not os.path.exists(path):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except Exception as exc:                          # noqa: BLE001
        return {"state": "unreadable", "rows": [], "error": str(exc)}
    return {"state": "ok", "rows": list(reversed(rows)), "error": ""}


def run(list_name: str, host: str, *, actor: str, fingerprint: str, reason: str,
        wait=None, reader=None, reloader=None) -> dict:
    """The run, holding the device. ``{"ok", "outcome", "steps", "record", ...}``; *wait*,
    *reader* and *reloader* replace the device-facing parts in tests."""
    from modules import restarts
    from modules.connection import with_temp_connection
    from modules.device_reload import reload_device
    from modules.nsot import device_ops, roundtrip

    device = _device(list_name, host)
    steps = []
    out = {"ok": False, "device": host, "list": list_name, "by": actor, "reason": reason,
           "outcome": "", "steps": steps}

    def step(name, ok, detail):
        steps.append({"step": name, "ok": bool(ok), "detail": detail})
        device_ops.note(name)

    def finish(outcome, ok=False):
        out.update(outcome=outcome, ok=ok, at=_iso(time.time()))
        out["record"] = record(list_name, {k: out[k] for k in
                                           ("at", "device", "list", "by", "reason", "outcome",
                                            "ok", "steps")} | {"window": out.get("window")})
        device_ops.note("record")
        return out

    if device is None:
        out["error"] = f"{host} is not in {list_name}'s inventory"
        return out
    platform = device.get("platform") or ""
    try:
        with device_ops.hold(list_name, host, "reload", actor or "unknown"):
            try:
                reads = (reader or read_device)(device)
            except Exception as exc:                  # noqa: BLE001
                step("read", False, f"it could not be read: {exc}")
                return finish("unread")
            now = judge(list_name, host, platform, reads, holding=True)
            if now["fingerprint"] != fingerprint:
                step("read", False, f"it moved since the preview (previewed {fingerprint}, "
                                    f"now {now['fingerprint']}): nothing was sent")
                return finish("moved")
            if now["failing"]:
                step("read", False, "a gate fails now: " + "; ".join(
                    f"{g['name']}: {g['detail']}" for g in now["failing"]))
                return finish("refused")
            step("read", True, "the same as the preview")
            started = time.time()
            got = restarts.record_planned([host], started, started + now["bound_s"] + 300,
                                          actor, reason, "reload", list_name=list_name)
            if not got.get("ok"):
                step("window", False, got.get("error", "not recorded") + ": nothing was sent")
                return finish("no_window")
            out["window"] = {"from": _iso(started),
                             "until": _iso(started + now["bound_s"] + 300)}
            step("window", True, f"declared until {out['window']['until']}")
            try:
                sent = (reloader or (lambda d: with_temp_connection(d, reload_device)))(device)
            except Exception as exc:                  # noqa: BLE001
                sent = {"ok": False, "outcome": "error", "detail": str(exc)}
            step("reload", sent.get("ok"), sent.get("detail") or sent.get("outcome", ""))
            if not sent.get("ok"):
                return finish(sent.get("outcome") or "not_reloaded")
            back = (wait or _wait_for_ssh)(device.get("ip", ""), now["bound_s"])
            step("wait", back.get("ok"),
                 f"answered after {back.get('after_s')} s" if back.get("ok")
                 else back.get("detail", "it did not answer"))
            if not back.get("ok"):
                return finish("not_back")
            try:
                after = (reader or read_device)(device)
            except Exception as exc:                  # noqa: BLE001
                step("verify", False, f"it answers on SSH's port and could not be read: {exc}")
                return finish("unverified")
            same = roundtrip.stored_is_device(reads.get("running", ""), after.get("running", ""))
            if same.get("equal"):
                step("verify", True, "it signed in with the credential Mercury holds, and runs "
                                     "what it ran")
                return finish("reloaded", ok=True)
            step("verify", False, f"it runs something else: {len(same.get('only_left') or [])} "
                                  f"line(s) gone, {len(same.get('only_right') or [])} new")
            return finish("differs")
    except device_ops.DeviceBusy as exc:
        out["error"] = f"Not reloaded: {exc}. Nothing was sent."
        out["outcome"] = "busy"
        return out


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def preview_start(list_name: str, host: str, actor: str) -> str:
    """The preview as a job (it reads the device); its card redraws on `reload`."""
    from modules.nsot import capture_job
    from modules.outbound import mask_payload

    return capture_job.start(list_name, f"reading {host} for a reload", actor,
                             lambda _j: mask_payload(plan(list_name, host)),
                             kind="reload preview", announce_keys=ANNOUNCE_KEYS,
                             announcer=ANNOUNCER)


def confirm_and_start(list_name: str, host: str, fingerprint: str, reason: str, *,
                      actor: str, ident=None) -> dict:
    """THE confirm: a reason in the shape of one, then the run as a job. ``{"job"}`` or
    ``{"error", "status"}``. The run re-reads and compares; nothing is judged here from a
    preview the browser sent."""
    from modules import identity
    from modules.nsot import capture_job
    from modules.nsot.authorisation import reason_problem
    from modules.outbound import mask_payload

    reason = " ".join((reason or "").split())
    problem = reason_problem({"reason": reason, "line": f"reloading {host}"})
    if problem:
        return {"status": 400, "error": f"Not reloaded: {problem}. Nothing was sent."}
    if not fingerprint:
        return {"status": 400, "error": "Not reloaded: the confirm carried no preview to be "
                                        "bound to. Nothing was sent."}

    def work(_job_id):
        with identity.carried(ident):
            return mask_payload(run(list_name, host, actor=actor, fingerprint=fingerprint,
                                    reason=reason))

    job = capture_job.start(list_name, f"reloading {host}", actor, work, kind=KIND,
                            announce_keys=ANNOUNCE_KEYS, announcer=ANNOUNCER)
    log.info("reload: %s/%s started by %s as job %s", list_name, host, actor, job)
    return {"job": job}
