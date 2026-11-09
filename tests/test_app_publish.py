"""Publishing a controller app version, minimal (C2854; board docs/boards/app-publish.html):
`modules/apps/publish_op.py`, the record's half in `modules/coderepo.py` (`record_test`,
`publish`, `review_policy`, `set_review`), and their routes.

The registry is the real one: a code repository committed here, fetched into Mercury's copy and
registered (tests/test_coderepo.py's world). The test run's container is the one seam faked:
`modules/apps/test_run.run` answers as the harness does (its own tests: tests/test_app_test_run.py),
its hash the staged folder's own, so a run over another folder is another hash.

- **Run its tests** stages the version from its pinned blobs, runs its manifest's tests on the
  network's controller Python, and keeps the run with the version by its hash.
- **Publish** needs a passing run at the hash previewed, a reason and a verified person; the
  author publishes only where the network's policy says so, recorded as self-review.
- **The confirm binds what was previewed:** a folder that moved, a new run or a changed policy
  publishes nothing and says so.
- **A Published version is deployable** (`channel.stage_published`), and a fetch that moves its
  folder's hash makes it a Draft again, the publication staying with the hash it was made for.
"""

import re
from html import unescape

import pytest

from modules import coderepo as R
from modules.apps import channel, publish_op as P, test_run
from tests.test_coderepo import ACTOR, NET, VERIFIED, code, git, lab, manifest  # noqa: F401
from tests.test_coderepo import fetch, set_to

AUTHOR = "author@example.invalid"
TEST = ("def test_one():\n    assert 1 + 1 == 2\n\n\ndef test_two():\n    assert 'a' < 'b'\n\n\n"
        "def test_three():\n    assert [1] == [1]\n")


def commit_tested(repo, name="of_versions", version="1.0.0", body="x = 1\n"):
    folder = repo / "apps" / name
    (folder / "tests").mkdir(parents=True, exist_ok=True)
    (folder / "manifest.yml").write_text(manifest(name, version)
                                         + "tests:\n  - tests/test_logic.py\n")
    (folder / f"{name}.py").write_text(body)
    (folder / "tests" / "test_logic.py").write_text(TEST)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"{name} {version}")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def world(lab, code, monkeypatch):  # noqa: F811
    """Default's code repository fetched, of_versions 1.0.0 registered with one test file, the
    controller's Python recorded as 3.5, and the harness faked: it passes unless told not to."""
    commit_tested(code)
    set_to(code)
    assert fetch()["ok"]
    state = {"ok": True, "runs": []}

    def fake_run(folder, python, *, tests, timeout_s, runner=None):
        sha = channel.script().folder_hash(folder)
        state["runs"].append({"folder": folder, "python": python, "tests": list(tests),
                              "timeout_s": timeout_s, "sha": sha})
        if state["ok"]:
            return {"ok": True, "passed": 3, "failed": 0, "errors": 0, "skipped": 0,
                    "python": python, "content_sha256": sha, "output": "3 passed",
                    "error": ""}
        return {"ok": False, "passed": 2, "failed": 1, "errors": 0, "skipped": 0,
                "python": python, "content_sha256": sha,
                "output": "FAILED tests/test_logic.py::test_one", "error": "pytest exited 1"}

    monkeypatch.setattr(test_run, "run", fake_run)
    monkeypatch.setattr(P, "_python", lambda network: ("3.5", "Python 3.5, recorded"))
    return state


def _entry(name="of_versions", version="1.0.0"):
    reg = R.registered(NET)
    app = next(a for a in reg["apps"] if a["name"] == name)
    return next(e for e in app["versions"] if e["version"].version == version)


def _tested():
    got = P.run_tests(NET, "of_versions", "1.0.0", actor=ACTOR, actor_verified=VERIFIED)
    assert got["ok"], got["error"]
    return got


# ── Run its tests ───────────────────────────────────────────────────────────────────────────

