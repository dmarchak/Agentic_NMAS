"""W2's A1 (the operator, 2026-10-17): a v2 page keeps the network it was drawn for.

A ``?list=`` address set the network for the first render only; every later request followed
the person's STORED choice. On W2 walk's History a live redraw drew Default's header ("in sync
… pushed to <Default's remote>") and Default's rows, expanding W2 walk's seed commit read
"fatal: bad object" (git ran in Default's repository), the top bar read "W2 walk" while the
picker marked Default, the top bar kept naming W2 walk after its delete, and the picker on
``/v2/settings/network/W2 walk`` reloaded that path with ``?list=Default``.

**On two networks made by the real create path** (Default, and Branch made as on v2, C931), each
seeded so each has its own commit, each with its own remote said by the remote read, and the
verified person's stored choice Default, with History opened at ``?list=Branch``:

- the top bar's label and the picker it draws name Branch, and agree on Default when the page
  is opened with no network named;
- every fragment and live re-fetch the page draws answers for Branch (its remote, its commit),
  and draws nothing naming Default;
- History's commit expand reads Branch's repository;
- a button's post (History's Verify the remote) acts on Branch, and so does the filters' plain
  GET form;
- another tab of the same person choosing Branch moves nothing on a page drawn for Default;
- after Branch's delete, the label says deleted, never Branch, and the page's redraws and
  buttons are refused naming Branch, never answered for Default;
- the picker on a network's settings path opens the chosen network's settings path, and a
  settings path naming a deleted network is refused even with another's ``?list=``.

**Structurally** (`TestEveryRequestNamesThePageSNetwork`): every request on every page the
interface walk renders (tests/interface_pages.py) names the page's network or goes to a route
declared network-free with its reason (`routes/page_network.NETWORK_FREE`); every request a v2
template draws with `url_for` goes to a route that can name it, or a declared one; and every
request call in the scripts v2 pages load is declared with how it carries the network.
"""

import re
from html import unescape
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from tests.conftest import TEST_PERSON
from tests.test_network_born_a_repository import _create, _seed, _sh, store  # noqa: F401

#: A start tag, its quoted values honoured; and one attribute in it.
_TAG = re.compile(r"<([a-zA-Z][\w:-]*)((?:\s+[^\s\"'>/=]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|"
                  r"[^\s\"'>]+))?)*)\s*/?>", re.S)
_ATTR = re.compile(r"([^\s\"'>/=]+)(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+)))?", re.S)
#: The attributes a page carries a request in, found by property: htmx's verbs and history, a
#: link, a form's and a button's address, and any `data-*` holding an address a script sends.
_VERBS = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")


def _attrs(body: str) -> dict:
    return {m.group(1): (m.group(2) if m.group(2) is not None else (m.group(3) or m.group(4)
                                                                     or ""))
            for m in _ATTR.finditer(body)}


def requests_in(text: str) -> list:
    """``[(tag, attribute, address)]``: every address on this app a page's HTML carries a
    request in, decoded as a browser reads it. Independent of `routes/page_network` (its own
    parse, its own idea of which attributes carry one): the control for that module."""
    out = []
    for m in _TAG.finditer(text):
        tag = m.group(1).lower()
        for k, v in _attrs(m.group(2)).items():
            v = unescape(v)
            if not v.startswith("/") or v.startswith("//"):
                continue
            if (k in _VERBS or k in ("href", "action", "formaction", "hx-push-url",
                                     "hx-replace-url")
                    or (k.startswith("data-") and (k.endswith("url") or k.endswith("src")))):
                out.append((tag, k, v))
    return out


def _named(url: str) -> str:
    return (parse_qs(urlsplit(url).query).get("list") or [""])[0]


def _drawn(text: str, attr: str, path: str) -> str:
    """The one address *text* draws in *attr* to *path*."""
    got = sorted({u for _t, k, u in requests_in(text) if k == attr
                  and urlsplit(u).path == path})
    assert len(got) == 1, f"the page draws {attr} to {path} as {got}"
    return got[0]


def _label(text: str) -> str:
    m = re.search(r'<details class="net net-pick menu-wrap"[^>]*>.*?<strong[^>]*>\s*(.*?)\s*'
                  r'</strong>', text, re.S)
    assert m, "no network label in the top bar"
    return m.group(1)


