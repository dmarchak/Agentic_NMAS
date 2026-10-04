"""The combined deploy's arrival watch (Coverage's artboard A2; decided by the operator,
2026-10-03): for 15 minutes after the batch, each deployed device's sent templates are
watched for their first data, never blocking and never rolling back.

On the reader's REAL capture from the host (`tests/fixtures/coverage_reporting/capture.json`,
the nine devices all reporting, read by `coverage_reporting.read` exactly as on the host) and
the batch's end placed before or after it:

- every sent template is a cell; NTP and LLDP are said as not read, never waiting;
- data at or after the batch's end ARRIVES, with its time and seconds after the batch; the
  first sighting is kept when later readings move the time on; data from before the batch
  never counts;
- SNMP and IP SLA are told apart by the target's file;
- a source the reader could not ask leaves its cells waiting and says why;
- at the deadline a cell still waiting is MISSING, saying for how long, with the device tab
  where its cause is looked for, and the watch ends;
- nothing deployed is nothing to watch, said as ended;
- end to end through Coverage's confirm: the job watches each DEPLOYED device's sent
  templates (`monitoring_coverage.sent_columns`, the preview's one home), and the result card
  draws them, re-read on the job's key while watching and no longer once it has ended.
"""

import copy
import html as html_mod
import json
import re

import pytest

from modules import arrival_watch as AW
from tests.test_coverage_reporting import _capture, read  # noqa: F401 (the fixture)


@pytest.fixture(autouse=True)
def _clean():
    AW._watches.clear()
    yield
    AW._watches.clear()


def _cells(job="j"):
    return {(r["device"], c["column"]): c for r in AW.state(job)["rows"] for c in r["cells"]}


class TestTheCells:
    def test_every_sent_template_is_a_cell_and_ntp_lldp_are_not_read(self):
        AW.start("j", {"r2": ["snmp", "syslog", "heartbeat", "ntp", "lldp", "ip_sla"]},
                 started=1000.0, thread=False)
        cells = _cells()
        assert {k[1] for k in cells} == {"snmp", "syslog", "heartbeat", "ntp", "lldp", "ip_sla"}
        assert cells[("r2", "ntp")]["state"] == "not_read"
        assert "not read here" in cells[("r2", "lldp")]["words"]
        assert cells[("r2", "snmp")]["state"] == "waiting"
        assert AW.state("j")["deadline"] == 1000.0 + 15 * 60

    def test_nothing_deployed_is_nothing_to_watch_said_as_ended(self):
        AW.start("j", {}, started=1000.0, thread=False)
        assert AW.state("j")["ended"] and AW.state("j")["rows"] == []


class TestArrival:
    def test_data_after_the_batch_arrives_with_its_time_before_it_never(self, read):  # noqa: F811
        value, _p, _l = read()
        now = value["read_at"]
        AW.start("before", {"r2": ["snmp", "syslog", "heartbeat", "ip_sla"]},
                 started=now + 1, thread=False)
        AW.observe("before", value=value, now=now + 2)
        assert {c["state"] for c in _cells("before").values()} == {"waiting"}, \
            "data read before the batch ended is not an arrival"
        AW.start("after", {"r2": ["snmp", "syslog", "heartbeat", "ip_sla"]},
                 started=now - 600, thread=False)
        assert AW.observe("after", value=value, now=now)
        cells = _cells("after")
        assert {k[1]: c["state"] for k, c in cells.items()} == {
            "snmp": "arrived", "syslog": "arrived", "heartbeat": "arrived", "ip_sla": "arrived"}
        hb = cells[("r2", "heartbeat")]
        assert hb["at"] == value["heartbeat"]["r2"]
        assert hb["words"].startswith("arrived by ") and " s after the batch" in hb["words"]

    def test_the_first_sighting_is_kept(self, read):  # noqa: F811
        value, _p, _l = read()
        AW.start("j", {"r2": ["syslog"]}, started=value["read_at"] - 600, thread=False)
        AW.observe("j", value=value, now=value["read_at"])
        first = _cells()[("r2", "syslog")]["at"]
        later = dict(value, syslog={**value["syslog"], "r2": value["syslog"]["r2"] + 180})
        assert not AW.observe("j", value=later, now=value["read_at"] + 200)
        assert _cells()[("r2", "syslog")]["at"] == first

    def test_snmp_and_ip_sla_are_told_apart_by_the_targets_file(self, read):  # noqa: F811
        cap = _capture()
        cap["targets"]["data"]["activeTargets"] = [
            t for t in cap["targets"]["data"]["activeTargets"]
            if not (t["labels"].get("device") == "r2"
                    and "ipsla" in (t.get("discoveredLabels") or {}).get("__meta_filepath", ""))]
        value, _p, _l = read(cap)
        AW.start("j", {"r2": ["snmp", "ip_sla"]}, started=value["read_at"] - 600, thread=False)
        AW.observe("j", value=value, now=value["read_at"])
        cells = _cells()
        assert cells[("r2", "snmp")]["state"] == "arrived"
        assert cells[("r2", "ip_sla")]["words"] == "not yet: Prometheus has no target for it yet"

    def test_an_unread_source_waits_and_says_why(self, read):  # noqa: F811
        value, _p, _l = read(prom_fail=("targets",))
        AW.start("j", {"r2": ["snmp", "syslog"]}, started=value["read_at"] - 600, thread=False)
        AW.observe("j", value=value, now=value["read_at"])
        cells = _cells()
        assert cells[("r2", "snmp")]["state"] == "waiting"
        assert "the targets could not be read" in cells[("r2", "snmp")]["words"]
        assert cells[("r2", "syslog")]["state"] == "arrived", "the rest are kept"


