"""v2 pages' work budget (C1973): what a page GET may do per request, asserted as work counted,
never wall-clock (CLAUDE.md, "Performance tests assert on work or growth").

SDN › Responses took about 20 s to load on the host (the operator, 2026-10-27). Measured that day
(read-only, the host's own stores in a separate process): not a controller read, but the AI calls
record: every page drawing AI spend (an AI control's readiness, Needs attention's cap rows,
Settings' AI cards) parsed the record's window again on every request, 11,508 lines that day
for 2.3 to 3.2 s a read; in the app, SDN › Responses took 21 to 25 s, Needs attention 30 to 35 s
and Settings › Installation 45 s.

The budget, each a test below:

1. **No v2 page GET asks an SDN controller.** A page draws the SDN reader's stored value and the
   loop's records; asking a controller is an action (Test connection, a preview) or the
   reader's job. Population: every v2 GET route with no path argument, and SDN's three tabs,
   with a connection saved whose controller counts each request.
2. **A page's read of the AI calls record parses only the calls recorded since the process
   last read it** (`records_migrate._tail_rows_kept`): with 400 calls today, a second request
   for each page that draws spend parses no line of the record, and after three more calls, at
   most three. Its growth form: the same page's parse count does not move with the record.
"""
import json
import time

import pytest

from modules import records_migrate
from modules.sdn import connections as C
from tests.sdn_fakes import FakeRyu
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_flow_ops import captured_table

BASE = "http://192.0.2.10:8080"
#: Pages that draw AI spend with hosted AI on and no background feature on (measured
#: 2026-10-27). Needs attention's cap rows read the same window (`calls.rows_since`, the one
#: read every spend figure goes through) only while a background feature is on.
SPEND_PAGES = ("/v2/sdn/responses?list=Default", "/v2/settings/installation")


@pytest.fixture
def lab(networks, monkeypatch):  # noqa: F811 - the fixture, used
    from modules.sdn import drivers
    from tests.interface_pages import as_a_verified_person

    fake = FakeRyu(BASE, flows={1: captured_table()})
    asked = []
    real_request = fake.request

    def counted(method, url, *a, **k):
        asked.append(f"{method} {url}")
        return real_request(method, url, *a, **k)
    fake.request = counted
    real = drivers.make

    def make(kind, connection, **kw):
        kw.setdefault("session", fake)
        kw.setdefault("sleep", lambda s: None)
        return real(kind, connection, **kw)
    monkeypatch.setattr(drivers, "make", make)
    C.save_connection("Default", {"name": "lab-controller", "kind": "ryu", "url": BASE},
                      actor="op@example.com")
    as_a_verified_person(monkeypatch)
    import app as A
    return {"client": A.app.test_client(), "asked": asked, "app": A.app}


def test_no_v2_page_get_asks_an_sdn_controller(lab):
    paths = sorted({r.rule for r in lab["app"].url_map.iter_rules()
                    if r.rule.startswith("/v2") and "GET" in r.methods and not r.arguments})
    paths += ["/v2/sdn/responses?list=Default", "/v2/sdn/flows?list=Default",
              "/v2/sdn?list=Default", "/v2/sdn/view?tab=responses&list=Default",
              "/v2/sdn/view?tab=flows&list=Default", "/v2/sdn/log?list=Default"]
    assert len(paths) >= 100, len(paths)          # the floor: v2's GET routes, measured 123
    asking = {}
    for p in paths:
        del lab["asked"][:]
        lab["client"].get(p)
        if lab["asked"]:
            asking[p] = list(lab["asked"])
    assert asking == {}, f"these v2 page GETs asked the controller: {asking}"
    # The counter counts: Test connection, an action, asks it.
    lab["client"].post("/v2/sdn/controller/lab-controller/test", data={"list": "Default"})
    assert lab["asked"], "Test connection asked the controller nothing: the counter is blind"


