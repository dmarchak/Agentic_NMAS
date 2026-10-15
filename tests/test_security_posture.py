"""The security posture, visible (Stage 3.2c).

`require_person_for_reveal`, `require_person_for_approve`,
`require_person_for_confirm`, `require_person_for_publish_remote` and
`service_allowed_operations` decide whether a **human** has to authorise a
reveal, an approval, a change onto a device, or a publish to a remote. Until
this panel they were visible only by opening `data/user_settings.json` over
SSH.

That is the shape that lost the drift checker for twenty-four days: a gate
switched off weeks ago looks exactly like a gate that was never on, and
nothing anywhere gives anyone cause to look.

**Effective value AND origin, both.** `identity.py` builds these keys with
`f"require_person_for_{action}"` and a default of `True`, so *unset* and *set
to the default* are indistinguishable by reading the value — and `migrate()`
seeds defaults only when the stored schema version is behind, so every key
added to `DEFAULTS` since an install last migrated is absent from its file.
Working, correct, and recorded nowhere. The panel exists to make that
distinction visible.
"""

import json

import pytest

from modules.identity import Identity


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """A settings file we control, read through the real accessors."""
    path = tmp_path / "user_settings.json"
    store = {}

    def _write(**kw):
        store.clear()
        store.update(kw)
        path.write_text(json.dumps(store), encoding="utf-8")
        return store

    monkeypatch.setattr("modules.config.load_user_settings",
                        lambda: dict(store))
    monkeypatch.setattr("modules.settings_schema.load_user_settings",
                        lambda: dict(store))
    _write()
    return _write


@pytest.fixture
def client(settings):
    import app as nmas

    nmas.app.config["TESTING"] = False
    return nmas.app.test_client()


class TestTheRecordedPostureStillHolds:
    """Asked directly, because a posture that drifted is a finding.

    Recorded when the identity layer was built: reveal, approve and confirm
    all require a **person**, and the service allowlist **starts empty**.
    """

    def test_person_is_required_for_reveal_approve_and_confirm(self):
        from modules.settings_schema import DEFAULTS

        for action in ("reveal", "approve", "confirm"):
            assert DEFAULTS[f"require_person_for_{action}"] is True, action

    def test_person_is_required_for_publish_remote_too(self):
        from modules.settings_schema import DEFAULTS

        assert DEFAULTS["require_person_for_publish_remote"] is True

    def test_identity_is_required_for_every_gated_action(self):
        from modules.identity import GATED_ACTIONS
        from modules.settings_schema import DEFAULTS

        for action in GATED_ACTIONS:
            assert DEFAULTS[f"require_identity_for_{action}"] is True, action

    def test_the_service_allowlist_starts_empty(self):
        from modules.settings_schema import DEFAULTS

        assert DEFAULTS["service_allowed_operations"] == [], (
            "the exception grants nothing until somebody names an operation")

    def test_every_gated_action_has_both_keys(self):
        """A gate with no key is ungated; a key with no action is a control
        that changes nothing. Both are the presence-vs-applicability shape."""
        from modules.identity import GATED_ACTIONS
        from modules.settings_schema import DEFAULTS

        expected = {f"{p}_{a}" for a in GATED_ACTIONS
                    for p in ("require_identity_for", "require_person_for")}
        found = {k for k in DEFAULTS
                 if k.startswith(("require_identity_for", "require_person_for"))}
        assert found == expected, found ^ expected


