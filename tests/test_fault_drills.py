"""Declared fault drills (`modules/fault_drills.py`; the operator's decision, 2026-11-11, word for
word: "declared fault drills are exempt from guard 11 (same change healed twice in 24 h) and from
the per-device rate holds. Nothing else: every other guard, the verify, the rollback and the
neighbour hold apply to a drill exactly as to a real fault"), no network, no device, a fake clock.

- **The operator's test:** "a declared drill re-injected 3 times heals 3 times; the same repeat
  undeclared halts at the second", through the REAL detect-to-decide path (`incidents.sight`,
  `settle`, `decide.run`) and the REAL act (`act.act_one` with the act tests' stand-in sources),
  at the lab's values (`heal_max_per_device_hour` 1, `heal_repeat_halts_hours` 24). Inside an
  hour the undeclared second is stopped by guard 9 (it runs before guard 11, section 6's
  order); past guard 9's hour and inside 24 hours it HALTS the policy by guard 11. Guard 9 alone
  (two different departures inside an hour), declared and not.
- **Nothing else is exempt:** guard 10 counts a drill's heals and halts a drill; the topology
  (neighbour) hold still holds a drill.
- **Never in the real figures:** a real incident's guards 9 and 11 do not count a drill's heal;
  the dry run's Right / Wrong counts leave drills out (`drill_counts` holds them).
- **The tag at creation:** set in the write that opens the incident; another device, or after
  the bound, is real; a member keeps its own; the exemption is the incident's tag, so a
  declaration that expires changes no incident already tagged.
- **The declaration:** one device, at most 15 minutes, three words, a person; a second open
  drill and a declaration after the fault are refused, naming both times.
- **Where it is made:** the card through the app's client (the menu row, the card, the answer
  in place, a refusal), the JSON body, a request no verified person made refused, and the CLI
  recording the host login, labelled.
- **History:** each declaration, and a drill heal's row says it was a drill.
"""

import importlib.machinery
import importlib.util
import os
import re
import types

import pytest

from tests.test_heal_act import FakeAct
from tests.test_heal_decide import Fake, GOLDEN, ROUTE4, ROUTE6
from tests.test_heal_decide import lab  # noqa: F401 (the fixture, named by each test below)
from tests.test_heal_policy import T0, auto, iso
from tests.test_heal_triggers import _Lazy
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

A, DC, DS, GD, I = (_Lazy("act"), _Lazy("decide"), _Lazy("decisions"), _Lazy("guards"),
                    _Lazy("incidents"))
NET, DEV = "Default", "edge-b"
BY = "op@example.com"
EXPECTS = "an IPv6 route added on edge-b"
MIN = 60


@pytest.fixture(autouse=True)
def no_host_addresses(monkeypatch):
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])


def FD():
    import modules.fault_drills as mod

    return mod


def _inv(_network, device):
    return {"hostname": device, "_netbox_id": 41}


def declare(at, device=DEV, minutes=10, expects=EXPECTS, **kw):
    got = FD().record_declared(NET, device, minutes=minutes, expects=expects, by=BY,
                               actor_verified="access", via="test", now=at, inventory=_inv, **kw)
    return got


def _departure(running, device=DEV):
    from modules.drift_check import departure, drift_diff

    return departure(drift_diff(GOLDEN, running, device))


def inject(at, running=GOLDEN + ROUTE6, device=DEV):
    """The fault on *device* at *at*: its configuration change sighted (the trigger's own
    writer), the grace period settled on its departure, the decision's real run; a heal is
    then acted by the real act. ``(incident, decision)`` as recorded."""
    seen = I.sight(NET, device, {"kind": "config_change", "key": f"cfg:{device}:{at}",
                                 "epoch": at, "at": iso(at), "attribution": {"by": "outside"},
                                 "words": "CONFIG_I"}, now=at)
    I.settle(NET, seen["incident"], {"state": "persisted", "words": "settled", "first": 0,
                                     "second": 1,
                                     "operands": {"departure": _departure(running, device)}},
             at + 100)
    ran = DC.run(NET, now=at + 130, sources=Fake(running))
    assert ran["ran"] and not ran["failed"], ran
    (one,) = [x for x in ran["decided"] if x["incident"] == seen["incident"]]
    d = DS.find(NET, one["decision"])
    if d["outcome"] == "heal":
        got = A.act_one(NET, d["id"], now=at + 140, sources=FakeAct(running))
        assert got["outcome"] == "healed", got
    inc = next(i for i in I.read(NET)["incidents"] if i["id"] == seen["incident"])
    return inc, DS.find(NET, d["id"])


