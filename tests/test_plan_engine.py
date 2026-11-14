"""The plan engine (modules/plan_engine.py; routes/plans_v2.py; the toolbar assistant's v2
answer): a plan of Mercury's operations previewed together, approved once by its hash, run in
order, each step through its own operation, the first that does not pass stopping it, nothing
retried.

On the operations' own test kits and real data:
- **the DHCP reservation:** tests/test_dhcp_reservations.py's Kea (the lab's real Kea answers,
  tests/fixtures/kea/), its files and its stand-ins for Kea's own check and the record;
- **the intent description:** tests/test_committed_before_p1.py's `host` (the host's real
  committed documents: s1 and r2 in the network Lab).
"""
import json

import pytest

from modules import dhcp_reservations as D
from modules import plan_engine as E
from tests.test_committed_before_p1 import host  # noqa: F401 (the fixture)
from tests.test_dhcp_reservations import FakeKea, kea_dir  # noqa: F401 (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `kea` builds on)

PERSON = "person@example.invalid"
REASON = "the printer needs a fixed address"
RES = {"mac": "aa:c1:ab:5d:20:9e", "address": "10.10.20.150", "hostname": "h5", "subnet": "20"}
LINK = {"device_a": "s1", "interface_a": "Gi0/1", "device_b": "r2",
        "interface_b": "GigabitEthernet1", "description": "s1 to r2"}


@pytest.fixture
def kea(kea_dir, networks, monkeypatch):  # noqa: F811
    """The reservation's own plan and apply on the lab's Kea, its own check passing and its
    record kept here; the network (Default, registered) owns its Kea."""
    k = FakeKea(kea_dir["files"])
    real_plan, real_apply, recorded = D.plan, D.apply, []
    monkeypatch.setattr(D, "plan", lambda ln, v, **kw: real_plan(ln, v, kea=k))
    monkeypatch.setattr(D, "apply", lambda ln, v, h, **kw: real_apply(
        ln, v, h, kea=k, run_test=lambda path: (True, "ok"),
        record=lambda ln_, p, actor, reason: recorded.append((p["subject"], actor, reason))
        or {"ok": True, "commit": "abc1234"}, **kw))
    monkeypatch.setattr("modules.list_settings.kea_owner", lambda ln: (ln, "set"))
    k.recorded, k.dir = recorded, kea_dir
    return k


def approve(plan, params, h=None, **over):
    network = "Default" if plan == "dhcp-reservation" else "Lab"
    kw = dict(actor=PERSON, actor_verified="access", person=True, reason=REASON)
    kw.update(over)
    p = E.preview(network, plan, params)
    return E.run(network, plan, params, p["hash"] if h is None else h, **kw)


# ── The schema: a plan Mercury has, exactly its parameters, each of its shape ───────────────

class TestTheSchema:
    @pytest.mark.parametrize("plan, params, code, words", [
        ("reload-everything", {}, "not_a_plan",
         "a plan is one of Mercury's (add-ztp-device, describe-link and dhcp-reservation)"),
        ("dhcp-reservation", dict(RES, commands="reload"), "unknown_parameter",
         "also given: a parameter the schema does not name is refused"),
        ("dhcp-reservation", {k: v for k, v in RES.items() if k != "mac"}, "missing_parameter",
         "no mac was given"),
        ("dhcp-reservation", dict(RES, mac="AA-C1-AB-5D-20-9E"), "wrong_shape",
         "parameter mac is a MAC address"),
        ("dhcp-reservation", dict(RES, address="10.10.20.999"), "wrong_shape",
         "parameter address is one IPv4 or IPv6 address"),
        ("describe-link", dict(LINK, device_b="s1"), "same_device",
         "both ends given are s1's"),
        ("describe-link", dict(LINK, description="x" * 241), "wrong_shape",
         "parameter description is 1 to 240"),
    ])
    def test_anything_else_is_refused_naming_what_it_compared(self, plan, params, code, words):
        got = E.preview("Lab", plan, params)
        assert (got["ok"], got["code"], got["hash"]) == (False, code, ""), got
        assert words in got["refused"], got["refused"]


# ── A one-step plan: the DHCP reservation ───────────────────────────────────────────────────

