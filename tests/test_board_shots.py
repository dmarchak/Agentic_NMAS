"""Board fidelity shots (C650; the operator, 2026-10-10: "a screenshot of the page next to the
board, compared region by region"). Runs only when asked: `NMAS_BOARD_SHOTS=<out folder>` and
`NMAS_BOARDS_DIR=<a copy of the mockups canvas's project/ folder>` (the Artifact tool's read of
the canvas saves it), with the first canvas's project/ folder ("NMAS redesign mockups") copied
into its `redesign/`. Otherwise every test here skips, and the suite never needs the canvas.

For each board-built screen in `SCREENS`: the board's own `.dc.html` and the page as built, fed
from real captures, rendered in the same headless Firefox at the board's width and at phone
width, saved as PNGs side by side in name (`<screen>-board-1280.png`, `<screen>-page-1280.png`).
A person (or the agent) compares them region by region and writes the verdicts into
docs/fidelity/<screen>.md, with the hash of the templates compared: tests/test_board_fidelity.py
refuses a board-built screen whose templates changed since their record.
"""

import base64
import json
import functools
import http.server
import os
import threading
import time

import pytest

OUT = os.environ.get("NMAS_BOARD_SHOTS", "")
BOARDS = os.environ.get("NMAS_BOARDS_DIR", "")

pytestmark = [pytest.mark.skipif(not (OUT and BOARDS),
                                 reason="board shots run only when asked (NMAS_BOARD_SHOTS, "
                                        "NMAS_BOARDS_DIR)"),
              # C1522: eleven shots write reader stores (topology-graph, dhcp, logs-summary);
              # each keeps them in its own folder.
              pytest.mark.usefixtures("reader_stores_in_tmp")]


def _full(b, path):
    """The whole page, not only the viewport (geckodriver's full-page screenshot)."""
    png = b._call("GET", f"/session/{b.session}/moz/screenshot/full")
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(png))


class _Boards:
    """The board files served on loopback (a snap Firefox cannot read the host's /tmp)."""

    def __enter__(self):
        from tests.browser import free_port
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=BOARDS)
        handler.log_message = lambda *a, **k: None
        self.port = free_port()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def url(self, name):
        return f"http://127.0.0.1:{self.port}/{name}"

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def test_dhcp(tmp_path, monkeypatch):
    """C529's board A (DhcpNetwork, 1440) beside the DHCP page's tabs, fed by the DHCP reader's
    value built from the lab's Kea answers (tests/fixtures/kea/); or, as a walk, the reader's
    stored document as the host holds it (`NMAS_BOARD_DHCP_DOC`)."""
    from tests import browser
    from tests import test_dhcp_v2 as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.dhcp_page._devices", lambda name: set())
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: __import__("modules.reader_job").reader_job
                        .read_cached(name))
    walked = os.environ.get("NMAS_BOARD_DHCP_DOC", "")
    if walked:
        from modules import reader_job
        with open(walked, encoding="utf-8") as fh:
            doc = json.load(fh)
        os.makedirs(os.path.dirname(reader_job.store_path("dhcp")), exist_ok=True)
        with open(reader_job.store_path("dhcp"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        import app as A
        with browser.Served(A.app) as served:
            for tab in ("sub", "lea", "res"):
                _shoot(f"dhcp-walk-{tab}", "", lambda w, t=tab: f"/v2/dhcp?list=Lab&tab={t}",
                       served, widths=((1440, 1.0), (390, 2.0)))
        return
    value = T._value()
    T._store(value)
    import app as A
    with browser.Served(A.app) as served:
        _shoot("dhcp-sub", "DhcpNetwork.dc.html", lambda w: "/v2/dhcp?list=Lab", served,
               widths=((1440, 1.0), (1280, 1.0), (390, 2.0)))
        # Board C's table (C529 step 3), as it reads after the subnet move: s1's committed
        # intent beside Kea's options, and every subnet Mercury's (ZTP's its own posture).
        value["intent"] = dict(T._s1_intent(), error="")
        value["families"]["dhcp4"]["held"] = {"10": "mercury", "20": "mercury", "255": "ztp"}
        value["families"]["dhcp6"]["held"] = {"10": "mercury", "20": "mercury", "30": "mercury"}
        # Board C's revision (C709): a pool says what it is for under its range, or that
        # Edit… adds a description.
        for fam, prefix in (("dhcp4", "10.10.10.0/24"), ("dhcp6", "2001:db8:10::/64")):
            sub = next((x for x in value["families"][fam]["subnets"] if x["prefix"] == prefix),
                       None)
            if sub:
                sub["pool_notes"] = ["lab hosts, VLAN 10"] * len(sub.get("pools") or [])
        T._store(value)
        _shoot("dhcp-sub-c", "DhcpSubnets.dc.html", lambda w: "/v2/dhcp?list=Lab", served,
               widths=((1440, 1.0), (390, 2.0)))
        _shoot("dhcp-sub-c-edit", "", lambda w: "/v2/dhcp/subnet?list=Lab&family=IPv4&id=10",
               served, widths=((1440, 1.0), (390, 2.0)))
        T._store(T._value())
        for tab in ("lea", "res", "exc"):
            _shoot(f"dhcp-{tab}", "", lambda w, t=tab: f"/v2/dhcp?list=Lab&tab={t}", served,
                   widths=((1440, 1.0), (390, 2.0)))


def test_onboard_discovered(tmp_path, monkeypatch):
    """Board L (ZtpDiscovery, 1440) beside Onboard devices › Discovered, fed the discovery
    reader's value with all three groups (tests/test_onboard_discovered_v2.py's), and a Pick's
    Add device card opened in place."""
    from tests import browser
    from tests import test_onboard_discovered_v2 as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: __import__("modules.reader_job").reader_job
                        .read_cached(name))
    monkeypatch.setattr("modules.discovery_page.time.time", lambda: T.NOW)
    T.store(T.value())
    import app as A
    with browser.Served(A.app) as served:
        _shoot("onboard-discovered", "ZtpDiscovery.dc.html",
               lambda w: "/v2/onboard/discovered?list=Lab", served,
               widths=((1440, 1.0), (1280, 1.0), (390, 2.0)))


def test_dhcp_reserve(tmp_path, monkeypatch):
    """C529 step 2's board B (DhcpReserve, 1440) beside the Reservations tab's card: board B's
    three operations as previews (Edit h2's MAC, Add an IPv6 address for h1, Remove h3's) and
    its refusal, against the lab's Kea answers with each subnet's file of Mercury's, and an
    Add's result in place."""
    import json as _json

    from tests import browser
    from tests import test_dhcp_v2 as T
    from tests.test_dhcp_reservations import FakeKea as KeaFiles

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules import dhcp_reservations as R
    from modules.nsot import ztp
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.dhcp_page._devices", lambda name: set())
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: __import__("modules.reader_job").reader_job
                        .read_cached(name))
    nmas = tmp_path / "nmas"
    nmas.mkdir()
    files, mains = {}, {}
    for family, svc, ids in (("IPv4", "dhcp4", (10, 20, 255)), ("IPv6", "dhcp6", (10, 20, 30))):
        main = str(tmp_path / f"kea-{svc}.conf")
        for sid in ids:
            files[(svc, sid)] = R.fragment(main, family, sid)
            entries = []
            if (svc, sid) == ("dhcp4", 20):
                entries = [{"hw-address": "aa:c1:ab:3e:11:70", "ip-address": "10.10.20.101",
                            "hostname": "h2"}]
            if (svc, sid) == ("dhcp4", 10):
                entries = [{"hw-address": "aa:c1:ab:b0:85:65", "ip-address": "10.10.10.102",
                            "hostname": "h3"}]
            with open(files[(svc, sid)], "w", encoding="utf-8") as fh:
                _json.dump(entries, fh)
        with open(main, "w", encoding="utf-8") as fh:
            fh.write("\n".join(R.directive(files[(svc, sid)]) for sid in ids))
        mains[family] = main
    kea = KeaFiles(files)
    monkeypatch.setattr(R, "main_config", lambda list_name, family: mains[family])
    monkeypatch.setattr(R, "_ztp_fragment", lambda list_name: files[("dhcp4", 255)])
    monkeypatch.setattr("modules.integrations.kea.KeaIntegration", lambda **kw: kea)
    monkeypatch.setattr(ztp, "_run_kea_test", lambda path, program="kea-dhcp4": (True, "ok"))
    T._store(T._value(kea=kea))
    from urllib.parse import urlencode
    asks = {
        "edit": {"op": "edit", "family": "IPv4", "subnet": "20", "key": "hw-address",
                 "identity": "aa:c1:ab:5d:20:9e", "address": "10.10.20.101",
                 "was": "hw-address=aa:c1:ab:3e:11:70"},
        "add": {"op": "add", "where": "IPv6:10", "key": "duid",
                "identity": "00:03:00:01:aa:c1:ab:99:f6:e2", "address": "2001:db8:10::101",
                "hostname": "h1"},
        "remove": {"op": "remove", "family": "IPv4", "subnet": "10",
                   "was": "hw-address=aa:c1:ab:b0:85:65"},
        "refused": {"op": "add", "where": "IPv4:20", "key": "hw-address",
                    "identity": "aa:c1:ab:77:02:10", "address": "10.10.20.101",
                    "hostname": "h5"},
    }
    import app as A
    with browser.Served(A.app) as served:
        for i, (name, ask) in enumerate(asks.items()):
            _shoot(f"dhcp-reserve-{name}", "DhcpReserve.dc.html" if i == 0 else "",
                   lambda w, a=ask: "/v2/dhcp/reservation?" + urlencode(dict(a, list="Lab")),
                   served, widths=((1440, 1.0), (390, 2.0)))


def _shoot(name, board_file, page_url_for, served, widths=((1280, 1.0), (390, 2.0)),
           settled=""):
    from tests.browser import Browser

    os.makedirs(OUT, exist_ok=True)
    with _Boards() as boards:
        for width, scale in widths:
            prefs = {"layout.css.devPixelsPerPx": str(scale)} if scale != 1.0 else {}
            with Browser(prefs=prefs) as b:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": width, "height": 1000})
                if board_file:
                    b.go(boards.url(board_file))
                    _full(b, os.path.join(OUT, f"{name}-board-{width}.png"))
                b.go(served.url(page_url_for(width)))
                if settled:
                    # A page that draws after it loads (a chart reading its data): shot once
                    # *settled* (a JS expression) is true, at most 10 s.
                    for _ in range(100):
                        if b.js(f"return !!({settled})"):
                            break
                        time.sleep(0.1)
                if width < 480:
                    # Firefox's narrowest window is 488 CSS px wide; a phone is narrower. The
                    # media queries are the same below 700, so the page is held to the phone's
                    # width as a column (through the CSSOM, which the strict CSP allows).
                    b.js(f"document.documentElement.style.maxWidth = '{width}px'; "
                         f"document.body.style.maxWidth = '{width}px'; return 1")
                _full(b, os.path.join(OUT, f"{name}-page-{width}.png"))
                if width < 480:
                    # The phone's first screen as well: what a person sees before scrolling.
                    png = b._call("GET", f"/session/{b.session}/screenshot")
                    with open(os.path.join(OUT, f"{name}-page-{width}-first.png"), "wb") as fh:
                        fh.write(base64.b64decode(png))


def test_logs(tmp_path, monkeypatch):
    """C652's board C (AskLogs, 1440) beside the Logs view, fed by the logs reader's value built
    from the real captures (tests/test_logs_v2's fixtures), 120 days, r4 opened to its lines."""
    from types import SimpleNamespace

    from tests import browser
    from tests import test_logs_v2 as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.readers.adjacencies.lists",
                        lambda: [("Lab", SimpleNamespace(repo_dir=str(tmp_path)), T.MANAGED)])
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: __import__("modules.reader_job").reader_job
                        .read_cached(name))
    monkeypatch.setattr("modules.logs_page.time.time", lambda: T.NOW)
    lines = T._fx("lines_r4.json")["answer"]

    class _R:
        def json(self):
            return lines
    monkeypatch.setattr("modules.integrations.loki.LokiIntegration._get",
                        lambda self, path, **p: {"ok": True, "response": _R()})
    walked = os.environ.get("NMAS_BOARD_LOGS_DOC", "")
    if walked:
        # A walk: the logs reader's stored document as the host holds it (names and counts),
        # drawn as of now for the network's devices it names.
        from modules import reader_job
        with open(walked, encoding="utf-8") as fh:
            doc = json.load(fh)
        os.makedirs(os.path.dirname(reader_job.store_path("logs-summary")), exist_ok=True)
        with open(reader_job.store_path("logs-summary"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        monkeypatch.setattr("modules.logs_page.time.time", lambda: doc["last_good"]["value"]
                            ["read_at_ts"])
        import app as A
        with browser.Served(A.app) as served:
            _shoot("logs-walk", "", lambda w: "/v2/history/query/syslog?list=Lab&range=30d", served,
                   widths=((1440, 1.0),))
        return
    T._store(T._read(previous=T._read()))
    import app as A
    with browser.Served(A.app) as served:
        _shoot("logs", "AskLogs.dc.html",
               lambda w: "/v2/history/query/syslog?list=Lab&range=120d&sev=all&d=r4", served,
               widths=((1440, 1.0), (390, 2.0)))


def test_logs_tail(tmp_path, monkeypatch):
    """C675's board D (LogsTail, 1440) beside the sidebar's Logs, the live tail, fed by the
    logs-tail reader's value built from real lines of the lab's Loki (tests/test_logs_tail's
    fixtures); and the same page arrived from History › Query, filtered, and paused; or, as a
    walk, the reader's stored document as the host holds it (`NMAS_BOARD_TAIL_DOC`)."""
    from tests import browser
    from tests import test_logs_tail as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules import reader_job
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: reader_job.read_cached(name))
    path = reader_job.store_path("logs-tail")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    walked = os.environ.get("NMAS_BOARD_TAIL_DOC", "")
    if walked:
        with open(walked, encoding="utf-8") as fh:
            doc = json.load(fh)
    else:
        doc = {"last_attempt": {"at": "2026-10-11T18:20:17Z", "ok": True, "error": ""},
               "last_good": {"value": T._read(), "value_at": "2026-10-11T18:20:12Z"}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    paused = doc["last_good"]["value"]["lines"][5]["at"] if \
        len(doc["last_good"]["value"].get("lines") or []) > 5 else ""
    import app as A
    with browser.Served(A.app) as served:
        _shoot("logs-tail" + ("-walk" if walked else ""), "" if walked else "LogsTail.dc.html",
               lambda w: "/v2/logs?list=Lab", served, widths=((1440, 1.0), (390, 2.0)))
        if not walked:
            _shoot("logs-tail-came", "", lambda w: "/v2/logs?list=Lab&d=s3&sev=error&from=query",
                   served, widths=((1440, 1.0),))
            _shoot("logs-tail-paused", "", lambda w: f"/v2/logs?list=Lab&paused={paused}",
                   served, widths=((1440, 1.0),))


def test_history_query(tmp_path, monkeypatch):
    """C667's board A (AskLibrary, 1440) beside History › Query, the logs reader's value built
    from the same real captures as the logs shot."""
    from types import SimpleNamespace

    from tests import browser
    from tests import test_logs_v2 as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.readers.adjacencies.lists",
                        lambda: [("Lab", SimpleNamespace(repo_dir=str(tmp_path)), T.MANAGED)])
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: __import__("modules.reader_job").reader_job
                        .read_cached(name))
    T._store(T._read(previous=T._read()))
    import app as A
    with browser.Served(A.app) as served:
        _shoot("history-query", "AskLibrary.dc.html", lambda w: "/v2/history?tab=query", served,
               widths=((1440, 1.0), (390, 2.0)))
        # C720: Ask your own at a desk, at half a screen and at phone width, a LogQL query in it.
        ask = ("/v2/history/query/metric/ask?list=Lab&lang=logql&range=30d&q="
               "%7Bjob%3D~%22.%2B%22%7D+%7C%3D+%22%25SYS-5-CONFIG_I%22")
        _shoot("history-ask", "", lambda w: ask, served,
               widths=((1440, 1.0), (960, 1.0), (390, 2.0)))


