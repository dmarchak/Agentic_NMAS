"""The AI reads as a senior engineer using Mercury (the operator's change of approach, 2026-11-14;
C3661, C3663; `modules/ai/router_reads.py` `COMMAND_OPS` and `command_refusal`,
`modules/nsot/reads.py` `ai_reads_as`, `modules/ai/fixit_reads.py` `FAMILY`,
`modules/ai/missing.py`), on tests/test_ai_router_reads.py's world: three networks' settings, a
credential store and an inventory in this test's own folder, the reads engine's session seams
faked (`connection.with_temp_connection`, Show commands' own, and
`connection.with_plain_connection`, the read-only account's); no device, no provider.

- **Whom the reads sign in as** is one answer (`reads.ai_reads_as`): by default Mercury's
  account, exactly as Show commands signs in (the inventory's login, its session path), with no
  read-only account needed at the check; under the read-only choice the device's read-only
  account, refused by name without it; a hand-edited value reads as the read-only account. Each
  read records whom it signed in as.
- **The setting** is offered on Settings › AI only while every device holds the read-only
  account with a passed probe, and its Save refuses otherwise, naming the devices.
- **A read is any command Mercury's allowlist holds whole**, each address of the network and
  each interface one the golden holds (IPv4 beside IPv6); a configuration form is
  `show_config`'s alone, under the configuration class; what Mercury leaves out is refused with
  its reason; `show telemetry internal connection` is on the allowlist.
- **Mercury's own reads** (intent, golden, neighbours, history, logs, metrics) are of a device in
  scope, the golden under the configuration class.
- **A missing capability** (a read Mercury lacks, a gap) is recorded for review and listed on
  History; a read refused for its scope is not one.
"""
import pytest

from modules import credentials, readonly_commands
from modules.ai import read_loop as RL
from modules.ai import router_reads as R
from tests.test_ai_router_reads import (  # noqa: F401 (the fixture)
    GOLDENS, INTENTS, NETWORK, RO_PW, _account, _reads_as_read_only, _state_on, lab, scope)

DEPLOY_PW = "Deploy-Pass-5531"


def ask(op, device="r3", **args):
    return {"op": op, "args": dict({"device": device}, **args), "why": "to see",
            "hypothesis": "it is down"}


def judged(*requests, **over):
    from modules.ai import fixit_reads as FR
    return RL.check(FR.FAMILY, list(requests), network=NETWORK, scope=scope(**over))


# ── Whom the reads sign in as (C3661) ─────────────────────────────────────────────────────────

def test_by_default_the_reads_sign_in_as_mercurys_account_as_show_commands_does(lab):
    """No read-only account anywhere: r3 is allowed at the check, and the engine signs it in
    through Show commands' own session (`with_temp_connection`, the inventory's login), never
    the read-only account's, recording whom it signed in as."""
    from modules.nsot import reads

    assert reads.ai_reads_as() == "mercury"
    sc = scope()
    assert sc["reads_as"] == "mercury" and sc["devices"]["r3"]["read_account"] is False
    got = R.match("show interfaces GigabitEthernet4", "r3", sc, network=NETWORK)
    assert got["verdict"] == "refused" and "device state class is off" in got["reason"]
    _state_on()
    assert R.match("show interfaces GigabitEthernet4", "r3", scope(),
                   network=NETWORK)["verdict"] == "allowed"
    answer = R.run("show", {"device": "r3", "words": "interfaces GigabitEthernet4"},
                   ["show interfaces GigabitEthernet4"], scope())
    assert lab.deploy == ["r3"] and lab.signed == [], "Show commands' path, never the plain one"
    # The inventory row names no login here, so the name is empty and its source the inventory.
    assert answer.signed_in_as == {"username": "", "source": "mercury-account:the inventory"}
    (record,) = reads.runs(NETWORK)["runs"]
    assert record["by"] == "ai_analysis" and record["signs_in_as"] == "mercury"
    assert record["results"]["r3"]["signed_in_as"]["source"].startswith("mercury-account:")
    assert reads.actor_words(record).endswith("as Mercury's account")
    assert DEPLOY_PW not in repr(record)


