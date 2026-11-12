"""No page load or badge poll waits on Grafana, Loki, Prometheus, NetBox, Kea or a device
(C3166; the operator's rule, 2026-11-12, CLAUDE.md: "every page draws at once from data the
background already holds").

Every GET page route the interface reaches is requested through the real app: the pages a
person navigates to (followed by their links from Needs attention and the device pages, on
tests/test_device_v2.py's lab with tests/interface_pages.py's seed), and every GET those pages
ask for (each `hx-get` and `href` they carry, with its query). Grafana, Loki, Prometheus,
NetBox and Kea are configured (each integration's address set, `IntegrationClient.url`,
`netbox_client.get_netbox_config`), and every HTTP request this process makes is a COUNTER
(`requests.Session.request`, which every integration client, NetBox's included, sends
through), as is the SSH opener (modules/connection.py's `open_ssh`, `read_host_key`,
`open_pinned_transport`), and Needs attention's computation (`attention.run_source`). Each
counted call raises at once, as an unreachable service does, so a page draws its failure and
the walk goes on. Counted per route: a route that calls out is on `NOT_YET_CONVERTED` (the
shrinking list of the routes the operator's plan converts in its slices 2 and 3) or on
`PRESSES` (a person's press, whose preview stays live and binds its hash), each with why, or
the test fails. `NOT_YET_CONVERTED` only shrinks (`FROZEN`, and tests/ratchet_lists.py).

What it cannot see, stated: a call a route makes only with data this lab does not hold (a
NetBox network's device, a Kea subnet), or only on a cache's miss after another route filled
it; a route no page reaches by a literal address. Those routes are on the lists by the
survey's reading of their code (~/Documents/nmas-reports/perf-survey-2026-11-12.md), not by
this measurement.
"""

import contextlib
import pathlib
import re
import tempfile
from html import unescape
from urllib.parse import parse_qsl, urlsplit

import pytest

#: The routes that still wait on a source on a request (the survey of 2026-11-12, C3166), by
#: endpoint, each with what it waits on and the slice that converts it. Only shrinks: a slice
#: removes its own routes; slice 1 removed Needs attention's three (`v2.landing`,
#: `v2.attention_list`, `device_v2.attention_count`); slice 2 removed the Logs tab, the drift
#: row's part and Syslog by device's two (`LOGS_CONVERTED`).
NOT_YET_CONVERTED = {
    # Slice 2 moved the builder's bounds and labels to the loki-labels reader; Ask's answer,
    # in the same routes when the address carries ask=1, still reads Loki on the request.
    "v2.history_ask_logs": "Loki for Ask's answer when the address asks (ask=1): a job, C3204",
    "v2.history_ask_logs_region": "Loki for Ask's answer when the address asks: a job, C3204",
    # Slice 3: the rest.
    "device_v2.device": "Prometheus (drained), git and a render: slice 3, a drained reader",
    "device_v2.drained": "Prometheus (drained): slice 3, a drained reader",
    "device_v2.overview": "git log and intent's render: slice 3, rows kept by their writers",
    "device_v2.netbox": "NetBox (three reads): slice 3, from netbox-lag's value",
    "device_v2.neighbours": "Prometheus (four reads): slice 3, from the adjacencies reader",
    "device_v2.monitoring": "Grafana (variables, folds): slice 3, in grafana-dashboards' value",
    "device_v2.panel": "Grafana (a panel's data): slice 3, a per-panel value while on screen",
    "device_v2.history": "git log and about 50 stores: slice 3, a timeline index",
    "device_v2.history_more": "git log and about 50 stores: slice 3, a timeline index",
    "device_v2.rekey": "the device over SSH (its host key): slice 3, a job",
    "device_v2.diagnose_card": "NetBox's cables: slice 3, a cables reader",
    "device_v2.diagnose_unreachable": "NetBox's cables: slice 3, a cables reader",
    "device_v2.pending_progress": "Kea (the pending stage): slice 3, onboarding-progress",
    "v2.devices": "Prometheus (drained) and git: slice 3, a drained reader",
    "v2.devices_table": "Prometheus (drained) and git: slice 3, a drained reader",
    "v2.monitoring_panel": "Grafana (a panel's data): slice 3, a per-panel value",
    "v2.heartbeat": "Loki and Prometheus per device: slice 3, a job or arrivals",
    "v2.history_page": "git log and about 50 stores: slice 3, a timeline index",
    "v2.history_timeline": "git log and about 50 stores: slice 3, a timeline index",
    "v2.history_timeline_more": "git log and about 50 stores: slice 3, a timeline index",
    "v2.history_remote": "git status: slice 3, into the remote-publication reader",
    "v2.history_query_metric": "Grafana; Loki for a logql: slice 3, a lazy part",
    "v2.history_query_metric_data": "Grafana; Loki for a logql: slice 3, browser-driven data",
    "v2.history_ask_metrics": "Prometheus and Loki's limits: slice 3, a catalogue reader",
    "v2.history_ask_metrics_region": "Prometheus and Loki's limits: slice 3, a reader",
    "console_ztp_v2.offer_view": "NetBox (the console path): slice 3, recorded at Create",
    "oob_onboard_v2.source_view": "NetBox (the planned device): slice 3, a cache or a lazy part",
    # Local but slow (no outside call; the operator's addition 4): each on this list.
    "v2.coverage": "local but slow (monitoring_coverage.fleet): slice 3",
    "v2.coverage_table": "local but slow (monitoring_coverage.fleet): slice 3",
    "device_v2.monitored_by": "local but slow (a device's monitoring coverage): slice 3",
    "v2.profile_apply": "local but slow (the apply's plan): slice 3",
    "v2.profile_apply_preview": "local but slow (the apply preview's render): slice 3",
    "v2.devices_deploy": "local but slow (routes/deploy.py plan_devices): slice 3",
    "device_v2.deploy": "local but slow (routes/deploy.py plan_devices): slice 3",
    "v2.history_reapply": "local but slow (the re-apply's plan): slice 3",
    "templates_v2.check": "local but slow (Approve…'s preview, approve_op.check): slice 3",
}

