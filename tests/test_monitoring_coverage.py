"""Which integrations each device is configured for, from its committed golden
(the operator, 2026-09-30: r6 was called "unreachable" by an SNMP alert when
the truth is that its configuration has no SNMP).

The goldens are the REAL fleet configs; r6's shape (no SNMP) is r2's real
config with its `snmp-server` lines removed, and a heartbeat-bearing golden is
r2's with P.1's applet added (the fixtures predate P.1, C71).
"""

import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
R2 = open(os.path.join(FLEET, "r2.cfg"), encoding="utf-8").read()
NO_SNMP = "".join(l for l in R2.splitlines(True) if not l.startswith("snmp-server"))
HEARTBEAT = R2 + ("event manager applet NMAS-HEARTBEAT\n event timer watchdog time 300\n"
                  " action 1.0 syslog priority notifications msg \"NMAS-HEARTBEAT\"\n")


@pytest.fixture(autouse=True)
def _no_first_seen_record():
    """Each test starts with no first-seen record: rows() keeps one in the
    store, and a test must not inherit another's dates."""
    from modules import monitoring_coverage

    path = monitoring_coverage._state_path()
    if os.path.exists(path):
        os.remove(path)
    yield


class _Ref:
    name = "Default"


def _settings(prometheus="", loki=""):
    vals = {"prometheus_url": prometheus, "loki_url": loki}
    return lambda k, d=None: vals.get(k, d)


def _devs(*hosts):
    return [(_Ref(), {"hostname": h}) for h in hosts]


def _golden(texts):
    def read(_ref, host):
        v = texts[host]
        if isinstance(v, Exception):
            raise v
        return v
    return read


class TestConfigured:
    def test_every_fleet_golden_configures_snmp_and_syslog(self):
        from modules.monitoring_coverage import configured

        for name in sorted(os.listdir(FLEET)):
            got = configured(open(os.path.join(FLEET, name), encoding="utf-8").read())
            assert got["snmp"] and got["syslog"], name
        assert len(os.listdir(FLEET)) >= 9                                # the floor

    def test_r6s_shape_has_no_snmp_and_the_heartbeat_is_read_from_its_applet(self):
        from modules.monitoring_coverage import configured

        assert configured(NO_SNMP)["snmp"] is False and configured(NO_SNMP)["syslog"] is True
        assert configured(R2)["heartbeat"] is False and configured(HEARTBEAT)["heartbeat"] is True

    def test_a_mention_inside_a_stanza_is_not_a_configuration(self):
        from modules.monitoring_coverage import configured

        assert configured(" snmp-server community x RO\n")["snmp"] is False


class TestExpected:
    def test_only_what_a_configured_connector_uses(self):
        from modules.monitoring_coverage import expected

        assert expected(_settings()) == {}
        assert expected(_settings(prometheus="http://p")) == {"snmp": "Prometheus"}
        assert expected(_settings("http://p", "http://l")) == {"snmp": "Prometheus", "syslog": "Loki",
                                                               "heartbeat": "Loki"}


class TestTheRows:
    def test_r6_reads_not_monitored_by_snmp_in_the_operators_words(self):
        from modules.monitoring_coverage import rows

        (row,) = rows(_devs("r2", "r6"), _golden({"r2": R2, "r6": NO_SNMP}), _settings(prometheus="http://p"))
        assert row["state"] == "not_monitored" and row["device"] == "r6" and row["missing"] == ["snmp"]
        assert row["headline"] == "r6 is not monitored by SNMP"
        assert row["detail"].startswith("r6 is not monitored by SNMP: its configuration has no SNMP "
                                        "community (the network uses Prometheus) (SNMP since ")
        # The check's name is a question, never a claim beside the headline.
        assert row["what"].startswith("whether r6's committed configuration has what")
        assert "is configured for every" not in row["what"]
        assert row["action"]["label"].startswith("Apply the monitoring profile")
        assert "not built yet" in row["action"]["label"]

    def test_every_missing_integration_is_named_on_one_row(self):
        from modules.monitoring_coverage import rows

        (row,) = rows(_devs("r6"), _golden({"r6": NO_SNMP}), _settings("http://p", "http://l"))
        assert row["missing"] == ["snmp", "heartbeat"]
        assert row["headline"] == "r6 is not monitored by SNMP or the syslog heartbeat"

    def test_a_covered_device_is_no_row_and_nothing_expected_is_no_rows(self):
        from modules.monitoring_coverage import rows

        assert rows(_devs("r2"), _golden({"r2": HEARTBEAT}), _settings("http://p", "http://l")) == []
        assert rows(_devs("r6"), _golden({"r6": NO_SNMP}), _settings()) == []

    def test_an_unreadable_golden_is_unknown_never_not_configured(self):
        from modules.monitoring_coverage import rows

        (row,) = rows(_devs("r3"), _golden({"r3": OSError("git show failed")}), _settings(prometheus="http://p"))
        assert row["state"] == "unknown" and "not the same as not configured" in row["detail"]

    def test_no_golden_is_named(self):
        from modules.monitoring_coverage import rows

        (row,) = rows(_devs("r9"), _golden({"r9": ""}), _settings(prometheus="http://p"))
        assert row["state"] == "not_monitored" and row["headline"] == "r9 is not monitored: it has no committed golden"


