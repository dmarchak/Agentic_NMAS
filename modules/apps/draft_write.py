"""Add an app to a network's code repository as a Draft: Mercury's ONE write path to a code
repository (the operator's decision of 2026-11-10: "build a write path that can ONLY create
Drafts in the code repository (preview, confirm, recorded); Publish stays the gate (review +
passing run at that hash). My rule is that everything goes through Mercury, so I don't commit
drafts by hand.").

One home for adding a Draft, whatever the files came from: a folder a person uploads now (SDN ›
Apps, Add an app as a Draft…), or an AI draft from words later (board authoring-from-words).
Both hand it an app's name and ``files``, ``{path inside the app's folder: bytes}``.

**What it can do, and nothing else:** ONE commit on top of the branch's commit, pushed
fast-forward only, that either adds a NEW folder, ``apps/<name>/`` (kind ``app``), or replaces
the files of a folder already there with a NEW VERSION of that app (kind ``version``, C2905:
an app fixed after a lab test reaches the repository through Mercury too). A new version is
allowed only when the folder at the base commit is exactly a version Mercury registered for the
app at that location (its content hash, `lifecycle.content_hash`, equal to a registered one's:
no change made outside Mercury is overwritten), the files differ from it, and the new
manifest's version is above every version registered for the app (`version_key`: three
numbers, major then minor then patch, semver's precedence for versions with no pre-release
part, which `modules.jobs.base.VERSION` admits none of). Nothing outside the folder is in the
commit (checked against the commit itself before it is pushed). Every file is committed as a
regular file (mode 100644), so no link and nothing executable can be made. Every version
already registered stays pinned by its own commit and hash: a new version is a new commit, so
nothing registered or published changes (the registry reads each version's blobs at its
commit).

**The preview** (`preview`): the exact program, written nowhere: the location and branch, the
base commit read now (``git ls-remote``; none when the branch does not exist yet in an empty
repository), the folder, whether it is a new app or a new version and the version it
supersedes, each file's path, size and sha256 and what changes (added, changed, removed or
unchanged, with the base's sha256), the commit message and its author (the verified person),
and the hash over all of it (`plan_hash`) the confirm binds.

**Refused, naming the comparison and both operands:** a location that is not a local path (an
https location needs a push credential Mercury does not hold); a folder already at the base
commit when Mercury has registered no version of that app there, or when its content is no
registered version's; files the same as the base's; a version not above every registered one; a
name that is not an app folder's (`coderepo.APP_FOLDER`); no ``manifest.yml``, or one naming
another app; a path that is absolute, holds ``..`` or a name outside `PART`, or lies outside the
folder; more than `MAX_FILES` files, a file over `MAX_FILE_BYTES` or a folder over
`MAX_TOTAL_BYTES`; a file that is not UTF-8 text; an empty branch setting on a repository with
no default branch yet (the card where the branch is set is named).

**The apply** (`apply`, the confirm's): the program made again inside the copy's lock and
refused when its hash is not the one confirmed, naming what moved (the base commit, the files,
or the rest); the commit built in a throwaway repository under the network's folder in
Mercury's data (``tempfile``; never Mercury's copy, never a working tree of the operator's), by
git's plumbing on a temporary index (read-tree of the base, update-index removing each file a
new version drops and adding each blob, write-tree, commit-tree with the person as author and
committer and the ``Actor:`` and ``Actor-Verified:`` trailers Mercury's commits carry); pushed as ``<commit>:refs/heads/<branch>``
with no force, so git itself refuses anything but a fast-forward; in the copy's git environment
(`coderepo._git`: no hooks, no credential helper or prompt, only the file and https
transports); the throwaway removed whatever happened; the write recorded in the code
repository's record (``drafts``: who, when, the location, branch, base, new commit, folder and
each file's hash, whether a new app or a new version, the version it supersedes and each file
added, changed or removed, a failure with why); then `coderepo.fetch`, so the folder registers as a
Draft in the same operation (its verify), and the code repository's keys announced.

**Rollback:** none, and none is needed: the commit adds a new folder, or a new version's files
in a folder whose earlier version stays at its own commit, and is pushed fast-forward only; a
refusal at any step changes nothing in the repository.

No address is parsed or drawn here: the location is `coderepo.location`'s (its own IPv4 and
IPv6 cases are tests/test_coderepo.py's), and only a local path is written to.
"""

import base64
import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time

log = logging.getLogger(__name__)

#: The steps, in order, as the manual's page names them
#: (docs/manual/how-it-works/draft-write.md).
STEPS = ("check", "preview", "confirm", "build", "push", "record", "register", "announce")

