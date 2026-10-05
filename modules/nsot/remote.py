"""nsot/remote.py — per-list git remote: adopt, verify, preview.

See ``docs/NSOT_PHASE2B_REMOTE_DURABILITY.md``. This module is the adopt-first
increment: it records an existing, hand-made remote setup as this list's
remote, verifies it, and previews what a first push would publish. **It does
not push.**

Three things shape it:

**Adoption, not creation.** The Default list's SSH alias, deploy key and
private repository already exist, made by hand. A wizard that assumed
greenfield would duplicate or overwrite a working setup. Adoption records
"this list uses alias X", verifies it, and leaves ``~/.ssh/config`` alone —
NMAS never edits that file, and must not relocate what a person put there.

**Per list.** The global ``nsot_git_*`` settings cannot express one repository
per network. ``data/lists/{slug}/remote.json`` follows the established
``source.json`` pattern. Two lists pushing to each other's repositories is the
failure this exists to prevent, and it is silent.

**Verification refuses, and says why.** Every check reports the failure and
the fix. Privacy in particular is established by a CONJUNCTION — the deploy
key can read the repository and an anonymous client cannot — because ``404``
alone cannot distinguish "private" from "does not exist".
"""

import json
import logging
import os
import re
import subprocess

log = logging.getLogger(__name__)

REMOTE_FILE = "remote.json"

#: Secret-bearing config shapes, and whether the value is recoverable from it.
#: The patterns are deliberately the same shapes `redact._POSITIONAL` masks —
#: a value this project considers worth hiding in a log is a value worth
#: counting before it is published.
SECRET_SHAPES = [
    ("snmp_community", re.compile(r"^\s*snmp-server community (\S+)", re.M), True),
    ("user_password", re.compile(
        r"^\s*username \S+(?: privilege \d+)? password (?:\d+ )?(\S+)", re.M), True),
    ("enable_password", re.compile(r"^\s*enable password (?:\d+ )?(\S+)", re.M), True),
    ("user_secret_hash", re.compile(
        r"^\s*username \S+(?: privilege \d+)? secret (\d+) (\S+)", re.M), False),
    ("enable_secret_hash", re.compile(r"^\s*enable secret (\d+) (\S+)", re.M), False),
]


# ---------------------------------------------------------------------------
# remote.json
# ---------------------------------------------------------------------------

def remote_path(list_name: str) -> str:
    from modules.config import get_list_data_dir

    return os.path.join(get_list_data_dir(list_name), REMOTE_FILE)


def load_remote(list_name: str):
    """This list's remote config, or ``None``. Absent means no remote."""
    path = remote_path(list_name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:                   # noqa: BLE001
        log.error("remote: unreadable %s: %s", path, exc)
        return None


def save_remote(list_name: str, config: dict) -> dict:
    """Write this list's remote config, replaced whole (a temp file per write, 0600; R18:
    one shared ``.tmp`` let two writers truncate each other's). Never touches
    ``~/.ssh/config``."""
    from modules.filestore import write_atomic

    path = remote_path(list_name)
    write_atomic(path, json.dumps(config, indent=2, sort_keys=True) + "\n")
    return {"ok": True, "path": path}


def unreadable_why(list_name: str) -> str:
    """Why this list's remote.json, which EXISTS, could not be read, or "" (R18: an
    unreadable file read as "no remote", and the push hook answered "nothing pushed" with ok).
    Absent and unreadable are different states."""
    path = remote_path(list_name)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as fh:
            json.load(fh)
        return ""
    except Exception as exc:                   # noqa: BLE001
        return f"{os.path.basename(path)} could not be read ({type(exc).__name__})"


def update_remote(list_name: str, change) -> tuple:
    """THE read-modify-write of this list's remote.json (CONCURRENCY_AUDIT R18): under its lock
    across processes, the record as stored NOW (absent: no remote; unreadable: refused, the
    file kept and a `.corrupt-` copy beside it) passed to *change*, then replaced whole.

    *change(config)* edits the record in place, or returns a string to refuse without saving.
    Returns ``(config, "")`` or ``(None, why)``. Before this, each commit's hook thread read,
    edited and saved its own copy: a failure recording `pending_tags` beside a success popping
    them lost a tag the C223 rule says is kept."""
    from modules.filestore import PathLock, StoreUnreadable, read_json_for_write

    with PathLock(lambda: remote_path(list_name)):
        path = remote_path(list_name)
        try:
            config = read_json_for_write(path) if os.path.exists(path) else \
                load_remote(list_name)
        except StoreUnreadable as exc:
            return None, str(exc)
        if not config:
            return None, f"'{list_name}' has no remote configured"
        refused = change(config)
        if isinstance(refused, str):
            return None, refused
        save_remote(list_name, config)
    return config, ""


def publish_lock(repo_dir: str):
    """One publisher per repository at a time, across processes (R18): each commit's hook
    thread pushed on its own, so two pushes could land out of order and the second be recorded
    as a divergence. The lock file is BESIDE the repository, never inside it (C345)."""
    from modules.filestore import PathLock

    return PathLock(os.path.abspath(repo_dir).rstrip(os.sep) + ".publish")


def adopt(list_name: str, *, ssh_alias: str, owner: str, repo: str,
          branch: str = "main", key_path: str = "", actor: str = "operator") -> dict:
    """Record an EXISTING setup as this list's remote.

    ``managed_by_nmas`` is false for an adopted setup: NMAS verifies and
    pushes, and never rewrites the key or the SSH stanza. ``auto_push`` starts
    false always — it is turned on after a successful push, never before.
    """
    from datetime import datetime, timezone

    from modules.filestore import PathLock

    with PathLock(lambda: remote_path(list_name)):
        return _adopt_locked(list_name, ssh_alias=ssh_alias, owner=owner, repo=repo,
                             branch=branch, key_path=key_path, actor=actor,
                             now=datetime.now(timezone.utc))


def _adopt_locked(list_name, *, ssh_alias, owner, repo, branch, key_path, actor, now) -> dict:
    """`adopt` under the record's lock (R18): checked and created in one hold, so two
    adoptions cannot both find no remote; an unreadable record is refused, never replaced."""
    unreadable = unreadable_why(list_name)
    if unreadable:
        return {"ok": False, "error": f"{unreadable}: refused, so it is not replaced. "
                                      f"Repair or remove {remote_path(list_name)}."}
    existing = load_remote(list_name)
    if existing:
        return {"ok": False, "error": (
            f"'{list_name}' already has a remote "
            f"({existing.get('owner')}/{existing.get('repo')}). Remove "
            f"{remote_path(list_name)} first if you mean to replace it.")}

    config = {
        "provider": "github",
        "ssh_alias": ssh_alias,
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "key_path": key_path,
        "auto_push": False,
        "managed_by_nmas": False,
        "adopted_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "adopted_by": actor,
        "verified_at": "",
        "acknowledged_secrets": None,
    }
    save_remote(list_name, config)
    log.info("remote: '%s' adopted %s:%s/%s (alias, key and ssh config left "
             "untouched)", list_name, ssh_alias, owner, repo)
    return {"ok": True, "remote": config}


def remote_url(config: dict) -> str:
    return f"{config['ssh_alias']}:{config['owner']}/{config['repo']}"


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _run(args, timeout=45, **kw):
    # An identity is supplied for the write probe's throwaway repository:
    # `commit-tree` refuses without one, and the probe must not depend on the
    # calling user having a global git config. It never reaches a real repo.
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0",
               GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15",
               GIT_AUTHOR_NAME="nmas", GIT_AUTHOR_EMAIL="nmas@localhost",
               GIT_COMMITTER_NAME="nmas", GIT_COMMITTER_EMAIL="nmas@localhost")
    return subprocess.run(args, capture_output=True, text=True,
                          timeout=timeout, env=env, **kw)


