"""Phase 2 in full: verify → capture → rotate → remove RW → golden → NetBox
→ promote.

**`ok` means all of it.** The previous shape had promotion SECOND of three,
so the one step that changes what the operator sees ran before the four that
do the work — and a device sat promoted with a throwaway password, no
golden, no NetBox record and the read-write community still on it, reporting
`ok: true`.

Two independent arguments put promotion last, which is why it is not a
preference: 4C.3's rule (the visible, durable change goes last among the
fallible), and rotation forcing it anyway (the CSV row must carry the
ROTATED credential).
"""

import os

import pytest


@pytest.fixture
def world(tmp_path, monkeypatch):
    from modules.nsot import manifest as _m, repo as _repo
    from modules.nsot.repo import GoldenItem, adopt_identity

    list_dir = tmp_path / "probe"
    repo_dir = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo_dir, "host_vars"), exist_ok=True)
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda n: str(list_dir))
    # DELEGATES for everything it does not name. A stub answering `None` to
    # every other key is the stub-drift problem again: this one returned
    # nothing for `platform_map`, so `netmiko_type_for_dialect` found no
    # driver and the whole phase refused before its first step — a failure
    # about the fixture wearing the shape of a failure about the code.
    import modules.settings_schema as _ss
    _real_get = _ss.get_setting
    _overrides = {"nsot_git_author_name": "NMAS",
                  "nsot_git_author_email": "n@l"}
    monkeypatch.setattr(
        "modules.settings_schema.get_setting",
        lambda k, d=None: _overrides[k] if k in _overrides else _real_get(k, d))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda c: None)
    monkeypatch.setattr("modules.secrets_store.KEY_FILE", str(tmp_path / "key.key"))
    monkeypatch.setattr("modules.credentials._FILE", str(tmp_path / "creds.json"))
    _repo.init_repo(repo_dir)

    identity = adopt_identity(repo_dir, GoldenItem("bp1", "", "203.0.113.31"))
    _m.upsert_device(repo_dir, identity, "bp1", mgmt_ip="203.0.113.31",
                     platform="cisco_iosxe", pending=True)

    import modules.credentials as creds
    creds.set_device_override("203.0.113.31", "admin", "BOOT5trap", "BOOT5trap")
    return {"repo": repo_dir, "identity": identity, "tmp": tmp_path}


#: A capture carrying both the things the first golden must not contain.
DIRTY = ("hostname bp1\n!\nusername admin privilege 15 password 0 BOOT5trap\n"
         "!\nsnmp-server community public RO\n"
         "snmp-server community s3cretRW RW 99\n"
         "!\ninterface GigabitEthernet2\n ip address 203.0.113.31 "
         "255.255.255.0\n!\nline vty 0 4\n transport input ssh\n!\nend\n")

CLEAN = ("hostname bp1\n!\nusername admin privilege 15 secret 9 $9$rotated\n"
         "!\nsnmp-server community public RO\n"
         "!\ninterface GigabitEthernet2\n ip address 203.0.113.31 "
         "255.255.255.0\n!\nline vty 0 4\n transport input ssh\n!\nend\n")


def _steps(**over):
    """Every collaborator faked. The ordering is what is under test."""
    captures = iter([{"ok": True, "config": DIRTY, "error": ""},
                     {"ok": True, "config": CLEAN, "error": ""}])

    def _rotate(repo, hostname, list_name, **kw):
        import modules.credentials as creds
        creds.set_device_override("203.0.113.31", "admin",
                                  "R0tatedValue99", "R0tatedValue99")
        return {"rotated": True, "state": "rotated", "reason": ""}

    steps = {
        "online": lambda ip: True,
        "reach": lambda *a, **k: "bp1#",
        "capture": lambda *a, **k: next(captures),
        "rotate": _rotate,
        "remove_rw": lambda *a, **k: {"ok": True,
                                      "removed": ["no snmp-server community "
                                                  "s3cretRW RW 99"],
                                      "kept": ["snmp-server community public RO"]},
        "netbox": lambda *a, **k: {"ok": True, "created": ["dcim/devices:7"],
                                   "device_id": 7},
    }
    steps.update(over)
    return steps


