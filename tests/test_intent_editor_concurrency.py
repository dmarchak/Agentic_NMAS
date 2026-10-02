"""The intent editor saves against the version the person opened (CONCURRENCY_AUDIT R2).

Two people editing r2's intent: the last writer won, silently. The editor's GET returned
only the text, the save sent `{yaml, summary}`, the file was written before the repository
lock and committed after it, so a person who opened the document before another person's
commit put their whole document back over it, and both saw success. The save also skipped
the preview's unknown-interface-key check, and an unchanged save drew "Committed ."

Now, through the real routes against a real repository:

- the GET hands out ``base``, the blob at HEAD, and the text is that blob's;
- a save whose base is no longer HEAD's blob is refused (409) with nothing written, naming
  both blobs and who moved it, with their change and this edit, each against what was opened;
- a save with no base is refused; a save with the current base commits and hands back the new
  base, so a second save from the same editor works;
- an unchanged save commits nothing and says so;
- the save runs the preview's checks (an unknown interface key is refused);
- the compare, the write and the commit happen under the repository lock: a save waits while
  another holder has it;
- the shipped client sends its base and draws the refusal with both changes.

Expected values come from git directly, never from the helpers under test.
"""

import json
import subprocess
import threading

import dukpy

from tests.payload_render import lift, shipped
from tests.test_intent_editor import world  # noqa: F401  (the fixture)

URL = "/templatize/committed/s4"


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          check=True).stdout


def _head(world):
    return _git(world["repo"], "rev-parse", "HEAD").strip()


def _opened(world):
    body = world["client"].get(URL).get_json()
    return body["yaml"], body["base"]


def _save(world, text, base, summary="an edit"):
    return world["client"].post(URL, json={"yaml": text, "summary": summary, "base": base})


class TestTheGetHandsOutWhatItOpened:
    def test_the_base_is_heads_blob_and_the_text_is_that_blob(self, world):
        text, base = _opened(world)
        assert base == _git(world["repo"], "rev-parse", "HEAD:host_vars/s4.yml").strip()
        assert text == _git(world["repo"], "show", "HEAD:host_vars/s4.yml")


class TestAStaleSaveIsRefused:
    def test_another_persons_commit_since_the_open_refuses_with_nothing_written(self, world):
        text_a, base_a = _opened(world)          # A opens
        text_b, base_b = _opened(world)          # B opens the same version
        assert _save(world, text_b.replace("uplink", "uplink B"), base_b,
                     "B retitles the uplink").get_json()["ok"] is True
        head_after_b = _head(world)
        b_blob = _git(world["repo"], "rev-parse", "HEAD:host_vars/s4.yml").strip()

        out = _save(world, text_a.replace("uplink", "uplink A"), base_a, "A retitles")
        body = out.get_json()
        assert out.status_code == 409 and body["stage"] == "moved"
        # Nothing written: HEAD and the file are B's.
        assert _head(world) == head_after_b
        on_disk = open(f"{world['repo']}/host_vars/s4.yml", encoding="utf-8").read()
        assert "uplink B" in on_disk and "uplink A" not in on_disk
        # Both operands and who moved it.
        assert body["base"] == base_a and body["current"] == b_blob
        assert base_a[:8] in body["error"] and b_blob[:8] in body["error"]
        assert "B retitles the uplink" in body["error"]
        # Each change against what A opened.
        assert "+" in body["their_change"] and "uplink B" in body["their_change"]
        assert "uplink A" in body["your_change"] and "uplink B" not in body["your_change"]

    def test_a_base_not_in_the_repository_still_refuses_and_says_why(self, world):
        text, _ = _opened(world)
        body = _save(world, text.replace("uplink", "x"), "0" * 40).get_json()
        assert body["stage"] == "moved" and "cannot be shown" in body["error"]

    def test_a_save_that_names_no_base_is_refused(self, world):
        text, _ = _opened(world)
        before = _head(world)
        out = world["client"].post(URL, json={"yaml": text.replace("uplink", "x"),
                                              "summary": "no base"})
        assert out.status_code == 400 and out.get_json()["stage"] == "base"
        assert _head(world) == before


