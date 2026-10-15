"""History › Query › Ask your own, the metrics builder (board E3, QueryBuilderMetrics3; approved
by the operator 2026-10-15; modules/history_promq.py, templates/v2/_history_ask_metrics.html).

Fed by real captures of the lab's Prometheus (tests/fixtures/prometheus/ask_*.json, read-only on
2026-10-15 09:47 to 09:50 UTC, instance addresses mapped into 192.0.2.0/24, and the earlier
status_config.json), asked through a stand-in for the Prometheus integration client that answers
as Prometheus did, evaluating a selector's matchers against the captured series' labels:

- ONE TOKEN EACH: a device, a role, an interface or a filter's value with a quote, a backslash,
  `}`, `{`, `|`, `=~` or a newline reaches Prometheus only inside one string token that reads
  back as itself (Go's string rules, F3's independent reader), several values an alternation of
  literals; a metric or label NAME Prometheus does not hold is refused by name, never asked;
- DISCOVERED: the metrics, their help and type, the devices, roles, interfaces and labels the
  builder offers are Prometheus's answers (renamed in a copy of the capture, the page follows);
  the counter rule from Prometheus's metadata; the bounds from its flags and configuration;
- the answer: each series' value now, highest and lowest summed here from the capture, the 20
  highest drawn and the rest counted; a bound passed refused naming both operands with nothing
  asked of the range; Prometheus not answering "Couldn't load" in place; no samples said
  against what Prometheus keeps;
- a read: nothing is written, and the region pushes the page's own address.
"""

import copy
import json
import math
import os
import re
from html import unescape

import pytest

from modules import history_promq as P
from tests.test_history_ask_logs import FakeLoki, go_unquote, tokens

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROM = os.path.join(ROOT, "tests", "fixtures", "prometheus")


def _fx(name):
    with open(os.path.join(PROM, name), encoding="utf-8") as fh:
        return json.load(fh)


FLAGS = _fx("ask_flags.json")["answer"]
NAMES = _fx("ask_names.json")["answer"]
META = _fx("ask_metadata.json")["answer"]
LABELS = _fx("ask_labels.json")
ROLE = _fx("ask_range_role.json")
PER_IF = _fx("ask_range_per_interface.json")
CONFIG = _fx("status_config.json")
#: The read: the end of the per-interface capture (a whole minute).
NOW = PER_IF["end"]
#: The board's question, as the builder forms it, and its range (the role capture's).
BOARD = {"m": "ifHCInOctets", "f": ["ifDescr != Null0"], "op": ["rate:5m", "bits", "sum:role"],
         "range": "custom", "from": "2026-10-12 06:00", "to": "2026-10-15 06:00"}
#: The captured series of ifHCInOctets: each one's labels (the stand-in matches selectors on
#: them, as Prometheus does).
SERIES = [dict(r["metric"], __name__="ifHCInOctets") for r in PER_IF["answer"]["data"]["result"]]


# ---------------------------------------------------------------------------- a stand-in

class _Resp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def matchers(text):
    """``[(label, op, value)]`` of a selector's braces, each value read with Go's rules."""
    out, i = [], 0
    while i < len(text):
        m = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(=~|!~|!=|=)\s*").match(text, i)
        if not m:
            raise AssertionError(f"not a matcher at {text[i:i + 30]!r}")
        value, i = go_unquote(text, m.end())
        out.append((m.group(1), m.group(2), value))
        i = re.compile(r"\s*,?\s*").match(text, i).end()
    return out


def selected(expr):
    """The captured series the (first) selector in *expr* picks, as Prometheus would."""
    m = re.search(r"([A-Za-z_:][A-Za-z0-9_:]*)\{", expr)
    if m:
        start = m.end()
        depth, i = 1, start
        while depth:                                    # to the selector's closing brace
            if expr[i] == '"':
                _v, i = go_unquote(expr, i)
                continue
            depth += {"{": 1, "}": -1}.get(expr[i], 0)
            i += 1
        name, ms = m.group(1), matchers(expr[start:i - 1])
    else:
        name, ms = re.search(r"([A-Za-z_:][A-Za-z0-9_:]*)", expr.split("(")[-1]).group(1), []
    out = []
    for s in SERIES:
        if s["__name__"] != name:
            continue
        ok = True
        for label, op, value in ms:
            have = s.get(label, "")
            hit = re.fullmatch(value, have, re.S) is not None if "~" in op else have == value
            ok &= hit if op in ("=", "=~") else not hit
        if ok:
            out.append(s)
    return out