#: The caps, measured from Lab 9's largest app, lab/lab9/apps/fabric_forwarding/ (2026-11-09:
#: 7 files, 66,237 bytes in all, its largest file fabric_forwarding.py 27,455 bytes), with
#: headroom: about 9x its files, 4.8x its largest file and 4x its folder. The folder's cap is
#: also what the confirm carries back as base64 in a form (about 1.42x once URL-encoded):
#: 256 KiB is about 372,000 bytes there, under the 500,000 bytes Flask 3.1 takes by default
#: (MAX_FORM_MEMORY_SIZE; 3.0.2, pinned now, sets none).
MAX_FILES = 64
MAX_FILE_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 256 * 1024
#: A path inside the folder: at most this many characters and folders deep.
MAX_PATH = 200
MAX_DEPTH = 8
#: One name in a path: letters, digits and ``. _ + -``, never ``.`` or ``..`` (and never
#: ``.git``, which git refuses in a tree).
PART = re.compile(r"^[A-Za-z0-9_.+-]{1,100}$")
#: Not measured: no push to a lab code repository has run. FETCH_TIMEOUT's placeholder, as a
#: fetch's was (C2856); a local push of a seven-file folder took well under a second in the
#: tests.
PUSH_TIMEOUT = 120
#: The Drafts kept in the code repository's record, newest last.
DRAFTS_KEPT = 100
#: Who made the commit, beside the person: the `Source:` trailer's slug.
SOURCE = "draft-write"
BASE_REF = "refs/mercury/base"


class Refused(ValueError):
    """Refused before anything was written; the message is the whole reason."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _short(sha: str) -> str:
    return (sha or "")[:12] or "none"


# ── the files ────────────────────────────────────────────────────────────────────────────────

def path_problem(rel: str) -> str:
    """Why *rel* is not a path inside an app's folder, or "". Refusing by shape: anything not
    plainly a relative path of `PART` names is refused."""
    if not isinstance(rel, str) or not rel:
        return "a file carries no path"
    shown = rel[:80].encode("unicode_escape").decode("ascii")
    if any(not (0x20 < ord(ch) < 0x7f) for ch in rel):
        return f"{shown!r} holds a character that is not printable ASCII (or a space)"
    if rel.startswith("/") or "\\" in rel or re.match(r"^[A-Za-z]:", rel):
        return f"{shown!r} is absolute: a path is relative to the app's folder"
    if len(rel) > MAX_PATH:
        return f"{shown!r}… is {len(rel)} characters, over a path's {MAX_PATH}"
    parts = rel.split("/")
    if len(parts) > MAX_DEPTH:
        return f"{shown!r} is {len(parts)} names deep, over {MAX_DEPTH}"
    for part in parts:
        if part in ("", ".", ".."):
            return (f"{shown!r} holds {part or 'an empty name'!r}: a path never leaves the "
                    "app's folder")
        if part.lower() == ".git":
            return f"{shown!r} holds .git, which git never takes in a tree"
        if not PART.match(part):
            return f"{shown!r}: {part!r} is not a file's name (letters, digits and . _ + -)"
    return ""


def too_many(n: int) -> str:
    """Why *n* files are too many for a Draft, or ""."""
    return f"the folder holds {n} files, over a Draft's {MAX_FILES}" if n > MAX_FILES else ""


def check_files(name: str, files: dict) -> list:
    """``[{"rel", "path", "size", "sha256", "data"}]`` sorted by path, or raises `Refused`
    naming the first problem with both operands. *files* maps a path inside the folder to its
    bytes."""
    from modules import coderepo
    from modules.apps.manifest import MANIFEST, MAX_BYTES, ManifestError, parse_manifest

    if not isinstance(name, str) or not coderepo.APP_FOLDER.match(name):
        shown = str(name)[:60].encode("unicode_escape").decode("ascii")
        raise Refused(f"{shown!r} is not an app's name (a-z, 0-9 and _, starting with a "
                      "letter, at most 41): the folder's name is the app's")
    if not isinstance(files, dict) or not files:
        raise Refused(f"the folder {name}/ holds no file")
    if too_many(len(files)):
        raise Refused(too_many(len(files)))
    out, total = [], 0
    for rel in sorted(files):
        why = path_problem(rel)
        if why:
            raise Refused(why)
        data = files[rel]
        if not isinstance(data, (bytes, bytearray)):
            raise Refused(f"{rel} carries no bytes")
        data = bytes(data)
        if len(data) > MAX_FILE_BYTES:
            # "at least": an upload is read only to one byte past the cap.
            raise Refused(f"{rel} is at least {len(data)} bytes, over a file's "
                          f"{MAX_FILE_BYTES}")
        total += len(data)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Refused(f"{rel} is not UTF-8 text (byte {exc.start} is not): a Draft holds "
                          "source and text only") from exc
        if "\0" in text:
            raise Refused(f"{rel} holds a NUL byte, so it is not text: a Draft holds source "
                          "and text only")
        out.append({"rel": rel, "path": f"{coderepo.APPS}/{name}/{rel}", "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(), "data": data})
    if total > MAX_TOTAL_BYTES:
        raise Refused(f"the folder is {total} bytes, over a Draft's {MAX_TOTAL_BYTES}")
    rels = {f["rel"] for f in out}
    for rel in rels:
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        while parent:
            if parent in rels:
                raise Refused(f"{parent} is a file and a folder (it holds {rel})")
            parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
    if MANIFEST not in rels:
        raise Refused(f"the folder {name}/ holds no {MANIFEST} at its top, and an app's "
                      "manifest says what it is")
    raw = next(f for f in out if f["rel"] == MANIFEST)["data"]
    if len(raw) > MAX_BYTES:
        raise Refused(f"{MANIFEST} is {len(raw)} bytes, over a manifest's {MAX_BYTES}")
    try:
        manifest = parse_manifest(raw.decode("utf-8"), f"{name}/{MANIFEST}")
    except ManifestError as exc:
        raise Refused(str(exc)[:600]) from exc
    if manifest.name != name:
        raise Refused(f"{name}/{MANIFEST} names the app {manifest.name!r}, and its folder is "
                      f"{name!r}: they are one name")
    for f in out:
        f["version"] = manifest.version
    return out


def files_fingerprint(checked: list) -> str:
    """sha256 over each file's path and sha256, in order: what the files were."""
    h = hashlib.sha256()
    for f in checked:
        h.update(f"{f['path']}\0{f['sha256']}\0".encode())
    return h.hexdigest()


