"""The AI read set for routers and switches (board H, part H24; docs/HEAL_TO_INTENT.md 19.5, N20
and N21; `modules/ai/router_reads.py`), on three networks' settings, a credential store and an
inventory in this test's own folder, through H28's real read-only account
(`credentials.set_read_account`) and device state switch
(`egress_classes.turn_on_device_state`); no device (the session is faked at the reads engine's
seam, `connection.with_plain_connection`), no provider.

- **19.5's planted table, whole** (`match`, each refusal's words asserted beside its verdict, so
  a refusal for the wrong reason fails): the three writing modifiers, `| format`, a later
  segment that could write, a newline, a control character, a word the shape does not name, a
  spliced `; reload`, an address out of shape, a peer intent does not name, and `show
  running-config` while the configuration class is off; and the allowed forms, IPv4 beside
  IPv6.
- **The loop's form** (`read_loop.check` on `AI_READS`): each operation's arguments compared
  with the scope (a device the incident does not name, one with no read-only account, an
  interface its golden does not hold, an address outside the network, a dialect's form on the
  other platform), and every device state read refused, naming the class, while the network's
  device state class is off (H28's switch: off by default, on by an admin, off in one press).
- **The read-only account** is the reads engine's own resolver's answer
  (`reads.read_account_for`), per device of the inventory: none set is no account on any
  device, whatever deploy login its profiles carry.
- **The family is declared through `read_loop`'s transport rule**, its verbs show, ping and
  traceroute only, its pings and traceroutes inside 19.5's bounds, and the left-out commands
  refused with their reasons.
- **The executor** runs through the reads engine as kind `ai_analysis` with no extras and no
  session of its own: the engine signs in as the read-only account, records whom it signed in
  as, refuses a device without one by name with no session opened, and skips a held device by
  name.
- **The scope** is built from committed intent and the golden: interfaces, peers, addresses and
  subnets (IPv4 and IPv6), the dialect, and the actor words.
"""
import threading

import pytest

from modules import credentials
from modules import readonly_commands
from modules.ai import egress_classes
from modules.ai import read_loop as RL
from modules.ai import router_reads as R
from tests.test_sdn_connections import make_networks

NETWORK = "Branch"
DEPLOY_PW, RO_PW = "Deploy-Pass-5531", "ReadOnly-Pass-8812"
REASON = "lab ten analysis reads"
#: The inventory as `load_saved_devices` gives it (tests/test_read_only_account.py's shape): r3
#: and xe routers on IOS-XE, s1 and ios switches on IOS.
DEVICES = [{"hostname": "r3", "ip": "192.0.2.5", "device_type": "cisco_xe", "role": "router",
            "_platform": "cisco-ios-xe", "_site": "lab"},
           {"hostname": "s1", "ip": "2001:db8::6", "device_type": "cisco_ios", "role": "switch",
            "_platform": "cisco-ios", "_site": "lab"},
           {"hostname": "xe", "ip": "192.0.2.2", "device_type": "cisco_xe", "role": "router",
            "_platform": "cisco-ios-xe", "_site": "lab"},
           {"hostname": "ios", "ip": "2001:db8::2", "device_type": "cisco_ios",
            "role": "switch", "_platform": "cisco-ios", "_site": "lab"}]
INTENTS = {
    "r3": {"platform": "cisco_iosxe",
           "interfaces": [{"name": "GigabitEthernet4", "ipv4": "192.0.2.5 255.255.255.252",
                           "ipv6": ["2001:db8::5/64"]},
                          {"name": "Loopback0", "ipv4": "198.51.100.3 255.255.255.255",
                           "ipv6": ["2001:db8:ff::3/128"]}],
           "routing": {"bgp": {"asn": 65001, "neighbors": [
               "neighbor 192.0.2.6 remote-as 65002", "neighbor 2001:db8::6 remote-as 65002"]}}},
    "s1": {"platform": "cisco_ios",
           "interfaces": [{"name": "GigabitEthernet0/1", "ipv4": "192.0.2.6 255.255.255.252",
                           "ipv6": ["2001:db8::6/64"]}]},
}
GOLDENS = {"r3": "hostname r3\ninterface GigabitEthernet4\n ip address 192.0.2.5 "
                 "255.255.255.252\ninterface Loopback0\n no shutdown\n",
           "s1": "hostname s1\ninterface GigabitEthernet0/1\n no shutdown\n"}
