"""Out-of-band ZTP on v2 (O6b and O7; routes/console_ztp_v2.py, templates/v2/_console_ztp.html,
Add device's offer in templates/v2/_onboard_add.html; docs/LAB9_PLAN.md section 8).

Through the Flask client, on the shared fake NetBox and the fake console server
(tests/console_fakes.py, via tests/test_console_ztp.World: s5's real console text):

- the offer: drawn on Add device's review only when NetBox shows the device's console path,
  its absence said with why (no Planned record, no cable, NetBox unreadable); after Create the
  kick-start is offered for a device whose survey is recorded;
- the survey: its preview names the path, the transport, the profile and every line, writes
  nothing and contacts no console; a refused preview draws each gate and no confirm; a confirm
  whose hash moved names both hashes and sends nothing; a person's confirm runs the job, the
  card listens for `console_ztp` and then draws the result (blank, the startup size, the
  transcript) from the record; a job that failed or a record no job explains is said;
- the kick-start: refused before Create (the device is not in the network), and without a
  survey; its preview draws the exact lines with the hostname NetBox's name (never a field);
  a confirm by anyone but a verified person is refused with nothing typed; a verified
  person's sends exactly the previewed lines.
"""

import os
import re
import types

import pytest

from modules.nsot import console_profiles as P
from modules.nsot import console_ztp as Z
from tests.test_console_session import PNP
from tests.test_console_ztp import (FAST, LIST, PLANNED, World, after_lines, blank_answers,
                                    kick_answers)

PERSON = "operator@example.invalid"


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch, __import__("socket").AF_INET)
    monkeypatch.setattr("modules.netbox_client._nb_ready",
                        lambda: (True, "", w.fake, "http://nb.invalid"))
    monkeypatch.setattr(Z, "DEFAULT_TIMINGS", FAST)
    yield w
    w.server.close()


@pytest.fixture
def client():
    import app as nmas
    return nmas.app.test_client()


@pytest.fixture
def person(monkeypatch):
    """A verified person at every gate (the gate and the route both ask `require`), verified by
    the access assertion."""
    from modules import identity
    who = types.SimpleNamespace(actor=PERSON, kind="person", peer="192.0.2.5",
                                is_identified=True)
    monkeypatch.setattr(identity, "require", lambda *a, **k: (who, None))
    monkeypatch.setattr(identity, "actor_verification",
                        lambda actor: "access" if actor == PERSON else "none")
    return who


def _text(r) -> str:
    return r.get_data(as_text=True)


