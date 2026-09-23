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