def test_under_the_read_only_choice_the_reads_sign_in_as_the_read_only_account(lab):
    from modules.nsot import reads

    _reads_as_read_only()
    _account()
    assert reads.ai_reads_as() == "read_only" and scope()["reads_as"] == "read_only"
    R.run("show", {"device": "r3", "words": "interfaces GigabitEthernet4"},
          ["show interfaces GigabitEthernet4"], scope())
    assert lab.signed == [{"host": "r3", "username": "mercury-ro", "password": RO_PW}]
    assert lab.deploy == []
    (record,) = reads.runs(NETWORK)["runs"]
    assert record["signs_in_as"] == "read_only"
    assert reads.actor_words(record).endswith("as the read-only account")


def test_a_hand_edited_value_reads_as_the_read_only_account_the_narrower(lab, monkeypatch):
    from modules.nsot import reads

    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: "anything" if key == reads.AI_READS_AS_KEY
                        else default)
    assert reads.ai_reads_as() == "read_only"

    def broken(key, default=None):
        raise OSError("unreadable")

    monkeypatch.setattr("modules.settings_schema.get_setting", broken)
    assert reads.ai_reads_as() == "read_only"


def test_a_scope_built_without_the_answer_asks_the_read_only_account():
    """The closed side: a scope that names no `reads_as` (a hand-built one, a caller from before
    C3661) is read as the read-only choice, so a device without the account is refused."""
    sc = {"network": NETWORK, "devices": {"r3": {"read_account": False,
                                                 "read_account_why": "none set"}}}
    assert R._device_named("r3", sc) == "no read-only account for r3: none set"
    assert R._device_named("r3", dict(sc, reads_as="mercury")) == ""
    assert R._device_named("r3", dict(sc, reads_as="read_only")).startswith(
        "no read-only account for r3")


def test_the_telemetry_connections_read_is_ios_xe_s_alone(lab):
    """`show telemetry internal connection` is IOS-XE 17's form: on IOS (s1) it is another
    platform's form, refused by name and never asked (the review of 2026-11-14)."""
    _state_on()
    (xe,) = judged(ask("show", words="telemetry internal connection"))
    assert xe["verdict"] == "allowed"
    (ios,) = judged(ask("show", device="s1", words="telemetry internal connection"))
    assert ios["verdict"] == "refused" and ios["requests"] == []
    assert "s1's platform is cisco_ios, and this form is cisco_iosxe's" in ios["reason"]


def test_a_record_from_before_names_the_read_only_account():
    from modules.nsot import reads
    assert reads.actor_words({"by": "ai_analysis", "actor": "a"}).endswith(
        "as the read-only account")


def test_a_persons_read_is_unchanged_by_the_setting(lab):
    from modules.nsot import reads

    _reads_as_read_only()
    _account()
    rec = reads.run(NETWORK, ["r3"], ["show version"], "admin@example.invalid", by="person")
    assert lab.deploy == ["r3"] and lab.signed == []
    assert "signed_in_as" not in rec["results"]["r3"] and "signs_in_as" not in rec


# ── The setting on Settings › AI (C3661) ──────────────────────────────────────────────────────

def _coverage(*rows, errors=None):
    return {"devices": [dict({"network": NETWORK}, **r) for r in rows],
            "networks": {"n": {"name": NETWORK, "error": errors or ""}}}