#: `NOT_YET_CONVERTED` as slice 1 left it: the list may lose a route, never gain one (the
#: operator's condition, 2026-11-12; tests/ratchet_lists.py holds the same across commits).
FROZEN = frozenset({
    "device_v2.logs", "device_v2.drift", "v2.history_query_syslog", "logs_v2.region",
    "v2.history_ask_logs", "v2.history_ask_logs_region", "device_v2.device",
    "device_v2.drained", "device_v2.overview", "device_v2.netbox", "device_v2.neighbours",
    "device_v2.monitoring", "device_v2.panel", "device_v2.history", "device_v2.history_more",
    "device_v2.rekey", "device_v2.diagnose_card", "device_v2.diagnose_unreachable",
    "device_v2.pending_progress", "v2.devices", "v2.devices_table", "v2.monitoring_panel",
    "v2.heartbeat", "v2.history_page", "v2.history_timeline", "v2.history_timeline_more",
    "v2.history_remote", "v2.history_query_metric", "v2.history_query_metric_data",
    "v2.history_ask_metrics", "v2.history_ask_metrics_region", "console_ztp_v2.offer_view",
    "oob_onboard_v2.source_view", "v2.coverage", "v2.coverage_table", "device_v2.monitored_by",
    "v2.profile_apply", "v2.profile_apply_preview", "v2.devices_deploy", "device_v2.deploy",
    "v2.history_reapply", "templates_v2.check"})

#: A person's press, never a page load: a preview a person asks for, busy on its control,
#: binding its hash to what the confirm sends (CLAUDE.md: what is confirmed is what is sent),
#: so it reads its source live, on purpose.
PRESSES = {
    "dhcp_v2.reservation_preview": "Add reservation…'s preview: Kea read live, its hash bound",
    "dhcp_v2.subnet_preview": "Add subnet…'s preview: Kea read live, its hash bound",
    "dhcp_v2.exclusion_preview": "Exclude a range…'s preview: Kea read live, its hash bound",
    "dhcp_v2.lease_preview": "Release a lease…'s preview: Kea read live, its hash bound",
    "device_v2.retire": "Retire…'s preview: NetBox and Kea read live, its hash bound",
}

