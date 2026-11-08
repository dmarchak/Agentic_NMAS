"""The controller app deploy's wired sources (C2765; `modules/apps/sources.py`): what SDN › Apps
and the deploy read on a real network, each from the carrier Mercury has for it.

Cases, each planted:
- the controller hosts are the parents of NetBox's ``openflow`` Service in the COMMITTED NSOT
  export (a working-tree edit is never read), each with its unit from ``openflow.unit``, its
  listen address from the Service (IPv4 or IPv6) and its login from the inventory; a host with
  no unit, a unit not of a unit's shape, or a host not in the inventory is listed with the
  problem named, and every read that needs it refuses naming it, asking no device;
- the registry, which has no carrier, refuses naming P4;
- the expected switches are those whose OpenFlow values name this controller, the controller
  host never among them, each DPID an INTEGER (the driver's form, C2756) and each profile entry
  by the switch's platform and os_version; the links are the connected cables between their
  OpenFlow ports, numbered by NetBox's openflow_port, else by the platform's own numbering, and a
  cable end neither numbers is refused naming the cable and the port;
- the host's three reads go through the reads engine (the capture list's commands, recorded),
  and answer while the calling thread already holds the controller (the confirm's job), never
  skipped as busy; an unanswered or cut read refuses naming the command;
- the stored read is the newest recorded run holding both the unit's show and cat; none is
  "unread", never "ok";
- the live read takes the controller connection the host's config context names, else the
  only one; no connection is unreadable on both reads, named;
- a whole preview on these sources, with the registry given, plans with NetBox's switches,
  links and listen address."""

import copy
import json

import pytest

from modules.apps import channel, deploy_op, sources as S
from modules.nsot import device_ops, export as X, reads
from modules.sdn import connections as C
from tests.test_controller_deploy import MANAGER, ls
from tests.test_controller_deploy_op import registry
from tests.test_nsot_export import net, netbox_list  # noqa: F401 - the fixtures
from tests.test_openflow_golden import _records, fake_netbox
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

NET = "Default"
CTL = "controller"
UNIT = "ryu-manager.service"
HOST = {"hostname": CTL, "ip": "192.0.2.1", "device_type": "linux", "username": "mercury",
        "role": "host"}
PLATFORMS = {"arista-eos": "arista_eos", "hp-procurve": "hp_procurve", "ovs-linux": "ovs_linux",
             "linux": "linux"}
VERSIONS = {"arista-sw1": "4.17.0F", "arista-sw2": "4.17.0F", "procurve-sw": "K.16.02.0020",
            "ovs1": "3.3.4", "ovs2": "3.3.4"}
DPIDS = {"arista-sw1": "0000000000000001", "arista-sw2": "0000000000000002",
         "procurve-sw": "0000000000000005"}


def lab_records(**changes):
    """The Lab 9 records with the controller's unit, each switch's os_version and a DPID for
    each switch (the OVS bridges' are the fixture's own); *changes* edit a device's
    ``config_context`` or ``custom_fields`` by name."""
    records = copy.deepcopy(_records())
    for d in records["devices"]:
        if d["name"] == CTL:
            d["config_context"] = {"openflow": {"unit": UNIT}}
        if d["name"] in VERSIONS:
            d["custom_fields"] = dict(d.get("custom_fields") or {}, os_version=VERSIONS[d["name"]])
        if d["name"] in DPIDS:
            d["custom_fields"]["openflow_datapath_id"] = DPIDS[d["name"]]
        for key, value in (changes.get(d["name"]) or {}).items():
            d[key] = value(d) if callable(value) else value
    return records


def lab_export(records=None, monkeypatch=None):
    records = records or lab_records()
    if monkeypatch is not None:
        monkeypatch.setattr("modules.inventory.source_config.load",
                            lambda name: {"source": "netbox",
                                          "filters": {"role": "openflow-switch"}})
    get, _calls = fake_netbox(records)
    built = X.build("lab9", get=get, version=lambda: records["netbox_version"])
    assert built["ok"], built["error"]
    return X.parse(built["bytes"])


@pytest.fixture
def platforms(monkeypatch):
    monkeypatch.setattr("modules.inventory.netbox_source.get_setting",
                        lambda key, default=None: (
                            {k: {"netmiko_device_type": v} for k, v in PLATFORMS.items()}
                            if key == "platform_map" else default))


