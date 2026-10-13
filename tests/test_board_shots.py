"""Board fidelity shots (C650; the operator, 2026-10-10: "a screenshot of the page next to the
board, compared region by region"). Runs only when asked: `NMAS_BOARD_SHOTS=<out folder>` and
`NMAS_BOARDS_DIR=<a copy of the mockups canvas's project/ folder>` (the Artifact tool's read of
the canvas saves it). Otherwise every test here skips, and the suite never needs the canvas.

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

pytestmark = pytest.mark.skipif(not (OUT and BOARDS),
                                reason="board shots run only when asked (NMAS_BOARD_SHOTS, "
                                       "NMAS_BOARDS_DIR)")


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