class _CountingJson:
    """`json` for records_migrate, counting each line it parses."""

    def __init__(self):
        self.parsed = 0

    def loads(self, *a, **k):
        self.parsed += 1
        return json.loads(*a, **k)

    def __getattr__(self, name):
        return getattr(json, name)


@pytest.fixture
def spend(lab, monkeypatch):
    """Hosted AI allowed and a key stored, so every AI control reads today's spend; 400 calls
    recorded today."""
    from modules.ai import calls, controls

    monkeypatch.setattr(controls, "_hosted", lambda: {"allowed": True})
    monkeypatch.setattr(controls, "_key_set", lambda: True)
    for i in range(400):
        assert calls.record({"id": calls.new_id(), "feature": "sdn_classify",
                             "actor": "op@example.com", "cost_usd": 0.0001,
                             "verdict": "answered"})["recorded"]
    counting = _CountingJson()
    monkeypatch.setattr(records_migrate, "json", counting)
    return {"counting": counting, "calls": calls}


@pytest.mark.parametrize("page", SPEND_PAGES)
def test_a_page_parses_only_the_calls_recorded_since_its_last_read(lab, spend, page):
    c, counting = lab["client"], spend["counting"]
    counting.parsed = 0
    assert c.get(page).status_code == 200
    first = counting.parsed
    assert first >= 400, f"{page} read {first} line(s) of the record: the page draws no spend"
    counting.parsed = 0
    assert c.get(page).status_code == 200
    assert counting.parsed == 0, f"{page} parsed {counting.parsed} line(s) again"
    for _ in range(3):
        spend["calls"].record({"id": spend["calls"].new_id(), "feature": "sdn_classify",
                               "actor": "op@example.com", "cost_usd": 0.0001,
                               "verdict": "answered"})
    counting.parsed = 0
    assert c.get(page).status_code == 200
    assert counting.parsed <= 3 * 2, f"{page} parsed {counting.parsed} line(s) for 3 new calls"


def test_the_kept_read_answers_what_a_whole_read_answers(lab, spend):
    """The kept rows are the whole read's: the same spend after appends, and after the file
    is rewritten (a new file at the path is read whole)."""
    import datetime
    calls = spend["calls"]
    day = calls.today()
    before = calls.spent_usd(day)
    calls.record({"id": calls.new_id(), "feature": "x", "actor": "a", "cost_usd": 0.5,
                  "verdict": "answered"})
    after = calls.spent_usd(day)
    assert after["calls"] == before["calls"] + 1
    assert after["usd"] == pytest.approx(before["usd"] + 0.5)
    start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    whole = [records_migrate._without(r, calls.WINDOW_WITHOUT)
             for r in records_migrate._tail_rows(calls._path(), start, True)]
    kept = records_migrate._tail_rows_kept(calls._path(), start, True, calls.WINDOW_WITHOUT)
    assert [r for _, r in kept] == whole
    # Rewritten in place (a shorter file): read whole again, never the kept rows.
    path = calls._path()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "only", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                               time.gmtime()),
                             "cost_usd": 0.25, "verdict": "answered"}) + "\n")
    rewritten = calls.spent_usd(day)
    assert rewritten["calls"] == 1 and rewritten["usd"] == pytest.approx(0.25)


