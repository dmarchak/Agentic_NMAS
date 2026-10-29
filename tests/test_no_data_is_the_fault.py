"""A rule whose no data is its fault fires on it (C2174; the operator, 2026-10-29, B high):
heartbeat and telemetry alerts fire in Grafana as "Alerting (NoData)", which the alerts reader
classed as no data, so no evidence pack was built and they never appeared on Monitoring ›
Alerts (52 heartbeat and 31 telemetry episodes on record had none).

The property is the rule's own, as Grafana states it: its no-data state is ``Alerting``
(`grafana_alerts.no_data_is_fault`), which both generators set (scripts/nmas-heartbeat-rules,
scripts/nmas-telemetry-rules) and no hand-built rule in the capture does; Grafana carries it
into the state it reports, "Alerting (NoData)" (`grafana_alerts.alerting_on_no_data`).

The captures: tests/fixtures/grafana/ (ruler, rules view, 2026-09-28: nine heartbeat rules and
seven hand-built ones, a quiet fleet) and tests/fixtures/grafana/alert_history/ (the rules
view of 2026-10-26, with the telemetry rules; the state history of 21 Oct, whose heartbeat and
telemetry rules fired on no data). Each firing case is a minimal edit of a real piece, said
where it is made. The ruler capture predates the telemetry generator, so its telemetry rule is
the captured heartbeat ruler entry edited to the telemetry generator's own rule (its uid,
title, labels, query and window), checked against that generator's output.
"""
import copy
from html import unescape

import pytest

from modules import alert_history as H
from modules import evidence_pack as EP
from modules import telemetry_rules
from modules.ai import explain
from modules.readers import grafana_alerts as G
from tests import test_grafana_reader as GR
from tests.test_alert_history import load as history_load
from tests.test_device_v2 import _store, lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import NOW, pack_lab  # noqa: F401 (the fixture)
from tests.test_heartbeat_rules import H as HB
from tests.test_heartbeat_rules import INTERVAL, MEASURED, SYSLOG, _gaps

#: When the planted alert's condition first held: inside the Loki capture's hour (as
#: tests/test_evidence_pack.py's ACTIVE).
ACTIVE = "2026-10-15T08:15:00Z"
TEL_UID, TEL_TITLE = "nmas-tel-r1-101", "NMAS telemetry stream lost: r1 subscription 101"


def _ruler_rules(ruler):
    return [(folder, r) for folder, groups in ruler.items() for g in groups
            for r in g.get("rules") or []]


def _telemetry_ruler():
    """The captured ruler with one telemetry rule added: the captured `nmas-hb-r1` entry, edited
    to the telemetry generator's rule for r1's subscription 101 (`rule_for`)."""
    T = telemetry_rules._script()
    want = T.rule_for("r1", "101", "efwpn8hr7sfeob")
    ruler = GR.load("ruler")
    hb = next(r for _f, r in _ruler_rules(ruler) if r["grafana_alert"]["uid"] == "nmas-hb-r1")
    tel = copy.deepcopy(hb)
    ga = tel["grafana_alert"]
    ga.update(uid=want["uid"], title=want["title"], rule_group=T.GROUP,
              no_data_state=want["noDataState"], exec_err_state=want["execErrState"])
    ga["data"][0]["datasourceUid"] = want["data"][0]["datasourceUid"]
    ga["data"][0]["model"]["expr"] = want["data"][0]["model"]["expr"]
    ga["data"][0]["relativeTimeRange"] = dict(want["data"][0]["relativeTimeRange"])
    tel["labels"] = dict(want["labels"])
    tel["annotations"] = dict(want["annotations"])
    ruler.setdefault("NMAS", []).append({"name": T.GROUP, "interval": "1m", "rules": [tel]})
    return ruler


def _heartbeat_view(state):
    """The 2026-09-28 rules view, r3's real heartbeat instance set to *state* at ACTIVE."""
    view = GR.load("rules_view")
    inst = GR.rule(view, "NMAS heartbeat missing: r3")["alerts"][0]
    inst["state"], inst["activeAt"] = state, ACTIVE
    return view, inst


