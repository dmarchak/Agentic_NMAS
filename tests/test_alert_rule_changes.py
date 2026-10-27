"""A change to a Grafana alert rule made in Grafana is recorded and drawn in History (C1886;
the operator, 2026-10-27: "Mercury should record the rule change (provisioning version or
rule-file hash, who, when) in History"; `modules/alert_rule_changes.py`).

The capture is the real ruler answer in tests/fixtures/grafana/ruler.json (read-only,
2026-09-28T20:25:30Z, sixteen rules): every rule carries its ``version``, ``updated`` and
``updated_by`` (``admin`` and ``nmas-automation`` for rules saved by a login, and
``{"name": "", "uid": "service"}`` with ``provenance: file`` for the nine file-provisioned
heartbeat rules). "Device unreachable (SNMP)" is version 11 in it (12 on the host when the
finding was raised). Every change below is a MINIMAL EDIT of that captured rule, said where it
is made: the version moved by one, ``updated`` and ``updated_by`` set as Grafana sets them on a
save, and the one field the test is about changed.
"""

import copy
import json
import os
import types

import pytest

from modules import alert_rule_changes as ARC
from modules import history_sources as HS
from modules.readers import grafana_alerts as G

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "grafana")
STORE = "grafana-alerts"
SNMP = "Device unreachable (SNMP)"
SNMP_UID = "afy1y3yecuyv4d"
NOW = 1792950000.0          # 2026-10-26T22:20:00Z, after every captured `updated`
LATER = NOW + 60


