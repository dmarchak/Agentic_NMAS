"""C2970: a lost telemetry stream is a WARNING while its device answers, and critical only by
folding (the operator, 2026-11-10: "Severity follows impact on service, not 'something
broke'… Fix it in the provisioned Grafana alert rule (its severity label), not by overriding
it in Mercury's display"; 2026-11-11: "telemetry loss is a WARNING while the device answers
(escalate only by folding)"). scripts/nmas-telemetry-rules labels each rule `severity:
warning`; `attention.grafana_source` reads every rule's label (`rule_level`), and a lost
stream's row is critical only inside its device's not-answering row; lost streams on several
devices are one row about the collector, a Warning like its rows (the operator, 2026-11-11:
critical is "an outage (something down or unreachable for users)", "so r7 isn't "critical" on
screen and a monitoring gap never pages anyone") (`_stream_rows`). No device, no network.

On real captures, each edit said where it is made:
- **the alerts:** tests/test_seen_before.py's (the rules view of 2026-10-26, which holds the
  routers' real lost-stream instances, each set firing at the time a case needs; the captured
  ruler with the telemetry generator's own rule for each, so the label under test is the one
  the generator writes), parsed by the real reader. A case about another label edits that one
  label on the generator's rule; a case about a fleet of two streaming devices drops the
  other devices' lost-stream rules from the view;
- **whether a device answers:** the reachability reader's own `read`, run cycle by cycle
  with each device's probe answered or missed, so every field is the reader's.
"""
import copy
import functools
import time

import pytest

from modules import attention as A
from modules import attention_record
from modules import reader_job as R
from modules.heal import seen_before as SB
from modules.readers import grafana_alerts as G
from modules.readers import reachability as RC
from tests import test_seen_before as T
from tests.test_seen_before import world  # noqa: F401  (the three networks' store)

ADDRESS = {d["hostname"]: d["ip"] for d in T.DEVICES}
ROW = "r2: 2 telemetry streams lost (101, 102)"


def probed(down=(), missed=(), absent=(), age=0, hosts=None, state="ok") -> dict:
    """The reachability reader's stored value as `reader_job.read_cached` answers it, read
    *age* seconds ago: three cycles of the reader's own `read`, each device's probe answered
    but for *down* (missed every cycle: counted as not answering at the third) and *missed*
    (missed on the last cycle only)."""
    targets = [(ADDRESS[h], h, T.NET) for h in (hosts or sorted(ADDRESS)) if h not in absent]
    by_ip = {ip: h for ip, h, _ in targets}
    status = dict(RC.STATUS)
    previous, value = {}, None
    try:
        for cycle in range(3):
            def probe(ip, cycle=cycle):
                host = by_ip[ip]
                if host in down or (host in missed and cycle == 2):
                    return False, RC.CLAIM_NONE
                return True, "answered ICMP"
            value = RC.read(probe, targets, previous, clock=lambda: time.time() - age)
            previous = value["devices"]
    finally:
        RC.STATUS.clear()
        RC.STATUS.update(status)
    return {"state": state, "why": "" if state == "ok" else "the store's file is torn",
            "doc": {"stale_after_seconds": R.page_promise(RC.READER),
                    "last_good": {"value_at": R._iso(time.time() - age), "value": value}}}


def ruler(devices, label=...):
    """The captured ruler with the generator's rules for each of *devices*; *label* edits the
    one label under test on them (None removes it: a rule installed before C2970)."""
    out = T.ruler_for(devices[0])
    group = out["NMAS"][-1]
    for d in devices[1:]:
        group["rules"] += T.ruler_for(d)["NMAS"][-1]["rules"]
    if label is not ...:
        for r in group["rules"]:
            if label is None:
                r["labels"].pop("severity", None)
            else:
                r["labels"]["severity"] = label
    return out


