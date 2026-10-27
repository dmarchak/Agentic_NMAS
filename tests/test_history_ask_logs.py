"""History › Query › Ask your own, the logs builder (board F3, QueryBuilderLogs3; approved by
the operator 2026-10-15; modules/history_logq.py, templates/v2/_history_ask_logs.html).

Fed by real captures of the lab's Loki (tests/fixtures/loki/ask_*.json and config_limits.yaml,
2026-10-15, read-only, addresses mapped into 192.0.2.0/24 and every line masked), asked through
a stand-in for the Loki integration client that answers as Loki did:

- ONE TOKEN EACH: a value with a quote, a backslash, `}`, `|` or a newline reaches Loki only
  inside one string token that reads back as itself (checked with an independent reader of Go's
  string literals, the way Loki reads them), never as a stage or a selector of its own;
- DISCOVERED: the jobs, the devices and the labels the builder offers are Loki's answers for the
  range (renamed in a copy of the capture, the page follows); a label is used only where it
  covers the whole range, else the line is matched, and the page says which;
- the bounds come from Loki's /config and refuse naming both operands; Mercury's windows bound
  likewise; nothing is asked of Loki's query path when refused;
- the answer: the counts per window charted with each series' numbers summed here from the
  capture, the lines newest first and masked, the empty answer said against what was sent, and a
  Loki that does not answer said "Couldn't load: …" in place;
- a read: nothing is written, and the region pushes the page's own address.
"""

import copy
import json
import os
import re
from html import unescape

import dukpy
import pytest

from modules import history_logq as Q

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOKI = os.path.join(ROOT, "tests", "fixtures", "loki")


def _fx(name):
    with open(os.path.join(LOKI, name), encoding="utf-8") as fh:
        return json.load(fh)


LABELS = _fx("ask_labels.json")
LINES = _fx("ask_lines_labelled.json")
TRAPS = _fx("ask_traps_labelled.json")
COUNTS = _fx("ask_counts_by_device.json")
with open(os.path.join(LOKI, "config_limits.yaml"), encoding="utf-8") as _fh:
    CONFIG = _fh.read()
#: The read: the end of the counts capture (a whole minute), so 24 h is exactly its window.
NOW = int(COUNTS["end"]) / 1e9
FIRST = {k: Q._when(v.replace("T", " ")[:16]) for k, v in LABELS["first_labelled"].items()}


# ---------------------------------------------------------------------------- Go's strings

def go_unquote(text, i):
    """``(value, end)``: the Go string literal starting at *text[i]* (a double quote), read as
    Go's strconv.Unquote reads it (Loki's LogQL lexer), and the index after its closing quote.
    Written from the Go specification, not from the code under test."""
    assert text[i] == '"', text[i:i + 20]
    out, i = [], i + 1
    simple = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
              "\\": "\\", '"': '"'}
    while True:
        # A string that never closes is a failure to say, not an index past the end.
        assert i < len(text), f"the string from {text[:40]!r} never closes"
        ch = text[i]
        if ch == '"':
            return "".join(out), i + 1
        assert ch != "\n", "a raw newline inside a Go string literal"
        if ch == "\\":
            assert i + 1 < len(text), f"the string from {text[:40]!r} ends in a backslash"
            nxt = text[i + 1]
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
            elif nxt == "x":
                out.append(chr(int(text[i + 2:i + 4], 16)))
                i += 4
            else:
                raise AssertionError(f"an escape Go refuses: \\{nxt}")
        else:
            out.append(ch)
            i += 1


def tokens(query):
    """The query's strings (each read back) and the text outside them."""
    strings, outside, i = [], [], 0
    while i < len(query):
        if query[i] == '"':
            value, i = go_unquote(query, i)
            strings.append(value)
            outside.append('"_"')
        elif query[i] == "`":
            raise AssertionError("a raw string: a backtick in a value could end it")
        else:
            outside.append(query[i])
            i += 1
    return strings, "".join(outside)


HOSTILE = ['say "hi"', "back\\slash", "brace} {job=~\".+\"}", "pipe | line_format \"x\"",
           "new\nline\r\t", '"} |= "', "\\\"", "\x00\x1f\x7f", "%`raw`"]


class TestOneTokenEach:
    @pytest.mark.parametrize("value", HOSTILE)
    def test_a_string_reads_back_as_itself_and_ends_where_it_should(self, value):
        tok = Q.string(value)
        got, end = go_unquote(tok, 0)
        assert got == value and end == len(tok)
        assert "\n" not in tok and "\r" not in tok

    @pytest.mark.parametrize("value", HOSTILE + ["r1.example", "(?:x)+*?[]{}^$"])
    def test_a_literal_pattern_matches_exactly_itself(self, value):
        pat = Q.literal(value)
        # RE2's escapes are Python's for these; \x{HH} is RE2's spelling of a byte.
        py = re.sub(r"\\x\{([0-9a-f]{2})\}", lambda m: "\\x" + m.group(1), pat)
        assert re.fullmatch(py, value, re.S)
        assert not re.fullmatch(py, value + "x", re.S)

    def test_hostile_choices_stay_one_token_each_in_the_whole_query(self):
        values = {"job": ["network_syslog", 'a"} |= "x'], "dev": ['r1"}', "s1|s2"],
                  "has": 'Neighbor" != "x} | json', "not": "a\nb\\", "sev": "5",
                  "mn": ["%OSPF-5-ADJCHG"], "show": "counts", "by": "device", "every": "5m"}
        spec, errors = Q.ask(values)
        assert not errors
        disc = {"labels": ["device", "job", "severity"], "since": {"device": 0, "severity": 0}}
        rng = {"start": NOW - 86400, "end": NOW, "seconds": 86400, "words": "the last 24 h"}
        built = Q.build(spec, disc, rng, spec["dev"])
        strings, outside = tokens(built["query"])
        # The structure is the builder's, whatever the values: one selector, the stages it
        # chose, the count around them.
        assert outside == ('sum by (device) (count_over_time({job=~"_", device=~"_", '
                           'severity=~"_"} |= "_" |= "_" != "_" !~ "_" [5m]))'), outside
        assert 'Neighbor" != "x} | json' in strings and "a\nb\\" in strings
        alt = next(s for s in strings if "network_syslog" in s)
        assert re.fullmatch(alt, 'a"} |= "x') and re.fullmatch(alt, "network_syslog")
        dev = next(s for s in strings if "r1" in s)
        assert re.fullmatch(dev, 's1|s2') and not re.fullmatch(dev, "s1")

    def test_a_device_matched_by_its_line_is_one_anchored_token(self):
        spec, _e = Q.ask({"dev": ["r1", 'x":\\s']})
        disc = {"labels": ["job"], "since": {}}
        rng = {"start": NOW - 86400, "end": NOW, "seconds": 86400, "words": "the last 24 h"}
        strings, outside = tokens(Q.build(spec, disc, rng, spec["dev"])["log_query"])
        assert outside == '{job=~"_"} |~ "_" !~ "_"', outside
        pat = strings[1]
        assert re.search(pat, "Oct 15 08:16:53 r1 7839: r1: Oct 15 08:16:52.862 UTC: %OSPF")
        assert not re.search(pat, "Oct 15 08:16:53 r10 7839: r10: Oct 15 08:16:52")
        assert re.search(pat, ' x":\\s: ') and not re.search(pat, ' x":s: ')

    def test_a_label_name_is_never_quoted_so_one_not_discovered_is_refused(self, web):
        html = web.get("/v2/history/query/ask/logs", query_string={
            "show": "counts", "by": "job) (rate({a=\"b\"}", "ask": "1"}).get_data(as_text=True)
        assert "is not a label name" in html
        assert web.asked and all("rate(" not in p.get("query", "") for _p, p in web.asked)

    def test_a_value_it_cannot_carry_is_refused_by_name(self):
        _s, errors = Q.ask({"mn": ["%LINK-3-UPDOWN", '"} or {'], "sev": "9", "every": "2m",
                            "range": "90d", "has": "x" * 201})
        words = " ".join(errors)
        assert "is not a mnemonic" in words and "is not a severity (0 to 7)" in words
        assert "is not a window" in words and "is not a range" in words
        assert "at most 200 are taken" in words


