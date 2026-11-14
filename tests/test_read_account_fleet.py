"""Board R (provisional, operator review pending; the operator, 2026-11-13): the read-only account
on the devices, Credentials › Profiles (`modules/nsot/read_account.py`, its reader
`modules/readers/read_account_coverage.py`, routes/credential_profiles_v2.py). On a credential
store in this test's own folder and r2's real capture and committed intent
(`tests.test_capture.build_capture_lab`); no device: the rollout's apply is the batch deploy's,
faked where it would send (`routes.deploy.apply_batch`), as tests/test_fleet_change_run.py does.

- **Coverage** says, per device, what its committed intent and golden hold of the account and
  its newest probe record, by state: no read-only account, can't be added (a golden holding it
  at another level), intent says it and not deployed yet, not yet, on the device and not in
  intent, holds it. Never a password; a golden's line is reduced to a name and a level.
- **The view** leads with the summary, groups by state (the states to act on first), cuts an
  open group at `GROUP_ROWS` saying how many it leaves (900 devices), and says a filter is a
  subset.
- **Add** previews and writes nothing (HEAD and the working tree unmoved); the preview names the
  intent change and the lines a deploy will send for the dialect (the telemetry line and the
  level-1 restore on IOS-XE), masked, and refuses a device by name; the commit is refused,
  naming both hashes, when the preview moved, and otherwise is one commit per network, as the
  person, with `Source: read-account-add`, the reason and the preview's hash.
- **The rollout** orders the canary alone, then waves, then each management-path carrier last
  and alone; the run pauses after the canary; a carrier's wave needs the confirm naming it; the
  first failure stops it; a moved plan refuses the run naming both hashes.
- **The routes** draw the held coverage (never computing it), the Add's preview and its refusal.

IPv6: nothing here parses or connects to an address; the account's lines are the same for IPv4
and IPv6 management (`privilege_exec`'s forms carry both), and the lab's device has no address
in any assertion.
"""

import json
import os
import subprocess

import pytest

from modules import credentials as C
from modules.nsot import read_account as RA

RO, RO_PW = "mercury-ro", "ReadOnly-Not-Real-7731"
ROW = {"hostname": "r2", "device_type": "cisco_xe", "platform": "cisco_iosxe"}
ACCOUNTS = {"default": {"username": RO, "password_set": True}}


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          check=True).stdout.strip()


# ── coverage, pure ────────────────────────────────────────────────────────────────────────────

class TestGoldenAccounts:
    def test_a_line_naming_no_privilege_is_level_one_and_no_value_is_kept(self):
        text = ("hostname r2\n"
                f"username {RO} secret 9 $9$NotRealSalt$abcdefghijklmnop\n"
                "username admin privilege 15 secret 9 $9$Other$qrstuvwxyz\n"
                " username indented privilege 3 secret 0 nope\n")
        got = RA.golden_accounts(text)
        assert got == {RO: 1, "admin": 15}
        assert "$9$" not in json.dumps(got)


class TestJudge:
    def _j(self, intent=None, golden=None, accounts=ACCOUNTS, probe=None):
        return RA.judge(ROW, "Lab", intent, golden, accounts, probe, target=3)

    def _intent(self, level):
        return {"users": [{"privilege": level, "secret_ref": "read-account:profile:default"}]}

    def test_no_profile_carries_one(self):
        got = self._j(golden={}, accounts={})
        assert got["state"] == "no_account" and "no read-only account resolves for r2" in got["why"]
        assert "default" in got["why"]

    def test_a_golden_holding_it_at_another_level_cannot_take_it(self):
        got = self._j(golden={RO: 1})
        assert got["state"] == "would_change"
        assert "level 1" in got["why"] and "CredentialWouldChange" in got["why"]

    def test_both_say_it_at_the_level(self):
        got = self._j(intent=self._intent(3), golden={RO: 3})
        assert got["state"] == "holds" and got["holds"] == {"level": 3}
        assert got["intent"] == {"profile": "default", "level": 3}

    def test_on_the_device_not_in_intent(self):
        assert self._j(golden={RO: 3})["state"] == "device_only"

    def test_intent_says_it_and_the_golden_does_not(self):
        got = self._j(intent=self._intent(3), golden={"admin": 15})
        assert got["state"] == "pending" and "deploy it" in got["why"]

    def test_neither(self):
        got = self._j(golden={})
        assert got["state"] == "not_yet" and got["platform"] == "IOS-XE"
        assert self._j(golden=None)["why"] == "no golden is recorded yet"

    def test_the_probe_rides_on_the_row(self):
        probe = {"network": "Lab", "at": "2026-11-13T19:40:00Z", "actor": "op@example.com",
                 "result": "PASS", "why": "", "file": "r2-20261113T194000Z.json"}
        assert self._j(golden={}, probe=probe)["probe"]["result"] == "PASS"


