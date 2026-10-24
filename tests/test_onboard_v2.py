"""Onboarding on v2 (cutover blocker 3, 2026-10-10): Devices › Add device… and a pending
device's Verify…, Get the bootstrap config… and Abandon….

What is held here:
- every action is `routes/onboard.py`'s core, the one code path today's wizard and banner call;
- Create is bound to the review it confirms: the plan rebuilt under the hostname's hold is
  compared with the one reviewed, and a different one is refused NAMING what moved, with
  nothing created (today's Create rebuilds with no binding, CONCURRENCY_AUDIT R36);
- Abandon's preview is its dry run, and its confirm is bound to it: under the device's hold
  the dry run is taken again, and a different one refuses with nothing removed;
- the form sends every field the plan reads (domain included: today's wizard cannot), and
  nothing the plan ignores;
- the pages answer on v2 and send nobody to today's onboarding.
"""

import ast
import json
import os
import re
import types

import pytest

from tests.test_onboard_abandon import _onboard, repo  # noqa: F401  (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def client():
    import app as nmas

    return nmas.app.test_client()


@pytest.fixture
def person(monkeypatch):
    """A verified person at every gate the routes ask."""
    from modules import identity

    who = types.SimpleNamespace(actor="operator@example.invalid", kind="person",
                                peer="192.0.2.5", is_identified=True)
    monkeypatch.setattr(identity, "require", lambda *a, **k: (who, None))
    return who


def _plan(**over):
    """A plan as `build_plan` answers it: its summary, intent and config (no secret)."""
    summary = {"hostname": "r6", "platform": "cisco_iosxe", "list": "Default",
               "source_kind": "local", "mgmt_ip": "192.0.2.6", "mgmt_mask": "255.255.255.0",
               "address_source": "static", "manager_interface": "GigabitEthernet2",
               "role": "router", "blocking_reasons": [], "advisories": []}
    summary.update(over)
    return types.SimpleNamespace(
        summary=summary, host_vars={"hostname": "r6", "bootstrap": {"domain": "example.net"}},
        bootstrap_config="hostname r6\nend", onboardable=not summary["blocking_reasons"],
        blocking_reasons=summary["blocking_reasons"], hostname="r6",
        address_source="static", mgmt_ip=summary["mgmt_ip"], mgmt_mac="")


FORM = {"list_name": "Default", "hostname": "r6", "platform": "cisco-ios-xe", "role": "router",
        "address_source": "static", "mgmt_ip": "192.0.2.6", "mgmt_mask": "255.255.255.0",
        "manager_interface": "GigabitEthernet2", "domain": "example.net"}


class TestTheBinding:
    """`plan_moved`: what a Create bound to a review may run on."""

    def test_the_same_plan_passes(self):
        from modules.nsot.onboard import plan_fingerprint, plan_moved, plan_shown

        shown = plan_shown(_plan())
        assert plan_moved(shown, plan_fingerprint(shown), _plan()) == ""

    def test_a_moved_plan_is_refused_naming_both_values(self):
        from modules.nsot.onboard import plan_fingerprint, plan_moved, plan_shown

        shown = plan_shown(_plan())
        why = plan_moved(shown, plan_fingerprint(shown), _plan(mgmt_ip="192.0.2.7"))
        assert why.startswith("the plan moved since your preview")
        assert "summary.mgmt_ip: previewed '192.0.2.6', now '192.0.2.7'" in why, why

    def test_text_that_is_not_the_fingerprint_s_is_refused(self):
        """The fingerprint is the binding; the text rides along only to name what moved."""
        from modules.nsot.onboard import plan_fingerprint, plan_moved, plan_shown

        shown = plan_shown(_plan())
        forged = shown.replace("192.0.2.6", "192.0.2.7")
        assert "does not hash to its fingerprint" in plan_moved(
            forged, plan_fingerprint(shown), _plan(mgmt_ip="192.0.2.7"))

    def test_no_fingerprint_is_refused(self):
        from modules.nsot.onboard import plan_moved, plan_shown

        assert "no preview fingerprint" in plan_moved(plan_shown(_plan()), "", _plan())

    def test_the_secret_reaches_neither_side(self):
        """The review is built with a placeholder secret and Create with none: the binding
        must not see the difference, or every Create would be refused."""
        from modules.nsot.onboard import build_plan, plan_shown

        args = dict(hostname="r6", platform="cisco_iosxe", list_name="Default",
                    mgmt_ip="192.0.2.6", mgmt_mask="255.255.255.0",
                    manager_interface="GigabitEthernet2", domain="example.net", role="router",
                    ztp_check=lambda *a, **k: None, kea=None)
        # No skip (C1171, Lab 7's history audit): it once turned ANY exception from build_plan
        # into a skip, so a broken build_plan would have passed this secrecy check unseen.
        a = build_plan(secret="PLACEHOLDER-not-the-real-credential", **args)
        b = build_plan(secret="", **args)
        assert plan_shown(a) == plan_shown(b)
        assert "PLACEHOLDER" not in plan_shown(a)