#: Needs attention's three routes, converted by slice 1: they read the background store.
CONVERTED = ("v2.landing", "v2.attention_list", "device_v2.attention_count")
#: Slice 2's four (C3166): they draw the logs-tail reader's buffer. The walk reaches the Logs tab;
#: the drift row's part and Syslog by device with a device opened are counted by
#: tests/test_logs_buffer.py on a seeded buffer (`TestNoPageAsksLoki`), which this walk's lab
#: does not reach.
LOGS_CONVERTED = ("device_v2.logs", "device_v2.drift", "v2.history_query_syslog",
                  "logs_v2.region")

#: The integrations are configured at their own names under `.invalid` (RFC 6761: nothing
#: resolves it), so a counted call names its service: grafana, loki, prometheus, netbox, kea.
_LINK = re.compile(r'\b(?:href|hx-get)="(/v2/[^"#]*)"')
#: A bound on the requests, about 2.5x the 204 distinct ones measured on 2026-11-12.
MAX_REQUESTS = 510

_CACHE: dict = {}


class Counted(Exception):
    pass


def _install_counters(mp, calls: list) -> None:
    import requests

    from modules import attention, connection
    from modules.integrations import base
    import modules.netbox_client as nbc

    mp.setattr(base.IntegrationClient, "url",
               property(lambda self: f"http://{self.name or 'integration'}.invalid"))
    real_cfg = nbc.get_netbox_config
    mp.setattr(nbc, "get_netbox_config",
               lambda: dict(real_cfg(), url="http://netbox.invalid", token="t"))

    def http(self, method, url, *a, **k):
        host = urlsplit(str(url)).hostname or ""
        name = host[:-len(".invalid")] if host.endswith(".invalid") else f"http {host}"
        calls.append(name)
        raise requests.exceptions.ConnectionError(f"counted: {name} is not answering")
    mp.setattr(requests.Session, "request", http)

    def ssh(*_a, **_k):
        calls.append("ssh")
        raise Counted("counted: the device is not answering")
    for fn in ("open_ssh", "read_host_key", "open_pinned_transport"):
        mp.setattr(connection, fn, ssh)
    real_run = attention.run_source

    def computed(src):
        calls.append("needs attention computed")
        return real_run(src)
    mp.setattr(attention, "run_source", computed)


def _requests_of(html: str) -> list:
    return [unescape(u) for u in _LINK.findall(html)]


def _key(endpoint: str, url: str) -> tuple:
    """One request per endpoint and set of query keys (a filter's values render the same
    route's code)."""
    return endpoint, tuple(sorted({k for k, _v in parse_qsl(urlsplit(url).query)}))


def measure() -> dict:
    """``{"calls": {endpoint: [what it called]}, "requested": {endpoint: [urls]},
    "status": {url: code}}``, once per test process, on its own lab and MonkeyPatch, both
    undone before it returns."""
    if "measured" in _CACHE:
        return _CACHE["measured"]
    from werkzeug.exceptions import MethodNotAllowed, NotFound

    import app as A
    from modules import attention_store
    from modules.integrations import grafana
    from tests import interface_pages
    from tests.test_device_v2 import lab_setup

    real_grafana = grafana.GrafanaIntegration
    mp = pytest.MonkeyPatch()
    calls, by_endpoint, requested, status = [], {}, {}, {}
    try:
        interface_pages.as_a_verified_person(mp)
        mp.setattr(attention_store, "COMPUTE_ON_READ", False)
        with tempfile.TemporaryDirectory(prefix="nmas-page-waits-") as tmp:
            with contextlib.contextmanager(lab_setup)(pathlib.Path(tmp), mp) as lab:
                interface_pages.seed(lab, mp, tmp)
                interface_pages._sdn_connection("Lab", mp)
                # The real Grafana client (the lab's is a fake), configured, so a page that
                # reads Grafana on a request is counted as every other service is.
                mp.setattr(grafana, "GrafanaIntegration", real_grafana)
                _install_counters(mp, calls)
                adapter = A.app.url_map.bind("localhost")
                client = lab["client"]
                todo, seen = list(interface_pages.START), set()
                while todo:
                    url = todo.pop(0)
                    try:
                        endpoint, _args = adapter.match(urlsplit(url).path, method="GET")
                    except (NotFound, MethodNotAllowed):
                        continue
                    key = _key(endpoint, url)
                    if key in seen:
                        continue
                    seen.add(key)
                    assert len(seen) < MAX_REQUESTS, (
                        f"the walk reached {MAX_REQUESTS} requests, its bound (2.5x the 204 "
                        "measured 2026-11-12): a page that links without end, or a bound to "
                        "re-measure")
                    del calls[:]
                    r = client.get(url, headers={"Accept": "text/html"})
                    status[url] = r.status_code
                    by_endpoint.setdefault(endpoint, []).extend(calls)
                    requested.setdefault(endpoint, []).append(url)
                    if r.mimetype == "text/html":
                        todo += _requests_of(r.get_data(as_text=True))
    finally:
        mp.undo()
    _CACHE["measured"] = {"calls": by_endpoint, "requested": requested, "status": status}
    return _CACHE["measured"]


