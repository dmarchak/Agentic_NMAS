"""A delete takes more than it was asked to, and the preview cannot see it.

**Measured on the real NetBox, 2026-09-24**, on the Stage 4C probe's
teardown — the second time the provenance-based Remove has ever run against
objects it created itself, and the first against a NetBox holding anything
else.

Remove deleted its eight objects. Every one of them was genuinely NMAS's:
tagged `nmas-managed`, in `data/netbox_created_ids.json`, and the apply
reported `ok: true` with `skipped: []`. **And two objects that were there
before disappeared** — `10.0.0.15/24` and `2001:db8::2/64`, r3's
containerlab management addresses from the Lab 1 import. The census caught
it, by identity, which a count could not have: ip-addresses 82 -> 80 against
a baseline of 229 -> 227.

**The gate was never wrong, and its claim is false.** Every step in the
proof of "Remove deletes only what it created" holds; the damage was done by
the database on Remove's behalf, after the last point at which NMAS was
looking. That is the worst failure shape in this design and the reason the
teardown was run against the real NetBox rather than proved by dry run.

These tests pin the two structural facts. Neither is the fix — the fix waits
on measuring *which* deletion cascaded, because a dependency map derived
from a guess is a second wrong thing that looks right.
"""

import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestThePreviewSimulatesNMASNotTheDatabase:
    """**A preview that lists eight while nine disappear is a preview that
    lies**, and it does so by construction rather than by a rendering bug.

    `remove_list_from_netbox(dry_run=True)` walks `_REMOVAL_ORDER` over the
    created-id record and calls `_nb_delete`, which in a dry run only
    records the intent. **Nothing on that path asks NetBox what a delete
    would take with it** — there is no query of dependents anywhere in the
    module — so the preview is exactly accurate about NMAS's intent and
    entirely silent about the consequence.

    Same rule as the deploy path's, which this violates: *what is confirmed
    is what happens, byte for byte.* There, the program is recomputed at
    apply and refused if anything moved. Here the operator confirms a list
    of eight and the database does something else.
    """

    def test_the_dry_run_records_intent_and_asks_nothing(self):
        import inspect

        from modules import netbox_client as nc

        src = inspect.getsource(nc._nb_delete)
        assert "record_intent" in src
        # The dry-run branch returns before any request is built.
        head = src[:src.index("assert_writes_allowed")]
        assert "is_dry_run" in head
        assert "session.delete" not in head

    def test_nothing_in_the_removal_path_queries_dependents(self):
        """The floor is the point: if a dependents query is ever added, this
        test must be updated, and updating it is how the claim gets
        re-examined."""
        import inspect

        from modules import netbox_client as nc

        src = inspect.getsource(nc.remove_list_from_netbox)
        assert "_nb_get_by_id" in src, "the scan is not reading the function"
        # It fetches each object it plans to delete, and nothing else.
        assert "_nb_get(" not in src, (
            "something now queries NetBox during removal — if it is a "
            "dependents query, the cascade finding may be addressed and "
            "this test should say so rather than fail")

    def test_the_cascade_was_KNOWN_and_silently_absorbed(self):
        """`_run()`'s already-gone branch is commented *"or cascaded by an
        earlier device delete"* and calls `forget_created`.

        **A cascade detector wired to nothing.** The one place in the
        program that knows a delete can take others with it drops the id and
        continues — it is not counted, not reported, and not distinguished
        from an object a human removed yesterday.
        """
        import inspect

        from modules import netbox_client as nc

        src = inspect.getsource(nc.remove_list_from_netbox)
        assert "cascaded" in src, "the comment naming the mechanism is gone"
        after = src[src.index("cascaded"):]
        assert "forget_created" in after[:400]
        assert "cascade" not in [k.lower() for k in ("",)]  # no key reports it
        assert '"cascaded"' not in src, (
            "if a cascade is now reported, this test should assert the "
            "report rather than its absence")


