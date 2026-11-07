"""The controller app deploy channel, Mercury's half (the SDN platform design revision 6, section 10
H, change C and C2; revision 7, decision 25; P6). The controller host's half is the root-owned
apply script, `deploy/controller/mercury-ryu-apply`, and this module LOADS that script's own
functions (`script()`) for what both sides must agree on byte for byte: the request's shape, the
content hash of a staged folder and the drop-in's text. One home, so Mercury's preview is the
script's render, never a second copy of it.

**Staging from the pinned revision's blobs (decision 25; `stage`).** A Published version's
folder is written from git's blobs at its revision (`git ls-tree`, `git cat-file`, through the
repository's git runner), never copied from a working tree, so an uncommitted edit never deploys.
The staged folder's hash is then RECOMPUTED from the bytes written (the script's `folder_hash`,
the same framing as `modules/jobs/lifecycle.content_hash`) and a hash other than the pin refuses,
naming both (`lifecycle.deploy_refusal`).

**The plan (`plan`)** shows the file list with hashes, the drop-in before and after, the
restart, and the switches that reconnect with the post-check's bound, or refuses, each refusal
naming the comparison and both operands:
- a version that is not Published, or whose staged hash is not its pin;
- C2: the unit's User is root (or empty) and `/opt/ryu-apps` may be written by the deploy
  account (nothing is staged);
- a folder the deploy account cannot stage into (root-owned, as from S1 to S3), or one that is
  absent or unreadable;
- the unit's User or command line unreadable (can't tell is never a pass);
- a required app missing from the set, or a requirement cycle;
- conformance (`modules/apps/conformance`, T17).

**What the host's reads are.** Every fact comes from the Linux host capture list's shaped reads
(`modules/discovery._LINUX_SHAPES`): `systemctl show -p User -p ExecStart <unit>` (the User,
and the ryu-manager path and argv systemd holds), `ls -la /opt/ryu-apps` (the folder's owner and
mode) and `systemctl cat <unit>` (the drop-in before). Nothing here dials a host: the caller
reads and passes the texts.

**The held write (`held_write`, C2673)** holds the controller (`device_ops.hold`, operation
`management.HOST_DEPLOY`), opens its plain session as the deploy account and runs the transport
(`modules/apps/transport.send`): the plan's files staged over the session's guarded SFTP, the
request written last, the one command `sudo -n /usr/local/sbin/mercury-ryu-apply`, and the
script's outcome read back whole.

**Not built here (P6's rest):** the registry the enabled set comes from (P4), the preview and
confirm route that calls `held_write` (C2677), the receipt and Needs attention rows (C2677,
C2678), and the screen (a board the operator signs).
"""

import functools
import hashlib
import importlib.machinery
import importlib.util
import json
import logging
import os
import re
import shlex

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "deploy", "controller", "mercury-ryu-apply")
#: Where the script is installed, and the one command the deploy account may run as root.
INSTALLED = "/usr/local/sbin/mercury-ryu-apply"
APPLY_COMMAND = f"sudo -n {INSTALLED}"
#: Apps Mercury always loads first, in this order, when enabled (the design's load order).
FIRST = ("of_versions", "switch_quirks")
_SHOW_LINE = re.compile(r"^(User|ExecStart)=(.*)$")
_ARGV = re.compile(r"argv\[\]=(.*?) ;")
_PATH = re.compile(r"path=(\S+) ;")


class ChannelRefused(ValueError):
    """A staging or a plan refused, in words naming the comparison and both operands."""


