"""No fix runs from AI text (docs/HEAL_TO_INTENT.md section 12, the operator's rule of
2026-11-11; docs/MERCURY_CHARTER.md, "The fix-it path"): an AI answer reaches a run only as ONE
operation of Mercury's catalog with validated parameters, a preview, a hash and a verified
person's approval; any other shape is refused and recorded.

- **A, the door** (`modules/ai/fix_proposal.py`, `proposal`; the catalog it holds an answer
  to, `modules/heal/catalog.py`): a well-formed proposal comes back as the operation's own
  preview and hash with nothing sent, held, started or written; every other shape is refused,
  the words naming what was compared and both operands, and the refusal is a use row of the
  call that answered, the reason whole. On tests/test_heal_resubscribe.py's lab (a lab
  router's real configuration on a box, its real intent, no device and no network).
- **B, from a proposal to a run takes a verified person and the hash:** for every catalog
  entry, the function its confirm route runs has no default for who confirms, refuses with
  nothing sent when no hash is given, when the hash is not the previewed one and when the
  actor is not a verified person, and runs with all three; its confirm endpoint is a
  ``confirm`` row of the gate table, which a service and an unidentified request do not pass,
  and its preview endpoint is the one the stages table names for that confirm.
- **C, nothing else reaches a run:** a parsed scan of every module under `modules/ai/`: none
  imports, names or looks up a run function. The run functions are DERIVED (`run_functions`),
  never typed: each catalog entry's run and its job starter; each confirm-gated route's view
  (`route_gates.GATES`' kind ``confirm``, which sends; an approve records a decision and is
  not one) and the verify, rollback and record functions `modules/operation_stages.py` names
  for it (it declares no apply stage: the route's view is the apply); every function that sends to a device, a controller or an HTTP write channel
  (tests/test_every_write_asks_protected.py's three populations, the one definition of a
  send, C101's scan under it) and every function or class of the same file that reaches one
  through the file's own calls; and the device hold's entry points
  (tests/test_session_write_guard.py's `_takes_the_hold`, asked of `device_ops`' functions).
  Floors on both populations, and planted modules in a temporary tree that the scan finds.
- **D, never a retry on its own:** parsed, the run function is called from no loop, no
  ``except`` or ``finally`` and never from itself, in the catalog, the door and the entry's
  module; driven, a run whose verify fails ends as one record with exactly its program sent
  and nothing after it, and another run takes another call with a person and the hashes.
- **E, the document says what the code does:** section 12 holds the operator's sentence
  exactly, his sentence on a saved fix in the bullet directly after it, its Mechanised bullet
  names this file, and the charter's fix-it path holds the rule too.

**What C assumes, and does not see.** Its population is `modules/ai/`: a caller of the
gateway outside it is not scanned (the SDN responder's classification and policy drafting live
in `modules/sdn/`, beside the flow operation they hand a checked answer to). A reference is
read from a module's own imports: a run function reached through another module's function
that is not itself in the derived set (the reads engine, which holds a device to read it), a
callable handed in as an argument, and a name built while running are not seen. **What D does
not claim:** that the hash of a second run differs (an unchanged program has the same hash:
the confirm binds what is sent, not the press), or that an operation's own steps never repeat
a send inside one confirmed run (Re-subscribe's re-add is sent once more if it did not land,
which its preview states).
"""
import ast
import hashlib
import importlib
import inspect
import os
import re

import pytest

from modules.ai import calls
from modules.ai import fix_proposal as FP
from modules.heal import catalog
from tests.source_index import tracked
from tests.test_every_write_asks_protected import controller_sends, device_sends, http_writes
from tests.test_heal_resubscribe import ABSENT, ACTOR, NET, REASON, Src, lab, seq  # noqa: F401
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)
from tests.test_session_write_guard import _takes_the_hold

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: The operator's words (2026-11-11), exactly.
RULE = ("No fix runs from AI text. The AI may propose one operation from Mercury's catalog, "
        "with its parameters; code validates it against intent and the guards, and a person "
        "approves it before it runs. The AI never composes commands, never runs anything "
        "itself, and never retries on its own.")
#: His one sentence more for section 12 (2026-11-11), exactly, capitalised as a sentence.
SAVED = ("A saved fix is the operation a person saved from a verified run, never the AI's "
         "words.")
DOOR = "modules/ai/fix_proposal.py"
CATALOG_FILE = "modules/heal/catalog.py"
#: 38 modules under modules/ai/ on 2026-11-11 (37, and the door).
AI_MODULES_AT_LEAST = 35
#: 136 run functions derived on 2026-11-11.
RUN_FUNCTIONS_AT_LEAST = 120
KEY = "telemetry-resubscribe"
PARAMS = {"device": "r2", "subscriptions": ["101", "102"]}


def answer(**over):
    """A well-formed proposal, with *over* laid on its fields."""
    return dict({"operation": KEY, "params": dict(PARAMS)}, **over)


def with_params(**over):
    return answer(params=dict(PARAMS, **over))


def recorded_call() -> str:
    """A call the record of AI calls holds, as the gateway records one."""
    row = calls.record({"id": calls.new_id(), "feature": "explain", "actor": ACTOR,
                        "verdict": "ok"})
    assert row["recorded"]
    return row["id"]


def folder() -> dict:
    """Every file of the test's own store, by its sha256."""
    from modules import config

    out = {}
    for base, _dirs, names in os.walk(config.DATA_DIR):
        for name in names:
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, config.DATA_DIR)] = hashlib.sha256(
                    fh.read()).hexdigest()
    return out


@pytest.fixture
def nothing_runs(monkeypatch):
    """Stand-ins that fail when used: a session, a device hold, a job, a read of a device.
    What was used is kept, so a caller that swallowed the failure is still found."""
    used = []

    def fails(what):
        def stand_in(*_a, **_kw):
            used.append(what)
            raise AssertionError(f"{what} was used")
        return stand_in

    monkeypatch.setattr("modules.connection.open_ssh", fails("a session"))
    monkeypatch.setattr("modules.nsot.device_ops.acquire", fails("a device hold"))
    monkeypatch.setattr("modules.nsot.device_ops.acquire_many", fails("a hold of several"))
    monkeypatch.setattr("modules.nsot.capture_job.start", fails("a job"))
    monkeypatch.setattr("modules.nsot.reads.run", fails("a read of a device"))
    return used


