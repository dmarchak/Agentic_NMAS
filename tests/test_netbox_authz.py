"""One-shot authorization for NetBox writes.

Confirming an import or removal must authorize *that operation only*. It must
not leave NetBox open for writes, and it must not still be valid if NetBox
changed between the preview the operator approved and the confirm they clicked.

Two independent conditions are required before any write executes:

* ``netbox_allow_writes`` — the persistent master switch, meaning "writes are
  permitted at all". Never flipped as a side effect of confirming.
* A single-use token bound to a hash of the previewed plan.
"""

import time

import pytest

from modules import netbox_authz
from modules.netbox_authz import (
    compute_plan_hash, consume_token, issue_token, verify_plan_unchanged,
)


@pytest.fixture(autouse=True)
def clean_tokens():
    netbox_authz.clear_tokens()
    yield
    netbox_authz.clear_tokens()


def _plan(*names):
    return {"creates": [{"endpoint": "dcim/devices", "name": n, "id": -1,
                         "payload": {"name": n}} for n in names]}


class TestPlanHash:
    def test_same_plan_same_hash(self):
        assert compute_plan_hash(_plan("R1", "R2")) == compute_plan_hash(_plan("R1", "R2"))

    def test_different_plan_different_hash(self):
        assert compute_plan_hash(_plan("R1")) != compute_plan_hash(_plan("R1", "R2"))

    def test_order_insensitive(self):
        """The plan is built from a thread pool, so ordering varies."""
        assert compute_plan_hash(_plan("R1", "R2")) == compute_plan_hash(_plan("R2", "R1"))

    def test_synthetic_ids_ignored(self):
        """Placeholder ids depend on visit order and carry no identity."""
        a = {"creates": [{"endpoint": "dcim/interfaces", "name": "Gi1",
                          "id": -1, "payload": {"device": -2}}]}
        b = {"creates": [{"endpoint": "dcim/interfaces", "name": "Gi1",
                          "id": -9, "payload": {"device": -7}}]}
        assert compute_plan_hash(a) == compute_plan_hash(b)

    def test_real_ids_are_significant(self):
        """A delete of object 5 is not the same approval as a delete of 6."""
        a = {"deletes": [{"endpoint": "dcim/devices", "name": "R1", "id": 5}]}
        b = {"deletes": [{"endpoint": "dcim/devices", "name": "R1", "id": 6}]}
        assert compute_plan_hash(a) != compute_plan_hash(b)

    def test_payload_change_detected(self):
        a = {"updates": [{"endpoint": "dcim/devices", "name": "R1", "id": 5,
                          "payload": {"status": "active"}}]}
        b = {"updates": [{"endpoint": "dcim/devices", "name": "R1", "id": 5,
                          "payload": {"status": "offline"}}]}
        assert compute_plan_hash(a) != compute_plan_hash(b)

    def test_empty_plan_is_stable(self):
        assert compute_plan_hash({}) == compute_plan_hash({"creates": []})


