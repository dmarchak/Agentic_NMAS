"""NSOT_PLAN P.1: Grafana heartbeat rules generated from the NetBox inventory."""

import importlib.machinery
import importlib.util
import re

import pytest
import yaml


def _load():
    loader = importlib.machinery.SourceFileLoader(
        "hb_rules_under_test", "scripts/nmas-heartbeat-rules")
    spec = importlib.util.spec_from_loader("hb_rules_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


H = _load()
FLEET = {**{f"r{i}": "cisco_iosxe" for i in range(1, 7)},
         **{f"s{i}": "cisco_ios" for i in range(1, 5)}}

#: s3's line as rsyslog wrote it (measured, /var/log/network, 2026-09-22),
#: with the heartbeat message in place of the traceback -- the SHAPE is the
#: measured part: `<ts> <host> <seq>: <host>: <msg>`.
LINE = ("Sep 25 16:34:44 {h} 39: {h}: *Sep 25 16:34:44.799: "
        "%HA_EM-5-LOG: NMAS-HEARTBEAT: NMAS-HEARTBEAT")


class TestOneRulePerDevice:
    def test_every_device_has_exactly_one_rule(self):
        doc = H.build(FLEET, "loki-uid", 300)
        assert sorted(H.devices_in(doc)) == sorted(FLEET)
        uids = [r["uid"] for r in doc["groups"][0]["rules"]]
        assert len(uids) == len(set(uids)) == 10
        assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,40}", u) for u in uids)

    def test_silence_is_alerting_not_fine(self):
        """A silent device yields no series; NoData must fire."""
        for rule in H.build(FLEET, "loki-uid", 300)["groups"][0]["rules"]:
            assert rule["noDataState"] == "Alerting"
            assert rule["execErrState"] == "Alerting"

    def test_the_window_is_per_dialect(self):
        doc = H.build({"r2": "cisco_iosxe", "s4": "cisco_ios"}, "uid", 300)
        w = {r["labels"]["device"]: r["data"][0]["relativeTimeRange"]["from"]
             for r in doc["groups"][0]["rules"]}
        assert w == {"r2": 750, "s4": 999}

    @pytest.mark.parametrize("dialect", sorted(H.HEARTBEAT_RATE))
    def test_one_missed_is_quiet_and_two_missed_fire_at_the_MEASURED_spread(
            self, dialect):
        """The property, against each platform's measured real intervals:
        one missed heartbeat (two real intervals, at their longest) stays
        inside the window; two missed (three, at their shortest) fall
        outside."""
        _rate, (lo, hi), _where = H.HEARTBEAT_RATE[dialect]
        w = H.window_seconds(300, dialect)
        assert 2 * hi < w < 3 * lo, (dialect, w, lo, hi)

    def test_one_window_for_every_platform_would_fail(self):
        """Why it is per dialect: 2.5 x 300 s is quiet on one missed r2
        heartbeat and ALERTS on one missed s4 heartbeat."""
        _r, (lo, hi), _w = H.HEARTBEAT_RATE["cisco_ios"]
        assert 2 * hi > 750

    def test_an_unmeasured_dialect_is_refused_not_defaulted(self):
        with pytest.raises(ValueError, match="no measured heartbeat rate"):
            H.build({"n1": "nxos"}, "uid", 300)


class TestTheHostMatchIsAnchored:
    def test_r1_matches_its_own_line_and_not_r10s(self):
        pat = re.compile(H.host_pattern("r1"))
        assert pat.search(LINE.format(h="r1"))
        assert not pat.search(LINE.format(h="r10"))
        assert not pat.search(LINE.format(h="br1"))

    def test_a_dot_in_a_name_is_literal(self):
        pat = re.compile(H.host_pattern("sw.a"))
        assert pat.search(LINE.format(h="sw.a"))
        assert not pat.search(LINE.format(h="swxa"))


class TestRefusals:
    def test_an_empty_inventory_is_refused_not_written(self):
        with pytest.raises(ValueError, match="empty"):
            H.build({}, "loki-uid", 300)

    def test_no_datasource_is_refused(self):
        with pytest.raises(ValueError, match="datasource"):
            H.build({"r1": "cisco_iosxe"}, "", 300)

    @pytest.mark.parametrize("interval", [0, None, 30])
    def test_an_unusable_interval_is_refused(self, interval):
        """Measured: an unset setting read as 0 produced a 60 s window."""
        with pytest.raises(ValueError, match="heartbeat interval"):
            H.build({"r1": "cisco_iosxe"}, "loki-uid", interval)

    def test_an_unusable_name_is_refused(self):
        with pytest.raises(ValueError):
            H.build({'r1"} or vector(1) #': "cisco_iosxe"}, "loki-uid", 300)


def test_the_rendered_file_parses_back_to_the_same_rules():
    doc = H.build(FLEET, "loki-uid", 300)
    text = H.render(doc)
    assert text.startswith("# GENERATED")
    assert yaml.safe_load(text) == doc