def test_the_choice_is_refused_naming_each_device_that_does_not_hold_it_and_pass():
    from modules.nsot import read_account as RA

    value = _coverage({"device": "r3", "state": "holds", "probe": {"result": "PASS"}},
                      {"device": "r7", "state": "holds", "probe": {"result": "FAIL"}},
                      {"device": "s1", "state": "not_yet", "probe": None},
                      {"device": "r6", "state": "holds", "probe": None})
    why = RA.reads_as_refusal(value)
    assert why.startswith("the read-only account is offered only when every device holds it "
                          "and its probe passed, and 3 do not: ")
    assert f"{NETWORK} r7: its newest probe was FAIL" in why
    assert f"{NETWORK} s1: not yet" in why and f"{NETWORK} r6: its newest probe has not run" \
        in why and "r3" not in why
    assert RA.reads_as_refusal(_coverage(
        {"device": "r3", "state": "holds", "probe": {"result": "PASS"}})) == ""
    assert "could not be read" in RA.reads_as_refusal(_coverage(
        {"device": "r3", "state": "holds", "probe": {"result": "PASS"}}, errors="git failed"))
    assert "names none" in RA.reads_as_refusal({"devices": [], "networks": {}})


def test_the_card_offers_it_only_when_ready_and_its_save_refuses_otherwise(lab, monkeypatch):
    from modules import installation_settings as I
    from modules.nsot import read_account as RA
    from modules.settings_schema import DEFAULTS, get_setting

    assert DEFAULTS["ai_device_reads_as"] == "mercury"
    not_ready = _coverage({"device": "r7", "state": "holds", "probe": {"result": "FAIL"}})
    monkeypatch.setattr(RA, "held", lambda: {"value": not_ready, "at": "", "why": ""})
    monkeypatch.setattr(RA, "read_coverage", lambda previous=None: not_ready)
    card = I.card("fixit")
    (f,) = [f for f in card["fields"] if f["key"] == "ai_device_reads_as"]
    assert f["choices"] == ("mercury",)
    assert "Not offered now: Branch r7: its newest probe was FAIL" in f["note"]
    loaded = card["loaded"]
    form = {k: loaded[k] for k in loaded}
    form["ai_device_reads_as"] = "read_only"
    with pytest.raises(I.Refused) as e:
        I.save_card("fixit", form, "op@example.com", "access", loaded=loaded)
    assert str(e.value).startswith("AI device reads sign in as stays Mercury's account: the "
                                   "read-only account is offered only when every device holds")
    assert "Branch r7: its newest probe was FAIL" in str(e.value)
    assert get_setting("ai_device_reads_as") == "mercury"
    ready = _coverage({"device": "r7", "state": "holds", "probe": {"result": "PASS"}})
    monkeypatch.setattr(RA, "held", lambda: {"value": ready, "at": "", "why": ""})
    monkeypatch.setattr(RA, "read_coverage", lambda previous=None: ready)
    (f,) = [f for f in I.card("fixit")["fields"] if f["key"] == "ai_device_reads_as"]
    assert f["choices"] == ("mercury", "read_only") and "Not offered" not in f["note"]
    got = I.save_card("fixit", form, "op@example.com", "access", loaded=loaded)
    assert got["ok"] and got["written"] == ["ai_device_reads_as"]
    assert get_setting("ai_device_reads_as") == "read_only"
    assert got["change_words"] == ["AI device reads sign in as Mercury's account → The "
                                   "read-only account (hardened)"]


# ── Any read Mercury's allowlist holds (C3661) ────────────────────────────────────────────────

def test_the_allowlist_holds_the_telemetry_connections_read():
    assert readonly_commands.refusal("show telemetry internal connection") == ""


