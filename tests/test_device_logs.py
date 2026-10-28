"""The device page's Logs (NSOT_GUI_BRIEF 3.3; step 4), from
`modules/device_logs`.

On Loki's REAL answer for r3's and s3's syslog, captured read-only from the
host on 2026-10-01 (`tests/fixtures/loki/device_logs.json`; s3's clock then
ran days behind and its lines carry IOS's unsynchronised `*`). The fake Loki
APPLIES the query's own line-filter stages (`|=`, `|~`, `!~`) to the captured
lines, so what is tested is the query the module sends, not a canned answer.
Nothing here opens a session to a device.
"""

import copy
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "loki", "device_logs.json")
#: A minimal edit of r3's real heartbeat line: the EEM error that NAMES the
#: applet (C21's shape), which must be listed, never folded as a heartbeat.
APPLET_ERROR = ("Oct  1 10:17:01 r3 2930: r3: Oct  1 10:17:00.400: %HA_EM-3-FMPD_ERROR: "
                "Error executing applet NMAS-HEARTBEAT statement 1.0")


def _lines(host):
    cap = json.load(open(CAPTURE, encoding="utf-8"))
    return [(int(ns), line) for s in cap[host]["body"]["data"]["result"] for ns, line in s["values"]]


def _stages(query):
    """The line-filter stages of a LogQL query, in order."""
    return re.findall(r'(\|=|\|~|!~)\s*(?:"([^"]*)"|`([^`]*)`)', query)


def _keep(line, stages):
    for op, quoted, raw in stages:
        pat = quoted if quoted else raw
        if op == "|=" and pat not in line:
            return False
        if op == "|~" and not re.search(pat, line):
            return False
        if op == "!~" and re.search(pat, line):
            return False
    return True


class Resp:
    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


@pytest.fixture
def loki(monkeypatch):
    from modules.integrations.loki import LokiIntegration
    corpus = _lines("r3") + _lines("s3")
    state = {"asked": [], "corpus": corpus}

    def fake_get(self, path, **params):
        q = params["query"]
        state["asked"].append((path, q))
        inner = q
        if path.endswith("/query"):              # sum(count_over_time(<sel> [24h]))
            inner = re.search(r"count_over_time\((.*) \[\d+h\]\)\)$", q).group(1)
        kept = sorted((x for x in state["corpus"] if _keep(x[1], _stages(inner))), reverse=True)
        if path.endswith("/query"):
            body = {"status": "success", "data": {"result": [
                {"metric": {}, "value": [params["time"] / 1e9, str(len(kept))]}] if kept else []}}
        else:
            kept = kept[:params["limit"]]
            body = {"status": "success", "data": {"result": [
                {"stream": {"job": "network_syslog"},
                 "values": [[str(ns), line] for ns, line in kept]}] if kept else []}}
        return {"ok": True, "response": Resp(body)}

    monkeypatch.setattr(LokiIntegration, "is_configured", lambda self: True)
    monkeypatch.setattr(LokiIntegration, "_get", fake_get)
    return state


def _now():
    return max(ns for ns, _l in _lines("r3") + _lines("s3")) / 1e9 + 60


def _view(host, loki):
    from modules import device_logs
    return device_logs.for_device({"hostname": host}, now=_now())


