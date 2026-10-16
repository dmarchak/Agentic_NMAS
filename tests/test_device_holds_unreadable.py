"""C988: an unreadable lock store is never "nothing held".

`device_ops` turned any `OSError` from listing a network's lock folder, or the root of them,
into an empty list, and any error opening a lock file into "nobody holds it", so a permission
error read as nothing running, and the update gate's `held_anywhere()` would have let an
update restart the app under a device another process held. Absent and unreadable are
different states: only ABSENT (`FileNotFoundError`) is nothing held; any other error raises
`device_ops.HoldsUnreadable`, naming the path, and each caller says it, failing closed.

Measured here with REAL unreadable folders and files (`chmod`, in a data folder of this test's
own; skipped as root, which `chmod` does not stop):

- the reads: an absent store is nothing held (the control); an unlistable root, an unlistable
  network folder, a root that can be listed but not searched, an unreadable lock file and an
  unreadable kept log each raise, naming the path; `busy_text` says the device is treated as
  held; indexing never marks a folder done past a lock file it could not read;
- each caller: the Update preview's operations gate refused with the reason, a waiting update
  kept waiting, `/health/operations` 500 with the reason, the list delete refused naming why,
  the In progress chip red naming the network (`read_all` too, `read` raising), Needs
  attention's interrupted operations and History's say "could not be read", a pending receipt
  drawn as its own row, Save's plan and Reload's gate refuse the device, the scheduled
  rotation's preview and run skip it, and job health shows the rows a hold would have hidden.
"""

import json
import os
import types

import pytest

from modules.nsot import device_ops as D
from tests.test_reload_v2 import _gate, _reads
from tests.test_save_v2 import lab  # noqa: F401 (the fixture)
from tests.test_scheduled_rotation import NOW, Rotations, _run, _states
from tests.test_update_button import _plan_kw
from tests.test_update_when_ci_passes import VERIFIED, _defer, _kw
from tests.test_update_when_ci_passes import store as update_store  # noqa: F401

fcntl = pytest.importorskip("fcntl")
pytestmark = pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                                reason="chmod does not stop root from reading")

NET = "C988net"
WORDS = "the device holds could not be read"


class Store:
    """A data folder of the test's own, its paths found independently of the code under test,
    and every mode it changes put back so the folder can be removed."""

    def __init__(self, data):
        self.data = str(data)
        self.root = os.path.join(self.data, "device_ops")
        self._changed = []

    def folder(self, net=NET):
        from modules import config
        return os.path.join(self.root, config.list_slug(net))

    def leftover(self, host="r1", net=NET):
        """A lock file a process that ended left its record in: listed as interrupted, and
        read by every hold query."""
        os.makedirs(self.folder(net), exist_ok=True)
        path = os.path.join(self.folder(net), f"{host}.lock")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"device": host, "list": net, "operation": "deploy",
                       "actor": "other@example.invalid", "started": 1.0, "pid": 4242}, fh)
        return path

    def chmod(self, path, mode):
        self._changed.append(path)
        os.chmod(path, mode)

    def restore(self):
        for path in reversed(self._changed):
            os.chmod(path, 0o700)


@pytest.fixture
def store(tmp_path, monkeypatch):
    from modules import config

    data = tmp_path / "holds-data"
    data.mkdir()
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    s = Store(data)
    yield s
    s.restore()


def _unlistable_folder(s):
    s.leftover()
    s.chmod(s.folder(), 0)
    return s.folder()


def _unlistable_root(s):
    s.leftover()
    s.chmod(s.root, 0)
    return s.root


def _unsearchable_root(s):
    """Listable, not searchable: each entry is named, none can be opened. `os.path.isdir`
    answers False for every one, which read as no network ever held a device."""
    s.leftover()
    s.chmod(s.root, 0o444)
    return s.folder()


SHAPES = {"an unlistable network folder": _unlistable_folder,
          "an unlistable root": _unlistable_root,
          "a root listed but not searchable": _unsearchable_root}


# ---------------------------------------------------------------------------------- the reads

