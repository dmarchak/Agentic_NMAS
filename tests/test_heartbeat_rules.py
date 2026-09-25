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
FLEET = ["r1", "r2", "r3", "r4", "r5", "r6", "s1", "s2", "s3", "s4"]

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

    def test_the_window_is_2_5_intervals(self):
        rule = H.build(["r1"], "loki-uid", 300)["groups"][0]["rules"][0]
        assert rule["data"][0]["relativeTimeRange"]["from"] == 750
        assert "[750s]" in rule["data"][0]["model"]["expr"]

    @pytest.mark.parametrize("interval", [60, 300, 600])
    def test_one_missed_is_quiet_and_two_missed_fire_at_measured_jitter(
            self, interval):
        """The property, not the constant. With the jitter measured on s4
        (91 s, scaled to the interval's tolerance), a gap of one missed
        heartbeat stays inside the window and a gap of two falls outside."""
        w = H.window_seconds(interval)
        jitter = min(H.MEASURED_JITTER_SECONDS,
                     interval * H.MAX_TOLERATED_JITTER_FRACTION - 1)
        one_missed_worst = 2 * interval + jitter
        two_missed_best = 3 * interval - jitter
        assert one_missed_worst < w < two_missed_best, (interval, w)


    def test_the_query_names_the_datasource_and_the_marker(self):
        rule = H.build(["r1"], "loki-uid", 300)["groups"][0]["rules"][0]
        assert rule["data"][0]["datasourceUid"] == "loki-uid"
        expr = rule["data"][0]["model"]["expr"]
        assert '{job="network_syslog"}' in expr and '"NMAS-HEARTBEAT"' in expr
        assert "|~ `" in expr, "the regex must be a raw (backtick) string"


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
            H.build([], "loki-uid", 300)

    def test_no_datasource_is_refused(self):
        with pytest.raises(ValueError, match="datasource"):
            H.build(["r1"], "", 300)

    @pytest.mark.parametrize("interval", [0, None, 30])
    def test_an_unusable_interval_is_refused(self, interval):
        """Measured: an unset setting read as 0 produced a 60 s window."""
        with pytest.raises(ValueError, match="heartbeat interval"):
            H.build(["r1"], "loki-uid", interval)

    def test_an_unusable_name_is_refused(self):
        with pytest.raises(ValueError):
            H.build(['r1"} or vector(1) #'], "loki-uid", 300)


def test_the_rendered_file_parses_back_to_the_same_rules():
    doc = H.build(FLEET, "loki-uid", 300)
    text = H.render(doc)
    assert text.startswith("# GENERATED")
    assert yaml.safe_load(text) == doc