def _heartbeat_value(state="Alerting (NoData)"):
    """The reader's value with r3's heartbeat firing on no data, and the Alertmanager's entry
    for it carrying its real labels (as Grafana sends a no-data-alerting instance on)."""
    view, inst = _heartbeat_view(state)
    am = [{"fingerprint": "f-hb-r3", "startsAt": "2026-10-15T08:16:00Z",
           "labels": {k: v for k, v in inst["labels"].items() if not k.startswith("__")},
           "status": {"state": "active", "silencedBy": []}}]
    return G.parse(GR.load("ruler"), view, am, NOW)


def _telemetry_value(state="Alerting (NoData)"):
    """The 2026-10-26 rules view with r1's real subscription-101 instance set to *state*,
    against the ruler holding the telemetry rule."""
    view = history_load("rules_view")
    inst = GR.rule(view, TEL_TITLE)["alerts"][0]
    inst["state"], inst["activeAt"] = state, ACTIVE
    return G.parse(_telemetry_ruler(), view, [], NOW)


# ------------------------------------------------------------------------- the property

class TestThePropertyIsTheRulesOwn:
    def test_in_the_captured_ruler_exactly_the_heartbeat_rules_alert_on_no_data(self):
        """Measured: the nine heartbeat rules' no-data state is Alerting; the seven hand-built
        rules' is OK or NoData. The label is never what decides."""
        rules = _ruler_rules(GR.load("ruler"))
        assert len(rules) == 16
        fault = {r["grafana_alert"]["uid"] for _f, r in rules
                 if G.no_data_is_fault(r["grafana_alert"].get("no_data_state"))}
        heartbeat = {r["grafana_alert"]["uid"] for _f, r in rules
                     if (r.get("labels") or {}).get("nmas") == "heartbeat"}
        assert fault == heartbeat and len(fault) == 9
        others = {r["grafana_alert"]["no_data_state"] for _f, r in rules
                  if r["grafana_alert"]["uid"] not in fault}
        assert others == {"OK", "NoData"}

    def test_both_generators_write_the_property(self):
        """The shipped rules: each generator's rule alerts on no data, by the constant the
        reader reads (a generator that stopped would leave its rules no data again)."""
        infos = HB.windows({h: _gaps(*MEASURED[h]) for h in MEASURED}, INTERVAL)
        hb = HB.build(infos, "loki-uid", INTERVAL, SYSLOG)["groups"][0]["rules"]
        tel = telemetry_rules._script().rule_for("r1", "101", "prom-uid")
        assert all(r["noDataState"] == G.NO_DATA_FAULT_STATE for r in hb)
        assert tel["noDataState"] == G.NO_DATA_FAULT_STATE

    def test_the_telemetry_ruler_entry_is_the_generators_rule(self):
        """The minimal edit holds what the generator writes: the reader reads its window."""
        T = telemetry_rules._script()
        ruler = _telemetry_ruler()
        tel = next(r for _f, r in _ruler_rules(ruler) if r["grafana_alert"]["uid"] == TEL_UID)
        assert G.query_window_seconds(tel["grafana_alert"]["data"]) == T.WINDOW_SECONDS
        rules = {r["uid"]: r for r in _telemetry_value("Normal")["rules"]}
        assert rules[TEL_UID]["query_window_seconds"] == T.WINDOW_SECONDS
        assert rules["nmas-hb-r1"]["query_window_seconds"] == 750

    @pytest.mark.parametrize("state, fault", [
        ("Alerting (NoData)", True), ("alerting  (nodata)", True), ("NoData", False),
        ("Normal (NoData)", False), ("Pending (NoData)", False), ("Alerting", False),
        ("Alerting (NoData, KeepLast)", False), ("Alerting (Error)", False), ("", False)])
    def test_grafanas_state_words_are_matched_whole(self, state, fault):
        assert G.alerting_on_no_data(state) is fault

    def test_the_rules_word_governs_where_the_ruler_holds_it(self):
        """Grafana's state words alone (a history row) say it; the ruler's no-data state,
        where it holds the rule, must say it too."""
        assert G._kind("Alerting (NoData)") == "condition"
        assert G._kind("Alerting (NoData)", "Alerting") == "condition"
        assert G._kind("Alerting (NoData)", "NoData") == "no_data"
        assert G._kind("NoData", "Alerting") == "no_data"
        assert G._kind("Alerting (Error)", "Alerting") == "error"


