"""AI troubleshooting's preview and a capture's documentation addresses (C3406; the operator's
paid AI plan, 2026-11-13: "FREE first: ... print exactly what a Troubleshoot with AI press would
send ... making no call", and "Automate moving addresses into documentation ranges in the
capture"; `fixit_troubleshoot.preview`, `gateway.request_body`, `read_loop.first_request` and
`second_request`, scripts/nmas-fixit-cases ``--preview`` and `doc_addresses`). No live AI call.

- **No call and no record:** the preview runs with the provider's send and its token count, the
  API key's read, the record of AI calls, the send log and the incident's proposal writer each
  replaced by a stand-in that fails the test; none is reached, and the stores' folders are
  byte for byte as they were.
- **What a press sends:** with the device state class on, the preview's pass 1 is byte for byte
  the body `troubleshoot` hands the provider for the same incident; with it off the preview
  still builds the reads pass, says the class is off now and writes no setting; given the reads
  a press's pass 1 asks for, its pass 2 is byte for byte the press's pass 2. A device read's
  line with a secret's shape is withheld as the loop withholds it.
- **The script:** ``--out`` inside the checkout refused (2), the preview written outside it,
  ``--doc-addresses`` applied to it.
- **Documentation addresses:** IPv4 and IPv6 addresses and prefixes moved into 192.0.2.0/24,
  198.51.100.0/24, 203.0.113.0/24 and 2001:db8::/32, sorted-order and deterministic (the same
  address the same within one output, distinct ones distinct, two runs over reordered input
  agree), prefix lengths kept; loopback, link-local, unspecified, multicast, netmasks and
  documentation addresses kept as written; times, MAC addresses and OIDs untouched; a planted
  pack holds none of its addresses after, its nested JSON included.
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import types

import pytest

from modules.ai import gateway
from tests.test_fixit_troubleshoot import ai, answer, fix, press, stopped  # noqa: F401
from tests.test_fixit_section_v2 import NET, web  # noqa: F401 (the fixture `ai` builds on)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: A type 9 hash: the egress mask's shape, planted in a device read's answer.
HASH = "$9$abcdefghijklmn$opqrstuvwxyz0123456789ABCDEFG"


def _script():
    loader = importlib.machinery.SourceFileLoader(
        "nmas_fixit_cases_preview", os.path.join(ROOT, "scripts", "nmas-fixit-cases"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _tree(*roots) -> dict:
    """Every file under *roots*: its size and sha256."""
    out = {}
    for root in roots:
        for folder, _dirs, files in os.walk(root):
            for name in files:
                path = os.path.join(folder, name)
                with open(path, "rb") as fh:
                    out[path] = hashlib.sha256(fh.read()).hexdigest()
    return out


@pytest.fixture
def reads(ai, monkeypatch):  # noqa: F811
    """The lab's r2 with its real intent (two subscriptions and their receiver), a read-only
    account, and the reads answered by stand-ins: the device's (a planted hash in one line),
    the collector's and the stream's series."""
    from modules.ai import read_loop as RL
    from modules.ai import router_reads as RR
    from modules.heal import diagnose_stream as DS
    from tests.test_heal_resubscribe import Src

    intents = Src()._intents
    monkeypatch.setattr(RR, "_committed", lambda network, hosts: (intents,
                                                                   {h: "" for h in hosts}))
    monkeypatch.setattr(RR, "read_accounts", lambda network, hosts: {h: (True, "")
                                                                     for h in hosts})
    ran = []

    def device(op, args, requests, scope):
        ran.append(("device", op, tuple(requests)))
        return RL.Answered("Subscription ID: 101\nState: Connected\n"
                           f"username ro secret 9 {HASH}\nAddress: 192.0.2.10", run="run-1")

    def collector(address, port, sources):
        ran.append(("collector", address, port))
        return {"state": "read", "address": address, "port": port, "listening": ["0.0.0.0"],
                "sessions": [{"remote": "192.0.2.6", "rport": 40000, "state": "ESTAB",
                              "bytes_received": 10, "lastrcv_ms": 900000}],
                "others": 0, "activity": "stale"}

    def series(dev, sub):
        ran.append(("series", dev, sub))
        return {"state": "absent", "count": 0, "why": ""}
    monkeypatch.setattr(RR, "run", device)
    monkeypatch.setattr(DS, "read_collector", collector)
    monkeypatch.setattr(DS, "series_of", series)
    return types.SimpleNamespace(ran=ran)


def _class(monkeypatch, on: bool):
    from modules.ai import egress_classes
    monkeypatch.setattr(egress_classes, "device_state_allowed", lambda network: (
        {"allowed": True, "why": ""} if on else {"allowed": False, "why": "an admin turns it on"}))


def _no_way_out(monkeypatch) -> list:
    """Every way out or into a record replaced by a stand-in that fails the test: the
    provider's send and count, the API key's read, the record of AI calls, the send log and
    the incident's proposal writer. The list holds each one reached."""
    from modules.ai import calls, read_log
    from modules.fixit import incident as F
    reached = []

    def stop(name):
        def stand_in(*a, **kw):
            reached.append(name)
            raise AssertionError(f"the preview reached {name}")
        return stand_in
    AD = gateway.anthropic_adapter
    monkeypatch.setattr(gateway, "anthropic_adapter", types.SimpleNamespace(
        **{**vars(AD), "send": stop("send"), "count_tokens": stop("count_tokens")}))
    monkeypatch.setattr(gateway, "_api_key", stop("the API key"))
    monkeypatch.setattr(gateway, "_prepared", stop("gateway._prepared"))
    monkeypatch.setattr(calls, "record", stop("calls.record"))
    monkeypatch.setattr(read_log, "sending", stop("read_log.sending"))
    monkeypatch.setattr(read_log, "answered", stop("read_log.answered"))
    monkeypatch.setattr(F, "record_proposal", stop("record_proposal"))
    return reached