def quiet_src(used) -> Src:
    """The lab's sources with a session that fails on any use."""
    src = Src()

    def opener(_dev):
        used.append("the operation's session")
        raise AssertionError("the operation's session was opened")
    src.opener = opener
    return src


def ask(ans, src, call_id, **over):
    kw = {"network": NET, "call_id": call_id, "actor": ACTOR, "actor_verified": "access",
          "sources": src}
    kw.update(over)
    return FP.proposal(ans, **kw)


# ── A: the door ─────────────────────────────────────────────────────────────────────────────

class TestTheDoor:
    def test_a_well_formed_proposal_is_the_operations_preview_and_hash_and_nothing_else(
            self, lab, nothing_runs):  # noqa: F811
        from modules.heal import resubscribe as R
        from routes import resubscribe_v2

        src, cid = quiet_src(nothing_runs), recorded_call()
        before = folder()
        got = ask(answer(), src, cid)
        p = R.plan(NET, "r2", ["101", "102"], sources=src)
        assert p["ok"] and len(p["hash"]) == 16
        assert got == {"ok": True, "operation": R.KEY, "params": PARAMS,
                       "preview": resubscribe_v2._masked(p), "hash": p["hash"]}
        assert [u["hash"] for u in got["preview"]["units"]] == [u["hash"] for u in p["units"]]
        assert got["preview"]["units"][0]["remove"] == p["units"][0]["remove"]
        # Nothing sent, held, started or written: not even a use row.
        assert nothing_runs == [] and src.box.batches == [] and src.box.opened == 0
        assert folder() == before
        assert calls.find(cid)["uses"] == []

    def test_what_it_returns_is_what_the_confirm_takes(self, lab):  # noqa: F811
        """The preview's hashes are the ones the operation's run is bound to: confirmed with
        them by a verified person it runs, and what is sent is the program previewed."""
        from modules.heal import resubscribe as R

        src = Src()
        got = ask(answer(), src, recorded_call())
        rec = R.apply(NET, "r2", got["params"]["subscriptions"], actor=ACTOR,
                      actor_verified="access", person=True,
                      confirmed={u["sub"]: u["hash"] for u in got["preview"]["units"]},
                      program=got["hash"], previewed="101,102", reason=REASON, sources=src)
        assert rec["outcome"] == "resubscribed", rec["why"]
        assert [ln for b in src.box.batches for ln in b] == [
            ln for u in got["preview"]["units"] for ln in u["remove"]] + [
            ln for u in got["preview"]["units"] for ln in u["readd"]]

    CASES = {
        # ── an operation not in the catalog
        "another operation": (answer(operation="reload-device"), "not_in_catalog",
                              ["an operation of the catalog (telemetry-resubscribe)",
                               "this one names 'reload-device'"]),
        "the re-add, a real operation the catalog does not hold": (
            answer(operation="telemetry-readd"), "not_in_catalog", ["names 'telemetry-readd'"]),
        # ── two operations, and none
        "two operations": (answer(operation=[KEY, KEY]), "not_one_operation",
                           ["names exactly one operation", "this one names 2"]),
        "a list of two proposals": ([answer(), answer()], "not_one_operation",
                                    ["one operation with its parameters", "a list of 2"]),
        "an operations list": (dict(answer(), operations=[answer(), answer()]),
                               "unknown_field", ["exactly the fields operation and params",
                                                 "also holds 'operations'"]),
        "no operation": ({"params": dict(PARAMS)}, "not_one_operation",
                         ["names exactly one operation", "this one names none"]),
        "an empty list of operations": (answer(operation=[]), "not_one_operation",
                                        ["this one names none"]),
        "an empty object": ({}, "not_one_operation", ["this one names none"]),
        "an empty list": ([], "not_one_operation", ["a list of 0"]),
        "an operation of nothing": (answer(operation=None), "not_one_operation",
                                    ["this one names none"]),
        "an operation of no text": (answer(operation=""), "not_one_operation",
                                    ["this one names none"]),
        # ── a parameter of the wrong type
        "a device that is a number": (with_params(device=7), "wrong_shape", [
            "parameter device is one name the network's inventory holds", "gave a number"]),
        "a device that is a list": (with_params(device=["r2"]), "wrong_shape",
                                    ["gave a list"]),
        "subscriptions as text": (with_params(subscriptions="101"), "wrong_shape", [
            "parameter subscriptions is a list of 1 to 20 subscription ids", "gave text"]),
        "a subscription that is a number": (with_params(subscriptions=[101]), "wrong_shape",
                                            ["a list holding a number (101)"]),
        "a subscription that is true": (with_params(subscriptions=[True]), "wrong_shape",
                                        ["a list holding true/false"]),
        "parameters that are a list": (answer(params=["r2", "101"]), "wrong_type", [
            "parameters are an object giving device and subscriptions", "gave a list"]),
        "an operation that is a number": (answer(operation=7), "wrong_type",
                                          ["as text", "gave a number"]),
        "an operation that is true": (answer(operation=True), "wrong_type",
                                      ["gave true/false"]),
        # ── an unknown extra field
        "an extra field": (dict(answer(), note="it is stuck"), "unknown_field",
                           ["exactly the fields operation and params", "also holds 'note'"]),
        "an extra parameter": (with_params(vrf="Mgmt"), "unknown_parameter", [
            "takes exactly the parameters device and subscriptions", "also gives 'vrf'"]),
        "no parameters": (answer(params={}), "missing_parameter",
                          ["gives no device and subscriptions"]),
        "a parameter left out": (answer(params={"device": "r2"}), "missing_parameter",
                                 ["gives no subscriptions"]),
        "no params field": ({"operation": KEY}, "missing_field", ["holds no params"]),
        # ── a device the inventory does not hold; a subscription intent does not declare
        "a device the inventory does not hold": (
            with_params(device="r9"), "refused_by_plan",
            ["own plan refused the proposal for Default", "r9 is not a device of Default"]),
        "a subscription intent does not declare": (
            with_params(subscriptions=["103"]), "refused_by_plan",
            ["intent declares no telemetry subscription 103 on r2 (2 declared)"]),
        "an id past the device's range": (
            with_params(subscriptions=["4294967296"]), "refused_by_plan",
            ["'4294967296' is not a telemetry subscription id"]),
        # ── a subscription id that is not digits
        "an id with a letter": (with_params(subscriptions=["10a"]), "wrong_shape", [
            "each text of 1 to 10 digits", "a list holding '10a'"]),
        "an id with a space": (with_params(subscriptions=[" 101"]), "wrong_shape",
                               ["a list holding ' 101'"]),
        "a negative id": (with_params(subscriptions=["-1"]), "wrong_shape",
                          ["a list holding '-1'"]),
        "digits that are not ASCII": (with_params(subscriptions=["１０１"]), "wrong_shape",
                                      ["a list holding"]),
        "eleven digits": (with_params(subscriptions=["12345678901"]), "wrong_shape",
                          ["a list holding '12345678901'"]),
        "an id twice": (with_params(subscriptions=["101", "101"]), "wrong_shape",
                        ["each once", "a list naming 101 more than once"]),
        "no ids": (with_params(subscriptions=[]), "wrong_shape", ["a list of 0"]),
        "more ids than the card takes": (
            with_params(subscriptions=[str(n) for n in range(21)]), "wrong_shape",
            ["a list of 1 to 20", "a list of 21"]),
        # ── free-text CLI in any field: outside the schema, never matched as a pattern
        "a command as the device": (with_params(device="configure terminal"), "wrong_shape", [
            "printable ASCII characters, no space", "'configure terminal' (18 characters)"]),
        "a newline in the device": (with_params(device="r2\nreload"), "wrong_shape",
                                    ["gave 'r2\\nreload' (9 characters)"]),
        "a semicolon in the device": (with_params(device="r2;reload"), "refused_by_plan",
                                      ["r2;reload is not a device of Default"]),
        "a command after an id": (with_params(subscriptions=["101; reload"]), "wrong_shape",
                                  ["a list holding '101; reload'"]),
        "a newline after an id": (with_params(subscriptions=["101\n no receiver"]),
                                  "wrong_shape", ["a list holding '101\\n no receiver'"]),
        "a command as the operation": (answer(operation="configure terminal"),
                                       "not_in_catalog", ["names 'configure terminal'"]),
        "a command after the key": (answer(operation=KEY + "; reload"), "not_in_catalog",
                                    ["names 'telemetry-resubscribe; reload'"]),
        # ── a commands or program field
        "a commands field": (dict(answer(), commands=["configure terminal",
                                                      "no telemetry ietf subscription 101"]),
                             "unknown_field", ["also holds 'commands'",
                                               "refused, whatever it holds"]),
        "a program field": (dict(answer(), program="configure terminal\nend"),
                            "unknown_field", ["also holds 'program'"]),
        "a commands parameter": (with_params(commands=["reload"]), "unknown_parameter",
                                 ["also gives 'commands'", "refused, whatever it holds"]),
        "a program parameter": (with_params(program=["reload"]), "unknown_parameter",
                                ["also gives 'program'"]),
        # ── a retry or run flag
        "a retry flag": (dict(answer(), retry=True), "unknown_field", ["also holds 'retry'"]),
        "a run flag": (dict(answer(), run=True), "unknown_field", ["also holds 'run'"]),
        "a retry parameter": (with_params(retry=3), "unknown_parameter",
                              ["also gives 'retry'"]),
        "a run parameter": (with_params(run="now"), "unknown_parameter", ["also gives 'run'"]),
        # ── an answer that is not an object
        "text": ("reload r2", "not_an_object", ["an object holding operation and params",
                                                "the answer is text"]),
        "nothing": (None, "not_an_object", ["the answer is nothing"]),
        "a number": (7, "not_an_object", ["the answer is a number"]),
        "true": (True, "not_an_object", ["the answer is true/false"]),
    }

    @pytest.mark.parametrize("name", sorted(CASES))
    def test_any_other_shape_is_refused_and_recorded(self, lab, nothing_runs,  # noqa: F811
                                                     name):
        ans, code, said = self.CASES[name]
        src, cid = quiet_src(nothing_runs), recorded_call()
        before = folder()
        got = ask(ans, src, cid)
        assert (got["ok"], got["code"]) == (False, code), got
        assert set(got) == {"ok", "code", "refused", "recorded"}
        for words in said:
            assert words in got["refused"], got["refused"]
        assert got["refused"].endswith("Nothing was previewed, and nothing runs")
        # Recorded, on the call's own use record, the reason whole.
        assert got["recorded"] is True
        (use,) = calls.find(cid)["uses"]
        assert (use["use"], use["actor"]) == ("refused by validation", ACTOR)
        assert got["refused"] in use["detail"]
        assert f"({code}; proposed for {NET}; asked by {ACTOR}, verified access)" in \
            use["detail"]
        # And nothing else: nothing sent, held or started, and only that row written.
        assert nothing_runs == [] and src.box.batches == [] and src.box.opened == 0
        after = folder()
        assert {k for k in set(before) | set(after) if before.get(k) != after.get(k)} == {
            "ai_calls.jsonl"}

    def test_a_long_value_is_said_bounded_and_the_reason_is_still_kept_whole(
            self, lab, nothing_runs):  # noqa: F811
        cid = recorded_call()
        long = "show running-config | " * 40
        got = ask(with_params(device=long), quiet_src(nothing_runs), cid)
        assert got["code"] == "wrong_shape"
        assert f"… ({len(long)} characters)" in got["refused"]
        assert long not in got["refused"] and len(got["refused"]) < 500
        assert got["refused"] in calls.find(cid)["uses"][0]["detail"]

    @pytest.mark.parametrize("call_id,said", [
        ("", "it came with no call id"),
        (None, "it came with no call id"),
        ("ai-0000000000000000", "holds no call 'ai-0000000000000000'"),
        (7, "a number for its call id"),
    ])
    def test_an_answer_of_no_recorded_call_is_refused_even_well_formed(
            self, lab, nothing_runs, call_id, said):  # noqa: F811
        src = quiet_src(nothing_runs)
        got = ask(answer(), src, call_id)
        assert (got["ok"], got["code"], got["recorded"]) == (False, "no_call", True)
        assert "a proposal is the answer of a recorded AI call" in got["refused"]
        assert said in got["refused"]
        # Kept all the same, as a use of the id it gave (or of none).
        (use,) = calls.uses()[call_id if isinstance(call_id, str) else ""]
        assert got["refused"] in use["detail"] and use["use"] == "refused by validation"
        assert nothing_runs == [] and src.box.opened == 0

    def test_who_asked_is_kept_with_the_refusal_and_approves_nothing(
            self, lab, nothing_runs):  # noqa: F811
        """The door takes who asked for its record alone: an unverified asker gets the same
        preview (the approval is the confirm's), and a refusal names them as they came."""
        src, cid = quiet_src(nothing_runs), recorded_call()
        got = ask(answer(), src, cid, actor="", actor_verified="")
        assert got["ok"] and calls.find(cid)["uses"] == []
        got = ask(answer(operation="reload-device"), src, cid, actor="", actor_verified="")
        (use,) = calls.find(cid)["uses"]
        assert use["actor"] == "" and "asked by nobody, verified none)" in use["detail"]

    def test_the_catalogs_own_check_reads_and_writes_nothing(self, lab,  # noqa: F811
                                                             nothing_runs):
        before = folder()
        got = catalog.preview(KEY, dict(PARAMS), network=NET, sources=quiet_src(nothing_runs))
        assert got["ok"] and set(got) == {"ok", "operation", "params", "preview", "hash"}
        bad = catalog.preview(KEY, dict(PARAMS, commands=["reload"]), network=NET,
                              sources=quiet_src(nothing_runs))
        assert (bad["ok"], bad["code"]) == (False, "unknown_parameter")
        assert folder() == before and nothing_runs == []