class TestTheReads:
    def test_an_absent_store_is_nothing_held(self, store):
        """The control: no folder at all is no device ever held, and raises nothing."""
        assert not os.path.exists(store.root)
        assert D.held_anywhere() == [] and D.interrupted_anywhere() == []
        assert D.held(NET) == [] and D.interrupted(NET) == [] and D.holder(NET, "r1") is None
        assert D.busy_text(NET, "r1") == ""

    def test_a_readable_store_reads_its_leftover(self, store):
        """The control for every shape below: the same store, readable, is read."""
        store.leftover()
        assert [r["device"] for r in D.interrupted_anywhere()] == ["r1"]
        assert D.held_anywhere() == [], "a leftover is interrupted, never held"

    @pytest.mark.parametrize("shape", sorted(SHAPES))
    def test_an_unreadable_store_raises_naming_the_path(self, store, shape):
        path = SHAPES[shape](store)
        for read in (D.held_anywhere, D.interrupted_anywhere):
            with pytest.raises(D.HoldsUnreadable) as got:
                read()
            assert path in str(got.value) and "Permission denied" in str(got.value), shape

    def test_an_unlistable_network_folder_raises_for_that_network(self, store):
        path = _unlistable_folder(store)
        for read in (D.held, D.in_flight):
            with pytest.raises(D.HoldsUnreadable) as got:
                read(NET)
            assert str(got.value) == f"{path}: Permission denied"
        with pytest.raises(D.HoldsUnreadable) as got:     # its kept log, inside it, first
            D.interrupted(NET)
        assert str(got.value) == f"{path}/{D.INTERRUPTED_LOG}: Permission denied"

    def test_an_unreadable_lock_file_is_never_nobody(self, store):
        """A lock file another user's process made (a CLI run as root): the device may be
        held, and `os.path.exists` cannot say so."""
        path = store.leftover("r1")
        store.chmod(path, 0)
        with pytest.raises(D.HoldsUnreadable) as got:
            D.holder(NET, "r1")
        assert str(got.value) == f"{path}: Permission denied"
        for read in (D.held, D.interrupted):
            with pytest.raises(D.HoldsUnreadable):
                read(NET)
        assert D.holder(NET, "r9") is None, "a device with no lock file is still nobody"

    def test_busy_text_treats_an_unreadable_hold_as_held(self, store):
        path = store.leftover("r1")
        store.chmod(path, 0)
        words = D.busy_text(NET, "r1")
        assert words == (f"r1's hold could not be read ({path}: Permission denied): it is "
                         "treated as held, and nothing is sent to it until it can be read")

    def test_an_unreadable_kept_log_raises_naming_it(self, store):
        store.leftover("r1")
        kept = os.path.join(store.folder(), D.INTERRUPTED_LOG)
        with open(kept, "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        store.chmod(kept, 0)
        with pytest.raises(D.HoldsUnreadable) as got:
            D.interrupted(NET)
        assert str(got.value) == f"{kept}: Permission denied"

    def test_indexing_stops_at_a_lock_file_it_cannot_read(self, store, monkeypatch):
        """A folder said indexed with a record left unmarked would hide that record from every
        reader for good; it stays read in full instead."""
        store.leftover("r1")
        bad = os.path.join(store.folder(), "r1.lock")
        real = os.stat

        def stat(path, *a, **k):
            if os.fspath(path) == bad:
                raise PermissionError(13, "Permission denied", bad)
            return real(path, *a, **k)

        monkeypatch.setattr(D.os, "stat", stat)
        assert D.index_all() == []
        monkeypatch.setattr(D.os, "stat", real)
        assert not D.indexed(NET)
        assert [r["device"] for r in D.interrupted(NET)] == ["r1"]


# -------------------------------------------------------------------------------- the callers

class TestTheUpdateGate:
    def test_the_operations_gate_refuses_naming_the_folder(self, store):
        from modules import update_op

        path = _unlistable_folder(store)
        kw = _plan_kw()
        kw.pop("operations")
        p = update_op.plan(**kw)
        gate = next(g for g in p["gates"] if g["name"] == update_op.OPERATIONS_GATE)
        assert gate["state"] == "fail" and not p["selectable"]
        assert gate["detail"].startswith(f"{WORDS}: {path}: Permission denied. Nothing can "
                                         "say no device is held")
        store.restore()
        p = update_op.plan(**kw)
        gate = next(g for g in p["gates"] if g["name"] == update_op.OPERATIONS_GATE)
        assert gate["state"] == "pass" and p["selectable"], "the control: readable passes"

    def test_a_waiting_update_keeps_waiting(self, store, update_store):  # noqa: F811
        from modules import update_op

        _defer()
        _unlistable_folder(store)
        kw = _kw(ci=VERIFIED)
        kw.pop("operations")                        # asked of the store, not handed in
        assert update_op.release_deferred(**kw) is None
        assert update_op.deferred()["target"] == "b" * 40, "still waiting"
        requests = update_store / "requests"
        assert not requests.exists() or os.listdir(requests) == []
        store.restore()
        assert update_op.release_deferred(**kw)["outcome"] == "requested", "the control"


class TestHealthOperations:
    def test_it_answers_500_with_the_reason(self, store):
        import app as nmas

        path = _unlistable_folder(store)
        resp = nmas.app.test_client().get("/health/operations")
        body = resp.get_json()
        assert resp.status_code == 500 and body["ok"] is False
        assert body["error"] == f"{WORDS}: {path}: Permission denied"


class TestTheListDelete:
    def test_the_delete_is_refused_naming_why(self, store):
        from modules import device

        path = _unlistable_folder(store)
        assert device._list_busy(NET) == (
            f"List '{NET}' was not deleted: its device holds could not be read ({path}: "
            "Permission denied), so nothing can say no operation is writing to it. Nothing "
            "was changed; delete it once they can be read.")


class TestTheInProgressChip:
    def test_the_chip_is_red_naming_the_network(self, store):
        from modules import in_flight

        path = _unlistable_folder(store)
        got = in_flight.chip([NET], "viewer@example.invalid")
        assert got["unread"] == [(NET, f"HoldsUnreadable: {path}: Permission denied")]
        assert got["level"] == "danger" and "1 network(s) unread" in got["words"]

    def test_diagnostics_names_it_and_the_read_raises(self, store):
        from modules import in_flight

        path = _unlistable_folder(store)
        assert in_flight.read_all([NET])["unread"] == [
            (NET, f"HoldsUnreadable: {path}: Permission denied")]
        with pytest.raises(D.HoldsUnreadable):
            in_flight.read(NET)


class TestNeedsAttentionAndHistory:
    def test_interrupted_operations_say_could_not_be_read(self, store):
        from modules import attention

        path = _unlistable_folder(store)
        got = attention.interrupted_source()
        assert got["state"] == "unreadable"
        (row,) = got["rows"]
        assert row["what"] == "Operations that did not finish could not be read"
        assert row["cause"].startswith(f"{WORDS}: {path}/{D.INTERRUPTED_LOG}: Permission "
                                       "denied. This is not the same as nothing needing")

    def test_a_pending_receipt_is_drawn_as_its_own_row(self, store):
        from modules import attention

        path = store.leftover("r1")
        store.chmod(path, 0)
        assert attention._pending_is_named(NET, "r1", {"at": "2026-10-16T00:00:00Z"}) is False

    def test_history_says_could_not_be_read(self, store):
        from modules import history_sources

        path = _unlistable_folder(store)
        ctx = {"ref": types.SimpleNamespace(name=NET), "device": "r1", "members": None,
               "since": None, "limit": 10}
        got = history_sources.interrupted(ctx)
        assert got["errors"] == [f"{WORDS}: {path}/{D.INTERRUPTED_LOG}: Permission denied"]
        assert got["events"] == []


class TestDeviceOperationsRefuse:
    def test_save_leaves_the_device_out_as_held(self, lab):  # noqa: F811
        from modules import config
        from modules.nsot import save_op

        folder = os.path.join(config.DATA_DIR, "device_ops", config.list_slug("Lab"))
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "r3.lock")
        open(path, "w", encoding="utf-8").close()
        os.chmod(path, 0)
        try:
            (r3,) = save_op.plan("Lab", ["r3"])["devices"]
        finally:
            os.chmod(path, 0o600)
        assert r3["group"] == "held"
        assert r3["why"].startswith(f"r3's hold could not be read ({path}: Permission denied)")
        assert save_op.plan("Lab", ["r3"])["devices"][0]["group"] == "save", "the control"

    def test_reload_s_busy_gate_fails(self, lab):  # noqa: F811
        from modules import config
        from modules.nsot import reload_op

        folder = os.path.join(config.DATA_DIR, "device_ops", config.list_slug("Lab"))
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "r2.lock")
        open(path, "w", encoding="utf-8").close()
        os.chmod(path, 0)
        try:
            gate = _gate(reload_op.judge("Lab", "r2", "cisco_iosxe", _reads(lab)), "busy")
        finally:
            os.chmod(path, 0o600)
        assert gate["state"] == "fail" and "r2's hold could not be read" in gate["detail"]
        gate = _gate(reload_op.judge("Lab", "r2", "cisco_iosxe", _reads(lab)), "busy")
        assert gate["state"] == "at_apply", "the control"


