"""C92: reachability as a reader job (modules/readers/reachability.py).

The dot was one probe, and a single miss drew "offline": 93% of 2,946 offline
runs ended at the very next probe (106 h of the host's log). The reader counts
consecutive misses against ONE threshold function (P.8 moves it per network),
says which probe answered, probes every list, and owns the dict every consumer
already reads. It announces on a change in who answers, with a keepalive, so
its silence is never mistaken for nothing having changed."""

import dataclasses

import pytest

from modules import attention as A
from modules import config
from modules import reader_job as R
from modules.readers import reachability as RE

T0 = 1_790_000_000.0
TARGETS = [("192.0.2.11", "r1", "Lab"), ("192.0.2.12", "r2", "Lab")]


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    saved = dict(RE.STATUS)
    RE.STATUS.clear()
    yield
    RE.STATUS.clear()
    RE.STATUS.update(saved)


def cycle(answers, previous, t):
    """One probe cycle: *answers* maps address -> answered."""
    fn = lambda ip: (answers[ip], RE.CLAIM_TCP if answers[ip] else RE.CLAIM_NONE)  # noqa: E731
    return RE.read(probe_fn=fn, targets=TARGETS, previous=previous, clock=lambda: t)


class TestCountingMisses:
    def test_one_miss_is_a_missed_probe_never_offline(self):
        v = cycle({"192.0.2.11": True, "192.0.2.12": True}, {}, T0)
        v = cycle({"192.0.2.11": False, "192.0.2.12": True}, v["devices"], T0 + 5)
        r1 = v["devices"]["192.0.2.11"]
        assert r1["last_result"] == "missed" and r1["consecutive_misses"] == 1
        assert r1["answering"] is True and RE.STATUS["192.0.2.11"] is True

    def test_the_threshold_th_miss_is_not_answering_since_then(self):
        v = cycle({"192.0.2.11": True, "192.0.2.12": True}, {}, T0)
        for k in (1, 2, 3):
            v = cycle({"192.0.2.11": False, "192.0.2.12": True}, v["devices"], T0 + 5 * k)
        r1 = v["devices"]["192.0.2.11"]
        assert r1["consecutive_misses"] == 3 and r1["answering"] is False
        assert r1["since"] == RE._iso(T0 + 15) and RE.STATUS["192.0.2.11"] is False

    def test_an_answer_resets_the_count_and_keeps_the_since_of_an_unbroken_state(self):
        v = cycle({"192.0.2.11": True, "192.0.2.12": True}, {}, T0)
        v = cycle({"192.0.2.11": False, "192.0.2.12": True}, v["devices"], T0 + 5)
        v = cycle({"192.0.2.11": True, "192.0.2.12": True}, v["devices"], T0 + 10)
        r1 = v["devices"]["192.0.2.11"]
        assert r1["consecutive_misses"] == 0 and r1["since"] == RE._iso(T0), \
            "answering throughout: one missed probe does not restart its since"

    def test_the_threshold_comes_from_the_one_function(self, monkeypatch):
        assert RE.miss_threshold() == 3
        monkeypatch.setattr(RE, "miss_threshold", lambda list_name="", hostname="": 5)
        v = cycle({"192.0.2.11": True, "192.0.2.12": True}, {}, T0)
        assert v["devices"]["192.0.2.11"]["threshold"] == 5

    def test_the_claim_names_the_probe_that_answered(self):
        v = cycle({"192.0.2.11": True, "192.0.2.12": False}, {}, T0)
        assert v["devices"]["192.0.2.11"]["claim"] == RE.CLAIM_TCP
        assert v["devices"]["192.0.2.12"]["claim"] == RE.CLAIM_NONE


class TestTheSharedDict:
    def test_it_is_the_dict_the_app_hands_every_consumer(self):
        import app as Ap
        assert Ap.device_status_cache is RE.STATUS

    def test_it_is_updated_in_place_and_a_departed_device_leaves(self):
        before = RE.STATUS
        RE.STATUS["192.0.2.99"] = True
        cycle({"192.0.2.11": True, "192.0.2.12": True}, {}, T0)
        assert RE.STATUS is before and "192.0.2.99" not in RE.STATUS


