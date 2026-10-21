"""C1504: Free <address> from <record>…, on an import's preview, frees the management address a
record retired before C1494's fix still holds.

Read 2026-10-21: a record retired as ``<name>-retired-21`` (Decommissioning) still held the
management address of the new device of the name, and no Mercury path freed it (Retire frees a record's addresses only for a
retirement from C1494 on). The import's preview now offers, for each such holder, its own preview
(the record's addresses, each deleted when Mercury created it, tagged AND recorded, else
unassigned and kept, and the record's primaries cleared), confirmed by hash as a verified person,
written through the write gate with Retire's own freeing code (`retire.free_netbox_addresses`),
read back, and recorded; then the import is previewed again.

Through the real app (test_netbox_v2's `networks` and `nb`: Branch holds r9), NetBox the
in-memory fake. The import's sync is replaced at its edge as test_netbox_v2 replaces it, but the
held address it reports comes from the REAL check (`_say_held_by_decommissioned`) against the
fake. Everything from the routes to the fake is the real code. Each case runs over IPv4 and
IPv6 (documentation addresses).
"""

import json
import re

import pytest

from tests.test_netbox_v2 import _job, _post, nb  # noqa: F401 (the fixture)
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

#: (the management address as the import reads it, as NetBox holds it on the retired record,
#: the address Mercury created on it, the address of another device).
FAMILIES = {
    "ipv4": ("192.0.2.9", "192.0.2.9/30", "192.0.2.65/32", "192.0.2.77/32"),
    "ipv6": ("2001:db8::9", "2001:db8::9/64", "2001:db8:1::65/128", "2001:db8:2::77/128"),
}


@pytest.fixture(params=sorted(FAMILIES))
def retired(request, nb, monkeypatch):  # noqa: F811
    """NetBox holds ``r9-retired-21`` (Decommissioning) with two addresses: the management
    address r9's import needs, a person's (untagged, unrecorded) and the record's primary, on
    GigabitEthernet2; and one Mercury created (tagged and recorded for Branch) on Loopback0.
    r9's own record is active. The import's preview reports the holder through the real
    check."""
    return _retired(request.param, nb, monkeypatch)


@pytest.fixture
def retired_v4(nb, monkeypatch):  # noqa: F811
    """`retired` on IPv4 alone (tests/test_confirm_buttons_drawn.py's case)."""
    return _retired("ipv4", nb, monkeypatch)


def _retired(family, nb, monkeypatch):  # noqa: F811
    import modules.netbox_client as nbc
    from modules import netbox_guard as guard
    from tests.fake_netbox import FakeNetBox

    ip, held, mine_addr, other_addr = FAMILIES[family]
    fake = FakeNetBox()
    monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: fake)
    monkeypatch.setattr(nbc, "_managed_tag_ids", {})
    old = fake.seed("dcim/devices", {"name": "r9-retired-21",
                                     "status": {"value": "decommissioning"}})
    new = fake.seed("dcim/devices", {"name": "r9", "status": {"value": "active"}})
    other = fake.seed("dcim/devices", {"name": "x1", "status": {"value": "active"}})
    loop = fake.seed("dcim/interfaces", {"name": "Loopback0", "device": {"id": old["id"]}})
    gi2 = fake.seed("dcim/interfaces", {"name": "GigabitEthernet2", "device": {"id": old["id"]}})
    x1_gi1 = fake.seed("dcim/interfaces", {"name": "GigabitEthernet1",
                                           "device": {"id": other["id"]}})
    theirs = fake.seed("ipam/ip-addresses", {"address": held,
                                             "assigned_object_type": "dcim.interface",
                                             "assigned_object_id": gi2["id"]})
    mine = fake.seed("ipam/ip-addresses", {
        "address": mine_addr, "assigned_object_type": "dcim.interface",
        "assigned_object_id": loop["id"],
        "tags": [{"id": 900, "slug": guard.MANAGED_TAG_SLUG, "name": guard.MANAGED_TAG}]})
    guard.record_created("Branch", "ipam/ip-addresses", mine["id"], mine_addr)
    old["primary_ip4" if family == "ipv4" else "primary_ip6"] = {"id": theirs["id"]}

    def sync(name, devs, dry_run=False, **k):
        found = []
        nbc._say_held_by_decommissioned(fake, "http://nb.invalid", ip, new["id"], "r9",
                                        held=found)
        nbc._drain_write_failures()
        if not dry_run:
            nb["sent"].append(name)
        return {"plan": nb["plan"]["value"], "held_by_retired": found}
    monkeypatch.setattr(nbc, "sync_list_to_netbox", sync)
    return dict(nb, fake=fake, ip=ip, held=held, mine=mine, theirs=theirs, old=old,
                x1_gi1=x1_gi1, other_addr=other_addr, family=family)