def _preview(iid, **kw):
    got = _script().preview(NET, iid, **kw)
    assert "preview" in got, got
    return got["preview"]


# ── No call and no record ───────────────────────────────────────────────────────────────────

def test_the_preview_asks_no_provider_and_writes_nothing(ai, reads, monkeypatch,  # noqa: F811
                                                         tmp_path):
    _class(monkeypatch, False)
    iid = stopped(ai)
    before = _tree(tmp_path, os.environ["NMAS_DATA_DIR"])
    with pytest.MonkeyPatch.context() as mp:
        reached = _no_way_out(mp)
        got = _preview(iid, actor="operator")
    assert reached == [], reached
    assert _tree(tmp_path, os.environ["NMAS_DATA_DIR"]) == before, "a store was written"
    assert got["first"]["body"] and got["second"]["body"], got["said"]
    assert ai.sent == []


def test_a_pass_1_the_gateway_refuses_prints_no_body_and_runs_no_read(ai, reads,  # noqa: F811
                                                                     monkeypatch):
    """A request the gateway refuses is never sent, so a press would run no read: the preview
    prints no body for it and runs none either (the tier's hand check of 2026-11-13, mutants P2
    and P3: a refused pass 1 still ran the reads, and nothing held it)."""
    from modules.ai import prompts
    _class(monkeypatch, True)
    iid = stopped(ai)

    def refused(*args, **kw):
        # The gateway's own refusal of the request (its prompt cannot be loaded), planted where
        # no read looks, so the reads would run if anything let them.
        raise prompts.PromptError("planted: the prompt file cannot be read")
    monkeypatch.setattr(prompts, "load", refused)
    got = _preview(iid)
    first = got["first"]
    assert first["body"] is None and first["refused"]["kind"] == "prompt", first
    assert reads.ran == [], f"a read ran for a pass 1 that is never sent: {reads.ran}"
    assert got["second"] is None
    assert not [r for r in got["reads"] if r.get("verdict") == "run"], got["reads"]


#: The preview's own functions in modules/ai/fixit_troubleshoot.py.
PREVIEW_NAMES = {"preview", "preview_requests", "_preview_body", "_read_shown"}