def _marked(text: str) -> list:
    return re.findall(r'class="net-row on" aria-current="true"[^>]*>'
                      r'(?:<span class="op-idle[^"]*">)?<span class="grow">(.*?)</span>', text)


REMOTES = {"Default": "example/default-config", "Branch": "example/branch-config"}


@pytest.fixture
def two(store, monkeypatch):  # noqa: F811
    """Default and Branch (the real create path), each seeded (its own commit), each with its
    own remote as the remote read says it; the verified person's stored choice is Default."""
    from modules import network_choice
    from modules.readers import remote_publication as RP

    _create(store, "Branch")
    sha = {}
    for name, slug in (("Default", "default"), ("Branch", "branch")):
        r = _seed(store, name)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        # Two seeds in one second are byte-identical commits, so each network then commits a
        # file of its own: a commit only its repository holds (W2 walk's seed was one).
        repo = store["data"] / "lists" / slug / "config_repo"
        (repo / "templates" / f"{slug}_own.j2").write_text(f"! {name}'s own\n", encoding="utf-8")
        assert _sh(repo, "add", f"templates/{slug}_own.j2")[0] == 0
        assert _sh(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit",
                   "-qm", f"template: {name}'s own")[0] == 0
        sha[name] = _sh(repo, "rev-parse", "HEAD")[1]
    assert sha["Default"] != sha["Branch"] and all(len(s) == 40 for s in sha.values()), sha

    def status_for(list_name, cached=None):
        if list_name not in REMOTES:
            return {}
        return {"state": "in_sync", "remote": REMOTES[list_name], "branch": "main",
                "head": sha[list_name], "remote_head": sha[list_name]}
    monkeypatch.setattr(RP, "status_for", status_for)

    c = store["client"]
    r = c.post("/v2/network/choose", data={"name": "Default", "next": "/v2/history"},
               headers={"HX-Request": "true"})
    assert r.status_code == 204, r.get_data(as_text=True)[:300]
    assert network_choice.of(TEST_PERSON)["current"] == "Default"
    return dict(store, sha=sha)


def _page(c, path):
    r = c.get(path, headers={"Accept": "text/html"})
    assert r.status_code == 200, (path, r.status_code, r.get_data(as_text=True)[:300])
    return r.get_data(as_text=True)


def _ask(c, url):
    """As htmx asks for a fragment."""
    return c.get(url, headers={"HX-Request": "true"})


@pytest.fixture
def verified(monkeypatch):
    """History's Verify the remote, recording the network it was asked for (no remote is
    contacted)."""
    from modules.nsot import remote as NR

    asked = []

    def verify(list_name, with_write_probe=False, actor=""):
        asked.append(list_name)
        return {"ok": True, "checks": [], "list": list_name}
    monkeypatch.setattr(NR, "verify", verify)
    return asked


