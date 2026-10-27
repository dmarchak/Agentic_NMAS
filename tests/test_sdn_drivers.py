"""The SDN controller driver interface and its registry (PHASE8_PLAN 17.2, item S1), through a
fake HTTP layer (tests/sdn_fakes.py), no network.

- **The registry:** every kind the plan names, each with its status; every declaration valid
  (capabilities a subset of the seven, a not-built driver declaring none); `make` refuses an
  unknown kind naming the kinds there are.
- **A driver not built** refuses every call, naming that it is not built and its status.
- **A capability not declared** refuses its calls and their render twins, naming it and why
  the driver lacks it; nothing is sent.
- **Every call answers and never raises**, whatever it is given and whatever its hook or the
  HTTP layer raises.
- **The bound:** one deadline per call, the connection's timeout, across the connect, each
  retry and the body's reading; a read retried after a connection error or a 502/503/504 while
  the deadline allows, a write never; an answer past MAX_BODY_BYTES refused, never cut.
- **The connection:** http and https, an IPv4 and an IPv6 literal host (bracketed), a path
  prefix; a user part, a query, another scheme, an unbracketed IPv6 address and a timeout out
  of bounds refused, naming why.
- **Credentials:** resolved by the callable at each request (basic or bearer), never on the
  driver, its session or its connection's repr, never in an answer (an exception's words, a
  controller's echo, a TLS error) and never in a log record.
- **Specs:** a flow or meter refused before anything is sent, naming each problem (a non-OXM
  match key, a boolean or null anywhere, an unknown action, an instruction inside
  WRITE_ACTIONS, a rate unit missing or doubled); `parse_dpid`'s forms.
- **Render and send are one path:** `apply` sends exactly the render's body text, byte for
  byte, and the digest is of what was sent.
"""
import json
import logging

import pytest
import requests

from modules.sdn import drivers
from modules.sdn.drivers import base
from modules.sdn.drivers.base import Connection, ControllerDriver, SpecError
from modules.sdn.drivers.ryu import RyuDriver
from tests.sdn_fakes import Clock, Response, Session

SECRET = "planted-controller-secret-7f3a9"
TOKEN = "planted-controller-token-c41e8"
DROP = {"priority": 100, "cookie": 7, "hard_timeout": 300,
        "match": {"eth_type": 2048, "ipv4_src": "192.0.2.3"}, "actions": []}
METER = {"meter_id": 1, "flags": ["KBPS"], "bands": [{"type": "DROP", "rate": 1000}]}

#: Every public call, with arguments that are well formed.
CALLS = {
    "test": (), "switches": (), "switch_desc": (1,), "links": (), "flows": (1,),
    "port_stats": (1,), "meters": (1,), "meter_features": (1,),
    "add_flow": (1, DROP), "render_add_flow": (1, DROP),
    "delete_flow_strict": (1, DROP), "render_delete_flow_strict": (1, DROP),
    "add_meter": (1, METER), "render_add_meter": (1, METER),
    "delete_meter": (1, {"meter_id": 1}), "render_delete_meter": (1, {"meter_id": 1}),
}


def ryu(session=None, url="http://127.0.0.1:8080", **kw):
    clock = kw.pop("clock", Clock())
    sleep = kw.pop("sleep", lambda s: None)
    return RyuDriver(Connection(url, **kw), session=session or Session(), clock=clock,
                     sleep=sleep)


# ───────────────────────────────────────────────────────────────────────────── the registry

def test_the_registry_holds_every_kind_the_plan_names_with_its_status():
    status = {kind: (cls.status, cls.read_first) for kind, cls in drivers.DRIVERS.items()}
    assert status == {
        "ryu": ("built", False), "onos": ("later", False),
        "opendaylight": ("later", True), "aci": ("later", True), "nsx": ("later", True),
        "apstra": ("later", True), "cloudvision": ("later", True),
        "floodlight": ("unmaintained", False)}


@pytest.mark.parametrize("kind", sorted(drivers.DRIVERS))
def test_every_declaration_is_valid(kind):
    cls = drivers.DRIVERS[kind]
    assert cls.kind == kind and cls.declaration_problems() == []
    assert cls.capabilities <= base.CAPABILITIES


