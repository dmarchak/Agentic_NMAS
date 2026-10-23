"""The one-decision out-of-band onboarding (modules/nsot/oob_onboard.py, its adapter
modules/nsot/oob_steps.py; the operator's approved design of 2026-10-23 with his changes).

End to end on loopback, on the console survey's world (tests/test_console_ztp.World: the shared
fake NetBox holding the Planned device and its console path, Mercury's port record, a fake raw
TCP console counting every byte it receives, answering with the real console text where a
capture holds it), with what this path reads besides: the Planned record's address in NetBox
IPAM, its cable to the relay, and the relay in committed intent. Create, its undo, the MAC's
record and SSH's answer are stood in for (each its own seam), so the orchestration is tested
alone; the five console pieces are the adapter's stand-ins (Phase A's at the merge).

- eligibility: offered only with a console path AND a port record; else the reason and the fix;
- derive: the address, mask, VLAN, interface, uplink, gateway and config server, each with
  where it came from; asked only for the uplink NetBox does not cable; an IPv6 planned address
  refused by name (C1245);
- the review: every byte the console may be sent in the program and in the hash; a router, a
  server that disagrees with Create's plan, an unreadable NetBox each refused;
- the run: the blank verdict decides typing (nothing created or typed on a device not blank,
  signed in or asking for a login); Create once, after the blank check; each line's answer read,
  a refusal stopping it there with Create's objects undone; the read-back and the MAC; the copy
  verified; the key's settle waited out before SSH is asked; every stop naming what it compared,
  what was sent and what was undone; refused before anything is sent (hash, person, reason,
  busy).
"""

import socket
import types

import pytest

from modules.nsot import oob_onboard as O
from tests import oob_fake_steps as S
from tests.test_console_ztp import ACTOR, LIST, World, _real

ADDRESS, MASK, GATEWAY, SERVER = "192.0.2.14", "255.255.255.252", "192.0.2.13", "192.0.2.10"
FAST = O.Timings(settle_s=0.05, quiet_s=0.3, step_timeout_s=3.0, poll_s=0.02, bound_s=60.0,
                 copy_timeout_s=5.0, key_settle_s=120.0, answer_bound_s=30.0,
                 answer_every_s=10.0)
FIELDS = {"list_name": LIST, "hostname": "edge1", "platform": "cisco_ios", "role": "switch",
          "domain": "example.net", "mgmt_interface": "", "uplink": ""}
MAC_TEXT = "0c00.0875.8001"


def facts(prefix="192.0.2.12/30", address=GATEWAY, helpers=(SERVER,)):
    return {"IPv4": {prefix: [{"device": "relay1", "iface": "GigabitEthernet3",
                               "address": address, "relays": list(helpers),
                               "network": LIST}]}, "errors": []}


def seed_link(fake, dev, address=f"{ADDRESS}/30") -> dict:
    """What this path reads of NetBox beside the console path: the relay's device, the
    Planned device's Vlan1 holding its planned *address*, and its Gi0/1 cabled to the relay's
    Gi3. ``{"relay", "vlan1", "up", "far", "link", "ip"}`` (tests/v2_context.py seeds the
    same)."""
    out = {"relay": fake.seed("dcim/devices", {"name": "relay1", "status": "active"})}
    out["vlan1"] = fake.seed("dcim/interfaces", {"name": "Vlan1", "device": {"id": dev["id"]}})
    out["up"] = fake.seed("dcim/interfaces", {"name": "GigabitEthernet0/1",
                                              "device": {"id": dev["id"]}})
    out["far"] = fake.seed("dcim/interfaces", {"name": "GigabitEthernet3",
                                               "device": {"id": out["relay"]["id"]}})
    out["link"] = fake.seed("dcim/cables", {
        "a_terminations": [{"object_type": "dcim.interface", "object_id": out["up"]["id"]}],
        "b_terminations": [{"object_type": "dcim.interface", "object_id": out["far"]["id"]}],
        "status": "connected", "label": ""})
    out["ip"] = fake.seed("ipam/ip-addresses", {
        "address": address, "assigned_object_type": "dcim.interface",
        "assigned_object_id": out["vlan1"]["id"],
        "assigned_object": {"id": out["vlan1"]["id"], "name": "Vlan1",
                            "device": {"id": dev["id"]}}})
    return out