def check_key_scope(config: dict) -> dict:
    """``ssh -T <alias>`` — and read what the reply says about the key.

    ``Hi owner/repo!`` is a deploy key scoped to ONE repository.
    ``Hi username!`` is an account-wide key, which would give this list push
    access to every repository the account owns. That is refused: the blast
    radius of a leaked key should be one repository, and the reply form tells
    us which we have for free.
    """
    proc = _run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                 "-T", config["ssh_alias"]])
    reply = (proc.stdout + proc.stderr).strip()
    greeting = next((l.strip() for l in reply.splitlines()
                     if l.strip().startswith("Hi ")), "")
    if not greeting:
        return {"ok": False, "name": "key_authenticates", "detail": reply[:200],
                "fix": f"ssh -T {config['ssh_alias']} does not authenticate. "
                       f"Check the key at {config.get('key_path') or '(unset)'} "
                       f"and the Host stanza in ~/.ssh/config."}
    scope = greeting[3:].split("!")[0].strip()
    if "/" not in scope:
        return {"ok": False, "name": "key_is_repo_scoped", "detail": greeting,
                "fix": f"'{scope}' is an ACCOUNT-WIDE key: it can push to every "
                       f"repository this account owns. Use a deploy key scoped "
                       f"to {config['owner']}/{config['repo']}."}
    want = f"{config['owner']}/{config['repo']}"
    if scope != want:
        return {"ok": False, "name": "key_matches_repo", "detail": greeting,
                "fix": f"the key is scoped to {scope}, not {want}."}
    return {"ok": True, "name": "key_is_repo_scoped", "detail": greeting}


def check_read(config: dict) -> dict:
    proc = _run(["git", "ls-remote", remote_url(config)])
    if proc.returncode != 0:
        return {"ok": False, "name": "read_works",
                "detail": (proc.stderr or "")[:200],
                "fix": "the key authenticates but cannot read the repository."}
    refs = [l for l in proc.stdout.splitlines() if l.strip()]
    return {"ok": True, "name": "read_works", "detail": f"{len(refs)} ref(s)",
            "refs": len(refs)}