# ---------------------------------------------------------------------------- a stand-in Loki

class _Resp:
    def __init__(self, body=None, text=""):
        self._body, self.text = body, text

    def json(self):
        return self._body


class FakeLoki:
    """Answers as the lab's Loki did on 2026-10-15 (the captures), and records each ask."""

    def __init__(self, labels=None, fail="", empty=False):
        self.asked, self.timeout = [], 65.0
        self.labels = labels or LABELS
        self.fail, self.empty = fail, empty
        #: A whole failed result to answer each ask for lines or counts with (C821).
        self.refuse = None

    def is_configured(self):
        return True

    def _get(self, path, **params):
        self.asked.append((path, params))
        if self.refuse and (path.endswith("query_range") or path.endswith("/query")):
            return self.refuse
        if self.fail and (path.endswith("query_range") or path.endswith("/query")):
            return {"ok": False, "error": self.fail}
        if path == "config":
            return {"ok": True, "response": _Resp(text=CONFIG)}
        if path.endswith("/labels"):
            return {"ok": True, "response": _Resp(self.labels["labels"])}
        m = re.search(r"/label/([^/]+)/values$", path)
        if m:
            return {"ok": True, "response": _Resp(self.labels["values"].get(
                m.group(1), {"status": "success", "data": []}))}
        q = params.get("query", "")
        if path.endswith("query_range") and params.get("direction") == "forward":
            label = re.match(r'\{(\w+)=~', q).group(1)
            ts = FIRST.get(label)
            res = [{"stream": {label: "x"}, "values": [[str(int(ts * 1e9)), "first"]]}] if ts else []
            return {"ok": True, "response": _Resp({"data": {"resultType": "streams",
                                                            "result": res}})}
        if path.endswith("/query"):
            return {"ok": True, "response": _Resp({"data": {"resultType": "vector", "result": [
                {"metric": {}, "value": [NOW, "0" if self.empty else "1240"]}]}})}
        if params.get("step"):
            body = copy.deepcopy(COUNTS["answer"])
            # As Loki answers: only the devices the selector names (one value, or an
            # alternation), read here with Go's string rules.
            m = re.search(r'device(=~?)"', q)
            if m:
                want, _end = go_unquote(q, m.end() - 1)
                regex = m.group(1) == "=~"
                body["data"]["result"] = [
                    r for r in body["data"]["result"]
                    if (re.fullmatch(want, r["metric"]["device"]) if regex
                        else r["metric"]["device"] == want)]
            if self.empty:
                body["data"]["result"] = []
            return {"ok": True, "response": _Resp(body)}
        body = copy.deepcopy((TRAPS if "snmptrapd" in q else LINES)["answer"])
        # The heartbeat stage, as Loki applies it: the line form device_logs names.
        from modules.device_logs import HEARTBEAT_LINE
        if "!~ " in q:
            for s in body["data"]["result"]:
                s["values"] = [v for v in s["values"] if not re.search(HEARTBEAT_LINE, v[1])]
        if self.empty:
            body["data"]["result"] = []
        return {"ok": True, "response": _Resp(body)}


@pytest.fixture
def web(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tests import test_logs_v2 as T

    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.readers.adjacencies.lists",
                        lambda: [("Lab", SimpleNamespace(repo_dir=str(tmp_path)), T.MANAGED)])
    monkeypatch.setattr("modules.history_logq._now", lambda: NOW)
    monkeypatch.setattr("modules.history_logq._devices_of_role",
                        lambda ln, role: ["s1", "s2"] if role == "switch" else [])
    monkeypatch.setattr("modules.history_logq.roles", lambda ln: [("router", 5), ("switch", 4)])
    loki = FakeLoki()
    monkeypatch.setattr("modules.history_logq._client", lambda list_name, wait=65.0: loki)
    Q.forget()
    import app as A
    client = A.app.test_client()
    client.loki = loki
    client.asked = loki.asked
    yield client
    Q.forget()


def _page(web, **qs):
    qs.setdefault("list", "Lab")
    r = web.get("/v2/history/query/ask/logs", query_string=qs)
    assert r.status_code == 200, r.status_code
    return unescape(r.get_data(as_text=True))


def _logs_asked(web):
    return [p for path, p in web.asked
            if path.endswith("query_range") and p.get("direction") == "backward"]


