"""C506 phase 3 (board approved 2026-10-06): effects a person DECLARES with a reason, because the
program cannot show them, in the confirmed plan's hash and the record, and honoured by verify.

Three declarations, the board's: an adjacency MOVES (a cable move: OSPF to r1 leaves Gi3 for
Gi4, and must re-form on Gi4 within OSPF's settle window, or verify fails and rolls back); a
session ENDS (decommissioned at the far end: its loss is expected); ROUTES are expected to
change (a smaller table is recorded, never a failure). An undeclared neighbour forming beside
the expected ones is a note; one forming where a declared move expected its peer fails, naming
both.

The parts: what a plan offers and how a declaration is checked against it
(`expected_effects.offers`, `declared_from`, `raw_of`); the card (the form carries each
declaration between plans; a reason that is not the shape of one keeps it pending); the hash
(`authorisation.fingerprint`, unchanged with nothing declared); the confirm and the apply (the
declarations reach the job, are checked again against the recomputed program, and refuse when
they no longer fit); verify on r3's real `show ip ospf neighbor` with minimal edits; the receipt.
"""

import json

import pytest

from modules import pipeline
from modules.nsot import expected_effects as fx
from modules.nsot.authorisation import fingerprint
from tests.test_bgp_hold_watch import R3, Clock, _summary
from tests.test_device_deploy_v2 import _get, _reasons, _vals, deploy  # noqa: F401
from tests.test_device_deploy_v2 import lab  # noqa: F401 (the fixture)
from tests.test_pipeline_reads_real_output import capture, device

#: r2 with a cable move's two interfaces, r1 on Gi3's subnet, and a BGP peer on neither.
INTENTS = {
    "r2": {"hostname": "r2", "interfaces": [
        {"name": "GigabitEthernet3", "ipv4": "192.0.2.13 255.255.255.0"},
        {"name": "GigabitEthernet4", "ipv4": "192.0.2.74 255.255.255.252"}],
        "routing": {"ospf": [{"networks": ["network 192.0.2.0 0.0.0.255 area 0"],
                              "settings": ["router-id 10.255.1.12"]}],
                    "bgp": {"neighbors": ["neighbor 198.51.100.1 remote-as 65002"]}}},
    "r1": {"hostname": "r1", "interfaces": [
        {"name": "GigabitEthernet1", "ipv4": "192.0.2.11 255.255.255.0"}],
        "routing": {"ospf": [{"networks": ["network 192.0.2.0 0.0.0.255 area 0"],
                              "settings": ["router-id 10.255.1.11"]}]}},
}
#: The board's cable move: Gi4 configured and brought up with OSPF, Gi3 shut.
MOVE_PROGRAM = ["interface GigabitEthernet4", " ip ospf 1 area 0", " no shutdown", "exit",
                "interface GigabitEthernet3", " shutdown", "exit"]
WHY = "the uplink moves to the new cable"
MOVE = {"kind": "moves", "id": "ospf:10.255.1.11@GigabitEthernet3", "to": "GigabitEthernet4",
        "reason": WHY}
END = {"kind": "ends", "id": "bgp:198.51.100.1", "reason": "the peer is decommissioned tonight"}
ROUTES = {"kind": "routes", "reason": "the summary replaces the specific routes"}


def _offer():
    return fx.offers(INTENTS, "r2", fx.for_device(INTENTS, "r2", MOVE_PROGRAM))