@pytest.fixture(scope="module")
def measured():
    return measure()


def _calling(m) -> dict:
    return {e: sorted(set(c)) for e, c in m["calls"].items() if c}


class TestTheWalk:
    def test_the_walk_reaches_the_population(self, measured):
        """Measured 2026-11-12: 204 distinct requests to 140 GET endpoints; the floors are
        about 80% of each."""
        assert sum(len(v) for v in measured["requested"].values()) >= 160
        assert len(measured["requested"]) >= 110
        for e in CONVERTED:
            assert e in measured["requested"], f"{e} was not requested"

    def test_the_counters_count_each_kind_of_call_out(self):
        """The control: each counter, installed as the walk installs it, counts a planted
        call of its kind (a Loki read through its client, NetBox's session, the SSH opener,
        Needs attention's computation)."""
        from modules import attention, connection
        from modules.integrations.loki import LokiIntegration
        import modules.netbox_client as nbc
        mp, calls = pytest.MonkeyPatch(), []
        try:
            _install_counters(mp, calls)
            assert LokiIntegration()._get("loki/api/v1/labels")["ok"] is False
            with pytest.raises(Exception):
                nbc._session_from_config(nbc.get_netbox_config()).get(
                    "http://netbox.invalid/api/status/")
            with pytest.raises(Counted):
                connection.read_host_key("2001:db8::7")
            attention.run_source(lambda: attention.source_result(
                "x", "X", read_at=0, took_ms=0, checked="a planted source"))
        finally:
            mp.undo()
        assert calls == ["loki", "netbox", "ssh", "needs attention computed"]


class TestNoPageWaits:
    def test_needs_attention_and_its_badge_call_nothing(self, measured):
        """Slice 1: the three routes read the background store, never a source."""
        for e in CONVERTED:
            assert not measured["calls"].get(e), (e, measured["calls"].get(e))

    def test_the_logs_tab_calls_nothing(self, measured):
        """Slice 2: the device's Logs tab, reached by the walk, draws the logs-tail reader's
        buffer; it called Loki four times a load before (three queries and the job's)."""
        assert "device_v2.logs" in measured["requested"], "the walk did not reach the Logs tab"
        assert not measured["calls"].get("device_v2.logs"), measured["calls"]["device_v2.logs"]

    def test_no_route_calls_out_unaccounted(self, measured):
        unaccounted = {e: c for e, c in _calling(measured).items()
                       if e not in NOT_YET_CONVERTED and e not in PRESSES}
        assert not unaccounted, (
            "a GET route waits on a source on a request, and is on neither NOT_YET_CONVERTED "
            "nor PRESSES (C3166: read what the background holds, or name it a press with "
            f"why): {unaccounted}")

    def test_the_list_only_shrinks(self):
        assert set(NOT_YET_CONVERTED) <= FROZEN, sorted(set(NOT_YET_CONVERTED) - FROZEN)

    def test_every_entry_says_why_and_is_a_route(self):
        import app as A
        gets = {r.endpoint for r in A.app.url_map.iter_rules() if "GET" in (r.methods or ())}
        for table in (NOT_YET_CONVERTED, PRESSES):
            for e, why in table.items():
                assert len(why.split()) >= 4, e
                assert e in gets, f"{e} is not a GET route (a removed one leaves its list)"
        assert not set(NOT_YET_CONVERTED) & set(PRESSES)
        assert not set(CONVERTED) & (set(NOT_YET_CONVERTED) | set(PRESSES))
        assert not set(LOGS_CONVERTED) & (set(NOT_YET_CONVERTED) | set(PRESSES))
        assert set(LOGS_CONVERTED) <= gets