class TestAddDevice:

    def test_devices_opens_add_device_on_v2(self, client):
        html = client.get("/v2/devices").get_data(as_text=True)
        m = re.search(r'<a class="btn" data-op="onboard" href="(/v2/onboard/new\?list=[^"]+)" '
                      r'hx-get="[^"]+" hx-target="#onboard-add"', html)
        assert m, "Add device… does not open v2's card"
        assert 'id="onboard-add"' in html and "Add device (today" not in html

    def test_the_form_carries_its_network_and_every_field(self, client):
        from modules import csp
        from routes.onboard_v2 import FIELDS

        r = client.get("/v2/onboard/new?list=Default")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert '<input type="hidden" name="list_name" value="Default">' in html
        sent = set(re.findall(r'\bname="([a-z_]+)"', html))
        assert set(FIELDS) <= sent, set(FIELDS) - sent
        assert 'hx-post="/v2/onboard/preview?list=Default"' in html

    def test_a_review_carries_the_binding_and_the_create(self, client, person, monkeypatch):
        from modules.nsot import onboard as O

        monkeypatch.setattr(O, "build_plan", lambda **k: _plan())
        html = client.post("/v2/onboard/preview", data=FORM).get_data(as_text=True)
        shown = O.plan_shown(_plan())
        assert f'name="fingerprint" value="{O.plan_fingerprint(shown)}"' in html
        assert 'name="shown" value="' in html and "Change the fields" in html
        assert "hostname r6" in html                           # the config it will boot
        assert 'hx-post="/v2/onboard/create?list=Default"' in html

    def test_a_clean_review_draws_the_create_button(self, client, person, monkeypatch):
        """C1148: the review drew its summary and Change the fields, never Create, because the
        template read `selectable` where the preview does not carry it. The form's action alone
        (above) cannot say a person can press anything."""
        from modules.nsot import onboard as O

        monkeypatch.setattr(O, "build_plan", lambda **k: _plan())
        html = client.post("/v2/onboard/preview", data=FORM).get_data(as_text=True)
        assert '<span class="op-idle">Create r6</span>' in html

    def test_a_blocked_review_draws_no_create_button(self, client, person, monkeypatch):
        """The control: a plan with a blocking reason is not selectable, so no Create."""
        from modules.nsot import onboard as O

        monkeypatch.setattr(O, "build_plan",
                            lambda **k: _plan(blocking_reasons=["192.0.2.6 is in use"]))
        html = client.post("/v2/onboard/preview", data=FORM).get_data(as_text=True)
        assert '<span class="op-idle">Create r6</span>' not in html

    def test_a_refused_review_says_why_and_keeps_the_fields(self, client):
        html = client.post("/v2/onboard/preview",
                           data=dict(FORM, list_name="")).get_data(as_text=True)
        assert "Not created:" in html and "no target list was sent" in html
        assert 'value="192.0.2.6"' in html

    def test_create_runs_on_the_plan_reviewed(self, client, person, monkeypatch, tmp_path):
        from modules.nsot import onboard as O

        ran = []
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        monkeypatch.setattr(O, "build_plan", lambda **k: _plan())
        monkeypatch.setattr(O, "real_steps", lambda repo, actor="": {})
        monkeypatch.setattr(O, "run_onboarding", lambda plan, repo, **k: ran.append(plan) or {
            "ok": True, "completed": ["credentials", "commit", "render"], "commit": "a" * 40})
        shown = O.plan_shown(_plan())
        r = client.post("/v2/onboard/create", data=dict(
            FORM, shown=shown, fingerprint=O.plan_fingerprint(shown)))
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and len(ran) == 1
        assert "PENDING" in html and "Open r6's page" in html

    def test_create_refuses_a_plan_that_moved_and_creates_nothing(self, client, person,
                                                                  monkeypatch, tmp_path):
        from modules.nsot import onboard as O

        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        monkeypatch.setattr(O, "build_plan", lambda **k: _plan(mgmt_ip="192.0.2.7"))
        monkeypatch.setattr(O, "run_onboarding",
                            lambda *a, **k: pytest.fail("created on a plan nobody reviewed"))
        shown = O.plan_shown(_plan())
        r = client.post("/v2/onboard/create", data=dict(
            FORM, shown=shown, fingerprint=O.plan_fingerprint(shown)))
        html = r.get_data(as_text=True)
        assert r.status_code == 409
        assert "Not created: the plan moved since your preview" in html
        assert "previewed &#39;192.0.2.6&#39;, now &#39;192.0.2.7&#39;" in html

    def test_create_with_no_fingerprint_is_refused(self, client, person, monkeypatch, tmp_path):
        from modules.nsot import onboard as O

        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        monkeypatch.setattr(O, "build_plan", lambda **k: _plan())
        monkeypatch.setattr(O, "run_onboarding", lambda *a, **k: pytest.fail("unbound"))
        r = client.post("/v2/onboard/create", data=FORM)
        assert r.status_code == 409 and "no preview fingerprint" in r.get_data(as_text=True)

    @pytest.mark.real_identity
    def test_create_needs_a_person(self, client):
        r = client.post("/v2/onboard/create", data=FORM)
        assert r.status_code in (401, 403)


