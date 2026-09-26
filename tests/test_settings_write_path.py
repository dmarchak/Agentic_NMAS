"""One write path, a positive seed declaration, and ratify-never-change.

Stage 3.2a/3.2b.

**The seed declaration is a whitelist, and the default is nothing.**
`migrate()` used to seed every absent key in `DEFAULTS` whenever
`current < SCHEMA_VERSION`. Measured before the change: bumping to v2 would
have written **98 keys on a v1 install, including all eight identity gates** —
silently converting every "defaulted" into "set explicitly" everywhere, in a
release that would look like an unrelated chore.

The fix is not "a bump must not seed a `require_*` key". That protects the
keys somebody thought of today and leaves the next security-relevant setting
unprotected until someone remembers it exists. A version declares what it
seeds and seeds nothing else — the same shape as `KNOWN_UNREACHABLE` having
to stay empty.

**`migrate()` does not write a value nobody chose.** An unwritten key means
*nobody decided*, which is information, and writing it destroys the
distinction irrecoverably. Recording a decision is `ratify()`, which takes an
actor — and which writes the value **already in force**, so it can be offered
from a read-only panel without letting a session change what it is allowed
to do.
"""

import json

import pytest

from tests.js_source import read_shipped, with_loaded_scripts


@pytest.fixture
def store(monkeypatch):
    """A settings file we control, through the real accessors."""
    from modules import settings_schema as ss

    data = {}
    monkeypatch.setattr(ss, "load_user_settings", lambda: dict(data))
    monkeypatch.setattr(ss, "save_user_settings",
                        lambda d: (data.clear(), data.update(d)))
    monkeypatch.setattr("modules.config.load_user_settings", lambda: dict(data))
    monkeypatch.setattr("modules.secrets_store.migrate_plaintext", lambda: [])
    return data


class TestAVersionSeedsOnlyWhatItDeclares:

    def test_a_bump_with_no_declaration_seeds_nothing(self, store, monkeypatch):
        """The measurement that motivated this: 98 keys, 8 of them gates."""
        from modules import settings_schema as ss

        store["settings_schema_version"] = ss.SCHEMA_VERSION
        monkeypatch.setattr(ss, "SCHEMA_VERSION", ss.SCHEMA_VERSION + 1)

        summary = ss.migrate()
        assert summary["added_keys"] == []

    def test_no_identity_gate_is_ever_seeded_by_an_undeclared_bump(
            self, store, monkeypatch):
        from modules import identity, settings_schema as ss

        store["settings_schema_version"] = ss.SCHEMA_VERSION
        monkeypatch.setattr(ss, "SCHEMA_VERSION", ss.SCHEMA_VERSION + 1)
        ss.migrate()

        for action in identity.GATED_ACTIONS:
            for prefix in ("require_identity_for", "require_person_for"):
                assert f"{prefix}_{action}" not in store

    def test_a_bump_seeds_exactly_its_declaration(self, store, monkeypatch):
        from modules import settings_schema as ss

        # Capture the target FIRST: patching SCHEMA_VERSION changes what
        # `ss.SCHEMA_VERSION + 1` evaluates to on the next line, which is how
        # the first version of this test declared seeds for v3 and asserted
        # about v2.
        nxt = ss.SCHEMA_VERSION + 1
        store["settings_schema_version"] = ss.SCHEMA_VERSION
        monkeypatch.setattr(ss, "SCHEMA_VERSION", nxt)
        monkeypatch.setitem(ss.SEEDS_BY_VERSION, nxt, ("nsot_git_branch",))

        summary = ss.migrate()
        assert summary["added_keys"] == ["nsot_git_branch"]
        assert "require_person_for_reveal" not in store

    def test_a_declaration_naming_an_unknown_key_seeds_nothing_for_it(
            self, store, monkeypatch):
        """A typo in a declaration must not create a key."""
        from modules import settings_schema as ss

        nxt = ss.SCHEMA_VERSION + 1
        store["settings_schema_version"] = ss.SCHEMA_VERSION
        monkeypatch.setattr(ss, "SCHEMA_VERSION", nxt)
        monkeypatch.setitem(ss.SEEDS_BY_VERSION, nxt, ("nsot_git_brnach",))

        ss.migrate()
        assert "nsot_git_brnach" not in store

    def test_every_declaration_after_v1_names_real_keys(self):
        """Fails when a version declares a key that does not exist. v1 is the
        original migration and is recorded as "*" rather than rewritten —
        changing what a released migration did is a lie about history."""
        from modules import settings_schema as ss

        for version, keys in ss.SEEDS_BY_VERSION.items():
            if keys == "*":
                assert version == 1, f"only v1 may seed everything, not v{version}"
                continue
            unknown = [k for k in keys if k not in ss.DEFAULTS]
            assert not unknown, f"v{version} declares unknown keys: {unknown}"


