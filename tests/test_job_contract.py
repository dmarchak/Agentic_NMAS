"""The job contract published as stubs (the SDN platform design r4, section 11, I-1; phase P1):
`modules/jobs/base.py` (the declaration, the scope, the inputs), `modules/jobs/sdk.py` (the
handles as signatures, the change plan recording), `modules/jobs/testing.py` (the context a unit
test runs a job in) and the recorded Ryu (`tests/fixtures/sdn/ryu_recorded.py`) its controller
reads come from. Every refusal is planted and must name the field and the value."""

import hashlib
import json
import os
import re

import pytest

from modules.jobs import base as B
from modules.jobs import sdk as S
from modules.jobs import testing as T
from tests.fixtures.sdn import ryu_recorded as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(ROOT, "docs", "DEVELOPING_JOBS_AND_APPS.md")


def meta(**changes):
    """Section 11's example declaration, with *changes*."""
    fields = dict(name="trace-path", version="1.0.0", summary="Traces a path.",
                  permission="read",
                  scope={"object_types": ["dcim.device", "dcim.interface"],
                         "roles": ["openflow-switch", "host"]},
                  max_changes=0, autonomous=False)
    fields.update(changes)
    return B.JobMeta(**fields)


def writer(max_changes=3):
    return meta(name="edge-flows", permission="write", max_changes=max_changes)


# ── the declaration ──────────────────────────────────────────────────────────────────────────

def test_the_designs_example_declaration_is_accepted():
    m = meta()
    assert (m.name, m.permission, m.max_changes, m.autonomous) == ("trace-path", "read", 0, False)
    assert m.scope.object_types == ("dcim.device", "dcim.interface")


@pytest.mark.parametrize("field,value", [
    ("name", "Trace Path"), ("name", "trace_path"), ("name", "1trace"), ("name", "t" * 42),
    ("version", "1.0"), ("version", "v1.0.0"), ("summary", ""), ("summary", "x" * 201),
    ("permission", "rw"), ("max_changes", -1), ("max_changes", "3"), ("autonomous", "yes"),
], ids=lambda v: str(v)[:20])
def test_a_malformed_field_is_refused_naming_the_field_and_the_value(field, value):
    with pytest.raises(B.ContractError) as got:
        meta(**{field: value})
    text = str(got.value)
    assert text.startswith("JobMeta refused: ")
    assert f"{field}: " in text and B.quoted(value) in text


@pytest.mark.parametrize("permission,max_changes,said", [
    ("read", 1, "permission 'read' makes no change, so max_changes is 0, not 1"),
    ("write", 0, "permission 'write' declares max_changes of at least 1, not 0"),
])
def test_permission_and_max_changes_must_agree(permission, max_changes, said):
    with pytest.raises(B.ContractError) as got:
        meta(permission=permission, max_changes=max_changes)
    assert said in str(got.value)


def test_a_job_reaching_no_object_type_is_refused():
    with pytest.raises(B.ContractError) as got:
        meta(scope={"object_types": [], "roles": ["host"]})
    assert "scope.object_types names at least one" in str(got.value)


def test_an_unknown_field_and_a_missing_one_are_each_named():
    with pytest.raises(B.ContractError) as got:
        B.JobMeta(name="trace-path", version="1.0.0", permission="read",
                  scope={"object_types": ["dcim.device"]}, timeout=5)
    assert "summary: missing" in str(got.value)
    assert "timeout: not a field of this contract (given 5)" in str(got.value)


def test_a_declaration_is_frozen():
    with pytest.raises(Exception):
        meta().max_changes = 5


# ── the scope ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("field,value,said", [
    ("object_types", ["device"], "an object type 'device' does not match"),
    ("object_types", ["dcim.device", "dcim.device"], "lists 'dcim.device' more than once"),
    ("roles", ["Openflow Switch"], "a role 'Openflow Switch' does not match"),
    ("roles", ["host", "host"], "lists 'host' more than once"),
])
def test_a_malformed_scope_is_refused_naming_the_value(field, value, said):
    with pytest.raises(B.ContractError) as got:
        B.Scope(**{field: value})
    assert f"{field}" in str(got.value) and said in str(got.value)


