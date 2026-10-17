"""B2 (W2, 2026-10-16): every recorded operation names its actor, whatever its route's gate.

The operator's NetBox import preview, Verify the remote and an earlier preview recorded
"unauthenticated" though the operator was signed in; confirms and the write probe named them,
and the first commit of a network created on v2 read "nobody recorded". The cause was one
line: `route_gates.enforce` returns before `identity.require` for a ``not_device`` gate, so
`flask.g.nmas_identity` is never set, and `identity.request_actor()`, `actor_verification()`
and `verified_identity()` read only that. A gate of N means no person is REQUIRED, never that
none is NAMED. They now read `identity.request_identity()`: the gate's verification when it
ran, else the same `identify()` made once for the request (what `viewer()` already drew).

What is held:

- over the whole route table, every endpoint and method, as a verified person: the recorded
  actor is that person and reads ``Actor-Verified: access``, and a job it starts carries them;
- as an unverified request: a gated route still refuses, and every other one records
  `identity.UNVERIFIED` ("unverified"), ``Actor-Verified: none``, carrying nobody into a job;
- through the real app: the NetBox import preview, Verify the remote and a network's creation
  each record the verified person, or "unverified", and the creation is refused unverified;
- a network's first commit names who made it (``Actor:``, ``Actor-Verified:``,
  ``Source: init``), and one made with nobody's request behind it names Mercury and the job.
"""

import json
import os
import re
import subprocess

import pytest

from modules import identity, route_gates
from tests.conftest import TEST_PERSON
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)


def _app():
    import app as A
    return A.app


UNVERIFIED_REQUEST = identity.Identity(outcome="no_header",
                                       reason="the request carried no assertion")

#: The routes the survey of 2026-10-16 found recording `request_actor()` with an ungated
#: (``not_device``) gate, each of which recorded "unauthenticated" for a verified person.
#: Today's three NetBox previews (`netbox_safety.preview_*`) left at 7.8 (2026-10-17).
UNGATED_RECORDERS = ("netbox_v2.preview", "remote.verify",
                     "adopt_v2.preview", "onboard_v2.abandon_preview")


def _every_endpoint_and_method():
    out = []
    for rule in _app().url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            out.append((rule, method))
    return out


def _inside(rule, method):
    """A request to *rule* by *method*, with the gate run as `before_request` runs it.
    ``(refusal_or_None, ctx)``: the caller reads the identity inside the context."""
    ctx = _app().test_request_context("/", method=method)
    ctx.push()
    ctx.request.url_rule = rule
    return route_gates.enforce(), ctx


class TestTheRouteTable:
    def test_the_population_is_the_whole_table_with_its_ungated_recorders(self):
        pairs = _every_endpoint_and_method()
        endpoints = {r.endpoint for r, _m in pairs}
        # 359 on 2026-10-16; 310 on 2026-10-17 after 7.8's removals (P7-20 to P7-24), fewer
        # after P7-25's eleven; a floor, not a count, kept about 10% under the measurement.
        assert len(pairs) >= 270, len(pairs)
        assert set(UNGATED_RECORDERS) <= endpoints
        assert "settings_v2.network_create" in endpoints
        assert {route_gates.GATES[e].kind for e in UNGATED_RECORDERS} == {route_gates.NOT_DEVICE}

    def test_as_a_verified_person_every_route_records_that_person(self):
        wrong = []
        for rule, method in _every_endpoint_and_method():
            refusal, ctx = _inside(rule, method)
            try:
                carried = identity.verified_identity()
                got = (refusal is None, identity.request_actor(),
                       identity.actor_verification(TEST_PERSON),
                       carried.actor if carried else None)
            finally:
                ctx.pop()
            if got != (True, TEST_PERSON, "access", TEST_PERSON):
                wrong.append((rule.endpoint, method, got))
        assert not wrong, f"{len(wrong)} route(s) do not name the verified person: {wrong[:12]}"

    def test_as_a_verified_service_an_ungated_route_records_the_service(self, monkeypatch):
        service = identity.Identity(actor="service:abc.access", kind="service",
                                    service_id="abc.access", verified=True, outcome="ok",
                                    peer_trusted=True, header_present=True)
        monkeypatch.setattr(identity, "identify", lambda _r: service)
        rules = {r.endpoint: r for r in _app().url_map.iter_rules()}
        for endpoint in UNGATED_RECORDERS:
            _refusal, ctx = _inside(rules[endpoint], "POST")
            try:
                assert identity.request_actor() == "service:abc.access", endpoint
            finally:
                ctx.pop()

    def test_as_an_unverified_request_gated_routes_refuse_and_the_rest_record_unverified(
            self, monkeypatch):
        monkeypatch.setattr(identity, "identify", lambda _r: UNVERIFIED_REQUEST)
        wrong, refused = [], 0
        for rule, method in _every_endpoint_and_method():
            gate = route_gates.GATES.get(rule.endpoint)
            gated = (method not in route_gates.SAFE_METHODS
                     and (gate is None or gate.kind != route_gates.NOT_DEVICE))
            refusal, ctx = _inside(rule, method)
            try:
                got = (refusal is not None, identity.request_actor(),
                       identity.actor_verification(identity.UNVERIFIED),
                       identity.verified_identity())
            finally:
                ctx.pop()
            refused += got[0]
            if gated and not got[0]:
                wrong.append((rule.endpoint, method, "a gated route did not refuse"))
            elif not gated and got != (False, identity.UNVERIFIED, "none", None):
                wrong.append((rule.endpoint, method, got))
        assert not wrong, wrong[:12]
        # 118 gated on 2026-10-16; 98 on 2026-10-17 after 7.8's removals; a floor
        assert refused >= 88, refused