def files_from_upload(uploads) -> tuple:
    """``(name, files, problem)`` from a folder's upload: each ``(filename, bytes)``, its
    filename the browser's relative path (``<folder>/<path>``, as static/js/nmas_draft.js sends
    it). The top folder's name is the app's; every file must be under that one folder."""
    tops, files = set(), {}
    for filename, data in uploads:
        filename = (filename or "").replace("\\", "/")
        if "/" not in filename:
            return "", {}, (f"{filename[:80]!r} came with no folder path (the browser sent a "
                            "name only): choose the app's folder again")
        top, rel = filename.split("/", 1)
        tops.add(top)
        if rel in files:
            return "", {}, f"{filename[:80]} was sent twice"
        files[rel] = data
    if not tops:
        return "", {}, "no folder was chosen: choose the app's folder"
    if len(tops) > 1:
        return "", {}, ("the files came from more than one folder (" + ", ".join(sorted(tops))
                        + "): choose one app's folder")
    return tops.pop(), files, ""


def carried(checked: list) -> list:
    """Each file as the confirm's form carries it back: its path and its bytes in base64."""
    return [{"rel": f["rel"], "b64": base64.b64encode(f["data"]).decode("ascii")}
            for f in checked]


def files_from_form(rels: list, b64s: list) -> tuple:
    """``(files, problem)``: the confirm's carried files read back."""
    if len(rels) != len(b64s):
        return {}, (f"the form carries {len(rels)} paths and {len(b64s)} files: they come in "
                    "pairs")
    files = {}
    for rel, b64 in zip(rels, b64s):
        try:
            files[rel] = base64.b64decode(b64.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError):
            return {}, f"the form's copy of {rel[:80]} is not base64"
    return files, ""


# ── the repository ───────────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _throwaway(network: str):
    """A throwaway repository under the network's folder in Mercury's data, beside the copy and
    never inside it; removed on the way out, whatever happened."""
    from modules import coderepo

    parent = os.path.dirname(coderepo.copy_dir(network))
    os.makedirs(parent, mode=0o700, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".draft-", dir=parent)
    try:
        made = coderepo._git(tmp, "init", "-q")                 # noqa: SLF001 (one env)
        if made.returncode != 0:
            raise Refused(f"the throwaway repository could not be made: {coderepo._said(made)}")
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(tmp: str, *args, what: str, timeout=None, text=True, extra_env=None, input=None):
    from modules import coderepo

    try:
        proc = coderepo._git(tmp, *args, timeout=timeout or coderepo.FETCH_TIMEOUT, text=text,
                             extra_env=extra_env, input=input)
    except subprocess.TimeoutExpired as exc:
        raise Refused(f"{what} did not finish within {exc.timeout} s (a placeholder bound, "
                      "C2856)") from exc
    except OSError as exc:
        raise Refused(f"git could not be run for {what} ({exc})") from exc
    if proc.returncode != 0:
        raise Refused(f"{what} failed: {coderepo._said(proc)}")
    return proc


def _refs(tmp: str, source: str, *patterns) -> dict:
    """``{ref: sha}`` the repository at *source* holds now, by ``git ls-remote``."""
    proc = _run(tmp, "ls-remote", "--", source, *patterns, what=f"git ls-remote of {source}")
    out = {}
    for line in proc.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref:
            out[ref.strip()] = sha.strip()
    return out


def _default_branch(tmp: str, source: str) -> str:
    proc = _run(tmp, "ls-remote", "--symref", "--", source, "HEAD",
                what=f"git ls-remote of {source}'s default branch")
    for line in proc.stdout.splitlines():
        m = re.match(r"^ref: refs/heads/(\S+)\tHEAD$", line)
        if m:
            return m.group(1)
    return ""


