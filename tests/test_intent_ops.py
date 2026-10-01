"""Revert and retry from the Device page (7.3), through the real routes and
`intent_ops`, on a real repository: r2's REAL config as its golden, full
intent seeded from it, then two intent edits, A and B.

Revert undoes ONE commit's change and keeps every later one; retry lifts a
rollback block with a stated reason. Two defects found building them: C213
(the retry log erased by one torn read) and C214 (any revert lifted the
rollback block). And C215, the deploy plan reading the ACTIVE list's
inventory, is pinned here with the plan's own `_artifact_for`.
"""

import json
import os
import subprocess

import pytest

from tests.conftest import TEST_PERSON
from tests.payload_render import lift, render_preview, render_result, shipped
from tests.test_seed_intent import LIST, build_seed_lab

HOST = "r2"
FAILED = ["interface GigabitEthernet2", " description CHANGED-BY-A", "exit"]


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True).stdout.strip()


def _edit(repo, mutate, subject):
    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars

    doc = hostvars.read_committed(repo, HOST)
    mutate(doc)
    hostvars.write_committed(repo, doc)
    assert save_host_vars(LIST, [HOST], actor="t", message=subject)["ok"]
    return _git(repo, "rev-parse", "HEAD")


def _set_description(text):
    def mutate(doc):
        doc["interfaces"][1]["description"] = text
    return mutate


def _add_ntp(doc):
    doc["ntp_servers"] = list(doc.get("ntp_servers") or []) + ["192.0.2.123"]


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from modules.nsot import seed

    lab = build_seed_lab(monkeypatch, tmp_path)
    entry = seed.entry_for(LIST, lab["device"])
    done = seed.apply(LIST, [lab["device"]], {HOST: entry["hash"]}, "t")
    assert done["save"]["ok"], done
    repo = lab["repo"]
    lab["a"] = _edit(repo, _set_description("CHANGED-BY-A"), "host_vars: r2 describe Gi2")
    lab["b"] = _edit(repo, _add_ntp, "host_vars: r2 add an NTP server")
    return lab


def _preview(lab, kind, **body):
    r = lab["client"].post(f"/templatize/{kind}/preview",
                           json={"list_name": LIST, "device": HOST, **body})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


def _target(d):
    return d["preview"]["what"]["targets"][0]


def _note(lab, applicability):
    """A rollback block recorded against A's change, and the classifier's
    answer fixed (its own tests drive the real one)."""
    from modules.nsot import hostvars
    hostvars.record_rolled_back(lab["repo"], HOST, lab["a"], reason="verify failed",
                                commands=FAILED)
    lab["applicability"] = applicability


@pytest.fixture
def classify(lab, monkeypatch):
    lab["applicability"] = "blocking"
    monkeypatch.setattr("routes.templatize.note_applicability",
                        lambda ln, h, has_intent=None: lab["applicability"])
    return lab


class TestRevertPreview:
    def test_it_draws_the_document_after_the_revert_and_writes_nothing(self, lab):
        head = _git(lab["repo"], "rev-parse", "HEAD")
        d = _preview(lab, "revert", sha=lab["a"][:12])
        t = _target(d)
        assert t["selectable"] and t["select_data"]["sha"] == lab["a"][:12]
        assert t["select_data"]["list"] == LIST, "the list rides to the apply"
        program = d["preview"]["targets"][0]["program"]
        assert any("CHANGED-BY-A" in l for l in program["lines"])
        notes = " ".join(program["notes"][0]["lines"])
        assert "interfaces.GigabitEthernet1.description: 'CHANGED-BY-A' ->" in notes
        said = " ".join(i["text"] for i in d["preview"]["what_not"]["items"])
        assert "Nothing is sent to the device" in said and "later intent commit is kept" in said
        assert _git(lab["repo"], "rev-parse", "HEAD") == head, "a preview commits nothing"
        assert "host_vars" not in _git(lab["repo"], "status", "--porcelain")
        assert "What will be committed as its intent" in render_preview(d["preview"])

    def test_the_default_commit_is_the_one_the_rollback_names(self, lab):
        from modules.nsot import hostvars
        hostvars.record_rolled_back(lab["repo"], HOST, lab["a"], commands=FAILED)
        d = _preview(lab, "revert")
        assert _target(d)["select_data"]["sha"] == lab["a"][:12]
        assert [c["rolled_back"] for c in d["commits"]][:2] == [False, True]

    def test_a_later_commit_on_the_same_setting_is_refused_by_name(self, lab):
        _edit(lab["repo"], _set_description("CHANGED-AGAIN"), "host_vars: r2 describe again")
        d = _preview(lab, "revert", sha=lab["a"][:12])
        t = _target(d)
        assert not t["selectable"] and "interfaces.GigabitEthernet1.description" in t["why_not"]


