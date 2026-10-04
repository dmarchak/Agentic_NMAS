"""C426: a device's model from a measured read, not a config line that may be absent.

The model was read only from the committed golden's capture header; a golden
captured without it named nothing (every switch's on the deployment host,
2026-10-04), and an unknown model folds no platform rule. The platform-facts
reader stores each device's own SNMP sysDescr, read from Prometheus for the
whole fleet in one query, and `device_page.model_of` uses it when the golden
names no chassis. C429's platform reasons then hold for every such switch.

The sysDescr rows are real (the deployment host's Prometheus, 2026-10-04),
their instance addresses changed to documentation addresses and their job
label dropped."""

import dataclasses
import os
import re

import pytest

from modules import config
from modules import panels
from modules import reader_job as R
from modules.readers import platform_facts as PF

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROWS = {
    "sysDescr": [
        {"metric": {"__name__": "sysDescr", "device": "r1", "instance": "192.0.2.11",
                    "role": "router",
                    "sysDescr": "Cisco IOS Software [Bengaluru], Virtual XE Software "
                                "(X86_64_LINUX_IOSD-UNIVERSALK9-M), Version 17.6.1a, RELEASE "
                                "SOFTWARE (fc2)\r\nTechnical Support: http://www.cisco.com/"
                                "techsupport\r\nCopyright (c) 1986-2021 by Cisco Systems, Inc."
                                "\r\nCompiled Sat 21-Aug-21 03:"},
         "value": [1791098203.323, "1"]},
        {"metric": {"__name__": "sysDescr", "device": "s1", "instance": "192.0.2.21",
                    "role": "switch",
                    "sysDescr": "Cisco IOS Software, vios_l2 Software (vios_l2-ADVENTERPRISEK9-M), "
                                "Version 15.2(CML_NIGHTLY_20180619)FLO_DSGS7, EARLY DEPLOYMENT "
                                "DEVELOPMENT BUILD, synced to  V152_6_0_81_E\r\nTechnical Support: "
                                "http://www.cisco.com/techsupport\r\nCopyright (c) 1986-2018 by Ci"},
         "value": [1791098203.323, "1"]},
    ],
    "sysObjectID": [
        {"metric": {"__name__": "sysObjectID", "device": "r1", "instance": "192.0.2.11",
                    "sysObjectID": "1.3.6.1.4.1.9.1.3004"}, "value": [1791098203.323, "1"]},
        {"metric": {"__name__": "sysObjectID", "device": "s1", "instance": "192.0.2.21",
                    "sysObjectID": "1.3.6.1.4.1.9.1.1227"}, "value": [1791098203.323, "1"]},
    ],
}


class _Resp:
    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"status": "success", "data": {"resultType": "vector", "result": self._rows}}


class _Prom:
    """PrometheusIntegration's two calls this reader makes."""
    asked: list = []
    fail = False

    def is_configured(self):
        return True

    def _get(self, path, **params):
        _Prom.asked.append((path, params.get("query")))
        if _Prom.fail:
            return {"ok": False, "error": "connection refused"}
        return {"ok": True, "response": _Resp(ROWS[params["query"]])}


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    import modules.integrations.prometheus as P
    monkeypatch.setattr(P, "PrometheusIntegration", _Prom)
    _Prom.asked, _Prom.fail = [], False


def _stored():
    """One real run of the registered reader, through reader_job, into the store."""
    doc = R.run_once(PF.READER, announce=lambda *a, **k: None)
    assert doc["last_attempt"]["ok"], doc
    return doc


def _golden(name):
    with open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", f"{name}.cfg"),
              encoding="utf-8") as fh:
        return fh.read()


def _headerless(name):
    """The golden as the host holds it for a switch: the capture header dropped."""
    return "".join(l for l in _golden(name).splitlines(True) if not l.startswith("! "))