class TestTheReservationPlan:
    def test_its_preview_is_the_reservations_own_and_writes_nothing(self, kea):
        got = E.preview("Default", "dhcp-reservation", RES)
        assert got["ok"], got["refused"]
        (step,) = got["steps"]
        assert step["kind"] == "dhcp-reservation" and step["hash"] == D.plan("Default", {
            "op": "add", "family": "IPv4", "subnet": "20", "key": "hw-address",
            "identity": RES["mac"], "address": RES["address"], "hostname": "h5"})["hash"]
        assert got["title"] == "Reserve 10.10.20.150 for h5 (aa:c1:ab:5d:20:9e)"
        assert open(kea.dir["files"][("dhcp4", 20)], encoding="utf-8").read() == "[]\n"
        assert ("config-reload", "dhcp4") not in kea.sent

    def test_an_ipv6_reservation_beside_the_ipv4_one(self, kea):
        got = E.preview("Default", "dhcp-reservation", dict(RES, address="2001:db8:10::150",
                                                        subnet="10"))
        (step,) = got["steps"]
        # The family is the address's: the IPv6 subnet 10's own preview answers.
        assert got["ok"], step["refused"]

    def test_approved_it_runs_its_own_apply_verify_and_record(self, kea):
        rec = approve("dhcp-reservation", RES)
        assert (rec["outcome"], rec["state"]) == ("done", "done"), rec["why"]
        (s,) = rec["plan_steps"]
        assert s["state"] == "done" and s["receipt"]["commit"] == "abc1234"
        with open(kea.dir["files"][("dhcp4", 20)], encoding="utf-8") as fh:
            assert json.load(fh) == [{"hw-address": RES["mac"], "ip-address": RES["address"],
                                      "hostname": "h5"}]
        assert kea.recorded == [("dhcp: h5 reserved 10.10.20.150 by MAC aa:c1:ab:5d:20:9e",
                                 PERSON, REASON)]
        from modules.nsot import privileged
        kept = privileged.get("Default", rec["id"])
        assert kept["key"] == "plan" and kept["hash"] == rec["hash"]
        assert [x["step"] for x in kept["steps"]] == ["approve", "step-1", "record"]

    @pytest.mark.parametrize("over, words", [
        ({"h": "0" * 16}, "you approved 0000000000000000, and the plan previewed now is"),
        ({"h": ""}, "you approved no hash"),
        ({"person": False}, "approved by a verified person"),
        ({"actor_verified": "none"}, "approved by a verified person"),
        ({"reason": "ok"}, "a reason of at least three words"),
    ])
    def test_without_the_hash_a_person_or_a_reason_nothing_runs(self, kea, over, words):
        rec = approve("dhcp-reservation", RES, **over)
        assert rec["outcome"] == "refused" and words in rec["why"], rec["why"]
        assert open(kea.dir["files"][("dhcp4", 20)], encoding="utf-8").read() == "[]\n"
        assert kea.recorded == []

    def test_a_network_using_anothers_kea_is_refused_by_name(self, kea, monkeypatch):
        monkeypatch.setattr("modules.list_settings.kea_owner", lambda ln: ("Core", "set"))
        got = E.preview("Default", "dhcp-reservation", RES)
        assert not got["ok"] and "Default uses Core's Kea (set)" in got["refused"]


# ── A two-step plan: a link described at both ends ──────────────────────────────────────────

def _head(host):  # noqa: F811
    from tests.test_intent_patch import _git
    return _git(host["repo"], "rev-parse", "HEAD").strip()