def test_history_ask_logs(tmp_path, monkeypatch):
    """Board F3 (QueryBuilderLogs3, 1440, and QueryBuilderLogs3Phone, 390; approved 2026-10-15)
    beside Ask your own's logs builder, Loki answering with the real captures of 2026-10-15
    (tests/test_history_ask_logs.py's stand-in): the board's counts question (OSPF adjacency
    changes for r1 and s1, counted every hour, the capture's step), its Lines view (the last
    hour's lines), and the three states the answer can be in."""
    from types import SimpleNamespace

    from tests import browser
    from tests import test_history_ask_logs as F
    from tests import test_logs_v2 as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.readers.adjacencies.lists",
                        lambda: [("Lab", SimpleNamespace(repo_dir=str(tmp_path)), T.MANAGED)])
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: __import__("modules.reader_job").reader_job
                        .read_cached(name))
    T._store(T._read(previous=T._read()))
    monkeypatch.setattr("modules.history_logq._now", lambda: F.NOW)
    monkeypatch.setattr("modules.history_logq.roles", lambda ln: [("router", 5), ("switch", 4)])
    loki = F.FakeLoki()
    monkeypatch.setattr("modules.history_logq._client", lambda list_name, wait=65.0: loki)
    from modules import history_logq
    history_logq.forget()
    base = "/v2/history/query/ask/logs?list=Lab"
    counts = (base + "&dev=r1&dev=s1&sev=5&mn=%25OSPF-5-ADJCHG&has=Neighbor&show=counts"
              "&every=1h&ask=1&hl=count")
    settled = "!document.querySelector('.panel-wait')"
    import app as A
    with browser.Served(A.app) as served:
        _shoot("history-ask-logs", "QueryBuilderLogs3.dc.html", lambda w: counts, served,
               settled=settled, widths=((1440, 1.0), (1280, 1.0)))
        _shoot("history-ask-logs", "QueryBuilderLogs3Phone.dc.html", lambda w: counts, served,
               settled=settled, widths=((390, 2.0),))
        _shoot("history-ask-logs-lines", "", lambda w: base + "&range=1h&ask=1", served,
               widths=((1440, 1.0), (390, 2.0)))
        _shoot("history-ask-logs-refused", "", lambda w: base + "&range=custom&from=2026-08-31"
               "%2008:25&to=2026-10-15%2008:25&ask=1", served, widths=((1440, 1.0),))
        loki.empty = True
        _shoot("history-ask-logs-empty", "", lambda w: base + "&range=1h&has=Neighbor&ask=1",
               served, widths=((1440, 1.0),))
        loki.empty, loki.fail = False, "Timed out after 65.0s"
        _shoot("history-ask-logs-down", "", lambda w: base + "&ask=1", served,
               widths=((1440, 1.0),))
        # Reveal… (C818): the capture with its one planted secret-bearing line
        # (tests/test_log_reveal.py), the box opened with a reason, then the line revealed.
        from tests.browser import Browser
        from tests.test_log_reveal import REASON, plant
        loki.fail = ""
        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path / "lab"))
        plant(loki)
        for width, scale in ((1440, 1.0), (390, 2.0)):
            prefs = {"layout.css.devPixelsPerPx": str(scale)} if scale != 1.0 else {}
            with Browser(prefs=prefs) as b:
                b._call("POST", f"/session/{b.session}/window/rect", {"width": width,
                                                                      "height": 1000})
                b.go(served.url(base + "&range=1h&ask=1"))
                if width < 480:
                    b.js(f"document.documentElement.style.maxWidth = '{width}px'; "
                         f"document.body.style.maxWidth = '{width}px'; return 1")
                b.wait_for("return document.querySelector('.lq-rvbox summary')", 15)
                b.js("var s = document.querySelector('.lq-rvbox summary'); s.click();"
                     "s.scrollIntoView({block: 'center'});"
                     "document.querySelector('.lq-rvbox input[name=reason]').value = "
                     f"{json.dumps(REASON)}; return 1")
                _full(b, os.path.join(OUT, f"history-ask-logs-reveal-ask-page-{width}.png"))
                b.js("document.querySelector('.lq-rvbox button[type=submit]').click(); return 1")
                b.wait_for("return document.querySelector('.lq-rv-line')", 15)
                _full(b, os.path.join(OUT, f"history-ask-logs-revealed-page-{width}.png"))
    history_logq.forget()


def test_history_ask_metrics(tmp_path, monkeypatch):
    """Board E3 (QueryBuilderMetrics3, 1440, and QueryBuilderMetrics3Phone, 390; approved
    2026-10-15) beside Ask your own's metrics builder, Prometheus answering with the real
    captures of 2026-10-15 (tests/test_history_ask_metrics.py's stand-in), Loki's bounds from
    F3's, Grafana's data sources from their capture (the long-term store's row): the board's
    question (bytes in per role over three days) asked, with the filter editor, From… to… and
    the operation menu open as the board draws them; the phone; and the three states."""
    import copy
    from types import SimpleNamespace

    from tests import browser
    from tests import test_history_ask_logs as F
    from tests import test_history_ask_metrics as E
    from tests import test_logs_v2 as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.readers.adjacencies.lists",
                        lambda: [("Lab", SimpleNamespace(repo_dir=str(tmp_path)), T.MANAGED)])
    monkeypatch.setattr("modules.history_promq._now", lambda: E.NOW)
    prom = E.FakeProm()
    monkeypatch.setattr("modules.history_promq._client", lambda list_name, wait=125.0: prom)
    loki = F.FakeLoki()
    monkeypatch.setattr("modules.history_logq._client", lambda list_name, wait=65.0: loki)
    with open(os.path.join(os.path.dirname(__file__), "fixtures", "grafana", "dashboards",
                           "datasources_api.json"), encoding="utf-8") as fh:
        datasources = json.load(fh)
    monkeypatch.setattr("modules.device_page._cached", lambda name, list_name=None: (
        {"datasources": datasources}, "2026-10-15T09:00:00Z", ""))
    from modules import list_settings
    real = list_settings.value
    history = next(d["uid"] for d in datasources if d["name"].startswith("Thanos"))
    monkeypatch.setattr("modules.list_settings.value", lambda ln, key, default=None: (
        history if key == "grafana_history_datasource_uid" else real(ln, key, default)))
    from modules import history_logq, history_promq, saved_views
    history_promq.forget()
    history_logq.forget()
    spec = history_promq.ask(E.BOARD)[0]
    saved_views.save("Lab", "Bytes in per role, bits",
                     history_promq.PAGE_PATH + history_promq.qs(spec, over={"ask": "1"}),
                     "operator@example.com")
    saved_views.save("Lab", "Who stopped answering", "/v2/history/query/metric/ask?lang=promql"
                     "&q=up+%3D%3D+0&range=24h", "operator@example.com")
    saved_views.save("Lab", "OSPF adjacency changes, by device", "/v2/history/query/ask/logs"
                     "?mn=%25OSPF-5-ADJCHG&show=counts&ask=1", "operator@example.com")
    base = history_promq.PAGE_PATH
    board = base + history_promq.qs(spec, "Lab", {"ask": "1", "hl": "op3", "fe": "1", "mq": "octets",
                                                  "fl": "ifDescr", "fo": "!~",
                                                  "fv": "Loopback.*"})
    asked = base + history_promq.qs(spec, "Lab", {"ask": "1", "hl": "op3", "mq": "octets"})
    opened = ("!document.querySelector('.panel-wait') && "
              "(document.querySelector('.lq-pickbox').open = true, "
              "document.querySelector('[data-keep=pq-op-add]').open = true, true)")
    settled = "!document.querySelector('.panel-wait')"
    import app as A
    with browser.Served(A.app) as served:
        _shoot("history-ask-metrics", "QueryBuilderMetrics3.dc.html", lambda w: board, served,
               settled=opened, widths=((1440, 1.0), (1280, 1.0)))
        _shoot("history-ask-metrics", "QueryBuilderMetrics3Phone.dc.html", lambda w: asked,
               served, settled=settled, widths=((390, 2.0),))
        refused = copy.deepcopy(prom.config)
        prom.config["data"]["yaml"] = prom.config["data"]["yaml"].replace(
            "scrape_interval: 30s", "scrape_interval: 1m")
        history_promq.forget()
        bad = dict(spec, op=["rate:1m", "bits", "sum:role"])
        _shoot("history-ask-metrics-refused", "", lambda w: base + history_promq.qs(
            bad, "Lab", {"ask": "1"}), served, widths=((1440, 1.0),))
        prom.config = refused
        history_promq.forget()
        prom.empty = True
        june = dict(spec, **{"from": "2026-06-01 06:00", "to": "2026-07-01 06:00"})
        _shoot("history-ask-metrics-empty", "", lambda w: base + history_promq.qs(
            june, "Lab", {"ask": "1"}), served, widths=((1440, 1.0),))
        prom.empty, prom.fail = False, "Could not connect to http://192.0.2.10:9090"
        _shoot("history-ask-metrics-down", "", lambda w: asked, served, widths=((1440, 1.0),))
    history_promq.forget()
    history_logq.forget()


def _words_step(world, answer, words):
    """Ask in words' step: *answer* planted for the adapter, *words* typed, Fill pressed."""
    def step(b):
        world.answer = answer
        b.js("var i = document.getElementById('lq-words'); i.value = " + json.dumps(words)
             + "; document.querySelector('[data-op=ask-in-words]').click(); return 1")
    return step


_W_NOTE = "(document.querySelector('.lq-words + .notice') || {}).textContent || ''"


def test_history_ask_words(tmp_path, monkeypatch):
    """8.1's board (`AskWords.dc.html`, 1440; drawn under the Phase 7 mode after the row was
    built) beside the metrics builder's Ask in words row, on tests/test_ai_nl_query.py's site
    (the builder's stand-in Prometheus, hosted AI allowed, the adapter answering as planted):
    the row; filled; a question back; Mercury's own answer; refused; then hosted AI off."""
    from tests import ai_controls_check as AIC
    from tests import browser
    from tests import test_ai_nl_query as Q
    from tests import test_history_ask_metrics as HM

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    webs = HM.web.__wrapped__(tmp_path, monkeypatch)
    worlds = Q.world.__wrapped__(tmp_path, monkeypatch)
    site = Q.site.__wrapped__(next(webs), next(worlds), monkeypatch)
    w = site.world
    url = "/v2/history/query/ask/metrics?list=Lab"
    states = [
        ("row", None, "!!document.getElementById('lq-words')"),
        ("filled", _words_step(w, Q._choices(), "input errors per interface, the top 5"),
         f"/Filled from your words/.test({_W_NOTE})"),
        ("ask", _words_step(w, Q._choices(outcome="ask", metric="",
                                          question="Which device, or one line per device?"),
                            "average cpu usage over the past 7 days"),
         f"/One question first/.test({_W_NOTE})"),
        ("guide", _words_step(w, None, "how is the weather on r1"),
         f"/answered this itself/.test({_W_NOTE})"),
        ("refused", _words_step(w, Q._choices(metric="ifInErrorz"),
                                "input errors per interface, the top 5"),
         f"/Not filled/.test({_W_NOTE})")]
    import app as A
    try:
        with browser.Served(A.app) as served:
            _d_walk("history-ask-words", served, url, states,
                    boards=(("AskWords.dc.html", 1440),),
                    widths=((1440, 1.0), (1280, 1.0), (390, 2.0)))
            AIC.set_state(monkeypatch, "ai_off")
            _d_walk("history-ask-words-off", served, url, [
                ("off", None, "!!document.querySelector('[data-ai-off-reason=ask_in_words]')")],
                widths=((1440, 1.0), (390, 2.0)))
    finally:
        next(worlds, None)
        next(webs, None)


def test_history_ask_words_logs(tmp_path, monkeypatch):
    """8.1's board's last state beside the logs builder's Ask in words row, on
    tests/test_ai_nl_logs.py's world (the builder's stand-in Loki): the row, then filled."""
    from tests import browser
    from tests import test_ai_nl_logs as L
    from tests import test_history_ask_logs as HL

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    webs = HL.web.__wrapped__(tmp_path, monkeypatch)
    w = L.world.__wrapped__(next(webs), monkeypatch, tmp_path)
    import app as A
    try:
        with browser.Served(A.app) as served:
            _d_walk("history-ask-words-logs", served, "/v2/history/query/ask/logs?list=Lab", [
                ("row", None, "!!document.getElementById('lq-words')"),
                ("filled", _words_step(w, L._choices(range="7d"),
                                       "OSPF adjacency changes per device, last 7 days"),
                 f"/Filled from your words/.test({_W_NOTE})")],
                widths=((1440, 1.0), (390, 2.0)))
    finally:
        next(webs, None)


def test_history_metric(tmp_path, monkeypatch):
    """C667's board B (AskMetric, 1440) beside the metrics question, Grafana answering with a
    real capture (tests/fixtures/grafana/dsquery/throughput.json)."""
    from tests import browser
    from tests import test_history_query as Q

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules import device_page
    g = Q._Grafana()
    monkeypatch.setattr(device_page, "_cached", lambda name, list_name=None: (
        {"datasources": [{"uid": "prom", "type": "prometheus", "name": "Prometheus",
                          "isDefault": True}]}, "2026-10-11T09:00:00Z", ""))
    monkeypatch.setattr(device_page, "grafana_client", lambda list_name: g)
    import app as A
    with browser.Served(A.app) as served:
        _shoot("history-metric", "AskMetric.dc.html",
               lambda w: "/v2/history/query/metric/errors?range=30d", served,
               settled="!document.querySelector('.panel-wait')",
               widths=((1440, 1.0), (390, 2.0)))
        # Board A's CPU and memory question in board B's layout: per device, no interface.
        _shoot("history-metric-cpu", "", lambda w: "/v2/history/query/metric/cpu?d=r1&range=7d",
               served, settled="!document.querySelector('.panel-wait')",
               widths=((1440, 1.0), (390, 2.0)))