class TestTheRead:
    def test_one_query_each_for_the_whole_fleet_and_the_image_each_names(self):
        value = PF.read()
        assert [q for _p, q in _Prom.asked] == ["sysDescr", "sysObjectID"]
        assert value["configured"] is True
        assert value["devices"]["s1"] == {
            "descr": "Cisco IOS Software, vios_l2 Software (vios_l2-ADVENTERPRISEK9-M), Version "
                     "15.2(CML_NIGHTLY_20180619)FLO_DSGS7, EARLY DEPLOYMENT DEVELOPMENT BUILD, "
                     "synced to  V152_6_0_81_E",
            "image": "vios_l2", "object_id": "1.3.6.1.4.1.9.1.1227"}
        assert value["devices"]["r1"]["image"] == "Virtual XE"

    def test_a_prometheus_that_cannot_be_asked_is_a_failed_read_never_an_empty_fleet(self):
        _Prom.fail = True
        doc = R.run_once(PF.READER, announce=lambda *a, **k: None)
        assert doc["last_attempt"]["ok"] is False
        assert "could not be asked for sysDescr" in doc["last_attempt"]["error"]
        assert PF.facts()[2].startswith("sysDescr has not been read: ")
        assert "connection refused" in PF.facts()[2]
        _Prom.fail = False                 # a later good read replaces the failure

        _stored()
        assert PF.facts()[2] == ""

    def test_unconfigured_is_said(self, monkeypatch):
        monkeypatch.setattr(_Prom, "is_configured", lambda self: False)
        _stored()
        assert PF.measured("s1") == ("", "Prometheus is not configured, so sysDescr is not read")

    def test_it_announces_only_when_an_answer_changes(self):
        v = PF.read()
        assert not PF.changed(v, PF.read())
        moved = {"configured": True, "devices": dict(v["devices"], s1={"image": "x"})}
        assert PF.changed(v, moved)
        assert PF.READER.invalidates == ("device_state",)
        assert "modules.readers.platform_facts" in R.DECLARED_MODULES


class TestTheModel:
    def test_a_headerless_switch_golden_takes_its_model_from_its_own_sysDescr(self):
        from modules import device_page as D

        _stored()
        assert D.model_from_golden(_headerless("s1"))[0] == ""
        model, basis, from_golden = D.model_of(_headerless("s1"), "s1")
        assert (model, from_golden) == ("vios_l2", False)
        assert basis == ("the device's SNMP sysDescr, as Prometheus holds it (the image; the "
                         "device reports no chassis model)")
        # No read time in words a change-only reader would leave stale on an open page.
        assert not re.search(r"\d\d:\d\d", basis) and "platform-facts" in R.CHANGE_ONLY

    def test_a_chassis_the_golden_names_stays_the_most_exact(self):
        from modules import device_page as D

        _stored()
        assert D.model_of(_golden("r2"), "r1") == ("C8000V", "the golden's Chassis type line", True)

    def test_the_measured_read_beats_the_goldens_image_line(self):
        from modules import device_page as D

        _stored()
        assert D.model_of(_golden("s1"), "s1")[2] is False
        # With no measured read the image line still answers, as before.
        assert D.model_of(_golden("s1"), "s9")[:1] == ("vios_l2",)

    def test_nothing_known_says_both_reasons(self):
        from modules import device_page as D

        _stored()
        model, basis, _g = D.model_of(_headerless("s1"), "s9")
        assert model == "" and basis == ("the golden names no model, and Prometheus holds no "
                                          "sysDescr for s9")
        assert D.model_of("", "s1")[0] == "vios_l2"

    def test_c429s_platform_reasons_now_hold_for_the_headerless_switch(self):
        from modules import device_page as D

        _stored()
        model = D.model_of(_headerless("s1"), "s1")[0]
        memory = {"targets": [{"expr": 'cempMemPoolUsed{device="$device"}'}]}
        cpu = {"targets": [{"expr": 'cpmCPUTotal1minRev{device="$device"}'}]}
        for panel in (memory, cpu):
            rule = panels.platform_fold(panel, model)
            assert rule is not None and rule.short == "not reported by vIOS"
        # A router's model is known not to match: its empty panel says what matched nothing.
        assert panels.platform_fold(cpu, D.model_of(_golden("r2"), "r1")[0]) is None

    def test_coverage_names_the_switch_vios_from_its_sysDescr(self):
        from modules import monitoring_coverage as M

        _stored()
        words = M._not_applicable_words("telemetry", {}, _headerless("s1"), "cisco_ios", "s1",
                                        PF.facts())
        assert words == "not applicable — vIOS doesn't support model-driven telemetry"
        # Without it the platform is all that can be said.
        assert M._not_applicable_words("telemetry", {}, _headerless("s1"), "cisco_ios", "s9",
                                       PF.facts()) == \
            "not applicable — IOS doesn't support model-driven telemetry"


def test_a_page_reads_the_store_never_prometheus():
    from modules import device_page as D

    _stored()
    _Prom.asked = []
    D.model_of(_headerless("s1"), "s1")
    assert _Prom.asked == []


def test_the_reader_is_declared_like_every_other():
    assert dataclasses.is_dataclass(PF.READER) and PF.READER.name == "platform-facts"
    assert any(r.name == "platform-facts" for r in R.readers())