def fake_plan(list_name, fields, d, secret):
    """Create's plan as `onboard.build_plan` answers it for the derived fields (its summary,
    intent and config; Phase A's `ztp_console` plan's config server)."""
    summary = {"hostname": fields["hostname"], "mgmt_ip": d["address"],
               "mgmt_mask": d["mask"], "manager_interface": d["interface"],
               "manager_gateway": d["gateway"], "netbox_id": d["netbox_id"]}
    return types.SimpleNamespace(summary=summary, host_vars={"hostname": "edge1"},
                                 bootstrap_config="hostname edge1\nend\n",
                                 blocking_reasons=[], planned_netbox_id=d["netbox_id"],
                                 ztp_server=SERVER)


class OobWorld(World):
    """The survey's world, with the Planned record's address, its cable to the relay, and the
    stand-ins for Create, its undo, the MAC's record and SSH."""

    def __init__(self, tmp_path, monkeypatch, family=socket.AF_INET, address=f"{ADDRESS}/30"):
        super().__init__(tmp_path, monkeypatch, family)
        S.install(monkeypatch)          # Phase A's pieces stood in at the adapter
        got = seed_link(self.fake, self.dev, address)
        self.relay, self.vlan1, self.up = got["relay"], got["vlan1"], got["up"]
        self.far, self.link, self.ip = got["far"], got["link"], got["ip"]
        self.facts = facts()
        self.created, self.undone, self.macs, self.probes, self.slept = [], [], [], [], []
        self.clock = [1000.0]
        self.answers = [(True, "port 22 accepted")]

    def uncable(self):
        """The uplink's cable to the relay gone from NetBox (the fake draws an interface's
        cable from its cables, as NetBox does)."""
        self.fake.store["dcim/cables"] = [c for c in self.fake.store["dcim/cables"]
                                          if c["id"] != self.link["id"]]

    def ip_like(self, **over):
        """Another address on the device's Vlan1, a new object (its own id)."""
        return dict({k: v for k, v in self.ip.items() if k != "id"}, **over)

    # the seams
    def plan_builder(self, list_name, fields, d, secret):
        return fake_plan(list_name, fields, d, secret)

    def create(self, list_name, fields, d, previewed, actor):
        self.created.append((list_name, fields["hostname"], previewed, actor))
        return {"ok": True, "completed": ["credentials", "commit", "render"], "commit": "c0ffee",
                "reason": ""}

    def undo(self, list_name, hostname, actor):
        self.undone.append(hostname)
        return {"ok": True, "undone": ["intent: removed host_vars/edge1.yml"], "remaining": []}

    def record_mac(self, list_name, hostname, mac, actor):
        self.macs.append(mac)
        return ""

    def probe(self, address):
        self.probes.append((address, self.clock[0]))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    def wall(self):
        return self.clock[0]

    def sleep(self, s):
        self.slept.append(s)
        self.clock[0] += s

    def nbk(self):
        return {"session": self.fake, "base": "http://nb.invalid", "facts": self.facts,
                "plan_builder": self.plan_builder}

    def review(self, **over):
        return O.preview(LIST, dict(FIELDS, **over), values={}, **self.nbk())

    def run(self, answers, *, greeting=b"", confirmed=None, actor=ACTOR, verified="access",
            reason="a new access switch", fields=None):
        p = self.review(**(fields or {}))
        assert p["ok"] or confirmed is not None, p["refusals"]
        self.consoles.append((greeting, list(answers)))
        return O.run(LIST, dict(FIELDS, **(fields or {})),
                     confirmed_hash=p["hash"] if confirmed is None else confirmed,
                     actor=actor, actor_verified=verified, reason=reason, timings=FAST,
                     wall=self.wall, sleep=self.sleep, values={}, probe=self.probe,
                     create=self.create, undo=self.undo, record_mac=self.record_mac,
                     **self.nbk())


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = OobWorld(tmp_path, monkeypatch)
    yield w
    w.server.close()


# ── the console's answers ──────────────────────────────────────────────────────────────────

def _echo(line, prompt):
    return f"{line}\r\n{prompt}".encode()


def _lines():
    return S.static_lines(None, {"hostname": "edge1", "interface": "GigabitEthernet0/1",
                                 "vlan": 1, "address": ADDRESS, "mask": MASK,
                                 "gateway": GATEWAY})


def _prompt(line, name):
    text = line.strip()
    if text == "end":
        return f"{name}#"
    if line.startswith(" "):
        return f"{name}(config-line)#" if text.startswith("exec-timeout") else \
            f"{name}(config-if)#"
    if text.startswith("vlan"):
        return f"{name}(config-vlan)#"
    if text.startswith("interface"):
        return f"{name}(config-if)#"
    if text.startswith("line"):
        return f"{name}(config-line)#"
    return f"{name}(config)#"


