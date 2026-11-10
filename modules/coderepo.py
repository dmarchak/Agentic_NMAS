"""A network's code repository and Mercury's read-only copy of it (the SDN platform design
revision 7, sections 11c.2 and 11c.3; P4's read side, pulled forward by the operator's decision
8 of 2026-11-08): where a network's jobs and apps live, apart from its configuration
repository, and the app versions Mercury has registered from it.

**The setting** (`LOCATION_KEY`, `BRANCH_KEY`; docs/SETTINGS.md): the repository's location,
a local path (``/srv/code/lab9.git``, or ``file:///srv/code/lab9.git``) or an ``https://`` URL
with no user part (a credential in it would sit in the settings file in the clear), and the
branch to fetch (empty: the repository's default branch). Empty by default: a network with
none set has no code, and SDN › Apps says so. Each network's own, never inherited from
Default: another network's code is never loaded into this network's controller. Written only
by `set_location`, from the network's Code repository card (Settings › the network › Network).

**Mercury's copy** (`copy_dir`): ``data/lists/<slug>/code_repo/``, beside the network's
configuration repository and never inside it. It is a repository with no working tree: made by
``git init`` and filled by ``git fetch`` of the one branch into ``refs/mercury/fetched``
(`FETCHED_REF`); nothing is ever checked out, so there is no file in it to read but git's
objects. It is fetched only on a person's request (`fetch`), bounded by `FETCH_TIMEOUT`, with
git's transports limited to ``file`` and ``https`` (``GIT_ALLOW_PROTOCOL``), no credential
prompt or helper, and no hooks. Mercury never commits to its copy. Its one write path to the
repository it copies is `modules/apps/draft_write.py` (the operator's decision of 2026-11-10:
"a write path that can ONLY create Drafts"): a NEW ``apps/<name>/`` folder, or a NEW VERSION of
an app registered here whose folder is exactly a registered version's content (C2905),
previewed as its exact program and confirmed by hash as a verified person, pushed to a
local-path location as one fast-forward commit built in a throwaway repository (never this
copy, never a working tree), recorded here (``drafts``) and fetched, so it registers as a
Draft. It never overwrites a change made outside Mercury, and every registered version stays
at its own commit; Publish stays the gate. Every other change to the repository is the
operator's.

**Registration** (the last step of `fetch`): each ``apps/<name>/`` folder at the fetched commit
is recorded as a Draft version, keyed by the repository's location, the commit and the folder's
content hash (`lifecycle.content_hash`, over the copy at that commit), with its manifest's
version and the commit's author. A folder whose manifest cannot be read, or names another app,
is recorded as a problem naming the file and why, and registers nothing. A version seen again
with the same hash keeps the commit it was first registered at; with another hash it is that
Draft moved (as `lifecycle.observe` has it), and the newer pin replaces it.

**The registry** (`registered`, `deploy_op.Sources.registered`'s shape): the versions recorded
for the location the setting names now, each read again from blobs at its commit (its manifest
parsed, its hash recomputed and compared with the one recorded); never a working tree, never
the configuration repository (T25, tests/test_code_apart_from_state.py). A location changed
since the last fetch lists nothing, naming both. Blobs at a commit never change, so what was
read of one is kept in memory (`_blob_read`).

The record (`RECORD`, beside the copy): every fetch with who, when, from where and what it
found or why it failed (the newest `FETCHES_KEPT`), the registered versions, and each Draft
Mercury added (``drafts``, `draft_write.DRAFTS_KEPT`, written by `draft_write.apply`). Written only
under the copy's lock, replaced atomically; a record that cannot be read refuses a fetch and
lists nothing.

**Not here** (post-lab, the design's Placement table): 11c.5's publication and identifier
checks at registration, the gate's verdict recorded at registration, a scheduled fetch, and
P4's Publish. Until Publish exists every registered version is a Draft, which the controller
app deploy refuses to stage (`channel.stage_published`).
"""

import functools
import json
import logging
import os
import re
import time
import urllib.parse

log = logging.getLogger(__name__)

