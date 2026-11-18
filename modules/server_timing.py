"""Server-Timing per section (docs/mercury-gui-redesign-brief.md §6 step 1; the operator,
2026-11-18): a page's builder and its route name the sections they spent time in, and the
response carries them as the standard ``Server-Timing`` header, so a browser's developer tools
(and `scripts/nmas-page-timing`, the measurement) read where a page's server time went without a
log line. Timing only: nothing reads it to decide.

**What is recorded.** `add(name, seconds)` appends one section to the request's list (Flask's
``g``); `laps(laps)` appends each stage of a builder's own lap record (`pipeline.lap`'s
``[(name, epoch)]``, the incident page's and the incidents list's), so the header and the app
log's lap line come from one record; `timed(name)` times a block. Outside a request each is a
no-op, so a builder called by a job or a test pays nothing.

**The header** (`install`'s after-request hook): each section as ``<token>;dur=<ms>;desc="<name>"``
in the order recorded, then ``total`` from the request's first hook (`request_log`'s stamp, so a
refused request is timed alike). A section's name is Mercury's own words, never a value from the
request: a token is the name lower-cased with every other character a hyphen, and ``desc`` drops
quotes and backslashes. A response with no section gets ``total`` alone.

**Cost.** One list per request and one header; measured with no section, nothing but the header.
"""

import contextlib
import re
import time

from flask import g, has_request_context

#: The header (RFC: W3C Server Timing).
HEADER = "Server-Timing"
#: A section's token: the name lower-cased, every character but a letter, digit or hyphen a
#: hyphen, at most 40 characters.
_TOKEN = re.compile(r"[^a-z0-9-]+")


def _sections() -> list:
    if not has_request_context():
        return None
    got = getattr(g, "nmas_server_timing", None)
    if got is None:
        got = g.nmas_server_timing = []
    return got


def add(name: str, seconds: float) -> None:
    """Section *name* took *seconds* in this request; nothing outside a request."""
    sections = _sections()
    if sections is not None and seconds is not None:
        sections.append((str(name), max(0.0, float(seconds))))


def laps(record) -> None:
    """Each stage of a builder's lap record (``[(name, epoch)]``, its first entry the start)."""
    record = list(record or [])
    for (_, a), (name, b) in zip(record, record[1:]):
        add(name, b - a)


@contextlib.contextmanager
def timed(name: str):
    """The block's time as section *name*."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        add(name, time.perf_counter() - t0)


def token(name: str) -> str:
    """A section's header token: *name* lower-cased, other characters hyphens."""
    return _TOKEN.sub("-", str(name).lower()).strip("-")[:40] or "section"


def header_value(sections: list, total_s=None) -> str:
    """The header's value: each section, then ``total`` when *total_s* is known."""
    parts = []
    for name, seconds in sections or []:
        desc = str(name).replace('"', "").replace("\\", "")[:80]
        parts.append(f'{token(name)};dur={seconds * 1000:.1f};desc="{desc}"')
    if total_s is not None:
        parts.append(f"total;dur={total_s * 1000:.1f}")
    return ", ".join(parts)


def install(app) -> None:
    """The after-request hook that writes the header (installed after `request_log`'s, so its
    start stamp is set)."""

    @app.after_request
    def _server_timing(response):
        started = getattr(g, "nmas_request_started", None)
        total = time.monotonic() - started if started is not None else None
        value = header_value(getattr(g, "nmas_server_timing", None) or [], total)
        if value:
            response.headers[HEADER] = value
        return response
