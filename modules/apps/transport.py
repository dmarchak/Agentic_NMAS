"""The controller app deploy channel's TRANSPORT (the SDN platform design revision 6, section 10
H, change C; P6; C2673): what crosses to the controller host, in this order and nothing else.

1. **The files**, each app's folder staged over SFTP as the deploy account to
   ``/opt/ryu-apps/<name>/<version>/<relative path>``, every byte read back from the local
   staged folder (`channel.stage`, git's blobs at the pinned revision) and checked against the
   plan's blob id and the request's content hash first: what is confirmed is what is sent.
2. **The request**, ``/opt/ryu-apps/.apply/request.json``, written LAST, in the apply script's
   exact shape (`channel.request`, the script's own parser), so the script never reads a
   request whose folders are not all there.
3. **The one command**, ``sudo -n /usr/local/sbin/mercury-ryu-apply``: no argument, nothing
   else on the line (`discovery.held_write_refusal`, exact string).
4. **The outcome**, ``/var/lib/mercury-ryu-apply/outcome.json`` (the script's OUTCOME_DIR),
   read back over SFTP and returned whole, beside the line the script printed.

**The write guard (`staging_refusal`)** is the session's: `connection.open_sftp` gives a host
kind's session an SFTP client that writes only a path of `staging_refusal`'s exact shapes, only
while this thread holds the device (`device_ops.may_write`), and refuses a link on the way
(every existing part of the path is `lstat`-ed before a write). Allowing is by exact shape:
- a file: ``/opt/ryu-apps/<name>/<version>/<part>[/<part>...]`` or exactly
  ``/opt/ryu-apps/.apply/request.json``;
- a folder: ``/opt/ryu-apps/<name>``, ``/opt/ryu-apps/<name>/<version>[/<part>...]`` or
  exactly ``/opt/ryu-apps/.apply``;
where <name> and <version> match the script's NAME and VERSION, and each <part> is
`PART` and never ``.`` or ``..`` (so no ``..``, no empty part from an absolute part or a
doubled slash). Anything else is refused naming the path and the rule.

**A failure partway** names what was staged and what was not, and whether the request was
written and the command sent. Nothing is ever deleted on the controller by the transport: a
second run writes the same bytes over the same paths, and the apply script judges the folder
by its recomputed hash.
"""

import json
import logging
import os
import posixpath
import re

log = logging.getLogger(__name__)

#: One part of a staged file's relative path below <name>/<version>: printable, no slash, no
#: space (refusing by resemblance is safe: a part outside it is refused, never quoted whole).
PART = re.compile(r"^[A-Za-z0-9_.+-]{1,128}$")
#: How long the one command's answer is waited for. NOT MEASURED (S1, 2026-11-10, measures the
#: controller's restart): about 2.5 times the script's own restart bound, `UP_BOUND_S`, itself a
#: placeholder; named in the refusal it fires in.
COMMAND_BOUND_FACTOR = 2.5


class TransportRefused(ValueError):
    """Refused before anything was sent, naming the comparison and both operands."""


def _script():
    from modules.apps import channel
    return channel.script()


def apps_root() -> str:
    return _script().APPS_ROOT


def request_path() -> str:
    s = _script()
    return posixpath.join(s.APPS_ROOT, *s.REQUEST_REL.split(os.sep))


def outcome_path() -> str:
    return posixpath.join(_script().OUTCOME_DIR, "outcome.json")


def command_bound_s() -> float:
    return COMMAND_BOUND_FACTOR * _script().UP_BOUND_S


def staging_refusal(path, kind: str = "file") -> str:
    """"" when *path* is a staging path of *kind* (``file`` or ``dir``) of the module's exact
    shapes, else the refusal naming the path and the rule it failed."""
    s = _script()
    root = s.APPS_ROOT
    shown = repr(str(path)[:160])
    rules = (f"a file is written only to {root}/<name>/<version>/<relative path> or "
             f"{request_path()}, a folder only to {root}/<name>, {root}/<name>/<version>[/...] "
             f"or {posixpath.dirname(request_path())}; <name> matches {s.NAME.pattern}, "
             f"<version> {s.VERSION.pattern}, each further part {PART.pattern}, never . or ..")
    if kind not in ("file", "dir"):
        return f"REFUSED: {kind!r} is neither a file nor a folder write. Nothing was sent."
    if not isinstance(path, str) or not path.isascii() or not path.isprintable():
        return f"REFUSED: the path {shown} is not printable ASCII ({rules}). Nothing was sent."
    if kind == "file" and path == request_path():
        return ""
    if kind == "dir" and path == posixpath.dirname(request_path()):
        return ""
    if not path.startswith(root + "/"):
        return f"REFUSED: the path {shown} is not under {root} ({rules}). Nothing was sent."
    parts = path[len(root) + 1:].split("/")
    for i, part in enumerate(parts):
        if part == "":
            return (f"REFUSED: the path {shown} has an empty part {i + 1} (an absolute part or "
                    f"a doubled or trailing slash; {rules}). Nothing was sent.")
        if part in (".", ".."):
            return (f"REFUSED: the path {shown} has the part {part!r} ({rules}). Nothing was "
                    "sent.")
    if not s.NAME.match(parts[0]):
        return (f"REFUSED: the path {shown}'s app name {parts[0][:60]!r} does not match "
                f"{s.NAME.pattern} ({rules}). Nothing was sent.")
    if len(parts) == 1:
        return "" if kind == "dir" else (
            f"REFUSED: the path {shown} is an app's folder, not a file in a version's folder "
            f"({rules}). Nothing was sent.")
    if not s.VERSION.match(parts[1]):
        return (f"REFUSED: the path {shown}'s version {parts[1][:60]!r} does not match "
                f"{s.VERSION.pattern} ({rules}). Nothing was sent.")
    if len(parts) == 2 and kind == "file":
        return (f"REFUSED: the path {shown} is a version's folder, not a file in it ({rules}). "
                "Nothing was sent.")
    for part in parts[2:]:
        if not PART.match(part):
            return (f"REFUSED: the path {shown}'s part {part[:60]!r} does not match "
                    f"{PART.pattern} ({rules}). Nothing was sent.")
    return ""


