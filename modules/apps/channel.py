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
restart, what the post-check waits for (`expected`: every switch and link NetBox names and every
enabled app's /health, the board's K6) with its bound, what of that is already missing or
failing at plan time (`already`, from the caller's read of the controller; not read is said),
and what a miss rolls back to (`rollback`, K2: the request the controller ran before by
Mercury's record, or with none recorded the drop-in before, `mercury.conf.prev`, K3). The plan's
hash covers the request, the drop-in after, the unit, the controller, the expected switches,
links and apps, and the rollback target, so a confirm by that hash binds what the post-check
and a rollback will use (C2706). What is already missing is drawn and named at the confirm but
is not in the hash: it is a live read, and the post-check's verdict depends only on what it
expects. It refuses, each refusal naming the comparison and both operands:
- a version that is not Published, or whose staged hash is not its pin;
- C2: the unit's User is root (or empty) and `/opt/ryu-apps` may be written by the deploy
  account (nothing is staged);
- a folder the deploy account cannot stage into (root-owned, as from S1 to S3), or one that is
  absent or unreadable;
- the unit's User or command line unreadable (can't tell is never a pass);
- a required app missing from the set, or a requirement cycle;
- conformance (`modules/apps/conformance`, T17);
- an app's start-time config holding anything Mercury's redaction masks
  (`config_secret_refusal`, decision K9: no secret ever goes in a config file);
- an expected switch with no DPID, an expected link that is not a pair of switch ports, or a
  recorded previous request the script would refuse (a rollback target that could not run).

**An app's start-time config (decision K9; C2707)** is compiled by Mercury (not built here: the
plan takes it per app) and staged as its own file beside the version's folder,
``/opt/ryu-apps/<app>/<version>.config.json`` (the script's `config_path`), so the Published
folder's hash stays the reviewed code's; its sha256 rides in the request as ``config_sha256``,
and the script checks it before it writes the drop-in. Runtime policy (dns_blacklist's verdict
service, say) is the other half of K9: pushed over the app's REST policy endpoint after the
restart, not built here.

**The rollback (decision K3; C2705).** The plan's ``rollback`` (`rollback_target`) is the one
answer to what a miss rolls back to, and it is in the hash: the previous request (kind
``request``), or, on a first deploy, the second request kind (kind ``dropin_before``,
`put_back_request`): the script puts the drop-in before back (its kept `mercury.conf.prev`,
bound to the plan's ``dropin_sha256`` by hash) and restarts. `post_check.deploy` takes it from
the plan and nowhere else. The window (`window`) is sized for the deploy and that rollback.

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

**The operation (`modules/apps/deploy_op.py`, C2677)** calls `plan` for the preview and again at
the confirm, holding the controller itself for the whole deploy and its rollback (one hold
across both sends, where `held_write` holds for one send), and passes *previous* from the
receipt store (`modules/controller_deploy_receipts.record`, K2). Not built here: the registry the
enabled set comes from (P4).
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

def host_commands(unit: str) -> dict:
    """The host's three shaped reads for *unit*, by the part of `plan`'s *host* each answers:
    ``{"show", "ls", "cat"}`` (the Linux host capture list's shapes, `discovery._LINUX_SHAPES`;
    the reads engine refuses any other)."""
    return {"show": f"systemctl show -p User -p ExecStart {unit}",
            "ls": f"ls -la {script().APPS_ROOT}", "cat": f"systemctl cat {unit}"}


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


def _app_entry(a: dict) -> dict:
    entry = {"name": a["name"], "version": a["version"], "sha256": a["sha256"]}
    if a.get("config_sha256") is not None:
        entry["config_sha256"] = a["config_sha256"]
    return entry


def request(apps, listen: dict) -> dict:
    """The request the script reads, normalised by the script's own parser (so its hash is the
    script's): *apps* in load order, each ``{"name", "version", "sha256"}`` and, for an app
    with a start-time config (decision K9), its ``config_sha256`` (`config_bytes`'s sha256).
    An app with no config carries no key, so a request with no config is the shape it always
    was, and hashes the same."""
    body = json.dumps({"apps": [_app_entry(a) for a in apps],
                       "listen": {"host": listen.get("host"), "port": listen.get("port")}},
                      sort_keys=True).encode("utf-8")
    try:
        return script().parse_request(body)
    except script().Refused as exc:
        raise ChannelRefused(f"the request would be refused by the script: {exc}") from exc


def put_back_request(before_text: str) -> dict:
    """The second request kind (decision K3): put the drop-in before back, bound to *before_text*
    (the plan's `dropin_before`, as `systemctl cat` showed it) by the script's own hash, and
    normalised by the script's own parser. Refused when there was no drop-in before, naming
    it: the put-back has nothing to put back then."""
    s = script()
    if not before_text:
        raise ChannelRefused(f"there was no drop-in before the deploy ({s.DROPIN_NAME} was not "
                             "in the unit's configuration when the plan read it), so there is "
                             "nothing to put back")
    body = json.dumps({"kind": s.PUT_BACK, "before_sha256": s.before_sha256(before_text)},
                      sort_keys=True).encode("utf-8")
    try:
        return s.parse_request(body)
    except s.Refused as exc:
        raise ChannelRefused(f"the put-back would be refused by the script: {exc}") from exc


# ── an app's start-time config (decision K9; C2707) ──────────────────────────────────────────

def config_bytes(config) -> bytes:
    """The bytes of an app's compiled start-time config as staged: canonical JSON (sorted keys,
    no spaces, ASCII), one line. Refuses anything but a JSON object of at most the script's
    MAX_BYTES."""
    s = script()
    if not isinstance(config, dict):
        raise ChannelRefused(f"a start-time config is a JSON object, not a "
                             f"{type(config).__name__}")
    try:
        data = (json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                           allow_nan=False) + "\n").encode("ascii")
    except (TypeError, ValueError) as exc:
        raise ChannelRefused(f"a start-time config is not JSON: {exc}") from exc
    if len(data) > s.MAX_BYTES:
        raise ChannelRefused(f"the start-time config is {len(data)} bytes, more than the "
                             f"script's {s.MAX_BYTES}")
    return data


def _leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, path + (str(key),))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _leaves(value, path + (f"[{i}]",))
    else:
        yield path, node