def check_write_probe(config: dict) -> dict:
    """Prove the key can WRITE, publishing nothing.

    A read-only deploy key passes the read checks and fails only on a write,
    so the property has to be exercised. The obvious probe —
    ``push HEAD:refs/nmas/writetest`` — would publish every commit and blob
    under HEAD, which is precisely what the acknowledgement gate exists to
    stop, before the operator had acknowledged anything. Deleting the ref
    afterwards does not remove the objects.

    So the probe is an ORPHAN commit with the EMPTY TREE, built in a throwaway
    repository: one commit object, one tree object, zero blobs, nothing
    reachable from ``config_repo``.
    """
    import shutil
    import tempfile

    work = tempfile.mkdtemp(prefix="nmas-writeprobe-")
    ref = "refs/nmas/writeprobe"
    try:
        if _run(["git", "-C", work, "init", "-q"]).returncode != 0:
            return {"ok": False, "name": "write_works",
                    "detail": "could not create the probe repository"}
        tree = _run(["git", "-C", work, "hash-object", "-t", "tree",
                     os.devnull]).stdout.strip()
        commit = _run(["git", "-C", work, "commit-tree", tree,
                       "-m", "nmas write probe"]).stdout.strip()
        if not commit:
            detail = _run(["git", "-C", work, "commit-tree", tree,
                           "-m", "nmas write probe"]).stderr.strip()
            return {"ok": False, "name": "write_works",
                    "detail": f"could not build the probe commit: {detail}"[:200],
                    "fix": "the probe repository could not create a commit; "
                           "this is a local fault, not a permission one."}
        push = _run(["git", "-C", work, "push", remote_url(config),
                     f"{commit}:{ref}"])
        if push.returncode != 0:
            return {"ok": False, "name": "write_works",
                    "detail": (push.stderr or "")[:200],
                    "fix": "the deploy key is read-only. Enable 'Allow write "
                           "access' on it in the repository's settings."}
        # Remove the ref. The two objects stay unreachable and are collected
        # by GitHub's own gc; nothing readable was ever published.
        cleanup = _run(["git", "-C", work, "push", remote_url(config), f":{ref}"])
        return {"ok": True, "name": "write_works",
                "detail": f"empty-tree probe accepted; ref removed "
                          f"({'clean' if cleanup.returncode == 0 else 'ref left behind'})",
                "ref_removed": cleanup.returncode == 0}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def check_private(config: dict) -> dict:
    """PRIVATE, established by conjunction — never by one status code.

    The deploy key can read it (checked separately) AND an anonymous client
    cannot. ``404`` alone is ambiguous between "private" and "does not exist",
    and the two endpoints answer differently on a real private repository
    (API 404, git endpoint 401), so a single-code check cannot express this.

    If the anonymous probe cannot run at all, this REFUSES. Fail-closed, the
    same rule as ``netbox_allow_writes``: not being able to check is not the
    same as having checked.
    """
    import urllib.error
    import urllib.request

    owner, repo = config["owner"], config["repo"]
    endpoints = [
        ("api", f"https://api.github.com/repos/{owner}/{repo}"),
        ("git", f"https://github.com/{owner}/{repo}.git/info/refs"
                f"?service=git-upload-pack"),
    ]
    seen = {}
    for label, url in endpoints:
        request = urllib.request.Request(
            url, headers={"User-Agent": "nmas-automation/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                seen[label] = response.status
        except urllib.error.HTTPError as exc:
            seen[label] = exc.code
        except Exception as exc:               # noqa: BLE001
            return {"ok": False, "name": "repository_is_private",
                    "detail": f"{label}: {type(exc).__name__}",
                    "fix": "could not verify the repository is private "
                           "(no outbound HTTPS?). Refusing: an unverified "
                           "privacy claim is not a privacy claim."}
    public = [label for label, code in seen.items() if code == 200]
    if public:
        return {"ok": False, "name": "repository_is_private", "detail": str(seen),
                "fix": f"{owner}/{repo} answers anonymously on {public} — it is "
                       f"PUBLIC. Make it private before pushing."}
    return {"ok": True, "name": "repository_is_private",
            "detail": f"anonymous: {seen} (and the deploy key can read it)"}


def check_right_repository(config: dict, list_name: str, repo_dir: str) -> dict:
    """Not our own source repo, not another list's, and not unrelated."""
    from modules.config import get_list_data_dir

    target = f"{config['owner']}/{config['repo']}".lower()

    own = _run(["git", "-C", os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "remote", "get-url",
        "origin"]).stdout.strip()
    if own and target in own.lower():
        return {"ok": False, "name": "not_the_application_repo", "detail": own,
                "fix": "that is this application's own source repository."}

    # Excluded by IDENTITY, not by name.
    #
    # `get_current_list_name()` returns the DISPLAY name ("Default") while the
    # directory is the slug ("default"), so `slug == list_name` was false for
    # the very list being verified — and every adopted list failed its own
    # uniqueness check, reporting itself as the other list that already owns
    # the repository. No list could ever pass verification.
    #
    # `ListRef.matches()` now owns that comparison. The local `_identity()`
    # helper this replaces was correct, but it was the third private fix for
    # one shape; a type that carries both names makes the mistake
    # unrepresentable instead of repaired per site.
    from modules.nsot.listref import resolve as _resolve

    mine = _resolve(list_name)
    lists_dir = os.path.dirname(mine.data_dir)
    for slug in sorted(os.listdir(lists_dir)):
        if mine.matches(slug):
            continue
        other = load_remote(slug)
        if other and f"{other.get('owner')}/{other.get('repo')}".lower() == target:
            return {"ok": False, "name": "not_another_lists_repo", "detail": slug,
                    "fix": f"list '{slug}' already pushes to {target}. Two "
                           f"networks must not share a repository."}

    ls = _run(["git", "ls-remote", remote_url(config)])
    remote_refs = [l for l in ls.stdout.splitlines() if l.strip()]
    if not remote_refs:
        return {"ok": True, "name": "repository_is_empty_or_related",
                "detail": "empty"}
    return _relatedness(repo_dir, remote_refs)


def remote_heads(remote_refs: list) -> list:
    """Branch-tip SHAs from ``git ls-remote`` output.

    Only ``refs/heads/*``, because those are always commits. A tag line gives
    the *tag object's* SHA and the peeled ``refs/tags/x^{}`` line gives the
    commit -- mixing the three kinds into one set was never the problem here,
    but it is why a count of "refs" is not a count of anything comparable.
    """
    heads = []
    for line in remote_refs:
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("refs/heads/"):
            heads.append(parts[0])
    return heads


def _have_commit(repo_dir: str, sha: str) -> bool:
    return _run(["git", "-C", repo_dir, "cat-file", "-e",
                 f"{sha}^{{commit}}"]).returncode == 0


def _is_ancestor(repo_dir: str, older: str, newer: str) -> bool:
    """True when *older* is an ancestor of *newer*, or the same commit.

    ``merge-base --is-ancestor`` answers both: a commit is its own ancestor.
    """
    return _run(["git", "-C", repo_dir, "merge-base", "--is-ancestor",
                 older, newer]).returncode == 0


def _relatedness(repo_dir: str, remote_refs: list) -> dict:
    """Does the remote hold this list's history?

    THE DEFECT THIS REPLACES. The previous test intersected the local ROOT
    commit with the remote's ref TIPS:

        local_root = rev-list --max-parents=0 HEAD
        if set(local_root) & {sha for each remote ref}: related

    A root commit is a ref tip only in a repository with exactly one commit,
    or one whose first commit happens to be tagged. So it passed on an empty
    remote, passed by luck on a one-commit remote, and **refused every remote
    with real history** -- including one holding nothing but our own 61
    commits, pushed from this very repository an hour earlier. It was only
    ever exercised against an empty remote, so "it passed" and "it works"
    stayed the same sentence right up to the moment the first push made them
    different.

    The question is ancestry, so ancestry is what it asks: take every SHA the
    remote advertises that this clone actually HAS, and see whether any of
    them sits on this list's history -- an ancestor of HEAD, or HEAD an
    ancestor of it.

    **Every advertised SHA, not just branch heads.** A remote that is ahead of
    us -- somebody pushed from another machine -- has a head we have never
    seen, and testing heads alone would report our own repository as
    unrelated for the sake of one unfetched commit. Its tags are still ours,
    and one shared commit is all relatedness requires.

    **Shared nothing means unrelated.** If not one advertised SHA exists in
    this clone, there is no history in common to find, and the original
    refusal stands unchanged.
    """
    advertised = []
    for line in remote_refs:
        parts = line.split()
        if parts:
            advertised.append(parts[0])

    # Peeled `refs/tags/x^{}` entries are the reason tags are usable here at
    # all: the unpeeled line carries the TAG OBJECT's sha, which is not a
    # commit and can never be an ancestor of anything.
    known = [sha for sha in dict.fromkeys(advertised)
             if _have_commit(repo_dir, sha)]

    related = [sha for sha in known
               if _is_ancestor(repo_dir, sha, "HEAD")
               or _is_ancestor(repo_dir, "HEAD", sha)]

    if related:
        heads = remote_heads(remote_refs)
        ahead = [sha for sha in heads if not _have_commit(repo_dir, sha)]
        detail = f"{len(related)} shared commit(s) on this list's history"
        if ahead:
            detail += f"; {len(ahead)} remote head(s) not yet fetched"
        return {"ok": True, "name": "repository_is_empty_or_related",
                "detail": detail}

    # Nothing shared. Keep the root-commit test as a second opinion: it is
    # sound when it fires, and costs one command.
    return _shared_root(repo_dir, remote_refs)


def _shared_root(repo_dir: str, remote_refs: list) -> dict:
    """The original test, kept as a fallback: a shared root commit.

    Sound when it fires -- two repositories sharing a root commit are the
    same history -- and useless when it does not, which is what made it the
    wrong primary test.
    """
    local_root = _run(["git", "-C", repo_dir, "rev-list", "--max-parents=0",
                       "HEAD"]).stdout.split()
    remote_shas = {l.split()[0] for l in remote_refs}
    if set(local_root) & remote_shas:
        return {"ok": True, "name": "repository_is_empty_or_related",
                "detail": "shares a root commit"}
    return {"ok": False, "name": "repository_is_empty_or_related",
            "detail": f"{len(remote_refs)} ref(s), none related",
            "fix": "the repository is not empty and shares no history with "
                   "this list. Pushing would interleave two histories."}


def verify(list_name: str, repo_dir: str = "", actor: str = "",
           with_write_probe: bool = False) -> dict:
    """The pre-push checks. The write probe is OPT-IN, and gated above here.

    Four of the five only read: an SSH greeting, a ``ls-remote``, two
    anonymous HTTPS requests. Those can run unauthenticated, because they are
    how somebody decides whether to publish at all, and gating them would mean
    authorising the thing being evaluated.

    The write probe is not one of them. It **pushes to GitHub** — an orphan
    commit with an empty tree, publishing no content, but a write to an
    external system all the same. "Reads may be ungated" does not extend to
    it, and bundling it into a read-only-sounding endpoint was the mistake:
    the argument was about reads and the endpoint was not.

    ``verified_at`` is set only when all five pass, so it keeps meaning "this
    remote is ready to be pushed to". The read-only pass records
    ``read_verified_at`` instead, which is a weaker claim and is named like
    one.
    """
    from datetime import datetime, timezone

    from modules.config import get_list_data_dir

    config = load_remote(list_name)
    if not config:
        return {"ok": False, "error": f"'{list_name}' has no remote configured"}
    repo_dir = repo_dir or os.path.join(get_list_data_dir(list_name),
                                        "config_repo")

    checks = [check_key_scope(config)]
    if checks[0]["ok"]:
        checks.append(check_read(config))
        checks.append(check_private(config))
        checks.append(check_right_repository(config, list_name, repo_dir))
        if with_write_probe:
            checks.append(check_write_probe(config))

    ok = all(c["ok"] for c in checks)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def change(stored):
        if ok:
            stored["read_verified_at"] = stamp
            if with_write_probe:
                stored["verified_at"] = stamp
        # EVERY verify's outcome, passed or not (the operator, 2026-10-05): the History card
        # draws it from here, so any redraw keeps the answer a person asked for.
        stored["last_verify"] = {
            "at": stamp, "by": actor, "ok": ok, "write_probe": bool(with_write_probe),
            "failed": [{"name": c.get("name", ""), "detail": str(c.get("detail") or "")[:200]}
                       for c in checks if not c["ok"]]}
    # Onto the record as stored NOW (R18): the checks take seconds, and a push recorded
    # meanwhile is kept.
    config = update_remote(list_name, change)[0] or config
    return {"ok": ok, "checks": checks, "remote": remote_url(config),
            "write_probe_run": bool(with_write_probe),
            "ready_to_push": bool(ok and with_write_probe),
            "note": ("" if with_write_probe else
                     "the write probe was NOT run — it pushes to the remote, "
                     "so it is a separate, gated step")}


# ---------------------------------------------------------------------------
# First-push preview
# ---------------------------------------------------------------------------

def _blobs_of_golden(repo_dir: str):
    """Every version of every ``golden/*.cfg`` in HISTORY, deduplicated.

    A push publishes every commit, so scanning HEAD would answer a question
    nobody asked. Deduplicating by blob sha keeps the work proportional to
    distinct CONTENT rather than to commits × files.
    """
    proc = _run(["git", "-C", repo_dir, "rev-list", "--objects", "--all"],
                timeout=120)
    seen = {}
    for line in proc.stdout.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[1].startswith("golden/") \
                and parts[1].endswith(".cfg"):
            seen[parts[0]] = parts[1]
    return seen


def describe_line(line: str) -> str:
    """A config line, safe to print. **Unconditionally.**

    Every path that shows device configuration in a report goes through this.
    The rule "never print a secret value" cannot be conditioned on knowing
    which values are secret, or on one of them being dead: a reporter cannot
    know what it is holding, and a caller that decides per-line will
    eventually decide wrong.

    Learned twice. A report meant to show SNMP access MODES printed a
    community, because its own ad-hoc regex knew about `snmp-server community`
    and not about `snmp-server host … version 2c <community>`. The redactor
    already knew that shape; the reporter had reimplemented a worse one.
    """
    from modules import redact

    return redact.redact_positional(line or "")


def snmp_access_modes(repo_dir: str, ref: str, hosts: list) -> dict:
    """Community ACCESS MODES per device. Counts and modes, never values.

    RO grants read. RW grants configuration write over SNMP — a write path
    into the device that no confirm hash, deploy gate or approval queue
    covers. Publishing an RW community is publishing config-write access, so
    it is reported separately from "how many communities are there".
    """
    modes_re = re.compile(
        r"^\s*snmp-server community \S+\s+(RO|RW)\b\s*(\S*)", re.M | re.I)
    bare_re = re.compile(r"^\s*snmp-server community \S+\s*$", re.M)

    per_device, totals = {}, {"RO": 0, "RW": 0, "unqualified": 0}
    for host in hosts:
        text = _run(["git", "-C", repo_dir, "show", f"{ref}:golden/{host}.cfg"],
                    timeout=60).stdout
        found = modes_re.findall(text)
        bare = len(bare_re.findall(text))
        modes = [m.upper() for m, _acl in found]
        for mode in modes:
            totals[mode] = totals.get(mode, 0) + 1
        totals["unqualified"] += bare
        per_device[host] = {
            "communities": len(found) + bare,
            "modes": modes,
            "acl_restricted": sum(1 for _m, acl in found if acl),
            "unqualified": bare,
        }
    return {"per_device": per_device, "totals": totals,
            "all_read_only": totals["RW"] == 0 and totals["unqualified"] == 0}


def ack_salt(list_name: str) -> str:
    """This list's salt for secret fingerprints, created once and kept in
    `remote.json` (0600, never in the repository). Salted so a fingerprint
    shown on a screen cannot be checked against a guessed community offline."""
    import secrets as _secrets

    config = load_remote(list_name)
    if not config:
        return ""
    if not config.get("ack_salt"):
        # Created under the record's lock (R18): two first readers each minting one would
        # leave the fingerprints of whichever lost unmatchable.
        config, _why = update_remote(
            list_name, lambda c: c.setdefault("ack_salt", _secrets.token_hex(16)) and None)
        if config is None:
            return ""
    return config["ack_salt"]


def _salt_beside(repo_dir: str, list_name: str) -> str:
    """The salt of the list whose `remote.json` sits beside *repo_dir*
    (`<list>/config_repo`), created there once; '' when the list has no
    remote. Found from the repository's own path, never by resolving the
    list's name, which creates its directory (C51)."""
    if not repo_dir:
        return ""
    path = os.path.join(os.path.dirname(os.path.abspath(repo_dir)), REMOTE_FILE)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh).get("ack_salt") or ""
    except (OSError, ValueError):
        return ""
    return got or (ack_salt(list_name) if list_name else "")


def secret_fingerprint(kind: str, value: str, salt: str) -> str:
    """A secret's name on a screen: HMAC-SHA256 of kind and value under the
    list's salt, 12 hex. Never the value, never reversible."""
    import hashlib
    import hmac

    return hmac.new(bytes.fromhex(salt), f"{kind}\0{value}".encode(),
                    hashlib.sha256).hexdigest()[:12]


def scan_history_secrets(repo_dir: str, list_name: str) -> dict:
    """What a push would publish, per device, per kind, with LIVENESS.

    The plan's gate predates the credential rotations, when every plaintext
    password in this history was live. It is not any more, and the difference
    is the whole point of asking somebody to acknowledge publication: a value
    the fleet has moved away from is evidence, and a value still in use is an
    exposure.

    LIVE means the value is still serving as a secret — it appears in a
    SECRET POSITION in the current HEAD golden, or in this list's credential
    store. DEAD means it appears only in older commits.

    Position matters, not presence. Comparing against the raw text of HEAD
    reported every router's old plaintext password as live, because that
    password was `admin` and the string still appears at HEAD as the username.

    The limit of that rule is worth stating where the code is, not only in a
    report: DEAD means "not in any device's current configuration in this
    list". It does NOT mean the value is unusable somewhere else — a password
    reused on another system is invisible here.
    """
    blobs = _blobs_of_golden(repo_dir)

    # Current secret VALUES, for the liveness test.
    #
    # Extracted through the same patterns, from the same positions — NOT by
    # asking whether the string appears anywhere in HEAD. The first version
    # did exactly that and reported all five routers' old plaintext passwords
    # as LIVE: the value was `admin`, which still appears at HEAD as the
    # USERNAME in `username admin privilege 15 secret 9 …`. A short secret
    # collides with ordinary config text, so "is this string present" is not
    # the question. "Is this string still serving as a secret" is.
    current = set()
    at_head = {}                         # value -> devices whose HEAD golden holds it
    proc = _run(["git", "-C", repo_dir, "ls-tree", "-r", "--name-only",
                 "HEAD", "golden"], timeout=60)
    for name in proc.stdout.splitlines():
        if not name.strip():
            continue
        text = _run(["git", "-C", repo_dir, "show", f"HEAD:{name}"],
                    timeout=60).stdout
        for _kind, pattern, _recoverable in SECRET_SHAPES:
            for match in pattern.finditer(text):
                current.add(match.groups()[-1])
                at_head.setdefault(match.groups()[-1], set()).add(
                    os.path.basename(name)[:-4])
    try:
        from modules.redact import known_secret_values
        current |= {v for v in known_secret_values() if v}
    except Exception:                          # noqa: BLE001
        pass

    findings = {}
    by_value = {}                        # (kind, value) -> recoverable, devices
    for sha, path in blobs.items():
        device = os.path.basename(path)[:-4]
        text = _run(["git", "-C", repo_dir, "cat-file", "-p", sha],
                    timeout=60).stdout
        for kind, pattern, recoverable in SECRET_SHAPES:
            for match in pattern.finditer(text):
                value = match.groups()[-1]
                if not value or len(value) < 2:
                    continue
                live = value in current
                entry = findings.setdefault((device, kind), {
                    "device": device, "kind": kind, "recoverable": recoverable,
                    "values": set(), "live": set(), "dead": set()})
                entry["values"].add(value)
                (entry["live"] if live else entry["dead"]).add(value)
                if live:
                    v = by_value.setdefault((kind, value), {
                        "recoverable": recoverable, "devices": set()})
                    v["devices"].add(device)

    rows = []
    for entry in findings.values():
        rows.append({
            "device": entry["device"], "kind": entry["kind"],
            "recoverable": entry["recoverable"],
            "distinct": len(entry["values"]),
            "live": len(entry["live"]), "dead": len(entry["dead"]),
        })
    rows.sort(key=lambda r: (r["kind"], r["device"]))

    gated = sorted({r["kind"] for r in rows
                    if r["recoverable"] and r["live"]})
    # Each LIVE value by its salted fingerprint, never the value, with where
    # it appears (the devices whose history holds it, and whose HEAD golden
    # holds it now). The acknowledgement is about these: another copy of an
    # acknowledged value publishes nothing new (the operator, 2026-10-01).
    salt = _salt_beside(repo_dir, list_name)
    live_values = []
    if salt:
        for (kind, value), v in by_value.items():
            live_values.append({
                "kind": kind, "fingerprint": secret_fingerprint(kind, value, salt),
                "recoverable": v["recoverable"], "devices": sorted(v["devices"]),
                "at_head": sorted(at_head.get(value, ()))})
        live_values.sort(key=lambda x: (x["kind"], x["fingerprint"]))
    return {"rows": rows, "blobs_scanned": len(blobs), "gated_kinds": gated,
            "live_values": live_values}


def first_push_preview(list_name: str, repo_dir: str = "") -> dict:
    """Counts and liveness. **Never values.**"""
    from modules.config import get_list_data_dir

    config = load_remote(list_name)
    if not config:
        return {"ok": False, "error": f"'{list_name}' has no remote configured"}
    repo_dir = repo_dir or os.path.join(get_list_data_dir(list_name),
                                        "config_repo")

    def count(*args):
        out = _run(["git", "-C", repo_dir, *args], timeout=120).stdout
        return len([l for l in out.splitlines() if l.strip()])

    tags = [t for t in _run(["git", "-C", repo_dir, "tag", "-l"],
                            timeout=60).stdout.splitlines() if t.strip()]
    by_prefix = {}
    for tag in tags:
        by_prefix[tag.split("/", 1)[0]] = by_prefix.get(tag.split("/", 1)[0], 0) + 1

    secrets = scan_history_secrets(repo_dir, list_name)
    hosts = sorted({os.path.basename(p)[:-4]
                    for p in _blobs_of_golden(repo_dir).values()})
    return {
        "snmp": snmp_access_modes(repo_dir, "HEAD", hosts),
        "ok": True,
        "remote": remote_url(config),
        "owner_repo": f"{config['owner']}/{config['repo']}",
        "branch": config.get("branch", "main"),
        "commits": count("rev-list", "--count", "HEAD") and int(
            _run(["git", "-C", repo_dir, "rev-list", "--count", "HEAD"],
                 timeout=60).stdout.strip() or 0),
        "commits_touching_golden": int(
            _run(["git", "-C", repo_dir, "rev-list", "--count", "HEAD", "--",
                  "golden"], timeout=60).stdout.strip() or 0),
        "tags": len(tags),
        "tags_by_prefix": by_prefix,
        "notes": count("for-each-ref", "refs/notes"),
        "secrets": secrets,
        "already_acknowledged": config.get("acknowledged_secrets"),
    }


# ---------------------------------------------------------------------------
# Acknowledgement, push, and the auto-push hold
# ---------------------------------------------------------------------------

def gated_summary(scan: dict) -> dict:
    """The shape an acknowledgement is ABOUT: gated kinds and their counts.

    Only live, recoverable material. A dead value is reported and never gated,
    and a hash is reported and never gated — so an acknowledgement is a
    statement about what is actually being exposed, not about everything the
    scan noticed.
    """
    counts = {}
    for row in scan["rows"]:
        if row["recoverable"] and row["live"]:
            counts[row["kind"]] = counts.get(row["kind"], 0) + row["live"]
    values = {v["fingerprint"]: {"kind": v["kind"], "devices": v["devices"],
                                 "at_head": v.get("at_head", [])}
              for v in scan.get("live_values") or [] if v["recoverable"]}
    return {"kinds": sorted(counts), "counts": counts, "values": values}


def acknowledge(list_name: str, *, actor: str, actor_kind: str,
                repo_dir: str = "", shown=None) -> dict:
    """Record that a person accepted publishing the gated material.

    Bound to **what was acknowledged** — the kinds, their counts, and the
    commit it was measured against. An acknowledgement that recorded only
    "yes" would carry forward across changes to the thing being acknowledged,
    which is the same failure mode as a template approval that survives a
    template edit.
    """
    from datetime import datetime, timezone

    from modules.config import get_list_data_dir

    config = load_remote(list_name)
    if not config:
        return {"ok": False, "error": f"'{list_name}' has no remote configured"}
    repo_dir = repo_dir or os.path.join(get_list_data_dir(list_name),
                                        "config_repo")

    scan = scan_history_secrets(repo_dir, list_name)
    gated = gated_summary(scan)
    # Only the values the person was SHOWN (CONCURRENCY_AUDIT R41): the gate's unit is the
    # value, and a secret committed between the card being drawn and the click was recorded
    # as acknowledged without anyone seeing it. *shown* is the card's fingerprints; None for
    # a caller with no card.
    if shown is not None:
        now, seen = set(gated["values"]), {str(s) for s in shown}
        if now != seen:
            new, gone = sorted(now - seen), sorted(seen - now)
            return {"ok": False, "error": (
                "Not acknowledged: the history's secrets changed after the card was drawn"
                + (f"; not shown: {', '.join(new)}" if new else "")
                + (f"; shown and no longer there: {', '.join(gone)}" if gone else "")
                + ". Open the acknowledgement again to read what it now covers.")}
    head = _run(["git", "-C", repo_dir, "rev-parse", "HEAD"],
                timeout=60).stdout.strip()

    # Written to the record as stored NOW, under its lock (R18): the scan may have created the
    # list's salt, and saving the copy read before it would drop the salt, changing every
    # fingerprint and making the next push hold on secrets already accepted.
    acknowledged = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by": actor, "by_kind": actor_kind,
        "kinds": gated["kinds"], "counts": gated["counts"],
        # Each acknowledged secret by fingerprint, with where it appeared:
        # what the gate compares, and what the card shows (never a value).
        "values": gated["values"],
        "commit": head,
    }
    config, why = update_remote(
        list_name, lambda c: c.__setitem__("acknowledged_secrets", acknowledged))
    if config is None:
        return {"ok": False, "error": why}
    log.info("remote: '%s' publication acknowledged by %s (%s) — kinds=%s "
             "counts=%s at %s", list_name, actor, actor_kind, gated["kinds"],
             gated["counts"], head[:12])
    return {"ok": True, "acknowledged": config["acknowledged_secrets"]}


