"""nsot/reload_op.py — Reload, a gated device-page operation (P.14; cutover blocker 6,
2026-10-10; drawn under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md).

P.14's plain form: the device boots the startup configuration it holds, and the first gate
requires that to be what it runs, so no file is sent and nothing in running is lost. Revert by
reload (booting a moment from history, the charter's Phase 2) builds on this with a boot file;
it is not this.

The preview (a job: it reads the device) reads the running and startup configurations, `show
version`, `show boot` and the `dir` reads (`read_device`), and judges P.14's six gates and C2239's SSH host key, each drawn by name with what it found:
1. running against startup (unsaved changes refuse; Persist… saves them first, previewed; a
   certificate startup keeps as a file in nvram: is the same certificate running shows inline
   when `dir nvram:` lists the file, and refuses, named, when it does not);
2. running against its golden and its committed intent (a departure is shown, and the stated
   reason is recorded as acknowledging it);
3. the startup configuration carries every account line running holds (the startup check's
   judgement, `onboard.startup_carries`);
4. the image it booted exists, and the boot variable, where the platform has one, names a file
   that exists;
5. no operation holds the device;
5a. its SSH host key survives (C2239, `_host_key_gate`): a key pair not saved, or two saved
   general-purpose key pairs with none named for SSH, asks for the stated reason;
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
     "a login with the credential Mercury holds, tried again for up to 3 minutes while the "
     "device starts serving SSH, and what it runs compared with what it ran; the window ends "
     "only once this passes", ("verify",)),
    ("record", "Record", "the reload's row: who, why, the window and each step's outcome",
     ("record",)),
)

#: Verify again's steps (C2240), for a reload that ended not verified: the same sign-in within
#: the bound, then what it runs compared with its committed golden (the run kept no copy of
#: what it ran; the preview's gate 2 checked it matched its golden, or took a reason).
VERIFY_STEPS = (
    ("verify", "Sign in and compare",
     "signed in to within the bound, the pauses growing, and what it runs compared with its "
     "committed golden", ("verify",)),
    ("record", "Record", "the verify's row beside the reload's: who, when and the outcome",
     ("record",)),
)
#: The job kind of a Verify again (`reload_job_card` draws its stepper from VERIFY_STEPS).
VERIFY_KIND = "reload_verify"

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
#: image path `show version` or `show boot` printed (`_images`), one token, or `nvram:` when
#: startup keeps a certificate as a file there (`normalize.certificate_pointers`).
_READ = dict(read_timeout=60, strip_prompt=True, strip_command=True)
NVRAM = "nvram:"


def read_device(device: dict) -> dict:
    """ONE session: the running configuration (`config_read.read`), then `show
    startup-config`, `show version`, `show boot` (a platform without it says so), `dir` of
    each image named, and `dir nvram:` when startup keeps a certificate as a file there.
    ``{"running", "startup", "version", "boot", "dirs": {path: text}}``.
    Reads only, so it takes no hold: the preview's job is a read, and the run that changes the
    device holds it (`run`)."""
    from modules.connection import with_temp_connection

    def read(conn):
        out = read_boot_pair(conn, device.get("hostname", ""))
        nvram = out.pop("nvram")
        out["version"] = conn.send_command("show version", **_READ) or ""
        boot = conn.send_command("show boot", **_READ) or ""
        out["boot"] = "" if "Invalid input" in boot else boot
        keys = conn.send_command("show crypto key mypubkey rsa", **_READ) or ""
        out["keys"] = "" if "Invalid input" in keys else keys
        out["dirs"] = {}
        for path in _images(out["version"], out["boot"]):
            if re.fullmatch(r"[\w.:/-]+", path):           # one token, as the device printed it
                out["dirs"][path] = conn.send_command(f"dir {path}", **_READ) or ""
        if nvram is not None:                               # startup keeps a certificate there
            out["dirs"][NVRAM] = nvram
        return out

    return with_temp_connection(device, read)


#: Where IOS and IOS-XE say a key pair is kept when `write memory` saved it (C2239: the
#: routers' keys read "private-config"; every vIOS-L2 switch's read "not specified", 2026-11-01).
SAVED_STORAGE = ("private-config", "nvram")


def rsa_keys(text: str) -> list:
    """`show crypto key mypubkey rsa` as ``[{"name", "storage", "general"}]``: each key pair,
    where it is kept (``""`` when not said) and whether it is a general-purpose key (the kind
    SSH serves; an encryption key is its pair's half)."""
    keys = []
    for block in re.split(r"(?m)^% Key pair was generated at:", text or "")[1:]:
        name = re.search(r"(?m)^\s*Key name:\s*(\S+)", block)
        storage = re.search(r"(?m)^\s*Storage Device:\s*(.+?)\s*$", block)
        usage = re.search(r"(?m)^\s*Usage:\s*(.+?)\s*$", block)
        if name:
            keys.append({"name": name.group(1),
                         "storage": storage.group(1) if storage else "",
                         "general": bool(usage and "general" in usage.group(1).lower())})
    return keys


def _host_key_gate(reads: dict) -> dict:
    """Whether the SSH host key survives a reload (C2239): a key pair `write memory` did not
    save is made anew at boot, and Mercury refuses every session to a device whose key changed
    until a person reviews it. Read from `show crypto key mypubkey rsa` and the running
    configuration's `ip ssh rsa keypair-name`. A reason acknowledges it; never a refusal, since
    the reload itself is sound and the new key is a person's to review."""
    gate = {"name": "its SSH host key survives the reload", "key": "host_key"}
    text = reads.get("keys")
    if not text:
        return dict(gate, state="ack", detail=(
            "its key pairs were not read (`show crypto key mypubkey rsa`), so whether its SSH "
            "host key survives the reload is not known. Your reason is recorded as "
            "acknowledging it"))
    keys = rsa_keys(text)
    named = re.search(r"(?m)^ip ssh rsa keypair-name (\S+)", reads.get("running", "") or "")
    serving = [k for k in keys if k["general"] and (not named or k["name"] == named.group(1))]
    if not serving:
        return dict(gate, state="ack", detail=(
            "no general-purpose key pair " + (f"named {named.group(1)} " if named else "")
            + "was listed, so which key SSH serves is not known. Your reason is recorded as "
            "acknowledging it"))
    unsaved = [k for k in serving if not k["storage"].lower().startswith(SAVED_STORAGE)]
    if unsaved:
        return dict(gate, state="ack", detail=(
            "its key pair "
            + ", ".join(f"{k['name']} (Storage Device: {k['storage'] or 'not said'})"
                        for k in unsaved)
            + " is not saved, so the reload makes a new one: its SSH host key changes, and "
            "Mercury refuses every session to it until a person reviews the new key on its "
            "page. Your reason is recorded as acknowledging it"))
    if len(serving) > 1:
        return dict(gate, state="ack", detail=(
            f"it keeps {len(serving)} general-purpose key pairs ("
            + ", ".join(k["name"] for k in serving) + ") and its configuration names none for "
            "SSH (`ip ssh rsa keypair-name`), so which one SSH serves after the reload is not "
            "fixed: a C8000v keeping two came back from a reload serving the other (C2239, its "
            "cause not confirmed). Your reason is recorded as acknowledging it"))
    return dict(gate, state="pass", detail=(
        f"its key pair {serving[0]['name']} is saved ({serving[0]['storage']}), so the reload "
        "keeps its SSH host key"))


def nvram_read(conn, startup: str):
    """`dir nvram:` on *conn* when *startup* keeps a certificate as a file there
    (`normalize.certificate_pointers`), else None, nothing sent: the read
    `roundtrip.startup_is_running` needs to tell a certificate's storage from a difference."""
    from modules.nsot import normalize

    if not normalize.certificate_pointers(startup):
        return None
    return conn.send_command(f"dir {NVRAM}", **_READ) or ""


def read_boot_pair(conn, hostname: str) -> dict:
    """What a device runs and what it boots, read on *conn* as Reload's gate reads them:
    the running configuration (`config_read.read`), `show startup-config`, and `dir nvram:`
    when startup keeps a certificate there (`nvram_read`). ``{"running", "startup",
    "nvram"}``, ``nvram`` None when not read. Persist's preview reads the same (C886)."""
    from modules import config_read

    out = {"running": config_read.read(conn, hostname)}
    out["startup"] = conn.send_command("show startup-config", **_READ) or ""
    out["nvram"] = nvram_read(conn, out["startup"])
    return out


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


def _unsaved_words(host: str, same: dict) -> str:
    """Gate 1's detail from `roundtrip.startup_is_running`'s answer: a certificate startup
    keeps as a file is the same certificate, said so; one whose file is absent is named; the
    count of differing lines leaves the certificate storage out."""
    present, missing = same.get("present") or [], same.get("missing") or []
    unsaved = len(same.get("only_left") or []) + len(same.get("only_right") or [])
    if same.get("equal"):
        if not present:
            return "they are the same: it boots what it runs"
        n = len(present)
        held = "present" if n == 1 else "both present" if n == 2 else f"all {n} present"
        return (f"they are the same; startup keeps {host}'s {n} certificate{'s' * (n != 1)} as "
                f"files in nvram: ({held}), running shows {'it' if n == 1 else 'them'} inline")
    parts = []
    if missing:
        it = "it" if len(missing) == 1 else "them"
        parts.append("startup keeps " + ", ".join(
            f"{c['certificate']} of {c['chain'].split()[-1]} as {c['file']}" for c in missing)
            + f", and `dir nvram:` does not list {it}: a reload would boot without {it}")
    if unsaved:
        parts.append(f"{unsaved} line(s) differ: a reload would boot startup and lose them; "
                     "save them first (Persist…)")
    return "; ".join(parts)


def judge(list_name: str, host: str, platform: str, reads: dict, *, holding: bool = False) -> dict:
    """The gates from *reads* (P.14's six and C2239's SSH host key), and the fingerprint the
    confirm is bound to. *holding*: the
    run judging under its own hold, which is not another operation's."""
    from modules.nsot import blast_radius, device_ops, onboard, repo as R, roundtrip
    from modules.nsot.intent_match import explain, intent_match

    repo = _repo(list_name)
    running, startup = reads.get("running", ""), reads.get("startup", "")
    gates = []
    same = roundtrip.startup_is_running(startup, running, (reads.get("dirs") or {}).get(NVRAM, ""))
    gates.append({"name": "running against startup", "key": "unsaved",
                  "state": "pass" if same.get("equal") else "fail",
                  "detail": _unsaved_words(host, same)})
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
    gates.append(_host_key_gate(reads))
    busy = "" if holding else device_ops.busy_text(list_name, host)   # the run holds it itself
    gates.append({"name": "no other operation holds it", "key": "busy",
                  "state": "fail" if busy else "at_apply",
                  "detail": busy or "checked again when the run takes the device"})
    radius = blast_radius.for_device(repo, host)
    seconds, bound_words = wait_bound(platform)
    shown = json.dumps({"running": _h(running), "startup": _h(startup),
                        "image": _IMAGE.search(reads.get("version", "") or "") and
                        _IMAGE.search(reads.get("version", "")).group(1),
                        "departs": departs,
                        "keys": [[k["name"], k["storage"]] for k in rsa_keys(reads.get("keys"))]},
                       sort_keys=True)
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


#: How long verify keeps trying to sign in after the device's SSH port first answers, and its
#: pauses between tries. The port answers before the device serves SSH: a C8000v on 2026-10-30
#: (B2) answered at about 01:11:37 UTC and logged `%SSH-5-ENABLED` at 01:11:51, 14 s later, so a
#: single read failed and a reload that came back read unverified (C2240). The bound is the
#: operator's, about 3 minutes (2026-11-01), 13 times that measured gap.
VERIFY_BOUND_S = 180
VERIFY_PAUSES_S = (5, 10, 20, 30)


def _verify_read(read, bound: float = VERIFY_BOUND_S, *, clock=time.monotonic,
                 sleep=time.sleep) -> dict:
    """*read* (one session) until it answers, within *bound*: ``{"ok", "reads", "attempts",
    "after_s", "error", "refused"}``. A refused host key is never tried again: it is the
    device's answer, not its boot (C2239), and ``refused`` carries it. The pauses grow
    (VERIFY_PAUSES_S, then the last of them) and the last try starts inside the bound."""
    from modules.host_keys import HostKeyRefused

    start, attempts, error = clock(), 0, ""
    while True:
        attempts += 1
        try:
            reads = read()
            return {"ok": True, "reads": reads, "attempts": attempts,
                    "after_s": round(clock() - start), "error": "", "refused": None}
        except HostKeyRefused as exc:
            return {"ok": False, "reads": None, "attempts": attempts,
                    "after_s": round(clock() - start), "error": str(exc), "refused": exc}
        except Exception as exc:                      # noqa: BLE001
            error = str(exc)
        pause = VERIFY_PAUSES_S[min(attempts - 1, len(VERIFY_PAUSES_S) - 1)]
        if clock() - start + pause >= bound:
            return {"ok": False, "reads": None, "attempts": attempts,
                    "after_s": round(clock() - start), "error": error, "refused": None}
        sleep(pause)


def records_path(repo_dir: str) -> str:
    """Where a network's reloads are recorded, from its repository folder: resolving it
    creates nothing (a READ must not bring a network's folder into being)."""
    return os.path.join(repo_dir, ".nsot", "reloads.jsonl")


#: The record's path inside the network's repository, as a commit names it.
RECORDS_REL = ".nsot/reloads.jsonl"


def record(list_name: str, row: dict) -> dict:
    """Append one reload's row and COMMIT it (B5 of the W2 walk, 2026-10-17: the row sat
    uncommitted, so the remote never held it and History's header read "in sync" beside
    it), through `repo._commit_paths`, the one commit path, which publishes. ``{"ok",
    "error", "commit", "commit_error"}``. Never raises: the reload happened whether or not
    its record could be written or committed, and the result says which. The file is
    written under the repository lock, so the commit carries exactly this row and any row
    an earlier version left uncommitted."""
    from modules.config import open_secure
    from modules.nsot import repo as R

    repo = _repo(list_name)
    path = records_path(repo)
    try:
        with R.repo_lock(repo):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open_secure(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
            subject = (f"reload: {row.get('device')} "
                       f"{'reloaded and verified' if row.get('ok') else row.get('outcome')}")
            got = R._commit_paths(list_name, [RECORDS_REL],              # noqa: SLF001
                                  f"{subject}\n\n{(row.get('reason') or '').strip()}",
                                  [f"Actor: {row.get('by') or 'unknown'}",
                                   f"Reload-Device: {row.get('device')}"], "reload")
    except Exception as exc:                          # noqa: BLE001
        log.error("reload: the record was NOT written for %s: %s", row.get("device"), exc)
        return {"ok": False, "error": str(exc), "commit": "", "commit_error": ""}
    if not got.get("ok"):
        log.error("reload: the record for %s was written and NOT committed: %s",
                  row.get("device"), got.get("error"))
    return {"ok": True, "error": "", "commit": got.get("commit", ""),
            "commit_error": "" if got.get("ok") else (got.get("error") or "not committed")}


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
        wait=None, reader=None, reloader=None, clock=None, verify_sleep=None) -> dict:
    """The run, holding the device. ``{"ok", "outcome", "steps", "record", ...}``; *wait*,
    *reader* and *reloader* replace the device-facing parts in tests, *clock* and
    *verify_sleep* the verify's retry timing."""
    from modules import restarts
    from modules.connection import with_temp_connection
    from modules.device_reload import reload_device
    from modules.nsot import device_ops, roundtrip

    device = _device(list_name, host)
    steps = []
    window = {}
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
            # The devices the preview said Mercury loses its path to, kept on the window as
            # its expected effects (the attribution rule, PHASE8_PLAN 20.2).
            radius = now.get("radius") or {}
            got = restarts.record_planned([host], started, started + now["bound_s"] + 300,
                                          actor, reason, "reload", list_name=list_name,
                                          unreachable=(radius.get("cut") or []
                                                       if radius.get("state") == "known"
                                                       else []))
            if not got.get("ok"):
                step("window", False, got.get("error", "not recorded") + ": nothing was sent")
                return finish("no_window")
            out["window"] = {"from": _iso(started),
                             "until": _iso(started + now["bound_s"] + 300),
                             "silence": got.get("silence"),
                             "silence_words": got.get("silence_words", "")}
            window = got.get("record") or {}
            # Said on the step, never only logged: a silence that could not be set is the
            # one fact a person needs before the alerts arrive (B3).
            step("window", True, f"declared until {out['window']['until']}"
                 + (f"; {got['silence_words']}" if got.get("silence_words") else ""))
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
            # Its port answers before it serves SSH (C2240: 14 s on a C8000v), so verify signs in
            # again within a bound; the window stays open until the reload is verified, and
            # otherwise runs to its declared end.
            tried = _verify_read(lambda: (reader or read_device)(device),
                                 **({"clock": clock} if clock else {}),
                                 **({"sleep": verify_sleep} if verify_sleep else {}))
            if tried["refused"] is not None:
                refused = tried["refused"]
                step("verify", False,
                     f"it answered with an SSH host key Mercury does not hold (offered "
                     f"{refused.offered.get('fingerprint', '?')}, held "
                     f"{refused.held.get('fingerprint', '?')}): every session to it is refused "
                     "until a person reviews the new key")
                return finish("host_key_changed")
            if not tried["ok"]:
                step("verify", False,
                     f"it answers on SSH's port and could not be read in {tried['attempts']} "
                     f"{'try' if tried['attempts'] == 1 else 'tries'} over {tried['after_s']} s: "
                     f"{tried['error']}")
                return finish("unverified")
            after = tried["reads"]
            same = roundtrip.stored_is_device(reads.get("running", ""), after.get("running", ""))
            if same.get("equal"):
                # Verified: the window ends now, not at its declared end, so a fall after this
                # is raised at once; its Grafana silence ends a settle margin later, since the
                # alerts outlast the return (B3).
                if window:
                    ended = restarts.end_window(
                        window, time.time(),
                        f"the reload is verified: {host} answered after {back.get('after_s')} s "
                        f"and signed in after {tried['after_s']} s more", by=actor)
                    out["window"]["ended"] = ended.get("ended_at")
                    out["window"]["end_words"] = ended.get("words", "")
                step("verify", True, "it signed in with the credential Mercury holds, and runs "
                                     "what it ran"
                     + (f" (signed in on try {tried['attempts']}, {tried['after_s']} s after its "
                        "port answered)" if tried["attempts"] > 1 else ""))
                return finish("reloaded", ok=True)
            step("verify", False, f"it runs something else: {len(same.get('only_left') or [])} "
                                  f"line(s) gone, {len(same.get('only_right') or [])} new")
            return finish("differs")
    except device_ops.DeviceBusy as exc:
        out["error"] = f"Not reloaded: {exc}. Nothing was sent."
        out["outcome"] = "busy"
        return out


def unverified(list_name: str) -> list:
    """Each device of *list_name* whose newest reload record ended not verified (C2240):
    ``[row, ...]``, newest first; a later record (a reload or a Verify again) replaces it.
    Raises OSError or ValueError when the record cannot be read."""
    got = read_records(_repo(list_name))
    if got["state"] == "unreadable":
        raise ValueError(got.get("error") or "the reload record could not be read")
    newest = {}
    for r in got["rows"]:
        newest.setdefault(r.get("device", ""), r)
    return [r for r in newest.values() if r.get("outcome") == "unverified"]


def verify_again(list_name: str, host: str, *, actor: str, reader=None, clock=None,
                 verify_sleep=None) -> dict:
    """Verify again (C2240), holding the device: sign in within the verify's bound and compare
    what it runs with its committed golden; recorded beside the reload as its own row (kind
    ``verify_again``). Sends nothing but the reads. ``{"ok", "outcome", "steps", "record",
    ...}``, the run's shape, so the Reload card draws it."""
    from modules.nsot import device_ops, repo as R, roundtrip

    device = _device(list_name, host)
    steps = []
    out = {"ok": False, "device": host, "list": list_name, "by": actor, "kind": "verify_again",
           "reason": "Verify again, after a reload that ended not verified",
           "outcome": "", "steps": steps}

    def step(name, ok, detail):
        steps.append({"step": name, "ok": bool(ok), "detail": detail})
        device_ops.note(name)

    def finish(outcome, ok=False):
        out.update(outcome=outcome, ok=ok, at=_iso(time.time()))
        out["record"] = record(list_name, {k: out[k] for k in
                                           ("at", "device", "list", "by", "reason", "outcome",
                                            "ok", "steps", "kind")})
        device_ops.note("record")
        return out

    if device is None:
        out["error"] = f"{host} is not in {list_name}'s inventory"
        return out
    try:
        with device_ops.hold(list_name, host, "reload", actor or "unknown"):
            tried = _verify_read(lambda: (reader or read_device)(device),
                                 **({"clock": clock} if clock else {}),
                                 **({"sleep": verify_sleep} if verify_sleep else {}))
            if tried["refused"] is not None:
                refused = tried["refused"]
                step("verify", False,
                     f"it answered with an SSH host key Mercury does not hold (offered "
                     f"{refused.offered.get('fingerprint', '?')}, held "
                     f"{refused.held.get('fingerprint', '?')}): review it with Re-key…")
                return finish("host_key_changed")
            if not tried["ok"]:
                step("verify", False,
                     f"it could not be read in {tried['attempts']} "
                     f"{'try' if tried['attempts'] == 1 else 'tries'} over {tried['after_s']} s: "
                     f"{tried['error']}")
                return finish("unverified")
            golden = R.golden_at(_repo(list_name), host, "HEAD") or ""
            if not golden:
                step("verify", False, "it signed in, and has no committed golden to compare "
                                      "what it runs with")
                return finish("unverified")
            same = roundtrip.stored_is_device(golden, tried["reads"].get("running", ""))
            if same.get("equal"):
                step("verify", True, "it signed in with the credential Mercury holds, and runs "
                                     "what its committed golden holds")
                return finish("reloaded", ok=True)
            step("verify", False, f"it signed in, and runs something other than its committed "
                                  f"golden: {len(same.get('only_left') or [])} line(s) gone, "
                                  f"{len(same.get('only_right') or [])} new")
            return finish("differs")
    except device_ops.DeviceBusy as exc:
        out["error"] = f"Not verified: {exc}. Nothing was read."
        out["outcome"] = "busy"
        return out


def verify_again_start(list_name: str, host: str, *, actor: str, ident=None) -> dict:
    """Verify again as a job (it reads the device for up to the verify's bound). ``{"job"}``."""
    from modules import identity
    from modules.nsot import capture_job
    from modules.outbound import mask_payload

    def work(_job_id):
        with identity.carried(ident):
            return mask_payload(verify_again(list_name, host, actor=actor))

    job = capture_job.start(list_name, f"verifying {host} again", actor, work,
                            kind=VERIFY_KIND, announce_keys=ANNOUNCE_KEYS,
                            announcer=ANNOUNCER, device=host, card="reload")
    log.info("reload: %s/%s verify again started by %s as job %s", list_name, host, actor, job)
    return {"job": job}


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
                            announce_keys=ANNOUNCE_KEYS, announcer=ANNOUNCER,
                            device=host, card="reload")
    log.info("reload: %s/%s started by %s as job %s", list_name, host, actor, job)
    return {"job": job}
