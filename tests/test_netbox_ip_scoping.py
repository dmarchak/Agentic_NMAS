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

        # Scoped to the CREATION path. `--remove-excluded` is a separate
        # mode that deletes deliberately, under provenance, and asserting
        # over the whole module would conflate the two.
        src = inspect.getsource(repair.plan) + inspect.getsource(repair.main)
        assert "will NOT be moved" in src
        assert "_nb_patch" not in src, "the repair can move an address"
        assert "assigned_object_id" not in src, \
            "the repair sets an assignment on an existing object"
        create_branch = inspect.getsource(repair.main).split(
            "_remove_excluded(args)")[-1]
        assert "_nb_delete" not in create_branch, \
            "the creation path can delete"

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


class TestARepairThatExaminesNothingRefuses:
    """**The floor, which matters more than the defect it guards.**

    `plan()` called `load_saved_devices(list_name)`. That function takes a
    **path** — `load_saved_devices(csv_path)` everywhere else — so a name
    failed to resolve the owning list, fell through to a CSV that is not
    there, and returned `[]`. The loop ran zero times and every count
    downstream **honestly** reported zero: *"Nothing to create."*

    The tell was visible: `default` and `Default` produced identical output,
    which means nothing downstream depended on the argument at all.

    **Fifth inferred-signature defect this stage**, after
    `set_device_override(list, host, dict)`, `preflight`'s lambda,
    `_commit`'s spy, and the `args[0] == "commit"` stub inside the test
    written to catch stub drift. *Read the signature.*

    For a repair script the vacuous pass is worse than usual, because the
    wrong conclusion it invites is **"the fleet is already correct"**.
    """

    @pytest.fixture(scope="class")
    def repair(self):
        import importlib.util
        from importlib.machinery import SourceFileLoader

        path = os.path.join(ROOT, "scripts", "nmas-netbox-repair-addresses")
        spec = importlib.util.spec_from_file_location(
            "repair2", path, loader=SourceFileLoader("repair2", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_zero_devices_REFUSES_and_names_the_path(self, repair, monkeypatch):
        monkeypatch.setattr(repair, "resolve_list",
                            lambda n: ("/data/lists/x/devices.csv", "X"))
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda *a, **k: [])

        with pytest.raises(repair.ExaminedNothing) as err:
            repair.plan("X")

        assert "resolved no devices" in str(err.value)
        assert "/data/lists/x/devices.csv" in str(err.value), \
            "the refusal does not say where it looked"

    def test_an_unknown_list_refuses_and_names_the_known_ones(
            self, repair, monkeypatch):
        monkeypatch.setattr("modules.device.get_device_lists",
                            lambda: [{"name": "Default", "filename": "default"}])

        with pytest.raises(repair.UnknownList) as err:
            repair.resolve_list("nope")
        assert "Default (default)" in str(err.value)

    def test_the_name_AND_the_slug_both_resolve(self, repair, monkeypatch):
        """`nmas-probe` registered as display name with slug `nmas_probe`
        already cost a runbook correction. Both spellings resolve, and both
        report the **registered** name so the output cannot be ambiguous."""
        monkeypatch.setattr("modules.device.get_device_lists",
                            lambda: [{"name": "Default", "filename": "default"}])

        for spelling in ("Default", "default"):
            path, registered = repair.resolve_list(spelling)
            assert registered == "Default"
            assert path.endswith(os.path.join("default", "devices.csv"))

    def test_it_never_resolves_through_get_list_data_dir(self):
        """That function calls `os.makedirs()`, so resolving a path creates
        a list — a typo at a repair script would silently make one.

        **Parsed, not grepped.** The first version of this test matched the
        docstring explaining why the call is absent: *the better the comment,
        the more likely it quotes the code it explains*, and this file's
        comments are unusually quotable. Fifth instance of that pattern.
        """
        import ast

        path = os.path.join(ROOT, "scripts", "nmas-netbox-repair-addresses")
        tree = ast.parse(open(path, encoding="utf-8").read())

        names, imported = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                imported.update(a.name for a in node.names)

        used = names | imported
        assert len(used) >= 40, "the parse found almost nothing"
        assert "get_list_data_dir" not in used, \
            "the repair resolves through the function that creates a list"
        assert "get_device_lists" in used, "the registry is the authority"

    def test_the_argument_is_checked_before_NetBox(self, repair):
        """A wrong list name reported as a configuration problem sends the
        reader to the wrong place — the same correction as a bootstrap
        render failure announced through `unsendable`."""
        import inspect

        src = inspect.getsource(repair.walk)
        assert src.index("resolve_list") < src.index("get_netbox_config")
        assert src.index("ExaminedNothing") < src.index("_session_from_config")

    def test_a_real_device_list_is_examined_and_counted(
            self, repair, monkeypatch):
        """**The floor on the floor.** Every assertion above is about
        refusing; a `plan()` that refused everything would satisfy them all
        and the repair would never run."""
        monkeypatch.setattr(repair, "resolve_list",
                            lambda n: ("/data/lists/x/devices.csv", "X"))
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda *a, **k: [{"hostname": "r3", "ip": "x"}])
        monkeypatch.setattr("modules.netbox_client.get_netbox_config",
                            lambda: {"url": "http://nb", "token": "t"})
        monkeypatch.setattr("modules.netbox_client._session_from_config",
                            lambda cfg: object())
        monkeypatch.setattr("modules.netbox_client._nb_get",
                            lambda *a, **k: [])

        out = repair.plan("X")
        assert out["examined"] == 1
        assert out["list"] == "X"
        assert out["skipped"], "a device not in NetBox must be reported"