class TestTheLinkPlan:
    def test_both_ends_are_previewed_and_committed_in_order(self, host):  # noqa: F811
        from tests.test_intent_patch import _git
        got = E.preview("Lab", "describe-link", LINK)
        assert got["ok"], got["refused"]
        assert [s["params"]["device"] for s in got["steps"]] == ["s1", "r2"]
        before = _head(host)
        rec = approve("describe-link", LINK)
        assert rec["outcome"] == "done", rec["why"]
        log = _git(host["repo"], "log", "--format=%s", f"{before}..HEAD").splitlines()
        assert len(log) == 2 and log[0].startswith("host_vars: r2") and \
            log[1].startswith("host_vars: s1"), log
        for dev in ("s1", "r2"):
            assert "s1 to r2" in _git(host["repo"], "show", f"HEAD:host_vars/{dev}.yml")

    def test_the_first_step_that_does_not_pass_stops_the_plan(self, host,  # noqa: F811
                                                              monkeypatch):
        from modules.nsot import intent_patch
        calls, real = [], intent_patch.commit

        def commit(network, device, *a, **kw):
            calls.append(device)
            if device == "s1":
                return {"ok": False, "status": 409, "stage": "render",
                        "error": "the render refused it (a test's own words)"}
            return real(network, device, *a, **kw)
        monkeypatch.setattr(intent_patch, "commit", commit)
        before = _head(host)
        rec = approve("describe-link", LINK)
        assert rec["outcome"] == "stopped" and rec["state"] == "failed", rec
        assert "step 1 (Set an interface's description in a device's intent) did not pass" in \
            rec["why"] and "No later step ran, and nothing is retried" in rec["why"]
        assert [s["state"] for s in rec["plan_steps"]] == ["failed", "not_run"]
        assert calls == ["s1"], "once, and never r2's"
        assert _head(host) == before

    def test_a_plan_moved_since_its_preview_runs_nothing(self, host):  # noqa: F811
        from modules.nsot import intent_edit
        p = E.preview("Lab", "describe-link", LINK)
        opened = intent_edit.open_doc("Lab", "r2")
        assert intent_edit.commit("Lab", "r2", opened["yaml"].replace(
            "domain_name: example.com", "domain_name: example.org"), "another person's edit",
            opened["base"], "someone")["ok"]
        before = _head(host)
        rec = E.run("Lab", "describe-link", LINK, p["hash"], actor=PERSON,
                    actor_verified="access", person=True, reason=REASON)
        assert rec["outcome"] == "refused" and "the plan is not the one approved" in rec["why"]
        assert _head(host) == before


# ── Tier 3: add a device by ZTP (Add device's Create; Verify stays its own approval) ────────

ZTP = {"hostname": "edge9", "platform": "cisco-ios-xe", "role": "router",
       "mac": "aa:c1:ab:5d:20:9e", "address": "192.0.2.60", "domain": "example.net"}


@pytest.fixture
def ztp(networks, monkeypatch):  # noqa: F811
    """Add device's own plan stood in as tests/test_onboard_v2.py stands it in (`_plan`: a plan
    as `build_plan` answers it, the ZTP form's), and Create's steps recorded, none real; the
    plan's answers in turn (`answers`), the last kept."""
    from modules.nsot import onboard
    from tests.test_onboard_v2 import _plan

    world = {"answers": [], "built": [], "ran": [],
             "result": {"ok": True, "steps": ["credentials", "commit", "reserve", "render"]}}

    def build_plan(**kw):
        world["built"].append(kw)
        made = (world["answers"] or [{}])[min(len(world["built"]) - 1,
                                              max(0, len(world["answers"]) - 1))]
        return _plan(hostname=kw["hostname"], address_source="ztp", mgmt_ip="",
                     mgmt_mask="", reservation_address=kw.get("mgmt_ip") or "",
                     reservation_state="to_write", **made)
    monkeypatch.setattr(onboard, "build_plan", build_plan)
    monkeypatch.setattr(onboard, "real_steps", lambda repo, actor: {
        "bind_credentials": None, "commit": None, "render": None, "reserve": None})
    monkeypatch.setattr(onboard, "run_onboarding", lambda plan, **kw: world["ran"].append(
        plan.summary["hostname"]) or dict(world["result"]))
    return world


