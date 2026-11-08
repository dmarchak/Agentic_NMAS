"""The controller driver's per-app `/health` read and the post-check's judgment of it (C2677;
the SDN platform design revision 6, section 8's ``app_health`` and section 10's post-check),
through the fake HTTP layer (tests/sdn_fakes.py), no network.

Cases, each planted:
- **the read:** `app_health(prefix)` sends exactly one GET of ``<prefix>/health`` on the
  controller connection's base URL (IPv4 and a bracketed IPv6 literal alike), no body; a prefix
  not of the manifest's shape is refused with nothing sent, so the call is never a way to GET
  anything else;
- **its three answers:** a 200 JSON object with a true or false ``ok`` is the app's parsed
  answer; no answer within the bound, a refused connection and a 404 (no such route: the app is
  not loaded) are "no answer", each naming why; a body that is not JSON, not an object, an
  ``ok`` that is not true or false, a 500 and a refused credential are "unreadable", naming
  what failed;
- **the bound:** per request, the placeholder `APP_HEALTH_TIMEOUT` (5 s, said as a
  placeholder), or the connection's own timeout when that is shorter; never the connection's
  longer one; each read's time is kept;
- **masked on the way in:** a credential value or a URL's user part an app echoes in its answer
  is masked before it leaves the driver;
- **the judgment:** a healthy answer passes a poll; an answer whose ``ok`` is false is unhealthy,
  naming the app's problems; no answer and unreadable never pass and are named; the result keeps
  each app's state and read time (the receipt measures the bound);
- **the wiring:** `Wired.observe` reads each named app's /health through the connection's
  driver, GETs only; a network with no connection makes each app unreadable, naming it; the
  preview reads the chosen set's apps under their manifests' prefixes, and the confirm's
  post-check reads the set last sent, the rollback target's prefixes after a rollback.
"""

import json

import pytest
import requests

from modules.apps import deploy_op, post_check, sources as S
from modules.apps.manifest import parse_manifest
from modules.sdn import connections as C
from modules.sdn.drivers import base
from modules.sdn.drivers.base import Connection
from modules.sdn.drivers.ryu import RyuDriver
from tests.sdn_fakes import Clock, Response, Session
from tests.test_controller_deploy import ALL_BACK, EXPECTED, SWITCH_2_DOWN
from tests.test_controller_deploy_op import CTL, NET, FakeSources
from tests.test_controller_deploy_op import _receipts_here  # noqa: F401 - autouse: the
#   receipts and the planned-restart record in each test's own folder (C571, C1864)
from tests.test_controller_deploy_op import run as run_confirm

PREFIX = "/fabric_forwarding"
SECRET = "planted-health-secret-51c2e"
HEALTHY = {"ok": True, "app": "fabric_forwarding", "version": "0.1.0", "configured": True,
           "switches": 5, "served": 5, "problems": []}
WAITING = dict(HEALTHY, ok=False, configured=False, served=0,
               problems=["waiting for its config (PUT /fabric_forwarding/config): no switch "
                         "is served"])


def ryu(session, url="http://192.0.2.10:8080", timeout=5.0, clock=None, credentials=None):
    return RyuDriver(Connection(url, timeout=timeout, credentials=credentials),
                     session=session, clock=clock or Clock(), sleep=lambda s: None)


def answer(body, status=200, content_type="application/json"):
    text = body if isinstance(body, str) else json.dumps(body)
    return Response(status, text, content_type)


# ── the read ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url, sent_to", [
    ("http://192.0.2.10:8080", "http://192.0.2.10:8080/fabric_forwarding/health"),
    ("http://[2001:db8::10]:8080", "http://[2001:db8::10]:8080/fabric_forwarding/health"),
])
def test_the_read_is_one_get_of_the_apps_health_path_ipv4_and_ipv6(url, sent_to):
    session = Session(answer(HEALTHY))
    got = ryu(session, url=url).app_health(PREFIX)
    assert got["ok"] is True and got["state"] == base.HEALTH_ANSWERED and got["error"] == ""
    assert got["answer"] == HEALTHY and got["path"] == "/fabric_forwarding/health"
    [sent] = session.sent
    assert sent["method"] == "GET" and sent["url"] == sent_to and sent["data"] is None


@pytest.mark.parametrize("prefix", ["/../stats", "fabric_forwarding", "/a/b", "/x?y=1",
                                    "/Fabric", "", None, "/stats/flowentry/add"])