@pytest.mark.parametrize("request_,sent", [
    (ask("show", words="interfaces GigabitEthernet4"), "show interfaces GigabitEthernet4"),
    (ask("show", words="interfaces Gi4"), "show interfaces Gi4"),
    (ask("show", words="telemetry internal connection"), "show telemetry internal connection"),
    (ask("show", words="ip route 192.0.2.6"), "show ip route 192.0.2.6"),
    (ask("show", words="ipv6 route 2001:db8::6"), "show ipv6 route 2001:db8::6"),
    (ask("show", words="ip route 192.0.2.4 255.255.255.252"),
     "show ip route 192.0.2.4 255.255.255.252"),
    (ask("show", words="ip bgp summary | include 192.0.2"),
     "show ip bgp summary | include 192.0.2"),
    (ask("show", words="ip ospf neighbor"), "show ip ospf neighbor"),
    (ask("ping", words="192.0.2.6"), "ping 192.0.2.6"),
    (ask("ping", words="ipv6 2001:db8::6"), "ping ipv6 2001:db8::6"),
    (ask("traceroute", words="2001:db8::6 numeric timeout 2 probe 1 ttl 1 16"),
     "traceroute 2001:db8::6 numeric timeout 2 probe 1 ttl 1 16"),
    (ask("traceroute", words="ipv6 2001:db8::6 numeric timeout 2 probe 1 ttl 1 16"),
     "traceroute ipv6 2001:db8::6 numeric timeout 2 probe 1 ttl 1 16"),
    # The families' own forms (the review's decision, 2026-11-14): abbreviated words, a unique
    # prefix of an interface's type, the brief forms of first-hop redundancy.
    (ask("show", words="ip int br"), "show ip int br"),
    (ask("show", words="interfaces Gig4"), "show interfaces Gig4"),
    (ask("show", words="standby brief"), "show standby brief"),
    (ask("show", words="vrrp brief"), "show vrrp brief"),
    (ask("show", words="ip cef 192.0.2.6 detail"), "show ip cef 192.0.2.6 detail"),
    (ask("show", words="bgp ipv6 unicast neighbors 2001:db8::6"),
     "show bgp ipv6 unicast neighbors 2001:db8::6"),
    (ask("show", words="version"), "show version"),
    (ask("show", words="processes cpu sorted"), "show processes cpu sorted"),
    (ask("show", words="ntp associations"), "show ntp associations"),
    (ask("ping", words="192.0.2.6 source GigabitEthernet4"),
     "ping 192.0.2.6 source GigabitEthernet4"),
])
def test_a_read_the_allowlist_holds_whole_runs_as_asked(lab, request_, sent):
    _state_on()
    (got,) = judged(request_)
    assert got["verdict"] == "allowed", got
    assert got["requests"] == [sent]


