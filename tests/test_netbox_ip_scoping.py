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


class TestTheLookupIsUnscoped:
    """**By value, and by VRF if one is supplied — never by device.**

    VRF narrowing cannot save it here: r3's address is in `clab-mgmt` and so
    is every other router's, so passing the VRF selects the same object.
    """

    def test_the_query_carries_no_device_or_interface(self):
        import inspect

        from modules import netbox_client as nc

        src = inspect.getsource(nc._ensure_ip_address)
        params = src[src.index("params"):src.index("existing =")]
        assert '"address"' in params, "the scan is not reading the lookup"
        assert "vrf_id" in params
        assert "device" not in params, (
            "the lookup is now device-scoped — if that is the fix, this test "
            "should assert the scoping rather than its absence")
        assert "interface" not in params

    def test_a_hit_on_another_interface_is_PATCHED_not_left_alone(self):
        import inspect

        from modules import netbox_client as nc

        src = inspect.getsource(nc._ensure_ip_address)
        assert "assigned_object_id" in src
        assert "_nb_patch" in src
        # The condition that triggers the steal, verbatim.
        assert 'existing.get("assigned_object_id") != interface_id' in src

    def test_the_scoping_EXISTS_160_lines_below_in_a_READ(self):
        """**The sharpest part.** The primary_ip4 fallback searches by
        address and then filters to interfaces belonging to this device:
        `if iface_id in nb_iface_map.values()`.

        So the scoping the write path lacks is present, correct, and in the
        same file — written by someone who had understood the problem in a
        place where getting it wrong would only have picked a wrong primary
        IP, not moved another device's address.
        """
        import inspect

        from modules import netbox_client as nc

        write = inspect.getsource(nc._ensure_ip_address)
        read = inspect.getsource(nc._upsert_device)
        assert "nb_iface_map.values()" in read, \
            "the device-scoped filter is gone — re-derive this finding"
        assert "if iface_id in nb_iface_map.values()" in read
        assert "nb_iface_map" not in write, (
            "the write now knows the device's interfaces — if that is the "
            "fix, assert the scoping rather than its absence")


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
