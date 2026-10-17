"""The pending-onboarding tracker tells a person when to press Verify (C1193; the operator's walk
W4, 2026-10-17: no live refresh, no probe after "fetched" marking "answering: ready to Verify",
no elapsed time or the 15-minute stop rule, no title, no In progress entry for the wait).

- the onboarding-progress reader (modules/readers/onboarding_progress.py) reads each pending
  onboarding's stage and, once there is something to answer, probes its address with the
  reachability reader's own read-only probe; it announces `pending` when a stage, an answer or
  the stop rule moves, never for a read's own time;
- the pending page draws "<device> onboarding progress" with its ZTP or static badge, the
  answer from the reader's store (never asked per request), the wait's time from its Create
  (the stepper's live clock), the stop rule, and re-reads itself on `pending`;
- the top bar's In progress chip lists the wait.

The device side is a fake at the probe's and `ztp.progress`'s seams; nothing reaches a network.
"""

import re

import pytest

from modules.readers import onboarding_progress as OP
from tests.test_onboard_v2 import TestAPendingDevice as P
from tests.test_onboard_v2 import client  # noqa: F401 (the fixture)

NOW = 1_760_731_200.0                                  # 2025-10-17T20:00:00Z
CREATED = "2025-10-17T19:50:00Z"                       # ten minutes before NOW
LONG_AGO = "2025-10-17T19:40:00Z"                      # twenty minutes before NOW
ZTP = {"name": "s5", "address_source": "ztp", "mgmt_ip": "", "mgmt_mac": "aa:bb:cc:00:02:60",
       "reserved_address": "192.0.2.60", "onboarded_at": CREATED}
STATIC = {"name": "s7", "address_source": "static", "mgmt_ip": "192.0.2.70",
          "onboarded_at": CREATED}


def _probe(answers=True):
    asked = []

    def probe(ip):
        asked.append(ip)
        return (True, "accepted a TCP connection on port 22 within 2 s") if answers else (
            False, "answered neither ICMP nor TCP 22 within 2 s each")
    return probe, asked


def _stage(stage):
    return lambda row: {"stage": stage, "summary": f"{stage} summary"}


class TestTheReader:

    def test_a_device_that_fetched_is_probed_and_answering_is_ready_to_verify(self):
        probe, asked = _probe()
        d = OP.judge("Lab", dict(ZTP), NOW, progress=_stage("fetched_not_reached"),
                     probe=probe)
        assert asked == ["192.0.2.60"]
        assert d["answering"] is True and "TCP connection on port 22" in d["claim"]
        assert d["probed_at"] == "2025-10-17T20:00:00Z" and d["stop"] is False

    def test_a_device_that_has_not_fetched_is_not_probed(self):
        """The control: before its fetch there is nothing of its own to answer."""
        probe, asked = _probe()
        d = OP.judge("Lab", dict(ZTP), NOW, progress=_stage("leased_not_fetched"), probe=probe)
        assert asked == [] and d["answering"] is None

    def test_a_static_device_is_probed_at_its_address(self):
        probe, asked = _probe(answers=False)
        d = OP.judge("Lab", dict(STATIC), NOW, probe=probe)
        assert asked == ["192.0.2.70"] and d["answering"] is False and d["stage"] == ""

    @pytest.mark.parametrize("created, stage, stop", [
        (LONG_AGO, "leased_not_fetched", True),
        (LONG_AGO, "reserved_not_leased", True),
        (CREATED, "leased_not_fetched", False),          # ten minutes: not yet
        (LONG_AGO, "fetched_not_reached", False),        # it fetched: the rule is met
    ])
    def test_the_stop_rule_is_no_fetch_fifteen_minutes_on(self, created, stage, stop):
        probe, _asked = _probe()
        d = OP.judge("Lab", dict(ZTP, onboarded_at=created), NOW, progress=_stage(stage),
                     probe=probe)
        assert d["stop"] is stop

    def test_it_reads_every_pending_device_and_says_one_it_could_not(self):
        def progress(row):
            raise RuntimeError("Kea down")
        probe, _asked = _probe()
        got = OP.read(pop=[("Lab", dict(ZTP)), ("Lab", dict(STATIC))], clock=lambda: NOW,
                      progress=progress, probe=probe)
        assert set(got["devices"]) == {"Lab/s5", "Lab/s7"}
        assert got["devices"]["Lab/s5"]["stage"] == "unknown"
        assert "Kea down" in got["devices"]["Lab/s5"]["summary"]
        assert got["devices"]["Lab/s7"]["answering"] is True

    def test_it_announces_a_move_and_never_a_read_time(self):
        a = {"devices": {"Lab/s5": dict(OP.judge("Lab", dict(ZTP), NOW,
                                                 progress=_stage("leased_not_fetched")))},
             "read_at": "t1"}
        later = {"devices": {"Lab/s5": dict(a["devices"]["Lab/s5"], probed_at="t2")},
                 "read_at": "t2"}
        assert not OP.changed(a, later)
        moved = {"devices": {"Lab/s5": dict(a["devices"]["Lab/s5"],
                                            stage="fetched_not_reached")}}
        assert OP.changed(a, moved)
        assert OP.changed(a, dict(a, devices={}))

    def test_its_population_is_every_networks_pending_onboardings_and_creates_nothing(
            self, monkeypatch, tmp_path):
        from modules.nsot import manifest
        repo = tmp_path / "lab" / "config_repo"
        repo.mkdir(parents=True)
        manifest.upsert_device(str(repo), "uid:s5", "s5", pending=True, address_source="ztp",
                               mgmt_mac="aa:bb:cc:00:02:60", reserved_address="192.0.2.60")
        manifest.upsert_device(str(repo), "uid:r1", "r1", mgmt_ip="192.0.2.1")   # not pending
        monkeypatch.setattr("modules.integration_groups.network_names", lambda: ["Lab", "Gone"])
        monkeypatch.setattr("modules.config.list_data_path",
                            lambda name: str(tmp_path / name.lower()))
        pop = OP.population()
        assert [(n, r["name"]) for n, r in pop] == [("Lab", "s5")]
        assert not (tmp_path / "gone").exists()

    def test_it_is_declared_and_announces_pending_and_in_progress(self):
        from modules import reader_job
        assert "modules.readers.onboarding_progress" in reader_job.DECLARED_MODULES
        assert set(OP.READER.invalidates) == {"pending", "in_progress"}
        assert OP.READER.announce_at_least_every == OP.KEEPALIVE_SECONDS > 0


