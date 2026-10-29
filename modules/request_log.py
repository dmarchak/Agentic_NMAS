"""One line per request for the record (C1836): method, path, status, duration and the verified
actor, so a refusal on a walk can be matched to the requests that preceded it.

werkzeug's own line (method, path with its query, status) already reaches the app's log file;
it carries neither how long the request took nor who made it. This line carries both, and
carries NO query string and no form value: what a person typed never reaches the log by this
path (a search, a reason, a value in a query is read by its route, never written here). Static
files are left to werkzeug's line: they have no actor worth reading and are most of the volume.

The actor is `identity.request_actor()`, the verified one (`UNVERIFIED` when the assertion was
not verified), never a name the request carries.

The line goes to the log file (through the root logger, as every module's) AND to standard
output, which under systemd is flask-app's journal: the journal held starts and stops only, and
the prepared host step (scripts/host-steps/c1836-flask-app-journal.sh) brings that journal into
Loki, so these lines reach Loki with no file permission widened for Alloy."""

import logging
import sys
import time
from urllib.parse import quote

from flask import g, request

log = logging.getLogger(__name__)

#: Paths whose requests get no line here (werkzeug's still records them).
SKIP_PREFIXES = ("/static/",)


class _Stdout(logging.StreamHandler):
    """Standard output as it is when a line is written, never the stream that was current at
    install (a test harness swaps it per test; a held stream would be closed)."""

    def emit(self, record):
        self.stream = sys.stdout
        super().emit(record)


def _to_stdout() -> None:
    """Once per process: this module's lines to standard output too. Masked as every handler
    is: app.py's `redact.redact_all_handlers()` runs after the blueprints are registered."""
    if any(isinstance(h, _Stdout) for h in log.handlers):
        return
    handler = _Stdout()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


#: What a path keeps unencoded on the line: a path's own punctuation, never a space, a percent
#: sign or a control character.
PATH_SAFE = "/-._~!$&'()*+,;=:@"


def line(method: str, path: str, status: int, ms, actor: str) -> str:
    """The line's text: ``request GET /v2/history 200 1203ms actor=<person>``.

    The path is the client's, decoded: percent-encoded here, so no request can write a line of
    its own choosing (a newline, or a device's syslog form, which Mercury's syslog reads count in
    any job once the journal reaches Loki)."""
    took = f"{ms:.0f}ms" if ms is not None else "?ms"
    return f"request {method} {quote(path, safe=PATH_SAFE)} {status} {took} actor={actor}"


def install(app) -> None:
    """Time every request from its first hook and log its line as the response leaves.
    Installed before the gate's hook, so a request the gate refuses is timed too."""
    _to_stdout()

    @app.before_request
    def _request_started():
        g.nmas_request_started = time.monotonic()

    @app.after_request
    def _request_line(response):
        try:
            path = request.path or ""
            if not path.startswith(SKIP_PREFIXES):
                from modules import identity
                started = getattr(g, "nmas_request_started", None)
                ms = (time.monotonic() - started) * 1000 if started is not None else None
                log.info("%s", line(request.method, path, response.status_code, ms,
                                    identity.request_actor()))
        except Exception as exc:                        # noqa: BLE001
            log.warning("request log: no line for this request (%s)", type(exc).__name__)
        return response
