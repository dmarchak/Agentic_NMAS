"""The topology visualization comes from the topology service, as an IMAGE.

Objective 1.2a(i) asks for the visualization from the previous labs -- the
NetworkX-based `rcn-topology` service. The Topology tab had been
rediscovering topology itself over CDP/LLDP: a second implementation of
something already built, already running and already configured under
Settings.

Two properties carry the weight here.

**Server-side.** The browser arrives through the Cloudflare tunnel and the
service listens on the LAN only, so a browser-side request works on the
console at the lab host and shows a broken image to every remote viewer.

**Never inlined.** An SVG is a document, not a picture: it can carry
`<script>`, `<foreignObject>` and external references, and injecting one into
the page runs it with the page's origin and session. Referenced through
`<img>`, the browser refuses to execute any of it.

That second one is not about distrusting our own service. "We trust the
source" is a property of today's deployment; `<img>` is a property of the
browser. Only one of them survives a change nobody remembers making.
"""

import os
import re

import pytest

PARTIAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "templates", "partials", "topology_service.html")

SVG_BODY = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><g/></svg>'


def _partial():
    with open(PARTIAL, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def client():
    import app as nmas

    return nmas.app.test_client()


class _Response:
    def __init__(self, body=SVG_BODY, status=200, content_type="image/svg+xml"):
        self.content = body
        self.status_code = status
        self.headers = {"Content-Type": content_type}


@pytest.fixture
def service(monkeypatch):
    """A configured topology service whose response the test controls."""
    state = {"response": _Response(), "raise": None, "asked": []}

    class FakeSession:
        def get(self, url, timeout=None):
            state["asked"].append(url)
            if state["raise"]:
                raise state["raise"]
            return state["response"]

    class FakeClient:
        url = "http://topology.invalid:8088"

        def is_configured(self):
            return state.get("configured", True)

        def session(self):
            return FakeSession()

    monkeypatch.setattr("modules.integrations.get_integration",
                        lambda name: FakeClient() if name == "topology_service" else None)
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None:
                        "svg" if key == "topology_service_type" else default)
    return state


class TestTheRouteReturnsAnImage:
    def test_the_content_type_is_svg(self, client, service):
        r = client.get("/topology/service/svg")
        assert r.status_code == 200
        assert r.mimetype == "image/svg+xml"

    def test_the_body_is_the_services_own_bytes(self, client, service):
        assert client.get("/topology/service/svg").data == SVG_BODY

    def test_it_asks_the_service_for_topology_svg(self, client, service):
        client.get("/topology/service/svg")
        assert service["asked"] == ["http://topology.invalid:8088/topology.svg"]

    def test_it_is_not_cached(self, client, service):
        """Caching here would make the Refresh button a lie."""
        r = client.get("/topology/service/svg")
        assert "no-store" in r.headers.get("Cache-Control", "")

    def test_it_carries_defence_in_depth_headers(self, client, service):
        """Behind the <img>, not instead of it: if this were ever rendered
        as a document, nothing in it should run or reach out."""
        r = client.get("/topology/service/svg")
        assert "default-src 'none'" in r.headers.get("Content-Security-Policy", "")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"


class TestTheUrlIsBuiltFromWhatTheOperatorSet:
    def test_a_base_url_gets_the_path_appended(self):
        from routes.topology_view import svg_url

        assert svg_url("http://host:8088") == "http://host:8088/topology.svg"
        assert svg_url("http://host:8088/") == "http://host:8088/topology.svg"

    def test_a_url_already_ending_in_svg_is_taken_as_given(self):
        """The operator pointed at an exact document; appending a path would
        break it."""
        from routes.topology_view import svg_url

        assert svg_url("http://host/graphs/lab.svg") == "http://host/graphs/lab.svg"

    def test_the_extension_check_is_case_insensitive(self):
        from routes.topology_view import svg_url

        assert svg_url("http://host/a.SVG") == "http://host/a.SVG"