def acknowledgement_covers(list_name: str, repo_dir: str = "") -> dict:
    """Does the recorded acknowledgement still cover what would be published?

    Re-scanned, not trusted. A NEW gated kind, or a secret VALUE not among
    those acknowledged (by fingerprint), means a person agreed to publish
    less than is now on offer, so it does not carry.

    **Another copy of an acknowledged value is not new** (the operator,
    2026-10-01): r6 received the community eight devices already carried,
    and the old rule (any rise in a kind's COUNT of occurrences) held four
    pushes for four hours. Under that rule every onboarding and profile
    apply froze pushes until someone re-acknowledged, which trains people to
    acknowledge without reading. A copy is reported (``copies``), never held.

    An acknowledgement recorded before fingerprints (no ``values``) keeps the
    count rule until it is made once more, and says so.

    A count that FELL, or a kind that disappeared, still carries: less is
    being published than was agreed to.
    """
    from modules.config import get_list_data_dir

    config = load_remote(list_name)
    if not config:
        return {"ok": False, "reason": "no remote configured"}
    ack = config.get("acknowledged_secrets")
    if not ack:
        return {"ok": False, "reason": "nothing has been acknowledged yet",
                "needs": "acknowledgement"}

    repo_dir = repo_dir or os.path.join(get_list_data_dir(list_name),
                                        "config_repo")
    now = gated_summary(scan_history_secrets(repo_dir, list_name))
    was = {"kinds": ack.get("kinds") or [], "counts": ack.get("counts") or {},
           "values": ack.get("values")}

    new_kinds = sorted(set(now["kinds"]) - set(was["kinds"]))
    risen = sorted(k for k, n in now["counts"].items()
                   if n > was["counts"].get(k, 0))
    if was["values"] is not None:
        new_values = {fp: v for fp, v in now["values"].items() if fp not in was["values"]}
        if new_kinds or new_values:
            named = "; ".join(f"{v['kind']} {fp} (in {', '.join(v['devices']) or '?'})"
                              for fp, v in sorted(new_values.items()))
            return {"ok": False, "needs": "re-acknowledgement",
                    "new_kinds": new_kinds, "new_values": new_values, "risen": risen,
                    "was": was, "now": now,
                    "reason": "a secret not acknowledged would be published: " + "; ".join(
                        x for x in ((f"new kinds {', '.join(new_kinds)}" if new_kinds else ""),
                                    named) if x)}
        return {"ok": True, "was": was, "now": now,
                # More occurrences of acknowledged values: said, never held.
                "copies": risen}
    if new_kinds or risen:
        return {"ok": False, "needs": "re-acknowledgement",
                "new_kinds": new_kinds, "risen": risen,
                "was": was, "now": now,
                "reason": (
                    "what would be published has grown since it was "
                    f"acknowledged: {'new kinds ' + ', '.join(new_kinds) if new_kinds else ''}"
                    f"{' and ' if new_kinds and risen else ''}"
                    f"{'more ' + ', '.join(risen) if risen else ''} (this acknowledgement "
                    "predates fingerprints, so it counts occurrences: acknowledge once "
                    "more to record each secret's fingerprint, and another copy of an "
                    "acknowledged secret will no longer hold a push)")}
    return {"ok": True, "was": was, "now": now}


