"""C54: a rotation row is derived from the audit AND from where the device is known.

The rotation audit is append-only, so a device that left kept its row for
ever: after P.6's teardown `rotation:bp-ztp-a` read `ok` about a device
destroyed a day earlier, and one whose last record was NOT safe would have read
`not_safe_to_reboot` for ever, cleared by nothing. Needs attention (7.2) is
built on these rows. The live instance, left on the host deliberately on
2026-09-28: `rotation:probe-r1a`, whose list R1's teardown deletes.
"""

import json
import os

from modules import job_health as J
from modules.nsot import credential_rotation as cr

#: probe-r1a's LAST record on the host, as rotation_audit.jsonl holds it.
PROBE = {"at": "2026-09-28T07:02:44Z", "device": "probe-r1a",
         "state": cr.ROTATED_PERSISTED, "via": "onboarding phase 2"}
UNSAFE = {"at": "2026-09-27T03:00:00Z", "device": "bp-gone",
          "state": cr.ROTATED_UNVERIFIED, "failed_stage": "device_startup_config"}
MANAGED = {"at": "2026-09-27T04:00:22Z", "device": "s1", "state": cr.ROTATED_UNVERIFIED,
           "failed_stage": "device_startup_config"}


def _rows(records, known):
    return {r["unit"]: r for r in J.rotation_rows(records=records, known=known)}


def test_a_device_still_known_keeps_its_verdict_and_one_that_left_is_departed():
    """R1's instance, before and after its list is deleted."""
    before = _rows([PROBE, MANAGED], ({"probe-r1a", "s1"}, ""))
    assert before["rotation:probe-r1a"]["state"] == "ok"
    after = _rows([PROBE, MANAGED], ({"s1"}, ""))
    gone = after["rotation:probe-r1a"]
    assert gone["state"] == "departed", gone
    assert "left management" in gone["detail"] and cr.ROTATED_PERSISTED in gone["detail"]
    assert after["rotation:s1"]["state"] == "not_safe_to_reboot", \
        "a device still managed keeps its verdict (the floor)"


def test_a_departed_device_whose_last_record_was_unsafe_says_so():
    """The case C54 was about: never a permanent not_safe_to_reboot nobody
    can clear, and never silence about what the last record said."""
    row = _rows([UNSAFE], ({"s1"}, ""))["rotation:bp-gone"]
    assert row["state"] == "departed"
    assert "NOT safe to reboot" in row["detail"] and "nothing here manages it" in row["detail"]


def test_an_unknown_known_set_calls_nothing_departed():
    """The floor against the vacuous reading: no device known anywhere (an
    unread store, or the test store) must not turn every row into
    "departed". The verdict stands."""
    rows = _rows([PROBE, UNSAFE], (set(), "no device is known in any list"))
    assert {r["state"] for r in rows.values()} == {"ok", "not_safe_to_reboot"}, rows


def test_a_partial_read_calls_nothing_departed_and_says_why():
    rows = _rows([UNSAFE], ({"s1"}, "could not read Lab: manifest (OSError)"))
    row = rows["rotation:bp-gone"]
    assert row["state"] == "not_safe_to_reboot", row
    assert "whether it has left management is unknown" in row["detail"]


def test_the_known_set_comes_from_the_inventory_and_the_manifest(monkeypatch, tmp_path):
    """A pending device (manifest, no inventory row) has not left; the match
    ignores case."""
    from modules import device

    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    repo = tmp_path / "lab" / "config_repo" / ".nsot"
    repo.mkdir(parents=True)
    (repo / "manifest.json").write_text(json.dumps(
        {"devices": {"uid:1": {"name": "BP-Pending"}}}), encoding="utf-8")
    (tmp_path / "lab" / "devices.csv").write_text("hostname\n", encoding="utf-8")
    monkeypatch.setattr(device, "get_device_lists",
                        lambda: [{"name": "Lab", "filename": "lab"}])
    monkeypatch.setattr(device, "load_saved_devices",
                        lambda p: [{"hostname": "R1"}] if p.endswith("devices.csv") else [])
    names, why = J.known_devices()
    assert why == "" and names == {"r1", "bp-pending"}, (names, why)


def test_the_headline_counts_a_departed_row_and_does_not_call_it_a_fault():
    row = _rows([PROBE], ({"s1"}, ""))["rotation:probe-r1a"]
    out = J.health(images=[], settings=[], rotations=[row], owner=[], ztp=[],
                    responder=[], startup=[], sessions=[], version=[], run=lambda *a, **k: (0, ""))
    assert "rotation:probe-r1a" not in out["not_ok"]
    assert "about a device that has left management" in out["headline"], out["headline"]