@pytest.mark.parametrize("request_,said", [
    (ask("show", words="running-config | redirect flash:x"),
     "Mercury's read-only allowlist refuses"),
    (ask("show", words="version\nreload"), "line break or control character"),
    (ask("show", words="clock ; reload"), "a ';' is never part of a read"),
    (ask("show", words="running-config"), "prints the device's configuration: it is "
                                          "show_config's"),
    (ask("show", words="run"), "prints the device's configuration: it is show_config's"),
    (ask("show", words="snmp community"), "left out of the AI's reads on purpose: it prints a "
                                          "secret's position"),
    (ask("show", words="logging"), "left out of the AI's reads on purpose"),
    (ask("show", words="tech-support"), "left out of the AI's reads on purpose"),
    (ask("show_config", words="running-config"), "the configuration class is off"),
    (ask("show", words="ip route 203.0.113.9"), "203.0.113.9 is not an address of Branch"),
    (ask("show", words="ipv6 route 2001:db8:9::9"), "2001:db8:9::9 is not an address of Branch"),
    (ask("show", words="ip route 203.0.113.0/24"), "203.0.113.0/24 is not a prefix of Branch"),
    (ask("show", words="interfaces GigabitEthernet9"), "GigabitEthernet9 is not an interface "
                                                       "r3's golden holds"),
    (ask("show", words="interfaces GigabitEthernet 4"), "write the interface as one word, "
                                                        "`GigabitEthernet4`"),
    (ask("show", words="spanning-tree"), "this form is a switch's"),
    (ask("show", words="telemetry ietf subscription 999 receiver"),
     "subscription 999 is not one r3's intent declares"),
    (ask("ping", words="edge1"), "a ping's target is one address of the network"),
    (ask("traceroute", words="192.0.2.6"), "its worst case is 270 s, over the 40 s an AI "
                                           "traceroute may hold the device"),
    (ask("ping", words="192.0.2.6 repeat 10 timeout 5"), "its worst case is 50 s, over the 40 s "
                                                         "an AI ping"),
    (ask("ping", words="192.0.2.6 repeat 100 timeout 10"), "past the 300 s a read may hold"),
    (ask("show", device="r9", words="version"), "r9 is not a device the incident names"),
    (ask("show", words="version", interface="Gi4"), "show takes no argument 'interface'"),
    (ask("configure", words="terminal"), "is not an operation of the fixit read family"),
    # BLOCKER 1 (Tier 1's review, 2026-11-14): with Mercury's account a show can print a
    # secret's position no left-out list named; the AI's show is a positive list of families.
    (ask("show", words="crypto isakmp key"), "left out of the AI's reads on purpose: it prints "
                                             "keys"),
    (ask("show", words="vtp password"), "left out of the AI's reads on purpose"),
    (ask("show", words="standby"), "is not one of the AI's read families' forms (show "
                                   "standby takes: `show standby brief`)"),
    (ask("show", words="standby GigabitEthernet4"), "is not one of the AI's read families' forms"),
    (ask("show", words="vrrp"), "is not one of the AI's read families' forms"),
    (ask("show", words="glbp"), "is not one of the AI's read families:"),
    (ask("show", words="sdwan running-config"), "is not one of the AI's read families:"),
    # SHOULD 4: configuration fragments under the device state class.
    (ask("show", words="policy-map"), "is not one of the AI's read families:"),
    (ask("show", words="parser macro"), "is not one of the AI's read families:"),
    (ask("show", words="alias"), "is not one of the AI's read families:"),
    (ask("show", words="event manager policy registered detail"),
     "is not one of the AI's read families:"),
    # SHOULD 3: an interface spelled otherwise resolves by its type to one the golden holds.
    (ask("show", words="interfaces Gig9"), "Gig9 is not an interface r3's golden holds"),
    (ask("show", words="interfaces G9"), "G9 is not an interface r3's golden holds"),
    (ask("show", words="interfaces Gigabit9"), "Gigabit9 is not an interface r3's golden holds"),
    (ask("show", words="interfaces Gig 9"), "write the interface as one word, `Gig9`"),
    (ask("show", words="interfaces Loop9"), "Loop9 is not an interface r3's golden holds"),
    (ask("show", words="interfaces Null0"), "'Null0' is not an interface Mercury can name"),
    (ask("show", words="interfaces Dialer1"), "'Dialer1' is not an interface Mercury can name"),
    (ask("show", words="interfaces nve1"), "'nve1' is not an interface Mercury can name"),
    (ask("show", words="interfaces T1"), "'T1' is not an interface Mercury can name"),
    (ask("ping", words="192.0.2.6 source Gig9"), "its source: Gig9 is not an interface r3's"),
    (ask("ping", words="192.0.2.6 source 203.0.113.9"), "its source: 203.0.113.9 is not an "
                                                         "address of Branch"),
    # NOTE 5: a netmask-shaped address is an address, a mask only right after one.
    (ask("show", words="ip route 128.0.0.0"), "128.0.0.0 is not an address of Branch"),
    (ask("show", words="ip route 255.255.255.0"), "255.255.255.0 is not an address of Branch"),
    (ask("show", words="ip route 192.0.2.4 255.0.255.0"), "'255.0.255.0' is not an IPv4 "
                                                          "netmask"),
])
def test_each_planted_read_is_refused_for_its_own_reason(lab, request_, said):
    _state_on()
    (got,) = judged(request_)
    assert got["verdict"] == "refused" and got["requests"] == [], got
    assert said in got["reason"], got["reason"]


def test_a_switchs_vlan_forms_are_read_of_a_known_switch(lab):
    """NOTE 8 (Tier 1's review): `show spanning-tree vlan 10` and `show mac address-table vlan
    10` are allowed of a device known to be a switch; spanning tree stays refused elsewhere."""
    sc = scope(capabilities={"s1": (True, "declared (a test's own words)"),
                             "r3": (False, "declared")})
    assert R.command_refusal("show spanning-tree vlan 10", "s1", sc) == ""
    assert R.command_refusal("show mac address-table vlan 10", "s1", sc) == ""
    assert "is not a VLAN" in R.command_refusal("show spanning-tree vlan 5000", "s1", sc)
    assert "this form is a switch's" in R.command_refusal("show spanning-tree vlan 10", "r3", sc)