def test_a_declaration_out_of_bounds_is_named():
    class Bad(ControllerDriver):
        kind, label, status = "bad", "Bad", "later"
        capabilities = frozenset({"read_flows", "fly"})
        read_first = True
        absent = {"read_flows": "x"}
    problems = Bad.declaration_problems()
    assert any("is not a frozenset of" in p for p in problems)
    assert "bad is later, so it declares no capability" in problems
    assert "bad: declares as absent what it declares" in problems
    class Worse(ControllerDriver):
        status = "someday"
        read_first = True
    problems = Worse.declaration_problems()
    assert "Worse names no kind or label" in problems
    assert any("status 'someday' is not one of" in p for p in problems)
    assert ": read_first is a later driver's" in problems


def test_ryu_declares_what_ofctl_rest_offers_and_says_why_topology_is_absent():
    assert RyuDriver.capabilities == frozenset({
        "read_flows", "read_port_stats", "read_meters", "write_flows", "write_meters",
        "delete_flows"})
    assert "read_topology" not in RyuDriver.capabilities
    assert "--observe-links" in RyuDriver.absent["read_topology"]


def test_make_answers_a_driver_or_names_the_kinds_there_are():
    made = drivers.make("ryu", Connection("http://127.0.0.1:8080"))
    assert made["ok"] and isinstance(made["driver"], RyuDriver)
    refused = drivers.make("pox", Connection("http://127.0.0.1:8080"))
    assert refused == {"ok": False, "error": "there is no controller driver of kind 'pox'; "
                       "the kinds are aci, apstra, cloudvision, floodlight, nsx, onos, "
                       "opendaylight, ryu"}


def test_declarations_lead_with_the_built_driver():
    out = drivers.declarations()
    assert out[0]["kind"] == "ryu" and out[0]["status"] == "built"
    assert {d["kind"] for d in out} == set(drivers.DRIVERS)
    assert all(d["capabilities"] == [] for d in out[1:])


def test_every_public_call_is_gated_and_no_driver_overrides_one():
    """A call outside CALL_CAPABILITY would skip the gate; a driver overriding a public call
    would skip the bound and the never-raise wrapper."""
    public = {n for n, v in vars(ControllerDriver).items()
              if callable(v) and not n.startswith("_")
              and n not in ("apply", "declaration", "declaration_problems")}
    assert public == set(base.CALL_CAPABILITY) == set(CALLS)
    for cls in drivers.DRIVERS.values():
        for klass in cls.__mro__:
            if klass is ControllerDriver or klass is object:
                break
            assert not public & set(vars(klass)), (cls.kind, public & set(vars(klass)))


# ───────────────────────────────────────────────────────────────────────────── refusals

@pytest.mark.parametrize("kind", [k for k, c in drivers.DRIVERS.items() if c.status != "built"])
@pytest.mark.parametrize("call", sorted(CALLS))
def test_a_driver_not_built_refuses_every_call_naming_it(kind, call):
    session = Session()
    driver = drivers.DRIVERS[kind](Connection("http://127.0.0.1:8080"), session=session)
    out = getattr(driver, call)(*CALLS[call])
    cls = drivers.DRIVERS[kind]
    name = f"render_{call}" if call.startswith(("add_", "delete_")) else call
    assert out == {"ok": False, "refused": True,
                   "error": f"the {cls.label} driver is not built (status: {cls.status}), so "
                            f"{name} is not available"}
    assert session.sent == []


def test_ryu_refuses_links_naming_the_capability_and_why():
    session = Session()
    out = ryu(session).links()
    assert out == {"ok": False, "refused": True, "error": (
        "Ryu does not declare read_topology, so links is refused: Ryu's ofctl_rest has no "
        "links call; its topology REST (ryu.app.rest_topology, run with --observe-links) is "
        "a separate application this driver does not read")}
    assert session.sent == []


class _ReadOnly(RyuDriver):
    """Ryu's calls, declaring only its reads: its writes must refuse."""
    kind, label = "readonly", "Read-only"
    capabilities = frozenset({"read_flows", "read_port_stats", "read_meters"})