class TestItIsDrawn:
    def test_needs_attention_draws_the_headline_with_its_action(self):
        from modules import attention
        from modules.monitoring_coverage import rows

        (row,) = rows(_devs("r6"), _golden({"r6": NO_SNMP}), _settings(prometheus="http://p"))
        got = attention.job_health_source(health=lambda: {"jobs": [row]})["rows"]
        assert len(got) == 1
        assert got[0]["what"] == "r6 is not monitored by SNMP" and got[0]["level"] == "warning"
        assert got[0]["devices"] == ["r6"]
        assert got[0]["action"]["label"].startswith("Apply the monitoring profile")

    def test_job_health_carries_the_rows(self, monkeypatch):
        from modules import job_health

        monkeypatch.setattr("modules.monitoring_coverage.rows",
                            lambda: [{"unit": "monitoring:r6", "state": "not_monitored", "max_age_minutes": 0}])
        assert job_health.monitoring_rows() == [{"unit": "monitoring:r6", "state": "not_monitored",
                                                  "max_age_minutes": 0}]


class TestSince:
    """The operator: "the condition began at a known moment (when r6 left the
    targets), so record and show it"."""

    def test_snmp_is_dated_by_the_keeper_that_stopped_scraping_it(self):
        from modules.monitoring_coverage import rows

        keeper = {"r6": {"since": "2026-09-30T18:02:11Z", "why": "its committed golden configures no SNMP"}}
        (row,) = rows(_devs("r6"), _golden({"r6": NO_SNMP}), _settings(prometheus="http://p"),
                      now=1790800000, keeper=keeper)
        assert row["since"] == 1790791331.0
        assert "SNMP since the target files stopped including it, 2026-09-30T18:02:11Z" in row["detail"]

    def test_a_gap_nothing_acted_on_is_dated_from_first_sight_and_kept(self):
        from modules.monitoring_coverage import rows

        args = (_devs("r6"), _golden({"r6": R2}), _settings(loki="http://l"))
        (first,) = rows(*args, now=1790790000, keeper={})
        (again,) = rows(*args, now=1790799999, keeper={})
        assert first["since"] == again["since"] == 1790790000
        assert "the syslog heartbeat since this check first saw it, 2026-09-30T" in again["detail"]

    def test_a_closed_gap_is_forgotten(self):
        from modules.monitoring_coverage import rows

        rows(_devs("r6"), _golden({"r6": R2}), _settings(loki="http://l"), now=1790790000, keeper={})
        assert rows(_devs("r6"), _golden({"r6": HEARTBEAT}), _settings(loki="http://l"), keeper={}) == []
        (row,) = rows(_devs("r6"), _golden({"r6": R2}), _settings(loki="http://l"), now=1790799000, keeper={})
        assert row["since"] == 1790799000

    def test_needs_attention_draws_the_since(self):
        from modules import attention
        from modules.monitoring_coverage import rows

        keeper = {"r6": {"since": "2026-09-30T18:02:11Z"}}
        (row,) = rows(_devs("r6"), _golden({"r6": NO_SNMP}), _settings(prometheus="http://p"), keeper=keeper)
        (drawn,) = attention.job_health_source(health=lambda: {"jobs": [row]})["rows"]
        assert drawn["since"] == "2026-09-30T18:02:11Z"
