"""Update the read-only account's lines (C3583; board R's step 1, provisional, operator review
pending): the account's IOS-XE telemetry entry became ``all: true``, and the six IOS-XE routers'
committed intents hold it with ``all: false``, so Add refuses each (`privilege_exec.with_entries`
never changes a held line in passing). THE edit of its own:

- `privilege_exec.with_updated_entries` changes only the held entries whose command the given
  set names, in another level or ``all``; it adds nothing, leaves an exact entry and every other
  held entry as they are, and never changes the caller's document;
- the coverage names each such line old -> new, Add's preview offers the update for the device
  instead of refusing it, and Update's preview names each line old -> new and the lines a deploy
  will then send, writing nothing;
- Update commits by its hash like Add, one commit per network as the person with
  ``Source: read-account-update``, the reason and the preview's hash; a moved preview writes
  nothing and names both hashes; afterwards the device's lines are current.

From the six's real shape: r2's real capture and committed intent (`tests.test_capture`), given
the account's ``users`` entry by reference and the pair as the six hold it (the telemetry line
without ``all``, the level-1 restore of ``show``). IPv6: not applicable (no address is parsed,
formatted or compared here).
"""

import json

import pytest

from modules.nsot import privilege_exec as PE
from modules.nsot import read_account as RA
from tests.test_read_account_fleet import RO, RO_PW, _git, _reread, lab  # noqa: F401

TELEMETRY = "show telemetry ietf subscription"
#: The pair as the six IOS-XE routers' committed intents hold it (read 2026-11-14).
SIX = [{"level": 3, "command": TELEMETRY, "all": False},
       {"level": 1, "command": "show", "all": False}]
OLD = f"privilege exec level 3 {TELEMETRY}"
NEW = f"privilege exec all level 3 {TELEMETRY}"


def _account_set():
    return [l["entry"] for l in PE.read_account_lines("cisco_iosxe", 3, ping_traceroute=False)]


class TestWithUpdatedEntries:
    def test_the_six_s_pair_gains_all_and_nothing_else_moves(self):
        other = {"level": 5, "command": "show clock", "all": False}
        doc = {"hostname": "r2", "privilege_exec": [dict(e) for e in SIX] + [dict(other)]}
        before = json.dumps(doc, sort_keys=True)
        got, changed = PE.with_updated_entries(doc, _account_set())
        assert json.dumps(doc, sort_keys=True) == before, "the caller's document changed"
        assert changed == [{"command": TELEMETRY, "old": SIX[0],
                            "new": {"level": 3, "command": TELEMETRY, "all": True}}]
        held = {e["command"]: e for e in got["privilege_exec"]}
        assert held[TELEMETRY]["all"] is True and held["show"] == SIX[1]
        assert held["show clock"] == other and got["hostname"] == "r2"
        assert PE.with_updated_entries(got, _account_set())[1] == [], "a second run changed"

    def test_another_level_is_changed_too(self):
        doc = {"privilege_exec": [{"level": 4, "command": TELEMETRY, "all": True}, SIX[1]]}
        _got, changed = PE.with_updated_entries(doc, _account_set())
        assert [(c["old"]["level"], c["new"]["level"]) for c in changed] == [(4, 3)]

    def test_an_entry_not_held_is_not_added(self):
        got, changed = PE.with_updated_entries({"privilege_exec": [SIX[1]]}, _account_set())
        assert changed == [] and got["privilege_exec"] == [SIX[1]]
        got, changed = PE.with_updated_entries({}, _account_set())
        assert changed == [] and "privilege_exec" not in got

    def test_add_still_refuses_to_change_it_in_passing(self):
        with pytest.raises(ValueError, match="changed by an edit of its own"):
            PE.with_entries({"privilege_exec": [dict(e) for e in SIX]}, _account_set())


@pytest.fixture
def six(lab):  # noqa: F811
    """r2's committed intent in the six's shape: the account's ``users`` entry by reference and
    the pair without ``all``, committed as an intent edit."""
    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars

    doc = hostvars.read_committed(lab["repo"], "r2")
    doc, _change = hostvars.with_read_account(doc, "default", 3)
    doc["privilege_exec"] = [dict(e) for e in SIX]
    hostvars.write_committed(lab["repo"], doc)
    assert save_host_vars("Lab", ["r2"], actor="t", source="intent-edit")["ok"]
    _reread(lab)
    return lab