# ------------------------------------------------------------------------- the reader

class TestTheReader:
    def test_a_heartbeat_firing_on_no_data_is_the_condition(self):
        v = _heartbeat_value()
        [inst] = v["instances"]
        assert inst["kind"] == "condition" and inst["state"] == "Alerting (NoData)"
        assert inst["absence"] == "no heartbeat received for 767 s from r3"
        assert inst["fingerprint"] == "f-hb-r3", "joined to its Alertmanager entry"
        assert v["counts"]["condition"] == 1 and v["counts"]["no_data"] == 0
        assert EP.firing(v) == [inst]

    def test_a_telemetry_stream_lost_on_no_data_is_the_condition(self):
        T = telemetry_rules._script()
        [inst] = _telemetry_value()["instances"]
        assert inst["kind"] == "condition" and inst["rule_uid"] == TEL_UID
        assert inst["absence"] == (f"no telemetry sample received on subscription 101 for "
                                   f"{T.WINDOW_SECONDS} s from r1")

    def test_another_rules_no_data_stays_no_data(self):
        """Edit: the captured `Interface error rate elevated` instance (its no-data state
        NoData) set to NoData, and `IP SLA probe failing` (its no-data state OK) set to
        Grafana's alerting words, which its own rule does not allow."""
        view = GR.load("rules_view")
        inst = GR.rule(view, "Interface error rate elevated")["alerts"][0]
        inst["state"], inst["activeAt"] = "NoData", ACTIVE
        ipsla = GR.rule(view, "IP SLA probe failing")["alerts"][0]
        ipsla["state"], ipsla["activeAt"] = "Alerting (NoData)", ACTIVE
        v = G.parse(GR.load("ruler"), view, [], NOW)
        assert {i["kind"] for i in v["instances"]} == {"no_data"}
        assert len(v["instances"]) == 2 and not any("absence" in i for i in v["instances"])
        assert EP.firing(v) == [] and v["counts"]["condition"] == 0


# ------------------------------------------------------------------------- the pack

