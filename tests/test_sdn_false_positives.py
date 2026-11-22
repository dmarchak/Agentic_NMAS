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
  checkout;
- each run is kept in its network's record of evaluation runs (C2946), its summary and every
  false positive under its id, owner-only; a series naming a network Mercury does not have is
  refused before anything is judged.
"""
import csv
import importlib.machinery
import importlib.util
import json
import os
import stat

import pytest

from modules.sdn import false_positives as FP
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)

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


def test_the_script_reports_each_and_exits_one_with_any(networks, tmp_path, capsys):  # noqa: F811
    from modules.sdn import evaluations

    mod = _script()
    code = mod.main(["--series", os.path.join(REC, "RC-TCP.jsonl"), "--network", "Default",
                     "--out", str(tmp_path / "fp")])
    said = capsys.readouterr().out
    assert code == 1 and said.count("RC-TCP pass 13") == 4
    assert "1 run(s), 16 passes, 4 detection(s) fired: 4 false positive(s) (high_rate 4)" in said
    assert os.path.exists(tmp_path / "fp" / "false_positives.csv")
    # C2946: the run is kept in the network's record too, its id said.
    kept = evaluations.read("Default")["rows"]
    assert [r["kind"] for r in kept] == ["run"] + ["false_positive"] * 4
    assert f"RC-TCP: kept in Default's record of evaluation runs as {kept[0]['run_id']} " \
           "(4 false positive(s))" in said
    assert evaluations.read("Branch")["state"] == "absent"


def test_a_run_is_kept_with_its_summary_and_each_false_positive(networks):  # noqa: F811
    from modules.sdn import evaluations

    series = FP.load(os.path.join(REC, "RC-TCP.jsonl"))
    got = FP.keep("Default", series, by="nmas-sdn-false-positives", now=1793500000.0)
    rows = evaluations.read("Default")["rows"]
    run, fps = rows[0], rows[1:]
    assert got == {"run_id": run["run_id"], "false_positives": 4}
    assert run["run_id"].startswith("fp-") and run["at"] == "2026-11-01T02:26:40Z"
    assert (run["kind"], run["run"], run["passes"], run["fired"], run["false_positives"],
            run["by_rule"]) == ("run", "RC-TCP", 16, 4, 4, {"high_rate": 4})
    assert [r["detection"] for r in fps] == FP.judge([series])["false_positives"]
    assert {r["run_id"] for r in fps} == {run["run_id"]}
    path = os.path.join(networks, "lists", "default", evaluations.FILE)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_a_series_whose_network_mercury_does_not_have_is_refused(networks, tmp_path,  # noqa: F811
                                                                   capsys):
    from modules.sdn import evaluations

    code = _script().main(["--series", os.path.join(REC, "RC-TCP.jsonl"), "--out",
                           str(tmp_path / "fp")])
    said = capsys.readouterr()
    assert code == 2 and "'SDN lab'" in said.err and "nothing was judged" in said.err
    assert not os.path.exists(tmp_path / "fp")
    assert evaluations.read("Default")["state"] == "absent"


@pytest.mark.parametrize("argv,words", [
    (["--series", "x.jsonl", "--out", ROOT], "inside the checkout"),
    (["--out", "/nonexistent-fp"], "give --series files or --list"),
    (["--list", "Default", "--passes", "500", "--out", "/nonexistent-fp"], "1 to 150 passes")])
def test_the_script_refuses_what_it_cannot_run(argv, words, capsys):
    assert _script().main(argv) == 2
    assert words in capsys.readouterr().err


# ------------------------------------------------- declared external owners (C3930) and times
# The Lab 9 hardware, 2026-11-20: the team's own flows (cookies 0x9a00..0x9a03 under
# 0xffff000000000000, declared in NetBox's config context mercury.external_flow_owners and
# committed in the NSOT export) were counted as unauthorised_flow once a run, 228 of 260; the
# loop flags none of them, because it reads the declared owners (`protected.
# external_for_network`). Documentation addresses only (192.0.2.x, 2001:db8::).

MASK64 = "0xffff000000000000"
TEAM_COOKIES = (0x9A00000000000000, 0x9A01000000000005, 0x9A02000000000001, 0x9A03000000000002)
ROGUE_V4, ROGUE_V6 = 0x1234000000000001, 0x1234000000000002


def _declared():
    """The team's four owners as `protected.external_for_network` answers them, the entries
    parsed by `protected.external_owners`, the one parser."""
    from modules import protected as P

    entries = [{"name": name, "owner": "lab9 team", "cookie": f"0x{app:04x}000000000000",
                "mask": MASK64, "reason": "the team's own application"}
               for name, app in (("lab9-base", 0x9A00), ("lab9-forwarding", 0x9A01),
                                 ("lab9-dhcp", 0x9A02), ("lab9-dns", 0x9A03))]
    got = P.external_owners([{"name": "switch1",
                              "custom_fields": {"openflow_datapath_id": "0000000000000001"},
                              "config_context": {"mercury": {"external_flow_owners": entries}}}])
    assert got["refused"] == [] and len(got["owners"]) == 4
    return dict(got, state="ok", source="the committed NSOT export 0123456789ab", error="")


def _flow(n, cookie, match):
    return {"id": f"flow:lab:0000000000000001:{n}", "dpid": 1, "table_id": 0,
            "priority": 1000 + n, "cookie": cookie, "match": match, "idle_timeout": 0,
            "hard_timeout": 0, "actions": [{"type": "OUTPUT", "port": 2}],
            "packet_count": 10, "byte_count": 1000}


def _lab_collection(at):
    team = [_flow(0, TEAM_COOKIES[0], {}),
            _flow(1, TEAM_COOKIES[1], {"eth_dst": "02:00:00:00:00:01"}),
            _flow(2, TEAM_COOKIES[2], {"eth_type": 2048, "ipv4_src": "192.0.2.20"}),
            _flow(3, TEAM_COOKIES[3], {"eth_type": 34525, "ipv6_src": "2001:db8::20"})]
    rogue = [_flow(4, ROGUE_V4, {"eth_type": 2048, "ipv4_src": "192.0.2.66"}),
             _flow(5, ROGUE_V6, {"eth_type": 34525, "ipv6_src": "2001:db8::66"})]
    flows = team + rogue
    return {"collected_at": at, "controllers": [{
        "connection": "lab", "own_cookies": [0], "state": "ok",
        "switches": [{"dpid": 1, "dpid_hex": "0000000000000001", "state": "ok",
                      "active_flows": len(flows), "flows": flows, "ports": []}]}]}


INTENT_OK = {"state": "ok", "flows": [], "withdrawn": {}}


def _lab_series(path):
    head = {"kind": "head", "label": "lab9-normal", "network": "Default",
            "thresholds": {"ok": True, "values": {}}, "intent": INTENT_OK}
    passes = [{"kind": "pass", "n": n, "topology": None,
               "collected": _lab_collection(at)}
              for n, at in ((1, "2026-11-20T17:00:00Z"), (2, "2026-11-20T17:00:15Z"),
                            (3, "2026-11-20T17:00:31Z"))]
    path.write_text("".join(json.dumps(r) + "\n" for r in [head] + passes), encoding="utf-8")
    return str(path)


def _cookies(rows):
    return sorted(int(r["words"].split("cookie ")[1].split(",")[0], 16) for r in rows)


def test_a_declared_owners_flow_is_never_counted_and_an_undeclared_one_is(  # noqa: F811
        networks, tmp_path, monkeypatch, capsys):
    from modules import protected as P

    monkeypatch.setattr(P, "external_for_network", lambda network: _declared())
    code = _script().main(["--series", _lab_series(tmp_path / "lab9.jsonl"), "--network",
                           "Default", "--out", str(tmp_path / "fp")])
    said = capsys.readouterr().out
    with open(tmp_path / "fp" / "false_positives.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert _cookies(rows) == [ROGUE_V4, ROGUE_V6], "the team's four flows are never counted"
    assert {r["rule"] for r in rows} == {"unauthorised_flow"} and code == 1
    assert {r["source"] for r in rows} == {"192.0.2.66", "2001:db8::66"}, "IPv4 and IPv6 alike"
    assert ("lab9-normal: declared external flow owners: 4 from the committed NSOT export "
            "0123456789ab, their flows never counted") in said
    with open(tmp_path / "fp" / "summary.json", encoding="utf-8") as fh:
        summary = json.load(fh)
    (run,) = summary["by_run"]
    assert run["owners"]["state"] == "ok" and run["owners"]["declared"] == 4
    assert run["by_rule"] == {"unauthorised_flow": 2}


def test_a_live_run_judges_with_the_loops_declared_owners(networks, monkeypatch):  # noqa: F811
    from modules import protected as P
    from modules.sdn import flow_intent

    monkeypatch.setattr(P, "external_for_network", lambda network: _declared())
    monkeypatch.setattr(flow_intent, "intent", lambda network: INTENT_OK)
    ats = iter(["2026-11-20T17:00:00Z", "2026-11-20T17:00:15Z"])
    got = FP.read_live("Default", 2, 10, collect=lambda: _lab_collection(next(ats)),
                       topology=lambda: None, sleep=lambda s: None)
    assert got["head"]["external"]["state"] == "ok"
    judged = FP.judge([got])
    assert _cookies(judged["false_positives"]) == [ROGUE_V4, ROGUE_V6]
    assert judged["by_rule"] == {"unauthorised_flow": 2}


def test_owners_that_cannot_be_read_are_said_never_silently_counted(  # noqa: F811
        networks, tmp_path, monkeypatch, capsys):
    from modules import protected as P

    monkeypatch.setattr(P, "external_for_network", lambda network: {
        "state": "unreadable", "owners": [], "refused": [], "source": "",
        "error": "Default's committed NSOT export cannot be used: its digest does not verify"})
    _script().main(["--series", _lab_series(tmp_path / "lab9.jsonl"), "--network", "Default",
                    "--out", str(tmp_path / "fp")])
    said = capsys.readouterr().out
    assert ("lab9-normal: declared external flow owners: could not be read (Default's "
            "committed NSOT export cannot be used: its digest does not verify), so every "
            "foreign flow was judged unauthorised, a declared owner's included") in said


def test_each_run_says_its_utc_window_and_its_measured_pass_times(  # noqa: F811
        networks, tmp_path, monkeypatch, capsys):
    from modules import protected as P
    from modules.sdn import flow_intent

    monkeypatch.setattr(P, "external_for_network", lambda network: _declared())
    monkeypatch.setattr(flow_intent, "intent", lambda network: INTENT_OK)
    # A pass read for about 5 s, then the 10 s gap: about 15 s a pass, as on the hardware.
    clock = iter([1795194000.0, 1795194005.2, 1795194015.2, 1795194020.0]).__next__
    ats = iter(["2026-11-20T17:00:00Z", "2026-11-20T17:00:15Z"])
    got = FP.read_live("Default", 2, 10, collect=lambda: _lab_collection(next(ats)),
                       topology=lambda: None, sleep=lambda s: None, clock=clock)
    (run,) = FP.judge([got])["by_run"]
    assert (run["start"], run["end"]) == ("2026-11-20T17:00:00Z", "2026-11-20T17:00:20Z")
    assert run["pass_s"] == {"min": 15.2, "median": 15.2, "max": 15.2}
    assert run["read_s"] == {"min": 4.8, "median": 5.0, "max": 5.2}
    assert run["times_from"] == "each pass's measured start and end"
    rec = FP.judge([FP.load(os.path.join(REC, "RC-TCP.jsonl"))])["by_run"][0]
    assert (rec["start"], rec["end"]) == ("2026-11-01T20:08:08Z", "2026-11-01T20:10:38Z")
    assert rec["pass_s"] == {"min": 10.0, "median": 10.0, "max": 10.0} and rec["read_s"] is None
    assert rec["times_from"] == "the collections' own times (collected_at)"
    assert rec["by_rule"] == {"high_rate": 4}
    _script().main(["--series", os.path.join(REC, "RC-TCP.jsonl"), "--network", "Default",
                    "--out", str(tmp_path / "fp")])
    said = capsys.readouterr().out
    assert ("RC-TCP: 2026-11-01T20:08:08Z to 2026-11-01T20:10:38Z UTC, 16 passes, a pass "
            "10 to 10 s (median 10 s) start to start, measured from the collections' own times "
            "(collected_at); by rule: high_rate 4") in said