def lost(devices=("r2",), label=..., at=None, only=None) -> dict:
    """The reader's value with each of *devices*' two real lost-stream instances firing, begun
    at *at* (``{device: iso}``, the worked example's second loss otherwise). *only* keeps the
    lost-stream rules of those devices alone in the view (a fleet where no other streams)."""
    view = T.history_load("rules_view")
    for d in devices:
        for sub in T.SUBS:
            inst = T.GR.rule(view, f"NMAS telemetry stream lost: {d} subscription {sub}")
            inst["alerts"][0]["state"] = T.FIRING
            inst["alerts"][0]["activeAt"] = (at or {}).get(d, T.LOST_2)
    if only is not None:
        for grp in view["data"]["groups"]:
            kept = [r for r in grp["rules"] if "telemetry stream lost" not in r["name"]
                    or any(f": {d} subscription " in r["name"] for d in only)]
            if len(kept) != len(grp["rules"]):
                grp["rules"] = kept
                grp.pop("totals")                     # the group's count of the rules dropped
    return G.parse(ruler(list(devices), label), view, [], T.NOW)


def source(v, reach=None, nets=None):
    v["streams"] = SB.context(v, T.STORE, sources=T.Src(nets=nets))
    cached = {"state": "ok", "doc": {"stale_after_seconds": None, "last_good": {
        "value_at": T.iso(T.NOW), "value": v}}}
    got = A.grafana_source(cached, reachability=probed() if reach is None else reach)
    # The capture's groups were last evaluated on 2026-10-26, long before the read time these
    # cases need, so each is also a "stopped evaluating" row: another subject, left out.
    got["rows"] = [r for r in got["rows"] if r["kind"] != "stalled"]
    return got


def rows(v, reach=None):
    return source(v, reach)["rows"]


def one(got: list) -> dict:
    """The only row of *got*: another count is said with what each is."""
    assert len(got) == 1, [(r.get("kind"), r.get("what"), r.get("level")) for r in got]
    return got[0]


def page(v, reach, monkeypatch):
    """Needs attention itself, from the Grafana source and the reachability source reading
    the same stored reachability value."""
    monkeypatch.setattr(A, "SOURCES", (lambda: source(v, reach),
                                       functools.partial(A.reachability_source, reach)))
    return A.needs_attention()


class TestTheRulesLabel:
    def test_the_generator_labels_every_lost_stream_rule_a_warning(self):
        from modules import telemetry_rules
        gen = telemetry_rules._script()
        doc = gen.build({"r2": ["101", "102"], "r7": ["101"]}, "prom-uid", 300)
        labels = [r["labels"] for g in doc["groups"] for r in g["rules"]]
        assert len(labels) == 3 and {l.get("severity") for l in labels} == {"warning"}
        assert gen.render(doc).count("severity: warning") == 3

    def test_the_reader_keeps_the_rules_own_label(self):
        v = lost()
        kept = {r["title"]: r["labels"].get("severity") for r in v["rules"]
                if "telemetry stream lost: r2 " in r["title"]}
        assert kept == {f"NMAS telemetry stream lost: r2 subscription {s}": "warning"
                        for s in T.SUBS}

    @pytest.mark.parametrize("labels,level,why", [
        ({"severity": "critical"}, "danger", "its rule is labelled severity critical in Grafana"),
        ({"severity": "warning"}, "warning", "its rule is labelled severity warning in Grafana"),
        ({"severity": "info"}, "", "its rule is labelled severity info in Grafana"),
        ({}, "danger", "no severity label on its rule in Grafana, so critical"),
        (None, "danger", "no severity label on its rule in Grafana, so critical"),
        ({"severity": "Warning"}, "danger",
         "its rule's severity label in Grafana is 'Warning', which is not critical, warning "
         "or info, so critical"),
    ])
    def test_each_value_has_its_level_and_an_unknown_one_is_said(self, labels, level, why):
        assert A.rule_level(labels) == (level, why)


