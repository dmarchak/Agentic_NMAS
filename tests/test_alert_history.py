"""The alert history (modules/alert_history.py; the operator's order of 2026-10-26): every
transition of every Grafana alert, timed by Grafana, recorded once by the alerts reader and by
`scripts/nmas-alert-backfill`, grouped into episodes for Monitoring › Alerts › History, and moved
to the data lake past its network's retention.

The captures (tests/fixtures/grafana/alert_history/, read-only on the host 2026-10-26 19:22
UTC, `alerthist_probe3.py` and `alerthist_probe4.py`, each a GET of Grafana): the 72 hours'
alert annotations and the rules view at the same moment (`annotations_72h.json`,
`rules_view.json`), and two hours of 21 Oct, 01:00 to 03:00 UTC, of a day with firing alerts
(`annotations_firing.json`, 93 rows, unchanged). The one measured agreement the dedupe rests on
is in them: r1's `IP SLA probe failing` (rttMonCtrlAdminIndex 2) moved Pending to
`Normal (NoData)` at 17:04:50, annotation 17894, and the rules view's instance reads
`Normal (NoData)` with `activeAt` 2026-10-26T17:04:50Z. Every other case is a minimal edit of a
captured row, said where it is made.
"""

import copy
import importlib.machinery
import importlib.util
import json
import os

import pytest

from modules import alert_history as H
from modules.readers import grafana_alerts as G

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "grafana",
                   "alert_history")
STORE = "grafana-alerts"
#: A read 26 minutes after r1's resolve, inside the hour the reader keeps a normal instance.
READ_AT = H.epoch("2026-10-26T17:30:00Z")