def test_topology(tmp_path, monkeypatch):
    """P.11's boards A (TopoDesktop, 1440) and B (TopoPhone, 390) beside the page, the reader's
    value built from the real captures (the lab as on the host: r5 retired, outside)."""
    from tests import browser
    from tests.test_topology_v2 import _store, _value

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    walked = os.environ.get("NMAS_BOARD_TOPOLOGY_DOC", "")
    if walked:
        # A walk: the reader's stored document as the host holds it (addresses taken out
        # before it left the host), drawn for the network it names.
        from modules import reader_job
        with open(walked, encoding="utf-8") as fh:
            doc = json.load(fh)
        name = next(iter(doc["last_good"]["value"]["networks"]))
        os.makedirs(os.path.dirname(reader_job.store_path("topology-graph")), exist_ok=True)
        with open(reader_job.store_path("topology-graph"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        monkeypatch.setattr("modules.nsot.listref.exists", lambda n: n == name)
        import app as A
        with browser.Served(A.app) as served:
            _shoot("topology-walk", "", lambda w: f"/v2/topology?list={name}", served,
                   widths=((1440, 1.0), (390, 2.0)))
        return
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    _store(_value())
    import app as A
    with browser.Served(A.app) as served:
        _shoot("topology-desktop", "TopoDesktop.dc.html", lambda w: "/v2/topology?list=Lab",
               served, widths=((1440, 1.0), (1280, 1.0)))
        _shoot("topology-phone", "TopoPhone.dc.html", lambda w: "/v2/topology?list=Lab",
               served, widths=((390, 2.0),))
        # The board's selected states: a link picked from the attention list (its card on the
        # desktop, its sheet on the phone), and the phone's Map tab.
        sel = "sel=r1%3AGi3~s1%3AGi0%2F2"
        _shoot("topology-desktop-sel", "", lambda w: f"/v2/topology?list=Lab&{sel}", served,
               widths=((1440, 1.0),))
        _shoot("topology-phone-sel", "", lambda w: f"/v2/topology?list=Lab&{sel}", served,
               widths=((390, 2.0),))
        _shoot("topology-phone-map", "", lambda w: "/v2/topology?list=Lab&tab=map", served,
               widths=((390, 2.0),))
        # Board D (C693, C694): r1 to r5's peering with r3, traced over the captured answers.
        from modules import path_trace as P
        from tests.test_path_trace import _reader
        net = _value()["networks"]["Lab"]
        got = P.trace("r1", "198.51.100.1", P.owners(net["nodes"], net["layers"]["bgp"]),
                      _reader("198.51.100.1"),
                      {n for n, v in net["nodes"].items() if v.get("managed")})
        P._write("Lab", {"id": "d" * 32, "state": "done", "source": "r1",
                         "dest": "198.51.100.1", "actor": "test-person@example.invalid",
                         "dest_words": "r5 (outside, AS 65002): 198.51.100.1, r3's peering",
                         "reading": [], "read": ["r1", "r3", "r4"], "runs": ["r-1", "r-2"],
                         "branches": got["branches"], "delivered": got["delivered"],
                         "started_at": time.time() - 20, "finished_at": time.time() - 15})
        path = f"a=r1&b=198.51.100.1&trace={'d' * 32}"
        _shoot("topology-path", "TopoPathTrace.dc.html",
               lambda w: f"/v2/topology?list=Lab&{path}", served,
               widths=((1440, 1.0), (1280, 1.0), (390, 2.0)))
        # Board E (C691): Snap to grid on.
        _shoot("topology-snap", "TopoSnap.dc.html", lambda w: "/v2/topology?list=Lab&snap=1",
               served, widths=((1440, 1.0), (1280, 1.0), (390, 2.0)))


def test_stepper(lab, monkeypatch):            # noqa: F811 (Save's lab, imported below)
    """THE stepper (2026-10-12; docs/fidelity/stepper.md) beside its boards: Save's running
    card, the one component, at the desk's 1440 beside `SaveProgress.dc.html` (C605) and at
    phone width beside `StepperPhone.dc.html`. Its rows are marked as Save's job keeps them
    (`save_op._mark`) and built by the real code (`save_page.job_card`); only the page's plan
    model is stood in for by that running card, as the page draws whichever card it is given."""
    from tests import browser

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules import save_page
    from modules.nsot import save_op

    job, t = "c" * 32, time.time() - 30
    for host, state, trail in (
            ("r1", "through", [["save", t], ["read_back", t + 4], ["read_running", t + 10],
                               ["commit_wait", t + 22]]),
            ("r2", "through", [["save", t], ["read_back", t + 3], ["read_running", t + 9],
                               ["commit_wait", t + 21]]),
            ("s1", "running", [["save", t], ["read_back", t + 9]]),
            ("r3", "running", [["save", t], ["read_back", t + 4], ["read_running", t + 10]]),
            ("r6", "waiting", []),
            ("s9", "not_persisted", [["save", t], ["read_back", t + 5]])):
        save_op._mark(job, host, state, trail=trail)
    card = save_page.job_card("Lab", job, {"state": "running", "elapsed_s": 41,
                                           "started_at": time.time() - 41})
    monkeypatch.setattr(save_page, "plan_card", lambda *a, **k: card)
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: True)
    import app as A
    with browser.Served(A.app) as served:
        _shoot("stepper-save", "SaveProgress.dc.html", lambda w: "/v2/devices/save?list=Lab",
               served, widths=((1440, 1.0), (1280, 1.0)))
        _shoot("stepper-phone", "StepperPhone.dc.html", lambda w: "/v2/devices/save?list=Lab",
               served, widths=((390, 2.0),))


from tests.test_save_v2 import lab  # noqa: E402,F401 (test_stepper's lab: Save's own)


def test_decline(tmp_path, monkeypatch):
    """C718 (board C603's C718 page, `CoverageDecline.dc.html`, approved 2026-10-13) beside
    Coverage as built: r2's real intent (tests/test_decline's lab), a section declined through
    the real apply (board C's row), r2's IP SLA as a row not in intent (board A: the row the IP
    SLA page's suggestion fills; planted, the lab having no IP SLA policy), then the Decline…
    card opened as its button opens it, its reason typed (board B). 1440 and phone width."""
    from tests import browser
    from tests import test_decline as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules import monitoring_coverage as MC
    from modules.nsot import decline, listref
    import routes.v2 as V

    lab_ = T.make_lab(tmp_path, monkeypatch)
    ref = listref.resolve(T.LIST)
    # Mgmt sources: a section r2's golden does not configure, so its decline draws (board C).
    e = decline.entry(T.LIST, T.HOST, "management", reason=T.WHY, actor="operator@example.com")
    assert decline.apply(T.LIST, T.HOST, "management", e["hash"], actor="operator@example.com",
                         reason=T.WHY, at=e["at"])["outcome"] == "declined"

    def coverage():
        c = MC.fleet(ref, devices=[(ref, dict(lab_["device"]))],
                     report=(None, "", "no reporting reader in this shot"))
        c["not_covered"] = [{"host": T.HOST, "section": "ip_sla", "suggested": True, "why": (
            "The profile's policy (upstream) suggests a probe of r2's static route's next "
            "hop, 192.0.2.1")}]
        return c

    monkeypatch.setattr(V, "_coverage", coverage)
    import app as A
    reason = T.WHY.replace(" ", "+").replace(";", "%3B").replace("'", "%27")
    card = f"/v2/monitoring/decline?list={T.LIST}&device={T.HOST}&section=ip_sla&reason={reason}"
    with browser.Served(A.app) as served, _Boards() as boards:
        for width, scale in ((1440, 1.0), (390, 2.0)):
            prefs = {"layout.css.devPixelsPerPx": str(scale)} if scale != 1.0 else {}
            with browser.Browser(prefs=prefs) as b:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": width, "height": 1000})
                b.go(boards.url("CoverageDecline.dc.html"))
                _full(b, os.path.join(OUT, f"decline-board-{width}.png"))
                b.go(served.url("/v2/monitoring/coverage"))
                if width < 480:
                    b.js(f"document.documentElement.style.maxWidth = '{width}px'; "
                         f"document.body.style.maxWidth = '{width}px'; return 1")
                _full(b, os.path.join(OUT, f"decline-page-{width}.png"))
                b.js("htmx.ajax('GET', arguments[0], {target: '#decline-card', "
                     "swap: 'outerHTML'}); return 1", served.url(card))
                b.wait_for("return !!document.querySelector('#decline-card .op-confirm')")
                _full(b, os.path.join(OUT, f"decline-card-page-{width}.png"))


# The screens built before the fidelity step (C650's UNCHECKED) that the operator walked in W1
# (2026-10-16), compared in groups. A board on the first canvas ("NMAS redesign mockups", the
# 2026-09-29/30 sign-offs) is read from the boards folder's `redesign/` (its Main, Logs and
# MonitoringQuery share names with the second canvas's).

# --- C650 group A: devices, bulk_intent ---

def _group_a_boards(name, board_file, widths):
    """A board alone at each width (the page is shot by `_group_a_page`)."""
    from tests.browser import Browser

    os.makedirs(OUT, exist_ok=True)
    with _Boards() as boards:
        for width, scale in widths:
            prefs = {"layout.css.devPixelsPerPx": str(scale)} if scale != 1.0 else {}
            with Browser(prefs=prefs) as b:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": width, "height": 1000})
                b.go(boards.url(board_file))
                _full(b, os.path.join(OUT, f"{name}-board-{width}.png"))


def _group_a_page(name, served, path, widths, act=None):
    """The page at each width, *act(b)* run on it first (a click, an htmx swap), as `_shoot`
    holds a phone's page to its column."""
    from tests.browser import Browser

    os.makedirs(OUT, exist_ok=True)
    settled = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
    for width, scale in widths:
        prefs = {"layout.css.devPixelsPerPx": str(scale)} if scale != 1.0 else {}
        with Browser(prefs=prefs) as b:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": width, "height": 1000})
            b.go(served.url(path))
            b.wait_for("return !!window.Alpine && " + settled, 15)
            if width < 480:
                b.js(f"document.documentElement.style.maxWidth = '{width}px'; "
                     f"document.body.style.maxWidth = '{width}px'; return 1")
            if act:
                act(b)
                b.wait_for("return " + settled, 15)
            _full(b, os.path.join(OUT, f"{name}-page-{width}.png"))
            if width < 480:
                png = b._call("GET", f"/session/{b.session}/screenshot")
                with open(os.path.join(OUT, f"{name}-page-{width}-first.png"), "wb") as fh:
                    fh.write(base64.b64decode(png))


def test_devices(lab, monkeypatch):            # noqa: F811 (Save's lab, imported above)
    """Devices (NSOT_GUI_BRIEF 13; the selection bar, Actions and Startup column from 7.4's
    board A, C593) beside `FleetSelect.dc.html` (1440) and the first canvas's
    `redesign/Devices.dc.html` (1440) and `redesign/DevicesPhone.dc.html` (390), on Save's lab
    (tests/test_save_v2.py: r2's real capture as its golden, r3 answering and not in the
    manifest, r4 not answering, s9 with no driver; the hourly startup check read r2 not saved
    and r3 saved). The page as it opens, and with r2 and r3 ticked and Actions open."""
    from tests import browser
    from tests.test_save_v2 import _startup_check

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules.nsot import listref

    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    _startup_check(lab, [{"list": "Lab", "device": "r2", "state": "not_persisted",
                          "detail": "the startup config does not carry username nmas"},
                         {"list": "Lab", "device": "r3", "state": "persisted"}])
    widths = ((1440, 1.0), (1280, 1.0), (390, 2.0))
    _group_a_boards("devices-fleetselect", "FleetSelect.dc.html", ((1440, 1.0), (1280, 1.0)))
    _group_a_boards("devices-redesign", "redesign/Devices.dc.html", ((1440, 1.0),))
    _group_a_boards("devices-phone", "redesign/DevicesPhone.dc.html", ((390, 2.0),))

    def tick_and_open(b):
        for host in ("r2", "r3"):
            b.click(f"#dev-{host}")
        b.wait_for("return document.querySelector('#dev-bar strong').textContent "
                   "=== '2 selected'", 5)
        b.click('#dev-bar button[aria-haspopup="menu"]')
        b.wait_for("var m=document.querySelector('#dev-bar [role=menu]'); "
                   "return m && m.offsetParent", 5)

    import app as A
    with browser.Served(A.app) as served:
        _group_a_page("devices", served, "/v2/devices", widths)
        _group_a_page("devices-selected", served, "/v2/devices", widths, act=tick_and_open)


def test_bulk_intent(tmp_path, monkeypatch):
    """Devices › Change a setting beside `BulkIntent.dc.html` (board D, 1440), on
    test_bulk_intent's lab (four devices' real fleet intent, the real render with a stub secret
    lookup; its fixture's own lines, inline here because Save's `lab` holds the name): the
    change as the Actions menu opens it for s1, s2 and r1 with tests/test_bulk_intent_v2.py's
    setting, its preview (s2 drifted, so refused naming both values), and the commit's result,
    each reached by its own button."""
    import subprocess

    from tests import browser
    from tests import test_bulk_intent as T
    from tests.test_bulk_intent_v2 import FLOW, KEPT

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from urllib.parse import urlencode

    from modules.nsot import hostvars, repo as R

    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost",
                            "nsot_device_tag_retention": 50}.get(key, default))
    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda c: None)
    repo = str(list_dir / "config_repo")
    R.init_repo(repo)
    for name in ("s1", "s2", "r1", "r3"):
        hostvars.write_committed(repo, T._old_shape_intent(name))
    R.save_host_vars("Lab", ["s1", "s2", "r1", "r3"], message="host_vars: seed", source="test")
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    monkeypatch.setattr("modules.device.get_device_lists",
                        lambda: [{"name": "Lab", "filename": "lab"}])
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: str(name) == "Lab")
    monkeypatch.setattr("routes.templatize._bulk_render_and_eligible",
                        lambda list_name, repo: (T._render, None))
    doc = hostvars.read_committed(repo, "s2")
    doc["logging"]["settings"] = ["trap errors"] + T.OLD_SETTINGS[1:]
    hostvars.write_committed(repo, doc)
    R.save_host_vars("Lab", ["s2"], message="host_vars: s2 drift", source="test")
    before = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
    path = "/v2/devices/change?" + urlencode(
        [("list", "Lab"), ("device", "s1"), ("device", "s2"), ("device", "r1"),
         ("summary", "drop the source interface"), ("path", "logging.settings"),
         ("before", FLOW), ("after", KEPT)])
    widths = ((1440, 1.0), (1280, 1.0), (390, 2.0))
    _group_a_boards("bulk-intent", "BulkIntent.dc.html", ((1440, 1.0),))

    def preview(b):
        b.click('#bulk-card button[data-op="bulk-intent"][type="submit"]')
        b.wait_for("var c=document.getElementById('bulk-card'); "
                   "return c && c.querySelector('[data-keep=bi-refused]')", 15)

    def opened(b):
        preview(b)
        b.js("document.querySelectorAll('#bulk-card details').forEach("
             "function (d) { d.open = true; }); return 1")

    def committed(b):
        preview(b)
        b.click('#bulk-card form[action$="/apply"] button[data-op="bulk-intent"]')
        b.wait_for("var c=document.getElementById('bulk-card'); "
                   "return c && c.textContent.indexOf('Committed') >= 0", 15)
        subprocess.run(["git", "-C", repo, "reset", "-q", "--hard", before], check=True)

    import app as A
    with browser.Served(A.app) as served:
        _group_a_page("bulk-intent-change", served, path, widths)
        _group_a_page("bulk-intent-preview", served, path, widths, act=preview)
        _group_a_page("bulk-intent-opened", served, path, ((1440, 1.0), (390, 2.0)), act=opened)
        _group_a_page("bulk-intent-result", served, path, ((1440, 1.0), (390, 2.0)),
                      act=committed)


# --- C650 group B: device ---

#: htmx at rest: a swapped-in control binds while it settles (the device-action tests' rule).
_DEVICE_SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
_DEVICE_CARD = "document.getElementById('device-op')"
_DEVICE_WIDTHS = ((1440, 1.0), (1280, 1.0), (390, 2.0))


def _device_fx(fixture, *args):
    """A device-action test's fixture, built by calling it: imported as a fixture its `lab`
    would shadow this file's (Save's)."""
    return fixture._get_wrapped_function()(*args)


def _device_boards(shots):
    """Each (shot name, board file, width, scale): the board alone, at its own width."""
    from tests.browser import Browser

    os.makedirs(OUT, exist_ok=True)
    with _Boards() as boards:
        for name, board_file, width, scale in shots:
            prefs = {"layout.css.devPixelsPerPx": str(scale)} if scale != 1.0 else {}
            with Browser(prefs=prefs) as b:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": width, "height": 1000})
                b.go(boards.url(board_file))
                _full(b, os.path.join(OUT, f"{name}-board-{width}.png"))


class _DevicePage:
    """One browser at one width on a device page: the page, then each action's card opened as
    its control opens it (a click on the control, or the control's own htmx request), each
    state shot whole; at phone width its first screen too."""

    def __init__(self, served, width, scale):
        self.served, self.width, self.scale = served, width, scale

    def __enter__(self):
        from tests.browser import Browser

        prefs = {"layout.css.devPixelsPerPx": str(self.scale)} if self.scale != 1.0 else {}
        self.cm = Browser(prefs=prefs)
        self.b = self.cm.__enter__()
        self.b._call("POST", f"/session/{self.b.session}/window/rect",
                     {"width": self.width, "height": 1000})
        return self

    def __exit__(self, *exc):
        from tests import browser
        try:
            self.b.go("about:blank")
            browser.close_socketio_sessions()
        finally:
            self.cm.__exit__(*exc)

    def open(self, path):
        b = self.b
        b.go(self.served.url(path))
        if self.width < 480:
            b.js(f"document.documentElement.style.maxWidth = '{self.width}px'; "
                 f"document.body.style.maxWidth = '{self.width}px'; return 1")
        b.wait_for("return !!window.Alpine && window.NMAS && "
                   "NMAS.live().state === 'connected' && " + _DEVICE_SETTLED, 20)

    def until(self, cond, timeout=30):
        self.b.wait_for(f"return ({cond}) && {_DEVICE_SETTLED}", timeout)

    def swap(self, url, until, method="GET", values=None, timeout=30):
        """The control's own request into the tab's place (`#tab-body`), as its hx-get does."""
        self.b.js("var t = document.getElementById('tab-body'); var m = "
                  "document.createElement('i'); m.id = 'shot-marker'; t.appendChild(m); "
                  "htmx.ajax(arguments[0], arguments[1], {target: '#tab-body', swap: "
                  "'innerHTML', values: arguments[2] || {}}); return 1", method, url, values)
        self.until(f"!document.getElementById('shot-marker') && ({until})", timeout)

    def click(self, css, until, timeout=30):
        self.b.js("var e = document.querySelector(arguments[0]); e.scrollIntoView("
                  "{block: 'center'}); e.click(); return 1", css)
        self.until(until, timeout)

    def menu(self):
        self.click('.page-actions button[aria-haspopup="menu"]',
                   "(function () { var m = document.querySelector('.page-actions [role=menu]');"
                   " return m && m.offsetParent !== null; })()", 10)

    def type(self, css, value, until, timeout=30):
        self.b.js("var i = document.querySelector(arguments[0]); i.value = arguments[1]; "
                  "i.dispatchEvent(new Event('input', {bubbles: true})); "
                  "i.dispatchEvent(new Event('change', {bubbles: true})); return 1", css, value)
        self.until(until, timeout)

    def shot(self, name):
        b = self.b
        b.js("window.scrollTo(0, 0); return 1")
        _full(b, os.path.join(OUT, f"{name}-page-{self.width}.png"))
        if self.width < 480:
            png = b._call("GET", f"/session/{b.session}/screenshot")
            with open(os.path.join(OUT, f"{name}-page-{self.width}-first.png"), "wb") as fh:
                fh.write(base64.b64decode(png))


def test_device_page(tmp_path, monkeypatch):
    """The device page's shell and Actions menu (redesign `Device`, 1440; `DevicePhone`, 390;
    the manual's board 7, `ActionsMenu`) and Capture (boards 1, 2 and 4), on test_capture's
    lab: r2's REAL configuration and committed intent, the device read replaced by r2 with
    `load-interval 30` on Gi2 (tests/test_device_capture_v2.py's lab and `_broken`). The card
    opened from the menu's row, the read run, the preview arriving by the job's announcement,
    the confirm clicked; then r2 moved before a confirm."""
    from tests import browser
    from tests import test_device_capture_v2 as T
    from tests.test_intent_match import _broken

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    lab = _device_fx(T.lab, tmp_path, monkeypatch)
    lab["running"]["r2"] = _broken(lab["captured"])
    _device_boards([("device", "redesign/Device.dc.html", 1440, 1.0),
                    ("device", "redesign/DevicePhone.dc.html", 390, 2.0),
                    ("device-menu", "ActionsMenu.dc.html", 1440, 1.0),
                    ("device-capture", "DevCapturePreview.dc.html", 1440, 1.0),
                    ("device-capture", "DevCapturePhone.dc.html", 390, 2.0),
                    ("device-capture-result", "DevCaptureResult.dc.html", 1440, 1.0)])
    ready = f"{_DEVICE_CARD} && {_DEVICE_CARD}.querySelector('.op-confirm')"
    import app as A
    with browser.Served(A.app) as served:
        for width, scale in _DEVICE_WIDTHS:
            with _DevicePage(served, width, scale) as p:
                p.open("/v2/device/r2")
                p.shot("device")
                p.menu()
                p.shot("device-menu")
                p.click('.page-actions a[data-op="capture"]', ready, 60)
                p.shot("device-capture")
        # The result, then r2 moving between a preview and its confirm (the board's second
        # card): the test's own move, load-interval 30 to 60.
        moved = _broken(lab["captured"]).replace("load-interval 30", "load-interval 60")
        for width, scale in ((1440, 1.0), (390, 2.0)):
            with _DevicePage(served, width, scale) as p:
                p.open("/v2/device/r2")
                p.swap("/v2/device/r2/capture?back=overview", ready, timeout=60)
                p.click("#device-op .op-confirm",
                        f"{_DEVICE_CARD} && /op-ok/.test({_DEVICE_CARD}.className)")
                p.shot("device-capture-result")
                if width == 1440:
                    lab["running"]["r2"] = moved
                    p.swap("/v2/device/r2/capture?back=overview", ready, timeout=60)
                    lab["running"]["r2"] = moved.replace("load-interval 60", "load-interval 90")
                    p.click("#device-op .op-confirm",
                            f"{_DEVICE_CARD} && /op-warn/.test({_DEVICE_CARD}.className)")
                    p.shot("device-capture-moved")
        # Inside a planned-restart window (C1025): the reachability reader's row for r2 says
        # not answering and a window covers it, so the real `answering` draws the header's
        # "Restarting as planned" chip (its words: tests/test_planned_restart_quiet.py).
        from modules import device_page

        cached = device_page._cached
        down = {"answering": False, "last_result": "missed", "since": "2026-10-17T00:08:02Z",
                "checked_at": "2026-10-17T00:09:02Z", "list": "Default"}   # the reader's row

        class _Every(dict):
            def __bool__(self):
                return True

            def get(self, key, default=None):
                return down

        monkeypatch.setattr(device_page, "_cached", lambda reader, *a, **k: (
            ({"devices": _Every()}, "2026-10-17T00:09:02Z", "") if reader == "reachability"
            else cached(reader, *a, **k)))
        monkeypatch.setattr(device_page, "_restarting", lambda host, list_name: {
            "words": "Restarting as planned (until 2026-10-17T00:27:47Z, by "
                     "person@example.invalid)", "until": "2026-10-17T00:27:47Z"})
        for width, scale in _DEVICE_WIDTHS:
            with _DevicePage(served, width, scale) as p:
                p.open("/v2/device/r2")
                p.shot("device-planned")


