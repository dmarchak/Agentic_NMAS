"""The controller app deploy as one operation (P6, C2677; the signed board
docs/boards/controller-app-deploy.html): its receipt store and Mercury's record of a controller's
set (K2, `modules/controller_deploy_receipts.py`), and the preview and the confirm's held run
(`modules/apps/deploy_op.py`).

Cases, each planted:
- the receipt is masked at rest and owner-only; a line that will not parse makes the store
  unreadable, never a shorter list;
- the record is the last receipt whose outcome left the controller running a request Mercury
  recorded (deployed, rolled back to the request before, not rolled back after an apply that
  succeeded); apply failed and refused leave the one before deciding; an unknown outcome is
  unknown, said; none is none;
- the plan's rollback target is the record's request (`channel.plan`'s *previous*), and an
  unreadable store refuses the preview;
- a source that is not wired is a refusal naming what is not built, never an empty set;
- the set the controller already runs, with the drop-in its render, changes nothing (K4), and
  the confirm's words name a redeploy, a first deploy's missing rollback and what the
  post-check expects to recover (K3, K6);
- the confirm holds the controller for the whole operation, makes the plan again and refuses a
  moved hash naming what moved, both hashes, before any window or send; a controller held by
  another operation is refused by name; a miss rolls back to the recorded request, its files
  staged again from their pins; every outcome writes its receipt, the window is declared
  before the send and ended when the post-check passes."""

import json
import os
import stat
import subprocess

import pytest

from modules import controller_deploy_receipts as deploy_receipts
from modules.apps import channel, deploy_op, post_check
from modules.apps.manifest import parse_manifest
from modules.jobs.lifecycle import Version, content_hash
from modules.nsot import device_ops
from tests.test_controller_deploy import (ALL_BACK, GIT_ENV, LISTEN, MANAGER, SWITCH_2_DOWN,
                                          UNIT, Clock, eos, link, ls, show)

NET = "lab9"
CTL = "ctl"
DEV = {"hostname": CTL, "ip": "192.0.2.50", "device_type": "linux", "username": "mercury"}
HEADER = f"# /etc/systemd/system/{UNIT}.d/mercury.conf"


@pytest.fixture(autouse=True)
def _receipts_here(tmp_path, monkeypatch):
    """The receipts and the planned-restart record in this test's own folder, never the
    store's (C571, C1864)."""
    from modules import restarts

    where = tmp_path / "receipts"
    monkeypatch.setattr(deploy_receipts, "path_for",
                        lambda network: str(where / network / deploy_receipts.FILENAME))
    (tmp_path / "restarts").mkdir()
    monkeypatch.setattr(restarts, "_data", lambda name: str(tmp_path / "restarts" / name))


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          env=dict(os.environ, **GIT_ENV)).stdout.decode().strip()


def a_manifest(name, version):
    return parse_manifest(
        f"name: {name}\nversion: {version}\ncontrollers:\n  ryu: \">=4.34\"\n"
        "openflow_versions: [\"1.0\", \"1.3\"]\nrequires: []\nconfig_schema: {type: object}\n"
        f"rest:\n  prefix: /{name}\n  endpoints:\n    - path: /health\n      methods: [GET]\n")


def registry(tmp_path, name="of_versions", versions=("1.0.0", "1.1.0")):
    """A code repository with one commit per version of *name*, each Published at its pin."""
    repo = tmp_path / "code"
    folder = repo / "apps" / name
    folder.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    out = []
    for v in versions:
        (folder / f"{name}.py").write_bytes(f"VERSION = {v!r}\n".encode())
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", v)
        rev = git(repo, "rev-parse", "HEAD")
        pin = content_hash(repo, f"apps/{name}", rev)
        out.append({"version": Version(kind="app", name=name, version=v, author="a@example.invalid",
                                       state="published", reviewer="r@example.invalid",
                                       content_sha256=pin),
                    "manifest": a_manifest(name, v), "repo": str(repo), "path": f"apps/{name}",
                    "rev": rev, "commit": rev})
    return {"state": "ok", "apps": [{"name": name, "versions": out}], "repo": {}, "error": ""}