class TestAnExcludedVRFIsNotModelled:
    """**NetBox enforces global uniqueness, so five identical addresses
    cannot be represented.** Measured 2026-09-24: the repair created one and
    NetBox refused the other four with *"Duplicate IP address found in
    global table: 10.0.0.15/24"*.

    Three honest options — disable the uniqueness check, do not model the
    addresses, or accept that NetBox is wrong about four interfaces — and
    the deciding test is **would this make sense on a network the tool did
    not build.** No real device has `10.0.0.15`; it is unreachable from
    anywhere, and NMAS reaches the fleet on a different range entirely.
    Importing it teaches NetBox about the emulator's plumbing rather than
    about the network, and weakening the uniqueness check would sacrifice a
    genuinely useful constraint to accommodate an artefact.

    **A setting, not a constant**, because another lab's emulator will name
    its management VRF something else — the network-agnostic rule that
    already makes the TFTP root and the Jenkins shell settings.
    """

    def test_the_default_excludes_the_containerlab_vrf(self):
        from modules.settings_schema import DEFAULTS

        assert DEFAULTS["netbox_excluded_vrfs"] == ["clab-mgmt"]

    def test_it_is_read_through_the_schema_not_the_raw_file(self):
        """`config.get_user_setting()` reads only the file and returns None
        for a key no install has written — which would exclude nothing,
        silently, on every install predating the setting.

        **Parsed, not grepped** — the function's own comment names
        `config.get_user_setting()` as the thing it does not use, and a
        substring search matched that. Third time tonight.
        """
        import ast
        import inspect
        import textwrap

        from modules import netbox_client as nc

        tree = ast.parse(textwrap.dedent(inspect.getsource(nc.excluded_vrfs)))
        called, imported = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                called.add(node.id)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
                called.update(a.name for a in node.names)

        assert "get_setting" in called, "the parse found nothing"
        assert "modules.settings_schema" in imported
        assert "get_user_setting" not in called, \
            "it reads the raw file, so a key no install has written "\
            "excludes nothing"

    def test_an_unreadable_settings_file_does_not_turn_it_off(self,
                                                              monkeypatch):
        """A read is survivable; silently dropping the exclusion is not."""
        from modules import netbox_client as nc
        from modules import settings_schema

        def _boom(*a, **k):
            raise RuntimeError("settings unreadable")

        monkeypatch.setattr(settings_schema, "get_setting", _boom)
        assert nc.excluded_vrfs() == {"clab-mgmt"}

    def test_a_hand_edited_string_is_accepted(self, monkeypatch):
        from modules import netbox_client as nc
        from modules import settings_schema

        monkeypatch.setattr(settings_schema, "get_setting",
                            lambda k, d=None: "clab-mgmt, mgmt-vrf")
        assert nc.excluded_vrfs() == {"clab-mgmt", "mgmt-vrf"}

    def test_an_EMPTY_setting_excludes_nothing(self, monkeypatch):
        """**The floor.** An operator who empties it gets the old behaviour,
        and a helper that always returned `clab-mgmt` would satisfy every
        test above."""
        from modules import netbox_client as nc
        from modules import settings_schema

        monkeypatch.setattr(settings_schema, "get_setting",
                            lambda k, d=None: [])
        assert nc.excluded_vrfs() == set()

    def test_the_import_skips_addresses_and_COUNTS_the_skip(self):
        """A skip nobody can see is the failure mode this stack is most
        prone to, so it lands in `ipam_stats` and in the log."""
        import inspect

        from modules import netbox_client as nc

        src = inspect.getsource(nc._upsert_device)
        assert "excluded_vrfs()" in src
        assert "ips_excluded" in src
        assert "excluded_vrfs\"]" in src or "excluded_vrfs\"]." in src

    def test_the_INTERFACE_is_still_modelled(self):
        """`vrf forwarding clab-mgmt` really is configured on the device.
        It is the addresses inside the VRF that describe the emulator, so
        the skip sits after the interface is created."""
        import inspect

        from modules import netbox_client as nc

        src = inspect.getsource(nc._upsert_device)
        assert src.index("_ensure_interface") < src.index("excluded_vrfs()"), \
            "the exclusion now skips the interface too"


