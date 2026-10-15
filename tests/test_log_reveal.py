"""Reveal one log line (C818; board F3's Reveal…; the operator's decision 2026-10-15):
modules/log_reveal.py, the route `v2.history_ask_logs_reveal`, History's `log_reveals`.

Fed by the logs builder's stand-in for Loki (tests/test_history_ask_logs.py), answering with
the real capture of 2026-10-15 (ask_lines_labelled.json) with ONE PLANTED LINE: s4 logging an
SNMP community being set, the value `PLANTED`, which is in no capture. The stand-in answers a
reveal's read as Loki does: its label API's indexed names (the capture's), and a selector of
`label="value"` matchers, read with the independent Go-string reader, over [start, end).

- a line with a masked value offers Reveal… carrying its stream, its time and the digest of
  the masked line; a line with nothing masked offers none; the masked value is marked;
- a verified person with a reason sees the line, read from Loki AGAIN by stream and time, and
  the reveal is recorded BEFORE it is drawn, with who, when, which line and the reason, never
  the value; the answer announces `reveals`;
- refused, naming both operands, with nothing shown and nothing recorded: no person (a
  service, even one granted the operation), a reason too short, a line Loki no longer holds, a
  line whose masked form is not the one shown; a record that cannot be written shows nothing;
- History's timeline draws the record (who, the line, the reason) and never the value; an
  unreadable record is said.
"""

import copy
import json
import os
import re
from html import unescape
from types import SimpleNamespace

import pytest

from tests.test_history_ask_logs import LINES, go_unquote, web  # noqa: F401 (the fixture)
from tests.test_history_ask_logs import _Resp

#: The planted value (not in any capture).
PLANTED = "Pl4ntedC0mmunity"
REASON = "check the community this change set"


def _planted():
    """The lines capture with ONE PLANTED line in its first stream (s4's), its newest."""
    body = copy.deepcopy(LINES["answer"])
    first = body["data"]["result"][0]
    ns = str(int(first["values"][0][0]) + 1)
    first["values"].insert(0, [ns, (f"Oct 15 08:24:59 s4 3072: s4: *Oct 12 02:41:01.100: "
                                    f"%PARSER-5-CFGLOG_LOGGEDCMD: User:nmas  logged command:"
                                    f"snmp-server community {PLANTED} RO")])
    return body, ns


def _selector(q):
    """``{label: value}`` from a selector of ``label="value"`` matchers (Go strings)."""
    assert q.startswith("{") and q.endswith("}"), q
    out, i = {}, 1
    while i < len(q) - 1:
        m = re.compile(r"\s*([A-Za-z_]\w*)=").match(q, i)
        assert m, q[i:]
        value, i = go_unquote(q, m.end())
        out[m.group(1)] = value
        i += 2 if q[i:i + 2] == ", " else 0
    return out


def plant(loki):
    """The logs builder's stand-in *loki* holding the planted line and answering a reveal's
    read as Loki does; ``loki.reads`` are the reveal's reads. Returns the line's time (ns).
    (tests/test_board_shots.py shoots Reveal… with it.)"""
    body, ns = _planted()
    loki.reads, loki.body, orig = [], body, loki._get

    def _get(path, **p):
        q = p.get("query", "")
        if path.endswith("query_range") and p.get("direction") == "backward":
            loki.asked.append((path, p))
            body = copy.deepcopy(loki.body)
            if "!~ " in q:               # the heartbeat stage, as Loki applies it (F3's stand-in)
                from modules.device_logs import HEARTBEAT_LINE
                for s in body["data"]["result"]:
                    s["values"] = [v for v in s["values"] if not re.search(HEARTBEAT_LINE, v[1])]
            return {"ok": True, "response": _Resp(body)}
        if path.endswith("query_range") and p.get("direction") == "forward" \
                and not re.match(r"\{\w+=~", q):
            loki.reads.append((path, p))
            want, lo, hi = _selector(q), int(p["start"]), int(p["end"])
            res = []
            for s in loki.body["data"]["result"]:
                if all(s["stream"].get(k) == v for k, v in want.items()):
                    vals = [v for v in s["values"] if lo <= int(v[0]) < hi]
                    if vals:
                        res.append({"stream": s["stream"], "values": vals})
            return {"ok": True, "response": _Resp({"data": {"resultType": "streams",
                                                            "result": res}})}
        if path.endswith("/labels") and abs(int(p.get("start") or 0) - int(ns)) <= 2 * 10 ** 9:
            loki.reads.append((path, p))
        return orig(path, **p)

    loki._get = _get
    return ns


