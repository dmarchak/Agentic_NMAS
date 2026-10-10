"""Templates › Seed the library… on v2 (cutover blocker 5, 2026-10-10): a network with no
committed template (one created on v2 starts so) is told so and offered the shipped library;
the preview lists the files it adds and writes nothing; the confirm commits them as the person
in one commit, never overwriting a file, bound to the shipped library previewed.
"""

import re
import subprocess

import pytest


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout


@pytest.fixture
def bare(tmp_path, monkeypatch):
    """A network `Lab` whose repository holds no template."""
    import app as A
    from modules.nsot import repo as R

    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {"nsot_git_author_name": "NMAS",
                                                   "nsot_git_author_email": "nmas@localhost"
                                                   }.get(key, default))
    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    repo = str(list_dir / "config_repo")
    R.init_repo(repo)
    return {"repo": repo, "client": A.app.test_client()}


def test_an_empty_library_is_said_and_seeding_offered(bare):
    html = bare["client"].get("/v2/templates?list=Lab").get_data(as_text=True)
    assert "has no committed configuration template" in html
    assert 'hx-get="/v2/templates/seed?list=Lab"' in html and "Seed the library…" in html
    assert "today&#39;s Templates page" not in html and "today's Templates page" not in html


def test_the_preview_lists_what_it_adds_and_writes_nothing(bare):
    from modules.nsot import templates_repo

    head = _git(bare["repo"], "rev-parse", "HEAD")
    html = bare["client"].get("/v2/templates/seed?list=Lab").get_data(as_text=True)
    for f in templates_repo.seed_paths():
        assert f'<span class="mono">{f}</span>' in html, f
    assert _git(bare["repo"], "rev-parse", "HEAD") == head
    assert not templates_repo.list_templates(bare["repo"]), "a preview seeded the library"


def test_the_confirm_commits_them_as_the_person(bare):
    from modules.nsot import approve_op, templates_repo

    html = bare["client"].get("/v2/templates/seed?list=Lab").get_data(as_text=True)
    sig = re.search(r'name="signature" value="([^"]*)"', html).group(1)
    r = bare["client"].post("/v2/templates/seed", data={"list": "Lab", "signature": sig})
    out = r.get_data(as_text=True)
    assert r.status_code == 200, out[:600]
    msg = _git(bare["repo"], "log", "-1", "--format=%B")
    assert msg.startswith("template: seed library (")
    assert "Actor: test-person@example.invalid" in msg
    assert set(approve_op.committed_templates(bare["repo"])) == \
        {p for p in templates_repo.seed_paths() if p.endswith(".j2")}
    assert "seeded" in out and "Approve each template" in out


def test_a_shipped_library_changed_since_the_preview_is_refused(bare):
    head = _git(bare["repo"], "rev-parse", "HEAD")
    r = bare["client"].post("/v2/templates/seed", data={"list": "Lab", "signature": "0" * 16})
    assert r.status_code == 409 and "changed since your preview" in r.get_data(as_text=True)
    assert _git(bare["repo"], "rev-parse", "HEAD") == head


@pytest.mark.real_identity
def test_seeding_needs_a_person(bare):
    r = bare["client"].post("/v2/templates/seed", data={"list": "Lab", "signature": "x"})
    assert r.status_code in (401, 403)
