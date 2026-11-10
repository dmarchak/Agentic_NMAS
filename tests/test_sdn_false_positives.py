"""False-positive runs on normal traffic (Lab 9 B3; `modules/sdn/false_positives.py`,
scripts/nmas-sdn-false-positives): the loop's rules over repeated normal-traffic collections,
each detection that fires logged with its rule, its evidence and what was done.

The runs are REAL: the operator's recorded captures of 2026-11-01 (tests/fixtures/sdn/recorded/:
RC-TCP, one iperf TCP session h2 to h4; RC-UDP1, one iperf UDP stream of large packets) and
the blind set's two normal collections (tests/fixtures/blind_sets/sdn_classify/
blind_normal_cases.json: N1, an idle fabric; N2, light normal traffic), each its own run.
- RC-TCP's transfer and RC-UDP1's stream are logged as High packet rate, watched, nothing
  proposed and no AI call (C2278, C2313), each row with its switch, port, measurement against
  its threshold and its evidence ids;
- the normal collections make no false positive;
- the log is a CSV with every column and a summary by rule and per pass, owner-only;
- a live run reads its passes read-only, bounded;
- the script reports each false positive, exits 1 with any, and refuses an --out inside the
  checkout.
"""
import csv
import importlib.machinery
import importlib.util
import json
import os
import stat

import pytest

from modules.sdn import false_positives as FP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC = os.path.join(ROOT, "tests", "fixtures", "sdn", "recorded")
NORMAL = os.path.join(ROOT, "tests", "fixtures", "blind_sets", "sdn_classify",
                      "blind_normal_cases.json")


def _normal_runs():
    with open(NORMAL, encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]
    return [{"label": c["id"], "head": {"thresholds": {"ok": True, "values": {}}},
             "passes": [{"n": 1, "collected": c["collection"], "topology": None}],
             "unparsed": 0} for c in cases]


def test_rc_tcp_and_rc_udp1_are_logged_watched_with_their_evidence():
    got = FP.judge([FP.load(os.path.join(REC, "RC-TCP.jsonl")),
                    FP.load(os.path.join(REC, "RC-UDP1.jsonl"))])
    assert got["runs"] == ["RC-TCP", "RC-UDP1"] and got["passes"] == 16 + 16
    assert set(got["by_rule"]) == {"high_rate"}
    tcp = [r for r in got["false_positives"] if r["run"] == "RC-TCP"]
    assert sorted((r["switch"][-1], r["port"]) for r in tcp) == [
        ("1", 2), ("1", 3), ("2", 2), ("2", 3)]
    assert {r["pass"] for r in tcp} == {13}
    assert all(r["done"] == "watched as High packet rate (basis transfer): nothing proposed, "
               "no AI call" for r in tcp)
    assert all(r["evidence"].startswith("port:lab-ryu:") for r in tcp)
    assert all(r["measured"].endswith("pps") and r["threshold"].endswith("pps") for r in tcp)
    udp = [r for r in got["false_positives"] if r["run"] == "RC-UDP1"]
    assert udp and all("basis large_packets" in r["done"] for r in udp)


def test_the_normal_collections_make_no_false_positive():
    got = FP.judge(_normal_runs())
    assert got["passes"] == 2 and got["false_positives"] == [] and got["per_pass"] == 0.0


def test_the_log_is_every_column_and_a_summary_owner_only(tmp_path):
    got = FP.judge([FP.load(os.path.join(REC, "RC-TCP.jsonl"))])
    paths = FP.write(got, str(tmp_path / "fp"))
    with open(paths["csv"], encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert tuple(rows[0]) == FP.COLUMNS and len(rows) == 4
    assert rows[0]["rule"] == "high_rate" and rows[0]["run"] == "RC-TCP"
    with open(paths["summary"], encoding="utf-8") as fh:
        summary = json.load(fh)
    assert summary["false_positives"] == 4 and summary["by_rule"] == {"high_rate": 4}
    assert summary["passes"] == 16
    for p in paths.values():
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_a_live_run_reads_its_passes_read_only_and_bounded():
    (normal,) = _normal_runs()[:1]
    reads, slept = [], []
    got = FP.read_live("Default", 3, 10, collect=lambda: reads.append(1) or
                       normal["passes"][0]["collected"], topology=lambda: None,
                       sleep=slept.append)
    assert len(got["passes"]) == 3 and len(reads) == 3 and slept == [10, 10]
    assert FP.judge([got])["false_positives"] == []


def _script():
    path = os.path.join(ROOT, "scripts", "nmas-sdn-false-positives")
    loader = importlib.machinery.SourceFileLoader("nmas_sdn_false_positives", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_the_script_reports_each_and_exits_one_with_any(tmp_path, capsys):
    mod = _script()
    code = mod.main(["--series", os.path.join(REC, "RC-TCP.jsonl"), "--out",
                     str(tmp_path / "fp")])
    said = capsys.readouterr().out
    assert code == 1 and said.count("RC-TCP pass 13") == 4
    assert "1 run(s), 16 passes, 4 detection(s) fired: 4 false positive(s) (high_rate 4)" in said
    assert os.path.exists(tmp_path / "fp" / "false_positives.csv")


@pytest.mark.parametrize("argv,words", [
    (["--series", "x.jsonl", "--out", ROOT], "inside the checkout"),
    (["--out", "/nonexistent-fp"], "give --series files or --list"),
    (["--list", "Default", "--passes", "500", "--out", "/nonexistent-fp"], "1 to 150 passes")])
def test_the_script_refuses_what_it_cannot_run(argv, words, capsys):
    assert _script().main(argv) == 2
    assert words in capsys.readouterr().err