READS = {
    "show running-config interface GigabitEthernet0/1":
        "Building configuration...\r\n\r\nCurrent configuration : 90 bytes\r\n!\r\n"
        "interface GigabitEthernet0/1\r\n switchport mode access\r\n media-type rj45\r\n"
        " negotiation auto\r\nend\r\n",
    "show running-config interface Vlan1":
        "Building configuration...\r\n\r\nCurrent configuration : 70 bytes\r\n!\r\n"
        "interface Vlan1\r\n ip address 192.0.2.14 255.255.255.252\r\nend\r\n",
    "show running-config | section line con 0": "line con 0\r\n exec-timeout 15 0\r\n",
    "show running-config | include ^hostname|^ip default-gateway":
        "hostname edge1\r\nip default-gateway 192.0.2.13\r\n",
    "show interfaces Vlan1": "Vlan1 is up, line protocol is up\r\n  Hardware is Ethernet SVI, "
                             f"address is {MAC_TEXT} (bia {MAC_TEXT})\r\n",
}
COPY_OK = ("Accessing tftp://192.0.2.10/edge1.cfg...\r\nLoading edge1.cfg from 192.0.2.10 "
           "(via Vlan1): !\r\n[OK - 2048 bytes]\r\n\r\n2048 bytes copied in 1.2 secs\r\n")


def saved_nvram(size=1234):
    """`dir nvram:` on a switch with a saved startup configuration of *size* bytes."""
    return _echo("dir nvram:", "") + (f"\r\nDirectory of nvram:/\r\n\r\n  253  -rw-        {size}"
                                      "                    <no date>  startup-config"
                                      "\r\n\r\nSwitch#").encode()


def answers(*, nvram=None, recheck=None, refuse_at=None, reads=None, copy=COPY_OK, upto=None):
    """A blank switch at `Switch>` answering the whole program: the wake, enable, the pager,
    the blank check, the blank check again (*recheck*, else *nvram*), each line (`refuse_at`:
    the line answered by IOS's refusal), each read-back, the copy. *upto*: stop answering
    after that many sends."""
    _wake, enable, blank = _real()
    out = [b"\r\nSwitch>", enable, _echo("terminal length 0", "Switch#"), nvram or blank,
           recheck or nvram or blank]
    name = "Switch"
    for i, line in enumerate(_lines()):
        if line.startswith("hostname "):
            name = line.split()[1]
        if refuse_at is not None and line.strip() == refuse_at:
            out.append(f"{line}\r\n               ^\r\n% Invalid input detected at '^' marker."
                       f"\r\n\r\n{_prompt(line, name)}".encode())
            continue
        out.append(_echo(line, _prompt(line, name)))
    plan = S.readback_plan(_lines())
    texts = dict(READS, **(reads or {}))
    for cmd in plan["reads"]:
        out.append(f"{cmd}\r\n{texts[cmd]}{name}#".encode())
    out.append(f"{S.copy_line(SERVER, 'edge1.cfg')}\r\n{copy}{name}#".encode())
    return out[:upto] if upto else out


def _sent_lines(world, index=0):
    got = world.received(index).decode("ascii", "replace").split("\r")
    return [line for line in got if line]


# ── eligibility ───────────────────────────────────────────────────────────────────────────

class TestEligibility:
    def nb(self, w):
        return {"session": w.fake, "base": "http://nb.invalid"}

    def test_a_console_path_and_a_port_record_make_it_available(self, world):
        got = O.eligibility(LIST, "edge1", **self.nb(world))
        assert got["state"] == "ok" and got["netbox_id"] == world.dev["id"]
        assert got["port_id"] == world.sport["id"]

    def test_no_name_asks_for_one_and_reads_nothing(self):
        got = O.eligibility(LIST, "", session=object(), base="x")
        assert got["state"] == "no_name" and "give the device's name first" in got["why"]

    def test_no_planned_record_says_so_and_links_netbox(self, world):
        got = O.eligibility(LIST, "nosuch", **self.nb(world))
        assert got["state"] == "no_record"
        assert got["why"].startswith("NetBox holds no device named nosuch")
        assert got["fix"] == {"href": "http://nb.invalid/dcim/devices/",
                              "words": "Open NetBox's devices", "where": "netbox"}

    def test_another_status_is_refused_naming_it(self, world):
        world.dev["status"] = "active"
        got = O.eligibility(LIST, "edge1", **self.nb(world))
        assert got["state"] == "no_record" and "with status active, not Planned" in got["why"]

    def test_no_console_path_names_the_device_and_links_its_netbox_page(self, world):
        world.fake.store["dcim/cables"] = [c for c in world.fake.store["dcim/cables"]
                                           if c["id"] != world.cable["id"]]
        got = O.eligibility(LIST, "edge1", **self.nb(world))
        assert got["state"] == "no_path"
        assert got["why"].startswith("No console path in NetBox for edge1")
        assert got["fix"]["href"] == f"http://nb.invalid/dcim/devices/{world.dev['id']}/"
        assert got["fix"]["words"] == "Open edge1 in NetBox"

    def test_no_port_record_names_the_port_and_points_at_console_servers(self, world):
        from modules.nsot import console_servers
        console_servers.remove_port(world.sport["id"], actor=ACTOR)
        got = O.eligibility(LIST, "edge1", **self.nb(world))
        assert got["state"] == "no_port" and got["fix"]["where"] == "console_servers"
        assert got["why"] == (f"cons-1's port port 5 (NetBox {world.sport['id']}) has no record "
                              "in Mercury, so Mercury does not know how to reach it")

    def test_an_unreachable_netbox_is_unreadable_never_unavailable(self, monkeypatch):
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (False, "no token", None, ""))
        got = O.eligibility(LIST, "edge1")
        assert got["state"] == "unreadable" and "NetBox is not reachable" in got["why"]


