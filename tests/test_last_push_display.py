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

Today's Remote card, which these tests executed, left at 7.8 (2026-10-17, P7-21), and
History › Remote set-up… had drawn the last push's when and who alone. The card now carries
it (`remote_setup._last_push`), and these tests render the real card through the app on a
temporary store, reading its Last push fact.
"""

import re

import pytest

from modules.nsot import remote as R
from tests.test_remote_setup_v2 import BASE, _connected, _get
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)


def render(networks, last_push):  # noqa: F811
    """The card's Last push fact for *last_push* as recorded, as its HTML."""
    _connected(networks)
    R.update_remote("Branch", lambda c: c.__setitem__("last_push", last_push))
    _r, card = _get(networks, f"{BASE}?list=Branch")
    return card.split("<dt>Last push</dt><dd>", 1)[1].split("</dd>", 1)[0]


def text_of(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


MANUAL_COMMIT = {"at": "2026-09-22T18:50:32Z", "by": "operator@example.com",
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
    def test_a_commit_push_names_its_commit(self, networks):  # noqa: F811
        """The case that showed only a timestamp and an actor."""
        out = text_of(render(networks, MANUAL_COMMIT))
        assert "commit 24438924" in out, out

    def test_a_tag_only_push_says_tag_only_and_names_the_tag(self, networks):  # noqa: F811
        out = text_of(render(networks, AUTO_TAG_ONLY))
        assert "tag only: baseline/20260922T172405Z" in out, out

    def test_a_commit_push_also_names_its_tags(self, networks):  # noqa: F811
        out = text_of(render(networks, AUTO_COMMIT))
        assert "commit abcdef12 + golden/s1/20260922T100000Z" in out, out

    def test_a_commit_with_no_tags_says_nothing_about_tags(self, networks):  # noqa: F811
        """A host_vars commit creates no tags by design; an empty list must not render as an
        empty addition."""
        out = text_of(render(networks, MANUAL_COMMIT))
        assert out.endswith("commit 24438924"), out


class TestItSaysHowItWasPublished:
    """"who last clicked" versus "what was last published" is the distinction
    that made this field misleading."""

    def test_a_person_reads_as_manual(self, networks):  # noqa: F811
        assert '<span class="badge badge-neutral">manual</span>' in render(networks, MANUAL_COMMIT)

    def test_the_hook_reads_as_auto(self, networks):  # noqa: F811
        assert '<span class="badge badge-neutral">auto</span>' in render(networks, AUTO_TAG_ONLY)

    def test_the_actor_is_still_named(self, networks):  # noqa: F811
        assert "by operator@example.com" in text_of(render(networks, MANUAL_COMMIT))


class TestEdges:
    def test_never_pushed(self, networks):  # noqa: F811
        _connected(networks)
        _r, card = _get(networks, f"{BASE}?list=Branch")
        assert "<dt>Last push</dt><dd>none yet</dd>" in card

    def test_a_record_with_no_kind_or_commit_says_so(self, networks):  # noqa: F811
        """Older records predate 1.2b. They must not render as a confident blank."""
        out = render(networks, {"at": "2026-09-21T19:57:47Z", "by": "operator@example.com"})
        assert "2026-09-21T19:57:47Z" in out and text_of(out).endswith(": unknown"), out

    @pytest.mark.parametrize("payload", (MANUAL_COMMIT, AUTO_TAG_ONLY, AUTO_COMMIT))
    def test_the_timestamp_is_always_shown(self, networks, payload):  # noqa: F811
        assert payload["at"] in render(networks, payload)

    def test_values_are_escaped(self, networks):  # noqa: F811
        """The actor comes from a verified claim, but the tag list comes from the repository
        and the commit from git output."""
        out = render(networks, {"at": "x", "by": "a<script>b", "kind": "commit",
                                "commit": "deadbeef", "tags": ["<t>"]})
        assert "<script>" not in out and "<t>" not in out
        assert "a&lt;script&gt;b" in out and "&lt;t&gt;" in out
