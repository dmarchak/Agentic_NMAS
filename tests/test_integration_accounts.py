"""scripts/nmas-integration-accounts: which account each stored integration
token acts as, and what it may do (C100, C230). Read-only, and never a token.

The Grafana permission list is REAL: the NMAS's own token's actions, read on
2026-09-30 from Grafana 13.2.0 Open Source (tests/fixtures/grafana/
token_permissions_editor.json, action names only). That token held an
Editor's permissions, so the script must name its writes; a Viewer's list is
the control."""

import importlib.machinery
import importlib.util
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "grafana", "token_permissions_editor.json")


def _load():
    path = os.path.join(ROOT, "scripts", "nmas-integration-accounts")
    loader = importlib.machinery.SourceFileLoader("nmas_integration_accounts", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


M = _load()
EDITOR = json.load(open(FIX, encoding="utf-8"))["actions"]
VIEWER = ["alert.instances:read", "alert.rules:read", "alert.silences:read", "annotations:read",
          "dashboards:read", "datasources:query", "folders:read"]


class Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


class Grafana:
    def __init__(self, perms, fail=None):
        self.perms, self.fail, self.asked = perms, fail, []

    def _get(self, path):
        self.asked.append(path)
        if path == self.fail:
            return {"ok": False, "error": "HTTP 401"}
        body = ({"version": "13.2.0"} if path == "api/health"
                else {a: [""] for a in self.perms})
        return {"ok": True, "response": Resp(body)}


class Session:
    def __init__(self, status=200):
        self.status, self.asked = status, []

    def get(self, url, timeout):
        self.asked.append(url)
        if url.endswith("api/status/"):
            return Resp({"netbox-version": "4.6.9"}, self.status)
        return Resp({"id": 7, "username": "nmas"}, self.status)


class TestGrafana:
    def test_the_measured_editor_token_is_named_as_able_to_silence_and_edit_rules(self):
        got = M.grafana_account(Grafana(EDITOR))
        assert got["asked"] and got["version"] == "13.2.0"
        for action in ("alert.silences:create", "alert.rules:write", "alert.rules:delete",
                       "dashboards:delete"):
            assert action in got["writes"]
        assert len(got["permissions"]) == 75

    def test_a_viewer_s_list_holds_no_write(self):
        """The control: a reader's token is not named as a writer."""
        assert M.grafana_account(Grafana(VIEWER))["writes"] == []

    def test_every_verb_in_the_measured_list_is_classified(self):
        """A new verb Grafana adds must be decided, not silently read as a read."""
        verbs = {a.rsplit(":", 1)[-1] for a in EDITOR}
        reads = {"read", "list", "query", "explore", "get", "access"}
        assert verbs - reads - set(M.WRITE_VERBS) == set()
        assert len(verbs) >= 10

    def test_could_not_ask_is_never_holds_nothing(self):
        got = M.grafana_account(Grafana(EDITOR, fail="api/access-control/user/permissions"))
        assert got == {"asked": False,
                       "why": "api/access-control/user/permissions: HTTP 401"}


class TestNetBox:
    def test_the_account_the_token_acts_as(self):
        s = Session()
        got = M.netbox_account(s, "https://nb.example")
        assert got == {"asked": True, "version": "4.6.9", "username": "nmas", "id": 7}
        assert [u.rsplit("/", 2)[-2] for u in s.asked] == ["status", "authentication-check"]

    def test_a_refusal_is_could_not_ask(self):
        got = M.netbox_account(Session(status=403), "https://nb.example")
        assert got == {"asked": False, "why": "api/status/: HTTP 403"}


class TestTheCommand:
    @pytest.fixture
    def both(self, monkeypatch):
        netbox = M.netbox_account(Session(), "https://nb.example")

        def set_(grafana):
            monkeypatch.setattr(M, "netbox_account", lambda: netbox)
            monkeypatch.setattr(M, "grafana_account", lambda: grafana)
        return set_

    def test_exit_codes_and_no_token_printed(self, both, capsys):
        editor, viewer = M.grafana_account(Grafana(EDITOR)), M.grafana_account(Grafana(VIEWER))
        both(editor)
        assert M.main([]) == 1
        out = capsys.readouterr().out
        assert "acts as 'nmas'" in out and "it can CHANGE Grafana" in out
        assert "alert.silences:create" in out and "Bearer" not in out
        both(viewer)
        assert M.main([]) == 0
        assert "no create, write or delete" in capsys.readouterr().out
        both({"asked": False, "why": "api/health: timeout"})
        assert M.main([]) == 2
        assert "COULD NOT ASK" in capsys.readouterr().out