#: r3's chain, as `credentials.resolve_read` names it when no profile on it carries one.
R3_NONE = ("no read-only account: none of the profiles it is looked for under "
           "(platform:cisco-ios-xe, role:router, site:lab, default) carries one")


class Session:
    """The reads engine's seams: who each session signed in as (the read-only one, and the
    deploy one, which must never open), and the answers."""

    def __init__(self):
        self.signed, self.deploy = [], []

    def plain(self, dev, fn):
        from modules.device import decrypt_field
        self.signed.append({"host": dev["hostname"], "username": dev.get("username"),
                            "password": decrypt_field(dev["password"]) if dev.get("password")
                            else ""})
        return fn(self)

    def temp(self, dev, fn):
        self.deploy.append(dev["hostname"])
        return fn(self)

    def answer(self, command):
        return f"{command}: answered"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """Three networks' settings, the credential store with deploy logins only (no read-only
    account: each test sets its own), the inventory, and the engine's session seams."""
    root = make_networks(tmp_path, monkeypatch)
    from modules import config
    monkeypatch.setattr(config, "get_list_data_dir",
                        lambda name: str(root / "lists" / config.list_slug(name)))
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path: [dict(d) for d in DEVICES])
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, c: conn.answer(c))
    session = Session()
    monkeypatch.setattr("modules.connection.with_plain_connection", session.plain)
    monkeypatch.setattr("modules.connection.with_temp_connection", session.temp)
    for name in ("role:router", "role:switch", "default"):
        credentials.save_profile(name, username="netops", password=DEPLOY_PW)
    return session


def _account(profile="default"):
    """The read-only account on *profile*. Set in each test's own body (never the fixture), so
    a parent without the account's code fails the test itself."""
    credentials.set_read_account(profile, "mercury-ro", RO_PW, actor="op@example.com",
                                 verified="access")


def _state_on(network=NETWORK):
    """The device state class turned on for *network* by an admin with a reason (H28's real
    switch), in the test's own body."""
    got = egress_classes.turn_on_device_state(network, REASON, actor="op@example.com",
                                              actor_verified="access", person=True)
    assert got.get("ok") is not False, got


def _ready():
    _account()
    _state_on()


def scope(**over):
    spec = dict(intents=INTENTS, goldens=GOLDENS, incident="inc-1",
                turned_on_by="admin@example.invalid")
    spec.update(over)
    return R.scope_for(NETWORK, ["r3", "s1"], **spec)


def match(command, device="r3", **over):
    return R.match(command, device, scope(**over), network=NETWORK)


# ── 19.5's planted table ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("command,said", [
    ("show interfaces GigabitEthernet4 | redirect flash:x",
     "REFUSED: output modifier 'redirect' is not a filter. It WRITES"),
    ("show interfaces GigabitEthernet4 | tee flash:x",
     "REFUSED: output modifier 'tee' is not a filter. It WRITES"),
    ("show interfaces GigabitEthernet4 | append flash:x",
     "REFUSED: output modifier 'append' is not a filter. It WRITES"),
    ("show interfaces GigabitEthernet4 | format x",
     "REFUSED: output modifier 'format' is not a filter."),
    ("show version | include a|redirect x",
     "REFUSED: output modifier 'redirect' is not a filter. It WRITES"),
    ("show interfaces GigabitEthernet4\nshow running-config",
     "REFUSED: one command per entry, no line breaks"),
    ("show interfaces GigabitEthernet4\x07", "REFUSED: a control character"),
    ("show interfaces GigabitEthernet4 extra words",
     "'extra' is a word the shape `show interfaces {interface}` does not name"),
    ("show interfaces Gi4; reload",
     "interfaces's argument interface: 'Gi4;' is not an interface name in the platform's "
     "interface-name shape"),
    ("show interfaces GigabitEthernet9",
     "GigabitEthernet9 is not an interface r3's golden holds (it holds GigabitEthernet4 and "
     "Loopback0)"),
    ("show ip route 999.1.1.1",
     "route's argument address: '999.1.1.1' is not one IPv4 address"),
    ("show ip bgp neighbors 192.0.2.99",
     "192.0.2.99 is not a BGP peer r3's intent names (it names 192.0.2.6 and 2001:db8::6)"),
    ("show running-config",
     "the configuration class is off for Branch: it is not built yet "
     "(egress_classes.configuration_allowed), so it is off for every network"),
    ("show running-config interface GigabitEthernet4",
     "the configuration class is off for Branch: it is not built yet"),
])
def test_each_planted_request_is_refused_for_its_own_reason(lab, command, said):
    _ready()
    got = match(command)
    assert got["verdict"] == "refused" and got["command"] == "", got
    assert said in got["reason"], got["reason"]


