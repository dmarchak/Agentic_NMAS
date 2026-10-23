"""The one-decision out-of-band onboarding on v2 (routes/oob_onboard_v2.py, templates/v2/
_oob_source.html, _oob_onboard.html, oob_run.html, Devices' _in_progress_panel.html; boards A to
D of docs/boards/oob-onboarding.html), with C1591 (Console servers' whole fingerprint) and C1595
(the running cards say leaving is safe).

Through the Flask client on tests/test_oob_onboard.OobWorld (the fake NetBox, the fake console,
the relay in intent; Create, its undo, the MAC's record and SSH stood in for):

- Add device › Address from draws Out-of-band (console) beside the three, disabled until the
  name is given and eligible, its reason and the link that fixes it said;
- Review the plan with it draws ONE review card in Add device (no Create button): the derived
  fields, the console path with the server's whole fingerprint, the program, ONE button;
- the confirm refuses with nothing sent (no reason, a moved hash naming both, not a verified
  person), and otherwise answers at once with THE stepper and "Safe to leave this page: the run
  continues"; the card then draws the record's result; the run has its own page;
- In progress: a console run's row opens its stepper, in the top bar's list and on Devices.
"""

import re
import types

import pytest

from modules.nsot import oob_onboard as O
from tests.test_console_ztp import LIST
from tests.test_oob_onboard import FAST, FIELDS, OobWorld, answers

PERSON = "operator@example.invalid"
QUICK = O.Timings(settle_s=0.05, quiet_s=0.3, step_timeout_s=3.0, poll_s=0.02, bound_s=60.0,
                  copy_timeout_s=5.0, key_settle_s=0.0, answer_bound_s=1.0,
                  answer_every_s=0.01)
FINGERPRINT = "SHA256:YdT9QQPLZ6e6h7X/HyPEFfOjoBxgAIS5jVa+lpFbujE"


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = OobWorld(tmp_path, monkeypatch)
    monkeypatch.setattr("modules.netbox_client._nb_ready",
                        lambda: (True, "", w.fake, "http://nb.invalid"))
    monkeypatch.setattr("modules.nsot.ztp_relayed.intent_everywhere", lambda: w.facts)
    monkeypatch.setattr(O, "_plan", w.plan_builder)
    monkeypatch.setattr(O, "_create", w.create)
    monkeypatch.setattr(O, "undo_created", w.undo)
    monkeypatch.setattr(O, "_record_mac", w.record_mac)
    monkeypatch.setattr(O, "DEFAULT_TIMINGS", QUICK)
    monkeypatch.setattr("modules.readers.reachability.probe", w.probe)
    monkeypatch.setattr("modules.integration_groups.network_names", lambda: [LIST])
    yield w
    w.server.close()


@pytest.fixture
def client():
    import app as nmas
    return nmas.app.test_client()


@pytest.fixture
def person(monkeypatch):
    from modules import identity
    who = types.SimpleNamespace(actor=PERSON, kind="person", peer="192.0.2.5",
                                is_identified=True)
    monkeypatch.setattr(identity, "require", lambda *a, **k: (who, None))
    monkeypatch.setattr(identity, "actor_verification",
                        lambda actor: "access" if actor == PERSON else "none")
    return who


def _text(r) -> str:
    return r.get_data(as_text=True)