# ── derive ────────────────────────────────────────────────────────────────────────────────

class TestDerive:
    def derive(self, w, role="switch", asked=None):
        return O.derive(LIST, "edge1", role, asked, session=w.fake, base="http://nb.invalid",
                        facts=w.facts)

    def test_every_field_is_derived_with_where_it_came_from(self, world):
        d = self.derive(world)
        assert d["refused_by"] == {} and d["asked"] == []
        assert (d["address"], d["mask"], d["vlan"], d["interface"], d["uplink"],
                d["gateway"], d["server"], d["filename"]) == \
            (ADDRESS, MASK, 1, "Vlan1", "GigabitEthernet0/1", GATEWAY, SERVER, "edge1.cfg")
        assert d["from"]["address"].startswith("NetBox IPAM, the one address assigned to it "
                                               f"({ADDRESS}/30, id {world.ip['id']})")
        assert d["from"]["uplink"] == f"NetBox: cable {world.link['id']} to relay1 " \
                                      "GigabitEthernet3"
        assert d["from"]["gateway"] == ("committed intent: relay1 GigabitEthernet3's own "
                                        "address on 192.0.2.12/30")
        assert d["netbox_id"] == world.dev["id"]

    def test_the_vlan_is_the_interface_the_address_is_on(self, world):
        world.vlan1["name"] = "Vlan10"
        world.ip["assigned_object"]["name"] = "Vlan10"
        d = self.derive(world)
        assert d["vlan"] == 10 and d["interface"] == "Vlan10"

    def test_an_ipv6_planned_address_is_refused_by_name(self, tmp_path, monkeypatch):
        w = OobWorld(tmp_path, monkeypatch, address="2001:db8::14/64")
        try:
            d = self.derive(w)
            assert "IPv6 (2001:db8::14/64)" in d["refused_by"]["address"]
            assert "C1245" in d["refused_by"]["address"] and d["gateway"] == ""
        finally:
            w.server.close()

    def test_no_address_in_netbox_is_refused_saying_where_to_plan_it(self, world):
        world.fake.store["ipam/ip-addresses"] = []
        assert "NetBox assigns no address to edge1" in self.derive(world)["refused_by"]["address"]

    def test_two_addresses_and_no_primary_are_refused(self, world):
        world.fake.seed("ipam/ip-addresses", world.ip_like(address="192.0.2.18/30"))
        got = self.derive(world)["refused_by"]["address"]
        assert got.startswith("NetBox assigns 2 addresses to edge1 and marks no primary")

    def test_the_primary_address_wins_over_another(self, world):
        other = world.fake.seed("ipam/ip-addresses", world.ip_like(
                                                          address="192.0.2.22/30"))
        world.dev["primary_ip4"] = {"id": other["id"]}
        world.facts = facts(prefix="192.0.2.20/30", address="192.0.2.21")
        d = self.derive(world)
        assert d["address"] == "192.0.2.22" and "its primary IPv4 address" in d["from"]["address"]

    def test_no_cable_to_the_relay_asks_for_the_uplink(self, world):
        world.uncable()
        d = self.derive(world)
        assert d["asked"] == ["uplink"]
        assert d["why"]["uplink"] == ("NetBox shows no cable from edge1 to relay1, and Mercury "
                                      "keeps no LLDP table to read it from: name the port it "
                                      "reaches the relay on")
        assert "uplink" in d["refused_by"]
        typed = self.derive(world, asked={"uplink": "GigabitEthernet0/2"})
        assert typed["uplink"] == "GigabitEthernet0/2" and typed["refused_by"] == {}
        assert typed["from"]["uplink"] == "asked: typed in the review"
        bad = self.derive(world, asked={"uplink": "Gi0/2; reload"})
        assert "is not a valid interface" in bad["refused_by"]["uplink"]

    def test_no_relay_in_intent_is_refused_with_the_link_s_reason(self, world):
        world.facts = {"IPv4": {}, "errors": []}
        got = self.derive(world)["refused_by"]["relay"]
        assert "no interface in committed intent is on a prefix holding it" in got

    def test_a_relay_with_no_helper_names_the_unknown_server(self, world):
        world.facts = facts(helpers=())
        assert "relays to no DHCP server" in self.derive(world)["refused_by"]["relay"]

    def test_a_router_s_interface_is_its_uplink(self, world):
        assert self.derive(world, role="router")["interface"] == "GigabitEthernet0/1"


