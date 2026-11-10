"""The generic read-only read loop (board H, part H25's core; docs/HEAL_TO_INTENT.md 19.5, B4's
design 1.1 and 1.5; `modules/ai/read_loop.py`), on a planted read family and a fake gateway: no
provider, no device, no controller.

- **The family is declared, and only reads are declarable:** a planted write (an HTTP POST or
  DELETE, a CLI `clear`, a writing modifier, `dir`) is refused when the family is declared,
  each refusal's words asserted; so are a placeholder that is no argument, an optional argument
  in a template, an egress class no read goes out under, a limit past 3, two operations of one
  name, and a transport with no read rule. A feature whose second pass could ask again is
  refused too.
- **The check refuses each request outside the family's shapes**, naming the operation and the
  argument it compared: an unknown operation, an argument outside its shape (IPv4 and IPv6
  both), an extra key (in the request and in its arguments), a true/false value or a fraction
  as a number, a missing argument, a control character, a fourth read, a switch the scope does
  not list; and all of them when the family's egress class is off, or not built, naming it.
- **The allowed forms pass**, the runner handed exactly the rendered requests, and their
  answers reach pass 2 masked: a planted secret (a stored value and a secret's shapes) never
  reaches the fake gateway, its line or leaf dropped whole and counted.
- **The answer bound:** an answer past `AI_READ_CAP` is cut, saying so with the whole answer's
  size and hash, never past the bound and never through a character.
- **Pass 2's check:** a citation of a read that does not exist, or was refused, is refused
  (pass 1's answer stands, said); an answer acting on what only a read returned is refused.
- **The caps, through the real gateway** (only the provider faked): a day cap reached by pass 1
  stops pass 2, recorded, with no second request; and the planted secret is in no byte sent.
- **The counts:** at most two calls, none when pass 1 asks nothing; `CALLS_PER_FINDING` 2 in the
  estimate.
"""
import dataclasses
import hashlib
import json

import pytest

from modules import redact
from modules.ai import background, calls, egress_classes, schemas, triggers
from modules.ai import read_loop as RL
from modules.ai.schemas import StrictModel
from tests.test_ai_gateway import own_record, world  # noqa: F401 (fixtures)

DPID1, DPID2 = "0000000000000001", "0000000000000002"
#: A value the installation holds (planted in `redact.known_secret_values`).
SECRET = "Planted-Known-Secret-77x"
NETWORK = "lab"


# ── The planted family and feature ────────────────────────────────────────────────────────────

def _switch_listed(dpid, scope):
    listed = tuple(scope.get("switches") or ())
    if dpid not in listed:
        return (f"dpid {dpid} is not a switch the controller lists: it lists "
                f"{' and '.join(listed) or 'none'}")
    return ""


DPID = RL.Text(r"[0-9a-f]{16}", "a datapath id of 16 lower-case hex digits")
PORT = RL.Integer(1, 0xFFFFFF00, "an OpenFlow port number from 1 to 4294967040")
HOST = RL.AnyOf((RL.Mac(), RL.Address()), "a MAC or one IPv4 or IPv6 address")


class Runner:
    """The family's executor, faked: what each operation answers, and what it was handed."""

    def __init__(self, answers=None, raises=None):
        self.answers = answers or {}
        self.raises = raises or {}
        self.ran = []

    def __call__(self, op, args, requests, scope):
        self.ran.append({"op": op, "args": dict(args), "requests": list(requests)})
        if op in self.raises:
            raise self.raises[op]
        return self.answers.get(op, f"{op} answered")


def _family(run=None, **over) -> RL.ReadFamily:
    ops = (
        RL.Operation("topology", args={}, sends=(("GET", "/v1.0/topology/switches"),)),
        RL.Operation("switch_flows", args={"dpid": RL.Arg(DPID, against=_switch_listed),
                                           "host": RL.Arg(HOST, required=False)},
                     sends=(("GET", "/stats/flow/{dpid}"),)),
        RL.Operation("port_stats", args={"dpid": RL.Arg(DPID, against=_switch_listed),
                                         "port": RL.Arg(PORT, required=False)},
                     sends=(("GET", "/stats/port/{dpid}"),)),
    )
    spec = dict(name="planted", transport="http", egress_class="device_state",
                operations=ops, run=run or Runner())
    spec.update(over)
    return RL.ReadFamily(**spec)


FAMILY = _family()
Ask = RL.request_model(FAMILY)


class First(StrictModel):
    claim: str
    cites: list[str]
    source: str
    reads: list[Ask] = []


class Second(StrictModel):
    claim: str
    cites: list[str]
    source: str


class Plain(StrictModel):
    claim: str
    cites: list[str]
    source: str


PACK_IDS = ("pack:1", "pack:2")


def _feature_check(answer, *, read_ids):
    for ref in answer.cites:
        if ref not in PACK_IDS and ref not in read_ids:
            return f"the answer cites {ref}, which was not sent"
    return ""