@pytest.mark.parametrize("command,sent", [
    ("show interfaces GigabitEthernet4 | count up", None),
    ("show interfaces GigabitEthernet4 | include line protocol|errors", None),
    ("show ip ospf neighbor GigabitEthernet4 detail | section Neighbor", None),
    ("show ip route 192.0.2.5", None),
    ("show ipv6 route 2001:db8::5", None),
    ("show ip cef 198.51.100.3", None),
    ("show ipv6 cef 2001:db8:ff::3", None),
    ("ping 192.0.2.4 source GigabitEthernet4 repeat 5 timeout 2", None),
    ("ping ipv6 2001:db8::4 repeat 5 timeout 2", None),
    ("traceroute 192.0.2.6 numeric timeout 2 probe 1 ttl 1 16", None),
    ("traceroute ipv6 2001:db8::6 numeric timeout 2 probe 1 ttl 1 16", None),
    ("show ip bgp neighbors 192.0.2.6", None),
    ("show bgp ipv6 unicast neighbors 2001:db8::6", None),
    ("show ipv6 route 2001:DB8:0::5", "show ipv6 route 2001:db8::5"),
    ("show ospfv3 neighbor", None),
])
def test_each_allowed_form_passes_rendered_exactly(lab, command, sent):
    _ready()
    got = match(command)
    assert got["verdict"] == "allowed", got["reason"]
    assert got["command"] == (sent or command) and got["reason"] == ""
    assert readonly_commands.refusal(got["command"]) == ""


@pytest.mark.parametrize("command,said", [
    ("show interfaces GigabitEthernet4 | inc up",
     "'inc' is not one of the output modifiers, in full: begin, count, exclude, include, "
     "section"),
    ("show interfaces GigabitEthernet4 | include", "| include needs what it filters by"),
    ("show ip route 2001:db8::5", "route's argument address: '2001:db8::5' is not one IPv4 "
     "address"),
    ("show ip route 203.0.113.9", "203.0.113.9 is not an address of Branch"),
    ("ping 192.0.2.4 repeat 100 timeout 2", "'100' is a word the shape"),
    ("ping 192.0.2.4", "`ping 192.0.2.4` stops before `repeat 5 timeout 2`"),
    ("show ip ospf neighbor", "stops before `{interface} detail`"),
    ("show ipv6 ospf neighbor", "r3's platform is cisco_iosxe, and this form is cisco_ios's"),
    ("sh int GigabitEthernet4", "`sh int GigabitEthernet4` is not one of the AI read set's "
     "commands"),
    ("show version", "`show version` is not one of the AI read set's commands"),
])
def test_the_whole_command_is_matched_and_nothing_resembling_it(lab, command, said):
    _ready()
    got = match(command)
    assert got["verdict"] == "refused" and said in got["reason"], got