def record_push(list_name: str, *, actor: str, branch: str = "",
                commit: str = "", tags=None, kind: str = "commit", pending=None,
                gone=None) -> dict:
    """Record a SUCCESSFUL push. The one producer of ``last_push``.

    Two code paths push: :func:`push` (the button) and
    ``archive.push_hook()`` (auto-push). Only the first ever wrote this, so
    after an auto-push the Remote card showed a "last push" from whenever
    somebody had last clicked — measured on the deployed instance, a
    2026-09-21 timestamp beside a tag published 2026-09-22. The card was not
    stale; it was answering a narrower question than it appeared to.

    ``kind`` distinguishes them, because "pushed" is not one event: a
    ``tags`` push publishes a baseline with no new commit, and a card that
    cannot tell the two apart cannot show what actually went out.

    *pending*: tags named and not sent, kept; *gone*: pending tags deleted locally since,
    dropped. Every other pending tag stays (another hook may have added it meanwhile).
    """
    from datetime import datetime, timezone

    def change(config):
        config["last_push"] = {
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "by": actor,
            "kind": kind,
            "branch": branch,
            "commit": commit,
            "tags": list(tags or []),
        }
        # A previous failure is cleared by a success: leaving it would have the
        # card reporting a problem that has since been fixed. So is a hold.
        config.pop("last_push_failure", None)
        config.pop("auto_push_held", None)
        # Tags this push sent leave the pending list; tags a hook call named and this push
        # could not send stay. Read from the record as stored NOW (R18), so a tag another
        # hook added meanwhile is kept, never dropped with this push's stale copy.
        sent, dropped = set(tags or []), set(gone or [])
        keep = (set(config.get("pending_tags") or []) - sent - dropped) | set(pending or [])
        if keep:
            config["pending_tags"] = sorted(keep)
        else:
            config.pop("pending_tags", None)

    config, why = update_remote(list_name, change)
    if config is None:
        return {"ok": False, "error": why}
    return {"ok": True, "last_push": config["last_push"]}