class TestRevertApply:
    def _apply(self, lab, d, **over):
        data = _target(d)["select_data"]
        body = {"list_name": data["list"], "device": HOST, "sha": data["sha"],
                "hash": data["hash"], **over}
        return lab["client"].post("/templatize/revert/apply", json=body)

    def test_it_undoes_one_commit_and_keeps_the_later_one(self, classify):
        lab = classify
        r = self._apply(lab, _preview(lab, "revert", sha=lab["a"][:12]))
        res = r.get_json()["result"]
        assert res["level"] == "success", res
        from modules.nsot import hostvars
        now = hostvars.read_committed(lab["repo"], HOST)
        assert now["interfaces"][1]["description"] != "CHANGED-BY-A"
        assert "192.0.2.123" in now["ntp_servers"], "B, the later commit, is kept"
        msg = _git(lab["repo"], "log", "-1", "--format=%B")
        assert "Source: revert" in msg and f"Reverts: {lab['a']}" in msg
        assert f"Actor: {TEST_PERSON}" in msg and "Actor-Verified: access" in msg
        # The statement names the revert commit, as git records it. (It asserted
        # `"abc" not in` the statement, a needle nothing planted: CI run #249's
        # commit was eabc1973..., and a 3-hex needle hits a sha ~1 time in 100.)
        head = _git(lab["repo"], "rev-parse", "HEAD").strip()
        assert head[:12] in res["record"]["statement"] and "Source: revert" in \
            res["record"]["statement"]
        assert "What was reverted" in render_result(res)

    def test_c214_a_standing_block_is_not_lifted_by_a_revert(self, classify):
        lab = classify
        _note(lab, "blocking")
        res = self._apply(lab, _preview(lab, "revert", sha=lab["b"][:12])).get_json()["result"]
        from modules.nsot import hostvars
        assert hostvars.rolled_back_note(lab["repo"], HOST) is not None, "the block stands"
        assert res["level"] == "partial"
        assert "STANDS" in res["happened"]["summary"]

    def test_c214_a_block_measured_gone_is_cleared(self, classify):
        lab = classify
        _note(lab, "no longer applies")
        res = self._apply(lab, _preview(lab, "revert", sha=lab["a"][:12])).get_json()["result"]
        from modules.nsot import hostvars
        assert hostvars.rolled_back_note(lab["repo"], HOST) is None
        assert res["level"] == "success" and "lifted" in res["happened"]["summary"]

    def test_intent_that_moved_since_the_preview_commits_nothing(self, lab):
        d = _preview(lab, "revert", sha=lab["a"][:12])
        _edit(lab["repo"], lambda doc: doc.update(domain_name="moved.example"),
              "host_vars: r2 domain")
        head = _git(lab["repo"], "rev-parse", "HEAD")
        res = self._apply(lab, d).get_json()["result"]
        assert res["targets"][0]["outcome"] == "moved"
        assert _git(lab["repo"], "rev-parse", "HEAD") == head

    def test_a_failed_commit_puts_the_file_back(self, lab, monkeypatch):
        before = _git(lab["repo"], "status", "--porcelain")
        d = _preview(lab, "revert", sha=lab["a"][:12])
        monkeypatch.setattr("modules.nsot.repo.save_host_vars",
                            lambda *a, **k: {"ok": False, "error": "planted"})
        res = self._apply(lab, d).get_json()["result"]
        assert res["targets"][0]["outcome"] == "failed" and res["level"] == "failed"
        assert _git(lab["repo"], "status", "--porcelain") == before, "no residue"

    def test_a_held_device_is_refused_with_nothing_committed(self, lab):
        import threading

        from modules.nsot import device_ops
        d = _preview(lab, "revert", sha=lab["a"][:12])
        held, done = threading.Event(), threading.Event()

        def other():
            with device_ops.hold(LIST, HOST, "deploy", "someone@example.com"):
                held.set()
                done.wait(10)

        t = threading.Thread(target=other)
        t.start()
        try:
            assert held.wait(10)
            res = self._apply(lab, d).get_json()["result"]
        finally:
            done.set()
            t.join(10)
        assert res["targets"][0]["outcome"] == "busy"
        assert _git(lab["repo"], "log", "-1", "--format=%s").startswith("host_vars: r2 add")

    def test_the_apply_needs_its_list(self, lab):
        r = lab["client"].post("/templatize/revert/apply",
                               json={"device": HOST, "sha": "x", "hash": "y"})
        assert r.status_code == 400 and "never from whichever list is active" in \
            r.get_json()["error"]

    def test_a_device_the_list_does_not_hold_is_refused(self, lab):
        r = lab["client"].post("/templatize/revert/preview",
                               json={"list_name": LIST, "device": "r9"})
        assert r.status_code == 404 and "not in Lab's inventory" in r.get_json()["error"]


