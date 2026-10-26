"""The device page's Drift row is no longer a dead end (C342, board C342Drift).

The operator, 2026-10-02: r3's Overview said "Drift: differs from its golden by 9 line(s) just
now" with no way to see the lines or act. The row now opens, in place, onto the lines the drift
run kept (masked on the way out), what the device's own log says about when and how it changed
(each line at the time Mercury RECEIVED it), and the three choices: keep it (Capture), put
intent back (Plan a deploy…), remove lines (Remove lines (Mode B)…), each with its help.

On `test_device_v2`'s lab (r3, r2's REAL configuration as its committed golden). The drift is
the REAL drift run (`drift_check.run_drift_check`) over r3 answering with that configuration
and two minimal edits: one interface description changed, and the account line's password
changed, so the kept diff carries a secret on both sides. The log is s3's REAL syslog as Loki
returned it (`tests/fixtures/loki/lines_s3.json`, s3's clock days behind and marked unset),
its device name edited to r3, through a fake Loki that applies the query's own line filters.
Nothing here opens a session to a device.
"""

import datetime
import json
import os
import re

import pytest

from tests.test_device_v2 import lab  # noqa: F401  (the fixture)
from tests.test_intent_match import R2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S3_LINES = os.path.join(ROOT, "tests", "fixtures", "loki", "lines_s3.json")
#: Two minimal edits of r2's real configuration: the lines r3 is found to run instead.
DESCRIPTION = " description P2P to s2 Gi0/2 - RIPng"
EDITED_DESCRIPTION = " description temp test link"
ACCOUNT = re.compile(r"^(username admin privilege 15 password 0 )(\S+)$", re.M)


def _golden():
    return open(R2, encoding="utf-8").read()


def _password(text):
    return ACCOUNT.search(text).group(2)


def _running():
    text = _golden()
    assert DESCRIPTION in text and ACCOUNT.search(text), "r2's capture moved: re-take the edits"
    text = text.replace(DESCRIPTION, EDITED_DESCRIPTION, 1)
    return ACCOUNT.sub(lambda m: m.group(1) + m.group(2) + "Edited9", text, count=1)


def _drift(monkeypatch, running=None):
    """The real drift run of the lab's network, r3 answering with *running*; recorded as the
    scheduler records it. Returns the run's result."""
    from modules import drift_check

    answer = running if running is not None else _running()
    monkeypatch.setattr("modules.connection.get_persistent_connection",
                        lambda dev, pool, lock: dev["hostname"])
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, cmd: answer if conn == "r3" else "")
    # The lab's r3 carries r2's configuration (its `hostname r2` line): the read check, which
    # refuses another device's configuration, is not what is tested here.
    monkeypatch.setattr("modules.config_read.check",
                        lambda text, hostname, previous=None, strict=True: text)
    result = drift_check.run_drift_check(triggered_by="test", list_name="Lab")
    drift_check._save_state({"last_check_ts": 1.0, "last_result": result}, "Lab")
    return result


def _overview(lab):  # noqa: F811
    r = lab["client"].get("/v2/device/r3/overview?list=Lab")
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _detail(lab):  # noqa: F811
    r = lab["client"].get("/v2/device/r3/drift?list=Lab")
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _drift_row(html):
    m = re.search(r'<li class="check[^"]*">\s*<span class="check-ico">.*?<strong>Since last capture</strong>'
                  r'(.*?)</li>', html, re.S)
    assert m, "the Overview draws no Since last capture row (the drift check's, C1819)"
    return m.group(0)


def _text(html):
    import html as html_mod
    return html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip())


# ---------------------------------------------------------------------------- Loki

def _s3_lines_as_r3():
    cap = json.load(open(S3_LINES, encoding="utf-8"))
    return [(int(ns), line.replace(" s3 ", " r3 ").replace(" s3: ", " r3: "))
            for s in cap["answer"]["data"]["result"] for ns, line in s["values"]]


def _stages(query):
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


class _Resp:
    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


