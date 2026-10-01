"""Is each list's repository published? HEAD against the REMOTE's own branch
(C223, the operator, 2026-09-29).

**What it answers.** Abandon's commit `7a72258` stayed on the host while
GitHub held `cf4d96d`, and nothing said so: the Git tab read "Everything is
committed", the Remote card showed the last push the hook recorded, and
Needs attention had no source for it. The hook's own record cannot answer
this, because a commit that never reached the hook leaves no record (C223),
and a record that cannot be read reads as no remote at all (C172). So the
answer is derived from two facts nothing in NMAS writes:

- the repository's HEAD, and
- the remote's branch, asked with `git ls-remote` at read time. The
  repository's own `origin` is asked (the push hook creates it), and only
  when there is none is the URL in `remote.json` used. So an unreadable
  record still gets an answer.

States per list: `in_sync`; `ahead` (N commits not pushed, with the oldest
one's sha and commit time); `remote_ahead` (the remote holds commits this
repository lacks); `diverged`; `no_branch` (the remote has no such branch);
`not_asked` (the remote could not be asked, with the reason); and
`record_unreadable` beside any of them, when `remote.json` exists and does
not read (C172's symptom, made visible here and not fixed).

A list with no `remote.json` and no `origin` has no remote, and is not a
row: "history on this host only" is the configuration, drawn by the card.
"""

import os
import subprocess
import time

from modules import reader_job

INTERVAL_SECONDS = 120
#: One sample on the host, 2026-09-29: `git ls-remote origin refs/heads/main`
#: over the SSH alias took 0.99 s, and a second attempt got no answer before
#: the session closed. So the bound is wider than 2.5x the sample, until there
#: are more samples; a timeout reads as `not_asked`, never as in sync.
LS_REMOTE_TIMEOUT_S = 10
LOCAL_GIT_TIMEOUT_S = 15


def _lists() -> dict:
    """name -> slug, from the lists' own map (resolving creates nothing, C51)."""
    from modules.device import _load_device_lists_config

    return dict((_load_device_lists_config().get("lists") or {}))


def _git(repo: str, *args, timeout=LOCAL_GIT_TIMEOUT_S):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          timeout=timeout, env=env)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _record(list_dir: str):
    """(state, config) of `remote.json`: absent, unreadable or ok."""
    import json

    from modules.nsot.remote import REMOTE_FILE

    path = os.path.join(list_dir, REMOTE_FILE)
    if not os.path.exists(path):
        return "absent", None
    try:
        with open(path, encoding="utf-8") as fh:
            config = json.load(fh)
        if not isinstance(config, dict):
            raise ValueError("not a mapping")
        return "ok", config
    except (OSError, ValueError) as exc:
        return f"unreadable: {exc}", None