class TestThePack:
    def test_it_is_built_when_it_fires_and_says_the_fault_is_the_absence(self, pack_lab):
        _store("grafana-alerts", _heartbeat_value(), at="2026-10-15T08:24:00Z")
        assert EP.after_alerts_read(clock=lambda: NOW) is True
        [pack] = EP.read()["rows"]
        alert = next(s for s in pack["sections"] if s["name"] == "alert")
        piece = alert["pieces"][0]
        assert piece["kind"] == "condition" and piece["state"] == "Alerting (NoData)"
        assert piece["absence"] == "no heartbeat received for 767 s from r3"
        assert pack["device"] == "r3" and EP.intact(pack)

    def test_another_rules_no_data_builds_no_pack(self, pack_lab):
        view = GR.load("rules_view")
        inst = GR.rule(view, "Interface error rate elevated")["alerts"][0]
        inst["state"], inst["activeAt"] = "NoData", ACTIVE
        _store("grafana-alerts", G.parse(GR.load("ruler"), view, [], NOW))
        assert EP.after_alerts_read(clock=lambda: NOW) is False
        assert EP.read()["state"] == "absent" and EP.tab()["counts"]["firing"] == 0

    def test_the_alerts_tab_lists_it_firing_and_the_pack_draws_the_absence(self, pack_lab):
        value = _heartbeat_value()
        _store("grafana-alerts", value, at="2026-10-15T08:24:00Z")
        assert EP.after_alerts_read(clock=lambda: NOW)
        t = EP.tab()
        assert t["counts"]["firing"] == 1 and t["counts"]["packed"] == 1
        [card] = t["groups"][0]["cards"]
        assert card["state"] == "Alerting (NoData)" and card["device"] == "r3"
        html = unescape(pack_lab["client"].get("/v2/monitoring/alerts").get_data(as_text=True))
        assert "1 firing</strong> · 1 with its evidence pack" in html
        assert f'data-keep="pack-{EP.alert_key(EP.firing(value)[0])}"' in html
        pid = card["pack"]["id"]
        r = pack_lab["client"].get(f"/v2/monitoring/alerts/pack/{pid}")
        drawn = unescape(r.get_data(as_text=True))
        assert r.status_code == 200
        assert ("The fault is the data's absence: <strong>no heartbeat received for 767 s "
                "from r3</strong>") in drawn
        assert "(condition, Alerting (NoData))" in drawn

    def test_a_secret_pasted_into_a_label_never_reaches_the_absence_words(self, pack_lab):
        """The absence words are built from the rule's labels, which reach Mercury unmasked;
        the pack's own mask keeps a pasted community out of them, as out of every label
        (test_evidence_pack's planted label). The minimal edit: r3's real heartbeat instance
        given a subscription label holding a pasted configuration line."""
        from tests.test_evidence_pack import SECRET, _text
        view, inst = _heartbeat_view("Alerting (NoData)")
        inst["labels"]["subscription"] = f"101; snmp-server community {SECRET} RO"
        am = [{"fingerprint": "f-hb-r3", "startsAt": "2026-10-15T08:16:00Z",
               "labels": {k: v for k, v in inst["labels"].items() if not k.startswith("__")},
               "status": {"state": "active", "silencedBy": []}}]
        _store("grafana-alerts", G.parse(GR.load("ruler"), view, am, NOW),
               at="2026-10-15T08:24:00Z")
        assert EP.after_alerts_read(clock=lambda: NOW)
        [pack] = EP.read()["rows"]
        piece = next(s for s in pack["sections"] if s["name"] == "alert")["pieces"][0]
        assert piece["absence"] == ("no heartbeat received on subscription 101; snmp-server "
                                    "community <redacted:snmp_community> RO for 767 s from r3")
        assert SECRET not in _text(pack) and EP.intact(pack)

    def test_a_pack_of_any_other_alert_carries_no_absence(self, pack_lab):
        from tests.test_evidence_pack import V4, _alerts
        _store("grafana-alerts", _alerts(V4), at="2026-10-15T08:24:00Z")
        assert EP.after_alerts_read(clock=lambda: NOW)
        [pack] = EP.read()["rows"]
        piece = next(s for s in pack["sections"] if s["name"] == "alert")["pieces"][0]
        assert "absence" not in piece


# ------------------------------------------------------------------------- Explain's guard

class TestExplainsGuard:
    def test_a_pack_firing_on_no_data_shows_the_fault(self, pack_lab):
        _store("grafana-alerts", _heartbeat_value(), at="2026-10-15T08:24:00Z")
        assert EP.after_alerts_read(clock=lambda: NOW)
        [pack] = EP.read()["rows"]
        why = explain.fault_shown(pack)
        assert why and "Alerting (NoData)" in why
        assert explain.needs_human_guard("no_fault_found", False, pack)["reason"]

    def test_a_no_data_kind_still_shows_none(self, pack_lab):
        _store("grafana-alerts", _heartbeat_value(), at="2026-10-15T08:24:00Z")
        assert EP.after_alerts_read(clock=lambda: NOW)
        [pack] = EP.read()["rows"]
        quiet = copy.deepcopy(pack)
        next(s for s in quiet["sections"] if s["name"] == "alert")["pieces"][0]["kind"] = \
            "no_data"
        assert explain.fault_shown(quiet) == ""
        assert explain.needs_human_guard("no_fault_found", False, quiet) == {}


# ------------------------------------------------------------------------- the history