def test_a_call_outside_the_scope_raises_naming_the_call_and_the_scope():
    scope = meta().scope
    scope.check("netbox.get('dcim.device')", "dcim.device", "host")
    with pytest.raises(B.ScopeError) as got:
        scope.check("netbox.get('ipam.prefix')", "ipam.prefix")
    assert ("netbox.get('ipam.prefix') reads 'ipam.prefix', outside the scope's object types "
            "[dcim.device, dcim.interface], roles [openflow-switch, host]") in str(got.value)
    with pytest.raises(B.ScopeError) as got:
        scope.check("netbox.get('dcim.device')", "dcim.device", "router")
    assert "reaches role 'router', outside" in str(got.value)


def test_an_empty_scope_reaches_nothing():
    with pytest.raises(B.ScopeError):
        B.Scope().check("netbox.get('dcim.device')", "dcim.device")


def test_a_job_calling_a_job_gets_the_intersection_never_the_union():
    outer = writer(max_changes=5)
    inner = meta(name="dhcp-unicast", permission="write", max_changes=2,
                 scope={"object_types": ["dcim.interface", "ipam.prefix"],
                        "roles": ["host", "router"]})
    got = B.composed_reach(outer, inner)
    assert got["permission"] == "write" and got["max_changes"] == 2
    assert got["scope"] == B.Scope(object_types=["dcim.interface"], roles=["host"])
    read = B.composed_reach(meta(), inner)
    assert (read["permission"], read["max_changes"]) == ("read", 0)


# ── the inputs ───────────────────────────────────────────────────────────────────────────────

class Trace(B.Job):
    meta = meta()

    class Inputs(B.JobInputs):
        src: B.HostRef
        dst: B.HostRef | B.DeviceRef

    def run(self, ctx, inputs):
        ctx.output.log(f"{inputs.src.name} to {inputs.dst.name} ({inputs.dst.kind})")


def test_a_reference_is_told_by_its_kind():
    got = Trace.Inputs.parse({"src": {"id": 7, "name": "host-a", "kind": "host"},
                              "dst": {"id": 9, "name": "edge1", "kind": "device"}})
    assert isinstance(got.src, B.HostRef) and isinstance(got.dst, B.DeviceRef)


@pytest.mark.parametrize("ref,said", [
    ({"id": 0, "name": "edge1"}, "a NetBox ID is 1 or more, not 0"),
    ({"id": True, "name": "edge1"}, "src.id: True refused"),
    ({"id": "7", "name": "edge1"}, "src.id: '7' refused"),
    ({"id": 7, "name": " "}, "a name is a non-empty label"),
    ({"id": 7, "name": "edge\n1"}, "printable characters"),
    ({"id": 7, "name": "edge1", "kind": "device"}, "src.kind: 'device' refused"),
], ids=["zero", "bool", "string-id", "blank", "control", "wrong-kind"])
def test_a_malformed_reference_is_refused_naming_it(ref, said):
    with pytest.raises(B.ContractError) as got:
        Trace.Inputs.parse({"src": ref, "dst": {"id": 9, "name": "edge1"}}, "Trace.Inputs")
    assert str(got.value).startswith("Trace.Inputs refused: ") and said in str(got.value)


def test_an_unknown_input_is_refused_by_name():
    with pytest.raises(B.ContractError) as got:
        Trace.Inputs.parse({"src": {"id": 7, "name": "host-a"}, "dst": {"id": 9, "name": "e"},
                            "port": 53})
    assert "port: not a field of this contract (given 53)" in str(got.value)


@pytest.mark.parametrize("body,said", [
    ({"Inputs": B.JobInputs, "run": lambda self, ctx, inputs: None}, "meta is a JobMeta"),
    ({"meta": meta(), "Inputs": dict, "run": lambda self, ctx, inputs: None},
     "Inputs is a subclass of JobInputs"),
    ({"meta": meta()}, "run(self, ctx, inputs) is not defined"),
], ids=["no-meta", "bad-inputs", "no-run"])
def test_a_job_class_missing_a_part_is_refused_when_defined(body, said):
    with pytest.raises(B.ContractError) as got:
        type("Broken", (B.Job,), body)
    assert str(got.value).startswith("the job class Broken refused: ") and said in str(got.value)


# ── the SDK's signatures ─────────────────────────────────────────────────────────────────────

SIGNATURES = [(handle, name) for handle in (S.NetBoxHandle, S.NsotHandle, S.DevicesHandle,
                                            S.ControllerHandle, S.PathsHandle, S.AiHandle,
                                            S.OutputHandle, S.JobFilesHandle)
              for name in sorted(vars(handle)) if not name.startswith("_") and name.islower()]
