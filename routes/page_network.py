"""Every request a v2 page makes is about the network the page was drawn for (W2's A1).

A ``?list=`` address set the network for the FIRST render only. Every later request the page
made (a fragment, a live re-fetch, a button's post, a link, a filter's form) carried no
network, so it was answered for the person's STORED choice (`network_choice`): History on a
network the address named flipped to Default's header and rows on its next live redraw,
expanding that network's commit ran git in Default's repository ("fatal: bad object"), and a
button would have acted on Default. Measured 2026-10-16 (A1's survey) on the 121 v2 pages the
interface walk renders: of 8,822 request addresses to a v2 route, 7,284 named no network
(1,337 of the 2,284 that are not plain links: fragments, live re-fetches, posts, forms). And
History's Verify the remote and Push now post outside /v2/, where only the installation's list
was ever read: on any other network's History they verified, and pushed, the installation's.

**The shape, made once, here:** the network a page is about (`page_network`: the network a
settings path names, else the address's ``?list=``, else the person's choice, else the
installation's, which is `listref.active_name()`, the very value the top bar's label draws) is
written into every request the page's HTML carries, as it leaves the server: each URL attribute
(`URL_ATTRS`) naming a v2 route (or one of `listref.PAGE_ROUTES_OUTSIDE_V2`) that does not
already name a network gets ``list=<it>``, and a
GET form gets it as a hidden field (a browser replaces a GET form's query with its fields). A
fragment is a v2 response too, so what it draws carries the network it was asked for, and the
page keeps its network however deep the redraws go. A redirect's or htmx's address header is
written the same way.

So the label, the picker and every request are one value, and another tab of the same person
choosing another network moves nothing on this one (the shape the operator's option (b), "the
address sets the stored choice", could not give: a read would write the choice, and every other
tab of that person would then redraw into the newly chosen network under its old label).

A route that is about no one network is declared here with its reason (`NETWORK_FREE`), and
its requests are left as drawn: the picker must open after the page's own network is deleted,
and the manual is the same for every network. A request naming a network that no longer exists
is refused before its view (`routes/list_param`), so a page whose network was deleted says so
in place rather than answering for another one.

tests/test_page_network.py holds the property on every page the interface walk renders and on
every v2 template and script.
"""

import functools
import html
import logging
import re
from urllib.parse import parse_qsl, quote, unquote, urlsplit

from flask import has_request_context, request

log = logging.getLogger(__name__)

#: The keys a request names its network by (`list_param.QUERY_KEYS`).
NETWORK_KEYS = ("list", "list_name")

#: Routes about no one network, each with why; their requests are left as drawn. A name ending
#: in ``*`` covers every endpoint it begins.
NETWORK_FREE = {
    "network_v2.*": ("the network picker lists and chooses among every network, and its label "
                     "says when the page's network was deleted: it must answer after that"),
    "settings_v2.scope": ("Settings' scope bar names its network in `at` and says when that "
                          "network was deleted, which it could not do refused"),
    "settings_v2.network_new": "a new network's form: the network does not exist yet",
    "settings_v2.network_create_preview": "a new network's preview: it does not exist yet",
    "settings_v2.network_create": "creating a network: it does not exist yet",
    # The installation's settings, every route under /v2/settings/installation: their endpoints
    # are named install_*, diag_*, platforms_* and records_*, never installation_* (the one
    # declaration "settings_v2.installation*" covered the page alone, and every card, save and
    # test on it named a network; tests/test_page_network.py holds the path to these names).
    "settings_v2.install*": "the installation's settings: every network's, no one's",
    "settings_v2.diag_*": "the installation's diagnostics: every network's, no one's",
    "settings_v2.platforms_*": "the installation's platforms: every network's, no one's",
    "settings_v2.records_*": "the installation's records stores: every network's, no one's",
    "v2.help_page": "the manual: the same for every network",
    "v2.help_panel": "the manual, in the help panel: the same for every network",
    "v2.about": "Help > About, a page of the manual: the software, the same for every network",
    "v2.installation_card": "About's installation card: the software, the same for every network",
    "v2.update*": "the application's Update page and its panel: the installation's",
    "device_v2.update_available": "the top bar's Update available: the installation's",
    # Requests v2 pages make outside /v2/ (`listref._request_choice` reads an address's network
    # there only for `PAGE_ROUTES_OUTSIDE_V2`): each is about every network, or names its own.
    "operations.in_flight": "In progress: what runs now in every network",
    "breakglass.export": ("the break-glass record names its network in its body, from the "
                          "preview that was confirmed, never from an address"),
    "update.*": "the application's update: the installation's",
    "health.health": "the application's health: the installation's",
    "static": "files the page loads",
}

#: The attributes a page's HTML carries a request in (htmx's verbs and history, a link, a form
#: and a button's form address, and a URL a script sends: `data-url`, `data-<what>-url`,
#: `data-panel-src`).
URL_ATTRS = ("href", "action", "formaction", "hx-get", "hx-post", "hx-put", "hx-patch",
             "hx-delete", "hx-push-url", "hx-replace-url", "data-url", "data-panel-src")
_ATTR = re.compile(r'(\s(?:href|action|formaction|hx-(?:get|post|put|patch|delete|push-url|'
                   r'replace-url)|data-url|data-[a-z-]+-url|data-panel-src)=")(/(?!/)[^"]*)(")')
#: A start tag, its quoted values honoured (a `>` inside one does not end it).
_FORM = re.compile(r"<form\b((?:\s+[^\s\"'>/=]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'>]+))?)*)"
                   r"\s*>", re.I)