class TestTheFormAndThePlanReadTheSameFields:
    """`_plan_args` and the v2 form, parsed: nothing read the form cannot send, nothing sent
    that is not read (today's check, tests/test_server_reads_nothing_the_form_cannot_send.py,
    holds the wizard; this holds v2's)."""

    @staticmethod
    def _server():
        from tests.test_server_reads_nothing_the_form_cannot_send import server_request_fields

        return server_request_fields("routes/onboard.py", "_plan_args")

    @staticmethod
    def _client():
        src = open(os.path.join(ROOT, "templates/v2/_onboard_add.html"), encoding="utf-8").read()
        form = src[src.index('class="set-form ob-form"'):]
        form = form[:form.index("</form>")]
        return set(re.findall(r'\bname="([a-z_]+)"', form))

    def test_the_floor(self):
        assert len(self._server()) >= 10 and len(self._client()) >= 10

    def test_nothing_read_that_the_form_cannot_send(self):
        # The source is the network's own; the secret is a parameter, minted at Create.
        assert self._server() - self._client() == {"source_kind"}

    def test_nothing_sent_that_is_not_read(self):
        assert self._client() - self._server() == {"list_name"}

    def test_the_route_names_the_form_s_fields(self):
        from routes.onboard_v2 import FIELDS

        assert set(FIELDS) == self._client()