class FakeProm:
    """Answers as the lab's Prometheus did on 2026-10-15 (the captures), and records each ask."""

    def __init__(self):
        self.asked, self.timeout = [], 125.0
        self.names, self.flags, self.config = copy.deepcopy(NAMES), copy.deepcopy(FLAGS), \
            copy.deepcopy(CONFIG)
        self.fail, self.empty = "", False

    def is_configured(self):
        return True

    def _ok(self, body):
        return {"ok": True, "status": 200, "response": _Resp(body)}

    def _get(self, path, **params):
        self.asked.append((path, params))
        q = params.get("query", "")
        if self.fail and path.startswith("api/v1/query"):
            return {"ok": False, "error": self.fail}
        if path == "api/v1/status/flags":
            return self._ok(self.flags)
        if path == "api/v1/status/config":
            return self._ok(self.config)
        if path == "api/v1/label/__name__/values":
            return self._ok(self.names)
        if path == "api/v1/metadata":
            return self._ok(META)
        if path in ("api/v1/labels",) or path.startswith("api/v1/label/"):
            metric, _end = go_unquote(params["match[]"], len("{__name__="))
            if path == "api/v1/labels":
                got = LABELS["labels"].get(metric) or {"status": "success", "data": []}
                return self._ok(got)
            label = path.split("/")[3]
            got = (LABELS["values"].get(metric) or {}).get(label)
            if got is None:                            # the same metric's captured series
                vals = sorted({s[label] for s in SERIES if s["__name__"] == metric and label in s})
                got = {"status": "success", "data": vals}
            return self._ok(got)
        if '=~"("' in q:
            bad = LABELS["bad_regex"]["answer"]
            return {"ok": False, "error": "HTTP 400", "status": 400, "detail": bad["error"]}
        if path == "api/v1/query":
            inner = re.fullmatch(r"count\((.*)\)", q, re.S).group(1)
            if inner == ROLE["query"]:
                n = len(ROLE["answer"]["data"]["result"])
            else:
                picked = selected(inner)
                by = re.match(r"\w+ by \((\w+)\) \(", inner)
                n = len({s.get(by.group(1)) for s in picked}) if by else len(picked)
                top = re.match(r"topk\((\d+), ", inner)
                n = min(n, int(top.group(1))) if top else n
            res = [{"metric": {}, "value": [NOW, str(n)]}] if n else []
            return self._ok({"status": "success", "data": {"resultType": "vector",
                                                           "result": res}})
        if path == "api/v1/query_range":
            if self.empty:
                return self._ok(LABELS["empty"]["answer"])
            for cap in (ROLE, PER_IF):
                if q == cap["query"]:
                    return self._ok(copy.deepcopy(cap["answer"]))
            return {"ok": False, "error": "HTTP 422", "status": 422,
                    "detail": f"the stand-in holds no capture for {q}"}
        raise AssertionError(f"the stand-in was asked {path}")


@pytest.fixture
def web(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tests import test_logs_v2 as T

    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.readers.adjacencies.lists",
                        lambda: [("Lab", SimpleNamespace(repo_dir=str(tmp_path)), T.MANAGED)])
    monkeypatch.setattr("modules.history_promq._now", lambda: NOW)
    prom = FakeProm()
    monkeypatch.setattr("modules.history_promq._client", lambda list_name, wait=125.0: prom)
    loki = FakeLoki()
    monkeypatch.setattr("modules.history_logq._client", lambda list_name, wait=65.0: loki)
    P.forget()
    from modules import history_logq
    history_logq.forget()
    import app as A
    client = A.app.test_client()
    client.prom = prom
    client.asked = prom.asked
    yield client
    P.forget()
    history_logq.forget()