class TestTheLevelIsTheRules:
    def test_a_labelled_lost_stream_is_a_warning_while_its_device_answers(self, world):  # noqa: F811
        row = one(rows(lost()))
        assert (row["what"], row["level"]) == (ROW, "warning")
        assert row["fix"]["answers"] == {
            "state": "answers",
            "words": "r2 answers Mercury's reachability probe (ICMP, then TCP 22): it is "
                     "reachable, and its telemetry is not arriving."}
        assert row["operands"]["severity"] == (
            "its rule is labelled severity warning in Grafana: NMAS telemetry stream lost: "
            "r2 subscription 101, NMAS telemetry stream lost: r2 subscription 102")
        assert row["operands"]["device_answers"].startswith("the reachability reading of ")
        assert row["operands"]["device_answers"].endswith(
            f": r2 ({ADDRESS['r2']}) answering, 0 consecutive miss(es), not answering at 3")
        # It still names its action and how it clears.
        assert row["action"]["open"] == "resubscribe" and row["action"]["subs"] == ["101", "102"]
        assert row["clears"]["ways"] == ["resolves"] and row["attach_to"] is None

    def test_the_same_rule_without_the_label_is_critical_as_before(self, world):  # noqa: F811
        """A host whose rules were installed before the label: nothing changes level."""
        row = one(rows(lost(label=None)))
        assert (row["what"], row["level"]) == (ROW, "danger")
        assert row["operands"]["severity"].startswith(
            "no severity label on its rule in Grafana, so critical: ")
        assert row["action"]["open"] == "resubscribe"

    def test_an_unknown_value_is_critical_and_the_record_names_it(self, world):  # noqa: F811
        row = one(rows(lost(label="page")))
        assert row["level"] == "danger"
        assert row["operands"]["severity"].startswith(
            "its rule's severity label in Grafana is 'page', which is not critical, warning "
            "or info, so critical")

    def test_critical_is_critical(self, world):  # noqa: F811
        row = one(rows(lost(label="critical")))
        assert row["level"] == "danger"

    def test_info_is_a_record_under_what_was_checked_never_a_row(self, world):  # noqa: F811
        got = source(lost(label="info"))
        assert got["rows"] == []
        assert ("2 alert(s) whose rule is labelled severity info, a record and not raised: "
                "NMAS telemetry stream lost: r2 subscription 101, NMAS telemetry stream "
                "lost: r2 subscription 102") in got["checked"]

    def test_another_rules_alert_keeps_its_level(self, world):  # noqa: F811
        """No other rule carries a label, so no other row moves: the captured hand-built
        rule, firing (tests/test_grafana_reader.py's edit), is critical as before."""
        view = T.history_load("rules_view")
        inst = T.GR.rule(view, "Device unreachable (SNMP)")["alerts"][0]
        inst["state"], inst["activeAt"] = "Alerting", T.LOST_2
        v = G.parse(T.GR.load("ruler"), view, [], T.NOW)
        row = one([r for r in rows(v) if r["kind"] in ("incident", "series")])
        assert row["level"] == "danger"
        assert row["operands"]["severity"] == "no severity label on its rule in Grafana, so critical"

    def test_the_worst_member_decides_and_no_data_decides_nothing(self):
        warn = ("warning", "w")
        crit = ("danger", "c")
        cond, nodata = {"kind": "condition", "rule": "a"}, {"kind": "no_data", "rule": "b"}
        assert A.group_level([cond, cond], [warn, crit]) == ("danger", "w: a; c: a")
        assert A.group_level([cond, nodata], [warn, crit]) == ("warning", "w")
        assert A.group_level([nodata], [crit]) == ("unknown", "")