def heals(n):
    return [x for x in DS.decisions(NET) if x["outcome"] == "heal"][:n]


@pytest.fixture
def auto_lab(lab):  # noqa: F811
    """Default marked lab, in AUTO for three hours from T0 - 60, the added line allowed."""
    auto(NET, now=T0 - 60, hours=3, kinds=("added_line",))
    return lab


# ── The operator's test ─────────────────────────────────────────────────────────────────────

class TestTheOperatorsTest:
    def test_the_lab_values_are_the_guards_values(self, auto_lab):
        from modules.heal import policy

        mode = policy.current(NET, T0)
        assert GD.value(mode, "heal_max_per_device_hour") == 1
        assert GD.value(mode, "heal_repeat_halts_hours") == 24

    def test_a_declared_drill_reinjected_3_times_heals_3_times(self, auto_lab):
        outcomes, tagged = [], []
        for n in range(3):
            at = T0 + n * 20 * MIN
            assert declare(at - 30)["ok"]
            inc, d = inject(at)
            tagged.append(bool(FD().tag_of(inc) and FD().tag_of(d)))
            outcomes.append((d["outcome"], (d.get("applied") or {}).get("outcome")))
            assert outcomes[-1] == ("heal", "healed"), (f"injection {n + 1}", d["words"])
        assert outcomes == [("heal", "healed")] * 3, outcomes
        assert tagged == [True] * 3 and DS.halted(NET) == {}

    def test_the_same_repeat_undeclared_is_stopped_at_the_second(self, auto_lab):
        _inc, first = inject(T0)
        _inc, second = inject(T0 + 20 * MIN)
        assert first["outcome"] == "heal"
        # Inside the hour guard 9 (the per-device rate) applies first, in section 6's order.
        assert (second["outcome"], second["guard"]["guard"]) == ("held", 9), second["words"]

    def test_the_same_repeat_undeclared_past_the_hour_halts_by_guard_11(self, auto_lab):
        _inc, first = inject(T0)
        _inc, second = inject(T0 + 70 * MIN)
        assert first["outcome"] == "heal"
        assert (second["outcome"], second["guard"]["guard"]) == ("halted", 11), second["words"]
        assert DS.halted(NET)["guard"] == 11, "the network's policy is halted"

    def test_the_same_repeat_declared_past_the_hour_heals_and_halts_nothing(self, auto_lab):
        for at in (T0, T0 + 70 * MIN):
            assert declare(at - 30)["ok"]
            _inc, d = inject(at)
            assert d["outcome"] == "heal", d["words"]
        assert DS.halted(NET) == {}

    @pytest.mark.parametrize("declared", [True, False], ids=("declared", "undeclared"))
    def test_guard_9_alone_two_departures_inside_an_hour(self, auto_lab, declared):
        got = []
        for n, running in enumerate((GOLDEN + ROUTE6, GOLDEN + ROUTE4)):
            at = T0 + n * 20 * MIN
            if declared:
                assert declare(at - 30)["ok"]
            got.append(inject(at, running=running)[1])
        assert _departure(GOLDEN + ROUTE6) != _departure(GOLDEN + ROUTE4)
        if declared:
            assert [d["outcome"] for d in got] == ["heal", "heal"], got[1]["words"]
        else:
            assert (got[1]["outcome"], got[1]["guard"]["guard"]) == ("held", 9)


# ── Nothing else is exempt ──────────────────────────────────────────────────────────────────

