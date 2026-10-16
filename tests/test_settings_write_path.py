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

from tests.js_source import read_shipped
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)


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
        """The standing rule: a new default reproduces what predates it (app.py's
        `_WF_DEFAULTS`, which left with the AI family, D15)."""
        from modules.settings_schema import DEFAULTS

        previous = {"wf_read_first": True, "wf_auto_backup": True, "wf_update_vars": True,
                    "wf_require_approval": False}
        for flag, value in previous.items():
            assert DEFAULTS[flag] is value, flag
        assert DEFAULTS["ai_enabled"] is True
        # The one deliberate exception (C497): the background agent is OFF until Stage 8.
        assert DEFAULTS["background_agent_enabled"] is False

    def test_declaring_them_seeds_nothing(self, store):
        """Adding a key to DEFAULTS must not write it to any install."""
        from modules import settings_schema as ss

        store["settings_schema_version"] = ss.SCHEMA_VERSION
        ss.migrate()
        for key in self.ORPHANS:
            assert key not in store, key

    def test_the_settings_saves_go_through_the_write_path(self):
        """Today's `/settings` save (and its `_save_settings`) left with today's Settings modal
        at 7.8 (2026-10-15); its homes, Settings › Installation's cards and each network's,
        write through `write_settings` (or a network's own store), never around it."""
        from tests.astcheck import calls_in

        from modules import installation_settings as I
        from modules import list_settings as L

        assert calls_in(I.save_card, "save_user_settings") == 0
        assert calls_in(I.save_card, "write_settings") == 1
        assert calls_in(L.write, "save_user_settings") == 0
        assert calls_in(L.write, "write_settings") == 1