def test_device_deploy(tmp_path, monkeypatch):
    """Plan a deploy… (boards 5 and 6, and C506's `DeployExpected`) on the deploy tests' lab
    (tests/test_device_deploy_v2.py's `deploy`: r2's real capture, its golden lacking
    `lldp run` and carrying `load-interval 30`, its intent shutting Gi3), the device path spied
    as those tests spy it and held until the running card is shot: the card with the residue
    ticked and its reason, the dangerous line waiting on its own; then given, confirmed, the
    one stepper running, the result; and a failed verify rolled back."""
    import threading

    from tests import browser
    from tests import test_device_deploy_v2 as D
    from tests import test_profile_apply as P

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    lab = _device_fx(D.deploy, _device_fx(P.lab, monkeypatch, tmp_path), monkeypatch)
    sent = []
    D._spy(monkeypatch, sent_hash=sent)
    import routes.deploy as rd
    gate = {"open": threading.Event()}

    def held(spy):
        def one(*a, **k):
            gate["open"].wait(60)
            return spy(*a, **k)
        return one

    monkeypatch.setattr(rd, "_deploy_one", held(rd._deploy_one))
    _r, plain = D._get(lab, "/v2/device/r2/deploy?" + D._reasons()[1:])
    rid = D._residue_id(plain)
    from urllib.parse import quote
    ticked = f"/v2/device/r2/deploy?back=overview&rm={quote(rid)}&why::{quote(rid)}=" \
             "left+over+from+the+old+design"
    _r, card = D._get(lab, ticked + D._reasons())
    sent.append(D._vals(card)["command_hash"])
    _device_boards([("device-deploy", "DevDeployPreview.dc.html", 1440, 1.0),
                    ("device-deploy-expected", "DeployExpected.dc.html", 1440, 1.0),
                    ("device-deploy-result", "DevDeployResult.dc.html", 1440, 1.0)])
    stepper = f"{_DEVICE_CARD} && {_DEVICE_CARD}.querySelector('[data-run-stepper]')"
    confirm = f"{_DEVICE_CARD} && {_DEVICE_CARD}.querySelector('.op-confirm')"
    import app as A
    with browser.Served(A.app) as served:
        for width, scale in _DEVICE_WIDTHS:
            with _DevicePage(served, width, scale) as p:
                p.open("/v2/device/r2")
                p.swap(ticked, f"{_DEVICE_CARD} && "
                               f"{_DEVICE_CARD}.querySelector('input[name=\"dz::0\"]')")
                p.shot("device-deploy")
                if width == 1280:
                    continue
                p.swap(ticked + D._reasons(), confirm)
                p.shot("device-deploy-ready")
                gate["open"] = threading.Event()
                p.click("#device-op .op-confirm", stepper)
                p.shot("device-deploy-running")
                gate["open"].set()
                p.until(f"{_DEVICE_CARD} && /op-ok/.test({_DEVICE_CARD}.className)", 30)
                p.shot("device-deploy-result")
        D._spy(monkeypatch, outcome="failed", rollback={
            "state": "restored",
            "detail": "the rollback undid what landed and read r2 back as it was"})
        with _DevicePage(served, 1440, 1.0) as p:
            p.open("/v2/device/r2")
            p.swap(ticked + D._reasons(), confirm)
            p.click("#device-op .op-confirm",
                    f"{_DEVICE_CARD} && /Rolled back/.test({_DEVICE_CARD}.textContent)")
            p.shot("device-deploy-rolledback")


def test_device_rotate_persist(tmp_path, monkeypatch):
    """Rotate credential… (board 3) and Persist on test_persist_screen's lab with the rotate
    tests' fakes of the device-facing calls (tests/test_device_rotate_v2.py's `rot`): the card
    while another person's deploy holds r2 (its check failing by name), the same card once the
    hold is released (redrawn by the release's announcement), the result; Persist's card and
    its result. Persist's only board is the first canvas's `PersistRunningHelp`."""
    from tests import browser
    from tests import test_device_rotate_v2 as RV
    from tests import test_persist_effect as PE
    from tests import test_persist_screen as PS

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules.nsot import device_ops
    _device_fx(RV.rot, _device_fx(PS.lab, tmp_path, monkeypatch), monkeypatch)
    pair = PE._r2({"running": PE._read("r1", "show running-config"),
                   "startup": PE._read("r1", "show startup-config")}, "r1")
    running = pair["running"].replace("\nlogging trap notifications\n",
                                      "\nlogging trap informational\n")
    _device_boards([("device-rotate-held", "DevRotateHeld.dc.html", 1440, 1.0),
                    ("device-persist", "redesign/PersistRunningHelp.dc.html", 1440, 1.0)])
    checks = f"{_DEVICE_CARD} && {_DEVICE_CARD}.querySelector('.op-gates')"
    ready = f"{_DEVICE_CARD} && {_DEVICE_CARD}.querySelector('.op-confirm')"
    ok = f"{_DEVICE_CARD} && /op-(ok|warn|danger)/.test({_DEVICE_CARD}.className)"
    import app as A
    with browser.Served(A.app) as served:
        for width, scale in ((1440, 1.0), (390, 2.0)):
            with _DevicePage(served, width, scale) as p:
                device_ops.acquire("Lab", "r2", "deploy", "alex@example.invalid")
                try:
                    p.open("/v2/device/r2")
                    p.swap("/v2/device/r2/rotate?back=overview", checks)
                    p.shot("device-rotate-held")
                finally:
                    device_ops.release("Lab", "r2")
                p.until(ready, 30)
                p.shot("device-rotate")
                p.click("#device-op .op-confirm", ok)
                p.shot("device-rotate-result")
                # C886: Persist's part reads what saving changes; r2 answers with r1's real
                # pair (tests/test_persist_effect.py), one logging line changed in running.
                monkeypatch.setattr("modules.connection.with_temp_connection",
                                    lambda dev, fn: fn(PE.Device(running, pair["startup"])))
                p.swap("/v2/device/r2/persist?back=overview",
                       ready + " && document.querySelector('#persist-effect:not([aria-busy])')")
                p.shot("device-persist")
                p.click("#device-op .op-confirm", f"{_DEVICE_CARD} && "
                        f"/Recorded/.test({_DEVICE_CARD}.textContent)")
                p.shot("device-persist-result")


def test_in_progress(tmp_path, monkeypatch):
    """C537: the top bar's In progress chip (boards A, `TopBarDesktop`, and B, `TopBarPhone`)
    and a device page reopening its card (board C, `Reattach`), on test_persist_screen's lab
    with the rotate tests' fakes (tests/test_device_rotate_v2.py's `rot`), the rotation held at
    its first step until the test lets it go: nothing running; the rotation confirmed on r2's
    page and the person gone to Devices (the chip, its list opened); r2's page opened again
    (the running card reopened); the rotation finished while the person is on Devices (the
    chip's outcome, its list opened); r2's page opened again (the result reopened)."""
    import threading

    from tests import browser
    from tests import test_device_rotate_v2 as RV
    from tests import test_persist_screen as PS

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules.nsot import capture_job
    from modules.nsot import credential_rotation as cr
    _device_fx(RV.rot, _device_fx(PS.lab, tmp_path, monkeypatch), monkeypatch)
    monkeypatch.setattr("modules.integration_groups.network_names", lambda: ["Lab"])
    gate, real = threading.Event(), cr.rotate
    monkeypatch.setattr(cr, "rotate", lambda *a, **k: (gate.wait(120), real(*a, **k))[1])
    _device_boards([("in-progress", "TopBarDesktop.dc.html", 1440, 1.0),
                    ("in-progress-phone", "TopBarPhone.dc.html", 1440, 1.0),
                    ("reattach", "Reattach.dc.html", 1440, 1.0)])
    ready = f"{_DEVICE_CARD} && {_DEVICE_CARD}.querySelector('.op-confirm')"
    chip = "document.querySelector('#nmas-in-progress .ip-chip')"
    opened = "document.querySelector('#nmas-in-progress details[open] .ip-menu')"
    import app as A
    with browser.Served(A.app) as served:
        for width, scale in ((1440, 1.0), (390, 2.0)):
            gate.clear()
            with _DevicePage(served, width, scale) as p:
                p.open("/v2/devices")
                p.shot("in-progress-idle")
                p.open("/v2/device/r2")
                p.swap("/v2/device/r2/rotate?back=overview", ready)
                p.click("#device-op .op-confirm", f"{_DEVICE_CARD} && "
                        f"/Rotating/.test({_DEVICE_CARD}.textContent)")
                p.open("/v2/devices")
                p.until(chip, 15)
                p.click("#nmas-in-progress summary", opened, 10)
                p.shot("in-progress-running")
                p.open("/v2/device/r2")
                p.until("document.querySelector('.op-reopened')", 15)
                p.shot("reattach-running")
                p.open("/v2/devices")
                p.until(chip, 15)
                job = next(r["job"] for r in capture_job.card_jobs() if r["state"] == "running")
                gate.set()
                assert capture_job.wait(job, 30)
                p.until(f"{chip} && /ip-ok/.test({chip}.className)", 15)
                p.click("#nmas-in-progress summary", opened, 10)
                p.shot("in-progress-finished")
                p.open("/v2/device/r2")
                p.until("document.querySelector('.op-reopened')", 15)
                p.shot("reattach-result")


def test_device_seed(tmp_path, monkeypatch):
    """Seed intent… (board 8) on the seed tests' lab (tests/test_device_seed_v2.py's `lab`:
    r2's real golden, its intent only the bootstrap block): the card from the menu's row at
    each width, then the confirm and its result in place."""
    from tests import browser
    from tests import test_device_seed_v2 as S

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    _device_fx(S.lab, tmp_path, monkeypatch)
    _device_boards([("device-seed", "DevSeed.dc.html", 1440, 1.0)])
    ready = f"{_DEVICE_CARD} && {_DEVICE_CARD}.querySelector('.op-confirm')"
    import app as A
    with browser.Served(A.app) as served:
        for width, scale in _DEVICE_WIDTHS:
            with _DevicePage(served, width, scale) as p:
                p.open("/v2/device/r2")
                p.menu()
                p.shot("device-seed-menu")
                p.click('.page-actions a[data-op="seed"]', ready)
                p.shot("device-seed")
                if width == 390:
                    p.click("#device-op .op-confirm", f"{_DEVICE_CARD} && "
                            f"/Open in History/.test({_DEVICE_CARD}.textContent)")
                    p.shot("device-seed-result")


def test_device_restore(tmp_path, monkeypatch):
    """Restore from… (boards 9 and 10) on the restore tests' history (tests/
    test_device_restore_v2.py's `history`: three moments of r2, the middle one shutting Gi3),
    the device path spied and held until the running card is shot: the chooser, the middle
    moment's preview waiting on its reason, the moment before onboarding, the confirm, the
    result; and a program that moved (the test's own changed hash) refused."""
    import threading

    from tests import browser
    from tests import test_device_restore_v2 as RS
    from tests import test_profile_apply as P

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules.nsot.repo import git
    hist = _device_fx(RS.history, _device_fx(P.lab, monkeypatch, tmp_path), monkeypatch)
    RS._spy(monkeypatch)
    import routes.deploy as rd
    gate = {"open": threading.Event()}
    spy = rd._deploy_one

    def one(*a, **k):
        gate["open"].wait(60)
        return spy(*a, **k)

    monkeypatch.setattr(rd, "_deploy_one", one)
    first = git(hist["repo"], "tag", "--list", "golden/r2/*", "--sort=creatordate")[1].split()[0]
    _device_boards([("device-restore", "DevRestore.dc.html", 1440, 1.0),
                    ("device-restore-result", "DevRestoreResult.dc.html", 1440, 1.0)])
    card = _DEVICE_CARD
    preview = f"/v2/device/r2/restore/preview?back=overview&moment={hist['middle']}"
    import app as A
    with browser.Served(A.app) as served:
        for width, scale in _DEVICE_WIDTHS:
            with _DevicePage(served, width, scale) as p:
                p.open("/v2/device/r2")
                p.swap("/v2/device/r2/restore?back=overview",
                       f"{card} && {card}.querySelector('input[name=chosen]')")
                p.shot("device-restore-choose")
                p.b.js("Array.prototype.filter.call(document.querySelectorAll('#device-op "
                       "button'), function (x) { return /^Preview /.test(x.textContent.trim()); "
                       "})[0].click(); return 1")
                p.until(f"{card} && {card}.querySelector('input[name=\"dz::0\"]')")
                p.shot("device-restore")
                if width == 1280:
                    continue
                p.swap(f"/v2/device/r2/restore/preview?back=overview&moment={first}",
                       f"{card} && /onboard/i.test({card}.textContent)")
                p.shot("device-restore-before")
                p.swap(preview + RS._reason(), f"{card} && {card}.querySelector('.op-confirm')")
                gate["open"] = threading.Event()
                p.click("#device-op .op-confirm", f"{card} && {card}.querySelector("
                        "'[data-run-stepper]')")
                p.shot("device-restore-running")
                gate["open"].set()
                p.until(f"{card} && /Open in History/.test({card}.textContent)")
                p.shot("device-restore-result")
                if width == 1440:
                    p.swap(preview + RS._reason(),
                           f"{card} && {card}.querySelector('.op-confirm')")
                    p.b.js("var b = document.querySelector('#device-op .op-confirm'); var v = "
                           "JSON.parse(b.getAttribute('hx-vals')); v.command_hash = "
                           "'0000000000000000'; b.setAttribute('hx-vals', JSON.stringify(v)); "
                           "return 1")
                    p.click("#device-op .op-confirm",
                            f"{card} && /refused|Not sent/i.test({card}.textContent) && "
                            f"!{card}.querySelector('.op-confirm')")
                    p.shot("device-restore-moved")


def test_device_revert_retry(tmp_path, monkeypatch):
    """Revert intent… and Retry rolled-back change… (board 11) on the intent-ops lab with a
    rollback block recorded against change A (tests/test_device_revert_retry_v2.py's
    `blocked`): the menu offering both, the retry card waiting on its reason and then given
    one, the revert card and its result, and Retry once no block stands."""
    from tests import browser
    from tests import test_device_revert_retry_v2 as RR
    from tests import test_intent_ops as IO

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    lab = _device_fx(IO.lab, tmp_path, monkeypatch)
    lab = _device_fx(RR.page, _device_fx(IO.classify, lab, monkeypatch), monkeypatch)
    IO._note(lab, "blocking")
    _device_boards([("device-revert", "DevRevertRetry.dc.html", 1440, 1.0)])
    card = _DEVICE_CARD
    import app as A
    with browser.Served(A.app) as served:
        # The phone first: the desk's confirm reverts the blocked commit.
        for width, scale in ((390, 2.0), (1440, 1.0)):
            with _DevicePage(served, width, scale) as p:
                p.open("/v2/device/r2")
                p.menu()
                p.shot("device-revert-menu")
                p.click('.page-actions a[data-op="revert-retry"][href*="op=retry"]',
                        f"{card} && {card}.querySelector('input[name=reason]')")
                p.shot("device-retry")
                p.type("#device-op input[name=reason]",
                       "the neighbour's OSPF was down for the carrier's maintenance, unrelated",
                       f"{card} && {card}.querySelector('.op-confirm')")
                p.shot("device-retry-ready")
                p.swap("/v2/device/r2/revert?back=overview",
                       f"{card} && {card}.querySelector('.op-confirm')")
                p.shot("device-revert")
                if width == 1440:
                    p.click("#device-op .op-confirm",
                            f"{card} && /What happened/.test({card}.textContent)")
                    p.shot("device-revert-result")
                    p.swap("/v2/device/r2/retry?back=overview",
                           f"{card} && !{card}.querySelector('.op-confirm')")
                    p.shot("device-retry-none")


def test_device_retire(tmp_path, monkeypatch):
    """Retire… (board 12) on the retire tests' world (tests/test_device_retire_v2.py's `page`:
    r4 and r5 in 'Lab', a real repository, CSV, manifest and credential store, NetBox holding
    r5 by hand), a target directory naming both: the card refused while no break-glass export
    holds r5's credential, the card once one does, the confirm and its result; then r5's
    address, the retired record (board 12's last card, `retired.html`)."""
    from urllib.parse import quote

    from tests import browser
    from tests import test_device_retire_v2 as RV
    from tests import test_retire as RT
    from tests import test_retire_screen as RS

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    world = _device_fx(RT.world, tmp_path, monkeypatch)
    page = _device_fx(RV.page, _device_fx(RS.screen, world, tmp_path, monkeypatch), monkeypatch)
    RV._targets(monkeypatch, tmp_path, [("r4", "192.0.2.14"), ("r5", "192.0.2.15")])
    _device_boards([("device-retire", "DevRetire.dc.html", 1440, 1.0)])
    card = _DEVICE_CARD
    url = f"/v2/device/r5/retire?back=overview&reason={quote(RS.REASON)}"
    import app as A
    with browser.Served(A.app) as served:
        with _DevicePage(served, 1440, 1.0) as p:
            p.open("/v2/device/r5")
            p.swap(url, f"{card} && {card}.querySelector('.op-gates')")
            p.shot("device-retire-refused")
        RS._export(page)
        # The phone first: the desk's confirm retires r5.
        for width, scale in ((390, 2.0), (1440, 1.0)):
            with _DevicePage(served, width, scale) as p:
                p.open("/v2/device/r5")
                p.swap(url, f"{card} && {card}.querySelector('.op-confirm')")
                p.shot("device-retire")
                if width == 1440:
                    RV._targets(monkeypatch, tmp_path, [("r4", "192.0.2.14")])
                    p.click("#device-op .op-confirm",
                            f"{card} && /What happened/.test({card}.textContent)")
                    p.shot("device-retire-result")