def _form(html: str) -> dict:
    """The hidden fields of the card's last form, as the browser would send them."""
    form = html.rsplit("<form", 1)[1]
    return dict(re.findall(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"', form))


def _wait(job: str):
    from modules.nsot import capture_job
    assert capture_job.wait(job, 30), "the job did not end within 30 s"
    return capture_job.get(job)


def _url(world, path=""):
    return f"/v2/onboard/console/{world.dev['id']}{path}"


# ── The offer (O7) ─────────────────────────────────────────────────────────────────────────

class TestTheOffer:
    def test_no_planned_record_says_why_and_reads_nothing(self, monkeypatch):
        from routes import console_ztp_v2 as R
        read = []
        monkeypatch.setattr("modules.nsot.console_path.read_console_path",
                            lambda *a, **k: read.append(a) or {})
        got = R.offer(LIST, None, "edge1", "cisco_ios", "switch")
        assert got["state"] == "no_record" and read == []
        assert got["why"].startswith("NetBox holds no Planned record of edge1")

    def test_a_console_path_is_offered_with_the_profile_for_its_role(self, world):
        from routes import console_ztp_v2 as R
        got = R.offer(LIST, world.dev["id"], "edge1", "cisco_ios", "switch")
        assert got["state"] == "path" and got["profile"] == "cisco_ios_switch"
        assert got["paths"][0]["server_port"]["name"] == "port 5"
        assert R.offer(LIST, world.dev["id"], "edge1", "cisco_ios", "router")["profile"] == \
            "cisco_ios_router"

    def test_no_cable_and_an_unreadable_netbox_are_said_apart(self, world, monkeypatch):
        from routes import console_ztp_v2 as R
        world.fake.store["dcim/cables"] = []
        world.port["cable"] = None
        got = R.offer(LIST, world.dev["id"], "edge1")
        assert got["state"] == "no_path" and "has no cable" in got["why"]
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (False, "NetBox URL and API token are not configured",
                                     None, ""))
        got = R.offer(LIST, world.dev["id"], "edge1")
        assert got["state"] == "unreadable" and "NetBox is not reachable" in got["why"]

    def test_a_platform_with_no_profile_chooses_none(self):
        from routes import console_ztp_v2 as R
        assert R.profile_for("no_such_dialect", "switch") == ""
        assert R.profile_for("cisco_ios", "") == ""        # two fit, and no role to choose by

    def test_add_device_s_review_draws_the_offer_or_its_absence(self, world, client, person,
                                                                 monkeypatch):
        from modules.nsot import onboard as O
        from tests.test_onboard_v2 import FORM, _plan

        def planned(record):
            def build(**_k):
                plan = _plan(hostname="edge1", platform="cisco_ios", role="switch")
                plan.netbox_record = record
                return plan
            return build

        def offer(html):
            """The review's offer, asked for as it loads, as the browser asks for it."""
            m = re.search(r'id="ob-console" aria-busy="true" hx-get="([^"]+)" '
                          r'hx-trigger="load"', html)
            assert m, "the review asks for no offer"
            return _text(client.get(m.group(1).replace("&amp;", "&")))

        form = dict(FORM, list_name=LIST, hostname="edge1", role="switch")
        monkeypatch.setattr(O, "build_plan", planned({"id": world.dev["id"],
                                                      "status": "planned"}))
        html = _text(client.post("/v2/onboard/preview", data=form))
        assert 'id="ob-create"' in html, "the Use <MAC> button includes the Create form"
        got = offer(html)
        assert 'id="ob-console"' in got and "Kick-start through the console…" in got
        assert f'hx-get="/v2/onboard/console/{world.dev["id"]}?list_name={LIST}&amp;' \
               "step=survey&amp;hostname=edge1&amp;profile=cisco_ios_switch&amp;add=1" in got
        monkeypatch.setattr(O, "build_plan", planned({"id": 9, "status": "active"}))
        got = offer(_text(client.post("/v2/onboard/preview", data=form)))
        assert "Kick-start through the console…" not in got
        assert 'data-console-absent="no_record"' in got
        assert "No console kick-start: NetBox holds no Planned record of edge1" in got

    def test_after_create_the_kick_start_is_offered_for_a_surveyed_device(self, world):
        from routes import console_ztp_v2 as R
        assert R.surveyed_offer(LIST, "edge1") is None
        world.survey(greeting=PNP, answers=blank_answers())
        got = R.surveyed_offer(LIST, "EDGE1")
        assert got["device_id"] == world.dev["id"] and got["survey"]["blank"] is True
        assert R.surveyed_offer("elsewhere", "edge1") is None

    def test_create_s_result_draws_the_kick_start(self, world, client, person, monkeypatch,
                                                  tmp_path):
        from modules.nsot import onboard as O
        from tests.test_onboard_v2 import FORM, _plan

        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        monkeypatch.setattr(O, "build_plan", lambda **k: _plan())
        monkeypatch.setattr(O, "real_steps", lambda repo, actor="": {})
        monkeypatch.setattr(O, "run_onboarding", lambda plan, repo, **k: {
            "ok": True, "completed": ["credentials", "commit", "render"], "commit": "a" * 40})
        shown = O.plan_shown(_plan())
        form = dict(FORM, list_name=LIST, hostname="edge1", shown=shown,
                    fingerprint=O.plan_fingerprint(shown))
        html = _text(client.post("/v2/onboard/create", data=form))
        assert "PENDING" in html and "Kick-start" not in html, "no survey: nothing offered"
        world.survey(greeting=PNP, answers=blank_answers())
        html = _text(client.post("/v2/onboard/create", data=form))
        assert "Kick-start edge1 through the console…" in html
        assert f"/v2/onboard/console/{world.dev['id']}?list_name={LIST}&amp;step=kickstart" \
            in html


# ── The survey ─────────────────────────────────────────────────────────────────────────────

class TestTheSurvey:
    def test_the_card_at_rest_chooses_the_profile_it_was_offered(self, world, client):
        from modules import csp
        r = client.get(_url(world, f"?list_name={LIST}&step=survey&hostname=edge1"
                                   "&profile=cisco_ios_switch&add=1"))
        html = _text(r)
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert '<option value="cisco_ios_switch" selected>' in html
        assert "Preview the survey" in html and world.server.accepted == 0

    def test_the_preview_names_the_path_the_transport_and_every_line(self, world, client,
                                                                      tmp_path):
        before = sorted(os.listdir(tmp_path / "data"))
        r = client.post(_url(world, "/survey/preview"),
                        data={"list_name": LIST, "step": "survey", "profile": "cisco_ios_switch",
                              "hostname": "edge1", "add": "1"})
        html = _text(r)
        assert r.status_code == 200, html
        pv = Z.survey_preview(LIST, world.dev["id"], profile="cisco_ios_switch")
        assert _form(html)["hash"] == pv["hash"]
        for words in ("con 0", "cons-1 port 5", pv["transport"], "terminal length 0⏎",
                      "show version⏎", "dir nvram:⏎", "disable⏎", "Survey edge1&#39;s console",
                      "No configuration line is typed and nothing is saved"):
            assert words in html, words
        assert world.server.accepted == 0, "a preview contacts no console"
        assert sorted(os.listdir(tmp_path / "data")) == before, "a preview writes nothing"

    def test_a_refused_preview_draws_each_gate_and_no_confirm(self, world, client):
        from modules.nsot import console_servers
        console_servers.remove_port(world.sport["id"], actor=PERSON)
        r = client.post(_url(world, "/survey/preview"),
                        data={"list_name": LIST, "step": "survey", "profile": "cisco_ios_switch"})
        html = _text(r)
        assert r.status_code == 409
        assert "The console-server port&#39;s record:" in html
        assert f"console-server port {world.sport['id']} (cons-1 port 5) has no record" in html
        assert "Settings › Installation › Console servers" in html
        assert "Survey edge1&#39;s console" not in html and 'name="hash"' not in html

    def test_a_confirm_whose_hash_moved_names_both_and_sends_nothing(self, world, client,
                                                                     person):
        r = client.post(_url(world, "/survey"),
                        data={"list_name": LIST, "step": "survey", "profile": "cisco_ios_switch",
                              "hash": "0" * 64})
        html = _text(r)
        pv = Z.survey_preview(LIST, world.dev["id"], profile="cisco_ios_switch")
        assert r.status_code == 409
        assert f"({'0' * 64} -&gt; {pv['hash']})" in html and "Nothing was sent" in html
        assert world.server.accepted == 0

    def test_without_a_person_the_gate_refuses_and_nothing_is_sent(self, world, client,
                                                                   monkeypatch):
        from modules import identity
        monkeypatch.setattr(identity, "require", lambda *a, **k: (
            types.SimpleNamespace(actor="unverified", is_identified=False),
            {"ok": False, "error": "This action requires a verified identity: none."}))
        pv = Z.survey_preview(LIST, world.dev["id"], profile="cisco_ios_switch")
        r = client.post(_url(world, "/survey"),
                        data={"list_name": LIST, "step": "survey",
                              "profile": "cisco_ios_switch", "hash": pv["hash"]})
        assert r.status_code == 403 and world.server.accepted == 0

    def test_a_person_s_confirm_runs_it_as_a_job_and_the_card_draws_the_record(
            self, world, client, person):
        world.consoles.append((PNP, blank_answers()))
        pv = Z.survey_preview(LIST, world.dev["id"], profile="cisco_ios_switch")
        r = client.post(_url(world, "/survey"),
                        data={"list_name": LIST, "step": "survey", "profile": "cisco_ios_switch",
                              "hostname": "edge1", "add": "1", "hash": pv["hash"]})
        html = _text(r)
        assert r.status_code == 200, html
        assert 'hx-trigger="nmas:console_ztp from:body, nmas:device_progress from:body"' \
            in html and 'aria-busy="true"' in html
        run = re.search(r"run=([0-9]{8}T[0-9]{12}Z-[0-9a-f]{32})", html).group(1)
        job = re.search(r"job=([0-9a-f]{32})", html).group(1)
        assert _wait(job)["state"] == "done"
        html = _text(client.get(_url(world, f"?list_name={LIST}&step=survey&run={run}"
                                            f"&job={job}&hostname=edge1&add=1")))
        assert "factory-blank" in html and "found at press_return" in html
        assert "0 bytes" in html, "the startup configuration's size"
        assert "The console's transcript (masked)" in html
        assert "Kick-start edge1…" in html, "a blank survey leads to the kick-start"
        rec = Z.get_run(LIST, run)
        assert (rec["actor"], rec["actor_verified"], rec["outcome"]) == (PERSON, "access",
                                                                         "surveyed")
        assert world.server.accepted == 1

    def test_a_failed_job_and_a_lost_one_are_said(self, world, client, monkeypatch):
        from modules.nsot import capture_job
        run = "20261022T000000000000Z-" + "a" * 32
        monkeypatch.setattr(capture_job, "get", lambda job: {
            "state": "failed", "error": "Refused: the survey changed since the preview"})
        html = _text(client.get(_url(world, f"?list_name={LIST}&run={run}&job={'b' * 32}")))
        assert "The run ended before its record did: Refused: the survey changed" in html
        monkeypatch.setattr(capture_job, "get", lambda job: None)
        html = _text(client.get(_url(world, f"?list_name={LIST}&run={run}&job={'b' * 32}")))
        assert "This server has no record of the run's job" in html


class TestThePendingPage:
    """C1575: once Add device's card is closed, the pending device's page is the way back. Its
    actions at rest (the page's own `#pending-actions`, re-drawn by Cancel and Close) offer the
    card when a survey is recorded (no NetBox read), at the kick-start when it found the device
    blank and at the survey again when not; with none recorded, a NetBox record onboarding
    recorded has its console path asked for as the page draws, offering the survey."""

    @pytest.fixture
    def pending(self, world, tmp_path, monkeypatch):
        from modules.nsot import listref, manifest
        repo = tmp_path / "repo"
        (repo / ".nsot").mkdir(parents=True)
        monkeypatch.setattr(listref, "resolve",
                            lambda name: types.SimpleNamespace(repo_dir=str(repo)))

        def onboard(netbox_id=None):
            manifest.upsert_device(str(repo), manifest.identity_for(device_uid="uid-edge1"),
                                   "edge1", pending=True, address_source="ztp",
                                   netbox_id=netbox_id, platform="cisco_ios", role="switch")
        return onboard

    def _actions(self, client) -> str:
        return _text(client.get(f"/v2/onboard/edge1/actions?list_name={LIST}"))

    def test_a_recorded_blank_survey_offers_the_kick_start_and_opens_the_card(
            self, world, client, pending, monkeypatch):
        from routes import console_ztp_v2 as R
        pending(netbox_id=world.dev["id"])
        world.survey(greeting=PNP, answers=blank_answers())
        read = []
        monkeypatch.setattr("modules.nsot.console_path.read_console_path",
                            lambda *a, **k: read.append(a) or {})
        html = self._actions(client)
        assert "Kick-start edge1 through the console…" in html and read == []
        url = re.search(r'hx-get="(/v2/onboard/console/\d+\?[^"]*step=kickstart[^"]*)"', html)
        assert url, "the card at the kick-start"
        monkeypatch.setattr(R, "_onboarded", lambda l, h: "")
        card = _text(client.get(url.group(1).replace("&amp;", "&")))
        assert 'id="console-ztp-card"' in card and "Preview the kick-start" in card

    def test_a_survey_that_found_it_configured_offers_the_survey_again(self, world, client,
                                                                        pending):
        pending(netbox_id=world.dev["id"])
        world.survey(answers=[b"\r\nSwitch#"])
        html = self._actions(client)
        assert "Survey edge1's console again…" in html
        assert "Kick-start edge1" not in html
        assert re.search(r'hx-get="/v2/onboard/console/\d+\?[^"]*step=survey[^"]*'
                         r'profile=cisco_ios_switch', html)

    def test_no_survey_asks_netbox_for_the_path_as_the_page_draws(self, world, client, pending):
        pending(netbox_id=world.dev["id"])
        html = self._actions(client)
        lazy = re.search(r'id="ob-console" aria-busy="true" hx-get="([^"]+)" hx-trigger="load"',
                         html)
        assert lazy and "pending=1" in lazy.group(1), "the path is asked for, never waited on"
        got = _text(client.get(lazy.group(1).replace("&amp;", "&")))
        assert "Survey edge1's console…" in got and "No survey of its console" in got
        assert "add=1" not in got, "not inside Add device: no plan to put the MAC in"
        world.fake.store["dcim/cables"] = []
        world.port["cable"] = None
        got = _text(client.get(lazy.group(1).replace("&amp;", "&")))
        assert 'hidden data-console-absent="no_path"' in got and "No console" not in got

    def test_no_survey_and_no_netbox_record_draws_nothing(self, world, client, pending):
        pending()
        html = self._actions(client)
        assert 'id="ob-console"' not in html and 'id="pending-actions"' in html


class TestAnOutOfBandDeviceHasNoStandaloneConsole:
    """C1643 and C1642 (the operator, Lab 9's take, 2026-10-23): a device the one-decision
    out-of-band run onboarded (address source `ztp_console`) still drew the old survey and
    kick-start on its pending page, and their routes would run on it. Its console is its run's:
    the routes refuse it, by its NetBox id or its name, naming its address source and the
    path's home, and send nothing; its page names how its run ended and links the run's page.
    Controls: the same device onboarded by ZTP is still offered the standalone flow (the
    router's DHCP-path nudge keeps its home), and a recorded run is still read."""

    WHY = ("edge1&#39;s onboarding in {list} is out-of-band: its address source is "
           "&#39;ztp_console&#39;, the one-decision console run&#39;s")

    @pytest.fixture
    def onboarded(self, world, tmp_path, monkeypatch):
        from modules.nsot import listref, manifest
        repo = tmp_path / "repo"
        (repo / ".nsot").mkdir(parents=True)
        monkeypatch.setattr(listref, "resolve",
                            lambda name: types.SimpleNamespace(repo_dir=str(repo)))

        def onboard(address_source="ztp_console", netbox_id=None):
            manifest.upsert_device(str(repo), manifest.identity_for(device_uid="uid-edge1"),
                                   "edge1", pending=True, address_source=address_source,
                                   netbox_id=netbox_id, platform="cisco_ios", role="switch")
        return onboard

    def _actions(self, client) -> str:
        return _text(client.get(f"/v2/onboard/edge1/actions?list_name={LIST}"))

    @pytest.mark.parametrize("by", ["netbox_id", "name"])
    def test_the_card_draws_only_the_refusal(self, world, client, onboarded, by):
        onboarded(netbox_id=world.dev["id"] if by == "netbox_id" else None)
        name = "&hostname=edge1" if by == "name" else ""
        html = _text(client.get(_url(world, f"?list_name={LIST}&step=survey{name}")))
        assert "Refused:" in html and self.WHY.format(list=LIST) in html, html
        assert "Preview the survey" not in html and "<form" not in html
        assert world.server.accepted == 0

    @pytest.mark.parametrize("path,step", [("/survey/preview", "survey"),
                                           ("/kickstart/preview", "kickstart")])
    def test_each_preview_refuses_it(self, world, client, onboarded, path, step):
        onboarded(netbox_id=world.dev["id"])
        r = client.post(_url(world, path), data={"list_name": LIST, "step": step,
                                                 "profile": "cisco_ios_switch",
                                                 "hostname": "edge1"})
        html = _text(r)
        assert r.status_code == 409 and self.WHY.format(list=LIST) in html, html
        assert 'name="hash"' not in html and world.server.accepted == 0

    @pytest.mark.parametrize("path,step", [("/survey", "survey"), ("/kickstart", "kickstart")])
    def test_each_confirm_refuses_it_and_sends_nothing(self, world, client, person, onboarded,
                                                       path, step):
        onboarded(netbox_id=world.dev["id"])
        r = client.post(_url(world, path), data={"list_name": LIST, "step": step,
                                                 "profile": "cisco_ios_switch",
                                                 "hostname": "edge1", "hash": "0" * 64})
        html = _text(r)
        assert r.status_code == 409 and self.WHY.format(list=LIST) in html, html
        assert "Nothing was sent." in html and world.server.accepted == 0

    def test_a_device_onboarded_by_ztp_is_still_offered_the_survey(self, world, client,
                                                                   onboarded):
        onboarded(address_source="ztp", netbox_id=world.dev["id"])
        html = _text(client.get(_url(world, f"?list_name={LIST}&step=survey&hostname=edge1"
                                            "&profile=cisco_ios_switch")))
        assert "Refused:" not in html and "Preview the survey" in html

    def test_its_page_names_its_run_and_offers_neither(self, world, client, onboarded,
                                                      monkeypatch):
        from modules.nsot import oob_onboard as O
        onboarded(netbox_id=world.dev["id"])
        world.survey(greeting=PNP, answers=blank_answers())     # a survey recorded before
        monkeypatch.setattr(O, "latest_run", lambda l, h: {
            "id": "r1", "outcome": "done", "started_at": "2026-10-23T23:53:23Z",
            "finished_at": "2026-10-23T23:56:17Z"} if (l, h) == (LIST, "edge1") else None)
        html = self._actions(client)
        assert "Onboarded out of band: its console run" in html, html
        assert "onboarded, answering: ready to Verify" in html
        assert re.search(r'href="/v2/[^"]*run\?list=' + LIST + r'&amp;device=edge1"', html), html
        for offer in ("Kick-start edge1", "Survey edge1", "/v2/onboard/console/"):
            assert offer not in html, offer

    def test_its_page_says_when_no_run_is_recorded_or_its_runs_cannot_be_read(
            self, world, client, onboarded, monkeypatch):
        from modules.nsot import oob_onboard as O
        onboarded()
        monkeypatch.setattr(O, "latest_run", lambda l, h: None)
        assert f"no console run of edge1 is recorded in {LIST}" in self._actions(client)

        def broken(l, h):
            raise OSError("the run records are unreadable")

        monkeypatch.setattr(O, "latest_run", broken)
        assert ("its console run could not be read: OSError: the run records are unreadable"
                in self._actions(client))


def _steps(html: str) -> list:
    """THE stepper's steps as drawn: ``[(key, state), ...]`` in order."""
    return [(k, s) for s, k in re.findall(
        r'<li class="run-step run-step-(\w+)" data-step="(\w+)"', html)]


class TestTheStepperFromTheConfirm:
    """C1579 (Lab 9's R8 recording: Verify and the NetBox import drew their stepper only near
    the end): the confirm's own answer draws THE stepper, the preview and the confirm done and
    every step of the run not yet done, and each step the run begins fills it, announced as
    `device_progress`, which the running card listens for (the deploy's pattern)."""

    def test_every_declared_name_is_a_note_the_code_makes(self):
        import ast
        tree = ast.parse(open(Z.__file__, encoding="utf-8").read())
        consts, prefixes = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "note" \
                    and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant):
                    consts.add(arg.value)
                elif isinstance(arg, ast.JoinedStr):
                    prefixes.add(arg.values[0].value)
        assert len(consts) >= 9 and prefixes == {"survey: "}, (consts, prefixes)
        declared = {n for kind in (Z.KIND_SURVEY, Z.KIND_KICKSTART)
                    for s in Z.run_stepper_steps(kind) for n in s[3]}
        for name in declared:
            assert name in consts or any(name.startswith(p) for p in prefixes), name
        assert consts <= declared, consts - declared
        for kind, steps in ((Z.KIND_SURVEY, Z.SURVEY_STEPS), (Z.KIND_KICKSTART,
                                                                Z.KICKSTART_STEPS)):
            assert [s[0] for s in Z.run_stepper_steps(kind)] == \
                [k for k, _w in steps if k not in Z.BEFORE_RUN]

    def test_the_confirm_draws_it_at_once_and_each_step_fills_it(self, world, client, person,
                                                                monkeypatch):
        import threading

        from modules import invalidation
        from modules.nsot import device_ops

        # The job is held as it begins the hold, and again as it begins the MAC read.
        gates = {"opening the console": threading.Event(), "survey: mac": threading.Event()}
        reached = {k: threading.Event() for k in gates}
        real_note, said = device_ops.note, []

        def note(step, device=None):
            real_note(step, device)
            if step in gates:
                reached[step].set()
                assert gates[step].wait(30)

        monkeypatch.setattr(device_ops, "note", note)
        monkeypatch.setattr(invalidation, "announce",
                            lambda keys, who, ok: said.append(tuple(keys)))
        world.consoles.append((PNP, blank_answers()))
        pv = Z.survey_preview(LIST, world.dev["id"], profile="cisco_ios_switch")
        try:
            r = client.post(_url(world, "/survey"),
                            data={"list_name": LIST, "step": "survey", "hostname": "edge1",
                                  "profile": "cisco_ios_switch", "add": "1",
                                  "hash": pv["hash"]})
            html = _text(r)
            assert r.status_code == 200, html
            assert "data-run-stepper" in html, "the confirm's answer draws THE stepper"
            assert _steps(html) == [("preview", "done"), ("confirm", "done"),
                                    ("hold", "running"), ("wake", "waiting"),
                                    ("reads", "waiting"), ("release", "waiting"),
                                    ("verify", "waiting"), ("record", "waiting")]
            assert "nmas:device_progress from:body" in html, "it fills as each step begins"
            assert 'href="/v2/device/edge1"' not in html, "no page yet to link to"
            run = re.search(r"run=([0-9]{8}T[0-9]{12}Z-[0-9a-f]{32})", html).group(1)
            job = re.search(r"job=([0-9a-f]{32})", html).group(1)
            card = _url(world, f"?list_name={LIST}&step=survey&run={run}&job={job}"
                               "&hostname=edge1&add=1")
            assert reached["opening the console"].wait(30)
            assert _steps(_text(client.get(card)))[2] == ("hold", "running")
            gates["opening the console"].set()
            assert reached["survey: mac"].wait(30)
            assert said.count(("device_progress",)) >= 4, said
            got = _steps(_text(client.get(card)))
            assert got == [("preview", "done"), ("confirm", "done"), ("hold", "done"),
                           ("wake", "done"), ("reads", "running"), ("release", "waiting"),
                           ("verify", "waiting"), ("record", "waiting")], got
        finally:
            for gate in gates.values():
                gate.set()
        assert _wait(job)["state"] == "done"
        html = _text(client.get(card))
        assert "factory-blank" in html and "data-run-stepper" not in html, "its record, drawn"

    def test_a_hold_by_another_operation_is_not_this_run_s_progress(self):
        from modules.nsot import device_ops
        from routes import console_ztp_v2 as R
        device_ops.acquire(LIST, "edge1", "deploy", PERSON)
        try:
            device_ops.note("waking the console")
            rows = R.run_steps(Z.KIND_KICKSTART, LIST, "edge1")
        finally:
            device_ops.release(LIST, "edge1")
        assert [(r["key"], r["state"]) for r in rows] == [
            ("preview", "done"), ("confirm", "done"), ("hold", "running"), ("wake", "waiting"),
            ("recheck", "waiting"), ("type", "waiting"), ("verify", "waiting"),
            ("readback", "waiting"), ("copy", "waiting"), ("record", "waiting")]


