"""C512 (the operator, 2026-10-06, the throwaway session's STOP 8 and STOP 10): onboarding never
added the device to Oxidized's router.db, so an onboarded device got no config backups, and
rotation's `oxidized_row` stage failed for it too ("<ip> is not in router.db").

Promotion now adds the row through the root-owned helper's ADD mode (its own tests are in
test_oxidized_router_db.py), reads router.db back, reloads Oxidized and passes only when
Oxidized lists the device. Onboarding's phase 2 and adopt draw the outcome as their last step,
`oxidized`; a failure there leaves the device managed and the run not ok.

The helper and Oxidized are faked here at `credential_rotation`'s functions, the seam every
caller goes through: a router.db of addresses, and the node list Oxidized serves.
"""

import json

import pytest

from tests.test_adopt_apply import IP as ADOPT_IP, SUPPLIED_PW as ADOPT_SUPPLIED_PW
from tests.test_adopt_apply import _apply as adopt_apply, lab  # noqa: F401 (the fixture)
from tests.test_onboard_phase_two import _steps, world  # noqa: F401 (the fixture)

IP = "192.0.2.41"


class FakeOxidized:
    """router.db's addresses and Oxidized's node list, and every call the code made."""

    def __init__(self, managed=True, held=(), lists_after_reload=True, add_answer=None,
                 lands=True):
        self.managed = managed
        self.held = list(held)
        self.nodes = list(held)
        self.lists_after_reload = lists_after_reload
        self.add_answer = add_answer
        self.lands = lands
        self.added = []
        self.reloads = 0

    def install(self, monkeypatch):
        cr = "modules.nsot.credential_rotation."
        monkeypatch.setattr(cr + "oxidized_managed", lambda: self.managed)
        monkeypatch.setattr(cr + "oxidized_addresses",
                            lambda router_db="": {"ok": True, "addresses": list(self.held)})
        monkeypatch.setattr(cr + "add_oxidized_row", self._add)
        monkeypatch.setattr(cr + "reload_oxidized", self._reload)
        monkeypatch.setattr(cr + "oxidized_node_names", lambda rest="": (list(self.nodes), ""))
        return self

    def _add(self, ip, model, username, password, router_db=""):
        self.added.append((ip, model, username, password))
        if self.add_answer is not None:
            return self.add_answer
        if self.lands:
            self.held.append(ip)
        return {"ok": True, "added": 1}

    def _reload(self, **_kw):
        self.reloads += 1
        if self.lists_after_reload:
            self.nodes = list(self.held)
        return {"ok": True}


def _add(dialect="cisco_ios", password="Fresh3", ip=IP):
    from modules.nsot.onboard import add_to_oxidized
    return add_to_oxidized(ip, dialect, "admin", password)


class TestAddToOxidized:

    def test_an_absent_device_is_added_and_oxidized_lists_it(self, monkeypatch):
        ox = FakeOxidized().install(monkeypatch)
        out = _add()
        assert out["ok"] and out["added"] and out["managed"], out
        assert ox.added == [(IP, "ios", "admin", "Fresh3")] and ox.reloads == 1
        assert "Oxidized lists it" in out["detail"]

    def test_ios_xe_takes_the_ios_model(self, monkeypatch):
        ox = FakeOxidized().install(monkeypatch)
        assert _add(dialect="cisco_iosxe")["ok"]
        assert ox.added[0][1] == "ios"

    def test_no_oxidized_configured_is_said_and_passes_touching_nothing(self, monkeypatch):
        ox = FakeOxidized(managed=False).install(monkeypatch)
        out = _add()
        assert out["ok"] and not out["managed"] and not out["added"]
        assert "no Oxidized is configured" in out["detail"]
        assert ox.added == [] and ox.reloads == 0

    def test_an_address_router_db_holds_is_left_as_it_is(self, monkeypatch):
        ox = FakeOxidized(held=[IP]).install(monkeypatch)
        out = _add()
        assert out["ok"] and not out["added"] and "already holds" in out["detail"]
        assert ox.added == [], "adding never changes a row: rotation owns its credential"

    def test_a_platform_with_no_oxidized_model_adds_nothing(self, monkeypatch):
        ox = FakeOxidized().install(monkeypatch)
        out = _add(dialect="")
        assert not out["ok"] and ox.added == []
        assert out["detail"].startswith("Oxidized does not back it up")

    def test_no_password_adds_nothing(self, monkeypatch):
        ox = FakeOxidized().install(monkeypatch)
        out = _add(password="")
        assert not out["ok"] and ox.added == [] and "no password" in out["detail"]

    def test_a_helper_refusal_is_named(self, monkeypatch):
        FakeOxidized(add_answer={"ok": False, "error": "router.db is locked"}).install(
            monkeypatch)
        out = _add()
        assert not out["ok"] and "router.db is locked" in out["detail"]

    def test_a_row_the_read_back_does_not_find_fails(self, monkeypatch):
        """The helper's word is a claim; router.db read back is the result."""
        FakeOxidized(lands=False).install(monkeypatch)
        out = _add()
        assert not out["ok"] and "read back without it" in out["detail"]

    def test_a_row_oxidized_does_not_list_after_its_reload_fails_naming_the_model(
            self, monkeypatch):
        """A model Oxidized cannot load leaves the row in the file and the node out of its
        list: the file alone would read as done while nothing is backed up."""
        FakeOxidized(lists_after_reload=False).install(monkeypatch)
        out = _add()
        assert not out["ok"] and out["added"]
        assert "does not list it after a reload" in out["detail"] and "'ios'" in out["detail"]

    def test_no_credential_is_in_the_outcome(self, monkeypatch):
        FakeOxidized().install(monkeypatch)
        for out in (_add(), _add(dialect="")):
            assert "Fresh3" not in json.dumps(out)


