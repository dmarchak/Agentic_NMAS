"""C1693 (b), the operator's order of 2026-10-27: committed intent round-trips through Mercury's
serialiser, checked in two places, because the intent files live in each network's config
repository on the host, not in this code repository.

1. **This repository's fixtures** (CI): every intent document under tests/fixtures (a YAML
   mapping naming a `hostname` and its `interfaces`, the property, not a folder) round-trips
   through `hostvars.to_yaml`, but the one planted on purpose,
   `committed/r2_hand_formatted.yml`, which the scan must find. A floor on the population, and a
   planted file in a temporary folder found too.
2. **Each network's committed intent** (Mercury, at run time): the intent-format reader judges
   every `host_vars/*.yml` at HEAD, keeping each blob's verdict by its sha, and Needs
   attention raises a row per hand-formatted device naming it, its network, the action
   (Normalise on its Intent tab) and how it clears (a normalising commit).
And every intent write path saves in the canonical format (part (a)): a hand-formatted input is
committed canonical by the editor's commit, feature 7's commit (the patch's path), bulk intent,
a restore's record and the extraction writer, and nothing else changes.
"""

import os
import subprocess

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
COMMITTED = os.path.join(FIXTURES, "committed")
#: The fixture planted on purpose: r2's real intent laid out by hand (C1693's own tests).
PLANTED = "committed/r2_hand_formatted.yml"


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def intent_documents(root: str) -> dict:
    """``{relative path: text}`` for every intent document under *root*: a ``.yml``/``.yaml``
    file whose YAML is a mapping naming a ``hostname`` and its ``interfaces``."""
    out = {}
    for folder, _dirs, files in os.walk(root):  # disk walk: the planted case's tmp folder is untracked; the fixtures hold no worktree
        for name in files:
            if not name.endswith((".yml", ".yaml")):
                continue
            path = os.path.join(folder, name)
            text = _text(path)
            try:
                doc = yaml.safe_load(text)
            except yaml.YAMLError:
                continue
            if isinstance(doc, dict) and "hostname" in doc and "interfaces" in doc:
                out[os.path.relpath(path, root).replace(os.sep, "/")] = text
    return out


def not_round_tripping(docs: dict) -> list:
    from modules.nsot import hostvars
    return sorted(p for p, text in docs.items() if not hostvars.round_trips(text))


class TestTheFixtures:
    def test_every_intent_fixture_round_trips_but_the_planted_one(self):
        docs = intent_documents(FIXTURES)
        assert len(docs) >= 3, sorted(docs)          # the floor: r2, s1, and the planted r2
        assert not_round_tripping(docs) == [PLANTED], (
            "an intent fixture that does not round-trip through hostvars.to_yaml: Mercury "
            "commits intent in its own formatting since C1693, so a fixture of committed "
            "intent is that formatting (or is planted, named here)")

    def test_a_planted_file_is_found(self, tmp_path):
        from modules.nsot import hostvars
        real = _text(os.path.join(COMMITTED, "s1.yml"))
        (tmp_path / "ok.yml").write_text(real)
        (tmp_path / "hand.yml").write_text("# a note\n" + real)
        (tmp_path / "not-intent.yml").write_text("sections: {}\n")
        docs = intent_documents(str(tmp_path))
        assert sorted(docs) == ["hand.yml", "ok.yml"]
        assert not_round_tripping(docs) == ["hand.yml"]
        assert hostvars.round_trips(real)


# ── part 2: the reader and its Needs attention row ─────────────────────────────

def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A network's config repository holding r2's intent hand-formatted and s1's canonical."""
    path = str(tmp_path / "config_repo")
    os.makedirs(os.path.join(path, "host_vars"))
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    for host, name in (("r2", "r2_hand_formatted.yml"), ("s1", "s1.yml")):
        with open(os.path.join(path, "host_vars", f"{host}.yml"), "w", encoding="utf-8") as fh:
            fh.write(_text(os.path.join(COMMITTED, name)))
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "intent")
    return path


