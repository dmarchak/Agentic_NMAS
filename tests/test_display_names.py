"""Display names, set per person (board E2a; the operator, 2026-11-11: "Display names:
configurable per person; default the part before "@"").

What is held here, on the real store in the test's own data folder, the real filter and the
real route through the Flask client:

- **The default:** the part of a person's identity before the "@", never the domain; a service
  by its label; a host login as it is.
- **The store** (`modules/display_names.py`, `data/display_names.json`): a row per person
  (``name``, ``set_by``, ``actor_verified``, ``at``), owner-only from creation, replaced
  whole; a name returned to the default keeps who returned it; an unreadable store refuses
  the write, is left byte for byte, and every person is drawn by their default.
- **Each refusal names both sides:** an "@", more than 32 printable characters, a character
  that cannot be printed, a name another person has (or their default), a name Mercury uses
  for itself, another person's name changed by someone who is no admin.
- **The filter `people`:** each email-shaped token of a recorded text becomes that person's
  display name; every other word, a typed reason's among them, is left as recorded.
- **The control** (Settings › Installation › Access and identity, `settings_v2.display_name`):
  a person sets their own and every screen draws it (the name chip, the confirm's statement,
  History's line); the response and an announcement name `people`; an admin (every verified
  person, until Mercury holds roles) sets another person's by the key their row carries; a
  service token and a refusal change nothing; the page holds an identity only inside its
  collapsed record.

The heal writers' ``policy_by`` field is held where each writer's own tests drive it
(tests/test_heal_act.py, test_heal_bounce.py, test_heal_session_clear.py); History › Export's
files where its own records are planted (tests/test_history_export.py); the scan of every v2
response is tests/test_display_names_drawn.py.
"""

import json
import os
import re
import stat

import pytest

from tests.conftest import TEST_PERSON
from tests.people_drawn import addresses
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

ALEX = "alex@example.invalid"
SAM = "sam@other.example.invalid"
CARD = "/v2/settings/installation/display-names"


def D():
    from modules import display_names
    return display_names


@pytest.fixture
def store(networks):  # noqa: F811
    """The test's own data folder (the `networks` fixture's), and the file the store keeps."""
    return {"client": networks["client"], "path": str(networks["dir"] / "display_names.json")}


def _set(person, name, by=None, admin=False):
    return D().set_name(person, name, by=by or person, actor_verified="access", admin=admin)


def _refusal(person, name, by=None, admin=False):
    with pytest.raises(D().Refused) as said:
        _set(person, name, by=by, admin=admin)
    return str(said.value)


def _as(monkeypatch, actor, kind="person"):
    """The request's verified identity, as the harness's own default sets it."""
    from modules import identity

    who = identity.Identity(
        actor=actor, email=actor if kind == "person" else "", kind=kind,
        service_id=actor.split(":", 1)[1] if kind == "service" else "", verified=True,
        outcome="ok", peer="198.51.100.7", peer_trusted=True, header_present=True)
    monkeypatch.setattr(identity, "identify", lambda _request: who)


def _post(store, **form):
    r = store["client"].post(CARD + "/save", data=form, headers={"HX-Request": "true"})
    return r, r.get_data(as_text=True)


def _chip(store):
    return store["client"].get("/v2/who").get_data(as_text=True)


class TestTheDefault:
    def test_a_person_is_the_part_before_the_at_never_the_domain(self, store):
        assert D().default(ALEX) == "alex" == D().shown(ALEX)
        assert D().default(SAM) == "sam"
        from modules import identity
        assert identity.display_name(ALEX) == "alex"
        assert "example" not in identity.display_name(SAM)

    def test_a_host_login_a_job_and_nobody_are_drawn_as_they_are(self, store):
        assert D().default("operator-login") == "operator-login"
        assert D().default("Mercury: repository init") == "Mercury: repository init"
        assert D().default("unverified") == "unverified"
        assert D().default("") == "" == D().shown("")

    def test_a_service_token_is_its_label(self, store):
        from modules.settings_schema import write_settings

        assert D().default("service:abc123.access") == "abc123.access", "unlabelled: its id"
        assert write_settings({"cf_access_service_labels": {"abc123.access": "nightly export"}},
                              actor="test")["ok"]
        assert D().default("service:abc123.access") == "nightly export"
        assert D().people("service:abc123.access") == "nightly export"