def _page(web, **qs):
    qs.setdefault("list", "Lab")
    r = web.get("/v2/history/query/ask/metrics", query_string=qs)
    assert r.status_code == 200, r.status_code
    return unescape(r.get_data(as_text=True))


def _ranges(web):
    return [p for path, p in web.asked if path == "api/v1/query_range"]


# ---------------------------------------------------------------------------- one token each

HOSTILE = ['say "hi"', "back\\slash", "brace} {job=~\".+\"}", "pipe | or", "new\nline\r\tend",
           '"} or vector(1) # x', "\\\"", "\x00\x1f\x7f", "=~", "{", "}", "a=~b|c"]


def _spec(**over):
    spec, errors = P.ask(dict(BOARD, **over))
    assert not errors, errors
    return spec


class TestOneTokenEach:
    @pytest.mark.parametrize("value", HOSTILE)
    def test_a_value_in_every_place_reads_back_as_itself(self, value):
        spec = _spec(dev=[value], role=value, **{"if": [value]},
                     f=[f"ifAlias = {value}", f"ifName !~ {value}"])
        built = P.build(spec, "counter", "bytes", "ifDescr", spec["op"])
        strings, outside = tokens(built["query"])
        assert outside == ('sum by (role) (rate(ifHCInOctets{device="_", role="_", '
                           'ifDescr="_", ifAlias="_", ifName!~"_"}[5m]) * 8)'), outside
        assert strings == [value] * 5
        assert "\n" not in built["query"] and "\r" not in built["query"]

    def test_several_values_are_one_alternation_of_literals(self):
        spec = _spec(dev=['r1"}', "s1|s2", "x.*"])
        strings, outside = tokens(P.build(spec, "counter", "bytes", "", spec["op"])["query"])
        assert outside.startswith('sum by (role) (rate(ifHCInOctets{device=~"_", ')
        pat = strings[0]
        for v in ('r1"}', "s1|s2", "x.*"):
            assert re.fullmatch(pat, v)
        for v in ("s1", "s2", "xyz", "r1"):
            assert not re.fullmatch(pat, v), v

    def test_a_pattern_typed_for_a_match_is_one_string_kept_a_pattern(self):
        spec = _spec(f=['ifDescr !~ Loopback.*"} or {a="b'])
        strings, outside = tokens(P.build(spec, "counter", "bytes", "", spec["op"])["query"])
        assert outside == 'sum by (role) (rate(ifHCInOctets{ifDescr!~"_"}[5m]) * 8)'
        assert strings == ['Loopback.*"} or {a="b']

    def test_a_filter_s_operator_is_never_read_from_its_value(self):
        assert P.parse_filter("ifDescr = ~x") == ("ifDescr", "=", "~x")
        assert P.parse_filter("ifDescr =~ x") == ("ifDescr", "=~", "x")
        assert P.parse_filter("ifDescr = =x") == ("ifDescr", "=", "=x")
        assert P.parse_filter('a"b = x') is None and P.parse_filter("ifDescr==x") is None

    def test_names_prometheus_does_not_hold_are_refused_and_never_asked(self, web):
        html = _page(web, m='ifHCInOctets) or vector(1', ask="1")
        assert "is not a metric name" in html
        html = _page(web, m="noSuchMetric", ask="1")
        assert "Prometheus holds no metric &#39;noSuchMetric&#39;" in html or \
            "Prometheus holds no metric 'noSuchMetric'" in html
        html = _page(web, m="ifHCInOctets", f=["notalabel = y", 'a{b} = c'],
                     op=["rate:5m", "sum:notalabel", "sum:x) or (y"], ask="1")
        assert "carries no label &#39;notalabel&#39;" in html or \
            "carries no label 'notalabel'" in html
        assert "is not a filter" in html and "is not an operation" in html
        assert "hold no label 'notalabel'" in html
        asked = " ".join(p.get("query", "") + p.get("match[]", "") for _path, p in web.asked)
        assert "noSuchMetric" not in asked and "notalabel" not in asked and "vector(1" not in asked
        assert not _ranges(web)

    def test_a_hostile_filter_through_the_page_reaches_prometheus_as_one_token(self, web):
        evil = '"} or vector(1) or {a="'
        _page(web, m="ifHCInOctets", f=[f"ifDescr = {evil}"], op=["rate:5m"], ask="1")
        counts = [p["query"] for path, p in web.asked if path == "api/v1/query"]
        assert counts
        for q in counts:
            strings, outside = tokens(q)
            assert evil in strings and "vector(1)" not in outside, outside