def _preview_callers(root: str, extra: dict = None) -> dict:
    """Every Python file of the product (app.py, routes/, modules/, scripts/, each parsed by
    `ast`; *extra* adds planted sources by name) that names one of the preview's functions:
    an attribute of a name bound to `modules.ai.fixit_troubleshoot`, or one imported from
    it. ``{path: [name, ...]}``, and the count of files parsed under ``"<parsed>"``."""
    import ast

    from tests import source_index
    files = {}
    for path in source_index.tracked("app.py", "routes", "modules", "scripts", root=root):
        rel = os.path.relpath(path, root)
        name = os.path.basename(rel)
        if name.endswith(".py") or (rel.startswith("scripts/") and "." not in name):
            files[rel] = path
    sources = {rel: open(p, encoding="utf-8", errors="replace").read()
               for rel, p in files.items()}
    sources.update(extra or {})
    found, parsed = {}, 0
    for rel, text in sources.items():
        if rel == "modules/ai/fixit_troubleshoot.py":
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue                    # a shell script in scripts/
        parsed += 1
        aliases, hits = set(), []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "modules.ai":
                aliases |= {a.asname or a.name for a in node.names
                            if a.name == "fixit_troubleshoot"}
            elif isinstance(node, ast.ImportFrom) and node.module == "modules.ai.fixit_troubleshoot":
                hits += [a.name for a in node.names if a.name in PREVIEW_NAMES]
            elif isinstance(node, ast.Import):
                aliases |= {a.asname for a in node.names
                            if a.name == "modules.ai.fixit_troubleshoot" and a.asname}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr in PREVIEW_NAMES
                    and isinstance(node.value, ast.Name) and node.value.id in aliases):
                hits.append(node.attr)
        if hits:
            found[rel] = sorted(set(hits))
    found["<parsed>"] = parsed
    return found


def test_the_preview_is_reached_from_the_host_s_command_line_alone():
    """The operator, 2026-11-13: "the preview is reachable only from the host's command line,
    with no web route; add a test that no route calls it." No route, app.py or product module
    names the preview's functions; scripts/nmas-fixit-cases, run on the host, is the one that
    does. Every product file is parsed (a floor on them), and a planted route is found."""
    found = _preview_callers(ROOT)
    parsed = found.pop("<parsed>")
    assert parsed >= 400, f"only {parsed} product files parsed: the scan lost its population"
    assert found == {"scripts/nmas-fixit-cases": ["preview"]}, found
    planted = ("from flask import Blueprint\nbp = Blueprint('x', __name__)\n\n"
               "@bp.route('/v2/peek')\ndef peek():\n"
               "    from modules.ai import fixit_troubleshoot as AIT\n"
               "    return AIT.preview('Default', {}, None)\n")
    found = _preview_callers(ROOT, {"routes/planted_peek.py": planted,
                                    "routes/planted_import.py":
                                        "from modules.ai.fixit_troubleshoot import preview\n"})
    assert found["routes/planted_peek.py"] == ["preview"], found
    assert found["routes/planted_import.py"] == ["preview"], found


def test_with_the_class_off_it_builds_the_reads_pass_and_says_so(ai, reads,  # noqa: F811
                                                                 monkeypatch):
    from modules.ai import fixit_troubleshoot as T
    _class(monkeypatch, False)
    iid = stopped(ai)
    got = _preview(iid)
    assert got["class"]["now"] == "off" and "an admin turns it on" in got["class"]["why_off"]
    assert got["first"]["prompt"] == "fixit_troubleshoot.v4"
    assert "collector_sessions" in json.dumps(got["first"]["body"]["system"]), "the read set"
    said = " ".join(got["said"])
    assert "is off for" in said and "did not change it" in said and "at most 3" in said
    # Every read the scope allows: the brief, then each subscription's three.
    ops = [r["op"] for r in got["reads"]]
    assert ops == ["telemetry_brief"] + ["telemetry_receiver", "collector_sessions",
                                         "stream_series"] * 2
    assert all(r["verdict"] == "run" for r in got["reads"]), got["reads"]
    assert [r for r in reads.ran if r[0] == "collector" and r[2] == 57000], reads.ran
    # The local reads alone: no device read is run.
    reads.ran.clear()
    local = _preview(iid, device_reads=False)
    assert [r["op"] for r in local["reads"]] == ["collector_sessions", "stream_series"] * 2
    assert not [r for r in reads.ran if r[0] == "device"]
    assert T.PREVIEW_CLASS == "device_state"


def test_a_device_read_s_secret_line_is_withheld_as_the_loop_withholds_it(ai, reads,  # noqa: F811
                                                                          monkeypatch):
    _class(monkeypatch, False)
    iid = stopped(ai)
    got = _preview(iid)
    text = json.dumps(got)
    assert "opqrstuvwxyz0123456789" not in text, "the hash's text is never in the preview"
    sent = got["second"]["body"]["messages"][0]["content"]
    assert "mercury_reads" in sent and "line withheld: a secret" in sent
    brief = got["reads"][0]
    assert brief["op"] == "telemetry_brief" and brief["withheld"] == 1, brief


