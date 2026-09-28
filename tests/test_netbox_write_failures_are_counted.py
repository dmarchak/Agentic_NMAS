"""Register C8: a NetBox write that did not land is COUNTED, and named.

Twenty write paths in `netbox_client.py` logged their failure at DEBUG and
the sync reported `failed=0`. `failed` counts only devices whose WHOLE upsert
raised, so a device whose VLAN, cable or primary IP did not land was counted
as created or updated, and its failures appeared nowhere. Stage 7.1 draws
that number in the preview-confirm component: a counter that cannot count
failures, drawn as an assurance. The restore preview's "9 of 9" over a
ten-device fleet, in another subsystem, and the reason C8 gates 7.1.

Removal had the other half: a delete NetBox refused went into `skipped`,
the bucket for deliberate provenance skips, as "delete failed" with the
reason thrown away. Two outcomes of different severity in one report.

The counting is measured against a NetBox that REFUSES chosen writes: the
number of failures reported must equal the number injected.
"""

import ast
import inspect

import pytest

from modules import netbox_client as nc
from modules import netbox_guard
from tests.fake_netbox import FakeNetBox, FakeResponse


class RefusingNetBox(FakeNetBox):
    """Refuses a POST to any endpoint in `refuse`, and a DELETE with 409."""

    def __init__(self, refuse=(), refuse_deletes=False):
        super().__init__()
        self.refuse = set(refuse)
        self.refuse_deletes = refuse_deletes

    def post(self, url, json=None, timeout=None):
        endpoint, _ = self._parse(url)
        if endpoint in self.refuse:
            return FakeResponse({"detail": f"refused {endpoint}"}, 400)
        return super().post(url, json=json, timeout=timeout)

    def delete(self, url, timeout=None):
        if self.refuse_deletes:
            return FakeResponse({"detail": "protected: in use"}, 409)
        return super().delete(url, timeout=timeout)


@pytest.fixture(autouse=True)
def writes_on(monkeypatch):
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    monkeypatch.setattr(nc, "_managed_tag_ids", {})
    nc._drain_write_failures()
    yield
    nc._drain_write_failures()


def _upsert(nb, **extra):
    site = nb.seed("dcim/sites", {"name": "Lab", "slug": "lab"})
    role = nb.seed("dcim/device-roles", {"name": "Router", "slug": "router"})
    with netbox_guard.for_list("Lab"), nc._attributed_to("r1"):
        return nc._upsert_device(
            nb, "http://nb.invalid", hostname="r1", ip="203.0.113.1",
            facts={"manufacturer": "Cisco", "model": "C8000v", "platform": "IOS-XE",
                   "serial": "SER0001", "sw_version": "17.6"},
            interfaces=[{"name": "GigabitEthernet1", "ip": "203.0.113.1",
                         "prefix_len": 24, "enabled": True}],
            site_id=site["id"], role_id=role["id"], ipam_stats={}, **extra)


VLANS = [{"vlan_id": 10, "name": "ten"}, {"vlan_id": 20, "name": "twenty"}]
VRFS = [{"name": "blue", "rd": "65000:1"}]


