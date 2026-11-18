"""Server-Timing per section (modules/server_timing.py; the redesign brief §6 step 1): a page's
sections reach the response's header in order with the request's total, a builder's lap record
becomes one section per stage, a section's name can never write the header's syntax, and outside
a request every call costs nothing."""

import time

from flask import Flask

from modules import request_log, server_timing


def _app():
    app = Flask(__name__)
    request_log.install(app)
    server_timing.install(app)

    @app.route("/page")
    def page():
        t0 = time.time()
        server_timing.laps([("start", t0), ("resolve", t0 + 0.25), ("AI section", t0 + 1.0)])
        with server_timing.timed("render"):
            pass
        return "ok"

    @app.route("/bare")
    def bare():
        return "ok"

    return app


def test_the_sections_reach_the_header_in_order_with_the_total():
    got = _app().test_client().get("/page").headers["Server-Timing"]
    parts = [p.strip() for p in got.split(",")]
    assert [p.split(";")[0] for p in parts] == ["resolve", "ai-section", "render", "total"]
    assert parts[0] == 'resolve;dur=250.0;desc="resolve"'
    assert parts[1] == 'ai-section;dur=750.0;desc="AI section"'
    assert float(parts[-1].split("dur=")[1]) >= 0


def test_a_page_with_no_section_carries_the_total_alone():
    got = _app().test_client().get("/bare").headers["Server-Timing"]
    assert got.startswith("total;dur=") and "," not in got


def test_a_name_never_writes_the_headers_syntax():
    value = server_timing.header_value([('a"b;c,d\\e', 0.001)])
    assert value == 'a-b-c-d-e;dur=1.0;desc="ab;c,de"'
    assert server_timing.token("Needs attention item") == "needs-attention-item"
    assert server_timing.token("") == "section"


def test_outside_a_request_every_call_is_nothing():
    server_timing.add("x", 1.0)
    server_timing.laps([("start", 0.0), ("x", 1.0)])
    with server_timing.timed("y"):
        pass