# ── The catalog ─────────────────────────────────────────────────────────────────────────────

def _resolve(dotted: str):
    mod, _, attr = dotted.rpartition(".")
    return getattr(importlib.import_module(mod), attr)


@pytest.fixture(scope="module")
def app():
    import app as A
    return A.app


class TestTheCatalog:
    def test_it_holds_re_subscribe_and_each_entry_is_whole(self, app):
        from modules.heal import resubscribe as R

        assert set(catalog.CATALOG) == {R.KEY} == {KEY}
        endpoints = {r.endpoint for r in app.url_map.iter_rules()}
        for key, op in catalog.CATALOG.items():
            assert op.key == key
            assert [f for f in op.__dataclass_fields__] == [
                "key", "words", "params", "plan", "drawn", "preview_endpoint",
                "confirm_endpoint", "runs"]
            assert op.params and all(p.name and p.takes and callable(p.refusal)
                                     for p in op.params)
            assert {op.preview_endpoint, op.confirm_endpoint} <= endpoints
            run = _resolve(op.runs)
            assert inspect.isfunction(run), op.runs
            # What it holds that can be called is the catalog's own: its plan's adapter, how
            # the plan is drawn, and each parameter's check. The run is a name.
            held = [op.plan, op.drawn] + [p.refusal for p in op.params]
            assert {f.__module__ for f in held} == {"modules.heal.catalog"}
            assert isinstance(op.runs, str) and run not in held

    def test_re_subscribes_plan_is_the_operations_own(self, lab):  # noqa: F811
        """The entry's plan is `resubscribe.plan`, called: the same answer, hash for hash."""
        from modules.heal import resubscribe as R

        src = Src()
        op = catalog.CATALOG[R.KEY]
        mine = op.plan(NET, dict(PARAMS), src)
        theirs = R.plan(NET, "r2", ["101", "102"], sources=src)
        assert mine == theirs and mine["ok"]
        assert op.runs == f"{R.apply.__module__}.{R.apply.__name__}"