def test_a_windowed_call_holds_no_request_and_a_found_call_does(lab, spend):
    """What the window keeps per process leaves out the request as sent (a month of whole rows
    was 363 MiB in a process on the host, 2026-10-27, `request` 125 of the record's 140 MiB);
    the call read by its id is whole. Both ways in: a call read with the window first, and one
    appended after it."""
    calls = spend["calls"]
    start = calls.day_start(calls.today())
    first, later = calls.new_id(), calls.new_id()
    calls.record({"id": first, "feature": "x", "actor": "a", "cost_usd": 0.5,
                  "verdict": "answered", "request": {"messages": ["the prompt as sent"]}})
    calls.rows_since(start)
    calls.record({"id": later, "feature": "x", "actor": "a", "cost_usd": 0.5,
                  "verdict": "answered", "request": {"messages": ["the prompt as sent"]}})
    rows = calls.rows_since(start)["rows"]
    assert {first, later} <= {r.get("id") for r in rows}
    assert not [r for r in rows if "request" in r]
    kept = records_migrate._kept[calls._path()]["rows"]
    assert {first, later} <= {r.get("id") for _, r in kept if isinstance(r, dict)}
    assert not [r for _, r in kept if isinstance(r, dict) and "request" in r]
    for cid in (first, later):
        assert calls.find(cid)["row"]["request"] == {"messages": ["the prompt as sent"]}


def _stamp(minutes_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes_ago * 60))


def _line(minutes_ago: float, cost: str = "0.5", n: int = 0) -> str:
    return ('{"id": "c%04d", "at": "%s", "cost_usd": %s, "verdict": "answered"}\n'
            % (n, _stamp(minutes_ago), cost))


def _floor(minutes_ago: float):
    import datetime
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=minutes_ago))


def _same(path, floor):
    """The kept read's rows are exactly the whole read's, over the same bytes."""
    kept = [r for _, r in records_migrate._tail_rows_kept(str(path), floor, True)]
    assert kept == records_migrate._tail_rows(str(path), floor, True)
    return kept


def test_a_line_half_written_at_a_read_is_counted_once_it_is_whole(tmp_path):
    """A kept read takes a line only once its newline is written: a call half written when a
    page reads is counted when it is whole, never lost as an unparsable fragment."""
    path = tmp_path / "calls.jsonl"
    path.write_text(_line(30, n=1), encoding="utf-8")
    floor = _floor(60)
    _same(path, floor)
    whole = _line(1, cost="0.75", n=2)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(whole[:20])
    assert [r["id"] for r in _same(path, floor)] == ["c0001"]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(whole[20:])
    assert [r["id"] for r in _same(path, floor)] == ["c0001", "c0002"]


def test_a_file_replaced_by_another_is_read_whole(tmp_path):
    """Another file put in the record's place (a new inode) is read whole, even when it is
    longer and ends with the bytes the kept read ended with: an earlier row it changed is
    read as it now is."""
    path = tmp_path / "calls.jsonl"
    tail = "".join(_line(m, n=i) for i, m in enumerate((25, 20, 10, 5), start=2))
    assert len(tail.encode()) > records_migrate.KEPT_EDGE    # the edge compared is the tail's
    path.write_text(_line(30, cost="0.5", n=1) + tail, encoding="utf-8")
    floor = _floor(60)
    _same(path, floor)
    other = tmp_path / "other.jsonl"
    other.write_text(_line(30, cost="9.5", n=1) + tail + _line(1, n=9), encoding="utf-8")
    other.replace(path)
    rows = _same(path, floor)
    assert rows[0]["cost_usd"] == 9.5 and rows[-1]["id"] == "c0009"


def test_a_row_appended_from_before_the_window_ends_it_as_a_whole_read_does(tmp_path):
    """A row appended with a time before the kept window's floor stops the read back from the
    end there, as the whole read stops; and a narrower window asked of a wider kept one is cut
    at its own floor."""
    path = tmp_path / "calls.jsonl"
    path.write_text(_line(50, n=1) + _line(40, n=2), encoding="utf-8")
    floor = _floor(60)
    _same(path, floor)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(_line(120, n=3) + _line(1, n=4))
    assert [r["id"] for r in _same(path, floor)] == ["c0004"]
    path2 = tmp_path / "calls2.jsonl"
    path2.write_text(_line(50, n=1) + _line(20, n=2) + _line(1, n=3), encoding="utf-8")
    _same(path2, _floor(60))
    assert [r["id"] for r in _same(path2, _floor(30))] == ["c0002", "c0003"]