def _keep_pending(config: dict, tags) -> None:
    """Tags a hook call NAMED and did not send, kept for the next push (the
    caller named them; nothing is computed from reachability)."""
    keep = set(config.get("pending_tags") or []) | {t for t in (tags or []) if t}
    if keep:
        config["pending_tags"] = sorted(keep)


def record_push_failure(list_name: str, *, actor: str, reason: str, tags=None) -> dict:
    """Record a FAILED push — deliberately not as ``last_push``.

    A timestamp on a push that did not happen is the worst kind of record:
    it reads as durability that does not exist. The failure is its own field,
    and ``last_push`` keeps pointing at the last thing that really went out.
    """
    from datetime import datetime, timezone

    def change(config):
        config["last_push_failure"] = {
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "by": actor,
            "reason": (reason or "")[:400],
        }
        _keep_pending(config, tags)

    config, why = update_remote(list_name, change)
    if config is None:
        return {"ok": False, "error": why}
    return {"ok": True, "last_push_failure": config["last_push_failure"]}


def record_push_held(list_name: str, *, reason: str, needs: str = "",
                     tags=None) -> dict:
    """Record that auto-push HELD a commit at the publication gate (the
    operator, 2026-10-01: four commits sat on the host for four hours and the
    reason was in the log alone, so the row said "not pushed" and its action,
    Push now, could not work until a person re-acknowledged). The reader draws
    it; the next successful push clears it. *tags* are the tags the held
    commit created, kept as ``pending_tags`` so the push that follows sends
    them."""
    from datetime import datetime, timezone

    def change(config):
        was = config.get("auto_push_held") or {}
        config["auto_push_held"] = {
            # SINCE the first hold, not the latest: the row's age is how long a
            # person has been needed.
            "since": was.get("since") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reason": (reason or "")[:400], "needs": needs or "",
        }
        _keep_pending(config, tags)

    config, why = update_remote(list_name, change)
    if config is None:
        return {"ok": False, "error": why}
    return {"ok": True, "auto_push_held": config["auto_push_held"]}


