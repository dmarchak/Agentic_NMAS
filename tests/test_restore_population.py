"""The inventory is the population for a restore preview, not the ref.

**Found while pricing r6.** A tenth device joining the Default list makes
every existing baseline a partial restore point, and `restore.plan_restore()`
iterated `devices_at(ref)` — the devices **at the ref**. A device onboarded
after the tag was therefore **absent from the preview entirely**: not an
error, not a skip, not named. The summary read *"Restoring 9 of 9
device(s)"* over a ten-device fleet.

Textually the drift checker's *"all 9 device(s) clean"* over a ten-device
inventory, which this project corrected in Phase 3.3 and which arrived again
in a different reader.

**The tag decision was right all along and disagreed with the preview.**
`routes/deploy.py::_baseline_earned()` reads the current inventory and
refuses the tag naming the device (*"1 device(s) were not measured against
…: ['r6']"*), while the screen the operator confirms from said nothing. Two
readers of one question, one correct, and the correct one is not the one a
person looks at.
"""

import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def world(monkeypatch, tmp_path):
    """A ref holding nine goldens, an inventory holding ten."""
    from modules.nsot import restore

    nine = [f"r{i}" for i in range(1, 6)] + [f"s{i}" for i in range(1, 5)]
    monkeypatch.setattr(restore._repo, "devices_at", lambda repo, ref: list(nine))
    monkeypatch.setattr(restore, "_repo_for", lambda ln: str(tmp_path))
    os.makedirs(tmp_path / ".git", exist_ok=True)
    monkeypatch.setattr(
        restore, "_devices_of",
        lambda ln: [{"hostname": h, "ip": f"10.255.1.{i + 10}"}
                    for i, h in enumerate(nine + ["r6"])])
    monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln: False)
    return {"nine": nine, "restore": restore}


class TestADeviceTheRefPredatesIsNamed:
    def test_it_appears_in_the_preview_at_all(self, world):
        out = world["restore"].plan_restore("Default", "baseline/2026")

        named = {s["hostname"] for s in out["skipped"]}
        assert "r6" in named, "the tenth device is absent from the preview"

    def test_with_a_reason_that_says_what_will_happen_to_it(self, world):
        out = world["restore"].plan_restore("Default", "baseline/2026")

        row = next(s for s in out["skipped"] if s["hostname"] == "r6")
        assert row["reason"] == "not in this baseline"
        assert "predates" in row["detail"]
        assert "leave it exactly as it is" in row["detail"]
        assert row["not_at_ref"] is True

    def test_the_summary_denominator_is_the_INVENTORY(self, world):
        """*"Restoring 9 of 9"* reads as complete. It was, of the ref."""
        out = world["restore"].plan_restore("Default", "baseline/2026")

        assert "of 10 device(s)" in out["summary"], out["summary"]
        assert out["inventory_size"] == 10

    def test_the_ref_is_flagged_partial(self, world):
        out = world["restore"].plan_restore("Default", "baseline/2026")
        assert out["partial"] is True

    def test_a_ref_covering_the_WHOLE_fleet_is_not_partial(
            self, world, monkeypatch):
        """**The floor.** A preview that always said "partial" would satisfy
        every assertion above and mean nothing."""
        from modules.nsot import restore

        monkeypatch.setattr(restore._repo, "devices_at",
                            lambda repo, ref: world["nine"] + ["r6"])

        out = restore.plan_restore("Default", "baseline/2026")
        assert out["partial"] is False
        assert not [s for s in out["skipped"] if s.get("not_at_ref")]
        assert "of 10 device(s)" in out["summary"]

    def test_a_single_device_restore_does_not_report_the_others(self, world):
        """Asking for one device is not a claim about the fleet, so the
        other nine are not "missing" from it."""
        out = world["restore"].plan_restore("Default", "baseline/2026",
                                            devices=["r1"])
        assert not [s for s in out["skipped"] if s.get("not_at_ref")]


class TestTheSurvey:
    """**How many other readers iterate an artefact where the inventory is
    the right population.** Asked for explicitly; the answer is recorded
    here so it is not re-derived.

    Three, of which two are fixed:

    * `drift_check` — corrected in Phase 3.3, every device in exactly one
      bucket;
    * `restore.plan_restore()` — this file;
    * `routes/golden.py`'s Baselines panel — `device_count` came from
      `devices_at()` with no reference to the inventory, so an older
      baseline read *9* and a newer one *10* with nothing saying the first
      covers less than the network does now. **A number is not a
      statement.**

    Correct as they are, and listed so the next survey does not re-check
    them:

    * `_baseline_earned()` reads the current inventory;
    * `event_monitor` iterates the **inventory** and looks the artefact up
      (`[ip for ip in device_ips if ip not in golden_ips]`) — the right way
      round;
    * `check_runner` and `pipeline_builder` generate CI checks from goldens,
      where the artefact genuinely is the population: you cannot verify a
      device you hold no reference for. **Neither states its coverage**,
      which is a smaller version of the same thing and is recorded rather
      than fixed;
    * `routes/deploy.py` and `routes/templates.py` use `next(...)` to find
      one device — lookups, not populations;
    * `routes/templatize.py`'s fleet validation report iterates goldens and
      drops a device with an unreadable one via a bare `continue`. Same
      shape, and **the honest answer is that it is a fourth instance**, left
      for when that panel is next touched rather than fixed blind here.
    * `ai_assistant`'s copies are Stage 8 and already recorded as deferred.
    """

    def test_the_panel_reports_coverage_against_the_inventory(self):
        import inspect

        from routes import golden

        src = inspect.getsource(golden)
        assert "missing_devices" in src
        assert '"partial"' in src
        assert "load_saved_devices" in src, \
            "the panel computes coverage without reading the inventory"

    def test_event_monitor_iterates_the_inventory_not_the_artefact(self):
        """The right way round, pinned so it stays that way."""
        import inspect

        from modules import event_monitor

        src = inspect.getsource(event_monitor)
        assert "for ip in device_ips if ip not in golden_ips" in src

    def test_baseline_earned_still_reads_the_current_inventory(self):
        import inspect

        from routes import deploy

        src = inspect.getsource(deploy._baseline_earned)
        assert "load_saved_devices" in src
        assert "not targeted" in src