@pytest.mark.parametrize("call,capability", [
    ("add_flow", "write_flows"), ("render_add_flow", "write_flows"),
    ("delete_flow_strict", "delete_flows"), ("render_delete_flow_strict", "delete_flows"),
    ("add_meter", "write_meters"), ("render_add_meter", "write_meters"),
    ("delete_meter", "write_meters"), ("render_delete_meter", "write_meters")])
def test_a_write_not_declared_is_refused_and_nothing_is_sent(call, capability):
    session = Session()
    driver = _ReadOnly(Connection("http://127.0.0.1:8080"), session=session)
    out = getattr(driver, call)(*CALLS[call])
    name = call if call.startswith("render_") else f"render_{call}"
    assert out == {"ok": False, "refused": True,
                   "error": f"Read-only does not declare {capability}, so {name} is refused"}
    assert session.sent == []


def test_apply_refuses_a_route_or_capability_the_driver_does_not_have():
    session = Session()
    rendered = ryu().render_add_flow(1, DROP)
    readonly = _ReadOnly(Connection("http://127.0.0.1:8080"), session=session)
    assert readonly.apply(rendered) == {
        "ok": False, "refused": True,
        "error": "Read-only does not declare write_flows, so apply is refused"}
    forged = dict(rendered, path="/stats/flowentry/clear/1", method="DELETE")
    assert ryu(session).apply(forged) == {
        "ok": False, "error": "Ryu has no write DELETE /stats/flowentry/clear/1"}
    assert ryu(session).apply({"ok": False, "error": "x"})["ok"] is False
    assert ryu(session).apply(dict(rendered, body={"dpid": 1}))["error"] == (
        "a rendered body is the exact text to send")
    assert session.sent == []


# ───────────────────────────────────────────────────────────────────────────── never raises

class _Raising(RyuDriver):
    def _flows(self, dpid):
        raise RuntimeError("the hook fell over")


def test_a_hook_that_raises_is_answered_never_raised(caplog):
    with caplog.at_level(logging.WARNING, logger="modules.sdn.drivers.base"):
        out = _Raising(Connection("http://127.0.0.1:8080"), session=Session()).flows(1)
    assert out == {"ok": False, "error": "flows failed: RuntimeError: the hook fell over"}
    assert "sdn ryu: flows failed: RuntimeError" in caplog.text


@pytest.mark.parametrize("raised", [KeyError("k"), ZeroDivisionError(), TypeError("t"),
                                    ValueError("v"), RecursionError()])
@pytest.mark.parametrize("call", sorted(CALLS))
def test_whatever_the_http_layer_raises_every_call_answers(raised, call):
    driver = ryu(Session(*[raised] * 3))
    out = getattr(driver, call)(*CALLS[call])
    assert isinstance(out, dict) and isinstance(out["ok"], bool) and "error" in out


@pytest.mark.parametrize("call", sorted(CALLS))
@pytest.mark.parametrize("args", [(None,), ("ninety",), (True,), ({},), (1, None), (1, 5),
                                  (1, {"nonsense": 1}), (2 ** 64,), (0,)])
def test_garbage_arguments_are_answered(call, args):
    args = (args + CALLS[call])[:len(CALLS[call])]
    out = getattr(ryu(Session(*[Response(200, "{}")] * 3)), call)(*args)
    assert isinstance(out, dict) and isinstance(out["ok"], bool) and isinstance(out["error"],
                                                                                 str)


def test_a_connection_that_is_not_one_is_answered():
    out = RyuDriver(None, session=Session()).flows(1)
    assert out == {"ok": False, "refused": True,
                   "error": "no controller connection was given (got NoneType)"}


def test_a_hook_answering_no_result_is_said():
    class Mute(RyuDriver):
        def _flows(self, dpid):
            return None
    out = Mute(Connection("http://127.0.0.1:8080"), session=Session()).flows(1)
    assert out == {"ok": False, "error": "Ryu's flows answered no result"}


# ───────────────────────────────────────────────────────────────────────────── the bound

def test_the_whole_call_is_bounded_by_the_connection_timeout():
    session = Session(requests.exceptions.Timeout("read timed out"))
    out = ryu(session, timeout=5).switches()
    assert out == {"ok": False, "error": "no answer within 5 s", "timeout": True, "attempts": 1}
    (sent,) = session.sent
    assert sent["timeout"] == (5.0, 5.0) and sent["stream"] is True
    assert sent["allow_redirects"] is False