ARGS = {"get": ("dcim.device",), "one": ("dcim.device", 1), "show": (None, "show version"),
        "switch_desc": (1,), "flows": (1,), "port_stats": (1,), "meters": (1,),
        "trace": ("a", "b"), "ask": ("why",), "table": ("t", [], []), "log": ("x",),
        "file": ("f", "x"), "read": ("f",)}


def test_every_handle_in_the_designs_table_has_its_signatures():
    ctx = S.Context(meta())
    for handle in ("netbox", "nsot", "devices", "controller", "paths", "changes", "ai",
                   "output", "job_files"):
        assert getattr(ctx, handle) is not None
    assert len(SIGNATURES) >= 20                          # the floor: every handle's calls


@pytest.mark.parametrize("handle,name", SIGNATURES,
                         ids=[f"{h.__name__}.{n}" for h, n in SIGNATURES])
def test_a_signature_raises_naming_the_call_and_the_phase_that_builds_it(handle, name):
    with pytest.raises(S.NotBuilt) as got:
        getattr(handle(), name)(*ARGS.get(name, ()))
    text = str(got.value)
    assert re.search(r"ctx\.[a-z_]+\.[a-z_]+ is not built yet: P[0-9]", text), text
    assert name in text and "modules.jobs.testing.FakeContext" in text


def test_commit_is_not_built_in_p1():
    with pytest.raises(S.NotBuilt, match="P4"):
        S.Context(writer(), mode="commit")
    with pytest.raises(S.NotBuilt, match="changes.commit is not built yet: P4"):
        S.Context(writer()).changes.commit()
    with pytest.raises(B.ContractError, match="mode 'apply' is not one of plan, commit"):
        S.Context(writer(), mode="apply")


# ── the change plan ──────────────────────────────────────────────────────────────────────────

FLOW = {"table_id": 0, "priority": 300, "match": {"eth_type": 2048, "ip_proto": 17,
                                                  "udp_dst": 67}, "actions": []}


def test_a_write_jobs_changes_are_recorded_in_order_and_nothing_else_happens():
    plan = S.ChangePlan(writer())
    plan.flow(4, "add_flow", flow=FLOW, connection="ctl")
    plan.feature(B.DeviceRef(id=3, name="edge1"), "openflow", {"version": "1.3"})
    plan.app_policy("dns_blacklist", "/policy", {"cache": {"ttl_seconds": 300}})
    assert [c["kind"] for c in plan.changes] == ["flow", "feature", "app_policy"]
    assert plan.changes[0] == {"kind": "flow", "connection": "ctl", "dpid": 4,
                               "change": {"do": "add_flow", "flow": FLOW}}
    assert plan.changes[1]["device"] == {"id": 3, "name": "edge1"}


def test_a_recorded_change_is_a_copy_the_job_cannot_move_afterwards():
    plan = S.ChangePlan(writer())
    given = json.loads(json.dumps(FLOW))
    returned = plan.flow(4, flow=given)
    given["priority"], returned["dpid"] = 1, 99
    assert plan.changes[0]["change"]["flow"]["priority"] == 300
    assert plan.changes[0]["dpid"] == 4


@pytest.mark.parametrize("dpid", [4, "0x4", "0000000000000004", "00:00:00:00:00:00:00:04"])
def test_a_dpid_is_recorded_as_its_number_in_every_form(dpid):
    plan = S.ChangePlan(writer())
    assert plan.flow(dpid, flow=FLOW)["dpid"] == 4


def test_a_read_job_makes_no_change():
    plan = S.ChangePlan(meta())
    with pytest.raises(S.ChangeRefused) as got:
        plan.flow(4, flow=FLOW)
    assert ("ctx.changes.flow from trace-path 1.0.0 refused: the job's permission is 'read'"
            in str(got.value))
    assert len(plan) == 0


def test_a_change_past_max_changes_is_refused_naming_both():
    plan = S.ChangePlan(writer(max_changes=1))
    plan.flow(4, flow=FLOW)
    with pytest.raises(S.ChangeRefused) as got:
        plan.flow(3, flow=FLOW)
    assert "change 2 is past the job's max_changes of 1" in str(got.value)
    assert len(plan) == 1