class TestRefreshExpandAndAButtonOnANonDefaultNetwork:
    """The operator's test: History at ``?list=Branch``, the stored choice Default."""

    def test_the_label_and_the_picker_name_the_page_s_network(self, two):
        c = two["client"]
        for path, network in (("/v2/history?list=Branch", "Branch"), ("/v2/history", "Default")):
            page = _page(c, path)
            assert _label(page) == network, path
            picker = _drawn(page, "hx-get", "/v2/network/picker")
            assert _marked(_ask(c, picker).get_data(as_text=True)) == [network], (path, picker)

    def test_every_fragment_and_live_refetch_the_page_draws_is_branch_s(self, two):
        c = two["client"]
        page = _page(c, "/v2/history?list=Branch")
        fragments = sorted({u for _t, k, u in requests_in(page) if k == "hx-get"})
        live = [u for u in fragments if urlsplit(u).path in ("/v2/history/remote",
                                                             "/v2/history/timeline")]
        assert len(fragments) >= 10 and len(live) == 2, fragments
        for url in fragments:
            r = _ask(c, url)
            text = r.get_data(as_text=True)
            assert r.status_code < 500, (url, r.status_code)
            assert "Default" not in {_named(u) for _t, _k, u in requests_in(text)}, (
                f"{url} drew a request naming Default on Branch's page")
        remote = _flat(_ask(c, _drawn(page, "hx-get", "/v2/history/remote")))
        assert REMOTES["Branch"] in remote and REMOTES["Default"] not in remote, remote[:600]
        timeline = _ask(c, _drawn(page, "hx-get", "/v2/history/timeline")).get_data(as_text=True)
        assert two["sha"]["Branch"][:12] in timeline, "Branch's seed commit is not on its page"
        assert two["sha"]["Default"][:12] not in timeline, "Default's rows on Branch's page"

    def test_history_s_commit_expand_reads_branch_s_repository(self, two):
        c = two["client"]
        page = _page(c, "/v2/history?list=Branch")
        timeline = _ask(c, _drawn(page, "hx-get", "/v2/history/timeline")).get_data(as_text=True)
        expand = [u for _t, k, u in requests_in(timeline) if k == "hx-get"
                  and urlsplit(u).path == f"/v2/history/commit/{two['sha']['Branch']}"]
        assert expand, "no Show the change for Branch's own commit"
        text = _ask(c, expand[0]).get_data(as_text=True)
        assert "could not be read" not in text and "bad object" not in text, text[:400]
        assert "templates/branch_own.j2" in text, text[:400]

    def test_a_button_s_post_acts_on_branch(self, two, verified):
        """Verify the remote, as nmas_history.js sends it: a JSON post to its drawn address."""
        c = two["client"]
        page = _page(c, "/v2/history?list=Branch")
        for card in (page, _ask(c, _drawn(page, "hx-get", "/v2/history/remote"))
                     .get_data(as_text=True)):
            url = _drawn(card, "data-url", "/remote/verify")
            r = c.post(url, json={})
            assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert verified == ["Branch", "Branch"], verified

    def test_the_filters_form_keeps_branch(self, two):
        """The Timeline's filters are a plain GET form: a browser sends its fields as the whole
        query, dropping any its address carried."""
        c = two["client"]
        page = _page(c, "/v2/history?list=Branch")
        form = re.search(r'<form\b[^>]*\baction="(/v2/history[^"]*)"[^>]*>(.*?)</form>', page,
                         re.S)
        assert form and not re.search(r'\bmethod="post"', form.group(0), re.I), "no filters form"
        fields = [(a["name"], a.get("value", "")) for a in
                  (_attrs(m.group(1)) for m in re.finditer(r"<input\b([^>]*)>", form.group(2)))
                  if a.get("name") and a.get("type") != "checkbox"]
        sent = urlsplit(unescape(form.group(1))).path + "?" + urlencode(fields)
        assert _label(_page(c, sent)) == "Branch", sent

    def test_another_tab_choosing_another_network_moves_nothing_here(self, two):
        """The stored choice is the person's across tabs: a page drawn for Default keeps
        answering for Default when another tab chooses Branch."""
        c = two["client"]
        page = _page(c, "/v2/history")
        assert _label(page) == "Default"
        r = c.post("/v2/network/choose", data={"name": "Branch", "next": "/v2/history"},
                   headers={"HX-Request": "true"})
        assert r.status_code == 204
        timeline = _ask(c, _drawn(page, "hx-get", "/v2/history/timeline")).get_data(as_text=True)
        assert two["sha"]["Default"][:12] in timeline and two["sha"]["Branch"][:12] not in timeline


def _flat(r):
    return re.sub(r"\s+", " ", r.get_data(as_text=True))


def _delete(c, name):
    pv = _flat(c.post(f"/v2/settings/network/{name}/delete/preview",
                      headers={"HX-Request": "true"}))
    fp = re.search(r'name="fingerprint" value="([0-9a-f]+)"', pv)
    assert fp, pv[:600]
    r = c.post(f"/v2/settings/network/{name}/delete", data={"typed": name,
                                                            "fingerprint": fp.group(1)},
               headers={"HX-Request": "true"})
    assert r.status_code == 200 and "is deleted" in _flat(r), _flat(r)[:600]


