"""SDN › Responses' loop log (C1971): the panel draws one run of the loop WHOLE, scrolling in its
box, any earlier run is reachable by its job id and start time, and Download log gives the run
as plain text named for the network and the run (Lab 8 objective 4.2's evidence is a full
3-minute run's log). Through the real app and routes, on tests/test_sdn_connections' store;
the log written by the loop's own `say`, as `start` and `run_pass` write it.
"""
import re
from html import unescape

import pytest

from modules.sdn import loop as LP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

T0 = 1_790_000_000.0          # 2026-09-21T14:13:20Z


def a_run(network="Default", t0=T0, passes=40, by="op@example.com"):
    """One run as the loop writes it: its start line naming its job, then *passes* passes of a
    read and a detect line each, 5 s apart, then its stop. The job id it names."""
    job = LP.job_id(network, t0)
    LP.say(network, "start", f"started by {by}, every 5 s, as job {job}", now=t0)
    for p in range(passes):
        LP.say(network, "read", f"pass {p:03d}: read 1 switch(es): 9 flows", now=t0 + 5 * p + 1)
        LP.say(network, "detect", f"pass {p:03d}: nothing new", now=t0 + 5 * p + 2)
    LP.say(network, "stop", f"stopped by {by}", now=t0 + 5 * passes + 3)
    return job


@pytest.fixture
def client(networks):  # noqa: F811 - the fixture, used
    import app as A
    return A.app.test_client()


def test_a_run_is_its_start_line_and_every_line_to_the_next_start(networks):  # noqa: F811
    LP.say("Default", "read", "a line written before any recorded start", now=T0 - 100)
    first = a_run(t0=T0, passes=3)
    second = a_run(t0=T0 + 600, passes=2)
    got = LP.run_log("Default")
    assert got["state"] == "ok" and got["job"] == second
    assert [r["job"] for r in got["runs"]] == [second, first, LP.BEFORE_FIRST_START]
    assert [r["count"] for r in got["runs"]] == [2 * 2 + 2, 3 * 2 + 2, 1]
    older = LP.run_log("Default", first)
    assert older["rows"][0]["step"] == "start" and older["rows"][-1]["step"] == "stop"
    assert older["at"] == "2026-09-21T14:13:20Z" and len(older["rows"]) == 8
    missing = LP.run_log("Default", "sdn-loop-default-19700101T000000Z")
    assert missing["state"] == "unknown" and "which holds 3 run(s)" in missing["error"]


def test_the_panel_draws_the_whole_run_in_a_box_that_scrolls(client):
    job = a_run(passes=60)                       # 122 lines, four times the old 30
    html = client.get("/v2/sdn/responses?list=Default").get_data(as_text=True)
    box = re.search(r'<pre class="mono sdn-log"[^>]*>(.*?)</pre>', html, re.S).group(1)
    lines = [ln for ln in box.splitlines() if ln.strip()]
    assert len(lines) == 122, len(lines)
    assert lines[0].endswith("stop: stopped by op@example.com")          # newest first
    assert lines[-1].endswith(f"start: started by op@example.com, every 5 s, as job {job}")
    assert "All 122 lines of this run, newest first." in html
    assert f'<option value="{job}" selected>{job} · started 2026-09-21 14:13:20 UTC' in html


def test_an_earlier_run_is_reachable_by_its_job_id(client):
    first = a_run(t0=T0, passes=2)
    second = a_run(t0=T0 + 600, passes=5)
    html = client.get("/v2/sdn/responses?list=Default").get_data(as_text=True)
    assert f'<option value="{second}" selected>' in html and f'<option value="{first}">' in html
    assert 'hx-get="/v2/sdn/log?list=Default"' in html and '<select id="sdn-log-run" ' \
                                                            'name="run">' in html
    part = client.get(f"/v2/sdn/log?list=Default&run={first}").get_data(as_text=True)
    assert f'<option value="{first}" selected>' in part
    assert "All 6 lines of this run" in part and "pass 004" not in part
    gone = client.get("/v2/sdn/log?list=Default&run=sdn-loop-default-19700101T000000Z")
    assert "Couldn't load: no run sdn-loop-default-19700101T000000Z is in Default&#39;s " \
           "loop log" in gone.get_data(as_text=True)


def test_a_run_longer_than_the_panel_says_how_many_it_draws(client, monkeypatch):
    from modules import sdn_ops_page
    monkeypatch.setattr(sdn_ops_page, "LOG_PANEL_LINES", 10)
    a_run(passes=20)                             # 42 lines
    html = client.get("/v2/sdn/responses?list=Default").get_data(as_text=True)
    box = re.search(r'<pre class="mono sdn-log"[^>]*>(.*?)</pre>', html, re.S).group(1)
    assert len([ln for ln in box.splitlines() if ln.strip()]) == 10
    assert "The newest 10 of this run's 42 lines, newest first: Download log has every " \
           "line." in html


def test_download_log_is_the_run_as_text_named_for_the_network_and_the_run(client):
    first = a_run(t0=T0, passes=2)
    a_run(t0=T0 + 600, passes=36)                # a 3-minute run at 5 s
    html = client.get("/v2/sdn/responses?list=Default").get_data(as_text=True)
    href = unescape(re.search(r'<a class="btn btn-small" href="([^"]+)" download', html).group(1))
    r = client.get(href)
    assert r.status_code == 200 and r.mimetype == "text/plain"
    job = LP.job_id("Default", T0 + 600)
    assert r.headers["Content-Disposition"] == f'attachment; filename="{job}.log"'
    assert job.startswith("sdn-loop-default-")                   # the network, then the run
    text = r.get_data(as_text=True).splitlines()
    assert text[0] == f"# Mercury SDN loop log: network Default, run {job}"
    assert len(text) == 2 + 36 * 2 + 2
    assert text[2].startswith("2026-09-21T14:23:20Z start:") and text[-1].endswith("stop: "
                                                                                  "stopped by "
                                                                                  "op@example.com")
    older = client.get(f"/v2/sdn/log/download?list=Default&run={first}")
    assert older.headers["Content-Disposition"] == f'attachment; filename="{first}.log"'
    assert len(older.get_data(as_text=True).splitlines()) == 2 + 2 * 2 + 2


def test_download_of_a_run_not_in_the_log_names_it(client):
    a_run(passes=1)
    r = client.get("/v2/sdn/log/download?list=Default&run=sdn-loop-default-19700101T000000Z")
    assert r.status_code == 404 and r.mimetype == "text/plain"
    assert "no run sdn-loop-default-19700101T000000Z is in Default's loop log, which holds " \
           "1 run(s)" in r.get_data(as_text=True)