def config_secret_refusal(name: str, version: str, config, values: dict = None) -> str:
    """"" or why *config* may not be staged: it holds something Mercury's redaction would mask
    (`modules/redact`: a known secret value anywhere in its text, or a key and value that read as
    a secret by position or by shape, such as ``password``, ``api_key`` or ``community``). The
    refusal names the key, never the value: no secret ever goes in a config file (decision K9;
    runtime policy that needs one is the app's REST policy endpoint's, after the restart, not
    built here). Refusing by resemblance is safe: a key that only looks like one is refused."""
    from modules import redact

    values = redact.known_secret_values() if values is None else values
    try:
        text = config_bytes(config).decode("ascii")
    except ChannelRefused as exc:
        return f"{name} {version}'s start-time config: {exc}"
    for path, value in _leaves(config):
        key = ".".join(path) or "(the top)"
        last = next((p for p in reversed(path) if not p.startswith("[")), "")
        line = f"{last} {value}" if last else str(value)
        if redact.redact_typed(line, values) != line or redact.redact_text(line, values) != line:
            return (f"{name} {version}'s start-time config key {key} reads as a secret to "
                    "Mercury's redaction (its value is not shown); a config file never carries "
                    "a secret, so nothing is staged")
    # Then the whole text as staged, so a key itself, or a secret split across the keys, is
    # caught too.
    if redact.redact_text(text, values) != text:
        return (f"{name} {version}'s start-time config holds a value Mercury masks as a secret; "
                "a config file never carries a secret, so nothing is staged")
    return ""


def render_dropin(req: dict, ryu_manager: str) -> str:
    """The drop-in the script writes for *req* (the script's own render)."""
    s = script()
    return s.render_dropin(req, ryu_manager, s.RYU_USER, s.APPS_ROOT)


# ── the plan ──────────────────────────────────────────────────────────────────────────────────