class TestASaveFromTheCurrentVersion:
    def test_it_commits_and_hands_back_the_new_base(self, world):
        text, base = _opened(world)
        body = _save(world, text.replace("uplink", "uplink 2"), base).get_json()
        assert body["ok"] is True and body["changed"] is True
        assert body["base"] == _git(world["repo"], "rev-parse",
                                    "HEAD:host_vars/s4.yml").strip()
        # The same editor saves again with what it was handed.
        again = _save(world, text.replace("uplink", "uplink 3"), body["base"]).get_json()
        assert again["ok"] is True and again["commit"]

    def test_an_unchanged_save_commits_nothing_and_says_so(self, world):
        text, base = _opened(world)
        before = _head(world)
        body = _save(world, text, base).get_json()
        assert body["ok"] is True and body["changed"] is False and body["commit"] == ""
        assert "Nothing to commit" in body["message"]
        assert _head(world) == before

    def test_the_save_runs_the_previews_checks(self, world):
        text, base = _opened(world)
        before = _head(world)
        edited = text.replace("description: uplink", "descripton: uplink")
        assert edited != text
        out = _save(world, edited, base)
        assert out.status_code == 400 and out.get_json()["stage"] == "schema"
        assert "descripton" in out.get_json()["error"]
        assert _head(world) == before


class TestTheSaveIsUnderTheRepositoryLock:
    def test_a_save_waits_while_another_holder_has_the_lock(self, world):
        from modules.nsot.repo import repo_lock

        text, base = _opened(world)
        before = _head(world)
        holding, release = threading.Event(), threading.Event()
        result = {}

        def holder():
            with repo_lock(world["repo"]):
                holding.set()
                release.wait(10)

        def saver():
            result["out"] = _save(world, text.replace("uplink", "uplink L"), base).get_json()

        h = threading.Thread(target=holder)
        h.start()
        assert holding.wait(5)
        s = threading.Thread(target=saver)
        s.start()
        s.join(0.6)
        # While the lock is held: nothing written, nothing committed, no answer yet.
        assert s.is_alive() and "out" not in result
        assert _head(world) == before
        assert "uplink L" not in open(f"{world['repo']}/host_vars/s4.yml",
                                      encoding="utf-8").read()
        release.set()
        h.join(10)
        s.join(10)
        assert result["out"]["ok"] is True and _head(world) != before


class TestTheShippedClient:
    SRC = shipped("partials__intent_editor.1.js")

    def test_it_keeps_the_base_it_opened_and_sends_it(self):
        opened = lift(self.SRC, "showIntentEditor")
        assert "_intentBase = d.base" in opened
        save = lift(self.SRC, "commitIntentEdit")
        assert "base: _intentBase" in save and "_intentBase = d.base" in save

    def test_it_draws_the_refusal_with_both_changes(self, world):
        text_a, base_a = _opened(world)
        text_b, base_b = _opened(world)
        _save(world, text_b.replace("uplink", "uplink <B>"), base_b, "B")
        refused = _save(world, text_a.replace("uplink", "uplink A"), base_a).get_json()
        js = lift(self.SRC, "_iEsc") + "\n" + lift(self.SRC, "_intentSaveHtml")
        drawn = dukpy.evaljs(js + f"\n_intentSaveHtml({json.dumps(refused)})")
        assert "text-danger" in drawn["status"] and "Not saved" in drawn["status"]
        assert "What changed since you opened it" in drawn["diff"]
        assert "uplink &lt;B&gt;" in drawn["diff"] and "<B>" not in drawn["diff"]
        assert "Your edit, not saved" in drawn["diff"] and "uplink A" in drawn["diff"]

    def test_it_says_nothing_was_committed_for_an_unchanged_save(self, world):
        text, base = _opened(world)
        body = _save(world, text, base).get_json()
        js = lift(self.SRC, "_iEsc") + "\n" + lift(self.SRC, "_intentSaveHtml")
        drawn = dukpy.evaljs(js + f"\n_intentSaveHtml({json.dumps(body)})")
        assert "Nothing to commit" in drawn["status"] and "Committed" not in drawn["status"]