def _feature(**over) -> RL.LoopFeature:
    spec = dict(task="connection_check", first=(("ping", 1), First),
                second=(("ping", 1), Second), plain=(("ping", 1), Plain),
                check=_feature_check, cites=lambda a: list(a.cites),
                acts_on=lambda a: [a.source] if a.source else [])
    spec.update(over)
    return RL.LoopFeature(**spec)


FEATURE = _feature()


class FakeGateway:
    """`gateway.ask`'s contract, faked: the answers in order, each validated by the schema it
    was asked with (as JSON, as the gateway validates), and every call kept whole."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def ask(self, task, prompt, schema, parts, **kw):
        self.calls.append(dict(kw, task=task, prompt=prompt, schema=schema, parts=dict(parts)))
        n = len(self.calls)
        item = self.answers.pop(0)
        if "error" in item:
            return {"ok": False, "error": item["error"], "detail": item.get("detail", ""),
                    "call_id": f"call-{n}"}
        return {"ok": True, "output": schema.model_validate_json(json.dumps(item)),
                "call_id": f"call-{n}", "cost_usd": 0.01}


def _ask(op, why="to see it", hypothesis="it shows the cause", **args):
    return {"op": op, "args": args, "why": why, "hypothesis": hypothesis}


def _first(*reads, cites=("pack:1",), source="192.0.2.5"):
    return {"claim": "a scan from 192.0.2.5", "cites": list(cites), "source": source,
            "reads": list(reads)}


def _second(cites=("pack:1", "read:1"), source="192.0.2.5"):
    return {"claim": "a scan, confirmed", "cites": list(cites), "source": source}


SCOPE = {"switches": (DPID1, DPID2)}


def _run(gw, family=None, feature=None, **kw):
    spec = dict(ask=gw.ask, network=NETWORK, data={"pack": "the pack"}, actor="job:j1",
                trigger={"kind": "background"}, scope=SCOPE, actable=("192.0.2.5",))
    spec.update(kw)
    return RL.run(family or _family(), feature or FEATURE, **spec)


@pytest.fixture(autouse=True)
def class_on(monkeypatch):
    """The device state class on for the planted network (H28 builds the real switch), and a
    stored secret the installation holds."""
    monkeypatch.setattr(egress_classes, "device_state_allowed",
                        lambda network: {"allowed": True, "why": ""}, raising=False)
    monkeypatch.setattr(redact, "known_secret_values", lambda: {SECRET: "template_secret"})


def _check(*reads, family=None, scope=SCOPE):
    return RL.check(family or FAMILY, list(reads), network=NETWORK, scope=scope)


# ── Declaration: only reads are declarable ────────────────────────────────────────────────────

@pytest.mark.parametrize("transport,sends,said", [
    ("http", (("POST", "/stats/flowentry/add"),),
     "the operation planted_write sends POST /stats/flowentry/add: a read family over http "
     "sends GET only"),
    ("http", (("DELETE", "/stats/flowentry/clear/{dpid}"),),
     "the operation planted_write sends DELETE /stats/flowentry/clear/{dpid}: a read family "
     "over http sends GET only"),
    ("http", (("get", "/stats/switches"),),
     "the operation planted_write sends get /stats/switches: a read family over http sends "
     "GET only"),
    ("http", (("GET", "http://192.0.2.9/stats/switches"),),
     "the operation planted_write sends GET http://192.0.2.9/stats/switches: a path is one "
     "on the controller, starting /, with no URL, space or query"),
    ("cli", ("clear ip bgp {dpid}",),
     "the operation planted_write sends 'clear ip bgp x', which is not a read: REFUSED:"),
    ("cli", ("show running-config | redirect flash:x",),
     "the operation planted_write sends 'show running-config | redirect flash:x', which is not "
     "a read: REFUSED: output modifier 'redirect' is not a filter. It WRITES"),
    ("cli", ("dir flash:",),
     "the operation planted_write sends 'dir flash:': a model's read is one of show, ping, "
     "traceroute, never dir"),
    ("cli", ("sh ver",),
     "the operation planted_write sends 'sh ver': a model's read is one of show, ping, "
     "traceroute, never sh"),
])
def test_a_planted_write_operation_is_refused_when_the_family_is_declared(transport, sends,
                                                                           said):
    write = RL.Operation("planted_write", args={"dpid": RL.Arg(DPID)}, sends=sends)
    with pytest.raises(RL.Undeclarable) as got:
        _family(transport=transport, operations=(write,))
    assert said in str(got.value)
    assert str(got.value).startswith("the planted read family cannot be declared: ")


@pytest.mark.parametrize("over,said", [
    ({"operations": (RL.Operation("flows", args={}, sends=(("GET", "/stats/flow/{dpid}"),)),)},
     "the operation flows's template names {dpid}, which is not one of its required "
     "arguments (none)"),
    ({"operations": (RL.Operation("flows", args={"dpid": RL.Arg(DPID, required=False)},
                                  sends=(("GET", "/stats/flow/{dpid}"),)),)},
     "the operation flows's template names {dpid}, which is not one of its required "
     "arguments (none)"),
    ({"operations": (RL.Operation("flows", args={}, sends=()),)},
     "the operation flows sends nothing: it names each request it sends"),
    ({"operations": ()}, "declares no operation"),
    ({"operations": (RL.Operation("topology", args={}, sends=(("GET", "/a"),)),
                     RL.Operation("topology", args={}, sends=(("GET", "/b"),)))},
     "declares the operation topology twice"),
    # Lab 9 B4 made topology a class (a kept SDN snapshot's) and seal a transport: the planted
    # class is one no read goes out under, and each list names every one there is.
    ({"egress_class": "netflow"},
     "its egress class 'netflow' is not one a read goes out under (configuration, "
     "device_state, topology)"),
    ({"limit": 4}, "its limit 4 is not 1 to 3, the most reads a pass may ask for"),
    ({"limit": True}, "its limit True is not 1 to 3, the most reads a pass may ask for"),
    ({"transport": "snmp"}, "its transport 'snmp' has no read rule (cli, http, seal)"),
    ({"run": "not callable"}, "its run is not callable"),
])
def test_a_family_out_of_shape_is_refused_when_declared(over, said):
    with pytest.raises(RL.Undeclarable) as got:
        _family(**over)
    assert said in str(got.value)


def test_an_operations_own_class_must_be_one_a_read_goes_out_under():
    op = RL.Operation("topology", args={}, sends=(("GET", "/a"),), egress_class="never")
    with pytest.raises(RL.Undeclarable) as got:
        _family(operations=(op,))
    assert ("the operation topology's egress class 'never' is not one a read goes out under"
            in str(got.value))


def test_a_feature_whose_second_pass_could_ask_again_is_refused():
    with pytest.raises(RL.Undeclarable) as got:
        _feature(second=(("ping", 1), First))
    assert "its second pass's schema First has a reads field: pass 2 cannot ask again" \
        in str(got.value)
    with pytest.raises(RL.Undeclarable) as got:
        _feature(first=(("ping", 1), Second))
    assert "its first pass's schema Second has no reads field" in str(got.value)
    with pytest.raises(RL.Undeclarable) as got:
        _feature(plain=(("ping", 1), First))
    assert "its plain pass's schema First has a reads field" in str(got.value)


# ── The check: each refusal, in its words ─────────────────────────────────────────────────────

@pytest.mark.parametrize("request_,said", [
    (_ask("delete_flows", dpid=DPID1),
     "'delete_flows' is not an operation of the planted read family (its operations: "
     "port_stats, switch_flows, topology)"),
    (_ask("switch_flows", dpid="0000-0000-0000-01"),
     "switch_flows's argument dpid: '0000-0000-0000-01' is not a datapath id of 16 lower-case "
     "hex digits"),
    (_ask("switch_flows", dpid=DPID1.upper().replace("0", "A")),
     "switch_flows's argument dpid: 'AAAAAAAAAAAAAAA1' is not a datapath id of 16 lower-case "
     "hex digits"),
    (_ask("switch_flows", dpid=1),
     "switch_flows's argument dpid: 1 is a number, not text (a datapath id of 16 lower-case "
     "hex digits)"),
    (_ask("switch_flows", dpid=DPID1, host="999.1.1.1"),
     "switch_flows's argument host: '999.1.1.1' is not a MAC or one IPv4 or IPv6 address"),
    (_ask("switch_flows", dpid=DPID1, host="2001:db8::5%eth0"),
     "switch_flows's argument host: '2001:db8::5%eth0' is not a MAC or one IPv4 or IPv6 "
     "address"),
    (_ask("switch_flows", dpid=DPID1, host="2001:db8::/64"),
     "switch_flows's argument host: '2001:db8::/64' is not a MAC or one IPv4 or IPv6 address"),
    (_ask("switch_flows", dpid=DPID1, table=0),
     "switch_flows takes no argument 'table' (it takes: dpid, host)"),
    (_ask("topology", dpid=DPID1), "topology takes no argument 'dpid' (it takes: none)"),
    (dict(_ask("topology"), command="show running-config"),
     "the request names 'command', which no read request has (its keys: op, args, why, "
     "hypothesis)"),
    (_ask("port_stats", dpid=DPID1, port=True),
     "port_stats's argument port: True is a true/false value, not a whole number "
     "(an OpenFlow port number from 1 to 4294967040)"),
    (_ask("port_stats", dpid=DPID1, port=1.0),
     "port_stats's argument port: 1.0 is not a whole number (an OpenFlow port number from 1 "
     "to 4294967040)"),
    (_ask("port_stats", dpid=DPID1, port="3"),
     "port_stats's argument port: '3' is text, not a whole number (an OpenFlow port number "
     "from 1 to 4294967040)"),
    (_ask("port_stats", dpid=DPID1, port=0xFFFFFFFE),
     "port_stats's argument port: 4294967294 is not an OpenFlow port number from 1 to "
     "4294967040"),
    (_ask("port_stats"), "port_stats needs its argument dpid (a datapath id of 16 lower-case "
     "hex digits)"),
    (_ask("port_stats", dpid="00000000000000ff"),
     "port_stats's argument dpid: dpid 00000000000000ff is not a switch the controller lists: "
     "it lists 0000000000000001 and 0000000000000002"),
    (_ask("topology", why="see\nshow running-config"),
     "the request's why holds a line break or control character"),
    (_ask("topology", hypothesis=""), "the request's hypothesis is empty"),
    (_ask("topology", why="x" * 201), "the request's why is 201 characters, over 200"),
    ({"op": "topology", "args": {}, "why": "w"},
     "the request has no hypothesis (its keys: op, args, why, hypothesis)"),
    (["topology"], "a read request is an object of op, args, why and hypothesis, not a list"),
    ({"op": "topology", "args": [DPID1], "why": "w", "hypothesis": "h"},
     "topology's args are an object of named arguments, not a list"),
])
def test_each_request_outside_the_shapes_is_refused_in_its_words(request_, said):
    (got,) = _check(request_)
    assert got["verdict"] == "refused", got
    assert said in got["reason"], got["reason"]
    assert got["id"] == "read:1"


def test_a_fourth_read_is_refused_past_the_limit_and_the_first_three_are_not():
    got = _check(*[_ask("topology")] * 4)
    assert [g["verdict"] for g in got] == ["allowed", "allowed", "allowed", "refused"]
    assert got[3]["reason"] == "past the 3 reads a pass may ask for"
    assert [g["id"] for g in got] == ["read:1", "read:2", "read:3", "read:4"]


def test_a_family_with_a_lower_limit_refuses_past_its_own():
    got = _check(_ask("topology"), _ask("topology"), family=_family(limit=1))
    assert [g["verdict"] for g in got] == ["allowed", "refused"]
    assert got[1]["reason"] == "past the 1 read a pass may ask for"


def test_every_read_is_refused_when_the_class_is_off_naming_it(monkeypatch):
    monkeypatch.setattr(egress_classes, "device_state_allowed",
                        lambda network: {"allowed": False,
                                         "why": "an admin has not turned it on"},
                        raising=False)
    got = _check(_ask("topology"), _ask("switch_flows", dpid=DPID1))
    assert [g["verdict"] for g in got] == ["refused", "refused"]
    for g in got:
        assert g["reason"] == ("the device state class is off for lab: an admin has not "
                               "turned it on")


def test_the_class_not_built_is_off_for_every_network(monkeypatch):
    monkeypatch.delattr(egress_classes, "device_state_allowed", raising=False)
    (got,) = _check(_ask("topology"))
    assert got["verdict"] == "refused"
    assert got["reason"] == ("the device state class is off for lab: it is not built yet "
                             "(egress_classes.device_state_allowed), so it is off for every "
                             "network")


def test_a_class_that_cannot_be_read_is_off(monkeypatch):
    def broken(network):
        raise OSError("settings unreadable")
    monkeypatch.setattr(egress_classes, "device_state_allowed", broken, raising=False)
    (got,) = _check(_ask("topology"))
    assert got["reason"] == ("the device state class is off for lab: it could not be read "
                             "(OSError), so it is off")


def test_a_classification_marking_refuses_every_read(monkeypatch):
    monkeypatch.setattr(egress_classes, "classification_marking", lambda network: "CUI")
    (got,) = _check(_ask("topology"))
    assert got["reason"] == ("lab carries the classification marking 'CUI', which forces AI "
                             "off: no read is sent")


@pytest.mark.parametrize("request_,requests,parsed", [
    (_ask("topology"), [("GET", "/v1.0/topology/switches")], {}),
    (_ask("switch_flows", dpid=DPID1), [("GET", f"/stats/flow/{DPID1}")], {"dpid": DPID1}),
    (_ask("switch_flows", dpid=DPID2, host="192.0.2.5"), [("GET", f"/stats/flow/{DPID2}")],
     {"dpid": DPID2, "host": "192.0.2.5"}),
    (_ask("switch_flows", dpid=DPID1, host="2001:DB8:8:0::5"), [("GET", f"/stats/flow/{DPID1}")],
     {"dpid": DPID1, "host": "2001:db8:8::5"}),
    (_ask("switch_flows", dpid=DPID1, host="0a:1b:2c:3d:4e:5f"),
     [("GET", f"/stats/flow/{DPID1}")], {"dpid": DPID1, "host": "0a:1b:2c:3d:4e:5f"}),
    (_ask("port_stats", dpid=DPID1, port=3), [("GET", f"/stats/port/{DPID1}")],
     {"dpid": DPID1, "port": 3}),
    # An optional argument the schema sends as null is absent, never a value.
    (_ask("port_stats", dpid=DPID1, port=None, host=None), [("GET", f"/stats/port/{DPID1}")],
     {"dpid": DPID1}),
], ids=["topology", "flows", "flows-ipv4-host", "flows-ipv6-host", "flows-mac-host",
        "port", "nulls-absent"])
def test_the_allowed_forms_pass_rendered_exactly(request_, requests, parsed):
    (got,) = _check(request_)
    assert got["verdict"] == "allowed", got.get("reason")
    assert got["requests"] == requests and got["args"] == parsed and got["reason"] == ""


def test_a_null_for_another_operations_argument_is_absent_but_a_value_is_refused():
    # The pass-1 schema's arguments object holds every operation's names (`request_model`),
    # so a model's null for one this operation does not take is no argument.
    (got,) = _check(_ask("topology", dpid=None))
    assert got["verdict"] == "allowed"


# ── The loop ──────────────────────────────────────────────────────────────────────────────────

def test_the_allowed_reads_run_and_reach_pass_2_and_the_refused_never_run():
    runner = Runner({"switch_flows": "table 0 priority 10 ipv4_src=192.0.2.5 packets 900",
                     "port_stats": "port 3 rx 5000 pps"})
    gw = FakeGateway(_first(_ask("switch_flows", dpid=DPID1, host="192.0.2.5"),
                            _ask("port_stats", dpid=DPID1, port=True),
                            _ask("port_stats", dpid=DPID2, port=3)),
                     _second(cites=("pack:1", "read:1", "read:3")))
    got = _run(gw, family=_family(run=runner))
    assert got["ok"] is True and got["pass"] == 2 and got["state"] == "answered", got
    assert [r["op"] for r in runner.ran] == ["switch_flows", "port_stats"]
    assert runner.ran[1]["requests"] == [("GET", f"/stats/port/{DPID2}")]
    assert [r["verdict"] for r in got["reads"]] == ["run", "refused", "run"]
    assert len(gw.calls) == 2
    first, second = gw.calls
    assert first["schema"] is First and second["schema"] is Second
    assert first["task"] == second["task"] == "connection_check"
    assert first["trigger"] == second["trigger"] == {"kind": "background"}
    assert "mercury_reads" not in first["parts"]
    sent = json.loads(second["parts"]["mercury_reads"])
    assert [s["id"] for s in sent] == ["read:1", "read:2", "read:3"]
    assert sent[0]["answer"] == "table 0 priority 10 ipv4_src=192.0.2.5 packets 900"
    assert sent[1]["verdict"] == "refused" and "answer" not in sent[1]
    assert "True is a true/false value" in sent[1]["reason"]
    assert second["parts"]["pack"] == "the pack"
    assert "read:<n>" in second["context"]["reads_format"]
    assert got["answer"].claim == "a scan, confirmed"
    assert got["call_ids"] == ["call-1", "call-2"] and got["cost_usd"] == pytest.approx(0.02)
    assert got["words"] == ("AI analysis: asked for 3 reads; 2 run, 1 refused; second pass "
                            "answered")


def test_a_planted_secret_in_a_reads_answer_never_reaches_the_gateway():
    text = "\n".join(["interface Gi4 up", f"username admin password 0 {SECRET}",
                      "enable secret 9 $9$abcdefghijk$LMNOPQRSTUVWXYZ012345",
                      "snmp-server community NotSoSecretComm RO",
                      f"description {SECRET}", "packets 900"])
    flows = {"flows": [{"match": {"ipv4_src": "192.0.2.5"}, "cookie": SECRET, "packets": 9}],
             "note": "key 1 md5 PlantedKeyValue9"}
    runner = Runner({"topology": text, "switch_flows": flows})
    gw = FakeGateway(_first(_ask("topology"), _ask("switch_flows", dpid=DPID1)), _second())
    got = _run(gw, family=_family(run=runner))
    sent = json.dumps([c["parts"] for c in gw.calls]) + json.dumps(got["reads"])
    for planted in (SECRET, "$9$abcdefghijk", "NotSoSecretComm", "PlantedKeyValue9"):
        assert planted not in sent, planted
    reads = {r["id"]: r for r in json.loads(gw.calls[1]["parts"]["mercury_reads"])}
    # A text answer: each line the mask changed is dropped whole and counted.
    assert reads["read:1"]["answer"].split("\n") == [
        "interface Gi4 up", "packets 900", "(4 lines withheld: a secret's shape)"]
    assert reads["read:1"]["withheld"] == 4
    # A structured answer: each leaf the mask changed is dropped whole and counted.
    body = json.loads(reads["read:2"]["answer"])
    assert body == {"flows": [{"cookie": RL.WITHHELD_LEAF, "match": {"ipv4_src": "192.0.2.5"},
                               "packets": 9}], "note": RL.WITHHELD_LEAF}
    assert reads["read:2"]["withheld"] == 2


def test_an_answer_past_the_bound_is_cut_saying_so_with_the_whole_answers_hash():
    line = "flow table 0 priority 10 é packets 900 bytes 1200\n"
    text = line * 200
    runner = Runner({"topology": text})
    gw = FakeGateway(_first(_ask("topology")), _second())
    got = _run(gw, family=_family(run=runner))
    (read,) = json.loads(gw.calls[1]["parts"]["mercury_reads"])
    answer = read["answer"]
    whole = text.encode("utf-8")
    assert len(answer.encode("utf-8")) <= RL.AI_READ_CAP == 4096
    assert read["cut"] is True and got["reads"][0]["cut"] is True
    shown = answer.rsplit("\n[cut:", 1)[0]
    assert text.startswith(shown) and shown.endswith("bytes 1200")
    assert answer.endswith(
        f"[cut: {len(shown.encode('utf-8'))} of {len(whole)} bytes shown; the whole answer's "
        f"sha256 {hashlib.sha256(whole).hexdigest()}]")
    assert read["bytes"] == len(whole)


def test_an_answer_within_the_bound_is_sent_whole():
    runner = Runner({"topology": "x" * 4000})
    gw = FakeGateway(_first(_ask("topology")), _second())
    _run(gw, family=_family(run=runner))
    (read,) = json.loads(gw.calls[1]["parts"]["mercury_reads"])
    assert read["answer"] == "x" * 4000 and read["cut"] is False


def test_a_cut_never_splits_a_character():
    runner = Runner({"topology": "é" * 5000})
    gw = FakeGateway(_first(_ask("topology")), _second())
    _run(gw, family=_family(run=runner))
    (read,) = json.loads(gw.calls[1]["parts"]["mercury_reads"])
    shown = read["answer"].rsplit("\n[cut:", 1)[0]
    assert set(shown) == {"é"} and len(read["answer"].encode("utf-8")) <= RL.AI_READ_CAP


def test_a_citation_of_a_read_that_does_not_exist_is_refused_in_pass_2s_check():
    gw = FakeGateway(_first(_ask("topology")), _second(cites=("pack:1", "read:9")))
    got = _run(gw)
    assert got["ok"] is True and got["pass"] == 1 and got["state"] == "first_pass"
    assert got["answer"].claim == "a scan from 192.0.2.5"
    assert got["second"]["why"] == ("the answer cites read:9, which is no read Mercury ran and "
                                    "sent (it sent read:1)")
    assert got["words"] == ("AI analysis: asked for 1 read; 1 run; second pass refused by "
                            "Mercury's check: the answer cites read:9, which is no read Mercury "
                            "ran and sent (it sent read:1); the first pass's answer is shown")


def test_a_citation_of_a_refused_read_is_refused():
    gw = FakeGateway(_first(_ask("topology"), _ask("port_stats", dpid=DPID1, port=True)),
                     _second(cites=("read:1", "read:2")))
    got = _run(gw)
    assert got["second"]["why"] == ("the answer cites read:2, which Mercury refused: nothing of "
                                    "it was run or sent")


def test_a_read_never_widens_what_may_be_acted_on():
    runner = Runner({"topology": "host 198.51.100.7 at 0000000000000002:4"})
    gw = FakeGateway(_first(_ask("topology")), _second(source="198.51.100.7"))
    got = _run(gw, family=_family(run=runner))
    assert got["pass"] == 1 and got["answer"].source == "192.0.2.5"
    assert got["second"]["why"] == ("the answer acts on 198.51.100.7, which is not one the "
                                    "finding names (192.0.2.5): a read never widens what may be "
                                    "acted on (198.51.100.7 is in read:1's answer)")


def test_pass_1_asking_for_nothing_is_the_whole_analysis_in_one_call():
    gw = FakeGateway(_first())
    got = _run(gw)
    assert len(gw.calls) == 1 and got["pass"] == 1 and got["state"] == "answered"
    assert got["reads"] == [] and got["words"] == ""


def test_no_read_run_means_no_second_pass():
    runner = Runner()
    gw = FakeGateway(_first(_ask("port_stats", dpid=DPID1, port=True),
                            _ask("topology", dpid=DPID1)))
    got = _run(gw, family=_family(run=runner))
    assert len(gw.calls) == 1 and runner.ran == [] and got["pass"] == 1
    assert got["words"] == ("AI analysis: asked for 2 reads; 2 refused; second pass not run: "
                            "no read was run")


def test_a_read_that_fails_is_said_sent_as_failed_and_not_citable():
    runner = Runner({"topology": "ok"}, raises={"port_stats": TimeoutError("no answer in 20 s")})
    gw = FakeGateway(_first(_ask("topology"), _ask("port_stats", dpid=DPID1)),
                     _second(cites=("read:2",)))
    got = _run(gw, family=_family(run=runner))
    assert [r["verdict"] for r in got["reads"]] == ["run", "failed"]
    assert got["reads"][1]["reason"] == "the read failed: TimeoutError: no answer in 20 s"
    assert got["second"]["why"] == ("the answer cites read:2, which failed: nothing of it was "
                                    "sent")


def test_pass_1_refused_by_its_check_runs_no_read():
    runner = Runner()
    gw = FakeGateway(_first(_ask("topology"), cites=("pack:9",)))
    got = _run(gw, family=_family(run=runner))
    assert got["ok"] is False and got["state"] == "refused_by_check"
    assert runner.ran == [] and len(gw.calls) == 1
    assert got["why"] == "the answer cites pack:9, which was not sent"


def test_pass_1_failing_at_the_gateway_is_said():
    gw = FakeGateway({"error": "feature_off", "detail": "heal_analysis is off for lab"})
    got = _run(gw)
    assert got["ok"] is False and got["state"] == "failed" and got["error"] == "feature_off"
    assert got["words"] == "AI analysis: not run: feature_off: heal_analysis is off for lab"


def test_with_the_class_off_pass_1_is_the_plain_call_and_says_why(monkeypatch):
    monkeypatch.setattr(egress_classes, "device_state_allowed",
                        lambda network: {"allowed": False, "why": "off by default"},
                        raising=False)
    gw = FakeGateway({"claim": "c", "cites": ["pack:1"], "source": "192.0.2.5"})
    got = _run(gw)
    assert gw.calls[0]["schema"] is Plain and len(gw.calls) == 1
    assert got["ok"] is True and got["pass"] == 1 and got["reads"] == []
    assert got["words"] == ("AI analysis: reads not asked: the device state class is off for "
                            "lab: off by default")


def test_with_the_class_off_and_no_plain_pass_every_read_is_refused_naming_it(monkeypatch):
    monkeypatch.setattr(egress_classes, "device_state_allowed",
                        lambda network: {"allowed": False, "why": "off by default"},
                        raising=False)
    runner = Runner()
    gw = FakeGateway(_first(_ask("topology")))
    got = _run(gw, family=_family(run=runner), feature=_feature(plain=None))
    assert gw.calls[0]["schema"] is First and runner.ran == [] and len(gw.calls) == 1
    assert got["reads"][0]["reason"] == "the device state class is off for lab: off by default"


@pytest.mark.parametrize("kind,detail,said", [
    ("over_cap", "today's spend $1.5000 plus $0.0000 reserved by 0 call(s) in flight plus this "
     "call's worst case $0.0003 is over the day cap $1.5000",
     "second pass not run: a cap is reached: today's spend $1.5000"),
    ("feature_cap", "the feature's day cap $1.0000 is reached",
     "second pass not run: this feature's cap is reached: the feature's day cap"),
    ("feature_off", "heal_analysis is off for lab",
     "second pass not run: feature_off: heal_analysis is off for lab"),
])
def test_pass_2_refused_at_the_gateway_keeps_pass_1s_answer_said(kind, detail, said):
    gw = FakeGateway(_first(_ask("topology")), {"error": kind, "detail": detail})
    got = _run(gw)
    assert got["ok"] is True and got["pass"] == 1 and got["state"] == "first_pass"
    assert got["answer"].claim == "a scan from 192.0.2.5"
    assert said in got["words"] and got["second"]["error"] == kind


# ── Through the real gateway: the day cap between the passes, and every byte sent ─────────────

@pytest.fixture
def registered(monkeypatch):
    """The planted schemas registered for the test alone (the registry restored after it)."""
    monkeypatch.setattr(schemas, "REGISTRY", dict(schemas.REGISTRY))
    for name, model in (("planted_read_first", First), ("planted_read_second", Second),
                        ("planted_read_plain", Plain)):
        schemas.REGISTRY[(name, 1)] = model
        monkeypatch.setattr(model, "__ai_schema__", (name, 1), raising=False)


RUN = "evaluation:planted-read-loop"


def _real(world, family, *answers):
    from modules.ai import gateway
    queue = list(answers)

    def send(body, key):
        world.sent.append({"bytes": json.dumps(body), "key": key, "body": body})
        world.answer = queue.pop(0)
        from modules.ai import anthropic_adapter as A
        return A.Reply(status=200, body=world.answer, attempts=1, latency_s=0.25)

    return RL.run(family, FEATURE, ask=gateway.ask, network=NETWORK, data={"pack": "the pack"},
                  actor=RUN, trigger=triggers.evaluation(RUN), scope=SCOPE,
                  actable=("192.0.2.5",), send=send)


def _body(answer, input_tokens=120):
    return {"content": [{"type": "text", "text": json.dumps(answer)}], "stop_reason": "end_turn",
            "usage": {"input_tokens": input_tokens, "output_tokens": 8}}


def test_the_day_cap_reached_by_pass_1_stops_pass_2_recorded_with_no_second_request(
        world, registered):
    # Pass 1's own cost takes the day past its cap ($1.50): 20M input tokens at Haiku's $0.10.
    family = _family(run=Runner({"topology": "switches 2"}))
    got = _real(world, family, _body(_first(_ask("topology")), input_tokens=20_000_000))
    assert len(world.sent) == 1, "no second request"
    assert got["ok"] is True and got["pass"] == 1 and got["state"] == "first_pass"
    assert got["second"]["error"] == "over_cap"
    assert "over the day cap $1.5000" in got["second"]["detail"]
    assert got["words"].startswith("AI analysis: asked for 1 read; 1 run; second pass not run: "
                                   "a cap is reached: today's spend $")
    rows = [r for r in calls.read()["rows"] if "verdict" in r]
    assert sorted((r["schema"], r["verdict"]) for r in rows) == [
        ("planted_read_first.v1", "ok"), ("planted_read_second.v1", "over_cap")]


def test_through_the_real_gateway_the_planted_secret_is_in_no_byte_sent(world, registered):
    text = f"interface Gi4 up\nusername admin password 0 {SECRET}\ndescription {SECRET}"
    family = _family(run=Runner({"topology": text}))
    got = _real(world, family, _body(_first(_ask("topology"))), _body(_second()))
    assert got["ok"] is True and got["pass"] == 2 and len(world.sent) == 2
    assert all(SECRET not in s["bytes"] for s in world.sent)
    assert "interface Gi4 up" in world.sent[1]["bytes"]
    assert "mercury_reads" in world.sent[1]["bytes"]


# ── The counts ────────────────────────────────────────────────────────────────────────────────

def test_the_loop_counts_two_calls_a_finding_in_the_estimate():
    assert RL.CALLS_PER_FINDING == 2
    spec = RL.estimate_spec({"task": "heal_analysis", "calls_per_finding": 1, "words": "w"})
    assert spec["calls_per_finding"] == 2 and spec["task"] == "heal_analysis"


def test_the_estimate_doubles_with_the_loops_two_calls(monkeypatch):
    # `background.estimate`'s calls a day are the trigger's frequency times its calls a
    # finding: a feature declared through `estimate_spec` is estimated at two calls.
    from modules.nsot import listref
    monkeypatch.setattr(listref, "network_id", lambda network: network)
    monkeypatch.setattr(background, "measured_cost", lambda task, now=None: {
        "usd_per_call": 0.03, "calls": 4, "measured": True, "basis": "planted"})
    monkeypatch.setitem(background.FEATURES, "planted_loop", RL.estimate_spec({
        "task": "connection_check", "words": "w", "trigger_words": "t",
        "findings": ("detection",), "calls_per_finding": 1,
        "frequency": lambda network: {"per_day": 5.0, "basis": "planted"}}))
    est = background.estimate(NETWORK, "planted_loop")
    assert est["calls_per_finding"] == 2 and est["calls_per_day"] == 10.0
    assert est["usd_per_day"] == pytest.approx(0.30)


def test_the_pass_1_schema_lists_the_familys_operations_and_arguments():
    sent = schemas.schema_for(First)
    text = json.dumps(sent)
    for name in ("topology", "switch_flows", "port_stats", "dpid", "host", "port"):
        assert f'"{name}"' in text
    # No count bound on reads in the schema: a fourth is the check's refusal, said, not the
    # whole answer's.
    assert "maxItems" not in text


def test_a_family_is_frozen_once_declared():
    with pytest.raises(dataclasses.FrozenInstanceError):
        FAMILY.limit = 9
    assert isinstance(FAMILY.operations, tuple)


def test_an_unknown_argument_type_in_the_schema_is_not_taken():
    # The arguments object takes text, a number or true/false: never a list or an object.
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        First.model_validate_json(json.dumps(_first(_ask("topology", dpid=[DPID1]))))


def test_the_ids_are_read_n_in_the_order_asked():
    got = _check(_ask("topology"), _ask("nope"), _ask("topology"))
    assert [g["id"] for g in got] == ["read:1", "read:2", "read:3"]
    assert RL.READ_ID.fullmatch("read:3") and not RL.READ_ID.fullmatch("read:03")


def test_every_argument_is_optional_in_the_schema_and_required_by_the_check():
    # The arguments object holds every operation's names, each optional (null by default), so
    # an argument a request lacks is the check's refusal, in words, never the whole answer's.
    field = Ask.model_fields["args"].annotation.model_fields["dpid"]
    assert field.default is None and not field.is_required()
    answer = First.model_validate_json(json.dumps(_first(_ask("port_stats"))))
    (got,) = _check(answer.model_dump(mode="json")["reads"][0])
    assert got["reason"].startswith("port_stats needs its argument dpid")