def _flat(html):
    return re.sub(r"\s+", " ", html).replace("&#39;", "'")


def _import_card(networks):  # noqa: F811
    _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Branch",
                                                      "device": "r9"})
    job = _job(card)
    return job, _flat(networks["client"].get(f"/v2/netbox/job/{job}").get_data(as_text=True))


def _free_card(networks, retired, **over):  # noqa: F811
    data = {"operation": "free", "list": "Branch", "device": "r9",
            "holder": str(retired["old"]["id"]), "address": retired["ip"], **over}
    r, card = _post(networks, "/v2/netbox/preview", data)
    m = re.search(r'/v2/netbox/job/([0-9a-f]{32})', card)
    if not m:
        return r, None, _flat(card)
    job = m.group(1)
    return r, job, _flat(networks["client"].get(f"/v2/netbox/job/{job}").get_data(as_text=True))


def _wrote_nothing(fake):
    return not (fake.posts or fake.patches or fake.deletes)


def _addr(fake, oid):
    return next((o for o in fake.objects("ipam/ip-addresses") if o["id"] == oid), None)


class TestTheImportOffersIt:
    def test_the_import_preview_names_the_holder_and_offers_free(self, networks, retired):
        _job_id, card = _import_card(networks)
        old, ip = retired["old"], retired["ip"]
        assert (f"<strong>{retired['held']} is held by r9-retired-21</strong> (NetBox device "
                f"{old['id']}, Decommissioning)") in card, card[:3000]
        form = card.split('name="operation" value="free"')[1].split("</form>")[0]
        for field, value in (("list", "Branch"), ("device", "r9"),
                             ("holder", str(old["id"])), ("address", ip)):
            assert f'<input type="hidden" name="{field}" value="{value}">' in form, field
        assert f'<span class="op-idle">Free {ip} from r9-retired-21…</span>' in form
        assert _wrote_nothing(retired["fake"])

    def test_no_holder_offers_nothing(self, networks, retired):
        """The control: with the record active, nothing is held by a retired record, and the
        card offers no Free."""
        retired["old"]["status"] = {"value": "active"}
        _job_id, card = _import_card(networks)
        assert 'value="free"' not in card and "is held by" not in card


class TestThePreview:
    def test_it_names_each_write_and_writes_nothing(self, networks, retired):
        r, job, card = _free_card(networks, retired)
        old, mine, theirs = retired["old"], retired["mine"], retired["theirs"]
        assert r.status_code == 200 and job, card[:2000]
        assert f"Free {retired['ip']} in NetBox from r9-retired-21" in card
        assert (f"<li>update dcim/devices #{old['id']} r9-retired-21: clears primary_ip4, "
                "primary_ip6</li>") in card, card[:4000]
        assert (f"<li>delete ipam/ip-addresses #{mine['id']} {mine['address']}: tagged "
                "nmas-managed and recorded as created by Mercury</li>") in card
        assert (f"<li>unassign ipam/ip-addresses #{theirs['id']} {theirs['address']}: kept in "
                "NetBox, assigned to nothing</li>") in card
        assert f'<span class="op-idle">Free {retired["ip"]}</span>' in card
        assert "turn NetBox writes on with this confirm" in card
        assert _wrote_nothing(retired["fake"])

    def test_a_tagged_address_mercury_did_not_record_is_unassigned_not_deleted(
            self, networks, retired):
        from modules import netbox_guard as guard
        guard.forget_created("Branch")
        _r, _job_id, card = _free_card(networks, retired)
        mine = retired["mine"]
        assert f"<li>unassign ipam/ip-addresses #{mine['id']} {mine['address']}" in card
        assert "<li>delete ipam/ip-addresses" not in card

    def test_a_holder_that_is_not_decommissioning_is_refused_naming_both(self, networks,
                                                                         retired):
        retired["old"]["status"] = {"value": "active"}
        _r, _job_id, card = _free_card(networks, retired)
        assert (f"NetBox device {retired['old']['id']} (r9-retired-21) is active, not "
                "Decommissioning") in card, card[:3000]
        assert 'gate' not in card.split("Free ")[0] and "Freeing…" not in card
        assert _wrote_nothing(retired["fake"])

    def test_an_address_the_record_does_not_hold_is_refused(self, networks, retired):
        _r, _job_id, card = _free_card(networks, retired, address=retired["other_addr"]
                                       .split("/")[0])
        assert (f"{retired['other_addr'].split('/')[0]} is no longer held by r9-retired-21 "
                f"(NetBox device {retired['old']['id']})") in card, card[:3000]
        assert "Freeing…" not in card

    @pytest.mark.parametrize("holder,address", [("x", "192.0.2.9"), ("0", "192.0.2.9"),
                                                ("7", "not-an-address"), ("7", "")])
    def test_a_malformed_holder_or_address_is_refused(self, networks, retired, holder,
                                                      address):
        r, job, card = _free_card(networks, retired, holder=holder, address=address)
        assert r.status_code == 400 and job is None
        assert "Free needs a NetBox device id and an address" in card