@pytest.fixture
def lab(web):  # noqa: F811
    """The builder's app with Loki holding the planted line."""
    from modules import history_logq
    ns = plant(web.loki)
    history_logq.forget()
    return SimpleNamespace(client=web, loki=web.loki, ns=ns)


def _lines(lab):
    r = lab.client.get("/v2/history/query/ask/logs", query_string={"list": "Lab", "range": "1h",
                                                                   "ask": "1"})
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _form(html, ns):
    """The Reveal… form the page drew for the line at *ns*: every field it can send."""
    at = html.index(f'name="ns" value="{ns}"')
    start = html.rindex('<form class="lq-pop lq-rvpop"', 0, at)
    m = re.match(r'<form class="lq-pop lq-rvpop"[^>]*>(.*?)</form>', html[start:], re.S)
    assert m, "no Reveal… form for the planted line"
    fields = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', m.group(1)))
    return {k: unescape(v) for k, v in fields.items()}


def _reveal(lab, **over):
    data = dict(_form(_lines(lab), lab.ns), reason=REASON)
    data.update(over)
    return lab.client.post("/v2/history/query/ask/logs/reveal", data=data)


@pytest.fixture
def audit(tmp_path, monkeypatch):
    """The reveal record in this test's own data folder."""
    data = tmp_path / "own-data"
    data.mkdir()
    monkeypatch.setattr("modules.config.DATA_DIR", str(data))
    return data / "reveal_audit.jsonl"


class TestTheLinesView:
    def test_a_masked_line_offers_reveal_and_a_clean_one_does_not(self, lab):
        html = _lines(lab)
        assert PLANTED not in html
        assert html.count("<summary class=\"btn btn-small\">Reveal…</summary>") == 1, \
            "only the planted line holds a masked value"
        f = _form(html, lab.ns)
        assert set(f) == {"list", "stream", "ns", "shown"}
        assert json.loads(f["stream"])["device"] == "s4" and f["ns"] == lab.ns
        assert re.fullmatch(r"[0-9a-f]{64}", f["shown"])
        assert ('<span class="lq-mask">&lt;redacted:snmp_community&gt;</span>' in html), \
            "the masked value is not marked"
        assert 'data-op="reveal-log-line"' in html and "/v2/help/reveal-log-line" in html

    def test_the_masked_parts_join_back_to_the_line(self):
        from routes.v2 import masked_parts
        line = "a <redacted:snmp_community> b <redacted:user_password>"
        parts = masked_parts(line)
        assert "".join(p for p, _m in parts) == line
        assert [p for p, m in parts if m] == ["<redacted:snmp_community>",
                                             "<redacted:user_password>"]
        assert masked_parts("") == [("", False)]


class TestARevealByAPerson:
    def test_the_line_is_read_again_recorded_first_and_drawn(self, lab, audit, monkeypatch):
        from modules import reveal_audit
        order, real = [], reveal_audit.record

        def record(**k):
            order.append(("record", len(lab.loki.reads)))
            return real(**k)
        monkeypatch.setattr(reveal_audit, "record", record)
        lab.loki.reads.clear()
        r = _reveal(lab)
        html = r.get_data(as_text=True)
        assert r.status_code == 200, html
        assert f"snmp-server community {PLANTED} RO" in unescape(html)
        assert "revealed to test-person@example.invalid" in html
        assert "reveals" in r.headers.get("X-NMAS-Invalidates", "")
        # Read AGAIN, now: the label API around the line, then the line at its nanosecond.
        paths = [p for p, _q in lab.loki.reads]
        assert paths == ["loki/api/v1/labels", "loki/api/v1/query_range"], paths
        q = lab.loki.reads[1][1]
        assert q["start"] == lab.ns and q["end"] == str(int(lab.ns) + 1)
        assert "detected_level" not in q["query"], "a label Loki does not index selected"
        assert order == [("record", 2)], "recorded after the read, before the answer"
        rows = [json.loads(l) for l in audit.read_text().splitlines()]
        assert len(rows) == 1
        row = rows[0]
        assert (row["actor"], row["kind"], row["what"], row["target"], row["list"]) == (
            "test-person@example.invalid", "person", "log_line", "s4", "Lab")
        assert row["ns"] == lab.ns and row["stream"]["job"] == "network_syslog"
        assert row["reason"] == REASON and row["line_at"].startswith("2026-")
        assert PLANTED not in audit.read_text(), "the record holds the value"

    def test_a_reason_in_the_record_is_masked_at_rest(self, lab, audit):
        r = _reveal(lab, reason=f"compare with snmp-server community {PLANTED} RO")
        assert r.status_code == 200
        assert PLANTED not in audit.read_text()