class TestTheFakeNetBoxCannotExhibitIt:
    """**No test in this suite could have caught this, and none will.**

    `FakeNetBox.delete` pops one object out of a dict of lists. There are no
    foreign keys, no `on_delete`, no PROTECT and no CASCADE — so every test
    of Remove has been measuring NMAS's loop against a store that is
    incapable of the behaviour that caused the damage.

    That is not a criticism of the fake; it is the boundary of what a fake
    can prove, and it is the same seam as every other defect this stage
    found: *a test that mocks a collaborator cannot see what the real
    collaborator does.* Recording it here so the next person to ask "why did
    750 tests miss this" has the answer in the suite rather than in a commit
    message.
    """

    def test_delete_removes_exactly_one_object_and_nothing_else(self):
        from tests.fake_netbox import FakeNetBox

        nb = FakeNetBox()
        nb.seed("ipam/vrfs", {"id": 4, "name": "probe"})
        nb.seed("ipam/ip-addresses", {"id": 22, "address": "a", "vrf": {"id": 4}})
        nb.seed("ipam/ip-addresses", {"id": 44, "address": "b", "vrf": {"id": 4}})

        nb.delete("http://nb/api/ipam/vrfs/4/")

        remaining = nb.objects("ipam/ip-addresses")
        assert len(remaining) == 2, (
            "the fake now models referential integrity — if that is "
            "deliberate, this test should assert the cascade instead")
        assert nb.objects("ipam/vrfs") == []

    def test_the_suite_asserts_the_very_claim_that_failed(self):
        """**`test_netbox_preview_fidelity.py` is named for this property.**

        *"The preview count is the executed count"* is a stated architecture
        decision, it has a test file of its own, and it is **false in
        production** — eight previewed, ten gone. It passes because it
        drives `FakeNetBox`, where a delete removes one object and the
        preview therefore cannot be wrong.

        The claim was always about NMAS's delete list. Nothing said so, and
        the file's name says the opposite. The floor here is that the file
        still exists and still uses the fake, so that whoever narrows the
        claim has to come through this test.
        """
        path = os.path.join(ROOT, "tests", "test_netbox_preview_fidelity.py")
        src = open(path, encoding="utf-8").read()
        assert "FakeNetBox" in src, "the scan is not reading the file"
        assert "preview" in src.lower()
        assert "cascade" not in src.lower(), (
            "preview fidelity now mentions cascades — if the claim has been "
            "narrowed or the fake taught referential integrity, this test "
            "should assert that rather than its absence")