class TestTheResidueIsKeyedOnTheInterface:
    """**The clean-up found nothing, and the reason was in NetBox's own
    refusal.**

    It matched `ip["vrf"]["name"]` against the excluded set. r1's
    `10.0.0.15/24` was sitting there as id 84 and never matched, because the
    repair created it **with no VRF at all** — which is precisely what
    NetBox said when it rejected the other four: *"Duplicate IP address
    found in the **global table**"*. There was no name to match, so the
    counters honestly reported zero and the output said *"examined every
    address in clab-mgmt"* about an object that was never in clab-mgmt.

    Two defects in one: a match on a field that is null, and a **second copy
    of the exclusion rule**. The rule is defined on the config
    (`vrf forwarding clab-mgmt`), so the import and the clean-up now both
    read it from there through the same `walk()`.
    """

    @pytest.fixture(scope="class")
    def repair(self):
        import importlib.util
        from importlib.machinery import SourceFileLoader

        path = os.path.join(ROOT, "scripts", "nmas-netbox-repair-addresses")
        spec = importlib.util.spec_from_file_location(
            "repair3", path, loader=SourceFileLoader("repair3", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _world(self, repair, monkeypatch, *, addresses, vrf_name="clab-mgmt",
               devices=(), recorded=()):
        """One device, one interface (id 60) whose GOLDEN says `vrf_name`."""
        from modules import netbox_guard as guard

        monkeypatch.setattr(repair, "walk", lambda ln: {
            "list": "Default", "csv": "/x", "examined": 1, "skipped": [],
            "session": None, "base": "http://nb",
            "rows": [{"device": "r1",
                      "facts": {"interfaces": [
                          {"name": "GigabitEthernet1", "vrf_name": vrf_name,
                           "cidr": "10.0.0.15/24"}]},
                      "ifaces": {"GigabitEthernet1": {"id": 60}}}]})

        def _get(session, base, path, **params):
            if "devices" in path:
                return list(devices)
            if params.get("interface_id") == 60:
                return list(addresses)
            return []

        monkeypatch.setattr("modules.netbox_client._nb_get", _get)
        monkeypatch.setattr(guard, "get_created",
                            lambda ln, ep="": {"ipam/ip-addresses":
                                               [{"id": i} for i in recorded]})

    #: r1's address as it really exists: created by the repair, tagged,
    #: recorded, and in the GLOBAL TABLE rather than in clab-mgmt.
    ID84 = {"id": 84, "address": "10.0.0.15/24", "vrf": None,
            "description": "r1 GigabitEthernet1",
            "tags": [{"slug": "nmas-managed"}]}

    def test_an_address_with_NO_VRF_is_still_found(self, repair, monkeypatch):
        """**The defect, as a test.** The old version keyed on the NetBox
        VRF field; this object has none."""
        self._world(repair, monkeypatch, addresses=[self.ID84], recorded=[84])

        r = repair.excluded_residue("Default")
        assert [x["id"] for x in r["eligible"]] == [84]
        assert r["eligible"][0]["netbox_vrf"] == "global", \
            "the report must say where it actually is"
        assert r["eligible"][0]["config_vrf"] == "clab-mgmt"

    def test_it_reports_what_it_examined(self, repair, monkeypatch):
        """*"examined every address in clab-mgmt"* was a claim the previous
        version could not support."""
        self._world(repair, monkeypatch, addresses=[self.ID84], recorded=[84])

        r = repair.excluded_residue("Default")
        assert r["devices"] == 1
        assert r["interfaces"] == 1
        assert r["targets"] == 1
        assert r["addresses"] == 1

    def test_an_address_NMAS_did_not_create_is_left_alone(
            self, repair, monkeypatch):
        """Provenance still governs; this is not an exemption from it."""
        self._world(repair, monkeypatch,
                    addresses=[dict(self.ID84, id=23, tags=[])], recorded=[])

        r = repair.excluded_residue("Default")
        assert r["eligible"] == []
        assert "not NMAS's" in r["skipped"][0]["why"]

    def test_tagged_but_unrecorded_is_also_left_alone(self, repair,
                                                      monkeypatch):
        """Id 23 exactly: created by the Lab 1 import before the record
        existed, so tagged and not in it."""
        self._world(repair, monkeypatch, addresses=[dict(self.ID84, id=23)],
                    recorded=[84])

        r = repair.excluded_residue("Default")
        assert r["eligible"] == []
        assert "created record" in r["skipped"][0]["why"]

    def test_a_devices_primary_ip_BLOCKS_rather_than_warns(
            self, repair, monkeypatch):
        """Deleting it nulls the device's primary — a MODIFICATION rather
        than a deletion, which the cascade map does not cover."""
        self._world(repair, monkeypatch, addresses=[self.ID84], recorded=[84],
                    devices=[{"name": "r1", "primary_ip4": {"id": 84}}])

        r = repair.excluded_residue("Default")
        assert r["eligible"] == []
        assert "r1.primary_ip4" in r["blocked"][0]["why"]

    def test_an_interface_OUTSIDE_an_excluded_vrf_is_never_considered(
            self, repair, monkeypatch):
        """**The floor.** A clean-up that considered every interface would
        be a fleet-wide address deleter wearing a narrow name."""
        self._world(repair, monkeypatch, addresses=[self.ID84], recorded=[84],
                    vrf_name="")

        r = repair.excluded_residue("Default")
        assert r["targets"] == 0
        assert r["eligible"] == []
        assert r["addresses"] == 0

    def test_no_excluded_vrf_configured_REFUSES(self, repair, monkeypatch):
        """Not "nothing to do": it cannot be cleaning up an exclusion that
        does not exist."""
        from modules import settings_schema

        monkeypatch.setattr(settings_schema, "get_setting",
                            lambda k, d=None: [])
        with pytest.raises(repair.NoExclusion):
            repair.excluded_residue("Default")

    def test_the_rule_is_read_from_the_golden_not_from_NetBox(self, repair):
        """One source. A second copy is how the import and the clean-up come
        to disagree about which interfaces are excluded."""
        import inspect

        src = inspect.getsource(repair.excluded_residue)
        assert 'intf.get("vrf_name")' in src
        assert 'ip.get("vrf")' not in src.split("netbox_vrf")[0], \
            "the clean-up is matching on NetBox's VRF field again"
        assert "walk(list_name)" in src


class TestTheCreatePathAppliesTheSameExclusion:
    """The repair created id 84 in the first place. With the exclusion in
    force it must not, and must **say** it did not."""

    @pytest.fixture(scope="class")
    def repair(self):
        import importlib.util
        from importlib.machinery import SourceFileLoader

        path = os.path.join(ROOT, "scripts", "nmas-netbox-repair-addresses")
        spec = importlib.util.spec_from_file_location(
            "repair4", path, loader=SourceFileLoader("repair4", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_an_excluded_interface_is_reported_not_created(
            self, repair, monkeypatch):
        monkeypatch.setattr(repair, "walk", lambda ln: {
            "list": "Default", "csv": "/x", "examined": 1, "skipped": [],
            "session": None, "base": "http://nb",
            "rows": [{"device": "r1",
                      "facts": {"interfaces": [
                          {"name": "GigabitEthernet1", "vrf_name": "clab-mgmt",
                           "cidr": "10.0.0.15/24"}]},
                      "ifaces": {"GigabitEthernet1": {"id": 60}}}]})
        monkeypatch.setattr("modules.netbox_client._nb_get",
                            lambda *a, **k: [])

        p = repair.plan("Default")
        assert p["creates"] == [], "the repair would recreate the artefact"
        assert [r["address"] for r in p["excluded"]] == ["10.0.0.15/24"]

    def test_an_ordinary_interface_is_still_created(self, repair, monkeypatch):
        """The floor: an exclusion that excluded everything would pass the
        test above."""
        monkeypatch.setattr(repair, "walk", lambda ln: {
            "list": "Default", "csv": "/x", "examined": 1, "skipped": [],
            "session": None, "base": "http://nb",
            "rows": [{"device": "r1",
                      "facts": {"interfaces": [
                          {"name": "Loopback0", "vrf_name": "",
                           "cidr": "10.255.1.11/32"}]},
                      "ifaces": {"Loopback0": {"id": 61}}}]})
        monkeypatch.setattr("modules.netbox_client._nb_get",
                            lambda *a, **k: [])

        p = repair.plan("Default")
        assert [r["address"] for r in p["creates"]] == ["10.255.1.11/32"]
        assert p["excluded"] == []


class TestRelationalFiltersAreIdKeyed:
    """**A filter that matches nothing is indistinguishable from a resource
    that is absent**, so a NetBox read filtered by a *related object's name*
    fails silently and honestly reports zero.

    Twice in one night, both outside this module: an ad-hoc
    `ipam/ip-addresses/?vrf=clab-mgmt` (NetBox wants `vrf_id` or the RD, not
    the name) returned `count: None` and said nothing about the VRF's
    contents; and the clean-up matched a **nested** `vrf.name` on objects
    that had no VRF at all.

    **The sweep's answer is a negative, and it is a real one.** All 37
    filtered reads in `netbox_client` key relations on ids — `device_id`,
    `site_id`, `interface_id`, `tunnel_id`, `termination_id` — and every
    `name=`/`slug=` filters an object by its **own** identity field, which
    is what those filters are for. The rule is pinned so it stays true, with
    a floor so "no offenders" cannot come from a scan that read nothing.
    """

    #: Kwargs that name a RELATED object. NetBox offers an `_id` form for
    #: each, and the id form cannot silently match nothing the way a name
    #: can — a wrong id is a wrong id, a wrong name is an empty result.
    RELATIONAL = {"vrf", "device", "interface", "tunnel", "rack", "cluster",
                  "tenant", "site", "region", "platform", "role",
                  "device_type", "manufacturer"}

    @staticmethod
    def _reads():
        import ast

        tree = ast.parse(open(os.path.join(ROOT, "modules", "netbox_client.py"),
                              encoding="utf-8").read())
        out = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in ("_nb_get", "_nb_first")):
                path = (node.args[2].value
                        if len(node.args) >= 3
                        and isinstance(node.args[2], ast.Constant) else "")
                out.append((path, {k.arg for k in node.keywords if k.arg},
                            node.lineno))
        return out

    def test_the_scan_finds_something(self):
        """**The floor.** Every assertion below is "no offenders"."""
        reads = self._reads()
        assert len(reads) >= 30, f"only {len(reads)} NetBox reads parsed"
        filtered = [r for r in reads if r[1]]
        assert len(filtered) >= 20, \
            f"only {len(filtered)} of them carry a filter"

    def test_no_read_filters_a_relation_by_name(self):
        offenders = [
            f"{path or '(dynamic)'} ?{','.join(sorted(kws))} (line {line})"
            for path, kws, line in self._reads()
            if kws & self.RELATIONAL]
        assert not offenders, (
            "these filter a RELATED object by name, which matches nothing "
            "when the name is wrong and reports it as an empty result: "
            + "; ".join(offenders))

    def test_and_the_relational_filters_that_exist_ARE_id_keyed(self):
        """**The positive anchor.** "No offenders" is also what a scan that
        could not run produces, so name what is expected to be found."""
        used = set()
        for _path, kws, _line in self._reads():
            used |= {k for k in kws if k.endswith("_id")}

        assert {"device_id", "interface_id", "site_id"} <= used, \
            f"expected the id-keyed relational filters, found {sorted(used)}"

    def test_name_and_slug_filters_are_an_objects_OWN_identity(self):
        """They are not the defect: `dcim/sites/?slug=` filters sites by
        their slug, which is what that filter is for. Listed explicitly so
        a future reader does not "fix" them."""
        own = [(p, sorted(k)) for p, k, _ in self._reads()
               if k & {"name", "slug"}]
        assert len(own) >= 8, f"only {len(own)} own-identity filters found"
        for path, kws in own:
            if "slug" in kws:
                assert path.startswith(("dcim/", "ipam/", "extras/")), path