class TestTheWritePathRefusesWhatItDoesNotKnow:

    def test_a_declared_key_is_written(self, store):
        from modules.settings_schema import write_settings

        assert write_settings({"wf_auto_backup": False})["ok"] is True
        assert store["wf_auto_backup"] is False

    def test_an_undeclared_key_is_refused(self, store):
        from modules.settings_schema import write_settings

        r = write_settings({"wf_auto_bakcup": False})
        assert r["ok"] is False
        assert r["refused"] == ["wf_auto_bakcup"]

    def test_a_refused_write_stores_nothing(self, store):
        """Not even the valid keys beside it — a half-applied settings write
        is worse than a rejected one."""
        from modules.settings_schema import write_settings

        write_settings({"wf_auto_backup": False, "typo_key": 1})
        assert store == {}

    def test_the_refusal_names_the_key(self, store):
        from modules.settings_schema import write_settings

        assert "typo_key" in write_settings({"typo_key": 1})["error"]

    def test_a_wrongly_typed_value_is_refused(self, store):
        from modules.settings_schema import write_settings

        r = write_settings({"wf_auto_backup": "yes please"})
        assert r["ok"] is False
        assert store == {}


class TestTheOrphanKeysAreDeclared:
    """Eight keys the Settings form has always written, known to nothing."""

    ORPHANS = ("ai_enabled", "background_agent_enabled", "wf_read_first",
               "wf_auto_backup", "wf_run_jenkins", "wf_save_golden",
               "wf_update_vars", "wf_require_approval")

    def test_each_is_now_in_the_schema(self):
        from modules.settings_schema import DEFAULTS, SCHEMA

        for key in self.ORPHANS:
            assert key in DEFAULTS, key
            assert key in SCHEMA["properties"], key

    def test_the_defaults_reproduce_the_previous_behaviour(self):
        """The standing rule: a new default reproduces what predates it."""
        import app as nmas
        from modules.settings_schema import DEFAULTS

        for flag, previous in nmas._WF_DEFAULTS.items():
            assert DEFAULTS[flag] is previous, flag
        assert DEFAULTS["ai_enabled"] is True
        assert DEFAULTS["background_agent_enabled"] is True

    def test_declaring_them_seeds_nothing(self, store):
        """Adding a key to DEFAULTS must not write it to any install."""
        from modules import settings_schema as ss

        store["settings_schema_version"] = ss.SCHEMA_VERSION
        ss.migrate()
        for key in self.ORPHANS:
            assert key not in store, key

    def test_the_settings_route_goes_through_the_write_path(self):
        from tests.astcheck import calls_in

        import app as nmas

        assert calls_in(nmas.save_settings, "write_settings") >= 1
        assert calls_in(nmas.save_settings, "save_user_settings") == 0