class TestTheModel:
    def test_what_the_plan_offers(self):
        o = _offer()
        assert o["moves"] == [{"id": "ospf:10.255.1.11@GigabitEthernet3", "proto": "ospf",
                               "peer": "r1", "rid": "10.255.1.11", "from": "GigabitEthernet3"}]
        assert o["to"] == ["GigabitEthernet4"]
        assert [e["id"] for e in o["ends"]] == ["bgp:198.51.100.1"], \
            "the session the program does not drop may be declared to end"

    def test_each_kind_checked_into_its_canonical_shape(self):
        got, problems = fx.declared_from([MOVE, END, ROUTES], _offer())
        assert problems == []
        assert got == [
            {"kind": "moves", "proto": "ospf", "peer": "r1", "rid": "10.255.1.11",
             "from": "GigabitEthernet3", "to": "GigabitEthernet4", "reason": WHY},
            {"kind": "ends", "proto": "bgp", "peer": "", "rid": "", "address": "198.51.100.1",
             "reason": END["reason"]},
            {"kind": "routes", "reason": ROUTES["reason"]}]
        assert [fx.words(d) for d in got] == [
            "OSPF to r1 (10.255.1.11) moves from GigabitEthernet3 to GigabitEthernet4",
            "BGP to 198.51.100.1 ends", "the route table is expected to change"]

    @pytest.mark.parametrize("item, says", [
        (dict(MOVE, id="ospf:10.255.1.99@GigabitEthernet3"), "is not one this program drops"),
        (dict(MOVE, to="GigabitEthernet9"), "it may move to GigabitEthernet4"),
        (dict(MOVE, reason="move"), "too short to be a reason"),
        (dict(END, id="bgp:192.0.2.200"), "cannot be declared to end"),
        ({"kind": "teleports", "reason": WHY}, "is not a kind of declaration"),
    ])
    def test_a_declaration_the_plan_does_not_offer_is_refused_by_name(self, item, says):
        got, problems = fx.declared_from([item], _offer())
        assert got == [] and len(problems) == 1 and says in problems[0], problems

    def test_declared_twice_is_refused(self):
        got, problems = fx.declared_from([MOVE, dict(MOVE)], _offer())
        assert len(got) == 1 and "declared twice" in problems[0]

    def test_what_the_card_carries_round_trips(self):
        got, _p = fx.declared_from([MOVE, END, ROUTES], _offer())
        assert fx.declared_from([fx.raw_of(d) for d in got], _offer()) == (got, [])

    def test_the_hash_holds_each_declaration_and_its_reason_and_nothing_else_moves(self):
        got, _p = fx.declared_from([MOVE], _offer())
        plain = fingerprint(MOVE_PROGRAM, [])
        assert fingerprint(MOVE_PROGRAM, [], (), ()) == plain, "nothing declared: unchanged"
        assert fingerprint(MOVE_PROGRAM, [], (), got) != plain
        assert fingerprint(MOVE_PROGRAM, [], (), [dict(got[0], reason=WHY + " soon")]) != \
            fingerprint(MOVE_PROGRAM, [], (), got)


@pytest.fixture
def card(deploy, monkeypatch):  # noqa: F811
    """r2's deploy card, its derived effects the cable move's over INTENTS."""
    import routes.deploy as rd
    monkeypatch.setattr(rd, "_committed_intents_of", lambda name: (INTENTS, ""))
    monkeypatch.setattr(rd, "_expected_effects", lambda *a, **k: fx.for_device(
        INTENTS, "r2", MOVE_PROGRAM))
    return deploy


def _q(**fields):
    from urllib.parse import urlencode
    return urlencode(fields)


def _part(page):
    import html
    return html.unescape(page.split('id="expected"')[1].split("</div></div>")[0])


