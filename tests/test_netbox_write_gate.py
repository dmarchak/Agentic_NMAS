"""Phase 0 acceptance: with allow-writes off, no code path can write to NetBox.

The gate lives on the three write chokepoints in modules/netbox_client.py
(_nb_post / _nb_patch / _nb_delete). Every NetBox write in the codebase goes
through one of them, so proving these three are closed proves the whole surface
is closed.

No test here touches a network: the session is a mock that fails loudly if any
HTTP verb is invoked.
"""

import pytest

from modules import netbox_guard
from modules.netbox_guard import NetBoxWriteBlocked, dry_run


class ExplodingSession:
    """A requests.Session stand-in whose write verbs must never be reached."""

    def _boom(self, *args, **kwargs):
        raise AssertionError(
            "A write reached the network with allow_writes off — the gate leaked"
        )

    post = _boom
    patch = _boom
    put = _boom
    delete = _boom
    get = _boom


@pytest.fixture
def writes_off(monkeypatch):
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: False)


@pytest.fixture
def writes_on(monkeypatch):
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)


class TestWriteGate:
    def test_assert_raises_when_writes_disabled(self, writes_off):
        with pytest.raises(NetBoxWriteBlocked):
            netbox_guard.assert_writes_allowed("POST dcim/devices/")

    def test_assert_passes_when_writes_enabled(self, writes_on):
        netbox_guard.assert_writes_allowed("POST dcim/devices/")

    def test_post_blocked_without_touching_network(self, writes_off):
        from modules.netbox_client import _nb_post
        with pytest.raises(NetBoxWriteBlocked):
            _nb_post(ExplodingSession(), "http://nb.invalid",
                     "dcim/devices/", {"name": "R1"})

    def test_patch_blocked_without_touching_network(self, writes_off):
        from modules.netbox_client import _nb_patch
        with pytest.raises(NetBoxWriteBlocked):
            _nb_patch(ExplodingSession(), "http://nb.invalid",
                      "dcim/devices/1/", {"name": "R1"})

    def test_delete_returns_false_without_touching_network(self, writes_off):
        from modules.netbox_client import _nb_delete
        assert _nb_delete(ExplodingSession(), "http://nb.invalid",
                          "dcim/devices/", 1) is False

    def test_sync_refuses_when_writes_disabled(self, writes_off):
        from modules.netbox_client import sync_list_to_netbox
        result = sync_list_to_netbox("Lab", [{"ip": "203.0.113.1", "hostname": "R1"}])
        assert result["ok"] is False
        assert result["blocked"] is True

    def test_remove_refuses_when_writes_disabled(self, writes_off, monkeypatch):
        from modules import netbox_client
        monkeypatch.setattr(netbox_client, "get_netbox_config",
                            lambda: {"url": "http://nb.invalid", "token": "t",
                                     "verify_tls": True, "auth_scheme": "Bearer",
                                     "allow_writes": False})
        result = netbox_client.remove_list_from_netbox("Lab")
        assert result["ok"] is False
        assert result["blocked"] is True


class TestDryRun:
    def test_dry_run_records_instead_of_writing(self, writes_off):
        """A dry run is allowed with writes off because it writes nothing."""
        from modules.netbox_client import _nb_post
        with dry_run() as plan:
            result = _nb_post(ExplodingSession(), "http://nb.invalid",
                              "dcim/devices/", {"name": "R1"})
        assert result["_dry_run"] is True
        assert result["id"] < 0                      # synthetic placeholder id
        assert plan.summary()["create_count"] == 1
        assert plan.summary()["creates"][0]["name"] == "R1"

    def test_dry_run_records_updates_and_deletes(self, writes_off):
        from modules.netbox_client import _nb_delete, _nb_patch
        with dry_run() as plan:
            _nb_patch(ExplodingSession(), "http://nb.invalid",
                      "dcim/sites/1/", {"name": "Lab"})
            _nb_delete(ExplodingSession(), "http://nb.invalid", "dcim/devices/", 7)
        s = plan.summary()
        assert s["update_count"] == 1 and s["delete_count"] == 1

    def test_dry_run_state_is_restored(self, writes_off):
        assert not netbox_guard.is_dry_run()
        with dry_run():
            assert netbox_guard.is_dry_run()
        assert not netbox_guard.is_dry_run()

    def test_dry_run_is_thread_local(self, writes_off):
        """A dry run on one thread must not put another thread into preview mode."""
        import threading
        seen = {}

        def worker():
            seen["inside_other_thread"] = netbox_guard.is_dry_run()

        with dry_run():
            t = threading.Thread(target=worker)
            t.start()
            t.join()
        assert seen["inside_other_thread"] is False