class TestRatifyNeverChanges:

    def test_it_writes_the_value_already_in_force(self, store):
        from modules.settings_schema import get_setting, ratify

        before = get_setting("require_person_for_reveal")
        assert ratify("require_person_for_reveal", actor="a@b")["ok"] is True
        assert store["require_person_for_reveal"] == before

    def test_it_cannot_be_used_to_change_a_value(self, store):
        """The property that lets a read-only panel offer it."""
        import inspect

        from modules import settings_schema as ss

        src = inspect.getsource(ss.ratify)
        assert "get_setting(key)" in src
        # No caller-supplied value anywhere in the signature.
        assert set(inspect.signature(ss.ratify).parameters) == {"key", "actor"}

    def test_it_requires_an_actor(self, store):
        """A ratification with nobody behind it is a seeded default wearing a
        better name."""
        from modules.settings_schema import ratify

        assert ratify("require_person_for_reveal", actor="")["ok"] is False

    def test_it_refuses_an_unknown_key(self, store):
        from modules.settings_schema import ratify

        assert ratify("not_a_setting", actor="a@b")["ok"] is False

    def test_ratifying_twice_is_harmless(self, store):
        from modules.settings_schema import ratify

        ratify("require_person_for_reveal", actor="a@b")
        r = ratify("require_person_for_reveal", actor="a@b")
        assert r["ok"] is True and r["already"] is True

    def test_the_origin_moves_from_default_to_file(self, store):
        from modules.settings_schema import origin_of, ratify

        assert origin_of("require_person_for_confirm") == "default"
        ratify("require_person_for_confirm", actor="a@b")
        assert origin_of("require_person_for_confirm") == "file"

    def test_the_effective_value_does_not_move(self, store):
        from modules import identity
        from modules.settings_schema import ratify

        before = {g["key"]: g["value"] for g in identity.posture()["gates"]}
        for key in before:
            ratify(key, actor="a@b")
        after = {g["key"]: g["value"] for g in identity.posture()["gates"]}
        assert after == before


@pytest.mark.real_identity


class TestTheRatifyRouteRequiresAPerson:

    @pytest.fixture
    def client(self, store):
        import app as nmas

        nmas.app.config["TESTING"] = False
        return nmas.app.test_client()

    def test_an_unverified_caller_is_refused(self, client):
        r = client.post("/identity/posture/ratify",
                        json={"key": "require_person_for_reveal"})
        assert r.status_code == 403
        assert r.get_json()["ok"] is False

    def test_the_refusal_does_not_write(self, client, store):
        client.post("/identity/posture/ratify",
                    json={"key": "require_person_for_reveal"})
        assert "require_person_for_reveal" not in store

    def test_it_ships_with_its_entry_point(self):
        import re

        import app as nmas

        page = with_loaded_scripts(nmas.app.test_client().get("/").get_data(as_text=True))
        flat = re.sub(r"\s+", " ", page)
        assert "/identity/posture/ratify" in flat
        assert page.count("ratifySetting") >= 2
        assert "record this decision" in flat


class TestEverySchemaKeyHasADecision:
    """Stage 3.2d: surfaced, or file-only **with a stated reason**.

    A setting that is neither in the UI nor recorded as deliberately
    file-only is a setting nobody knows the status of, which is the state all
    of them were in.

    `docs/SETTINGS.md` is the record, and this test is what stops it going
    stale: a key added to `DEFAULTS` and mentioned nowhere fails here.
    """

    @staticmethod
    def _corpus():
        import io
        import os

        parts = []
        # `static/js/gen` too: Stage 7 0b moved the script that
        # names these keys out of the templates, and a scan of
        # templates alone would report every one as unsurfaced.
        for base in ("templates", "docs", "static/js/gen"):
            for root, _d, files in os.walk(base):
                for f in files:
                    if f.endswith((".html", ".md", ".js")):
                        parts.append(io.open(os.path.join(root, f),
                                             encoding="utf-8",
                                             errors="replace").read())
        return "\n".join(parts)

    def test_every_key_is_surfaced_or_documented(self):
        import re

        from modules.settings_schema import DEFAULTS

        corpus = self._corpus()
        # The identity gates are built by f-string on BOTH sides -- Python and
        # the panel's JavaScript -- so a literal search cannot see them. They
        # are covered by test_security_posture.py instead, which asserts the
        # panel renders one row per gated action.
        exempt = {"settings_schema_version"}
        missing = [k for k in DEFAULTS
                   if k not in exempt
                   and not k.startswith(("require_identity_for",
                                         "require_person_for"))
                   and not re.search(r"\b" + re.escape(k) + r"\b", corpus)]
        assert not missing, (
            "no UI control and no entry in docs/SETTINGS.md: " + str(missing))

    def test_the_settings_doc_exists_and_names_the_write_path(self):
        import io

        text = read_shipped("docs/SETTINGS.md")
        assert "write_settings()" in text
        assert "never seeds a default" in text