class TestTheLines:
    def test_the_capture_is_real(self):
        assert len(_lines("r3")) == 40 and len(_lines("s3")) == 40

    def test_r3s_lines_newest_first_with_heartbeats_folded(self, loki):
        v = _view("r3", loki)
        hb = [ns for ns, l in _lines("r3") if "NMAS-HEARTBEAT: NMAS-HEARTBEAT" in l]
        assert v["heartbeat"]["count"] == len(hb) > 0
        assert all("NMAS-HEARTBEAT" not in l["text"] for l in v["lines"])
        assert len(v["lines"]) == 40 - len(hb)
        assert [l["ns"] for l in v["lines"]] == sorted((l["ns"] for l in v["lines"]), reverse=True)
        login = next(l for l in v["lines"] if l["mnemonic"] == "%SEC_LOGIN-5-LOGIN_SUCCESS")
        assert login["sev_word"] == "notice" and login["text"].startswith("Login Success")
        delayed = next(l for l in v["lines"] if l["mnemonic"] == "%DBAL-4-DELAYED_BATCH")
        assert delayed["kind"] == "warn" and delayed["devts"] == "Oct  1 10:04:08.318 UTC"

    def test_an_error_naming_the_applet_is_listed_never_folded(self, loki):
        """C21: the marker in a line is not a heartbeat."""
        loki["corpus"].append((max(ns for ns, _l in loki["corpus"]) + 1, APPLET_ERROR))
        v = _view("r3", loki)
        err = next(l for l in v["lines"] if l["mnemonic"] == "%HA_EM-3-FMPD_ERROR")
        assert err["kind"] == "danger" and "NMAS-HEARTBEAT" in err["text"]
        assert v["heartbeat"]["count"] == len([1 for _n, l in _lines("r3")
                                               if "NMAS-HEARTBEAT: NMAS-HEARTBEAT" in l])

    def test_an_unsynchronised_device_clock_is_said(self, loki):
        v = _view("s3", loki)
        assert v["lines"] == [] or all(l["unsync"] for l in v["lines"] if l["devts"])
        loki["corpus"].append((max(ns for ns, _l in loki["corpus"]) + 1,
                               "Oct  1 10:20:14 s3 1039: s3: *Sep 27 22:05:50.854: "
                               "%LINK-3-UPDOWN: Interface GigabitEthernet0/3, changed state to down"))
        v = _view("s3", loki)
        line = v["lines"][0]
        assert line["unsync"] and line["devts"] == "Sep 27 22:05:50.854" and v["unsync"] >= 1
        assert line["kind"] == "danger" and line["sev_word"] == "error"

    def test_a_prefix_of_another_name_never_matches(self, loki):
        # "br3:" holds the substring "r3:", so only the anchored stage keeps it out.
        loki["corpus"].append((1, "Oct  1 10:00:00 br3 1: br3: Oct  1 10:00:00.000: %SYS-5-CONFIG_I: "
                                  "Configured from console by br3-only"))
        assert all("br3-only" not in l["text"] for l in _view("r3", loki)["lines"])

    def test_a_cut_list_says_so(self, loki, monkeypatch):
        from modules import device_logs
        monkeypatch.setattr(device_logs, "LIMIT", 3)
        v = _view("r3", loki)
        assert len(v["lines"]) == 3 and v["cut"] is True

    def test_a_line_with_no_mnemonic_is_kept_whole(self):
        from modules import device_logs
        p = device_logs.parse("Oct  1 10:00:00 r3 1: r3: something IOS says without one", "r3")
        assert p["mnemonic"] == "" and p["text"] == "something IOS says without one"

    def test_secrets_are_masked_on_the_way_out(self, loki):
        loki["corpus"].append((max(ns for ns, _l in loki["corpus"]) + 1,
                               "Oct  1 10:21:00 r3 2931: r3: Oct  1 10:21:00.000: %PARSER-5-CFGLOG_LOGGEDCMD: "
                               "User:admin  logged command:snmp-server community Planted0Secret RO"))
        v = _view("r3", loki)
        assert "Planted0Secret" not in json.dumps(v)

    def test_a_name_that_cannot_be_matched_safely_is_refused(self, loki):
        from modules import device_logs
        v = device_logs.for_device({"hostname": 'r3"} or {job=~".+'})
        assert v["errors"] and loki["asked"] == []


class TestSourcesThatCannotBeRead:
    def test_loki_not_configured_is_said(self, monkeypatch):
        from modules import device_logs
        from modules.integrations.loki import LokiIntegration
        monkeypatch.setattr(LokiIntegration, "is_configured", lambda self: False)
        assert device_logs.for_device({"hostname": "r3"})["configured"] is False

    def test_loki_unreachable_is_an_error_never_a_quiet_device(self, monkeypatch):
        from modules import device_logs
        from modules.integrations.loki import LokiIntegration
        monkeypatch.setattr(LokiIntegration, "is_configured", lambda self: True)
        monkeypatch.setattr(LokiIntegration, "_get",
                            lambda self, path, **p: {"ok": False, "error": "Could not connect"})
        v = device_logs.for_device({"hostname": "r3"})
        assert v["errors"] == ["Loki could not be asked: Could not connect"] and v["lines"] == []