def push(list_name: str, *, actor: str, repo_dir: str = "") -> dict:
    """main + --follow-tags, then refs/notes/* IF any note ref exists.

    Notes are pushed only when there is something to push: an empty refspec
    errors on some git versions, and reporting ``0 notes`` is the honest
    answer rather than a failure.

    Refuses unless verification passed and the acknowledgement still covers
    what would go out.
    """
    import time
    from datetime import datetime, timezone

    from modules.config import get_list_data_dir

    config = load_remote(list_name)
    if not config:
        return {"ok": False, "error": f"'{list_name}' has no remote configured"}
    if not config.get("verified_at"):
        return {"ok": False, "error": "this remote has not passed verification"}

    covers = acknowledgement_covers(list_name, repo_dir)
    if not covers["ok"]:
        return {"ok": False, "error": covers["reason"], "needs": covers.get("needs"),
                "detail": covers}

    repo_dir = repo_dir or os.path.join(get_list_data_dir(list_name),
                                        "config_repo")
    url, branch = remote_url(config), config.get("branch", "main")
    started = time.time()
    # One publisher per repository at a time (R18), with the auto-push hook.
    with publish_lock(repo_dir):
        return _push_locked(list_name, actor, repo_dir, url, branch, started)


def _push_locked(list_name: str, actor: str, repo_dir: str, url: str, branch: str,
                 started: float) -> dict:
    import time

    before = {l.split()[1] for l in _run(["git", "ls-remote", url],
                                         timeout=90).stdout.splitlines()
              if len(l.split()) > 1}

    # HEAD read ONCE under the lock; that sha is pushed and recorded (R18).
    head = _run(["git", "-C", repo_dir, "rev-parse", "HEAD"], timeout=60).stdout.strip()
    if not head:
        return {"ok": False, "error": "HEAD could not be read, so nothing was pushed",
                "stage": "push_main"}
    main_push = _run(["git", "-C", repo_dir, "push", "--follow-tags", url,
                      f"{head}:refs/heads/{branch}"], timeout=600)
    if main_push.returncode != 0:
        return {"ok": False, "error": (main_push.stderr or "")[:400],
                "stage": "push_main"}

    note_refs = [l for l in _run(["git", "-C", repo_dir, "for-each-ref",
                                  "--format=%(refname)", "refs/notes"],
                                 timeout=60).stdout.splitlines() if l.strip()]
    notes_pushed = 0
    if note_refs:
        notes = _run(["git", "-C", repo_dir, "push", url, "refs/notes/*:refs/notes/*"],
                     timeout=300)
        notes_pushed = len(note_refs) if notes.returncode == 0 else 0

    after = {l.split()[1] for l in _run(["git", "ls-remote", url],
                                        timeout=90).stdout.splitlines()
             if len(l.split()) > 1}
    gained = after - before

    record_push(list_name, actor=actor, branch=branch, kind="commit", commit=head,
                tags=[r.split("refs/tags/", 1)[1] for r in gained
                      if r.startswith("refs/tags/") and not r.endswith("^{}")])

    result = {
        "ok": True, "remote": url, "branch": branch,
        "refs_now": len(after),
        "refs_gained": len(gained),
        "tags_pushed": len([r for r in gained if r.startswith("refs/tags/")]),
        "heads_pushed": len([r for r in gained if r.startswith("refs/heads/")]),
        "notes_pushed": notes_pushed,
        "note_refs_present": len(note_refs),
        "seconds": round(time.time() - started, 1),
    }
    log.info("remote: '%s' pushed to %s by %s — %s", list_name, url, actor,
             {k: v for k, v in result.items() if k != "ok"})
    return result