# ── B: from a proposal to a run takes a verified person and the hash ────────────────────────

class ResubscribeDrive:
    """Re-subscribe's run driven on tests/test_heal_resubscribe.py's lab, one subscription."""
    no_hash = [{"confirmed": {}, "program": ""}, {"confirmed": None, "program": ""}]
    wrong_hash = [{"confirmed": {"101": "0" * 16}}, {"program": "0" * 16},
                  {"program": ""}]

    def __init__(self, **sources):
        self.src = Src(**sources)

    def plan(self):
        from modules.heal import resubscribe as R
        return R.plan(NET, "r2", ["101"], sources=self.src)

    def run(self, fn, **over):
        p = self.plan()
        kw = {"actor": ACTOR, "actor_verified": "access", "person": True,
              "confirmed": {u["sub"]: u["hash"] for u in p["units"]}, "program": p["hash"],
              "previewed": "101", "reason": REASON}
        kw.update(over)
        return fn(NET, "r2", ["101"], sources=self.src, **kw)

    def sent(self) -> list:
        return [ln for b in self.src.box.batches for ln in b]

    def opened(self) -> int:
        return self.src.box.opened

    def records(self) -> list:
        from modules.nsot import privileged
        return privileged.runs(NET)["runs"]

    def stored(self, rec) -> dict:
        from modules.nsot import privileged
        return privileged.get(NET, rec["id"])

    def failing(self):
        """A drive whose verify fails: the stream's series never comes back."""
        return type(self)(series=seq([ABSENT]))


#: How each catalog entry's run is driven; an entry with no drive fails (`TestToARun`).
DRIVES = {KEY: ResubscribeDrive}


def _not_a_person() -> list:
    from modules import identity

    return [{"actor_verified": ""}, {"actor_verified": "none"}, {"actor_verified": None},
            {"actor_verified": "system"}, {"actor_verified": "policy"},
            {"actor_verified": "host"}, {"actor_verified": "service"}, {"person": False},
            {"person": "yes"}, {"person": None}, {"actor": ""},
            {"actor": identity.UNVERIFIED}]


