"""A restart stops the SDN loop, and says so (`modules/sdn/loop.py` `after_restart`,
`stopped_by_restart`; `modules/attention.py` `sdn_loop_source`; C2000).

- At the app's start, a network whose loop log ends in a start with no stop after it (the loop
  was running when its process ended) has the stop recorded, naming the restart and the last
  line's time; a loop already stopped, a network with no log, and a second start of the app
  record nothing more. The loop does not start again by itself.
- The loop's status then reads that stop, never an older person's stop.
- Needs attention: a WARNING row per network the restart stopped, naming the network and both
  times, with Start as its action on SDN › Responses; gone once the loop is started again, and
  24 hours after the restart (said as when it clears).
"""
from modules import attention as A
from modules.sdn import loop as LP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

NET = "Default"
T0 = 1_790_000_000.0


def _ran(network=NET, stopped=False):
    LP.say(network, "stop", "stopped by op@example.com", T0 - 100)
    LP.say(network, "start", "started by op@example.com, every 10 s, as job j1", T0 - 60)
    LP.say(network, "read", "read 1 switch(es)", T0 - 20)
    if stopped:
        LP.say(network, "stop", "stopped by op@example.com", T0 - 10)


def test_a_loop_running_at_the_restart_has_its_stop_recorded_once(networks):  # noqa: F811
    _ran()
    assert LP.after_restart([NET], now=T0) == [{"network": NET, "last_at": LP._iso(T0 - 20)}]
    last = LP._read(NET, LP.LOG_FILE)["rows"][-1]
    assert last["step"] == "stop" and last["by"] == LP.RESTART_ACTOR
    assert last["words"] == (f"stopped by the app's restart: its last line was at "
                             f"{LP._iso(T0 - 20)} UTC; the loop does not start again by itself: "
                             "start it on SDN › Responses")
    assert LP.after_restart([NET], now=T0 + 5) == [], "a second start records nothing more"
    assert LP.status(NET) == {"running": False, "stopped": last}


def test_a_stopped_loop_and_a_network_with_no_log_record_nothing(networks):  # noqa: F811
    _ran(stopped=True)
    assert LP.after_restart([NET, "Nowhere"], now=T0) == []
    assert LP.stopped_by_restart(NET) is None and LP.stopped_by_restart("Nowhere") is None


def test_the_row_names_the_network_and_both_times_and_clears_on_a_start(networks):  # noqa: F811
    _ran()
    LP.after_restart([NET], now=T0)
    stop = LP.stopped_by_restart(NET)
    got = A.sdn_loop_source(found={NET: stop}, now=T0 + 60)
    (r,) = got["rows"]
    assert (r["source"], r["kind"], r["level"]) == ("sdn_loop", "restart_stopped", "warning")
    assert r["what"] == "The SDN loop on Default was stopped by the app's restart"
    assert (f"its last line at {LP._iso(T0 - 20)} UTC, the stop recorded at {LP._iso(T0)}"
            in r["cause"])
    assert r["action"]["href"] == "/v2/sdn/responses?list=Default"
    assert r["action"]["label"].startswith("Start the loop on Default's SDN › Responses")
    assert r["clears"]["ways"] == ["resolves", "time"] and r["clears_at"] == LP._iso(T0 + 86400)
    LP.say(NET, "start", "started by op@example.com, every 10 s, as job j2", T0 + 120)
    assert LP.stopped_by_restart(NET) is None
    assert A.sdn_loop_source(found={NET: None}, now=T0 + 130)["rows"] == []


def test_the_row_clears_24_hours_after_the_restart(networks):  # noqa: F811
    _ran()
    LP.after_restart([NET], now=T0)
    stop = LP.stopped_by_restart(NET)
    assert A.sdn_loop_source(found={NET: stop}, now=T0 + 86399)["rows"]
    assert A.sdn_loop_source(found={NET: stop}, now=T0 + 86400)["rows"] == []


def test_a_person_s_stop_is_never_a_restart_s(networks):  # noqa: F811
    _ran(stopped=True)
    assert A.sdn_loop_source(found={NET: LP.stopped_by_restart(NET)}, now=T0)["rows"] == []


def test_the_source_is_read_by_the_page_and_moved_by_sdn():
    assert A.sdn_loop_source in A.SOURCES
    assert A.SOURCE_KEYS["sdn_loop_source"] == ("sdn",)