class TestTheProbeRecords:
    """The records are kept by network and IDENTITY (`read_account_probe.record_dir`); the flat
    ones the command line kept by name before are read for their own network only."""

    def _write(self, folder, name, **rec):
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(rec))

    def test_the_newest_by_identity_and_a_flat_one_of_the_network(self, tmp_path, monkeypatch):
        from modules.nsot import read_account_op as RAO
        from modules import read_account_probe as P

        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        ident = "uid:1111-aaaa"
        mine = P.record_dir("Lab", ident)
        assert ":" not in os.path.basename(mine) and "Lab" in mine
        for stamp, result in (("20261113T172802Z", "FAIL"), ("20261113T194000Z", "INCOMPLETE")):
            self._write(mine, f"r2-{stamp}.json", network="Lab", device="r2", at=stamp,
                        actor="op@example.com", verdict={"result": result, "why": "w"})
        root = P.records_root()
        self._write(root, "r2-20261114T000000Z.json", network="Other", device="r2",
                    at="20261114T000000Z", verdict={"result": "PASS"})
        got = RAO.newest("Lab", "r2", identity=ident)
        assert got["result"] == "INCOMPLETE" and got["actor"] == "op@example.com"
        assert RAO.newest("Lab", "r2", identity="uid:someone-else") == {}, \
            "another identity of the same name inherits nothing"
        assert RAO.newest("Other", "r2", identity="")["result"] == "PASS"

    def test_an_unreadable_record_is_named_never_skipped(self, tmp_path, monkeypatch):
        from modules.nsot import read_account_op as RAO
        from modules import read_account_probe as P

        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        folder = P.record_dir("Lab", "uid:1")
        os.makedirs(folder)
        (tmp_path / "probes" / "read-account" / "Lab" / "uid-1" / "r2-x.json").write_text("{no")
        got = RAO.newest("Lab", "r2", identity="uid:1")
        assert got["result"] == "UNREADABLE" and "could not be read" in got["why"]
        assert RAO.newest("Lab", "r2", identity="uid:absent") == {}


class TestTheView:
    def _rows(self, n, state="not_yet", network="Lab", platform="IOS-XE"):
        return [{"network": network, "device": f"d{i}", "platform": platform, "state": state,
                 "probe": None} for i in range(n)]

    def test_at_900_devices_every_group_is_closed_and_an_open_one_is_cut(self):
        value = {"devices": self._rows(610, "holds") + self._rows(290, "not_yet"), "level": 3}
        v = RA.view(value)
        assert v["total"] == 900 and not v["subset"]
        assert [g["state"] for g in v["groups"]] == ["not_yet", "holds"], "act-on states lead"
        assert not any(g["open"] for g in v["groups"])
        held = v["groups"][1]
        assert held["count"] == 610 and len(held["rows"]) == RA.GROUP_ROWS
        assert held["left"] == 610 - RA.GROUP_ROWS
        assert v["summary"][1]["words"] == "hold it at level 3"
        assert RA.view(value, open_group="holds")["groups"][1]["open"]

    def test_a_filter_is_a_subset_and_says_how_many_match(self):
        value = {"devices": self._rows(3) + [dict(self._rows(1, "pending")[0], device="edge")]}
        v = RA.view(value, q="edg")
        assert v["subset"] and v["matching"] == 1 and v["total"] == 4
        assert [g["state"] for g in v["groups"]] == ["pending"]
        assert RA.view(value, state="pending")["matching"] == 1


# ── the lab ───────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def lab(monkeypatch, tmp_path):
    from modules.nsot import approval
    from tests.test_capture import build_capture_lab

    monkeypatch.setattr(approval, "is_approved", lambda repo, t: True)
    got = build_capture_lab(monkeypatch, tmp_path)
    # The seed records r2's partial syslog block as the device holds it (heartbeat 0), which
    # the intent editor refuses on any edit; a person types the heartbeat in, as
    # tests/test_intent_editor_v2.py does, and commits it.
    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars
    doc = hostvars.read_committed(got["repo"], "r2")
    block = doc["logging"]["syslog"]
    assert block.get("heartbeat") == 0, block
    block["heartbeat"] = 300
    hostvars.write_committed(got["repo"], doc)
    assert save_host_vars("Lab", ["r2"], actor="t", source="intent-edit")["ok"]
    monkeypatch.setattr(C, "_FILE", str(tmp_path / "credential_profiles.json"))
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path / "data"))
    os.makedirs(tmp_path / "data", exist_ok=True)
    C.save_profile("default", username="netops", password="Deploy-Not-Real-5531")
    C.set_read_account("default", RO, RO_PW, actor="op@example.com", verified="access")
    monkeypatch.setattr("modules.nsot.listref._registry", lambda: {"Lab": "lab"})
    monkeypatch.setattr("modules.credential_profiles_page._read_rows",
                        lambda name: [dict(ROW)] if name == "Lab" else [])
    held = {}

    def _held():
        if "value" not in held:
            held["value"] = RA.read_coverage()
        return {"value": held["value"], "at": "2026-11-13T20:00:00Z", "why": ""}
    monkeypatch.setattr(RA, "held", _held)
    got["held"] = held
    return got