class TestEffectiveValueAndOrigin:
    """The distinction the panel exists for."""

    def test_an_absent_key_reports_its_default(self, settings):
        from modules import identity

        settings()                              # empty file
        g = {x["key"]: x for x in identity.posture()["gates"]}
        assert g["require_person_for_reveal"]["value"] is True
        assert g["require_person_for_reveal"]["origin"] == "default"

    def test_a_key_set_to_the_default_is_marked_explicit(self, settings):
        """Same value, different fact: one was decided, one was inherited."""
        from modules import identity

        settings(require_person_for_reveal=True)
        g = {x["key"]: x for x in identity.posture()["gates"]}
        assert g["require_person_for_reveal"]["value"] is True
        assert g["require_person_for_reveal"]["origin"] == "file"

    def test_a_gate_switched_off_reports_off_and_explicit(self, settings):
        from modules import identity

        settings(require_person_for_reveal=False)
        g = {x["key"]: x for x in identity.posture()["gates"]}
        assert g["require_person_for_reveal"]["value"] is False
        assert g["require_person_for_reveal"]["origin"] == "file"

    def test_the_allowlist_origin_is_reported_too(self, settings):
        from modules import identity

        settings(service_allowed_operations=["credential_rotation"])
        p = identity.posture()
        assert p["service_allowed_operations"] == ["credential_rotation"]
        assert p["service_allowlist_origin"] == "file"

    def test_an_unreadable_store_says_unknown_not_default(self, settings,
                                                          monkeypatch):
        """"Could not read it" and "it is the default" are different claims."""
        from modules import identity

        monkeypatch.setattr("modules.config.load_user_settings",
                            lambda: (_ for _ in ()).throw(OSError("boom")))
        assert identity._setting_origin("require_person_for_reveal") == "unknown"


class TestItReadsThroughTheGateItDescribes:
    """A diagnostic computed a second way is a diagnostic that can be wrong on
    its own — the reason `/identity/status` reports `may` rather than which
    gates are enabled."""

    def test_the_value_comes_from_the_same_accessor(self, settings,
                                                    monkeypatch):
        from modules import identity

        seen = []
        real = identity._setting
        monkeypatch.setattr(identity, "_setting",
                            lambda k, d=None: seen.append(k) or real(k, d))
        identity.posture()
        assert "require_person_for_reveal" in seen
        assert "service_allowed_operations" in seen

    def test_it_covers_every_gated_action(self, settings):
        from modules import identity

        actions = {g["action"] for g in identity.posture()["gates"]}
        assert actions == set(identity.GATED_ACTIONS)


#: Who is looking, as `identity.identify()` answers: a caller with no verified assertion, and a
#: verified person.
NOBODY = Identity()
PERSON = Identity(actor="op@example.com", email="op@example.com", kind="person", verified=True,
                  outcome="ok", peer_trusted=True, header_present=True)


class TestAccessValuesAreNotHandedToAnyone:
    """The team domain and the AUD are what an assertion is validated against, so they are
    shown to a verified person only. Today's posture route (/identity/posture) refused to
    echo them; it left with today's Settings modal at 7.8 (2026-10-15), and the same rule is
    Settings › Installation › Access and identity's (`installation_settings.access_view`)."""

    def test_an_unverified_caller_gets_no_values(self, settings):
        from modules import installation_settings as I

        settings(cf_access_team_domain="example.cloudflareaccess.com",
                 cf_access_aud="a" * 64)
        view = I.access_view(NOBODY)
        assert view["access"] is None and view["person"] is False
        assert "example.cloudflareaccess.com" not in json.dumps(view, default=str)
        assert I.access_view(PERSON)["access"]["team_domain"] == "example.cloudflareaccess.com"

    def test_but_it_still_says_whether_they_are_set(self, settings):
        """Set-or-unset is posture; the value is configuration."""
        from modules import installation_settings as I

        settings(cf_access_team_domain="example.cloudflareaccess.com")
        view = I.access_view(NOBODY)
        assert view["access_set"]["cf_access_team_domain"] is True
        assert view["access_set"]["cf_access_aud"] is False

    def test_the_gates_themselves_are_shown_to_anyone(self, settings):
        """Hiding "a person is required to reveal" protects nothing and makes
        it uncheckable."""
        from modules import installation_settings as I

        settings(require_person_for_reveal=False)
        cells = {c["key"]: c for g in I.access_view(NOBODY)["gates"] for c in g["cells"]}
        assert cells["require_person_for_reveal"]["value"] is False

    def test_a_revealed_aud_shows_its_ends_only(self, settings):
        from modules import identity

        settings(cf_access_aud="0123456789" + "x" * 40 + "9876543210")
        acc = identity.posture(reveal_config=True)["access"]
        assert acc["aud_preview"].startswith("01234567")
        assert acc["aud_preview"].endswith("43210")
        assert "xxxxxxxx" not in acc["aud_preview"]

    def test_the_certs_url_is_derived_not_stored(self, settings):
        """The thing that decides which tenant an assertion is checked
        against, shown so a wrong team domain is visible."""
        from modules import identity

        settings(cf_access_team_domain="example.cloudflareaccess.com")
        acc = identity.posture(reveal_config=True)["access"]
        assert acc["certs_url"].endswith("/cdn-cgi/access/certs")
        assert "example.cloudflareaccess.com" in acc["certs_url"]

    def test_trusted_peers_are_counted_not_listed(self, settings):
        from modules import identity

        settings(cf_access_trusted_peers="198.51.100.7, 198.51.100.8")
        acc = identity.posture(reveal_config=True)["access"]
        assert acc["trusted_peer_count"] == 2
        assert "198" not in json.dumps(acc)