class TestDiscovered:
    def test_the_jobs_and_devices_offered_are_loki_s(self, web):
        html = _page(web)
        for job in LABELS["values"]["job"]["data"]:
            assert f">{job}</a>" in html, job
        assert "all 9" in html and 'value="r6"' in html
        assert "The values Loki's <span class=\"mono\">job</span> label holds" in html

    def test_renamed_in_the_capture_the_page_follows(self, web):
        renamed = copy.deepcopy(LABELS)
        renamed["values"]["job"]["data"] = ["alpha", "beta"]
        renamed["values"]["device"]["data"] = ["edge-1"]
        web.loki.labels = renamed
        html = _page(web)
        assert ">alpha</a>" in html and ">beta</a>" in html and "network_syslog</a>" not in html
        assert "all 1" in html

    def test_the_labels_are_asked_for_the_range(self, web):
        _page(web, range="7d")
        got = [p for path, p in web.asked if path.endswith("/labels")]
        assert got and int(got[0]["end"]) - int(got[0]["start"]) == 7 * 86400 * 10 ** 9

    def test_a_label_is_used_only_where_it_covers_the_range(self, web):
        # 24 h: the device label began 13 Oct, before the range, so it is used; severity began
        # 15 Oct 03:49, inside it, so severity is read from the line's mnemonic.
        q24 = Q.view("Lab", {"dev": ["r1", "s1"], "sev": "5"}, now=NOW, client=web.loki)
        assert 'device=~"r1|s1"' in q24["built"]["query"]
        assert "severity=~" not in q24["built"]["query"]
        assert '-[0-5]-' in q24["built"]["query"]
        q1 = Q.view("Lab", {"dev": ["r1"], "sev": "5", "range": "1h"}, now=NOW, client=web.loki)
        assert 'device="r1"' in q1["built"]["query"]
        assert 'severity=~"[0-5]"' in q1["built"]["query"]
        q7 = Q.view("Lab", {"dev": ["r1"], "range": "7d"}, now=NOW, client=web.loki)
        assert "device=" not in q7["built"]["query"] and r"\\sr1:\\s" in q7["built"]["query"]

    def test_the_page_says_how_each_is_matched(self, web):
        html = _page(web, dev="r1", sev="5", range="7d")
        assert "matched by its own name before the line" in html
        assert "By the digit in each line" in html
        html = _page(web, dev="r1", sev="5", range="1h")
        assert "By the <span class=\"mono\">device</span> label Loki holds" in html
        assert "By Loki's <span class=\"mono\">severity</span> label" in html

    def test_the_bounds_are_loki_s_own_read_from_its_config(self, web):
        html = _page(web)
        assert "max_query_length 30d1h" in html and "30 days 1 hour" in html
        assert "1 min an ask" in html and "5,000 lines" in html and "500 series" in html
        assert "retention_period 2y" in html and "2 years" in html

    def test_the_mnemonics_offered_are_the_logs_reader_s(self, web):
        from tests import test_logs_v2 as T
        from modules import reader_job
        T._store(T._read(previous=T._read(), retention=730))
        try:
            html = _page(web, range="30d")
        finally:
            os.remove(reader_job.store_path("logs-summary"))
        assert "DBAL-4-DELAYED_BATCH</a>" in html and "Mercury's logs reader counted" in html


class TestTheAnswer:
    def test_counts_are_asked_per_window_and_summed_here_from_the_capture(self, web):
        html = _page(web, show="counts", by="device", every="1h", range="24h", ask="1")
        asked = [p for path, p in web.asked if p.get("step")]
        assert len(asked) == 1 and asked[0]["step"] == "3600"
        assert asked[0]["query"].startswith("sum by (device) (count_over_time({job=~\".+\"}")
        assert asked[0]["query"].endswith(" [1h]))")
        assert int(asked[0]["start"]) % (3600 * 10 ** 9) == 0, "whole windows, as Loki aligns"
        start, end = NOW - 86400, NOW
        for row in COUNTS["answer"]["data"]["result"]:
            dev = row["metric"]["device"]
            # Each point closes the hour before it; only whole hours inside the range count.
            total = sum(int(v) for t, v in row["values"] if t - 3600 >= start and t <= end)
            assert re.search(rf'device="{dev}"</span></td><td class="num">{total:,} line', html), dev
        assert "data-panel-json='" in html and "answered in" in html

    def test_the_chart_payload_holds_a_lines_link_per_series(self, web):
        got = Q.view("Lab", {"show": "counts", "every": "1h", "ask": "1"}, now=NOW,
                     client=web.loki)
        p = got["answer"]["payload"]
        assert p["stepped"] and p["legend_off"] and p["step"] == 3600
        s = p["series"][0]
        # 08:25 to 08:25: the 23 whole hours inside it (09:00 to 08:00 the next day).
        assert len(s["times"]) == len(s["values"]) == 23
        assert "dev=" + s["label"].split('"')[1] in s["href"] and "show" not in s["href"]

    def test_lines_are_newest_first_masked_and_heartbeats_left_out(self, web):
        html = _page(web, ask="1", range="1h")
        q = _logs_asked(web)[0]
        assert q["limit"] == 200 and "!~ \"%HA_EM-" in q["query"]
        times = re.findall(r'<td class="lq-nw mono"><time datetime="([0-9T:Z-]+)"', html)
        assert times and times == sorted(times, reverse=True)
        assert "%OSPF-5-ADJCHG: Process 1, Nbr 192.0.2.21" in html
        assert ">network_syslog</td>" in html and "5 notice" in html

    def test_a_trap_is_drawn_with_its_job_and_no_severity(self, web):
        html = _page(web, job="snmptrapd", ask="1", range="30d")
        q = _logs_asked(web)[0]
        assert q["query"].startswith('{job="snmptrapd"}')
        assert "IF-MIB::linkDown" in html and ">snmptrapd</td>" in html
        row = re.search(r"<tr><td class=\"lq-nw mono\"><time [^>]*>[^<]*</time></td>"
                        r"<td class=\"mono\">s1</td>"
                        r"<td>(.*?)</td>", html)
        assert row and "—" in row.group(1) and "notice" not in row.group(1)

    def test_a_secret_in_a_line_is_masked(self, web):
        body = copy.deepcopy(LINES)
        body["answer"]["data"]["result"][0]["values"].insert(0, [
            "1792052699000000000", "Oct 15 08:24:59 r1 1: r1: Oct 15 08:24:58: %PARSER-5-"
            "CFGLOG_LOGGEDCMD: User:a  logged command:username admin password 0 Sup3rSecret"])
        web.loki.labels = LABELS
        orig = web.loki._get

        def _get(path, **p):
            if path.endswith("query_range") and p.get("direction") == "backward":
                web.loki.asked.append((path, p))
                return {"ok": True, "response": _Resp(body["answer"])}
            return orig(path, **p)
        web.loki._get = _get
        html = _page(web, ask="1", range="1h")
        assert "Sup3rSecret" not in html and "CFGLOG_LOGGEDCMD" in html

    def test_a_range_longer_than_loki_s_ask_is_refused_naming_both(self, web):
        html = _page(web, range="custom", **{"from": "2026-08-31 08:25", "to": "2026-10-15 08:25"},
                     ask="1")
        assert "Refused: one ask spans at most 30 days 1 hour (Loki's max_query_length, 30d1h)" \
               ". This range is 45 days." in html
        assert "Narrow to the last 30 days" in html
        assert not _logs_asked(web)

    def test_more_windows_than_drawn_is_refused_with_the_window_that_fits(self, web):
        html = _page(web, show="counts", every="1m", range="30d", ask="1")
        assert "at most 1,000 windows a series (Mercury's bound)" in html
        assert "30 days every 1 minute is 43,200 windows" in html
        assert "Count every 1 hour" in html
        assert not [p for _path, p in web.asked if p.get("step")]

    def test_loki_not_answering_is_couldn_t_load_in_place(self, web):
        web.loki.fail = "Timed out after 65.0s"
        html = _page(web, ask="1")
        assert "Couldn't load: Loki did not answer within 1 min (its query_timeout" in html
        assert "Nothing is drawn from an earlier answer" in html and "Ask again" in html

    def test_an_empty_answer_is_said_against_what_was_sent(self, web):
        web.loki.empty = True
        html = _page(web, ask="1", range="1h")
        assert "No lines match over the last 1 h." in html
        assert "inside what Loki keeps (2 years), so this is an answer, not a gap" in html

    def test_an_empty_answer_resting_on_free_text_is_never_called_an_answer(self, web):
        """C1804 (the operator's walk, 2026-10-26): "reboot", which IOS never logs, read as no
        reboots. A zero resting on a text filter says the text may not be how the platform
        logs it, and offers to drop it."""
        web.loki.empty = True
        html = unescape(_page(web, ask="1", has="Neighbor", range="1h"))
        assert "No lines match over the last 1 h." in html
        assert ("No line contains “Neighbor”: this may not match how the platform logs it."
                in html)
        assert "Drop the text filter" in html
        assert "inside what Loki keeps (2 years)." in html
        assert "an answer, not a gap" not in html

    def test_older_pages_carry_where_they_start(self, web):
        html = _page(web, ask="1", range="1h")
        assert "Lines 1 to " in html and "newest first" in html