def test_a_prefix_not_of_the_manifests_shape_is_refused_and_nothing_is_sent(prefix):
    session = Session()
    got = ryu(session).app_health(prefix)
    assert got["ok"] is False and session.sent == []
    assert "an app's REST prefix is one segment" in got["error"]
    assert "so its /health was not read" in got["error"]


# ── its three answers ────────────────────────────────────────────────────────────────────────

def test_an_answer_whose_ok_is_false_is_answered_with_the_apps_problems():
    got = ryu(Session(answer(WAITING))).app_health(PREFIX)
    assert got["ok"] is True and got["state"] == base.HEALTH_ANSWERED
    entry = post_check.health_entry(got)
    assert entry["ok"] is False and entry["state"] == post_check.ANSWERED
    assert entry["error"] == WAITING["problems"][0]


@pytest.mark.parametrize("given, said", [
    ([requests.exceptions.Timeout("read timed out")],
     "no answer within 5 s from /fabric_forwarding/health (the /health read's bound: 5 s (a "
     "placeholder, not measured"),
    ([requests.exceptions.ConnectionError("refused")] * 3,
     "could not connect to http://192.0.2.10:8080, asking /fabric_forwarding/health"),
    ([answer("<html>404 Not Found</html>", 404, "text/html")],
     "HTTP 404 from /fabric_forwarding/health: the controller serves no "
     "/fabric_forwarding/health, so the app is not loaded"),
])
def test_no_answer_is_said_naming_why(given, said):
    got = ryu(Session(*given)).app_health(PREFIX)
    assert got["ok"] is False and got["state"] == base.HEALTH_NO_ANSWER
    assert said in got["error"]
    entry = post_check.health_entry(got)
    assert entry["ok"] is False and entry["state"] == post_check.NO_ANSWER


@pytest.mark.parametrize("given, said", [
    (answer("ok", 200, "text/plain"),
     "HTTP 200 from /fabric_forwarding/health with a body that is not JSON"),
    (answer([True]), "/fabric_forwarding/health answered a list, not an object"),
    (answer({"ok": "yes"}), "/fabric_forwarding/health's answer has no true or false ok (its "
                            "ok is 'yes')"),
    (answer({"status": "up"}), "its ok is 'None'"),
    (answer("Traceback (most recent call last):\nKeyError: 'switches'", 500, "text/plain"),
     "HTTP 500 from /fabric_forwarding/health (KeyError: 'switches')"),
    (answer("", 401), "HTTP 401: the controller refused the tool's credential from "
                      "/fabric_forwarding/health"),
    (answer("", 302), "/fabric_forwarding/health: HTTP 302: the controller answered a redirect"),
])
def test_an_answer_that_is_not_a_health_answer_is_unreadable_naming_what_failed(given, said):
    got = ryu(Session(given)).app_health(PREFIX)
    assert got["ok"] is False and got["state"] == base.HEALTH_UNREADABLE
    assert said in got["error"], got["error"]
    entry = post_check.health_entry(got)
    assert entry["ok"] is False and entry["state"] == post_check.UNREADABLE


# ── the bound ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("own, bound", [(30.0, 5.0), (120.0, 5.0), (5.0, 5.0), (2.0, 2.0)])
def test_each_request_is_bounded_by_the_placeholder_or_a_shorter_connection_timeout(own, bound):
    session = Session(answer(HEALTHY))
    got = ryu(session, timeout=own).app_health(PREFIX)
    [sent] = session.sent
    assert sent["timeout"] == (bound, bound)
    assert got["bound"]["seconds"] == bound and got["bound"]["measured"] is False
    if bound == base.APP_HEALTH_TIMEOUT["seconds"]:
        assert "a placeholder, not measured" in got["bound"]["words"]
    else:
        assert got["bound"]["words"] == "2 s, the controller connection's own timeout"


def test_a_shorter_deadline_never_lengthens_the_connections():
    """The one HTTP channel's *timeout* only shortens: a caller cannot outwait the connection."""
    session = Session(answer([1]), answer([1]))
    drv = ryu(session, timeout=5.0)
    drv._http("GET", "/stats/switches", timeout=60.0)  # noqa: SLF001 - the channel itself
    drv._http("GET", "/stats/switches", timeout=1.5)  # noqa: SLF001
    assert [s["timeout"] for s in session.sent] == [(5.0, 5.0), (1.5, 1.5)]


def test_each_reads_time_is_kept():
    clock = Clock(step=0.25)
    got = ryu(Session(answer(HEALTHY)), clock=clock).app_health(PREFIX)
    assert got["elapsed_s"] > 0
    assert post_check.health_entry(got)["elapsed_s"] == got["elapsed_s"]


