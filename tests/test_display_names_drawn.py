"""No v2 response draws a person's identity outside a collapsed record (board E2a; the
operator, 2026-11-11: display names ship before a screen is recorded).

**The population, by property:** every HTML response the v2 walk receives
(tests/v2_context.py's measurement: every page tests/interface_pages.py reaches from its
starts, every fragment a page or a fragment asks for, and every request its providers make,
GET and POST, with their planted records), read once by tests/people_drawn.py as each response
arrives. **A person's identity** is an email-shaped word under a documentation domain, the only
kind a test may plant (tests/test_nothing_personal_is_published.py), so the walk's viewer and
every actor its lab and providers plant is one: an operation's actor, a policy's setter in a
heal's recorded step words ("as the policy set by <identity>, holding <device>"), an
acknowledgement's, a Grafana silence's author, an AI call's, a commit's.

**What it assumes stays true:** a test plants a person under a documentation domain (held by
the publication test); a response the walk never makes is not read (the walk's own floors,
tests/test_v2_context_is_drawn.py, hold what it reaches); an identity the page builds in the
browser is not seen (v2 draws on the server). What is NOT a person, and is left: an address in
a captured device configuration (another domain), and a setting's own value drawn by an element
that says so (``data-address``: a notification's destination).

The scan is shown able to see: planted pages, each drawing an identity in one way a page can,
are each found; a collapsed record and a declared destination are not.
"""

import pytest

from tests import v2_context as V2
from tests.people_drawn import RECORD_CLASSES, addresses, scan

PERSON = "person@example.invalid"


@pytest.fixture(scope="module")
def walked():
    """The walk's measurement, once per test process (`V2.measure` keeps it)."""
    return V2.measure()


class TestEveryResponse:
    def test_the_walk_read_its_responses_and_reached_records(self, walked):
        # 1763 HTML responses read on 2026-11-11 (the walk's pages, fragments and providers):
        # a walk that stopped reading most of them would fall below this.
        assert walked["bodies"] >= 1500, walked["bodies"]
        # 17 of them kept an identity inside a collapsed record on 2026-11-11 (the Display
        # names card's rows, History's "the identity as recorded", an AI call's folded parts):
        # a scan that stopped seeing records, or a walk that planted no person, would fall
        # below this.
        assert walked["records"] >= 12, walked["records"]

    def test_none_draws_an_identity_outside_a_collapsed_record(self, walked):
        found = sorted(
            f"{route} [{templates}] draws {identity} in {where}: “{words}”"
            for (route, templates), hits in walked["addresses"].items()
            for identity, where, words in hits)
        assert found == [], (
            f"{len(found)} place(s) draw a person's identity on the page. Draw the person by "
            "display name (the `people` filter where the template draws a recorded actor or "
            "recorded words; `identity.display_name` in the code that builds a page's words), "
            "or keep the identity inside a collapsed record "
            f"(a closed <details> of class {', '.join(RECORD_CLASSES)}):\n" + "\n".join(found))


class TestTheScanSees:
    """Each way a page can draw an identity, planted: found, with where it is."""

    @pytest.mark.parametrize("page, where", [
        (f"<p>Recorded by {PERSON}, just now</p>", "p"),
        (f'<span title="Signed in as {PERSON}">p</span>', "span[title]"),
        (f'<form><input type="hidden" name="person" value="{PERSON}"></form>',
         "form > input[value]"),
        (f'<a href="/v2/history?person={PERSON}">theirs</a>', "a[href]"),
        (f"<pre>12:00:01 start: started by {PERSON}, every 10 s</pre>", "pre"),
        # A row a person opens is still the page: only a record class is a record.
        (f'<details class="att"><summary>r3</summary><p>by {PERSON}</p></details>',
         "details > p"),
        # A record the server drew open is on the screen.
        (f'<details class="id-record" open><summary>s</summary>{PERSON}</details>', "details"),
        # A record's own summary is its line, drawn while it is closed.
        (f'<details class="id-record"><summary>By {PERSON}</summary>x</details>',
         "details > summary"),
        # After a record closes, the page goes on.
        (f'<details class="id-record"><summary>s</summary>{PERSON}</details><p>{PERSON}</p>',
         "p"),
        (f"<li>as the policy set by {PERSON}, holding r3</li>", "li")])
    def test_a_planted_identity_is_found(self, page, where):
        found = addresses(f"<html><body>{page}</body></html>")
        assert [(i, w.split("body > ")[-1]) for i, w, _words in found] == [(PERSON, where)]

    def test_the_words_around_it_are_said(self):
        (hit,) = addresses(f"<p>Recorded by {PERSON}, just now</p>")
        assert hit[2] == f"Recorded by {PERSON}, just now"

    @pytest.mark.parametrize("page", [
        f'<details class="id-record"><summary>The verified identity</summary>{PERSON}</details>',
        f'<details class="tl-record-d small"><summary>Details</summary><dl><dd title="{PERSON}">'
        f"by {PERSON}</dd></dl></details>",
        f'<details class="hist-ai-part"><summary>the data</summary><pre>{PERSON}</pre></details>'])
    def test_a_collapsed_record_keeps_it(self, page):
        drawn, kept = scan(f"<html><body>{page}</body></html>")
        assert drawn == [] and kept and all(i == PERSON for i, _w, _a in kept)

    def test_a_declared_destination_is_a_setting_s_value(self):
        page = (f'<td><span data-address="destination">{PERSON}</span></td>'
                f'<input data-address="destination" aria-label="Code for {PERSON}">')
        assert scan(page) == ([], [])

    def test_a_captured_configuration_s_own_address_is_not_a_person(self):
        """The assumption, stated: only a documentation domain is a planted person."""
        vendor = "call-home@" + "vendor-domain.net"
        assert addresses(f"<pre>contact-email-addr {vendor}</pre>") == []
        assert addresses("<p>git@host.example:group/repo.git</p>") != [], \
            "an address-shaped word under a documentation domain is read as one"


class TestRecordedWordsAreDrawnByDisplayName:
    def test_a_heal_s_step_words_name_the_setter_by_display_name(self):
        """The planted step the walk's heal run draws (tests/fixtures/heal_run): recorded with
        the setter's identity, drawn with their name; the recorded step is not rewritten."""
        from modules.heal import run_card

        steps = [{"step": "take", "result": "ok",
                  "words": f"taken by heal to intent (policy set by {PERSON})"},
                 {"step": "apply", "result": "ok", "at": "2026-11-11T00:00:00Z",
                  "words": f"as the policy set by {PERSON}, holding r3"}]
        drawn = run_card._drawn(steps)
        assert [s["words"] for s in drawn] == [
            "taken by heal to intent (policy set by person)",
            "as the policy set by person, holding r3"]
        assert PERSON in steps[1]["words"], "a copy: the record keeps the identity"
        phase = run_card.act_phase(steps, ended=True)
        assert PERSON not in repr(phase) and "set by person, holding r3" in repr(phase)