# ---------------------------------------------------------------------------- discovered

class TestDiscovered:
    def test_the_metrics_offered_are_prometheus_s_with_their_help(self, web):
        html = _page(web, mq="octets")
        assert "ifHCInOctets</span> The total number of octets received on the interface" in html
        assert "1.3.6.1.2.1" not in html.split('class="pq-pick"')[1].split("</div>")[0]
        assert f"{len(NAMES['data']):,} over the last 24 h" in html
        assert "counter · bytes" in html

    def test_renamed_in_the_capture_the_page_follows(self, web):
        web.prom.names = {"status": "success", "data": ["alpha_total", "beta"]}
        html = _page(web)
        assert "alpha_total" in html and "ifHCInOctets" not in html.split('id="pq-mq"')[1]
        assert "2 over the last 24 h" in html
        # A Start-from chip whose metric Prometheus does not hold is no link.
        assert re.search(r'<span class="lq-chip pq-off"[^>]*title="Prometheus holds no '
                         r'ifHCInOctets[^"]*">Bytes in, per role</span>', html)

    def test_devices_roles_and_interfaces_are_the_label_values(self, web):
        html = _page(web, m="ifHCInOctets")
        vals = LABELS["values"]["ifHCInOctets"]
        assert f"all {len(vals['device']['data'])}" in html
        for role in vals["role"]["data"]:
            assert f"by role: {role}</a>" in html
        descr = vals["ifDescr"]["data"]
        for i in descr[:3]:
            assert f">{i}</a>" in html
        assert f"+ {len(descr) - 3} more" in html and "IF-MIB's <span class=\"mono\">ifDescr" in html

    def test_the_labels_are_asked_for_the_metric_over_the_range(self, web):
        _page(web, m="ifHCInOctets", range="7d")
        got = [p for path, p in web.asked if path == "api/v1/labels"]
        assert got and got[0]["match[]"] == '{__name__="ifHCInOctets"}'
        assert int(got[0]["end"]) - int(got[0]["start"]) == 7 * 86400

    def test_the_bounds_are_prometheus_s_own_read_from_its_flags(self, web):
        html = _page(web, m="ifHCInOctets")
        assert "keeps 90 days at full detail" in html and "retention.time 90d" in html
        assert "capped at 100GiB" in html and "stops at 2 min" in html
        assert "50,000,000 samples" in html
        assert "max_query_length 30d1h" in html, "the logs builder's row, from Loki's /config"
        web.prom.flags = copy.deepcopy(FLAGS)
        web.prom.flags["data"]["storage.tsdb.retention.time"] = "15d"
        P.forget()
        assert "keeps 15 days at full detail" in _page(web, m="ifHCInOctets")

    def test_the_counter_rule_is_prometheus_s_metadata(self, web):
        q = P.view("Lab", {"m": "ifHCInOctets"}, now=NOW, client=web.prom)
        assert q["kind"] == "counter" and q["built"]["query"] == "rate(ifHCInOctets[5m])"
        assert "is a counter (Prometheus's metadata says so)" in q["notes"][0]
        g = P.view("Lab", {"m": "cpmCPUTotal5minRev", "op": ["rate:5m", "max:device"]}, now=NOW,
                   client=web.prom)
        assert g["kind"] == "gauge" and g["built"]["query"] == "max by (device) (cpmCPUTotal5minRev)"
        assert any("is a gauge" in e for e in g["errors"])

    def test_the_unit_follows_the_chain(self, web):
        q = P.view("Lab", BOARD, now=NOW, client=web.prom)
        assert q["unit"] == "bytes" and "octet" in q["unit_where"]
        assert q["built"]["unit_words"] == "bits per second" and q["built"]["chart_unit"] == "bps"
        g = P.view("Lab", {"m": "cpmCPUTotal5minRev", "op": ["bits"]}, now=NOW, client=web.prom)
        assert any("not counted in bytes" in e for e in g["errors"])