def _reread(lab):
    lab["held"].pop("value", None)


class TestCoverageOnTheLab:
    def test_r2_takes_it_not_yet_and_no_password_is_in_the_value(self, lab):
        value = RA.read_coverage()
        (row,) = value["devices"]
        assert row["device"] == "r2" and row["state"] == "not_yet"
        assert row["account"] == RO and row["profile"] == "default"
        assert value["networks"] == {"lab": {"name": "Lab", "error": ""}}, "keyed by its id"
        assert RO_PW not in json.dumps(value)

    def test_a_golden_holding_it_at_level_one_cannot_take_it(self, lab):
        from modules.nsot.repo import GoldenItem, save_golden

        text = lab["captured"] + f"username {RO} secret 9 $9$NotRealSalt$abcdefghijklmnop\n"
        assert save_golden("Lab", [GoldenItem("r2", text, "203.0.113.12", platform="cisco_iosxe")],
                           source="capture", actor="t", baseline=False)
        (row,) = RA.read_coverage()["devices"]
        assert row["state"] == "would_change" and row["holds"] == {"level": 1}

    def test_a_golden_is_read_again_only_when_its_blob_moved(self, lab, monkeypatch):
        first = RA.read_coverage()
        calls = []
        import modules.nsot.repo as R
        real = R.committed_golden_for
        monkeypatch.setattr(R, "committed_golden_for",
                            lambda repo, entry: calls.append(entry) or real(repo, entry))
        RA.read_coverage(first)
        assert calls == [], "an unchanged golden is not read again"
        RA.read_coverage({})
        assert len(calls) == 1

    def test_the_reader_hands_the_last_good_value_on_so_no_golden_is_read_twice(
            self, lab, monkeypatch):
        """The reader job's own read (`readers.read_account_coverage.read`): given no previous
        value it takes the last good one the reader job holds, and hands either to
        `read_coverage`, so a cycle with nothing committed reads no golden."""
        from modules import reader_job
        from modules.readers import read_account_coverage as RAC
        import modules.nsot.repo as R

        first = RAC.read({})
        assert [r["device"] for r in first["devices"]] == ["r2"]
        monkeypatch.setattr(reader_job, "read_cached",
                            lambda name: {"doc": {"last_good": {"value": first}}}
                            if name == RAC.NAME else {})
        calls = []
        real = R.committed_golden_for
        monkeypatch.setattr(R, "committed_golden_for",
                            lambda repo, entry: calls.append(entry) or real(repo, entry))
        again = RAC.read()
        assert calls == [], "the last good value's summaries were handed on"
        assert again["devices"] == first["devices"]
        assert RAC.READER.name == RAC.NAME and RAC.READER.invalidates == ("read_account",)