class TestWhetherTheDeviceAnswers:
    """The reading is the reachability reader's stored value; one that cannot say is said."""

    def test_a_device_that_missed_its_last_probe_is_said(self, world):  # noqa: F811
        row = one(rows(lost(), probed(missed=("r2",))))
        assert row["level"] == "warning" and row["what"] == ROW
        assert row["fix"]["answers"] == {
            "state": "missed",
            "words": "r2 missed Mercury's last 1 reachability probe; it is counted as not "
                     "answering at 3. If it stops answering, this becomes part of its "
                     "not-answering item."}

    @pytest.mark.parametrize("reach,why", [
        (dict(state="unreadable"),
         "Mercury's reachability reading could not be read (the store's file is torn)"),
        (dict(age=151), "Mercury's reachability reading is 2 min old, past its promise of 2 min"),
        (dict(absent=("r2",)), "Mercury's reachability reading holds no device named r2"),
    ])
    def test_a_reading_that_cannot_say_marks_the_warning(self, world, reach, why):  # noqa: F811
        row = one(rows(lost(), probed(**reach)))
        assert row["level"] == "warning"
        assert row["what"] == ROW + " (not known whether r2 answers)"
        assert row["fix"]["answers"] == {
            "state": "unknown",
            "words": f"Not known whether r2 answers: {why}. If r2 is down, this item does "
                     "not say so."}
        assert row["attach_to"] is None

    def test_a_reading_inside_its_promise_is_taken(self, world):  # noqa: F811
        assert R.page_promise(RC.READER) == 150
        row = one(rows(lost(), probed(age=140)))
        assert row["fix"]["answers"]["state"] == "answers" and row["what"] == ROW

    def test_two_networks_devices_of_one_name_that_disagree_decide_nothing(self):
        got = probed()
        devices = got["doc"]["last_good"]["value"]["devices"]
        other = dict(devices[ADDRESS["r2"]], address="2001:db8::12", list="Branch",
                     answering=False, consecutive_misses=3)
        devices["2001:db8::12"] = other
        ans = A.device_answers("r2", got, time.time())
        assert ans["state"] == "unknown" and (
            "2 devices named r2 are probed, in different networks, and not all of them "
            "answer") in ans["words"]

    def test_an_unlabelled_rows_title_is_left_as_it_was(self, world):  # noqa: F811
        row = one(rows(lost(label=None), probed(absent=("r2",))))
        assert row["what"] == ROW and row["fix"]["answers"]["state"] == "unknown"


class TestFoldedIntoTheDeviceDownRow:
    def test_a_device_not_answering_takes_its_lost_streams_into_its_row(self, world,  # noqa: F811
                                                                         monkeypatch):
        reach = probed(down=("r2",))
        got = page(lost(), reach, monkeypatch)
        row = one(got["rows"])
        assert (row["id"], row["level"]) == ("reachability:not-answering", "danger")
        assert row["what"] == "r2 is not answering"
        also = one(row["attached"])
        assert also["what"] == ROW and also["kind"] == "incident"
        # The device-down row keeps its own action: nothing is re-subscribed on a device
        # that does not answer.
        assert row["action"]["label"].startswith("Check the path from Mercury first")
        assert got["badge"] == dict(got["badge"], n=1, level="danger")
        said = T.text_of(T.drawn(got["rows"]))
        assert f"Also: {ROW} (grafana)" in said and "Re-subscribe" not in said

    def test_the_fold_is_the_readings_not_the_labels(self, world, monkeypatch):  # noqa: F811
        got = page(lost(label=None), probed(down=("r2",)), monkeypatch)
        assert [r["id"] for r in got["rows"]] == ["reachability:not-answering"]

    def test_another_device_down_folds_nothing_of_this_one(self, world, monkeypatch):  # noqa: F811
        got = page(lost(), probed(down=("r7",)), monkeypatch)
        assert [(r["what"], r["level"]) for r in got["rows"]] == [
            ("r7 is not answering", "danger"), (ROW, "warning")]
        assert got["rows"][0]["attached"] == []

    def test_the_row_stands_alone_and_says_so_when_no_device_down_row_is_drawn(self, world):  # noqa: F811
        row = one(rows(lost(), probed(down=("r2",))))
        assert row["attach_to"] == A.NOT_ANSWERING_ROW
        assert row["fix"]["answers"]["words"] == (
            "r2 is not answering Mercury's reachability probe (3 consecutive misses), so "
            "its telemetry is lost with it.")