# ── What a press sends ──────────────────────────────────────────────────────────────────────

def test_pass_1_is_byte_for_byte_what_the_press_hands_the_provider(ai, reads,  # noqa: F811
                                                                   monkeypatch):
    _class(monkeypatch, True)
    iid = stopped(ai)
    with pytest.MonkeyPatch.context() as mp:
        reached = _no_way_out(mp)
        got = _preview(iid)
    assert reached == [] and got["class"]["now"] == "on"
    # The press, through the real route and gateway (the fixture's stand-in provider back).
    ai.answer = answer(fix())
    r, html = press(ai, iid)
    assert r.status_code == 200, html
    (body,) = ai.sent
    assert json.dumps(got["first"]["body"], sort_keys=True) == json.dumps(body, sort_keys=True)
    assert got["first"]["body"] == body


def test_pass_2_given_the_press_s_reads_is_byte_for_byte_the_press_s(ai, reads,  # noqa: F811
                                                                    monkeypatch):
    """The preview's runner and pass 2 are the loop's: given the reads a press's pass 1 asks
    for, its pass 2 is the body the press sends second."""
    from modules.ai import fixit_troubleshoot as T
    from modules.ai import anthropic_adapter as AD
    _class(monkeypatch, True)
    iid = stopped(ai)
    asked = [{"op": "collector_sessions", "args": {"device": "r2", "subscription": "101"},
              "why": "the collector's side", "hypothesis": "a dead session"},
             {"op": "telemetry_receiver", "args": {"device": "r2", "subscription": "101"},
              "why": "the device's side", "hypothesis": "a dead session"},
             {"op": "stream_series", "args": {"device": "r2", "subscription": "101"},
              "why": "the series", "hypothesis": "a dead session"}]
    monkeypatch.setattr(T, "preview_requests", lambda incident, device_reads=True: asked)
    got = _preview(iid)
    first = answer(fix())
    first["reads"] = asked
    script = iter([first, answer(fix(), cites=("attempt:1", "read:1"))])

    def send(body, key):
        ai.sent.append(body)
        return AD.Reply(status=200, body={
            "content": [{"type": "text", "text": json.dumps(next(script))}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 9000, "output_tokens": 600}},
            attempts=1, latency_s=0.2)
    monkeypatch.setattr(gateway, "anthropic_adapter", types.SimpleNamespace(
        **{**vars(gateway.anthropic_adapter), "send": send}))
    r, html = press(ai, iid)
    assert r.status_code == 200, html
    assert len(ai.sent) == 2
    assert got["first"]["body"] == ai.sent[0]
    assert got["second"]["body"] == ai.sent[1]


# ── The script ──────────────────────────────────────────────────────────────────────────────

def test_the_script_refuses_out_inside_the_checkout_and_writes_outside_it(ai, reads,  # noqa: F811
                                                                         monkeypatch,
                                                                         tmp_path, capsys):
    _class(monkeypatch, False)
    iid = stopped(ai)
    s = _script()
    inside = os.path.join(ROOT, "fixit-preview.json")
    assert s.main(["--preview", "--network", NET, "--incident", iid, "--out", inside]) == 2
    assert not os.path.exists(inside)
    assert s.main(["--preview", "--network", NET]) == 2
    out = str(tmp_path / "preview.json")
    assert s.main(["--preview", "--network", NET, "--incident", iid, "--out", out,
                   "--doc-addresses"]) == 0
    with open(out, encoding="utf-8") as fh:
        got = json.load(fh)
    assert got["first"]["body"] and "doc_addresses" in got
    assert "nothing was sent to the AI" in capsys.readouterr().out


# ── Documentation addresses ─────────────────────────────────────────────────────────────────

#: Addresses that are no documentation address (RFC 2544's benchmarking ranges, RFC 5180's
#: for IPv6): what a capture's lab addresses stand for here.
V4A, V4B, V4C = "198.18.0.6", "198.18.0.10", "198.19.4.1"
V6A, V6B = "2001:2::6", "2001:2:0:1::10"