@pytest.mark.parametrize("command,said", [
    ("show key chain", "it prints a secret's position"),
    ("show snmp community", "it prints a secret's position"),
    ("show users", "it prints a secret's position"),
    ("show startup-config", "configuration in another form"),
    ("show archive", "configuration in another form"),
    ("show access-lists", "an access list's entries are configuration"),
    ("show ip access-lists EDGE-IN", "an access list's entries are configuration"),
    ("show tech-support", "configuration in another form"),
    ("more flash:x", "a file may be configuration"),
    ("dir flash:", "a file may be configuration"),
    ("show logging", "the logs reach the model only from Loki, masked, in the pack"),
])
def test_the_left_out_reads_are_refused_with_their_reasons(lab, command, said):
    _ready()
    got = match(command)
    assert got["verdict"] == "refused" and "left out of the AI read set on purpose" in \
        got["reason"] and said in got["reason"], got


# ── The device scope ──────────────────────────────────────────────────────────────────────────

def test_a_device_the_incident_does_not_name_is_refused(lab):
    _ready()
    got = match("show interfaces GigabitEthernet4", device="r9")
    assert got["verdict"] == "refused"
    assert "r9 is not a device the incident names in Branch (it names r3 and s1)" in \
        got["reason"]


def test_a_device_with_no_read_only_account_is_refused_by_name(lab):
    """Only the switches' profile carries one: r3, a router whose profiles carry the deploy
    login, is refused naming every profile looked under; s1 is allowed."""
    _state_on()
    _account("role:switch")
    got = match("show interfaces GigabitEthernet4")
    assert got["verdict"] == "refused"
    assert got["reason"] == ("interfaces's argument device: no read-only account for r3: "
                             f"{R3_NONE}")
    assert match("show interfaces GigabitEthernet0/1", device="s1")["verdict"] == "allowed"


def test_the_scopes_account_is_the_reads_engines_resolver_per_inventory_device(lab):
    """None set: no device has one, whatever deploy login its profiles carry. Set on the
    switches' profile: s1 has one, r3 not; a host the inventory does not hold has none."""
    got = R.read_accounts(NETWORK, ["r3", "s1", "r9"])
    assert got["r3"] == (False, R3_NONE)
    assert got["s1"][0] is False and "(platform:cisco-ios, role:switch, site:lab, default)" \
        in got["s1"][1]
    assert got["r9"] == (False, "r9 is not a device of Branch")
    _account("role:switch")
    got = R.read_accounts(NETWORK, ["r3", "s1"])
    assert got == {"r3": (False, R3_NONE), "s1": (True, "")}
    devices = scope()["devices"]
    assert devices["s1"]["read_account"] is True and devices["r3"]["read_account"] is False
    assert RO_PW not in repr(scope())


def test_every_device_state_read_is_refused_naming_the_class_while_it_is_off(lab):
    _account()
    got = match("show interfaces GigabitEthernet4")
    assert got["verdict"] == "refused"
    assert got["reason"] == ("the device state class is off for Branch: off by default, and "
                             "no admin has turned it on (ai_device_state_class is false)")
    _state_on("Default")
    assert match("show interfaces GigabitEthernet4")["verdict"] == "refused", \
        "another network's switch turns no other on"
    _state_on()
    assert match("show interfaces GigabitEthernet4")["verdict"] == "allowed"
    egress_classes.turn_off_device_state(NETWORK, actor="op@example.com",
                                         actor_verified="access", person=True)
    got = match("show interfaces GigabitEthernet4")
    assert got["verdict"] == "refused" and got["reason"].startswith(
        "the device state class is off for Branch"), got


def test_the_interface_is_compared_in_its_long_form(lab):
    _ready()
    got = match("show interfaces Gi4")
    assert got["verdict"] == "allowed" and got["command"] == "show interfaces Gi4"


