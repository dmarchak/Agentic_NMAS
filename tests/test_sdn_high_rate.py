"""High packet rate, watched and never answered (board S-HR, C2238; PHASE8_PLAN 17.8;
`detect.WATCH_ONLY`, `loop._watch_pass`). No network: the Lab 8 walk of 2026-10-27's own
evidence (tests/fixtures/ai_cases/sdn_classify/recorded_walk.json: the retired scan-fallback
cases rebuilt by today's rule through tests/test_sdn_classify_walk_cases.py's `rebuilt`, and
the walk's floods as it kept them), through the loop's pass with its classify step counted.

- **Watched**: the walk's high packet rate on s1 port 2 at 23:24:40 (walk-fp-6) is one watching
  row, action none: no AI call, nothing proposed, its line saying so.
- **Joined**: 33 s later the walk's flood fired on the same ports (walk-flood-1-s1 and -s2,
  23:25:13): one AI call each, the floods'; each flood's response says it began as High packet
  rate at 23:24:40, and each watching row closes "joined flood incident <id>".
- **Ended**: the walk's four pair-check rates at 23:13:48 (walk-fp-1 to 4) end in the next pass
  that no longer shows them, "ended, never more than a rate".
- **One row per incident**: one source on two switches is one row, the second seen also; one
  firing again while watched opens no second row.
- **Already answered**: a high rate on traffic a flood's response already answers is said and
  not watched apart.
- **The window** is the flood's, said as such.
"""
import pytest

from modules.sdn import detect as D
from modules.sdn import incidents
from modules.sdn import loop as LP
from tests.test_sdn_classify_walk_cases import load, rebuilt
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_incidents import NET, NO_DRIVER, WINDOWS, calls, collected, det  # noqa: F401
from tests.test_sdn_ops_v2 import lab  # noqa: F401 - the fixture

pytestmark = pytest.mark.usefixtures("calls")


def walk(key: str) -> dict:
    """The walk's detection *key*: a retired case rebuilt by today's rule, else as kept."""
    data = load()
    retired = {c["key"]: c for c in data["retired"]}
    if key in retired:
        return rebuilt(retired[key])[0]
    return next(c for c in data["cases"] if c["key"] == key)["detection"]


def a_pass(fired, still=None, at=None):
    """One pass: *fired* the detections new in it, *still* every one it shows (default
    *fired*), at *at* (default the first fired one's time)."""
    at = at if at is not None else D._epoch(fired[0]["at"])
    shows = list(fired if still is None else still)
    observe = lambda network, c: {  # noqa: E731
        "ok": True, "fired": [d["key"] for d in fired], "resolved": [],
        "detections": shows, "thresholds": dict(WINDOWS), "collected_at": LP._iso(at)}
    return LP.run_pass(NET, collect=collected, observe=observe, now=lambda: at,
                       driver=NO_DRIVER)


def _closed(kind: str) -> list:
    return [r for r in LP._read(NET, LP.PENDING_FILE)["rows"] if r.get("kind") == kind]


def test_the_walk_s_high_rate_is_watched_with_no_ai_call_and_nothing_proposed(calls):
    rate = walk("walk-fp-6")
    assert (rate["rule"], rate["dpid"], rate["port"]) == ("high_rate", 1, 2)
    out = a_pass([rate])
    assert out["ok"], out
    assert calls == [] and out["proposed"] == [] and LP.awaiting(NET)["rows"] == []
    (row,) = LP.watching(NET)["rows"]
    assert out["watching"] == [row["id"]] and row["id"].startswith("watch-")
    assert (row["action"], row["detection"]["key"], row["at"]) == (
        "none", rate["key"], "2026-10-27T23:24:40Z")
    (said,) = [x for x in out["lines"] if x["step"] == "watch"]
    assert said["words"].endswith(
        f": watched as High packet rate ({row['id']}), not called a scan or a flood: nothing "
        "proposed, no AI call; it joins the flood rule's incident if that fires for this "
        "traffic, and ends when it no longer fires")
    assert "sdn" in out["announced"]["keys"] and "ai_calls" not in out["announced"]["keys"]