# ── the review ────────────────────────────────────────────────────────────────────────────

class TestTheReview:
    def test_a_clean_review_names_everything_and_binds_it(self, world):
        p = world.review()
        assert p["ok"], p["refusals"]
        assert p["device"] == "edge1" and p["device_id"] == world.dev["id"]
        assert p["profile"]["name"] == "cisco_ios_switch" and len(p["profile"]["sha256"]) == 64
        assert p["lines"] == list(_lines())
        assert p["copy"] == "copy tftp://192.0.2.10/edge1.cfg running-config"
        assert len(p["creates"]) == 4 and "no Kea subnet" in p["creates"][3]
        assert f"NetBox id {world.dev['id']}" in p["creates"][2]
        assert len(p["hash"]) == 64 and p["not_doing"] == list(O.NOT_DOING)
        prog = p["program"]
        typed = [t for _s, t in prog["lines"]]
        assert typed == [l + "\r" for l in _lines()]
        assert [t for _s, t in prog["read_back"]] == [c + "\r" for c in p["read_back"]]
        assert [t for _s, t in prog["copy"]] == [p["copy"] + "\r"]

    def test_the_hash_moves_with_what_the_console_is_sent(self, world):
        before = world.review()["hash"]
        world.ip["address"] = "192.0.2.18/30"
        world.facts = facts(prefix="192.0.2.16/30", address="192.0.2.17")
        assert world.review()["hash"] != before
        world.ip["address"] = f"{ADDRESS}/30"
        world.facts = facts()
        assert world.review()["hash"] == before
        world.uncable()
        assert world.review(uplink="GigabitEthernet0/2")["hash"] != before

    def test_a_server_create_s_plan_disagrees_with_is_refused_naming_both(self, world):
        world.facts = facts(helpers=("192.0.2.11",))
        got = world.review()["refused_by"]["plan"]
        assert got == ("Create's plan copies from config server 192.0.2.10, and the relay's "
                       "helper target is 192.0.2.11")

    def test_a_router_is_refused_by_name(self, world):
        got = world.review(role="router")
        assert not got["ok"] and "built for a switch" in got["refused_by"]["role"]
        assert got["hash"] == ""

    def test_create_s_plan_refusals_are_the_review_s(self, world, monkeypatch):
        refuse = world.plan_builder

        def blocked(*a):
            return types.SimpleNamespace(**dict(vars(refuse(*a)),
                                                blocking_reasons=["'edge1' already has an "
                                                                  "identity"]))
        monkeypatch.setattr(world, "plan_builder", blocked)
        assert world.review()["refused_by"]["plan"] == "'edge1' already has an identity"

    def test_the_review_contacts_no_console(self, world):
        world.review()
        assert world.server.accepted == 0


# ── the run ───────────────────────────────────────────────────────────────────────────────

