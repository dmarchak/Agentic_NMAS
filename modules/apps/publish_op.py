"""Publishing a controller app version, minimal (C2854; the operator's replan of 2026-11-09:
"a person's review plus the plain test run's pass"): the step that moves a registered Draft to
Published, the only state a controller app deploy stages (`channel.stage_published`).

**Two operations, each a person's:**
- **Run its tests** (`run_tests`): the version's folder staged from the copy's blobs at its
  commit (`channel.stage`, never a working tree), its manifest's own tests run in the container
  harness on the network's controller Python (`modules/apps/test_run.run`, the operator's
  decision C2635: an app's code never runs in Mercury's process), and the run kept with the
  version's record by its content hash (`coderepo.record_test`). A run of another hash is never
  this version's.
- **Publish** (`preview`, then `apply`): the preview names the version, its pin (commit and
  content hash), its author, the newest test run at that hash, who may publish under the
  network's review policy (`coderepo.review_policy`) and the hash the confirm binds
  (`plan_hash`: the network, the app, the version, the content hash, the test run and the
  policy). The confirm, by that hash as a verified person with a reason, is checked again
  inside the record's lock (`coderepo.publish`: the folder read again from its blobs, the test
  run passed at that hash, `lifecycle.publish`'s own rules) and kept with the version's record.

**What it does not do yet** (the replan's deferral, after Nov 30): the gate's mutation,
survivors, reconcile and `@covers` checks (C2728); the registry's other columns. A Published
version is deployable on SDN › Apps the moment it is recorded.

**The steps** (`STEPS`, the manual's page docs/manual/how-it-works/app-publish.md): ``stage``,
``test``, ``record`` for a run; ``read``, ``confirm``, ``check``, ``publish``, ``announce`` for
the publication. It changes no device, so there is no verify or rollback of one: a wrong
publication is corrected forward by a new version (or a Retire, P4's, not built).
"""

import hashlib
import logging
import shutil
import tempfile

log = logging.getLogger(__name__)

RUN_STEPS = ("stage", "test", "record")
STEPS = ("read", "confirm", "check", "publish", "announce")


class Refused(ValueError):
    """Refused before anything was recorded; the message is the whole reason."""


def plan_hash(network: str, name: str, version: str, sha256: str, test_id: str,
              policy: str) -> str:
    """What the confirm binds (see the module's docstring)."""
    body = "\0".join((network, name, version, sha256 or "", test_id or "", policy or ""))
    return hashlib.sha256(body.encode()).hexdigest()


def _python(network: str):
    """``(major.minor, words)`` of the network's controller Python, or ``(None, why)``."""
    from modules.sdn import controller_runtime

    t = controller_runtime.target(network)
    if t.version is None:
        return None, t.words or "the controller's Python is not recorded"
    return ".".join(str(n) for n in tuple(t.version)[:2]), t.words


def _manifest_of(network: str, name: str, version: str):
    from modules import coderepo

    reg = coderepo.registered(network)
    for app in reg.get("apps") or []:
        if app["name"] == name:
            for entry in app["versions"]:
                if entry["version"].version == version:
                    return entry, ""
    return None, (reg.get("error") or f"{name} {version} is not registered for {network}")


def preview(network: str, name: str, version: str, *, viewer: str) -> dict:
    """What Publish draws for *viewer* before the confirm: ``{"ok", "name", "version",
    "commit", "sha256", "author", "state", "test", "policy", "policy_words", "may", "why",
    "hash", "error"}``. Writes nothing."""
    from modules import coderepo
    from modules.jobs.lifecycle import PUBLISHED, same_person

    entry, why = _manifest_of(network, name, version)
    if entry is None:
        return {"ok": False, "error": why}
    v = entry["version"]
    policy = coderepo.review_policy(network)
    if policy["state"] != "ok":
        return {"ok": False, "error": policy["error"]}
    test = entry.get("test")
    out = {"ok": True, "error": "", "network": network, "name": name, "version": version,
           "commit": entry.get("commit", ""), "sha256": v.content_sha256, "author": v.author,
           "state": v.state, "test": test, "policy": policy["value"],
           "policy_words": policy["words"], "reviewer": viewer,
           "publication": entry.get("publication"),
           "tests": list(getattr(entry.get("manifest"), "tests", ()) or ())}
    reasons = []
    if v.state == PUBLISHED:
        reasons.append(f"{name} {version} is Published already, by {v.reviewer}")
    if test is None:
        reasons.append("its tests have not been run at this hash: Run its tests first")
    elif test.get("ok") is not True:
        reasons.append(f"its last test run did not pass ({test.get('failed')} failed, "
                       f"{test.get('errors')} errors): a new commit, fetched, is a new pin")
    self_review = same_person(viewer, v.author)
    if self_review and policy["value"] != "self_recorded":
        reasons.append(f"you are its author ({v.author}), and {network}'s review policy is "
                       f"{policy['words']}: another person publishes it, or the policy is "
                       "changed on the Code repository card")
    out.update(may=not reasons, why="; ".join(reasons), self_review=self_review,
               hash=plan_hash(network, name, version, v.content_sha256,
                              (test or {}).get("id", ""), policy["value"]))
    return out