def test_the_walk_s_flood_joins_each_watching_row_on_its_own_port(calls):
    rates = [walk("walk-fp-6"), walk("walk-fp-7")]          # s1 port 2, s2 port 3, 23:24:40
    floods = [walk("walk-flood-1-s1"), walk("walk-flood-1-s2")]   # the same ports, 23:25:13
    assert [(d["dpid"], d["port"]) for d in rates] == [(d["dpid"], d["port"]) for d in floods]
    a_pass(rates)
    watched = {r["detection"]["dpid"]: r["id"] for r in LP.watching(NET)["rows"]}
    assert len(watched) == 2
    out = a_pass(floods, still=floods + rates)
    assert out["ok"], out
    assert [d["rule"] for d in calls] == ["flood", "flood"], "the floods' calls, and only theirs"
    assert LP.watching(NET)["rows"] == []
    responses = {r["detection"]["dpid"]: r for r in LP.awaiting(NET)["rows"]}
    assert sorted(responses) == [1, 2] and sorted(out["joined"]) == sorted(watched.values())
    joined = {r["id"]: r for r in _closed("joined")}
    for dpid, wid in watched.items():
        resp = responses[dpid]
        assert resp["began_as"] == {"watch": wid, "since": "2026-10-27T23:24:40Z",
                                    "words": "began as High packet rate at "
                                             "2026-10-27T23:24:40Z"}
        assert (joined[wid]["incident"], joined[wid]["why"]) == (
            resp["id"], f"joined flood incident {resp['id']}")


def test_the_walk_s_pair_check_rates_end_never_more_than_a_rate(calls):
    rates = [walk(f"walk-fp-{n}") for n in (1, 2, 3, 4)]       # 23:13:48, each its own port
    a_pass(rates)
    ids = sorted(r["id"] for r in LP.watching(NET)["rows"])
    assert len(ids) == 4
    out = a_pass([], at=D._epoch(rates[0]["at"]) + 10)
    assert calls == [] and sorted(out["ended"]) == ids and LP.watching(NET)["rows"] == []
    assert {r["why"] for r in _closed("ended")} == {"ended, never more than a rate"}
    assert all("ended, never more than a rate: none of its switches shows it now"
               in x["words"] for x in out["lines"] if x["step"] == "watch")


def test_one_row_while_any_switch_shows_it(calls):
    one = det(1, rule="high_rate")
    out = a_pass([one])
    (wid,) = out["watching"]
    assert a_pass([], still=[one], at=D._epoch(one["at"]) + 5)["ended"] == []
    (row,) = LP.watching(NET)["rows"]
    assert row["id"] == wid


def test_one_source_on_two_switches_is_one_row_and_firing_again_opens_none(calls):
    s1, s2 = det(1, rule="high_rate"), det(2, rule="high_rate")
    out = a_pass([s1, s2])
    (row,) = LP.watching(NET)["rows"]
    assert out["watching"] == [row["id"]] and row["members"] == [s1["key"], s2["key"]]
    assert row["incident"]["key"] == "high_rate|192.0.2.1"
    out = a_pass([s1], still=[s1, s2], at=D._epoch(s1["at"]) + 5)
    assert out["watching"] == [] and [r["id"] for r in LP.watching(NET)["rows"]] == [row["id"]]
    assert calls == []


def test_a_rate_naming_no_source_firing_again_while_watched_opens_no_second_row(calls):
    """A detection naming no source is its own incident (`incidents.SINGLE`), so no window
    joins it: its key, already a member of the open row, is what keeps it one row."""
    rate = walk("walk-fp-6")
    assert rate["source"] is None
    (wid,) = a_pass([rate])["watching"]
    out = a_pass([rate], at=D._epoch(rate["at"]) + 5)
    assert out["watching"] == [] and [r["id"] for r in LP.watching(NET)["rows"]] == [wid]


def test_a_rate_on_traffic_a_flood_already_answers_is_not_watched_apart(calls):
    flood = walk("walk-flood-1-s1")
    first = a_pass([flood])
    (resp,) = first["proposed"]
    rate = dict(walk("walk-fp-6"), at=flood["at"])
    out = a_pass([rate], still=[flood, rate], at=D._epoch(flood["at"]) + 10)
    assert out["watching"] == [] and LP.watching(NET)["rows"] == []
    (said,) = [x for x in out["lines"] if x["step"] == "watch"]
    assert said["words"] == (f"1 switch (0000000000000001): a high packet rate on traffic flood "
                             f"incident {resp} already answers: not watched apart")
    assert [d["rule"] for d in calls] == ["flood"]


# ── seen where people look (17.8 item 4, (b)) ────────────────────────────────────────────────