class TestTheCountCounts:
    def test_every_refused_write_is_counted_and_named(self):
        """Three writes refused (two VLANs, one VRF): three failures, each
        naming the device and the write. The device still counts as written,
        which is why `failed` alone could never show them."""
        nb = RefusingNetBox(refuse={"ipam/vlans", "ipam/vrfs"})
        outcome = _upsert(nb, vlans=VLANS, vrfs=VRFS)
        failures = nc._drain_write_failures()
        assert outcome["action"] in ("created", "updated")
        assert sorted(f["write"] for f in failures) == ["VLAN 10", "VLAN 20", "VRF blue"]
        assert {f["device"] for f in failures} == {"r1"}
        assert all("400" in f["error"] for f in failures)

    def test_nothing_refused_counts_nothing(self):
        """The control: the same writes, accepted, record no failure."""
        _upsert(RefusingNetBox(), vlans=VLANS, vrfs=VRFS)
        assert nc._drain_write_failures() == []

    def test_the_report_carries_it(self):
        report = nc.write_failure_report(
            [{"hostname": "r2", "ip": "x", "error": "boom"}],
            [{"device": "r1", "write": "VLAN 10", "error": "e"},
             {"device": "r2", "write": "cable", "error": "e"}])
        assert report["complete"] is False
        assert report["partial"] == ["r1"], "a wholly failed device is not also partial"
        assert len(report["write_failures"]) == 2

    def test_no_failed_device_is_not_complete_when_a_write_did_not_land(self):
        """C8's own case: `failed` is empty, every device was written, and a
        write did not land. The test above could not show this: it had a
        wholly failed device too, so `complete` was false whichever it read
        (the negative control that ignored write failures passed it)."""
        report = nc.write_failure_report(
            [], [{"device": "r1", "write": "primary_ip4", "error": "e"}])
        assert report["failed"] == []
        assert report["complete"] is False
        assert report["partial"] == ["r1"]

    def test_a_clean_report_is_complete(self):
        assert nc.write_failure_report([], [])["complete"] is True

    def test_the_sync_summary_uses_it(self):
        src = inspect.getsource(nc._sync_list_to_netbox_impl)
        assert "**write_failure_report(failed, _drain_write_failures())" in src
        assert src.index("_drain_write_failures()  ") < src.index("write_failure_report("), \
            "the recorder is emptied at the START of a sync"


class TestNoWritePathFailsSilently:
    """Mechanical, so a twenty-first cannot arrive at DEBUG: every `except`
    guarding a write records the failure or re-raises."""

    WRITES = ("_nb_post", "_nb_patch", "_nb_delete")
    RECORDS = ("_write_failed", "_ensure_failed", "_note_delete_failure")

    def _guarded(self):
        tree = ast.parse(inspect.getsource(nc))
        out = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            called = {n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
                      for body in node.body for n in ast.walk(body) if isinstance(n, ast.Call)}
            if not (called & set(self.WRITES) or any(c.startswith("_ensure_") for c in called)):
                continue
            for handler in node.handlers:
                out.append((node.lineno, handler))
        return out

    def test_the_scan_finds_the_write_handlers(self):
        assert len(self._guarded()) >= 18, len(self._guarded())

    @staticmethod
    def _returns_a_refusal(handler) -> bool:
        """`return {"ok": False, ...}`: the whole operation reports failing."""
        for n in ast.walk(handler):
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
                for k, v in zip(n.value.keys, n.value.values):
                    if (isinstance(k, ast.Constant) and k.value == "ok"
                            and isinstance(v, ast.Constant) and v.value is False):
                        return True
        return False

    def test_each_records_reraises_retries_or_refuses(self):
        """Four acceptable shapes, and nothing else:
        * it RECORDS the failure (`_write_failed`, `_ensure_failed`,
          `_note_delete_failure`);
        * it RE-RAISES;
        * it RETRIES the write (a compatibility fallback, `device_role` or
          `content_types`), whose own failure then propagates;
        * the whole operation RETURNS `{"ok": False, ...}` with the reason.
        Its first run found fourteen handlers the hand survey had missed;
        eight were silent (three update fallbacks returning the unchanged
        object, the interface VLAN assignments, the managed tag, the list VRF
        and the config template)."""
        silent = []
        for line, handler in self._guarded():
            names = {n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
                     for n in ast.walk(handler) if isinstance(n, ast.Call)}
            raises = any(isinstance(n, ast.Raise) for n in ast.walk(handler))
            retries = bool(names & set(self.WRITES))
            if not (names & set(self.RECORDS) or raises or retries
                    or self._returns_a_refusal(handler)):
                silent.append(line)
        assert silent == [], f"write failures handled without being recorded, at lines {silent}"


class TestAFailedDeleteIsNotASkip:
    def test_a_refused_delete_says_why(self, monkeypatch):
        nb = RefusingNetBox(refuse_deletes=True)
        obj = nb.seed("ipam/vlans", {"vid": 10})
        with netbox_guard.for_list("Lab"):
            assert nc._nb_delete(nb, "http://nb.invalid", "ipam/vlans/", obj["id"]) is False
        assert "HTTP 409" in nc.last_delete_failure()

    def test_removal_reports_failures_apart_from_skips(self):
        src = inspect.getsource(nc)
        assert '"reason": "delete failed"' not in src, \
            "a failed delete must not share the skip bucket"
        # 3 since C130: the removal loop's third is an object that could not
        # be READ, which is neither gone nor deleted.
        assert src.count('failed.append({"endpoint": endpoint, "id": obj_id,') == 3
        assert src.count('"failed": failed,') >= 2


