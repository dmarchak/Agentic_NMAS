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

**The CDN entries are C123's, and leave with it.** Four libraries load from
public CDNs, two unpinned. They are listed by exact path prefix, never by
host, so the policy admits those files and not the rest of the CDN.
"""

#: Script and style sources outside this origin, by exact path prefix (C123).
CDN_SCRIPTS = (
    "https://cdn.jsdelivr.net/npm/xterm/",            # device.html, the terminal (7.8)
    "https://cdn.jsdelivr.net/npm/socket.io-client/",  # device.html, the terminal (7.8)
    "https://unpkg.com/vis-network@9.1.6/",            # index.html, topology
    "https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/",  # index.html, device ordering
)
CDN_STYLES = ("https://cdn.jsdelivr.net/npm/xterm/",)

POLICY = "; ".join((
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' " + " ".join(CDN_SCRIPTS),
    "style-src 'self' 'unsafe-inline' " + " ".join(CDN_STYLES),
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