class TestTheReader:
    def test_it_names_the_hand_formatted_device(self, repo):
        from modules.readers import intent_format
        got = intent_format.judge(repo)
        assert got["hand"] == ["r2"]
        assert sorted(f["device"] for f in got["files"]) == ["r2", "s1"]
        assert got["read"] == 2 and got["head"] == _git(repo, "rev-parse", "HEAD")

    def test_a_blob_judged_before_is_not_read_again(self, repo):
        """The work counted: a cycle with nothing committed reads no document."""
        from modules.readers import intent_format
        first = intent_format.judge(repo)
        again = intent_format.judge(repo, first["blobs"])
        assert again["read"] == 0 and again["hand"] == ["r2"]

    def test_a_normalising_commit_clears_it(self, repo):
        from modules.nsot import hostvars
        from modules.readers import intent_format
        path = os.path.join(repo, "host_vars", "r2.yml")
        first = intent_format.judge(repo)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(hostvars.canonical(_text(path)))
        _git(repo, "commit", "-q", "-am", "normalise r2")
        again = intent_format.judge(repo, first["blobs"])
        assert again["hand"] == [] and again["read"] == 1

    def test_a_working_file_nobody_committed_is_not_read(self, repo):
        """Reads git at HEAD, never a working file (C104)."""
        from modules.readers import intent_format
        with open(os.path.join(repo, "host_vars", "s1.yml"), "a", encoding="utf-8") as fh:
            fh.write("# uncommitted\n")
        assert intent_format.judge(repo)["hand"] == ["r2"]

    def test_a_repository_git_cannot_read_raises(self, tmp_path):
        from modules.readers import intent_format
        with pytest.raises(RuntimeError, match="rev-parse"):
            intent_format.judge(str(tmp_path))

    def test_each_network_is_judged_and_a_failure_is_said_per_network(self, repo, monkeypatch,
                                                                     tmp_path):
        from modules.readers import intent_format
        monkeypatch.setattr(intent_format, "_repo_for",
                            lambda name: repo if name == "Lab" else str(tmp_path / "none"))
        got = intent_format.read(lists=["Lab", "Gone"], previous={})
        assert got["lists"]["Lab"]["hand"] == ["r2"]
        assert "rev-parse" in got["lists"]["Gone"]["error"]


def _stored(value):
    return {"state": "ok", "doc": {"last_good": {"value": value,
                                                 "value_at": "2026-10-27T08:00:00Z"},
                                   "stale_after_seconds": 900}}


class TestTheRow:
    def test_one_row_per_hand_formatted_device_naming_the_action(self, repo):
        from modules import attention as A
        from modules.readers import intent_format
        got = A.intent_format_source(cached=_stored(
            {"lists": {"Lab": intent_format.judge(repo)}}))
        rows = got["rows"]
        assert [r["kind"] for r in rows] == ["hand"] and rows[0]["devices"] == ["r2"]
        r = rows[0]
        assert "r2's committed intent is hand-formatted" in r["what"]
        assert "Normalise the formatting" in r["action"]["label"]
        assert r["action"]["href"] == "/v2/device/r2?tab=intent&normalise=1&list=Lab"
        assert r["clears"]["ways"] == ["resolves"] and "Mercury's own formatting" in \
            r["clears"]["when"]
        assert "2 committed intent document(s) in 1 network(s), 1 hand-formatted" in \
            got["checked"]

    def test_no_row_when_every_document_round_trips(self):
        from modules import attention as A
        got = A.intent_format_source(cached=_stored({"lists": {"Lab": {
            "head": "abc", "blobs": {"b1": True}, "files": [{"device": "s1", "blob": "b1"}],
            "hand": [], "read": 0}}}))
        assert got["rows"] == [] and got["state"] == "read"

    def test_an_unreadable_network_is_a_row_never_nothing(self):
        from modules import attention as A
        got = A.intent_format_source(cached=_stored({"lists": {
            "Lab": {"head": "abc", "blobs": {}, "files": [], "hand": []},
            "Gone": {"error": "RuntimeError: git rev-parse HEAD failed"}}}))
        assert [r["kind"] for r in got["rows"]] == ["unreadable"]
        assert "Gone" in got["rows"][0]["what"] and got["rows"][0]["level"] == "unknown"

    def test_a_reader_that_never_stored_is_the_source_unreadable(self):
        from modules import attention as A
        got = A.intent_format_source(cached={"state": "ok", "doc": {}})
        assert got["state"] == "unreadable"


# ── part (a): every intent write path saves in the canonical format ─────────────