class TestAdd:
    def test_the_preview_writes_nothing_and_says_the_lines(self, lab):
        head = _git(lab["repo"], "rev-parse", "HEAD")
        status = _git(lab["repo"], "status", "--porcelain", "--untracked-files=all")
        p = RA.add_preview([("Lab", "r2")])
        assert p["ok"] and [t["device"] for t in p["taking"]] == ["r2"], p
        assert _git(lab["repo"], "rev-parse", "HEAD") == head
        assert _git(lab["repo"], "status", "--porcelain", "--untracked-files=all") == status
        assert "host_vars" not in status
        (g,) = p["groups"]
        lines = [l["line"] for l in g["lines"]]
        assert lines == ["privilege exec all level 3 show telemetry ietf subscription",
                         "privilege exec level 3 show telemetry ietf",
                         "privilege exec level 3 show telemetry",
                         "privilege exec level 1 show",
                         f"username {RO} privilege 3 algorithm-type scrypt secret "
                         "<redacted:read-account:profile:default>"]
        effect = {l["line"]: l["effect"] for l in g["lines"]}
        assert "puts `show` back at level 1" in effect["privilege exec level 1 show"]
        assert "leading word" in effect["privilege exec level 3 show telemetry"]
        assert any("users gains" in w for w in g["change"])
        assert RO_PW not in json.dumps(p)
        assert RA.add_preview([("Lab", "r2")])["hash"] == p["hash"]

    def test_the_lines_shown_are_the_lines_the_template_writes(self, lab):
        """The level's lines a person reads are `privilege_exec.rendered`'s for the same
        entries, leading words included (C3580), each entry's effect on its own line."""
        from modules.nsot import privilege_exec as PE

        (g,) = RA.add_preview([("Lab", "r2")])["groups"]
        wanted = PE.read_account_lines("cisco_iosxe", 3, ping_traceroute=False)
        shown = [l["line"] for l in g["lines"]][:-1]
        assert shown == PE.rendered([w["entry"] for w in wanted])
        effect = {l["line"]: l["effect"] for l in g["lines"]}
        for w in wanted:
            assert effect[PE.render_line(w["entry"])] == w["effect"]

    def test_a_device_is_refused_by_name(self, lab):
        p = RA.add_preview([("Lab", "r2"), ("Lab", "gone"), ("Nowhere", "x")])
        why = {r["device"]: r["why"] for r in p["refused"]}
        assert "not in Lab's devices" in why["gone"] and "no network is named" in why["x"]

    def test_the_commit_is_one_commit_as_the_person_with_the_reason(self, lab):
        p = RA.add_preview([("Lab", "r2")])
        head = _git(lab["repo"], "rev-parse", "HEAD")
        got = RA.add_commit([("Lab", "r2")], p["hash"], "every AI read signs in as it",
                            "op@example.com")
        assert got["ok"] and got["commits"][0]["commit"], got
        log = _git(lab["repo"], "log", "-1", "--format=%B")
        assert _git(lab["repo"], "rev-list", "--count", f"{head}..HEAD") == "1"
        assert "Source: read-account-add" in log and "Actor: op@example.com" in log
        assert "Reason: every AI read signs in as it" in log and f"Preview: {p['hash']}" in log
        from modules.nsot import hostvars
        doc = hostvars.read_committed(lab["repo"], "r2")
        assert {"privilege": 3, "secret_ref": "read-account:profile:default"} in doc["users"]
        assert {"level": 1, "command": "show", "all": False} in doc["privilege_exec"]
        _reread(lab)
        (row,) = RA.held()["value"]["devices"]
        assert row["state"] == "pending" and RA.pending_of("Lab") == ["r2"]

    def test_a_moved_preview_writes_nothing_and_names_both_hashes(self, lab):
        head = _git(lab["repo"], "rev-parse", "HEAD")
        got = RA.add_commit([("Lab", "r2")], "0" * 64, "why", "op@example.com")
        assert not got["ok"] and "000000000000 ->" in got["error"]
        assert got["preview"]["hash"][:12] in got["error"]
        assert _git(lab["repo"], "rev-parse", "HEAD") == head

    def test_a_reason_is_needed(self, lab):
        p = RA.add_preview([("Lab", "r2")])
        got = RA.add_commit([("Lab", "r2")], p["hash"], "  ", "op@example.com")
        assert not got["ok"] and "a reason is needed" in got["error"]


# ── the rollout ───────────────────────────────────────────────────────────────────────────────

class TestTheOrder:
    def test_the_canary_then_waves_then_each_carrier_alone(self):
        batches, confirm_at = RA.order(["a", "b", "c", "d", "e"], "c", 2, {"b": ["x"], "e": ["y"]})
        assert batches == [["c"], ["a", "d"], ["b"], ["e"]] and confirm_at == [2, 3]

    def test_a_carrier_chosen_as_canary_is_still_last(self):
        batches, confirm_at = RA.order(["a", "b"], "b", 4, {"b": ["x"]})
        assert batches == [["a"], ["b"]] and confirm_at == [1]