@functools.lru_cache(maxsize=1)
def script():
    """The apply script as a module (its functions and constants as the repository holds them;
    the installed copy differs only in the constants its host step renders)."""
    loader = importlib.machinery.SourceFileLoader("mercury_ryu_apply", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# ── staging from blobs ────────────────────────────────────────────────────────────────────────

def stage(repo, path: str, rev: str, dest: str) -> dict:
    """Write the folder *path* of *repo* as git holds it at *rev* into *dest* (which must not
    exist), from blobs, each file with its git mode. Returns ``{"folder", "files": [{"path",
    "mode", "blob", "bytes"}], "sha256"}``, the hash recomputed from what was written. Refuses
    a link or submodule in the folder and a folder git holds nothing in, naming it."""
    from modules.nsot.repo import run_git

    repo = os.fspath(repo)
    norm = os.path.normpath(path).replace(os.sep, "/")
    if not norm or os.path.isabs(path) or norm == ".." or norm.startswith("../"):
        raise ChannelRefused(f"{path!r} is not a folder inside the repository")
    if os.path.lexists(dest):
        raise ChannelRefused(f"the staging folder {dest} exists already: a staging writes a "
                             "fresh folder")
    proc = run_git(repo, "ls-tree", "-r", "-z", "--full-tree", rev, "--", norm, text=False)
    if proc.returncode != 0:
        said = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise ChannelRefused(f"git ls-tree refused {norm} at {rev}: "
                             f"{said[0] if said else 'no reason given'}")
    entries = []
    for raw in (proc.stdout or b"").split(b"\0"):
        if not raw:
            continue
        head, _, name = raw.partition(b"\t")
        mode, kind, obj = head.decode("ascii").split()
        rel = name.decode("utf-8", "surrogateescape")[len(norm) + 1:]
        if mode == "120000":
            raise ChannelRefused(f"{rel} in {norm} at {rev} is a symbolic link: a staged folder "
                                 "holds only files")
        if kind != "blob":
            raise ChannelRefused(f"{rel} in {norm} at {rev} is a {kind}, not a file")
        entries.append((rel, mode, obj))
    if not entries:
        raise ChannelRefused(f"git holds no file in {norm} at {rev}")
    batch = "".join(f"{obj}\n" for _, _, obj in entries).encode("ascii")
    cat = run_git(repo, "cat-file", "--batch", text=False, input=batch)
    if cat.returncode != 0:
        raise ChannelRefused(f"git cat-file could not read {norm}'s blobs at {rev}")
    data, at, files = cat.stdout, 0, []
    os.makedirs(dest, mode=0o755)
    for rel, mode, obj in entries:
        end = data.index(b"\n", at)
        header = data[at:end].decode("ascii").split()
        if len(header) != 3 or header[0] != obj or header[1] != "blob":
            raise ChannelRefused(f"git cat-file answered {' '.join(header)!r} for {rel}'s blob "
                                 f"{obj}")
        size = int(header[2])
        body = data[end + 1:end + 1 + size]
        at = end + 1 + size + 1
        target = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(target), mode=0o755, exist_ok=True)
        perm = 0o755 if mode == "100755" else 0o644
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, perm)
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
        os.chmod(target, perm)
        files.append({"path": rel, "mode": mode, "blob": obj, "bytes": size})
    return {"folder": dest, "files": files, "sha256": script().folder_hash(dest)}


def stage_published(version, repo, path: str, rev: str, dest: str) -> dict:
    """`stage`, then `lifecycle.deploy_refusal` against what was staged: ``{"ok", "staged",
    "refusal"}``. A Draft stages nothing (it deploys only in the container harness)."""
    from modules.jobs.lifecycle import PUBLISHED, deploy_refusal

    if version.state != PUBLISHED:
        return {"ok": False, "staged": None, "refusal": deploy_refusal(version, "")}
    staged = stage(repo, path, rev, dest)
    why = deploy_refusal(version, staged["sha256"])
    return {"ok": not why, "staged": staged, "refusal": why}


# ── the host's reads ──────────────────────────────────────────────────────────────────────────

def parse_show(text: str) -> dict:
    """``{"user", "exec_path", "argv", "readable"}`` from `systemctl show -p User -p ExecStart
    <unit>`'s answer; an absent User line is unreadable, never root."""
    found = {}
    for line in str(text or "").splitlines():
        m = _SHOW_LINE.match(line.strip())
        if m:
            found[m.group(1)] = m.group(2)
    argv_m = _ARGV.search(found.get("ExecStart", ""))
    path_m = _PATH.search(found.get("ExecStart", ""))
    argv = shlex.split(argv_m.group(1)) if argv_m else []
    return {"user": found.get("User"), "exec_path": path_m.group(1) if path_m else "",
            "argv": argv, "readable": "User" in found and bool(argv)}


def parse_ls_dot(text: str) -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "mode", "owner", "group", "error"}`` for the
    folder itself (its ``.`` line) in `ls -la <folder>`'s answer."""
    body = str(text or "")
    if "No such file or directory" in body:
        return {"state": "absent", "mode": "", "owner": "", "group": "", "error": ""}
    for line in body.splitlines():
        parts = line.split()
        if len(parts) >= 9 and parts[-1] == "." and len(parts[0]) >= 10 and parts[0][0] == "d":
            return {"state": "ok", "mode": parts[0][:10], "owner": parts[2], "group": parts[3],
                    "error": ""}
    return {"state": "unreadable", "mode": "", "owner": "", "group": "",
            "error": "the answer holds no line for the folder itself (its `.` entry)"}


def can_write(folder: dict, account: str) -> bool:
    """Whether *account* can stage into *folder* (`parse_ls_dot`): its owner with the owner's
    write bit, its group named the same with the group's, or anyone with the others'."""
    m = folder.get("mode", "")
    return (folder.get("owner") == account and m[2:3] == "w") \
        or (folder.get("group") == account and m[5:6] == "w") or m[8:9] == "w"