class TestRefused:
    @pytest.mark.parametrize("reason,words", [
        ("", "a reveal needs a reason: at least 3 words and 8 characters; none was given"),
        ("because", "a reveal needs a reason of at least 3 words and 8 characters; this one "
                    "is 1 word and 7 characters"),
        ("x " * 200, "a reason is at most 300 characters; this one is 399")])
    def test_a_reason_not_the_shape_of_one(self, lab, audit, reason, words):
        lab.loki.reads.clear()
        r = _reveal(lab, reason=reason)
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 400 and words in html, html
        assert PLANTED not in html and lab.loki.reads == [] and not audit.exists()

    def test_a_service_even_one_granted_the_operation(self, lab, audit, monkeypatch):
        from modules import identity
        svc = identity.Identity(actor="service:abc.access", kind="service",
                                service_id="abc.access", verified=True, outcome="ok",
                                peer="198.51.100.7", peer_trusted=True, header_present=True)
        form = _form(_lines(lab), lab.ns)
        monkeypatch.setattr(identity, "identify", lambda _r: svc)
        monkeypatch.setattr(identity, "service_may", lambda op: op == "log_line")
        r = lab.client.post("/v2/history/query/ask/logs/reveal", data=dict(form, reason=REASON))
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 403, html
        assert "revealed only to a verified person; this request is a service, not a person" \
            in html
        assert PLANTED not in html and not audit.exists()

    @pytest.mark.real_identity
    def test_no_one_identified_draws_nothing(self, lab, audit):
        r = lab.client.post("/v2/history/query/ask/logs/reveal", data={"ns": lab.ns,
                                                                        "reason": REASON})
        assert r.status_code in (401, 403) and PLANTED not in r.get_data(as_text=True)
        assert not audit.exists()

    def test_a_line_loki_no_longer_holds(self, lab, audit):
        form = _form(_lines(lab), lab.ns)
        lab.loki.body = copy.deepcopy(LINES["answer"])        # the planted line has aged out
        r = lab.client.post("/v2/history/query/ask/logs/reveal", data=dict(form, reason=REASON))
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 409, html
        assert "Loki holds no line at 2026-" in html and "whose masked form is the one shown" \
            in html and '{device="s4"' in html
        assert not audit.exists()

    def test_a_line_whose_masked_form_is_not_the_one_shown(self, lab, audit):
        r = _reveal(lab, shown="0" * 64)
        assert r.status_code == 409 and not audit.exists()

    def test_a_line_with_nothing_masked(self, lab, audit):
        from modules import log_reveal
        from modules.redact import redact_text
        s = lab.loki.body["data"]["result"][0]
        ns, raw = s["values"][1]
        assert redact_text(raw) == raw, "the capture's line holds a secret"
        form = dict(_form(_lines(lab), lab.ns), ns=ns, shown=log_reveal.digest(raw))
        r = lab.client.post("/v2/history/query/ask/logs/reveal", data=dict(form, reason=REASON))
        assert r.status_code == 409
        assert "nothing in this line is masked" in r.get_data(as_text=True)
        assert not audit.exists()

    def test_a_record_that_cannot_be_written_shows_nothing(self, lab, audit, monkeypatch):
        from modules import reveal_audit
        monkeypatch.setattr(reveal_audit, "record", lambda **k: dict(k, recorded=False))
        r = _reveal(lab)
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 503 and PLANTED not in html
        assert "a log line is never revealed unrecorded" in html

    @pytest.mark.parametrize("over,words", [
        ({"stream": "not json"}, "the line's stream is not a set of labels"),
        ({"stream": json.dumps({"bad name": "x"})}, "'bad name' is not a label name"),
        ({"ns": "12ab"}, "'12ab' is not a time in nanoseconds"),
        ({"shown": "xyz"}, "what was shown is not named")])
    def test_a_line_not_named(self, lab, audit, over, words):
        r = _reveal(lab, **over)
        assert r.status_code == 400 and words in unescape(r.get_data(as_text=True))
        assert not audit.exists()

    def test_a_network_that_does_not_exist(self, lab, audit):
        r = _reveal(lab, list="Nowhere")
        assert r.status_code == 404
        assert "there is no network named 'Nowhere'" in unescape(r.get_data(as_text=True))