class TestTheRun:
    def test_a_blank_switch_is_onboarded_in_one_run(self, world):
        rec = world.run(answers())
        assert rec["outcome"] == "done", rec["reason"]
        assert rec["reason"] == f"edge1 answers at {ADDRESS}: ready to Verify"
        assert world.created == [(LIST, "edge1", world.review()["plan"]["fingerprint"], ACTOR)]
        assert world.undone == [] and world.macs == ["0c:00:08:75:80:01"]
        assert rec["mac"] == "0c:00:08:75:80:01" and rec["copy"]["bytes"] == 2048
        sent = _sent_lines(world)
        assert sent[:3] == ["enable", "terminal length 0", "dir nvram:"]
        assert [l for l in sent if l in _lines()] == list(_lines())
        assert sent[-1] == "copy tftp://192.0.2.10/edge1.cfg running-config"

    def test_the_bytes_written_are_exactly_the_program(self, world):
        rec = world.run(answers())
        p = world.review()
        prog = p["program"]
        want = (["\r", "enable\r"] + [t for _s, t in prog["reads"]]
                + [t for _s, t in prog["recheck"]] + [t for _s, t in prog["lines"]]
                + [t for _s, t in prog["read_back"]] + [t for _s, t in prog["copy"]])
        assert world.received().decode() == "".join(want)
        assert rec["bytes_written"] == len("".join(want))

    def test_ssh_is_asked_only_after_the_key_s_settle(self, world):
        world.answers = [(False, "no answer"), (True, "port 22 accepted")]
        rec = world.run(answers())
        assert rec["outcome"] == "done"
        first = world.probes[0][1]
        assert first >= rec["copied_at"] + FAST.key_settle_s
        assert rec["settle_until"] == rec["copied_at"] + FAST.key_settle_s
        assert rec["answering"]["tries"] == 2

    def test_not_answering_keeps_the_pending_device_and_says_so(self, world):
        world.answers = [(False, "port 22 refused")]
        rec = world.run(answers())
        assert rec["outcome"] == "not_answering" and world.undone == []
        assert rec["stop"]["compared"].startswith(f"SSH to {ADDRESS} through relay1 did not "
                                                  "answer within 30 s")
        assert "Kept: the pending device" in rec["reason"]
        # Asked at the settle's end and every 10 s until the bound: 0, 10, 20 and 30 s.
        assert rec["answering"]["tries"] == 4
        assert [round(at - world.probes[0][1]) for _a, at in world.probes] == [0, 10, 20, 30]

    def test_a_device_not_blank_is_never_typed_on_and_nothing_is_created(self, world):
        rec = world.run(answers(nvram=saved_nvram(), upto=4))
        assert rec["outcome"] == "not_blank" and world.created == [] and world.undone == []
        assert "nvram holds a startup configuration of 1234 bytes" in rec["reason"]
        assert "Nothing was created." in rec["reason"]
        assert not [l for l in _sent_lines(world) if l in _lines()]

    def test_a_blank_check_that_cannot_be_read_types_nothing(self, world):
        odd = _echo("dir nvram:", "") + b"\r\n%Error opening nvram:/ (No such device)\r\nSwitch#"
        rec = world.run(answers(nvram=odd, upto=4))
        assert rec["outcome"] == "not_blank" and world.created == []
        # The session stops at the refused read (C1593, merged with Phase A) and names it.
        assert rec["stop"]["compared"] == ("blank is unknown: 'dir nvram:' was refused: "
                                           "'%Error opening nvram:/ (No such device)'")
        assert not [l for l in _sent_lines(world) if l in _lines()]

    def test_a_configuration_saved_since_the_check_is_found_again_and_create_undone(self,
                                                                                    world):
        rec = world.run(answers(recheck=saved_nvram(99), upto=5))
        assert rec["outcome"] == "not_blank" and len(world.created) == 1
        assert world.undone == ["edge1"], "Create had run: its objects are undone"
        assert "the blank check again found startup-config is 99 bytes" in rec["reason"]
        assert not [l for l in _sent_lines(world) if l in _lines()]

    def test_a_blank_check_again_that_cannot_be_read_types_nothing_and_undoes(self, world):
        odd = _echo("dir nvram:", "") + b"\r\n%Error opening nvram:/ (No such device)\r\nSwitch#"
        rec = world.run(answers(recheck=odd, upto=5))
        assert rec["outcome"] == "not_blank" and world.undone == ["edge1"]
        assert ("the blank check again found 'dir nvram:' refused: '%Error opening nvram:/ "
                "(No such device)' (blank needs 0 or none)") in rec["reason"]
        assert not [l for l in _sent_lines(world) if l in _lines()]

    def test_an_unexpected_answer_to_the_wake_creates_nothing_and_undoes_nothing(self, world):
        rec = world.run([b"\r\n*** a banner and no prompt ***\r\n"])
        assert rec["outcome"] == "unexpected" and world.created == [] and world.undone == []
        assert rec["stop"]["compared"].startswith("expected a prompt answering the wake")

    def test_a_password_prompt_mid_lines_stops_there_and_undoes_create(self, world):
        got = answers()
        at = next(i for i, a in enumerate(got) if a.startswith(b"vlan 1\r\n"))
        got[at] = b"vlan 1\r\nPassword: "
        rec = world.run(got[:at + 1])
        assert rec["outcome"] == "unexpected" and world.undone == ["edge1"]
        assert rec["stop"]["compared"].startswith("expected config after 'vlan 1'")
        assert _sent_lines(world)[-1] == "vlan 1"

    def test_a_refused_read_back_stops_and_undoes(self, world):
        rec = world.run(answers(reads={"show running-config | section line con 0":
                                       "% Invalid input detected at '^' marker.\r\n"}))
        assert rec["outcome"] == "read_back" and world.undone == ["edge1"]
        assert rec["stop"]["compared"] == ("the read-back 'show running-config | section line "
                                           "con 0' was refused: \"% Invalid input detected at "
                                           "'^' marker.\"")

    def test_a_review_that_refuses_sends_nothing_whatever_hash_is_given(self, world):
        with pytest.raises(O.Refused) as err:
            world.run(answers(), confirmed="", fields={"role": "router"})
        assert "built for a switch" in str(err.value) and "Nothing was sent" in str(err.value)
        assert world.server.accepted == 0

    def test_a_console_found_signed_in_types_nothing(self, world):
        rec = world.run([b"\r\nSwitch#"])
        assert rec["outcome"] == "signed_in" and world.created == []
        assert rec["stop"]["compared"].startswith("the console answered at priv_exec")
        assert _sent_lines(world) == []

    def test_a_login_prompt_types_nothing(self, world):
        rec = world.run([b"\r\nUsername: "])
        assert rec["outcome"] == "login" and world.created == []

    def test_a_refused_line_stops_there_and_undoes_create(self, world):
        line = f"ip address {ADDRESS} {MASK}"
        rec = world.run(answers(refuse_at=line))
        assert rec["outcome"] == "refused_line" and world.undone == ["edge1"]
        assert rec["stop"]["compared"] == (f"'{line}' was refused: \"% Invalid input detected "
                                           "at '^' marker.\". Stopped there")
        sent = _sent_lines(world)
        assert sent[-1] == " " + line, "nothing after the refused line"
        assert "Undone: intent: removed host_vars/edge1.yml." in rec["reason"]
        assert "a reload returns it to its factory state" in rec["reason"]

    def test_a_line_the_read_back_does_not_find_stops_and_undoes(self, world):
        rec = world.run(answers(reads={"show running-config interface Vlan1":
                                       "interface Vlan1\r\n no ip address\r\nend\r\n"}))
        assert rec["outcome"] == "read_back" and world.undone == ["edge1"]
        assert f"typed 'ip address {ADDRESS} {MASK}'" in rec["stop"]["compared"]
        assert "copy tftp" not in world.received().decode()

    def test_a_mac_that_cannot_be_read_stops_and_undoes(self, world):
        rec = world.run(answers(reads={"show interfaces Vlan1": "Vlan1 is up\r\n"}))
        assert rec["outcome"] == "read_back" and world.undone == ["edge1"]
        assert "the MAC in use could not be read" in rec["stop"]["compared"]
        assert world.macs == []

    @pytest.mark.parametrize("copy,why", [
        ("%Error opening tftp://192.0.2.10/edge1.cfg (Timed out)\r\n", "holds a refusal"),
        ("Accessing tftp://192.0.2.10/edge1.cfg...\r\n[OK - 0 bytes]\r\n",
         "must move more than 0 bytes"),
        ("Accessing tftp://192.0.2.10/edge1.cfg...\r\n", "printed 0"),
        ("[OK - 10 bytes]\r\n% Invalid input detected at '^' marker.\r\n", "holds a refusal"),
    ], ids=["error", "zero-bytes", "no-ok", "refused-inside"])
    def test_a_copy_that_did_not_fetch_stops_and_undoes(self, world, copy, why):
        rec = world.run(answers(copy=copy))
        assert rec["outcome"] == "copy_failed" and world.undone == ["edge1"]
        assert why in rec["stop"]["compared"] and world.probes == []

    def test_create_refused_stops_with_nothing_typed_after_it(self, world, monkeypatch):
        monkeypatch.setattr(world, "create", lambda *a: {"ok": False, "completed": [],
                                                         "commit": "", "reason": "it moved"})
        rec = world.run(answers(upto=5))
        assert rec["outcome"] == "create_failed"
        assert rec["stop"]["compared"] == "Create did not complete: it moved (completed: none)"
        assert not [l for l in _sent_lines(world) if l in _lines()]

    def test_a_moved_hash_is_refused_naming_both_and_nothing_is_sent(self, world):
        with pytest.raises(O.Refused) as err:
            world.run(answers(), confirmed="0" * 64)
        assert f"({'0' * 64} -> {world.review()['hash']})" in str(err.value)
        assert "Nothing was sent" in str(err.value) and world.server.accepted == 0

    def test_only_a_verified_person_with_a_reason(self, world):
        with pytest.raises(O.Refused) as err:
            world.run(answers(), verified="none")
        assert "an out-of-band onboarding is confirmed by a verified person" in str(err.value)
        with pytest.raises(O.Refused) as err:
            world.run(answers(), reason="  ")
        assert "given a reason, and none was" in str(err.value)
        assert world.server.accepted == 0

    def test_a_device_held_by_another_operation_is_refused_by_name(self, world):
        from modules.nsot import device_ops
        with device_ops.hold(LIST, "edge1", "deploy", "other@example.invalid"):
            import threading
            got = {}
            t = threading.Thread(target=lambda: got.setdefault("e", _catch(world)))
            t.start()
            t.join(30)
        assert isinstance(got["e"], O.Refused)
        assert "deployed to" in str(got["e"]) and "other@example.invalid" in str(got["e"])
        assert world.server.accepted == 0

    def test_the_run_notes_each_step_as_it_begins_and_each_name_is_declared(self, world,
                                                                             monkeypatch):
        from modules.nsot import device_ops
        noted = []
        real = device_ops.note
        monkeypatch.setattr(device_ops, "note", lambda step, device=None: (
            noted.append(step), real(step, device)))
        world.run(answers())
        declared = [n for _k, _w, _waits, names in O.run_stepper_steps() for n in names]
        assert [n for n in noted if n in declared] == declared
        assert set(noted) <= set(declared) | {"onboard: undo"}


