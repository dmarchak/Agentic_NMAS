"""Absent and unreadable are different facts, one layer under every setting.

The chain this file exists to break, measured end to end:

1. `save_user_settings()` opened the real path with ``"w"`` — truncate in
   place, no atomic rename — so the file on disk is briefly a partial
   document.
2. A read arriving in that window got a `JSONDecodeError`.
3. `load_user_settings()` caught it and returned ``{}``, making an unreadable
   file indistinguishable from a first run.
4. The next write persisted that ``{}`` plus the single key being set.
   **Everything else was gone**, including ``settings_schema_version``.
5. The file then read as v0, so the next settings-panel GET ran `migrate()`
   and seeded 107 defaults over it — the Cloudflare Access configuration
   materialising as empty strings.
6. And `cf_access_trusted_peers` blank meant `peer_trusted = (not allowed)
   or ...` trusted **every** peer, silently ending replay protection.

Five mechanisms, each individually defensible, and **nothing announced any
of it**. It surfaced only because the onboarding wizard refused to create a
device and the operator happened to believe the values had been set.

A read on defaults is survivable. A **write** on defaults is what destroyed
the file, and that is the split these tests pin.
"""

import json
import os

import pytest


@pytest.fixture
def settings(tmp_path, monkeypatch):
    import modules.config as cfg

    path = tmp_path / "user_settings.json"
    monkeypatch.setattr(cfg, "USER_SETTINGS_FILE", str(path))
    monkeypatch.setattr(cfg, "_read_failure", {})
    return cfg, path


FULL = {"settings_schema_version": 1,
        "cf_access_team_domain": "example.cloudflareaccess.com",
        "cf_access_aud": "a" * 64,
        "cf_access_trusted_peers": "198.51.100.7",
        "netbox_url": "https://netbox.example"}


class TestTheTwoHalvesThatGotCollapsed:

    def test_a_missing_file_still_returns_empty(self, settings):
        """First run must work. This is the half that was RIGHT, and a fix
        that raised on everything would break it silently."""
        cfg, path = settings
        assert not path.exists()
        assert cfg.load_user_settings() == {}

    def test_a_truncated_file_RAISES(self, settings):
        """The half that was wrong. Against the previous code this returned
        `{}` and the next write persisted it."""
        cfg, path = settings
        path.write_text('{"settings_schema_version": 1, "cf_ac', encoding="utf-8")
        with pytest.raises(cfg.SettingsUnreadable):
            cfg.load_user_settings()

    def test_the_two_are_not_the_same_call(self, settings):
        """Stated as one assertion, because collapsing them is the defect."""
        cfg, path = settings
        assert cfg.load_user_settings() == {}          # absent
        path.write_text("{oh no", encoding="utf-8")
        with pytest.raises(cfg.SettingsUnreadable):    # unreadable
            cfg.load_user_settings()


class TestAWriteOnDefaultsIsRefused:

    def test_set_user_setting_refuses_while_unreadable(self, settings):
        cfg, path = settings
        path.write_text('{"settings_schema_version": 1, "cf_ac', encoding="utf-8")
        with pytest.raises(cfg.SettingsUnreadable):
            cfg.set_user_setting("netbox_allow_writes", True)

    def test_and_the_damaged_file_is_left_alone(self, settings):
        """The write that erased everything was the NEXT one, not the read."""
        cfg, path = settings
        broken = '{"settings_schema_version": 1, "cf_ac'
        path.write_text(broken, encoding="utf-8")
        with pytest.raises(cfg.SettingsUnreadable):
            cfg.set_user_setting("netbox_allow_writes", True)
        assert path.read_text(encoding="utf-8") == broken

    def test_a_read_survives_on_defaults(self, settings):
        """Survivable, and deliberately different from the write."""
        cfg, path = settings
        path.write_text("{broken", encoding="utf-8")
        assert cfg.get_user_setting("netbox_url", "(default)") == "(default)"

    def test_a_healthy_file_still_writes(self, settings):
        """The control. A guard that refused every write would pass every
        test above and make the settings page read-only for ever."""
        cfg, path = settings
        path.write_text(json.dumps(FULL), encoding="utf-8")
        assert cfg.set_user_setting("netbox_allow_writes", True) is True
        after = json.loads(path.read_text(encoding="utf-8"))
        assert after["netbox_allow_writes"] is True
        assert after["cf_access_team_domain"] == FULL["cf_access_team_domain"]


