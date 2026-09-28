"""R2a's findings, pinned (2026-09-28): the import preview must show what the
import does, and must not write the record of one.

C134: the dry run ran the same `_sync_list_to_netbox_impl` as a real import,
including `_record_sync_status()`, so every import PREVIEW overwrote the
stored summary of the last real import: the record the NetBox tab's sync card
draws as that import's result. Measured on the host: `ok: True, updated 9`
stamped at the second of a preview, nothing written to NetBox.

C135: a dry-run PATCH returned only its payload, so the protocol-tag step
read the device it had just "updated" as having no tags and planned a `tags`
write on eight devices whose tags were already exactly those (every one
SETS == HOLDS on the host). The preview listed writes the import never
makes. Now the dry run reads the object, returns it with the payload over it,
and records what the payload CHANGES, which the preview draws.
"""

import json
import os

import pytest

from tests.fake_netbox import FakeNetBox


@pytest.fixture
def nb(monkeypatch, tmp_path):
    from modules import netbox_guard
    import modules.netbox_client as nbc

    box = FakeNetBox()
    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9",
                                                           "token": "t"})
    monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: box)
    monkeypatch.setattr(nbc, "_managed_tag_ids", {})
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    monkeypatch.setattr(nbc, "_SYNC_STATUS_FILE", str(tmp_path / "netbox_sync_status.json"))
    return box, tmp_path / "netbox_sync_status.json"


class TestAPreviewRecordsNoImport:
    def test_a_dry_run_writes_no_sync_status(self, nb):
        from modules.netbox_client import sync_list_to_netbox

        box, status = nb
        out = sync_list_to_netbox("probe-c134", [], dry_run=True)
        assert out.get("dry_run") is True
        assert not status.exists(), "a preview wrote the record of an import"

    def test_a_real_import_records_its_status(self, nb):
        """The control: the real run still records, or the card has nothing."""
        from modules.netbox_client import sync_list_to_netbox

        box, status = nb
        sync_list_to_netbox("probe-c134", [])
        assert "probe-c134" in json.loads(status.read_text())["lists"]

    def test_a_preview_leaves_an_existing_record_alone(self, nb):
        """The host's case: the real import's record was there first."""
        from modules.netbox_client import sync_list_to_netbox

        box, status = nb
        status.write_text(json.dumps({"lists": {"probe-c134": {"timestamp": "real"}}}))
        before = status.read_text()
        sync_list_to_netbox("probe-c134", [], dry_run=True)
        assert status.read_text() == before


class TestAPreviewSaysWhatAnUpdateChanges:
    def _tagged_device(self, box):
        tags = [{"id": 1, "slug": "ospf", "name": "ospf"}, {"id": 2, "slug": "cdp", "name": "cdp"}]
        return box.seed("dcim/devices", {"name": "r3", "serial": "S3", "tags": tags})

    def test_the_patch_returns_the_object_it_updates(self, nb):
        """What the protocol-tag step reads after the device PATCH."""
        from modules import netbox_client
        from modules.netbox_guard import dry_run

        box, _s = nb
        dev = self._tagged_device(box)
        with dry_run():
            out = netbox_client._nb_patch(box, "http://nb", f"dcim/devices/{dev['id']}/",
                                          {"serial": "S3"})
        assert [t["slug"] for t in out["tags"]] == ["ospf", "cdp"], \
            "a payload-only return reads an untagged device and plans a tags write"

    def test_an_update_that_changes_nothing_says_so(self, nb):
        from modules import netbox_client
        from modules.netbox_guard import dry_run
        from modules.preview_confirm import netbox_import_preview

        box, _s = nb
        dev = self._tagged_device(box)
        with dry_run() as plan:
            netbox_client._nb_patch(box, "http://nb", f"dcim/devices/{dev['id']}/",
                                    {"tags": [1, 2]})
            netbox_client._nb_patch(box, "http://nb", f"dcim/devices/{dev['id']}/",
                                    {"serial": "S9"})
        updates = plan.summary()["updates"]
        assert [u["changed"] for u in updates][0] == {}
        assert list(updates[1]["changed"]) == ["serial"]
        p = netbox_import_preview({"list": "Lab", "device_count": 1, "plan": plan.summary(),
                                   "writes_allowed": True, "plan_hash": "ab"},
                                  {"may": True, "statement": "You are confirming as p."})
        lines = p["targets"][0]["program"]["lines"]
        assert any("changes nothing" in line for line in lines)
        assert any(line.endswith("changes serial") for line in lines)
        assert "change 1" in p["what"]["summary"] and "1 more update(s)" in p["what"]["summary"]