@pytest.fixture
def planned(monkeypatch):
    """`plan_devices` gives each device a program (a moved one when asked), the Topology read
    says Mercury reaches x through c, and `apply_batch` records what it was sent and runs its
    check after verify on each device that deployed, as THE apply's `_settle_after_verify`
    does (a ``rollback`` reason fails the device, rolled back). Each device's probe is planned
    (none for a device in ``no_probe``; a moved hash, once its own apply has begun, for one in
    ``probe_moves``) and run with the verdict ``verdict`` names (PASS by default)."""
    import routes.deploy as rd
    from modules import read_account_probe as P
    from modules.nsot.deploy import DEPLOYED

    state = {"moved": set(), "calls": [], "fail": set(), "no_probe": set(),
             "probe_moves": set(), "verdict": {}, "probed": [], "rolled_back": []}

    def probe_plan(network, d):
        if d in state["no_probe"]:
            return {"refused": f"REFUSED: no read-only account for {d}: none resolves"}
        moved = d in state["probe_moves"] and any(d in c for c in state["calls"])
        return {"network": network, "device": d, "hash": "p-moved" if moved else f"p-{d}",
                "account": {"username": RO, "source": "profile"},
                "reads": [{"op": "version", "command": "show version"},
                          {"op": "mac", "result": "NOT MEASURED", "why": "no MAC"}],
                "refused_steps": [{"key": "enable", "command": "enable"}]}

    def probe_run(p, dev, actor, values, cap, held=False):
        assert held, "the rollout's probe runs inside THE apply's hold"
        state["probed"].append(p["device"])
        result = state["verdict"].get(p["device"], "PASS")
        return {"device": p["device"], "verdict": {"result": result, "why": f"{result} said"}}

    def plan_devices(list_name, hosts, **kw):
        return [{"device": d, "deployable": True, "blocking_reasons": [], "capture_hash": f"c-{d}",
                 "to_add": ([] if d == "same" else [f"username {RO} privilege 3 x", "ntp server y"]
                            if d == "b" else [f"username {RO} privilege 3 x"]),
                 "command_hash": "moved" if d in state["moved"] else f"h-{d}"} for d in hosts]

    def apply_batch(list_name, confirmations, command_hashes, **kw):
        state["calls"].append(list(confirmations))
        check, results = kw.get("after_verify"), []
        for d in confirmations:
            r = {"device": d, "outcome": "failed" if d in state["fail"] else DEPLOYED,
                 "verify": {"ok": d not in state["fail"]}}
            if check is not None and r["outcome"] == DEPLOYED:
                why = (check(d, r, None) or {}).get("rollback")
                if why:
                    r.update(outcome="failed", reason=why, stage="after_verify")
                    state["rolled_back"].append(d)
            results.append(r)
        return {"results": results}
    # `raising=False`: the fixture plants the probe's plan whether or not the module under test
    # has one yet, so a test of the probe in verify fails in its own body where it is missing.
    monkeypatch.setattr(RA, "_probe_plan", probe_plan, raising=False)
    monkeypatch.setattr(P, "run", probe_run)
    monkeypatch.setattr(P, "_inventory", lambda network: {d: {} for d in ("a", "b", "c")})
    monkeypatch.setattr(P, "write_record", lambda rec: f"/records/{rec['device']}-1.json")
    monkeypatch.setattr("modules.nsot.reads.cap_bytes", lambda network: 4096)
    monkeypatch.setattr("modules.redact.known_secret_values", lambda: {})
    monkeypatch.setattr(rd, "plan_devices", plan_devices)
    monkeypatch.setattr(rd, "apply_batch", apply_batch)
    monkeypatch.setattr(RA, "management_carriers",
                        lambda network, hosts: {"carries": {"c": ["x"]} if "c" in hosts else {},
                                                "why": ""})
    monkeypatch.setattr(RA, "held", lambda: {"value": {"devices": [
        {"network": "Lab", "device": d, "account": RO, "state": "pending"}
        for d in ("a", "b", "c")]}, "at": "", "why": ""})
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    return state