class TestProvenance:
    def test_managed_tag_detected_by_slug_and_name(self):
        assert netbox_guard.has_managed_tag({"tags": [{"slug": "nmas-managed"}]})
        assert netbox_guard.has_managed_tag({"tags": [{"name": "nmas-managed"}]})
        assert not netbox_guard.has_managed_tag({"tags": [{"slug": "core"}]})
        assert not netbox_guard.has_managed_tag({})

    def test_created_ids_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE",
                            str(tmp_path / "created.json"))
        netbox_guard.record_created("Lab", "dcim/devices/", 42, "R1")
        assert netbox_guard.was_created_by_nmas("Lab", "dcim/devices/", 42)
        assert not netbox_guard.was_created_by_nmas("Lab", "dcim/devices/", 99)

        netbox_guard.forget_created("Lab", "dcim/devices/", 42)
        assert not netbox_guard.was_created_by_nmas("Lab", "dcim/devices/", 42)

    def test_forget_whole_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE",
                            str(tmp_path / "created.json"))
        netbox_guard.record_created("Lab", "dcim/devices/", 1, "R1")
        netbox_guard.record_created("Lab", "dcim/sites/", 2, "Lab")
        netbox_guard.forget_created("Lab")
        assert netbox_guard.get_created("Lab") == {}

    def test_removal_without_provenance_deletes_nothing(self, writes_on, tmp_path,
                                                        monkeypatch):
        """The key regression: removal used to delete by site membership."""
        from modules import netbox_client
        monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE",
                            str(tmp_path / "created.json"))
        monkeypatch.setattr(netbox_client, "get_netbox_config",
                            lambda: {"url": "http://nb.invalid", "token": "t",
                                     "verify_tls": True, "auth_scheme": "Bearer",
                                     "allow_writes": True})
        monkeypatch.setattr(netbox_client, "_session_from_config",
                            lambda cfg: ExplodingSession())

        result = netbox_client.remove_list_from_netbox("UntouchedList")
        assert result["ok"] is True
        assert result["deleted_devices"] == 0
        assert "no record" in result["message"].lower()

    def test_forget_only_never_writes(self, tmp_path, monkeypatch):
        from modules import netbox_client
        monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE",
                            str(tmp_path / "created.json"))
        netbox_guard.record_created("Lab", "dcim/devices/", 1, "R1")
        result = netbox_client.remove_list_from_netbox("Lab", forget_only=True)
        assert result["ok"] and result["forget_only"]
        assert netbox_guard.get_created("Lab") == {}


class TestRemoveNeverDeletesItsOwnTag:
    """The `nmas-managed` tag is in the created-object record — NMAS creates
    it — and must never be removed.

    **Removal requires tagged AND recorded.** A Remove that deleted its own
    tag would strip the marking from every object carrying it, and every
    future Remove would find nothing to delete: the whole fleet of
    NMAS-created objects becomes permanently unremovable and
    indistinguishable from operator-owned ones.

    It was enforced only by two tuples not mentioning `extras/tags`, and
    stated only in `scripts/nmas-netbox-census`'s prose. A rule living in one
    file's docstring and another file's omission is a rule nothing would
    notice being broken — measured on the live deployment, where
    `get_created('nmas-probe')` holds `extras/tags: [{id: 6, name:
    "nmas-managed"}]` alongside the three objects a teardown must remove.
    """

    def test_neither_remover_walks_extras_tags(self):
        from modules.netbox_client import _PER_DEVICE_ORDER, _REMOVAL_ORDER

        assert "extras/tags" not in _REMOVAL_ORDER
        assert "extras/tags" not in _PER_DEVICE_ORDER

    def test_no_endpoint_under_extras_is_walked_at_all(self):
        """Broader than the one name: `extras/` holds tags, custom fields and
        config templates, none of which is data a device list owns."""
        from modules.netbox_client import _PER_DEVICE_ORDER, _REMOVAL_ORDER

        for order in (_REMOVAL_ORDER, _PER_DEVICE_ORDER):
            assert not [e for e in order if e.startswith("extras/")], order

    def test_the_orders_are_not_empty(self):
        """The floor. Two empty tuples would satisfy every assertion above
        and remove nothing at all."""
        from modules.netbox_client import _PER_DEVICE_ORDER, _REMOVAL_ORDER

        assert len(_REMOVAL_ORDER) >= 8, _REMOVAL_ORDER
        assert "dcim/devices" in _REMOVAL_ORDER
        assert "dcim/devices" in _PER_DEVICE_ORDER

    def test_the_census_and_the_code_agree(self):
        """The prose that carried this rule, checked against the tuples it
        describes — so the two cannot drift apart silently."""
        import importlib.util
        import os

        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "scripts", "nmas-netbox-census")
        spec = importlib.util.spec_from_loader("census",
                                               importlib.machinery.SourceFileLoader(
                                                   "census", path))
        census = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(census)

        from modules.netbox_client import _REMOVAL_ORDER

        assert "extras/tags" in census.NOT_COUNTED
        assert "Remove never deletes one" in census.NOT_COUNTED["extras/tags"]
        assert "extras/tags" not in _REMOVAL_ORDER