# --- C650 group C: device tabs overview, ask ---

def test_tab_ask(tmp_path, monkeypatch):
    """tab:ask beside board A (ReadsAsk: idle, refused as typed, the answer, the comparison,
    the device held), E (ReadsPhone, 390), C582's reason field (ReadsReasonC582) and T2-A to
    T2-D (Tier2Privileged: the card's choose, preview, result and changes-nothing states), on
    test_device_v2's lab (r3), the device faked at the connection seam answering from r3's real
    captures (tests/test_ask_the_device's and tests/test_privileged's). The comparison's
    earlier answer is r3's `show ip ospf neighbor` capture with one neighbour's state edited
    (FULL/BDR to 2WAY/DROTHER), said so."""
    from urllib.parse import quote

    from tests import browser
    from tests import test_ask_the_device as TA
    from tests import test_privileged as TP

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    lab_ = _c_device_lab(tmp_path, monkeypatch)
    from modules.nsot import device_ops, reads
    dev = TA.Device()
    ospf = TA._text("operational", "r3__show_ip_ospf_neighbor.txt")
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, c, **kw: conn.answer(c))
    who = "operator@example.com"
    dev.answers["show ip ospf neighbor"] = ospf.replace("200   FULL/BDR    ",
                                                        "200   2WAY/DROTHER")
    reads.run("Lab", ["r3"], ["show ip ospf neighbor"], who, session=dev)
    dev.answers["show ip ospf neighbor"] = ospf
    done = reads.run("Lab", ["r3"], ["show ip ospf neighbor"], who, session=dev)["id"]
    with device_ops.hold("Lab", "r3", "deploy", "a-person@example.com", detail="a deploy"):
        held = reads.run("Lab", ["r3"], ["show ip interface brief"], who, session=dev)["id"]
    base = "/v2/device/r3?tab=ask"
    import app as A
    with browser.Served(A.app) as served:
        _shoot("tab-ask", "ReadsAsk.dc.html", lambda w: base, served,
               widths=((1440, 1.0), (1280, 1.0)))
        _shoot("tab-ask-refused", "", lambda w: base + "&command=" + quote(
            "show running-config | redirect flash:x"), served, widths=((1440, 1.0),))
        _shoot("tab-ask-answer", "ReadsPhone.dc.html", lambda w: f"{base}&run={done}", served,
               widths=((1440, 1.0), (390, 2.0)))
        _shoot("tab-ask-compare", "", lambda w: f"{base}&run={done}&compare=" + quote(
            "show ip ospf neighbor"), served, widths=((1440, 1.0), (390, 2.0)))
        _shoot("tab-ask-held", "", lambda w: f"{base}&run={held}", served,
               widths=((1440, 1.0),))
        _shoot("tab-ask-reason", "ReadsReasonC582.dc.html", lambda w: base + "&command=" + quote(
            "send log 1 MERCURY TEST alert rule check"), served, widths=((1440, 1.0), (390, 2.0)))
        # Tier 2 (T2-A to T2-D): the card as its Actions row opens it, in place of the tab.
        t2 = TP.t2.__wrapped__(lab_, monkeypatch)
        s = t2["session"]
        s.reads["show interfaces GigabitEthernet2"] = [TP.COUNTERS_BEFORE, TP.COUNTERS_BEFORE,
                                                       TP.COUNTERS_AFTER]
        s.sends["clear counters GigabitEthernet2"] = TP.P.COUNTERS_PROMPT
        s.reads["show debugging"] = TP._cap(TP.OPS, "r2__show_debugging.txt")
        run = reads.run("Lab", ["r3"], ["show interfaces GigabitEthernet2"], who,
                        session=s)["id"]
        dbg = reads.run("Lab", ["r3"], ["show debugging"], who, session=s)["id"]
        op = "/v2/device/r3?op=privileged&list=Lab"
        cc = "&key=clear-counters&arg=GigabitEthernet2"
        _shoot("tab-ask-t2-choose", "Tier2Privileged.dc.html", lambda w: op, served,
               widths=((1440, 1.0), (390, 2.0)))
        _shoot("tab-ask-t2-preview", "", lambda w: f"{op}{cc}&run={run}", served,
               widths=((1440, 1.0), (390, 2.0)))
        _shoot("tab-ask-t2-nothing", "", lambda w: f"{op}&key=undebug-all&arg=&run={dbg}",
               served, widths=((1440, 1.0),))
        h = TP.P.plan("Lab", "r3", "clear-counters", "GigabitEthernet2")["hash"]
        rec = TP.P.apply("Lab", "r3", "clear-counters", "GigabitEthernet2", actor=who,
                         confirmed_hash=h, reason=TP.REASON)
        _shoot("tab-ask-t2-result", "", lambda w: f"{op}{cc}&result={rec['id']}", served,
               widths=((1440, 1.0), (390, 2.0)))


def _c_device_lab(tmp_path, monkeypatch):
    """Group C's lab: tests/test_device_v2's (r3 with r2's real config as its committed golden,
    Grafana's captured dashboards stored by the real reader, r3 answering), its fixture's body
    run directly (the module's `lab` is Save's)."""
    from tests import test_device_v2 as D
    gen = D.lab.__wrapped__(tmp_path, monkeypatch)
    return next(gen)


def test_tab_overview(tmp_path, monkeypatch):
    """tab:overview beside Device (its content under the tabs), DevicePhone, and the folded
    boards (DeviceOverviewFolded, PhoneFolded), on the browser layout test's lab (tests/
    test_profile_apply's: r2's real configuration as its golden and its parsed intent
    committed; r6 in its real shape), r2 answering in the reachability store; then r6 with
    `cdp run` in its golden and not in its intent (tests/test_overview_intent's case)."""
    from tests import browser
    from tests import test_device_v2 as D
    from tests import test_overview_intent as O
    from tests import test_profile_apply as P
    from tests import test_v2_layout_in_a_browser as L

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    lab_ = P.lab.__wrapped__(monkeypatch, tmp_path)
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(L.R2), dict(L.R6)])
    now = time.time()
    iso = lambda s: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - s))  # noqa: E731
    D._store("reachability", {"devices": {
        a: {"answering": True, "since": iso(86400 * 2), "checked_at": iso(4),
            "last_result": "answered"} for a in (L.R2["ip"], L.R6["ip"])}}, at=iso(4))
    O._give_r6(lab_, "cdp run\n")
    import app as A
    with browser.Served(A.app) as served:
        _shoot("tab-overview", "redesign/Device.dc.html", lambda w: "/v2/device/r2", served,
               widths=((1440, 1.0), (1280, 1.0)))
        _shoot("tab-overview", "redesign/DevicePhone.dc.html", lambda w: "/v2/device/r2",
               served, widths=((390, 2.0),))
        _shoot("tab-overview-folded", "redesign/DeviceOverviewFolded.dc.html",
               lambda w: "/v2/device/r6", served, widths=((1440, 1.0),))
        _shoot("tab-overview-folded", "redesign/PhoneFolded.dc.html",
               lambda w: "/v2/device/r6", served, widths=((390, 2.0),))


def test_tab_overview_drift(tmp_path, monkeypatch):
    """C342 (board C342Drift, 1440) beside r3's Overview on test_device_v2's lab: the REAL drift
    run with two minimal edits of r2's real configuration (tests/test_drift_overview's), the
    Drift row closed, then opened (the kept lines masked, s3's real log lines as r3's, the three
    choices); then the drift record unreadable."""
    from tests import browser
    from tests import test_device_v2 as D
    from tests import test_drift_overview as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    lab_ = D.lab_setup(tmp_path, monkeypatch)
    next(lab_)
    T._drift(monkeypatch)
    T.loki.__wrapped__(monkeypatch)
    T._at_the_corpus(monkeypatch)
    monkeypatch.setattr("modules.device_page._epoch", lambda iso: None)
    from modules import drift_check
    state = drift_check._state_file("Lab")
    with open(state, encoding="utf-8") as fh:
        good = fh.read()

    def write(text, b):
        with open(state, "w", encoding="utf-8") as fh:
            fh.write(text)
        b.go(served.url("/v2/device/r3?list=Lab"))

    def closed(b):
        write(good, b)

    def unreadable(b):
        write('{"last_result": {"drifted_devices": [', b)

    states = [("closed", closed, "document.querySelector('details.drift-open')"),
              ("open", "document.querySelector('details.drift-open').open = true",
               "document.querySelector('.drift-parts')"),
              ("unreadable", unreadable, "document.querySelector('.check-unreadable')")]
    import app as A
    with browser.Served(A.app) as served:
        _d_walk("tab-overview-drift", served, "/v2/device/r3?list=Lab", states,
                boards=(("C342Drift.dc.html", 1440),),
                widths=((1440, 1.0), (1280, 1.0), (390, 2.0)))


# --- C650 group D: tab intent, tab history, history ---

_D_SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


def _d_walk(name, served, url, states, boards=(),
            widths=((1440, 1.0), (1280, 1.0), (390, 2.0))):
    """Group D's walk: at each width, the boards drawn at that width (each board a (file,
    width) pair), then the page at *url* and, in turn, each state of *states* (label, a JS
    step run on the page, a Python step given the browser, or None; a JS condition that says
    the state is drawn; or a function of the width giving them), each shot as
    `<name>-<label>-page-<width>.png`."""
    from tests.browser import Browser

    os.makedirs(OUT, exist_ok=True)
    with _Boards() as bs:
        for width, scale in widths:
            prefs = {"layout.css.devPixelsPerPx": str(scale)} if scale != 1.0 else {}
            with Browser(prefs=prefs) as b:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": width, "height": 1000})
                for board, at in boards:
                    if at != width:
                        continue
                    b.go(bs.url(board))
                    _full(b, os.path.join(OUT, f"{name}-board-{board.split('/')[-1][:-8]}-"
                                               f"{width}.png"))
                if not url:
                    continue
                b.go(served.url(url))
                for label, step, drawn in (states(width) if callable(states) else states):
                    if callable(step):
                        step(b)
                    elif step:
                        b.js(step + "; return 1")
                    b.wait_for(f"return ({drawn}) && {_D_SETTLED}", 20)
                    time.sleep(0.3)
                    if width < 480:
                        b.js(f"document.documentElement.style.maxWidth = '{width}px'; "
                             f"document.body.style.maxWidth = '{width}px'; return 1")
                    _full(b, os.path.join(OUT, f"{name}-{label}-page-{width}.png"))


def test_tab_intent(monkeypatch, tmp_path):
    """C650 group D, tab:intent: H, the one intent editor (boards DevIntentEdit,
    DevIntentFields, DevIntentStates, DevIntentDiffs; 7.4 Fleet page) beside r2's Intent tab on
    the browser layout test's lab (tests/test_profile_apply's: r2's captured configuration, its
    intent parsed from it): the read-only card, Edit opened and checked, a description edited,
    an error typed, then committed; and, apart, intent moved under an open edit."""
    from tests import browser
    from tests import test_profile_apply as P
    from tests import test_v2_layout_in_a_browser as L

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    P.lab.__wrapped__(monkeypatch, tmp_path)
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(L.R2), dict(L.R6)])
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    from modules.nsot import intent_edit
    opened = intent_edit.open_doc("Lab", "r2")
    text = opened["yaml"]
    assert "description: " in text, text[:400]
    # The extraction records r2's syslog block as the device holds it, with no heartbeat
    # (C490); an authored document carries it whole, so it is given one first, as a person
    # does in tests/test_intent_editor_v2's browser walk.
    fixed = (text.replace("heartbeat: 0", "heartbeat: 300") if "heartbeat: 0" in text
             else text.replace("  syslog:\n", "  syslog:\n    heartbeat: 300\n", 1))
    got = intent_edit.commit("Lab", "r2", fixed, "the syslog heartbeat", opened["base"],
                             "operator@example.com")
    assert got["ok"], got
    ta = "var t = document.querySelector('#ie-text'); "
    typed = ("t.dispatchEvent(new Event('input', {bubbles: true}))")
    checked = ("!!document.querySelector('#ie-check .ie-col, #ie-check .ie-err')")

    def edit(width):
        # Loopback0's description, a value of its own at each width (each width commits).
        return (ta + "t.value = t.value.replace(/description: mgmt identity.*/, "
                     f"'description: mgmt identity w{width}'); " + typed)

    def edited(width):
        return (f"!!document.querySelector('#ie-check .ie-col') && /identity w{width}/"
                ".test(document.querySelector('#ie-check').textContent)")

    bad = (ta + "t.value = t.value.replace(/\\n/, '\\nshutdown: [yes please\\n'); " + typed)
    unbad = (ta + "t.value = t.value.replace('\\nshutdown: [yes please', ''); " + typed)
    commit = ("document.querySelector('#intent-form input[name=summary]').value = "
              "'the uplink\\'s real description'; "
              "document.querySelector('#intent-form button[data-op=\"edit-intent\"]').click()")

    def states(width):
        return [
            ("view", None, "!!document.querySelector('#intent .intent-doc')"),
            ("open", "document.querySelector('.card-head a[data-op=\"edit-intent\"]').click()",
             checked),
            ("edited", edit(width), edited(width)),
            ("error", bad, "!!document.querySelector('#ie-check .ie-err')"),
            ("fixed", unbad, edited(width)),
            ("done", commit, "/Committed to r2's intent/.test(document.body.textContent)"),
        ]

    import app as A
    with browser.Served(A.app) as served:
        _d_walk("tab-intent", served, "/v2/device/r2?tab=intent", states,
                boards=(("DevIntentEdit.dc.html", 1440), ("DevIntentFields.dc.html", 1440),
                        ("DevIntentStates.dc.html", 1440), ("DevIntentDiffs.dc.html", 1440)))
        # Intent moved under an open edit (board H's state 3): another person commits a
        # different line between the open and the commit.
        from tests.browser import Browser
        with Browser() as b:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
            b.go(served.url("/v2/device/r2?tab=intent&edit=1"))
            b.wait_for(f"return {checked} && {_D_SETTLED}", 20)
            opened = intent_edit.open_doc("Lab", "r2")
            theirs = opened["yaml"].replace("domain_name: example.com",
                                            "domain_name: lab.example", 1)
            assert theirs != opened["yaml"]
            assert intent_edit.commit("Lab", "r2", theirs, "their change", opened["base"],
                                      "other@example.com")["ok"]
            b.js(edit(1) + "; return 1")
            b.wait_for(f"return {edited(1)} && {_D_SETTLED}", 20)
            b.js(commit + "; return 1")
            b.wait_for(f"return /not saved/.test(document.body.textContent) && {_D_SETTLED}",
                       20)
            _full(b, os.path.join(OUT, "tab-intent-moved-page-1440.png"))
        # C884: a commit deleting a line r2 holds (Loopback0's description), which a merge-only
        # deploy keeps: the deploy's lines, and apart, the line only r2 holds with Remove
        # lines (Mode B)… beside it.
        with Browser() as b:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
            b.go(served.url("/v2/device/r2?tab=intent&edit=1"))
            b.wait_for(f"return {checked} && {_D_SETTLED}", 20)
            b.js(ta + "t.value = t.value.replace(/description: mgmt identity.*/, "
                      "\"description: ''\"); " + typed + "; return 1")
            b.wait_for("return !!document.querySelector('#ie-check .ie-keep') && "
                       + _D_SETTLED, 20)
            b.js(commit + "; return 1")
            b.wait_for("return /What a deploy keeps/.test(document.body.textContent) && "
                       + _D_SETTLED, 20)
            _full(b, os.path.join(OUT, "tab-intent-departs-page-1440.png"))


def _d_history_lab(tmp_path, monkeypatch):
    """r3's records on tests/test_device_v2's lab, written by the real paths as
    tests/test_device_history_v2 writes them: its golden (r2's real configuration, Source:
    capture), an intent commit, a deploy receipt and a failed one. Returns the lab's
    generator, to be closed after the shots."""
    from tests import test_device_history_v2 as H
    from tests import test_device_v2 as DV

    gen = DV.lab.__wrapped__(tmp_path, monkeypatch)
    lab_ = next(gen)
    H._intent_commit(lab_)
    H._receipt(outcome="failed", reason="verify did not pass: 1 line not read back",
               at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 5)))
    H._receipt(at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 9)))
    return gen


_D_ROWS = "!!document.querySelector('.hist-tl details.tl-row')"
_D_OPEN = "document.querySelector('.hist-tl details.tl-row').open = true"