class TestTheZtpPlan:
    def test_its_preview_is_add_devices_own_with_no_credential(self, ztp):
        from modules.nsot.onboard import plan_fingerprint, plan_shown
        from tests.test_onboard_v2 import _plan
        got = E.preview("Default", "add-ztp-device", ZTP)
        assert got["ok"], got["refused"]
        (step,) = got["steps"]
        assert step["kind"] == "ztp-create"
        assert step["hash"] == plan_fingerprint(plan_shown(_plan(
            hostname="edge9", address_source="ztp", mgmt_ip="", mgmt_mask="",
            reservation_address="192.0.2.60", reservation_state="to_write")))
        assert E.ZTP_LATER in step["drawn"]["not_done"] and E.ZTP_SECRET in \
            step["drawn"]["not_done"]
        assert "PLACEHOLDER" not in json.dumps(got) and "shown" not in step
        (kw,) = ztp["built"]
        assert kw["secret"] == "PLACEHOLDER-not-the-real-credential"
        assert (kw["mgmt_ip"], kw["mgmt_mac"], kw["address_source"], kw["list_name"]) == (
            "192.0.2.60", "aa:c1:ab:5d:20:9e", "ztp", "Default")
        assert ztp["ran"] == [], "a preview creates nothing"

    def test_a_plan_add_device_refuses_is_refused_naming_why(self, ztp):
        ztp["answers"] = [{"blocking_reasons": ["the MAC is already reserved for r7"]}]
        got = E.preview("Default", "add-ztp-device", ZTP)
        assert not got["ok"] and "the MAC is already reserved for r7" in got["refused"]

    def test_approved_create_runs_once_and_the_device_is_pending(self, ztp):
        rec = E.run("Default", "add-ztp-device", ZTP,
                    E.preview("Default", "add-ztp-device", ZTP)["hash"], actor=PERSON,
                    actor_verified="access", person=True, reason="a new edge router")
        # Created and pending: never green, Verify its own approval (the step kind's words).
        assert (rec["outcome"], rec["state"]) == ("partial", "unverified"), rec["why"]
        assert rec["why"].endswith("created and pending: Verify is its own approval")
        (s,) = rec["plan_steps"]
        assert s["state"] == "done" and "edge9 created and pending" in s["words_said"]
        assert E.ZTP_LATER in s["words_said"]

    def test_a_create_that_stops_stops_the_plan(self, ztp):
        ztp["result"] = {"ok": False, "failed_at": "reserve",
                         "reason": "Kea refused the reservation (a test's own words)"}
        rec = E.run("Default", "add-ztp-device", ZTP,
                    E.preview("Default", "add-ztp-device", ZTP)["hash"], actor=PERSON,
                    actor_verified="access", person=True, reason="a new edge router")
        assert rec["outcome"] == "stopped" and "Kea refused the reservation" in rec["why"]
        assert rec["plan_steps"][0]["receipt"]["failed_at"] == "reserve"

    def test_a_plan_that_moved_creates_nothing(self, ztp):
        h = E.preview("Default", "add-ztp-device", ZTP)["hash"]
        ztp["answers"] = [{}, {"role": "switch"}]
        ztp["built"].clear()
        rec = E.run("Default", "add-ztp-device", ZTP, h, actor=PERSON,
                    actor_verified="access", person=True, reason="a new edge router")
        # Approved on the first answer; Create's own plan moved before it ran: it stops there.
        assert rec["outcome"] == "stopped" and rec["plan_steps"][0]["state"] == "refused"
        assert "is not the one approved" in rec["why"] or "moved" in rec["why"]
        assert ztp["ran"] == []

    @pytest.mark.parametrize("address", ["192.0.2.60", "2001:db8:60::60"])
    def test_its_schema_takes_either_family_and_add_device_judges_it(self, ztp, address):
        got = E.preview("Default", "add-ztp-device", dict(ZTP, address=address))
        assert got["ok"] and ztp["built"][-1]["mgmt_ip"] == address

    def test_its_form_is_add_devices_own_mapping_with_its_inventory_source(self, ztp,
                                                                         monkeypatch):
        """One home for Add device's form (`routes.onboard_v2.form_of`): the plan's values go
        through it, the network's inventory source included, and no DHCP relay."""
        monkeypatch.setattr("routes.onboard_v2._source_kind", lambda list_name: "netbox")
        data = E._ztp_data("Default", ZTP)
        assert data["source_kind"] == "netbox" and data["ztp_router"] == ""
        assert data["address_source"] == "ztp" and data["mgmt_ip"] == "192.0.2.60"
        assert "ztp_router" not in {p.name for p in E.ZTP_PARAMS}

    def test_no_plan_takes_a_secret(self):
        """The one-time credential is Mercury's: no plan's parameter can carry a secret, and the
        bootstrap reveal is no step (its endpoint is no step kind's)."""
        names = {p.name for plan in E.PLANS.values() for p in plan.params} | {
            p.name for k in E.STEP_KINDS.values() for p in k.params}
        assert not {n for n in names if any(w in n for w in (
            "secret", "password", "credential", "key", "token", "community"))}, names
        assert "onboard_v2.bootstrap" not in {k.by_hand for k in E.STEP_KINDS.values()}


# ── The review's fixes (Tier 2's review, 2026-11-14) ────────────────────────────────────────