class TestPromotionAddsTheRow:

    def test_the_rotated_credential_lands_and_the_step_passes(self, world, monkeypatch):
        from modules.nsot.onboard import run_phase_two

        ox = FakeOxidized().install(monkeypatch)
        out = run_phase_two(world["repo"], "bp1", "probe", actor="t", **_steps())
        assert out["ok"] is True, out
        assert ox.added == [("203.0.113.31", "ios", "admin", "R0tatedValue99")], (
            "the row carries the ROTATED credential, never the bootstrap one")
        last = out["steps"][-1]
        assert last["step"] == "oxidized" and last["ok"], last

    def test_a_failed_addition_leaves_the_device_managed_and_the_run_not_ok(
            self, world, monkeypatch):
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import run_phase_two

        FakeOxidized(lists_after_reload=False).install(monkeypatch)
        out = run_phase_two(world["repo"], "bp1", "probe", actor="t", **_steps())
        assert out["promoted"] is True and out["ok"] is False, out
        last = out["steps"][-1]
        assert last["step"] == "oxidized" and not last["ok"]
        assert "does not list it" in last["detail"]
        assert _m.pending_devices(world["repo"]) == [], "promotion stands"

    def test_a_promotion_that_says_nothing_of_oxidized_fails_the_step(self, world):
        from modules.nsot.onboard import run_phase_two

        out = run_phase_two(world["repo"], "bp1", "probe", actor="t",
                            **_steps(promote=lambda *a, **k: {"ok": True}))
        assert out["ok"] is False
        assert out["steps"][-1] == {"step": "oxidized", "ok": False, "detail": (
            "promotion did not say whether Oxidized's router.db holds it")}



class TestAdoptAddsTheRowToo:
    """Adopt promotes through the same function and draws its outcome as the same last step."""

    def test_an_adopted_device_router_db_lacks_gets_the_tools_account(self, lab, monkeypatch):
        ox = FakeOxidized().install(monkeypatch)
        out = adopt_apply(lab)
        assert out["ok"] and out["steps"][-1]["step"] == "oxidized", out["steps"][-1]
        (ip, model, user, pw), = ox.added
        assert (ip, model, user) == (ADOPT_IP, "ios", "nmas")
        assert pw and pw != ADOPT_SUPPLIED_PW, "the tool's account, never the supplied one"

    def test_one_router_db_already_holds_is_left_as_it_is(self, lab, monkeypatch):
        ox = FakeOxidized(held=[ADOPT_IP]).install(monkeypatch)
        out = adopt_apply(lab)
        assert out["ok"] and ox.added == []
        assert "already holds" in out["steps"][-1]["detail"]

    def test_a_failed_addition_is_a_failed_last_step(self, lab, monkeypatch):
        FakeOxidized(lists_after_reload=False).install(monkeypatch)
        out = adopt_apply(lab)
        assert not out["ok"] and out["steps"][-1]["step"] == "oxidized"
        assert not out["steps"][-1]["ok"]


class TestOxidizedsOwnNodeList:
    """`oxidized_node_names`: what Oxidized loaded, read from its REST node list."""

    @pytest.fixture
    def serve(self, monkeypatch):
        from modules.nsot import credential_rotation as CR

        class _Client:
            url = "http://192.0.2.50:8888"

        def _serve(body=None, error=None, refusal=None):
            monkeypatch.setattr(CR, "oxidized_client",
                                lambda rest="": (None, refusal) if refusal else (_Client(), None))
            monkeypatch.setattr(CR, "_oxidized_get", lambda client, path: (body, error))
            return CR.oxidized_node_names()
        return _serve

    def test_the_names_it_lists(self, serve):
        body = json.dumps([{"name": IP, "model": "IOS"}, {"name": "192.0.2.42", "model": "IOS"}])
        assert serve(body) == ([IP, "192.0.2.42"], "")

    def test_an_unreachable_oxidized_is_none_with_why(self, serve):
        names, why = serve(error="connection refused")
        assert names is None and "nodes.json failed: connection refused" in why

    def test_an_unreadable_list_is_none_with_why(self, serve):
        names, why = serve("<html>")
        assert names is None and "could not be read" in why

    def test_no_oxidized_is_none_with_its_refusal(self, serve):
        names, why = serve(refusal={"ok": False, "error": "oxidized_url is not set"})
        assert names is None and why == "oxidized_url is not set"


@pytest.mark.parametrize("dialect", ["cisco_ios", "cisco_iosxe"])
def test_every_dialect_has_an_oxidized_model(dialect):
    from modules.nsot.platform import DIALECTS, oxidized_model_for_dialect

    assert dialect in DIALECTS and oxidized_model_for_dialect(dialect) == "ios"


def test_every_dialect_is_mapped():
    from modules.nsot.platform import DIALECTS, oxidized_model_for_dialect

    assert {d: oxidized_model_for_dialect(d) for d in DIALECTS}