class TestToARun:
    def test_every_entry_is_driven(self):
        assert set(DRIVES) == set(catalog.CATALOG)

    @pytest.mark.parametrize("key", sorted(catalog.CATALOG))
    def test_who_confirms_is_never_defaulted(self, key):
        params = inspect.signature(_resolve(catalog.CATALOG[key].runs)).parameters
        for name in ("actor", "actor_verified", "person"):
            assert name in params, f"{key}'s run takes no {name}"
            assert params[name].default is inspect.Parameter.empty, (
                f"{key}'s run has a default for {name}")
            assert params[name].kind is inspect.Parameter.KEYWORD_ONLY

    @pytest.mark.parametrize("key", sorted(catalog.CATALOG))
    def test_no_hash_and_a_hash_not_previewed_are_refused_with_nothing_sent(
            self, lab, key):  # noqa: F811
        run = _resolve(catalog.CATALOG[key].runs)
        cases = DRIVES[key].no_hash + DRIVES[key].wrong_hash
        for n, case in enumerate(cases, 1):
            d = DRIVES[key]()
            rec = d.run(run, **case)
            assert rec["outcome"] == "refused", (case, rec["outcome"])
            assert d.sent() == [] and d.opened() == 0, case
            kept = d.stored(rec)
            assert kept["outcome"] == "refused" and len(d.records()) == n
            assert "Nothing was sent" in kept["why"], kept["why"]
        d = DRIVES[key]()
        why = d.run(run, **DRIVES[key].wrong_hash[0])["why"]
        assert "confirmed 0000000000000000, now " + d.plan()["units"][0]["hash"] in why

    @pytest.mark.parametrize("key", sorted(catalog.CATALOG))
    def test_one_who_is_not_a_verified_person_is_refused_with_nothing_sent(
            self, lab, key):  # noqa: F811
        run = _resolve(catalog.CATALOG[key].runs)
        for n, case in enumerate(_not_a_person(), 1):
            d = DRIVES[key]()
            rec = d.run(run, **case)
            assert rec["outcome"] == "refused", (case, rec["outcome"])
            assert d.sent() == [] and d.opened() == 0, case
            assert "is confirmed by a verified person, and this request is not one" in \
                rec["why"], rec["why"]
            kept = d.stored(rec)
            assert len(d.records()) == n
            # Recorded as it was stated: a kind nobody gave is "none", never a default.
            stated = case["actor_verified"] if "actor_verified" in case else "access"
            assert kept["actor_verified"] == (stated or "none")

    @pytest.mark.parametrize("key", sorted(catalog.CATALOG))
    def test_it_runs_with_the_previewed_hash_and_a_verified_person(self, lab,  # noqa: F811
                                                                  key):
        from modules import identity

        run = _resolve(catalog.CATALOG[key].runs)
        assert len(identity.REQUEST_VERIFICATIONS) >= 2
        for n, how in enumerate(identity.REQUEST_VERIFICATIONS, 1):
            d = DRIVES[key]()
            program = d.plan()["program"]
            rec = d.run(run, actor_verified=how)
            assert rec["outcome"] not in ("refused", "running"), rec["why"]
            assert d.sent() == program and program
            kept = d.stored(rec)
            assert len(d.records()) == n
            assert (kept["actor"], kept["actor_verified"], kept["key"]) == (ACTOR, how, key)

    @pytest.mark.parametrize("key", sorted(catalog.CATALOG))
    def test_its_confirm_is_a_confirm_gate_and_its_preview_that_confirms_own(self, app, key):
        from modules import identity
        from modules import operation_stages as S
        from modules import route_gates as G

        op = catalog.CATALOG[key]
        gate = G.GATES[op.confirm_endpoint]
        assert gate.kind == G.C == "confirm"
        # The confirm class needs a person: an unidentified request and a verified service
        # are refused by the gate's own rule, a verified person is not.
        nobody = identity.Identity()
        service = identity.Identity(actor="service:ci", kind="service", service_id="ci",
                                    verified=True, outcome="ok", peer="192.0.2.7",
                                    peer_trusted=True, header_present=True)
        person = identity.Identity(actor=ACTOR, email=ACTOR, kind="person", verified=True,
                                   outcome="ok", peer="192.0.2.7", peer_trusted=True,
                                   header_present=True)
        assert identity.may(nobody, gate.kind, gate.operation)[0] is False
        assert identity.may(service, gate.kind, gate.operation)[0] is False
        assert identity.may(person, gate.kind, gate.operation) == (True, "")
        # Its preview is the one the stages table names for that confirm, and it changes
        # nothing: every method it answers is a safe one, or its gate says not_device.
        assert S.STAGES[op.confirm_endpoint].preview == op.preview_endpoint
        methods = set().union(*(r.methods for r in app.url_map.iter_rules()
                                if r.endpoint == op.preview_endpoint))
        assert methods and (methods <= G.SAFE_METHODS
                            or G.GATES[op.preview_endpoint].kind == G.NOT_DEVICE)
        # And the confirm's view reaches the entry's run: by its job starter or itself.
        view = inspect.unwrap(app.view_functions[op.confirm_endpoint])
        tree = ast.parse(inspect.getsource(inspect.getmodule(view)))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == view.__name__)
        reached = {name for _line, name in references(ast.unparse(node))}
        assert reached & ({op.runs} | starters(op.runs)), (op.confirm_endpoint, reached)


# ── C: nothing else reaches a run ───────────────────────────────────────────────────────────