class TestTheOutcomeReachesTheScreen:
    """C85. C8's fix landed in the stored summary and never reached the
    screen: the sync card read `failed` and drew green. The import's outcome
    is now a RESULT (7.1 step 2), levelled by `complete`, with every write
    that did not land named."""

    def _summary(self, **over):
        s = {"total": 3, "synced": 3, "created": 1, "updated": 2, "site": "lab",
             "timestamp": "2026-09-27 12:00:00", "failed": [], "write_failures": [],
             "partial": [], "complete": True}
        s.update(over)
        return s

    def test_a_complete_import_is_green(self):
        from modules.preview_confirm import netbox_sync_result

        assert netbox_sync_result(self._summary())["level"] == "success"

    def test_a_partial_import_names_each_write_and_is_not_green(self):
        from modules.preview_confirm import netbox_sync_result

        wf = [{"device": "r2", "write": "cable Gi2 -> s4:Gi1/0", "error": "400 refused"},
              {"device": "r2", "write": "primary_ip4", "error": "409"}]
        r = netbox_sync_result(self._summary(write_failures=wf, partial=["r2"], complete=False))
        assert r["level"] == "partial"
        item = next(i for i in r["did_not"]["items"] if i["target"] == "r2")
        assert item["lines"] == ["cable Gi2 -> s4:Gi1/0: 400 refused", "primary_ip4: 409"]

    def test_a_summary_older_than_the_counting_is_unknown_never_green(self):
        from modules.preview_confirm import netbox_sync_result

        old = self._summary()
        for k in ("write_failures", "partial", "complete"):
            old.pop(k)
        r = netbox_sync_result(old)
        assert r["level"] != "success"
        assert any(i["kind"] == "uncounted" for i in r["did_not"]["items"])

    def test_the_status_route_carries_the_result(self, monkeypatch, tmp_path):
        import json as _json

        import app as A
        from modules import netbox_client as nb

        path = tmp_path / "netbox_sync_status.json"
        path.write_text(_json.dumps({"lists": {"Default": self._summary(
            write_failures=[{"device": "r2", "write": "vlan 100", "error": "x"}],
            partial=["r2"], complete=False)}}), encoding="utf-8")
        monkeypatch.setattr(nb, "_SYNC_STATUS_FILE", str(path))
        body = A.app.test_client().get("/netbox/status").get_json()
        result = body["status"]["lists"]["Default"]["result"]
        assert result["level"] == "partial"
        # The write path never persists a result: the file is unchanged.
        assert "result" not in _json.loads(path.read_text())["lists"]["Default"]

    def test_the_sync_card_takes_its_colour_from_the_result(self):
        """The screen half of C85, from the shipped source: the badge is the
        result's level and the outcome is drawn by the component."""
        from tests.payload_render import lift, shipped

        card = lift(shipped("index.4.js"), "loadNetboxTab")
        assert "previewConfirmResultLevel(summary.result)" in card
        assert "previewConfirmResultHtml(summary.result" in card
        assert "summary.failed && summary.failed.length ? 'warning text-dark' : 'success'" not in card

    def test_every_summary_key_the_card_reads_is_carried(self, monkeypatch, tmp_path):
        """The card drew `scanned 0/9` beside `devices updated 9` for every
        import: it read `summary.scanned`, a key the summary never carried
        (it carries `synced`), and `|| 0` drew the miss as a zero (the
        operator's reading, 2026-09-28). The payload check's reverse direction
        sees depth-one reads only, and this is a nested one. So: every
        `summary.<key>` the card reads is a key the REAL stored summary carries."""
        import re

        from tests import payload_providers as P
        from tests.payload_render import lift, shipped

        card = lift(shipped("index.4.js"), "loadNetboxTab")
        reads = set(re.findall(r"\bsummary\.([a-z_]+)", card))
        carried = set(P.netbox_status(monkeypatch, tmp_path)["status"]["lists"]["Default"])
        assert len(reads) >= 6, reads
        assert reads - carried == set(), f"read and never carried: {reads - carried}"