# ── masked on the way in ─────────────────────────────────────────────────────────────────────

def test_a_secret_an_app_echoes_is_masked_before_it_leaves_the_driver():
    body = dict(WAITING, problems=[f"login as mercury:{SECRET} refused",
                                   "verdict service http://user:hunter2pass@192.0.2.9/ down"])
    got = ryu(Session(answer(body)),
              credentials=lambda: {"username": "mercury", "password": SECRET}).app_health(PREFIX)
    text = json.dumps(got)
    assert SECRET not in text and "hunter2pass" not in text
    entry = post_check.health_entry(got)
    assert SECRET not in entry["error"] and "hunter2pass" not in entry["error"]
    assert "<redacted>" in entry["error"]


# ── the judgment ─────────────────────────────────────────────────────────────────────────────

def observed_with(entry):
    return dict(ALL_BACK, health={"of_versions": entry})


def test_a_healthy_answer_passes_and_its_state_and_time_are_kept():
    entry = post_check.health_entry(ryu(Session(answer(HEALTHY))).app_health("/of_versions"))
    got = post_check.evaluate(EXPECTED, observed_with(entry))
    assert got["ok"] is True and got["unreadable"] == [] and got["unhealthy"] == []
    assert got["health"]["of_versions"]["state"] == "answered"
    assert got["health"]["of_versions"]["ok"] is True
    assert got["health"]["of_versions"]["elapsed_s"] == entry["elapsed_s"]


def test_an_unhealthy_answer_fails_the_poll_naming_the_apps_problems():
    entry = post_check.health_entry(ryu(Session(answer(WAITING))).app_health("/of_versions"))
    got = post_check.evaluate(EXPECTED, observed_with(entry))
    assert got["ok"] is False and got["unreadable"] == []
    assert got["unhealthy"] == [f"of_versions ({WAITING['problems'][0]})"]
    assert "apps not healthy: of_versions (waiting for its config" in post_check.miss_words(got)


@pytest.mark.parametrize("given, state", [
    (answer("", 404, "text/html"), "no answer"),
    (answer("not json", 200, "text/plain"), "unreadable"),
])
def test_no_answer_and_unreadable_never_pass_and_are_named(given, state):
    entry = post_check.health_entry(ryu(Session(given)).app_health("/of_versions"))
    got = post_check.evaluate(EXPECTED, observed_with(entry))
    assert got["ok"] is False and got["unhealthy"] == []
    [said] = got["unreadable"]
    assert said.startswith(f"of_versions's /health ({state}: ")
    assert got["health"]["of_versions"]["state"] == state


def test_an_entry_not_of_the_drivers_shape_is_unreadable_never_healthy():
    entry = post_check.health_entry({"ok": True})
    assert entry["ok"] is False and entry["state"] == post_check.UNREADABLE
    assert post_check.evaluate(EXPECTED, observed_with(entry))["ok"] is False


def test_the_post_check_waits_through_no_answer_until_the_app_answers_healthy():
    clock = Clock(start=0.0)
    drv = ryu(Session(answer("", 404, "text/html"), answer(WAITING), answer(HEALTHY)))

    def read():
        return observed_with(post_check.health_entry(drv.app_health("/of_versions")))
    got = post_check.wait(read, EXPECTED, clock=clock, sleep=lambda s: setattr(
        clock, "now", clock.now + s))
    assert got["ok"] is True and got["polls"] == 3


def test_a_health_with_no_answer_at_the_bound_is_a_miss_naming_it():
    clock = Clock(start=0.0)
    drv = ryu(Session(*[answer("", 404, "text/html")] * 200))

    def read():
        return observed_with(post_check.health_entry(drv.app_health("/of_versions")))
    got = post_check.wait(read, EXPECTED, clock=clock, sleep=lambda s: setattr(
        clock, "now", clock.now + s))
    assert got["ok"] is False
    assert "unreadable: of_versions's /health (no answer: HTTP 404 from /of_versions/health" in \
        got["words"]


# ── the wiring ───────────────────────────────────────────────────────────────────────────────

class Driver:
    """The connection's driver: a real RyuDriver on a fake session, so every request is kept."""

    def __init__(self, *answers):
        self.session = Session(*answers)
        self.drv = ryu(self.session)


def wired_with(monkeypatch, driver):
    monkeypatch.setattr(C, "connections", lambda network: {"connections": [{"name": "ryu"}]})
    monkeypatch.setattr(C, "driver_for", lambda network, name: {"ok": True, "error": "",
                                                                "driver": driver})