class TestTheCard:
    def test_the_three_choices_and_what_each_offers(self, card):
        _r, page = _get(card, "/v2/device/r2/deploy?" + _reasons()[1:])
        part = _part(page)
        for words in fx.DECLARE_WORDS.values():
            assert f"{words}…" in part
        assert 'value="ospf:10.255.1.11@GigabitEthernet3"' in part and \
            "OSPF to r1 (10.255.1.11) over GigabitEthernet3" in part
        assert '<option value="GigabitEthernet4"' in part
        assert 'value="bgp:198.51.100.1"' in part
        assert "Declared by you" not in part

    def test_a_move_declared_is_drawn_carried_and_in_the_confirm_s_hash(self, card):
        _r, plain = _get(card, "/v2/device/r2/deploy?" + _reasons()[1:])
        _r, page = _get(card, "/v2/device/r2/deploy?" + _reasons()[1:] + "&" + _q(
            mv_id=MOVE["id"], mv_to="GigabitEthernet4", mv_why=WHY))
        part = _part(page)
        assert "Declared by you, with a reason" in part
        assert ("OSPF to r1 (10.255.1.11) moves from GigabitEthernet3 to GigabitEthernet4: it "
                "must re-form on GigabitEthernet4 within OSPF's settle window (45 s)") in part
        assert f"Reason: “{WHY}” · in the hash and the record" in part
        assert 'name="decl"' in part and 'name="undecl"' in part
        vals = _vals(page)
        assert json.loads(vals["declare"]) == [MOVE]
        assert vals["command_hash"] != _vals(plain)["command_hash"]
        assert 'value=""' in part.split('name="mv_why"')[1][:40], "the new form is cleared"

    def test_a_carried_declaration_is_planned_again_and_removed_by_its_box(self, card):
        carried = json.dumps(MOVE, sort_keys=True)
        _r, kept = _get(card, "/v2/device/r2/deploy?" + _reasons()[1:] + "&" + _q(decl=carried))
        assert json.loads(_vals(kept)["declare"]) == [MOVE]
        _r, gone = _get(card, "/v2/device/r2/deploy?" + _reasons()[1:] + "&"
                        + _q(decl=carried, undecl="0"))
        _r, plain = _get(card, "/v2/device/r2/deploy?" + _reasons()[1:])
        assert "Declared by you" not in _part(gone)
        assert _vals(gone)["command_hash"] == _vals(plain)["command_hash"]

    def test_a_reason_too_short_keeps_it_pending_and_declares_nothing(self, card):
        _r, plain = _get(card, "/v2/device/r2/deploy?" + _reasons()[1:])
        _r, page = _get(card, "/v2/device/r2/deploy?" + _reasons()[1:] + "&" + _q(
            mv_id=MOVE["id"], mv_to="GigabitEthernet4", mv_why="move"))
        part = _part(page)
        assert "Not declared yet:" in part and "too short to be a reason" in part
        assert 'value="move"' in part and "open>" in part.split("mv_id")[0][-400:], "kept, and left open"
        assert "Declared by you" not in part
        assert _vals(page)["command_hash"] == _vals(plain)["command_hash"]

    def test_a_session_ends_and_routes_change(self, card):
        _r, page = _get(card, "/v2/device/r2/deploy?" + _reasons()[1:] + "&" + _q(
            end_id=END["id"], end_why=END["reason"]) + "&" + _q(rt_why=ROUTES["reason"]))
        part = _part(page)
        assert "BGP to 198.51.100.1 ends: its loss is expected" in part
        assert "The route table is expected to change: a smaller route table is recorded" in part
        assert {d["kind"] for d in json.loads(_vals(page)["declare"])} == {"ends", "routes"}

    def test_the_confirm_hands_the_declarations_to_the_job(self, card, monkeypatch):
        from modules import deploy_job
        got = {}

        def start(*a, **kw):
            got.update(kw)
            return "job-1"
        monkeypatch.setattr(deploy_job, "start", start)
        _r, page = _get(card, "/v2/device/r2/deploy?" + _reasons()[1:] + "&" + _q(
            mv_id=MOVE["id"], mv_to="GigabitEthernet4", mv_why=WHY))
        r = card["client"].post("/v2/device/r2/deploy/confirm", data=_vals(page))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert got["declare"] == {"r2": [MOVE]}


class TestTheApply:
    def _plan(self, declare):
        import routes.deploy as rd
        entry = rd.plan_devices("Lab", ["r2"], declare={"r2": declare})[0]
        auth = [{"line": "shutdown", "reason": "the link is being retired"}]
        entry = rd.plan_devices("Lab", ["r2"], authorise={"r2": auth},
                                declare={"r2": declare})[0]
        return entry, auth

    def test_the_apply_recomputes_the_same_hash_and_carries_them_to_the_device(
            self, card, monkeypatch):
        import routes.deploy as rd
        reached = []

        def spy(entry, list_name, rows, authorise, **kw):
            reached.append(kw.get("declare"))
            return {"device": "r2", "outcome": "deployed", "commands": ["lldp run"]}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        entry, auth = self._plan([MOVE])
        assert entry["declared"] and entry.get("deployable") is not False
        report = rd.apply_batch("Lab", {"r2": entry["capture_hash"]},
                                {"r2": entry["command_hash"]}, authorise={"r2": auth},
                                declare={"r2": [MOVE]}, actor="t")
        assert [r.get("outcome") for r in report["results"]] == ["deployed"], report["results"]
        assert reached == [{"r2": [MOVE]}]

    def test_without_the_declaration_the_confirmed_hash_is_refused(self, card, monkeypatch):
        import routes.deploy as rd
        monkeypatch.setattr(rd, "_deploy_one", lambda *a, **k: pytest.fail("sent"))
        entry, auth = self._plan([MOVE])
        report = rd.apply_batch("Lab", {"r2": entry["capture_hash"]},
                                {"r2": entry["command_hash"]}, authorise={"r2": auth},
                                actor="t")
        (r,) = report["results"]
        assert r["outcome"] == "refused" and "changed since you confirmed" in r["reason"]

    def test_a_declaration_that_no_longer_fits_refuses_by_name(self, card, monkeypatch):
        import routes.deploy as rd
        monkeypatch.setattr(rd, "_deploy_one", lambda *a, **k: pytest.fail("sent"))
        entry, auth = self._plan([MOVE])
        report = rd.apply_batch("Lab", {"r2": entry["capture_hash"]},
                                {"r2": entry["command_hash"]}, authorise={"r2": auth},
                                declare={"r2": [dict(MOVE, to="GigabitEthernet9")]}, actor="t")
        (r,) = report["results"]
        assert r["outcome"] == "refused"
        assert "a declared effect no longer fits the program" in r["reason"]
        assert "GigabitEthernet9" in r["reason"]

    def test_the_plan_refuses_one_it_does_not_offer(self, card):
        entry, _auth = self._plan([dict(MOVE, to="GigabitEthernet9")])
        assert entry["deployable"] is False
        assert any("a declared effect is refused" in b and "GigabitEthernet9" in b
                   for b in entry["blocking_reasons"])


