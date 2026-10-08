"""A v2 page or part that failed, answered ON v2, in place, with its status.

C569 (the operator's walk, 2026-10-08): Coverage raised on a cell, and the app's error handler
redirected the navigation to today's index, so the Coverage tab and a result's "Back to
Coverage", both correct links, opened today's page. A failure is never a redirect to another
interface: it says "Couldn't load", with what failed, under the strict policy, and links back
to v2. An htmx part gets the notice alone, to draw in place.

The minimal state, not a designed screen: a designed v2 error page needs a mockup and the
operator's sign-off first (the cutover gap `v2_error_page`, tests/todays_page_links.py).
"""

import logging

log = logging.getLogger(__name__)


def answer(message: str, status: int):
    """The response for a failed v2 request that wants HTML: *message* names what failed."""
    from flask import make_response, request, url_for
    from html import escape

    from modules.csp import STRICT_POLICY

    notice = (f'<div class="notice notice-danger" role="alert"><p>Couldn\'t load: '
              f'{escape(message)}</p></div>')
    if request.headers.get("HX-Request"):
        body = notice
    else:
        body = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                "<title>Couldn't load</title>"
                f'<link rel="stylesheet" href="{url_for("static", filename="css/nmas-v2.css")}">'
                f'</head><body><main class="v2-failure">{notice}'
                f'<p><a href="{url_for("v2.landing")}">Needs attention</a></p></main>'
                '</body></html>')
    response = make_response(body, status)
    response.headers["Content-Security-Policy"] = STRICT_POLICY
    return response
