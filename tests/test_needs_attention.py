"""Needs attention (Stage 7.2): one row shape, one source contract, job health first.

NSOT_STAGE7_PLAN section 1a: one list, every source, each row the same shape
(what, device, since, cause, operands, the ONE action); a source that could
not be read is a row, never an absence; and an empty page says what it looked
at, with the time of each source. NSOT_PLAN 8.6: each row keeps an empty
triage slot for Stage 8.

The job-health fixtures are the shapes systemd and the journal return,
measured on the NMAS host (tests/test_job_health.py).
"""

import json
import os

import dukpy
import pytest

from modules import attention as A
from modules import job_health as J
from tests.test_job_health import LOADED, NOW, _fail, _ok, _runner

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _health(journal, **rows):
    """job_health.health() over the measured systemd shapes, with every other
    family empty unless given."""
    kw = dict(images=[], settings=[], rotations=[], owner=[], ztp=[], responder=[],
              startup=[], sessions=[], version=[])
    kw.update(rows)
    return lambda: J.health(NOW, _runner(LOADED, journal), **kw)


# ---------------------------------------------------------------------------
# The row and the source contract
# ---------------------------------------------------------------------------

class TestTheRowRefusesASilentPart:
    GOOD = dict(source="s", key="k", what="x is failing", cause="because y",
                action={"label": "do z"}, level="danger")

    def test_a_complete_row_carries_every_part_and_an_empty_triage_slot(self):
        r = A.row(**self.GOOD, devices=["r1", ""], since=NOW, operands={"a": 1})
        assert r["id"] == "s:k" and r["devices"] == ["r1"]
        assert r["since"].endswith("Z") and r["triage"] is None
        assert r["action"] == {"known": True, "label": "do z"}

    @pytest.mark.parametrize("part", ["what", "cause", "key", "source"])
    def test_no_cause_or_no_what_is_refused(self, part):
        with pytest.raises(A.RowRefused, match=part):
            A.row(**{**self.GOOD, part: "  "})

    @pytest.mark.parametrize("action", [None, {}, {"label": ""}, "do z"])
    def test_no_action_is_refused(self, action):
        with pytest.raises(A.RowRefused, match="action"):
            A.row(**{**self.GOOD, "action": action})

    def test_an_unknown_level_is_refused(self):
        with pytest.raises(A.RowRefused, match="level"):
            A.row(**{**self.GOOD, "level": "green"})

    def test_since_not_recorded_stays_none(self):
        """None is drawn as 'not recorded', never replaced by now."""
        assert A.row(**self.GOOD)["since"] is None


class TestTheSourceContract:
    def test_an_unreadable_source_is_a_row_never_an_absence(self):
        res = A.source_result("x", "Thing", read_at=NOW, took_ms=3, error="it timed out")
        assert res["state"] == "unreadable" and len(res["rows"]) == 1
        r = res["rows"][0]
        assert r["level"] == "unknown" and "Thing could not be read" in r["what"]
        assert "not the same as nothing needing attention" in r["cause"]
        assert r["action"]["known"] is False

    def test_a_read_source_must_say_what_it_looked_at(self):
        with pytest.raises(A.RowRefused, match="looked at"):
            A.source_result("x", "Thing", read_at=NOW, took_ms=3, rows=[])

    def test_a_raising_adapter_is_still_a_row(self):
        def broken():
            raise KeyError("jobs")
        page = A.needs_attention([broken])
        assert page["headline"] == "1 thing(s) need attention"
        assert page["rows"][0]["level"] == "unknown" and page["unreadable"] == ["broken"]


# ---------------------------------------------------------------------------
# Source: job health
# ---------------------------------------------------------------------------