# ---------------------------------------------------------------------------
# Verify, on r3's real `show ip ospf neighbor` (r1, 10.255.1.11, on GigabitEthernet3) with the
# one edit each case needs, and r3's real BGP table.
# ---------------------------------------------------------------------------

R3_OSPF = capture("r3", "show_ip_ospf_neighbor")
R1_ROW = "10.255.1.11     100   FULL/DROTHER    00:00:39    10.255.3.11     GigabitEthernet3"
assert R1_ROW in R3_OSPF                    # the edits below are of a real row


def _moved_to(interface):
    return R3_OSPF.replace(R1_ROW, R1_ROW.replace("GigabitEthernet3", interface))


def _without_r1():
    return R3_OSPF.replace(R1_ROW + "\n", "")


def _with(row):
    return R3_OSPF.rstrip("\n") + "\n" + row + "\n"


R3_MOVE = {"kind": "moves", "proto": "ospf", "peer": "r1", "rid": "10.255.1.11",
           "from": "GigabitEthernet3", "to": "GigabitEthernet5", "reason": WHY}
R1_DROP = {"proto": "ospf", "peer": "r1", "rid": "10.255.1.11", "address": "10.255.3.11",
           "via": "GigabitEthernet3", "why": "its adjacency is on GigabitEthernet3"}


@pytest.fixture
def verify(monkeypatch):
    """r3 before (its real reads) and after (*ospf*, *summary*), verify run with a fake clock;
    the reads verify makes while it waits are the after state."""
    real = device("r3")

    def snap(ospf, summary):
        def reply(conn, command, **kw):
            if command == "show ip ospf neighbor":
                return ospf
            if command == "show bgp all summary":
                return summary
            return real(conn, command, **kw)
        monkeypatch.setattr("modules.commands.run_device_command", reply)
        return pipeline._detect_routing_neighbors(None)

    def run(after_ospf, *, declared=(), drops=(R1_DROP,), summary=None, routes=None):
        before = snap(R3_OSPF, _summary())
        after = snap(after_ospf, summary or _summary())
        clock = Clock(1010.0)
        ctx = pipeline.PipelineContext(
            config_type="template", device_ips=["x"], params={}, ip_params_map={},
            selected_devices=[{"ip": "x", "hostname": "r3"}], connections_pool={},
            pool_lock=None, config_id="t", settle_sleep=clock.sleep, settle_clock=clock)
        ctx.pre_snapshots = {"x": {"routing_neighbors": before}}
        ctx.post_snapshots = {"x": {"routing_neighbors": after, "running_config": R3}}
        if routes:
            ctx.pre_snapshots["x"]["routes"] = {"total_count": routes[0]}
            ctx.post_snapshots["x"]["routes"] = {"total_count": routes[1]}
        ctx.pushed_at = {"x": 1000.0}
        ctx.rendered_commands = {"x": ["interface GigabitEthernet5", " ip ospf 1 area 0",
                                       " no shutdown", "exit", "interface GigabitEthernet3",
                                       " shutdown", "exit"]}
        ctx.expected_effects = {"x": {"adjacencies_drop": list(drops),
                                      "declared": list(declared)}}
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda *a, **k: None)
        monkeypatch.setattr(pipeline, "_detect_routing_neighbors", lambda _c: after)
        failed = None
        try:
            pipeline._stage_verify(ctx)
        except pipeline.PipelineStageError as exc:
            failed = str(exc)
        return ctx.verify_result["x"], failed, clock
    return run