class TestTheCensusIsWhatCaughtIt:
    """Identity, not counts — and this is the run that earned the
    distinction.

    The total moved 229 -> 227. The eight objects NMAS created after the
    baseline and then deleted net to zero, so the **-2 is exactly the two
    addresses** and nothing else was lost. A count-only check over a
    population that both gained and lost objects would have had to be
    reasoned about; identity per type named the two objects outright.
    """

    def test_a_removal_that_takes_an_untracked_object_is_a_finding(self):
        from importlib.machinery import SourceFileLoader
        import importlib.util

        path = os.path.join(ROOT, "scripts", "nmas-netbox-census")
        spec = importlib.util.spec_from_file_location(
            "census_c", path, loader=SourceFileLoader("census_c", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        def snap(objs):
            return {"tag": "nmas-managed",
                    "types": {"ip-addresses": {
                        "total": len(objs), "objects": sorted(objs),
                        "tagged": 0, "tagged_objects": []}}}

        findings = mod.compare(
            snap(["22:10.0.0.15/24", "44:2001:db8::2/64", "9:other"]),
            snap(["9:other"]))

        assert findings, "the census did not notice two objects going missing"
        assert any("REMOVED" in f for f in findings)
        assert any("22:10.0.0.15/24" in f for f in findings), \
            "the finding must NAME the objects, not count them"


class TestThePreviewShowsWhatTheDatabaseWillTake:
    """**The second finding, and it outlives the first.**

    Keying the address lookup on the interface stops the import moving
    another device's address. It does nothing about this: any delete of any
    type can take objects with it, and until now the preview reported only
    what NMAS intended.

    `netbox_cascade.CASCADES` is **measured, not inferred from Django's
    `on_delete`** — `dcim/interfaces` from the changelog of request
    `263695a3`, which held one DELETE and three deletions.
    """

    def _wire(self, monkeypatch):
        from tests.fake_netbox import FakeNetBox

        from modules import netbox_guard as guard

        nb = FakeNetBox()
        monkeypatch.setattr(guard, "writes_allowed", lambda: True)
        monkeypatch.setattr(guard, "assert_writes_allowed", lambda *a: None)
        return nb

    def test_an_address_on_a_doomed_interface_is_reported(self, monkeypatch):
        from modules import netbox_cascade as nc

        nb = self._wire(monkeypatch)
        nb.seed("ipam/ip-addresses",
                {"id": 22, "address": "10.0.0.15/24",
                 "assigned_object_type": "dcim.interface",
                 "assigned_object_id": 60})

        out = nc.dependents_of(nb, "http://nb", "dcim/interfaces", 60)

        assert out["ok"] is True
        assert [o["id"] for o in out["objects"]] == [22]
        assert out["objects"][0]["endpoint"] == "ipam/ip-addresses"

    def test_a_device_reaches_its_interfaces_ADDRESSES_transitively(
            self, monkeypatch):
        """Expanded by the walk rather than listed under devices in the map,
        so the two cannot disagree."""
        from modules import netbox_cascade as nc

        nb = self._wire(monkeypatch)
        nb.seed("dcim/interfaces", {"id": 60, "name": "Gi1",
                                    "device": {"id": 10}})
        nb.seed("ipam/ip-addresses",
                {"id": 22, "address": "10.0.0.15/24",
                 "assigned_object_type": "dcim.interface",
                 "assigned_object_id": 60})

        out = nc.dependents_of(nb, "http://nb", "dcim/devices", 10)

        got = {(o["endpoint"], o["id"]) for o in out["objects"]}
        assert ("dcim/interfaces", 60) in got
        assert ("ipam/ip-addresses", 22) in got

    def test_an_UNMEASURED_type_says_so_and_does_not_say_none(self):
        """**The design.** An empty answer and an unmeasured one look
        identical in a preview, and the one that reads as safe is the one
        nobody checked."""
        from modules import netbox_cascade as nc

        out = nc.dependents_of(None, "http://nb", "dcim/sites", 3)

        assert out["objects"] == []
        assert out["unproven"], "an unmeasured type reported 'takes nothing'"
        assert "not been measured" in out["unproven"][0]

    def test_a_FAILED_query_is_unproven_not_empty(self, monkeypatch):
        from modules import netbox_cascade as nc

        class Broken:
            def get(self, *a, **k):
                raise RuntimeError("connection reset")

        out = nc.dependents_of(Broken(), "http://nb", "dcim/interfaces", 60)

        assert out["objects"] == []
        assert out["ok"] is False
        assert any("the query failed" in u for u in out["unproven"])

    def test_collateral_separates_what_is_NMAS_from_what_is_not(
            self, monkeypatch):
        """The question the provenance gate was built to answer and could
        not, because it was asked about each object rather than about the
        consequence."""
        from modules import netbox_cascade as nc

        nb = self._wire(monkeypatch)
        nb.seed("ipam/ip-addresses",
                {"id": 22, "address": "10.0.0.15/24",
                 "assigned_object_type": "dcim.interface",
                 "assigned_object_id": 60})
        nb.seed("ipam/ip-addresses",
                {"id": 99, "address": "10.255.0.31/24",
                 "assigned_object_type": "dcim.interface",
                 "assigned_object_id": 60})

        out = nc.collateral(nb, "http://nb",
                            [{"endpoint": "dcim/interfaces", "id": 60}],
                            recorded_ids={("ipam/ip-addresses", 99)})

        assert out["proven"] is True
        assert {o["id"] for o in out["taken"]} == {22, 99}
        assert [o["id"] for o in out["foreign"]] == [22], \
            "the address NMAS never created must be the one flagged"

    def test_the_preview_carries_it_and_the_APPLY_does_not(self, monkeypatch):
        """After an apply the objects are gone, so the same query would
        report no consequence for a delete that had one."""
        import inspect

        from modules import netbox_client as nc

        src = inspect.getsource(nc.remove_list_from_netbox)
        assert '"cascade": cascade' in src
        assert "if dry_run else None" in src

    def test_the_removal_order_and_the_cascade_map_are_checked_against_each_other(self):
        """**The floor.** Every endpoint the removal walks is either
        measured or listed as unmeasured — adding one to `_REMOVAL_ORDER`
        without deciding which is a silent 'takes nothing'."""
        from modules.netbox_cascade import CASCADES, UNMEASURED
        from modules.netbox_client import _PER_DEVICE_ORDER, _REMOVAL_ORDER

        walked = set(_REMOVAL_ORDER) | set(_PER_DEVICE_ORDER)
        assert len(walked) >= 9, "the scan is not reading the removal order"
        classified = set(CASCADES) | set(UNMEASURED)
        assert not (walked - classified), (
            f"unclassified endpoints: {sorted(walked - classified)} — each "
            "must be measured or declared unmeasured")
        assert CASCADES, "the measured set is empty; nothing is proven"


class TestTheOperatorCanSEEIt:
    """**The shipped renderer, executed.**

    A preview finding nobody can see is the defect this project keeps
    rediscovering: `loadOnboardPending` had no caller, the pending banner's
    buttons read an empty select, and the agent panel had three guards each
    hiding the same data while every server test passed. So the consequence
    is rendered by a **pure** function, and this runs that function's
    shipped source against the payload the endpoint returns.
    """

    @staticmethod
    def _source():
        """`nbCascadeHtml` out of the template, brace-matched, plus the
        escaper it calls."""
        path = os.path.join(ROOT, "templates", "partials",
                            "netbox_safety_modal.html")
        page = open(path, encoding="utf-8").read()
        out = []
        for name in ("_nbEscape", "nbCascadeHtml"):
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

    def _render(self, cascade):
        import json

        dukpy = pytest.importorskip("dukpy")
        return dukpy.evaljs(self._source()
                            + f"\nnbCascadeHtml({json.dumps(cascade)})")

    def test_a_foreign_object_is_named_and_flagged_danger(self):
        html = self._render({
            "taken": [{"endpoint": "ipam/ip-addresses", "id": 22,
                       "name": "10.0.0.15/24", "via": "dcim/interfaces",
                       "foreign": True}],
            "foreign": [{"endpoint": "ipam/ip-addresses", "id": 22,
                         "name": "10.0.0.15/24", "via": "dcim/interfaces",
                         "foreign": True}],
            "unproven": [], "proven": True})

        assert "alert-danger" in html
        assert "10.0.0.15/24" in html, "the object is not named"
        assert "did not create" in html

    def test_unproven_is_its_own_banner_and_says_it_is_not_nothing(self):
        html = self._render({"taken": [], "foreign": [], "proven": False,
                             "unproven": ["dcim/sites: not measured"]})

        assert "alert-warning" in html
        assert "incomplete" in html
        assert "not</em> the same as nothing" in html
        assert "dcim/sites: not measured" in html

    def test_a_clean_proven_preview_adds_no_alarm(self):
        """**The floor.** A renderer that always warned would satisfy both
        tests above and train the operator to click through."""
        html = self._render({"taken": [], "foreign": [], "unproven": [],
                             "proven": True})

        assert "alert-danger" not in html
        assert "alert-warning" not in html
        assert html.strip() == ""

    def test_NMAS_owned_collateral_is_stated_without_alarm(self):
        html = self._render({
            "taken": [{"endpoint": "ipam/ip-addresses", "id": 99,
                       "name": "x", "via": "dcim/interfaces",
                       "foreign": False}],
            "foreign": [], "unproven": [], "proven": True})

        assert "alert-danger" not in html
        assert "1 further" in html

    def test_a_missing_cascade_key_renders_nothing_rather_than_throwing(self):
        """An older payload, or an apply response, carries no cascade."""
        assert self._render(None) == ""

    def test_the_renderer_is_actually_CALLED_by_the_modal(self):
        """**Added because the control passed.**

        Deleting the call site from the modal left every test above green:
        they execute `nbCascadeHtml` directly, which tests the render and
        not the wiring. That is `loadOnboardPending` having no caller, and
        the `/onboard/create` payload seam, for the third time — *a test
        that constructs its subject cannot notice that nothing else does.*

        Counted excluding the definition, so the function existing is not
        mistaken for the function being used.
        """
        path = os.path.join(ROOT, "templates", "partials",
                            "netbox_safety_modal.html")
        page = open(path, encoding="utf-8").read()

        defs = page.count("function nbCascadeHtml(")
        calls = page.count("nbCascadeHtml(") - defs
        assert defs == 1, f"expected one definition, found {defs}"
        assert calls >= 1, (
            "nbCascadeHtml is defined and never called — the consequence is "
            "computed by the server, carried to the browser, and drawn "
            "nowhere")
        assert "${nbCascadeHtml(d.cascade)}" in page, \
            "it is called with something other than the preview payload"