# ---------------------------------------------------------------------------
# The page, through the real route.
# ---------------------------------------------------------------------------

from tests.test_profile_apply import lab  # noqa: E402,F401 (the fixture)


@pytest.fixture
def page(lab, loki, monkeypatch):
    from modules import device_logs, device_page
    from modules.nsot import listref
    monkeypatch.setattr(device_page, "find_device", lambda name, ref=None: (
        listref.resolve("Lab"), {"hostname": name, "ip": "192.0.2.1", "platform": "cisco_ios"}))
    real = device_logs.for_device
    monkeypatch.setattr(device_logs, "for_device", lambda dev, now=None: real(dev, now=_now()))

    def no_session(*a, **k):
        raise AssertionError("the Logs tab opened a session to a device")
    monkeypatch.setattr("modules.connection.open_ssh", no_session)

    def get(url):
        r = lab["client"].get(url)
        return r, r.get_data(as_text=True)
    return get


class TestThePage:
    def test_r3s_logs_drawn_and_strict(self, page):
        from modules import csp
        r, html = page("/v2/device/r3/logs")
        assert r.status_code == 200 and r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert not re.search(r"\sstyle=|\son[a-z]+=", html)
        assert re.search(r"\d+ heartbeat\(s\) in the last 24 h, the last <time", html)
        assert "<code>%SEC_LOGIN-5-LOGIN_SUCCESS</code>" in html
        assert "Nothing here opens a session to the device." in html

    def test_s3s_unsynchronised_clock_is_said_on_the_page(self, page, loki):
        loki["corpus"].append((max(ns for ns, _l in loki["corpus"]) + 1,
                               "Oct  1 10:20:14 s3 1039: s3: *Sep 27 22:05:50.854: "
                               "%LINK-3-UPDOWN: Interface GigabitEthernet0/3, changed state to down"))
        _r, html = page("/v2/device/s3/logs")
        assert "marks unsynchronised (*)" in html

    def test_the_tab_is_built(self, page):
        _r, html = page("/v2/device/r3?tab=logs")
        assert 'hx-get="/v2/device/r3/logs?list=Lab"' in html and 'id="logs"' in html


# ---------------------------------------------------------------------------
# C820: the syslog job is measured from Loki, never named in the product.
# ---------------------------------------------------------------------------

JOBS_CAPTURE = os.path.join(ROOT, "tests", "fixtures", "loki", "syslog_jobs.json")


def _jobs_answer(*jobs):
    """The lab's real answer to the count by job (`syslog_jobs.json`), its one row's job
    renamed for each of *jobs* (a minimal edit); none: an answer holding no row."""
    cap = json.load(open(JOBS_CAPTURE, encoding="utf-8"))
    row = cap["body"]["data"]["result"][0]
    body = copy.deepcopy(cap["body"])
    body["data"]["result"] = [dict(copy.deepcopy(row), metric={"job": j}) for j in jobs]
    return body


@pytest.fixture
def held(loki, syslog_job_measured, monkeypatch):
    """The `loki` fixture's corpus held under the jobs a planted count-by-job answer names, as a
    real Loki holds them: a selector naming any other job finds no stream."""
    from modules import device_logs
    from modules.integrations.loki import LokiIntegration
    inner = LokiIntegration._get
    state = {"jobs": ["site_syslog"], "measured": 0, "refuse": None}

    def get(self, path, **params):
        q = params["query"]
        if q == device_logs.job_query():
            state["measured"] += 1
            loki["asked"].append((path, q))
            if state["refuse"]:
                return state["refuse"]
            return {"ok": True, "response": Resp(_jobs_answer(*state["jobs"]))}
        m = re.search(r'\{job(=~?)"([^"]*)"', q)
        named = (set(m.group(2).split("|")) if m.group(1) == "=~" else {m.group(2)}) if m else set()
        if not named & set(state["jobs"]):
            loki["asked"].append((path, q))
            return {"ok": True, "response": Resp({"status": "success",
                                                 "data": {"result": []}})}
        return inner(self, path, **params)

    monkeypatch.setattr(LokiIntegration, "_get", get)
    monkeypatch.setattr(LokiIntegration, "url", property(lambda self: "http://loki.invalid"))
    return state