class TestTheStore:
    def test_a_set_name_is_kept_with_who_set_it_owner_only(self, store):
        out = _set(ALEX, "  Lex   Luthor ")
        assert (out["name"], out["shown"], out["was"], out["nothing"]) == (
            "Lex Luthor", "Lex Luthor", "", False)
        with open(store["path"], encoding="utf-8") as fh:
            table = json.load(fh)
        assert set(table) == {ALEX}
        assert set(table[ALEX]) == {"name", "set_by", "actor_verified", "at"}
        assert (table[ALEX]["name"], table[ALEX]["set_by"], table[ALEX]["actor_verified"]) == (
            "Lex Luthor", ALEX, "access")
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", table[ALEX]["at"])
        assert stat.S_IMODE(os.stat(store["path"]).st_mode) == 0o600
        left = [n for n in os.listdir(os.path.dirname(store["path"]))
                if n.startswith("display_names.json.tmp-")]
        assert left == [], "replaced whole: no temporary file is left"
        assert D().shown(ALEX) == "Lex Luthor" and D().default(ALEX) == "alex"

    def test_the_same_name_again_changes_nothing(self, store):
        _set(ALEX, "Lex")
        before = open(store["path"], "rb").read()
        assert _set(ALEX, "Lex")["nothing"] is True
        assert open(store["path"], "rb").read() == before

    def test_use_the_default_keeps_who_returned_it(self, store):
        _set(ALEX, "Lex")
        out = _set(ALEX, "", by=TEST_PERSON, admin=True)
        assert (out["default"], out["shown"], out["was"]) == (True, "alex", "Lex")
        assert D().shown(ALEX) == "alex"
        row = json.load(open(store["path"], encoding="utf-8")).get(ALEX) or {}
        assert (row.get("name"), row.get("set_by")) == ("", TEST_PERSON)

    def test_a_change_another_process_made_is_drawn(self, store):
        """The parsed store is kept until the file changes: a write by another worker
        process (the file replaced) is read, never the kept copy."""
        _set(ALEX, "Lex")
        assert D().shown(ALEX) == "Lex"
        other = store["path"] + ".other-process"
        with open(other, "w", encoding="utf-8") as fh:
            json.dump({ALEX: {"name": "Alexander", "set_by": ALEX, "actor_verified": "access",
                              "at": "2026-11-11T00:00:00Z"}}, fh)
        os.replace(other, store["path"])
        assert D().shown(ALEX) == "Alexander"

    def test_an_unreadable_store_refuses_the_write_and_draws_the_default(self, store):
        _set(ALEX, "Lex")
        with open(store["path"], "w", encoding="utf-8") as fh:
            fh.write('{"alex@example.invalid": {"name": "Lex"')          # cut short
        damaged = open(store["path"], "rb").read()
        assert D().shown(ALEX) == "alex", "the default, never a guess at what it held"
        assert D().people(f"set by {ALEX}") == "set by alex"
        with pytest.raises(D().Unreadable) as said:
            _set(ALEX, "Alexander")
        assert said.value.kind == "ValueError" and "display_names.json" in str(said.value)
        assert open(store["path"], "rb").read() == damaged, "nothing was written over it"
        view = D().view(ALEX, "through Cloudflare Access", admin=True)
        assert view["readable"] is False and "ValueError" in view["why"]
        assert [r["may_change"] for r in view["rows"]] == [False]

    def test_a_file_that_is_no_table_of_people_is_unreadable(self, store):
        with open(store["path"], "w", encoding="utf-8") as fh:
            json.dump(["alex"], fh)
        with pytest.raises(D().Unreadable) as said:
            _set(ALEX, "Lex")
        assert "holds a list, not a table of people" in str(said.value)
        assert json.load(open(store["path"], encoding="utf-8")) == ["alex"]