class TestNothingElse:
    def _drill_heals(self, n):
        tag = {"id": "fd-0000000000", "declared_by": BY, "expects": EXPECTS,
               "until": iso(T0 + 600)}
        for k in range(n):
            DS.record(NET, {"outcome": "heal", "device": f"o-{k}", "fault_drill": tag}, T0 - 100)

    @pytest.mark.parametrize("declared", [True, False], ids=("a drill", "a real incident"))
    def test_guard_10_counts_drills_and_halts_a_drill(self, auto_lab, declared):
        self._drill_heals(6)
        if declared:
            assert declare(T0 - 30)["ok"]
        _inc, d = inject(T0)
        assert (d["outcome"], d["guard"]["guard"]) == ("halted", 10), d["words"]
        assert d["guard"]["operands"]["heals_last_hour"] == 6

    def test_the_neighbour_hold_still_holds_a_drill(self, auto_lab):
        held = {"held": True, "until": iso(T0 + 3600), "minutes": 60, "changes": [],
                "words": "held until then: Mercury's deploy of core-a, its intent neighbour"}
        assert declare(T0 - 30)["ok"]
        seen = I.sight(NET, DEV, {"kind": "config_change", "key": "cfg:x", "epoch": T0,
                                  "at": iso(T0), "attribution": {"by": "outside"},
                                  "words": "CONFIG_I"}, now=T0)
        I.settle(NET, seen["incident"], {"state": "persisted", "words": "s", "first": 0,
                                         "second": 1,
                                         "operands": {"departure": _departure(GOLDEN + ROUTE6)}},
                 T0 + 100)
        inc = I.claim(NET, seen["incident"], by="test", now=T0 + 120)
        assert FD().tag_of(inc)
        d = DC.decide_one(NET, inc, now=T0 + 130, sources=Fake(GOLDEN + ROUTE6, held=held))
        assert (d["outcome"], d["guard"]["guard"]) == ("held", 5), d["words"]

    def test_only_guards_9_and_11_are_exempt(self):
        assert GD.GUARDS_A_DRILL_PASSES == (9, 11)
        tag = {"id": "fd-1"}
        rows = [{"outcome": "heal", "device": DEV, "departure": "x", "epoch": T0}]
        assert GD.g9_device_rate(rows, DEV, "heal", T0, 1, drill=tag) is None
        assert GD.g11_repeat(rows, DEV, "x", "heal", T0, 24, drill=tag) is None
        assert GD.g9_device_rate(rows, DEV, "heal", T0, 1)["guard"] == 9
        assert GD.g11_repeat(rows, DEV, "x", "heal", T0, 24)["guard"] == 11


# ── Never in the real figures ───────────────────────────────────────────────────────────────

class TestNeverInTheRealFigures:
    def test_a_real_incident_after_a_drills_heal_is_not_counted_against(self, auto_lab):
        assert declare(T0 - 30)["ok"]
        _inc, drill = inject(T0)
        _inc, real = inject(T0 + 20 * MIN)
        assert FD().tag_of(drill) and not FD().tag_of(real)
        assert (drill["outcome"], real["outcome"]) == ("heal", "heal"), real["words"]

    def test_the_dry_run_counts_leave_drills_out(self, lab):  # noqa: F811
        tag = {"id": "fd-1", "declared_by": BY, "expects": EXPECTS, "until": iso(T0)}
        DS.record(NET, {"outcome": "would_heal", "kind": "added_line"}, T0)
        DS.record(NET, {"outcome": "would_heal", "kind": "added_line", "fault_drill": tag}, T0)
        DS.record(NET, {"outcome": "heal", "kind": "added_line", "fault_drill": tag}, T0)
        assert DS.dry_run_counts(NET)["added_line"]["records"] == 1
        assert DS.drill_counts(NET) == {"would_heal": 1, "heal": 1}


# ── The tag, at creation ────────────────────────────────────────────────────────────────────