class TestTheSyslogJobIsMeasured:
    def test_the_capture_is_the_query_the_module_asks(self):
        from modules import device_logs
        cap = json.load(open(JOBS_CAPTURE, encoding="utf-8"))
        assert cap["query"] == device_logs.job_query()
        assert [r["metric"]["job"] for r in cap["body"]["data"]["result"]] == ["network_syslog"]

    def test_another_networks_job_is_read_from_loki_and_its_lines_drawn(self, page, held, loki):
        """A planted Loki whose count names `site_syslog`: the tab asks that job's lines and
        draws them; the lab's job name is asked nowhere."""
        from modules import device_logs
        r, html = page("/v2/device/r3/logs")
        assert r.status_code == 200
        assert "<code>%SEC_LOGIN-5-LOGIN_SUCCESS</code>" in html, html[-1500:]
        assert re.search(r"\d+ heartbeat\(s\) in the last 24 h", html)
        others = [q for _p, q in loki["asked"] if q != device_logs.job_query()]
        assert len(others) >= 3, others          # the label's start, the lines, the heartbeats
        assert all(re.search(r'\{job="site_syslog"[,}]', q) for q in others), others
        assert not any("network_syslog" in q for _p, q in loki["asked"])
        assert held["measured"] == 1

    def test_the_labs_answer_reads_the_labs_job(self, held, loki):
        """The lab's own answer, unedited: the tab reads `network_syslog`, as it did."""
        held["jobs"] = ["network_syslog"]
        v = _view("r3", loki)
        assert v["errors"] == [] and v["lines"], v
        assert any(q.startswith('{job="network_syslog"} |= "r3:"') for _p, q in loki["asked"])

    def test_two_jobs_are_both_read(self, held, loki):
        from modules import device_logs
        held["jobs"] = ["alpha_syslog", "site_syslog"]
        assert device_logs.job_matcher() == 'job=~"alpha_syslog|site_syslog"'
        assert _view("r3", loki)["lines"]

    def test_none_found_is_said_and_no_line_is_asked(self, page, held, loki):
        from modules import device_logs
        held["jobs"] = []
        r, html = page("/v2/device/r3/logs")
        assert r.status_code == 200
        assert ("The syslog job could not be found: no job in Loki holds a device&#39;s syslog "
                "line (a device&#39;s own name, its time and a mnemonic) in the last 24 h. "
                "Not the same as r3 having sent nothing.") in html, html[-1500:]
        assert [q for _p, q in loki["asked"]] == [device_logs.job_query()]

    def test_a_refused_ask_is_said_with_lokis_words(self, held, loki):
        held["refuse"] = {"ok": False, "status": 400, "error": "HTTP 400",
                          "detail": "parse error at line 1, col 5: planted"}
        v = _view("r3", loki)
        assert v["errors"] == ["The syslog job could not be found: Loki could not be asked which "
                               "job holds the devices' syslog: HTTP 400 (parse error at line 1, "
                               "col 5: planted)"], v["errors"]

    def test_asked_once_an_hour_and_a_failed_ask_keeps_the_last_jobs(self, held, loki):
        from modules import device_logs

        def jobs(at):
            try:
                return device_logs.syslog_jobs(now=at)
            except device_logs.NoSyslogJob as exc:
                return f"refused: {exc}"
        now = _now()
        assert jobs(now) == ["site_syslog"]
        assert jobs(now + 60) == ["site_syslog"] and held["measured"] == 1
        held["refuse"] = {"ok": False, "error": "Could not connect to http://loki.invalid"}
        later = now + device_logs.LABEL_ASK_EVERY + 1
        assert jobs(later) == ["site_syslog"] and held["measured"] == 2
        held["refuse"], held["jobs"] = None, []
        assert jobs(later + 1) == ["site_syslog"], "an ask finding none dropped the jobs found"


