"""A network with no devices marks its device-level checks "no devices yet" (the operator,
2026-11-05), on any installation, host or laptop kit.

Found by measurement, as the kit's marks were (C2521): three scratch installations in a
loopback-only namespace, every reader run once, then Needs attention listed. A fresh host
(Default only, no repository) raised drift "never", baseline unreadable and intent-format
unreadable; an empty network with a repository raised drift "never", and Default's intent
formatting unreadable; the same network with one device added raised drift "never" again,
plus two rows only a device brings (break-glass "could not be checked", the adjacency log
unreadable), which an empty network never raises. So the marked checks are drift, baseline
and intent formatting, per network; and (C2560, on the kit at ee620634, where NetBox is
configured) NetBox against the committed goldens, whose Default row the survey's unconfigured
NetBox never raised. Held here:
- an empty network shows each as one line, "no devices yet: ...", and none of their rows;
- the SAME network, one device added, raises them exactly as before;
- an unreadable inventory is never "no devices": its checks stay rows;
- host and laptop kit alike;
- the device count is read without per-device work (the CSV's first row; NetBox's cache).
"""
import json

import pytest

from modules import attention as A
from modules import device

DEVICE = {"hostname": "r1", "ip": "192.0.2.11", "device_type": "cisco_ios",
          "username": "u", "password": "p", "secret": "s"}