class TestJobHealthAsASource:
    def test_the_measured_failing_job_is_a_row_with_its_cause_and_since(self):
        journal = "\n".join([_ok(NOW - 73 * 1800)]
                            + [_fail(NOW - k * 1800) for k in range(72, 0, -1)])
        res = A.job_health_source(_health(journal))
        assert res["state"] == "read"
        rows = {r["id"]: r for r in res["rows"]}
        r = rows["job_health:clab-sync"]
        assert r["what"] == "clab-sync is failing" and r["level"] == "danger"
        assert "nmas-clab-targets: command not found" in r["cause"]
        # SINCE is the streak's FIRST failure, not the latest one.
        assert r["since"] == A._iso(NOW - 72 * 1800)
        assert r["action"]["command"] == "journalctl -u clab-sync.service -n 50 --no-pager"

    def test_ok_jobs_are_not_rows_and_are_counted_as_looked_at(self):
        res = A.job_health_source(_health(_ok(NOW - 60)))
        assert res["rows"] == []
        assert res["checked"] == f"{len(J.JOBS)} job-health row(s), {len(J.JOBS)} ok"

    def test_a_stale_job_says_since_it_went_stale(self):
        res = A.job_health_source(_health(_ok(NOW - 4 * 3600)))
        r = {x["id"]: x for x in res["rows"]}["job_health:clab-sync"]
        assert r["what"] == "clab-sync has not succeeded recently"
        assert r["since"] == A._iso(NOW - 4 * 3600 + 90 * 60)

    def test_a_device_row_names_its_device_as_a_field(self):
        """Rows concerning a device carry it as a field, never parsed back out
        of the unit string (the adjacent-match family)."""
        from modules.nsot import credential_rotation as cr
        rot = J.rotation_rows([{"device": "r2", "state": cr.ROTATED_UNVERIFIED,
                                "failed_stage": "device_startup_config",
                                "at": "2026-09-28T10:00:00Z"}],
                              known=({"r2"}, ""))
        assert rot and rot[0]["device"] == "r2"
        res = A.job_health_source(_health(_ok(NOW - 60), rotations=rot))
        r = {x["id"]: x for x in res["rows"]}["job_health:rotation:r2"]
        assert r["devices"] == ["r2"] and r["level"] == "danger"
        assert "nmas-persist-native r2" in r["cause"]

    def test_departed_and_not_applicable_are_not_rows(self):
        gone = [{"unit": "rotation:r9", "device": "r9", "what": "x",
                 "state": "departed", "detail": "left", "max_age_minutes": 0}]
        na = [{"unit": "yang", "what": "x", "state": "not_applicable",
               "detail": "declared", "max_age_minutes": 0}]
        res = A.job_health_source(_health(_ok(NOW - 60), rotations=gone, settings=na))
        assert res["rows"] == []

    def test_an_unmapped_state_is_drawn_loud_with_its_own_name(self):
        new = [{"unit": "new-thing", "what": "x", "state": "exploded",
                "detail": "d", "max_age_minutes": 0}]
        res = A.job_health_source(_health(_ok(NOW - 60), version=new))
        r = res["rows"][0]
        assert r["level"] == "danger" and r["what"] == "new-thing reads exploded"

    def test_a_health_read_that_raises_is_the_unreadable_row(self):
        def boom():
            raise OSError("systemctl gone")
        res = A.job_health_source(boom)
        assert res["state"] == "unreadable"
        assert "systemctl gone" in res["rows"][0]["cause"]

    #: One real unit per job-health row family (the unit strings job_health
    #: writes), so the action each gets is asked of the code, not assumed.
    FAMILIES = {"systemd": "clab-sync", "image": "vzdump:rcn-lab1",
                "settings": "setting:clab_host", "rotation": "rotation:r1",
                "clab-sync-owner": "clab-sync-owner",
                "ztp-responder": "nmas-ztp-responder",
                "startup": "startup:lab/r1", "ssh": "ssh:192.0.2.1",
                "running-version": "running-version", "ztp-posture": "ztp-posture"}

    #: Families whose rows write their remedy into the detail, so the row
    #: says no separate action is recorded (known: False) rather than
    #: inventing one. 7.2's later steps lift each; this set only SHRINKS.
    NO_RECORDED_ACTION = {"image", "settings", "rotation", "clab-sync-owner",
                          "ztp-responder", "startup", "ssh", "running-version",
                          "ztp-posture"}

    def test_the_families_without_a_recorded_action_only_shrink(self):
        got = {fam for fam, unit in self.FAMILIES.items()
               if A._job_action({"unit": unit, "state": "failing"}).get("known") is False}
        assert got == self.NO_RECORDED_ACTION, (
            f"now without an action: {sorted(got - self.NO_RECORDED_ACTION)}; "
            f"now with one (shrink the pin): {sorted(self.NO_RECORDED_ACTION - got)}")
        # The floor: the family that has actions keeps them.
        assert "systemd" not in got