class TestTheRollout:
    def test_the_one_preview(self, lab, planned):
        p = RA.rollout_plan("Lab", ["a", "b", "c", "same"], "b", 4)
        assert p["ok"], p
        assert p["batches"] == [["b"], ["a"], ["c"]] and p["confirm_at"] == [2]
        assert p["unchanged"] == ["same"] and p["carries"] == {"c": ["x"]}
        assert {d["device"]: d["besides"] for d in p["devices"]} == {"a": 0, "b": 1, "c": 0}
        assert RA.rollout_plan("Lab", ["a", "b", "c", "same"], "b", 4)["hash"] == p["hash"]
        assert RA.rollout_plan("Lab", ["a", "b", "c", "same"], "a", 4)["hash"] != p["hash"]

    def test_the_run_goes_wave_to_wave_by_itself_the_carrier_last(self, lab, planned):
        """The operator, 2026-11-14 (board R's 00): one confirm, then the canary and every
        wave by themselves, the carrier last, with no press between them."""
        from modules.nsot import capture_job

        p = RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4)
        job = RA.rollout_start("Lab", ["a", "b", "c"], "b", 4, p["hash"], actor="op",
                               actor_kind="person")
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        assert run["state"] == "done" and planned["calls"] == [["b"], ["a"], ["c"]]
        assert [r["device"] for r in run["results"]] == ["b", "a", "c"]

    def test_the_pause_after_the_canary_holds_until_continued(self, lab, planned):
        from modules.nsot import capture_job

        options = {"pause_after_canary": "1"}
        p = RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4, options=options)
        job = RA.rollout_start("Lab", ["a", "b", "c"], "b", 4, p["hash"], actor="op",
                               actor_kind="person", options=options)
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        assert run["state"] == "paused" and run["waits"] == "canary" and planned["calls"] == [["b"]]
        assert RA.go_on_refusal(run) == ""
        job = RA.rollout_go_on(run, actor="op", actor_kind="person")
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        assert run["state"] == "done" and planned["calls"] == [["b"], ["a"], ["c"]]

    def test_a_changed_option_is_a_changed_hash_and_refuses_the_confirm(self, lab, planned):
        from modules.nsot import capture_job

        p = RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4)
        q = RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4, options={"settle_s": "30"})
        assert p["hash"] != q["hash"]
        job = RA.rollout_start("Lab", ["a", "b", "c"], "b", 4, p["hash"], actor="op",
                               actor_kind="person", options={"settle_s": "30"})
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        assert run["state"] == "refused" and p["hash"][:12] in run["error"]
        assert q["hash"][:12] in run["error"] and planned["calls"] == []

    def test_the_first_failure_stops_it_names_the_rest_and_tells_the_team(self, lab, planned,
                                                                         monkeypatch):
        from modules.nsot import capture_job

        told = []
        monkeypatch.setattr("modules.notify.delivery.deliver_event",
                            lambda event, teams: told.append(event) or {"sent": 1})
        planned["fail"] = {"a"}
        p = RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4)
        job = RA.rollout_start("Lab", ["a", "b", "c"], "b", 4, p["hash"], actor="op",
                               actor_kind="person")
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        assert run["state"] == "stopped" and "a did not deploy and verify" in run["stopped"]
        assert run["not_started"] == ["c"] and planned["calls"] == [["b"], ["a"]]
        assert len(told) == 1 and told[0]["event"] == "rollout_stopped"
        assert "c" in told[0]["outcome"]
        assert RA.go_on_refusal(run).startswith("that rollout is not paused")

    def test_each_device_is_probed_as_the_account_as_part_of_its_verify(self, lab, planned):
        """The coordinator, 2026-11-14 (item 1): deploy, read back, probe as the account; the
        probe planned at the preview, its hash in the plan's, its verdict on the result."""
        from modules.nsot import capture_job

        p = RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4)
        assert {d["device"]: d["probe"]["hash"] for d in p["devices"]} == {
            "a": "p-a", "b": "p-b", "c": "p-c"}
        assert p["devices"][0]["probe"]["not_measured"] == ["mac"]
        job = RA.rollout_start("Lab", ["a", "b", "c"], "b", 4, p["hash"], actor="op",
                               actor_kind="person")
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        assert run["state"] == "done" and planned["probed"] == ["b", "a", "c"]
        assert {r["device"]: r["probe"]["result"] for r in run["results"]} == {
            "a": "PASS", "b": "PASS", "c": "PASS"}
        assert run["results"][0]["probe"]["record"] == "b-1.json"

    def test_a_probe_moved_since_the_preview_is_a_moved_hash(self, lab, planned):
        p = RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4)
        planned["calls"].append(["a"])           # what a probe's plan reads moved
        planned["probe_moves"] = {"a"}
        assert RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4)["hash"] != p["hash"]

    @pytest.mark.parametrize("verdict", ["FAIL", "UNREADABLE"])
    def test_a_failed_probe_rolls_the_device_back_stops_and_tells_the_team(
            self, lab, planned, monkeypatch, verdict):
        from modules.nsot import capture_job

        told = []
        monkeypatch.setattr("modules.notify.delivery.deliver_event",
                            lambda event, teams: told.append(event) or {"sent": 1})
        planned["verdict"] = {"a": verdict}
        p = RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4)
        job = RA.rollout_start("Lab", ["a", "b", "c"], "b", 4, p["hash"], actor="op",
                               actor_kind="person")
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        assert run["state"] == "stopped" and planned["rolled_back"] == ["a"]
        assert planned["calls"] == [["b"], ["a"]] and run["not_started"] == ["c"]
        a = next(r for r in run["results"] if r["device"] == "a")
        assert f"gave {verdict}" in a["reason"] and a["probe"]["result"] == verdict
        assert len(told) == 1 and told[0]["event"] == "rollout_stopped"

    def test_an_incomplete_probe_passes_and_says_so(self, lab, planned):
        from modules.nsot import capture_job

        planned["verdict"] = {"a": "INCOMPLETE"}
        p = RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4)
        job = RA.rollout_start("Lab", ["a", "b", "c"], "b", 4, p["hash"], actor="op",
                               actor_kind="person")
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        assert run["state"] == "done" and planned["rolled_back"] == []
        assert next(r for r in run["results"] if r["device"] == "a")["probe"]["result"] == \
            "INCOMPLETE"

    def test_a_probe_that_moved_at_apply_rolls_back_naming_both_hashes(self, lab, planned):
        from modules.nsot import capture_job

        planned["probe_moves"] = {"a"}
        p = RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4)
        job = RA.rollout_start("Lab", ["a", "b", "c"], "b", 4, p["hash"], actor="op",
                               actor_kind="person")
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        a = next(r for r in run["results"] if r["device"] == "a")
        assert run["state"] == "stopped" and planned["rolled_back"] == ["a"]
        assert "p-a" in a["reason"] and "p-moved" in a["reason"] and "a" not in planned["probed"]

    def test_a_device_whose_probe_cannot_be_planned_is_refused_at_the_preview(self, lab,
                                                                              planned):
        planned["no_probe"] = {"a"}
        p = RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4)
        assert p["ok"] and [d["device"] for d in p["devices"]] == ["b", "c"]
        (r,) = p["refused"]
        assert r["device"] == "a" and "cannot be probed after verify" in r["reasons"][0]

    def test_an_unreadable_management_path_is_not_offered_and_refused_at_confirm(
            self, lab, planned, monkeypatch):
        """An unreadable read neither passes nor fails: no device is guessed to carry the
        path, the plan is blocked, and the confirm refuses naming the comparison and both
        operands, with nothing sent."""
        from modules.nsot import capture_job

        monkeypatch.setattr(RA, "management_carriers", lambda network, hosts: {
            "carries": {}, "why": "the Topology read could not be used (no LLDP read yet)"})
        p = RA.rollout_plan("Lab", ["a", "b", "c"], "", 4)
        assert p["ok"] and p["blocked"], p
        assert "no LLDP read yet" in p["blocked"] and "you named none" in p["blocked"]
        assert "must be usable (it is not)" in p["blocked"]
        job = RA.rollout_start("Lab", ["a", "b", "c"], "", 4, p["hash"], actor="op",
                               actor_kind="person")
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        assert run["state"] == "refused" and run["error"] == p["blocked"]
        assert planned["calls"] == [], "nothing is sent"

    def test_devices_the_person_names_go_last_alone(self, lab, planned, monkeypatch):
        from modules.nsot import capture_job

        monkeypatch.setattr(RA, "management_carriers", lambda network, hosts: {
            "carries": {}, "why": "the Topology read could not be used"})
        p = RA.rollout_plan("Lab", ["a", "b", "c"], "", 4, named=["a"])
        assert not p["blocked"] and p["named"] == ["a"]
        assert p["batches"] == [["b"], ["c"], ["a"]] and p["confirm_at"] == [2]
        assert p["hash"] != RA.rollout_plan("Lab", ["a", "b", "c"], "", 4)["hash"]
        job = RA.rollout_start("Lab", ["a", "b", "c"], "", 4, p["hash"], actor="op",
                               actor_kind="person", named=["a"])
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        assert run["state"] == "done" and planned["calls"] == [["b"], ["c"], ["a"]]

    def test_a_blocked_preview_offers_no_deploy(self, lab, planned, monkeypatch):
        from modules.nsot import capture_job

        monkeypatch.setattr(RA, "management_carriers", lambda network, hosts: {
            "carries": {}, "why": "the Topology read could not be used"})
        c = lab["client"]
        r = c.post("/v2/credentials/profiles/read-account/rollout/plan",
                   data={"network": "Lab", "device": ["a", "b"], "size": "4"})
        job = r.get_data(as_text=True).split("/rollout/plan/", 1)[1].split("?", 1)[0]
        assert capture_job.wait(job, 10)
        card = c.get(f"/v2/credentials/profiles/read-account/rollout/plan/{job}?network=Lab"
                     "&device=a&device=b&size=4").get_data(as_text=True)
        assert "data-ra-blocked" in card and "Deploy the canary" not in card
        assert capture_job.get(job)["payload"]["blocked"] in card.replace("&#39;", "'")
        r = c.post("/v2/credentials/profiles/read-account/rollout",
                   data={"network": "Lab", "device": ["a", "b"], "size": "4",
                         "hash": capture_job.get(job)["payload"]["hash"]})
        run = r.get_data(as_text=True).split("/rollout/run/", 1)[1].split("?", 1)[0]
        assert capture_job.wait(run, 10)
        assert capture_job.get(run)["payload"]["state"] == "refused" and planned["calls"] == []

    def test_a_moved_plan_sends_nothing_and_names_both_hashes(self, lab, planned):
        from modules.nsot import capture_job

        p = RA.rollout_plan("Lab", ["a", "b"], "", 4)
        planned["moved"] = {"a"}
        job = RA.rollout_start("Lab", ["a", "b"], "", 4, p["hash"], actor="op",
                               actor_kind="person")
        assert capture_job.wait(job, 10)
        run = capture_job.get(job)["payload"]
        assert run["state"] == "refused" and p["hash"][:12] in run["error"]
        assert planned["calls"] == []