# ------------------------------------------------------------------ through the real app

@pytest.fixture
def seen(monkeypatch):
    """The actor each ungated recorder hands its record: NetBox's preview job and the
    remote's read-only checks, neither of which may reach NetBox or GitHub here."""
    from modules import netbox_jobs
    from modules.nsot import remote as R

    got = {}

    def start_preview(operation, list_name, actor, confirm):
        got["netbox"] = actor
        return "job-b2"

    def verify(list_name, with_write_probe=False, actor=""):
        got["verify"] = actor
        return {"ok": True, "checks": [], "actor": actor}

    monkeypatch.setattr(netbox_jobs, "start_preview", start_preview)
    monkeypatch.setattr(netbox_jobs, "read", lambda _id: {"state": "running", "job": "job-b2"})
    monkeypatch.setattr(R, "verify", verify)
    return got


def _ask(networks, seen):  # noqa: F811
    c = networks["client"]
    c.post("/v2/netbox/preview", data={"operation": "import", "list": "Branch"},
           headers={"HX-Request": "true"})
    r = c.post("/remote/verify", json={"list": "Branch"})
    assert r.status_code == 200, r.get_data(as_text=True)
    return seen


def _post(n, path, data):
    r = n["client"].post(path, data=data, headers={"HX-Request": "true"})
    return r, re.sub(r"\s+", " ", r.get_data(as_text=True))


def _create(n, name):
    _r, pv = _post(n, "/v2/settings/networks/new/preview", {"name": name})
    fp = re.search(r'name="fingerprint" value="([0-9a-f]+)"', pv).group(1)
    return _post(n, "/v2/settings/networks/new", {"name": name, "fingerprint": fp})


def _first_commit(repo):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    out = subprocess.run(["git", "-C", str(repo), "log", "--reverse", "--format=%B%x00"],
                         capture_output=True, text=True, env=env, check=True).stdout
    return out.split("\x00")[0].strip()


def _trailers(message):
    return dict(re.findall(r"^([A-Za-z-]+): (.+)$", message, re.M))