class TestScheduledRotation:
    @pytest.fixture(autouse=True)
    def _own_settings(self, tmp_path, monkeypatch):
        """As test_scheduled_rotation's `data`: its settings and profiles of its own."""
        monkeypatch.setattr("modules.config.USER_SETTINGS_FILE",
                            str(tmp_path / "user_settings.json"))
        monkeypatch.setattr("modules.credentials._FILE",
                            str(tmp_path / "credential_profiles.json"))

    def _r3_unreadable(self, store):
        path = store.leftover("r3", net="Lab")
        store.chmod(path, 0)
        return path

    def test_the_run_skips_it_and_the_rest_run(self, store, monkeypatch):
        path = self._r3_unreadable(store)
        rot = Rotations()
        got = _run(monkeypatch, _states(), trigger="scheduled", rotate=rot)
        assert [c["device"] for c in rot.calls] == ["r1"]
        (skip,) = got["skipped"]
        assert skip["device"] == "r3"
        assert (f"its hold could not be read ({path}: Permission denied), so it is treated "
                "as held") in skip["why"]

    def test_the_preview_says_it(self, store, monkeypatch):
        from modules.nsot import scheduled_rotation as SR

        path = self._r3_unreadable(store)
        states = _states()
        monkeypatch.setattr(SR, "device_states", lambda now=None, **_k: states)
        got = SR.preview(now=NOW)
        (r3,) = [c for c in got["chosen"] if c["device"] == "r3"]
        assert r3.get("now", "").startswith(
            f"its hold could not be read ({path}: Permission denied)"), r3