@pytest.mark.parametrize("call,said", [
    (lambda p: p.flow("4", flow=FLOW), "'4' is not a datapath id"),
    (lambda p: p.flow(4, "wipe_table", flow=FLOW), "do 'wipe_table' is not one of add_flow"),
    (lambda p: p.flow(4, "add_flow"), "add_flow names its flow as a non-empty mapping, not None"),
    (lambda p: p.flow(4, "add_meter", flow=FLOW), "add_meter names its meter"),
    (lambda p: p.flow(4, "add_flow", flow=FLOW, meter={"meter_id": 1}),
     "add_flow takes a flow, not a meter"),
    (lambda p: p.flow(4, flow={"match": {"in_port": {1, 2}}}),
     "flow.change.flow.match.in_port is a set"),
    (lambda p: p.flow(4, flow={"priority": float("nan")}), "which JSON cannot carry"),
    (lambda p: p.feature({"id": 3}, "openflow", {}), "device is a DeviceRef, not {'id': 3}"),
    (lambda p: p.feature(B.DeviceRef(id=3, name="e"), "Open Flow", {}),
     "feature 'Open Flow' does not match"),
    (lambda p: p.feature(B.DeviceRef(id=3, name="e"), "openflow", [1]),
     "values is a mapping, not [1]"),
    (lambda p: p.app_policy("dns-blacklist", "/policy", {}), "app 'dns-blacklist' does not match"),
    (lambda p: p.app_policy("dns_blacklist", "policy", {}), "endpoint 'policy' is a path"),
    (lambda p: p.app_policy("dns_blacklist", "/policy", "x"), "body is a mapping, not 'x'"),
], ids=["dpid", "do", "no-flow", "no-meter", "both", "set", "nan", "device", "feature",
        "values", "app", "endpoint", "body"])
def test_a_malformed_change_is_refused_naming_its_value(call, said):
    plan = S.ChangePlan(writer())
    with pytest.raises(S.ChangeRefused) as got:
        call(plan)
    assert said in str(got.value)
    assert len(plan) == 0


def test_the_plans_hash_is_its_canonical_json_and_moves_with_any_change():
    one, two = S.ChangePlan(writer()), S.ChangePlan(writer())
    one.flow(4, flow={"priority": 300, "table_id": 0})
    two.flow(4, flow={"table_id": 0, "priority": 300})            # the same, keys reordered
    assert one.sha256() == two.sha256()
    text = json.dumps({"changes": one.changes, "job": "edge-flows", "version": "1.0.0"},
                      sort_keys=True, separators=(",", ":"))
    assert one.sha256() == hashlib.sha256(text.encode()).hexdigest()
    two.flow(3, flow={"table_id": 0, "priority": 300})
    assert one.sha256() != two.sha256()


# ── the recorded Ryu ─────────────────────────────────────────────────────────────────────────

def capture_sections():
    """The capture's headers, read by a path independent of the fake's parser."""
    with open(R.CAPTURE, encoding="utf-8") as fh:
        return re.findall(r"^### (\S+)(?: (\d+))?$", fh.read(), re.M)