def test_the_tests_run_from_the_pinned_blobs_on_the_controller_python_and_are_kept_by_hash(world):
    got = _tested()
    [run] = world["runs"]
    sha = _entry()["version"].content_sha256
    assert run["sha"] == sha and run["python"] == "3.5"
    assert run["tests"] == ["tests/test_logic.py"] and run["timeout_s"] == test_run.BOUND_S
    assert got["entry"]["content_sha256"] == sha and got["entry"]["by"] == ACTOR
    assert _entry()["test"]["id"] == got["entry"]["id"] and _entry()["test"]["passed"] == 3


def test_a_failing_run_is_kept_and_publish_says_why_it_may_not(world):
    world["ok"] = False
    got = P.run_tests(NET, "of_versions", "1.0.0", actor=ACTOR, actor_verified=VERIFIED)
    assert got["ok"] is False and got["entry"]["failed"] == 1
    p = P.preview(NET, "of_versions", "1.0.0", viewer=ACTOR)
    assert p["may"] is False and "its last test run did not pass (1 failed, 0 errors)" in p["why"]


def test_no_controller_python_recorded_runs_nothing_and_says_so(world, monkeypatch):
    monkeypatch.setattr(P, "_python", lambda network: (None, "nothing recorded for Default"))
    got = P.run_tests(NET, "of_versions", "1.0.0", actor=ACTOR, actor_verified=VERIFIED)
    assert got["ok"] is False and world["runs"] == []
    assert got["error"] == "can't tell which Python to run its tests on: nothing recorded for " \
                           "Default"


def test_a_run_over_another_hash_is_never_this_version_s(world):
    with pytest.raises(R.Refused, match="is registered at"):
        R.record_test(NET, "of_versions", "1.0.0", {"ok": True, "content_sha256": "f" * 64},
                      actor=ACTOR, actor_verified=VERIFIED)


def test_the_controller_python_is_the_network_s_recorded_one(monkeypatch):
    from modules.apps.python_versions import Target
    from modules.sdn import controller_runtime

    monkeypatch.setattr(controller_runtime, "target",
                        lambda n: Target((3, 5), "Python 3.5.10 on lab9's controller"))
    assert P._python("lab9") == ("3.5", "Python 3.5.10 on lab9's controller")
    monkeypatch.setattr(controller_runtime, "target", lambda n: Target(None, "can't tell"))
    assert P._python("lab9") == (None, "can't tell")


# ── Publish ─────────────────────────────────────────────────────────────────────────────────

def test_a_reviewed_version_with_a_passing_run_is_published_and_deployable(world, tmp_path):
    from modules.jobs.lifecycle import PUBLISHED

    _tested()
    p = P.preview(NET, "of_versions", "1.0.0", viewer=ACTOR)
    assert p["may"] is True and p["author"] == AUTHOR and p["test"]["ok"] is True
    done = P.apply(NET, "of_versions", "1.0.0", p["hash"], actor=ACTOR, actor_verified=VERIFIED,
                   reason="read the logic and its tests")
    assert done["outcome"] == "published", done
    assert done["reviewer"] == ACTOR and done["self_review"] is False
    e = _entry()
    assert e["version"].state == PUBLISHED and e["version"].reviewer == ACTOR
    assert e["publication"]["reason"] == "read the logic and its tests"
    staged = channel.stage_published(e["version"], e["repo"], e["path"], e["rev"],
                                     str(tmp_path / "staged"))
    assert staged["ok"] is True and staged["refusal"] == ""


def test_the_author_publishes_only_where_the_network_s_policy_says_so(world):
    _tested()
    p = P.preview(NET, "of_versions", "1.0.0", viewer=AUTHOR)
    assert p["may"] is False and f"you are its author ({AUTHOR})" in p["why"]
    refused = P.apply(NET, "of_versions", "1.0.0", p["hash"], actor=AUTHOR,
                      actor_verified=VERIFIED, reason="mine")
    assert refused["outcome"] == "refused" and "you are its author" in refused["error"]
    R.set_review(NET, "self_recorded", actor=ACTOR, actor_verified=VERIFIED,
                 loaded="another_person")
    p = P.preview(NET, "of_versions", "1.0.0", viewer=AUTHOR)
    assert p["may"] is True and p["self_review"] is True
    done = P.apply(NET, "of_versions", "1.0.0", p["hash"], actor=AUTHOR,
                   actor_verified=VERIFIED, reason="one person runs this network")
    assert done["outcome"] == "published" and done["self_review"] is True
    assert done["policy"] == "self_recorded" and _entry()["version"].self_review is True


