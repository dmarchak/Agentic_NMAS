"""History past the live store's retention (C406; NSOT_STAGE7_PLAN 14.2).

From about 2026-11-28 the tool could not show a metric older than 90 days, though Thanos held
it: every panel read Grafana's live Prometheus datasource, and a range past 90 days was
refused. Measured 2026-10-04 (read-only, via LAN): Thanos Query answers the tool's own reads
the same as Prometheus (the targets, coverage's two queries, adjacencies, restarts, 30- and
60-day ranges exactly; one rate to 2.13e-16 relative, summation order), adding only its
external labels (`monitor`, `replica`) to raw selectors.

Now a panel range longer than `metrics_live_retention_days` reads the datasource named by
`grafana_history_datasource_uid` (empty by default, so nothing changes until it is set): the
same expression on the store that keeps it, said in the panel's foot line; the range control
says both stores; a setting naming a datasource Grafana does not hold, or a non-PromQL one, is
refused naming it. The datasource list is the host's shape (uid, type, name), the UIDs
replaced.
"""

import pytest

from modules import panels
from tests.test_telemetry_fold import _Grafana, stored  # noqa: F401 (the fixture)

DATASOURCES = [{"uid": "grafana", "type": "datasource", "name": "-- Grafana --", "is_default": False},
               {"uid": "thanos-lake", "type": "prometheus", "name": "Thanos (lake)",
                "is_default": False},
               {"uid": "loki", "type": "loki", "name": "loki", "is_default": False},
               {"uid": "prom", "type": "prometheus", "name": "prometheus", "is_default": True}]
DAY = 86400


@pytest.fixture
def settings(monkeypatch):
    values = {}
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: values.get(key, default))
    return values


class TestTheHistoryStore:
    def test_unset_is_none_and_says_nothing(self, settings):
        assert panels.history_store(DATASOURCES) == (None, "")

    def test_set_names_grafanas_promql_datasource(self, settings):
        settings["grafana_history_datasource_uid"] = "thanos-lake"
        assert panels.history_store(DATASOURCES) == (
            {"uid": "thanos-lake", "type": "prometheus", "name": "Thanos (lake)"}, "")

    @pytest.mark.parametrize("uid,why", [("gone", "is not one Grafana holds"),
                                         ("loki", "is a loki datasource, not PromQL")])
    def test_a_wrong_setting_is_said(self, settings, uid, why):
        settings["grafana_history_datasource_uid"] = uid
        ds, said = panels.history_store(DATASOURCES)
        assert ds is None and why in said


class TestTheRangeIsServedNeverTrimmed:
    def test_within_the_live_store_needs_no_history(self, settings):
        panels.check_range(90 * DAY, "prometheus")

    def test_past_it_with_no_history_is_refused_naming_the_setting(self, settings):
        with pytest.raises(panels.RangeRefused, match=r"the live store keeps 90 days, and no "
                                                      r"history store is set"):
            panels.check_range(91 * DAY, "prometheus")

    def test_past_it_with_a_wrong_setting_is_refused_naming_why(self, settings):
        settings["grafana_history_datasource_uid"] = "gone"
        history, why = panels.history_store(DATASOURCES)
        with pytest.raises(panels.RangeRefused, match="gone .* is not one Grafana holds"):
            panels.check_range(91 * DAY, "prometheus", history, why)

    def test_past_it_with_history_is_served(self, settings):
        settings["grafana_history_datasource_uid"] = "thanos-lake"
        panels.check_range(400 * DAY, "prometheus", *panels.history_store(DATASOURCES))

    def test_the_live_retention_is_the_setting(self, settings):
        settings["metrics_live_retention_days"] = 30
        with pytest.raises(panels.RangeRefused, match="the live store keeps 30 days"):
            panels.check_range(31 * DAY, "prometheus")

    def test_loki_keeps_its_own_limit(self, settings):
        settings["grafana_history_datasource_uid"] = "thanos-lake"
        with pytest.raises(panels.RangeRefused, match="Loki serves at most 30 days"):
            panels.check_range(31 * DAY, "loki", *panels.history_store(DATASOURCES))