#: C1813: r1's captured OSPF line (tests/fixtures/loki/ask_lines_labelled.json), its facility
#: made OSPFv3's, the only edit: IOS writes OSPFv3's adjacency change as %OSPFv3-5-ADJCHG (45
#: lines in the lab's Loki in the 7 days to 2026-10-26).
OSPFV3_LINE = ("Oct 15 08:16:53 r1 7839: r1: Oct 15 08:16:52.862 UTC: %OSPFv3-5-ADJCHG: Process 1, "
               "Nbr 192.0.2.21 on GigabitEthernet2 from 2WAY to DOWN, Neighbor Down: Dead timer "
               "expired")
#: The facility as upper case alone, the shape C1813 found in five patterns.
_UPPER_ONLY = re.compile(r"\[A-Z0-9_\][+*](?:\(\?:-\[A-Z0-9_\]\+\)\*)?-\[0-")


class TestAMixedCaseFacility:
    """C1813 and C1322: OSPFv3's mnemonic is read wherever OSPF's is."""

    def test_every_reader_of_a_line_takes_ospfv3s_mnemonic(self):
        from modules import device_logs, history_logq, logs_page
        m = re.search(device_logs.LOGQL_FIELDS, OSPFV3_LINE)
        assert m and m.group("dev") == "r1" and m.group("mn") == "%OSPFv3-5-ADJCHG"
        msg = device_logs._MESSAGE.match(OSPFV3_LINE.split(" r1: ", 1)[1])
        assert msg and msg.group("mnemonic") == "%OSPFv3-5-ADJCHG" and msg.group("sev") == "5"
        assert device_logs.mnemonic_severity("%OSPFv3-5-ADJCHG") == 5
        assert history_logq._MN.match("%OSPFv3-5-ADJCHG") and history_logq._MN.match("OSPFv3-5-ADJCHG")
        assert history_logq._MN_IN_TEXT.findall("count OSPFv3-5-ADJCHG lines") == ["OSPFv3-5-ADJCHG"]
        assert logs_page._MN_OK.match("%OSPFv3-5-ADJCHG")
        # The severity filter as Loki reads it (RE2 and Python agree on this pattern).
        assert re.search("%" + device_logs.mnemonic("[0-5]"), OSPFV3_LINE)
        assert not re.search("%" + device_logs.mnemonic("[0-4]"), OSPFV3_LINE)

    def test_the_mnemonic_after_the_severity_stays_upper_case(self):
        from modules import history_logq
        assert not history_logq._MN.match("%OSPFv3-5-adjchg")

    def test_no_pattern_takes_an_upper_case_facility_alone(self):
        from tests import source_index
        files = [f for f in source_index.tracked("modules", suffix=".py") +
                 source_index.tracked("routes", suffix=".py", recursive=False)]
        assert len(files) > 100
        found = [f for f in files
                 if _UPPER_ONLY.search(open(f, encoding="utf-8").read())]
        assert found == []

    def test_the_scan_finds_the_old_shape(self):
        # The planted case: each spelling C1813 found.
        for old in (r"%[A-Z0-9_]+(?:-[A-Z0-9_]+)*-[0-7]-[A-Z0-9_]+", r"%[A-Z0-9_]+-[0-2]-",
                    r"%[A-Z0-9_]+(?:-[A-Z0-9_]+)*-[0-{n}]-[A-Z0-9_]+",
                    r"%?([A-Z][A-Z0-9_]*(?:-[A-Z0-9_]+)*-[0-7]-[A-Z0-9_]+)"):
            assert _UPPER_ONLY.search(old), old
        assert not _UPPER_ONLY.search(r"[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*-[0-7]-")