def _stored(monkeypatch, d):
    monkeypatch.setattr(OP, "stored", lambda list_name, name: (
        (dict(d, read_at="2026-10-10T09:01:00Z"), "") if d is not None
        else (None, "the reader has not stored a value yet")))


def _page(client, monkeypatch, row, stage=None, stored=None):  # noqa: F811
    monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [dict(row)])
    if stage:
        monkeypatch.setattr("modules.nsot.ztp.progress", lambda entry: {
            "stage": stage, "summary": f"{stage.replace('_', ' ')} now"})
    _stored(monkeypatch, stored)
    return client.get(f"/v2/device/{row['name']}").get_data(as_text=True)


ZTP_ROW = dict(P.PENDING, address_source="ztp", mgmt_ip="", mgmt_mac="aa:bb:cc:00:02:60",
               reserved_address="192.0.2.60")
ANSWERING = {"answering": True, "claim": "accepted a TCP connection on port 22 within 2 s",
             "probed_at": "2026-10-10T09:01:00Z", "address": "192.0.2.60",
             "stage": "fetched_not_reached", "stop": False}


class TestThePage:

    def test_it_is_titled_with_its_way_and_re_reads_itself_on_pending(  # noqa: F811
            self, client, monkeypatch):
        html = _page(client, monkeypatch, ZTP_ROW, "leased_not_fetched")
        assert re.search(r'<h2 id="ob-steps-h">bp1 onboarding progress</h2>\s*'
                         r'<span class="badge badge-info">ZTP</span>', html), html
        wrap = re.search(r'<div id="pending-progress"[^>]*>', html).group(0)
        assert 'hx-trigger="nmas:pending from:body"' in wrap
        assert 'hx-get="/v2/device/bp1/pending/progress?list=' in wrap
        static = _page(client, monkeypatch, P.PENDING)
        assert '<span class="badge badge-info">static</span>' in static

    def test_answering_after_its_fetch_says_ready_to_verify(self, client, monkeypatch):  # noqa: F811
        html = _page(client, monkeypatch, ZTP_ROW, "fetched_not_reached", ANSWERING)
        assert "Answering: ready to Verify." in html
        assert "accepted a TCP connection on port 22 within 2 s" in html
        assert "sent nothing: no login was tried" in html
        waiting = html[html.index('data-step="waiting"'):]
        assert "answering: ready to Verify" in waiting[:waiting.index("</li>")]

    def test_no_answer_yet_says_so_and_before_its_fetch_says_nothing(  # noqa: F811
            self, client, monkeypatch):
        html = _page(client, monkeypatch, ZTP_ROW, "fetched_not_reached",
                     dict(ANSWERING, answering=False,
                          claim="answered neither ICMP nor TCP 22 within 2 s each"))
        assert "Not answering yet." in html and "Answering: ready" not in html
        html = _page(client, monkeypatch, ZTP_ROW, "fetched_not_reached", None)
        assert "Not probed yet:" in html
        html = _page(client, monkeypatch, ZTP_ROW, "leased_not_fetched",
                     dict(ANSWERING, answering=None, stage="leased_not_fetched"))
        assert "Answering" not in html and "Not probed yet" not in html

    def test_the_wait_counts_from_its_create(self, client, monkeypatch):  # noqa: F811
        html = _page(client, monkeypatch, ZTP_ROW, "leased_not_fetched")
        waiting = html[html.index('data-step="waiting"'):]
        waiting = waiting[:waiting.index("</li>")]
        assert f'data-run-since="{P.PENDING["onboarded_at"]}"' in waiting, waiting
        assert "The stop rule: no fetch 15 minutes after boot: stop." in html

    def test_the_stop_rule_fires_fifteen_minutes_on_with_no_fetch(  # noqa: F811
            self, client, monkeypatch):
        late = dict(ZTP_ROW, age_seconds=OP.STOP_AFTER_S + 60)
        html = _page(client, monkeypatch, late, "leased_not_fetched")
        assert "<strong>No fetch 15 minutes after boot: stop.</strong>" in html
        # The controls: before fifteen minutes, and after a fetch, it does not fire.
        html = _page(client, monkeypatch, ZTP_ROW, "leased_not_fetched")
        assert "<strong>No fetch 15 minutes" not in html
        html = _page(client, monkeypatch, late, "fetched_not_reached")
        assert "<strong>No fetch 15 minutes" not in html

    def test_its_fragment_draws_alone_and_says_when_it_is_no_longer_pending(  # noqa: F811
            self, client, monkeypatch):
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [dict(ZTP_ROW)])
        monkeypatch.setattr("modules.nsot.ztp.progress", lambda entry: {
            "stage": "fetched_not_reached", "summary": "fetched"})
        _stored(monkeypatch, ANSWERING)
        frag = client.get("/v2/device/bp1/pending/progress").get_data(as_text=True)
        assert frag.lstrip().startswith('<div id="pending-progress"')
        assert "Answering: ready to Verify." in frag and "<html" not in frag
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [])
        gone = client.get("/v2/device/bp1/pending/progress").get_data(as_text=True)
        assert "bp1 is no longer pending" in gone and 'id="pending-progress"' in gone