def _link_refusal(link) -> str:
    """Why *link* is not a link the post-check can wait for, or ""."""
    try:
        for end in ("src", "dst"):
            if link[end]["dpid"] is None or link[end]["port_no"] is None:
                raise KeyError(end)
    except (KeyError, TypeError):
        return (f"the expected link {link!r} is not a pair of switch ports ({{\"src\": "
                "{\"dpid\", \"port_no\"}, \"dst\": {...}}), so the post-check could not wait "
                "for it")
    return ""


def _typed(value) -> str:
    """*value* as JSON, so a sort key tells 1 from "1" (the post-check compares by equality,
    and the driver's DPIDs are integers)."""
    return json.dumps(value, sort_keys=True)


def _link_key(link) -> list:
    """*link* as its two ends, sorted, so a link and its reverse are one link (as the post-check
    compares them), each value kept as given."""
    return sorted([[link[e]["dpid"], link[e]["port_no"]] for e in ("src", "dst")], key=_typed)


def rollback_target(previous, *, controller: str, dropin_before_text: str) -> dict:
    """What a miss puts back (the board's K2 and K3): *previous*, the request the controller ran
    before by Mercury's record (the last deploy whose outcome left the controller running its
    request), normalised by the script's parser; or, with none recorded (the first deploy
    through Mercury), the drop-in before, which the apply script keeps as `mercury.conf.prev`.
    ``{"kind": "request"|"dropin_before", "request", "request_sha256", "dropin_sha256",
    "words"}``. *request* is the request a rollback sends, the one owner of it
    (`post_check.deploy` sends this and nothing else): the recorded request, or the second
    request kind (`put_back_request`) bound to the drop-in before by the script's own hash,
    which is *dropin_sha256*; with no drop-in before there is nothing to put back, *request* is
    None and the words say a miss is not rolled back. A recorded request the script would
    refuse raises `ChannelRefused`."""
    s = script()
    if previous is None:
        before = dropin_before_text or ""
        first = (f"no previous request is recorded for {controller} (its first deploy through "
                 "Mercury)")
        if not before:
            return {"kind": "dropin_before", "request": None, "request_sha256": "",
                    "dropin_sha256": "",
                    "words": (f"{first} and the unit has no mercury.conf now, so there is no "
                              f"drop-in before for the apply script to put back (it keeps one "
                              f"as {s.DROPIN_NAME}.prev): a miss is not rolled back, and the "
                              "receipt says so")}
        req = put_back_request(before)
        return {"kind": "dropin_before", "request": req, "request_sha256": s.request_sha256(req),
                "dropin_sha256": s.before_sha256(before),
                "words": (f"{first}, so a miss puts back the drop-in before, shown above (the "
                          f"apply script keeps it as {s.DROPIN_NAME}.prev; the put-back request "
                          f"is bound to it by its hash, {s.before_sha256(before)[:12]}), "
                          "restarts again and post-checks again")}
    try:
        req = s.parse_request(json.dumps(previous, sort_keys=True).encode("utf-8"))
    except (s.Refused, TypeError, ValueError) as exc:
        raise ChannelRefused(f"the rollback target, the request {controller} ran before by "
                             f"Mercury's record, would be refused by the script: {exc}") from exc
    apps = ", ".join(f"{a['name']} {a['version']}" for a in req["apps"]) or "no managed app"
    return {"kind": "request", "request": req, "request_sha256": s.request_sha256(req),
            "dropin_sha256": "",
            "words": (f"a miss applies the request {controller} runs by Mercury's record "
                      f"({apps}; request {s.request_sha256(req)[:12]}) as a second request, "
                      "restarts again and post-checks again")}


