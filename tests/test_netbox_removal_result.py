"""C121 (7.1's NetBox Remove retrofit): a Remove's result is drawn by the
result component from the row that records it, its colour from `complete`,
and the record is read back on the NetBox tab.

The toast said "Removed N object(s) from NetBox" in green whenever the
request succeeded, including when NetBox refused some deletes, and nothing
recorded a removal at all. Driven through the real apply and reader routes,
with NetBox itself stubbed, and drawn by the SHIPPED renderer.
"""

import json
import os

import dukpy
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _draw(result):
    src = open(os.path.join(ROOT, "static", "js", "nmas_preview_confirm.js")).read()
    return dukpy.evaljs("var window = {};\n" + src
                        + f"\nwindow.previewConfirmResultHtml({json.dumps(result)}, {{}});")


def _panel(payload):
    src = "".join(open(os.path.join(ROOT, "static", "js", f)).read()
                  for f in ("nmas_preview_confirm.js", "nmas_netbox_removals.js"))
    return dukpy.evaljs("var window = this;\n" + src
                        + f"\nwindow.netboxRemovalsHtml({json.dumps(payload)});")


@pytest.fixture
def client(monkeypatch, tmp_path):
    import app as A
    import routes.netbox_safety as ns
    from modules import netbox_guard

    monkeypatch.setattr(netbox_guard, "_REMOVALS_FILE", str(tmp_path / "netbox_removals.jsonl"))
    monkeypatch.setattr(ns, "_authorize", lambda data, kind, ln, recompute=None: (True, None, 200))
    monkeypatch.setattr(ns, "_maybe_permit_writes", lambda data: None)
    monkeypatch.setattr("modules.identity.request_actor", lambda: "ops@example.com")
    state = {}

    def remove(list_name, dry_run=False, forget_only=False, **k):
        return state["result"]
    monkeypatch.setattr("modules.netbox_client.remove_list_from_netbox", remove)
    return A.app.test_client(), state


def _obj(n, reason=""):
    return {"endpoint": "dcim/devices", "id": n, "name": f"r{n}", "reason": reason}


class TestTheResultIsDrawnFromTheRecord:
    def test_a_partial_removal_is_never_green(self, client):
        c, state = client
        state["result"] = {"ok": True, "deleted": [_obj(1), _obj(2)], "skipped": [],
                           "failed": [_obj(3, "409 Conflict: protected")], "complete": False}
        d = c.post("/netbox/safety/remove/apply", json={"list_name": "Lab"}).get_json()
        assert d["result"]["level"] == "partial"
        html = _draw(d["result"])
        assert "Partly done" in html and "REFUSED" in html and "409 Conflict: protected" in html
        assert "Done." not in html

    def test_a_complete_removal_is_green_and_recorded_by_the_person(self, client):
        c, state = client
        state["result"] = {"ok": True, "deleted": [_obj(1)], "skipped": [_obj(9)],
                           "failed": [], "complete": True}
        d = c.post("/netbox/safety/remove/apply", json={"list_name": "Lab"}).get_json()
        assert d["result"]["level"] == "success"
        html = _draw(d["result"])
        assert "dcim/devices #1 r1" in html and "Left alone" in html
        assert "ops@example.com" in html

    def test_forget_is_recorded_and_says_nothing_was_deleted(self, client):
        c, state = client
        state["result"] = {"ok": True, "forget_only": True, "message": "forgot"}
        d = c.post("/netbox/safety/remove/apply",
                   json={"list_name": "Lab", "forget_only": True}).get_json()
        assert d["result"]["level"] == "nothing"
        assert "Nothing was deleted" in d["result"]["happened"]["summary"]

    def test_the_record_is_read_back_drawn_the_same_way(self, client):
        c, state = client
        state["result"] = {"ok": True, "deleted": [_obj(1)], "skipped": [],
                           "failed": [_obj(3, "refused")], "complete": False}
        applied = c.post("/netbox/safety/remove/apply", json={"list_name": "Lab"}).get_json()
        back = c.get("/netbox/safety/removals").get_json()
        assert back["ok"] and back["removals"][0]["by"] == "ops@example.com"
        assert back["removals"][0]["result"]["level"] == applied["result"]["level"]
        html = _panel(back)
        assert "Latest:" in html and "Partly done" in html


class TestThePanel:
    def test_a_failed_read_is_not_none_recorded(self):
        html = _panel({"ok": False, "error": "unreadable"})
        assert "could not be read" in html and "not the same as no removal" in html

    def test_never_written_says_so(self):
        assert "never been written" in _panel({"ok": True, "state": "absent", "removals": []})

    def test_every_value_is_escaped(self):
        html = _panel({"ok": True, "state": "ok", "removals": [
            {"at": "<b>t</b>", "by": "<i>x</i>", "result": {}}]})
        assert "<b>t</b>" not in html and "&lt;b&gt;" in html