class TestEachRefusalNamesBothSides:
    def test_a_name_holding_an_at(self, store):
        why = _refusal(ALEX, "lex@home")
        assert why == "A display name holds no address: 'lex@home' contains '@'."
        assert not os.path.exists(store["path"]), "nothing was saved"

    def test_a_name_over_the_bound_says_both_numbers(self, store):
        assert _set(ALEX, "x" * 32)["name"] == "x" * 32, "the bound itself is a name"
        why = _refusal(ALEX, "y" * 33)
        assert why == "A display name is at most 32 printable characters: this one is 33."
        assert D().shown(ALEX) == "x" * 32

    def test_a_character_that_cannot_be_printed(self, store):
        why = _refusal(ALEX, "Lex\x07")
        assert "at most 32 printable characters" in why
        assert "1 that cannot be printed" in why and "U+0007" in why

    def test_a_name_another_person_has_whatever_its_case(self, store):
        _set(ALEX, "Lex")
        why = _refusal(SAM, "lex")
        assert why.startswith("'lex' is already Lex's display name: choose another")
        assert "two people are never drawn alike" in why and "@" not in why
        assert D().shown(SAM) == "sam"

    def test_another_persons_default_is_theirs_too(self, store):
        _set(ALEX, "Lex")
        why = _refusal(SAM, "Alex")
        assert why.startswith("'Alex' is already Lex's default name")
        assert "@" not in why.replace('"@"', "")
        assert _set(SAM, "Sam I Am")["name"] == "Sam I Am", "any other name is theirs to take"

    def test_a_name_mercury_uses_for_itself_or_for_nobody(self, store):
        for name in ("Mercury", "mercury: drift check", "you", "service:x", "unverified"):
            why = _refusal(ALEX, name)
            assert why.startswith("A display name is a person's:") and repr(name) in why
        assert not os.path.exists(store["path"])

    def test_only_an_admin_changes_another_persons(self, store):
        _set(ALEX, "Lex")
        why = _refusal(ALEX, "Lexington", by=SAM, admin=False)
        assert why == ("Only an admin changes another person's display name: you are sam, "
                       "and this is Lex's.")
        assert D().shown(ALEX) == "Lex"
        assert _set(ALEX, "Lexington", by=SAM, admin=True)["name"] == "Lexington"
        row = json.load(open(store["path"], encoding="utf-8"))[ALEX]
        assert row["set_by"] == SAM, "the row names who set it, not whose it is"

    def test_nobody_verified_sets_none(self, store):
        why = _refusal(ALEX, "Lex", by="unverified")
        assert "set by a verified person" in why and "not verified" in why
        assert not os.path.exists(store["path"])


class TestThePeopleFilter:
    def test_a_recorded_identity_becomes_the_display_name(self, store):
        words = f"as the policy set by {ALEX}, holding r3"
        assert D().people(words) == "as the policy set by alex, holding r3"
        _set(ALEX, "Lex")
        assert D().people(words) == "as the policy set by Lex, holding r3"
        assert D().people(ALEX) == "Lex", "a recorded actor alone, too"

    def test_every_other_word_is_left_as_recorded(self, store):
        reason = ("the collector at 2001:db8::7 port 57500 was restarted (ticket NET-42); "
                  f"agreed with {SAM}.")
        drawn = D().people(reason)
        assert drawn == reason.replace(SAM, "sam")
        assert drawn.endswith("agreed with sam."), "the sentence keeps its full stop"
        for same in ("", "no person here", "a remote: git@host.example:group/repo.git",
                     "https://reader@host.example/path", "host:aa:bb@0000000000000002/1"):
            assert D().people(same) == same
        assert D().people(None) == ""

    def test_several_people_in_one_text(self, store):
        _set(ALEX, "Lex")
        assert D().people(f"{ALEX} approved what {SAM} proposed ({ALEX})") == \
            "Lex approved what sam proposed (Lex)"

    def test_a_page_s_model_is_drawn_as_a_copy(self, store):
        model = {"rows": [{"what": f"kept by {ALEX}", "n": 3, "who": (ALEX, None),
                           "id": f"row:{ALEX}", "event": f"e:{ALEX}"}], ALEX: "k"}
        drawn = D().people_payload(model)
        assert drawn == {"rows": [{"what": "kept by alex", "n": 3, "who": ("alex", None),
                                   "id": f"row:{ALEX}", "event": f"e:{ALEX}"}], ALEX: "k"}, \
            "what a row is known by, and every key, as they are: the page sends them back"
        assert model["rows"][0]["what"] == f"kept by {ALEX}", "the model itself is untouched"

    def test_the_jinja_filter_escapes_a_name_as_the_page_does(self, store):
        from flask import render_template_string
        from markupsafe import Markup

        import app as A

        _set(ALEX, "<Lex> & co")
        with A.app.test_request_context("/v2/"):
            plain = render_template_string("{{ words | people }}", words=f"by {ALEX}")
            drawn = render_template_string("{{ words | people }}",
                                           words=Markup(f"<b>by {ALEX}</b>"))
        assert plain == "by &lt;Lex&gt; &amp; co"
        assert drawn == "<b>by &lt;Lex&gt; &amp; co</b>", "markup kept, the name escaped"