class TestAPendingDevice:

    PENDING = {"identity": "uid:x", "name": "bp1", "mgmt_ip": "203.0.113.31",
               "address_source": "static", "onboarded_at": "2026-10-10T09:00:00Z",
               "age_seconds": 60, "state": "in_flight", "credential_findable": True}

    def test_the_page_draws_its_three_actions(self, client, monkeypatch):
        monkeypatch.setattr("modules.nsot.manifest.pending_devices",
                            lambda repo: [dict(self.PENDING)])
        html = client.get("/v2/device/bp1").get_data(as_text=True)
        assert 'id="pending-actions"' in html
        for route in ("verify/preview", "bootstrap", "abandon/preview"):
            assert f'hx-post="/v2/onboard/bp1/{route}?list=Default"' in html, route
        assert len(re.findall(r'<input type="hidden" name="list_name" value="[^"]+">',
                              html)) == 3

    def test_the_page_draws_today_s_banner_facts(self, client, monkeypatch):
        """Today's banner drew a ZTP device's stage and the last Verify or Abandon; the
        pending page draws both, read the same way, and says when the record is unreadable."""
        from modules.nsot import onboard as O

        row = dict(self.PENDING, address_source="ztp", mgmt_ip="",
                   mgmt_mac="aa:bb:cc:00:02:60", reserved_address="192.0.2.60")
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [dict(row)])
        monkeypatch.setattr("modules.nsot.ztp.progress", lambda entry, **_k: {
            "stage": "reserved_not_leased", "summary": "reserved; no lease yet"})
        monkeypatch.setattr(O, "read_runs", lambda repo: {"state": "ok", "error": "", "rows": [
            {"at": "2026-10-10T09:05:00Z", "kind": "verify", "device": "bp1",
             "actor": "operator@example.invalid", "ok": False, "mgmt_ip": "192.0.2.60",
             "steps": [{"step": "verify", "ok": False, "detail": "no answer"}],
             "verify": {"state": "did_not_answer", "error": "no answer", "causes": []}}]})
        html = client.get("/v2/device/bp1").get_data(as_text=True)
        assert "reserved not leased" in html and "reserved; no lease yet" in html
        assert "Last verify" in html and "bp1 did not answer at 192.0.2.60" in html
        monkeypatch.setattr(O, "read_runs", lambda repo: {"state": "unreadable",
                                                          "error": "bad line", "rows": []})
        html = client.get("/v2/device/bp1").get_data(as_text=True)
        assert "its record could not be read: bad line" in html

    def test_verify_s_preview_carries_its_fingerprint_to_the_confirm(self, client, monkeypatch):
        """C1150: the preview is `preview_confirm.build`'s own output, which carries
        `select_data` only under `what.targets`. The earlier mock put it under `targets`, a
        shape build() never returns, so the test passed while the real hand-off sent an empty
        fingerprint and every Verify was refused."""
        from modules import preview_confirm as P
        from routes import onboard

        pv = P.build(action="verify", summary="Verify bp1: it answered.",
                     targets=[{"name": "bp1", "state": "ready", "selectable": True,
                               "select_data": {"fingerprint": "f" * 64},
                               "program": {"lines": ["no snmp-server community"]},
                               "operands": [{"name": "address", "value": "192.0.2.9"}],
                               "gates": [P.gate("reached", "pass", "it answered")]}],
                     what_not=[], nothing_left_out="Nothing left out.",
                     confirm={"may": True, "statement": "You are confirming as x."})
        assert "select_data" not in pv["targets"][0]       # the shape the route must read
        monkeypatch.setattr(onboard, "verify_preview_of",
                            lambda name, data, req: ({"ok": True, "preview": pv}, 200))
        html = client.post("/v2/onboard/bp1/verify/preview",
                           data={"list_name": "probe"}).get_data(as_text=True)
        assert f'name="fingerprint" value="{"f" * 64}"' in html
        assert 'hx-post="/v2/onboard/bp1/verify?list=Default"' in html and "Verify bp1" in html

    def test_verify_s_preview_refused_names_the_causes(self, client, monkeypatch):
        from routes import onboard

        monkeypatch.setattr(onboard, "verify_preview_of", lambda name, data, req: (
            {"ok": False, "error": "bp1 did not answer at 203.0.113.31",
             "causes": [{"text": "it has not booted"}]}, 409))
        r = client.post("/v2/onboard/bp1/verify/preview", data={"list_name": "probe"})
        html = r.get_data(as_text=True)
        assert r.status_code == 409 and "Not verified:" in html
        assert "did not answer" in html and "it has not booted" in html

    def test_verify_confirms_through_the_core(self, client, person, monkeypatch):
        from routes import onboard

        seen = []
        monkeypatch.setattr(onboard, "verify_run", lambda name, data, ident: seen.append(
            (name, data.get("fingerprint"), ident.actor)) or ({"ok": True, "result": {
                "level": "success", "happened": {"summary": "bp1 is onboarded"},
                "did_not": {"items": []}}}, 200))
        html = client.post("/v2/onboard/bp1/verify", data={
            "list_name": "probe", "fingerprint": "f" * 64}).get_data(as_text=True)
        assert seen == [("bp1", "f" * 64, "operator@example.invalid")]
        assert "bp1 is onboarded" in html and "Open bp1&#39;s page" in html
        assert "data-run-stepper" not in html, "no steps recorded: none drawn"

    def test_verify_draws_the_steps_it_reached_on_the_one_stepper(self, client, person,
                                                                  monkeypatch):
        """The one stepper (2026-10-12): phase two's steps from its own result, the one it
        stopped at failed with its reason, the rest not reached."""
        from modules.nsot.onboard import PHASE_TWO_STEPS
        from routes import onboard

        ran = [{"step": "verify", "ok": True, "detail": "answered"},
               {"step": "capture", "ok": True, "detail": ""},
               {"step": "rotate", "ok": False, "detail": "the new secret did not log in"}]
        ran += [{"step": s, "ok": False, "detail": "did not run"} for s in PHASE_TWO_STEPS[3:]]
        monkeypatch.setattr(onboard, "verify_run", lambda name, data, ident: ({
            "ok": False, "steps": ran, "stopped_at": "rotate", "reason": "rotation refused",
            "result": {"level": "failed", "happened": {"summary": "bp1 is still pending"},
                       "did_not": {"items": []}}}, 200))
        html = client.post("/v2/onboard/bp1/verify", data={
            "list_name": "probe", "fingerprint": "f" * 64}).get_data(as_text=True)
        got = re.findall(r'<li class="run-step run-step-([a-z_]+)" data-step="([a-z_]+)"'
                         r'(?: title="([^"]*)")?', html)
        assert [(k, s) for s, k, _t in got] == [
            ("verify", "done"), ("capture", "done"), ("rotate", "failed")] + [
            (k, "not_reached") for k in PHASE_TWO_STEPS[3:]]
        assert got[2][2] == "the new secret did not log in"
        assert "bp1 is still pending" in html