def test_a_body_still_arriving_at_the_deadline_is_a_timeout_not_a_partial_read():
    clock = Clock()

    def tick():
        clock.now += 2.0

    trickle = Response(200, chunks=[b"[1", b", 2", b", 3", b"]"], on_chunk=tick)
    out = ryu(Session(trickle), timeout=5, clock=clock).switches()
    assert out["ok"] is False and out["error"] == "no answer within 5 s"
    assert trickle.closed


def test_a_read_is_retried_within_the_deadline_and_a_write_never():
    slept = []
    session = Session(requests.exceptions.ConnectionError("refused"),
                      Response(503, ""), Response(200, "[1]"))
    out = ryu(session, sleep=slept.append).switches()
    assert out["ok"] and len(session.sent) == 3 and slept == [base.RETRY_PAUSE] * 2
    session = Session(requests.exceptions.ConnectionError("refused"))
    out = ryu(session, sleep=slept.append).add_flow(1, DROP)
    assert len(session.sent) == 1
    assert out["error"] == "could not connect to http://127.0.0.1:8080"


def test_no_retry_when_the_deadline_leaves_no_room():
    clock = Clock()
    session = Session(lambda req: (setattr(clock, "now", clock.now + 4.9),
                                   requests.exceptions.ConnectionError("x"))[1])
    out = ryu(session, timeout=5, clock=clock).switches()
    assert len(session.sent) == 1 and out["attempts"] == 1


def test_each_retry_gets_only_what_is_left_of_the_deadline():
    clock = Clock()

    def slow_failure(request):
        clock.now += 2.0
        return requests.exceptions.ConnectionError("x")

    session = Session(slow_failure, Response(200, "[]"))
    assert ryu(session, timeout=5, clock=clock).switches()["ok"]
    assert session.sent[0]["timeout"] == (5.0, 5.0)
    assert session.sent[1]["timeout"] == (3.0, 3.0)


def test_an_answer_past_the_size_bound_is_refused_not_cut(monkeypatch):
    monkeypatch.setattr(base, "MAX_BODY_BYTES", 8)
    out = ryu(Session(Response(200, chunks=[b"[1, 2, 3", b", 4]"]))).switches()
    assert out["ok"] is False
    assert out["error"] == "the answer is larger than 8 bytes, so it was not read"


def test_a_redirect_is_not_followed_and_names_where():
    out = ryu(Session(Response(302, "", headers={"Location": "https://elsewhere/"}))).switches()
    assert out["ok"] is False and out["status"] == 302
    assert "redirect (to https://elsewhere/)" in out["error"]


def test_a_tls_failure_says_so():
    out = ryu(Session(requests.exceptions.SSLError("certificate verify failed")),
              url="https://192.0.2.10:8443").switches()
    assert out["ok"] is False and out["error"].startswith("TLS error: ")


@pytest.mark.parametrize("verify", [True, False])
def test_the_connection_says_whether_tls_is_verified(verify):
    session = Session(Response(200, "[]"))
    ryu(session, url="https://192.0.2.10:8443", verify_tls=verify).switches()
    assert session.sent[0]["verify"] is verify


# ───────────────────────────────────────────────────────────────────────────── the connection

@pytest.mark.parametrize("url,sent", [
    ("http://192.0.2.10:8080", "http://192.0.2.10:8080/stats/switches"),
    ("http://[2001:db8::10]:8080", "http://[2001:db8::10]:8080/stats/switches"),
    ("http://[::1]:8080/", "http://[::1]:8080/stats/switches"),
    ("https://controller.example:8443/ryu", "https://controller.example:8443/ryu/stats/switches"),
])
def test_ipv4_ipv6_and_named_hosts_each_reach_their_url(url, sent):
    session = Session(Response(200, "[]"))
    assert ryu(session, url=url).switches()["ok"]
    assert session.sent[0]["url"] == sent


