"""The lifecycle shared by jobs (I-1) and controller apps (I-2): the SDN design (rev. 4),
sections 11 ("The lifecycle") and 12 ("Controller apps follow I-1's lifecycle"). Pure functions
over a `Version` record; no store yet (P4 adds `job_runs`, and the registry that keeps these).

The states:
- **Draft:** the author only, plan mode only (a job); deploys only in the container harness
  (an app).
- **Published:** reviewed by someone other than the author, its harness tests passed, and
  pinned by its folder's content hash. **Any edit (the hash moved) returns it to Draft**
  (`observe`). Self-review is allowed only where the installation's policy says single-user,
  and is recorded as such (`self_review`).
- **Retired:** kept for audit.

Standard change (section 11, step 3) is a flag on a Published version, P4's to set and honour;
the record refuses it on any other state.

**The content hash** (`content_hash`): the folder as git holds it at a revision (C2616; the
operator, 2026-11-06: "hash the folder as git holds it ... so running tests never moves a job
back to Draft"). SHA-256 over each tracked file's path relative to the folder, its git mode
(`100644`, or `100755` for an executable) and its blob id, from `git ls-tree -r` at that
revision, in the byte order of the paths, after a version tag. So what is not committed never
enters it: bytecode (`__pycache__`), an untracked file, an edit not yet committed. A committed
edit, rename, addition, removal or change of the executable bit moves it; no modification time
or owner can. A symbolic link or a submodule in the folder is refused, naming it, as is a path
outside the repository, a folder git holds nothing in, and a folder that is not in a
repository. Readers take what is committed (CLAUDE.md), and so does the review.
"""

import hashlib
import os
from typing import Literal

from pydantic import StrictBool, field_validator, model_validator

from modules.jobs.base import APP_NAME, JOB_NAME, VERSION, Contract, ContractError, matches

DRAFT, PUBLISHED, RETIRED = "draft", "published", "retired"
STATES = (DRAFT, PUBLISHED, RETIRED)
KINDS = ("job", "app")
NAMES = {"job": JOB_NAME, "app": APP_NAME}
#: The hash's own version, hashed first, so a change of framing can never collide with this one.
HASH_FRAMING = b"mercury-git-folder-sha256-v2\0"
SHA256_HEX = 64


class LifecycleError(ContractError):
    """A lifecycle step refused, naming the version, the comparison and both operands."""


def same_person(a: str, b: str) -> bool:
    """Whether two identities name one person: compared stripped and case-folded, as an email
    address is (`Reviewer@Example` reviewing `reviewer@example`'s work is self-review)."""
    return (a or "").strip().casefold() == (b or "").strip().casefold()