class TestThePage:
    def test_strict_policy_the_viewer_and_the_how_link(self, web):
        from modules import csp
        r = web.get("/v2/history/query/ask/logs?list=Lab")
        assert r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        html = r.get_data(as_text=True)
        assert 'data-manual="history#ask-logs"' in html and "<script>" not in html
        assert 'aria-current="page">Query</a>' in html

    def test_the_region_pushes_the_page_s_own_address(self, web):
        r = web.get("/v2/history/query/ask/logs/region",
                    query_string={"list": "Lab", "dev": "r1", "hl": "dev"},
                    headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert r.headers["HX-Push-Url"].startswith("/v2/history/query/ask/logs?list=Lab&dev=r1")
        body = r.get_data(as_text=True)
        assert body.lstrip().startswith('<div id="lq"') and "<html" not in body

    def test_every_request_names_its_own_target(self, web):
        """The frame turns htmx's inheritance off (C409): a request with no target of its own
        swaps the control it sits on, the region drawn inside itself."""
        html = _page(web, show="counts", ask="1")
        region = html[html.index('<div id="lq"'):]
        tags = re.findall(r"<(?:a|form|select|input|button)\b[^>]*\bhx-get=\"/v2/history/query/"
                          r"ask/logs/region[^>]*>", region)
        assert len(tags) >= 20
        for tag in tags:
            assert 'hx-target="#lq"' in tag and 'hx-swap="outerHTML"' in tag, tag

    def test_the_last_choice_is_marked_and_said(self, web):
        html = _page(web, sev="5", hl="sev")
        assert re.search(r'<mark>\|~ "%\[A-Z0-9_\]\+', html), "the severity stage is marked"
        assert "the last choice:" in html and "or worse, read from the line" in html

    def test_a_start_from_chip_sets_its_choices_and_is_marked(self, web):
        html = _page(web, mn="%OSPF-5-ADJCHG", show="counts", by="device", every="5m")
        assert re.search(r'class="lq-chip on"[^>]*aria-current="true">OSPF adjacency changes', html)
        assert "OSPF adjacency changes per 5 minutes, every device" not in html  # not asked yet

    def test_code_mode_takes_the_query_formed(self, web):
        html = _page(web, dev="r1", range="1h")
        assert "/v2/history/query/metric/ask?" in html and "lang=logql" in html

    def test_edit_as_code_from_counts_ends_in_the_chart(self, web):
        """C819: Counts over time's query, handed to Code mode, is drawn there as series by
        the same chart (Loki answering with the counts capture); it was refused before."""
        html = _page(web, dev="r1", show="counts", every="1h", ask="1")
        href = re.search(r'<a href="(/v2/history/query/metric/ask\?[^"]+)">Edit as code</a>',
                         html).group(1)
        assert "lang=logql" in href and "count_over_time" in href
        code = unescape(web.get(href).get_data(as_text=True))
        assert "data-panel-json" in code, "Code mode drew no chart for the count query"
        assert "Couldn't load" not in code and "not lines" not in code
        asked = [p for path, p in web.asked if path.endswith("query_range") and p.get("step")]
        assert asked and "count_over_time" in asked[-1]["query"]

    def test_nothing_is_written(self, web, tmp_path):
        from modules import config
        before = sorted(os.listdir(config.DATA_DIR)) if os.path.isdir(config.DATA_DIR) else []
        _page(web, ask="1", show="counts")
        _page(web, ask="1")
        after = sorted(os.listdir(config.DATA_DIR)) if os.path.isdir(config.DATA_DIR) else []
        assert before == after


# ---------------------------------------------------------------------------- in a browser

def test_the_builder_in_a_browser(web):  # noqa: F811
    """In a real browser at 1440: the counts chart draws from the answer the page holds; a click
    on it names its window and offers that series' lines for the window; From… to… says the
    local time beside a UTC time typed; a choice redraws the region in place, pushes its
    address and drops the answer (it no longer matches the query); nothing scrolls sideways."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A

    url = ("/v2/history/query/ask/logs?list=Lab&dev=r1&dev=s1&show=counts&every=1h&ask=1")
    with browser.Served(A.app) as srv, browser.Browser() as b:
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
        b.go(srv.url(url))
        b.wait_for("return document.querySelector('.lq-panel .u-over')", 15)
        b.js("var o = document.querySelector('.lq-panel .u-over'); o.scrollIntoView();"
             "var r = o.getBoundingClientRect(); var x = r.left + r.width * 0.5,"
             " y = r.top + r.height * 0.3; ['mousemove', 'mousedown', 'mouseup', 'click']"
             ".forEach(function (t) { o.dispatchEvent(new MouseEvent(t, {bubbles: true,"
             " clientX: x, clientY: y})); }); return 1")
        b.wait_for("var p = document.querySelector('.lq-pick'); return p && !p.hidden", 10)
        pick = b.js("var p = document.querySelector('.lq-pick'); var a = p.querySelector('a');"
                    "var s = p.querySelector('span');"
                    "return [p.textContent, a ? a.getAttribute('href') : '', s.title]")
        # One zone per view (the operator, 2026-10-26): the title's span and the legend's
        # windows in the browser's zone, named, UTC on hover; the chart's counts over their
        # windows (the first drawn time a step before the first count's close).
        zone = b.js("var t = document.querySelector('.lq-top time[data-lq-when=span]');"
                    "var c = document.querySelector('.lq-panel').__nmasChart;"
                    "var p = document.querySelector('.lq-panel').__nmasLast;"
                    "return [t.textContent, t.title, window.NMAS_PANELS.viewerZone("
                    "Date.parse(t.getAttribute('data-lq-to')) / 1000),"
                    " c.data[0][0], p.series[0].times[0], p.step,"
                    " c.data[0].length, p.series[0].times.length]")
        b.js("var d = document.querySelector('.lq-pickbox'); d.open = true;"
             "var i = document.getElementById('lq-from'); i.value = '2026-10-10 06:00';"
             "i.dispatchEvent(new Event('input', {bubbles: true})); return 1")
        local = b.js("return document.getElementById('lq-from-local').textContent")
        b.js("document.querySelector('[data-lq-close]').click(); return 1")
        closed = b.js("return !document.querySelector('.lq-pickbox').open")
        b.js("var a = Array.prototype.find.call(document.querySelectorAll('.lq-chip'),"
             " function (x) { return x.textContent.trim() === '7 days'; }); a.click(); return 1")
        b.wait_for("return location.search.indexOf('range=7d') >= 0"
                   " && !document.getElementById('lq-answer')", 10)
        b.click("#lq-ask")
        b.wait_for("return location.search.indexOf('ask=1') >= 0"
                   " && document.getElementById('lq-answer')", 10)
        nested = b.js("return document.querySelectorAll('#lq').length")
        wide = b.js("return document.documentElement.scrollWidth <= window.innerWidth")
        b.go("about:blank")
    words, href, utc_words = pick
    assert re.search(r'device="(r1|s1)" · \d+ \w{3} \d\d:\d\d to (\d+ \w{3} )?\d\d:\d\d \S+ · '
                     r'\d+ lines? in this window', words), words
    assert re.search(r' UTC · \d+ lines? in this window$', utc_words), utc_words
    text, title, name, first_drawn, first_close, step, drawn_n, closes_n = zone
    assert text.endswith(" " + name) and title.endswith(" UTC"), (text, title, name)
    assert first_drawn == first_close - step and drawn_n == closes_n + 1, zone
    assert "show=counts" not in href and "range=custom" in href and "from=" in href and "to=" in href
    assert re.search(r"dev=(r1|s1)(&|$)", href) and "ask=1" in href, href
    assert re.fullmatch(r"UTC · \d\d:\d\d local \(UTC([+\u2212]\d+(:\d\d)?)?\)", local), local
    assert closed and wide and nested == 1, (closed, wide, nested)


# ---------------------------------------------------------------------------- the script

def _js(expr):
    src = open(os.path.join(ROOT, "static", "js", "nmas_logq.js"), encoding="utf-8").read()
    return dukpy.evaljs("var window = {};" + src + ";" + expr)


class TestTheScript:
    def test_a_utc_time_is_read_and_its_local_time_said(self):
        assert _js("window.NMAS_LOGQ.parseUtc('2026-10-10 06:00')") == 1791612000
        assert _js("window.NMAS_LOGQ.parseUtc('10/10/2026')") is None
        assert _js("window.NMAS_LOGQ.localWords(1791612000, -360)") == \
            "UTC · 00:00 local (UTC\u22126)"
        assert _js("window.NMAS_LOGQ.localWords(1791612000, 330)") == \
            "UTC · 11:30 local (UTC+5:30)"

    def test_a_point_opens_its_window_s_lines(self):
        got = _js("var w = window.NMAS_LOGQ.windowOf(1792052700, 300);"
                  "[w.from, w.to, window.NMAS_LOGQ.pickHref('/v2/x?list=Lab&dev=r1', w)]")
        assert got[:2] == ["2026-10-15 08:20", "2026-10-15 08:25"]
        assert got[2] == "/v2/x?list=Lab&dev=r1&from=2026-10-15%2008%3A20&to=2026-10-15%2008%3A25"

    def test_the_series_nearest_the_pointer_with_a_count(self):
        # Values 4 and 2 at index 0, drawn at y = 200 - 40 v; the pointer at 125 is nearer 2.
        got = _js("window.NMAS_LOGQ.nearest([[0], [4], [2], [0]], 0, 125,"
                  " function (v) { return 200 - 40 * v; })")
        assert got == 1
        assert _js("window.NMAS_LOGQ.nearest([[0], [0], [null]], 0, 10,"
                   " function (v) { return v; })") == -1


class TestARolesDevices:
    """The devices a role filter matches, from the NAMED network's own inventory (C833: mutation
    night #12 found its 5 survivors; the page's tests stood it in)."""

    ROWS = [{"hostname": "r2", "role": "router"}, {"hostname": "s1", "role": "switch"},
            {"hostname": "r1", "role": "router"}, {"hostname": "", "role": "router"},
            {"hostname": "x9", "role": None}, {"role": "router"}]

    @pytest.fixture
    def inventory(self, monkeypatch):
        from types import SimpleNamespace
        asked = {}

        def resolve(name):
            asked["network"] = name
            return SimpleNamespace(csv_path=f"/lists/{name}/devices.csv")

        def load(path):
            asked["path"] = path
            if "Unreadable" in path:
                raise OSError("devices.csv: permission denied")
            return [dict(r) for r in self.ROWS]
        monkeypatch.setattr("modules.nsot.listref.resolve", resolve)
        monkeypatch.setattr("modules.device.load_saved_devices", load)
        return asked

    def test_the_roles_named_devices_sorted_from_that_networks_inventory(self, inventory):
        assert Q._devices_of_role("Branch", "router") == ["r1", "r2"]
        assert inventory == {"network": "Branch", "path": "/lists/Branch/devices.csv"}

    def test_a_device_with_no_role_matches_only_the_empty_role(self, inventory):
        assert Q._devices_of_role("Branch", "") == ["x9"]
        assert Q._devices_of_role("Branch", "firewall") == []

    def test_an_unreadable_inventory_matches_nothing(self, inventory):
        assert Q._devices_of_role("Unreadable", "router") == []


# ---------------------------------------------------------------------------- Loki's own words
# C821: Loki answers a query it refuses with its reason as PLAIN TEXT; the integration client
# kept a JSON answer's `error` (Prometheus's form) and nothing else, so the person read
# "HTTP 400" alone.

REFUSED = _fx("refused_plain_text.json")
PLANTED = "PlantedC0mmunity0nTheWire"


def _refused(monkeypatch, body=None, content_type=None, status=None):
    """The real client's one GET, on Loki's captured refusal (or *body* in its place)."""
    from types import SimpleNamespace

    from modules.integrations.loki import LokiIntegration

    def no_json():
        raise ValueError("Expecting value: line 1 column 1 (char 0)")
    answer = SimpleNamespace(status_code=status or REFUSED["status"], json=no_json,
                             text=REFUSED["body"] if body is None else body,
                             headers={"Content-Type": content_type or REFUSED["content_type"]})
    c = LokiIntegration()
    monkeypatch.setattr(LokiIntegration, "url", "http://192.0.2.10:3100")
    monkeypatch.setattr(c, "session", lambda: SimpleNamespace(get=lambda *a, **k: answer))
    return c._get("loki/api/v1/query_range", query=REFUSED["query"])


class TestLokisOwnWords:
    def test_the_capture_is_one_plain_text_line_carrying_the_planted_value(self):
        assert REFUSED["status"] == 400 and REFUSED["content_type"].startswith("text/plain")
        assert "\n" not in REFUSED["body"] and REFUSED["body"].count(PLANTED) == 2

    def test_a_plain_text_refusal_keeps_its_line_masked(self, monkeypatch):
        r = _refused(monkeypatch)
        assert not r["ok"] and r["status"] == 400 and r["error"] == "HTTP 400"
        assert PLANTED not in json.dumps(r), r
        # Loki's own words, around the masked value, as the capture holds them.
        head = REFUSED["body"].partition(PLANTED)[0]
        said = r.get("detail", "")
        assert said.startswith(head) and "error parsing regexp: missing closing ): `" in said \
            and said.endswith(" RO`"), said

    def test_only_the_first_line_is_kept(self, monkeypatch):
        r = _refused(monkeypatch, body="\n" + REFUSED["body"] + "\nsecond line, planted\n")
        said = r.get("detail", "")
        assert said.startswith("parse error : stage '|~ ") and "second line" not in said, said

    def test_bounded_at_500_and_masked(self, monkeypatch):
        """A long line is cut at 500 characters, the planted value inside them still masked."""
        from modules.integrations.base import DETAIL_LIMIT
        r = _refused(monkeypatch, body="x" * 300 + " " + REFUSED["body"] + " " + "y" * 400)
        said = r.get("detail", "")
        assert DETAIL_LIMIT == 500 and len(said) == 500
        assert "community <redacted" in said and "PlantedC0" not in said

    def test_an_html_page_or_an_empty_answer_adds_no_words(self, monkeypatch):
        r = _refused(monkeypatch, body="<html><body>502 Bad Gateway</body></html>",
                     content_type="text/html", status=502)
        assert r["error"] == "HTTP 502" and "detail" not in r
        assert "detail" not in _refused(monkeypatch, body="  \n\n")

    def test_the_page_says_lokis_reason_masked(self, web, monkeypatch):
        web.loki.refuse = _refused(monkeypatch)
        html = _page(web, ask="1")
        assert "Couldn't load: Loki refused the query: HTTP 400: parse error : stage " in html, \
            html[html.find("Couldn't load"):][:400]
        assert "error parsing regexp: missing closing )" in html
        assert PLANTED not in html


# ---------------------------------------------------------------------------- the walk of 10-26
# The operator walked History › Query on 2026-10-26: a count drawn a window late, a 7-day
# title ending at the last series' last line, a day's window without its end date, the axis
# in one zone and the words in another, leftover filters no line could match, and a builder
# whose scope came after the choices read over it.

#: The walk's day: the read at 26 Oct 08:25 UTC, and r1's lines at known times on 22 Oct.
WALK_NOW = 1793003100                                     # 2026-10-26 08:25 UTC
EVENTS = [1792674000, 1792674300, 1792677600]             # 22 Oct 13:00, 13:05, 14:00 UTC
DAY = 86400


class EventLoki(FakeLoki):
    """Loki's counts as count_over_time defines them, written here from its definition, not
    from the code under test: the point at t counts the lines in (t − step, t], and Loki
    leaves out a point with none. Every other read is the captures' (FakeLoki)."""

    def _get(self, path, **params):
        if path.endswith("query_range") and params.get("step"):
            self.asked.append((path, params))
            step = int(params["step"])
            start, end = int(params["start"]) // 10 ** 9, int(params["end"]) // 10 ** 9
            values = [[t, str(n)] for t in range(start, end + 1, step)
                      for n in [sum(1 for e in EVENTS if t - step < e <= t)] if n]
            return {"ok": True, "response": _Resp({"data": {"resultType": "matrix", "result": [
                {"metric": {"device": "r1"}, "values": values}]}})}
        return super()._get(path, **params)


def _panels(expr):
    """static/js/nmas_panels.js (and nmas_logq.js after it, as base.html loads them) in
    duktape, *expr* evaluated."""
    src = "".join(open(os.path.join(ROOT, "static", "js", f), encoding="utf-8").read() + ";"
                  for f in ("nmas_panels.js", "nmas_logq.js"))
    return dukpy.evaljs("var window = {};" + src + expr)


def _week_of_days(web):
    loki = EventLoki()
    got = Q.view("Lab", {"show": "counts", "by": "device", "every": "1d", "range": "7d",
                         "ask": "1"}, now=WALK_NOW, client=loki)
    assert got["answer"]["state"] == "ok", got["answer"]
    return got


class TestACountIsDrawnOverTheWindowItCounts:
    def test_r1_s_lines_of_22_oct_are_drawn_over_22_oct(self, web):
        got = _week_of_days(web)
        p = got["answer"]["payload"]
        assert p["window_close"] is True and p["step"] == DAY
        drawn = _panels(f"window.NMAS_PANELS.drawnData({json.dumps(p)})")
        times, counts = drawn[0], drawn[1]
        i = counts.index(3)
        # uPlot's stepped path (align 1) holds a point's value from its time to the next one.
        assert times[i] <= EVENTS[0] < times[i + 1] and times[i] <= EVENTS[-1] < times[i + 1], \
            (Q._utc(times[i]), Q._utc(times[i + 1]))
        assert (Q._utc(times[i]), Q._utc(times[i + 1])) == ("22 Oct 00:00", "23 Oct 00:00")
        assert sum(counts[:-1]) == 3, "a count drawn twice, or the closing point counted"

    def test_the_last_window_is_drawn_to_its_close_and_the_pointer_reads_its_own_window(self):
        got = _panels("var P = window.NMAS_PANELS; var d = P.windowData([[200, 300], [4, 7]], 100);"
                      "[d, P.windowIdx(d[0], 150), P.windowIdx(d[0], 250), P.windowIdx(d[0], 300)]")
        assert got[0] == [[100, 200, 300], [4, 7, 7]]
        assert got[1:] == [0, 1, 1], "a pointer is read as the window it is in, never the close"

    def test_the_title_spans_the_whole_windows_and_a_day_s_window_names_both_dates(self, web):
        got = _week_of_days(web)
        a = got["answer"]
        # Points 21 Oct to 26 Oct 00:00 close the six whole days from 20 Oct: the title is the
        # range's, never the last series' last line (it read "to 23 Oct" from r1's).
        assert got["answer_span"] == (WALK_NOW // DAY * DAY - 6 * DAY, WALK_NOW // DAY * DAY)
        assert got["answer_title"].endswith(", 20 Oct 00:00 to 26 Oct 00:00 UTC"), \
            got["answer_title"]
        assert a["series"][0]["last_words"] == "22 Oct 00:00 to 23 Oct 00:00 UTC"
        assert Q.history_ask.span(EVENTS[0], EVENTS[-1]) == "22 Oct 13:00 to 14:00"

    def test_the_page_draws_the_window_r1_s_lines_were_counted_in(self, web, monkeypatch):
        loki = EventLoki()
        monkeypatch.setattr("modules.history_logq._client", lambda list_name, wait=65.0: loki)
        monkeypatch.setattr("modules.history_logq._now", lambda: WALK_NOW)
        html = _page(web, show="counts", every="1d", range="7d", ask="1")
        assert re.search(r'<td><time datetime="2026-10-22T00:00:00Z" data-lq-to="2026-10-23T'
                         r'00:00:00Z" data-lq-when="span">22 Oct 00:00 to 23 Oct 00:00 UTC</time>'
                         r'</td>', html), "the legend's last window"


class TestOneZonePerView:
    def test_every_time_in_an_answer_is_one_the_script_writes_in_the_viewer_s_zone(self, web):
        html = _page(web, ask="1", range="1h")
        top = re.search(r'<div class="lq-top">(.*?)</div>', html, re.S).group(1)
        assert "UTC" not in re.sub(r"<time [^>]*>[^<]*</time>|title=\"[^\"]*\"", "", top), \
            "a time written outside a <time> the script redraws"
        assert re.search(r'<strong title="The lines, every device, \d+ Oct \d\d:\d\d to '
                         r'\d\d:\d\d UTC">', top), "the title's UTC words are its hover"
        assert '<th scope="col">Time (<span class="lq-zone" data-lq-zone>UTC</span>)</th>' in html
        assert re.search(r'<td class="lq-nw mono"><time datetime="[0-9T:-]+Z" '
                         r'data-lq-when="dts" data-lq-bare>\d+ Oct \d\d:\d\d:\d\d</time>', html)

    def test_the_words_in_a_zone_six_hours_west(self):
        got = _panels("var P = window.NMAS_PANELS, L = window.NMAS_LOGQ;"
                      "var west = function () { return -360; }, z = function () { return 'MDT'; };"
                      "[P.whenWords(1792627200, -360, 'dt'), P.whenWords(1792627200, 0, 't'),"
                      " P.spanWords(1792627200, 1792713600, -360, -360),"
                      " P.spanWords(1792656000, 1792659600, -360, -360),"
                      " L.timeText('span', 1792627200, 1792713600, west, z, false),"
                      " L.timeText('dts', 1792674005, 0, west, z, true),"
                      " P.tipWhen(1792627200, {stepped: true, window_close: true, step: 86400},"
                      "           west, z),"
                      " P.tipWhen(1792627200, {hover_utc: true}, west, z),"
                      " L.pickWords('device=\"r1\"', 1792627200, 1792713600, 3, west, z),"
                      " P.offsetWords(-360), P.offsetWords(330), P.offsetWords(0)]")
        assert got == ["21 Oct 18:00", "00:00", "21 Oct 18:00 to 22 Oct 18:00",
                       "22 Oct 02:00 to 03:00", "21 Oct 18:00 to 22 Oct 18:00 MDT",
                       "22 Oct 07:00:05",
                       ["21 Oct 18:00 to 22 Oct 18:00 MDT", "22 Oct 00:00 to 23 Oct 00:00 UTC"],
                       ["21 Oct 18:00 MDT", "22 Oct 00:00 UTC"],
                       'device="r1" · 21 Oct 18:00 to 22 Oct 18:00 MDT · 3 lines in this window',
                       "UTC\u22126", "UTC+5:30", "UTC"]

    def test_a_panel_outside_history_keeps_its_one_line(self):
        got = _panels("window.NMAS_PANELS.tipWhen(1792627200, {}, function () { return -360; },"
                      " function () { return 'MDT'; })")
        assert got[1] is None


class TestFiltersThatCannotMatchTogether:
    def test_a_mnemonic_chosen_and_another_typed_into_text(self):
        spec, _e = Q.ask({"mn": ["%LINK-3-UPDOWN"], "has": "OSPF-5-ADJCHG"})
        (words, fixes), = Q.clashes(spec)
        assert "LINK-3-UPDOWN" in words and "OSPF-5-ADJCHG" in words
        assert fixes[0] == ("Drop LINK-3-UPDOWN", {"mn": [], "hl": "mn"}), "the leftover first"
        spec, _e = Q.ask({"mn": ["%LINK-3-UPDOWN"], "has": "OSPF-5-ADJCHG", "hl": "mn"})
        assert Q.clashes(spec)[0][1][0][1] == {"has": "", "hl": "has"}, \
            "the mnemonic chosen last: the text is the leftover"

    def test_what_can_match_together_is_not_warned(self):
        for values in ({"mn": ["%OSPF-5-ADJCHG"], "has": "OSPF-5-ADJCHG"},
                       {"mn": ["%OSPF-5-ADJCHG"], "has": "Neighbor Down"},
                       {"has": "OSPF-5-ADJCHG"}, {"mn": ["%OSPF-5-ADJCHG"], "sev": "5"},
                       {"mn": ["%OSPF-5-ADJCHG", "%LINK-3-UPDOWN"], "sev": "3"},
                       {"has": "Down", "not": "Up"}):
            spec, _e = Q.ask(values)
            assert Q.clashes(spec) == [], values

    def test_a_severity_every_mnemonic_is_milder_than_and_text_excluded_by_its_own(self):
        spec, _e = Q.ask({"mn": ["%OSPF-5-ADJCHG"], "sev": "3"})
        (words, fixes), = Q.clashes(spec)
        assert "severity 5" in words and [f[0] for f in fixes] == ["Drop OSPF-5-ADJCHG",
                                                                   "Any severity"]
        spec, _e = Q.ask({"has": "Neighbor Down", "not": "Down"})
        assert Q.clashes(spec)[0][1] == [("Drop the excluded text \u201cDown\u201d",
                                          {"not": "", "hl": "not"})]

    def test_the_page_warns_with_the_one_click_that_drops_the_leftover(self, web):
        html = _page(web, mn="%LINK-3-UPDOWN", has="OSPF-5-ADJCHG", show="counts")
        box = html[html.index("cannot match together"):]
        href = re.search(r'<a class="btn btn-small btn-primary" href="([^"]+)"', box).group(1)
        assert "has=OSPF-5-ADJCHG" in href and "mn=" not in href, href
        assert "Drop LINK-3-UPDOWN</a>" in box


class TestScopeFirst:
    """The builder's order by dependency (the operator's design note, 2026-10-26): Range, Kind
    and Devices, then what is read over them; a choice the scope no longer holds is kept and
    marked, never dropped."""

    def test_the_rows_run_range_kind_devices_then_the_choices(self, web):
        html = _page(web)
        rows = re.findall(r'<div class="lq-row(?: lq-acts)?"><(?:span|label)[^>]*class="lq-lab"'
                          r'[^>]*>([^<]*)<', html)
        assert [r for r in rows if r] == ["Start from", "Range", "Kind", "Devices", "Severity",
                                          "Mnemonic", "Text", "Show", "The query"], rows

    def test_a_kind_and_a_device_the_range_does_not_hold_are_kept_and_marked(self, web):
        html = _page(web, job="no-such-kind", dev="r99")
        assert re.search(r'>no-such-kind ×</a>', html) and re.search(
            r'>r99 ×</a><span class="lq-unseen">not seen in this range</span>', html)
        assert 'name="job" value="no-such-kind"' in html and 'name="dev" value="r99"' in html

    def test_the_devices_are_read_for_the_kinds_chosen(self, web):
        _page(web, job="snmptrapd")
        got = [p for path, p in web.asked if path.endswith("/label/device/values")]
        assert got and got[-1].get("query") == '{job="snmptrapd"}', got
        web.asked.clear()
        _page(web)
        got = [p for path, p in web.asked if path.endswith("/label/device/values")]
        assert got and "query" not in got[-1], "every kind: no narrowing"


def _re2_as_python(pat):
    """An RE2 pattern the builder writes, as Python's re reads it: RE2's \\x{HH} is Python's
    \\xHH; the flag and the escapes `literal` writes read the same in both."""
    return re.sub(r"\\x\{([0-9a-f]{2})\}", lambda m: "\\x" + m.group(1), pat)


class TestAnyCase:
    """C1834 (the operator's order, 2026-10-26): Loki's |= is case-sensitive, so the Text
    filter gains a choice, "any case" (the address's `anycase`): on, the text is matched in any
    case by RE2's flag before the text written as a literal; off (the default), exactly as
    written, as before. Each query is read back by the independent Go-string reader above."""

    RNG = {"start": NOW - 86400, "end": NOW, "seconds": 86400, "words": "the last 24 h"}
    DISC = {"labels": ["device", "job"], "since": {"device": 0}}

    def _built(self, **values):
        spec, errors = Q.ask(values)
        assert not errors, errors
        return Q.build(spec, self.DISC, self.RNG, spec["dev"])

    def test_off_the_text_is_matched_exactly_as_written(self):
        b = self._built(has="Down")
        strings, outside = tokens(b["log_query"])
        assert outside == '{job=~"_"} |= "_" !~ "_"', outside
        assert strings[1] == "Down"
        assert b["explain"]["has"] == 'keeps the lines containing "Down", exactly as written'
        assert 'containing "Down", newest' in b["reads"] and "any case" not in b["reads"]

    def test_on_the_text_is_matched_in_any_case(self):
        b = self._built(has="down", anycase="1")
        strings, outside = tokens(b["log_query"])
        assert outside == '{job=~"_"} |~ "_" !~ "_"', outside
        assert strings[1] == "(?i)down", strings
        pat = _re2_as_python(strings[1])
        for line in ("Neighbor 192.0.2.2 Down", "from FULL to DOWN", "changed state to down"):
            assert re.search(pat, line), line
        assert not re.search(pat, "changed state to up")
        assert b["explain"]["has"] == 'keeps the lines containing "down", in any case'
        assert 'containing "down", in any case, newest' in b["reads"], b["reads"]

    @pytest.mark.parametrize("text", ["a.b*(c)+?", "[x]{2}^$|y", 'say "hi" \\ there',
                                      "tab\there", "(?-i)Down"])
    def test_a_text_holding_regex_characters_matches_only_itself_in_any_case(self, text):
        b = self._built(has=text, anycase="1")
        strings, _outside = tokens(b["log_query"])
        assert strings[1] == "(?i)" + Q.literal(text), strings[1]
        pat = _re2_as_python(strings[1])
        assert re.fullmatch(pat, text, re.S) and re.fullmatch(pat, text.swapcase(), re.S)
        # Every metacharacter is itself: what the text would match read as RE2 is not matched.
        assert not re.fullmatch(pat, text + "x", re.S)
        if "." in text:
            assert not re.fullmatch(pat, text.replace(".", "X"), re.S)

    def test_the_choice_is_carried_only_as_one(self):
        _spec, errors = Q.ask({"has": "down", "anycase": "yes"})
        assert errors == ["'yes' is not the any-case choice (1, or none)"], errors
        spec, _e = Q.ask({"has": "down", "anycase": "yes"})
        assert spec["anycase"] == "" and "|= " in Q.build(spec, self.DISC, self.RNG,
                                                         [])["log_query"]
        assert "anycase" in Q.ADDRESS_KEYS and "anycase" in Q.FILTERS
        assert Q.DEFAULTS["anycase"] == "", "off by default: the builder as it was"
        assert Q.qs(Q.ask({"has": "down"})[0]) == "?has=down"
        assert Q.qs(Q.ask({"has": "down", "anycase": "1"})[0]) == "?has=down&anycase=1"

    def test_the_page_draws_the_choice_beside_contains_and_asks_with_it(self, web):
        html = _page(web, has="Neighbor")
        box = re.search(r'<input id="lq-anycase"[^>]*>', html).group(0)
        assert 'type="checkbox"' in box and 'name="anycase"' in box and 'value="1"' in box
        assert 'form="lq-form"' in box and "checked" not in box
        assert html.index('id="lq-has"') < html.index('id="lq-anycase"') < \
            html.index('id="lq-not"'), "beside contains"
        assert '|= "Neighbor"' in html
        web.asked.clear()
        html = _page(web, ask="1", has="neighbor", anycase="1", range="1h", hl="has")
        box = re.search(r'<input id="lq-anycase"[^>]*>', html).group(0)
        assert " checked" in box
        assert 'keeps the lines containing "neighbor", in any case' in html
        asked = [p["query"] for p in _logs_asked(web)]
        assert asked and '|~ "(?i)neighbor" !~ ' in asked[-1] and "|= " not in asked[-1], asked
        # Carried once: the checkbox is the lq-form's own, never a hidden copy beside it.
        form = re.search(r'<form id="lq-form".*?</form>', html, re.S).group(0)
        assert 'name="anycase"' not in form

    def test_an_empty_answer_says_the_text_was_matched_in_any_case(self, web):
        web.loki.empty = True
        html = unescape(_page(web, ask="1", has="neighbor", anycase="1", range="1h"))
        assert "No line contains “neighbor”, in any case: this may not match" in html

    def test_an_excluded_text_a_text_in_any_case_need_not_hold_is_no_clash(self):
        spec, _e = Q.ask({"has": "neighbor down", "anycase": "1", "not": "down"})
        assert Q.clashes(spec) == [], "a line holding NEIGHBOR DOWN passes both"
        spec, _e = Q.ask({"has": "neighbor 192.0.2.7", "anycase": "1", "not": "192.0.2.7"})
        assert Q.clashes(spec), "digits have no case: every line holding the text holds it"
        spec, _e = Q.ask({"mn": ["%LINK-3-UPDOWN"], "has": "ospf-5-adjchg", "anycase": "1"})
        (words, _fixes), = Q.clashes(spec)
        assert "name different mnemonics" in words