class FakeSources(deploy_op.Sources):
    def __init__(self, tmp_path, cat="", reads=None, outcomes=None, user="ryu"):
        self.reg = registry(tmp_path)
        self.cat, self.user = cat, user
        self.reads = list(reads or [])
        self.outcomes = list(outcomes or [])
        self.sent, self.held_at_send, self.hashes = [], [], []

    def controllers(self, network):
        return {"state": "ok", "error": "", "controllers": [
            {"name": CTL, "unit": UNIT, "dev": dict(DEV), "listen": dict(LISTEN)}]}

    def registered(self, network):
        return self.reg

    def host_reads(self, network, controller):
        return {"state": "ok", "show": show(self.user), "ls": ls("mercury"), "cat": self.cat,
                "at": "2026-11-08T05:00:00Z", "error": ""}

    def expected(self, network, controller):
        return {"state": "ok", "error": "",
                "switches": [eos("sw-a"), dict(eos("sw-b"), dpid=2)],
                "links": [link(1, 1, 2, 1)]}

    def observe(self, network, controller, apps=None):
        return self.reads.pop(0) if self.reads else SWITCH_2_DOWN

    def controller_read(self, network, controller):
        return {"state": "ok", "at": "2026-11-08T05:00:00Z", "show": show(self.user),
                "cat": self.cat,
                "health": {}, "observed": None, "error": ""}

    def send(self, dev, tplan):
        self.sent.append(tplan)
        self.held_at_send.append(device_ops.may_write(dev["ip"]))
        # The staged folders' hashes as sent (the job removes its folders when it ends).
        self.hashes.append({n: channel.script().folder_hash(f)
                            for n, f in (tplan.get("folders") or {}).items()})
        outcome = self.outcomes.pop(0) if self.outcomes else {"ok": True, "up_after_s": 3.0}
        return {"ok": bool(outcome.get("ok")), "step": "done", "error": outcome.get("error", ""),
                "staged": ["x"], "not_staged": [], "request_written": True,
                "command_sent": True, "printed": outcome, "outcome": outcome}


ALL_BACK_TWO = dict(ALL_BACK, health={"of_versions": {"ok": True}})


def receipt(outcome, request=None, before=None, **extra):
    return dict({"controller": CTL, "actor": "op@example.invalid", "outcome": outcome,
                 "request": request, "before": before or {}}, **extra)


REQ_A = {"apps": [{"name": "of_versions", "version": "1.0.0", "sha256": "a" * 64}],
         "listen": LISTEN}
REQ_B = {"apps": [{"name": "of_versions", "version": "1.1.0", "sha256": "b" * 64}],
         "listen": LISTEN}


# ── the receipt store ────────────────────────────────────────────────────────────────────────

def test_a_receipt_is_masked_at_rest_and_owner_only():
    got = deploy_receipts.write(NET, receipt(
        "apply failed", REQ_A, error="the line was: snmp-server community s3cr3tcomm RO",
        steps=[{"step": "apply", "error": "snmp-server community s3cr3tcomm RO"}]))
    assert got["ok"], got
    path = deploy_receipts.path_for(NET)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert "s3cr3tcomm" not in text and text.count("redacted:snmp_community") == 2
    [row] = deploy_receipts.read(NET)["rows"]
    assert row["outcome"] == "apply failed" and row["network"] == NET and row["id"]