# ---------------------------------------------------------------------------
# The page, the route and the shipped panel
# ---------------------------------------------------------------------------

def _panel(payload):
    src = open(os.path.join(ROOT, "static", "js", "nmas_attention.js")).read()
    return dukpy.evaljs("var window = {};\n" + src
                        + f"\nwindow.attentionPanelHtml({json.dumps(payload)});")


class TestThePageAndThePanel:
    def test_nothing_says_what_it_looked_at_and_when(self, monkeypatch):
        monkeypatch.setattr(A, "SOURCES", (lambda: A.job_health_source(_health(_ok(NOW - 60))),))
        page = A.needs_attention()
        assert page["headline"] == "Nothing needs attention" and page["rows"] == []
        src = page["sources"][0]
        assert src["state"] == "read" and src["read_at"] and src["checked"]
        html = _panel(page)
        assert "Nothing needs attention" in html and "Job health: read" in html
        assert src["checked"] in html and 'data-attention="none"' in html

    def test_rows_are_worst_first_and_drawn_with_every_part(self, monkeypatch):
        journal = "\n".join([_ok(NOW - 73 * 1800), _fail(NOW - 60)])
        unk = [{"unit": "running-version", "what": "x", "state": "unknown",
                "detail": "could not ask", "max_age_minutes": 0}]
        monkeypatch.setattr(A, "SOURCES", (lambda: A.job_health_source(
            _health(journal, version=unk)),))
        page = A.needs_attention()
        levels = [r["level"] for r in page["rows"]]
        # The fake runner answers every systemd unit with this journal, so
        # each is failing; the unknown row sorts after all of them.
        assert levels == ["danger"] * len(J.JOBS) + ["unknown"], levels
        html = _panel(page)
        assert "clab-sync is failing" in html and "command not found" in html
        assert "journalctl -u clab-sync.service" in html and "since 20" in html
        assert "cannot tell" in html and "since not recorded" in html

    def test_a_failed_read_is_never_drawn_as_nothing(self):
        html = _panel({"ok": False, "error": "timeout"})
        assert "Could not ask what needs attention" in html
        assert "not the same as nothing needing attention" in html
        assert "Nothing needs attention" not in html

    def test_every_value_is_escaped(self, monkeypatch):
        bad = [{"unit": "<img src=x>", "what": "x", "state": "unknown",
                "detail": "<script>alert(1)</script>", "max_age_minutes": 0}]
        monkeypatch.setattr(A, "SOURCES", (lambda: A.job_health_source(
            _health(_ok(NOW - 60), version=bad)),))
        html = _panel(A.needs_attention())
        assert "<script>" not in html and "<img" not in html
        assert "&lt;script&gt;" in html

    def test_the_route_answers_the_page(self, monkeypatch):
        import app as nmas
        journal = "\n".join([_ok(NOW - 3600), _fail(NOW - 60)])
        monkeypatch.setattr(A, "SOURCES", (lambda: A.job_health_source(
            _health(journal)),))
        r = nmas.app.test_client().get("/attention")
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True and body["rows"]
        assert "clab-sync is failing" in _panel(body)

    def test_the_landing_view_includes_the_panel_and_loads_its_script(self):
        index = open(os.path.join(ROOT, "templates", "index.html")).read()
        part = open(os.path.join(ROOT, "templates", "partials", "needs_attention.html")).read()
        assert "{% include 'partials/needs_attention.html' %}" in index
        assert 'id="needsAttentionPanel"' in part and "js/nmas_attention.js" in part