class TestEveryStepIsReportedAndOkMeansAllOfIt:

    def test_a_clean_run_reports_every_step(self, world):
        from modules.nsot.onboard import PHASE_TWO_STEPS, run_phase_two

        out = run_phase_two(world["repo"], "bp1", "probe", actor="t",
                            **_steps())
        assert out["ok"] is True, out
        assert [s["step"] for s in out["steps"]] == list(PHASE_TWO_STEPS)
        assert all(s["ok"] for s in out["steps"]), out["steps"]

    def test_a_partial_run_names_every_step_that_did_not_run(self, world):
        """"The phase failed" is not actionable; "rotate failed and these
        four therefore did not run" is."""
        from modules.nsot.onboard import run_phase_two

        out = run_phase_two(
            world["repo"], "bp1", "probe",
            **_steps(rotate=lambda *a, **k: {"rotated": False,
                                             "state": "not_started",
                                             "reason": "the device refused"}))
        assert out["ok"] is False
        assert out["reason"] == "the device refused"
        not_run = {r["step"] for r in out["steps"] if r["detail"] == "did not run"}
        assert not_run == {"remove_rw", "golden", "netbox", "promote"}, not_run
        assert {r["step"] for r in out["remaining"]} == not_run

    def test_ok_is_false_if_any_step_is_false(self, world):
        """`ok` is computed from the steps, not set beside them.

        The first version of this asserted only the outcome, and a control
        forcing `ok = True` at the end of a clean run passed — because every
        failure path returned through `_stop`, which set `ok` itself, so the
        computation was never load-bearing. `ok` is now decided in one place
        from the step rows, and the assertion below is on the RELATIONSHIP
        rather than on the value.
        """
        from modules.nsot.onboard import run_phase_two

        out = run_phase_two(world["repo"], "bp1", "probe",
                            **_steps(netbox=lambda *a, **k: {
                                "ok": False, "reason": "writes disabled"}))
        assert out["ok"] is False
        assert out["promoted"] is False

    def test_ok_and_the_steps_can_never_disagree(self, world):
        """The property the control exists for: `ok` true with any step
        false, or `ok` false with every step true, is a result field scoped
        to a part and read as the whole."""
        from modules.nsot.onboard import run_phase_two

        for label, over in (("clean", {}),
                            ("capture", {"capture": lambda *a, **k: {
                                "ok": False, "config": "", "error": "x"}}),
                            ("netbox", {"netbox": lambda *a, **k: {
                                "ok": False, "reason": "x"}})):
            out = run_phase_two(world["repo"], "bp1", "probe", **_steps(**over))
            every = all(r["ok"] for r in out["steps"])
            assert out["ok"] is every, (label, out["ok"], out["steps"])
            if label != "clean":
                # and re-pend it for the next iteration
                from modules.nsot import manifest as _m
                data = _m.load(world["repo"])
                for e in data["devices"].values():
                    e["verified_at"] = None
                _m.save(world["repo"], data)


class TestAPartialRunLeavesTheDevicePending:
    """**The wrong-and-looks-right state for this phase**, and what makes it
    impossible rather than unlikely."""

    @pytest.mark.parametrize("failing", ["capture", "rotate", "remove_rw",
                                         "netbox"])
    def test_the_device_is_still_pending(self, world, failing):
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import run_phase_two

        fail = {"capture": lambda *a, **k: {"ok": False, "config": "",
                                            "error": "x"},
                "rotate": lambda *a, **k: {"rotated": False, "reason": "x"},
                "remove_rw": lambda *a, **k: {"ok": False, "error": "x"},
                "netbox": lambda *a, **k: {"ok": False, "reason": "x"}}[failing]
        run_phase_two(world["repo"], "bp1", "probe", **_steps(**{failing: fail}))

        pending = _m.pending_devices(world["repo"])
        assert [p["name"] for p in pending] == ["bp1"], (
            f"a {failing} failure left the device promoted")

    def test_promotion_is_last_in_the_declared_order(self):
        from modules.nsot.onboard import PHASE_TWO_STEPS

        assert PHASE_TWO_STEPS[-1] == "promote"

    def test_nothing_before_promotion_writes_verified_at(self, world):
        """**The control you cannot get from the order alone.**

        Moving promotion earlier must be noticed. Here it runs first and the
        run then fails — and the device is left promoted, which is exactly
        the state this ordering exists to prevent. If this assertion ever
        stops failing for the wrong implementation, the ordering has stopped
        being load-bearing.
        """
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import promote_device, run_phase_two

        # Promotion, out of order: performed during the capture step.
        def _early(*a, **k):
            promote_device(world["repo"], "bp1", "probe", username="admin",
                           password="whatever")
            return {"ok": False, "config": "", "error": "capture failed"}

        run_phase_two(world["repo"], "bp1", "probe", **_steps(capture=_early))

        assert _m.pending_devices(world["repo"]) == [], (
            "the control did not reproduce the defect, so it proves nothing")
        # And the shipped order does NOT do that:
        from modules.nsot import repo as _repo
        from modules.nsot.repo import GoldenItem, adopt_identity
        ident2 = adopt_identity(world["repo"], GoldenItem("bp2", "", "203.0.113.32"))
        _m.upsert_device(world["repo"], ident2, "bp2", mgmt_ip="203.0.113.32",
                         platform="cisco_iosxe", pending=True)
        import modules.credentials as creds
        creds.set_device_override("203.0.113.32", "admin", "B", "B")
        run_phase_two(world["repo"], "bp2", "probe",
                      **_steps(capture=lambda *a, **k: {"ok": False,
                                                        "config": "",
                                                        "error": "x"}))
        assert [p["name"] for p in _m.pending_devices(world["repo"])] == ["bp2"]


