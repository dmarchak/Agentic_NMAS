"""The card must show WHAT was published, not only who clicked.

`last_push` began as a field only the Push button wrote, so it meant "when
somebody last clicked" on a card labelled "last push" (Stage 1.2b). 1.2b made
both push paths record it — and recorded `kind`, `commit` and `tags` so the
card could say what actually went out.

Then the card displayed none of that. `kind` was rendered **only** when it
equalled `'tags'`, and `commit` was never rendered at all, so an ordinary
commit push showed exactly the timestamp and the actor: the same misleading
reading the whole fix existed to end. Recording a fact and not showing it
leaves the card saying the same wrong thing.

These tests **execute** the helper with dukpy rather than inspecting its
source. A structural assertion is what let the `--write` crash ship: it can
confirm the shape of code that cannot run.
"""

import os
import re

import pytest

# NOT importorskip: dukpy is pinned in requirements.txt, and a test that
# skips wherever its dependency is missing protects nothing -- the same
# reasoning `test_inline_javascript.py` records for its node check, which is
# why that file carries a scanner that always runs alongside it.
import dukpy

PARTIAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "templates", "partials", "golden_repo.html")


def _helper_source():
    with open(PARTIAL, encoding="utf-8") as handle:
        text = handle.read()
    esc = text[text.index("function _gEsc"):text.index("function _gList")]
    body = text[text.index("function _gLastPush"):
                text.index("function loadGoldenRepoPanel")]
    return esc + body


def render(payload):
    """Run the real helper and return its HTML."""
    import json

    script = _helper_source() + "\n_gLastPush(%s);" % json.dumps(payload)
    return dukpy.evaljs(script)


def text_of(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


MANUAL_COMMIT = {"at": "2026-09-22T18:50:32Z", "by": "dustnm@gmail.com",
                 "kind": "commit",
                 "commit": "24438924707fa4a55784e2b024aedcf936c85f52",
                 "tags": []}
AUTO_TAG_ONLY = {"at": "2026-09-22T17:24:05Z", "by": "auto-push",
                 "kind": "tags", "commit": "3d1fbf2912ee",
                 "tags": ["baseline/20260922T172405Z"]}
AUTO_COMMIT = {"at": "2026-09-22T10:00:00Z", "by": "auto-push",
               "kind": "commit", "commit": "abcdef1234567890",
               "tags": ["golden/s1/20260922T100000Z"]}


class TestItSaysWhatWasPublished:
    def test_a_commit_push_names_its_commit(self):
        """The case that showed only a timestamp and an actor."""
        out = text_of(render(MANUAL_COMMIT))
        assert "24438924" in out, out
        assert "commit" in out

    def test_a_tag_only_push_says_tag_only(self):
        out = text_of(render(AUTO_TAG_ONLY))
        assert "tag only" in out

    def test_a_tag_only_push_names_the_tag(self):
        assert "baseline/20260922T172405Z" in text_of(render(AUTO_TAG_ONLY))

    def test_a_commit_push_also_names_its_tags(self):
        out = text_of(render(AUTO_COMMIT))
        assert "abcdef12" in out
        assert "golden/s1/20260922T100000Z" in out

    def test_a_commit_with_no_tags_says_nothing_about_tags(self):
        """A host_vars commit creates no tags by design; an empty list must
        not render as an empty code block."""
        out = render(MANUAL_COMMIT)
        assert "<code></code>" not in out


class TestItSaysHowItWasPublished:
    """"who last clicked" versus "what was last published" is the distinction
    that made this field misleading."""

    def test_a_person_reads_as_manual(self):
        assert "manual" in text_of(render(MANUAL_COMMIT))

    def test_the_hook_reads_as_auto(self):
        assert "auto" in text_of(render(AUTO_TAG_ONLY))

    def test_the_two_are_distinguishable(self):
        assert text_of(render(MANUAL_COMMIT)).split()[1] != \
            text_of(render(AUTO_TAG_ONLY)).split()[1]

    def test_the_actor_is_still_named(self):
        assert "dustnm@gmail.com" in text_of(render(MANUAL_COMMIT))


class TestEdges:
    def test_never_pushed(self):
        assert text_of(render(None)) == "never"

    def test_a_record_with_no_kind_or_commit_says_so(self):
        """Older records predate 1.2b. They must not render as a confident
        blank."""
        out = text_of(render({"at": "2026-09-21T19:57:47Z",
                              "by": "dustnm@gmail.com"}))
        assert "2026-09-21T19:57:47Z" in out
        assert "unknown" in out

    def test_the_timestamp_is_always_shown(self):
        for payload in (MANUAL_COMMIT, AUTO_TAG_ONLY, AUTO_COMMIT):
            assert payload["at"] in text_of(render(payload))

    def test_values_are_escaped(self):
        """The actor comes from a verified claim, but the tag list comes from
        the repository and the commit from git output."""
        out = render({"at": "x", "by": "a<script>b", "kind": "commit",
                      "commit": "deadbeef", "tags": []})
        assert "<script>" not in out
        assert "&lt;script&gt;" in out