def test_the_recorded_ryu_answers_every_path_the_capture_recorded():
    ryu = R.RecordedRyu()
    sections = capture_sections()
    assert len(sections) >= 12                              # the floor: 2 + 2 per switch x 5
    expected = sorted(R.SECTIONS[s].format(d) for s, d in sections)
    assert ryu.paths == expected
    with open(R.CAPTURE, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    first_desc = next(i for i, line in enumerate(lines) if line.startswith("### desc "))
    dpid = lines[first_desc].split()[2]
    assert ryu.get(f"/stats/desc/{dpid}") == json.loads(lines[first_desc + 1])


@pytest.mark.parametrize("method,path", [("GET", "/stats/flow/4"), ("GET", "/stats/desc/99"),
                                         ("POST", "/stats/switches"),
                                         ("GET", "/v1.0/topology/hosts")])
def test_a_path_not_recorded_raises_naming_it(method, path):
    with pytest.raises(R.UnrecordedPath) as got:
        R.RecordedRyu().answer(method, path)
    assert str(got.value).startswith(f"{method} {path} was not recorded")


def test_a_malformed_capture_is_refused_naming_its_line():
    with pytest.raises(ValueError, match="line 1: 'flows 4' is not one of the recorded"):
        R.parse_capture("### flows 4\n[]\n")
    with pytest.raises(ValueError, match="line 2: the answer to /stats/switches is not JSON"):
        R.parse_capture("### switches\n[1, \n")


# ── the test double ──────────────────────────────────────────────────────────────────────────

class Inventory(B.Job):
    """A read job a teammate might write: every switch, its maker, and its links."""

    meta = meta(name="switch-inventory")

    def run(self, ctx, inputs):
        switches = ctx.controller.switches()["switches"]
        links = ctx.controller.links()["links"]
        rows = []
        for sw in switches:
            desc = ctx.controller.switch_desc(sw["dpid"])["desc"]
            ends = sum(1 for link in links if link["src"]["dpid"] == sw["dpid"])
            rows.append([sw["dpid_hex"], desc["mfr_desc"], ends])
        ctx.output.table("switches", ["dpid", "maker", "links"], rows)


def test_a_job_reads_the_recorded_controller_through_the_real_driver():
    ryu = R.RecordedRyu()
    ctx = T.plan_run(Inventory, {}, controller=ryu.driver())
    table = ctx.output.tables[0]
    assert len(table["rows"]) == len(ryu.dpids())
    with open(R.CAPTURE, encoding="utf-8") as fh:
        text = fh.read()
    links = json.loads(text.split("### links\n", 1)[1].splitlines()[0])
    assert sum(r[2] for r in table["rows"]) == len(links)
    assert len(ctx.changes) == 0
    assert all(method == "GET" for method, _path in ryu.sent)


def test_the_controller_handle_offers_reads_only():
    ctx = T.FakeContext(writer(), controller=R.RecordedRyu().driver())
    assert set(T.CONTROLLER_READS) == {"switches", "switch_desc", "links", "hosts", "topology",
                                       "flows", "port_stats", "meters"}
    with pytest.raises(AttributeError, match="a controller write is ctx.changes.flow"):
        ctx.controller.add_flow(4, FLOW)


def test_an_unrecorded_read_through_the_driver_answers_its_path():
    ctx = T.FakeContext(meta(), controller=R.RecordedRyu().driver())
    got = ctx.controller.flows(4)
    assert got["ok"] is False and "GET /stats/flow/4 was not recorded" in got["error"]


def test_the_fake_netbox_refuses_an_object_type_outside_the_scope():
    ctx = T.FakeContext(meta(), netbox={"dcim.device": [{"id": 3, "name": "edge1"}],
                                        "ipam.prefix": [{"id": 1}]})
    assert ctx.netbox.get("dcim.device", name="edge1") == [{"id": 3, "name": "edge1"}]
    assert ctx.netbox.one("dcim.device", 3)["name"] == "edge1"
    with pytest.raises(B.ScopeError, match=r"netbox.get\('ipam.prefix'\) reads 'ipam.prefix'"):
        ctx.netbox.get("ipam.prefix")


def test_the_fake_devices_keep_show_commands_allowlist():
    edge = B.DeviceRef(id=3, name="edge1")
    ctx = T.FakeContext(meta(), devices={(3, "show version"): "Version 1"})
    assert ctx.devices.show(edge, "show version") == {"ok": True, "error": "",
                                                      "text": "Version 1"}
    refused = ctx.devices.show(edge, "configure terminal")
    assert refused["ok"] is False and refused["error"]
    with pytest.raises(LookupError, match="no answer to 'show clock' from device 3"):
        ctx.devices.show(edge, "show clock")


def test_a_handle_not_given_stays_its_signature():
    ctx = T.FakeContext(meta())
    with pytest.raises(S.NotBuilt, match="ctx.ai.ask"):
        ctx.ai.ask("why")


def test_recorded_output_refuses_a_ragged_table():
    out = T.RecordedOutput()
    with pytest.raises(B.ContractError, match="row 1 has 1 cells, not the 2 columns"):
        out.table("t", ["a", "b"], [[1, 2], [3]])


def test_plan_run_validates_the_inputs_through_the_jobs_inputs():
    with pytest.raises(B.ContractError, match="Trace.Inputs refused: src: missing"):
        T.plan_run(Trace, {"dst": {"id": 9, "name": "edge1"}})
    ctx = T.plan_run(Trace, {"src": {"id": 7, "name": "host-a"},
                             "dst": {"id": 9, "name": "edge1", "kind": "device"}})
    assert ctx.output.lines == ["host-a to edge1 (device)"]


# ── the guide ────────────────────────────────────────────────────────────────────────────────

def test_every_path_the_developer_guide_names_exists():
    with open(GUIDE, encoding="utf-8") as fh:
        named = set(re.findall(r"`((?:modules|tests|docs|scripts)/[A-Za-z0-9_./-]+)`", fh.read()))
    assert len(named) >= 10, named                          # the floor: the guide names its files
    missing = sorted(p for p in named if not os.path.exists(os.path.join(ROOT, p.rstrip("/"))))
    assert missing == []