@pytest.fixture
def lab(networks, platforms, monkeypatch):  # noqa: F811 - the fixture, used
    """Default holding the Lab 9 export, its inventory the controller host."""
    doc = lab_export(monkeypatch=monkeypatch)
    state = {"export": doc, "inventory": [dict(HOST)]}
    monkeypatch.setattr(X, "read", lambda network, rev="HEAD": {
        "ok": state["export"] is not None, "export": state["export"],
        "sha256": (state["export"] or {}).get("sha256", ""),
        "error": "" if state["export"] else f"{network} has no committed NSOT export at HEAD"})
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in state["inventory"]])
    return state


def the_controller():
    got = S.Wired().controllers(NET)
    assert got["state"] == "ok", got
    return next(c for c in got["controllers"] if c["name"] == CTL)


# ── the controller hosts ─────────────────────────────────────────────────────────────────────

def test_a_controller_host_is_the_openflow_services_parent_with_its_unit_and_login(lab):
    ctl = the_controller()
    assert ctl["problems"] == []
    assert ctl["unit"] == UNIT and ctl["dev"]["hostname"] == CTL
    # The Service has no address of its own: its device's primary IPv4, and the Service's port.
    assert ctl["listen"] == {"host": "192.0.2.1", "port": 6653}
    assert "NetBox's openflow Service on controller" in ctl["service"]


def test_an_ipv6_listen_address_is_read_as_an_ipv4_one_is(networks, platforms,  # noqa: F811
                                                          monkeypatch):
    records = lab_records(controller={"primary_ip4": None,
                                      "primary_ip6": {"address": "2001:db8::1/64"}})
    doc = lab_export(records, monkeypatch)
    [ctl] = S.controllers_from(doc, NET, {CTL: dict(HOST)})
    assert ctl["listen"] == {"host": "2001:db8::1", "port": 6653}
    # A Service with its own address listens there, IPv6 the same as IPv4.
    records["services"][0]["ipaddresses"] = [{"address": "2001:db8::53/64"}]
    [ctl] = S.controllers_from(lab_export(records, monkeypatch), NET, {CTL: dict(HOST)})
    assert ctl["listen"]["host"] == "2001:db8::53"


@pytest.mark.parametrize("change, inventory, words", [
    ({"config_context": {}}, [HOST], "has no openflow.unit"),
    ({"config_context": {"openflow": {"unit": "ryu; reboot"}}}, [HOST],
     "is not a unit's name"),
    ({}, [], "is not a device of Default's inventory"),
])
def test_a_host_missing_what_a_read_needs_is_listed_and_every_read_refuses_naming_it(
        lab, monkeypatch, change, inventory, words):
    lab["export"] = lab_export(lab_records(controller=change), monkeypatch)
    lab["inventory"] = list(inventory)
    asked = []
    monkeypatch.setattr(reads, "run", lambda *a, **k: asked.append(a))
    ctl = the_controller()
    assert any(words in p for p in ctl["problems"]), ctl["problems"]
    src = S.Wired().for_actor("op@example.invalid")
    got = src.host_reads(NET, ctl)
    assert got["state"] == "unreadable" and words in got["error"]
    stored = src.controller_read(NET, ctl)
    assert stored["state"] == "unread" and words in stored["error"]
    # The effect: no device was asked.
    assert asked == []


def test_no_committed_export_is_unreadable_naming_it_never_no_controller(lab):
    lab["export"] = None
    got = S.Wired().controllers(NET)
    assert got["state"] == "unreadable" and got["controllers"] == []
    assert "committed NSOT export" in got["error"] and "no committed NSOT export" in got["error"]


def test_the_controllers_are_read_from_the_committed_export_never_the_working_tree(
        net, platforms, monkeypatch):  # noqa: F811 - the fixtures
    records = lab_records()
    get, _calls = fake_netbox(records)
    built = X.build("lab9", get=get, version=lambda: records["netbox_version"])
    assert X.write("lab9", "op@example.invalid", "access-assertion", data=built["bytes"])["ok"]
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [dict(HOST)])
    # A working-tree edit naming another host is never read.
    edited = json.loads(built["bytes"])
    edited["body"]["services"][0]["parent"] = "elsewhere"
    (net / "config_repo" / X.PATH).write_text(json.dumps(edited), encoding="utf-8")
    got = S.Wired().controllers("lab9")
    assert got["state"] == "ok" and [c["name"] for c in got["controllers"]] == [CTL]