def test_every_read_set_shape_and_runbook_command_is_one_of_the_families(lab):
    """The families' floor: every command the AI read set's shapes send (the device state
    ones) and every command the heal runbooks render, on both dialects, is a read of one of
    the AI's families, but those named here with why."""
    from tests.test_heal_diagnose import every_command

    hv = {"interfaces": [{"name": "GigabitEthernet0/1", "ipv4": "192.0.2.2 255.255.255.0",
                          "ipv6": ["2001:db8::2/64"]}],
          "telemetry": [{"subscription": "101", "settings": []}],
          "routing": {"bgp": {"neighbors": ["neighbor 192.0.2.1 remote-as 65002",
                                            "neighbor 2001:db8::1 remote-as 65002"]}}}
    intents = {"xe": dict(hv, platform="cisco_iosxe"), "ios": dict(hv, platform="cisco_ios")}
    golden = "interface GigabitEthernet0/1\ninterface Loopback0\n"
    sc = R.scope_for(NETWORK, ["xe", "ios"], intents=intents,
                     goldens={"xe": golden, "ios": golden}, ping_traceroute=True,
                     capabilities={h: (True, "measured (a test's own words)")
                                   for h in ("xe", "ios")})
    named = {
        # A configuration form: show_config's, under the configuration class.
        "acl_counters": "prints the device's configuration: it is show_config's",
        # Each dialect's own form, refused on the other: another platform's.
        "telemetry_connection": "this form is cisco_iosxe's",
    }
    devices = {"cisco_iosxe": "xe", "cisco_ios": "ios"}
    seen, refused = 0, {}
    for kind, dialect, command in every_command():
        why = R.command_refusal(command, devices[dialect], sc)
        seen += 1
        if why:
            refused.setdefault(kind, set()).add(why)
    unexplained = {k: w for k, w in refused.items()
                   if k not in named or not all(named[k] in x for x in w)}
    assert unexplained == {}, unexplained
    assert seen >= 70, seen
    args = {"interface": "GigabitEthernet0/1", "address": "192.0.2.1", "peer": "192.0.2.1",
            "mac": "aabb.cc00.0100", "subscription": "101"}
    shapes = 0
    for name, send, _a, _against, cls, _w in R.SHAPES:
        if cls == "configuration":
            continue
        values = dict(args)
        if "6" in name or "ipv6" in send:
            values.update(address="2001:db8::1", peer="2001:db8::1")
        command = send.format(**values)
        host = "ios" if name in ("ipv6_ospf_neighbor",) else "xe"
        assert R.command_refusal(command, host, sc) == "", (name, command)
        shapes += 1
    assert shapes >= 30, shapes


def test_the_egress_mask_withholds_the_planted_secret_lines():
    """Defence in depth under the families (Tier 1's review): the planted outputs' secret
    positions are masked on the way to the model (`redact.redact_egress`)."""
    from modules import redact

    planted = {
        "isakmp": ("Keyring      Hostname/Address                            Preshared Key\n"
                   "default      192.0.2.9                                   Isakmp-Key-7731\n"
                   "default      2001:db8::9                                 Isakmp-Key-7732"),
        "vtp": "VTP Password: Vtp-Secret-5521",
        "hsrp": "  Authentication text, string \"Hsrp-Auth-4410\"",
        "hsrp md5": "  Authentication MD5, key-string \"Hsrp-Md5-4411\"",
        "vrrp": "  Authentication text \"Vrrp-Auth-4412\"",
        "glbp": "  Authentication text, string \"Glbp-Auth-4413\"",
        "pair": "Username: admin    Password: Pair-Pass-6610",
        "preshared": "Preshared key = Psk-Value-9901",
    }
    for label, text in planted.items():
        out = redact.redact_egress(text)
        for secret in ("Isakmp-Key-7731", "Isakmp-Key-7732", "Vtp-Secret-5521", "Hsrp-Auth-4410",
                       "Hsrp-Md5-4411", "Vrrp-Auth-4412", "Glbp-Auth-4413", "Pair-Pass-6610",
                       "Psk-Value-9901"):
            assert secret not in out, (label, out)
    kept = "Internet  192.0.2.6   5   aabb.cc00.0100  ARPA   GigabitEthernet4"
    assert redact.redact_egress(kept) == kept, "an ARP row is no key row"
    assert "admin" in redact.redact_egress(planted["pair"]), "the username stays"


