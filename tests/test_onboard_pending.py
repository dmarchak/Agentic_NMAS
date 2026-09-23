"""Pending is a state, not a hiding place — and it has an exit.

A device is onboarded when the tool has REACHED it. Until then it is in the
manifest, in NetBox and in git, and deliberately **not in the inventory**: a
device in the inventory is one the tool will poll, back up, drift-check, pool
a connection for and offer in bulk ops, and one that has never answered would
read as unreachable in nine places and mean nothing in any of them.

**The wrong-and-looks-right state is "pending for ever and nobody notices."**
So a count is not enough and neither is a list: every row carries its age and
a state, and a device past the threshold is flagged rather than merely
listed. `promote_device()` was written before the flag, because a state an
operator cannot clear is the trap just removed from the identity map wearing
a new name.
"""

import os
import time

import pytest

from modules.nsot.manifest import (PENDING_OVERDUE_SECONDS,
                                   PENDING_STALE_SECONDS)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    from modules.nsot import repo as _repo

    list_dir = tmp_path / "probe"
    repo_dir = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo_dir, "host_vars"), exist_ok=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda k, d=None: {"nsot_git_author_name": "NMAS",
                                           "nsot_git_author_email": "n@l"}.get(k, d))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda c: None)
    monkeypatch.setattr("modules.secrets_store.KEY_FILE", str(tmp_path / "key.key"))
    _repo.init_repo(repo_dir)
    return repo_dir


def _pending(repo, name="bp1", ip="203.0.113.31", age=0):
    from modules.nsot import manifest as _m
    from modules.nsot.repo import GoldenItem, adopt_identity

    identity = adopt_identity(repo, GoldenItem(name, "", ip))
    _m.upsert_device(repo, identity, name, mgmt_ip=ip,
                     platform="cisco_iosxe", pending=True)
    if age:
        data = _m.load(repo)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                              time.gmtime(time.time() - age))
        data["devices"][identity]["onboarded_at"] = stamp
        _m.save(repo, data)
    return identity


class TestPendingIsVisibleWithItsAge:

    def test_a_new_device_is_pending(self, repo):
        from modules.nsot import manifest as _m

        _pending(repo)
        rows = _m.pending_devices(repo)
        assert len(rows) == 1
        assert rows[0]["name"] == "bp1"
        assert rows[0]["state"] == "in_flight"

    def test_an_hour_is_normal_and_does_not_draw_attention(self, repo):
        """A flag that fires on the ordinary case stops meaning anything."""
        from modules.nsot import manifest as _m

        _pending(repo, age=3600)
        assert _m.pending_devices(repo)[0]["state"] == "in_flight"

    def test_past_a_day_it_is_flagged(self, repo):
        """The gap is one human action and a six-minute boot. A device still
        pending after a working day means the plan changed or it was
        forgotten, and neither is visible from a count."""
        from modules.nsot import manifest as _m

        _pending(repo, age=PENDING_OVERDUE_SECONDS + 60)
        assert _m.pending_devices(repo)[0]["state"] == "overdue"

    def test_past_a_week_it_is_stale(self, repo):
        from modules.nsot import manifest as _m

        _pending(repo, age=PENDING_STALE_SECONDS + 60)
        assert _m.pending_devices(repo)[0]["state"] == "stale"

    def test_the_age_is_reported_not_just_the_state(self, repo):
        """'Pending' and 'pending since Tuesday' are different facts."""
        from modules.nsot import manifest as _m

        _pending(repo, age=5000)
        assert _m.pending_devices(repo)[0]["age_seconds"] >= 4900

    def test_the_oldest_is_first(self, repo):
        from modules.nsot import manifest as _m

        _pending(repo, "old", "203.0.113.1", age=PENDING_STALE_SECONDS + 5)
        _pending(repo, "new", "203.0.113.2", age=10)
        assert [r["name"] for r in _m.pending_devices(repo)] == ["old", "new"]