class TestThePopulation:
    def test_every_list_is_probed_and_an_address_once(self, monkeypatch):
        from modules import device
        monkeypatch.setattr(device, "get_device_lists", lambda: [
            {"name": "Lab", "filename": "lab"}, {"name": "Other", "filename": "other"}])
        rows = {"lab": [{"hostname": "r1", "ip": "192.0.2.11"}],
                "other": [{"hostname": "x1", "ip": "192.0.2.21"},
                          {"hostname": "r1-dup", "ip": "192.0.2.11"},
                          {"hostname": "bad", "ip": "not-an-address"}]}
        monkeypatch.setattr(device, "load_saved_devices",
                            lambda path: rows["lab" if "/lab/" in path else "other"])
        got = RE.population()
        assert got == [("192.0.2.11", "r1", "Lab"), ("192.0.2.21", "x1", "Other")]


class TestTheKeepalive:
    def test_announce_only_on_change_without_a_keepalive_is_refused(self):
        with pytest.raises(R.ReaderRefused, match="no keepalive"):
            R.register(dataclasses.replace(RE.READER, name="t-nokeep", announce_at_least_every=0))

    def test_it_announces_on_a_change_skips_an_unchanged_cycle_and_keeps_alive(self):
        heard, t = [], [T0]
        answers = {"192.0.2.11": True, "192.0.2.12": True}
        reader = dataclasses.replace(RE.READER, read=lambda: RE.read(
            probe_fn=lambda ip: (answers[ip], RE.CLAIM_TCP), targets=TARGETS, clock=lambda: t[0]))
        R._LAST_ANNOUNCED.pop(reader.name, None)
        say = lambda *a: heard.append(t[0])  # noqa: E731
        R.run_once(reader, announce=say, clock=lambda: t[0])          # first: announced
        t[0] += 5
        R.run_once(reader, announce=say, clock=lambda: t[0])          # unchanged: skipped
        answers["192.0.2.11"] = False
        for _ in range(3):                                            # r1 stops answering
            t[0] += 5
            R.run_once(reader, announce=say, clock=lambda: t[0])
        t[0] += RE.KEEPALIVE_SECONDS                                  # a quiet minute
        R.run_once(reader, announce=say, clock=lambda: t[0])
        assert heard == [T0, T0 + 20, T0 + 20 + RE.KEEPALIVE_SECONDS], heard

    def test_the_page_s_promise_is_two_and_a_half_keepalives(self):
        assert R.page_promise(RE.READER) == int(RE.KEEPALIVE_SECONDS * 2.5)


def stored(devices):
    return {"state": "ok", "why": "", "doc": {"stale_after_seconds": 150, "last_good": {
        "value": {"devices": devices, "counts": {
            "answering": sum(1 for d in devices.values() if d["answering"]),
            "not_answering": sum(1 for d in devices.values() if not d["answering"]),
            "missed_last_probe": 0}},
        "value_at": R._iso(T0)}}}


def dev(name, ip, answering, misses=0, since="2026-09-28T21:00:00Z"):
    return {"address": ip, "hostname": name, "answering": answering,
            "consecutive_misses": misses, "threshold": 3, "since": since,
            "claim": RE.CLAIM_TCP if answering else RE.CLAIM_NONE,
            "last_result": "answered" if answering else "missed"}


class TestTheSource:
    def test_everyone_answering_is_no_row(self):
        res = A.reachability_source(cached=stored({"a": dev("r1", "a", True)}))
        assert res["rows"] == [] and "1 answering, 0 not answering" in res["checked"]

    def test_several_not_answering_is_one_row_that_names_each(self):
        res = A.reachability_source(cached=stored({
            "a": dev("r1", "a", False, 4, "2026-09-28T21:00:00Z"),
            "b": dev("r2", "b", False, 3, "2026-09-28T21:00:05Z"),
            "c": dev("s1", "c", True)}))
        (row,) = res["rows"]
        assert row["what"] == "2 devices are not answering" and row["devices"] == ["r1", "r2"]
        assert "4 consecutive misses" in row["cause"] and "path from Mercury" in row["cause"]

    def test_nothing_stored_is_unreadable(self):
        res = A.reachability_source(cached={"state": "absent", "doc": None, "why": "never"})
        assert res["state"] == "unreadable"