# ---------------------------------------------------------------------------
# Source: drift, with coverage (C96)
# ---------------------------------------------------------------------------

from tests import payload_providers as P  # noqa: E402


def _status(**kw):
    base = {"list": "lab", "state": "idle", "disabled": False, "last_run": None,
            "last_ts": 0}
    base.update(kw)
    return lambda: base


class TestDriftAsASource:
    def test_a_real_run_gives_a_row_per_device_it_did_not_clear(self, monkeypatch, tmp_path):
        """Through run_drift_check(): r1 clean, r2 drifted, r3 no golden, r4
        unreachable. Every device but the clean one is a row, each naming it."""
        P._drift_run(monkeypatch, tmp_path)
        res = A.drift_source()
        rows = {r["id"].split(":", 2)[2]: r for r in res["rows"]}
        drifted = rows["drifted:r2"]
        assert drifted["level"] == "danger" and drifted["devices"] == ["r2"]
        assert drifted["operands"]["diff_lines"] > 0
        assert drifted["operands"]["coverage"] == "checked 2 of 4"
        assert drifted["action"]["label"].startswith("From its Device page")
        # The check saw drift at a time; since when it has differed is not
        # recorded, so since stays empty rather than claiming the run time.
        assert drifted["since"] is None and "not recorded" in drifted["cause"]
        assert rows["skipped:r3"]["action"]["label"].startswith("Capture")
        assert rows["unreachable:r4"]["level"] == "unknown"
        assert not any("r1" in r["devices"] for r in res["rows"])
        assert "checked 2 of 4" in res["checked"] and "manual" in res["checked"]

    def test_the_value_is_dated_by_the_run_not_by_the_read(self):
        last = {"ok": True, "inventory": 1, "checked": 1, "clean": 1,
                "drifted_devices": [], "skipped": [], "errors": [],
                "triggered_by": "scheduled"}
        res = A.drift_source(_status(last_run=last, last_ts=NOW - 600), now=NOW)
        assert res["value_at"] == A._iso(NOW - 600) and res["value_at"] != res["read_at"]
        assert res["rows"] == []

    def test_switched_off_is_a_row_naming_who_and_since(self):
        res = A.drift_source(_status(disabled=True, disabled_by="ops@example.com",
                                     disabled_at="2026-08-30T10:03:00Z"), now=NOW)
        r = res["rows"][0]
        assert r["what"] == "Drift checking is switched off for lab"
        assert "ops@example.com" in r["cause"] and r["since"] == "2026-08-30T10:03:00Z"

    def test_never_run_is_unknown_not_clean(self):
        res = A.drift_source(_status(), now=NOW)
        assert [r["level"] for r in res["rows"]] == ["unknown"]
        assert "unknown" in res["rows"][0]["cause"]

    def test_a_failed_run_is_a_row_with_its_reason(self):
        res = A.drift_source(_status(last_run={"ok": False, "summary": "Drift check failed: boom"},
                                     last_ts=NOW - 60), now=NOW)
        assert res["rows"][0]["cause"] == "Drift check failed: boom"

    def test_an_old_run_is_a_row_and_its_findings_still_stand(self):
        from modules import drift_check as D
        last = {"ok": True, "inventory": 2, "checked": 2, "drifted_devices":
                [{"hostname": "r2", "diff_lines": 4}], "skipped": [], "errors": []}
        old = NOW - (A.DRIFT_STALE_INTERVALS + 1) * D._get_interval()
        res = A.drift_source(_status(last_run=last, last_ts=old), now=NOW)
        keys = [r["id"] for r in res["rows"]]
        assert keys == ["drift:lab:stale", "drift:lab:drifted:r2"]

    def test_the_drift_panel_draws_what_the_run_found(self, monkeypatch, tmp_path):
        """C96: after a run the panel said there was one and not what it found."""
        import app as nmas
        from tests.js_source import with_loaded_scripts
        from tests.payload_render import lift

        # /drift/status counts the approval queue, which resolves a list path.
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
        status = P.drift_status(monkeypatch, tmp_path)
        page = with_loaded_scripts(nmas.app.test_client().get("/").get_data(as_text=True))
        js = lift(page, "driftDetailHtml")
        html = dukpy.evaljs(js + f"\ndriftDetailHtml({json.dumps(status)});")
        assert "Drifted: r2" in html and "diff line(s)" in html
        assert "triggered by manual" in html and status["last_run"]["timestamp"] in html