class TestTheReviewsFixes:
    def test_a_preview_on_one_network_is_refused_on_another(self, kea):
        p = E.preview("Default", "dhcp-reservation", RES)
        other = E.plan_hash(p["plan"], p["params"], p["steps"], "Lab")
        assert other != p["hash"] and p["network"] == "Default"
        rec = E.run("Default", "dhcp-reservation", RES, other, actor=PERSON,
                    actor_verified="access", person=True, reason=REASON)
        assert rec["outcome"] == "refused" and kea.recorded == []

    def test_a_wrong_shaped_value_is_never_echoed(self):
        got = E.preview("Lab", "dhcp-reservation", dict(RES, mac="secret-hunter2-AA"))
        assert got["code"] == "wrong_shape" and "hunter2" not in got["refused"]
        assert "parameter mac is a MAC address" in got["refused"]

    def test_a_description_that_reads_as_a_secret_is_refused(self, host):  # noqa: F811
        from modules.redact import redact_text
        secretish = "password Cisco123"
        assert redact_text(secretish) != secretish, "the planted value is one the mask takes"
        got = E.preview("Lab", "describe-link", dict(LINK, description=secretish))
        assert got["code"] == "wrong_shape" and "nothing that reads as a secret" in \
            got["refused"] and "Cisco123" not in got["refused"]

    def test_the_description_steps_own_apply_rechecks_its_hash(self, host):  # noqa: F811
        before = _head(host)
        got = E._description_apply("Lab", {"device": "s1", "interface": "Gi0/1",
                                           "description": "s1 to r2"}, "0" * 16,
                                   actor=PERSON, reason=REASON)
        assert got["outcome"] == "moved" and "nothing was committed" in got["words"]
        assert _head(host) == before

    def test_the_ztp_steps_own_apply_rechecks_its_hash(self, ztp):
        got = E._ztp_apply("Default", dict(ZTP), "0" * 16, actor=PERSON, reason=REASON)
        assert got["outcome"] == "moved" and "nothing was created" in got["words"]
        assert ztp["ran"] == []

    def test_a_step_that_raises_is_failed_unknown_never_not_run(self, host,  # noqa: F811
                                                                monkeypatch):
        from modules.nsot import intent_patch

        def boom(*a, **k):
            raise RuntimeError("the repository broke (a test's own words)")
        monkeypatch.setattr(intent_patch, "commit", boom)
        rec = approve("describe-link", LINK)
        assert rec["outcome"] == "failed" and rec["state"] == "failed"
        first, second = rec["plan_steps"]
        assert first["state"] == "failed" and "whether it landed is unknown" in \
            first["words_said"]
        assert second["state"] == "not_run"

    def test_the_job_is_listed_by_its_page_and_announces_what_its_steps_write(
            self, kea, monkeypatch):
        from modules import invalidation
        started = []
        monkeypatch.setattr("modules.nsot.capture_job.start",
                            lambda *a, **kw: started.append(kw) or "j-9")
        got = E.start("Default", "dhcp-reservation", RES,
                      E.preview("Default", "dhcp-reservation", RES)["hash"], actor=PERSON,
                      actor_verified="access", person=True, reason=REASON)
        (kw,) = started
        assert kw["page"].startswith("/v2/plans/preview?list=Default&plan=dhcp-reservation&run=")
        assert kw["page"].endswith("&job={job}") and got["job"] == "j-9"
        # Its record, and what its one step's own operation announces (the reservation's).
        assert kw["announcer"] == "plan" and kw["announce_keys"] == ("privileged", "dhcp")
        assert set(kw["announce_keys"]) <= set(invalidation.ANNOUNCERS["plan"])

    def test_each_step_kind_announces_what_its_own_operation_announces(self):
        """A step kind's keys are its by-hand route's own (`invalidation.DECLARED`), and the
        plan's announcer and its route declare every one."""
        from modules import invalidation
        for kind in E.STEP_KINDS.values():
            assert set(kind.announces) <= set(invalidation.DECLARED[kind.by_hand]), kind.key
            assert set(kind.announces) <= set(invalidation.ANNOUNCERS["plan"]), kind.key
            assert set(kind.announces) <= set(invalidation.DECLARED["plans_v2.approve"])
        assert set(E.STEP_KINDS["ztp-create"].announces) == {
            "pending", "intent", "credentials", "remote", "in_progress"}

    @pytest.mark.parametrize("outcome, level, words", [
        ("done", "ok", "every step ran and was verified"),
        ("partial", "warn", "every step ran; one leaves its own approval to come"),
        ("stopped", "danger", "stopped at a step that did not pass"),
        ("refused", "danger", "nothing ran"),
    ])
    def test_in_progress_draws_each_end_at_its_level(self, monkeypatch, outcome, level, words):
        """The job's payload as In progress reads a page job's (`in_flight.page_finished_row`):
        a plan that passed is never drawn "failed · refused: no reason"."""
        from modules import in_flight
        payload = E.payload_of({"id": "r1", "outcome": outcome, "why": "the plan's own words"})
        monkeypatch.setattr("modules.nsot.capture_job.get",
                            lambda job: {"state": "done", "payload": payload})
        row = in_flight.page_finished_row({"job": "j-1", "list": "Default", "kind": "plan",
                                           "page": "/v2/plans/preview?job=j-1",
                                           "finished_at": 0}, "someone")
        assert row["level"] == level and row["words"].startswith(words), row
        assert "the plan's own words" in row["words"]