class TestAFailureHasAReason:
    """A blank area cannot be told from a topology with nothing in it."""

    def test_not_configured_says_where_to_set_it(self, client, service):
        service["configured"] = False
        r = client.get("/topology/service/svg")
        assert r.status_code == 503
        assert "Settings" in r.get_json()["error"]

    def test_unreachable_says_so(self, client, service):
        service["raise"] = OSError("connection refused")
        r = client.get("/topology/service/svg")
        assert r.status_code == 502
        assert "Could not reach" in r.get_json()["error"]

    def test_an_http_error_is_reported_with_its_status(self, client, service):
        service["response"] = _Response(status=500)
        r = client.get("/topology/service/svg")
        assert r.status_code == 502
        assert "500" in r.get_json()["error"]

    def test_a_non_svg_response_is_refused_not_passed_through(self, client, service):
        """Handing HTML to an <img> produces a broken-image icon with no
        reason attached."""
        service["response"] = _Response(body=b"<html>login</html>",
                                        content_type="text/html")
        r = client.get("/topology/service/svg")
        assert r.status_code == 502
        assert "not an SVG" in r.get_json()["error"]

    def test_svg_bytes_are_accepted_even_with_a_vague_content_type(self, client,
                                                                   service):
        """Some servers send application/octet-stream. Refusing a real SVG
        over its Content-Type would be the check being wrong."""
        service["response"] = _Response(content_type="application/octet-stream")
        assert client.get("/topology/service/svg").status_code == 200


class TestThePageNeverInjectsSvgMarkup:
    """The property that makes the <img> choice meaningful."""

    def test_the_image_is_an_img_tag(self):
        assert re.search(r'<img[^>]+id="topoSvcImage"', _partial())

    def test_the_partial_never_writes_svg_into_the_dom(self):
        source = _partial()
        scripts = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", source, re.S))
        for forbidden in ("innerHTML", "insertAdjacentHTML", "outerHTML",
                          "document.write", "createElementNS"):
            assert forbidden not in scripts, (
                f"{forbidden} could put SVG markup in the page, where its "
                f"scripts would run with this page's origin")

    def test_text_content_is_used_for_messages(self):
        """The error path writes a message; it must set text, not markup."""
        assert "textContent" in _partial()

    def test_there_is_no_iframe_or_object_embed(self):
        source = _partial()
        for tag in ("<iframe", "<object", "<embed"):
            assert tag not in source, tag


class TestTheControls:
    def test_refresh_busts_the_cache(self):
        """Without a changing query the browser serves the previous render
        and Refresh silently does nothing."""
        source = _partial()
        assert re.search(r"image\.src\s*=\s*'/topology/service/svg\?t='\s*\+\s*Date\.now\(\)",
                         source)

    def test_the_interval_selector_offers_the_four_choices(self):
        source = _partial()
        for value in ('value="0"', 'value="30"', 'value="60"', 'value="300"'):
            assert value in source, value

    def test_changing_the_interval_clears_the_previous_timer(self):
        """Otherwise each change adds another timer and the refresh rate
        silently multiplies."""
        source = _partial()
        body = source[source.index("function topoSvcSetInterval"):]
        body = body[:body.index("function topoSvcInit")]
        assert "clearInterval" in body
        assert body.index("clearInterval") < body.index("setInterval(")

    def test_it_reports_when_it_last_refreshed(self):
        assert "topoSvcStamp" in _partial()
        assert "refreshed " in _partial()


class TestThePanelIsServerRenderedAndSelfStarting:
    def test_the_placeholder_is_in_the_markup(self):
        markup = re.sub(r"<script[^>]*>.*?</script>", "", _partial(), flags=re.S)
        assert 'id="topoSvcPlaceholder"' in markup
        assert "did not load" in markup

    def test_the_placeholder_names_where_to_look(self):
        assert "Settings" in _partial()

    def test_it_registers_its_own_initialiser(self):
        assert re.search(r"addEventListener\(\s*'DOMContentLoaded'\s*,\s*topoSvcInit\s*\)",
                         _partial())

    def test_a_missing_element_is_reported_not_swallowed(self):
        source = _partial()
        assert source.count("console.error") >= 2

    def test_it_is_its_own_script_block(self):
        assert _partial().count("<script>") == 1


class TestTheTabShowsTheServiceFirst:
    def test_the_partial_is_included_and_the_legacy_view_collapsed(self):
        import app as nmas

        html = nmas.app.test_client().get("/").get_data(as_text=True)
        block = html[html.index('id="topologyPane"'):html.index("end Topology tab pane")]
        assert "topoSvcImage" in block
        assert 'id="legacyDiscovery"' in block
        assert block.index("topoSvcImage") < block.index('id="legacyDiscovery"')

    def test_the_legacy_views_still_exist(self):
        """Collapse only. No deletions, no behaviour change."""
        import app as nmas

        html = nmas.app.test_client().get("/").get_data(as_text=True)
        for view in ("topoCdpView", "topoOspfView", "topoBgpView", "topoTunnelView"):
            assert view in html, view