LOCATION_KEY = "code_repository"
BRANCH_KEY = "code_repository_branch"
#: Who may publish one of the network's versions (C2854; `lifecycle.publish`'s single-user
#: policy): someone other than its author (the default), or its author too, recorded as
#: self-review, for a network one person runs. Mercury resolves no roles yet (9.I), so it
#: cannot measure how many people review a network's code: the network says.
REVIEW_KEY = "code_review"
REVIEW_CHOICES = {
    "another_person": "someone other than its author",
    "self_recorded": "its author too, recorded as self-review (one person runs this network)",
}
DEFAULT_REVIEW = "another_person"
#: The test runs kept per version (each a plain run of the version's own tests, C2854).
TESTS_KEPT = 10
#: Mercury's copy, in the network's folder (`copy_dir`).
COPY = "code_repo"
#: The record of fetches and registered versions, beside the copy.
RECORD = "code_repo_record.json"
FETCHED_REF = "refs/mercury/fetched"
#: The folder an app's code sits in, in the code repository (11c.1).
APPS = "apps"
MANIFEST = "manifest.yml"
#: Not measured: no fetch of a lab code repository has run. A placeholder, as the reads' first
#: bounds were, until the first fetch through the card measures one (C2856). A local fetch of a
#: two-commit repository took well under a second in the tests.
FETCH_TIMEOUT = 120
FETCHES_KEPT = 100
#: git's transports a fetch may use: a local path and HTTPS. ssh needs a key Mercury does not
#: hold for this; ``git://`` and ``http://`` are not authenticated; ``ext::`` runs a command.
ALLOWED_PROTOCOLS = "file:https"
MAX_LOCATION = 500
BRANCH = re.compile(r"^(?!-)(?!.*\.\.)(?!.*//)(?!.*@\{)[A-Za-z0-9._/-]{1,100}$")
APP_FOLDER = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
CARD = "Settings › {network} › Network › Code repository"
#: A fetch's steps, in order, as the manual's page names them
#: (docs/manual/how-it-works/code-repository.md).
STEPS = ("check", "fetch", "register", "record", "announce")
#: Announced after a fetch, so the card on every open page and SDN › Apps read again.
ANNOUNCER = "code-repo"
ANNOUNCE_KEYS = ("code_repo",)