def test_a_line_that_will_not_parse_makes_the_store_unreadable():
    deploy_receipts.write(NET, receipt("deployed", REQ_A))
    with open(deploy_receipts.path_for(NET), "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    got = deploy_receipts.read(NET)
    assert got["state"] == "unreadable" and got["rows"] == []
    rec = deploy_receipts.record(NET, CTL)
    assert rec["state"] == "unreadable" and "cannot be read" in rec["words"]


def test_no_receipt_is_none_and_absent_is_not_unreadable():
    assert deploy_receipts.read(NET)["state"] == "absent"
    rec = deploy_receipts.record(NET, CTL)
    assert rec["state"] == "none" and rec["request"] is None
    assert rec["words"] == f"no deploy through Mercury is recorded for {CTL}"


@pytest.mark.parametrize("rows, state, runs", [
    ([receipt("deployed", REQ_A)], "ok", REQ_A),
    ([receipt("deployed", REQ_A), receipt("apply failed", REQ_B)], "ok", REQ_A),
    ([receipt("deployed", REQ_A), receipt("refused", REQ_B)], "ok", REQ_A),
    ([receipt("rolled back", REQ_B, before={"kind": "request", "request": REQ_A})], "ok", REQ_A),
    ([receipt("rolled back", REQ_B, before={"kind": "dropin_before", "request": None})],
     "none", None),
    ([receipt("not rolled back", REQ_B, post_check={"ok": False})], "ok", REQ_B),
    ([receipt("deployed", REQ_A), receipt("not rolled back", REQ_B)], "unknown", None),
    ([receipt("deployed", REQ_A), receipt("unknown", REQ_B)], "unknown", None),
    ([receipt("deployed", REQ_A), receipt("rollback failed", REQ_B)], "unknown", None),
])
def test_the_record_is_the_last_receipt_that_left_the_controller_running_a_request(
        rows, state, runs):
    for r in rows:
        assert deploy_receipts.write(NET, r)["ok"]
    deploy_receipts.write(NET, dict(receipt("deployed", REQ_B), controller="another"))
    rec = deploy_receipts.record(NET, CTL)
    assert rec["state"] == state and rec["request"] == runs, rec


# ── the preview ───────────────────────────────────────────────────────────────────────────────

def test_a_source_not_wired_refuses_naming_what_is_not_built():
    got = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=deploy_op.Unwired())
    assert got["ok"] is False
    assert got["refusals"] == [f"{NET}'s controllers: {deploy_op.NOT_WIRED['controllers']}"]


def test_the_record_s_request_is_the_plan_s_rollback_target(tmp_path):
    src = FakeSources(tmp_path)
    first = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    assert first["ok"], first["refusals"]
    assert first["rollback"]["request"] is None and first["record"]["state"] == "none"
    deploy_receipts.write(NET, receipt("deployed", first["request"]))
    got = deploy_op.preview(NET, CTL, {"of_versions": "1.1.0"}, src=src)
    assert got["ok"], got["refusals"]
    assert got["rollback"]["kind"] == "request" and got["rollback"]["request"] == first["request"]
    assert got["change"] == [{"name": "of_versions", "from": "1.0.0", "to": "1.1.0"}]
    assert deploy_op.confirm_words(got) == "Deploy of_versions 1.1.0 and restart ctl"


def test_an_unreadable_record_refuses_the_preview(tmp_path):
    os.makedirs(os.path.dirname(deploy_receipts.path_for(NET)))
    with open(deploy_receipts.path_for(NET), "w", encoding="utf-8") as fh:
        fh.write("not json\n")
    got = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=FakeSources(tmp_path))
    assert got["ok"] is False
    assert any("so what a miss rolls back to is not known" in r for r in got["refusals"])


def test_a_version_not_registered_is_refused_naming_the_versions_there_are(tmp_path):
    got = deploy_op.preview(NET, CTL, {"of_versions": "9.9.9"}, src=FakeSources(tmp_path))
    assert got["refusals"] == ["of_versions has no registered version 9.9.9 (its versions: "
                               "1.0.0, 1.1.0)"]


def test_the_set_the_controller_runs_changes_nothing_and_offers_the_redeploy(tmp_path):
    src = FakeSources(tmp_path)
    first = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    deploy_receipts.write(NET, receipt("deployed", first["request"]))
    src.cat = f"# /lib/systemd/system/{UNIT}\n[Service]\n\n{HEADER}\n{first['dropin_after']}"
    again = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    assert again["ok"] and again["nothing"] is True and again["change"] == []
    assert deploy_op.confirm_words(again) == "Redeploy the same set and restart ctl"
    moved = deploy_op.preview(NET, CTL, {"of_versions": "1.1.0"}, src=src)
    assert moved["nothing"] is False