class TestAfterTheNetworkIsDeleted:
    def test_the_label_says_deleted_and_nothing_answers_for_another_network(self, two, verified):
        c = two["client"]
        page = _page(c, "/v2/history?list=Branch")
        label = _drawn(page, "hx-get", "/v2/network/label")
        timeline = _drawn(page, "hx-get", "/v2/history/timeline")
        verify = _drawn(page, "data-url", "/remote/verify")
        _delete(c, "Branch")
        said = _ask(c, label).get_data(as_text=True)
        assert re.search(r">\s*deleted\s*</strong>", said) and ">Branch<" not in said, said
        # The page's redraw and its button are refused naming Branch, never answered for the
        # stored choice (Default).
        r = _ask(c, timeline)
        assert r.status_code == 404 and r.get_json()["unknown_list"] == "Branch", r.status_code
        r = c.post(verify, json={})
        assert r.status_code == 404 and r.get_json()["unknown_list"] == "Branch"
        assert verified == [], "the button acted on another network"
        # The picker still opens, and marks no network as the one shown.
        picker = _ask(c, _drawn(page, "hx-get", "/v2/network/picker"))
        assert picker.status_code == 200 and _marked(picker.get_data(as_text=True)) == []

    def test_a_settings_path_naming_it_draws_it_deleted_whatever_the_query_names(self, two):
        """Never Default's, nor Branch's live cards: its deleted page (C1029,
        tests/test_deleted_network.py), with nothing to act on."""
        c = two["client"]
        _delete(c, "Branch")
        r = c.get("/v2/settings/network/Branch?list=Default")
        assert r.status_code == 410 and "<strong>Branch was deleted</strong>" in _flat(r)
        assert "set-card" not in _flat(r) and "hx-post" not in _flat(r).split("<main", 1)[1]


class TestThePickerOnANetworkSSettingsPath:
    def test_choosing_opens_the_chosen_network_s_settings(self, two):
        c = two["client"]
        page = _page(c, "/v2/settings/network/Branch")
        assert _label(page) == "Branch"
        assert _marked(_ask(c, _drawn(page, "hx-get", "/v2/network/picker"))
                       .get_data(as_text=True)) == ["Branch"]
        r = c.post("/v2/network/choose", data={"name": "Default",
                                               "next": "/v2/settings/network/Branch"},
                   headers={"HX-Request": "true"})
        assert r.headers["HX-Redirect"] == "/v2/settings/network/Default", r.headers
        landed = _page(c, r.headers["HX-Redirect"])
        assert _label(landed) == "Default"


# ── Structural: every request, every page, template and script ─────────────────────────────

def _endpoint(app, path: str) -> tuple:
    from urllib.parse import unquote

    from werkzeug.exceptions import HTTPException

    adapter = app.url_map.bind("localhost")
    for method in ("GET", "POST"):
        try:
            rule, _a = adapter.match(unquote(path), method=method, return_rule=True)
        except HTTPException:
            continue
        return rule.endpoint, "list_name" in rule.arguments
    return "", False


def unnamed(app, text: str) -> list:
    """Every request in *text* that names no network and goes to a route not declared
    network-free and whose path names none: the property, as `(attribute, address)`. A GET
    form is judged by the fields a browser sends, which replace its address's query. (WHICH
    network a request names is the behavioural tests' question above: a page may link to
    another network's on purpose, Needs attention's rows and Monitoring's network menu do.)"""
    from routes.page_network import is_network_free

    def free(path):
        endpoint, in_path = _endpoint(app, path)
        return not endpoint or in_path or is_network_free(endpoint)

    out = []
    for _tag, k, url in requests_in(text):
        if not free(urlsplit(url).path) and not _named(url):
            out.append((k, url))
    for m in re.finditer(r"<form\b([^>]*)>(.*?)</form>", text, re.S):
        a = _attrs(m.group(1))
        action = unescape(a.get("action", ""))
        if (a.get("method") or "get").lower() != "get" or not action.startswith("/"):
            continue
        if free(urlsplit(action).path):
            continue
        fields = dict((x.get("name"), x.get("value")) for x in
                      (_attrs(i.group(1)) for i in re.finditer(r"<input\b([^>]*)>", m.group(2))))
        if not fields.get("list"):
            out.append(("GET form fields", action))
    return out