DEVICE6 = {"hostname": "r2", "ip": "2001:db8::12", "device_type": "cisco_ios",
           "username": "u", "password": "p", "secret": "s"}


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A temporary installation with one network, net1, current and empty (its repository made
    by the one init), and Default unregistered-on-disk as a fresh install leaves it."""
    from modules import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
    settings = tmp_path / "user_settings.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(settings))
    registry = tmp_path / "device_lists.json"
    monkeypatch.setattr(config, "DEVICE_LISTS_CONFIG", str(registry))
    monkeypatch.setattr(device, "DEVICE_LISTS_CONFIG", str(registry))
    ok, msg = device.create_device_list("net1", actor="test")
    assert ok, msg
    assert device.set_installation_list("net1")[0]

    def kind(value):
        settings.write_text(json.dumps({"installation_kind": value}), encoding="utf-8")

    def add(dev=DEVICE):
        device.save_device(dict(dev), str(tmp_path / "lists" / "net1" / "devices.csv"))

    return {"dir": tmp_path, "kind": kind, "add": add,
            "csv": tmp_path / "lists" / "net1" / "devices.csv"}


KINDS = ["host", "laptop_kit"]


class TestPresence:
    def test_a_new_network_has_none(self, store):
        assert device.presence("net1")["state"] == "none"

    def test_a_header_only_file_has_none(self, store):
        assert store["csv"].exists() and store["csv"].read_text().strip()
        assert device.presence("net1")["state"] == "none"

    @pytest.mark.parametrize("dev", [DEVICE, DEVICE6], ids=["ipv4", "ipv6"])
    def test_one_device_is_some(self, store, dev):
        store["add"](dev)
        assert device.presence("net1")["state"] == "some"

    def test_an_absent_file_is_none(self, store):
        store["csv"].unlink()
        assert device.presence("net1")["state"] == "none"

    def test_an_unreadable_file_is_unreadable_never_none(self, store):
        store["csv"].unlink()
        store["csv"].mkdir()
        got = device.presence("net1")
        assert got["state"] == "unreadable" and "could not be read" in got["why"]

    def test_an_unreadable_registry_is_unreadable(self, store):
        (store["dir"] / "device_lists.json").write_text("{torn", encoding="utf-8")
        assert device.presence("net1")["state"] == "unreadable"

    @pytest.mark.parametrize("meta,state", [
        ({"never_loaded": True}, "unreadable"), ({"error": "HTTP 503"}, "unreadable"),
        ({}, "none")])
    def test_a_netbox_list_is_read_from_its_cache(self, store, monkeypatch, meta, state):
        from modules import inventory
        from modules.inventory import source_config

        monkeypatch.setattr(source_config, "is_netbox_sourced", lambda name: True)
        monkeypatch.setattr(inventory, "load_netbox_devices", lambda name: ([], [], meta))
        assert device.presence("net1")["state"] == state

    def test_a_netbox_list_with_a_device_is_some(self, store, monkeypatch):
        from modules import inventory
        from modules.inventory import source_config

        monkeypatch.setattr(source_config, "is_netbox_sourced", lambda name: True)
        monkeypatch.setattr(inventory, "load_netbox_devices",
                            lambda name: ([dict(DEVICE)], [], {"error": "HTTP 503"}))
        assert device.presence("net1")["state"] == "some"

    def test_it_reads_the_inventory_the_checks_read_once_with_no_device_io(self, store,
                                                                         monkeypatch):
        """One call of the one dispatch (`load_saved_devices`), never a device session."""
        calls = []
        monkeypatch.setattr(device, "load_saved_devices",
                            lambda path: calls.append(path) or [dict(DEVICE)])
        monkeypatch.setattr("modules.connection.open_ssh",
                            lambda *a, **k: pytest.fail("presence opened a session"))
        assert device.presence("net1")["state"] == "some"
        assert calls == [str(store["csv"])]

    def test_an_unregistered_name_is_unreadable_never_none(self, store):
        assert device.presence("nowhere")["state"] == "unreadable"

    def test_a_committed_golden_with_no_inventory_is_some(self, store, monkeypatch,
                                                          intent_matches):
        """A network whose inventory is empty while its repository still holds a committed
        golden has a device whose record governs: its checks stay rows."""
        from modules.nsot import repo as R

        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
        out = R.save_golden("net1", [R.GoldenItem("r1", "hostname r1\n!\nend\n", "192.0.2.11",
                                                  platform="cisco_ios")], allow_new=True)
        assert out["ok"], out
        assert device.presence("net1")["state"] == "some"

    def test_it_writes_nothing(self, store):
        before = sorted(p.name for p in store["dir"].rglob("*"))
        device.presence("net1")
        device.presence("nowhere")
        assert sorted(p.name for p in store["dir"].rglob("*")) == before


def _marked(res):
    return res["state"] == "read" and res["marked"] == "no devices yet" and not res["rows"] \
        and res["checked"].startswith("no devices yet: net1 holds no device")


@pytest.mark.parametrize("kind", KINDS)
class TestDrift:
    def test_an_empty_network_is_one_line_and_no_row(self, store, kind):
        store["kind"](kind)
        assert _marked(A.drift_source())

    def test_the_same_network_with_a_device_raises_its_row_as_before(self, store, kind):
        store["kind"](kind)
        store["add"]()
        res = A.drift_source()
        assert [r["id"] for r in res["rows"]] == ["drift:net1:never"] and not res["marked"]

    def test_an_unreadable_inventory_keeps_its_row(self, store, kind):
        store["kind"](kind)
        store["csv"].unlink()
        store["csv"].mkdir()
        assert [r["id"] for r in A.drift_source()["rows"]] == ["drift:net1:never"]


@pytest.mark.parametrize("kind", KINDS)
class TestBaseline:
    def test_an_empty_network_is_one_line(self, store, kind):
        store["kind"](kind)
        assert _marked(A.baseline_source())

    def test_the_same_network_with_a_device_is_read_as_before(self, store, kind):
        store["kind"](kind)
        store["add"]()
        res = A.baseline_source()
        assert not res["marked"] and res["checked"].startswith("list net1: no baseline")

    def test_an_unreadable_repository_on_an_empty_network_is_no_row(self, store, kind):
        """A fresh Default has no repository: its baseline was "could not be read"."""
        store["kind"](kind)
        assert device.set_installation_list("Default")[0]
        res = A.baseline_source()
        assert res["state"] == "read" and res["marked"] == "no devices yet" and not res["rows"]


def _intent(**lists):
    return {"state": "ok", "doc": {"stale_after_seconds": 600, "last_good": {
        "value_at": "2026-11-05T05:52:45Z", "value": {"lists": lists}}}}


#: The measured shape: a fresh Default with no repository, and a network with one device whose
#: intent is hand-formatted.
NO_REPO = {"error": "RuntimeError: git rev-parse HEAD failed in <data>/lists/default/config_repo"}
HAND = {"head": "0" * 40, "files": ["host_vars/r1.yml"], "hand": ["r1"]}


@pytest.mark.parametrize("kind", KINDS)
class TestIntentFormat:
    def test_an_empty_network_is_its_own_line_never_its_unreadable_row(self, store, kind):
        store["kind"](kind)
        res = A.intent_format_source(cached=_intent(Default=NO_REPO, net1=HAND),
                                     presence=device.presence)
        assert [n["check"] for n in res["not_applicable"]] == ["Default", "net1"]
        assert all(n["mark"] == "no devices yet" for n in res["not_applicable"])
        assert res["rows"] == []

    def test_the_same_network_with_a_device_raises_its_rows_as_before(self, store, kind):
        store["kind"](kind)
        store["add"]()
        res = A.intent_format_source(cached=_intent(Default=NO_REPO, net1=HAND),
                                     presence=device.presence)
        assert [r["id"] for r in res["rows"]] == ["intent-format:net1:r1"]
        assert [n["check"] for n in res["not_applicable"]] == ["Default"]

    def test_a_planted_value_without_presence_is_read_as_before(self, store, kind):
        store["kind"](kind)
        res = A.intent_format_source(cached=_intent(Default=NO_REPO, net1=HAND))
        assert sorted(r["kind"] for r in res["rows"]) == ["hand", "unreadable"]
        assert not res["not_applicable"]

    def test_an_unreadable_inventory_keeps_its_rows(self, store, kind):
        store["kind"](kind)
        res = A.intent_format_source(cached=_intent(net1=HAND),
                                     presence=lambda n: {"state": "unreadable", "why": "x"})
        assert [r["id"] for r in res["rows"]] == ["intent-format:net1:r1"]


def _lag(**networks):
    return {"state": "ok", "doc": {"stale_after_seconds": 900, "last_good": {
        "value_at": "2026-11-05T05:52:45Z",
        "value": {"configured": True, "networks": networks}}}}


#: C2560's shape on the kit at ee620634: Default, with no repository, as the netbox-lag reader
#: stores it (`readers/netbox_lag.committed_goldens`); and one device NetBox holds less of.
NO_GOLDENS = {"error": "the committed goldens could not be listed (fatal: not a git repository)"}
BEHIND = {"in_netbox": True, "checked": 1, "lldp_error": "", "devices": {
    "r1": {"interfaces": ["GigabitEthernet0/1"], "addresses": [], "cables": [], "netbox_id": 7}}}


@pytest.mark.parametrize("kind", KINDS)
class TestNetBoxLag:
    """C2560's fourth check: "NetBox against the committed goldens" raised "Default's goldens
    could not be compared with NetBox" for a Default holding no device and no repository."""

    def test_an_empty_network_is_its_own_line_never_its_unreadable_row(self, store, kind):
        store["kind"](kind)
        res = A.netbox_lag_source(cached=_lag(Default=NO_GOLDENS, net1=NO_GOLDENS),
                                  writes=True, presence=device.presence)
        assert res["rows"] == []
        assert [n["check"] for n in res["not_applicable"]] == ["Default", "net1"]
        assert all(n["mark"] == "no devices yet" for n in res["not_applicable"])
        assert "2 network(s) with no devices yet" in res["checked"]

    def test_the_reader_s_own_value_is_judged_by_presence(self, store, kind, monkeypatch):
        store["kind"](kind)
        monkeypatch.setattr("modules.reader_job.read_cached",
                            lambda name: _lag(Default=NO_GOLDENS))
        res = A.netbox_lag_source(writes=True)
        assert res["rows"] == [] and [n["check"] for n in res["not_applicable"]] == ["Default"]

    def test_the_same_network_with_a_device_raises_its_rows_as_before(self, store, kind):
        store["kind"](kind)
        store["add"]()
        res = A.netbox_lag_source(cached=_lag(Default=NO_GOLDENS, net1=BEHIND), writes=True,
                                  presence=device.presence)
        assert [r["id"] for r in res["rows"]] == ["netbox-lag:net1:r1"]
        assert [n["check"] for n in res["not_applicable"]] == ["Default"]

    def test_a_planted_value_without_presence_is_read_as_before(self, store, kind):
        store["kind"](kind)
        res = A.netbox_lag_source(cached=_lag(Default=NO_GOLDENS), writes=True)
        assert [r["id"] for r in res["rows"]] == ["netbox-lag:Default:unreadable"]
        assert not res["not_applicable"]

    def test_an_unreadable_inventory_keeps_its_row(self, store, kind):
        store["kind"](kind)
        res = A.netbox_lag_source(cached=_lag(Default=NO_GOLDENS), writes=True,
                                  presence=lambda n: {"state": "unreadable", "why": "x"})
        assert [r["id"] for r in res["rows"]] == ["netbox-lag:Default:unreadable"]


@pytest.mark.parametrize("kind", KINDS)
class TestThePage:
    def _page(self):
        return A.needs_attention(sources=[A.drift_source, A.baseline_source])

    def test_what_was_checked_draws_each_mark_and_no_row(self, store, kind):
        store["kind"](kind)
        page = self._page()
        assert page["rows"] == [] and page["badge"]["n"] == 0
        marks = {s["source"]: s for s in page["sources"]
                 if s["checked"].startswith(A.NO_DEVICES + ": ")}
        assert set(marks) == {"drift", "baseline"}
        assert all(s["count"] == 0 and s["state"] == "read" for s in marks.values())

    def test_the_first_device_brings_the_rows_back(self, store, kind):
        store["kind"](kind)
        store["add"]()
        page = self._page()
        assert [r["id"] for r in page["rows"]] == ["drift:net1:never"]
        assert not [s for s in page["sources"]
                    if s["checked"].startswith((A.NO_DEVICES + ": ", "not applicable on"))]
