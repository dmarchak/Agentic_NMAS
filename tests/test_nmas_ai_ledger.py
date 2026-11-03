"""scripts/nmas-ai-ledger (C2310): the AI spend by UTC day, computed from the record of AI calls
each time a figure is stated, never carried forward (the operator, 2026-11-02; PHASE8_PLAN 0.5).
Rows in the record's own shapes as the host's `data/ai_calls.jsonl` holds them (read
2026-11-02: a call with no trigger, recorded before triggers were; an evaluation's, its trigger
`{"kind": "evaluation", "run"}`; a background job's; a person's; and a use of a call, which
costs nothing), their values minimal.

- **By day**: each UTC day's calls, the calls that cost, its dollars and the running total, and
  whose they were (evaluation, person, background, other); a use of a call is not a call.
- **Since, budget and reading**: the total since a day (its day included) and before it, what
  is left of a budget, and the gap to the console's reading; a budget or reading with no span
  is refused.
- **Never guessed**: a line that does not parse is counted; an unreadable record exits 2.
"""
import importlib.machinery
import importlib.util
import json

import pytest


def _load():
    loader = importlib.machinery.SourceFileLoader("ai_ledger_under_test", "scripts/nmas-ai-ledger")
    spec = importlib.util.spec_from_loader("ai_ledger_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


L = _load()

ROWS = [
    {"actor": "op@example.com", "at": "2026-10-28T23:59:59Z", "cost_usd": 1.25, "id": "ai-1"},
    {"actor": "evaluation:e3", "at": "2026-10-29T00:00:01Z", "cost_usd": 2.5, "id": "ai-2",
     "trigger": {"kind": "evaluation", "run": "e3"}},
    {"actor": "op@example.com", "at": "2026-10-29T08:00:00Z", "cost_usd": 0.25, "id": "ai-3",
     "trigger": {"kind": "person", "by": "op@example.com", "verified": "access"}},
    {"actor": "sdn-loop-sdn_lab", "at": "2026-10-29T09:00:00Z", "cost_usd": 0.0, "id": "ai-4",
     "trigger": {"kind": "background", "feature": "sdn_classify", "job": "j", "finding": "k",
                 "network": "sdn_lab"}},
    {"actor": "op@example.com", "at": "2026-10-29T09:01:00Z", "use": "kept", "use_of": "ai-3",
     "detail": "", "links": []},
    {"actor": "evaluation:e4", "at": "2026-11-01T10:00:00Z", "cost_usd": 0.125, "id": "ai-5",
     "trigger": {"kind": "evaluation", "run": "e4"}},
]


def _lines(rows=ROWS, extra=()):
    return [json.dumps(r) for r in rows] + list(extra)


def test_each_utc_day_its_calls_dollars_and_whose():
    got = L.by_day(_lines())
    assert sorted(got["days"]) == ["2026-10-28", "2026-10-29", "2026-11-01"]
    d = got["days"]["2026-10-29"]
    assert (d["calls"], d["costing"], d["usd"]) == (3, 2, 2.75), "the use of a call is no call"
    assert dict(d["kinds"]) == {"evaluation": 2.5, "person": 0.25, "background": 0.0}
    assert dict(got["days"]["2026-10-28"]["kinds"]) == {"other": 1.25}
    out = L.report(got)
    assert out[1].startswith("2026-10-29  calls      3  costing      2  $    2.7500  running "
                             "$    4.0000  (evaluation $2.5000, person $0.2500)")
    assert out[-1] == ("lifetime, every day the record holds: $4.1250 (never a budget's "
                       "figure); lines that did not parse: 0")


def test_since_a_day_the_budget_left_and_the_gap_to_the_console():
    out = L.report(L.by_day(_lines()), since="2026-10-29", budget=190, reading=2.80)
    assert out[-3] == "since 2026-10-29 (its day included): $2.8750; before it: $1.2500"
    assert out[-2] == ("of the $190.00 budget for the spend since 2026-10-29: $2.8750 spent, "
                       "$187.1250 left")
    assert out[-1].startswith("the console's reading $2.80; the ledger's $2.8750; the gap "
                              "$+0.0750")


def test_a_line_that_does_not_parse_is_counted_never_guessed():
    got = L.by_day(_lines(extra=['{"at": "2026-10-29T10:00:00Z", "cost_usd": 9', "", "[]"]))
    assert got["unparsed"] == 1 and got["days"]["2026-10-29"]["usd"] == 2.75


def test_the_command_reads_the_record_given_and_refuses_what_it_cannot(tmp_path, capsys):
    ledger = tmp_path / "ai_calls.jsonl"
    ledger.write_text("\n".join(_lines()) + "\n", encoding="utf-8")
    assert L.main(["--ledger", str(ledger), "--since", "2026-11-01", "--budget", "1"]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed[-1] == ("of the $1.00 budget for the spend since 2026-11-01: $0.1250 spent, "
                           "$0.8750 left")
    assert L.main(["--ledger", str(ledger), "--budget", "1"]) == 2
    assert "need --since" in capsys.readouterr().err
    assert L.main(["--ledger", str(tmp_path / "absent.jsonl")]) == 2
    assert "cannot be read" in capsys.readouterr().err


@pytest.mark.parametrize("row,kind", [
    ({"actor": "evaluation:x"}, "evaluation"),
    ({"actor": "a", "trigger": {"kind": "evaluation"}}, "evaluation"),
    ({"actor": "a", "trigger": {"kind": "person"}}, "person"),
    ({"actor": "a", "trigger": {"kind": "background"}}, "background"),
    ({"actor": "a", "trigger": None}, "other"),
])
def test_whose_a_call_is(row, kind):
    assert L.kind_of(row) == kind