def test_reveal_in_a_browser(lab, audit):
    """In a real browser at 1440 and at phone width: Reveal… opens its box in place, Cancel
    closes it revealing nothing, a reason and Reveal draw the line unmasked under its masked
    form and the box closes so it never covers the line, the box's How link is there, the box
    stays inside the window, and nothing scrolls sideways."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A

    url = "/v2/history/query/ask/logs?list=Lab&range=1h&ask=1"
    got = {}
    with browser.Served(A.app) as srv:
        for width in (1440, 500):
            with browser.Browser() as b:
                b._call("POST", f"/session/{b.session}/window/rect", {"width": width,
                                                                      "height": 1000})
                b.go(srv.url(url))
                b.wait_for("return document.querySelector('.lq-rvbox summary')", 15)
                b.js("document.querySelector('.lq-rvbox summary').click(); return 1")
                opened = b.js("return document.querySelector('.lq-rvbox').open")
                b.js("document.querySelector('.lq-rvbox [data-lq-close]').click(); return 1")
                closed = b.js("return !document.querySelector('.lq-rvbox').open")
                b.js("document.querySelector('.lq-rvbox summary').click();"
                     "var i = document.querySelector('.lq-rvbox input[name=reason]');"
                     f"i.value = {json.dumps(REASON)}; return 1")
                inside = b.js("var p = document.querySelector('.lq-rvpop').getBoundingClientRect();"
                              "return p.left >= 0 && p.right <= window.innerWidth")
                b.js("document.querySelector('.lq-rvbox button[type=submit]').click(); return 1")
                b.wait_for("return document.querySelector('.lq-rv-line')", 15)
                b.wait_for("return !document.querySelector('.lq-rvbox').open", 5)
                got[width] = {
                    "opened": opened, "closed": closed, "inside": inside,
                    "line": b.js("return document.querySelector('.lq-rv-line').textContent"),
                    "how": b.js("return !!document.querySelector('.lq-rvbox a.how-link')"),
                    "wide": b.js("return document.documentElement.scrollWidth"
                                 " <= window.innerWidth")}
                b.go("about:blank")
    for width, g in got.items():
        assert g["opened"] and g["closed"] and g["how"], (width, g)
        assert f"snmp-server community {PLANTED} RO" in g["line"], (width, g["line"])
        assert g["inside"] and g["wide"], (width, g)
    assert len(audit.read_text().splitlines()) == 2, "each reveal is its own record"


class TestHistoryDrawsTheRecord:
    def _ctx(self, device="", members=None):
        return {"ref": SimpleNamespace(name="Lab"), "device": device, "limit": 50,
                "since": None, "members": members}

    def test_the_record_is_a_timeline_row_and_never_the_value(self, lab, audit):
        from modules import history_sources as HS
        assert _reveal(lab).status_code == 200
        got = HS.log_reveals(self._ctx())
        assert got["errors"] == [] and len(got["events"]) == 1
        e = got["events"][0]
        assert e["kind"] == "reveal" and e["devices"] == ["s4"]
        assert e["what"].startswith("Log line revealed: s4 at 2026-")
        assert e["who"] == "test-person@example.invalid" and e["detail"] == REASON
        assert 'job="network_syslog"' in dict(e["record"])["Line"]
        assert PLANTED not in json.dumps(got)
        assert HS.log_reveals(self._ctx(device="r1"))["events"] == []
        assert HS.log_reveals(dict(self._ctx(), ref=SimpleNamespace(name="Other")))["events"] \
            == [], "another network's History drew this network's reveal"
        assert HS.log_reveals(self._ctx(members={"r1"}))["events"][0]["devices"] == [], \
            "a device outside the inventory is the network's own record, never hidden"
        assert "reveal" in HS.KIND_FILTERS["reveals"]

    def test_the_one_timeline_reader_files_it_under_its_kind(self, lab, audit):
        from modules import history_sources as HS
        assert _reveal(lab).status_code == 200
        ref = SimpleNamespace(name="Lab", repo_dir=str(audit.parent), data_dir=str(audit.parent))
        got = HS.timeline(ref, kinds=["reveals"])
        assert [e["kind"] for e in got["events"]] == ["reveal"]
        assert got["counts"].get("reveal") == 1

    def test_an_unreadable_record_is_said(self, audit):
        from modules import history_sources as HS
        audit.mkdir()                                          # a folder where the file is
        got = HS.log_reveals(self._ctx())
        assert got["events"] == [] and got["errors"] and \
            got["errors"][0].startswith("the reveal record could not be read:")