def _source(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _module(rel: str) -> str:
    """A product file's dotted module name, or ``""`` (a script is no importable module)."""
    if not rel.endswith(".py") or not rel.startswith(("modules/", "routes/", "app.py")):
        return ""
    return rel[:-3].replace("/", ".")


def _calls(node) -> set:
    """The names *node* calls: ``f(...)`` as ``f``, ``x.f(...)`` as ``f``."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                out.add(n.func.id)
            elif isinstance(n.func, ast.Attribute):
                out.add(n.func.attr)
    return out


def reaching(source: str, seeds: set) -> set:
    """The module-level functions and classes of *source* that hold a function named in
    *seeds*, or that call, by the file's own names, one that does (to a fixed point)."""
    units = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            inner = {n.name for n in ast.walk(node)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            units[node.name] = (inner | {node.name}, _calls(node))
    hit = {name for name, (inner, _called) in units.items() if inner & seeds}
    while True:
        more = {name for name, (_inner, called) in units.items()
                if name not in hit and called & (hit | seeds)}
        if not more:
            return hit
        hit |= more


def starters(run: str) -> set:
    """The functions of a run function's module that call it (its job starter), dotted."""
    module, _, name = run.rpartition(".")
    rel = module.replace(".", "/") + ".py"
    return {f"{module}.{n}" for n in reaching(_source(rel), {name})} - {run}


def senders() -> dict:
    """``{file: {function names}}``: every function that sends to a device, a controller or
    an HTTP write channel, by tests/test_every_write_asks_protected.py's three populations."""
    out = {}
    for rel, name in device_sends():
        out.setdefault(rel, set()).add(name)
    for rel, name, _said in controller_sends():
        out.setdefault(rel, set()).add(name)
    for rel, name in http_writes():
        out.setdefault(rel, set()).add(name)
    return out


def hold_entries() -> set:
    """`device_ops`' functions a call of which takes the hold, by the session write guard's
    own definition (`_takes_the_hold`), dotted."""
    from modules.nsot import device_ops

    out = set()
    for name, value in vars(device_ops).items():
        if inspect.isfunction(value) and value.__module__ == device_ops.__name__:
            func = ast.parse(f"def f():\n    device_ops.{name}()\n").body[0]
            if _takes_the_hold(func):
                out.add(f"{device_ops.__name__}.{name}")
    return out


def run_functions(app) -> dict:
    """``{dotted name: why it is a run function}``, each set derived (the module's
    docstring): nothing here is a typed list of names."""
    from modules import operation_stages as S
    from modules import route_gates as G

    out = {}
    for key, op in catalog.CATALOG.items():
        out[op.runs] = f"the catalog's {key}: its run"
        for name in starters(op.runs):
            out.setdefault(name, f"the catalog's {key}: it starts the run")
    for endpoint, stages in S.STAGES.items():
        if G.GATES[endpoint].kind != G.C:
            continue                                  # an approve records; a confirm sends
        view = app.view_functions.get(endpoint)
        if view is not None:
            view = inspect.unwrap(view)
            out.setdefault(f"{view.__module__}.{view.__name__}",
                           f"the gated route {endpoint}'s view")
        for stage in ("verify", "rollback", "record"):
            value = getattr(stages, stage)
            if re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)+", value):
                out.setdefault(value, f"{endpoint}'s {stage}")
    for rel, names in senders().items():
        module = _module(rel)
        if not module:
            continue
        for name in reaching(_source(rel), names):
            out.setdefault(f"{module}.{name}", f"sends, or reaches a send in {rel}")
    for name in hold_entries():
        out.setdefault(name, "takes the device hold")
    return out


def _dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return ".".join([node.id] + parts[::-1])
    return ""


def bindings(tree, package: str = "") -> tuple:
    """``({local name: the dotted name it is bound to}, [(line, dotted name imported)])`` for
    every import in *tree*, wherever it is written (a function's own import binds too). An
    ``import a.b`` binds ``a``; an ``import a.b as c`` binds ``c`` to ``a.b``; a ``from a
    import b as c`` binds ``c`` to ``a.b``. *package* resolves a relative import."""
    bound, imported = {}, []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                bound[a.asname or a.name.split(".")[0]] = (
                    a.name if a.asname else a.name.split(".")[0])
                imported.append((node.lineno, a.name))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                up = package.split(".")[:len(package.split(".")) - (node.level - 1)]
                base = ".".join(up + ([base] if base else []))
            for a in node.names:
                bound[a.asname or a.name] = f"{base}.{a.name}"
                imported.append((node.lineno, f"{base}.{a.name}"))
    return bound, imported


def resolved(expr, bound: dict) -> str:
    """The dotted name an expression reaches through *bound* (``c.d`` is ``a.b.d`` where ``c``
    is bound to ``a.b``, so an alias is followed), or ``""``."""
    name = _dotted(expr)
    root, _, rest = name.partition(".")
    if root not in bound:
        return ""
    return bound[root] + (f".{rest}" if rest else "")


def references(source: str, package: str = "") -> list:
    """``[(line, dotted name)]``: every name *source* reaches through its imports, parsed
    (never matched as text; a docstring or a comment names nothing): each import, each
    attribute of a bound name (`resolved`), a ``getattr(c, "d")`` of a constant (``a.b.d``),
    and an ``import_module("a.b")`` or ``__import__("a.b")`` of a constant (``a.b.*``)."""
    tree = ast.parse(source)
    bound, out = bindings(tree, package)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            name = resolved(node, bound)
            if name:
                out.append((node.lineno, name))
        elif isinstance(node, ast.Call):
            called = _dotted(node.func).rpartition(".")[2]
            text = [a.value for a in node.args
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if called == "getattr" and len(node.args) >= 2 and text:
                base = resolved(node.args[0], bound)
                if base:
                    out.append((node.lineno, f"{base}.{text[0]}"))
            elif called in ("import_module", "__import__") and text:
                out.append((node.lineno, f"{text[0]}.*"))
    return sorted(set(out))


def reached(files: dict, run: dict) -> list:
    """``[(file, line, name, why)]``: each reference in *files* (``{path: source}``) to a run
    function: the function itself, anything under it, or its whole module looked up by name
    or star-imported."""
    out = []
    modules = {name.rpartition(".")[0] for name in run}
    for rel, source in sorted(files.items()):
        package = os.path.dirname(rel).replace("/", ".")
        for line, name in references(source, package):
            hit = next((r for r in run if name == r or name.startswith(r + ".")), None)
            if hit is None and name.endswith(".*") and name[:-2] in modules:
                hit = name
            if hit is not None:
                out.append((rel, line, name, run.get(hit, "its whole module, by name")))
    return out


def ai_modules() -> dict:
    return {os.path.relpath(p, ROOT): _source(os.path.relpath(p, ROOT))
            for p in tracked("modules/ai", suffix=".py")}


@pytest.fixture(scope="module")
def run(app):
    return run_functions(app)


class TestNothingElseReachesARun:
    def test_the_populations_have_their_floors(self, run):
        files = ai_modules()
        assert len(files) >= AI_MODULES_AT_LEAST, len(files)
        assert {DOOR, "modules/ai/gateway.py", "modules/ai/heal_analysis.py",
                "modules/ai/read_loop.py", "modules/ai/explain.py"} <= set(files)
        assert len(run) >= RUN_FUNCTIONS_AT_LEAST, len(run)
        # One of each kind the derivation finds, each by its own path.
        for name in ("modules.heal.resubscribe.apply", "modules.heal.resubscribe.start",
                     "routes.resubscribe_v2.confirm", "modules.pipeline._stage_rollback",
                     "modules.pipeline._push_via_netmiko", "modules.sdn.flow_ops.apply",
                     "modules.sdn.flow_ops._send", "modules.nsot.device_ops.hold",
                     "modules.nsot.device_ops.acquire_many",
                     "modules.sdn.drivers.base.ControllerDriver"):
            assert name in run, name
        # A plan, a read and a preview are no run.
        for name in ("modules.heal.resubscribe.plan", "modules.heal.catalog.preview",
                     "modules.sdn.flow_ops.plan", "modules.nsot.device_ops.holder",
                     "routes.resubscribe_v2.preview"):
            assert name not in run, name

    def test_no_ai_module_reaches_a_run_function(self, run):
        found = reached(ai_modules(), run)
        assert found == [], "\n".join(f"{f}:{ln} reaches {n} ({why})"
                                      for f, ln, n, why in found)

    def test_the_door_and_the_catalog_reach_none_and_never_resolve_the_run(self, run):
        files = {DOOR: _source(DOOR), CATALOG_FILE: _source(CATALOG_FILE)}
        assert reached(files, run) == []
        for rel, source in files.items():
            tree = ast.parse(source)
            loads = [n.lineno for n in ast.walk(tree)
                     if isinstance(n, ast.Attribute) and n.attr == "runs"]
            lookups = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
                       and _dotted(n.func).rpartition(".")[2] in (
                           "import_module", "__import__", "getattr", "eval", "exec")]
            assert loads == [] and lookups == [], (rel, loads, lookups)

    def test_only_the_door_takes_an_answer_to_the_catalog(self):
        using = {rel for rel, source in ai_modules().items()
                 if any(name == "modules.heal.catalog" or name.startswith("modules.heal.catalog.")
                        for _line, name in references(source, "modules.ai"))}
        assert using == {DOOR}

    PLANTED = {
        "direct": ("from modules.heal.resubscribe import apply\n\n"
                   "def fix(net, ans):\n"
                   "    return apply(net, ans['device'], ans['subs'], actor='ai',\n"
                   "                 actor_verified='access', person=True, confirmed={})\n",
                   "modules.heal.resubscribe.apply"),
        "alias": ("def fix(net, ans):\n"
                  "    from modules.heal import resubscribe as R\n"
                  "    go = R.apply\n"
                  "    return go(net, ans['device'], ans['subs'])\n",
                  "modules.heal.resubscribe.apply"),
        "starter": ("import modules.heal.resubscribe as op\n\n"
                    "def fix(net, ans):\n    return op.start(net, **ans)\n",
                    "modules.heal.resubscribe.start"),
        "flows": ("from modules.sdn import flow_ops\n\n"
                  "def fix(net, ask, h):\n"
                  "    return flow_ops.apply(net, ask, h, actor='ai')\n",
                  "modules.sdn.flow_ops.apply"),
        "module path": ("import modules.sdn.flow_ops\n\n"
                        "def fix(net, ask, h):\n"
                        "    return modules.sdn.flow_ops.apply(net, ask, h, actor='ai')\n",
                        "modules.sdn.flow_ops.apply"),
        "hold": ("from modules.nsot import device_ops\n\n"
                 "def fix(net, host):\n"
                 "    with device_ops.hold(net, host, 'fix', 'ai'):\n        pass\n",
                 "modules.nsot.device_ops.hold"),
        "pipeline": ("from modules.pipeline import _push_via_netmiko as push\n",
                     "modules.pipeline._push_via_netmiko"),
        "a route's view": ("from routes.resubscribe_v2 import confirm\n",
                           "routes.resubscribe_v2.confirm"),
        "getattr": ("from modules.heal import resubscribe\n\n"
                    "def fix(*a):\n    return getattr(resubscribe, 'apply')(*a)\n",
                    "modules.heal.resubscribe.apply"),
        "by name": ("import importlib\n\n"
                    "def fix(*a):\n"
                    "    op = importlib.import_module('modules.heal.resubscribe')\n"
                    "    return op.apply(*a)\n",
                    "modules.heal.resubscribe.*"),
        "relative": ("from ..heal.resubscribe import apply\n",
                     "modules.heal.resubscribe.apply"),
    }

    @pytest.mark.parametrize("name", sorted(PLANTED))
    def test_a_planted_ai_module_reaching_a_run_is_found(self, run, tmp_path, name):
        source, want = self.PLANTED[name]
        folder_ = tmp_path / "modules" / "ai"
        folder_.mkdir(parents=True)
        (folder_ / "fixer.py").write_text(source, encoding="utf-8")
        files = {os.path.relpath(str(p), str(tmp_path)): p.read_text(encoding="utf-8")
                 for p in sorted(folder_.iterdir())}
        assert list(files) == ["modules/ai/fixer.py"]
        found = reached(files, run)
        assert [n for _f, _l, n, _w in found if n == want], (name, found)

    def test_what_is_no_reach_is_not_found(self, run):
        quiet = {
            "modules/ai/fixer.py": (
                '"""Never calls modules.heal.resubscribe.apply or flow_ops.apply."""\n'
                "from modules.heal import catalog, resubscribe\n"
                "from modules.sdn import flow_ops\n"
                "from modules.nsot import device_ops\n\n"
                "def apply(x):\n    # resubscribe.apply(x) is never called here\n"
                "    return x\n\n"
                "def look(net, host, subs, ask):\n"
                "    held = device_ops.holder(net, host)\n"
                "    return (resubscribe.plan(net, host, subs), resubscribe.KEY, apply(held),\n"
                "            flow_ops.plan(net, ask), catalog.preview('k', {}, network=net))\n")}
        assert reached(quiet, run) == []


# ── D: never a retry on its own ─────────────────────────────────────────────────────────────

def _parents(tree) -> dict:
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[id(child)] = node
    return out


def run_calls(source: str, module: str, run: str) -> list:
    """``[(line, how)]``: each call of the run function *run* (dotted) in *source* (the module
    *module*), *how* naming what it is called from when that is a loop, a comprehension, an
    ``except`` or ``finally``, or the run function itself; ``""`` otherwise. In the run's own
    module a call by its bare name counts; anywhere, one resolved through the imports."""
    run_module, _, name = run.rpartition(".")
    tree = ast.parse(source)
    parents = _parents(tree)
    bound, _imported = bindings(tree, module.rpartition(".")[0])
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        bare = module == run_module and isinstance(node.func, ast.Name) and node.func.id == name
        if not bare and resolved(node.func, bound) != run:
            continue
        how, child, up = "", node, parents.get(id(node))
        while up is not None and not how:
            if isinstance(up, (ast.For, ast.AsyncFor, ast.While)) and child not in up.orelse:
                how = "a loop"
            elif isinstance(up, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                how = "a comprehension"
            elif isinstance(up, ast.ExceptHandler):
                how = "an except"
            elif isinstance(up, ast.Try) and child in up.finalbody:
                how = "a finally"
            elif isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                    module == run_module and up.name == name and parents.get(id(up)) is tree:
                how = "itself"
            child, up = up, parents.get(id(up))
        out.append((node.lineno, how))
    return sorted(out)


class TestNeverARetryOnItsOwn:
    @pytest.mark.parametrize("key", sorted(catalog.CATALOG))
    def test_the_run_is_called_from_no_loop_no_handler_and_never_from_itself(self, key):
        op = catalog.CATALOG[key]
        module = op.runs.rpartition(".")[0]
        rel = module.replace(".", "/") + ".py"
        own = run_calls(_source(rel), module, op.runs)
        assert own, f"{rel} calls {op.runs} nowhere: its job starter is gone, or the scan is"
        assert [c for c in own if c[1]] == [], own
        for other, name in ((DOOR, "modules.ai.fix_proposal"),
                            (CATALOG_FILE, "modules.heal.catalog")):
            assert run_calls(_source(other), name, op.runs) == [], other

    def test_each_planted_retry_is_found(self):
        run = "modules.heal.resubscribe.apply"
        planted = {
            "a loop": "def start(*a):\n    for _ in range(3):\n        got = apply(*a)\n",
            "a while": ("def start(*a):\n    got = None\n    while not got:\n"
                        "        got = apply(*a)\n"),
            "a comprehension": "def start(*a):\n    return [apply(*a) for _ in range(2)]\n",
            "an except": ("def start(*a):\n    try:\n        return check(*a)\n"
                          "    except ValueError:\n        return apply(*a)\n"),
            "a finally": ("def start(*a):\n    try:\n        return check(*a)\n"
                          "    finally:\n        apply(*a)\n"),
            "itself": "def apply(*a):\n    if not a:\n        return apply(1)\n",
        }
        for name, source in planted.items():
            got = run_calls(source, "modules.heal.resubscribe", run)
            assert [how for _line, how in got if how], (name, got)
        # In another module, through its import and an alias.
        other = ("from modules.heal import resubscribe as R\n\n"
                 "def again(*a):\n    while True:\n        R.apply(*a)\n")
        assert run_calls(other, "modules.heal.catalog", run) == [(5, "a loop")]
        # Once, in the open, is no retry; neither is another object's own apply.
        once = ("def start(*a):\n    return work(lambda job: apply(*a))\n\n"
                "def other(box, x):\n    for b in x:\n        box.apply(b)\n")
        assert run_calls(once, "modules.heal.resubscribe", run) == [(2, "")]

    @pytest.mark.parametrize("key", sorted(catalog.CATALOG))
    def test_a_failed_run_is_one_record_and_nothing_more_is_sent(self, lab,  # noqa: F811
                                                                 nothing_started, key):
        run = _resolve(catalog.CATALOG[key].runs)
        d = DRIVES[key]().failing()
        program = d.plan()["program"]
        rec = d.run(run)
        assert rec["state"] == "failed" and rec["outcome"] not in ("refused", "running"), rec
        assert rec["finished_at"] is not None
        # One record, exactly the program sent, and nothing queued to send again.
        (kept,) = d.records()
        assert kept["id"] == rec["id"] and kept["state"] == "failed"
        assert d.sent() == program
        assert nothing_started == []
        # Another run is another call: without a person, or without the hashes, it is
        # refused and still nothing more is sent; with both, it is a second record.
        for case in ({"person": False}, {"actor_verified": "none"}, DRIVES[key].no_hash[0]):
            assert d.run(run, **case)["outcome"] == "refused"
            assert d.sent() == program
        assert len(d.records()) == 4
        d.run(run)
        assert len(d.sent()) == 2 * len(program) and len(d.records()) == 5


@pytest.fixture
def nothing_started(monkeypatch):
    """A job starter that fails when used: a run that asked for another would start one."""
    used = []

    def start(*_a, **_kw):
        used.append("a job")
        raise AssertionError("a job was started")
    monkeypatch.setattr("modules.nsot.capture_job.start", start)
    return used


# ── E: the document says what the code does ─────────────────────────────────────────────────

def _section(text: str, heading: str) -> str:
    """The section of a document that starts at the line beginning *heading*, to the next
    heading of its level."""
    level = heading.split(" ")[0]
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(heading))
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith(level + " ")), len(lines))
    return "\n".join(lines[start:end])