class TestTheCollectorRow:
    THREE = ("r1", "r2", "r7")

    def test_several_devices_within_the_window_are_one_warning_row(self, world):  # noqa: F811
        assert (A.COLLECTOR_DEVICES, A.COLLECTOR_WINDOW_SECONDS) == (3, 150)
        at = {"r1": "2026-11-08T21:30:50Z", "r2": "2026-11-08T21:31:50Z",
              "r7": "2026-11-08T21:33:20Z"}                       # 150 s, first to last
        row = one(rows(lost(self.THREE, at=at)))
        assert (row["kind"], row["level"]) == ("collector", "warning")
        assert row["what"] == "3 devices stopped streaming telemetry together (r1, r2, r7)"
        assert "critical" not in (row["what"] + row["cause"] + row["action"]["label"]).lower()
        assert row["cause"] == (
            "lost-stream alerts began on 3 devices within 150 s of each other, and none of "
            "them is counted as not answering. What they share is the collector (its "
            "listener and the sessions it holds), the path to it, its scrape, or one change "
            "made to all of them; the alerts cannot say which")
        assert row["action"]["label"].startswith("Check the collector first: whether it is "
                                                 "listening and holds these devices' sessions")
        assert row["devices"] == list(self.THREE) and row["since"] == at["r1"]
        assert row["operands"]["rule"] == "3 or more devices within the window"
        assert row["clears"]["ways"] == ["resolves"]
        # Each device's own row under it, as itself, still offering its action.
        assert [(f["what"], f["level"], f["action"]["open"], f["action"]["device"])
                for f in row["folded"]] == [
            (f"{d}: 2 telemetry streams lost (101, 102)", "warning", "resubscribe", d)
            for d in self.THREE]

    def test_one_device_fewer_is_a_warning_each(self, world):  # noqa: F811
        got = rows(lost(("r2", "r7")))
        assert sorted((r["what"], r["level"], r["kind"]) for r in got) == [
            ("r2: 2 telemetry streams lost (101, 102)", "warning", "incident"),
            ("r7: 2 telemetry streams lost (101, 102)", "warning", "incident")]
        assert all(r["action"]["open"] == "resubscribe" for r in got)

    def test_a_device_outside_the_window_is_not_counted(self, world):  # noqa: F811
        at = {"r1": "2026-11-08T21:30:50Z", "r2": "2026-11-08T21:31:50Z",
              "r7": "2026-11-08T21:33:21Z"}                       # 151 s after the first
        got = rows(lost(self.THREE, at=at))
        assert sorted(r["kind"] for r in got) == ["incident"] * 3
        assert {r["level"] for r in got} == {"warning"}

    def test_a_device_not_answering_is_its_own_rows_and_not_the_collectors(self, world):  # noqa: F811
        got = rows(lost(self.THREE), probed(down=("r7",)))
        assert sorted((r["kind"], r["devices"][0], r["attach_to"]) for r in got) == [
            ("incident", "r1", None), ("incident", "r2", None),
            ("incident", "r7", A.NOT_ANSWERING_ROW)]

    def test_every_streaming_device_counts_when_there_are_two(self, world):  # noqa: F811
        row = one(rows(lost(("r2", "r7"), only=("r2", "r7"))))
        assert row["kind"] == "collector" and row["level"] == "warning"
        assert row["what"] == "2 devices stopped streaming telemetry together (r2, r7)"
        assert row["operands"]["rule"] == (
            "every device Grafana holds a lost-stream rule for (2) within the window")
        # One device of one is never the collector's row: nothing tells it from the device.
        alone = one(rows(lost(("r2",), only=("r2",))))
        assert alone["kind"] == "incident" and alone["level"] == "warning"

    def test_unlabelled_rules_fold_the_same_way(self, world):  # noqa: F811
        row = one(rows(lost(self.THREE, label=None)))
        # Rules installed before the label keep today's level, the folded rows' and the
        # collector row's alike: nothing changes level until the host step runs.
        assert row["kind"] == "collector" and {f["level"] for f in row["folded"]} == {"danger"}
        assert row["level"] == "danger"

    def test_the_page_counts_one_item_and_draws_each_device_under_it(self, world,  # noqa: F811
                                                                     monkeypatch):
        reach = probed()
        got = page(lost(self.THREE), reach, monkeypatch)
        row = one(got["rows"])
        assert got["badge"]["n"] == 1 and got["badge"]["level"] == "warning"
        # Each folded row is named with its networks and its reading's age, as a row is (the
        # store's three networks each hold the routers).
        assert all(set(f["networks"]) == {f["devices"][0]} and f["networks"][f["devices"][0]]
                   and f["read_at"] == row["read_at"] for f in row["folded"])
        for f in row["folded"]:
            f["networks"] = {f["devices"][0]: [T.NET]}        # one network, so it is offered
        html = T.drawn(got["rows"], nets={d: [T.NET] for d in self.THREE})
        said = T.text_of(html)
        assert "1 item · 1 warning" in said and "Warning · 1" in said
        assert "Critical ·" not in said and "critical" not in said.lower().split("what was checked")[0]
        assert "3 devices under this item" in said
        for d, f in zip(self.THREE, row["folded"]):
            assert f'data-attention-row="{f["id"]}"' in html
            assert f"{d}: 2 telemetry streams lost (101, 102)" in said
            assert f"Re-subscribe {d}'s telemetry (101, 102)…" in said
            assert f'id="resub-{d}" hx-get="/v2/device/{d}/resubscribe?list={T.NET}' in html
        # Closed until opened: a folded row is a details element with no `open`.
        import re
        # (The collector's own item is a Warning too: its device rows are the incident ones.)
        nested = re.findall(r'<details class="att att-warning" data-attention-row="[^"]*:incident:'
                            r'[^>]*>', html)
        assert len(nested) == 3 and not any(" open" in n for n in nested)

    def test_the_record_holds_each_folded_row_as_present(self, world):  # noqa: F811
        row = one(rows(lost(self.THREE)))
        present = attention_record._present({"rows": [row]})
        assert set(present) == {row["id"]} | {f["id"] for f in row["folded"]}
        assert all(present[f["id"]]["level"] == "warning" for f in row["folded"])