def test_the_registry_has_no_carrier_and_refuses_naming_p4(lab):
    got = S.Wired().registered(NET)
    assert got["state"] == "not_wired" and got["apps"] == []
    assert "the app registry (P4) is not built" in got["error"]


# ── what the post-check expects ──────────────────────────────────────────────────────────────

def test_the_expected_switches_are_netboxs_with_integer_dpids_never_the_host(lab):
    exp = S.Wired().expected(NET, the_controller())
    assert exp["state"] == "ok", exp["error"]
    got = {s["name"]: s["dpid"] for s in exp["switches"]}
    # C2756: NetBox's sixteen hex digits as the integers the driver lists.
    assert got == {"arista-sw1": 1, "arista-sw2": 2, "ovs1": 3, "ovs2": 4, "procurve-sw": 5}
    assert all(isinstance(d, int) for d in got.values())
    assert all(s["selected"]["ok"] for s in exp["switches"])


def test_the_controller_host_is_never_one_of_its_switches_even_with_a_port_tagged(
        lab, monkeypatch):
    records = lab_records()
    for i in records["interfaces"]:
        if i["device"]["name"] == CTL:
            i["tags"] = [{"slug": "openflow"}]
    lab["export"] = lab_export(records, monkeypatch)
    exp = S.Wired().expected(NET, the_controller())
    assert exp["state"] == "ok", exp["error"]
    assert CTL not in {s["name"] for s in exp["switches"]}


def test_the_expected_links_are_the_cables_between_openflow_ports_by_their_numbers(lab):
    exp = S.Wired().expected(NET, the_controller())
    pairs = sorted(sorted([(lk["src"]["dpid"], lk["src"]["port_no"]),
                           (lk["dst"]["dpid"], lk["dst"]["port_no"])]) for lk in exp["links"])
    assert pairs == [[(1, 18), (3, 1)], [(1, 19), (5, 2)], [(2, 18), (4, 1)], [(4, 3), (5, 3)]]


def _without_port(records, device, port):
    for i in records["interfaces"]:
        if i["device"]["name"] == device and i["name"] == port:
            i["custom_fields"] = {"openflow_port": None}
    return records


def test_a_port_numbered_by_its_platform_needs_no_openflow_port(lab, monkeypatch):
    lab["export"] = lab_export(_without_port(lab_records(), "arista-sw1", "Ethernet19"),
                               monkeypatch)
    exp = S.Wired().expected(NET, the_controller())
    assert exp["state"] == "ok", exp["error"]
    assert {"dpid": 1, "port_no": 19} in [lk[e] for lk in exp["links"] for e in ("src", "dst")]


def test_a_cable_end_nothing_numbers_is_refused_naming_the_cable_and_the_port(lab, monkeypatch):
    # Open vSwitch numbers ports by the order they are added: only NetBox's number names one.
    lab["export"] = lab_export(_without_port(lab_records(), "ovs2", "eno4"), monkeypatch)
    exp = S.Wired().expected(NET, the_controller())
    assert exp["state"] == "unreadable" and exp["switches"] == []
    assert "the cable ovs2:eno4 to procurve-sw:3: ovs2's eno4 has no OpenFlow port number" \
        in exp["error"]


def test_a_switch_whose_values_cannot_be_read_refuses_naming_it(lab, monkeypatch):
    lab["export"] = lab_export(lab_records(ovs1={
        "config_context": {"openflow": {"version": "9.9"}}}), monkeypatch)
    exp = S.Wired().expected(NET, the_controller())
    assert exp["state"] == "unreadable"
    assert "ovs1's OpenFlow values can't be read: openflow.version '9.9'" in exp["error"]


def test_a_switch_with_no_os_version_is_cant_tell_never_a_pass(lab, monkeypatch):
    lab["export"] = lab_export(lab_records(ovs1={
        "custom_fields": lambda d: dict(d["custom_fields"], os_version=None)}), monkeypatch)
    exp = S.Wired().expected(NET, the_controller())
    sel = next(s for s in exp["switches"] if s["name"] == "ovs1")["selected"]
    assert sel["ok"] is False and "NetBox holds no os_version for ovs1" in sel["error"]