def judge(repo: str, list_dir: str) -> dict:
    """One list's publication state. Never raises for a git failure: it names it."""
    from modules.nsot.remote import remote_url

    record, config = _record(list_dir)
    out = {"record": "ok" if record == "ok" else record.split(":")[0],
           "record_detail": "" if record in ("ok", "absent") else record}
    rc, origin, _ = _git(repo, "remote", "get-url", "origin")
    target = "origin" if rc == 0 and origin else (remote_url(config) if config else "")
    if not target:
        out["state"] = "no_remote" if record == "absent" else "not_asked"
        if record != "absent":
            out["reason"] = ("remote.json cannot be read and the repository has no origin, "
                             "so there is nothing to ask")
        return out
    branch = (config or {}).get("branch") or "main"
    out.update(branch=branch,
               remote=(f"{config['owner']}/{config['repo']}" if config and config.get("owner")
                       else (origin or target)))
    rc, head, err = _git(repo, "rev-parse", "HEAD")
    if rc != 0:
        out.update(state="not_asked", reason=f"this repository has no HEAD: {err[:200]}")
        return out
    out["head"] = head
    try:
        rc, line, err = _git(repo, "ls-remote", target, f"refs/heads/{branch}",
                             timeout=LS_REMOTE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        out.update(state="not_asked", reason=f"the remote did not answer within "
                                             f"{LS_REMOTE_TIMEOUT_S} s")
        return out
    out["asked_at"] = time.time()
    if rc != 0:
        out.update(state="not_asked", reason=f"git ls-remote failed: {err[:300]}")
        return out
    remote_sha = line.split()[0] if line.split() else ""
    out["remote_head"] = remote_sha
    if not remote_sha:
        n = _git(repo, "rev-list", "--count", "HEAD")[1]
        out.update(state="no_branch", ahead=int(n or 0))
        return out
    if remote_sha == head:
        out.update(state="in_sync", ahead=0)
        return out
    if _git(repo, "cat-file", "-e", f"{remote_sha}^{{commit}}")[0] != 0:
        out.update(state="remote_ahead", reason="the remote holds a commit this repository "
                                                "does not have; NMAS never force-pushes")
        return out
    if _git(repo, "merge-base", "--is-ancestor", remote_sha, head)[0] == 0:
        n = int(_git(repo, "rev-list", "--count", f"{remote_sha}..{head}")[1] or 0)
        oldest = _git(repo, "log", "--reverse", "--format=%H %ct %s",
                      f"{remote_sha}..{head}")[1].splitlines()
        sha, at, subject = (oldest[0].split(" ", 2) + ["", ""])[:3] if oldest else ("", "0", "")
        out.update(state="ahead", ahead=n, oldest_sha=sha, oldest_at=float(at or 0),
                   oldest_subject=subject)
        return out
    if _git(repo, "merge-base", "--is-ancestor", head, remote_sha)[0] == 0:
        out.update(state="remote_ahead", reason="the remote is ahead of this repository")
        return out
    out.update(state="diverged", reason="this repository and the remote have each moved; "
                                        "NMAS never force-pushes, so a person resolves it")
    return out


def read(lists=None) -> dict:
    from modules.config import LISTS_DIR

    names = _lists() if lists is None else lists
    out = {}
    for name, slug in sorted(names.items()):
        list_dir = os.path.join(LISTS_DIR, slug)
        repo = os.path.join(list_dir, "config_repo")
        if not os.path.isdir(os.path.join(repo, ".git")):
            continue
        try:
            out[name] = judge(repo, list_dir)
        except Exception as exc:                     # noqa: BLE001
            out[name] = {"state": "not_asked",
                         "reason": f"the check raised {type(exc).__name__}: {exc}"}
    return {"lists": out}


def status_for(list_name: str, cached=None) -> dict:
    """The stored answer for one list, with the read's age. {} before any read."""
    got = reader_job.read_cached(READER.name) if cached is None else cached
    good = ((got.get("doc") or {}).get("last_good") or {})
    value = ((good.get("value") or {}).get("lists") or {}).get(list_name)
    if value is None:
        return {}
    return {**value, "value_at": good.get("value_at"),
            "stale_after_seconds": INTERVAL_SECONDS * reader_job.STALE_AFTER_INTERVALS}


def age_words(seconds) -> str:
    s = max(0, int(seconds or 0))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min"
    if s < 86400:
        return f"{s // 3600} h {s % 3600 // 60} min"
    return f"{s // 86400} d {s % 86400 // 3600} h"


def describe(pub: dict, now: float = None) -> dict:
    """The ONE sentence about publication, and its level, for the Git tab's
    status line, the Remote card and Needs attention (C223). Computed here, so
    no screen composes its own and none decides a colour.

    ``{"level", "state", "clause", "detail"}``: *clause* follows "Everything
    is committed ·"; *detail* is the evidence (both heads, the read's age)."""
    now = time.time() if now is None else now
    if not pub:
        return {"level": "secondary", "state": "not_read", "clause":
                "not yet compared with the remote (the check runs every "
                f"{INTERVAL_SECONDS // 60} min, and after every commit)", "detail": ""}
    state, remote = pub.get("state"), pub.get("remote") or "the remote"
    asked = (f"compared {age_words(now - pub['asked_at'])} ago"
             if pub.get("asked_at") else "")
    heads = (f"HEAD {str(pub.get('head', ''))[:7]}, {remote} {pub.get('branch', '')} at "
             f"{str(pub.get('remote_head', ''))[:7] or 'nothing'}")
    unreadable = pub.get("record") == "unreadable"
    record = (" The remote record (remote.json) cannot be read, so the push hook treats "
              f"this list as having no remote and pushes nothing (C172): {pub.get('record_detail')}."
              if unreadable else "")
    if state == "no_remote":
        return {"level": "secondary", "state": state,
                "clause": "no remote: the history is on this host only", "detail": ""}
    if state == "in_sync":
        return {"level": "danger" if unreadable else "success", "state": state,
                "clause": f"and pushed to {remote}" + record,
                "detail": "; ".join(x for x in (heads, asked) if x)}
    if state == "ahead":
        n = pub.get("ahead", 0)
        age = age_words(now - pub["oldest_at"]) if pub.get("oldest_at") else "unknown age"
        return {"level": "danger" if unreadable else "warning", "state": state,
                "clause": (f"{n} commit(s) not pushed to {remote} (oldest: "
                           f"{str(pub.get('oldest_sha', ''))[:7]}, {age})" + record),
                "detail": "; ".join(x for x in (heads, asked,
                                                 f"oldest: {pub.get('oldest_subject', '')}")
                                    if x)}
    if state == "no_branch":
        return {"level": "warning", "state": state,
                "clause": (f"none of its {pub.get('ahead', 0)} commit(s) is on {remote}: the "
                           f"remote has no {pub.get('branch')} branch" + record),
                "detail": asked}
    if state in ("remote_ahead", "diverged"):
        return {"level": "danger", "state": state,
                "clause": f"{remote} does not match: {pub.get('reason', '')}" + record,
                "detail": "; ".join(x for x in (heads, asked) if x)}
    return {"level": "warning", "state": state or "not_asked",
            "clause": ("whether it is pushed is unknown: "
                       + (pub.get("reason") or "the remote could not be asked") + record),
            "detail": asked}


def refresh_hook(context: dict) -> dict:
    """A post-commit hook, registered after the push: re-read at once, so a
    commit or a push is reflected without waiting for the next cycle."""
    reader_job.run_once(READER, announce=reader_job.announce_via_page,
                        trigger={"kind": "after_commit"})
    return {"ok": True, "message": "publication state re-read"}


READER = reader_job.register(reader_job.Reader(
    name="remote-publication",
    what="whether each list's repository is published: HEAD against the remote's own branch",
    endpoints=("each list's config repository: HEAD and its commit log",
               "each list's remote, by `git ls-remote <origin> refs/heads/<branch>`"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("a commit left on the host matters in minutes, not seconds; one "
                    "ls-remote is about 1 s over SSH (measured on the host, 2026-09-29), and "
                    "a commit re-reads at once through the post-commit hook"),
    read=read,
    invalidates=("remote",),
    remedy="Read the reason above: it names the list and what could not be asked",
    window="the repository and the remote at the read",
))
