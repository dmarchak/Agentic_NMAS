"""Stage 4C.6 — a device is drift-covered the moment it is in the inventory.

After 3.3b the drift population **is the inventory**, so enrolment is not a
step somebody has to remember: a device becomes covered when it is onboarded,
not when a golden appears.

**That is exactly what was silently wrong before Stage 3.3.** A device
onboarded after the migration would have had a golden in `config_repo/`, no
file in the legacy store, and been invisible to the checker — not an error,
not a skip, simply absent from the counts, with "all 9 device(s) clean" over
a ten-device inventory reading identically to the same sentence over nine.

Three things are proved here, and the third is the one that could not have
been written in 3.3b:

1. between inventory insert and first capture the device is **named** with
   *"no golden config saved"* — on the panel, executed, not just in the
   payload;
2. once captured, coverage reads **`checked N+1 of N+1`**;
3. the 3.3b negative control, re-run **against a device that did not exist
   when 3.3b was written**.
"""

import json
import re

import pytest

from tests.js_source import with_loaded_scripts

dukpy = pytest.importorskip("dukpy")

NEW = "bp-onboard-c"


def _device(name, ip):
    return {"hostname": name, "ip": ip, "username": "u", "password": "p",
            "device_type": "cisco_xe", "platform": "cisco_iosxe"}


@pytest.fixture
def fleet(monkeypatch):
    """Nine devices, all captured and clean — then a tenth is onboarded."""
    from modules import drift_check

    nine = [_device(f"r{i}", f"203.0.113.{i}") for i in range(1, 10)]
    goldens = {d["ip"]: "hostname x\n!\nend\n" for d in nine}
    inventory = list(nine)

    monkeypatch.setattr("modules.device.get_current_device_list",
                        lambda: ("lab", "lab.csv"))
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda p: list(inventory))
    monkeypatch.setattr("modules.ai_assistant._load_golden_config_file",
                        lambda ip: goldens.get(ip))
    monkeypatch.setattr("modules.connection.get_persistent_connection",
                        lambda d, pool, lock: d["ip"])
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, cmd: "hostname x\n!\nend\n")
    monkeypatch.setattr("modules.approval_queue.add_approval",
                        lambda **kw: {"ok": True})

    return {"module": drift_check, "inventory": inventory,
            "goldens": goldens,
            "onboard": lambda: inventory.append(_device(NEW, "203.0.113.60")),
            # The capture matches what the stub device returns, because a
            # golden IS a capture. The first version wrote different text and
            # the device read as drifted the moment it was onboarded -- the
            # code being right and the fixture being wrong.
            "capture": lambda: goldens.__setitem__("203.0.113.60",
                                                   "hostname x\n!\nend\n"),
            "capture_stale": lambda: goldens.__setitem__(
                "203.0.113.60", "hostname x\n!\nip route 0.0.0.0 0.0.0.0 Null0\nend\n")}


class TestEnrolmentIsImmediate:
    """Not "when a golden appears" — when the device is in the inventory."""

    def test_nine_devices_read_nine_of_nine(self, fleet):
        result = fleet["module"].run_drift_check("test")
        assert (result["inventory"], result["checked"]) == (9, 9)

    def test_onboarding_moves_the_denominator_at_once(self, fleet):
        fleet["onboard"]()
        result = fleet["module"].run_drift_check("test")
        assert result["inventory"] == 10, (
            "a device in the inventory is drift-covered; it did not have to "
            "wait for a capture to be counted")

    def test_the_new_device_lands_in_exactly_one_bucket(self, fleet):
        fleet["onboard"]()
        result = fleet["module"].run_drift_check("test")
        buckets = ([d["hostname"] for d in result["skipped"]]
                   + [d["hostname"] for d in result["errors"]]
                   + [d["hostname"] for d in result["drifted_devices"]])
        assert buckets.count(NEW) == 1

    def test_every_device_is_still_accounted_for(self, fleet):
        fleet["onboard"]()
        result = fleet["module"].run_drift_check("test")
        assert (result["checked"] + len(result["skipped"])
                + len(result["errors"])) == 10


class TestBeforeTheFirstCaptureItIsNAMED:
    """"Not yet captured" and "invisible" are different states, and only one
    of them is acceptable."""

    def test_the_reason_is_no_golden_config(self, fleet):
        fleet["onboard"]()
        result = fleet["module"].run_drift_check("test")
        reasons = {d["hostname"]: d["reason"] for d in result["skipped"]}
        assert NEW in reasons
        assert "no golden config" in reasons[NEW]

    def test_it_is_not_counted_as_checked(self, fleet):
        fleet["onboard"]()
        result = fleet["module"].run_drift_check("test")
        assert result["checked"] == 9

    def test_the_summary_states_the_coverage(self, fleet):
        fleet["onboard"]()
        result = fleet["module"].run_drift_check("test")
        assert "checked 9 of 10" in result["summary"]

    def test_and_names_it(self, fleet):
        fleet["onboard"]()
        result = fleet["module"].run_drift_check("test")
        assert NEW in result["summary"]