# ── C3427, its first part: Replace its password… refused while a device holds it ──────────────

class TestReplaceWhileADeviceHoldsIt:
    """A device holding the account keeps the password it was given; no operation carries a new
    one yet, so Replace its password… is refused while the coverage says one holds it, naming
    it, and while the coverage cannot be read; allowed when none does. The store is unchanged by
    a refusal, and no response carries a password."""

    def _post(self, lab, password="ReadOnly-New-Not-Real-9911"):
        return lab["client"].post("/v2/credentials/profiles/read-account",
                                  data={"name": "default", "username": RO, "password": password})

    def _holding(self, lab, monkeypatch, holds):
        row = {"network": "Lab", "device": "r2", "profile": "default", "account": RO,
               "holds": {"level": 3} if holds else None, "state": "holds" if holds else "not_yet"}
        monkeypatch.setattr(RA, "held", lambda: {"value": {"devices": [row]},
                                                 "at": "2026-11-13T20:00:00Z", "why": ""})

    def test_refused_naming_the_device_and_the_store_unchanged(self, lab, monkeypatch):
        self._holding(lab, monkeypatch, True)
        before = C.resolve_read()["password"]
        r = self._post(lab)
        html = r.get_data(as_text=True)
        assert r.status_code == 400 and "r2 (Lab)" in html and "2026-11-13T20:00:00Z" in html
        assert "a replaced password reaches none of them" in html.replace("&#39;", "'")
        assert C.resolve_read()["password"] == before == RO_PW
        assert "ReadOnly-New-Not-Real-9911" not in html and RO_PW not in html

    def test_refused_while_the_coverage_cannot_be_read(self, lab, monkeypatch):
        monkeypatch.setattr(RA, "held", lambda: {"value": None, "at": "", "why": "absent"})
        r = self._post(lab)
        assert r.status_code == 400 and "cannot be told" in r.get_data(as_text=True)
        assert C.resolve_read()["password"] == RO_PW

    def test_allowed_when_no_device_holds_it(self, lab, monkeypatch):
        self._holding(lab, monkeypatch, False)
        r = self._post(lab)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert C.resolve_read()["password"] == "ReadOnly-New-Not-Real-9911"


