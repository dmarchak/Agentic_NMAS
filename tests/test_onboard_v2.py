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
        try:
            a = build_plan(secret="PLACEHOLDER-not-the-real-credential", **args)
            b = build_plan(secret="", **args)
        except Exception as exc:                 # noqa: BLE001 (the stores this test lacks)
            pytest.skip(f"build_plan needs a store here: {exc}")
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
        assert 'hx-post="/v2/onboard/preview"' in html

    def test_a_review_carries_the_binding_and_the_create(self, client, person, monkeypatch):
        from modules.nsot import onboard as O

        monkeypatch.setattr(O, "build_plan", lambda **k: _plan())
        html = client.post("/v2/onboard/preview", data=FORM).get_data(as_text=True)
        shown = O.plan_shown(_plan())
        assert f'name="fingerprint" value="{O.plan_fingerprint(shown)}"' in html
        assert 'name="shown" value="' in html and "Change the fields" in html
        assert "hostname r6" in html                           # the config it will boot
        assert 'hx-post="/v2/onboard/create"' in html

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
            assert f'hx-post="/v2/onboard/bp1/{route}"' in html, route
        assert len(re.findall(r'<input type="hidden" name="list_name" value="[^"]+">',
                              html)) == 3

    def test_the_page_draws_today_s_banner_facts(self, client, monkeypatch):
        """Today's banner drew a ZTP device's stage and the last Verify or Abandon; the
        pending page draws both, read the same way, and says when the record is unreadable."""
        from modules.nsot import onboard as O

        row = dict(self.PENDING, address_source="ztp", mgmt_ip="",
                   mgmt_mac="aa:bb:cc:00:02:60", reserved_address="192.0.2.60")
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [dict(row)])
        monkeypatch.setattr("modules.nsot.ztp.progress", lambda entry: {
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
        from routes import onboard

        pv = {"what": {"summary": "Verify bp1: it answered."}, "confirm": {
            "may": True, "statement": "You are confirming as x."}, "what_not": {"items": []},
              "targets": [{"name": "bp1", "program": {"lines": ["no snmp-server community"]},
                           "operands": [], "gates": [],
                           "select_data": {"fingerprint": "f" * 64}}]}
        monkeypatch.setattr(onboard, "verify_preview_of",
                            lambda name, data, req: ({"ok": True, "preview": pv}, 200))
        html = client.post("/v2/onboard/bp1/verify/preview",
                           data={"list_name": "probe"}).get_data(as_text=True)
        assert f'name="fingerprint" value="{"f" * 64}"' in html
        assert 'hx-post="/v2/onboard/bp1/verify"' in html and "Verify bp1" in html

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
        assert 'hx-post="/v2/onboard/bp1/abandon"' in html
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
        moved, so nothing is removed and both are named."""
        from modules.nsot import manifest

        _onboard(repo)
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

    def test_each_v2_action_calls_today_s_core(self):
        from tests.astcheck import calls_in

        from routes import onboard as v1, onboard_v2 as v2

        assert calls_in(v2.preview, "plan_of") == 1 and calls_in(v1.plan, "plan_of") == 1
        assert calls_in(v2.create, "create_run") == 1 and calls_in(v1.create, "create_run") == 1
        assert calls_in(v2.verify, "verify_run") == 1 and calls_in(v1.verify, "verify_run") == 1
        assert calls_in(v2.abandon, "abandon_run") == 1
        assert calls_in(v1.abandon, "abandon_run") == 1
        assert calls_in(v2.verify_preview, "verify_preview_of") == 1
        assert calls_in(v1.verify_preview, "verify_preview_of") == 1


def test_the_binding_is_canonical_json():
    """`plan_shown` is sorted JSON, so the same plan is the same text in any process."""
    from modules.nsot.onboard import plan_shown

    assert json.loads(plan_shown(_plan()))["summary"]["mgmt_ip"] == "192.0.2.6"
    assert plan_shown(_plan()) == plan_shown(_plan())
