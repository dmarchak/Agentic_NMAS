"""A device's own save is never recorded or drawn as a rotation (C362; the operator,
2026-10-03: r2's History read "Persisted: rotated and persisted" after only Persist ran, a
false audit trail).

- At the source: `onboard._record_native_persist` (the device page's Persist,
  `nmas-persist-native`, adopt, onboarding's save) writes the save's OWN state, one of
  `cr.SAVE_STATES`, for every answer the save can give, and never one of
  `cr.ROTATION_STATES`; the two sets share nothing and no save state says "rotat".
- Every reader with the new states: job health reads a save as a save (its row's "what"
  and detail claim no rotation; a save that could not be judged keeps the last answer);
  History draws a save as kind `persist`, its line never "rotat".
- The host's existing rows: its ten rows (as measured on 2026-10-03, metadata only) hold
  five saves recorded with a rotation's state, derived here from their shape independently
  of `record_exceptions.ROW_EXCEPTIONS`, which must name exactly those five. History draws
  them as saves, marked corrected, with what they recorded and why; job health agrees.
- C363: a golden commit's known exception is drawn in History (it read a key no exception has).
"""

import json
import re

import pytest

from modules.nsot import credential_rotation as cr
from modules.nsot import onboard as _onboard
from modules.nsot import record_exceptions as X
from tests.test_device_v2 import _get, lab  # noqa: F401 (the fixture)

#: The real recorder, taken before a lab replaces it with a spy.
REAL_RECORD = _onboard._record_native_persist

ROTATE_STAGES = ["preflight", "confirmation", "generate", "stage", "invalidate_redaction_cache",
                 "original_session", "recheck_entry_kind", "push", "verify_new_credential",
                 "captured_type_9", "post_capture", "commit"]
CHAIN_STAGES = ["device_startup_config", "oxidized_row", "oxidized_reload", "fetch_confirmed",
                "clab_sync", "startup_file", "startup_applies", "startup_safe"]
SAVE_STAGES = ["device_startup_config"]


def _row(at, phase, via, device, state, stages, actor="person@example.invalid"):
    row = {"at": at, "phase": phase, "device": device, "state": state, "failed_stage": "",
           "actor": actor, "stages": [{"name": s, "ok": True, "reason": ""} for s in stages]}
    if via is not None:
        row["via"] = via
    return row


#: The host's rotation record as read on 2026-10-03 (`nmas-host nmas`, metadata only): every
#: row's time, phase, path, device, state and stage names as measured; actors replaced (the
#: CLI's three by one bare login, as measured), stage reasons left empty.
HOST_ROWS = [
    _row("2026-09-27T03:35:52Z", "rotate", None, "bp-ztp-a",
         "rotated_persistence_not_attempted", ROTATE_STAGES),
    _row("2026-09-27T03:48:44Z", "persist", None, "bp-ztp-a", "rotated_and_persisted",
         SAVE_STAGES, actor="operator"),
    _row("2026-09-27T03:58:29Z", "persist", None, "bp-ztp-a", "rotated_and_persisted",
         SAVE_STAGES, actor="operator"),
    _row("2026-09-27T04:00:22Z", "persist", None, "s1", "rotated_and_persisted",
         SAVE_STAGES, actor="operator"),
    _row("2026-09-28T07:02:40Z", "rotate", "onboarding phase 2", "probe-r1a",
         "rotated_persistence_not_attempted", ROTATE_STAGES),
    _row("2026-09-28T07:02:44Z", "persist", "onboarding phase 2", "probe-r1a",
         "rotated_and_persisted", SAVE_STAGES),
    _row("2026-09-29T16:41:50Z", "persist", "device page", "r2", "rotated_and_persisted",
         SAVE_STAGES),
    _row("2026-09-29T20:05:37Z", "rotate", "device page", "r2",
         "rotated_persistence_not_attempted", ROTATE_STAGES),
    _row("2026-09-29T20:08:48Z", "persist", "device page", "r2", "rotated_and_persisted",
         CHAIN_STAGES),
    _row("2026-10-03T06:50:31Z", "persist", "device page", "r2", "rotated_and_persisted",
         SAVE_STAGES),
]