def _base(tmp: str, network: str, loc: dict) -> dict:
    """``{"branch", "branch_from", "base"}`` read now; the base fetched into *tmp* as
    `BASE_REF`. Raises `Refused`."""
    from modules import coderepo

    source, branch, branch_from = loc["source"], loc["branch"], "setting"
    if not branch:
        branch, branch_from = _default_branch(tmp, source), "default"
        if not branch:
            raise Refused(f"{loc['location']} has no default branch yet (it holds no commit), "
                          f"and {network}'s branch setting is empty: name the branch on "
                          f"{coderepo._card(network)}")                  # noqa: SLF001
    base = _refs(tmp, source, f"refs/heads/{branch}").get(f"refs/heads/{branch}", "")
    if not base:
        others = [r for r in _refs(tmp, source) if r.startswith("refs/")]
        if others:
            raise Refused(f"the branch {branch} does not exist in {loc['location']}, which "
                          f"holds {len(others)} other refs: a Draft goes on an existing branch, "
                          "or is the first commit of an empty repository; name the branch on "
                          f"{coderepo._card(network)}")                  # noqa: SLF001
        return {"branch": branch, "branch_from": branch_from, "base": ""}
    _run(tmp, "fetch", "--no-tags", "--no-write-fetch-head", "--no-recurse-submodules", "--",
         source, f"+refs/heads/{branch}:{BASE_REF}", what=f"git fetch of {loc['location']}")
    got = _run(tmp, "rev-parse", "--verify", "--quiet", f"{BASE_REF}^{{commit}}",
               what="reading the fetched base").stdout.strip()
    if got != base:
        raise Refused(f"{branch} moved while it was read (ls-remote said {_short(base)}, the "
                      f"fetch got {_short(got)}): look at it again")
    return {"branch": branch, "branch_from": branch_from, "base": base}


def _folder_at(tmp: str, base: str, name: str) -> str:
    """What ``apps/<name>`` is at *base*: "" (absent), "tree" or "blob"; and ``apps`` itself
    must be a folder when present."""
    from modules import coderepo

    for path in (coderepo.APPS, f"{coderepo.APPS}/{name}"):
        proc = _run(tmp, "ls-tree", base, "--", path, what=f"reading {path} at {_short(base)}")
        line = proc.stdout.strip()
        if not line:
            return ""
        kind = line.split()[1]
        if path == coderepo.APPS and kind != "tree":
            raise Refused(f"{coderepo.APPS} at {_short(base)} is a {kind}, not a folder, so no "
                          "app folder can go under it")
    return kind


def _message(name: str, version: str, checked: list, actor: str, actor_verified: str,
             supersedes: dict = None, counts: dict = None) -> str:
    trailers = f"Source: {SOURCE}\nActor: {actor}\nActor-Verified: {actor_verified}\n"
    if not supersedes:
        return (f"Add {name} {version} as a Draft\n\n"
                f"{len(checked)} files under apps/{name}/, added through Mercury's Add an app as "
                "a Draft (a new folder only; Publish is a person's review and a passing test run "
                "at its hash).\n\n" + trailers)
    c = counts or {}
    return (f"Add {name} {version} as a Draft\n\n"
            f"{len(checked)} files under apps/{name}/, a new version of {name} "
            f"{supersedes['version']} (registered at {supersedes['commit'][:12]}, hash "
            f"{supersedes['content_sha256'][:12]}), added through Mercury's Add an app as a "
            f"Draft: {c.get('added', 0)} added, {c.get('changed', 0)} changed, "
            f"{c.get('removed', 0)} removed. {name} {supersedes['version']} stays at its own "
            "commit; Publish is a person's review and a passing test run at its hash.\n\n"
            + trailers)


def version_key(version: str) -> tuple:
    """A manifest's version as the numbers it is compared by. `modules.jobs.base.VERSION` holds
    every version to three dot-separated numbers with no pre-release or build part, so this is
    semver's precedence for them: major, then minor, then patch, each as a number (1.10.0 is
    above 1.9.0). Raises `Refused` for anything else."""
    from modules.jobs.base import VERSION

    if not isinstance(version, str) or not VERSION.match(version):
        raise Refused(f"{str(version)[:40]!r} is not a version (three dot-separated numbers), "
                      "so it cannot be compared")
    return tuple(int(p) for p in version.split("."))


def changes_fingerprint(changes: list) -> str:
    """sha256 over each change, in order: what the commit does to each path."""
    h = hashlib.sha256()
    for c in changes:
        h.update(f"{c['path']}\0{c['change']}\0{c['sha256']}\0{c['was_sha256']}\0"
                 f"{c['was_mode']}\0".encode())
    return h.hexdigest()