def already_wrong(expected: dict, observed, switches) -> dict:
    """What of *expected* (the post-check's) is already missing or failing in *observed*, the
    controller read at plan time (the board's K6), so the plan draws it beside what the
    post-check waits for and the confirm names it. ``{"read", "missing_switches",
    "missing_links", "unhealthy", "unreadable", "expecting", "words"}``; *observed* None is
    "not read", said, never "nothing missing"."""
    from modules.apps import post_check

    empty = {"missing_switches": [], "missing_links": [], "unhealthy": [], "unreadable": [],
             "expecting": []}
    if not isinstance(observed, dict):
        return dict(empty, read=False, words=(
            "the controller was not read at plan time, so what is already missing or failing "
            "is not known"))
    got = post_check.evaluate(expected, observed)
    named = {sw.get("dpid"): sw.get("name") for sw in switches}
    gone = [f"{named.get(d) or '?'} ({d})" for d in got["missing_switches"]]
    links = [post_check._link_words(link) for link in got["missing_links"]]  # noqa: SLF001
    sick = list(got["unhealthy"])
    expecting = ([f"expecting {w} to reconnect" for w in gone]
                 + [f"expecting the link {w} to come back" for w in links]
                 + [f"expecting {w.split(' ', 1)[0]}'s /health to recover" for w in sick])
    parts = ([f"switches not connected now: {', '.join(gone)}"] if gone else []) \
        + ([f"links not listed now: {', '.join(links)}"] if links else []) \
        + ([f"apps failing /health now: {', '.join(sick)}"] if sick else []) \
        + ([f"unreadable now: {', '.join(got['unreadable'])}"] if got["unreadable"] else [])
    words = "; ".join(parts) or "every expected switch, link and app's /health answers now"
    if expecting:
        words += (". The post-check expects each of them back, so unless it recovers this "
                  "deploy will miss and roll back")
    return {"read": True, "missing_switches": gone, "missing_links": links, "unhealthy": sick,
            "unreadable": list(got["unreadable"]), "expecting": expecting, "words": words}


def plan(*, network: str, controller: str, unit: str, enabled, host: dict, listen: dict,
         switches, links, previous, observed=None, account: str = "") -> dict:
    """The deploy's plan, or its refusals (see the module's docstring).

    *enabled*: ``[{"version": lifecycle.Version, "manifest": Manifest, "staged": stage()'s
    answer or None, "config": the app's compiled start-time config (a JSON object) or absent}]``
    (an app's config is staged as ``configs[name]``, `config_bytes`'s text, and its sha256 is
    the request's ``config_sha256``, so it is in the plan's hash with the request); *host*:
    ``{"show", "ls", "cat"}``, the three reads' texts; *listen*: NetBox's ``{"host", "port"}``
    for the controller's OpenFlow service; *switches*: the expected switches, ``[{"name",
    "dpid", "selected"}]`` (`profile.select`'s answer); *links*: every link NetBox names
    between them, ``[{"src": {"dpid", "port_no"}, "dst": {...}}]``; *previous*: the request the
    controller ran before by Mercury's record, or None when none is recorded
    (`rollback_target`; the caller passes it from the receipt store,
    `deploy_receipts.record`); *observed*: the controller read at plan time in the post-check's
    shape
    (`post_check.evaluate`), or None when it was not read."""
    from modules.apps import conformance, post_check
    from modules.jobs.lifecycle import deploy_refusal

    s = script()
    account = account or s.DEPLOY_USER
    refusals = [f"the expected switch {sw.get('name') or '?'} has no DPID, so the post-check "
                "could not wait for it" for sw in switches if sw.get("dpid") in (None, "")]
    refusals += [why for why in (_link_refusal(link) for link in links) if why]
    for item in enabled:
        v, staged = item["version"], item.get("staged")
        why = deploy_refusal(v, staged["sha256"] if staged else "")
        if why:
            refusals.append(why)
        if item.get("config") is not None:
            why = config_secret_refusal(item["manifest"].name, item["manifest"].version,
                                        item["config"])
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
    configs = {item["manifest"].name: config_bytes(item["config"]).decode("ascii")
               for item in enabled if item.get("config") is not None}
    apps = [dict({"name": m.name, "version": m.version, "sha256": staged[m.name]["sha256"]},
                 **({"config_sha256": hashlib.sha256(configs[m.name].encode("ascii"))
                     .hexdigest()} if m.name in configs else {}))
            for m in ordered]
    try:
        req = request(apps, listen)
    except ChannelRefused as exc:
        return dict(out, refusals=[str(exc)])
    ryu_manager = shown["exec_path"] or shown["argv"][0]
    after = render_dropin(req, ryu_manager)
    before = dropin_before(host.get("cat"), unit)
    try:
        rollback = rollback_target(previous, controller=controller, dropin_before_text=before)
    except ChannelRefused as exc:
        return dict(out, refusals=[str(exc)])
    names = [sw.get("name") for sw in switches]
    bound = post_check.bound()
    expected = {"switches": [sw.get("dpid") for sw in switches], "links": list(links),
                "apps": [m.name for m in ordered]}
    bound_fields = {"request": req, "dropin_after": after, "unit": unit,
                    "controller": controller, "expected": expected, "rollback": rollback}
    return dict(out, ok=True, request=req, request_sha256=s.request_sha256(req),
                expected=expected, already=already_wrong(expected, observed, switches),
                rollback=rollback,
                files={m.name: staged[m.name]["files"] for m in ordered},
                folders={m.name: staged[m.name]["folder"] for m in ordered},
                configs=configs,
                dropin_before=before, dropin_after=after,
                restart=(f"{unit} on {controller} restarts (systemctl restart, by the apply "
                         f"script), so every switch reconnects: {', '.join(names) or 'none'}"),
                reconnect=dict(bound, switches=names),
                window={"devices": [controller], "unreachable": names,
                        "seconds": window_seconds()},
                plan_sha256=plan_hash(bound_fields))