# ---------------------------------------------------------------------------
# Source: the approval queue, and the attach rule
# ---------------------------------------------------------------------------

def _drift_status_with(host):
    last = {"ok": True, "inventory": 2, "checked": 2, "clean": 1,
            "drifted_devices": [{"hostname": host, "diff_lines": 6}],
            "skipped": [], "errors": [], "triggered_by": "scheduled"}
    return _status(list="lab", last_run=last, last_ts=NOW - 60)


def _item(host, kind="update_golden_config", **kw):
    return {"id": f"q-{host}-{kind}", "status": "pending", "action_type": kind,
            "device_hostname": host, "description": f"Config drift detected on {host}",
            "context": "Detected by scheduled drift check", "created_ts": NOW - 50, **kw}


class TestApprovalsAsASource:
    @pytest.fixture
    def queue(self, tmp_path, monkeypatch):
        from modules import approval_queue as Q
        path = tmp_path / "approval_queue.json"
        monkeypatch.setattr(Q, "_queue_path", lambda: str(path))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        return Q, path

    def test_the_read_writes_nothing_and_applies_expiry_in_memory(self, queue):
        import time as _time
        Q, path = queue
        # The reader expires against the WALL clock, so these are real times.
        fresh = _item("r2", created_ts=_time.time() - 60)
        old = _item("r9", created_ts=_time.time() - (Q.EXPIRY_HOURS + 1) * 3600)
        path.write_text(json.dumps([fresh, old]))
        before = path.read_bytes()
        pending, reason = Q.read_pending()
        assert reason is None and [e["device_hostname"] for e in pending] == ["r2"]
        assert path.read_bytes() == before, "a read changed the queue"

    def test_an_unreadable_queue_is_its_own_answer_not_empty(self, queue):
        Q, path = queue
        path.write_text('[{"id": "q1", "status": "pen')                 # torn
        res = A.approvals_source()
        assert res["state"] == "unreadable" and "could not be read" in res["rows"][0]["cause"]

    def test_absent_is_nothing_waiting(self, queue):
        res = A.approvals_source()
        assert res["state"] == "read" and res["rows"] == []
        assert res["checked"] == "list lab: 0 pending approval(s)"

    def test_a_drift_item_folds_into_its_drift_row(self, queue):
        page = A.needs_attention([lambda: A.drift_source(_drift_status_with("r2"), now=NOW),
                                  lambda: A.approvals_source(lambda: ([_item("r2")], None))])
        assert len(page["rows"]) == 1, [r["id"] for r in page["rows"]]
        r = page["rows"][0]
        assert r["id"] == "drift:lab:drifted:r2" and len(r["attached"]) == 1
        assert r["attached"][0]["source"] == "approvals"
        assert r["action"]["label"].startswith("Review it in Approvals")
        assert "1 thing(s)" in page["headline"]
        html = _panel(page)
        assert "Also: An approval is waiting" in html

    def test_a_drift_item_whose_drift_is_gone_stands_alone_and_says_so(self, queue):
        page = A.needs_attention([lambda: A.drift_source(_drift_status_with("r3"), now=NOW),
                                  lambda: A.approvals_source(lambda: ([_item("r2")], None))])
        ids = sorted(r["id"] for r in page["rows"])
        assert ids == ["approvals:q-r2-update_golden_config", "drift:lab:drifted:r3"]
        assert "which is not on this page" in _panel(page)

    def test_any_other_approval_is_its_own_row(self, queue):
        res = A.approvals_source(lambda: ([_item("r2", kind="revert_to_golden")], None))
        r = res["rows"][0]
        assert r["attach_to"] is None and r["devices"] == ["r2"]
        assert r["since"] == A._iso(NOW - 50)

    def test_the_route_masks_what_a_row_quotes(self, queue, monkeypatch):
        import app as nmas
        secret = _item("r2", kind="revert_to_golden",
                       description="snmp-server community Pl4ntedC0mmunity RO")
        monkeypatch.setattr(A, "SOURCES", (lambda: A.approvals_source(
            lambda: ([secret], None)),))
        body = nmas.app.test_client().get("/attention").get_data(as_text=True)
        assert "Pl4ntedC0mmunity" not in body and "redacted" in body