def test_ipv4_and_ipv6_are_moved_in_sorted_order_with_prefixes_kept():
    s = _script()
    got, said = s.doc_addresses({"a": f"peer {V4B} and {V4A}/31, net {V4C}/24",
                                 "b": [f"ipv6 {V6B}/64 via {V6A}", f"again {V4A}"]})
    assert got == {"a": "peer 192.0.2.2 and 192.0.2.1/31, net 192.0.2.3/24",
                   "b": ["ipv6 2001:db8::2/64 via 2001:db8::1", "again 192.0.2.1"]}
    assert said["moved"] == {"ipv4": 3, "ipv6": 2}


def test_two_runs_over_reordered_input_agree_and_distinct_stay_distinct():
    s = _script()
    one, _ = s.doc_addresses([V4A, V4B, V6A, V6B])
    two, _ = s.doc_addresses([V6B, V4B, V6A, V4A])
    assert dict(zip([V4A, V4B, V6A, V6B], one)) == dict(zip([V6B, V4B, V6A, V4A], two))
    assert len(set(one)) == 4


@pytest.mark.parametrize("text, why", [
    ("127.0.0.1", "loopback"), ("::1", "loopback"),
    ("169.254.3.4", "link-local"), ("fe80::1%eth0", "link-local"),
    ("0.0.0.0", "unspecified"), ("::", "unspecified"),
    ("224.0.0.5", "multicast"), ("ff02::5", "multicast"),
    ("255.255.255.0", "a netmask"), ("0.0.0.255", "this network (0.0.0.0/8)"),
    ("192.0.2.7", "documentation"), ("2001:db8::7", "documentation"),
], ids=["loopback", "loopback v6", "link-local", "link-local v6", "unspecified",
        "unspecified v6", "multicast", "multicast v6", "netmask", "wildcard",
        "documentation", "documentation v6"])
def test_what_names_no_lab_is_kept_as_written(text, why):
    got, said = _script().doc_addresses({"t": f"x {text} y"})
    assert got == {"t": f"x {text} y"} and said["kept"] == {why: 1}


def test_a_documentation_address_already_there_is_never_given_twice():
    got, _ = _script().doc_addresses(f"192.0.2.1 and {V4A}, 2001:db8::1 and {V6A}")
    assert got == "192.0.2.1 and 192.0.2.2, 2001:db8::1 and 2001:db8::2"


@pytest.mark.parametrize("text", [
    "at 10:20:30 on 2026-11-12T10:20:30.5Z", "mac aa:bb:cc:dd:ee:ff and aabb.ccdd.eeff",
    "oid 1.3.6.1.4.1.9.9.1", "std::map and r7::stream", "version 17.3.4",
], ids=["times", "macs", "an oid", "words with colons", "a version"])
def test_what_is_no_address_is_untouched(text):
    got, said = _script().doc_addresses(text)
    assert got == text and said["moved"] == {"ipv4": 0, "ipv6": 0}


def test_a_planted_pack_holds_none_of_its_addresses_after():
    """A pack as a capture keeps it: its sections a JSON string inside the data, keys holding
    an address, a host:address run together; none of the planted addresses is left."""
    inner = json.dumps([{"name": "intent", "pieces": [
        {"ref": "intent:1", "ipv4": f"{V4A}/30", "ipv6": [f"{V6A}/64"],
         "receiver": f"host:{V4B}", "bgp": {V4C: "up"}}]}], separators=(",", ":"))
    pack = {"data": {"pack": inner, "the_incident": f"r7 lost its stream to {V4B}"},
            "ctx": {"network": f"{V6B} is the collector"}, "actable": ["r7", "101"]}
    got, said = _script().doc_addresses(pack)
    text = json.dumps(got)
    for planted in (V4A, V4B, V4C, V6A, V6B):
        assert planted not in text, planted
    assert json.loads(got["data"]["pack"])[0]["pieces"][0]["bgp"] == {"192.0.2.3": "up"}
    assert "host:192.0.2.2" in got["data"]["pack"] and got["actable"] == ["r7", "101"]
    assert said["moved"] == {"ipv4": 3, "ipv6": 2}


def test_the_capture_moves_its_addresses_by_default(ai, capsys):  # noqa: F811
    iid = stopped(ai)
    assert _script().main(["--capture", "--network", NET, "--incident", iid]) == 0
    got = json.loads(capsys.readouterr().out)
    assert "doc_addresses" in got and "pack" in got
    assert _script().main(["--capture", "--network", NET, "--incident", iid,
                           "--raw-addresses"]) == 0
    assert "doc_addresses" not in json.loads(capsys.readouterr().out)