class Refused(ValueError):
    """A setting or a fetch refused, naming the comparison and both operands."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _card(network: str) -> str:
    return CARD.format(network=network)


# ── the setting ──────────────────────────────────────────────────────────────────────────────

def parse_location(text: str) -> dict:
    """``{"ok", "kind" ("path" or "https"), "source" (what git fetches), "error"}`` for a
    location as typed. A path is absolute; an ``https://`` URL has a host (an IPv6 literal
    bracketed), no user part, no query and no fragment."""
    from modules import config

    text = (text or "").strip()
    no = {"ok": False, "kind": "", "source": ""}
    if not text:
        return dict(no, error="no location was given")
    if len(text) > MAX_LOCATION:
        return dict(no, error=f"a location is at most {MAX_LOCATION} characters, and this is "
                              f"{len(text)}")
    if any(not (0x21 <= ord(ch) <= 0x7e) for ch in text):
        return dict(no, error="a location is printable ASCII with no space")
    path = text[len("file://"):] if text.startswith("file://") else text
    if path.startswith("/"):
        real = os.path.realpath(path)
        data = os.path.realpath(config.DATA_DIR)
        if real == data or real.startswith(data + os.sep):
            return dict(no, error=(f"{text} is inside Mercury's own data ({config.DATA_DIR}): "
                                   "a code repository is the operator's, kept apart from "
                                   "every network's state"))
        return {"ok": True, "kind": "path", "source": os.path.normpath(path), "error": ""}
    parts = urllib.parse.urlsplit(text)
    if parts.scheme != "https":
        scheme = parts.scheme or text.split(":", 1)[0]
        return dict(no, error=(f"a code repository is fetched from a local path (starting /, "
                               f"or file://) or an https:// URL, and {scheme!r} is neither "
                               "(ssh needs a key Mercury does not hold for it; git:// and "
                               "http:// are not authenticated)"))
    if "@" in parts.netloc:
        return dict(no, error=("the URL carries a user part (before @), and a credential "
                               "would sit in the settings file in the clear: give the URL "
                               "without it"))
    try:
        host = parts.hostname
        if parts.port is not None and not 0 < parts.port < 65536:
            raise ValueError(f"port {parts.port} is out of range")
    except ValueError as exc:
        return dict(no, error=f"the URL's host or port can't be read ({exc})")
    if not host:
        return dict(no, error="the URL names no host")
    if parts.query or parts.fragment:
        return dict(no, error="the URL carries a query or a fragment, which git does not fetch")
    return {"ok": True, "kind": "https", "source": text, "error": ""}


def branch_problem(branch: str) -> str:
    """Why *branch* is not a branch's name, or "" (empty is the repository's default)."""
    branch = (branch or "").strip()
    if not branch:
        return ""
    if not BRANCH.match(branch) or branch.endswith((".lock", "/", ".")):
        return (f"{branch[:60]!r} is not a branch's name (letters, digits, . _ / -; no "
                "leading -, no .., no //, not ending in / . or .lock)")
    return ""


def location(network: str) -> dict:
    """*network*'s setting: ``{"state" ("ok", "none", "unreadable"), "location", "branch",
    "kind", "source", "error"}``."""
    from modules import list_settings as L

    out = {"location": "", "branch": "", "kind": "", "source": ""}
    try:
        loc, _o = L.resolve(network, LOCATION_KEY)
        branch, _o = L.resolve(network, BRANCH_KEY)
    except L.ListSettingsUnreadable as exc:
        return dict(out, state="unreadable", error=f"{network}'s settings can't be read ({exc})")
    loc = "" if loc is None else str(loc).strip()
    branch = "" if branch is None else str(branch).strip()
    out.update(location=loc, branch=branch)
    if not loc:
        return dict(out, state="none",
                    error=(f"{network} has no code repository set: set its location on "
                           f"{_card(network)}, then Fetch"))
    got = parse_location(loc)
    why = got["error"] or branch_problem(branch)
    if why:
        return dict(out, state="unreadable",
                    error=f"{network}'s code repository setting can't be used: {why}")
    return dict(out, state="ok", kind=got["kind"], source=got["source"], error="")


def _lock(network: str):
    from modules.filestore import PathLock

    return PathLock(lambda: copy_dir(network))


def set_location(network: str, loc: str, branch: str, *, actor: str, actor_verified: str,
                 loaded: str = None) -> dict:
    """Set *network*'s code repository to *loc* and *branch*, as *actor*, a verified person.
    *loaded*: the location and branch as the card drew them (``"<location>\\n<branch>"``);
    with it, a save is refused when the setting moved since, naming both. Recorded in the
    network's settings record with the values before and after. ``{"ok", "before", "after",
    "unchanged"}``; raises `Refused`. An empty *loc* clears it (the branch with it)."""
    from modules import list_settings as L

    if not network:
        raise Refused("a code repository is set for one network, and none was named")
    if not actor or actor_verified in ("", "none"):
        raise Refused("a network's code repository is set by a verified person")
    loc, branch = (loc or "").strip(), (branch or "").strip()
    if loc:
        got = parse_location(loc)
        if not got["ok"]:
            raise Refused(f"not saved: {got['error']}")
        why = branch_problem(branch)
        if why:
            raise Refused(f"not saved: {why}")
    else:
        branch = ""
    with _lock(network):
        held = location(network)
        if held["state"] == "unreadable" and held["error"].startswith(f"{network}'s settings"):
            raise Refused(f"{held['error']}: nothing was saved")
        before = f"{held['location']}\n{held['branch']}"
        if loaded is not None and loaded.replace("\r", "") != before:
            raise Refused(f"{network}'s code repository moved since the card drew it (drawn: "
                          f"{setting_words(loaded)}; now: {setting_words(before)}): nothing "
                          "was saved; look at it again")
        after = f"{loc}\n{branch}"
        if before == after:
            return {"ok": True, "before": before, "after": after, "unchanged": True}
        got = L.write(network, {LOCATION_KEY: loc, BRANCH_KEY: branch}, actor=actor)
        if not got.get("ok"):
            raise Refused(f"not saved: {got.get('error') or 'the setting was not written'}")
    L._record(network, {"kind": "code_repository", "group": LOCATION_KEY,       # noqa: SLF001
                        "written": [LOCATION_KEY, BRANCH_KEY], "before": before,
                        "after": after, "actor": actor, "actor_verified": actor_verified})
    log.info("code repository: %s set %s's to %s", actor, network, setting_words(after))
    return {"ok": True, "before": before, "after": after, "unchanged": False}


def review_policy(network: str) -> dict:
    """*network*'s review policy: ``{"state" ("ok", "unreadable"), "value", "words",
    "error"}``; unset is the default, someone other than the author."""
    from modules import list_settings as L

    try:
        value, _o = L.resolve(network, REVIEW_KEY)
    except L.ListSettingsUnreadable as exc:
        return {"state": "unreadable", "value": "", "words": "",
                "error": f"{network}'s settings can't be read ({exc})"}
    value = str(value or "").strip() or DEFAULT_REVIEW
    if value not in REVIEW_CHOICES:
        return {"state": "unreadable", "value": value, "words": "",
                "error": (f"{network}'s review policy is {value!r}, not one of "
                          f"{', '.join(REVIEW_CHOICES)}")}
    return {"state": "ok", "value": value, "words": REVIEW_CHOICES[value], "error": ""}


def set_review(network: str, value: str, *, actor: str, actor_verified: str,
               loaded: str = None) -> dict:
    """Set who may publish *network*'s versions, as *actor*, a verified person, refused when it
    moved since the card drew it (*loaded*). Recorded in the network's settings record with the
    value before and after. ``{"ok", "before", "after", "unchanged"}``; raises `Refused`."""
    from modules import list_settings as L

    if not actor or actor_verified in ("", "none"):
        raise Refused("a network's review policy is set by a verified person")
    value = (value or "").strip()
    if value not in REVIEW_CHOICES:
        raise Refused(f"not saved: who may publish is one of {', '.join(REVIEW_CHOICES)}, not "
                      f"{value[:40]!r}")
    with _lock(network):
        held = review_policy(network)
        if held["state"] == "unreadable" and held["error"].startswith(f"{network}'s settings"):
            raise Refused(f"{held['error']}: nothing was saved")
        before = held["value"]
        if loaded is not None and loaded.strip() != before:
            raise Refused(f"{network}'s review policy moved since the card drew it (drawn: "
                          f"{loaded.strip()}; now: {before}): nothing was saved; look at it "
                          "again")
        if before == value:
            return {"ok": True, "before": before, "after": value, "unchanged": True}
        got = L.write(network, {REVIEW_KEY: value}, actor=actor)
        if not got.get("ok"):
            raise Refused(f"not saved: {got.get('error') or 'the setting was not written'}")
    L._record(network, {"kind": "code_review", "group": LOCATION_KEY,           # noqa: SLF001
                        "written": [REVIEW_KEY], "before": before, "after": value,
                        "actor": actor, "actor_verified": actor_verified})
    log.info("code repository: %s set %s's review policy to %s", actor, network, value)
    return {"ok": True, "before": before, "after": value, "unchanged": False}


def setting_words(pair: str) -> str:
    """``"<location>\\n<branch>"`` in words."""
    loc, _, branch = str(pair or "").partition("\n")
    if not loc:
        return "none set"
    return f"{loc}, branch {branch}" if branch else f"{loc}, its default branch"


# ── the copy and its record ─────────────────────────────────────────────────────────────────

def copy_dir(network: str) -> str:
    """Mercury's copy of *network*'s code repository (never created by asking)."""
    from modules.nsot import listref

    return os.path.join(listref.resolve(network).data_dir, COPY)


def _record_path(network: str) -> str:
    return os.path.join(os.path.dirname(copy_dir(network)), RECORD)


def _empty() -> dict:
    return {"fetches": [], "versions": []}


def read_record(network: str) -> dict:
    """``{"state" ("ok", "absent", "unreadable"), "record", "error"}``."""
    path = _record_path(network)
    if not os.path.exists(path):
        return {"state": "absent", "record": _empty(), "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        if not isinstance(rec, dict) or not isinstance(rec.get("fetches"), list) \
                or not isinstance(rec.get("versions"), list):
            raise ValueError("not a record of fetches and versions")
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "record": _empty(),
                "error": f"{RECORD} can't be read ({type(exc).__name__}: {exc})"[:300]}
    return {"state": "ok", "record": rec, "error": ""}


def _write_record(network: str, rec: dict) -> None:
    from modules.filestore import write_atomic

    write_atomic(_record_path(network), json.dumps(rec, indent=2, sort_keys=True) + "\n")


def _git_env() -> dict:
    env = dict(os.environ)
    env.update(GIT_ALLOW_PROTOCOL=ALLOWED_PROTOCOLS, GIT_TERMINAL_PROMPT="0",
               GIT_ASKPASS="", SSH_ASKPASS="")
    return env


def _git(dest: str, *args, timeout=None, text=True, extra_env=None, input=None):
    """git in *dest* with the copy's environment (`_git_env`), no hooks and no credential
    helper; *extra_env* adds to it (the draft writer's temporary index and author), *input*
    is its standard input."""
    from modules.nsot.repo import run_git

    kw = {"env": dict(_git_env(), **(extra_env or {})), "text": text}
    if timeout is not None:
        kw["timeout"] = timeout
    if input is not None:
        kw["input"] = input
    return run_git(dest, "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=", *args,
                   **kw)


def _said(proc) -> str:
    err = proc.stderr if isinstance(proc.stderr, str) else \
        (proc.stderr or b"").decode("utf-8", "replace")
    lines = [ln for ln in str(err or "").strip().splitlines() if ln.strip()]
    return (lines[-1] if lines else f"git exited {proc.returncode}")[:240]


def fetched_commit(dest: str) -> str:
    """The commit `FETCHED_REF` names in the copy *dest*, or ""."""
    from modules.nsot.repo import has_repository

    if not has_repository(dest):
        return ""
    proc = _git(dest, "rev-parse", "--verify", "--quiet", f"{FETCHED_REF}^{{commit}}")
    return proc.stdout.strip() if proc.returncode == 0 else ""


# ── reading blobs at a commit ───────────────────────────────────────────────────────────────

def app_folders(dest: str, commit: str) -> list:
    """The names of the folders directly under ``apps/`` at *commit* (git's tree, never a
    working tree); [] when there is no ``apps/``."""
    proc = _git(dest, "ls-tree", "-z", commit, "--", f"{APPS}/", text=False)
    if proc.returncode != 0:
        raise Refused(f"git ls-tree could not read {APPS}/ at {commit[:12]}: {_said(proc)}")
    names = []
    for raw in (proc.stdout or b"").split(b"\0"):
        if not raw:
            continue
        head, _, name = raw.partition(b"\t")
        _mode, kind, _obj = head.decode("ascii").split()
        if kind == "tree":
            names.append(name.decode("utf-8", "surrogateescape")[len(APPS) + 1:])
    return sorted(names)


@functools.lru_cache(maxsize=512)
def _blob_read(dest: str, commit: str, path: str) -> tuple:
    """``(manifest or None, content hash or "", problem or "")`` for the folder *path* at
    *commit*: what is at a commit never changes, so it is read once."""
    from modules.apps.manifest import MAX_BYTES, ManifestError, parse_manifest
    from modules.jobs.lifecycle import LifecycleError, content_hash

    source = f"{path}/{MANIFEST}"
    kind = _git(dest, "cat-file", "-t", f"{commit}:{source}")
    if kind.returncode != 0 or kind.stdout.strip() != "blob":
        return None, "", f"{source} at {commit[:12]}: no manifest (a file named {MANIFEST})"
    size = _git(dest, "cat-file", "-s", f"{commit}:{source}")
    if size.returncode != 0 or not size.stdout.strip().isdigit():
        return None, "", f"{source} at {commit[:12]}: its size can't be read"
    if int(size.stdout) > MAX_BYTES:
        return None, "", (f"{source} at {commit[:12]} is {int(size.stdout)} bytes, over a "
                          f"manifest's {MAX_BYTES}")
    blob = _git(dest, "cat-file", "blob", f"{commit}:{source}", text=False)
    if blob.returncode != 0:
        return None, "", f"{source} at {commit[:12]}: {_said(blob)}"
    try:
        manifest = parse_manifest(blob.stdout.decode("utf-8"), source)
    except UnicodeDecodeError:
        return None, "", f"{source} at {commit[:12]} is not UTF-8 text"
    except ManifestError as exc:
        return None, "", f"{source} at {commit[:12]}: {exc}"[:600]
    try:
        digest = content_hash(dest, path, commit)
    except LifecycleError as exc:
        return None, "", f"{path} at {commit[:12]}: {exc}"[:600]
    return manifest, digest, ""


def _author(dest: str, commit: str, path: str) -> str:
    proc = _git(dest, "log", "-1", "--format=%ae", commit, "--", path)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def scan(dest: str, commit: str) -> dict:
    """``{"found": [{"name", "version", "path", "commit", "content_sha256", "author"}],
    "problems": [words]}``: each ``apps/<name>/`` folder at *commit*, read from blobs."""
    found, problems = [], []
    for name in app_folders(dest, commit):
        path = f"{APPS}/{name}"
        if not APP_FOLDER.match(name):
            problems.append(f"{path} at {commit[:12]}: {name!r} is not an app's name "
                            "(a-z, 0-9 and _, starting with a letter)")
            continue
        manifest, digest, why = _blob_read(dest, commit, path)
        if why:
            problems.append(why)
            continue
        if manifest.name != name:
            problems.append(f"{path}/{MANIFEST} at {commit[:12]} names the app "
                            f"{manifest.name!r}, and its folder is {name!r}")
            continue
        found.append({"name": name, "version": manifest.version, "path": path,
                      "commit": commit, "content_sha256": digest,
                      "author": _author(dest, commit, path)})
    return {"found": found, "problems": problems}


def merge(versions: list, found: list, loc: str, *, at: str, by: str) -> tuple:
    """``(versions after, [words for each version registered or moved])``: *found* (one
    location's scan) into the recorded *versions*, keyed by location, name and version."""
    out = [dict(v) for v in versions]
    said = []
    for f in found:
        key = (loc, f["name"], f["version"])
        old = next((v for v in out if (v.get("location"), v.get("name"),
                                       v.get("version")) == key), None)
        if old and old.get("content_sha256") == f["content_sha256"]:
            continue
        row = dict(f, location=loc, registered_at=at, registered_by=by)
        if old:
            out[out.index(old)] = row
            said.append(f"{f['name']} {f['version']} moved: its folder hashes "
                        f"{f['content_sha256'][:12]} at {f['commit'][:12]}, and was "
                        f"{old.get('content_sha256', '')[:12]} at "
                        f"{str(old.get('commit', ''))[:12]} (a Draft takes the new pin)")
        else:
            out.append(row)
            said.append(f"{f['name']} {f['version']} registered at {f['commit'][:12]}, "
                        f"hash {f['content_sha256'][:12]}")
    return out, said


# ── the fetch (a person's request) ──────────────────────────────────────────────────────────

def fetch(network: str, *, actor: str, actor_verified: str) -> dict:
    """Fetch *network*'s code repository into Mercury's copy and register what is at the
    fetched commit, as *actor*, a verified person. ``{"ok", "commit", "before", "changed",
    "registered": [words], "problems": [words], "error"}``. A failed fetch is recorded too,
    with why; the copy keeps the commit it had."""
    from modules.nsot.repo import has_repository

    if not actor or actor_verified in ("", "none"):
        raise Refused("a code repository is fetched for a verified person")
    loc = location(network)
    if loc["state"] != "ok":
        raise Refused(loc["error"])
    dest = copy_dir(network)
    with _lock(network):
        got = read_record(network)
        if got["state"] == "unreadable":
            raise Refused(f"{got['error']}: nothing was fetched, since writing would replace "
                          "every fetch and version in it")
        rec = got["record"]
        os.makedirs(dest, mode=0o700, exist_ok=True)
        before = fetched_commit(dest)
        row = {"at": _now(), "by": actor, "actor_verified": actor_verified,
               "location": loc["location"], "branch": loc["branch"], "before": before,
               "commit": "", "ok": False, "error": "", "registered": [], "problems": []}
        started = time.monotonic()
        result = _fetch_into(dest, loc, has_repository)
        # How long git's fetch took, kept with the fetch: FETCH_TIMEOUT's measurement (C2856).
        row["took_ms"] = int((time.monotonic() - started) * 1000)
        if result["error"]:
            row["error"] = result["error"]
        else:
            row["commit"] = result["commit"]
            try:
                found = scan(dest, result["commit"])
            except Refused as exc:
                row["error"] = str(exc)
            else:
                rec["versions"], row["registered"] = merge(
                    rec["versions"], found["found"], loc["location"], at=row["at"], by=actor)
                row["problems"], row["ok"] = found["problems"], True
        rec["fetches"] = (rec["fetches"] + [row])[-FETCHES_KEPT:]
        _write_record(network, rec)
    log.info("code repository: %s fetched %s's %s: %s", actor, network, loc["location"],
             row["commit"][:12] or row["error"])
    _announce(network)
    return {"ok": row["ok"], "commit": row["commit"], "before": before,
            "changed": bool(row["ok"] and row["commit"] != before),
            "registered": row["registered"], "problems": row["problems"],
            "error": row["error"]}


def _announce(network: str) -> None:
    """Every open page hears that the network's copy and registry may have moved."""
    from modules import invalidation

    try:
        invalidation.announce(ANNOUNCE_KEYS, by=ANNOUNCER)
    except Exception as exc:                          # noqa: BLE001 (counted in the log)
        log.warning("code repository: %s's fetch was not announced: %s", network, exc)


def _fetch_into(dest: str, loc: dict, has_repository) -> dict:
    """``{"commit", "error"}``: the branch fetched into `FETCHED_REF` of the copy."""
    import subprocess

    if not has_repository(dest):
        made = _git(dest, "init", "-q")
        if made.returncode != 0:
            return {"commit": "", "error": f"the copy could not be made: {_said(made)}"}
    want = f"refs/heads/{loc['branch']}" if loc["branch"] else "HEAD"
    try:
        proc = _git(dest, "fetch", "--no-tags", "--no-write-fetch-head",
                    "--no-recurse-submodules", "--", loc["source"],
                    f"+{want}:{FETCHED_REF}", timeout=FETCH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"commit": "", "error": (f"git fetch of {loc['location']} did not finish within "
                                        f"{FETCH_TIMEOUT} s (a placeholder bound, C2856)")}
    except OSError as exc:
        return {"commit": "", "error": f"git could not be run ({exc})"}
    if proc.returncode != 0:
        return {"commit": "", "error": f"git fetch of {loc['location']} ({want}) failed: "
                                       f"{_said(proc)}"}
    commit = fetched_commit(dest)
    if not commit:
        return {"commit": "", "error": f"the fetch named no commit for {want}"}
    return {"commit": commit, "error": ""}


# ── the registry (reads only) ───────────────────────────────────────────────────────────────

def _last(rec: dict, ok_only: bool) -> dict:
    rows = [f for f in rec.get("fetches") or [] if f.get("ok") or not ok_only]
    return rows[-1] if rows else {}


def registered(network: str) -> dict:
    """`deploy_op.Sources.registered` for *network*: ``{"state" ("ok", "none", "unfetched",
    "unreadable"), "apps": [{"name", "versions": [entry]}], "repo": {"path", "branch",
    "commit", "fetched_at"}, "problems", "error"}``, each entry ``{"version":
    lifecycle.Version, "manifest", "repo", "path", "rev", "commit", "reviewed_at",
    "registered_at", "location"}``. Reads only."""
    from modules.jobs.lifecycle import DRAFT, PUBLISHED, Version

    loc = location(network)
    out = {"apps": [], "repo": {}, "problems": []}
    if loc["state"] != "ok":
        return dict(out, state=loc["state"], error=loc["error"])
    got = read_record(network)
    if got["state"] == "unreadable":
        return dict(out, state="unreadable", error=got["error"])
    rec = got["record"]
    last = _last(rec, ok_only=True)
    repo = {"path": loc["location"], "branch": loc["branch"], "commit": "", "fetched_at": ""}
    if not last:
        failed = _last(rec, ok_only=False)
        tail = f" (the last try, {failed['at']}, failed: {failed['error']})" if failed else ""
        return dict(out, repo=repo, state="unfetched",
                    error=(f"{network}'s code repository {loc['location']} has not been "
                           f"fetched yet{tail}: Fetch on {_card(network)}"))
    then = f"{last.get('location', '')}\n{last.get('branch') or ''}"
    named = f"{loc['location']}\n{loc['branch']}"
    if then != named:
        return dict(out, repo=repo, state="unreadable",
                    error=(f"Mercury's copy was fetched from {setting_words(then)}, and the "
                           f"setting names {setting_words(named)} now: Fetch again on "
                           f"{_card(network)}"))
    dest = copy_dir(network)
    now = fetched_commit(dest)
    if now != last.get("commit"):
        return dict(out, repo=repo, state="unreadable",
                    error=(f"Mercury's copy names commit {now[:12] or 'none'}, and its record "
                           f"says the last fetch was {str(last.get('commit'))[:12]}: Fetch "
                           f"again on {_card(network)}"))
    repo.update(commit=last["commit"], fetched_at=last.get("at", ""))
    problems = list(last.get("problems") or [])
    apps: dict = {}
    for row in rec.get("versions") or []:
        if row.get("location") != loc["location"]:
            continue
        name, path, commit = row.get("name", ""), row.get("path", ""), row.get("commit", "")
        manifest, digest, why = _blob_read(dest, commit, path)
        if why:
            problems.append(f"{name} {row.get('version')}: {why}")
            continue
        if digest != row.get("content_sha256"):
            problems.append(f"{name} {row.get('version')}: registered with hash "
                            f"{str(row.get('content_sha256'))[:12]}, and its blobs at "
                            f"{commit[:12]} hash to {digest[:12]}")
            continue
        # Published (C2854) only at the hash the review was of: a publication of another pin is
        # not this version's, so it stands as a Draft.
        pub = row.get("publication") or {}
        published = pub.get("content_sha256") == digest and bool(pub.get("reviewer"))
        try:
            version = Version(kind="app", name=name, version=row.get("version", ""),
                              author=row.get("author") or "unknown",
                              state=PUBLISHED if published else DRAFT, content_sha256=digest,
                              reviewer=pub.get("reviewer", "") if published else "",
                              self_review=bool(pub.get("self_review")) if published else False)
        except ValueError as exc:
            problems.append(f"{name} {row.get('version')}: {exc}"[:300])
            continue
        apps.setdefault(name, []).append({
            "version": version, "manifest": manifest, "repo": dest, "path": path,
            "rev": commit, "commit": commit,
            "reviewed_at": pub.get("at", "") if published else "",
            "publication": dict(pub) if published else None,
            "test": last_test(row, digest),
            "registered_at": row.get("registered_at", ""), "location": loc["location"]})
    return dict(out, state="ok", error="", repo=repo, problems=problems,
                apps=[{"name": n, "versions": apps[n]} for n in sorted(apps)])


def _version_row(rec: dict, loc: str, name: str, version: str):
    return next((v for v in rec.get("versions") or [] if (v.get("location"), v.get("name"),
                 v.get("version")) == (loc, name, version)), None)


def last_test(row: dict, sha256: str):
    """The newest recorded test run of *row*'s version at *sha256*, or None."""
    runs = [t for t in (row or {}).get("tests") or [] if t.get("content_sha256") == sha256]
    return runs[-1] if runs else None


def version_record(network: str, name: str, version: str) -> dict:
    """``{"state" ("ok", "absent", "unreadable"), "row", "commit", "path", "digest", "error"}``:
    the registered version's record row and its folder's hash read again from the copy's blobs
    at its commit. Reads only."""
    loc = location(network)
    if loc["state"] != "ok":
        return {"state": "unreadable", "row": None, "error": loc["error"]}
    got = read_record(network)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "row": None, "error": got["error"]}
    row = _version_row(got["record"], loc["location"], name, version)
    if row is None:
        return {"state": "absent", "row": None,
                "error": f"{name} {version} is not registered for {loc['location']}"}
    _m, digest, why = _blob_read(copy_dir(network), row.get("commit", ""), row.get("path", ""))
    if why:
        return {"state": "unreadable", "row": row, "error": f"{name} {version}: {why}"}
    return {"state": "ok", "row": row, "commit": row.get("commit", ""),
            "path": row.get("path", ""), "digest": digest, "error": ""}


def record_test(network: str, name: str, version: str, run: dict, *, actor: str,
                actor_verified: str) -> dict:
    """Keep *run* (`modules/apps/test_run.run`'s answer) with the version's record, as *actor*,
    its id the entry's; the newest `TESTS_KEPT`. Raises `Refused` when the version is not
    registered or its run was over another hash than its registered one."""
    import uuid

    with _lock(network):
        got = read_record(network)
        if got["state"] == "unreadable":
            raise Refused(f"{got['error']}: the test run was not recorded")
        rec = got["record"]
        loc = location(network)
        row = _version_row(rec, loc["location"], name, version)
        if row is None:
            raise Refused(f"{name} {version} is not registered: the test run was not recorded")
        if run.get("content_sha256") != row.get("content_sha256"):
            raise Refused(f"the run was over {str(run.get('content_sha256'))[:12]}, and {name} "
                          f"{version} is registered at {str(row.get('content_sha256'))[:12]}: "
                          "not recorded")
        entry = {"id": uuid.uuid4().hex[:12], "at": _now(), "by": actor,
                 "actor_verified": actor_verified,
                 **{k: run.get(k) for k in ("ok", "passed", "failed", "errors", "python",
                                            "content_sha256", "output", "error")}}
        row["tests"] = ((row.get("tests") or []) + [entry])[-TESTS_KEPT:]
        _write_record(network, rec)
    _announce(network)
    return entry


def publish(network: str, name: str, version: str, *, content_sha256: str, test_id: str,
            reviewer: str, reviewer_verified: str, reason: str) -> dict:
    """Publish *name* *version* (P4's Publish, minimal: C2854), as *reviewer*, a verified person,
    for *reason*. Refused, naming both operands: a version not registered, a folder whose hash
    read again from its blobs is not *content_sha256* (the one previewed), a test run *test_id*
    that is not this version's at that hash or did not pass, and `lifecycle.publish`'s own
    problems (only a Draft; the reviewer someone other than the author unless the network's
    review policy is `self_recorded`). The publication is kept with the version's record; a
    fetch that moves the folder's hash replaces the row, so the new pin is a Draft again."""
    from modules.jobs.lifecycle import DRAFT, LifecycleError, Version
    from modules.jobs.lifecycle import publish as lifecycle_publish

    if not reviewer or reviewer_verified in ("", "none"):
        raise Refused("a version is published by a verified person")
    if not (reason or "").strip():
        raise Refused("a publication says why: type the review's reason")
    policy = review_policy(network)
    if policy["state"] != "ok":
        raise Refused(f"{policy['error']}: nothing was published")
    with _lock(network):
        got = read_record(network)
        if got["state"] == "unreadable":
            raise Refused(f"{got['error']}: nothing was published")
        rec = got["record"]
        loc = location(network)
        row = _version_row(rec, loc["location"], name, version)
        if row is None:
            raise Refused(f"{name} {version} is not registered for {loc['location']}")
        _m, digest, why = _blob_read(copy_dir(network), row.get("commit", ""),
                                     row.get("path", ""))
        if why:
            raise Refused(f"{name} {version}: {why}")
        if digest != content_sha256:
            raise Refused(f"{name} {version}'s folder hashes {digest[:12]} now, and the review "
                          f"was of {str(content_sha256)[:12]}: nothing was published")
        test = next((t for t in row.get("tests") or [] if t.get("id") == test_id), None)
        if test is None or test.get("content_sha256") != digest:
            raise Refused(f"no test run {test_id or '(none)'} of {name} {version} at "
                          f"{digest[:12]} is recorded: run its tests first")
        if test.get("ok") is not True:
            raise Refused(f"its test run {test_id} did not pass ({test.get('failed')} failed, "
                          f"{test.get('errors')} errors): nothing was published")
        draft = Version(kind="app", name=name, version=version,
                        author=row.get("author") or "unknown", state=DRAFT,
                        content_sha256=digest)
        if (row.get("publication") or {}).get("content_sha256") == digest:
            raise Refused(f"{name} {version} is already Published at {digest[:12]}")
        try:
            done = lifecycle_publish(draft, digest, reviewer=reviewer, harness_passed=True,
                                     single_user=policy["value"] == "self_recorded")
        except LifecycleError as exc:
            raise Refused("; ".join(exc.problems) if getattr(exc, "problems", None)
                          else str(exc)) from exc
        row["publication"] = {"content_sha256": digest, "reviewer": reviewer,
                              "reviewer_verified": reviewer_verified,
                              "self_review": done.self_review, "at": _now(),
                              "reason": reason.strip()[:500], "test_id": test_id,
                              "policy": policy["value"]}
        _write_record(network, rec)
    log.info("code repository: %s published %s %s on %s at %s", reviewer, name, version,
             network, digest[:12])
    _announce(network)
    return dict(row["publication"], name=name, version=version)


def _drawn(row: dict) -> dict:
    """A fetch as the card draws it (its whole record stays in the copy's record)."""
    return {k: row[k] for k in ("at", "by", "ok", "commit", "branch", "error") if k in row}


def card(network: str) -> dict:
    """What the network's Code repository card draws: the setting, the last fetch (and the
    last good one when the last failed), and what is registered."""
    loc = location(network)
    got = read_record(network)
    rec = got["record"]
    reg = registered(network) if loc["state"] == "ok" else {"state": loc["state"], "apps": [],
                                                            "problems": [], "error": ""}
    return {"network": network, "location": loc["location"], "branch": loc["branch"],
            "state": loc["state"], "error": loc["error"] if loc["state"] == "unreadable" else "",
            "loaded": f"{loc['location']}\n{loc['branch']}",
            "record_state": got["state"], "record_error": got["error"],
            "last": _drawn(_last(rec, ok_only=False)), "last_ok": _drawn(_last(rec, True)),
            "registered_state": reg["state"], "registered_error": reg.get("error", ""),
            "apps": len(reg["apps"]), "versions": sum(len(a["versions"]) for a in reg["apps"]),
            "problems": reg.get("problems") or [], "timeout": FETCH_TIMEOUT,
            "review": review_policy(network), "review_choices": REVIEW_CHOICES}