class TestTheControl:
    def test_a_person_sets_their_own_and_every_screen_draws_it(self, store):
        import app as A

        # The card at rest names the viewer by their default, and holds the identity only in
        # its collapsed record: its form names the person by a key.
        html = store["client"].get(CARD).get_data(as_text=True)
        assert 'id="card-display-names"' in html and "Display names" in html
        assert "you (verified through Cloudflare Access)" in html
        assert "<strong>test-person</strong>" in html and "the default" in html
        assert addresses(html) == [], "no identity outside the collapsed record"
        record = re.search(r'<details class="id-record[^"]*"[^>]*>(.*?)</details>', html, re.S)
        assert record and TEST_PERSON in record.group(1), "the identity, in its record"
        assert html.count(TEST_PERSON) == 1
        assert 'name="person" value="' + D().person_key(TEST_PERSON) + '"' in html
        assert ">test-person<" in _chip(store) and ">TE<" in _chip(store)
        sock = A.socketio.test_client(A.app)
        sock.get_received()
        r, html = _post(store, name="Tess")
        assert r.status_code == 200 and "<strong>Saved:</strong>" in html
        assert "now shown as <strong>Tess</strong>" in html and "in place of test-person" in html
        assert r.headers["X-NMAS-Invalidates"] == "people"
        told = [m["args"][0] for m in sock.get_received() if m["name"] == "nmas_invalidate"]
        sock.disconnect()
        assert [(m["keys"], m["by"]) for m in told] == [(["people"], "display-names")]
        row = json.load(open(store["path"], encoding="utf-8"))[TEST_PERSON]
        assert (row["name"], row["set_by"], row["actor_verified"]) == (
            "Tess", TEST_PERSON, "access"), "recorded with the request's verified actor"
        chip = _chip(store)
        assert ">Tess<" in chip and ">TE<" in chip and "test-person" not in chip
        assert 'hx-trigger="nmas:people from:body"' in chip, "it reads again on the key"
        from modules import history_sources, identity, in_flight, preview_confirm
        with A.app.test_request_context("/v2/"):
            from flask import request
            assert preview_confirm.confirm_part(request)["statement"] == \
                "You are confirming as Tess."
        assert identity.display_name(TEST_PERSON) == "Tess"
        assert history_sources.shown_who(f"{TEST_PERSON} (not verified)") == "Tess"
        assert in_flight._who(TEST_PERSON, "someone-else") == "Tess"
        page = store["client"].get("/v2/settings/installation?tab=access").get_data(as_text=True)
        assert "Signed in as</dt><dd>Tess" in page and ">Tess<" in page
        assert addresses(page) == []
        # An address kept from before display names names an identity: History draws, and
        # filters by, that person's name.
        old = store["client"].get(f"/v2/history?person={TEST_PERSON}").get_data(as_text=True)
        assert "Nothing matches, person Tess" in old and addresses(old) == []

    def test_use_the_default_returns_to_it(self, store):
        _post(store, name="Tess")
        r, html = _post(store, name="ignored", use_default="1")
        assert r.status_code == 200 and "now shown as <strong>test-person</strong>" in html
        assert "<strong>test-person</strong> (the default), in place of Tess" in html
        assert ">test-person<" in _chip(store)
        _r, again = _post(store, name="")
        assert "<strong>Nothing changed:</strong>" in again, "an empty name is the default too"

    def test_a_refusal_changes_nothing_and_keeps_what_was_typed(self, store):
        _post(store, name="Tess")
        before = open(store["path"], "rb").read()
        r, html = _post(store, name="tess@home")
        assert r.status_code == 409 and "X-NMAS-Invalidates" not in r.headers
        assert "<strong>Not saved:</strong> A display name holds no address: " \
            "&#39;tess@home&#39; contains &#39;@&#39;. Nothing was changed." in html
        assert 'value="tess@home"' in html and re.search(
            r'<details class="set-replace" data-keep="dn-change-[^"]+" open>', html)
        r, html = _post(store, name="z" * 41)
        assert r.status_code == 409
        assert "at most 32 printable characters: this one is 41." in html
        assert open(store["path"], "rb").read() == before and ">Tess<" in _chip(store)

    def test_two_people_never_share_a_name_and_an_admin_sets_anothers(self, store, monkeypatch):
        _as(monkeypatch, ALEX)
        r, _html = _post(store, name="Lex")
        assert r.status_code == 200 and ">Lex<" in _chip(store)
        _as(monkeypatch, TEST_PERSON)
        r, html = _post(store, name="LEX")
        assert r.status_code == 409 and "is already Lex&#39;s display name" in html
        assert ALEX not in html.replace(ALEX, "", 1), "the other person only in their record"
        assert addresses(html) == []
        assert "another person" in html and "set by Lex" in html
        # Every verified person is an admin until Mercury holds roles: the other row's own
        # key names it, and the row then says who set it.
        key = D().person_key(ALEX)
        assert f'<tr data-person="{key}">' in html
        r, html = _post(store, person=key, name="Alexander")
        assert r.status_code == 200 and "that person is now shown as <strong>Alexander</strong>" in html
        row = json.load(open(store["path"], encoding="utf-8"))[ALEX]
        assert (row["name"], row["set_by"]) == ("Alexander", TEST_PERSON)
        assert "set by test-person" in store["client"].get(CARD).get_data(as_text=True)
        _as(monkeypatch, ALEX)
        assert ">Alexander<" in _chip(store)

    def test_a_key_that_names_nobody_is_refused(self, store):
        r, html = _post(store, person="0" * 16, name="Ghost")
        assert r.status_code == 409 and "No person on this card was named" in html
        assert not os.path.exists(store["path"])

    def test_a_service_token_sets_none(self, store, monkeypatch):
        from modules.settings_schema import write_settings

        # Even where the installation lets a service configure: a name is a person's.
        assert write_settings({"require_person_for_configure": False}, actor="test")["ok"]
        _as(monkeypatch, "service:abc123.access", kind="service")
        r, html = _post(store, name="Robot")
        assert r.status_code == 403
        assert "set by a verified person: this request is a service (abc123.access), not a " \
            "person." in html
        assert not os.path.exists(store["path"])
        card = store["client"].get(CARD).get_data(as_text=True)
        assert "no verified person" in card and "Change…" not in card

    def test_an_unreadable_store_is_said_and_nothing_is_saved(self, store):
        with open(store["path"], "w", encoding="utf-8") as fh:
            fh.write("not json")
        r, html = _post(store, name="Tess")
        assert r.status_code == 409
        assert "The display names could not be read (ValueError), so nothing was saved." in html
        assert open(store["path"], encoding="utf-8").read() == "not json"
        card = store["client"].get(CARD).get_data(as_text=True)
        assert "The display names could not be read, so each person is drawn by their " \
            "default" in card and "Change…" not in card
        assert ">test-person<" in _chip(store)