def read_refusal(path) -> str:
    """"" when *path* is the one file the transport reads back (`outcome_path`), else why."""
    if path == outcome_path():
        return ""
    return (f"REFUSED: the path {str(path)[:160]!r} is not {outcome_path()}, the one file the "
            "controller's deploy channel reads back. Nothing was read.")


# ── what is sent ─────────────────────────────────────────────────────────────────────────────

def _items(plan: dict) -> list:
    """``[(app, local folder, remote folder, [(file, local path, remote path, perm)])]`` in
    the request's load order, every byte checked against the plan first (`TransportRefused`
    naming both operands)."""
    s = _script()
    if not isinstance(plan, dict) or plan.get("ok") is not True:
        raise TransportRefused("REFUSED: the plan is not an approved plan (its ok is "
                               f"{(plan or {}).get('ok')!r}), so nothing is staged. Nothing "
                               "was sent.")
    folders, files = plan.get("folders") or {}, plan.get("files") or {}
    out = []
    for app in plan["request"]["apps"]:
        name, version = app["name"], app["version"]
        local = folders.get(name)
        if not local or not os.path.isdir(local):
            raise TransportRefused(f"REFUSED: {name} {version}'s staged folder "
                                   f"{local or '(none)'} is not a folder here. Nothing was "
                                   "sent.")
        got = s.folder_hash(local)
        if got != app["sha256"]:
            raise TransportRefused(f"REFUSED: {name} {version}'s staged folder {local} hashes "
                                   f"{got}, not the plan's {app['sha256']}: it changed after "
                                   "the plan. Nothing was sent.")
        remote = posixpath.join(s.APPS_ROOT, name, version)
        listed = []
        for f in files.get(name) or []:
            rel = f["path"]
            target = f"{remote}/{rel}"
            why = staging_refusal(target, "file")
            if why:
                raise TransportRefused(why)
            path = os.path.join(local, *rel.split("/"))
            with open(path, "rb") as fh:
                data = fh.read()
            blob = s.blob_id(data)
            if blob != f["blob"]:
                raise TransportRefused(f"REFUSED: {rel} in {name} {version} is blob {blob} "
                                       f"here, not the plan's {f['blob']}. Nothing was sent.")
            listed.append((rel, path, target, 0o755 if f["mode"] == "100755" else 0o644))
        if not listed:
            raise TransportRefused(f"REFUSED: the plan lists no file for {name} {version}. "
                                   "Nothing was sent.")
        out.append((app, local, remote, listed))
    return out


