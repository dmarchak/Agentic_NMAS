"""The census: identity per type, tagged counted separately, and it can say no.

Stage 4C.0, built so the 4C probe's **teardown is measured rather than
eyeballed**. The provenance-based Remove has existed since Phase 0 and has
never been exercised against objects it created itself.

Two properties the obvious version would not have had:

**Identity, not counts.** Counts can match while the contents differ: Remove
deletes the probe's prefix, something else creates one during the run, the
total returns to baseline, and the probe's object is gone-but-replaced. *"The
same objects"* is the claim; *"the same number"* is a proxy for it.

**Tagged counted separately from the total.** The real NetBox already holds
`nmas-managed` objects from the Lab 1 import, and the population Remove may
touch is the tagged one — so the tagged before/after is the number that
actually tests the provenance gate. A total that matched while the tagged set
drifted would be a pass hiding a failure.
"""

import json
import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def census():
    from importlib.machinery import SourceFileLoader

    path = os.path.join(ROOT, "scripts", "nmas-netbox-census")
    spec = importlib.util.spec_from_file_location(
        "census", path, loader=SourceFileLoader("census", path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _snapshot(**types):
    """``{name: (objects, tagged_objects)}`` → a census-shaped dict."""
    return {"tag": "nmas-managed",
            "types": {name: {"total": len(objs), "objects": sorted(objs),
                             "tagged": len(tag), "tagged_objects": sorted(tag)}
                      for name, (objs, tag) in types.items()}}


class TestItCanSayNo:
    """The only way to know a comparison works is to see it refuse."""

    def test_an_identical_census_passes(self, census):
        snap = _snapshot(devices=(["1:r1", "2:r2"], ["2:r2"]))
        assert census.compare(snap, snap) == []

    def test_an_object_left_behind_is_a_finding(self, census):
        """The probe's own negative control: leave one tagged object."""
        before = _snapshot(devices=(["1:r1"], []))
        after = _snapshot(devices=(["1:r1", "9:bp-onboard-c"], ["9:bp-onboard-c"]))
        findings = census.compare(before, after)
        assert findings
        assert any("LEFT BEHIND" in f and "bp-onboard-c" in f for f in findings)

    def test_it_is_reported_as_tagged_as_well(self, census):
        """Tagged is the population Remove may touch, so it gets its own
        line — not folded into the total."""
        before = _snapshot(devices=(["1:r1"], []))
        after = _snapshot(devices=(["1:r1", "9:bp"], ["9:bp"]))
        findings = census.compare(before, after)
        assert any("nmas-managed object(s) LEFT BEHIND" in f for f in findings)

    def test_an_object_removed_that_should_not_have_been(self, census):
        """Remove deleting somebody else's object is the worse failure."""
        before = _snapshot(sites=(["1:hq", "2:branch"], ["2:branch"]))
        after = _snapshot(sites=(["2:branch"], ["2:branch"]))
        findings = census.compare(before, after)
        assert any("REMOVED" in f and "1:hq" in f for f in findings)


class TestCountsAreNotTheClaim:
    """The property the whole script exists for."""

    def test_a_matching_count_with_different_objects_fails(self, census):
        before = _snapshot(prefixes=(["1:10.0.0.0/24"], []))
        after = _snapshot(prefixes=(["7:10.9.9.0/24"], []))
        findings = census.compare(before, after)
        assert findings, "the count matched and the object changed"

    def test_and_it_says_so_in_those_words(self, census):
        """A reader who sees only 'removed' and 'left behind' might think two
        unrelated things happened. They did not."""
        before = _snapshot(prefixes=(["1:a"], []))
        after = _snapshot(prefixes=(["7:b"], []))
        findings = census.compare(before, after)
        assert any("COUNT matches" in f for f in findings)

    def test_the_tagged_set_drifting_under_a_matching_total_fails(self, census):
        """A pass hiding a failure: the total is identical, and an object
        that was NMAS's no longer is."""
        before = _snapshot(devices=(["1:a", "2:b"], ["1:a"]))
        after = _snapshot(devices=(["1:a", "2:b"], ["2:b"]))
        findings = census.compare(before, after)
        assert findings
        assert all("nmas-managed" in f for f in findings)


class TestTheEdgeOfTheClaimIsStated:
    """A type absent from the census is not reported as unchanged — it is not
    reported at all. The same rule as `nmas-check-secret-storage`."""

    def test_it_names_what_it_does_not_count(self, census):
        assert census.NOT_COUNTED
        assert "extras/tags" in census.NOT_COUNTED

    def test_every_type_the_sync_creates_is_counted(self, census):
        """The list must not fall behind the thing it audits."""
        import io
        import re

        src = io.open(os.path.join(ROOT, "modules", "netbox_client.py"),
                      encoding="utf-8").read()
        used = set(re.findall(r'"((?:dcim|ipam)/[a-z-]+/)"', src))
        counted = {path for _n, path in census.ENDPOINTS}
        known = counted | {f"{k}/" for k in census.NOT_COUNTED}
        # Not vacuous: 15 endpoints, measured. A regex that matched nothing
        # would make this assertion true and meaningless -- five can't-fail
        # controls have been found in this project already.
        assert len(used) >= 12, f"the endpoint scan found only {len(used)}"
        missing = sorted(used - known)
        assert not missing, (
            "netbox_client touches these and the census neither counts them "
            "nor records why: " + str(missing))

    def test_a_type_in_only_one_census_is_a_finding(self, census):
        """Two snapshots taken by different versions of this script must not
        compare clean."""
        before = _snapshot(devices=(["1:a"], []))
        after = _snapshot(devices=(["1:a"], []), vlans=([], []))
        assert any("only one census" in f
                   for f in census.compare(before, after))


class TestIdentityIsReadable:

    def test_it_carries_the_id(self, census):
        assert census._identity({"id": 7, "name": "r6"}).startswith("7:")

    def test_an_address_has_no_name_and_still_identifies(self, census):
        """An IP, a prefix and a cable have no `name`; falling back to the id
        alone makes a diff unreadable exactly when somebody needs to read it."""
        assert "10.0.0.1/24" in census._identity(
            {"id": 3, "address": "10.0.0.1/24"})

    def test_tagging_is_read_from_the_slug(self, census):
        obj = {"id": 1, "tags": [{"slug": "nmas-managed"}]}
        assert census._is_tagged(obj, "nmas-managed") is True
        assert census._is_tagged({"id": 2, "tags": []}, "nmas-managed") is False

    def test_the_tag_slug_comes_from_the_guard(self, census):
        """Not a second copy of the string — the provenance gate owns it."""
        import io

        src = io.open(os.path.join(ROOT, "scripts", "nmas-netbox-census"),
                      encoding="utf-8").read()
        assert "from modules.netbox_guard import MANAGED_TAG_SLUG" in src


class TestItRefusesToWriteACensusItCouldNotTake:
    """A file that looks like a snapshot and is not one would be compared
    against later, and would pass."""

    def test_an_unreachable_netbox_raises(self, census, monkeypatch):
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (False, "connection refused", None, ""))
        with pytest.raises(SystemExit) as excinfo:
            census.take()
        assert "not reachable" in str(excinfo.value)


class TestATeardownThatCannotBeMeasuredHasNotPassed:
    """**Three exit codes, because two cannot say "unproven".**

    Found by running the probe: step 2's baseline was never taken, because
    creating the list through the GUI does not prompt for one and the
    `--out` command was lost when the method moved to the UI. So this run's
    teardown -- the thing the probe exists to prove -- could not be
    evaluated at all.

    The script's answer to that was `FileNotFoundError`, exiting **1**, and
    1 is what *"the teardown left objects behind"* exits with. The two most
    different outcomes the probe can have shared a code. Same distinction as
    `inconclusive` to `failed`, `"checked 7 of 9"` to a number that reads as
    complete, and `did_not_answer` to a device verdict.

    **It is not recoverable after the fact**, which is why it must refuse
    rather than offer: a baseline taken once the probe has begun writing
    contains the probe's own objects, so the teardown would measure clean
    while leaving them behind -- worse than having none.
    """

    def _main(self, census, monkeypatch, argv, taken=None):
        monkeypatch.setattr(census, "take",
                            lambda *a, **k: taken if taken is not None
                            else pytest.fail("a census was taken before the "
                                             "baseline was validated"))
        monkeypatch.setattr(census.sys, "argv", ["nmas-netbox-census"] + argv)
        return census.main()

    def test_a_missing_baseline_is_UNPROVEN_not_a_difference(
            self, census, monkeypatch, tmp_path, capsys):
        code = self._main(census, monkeypatch,
                          ["--compare", str(tmp_path / "never-taken.json")])

        assert code == census.EXIT_UNPROVEN
        assert code != census.EXIT_DIFFERS, "unproven read as a failed teardown"
        assert code != census.EXIT_PASS
        out = capsys.readouterr().out
        assert "UNPROVEN" in out
        assert "cannot be measured" in out
        assert "NOT a pass" in out

    def test_it_does_not_take_a_census_first(
            self, census, monkeypatch, tmp_path):
        """The validation runs BEFORE the live read. The old order spent a
        full pass over NetBox and then raised on the `open()`."""
        self._main(census, monkeypatch,
                   ["--compare", str(tmp_path / "never-taken.json")])
        # The stubbed `take` fails the test if it is called at all.

    def test_JSON_that_is_not_a_census_is_UNPROVEN_too(
            self, census, monkeypatch, tmp_path, capsys):
        p = tmp_path / "wrong.json"
        p.write_text('{"devices": []}', encoding="utf-8")

        assert self._main(census, monkeypatch, ["--compare", str(p)]) \
            == census.EXIT_UNPROVEN
        assert "not a census" in capsys.readouterr().out

    def test_an_EMPTY_baseline_is_UNPROVEN_rather_than_a_pass(
            self, census, monkeypatch, tmp_path, capsys):
        """The vacuous-pass failure, in the file rather than the assertion:
        every comparison against a baseline that counted nothing passes."""
        p = tmp_path / "empty.json"
        p.write_text('{"types": {}}', encoding="utf-8")

        assert self._main(census, monkeypatch, ["--compare", str(p)]) \
            == census.EXIT_UNPROVEN
        assert "vacuously" in capsys.readouterr().out

    def test_unreadable_JSON_names_itself_rather_than_raising(
            self, census, tmp_path):
        p = tmp_path / "half.json"
        p.write_text('{"types": {"sites"', encoding="utf-8")
        data, reason = census.read_baseline(str(p))

        assert data is None
        assert "not readable JSON" in reason

    def test_a_REAL_baseline_still_compares_and_can_pass(
            self, census, monkeypatch, tmp_path, capsys):
        """**The floor.** Every assertion above is about refusing; a
        function that refused everything would satisfy all of them and the
        probe would have no acceptance at all."""
        snap = _snapshot(sites=(["a"], ["a"]))
        p = tmp_path / "before.json"
        p.write_text(json.dumps(snap), encoding="utf-8")

        code = self._main(census, monkeypatch, ["--compare", str(p)],
                          taken=snap)
        assert code == census.EXIT_PASS
        assert "PASS" in capsys.readouterr().out

    def test_and_a_real_difference_is_still_a_DIFFERENCE(
            self, census, monkeypatch, tmp_path, capsys):
        """The other floor: unproven must not have swallowed the failure."""
        before = _snapshot(sites=(["a"], ["a"]))
        after = _snapshot(sites=(["a", "probe"], ["a", "probe"]))
        p = tmp_path / "before.json"
        p.write_text(json.dumps(before), encoding="utf-8")

        code = self._main(census, monkeypatch, ["--compare", str(p)],
                          taken=after)
        assert code == census.EXIT_DIFFERS
        assert "difference(s)" in capsys.readouterr().out

    def test_a_snapshot_records_WHEN_it_was_taken(self, census, monkeypatch,
                                                  tmp_path, capsys):
        """A baseline taken after the probe began writing contains the
        probe's own objects. The file is the only place that ordering can
        be checked from, so the time travels with it."""
        out = tmp_path / "before.json"
        self._main(census, monkeypatch, ["--out", str(out)],
                   taken=_snapshot(sites=(["a"], [])))

        written = json.loads(out.read_text(encoding="utf-8"))
        assert written["taken_at"].endswith("Z")
        assert written["taken_at"][:2] == "20"

    def test_the_comparison_reports_that_time(self, census, monkeypatch,
                                              tmp_path, capsys):
        snap = _snapshot(sites=(["a"], ["a"]))
        snap["taken_at"] = "2026-09-24T01:00:00Z"
        p = tmp_path / "before.json"
        p.write_text(json.dumps(snap), encoding="utf-8")

        self._main(census, monkeypatch, ["--compare", str(p)], taken=snap)
        assert "baseline taken: 2026-09-24T01:00:00Z" in capsys.readouterr().out

    def test_an_OLD_baseline_without_the_field_still_compares(
            self, census, monkeypatch, tmp_path, capsys):
        """The field was added after the first probe run took its baseline.
        Refusing one that predates it would retire the only baseline that
        exists."""
        snap = _snapshot(sites=(["a"], ["a"]))
        p = tmp_path / "before.json"
        p.write_text(json.dumps(snap), encoding="utf-8")

        assert self._main(census, monkeypatch, ["--compare", str(p)],
                          taken=snap) == census.EXIT_PASS
        assert "baseline taken: unrecorded" in capsys.readouterr().out