def load(name):
    with open(os.path.join(FIX, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _rule(ruler, title):
    for groups in ruler.values():
        for grp in groups:
            for rule in grp["rules"]:
                if rule["grafana_alert"]["title"] == title:
                    return rule
    raise KeyError(title)


def saved(ruler, title=SNMP, by=None, at="2026-10-26T22:30:00Z", step=1):
    """*ruler* with *title* saved once more in Grafana: its version moved by *step*, its
    ``updated`` and ``updated_by`` set (Grafana's own shape). Returns the rule to edit."""
    rule = _rule(ruler, title)
    ga = rule["grafana_alert"]
    ga["version"] += step
    ga["updated"] = at
    ga["updated_by"] = by if by is not None else {"name": "admin", "uid": "afwpkish4ej28d"}
    return rule


def _threshold(rule):
    data = rule["grafana_alert"]["data"]
    return next(d for d in data if d["refId"] == "C")["model"]["conditions"][0]["evaluator"]


@pytest.fixture
def store(tmp_path, monkeypatch):
    """The record in this test's folder; no network registry asked."""
    monkeypatch.setattr(ARC, "_path", lambda: str(tmp_path / "alert_rule_changes.jsonl"))
    from modules import alert_history
    monkeypatch.setattr(alert_history, "_networks", lambda: {STORE: ["Default"]})
    ARC._LAST_SEEN.clear()
    return tmp_path


def _rows():
    return [r for r in ARC.read()["rows"] if r.get("kind") == "rule"]


def _record(ruler, now=NOW):
    return ARC.record(STORE, ARC.from_ruler(ruler), ["Default"], now=now)


# ---------------------------------------------------------------------------- the capture

class TestTheRulerAsCaptured:
    def test_every_rule_has_its_version_hash_who_and_when(self):
        defs = ARC.from_ruler(load("ruler"))
        assert len(defs) == 16
        for d in defs.values():
            assert isinstance(d["version"], int) and len(d["hash"]) == 16 and d["updated"]
        snmp = defs[SNMP_UID]
        assert (snmp["title"], snmp["version"], snmp["updated"]) == (SNMP, 11,
                                                                     "2026-09-28T19:38:21Z")
        assert snmp["who"]["words"] == "admin (in Grafana)" and snmp["devices"] == []

    def test_who_is_grafanas_words_for_a_login_a_service_account_and_provisioning(self):
        defs = {d["title"]: d for d in ARC.from_ruler(load("ruler")).values()}
        assert defs["Interface down"]["who"]["words"] == "nmas-automation (in Grafana)"
        hb = defs["NMAS heartbeat missing: r1"]
        assert hb["who"] == {"name": "", "uid": "service", "provenance": "file",
                             "words": "Grafana's file provisioning (as service)"}
        assert hb["devices"] == ["r1"], "a rule generated per device names it by label"

    def test_where_grafana_names_no_one_the_row_says_so(self):
        ga = copy.deepcopy(_rule(load("ruler"), SNMP)["grafana_alert"])
        del ga["updated_by"]
        assert ARC.who(ga)["words"] == ARC.NOT_SAID == "Grafana does not say"
        ga["updated_by"] = {"name": "", "uid": ""}
        assert ARC.who(ga)["words"] == "Grafana does not say"

    def test_the_reader_keeps_the_definitions_and_judges_them_complete(self):
        v = G.parse(load("ruler"), load("rules_view"), [], NOW)
        assert len(v["rule_definitions"]) == 16
        assert v["rule_definitions_complete"] is True and v["rule_definitions_why"] == ""

    def test_a_ruler_missing_a_rule_the_view_lists_is_partial(self):
        """Edit: the SNMP rule dropped from the ruler's answer (a folder the token cannot
        read), the rules view as captured."""
        ruler = load("ruler")
        for groups in ruler.values():
            for grp in groups:
                grp["rules"] = [r for r in grp["rules"]
                                if r["grafana_alert"]["uid"] != SNMP_UID]
        v = G.parse(ruler, load("rules_view"), [], NOW)
        assert v["rule_definitions_complete"] is False
        assert SNMP_UID in v["rule_definitions_why"]


class TestWhatIsHashed:
    @pytest.mark.parametrize("path, value", [
        (("grafana_alert", "version"), 99),
        (("grafana_alert", "updated"), "2026-10-27T00:00:00Z"),
        (("grafana_alert", "updated_by"), {"name": "someone", "uid": "x"}),
        (("grafana_alert", "provenance"), "api"),
        (("grafana_alert", "guid"), "00000000-0000-0000-0000-000000000000"),
        (("grafana_alert", "metadata", "editor_settings"), {"simplified": False}),
    ])
    def test_a_field_it_leaves_out_moves_no_hash(self, path, value):
        rule = _rule(load("ruler"), SNMP)
        before = ARC.definition_hash(rule)
        node = rule
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = value
        assert ARC.definition_hash(rule) == before
        assert path in ARC.NOT_HASHED

    @pytest.mark.parametrize("edit", [
        lambda r: _threshold(r).update(params=[2]),
        lambda r: r.update({"for": "5m"}),
        lambda r: r.update(labels={"severity": "critical"}),
        lambda r: r["annotations"].update(summary="changed"),
        lambda r: r["grafana_alert"].update(is_paused=True),
        lambda r: r["grafana_alert"]["data"][0]["model"].update(expr="up == 0"),
        lambda r: r["grafana_alert"].update(no_data_state="Alerting"),
        lambda r: r["grafana_alert"].update(title="Device unreachable"),
    ], ids=["threshold", "for", "labels", "annotations", "paused", "query", "no_data",
            "title"])
    def test_what_the_rule_evaluates_or_sends_moves_it(self, edit):
        rule = _rule(load("ruler"), SNMP)
        before = ARC.definition_hash(rule)
        edit(rule)
        assert ARC.definition_hash(rule) != before


# ---------------------------------------------------------------------------- the changes

class TestTheChanges:
    def test_the_first_read_is_a_baseline_per_rule_never_a_change(self):
        rows = ARC.changes([], STORE, ARC.from_ruler(load("ruler")), ["Default"], now=NOW)
        assert len(rows) == 16 and {r["change"] for r in rows} == {"baseline"}
        snmp = next(r for r in rows if r["uid"] == SNMP_UID)
        assert snmp["summary"] == "first seen at version 11" and snmp["version_from"] is None
        assert snmp["at"] == ARC.iso(NOW) and snmp["at_basis"] == ARC.AT_BASIS["seen"]

    def test_a_version_moving_with_a_new_threshold_is_one_change_said_in_words(self):
        """Edit: the SNMP rule saved by admin with its threshold 1 -> 2 (version 11 -> 12)."""
        base = ARC.changes([], STORE, ARC.from_ruler(load("ruler")), now=NOW)
        ruler = load("ruler")
        _threshold(saved(ruler)).update(params=[2])
        rows = ARC.changes(base, STORE, ARC.from_ruler(ruler), ["Default"], now=LATER)
        assert len(rows) == 1
        r = rows[0]
        assert (r["change"], r["uid"], r["title"]) == ("changed", SNMP_UID, SNMP)
        assert (r["version_from"], r["version"]) == (11, 12)
        assert r["hash_from"] and r["hash"] and r["hash_from"] != r["hash"]
        assert r["summary"] == "threshold C: below 1 → below 2"
        assert r["changed"] == ["expressions"]
        assert r["who"] == "admin (in Grafana)"
        assert r["updated_by"] == {"name": "admin", "uid": "afwpkish4ej28d"}
        assert r["at"] == "2026-10-26T22:30:00Z" and r["at_basis"] == ARC.AT_BASIS["updated"]
        assert r["seen_at"] == ARC.iso(LATER)
        kept = json.dumps(r["facets"])
        assert "cisco_8000v" not in kept and "not responding" not in kept, \
            "a digest, never the query's or the annotation's text"

    def test_the_pending_period_labels_annotations_and_paused_are_said(self):
        """Edit: the SNMP rule saved with `for` 2m -> 5m, a label added, its summary
        annotation reworded and the rule paused."""
        base = ARC.changes([], STORE, ARC.from_ruler(load("ruler")), now=NOW)
        ruler = load("ruler")
        rule = saved(ruler)
        rule["for"] = "5m"
        rule["labels"] = {"severity": "critical"}
        rule["annotations"]["summary"] = "{{ $labels.instance }} does not answer SNMP"
        rule["grafana_alert"]["is_paused"] = True
        r = ARC.changes(base, STORE, ARC.from_ruler(ruler), now=LATER)[0]
        assert r["summary"] == ("pending period 2m → 5m; labels: severity added (critical); "
                                "annotations: summary changed; paused")
        assert "does not answer" not in r["summary"], "an annotation's text is never copied"

    def test_a_query_change_is_named_without_its_text(self):
        """Edit: query A's PromQL changed."""
        base = ARC.changes([], STORE, ARC.from_ruler(load("ruler")), now=NOW)
        ruler = load("ruler")
        saved(ruler)["grafana_alert"]["data"][0]["model"]["expr"] = "up{job=\"x\"}"
        r = ARC.changes(base, STORE, ARC.from_ruler(ruler), now=LATER)[0]
        assert r["summary"] == "query A: its text changed" and r["changed"] == ["queries"]

    def test_a_save_with_no_edit_moves_the_version_and_says_nothing_changed(self):
        """Edit: the SNMP rule saved with only its editor layout changed."""
        base = ARC.changes([], STORE, ARC.from_ruler(load("ruler")), now=NOW)
        ruler = load("ruler")
        saved(ruler)["grafana_alert"]["metadata"]["editor_settings"] = {}
        r = ARC.changes(base, STORE, ARC.from_ruler(ruler), now=LATER)[0]
        assert r["change"] == "changed" and r["hash_from"] == r["hash"]
        assert r["summary"].startswith("saved with no change to what it evaluates or sends")

    def test_saves_mercury_did_not_see_are_counted(self):
        """Edit: the SNMP rule saved three times between two reads (version 11 -> 14)."""
        base = ARC.changes([], STORE, ARC.from_ruler(load("ruler")), now=NOW)
        ruler = load("ruler")
        _threshold(saved(ruler, step=3)).update(params=[2])
        r = ARC.changes(base, STORE, ARC.from_ruler(ruler), now=LATER)[0]
        assert r["summary"].endswith("(3 saves since the last read; Mercury saw the last)")

    def test_where_grafana_says_nobody_the_row_says_it_does_not_say(self):
        """Edit: the SNMP rule saved with no `updated_by` (an older Grafana's shape)."""
        base = ARC.changes([], STORE, ARC.from_ruler(load("ruler")), now=NOW)
        ruler = load("ruler")
        rule = saved(ruler)
        del rule["grafana_alert"]["updated_by"]
        rule["for"] = "5m"
        r = ARC.changes(base, STORE, ARC.from_ruler(ruler), now=LATER)[0]
        assert r["who"] == "Grafana does not say"

    def test_a_removed_rule_and_one_added_again(self):
        """Edit: the SNMP rule deleted from the ruler, then put back."""
        base = ARC.changes([], STORE, ARC.from_ruler(load("ruler")), now=NOW)
        ruler = load("ruler")
        for groups in ruler.values():
            for grp in groups:
                grp["rules"] = [r for r in grp["rules"]
                                if r["grafana_alert"]["uid"] != SNMP_UID]
        gone = ARC.changes(base, STORE, ARC.from_ruler(ruler), now=LATER)
        assert [(r["change"], r["uid"], r["version_from"]) for r in gone] == [
            ("removed", SNMP_UID, 11)]
        assert gone[0]["who"].startswith("Grafana does not say")
        assert gone[0]["at_basis"] == ARC.AT_BASIS["seen"]
        back = ARC.changes(base + gone, STORE, ARC.from_ruler(load("ruler")), now=LATER + 60)
        assert [(r["change"], r["version"]) for r in back] == [("added", 11)]

    def test_nothing_moved_is_nothing_recorded(self):
        base = ARC.changes([], STORE, ARC.from_ruler(load("ruler")), now=NOW)
        assert ARC.changes(base, STORE, ARC.from_ruler(load("ruler")), now=LATER) == []

    def test_each_configuration_is_judged_against_its_own_record(self):
        base = ARC.changes([], STORE, ARC.from_ruler(load("ruler")), now=NOW)
        other = ARC.changes(base, "grafana-alerts@lab2", ARC.from_ruler(load("ruler")), now=NOW)
        assert {r["change"] for r in other} == {"baseline"} and len(other) == 16


# ---------------------------------------------------------------------------- the store

def _cached(values):
    """`reader_job.read_cached` answering each store's stored value."""
    return lambda name: {"state": "ok", "doc": {"last_good": {"value": values[name]}}}


class TestTheRecord:
    def test_two_reads_record_a_baseline_then_the_change_once(self, store):
        assert _record(load("ruler"))["added"] == 16
        ruler = load("ruler")
        _threshold(saved(ruler)).update(params=[2])
        assert _record(ruler, LATER)["added"] == 1
        assert _record(ruler, LATER + 60)["added"] == 0, "the store is the state"
        rows = _rows()
        assert [r["change"] for r in rows].count("changed") == 1 and len(rows) == 17

    def test_a_secret_in_a_label_is_kept_masked_and_never_reads_as_moved(self, store,
                                                                          monkeypatch):
        """Edit: a label on the SNMP rule whose value is a held secret; then the rule saved
        with only its pending period changed. The kept row is masked, and the next change is
        compared masked against masked, so the label is not said to have moved."""
        from modules import redact
        planted = "Planted-Secret-0451"
        monkeypatch.setattr(redact, "known_secret_values", lambda: {planted: "Lab:planted"})
        ruler = load("ruler")
        _rule(ruler, SNMP)["labels"] = {"token": planted}
        _record(ruler)
        assert planted not in open(ARC._path(), encoding="utf-8").read()
        rule = saved(ruler)
        rule["for"] = "5m"
        _record(ruler, LATER)
        changed = [r for r in _rows() if r["change"] == "changed"]
        assert [r["summary"] for r in changed] == ["pending period 2m → 5m"]
        assert planted not in open(ARC._path(), encoding="utf-8").read()

    def test_an_unreadable_record_adds_nothing(self, store, monkeypatch):
        monkeypatch.setattr(ARC, "read", lambda: {"state": "unreadable", "rows": [],
                                                  "error": "PermissionError: denied"})
        got = _record(load("ruler"))
        assert got["ok"] is False and "cannot be read" in got["error"]

    def test_the_after_store_step_records_from_each_stored_value(self, store, monkeypatch):
        from modules import evidence_pack, reader_job
        monkeypatch.setattr(evidence_pack, "_alert_stores", lambda: [STORE])
        values = {STORE: G.parse(load("ruler"), load("rules_view"), [], NOW)}
        monkeypatch.setattr(reader_job, "read_cached", _cached(values))
        assert ARC.after_alerts_read(clock=lambda: NOW) is True
        ruler = load("ruler")
        _threshold(saved(ruler)).update(params=[2])
        values[STORE] = G.parse(ruler, load("rules_view"), [], LATER)
        assert ARC.after_alerts_read(clock=lambda: LATER) is True
        changed = [r for r in _rows() if r["change"] == "changed"]
        assert [(r["version_from"], r["version"], r["networks"]) for r in changed] == [
            (11, 12, ["Default"])]

    def test_unchanged_values_do_not_read_the_store(self, store, monkeypatch):
        from modules import evidence_pack, reader_job
        monkeypatch.setattr(evidence_pack, "_alert_stores", lambda: [STORE])
        values = {STORE: G.parse(load("ruler"), load("rules_view"), [], NOW)}
        monkeypatch.setattr(reader_job, "read_cached", _cached(values))
        reads, real = [], ARC.read
        monkeypatch.setattr(ARC, "read", lambda: reads.append(1) or real())
        assert ARC.after_alerts_read() is True
        assert ARC.after_alerts_read() is False and len(reads) == 1

    def test_a_partial_read_records_nothing_and_moves_no_state(self, store, monkeypatch):
        """Edit: after the baseline, a read whose ruler lacks the SNMP rule while the view
        lists it, with another rule's threshold changed: neither is recorded."""
        from modules import evidence_pack, reader_job
        monkeypatch.setattr(evidence_pack, "_alert_stores", lambda: [STORE])
        values = {STORE: G.parse(load("ruler"), load("rules_view"), [], NOW)}
        monkeypatch.setattr(reader_job, "read_cached", _cached(values))
        assert ARC.after_alerts_read(clock=lambda: NOW) is True
        ruler = load("ruler")
        _threshold(saved(ruler, title="IP SLA probe failing")).update(params=[5])
        for groups in ruler.values():
            for grp in groups:
                grp["rules"] = [r for r in grp["rules"]
                                if r["grafana_alert"]["uid"] != SNMP_UID]
        values[STORE] = G.parse(ruler, load("rules_view"), [], LATER)
        assert ARC.after_alerts_read(clock=lambda: LATER) is False
        assert {r["change"] for r in _rows()} == {"baseline"}

    def test_a_value_stored_before_this_release_is_not_read_as_no_rules(self, store,
                                                                        monkeypatch):
        """Edit: the stored value without the definitions an older release did not keep."""
        from modules import evidence_pack, reader_job
        monkeypatch.setattr(evidence_pack, "_alert_stores", lambda: [STORE])
        values = {STORE: G.parse(load("ruler"), load("rules_view"), [], NOW)}
        monkeypatch.setattr(reader_job, "read_cached", _cached(values))
        assert ARC.after_alerts_read(clock=lambda: NOW) is True
        for k in ("rule_definitions", "rule_definitions_complete", "rule_definitions_why"):
            values[STORE].pop(k)
        ARC._LAST_SEEN.clear()
        assert ARC.after_alerts_read(clock=lambda: LATER) is False
        assert "removed" not in {r["change"] for r in _rows()}

    def test_the_alerts_reader_runs_it_after_each_stored_read(self, monkeypatch):
        from modules import alert_history, evidence_pack
        ran = []
        monkeypatch.setattr(alert_history, "after_alerts_read", lambda: ran.append("h"))
        monkeypatch.setattr(ARC, "after_alerts_read", lambda: ran.append("r") or True)
        monkeypatch.setattr(evidence_pack, "after_alerts_read", lambda: ran.append("p"))
        assert G.READER.after_store is G._after_store
        assert G._after_store() is True and ran == ["h", "r", "p"]

    def test_it_is_a_records_store_kept_once_for_the_installation(self):
        from modules import records_db
        from modules import records_migrate as RM
        from modules.settings_schema import DEFAULTS
        assert ARC.STORE in records_db.STORES and not RM.store_of(ARC.STORE).per_network
        assert DEFAULTS["records_store_alert_rule_changes"] == "file"


# ---------------------------------------------------------------------------- History

def _ctx(device="", network="Default", limit=50):
    return {"ref": types.SimpleNamespace(name=network), "device": device, "limit": limit,
            "since": None, "until": None, "members": None, "call": ""}


def _changed_store():
    _record(load("ruler"))
    ruler = load("ruler")
    _threshold(saved(ruler)).update(params=[2])
    hb = saved(ruler, title="NMAS heartbeat missing: r1",
               by={"name": "", "uid": "service"}, at="2026-10-26T22:31:00Z")
    hb["labels"]["window_seconds"] = "800"
    _record(ruler, LATER)


class TestHistory:
    def test_a_change_is_one_line_with_versions_words_who_and_when(self, store):
        _changed_store()
        got = HS.alert_rule_changes(_ctx())
        assert got["errors"] == []
        line = next(e for e in got["events"] if SNMP in e["what"])
        assert line["what"] == ("Alert rule changed in Grafana: Device unreachable (SNMP), "
                                "version 11 → 12: threshold C: below 1 → below 2")
        assert line["kind"] == "alert_rule" and line["who"] == "admin (in Grafana)"
        assert line["at"] == "2026-10-26T22:30:00Z" and line["devices"] == []
        record = dict(line["record"])
        assert record["Saved in Grafana"] == "2026-10-26T22:30:00Z"
        assert record["Seen by Mercury"] == ARC.iso(LATER)
        assert record["Definition hash"].count("→") == 1
        assert record["Devices"].startswith("none by label")

    def test_the_first_read_is_one_row_not_sixteen(self, store):
        _changed_store()
        firsts = [e for e in HS.alert_rule_changes(_ctx())["events"]
                  if e["outcome"] == "baseline"]
        assert len(firsts) == 1
        assert firsts[0]["what"] == ("Alert rules first recorded from Grafana: 16 rules, "
                                     "each at its version")
        assert dict(firsts[0]["record"])[SNMP].startswith("version 11, hash ")

    def test_a_device_draws_only_the_rule_its_label_names(self, store):
        _changed_store()
        r1 = HS.alert_rule_changes(_ctx(device="r1"))["events"]
        changed = [e for e in r1 if e["outcome"] == "changed"]
        assert [e["devices"] for e in changed] == [["r1"]]
        assert changed[0]["what"].endswith("labels: window_seconds 750 → 800")
        assert changed[0]["who"] == "Grafana's file provisioning (as service)"
        assert not any(SNMP in e["what"] for e in r1)

    def test_another_networks_grafana_is_not_drawn(self, store):
        _changed_store()
        assert HS.alert_rule_changes(_ctx(network="Lab2"))["events"] == []

    def test_an_unreadable_record_is_an_error_never_no_changes(self, store, monkeypatch):
        monkeypatch.setattr(ARC, "read", lambda: {"state": "unreadable", "rows": [],
                                                  "error": "PermissionError: denied"})
        got = HS.alert_rule_changes(_ctx())
        assert got["events"] == [] and "could not be read" in got["errors"][0]

    def test_the_kind_filter_offers_it_and_the_timeline_keeps_it(self, store, monkeypatch):
        _changed_store()
        assert HS.KIND_FILTERS["alert_rules"] == ("alert_rule",)
        assert HS.SOURCES["alert_rule_changes"] is HS.alert_rule_changes
        h = HS.timeline(types.SimpleNamespace(name="Default"), kinds=["alert_rules"],
                        members=[])
        assert h["errors"] == []
        assert {e["kind"] for e in h["events"]} == {"alert_rule"} and len(h["events"]) == 3