# ── the routes ────────────────────────────────────────────────────────────────────────────────

class TestTheRoutes:
    def test_the_page_draws_what_the_reader_holds_and_redraws_after_an_add(self, lab):
        c = lab["client"]
        html = c.get("/v2/credentials/profiles?list=Lab").get_data(as_text=True)
        (row,) = RA.held()["value"]["devices"]
        assert f'data-ra-device="r2" data-state="{row["state"]}"' in html
        assert "1 not yet" in html and "Add the read-only account…" in html
        assert RO_PW not in html
        form = c.post("/v2/credentials/profiles/read-account/add/preview",
                      data={"device": ["Lab/r2"], "reason": "why"}).get_data(as_text=True)
        h = form.split('name="hash" value="', 1)[1].split('"', 1)[0]
        r = c.post("/v2/credentials/profiles/read-account/add",
                   data={"device": ["Lab/r2"], "reason": "every AI read", "hash": h})
        added = r.get_data(as_text=True)
        assert r.status_code == 200 and "data-ra-committed" in added
        # The rollout is offered at once for the device just committed, before the coverage
        # has read again.
        assert 'name="device" value="r2" checked' in added
        _reread(lab)
        again = c.get("/v2/credentials/profiles/read-account/fleet").get_data(as_text=True)
        assert 'data-ra-device="r2" data-state="pending"' in again
        assert RA.held()["value"]["devices"][0]["state"] == "pending"

    def test_nothing_held_says_so_and_why(self, lab, monkeypatch):
        why = "no reader has written it"
        monkeypatch.setattr(RA, "held", lambda: {"value": None, "at": "", "why": why})
        html = lab["client"].get("/v2/credentials/profiles/read-account/fleet").get_data(
            as_text=True)
        assert "Not read yet:" in html and RA.held()["why"] in html
        assert RA.held()["value"] is None, "nothing is computed on the request in its place"

    def test_the_add_preview_and_a_moved_confirm(self, lab):
        c = lab["client"]
        form = c.get("/v2/credentials/profiles/read-account/add?tick=not-yet").get_data(
            as_text=True)
        assert 'value="Lab/r2" aria-label="Tick r2" checked' in form
        r = c.post("/v2/credentials/profiles/read-account/add/preview",
                   data={"device": ["Lab/r2"], "reason": "why"})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "privilege exec level 1 show" in html, html[:400]
        assert "Add to 1 device&#39; intent" in html or "Add to 1 device' intent" in html
        head = _git(lab["repo"], "rev-parse", "HEAD")
        r = c.post("/v2/credentials/profiles/read-account/add",
                   data={"device": ["Lab/r2"], "reason": "why", "hash": "f" * 64})
        assert r.status_code == 409 and "Nothing was written" in r.get_data(as_text=True)
        assert _git(lab["repo"], "rev-parse", "HEAD") == head

    def test_the_rollout_form_offers_the_pending_and_its_preview_is_the_plan(self, lab,
                                                                             planned):
        from modules.nsot import capture_job

        c = lab["client"]
        html = c.get("/v2/credentials/profiles/read-account/rollout?network=Lab") \
            .get_data(as_text=True)
        assert 'name="device" value="a" checked' in html and "Preview the rollout" in html
        r = c.post("/v2/credentials/profiles/read-account/rollout/plan",
                   data={"network": "Lab", "device": ["a", "b", "c"], "canary": "b",
                         "size": "4"})
        page = r.get_data(as_text=True)
        job = page.split("/rollout/plan/", 1)[1].split("?", 1)[0]
        assert capture_job.wait(job, 10)
        assert capture_job.get(job)["payload"]["hash"] == \
            RA.rollout_plan("Lab", ["a", "b", "c"], "b", 4)["hash"]
        card = c.get(f"/v2/credentials/profiles/read-account/rollout/plan/{job}?network=Lab"
                     "&device=a&device=b&device=c&canary=b&size=4").get_data(as_text=True)
        assert "Deploy the canary" in card and "Last, alone" in card and planned["calls"] == []