# ── The route and the card ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(kea, monkeypatch):
    import app as A
    monkeypatch.setattr("modules.nsot.capture_job.start",
                        lambda lst, label, actor, work, **kw: (work("j-1"), "j-1")[1])
    A.app.config["TESTING"] = True
    return A.app.test_client()


HX = {"HX-Request": "true"}
#: The run's first step, done, as THE stepper draws it (`run_stepper`, `plan_engine.run_card`).
DONE_STEP = 'run-step run-step-done" data-step="step-1"'


class TestTheRunOnTheOneStepper:
    """A plan's run drawn by THE stepper from its own record (`plan_engine.run_card`): each step
    its recorded state, never green over a stop or a step that leaves its own approval."""

    def _rec(self, state, outcome, *steps):
        return {"title": "Describe the link", "plan": "describe-link", "state": state,
                "outcome": outcome, "why": "the run's own words",
                "plan_steps": [{"n": n, "kind": k, "words": f"words {n}", "state": s,
                                "words_said": f"said {n}"}
                               for n, (k, s) in enumerate(steps, 1)]}

    def _states(self, card):
        (row,) = card["rows"]
        return row["group"], [(s["key"], s["words"], s["state"]) for s in row["steps"]]

    def test_a_stopped_run_draws_its_failed_step_and_the_rest_not_reached(self):
        group, steps = self._states(E.run_card(self._rec(
            "failed", "stopped", ("intent-description", "done"),
            ("intent-description", "refused"), ("intent-description", "not_run"))))
        assert group == "failed"
        assert steps == [("step-1", "Set a description", "done"),
                         ("step-2", "Set a description", "failed"),
                         ("step-3", "Set a description", "not_reached")]

    def test_running_the_steps_not_yet_run_wait_their_turn(self):
        card = E.run_card(self._rec("running", "running", ("intent-description", "done"),
                                    ("intent-description", "running"),
                                    ("intent-description", "not_run")))
        group, steps = self._states(card)
        assert group == "running" and card["single"]
        assert [s for _k, _w, s in steps] == ["done", "running", "waiting"]
        assert card["rows"][0]["steps"][0]["note"] == "said 1"

    def test_a_create_that_leaves_its_verify_is_never_green(self):
        group, steps = self._states(E.run_card(self._rec(
            "unverified", "partial", ("ztp-create", "done"))))
        assert group == "partial" and steps == [("step-1", "Create by ZTP", "needs")]

    def test_a_run_refused_before_its_steps_says_why_in_their_place(self):
        card = E.run_card({"title": "Reserve it", "state": "refused", "outcome": "refused",
                           "why": "the plan is not the one approved", "plan_steps": []})
        (row,) = card["rows"]
        assert row["group"] == "failed" and row["steps"] == []
        assert row["detail"] == "the plan is not the one approved"

    def test_approved_its_page_draws_the_running_step_on_the_stepper(self, kea, monkeypatch):
        """Approve pressed on the real card; while the run's step applies, the run's page (the
        job's *page*, as In progress opens it) draws it on `run_stepper`, the step running and
        the card asking for itself again; once it ends, the step done and the redraw stopped."""
        import dataclasses
        import re

        import app as A
        A.app.config["TESTING"] = True
        client = A.app.test_client()
        started, during = [], []
        monkeypatch.setattr("modules.nsot.capture_job.start",
                            lambda lst, label, actor, work, **kw: started.append((work, kw))
                            or "j-1")
        kind = E.STEP_KINDS["dhcp-reservation"]

        def apply(*a, **k):
            page = started[0][1]["page"].replace("{job}", "j-1")
            during.append(client.get(page, headers=HX).get_data(as_text=True))
            return kind.apply(*a, **k)
        monkeypatch.setitem(E.STEP_KINDS, "dhcp-reservation", dataclasses.replace(kind,
                                                                                apply=apply))
        html = client.get("/v2/plans/preview", query_string={
            "list": "Default", "plan": "dhcp-reservation", "params": json.dumps(RES)},
            headers=HX).get_data(as_text=True)
        m = re.search(r'hx-post="(/v2/plans/approve[^"]*)" hx-vals=\'\{"hash": "([0-9a-f]{16})"',
                      html)
        r = client.post(m.group(1).replace("&amp;", "&"), data={
            "hash": m.group(2), "plan": "dhcp-reservation", "params": json.dumps(RES),
            "reason": REASON}, headers=HX)
        assert r.status_code == 200 and 'aria-busy="true"' in r.get_data(as_text=True)
        monkeypatch.setattr("modules.nsot.capture_job.get", lambda job: {"state": "running"})
        ((work, kw),) = started
        work("j-1")
        (out,) = during
        assert "data-run-stepper" in out and 'aria-busy="true"' in out
        assert 'run-step run-step-running" data-step="step-1"' in out
        assert 'aria-current="step"' in out and "DHCP reservation" in out
        assert kea.recorded
        after = client.get(kw["page"].replace("{job}", "j-1"), headers=HX).get_data(as_text=True)
        assert DONE_STEP in after and 'aria-busy="true"' not in after