class TestHistory:
    """Each run is read again on History (Console surveys and kick-starts), the network's own
    records, a device being onboarded included (no inventory filters it out)."""

    def _ctx(self, device=""):
        return {"ref": types.SimpleNamespace(name=LIST), "device": device, "members": set(),
                "limit": 50, "since": None}

    def test_a_survey_is_an_event_with_its_verdict_mac_and_transcript(self, world):
        from modules import history_sources as HS
        rec = world.survey(greeting=PNP, answers=blank_answers())
        got = HS.console_ztp(self._ctx())
        assert got["errors"] == [] and len(got["events"]) == 1
        ev = got["events"][0]
        assert (ev["kind"], ev["what"], ev["devices"], ev["outcome"]) == (
            "console", "Console survey: factory-blank", ["edge1"], "surveyed")
        assert ev["marks"] == [] and dict(ev["record"])["Run"] == rec["id"]
        assert "Transcript (masked)" in dict(ev["record"])
        assert HS.console_ztp(self._ctx(device="other"))["events"] == []
        assert "console" in HS.KIND_FILTERS and HS.SOURCES["console_ztp"] is HS.console_ztp

    def test_a_console_found_signed_in_is_marked_stopped(self, world):
        from modules import history_sources as HS
        world.survey(answers=[b"\r\nSwitch#"])
        ev = HS.console_ztp(self._ctx())["events"][0]
        assert ev["what"] == "Console survey: not factory-blank"
        assert ev["outcome"] == "stopped: found signed in" and ev["marks"] == ["stopped"]


