"""C121 (7.1's NetBox Remove retrofit): a Remove's result is drawn from the row that records
it, its colour from `complete`, and the record is read back on the NetBox page.

The toast said "Removed N object(s) from NetBox" in green whenever the request succeeded,
including when NetBox refused some deletes, and nothing recorded a removal at all. Today's
NetBox tab, whose routes and panel this drove, left at 7.8 (2026-10-17); driven now through
v2's NetBox page (its preview job, its confirm and its Removals read), with NetBox itself
stubbed at `remove_list_from_netbox`, the confirm's one-shot check passed, and drawn by the
page's own templates.
"""

import re

import pytest

from tests.conftest import TEST_PERSON
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

#: A removal dry run whose cascade NetBox answered, taking nothing more (B9: Remove is offered
#: only over an established reach).
PROVEN = {"taken": [], "foreign": [], "unproven": [], "proven": True}


class _Inline:
    def __init__(self, target=None, **_k):
        self.target = target

    def start(self):
        self.target()


def _obj(n, reason=""):
    return {"endpoint": "dcim/devices", "id": n, "name": f"r{n}", "reason": reason}


@pytest.fixture
def removal(networks, monkeypatch, tmp_path):
    import modules.netbox_client as nbc
    from modules import netbox_guard

    monkeypatch.setattr(netbox_guard, "_REMOVALS_FILE", str(tmp_path / "netbox_removals.jsonl"))
    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://192.0.2.8", "token": "t"})
    monkeypatch.setattr("modules.netbox_ops.authorize", lambda *a, **k: None)
    monkeypatch.setattr("modules.netbox_jobs.threading.Thread", _Inline)
    state = {}

    def remove(list_name, dry_run=False, forget_only=False, **k):
        if dry_run:
            return {"ok": True, "list": list_name, "deleted": [_obj(1)], "skipped": [],
                    "failed": [], "complete": True, "dry_run": True, "cascade": PROVEN}
        return dict(state["result"], list=list_name)
    monkeypatch.setattr(nbc, "remove_list_from_netbox", remove)
    return state


def _confirmed(networks):
    """Preview Branch's removal, confirm it, and return the confirm's card (whitespace
    collapsed, quotes unescaped)."""
    headers = {"HX-Request": "true"}
    card = networks["client"].post("/v2/netbox/preview", data={"operation": "remove",
                                                               "list": "Branch"},
                                   headers=headers).get_data(as_text=True)
    job = re.search(r"/v2/netbox/job/([0-9a-f]{32})", card).group(1)
    r = networks["client"].post(f"/v2/netbox/job/{job}/confirm", headers=headers)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return re.sub(r"\s+", " ", r.get_data(as_text=True)).replace("&#39;", "'")


def _removals(networks):
    html = networks["client"].get("/v2/netbox/removals?list=Branch").get_data(as_text=True)
    return re.sub(r"\s+", " ", html).replace("&#39;", "'")


class TestTheResultIsDrawnFromTheRecord:
    def test_a_partial_removal_is_never_green_and_names_each_refusal(self, networks, removal):
        removal["result"] = {"ok": True, "deleted": [_obj(1), _obj(2)], "skipped": [],
                             "failed": [_obj(3, "409 Conflict: protected")], "complete": False}
        card = _confirmed(networks)
        assert "notice-warn set-result" in card and "notice-muted set-result" not in card
        assert "2 object(s) deleted from NetBox for Branch; NetBox REFUSED 1" in card
        assert "dcim/devices #3 r3: 409 Conflict: protected" in card, \
            "which object NetBox refused, and why, is not drawn"

    def test_a_complete_removal_is_green_and_recorded_by_the_person(self, networks, removal):
        removal["result"] = {"ok": True, "deleted": [_obj(1)], "skipped": [_obj(9)],
                             "failed": [], "complete": True}
        card = _confirmed(networks)
        assert "notice-muted set-result" in card
        assert "1 object(s) deleted from NetBox for Branch." in card
        assert "Left alone" in card and "dcim/devices #9 r9" in card
        assert f"by {TEST_PERSON}" in _removals(networks)

    def test_forget_is_recorded_and_says_nothing_was_deleted(self, networks, removal):
        """Stop tracking's result, through the same record (`netbox_ops.remove`'s forget_only,
        v2's Stop tracking's one path)."""
        from modules import netbox_guard, netbox_ops
        from modules.preview_confirm import netbox_removal_result

        removal["result"] = {"ok": True, "forget_only": True, "message": "forgot"}
        result = netbox_ops.remove("Branch", {"forget_only": True}, TEST_PERSON)
        row = netbox_guard.record_removal("Branch", TEST_PERSON, result, forget_only=True)["row"]
        drawn = netbox_removal_result(row)
        assert drawn["level"] == "nothing"
        assert "Nothing was deleted" in drawn["happened"]["summary"]

    def test_the_record_is_read_back_drawn_the_same_way(self, networks, removal):
        removal["result"] = {"ok": True, "deleted": [_obj(1)], "skipped": [],
                             "failed": [_obj(3, "refused")], "complete": False}
        card = _confirmed(networks)
        back = _removals(networks)
        summary = "1 object(s) deleted from NetBox for Branch; NetBox REFUSED 1"
        assert summary in card and summary in back
        assert "notice-warn set-result" in back, "the record read back is drawn green"
        assert f"by {TEST_PERSON}" in back


class TestTheRemovalsRead:
    def test_a_failed_read_is_not_none_recorded(self, networks, removal, monkeypatch):
        from modules import netbox_guard
        monkeypatch.setattr(netbox_guard, "read_removals", lambda name: {
            "state": "unreadable", "rows": [], "error": "unreadable"})
        html = _removals(networks)
        assert "The removal record cannot be read: unreadable" in html
        assert "None recorded" not in html

    def test_never_written_says_none_recorded(self, networks, removal):
        assert "None recorded." in _removals(networks)

    def test_every_value_is_escaped(self, networks, removal, monkeypatch):
        from modules import netbox_guard
        monkeypatch.setattr(netbox_guard, "read_removals", lambda name: {
            "state": "ok", "error": "", "rows": [
                {"at": "2026-10-17T00:00:00Z", "actor": "<i>x</i>", "list": "Branch",
                 "ok": True, "deleted": [{"endpoint": "dcim/devices", "id": 1,
                                          "name": "<b>t</b>"}], "complete": True}]})
        html = _removals(networks)
        assert "<i>x</i>" not in html and "&lt;i&gt;x&lt;/i&gt;" in html