class TestTheCard:
    def _card(self, client):
        r = client.get("/v2/plans/preview", query_string={
            "list": "Default", "plan": "dhcp-reservation", "params": json.dumps(RES)}, headers=HX)
        return r, r.get_data(as_text=True)

    def test_approved_on_its_card_it_runs_and_draws_each_step_in_place(self, client, kea):
        import re
        r, html = self._card(client)
        assert r.status_code == 200, html
        m = re.search(r'hx-post="(/v2/plans/approve[^"]*)" hx-vals=\'\{"hash": "([0-9a-f]{16})"'
                      r'\}\'[^>]*hx-disabled-elt="this"', html)
        assert m, "Approve the plan carries the plan's hash, busy on itself"
        assert "Approve the plan on Default: Reserve 10.10.20.150 for h5" in html
        r = client.post(m.group(1).replace("&amp;", "&"), data={
            "hash": m.group(2), "plan": "dhcp-reservation", "params": json.dumps(RES),
            "reason": REASON}, headers=HX)
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out
        assert "Every step ran and was verified:" in out and DONE_STEP in out
        assert kea.recorded

    def test_a_job_that_ended_with_no_record_is_said_never_running(self, kea, monkeypatch):
        """The card's state for a run with no record: the job's own, read from the job
        registry; a job that failed is its failure, and one still running is running."""
        import app as A
        from routes import plans_v2
        jobs = {"j-x": {"state": "failed",
                        "error": "RuntimeError: the store broke (a test's own words)"},
                "j-y": {"state": "running", "error": ""}}
        monkeypatch.setattr("modules.nsot.capture_job.get", lambda job: jobs.get(job))
        with A.app.test_request_context():
            failed = plans_v2.card("Default", {"run": "run-x", "job": "j-x"})
            going = plans_v2.card("Default", {"run": "run-y", "job": "j-y"})
        assert failed["state"] == "running" and "the store broke" in failed["job_failed"]
        assert going["state"] == "running" and going["job_failed"] == ""

    def test_a_refusal_is_drawn_through_the_mask(self, kea, monkeypatch):
        """A step's own refusal may quote what its operation read: the card draws it through
        the same mask as the preview's own words."""
        import app as A
        from routes import plans_v2
        monkeypatch.setattr(E, "preview", lambda *a, **k: {
            "ok": False, "refused": "password Cisco123",
            "steps": [], "hash": "", "code": "step_refused"})
        with A.app.test_request_context():
            c = plans_v2.card("Default", {"plan": "dhcp-reservation", "params": "{}"})
        assert "Cisco123" not in c["preview"]["refused"] and "<redacted" in \
            c["preview"]["refused"]

    def test_approved_its_in_progress_row_opens_a_whole_page_with_its_outcome(
            self, client, kea, monkeypatch):
        """Approve pressed on the card; the job's end as In progress draws it (from the job's
        own payload, `in_flight.page_finished_row`): done, at ok, never "failed · refused";
        its Open, a plain request to the job's page, is the whole frame around the card with
        the outcome, never the bare fragment."""
        import re

        from modules import in_flight
        started = []
        monkeypatch.setattr("modules.nsot.capture_job.start",
                            lambda lst, label, actor, work, **kw:
                            started.append((work("j-1"), kw)) or "j-1")
        _r, html = self._card(client)
        m = re.search(r'hx-post="(/v2/plans/approve[^"]*)" hx-vals=\'\{"hash": "([0-9a-f]{16})"',
                      html)
        r = client.post(m.group(1).replace("&amp;", "&"), data={
            "hash": m.group(2), "plan": "dhcp-reservation", "params": json.dumps(RES),
            "reason": REASON}, headers=HX)
        assert r.status_code == 200 and kea.recorded
        ((payload, kw),) = started
        monkeypatch.setattr("modules.nsot.capture_job.get",
                            lambda job: {"state": "done", "payload": payload})
        row = in_flight.page_finished_row({"job": "j-1", "list": "Default", "kind": "plan",
                                           "page": kw["page"].replace("{job}", "j-1"),
                                           "finished_at": 0}, "someone")
        assert row["level"] == "ok" and row["words"].startswith(
            "every step ran and was verified"), row
        page = client.get(row["href"])
        whole = page.get_data(as_text=True)
        assert page.status_code == 200 and whole.lstrip().lower().startswith("<!doctype html")
        assert "<title>A plan" in whole and "htmx" in whole
        assert "Every step ran and was verified:" in whole and DONE_STEP in whole

    def test_a_hash_not_previewed_is_refused_in_place_with_nothing_run(self, client, kea):
        r = client.post("/v2/plans/approve?list=Default", data={
            "hash": "0" * 16, "plan": "dhcp-reservation", "params": json.dumps(RES),
            "reason": REASON}, headers=HX)
        out = r.get_data(as_text=True)
        assert r.status_code == 409 and "Not run:" in out and "0000000000000000" in out
        assert kea.recorded == []


