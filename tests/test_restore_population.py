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
      statement.** (Fixed in the route; the panel and its route left at 7.8,
      2026-10-17, and a restore's coverage is `restore.coverage`'s.)

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

    def test_the_restore_reports_coverage_against_the_inventory(self):
        """Today's Baselines panel computed it in /golden/baselines until both left at 7.8
        (2026-10-17); a restore's coverage (`restore.coverage`, which THE restore plan and
        History's Re-apply… state) reads the list's inventory, never the ref's devices."""
        import inspect

        from modules.nsot import restore

        src = inspect.getsource(restore.coverage)
        assert "inventory = _devices_of(list_name)" in src, \
            "the restore computes coverage without reading the inventory"
        assert '"partial"' in src and "not_at_ref" in src


    def test_baseline_earned_still_reads_the_current_inventory(self):
        import inspect

        from routes import deploy

        src = inspect.getsource(deploy._baseline_earned)
        # The inventory of the BATCH'S OWN list (C215), never the active one.
        assert "_devices_of(list_name)" in src and "get_current_device_list" not in src
        assert "not targeted" in src


# TestThePanelDRAWSTheCoverage (today's Baselines panel's "N of M, partial, predates …", drawn
# from /golden/baselines) left with the panel at 7.8 (2026-10-17, P7-21). History's Re-apply…
# names each device the baseline predates and counts them, "left as they are"
# (tests/test_reapply_v2.py).


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
        from modules.nsot.device_environment import Environment

        # r6 is emulated: its environment brings SSH up and injects an account, as NetBox
        # records it since C663 step 3 (a key generated in the config is not kept in a
        # capture, so a device with no environment would round-trip a line short).
        r6_env = Environment(owned_lines=("username admin privilege 15 password admin",
                                          "ip ssh maxstartups 128"), source="r6's emulator")
        return bootstrap_config.render_bootstrap(
            "cisco_iosxe", hostname="r6", username="admin",
            secret="$9$abc123", domain="rcn.lab",
            manager_interface="GigabitEthernet2",
            manager_address="10.255.0.32", manager_mask="255.255.255.0",
            environment=r6_env)

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
