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

from tests.js_source import read_shipped

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# The population tests (a device the ref predates is named; the denominator is
# the inventory) moved to tests/test_golden_restore.py,
# TestTheInventoryIsThePopulation, when P.3 step 5 (register C23) put the rule
# into build_targets() and deleted plan_restore(): no route called it, so the
# tests here were testing a function the operator's preview never ran.


class TestTheSurvey:
    """**How many other readers iterate an artefact where the inventory is
    the right population.** Asked for explicitly; the answer is recorded
    here so it is not re-derived.

    Three, of which two are fixed:

    * `drift_check` — corrected in Phase 3.3, every device in exactly one
      bucket;
    * the restore preview: fixed in `restore.plan_restore()`, which no route
      called (C23), and fixed for real in `build_targets()` by P.3 step 5;
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


class TestThePanelDRAWSTheCoverage:
    """**I computed it and drew nothing.**

    Step 1 taught `/golden/baselines` to return `partial`, `inventory_size`
    and `missing_devices`, and the panel rendered `${b.device_count}
    device(s)` exactly as before — a value carried to the browser and drawn
    nowhere, **in the commit whose whole purpose was to fix a
    coverage-reporting gap**.

    That is `loadOnboardPending` having no caller and `nbCascadeHtml` never
    being called, for the fourth time in this session, and the first where I
    introduced it rather than found it.
    """

    @staticmethod
    def _source():
        path = os.path.join(ROOT, "templates", "partials", "golden_repo.html")
        page = read_shipped(path)
        out = []
        for name in ("_gEsc", "_gBaselineCoverage"):
            start = page.index(f"function {name}(")
            depth, i, seen = 0, page.index("{", start), False
            while i < len(page):
                if page[i] == "{":
                    depth += 1
                    seen = True
                elif page[i] == "}":
                    depth -= 1
                    if seen and depth == 0:
                        break
                i += 1
            out.append(page[start:i + 1])
        return "\n".join(out)

    def _render(self, baseline):
        import json

        dukpy = pytest.importorskip("dukpy")
        return dukpy.evaljs(self._source()
                            + f"\n_gBaselineCoverage({json.dumps(baseline)})")

    def test_a_partial_baseline_says_partial_and_names_what_it_predates(self):
        html = self._render({"device_count": 9, "inventory_size": 10,
                             "partial": True, "missing_devices": ["r6"]})

        assert "partial" in html
        assert "9 of 10" in html
        assert "r6" in html, "it does not say WHICH device"
        assert "warning" in html, "it renders as an ordinary count"

    def test_a_complete_baseline_is_a_plain_count(self):
        """**The floor.** A renderer that always warned would satisfy the
        test above and train the operator to ignore the badge."""
        html = self._render({"device_count": 10, "inventory_size": 10,
                             "partial": False, "missing_devices": []})

        assert "10 device(s)" in html
        assert "partial" not in html
        assert "warning" not in html

    def test_many_missing_devices_are_summarised_not_dumped(self):
        html = self._render({"device_count": 2, "inventory_size": 10,
                             "partial": True,
                             "missing_devices": [f"d{i}" for i in range(8)]})

        assert "+4 more" in html
        assert "2 of 10" in html

    def test_an_OLD_payload_without_the_fields_still_renders(self):
        """A cached response from before step 1 carries no `partial`."""
        html = self._render({"device_count": 9})
        assert "9 device(s)" in html

    def test_the_renderer_is_actually_CALLED_by_the_table(self):
        """The check that caught this class last time. Counted excluding the
        definition, so existing is not mistaken for being used."""
        path = os.path.join(ROOT, "templates", "partials", "golden_repo.html")
        page = read_shipped(path)

        defs = page.count("function _gBaselineCoverage(")
        calls = page.count("_gBaselineCoverage(") - defs
        assert defs == 1
        assert calls >= 1, "computed, carried to the browser, drawn nowhere"
        assert "${_gBaselineCoverage(b)}" in page


class TestABootstrapConfigRoundTripsCleanly:
    """**Whether the cohort's approval can be re-granted at all.**

    Onboarding binds the new device to its platform template at Create, so
    `cisco_iosxe/base.j2` cannot be approved again until every bound device
    — including the new one — round-trips. If a bootstrap-shaped config did
    not, the cohort's deploy path would stay offline until the device was
    configured further, which is a materially different operational answer.

    Measured: **100% modeled coverage, zero unmodelled, nothing missing or
    extra.** The one line that does not survive the round-trip is the
    generator's own banner comment, and IOS does not retain `!` comments in
    `show running-config`, so a **capture** does not carry it.
    """

    def _bootstrap(self):
        from modules.nsot import bootstrap_config

        return bootstrap_config.render_bootstrap(
            "cisco_iosxe", hostname="r6", username="admin",
            secret="$9$abc123", domain="rcn.lab",
            manager_interface="GigabitEthernet2",
            manager_address="10.255.0.32", manager_mask="255.255.255.0")

    def test_a_captured_bootstrap_round_trips_at_100_percent(self):
        from modules.nsot import roundtrip
        from modules.nsot.parsers import get_parser

        capture = "\n".join(l for l in self._bootstrap().splitlines()
                            if not l.strip().startswith("! ")) + "\n"
        parsed = get_parser("cisco_iosxe").parse(capture)
        report = roundtrip.compare(
            capture, roundtrip.render(parsed, "cisco_iosxe", None), parsed)

        assert report["ok"] is True, report["details"]
        assert report["modeled_coverage"] == 100.0
        assert report["unmodeled"] == 0

    def test_the_only_unrenderable_line_is_the_generator_s_comment(self):
        """Named, so that if this ever fails it is obvious whether a NEW
        construct appeared or the comment handling changed."""
        from modules.nsot import roundtrip
        from modules.nsot.parsers import get_parser

        text = self._bootstrap()
        parsed = get_parser("cisco_iosxe").parse(text)
        report = roundtrip.compare(
            text, roundtrip.render(parsed, "cisco_iosxe", None), parsed)

        missing = [m["line"] for m in report["details"]["missing"]]
        assert missing == ["! minimal bootstrap - management plane only"], missing