def test_a_first_deploy_s_confirm_names_no_rollback_and_what_must_recover(tmp_path):
    src = FakeSources(tmp_path)
    src.observe = lambda n, c, apps=None: dict(ALL_BACK, health={"of_versions": {"ok": False,
                                                                      "error": "503"}})
    got = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    assert deploy_op.confirm_words(got) == (
        "Deploy of_versions 1.0.0 and restart ctl, with no rollback, expecting of_versions's "
        "/health to recover")


@pytest.mark.parametrize("text, said", [
    ("of_versions", "'of_versions' is not name=version"),
    ("a=1.0.0,a=1.1.0", "the set names a twice"),
    ("A=1.0.0", "'A=1.0.0' is not name=version"),
])
def test_a_malformed_set_is_refused_naming_it(text, said):
    with pytest.raises(deploy_op.Refused, match=said):
        deploy_op.parse_set(text)


# ── the confirm's held run ───────────────────────────────────────────────────────────────────

def run(src, chosen, confirmed, then=None):
    clock = Clock()
    return deploy_op.run("job-1", NET, CTL, chosen, confirmed, then_parts=then or {},
                         actor="op@example.invalid", actor_verified="access", src=src,
                         clock=clock, sleep=clock.sleep, now=lambda: 1_800_000_000 + clock())


def planned_windows():
    from modules import restarts
    return [p for p in restarts.planned_rows() if p.get("list") == NET]


def test_a_confirmed_plan_is_held_throughout_deployed_and_recorded_with_its_window_ended(
        tmp_path):
    src = FakeSources(tmp_path)
    shown = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    src.reads = [ALL_BACK_TWO]
    got = run(src, {"of_versions": "1.0.0"}, shown["plan_sha256"], shown["parts"])
    assert got["outcome"] == "deployed" and got["written"], got
    assert src.held_at_send == [True]
    assert src.sent[0]["request"] == shown["request"]
    [row] = deploy_receipts.read(NET)["rows"]
    assert row["outcome"] == "deployed" and row["plan_sha256"] == shown["plan_sha256"]
    assert row["actor"] == "op@example.invalid" and row["actor_verified"] == "access"
    assert row["window"]["ended"] is True and row["post_check"]["ok"] is True
    [window] = planned_windows()
    assert window["devices"] == [CTL]
    assert deploy_receipts.record(NET, CTL)["request"] == shown["request"]
    assert not device_ops.held(NET)


def test_a_plan_that_moved_since_the_preview_sends_nothing_and_names_what_moved(tmp_path):
    src = FakeSources(tmp_path)
    shown = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    src.cat = f"{HEADER}\n[Service]\nUser=ryu\n"
    got = run(src, {"of_versions": "1.0.0"}, shown["plan_sha256"], shown["parts"])
    assert got["outcome"] == "refused" and src.sent == [] and planned_windows() == []
    [row] = deploy_receipts.read(NET)["rows"]
    now = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    assert row["error"].startswith(
        f"the plan made again at the confirm, holding {CTL}, has hash {now['plan_sha256']}, "
        f"and you confirmed {shown['plan_sha256']}. What moved: the drop-in before (")
    assert "the rollback target (" in row["error"] and "the request (" not in row["error"]
    assert row["error"].endswith("Nothing was staged or sent")


def test_a_controller_held_by_another_operation_is_refused_by_name(tmp_path):
    src = FakeSources(tmp_path)
    shown = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    with device_ops.hold(NET, CTL, "reload", "other@example.invalid"):
        import threading
        out = {}
        t = threading.Thread(target=lambda: out.update(
            run(src, {"of_versions": "1.0.0"}, shown["plan_sha256"])))
        t.start()
        t.join(30)
    assert out["outcome"] == "refused" and src.sent == []
    [row] = deploy_receipts.read(NET)["rows"]
    assert f"{CTL} is held by another operation (" in row["error"]
    assert "other@example.invalid" in row["error"] and "this is not queued" in row["error"]