def test_show_config_takes_only_a_configuration_form(lab):
    """The configuration class is off on every network (C1720), so this is the operation's own
    comparison, asked whole: a configuration form is show_config's alone, both ways."""
    sc = scope()
    assert R.command_refusal("show running-config", "r3", sc, config=True) == ""
    assert R.command_refusal("show startup-config", "r3", sc, config=True) == ""
    assert "is not a configuration form" in R.command_refusal("show version", "r3", sc,
                                                              config=True)
    assert "it is show_config's" in R.command_refusal("sh run", "r3", sc)
    assert R.command_refusal("show version", "r3", sc) == ""


def test_a_pings_options_need_the_choice_only_under_the_read_only_account(lab):
    _state_on()
    (got,) = judged(ask("ping", words="192.0.2.6 repeat 5"))
    assert got["verdict"] == "allowed", "Mercury's account holds ping's options"
    _reads_as_read_only()
    _account()
    (got,) = judged(ask("ping", words="192.0.2.6 repeat 5"))
    assert got["verdict"] == "refused" and "installation choice" in got["reason"]
    (got,) = judged(ask("ping", words="192.0.2.6 repeat 5"), ping_traceroute=True)
    assert got["verdict"] == "allowed"


def test_the_family_is_the_allowlists_verbs_and_mercurys_own_reads():
    from modules.ai import fixit_reads as FR

    names = [op.name for op in FR.FAMILY.operations]
    assert names == ["show", "show_config", "ping", "traceroute", "intent", "golden",
                     "neighbours", "history", "logs", "metrics", "collector_sessions",
                     "stream_series"]
    assert {FR.FAMILY.transport_of(FR.FAMILY.operation(n)) for n in names[:4]} == {"cli"}
    assert FR.FAMILY.class_of(FR.FAMILY.operation("show_config")) == "configuration"
    assert FR.FAMILY.class_of(FR.FAMILY.operation("golden")) == "configuration"
    assert FR.FAMILY.class_of(FR.FAMILY.operation("show")) == "device_state"
    # No fixed shape is AI troubleshooting's any more; the shapes stay the probe's.
    assert not {"interfaces", "telemetry_brief", "telemetry_connection"} & set(names)
    assert "telemetry_connection" in {op.name for op in FR.SHAPES_FAMILY.operations}
    assert "telemetry_connection" not in {op.name for op in FR.FAMILY_V4.operations}
    assert FR.FAMILY.limit == RL.MAX_READS == 3, "the read budget: three a pass"


def test_mercurys_own_reads_are_of_a_device_in_scope_the_golden_under_its_class(lab):
    _state_on()
    got = judged(ask("intent"), ask("neighbours", device="s1"),
                 ask("history", device="r9")) + judged(ask("golden"))
    assert [g["verdict"] for g in got] == ["allowed", "allowed", "refused", "refused"]
    assert got[0]["requests"] == ["local intent r3"]
    assert "r9 is not a device in this investigation's scope" in got[2]["reason"]
    assert "the configuration class is off" in got[3]["reason"]