class TestAbandon:

    def test_the_preview_is_the_dry_run_and_removes_nothing(self, client, repo, monkeypatch):
        from modules.nsot import manifest
        from modules.nsot.onboard import abandon_fingerprint

        _onboard(repo)
        monkeypatch.setattr("modules.netbox_client.remove_device_from_netbox",
                            lambda *a, **k: {"ok": True, "deleted": [], "skipped": [],
                                             "message": "dry"})
        r = client.post("/v2/onboard/bp1/abandon/preview", data={"list_name": "probe"})
        html = r.get_data(as_text=True)
        assert r.status_code == 200, html
        assert "intent: would remove host_vars/bp1.yml" in html
        assert manifest.find_by_name(repo, "bp1")[0], "a preview released the name"
        fps = re.findall(r'name="fingerprint" value="([0-9a-f]{64})"', html)
        assert len(fps) == 1
        assert 'hx-post="/v2/onboard/bp1/abandon?list=Default"' in html
        assert abandon_fingerprint  # imported: the value is checked against the run below

    def test_the_confirm_runs_what_was_shown(self, client, repo, person, monkeypatch):
        from modules.nsot import manifest

        _onboard(repo)
        monkeypatch.setattr("modules.netbox_client.remove_device_from_netbox",
                            lambda *a, **k: {"ok": True, "deleted": [], "skipped": [],
                                             "message": "none"})
        pv = client.post("/v2/onboard/bp1/abandon/preview",
                         data={"list_name": "probe"}).get_data(as_text=True)
        fp = re.search(r'name="fingerprint" value="([0-9a-f]{64})"', pv).group(1)
        r = client.post("/v2/onboard/bp1/abandon", data={"list_name": "probe",
                                                         "fingerprint": fp})
        html = r.get_data(as_text=True)
        assert r.status_code == 200, html
        assert "is abandoned" in html and "Back to Devices" in html
        assert not manifest.find_by_name(repo, "bp1")[0]

    def test_a_dry_run_that_moved_is_refused_and_removes_nothing(self, client, repo, person,
                                                                 monkeypatch):
        """Shown with NetBox holding nothing; at the confirm NetBox holds an object. The plan
        moved, so nothing is removed and both are named. The device has the NetBox id Verify
        records, so Abandon asks the remover (C1597: an onboarding with none made nothing
        there)."""
        from modules.nsot import manifest
        from tests.test_onboard_abandon import VERIFIED_NB_ID

        _onboard(repo, netbox_id=VERIFIED_NB_ID)
        held = {"deleted": []}
        monkeypatch.setattr("modules.netbox_client.remove_device_from_netbox",
                            lambda *a, **k: {"ok": True, "deleted": list(held["deleted"]),
                                             "skipped": [], "message": ""})
        pv = client.post("/v2/onboard/bp1/abandon/preview",
                         data={"list_name": "probe"}).get_data(as_text=True)
        fp = re.search(r'name="fingerprint" value="([0-9a-f]{64})"', pv).group(1)
        held["deleted"] = ["dcim.device 7"]
        r = client.post("/v2/onboard/bp1/abandon", data={"list_name": "probe",
                                                         "fingerprint": fp})
        html = r.get_data(as_text=True)
        assert r.status_code == 409, html
        assert "Not abandoned: what Abandon would do moved since your preview" in html
        assert f"previewed {fp[:12]}" in html and "1 object(s) removed" in html
        assert "Nothing was removed" in html
        assert manifest.find_by_name(repo, "bp1")[0], "removed on a plan nobody was shown"
        assert os.path.exists(os.path.join(repo, "host_vars", "bp1.yml"))

    def test_the_fingerprint_binds_every_part_of_the_dry_run(self):
        """Lab 7 (b)'s mutation sample (2026-10-17): the Abandon fingerprint ignoring a
        step's NAME, a step's ok, whether the dry run finishes, or its error survived every
        test, since the route tests move a step's detail alone. Each part, changed alone, must
        move the fingerprint the confirm is bound to: "would remove the reservation: ok" and
        "...: fails" are two different things to have been shown."""
        from modules.nsot.onboard import abandon_fingerprint

        base = {"ok": True, "error": "",
                "steps": [{"step": "intent", "ok": True, "detail": "would remove it"},
                          {"step": "reservation", "ok": True, "detail": "would release it"}]}

        def moved(**change):
            dry = json.loads(json.dumps(base))
            step = change.pop("step", None)
            if step:
                dry["steps"][1].update(step)
            dry.update(change)
            return abandon_fingerprint(dry)

        was = abandon_fingerprint(base)
        assert moved(step={"step": "netbox"}) != was, "a step's name is not bound"
        assert moved(step={"ok": False}) != was, "a step's ok is not bound"
        assert moved(step={"detail": "would keep it"}) != was, "a step's words are not bound"
        assert moved(ok=False) != was, "whether it finishes is not bound"
        assert moved(error="NetBox could not be read") != was, "its error is not bound"

    def test_an_unbound_confirm_is_refused(self, client, person):
        r = client.post("/v2/onboard/bp1/abandon", data={"list_name": "probe"})
        assert r.status_code == 400 and "no preview fingerprint" in r.get_data(as_text=True)


