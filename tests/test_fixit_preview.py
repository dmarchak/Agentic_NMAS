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
  line with a secret's shape is withheld as the loop withholds it. The incident's pack names
  its people (intent commit, History, an approval) and the two bodies hold no address, each
  person their stable label (C3424).
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


def _no_label_key_held(mp):
    """No label key held by this process (the suite's planted one taken away), and none in
    the store: ``(the stored value to put back, the settings writer)``."""
    from modules import display_names, secrets_store
    from modules.config import get_user_setting, set_user_setting
    mp.delitem(display_names._LABEL_KEY, "key", raising=False)
    was = get_user_setting(display_names.LABEL_KEY_SETTING, "")
    secrets_store.set_secret(display_names.LABEL_KEY_SETTING, "")
    return was, set_user_setting


@pytest.mark.parametrize("installed", [False, True], ids=["no key", "installed key"])
def test_the_preview_writes_nothing_whatever_asked_for_the_label_key_first(
        ai, reads, monkeypatch, tmp_path, installed):  # noqa: F811
    """C3458: the preview the first thing in its process to ask for the label key (none held),
    with none installed: refused, the key named, nothing sent and nothing written (it once made
    the key, writing user_settings.json); with one installed at the start: labelled from it,
    and nothing written either."""
    from modules import display_names
    _class(monkeypatch, False)
    iid = stopped(ai)
    was, put_back = _no_label_key_held(monkeypatch)
    try:
        if installed:
            assert display_names.install_label_key() == "installed"
        before = _tree(tmp_path, os.environ["NMAS_DATA_DIR"])
        with pytest.MonkeyPatch.context() as mp:
            reached = _no_way_out(mp)
            got = _script().preview(NET, iid, actor="operator")
        assert reached == [], reached
        assert _tree(tmp_path, os.environ["NMAS_DATA_DIR"]) == before, "a store was written"
        if installed:
            assert got["preview"]["first"]["body"], got
            assert "person-" in json.dumps(got["preview"]["first"]["body"])
        else:
            assert "preview" not in got, "a person was labelled with no key installed"
            assert display_names.LABEL_KEY_SETTING in got["error"], got
            assert "nothing was sent" in got["error"]
        assert ai.sent == []
    finally:
        put_back(display_names.LABEL_KEY_SETTING, was)


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
    assert got["first"]["prompt"] == "fixit_troubleshoot.v5"
    assert "collector_sessions" in json.dumps(got["first"]["body"]["system"]), "the read set"
    said = " ".join(got["said"])
    assert "is off for" in said and "did not change it" in said and "at most 3" in said
    # Every read the scope allows: the brief and the device's connections (C3640), then each
    # subscription's three; the device's by Mercury's allowlist (C3661).
    ops = [r["op"] for r in got["reads"]]
    assert ops == ["show", "show"] + ["show", "collector_sessions", "stream_series"] * 2
    sent = [r["requests"] for r in got["reads"] if r["op"] == "show"]
    assert sent == [["show telemetry ietf subscription all"],
                    ["show telemetry internal connection"],
                    ["show telemetry ietf subscription 101 receiver"],
                    ["show telemetry ietf subscription 102 receiver"]]
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
    assert brief["op"] == "show" and brief["requests"] == [
        "show telemetry ietf subscription all"] and brief["withheld"] == 1, brief


# ── What a press sends ──────────────────────────────────────────────────────────────────────

def _one_instant(monkeypatch):
    """The preview and the press built at one instant: the evidence pack's clock seam
    (`evidence_pack._now`) pinned, so the two bodies compare byte for byte whatever second
    each is built in (CI run #1678: built a second apart, every read time differed)."""
    import time
    from modules import evidence_pack as EP
    fixed = float(int(time.time()))
    monkeypatch.setattr(EP, "_now", lambda: fixed)