def test_monitoring_alerts_explain(tmp_path, monkeypatch):
    """P1's Alerts tab (PHASE8_PLAN 15.9) beside its board, owed since 15.12 and drawn
    2026-10-26 (`AlertsExplain.dc.html`, 1440): tests/v2_context.py's `_alert_evidence` set-up
    (r3's real heartbeat instance and a silenced syslog instance firing, each pack built by the
    real trigger over the Loki and Prometheus captures), on test_device_v2's lab; the tab, the
    first card opened, and Explain pressed with hosted AI allowed and an answer planted."""
    import json as _json
    import tempfile

    from modules import evidence_pack as EP
    from modules import history_logq as Q
    from modules import reader_job, settings_schema
    from modules.ai import anthropic_adapter, calls, gateway
    from modules.readers import grafana_alerts as G
    from tests import browser
    from tests import test_device_v2 as DV
    from tests import test_evidence_pack as T
    from tests import test_grafana_reader as GR

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    gen = DV.lab.__wrapped__(tmp_path, monkeypatch)
    next(gen)
    folder = tempfile.mkdtemp(prefix="nmas-shots-packs-", dir=str(tmp_path))
    monkeypatch.setattr(EP, "_path", lambda: os.path.join(folder, "evidence_packs.jsonl"))
    monkeypatch.setattr(EP, "_alert_stores", lambda: ["grafana-alerts-walk"])
    monkeypatch.setattr(reader_job, "store_path",
                        lambda name: os.path.join(folder, "readers", f"{name}.json"))
    monkeypatch.setattr(Q, "_client", lambda *a, **k: T.DeviceLoki())
    T._prometheus(monkeypatch)
    os.makedirs(os.path.join(folder, "readers"))
    value = T._alerts(heartbeat=True)
    view, am = GR.silenced_syslog()
    value["instances"] += G.parse(GR.load("ruler"), view, am, GR.READ_AT,
                                  silences=[GR.SILENCE])["instances"]
    with open(reader_job.store_path("grafana-alerts-walk"), "w", encoding="utf-8") as fh:
        _json.dump({"last_good": {"value": value, "value_at": "2026-10-15T08:24:00Z"}}, fh)
    assert EP.after_alerts_read(clock=lambda: T.NOW)
    pack = EP.read()["rows"][-1]
    cite = next(s["ref"] for s in pack["sections"] if s["name"] == "alert")
    answer = {"outcome": "answer", "rationale": "The heartbeat stopped while the device was up.",
              "hypotheses": [{"claim": "The device stopped sending its heartbeat.",
                              "evidence_refs": [cite],
                              "confirm_with": "show logging | include HEARTBEAT"}],
              "checked": [], "needs_human": True, "why_not": ""}
    allowed = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                             "reason": "the shot's planted answer"}, "ai_cap_usd_per_day": 1.5}
    real_get = settings_schema.get_setting
    monkeypatch.setattr(settings_schema, "get_setting",
                        lambda k, d=None: allowed[k] if k in allowed else real_get(k, d))
    monkeypatch.setattr(gateway, "_api_key", lambda: "sk-planted-shot-key-0123456789")
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    monkeypatch.setattr(calls, "_path", lambda: os.path.join(folder, "ai_calls.jsonl"))
    monkeypatch.setattr(anthropic_adapter, "send", lambda body, key: anthropic_adapter.Reply(
        status=200, body={"content": [{"type": "text", "text": _json.dumps(answer)}],
                          "stop_reason": "end_turn",
                          "usage": {"input_tokens": 4000, "output_tokens": 200}},
        attempts=1, latency_s=0.5))
    card = "document.querySelector('details.pack-card')"
    try:
        import app as A
        _d_walk("alerts-explain", None, "", [], boards=(("AlertsExplain.dc.html", 1440),),
                widths=((1440, 1.0),))
        with browser.Served(A.app) as served:
            _d_walk("alerts-explain", served, "/v2/monitoring/alerts", [
                ("tab", None, f"!!{card}"),
                ("open", f"{card}.open = true",
                 f"!!{card}.querySelector('[data-op=\"alert-evidence\"]')"),
                ("explained", f"{card}.querySelector('[data-op=\"alert-evidence\"]').click()",
                 f"/The device stopped sending its heartbeat/.test({card}.textContent)")],
                widths=((1440, 1.0), (1280, 1.0), (390, 2.0)))
    finally:
        next(gen, None)


def test_tab_intent_words(tmp_path, monkeypatch):
    """Feature 7 (PHASE8_PLAN 15.16): board F7 (`IntentWords.dc.html`, 1440) beside s1's Intent
    tab on the host's real committed lab (tests/test_committed_before_p1's `host`): the row
    drawn, then a sentence drafted (hosted AI allowed, the adapter answering as planted) and
    previewed by the intent editor in place."""
    import json as _json
    from tests import browser
    from tests import test_ai_intent_change as F
    from tests import test_committed_before_p1 as P

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    host = P.host.__wrapped__(monkeypatch, tmp_path)
    world = F.world.__wrapped__(host, monkeypatch, tmp_path)
    world.answer = F.DESCRIBE
    row = "document.getElementById('intent-words')"
    draft = ("var i = document.getElementById('iw-words'); "
             "i.value = 'describe GigabitEthernet0/1 as uplink to edge1'; "
             "i.form.querySelector('button[type=submit]').click()")
    _d_walk("tab-intent-words", None, "", [], boards=(
        ("IntentWords.dc.html", 1440),), widths=((1440, 1.0),))
    with browser.Served(host["app"]) as served:
        _d_walk("tab-intent-words", served, "/v2/device/s1?tab=intent&list=Lab", [
            ("row", None, f"!!{row}"),
            ("drafted", draft, f"/Drafted from your words/.test({row}.textContent)")],
            widths=((1440, 1.0), (1280, 1.0), (390, 2.0)))
    assert _json.dumps(world.sent[-1]["body"]).count("uplink to edge1") >= 1


def test_tab_history(tmp_path, monkeypatch):
    """C650 group D, tab:history: board D (`HistoryTimeline.dc.html`, 1280; signed off
    2026-10-03, "a device tab is the same timeline filtered to the device") beside r3's
    History tab, r3's real records (`_d_history_lab`), its rows closed and the newest
    opened."""
    from tests import browser

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    gen = _d_history_lab(tmp_path, monkeypatch)
    try:
        import app as A
        with browser.Served(A.app) as served:
            _d_walk("tab-history", served, "/v2/device/r3?tab=history", [
                ("rows", None, _D_ROWS), ("open", _D_OPEN, _D_ROWS)],
                boards=(("HistoryTimeline.dc.html", 1280),),
                widths=((1280, 1.0), (1440, 1.0), (390, 2.0)))
    finally:
        next(gen, None)


def test_history(tmp_path, monkeypatch):
    """C650 group D, history.html: boards D (`HistoryTimeline.dc.html`, 1280), the earlier
    History board (`History.dc.html`, 1280) and 7.5's identity line
    (`HistoryIdentity.dc.html`, 1440) beside History: the same real records as r3's tab
    (`_d_history_lab`); then the browser layout test's widest timeline
    (tests/test_v2_layout_in_a_browser's `_timeline`: a denied decision, a nine-device
    golden marked known wrong, the identity line counting 52 commits), a row opened, the
    identity filter on, and the Baselines tab on its `BASELINES`."""
    from tests import browser
    from tests import test_v2_layout_in_a_browser as L

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    gen = _d_history_lab(tmp_path, monkeypatch)
    try:
        import app as A
        with browser.Served(A.app) as served:
            _d_walk("history-real", served, "/v2/history?since=", [("rows", None, _D_ROWS)],
                    widths=((1280, 1.0),))
            from modules import reader_job
            from routes import v2
            monkeypatch.setattr(v2, "_history_timeline", L._timeline)
            real = reader_job.read_cached
            monkeypatch.setattr(reader_job, "read_cached", lambda name: (
                L.BASELINES if name == "baseline-usability" else real(name)))
            _d_walk("history", served, "/v2/history", [
                ("rows", None, _D_ROWS), ("open", _D_OPEN, _D_ROWS)],
                boards=(("HistoryTimeline.dc.html", 1280), ("History.dc.html", 1280),
                        ("HistoryIdentity.dc.html", 1440)),
                widths=((1280, 1.0), (1440, 1.0), (390, 2.0)))
            _d_walk("history-unverified", served, "/v2/history?identity=unverified",
                    [("rows", None, _D_ROWS)], widths=((1440, 1.0),))
            _d_walk("history-kinds", served, "/v2/history", [(
                "menu", "document.querySelector('details.hist-kinds').open = true",
                "!!document.querySelector('details.hist-kinds[open]')")],
                widths=((1280, 1.0),))
            _d_walk("history-baselines", served, "/v2/history?tab=baselines", [
                ("rows", None, "!!document.querySelector('.hist-bl details')")],
                widths=((1280, 1.0), (390, 2.0)))
    finally:
        next(gen, None)


def test_history_ai_call(tmp_path, monkeypatch):
    """15.14 (the operator, 2026-10-26): an AI call's row on History, opened, and "Show the
    prompt and the answer" pressed, the window drawn as a commit's "Show the change" is. No
    board draws an AI call (the kind is later than board D). Fed by tests/test_ai_explain's
    world (the real builder's pack, Explain's real request, a planted answer, recorded by the
    gateway), its fixtures chained by hand: this module's `lab` is test_save_v2's."""
    from tests import browser
    from tests import test_ai_explain as X
    from tests import test_device_v2 as DV
    from tests import test_evidence_pack as EP

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    gen = DV.lab.__wrapped__(tmp_path, monkeypatch)
    packs = EP.pack_lab.__wrapped__(next(gen), tmp_path, monkeypatch)
    w = X.world.__wrapped__(next(packs), monkeypatch, tmp_path)
    w.answer = X._answer(w.pack)
    assert X._explain(w)["ok"] is True
    row = "document.querySelector('.hist-tl details.tl-row[data-kind=\"ai_call\"]')"
    try:
        import app as A
        with browser.Served(A.app) as served:
            _d_walk("history-ai-call", served, "/v2/history?kind=ai_calls&since=", [
                ("rows", None, f"!!{row}"),
                ("open", f"{row}.open = true; {row}.querySelector('[id^=\"ai-\"] button').click()",
                 f"!!{row}.querySelector('.hist-ai')")],
                widths=((1280, 1.0), (390, 2.0)))
            # The device's History tab: the same rows, the calls whose subject names it.
            _d_walk("tab-history-ai-call", served, "/v2/device/r1?tab=history", [
                ("open", f"{row}.open = true; {row}.querySelector('[id^=\"ai-\"] button').click()",
                 f"!!{row} && !!{row}.querySelector('.hist-ai')")],
                widths=((1280, 1.0),))
    finally:
        next(packs, None)
        next(gen, None)


# --- C650 group E2: credentials ---

_E2_SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


def _e2_walk(name, served, states, widths, boards=()):
    """Group E2's walk: at each width, each board whose own width it is (*boards*: (file,
    width)), then each state in turn (label, the page's address or "" to stay, a step run on
    the page (JS text, or a callable given the browser) or None, a JS condition that says the
    state is drawn, the widths it is shot at or () for all), each shot as
    `<name>-<label>-page-<width>.png`."""
    from tests.browser import Browser

    os.makedirs(OUT, exist_ok=True)
    with _Boards() as bs:
        for width, scale in widths:
            prefs = {"layout.css.devPixelsPerPx": str(scale)} if scale != 1.0 else {}
            with Browser(prefs=prefs) as b:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": width, "height": 1000})
                for board, at in boards:
                    if at == width:
                        b.go(bs.url(board))
                        _full(b, os.path.join(OUT, f"{name}-board-{board[:-8]}-{width}.png"))
                for label, url, step, drawn, only in states:
                    if only and width not in only:
                        continue
                    if url:
                        b.go(served.url(url))
                        b.wait_for(f"return !!window.htmx && !!window.Alpine && {_E2_SETTLED}",
                                   20)
                    if callable(step):
                        step(b)
                    elif step:
                        b.js(step + "; return 1")
                    b.wait_for(f"return ({drawn or 'true'}) && {_E2_SETTLED}", 30)
                    # A click scrolls the page; the full shot is taken from the top, so the
                    # sticky sidebar and bar are drawn where they stand at rest.
                    b.js("window.scrollTo(0, 0); return 1")
                    time.sleep(0.3)
                    if width < 480:
                        b.js(f"document.documentElement.style.maxWidth = '{width}px'; "
                             f"document.body.style.maxWidth = '{width}px'; return 1")
                    _full(b, os.path.join(OUT, f"{name}-{label}-page-{width}.png"))
                    if width < 480 and url:
                        png = b._call("GET", f"/session/{b.session}/screenshot")
                        with open(os.path.join(OUT, f"{name}-{label}-page-{width}-first.png"),
                                  "wb") as fh:
                            fh.write(base64.b64decode(png))


def test_credentials(tmp_path, monkeypatch, capsys):
    """Credentials › The break-glass record beside board 7 (`DevBreakglassExport.dc.html`) and
    board 20 (`BreakglassRestore.dc.html`), on test_breakglass_export's lab (a real key, r1 and
    s1's credentials, the real export, check, drill and record format; its fixture's lines
    inline, Save's `lab` holding the name): a real export drilled by the CLI's own `drill` and
    recorded, its download intact, then r1 rotated and job health judging the record stale
    (the board's "not current"). The page; the export opened (A); the kept file checked (C,
    posted as the form posts it); and the export's result (B, the browser's word posted)."""
    import base64 as _b64

    from tests import browser
    from tests.test_breakglass_export import DEVICES, LIST, PASS
    from tests.test_credentials_v2 import TestTheOfflineDrill

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from cryptography.fernet import Fernet

    import app as A
    from modules import breakglass_export as BE
    from modules import reader_job

    key = Fernet.generate_key()
    (tmp_path / "key.key").write_bytes(key)
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.KEY_FILE", str(tmp_path / "key.key"))
    monkeypatch.setattr(BE, "list_devices", lambda ln: [dict(d) for d in DEVICES])
    token = Fernet(key).encrypt(b"a stored value").decode()
    monkeypatch.setattr(BE, "live_stores",
                        lambda data_dir="": {"credential_profiles.json": [token]})
    lab_ = {"client": A.app.test_client(), "dir": tmp_path, "key": key}
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == LIST)
    folder = tmp_path / "lists" / "lab"
    folder.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(folder))
    kept = tmp_path / "kept"
    kept.mkdir()
    line, d = TestTheOfflineDrill()._receipt(lab_, kept, capsys, monkeypatch)
    assert "Not recorded" not in lab_["client"].post(
        "/v2/credentials/drill", data={"list": LIST, "receipt": line}).get_data(as_text=True)
    intact = {"list": LIST, "sha256": d["sha256"], "browser_sha256": d["sha256"],
              "filename": d["filename"]}
    assert "Downloaded intact" in lab_["client"].post(
        "/v2/credentials/intact", data=intact).get_data(as_text=True)
    # r1 rotated since, and job health's read after the export judging the record stale.
    rotated = [dict(x) for x in DEVICES]
    rotated[0]["password"] = "R1-Rotated-Value-55"
    monkeypatch.setattr(BE, "list_devices", lambda ln: [dict(x) for x in rotated])
    judged = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(time.time()) + 1))
    stale = {"state": "ok", "doc": {"last_good": {"value_at": judged, "value": {"health": {
        "jobs": [{"unit": f"breakglass:{LIST}/r1", "device": "r1",
                  "state": "breakglass_stale"}]}}}}}
    real = reader_job.read_cached
    monkeypatch.setattr(reader_job, "read_cached",
                        lambda name, *a, **k: stale if name == "job-health"
                        else real(name, *a, **k))
    time.sleep(2)
    page = f"/v2/credentials?list={LIST}"
    check = (
        "var bin = atob(arguments[0]), a = new Uint8Array(bin.length);"
        "for (var i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);"
        "var f = new FormData(); f.append('list', arguments[1]);"
        "f.append('passphrase', arguments[2]);"
        "f.append('file', new Blob([a]), arguments[3]);"
        "fetch('/v2/credentials/check', {method: 'POST', body: f, "
        "headers: {'HX-Request': 'true'}})"
        ".then(function (r) { return r.text(); }).then(function (t) {"
        "document.getElementById('bg-op').innerHTML = t; htmx.process("
        "document.getElementById('bg-op')); })")

    def checked(b):
        b.js(check + "; return 1", _b64.b64encode(_b64.b64decode(d["file"])).decode(), LIST,
             PASS, d["filename"])

    done = ("htmx.ajax('POST', '/v2/credentials/intact', {target: '#bg-op', swap: 'innerHTML', "
            f"values: {json.dumps(intact)}}})")
    with browser.Served(A.app) as served:
        _e2_walk("credentials", served, [
            ("record", page, None, "!!document.querySelector('#bg-record') && "
                                   "!!document.querySelector('#bg-drill')", ()),
            ("export", page + "&open=export", None,
             "!!document.querySelector('#bg-export [data-bg-pass]')", (1440, 390)),
            ("check", page, checked, "!!document.querySelector('#bg-op .bg-verdict')",
             (1440, 390)),
            ("done", page, done, "/Downloaded intact/.test((document.querySelector("
                                 "'#bg-op #bg-export') || {}).textContent || '')",
             (1440, 390)),
        ], widths=((1440, 1.0), (1280, 1.0), (390, 2.0)),
            boards=(("DevBreakglassExport.dc.html", 1440), ("BreakglassRestore.dc.html", 1440)))


# --- C650 group F1: landing ---

_F1_SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


def _f1_walk(served, name, path, widths, boards=(), states=(("", "", "true"),), dark=False):
    """Group F1's walk: at each width each board shot, then the page at *path* (in the dark
    theme when *dark*, chosen as the theme menu keeps it) and, in turn, each state of
    *states* (label, a script run on the page or "", a condition that says it is drawn),
    shot as `<name>[-<label>]-page-<width>.png`; a phone's page held to its column."""
    from tests.browser import Browser

    os.makedirs(OUT, exist_ok=True)
    with _Boards() as bs:
        for width, scale in widths:
            prefs = {"layout.css.devPixelsPerPx": str(scale)} if scale != 1.0 else {}
            with Browser(prefs=prefs) as b:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": width, "height": 1000})
                for board in boards:
                    b.go(bs.url(board))
                    _full(b, os.path.join(OUT, f"{name}-board-{board.split('/')[-1][:-8]}-"
                                               f"{width}.png"))
                b.go(served.url(path))
                if dark:
                    b.js("try { localStorage.setItem('nmas.theme', 'dark'); } catch (e) {} "
                         "return 1")
                    b.go(served.url(path))
                b.wait_for("return !!window.Alpine && " + _F1_SETTLED, 20)
                if width < 480:
                    b.js(f"document.documentElement.style.maxWidth = '{width}px'; "
                         f"document.body.style.maxWidth = '{width}px'; return 1")
                for label, step, drawn in states:
                    if step:
                        b.js(step + "; return 1")
                    b.wait_for(f"return ({drawn}) && {_F1_SETTLED}", 20)
                    time.sleep(0.4)
                    shot = f"{name}-{label}" if label else name
                    _full(b, os.path.join(OUT, f"{shot}-page-{width}.png"))
                    if width < 480:
                        png = b._call("GET", f"/session/{b.session}/screenshot")
                        with open(os.path.join(OUT, f"{shot}-page-{width}-first.png"),
                                  "wb") as fh:
                            fh.write(base64.b64decode(png))