# ── the host's reads ─────────────────────────────────────────────────────────────────────────

CAT = f"# /etc/systemd/system/{UNIT}\n[Service]\nUser=ryu\n"


@pytest.fixture
def host(lab, monkeypatch):
    """The controller host answering its three reads through the reads engine's own path."""
    answers = {f"systemctl show -p User -p ExecStart {UNIT}":
               (f"User=ryu\nExecStart={{ path={MANAGER} ; argv[]={MANAGER} --observe-links ; "
                "ignore_errors=no ; start_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }\n"),
               "ls -la /opt/ryu-apps": ls("mercury"), f"systemctl cat {UNIT}": CAT}
    asked = []

    def run_device_command(conn, command, read_timeout=None):
        asked.append(command)
        if command not in answers:
            raise RuntimeError(f"not answered: {command}")
        return answers[command]
    monkeypatch.setattr("modules.commands.run_device_command", run_device_command)
    monkeypatch.setattr("modules.connection.with_temp_connection", lambda dev, fn: fn(object()))
    return {"answers": answers, "asked": asked}


def test_the_three_reads_go_through_the_reads_engine_and_are_recorded(host):
    ctl = the_controller()
    got = S.Wired().for_actor("op@example.invalid").host_reads(NET, ctl)
    assert got["state"] == "ok", got["error"]
    assert sorted(host["asked"]) == sorted(channel.host_commands(UNIT).values())
    assert got["cat"] == CAT and got["at"]
    rec = reads.get(NET, got["run"])
    assert rec["actor"] == "op@example.invalid" and rec["state"] == "done"
    assert rec["results"][CTL]["driver"] == "linux"


def test_the_reads_answer_while_this_thread_holds_the_controller(host):
    from modules.inventory.management import HOST_DEPLOY
    ctl = the_controller()
    with device_ops.hold(NET, CTL, HOST_DEPLOY, "op@example.invalid", ip=HOST["ip"]):
        got = S.Wired().for_actor("op@example.invalid").host_reads(NET, ctl)
    assert got["state"] == "ok", got["error"]


def test_an_unanswered_read_refuses_naming_the_command(host):
    del host["answers"][f"systemctl cat {UNIT}"]
    got = S.Wired().for_actor("op@example.invalid").host_reads(NET, the_controller())
    assert got["state"] == "unreadable"
    assert f"`systemctl cat {UNIT}` was not answered" in got["error"]


def test_a_read_with_no_person_asks_no_device(host):
    got = S.Wired().host_reads(NET, the_controller())
    assert got["state"] == "unreadable" and "for a person" in got["error"]
    assert host["asked"] == []


def test_an_answer_cut_at_the_cap_is_never_read_as_whole(host):
    host["answers"][f"systemctl cat {UNIT}"] = CAT + "#" * (64 * 1024) + "\n"
    ctl = the_controller()
    got = S.Wired().for_actor("op@example.invalid").host_reads(NET, ctl)
    assert got["state"] == "unreadable" and "was cut at" in got["error"]
    # The run is recorded, and the stored read never takes its cut answer either.
    assert S.Wired().controller_read(NET, ctl)["state"] == "unread"


def test_the_stored_read_is_the_newest_run_with_both_answers_and_none_is_unread(host):
    ctl = the_controller()
    none = S.Wired().controller_read(NET, ctl)
    assert none["state"] == "unread" and f"no read of {UNIT} on {CTL} is recorded" in \
        none["error"]
    S.Wired().for_actor("op@example.invalid").host_reads(NET, ctl)
    got = S.Wired().controller_read(NET, ctl)
    assert got["state"] == "ok" and got["cat"] == CAT and got["at"]
    assert "User=ryu" in got["show"]


# ── the controller live ──────────────────────────────────────────────────────────────────────

class FakeDriver:
    def switches(self):
        return {"ok": True, "switches": [{"dpid": 1}, {"dpid": 3}]}

    def links(self):
        return {"ok": True, "links": []}