@pytest.fixture
def loki(monkeypatch):
    """A Loki holding s3's real lines as r3's, answering a range query by applying the query's
    own line filters (so what is tested is the query sent), or failing when told to."""
    from modules.integrations.loki import LokiIntegration

    state = {"asked": [], "corpus": _s3_lines_as_r3(), "fail": ""}

    def fake_get(self, path, **params):
        state["asked"].append((path, dict(params)))
        if state["fail"]:
            return {"ok": False, "error": state["fail"]}
        kept = sorted((x for x in state["corpus"] if _keep(x[1], _stages(params["query"]))
                       and int(params["start"]) <= x[0] <= int(params["end"])), reverse=True)
        kept = kept[:params["limit"]]
        body = {"status": "success", "data": {"result": [
            {"stream": {"job": "network_syslog"},
             "values": [[str(ns), line] for ns, line in kept]}] if kept else []}}
        return {"ok": True, "response": _Resp(body)}

    monkeypatch.setattr(LokiIntegration, "is_configured", lambda self: True)
    monkeypatch.setattr(LokiIntegration, "_get", fake_get)
    return state


def _config_lines():
    """The corpus's own configuration lines, found by the fixture's text, not the code."""
    return sorted(((ns, l) for ns, l in _s3_lines_as_r3() if "%SYS-5-CONFIG_I:" in l),
                  reverse=True)


def _now_after_corpus():
    return max(ns for ns, _l in _s3_lines_as_r3()) / 1e9 + 60


def _at_the_corpus(monkeypatch):
    """The log asked as if a minute after the corpus's last line (its window ends now)."""
    from modules import device_logs

    real = device_logs.change_lines
    monkeypatch.setattr(device_logs, "change_lines",
                        lambda dev, since=None, now=None: real(dev, since=since,
                                                               now=_now_after_corpus()))


# ---------------------------------------------------------------------------- the row's states