# ---------------------------------------------------------------------------
# Source: pending onboardings
# ---------------------------------------------------------------------------

def _pending(name, state, **kw):
    return {"identity": f"uid:{name}", "name": name, "state": state,
            "onboarded_at": "2026-09-27T10:00:00Z", "age_seconds": 30 * 3600,
            "address_source": "static", "credential_findable": True, **kw}


class TestPendingOnboardingsAsASource:
    def test_in_flight_is_counted_not_listed(self, monkeypatch):
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        res = A.pending_onboarding_source(lambda: [_pending("bp-a", "in_flight")])
        assert res["rows"] == [] and res["checked"] == "list lab: 1 pending, 1 within their first day"

    def test_overdue_is_a_row_with_its_action(self, monkeypatch):
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        res = A.pending_onboarding_source(lambda: [_pending("bp-a", "overdue")])
        r = res["rows"][0]
        assert r["what"] == "bp-a was onboarded 30 h ago and has never been reached"
        assert r["since"] == "2026-09-27T10:00:00Z" and "Verify" in r["action"]["label"]

    def test_a_credential_nothing_can_find_is_danger_even_in_flight(self, monkeypatch):
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        res = A.pending_onboarding_source(
            lambda: [_pending("bp-b", "in_flight", credential_findable=False)])
        r = res["rows"][0]
        assert r["level"] == "danger" and "Abandon" in r["action"]["label"]
        assert "0 within their first day" in res["checked"]

    def test_a_manifest_that_raises_is_the_unreadable_row(self, monkeypatch):
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")

        def boom():
            raise ValueError("manifest damaged")
        res = A.pending_onboarding_source(boom)
        assert res["state"] == "unreadable" and "manifest damaged" in res["rows"][0]["cause"]


# ---------------------------------------------------------------------------
# Source: rollback blocks, through the ONE classifier and a REAL plan
# ---------------------------------------------------------------------------

