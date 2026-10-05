"""C327 (2026-10-02): approving or rejecting a queued item answers with the entry and, for an
approve, its execution, and both carry the queued diff (`diff`, `advisory_diff`), which is
device config. The list's GET masked it since C56; these POSTs returned it raw. They are
gated `approve`, so C77's `not_device` sweep never reached them.

Through the real routes, as the harness's verified person, with a community and a hashed
secret planted in the diff the drift check would have queued. The control is the GET, which
was masked all along: the same planted values never leave it either.
"""

import pytest

COMMUNITY = "PlantedCommunity327x"
SECRET = "$9$PlantedHash327yyyyyyyy$zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
DIFF = (f"--- golden\n+++ running\n+snmp-server community {COMMUNITY} RO\n"
        f"+username nmas privilege 15 secret 9 {SECRET}\n")


@pytest.fixture
def queue(tmp_path, monkeypatch):
    import app as app_module
    from modules import approval_queue
    from modules.nsot.repo import GoldenItem, save_golden

    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / name))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "t")
    (tmp_path / "t").mkdir()
    ip = "203.0.113.12"
    assert save_golden("t", [GoldenItem("r2", "hostname r2\n", ip, platform="cisco_ios")],
                       source="onboarding", actor="x", allow_new=True)["ok"]
    device = {"hostname": "r2", "ip": ip, "device_type": "cisco_xe", "platform": "cisco_iosxe"}
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(device)])

    def add(action_type):
        e = approval_queue.add_approval(action_type, "drift on r2", ip, "r2", DIFF, {}, "test")
        return e["id"] if isinstance(e, dict) else e
    return {"client": app_module.app.test_client(), "add": add}


def _leaks(text):
    return [v for v in (COMMUNITY, SECRET) if v in text]


class TestTheResponsesAreMasked:
    def test_a_reject_returns_the_entry_masked(self, queue):
        entry_id = queue["add"]("update_golden_config")
        r = queue["client"].post(f"/ai/approvals/{entry_id}/reject")
        body = r.get_data(as_text=True)
        assert r.status_code == 200, body[:300]
        assert r.get_json()["entry"]["status"] == "rejected"
        assert _leaks(body) == [], "the reject answered with the queued diff unmasked"
        assert "<redacted:" in body, "the diff should still be drawn, its slots masked"

    def test_an_approve_returns_the_entry_and_the_execution_masked(self, queue):
        entry_id = queue["add"]("revert_to_golden")
        r = queue["client"].post(f"/ai/approvals/{entry_id}/approve")
        body = r.get_data(as_text=True)
        assert r.status_code == 200, body[:300]
        out = r.get_json()
        assert out["execution"].get("advisory_diff"), out["execution"]
        assert _leaks(body) == [], "the approve answered with the queued diff unmasked"
        assert "<redacted:" in out["entry"]["diff"]
        assert "<redacted:" in out["execution"]["advisory_diff"]


class TestTheControl:
    def test_the_list_was_masked_all_along(self, queue):
        queue["add"]("update_golden_config")
        body = queue["client"].get("/ai/approvals").get_data(as_text=True)
        assert _leaks(body) == [] and "<redacted:" in body