class TestRetry:
    def _apply(self, lab, d, reason):
        data = _target(d)["select_data"]
        return lab["client"].post("/templatize/retry/apply", json={
            "list_name": data["list"], "device": HOST, "hash": data["hash"],
            "reason": reason}).get_json()["result"]

    def test_no_block_is_nothing_to_retry(self, lab):
        t = _target(_preview(lab, "retry"))
        assert not t["selectable"] and "nothing to retry" in t["why_not"]

    def test_a_block_that_no_longer_applies_is_not_offered(self, classify):
        lab = classify
        _note(lab, "no longer applies")
        t = _target(_preview(lab, "retry"))
        assert not t["selectable"] and "would authorise nothing" in t["why_not"]

    def test_a_standing_block_is_drawn_with_its_program_and_history(self, classify):
        lab = classify
        _note(lab, "blocking")
        d = _preview(lab, "retry")
        assert _target(d)["selectable"]
        target = d["preview"]["targets"][0]
        assert target["program"]["lines"] == FAILED
        ops = {o["name"]: o["value"] for o in target["operands"]}
        assert ops["retried before on this device"] == "never"
        assert ops["applies now"] == "blocking"

    @pytest.mark.parametrize("reason", ["", "ok", "retry the rolled-back change"])
    def test_a_reason_that_is_not_the_shape_of_one_is_refused(self, classify, reason):
        lab = classify
        _note(lab, "blocking")
        res = self._apply(lab, _preview(lab, "retry"), reason)
        assert res["targets"][0]["outcome"] == "refused" and "reason" in \
            res["targets"][0]["reason"]
        from modules.nsot import hostvars
        assert hostvars.rolled_back_note(lab["repo"], HOST) is not None

    def test_a_stated_reason_lifts_the_block_and_is_recorded(self, classify):
        lab = classify
        _note(lab, "blocking")
        res = self._apply(lab, _preview(lab, "retry"), "the link was down for maintenance")
        assert res["level"] == "success", res
        from modules.nsot import hostvars
        assert hostvars.rolled_back_note(lab["repo"], HOST) is None
        log = hostvars.retry_log(lab["repo"])
        assert [(e["device"], e["actor"], e["reason"]) for e in log] == [
            (HOST, TEST_PERSON, "the link was down for maintenance")]
        assert "stated reason, as testimony" in render_result(res)
        _note(lab, "blocking")
        ops = {o["name"]: o["value"] for o in
               _preview(lab, "retry")["preview"]["targets"][0]["operands"]}
        assert ops["retried before on this device"].startswith("1 time(s)")

    def test_a_block_that_changed_since_the_preview_is_refused(self, classify):
        lab = classify
        _note(lab, "blocking")
        d = _preview(lab, "retry")
        from modules.nsot import hostvars
        hostvars.record_rolled_back(lab["repo"], HOST, lab["b"], commands=FAILED + ["x"])
        res = self._apply(lab, d, "the link was down for maintenance")
        assert res["targets"][0]["outcome"] == "moved"

    def test_c213_an_unreadable_retry_log_refuses_and_keeps_the_block(self, classify):
        lab = classify
        _note(lab, "blocking")
        from modules.nsot import hostvars
        path = os.path.join(lab["repo"], hostvars.RETRY_LOG_REL)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('[{"device": "r2", "reason": "an earlier retry"')    # torn
        d = _preview(lab, "retry")
        ops = {o["name"]: o["value"] for o in d["preview"]["targets"][0]["operands"]}
        assert ops["retried before on this device"].startswith("could not be read")
        res = self._apply(lab, d, "the link was down for maintenance")
        assert res["targets"][0]["outcome"] == "failed"
        assert "block stands" in res["targets"][0]["reason"]
        assert hostvars.rolled_back_note(lab["repo"], HOST) is not None
        kept = [f for f in os.listdir(os.path.dirname(path)) if ".corrupt-" in f]
        assert kept, "the damaged log is kept, never replaced by a one-entry list"