def test_landing(tmp_path, monkeypatch):
    """Needs attention (NSOT_GUI_BRIEF 13) beside `redesign/Main.dc.html` (1440),
    `redesign/LandingPhone.dc.html` and `redesign/NavPhone.dc.html` (390), `BrandSidebar`,
    `KnownNoise` and `C566Coverage` (1440). On the browser layout test's lab (tests/
    test_profile_apply's: r2's real configuration and intent), with the management section
    proposed and `_common.j2` committed as the shipped version from before P1 (tests/
    test_template_bring's stale lab, so C566's row is raised by the real source), and every
    other source as the payload check's provider builds it (`payload_providers.
    needs_attention`: job health over the measured systemd shapes, a real drift run, an
    approval, an overdue onboarding, a rollback block, a failed deploy, a denied baseline, an
    authorisation, an unreadable source). Two receipts written through the real store."""
    from tests import browser
    from tests import payload_providers as PP
    from tests import test_profile_apply as P
    from tests.test_profile_reaches_the_program import _propose_management
    from tests.test_template_bring import _commit_stale

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    lab_ = P.lab.__wrapped__(monkeypatch, tmp_path)
    # The modules that bound the accessor when imported (test_device_v2's lab does the same).
    for bound in ("modules.device", "modules.inventory", "modules.inventory.source_config"):
        monkeypatch.setattr(f"{bound}.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    _propose_management(lab_)
    _commit_stale(lab_)
    PP.needs_attention(monkeypatch, tmp_path)
    from modules import attention as A
    from modules.nsot import listref, receipts

    monkeypatch.setattr(A, "SOURCES", tuple(A.SOURCES) + (
        lambda: A.template_behind_source(listref.resolve("Lab")),))
    now = time.time()
    iso = lambda s: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - s))  # noqa: E731
    assert receipts.write("Lab", [
        {"id": "f1a", "at": iso(5400), "action": "deploy", "device": "r6",
         "actor": "operator@example.com", "outcome": "deployed", "program_lines": 4,
         "reason": "", "golden_commit": "abc1234def"},
        {"id": "f1b", "at": iso(600), "action": "restore", "device": "r2",
         "actor": "operator@example.com", "outcome": "refused", "program_lines": 0,
         "reason": "the device moved since the preview", "golden_commit": ""}])["ok"]
    evidence = ("document.querySelector('#attention details.evidence').open = true",
                "document.querySelector('#attention details.evidence').open")
    drawer = ("document.querySelector('.menu-btn').click()",
              "!!document.querySelector('.sidebar.open')")
    import app as A_
    with browser.Served(A_.app) as served:
        _f1_walk(served, "landing", "/v2/", ((1440, 1.0), (1280, 1.0)),
                 boards=("redesign/Main.dc.html",),
                 states=(("", "", "true"), ("evidence",) + evidence))
        _f1_walk(served, "landing-brand", "/v2/", ((1440, 1.0),),
                 boards=("BrandSidebar.dc.html", "KnownNoise.dc.html", "C566Coverage.dc.html"))
        _f1_walk(served, "landing-dark", "/v2/", ((1440, 1.0),), dark=True)
        _f1_walk(served, "landing-phone", "/v2/", ((390, 2.0),),
                 boards=("redesign/LandingPhone.dc.html", "redesign/NavPhone.dc.html"),
                 states=(("", "", "true"), ("drawer",) + drawer))


# --- C650 group F2: show_commands, show_commands_run ---

def _f2_reads_lab(tmp_path, monkeypatch):
    """Show commands' lab (tests/test_show_commands.py): test_device_v2's lab (r3, IOS-XE; r9,
    IOS), its fixture's body called here (this module's `lab` is Save's), the sessions faked at
    the connection seam answering from real captures, and board F's Loki stand-in (r3's line
    arrives, r9's never; `lp`). A command whose answer is an exception raises it, so a read
    fails as a device's would."""
    from tests import test_device_v2 as D
    from tests import test_show_commands as T

    gen = D.lab.__wrapped__(tmp_path, monkeypatch)
    built = next(gen)
    sc = T.sc.__wrapped__(built, monkeypatch)
    lp = T.lp.__wrapped__(sc, monkeypatch)

    def answer(conn, command, **kw):
        got = conn.answer(command)
        if isinstance(got, Exception):
            raise got
        return got
    monkeypatch.setattr("modules.commands.run_device_command", answer)
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    return gen, lp


def test_show_commands_pick(tmp_path, monkeypatch):
    """C548's board B (ReadsFleetPick, 1440) beside Show commands' pick card: three commands,
    the third refused across devices, two saved sets; board F's footer (ReadsLogPath, 1440) with
    Loki configured; board C582 (ReadsReasonC582, 1440): a send log at level 2 typed, then its
    reason given beside a second line that is not a test. Phone width without a board: board E
    and G draw only the device's Ask tab and the run's page."""
    from urllib.parse import urlencode

    from tests import browser
    from tests import test_show_commands as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    gen, sc = _f2_reads_lab(tmp_path, monkeypatch)
    try:
        from modules.nsot import command_sets
        for name, cmds, why in (
                ("Routing health", ["show ip ospf neighbor", "show ip route summary"],
                 "OSPF and the route table"),
                ("Time", ["show clock"], "")):
            assert command_sets.save("Lab", name, cmds, "operator@example.com", why)["ok"]
        pick = "/v2/show-commands?" + urlencode(
            {"list": "Lab", "command": ["show ip ospf neighbor", "show clock",
                                        "show tech-support"]}, doseq=True)
        asked = "/v2/show-commands?" + urlencode({"list": "Lab", "command": [T.URGENT]},
                                                doseq=True)
        given = "/v2/show-commands?" + urlencode(
            {"list": "Lab", "command": [T.URGENT, "send log 2 MERCURY alert rule check"],
             "reason": T.REASON}, doseq=True)
        import app as A
        with browser.Served(A.app) as served:
            _shoot("show-commands", "ReadsFleetPick.dc.html", lambda w: pick, served,
                   widths=((1440, 1.0), (1280, 1.0)))
            _shoot("show-commands", "", lambda w: pick, served, widths=((390, 2.0),))
            _shoot("show-commands-logpath", "ReadsLogPath.dc.html",
                   lambda w: "/v2/show-commands?list=Lab", served, widths=((1440, 1.0),))
            _shoot("show-commands-reason", "ReadsReasonC582.dc.html", lambda w: asked, served,
                   widths=((1440, 1.0), (390, 2.0)))
            _shoot("show-commands-reason-given", "", lambda w: given, served,
                   widths=((1440, 1.0),))
    finally:
        next(gen, None)


def test_show_commands_run(tmp_path, monkeypatch):
    """C548's boards C (ReadsFleetResult), C2 (ReadsResultC2), D (ReadsCompare) and F's result
    (ReadsLogPath), 1440, and E and G at 390 (ReadsPhone, ReadsLogPathPhone) beside a run's
    page, runs started through the real route on Show commands' lab: two commands answered
    alike and not; C2's OSPF captures (r9's IPv6 answer empty) as opened, with Dead Time
    ticked, and against r3; r3 and r9 side by side and only the differences; a run with r3's
    `show ip interface` failing (planted), its `show logging` past the cap (s1's capture
    repeated) and r9 held by another operation; and the logging-path test's result."""
    from tests import browser
    from tests import test_show_commands as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    gen, sc = _f2_reads_lab(tmp_path, monkeypatch)
    try:
        from modules.nsot import device_ops
        ans = sc["fleet"].answers
        ans["r3"]["show ip ospf neighbor"] = T.OSPF
        ans["r9"]["show ip ospf neighbor"] = T.OSPF_LATER
        ans["r3"]["show ipv6 ospf neighbor"] = T._cap("r3__show_ipv6_ospf_neighbor.txt")
        ans["r9"]["show ipv6 ospf neighbor"] = ""
        _r, plain = T._run(sc, ["show clock", "show ip interface"])
        _r, c2 = T._run(sc, ["show ip ospf neighbor", "show ipv6 ospf neighbor"])
        logging_ = T._cap("s1__show_logging__after_clear_logging.txt")
        ans["r3"]["show logging"] = logging_ * (40 * 1024 // len(logging_) + 1)
        ans["r3"]["show ip interface"] = TimeoutError("did not answer in 120 s")
        with device_ops.hold("Lab", "r9", "deploy", "operator@example.com",
                             detail="a deploy, for this shot"):
            _r, failed = T._run(sc, ["show clock", "show ip interface", "show logging"])
        _r, logpath = T._test(sc)
        import app as A
        with browser.Served(A.app) as served:
            _shoot("show-commands-run", "ReadsFleetResult.dc.html", lambda w: plain, served,
                   widths=((1440, 1.0), (1280, 1.0)))
            _shoot("show-commands-run", "ReadsPhone.dc.html", lambda w: plain, served,
                   widths=((390, 2.0),))
            _shoot("show-commands-run-failed", "", lambda w: failed, served,
                   widths=((1440, 1.0),))
            _shoot("show-commands-run-c2", "ReadsResultC2.dc.html", lambda w: c2, served,
                   widths=((1440, 1.0), (1280, 1.0)))
            _shoot("show-commands-run-c2", "ReadsLogPathPhone.dc.html", lambda w: c2, served,
                   widths=((390, 2.0),))
            run_id = c2.split("/run/", 1)[1].split("?", 1)[0]
            r = sc["client"].post(f"/v2/show-commands/run/{run_id}/ignore?list=Lab",
                                  data={"command": "show ip ospf neighbor",
                                        "column": ["Dead Time"]},
                                  headers={"HX-Request": "true"})
            assert r.status_code == 200
            _shoot("show-commands-run-c2-ignored", "", lambda w: c2, served,
                   widths=((1440, 1.0),))
            _shoot("show-commands-run-c2-against", "",
                   lambda w: c2 + "&against=r3&show=differences", served, widths=((1440, 1.0),))
            _shoot("show-commands-run-compare", "ReadsCompare.dc.html",
                   lambda w: plain + "&left=r3&right=r9&command=show%20ip%20interface", served,
                   widths=((1440, 1.0), (390, 2.0)))
            _shoot("show-commands-run-logpath", "ReadsLogPath.dc.html", lambda w: logpath,
                   served, widths=((1440, 1.0),))
            _shoot("show-commands-run-logpath", "", lambda w: logpath, served,
                   widths=((390, 2.0),))
    finally:
        next(gen, None)


# --- C650: save, pending, retired (the screens the operator's walk W4 touched, 2026-10-17) ---

def _w4_press(b, css, until, timeout=60):
    """Press *css* as a person does (scrolled into view, clicked) and wait for *until*."""
    b.js("var e = document.querySelector(arguments[0]); e.scrollIntoView({block: 'center'}); "
         "e.click(); return 1", css)
    b.wait_for(f"return !!({until})", timeout)


def test_save_page(lab, monkeypatch):            # noqa: F811 (Save's lab, imported above)
    """Devices › Save (7.4's board C, `SaveAll.dc.html`, at 1440 and 1280) on Save's lab
    (tests/test_save_v2.py: r2's real capture as its golden, r3 answering and not in the
    manifest, r4 not answering, s9 with no driver; the hourly startup check read r2 not saved
    and r3 saved). The plan for all four; the result of r2 and r3 confirmed in the page as a
    person does (r2's running moved by `_broken`, so its golden is recorded; r3 refused by the
    manifest: a partial); then the whole network (r2 alone) saved, its baseline decided. The
    run between is the one stepper's, shot by `test_stepper` (docs/fidelity/stepper.md)."""
    from tests import browser
    from tests.test_intent_match import _broken
    from tests.test_save_v2 import _startup_check

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules.nsot import listref

    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    _startup_check(lab, [{"list": "Lab", "device": "r2", "state": "not_persisted",
                          "detail": "the startup config does not carry username nmas"},
                         {"list": "Lab", "device": "r3", "state": "persisted"}])
    widths = ((1440, 1.0), (1280, 1.0), (390, 2.0))
    _group_a_boards("save", "SaveAll.dc.html", ((1440, 1.0), (1280, 1.0)))
    card = "document.getElementById('save-op')"
    runs = {"n": 0}

    def save_two(b):
        # Each width's run records a golden: r2's running alternates, so it always moved.
        runs["n"] += 1
        lab["running"]["r2"] = _broken(lab["captured"]) if runs["n"] % 2 else lab["captured"]
        _w4_press(b, "#save-op .op-confirm",
                  f"{card} && {card}.textContent.indexOf('1 saved and recorded, 1 not') >= 0")

    def save_all(b):
        _w4_press(b, "#save-op .op-confirm",
                  f"{card} && /baseline earned|No baseline/.test({card}.textContent)")

    import app as A
    with browser.Served(A.app) as served:
        _group_a_page("save-plan", served,
                      "/v2/devices/save?list=Lab&device=r2&device=r3&device=r4&device=s9", widths)
        _group_a_page("save-result", served, "/v2/devices/save?list=Lab&device=r2&device=r3",
                      widths, act=save_two)
        lab["rows"][:] = lab["rows"][:1]                     # r2 is the whole network
        lab["running"]["r2"] = lab["captured"]               # at its committed intent
        _group_a_page("save-fleet", served, "/v2/devices/save?list=Lab&all=1",
                      ((1440, 1.0), (390, 2.0)), act=save_all)


def test_pending_page(tmp_path, monkeypatch):
    """A pending device's page (`pending.html`) beside the canvas's pending device page
    (`OnboardPanel.dc.html`, 1440 and 1280) and board M (`ZtpPlan.dc.html`, 1440), fed the rows
    the page's own tests build (tests/test_onboard_v2.py's `TestAPendingDevice.PENDING`,
    tests/test_onboarding_progress.py's ZTP row and probe answer): bp1 by ZTP, fetched and
    answering; bp1 static, overdue, its last Verify failed; Verify's preview (that test file's
    preview model) and its result stopped at the rotation (its stepper test's steps), each
    pressed in the page; Abandon's dry run, the real `abandon_onboarding` on
    tests/test_onboard_abandon.py's repository; the (i)'s help panel."""
    from tests import browser
    from tests import test_onboarding_progress as OPT
    from tests.test_onboard_abandon import _onboard
    from tests.test_onboard_abandon import repo as abandon_repo
    from tests.test_onboard_v2 import TestAPendingDevice as P

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules import preview_confirm as PC
    from modules.nsot import onboard as O
    from modules.nsot.onboard import PHASE_TWO_STEPS
    from routes import onboard as RO

    # Abandon's dry run, from the real core on a real repository (its own monkeypatches undone
    # before the page is served).
    (tmp_path / "abandon").mkdir()
    with pytest.MonkeyPatch.context() as mp:
        repo = _device_fx(abandon_repo, tmp_path / "abandon", mp)
        _onboard(repo)
        mp.setattr("modules.netbox_client.remove_device_from_netbox",
                   lambda *a, **k: {"ok": True, "deleted": [], "skipped": [], "message": "dry"})
        dry = RO.abandon_run("bp1", {"list_name": "probe", "dry_run": "1"}, "")
    assert dry[0].get("steps"), dry
    monkeypatch.setattr(RO, "abandon_run", lambda name, data, actor, confirmed="": dry)
    pv = PC.build(action="verify", summary="Verify bp1: it answered.",
                  targets=[{"name": "bp1", "state": "ready", "selectable": True,
                            "select_data": {"fingerprint": "f" * 64},
                            "program": {"lines": ["no snmp-server community"]},
                            "operands": [{"name": "address", "value": "192.0.2.9"}],
                            "gates": [PC.gate("reached", "pass", "it answered")]}],
                  what_not=[], nothing_left_out="Nothing left out.",
                  confirm={"may": True, "statement": "You are confirming as x."})
    monkeypatch.setattr(RO, "verify_preview_of",
                        lambda name, data, req: ({"ok": True, "preview": pv}, 200))
    ran = [{"step": "verify", "ok": True, "detail": "answered"},
           {"step": "capture", "ok": True, "detail": ""},
           {"step": "rotate", "ok": False, "detail": "the new secret did not log in"}]
    ran += [{"step": s, "ok": False, "detail": "did not run"} for s in PHASE_TWO_STEPS[3:]]
    monkeypatch.setattr(RO, "verify_run", lambda name, data, ident: ({
        "ok": False, "steps": ran, "stopped_at": "rotate", "reason": "rotation refused",
        "result": {"level": "failed", "happened": {"summary": "bp1 is still pending"},
                   "did_not": {"items": []}}}, 200))

    def rows(row, stage=None, stored=None, runs=None):
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [dict(row)])
        if stage:
            monkeypatch.setattr("modules.nsot.ztp.progress", lambda entry, **_k: {
                "stage": stage, "summary": f"{stage.replace('_', ' ')} now"})
        OPT._stored(monkeypatch, stored)
        monkeypatch.setattr(O, "read_runs", lambda repo: runs or {
            "state": "ok", "error": "", "rows": []})

    actions = "document.getElementById('pending-actions')"
    verify_btn = '#pending-actions form[hx-post*="verify/preview"] button'
    confirm = '#pending-actions form[hx-post*="/verify"]:not([hx-post*="preview"]) button'

    settled = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"

    def verify(b):
        # Settled first: a confirm pressed before htmx has processed the card submits the
        # form as a page of its own.
        _w4_press(b, verify_btn, f"document.querySelector('{confirm}') && {settled}", 30)

    def verified(b):
        verify(b)
        _w4_press(b, confirm, f"{actions} && /still pending/.test({actions}.textContent) && "
                              f"{actions}.querySelector('[data-run-stepper]')", 30)

    def abandon(b):
        _w4_press(b, '#pending-actions form[hx-post*="abandon/preview"] button',
                  "document.querySelector('#pending-actions form[hx-post*=\"/abandon\"]"
                  ":not([hx-post*=\"preview\"])')", 30)

    def helped(b):
        _w4_press(b, ".page-title .info-link",
                  "(document.getElementById('help-panel-body') || {textContent: ''})"
                  ".textContent.trim().length > 80", 30)

    _group_a_boards("pending-panel", "OnboardPanel.dc.html", ((1440, 1.0), (1280, 1.0)))
    _group_a_boards("pending-plan", "ZtpPlan.dc.html", ((1440, 1.0),))
    import app as A
    with browser.Served(A.app) as served:
        rows(OPT.ZTP_ROW, "fetched_not_reached", OPT.ANSWERING)
        _group_a_page("pending-ztp", served, "/v2/device/bp1",
                      ((1440, 1.0), (1280, 1.0), (390, 2.0)))
        _group_a_page("pending-help", served, "/v2/device/bp1", ((1440, 1.0),), act=helped)
        rows(dict(P.PENDING, state="overdue", age_seconds=2 * 86400), runs={
            "state": "ok", "error": "", "rows": [
                {"at": "2026-10-10T09:05:00Z", "kind": "verify", "device": "bp1",
                 "actor": "operator@example.invalid", "ok": False, "mgmt_ip": "192.0.2.60",
                 "steps": [{"step": "verify", "ok": False, "detail": "no answer"}],
                 "verify": {"state": "did_not_answer", "error": "no answer", "causes": []}}]})
        _group_a_page("pending-static", served, "/v2/device/bp1", ((1440, 1.0), (390, 2.0)))
        rows(P.PENDING)
        _group_a_page("pending-verify", served, "/v2/device/bp1", ((1440, 1.0), (390, 2.0)),
                      act=verify)
        _group_a_page("pending-verified", served, "/v2/device/bp1", ((1440, 1.0),),
                      act=verified)
        _group_a_page("pending-abandon", served, "/v2/device/bp1", ((1440, 1.0),), act=abandon)