class TestEveryRequestNamesThePageSNetwork:
    def test_the_check_finds_a_planted_request_and_passes_a_named_one(self):
        import app as A

        with A.app.test_request_context("/v2/"):
            planted = ('<section hx-get="/v2/history/timeline" hx-trigger="nmas:goldens from:body">'
                       '<a href="/v2/devices?list=Lab">x</a><a href="/v2/help/history">h</a>'
                       '<form action="/v2/history?list=Lab"><input name="device"></form>'
                       '<span data-url="/remote/verify"></span></section>')
            assert unnamed(A.app, planted) == [
                ("hx-get", "/v2/history/timeline"), ("data-url", "/remote/verify"),
                ("GET form fields", "/v2/history?list=Lab")]

    def test_every_page_the_walk_renders(self):
        """Every request on the 121 v2 pages tests/interface_pages.py renders: 8,822 to a v2
        route on 2026-10-16, 7,284 of them naming no network before A1's fix. And on each page
        the most requests name the network its top bar names (the ones the page wrote)."""
        import collections

        import app as A

        from tests import interface_pages

        pages = interface_pages.pages()["v2"]
        assert len(pages) >= 100, len(pages)
        seen, missing, own = 0, {}, []
        with A.app.test_request_context("/v2/"):
            for url, text in pages.items():
                found = requests_in(text)
                seen += len(found)
                for got in unnamed(A.app, text):
                    missing.setdefault(got, url)
                counts = collections.Counter(_named(u) for _t, _k, u in found if _named(u))
                if counts and counts.most_common(1)[0][0] != _label(text):
                    own.append((url, _label(text), counts.most_common(2)))
        assert seen >= 5000, seen
        assert not missing, (f"{len(missing)} requests name no network, e.g. "
                             f"{sorted(missing.items())[:8]}")
        assert not own, f"pages whose requests mostly name another network than their label: {own}"

    def test_every_url_for_a_template_draws_can_name_the_network(self):
        """Every route a v2 template's `url_for` names is a v2 route (whose requests name the
        page's network as they leave), a route outside /v2/ that reads it there
        (`listref.PAGE_ROUTES_OUTSIDE_V2`), or one declared network-free with its reason."""
        import pathlib

        import app as A
        from modules.nsot.listref import PAGE_ROUTES_OUTSIDE_V2
        from routes.page_network import NETWORK_FREE, is_network_free

        rules = {}
        for r in A.app.url_map.iter_rules():
            rules.setdefault(r.endpoint, []).append(r.rule)
        from tests.source_index import tracked

        named = {}
        for p in map(pathlib.Path, tracked("templates/v2", suffix=".html", recursive=False)):
            for m in re.finditer(r"url_for\(\s*'([\w.]+)'", p.read_text(encoding="utf-8")):
                named.setdefault(m.group(1), p.name)
        assert len(named) >= 200, len(named)
        def paths(ep):
            # `url_for('device_v2.' ~ op)`: every endpoint the prefix can complete to.
            if ep.endswith("."):
                return [r for e, rs in rules.items() if e.startswith(ep) for r in rs]
            return rules.get(ep, [])
        bad = sorted(f"{ep} ({named[ep]}: {paths(ep)})" for ep in named
                     if not paths(ep) or (not all(r.startswith("/v2/") for r in paths(ep))
                                          and ep not in PAGE_ROUTES_OUTSIDE_V2
                                          and not is_network_free(ep)))
        assert not bad, f"requests to routes that cannot name the page's network: {bad}"
        assert all(len(why) >= 20 for why in NETWORK_FREE.values()), "a declaration without why"

    def test_the_installation_s_settings_the_manual_and_the_update_are_network_free(self):
        """Every route under the installation's settings, the manual and the Update is about
        no one network, so each is declared (`NETWORK_FREE`), whatever its endpoint is named:
        the installation's are install_*, diag_*, platforms_* and records_*, and the one
        declaration ``settings_v2.installation*`` had covered the page alone. And no route
        elsewhere in Settings is swept in by those names."""
        import app as A
        from routes.page_network import is_network_free

        prefixes = ("/v2/settings/installation", "/v2/help/", "/v2/update")
        under, wrong = 0, []
        for r in A.app.url_map.iter_rules():
            if r.rule.startswith(prefixes):
                under += 1
                if not is_network_free(r.endpoint):
                    wrong.append(f"{r.endpoint} {r.rule}: not declared")
            elif r.rule.startswith("/v2/settings/network/") and is_network_free(r.endpoint):
                wrong.append(f"{r.endpoint} {r.rule}: a network's settings declared free")
        assert under >= 30, under
        assert not wrong, wrong

    def test_every_request_a_script_makes_is_declared(self):
        """Every request call in the scripts v2 pages load, each declared with how it carries
        the page's network: from an address the page drew (written in as it left), or why it
        needs none. A new call is refused until declared."""
        import pathlib

        from tests import interface_pages

        loaded = set(interface_pages.scripts(("v2",)))
        root = pathlib.Path(__file__).resolve().parent.parent / "static" / "js"
        call = re.compile(r"\b(fetch|htmx\.ajax|location\.assign|location\.replace|"
                          r"XMLHttpRequest|EventSource|window\.open|\.submit)\s*\(|"
                          r"\b(?:location\.href|\.href)\s*=(?!=)")
        found = set()
        for name in sorted(loaded):
            path = root / pathlib.Path(name).name
            for line in path.read_text(encoding="utf-8").splitlines():
                if call.search(line) and not line.lstrip().startswith(("//", "*", "/*")):
                    found.add((path.name, line.strip()))
        assert len(found) >= 10, sorted(found)
        undeclared = sorted(f for f in found if not any(
            f[0] == js and snippet in f[1] for (js, snippet) in SCRIPT_REQUESTS))
        assert not undeclared, f"undeclared request calls in v2 scripts: {undeclared}"
        stale = sorted(k for k in SCRIPT_REQUESTS
                       if not any(f[0] == k[0] and k[1] in f[1] for f in found))
        assert not stale, f"declared calls no longer in the scripts: {stale}"