def test_a_reopened_card_names_who_started_it_by_display_name():
    """`device_actions.reopened_words`: the badge on a card another person's run reopens."""
    from modules import device_actions

    # Premise corrected (the operator, 2026-11-12: "no "Reopened" label"; C3122's "Your run,
    # started 13:01"): whose run it is, by display name, and its times as ISO, which the page
    # draws in the viewer's zone (C3121).
    job = {"actor": "pat.lee@example.invalid", "state": "running", "started_at": 1762862400.0}
    assert device_actions.reopened_words(job, "viewer@example.invalid") == {
        "whose": "pat.lee's run", "started": "2025-11-11T12:00:00Z", "finished": ""}
    assert device_actions.reopened_words(job, "pat.lee@example.invalid")["whose"] == "Your run"
    done = dict(job, state="done", finished_at=1762862460.0)
    assert device_actions.reopened_words(done, "viewer@example.invalid")["finished"] == \
        "2025-11-11T12:01:00Z"
    assert device_actions.reopened_words({"state": "done"}, "v@example.invalid") == {
        "whose": "A run nobody recorded", "started": "", "finished": ""}
    # A self-heal's card says who it is by itself (C3161): no banner, and no person named.
    assert device_actions.reopened_words(dict(job, card="heal_run"), "v@example.invalid") == {}