class TestBackgroundAgentHasAControl:
    """It is the PERSISTENT switch and had none: `/settings` accepted it and
    nothing ever sent it, so it was settable by `curl` alone.

    The Agent tab's Pause button is a different thing — `pause_agent()` sets
    an in-memory Event and persists nothing, so a pause is lost on restart
    and the agent comes back running. Two controls that look like one switch,
    and only the invisible one survives a restart.
    """

    @pytest.fixture(scope="class")
    def page(self):
        import app as nmas

        return with_loaded_scripts(nmas.app.test_client().get("/").get_data(as_text=True))

    def test_the_form_has_the_switch(self, page):
        assert "settingsBackgroundAgentEnabled" in page

    def test_the_save_payload_includes_it(self, page):
        """A control absent from the payload saves silently and never
        persists — the shape this whole stage is about."""
        i = page.index("window.saveSettings = function()")
        assert "background_agent_enabled" in page[i:i + 4000]

    def test_the_form_is_populated_from_the_server(self, page):
        i = page.index("window.openSettingsModal = function()")
        assert "background_agent_enabled" in page[i:i + 4000]

    def test_pause_persists_nothing(self):
        """Pinned, because the UI makes it look like a switch."""
        import inspect

        from modules import agent_runner

        src = inspect.getsource(agent_runner.pause_agent)
        assert "save" not in src and "set_user_setting" not in src

    def test_the_difference_is_written_down(self):
        import io

        text = read_shipped("docs/SETTINGS.md")
        assert "Pause is not disable" in text


class TestASaveThatDidNotPersistSaysSo:
    """The Kea Username field cleared itself on re-render.

    The save is followed by a re-render from the server, so a field that did
    not persist is redrawn with the stored value and simply appears to empty.
    That is the silent-drop shape one layer on from a control missing from
    the payload — and a non-secret field that empties itself must say so.
    """

    @pytest.fixture(scope="class")
    def page(self):
        import app as nmas

        return with_loaded_scripts(nmas.app.test_client().get("/").get_data(as_text=True))

    def test_the_save_compares_what_came_back(self, page):
        assert "did not persist" in page

    def test_secrets_are_excluded_from_the_comparison(self, page):
        """They are never echoed, by design, so they would always 'differ'."""
        i = page.index("did not persist")
        window = page[max(0, i - 1200):i]
        assert "f.type === 'secret'" in window

    def test_a_non_secret_field_round_trips_through_the_route(self, tmp_path,
                                                              monkeypatch):
        """Behavioural: the thing the comparison would catch, not caught.

        Patches the settings FILE rather than the accessors. The first version
        of this test used the mocking fixture above, which redirects
        `settings_schema.load_user_settings` but not
        `modules.config.set_user_setting` -- so the write went to the real
        file and the read to the mock, and it reported `kea_username` as lost.
        That looked exactly like the reported bug and was entirely my own
        test. Reader and writer have to agree on the file, or the harness
        manufactures the defect it is looking for.
        """
        import app as nmas
        from modules import config

        path = tmp_path / "user_settings.json"
        path.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(path))

        client = nmas.app.test_client()
        r = client.post("/settings/integrations/kea",
                        json={"kea_username": "keauser",
                              "kea_url": "http://example:8000"})
        assert r.get_json()["ok"] is True
        assert r.get_json()["integration"]["kea_username"] == "keauser"