class TestARemovedKeyStaysInTheFileReadByNothing:
    """C705: `grafana_device_dashboard_url` was removed the way the schema removes a key
    (`SEEDS_BY_VERSION`: a key removed from DEFAULTS is not removed from any file). It is
    declared nowhere, a write naming it is refused, and a value an older build stored stays in
    the file, read by nothing, beside writes of every other key. The host's file held it,
    empty, when measured on 2026-10-16."""

    KEY = "grafana_device_dashboard_url"
    STORED = "https://grafana.example/d/x?var-device={hostname}"

    def test_it_is_declared_nowhere(self):
        from modules import settings_scope
        from modules.integrations import REGISTRY
        from modules.settings_schema import DEFAULTS, SCHEMA

        assert self.KEY not in DEFAULTS
        assert self.KEY not in SCHEMA["properties"]
        assert self.KEY not in settings_scope.SCOPES
        owners = [name for name, cls in REGISTRY.items()
                  if self.KEY in cls.plain_keys + cls.secret_keys]
        assert owners == [], f"an integration still lists {self.KEY}: {owners}"
        # The population is real: Grafana's own keys are each declared.
        grafana = REGISTRY["grafana"]
        assert len(grafana.plain_keys) >= 6
        assert set(grafana.plain_keys) <= set(DEFAULTS)

    def test_a_write_naming_it_is_refused_by_name(self, store):
        from modules.settings_schema import ratify, write_settings

        r = write_settings({self.KEY: "https://g/{hostname}"})
        assert r["ok"] is False and r["refused"] == [self.KEY] and self.KEY in r["error"]
        assert self.KEY not in store
        assert ratify(self.KEY, actor="a@b")["ok"] is False

    def test_a_stored_value_survives_a_write_and_a_migration(self, store, monkeypatch):
        from modules import settings_schema as ss

        store.update({self.KEY: self.STORED, "settings_schema_version": 1})
        assert ss.write_settings({"grafana_verify_tls": False}, actor="a@b")["ok"] is True
        assert store.get(self.KEY) == self.STORED and store.get("grafana_verify_tls") is False
        monkeypatch.setattr(ss, "SCHEMA_VERSION", 2)
        ss.migrate()
        assert store.get(self.KEY) == self.STORED and store.get("settings_schema_version") == 2

    def test_no_product_code_names_it(self):
        """Parsed for Python (string constants, never comments), anchored as a word for
        templates and scripts; a control key the product does read is found by the same scan."""
        import ast
        import os
        import re

        from tests import source_index

        root = source_index.ROOT
        files = (source_index.tracked("modules", "routes", "templates", "static/js", "scripts")
                 + source_index.tracked(".", suffix=".py", recursive=False))

        def names(key):
            word = re.compile(rf"\b{re.escape(key)}\b")
            hits, scanned = [], 0
            for p in files:
                rel = os.path.relpath(p, root)
                if p.endswith(".py"):
                    scanned += 1
                    with open(p, encoding="utf-8") as fh:
                        tree = ast.parse(fh.read())
                    if any(isinstance(n, ast.Constant) and isinstance(n.value, str)
                           and word.search(n.value) for n in ast.walk(tree)):
                        hits.append(rel)
                elif p.endswith((".html", ".js", ".sh")) or rel.startswith("scripts/"):
                    scanned += 1
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        if word.search(fh.read()):
                            hits.append(rel)
            return hits, scanned

        hits, scanned = names(self.KEY)
        assert scanned >= 300, f"the scan read only {scanned} files"
        assert hits == [], f"product code still names {self.KEY}: {hits}"
        control, _n = names("grafana_device_dashboard_uid")
        assert "modules/settings_schema.py" in control


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
    """Record this decision on Settings › Installation › Access and identity
    (`settings_v2.install_ratify`); today's ratify route (/identity/posture/ratify) left with
    today's Settings modal at 7.8 (2026-10-15)."""

    RECORD = "/v2/settings/installation/access/record"

    @pytest.fixture
    def client(self, store):
        import app as nmas

        nmas.app.config["TESTING"] = False
        return nmas.app.test_client()

    def test_an_unverified_caller_is_refused(self, client):
        r = client.post(self.RECORD, data={"keys": ["require_person_for_reveal"]})
        assert r.status_code == 403

    def test_the_refusal_does_not_write(self, client, store):
        client.post(self.RECORD, data={"keys": ["require_person_for_reveal"]})
        assert "require_person_for_reveal" not in store

    def test_it_ships_with_its_entry_point(self, store):
        """With every gate defaulted (nobody decided), the tab offers the decision."""
        import re

        import app as nmas

        page = nmas.app.test_client().get("/v2/settings/installation?tab=access") \
            .get_data(as_text=True)
        flat = re.sub(r"\s+", " ", page)
        assert self.RECORD in flat and "Record this decision" in flat


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

        from tests.source_index import tracked

        parts = []
        # `static/js/gen` too: Stage 7 0b moved the script that
        # names these keys out of the templates, and a scan of
        # templates alone would report every one as unsurfaced.
        # A DECISION lives in a UI control or in docs/SETTINGS.md, and nowhere
        # else: the corpus was all of `docs/`, so a key named in a register
        # row or a plan counted as its "stated reason" (C155: the removed
        # `netbox_remove_on_list_delete` passed on its own finding's row, and
        # `clab_labs` had never been decided at all).
        for path in tracked("templates", "static/js/gen", suffix=(".html", ".js"),
                                root="."):
            parts.append(io.open(path, encoding="utf-8", errors="replace").read())
        parts.append(io.open(os.path.join("docs", "SETTINGS.md"),
                             encoding="utf-8").read())
        return "\n".join(parts)

    def test_a_mention_elsewhere_in_docs_is_not_a_decision(self):
        """The control: a key named only in another document is not in the
        corpus, however often the register mentions it."""
        import io

        corpus = self._corpus()
        register = io.open("docs/OPEN_FINDINGS.md", encoding="utf-8").read()
        # A word the register really contains and no control or SETTINGS.md
        # does: present there, absent here. (A made-up string absent from both
        # would pass whatever the corpus held.)
        assert "nmas-netbox-mask-context" in register, "the control's word left the register"
        assert "nmas-netbox-mask-context" not in corpus

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


class TestASaveThatDidNotPersistSaysSo:
    """The Kea Username field cleared itself on re-render.

    The save is followed by a re-render from the server, so a field that did not persist is
    redrawn with the stored value and simply appears to empty. Today's Integrations card
    compared what came back in its script; it left with today's Settings modal at 7.8
    (2026-10-15). On v2 the card is redrawn from the server after its Save, naming the fields
    written, so a field that did not persist shows as what is stored: driven here.
    """

    def test_a_non_secret_field_round_trips_through_the_card(self, networks):
        """Behavioural, on a temporary store (`tests/test_settings_v2.networks`): reader and
        writer agree on the file, or the harness manufactures the defect it is looking for."""
        import html as html_mod

        from tests.test_settings_v2 import _save

        r, html = _save(networks, "Default", "kea", {"kea_username": "keauser",
                                                     "kea_url": "http://192.0.2.8:8000"})
        assert r.status_code == 200 and "Kea saved" in html, html
        from modules.settings_schema import get_setting
        assert get_setting("kea_username") == "keauser"
        assert 'value="keauser"' in html_mod.unescape(html), "redrawn with what was stored"