def run_tests(network: str, name: str, version: str, *, actor: str, actor_verified: str,
              runner=None) -> dict:
    """Run the version's own tests (see the module's docstring): ``{"ok", "run", "entry",
    "error"}``; *entry* is the recorded run (None when nothing was recorded)."""
    from modules import coderepo
    from modules.apps import channel, test_run

    if not actor or actor_verified in ("", "none"):
        return {"ok": False, "run": None, "entry": None,
                "error": "a version's tests are run for a verified person"}
    entry, why = _manifest_of(network, name, version)
    if entry is None:
        return {"ok": False, "run": None, "entry": None, "error": why}
    python, words = _python(network)
    if python is None:
        return {"ok": False, "run": None, "entry": None,
                "error": f"can't tell which Python to run its tests on: {words}"}
    tests = list(getattr(entry["manifest"], "tests", ()) or ())
    if not tests:
        return {"ok": False, "run": None, "entry": None,
                "error": f"{name} {version}'s manifest names no test, so nothing can pass"}
    root = tempfile.mkdtemp(prefix="nmas-app-test-")
    try:
        try:
            staged = channel.stage(entry["repo"], entry["path"], entry["rev"],
                                   f"{root}/{name}-{version}")
        except channel.ChannelRefused as exc:
            return {"ok": False, "run": None, "entry": None,
                    "error": f"{name} {version} could not be staged: {exc}"}
        if staged["sha256"] != entry["version"].content_sha256:
            return {"ok": False, "run": None, "entry": None,
                    "error": (f"{name} {version} stages as {staged['sha256'][:12]}, and is "
                              f"registered at {entry['version'].content_sha256[:12]}")}
        kw = {"tests": tests, "timeout_s": test_run.BOUND_S}
        if runner is not None:
            kw["runner"] = runner
        got = test_run.run(staged["folder"], python, **kw)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    try:
        recorded = coderepo.record_test(network, name, version, got, actor=actor,
                                        actor_verified=actor_verified)
    except coderepo.Refused as exc:
        return {"ok": False, "run": got, "entry": None, "error": str(exc)}
    return {"ok": bool(got.get("ok")), "run": got, "entry": recorded,
            "error": "" if got.get("ok") else (got.get("error") or "its tests did not pass")}


def apply(network: str, name: str, version: str, confirmed: str, *, actor: str,
          actor_verified: str, reason: str) -> dict:
    """Publish, bound to *confirmed* (the preview's hash): ``{"outcome" ("published",
    "refused"), "error", "moved", ...the publication}``."""
    from modules import coderepo

    now = preview(network, name, version, viewer=actor)
    if not now.get("ok"):
        return {"outcome": "refused", "error": now.get("error"), "moved": False}
    if now["hash"] != (confirmed or ""):
        return {"outcome": "refused", "moved": True,
                "error": (f"what Publish would record moved since the preview (confirmed "
                          f"{(confirmed or 'none')[:12]}, now {now['hash'][:12]}: the folder's "
                          "hash, its test run or the review policy changed): nothing was "
                          "published; look at it again")}
    if not now["may"]:
        return {"outcome": "refused", "error": now["why"], "moved": False}
    try:
        done = coderepo.publish(network, name, version, content_sha256=now["sha256"],
                                test_id=(now["test"] or {}).get("id", ""), reviewer=actor,
                                reviewer_verified=actor_verified, reason=reason)
    except coderepo.Refused as exc:
        return {"outcome": "refused", "error": str(exc), "moved": False}
    return dict(done, outcome="published", error="", moved=False)