class TestJobHealth:
    def test_the_rows_a_hold_hides_are_shown(self, store):
        """The held set only HIDES rows; unreadable, it hides none."""
        from modules import job_health
        from modules.nsot import credential_rotation as cr

        _unlistable_folder(store)
        rec = [{"device": "s1", "state": cr.ROTATED_PENDING_PERSIST,
                "at": "2026-10-06T19:00:00Z"}]
        rows = job_health.rotation_rows(records=rec, known=({"s1"}, ""))
        assert [r["state"] for r in rows] == ["not_safe_to_reboot"]

    def test_a_staged_rotation_is_shown(self, store, tmp_path, monkeypatch):
        from modules import job_health
        from modules.nsot import credential_rotation as cr

        monkeypatch.setattr(cr, "staged_devices", lambda repo: [{"device": "r1", "since": 1}])
        monkeypatch.setattr("modules.nsot.adopt.is_adoption_staged", lambda repo, d: False)

        def unreadable(_l, h):
            raise D.HoldsUnreadable("/x/r1.lock", PermissionError(13, "Permission denied"))

        rows = job_health.staged_rotation_rows(
            lists=[{"name": NET, "filename": "c988"}], holder=unreadable)
        assert [r["unit"] for r in rows] == [f"rotation-staged:{NET}/r1"]