def test_the_live_read_takes_the_networks_only_connection(lab, monkeypatch):
    monkeypatch.setattr(C, "connections", lambda network: {"connections": [{"name": "ryu"}]})
    monkeypatch.setattr(C, "driver_for", lambda network, name: {"ok": name == "ryu",
                                                                "driver": FakeDriver()})
    got = S.Wired().observe(NET, the_controller())
    assert got["connection"] == "ryu" and got["switches"]["switches"][1]["dpid"] == 3
    assert got["links"] == {"ok": True, "links": []}


def test_with_two_connections_the_host_names_its_own_or_both_reads_say_why(lab, monkeypatch):
    monkeypatch.setattr(C, "connections", lambda network: {
        "connections": [{"name": "ryu"}, {"name": "other"}]})
    monkeypatch.setattr(C, "driver_for", lambda network, name: {"ok": True,
                                                                "driver": FakeDriver()})
    got = S.Wired().observe(NET, the_controller())
    assert got["switches"]["ok"] is False and got["links"]["ok"] is False
    assert "has 2 controller connections (ryu, other)" in got["switches"]["error"]
    lab["export"] = lab_export(lab_records(controller={"config_context": {"openflow": {
        "unit": UNIT, "connection": "other"}}}), monkeypatch)
    assert S.Wired().observe(NET, the_controller())["connection"] == "other"
    # A name the network holds no connection by is refused naming it and the ones there are.
    lab["export"] = lab_export(lab_records(controller={"config_context": {"openflow": {
        "unit": UNIT, "connection": "gone"}}}), monkeypatch)
    got = S.Wired().observe(NET, the_controller())
    assert got["switches"]["ok"] is False and \
        "Default has no controller connection 'gone': ryu, other" in got["switches"]["error"]


# ── a whole preview, and the confirm's job ───────────────────────────────────────────────────

@pytest.fixture
def given(host, tmp_path, monkeypatch):
    """The wired sources with the registry given (P4's, not built) and a send that is never
    made, the controller connection the network's only one; the receipts and the windows in this
    test's folder (C571, C1864)."""
    from modules import controller_deploy_receipts as deploy_receipts, restarts

    monkeypatch.setattr(C, "connections", lambda network: {"connections": [{"name": "ryu"}]})
    monkeypatch.setattr(C, "driver_for", lambda network, name: {"ok": True,
                                                                "driver": FakeDriver()})
    where = tmp_path / "receipts"
    monkeypatch.setattr(deploy_receipts, "path_for",
                        lambda network: str(where / network / deploy_receipts.FILENAME))
    (tmp_path / "restarts").mkdir()
    monkeypatch.setattr(restarts, "_data", lambda name: str(tmp_path / "restarts" / name))
    reg = registry(tmp_path)

    class Given(S.Wired):
        def for_actor(self, actor):
            return Given(actor)

        def registered(self, network):
            return reg

        def send(self, dev, tplan):
            return {"ok": False, "command_sent": False, "error": "a test's send, never made",
                    "staged": [], "not_staged": []}
    monkeypatch.setattr(deploy_op, "SOURCES", Given())
    return Given


def test_the_production_default_is_the_wired_sources(monkeypatch):
    monkeypatch.setattr(deploy_op, "SOURCES", None)
    assert type(deploy_op.sources()) is S.Wired


def test_a_preview_on_the_wired_sources_plans_with_netboxs_switches_links_and_listen(given):
    src = given().for_actor("op@example.invalid")
    plan = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    assert plan["ok"], plan.get("refusals")
    assert sorted(plan["expected"]["switches"]) == [1, 2, 3, 4, 5]
    assert len(plan["expected"]["links"]) == 4
    assert plan["request"]["listen"] == {"host": "192.0.2.1", "port": 6653}
    # What is already missing was read live: switches 2, 4 and 5 are not connected now.
    assert plan["already"]["read"] is True and len(plan["already"]["missing_switches"]) == 3


def _host_runs():
    return [r for r in reads.runs(NET, device=CTL)["runs"]
            if r.get("commands") == list(channel.host_commands(UNIT).values())]