def _traffic(stored):  # noqa: F811
    return next(p for p in stored["panels"] if p.get("title") == "Traffic in")


class TestThePanelReadsTheStoreThatKeepsTheRange:
    def test_a_long_range_asks_the_history_store_the_same_expression(self, settings, stored):  # noqa: F811
        settings["grafana_history_datasource_uid"] = "thanos-lake"
        history, why = panels.history_store(DATASOURCES)
        prom = panels.default_datasource(DATASOURCES, "prometheus")
        short = panels.build_request(_traffic(stored), stored, {"device": "s1"}, 7 * DAY, prom,
                                     history, why)
        long = panels.build_request(_traffic(stored), stored, {"device": "s1"}, 180 * DAY, prom,
                                    history, why)
        assert {q["datasource"]["uid"] for q in short["queries"]} == {"prom"}
        assert {q["datasource"]["uid"] for q in long["queries"]} == {"thanos-lake"}
        assert [q["expr"] for q in short["queries"]] == [q["expr"] for q in long["queries"]]
        assert long["queries"][0]["intervalMs"] >= 15 * 60 * 1000, "a long range, a wide step"

    def test_the_panel_says_which_store_answered(self, settings, stored):  # noqa: F811
        settings["grafana_history_datasource_uid"] = "thanos-lake"
        history, _why = panels.history_store(DATASOURCES)
        prom = panels.default_datasource(DATASOURCES, "prometheus")
        assert panels.store_words(7 * DAY, _traffic(stored), stored, {"device": "s1"}, prom,
                                  history) == ""
        assert panels.store_words(180 * DAY, _traffic(stored), stored, {"device": "s1"}, prom,
                                  history) == ("from the history store Thanos (lake): the live "
                                               "store keeps 90 days")

    def test_the_range_control_says_both_stores(self, settings):
        assert panels.limit_words(DATASOURCES) == "The live store keeps 90 days"
        settings["grafana_history_datasource_uid"] = "thanos-lake"
        assert panels.limit_words(DATASOURCES) == ("The live store keeps 90 days; a longer range "
                                                   "reads the history store Thanos (lake)")

    def test_through_the_device_panel_request(self, settings, stored, monkeypatch):  # noqa: F811
        from modules import device_page
        value = {"dashboards": {"nmas-device": stored}, "datasources": DATASOURCES}
        monkeypatch.setattr(device_page, "_cached", lambda reader, *_l: (value, "2026-10-04T00:00:00Z", ""))
        settings["grafana_history_datasource_uid"] = "thanos-lake"
        asked = []

        class G(_Grafana):
            def query(self, body):
                asked.append(body)
                return super().query(body)

        payload, status = device_page.panel_data({"hostname": "s1"}, "Default", "nmas-device",
                                                 _traffic(stored)["id"], "180d", client=G())
        assert status == 200, payload
        assert {q["datasource"]["uid"] for q in asked[0]["queries"]} == {"thanos-lake"}
        assert payload["store"].startswith("from the history store Thanos (lake)")
        payload, status = device_page.panel_data({"hostname": "s1"}, "Default", "nmas-device",
                                                 _traffic(stored)["id"], "7d", client=G())
        assert status == 200 and payload["store"] == ""


def test_the_foot_line_draws_the_store():
    import json
    import os

    import dukpy
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "static", "js", "nmas_panels.js"), encoding="utf-8").read()
    got = json.loads(dukpy.evaljs("var window = {};\n" + src + "\nJSON.stringify("
                                  "window.NMAS_PANELS.footWords({range: '180 days', step: 21600, "
                                  "store: 'from the history store Thanos (lake): the live store "
                                  "keeps 90 days'}));"))
    assert got == ("180 days, step 21600 s · from the history store Thanos (lake): the live "
                   "store keeps 90 days")