class TestEveryWritePathIsCanonical:
    """Each path, given r2's intent laid out by hand, commits Mercury's own formatting of it:
    the same document, and only that device's file changes."""

    HAND = _text(os.path.join(COMMITTED, "r2_hand_formatted.yml"))
    CANONICAL = _text(os.path.join(COMMITTED, "r2.yml"))

    def test_the_editor_s_write(self, tmp_path):
        """`write_committed_text`: the editor's commit, feature 7's (through it), bulk intent's
        and a restore's record all write through it."""
        from modules.nsot import hostvars
        path = hostvars.write_committed_text(str(tmp_path), "r2", self.HAND)
        assert _text(path) == self.CANONICAL
        assert os.listdir(os.path.dirname(path)) == ["r2.yml"]

    def test_a_restore_s_record(self, tmp_path):
        from modules.nsot import hostvars
        path = hostvars.write_committed_text(str(tmp_path), "r2", self.HAND,
                                             judge_descriptions=False)
        assert _text(path) == self.CANONICAL

    def test_the_extraction_writer(self, tmp_path):
        """`write_committed`: seed, onboarding, adopt's intent, a decline, IP SLA's policy,
        a rotation's intent and a revert write a parsed document through `to_yaml`."""
        from modules.nsot import hostvars
        path = hostvars.write_committed(str(tmp_path), hostvars.from_yaml(self.HAND))
        assert _text(path) == self.CANONICAL

    def test_nothing_else_changes(self, tmp_path):
        from modules.nsot import hostvars
        path = hostvars.write_committed_text(str(tmp_path), "r2", self.HAND)
        assert hostvars.from_yaml(_text(path)) == hostvars.from_yaml(self.HAND)

    def test_a_secrets_block_is_refused_never_dropped(self, tmp_path):
        from modules.nsot import hostvars
        # Refused by the leak check before the serialiser is asked (a secrets block holds
        # values), and by `canonical` too if it were not: never written without it.
        with pytest.raises(ValueError):
            hostvars.write_committed_text(str(tmp_path), "s9",
                                          "hostname: s9\nsecrets:\n  community: x\n")
        with pytest.raises(ValueError, match="would change what it says"):
            hostvars.canonical("hostname: s9\nsecrets:\n  community: x\n")
        assert not os.path.exists(hostvars.committed_path(str(tmp_path), "s9"))

    def test_a_secret_spelled_in_escapes_is_refused_in_the_text_written(self, tmp_path,
                                                                         monkeypatch):
        """The text given hides a stored value in YAML escapes (printable ASCII, so allowed
        through); Mercury's formatting writes it plainly, and the leak check on the text
        WRITTEN refuses it, writing nothing."""
        from modules import credentials
        from modules.nsot import hostvars
        values = {"s1:snmp_community_ro": "Str0ngC0mmunityValue"}
        monkeypatch.setattr(credentials, "get_template_secret",
                            lambda name: values.get(name, ""))
        monkeypatch.setattr(credentials, "list_template_secrets",
                            lambda: [{"name": n, "secret_kind": "plaintext",
                                      "rotatable": True} for n in values])
        hidden = "".join(f"\\x{ord(c):02x}" for c in values["s1:snmp_community_ro"])
        text = f'hostname: s1\nbanner: "{hidden}"\n'
        assert hostvars.from_yaml(text)["banner"] == values["s1:snmp_community_ro"]
        with pytest.raises(hostvars.SecretLeak):
            hostvars.write_committed_text(str(tmp_path), "s1", text)
        assert not os.path.exists(hostvars.committed_path(str(tmp_path), "s1"))

    @staticmethod
    def writers(files: dict) -> set:
        """``{(path, function)}``: each function that opens a file for writing and names a
        committed intent path (`hostvars.committed_path`, or `committed_path` inside
        hostvars itself), parsed, never matched as text. *files*: ``{path: source}``."""
        import ast

        out = set()
        for rel, text in files.items():
            here = rel == "modules/nsot/hostvars.py"
            for fn in ast.walk(ast.parse(text)):
                if not isinstance(fn, ast.FunctionDef):
                    continue
                calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
                writes = any(getattr(c.func, "id", "") == "open" and any(
                    isinstance(a, ast.Constant) and a.value in ("w", "wb", "a")
                    for a in c.args[1:2]) for c in calls)
                names = any(
                    (isinstance(c.func, ast.Attribute) and c.func.attr == "committed_path"
                     and getattr(c.func.value, "id", "") == "hostvars")
                    or (here and getattr(c.func, "id", "") == "committed_path")
                    for c in calls)
                if writes and names:
                    out.add((rel, fn.name))
        return out

    def test_no_other_writer_of_committed_intent(self):
        """The population: every function in modules/ and routes/ that writes a file at a
        committed intent path is `write_committed` or `write_committed_text`, or a put-back
        of HEAD's own text after a failed commit."""
        allowed = {("modules/nsot/hostvars.py", "write_committed"),
                   ("modules/nsot/hostvars.py", "write_committed_text"),
                   # Put-backs: each writes HEAD's own text back after a failed commit.
                   ("modules/nsot/bulk_intent.py", "_put_back")}
        from tests.source_index import tracked

        files = {os.path.relpath(path, ROOT).replace(os.sep, "/"): _text(path)
                 for path in tracked("modules", "routes", suffix=".py")}
        found = self.writers(files)
        assert {("modules/nsot/hostvars.py", "write_committed"),
                ("modules/nsot/hostvars.py", "write_committed_text")} <= found, \
            "the scan finds the writers it allows"
        assert found <= allowed, sorted(found - allowed)

    def test_a_planted_writer_is_found(self):
        planted = {"modules/x.py": (
            "def sneak(repo, host, text):\n"
            "    with open(hostvars.committed_path(repo, host), 'w') as fh:\n"
            "        fh.write(text)\n")}
        assert self.writers(planted) == {("modules/x.py", "sneak")}