class TestTheDamagedFileIsPreserved:

    def test_it_is_copied_aside(self, settings):
        cfg, path = settings
        path.write_text("{broken", encoding="utf-8")
        with pytest.raises(cfg.SettingsUnreadable):
            cfg.load_user_settings()
        kept = [p for p in os.listdir(path.parent) if ".corrupt-" in p]
        assert kept, os.listdir(path.parent)

    def test_owner_only(self, settings):
        """It is a settings file, and settings files hold secrets — true in
        general even when this one's are already gone."""
        if os.name == "nt":
            pytest.skip("POSIX modes")
        cfg, path = settings
        path.write_text("{broken", encoding="utf-8")
        with pytest.raises(cfg.SettingsUnreadable):
            cfg.load_user_settings()
        kept = next(p for p in os.listdir(path.parent) if ".corrupt-" in p)
        mode = os.stat(path.parent / kept).st_mode & 0o777
        assert mode == 0o600, oct(mode)


class TestTheWriteIsAtomic:

    def test_no_partial_document_is_ever_at_the_real_path(self, settings):
        """The window that started the chain. `save_user_settings` wrote to
        the real path with "w"; a reader in that window saw a fragment.

        Asserted through the writer's own behaviour: the temp file carries
        the partial content and the real path is replaced whole.
        """
        cfg, path = settings
        path.write_text(json.dumps(FULL), encoding="utf-8")
        seen = []
        real_replace = os.replace

        def _spy(src, dst):
            # At this instant the destination must still be the OLD, valid
            # document — never a truncated one.
            seen.append(json.loads(open(dst, encoding="utf-8").read()))
            return real_replace(src, dst)

        import modules.config as _cfg
        orig = _cfg.os.replace
        _cfg.os.replace = _spy
        try:
            cfg.save_user_settings(dict(FULL, netbox_allow_writes=True))
        finally:
            _cfg.os.replace = orig

        assert seen, "save_user_settings did not go through os.replace"
        assert seen[0]["cf_access_team_domain"] == FULL["cf_access_team_domain"]

    def test_the_temp_file_does_not_survive(self, settings):
        cfg, path = settings
        cfg.save_user_settings(dict(FULL))
        assert not os.path.exists(str(path) + ".tmp")