class TestTheRowDrawn:
    def test_what_mercury_cannot_see_is_one_line_under_the_lead(self, world):  # noqa: F811
        row = one(rows(lost()))
        unseen = ("Until it is back, Mercury cannot see what this stream carries: r2's "
                  "telemetry-only panels on its Monitoring tab, its Telemetry column on "
                  "Monitoring › Coverage and its Telemetry rates in History. Self-healing "
                  "reads the stream only to say it is back (Re-subscribe's Verify and the "
                  "diagnosis).")
        assert row["fix"]["unseen"] == unseen
        html = T.drawn([row])
        said = T.text_of(html)
        answers = row["fix"]["answers"]["words"]
        order = [said.index(x) for x in (T.LEAD, answers, unseen, T.NEEDS, "What to do")]
        assert order == sorted(order), order
        assert '<p class="fix-answers">' in html and '<p class="fix-unseen small muted">' in html
        # The level's own badge and section: the warning token's class, never the critical one.
        assert '<details class="att att-warning"' in html and "att-danger" not in html
        assert '<span class="att-level">Warning</span>' in html
        assert "1 item · 1 warning" in said and "critical" not in said.split("What to do")[0]

    def test_a_reading_that_cannot_say_is_drawn_as_a_warning_line(self, world):  # noqa: F811
        row = one(rows(lost(), probed(absent=("r2",))))
        html = T.drawn([row])
        assert '<p class="fix-answers warn-text">Not known whether r2 answers: ' in html
        assert 'title="r2: 2 telemetry streams lost (101, 102) (not known whether r2 answers)"' \
            in html

    def test_every_field_the_row_carries_is_drawn(self, world):  # noqa: F811
        import app as nmas
        from tests import v2_context as V
        row = one(rows(lost(TestTheCollectorRow.THREE)))
        reads = V.template_reads(nmas.app.jinja_env, "v2/_attention.html")
        carried, undrawn = V.carried({"fix": row["folded"][0]["fix"], "folded": []}, reads)
        assert not undrawn, sorted(undrawn)
        assert {"answers", "unseen", "folded"} <= carried