class TestTheBootstrapReveal:

    def test_it_reveals_through_the_core_to_a_person(self, client, monkeypatch):
        from routes import onboard

        monkeypatch.setattr(onboard, "bootstrap_reveal", lambda name, data, req: (
            {"ok": True, "config": "hostname bp1\nend", "revealed_by": "a@b"}, 200))
        html = client.post("/v2/onboard/bp1/bootstrap",
                           data={"list_name": "probe"}).get_data(as_text=True)
        assert "hostname bp1" in html and "Revealed to a@b and recorded" in html

    @pytest.mark.real_identity
    def test_a_refused_reveal_shows_no_config(self, client, repo):
        _onboard(repo)
        r = client.post("/v2/onboard/bp1/bootstrap", data={"list_name": "probe"})
        html = r.get_data(as_text=True)
        assert r.status_code in (401, 403) and "<pre" not in html

    def test_the_route_is_the_core_s(self):
        """Parsed: v2's reveal calls the one reveal, which gates and records."""
        from tests.astcheck import calls_in

        from routes import onboard, onboard_v2

        assert calls_in(onboard_v2.bootstrap, "bootstrap_reveal") == 1
        src = ast.unparse(ast.parse(open(onboard.__file__, encoding="utf-8").read()))
        assert "reveal_audit.record(" in src