# ── The toolbar assistant names a plan ──────────────────────────────────────────────────────

class TestTheAssistantProposes:
    def _words(self, plan):
        from modules.ai import assistant as A
        return A.AssistantAnswerV2(answer="Mercury can reserve it for you.", cites=["x"],
                                   covered=True, screens=[], plan=plan)

    def test_a_plan_it_names_is_held_to_the_schema_and_offered(self):
        from modules.ai import assistant as A
        ask = A.PlanAsk(plan="dhcp-reservation",
                        params=[A.PlanParam(name=k, value=v) for k, v in RES.items()])
        got, why = A.plan_of(self._words(ask))
        assert why == "" and got == {"plan": "dhcp-reservation", "params": RES,
                                     "title": "Reserve 10.10.20.150 for h5 (aa:c1:ab:5d:20:9e)"}
        assert "dhcp-reservation" in [x["plan"] for x in A.context()["plans"]]

    @pytest.mark.parametrize("params, words", [
        ([("mac", "AA"), ("address", "10.10.20.150"), ("hostname", "h5"), ("subnet", "20")],
         "parameter mac is a MAC address"),
        ([("mac", RES["mac"]), ("mac", RES["mac"])], "names the parameter 'mac' twice"),
        ([("password", "hunter2")] + list(RES.items()), "a parameter the schema does not name"),
    ])
    def test_anything_else_drops_the_plan_not_the_answer(self, params, words):
        """Mercury's check of the plan: a wrong one is dropped, said, and the answer's own text
        still drawn (the check of the answer passes); the wrong value is never echoed."""
        from modules.ai import assistant as A
        ask = A.PlanAsk(plan="dhcp-reservation",
                        params=[A.PlanParam(name=k, value=v) for k, v in params])
        assert A.check(self._words(ask), [{"link": "x"}]) == ""
        plan, why = A.plan_of(self._words(ask))
        assert plan is None and why.startswith("its plan") and words in why, why
        assert "hunter2" not in why and "AA" not in why.replace("ADDRESS", "")

    def test_no_plan_is_none(self):
        from modules.ai import assistant as A
        assert A.plan_of(self._words(None)) == (None, "")