@pytest.mark.parametrize("url,words", [
    ("", "the controller's URL is not set"),
    ("ftp://192.0.2.10", "the controller's URL must be http or https, not 'ftp'"),
    ("http://", "the controller's URL names no host"),
    ("http://2001:db8::10:8080", "the controller's URL is not a URL"),
    ("http://admin:pw@192.0.2.10:8080", "the controller's URL carries a user part"),
    ("http://[2001:db8::10]:8080/?x=1", "the controller's URL carries a query or a fragment"),
])
def test_a_connection_that_cannot_be_used_is_refused_naming_why(url, words):
    session = Session()
    out = ryu(session, url=url).switches()
    assert out["ok"] is False and out["error"].startswith(words)
    assert session.sent == []


@pytest.mark.parametrize("timeout", [0, -1, 121, "5", True, None])
def test_a_timeout_out_of_bounds_is_refused(timeout):
    out = ryu(timeout=timeout).switches()
    assert out["ok"] is False
    assert out["error"].startswith("the connection's timeout must be more than 0 and at most "
                                   "120 seconds")


# ───────────────────────────────────────────────────────────────────────────── credentials

def _creds(**values):
    calls = []

    def resolve():
        calls.append(1)
        return dict(values)
    resolve.calls = calls
    return resolve


def test_basic_credentials_are_resolved_at_each_request_and_sent():
    resolve = _creds(username="mercury", password=SECRET)
    session = Session(Response(200, "[]"), Response(200, "[]"))
    driver = ryu(session, credentials=resolve)
    driver.switches()
    driver.switches()
    assert [s["auth"] for s in session.sent] == [("mercury", SECRET)] * 2
    assert all("Authorization" not in s["headers"] for s in session.sent)
    assert len(resolve.calls) >= 2