def plan_hash(program: dict) -> str:
    """What the confirm binds: every field of the program, in a fixed order."""
    body = json.dumps({k: program[k] for k in (
        "network", "location", "branch", "base", "folder", "message", "author", "files_sha",
        "kind", "supersedes", "highest", "changes_sha")}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def _base_files(tmp: str, base: str, folder: str) -> dict:
    """``{rel: {"mode", "size", "sha256"}}``: each file git holds under *folder* at *base*, read
    from its blob (the content hash at the base was computed first, so none is a link or a
    submodule)."""
    proc = _run(tmp, "ls-tree", "-r", "-z", "--full-tree", base, "--", folder, text=False,
                what=f"reading {folder} at {_short(base)}")
    out = {}
    for raw in (proc.stdout or b"").split(b"\0"):
        if not raw:
            continue
        head, _, name = raw.partition(b"\t")
        mode, _kind, obj = head.decode("ascii").split()
        path = name.decode("utf-8", "surrogateescape")
        data = _run(tmp, "cat-file", "blob", obj, text=False,
                    what=f"reading {path} at {_short(base)}").stdout
        out[path[len(folder):]] = {"mode": mode, "size": len(data),
                                   "sha256": hashlib.sha256(data).hexdigest()}
    return out


def _changes(checked: list, was: dict, folder: str) -> list:
    """Every path the commit names, sorted: each new file ``added``, ``changed`` (another
    sha256, or a mode other than a regular file's) or ``unchanged``, and each base file the new
    version drops ``removed``; with the base's sha256 and mode beside it."""
    out = []
    new = {f["rel"]: f for f in checked}
    for rel in sorted(set(new) | set(was)):
        f, w = new.get(rel), was.get(rel)
        if f is None:
            change = "removed"
        elif w is None:
            change = "added"
        elif w["sha256"] != f["sha256"] or w["mode"] != "100644":
            change = "changed"
        else:
            change = "unchanged"
        out.append({"rel": rel, "path": f"{folder}{rel}", "change": change,
                    "size": f["size"] if f else None, "sha256": f["sha256"] if f else "",
                    "was_size": w["size"] if w else None, "was_sha256": w["sha256"] if w else "",
                    "was_mode": w["mode"] if w else ""})
    return out


def _new_version(network: str, name: str, checked: list, tmp: str, loc: dict, at: dict,
                 folder: str) -> dict:
    """A folder already at the base: ``{"supersedes", "highest", "changes"}`` when it is a new
    version Mercury may add (C2905), or raises `Refused` naming the comparison."""
    from modules import coderepo
    from modules.jobs.lifecycle import LifecycleError, content_hash

    base, where = at["base"], f"{folder} already exists at {_short(at['base'])} on {at['branch']}"
    card = coderepo._card(network)                            # noqa: SLF001 (its words)
    got = coderepo.read_record(network)
    if got["state"] == "unreadable":
        raise Refused(f"{where}, and which versions of {name} Mercury registered can't be told: "
                      f"{got['error']}")
    rows = [v for v in got["record"].get("versions") or []
            if (v.get("location"), v.get("name")) == (loc["location"], name)]
    if not rows:
        raise Refused(f"{where} (a tree): a Draft is a new app folder only, never a change to one "
                      "already there, unless it is a new version of an app Mercury registered, "
                      f"and Mercury has registered no version of {name} for {loc['location']}: "
                      f"Fetch now on {card} to register it, then add the new version, or "
                      "choose another name")
    try:
        digest = content_hash(tmp, folder.rstrip("/"), base)
    except LifecycleError as exc:
        raise Refused(f"{where}, and its content can't be hashed: {exc}"[:600]) from exc
    match = next((v for v in rows if v.get("content_sha256") == digest), None)
    if match is None:
        held = ", ".join(f"{v.get('version')} {str(v.get('content_sha256'))[:12]}"
                         for v in sorted(rows, key=lambda v: str(v.get("version"))))
        raise Refused(f"{folder} at {_short(base)} hashes {digest[:12]}, and no version of {name} "
                      f"Mercury registered for {loc['location']} has that content ({held}): it "
                      "was changed outside Mercury since, and a new version would overwrite "
                      f"that change; Fetch now on {card} to register what is there, then add "
                      "the new version on top of it")
    changes = _changes(checked, _base_files(tmp, base, folder), folder)
    if all(c["change"] == "unchanged" for c in changes):
        raise Refused(f"the {len(checked)} files are {name} {match.get('version')}'s at "
                      f"{_short(base)}, file for file (the same paths, sha256 and mode): nothing "
                      "changed, so there is no new version to add")
    highest = max((str(v.get("version")) for v in rows), key=version_key)
    new = checked[0]["version"]
    if version_key(new) <= version_key(highest):
        raise Refused(f"{name} {new} is not above {highest}, the highest version of {name} "
                      f"registered for {loc['location']} (versions compare as three numbers, "
                      "major then minor then patch): a new version's manifest names a higher one, "
                      "and every registered version stays at its own commit")
    return {"supersedes": {"version": str(match.get("version")),
                           "commit": str(match.get("commit") or ""), "content_sha256": digest,
                           "published": bool((match.get("publication") or {}).get("reviewer"))
                           and (match.get("publication") or {}).get("content_sha256") == digest},
            "highest": highest, "changes": changes}


def _program(network: str, name: str, files: dict, tmp: str, *, actor: str,
             actor_verified: str) -> dict:
    from modules import coderepo

    if not actor or actor_verified in ("", "none"):
        raise Refused("a Draft is added by a verified person")
    checked = check_files(name, files)
    loc = coderepo.location(network)
    if loc["state"] != "ok":
        raise Refused(loc["error"])
    if loc["kind"] != "path":
        raise Refused(f"{network}'s code repository is {loc['location']}, an https location, "
                      "and Mercury adds a Draft only to a local path: pushing over https needs "
                      "a push credential Mercury does not hold, so it is refused; commit the "
                      "folder there yourself, then Fetch now")
    at = _base(tmp, network, loc)
    folder = f"{coderepo.APPS}/{name}/"
    was = {"supersedes": None, "highest": "",
           "changes": _changes(checked, {}, folder)}
    if at["base"]:
        kind = _folder_at(tmp, at["base"], name)
        if kind == "tree":
            was = _new_version(network, name, checked, tmp, loc, at, folder)
        elif kind:
            raise Refused(f"{folder} already exists at {_short(at['base'])} on {at['branch']} "
                          f"(a {kind}): a Draft is a new app folder only, never a change to "
                          "one already there; choose another name, or change that app in the "
                          "repository")
    version = checked[0]["version"]
    counts = {k: sum(1 for c in was["changes"] if c["change"] == k)
              for k in ("added", "changed", "removed", "unchanged")}
    program = {"ok": True, "error": "", "network": network, "name": name, "version": version,
               "location": loc["location"], "source": loc["source"], "branch": at["branch"],
               "branch_from": at["branch_from"], "base": at["base"], "folder": folder,
               "kind": "version" if was["supersedes"] else "app",
               "supersedes": was["supersedes"], "highest": was["highest"],
               "changes": was["changes"], "counts": counts,
               "changes_sha": changes_fingerprint(was["changes"]),
               "files": [{k: f[k] for k in ("rel", "path", "size", "sha256")} for f in checked],
               "total": sum(f["size"] for f in checked),
               "files_sha": files_fingerprint(checked),
               "message": _message(name, version, checked, actor, actor_verified,
                                   was["supersedes"], counts),
               "author": actor, "author_verified": actor_verified,
               "caps": {"files": MAX_FILES, "file_bytes": MAX_FILE_BYTES,
                        "total_bytes": MAX_TOTAL_BYTES}}
    program["hash"] = plan_hash(program)
    program["_checked"] = checked
    return program


def preview(network: str, name: str, files: dict, *, actor: str, actor_verified: str) -> dict:
    """The exact program (see the module's docstring): ``{"ok", "error", "network", "name",
    "version", "location", "branch", "branch_from", "base", "folder", "kind" ("app" or
    "version"), "supersedes" (None, or the registered version's ``{"version", "commit",
    "content_sha256", "published"}``), "highest", "changes", "counts", "changes_sha", "files",
    "total", "files_sha", "message", "author", "hash", "carried"}``. Writes nothing to the
    repository, the copy or its record; its throwaway is removed."""
    try:
        with _throwaway(network) as tmp:
            program = _program(network, name, files, tmp, actor=actor,
                               actor_verified=actor_verified)
    except Refused as exc:
        return {"ok": False, "error": str(exc), "network": network, "name": name}
    program["carried"] = carried(program.pop("_checked"))
    return program


def control(network: str, state: str = "rest") -> dict:
    """What SDN › Apps draws for the control at rest (*state* ``rest``) or its folder picker
    (``form``): ``{"state", "network", "may", "why", "location", "branch", "caps"}``. Reads
    the setting only; the preview reads the repository."""
    from modules import coderepo

    loc = coderepo.location(network)
    why = ""
    if loc["state"] != "ok":
        why = loc["error"]
    elif loc["kind"] != "path":
        why = (f"{loc['location']} is an https location, and Mercury adds a Draft only to a "
               "local path: a push over https needs a push credential Mercury does not hold")
    return {"state": state if not why else "rest", "network": network, "may": not why,
            "why": why, "location": loc["location"], "branch": loc["branch"],
            "caps": {"files": MAX_FILES, "file_bytes": MAX_FILE_BYTES,
                     "total_bytes": MAX_TOTAL_BYTES}}


# ── the apply ────────────────────────────────────────────────────────────────────────────────

def _author_env(actor: str) -> dict:
    email = actor if "@" in actor else f"{actor}@mercury.invalid"
    return {"GIT_AUTHOR_NAME": actor, "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": actor, "GIT_COMMITTER_EMAIL": email}


def build(tmp: str, program: dict) -> str:
    """The commit, built in *tmp* on a temporary index from the base's tree and the program's
    blobs; checked to add exactly the program's files under its folder (a new app), or to make
    exactly the program's changes there (a new version: each added, changed or removed file and
    nothing else). Returns its sha."""
    checked = program["_checked"]
    index = {"GIT_INDEX_FILE": os.path.join(tmp, "draft-index")}
    if program["base"]:
        _run(tmp, "read-tree", BASE_REF, what="reading the base's tree", extra_env=index)
    else:
        _run(tmp, "read-tree", "--empty", what="starting an empty tree", extra_env=index)
    for c in program["changes"]:
        if c["change"] == "removed":
            _run(tmp, "update-index", "--force-remove", "--", c["path"],
                 what=f"removing {c['path']}", extra_env=index)
    for f in checked:
        blob = _run(tmp, "hash-object", "-w", "--stdin", what=f"storing {f['path']}",
                    text=False, input=f["data"]).stdout.decode("ascii").strip()
        _run(tmp, "update-index", "--add", "--cacheinfo", f"100644,{blob},{f['path']}",
             what=f"adding {f['path']}", extra_env=index)
    tree = _run(tmp, "write-tree", what="writing the tree", extra_env=index).stdout.strip()
    parent = ("-p", program["base"]) if program["base"] else ()
    commit = _run(tmp, "commit-tree", "--no-gpg-sign", tree, *parent, "-F", "-",
                  what="making the commit", input=program["message"],
                  extra_env=dict(index, **_author_env(program["author"]))).stdout.strip()
    if program["kind"] == "version":
        made = changed_paths(tmp, program["base"], commit)
        want = sorted((STATUS[c["change"]], c["path"]) for c in program["changes"]
                      if c["change"] in STATUS)
        if made != want:
            raise Refused(f"the commit built changes {len(made)} paths and the program names "
                          f"{len(want)} ({_first_apart(made, want)}): nothing was pushed")
        return commit
    added = added_paths(tmp, program["base"], commit)
    want = sorted(f["path"] for f in checked)
    if added != want:
        raise Refused(f"the commit built changes {len(added)} paths and the program names "
                      f"{len(want)}: nothing was pushed")
    return commit


def added_paths(repo: str, base: str, commit: str) -> list:
    """Every path *commit* changes against *base* (its whole tree when there is no base), each
    one an addition, or raises `Refused`."""
    args = ("diff-tree", "-r", "--no-commit-id", "--name-status", "--no-renames")
    proc = _run(repo, *args, *((base, commit) if base else ("--root", commit)),
                what="reading what the commit changes")
    out = []
    for line in proc.stdout.splitlines():
        status, _, path = line.partition("\t")
        if status != "A":
            raise Refused(f"the commit changes {path} ({status}), and a Draft only adds: "
                          "nothing was pushed")
        out.append(path)
    return sorted(out)


#: git's name-status letter for each change a new version's commit makes.
STATUS = {"added": "A", "changed": "M", "removed": "D"}


def changed_paths(repo: str, base: str, commit: str) -> list:
    """``[(status, path)]``, sorted: every path *commit* changes against *base*, as git's
    name-status letter, renames read as a removal and an addition."""
    proc = _run(repo, "diff-tree", "-r", "--no-commit-id", "--name-status", "--no-renames",
                base, commit, what="reading what the commit changes")
    out = []
    for line in proc.stdout.splitlines():
        status, _, path = line.partition("\t")
        out.append((status, path))
    return sorted(out)


def _first_apart(made: list, want: list) -> str:
    extra = sorted(set(made) - set(want))
    missing = sorted(set(want) - set(made))
    if extra:
        return f"it makes {extra[0][0]} {extra[0][1]}, which the program does not name"
    if missing:
        return f"the program names {missing[0][0]} {missing[0][1]}, which it does not make"
    return "the same paths, in another order"


def push(tmp: str, program: dict, commit: str) -> None:
    """``<commit>:refs/heads/<branch>`` to the location, with no force: git refuses anything
    but a fast-forward (or a new branch in an empty repository), and its words are kept."""
    from modules import coderepo

    what = f"the push to {program['location']} ({program['branch']}, fast-forward only)"
    try:
        proc = coderepo._git(tmp, "push", "--no-verify", "--porcelain", "--",  # noqa: SLF001
                             program["source"], f"{commit}:refs/heads/{program['branch']}",
                             timeout=PUSH_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise Refused(f"{what} did not finish within {PUSH_TIMEOUT} s (a placeholder bound, "
                      "C2856)") from exc
    except OSError as exc:
        raise Refused(f"git could not be run for {what} ({exc})") from exc
    if proc.returncode != 0:
        said = [ln.split("\t")[-1] for ln in (proc.stdout or "").splitlines()
                if ln.startswith("!")]
        raise Refused(f"{what} was refused by git: "
                      f"{said[0] if said else coderepo._said(proc)}")    # noqa: SLF001


def _moved(program: dict, then_base, then_files, confirmed: str) -> str:
    if then_base is not None and then_base != program["base"]:
        return (f"the base commit moved since the preview (previewed {_short(then_base)}, now "
                f"{_short(program['base'])} on {program['branch']})")
    if then_files is not None and then_files != program["files_sha"]:
        return (f"the files changed since the preview (previewed {_short(then_files)}, now "
                f"{_short(program['files_sha'])})")
    return (f"what Add would commit moved since the preview (confirmed "
            f"{_short(confirmed)}, now {_short(program['hash'])}: the location, the branch, "
            "the version it supersedes or who confirms it)")


def _record(network: str, rec: dict, row: dict) -> None:
    from modules import coderepo

    rec["drafts"] = ((rec.get("drafts") or []) + [row])[-DRAFTS_KEPT:]
    coderepo._write_record(network, rec)                      # noqa: SLF001 (one writer)


def apply(network: str, name: str, files: dict, confirmed: str, *, actor: str,
          actor_verified: str, then_base: str = None, then_files: str = None) -> dict:
    """Add the previewed Draft, bound to *confirmed* (the preview's hash): ``{"outcome"
    ("added", "refused"), "error", "moved", "commit", "base", "branch", "folder", "files",
    "registered", "fetch"}``. *then_base* and *then_files* are the preview's base commit and
    files' fingerprint, so a refusal names which moved."""
    from modules import coderepo

    out = {"outcome": "refused", "error": "", "moved": False, "network": network, "name": name,
           "commit": "", "base": "", "branch": "", "folder": "", "files": [],
           "registered": False, "fetch": None}
    with coderepo._lock(network):                             # noqa: SLF001 (the copy's lock)
        got = coderepo.read_record(network)
        if got["state"] == "unreadable":
            return dict(out, error=(f"{got['error']}: nothing was added, since the write "
                                    "could not be recorded"))
        rec = got["record"]
        row = {"at": _now(), "by": actor, "actor_verified": actor_verified, "name": name,
               "location": "", "branch": "", "base": "", "commit": "", "folder": "",
               "files": [], "ok": False, "error": ""}
        try:
            with _throwaway(network) as tmp:
                program = _program(network, name, files, tmp, actor=actor,
                                   actor_verified=actor_verified)
                row.update(location=program["location"], branch=program["branch"],
                           base=program["base"], folder=program["folder"],
                           files=[{k: f[k] for k in ("path", "size", "sha256")}
                                  for f in program["files"]],
                           kind=program["kind"], version=program["version"],
                           supersedes=program["supersedes"],
                           changes=[{k: c[k] for k in ("path", "change", "sha256",
                                                       "was_sha256")}
                                    for c in program["changes"]
                                    if c["change"] != "unchanged"])
                if program["hash"] != (confirmed or ""):
                    return dict(out, moved=True, error=(
                        _moved(program, then_base, then_files, confirmed)
                        + ": nothing was added; look at it again"))
                commit = build(tmp, program)
                row["built"] = commit
                started = time.monotonic()
                push(tmp, program, commit)
                row.update(commit=commit, ok=True, took_ms=int((time.monotonic() - started)
                                                               * 1000))
        except Refused as exc:
            if not row["location"]:
                # Refused before the program was made: nothing was tried, nothing to record.
                return dict(out, error=str(exc))
            row["error"] = str(exc)[:600]
        _record(network, rec, row)
    if not row["ok"]:
        log.info("draft write: %s's Draft %s on %s refused: %s", actor, name, network,
                 row["error"])
        coderepo._announce(network)                           # noqa: SLF001 (one announcer)
        return dict(out, error=row["error"], base=row["base"], branch=row["branch"],
                    folder=row["folder"])
    log.info("draft write: %s added %s to %s's %s at %s", actor, name, network,
             row["location"], row["commit"][:12])
    out.update(outcome="added", commit=row["commit"], base=row["base"], branch=row["branch"],
               folder=row["folder"], files=row["files"], location=row["location"],
               version=program["version"], at=row["at"], by=actor, kind=program["kind"],
               supersedes=program["supersedes"], counts=program["counts"])
    out.update(_register(network, name, program["version"], row["commit"], actor=actor,
                         actor_verified=actor_verified))
    return out


def _register(network: str, name: str, version: str, commit: str, *, actor: str,
              actor_verified: str) -> dict:
    """The verify: a fetch, then the registry read for the new folder's version."""
    from modules import coderepo

    try:
        fetched = coderepo.fetch(network, actor=actor, actor_verified=actor_verified)
    except coderepo.Refused as exc:
        fetched = {"ok": False, "commit": "", "error": str(exc), "registered": [],
                   "problems": []}
    reg = coderepo.registered(network)
    entry = next((e for a in reg.get("apps") or [] if a["name"] == name
                  for e in a["versions"] if e["version"].version == version), None)
    why = ""
    if not fetched.get("ok"):
        why = f"the fetch after it failed: {fetched.get('error')}"
    elif entry is None:
        mine = [p for p in fetched.get("problems") or [] if f"{coderepo.APPS}/{name}" in p]
        why = ("; ".join(mine) if mine else
               (reg.get("error") or f"{name} {version} is not in the registry after the fetch"))
    return {"registered": entry is not None and not why, "register_error": why,
            "fetch": {k: fetched.get(k) for k in ("ok", "commit", "error")},
            "fetched_past": bool(fetched.get("ok") and fetched.get("commit") != commit)}
