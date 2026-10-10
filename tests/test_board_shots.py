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


def _shoot(name, board_file, page_url_for, served, widths=((1280, 1.0), (390, 2.0))):
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
    T._store(T._read(previous=T._read()))
    import app as A
    with browser.Served(A.app) as served:
        _shoot("logs", "AskLogs.dc.html",
               lambda w: "/v2/logs?list=Lab&range=120d&sev=all&d=r4", served,
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