class Version(Contract):
    """One version of a job or an app, and where it stands."""

    kind: Literal["job", "app"]
    name: str
    version: str
    author: str
    state: Literal["draft", "published", "retired"] = DRAFT
    content_sha256: str
    reviewer: str = ""
    self_review: StrictBool = False
    standard_change: StrictBool = False

    @field_validator("version")
    @classmethod
    def _version(cls, v):
        return matches(VERSION, v, "a version")

    @field_validator("author")
    @classmethod
    def _author(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("an author is a non-empty identity")
        return v

    @field_validator("content_sha256")
    @classmethod
    def _hash(cls, v):
        if not (isinstance(v, str) and len(v) == SHA256_HEX
                and all(c in "0123456789abcdef" for c in v)):
            raise ValueError(f"a content hash is {SHA256_HEX} lower-case hex digits")
        return v

    @model_validator(mode="after")
    def _consistent(self):
        matches(NAMES[self.kind], self.name, f"a{'n' if self.kind == 'app' else ''} "
                                             f"{self.kind}'s name")
        if self.state == PUBLISHED and not self.reviewer.strip():
            raise ValueError("a Published version names its reviewer")
        if self.self_review and not same_person(self.reviewer, self.author):
            raise ValueError(f"self_review is set, but the reviewer {self.reviewer!r} is not "
                             f"the author {self.author!r}")
        if self.standard_change and self.state != PUBLISHED:
            raise ValueError(f"only a Published version is a standard change, not a "
                             f"{self.state} one")
        return self

    def label(self) -> str:
        return f"{self.kind} {self.name} {self.version} ({self.state}, {self.content_sha256[:12]})"

    def _with(self, **changes) -> "Version":
        return Version(**dict(self.model_dump(), **changes))


# ── the content hash ─────────────────────────────────────────────────────────────────────────

def _refuse(where: str, problem: str):
    raise LifecycleError(where, [problem])


def content_hash(repo, path: str, rev: str = "HEAD") -> str:
    """The content hash of the folder *path* (relative to the repository *repo*) as git holds it
    at *rev* (see the module's docstring), as 64 hex digits."""
    from modules.nsot.repo import has_repository, run_git

    repo = os.fspath(repo)
    where = f"the folder {path!r} at {rev} in {repo!r}"
    if not has_repository(repo):
        _refuse(where, f"{repo!r} is not a git repository: a folder is hashed as git holds it")
    norm = os.path.normpath(path).replace(os.sep, "/") if path else ""
    if not norm or os.path.isabs(path) or norm == ".." or norm.startswith("../"):
        _refuse(where, f"{path!r} is not a folder inside the repository")
    proc = run_git(repo, "ls-tree", "-r", "-z", "--full-tree", rev, "--", norm, text=False)
    if proc.returncode != 0:
        said = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        _refuse(where, f"git ls-tree refused it: {said[0] if said else 'no reason given'}")
    entries = []
    prefix = norm + "/"
    for raw in (proc.stdout or b"").split(b"\0"):
        if not raw:
            continue
        head, _, name = raw.partition(b"\t")
        mode, kind, obj = head.decode("ascii").split()
        full = name.decode("utf-8", "surrogateescape")
        rel = full[len(prefix):] if full.startswith(prefix) else full
        if mode == "120000":
            _refuse(where, f"{rel} is a symbolic link: a hashed folder holds only files")
        if kind != "blob":
            _refuse(where, f"{rel} is a {kind} (a submodule), not a file")
        entries.append((os.fsencode(rel), mode.encode("ascii"), obj.encode("ascii")))
    if not entries:
        _refuse(where, "git holds no file there")
    digest = hashlib.sha256(HASH_FRAMING)
    for rel, mode, obj in sorted(entries):
        digest.update(len(rel).to_bytes(8, "big") + rel + mode + b" "
                      + len(obj).to_bytes(1, "big") + obj)
    return digest.hexdigest()


# ── the steps ────────────────────────────────────────────────────────────────────────────────

def draft(kind: str, name: str, version: str, author: str, repo, path: str,
          rev: str = "HEAD") -> Version:
    """A new Draft of the folder *path* in *repo*, pinned by its hash at *rev* now."""
    return Version(kind=kind, name=name, version=version, author=author,
                   content_sha256=content_hash(repo, path, rev))


def observe(v: Version, folder_hash: str) -> Version:
    """*v* after its folder was hashed as *folder_hash*: unchanged when the hash is the pinned
    one; a Published version whose hash moved returns to Draft (its review and standard change
    cleared); a Draft takes the new hash; a Retired version stays as it was retired."""
    if folder_hash == v.content_sha256 or v.state == RETIRED:
        return v
    return v._with(state=DRAFT, content_sha256=folder_hash, reviewer="", self_review=False,
                   standard_change=False)


def publish(v: Version, folder_hash: str, *, reviewer: str, harness_passed: bool,
            single_user: bool = False) -> Version:
    """*v* Published by *reviewer*, or `LifecycleError` naming what was compared:
    - only a Draft is published;
    - *folder_hash* (the folder as reviewed) equals the Draft's pinned hash;
    - its harness tests passed;
    - the reviewer is someone other than the author, unless the installation's policy is
      single-user (*single_user*), when the review is recorded as self-review."""
    problems = []
    if v.state != DRAFT:
        problems.append(f"only a Draft is published; this version is {v.state}")
    if folder_hash != v.content_sha256:
        problems.append(f"the folder's hash {folder_hash} is not the Draft's pinned "
                        f"{v.content_sha256}: the folder moved since it was drafted")
    if harness_passed is not True:
        problems.append(f"its harness tests have not passed (harness_passed is "
                        f"{harness_passed!r})")
    if not isinstance(reviewer, str) or not reviewer.strip():
        problems.append("no reviewer is named")
    elif same_person(reviewer, v.author) and single_user is not True:
        problems.append(f"the reviewer {reviewer!r} is the author {v.author!r}, and the "
                        "installation's policy is not single-user")
    if problems:
        raise LifecycleError(f"publishing {v.label()}", problems)
    return v._with(state=PUBLISHED, reviewer=reviewer,
                   self_review=same_person(reviewer, v.author))


def retire(v: Version) -> Version:
    """*v* Retired, kept for audit."""
    if v.state == RETIRED:
        raise LifecycleError(f"retiring {v.label()}", ["it is already retired"])
    return v._with(state=RETIRED, standard_change=False)


def run_refusal(v: Version, mode: str, runner: str) -> str:
    """Why *runner* may not run job version *v* in *mode*, or "" when they may: a Draft runs
    for its author only, in plan mode only; a Retired version never runs."""
    if v.kind != "job":
        return f"{v.label()} is an app; an app is deployed, not run"
    if mode not in ("plan", "commit"):
        return f"mode {mode!r} is not plan or commit"
    if v.state == RETIRED:
        return f"{v.label()} is retired"
    if v.state == DRAFT:
        if not same_person(runner, v.author):
            return f"{v.label()} is a Draft: only its author {v.author!r} runs it, not {runner!r}"
        if mode != "plan":
            return f"{v.label()} is a Draft: it runs in plan mode only, not {mode}"
    return ""


def deploy_refusal(v: Version, staged_hash: str) -> str:
    """Why app version *v* may not deploy to a real controller with its folder staged as
    *staged_hash*, or "" when it may: only a Published version, byte for byte the version
    reviewed (section 12)."""
    if v.kind != "app":
        return f"{v.label()} is a job; a job is run, not deployed"
    if v.state != PUBLISHED:
        return (f"{v.label()} is {v.state}: only a Published version deploys to a controller "
                "(a Draft deploys only in the container harness)")
    if staged_hash != v.content_sha256:
        return (f"the staged folder's hash {staged_hash} is not the Published "
                f"{v.content_sha256}")
    return ""