def _one_joined_one_watching():
    """The walk's two rates watched; then only s1's flood fires: s1's row joins it and s2's
    stays watching (its rate still shown)."""
    rates = [walk("walk-fp-6"), walk("walk-fp-7")]
    a_pass(rates)
    flood = walk("walk-flood-1-s1")
    a_pass([flood], still=[flood] + rates)
    (watching,) = LP.watching(NET)["rows"]
    (resp,) = LP.awaiting(NET)["rows"]
    return watching, resp


def test_responses_draws_the_watching_row_and_the_flood_that_began_as_one(lab):
    from html import unescape
    watching, resp = _one_joined_one_watching()
    assert watching["detection"]["dpid"] == 2 and resp["began_as"]["since"] == watching["at"]
    page = unescape(lab["client"].get("/v2/sdn/responses?list=Default").get_data(as_text=True))
    assert "<strong>1 awaiting approval</strong> · 1 watching · 1 incident seen on 1 switch" in page
    assert f'id="sdn-i-{watching["id"]}"' in page and "1 watching</span>" in page
    for words in ("not asked", "nothing: a rate alone names no threat",
                  "Why it is not called a scan or a flood:",
                  "the flood rule has not fired for this port or source (its 30 s hold)",
                  "What happens next:", '"ended, never more than a rate"',
                  "Proposed:</strong> nothing, and no AI call",
                  "One Needs attention row for the incident, a warning, until it joins a "
                  "flood, ends, or is dismissed.",
                  f'/v2/sdn/response/{watching["id"]}/dismiss',
                  "Flood · began as High packet rate",
                  f'(watching row <span class="mono">{resp["began_as"]["watch"]}</span>'):
        assert words in page, words
    pps = watching["detection"]["measurement"]["value"]
    assert pps > 1000 and f"{pps:,.0f} packets a second (threshold 100)" in page
    # The rules card: High packet rate its own row; the scan needs L4 flows only.
    assert ("<tr><td>High packet rate</td><td>a port's packet rate on a switch whose flows "
            "name no transport ports</td><td>100 packets a second</td>") in page
    assert "packet-rate fallback" not in page


def test_a_watching_row_is_dismissed_with_a_reason_and_never_confirmed(lab):
    watching, _resp = _one_joined_one_watching()
    c, wid = lab["client"], watching["id"]
    r = c.post(f"/v2/sdn/response/{wid}/dismiss", data={"list": "Default", "reason": ""})
    assert r.status_code == 409 and "names its reason" in r.get_data(as_text=True)
    with pytest.raises(ValueError, match="awaiting a person"):
        LP.resolve(NET, wid, "confirmed", actor="op@example.com", operation="op-x")
    r = c.post(f"/v2/sdn/response/{wid}/dismiss",
               data={"list": "Default", "reason": "the lab's own iperf"})
    assert r.status_code == 200 and LP.watching(NET)["rows"] == []
    (d,) = [x for x in _closed("dismissed") if x["id"] == wid]
    assert d["why"] == "the lab's own iperf"


def test_needs_attention_has_one_warning_per_watching_row_until_it_joins(networks):  # noqa: F811
    from modules import attention as A
    rate = walk("walk-fp-6")
    a_pass([rate])
    (w,) = LP.watching(NET)["rows"]
    got = A.sdn_responses_source(found={NET: LP.awaiting(NET)},
                                 watched={NET: LP.watching(NET)})
    (row,) = got["rows"]
    assert (row["kind"], row["level"], row["operands"]["incident"]) == (
        "watching", "warning", w["id"])
    assert row["what"] == ("High packet rate on Default at 0000000000000001 port 2: watched, "
                           "not called a scan or a flood")
    assert "Nothing is proposed and no AI call is made" in row["cause"]
    assert row["action"]["href"] == (f"/v2/sdn/responses?list=Default&incident={w['id']}"
                                     f"#sdn-i-{w['id']}")
    assert got["checked"].endswith("; 1 high packet rate(s) watched")
    flood = walk("walk-flood-1-s1")
    a_pass([flood], still=[flood, rate])
    rows = A.sdn_responses_source(found={NET: LP.awaiting(NET)},
                                  watched={NET: LP.watching(NET)})["rows"]
    assert [r["kind"] for r in rows] == ["awaiting"]


def test_the_window_is_the_flood_s_and_says_so():
    assert incidents.window("high_rate", WINDOWS) == {
        "seconds": 30, "setting": "sdn_flood_window_seconds",
        "words": "within 30 s, the flood rule's window, which it joins within "
                 "(sdn_flood_window_seconds)"}
    assert incidents.group_key(det(1, rule="high_rate")) == "high_rate|192.0.2.1"