def test_the_apps_tab_lists_the_controller_host_netbox_names_on_the_wired_sources(
        host, monkeypatch):
    from html import unescape

    import app as A
    monkeypatch.setattr(deploy_op, "SOURCES", S.Wired())
    S.Wired().for_actor("op@example.invalid").host_reads(NET, the_controller())
    asked_before = list(host["asked"])
    runs_before = len(reads.runs(NET)["runs"])
    html = unescape(A.app.test_client().get("/v2/sdn/apps").get_data(as_text=True))
    # The page view draws the stored read: it asks the host nothing and records no read.
    assert host["asked"] == asked_before and len(reads.runs(NET)["runs"]) == runs_before
    assert "can't be listed" not in html
    assert f">{CTL} " in html and f"unit {UNIT}" in html.replace('<span class="mono">', "") \
        .replace("</span>", "")
    assert "listening on 192.0.2.1" in html.replace('<span class="mono">', "") \
        .replace("</span>", "")
    # The registry alone is not built, and the tab says so in place of an empty list.
    assert "No app version can be listed:" in html and "the app registry (P4) is not built" \
        in html
    # The stored read (the run just recorded) is what the card compares; no deploy is recorded.
    assert "no deploy through Mercury" in html


def test_the_preview_route_reads_the_host_as_the_person_previewing(given):
    import app as A
    from tests.conftest import TEST_PERSON
    r = A.app.test_client().post("/v2/sdn/apps/preview", data={
        "list": NET, "controller": CTL, "set": "of_versions=1.0.0"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert "The set, in load order" in r.get_data(as_text=True)
    [run] = _host_runs()
    assert run["actor"] == TEST_PERSON
    # So it is gated as a device read (a person) and says what it changes: the reads' record.
    from modules import invalidation, route_gates
    assert route_gates.GATES["sdn_v2.apps_preview"].kind == "reveal"
    assert invalidation.DECLARED["sdn_v2.apps_preview"] == ("reads",)


def test_the_confirms_job_reads_the_host_again_as_its_actor_holding_it(given):
    from modules import controller_deploy_receipts as deploy_receipts
    from modules.nsot import capture_job

    plan = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"},
                             src=given().for_actor("op@example.invalid"))
    assert plan["ok"], plan.get("refusals")
    job = deploy_op.start(NET, CTL, {"of_versions": "1.0.0"}, plan["plan_sha256"],
                          then_parts=plan["parts"], actor="op@example.invalid",
                          actor_verified="access-assertion")
    assert capture_job.wait(job, 60)
    [receipt] = deploy_receipts.read(NET)["rows"]
    # The plan made again (holding the controller) matched: the send was the first thing to
    # fail, never a refusal of the host's reads.
    assert receipt["outcome"] == "apply failed", receipt.get("error")
    assert [r["actor"] for r in _host_runs()] == ["op@example.invalid", "op@example.invalid"]


def test_the_post_checks_reads_are_of_the_controller_as_netbox_names_it(given, monkeypatch):
    """The post-check reads the controller the confirm found (its unit, its connection), so a
    host whose config context names its connection is read on that one, never another."""
    from modules import controller_deploy_receipts as deploy_receipts
    from modules.nsot import capture_job

    seen, links = [], []

    class Sent(given):
        def for_actor(self, actor):
            return Sent(actor)

        def send(self, dev, tplan):
            out = {"ok": True, "up_after_s": 3.0}
            return {"ok": True, "step": "done", "error": "", "staged": ["x"],
                    "not_staged": [], "request_written": True, "command_sent": True,
                    "printed": out, "outcome": out}

        def observe(self, network, controller):
            seen.append(dict(controller))
            return {"switches": {"ok": True, "switches": [{"dpid": d} for d in range(1, 6)]},
                    "links": {"ok": True, "links": links},
                    "health": {"of_versions": {"ok": True}}}
    monkeypatch.setattr(deploy_op, "SOURCES", Sent())
    plan = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"},
                             src=Sent().for_actor("op@example.invalid"))
    assert plan["ok"], plan.get("refusals")
    seen.clear()
    links.extend(plan["expected"]["links"])     # every expected link back after the restart
    job = deploy_op.start(NET, CTL, {"of_versions": "1.0.0"}, plan["plan_sha256"],
                          then_parts=plan["parts"], actor="op@example.invalid",
                          actor_verified="access-assertion")
    assert capture_job.wait(job, 60)
    [receipt] = deploy_receipts.read(NET)["rows"]
    assert receipt["outcome"] == "deployed", receipt.get("error")
    assert seen and all(c.get("unit") == UNIT and "connection" in c for c in seen), seen