class TestPromotionIsTheExit:

    def test_promoting_clears_pending(self, repo):
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import promote_device

        _pending(repo)
        out = promote_device(repo, "bp1", "probe", actor="t",
                             username="admin", password="s3cret")
        assert out["ok"] is True, out
        assert out["verified"] is True
        assert _m.pending_devices(repo) == []

    def test_promoting_adds_the_inventory_row(self, repo):
        """**The claim the review screen made and no step performed.**

        `writes_devices_csv` reported `yes` while nothing wrote a row, so a
        successful onboarding produced a device absent from every inventory
        — `load_saved_devices()` is the single dispatch point for the
        connection pool, backups, the terminal, bulk ops, drift and the AI
        tools.
        """
        from modules.config import get_list_data_dir
        from modules.device import load_saved_devices
        from modules.nsot.onboard import promote_device

        _pending(repo)
        csv_path = os.path.join(get_list_data_dir("probe"), "devices.csv")
        assert not os.path.exists(csv_path) or not load_saved_devices(csv_path)

        promote_device(repo, "bp1", "probe", username="admin",
                       password="s3cret", secret="s3cret")
        rows = load_saved_devices(csv_path)
        assert [r["hostname"] for r in rows] == ["bp1"]
        assert rows[0]["ip"] == "203.0.113.31"

    def test_the_credential_is_encrypted_in_the_row(self, repo):
        from modules.config import get_list_data_dir
        from modules.device import decrypt_field, load_saved_devices
        from modules.nsot.onboard import promote_device

        _pending(repo)
        promote_device(repo, "bp1", "probe", username="admin",
                       password="s3cret", secret="s3cret")
        row = load_saved_devices(
            os.path.join(get_list_data_dir("probe"), "devices.csv"))[0]
        assert row["password"] != "s3cret", "stored in the clear"
        assert decrypt_field(row["password"]) == "s3cret"

    def test_promoting_twice_is_not_two_rows(self, repo):
        from modules.config import get_list_data_dir
        from modules.device import load_saved_devices
        from modules.nsot.onboard import promote_device

        _pending(repo)
        promote_device(repo, "bp1", "probe", username="admin", password="p")
        second = promote_device(repo, "bp1", "probe", username="admin",
                                password="p")
        rows = load_saved_devices(
            os.path.join(get_list_data_dir("probe"), "devices.csv"))
        assert len(rows) == 1, rows
        assert second["csv_row"] is False

    def test_a_device_that_was_never_onboarded_is_refused(self, repo):
        from modules.nsot.onboard import promote_device

        out = promote_device(repo, "never", "probe")
        assert out["ok"] is False
        assert "no identity" in out["error"]

    def test_promotion_does_not_decide_the_device_answered(self):
        """It records a finding the caller established. A function that both
        tested reachability and promoted on its own result would be its own
        witness."""
        import ast
        import inspect
        import textwrap

        from modules.nsot import onboard

        tree = ast.parse(textwrap.dedent(
            inspect.getsource(onboard.promote_device)))
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        for reaching in ("ConnectHandler", "connect", "send_command", "ping",
                         "get_connection"):
            assert reaching not in names, (
                f"promote_device calls {reaching} — it would be its own "
                f"witness for the thing it records")


class TestPendingAndAbandonAgree:

    def test_an_abandoned_pending_device_leaves_no_pending_row(self, repo):
        """The two exits from pending are promotion and abandon. A device
        that left by one must not still be listed by the other."""
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import abandon_onboarding

        _pending(repo)
        assert _m.pending_devices(repo)
        out = abandon_onboarding(
            repo, "bp1", "probe",
            remove_netbox=lambda l, h, dry_run=False: {"ok": True,
                                                       "deleted": [],
                                                       "skipped": []})
        assert out["ok"] is True, out
        assert _m.pending_devices(repo) == []


class TestPromotionRefusesTheBootstrapCredential:
    """`mint_bootstrap_credential` says the value is *"never written to
    devices.csv or the credential store"*. Promotion is the first call that
    writes a durable row, so it is where that sentence stops being a
    convention and becomes a check.

    Refused rather than warned: a throwaway password stored as a device's
    durable credential is a wrong thing that would look exactly like a
    working one — SSH succeeds, the row is present, and the credential dies
    at the next rotation.
    """

    def test_the_staged_value_is_refused(self, repo):
        from modules.nsot.onboard import (promote_device,
                                          stage_bootstrap_credential)

        _pending(repo)
        stage_bootstrap_credential(repo, "bp1", "OneTimeBootstrapPass99")
        out = promote_device(repo, "bp1", "probe", username="admin",
                             password="OneTimeBootstrapPass99")
        assert out["ok"] is False
        assert "rotate it first" in out["error"]

    def test_a_rotated_credential_is_accepted(self, repo):
        """The control. A guard that refused every password would pass the
        test above and make promotion impossible."""
        from modules.nsot.onboard import (promote_device,
                                          stage_bootstrap_credential)

        _pending(repo)
        stage_bootstrap_credential(repo, "bp1", "OneTimeBootstrapPass99")
        out = promote_device(repo, "bp1", "probe", username="admin",
                             password="TheRotatedOne42")
        assert out["ok"] is True, out

    def test_no_staged_value_does_not_block_promotion(self, repo):
        """Rotation clears the staging on success, so the common case has
        nothing staged at all."""
        from modules.nsot.onboard import promote_device

        _pending(repo)
        assert promote_device(repo, "bp1", "probe", username="admin",
                              password="anything")["ok"] is True