class TestTheTag:
    def _open(self, at, device=DEV, kind="config_change", related=None):
        t = {"kind": kind, "key": f"{kind}:{device}:{at}", "epoch": at, "at": iso(at),
             "words": "x", **({"related": related} if related else {})}
        got = I.sight(NET, device, t, now=at)
        return next(i for i in I.read(NET)["incidents"] if i["id"] == got["incident"])

    def test_inside_the_drill_it_is_tagged_with_its_shape(self, lab):  # noqa: F811
        r = declare(T0 - 30)["record"]
        inc = self._open(T0)
        assert inc["fault_drill"] == {"id": r["id"], "declared_by": BY, "expects": EXPECTS,
                                      "until": r["until"]}

    def test_another_device_or_after_the_bound_is_real(self, lab):  # noqa: F811
        assert declare(T0 - 30, minutes=1)["ok"]
        assert FD().tag_of(self._open(T0, device="core-a")) is None
        assert FD().tag_of(self._open(T0 + 31)) is None

    def test_a_member_keeps_its_own_tag(self, lab):  # noqa: F811
        assert declare(T0 - 30, device="core-a")["ok"]
        inc = self._open(T0, device=DEV)
        self._open(T0 + 5, device="core-a", kind="adjacency", related=[DEV])
        inc = next(i for i in I.read(NET)["incidents"] if i["id"] == inc["id"])
        (m,) = inc["attached"]
        assert m["device"] == "core-a" and FD().tag_of(m) and FD().tag_of(inc) is None

    def test_the_tag_survives_the_declarations_expiry(self, auto_lab):
        """The exemption is the incident's tag, never the declaration read at the decision: a
        drill decided after its bound is still a drill."""
        DS.record(NET, {"outcome": "heal", "device": DEV, "departure": "y"}, T0 + 20 * MIN)
        assert declare(T0 - 30, minutes=1)["ok"]
        seen = I.sight(NET, DEV, {"kind": "config_change", "key": "cfg:late", "epoch": T0,
                                  "at": iso(T0), "words": "CONFIG_I"}, now=T0)
        I.settle(NET, seen["incident"], {"state": "persisted", "words": "s", "first": 0,
                                         "second": 1,
                                         "operands": {"departure": _departure(GOLDEN + ROUTE6)}},
                 T0 + 25 * MIN)
        ran = DC.run(NET, now=T0 + 30 * MIN, sources=Fake(GOLDEN + ROUTE6))
        (one,) = ran["decided"]
        d = DS.find(NET, one["decision"])
        assert FD().covering(NET, DEV, T0 + 30 * MIN) == {}, "the declaration has expired"
        assert d["outcome"] == "heal" and FD().tag_of(d), d["words"]

    def test_a_tag_that_cannot_be_read_is_real(self, lab, monkeypatch):  # noqa: F811
        assert declare(T0 - 30)["ok"]
        with open(FD().path(NET), "a", encoding="utf-8") as fh:
            fh.write("not json\n")
        assert FD().tag_of(self._open(T0)) is None


# ── The declaration ─────────────────────────────────────────────────────────────────────────

class TestTheDeclaration:
    @pytest.mark.parametrize("kw,words", [
        ({"minutes": 16}, "1 to 15 minutes, and 16 was asked"),
        ({"minutes": 0}, "1 to 15 minutes, and 0 was asked"),
        ({"minutes": "ten"}, "a whole number of minutes"),
        ({"expects": "route added"}, "3 words or more"),
    ])
    def test_its_shape_is_refused_by_name(self, lab, kw, words):  # noqa: F811
        got = declare(T0, **kw)
        assert not got["ok"] and words in got["error"], got

    def test_no_person_and_no_network_are_refused(self, lab):  # noqa: F811
        got = FD().record_declared(NET, DEV, minutes=5, expects=EXPECTS, by="", via="t",
                                   now=T0, inventory=_inv)
        assert not got["ok"] and "declared by a person" in got["error"]
        got = FD().record_declared("Nowhere", DEV, minutes=5, expects=EXPECTS, by=BY, via="t",
                                   now=T0, inventory=_inv)
        assert not got["ok"] and "is no network" in got["error"]

    def test_a_device_not_in_the_network_is_refused(self, lab):  # noqa: F811
        def none(_n, d):
            raise LookupError(f"no device named {d!r}")
        got = FD().record_declared(NET, "nope", minutes=5, expects=EXPECTS, by=BY, via="t",
                                   now=T0, inventory=none)
        assert not got["ok"] and "nope is not a device of Default" in got["error"]

    def test_a_declaration_after_the_fault_is_refused_naming_both_times(self, lab):  # noqa: F811
        seen = I.sight(NET, DEV, {"kind": "config_change", "key": "k", "epoch": T0 - 60,
                                  "at": iso(T0 - 60), "words": "x"}, now=T0 - 60)
        got = declare(T0)
        assert not got["ok"], got
        assert seen["incident"] in got["error"] and iso(T0 - 60) in got["error"] \
            and iso(T0) in got["error"], got["error"]
        assert "never makes it a drill" in got["error"]
        assert FD().declared(NET) == [], "nothing recorded"

    def test_a_second_open_drill_on_the_device_is_refused(self, lab):  # noqa: F811
        first = declare(T0 - 30)["record"]
        got = declare(T0)
        assert not got["ok"] and first["id"] in got["error"] and first["until"] in got["error"]
        assert declare(T0 + 11 * MIN)["ok"], "expired is expired"
        assert declare(T0, device="core-a")["ok"], "another device is its own"

    def test_the_record_and_its_mode(self, lab):  # noqa: F811
        r = declare(T0, script="rehearsal F1", reason="tonight's rehearsal")["record"]
        assert (r["device"], r["device_id"], r["minutes"], r["by"], r["script"]) == \
            (DEV, 41, 10, BY, "rehearsal F1")
        assert r["until"] == iso(T0 + 600) and r["id"].startswith("fd-")
        assert oct(os.stat(FD().path(NET)).st_mode & 0o777) == "0o600"