def test_pass_1_is_byte_for_byte_what_the_press_hands_the_provider(ai, reads,  # noqa: F811
                                                                   monkeypatch):
    _class(monkeypatch, True)
    _one_instant(monkeypatch)
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
    _one_instant(monkeypatch)
    iid = stopped(ai)
    asked = [{"op": "collector_sessions", "args": {"device": "r2", "subscription": "101"},
              "why": "the collector's side", "hypothesis": "a dead session"},
             {"op": "show", "args": {"device": "r2",
                                     "words": "telemetry ietf subscription 101 receiver"},
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


def test_the_incident_s_pack_sends_no_person_but_by_their_label(ai, reads,  # noqa: F811
                                                                monkeypatch):
    """C3424 (the operator's STOP of 2026-11-13: the r7 preview carried an address twice, the
    intent piece's ``intent_commit.actor``): the incident's pack as built holds the planted
    people (its intent commit's actor, a History record's who and its words, an approval a
    later section carries), the control; the preview's two bodies hold no address at all, and
    each person is their stable label (`display_names.label`)."""
    from modules import display_names
    from modules import evidence_pack as EP
    alice, bob = "alice.ops@example.com", "bob.lab@example.org"
    real = EP.build_incident
    built = []

    def planted(*a, **kw):
        pack = real(*a, **kw)
        # The pieces as `intent_section` and `history_section` write them (this lab's are
        # absent: its device has no golden and no History in the window).
        for s in pack["sections"]:
            if s["name"] == "intent":
                s.update(state="ok", pieces=[{
                    "ref": "intent:1", "state": "differs", "adds": 1, "removes": 0,
                    "lines": ["+ ntp server 192.0.2.1"], "intent_commit": {
                        "state": "ok", "sha": "0" * 12, "actor": alice, "verified": "access",
                        "at": "2026-11-12T00:00:00+00:00", "how": "verified sign-in"}}])
            if s["name"] == "history":
                s.update(state="ok", pieces=[{
                    "ref": "history:1", "at": "2026-11-12T00:00:00Z", "kind": "intent",
                    "what": "intent committed", "who": bob, "outcome": "", "sha": "1" * 12,
                    "detail": f"asked by {alice}", "verified": "access"}])
        pack["sections"].append({"ref": "approvals", "name": "approvals", "state": "ok",
                                 "pieces": [{"ref": "approvals:1", "approved_by": bob}]})
        built.append(pack)
        return pack
    monkeypatch.setattr(EP, "build_incident", planted)
    _class(monkeypatch, True)
    iid = stopped(ai)
    got = _preview(iid)
    stored = json.dumps(built[-1])
    assert alice in stored and bob in stored, "the control: the pack holds both"
    for name in ("first", "second"):
        body = json.dumps(got[name]["body"])
        assert display_names.EMAIL.search(body) is None, (name, display_names.EMAIL.search(body))
        assert display_names.label(alice) in body and display_names.label(bob) in body, name


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


# ── A pack the size of r4's (the host's preview, 2026-11-14) ────────────────────────────────

#: The sizes measured on the host (`nmas-fixit-cases --preview` of r4's standing incident,
#: 2026-11-14 10:3x UTC): the trimmable sections' 16,784 characters as sent (logs 4,390,
#: neighbours 3,836, history 3,234, observer 2,701, health 2,623), planted here in the three
#: whose pieces are free text (the observer's and health's are drawn by their own line
#: builders from figures), and the topology's 13,931.
R4_SECTIONS = {"logs": 6000, "neighbours": 5500, "history": 5284}
R4_TOPOLOGY = 13931


def _r4_sized(monkeypatch):
    """The lab's incident with its pack's sections and its topology grown to r4's measured
    sizes: each trimmable section given pieces of about 110 characters to its size, and the
    topology sent with a subgraph of its size. Real builders underneath; only the sizes are
    planted."""
    from modules import evidence_pack as EP
    from modules.ai import explain

    real_pack, real_topo = EP.build_incident, explain.topology

    def pack(*a, **kw):
        got = real_pack(*a, **kw)
        names = {s.get("name") for s in got["sections"]}
        for name, size in R4_SECTIONS.items():
            pieces = [{"ref": f"{name}:{n}", "what": f"line {n} " + "x" * 90}
                      for n in range(1, size // 110 + 1)]
            if name in names:
                for s in got["sections"]:
                    if s.get("name") == name:
                        s.update(state="ok", pieces=pieces)
            else:
                got["sections"].append({"ref": name, "name": name, "state": "ok",
                                        "source": "planted", "pieces": pieces})
        return got

    def topology(p):
        got = real_topo(p)
        return dict(got, sent=True, why="", summary="a summary " * 140,
                    yaml="devices:\n" + "  - r: x\n" * (R4_TOPOLOGY // 10), ids=["dev:1"],
                    reached={"r2": {"hop": 0}})

    monkeypatch.setattr(EP, "build_incident", pack)
    monkeypatch.setattr(explain, "topology", topology)


def test_a_pack_the_size_of_r4s_still_fits_both_passes(ai, reads, monkeypatch):  # noqa: F811
    """The host's preview of r4's incident (2026-11-14) built pass 1 at 36,051 tokens and pass 2
    at 35,688 by the fallback estimate, over the task's bound of 27,000: a press would be
    refused (`prompt_too_long`) whenever the provider's count is not had. With a pack and a
    topology of those sizes, both passes now fit by the fallback estimate itself, the topology
    left out and the largest sections cut, each said; pass 2 carries no read set."""
    from modules.ai import fixit_troubleshoot as T
    from modules.ai import profiles
    _class(monkeypatch, True)
    _r4_sized(monkeypatch)
    iid = stopped(ai)
    got = _preview(iid)
    bound = profiles.TASKS[T.FEATURE]["max_prompt_tokens"]
    assert got["first"]["prompt_tokens_estimated"] <= bound, got["first"]
    assert got["second"] is not None
    assert got["second"]["prompt_tokens_estimated"] <= bound, got["second"]
    assert "read_set" not in json.dumps(got["second"]["body"]["system"])
    assert "read_set" in json.dumps(got["first"]["body"]["system"])
    sent = got["first"]["body"]["messages"][0]["content"]
    assert T.TOPOLOGY_LEFT_OUT in sent and "pieces sent, to fit the request's bound" in sent
    # The worst pass 2 (three reads at the cap) fits too: pass 1 with the reserve is in bound.
    prep = T.request(NET, *_found(ai, iid))
    chars = T.request_chars(prep)
    worst = chars + max(0, T.READS_RESERVE_CHARS - len(T.read_set()))
    assert gateway.tokens_of_chars(max(chars, worst)) <= bound
    assert prep["said"]["fit"][0] == "the topology left out", prep["said"]["fit"]
    assert any("cut to" in step for step in prep["said"]["fit"])


def test_a_pack_that_fits_is_sent_whole(ai, reads, monkeypatch):  # noqa: F811
    """The lab's own pack, with a small topology sent: nothing is left out or cut, and the fit
    says so by saying nothing."""
    from modules.ai import explain
    from modules.ai import fixit_troubleshoot as T
    _class(monkeypatch, True)
    real = explain.topology
    monkeypatch.setattr(explain, "topology", lambda p: dict(
        real(p), sent=True, why="", summary="a small network", yaml="devices:\n  - r: x\n",
        ids=["dev:1"], reached={"r2": {"hop": 0}}))
    iid = stopped(ai)
    prep = T.request(NET, *_found(ai, iid))
    assert prep["said"]["fit"] == []
    assert prep["topo"]["sent"] is True and prep["data"]["network_topology"].startswith(
        "devices:")
    assert T.TOPOLOGY_LEFT_OUT not in json.dumps(prep["data"])


def _found(w, iid):
    """``(found, incident)`` as the press and the preview resolve them
    (`incident_page.resolve`, `fixit.section.incident_of`)."""
    from modules import incident_page
    from modules.fixit import section
    found = incident_page.resolve(NET, iid)
    return found, section.incident_of(NET, found)["incident"]