class TestOneCodePath:

    def test_each_v2_action_calls_the_one_core(self):
        """Today's routes, which called the same cores, left at 7.8 (2026-10-17, P7-25): v2's
        actions are the cores' only callers, and routes/onboard.py serves no route."""
        from tests.astcheck import calls_in

        from routes import onboard as core, onboard_v2 as v2

        assert calls_in(v2.preview, "plan_of") == 1
        assert calls_in(v2.create, "create_run") == 1
        assert calls_in(v2.verify, "verify_run") == 1
        assert calls_in(v2.abandon, "abandon_run") == 1
        assert calls_in(v2.verify_preview, "verify_preview_of") == 1
        assert not hasattr(core, "bp")


class TestTheCoresBindEveryConfirm:
    """Today's wizard created and abandoned unbound (CONCURRENCY_AUDIT R36, confirms-11 and
    -12); with it gone the cores bind every confirm, so no caller can send an unbound one."""

    def test_a_create_without_its_preview_is_refused_creating_nothing(self, monkeypatch,
                                                                      tmp_path):
        from modules.nsot import onboard as O
        from routes import onboard

        ran = []
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        monkeypatch.setattr(O, "build_plan", lambda **k: _plan())
        monkeypatch.setattr(O, "real_steps", lambda repo, actor="": {})
        monkeypatch.setattr(O, "run_onboarding",
                            lambda *a, **k: ran.append(1) or {"ok": True, "completed": []})
        out, status = onboard.create_run(dict(FORM), "<operator>")
        assert status == 409 and out.get("moved") and "preview first" in out["error"], out
        assert ran == []

    def test_an_abandon_without_its_dry_run_is_refused_removing_nothing(self, monkeypatch,
                                                                        tmp_path):
        from modules.nsot import onboard as O
        from routes import onboard

        ran = []
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        monkeypatch.setattr(O, "abandon_onboarding",
                            lambda *a, **k: ran.append(k) or {"ok": True, "steps": [],
                                                              "moved": True})
        out, status = onboard.abandon_run("bp1", {"list_name": "probe"}, "<operator>")
        assert status == 400 and "preview first" in out["error"], out
        assert ran == []
        onboard.abandon_run("bp1", {"list_name": "probe", "dry_run": "1"}, "<operator>")
        assert ran and ran[0]["dry_run"] is True


def test_the_binding_is_canonical_json():
    """`plan_shown` is sorted JSON, so the same plan is the same text in any process."""
    from modules.nsot.onboard import plan_shown

    assert json.loads(plan_shown(_plan()))["summary"]["mgmt_ip"] == "192.0.2.6"
    assert plan_shown(_plan()) == plan_shown(_plan())


class TestCreateDrawsWhatItCreated:
    """C1149: Create's result names what it wrote, each on no device, and its record (W4 step
    9 reads these lines). v2's card drew only the summary and what did not happen; today's
    wizard drew the result component's created lines and record statement."""

    def test_the_created_lines_and_the_record_are_drawn(self, client, person, monkeypatch,
                                                        tmp_path):
        from modules.nsot import onboard as O

        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        monkeypatch.setattr(O, "build_plan", lambda **k: _plan())
        monkeypatch.setattr(O, "real_steps", lambda repo, actor="": {})
        monkeypatch.setattr(O, "run_onboarding", lambda plan, repo, **k: {
            "ok": True, "completed": ["credentials", "commit", "render"], "commit": "a" * 40})
        shown = O.plan_shown(_plan())
        r = client.post("/v2/onboard/create", data=dict(
            FORM, shown=shown, fingerprint=O.plan_fingerprint(shown)))
        html = " ".join(r.get_data(as_text=True).split())
        assert r.status_code == 200 and "PENDING" in html
        created = re.search(r"What was created \(on no device\)</h3> "
                            r'<ul class="mono small" data-onboard-created>(.*?)</ul>', html)
        assert created, html[-1500:]
        lines = re.findall(r"<li>(.*?)</li>", created.group(1))
        assert [l.split(":")[0] for l in lines] == ["credentials", "commit", "render"], lines
        assert "(aaaaaaaaaaaa)" in lines[1]
        assert "Commit aaaaaaaaaaaa records r6 as pending." in html