# ── History ─────────────────────────────────────────────────────────────────────────────────

def _ctx(device=""):
    return {"ref": types.SimpleNamespace(name=NET), "device": device, "limit": 50,
            "since": None, "until": None, "members": None, "inventory": set()}


class TestHistory:
    def test_each_declaration_is_a_row(self, lab):  # noqa: F811
        from modules import history_sources as HS

        r = declare(T0, script="rehearsal F1")["record"]
        (e,) = HS.fault_drills(_ctx())["events"]
        assert e["kind"] == "fault_drill" and e["devices"] == [DEV] and e["who"] == BY
        assert e["what"] == f"Fault drill declared on {DEV}: {EXPECTS}"
        assert ("Until", r["until"]) in e["record"] and ("Script", "rehearsal F1") in e["record"]
        assert HS.SOURCE_KINDS["fault_drills"] == ("fault_drill",)
        assert HS.KIND_FILTERS["fault_drills"] == ("fault_drill",)

    def test_a_drill_heal_says_it_was_a_drill(self, auto_lab):
        from modules import history_sources as HS

        r = declare(T0 - 30)["record"]
        inject(T0)
        inject(T0 + 20 * MIN)       # a real one beside it
        events = HS.heal(_ctx())["events"]
        drills = [e for e in events if e["what"].startswith("Fault drill: ")]
        assert len(events) == 2 and len(drills) == 1, [e["what"] for e in events]
        line = dict(drills[0]["record"])["Fault drill"]
        assert line.startswith(f"{r['id']}, declared by {BY}: {EXPECTS}"), line


# ── Where it is made: the card, the JSON body, the CLI ──────────────────────────────────────

@pytest.fixture
def page(lab, monkeypatch):  # noqa: F811
    """Default holding edge-b, served as the device page reads it."""
    device = {"hostname": DEV, "ip": "192.0.2.6", "device_type": "cisco_xe",
              "platform": "cisco_iosxe", "username": "admin"}
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [dict(device)])
    import app as APP

    return {"client": APP.app.test_client()}


