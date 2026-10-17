"""The interface at 900 devices. Numbers, not aspirations.

**Nine devices will pass every test written at nine devices**, so this file
pins what the interface actually costs at scale, measured 2026-09-23 with
`scripts/nmas-scale-report`.

It asserts the **status quo**, deliberately. The page grows linearly with the
inventory today; a test asserting it does not would fail immediately and be
deleted. So the marginal cost is pinned instead, and the day somebody bounds
the device list this test **fails and has to be updated with a new number** —
which is the point. A bound that improves things should have to be recorded.

**The pages are v2's since P7-19 (2026-10-15, burn-down P7-08a)**: Needs attention, the
Devices list and a device's page, each at 9 devices and at 900, every device but the
fleet's `no_golden` ones with a committed golden (`scripts_scale_helper`). Criterion 11's
property, "no per-device work per request", is asserted as what must not move with the
fleet: processes started, files read from the network's folder, inventory reads, sockets
opened. The CPU work and the bytes that do move are pinned as numbers. Until then this
measured today's index, `/` (45,117 bytes fixed, 1,616 per device on 2026-10-15), which goes
at cutover.

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
#:
#: 205,352 since 2026-10-12: today's Configure tab (its pane, two modals and inline script,
#: about 160 kB) was removed at 7.8.
#:
#: 76,444 fixed, 1,616 per device and 199,435 extracted since 2026-10-14: the AI family
#: left (D15): base.html's AI panel, its CSS and script (about 2,000 lines), the Agent,
#: Approvals and Ansible tabs, the settings modal's AI sections, and the page's embedded copy
#: of every device (`device-full-data`, read only by the AI's device cache), which was most of
#: the per-device cost.
#:
#: 45,117 fixed since 2026-10-15: today's Settings modal (its NetBox section, the integrations
#: and security posture partials, its script), the Logs tab and the status bar left (7.8).
#: Those two figures were today's index's, and left with its measurement (P7-19, 2026-10-15);
#: the extracted script stays pinned until today's pages, the only ones loading it, go.
#:
#: 132,580 extracted since 2026-10-17: today's NetBox tab left (7.8): index.4.js's NetBox
#: section and the import and removal dialog's script (about 19 kB). It had been about
#: 151 kB, inside the 25% tolerance of 199,435, and fell outside it here.
#:
#: 83,689 extracted since 2026-10-17 (P7-21): today's Git tab, Remote card and Baselines left
#: (7.8): index.4.js, the Remote card's and the Baselines panel's scripts
#: (partials__golden_repo.2.js and .3.js) and the panel's rows in partials__golden_repo.1.js
#: (about 49 kB).
EXTRACTED_SCRIPT_BYTES = 83_689
TOLERANCE = 0.25

#: v2's pages, measured 2026-10-15 (P7-19) at 9 and 900 devices: {page: (fixed bytes, bytes
#: per device, Python calls per device)}. A page drawing no device list costs no byte per
#: device. Update with a new measurement, never by widening.
#:
#: - Needs attention: no byte per device, and about one Python call (0.8 to 1.0 measured).
#: - Devices: every row drawn (C450, 7.4's revised Devices board owed: summary, groups,
#:   paging), so bytes and calls per device; bounding it fails this, with a new number.
#:   31,250 bytes at 9 devices, 886,902 at 900; 23,416 calls at 9, 1,180,027 at 900.
#:   627 calls per device since C855 (2026-10-15), from 1,298: `_intent_of` built and
#:   compiled a pattern per device (past `re`'s 512-entry cache, every time); it reads the
#:   trailer literally now. 23,506 calls at 9, 581,965 at 900.
#: - A device's page: no byte per device, and 19 calls per device since C855 (2026-10-15),
#:   from 460 (463 with the identities below). Those were its record reading EVERY device's
#:   last measurement (`device_list.last_measured`, a pattern compiled per device in
#:   `_intent_of`) and its Credential check judging every device's rotation policy
#:   (`scheduled_rotation.device_state` over `device_states`) to draw one: 0.03 s at 9
#:   devices, 0.3 s at 900 (P7-19). Both now read the one device: 48,698 calls at 9 and
#:   461,042 at 900 before, 48,080 and 64,987 after. The 19 left is NAMED, not fixed: the
#:   manifest is one file keyed by identity, so `manifest.find_by_name` passes over the
#:   entries before the one it finds, about 7 calls an entry, three lookups a page (the
#:   header's and the Overview's `hardware`, and `intent_check`): 0.14 ms a pass beside
#:   0.5 ms to read the file, at 900 outside the profiler (2026-10-15). The measured
#:   device's entry is the manifest's LAST (`scripts_scale_helper.identity_for`), so the
#:   pin is the whole pass, never wherever a random identity sorted. Not in it: the same
#:   pass over the inventory in `device_page.find_device` (3 calls a row before the match),
#:   because the measured device is the inventory's first row.
V2_PAGES = {
    # Its fixed bytes are not pinned (None): its rows come from the reader stores every test
    # in a worker shares, 49,813 bytes alone and 88,687 mid-suite (measured 2026-10-15). What
    # moves with the fleet is read within one environment, so its per-device pins hold.
    "/v2/": (None, 0, 1),
    "/v2/devices": (22_610, 960, 627),
    "/v2/device/cor0000": (33_319, 0, 19),
}


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
        # The MEDIAN of seven reads (C463): one sample on a shared CI runner measured the
        # runner. CI read 110 ms once (run #427, 2026-10-05) where CI's interpreter here reads
        # a median 0.88 ms and a worst 5.7 ms over 200 reads. A stall hits one read; a slow
        # read is slow every time, and the median still catches it.
        times = []
        for _ in range(7):
            start = time.perf_counter()
            rows = load_saved_devices(path)
            times.append(time.perf_counter() - start)
        elapsed = sorted(times)[len(times) // 2]

        assert len(rows) == 900
        assert elapsed < 0.05, (
            f"the read took {elapsed*1000:.1f} ms (median of 7; all: "
            f"{', '.join(f'{t*1000:.1f}' for t in times)}) — if this ever becomes the "
            "cost, the conclusion in NSOT_STAGE7_GUI.md §0a changes")

    def test_a_lookup_after_the_read_is_free(self, tmp_path):
        import time

        from modules.device import load_saved_devices

        path = write_csv(str(tmp_path / "devices.csv"), build_fleet(900))
        rows = load_saved_devices(path)
        start = time.perf_counter()
        next((r for r in rows if r["ip"] == rows[-1]["ip"]), None)
        assert time.perf_counter() - start < 0.01


SIZES = (9, 900)


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    """{page: {size: cost}}, each page at 9 devices and at 900, on test_profile_apply's lab:
    built once per worker (the 900 goldens' commit is most of it, about 15 s measured
    2026-10-15), on its own MonkeyPatch, as a verified person (a module-scoped fixture runs
    before conftest's function-scoped one, and a gated control is drawn only for a viewer who
    may use it)."""
    from scripts_scale_helper import commit_goldens, measure

    import app as A
    from tests.interface_pages import as_a_verified_person
    from tests.test_profile_apply import lab_setup

    from tests.v2_context import _store_aside, _store_back

    fleet = build_fleet(max(SIZES))
    mp = pytest.MonkeyPatch()
    out = {page: {} for page in V2_PAGES}
    # C875: measured on the store a fresh install has, never what earlier tests in this worker
    # left in the shared reader stores. Needs attention draws its rows from them, and each row
    # an earlier test left was matched against the fleet, so the per-device count moved with
    # test order (+3.0, -3.3, +3.3 in four gates of one night; a warm-up request alone did not
    # hold it). The same set-aside P7-04's walk uses (tests/v2_context.py), restored exactly.
    aside = _store_aside()
    try:
        as_a_verified_person(mp)
        lab = lab_setup(mp, tmp_path_factory.mktemp("scale"))
        rows, loads = {"now": []}, {"n": 0}

        def loader(path=None):
            loads["n"] += 1
            return [dict(r) for r in rows["now"]]
        mp.setattr("modules.device.load_saved_devices", loader)
        mp.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(r) for r in rows["now"]])
        client = A.app.test_client()
        done = 0
        for size in SIZES:
            commit_goldens("Lab", fleet[done:size])
            rows["now"], done = fleet[:size], size
            for page in V2_PAGES:
                # C875: one discarded request first. A once-per-process cost (a template's
                # first compile, a cache's first fill, a record an earlier test left for the
                # first read) landed on whichever size paid it, and moved the per-device count
                # by +3.0 and -3.3 in three gates of one night while passing alone. The rule is
                # work per request at steady state, so each size is measured warm.
                client.get(page)
                out[page][size] = measure(client, page, os.path.dirname(lab["repo"]), loads)
    finally:
        mp.undo()
        _store_back(aside)
    return out


class TestAV2PageDoesNoPerDeviceWork:
    """Criterion 11 on v2 (P7-08a): a request costs the same I/O at 900 devices as at 9.
    Each count is compared exactly: one more process, file or inventory read per request at
    900 is the per-device work the rule forbids, found before a person waits for it."""

    @pytest.mark.parametrize("what", ("children", "opens", "loads", "connects"))
    def test_the_io_does_not_move_with_the_fleet(self, measured, what):
        moved = {p: (c[SIZES[0]][what], c[SIZES[-1]][what]) for p, c in measured.items()
                 if c[SIZES[0]][what] != c[SIZES[-1]][what]}
        assert moved == {}, (f"{what} per request moves with the fleet (9 devices, 900): "
                             f"{moved}")

    def test_the_measurement_saw_the_work(self, measured):
        """Floors: a measurement that counted nothing passes every check above. Every page
        reads its records through git and the network's folder (measured 2026-10-15: 3 to 11
        processes and 3 to 18 files), and no page opens a socket."""
        for page, cost in measured.items():
            small = cost[SIZES[0]]
            assert small["children"] >= 1 and small["opens"] >= 1, (page, small)
            assert small["connects"] == 0, (page, small)
            assert small["calls"] > 1_000, (page, small)

    def test_the_counters_count(self, tmp_path):
        """The control: a page that reads one file per device and starts one process per
        device is seen moving, on a throwaway app with the same measurement."""
        import subprocess as sp

        from flask import Flask
        from scripts_scale_helper import measure

        app, n = Flask("scale_probe"), {"devices": 1}
        for i in range(3):
            (tmp_path / f"d{i}.cfg").write_text("x")

        @app.route("/page")
        def page():
            for i in range(n["devices"]):
                open(tmp_path / f"d{i}.cfg", encoding="utf-8").read()
                sp.run(["true"], check=False)
            return "<p>ok</p>"
        c, loads = app.test_client(), {"n": 0}
        one = measure(c, "/page", str(tmp_path), loads)
        n["devices"] = 3
        three = measure(c, "/page", str(tmp_path), loads)
        assert (one["opens"], three["opens"]) == (1, 3)
        assert (one["children"], three["children"]) == (1, 3)
        assert three["calls"] > one["calls"]


class TestWhatMovesWithTheFleetIsPinned:
    """Asserting the STATUS QUO, per page: the fixed bytes, and the bytes and Python calls
    each device adds. The day somebody bounds the Devices list, or finds a device's manifest
    entry without a pass over the manifest, this fails and must be updated with a new number.

    The device page's pin rests on its device's manifest entry being the LAST (V2_PAGES):
    checked here, so a change to the identities cannot quietly shrink the pass it pays."""

    def test_the_measured_device_s_manifest_entry_is_the_last(self):
        from scripts_scale_helper import identity_for

        fleet = build_fleet(max(SIZES))
        measured = next(d for d in fleet if d["hostname"] == "cor0000")
        for size in SIZES:
            ids = sorted(identity_for(d) for d in fleet[:size])
            assert len(set(ids)) == size and ids[-1] == identity_for(measured), (size, ids[-3:])

    @pytest.mark.parametrize("page", sorted(p for p, v in V2_PAGES.items() if v[0] is not None))
    def test_the_fixed_bytes(self, measured, page):
        fixed, per_device, _calls = V2_PAGES[page]
        small = measured[page][SIZES[0]]["bytes"]
        got = small - per_device * SIZES[0]
        assert abs(got - fixed) <= fixed * TOLERANCE, (page, got, fixed)

    @pytest.mark.parametrize("page", sorted(V2_PAGES))
    def test_the_bytes_per_device(self, measured, page):
        _fixed, per_device, _calls = V2_PAGES[page]
        cost = measured[page]
        marginal = (cost[SIZES[-1]]["bytes"] - cost[SIZES[0]]["bytes"]) / (SIZES[-1] - SIZES[0])
        assert abs(marginal - per_device) <= max(per_device * TOLERANCE, 1), (
            f"{page}: {marginal:.1f} bytes per device, pinned at {per_device}. If the list "
            "was bounded, that is good news: record the new number rather than widening.")

    @pytest.mark.parametrize("page", sorted(V2_PAGES))
    def test_the_python_calls_per_device(self, measured, page):
        _fixed, _bytes, per_device = V2_PAGES[page]
        cost = measured[page]
        marginal = (cost[SIZES[-1]]["calls"] - cost[SIZES[0]]["calls"]) / (SIZES[-1] - SIZES[0])
        assert abs(marginal - per_device) <= max(per_device * TOLERANCE, 2), (
            f"{page}: {marginal:.1f} Python calls per device, pinned at {per_device}. "
            "A page that stopped passing over every device: record the new number.")


class TestTheExtractedScript:
    """Today's pages only (static/js/gen/, Stage 7 §0b); leaves with them (P7-27)."""

    def test_the_extracted_script_is_no_longer_in_the_document(self):
        """**The §0b acceptance**, pinned as a number for the same reason the page cost is:
        a later change that quietly inlines a block again must update this line rather than
        pass."""
        import os as _os

        from tests.source_index import tracked

        total = sum(_os.path.getsize(f)
                    for f in tracked("static/js/gen", suffix=".js", recursive=False,
                                     root="."))
        # The floor is the extraction's, not a size target: 75 kB, below the 83,689 left after
        # today's Git tab, Remote card and Baselines (7.8, P7-21, 2026-10-17; 125 kB below the
        # 132,580 left after today's NetBox tab, and 150 kB below the 199,435 left after the AI
        # family's tabs, D15) and far above what one template's inline block was.
        assert total > 75_000, (
            f"only {total} bytes are extracted — the inline script has "
            "returned to the templates")
        assert abs(total - EXTRACTED_SCRIPT_BYTES) < EXTRACTED_SCRIPT_BYTES * TOLERANCE