@pytest.mark.parametrize("moved", ["a new run", "the policy"])
def test_what_moved_since_the_preview_publishes_nothing_and_says_so(world, moved):
    _tested()
    p = P.preview(NET, "of_versions", "1.0.0", viewer=ACTOR)
    if moved == "a new run":
        _tested()
    else:
        R.set_review(NET, "self_recorded", actor=ACTOR, actor_verified=VERIFIED)
    got = P.apply(NET, "of_versions", "1.0.0", p["hash"], actor=ACTOR, actor_verified=VERIFIED,
                  reason="r")
    assert got["outcome"] == "refused" and got["moved"] is True
    assert f"confirmed {p['hash'][:12]}" in got["error"]
    assert _entry()["version"].state == "draft"


def test_no_run_and_no_reason_publish_nothing(world):
    p = P.preview(NET, "of_versions", "1.0.0", viewer=ACTOR)
    assert p["may"] is False and "its tests have not been run at this hash" in p["why"]
    _tested()
    p = P.preview(NET, "of_versions", "1.0.0", viewer=ACTOR)
    got = P.apply(NET, "of_versions", "1.0.0", p["hash"], actor=ACTOR, actor_verified=VERIFIED,
                  reason="  ")
    assert got["outcome"] == "refused" and "says why" in got["error"]
    with pytest.raises(R.Refused, match="verified person"):
        R.publish(NET, "of_versions", "1.0.0", content_sha256=p["sha256"], test_id="x",
                  reviewer=ACTOR, reviewer_verified="none", reason="r")


def test_the_folder_read_again_at_the_confirm_must_be_the_one_reviewed(world):
    _tested()
    p = P.preview(NET, "of_versions", "1.0.0", viewer=ACTOR)
    with pytest.raises(R.Refused, match="and the review was of"):
        R.publish(NET, "of_versions", "1.0.0", content_sha256="0" * 64,
                  test_id=p["test"]["id"], reviewer=ACTOR, reviewer_verified=VERIFIED,
                  reason="r")


def test_a_failed_run_is_refused_by_the_record_itself(world):
    world["ok"] = False
    got = P.run_tests(NET, "of_versions", "1.0.0", actor=ACTOR, actor_verified=VERIFIED)
    with pytest.raises(R.Refused, match=r"its test run \S+ did not pass \(1 failed, 0 errors\)"):
        R.publish(NET, "of_versions", "1.0.0", content_sha256=got["run"]["content_sha256"],
                  test_id=got["entry"]["id"], reviewer=ACTOR, reviewer_verified=VERIFIED,
                  reason="r")