class TestTheFirstGoldenIsATrueRecord:
    """Asserted on the FILE, not on intent."""

    def _run(self, world):
        from modules.nsot.onboard import run_phase_two

        return run_phase_two(world["repo"], "bp1", "probe", actor="t",
                             **_steps())

    def test_it_exists_after_a_clean_run(self, world):
        assert self._run(world)["ok"] is True
        path = os.path.join(world["repo"], "golden", "bp1.cfg")
        assert os.path.exists(path), os.listdir(
            os.path.join(world["repo"], "golden"))

    def test_it_contains_no_rw_community(self, world):
        self._run(world)
        text = open(os.path.join(world["repo"], "golden", "bp1.cfg"),
                    encoding="utf-8").read()
        assert "RW" not in text, text
        assert "s3cretRW" not in text

    def test_it_contains_no_bootstrap_credential(self, world):
        self._run(world)
        text = open(os.path.join(world["repo"], "golden", "bp1.cfg"),
                    encoding="utf-8").read()
        assert "BOOT5trap" not in text, (
            "the repository's first record of this device carries the "
            "throwaway password, in history, where a remote may publish it")

    def test_the_RO_community_survives(self, world):
        """The control: removing RW must not take the fleet's RO with it."""
        self._run(world)
        text = open(os.path.join(world["repo"], "golden", "bp1.cfg"),
                    encoding="utf-8").read()
        assert "snmp-server community public RO" in text

    def test_it_is_one_commit(self, world):
        import subprocess

        before = subprocess.run(["git", "-C", world["repo"], "rev-list",
                                 "--count", "HEAD"], capture_output=True,
                                text=True).stdout.strip()
        self._run(world)
        after = subprocess.run(["git", "-C", world["repo"], "rev-list",
                                "--count", "HEAD"], capture_output=True,
                               text=True).stdout.strip()
        assert int(after) == int(before) + 1, "one commit, one true record"


class TestAfterASuccessfulRun:

    def test_the_csv_row_carries_the_ROTATED_credential(self, world):
        """Not the bootstrap value, and not empty — the bug this ordering
        fixes at its cause, because promotion reads the credential back out
        of the override rather than being handed it."""
        from modules.config import get_list_data_dir
        from modules.device import decrypt_field, load_saved_devices
        from modules.nsot.onboard import run_phase_two

        run_phase_two(world["repo"], "bp1", "probe", actor="t", **_steps())
        rows = load_saved_devices(
            os.path.join(get_list_data_dir("probe"), "devices.csv"))
        assert [r["hostname"] for r in rows] == ["bp1"]
        assert decrypt_field(rows[0]["password"]) == "R0tatedValue99"

    def test_verified_at_and_netbox_id_are_set(self, world):
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import run_phase_two

        run_phase_two(world["repo"], "bp1", "probe", actor="t", **_steps())
        _identity, entry = _m.find_by_name(world["repo"], "bp1")
        assert entry["verified_at"]
        assert entry["netbox_id"] == 7

    def test_the_staging_is_empty(self, world):
        """Rotation clearing it is what "rotated" means; a staged credential
        left behind is a rotation that did not finish."""
        from modules.nsot.onboard import (run_phase_two,
                                          stage_bootstrap_credential,
                                          staged_bootstrap_credential)

        stage_bootstrap_credential(world["repo"], "bp1", "BOOT5trap")
        run_phase_two(world["repo"], "bp1", "probe", actor="t",
                      **_steps(rotate=lambda r, h, l, **k: (
                          __import__("modules.nsot.onboard", fromlist=["x"])
                          .clear_bootstrap_credential(r, h),
                          {"rotated": True, "state": "rotated"})[1]))
        assert staged_bootstrap_credential(world["repo"], "bp1") is None


class TestAbandonRefusesAPromotedDevice:

    def test_it_refuses_and_says_why(self, world):
        from modules.nsot.onboard import abandon_onboarding, run_phase_two

        run_phase_two(world["repo"], "bp1", "probe", actor="t", **_steps())
        out = abandon_onboarding(world["repo"], "bp1", "probe")
        assert out["ok"] is False
        assert "promoted" in out["error"]
        assert "device list" in out["error"], (
            "the refusal must name what to do instead")

    def test_a_pending_device_is_still_abandonable(self, world):
        """The control. A refusal that refused everything would pass the
        test above and make abandon useless."""
        from modules.nsot.onboard import abandon_onboarding

        out = abandon_onboarding(
            world["repo"], "bp1", "probe",
            remove_netbox=lambda l, h, dry_run=False: {"ok": True,
                                                       "deleted": [],
                                                       "skipped": []})
        assert out["ok"] is True, out
        assert out["released"] == "bp1"