class TestTheReaperNoLongerProbes:
    def test_session_reaper_reaps_and_never_probes(self, monkeypatch):
        """ping_worker probed the active list and wrote one probe's answer into
        the dict; its replacement only closes idle sessions (C97)."""
        from modules import connection as C

        calls = []
        monkeypatch.setattr(C, "reap_idle", lambda: calls.append("reap"))
        monkeypatch.setattr(C, "is_device_online", lambda *a, **k: calls.append("probe"))

        class Stop(Exception):
            pass

        def sleep(_):
            raise Stop

        monkeypatch.setattr(C.time, "sleep", sleep)
        started = []
        monkeypatch.setattr(C.threading, "Thread",
                            lambda target, **k: type("T", (), {"start": lambda s: started.append(target)})())
        C.session_reaper(interval=5)
        with pytest.raises(Stop):
            started[0]()
        assert calls == ["reap"] and not hasattr(C, "ping_worker")


class _Accepted:
    """A connection a device accepted: the context manager `socket.create_connection` returns."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestTheProbe:
    """IP connectivity (Lab 7's "IP connectivity"): the reader's probe, ICMP first and then TCP 22,
    with the device's answers standing in for the network (no packet leaves). Its claim names
    the probe that answered, which the Devices page shows; a silent device is down, never an
    error."""

    def test_an_icmp_answer_is_enough_and_tcp_is_not_tried(self):
        tried = []
        got = RE.probe("192.0.2.10", ping=lambda ip, **kw: 12.5,
                       connect=lambda *a, **kw: tried.append(a) or _Accepted())
        assert got == (True, RE.CLAIM_ICMP) and tried == []

    @pytest.mark.parametrize("icmp", [lambda ip, **kw: None, lambda ip, **kw: False])
    def test_icmp_silent_then_ssh_accepts(self, icmp):
        seen = []
        got = RE.probe("192.0.2.10", ping=icmp,
                       connect=lambda addr, **kw: seen.append(addr) or _Accepted())
        assert got == (True, RE.CLAIM_TCP) and seen == [("192.0.2.10", 22)]

    def test_icmp_not_permitted_falls_back_to_tcp(self):
        """ping3 needs a raw socket; without the right it raises, and TCP decides."""
        def no_raw_socket(ip, **kw):
            raise PermissionError("Operation not permitted")
        assert RE.probe("192.0.2.10", ping=no_raw_socket,
                        connect=lambda *a, **kw: _Accepted()) == (True, RE.CLAIM_TCP)

    def test_each_probe_is_bounded_at_two_seconds(self):
        """A silent address costs each probe its bound, never the kernel's connect timeout
        (about two minutes with Linux's default SYN retries), and the reader probes the whole
        fleet every cycle. The bound is pinned here, so a change to it is made here too (the
        nightly mutation run's first find, 2026-10-14: dropping either bound survived)."""
        asked = {}

        def ping(ip, **kw):
            asked["ping"] = (ip, kw)
            return None

        def connect(addr, **kw):
            asked["connect"] = (addr, kw)
            raise TimeoutError("timed out")
        assert RE.probe("192.0.2.10", ping=ping, connect=connect) == (False, RE.CLAIM_NONE)
        assert asked["ping"][0] == "192.0.2.10" and asked["ping"][1]["timeout"] == 2
        assert asked["connect"] == (("192.0.2.10", 22), {"timeout": 2})

    def test_a_lan_device_answering_in_under_a_millisecond_is_up_by_icmp(self):
        """ping3 answers in milliseconds here; a device on the same segment answers in well
        under one (the nightly mutation run, 2026-10-14: `> 1` for `> 0` survived)."""
        assert RE.probe("192.0.2.10", ping=lambda ip, **kw: 0.4,
                        connect=lambda *a, **kw: _Accepted()) == (True, RE.CLAIM_ICMP)

    @pytest.mark.parametrize("error", [TimeoutError("timed out"),
                                       ConnectionRefusedError(111, "Connection refused"),
                                       OSError(113, "No route to host")])
    def test_a_device_that_answers_neither_is_down(self, error):
        def fails(*a, **kw):
            raise error
        assert RE.probe("192.0.2.10", ping=lambda ip, **kw: None,
                        connect=fails) == (False, RE.CLAIM_NONE)