class TestTheInProgressChip:

    @pytest.fixture
    def quiet(self, monkeypatch, tmp_path):
        (tmp_path / "lab" / "config_repo").mkdir(parents=True)
        monkeypatch.setattr("modules.nsot.device_ops.in_flight", lambda name, now: [])
        monkeypatch.setattr("modules.op_progress.running", lambda now: [])
        monkeypatch.setattr("modules.nsot.capture_job.card_jobs", lambda now: [])
        # The path that only asks (a read creates no list).
        monkeypatch.setattr("modules.config.list_data_path", lambda name: str(tmp_path / "lab"))

    @staticmethod
    def _reader_store(monkeypatch, pop):
        """The reader's store as its own `read` writes it from *pop* (never a hand-built
        shape): the chip reads only this, never a manifest (tests/test_scale.py)."""
        from modules import reader_job
        value = OP.read(pop=pop, clock=lambda: NOW,
                        progress=lambda row: {"stage": "fetched_not_reached", "summary": ""},
                        probe=lambda addr: (True, ANSWERING["claim"]))
        monkeypatch.setattr(reader_job, "read_cached", lambda name: {
            "state": "ok", "why": "",
            "doc": {"last_good": {"value": value, "value_at": "2026-10-10T09:01:00Z"}}})

    def test_a_pending_onboarding_is_a_wait_in_progress(self, quiet, monkeypatch):
        from modules import in_flight as F
        self._reader_store(monkeypatch, [("Lab", dict(ZTP_ROW))])
        chip = F.chip(["Lab"], "op@example.invalid", now=NOW)
        assert len(chip["running"]) == 1, chip
        row = chip["running"][0]
        assert row["device"] == "bp1" and row["list"] == "Lab" and row["page"] is True
        assert row["name"] == "Onboarding: waiting for it"
        assert row["step"] == "answering: ready to Verify"
        assert chip["shown"] and chip["level"] == "run"

    def test_nothing_pending_lists_nothing(self, quiet, monkeypatch):
        """The control: no pending onboarding, no row."""
        from modules import in_flight as F
        self._reader_store(monkeypatch, [])
        chip = F.chip(["Lab"], "op@example.invalid", now=NOW)
        assert chip["running"] == [] and not chip["shown"]

    def test_another_networks_pending_onboarding_is_not_listed(self, quiet, monkeypatch):
        """The chip lists the networks it is asked about, read from the one store."""
        from modules import in_flight as F
        self._reader_store(monkeypatch, [("Other", dict(ZTP_ROW))])
        chip = F.chip(["Lab"], "op@example.invalid", now=NOW)
        assert chip["running"] == [], chip

    def test_the_onboarding_routes_tell_the_chip(self):
        from modules import invalidation as I
        for route in ("onboard_v2.create", "onboard_v2.verify", "onboard_v2.abandon"):
            assert "in_progress" in I.keys_for(route), route