class TestTheUpdate:
    def test_the_coverage_names_the_line_and_add_offers_the_update(self, six):
        (row,) = RA.held()["value"]["devices"]
        assert row["other_form"] == [{"old": OLD, "new": NEW}]
        (d,) = RA.candidates()["networks"][0]["devices"]
        assert d["addable"] and d["other_form"] == 1
        p = RA.add_preview([("Lab", "r2")])
        assert p["ok"] and p["refused"] == [] and p["taking"] == []
        assert p["updating"] == [{"network": "Lab", "device": "r2",
                                  "lines": [{"old": OLD, "new": NEW}]}]

    def test_the_preview_names_each_line_and_writes_nothing(self, six):
        head = _git(six["repo"], "rev-parse", "HEAD")
        p = RA.update_preview([("Lab", "r2")])
        assert p["ok"] and [t["device"] for t in p["taking"]] == ["r2"], p
        (g,) = p["groups"]
        assert g["changes"] == [{"old": OLD, "new": NEW}] and g["devices"] == ["r2"]
        lines = [l["line"] for l in g["lines"]]
        assert lines[0] == NEW and "privilege exec level 1 show" in lines
        assert lines[-1].startswith(f"username {RO} privilege 3 ") and "<redacted:" in lines[-1]
        assert RO_PW not in json.dumps(p)
        assert _git(six["repo"], "rev-parse", "HEAD") == head
        assert RA.update_preview([("Lab", "r2")])["hash"] == p["hash"]
        assert p["hash"] != RA.add_preview([("Lab", "r2")])["hash"]

    def test_the_commit_is_one_commit_and_only_the_line_moves(self, six):
        from modules.nsot import hostvars

        before = hostvars.read_committed(six["repo"], "r2")
        p = RA.update_preview([("Lab", "r2")])
        head = _git(six["repo"], "rev-parse", "HEAD")
        got = RA.update_commit([("Lab", "r2")], p["hash"], "the telemetry line became all",
                               "op@example.com")
        assert got["ok"] and got["commits"][0]["commit"], got
        assert _git(six["repo"], "rev-list", "--count", f"{head}..HEAD") == "1"
        log = _git(six["repo"], "log", "-1", "--format=%B")
        assert "Source: read-account-update" in log and "Actor: op@example.com" in log
        assert "Reason: the telemetry line became all" in log and f"Preview: {p['hash']}" in log
        after = hostvars.read_committed(six["repo"], "r2")
        assert {e["command"]: e["all"] for e in after["privilege_exec"]} == {
            TELEMETRY: True, "show": False}
        assert {k: v for k, v in after.items() if k != "privilege_exec"} == {
            k: v for k, v in before.items() if k != "privilege_exec"}
        _reread(six)
        again = RA.update_preview([("Lab", "r2")])
        assert again["taking"] == [] and again["current"] == [{"network": "Lab", "device": "r2"}]
        assert RA.held()["value"]["devices"][0]["other_form"] == []

    def test_a_moved_preview_writes_nothing_and_names_both_hashes(self, six):
        head = _git(six["repo"], "rev-parse", "HEAD")
        p = RA.update_preview([("Lab", "r2")])
        got = RA.update_commit([("Lab", "r2")], "0" * 64, "why", "op@example.com")
        assert not got["ok"] and "000000000000" in got["error"] and p["hash"][:12] in got["error"]
        assert _git(six["repo"], "rev-parse", "HEAD") == head
        assert not RA.update_commit([("Lab", "r2")], p["hash"], " ", "op")["ok"], "no reason"

    def test_an_intent_that_moved_is_a_moved_hash(self, six):
        from modules.nsot import hostvars
        from modules.nsot.repo import save_host_vars

        p = RA.update_preview([("Lab", "r2")])
        doc = hostvars.read_committed(six["repo"], "r2")
        doc["logging"]["syslog"]["heartbeat"] = 301
        hostvars.write_committed(six["repo"], doc)
        assert save_host_vars("Lab", ["r2"], actor="t", source="intent-edit")["ok"]
        head = _git(six["repo"], "rev-parse", "HEAD")
        got = RA.update_commit([("Lab", "r2")], p["hash"], "why", "op@example.com")
        assert not got["ok"] and p["hash"][:12] in got["error"]
        assert _git(six["repo"], "rev-parse", "HEAD") == head


class TestTheRoutes:
    def _client(self):
        import app as A
        return A.app.test_client()

    def test_add_offers_it_and_the_update_previews_and_commits(self, six, monkeypatch):
        monkeypatch.setattr("modules.identity.request_actor", lambda: "op@example.com")
        c = self._client()
        base = "/v2/credentials/profiles/read-account"
        for url in (base + "/add", base + "/fleet?open=pending"):
            r = c.get(url, headers={"Accept": "text/html"})
            assert r.status_code == 200 and "1 line in another form" in r.get_data(as_text=True)
        html = c.post(base + "/add/preview", data={"device": ["Lab/r2"], "reason": "why"}) \
            .get_data(as_text=True)
        assert "data-ra-update-offer" in html and "Update the read-only account" in html
        r = c.post(base + "/add/preview", data={"device": ["Lab/r2"], "reason": "why",
                                                "mode": "update"})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "data-ra-update-lines" in html, html[:400]
        assert f"<code>{OLD}</code> → <code>{NEW}</code>" in html
        p = RA.update_preview([("Lab", "r2")])
        r = c.post(base + "/add", data={"device": ["Lab/r2"], "reason": "why",
                                        "mode": "update", "hash": "f" * 64})
        assert r.status_code == 409 and "data-ra-update-refused" in r.get_data(as_text=True)
        r = c.post(base + "/add", data={"device": ["Lab/r2"], "reason": "why",
                                        "mode": "update", "hash": p["hash"]})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "Updated in intent" in html, html[:400]
        assert "read-account-update" in html