class TestRollbackBlocksAsASource:
    @pytest.fixture
    def blocked(self, monkeypatch, tmp_path):
        """test_rollback_block_enforced's lab: r2's real config and committed
        intent, a block planted with the real record_rolled_back() on the
        program the real plan computes."""
        from tests.test_rollback_block_enforced import _plant, _program, _set_description
        from tests.test_capture import build_capture_lab

        lab = build_capture_lab(monkeypatch, tmp_path)
        _set_description(lab["repo"], "GigabitEthernet2", "C118-FAILED-CHANGE")
        _artifact, failed = _program(lab["repo"])
        _plant(lab["repo"], failed)
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
        return lab

    def test_a_standing_block_is_a_row_naming_the_device(self, blocked):
        res = A.rollback_source()
        assert [r["id"] for r in res["rows"]] == ["rollback:Lab:r2"], res
        r = res["rows"][0]
        assert r["level"] == "warning" and r["devices"] == ["r2"]
        assert "C118 measurement" in r["cause"] and r["since"]
        assert r["action"]["known"] is False and "7.3" in r["action"]["label"]
        assert res["checked"] == "list Lab: 1 standing, 0 no longer blocking"

    def test_a_block_whose_change_is_gone_is_counted_not_listed(self, blocked):
        from tests.test_rollback_block_enforced import _set_description
        _set_description(blocked["repo"], "GigabitEthernet2", "something else entirely")
        res = A.rollback_source()
        assert res["rows"] == []
        assert res["checked"] == "list Lab: 0 standing, 1 no longer blocking"

    def test_an_unreadable_record_is_ONE_row_and_plans_nothing(self, blocked, monkeypatch):
        """C158: the record blocks every plan; asked per device it would plan
        the whole fleet to say one thing."""
        import routes.deploy as rd
        path = os.path.join(blocked["repo"], ".nsot", "rolled_back.json")
        with open(path, "w") as fh:
            fh.write('{"r2": {"commands": [" shut')                  # torn
        monkeypatch.setattr(rd, "_artifact_for", lambda *a: pytest.fail("planned a device"))
        res = A.rollback_source()
        assert [r["id"] for r in res["rows"]] == ["rollback:Lab:record"]
        assert res["rows"][0]["level"] == "danger"
        assert "could not be read" in res["rows"][0]["cause"]


# ---------------------------------------------------------------------------
# Source: deploys and restores, from the REAL receipts a real apply writes
# ---------------------------------------------------------------------------

class TestDeploysAsASource:
    def test_a_real_apply_s4_clean_s3_refused(self, monkeypatch):
        """payload_providers.deploy_apply: s4 deploys and verifies, s3 is
        refused (its program moved since it was confirmed). The receipts it
        writes are the input: s4 is clean and absent, s3 is a warning, since
        nothing was sent to it."""
        P.deploy_apply(monkeypatch)
        res = A.deploy_source()
        assert res["state"] == "read", res
        by_dev = {r["devices"][0]: r for r in res["rows"]}
        assert sorted(by_dev) == ["s3"], [r["id"] for r in res["rows"]]
        r = by_dev["s3"]
        assert r["level"] == "warning" and r["operands"]["sent_lines"] == 0
        assert r["what"].startswith("The last deploy to s3: refused")
        assert "Changes tab" in r["action"]["label"]
        assert "1 clean" in res["checked"] and "2 device(s)" in res["checked"]

    def _row(self, host, outcome, sent, at, **kw):
        return {"device": host, "outcome": outcome, "sent": sent, "at": at,
                "action": "deploy", "program_lines": 3 if sent else 0,
                "matches_confirmed": True if sent else None, "actor": "ops@example.com",
                "checks": {"ran": bool(sent), "ok": True if outcome == "deployed" else False,
                           "issues": kw.pop("issues", [])}, **kw}

    def test_a_later_clean_run_supersedes_a_failure(self):
        rows = [self._row("r2", "deployed", True, "2026-09-28T12:00:00Z"),       # newest
                self._row("r2", "failed", True, "2026-09-28T11:00:00Z")]
        res = A.deploy_source(lambda: {"state": "ok", "rows": rows})
        assert res["rows"] == []

    def test_a_failure_that_sent_is_danger_with_its_findings(self):
        rows = [self._row("r2", "failed", True, "2026-09-28T11:00:00Z", stage="verify",
                          reason="verify failed", issues=["ospf: 5 -> 3 neighbours"],
                          rollback={"performed": True, "state": "restored"})]
        r = A.deploy_source(lambda: {"state": "ok", "rows": rows})["rows"][0]
        assert r["level"] == "danger" and r["since"] == "2026-09-28T11:00:00Z"
        assert "ospf: 5 -> 3 neighbours" in r["cause"] and "rollback: restored" in r["cause"]

    def test_unreadable_receipts_are_the_unreadable_row_and_absent_is_none(self):
        bad = A.deploy_source(lambda: {"state": "unreadable", "error": "line 3 is not JSON"})
        assert bad["state"] == "unreadable" and "line 3 is not JSON" in bad["rows"][0]["cause"]
        none = A.deploy_source(lambda: {"state": "absent", "rows": []})
        assert none["rows"] == [] and "no deploy or restore recorded" in none["checked"]