def enable_auto_push(list_name: str, *, actor: str) -> dict:
    """Offered only after a successful push, never before."""
    def change(config):
        if not config.get("last_push"):
            return "auto-push is offered only after a successful push"
        config["auto_push"] = True

    config, why = update_remote(list_name, change)
    if config is None:
        return {"ok": False, "error": why}
    log.info("remote: '%s' auto-push enabled by %s", list_name, actor)
    return {"ok": True}


def auto_push_decision(list_name: str, repo_dir: str = "") -> dict:
    """May the post-commit hook push this commit WITHOUT a person?

    Auto-push must not widen what is published. Each new commit is re-scanned:
    if it introduces a gated kind that was not acknowledged, or raises the
    count of one that was, the push is HELD and a person is asked to
    re-acknowledge. Ordinary commits — a golden change carrying no new
    exposure — push as before.

    Holding is the conservative direction and the recoverable one: the commit
    is already safe in the local repository, and nothing is lost by waiting.
    Pushing would be irreversible.
    """
    config = load_remote(list_name)
    if not config:
        return {"push": False, "reason": "no remote configured"}
    if not config.get("auto_push"):
        return {"push": False, "reason": "auto-push is not enabled"}

    covers = acknowledgement_covers(list_name, repo_dir)
    if covers["ok"]:
        return {"push": True, "reason": "acknowledgement still covers this"}
    return {"push": False, "held": True, "reason": covers["reason"],
            "needs": covers.get("needs"), "new_kinds": covers.get("new_kinds"),
            "risen": covers.get("risen")}