class TestOrderAndCounts:
    def test_critical_first_and_each_level_counted(self, world, monkeypatch):  # noqa: F811
        """r7's rules as installed before the label (critical), r2's labelled (warning)."""
        view = T.history_load("rules_view")
        for d, at in (("r2", T.LOST_2), ("r7", "2026-11-08T23:30:50Z")):
            for sub in T.SUBS:
                inst = T.GR.rule(view, f"NMAS telemetry stream lost: {d} subscription {sub}")
                inst["alerts"][0]["state"], inst["alerts"][0]["activeAt"] = T.FIRING, at
        both = ruler(["r2", "r7"])
        for r in both["NMAS"][-1]["rules"]:
            if r["labels"]["device"] == "r7":
                r["labels"].pop("severity", None)
        v = G.parse(both, view, [], T.NOW)
        got = page(v, probed(), monkeypatch)
        assert [(r["devices"], r["level"]) for r in got["rows"]] == [
            (["r7"], "danger"), (["r2"], "warning")]
        assert got["badge"]["n"] == 2 and got["badge"]["level"] == "danger"
        said = T.text_of(T.drawn(got["rows"], nets={"r2": [T.NET], "r7": [T.NET]}))
        assert "2 items · 1 critical · 1 warning" in said
        assert said.index("Critical · 1") < said.index("Warning · 1")

    def test_a_warning_alone_makes_the_count_a_warning(self, world, monkeypatch):  # noqa: F811
        got = page(lost(), probed(), monkeypatch)
        assert got["badge"]["n"] == 1 and got["badge"]["level"] == "warning"

    def test_the_needs_you_line_stays_true_at_warning(self, world):  # noqa: F811
        row = one(rows(lost()))
        assert row["level"] == "warning"
        assert T.NEEDS in T.text_of(T.drawn([row]))

    def test_the_collector_kind_says_how_it_clears(self):
        assert A.CLEARS[("grafana", "collector")][0] == ("resolves",)
        assert copy.deepcopy(A.ROW_KINDS[("grafana", "collector")])[1].startswith(
            "check the collector")


def test_a_folded_rows_action_opens_it_in_a_real_browser(world, monkeypatch):  # noqa: F811
    """The collector's row in the real page: one item counted; each device's row inside it,
    closed; a folded row's own Re-subscribe… opens that row (and the row holding it) to its
    card's slot, as it does on a row standing alone (nmas_v2.js `citeClicked`)."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as nmas
    three = TestTheCollectorRow.THREE
    v, reach = lost(three), probed()
    monkeypatch.setattr(A, "SOURCES", (lambda: source(copy.deepcopy(v), reach),))
    # One network holds each router here, so its Re-subscribe is offered.
    monkeypatch.setattr(A, "_device_networks", lambda: {d: [T.NET] for d in three})
    A._shared.clear()
    top = "document.querySelector('details.att')"
    kids = "document.querySelectorAll('details.att details.att')"
    with browser.Served(nmas.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/"))
            b.wait_for(f"return !!window.htmx && !!{top}", 15)
            summary = b.js("return document.querySelector('.att-summary').textContent")
            before = b.js(f"return Array.from({kids}).map(function (d) {{"
                          " return [d.getAttribute('data-attention-row'), d.open]; })")
            b.click("details.att > summary.att-line")
            b.wait_for(f"return {top}.open", 10)
            b.click("details.att details.att a.att-jump")
            b.wait_for(f"return {kids}[0].open", 10)
            after = b.js(f"return Array.from({kids}).map(function (d) {{ return d.open; }})")
            # Opening it asks for its card (`toggle once from:closest details.att`): the slot's
            # placeholder is replaced in the row pressed, and stays in the rows left closed.
            waiting = "Drawn when this item is open: what Re-subscribe will send to "
            b.wait_for(f"return {kids}[0].textContent.indexOf('{waiting}') < 0", 10)
            slots = b.js(f"return Array.from({kids}).map(function (d) {{"
                         f" return d.textContent.indexOf('{waiting}') >= 0; }})")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
            A._shared.clear()
    assert "1 item" in summary and "1 warning" in summary and "critical" not in summary
    assert [open_ for _id, open_ in before] == [False, False, False]
    assert [i.split(":")[1] for i, _ in before] == ["incident"] * 3
    assert after == [True, False, False], "only the row whose action was pressed opened"
    assert slots == [False, True, True]