# ---------------------------------------------------------------------------- the answer

def _si(v, suffix):
    """The value as the chart writes it, written here from its rules (nmas_panels.js): three
    significant figures at most, an SI prefix past a thousand."""
    for size, prefix in ((1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k")):
        if abs(v) >= size:
            v, unit = v / size, f" {prefix}{suffix}"
            break
    else:
        unit = f" {suffix}"
    a = abs(v)
    n = round(v) if a >= 100 else math.floor(v * 10 + 0.5) / 10 if a >= 10 else \
        math.floor(v * 100 + 0.5) / 100
    text = f"{n:.2f}".rstrip("0").rstrip(".") if a < 100 else str(int(n))
    return text + unit


class TestTheAnswer:
    def test_the_board_s_question_now_highest_and_lowest_from_the_capture(self, web):
        html = _page(web, ask="1", **BOARD)
        asked = _ranges(web)
        assert len(asked) == 1 and asked[0]["query"] == ROLE["query"]
        assert asked[0]["step"] == "300" and int(asked[0]["start"]) == ROLE["start"]
        for row in ROLE["answer"]["data"]["result"]:
            vals = [float(v) for _t, v in row["values"]]
            role = row["metric"]["role"]
            cells = re.search(rf'role=&quot;{role}&quot;|role="{role}"</span></td>(.*?)</tr>',
                              html, re.S).group(1)
            for v in (vals[-1], max(vals), min(vals)):
                assert _si(v, "b/s") in cells, (role, _si(v, "b/s"), cells)
        assert "2 series · answered in" in html and "Now (06:00 UTC)" in html
        assert "Bytes in per role, in bits per second, 12 Oct 06:00 to 15 Oct 06:00 UTC" in html

    def test_the_chart_payload_is_the_answer_in_its_unit(self, web):
        q = P.view("Lab", dict(BOARD, ask="1"), now=NOW, client=web.prom)
        p = q["answer"]["payload"]
        assert p["legend_off"] and p["unit"] == "bps" and p["step"] == 300
        assert len(p["series"]) == 2 and len(p["series"][0]["times"]) == 865

    def test_the_twenty_highest_are_drawn_and_the_rest_counted(self, web):
        q = P.view("Lab", {"m": "ifHCInOctets", "op": ["rate:5m", "bits"], "range": "custom",
                           "within": "15 minutes", "ask": "1"}, now=NOW, client=web.prom)
        a = q["answer"]
        result = PER_IF["answer"]["data"]["result"]
        highs = sorted((max(float(v) for _t, v in r["values"]) for r in result), reverse=True)
        assert a["series_total"] == len(result) and len(a["series"]) == 20
        assert [s["high"] for s in a["series"]] == highs[:20]
        html = _page(web, m="ifHCInOctets", op=["rate:5m", "bits"], range="custom",
                     within="15 minutes", ask="1")
        assert f"{len(result)} series answer: the 20 highest in range are drawn; the other " \
               f"{len(result) - 20} are counted, not drawn" in html

    def test_a_window_shorter_than_two_scrapes_is_refused_naming_both(self, web):
        yml = web.prom.config["data"]["yaml"].replace("scrape_interval: 30s", "scrape_interval: 1m")
        web.prom.config["data"]["yaml"] = yml
        html = _page(web, ask="1", **dict(BOARD, op=["rate:1m", "bits", "sum:role"]))
        assert "Refused: a rate needs two samples in each window, and the slowest job this " \
               "metric comes from is scraped every 1 min (its scrape_interval). A window of " \
               "1 min is shorter than two scrapes, 2 min." in html
        assert "Rate over 5 minutes" in html and not _ranges(web)

    def test_more_samples_than_prometheus_loads_is_refused_naming_both(self, web):
        web.prom.flags["data"]["query.max-samples"] = "10000"
        html = _page(web, ask="1", **BOARD)
        sel = len([s for s in SERIES if s["ifDescr"] != "Null0"])
        assert "Refused: one ask loads at most 10,000 samples (Prometheus&#39;s query.max-samples)" \
            in html or "Refused: one ask loads at most 10,000 samples (Prometheus's " \
            "query.max-samples)" in html
        assert f"({sel} series × 865 points" in html and not _ranges(web)

    def test_more_series_than_an_answer_holds_is_refused_naming_both(self, web, monkeypatch):
        monkeypatch.setattr("modules.panels.MAX_SERIES", 50)
        html = _page(web, m="ifHCInOctets", op=["rate:5m", "bits"], range="custom",
                     within="15 minutes", ask="1")
        assert "Refused: at most 50 series an answer (Mercury&#39;s bound)" in html or \
            "Refused: at most 50 series an answer (Mercury's bound)" in html
        assert f"This query answers {len(SERIES)} series at the range" in html
        assert "Only the top 10" in html and not _ranges(web)

    def test_prometheus_not_answering_is_couldn_t_load_in_place(self, web):
        web.prom.fail = "Timed out after 125.0s"
        html = _page(web, ask="1", **BOARD)
        assert "Couldn't load: Prometheus did not answer within 2 min (its query.timeout" in html
        assert "Nothing is drawn from an earlier answer" in html and "Ask again" in html
        assert "Prometheus not answering" in html

    def test_a_query_prometheus_refuses_is_said_in_its_own_words(self, web):
        html = _page(web, m="ifHCInOctets", f=["ifDescr =~ ("], ask="1")
        assert "Couldn't load: Prometheus refused the query: invalid parameter" in html
        assert "missing closing )" in html and ">Prometheus refused the query</span>" in html
        assert "Needs attention" not in html.split('id="lq-answer"')[1]

    def test_prometheus_s_own_words_travel_with_its_refusal(self, monkeypatch):
        """The integration client's one GET keeps the service's `error` when it refuses (its
        captured answer to a bad pattern, HTTP 400), so the page can say it."""
        from types import SimpleNamespace

        from modules.integrations.prometheus import PrometheusIntegration
        body = LABELS["bad_regex"]["answer"]
        answer = SimpleNamespace(status_code=LABELS["bad_regex"]["status"], json=lambda: body)
        c = PrometheusIntegration()
        monkeypatch.setattr(PrometheusIntegration, "url", "http://192.0.2.10:9090")
        monkeypatch.setattr(c, "session", lambda: SimpleNamespace(get=lambda *a, **k: answer))
        r = c._get("api/v1/query", query='count(ifHCInOctets{ifDescr=~"("})')
        assert not r["ok"] and r["status"] == 400 and r.get("detail") == body["error"]
        assert P._words(r, c) == f"Prometheus refused the query: {body['error']}"
        json.dumps(r)                                   # the result stays plain data

    def test_a_services_words_are_masked_on_the_way_out(self, monkeypatch):
        """A refusal's text can quote what it was sent; a credential in it leaves masked."""
        from types import SimpleNamespace

        from modules.integrations.prometheus import PrometheusIntegration
        planted = "snmp-server community PlantedC0mmunity0nTheWire RO"
        answer = SimpleNamespace(status_code=400, json=lambda: {"error": f"parse error: {planted}"})
        c = PrometheusIntegration()
        monkeypatch.setattr(PrometheusIntegration, "url", "http://192.0.2.10:9090")
        monkeypatch.setattr(c, "session", lambda: SimpleNamespace(get=lambda *a, **k: answer))
        r = c._get("api/v1/query", query="up")
        assert r["detail"].startswith("parse error: snmp-server community ")
        assert "PlantedC0mmunity0nTheWire" not in r["detail"]

    def test_no_samples_is_said_against_what_prometheus_keeps(self, web):
        web.prom.empty = True
        html = _page(web, ask="1", **dict(BOARD, **{"from": "2026-06-01 06:00",
                                                     "to": "2026-07-01 06:00"}))
        assert "No samples between 1 Jun 2026 06:00 and 1 Jul 2026 06:00 UTC" in html
        assert "Prometheus holds ifHCInOctets from 17 Jul 2026" in html and "(90 days)" in html
        assert "This is not the same as a zero." in html and "Start the range at 17 Jul" in html


# ---------------------------------------------------------------------------- the page

class TestThePage:
    def test_strict_policy_the_how_link_and_the_tab(self, web):
        from modules import csp
        r = web.get("/v2/history/query/ask/metrics?list=Lab")
        assert r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        html = r.get_data(as_text=True)
        assert 'data-manual="history#ask-metrics"' in html and "<script>" not in html
        assert 'aria-current="page">Query</a>' in html

    def test_the_region_pushes_the_page_s_own_address(self, web):
        r = web.get("/v2/history/query/ask/metrics/region",
                    query_string={"list": "Lab", "m": "ifHCInOctets", "ok1": "increase",
                                  "oa1": "1h", "ok2": "sum", "oa2": "role", "hl": "op2"},
                    headers={"HX-Request": "true"})
        assert r.status_code == 200
        push = r.headers["HX-Push-Url"]
        assert push.startswith("/v2/history/query/ask/metrics?list=Lab&m=ifHCInOctets")
        assert "op=increase%3A1h&op=sum%3Arole" in push and "ok1" not in push
        body = r.get_data(as_text=True)
        assert body.lstrip().startswith('<div id="lq"') and "<html" not in body

    def test_every_request_names_its_own_target(self, web):
        html = _page(web, ask="1", fe="1", fl="ifDescr", top="5", **BOARD)
        region = html[html.index('<div id="lq"'):]
        tags = re.findall(r"<(?:a|form|select|input|button)\b[^>]*\bhx-get=\"/v2/history/query/"
                          r"ask/metrics/region[^>]*>", region)
        assert len(tags) >= 30
        for tag in tags:
            assert 'hx-target="#lq"' in tag and 'hx-swap="outerHTML"' in tag, tag

    def test_the_last_choice_is_marked_and_said(self, web):
        html = _page(web, hl="op3", **BOARD)
        assert "<mark>sum by (role)</mark>" in html and "the last choice:" in html
        assert "adds up the series into one line per role" in html
        assert "The whole query reads: ifHCInOctets" in html and "in bits per second." in html

    def test_a_start_from_chip_sets_its_choices_and_is_marked(self, web):
        html = _page(web, **BOARD)
        assert re.search(r'class="lq-chip on"[^>]*aria-current="true">Bytes in, per role', html)

    def test_code_mode_takes_the_query_formed_and_its_builder_switch_comes_back(self, web):
        html = _page(web, **BOARD)
        assert "/v2/history/query/metric/ask?" in html and "lang=promql" in html
        code = web.get("/v2/history/query/metric/ask?list=Lab&lang=promql").get_data(as_text=True)
        assert 'href="/v2/history/query/ask/metrics"' in code and "lq-later" not in code

    def test_the_server_reads_nothing_the_page_cannot_send(self, web):
        """Every key the builder reads, some control on its page sends (a link's address, a
        field's name); the operations' selects send ok<i> and oa<i>."""
        html = _page(web, ask="1", fe="1", fl="ifDescr", fo="!~", fv="Loopback.*", top="5",
                     mq="octets", **dict(BOARD, op=["rate:5m", "bits", "sum:role", "ne:0"]))
        names = set(re.findall(r'\bname="([^"]+)"', html))
        for href in re.findall(r'(?:href|hx-get)="/v2/history/query/ask/metrics[^"?]*\?([^"]*)"',
                               html):
            names |= {kv.split("=", 1)[0] for kv in href.replace("&amp;", "&").split("&")}
        need = set(P.DEFAULTS) | {"ok1", "oa1", "ok2", "ok3", "oa3", "ok4", "oa4"}
        assert need <= names, sorted(need - names)

    def test_a_network_with_no_store_configured_is_drawn_saying_so(self, web, monkeypatch):
        """Both builders on a network with no Prometheus or Loki set: the page, saying so,
        never an error page (the logs builder's bounds line once read Loki's unread limits)."""
        class Unset(FakeProm):
            def is_configured(self):
                return False
        none = Unset()
        monkeypatch.setattr("modules.history_promq._client", lambda list_name, wait=0: none)
        monkeypatch.setattr("modules.history_logq._client", lambda list_name, wait=0: none)
        html = _page(web, ask="1", **BOARD)
        assert "No metrics store is configured for this network" in html
        assert "no log store is configured for this network" in html
        r = web.get("/v2/history/query/ask/logs?list=Lab&ask=1")
        assert r.status_code == 200, r.status_code
        body = r.get_data(as_text=True)
        assert "no log store is configured for this network" in body
        assert not none.asked

    def test_nothing_is_written(self, web):
        from modules import config
        before = sorted(os.listdir(config.DATA_DIR)) if os.path.isdir(config.DATA_DIR) else []
        _page(web, ask="1", **BOARD)
        _page(web, ask="1", m="ifHCInOctets", fe="1", fl="ifDescr", fo="=", fv="Vlan99")
        after = sorted(os.listdir(config.DATA_DIR)) if os.path.isdir(config.DATA_DIR) else []
        assert before == after

    def test_both_builders_views_can_be_saved_their_repeats_kept(self):
        from modules import saved_views
        got, err = saved_views.address("/v2/history/query/ask/metrics?list=Lab&m=ifHCInOctets"
                                       "&f=ifDescr+%21%3D+Null0&op=rate%3A5m&op=bits&ask=1")
        assert not err and got.count("op=") == 2 and "f=ifDescr" in got
        got, err = saved_views.address("/v2/history/query/ask/logs?list=Lab&dev=r1&dev=s1"
                                       "&show=counts&ask=1")
        assert not err and got.count("dev=") == 2, (got, err)
        _got, err = saved_views.address("/v2/history/query/ask/metrics?m=x&mq=octets")
        assert "does not read: mq" in err

    def test_the_saved_queries_beside_it_show_each_one_s_query(self, web, tmp_path):
        from modules import saved_views
        addr = "/v2/history/query/ask/metrics" + P.qs(P.ask(BOARD)[0], over={"ask": "1"})
        assert saved_views.save("Lab", "Bytes in per role, bits", addr, "operator")["ok"]
        html = _page(web)
        assert "Bytes in per role, bits" in html and ROLE["query"] in html and "Run ›" in html


# ---------------------------------------------------------------------------- in a browser

def test_the_builder_in_a_browser(web):  # noqa: F811
    """In a real browser at 1440: the chart draws from the answer the page holds; an operation's
    select redraws the region in place, pushes its address and drops the answer; Ask draws it
    again; From… to… says the local time beside a UTC time typed; nothing scrolls sideways, at
    1440 or at a phone's 390."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A

    url = "/v2/history/query/ask/metrics" + P.qs(P.ask(BOARD)[0], "Lab", {"ask": "1"})
    with browser.Served(A.app) as srv, browser.Browser() as b:
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
        b.go(srv.url(url))
        b.wait_for("return document.querySelector('.lq-panel .u-over')", 15)
        legend = b.js("return document.querySelectorAll('.pq-legend tbody tr').length")
        b.js("var s = document.querySelector('select[name=oa3]'); s.value = 'device';"
             "s.dispatchEvent(new Event('change', {bubbles: true})); return 1")
        b.wait_for("return location.search.indexOf('op=sum%3Adevice') >= 0"
                   " && !document.getElementById('lq-answer')", 10)
        marked = b.js("return document.querySelector('.lq-q mark').textContent")
        b.js("var d = document.querySelector('.lq-pickbox'); d.open = true;"
             "var i = document.getElementById('lq-from'); i.value = '2026-10-10 06:00';"
             "i.dispatchEvent(new Event('input', {bubbles: true})); return 1")
        local = b.js("return document.getElementById('lq-from-local').textContent")
        b.js("document.querySelector('[data-lq-close]').click(); return 1")
        wide = b.js("return document.documentElement.scrollWidth <= window.innerWidth")
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 390, "height": 900})
        b.go(srv.url(url))
        b.wait_for("return document.querySelector('.lq-panel .u-over')", 15)
        narrow = b.js("return document.documentElement.scrollWidth <= window.innerWidth + 1")
        b.go("about:blank")
    assert legend == 2 and marked.strip() == "sum by (device)", (legend, marked)
    assert re.fullmatch(r"UTC · \d\d:\d\d local \(UTC([+\u2212]\d+(:\d\d)?)?\)", local), local
    assert wide and narrow, (wide, narrow)