class TestTheCard:
    def test_the_menu_row_opens_the_card(self, page):
        c = page["client"]
        menu = c.get(f"/v2/device/{DEV}/actions?tab=overview").get_data(as_text=True)
        assert f'hx-get="/v2/device/{DEV}/fault-drill?back=overview' in menu
        assert "Declare a fault drill…" in menu
        r = c.get(f"/v2/device/{DEV}/fault-drill?back=overview")
        card = r.get_data(as_text=True)
        assert r.status_code == 200 and f"Declare a fault drill on {DEV}" in card
        assert 'hx-post="/v2/fault-drills/declared' in card and 'value="10"' in card
        assert 'max="15"' in card and "Declare the drill" in card and "Declaring…" in card
        page_html = c.get(f"/v2/device/{DEV}?op=declare_drill").get_data(as_text=True)
        assert f"Declare a fault drill on {DEV}" in page_html
        # Pressed as the card's form sends it: its own fields, and the drill recorded.
        sent = dict(re.findall(r'name="(list|device|back|minutes)"[^>]*value="([^"]*)"', card))
        assert sent == {"list": NET, "device": DEV, "back": "overview", "minutes": "10"}, sent
        r = c.post("/v2/fault-drills/declared", data=dict(sent, expects=EXPECTS))
        assert r.status_code == 200 and [x["device"] for x in FD().declared(NET)] == [DEV]

    def test_declared_the_answer_in_place(self, page):
        r = page["client"].post("/v2/fault-drills/declared", data={
            "list": NET, "device": DEV, "minutes": "10", "expects": EXPECTS, "back": "overview"})
        html = r.get_data(as_text=True)
        (row,) = FD().declared(NET)
        hhmm = row["until"][11:16]
        assert r.status_code == 200, html[:400]
        assert f"Declared: a drill on {DEV} until" in html and f"{hhmm} UTC" in html
        assert (f"Inject the fault now; an incident on {DEV} before") in html and EXPECTS in html
        assert row["by"] == "test-person@example.invalid" and row["via"] == "device page"
        assert r.headers.get("X-NMAS-Invalidates", "").find("fault_drills") >= 0

    def test_a_refusal_is_said_in_place(self, page):
        page["client"].post("/v2/fault-drills/declared", data={
            "list": NET, "device": DEV, "minutes": "10", "expects": EXPECTS})
        r = page["client"].post("/v2/fault-drills/declared", data={
            "list": NET, "device": DEV, "minutes": "10", "expects": EXPECTS})
        html = r.get_data(as_text=True)
        assert r.status_code == 409 and "Couldn't declare the drill: " in html
        assert "one drill per device at a time" in html and "Declare the drill" in html
        assert len(FD().declared(NET)) == 1, "the refused press recorded nothing"

    def test_a_script_declares_with_a_json_body(self, page):
        r = page["client"].post("/v2/fault-drills/declared", json={
            "list": NET, "device": DEV, "minutes": 5, "expects": EXPECTS, "script": "F1"})
        got = r.get_json()
        assert r.status_code == 200 and got["ok"], got
        assert got["record"]["via"] == "api" and got["record"]["script"] == "F1"
        (row,) = FD().declared(NET)
        assert (row["id"], row["minutes"], row["by"]) == (got["record"]["id"], 5,
                                                          "test-person@example.invalid")

    @pytest.mark.real_identity
    def test_a_request_no_verified_person_made_is_refused(self, page):
        r = page["client"].post("/v2/fault-drills/declared", data={
            "list": NET, "device": DEV, "minutes": "10", "expects": EXPECTS})
        assert r.status_code in (401, 403), r.status_code
        assert FD().declared(NET) == []

    def test_the_route_is_gated_for_a_person(self):
        from modules import route_gates

        g = route_gates.GATES["device_v2.fault_drill_declare"]
        assert (g.kind, g.operation) == ("configure", "fault_drill_declare")


def _cli():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts", "nmas-fault-drill")
    loader = importlib.machinery.SourceFileLoader("nmas_fault_drill", path)
    spec = importlib.util.spec_from_loader("nmas_fault_drill", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class TestTheCLI:
    def test_it_records_the_host_login_labelled(self, page, monkeypatch, capsys):
        monkeypatch.setattr("getpass.getuser", lambda: "operator")
        code = _cli().main([NET, DEV, "--minutes", "10", "--expects", EXPECTS,
                            "--script", "rehearsal F1"])
        out = capsys.readouterr().out
        (row,) = FD().declared(NET)
        assert code == 0 and row["by"] == "operator (host login, not a verified identity)"
        assert row["via"] == "nmas-fault-drill" and row["actor_verified"] == "host-shell"
        assert f"declared: a fault drill on {DEV} in {NET} from {row['from']} until " \
               f"{row['until']} ({row['id']})" in out

    def test_a_refusal_exits_1_naming_it(self, page, capsys):
        code = _cli().main([NET, DEV, "--minutes", "20", "--expects", EXPECTS])
        assert code == 1 and "refused: a fault drill lasts 1 to 15 minutes" in \
            capsys.readouterr().err