def test_the_loops_form_is_judged_by_the_same_family(lab):
    _ready()
    asks = [{"op": "interfaces", "args": {"device": "r3", "interface": "GigabitEthernet4"},
             "why": "is it up", "hypothesis": "the link is down"},
            {"op": "ping6_from", "args": {"device": "s1", "address": "2001:db8::5",
                                          "interface": "GigabitEthernet0/1"},
             "why": "reach", "hypothesis": "the far end answers"},
            {"op": "route", "args": {"device": "r3", "address": "192.0.2.5", "extra": "x"},
             "why": "route", "hypothesis": "no route"}]
    got = RL.check(R.AI_READS, asks, network=NETWORK, scope=scope())
    assert [g["verdict"] for g in got] == ["allowed", "allowed", "refused"]
    assert got[0]["requests"] == ["show interfaces GigabitEthernet4"]
    assert got[1]["requests"] == ["ping ipv6 2001:db8::5 source GigabitEthernet0/1 repeat 5 "
                                  "timeout 2"]
    assert "route takes no argument 'extra'" in got[2]["reason"]


# ── The declaration ───────────────────────────────────────────────────────────────────────────

def test_the_family_is_declared_over_the_cli_rule_with_its_verbs_and_bounds():
    assert R.AI_READS.transport == "cli" and R.AI_READS.egress_class == "device_state"
    assert len(R.AI_READS.operations) == len(R.SHAPES) == 30      # the floor: 19.5's set
    for op in R.AI_READS.operations:
        (send,) = op.sends
        assert send.split()[0] in RL.CLI_VERBS, send
        assert "|" not in send, send
        assert op.args["device"].against is R._device_named
        words = send.split()
        if words[0] == "ping":
            assert words[-4:] == ["repeat", "5", "timeout", "2"], send
        if words[0] == "traceroute":
            assert words[-8:] == "numeric timeout 2 probe 1 ttl 1 16".split(), send
    config = sorted(o.name for o in R.AI_READS.operations if o.egress_class)
    assert config == ["running_config", "running_config_interface"]
    assert {R.AI_READS.class_of(o) for o in R.AI_READS.operations} == {
        "device_state", "configuration"}


def test_each_ipv4_shape_has_its_ipv6_twin():
    names = {o.name for o in R.AI_READS.operations}
    for four, six in (("route", "route6"), ("cef", "cef6"), ("arp", "nd"), ("ping", "ping6"),
                      ("ping_from", "ping6_from"), ("traceroute", "traceroute6"),
                      ("bgp_neighbor", "bgp_neighbor6"), ("bgp_summary", "bgp_summary6"),
                      ("ip_interface", "ipv6_interface"), ("ospf_interface",
                                                           "ospfv3_interface")):
        assert {four, six} <= names, (four, six)


# ── The executor ──────────────────────────────────────────────────────────────────────────────

def test_a_device_without_a_read_only_account_is_refused_by_the_engine_with_no_session(lab):
    """The executor holds no session of its own: the reads engine refuses r3 by name before
    any session opens, read-only or deploy."""
    _account("role:switch")
    with pytest.raises(RuntimeError) as e:
        R.run("interfaces", {"device": "r3"}, ["show interfaces GigabitEthernet4"], scope())
    assert str(e.value) == f"no read-only account for r3: {R3_NONE}. Nothing was sent"
    assert lab.signed == [] and lab.deploy == []


def test_the_executor_signs_in_as_the_read_only_account_through_the_engine(lab):
    from modules.nsot import reads
    _account()
    got = R.run("interfaces", {"device": "r3"}, ["show interfaces GigabitEthernet4"], scope())
    assert got == "show interfaces GigabitEthernet4: answered"
    assert lab.signed == [{"host": "r3", "username": "mercury-ro", "password": RO_PW}]
    assert lab.deploy == [], "never the deploy account's session"
    (record,) = reads.runs(NETWORK)["runs"]
    assert record["by"] == "ai_analysis" == R.KIND
    assert record["actor"] == ("the AI analysis of incident inc-1, turned on by "
                               "admin@example.invalid")
    assert record["results"]["r3"]["signed_in_as"] == {
        "username": "mercury-ro", "source": "read-account:profile:default"}
    assert RO_PW not in repr(record)
    assert reads.EXTRAS["ai_analysis"] == () and "ai_analysis" in reads.READ_ACCOUNT_KINDS
    assert reads.refusal(["terminal length 0"], 1, by="ai_analysis")


