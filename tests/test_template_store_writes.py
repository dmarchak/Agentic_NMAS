"""Templates and bindings are replaced whole, and an unreadable bindings file is never a guess
(CONCURRENCY_AUDIT R14, its server half; 2026-10-04).

R14: a template save and a bindings save truncated their file in place, so a render reading it
mid-write saw a part; `load_bindings` read an unreadable file as the DEFAULTS, so a device was
rendered through the wrong template, silently. Now both writes replace the file atomically
(their temp file beside the repository, never in it), and an unreadable `bindings.yml` raises
`BindingsUnreadable`: no template is chosen for any device, and the listing says why.

Not this half: a base blob the editor sends, so a stale editor cannot overwrite a newer save
(that is the v1 editor's JavaScript; recorded on R14).
"""

import os
import threading

import pytest

from modules.nsot import templates_repo as T


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "lab" / "config_repo"
    (path / "templates" / "cisco_ios").mkdir(parents=True)
    return str(path)


def _inside(repo):
    return sorted(os.path.relpath(os.path.join(d, f), repo)
                  for d, _s, files in os.walk(repo) for f in files)


class TestTheBindings:
    def test_absent_is_the_defaults(self, repo):
        assert T.load_bindings(repo)["platforms"]

    def test_unreadable_refuses_naming_the_file(self, repo):
        with open(T.bindings_path(repo), "w", encoding="utf-8") as fh:
            fh.write("platforms: {cisco_ios: [unclosed\n")
        with pytest.raises(T.BindingsUnreadable, match="bindings.yml could not be read"):
            T.load_bindings(repo)
        with pytest.raises(T.BindingsUnreadable):
            T.template_for_device(repo, "s1", "cisco_ios")

    def test_a_document_that_is_not_a_mapping_is_unreadable(self, repo):
        with open(T.bindings_path(repo), "w", encoding="utf-8") as fh:
            fh.write("- just\n- a list\n")
        with pytest.raises(T.BindingsUnreadable):
            T.load_bindings(repo)

    def test_a_save_leaves_nothing_else_in_the_repository(self, repo):
        T.save_bindings(repo, {"platforms": {"cisco_ios": "cisco_ios/base.j2"}, "overrides": {}})
        assert _inside(repo) == [os.path.join("templates", "bindings.yml")]
        assert T.load_bindings(repo)["platforms"] == {"cisco_ios": "cisco_ios/base.j2"}


class TestTheTemplate:
    A = "hostname {{ hostname }}\n" + "! a\n" * 20000
    B = "hostname {{ hostname }}\n" + "! b\n" * 30000

    def test_a_save_leaves_nothing_else_in_the_repository(self, repo):
        assert T.write_template(repo, "cisco_ios/base.j2", self.A)["ok"]
        assert _inside(repo) == [os.path.join("templates", "cisco_ios", "base.j2")]

    def test_a_reader_never_sees_part_of_a_template(self, repo):
        T.write_template(repo, "cisco_ios/base.j2", self.A)
        seen, stop = set(), threading.Event()

        def read():
            while not stop.is_set():
                seen.add(len(T.read_template(repo, "cisco_ios/base.j2")))

        reader = threading.Thread(target=read)
        reader.start()
        try:
            for i in range(60):
                T.write_template(repo, "cisco_ios/base.j2", self.B if i % 2 else self.A)
        finally:
            stop.set()
            reader.join(10)
        assert seen <= {len(self.A), len(self.B)}, sorted(seen)[:5]


def test_the_listing_says_the_bindings_are_unreadable(tmp_path, monkeypatch):
    import app as A
    from routes import templates as troutes
    repo = str(tmp_path / "config_repo")
    os.makedirs(os.path.join(repo, "templates"))
    with open(T.bindings_path(repo), "w", encoding="utf-8") as fh:
        fh.write("platforms: [\n")
    monkeypatch.setattr(troutes, "_active_list", lambda *a: "Lab")
    monkeypatch.setattr(troutes, "_repo_for", lambda *_a: repo)
    r = A.app.test_client().get("/templates")
    assert r.status_code == 409, r.get_data(as_text=True)[:300]
    assert "bindings.yml could not be read" in r.get_json()["error"]