def _bullets(section: str) -> list:
    """A section's top-level bullets, each as one line of plain words (no bold markers)."""
    out = []
    for line in section.splitlines():
        if line.startswith("- "):
            out.append(line[2:])
        elif out and line.startswith("  "):
            out[-1] += " " + line.strip()
        elif out and not line.strip():
            out.append("")
    return [" ".join(b.replace("**", "").split()) for b in out if b]


class TestTheDocumentSaysIt:
    def test_section_12_holds_the_rule_exactly_and_names_this_test(self):
        section = _section(_source("docs/HEAL_TO_INTENT.md"), "## 12. ")
        assert section.startswith("## 12. The AI analysis of a can't-fix")
        bullets = _bullets(section)
        (rule,) = [b for b in bullets if b.startswith("No fix runs from AI text.")]
        assert rule.startswith(RULE + " "), rule
        # His one sentence more, the bullet directly after the rule's.
        after = bullets[bullets.index(rule) + 1]
        assert after.startswith(SAVED + " "), after
        assert [b for b in bullets if "saved fix" in b.lower()] == [after]
        (mechanised,) = [b for b in bullets if b.startswith("Mechanised:")]
        assert "tests/test_ai_fix_rule.py" in mechanised
        assert "tests/test_heal_analysis_never_read.py" in mechanised
        # The words it replaced are named once, as replaced, and stated nowhere in the section.
        flat = " ".join(section.split())
        assert flat.count("No fix is ever chosen or run from AI text") == 1
        assert 'replacing "No fix is ever chosen or run from AI text"' in flat

    def test_the_charters_fix_it_path_rests_on_it(self):
        section = " ".join(_section(_source("docs/MERCURY_CHARTER.md"),
                                    "## The fix-it path").replace("**", "").split())
        assert RULE in section

    def test_the_door_and_the_analysis_say_the_same(self):
        assert RULE in " ".join(FP.__doc__.split())
        from modules.ai import heal_analysis
        said = " ".join(heal_analysis.__doc__.split())
        assert "No fix runs from AI text" in said
        assert "is ever chosen or run from AI text" not in said

    def test_a_reworded_rule_or_an_unnamed_test_is_found(self):
        text = _source("docs/HEAL_TO_INTENT.md")
        section = _section(text, "## 12. ")
        reworded = _bullets(section.replace("never retries", "rarely retries"))
        assert not [b for b in reworded if b.startswith(RULE + " ")]
        resaid = _bullets(section.replace("never the AI's words", "or the AI's words"))
        assert not [b for b in resaid if b.startswith(SAVED + " ")]
        unnamed = _bullets(section.replace("tests/test_ai_fix_rule.py", "a test"))
        assert not [b for b in unnamed if b.startswith("Mechanised:")
                    and "tests/test_ai_fix_rule.py" in b]
        # Anchored on the section: the sentence elsewhere in the file does not count.
        moved = text.replace("## 12. ", "## 12a. ") + "\n## 12. Another\n\nNothing here.\n"
        assert not [b for b in _bullets(_section(moved, "## 12. "))
                    if b.startswith("No fix runs")]