class TestTheConfirm:
    def _confirm(self, networks, job, **data):  # noqa: F811
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm", data)
        return r, _flat(html)

    def test_it_frees_the_record_through_the_write_gate_and_reads_back(self, networks,
                                                                       retired):
        from modules import netbox_guard as guard
        from tests.conftest import TEST_PERSON
        fake, old, mine, theirs = (retired["fake"], retired["old"], retired["mine"],
                                   retired["theirs"])
        _r, job, _card = _free_card(networks, retired)
        r, html = self._confirm(networks, job, permit_writes="on")
        assert r.status_code == 200, html[:3000]
        # Mercury's is deleted; the person's unassigned and kept; the primaries cleared first.
        assert fake.deletes == [("ipam/ip-addresses", mine["id"])]
        kept = _addr(fake, theirs["id"])
        assert kept and (kept["assigned_object_type"], kept["assigned_object_id"]) == (None,
                                                                                      None)
        assert fake.patches[0] == ("dcim/devices", old["id"],
                                   {"primary_ip4": None, "primary_ip6": None})
        assert not fake.posts
        # Read back: the record holds none; it is still Decommissioning, named as it was.
        from modules.netbox_client import _nb_get
        assert _nb_get(fake, "http://nb.invalid", "ipam/ip-addresses/",
                       device_id=old["id"]) == []
        assert old["status"] == {"value": "decommissioning"} and old["name"] == "r9-retired-21"
        # Drawn in place, and the import offered again.
        assert (f"{retired['ip']} is free: r9-retired-21 read back holding no IP address "
                f"(deleted {mine['address']}; unassigned {theirs['address']}, kept in NetBox). "
                "Preview the import again to give it to r9.") in html, html[:3000]
        assert '<span class="op-idle">Preview the import of r9 again…</span>' in html
        assert nb_sent_nothing(retired)
        # Recorded: the job's record names who and each address; the befores in the
        # modification record; Mercury's created entry for the deleted address forgotten.
        from modules import netbox_jobs
        record = netbox_jobs.read(job)
        assert record["actor"] == TEST_PERSON and record["state"] == "imported"
        assert [a["id"] for a in record["free_record"]["deleted"]] == [mine["id"]]
        assert [a["id"] for a in record["free_record"]["unassigned"]] == [theirs["id"]]
        modified = json.dumps(guard.read_modified()[0])
        assert str(theirs["id"]) in modified and str(old["id"]) in modified, modified[:2000]
        assert not guard.was_created_by_nmas("Branch", "ipam/ip-addresses", mine["id"])
        # Read again later, the card draws the same result.
        again = _flat(networks["client"].get(f"/v2/netbox/job/{job}").get_data(as_text=True))
        assert f"{retired['ip']} is free" in again

    def test_an_unassign_netbox_did_not_keep_is_drawn_as_not_freed(self, networks, retired):
        """NetBox answered the unassign but kept the address on the record: the read-back
        finds it, and the card says it was not freed, naming it, never green."""
        fake, theirs = retired["fake"], retired["theirs"]
        _r, job, _card = _free_card(networks, retired)
        real = fake.patch

        def keeps(url, json=None, timeout=None):
            if "ipam/ip-addresses" in url:
                fake.patches.append(("ipam/ip-addresses", theirs["id"], dict(json or {})))
                return type("R", (), {"ok": True, "status_code": 200,
                                      "json": lambda s: dict(theirs),
                                      "raise_for_status": lambda s: None, "text": ""})()
            return real(url, json=json, timeout=timeout)
        fake.patch = keeps
        r, html = self._confirm(networks, job, permit_writes="on")
        assert r.status_code == 200, html[:3000]
        assert (f"{retired['ip']} was not freed from r9-retired-21: r9-retired-21 still holds "
                f"{theirs['address']} after its addresses were deleted or unassigned") in html
        assert "notice-warn" in html and "is free" not in html
        from modules import netbox_jobs
        assert netbox_jobs.read(job)["state"] == "failed"

    def test_writes_off_and_not_permitted_is_refused_and_nothing_written(self, networks,
                                                                         retired):
        _r, job, _card = _free_card(networks, retired)
        r, html = self._confirm(networks, job)
        assert r.status_code == 403 and "NetBox writes are off for every network" in html
        assert _wrote_nothing(retired["fake"]) and retired["switch"]["on"] is False

    def test_an_address_that_moved_since_the_preview_is_refused(self, networks, retired):
        fake, theirs = retired["fake"], retired["theirs"]
        _r, job, _card = _free_card(networks, retired)
        moved = _addr(fake, theirs["id"])
        moved["assigned_object_id"] = retired["x1_gi1"]["id"]       # a person moved it
        r, html = self._confirm(networks, job, permit_writes="on")
        assert r.status_code == 409, html[:3000]
        assert (f"{retired['ip']} is no longer held by r9-retired-21 (NetBox device "
                f"{retired['old']['id']}): the preview read it there, and NetBox now holds "
                f"{retired['mine']['address']} on that record") in html
        assert "Nothing was written to NetBox." in html
        assert _wrote_nothing(fake)

    def test_another_address_on_the_record_moves_the_hash_and_is_refused(self, networks,
                                                                         retired):
        fake = retired["fake"]
        _r, job, _card = _free_card(networks, retired)
        gi2 = next(i for i in fake.objects("dcim/interfaces")
                   if i["name"] == "GigabitEthernet2")
        fake.seed("ipam/ip-addresses", {"address": retired["other_addr"],
                                        "assigned_object_type": "dcim.interface",
                                        "assigned_object_id": gi2["id"]})
        r, html = self._confirm(networks, job, permit_writes="on")
        assert r.status_code == 409, html[:3000]
        assert (f"what NetBox device {retired['old']['id']} holds changed since the preview of "
                f"freeing {retired['ip']}: the preview's plan hashed ") in html
        assert ", NetBox's now hashes " in html and "(3 address(es): " in html
        assert _wrote_nothing(fake)

    def test_a_record_no_longer_decommissioning_at_the_confirm_is_refused(self, networks,
                                                                          retired):
        _r, job, _card = _free_card(networks, retired)
        retired["old"]["status"] = {"value": "active"}
        r, html = self._confirm(networks, job, permit_writes="on")
        assert r.status_code == 409 and "is active, not Decommissioning" in html, html[:3000]
        assert _wrote_nothing(retired["fake"])

    def test_a_non_person_is_refused(self, networks, retired, monkeypatch):
        from modules import identity
        _r, job, _card = _free_card(networks, retired)
        svc = identity.Identity(actor="service:abc.access", kind="service",
                                service_id="abc.access", verified=True, outcome="ok",
                                peer="198.51.100.7", peer_trusted=True, header_present=True)
        monkeypatch.setattr(identity, "identify", lambda _r: svc)
        r = networks["client"].post(f"/v2/netbox/job/{job}/confirm",
                                    data={"permit_writes": "on"},
                                    headers={"HX-Request": "true"})
        assert r.status_code == 403
        assert _wrote_nothing(retired["fake"])

    def test_a_confirm_is_used_once(self, networks, retired):
        _r, job, _card = _free_card(networks, retired)
        assert self._confirm(networks, job, permit_writes="on")[0].status_code == 200
        r, html = self._confirm(networks, job, permit_writes="on")
        assert r.status_code == 409 and "not one ready to confirm" in html


class TestOneHome:
    def test_retire_and_free_call_the_same_freeing_code(self):
        """Retire's NetBox step and Free call `retire.free_netbox_addresses` and read back
        through `retire.netbox_addresses_left`; neither writes an address on its own."""
        import inspect

        from modules import netbox_ops
        from modules.nsot import retire
        for func in (retire._retire_netbox_record, netbox_ops.free):
            src = inspect.getsource(func)
            assert "free_netbox_addresses(" in src and "netbox_addresses_left(" in src, func
            assert "_nb_delete(" not in src and "ipam/ip-addresses/{" not in src, func


def nb_sent_nothing(retired):
    """Free runs no import: the import's sync was never called to write."""
    return retired["sent"] == []