def test_a_publication_of_another_hash_is_never_this_pin_s(world):
    import json

    path = R._record_path(NET)
    with open(path, encoding="utf-8") as fh:
        rec = json.load(fh)
    rec["versions"][0]["publication"] = {"content_sha256": "e" * 64, "reviewer": ACTOR,
                                         "self_review": False, "at": "2026-11-09T00:00:00Z"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    e = _entry()
    assert e["version"].state == "draft" and e["publication"] is None


def test_a_fetch_that_moves_the_folder_makes_it_a_draft_again(world, code):  # noqa: F811
    _tested()
    p = P.preview(NET, "of_versions", "1.0.0", viewer=ACTOR)
    assert P.apply(NET, "of_versions", "1.0.0", p["hash"], actor=ACTOR,
                   actor_verified=VERIFIED, reason="r")["outcome"] == "published"
    commit_tested(code, body="x = 2\n")
    assert fetch()["ok"]
    e = _entry()
    assert e["version"].state == "draft" and e["publication"] is None and e["test"] is None


# ── Who may publish ─────────────────────────────────────────────────────────────────────────

def test_the_policy_defaults_to_another_person_and_is_set_by_a_verified_person(world):
    assert R.review_policy(NET)["value"] == "another_person"
    with pytest.raises(R.Refused, match="verified person"):
        R.set_review(NET, "self_recorded", actor=ACTOR, actor_verified="none")
    with pytest.raises(R.Refused, match="not 'everyone'"):
        R.set_review(NET, "everyone", actor=ACTOR, actor_verified=VERIFIED)
    with pytest.raises(R.Refused, match="moved since the card drew it"):
        R.set_review(NET, "self_recorded", actor=ACTOR, actor_verified=VERIFIED,
                     loaded="self_recorded")
    got = R.set_review(NET, "self_recorded", actor=ACTOR, actor_verified=VERIFIED,
                       loaded="another_person")
    assert got == {"ok": True, "before": "another_person", "after": "self_recorded",
                   "unchanged": False}
    assert R.review_policy(NET)["words"].startswith("its author too")


# ── The routes and the card ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client(world, monkeypatch):
    import app as A

    heard = []
    monkeypatch.setattr("modules.invalidation.announce",
                        lambda keys, by, ok=True: heard.append((tuple(keys), by)))
    c = A.app.test_client()
    c.heard = heard
    return c


def _form(**extra):
    return dict({"list": NET, "app": "of_versions", "version": "1.0.0"}, **extra)


def publish_preview(c):
    return c.post("/v2/sdn/apps/version/publish/preview", data=_form())


def test_run_its_tests_then_review_and_publish_through_the_routes(client):
    r = client.post("/v2/sdn/apps/version/test", data=_form())
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "<strong>3 passed</strong> on Python 3.5" in html, html
    assert ("code_repo",) in [k for k, _by in client.heard]
    html = publish_preview(client).get_data(as_text=True)
    assert "Publish of_versions 1.0.0" in html and "you may publish it" in html
    hash_ = re.search(r'name="hash" value="([0-9a-f]{64})"', html).group(1)
    r = client.post("/v2/sdn/apps/version/publish/confirm",
                    data=_form(hash=hash_, reason="read it"))
    done = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and "Published of_versions 1.0.0" in done, done
    # The verified person is the test client's own (the suite's identity), never the form's.
    assert _entry()["version"].state == "published"
    assert _entry()["version"].reviewer == "test-person@example.invalid"
    assert client.heard[-1] == (R.ANNOUNCE_KEYS, R.ANNOUNCER), "every page listing it redraws"


def test_a_confirm_with_no_hash_or_a_stale_one_publishes_nothing(client):
    client.post("/v2/sdn/apps/version/test", data=_form())
    r = client.post("/v2/sdn/apps/version/publish/confirm", data=_form(reason="r"))
    assert r.status_code == 400 and "carries no preview hash" in unescape(r.get_data(as_text=True))
    r = client.post("/v2/sdn/apps/version/publish/confirm",
                    data=_form(hash="a" * 64, reason="r"))
    assert r.status_code == 409 and "moved since the preview" in unescape(r.get_data(as_text=True))
    assert _entry()["version"].state == "draft"


def test_a_version_not_registered_is_refused_with_no_confirm(client):
    r = client.post("/v2/sdn/apps/version/publish/preview", data=_form(version="9.9.9"))
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 409 and "9.9.9 is not registered" in html
    assert "publish/confirm" not in html
    # The effect of the press: nothing is recorded, and nothing is announced.
    assert _entry()["version"].state == "draft" and _entry()["test"] is None
    assert client.heard == []


def test_the_code_repository_card_sets_who_may_publish(client):
    r = client.post(f"/v2/settings/network/{NET}/code-review",
                    data={"review": "self_recorded", "loaded_review": "another_person"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and "are published by its author too" in html, html
    assert R.review_policy(NET)["value"] == "self_recorded"
    r = client.post(f"/v2/settings/network/{NET}/code-review",
                    data={"review": "another_person", "loaded_review": "another_person"})
    assert r.status_code == 409 and "moved since the card drew it" in unescape(
        r.get_data(as_text=True))
    assert R.review_policy(NET)["value"] == "self_recorded"
