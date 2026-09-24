"""The interface at 900 devices. Numbers, not aspirations.

**Nine devices will pass every test written at nine devices**, so this file
pins what the interface actually costs at scale, measured 2026-09-23 with
`scripts/nmas-scale-report`.

It asserts the **status quo**, deliberately. The page grows linearly with the
inventory today; a test asserting it does not would fail immediately and be
deleted. So the marginal cost is pinned instead, and the day somebody bounds
the device list this test **fails and has to be updated with a new number** —
which is the point. A bound that improves things should have to be recorded.

Nothing here writes into `data/lists/`: `fleet_scale.write_csv()` refuses a
path under it, and these tests build in `tmp_path`.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures.fleet_scale import (STATE_MIX, build_fleet, expected_counts,
                                  write_csv)

#: Measured 2026-09-23. Update with a new measurement, never by widening.
#:
#: **Re-measured 2026-09-24 after Stage 7 §0b.** 275 KB of pure inline
#: script moved from the templates into `static/js/gen/`, so the HTML can be
#: declared uncacheable (§6c) without re-sending the script on every
#: navigation. The document dropped **647,383 -> 365,417 bytes fixed**, a
#: 44% reduction.
#:
#: **The total first load did not shrink** -- 656,200 bytes in one
#: uncacheable document became 378,052 of HTML plus 284,662 of JavaScript,
#: which is marginally MORE. That is the point and not a disappointment:
#: the 284,662 is now cacheable and the 378,052 is not, where before a
#: single figure had to be one or the other. The number that improves on a
#: second visit went from **zero to 43%**.
#:
#: §0b's own claim is unchanged and still the bigger one: the fixed cost is
#: 97% of a nine-device page and is re-sent before a single device row.
#: Moving it did not make it smaller, it made it cacheable.
FIXED_PAGE_BYTES = 365_417
EXTRACTED_SCRIPT_BYTES = 284_662
BYTES_PER_DEVICE = 2_239
TOLERANCE = 0.25


class TestTheFleetIsRealisticallyMixed:
    """A uniform fleet renders fast and proves nothing: it is the mixture
    that forces filtering, because a list where every row looks the same
    needs no filter."""

    def test_it_builds_the_size_asked_for(self):
        assert len(build_fleet(900)) == 900

    def test_every_state_is_represented(self):
        counts = expected_counts(build_fleet(900))
        for state in STATE_MIX:
            assert counts[state] > 0, state

    def test_no_state_dominates(self):
        """A fleet that is 95% healthy makes the unhealthy rows hard to find,
        which is realistic — but a fixture where one state is everything
        cannot exercise a filter."""
        counts = expected_counts(build_fleet(900))
        worst = max(counts[s] for s in STATE_MIX)
        assert worst < 0.7 * 900

    def test_sites_platforms_and_roles_all_vary(self):
        fleet = build_fleet(900)
        assert len({d["site"] for d in fleet}) >= 10
        assert len({d["platform"] for d in fleet}) == 2
        assert len({d["role"] for d in fleet}) == 4

    def test_addresses_are_distinct(self):
        """A fixture with colliding addresses would make every by-IP lookup
        in the suite mean something different."""
        fleet = build_fleet(900)
        assert len({d["ip"] for d in fleet}) == 900

    def test_it_is_deterministic(self):
        """A scale measurement that moves between runs cannot be compared to
        the one recorded yesterday."""
        assert build_fleet(200) == build_fleet(200)

    def test_the_platforms_are_dialects_not_slugs(self):
        from modules.nsot.platform import is_dialect

        assert all(is_dialect(d["platform"]) for d in build_fleet(90))


class TestItCannotTouchTheLiveData:
    """The operational form of the conftest guard."""

    def test_writing_under_the_live_lists_dir_is_refused(self, tmp_path):
        from modules.config import LISTS_DIR

        with pytest.raises(ValueError) as excinfo:
            write_csv(os.path.join(LISTS_DIR, "scale", "devices.csv"),
                      build_fleet(5))
        assert "refusing" in str(excinfo.value)

    def test_writing_under_tmp_is_fine(self, tmp_path):
        path = write_csv(str(tmp_path / "devices.csv"), build_fleet(5))
        assert os.path.exists(path)


class TestTheReadIsNotTheCost:
    """75 unbounded `load_saved_devices()` call sites, and treating them as 75
    equal work items would spend the effort in the wrong place.

    Measured at 900 devices: the read is **0.73 ms**. What costs is what
    follows it — a golden file read per device is 0.3 s, a `git log` per
    device is 7.2 s, an SSH round trip per device is 225 s.
    """

    def test_reading_900_devices_is_fast(self, tmp_path):
        import time

        from modules.device import load_saved_devices

        path = write_csv(str(tmp_path / "devices.csv"), build_fleet(900))
        load_saved_devices(path)                       # warm
        start = time.perf_counter()
        rows = load_saved_devices(path)
        elapsed = time.perf_counter() - start

        assert len(rows) == 900
        assert elapsed < 0.05, (
            f"the read took {elapsed*1000:.1f} ms — if this ever becomes the "
            "cost, the conclusion in NSOT_STAGE7_GUI.md §0a changes")

    def test_a_lookup_after_the_read_is_free(self, tmp_path):
        import time

        from modules.device import load_saved_devices

        path = write_csv(str(tmp_path / "devices.csv"), build_fleet(900))
        rows = load_saved_devices(path)
        start = time.perf_counter()
        next((r for r in rows if r["ip"] == rows[-1]["ip"]), None)
        assert time.perf_counter() - start < 0.01


class TestThePageGrowsWithTheInventory:
    """Asserting the STATUS QUO. The day somebody bounds the device list this
    fails and must be updated with a new number."""

    @pytest.fixture(scope="class")
    def measured(self):
        from scripts_scale_helper import render_sizes

        return render_sizes([9, 900])

    def test_the_page_carries_every_device(self, measured):
        small, large = measured[9], measured[900]
        marginal = (large["bytes"] - small["bytes"]) / (900 - 9)
        assert abs(marginal - BYTES_PER_DEVICE) < BYTES_PER_DEVICE * TOLERANCE, (
            f"the per-device page cost is now {marginal:.0f} bytes, not "
            f"{BYTES_PER_DEVICE}. If the list was bounded, that is good news "
            "— record the new number here rather than widening the tolerance.")

    def test_the_fixed_cost_is_shipped_on_every_load(self, measured):
        """Its own finding, and nothing to do with scale: a third of a
        megabyte of markup before the first device row."""
        small = measured[9]
        fixed = small["bytes"] - BYTES_PER_DEVICE * 9
        assert abs(fixed - FIXED_PAGE_BYTES) < FIXED_PAGE_BYTES * TOLERANCE

    def test_the_extracted_script_is_no_longer_in_the_document(self):
        """**The §0b acceptance**, and the reason the figure above moved.

        Pinned as a number for the same reason the page cost is: a later
        change that quietly inlines a block again must update this line
        rather than pass."""
        import glob
        import os as _os

        total = sum(_os.path.getsize(f)
                    for f in glob.glob("static/js/gen/*.js"))
        assert total > 200_000, (
            f"only {total} bytes are extracted — the inline script has "
            "returned to the templates")
        assert abs(total - EXTRACTED_SCRIPT_BYTES) < EXTRACTED_SCRIPT_BYTES * TOLERANCE

    def test_one_render_reads_the_whole_inventory(self, measured):
        """Cheap today — 0.73 ms — and recorded so the claim in §0a is
        checkable rather than remembered."""
        assert measured[900]["loads"] >= 1