def may_write(folder: dict, account: str) -> bool:
    """`can_write`, or the group write bit at all: whether its group holds *account* is not in
    the read, so for the unsafe state (C2) it counts as writable (refusing by resemblance is
    safe)."""
    return can_write(folder, account) or folder.get("mode", "")[5:6] == "w"


def dropin_before(cat_text: str, unit: str) -> str:
    """The text of `<unit>.d/mercury.conf` in `systemctl cat <unit>`'s answer, or "" when the
    unit has none."""
    header = f"# {script().DROPIN_ROOT}/{unit}.d/{script().DROPIN_NAME}"
    out, inside = [], False
    for line in str(cat_text or "").splitlines():
        if line.startswith("# /"):
            inside = line.strip() == header
            continue
        if inside:
            out.append(line)
    return ("\n".join(out).strip("\n") + "\n") if out else ""


# ── the order, the request and the drop-in ────────────────────────────────────────────────────

def load_order(manifests) -> list:
    """*manifests* in load order: every app after the apps it requires, `FIRST` first when
    enabled, the rest by name. Refuses a requirement the set lacks, or a cycle, naming it."""
    by_name = {m.name: m for m in manifests}
    for m in manifests:
        missing = [r for r in m.requires if r not in by_name]
        if missing:
            raise ChannelRefused(f"{m.name} {m.version} requires {', '.join(missing)}, which "
                                 f"the enabled set ({', '.join(sorted(by_name)) or 'none'}) "
                                 "does not hold")
    rank = {n: i for i, n in enumerate(FIRST)}
    done, out = set(), []
    pending = sorted(by_name, key=lambda n: (rank.get(n, len(FIRST)), n))
    while pending:
        ready = [n for n in pending if all(r in done for r in by_name[n].requires)]
        if not ready:
            raise ChannelRefused(f"the requirements of {', '.join(pending)} form a cycle")
        out.append(by_name[ready[0]])
        done.add(ready[0])
        pending.remove(ready[0])
    return out


def request(apps, listen: dict) -> dict:
    """The request the script reads, normalised by the script's own parser (so its hash is the
    script's): *apps* in load order, each ``{"name", "version", "sha256"}``."""
    body = json.dumps({"apps": [{"name": a["name"], "version": a["version"],
                                 "sha256": a["sha256"]} for a in apps],
                       "listen": {"host": listen.get("host"), "port": listen.get("port")}},
                      sort_keys=True).encode("utf-8")
    try:
        return script().parse_request(body)
    except script().Refused as exc:
        raise ChannelRefused(f"the request would be refused by the script: {exc}") from exc


def render_dropin(req: dict, ryu_manager: str) -> str:
    """The drop-in the script writes for *req* (the script's own render)."""
    s = script()
    return s.render_dropin(req, ryu_manager, s.RYU_USER, s.APPS_ROOT)


# ── the plan ──────────────────────────────────────────────────────────────────────────────────