def test_a_token_is_sent_as_a_bearer_header():
    session = Session(Response(200, "[]"))
    ryu(session, credentials=_creds(token=TOKEN)).switches()
    assert session.sent[0]["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert session.sent[0]["auth"] is None


class _Echo(RyuDriver):
    """A hook whose exception carries the secret, as a client library's error may."""

    def _switch_desc(self, dpid):
        raise RuntimeError(f"login as mercury:{SECRET} refused")


#: Each way a credential could come back: (the answer the controller gives, the call, where in
#: the answer it would land, what is there instead). The 401's echo is never returned at all
#: (the driver's own words name a refused credential), so it holds even with no scrub.
LEAK_PATHS = {
    "a 500's traceback": (
        Response(500, f"Traceback (most recent call last):\nKeyError: '{SECRET}'",
                 content_type="text/plain"),
        "flows", ("detail",), "KeyError: '<redacted>'"),
    "a 401 echoing the header": (
        Response(401, f"Authorization: Bearer {TOKEN}", content_type="text/plain"),
        "flows", ("error",), "HTTP 401: the controller refused the tool's credential"),
    "a TLS error's words": (
        requests.exceptions.SSLError(f"handshake with {TOKEN} failed"),
        "flows", ("error",), "TLS error: handshake with <redacted> failed"),
    "a 200's data": (
        Response(200, json.dumps({"1": {"mfr_desc": SECRET}})),
        "switch_desc", ("desc", "mfr_desc"), "<redacted>"),
    "a hook's exception": (
        None, "switch_desc", ("error",),
        "switch_desc failed: RuntimeError: login as mercury:<redacted> refused"),
}


@pytest.mark.parametrize("path", sorted(LEAK_PATHS))
def test_no_credential_reaches_an_answer_or_a_log(path, caplog):
    answer, call, where, instead = LEAK_PATHS[path]
    creds = _creds(username="mercury", password=SECRET, token=TOKEN)
    session = Session(answer)
    cls = _Echo if answer is None else RyuDriver
    with caplog.at_level(logging.DEBUG):
        out = getattr(cls(Connection("http://127.0.0.1:8080", credentials=creds),
                          session=session, clock=Clock()), call)(1)
    if answer is not None:
        assert session.sent[0]["headers"]["Authorization"] == f"Bearer {TOKEN}"
    value = out
    for key in where:
        value = value[key]
    assert value == instead
    assert SECRET not in json.dumps(out) and TOKEN not in json.dumps(out)
    assert SECRET not in caplog.text and TOKEN not in caplog.text


def test_the_driver_keeps_no_credential():
    """The driver keeps nothing resolved (the fake session it was given is the test's record
    of what was sent, so it is left out), and a session the driver builds itself holds none
    either: each request carries its own."""
    creds = _creds(username="mercury", password=SECRET, token=TOKEN)
    driver = ryu(Session(Response(200, "[]")), credentials=creds)
    assert driver.switches()["ok"]
    held = {k: v for k, v in vars(driver).items() if k != "_session_given"}
    built = RyuDriver(Connection("http://127.0.0.1:8080", credentials=creds))
    text = (repr(held) + repr(driver) + repr(driver.connection)
            + repr(vars(built._session())))
    assert SECRET not in text and TOKEN not in text


def test_credentials_that_cannot_be_read_refuse_the_call():
    def broken():
        raise OSError(f"store unreadable near {SECRET}")
    session = Session()
    out = ryu(session, credentials=broken).switches()
    assert out == {"ok": False,
                   "error": "the controller's credentials could not be read (OSError)"}
    assert session.sent == []


# ───────────────────────────────────────────────────────────────────────────── specs

@pytest.mark.parametrize("value,dpid", [
    (1, 1), (0x1A, 26), ("0x1a", 26), ("000000000000001a", 26),
    ("00:00:00:00:00:00:00:1a", 26), (2 ** 64 - 1, 2 ** 64 - 1)])
def test_a_datapath_id_in_each_form(value, dpid):
    assert base.parse_dpid(value) == dpid


@pytest.mark.parametrize("value", [0, 2 ** 64, -1, "26", "1a", True, None, 1.0,
                                   "00:00:00:1a", "zz00000000000000"])
def test_a_datapath_id_refused_in_words(value):
    with pytest.raises(SpecError):
        base.parse_dpid(value)


def test_dpid_hex():
    assert base.dpid_hex(26) == "000000000000001a"


@pytest.mark.parametrize("spec,words", [
    ({"match": {"nw_src": "192.0.2.1"}}, "'nw_src' is not an OpenFlow 1.3 OXM field name"),
    ({"match": {"tp_dst": 22}}, "'tp_dst' is not an OpenFlow 1.3 OXM field name"),
    ({"match": {"in_port": True}}, "match field in_port must be a number or a string"),
    ({"match": {"in_port": None}}, "match field in_port must be a number or a string"),
    ({"match": {"ipv6_src": ["2001:db8::1"]}}, "match field ipv6_src must be a number"),
    ({"actions": [{"type": "OUTPUT", "port": True}]}, "OUTPUT's port must be a number"),
    ({"actions": [{"type": "OUTPUT", "port": "SOMEWHERE"}]}, "'SOMEWHERE' is not a port"),
    ({"actions": [{"type": "OUTPUT"}]}, "OUTPUT carries ['port'], not []"),
    ({"actions": [{"type": "DROP"}]}, "'DROP' is not an action this interface can send"),
    ({"actions": [{"type": "UNPARSED", "text": "EXPERIMENTER: {}"}]},
     "'UNPARSED' is not an action this interface can send (read back as the controller's "
     "'EXPERIMENTER: {}')"),
    ({"actions": [{"type": "WRITE_ACTIONS", "actions": [{"type": "GOTO_TABLE",
                                                         "table_id": 1}]}]},
     "WRITE_ACTIONS holds actions, not the instruction GOTO_TABLE"),
    ({"actions": [{"type": "SET_FIELD", "field": "dl_dst", "value": "x"}]},
     "SET_FIELD's 'dl_dst' is not an OpenFlow 1.3 OXM field name"),
    ({"actions": [{"type": "METER", "meter_id": False}]}, "METER's meter_id must be a whole"),
    ({"actions": "OUTPUT:2"}, "actions are a list, not a str"),
    ({"priority": 70000}, "priority must be a whole number from 0 to 65535, not 70000"),
    ({"hard_timeout": True}, "hard_timeout must be a whole number from 0 to 65535, not True"),
    ({"table_id": 255}, "table_id must be a whole number from 0 to 254, not 255"),
    ({"cookie": 2 ** 64}, "cookie must be a whole number from 0 to 18446744073709551615"),
    ({"dpid": 2}, "the spec names switch 2, the call switch 1"),
    ({"flags": 1}, "a flow has no field flags"),
])
def test_a_flow_spec_is_refused_before_anything_is_sent(spec, words):
    session = Session()
    out = ryu(session).add_flow(1, spec)
    assert out["ok"] is False and words in out["error"], out
    assert session.sent == []


@pytest.mark.parametrize("spec,words", [
    ({"meter_id": 1, "flags": ["KBPS", "PKTPS"], "bands": [{"type": "DROP", "rate": 1}]},
     "exactly one rate unit"),
    ({"meter_id": 1, "flags": ["BURST"], "bands": [{"type": "DROP", "rate": 1}]},
     "exactly one rate unit"),
    ({"meter_id": 1, "flags": ["KBPS", "FAST"], "bands": [{"type": "DROP", "rate": 1}]},
     "a meter's flags are from KBPS, PKTPS, BURST, STATS"),
    ({"meter_id": 1, "flags": ["KBPS"], "bands": []}, "a meter has at least one band"),
    ({"meter_id": 1, "flags": ["KBPS"], "bands": [{"type": "REMARK", "rate": 1}]},
     "a band's type is DROP or DSCP_REMARK, not 'REMARK'"),
    ({"meter_id": 1, "flags": ["KBPS"], "bands": [{"type": "DROP", "rate": 0}]},
     "a band's rate must be a whole number from 1"),
    ({"meter_id": 1, "flags": ["KBPS"], "bands": [{"type": "DSCP_REMARK", "rate": 5}]},
     "a DSCP remark's prec_level must be a whole number"),
    ({"meter_id": 0, "flags": ["KBPS"], "bands": [{"type": "DROP", "rate": 1}]},
     "meter_id must be a whole number from 1 to 4294901760, not 0"),
    ({"flags": ["KBPS"]}, "a meter spec names its meter_id"),
])
def test_a_meter_spec_is_refused_before_anything_is_sent(spec, words):
    session = Session()
    out = ryu(session).add_meter(1, spec)
    assert out["ok"] is False and words in out["error"], out
    assert session.sent == []


def test_a_flow_spec_may_be_a_flow():
    flow = base.Flow(dpid=1, priority=100, match={"eth_type": 2048}, actions=[])
    assert ryu().render_add_flow(1, flow)["ok"]
    assert flow.drops and not base.Flow(dpid=1, actions=[{"type": "OUTPUT", "port": 1}]).drops


# ───────────────────────────────────────────────────────────────────────────── render = send

@pytest.mark.parametrize("call,spec", [("add_flow", DROP), ("delete_flow_strict", DROP),
                                       ("add_meter", METER),
                                       ("delete_meter", {"meter_id": 1})])
def test_apply_sends_the_render_byte_for_byte(call, spec):
    session = Session(Response(200, "", content_type="text/html; charset=UTF-8"))
    driver = ryu(session)
    rendered = getattr(driver, f"render_{call}")(1, spec)
    out = getattr(driver, call)(1, spec)
    (sent,) = session.sent
    assert sent["method"] == rendered["method"] == "POST"
    assert sent["url"] == "http://127.0.0.1:8080" + rendered["path"]
    assert sent["data"] == rendered["body"].encode("utf-8")
    assert sent["headers"]["Content-Type"] == "application/json"
    assert out["request"] == {k: rendered[k] for k in ("method", "path", "body")}
    assert out["digest"] == base.request_digest(rendered)


def test_a_render_hashed_at_preview_is_what_apply_sends():
    driver_at_preview, session = ryu(), Session(Response(200, ""))
    rendered = driver_at_preview.render_add_flow(1, DROP)
    digest = base.request_digest(rendered)
    out = ryu(session).apply(rendered)
    assert out["ok"] and base.request_digest({
        "method": session.sent[0]["method"], "path": rendered["path"],
        "body": session.sent[0]["data"].decode("utf-8")}) == digest


def test_the_digest_covers_method_path_and_body():
    r = {"method": "POST", "path": "/a", "body": "{}"}
    assert len({base.request_digest(r), base.request_digest(dict(r, method="PUT")),
                base.request_digest(dict(r, path="/b")),
                base.request_digest(dict(r, body="{ }"))}) == 4