_METHOD = re.compile(r"\smethod=\"([^\"]*)\"", re.I)
_ACTION = re.compile(r"\saction=\"(/(?!/)[^\"]*)\"")
_FORM_END = re.compile(r"</form\s*>", re.I)
_HAS_LIST_FIELD = re.compile(r"\sname=\"(?:list|list_name)\"")
#: Response headers that carry an address the browser goes to next.
URL_HEADERS = ("Location", "HX-Redirect", "HX-Push-Url", "HX-Replace-Url")


def is_network_free(endpoint: str) -> bool:
    """Is *endpoint* declared about no one network (`NETWORK_FREE`)?"""
    for name in NETWORK_FREE:
        if name.endswith("*") and endpoint.startswith(name[:-1]):
            return True
        if endpoint == name:
            return True
    return False


def page_network() -> str:
    """The network the page this request draws is about: the top bar's label's value."""
    from modules.nsot import listref

    return listref.active_name()


@functools.lru_cache(maxsize=4096)
def _route_of(url_map, path: str) -> tuple:
    """``(endpoint, names a network in its path)`` for *path* in *url_map*, or ``("", False)``
    when no route takes it (whether it resolves is tests/test_page_requests_resolve.py's)."""
    from werkzeug.exceptions import HTTPException

    adapter = url_map.bind("localhost")
    for method in ("GET", "POST"):
        try:
            rule, _args = adapter.match(unquote(path), method=method, return_rule=True)
        except HTTPException:
            continue
        return rule.endpoint, "list_name" in rule.arguments
    return "", False


def needs_network(url: str) -> bool:
    """Does *url* (as a browser reads it: entities decoded) need the page's network written in?
    An address on this app naming none, to a v2 route (or one outside /v2/ that answers for the
    page's network, `listref.PAGE_ROUTES_OUTSIDE_V2`) not declared network-free, whose path does
    not name a network itself."""
    from flask import current_app

    from modules.nsot.listref import PAGE_ROUTES_OUTSIDE_V2

    parts = urlsplit(url)
    if parts.scheme or parts.netloc or not parts.path.startswith("/"):
        return False
    if any(k in NETWORK_KEYS for k, _v in parse_qsl(parts.query, keep_blank_values=True)):
        return False
    endpoint, in_path = _route_of(current_app.url_map, parts.path)
    if not endpoint or in_path or is_network_free(endpoint):
        return False
    return parts.path.startswith("/v2/") or endpoint in PAGE_ROUTES_OUTSIDE_V2


def with_network(url: str, name: str, escaped: bool = False) -> str:
    """*url* naming the network *name*, when it needs it; else *url* unchanged. *escaped*: the
    URL is an HTML attribute's text (``&amp;`` between its parameters)."""
    raw = html.unescape(url) if escaped else url
    if not name or not needs_network(raw):
        return url
    head, hash_, frag = url.partition("#")
    amp = "&amp;" if escaped else "&"
    joiner = "" if head.endswith(("?", "&", amp)) else (amp if "?" in head else "?")
    return f"{head}{joiner}list={quote(name, safe='')}{hash_}{frag}"


def rewrite(text: str, name: str) -> str:
    """*text* (a v2 response's HTML) with every request it carries naming *name*."""
    if not name:
        return text
    text = _ATTR.sub(lambda m: m.group(1) + with_network(m.group(2), name, escaped=True)
                     + m.group(3), text)
    return _hidden_fields(text)


def _hidden_fields(text: str) -> str:
    """A GET form (no method, or ``get``) whose v2 address names a network, and which holds no
    field naming one, gets that network as a hidden field: a browser sends a GET form's fields
    as the WHOLE query, dropping the network its address carried (History's filters did)."""
    out, at = [], 0
    for m in _FORM.finditer(text):
        attrs = m.group(1)
        method = _METHOD.search(attrs)
        action = _ACTION.search(attrs)
        if (method and method.group(1).lower() != "get") or not action:
            continue
        end = _FORM_END.search(text, m.end())
        if _HAS_LIST_FIELD.search(text[m.end():end.start() if end else len(text)]):
            continue
        named = dict(parse_qsl(urlsplit(html.unescape(action.group(1))).query))
        key = next((k for k in NETWORK_KEYS if named.get(k)), "")
        if not key:
            continue
        out.append(text[at:m.end()])
        out.append(f'<input type="hidden" name="{key}" '
                   f'value="{html.escape(named[key], quote=True)}">')
        at = m.end()
    out.append(text[at:])
    return "".join(out)


def install(app) -> None:
    @app.after_request
    def _every_request_names_the_page_s_network(response):
        if not has_request_context() or not request.path.startswith("/v2/"):
            return response
        try:
            name = page_network()
        except Exception:                             # noqa: BLE001 (the page still answers)
            log.warning("page_network: the page's network could not be read", exc_info=True)
            return response
        from modules.nsot.listref import exists

        # A name no network has (an installation whose current list was never registered)
        # is not written: every request would then be refused, while unwritten they resolve
        # to that same installation list.
        if not name or not exists(name):
            return response
        for header in URL_HEADERS:
            value = response.headers.get(header)
            if value and value.startswith("/") and not value.startswith("//"):
                response.headers[header] = with_network(value, name)
        if (response.mimetype != "text/html" or response.direct_passthrough
                or response.is_streamed):
            return response
        body = response.get_data(as_text=True)
        written = rewrite(body, name)
        if written != body:
            response.set_data(written)
        return response