#: Every request call in the scripts v2 pages load: (script, the call's text) -> how it carries
#: the page's network. "drawn" means its address is an attribute the page drew, which
#: `routes/page_network` wrote the network into.
SCRIPT_REQUESTS = {
    ("nmas_apply.js", "root.fetch(el.getAttribute('data-url')"): "drawn: data-url",
    ("nmas_apply.js", "root.location.assign(o.go)"): (
        "the server's answer: v2.ip_sla_commit names the network in the Apply it returns"),
    ("nmas_credentials.js", "a.href = url;"): "a download of bytes already held: no request",
    ("nmas_credentials.js", "root.fetch(el.getAttribute('data-export-url')"): (
        "drawn: breakglass.export, network-free (its body names the network)"),
    ("nmas_credentials.js", "return root.fetch(el.getAttribute('data-intact-url')"): (
        "drawn: data-intact-url"),
    ("nmas_drag.js", "root.htmx.ajax('GET', url"): "drawn: the element's own hx-get",
    ("nmas_history.js", "root.fetch(el.getAttribute('data-url')"): "drawn: data-url",
    ("nmas_logq.js", "a.href = href;"): (
        "the server's answer: the series' link from data-panel-src, built by its qs, which "
        "names the network"),
    ("nmas_panels.js", "root.fetch(src"): "drawn: data-panel-src",
    ("nmas_topology.js", "else form.submit();"): "drawn: the form's own action",
    ("nmas_update.js", "return root.fetch(url"): "drawn: update.* and health, network-free",
    ("nmas_update.js", "root.fetch(this.$root.getAttribute('data-url')"): (
        "drawn: update.check, network-free"),
    ("nmas_v2.js", "root.htmx.ajax('GET', url"): "drawn: the held region's own hx-get",
    ("nmas_v2.js", "if (target) root.location.assign(target);"): (
        "the jump box: its base path, the typed name, and its form's drawn address's query "
        "(jumpTarget's third argument)"),
    ("nmas_v2.js", "root.fetch(el.getAttribute('data-url')"): "drawn: data-url",
}


def test_the_jump_box_keeps_its_form_s_network():
    """The jump box's call passes its form's drawn query: the declaration above, checked."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parent.parent / "static" / "js" / "nmas_v2.js") \
        .read_text(encoding="utf-8")
    m = re.search(r"var target = jumpTarget\(([^;]*)\);", src, re.S)
    assert m and "addressQuery(form)" in m.group(1), m and m.group(0)
    assert re.search(r"return name \? base \+ encodeURIComponent\(name\) \+ \(query \|\| ''\)",
                     src), "jumpTarget does not append the query"