def test_a_miss_rolls_back_to_the_recorded_request_staged_again_from_its_pins(tmp_path):
    src = FakeSources(tmp_path)
    first = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    src.reads = [ALL_BACK_TWO]
    assert run(src, {"of_versions": "1.0.0"}, first["plan_sha256"])["outcome"] == "deployed"
    misses = [SWITCH_2_DOWN] * (int(post_check.bound()["seconds"] // post_check.POLL_S) + 1)
    src.sent, src.hashes, src.held_at_send = [], [], []
    shown = deploy_op.preview(NET, CTL, {"of_versions": "1.1.0"}, src=src)
    src.reads = misses + [ALL_BACK_TWO]
    got = run(src, {"of_versions": "1.1.0"}, shown["plan_sha256"])
    assert got["outcome"] == "rolled back", got
    assert [t["request"] for t in src.sent] == [shown["request"], first["request"]]
    assert src.hashes[1] == {"of_versions": first["request"]["apps"][0]["sha256"]}
    assert src.held_at_send == [True, True]
    row = deploy_receipts.read(NET)["rows"][0]
    assert row["before"]["kind"] == "request" and row["before"]["request"] == first["request"]
    assert deploy_receipts.record(NET, CTL)["request"] == first["request"]


def test_a_controller_whose_login_is_not_the_deploy_account_is_refused(tmp_path):
    src = FakeSources(tmp_path)
    src.controllers = lambda n: {"state": "ok", "error": "", "controllers": [
        {"name": CTL, "unit": UNIT, "dev": dict(DEV, username="root"), "listen": LISTEN}]}
    got = run(src, {"of_versions": "1.0.0"}, "f" * 64)
    assert got["outcome"] == "refused" and src.sent == []
    [row] = deploy_receipts.read(NET)["rows"]
    assert row["error"] == (f"{CTL}'s driver is 'linux' and its login 'root'; the deploy needs "
                            "'linux' and the deploy account 'mercury'. Nothing was sent")


def test_an_outcome_not_read_is_unknown_and_never_rolled_back(tmp_path):
    src = FakeSources(tmp_path)
    shown = deploy_op.preview(NET, CTL, {"of_versions": "1.0.0"}, src=src)
    src.send = lambda dev, tplan: {"ok": False, "step": "done", "command_sent": True,
                                   "error": "outcome.json did not read", "printed": None,
                                   "outcome": None, "staged": [], "not_staged": []}
    got = run(src, {"of_versions": "1.0.0"}, shown["plan_sha256"])
    assert got["outcome"] == "unknown"
    row = deploy_receipts.read(NET)["rows"][0]
    assert row["window"]["ended"] is False and row["rollback_target"] == ""
    assert json.dumps(row).count("rollback apply") == 0


# ── Needs attention (artboard I) ─────────────────────────────────────────────────────────────

def _rows(*receipts_):
    from modules import attention
    for r in receipts_:
        deploy_receipts.write(NET, r)
    got = attention.controller_deploy_source(found={NET: deploy_receipts.read(NET)}, now=2e9)
    return got["rows"]


@pytest.mark.parametrize("outcome, kind, level", [
    ("unknown", "outcome_unknown", "unknown"),
    ("rollback failed", "not_back", "danger"),
    ("not rolled back", "not_back", "danger"),
])
def test_a_deploy_left_unknown_or_not_back_is_a_row_with_its_receipt(outcome, kind, level):
    [r] = _rows(receipt("deployed", REQ_A), receipt(outcome, REQ_B, error="it missed"))
    assert (r["kind"], r["level"], r["devices"]) == (kind, level, [CTL])
    assert r["action"]["href"].startswith(f"/v2/sdn/apps?list={NET}&receipt=")
    assert "it missed" in r["cause"] and r["clears"]["ways"] == ["resolves"]


@pytest.mark.parametrize("later, rows", [("deployed", 0), ("rolled back", 0), ("refused", 1),
                                         ("apply failed", 1)])
def test_the_row_clears_by_a_later_deploy_that_leaves_a_known_set(later, rows):
    assert len(_rows(receipt("unknown", REQ_B), receipt(later, REQ_A))) == rows


def test_unreadable_receipts_are_a_row_never_silence():
    from modules import attention
    got = attention.controller_deploy_source(found={NET: {"state": "unreadable", "rows": [],
                                                          "error": "planted"}}, now=2e9)
    [r] = got["rows"]
    assert r["kind"] == "unreadable" and "planted" in r["cause"]
