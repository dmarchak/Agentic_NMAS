"""The Grafana alert reader (modules/readers/grafana_alerts.py) and its Needs
attention source (attention.grafana_source), against the REAL capture in
tests/fixtures/grafana/ (read-only, 2026-09-28T20:25:30Z, sixteen rules, a
quiet fleet). Every firing case is a MINIMAL EDIT of a real piece: a real
rule's real instance with its state changed, or an Alertmanager entry
carrying that instance's real labels. Each test says which edit it made."""

import copy
import json
import os
import time

import pytest

from modules import attention as A
from modules import config
from modules import reader_job as R
from modules.readers import grafana_alerts as G

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "grafana")
READ_AT = 1790627130.0     # the capture's own time, 2026-09-28T20:25:30Z


def load(name):
    with open(os.path.join(FIX, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def rule(view, title):
    for grp in view["data"]["groups"]:
        for r in grp["rules"]:
            if r["name"] == title:
                return r
    raise KeyError(title)


def parse(view=None, alerts=None, read_at=READ_AT):
    return G.parse(load("ruler"), view or load("rules_view"), alerts or [], read_at)


# ---------------------------------------------------------------------------
# The reader, on the capture as it is
# ---------------------------------------------------------------------------

class TestTheQuietFleetAsCaptured:
    def test_every_rule_is_read_and_nothing_is_alerting(self):
        v = parse()
        assert v["counts"]["rules"] == 16 and v["configured_rules"] == 16
        assert v["instances"] == [] and v["stalled_groups"] == []
        # The three rules whose no-data state is OK by decision read
        # "Normal (NoData)": counted, never a row.
        assert v["counts"]["normal_no_data"] >= 3

    def test_which_device_comes_from_where_is_decided_per_rule(self):
        rules = {r["title"]: r for r in parse()["rules"]}
        assert rules["NMAS heartbeat missing: r1"]["device_source"]["from"] == "label"
        syslog = rules["Critical syslog received"]["device_source"]
        assert syslog["from"] == "line" and syslog["matches_definition"] is True
        assert rules["Device unreachable (SNMP)"]["device_source"]["from"] == "address_or_none"

    def test_a_line_rule_with_another_pattern_is_named_as_not_the_definition(self):
        """C166's first fix captured the IOS sequence number as the device."""
        wrong = G.device_source({}, ['sum by (device) ({job="x"} | regexp "(?P<device>\\\\d+): ")'])
        assert wrong["from"] == "line" and wrong["matches_definition"] is False
        assert "NOT the one definition" in wrong["why"]


class TestCompleteness:
    def test_a_rule_counting_more_instances_than_it_lists_is_refused(self):
        """Edit: drop one of Device unreachable's nine real instances."""
        view = load("rules_view")
        r = rule(view, "Device unreachable (SNMP)")
        r["alerts"] = r["alerts"][1:]
        with pytest.raises(G.PartialAnswer, match="counts 9 instances and lists 8"):
            parse(view)

    def test_a_next_page_token_is_refused(self):
        view = load("rules_view")
        view["data"]["groupNextToken"] = "abc"
        with pytest.raises(G.PartialAnswer, match="next-page token"):
            parse(view)

    def test_an_evaluator_that_stopped_is_its_own_state(self):
        """The same capture read four minutes later: 200, nothing firing,
        and nothing evaluated. It reads exactly like a healthy fleet."""
        v = parse(read_at=READ_AT + 240)
        assert {g["group"] for g in v["stalled_groups"]} == {"nmas-heartbeat", "1m"}
        assert parse(read_at=READ_AT + 60)["stalled_groups"] == []


class TestKindsAndTheJoin:
    def test_an_alerting_address_instance_is_a_condition_joined_to_its_fingerprint(self):
        """Edit: one real Device unreachable instance set Alerting, and the
        Alertmanager entry that carries its real labels."""
        view = load("rules_view")
        inst = next(a for a in rule(view, "Device unreachable (SNMP)")["alerts"]
                    if a["labels"]["instance"] == "10.255.1.11")
        inst["state"] = "Alerting"
        inst["activeAt"] = "2026-09-28T20:20:00Z"
        am = [{"fingerprint": "f1", "startsAt": "2026-09-28T20:22:00Z", "labels": dict(inst["labels"]),
               "status": {"state": "active", "silencedBy": []}}]
        (i,) = parse(view, am)["instances"]
        assert i["kind"] == "condition" and i["fingerprint"] == "f1"
        assert i["starts_at"] == "2026-09-28T20:22:00Z" and i["active_at"] == "2026-09-28T20:20:00Z"
        assert i["device_from"] == "address" and i["address"] == "10.255.1.11"
        assert "device" not in i, "an address is stored as an address, never a guessed name"

    def test_grafana_s_own_no_data_alert_is_no_data_never_a_condition(self):
        """C165: DatasourceNoData instances made "0 against 2" read as a
        disagreement. Edit: an Alertmanager entry of Grafana's own shape for
        a real rule."""
        am = [{"fingerprint": "f2", "startsAt": "2026-09-28T20:00:00Z",
               "labels": {"alertname": "DatasourceNoData", "rulename": "IP SLA probe failing",
                          "grafana_folder": "RCN Lab", "datasource_uid": "x", "ref_id": "A"},
               "status": {"state": "active"}}]
        v = parse(alerts=am)
        (i,) = v["instances"]
        assert i["kind"] == "no_data" and i["rule"] == "IP SLA probe failing"
        assert v["counts"]["no_data"] == 1 and v["counts"]["condition"] == 0
        assert v["alertmanager_only"] == 1


class TestTheRead:
    class Fake:
        def __init__(self, fail=None):
            self.asked, self.fail = [], fail

        def _get(self, path):
            self.asked.append(path)
            if path == self.fail:
                return {"ok": False, "error": "HTTP 403"}
            body = {G.RULER: load("ruler"), G.RULES_VIEW: load("rules_view"),
                    G.ALERTMANAGER: load("alertmanager")}[path]

            class Resp:
                def json(self):
                    return copy.deepcopy(body)
            return {"ok": True, "response": Resp()}

    def test_it_reads_the_three_endpoints_it_names(self):
        f = self.Fake()
        v = G.read(f)
        assert f.asked == [G.RULER, G.RULES_VIEW, G.ALERTMANAGER]
        assert set(G.READER.endpoints) == set(f.asked) and v["counts"]["rules"] == 16

    def test_a_refusal_names_the_endpoint_and_is_a_failed_attempt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
        with pytest.raises(ConnectionError, match="rules.*HTTP 403"):
            G.read(self.Fake(fail=G.RULES_VIEW))

    def test_the_reader_is_declared_with_its_measured_interval(self):
        assert G.READER in R.readers() and G.READER.interval_seconds == 60
        assert "60 s" in G.READER.interval_basis and G.READER.invalidates == ("alerts",)


# ---------------------------------------------------------------------------
# The Needs attention source, from the cache
# ---------------------------------------------------------------------------

INVENTORY = [{"hostname": h, "ip": ip} for h, ip in (
    ("r1", "10.255.1.11"), ("r2", "10.255.1.12"), ("r3", "10.255.1.13"), ("r4", "10.255.1.14"),
    ("r6", "10.255.0.32"), ("s1", "10.255.1.21"), ("s2", "10.255.1.22"), ("s3", "10.255.1.23"),
    ("s4", "10.255.1.24"))]


def cached(value, value_at=READ_AT):
    return {"state": "ok", "why": "", "doc": {
        "endpoints": list(G.READER.endpoints), "stale_after_seconds": 180,
        "last_good": {"value": value, "value_at": R._iso(value_at)}}}


@pytest.fixture
def inventory(monkeypatch):
    from modules import device
    monkeypatch.setattr(device, "load_saved_devices", lambda *a, **k: list(INVENTORY))


def heartbeat_silence(view, devices, silence_at, phase):
    """Edit: each named device's real heartbeat instance set Alerting at the
    moment its OWN window runs out after one silence, its last heartbeat
    `phase[d]` seconds before the silence (a device heartbeats every 300 s)."""
    for d in devices:
        inst = rule(view, f"NMAS heartbeat missing: {d}")["alerts"][0]
        window = int(inst["labels"]["window_seconds"])
        inst["state"] = "Alerting"
        inst["activeAt"] = R._iso(silence_at - phase[d] + window)
    return view


class TestTheSource:
    def test_nothing_stored_is_an_unknown_row_never_nothing_firing(self):
        res = A.grafana_source(cached={"state": "absent", "doc": None, "why": "no reader has run"})
        assert res["state"] == "unreadable" and "not read yet" in res["rows"][0]["cause"]

    def test_the_quiet_capture_draws_no_row_and_says_what_it_read(self, inventory):
        res = A.grafana_source(cached=cached(parse()))
        assert res["rows"] == [] and res["stale_after_seconds"] == 180
        assert res["value_at"] == R._iso(READ_AT)
        assert "16 rule(s)" in res["checked"] and "healthy by decision" in res["checked"]

    def test_an_alert_on_an_address_names_the_device_and_where_it_came_from(self, inventory):
        view = load("rules_view")
        inst = next(a for a in rule(view, "Device unreachable (SNMP)")["alerts"]
                    if a["labels"]["instance"] == "10.255.1.11")
        inst["state"], inst["activeAt"] = "Alerting", "2026-09-28T20:20:00Z"
        (row,) = A.grafana_source(cached=cached(parse(view)))["rows"]
        assert row["what"] == "Device unreachable (SNMP) is alerting on r1"
        assert row["level"] == "danger" and row["devices"] == ["r1"]
        (m,) = row["operands"]["members"]
        assert m["device_from"] == "address" and "10.255.1.11" in m["device_note"]
        assert row["triage"] is None, "the slot 8.6's triage attaches to"

    def test_an_address_no_device_holds_is_said_never_guessed(self, inventory):
        view = load("rules_view")
        inst = next(a for a in rule(view, "Device unreachable (SNMP)")["alerts"]
                    if a["labels"]["instance"] == "10.255.1.11")
        inst["state"], inst["labels"]["instance"] = "Alerting", "192.0.2.9"
        (row,) = A.grafana_source(cached=cached(parse(view)))["rows"]
        assert row["devices"] == [] and "matches no device" in row["cause"]

    def test_one_silence_across_the_fleet_is_one_incident_whose_subject_is_the_pipeline(self, inventory):
        """8.6: per-device windows fire one outage hundreds of seconds apart,
        so grouping on startsAt would split it; on the onset it is one."""
        devices = ["r1", "r2", "r3", "r4", "r6", "s1", "s2", "s3", "s4"]
        phase = {d: (37 * i) % 300 for i, d in enumerate(devices)}
        view = heartbeat_silence(load("rules_view"), devices, READ_AT - 3000, phase)
        rows = A.grafana_source(cached=cached(parse(view)))["rows"]
        (incident,) = rows
        assert incident["what"] == "Every device's syslog heartbeat stopped at once"
        assert sorted(incident["devices"]) == sorted(devices)
        assert len(incident["operands"]["members"]) == 9
        starts = [time.mktime(time.strptime(m["onset"], "%Y-%m-%dT%H:%M:%SZ"))
                  for m in incident["operands"]["members"]]
        assert max(starts) - min(starts) <= A.INCIDENT_GAP_SECONDS

    def test_two_silences_further_apart_than_an_onset_s_uncertainty_are_two(self, inventory):
        view = heartbeat_silence(load("rules_view"), ["r1"], READ_AT - 3000, {"r1": 0})
        view = heartbeat_silence(view, ["s4"], READ_AT - 3000 + A.INCIDENT_GAP_SECONDS + 60,
                                 {"s4": 0})
        rows = A.grafana_source(cached=cached(parse(view)))["rows"]
        assert sorted(r["what"] for r in rows) == ["NMAS heartbeat missing: r1 is alerting on r1",
                                                   "NMAS heartbeat missing: s4 is alerting on s4"]

    def test_a_rule_in_no_data_is_a_row_with_no_instance_needed(self, inventory):
        view = load("rules_view")
        rule(view, "Interface error rate elevated")["health"] = "nodata"
        (row,) = A.grafana_source(cached=cached(parse(view)))["rows"]
        assert row["what"] == "Interface error rate elevated reads no data"
        assert "unknown" in row["cause"] and row["level"] == "warning"

    def test_a_stalled_evaluator_is_a_danger_row(self, inventory):
        rows = A.grafana_source(cached=cached(parse(read_at=READ_AT + 240)))["rows"]
        assert {r["what"] for r in rows} == {"Grafana has stopped evaluating nmas-heartbeat",
                                             "Grafana has stopped evaluating 1m"}
        assert {r["level"] for r in rows} == {"danger"}

    def test_the_floor_names_an_inventory_device_with_no_heartbeat_rule_the_reader_sees(
            self, monkeypatch):
        from modules import device
        monkeypatch.setattr(device, "load_saved_devices",
                            lambda *a, **k: INVENTORY + [{"hostname": "r7", "ip": "10.255.0.40"}])
        (row,) = A.grafana_source(cached=cached(parse()))["rows"]
        assert row["id"] == "grafana:heartbeat-floor" and row["devices"] == ["r7"]
        assert "cannot see it" in row["cause"]

    def test_an_alert_for_a_device_that_left_is_named_as_that(self, monkeypatch):
        from modules import device
        monkeypatch.setattr(device, "load_saved_devices",
                            lambda *a, **k: [d for d in INVENTORY if d["hostname"] != "r6"])
        view = heartbeat_silence(load("rules_view"), ["r6"], READ_AT - 3000, {"r6": 0})
        (row,) = [r for r in A.grafana_source(cached=cached(parse(view)))["rows"]
                  if r["id"].startswith("grafana:incident")]
        assert "NOT in the inventory" in row["cause"]


class TestThePanelDrawsMembers:
    def test_each_member_with_its_device_origin_and_onset_basis(self, inventory, monkeypatch):
        devices = ["r1", "r2", "r3", "r4", "r6", "s1", "s2", "s3", "s4"]
        view = heartbeat_silence(load("rules_view"), devices, READ_AT - 3000,
                                 {d: 0 for d in devices})
        monkeypatch.setattr(A, "SOURCES", (lambda: A.grafana_source(cached=cached(parse(view))),))
        page = A.needs_attention()
        from tests.test_needs_attention import _panel
        html = _panel(page)
        assert html.count("<li>NMAS heartbeat missing:") == 9
        assert "from the rule&#39;s device label" in html or "from the rule's device label" in html
        assert "minus the rule" in html and "[object Object]" not in html