def _hidden(html: str) -> dict:
    form = html.rsplit('hx-post="/v2/onboard/oob/confirm"', 1)[1].split("</form>")[0]
    return dict(re.findall(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"', form))


def _wait(job: str):
    from modules.nsot import capture_job
    assert capture_job.wait(job, 30), "the job did not end within 30 s"
    return capture_job.get(job)


ADD = dict(FIELDS, address_source="ztp_console", mgmt_ip="", mgmt_mask="", mgmt_mac="",
           manager_interface="", manager_gateway="", ztp_router="")


# ── Add device's option (board A) ─────────────────────────────────────────────────────────

class TestTheOption:
    def test_the_form_draws_four_sources_the_fourth_waiting_for_a_name(self, client):
        from modules import csp
        r = client.get("/v2/onboard/new?list=Default")
        html = _text(r)
        assert r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        field = html.split('<select id="f-ob-source"')[1].split("</div>")[0]
        assert 'hx-get="/v2/onboard/oob/source?list=Default"' in field
        assert 'hx-swap-oob' not in field, "the page draws the line in place"
        assert 'hx-trigger="change from:#f-ob-hostname"' in field, "no load without a name"
        assert re.search(r'<option value="ztp_console" disabled>Out-of-band \(console\)', field)
        assert "Out-of-band (console) is checked once the name is given" in field
        assert html.count('<option value="ztp_console"') == 1

    def test_an_eligible_device_enables_it(self, world, client):
        html = _text(client.get(f"/v2/onboard/oob/source?list_name={LIST}&hostname=edge1"
                                "&address_source=ztp_console"))
        assert '<option value="ztp_console" selected>' in html
        assert "Out-of-band (console) is available: NetBox shows edge1's console path" in html
        assert '<span class="set-origin ob-oob-why" id="ob-oob-why" hx-swap-oob="true"' in html
        assert "<select" not in html, "the options alone: the select keeps its own attributes"

    def test_a_port_with_no_record_is_disabled_with_its_reason_and_fix(self, world, client):
        from modules.nsot import console_servers
        console_servers.remove_port(world.sport["id"], actor=PERSON)
        html = _text(client.get(f"/v2/onboard/oob/source?list_name={LIST}&hostname=edge1"))
        assert '<option value="ztp_console" disabled>' in html
        assert "has no record in Mercury, so Mercury does not know how to reach it." in html
        assert '<a href="/v2/settings/installation?tab=console">Open Console servers</a>' in html

    def test_no_console_path_links_the_device_s_netbox_page(self, world, client):
        world.fake.store["dcim/cables"] = [c for c in world.fake.store["dcim/cables"]
                                           if c["id"] != world.cable["id"]]
        html = _text(client.get(f"/v2/onboard/oob/source?list_name={LIST}&hostname=edge1"))
        assert "No console path in NetBox for edge1" in html
        assert (f'<a href="http://nb.invalid/dcim/devices/{world.dev["id"]}/" target="_blank" '
                'rel="noopener">Open edge1 in NetBox</a>') in html


# ── the one review (board B) ──────────────────────────────────────────────────────────────

class TestTheReview:
    def test_review_the_plan_draws_one_card_and_one_button(self, world, client, monkeypatch):
        monkeypatch.setattr("modules.host_keys.held", lambda ip: None)
        r = client.post("/v2/onboard/preview", data=ADD)
        html = _text(r)
        assert r.status_code == 200, html
        assert 'id="onboard-add"' in html and 'id="oob-card"' in html
        assert 'id="ob-create"' not in html, "no Create button: the run creates"
        assert html.count("Onboard edge1 through its console</span>") == 1
        prog = html.split("data-oob-program>")[1].split("</pre>")[0]
        for line in ("hostname edge1", " ip address 192.0.2.14 255.255.255.252",
                     "ip default-gateway 192.0.2.13", "read back: show interfaces Vlan1",
                     "copy (priv_exec): copy tftp://192.0.2.10/edge1.cfg running-config⏎"):
            assert line in prog, line
        assert "ip route" not in prog
        for words in ("NetBox IPAM, the one address assigned to it", "relay1 GigabitEthernet3",
                      "Planned in NetBox (id", "no Kea subnet, reservation or MAC rule",
                      "this driver speaks no SSH"):
            assert words in html, words
        assert len(_hidden(html)["hash"]) == 64 and 'name="reason"' in html

    def test_the_console_server_s_whole_fingerprint_is_drawn(self, world, client,
                                                            monkeypatch):
        world.set_port(driver="raw_tcp", host=world.server.host, tcp_port=world.server.port,
                       jump_host="192.0.2.40", ssh_port=22, credential_ref="jump-key")
        monkeypatch.setattr("modules.host_keys.held", lambda ip: {
            "type": "ssh-ed25519", "fingerprint": FINGERPRINT, "kept_at": "2026-10-23T02:46Z"})
        html = _text(client.post("/v2/onboard/preview", data=ADD))
        assert f'ssh-ed25519 <span class="fp" data-fingerprint>{FINGERPRINT}</span>' in html

    def test_a_refused_review_draws_its_checks_and_no_button(self, world, client):
        r = client.post("/v2/onboard/preview", data=dict(ADD, role="router"))
        html = _text(r)
        assert r.status_code == 409
        assert "The role:</strong> the out-of-band static path is built for a switch" in html
        assert "through its console</span>" not in html

    def test_an_uplink_netbox_does_not_cable_is_asked_in_the_card(self, world, client):
        world.uncable()
        html = _text(client.post("/v2/onboard/preview", data=ADD))
        assert 'hx-post="/v2/onboard/oob/preview"' in html and 'name="uplink"' in html
        html = _text(client.post("/v2/onboard/oob/preview",
                                 data=dict(FIELDS, uplink="GigabitEthernet0/2", add="1")))
        assert "asked: typed in the review" in html
        assert "Onboard edge1 through its console</span>" in html


# ── the confirm and the run (boards B and C) ──────────────────────────────────────────────

class TestTheConfirm:
    def review(self, client):
        return _hidden(_text(client.post("/v2/onboard/preview", data=ADD)))

    def test_no_reason_is_refused_and_nothing_is_sent(self, world, client, person):
        form = self.review(client)
        r = client.post("/v2/onboard/oob/confirm", data=dict(form, reason=""))
        assert r.status_code == 409 and "a reason is given" in _text(r)
        assert world.server.accepted == 0

    def test_a_moved_hash_is_refused_naming_both(self, world, client, person):
        form = self.review(client)
        r = client.post("/v2/onboard/oob/confirm", data=dict(form, hash="0" * 64,
                                                              reason="new switch"))
        assert r.status_code == 409
        assert f"({'0' * 64} -&gt; {form['hash']})" in _text(r)
        assert world.server.accepted == 0

    def test_only_a_verified_person_confirms(self, world, client, monkeypatch, person):
        monkeypatch.setattr("modules.identity.actor_verification", lambda a: "none")
        form = self.review(client)
        r = client.post("/v2/onboard/oob/confirm", data=dict(form, reason="new switch"))
        assert r.status_code == 403 and "is confirmed by a verified person" in _text(r)
        assert world.server.accepted == 0

    def test_the_confirm_draws_the_stepper_at_once_then_the_result(self, world, client,
                                                                  person):
        world.consoles.append((b"", answers()))
        form = self.review(client)
        r = client.post("/v2/onboard/oob/confirm", data=dict(form, reason="new switch"))
        html = _text(r)
        assert r.status_code == 200, html
        assert 'hx-trigger="nmas:console_ztp from:body, nmas:device_progress from:body"' in html
        steps = re.findall(r'class="run-step run-step-([a-z_]+)" data-step="([a-z]+)"', html)
        assert steps[:3] == [("done", "preview"), ("done", "confirm"), ("running", "hold")]
        assert [k for _s, k in steps] == ["preview", "confirm"] + [
            k for k, *_ in O.run_stepper_steps()]
        assert "Safe to leave this page: the run continues." in html
        assert "Open this run's page – the run continues" in html
        job = re.search(r"job=([0-9a-f]{32})", html).group(1)
        run = re.search(r"run=([0-9T]+Z-[0-9a-f]{32})", html).group(1)
        assert _wait(job)["state"] == "done"
        card = _text(client.get(f"/v2/onboard/oob/card?list_name={LIST}&run={run}&job={job}"
                                "&hostname=edge1"))
        assert "onboarded, answering: ready to Verify" in card
        assert "0c:00:08:75:80:01" in card and "Open edge1's page to Verify" in card
        page = _text(client.get(f"/v2/onboard/oob/run?list={LIST}&device=edge1"))
        assert 'id="oob-card"' in page and "onboarded, answering: ready to Verify" in page


class TestTheRunPage:
    def test_a_device_with_no_run_says_so(self, world, client):
        html = _text(client.get(f"/v2/onboard/oob/run?list={LIST}&device=nosuch"))
        assert "Nothing to show: nosuch has no console run in" in html

    def test_a_running_run_of_another_process_draws_its_stepper_from_the_hold(self, world,
                                                                             client):
        from modules.nsot import console_ztp as Z
        from modules.nsot import device_ops
        rec = {"id": "20261023T000000000000Z-" + "a" * 32, "kind": O.KIND, "list": LIST,
               "device_id": world.dev["id"], "device": "edge1", "outcome": "running",
               "started_at": 1.0, "at": "2026-10-23T00:00:00Z"}
        Z.record(LIST, rec)
        with device_ops.hold(LIST, "edge1", O.OP, PERSON):
            device_ops.note("onboard: kick-start")
            html = _text(client.get(f"/v2/onboard/oob/run?list={LIST}&device=edge1"))
        assert 'aria-busy="true"' in html and "Safe to leave this page" in html
        assert 'class="run-step run-step-running" data-step="kickstart"' in html


# ── In progress (board D) ─────────────────────────────────────────────────────────────────

class TestInProgress:
    def test_a_console_run_s_row_opens_its_stepper(self, world, client):
        from modules.nsot import device_ops
        with device_ops.hold(LIST, "edge1", O.OP, PERSON):
            device_ops.note("onboard: copy")
            chip = _text(client.get("/operations/in_flight", headers={"HX-Request": "true"}))
            panel = _text(client.get("/operations/in_flight?view=panel",
                                     headers={"HX-Request": "true"}))
        link = (f'href="/v2/onboard/oob/run?list={LIST}&amp;device=edge1">Open its '
                "stepper</a>")
        for html in (chip, panel):
            assert link in html
            assert "Out-of-band onboarding" in html
            assert "Copy the bootstrap: the bootstrap copied from" in html
        assert 'id="h-ip-panel"' in panel

    def test_nothing_running_draws_no_panel(self, world, client, monkeypatch):
        # This process's job registry may hold another test's job: nothing runs here.
        monkeypatch.setattr("modules.op_progress.running", lambda now=None: [])
        monkeypatch.setattr("modules.nsot.capture_job.card_jobs", lambda now=None: [])
        panel = _text(client.get("/operations/in_flight?view=panel",
                                 headers={"HX-Request": "true"}))
        assert 'id="h-ip-panel"' not in panel

    def test_devices_asks_for_its_in_progress_list_live(self, client):
        html = _text(client.get("/v2/devices"))
        assert ('id="ip-panel" hx-get="/operations/in_flight?view=panel" hx-trigger="load, '
                "nmas:in_progress from:body, nmas:device_holds from:body, nmas:device_progress "
                'from:body"') in html


# ── C1591 and C1595 ───────────────────────────────────────────────────────────────────────

class TestTheFingerprintAndLeaving:
    def test_console_servers_draws_the_whole_fingerprint_and_its_type(self, world, client,
                                                                      monkeypatch):
        world.set_port(driver="command_bridge", host="192.0.2.30", ssh_port=22,
                       container="edge-a", credential_ref="console-bridge", tcp_port=None)
        monkeypatch.setattr("modules.host_keys.held", lambda ip: {
            "type": "ssh-ed25519", "fingerprint": FINGERPRINT})
        html = _text(client.get("/v2/settings/installation?tab=console"))
        row = html.split(f'id="cs-port-{world.sport["id"]}"')[1].split("</tr>")[0]
        assert f'ssh-ed25519 <span class="fp" data-fingerprint>{FINGERPRINT}</span>' in row
        assert "…" not in row.split("data-fingerprint>")[1].split("</span>")[0]

    def test_the_console_card_running_says_leaving_is_safe(self):
        import app as nmas
        from flask import render_template
        c = {"step": "survey", "state": "running", "list_name": LIST, "device_id": 3,
             "hostname": "edge1", "run": "r", "job": "j", "steps": [], "add": False}
        with nmas.app.test_request_context("/"):
            html = render_template("v2/_console_ztp.html", c=c)
        assert '<strong>Safe to leave this page: the run continues.</strong>' in html
        assert "/v2/onboard/oob/run?list=" in html
