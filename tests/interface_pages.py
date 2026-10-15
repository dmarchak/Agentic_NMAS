"""The pages a person navigates to, rendered, each with the scripts it loads.

**Not a test module.** The checks that ask a question of "the interface" (is every route
reached, does every request resolve, has every function a caller, is every GUI blueprint
called) read it from here, so there is one answer to what the interface is, and removing
today's pages (`/` and `/device/<ip>`, Phase 7's removals) changes the answer without
breaking a check (P7-19, 2026-10-15; they rendered `/` and `/device/<ip>` until then).

**v2, by property:** every full v2 page (a 200 `text/html` document) reached by following
`<a href>` links from Needs attention (`/v2/`) and from a device page, on test_device_v2's
lab, with a device that has a committed golden (r3) and one that has none (r9). A link counts
once per path and `tab`: a query's other parameters are a filter's, a range's or a query's
(History's saved queries alone are about a hundred), and render the same page's controls.
A page is new to the population the commit that links it, with nothing listed here.
Measured 2026-10-15: 119 pages, in about 3.5 s.

**Today's pages while they exist** (`TODAYS_PAGES`), each rendered with a device as it was
before (with no device the index's per-device loop renders nothing and the device page
redirects). A page whose route is gone contributes nothing, and so does one that redirects
into v2 (`/` at cutover); any other answer is a failure, never a page quietly left out.

What it cannot see, stated: a v2 page reached only by a form or a script (a batch's Apply,
Re-apply, Bulk intent, a pending or retired device's page), whose own references are in its
template's `url_for` and the shared scripts every page loads; and a link built by a script.
"""

import contextlib
import re
import tempfile
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlsplit

from tests.js_source import loaded_scripts

#: Where the walk starts: Needs attention, and a device page in each golden state.
START = ("/v2/", "/v2/device/r3", "/v2/device/r9")
#: The query parameters that make a different page (a device or settings tab, the intent
#: editor open); any other parameter is a filter over the same page.
PAGE_PARAMS = ("tab", "edit")
#: A bound on the walk, about 2.5x the 119 pages measured (2026-10-15); reaching it fails.
MAX_PAGES = 300

#: Today's device for today's pages (route_references' fixture device since Stage 7.0).
FIXTURE_DEVICE = {"ip": "192.0.2.1", "hostname": "r1", "device_type": "cisco_ios",
                  "username": "admin", "password": "", "secret": ""}
#: Today's pages, until Phase 7 removes them (P7-22 the device page, P7-27 the index).
TODAYS_PAGES = ("/", f"/device/{FIXTURE_DEVICE['ip']}")

_LINK = re.compile(r'<a\b[^>]*\bhref="(/v2/[^"#]*)"')
_CACHE: dict = {}


def _page_key(href: str) -> str:
    parts = urlsplit(unescape(href))
    keep = [(k, v) for k, v in parse_qsl(parts.query) if k in PAGE_PARAMS]
    return parts.path + ("?" + urlencode(keep) if keep else "")


def _is_document(response, body: str) -> bool:
    return (response.status_code == 200 and response.mimetype == "text/html"
            and "<html" in body[:600].lower())


def _walk(client) -> dict:
    todo, seen, pages = list(START), set(), {}
    while todo:
        url = todo.pop(0)
        if url in seen:
            continue
        seen.add(url)
        assert len(pages) < MAX_PAGES, (
            f"the walk reached {MAX_PAGES} pages, its bound (2.5x the 119 measured "
            "2026-10-15): a page that links without end, or a bound to re-measure")
        r = client.get(url, headers={"Accept": "text/html"})
        body = r.get_data(as_text=True)
        if not _is_document(r, body):
            assert url not in START, f"{url} did not render ({r.status_code})"
            continue
        pages[url] = body
        todo += [k for k in map(_page_key, _LINK.findall(body)) if k not in seen]
    return pages