def load(name):
    with open(os.path.join(FIX, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def ann(rows, ident):
    return next(r for r in rows if r["id"] == ident)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """The history in this test's folder; no network registry asked."""
    monkeypatch.setattr(H, "_path", lambda: str(tmp_path / "alert_history.jsonl"))
    monkeypatch.setattr(H, "_networks", lambda: {STORE: ["Default"]})
    H._LAST_SEEN.clear()
    return tmp_path


def _rows():
    return H.read()["rows"]


def _backfill(rows):
    return H.record([r for r in (H.from_annotation(a, STORE, ["Default"]) for a in rows) if r])


def _view_value(read_at=READ_AT):
    return G.parse({}, load("rules_view"), [], read_at)


# ---------------------------------------------------------------------------- the sources

class TestTheStateHistoryAsCaptured:
    def test_each_annotation_is_one_transition_timed_by_grafana(self):
        rows = load("annotations_firing")
        got = [H.from_annotation(a, STORE) for a in rows]
        assert len(got) == 93 and all(got), "no row in the slice is normal to normal"
        a = ann(rows, rows[-1]["id"])
        r = H.from_annotation(a, STORE)
        assert r["at"] == H.iso(a["time"] // 1000) and r["at_basis"] == H.AT_BASIS["backfill"]
        assert r["grafana_id"] == a["id"] and r["source"] == "backfill"
        assert r["state"] == a["newState"] and r["prev_state"] == a["prevState"]

    def test_labels_come_from_the_tags_and_name_the_device(self):
        a = ann(load("annotations_72h"), 17894)
        r = H.from_annotation(a, STORE)
        assert r["labels"] == {"alertname": "IP SLA probe failing", "device": "r1",
                               "grafana_folder": "RCN Lab", "instance": "10.255.1.11",
                               "job": "cisco_ipsla", "role": "router",
                               "rttMonCtrlAdminIndex": "2"}
        assert (r["device"], r["device_from"], r["to"]) == ("r1", "label", "normal")

    def test_a_value_with_a_colon_is_read_whole_from_the_text(self):
        """Grafana's tag for the heartbeat rule's alertname reads `NMAS heartbeat missing_ r4`
        (a value's colon written `_`); the text's braces hold it whole, as the rules view
        names it, so the reader's row and this one share a key."""
        a = ann(load("annotations_firing"), 15081)
        assert "alertname:NMAS heartbeat missing_ r4" in a["tags"]
        labels = H.annotation_labels(a)
        assert labels["alertname"] == "NMAS heartbeat missing: r4"
        assert labels["window_seconds"] == "749" and labels["device"] == "r4"

    def test_an_ipv4_and_an_ipv6_polled_address_stay_whole(self):
        """Edit: the real Device unreachable row's `device` label dropped, its instance an
        IPv4 address with a port, then an IPv6 one, the tag mangled as Grafana mangles a
        colon and the text whole: the address is the text's."""
        base = copy.deepcopy(ann(load("annotations_72h"), 17895))
        base["tags"] = [t for t in base["tags"] if not t.startswith("device:")]
        base["text"] = base["text"].replace("device=s3, ", "")
        for addr in ("192.0.2.23:161", "[2001:db8::23]:161"):
            a = copy.deepcopy(base)
            a["tags"] = [t if not t.startswith("instance:") else
                         "instance:" + addr.replace(":", "_") for t in a["tags"]]
            a["text"] = a["text"].replace("instance=10.255.1.23", f"instance={addr}")
            r = H.from_annotation(a, STORE)
            assert (r["address"], r["device_from"], r["device"]) == (addr, "address", "")

    def test_braces_that_disagree_with_the_tags_leave_the_tags(self):
        """Edit: a label dropped from the text only."""
        a = copy.deepcopy(ann(load("annotations_72h"), 17896))
        a["text"] = a["text"].replace("role=switch, ", "")
        assert H.annotation_labels(a)["role"] == "switch"

    def test_a_move_between_two_normal_states_is_not_a_transition(self):
        """Edit: a real resolve row's states set to Normal, then Normal (Updated)."""
        a = copy.deepcopy(ann(load("annotations_72h"), 17896))
        a["prevState"], a["newState"] = "Normal", "Normal (Updated)"
        assert H.from_annotation(a, STORE) is None

    def test_with_no_tags_the_braces_alone_are_read(self):
        a = copy.deepcopy(ann(load("annotations_72h"), 17896))
        tags = a.pop("tags")
        assert H.annotation_labels(a) == dict(t.split(":", 1) for t in tags)


class TestTimesAreGrafanas:
    def test_the_reader_times_a_transition_by_active_at_never_the_devices_clock(self):
        """Edit: the captured `Critical syslog received` instance set Alerting at 03:14:50,
        its labels carrying the device's own clock two hours slow (as a vIOS's runs) and its
        value the device's timestamp: the row is at Grafana's activeAt, and Mercury's own
        clock is kept apart as `recorded_at`."""
        view = load("rules_view")
        rule = next(r for g in view["data"]["groups"] for r in g["rules"]
                    if r["name"] == "Critical syslog received")
        inst = rule["alerts"][0]
        inst["state"], inst["activeAt"] = "Alerting", "2026-10-21T03:14:50Z"
        inst["labels"]["device_clock"] = "2026-10-21T01:12:03Z"
        inst["value"] = "*Oct 21 01:12:03.117: %SYS-2-MALLOCFAIL"
        value = G.parse({}, view, [], H.epoch("2026-10-21T03:15:30Z"))
        (row,) = [r for r in H.from_reader(value, STORE, now=1.0e9)
                  if r["rule"] == "Critical syslog received"]
        assert row["at"] == "2026-10-21T03:14:50Z" and row["to"] == "condition"
        assert row["at_basis"] == H.AT_BASIS["reader"]
        assert row["recorded_at"] == H.iso(1.0e9)
        assert "01:12:03" not in row["at"]

    def test_an_instance_with_no_grafana_time_is_left_out(self):
        value = {"instances": [{"rule": "x", "state": "Alerting", "kind": "condition",
                                "labels": {"alertname": "x"}, "active_at": None,
                                "starts_at": None}]}
        assert H.from_reader(value, STORE) == []

    @pytest.mark.parametrize("text,want", [
        ("2026-10-22T07:17:50Z", "2026-10-22T07:17:50Z"),
        ("2026-10-22T07:17:50.123456789Z", "2026-10-22T07:17:50Z"),
        ("2026-10-22T09:17:50+02:00", "2026-10-22T07:17:50Z"),
        ("0001-01-01T00:00:00Z", ""), ("", ""), ("not a time", "")])
    def test_grafanas_times_parse_to_utc_seconds(self, text, want):
        assert H.iso(H.epoch(text)) == want


# ---------------------------------------------------------------------------- once each

class TestRecordedOnce:
    def test_the_reader_and_the_backfill_record_the_measured_resolve_once(self, store):
        rows72 = load("annotations_72h")
        # The episode's start, as the backfill reads it (17893, Normal (NoData) to Pending).
        assert _backfill([ann(rows72, 17893)])["added"] == 1
        value = _view_value()
        normal = [n for n in value["recently_normal"]
                  if n["labels"].get("rttMonCtrlAdminIndex") == "2"]
        assert normal and normal[0]["active_at"] == "2026-10-26T17:04:50Z"
        got = H.record(H.from_reader(value, STORE, ["Default"]))
        assert got["added"] == 1, got
        # The same resolve, from the state history: held, never a second row.
        again = _backfill(rows72)
        assert again["held"] >= 2 and again["ok"]
        ident = H.identity(STORE, "IP SLA probe failing", ann(rows72, 17894)["tags"] and
                           H.annotation_labels(ann(rows72, 17894)))
        resolves = [r for r in _rows() if r.get("identity") == ident and r["to"] == "normal"
                    and r["at"] == "2026-10-26T17:04:50Z"]
        assert len(resolves) == 1 and resolves[0]["source"] == "reader"

    def test_a_second_reader_run_and_a_backfill_rerun_add_nothing(self, store):
        rows = load("annotations_firing")
        first = _backfill(rows)
        assert first["added"] == 93
        assert _backfill(rows)["added"] == 0
        assert _backfill(list(reversed(rows)))["added"] == 0
        value = _view_value()
        H.record(H.from_reader(value, STORE))
        n = len(_rows())
        H.record(H.from_reader(value, STORE))
        assert len(_rows()) == n
        assert len({r["key"] for r in _rows()}) == len(_rows())

    def test_a_resolve_with_no_recorded_start_is_not_kept(self, store):
        got = H.record(H.from_reader(_view_value(), STORE))
        assert got["added"] == 0 and got["unopened"] >= 1

    def test_the_after_store_step_records_and_reads_the_store_only_on_change(
            self, store, monkeypatch):
        from modules import evidence_pack, reader_job
        _backfill([ann(load("annotations_72h"), 17893)])
        value = _view_value()
        monkeypatch.setattr(evidence_pack, "_alert_stores", lambda: [STORE])
        monkeypatch.setattr(reader_job, "read_cached", lambda name: {
            "state": "ok", "doc": {"last_good": {"value": value}}})
        monkeypatch.setattr(H, "_LAST_EXPIRE", {"at": 1e12})
        reads = []
        real = H.read
        monkeypatch.setattr(H, "read", lambda: reads.append(1) or real())
        assert H.after_alerts_read() is True
        assert H.after_alerts_read() is False and len(reads) == 1, "unchanged: no store read"

    def test_the_reader_runs_it_after_each_stored_read(self):
        assert G.READER.after_store is G._after_store

    def test_an_unreadable_store_records_nothing(self, store, monkeypatch):
        monkeypatch.setattr(H, "read", lambda: {"state": "unreadable", "rows": [],
                                                "error": "PermissionError: denied"})
        got = _backfill(load("annotations_72h"))
        assert got["ok"] is False and "cannot be read" in got["error"]


# ---------------------------------------------------------------------------- the backfill

def _script():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts", "nmas-alert-backfill")
    loader = importlib.machinery.SourceFileLoader("nmas_alert_backfill", path)
    spec = importlib.util.spec_from_loader("nmas_alert_backfill", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class Grafana:
    """Grafana's annotations API over the captured rows: from and to in ms, inclusive, the
    newest first, at most `limit`. The window applies only when both ends are above zero, as
    Grafana's does (measured on the host 2026-10-26: an ask from 0 answered the newest row of
    all, after the window's end)."""

    timeout = 5.0

    def __init__(self, rows):
        self.rows, self.asked = rows, []

    def _get(self, path):
        from urllib.parse import parse_qs, urlparse
        q = {k: int(v[0]) if k != "type" else v[0] for k, v in parse_qs(
            urlparse(path).query).items()}
        self.asked.append(q)
        if q["from"] > 0 and q["to"] > 0:
            inside = [r for r in self.rows
                      if r["time"] <= q["to"] and r.get("timeEnd", r["time"]) >= q["from"]]
        else:
            inside = list(self.rows)
        got = sorted(inside, key=lambda r: -r["time"])[:q["limit"]]

        class Resp:
            def json(self):
                return got
        return {"ok": True, "response": Resp()}


NOW_MS = H.epoch("2026-10-26T19:22:48Z") * 1000


def _summary(out):
    return next(line for line in out if line.startswith("read "))


class TestTheBackfill:
    def _run(self, rows, *args, client=None):
        out = []
        mod = _script()
        client = client or Grafana(rows)
        code = mod.main(list(args), client=client, now_ms=NOW_MS, out=out.append)
        return code, out, client

    def test_it_reads_all_grafana_holds_and_reruns_add_nothing(self, store):
        rows = load("annotations_firing") + load("annotations_72h")
        code, out, _c = self._run(rows)
        assert code == 0 and "recorded 121" in out[-1], out
        assert "oldest 2026-10-21T01:" in _summary(out)
        code, out, _c = self._run(rows)
        assert code == 0 and "recorded 0, already held 121" in out[-1]

    def test_a_quiet_stretch_is_jumped_and_the_end_is_known_first(self, store):
        """Five quiet days between the 21 Oct slice and the 72 hours: one ask finds the older
        row and the walk jumps to it; the oldest day, found before the walk, is its end."""
        rows = load("annotations_firing") + load("annotations_72h")
        code, out, client = self._run(rows)
        assert code == 0 and "1 quiet stretches skipped" in _summary(out)
        assert [line for line in out if line.startswith("quiet from ")], out
        assert out[0].startswith("estimate: ") and "back to 2026-10-21T01:" in out[0], out[0]

    def test_it_never_asks_from_zero_and_reads_each_row_once(self, store):
        """The first form asked from 0, which Grafana answers without the window: it jumped
        back to the newest row and walked the same days again without end (2026-10-26)."""
        rows = load("annotations_firing") + load("annotations_72h")
        code, out, client = self._run(rows, "--dry-run")
        assert code == 0 and all(q["from"] > 0 for q in client.asked)
        assert f"read {len(rows)} annotations" in _summary(out)

    def test_a_row_after_the_window_is_refused_never_followed(self, store):
        """A Grafana that answers the newest rows whatever the window (the measured answer to
        an ask from 0): the walk stops naming the row and the window, rather than loop."""
        class Unwindowed(Grafana):
            def _get(self, path):
                return super()._get(path.replace("from=", "from=-"))
        rows = load("annotations_firing") + load("annotations_72h")
        code, out, _c = self._run(rows, client=Unwindowed(rows))
        assert code == 2 and "REFUSED" in out[-1] and "after the window's end" in out[-1], out

    def test_the_estimate_comes_first_and_each_day_says_its_progress(self, store):
        rows = load("annotations_firing") + load("annotations_72h")
        code, out, _c = self._run(rows)
        est = out[0]
        assert est.startswith("estimate: ") and "at most 6 days" in est, est
        assert "bound at 5.0 s" in est and "no evidence pack is built" in est
        days = [line for line in out if line.startswith("day ")]
        assert len(days) == 4 and all(" of at most 6, " in d for d in days), days
        assert days[-1].endswith("121 recorded"), days[-1]

    def test_each_line_is_flushed_as_it_is_said(self, monkeypatch):
        """A run that stalls says where: the default output flushes every line."""
        import builtins
        mod = _script()
        said = []
        monkeypatch.setattr(builtins, "print", lambda *a, **k: said.append(k))
        assert mod.main.__defaults__[-1] is mod._say
        mod._say("x")
        assert said == [{"flush": True}]

    def test_a_full_page_is_split_until_each_half_answers_less(self, store, monkeypatch):
        """The limit set just above the slice's busiest minute (one evaluation tick fires
        many rules at once), far below its day: the day's page is split, every row read."""
        from collections import Counter
        rows = load("annotations_firing")
        busiest = max(Counter(r["time"] // 60000 for r in rows).values())
        mod = _script()
        monkeypatch.setattr(mod, "LIMIT", busiest + 1)
        out = []
        assert mod.main([], client=Grafana(rows), now_ms=NOW_MS, out=out.append) == 0, out
        assert "recorded 93" in out[-1] and " 0 split" not in _summary(out)

    def test_a_window_still_full_at_a_minute_is_refused(self, store, monkeypatch):
        """Edit: eleven copies of one real row in the same second, the limit set to ten."""
        mod = _script()
        monkeypatch.setattr(mod, "LIMIT", 10)
        row = ann(load("annotations_72h"), 17896)
        crowd = [dict(row, id=row["id"] + i) for i in range(11)]
        out = []
        assert mod.main([], client=Grafana(crowd), now_ms=NOW_MS, out=out.append) == 2
        assert "REFUSED" in out[-1] and "page limit" in out[-1]

    def test_a_dry_run_records_nothing(self, store):
        code, out, _c = self._run(load("annotations_72h"), "--dry-run")
        assert code == 0 and out[-1] == "dry run: nothing recorded"
        assert H.read()["state"] == "absent"

    def test_a_grafana_that_does_not_answer_stops_naming_the_window(self, store):
        class Down:
            def _get(self, path):
                return {"ok": False, "error": "HTTP 500"}
        code, out, _c = self._run([], client=Down())
        assert code == 1 and "HTTP 500" in out[-1] and "api/annotations from" in out[-1]


# ---------------------------------------------------------------------------- episodes

class TestEpisodes:
    def test_the_slice_groups_into_episodes_by_outcome(self, store):
        _backfill(load("annotations_firing"))
        eps = H.episodes(_rows())
        fired = [e for e in eps if e["outcome"] == "fired"]
        assert fired and all(e["fired_at"] and e["started_at"] <= e["fired_at"] for e in fired)
        assert all(e["resolved_at"] >= e["fired_at"] for e in fired if e["resolved_at"])
        assert {e["outcome"] for e in eps} >= {"fired", "pending_only", "no_data"}
        s3 = [e for e in fired if e["device"] == "s3" and
              e["rule"] == "Device unreachable (SNMP)"]
        assert s3 and s3[0]["duration_words"]

    def test_an_open_episode_the_reader_still_holds_is_ongoing_and_not_history(self, store):
        rows = load("annotations_firing")
        _backfill(rows)
        open_ = [e for e in H.episodes(_rows()) if not e["resolved_at"]]
        assert open_, "the slice ends with some alerts still open"
        held = {open_[0]["identity"]}
        again = {e["id"]: e for e in H.episodes(_rows(), held)}
        assert again[open_[0]["id"]]["ongoing"] is True

    def test_the_tab_summarises_filters_and_caps_each_group(self, store, monkeypatch):
        from modules import evidence_pack as EP
        _backfill(load("annotations_firing"))
        monkeypatch.setattr(H, "_firing_now", lambda: set())
        monkeypatch.setattr(EP, "read", lambda: {"state": "ok", "rows": [], "error": ""})
        now = H.epoch("2026-10-21T04:00:00Z")
        t = H.tab({"range": "24h"}, now=now)
        assert t["counts"]["outcomes"]["fired"] == sum(g["count"] for g in t["groups"])
        assert t["groups"][0]["count"] >= t["groups"][-1]["count"]
        only = H.tab({"range": "24h", "rule": "Device unreachable (SNMP)"}, now=now)
        assert [g["family"] for g in only["groups"]] == ["Device unreachable (SNMP)"]
        dev = H.tab({"range": "24h", "device": "s3"}, now=now)
        assert {e["device"] for g in dev["groups"] for e in g["episodes"]} == {"s3"}
        assert H.tab({"range": "24h"}, now=now + 2 * 86400)["groups"] == []
        everything = H.tab({"range": "all", "show": "all"}, now=now)
        assert everything["counts"]["shown"] > t["counts"]["shown"]
        monkeypatch.setattr(H, "GROUP_SHOWN", 1)
        capped = H.tab({"range": "all", "show": "all"}, now=now)
        assert all(len(g["episodes"]) == 1 for g in capped["groups"])
        assert any(g["count"] > 1 for g in capped["groups"])

    def test_heartbeat_rules_per_device_are_one_group(self, store, monkeypatch):
        from modules import evidence_pack as EP
        _backfill(load("annotations_firing"))
        monkeypatch.setattr(H, "_firing_now", lambda: set())
        monkeypatch.setattr(EP, "read", lambda: {"state": "ok", "rows": [], "error": ""})
        t = H.tab({"range": "all", "show": "all"}, now=H.epoch("2026-10-21T04:00:00Z"))
        fams = [g["family"] for g in t["groups"]]
        assert "NMAS heartbeat missing" in fams
        assert not any(f.startswith("NMAS heartbeat missing:") for f in fams)


# ---------------------------------------------------------------------------- retention

class TestRetention:
    def test_rows_past_retention_move_to_the_lake_and_leave_the_view(self, store,
                                                                       monkeypatch):
        rows = load("annotations_firing")
        _backfill(rows)
        monkeypatch.setattr(H, "retention_days", lambda network: 1)
        put = {}
        got = H.expire(now=H.epoch("2026-10-23T00:00:00Z"),
                       archive=lambda key, body: put.__setitem__(key, body))
        assert got["moved"] == 93 and got["kept"] == 0 and not got["why"]
        (key,) = put
        assert key.startswith("alert-history/Default/2026-10-21T01") and key.endswith("_93.jsonl")
        assert len(put[key].decode().splitlines()) == 93
        assert H.transitions(_rows()) == []
        assert _backfill(rows)["added"] == 0, "a moved transition is never recorded again"

    def test_only_rows_older_than_the_longest_retention_move(self, store, monkeypatch):
        _backfill(load("annotations_firing"))
        monkeypatch.setattr(H, "retention_days", lambda network: 90)
        got = H.expire(now=H.epoch("2026-10-23T00:00:00Z"), archive=lambda k, b: None)
        assert got["moved"] == 0 and len(H.transitions(_rows())) == 93

    def test_with_no_archive_nothing_moves_and_why_is_said(self, store, monkeypatch):
        _backfill(load("annotations_firing"))
        monkeypatch.setattr(H, "retention_days", lambda network: 1)
        monkeypatch.setattr(H, "_archive_for", lambda network: (
            None, f"{network} has no S3/MinIO archive configured"))
        got = H.expire(now=H.epoch("2026-10-23T00:00:00Z"))
        assert got["moved"] == 0 and got["kept"] == 93 and "no S3/MinIO archive" in got["why"]
        assert len(H.transitions(_rows())) == 93

    def test_an_archive_that_refuses_moves_nothing(self, store, monkeypatch):
        _backfill(load("annotations_firing"))
        monkeypatch.setattr(H, "retention_days", lambda network: 1)

        def refuse(key, body):
            raise OSError("AccessDenied")
        got = H.expire(now=H.epoch("2026-10-23T00:00:00Z"), archive=refuse)
        assert got["moved"] == 0 and "AccessDenied" in got["why"]
        assert len(H.transitions(_rows())) == 93

    def test_the_retention_is_the_networks_setting(self, monkeypatch):
        from modules import list_settings
        asked = []
        monkeypatch.setattr(list_settings, "value", lambda n, k, d=None: asked.append((n, k))
                            or 14)
        assert H.retention_days("Lab") == 14 and H.retention_days("") == 14
        assert asked == [("Lab", "alert_history_retention_days"),
                         ("Default", "alert_history_retention_days")]

    def test_dropping_moved_rows_from_the_store_is_refused_with_its_reason(self):
        with pytest.raises(H.Refused, match="append-only"):
            H.compact()