# ---------------------------------------------------------------------------
# Source: the last baseline decision, recorded IN the commit it judged
# ---------------------------------------------------------------------------

from tests.test_intent_match import _broken, lab  # noqa: E402,F401  (the fixture)


def _message(repo):
    import subprocess
    return subprocess.run(["git", "-C", repo, "log", "-1", "--format=%B"],
                          capture_output=True, text=True).stdout


def _save(config, **kw):
    from modules.nsot.repo import GoldenItem, save_golden
    return save_golden("Lab", [GoldenItem("r2", config, "203.0.113.12")],
                       actor="t", **{"source": "save_all", "inventory_size": 1, **kw})


class TestTheBaselineDecisionIsDurable:
    def test_a_denial_is_recorded_in_the_commit_with_its_reasons(self, lab):
        repo, captured = lab
        out = _save(_broken(captured))
        assert out["ok"] and not out["baseline"]
        msg = _message(repo)
        assert "Baseline: denied: " in msg and "r2 does not match its committed intent" in msg

    def test_an_earned_baseline_is_recorded_too(self, lab):
        repo, captured = lab
        out = _save(captured)
        assert out["baseline"].startswith("baseline/")
        assert "Baseline: earned" in _message(repo)

    def test_a_save_that_never_claimed_the_network_records_no_decision(self, lab):
        """A single-device capture passes baseline=False with no reasons: it
        did not ask, so there is no decision to record."""
        repo, captured = lab
        _save(_broken(captured), source="capture", baseline=False)
        assert "Baseline:" not in _message(repo)

    def test_a_caller_that_decided_records_its_own_reasons(self, lab):
        """Deploy and restore measure coverage themselves and pass
        baseline=False: their reasons lived only in their report."""
        repo, captured = lab
        _save(_broken(captured), source="pipeline", baseline=False,
              baseline_reasons=["the batch targeted 1 of 9 inventory devices"])
        assert "Baseline: denied: the batch targeted 1 of 9 inventory devices" in _message(repo)


class TestBaselineAsASource:
    @pytest.fixture(autouse=True)
    def _list(self, monkeypatch):
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")

    def test_a_denial_is_a_row_with_its_reasons_and_its_time(self, lab):
        repo, captured = lab
        _save(_broken(captured))
        res = A.baseline_source()
        [r] = res["rows"]
        assert r["level"] == "warning" and "save_all" in r["what"]
        assert "r2 does not match its committed intent" in r["cause"]
        assert r["since"] and res["value_at"] == r["since"]
        assert "Save All" in r["action"]["label"]

    def test_a_later_earned_baseline_supersedes_it(self, lab):
        repo, captured = lab
        _save(_broken(captured))
        _save(captured)
        res = A.baseline_source()
        assert res["rows"] == [] and res["checked"].endswith(": earned")

    def test_a_later_capture_that_never_asked_does_not_hide_it(self, lab):
        """The NEWEST DECISION decides, not the newest commit: a one-device
        capture after a denial made no decision and must not clear it."""
        repo, captured = lab
        _save(_broken(captured))
        _save(captured, source="capture", baseline=False)
        assert len(A.baseline_source()["rows"]) == 1

    def test_no_decision_recorded_says_so_and_a_failed_read_is_a_row(self, lab):
        none = A.baseline_source(lambda: "")
        assert none["rows"] == [] and "no baseline decision recorded yet" in none["checked"]

        def boom():
            raise RuntimeError("git log failed: not a repository")
        bad = A.baseline_source(boom)
        assert bad["state"] == "unreadable" and "not a repository" in bad["rows"][0]["cause"]