def request_bytes(plan: dict) -> bytes:
    """request.json's bytes: the plan's request, which the script's own parser reads back as
    itself (`channel.request` normalised it), refused otherwise."""
    s = _script()
    body = json.dumps(plan["request"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        back = s.parse_request(body)
    except s.Refused as exc:
        raise TransportRefused(f"REFUSED: the request would be refused by the script: {exc}. "
                               "Nothing was sent.") from exc
    if back != plan["request"]:
        raise TransportRefused("REFUSED: the request the script would read is not the plan's "
                               f"(sha256 {s.request_sha256(back)}, not "
                               f"{s.request_sha256(plan['request'])}). Nothing was sent.")
    return body


def _dirs(remote: str, rels) -> list:
    """Every folder a version's files need, parents first: <name>, <name>/<version>, then each
    sub-folder."""
    out = [posixpath.dirname(remote), remote]
    for rel in rels:
        parts = rel.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            d = posixpath.join(remote, *parts[:i])
            if d not in out:
                out.append(d)
    return out


def _parse_line(text) -> dict:
    for line in reversed(str(text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                doc = json.loads(line)
            except ValueError:
                return None
            return doc if isinstance(doc, dict) else None
    return None


def send(conn, plan: dict, *, ip: str) -> dict:
    """Stage *plan*'s files, write its request, send the one command and read the outcome, over
    *conn*, a host kind's plain session to the controller at *ip* that THIS thread holds.

    Returns ``{"ok", "step", "error", "staged", "not_staged", "request_written",
    "command_sent", "printed", "outcome", "deleted": []}``: *ok* is the script's outcome's,
    and only when the outcome file and the printed line agree."""
    from modules import connection, discovery
    from modules.apps import channel
    from modules.nsot import device_ops

    result = {"ok": False, "step": "check", "error": "", "staged": [], "not_staged": [],
              "request_written": False, "command_sent": False, "printed": None,
              "outcome": None, "deleted": []}
    if not device_ops.may_write(ip):
        result["error"] = (f"REFUSED: this operation does not hold the controller at {ip}: the "
                           "deploy channel stages and applies only while the device is held "
                           "(device_ops.hold). Nothing was sent.")
        return result
    try:
        items = _items(plan)
        body = request_bytes(plan)
    except (TransportRefused, OSError) as exc:
        result["error"] = str(exc)
        return result
    why = discovery.held_write_refusal("linux", channel.APPLY_COMMAND)
    if why:
        result["error"] = why
        return result
    pending = [target for _app, _l, _r, listed in items for _rel, _p, target, _m in listed]
    result["not_staged"] = list(pending)
    result["step"] = "stage"
    sftp = None
    try:
        sftp = connection.open_sftp(conn)
        for _app, _local, remote, listed in items:
            for d in _dirs(remote, [rel for rel, _p, _t, _m in listed]):
                sftp.mkdir(d)
            for _rel, path, target, perm in listed:
                with open(path, "rb") as fh:
                    sftp.write(target, fh.read(), perm)
                result["staged"].append(target)
                result["not_staged"].remove(target)
        result["step"] = "request"
        sftp.mkdir(posixpath.dirname(request_path()))
        sftp.write(request_path(), body, 0o644)
        result["request_written"] = True
        result["step"] = "command"
        result["command_sent"] = True
        printed = conn.send_command(channel.APPLY_COMMAND, read_timeout=command_bound_s())
        result["printed"] = _parse_line(printed)
        result["step"] = "outcome"
        raw = sftp.read(outcome_path())
        try:
            outcome = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            outcome = None
        result["outcome"] = outcome
    except Exception as exc:                          # noqa: BLE001 - named, with what landed
        result["error"] = _partway(result, exc)
        log.warning("controller transport to %s stopped at %s: %s", ip, result["step"],
                    result["error"])
        return result
    finally:
        if sftp is not None:
            try:
                sftp.close()
            except Exception:                         # noqa: BLE001 - the session closes it
                pass
    return _judge(result)


def _partway(result: dict, exc: Exception) -> str:
    landed = len(result["staged"])
    left = len(result["not_staged"])
    what = {"stage": "staging", "request": "writing the request", "command": "the apply "
            "command", "outcome": "reading the outcome"}.get(result["step"], result["step"])
    words = (f"stopped at {what}: {type(exc).__name__}: {str(exc)[:300]}. Staged {landed} "
             f"file(s), not staged {left}; the request was "
             f"{'written' if result['request_written'] else 'not written'}; the command was "
             f"{'sent' if result['command_sent'] else 'not sent'}. Nothing was deleted on the "
             "controller")
    if result["step"] == "command":
        words += (f"; whether the script ran is not known: its outcome is in {outcome_path()}, "
                  f"waited for {command_bound_s():.0f} s ({COMMAND_BOUND_FACTOR} times the "
                  "script's restart bound, a placeholder, not measured)")
    return words


def _judge(result: dict) -> dict:
    printed, outcome = result["printed"], result["outcome"]
    result["step"] = "done"
    if outcome is None:
        result["error"] = (f"{outcome_path()} did not read as one JSON object, so the apply's "
                           "outcome is not known")
        return result
    if printed is not None and printed.get("outcome_not_written"):
        result["outcome"] = printed
        result["error"] = (f"the script did not write {outcome_path()} "
                           f"({printed['outcome_not_written']}), so the file is another run's; "
                           "the printed outcome is this run's")
        return result
    if printed != outcome:
        result["error"] = (f"{outcome_path()} (started {outcome.get('started')!r}) is not the "
                           f"line the script printed (started "
                           f"{(printed or {}).get('started')!r}), so which run it is is not known")
        return result
    result["ok"] = outcome.get("ok") is True
    if not result["ok"]:
        result["error"] = str(outcome.get("refused") or outcome.get("error")
                              or "the script's outcome is not ok")
    return result