class TestThePanelNamesItToo:
    """**On the panel, executed** — not just in the payload.

    Third renderer extracted for this reason, after the agent panel and the
    onboarding wizard: a test against the payload cannot see a screen that
    does not draw it.
    """

    @pytest.fixture(scope="class")
    def js(self):
        import app as nmas

        page = with_loaded_scripts(nmas.app.test_client().get("/").get_data(as_text=True))
        start = page.index("function driftDetailHtml(")
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
        return page[start:i + 1]

    def _html(self, js, payload):
        return dukpy.evaljs(js + f"\ndriftDetailHtml({json.dumps(payload)});")

    def test_the_uncaptured_device_is_on_screen(self, js, fleet):
        fleet["onboard"]()
        result = fleet["module"].run_drift_check("test")
        html = self._html(js, {"last_run": result})
        assert NEW in html
        assert "no golden config" in html

    def test_the_coverage_is_on_screen(self, js, fleet):
        fleet["onboard"]()
        result = fleet["module"].run_drift_check("test")
        flat = re.sub(r"\s+", " ", self._html(js, {"last_run": result}))
        assert "checked 9 of 10" in flat

    def test_it_is_labelled_not_checked_rather_than_omitted(self, js, fleet):
        fleet["onboard"]()
        result = fleet["module"].run_drift_check("test")
        assert "Not checked:" in self._html(js, {"last_run": result})

    def test_a_full_pass_shows_the_full_count(self, js, fleet):
        fleet["onboard"]()
        fleet["capture"]()
        result = fleet["module"].run_drift_check("test")
        flat = re.sub(r"\s+", " ", self._html(js, {"last_run": result}))
        assert "checked 10 of 10" in flat
        assert "Not checked:" not in flat


class TestOnceCapturedCoverageIsComplete:

    def test_checked_ten_of_ten(self, fleet):
        fleet["onboard"]()
        fleet["capture"]()
        result = fleet["module"].run_drift_check("test")
        assert (result["inventory"], result["checked"]) == (10, 10)
        assert "checked 10 of 10" in result["summary"]

    def test_nothing_is_skipped(self, fleet):
        fleet["onboard"]()
        fleet["capture"]()
        assert fleet["module"].run_drift_check("test")["skipped"] == []

    def test_the_new_device_is_clean(self, fleet):
        fleet["onboard"]()
        fleet["capture"]()
        result = fleet["module"].run_drift_check("test")
        assert result["clean"] == 10
        assert result["drifted"] == 0

    def test_a_newly_onboarded_device_can_also_be_DRIFTED(self, fleet):
        """Enrolment means covered, not assumed clean. A device whose golden
        was captured before a change is drifted like any other — and the
        first capture is exactly when that is most likely."""
        fleet["onboard"]()
        fleet["capture_stale"]()
        result = fleet["module"].run_drift_check("test")
        assert result["inventory"] == 10
        assert result["checked"] == 10
        assert [d["hostname"] for d in result["drifted_devices"]] == [NEW]


class TestThe33bControlAgainstADeviceThatDidNotExistThen:
    """3.3b's own negative control, re-run against the case it was written to
    prevent but could not test: a device onboarded afterwards.

    Point the population back at `_list_golden_configs()` — the legacy
    enumerator — and the newly onboarded device vanishes from the counts
    entirely. Not an error, not a skip: **absent**, with the total silently
    dropping to nine and the sentence reading exactly as it did before.
    """

    def test_the_legacy_population_loses_the_new_device(self, fleet,
                                                        monkeypatch):
        fleet["onboard"]()
        fleet["capture"]()

        legacy = [{"device_ip": d["ip"], "hostname": d["hostname"]}
                  for d in fleet["inventory"] if d["hostname"] != NEW]
        monkeypatch.setattr("modules.ai_assistant._list_golden_configs",
                            lambda: legacy)

        # What 3.3b replaced: the golden store as the population.
        population = [d for d in fleet["inventory"]
                      if d["ip"] in {e["device_ip"] for e in legacy}]
        assert NEW not in [d["hostname"] for d in population]
        assert len(population) == 9, (
            "the device is invisible to the legacy enumerator — this is the "
            "state 3.3b removed, reproduced against a device that did not "
            "exist when 3.3b was written")

    def test_and_the_inventory_population_keeps_it(self, fleet, monkeypatch):
        """The same fixture, the real code: 10 of 10."""
        fleet["onboard"]()
        fleet["capture"]()
        monkeypatch.setattr("modules.ai_assistant._list_golden_configs",
                            lambda: [])           # the legacy store is empty
        result = fleet["module"].run_drift_check("test")
        assert result["inventory"] == 10
        assert result["checked"] == 10, (
            "the legacy store says nothing and the inventory says ten — the "
            "drift check must follow the inventory")

    def test_the_counts_would_have_agreed_with_themselves(self, fleet,
                                                          monkeypatch):
        """Why it was invisible: nine of nine is a true sentence about the
        wrong population, and reads identically to nine of ten."""
        nine = fleet["module"].run_drift_check("test")
        fleet["onboard"]()
        fleet["capture"]()
        ten = fleet["module"].run_drift_check("test")
        assert "checked 9 of 9" in nine["summary"]
        assert "checked 10 of 10" in ten["summary"]
        assert nine["summary"] != ten["summary"], (
            "the coverage figure is what makes the two distinguishable")