class TestTheDeadline:
    def test_still_waiting_at_15_minutes_is_missing_with_where_to_look(self, read):  # noqa: F811
        value, _p, _l = read()
        started = value["read_at"] + 1
        AW.start("j", {"r2": ["snmp", "heartbeat", "ntp"]}, started=started, thread=False)
        assert AW.observe("j", value=value, now=started + 15 * 60)
        cells = _cells()
        assert cells[("r2", "heartbeat")]["state"] == "missing"
        assert cells[("r2", "heartbeat")]["words"] == "not arrived in 15 min"
        assert cells[("r2", "snmp")]["where"] == "monitoring"
        assert cells[("r2", "ntp")]["state"] == "not_read"
        assert AW.state("j")["ended"] and AW.state("j")["missing"] == 2
        assert not AW.observe("j", value=value, now=started + 16 * 60), "an ended watch is still"


class TestEndToEnd:
    def test_the_job_watches_what_it_deployed_and_the_card_draws_it(self, lab, monkeypatch,  # noqa: F811
                                                                   r6_probe_unsent,
                                                                   r2_snmp_down):
        import routes.deploy as rd
        from modules.nsot import capture_job
        from tests.test_coverage_deploy import _page

        started = []
        real_start = AW.start
        monkeypatch.setattr(AW, "start", lambda job, sent, **kw: started.append(sent)
                            or real_start(job, sent, thread=False, **kw))

        def spy(entry, list_name, rows, authorise, **kw):
            return {"device": entry["artifact"].device, "outcome": "deployed",
                    "commands": ["x"], "verify": {"ok": True, "issues": [], "unreadable": [],
                                                  "intent_unmet": []}}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        _r, page = _page(lab, monkeypatch, r2_snmp_down, devices=("r6",))
        body = json.loads(html_mod.unescape(re.search(r"data-body='([^']*)'", page).group(1)))
        out = lab["client"].post("/v2/monitoring/apply/confirm", json=body).get_json()
        assert capture_job.wait(out["job"], 20)
        assert list(started[0]) == ["r6"] and "ip_sla" in started[0]["r6"], started
        frag = lab["client"].get(out["url"]).get_data(as_text=True)
        assert "Watching each sent template for its first data until" in frag
        assert 'hx-trigger="nmas:deploy_job from:body"' in frag, "re-read while watching"
        assert "IP SLA: not yet" in frag
        AW.observe(out["job"], value=r2_snmp_down,
                   now=AW.state(out["job"])["deadline"] + 1, read=False)
        frag = lab["client"].get(out["url"]).get_data(as_text=True)
        assert "Watched for 15 min after the batch" in frag
        assert "IP SLA: not arrived in 15 min" in frag
        assert 'href="/v2/device/r6?tab=monitoring">Diagnose on its Monitoring tab</a>' in frag
        assert 'hx-trigger="nmas:deploy_job from:body"' not in frag, "no re-read once ended"


def test_only_what_was_deployed_is_watched(monkeypatch):
    """A device rolled back or refused kept nothing that was sent: it is not watched."""
    from modules import deploy_job
    from modules.nsot import capture_job

    started = []
    monkeypatch.setattr(AW, "start", lambda job, sent, **kw: started.append(sent))
    monkeypatch.setattr("routes.deploy.apply_batch", lambda *a, **k: {
        "results": [{"device": "r6", "outcome": "deployed"},
                    {"device": "r2", "outcome": "rolled_back"},
                    {"device": "r3", "outcome": "refused"}],
        "templates_sent": {"r6": ["snmp"], "r2": ["snmp"], "r3": ["syslog"]}})
    job = deploy_job.start("Lab", ["r6", "r2", "r3"], {"r6": "a", "r2": "b", "r3": "c"},
                           {"r6": "x", "r2": "y", "r3": "z"}, authorise={}, remove={},
                           scope="templates", actor="t", actor_kind="person", ident=None)
    assert capture_job.wait(job, 20)
    assert started == [{"r6": ["snmp"]}]


def test_in_the_suite_a_watch_starts_no_thread_and_ends_with_its_test():
    """C420: a watch started by a test's deploy ran its 15-minute loop in the worker beside
    every later test. In the suite (tests/conftest.py) the watch is kept, no loop starts."""
    import threading

    AW.start("c420", {"r2": ["snmp"]})
    assert AW.state("c420") is not None
    assert not [t for t in threading.enumerate() if t.name == "arrival-c420"]


from tests.test_coverage_deploy import lab, r2_snmp_down, r6_probe_unsent  # noqa: E402,F401,F811