def _plant(rows):
    """Into this test's own rotation record (conftest points the record at a temp file)."""
    with open(cr._rotation_record_path(), "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


class TestTheSaveRecordsItsOwnState:
    @pytest.mark.parametrize("answer, state", [
        ({"ok": True, "state": "persisted", "detail": "carries it"}, cr.SAVE_PERSISTED),
        ({"ok": False, "state": "not_persisted", "detail": "lacks one"}, cr.SAVE_NOT_PERSISTED),
        ({"ok": False, "state": "unknown", "detail": "no username line"}, cr.SAVE_UNVERIFIED),
        ({"ok": False, "detail": "the save or its read-back could not run"}, cr.SAVE_UNVERIFIED),
    ])
    def test_every_answer_records_a_save_state_never_a_rotations(self, answer, state):
        REAL_RECORD("r2", answer, "person@example.invalid", via="device page")
        row = cr.rotation_records()[-1]
        assert row["state"] == state
        assert row["state"] in cr.SAVE_STATES and row["state"] not in cr.ROTATION_STATES

    def test_the_two_vocabularies_share_nothing_and_a_save_never_says_rotated(self):
        assert len(cr.ROTATION_STATES) >= 8 and len(cr.SAVE_STATES) == 3
        assert not set(cr.SAVE_STATES) & set(cr.ROTATION_STATES)
        assert not [s for s in cr.SAVE_STATES if "rotat" in s]


def _rows(records, device="r2"):
    from modules import job_health
    return [r for r in job_health.rotation_rows(records=records, known=({device}, ""))
            if r["unit"] == f"rotation:{device}"]


class TestJobHealthReadsASave:
    def test_a_save_that_read_back_is_ok_and_claims_no_rotation(self):
        (row,) = _rows([_row("2026-10-03T06:50:31Z", "persist", "device page", "r2",
                             cr.SAVE_PERSISTED, SAVE_STAGES)])
        assert row["state"] == "ok"
        assert "rotat" not in (row["what"] + row["detail"]).lower()

    def test_a_save_that_did_not_carry_it_is_not_safe_and_claims_no_rotation(self):
        (row,) = _rows([_row("2026-10-03T06:50:31Z", "persist", "device page", "r2",
                             cr.SAVE_NOT_PERSISTED, SAVE_STAGES)])
        assert row["state"] == "not_safe_to_reboot"
        assert "rotat" not in (row["what"] + row["detail"]).lower()
        assert "nmas-persist-native r2" in row["action"]["command"]

    def test_a_save_that_could_not_be_judged_keeps_the_rotations_answer(self):
        (row,) = _rows([_row("2026-10-03T06:00:00Z", "rotate", "device page", "r2",
                             cr.ROTATED_PENDING_PERSIST, ROTATE_STAGES),
                        _row("2026-10-03T06:50:31Z", "persist", "device page", "r2",
                             cr.SAVE_UNVERIFIED, SAVE_STAGES)])
        assert row["state"] == "not_safe_to_reboot" and "persistence NOT ATTEMPTED" in row["detail"]

    def test_a_save_that_could_not_be_judged_alone_is_unknown(self):
        (row,) = _rows([_row("2026-10-03T06:50:31Z", "persist", "device page", "r2",
                             cr.SAVE_UNVERIFIED, SAVE_STAGES)])
        assert row["state"] == "unknown"

    def test_a_save_that_read_back_clears_a_rotation_it_finished(self):
        unsaved = _row("2026-10-03T06:00:00Z", "persist", "device page", "r2",
                       cr.ROTATED_UNVERIFIED, SAVE_STAGES)
        unsaved.update(failed_stage="device_startup_config")
        assert _rows([unsaved])[0]["state"] == "not_safe_to_reboot"
        assert _rows([unsaved, _row("2026-10-03T06:50:31Z", "persist", "device page", "r2",
                                    cr.SAVE_PERSISTED, SAVE_STAGES)])[0]["state"] == "ok"


def _saves_alone(rows):
    """The host's saves recorded as rotations, by SHAPE (independent of the exceptions
    table): one stage, the device's own save, outside an onboarding (whose rotation ran in
    the same operation), recorded with a rotation's state."""
    return {(r["device"], r["at"]) for r in rows
            if [s["name"] for s in r["stages"]] == SAVE_STAGES
            and r.get("via") != "onboarding phase 2" and r["state"] in cr.ROTATION_STATES}


class TestTheHostsRowsAreCorrected:
    def test_the_table_names_exactly_the_saves_recorded_as_rotations(self):
        assert len(HOST_ROWS) == 10
        assert set(X.ROW_EXCEPTIONS) == _saves_alone(HOST_ROWS)
        assert len(X.ROW_EXCEPTIONS) == 5

    def test_each_is_read_as_a_save_beside_what_it_recorded(self):
        _plant(HOST_ROWS)
        known = cr.rotation_records_as_known()
        corrected = [r for r in known if r.get("exception")]
        assert {(r["device"], r["at"]) for r in corrected} == set(X.ROW_EXCEPTIONS)
        assert {r["state"] for r in corrected} == {cr.SAVE_PERSISTED}
        assert {r["recorded_state"] for r in corrected} == {"rotated_and_persisted"}
        assert [r for r in cr.rotation_records() if r["state"] == "persisted"] == [], (
            "the record itself is never rewritten")
        assert [r["state"] for r in known if not r.get("exception")] == [
            r["state"] for r in HOST_ROWS if (r["device"], r["at"]) not in X.ROW_EXCEPTIONS]

    def test_a_row_at_the_same_time_with_another_state_is_not_corrected(self):
        other = dict(HOST_ROWS[-1], state=cr.ROTATED_UNVERIFIED)
        assert X.row_exception(other) is None
        assert X.row_exception(HOST_ROWS[-1])["was"] == cr.SAVE_PERSISTED

    def test_job_health_reads_r2_as_its_last_save(self):
        _plant(HOST_ROWS)
        (row,) = _rows(None)
        assert row["state"] == "ok" and "rotat" not in (row["what"] + row["detail"]).lower()

    def test_r2s_history_draws_both_saves_as_saves_marked_corrected(self, tmp_path, monkeypatch):
        from tests.test_persist_screen import lab as persist_lab
        built = persist_lab.__wrapped__(tmp_path, monkeypatch)
        _plant(HOST_ROWS)
        html = built["client"].get("/v2/device/r2/history").get_data(as_text=True)
        items = re.findall(r'<details class="hist-row tl-row"[^>]*>(.*?)</details>', html, re.S)
        line = lambda item: re.search(r'<summary class="hist-sum">(.*?)</summary>', item,  # noqa: E731
                                      re.S).group(1)
        saves = [i for i in items if "badge" in i and ">persist<" in line(i)]
        assert len(saves) == 2, len(saves)
        for item in saves:
            assert "Persisted: the startup config carries the running credential" in line(item)
            assert "corrected" in line(item) and "rotat" not in line(item).lower()
            assert "rotated_and_persisted" in item and "C362" in item
            assert "rotated nothing" in item, "the reason is drawn"
        assert "Rotation: rotated persistence not attempted" in html
        assert "Rotation&#39;s persistence: rotated and persisted" in html or \
            "Rotation's persistence: rotated and persisted" in html


def test_a_golden_commits_known_exception_is_drawn(lab, monkeypatch):  # noqa: F811
    """C363: History read the exception's `reason`; the table's key is `why`."""
    from modules.nsot import repo as R
    sha = R.golden_history(lab["repo"], "r3")[0]["sha"]
    monkeypatch.setitem(X.EXCEPTIONS, sha, dict(next(iter(X.EXCEPTIONS.values()))))
    html = _get(lab, "/v2/device/r3/history")[1]
    assert "record known wrong" in html
    assert "this commit is a credential rotation" in html