class TestTheRealRoutes:
    def test_a_verified_person_s_preview_and_verify_record_that_person(
            self, networks, seen):  # noqa: F811
        got = _ask(networks, seen)
        assert got == {"netbox": TEST_PERSON, "verify": TEST_PERSON}

    def test_an_unverified_request_s_preview_and_verify_record_unverified(
            self, networks, seen, monkeypatch):  # noqa: F811
        monkeypatch.setattr(identity, "identify", lambda _r: UNVERIFIED_REQUEST)
        got = _ask(networks, seen)
        assert got == {"netbox": "unverified", "verify": "unverified"}

    def test_a_network_s_first_commit_names_the_person_who_created_it(
            self, networks):  # noqa: F811
        r, html = _create(networks, "Site West")
        assert r.status_code == 200 and "Created Site West" in html, html[:400]
        message = _first_commit(networks["dir"] / "lists" / "site_west" / "config_repo")
        assert message.startswith("Initialize NSoT configuration repository"), message
        t = _trailers(message)
        assert (t.get("Actor"), t.get("Actor-Verified"), t.get("Source")) == \
            (TEST_PERSON, "access", "init"), message
        from modules.history_sources import actor_words
        assert actor_words(t["Actor"], t["Actor-Verified"]) == {"who": TEST_PERSON, "how": ""}

    def test_an_unverified_request_cannot_create_a_network(
            self, networks, monkeypatch):  # noqa: F811
        _r, pv = _post(networks, "/v2/settings/networks/new/preview", {"name": "Site North"})
        fp = re.search(r'name="fingerprint" value="([0-9a-f]+)"', pv).group(1)
        monkeypatch.setattr(identity, "identify", lambda _r: UNVERIFIED_REQUEST)
        r, _html = _post(networks, "/v2/settings/networks/new",
                         {"name": "Site North", "fingerprint": fp})
        assert r.status_code == 403
        registry = json.loads((networks["dir"] / "device_lists.json").read_text())["lists"]
        assert "Site North" not in registry
        assert not (networks["dir"] / "lists" / "site_north").exists()

    def test_a_first_commit_an_unverified_request_makes_says_unverified(
            self, networks, monkeypatch):  # noqa: F811
        """The gate refuses this route unverified; the record's words are held where it is
        made, in the request (a gate switched off by its setting reaches exactly this)."""
        from modules import network_admin as NA
        monkeypatch.setattr(identity, "identify", lambda _r: UNVERIFIED_REQUEST)
        fp = NA.create_preview("Site South")["fingerprint"]
        with _app().test_request_context("/v2/settings/networks/new", method="POST"):
            NA.create("Site South", fp, identity.request_actor(),
                      identity.actor_verification(identity.request_actor()))
        t = _trailers(_first_commit(networks["dir"] / "lists" / "site_south" / "config_repo"))
        assert (t.get("Actor"), t.get("Actor-Verified")) == ("unverified", "none")

    @pytest.mark.parametrize("operation", ["import", "remove", "forget"])
    def test_a_confirmed_netbox_job_s_record_names_who_confirmed(
            self, operation, tmp_path, monkeypatch):
        """The job record carried the PREVIEW's actor through the confirm, so all 8 NetBox job
        records of W2's sitting read "unauthenticated", the import d0d4031f77 among them,
        though its writes named the person. NetBox's writes are faked; the record is real."""
        from modules import config, netbox_client, netbox_guard, netbox_jobs, netbox_ops
        from modules import preview_confirm
        monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
        monkeypatch.setattr(netbox_ops, "start_import",
                            lambda *a, on_end=None, **k: on_end("done"))
        monkeypatch.setattr(netbox_client, "sync_status_with_results", lambda: {"lists": {}})
        monkeypatch.setattr(netbox_ops, "remove", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(netbox_ops, "forget", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(netbox_guard, "record_removal", lambda *a, **k: {"row": {}})
        monkeypatch.setattr(preview_confirm, "netbox_removal_result", lambda *a: {})

        job_id = netbox_jobs.new_id()
        netbox_jobs._write(job_id, {"state": "previewed", "operation": operation,
                                    "list": "Branch", "actor": "unverified", "token": "t"})
        confirm = {"import": netbox_jobs.start_import, "remove": netbox_jobs.remove,
                   "forget": netbox_jobs.forget}[operation]
        confirm(job_id, {}, TEST_PERSON)
        job = netbox_jobs.read(job_id)
        assert job["state"] == "imported", job
        assert (job["actor"], job["previewed_by"]) == (TEST_PERSON, "unverified"), job

    def test_a_first_commit_with_nobody_s_request_behind_it_names_mercury(self, tmp_path):
        from modules.nsot import repo as R
        R.init_repo(str(tmp_path / "config_repo"))
        t = _trailers(_first_commit(tmp_path / "config_repo"))
        assert t.get("Actor") == "Mercury: repository init" and t.get("Source") == "init"
        assert t.get("Actor-Verified") in ("none", "host-shell")