def test_retired_page(tmp_path, monkeypatch):
    """A retired device's address (`retired.html`) beside the last card of board 12
    (`DevRetire.dc.html`, 1440 and 1280), on the retire tests' world (tests/test_retire.py's
    `world`, tests/test_device_retire_v2.py's `page`: r4 and r5 in 'Lab', a real repository,
    CSV, manifest and credential store): r5 retired through the real confirm as that file's
    test does, its address then opened; and its Onboard it again… pressed."""
    from tests import browser
    from tests import test_device_retire_v2 as RV
    from tests import test_retire as RT
    from tests import test_retire_screen as RS

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    world = _device_fx(RT.world, tmp_path, monkeypatch)
    page = _device_fx(RV.page, _device_fx(RS.screen, world, tmp_path, monkeypatch), monkeypatch)
    RS._export(page)
    RV._targets(monkeypatch, tmp_path, [("r4", "192.0.2.14")])
    _r, card = RV._card(page)
    r = page["client"].post("/v2/device/r5/retire/confirm", data=RV._vals(card))
    assert r.status_code == 200 and "r5 is retired" in r.get_data(as_text=True)

    def again(b):
        _w4_press(b, 'a[data-op="onboard"]',
                  "document.querySelector('#onboard-add input[name=hostname]')", 30)

    _group_a_boards("retired", "DevRetire.dc.html", ((1440, 1.0), (1280, 1.0)))
    import app as A
    with browser.Served(A.app) as served:
        _group_a_page("retired", served, "/v2/device/r5", ((1440, 1.0), (1280, 1.0), (390, 2.0)))
        _group_a_page("retired-again", served, "/v2/device/r5", ((1440, 1.0),), act=again)


#: C1346's relayed ZTP device, as tests/test_ztp_relayed.py plans it: the relay's check as the
#: plan reads it (TestTheChoiceInThePlan.RELAYED_CHECK), and the fields a person types.
_RELAYED_FIELDS = {"hostname": "edge1", "address_source": "ztp", "mgmt_ip": "198.51.100.2",
                   "mgmt_mask": "255.255.255.252", "mgmt_mac": "aa:bb:cc:00:04:02",
                   "manager_interface": "GigabitEthernet2", "manager_gateway": "198.51.100.1",
                   "role": "router", "domain": "example.net"}


def _fill(b, fields):
    """Set Add device's fields as a person does (each one's value, then its change event, so
    the card's CSS shows the rows the address source asks for); the platform is the first one
    the form offers."""
    b.js("var f = document.querySelector('#onboard-add form'); var v = arguments[0]; "
         "var p = f.querySelector('select[name=platform] "
         "option:not([value=\"\"]):not([disabled])'); "
         "if (p) { v = Object.assign({platform: p.value}, v); } "
         "Object.keys(v).forEach(function (k) { var e = f.querySelector('[name=' + k + ']'); "
         "e.value = v[k]; e.dispatchEvent(new Event('change', {bubbles: true})); }); return 1",
         fields)


def test_onboard_add_relayed(lab, monkeypatch):            # noqa: F811 (Save's lab)
    """Devices › Add device… (board E, `OnboardList.dc.html`'s "The devices", 1440 and 1280)
    after C1346: the card opened from Devices on Save's lab as a person opens it, then ZTP chosen
    so Route option (3) is drawn (None (D4), the default), then "The relay's own address" chosen
    with the relayed device's fields filled, then its review, planned behind the relay as
    tests/test_ztp_relayed.py plans it (the relay's check its RELAYED_CHECK, the relay's own
    address the gateway). The control: Static hides the row."""
    import re

    from tests import browser
    from tests.test_ztp_relayed import TestTheChoiceInThePlan as Choice

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import modules.settings_schema as ss
    from modules.nsot import listref
    from modules.nsot import onboard as O

    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    real = ss.get_setting
    # The schema's own IOS-XE mapping (Save's lab maps none), and the syslog block the schema's
    # defaults build with a syslog host (the relayed plan's test sets one).
    mapped = {"cisco-ios-xe": {"netmiko_device_type": "cisco_xe", "template_dir": "cisco-ios-xe"}}
    monkeypatch.setattr(ss, "get_setting", lambda k, *a, **kw: (
        mapped if k == "platform_map" else real(k, *a, **kw)))
    monkeypatch.setattr(O, "syslog_baseline", lambda list_name: (
        {"trap": "notifications", "origin_id": "hostname", "source_interface": "Loopback0",
         "hosts": ["192.0.2.10"], "heartbeat": 300}, ""))
    monkeypatch.setattr(O, "_name_in_manifest", lambda *a: (False, True))
    monkeypatch.setattr(O, "_name_in_netbox", lambda *a: (False, True))
    monkeypatch.setattr(O, "_ztp_check", lambda *a, **k: dict(Choice.RELAYED_CHECK))
    _group_a_boards("onboard-add", "OnboardList.dc.html", ((1440, 1.0), (1280, 1.0)))
    opened = "document.querySelector('#onboard-add input[name=hostname]')"
    shown = ("(function () { var e = document.querySelector('#f-ob-router'); "
             "return !!(e && e.offsetParent); })()")

    def add(b):
        _w4_press(b, 'a[data-op="onboard"]', opened, 30)

    def ztp(b):
        add(b)
        _fill(b, {"address_source": "ztp"})
        b.wait_for(f"return {shown}", 5)

    def relay(b):
        add(b)
        _fill(b, dict(_RELAYED_FIELDS, ztp_router="relay"))
        b.wait_for(f"return {shown}", 5)

    def review(b):
        relay(b)
        _w4_press(b, '#onboard-add button[data-op="onboard"]',
                  "!document.querySelector('#f-ob-hostname')", 30)
        # The review offers Create to the browser's person (no blocking reason), and the page is
        # shot from its top (a full-page shot draws the sticky bars where it was scrolled).
        assert b.js("var e = document.querySelector('#onboard-add button[data-op=onboard] "
                    ".op-idle'); return e ? e.textContent : ''") == "Create edge1"
        b.js("window.scrollTo(0, 0); return 1")

    def static(b):
        add(b)
        _fill(b, {"address_source": "static"})
        b.wait_for(f"return !{shown}", 5)

    import app as A
    # What the review draws, read by the test client from the same seams first: the relayed
    # plan's address claim with option 3 as chosen (Create is drawn for the browser's person).
    html = A.app.test_client().post("/v2/onboard/preview", data=dict(
        _RELAYED_FIELDS, list_name="Lab", platform="cisco-ios-xe",
        ztp_router="relay")).get_data(as_text=True)
    said = re.findall(r'<div class="notice[^"]*"[^>]*>(.*?)</div>', html, re.S)
    assert "ZTP behind the relay relay-a GigabitEthernet3 (198.51.100.1)" in html, said
    assert "offering option 3 (routers) 198.51.100.1, the relay&#39;s own address" in html
    widths = ((1440, 1.0), (1280, 1.0), (390, 2.0))
    with browser.Served(A.app) as served:
        _group_a_page("onboard-add-ztp", served, "/v2/devices", widths, act=ztp)
        _group_a_page("onboard-add-relay", served, "/v2/devices", ((1440, 1.0), (390, 2.0)),
                      act=relay)
        _group_a_page("onboard-add-review", served, "/v2/devices", ((1440, 1.0), (390, 2.0)),
                      act=review)
        _group_a_page("onboard-add-static", served, "/v2/devices", ((1440, 1.0),), act=static)


def test_dhcp_subnet_add_for_ztp(tmp_path, monkeypatch):
    """DHCP › Subnets › Add a subnet… (board C's section 4, `DhcpSubnets.dc.html`, 1440) after
    C1346: the empty form with For ZTP onboarding unticked, then ticked with a relayed prefix
    and its pool, previewed against tests/test_ztp_relayed.py's Kea (subnet 255 this host's,
    40 declared relayed) and its relay in intent (TestTheSubnetIsDeclaredAtAdd: relay-b
    GigabitEthernet2 on 198.51.100.4/30, helper 192.0.2.10), and the refusal a gateway draws
    on a ZTP subnet. The page under the card is test_dhcp's (the lab's Kea answers)."""
    import re
    from urllib.parse import urlencode

    from tests import browser
    from tests import test_dhcp_v2 as T
    from tests import test_ztp_relayed as TR

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    (tmp_path / "lab").mkdir()
    (tmp_path / "kea").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.dhcp_page._devices", lambda name: set())
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: __import__("modules.reader_job").reader_job
                        .read_cached(name))
    # The page's network owns the Kea it shows (C1181), so the card may preview a change.
    monkeypatch.setattr("modules.list_settings.kea_owner",
                        lambda name: (name, "it sets its own Kea"))
    files = _device_fx(TR.kea_files, tmp_path / "kea")
    monkeypatch.setattr("modules.dhcp_reservations.main_config",
                        lambda list_name, family: files["main"])
    monkeypatch.setattr("modules.integrations.kea.KeaIntegration",
                        lambda **kw: TR.FakeKea({255: files["direct"], 40: files["relayed"]}))
    value = T._value()
    intent = dict(T._s1_intent(), error="")
    intent["IPv4"] = dict(intent["IPv4"],
                          **TR.TestTheSubnetIsDeclaredAtAdd._intent()["IPv4"])
    value["intent"] = intent
    value["families"]["dhcp4"]["held"] = {"10": "mercury", "20": "mercury", "255": "ztp"}
    value["families"]["dhcp6"]["held"] = {"10": "mercury", "20": "mercury", "30": "mercury"}
    T._store(value)
    base = {"list": "Lab", "op": "add"}
    ztp = dict(base, family="IPv4", prefix="198.51.100.4/30",
               pool="198.51.100.6 - 198.51.100.6", ztp="1")
    import app as A
    client = A.app.test_client()
    form = client.get("/v2/dhcp/subnet?" + urlencode(base)).get_data(as_text=True)
    assert '<input type="checkbox" name="ztp" value="1"> For ZTP onboarding' in form
    html = client.get("/v2/dhcp/subnet?" + urlencode(ztp)).get_data(as_text=True)
    said = re.findall(r'<div class="dh-refuse"[^>]*><p>(.*?)</p>', html, re.S)
    assert 'name="ztp" value="1" checked' in html and "Add 198.51.100.4/30" in html, said
    assert "user-context: {&#34;mercury-ztp&#34;: &#34;relayed&#34;}" in html
    assert "for ZTP behind relay-b GigabitEthernet2 (198.51.100.5, its relay)" in html
    refused = client.get("/v2/dhcp/subnet?" + urlencode(dict(ztp, gateway="198.51.100.5")))
    assert "carries no gateway or DNS option (D4)" in refused.get_data(as_text=True)
    _group_a_boards("dhcp-subnet-add", "DhcpSubnets.dc.html", ((1440, 1.0),))
    with browser.Served(A.app) as served:
        _group_a_page("dhcp-subnet-add", served, "/v2/dhcp/subnet?" + urlencode(base),
                      ((1440, 1.0), (1280, 1.0), (390, 2.0)))
        _group_a_page("dhcp-subnet-add-ztp", served, "/v2/dhcp/subnet?" + urlencode(ztp),
                      ((1440, 1.0), (1280, 1.0), (390, 2.0)))
        _group_a_page("dhcp-subnet-add-ztp-refused", served, "/v2/dhcp/subnet?" + urlencode(
            dict(ztp, gateway="198.51.100.5")), ((1440, 1.0),))


def test_dhcp_relayed_ztp_subnet(tmp_path, monkeypatch):
    """C1377: DHCP › Subnets and Leases with a subnet Mercury's Add wrote for ZTP behind a relay
    (tests/test_dhcp_v2.py's `_RelayedKea`: the lab's Kea answers with subnet 40,
    198.51.100.0/29, declared relayed, onboarding's one reservation and two leases, and an IPv6
    subnet carrying the same mark), Kea's main files including Mercury's subnet files so the
    reader's own `held_by` says who holds each. Beside board C's section 1
    (`DhcpSubnets.dc.html`, 1440), which draws a Mercury row and ZTP's row and no relayed one."""
    from tests import browser
    from tests import test_dhcp_v2 as T

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.dhcp_page._devices", lambda name: set())
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: __import__("modules.reader_job").reader_job
                        .read_cached(name))
    monkeypatch.setattr("modules.list_settings.kea_owner",
                        lambda name: (name, "it sets its own Kea"))
    from modules import dhcp_subnets as S
    mains = {}
    for family, key in (("IPv4", "subnet4"), ("IPv6", "subnet6")):
        main = tmp_path / f"kea-{key}.conf"
        main.write_text('{ "Dhcp": { "%s": <?include "%s"?> } }\n'
                        % (key, S.subnets_file(str(main), family)))
        mains[family] = str(main)
    monkeypatch.setattr("modules.dhcp_reservations.main_config",
                        lambda list_name, family: mains[family])
    T._store(T._value(kea=T._RelayedKea()))
    import app as A
    html = A.app.test_client().get("/v2/dhcp/view?list=Lab").get_data(as_text=True)
    assert 'aria-label="Remove 198.51.100.0/29"' in html and "1 reserved, 1 other" in html
    _group_a_boards("dhcp-relayed-ztp", "DhcpSubnets.dc.html", ((1440, 1.0),))
    with browser.Served(A.app) as served:
        _group_a_page("dhcp-relayed-ztp-sub", served, "/v2/dhcp?list=Lab",
                      ((1440, 1.0), (1280, 1.0), (390, 2.0)))
        _group_a_page("dhcp-relayed-ztp-lea", served, "/v2/dhcp?list=Lab&tab=lea&open=dhcp4:40",
                      ((1440, 1.0), (390, 2.0)))


def test_dhcp_lease_release(tmp_path, monkeypatch):
    """C1403: DHCP › Leases with each row's Release lease… (subnet 10's group open), and the
    release card drawn from a real preview of 10.10.10.102 (tests/test_dhcp_leases.py's
    `LeaseKea`: the lab's captured leases), beside board A's Leases tab (`DhcpNetwork.dc.html`,
    1440), which draws no change control on a lease."""
    from tests import browser
    from tests import test_dhcp_v2 as T
    from tests.test_dhcp_leases import LeaseKea

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.dhcp_page._devices", lambda name: set())
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: __import__("modules.reader_job").reader_job
                        .read_cached(name))
    monkeypatch.setattr("modules.list_settings.kea_owner",
                        lambda name: (name, "it sets its own Kea"))
    kea = LeaseKea({})
    monkeypatch.setattr("modules.integrations.kea.KeaIntegration", lambda **kw: kea)
    T._store(T._value())
    import app as A
    card = "/v2/dhcp/lease?list=Lab&family=IPv4&address=10.10.10.102"
    assert "Release 10.10.10.102" in A.app.test_client().get(card).get_data(as_text=True)
    _group_a_boards("dhcp-lease-release", "DhcpNetwork.dc.html", ((1440, 1.0),))
    with browser.Served(A.app) as served:
        _group_a_page("dhcp-lease-release-lea", served, "/v2/dhcp?list=Lab&tab=lea&open=dhcp4:10",
                      ((1440, 1.0), (1280, 1.0), (390, 2.0)))
        _group_a_page("dhcp-lease-release-card", served, card,
                      ((1440, 1.0), (1280, 1.0), (390, 2.0)))
    assert kea.dels == [], "a shot released a lease"
