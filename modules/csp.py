"""The Content-Security-Policy on every HTML page (C88, option (c)).

**The belt, not the braces** (the operator, 2026-09-27). The fix for an
unescaped value in HTML is ESCAPING it, and that happens screen by screen as
Stage 7 rebuilds each one: the preview and result components escape every
field they draw. This policy bounds the damage meanwhile, and says honestly
how far it bounds it.

**What it cannot do: stop injected script from RUNNING.** The pages carry 273
inline `on…=` handlers in the templates, 36 more built as strings in the
shipped JavaScript and 12 inline `<script>` blocks (measured 2026-09-27).
Nonces cover script blocks and never inline handlers, so `script-src` keeps
`'unsafe-inline'` until those are gone, which is a migration of about 300
sites, not a header.

**What it does bound:** where injected script can SEND data and what it can
LOAD. `connect-src 'self'` keeps fetch, XHR and WebSockets on this origin;
`script-src` loads scripts only from here and the listed CDN paths;
`form-action 'self'` keeps form posts here; `object-src 'none'`,
`base-uri 'self'` and `frame-ancestors 'none'` close plugins, base-tag
rewriting and framing. A top-level navigation carrying data off the page is
NOT blockable by CSP, and the policy does not pretend otherwise.

**No CDN is admitted** (C123, closed 2026-09-28). While four libraries
loaded from public CDNs the policy had to admit them, which is a policy
permitting the thing it should block; they are vendored now, so script and
style come from this origin only.
"""

#: Script and style sources outside this origin: NONE (C123). The four
#: libraries that loaded from public CDNs, two unpinned, are vendored from
#: registry-verified tarballs (static/js/vendor/MANIFEST.json), so the policy
#: admits nothing that is not served from here.
CDN_SCRIPTS = ()
CDN_STYLES = ()

POLICY = "; ".join((
    "default-src 'self'",
    " ".join(("script-src 'self' 'unsafe-inline'",) + CDN_SCRIPTS),
    " ".join(("style-src 'self' 'unsafe-inline'",) + CDN_STYLES),
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
))


def install(app) -> None:
    """Set the policy on every HTML response that does not carry its own."""

    @app.after_request
    def _content_security_policy(response):
        if (response.mimetype == "text/html"
                and "Content-Security-Policy" not in response.headers):
            response.headers["Content-Security-Policy"] = POLICY
        return response