def test_mercurys_own_reads_run_through_the_evidence_packs_builders(lab, monkeypatch):
    from modules import evidence_pack as EP
    from modules.ai import fixit_reads as FR

    seen = []
    monkeypatch.setattr(EP, "history_section",
                        lambda ref, host: seen.append(("history", ref.name, host)) or {"ok": 1})
    monkeypatch.setattr(EP, "logs_section",
                        lambda ref, host, onset, now: seen.append(("logs", host)) or {"ok": 2})
    sc = scope()
    assert FR.run("history", {"device": "r3"}, ["local history r3"], sc) == {"ok": 1}
    assert FR.run("logs", {"device": "s1"}, ["local logs s1"], sc) == {"ok": 2}
    assert seen == [("history", NETWORK, "r3"), ("logs", "s1")]
    got = FR.run("golden", {"device": "r3"}, ["local golden r3"],
                 dict(sc, network=NETWORK))
    assert got["device"] == "r3"


# ── A missing capability (C3663) ──────────────────────────────────────────────────────────────

def test_a_read_mercury_lacks_and_a_gap_are_recorded_for_review_and_listed(lab):
    from modules import history_sources as HS
    from modules.ai import missing

    _state_on()
    records = judged(ask("show", words="running-config | redirect flash:x"),
                     ask("show", words="ip route 203.0.113.9"),
                     ask("configure", words="terminal")) + judged(
                         ask("show", words="snmp community"))

    class Gap:
        what = "close the collector's half-open session"
        evidence_refs = ["read:1"]

    class Answer:
        gap = Gap()

    rows = missing.wanted(Answer(), records, feature="fixit_troubleshoot", network=NETWORK,
                          about=("incident", "inc-1"))
    # the out-of-scope address is the check working, never a missing capability
    assert [(r["kind"], r["what"]) for r in rows] == [
        ("read", "show running-config | redirect flash:x"), ("read", "a read"),
        ("read", "show snmp community"),
        ("operation", "close the collector's half-open session")]
    assert all(r["about"] == {"kind": "incident", "id": "inc-1"} for r in rows)
    assert missing.record(rows)["recorded"] == 4
    got = missing.rows()
    assert got["state"] == "ok" and len(got["rows"]) == 4
    assert got["rows"][0]["kind"] == "operation", "newest first"
    events = HS.ai_missing({"ref": type("Ref", (), {"name": NETWORK})(), "device": "",
                            "limit": 50, "since": None, "until": None,
                            "members": None})["events"]
    assert len(events) == 4 and {e["kind"] for e in events} == {"ai_missing"}
    assert events[0]["what"].startswith("AI wanted an operation Mercury lacks: close the "
                                        "collector's half-open session, for incident inc-1")
    assert HS.SOURCE_KINDS["ai_missing"] == ("ai_missing",)
    assert "ai_missing" in HS.KIND_FILTERS["ai_missing"]


def test_the_investigation_records_what_it_lacked(lab, monkeypatch):
    from modules.ai import fixit_troubleshoot as FT
    from modules.ai import missing

    _state_on()
    records = judged(ask("show", words="running-config | redirect flash:x"))

    class Incident:
        id = "inc-9"

    got = FT.record_missing({"answer": None, "reads": records}, Incident(), NETWORK)
    assert got == {"ok": True, "recorded": 1, "error": ""}
    (row,) = missing.rows()["rows"]
    assert row["feature"] == "fixit_troubleshoot" and row["about"]["id"] == "inc-9"
    assert row["network"] == NETWORK


def test_nothing_reads_a_missing_capability_to_act_on_it():
    """Only the store itself, the investigation that writes it and History's listing name the
    module: no route, job or AI feature reads a row to do anything (C3663: never acted on)."""
    import os
    import re

    from tests.source_index import ROOT, tracked

    users = []
    for path in tracked("modules", "routes", suffix=".py"):
        with open(path, encoding="utf-8") as fh:
            if re.search(r"\bfrom modules\.ai import missing\b|modules\.ai\.missing\b",
                         fh.read()):
                users.append(os.path.relpath(path, ROOT))
    users.sort()
    assert users == ["modules/ai/fixit_troubleshoot.py", "modules/history_sources.py"], users
