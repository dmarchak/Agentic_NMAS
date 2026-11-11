"""scripts/nmas-post-deploy-check: the smoke check after a deploy, and what SMOKE OK requires.

The operator, 2026-11-11: the local-account check is part of the smoke check's own output, so
SMOKE OK requires the line "local account: off (setting off, access proxy configured, not
loopback-only)". Held here: that line is said for exactly one combination of the three facts
and every other combination is said fact by fact and fails; the facts come from Mercury's own
stores (the setting, the access proxy's three values, the address it binds); and SMOKE OK needs
the expected commit, every page, no traceback, each expected self-healing mode and, when asked,
the local account off. Nothing here reaches a network: the running Mercury's answers are
handed to `run` as its parameters.
"""

import importlib.machinery
import importlib.util
import itertools
import os

import pytest

from tests.test_sdn_connections import networks  # noqa: F401 (a data folder of the test's own)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFF = "local account: off (setting off, access proxy configured, not loopback-only)"
SHA = "669017fc06"
PROXY = {"cf_access_team_domain": "team.example.com", "cf_access_aud": "a" * 64,
         "cf_access_trusted_peers": "192.0.2.10"}


def _script():
    path = os.path.join(ROOT, "scripts", "nmas-post-deploy-check")
    loader = importlib.machinery.SourceFileLoader("nmas_post_deploy_check", path)
    spec = importlib.util.spec_from_loader("nmas_post_deploy_check", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class _Lazy:
    """The script, loaded at the first use inside a test, so a test's own body is what fails
    where the script is missing."""

    def __getattr__(self, name):
        mod = _script()
        self.__dict__.update(vars(mod))
        return getattr(mod, name)


S = _Lazy()


def _answers(**over):
    """A healthy installation's answers, each replaceable: what `run` is handed."""
    base = {
        "health": lambda _b: {"ok": True, "commit": SHA + "aa", "started_at": "2026-11-11T22:45:19Z"},
        "fetch": lambda _u: 200,
        "journal": lambda _s: "started\nready\n",
        "modes": lambda: {"Default": {"mode": "dry_run", "set": "dry_run", "state": "ok"},
                          "Lab": {"mode": "off", "set": "off", "state": "ok"}},
        "local_account": lambda: {"setting": False, "proxied": True, "loopback": False},
    }
    base.update(over)
    return base


def _run(expected_heal=None, account_off=True, want=SHA, **over):
    said = []
    ok = S.run(want, base="http://mercury.invalid", expected_heal=expected_heal or {},
               local_account_off=account_off, out=said.append, **_answers(**over))
    return ok, said


class TestTheLocalAccountLine:
    def test_only_one_combination_reads_off_and_it_is_the_operators_words(self):
        seen = {}
        for setting, proxied, loopback in itertools.product((False, True), repeat=3):
            ok, line = S.local_account_line(setting, proxied, loopback)
            seen[(setting, proxied, loopback)] = (ok, line)
        assert seen[(False, True, False)] == (True, OFF)
        assert S.LOCAL_ACCOUNT_OFF == OFF
        others = {k: v for k, v in seen.items() if k != (False, True, False)}
        assert len(others) == 7 and not any(ok for ok, _line in others.values())
        assert not any(line == OFF for _ok, line in others.values())

    @pytest.mark.parametrize("setting, proxied, loopback, words", [
        (True, True, False, "(setting ON, access proxy configured, not loopback-only)"),
        (False, False, False, "(setting off, access proxy NOT configured, not loopback-only)"),
        (False, True, True, "(setting off, access proxy configured, LOOPBACK-ONLY)"),
        (True, False, True, "(setting ON, access proxy NOT configured, LOOPBACK-ONLY)"),
    ])
    def test_any_other_combination_says_each_fact_as_it_was_read(self, setting, proxied,
                                                                 loopback, words):
        ok, line = S.local_account_line(setting, proxied, loopback)
        assert ok is False and line == "local account: NOT as expected " + words


class TestTheFactsAreMercurysOwn:
    """The three facts read from the real stores of a test's own data folder."""

    def _set(self, monkeypatch, host, values):
        from modules import config
        from modules.settings_schema import write_settings

        monkeypatch.setattr(config, "FLASK_HOST", host)
        if values:
            assert write_settings(values, actor="test")["ok"], values

    def test_behind_a_proxy_with_the_setting_off_it_reads_off(self, networks, monkeypatch):  # noqa: F811
        self._set(monkeypatch, "0.0.0.0", PROXY)
        facts = S.read_local_account()
        assert facts == {"setting": False, "proxied": True, "loopback": False}
        assert S.local_account_line(**facts) == (True, OFF)

    def test_with_no_proxy_configured_it_is_not_as_expected(self, networks, monkeypatch):  # noqa: F811
        self._set(monkeypatch, "0.0.0.0", {})
        facts = S.read_local_account()
        assert facts == {"setting": False, "proxied": False, "loopback": False}
        ok, line = S.local_account_line(**facts)
        assert ok is False and "access proxy NOT configured" in line

    def test_two_of_the_proxys_three_values_are_not_a_proxy(self, networks, monkeypatch):  # noqa: F811
        two = {k: v for k, v in PROXY.items() if k != "cf_access_trusted_peers"}
        self._set(monkeypatch, "0.0.0.0", two)
        assert S.read_local_account()["proxied"] is False

    @pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
    def test_the_setting_on_and_loopback_only_are_each_read(self, networks, monkeypatch, host):  # noqa: F811
        from modules import local_account as LA

        self._set(monkeypatch, host, dict(PROXY, **{LA.SETTING: True}))
        facts = S.read_local_account()
        assert facts == {"setting": True, "proxied": True, "loopback": True}
        ok, line = S.local_account_line(**facts)
        assert ok is False and "setting ON" in line and "LOOPBACK-ONLY" in line


class TestSmokeOk:
    def test_a_healthy_installation_behind_its_proxy_is_ok_and_says_each_line(self):
        ok, said = _run(expected_heal={"Default": "dry_run"})
        assert ok is True and said[-1] == "SMOKE OK"
        assert said[0] == "health: True 669017fc started 2026-11-11T22:45:19Z"
        assert [s for s in said if s.startswith("page ")] == [f"page {p} 200" for p in S.PAGES]
        assert "journal since start: 2 lines, 0 tracebacks" in said
        assert "heal Default | mode now dry_run | set dry_run | state ok" in said
        assert OFF in said

    @pytest.mark.parametrize("over, line", [
        ({"health": lambda _b: {"ok": True, "commit": "5829af4856", "started_at": "x"}}, "health: True 5829af48"),
        ({"health": lambda _b: {"ok": False, "commit": SHA, "started_at": "x"}}, "health: False"),
        ({"fetch": lambda u: 500 if u.endswith("/v2/history") else 200}, "page /v2/history 500"),
        ({"journal": lambda _s: "x\nTraceback (most recent call last)\n  y\n"}, "1 tracebacks"),
        ({"local_account": lambda: {"setting": True, "proxied": True, "loopback": False}},
         "local account: NOT as expected (setting ON, access proxy configured, not loopback-only)"),
        ({"local_account": lambda: {"setting": False, "proxied": False, "loopback": False}},
         "access proxy NOT configured"),
        ({"local_account": lambda: {"setting": False, "proxied": True, "loopback": True}},
         "LOOPBACK-ONLY"),
        ({"local_account": lambda: {"error": "OSError"}}, "local account: not read (OSError)"),
    ])
    def test_each_thing_wrong_is_said_and_fails_it(self, over, line):
        ok, said = _run(**over)
        assert ok is False and said[-1] == "SMOKE FAILED"
        assert any(line in s for s in said), said

    def test_health_that_does_not_answer_fails_it_and_is_said(self):
        def down(_base):
            raise ConnectionRefusedError("refused")
        ok, said = _run(health=down)
        assert ok is False and said[0] == "health: not answered (ConnectionRefusedError)"
        assert said[-1] == "SMOKE FAILED"

    def test_an_expected_heal_mode_is_compared_naming_both(self):
        ok, said = _run(expected_heal={"Default": "dry_run", "Lab": "off"})
        assert ok is True
        ok, said = _run(expected_heal={"Default": "dry_run"},
                        modes=lambda: {"Default": {"mode": "auto", "set": "auto", "state": "ok"}})
        assert ok is False
        assert "heal Default: expected dry_run, and its mode now is auto" in said
        ok, said = _run(expected_heal={"Elsewhere": "off"})
        assert ok is False
        assert "heal Elsewhere: expected off, and the installation has no such network" in said

    def test_with_no_expectation_a_mode_is_printed_and_not_judged(self):
        ok, said = _run(modes=lambda: {"Default": {"mode": "auto", "set": "auto", "state": "ok"}})
        assert ok is True and "heal Default | mode now auto | set auto | state ok" in said

    def test_the_local_account_fails_it_only_where_off_was_asked(self):
        on = {"local_account": lambda: {"setting": True, "proxied": False, "loopback": True}}
        ok, said = _run(account_off=False, **on)
        assert ok is True and said[-1] == "SMOKE OK"
        assert any(s.startswith("local account: NOT as expected") for s in said)
        ok, said = _run(account_off=True, **on)
        assert ok is False and said[-1] == "SMOKE FAILED"


class TestTheCommandLine:
    def test_help_says_what_ok_requires_and_reads_nothing(self, capsys):
        assert S.main(["--help"]) == 0
        out = capsys.readouterr().out
        assert OFF in out and "SMOKE OK" in out and "--expect-heal NETWORK=MODE" in out

    @pytest.mark.parametrize("argv", [[], ["--expect-local-account-off"], [SHA, "extra"],
                                      [SHA, "--unknown"], [SHA, "--expect-heal", "Default"]])
    def test_a_command_it_does_not_understand_is_usage_never_a_check(self, argv, capsys):
        assert S.main(argv) == 2
        assert "SMOKE" not in capsys.readouterr().out

    def test_heal_expectations_are_network_and_mode(self):
        assert S.heal_expectations(["Default=dry_run", "Lab = off"]) == {"Default": "dry_run",
                                                                          "Lab": "off"}
        for bad in ("Default", "=off", "Default="):
            with pytest.raises(ValueError) as exc:
                S.heal_expectations([bad])
            assert repr(bad) in str(exc.value)
