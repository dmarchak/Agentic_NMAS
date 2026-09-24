"""An address is matched by VALUE ALONE, so the import takes it from whoever
has it.

**Measured on the real NetBox, 2026-09-24.** Onboarding `bp-onboard-c` moved
`10.0.0.15/24` and `2001:db8::2/64` — r3's containerlab management addresses
— onto the new device's `GigabitEthernet1`. Forty minutes later Remove
deleted that interface and the database took both addresses with it, which
is how the damage surfaced. **The delete was correct given the database it
was handed; the write is the defect.**

`_ensure_ip_address()` looks up `{"address": cidr}`, narrowed by VRF and by
nothing else, and when the hit is assigned elsewhere it PATCHes
`assigned_object_id` onto the interface it is importing. Its docstring says
*get-or-create*.

**It is not a probe accident, it is structural.** Every vrnetlab node
answers on the same internal management address: all five Lab 1 routers
carry the identical `GigabitEthernet1 / vrf forwarding clab-mgmt /
ip address 10.0.0.15 255.255.255.0`, asserted below against the fleet
fixtures. So one NetBox object has been passed between six devices, and
whichever import ran last owns it.

**Two mechanisms failed silently and both were working correctly.** A PATCH
never adds `nmas-managed` and never records to `netbox_created_ids.json`, so
the stolen address was correctly identified as not NMAS's — Remove would
have skipped it. It died anyway, because provenance protects the *object*
and a cascade travels along the *relationship*, which nothing checks.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")


class TestTheCollisionIsStructural:
    """The fleet shares one management address by construction."""

    def test_every_router_carries_the_same_vrnetlab_mgmt_address(self):
        rows = {}
        for name in sorted(os.listdir(FLEET)):
            text = open(os.path.join(FLEET, name), encoding="utf-8").read()
            m = re.search(r"interface GigabitEthernet1\n(?: .*\n)*?"
                          r" ip address (\S+) (\S+)", text)
            if m:
                rows[name] = m.group(1)

        assert len(rows) >= 5, f"the scan found only {rows} — it is not reading the fleet"
        assert len(set(rows.values())) == 1, (
            "the routers no longer share one management address; this test "
            "is the premise of the whole finding and should be re-derived")
        shared = next(iter(rows.values()))
        assert list(rows.values()).count(shared) >= 5

    def test_and_it_is_the_clab_mgmt_vrf_on_all_of_them(self):
        found = 0
        for name in sorted(os.listdir(FLEET)):
            text = open(os.path.join(FLEET, name), encoding="utf-8").read()
            stanza = re.search(r"interface GigabitEthernet1\n((?: .*\n)+)", text)
            if stanza and "vrf forwarding clab-mgmt" in stanza.group(1):
                found += 1
        assert found >= 5, f"only {found} routers matched — scan is wrong"


class TestTheLookupIsKeyedOnTheInterface:
    """**"Does this interface already have this address", never "does this
    address exist".**

    Two devices must be able to hold the same value and that is not a
    compromise: every containerlab node answers on `10.0.0.15` inside its
    own namespace, and the same is true behind different VRFs and in
    disconnected management networks. The address genuinely is duplicated
    and each instance genuinely belongs to its device. **One value, many
    interfaces, each its own object.**

    These replace three tests that asserted the *absence* of scoping, each
    of which said in its own message what to assert once the fix landed.
    """

    def _wire(self, monkeypatch):
        from tests.fake_netbox import FakeNetBox

        from modules import netbox_guard as guard

        nb = FakeNetBox()
        monkeypatch.setattr(guard, "writes_allowed", lambda: True)
        monkeypatch.setattr(guard, "assert_writes_allowed", lambda *a: None)
        monkeypatch.setattr(guard, "record_created", lambda *a, **k: None)
        monkeypatch.setattr(guard, "get_current_list", lambda: "probe")
        return nb

    def _seed_on(self, nb, ip_id, address, iface_id):
        nb.seed("ipam/ip-addresses",
                {"id": ip_id, "address": address, "status": "active",
                 "description": "r3 GigabitEthernet1",
                 "assigned_object_type": "dcim.interface",
                 "assigned_object_id": iface_id})

    def test_the_same_value_on_another_interface_is_a_NEW_object(
            self, monkeypatch):
        """**The defect, as a test.** r3 holds 10.0.0.15/24 on interface 30;
        importing bp-onboard-c's identical Gi1 must not touch it."""
        from modules import netbox_client as nc

        nb = self._wire(monkeypatch)
        self._seed_on(nb, 22, "10.0.0.15/24", 30)

        out = nc._ensure_ip_address(nb, "http://nb", "10.0.0.15/24",
                                    interface_id=60,
                                    description="bp-onboard-c GigabitEthernet1")

        assert out["id"] != 22, "the import took r3's address again"
        assert out["assigned_object_id"] == 60
        r3s = [o for o in nb.objects("ipam/ip-addresses") if o["id"] == 22][0]
        assert r3s["assigned_object_id"] == 30, "r3 lost its address"
        assert r3s["description"] == "r3 GigabitEthernet1"
        assert len(nb.objects("ipam/ip-addresses")) == 2, \
            "one value, two interfaces, two objects"

    def test_a_shared_VRF_does_not_make_them_one(self, monkeypatch):
        """VRF narrowing reads like the fix and never was: r3's address is
        in clab-mgmt and so is every other router's."""
        from modules import netbox_client as nc

        nb = self._wire(monkeypatch)
        nb.seed("ipam/vrfs", {"id": 2, "name": "clab-mgmt"})
        self._seed_on(nb, 22, "10.0.0.15/24", 30)
        nb.objects("ipam/ip-addresses")[0]["vrf"] = {"id": 2}

        out = nc._ensure_ip_address(nb, "http://nb", "10.0.0.15/24",
                                    interface_id=60, vrf_id=2,
                                    description="bp-onboard-c Gi1")

        assert out["id"] != 22
        assert len(nb.objects("ipam/ip-addresses")) == 2

    def test_the_SAME_interface_is_still_reused_not_duplicated(
            self, monkeypatch):
        """The floor. A function that always created would satisfy both
        tests above and fill NetBox with duplicates on every sync."""
        from modules import netbox_client as nc

        nb = self._wire(monkeypatch)
        self._seed_on(nb, 22, "10.0.0.15/24", 30)

        out = nc._ensure_ip_address(nb, "http://nb", "10.0.0.15/24",
                                    interface_id=30,
                                    description="r3 GigabitEthernet1")

        assert out["id"] == 22, "it created a duplicate on the same interface"
        assert len(nb.objects("ipam/ip-addresses")) == 1

    def test_case_differs_and_it_is_still_the_same_address(self, monkeypatch):
        """`2001:DB8::2/64` from a config and `2001:db8::2/64` from NetBox
        are one address. Compared as addresses, not as text — otherwise the
        v6 object duplicates on every single sync."""
        from modules import netbox_client as nc

        nb = self._wire(monkeypatch)
        self._seed_on(nb, 44, "2001:db8::2/64", 30)

        out = nc._ensure_ip_address(nb, "http://nb", "2001:DB8::2/64",
                                    interface_id=30, description="r3 Gi1")

        assert out["id"] == 44
        assert len(nb.objects("ipam/ip-addresses")) == 1

    def test_no_interface_REFUSES_rather_than_matching_by_address(self):
        """The fallback *is* the defect. A caller with no interface has no
        business claiming an address, so it raises instead of widening."""
        import pytest as _pytest

        from modules import netbox_client as nc

        with _pytest.raises(nc.UnscopedAddressLookup) as err:
            nc._ensure_ip_address(None, "http://nb", "10.0.0.15/24",
                                  interface_id=None)
        assert "by address alone" in str(err.value)

    def test_the_query_is_scoped_and_says_so(self):
        import inspect

        from modules import netbox_client as nc

        src = inspect.getsource(nc._ensure_ip_address)
        assert "interface_id=interface_id" in src
        assert 'params' not in src.split('"""')[2], \
            "an address-keyed params dict is back"

    def test_the_read_160_lines_below_uses_the_same_scope(self):
        """It always did. That is the finding, not the fix: careful in the
        place where being wrong picked a wrong primary IP, absent from the
        place where being wrong moved another device's address."""
        import inspect

        from modules import netbox_client as nc

        read = inspect.getsource(nc._upsert_device)
        assert "if iface_id in nb_iface_map.values()" in read