def test_wired_observe_reads_each_named_apps_health_with_gets_only(monkeypatch):
    held = Driver(answer([1, 2]), answer([]), answer(HEALTHY), answer(WAITING))
    wired_with(monkeypatch, held.drv)
    got = S.Wired().observe(NET, {"name": CTL, "connection": ""},
                            apps={"fabric_forwarding": PREFIX, "of_versions": "/of_versions"})
    assert got["health"]["fabric_forwarding"]["ok"] is True
    assert got["health"]["of_versions"]["ok"] is False
    assert got["health"]["of_versions"]["state"] == "answered"
    assert [s["method"] for s in held.session.sent] == ["GET"] * 4
    assert [s["url"].split(":8080", 1)[1] for s in held.session.sent[2:]] == [
        "/fabric_forwarding/health", "/of_versions/health"]


def test_wired_observe_with_no_apps_reads_no_health(monkeypatch):
    held = Driver(answer([1]), answer([]))
    wired_with(monkeypatch, held.drv)
    got = S.Wired().observe(NET, {"name": CTL, "connection": ""})
    assert got["health"] == {} and len(held.session.sent) == 2


def test_with_no_connection_each_app_is_unreadable_naming_it(monkeypatch):
    monkeypatch.setattr(C, "connections", lambda network: {"connections": []})
    got = S.Wired().observe(NET, {"name": CTL, "connection": ""},
                            apps={"fabric_forwarding": PREFIX})
    entry = got["health"]["fabric_forwarding"]
    assert entry["ok"] is False and entry["state"] == "unreadable"
    assert entry["error"].startswith("the controller connection: ")


def a_manifest(name, version, prefix):
    return parse_manifest(
        f"name: {name}\nversion: {version}\ncontrollers:\n  ryu: \">=4.34\"\n"
        "openflow_versions: [\"1.0\", \"1.3\"]\nrequires: []\nconfig_schema: {type: object}\n"
        f"rest:\n  prefix: {prefix}\n  endpoints:\n    - path: /health\n      methods: [GET]\n")


class Recording(FakeSources):
    """FakeSources that keep the apps each controller read was asked for."""

    def __init__(self, tmp_path, **kw):
        super().__init__(tmp_path, **kw)
        self.asked = []
        versions = self.reg["apps"][0]["versions"]
        # 1.1.0 serves its REST under another prefix than 1.0.0, so a read says which it read.
        versions[1]["manifest"] = a_manifest("of_versions", "1.1.0", "/of_versions_two")

    def observe(self, network, controller, apps=None):
        self.asked.append(dict(apps or {}))
        return super().observe(network, controller, apps=apps)


def test_the_preview_reads_the_chosen_sets_health_under_its_manifests_prefix(tmp_path):
    src = Recording(tmp_path)
    src.reads = [dict(ALL_BACK, health={"of_versions": post_check.health_entry(
        ryu(Session(answer(WAITING))).app_health("/of_versions_two"))})]
    got = deploy_op.preview(NET, CTL, {"of_versions": "1.1.0"}, src=src)
    assert got["ok"], got.get("refusals")
    assert src.asked == [{"of_versions": "/of_versions_two"}]
    assert got["already"]["unhealthy"] == [f"of_versions ({WAITING['problems'][0]})"]
    assert "expecting of_versions's /health to recover" in deploy_op.confirm_words(got)


def test_the_confirms_post_check_reads_the_set_last_sent_and_the_rollbacks_after_it(tmp_path):
    src = Recording(tmp_path)
    healthy = dict(ALL_BACK, health={"of_versions": {"ok": True}})
    first = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    src.reads = [healthy]
    assert run_confirm(src, {"of_versions": "1.0.0"}, first["plan_sha256"])["outcome"] == \
        "deployed"
    assert src.asked[1:] == [{"of_versions": "/of_versions"}]
    shown = deploy_op.preview(NET, CTL, {"of_versions": "1.1.0"}, src=src)
    misses = [SWITCH_2_DOWN] * (int(post_check.bound()["seconds"] // post_check.POLL_S) + 1)
    src.asked, src.reads = [], misses + [healthy]
    got = run_confirm(src, {"of_versions": "1.1.0"}, shown["plan_sha256"])
    assert got["outcome"] == "rolled back", got
    assert src.asked[:len(misses)] == [{"of_versions": "/of_versions_two"}] * len(misses)
    assert src.asked[len(misses):] == [{"of_versions": "/of_versions"}]