# ── The kick-start ─────────────────────────────────────────────────────────────────────────

class TestTheKickstart:
    def _surveyed(self, world, monkeypatch, onboarded=True):
        from routes import console_ztp_v2 as R
        world.survey(greeting=PNP, answers=blank_answers())
        if onboarded:
            monkeypatch.setattr(R, "_onboarded", lambda l, h: "")

    def test_it_is_refused_until_the_device_is_in_the_network(self, world, client, tmp_path,
                                                              monkeypatch):
        from modules.nsot import listref, manifest
        self._surveyed(world, monkeypatch, onboarded=False)
        repo = tmp_path / "repo"
        (repo / ".nsot").mkdir(parents=True)
        monkeypatch.setattr(listref, "resolve",
                            lambda name: types.SimpleNamespace(repo_dir=str(repo)))
        r = client.post(_url(world, "/kickstart/preview"),
                        data={"list_name": LIST, "step": "kickstart",
                              "param_interface": "GigabitEthernet0/1", "param_vlan": "10"})
        assert r.status_code == 409
        assert "edge1 is not in console-o6 yet: Create it in Add device first" in _text(r)
        manifest.upsert_device(str(repo), manifest.new_device_uid(), "edge1")
        r = client.post(_url(world, "/kickstart/preview"),
                        data={"list_name": LIST, "step": "kickstart",
                              "param_interface": "GigabitEthernet0/1", "param_vlan": "10"})
        assert r.status_code == 200, _text(r)

    def test_without_a_survey_it_is_refused(self, world, client):
        html = _text(client.get(_url(world, f"?list_name={LIST}&step=kickstart")))
        assert "has no console survey in console-o6: survey its console first" in html

    def test_the_preview_draws_the_exact_lines_with_netbox_s_hostname(self, world, client,
                                                                      monkeypatch):
        from modules.nsot import console_survey as V
        self._surveyed(world, monkeypatch)
        html = _text(client.get(_url(world, f"?list_name={LIST}&step=kickstart")))
        assert 'name="param_interface"' in html and 'name="param_vlan"' in html
        assert 'name="param_hostname"' not in html, "the hostname is NetBox's, never typed"
        r = client.post(_url(world, "/kickstart/preview"),
                        data={"list_name": LIST, "step": "kickstart",
                              "param_interface": "GigabitEthernet0/1", "param_vlan": "10"})
        html = _text(r)
        lines = V.render_kickstart(P.load("cisco_ios_switch"),
                                   {"hostname": "edge1", "interface": "GigabitEthernet0/1",
                                    "vlan": "10", **PLANNED})
        assert r.status_code == 200, html
        assert "<pre class=\"ask-pre\">" + "\n".join(lines) + "\n</pre>" in html
        assert " exec-timeout 15 0" in lines and "hostname edge1" in lines
        assert "Kick-start edge1" in html and world.server.accepted == 1

    def test_only_a_verified_person_may_confirm_and_nothing_is_typed_otherwise(
            self, world, client, person, monkeypatch):
        from modules import identity
        self._surveyed(world, monkeypatch)
        params = {"interface": "GigabitEthernet0/1", "vlan": "10"}
        pv = Z.kickstart_preview(LIST, world.dev["id"], params)
        monkeypatch.setattr(identity, "actor_verification", lambda actor: "host-shell")
        r = client.post(_url(world, "/kickstart"),
                        data={"list_name": LIST, "step": "kickstart", "hash": pv["hash"],
                              "param_interface": "GigabitEthernet0/1", "param_vlan": "10"})
        assert r.status_code == 403
        assert "a kick-start is confirmed by a verified person" in _text(r)
        assert "verified &#39;host-shell&#39;" in _text(r)
        assert world.server.accepted == 1, "only the survey's connection"

    def test_a_verified_person_s_kick_start_sends_exactly_the_previewed_lines(
            self, world, client, person, monkeypatch):
        from modules.nsot import console_survey as V
        self._surveyed(world, monkeypatch)
        params = {"interface": "GigabitEthernet0/1", "vlan": "10"}
        pv = Z.kickstart_preview(LIST, world.dev["id"], params)
        lines = V.render_kickstart(P.load("cisco_ios_switch"),
                                   dict(params, hostname="edge1", **PLANNED))
        world.consoles.append((b"", kick_answers(lines)))
        r = client.post(_url(world, "/kickstart"),
                        data={"list_name": LIST, "step": "kickstart", "hash": pv["hash"],
                              "hostname": "edge1", "param_interface": "GigabitEthernet0/1",
                              "param_vlan": "10"})
        html = _text(r)
        assert r.status_code == 200, html
        run = re.search(r"run=([0-9]{8}T[0-9]{12}Z-[0-9a-f]{32})", html).group(1)
        job = re.search(r"job=([0-9a-f]{32})", html).group(1)
        assert _wait(job)["state"] == "done"
        program = (b"\renable\rdir nvram:\r" + b"".join(f"{l}\r".encode() for l in lines)
                   + after_lines(lines))
        assert world.received(1) == program
        html = _text(client.get(_url(world, f"?list_name={LIST}&step=kickstart&run={run}"
                                            f"&job={job}")))
        assert "typed, verified" in html and "The lines sent" in html
        assert Z.get_run(LIST, run)["lines"] == list(lines)