def test_a_held_device_is_skipped_by_name(lab):
    from modules.nsot import device_ops
    _account()
    held, done = threading.Event(), threading.Event()

    def deploy():
        with device_ops.hold(NETWORK, "r3", "deploy", "admin@example.invalid"):
            held.set()
            done.wait(30)

    other = threading.Thread(target=deploy)
    other.start()
    try:
        assert held.wait(30)
        with pytest.raises(RuntimeError) as e:
            R.run("interfaces", {"device": "r3"}, ["show interfaces Gi4"], scope())
    finally:
        done.set()
        other.join(30)
    assert str(e.value).startswith("skipped: r3 is being ") and \
        "by admin@example.invalid" in str(e.value), str(e.value)
    assert lab.signed == [] and lab.deploy == []


# ── The scope ─────────────────────────────────────────────────────────────────────────────────

def test_the_scope_is_read_from_intent_and_the_golden_ipv4_beside_ipv6(lab):
    got = scope()
    r3 = got["devices"]["r3"]
    assert r3["interfaces"] == ["GigabitEthernet4", "Loopback0"]
    assert r3["peers"] == ["192.0.2.6", "2001:db8::6"]
    assert r3["dialect"] == "cisco_iosxe" and got["devices"]["s1"]["dialect"] == "cisco_ios"
    assert "192.0.2.4/30" in got["prefixes"] and "2001:db8::/64" in got["prefixes"]
    assert {"192.0.2.5", "2001:db8::5", "198.51.100.3"} <= set(got["addresses"])
    assert "read_session" not in got, "no session of its own: the engine's is the one way in"


def test_an_unknown_platform_reads_as_no_dialect_never_as_ios(lab):
    intents = dict(INTENTS, r3=dict(INTENTS["r3"], platform="junos"))
    assert scope(intents=intents)["devices"]["r3"]["dialect"] == ""


def test_golden_interfaces_are_the_interface_lines_as_written():
    assert R.golden_interfaces(" interface x\ninterface Gi1\ninterface Gi1\n") == ["Gi1"]


# ── The diagnosis runbooks' pipe rule, held to the matcher (19.5) ─────────────────────────────

#: The runbook reads the AI set does not hold, each with why. 19.5 says the runbooks never use
#: a left-out read; these two are the exceptions it did not foresee (H15's ACL counters, H14's
#: don't-fragment probe), named here so a third cannot arrive unseen.
RUNBOOK_ONLY = {
    "acl_counters": "an access list's entries are configuration",
    "df_ping": "'size' is a word the shape `ping {address} repeat 5 timeout 2` does not name",
}


def test_every_runbook_command_matches_the_ai_read_set_but_the_named_exceptions(lab):
    from tests.test_heal_diagnose import every_command
    _ready()
    devices = {"cisco_iosxe": "xe", "cisco_ios": "ios"}
    hv = {"interfaces": [{"name": "GigabitEthernet0/1", "ipv4": "192.0.2.2 255.255.255.0",
                          "ipv6": ["2001:db8::2/64"]}],
          "routing": {"bgp": {"neighbors": ["neighbor 192.0.2.1 remote-as 65002",
                                            "neighbor 2001:db8::1 remote-as 65002"]}}}
    intents = {"xe": dict(hv, platform="cisco_iosxe"), "ios": dict(hv, platform="cisco_ios")}
    golden = "interface GigabitEthernet0/1\ninterface Loopback0\n"
    sc = R.scope_for(NETWORK, ["xe", "ios"], intents=intents,
                     goldens={"xe": golden, "ios": golden})
    matched, excepted = 0, set()
    for kind, dialect, command in every_command():
        got = R.match(command, devices[dialect], sc, network=NETWORK)
        if kind in RUNBOOK_ONLY:
            assert got["verdict"] == "refused" and RUNBOOK_ONLY[kind] in got["reason"], got
            excepted.add(kind)
            continue
        assert got["verdict"] == "allowed", (kind, command, got["reason"])
        assert got["command"] == command
        matched += 1
    assert excepted == set(RUNBOOK_ONLY)
    assert matched == 2 * 27 - 2 * len(RUNBOOK_ONLY)   # the floor: every other template