class TestTheRow:
    def test_at_its_golden_there_is_nothing_to_open(self, lab, monkeypatch):  # noqa: F811
        result = _drift(monkeypatch, running=_golden())
        assert result["clean"] == 1 and not result["drifted_devices"], result
        row = _drift_row(_overview(lab))
        assert "unchanged at the last run" in row and "check-ok" in row
        assert "<details" not in row and "/drift" not in row

    def test_drifted_the_row_is_closed_and_asks_for_its_lines_once(self, lab, monkeypatch):  # noqa: F811
        result = _drift(monkeypatch)
        n = result["drifted_devices"][0]["diff_lines"]
        row = _drift_row(_overview(lab))
        assert f"changed: differs from its golden by {n} line(s)" in row and "check-warn" in row
        details = re.search(r"<details [^>]*>", row)
        assert details, "a drifted row draws nothing to open"
        details = details.group(0)
        assert 'hx-get="/v2/device/r3/drift?list=Lab"' in details
        assert 'hx-trigger="toggle once"' in details and 'data-keep="drift"' in details
        assert "<details" in row and " open" not in details
        assert "The lines, what r3's log says, and what to do" in row
        # The lines are fetched when the row is opened, never drawn with the tab.
        assert EDITED_DESCRIPTION.strip() not in row

    def test_an_unreadable_record_is_neither_clean_nor_never_run(self, lab, monkeypatch):  # noqa: F811
        from modules import drift_check
        path = drift_check._state_file("Lab")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"last_result": {"drifted_devices": [')
        row = _drift_row(_overview(lab))
        text = _text(row)
        assert "check-unreadable" in row and 'class="check-unread"' in row
        assert "unreadable" in text and "the drift record could not be read" in text
        assert "whether r3 is at its golden is not known" in text
        assert "no drift run recorded" not in text and "unchanged at the last run" not in text
        assert "check-ok" not in row and "<details" not in row

    def test_a_network_never_checked_says_so(self, lab):  # noqa: F811
        row = _drift_row(_overview(lab))
        assert "no drift run recorded for this list" in row
        assert "check-unreadable" not in row and "<details" not in row


# ---------------------------------------------------------------------------- what it opens onto

class TestTheLines:
    def test_the_kept_lines_are_drawn_masked_with_their_counts(self, lab, monkeypatch, loki):  # noqa: F811
        result = _drift(monkeypatch)
        html = _detail(lab)
        text = _text(html)
        assert "-" + DESCRIPTION in html and "+" + EDITED_DESCRIPTION in html
        assert "2 lines only on r3, 2 only in its golden" in text
        n = result["drifted_devices"][0]["diff_lines"]
        assert f"counted the same {n}" in text, text
        assert 'class="dl-add"' in html and 'class="dl-del"' in html

    def test_a_secret_in_the_diff_is_masked_on_both_sides(self, lab, monkeypatch, loki):  # noqa: F811
        _drift(monkeypatch)
        old, new = _password(_golden()), _password(_running())
        assert old != new and len(old) >= 4
        html = _detail(lab)
        # Each value in its position (r2's old value is also a word elsewhere in the line).
        assert f"password 0 {old}" not in html and new not in html
        assert html.count("username admin privilege 15 password 0 &lt;redacted:user_password&gt;") == 2
        assert "2 lines masked" in _text(html)

    @pytest.mark.parametrize("mark", ["+", "-", " "])
    def test_every_canary_shape_is_masked_behind_a_diff_mark(self, mark):
        """The product's own canary lines (`redact.CANARY_LINES`, every secret shape Mercury
        emits), each as a diff line: a pattern anchored at a line's start (`enable secret`)
        must match behind the mark too."""
        from modules import device_page, redact

        text = "\n".join(mark + line for _label, line in redact.CANARY_LINES)
        rows = device_page._diff_rows(text)
        drawn = "\n".join(r["text"] for r in rows)
        for token in redact.CANARY_TOKENS.values():
            assert token not in drawn, (token, drawn)
        assert all(r["text"].startswith(mark) and r["masked"] for r in rows)

    def test_lines_kept_by_an_earlier_run_say_they_may_have_moved(self, lab, monkeypatch, loki):  # noqa: F811
        """The queue keeps the FIRST run's diff for a device (C337): a later run that counted
        another number is said, never drawn as if it were the last run's."""
        _drift(monkeypatch)
        more = _running().replace("\nlldp run\n", "\n")
        assert more != _running(), "r2's capture has no `lldp run` to remove"
        result = _drift(monkeypatch, running=more)
        text = _text(_detail(lab))
        assert f"counted {result['drifted_devices'][0]['diff_lines']} where these are" in text
        assert "may have moved since" in text

    def test_lines_no_longer_kept_are_said_with_why(self, lab, monkeypatch, loki):  # noqa: F811
        from modules import approval_queue as Q
        _drift(monkeypatch)
        item = next(e for e in Q.get_pending("Lab") if e["device_hostname"] == "r3")
        assert Q.withdraw(item["id"], "a test withdrew it", by="test", list_name="Lab")["ok"]
        text = _text(_detail(lab))
        assert "Not kept: the drift item for r3 was withdrawn: a test withdrew it" in text
        assert "Capture's preview reads r3" in text


class TestTheLog:
    def test_only_its_change_lines_newest_first_at_their_receive_time(self, monkeypatch, loki):
        from modules import device_logs

        v = device_logs.change_lines({"hostname": "r3"}, since=None, now=_now_after_corpus())
        want = _config_lines()
        assert len(want) == 2 and not v["error"], v
        assert [l["ns"] for l in v["lines"]] == [ns for ns, _l in want]
        for line, (ns, _raw) in zip(v["lines"], want):
            received = datetime.datetime.fromtimestamp(ns / 1e9, datetime.timezone.utc)
            assert line["at_iso"] == received.strftime("%Y-%m-%dT%H:%M:%SZ")
            assert line["mnemonic"] == "%SYS-5-CONFIG_I" and line["unsync"]
            # The device's clock ran days behind: its own time is never the line's time.
            assert not line["at_iso"].startswith("2026-10-05")
        query = loki["asked"][-1][1]["query"]
        for mn in ("%SYS-5-CONFIG_I", "%SYS-5-CONFIG_P", "%SYS-5-RESTART", "%SYS-5-RELOAD",
                   "%PARSER-5-CFGLOG_LOGGEDCMD"):
            assert re.escape(mn) in query, (mn, query)

    def test_the_window_starts_at_the_golden_and_never_past_lokis_longest_ask(self, monkeypatch, loki):
        from modules import device_logs

        now = _now_after_corpus()
        newest = _config_lines()[0][0] / 1e9
        v = device_logs.change_lines({"hostname": "r3"}, since=newest + 1, now=now)
        assert v["lines"] == [] and not v["capped"]
        old = device_logs.change_lines({"hostname": "r3"}, since=now - 90 * 86400, now=now)
        assert old["capped"] and int(loki["asked"][-1][1]["start"]) == int((now - 30 * 86400) * 1e9)

    def test_the_drawn_log_names_each_receive_time_and_the_devices_own(self, lab, monkeypatch, loki):  # noqa: F811
        _drift(monkeypatch)
        _at_the_corpus(monkeypatch)
        monkeypatch.setattr("modules.device_page._epoch", lambda iso: None)
        html = _detail(lab)
        for ns, raw in _config_lines():
            at = datetime.datetime.fromtimestamp(ns / 1e9, datetime.timezone.utc)
            assert at.strftime("%m-%d %H:%M:%S UTC") in html, at
            own = re.search(r"\*(\w{3}\s+\d+ [\d:.]+ UTC)", raw).group(1)
            assert f"r3's own time: {own} (its clock not set)" in html
        assert "Configured from console by" in html
        assert 'href="/v2/device/r3?tab=logs&amp;list=Lab"' in html

    def test_loki_not_answering_is_couldnt_load_never_no_lines(self, lab, monkeypatch, loki):  # noqa: F811
        _drift(monkeypatch)
        loki["fail"] = "connection refused"
        text = _text(_detail(lab))
        assert "Couldn't load: Loki could not be asked: connection refused" in text
        assert "line about" not in text and "lines about" not in text
        # The other parts are drawn.
        assert "only on r3" in text and "What to do" in text


class TestTheChoices:
    def test_three_choices_each_opening_its_card_in_this_network_with_its_help(self, lab, monkeypatch, loki):  # noqa: F811
        _drift(monkeypatch)
        html = _detail(lab)
        want = {
            "capture": ("Capture", "/v2/device/r3/capture?back=overview&amp;list=Lab",
                        "/v2/device/r3?tab=overview&amp;op=capture&amp;list=Lab"),
            "deploy": ("Plan a deploy…", "/v2/device/r3/deploy?back=overview&amp;list=Lab",
                       "/v2/device/r3?tab=overview&amp;op=deploy&amp;list=Lab"),
            "removal": ("Remove lines (Mode B)…",
                        "/v2/device/r3/deploy?back=overview&amp;focus=removal&amp;list=Lab",
                        "/v2/device/r3?tab=overview&amp;op=deploy&amp;focus=removal&amp;list=Lab"),
        }
        for op, (label, get, href) in want.items():
            a = re.search(rf'<a class="btn btn-small" data-op="{op}"[^>]*>.*?</a>(<a class="how-link[^>]*>)', html, re.S)
            assert a, op
            assert f'hx-get="{get}"' in a.group(0) and f'href="{href}"' in a.group(0), a.group(0)
            assert label in a.group(0)
            assert f'data-manual="{op}"' in a.group(1)
        # C503: "How does this work?" in words once in the card, the others the (i) alone.
        assert html.count("How does capture work?</span>") == 1
        assert html.count('class="how-link compact"') == 2
        assert "capture first, or the apply refuses with nothing sent" in html

    def test_a_detail_that_cannot_be_read_says_couldnt_load_in_place(self, lab, monkeypatch):  # noqa: F811
        def broken(ref, dev, now=None):
            raise OSError("the queue's disk went away")
        monkeypatch.setattr("modules.device_page.drift_detail", broken)
        text = _text(_detail(lab))
        assert "Couldn't load: OSError: the queue's disk went away." in text