class TestOneClassifier:
    def test_the_list_and_the_screens_ask_the_same_function(self):
        import inspect

        import routes.templatize as T
        from modules.nsot import intent_ops
        assert "note_applicability(" in inspect.getsource(T.rolled_back_notes)
        assert "note_applicability" in inspect.getsource(intent_ops._applicability)


class TestC215ThePlanReadsItsOwnList:
    """`_artifact_for(list_name, …)` read the device row from the ACTIVE list,
    and a miss took `platform_for_device({})`: on probe-r1a's real repository
    the plan chose the IOS template for an IOS-XE device."""

    @pytest.fixture
    def plan(self, monkeypatch):
        import routes.deploy as rd
        from modules import device
        from modules.nsot import templates_repo

        rows = {"A": [{"hostname": HOST, "platform": "cisco_ios"}],
                "B": [{"hostname": HOST, "platform": "cisco_iosxe"}], "C": []}
        asked = []
        monkeypatch.setattr(rd, "_repo_for", lambda ln: "/nonexistent")
        monkeypatch.setattr(rd, "_captured_record", lambda repo, h: {"text": "hostname r2\n",
                                                                    "refused": ""})
        monkeypatch.setattr(device, "get_current_device_list", lambda: ("A", "a.csv"))
        monkeypatch.setattr(device, "load_saved_devices", lambda p=None: rows["A"])
        monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: rows[ln])

        def template_for(repo, h, platform):
            asked.append(platform)
            raise RuntimeError("stop here: the platform is what is measured")

        monkeypatch.setattr(templates_repo, "template_for_device", template_for)
        return rd, asked

    def test_a_plan_for_one_list_reads_that_lists_row(self, plan):
        rd, asked = plan
        with pytest.raises(RuntimeError):
            rd._artifact_for("B", HOST)
        assert asked == ["cisco_iosxe"], "list B's row, while list A is active"

    def test_a_device_the_list_does_not_hold_is_refused_never_defaulted(self, plan):
        rd, asked = plan
        built, err = rd._artifact_for("C", HOST)
        assert built is None and "not in C's inventory" in err
        assert asked == [], "no template was chosen for a device with no row"


class TestTheShippedClient:
    def _button(self, kind, preview, reason):
        import dukpy
        js = (lift(shipped("nmas_preview_confirm.js"), "previewConfirmButton") + "\n"
              + lift(shipped("nmas_intent_ops.js"), "intentOpButton"))
        return dukpy.evaljs(js + f"\nintentOpButton({json.dumps(kind)}, "
                                 f"{json.dumps(preview)}, {json.dumps(reason)})")

    def test_a_retry_needs_a_reason_typed(self, classify):
        lab = classify
        _note(lab, "blocking")
        p = _preview(lab, "retry")["preview"]
        assert self._button("retry", p, "  ") == {"disabled": True,
                                                   "text": "State a reason first"}
        assert self._button("retry", p, "the link was down")["disabled"] is False

    def test_the_commit_chooser_escapes_and_marks_the_rolled_back_commit(self):
        import dukpy
        js = lift(shipped("nmas_intent_ops.js"), "esc") + "\n" + lift(
            shipped("nmas_intent_ops.js"), "revertCommitChooser")
        html = dukpy.evaljs(js + "\nrevertCommitChooser(" + json.dumps([
            {"sha": "aaa", "date": "d", "subject": "<b>x</b>", "rolled_back": True},
            {"sha": "bbb", "date": "d", "subject": "y", "rolled_back": False}]) + ", 'bbb')")
        assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x" not in html
        assert "(the change a rollback undid)" in html
        assert '<option value="bbb" selected>' in html

    def test_the_device_page_offers_both(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        page = open(os.path.join(root, "templates", "device.html"), encoding="utf-8").read()
        assert 'onclick="openRevert(this.dataset.hostname)"' in page
        assert 'onclick="openRetry(this.dataset.hostname)"' in page