@pytest.fixture
def on_record(pack_lab, monkeypatch):  # noqa: F811
    """The lab with the 21 Oct slice in its history as the reader and the backfill recorded it
    before C2174: each "Alerting (NoData)" row recorded ``no_data``. Nothing firing now."""
    monkeypatch.setattr(H, "_path", lambda: str(pack_lab["tmp"] / "alert_history.jsonl"))
    monkeypatch.setattr(H, "_networks", lambda: {"grafana-alerts": ["Lab"]})
    monkeypatch.setattr(H, "_firing_now", lambda: set())
    rows = [r for r in (H.from_annotation(a, "grafana-alerts", ["Lab"])
                        for a in history_load("annotations_firing")) if r]
    for r in rows:
        if r["state"] == "Alerting (NoData)":
            assert r["to"] == "condition", "recorded now, it is the condition"
            r["to"] = "no_data"
    assert H.record(rows)["added"] == 93
    return pack_lab


def _past(rule):
    return next(e for e in H.episodes(H.read()["rows"]) if e["rule"] == rule)


class TestTheHistory:
    def test_the_reader_records_it_firing_with_its_state_words(self):
        [row] = H.from_reader(_heartbeat_value(), "grafana-alerts", ["Lab"])
        assert row["to"] == "condition" and row["state"] == "Alerting (NoData)"

    def test_an_episode_on_record_as_no_data_reads_as_fired(self, on_record):
        e = _past("NMAS heartbeat missing: r2")
        assert e["outcome"] == "fired" and e["fired_at"] == e["started_at"]
        assert [s["state"] for s in e["states"]] == ["Alerting (NoData)"]
        assert H.read()["rows"][0]["schema"] == H.SCHEMA, "no row rewritten"
        assert any(r["to"] == "no_data" for r in H.read()["rows"]), "the record is as kept"

    def test_a_no_data_state_episode_still_reads_no_data(self, on_record):
        """Edit: a real resolve row of `Interface error rate elevated` set from Normal to
        NoData (its rule's no-data state is NoData), recorded."""
        a = copy.deepcopy(next(a for a in history_load("annotations_firing")
                               if a["newState"] == "Pending (NoData)"))
        a["newState"], a["id"], a["time"] = "NoData", 1, a["time"] - 3600_000
        row = H.from_annotation(a, "grafana-alerts", ["Lab"])
        assert row["to"] == "no_data" and H.kind_read(row) == "no_data"

    def test_build_evidence_builds_its_pack_saying_what_was_absent(self, on_record):
        """The 52 and 31 on record are not rebuilt by themselves: Build evidence builds each."""
        assert EP.read()["state"] == "absent", "nothing was built automatically"
        e = _past("NMAS heartbeat missing: r2")
        c = on_record["client"]
        r = c.post(f"/v2/monitoring/alerts/history/{e['id']}/evidence",
                   headers={"HX-Request": "true"})
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 200, html
        [pack] = EP.read()["rows"]
        piece = next(s for s in pack["sections"] if s["name"] == "alert")["pieces"][0]
        assert piece["state"] == "Alerting (NoData)" and piece["kind"] == "condition"
        assert piece["absence"] == "no heartbeat received for 750 s from r2"
        assert "The fault is the data's absence" in html
        assert explain.fault_shown(pack), "a past absence still shows the fault"

    def test_a_telemetry_episodes_window_is_its_rules_own(self, on_record):
        """A backfilled row carries no rule uid and the telemetry rule no window label: the
        window is the one the reader holds for the rule by its title."""
        T = telemetry_rules._script()
        e = _past(TEL_TITLE)
        inst = EP.episode_instance(e)
        assert inst["absence"] == ("no telemetry sample received on subscription 101 over the "
                                   "rule's window (not recorded) from r1")
        _store("grafana-alerts", _telemetry_value("Normal"))
        inst = EP.episode_instance(e)
        assert inst["state"] == "Alerting (NoData)"
        assert inst["absence"] == (f"no telemetry sample received on subscription 101 for "
                                   f"{T.WINDOW_SECONDS} s from r1")