def plan_hash(plan: dict) -> str:
    """The plan's hash, from the fields of *plan* (a `plan` answer, or the same fields) that a
    confirm binds: the request, the drop-in after, the unit, the controller, the expected
    switches, links (each link's ends sorted, so a link and its reverse are one) and apps, and
    the rollback target's kind and hashes (C2706). What is already missing (``already``) is a
    live read and is not in it. `post_check.deploy` recomputes it from the plan it is handed and
    refuses a plan whose hash moved. Raises KeyError or TypeError on a plan without them."""
    expected, rollback = plan["expected"], plan["rollback"]
    body = {"request": plan["request"], "dropin_after": plan["dropin_after"],
            "unit": plan["unit"], "controller": plan["controller"],
            "expected": {"switches": sorted(expected["switches"], key=_typed),
                         "links": sorted((_link_key(link) for link in expected["links"]),
                                         key=_typed),
                         "apps": expected["apps"]},
            "rollback": {"kind": rollback["kind"], "request_sha256": rollback["request_sha256"],
                         "dropin_sha256": rollback["dropin_sha256"]}}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


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


def window() -> dict:
    """``{"seconds", "words", "parts"}``: the planned-restart window a deploy declares (F7;
    C2711), the whole worst case it sits inside, twice over (a rollback is a second request
    and a second post-check, inside the same window). Each pass is:
    - the session the staging runs over opening (`connection.CONNECT_TIMEOUT_S`, which bounds
      its connect, banner, key exchange and authentication);
    - the one command's wait (`transport.command_bound_s`, 2.5 times the script's restart
      bound, `UP_BOUND_S`), which holds the script's whole run: its checks, the drop-in's
      write, the restart and its wait for the unit, so the unit's up bound is counted inside
      it and not again;
    - the post-check's bound (`post_check.bound`).
    The staging transfer itself has no bound of its own (an SFTP write waits as long as the
    session stays open), so it is named in the words and not counted; nothing here is a new
    figure, each part is its constant's."""
    from modules import connection
    from modules.apps import post_check, transport

    up = script().UP_BOUND_S
    parts = {"session": int(connection.CONNECT_TIMEOUT_S),
             "command": int(round(transport.command_bound_s())),
             "post_check": int(post_check.bound()["seconds"])}
    one = sum(parts.values())
    seconds = 2 * one
    words = (f"{seconds} s: twice (the deploy, then room for its rollback) the session's "
             f"opening bound of {parts['session']} s, the apply command's wait of "
             f"{parts['command']} s ({transport.COMMAND_BOUND_FACTOR} times the script's "
             f"restart bound of {up} s, which it holds: the unit's wait is inside it) and the "
             f"post-check's bound of {parts['post_check']} s. The script's restart bound and "
             "the post-check's are placeholders until S1 measures them; the staging transfer "
             "has no bound of its own and is not counted")
    return {"seconds": seconds, "words": words, "parts": parts}


def window_seconds() -> int:
    """`window`'s seconds."""
    return window()["seconds"]