def plan(*, network: str, controller: str, unit: str, enabled, host: dict, listen: dict,
         switches, account: str = "") -> dict:
    """The deploy's plan, or its refusals (see the module's docstring).

    *enabled*: ``[{"version": lifecycle.Version, "manifest": Manifest, "staged": stage()'s
    answer or None}]``; *host*: ``{"show", "ls", "cat"}``, the three reads' texts; *listen*:
    NetBox's ``{"host", "port"}`` for the controller's OpenFlow service; *switches*: the
    expected switches, ``[{"name", "dpid", "selected"}]`` (`profile.select`'s answer)."""
    from modules.apps import conformance, post_check
    from modules.jobs.lifecycle import deploy_refusal

    s = script()
    account = account or s.DEPLOY_USER
    refusals = []
    for item in enabled:
        v, staged = item["version"], item.get("staged")
        why = deploy_refusal(v, staged["sha256"] if staged else "")
        if why:
            refusals.append(why)
    shown = parse_show(host.get("show"))
    folder = parse_ls_dot(host.get("ls"))
    if not shown["readable"]:
        refusals.append(f"can't tell {unit}'s User or command line: `systemctl show -p User -p "
                        f"ExecStart {unit}` answered no User line or no command line, so whether "
                        "Ryu runs as root is not known")
    if folder["state"] != "ok":
        refusals.append(f"{s.APPS_ROOT} cannot be staged into: it is {folder['state']}"
                        + (f" ({folder['error']})" if folder["error"] else ""))
    if shown["readable"] and folder["state"] == "ok":
        as_root = (shown["user"] or "") in ("", "root")
        if as_root and may_write(folder, account):
            refusals.append(
                f"refused before staging (C2): {unit}'s User is {shown['user']!r} (root) and "
                f"{s.APPS_ROOT} is {folder['owner']}:{folder['group']} {folder['mode']}, which "
                f"{account} may write; code it writes would run as root at the next restart. "
                f"Move the unit to User={s.RYU_USER} first (S3 step 1)")
        elif not can_write(folder, account):
            refusals.append(
                f"{account} cannot stage into {s.APPS_ROOT}: it is {folder['owner']}:"
                f"{folder['group']} {folder['mode']} (the folder changes owner at S3 step 1, "
                f"after {unit} runs as User={s.RYU_USER}; its User is {shown['user']!r} now)")
    manifests = [item["manifest"] for item in enabled]
    try:
        ordered = load_order(manifests)
    except ChannelRefused as exc:
        refusals.append(str(exc))
        ordered = manifests
    conf = conformance.check(ordered, switches)
    refusals += [f"conformance: {p}" for p in conf["problems"]]
    out = {"ok": False, "network": network, "controller": controller, "unit": unit,
           "refusals": refusals, "conformance": conf, "user_now": shown["user"],
           "folder": folder}
    if refusals:
        return out
    staged = {item["manifest"].name: item["staged"] for item in enabled}
    apps = [{"name": m.name, "version": m.version, "sha256": staged[m.name]["sha256"]}
            for m in ordered]
    try:
        req = request(apps, listen)
    except ChannelRefused as exc:
        return dict(out, refusals=[str(exc)])
    ryu_manager = shown["exec_path"] or shown["argv"][0]
    after = render_dropin(req, ryu_manager)
    before = dropin_before(host.get("cat"), unit)
    names = [sw.get("name") for sw in switches]
    bound = post_check.bound()
    body = {"request": req, "dropin_after": after, "unit": unit, "controller": controller,
            "switches": sorted(str(sw.get("dpid")) for sw in switches)}
    return dict(out, ok=True, request=req, request_sha256=s.request_sha256(req),
                files={m.name: staged[m.name]["files"] for m in ordered},
                folders={m.name: staged[m.name]["folder"] for m in ordered},
                dropin_before=before, dropin_after=after,
                restart=(f"{unit} on {controller} restarts (systemctl restart, by the apply "
                         f"script), so every switch reconnects: {', '.join(names) or 'none'}"),
                reconnect=dict(bound, switches=names),
                window={"devices": [controller], "unreachable": names,
                        "seconds": window_seconds()},
                plan_sha256=hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8"))
                .hexdigest())


def held_write(plan: dict, *, list_name: str, dev: dict, actor: str) -> dict:
    """Apply *plan* (an ok `plan()`'s answer) to the controller *dev*, holding it as
    `management.HOST_DEPLOY` for *actor*: `transport.send`'s answer, or ``{"ok": False,
    "refused"}`` before anything is sent, naming the comparison and both operands."""
    from modules import connection
    from modules.apps import transport
    from modules.inventory.management import HOST_DEPLOY
    from modules.nsot import device_ops

    dev = dev or {}
    name, ip = dev.get("hostname") or "", dev.get("ip") or ""
    account = script().DEPLOY_USER

    def refused(words):
        return {"ok": False, "refused": f"REFUSED: {words}. Nothing was sent."}

    if not isinstance(plan, dict) or plan.get("ok") is not True:
        return refused(f"the plan is not an approved plan (its ok is "
                       f"{(plan or {}).get('ok')!r})")
    if plan.get("controller") != name:
        return refused(f"the plan is for {plan.get('controller')!r}, and the device is "
                       f"{name!r}")
    if (dev.get("device_type") or "") != "linux":
        return refused(f"{name}'s driver is {dev.get('device_type')!r}, not 'linux', the host "
                       "kind's")
    if (dev.get("username") or "") != account:
        return refused(f"{name}'s login is {dev.get('username')!r}, not the deploy account "
                       f"{account!r}, whose staged files the apply script accepts")
    try:
        with device_ops.hold(list_name, name, HOST_DEPLOY, actor,
                             detail=plan.get("plan_sha256", ""), ip=ip):
            conn = connection.open_ssh(connection.stored_connection_params(dev),
                                       owner=f"{HOST_DEPLOY} {name}", plain=True)
            try:
                return transport.send(conn, plan, ip=ip)
            finally:
                conn.disconnect()
    except (device_ops.DeviceBusy, connection.NoLogin) as exc:
        return refused(str(exc).removesuffix(" No session was opened."))


def window_seconds() -> int:
    """The planned-restart window a deploy declares: the script's restart bound and the
    post-check's, twice (a rollback is a second apply and post-check)."""
    from modules.apps import post_check

    one = script().UP_BOUND_S + post_check.bound()["seconds"]
    return 2 * one