class TestVerifyHonoursThem:
    def test_a_declared_move_that_re_forms_on_its_interface_passes(self, verify):
        v, failed, _clock = verify(_moved_to("GigabitEthernet5"), declared=[R3_MOVE])
        assert failed is None, v["issues"]
        assert v["declared_moves"][0]["state"] == "formed"
        assert v["declared"] == [R3_MOVE]

    def test_re_forming_on_another_interface_fails_naming_both(self, verify):
        v, failed, _clock = verify(_moved_to("GigabitEthernet2"), declared=[R3_MOVE])
        assert failed and any(
            "declared to move to GigabitEthernet5, and re-formed on GigabitEthernet2 instead"
            in i for i in v["issues"]), v["issues"]

    def test_someone_else_forming_there_instead_fails_naming_both(self, verify):
        stranger = "10.255.1.99     100   FULL/DROTHER    00:00:39    10.255.5.99     GigabitEthernet5"
        v, failed, _clock = verify(_with(stranger).replace(R1_ROW + "\n", ""),
                                   declared=[R3_MOVE])
        assert failed and any("formed there with 10.255.1.99 (not declared), and 10.255.1.11 "
                              "did not" in i for i in v["issues"]), v["issues"]

    def test_a_move_that_never_forms_fails_after_the_protocol_s_window(self, verify):
        v, failed, clock = verify(_without_r1(), declared=[R3_MOVE])
        assert failed and any("did not form there within 45 s" in i for i in v["issues"])
        assert sum(clock.slept) >= 45, "waited OSPF's settle window for it"

    def test_a_neighbour_already_on_the_target_replaces_nothing(self, verify):
        """10.255.1.14 was on GigabitEthernet4 before the change: a move of r1 to Gi4 that does
        not happen is 'did not form', never 'someone else formed there'."""
        to4 = dict(R3_MOVE, to="GigabitEthernet4")
        v, failed, _clock = verify(_without_r1(), declared=[to4])
        assert failed and any("did not form there" in i for i in v["issues"]), v["issues"]
        assert not any("not declared" in i for i in v["issues"])

    def test_an_undeclared_additional_neighbour_is_a_note(self, verify):
        extra = "10.255.1.99     100   FULL/DROTHER    00:00:39    10.255.5.99     GigabitEthernet5"
        v, failed, _clock = verify(_with(extra), drops=())
        assert failed is None, v["issues"]
        assert any("an adjacency nobody declared formed with 10.255.1.99" in n
                   for n in v["notes"]), v["notes"]

    def test_an_ended_session_is_expected_to_go(self, verify):
        ends = {"kind": "ends", "proto": "bgp", "peer": "", "rid": "",
                "address": "198.51.100.1", "reason": "the peer is decommissioned tonight"}
        v, failed, _clock = verify(R3_OSPF, declared=[ends], drops=(),
                                   summary=_summary("Idle"))
        assert failed is None, v["issues"]
        assert v["bgp_watch"]["before"] == 1, "the hold watch counts the session that stays"

    def test_the_same_session_not_declared_fails(self, verify):
        v, failed, _clock = verify(R3_OSPF, drops=(), summary=_summary("Idle"))
        assert failed

    def test_routes_declared_to_change_are_recorded_not_failed(self, verify):
        v, failed, _clock = verify(R3_OSPF, drops=(), declared=[{"kind": "routes",
                                                               "reason": ROUTES["reason"]}],
                                   routes=(12, 6))
        assert failed is None, v["issues"]
        assert v["routes_declared"] == ROUTES["reason"]
        assert any("Route table 12 → 6: declared to change" in n for n in v["notes"])


class TestTheRecord:
    def test_the_receipt_keeps_the_declarations_the_moves_and_the_notes(self):
        from modules.nsot import receipts
        result = {"device": "r3", "outcome": "deployed", "commands": ["x"],
                  "declared": [R3_MOVE], "verify": {
                      "ok": True, "declared_moves": [{"move": fx.words(R3_MOVE),
                                                      "state": "formed", "elapsed": 38.0,
                                                      "window": 45}],
                      "notes": ["OSPF: an adjacency nobody declared formed with 10.255.1.99"]}}
        (row,) = receipts.rows_for({"results": [result], "golden": {}}, list_name="Lab",
                                   action="deploy", actor="t", actor_kind="person",
                                   confirmations={}, command_hashes={})
        assert row["declared"] == [R3_MOVE]
        assert row["checks"]["declared_moves"][0]["state"] == "formed"
        assert row["checks"]["notes"] == result["verify"]["notes"]