def _catch(world):
    try:
        world.run(answers())
    except Exception as exc:                          # noqa: BLE001 - the test reads it
        return exc
    return None


class TestStopWords:
    def test_a_stop_names_what_was_sent_and_undone(self):
        got = O.stop_words("refused_line", "'x' was refused", ["configure terminal", " x"],
                           {"undone": ["intent: removed"], "remaining": ["identity: kept"]})
        assert got == ("'x' was refused. Sent: configure terminal;  x. Undone: intent: "
                       "removed. Not undone: identity: kept. Nothing was saved on the device: "
                       "a reload returns it to its factory state.")

    def test_a_stop_before_create_says_nothing_was_created(self):
        assert O.stop_words("not_blank", "nvram holds 9 bytes", [], None) == \
            "nvram holds 9 bytes. Nothing was typed. Nothing was created."

    def test_the_settle_is_said_until_it_ends(self):
        rec = {"device": "edge1", "address": ADDRESS, "settle_until": 1200.0}
        assert O.settle_words(rec, now=1100.0) == ("waiting for edge1's SSH key to settle, "
                                                   "until 00:20:00 UTC")
        assert O.settle_words(rec, now=1200.0) == f"SSH at {ADDRESS} to answer"


class TestTheStandInsKeepPhaseAsShapes:
    def test_the_static_lines_end_with_the_console_timeout_and_never_route(self):
        lines = _lines()
        assert lines[0] == "configure terminal" and lines[-1] == "end"
        assert f"ip default-gateway {GATEWAY}" in lines
        assert not [l for l in lines if l.strip().startswith("ip route")]
        assert lines[-3:-1] == ("line con 0", " exec-timeout 15 0")

    @pytest.mark.parametrize("field,value", [("address", "2001:db8::14"),
                                             ("gateway", "2001:db8::13")], ids=["ipv6-address",
                                                                               "ipv6-gateway"])
    def test_an_ipv6_value_is_refused_by_name(self, field, value):
        params = {"hostname": "edge1", "interface": "GigabitEthernet0/1", "vlan": 1,
                  "address": ADDRESS, "mask": MASK, "gateway": GATEWAY, field: value}
        with pytest.raises(ValueError) as err:
            S.static_lines(None, params)
        assert "IPv6" in str(err.value) and "C1245" in str(err.value)

    def test_an_ipv6_config_server_is_refused_by_name(self):
        with pytest.raises(ValueError) as err:
            S.copy_line("2001:db8::10", "edge1.cfg")
        assert "IPv6" in str(err.value)

    def test_a_log_message_is_not_a_refusal_and_a_percent_line_is(self):
        assert S.refused_in("%LINK-3-UPDOWN: Interface Vlan1, changed state to up\r\n", None) \
            == ("", "")
        assert S.refused_in("ip address dhcp\r\n   ^\r\n% Invalid input detected at '^' "
                            "marker.\r\n", None) == ("% Invalid input detected at '^' marker.",
                                                     "ip address dhcp")
