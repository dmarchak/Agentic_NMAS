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
    """Write this list's remote config. Never touches ``~/.ssh/config``."""
    path = remote_path(list_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return {"ok": True, "path": path}


def adopt(list_name: str, *, ssh_alias: str, owner: str, repo: str,
          branch: str = "main", key_path: str = "", actor: str = "operator") -> dict:
    """Record an EXISTING setup as this list's remote.

    ``managed_by_nmas`` is false for an adopted setup: NMAS verifies and
    pushes, and never rewrites the key or the SSH stanza. ``auto_push`` starts
    false always — it is turned on after a successful push, never before.
    """
    from datetime import datetime, timezone

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
        "adopted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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

    lists_dir = os.path.dirname(get_list_data_dir(list_name))
    for slug in sorted(os.listdir(lists_dir)):
        if slug == list_name:
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


def verify(list_name: str, repo_dir: str = "") -> dict:
    """All five checks. Every one must pass."""
    from modules.config import get_list_data_dir

    config = load_remote(list_name)
    if not config:
        return {"ok": False, "error": f"'{list_name}' has no remote configured"}
    repo_dir = repo_dir or os.path.join(get_list_data_dir(list_name),
                                        "config_repo")

    checks = [check_key_scope(config)]
    if checks[0]["ok"]:
        checks.append(check_read(config))
        checks.append(check_write_probe(config))
        checks.append(check_private(config))
        checks.append(check_right_repository(config, list_name, repo_dir))

    ok = all(c["ok"] for c in checks)
    if ok:
        from datetime import datetime, timezone
        config["verified_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        save_remote(list_name, config)
    return {"ok": ok, "checks": checks, "remote": remote_url(config)}


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
    try:
        from modules.redact import known_secret_values
        current |= {v for v in known_secret_values() if v}
    except Exception:                          # noqa: BLE001
        pass

    findings = {}
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
    return {"rows": rows, "blobs_scanned": len(blobs), "gated_kinds": gated}


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
    return {"kinds": sorted(counts), "counts": counts}


def acknowledge(list_name: str, *, actor: str, actor_kind: str,
                repo_dir: str = "") -> dict:
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
    head = _run(["git", "-C", repo_dir, "rev-parse", "HEAD"],
                timeout=60).stdout.strip()

    config["acknowledged_secrets"] = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by": actor, "by_kind": actor_kind,
        "kinds": gated["kinds"], "counts": gated["counts"],
        "commit": head,
    }
    save_remote(list_name, config)
    log.info("remote: '%s' publication acknowledged by %s (%s) — kinds=%s "
             "counts=%s at %s", list_name, actor, actor_kind, gated["kinds"],
             gated["counts"], head[:12])
    return {"ok": True, "acknowledged": config["acknowledged_secrets"]}


def acknowledgement_covers(list_name: str, repo_dir: str = "") -> dict:
    """Does the recorded acknowledgement still cover what would be published?

    Re-scanned, not trusted. A NEW gated kind, or a HIGHER count of one
    already acknowledged, means a person agreed to publish less than is now
    on offer — so it does not carry.

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
    was = {"kinds": ack.get("kinds") or [], "counts": ack.get("counts") or {}}

    new_kinds = sorted(set(now["kinds"]) - set(was["kinds"]))
    risen = sorted(k for k, n in now["counts"].items()
                   if n > was["counts"].get(k, 0))
    if new_kinds or risen:
        return {"ok": False, "needs": "re-acknowledgement",
                "new_kinds": new_kinds, "risen": risen,
                "was": was, "now": now,
                "reason": (
                    "what would be published has grown since it was "
                    f"acknowledged: {'new kinds ' + ', '.join(new_kinds) if new_kinds else ''}"
                    f"{' and ' if new_kinds and risen else ''}"
                    f"{'more ' + ', '.join(risen) if risen else ''}")}
    return {"ok": True, "was": was, "now": now}


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

    before = {l.split()[1] for l in _run(["git", "ls-remote", url],
                                         timeout=90).stdout.splitlines()
              if len(l.split()) > 1}

    main_push = _run(["git", "-C", repo_dir, "push", "--follow-tags", url,
                      f"HEAD:refs/heads/{branch}"], timeout=600)
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

    config["last_push"] = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by": actor, "commit": _run(["git", "-C", repo_dir, "rev-parse", "HEAD"],
                                    timeout=60).stdout.strip(),
    }
    save_remote(list_name, config)

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
    config = load_remote(list_name)
    if not config:
        return {"ok": False, "error": "no remote configured"}
    if not config.get("last_push"):
        return {"ok": False, "error": "auto-push is offered only after a "
                                      "successful push"}
    config["auto_push"] = True
    save_remote(list_name, config)
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