class TestWhyNeitherGuardCaughtIt:
    def test_a_patch_never_tags_and_never_records(self):
        """So the stolen address was correctly NOT NMAS's, by both tests
        Remove applies. It died by cascade regardless: provenance protects
        the object, the cascade travels the relationship."""
        import inspect

        from modules import netbox_client as nc

        patch_src = inspect.getsource(nc._nb_patch)
        assert "_with_managed_tag" not in patch_src
        assert "record_created" not in patch_src
        post_src = inspect.getsource(nc._nb_post)
        assert "_with_managed_tag" in post_src, "the contrast is the point"
        assert "record_created" in post_src

    def test_the_description_is_the_only_trace_the_steal_leaves(self):
        """`f"{hostname} {intf['name']}"` is overwritten by each writer, so
        it names the LAST one — which is what makes a still-stolen address
        findable and a returned one invisible."""
        import inspect

        from modules import netbox_client as nc

        src = inspect.getsource(nc._upsert_device)
        assert 'description=f"{hostname} {intf[\'name\']}"' in src


class TestTheDetector:
    """`scripts/nmas-netbox-ip-provenance` reads that description back."""

    @pytest.fixture(scope="class")
    def tool(self):
        import importlib.util
        from importlib.machinery import SourceFileLoader

        path = os.path.join(ROOT, "scripts", "nmas-netbox-ip-provenance")
        spec = importlib.util.spec_from_file_location(
            "ipprov", path, loader=SourceFileLoader("ipprov", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @pytest.mark.parametrize("desc,host", [
        ("r3 GigabitEthernet1", "r3"),
        ("r3 GigabitEthernet1 secondary", "r3"),
        ("bp-onboard-c management (device list SSH IP)", "bp-onboard-c"),
        ("", ""),
        ("no-interface-here", ""),
    ])
    def test_it_reads_the_hostname_the_sync_wrote(self, tool, desc, host):
        assert tool.described_host(desc) == host

    def test_a_hyphenated_name_survives(self, tool):
        assert tool.described_host("bp-onboard-c Gi1") == "bp-onboard-c"


class TestTheRepairRefusesUntilTheFixIsIn:
    """**A repair that recreates the damage is worse than no repair.**

    The import is golden-driven, so the addresses are recoverable: nothing
    on any device was lost — r3 still has `10.0.0.15` on Gi1 in its running
    config. What was damaged is NetBox, which is not versioned. But a
    re-import with the *old* code walks the fleet again and reproduces the
    same one-object-many-claimants state, so the order is forced: the lookup
    fix lands, then the repair runs.

    `scripts/nmas-netbox-repair-addresses` checks that precondition in the
    code rather than trusting the operator to sequence it.
    """

    @pytest.fixture(scope="class")
    def repair(self):
        import importlib.util
        from importlib.machinery import SourceFileLoader

        path = os.path.join(ROOT, "scripts", "nmas-netbox-repair-addresses")
        spec = importlib.util.spec_from_file_location(
            "repair", path, loader=SourceFileLoader("repair", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_it_recognises_the_fix_is_in(self, repair):
        assert repair._lookup_is_interface_keyed() is True

    def test_and_it_would_refuse_without_it(self, repair, monkeypatch):
        """The control, driven through the same function: with an
        address-keyed lookup the precondition is False and `main` returns 2
        before touching anything."""
        import inspect

        monkeypatch.setattr(
            inspect, "getsource",
            lambda obj: 'params = {"address": address_cidr}')
        assert repair._lookup_is_interface_keyed() is False

    def test_it_never_repoints_an_address_that_lives_elsewhere(self, repair):
        """Moving an address is what caused this, so a repair reports a
        holder and does not touch it."""
        import inspect

        src = inspect.getsource(repair)
        assert "will NOT be moved" in src
        assert "_nb_patch" not in src, "the repair can move an address"
        assert "_nb_delete" not in src, "the repair can delete"
        assert "assigned_object_id" not in src, \
            "the repair sets an assignment on an existing object"

    def test_dry_run_is_the_default(self, repair):
        import inspect

        src = inspect.getsource(repair.main)
        assert 'if not args.apply:' in src
        assert "Nothing was created" in src

    def test_nothing_to_create_does_not_claim_netbox_is_correct(self, repair):
        """*"Nothing to create"* and *"NetBox is right"* are different
        claims, and the first must not be read as the second."""
        import inspect

        src = " ".join(inspect.getsource(repair.main).split()).replace('" "', "")
        assert "not a claim that NetBox is correct" in src