class TestTheReseedsBlastRadiusIsEnumerable:
    """**What a version-0 reseed destroys without leaving a trace.**

    Measured, two days after the fact: `clab_host` was set on 2026-09-22 —
    `nmas-check-startup-applies` passes no `clab=` and read two remote files
    per device, which it cannot do with an empty setting — and it is empty
    now. The settings file erased itself on 2026-09-23 and the reseed wrote
    107 defaults.

    **The blast radius was assessed as "the Cloudflare Access values" and
    was wider.** `clab_configs_dir` and `clab_launch_patch` have plausible
    non-empty defaults, so they survived *looking* correct; the keys whose
    default is empty went blank leaving nothing to notice.

    **`scripts/nmas-settings-diff` cannot find them, by construction** — it
    lists what differs from the default, and a reset key equals it. The loss
    is recoverable from knowledge, not from measurement, which is the whole
    reason the list is written down rather than derived.
    """

    def test_the_gating_keys_are_named(self):
        from modules.settings_schema import GUARD_GATING_EMPTY_DEFAULTS

        assert len(GUARD_GATING_EMPTY_DEFAULTS) >= 3, \
            "the list is the only record of what a reseed silently takes"
        assert "clab_host" in GUARD_GATING_EMPTY_DEFAULTS

    def test_each_is_declared_and_each_default_really_is_empty(self):
        """If a default stops being empty, the key stops being invisible and
        belongs off the list — so this fails rather than quietly over-listing."""
        from modules.settings_schema import (DEFAULTS,
                                             GUARD_GATING_EMPTY_DEFAULTS)

        for key in GUARD_GATING_EMPTY_DEFAULTS:
            assert key in DEFAULTS, f"{key} is not a declared setting"
            assert DEFAULTS[key] == "", (
                f"{key}'s default is no longer empty, so a reseed would "
                "leave a visible value — take it off the list")

    def test_a_setting_with_a_REAL_default_is_not_on_it(self):
        """**The floor.** A list containing everything would be a list
        nobody reads, and the point is which losses are *invisible*."""
        from modules.settings_schema import (DEFAULTS,
                                             GUARD_GATING_EMPTY_DEFAULTS)

        assert "clab_configs_dir" not in GUARD_GATING_EMPTY_DEFAULTS
        assert DEFAULTS["clab_configs_dir"] != ""

    def test_the_diff_script_cannot_detect_these(self):
        """Stated as a test because it is the reason the list exists, and
        because somebody will otherwise reach for the script."""
        import inspect
        import importlib.util
        import os
        from importlib.machinery import SourceFileLoader

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "scripts", "nmas-settings-diff")
        spec = importlib.util.spec_from_file_location(
            "sdiff", path, loader=SourceFileLoader("sdiff", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        src = inspect.getsource(mod)
        assert "DEFAULTS" in src, "the scan is not reading the script"
        # It compares against DEFAULTS, so a key reset TO its default is
        # equal and cannot appear.
        assert "!=" in src or "differ" in src.lower()


class TestTheEmptyDefaultGuardListIsDerivedNotRemembered:
    """A hand-maintained list of these is the wrong shape, and the fourth
    instance is the proof.

    `oxidized_rest_url` was written with the same refusal as the other three
    (*"<key> is not configured"*), defaulted to empty like the other three, and
    sat outside the tuple for as long as it existed — because adding it
    depended on somebody remembering to.

    The pattern, stated once: **a guard whose enabling setting defaults to
    empty is indistinguishable, from its output, from a guard that ran.** It
    refuses, which is safe; it says "not configured", which is true; and
    nothing downstream can tell that apart from a check that executed and
    passed.

    The contract is one-directional on purpose — see
    `test_a_key_the_scan_cannot_see_may_still_be_recorded`.
    """

    def test_the_scan_finds_something(self):
        """**The floor.** Everything below is a set difference, and a scan
        that could not run produces no offenders either."""
        from modules.settings_schema import discover_empty_default_guards

        found = discover_empty_default_guards()
        assert len(found) >= 3, (
            f"the guard scan found {len(found)} — it is matching nothing, "
            "which is indistinguishable from a codebase with no such guards")
        assert "clab_host" in found, \
            "the known instance is not being found, so the scan is broken"
        assert all(found.values()), "every hit must name where it was found"

    def test_everything_discovered_is_recorded(self):
        """The direction that would have caught the fourth.

        A new guard on an empty-defaulting key fails this the day it is
        written, rather than being noticed four instances later.
        """
        from modules.settings_schema import (GUARD_GATING_EMPTY_DEFAULTS,
                                             discover_empty_default_guards)

        found = discover_empty_default_guards()
        missing = sorted(set(found) - set(GUARD_GATING_EMPTY_DEFAULTS))
        assert not missing, (
            "these refuse on a setting whose default is empty and are not in "
            f"GUARD_GATING_EMPTY_DEFAULTS: "
            + "; ".join(f"{k} ({', '.join(found[k])})" for k in missing))

    def test_a_key_the_scan_cannot_see_may_still_be_recorded(self):
        """The scan is a LOWER BOUND, deliberately.

        It reads string constants, so it finds a guard that names its key in
        its own refusal and misses one that does not. `yang_push_script` names
        its key in an advisory (*"set yang_push_script to check"*) rather than
        a refusal, so it stays recorded by hand — and asserting the reverse
        direction would force it out of the list to make a test pass.
        """
        from modules.settings_schema import (GUARD_GATING_EMPTY_DEFAULTS,
                                             discover_empty_default_guards)

        unseen = set(GUARD_GATING_EMPTY_DEFAULTS) - set(
            discover_empty_default_guards())
        assert unseen == {"yang_push_script"}, (
            "the set the scan cannot see has changed: "
            f"{sorted(unseen)}. Each one needs a reason, or it is a ghost")

    def test_the_deprecated_key_is_not_listed(self):
        """A list that keeps ghosts stops meaning what it says.

        `oxidized_rest_url` gated two stages and now gates nothing; the guard
        moved onto `oxidized_url`, which has the same empty default. Listing
        the dead one would claim a live guard that is not there.
        """
        from modules.settings_schema import GUARD_GATING_EMPTY_DEFAULTS

        assert "oxidized_rest_url" not in GUARD_GATING_EMPTY_DEFAULTS
        assert "oxidized_url" in GUARD_GATING_EMPTY_DEFAULTS

    def test_a_docstring_quoting_the_refusal_is_a_mention(self):
        """A pattern that can appear in English needs an anchor.

        The module's own prose quotes `"<key> is not configured"` while
        explaining it, which is the sixth time in this project that the
        explanation of a construct would have matched a search for it.
        """
        import ast

        from modules.settings_schema import _NOT_CONFIGURED

        tree = ast.parse('def f():\n    """clab_host is not configured."""\n'
                         '    return {"error": "clab_host is not configured"}\n')
        doc = tree.body[0].body[0].value
        assert _NOT_CONFIGURED.match(doc.value), \
            "the pattern itself must match, or this proves nothing"
        from modules.settings_schema import discover_empty_default_guards
        assert "settings_schema.py" not in "".join(
            sum(discover_empty_default_guards().values(), [])), (
            "the scanner is matching its own explanatory prose")