class TestItShipsWithItsEntryPoint:
    """Four unreachable features have been found by asking this question. Today's posture
    panel (loaded by today's Settings modal) left at 7.8 (2026-10-15); the posture is Settings
    › Installation › Access and identity, drawn here as a page."""

    @pytest.fixture
    def tab(self, client):
        import re

        html = client.get("/v2/settings/installation?tab=access").get_data(as_text=True)
        return re.sub(r"\s+", " ", html)

    def test_the_tab_draws_the_gates(self, tab):
        assert 'id="card-gates"' in tab and 'id="card-access"' in tab

    def test_the_reason_is_written_not_implied(self, tab):
        """A disabled input says "you can't" and never says why (whitespace-normalised: a
        phrase that wraps across a source line looked absent once)."""
        assert "Why read-only" in tab and "lower its own gate" in tab

    @pytest.mark.real_identity
    def test_the_values_are_withheld_saying_so(self, tab):
        assert "shown to a verified person only" in tab

    def test_a_read_failure_does_not_read_as_the_defaults(self, client, monkeypatch):
        """The settings file's own health, as `config.settings_read_health` reports a file
        the settings layer could not read: every gate is then its default, said so."""
        monkeypatch.setattr("modules.config.settings_read_health",
                            lambda: {"unreadable": True, "error": "boom"})
        html = client.get("/v2/settings/installation?tab=access").get_data(as_text=True)
        assert "The settings file could not be read" in html
        assert "nothing on this tab may be assumed" in html


class TestWhyOriginIsNotObvious:
    """The mechanism that makes "defaulted" the likely state, pinned.

    `migrate()` returns early once the stored `settings_schema_version` has
    caught up, and `SCHEMA_VERSION` is still 1. So a key added to `DEFAULTS`
    after an install reached v1 is never written to that install's file. It
    works -- `get_setting()` falls back to `DEFAULTS` -- but the file is not a
    record of the configuration, and every identity gate is in exactly that
    position on any install that migrated before they existed.

    This is a finding for 3.2a, pinned here because 3.2c is what makes it
    visible.
    """

    def test_a_key_added_after_v1_is_never_seeded(self, monkeypatch):
        from modules import settings_schema as ss

        store = {"settings_schema_version": ss.SCHEMA_VERSION}
        monkeypatch.setattr(ss, "load_user_settings", lambda: dict(store))
        monkeypatch.setattr(ss, "save_user_settings", store.update)
        monkeypatch.setattr("modules.secrets_store.migrate_plaintext",
                            lambda: [])
        monkeypatch.setitem(ss.DEFAULTS, "a_key_added_after_v1", "x")

        summary = ss.migrate()
        assert summary["added_keys"] == []
        assert "a_key_added_after_v1" not in store

    def test_but_reading_it_still_works(self, monkeypatch):
        """Which is why nothing surfaces the gap on its own."""
        from modules import settings_schema as ss

        monkeypatch.setattr(ss, "load_user_settings", lambda: {})
        monkeypatch.setitem(ss.DEFAULTS, "a_key_added_after_v1", "x")
        assert ss.get_setting("a_key_added_after_v1") == "x"