def _todays(app_module, monkeypatch, client) -> dict:
    from werkzeug.exceptions import MethodNotAllowed, NotFound

    monkeypatch.setattr(app_module, "load_saved_devices",
                        lambda *a, **k: [dict(FIXTURE_DEVICE)], raising=False)
    monkeypatch.setattr(app_module, "get_device_context",
                        lambda d, *a, **k: (["flash:"], [], "flash:"), raising=False)
    adapter = app_module.app.url_map.bind("localhost")
    out = {}
    for path in TODAYS_PAGES:
        try:
            adapter.match(path, method="GET")
        except (NotFound, MethodNotAllowed):
            continue                     # removed: nothing of it is the interface any more
        r = client.get(path, headers={"Accept": "text/html"})
        if r.status_code in (301, 302, 303, 307, 308):
            where = urlsplit(r.headers.get("Location", "")).path
            assert where.startswith("/v2/"), f"{path} redirects to {where!r}, not into v2"
            continue
        body = r.get_data(as_text=True)
        assert _is_document(r, body), f"{path} did not render ({r.status_code})"
        out[path] = body
    return out


def as_a_verified_person(mp) -> None:
    """The walk is a verified person's, whoever asks for it: a gated control is drawn only for
    a viewer who may use it (C738), and conftest's verified person is a FUNCTION-scoped
    fixture, absent when a module-scoped fixture builds the pages. Without this the editor's
    Edit was missing from the population exactly when the first caller was module-scoped
    (measured 2026-10-15: the intent editor's three references, present or absent by order)."""
    from modules import identity
    from tests.conftest import TEST_PERSON

    person = identity.Identity(actor=TEST_PERSON, email=TEST_PERSON, kind="person",
                               verified=True, outcome="ok", peer="198.51.100.7",
                               peer_trusted=True, header_present=True)
    mp.setattr(identity, "identify", lambda _request: person)


def _commit_intent(repo: str, host: str) -> None:
    """*host*'s intent, extracted from its committed golden by the real parser and committed
    as an extraction is (test_profile_apply's lab does the same for r6): without it the
    Intent tab draws no editor, and the editor's references are not in the population."""
    from modules.nsot import hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import save_host_vars

    golden = open(f"{repo}/golden/{host}.cfg", encoding="utf-8").read()
    hv = get_parser("cisco_iosxe").parse(golden)
    hv["hostname"] = host           # the lab commits r2's real config as r3's golden
    hostvars.write_committed(repo, hv)
    out = save_host_vars("Lab", [host], actor="t", source="extraction")
    assert out["ok"], out


def pages() -> dict:
    """``{"v2": {url: html}, "todays": {url: html}}``, each page's HTML as served (its
    scripts are `scripts()`).

    Built once per test process, on its own lab and MonkeyPatch, both undone before it
    returns: the answer is text, and no caller's state is the lab's."""
    if "pages" in _CACHE:
        return _CACHE["pages"]
    import pytest

    import app as A
    from tests.test_device_v2 import lab_setup

    mp = pytest.MonkeyPatch()
    try:
        as_a_verified_person(mp)
        with tempfile.TemporaryDirectory(prefix="nmas-interface-") as tmp:
            import pathlib

            with contextlib.contextmanager(lab_setup)(pathlib.Path(tmp), mp) as lab:
                _commit_intent(lab["repo"], "r3")
                v2 = _walk(lab["client"])
                todays = _todays(A, mp, lab["client"])
    finally:
        mp.undo()
    _CACHE["pages"] = {"v2": v2, "todays": todays}
    return _CACHE["pages"]


def scripts(which=("v2", "todays")) -> dict:
    """``{path under static/js: text}``: the project's scripts the pages of *which* load, each
    once (v2's pages each load the same two dozen; appended per page, the corpus was 22 MB)."""
    out = {}
    for group in which:
        for html in pages()[group].values():
            out.update(loaded_scripts(html))
    return out


def corpus(which=("v2", "todays")) -> str:
    """Every page's HTML (v2's first, then today's), then each script those pages load, once,
    each in a ``<script>`` element as `with_loaded_scripts` appends it."""
    p = pages()
    html = [text for group in which for text in p[group].values()]
    return "\n".join(html + [f"<script>\n{s}\n</script>" for s in scripts(which).values()])


def v2_corpus() -> str:
    """v2's pages and the scripts they load: what is left when today's pages are gone."""
    return corpus(("v2",))