class TestTokenLifecycle:
    def test_token_works_once(self):
        token = issue_token("import", "Lab", "hash1")["token"]
        ok, err, approved = consume_token(token, "import", "Lab")
        assert ok and approved == "hash1"

    def test_token_cannot_be_replayed(self):
        """The whole point of one-shot: confirming twice must not write twice."""
        token = issue_token("import", "Lab", "hash1")["token"]
        assert consume_token(token, "import", "Lab")[0] is True
        ok, err, _ = consume_token(token, "import", "Lab")
        assert ok is False
        # WHICH state, with its operand (2026-09-28): "expired or already
        # used" named neither, and hid a third.
        assert err.startswith("This confirmation was already used, ")
        assert "expired" not in err

    def test_unknown_token_refused(self):
        """The third state, the one that happened: a token this server never
        issued (the import preview had masked it on its way out)."""
        ok, err, _ = consume_token("<redacted:token>", "import", "Lab")
        assert ok is False
        assert "not one this server issued" in err and "did not arrive intact" in err
        assert "expired" not in err and "already used" not in err

    def test_token_expires(self, monkeypatch):
        """A confirmation left open in a browser tab must not stay valid."""
        token = issue_token("import", "Lab", "hash1", ttl=60)["token"]
        later = time.time() + 3600
        monkeypatch.setattr(netbox_authz.time, "time", lambda: later)
        ok, err, _ = consume_token(token, "import", "Lab")
        assert ok is False
        # Both operands: how long ago it expired, and the window.
        assert err.startswith("This confirmation expired 3540 s ago. The window is 60 s")
        assert "computed 3600 s ago" in err

    def test_token_bound_to_operation(self):
        """A remove token must not authorize an import."""
        token = issue_token("remove", "Lab", "hash1")["token"]
        ok, err, _ = consume_token(token, "import", "Lab")
        assert ok is False
        assert "different operation" in err

    def test_token_bound_to_list(self):
        token = issue_token("import", "Lab", "hash1")["token"]
        ok, err, _ = consume_token(token, "import", "Production")
        assert ok is False
        assert "different device list" in err

    def test_failed_consume_still_burns_the_token(self):
        """No retry loop: a rejected token is gone, not re-usable."""
        token = issue_token("import", "Lab", "hash1")["token"]
        consume_token(token, "import", "WrongList")
        ok, _, _ = consume_token(token, "import", "Lab")
        assert ok is False

    def test_tokens_are_unguessable_and_distinct(self):
        tokens = {issue_token("import", "Lab", "h")["token"] for _ in range(50)}
        assert len(tokens) == 50
        assert all(len(t) >= 32 for t in tokens)


class TestPlanReverification:
    def test_unchanged_plan_passes(self):
        plan = _plan("R1", "R2")
        ok, err = verify_plan_unchanged(compute_plan_hash(plan), plan)
        assert ok

    def test_changed_plan_aborts(self):
        """Someone added a device in NetBox between preview and confirm."""
        approved = compute_plan_hash(_plan("R1", "R2"))
        ok, err = verify_plan_unchanged(approved, _plan("R1"))
        assert ok is False
        assert "NetBox changed since preview" in err


class TestMasterSwitchIndependence:
    """Confirming must never turn the master switch on by itself."""

    # The switch moving only with a confirm that passes, and never with a plain one, is
    # driven through the real routes in test_netbox_switch_after_confirm.py (C330).

    def test_master_switch_checked_before_token_is_burned(self, monkeypatch):
        """An unauthorized instance must not consume the operator's token."""
        from modules import netbox_guard
        from routes.netbox_safety import _authorize
        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: False)

        token = issue_token("import", "Lab", "hash1")["token"]
        ok, err, status = _authorize({"token": token}, "import", "Lab",
                                     recompute=lambda: {})
        assert ok is False and status == 403
        assert netbox_authz.active_token_count() == 1, "token was burned despite 403"

    def test_authorize_rejects_missing_token(self, monkeypatch):
        from modules import netbox_guard
        from routes.netbox_safety import _authorize
        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
        ok, err, status = _authorize({}, "import", "Lab", recompute=lambda: {})
        assert ok is False and status == 400

    def test_authorize_rejects_changed_plan(self, monkeypatch):
        from modules import netbox_guard
        from routes.netbox_safety import _authorize
        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)

        approved = compute_plan_hash(_plan("R1", "R2"))
        token = issue_token("import", "Lab", approved)["token"]
        ok, err, status = _authorize({"token": token}, "import", "Lab",
                                     recompute=lambda: _plan("R1"))
        assert ok is False and status == 409
        assert "NetBox changed since preview" in err["error"]
        assert err["stale"] is True

    def test_authorize_accepts_matching_plan(self, monkeypatch):
        from modules import netbox_guard
        from routes.netbox_safety import _authorize
        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)

        plan = _plan("R1", "R2")
        token = issue_token("import", "Lab", compute_plan_hash(plan))["token"]
        ok, err, status = _authorize({"token": token}, "import", "Lab",
                                     recompute=lambda: plan)
        assert ok is True and err is None
