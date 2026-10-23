"""C1597 and C1613 (the operator, 2026-10-23: "Abandon can undo a static-path Create: the
Planned NetBox record and console path kept, everything Create made removed, no Kea on this
path"): an out-of-band (``ztp_console``) onboarding undone and run again.

s5's Planned record was made through Mercury's chokepoint before Add device, so it is in the
network's created-object record. Abandon's NetBox step read that record as its own to delete
(with its console port and cable, by NetBox's cascade), and the one-decision run's undo, which
keeps NetBox, could not give the name back: the release re-derived the reference and refused,
and a retry was refused at Create.

On a real repository, a real Create (`run_onboarding` with `real_steps`: the credential staged,
its override, the intent and identity committed, the record's id on the entry) of a static
out-of-band plan that read a Planned record, the fake NetBox holding that record, its console
port, the console server's port and the cable between them, all in Mercury's created-object
record, and a real SSH host key kept at the device's address:

1. Abandon keeps the Planned record and its console path (the remover never called), removes
   everything Create made (intent, staged credential, override, host key) and gives the name
   back;
2. the same name is then planned and created again;
3. Abandon's dry run says the same and writes nothing, the created-object record unchanged
   (C1596's shape);
4. the one-decision run's undo gives the name back and keeps NetBox;
5. a Planned record Verify set Active is not kept as done: the step fails naming the status and
   how to finish, and the name is not released;
6. controls: an entry with no NetBox id, and one whose id Verify wrote for a record it made,
   still go through the provenance-gated remover.

Documentation addresses (RFC 5737) throughout."""

import os

import paramiko
import pytest

from modules import credentials, host_keys, netbox_guard
from modules.nsot import device_environment as DE
from modules.nsot import manifest, onboard, oob_onboard
from tests.fake_netbox import FakeNetBox
from tests.test_console_ztp_static import ADDRESS, _plan
from tests.test_onboard_plan import lab  # noqa: F401 - the fixture

LIST = "probe"
BASE = "http://netbox.example.test:8000"
ACTOR = "p@example.invalid"
PLANNED = {"value": "planned", "label": "Planned"}


class _World:
    """The fake NetBox with s5's Planned record and console path, all recorded as Mercury's,
    and the stores Create and Abandon write, each in the test's own folder."""

    def __init__(self, lab, tmp_path, monkeypatch):
        from modules import config, secrets_store
        import modules.netbox_client as nbc

        data = tmp_path / "data"
        data.mkdir()
        monkeypatch.setattr(config, "DATA_DIR", str(data))
        monkeypatch.setattr("modules.config.list_data_path", config.get_list_data_dir)
        monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "creds.json"))
        monkeypatch.setattr(secrets_store, "KEY_FILE", str(lab["dir"] / "key.key"))
        for name in ("_CREATED_IDS_FILE", "_MODIFIED_FILE", "_ADOPTED_FILE", "_REMOVALS_FILE"):
            monkeypatch.setattr(netbox_guard, name, str(tmp_path / f"{name.lower()}.json"))
        # Whether another device has the address is host_keys' own question, answered "none".
        monkeypatch.setattr(host_keys, "holders",
                            lambda ip, **k: {"others": [], "unreadable": []})
        self.repo = lab["repo"]
        self.fake = fake = FakeNetBox()
        self.dev = fake.seed("dcim/devices", {"name": "s5", "status": dict(PLANNED),
                                              "tags": [{"slug": "nmas-managed"}]})
        self.cs = fake.seed("dcim/devices", {"name": "clab-console", "status": "active"})
        self.port = fake.seed("dcim/console-ports", {"device": self.dev["id"], "name": "con 0"})
        self.sport = fake.seed("dcim/console-server-ports", {"device": self.cs["id"],
                                                             "name": "port 1"})
        self.cable = fake.seed("dcim/cables", {
            "a_terminations": [{"object_type": "dcim.consoleport",
                                "object_id": self.port["id"]}],
            "b_terminations": [{"object_type": "dcim.consoleserverport",
                                "object_id": self.sport["id"]}],
            "status": "connected", "label": ""})
        # Made through Mercury's chokepoint before Add device, as s5's were (C1597).
        for endpoint, obj in (("dcim/devices", self.dev), ("dcim/devices", self.cs),
                              ("dcim/console-ports", self.port),
                              ("dcim/console-server-ports", self.sport),
                              ("dcim/cables", self.cable)):
            netbox_guard.record_created(LIST, endpoint, obj["id"], name=obj.get("name", ""))
        monkeypatch.setattr(nbc, "_nb_ready", lambda: (True, "", fake, BASE))
        # The plan reads the Planned record (the environment read, stood in for with the
        # record the fake holds, as tests/test_onboard_planned_record.py's `held` does).
        monkeypatch.setattr(onboard, "_name_in_netbox", lambda hostname: (True, True))
        monkeypatch.setattr(DE, "read", lambda hostname, **k: DE.Environment(
            source=f"NetBox device {hostname} (id {self.dev['id']})", netbox=self.record()))
        self.removals = []
        monkeypatch.setattr("modules.netbox_client.remove_device_from_netbox",
                            self._remover_called)

    def record(self):
        return {"id": self.dev["id"], "status": "planned", "status_label": "Planned",
                "site": "Default", "role": "switch", "role_name": "Access switch",
                "role_kind": "switch", "platform": "", "platform_name": "",
                "tags": ["nmas-managed"], "url": f"{BASE}/dcim/devices/{self.dev['id']}/"}

    def _remover_called(self, *a, **k):
        self.removals.append((a, k))
        return {"ok": False, "error": "the remover was called"}

    def create(self, planned=True):
        plan = _plan()
        assert plan.onboardable, plan.blocking_reasons
        assert plan.planned_netbox_id == (self.dev["id"] if planned else None), \
            "floor: the plan read the record, or none"
        got = onboard.run_onboarding(plan, repo=self.repo,
                                     **onboard.real_steps(self.repo, actor=ACTOR))
        assert got["ok"] and not got.get("failed_at"), got
        return plan

    def keep_key(self):
        assert host_keys.check(ADDRESS, paramiko.ECDSAKey.generate(),
                               owner="test:first-contact")["state"] == "kept"

    def abandon(self, **kw):
        dry = onboard.abandon_onboarding(self.repo, "s5", LIST, actor=ACTOR, dry_run=True, **kw)
        return dry, onboard.abandon_onboarding(self.repo, "s5", LIST, actor=ACTOR,
                                               confirmed=onboard.abandon_fingerprint(dry), **kw)

    def netbox_held(self):
        """Whether the Planned record, its console port, the server's port and the cable are
        all still in NetBox."""
        ids = {ep: {o["id"] for o in self.fake.objects(ep)} for ep in (
            "dcim/devices", "dcim/console-ports", "dcim/console-server-ports", "dcim/cables")}
        return (self.dev["id"] in ids["dcim/devices"] and self.port["id"] in
                ids["dcim/console-ports"] and self.sport["id"] in ids["dcim/console-server-ports"]
                and self.cable["id"] in ids["dcim/cables"])

    def created_record(self) -> bytes:
        with open(netbox_guard._CREATED_IDS_FILE, "rb") as fh:  # noqa: SLF001 - the store
            return fh.read()


@pytest.fixture
def world(lab, tmp_path, monkeypatch):  # noqa: F811 - the fixture
    return _World(lab, tmp_path, monkeypatch)


def _step(out, name):
    return next(s for s in out["steps"] if s["step"] == name)


KEPT = "kept: the Planned record s5 (id {id}) existed before Add device; Create made nothing in " \
       "NetBox"


class TestAbandonKeepsThePlannedRecord:
    def test_everything_create_made_goes_and_the_record_and_console_path_stay(self, world):
        world.create()
        world.keep_key()
        entry = manifest.find_by_name(world.repo, "s5")[1]
        assert entry["netbox_id"] == world.dev["id"] and entry["address_source"] == "ztp_console"
        assert onboard.staged_bootstrap_credential(world.repo, "s5"), "floor: Create staged it"
        assert credentials.has_device_override(ADDRESS), "floor: Create wrote the override"
        assert (host_keys.held(ADDRESS) or {}).get("fingerprint"), "floor: a key is kept"
        _dry, out = world.abandon()
        assert out["ok"] is True, out
        assert _step(out, "netbox") == {"step": "netbox", "ok": True,
                                        "detail": KEPT.format(id=world.dev["id"])}
        assert world.removals == [], "the remover was called on a Planned record Create read"
        assert world.netbox_held() and not world.fake.deletes and not world.fake.patches
        assert not os.path.exists(os.path.join(world.repo, "host_vars", "s5.yml"))
        assert not onboard.staged_bootstrap_credential(world.repo, "s5")
        assert not credentials.has_device_override(ADDRESS)
        assert not (host_keys.held(ADDRESS) or {}).get("fingerprint")
        assert out["released"] == "s5"
        assert manifest.find_by_name(world.repo, "s5") == (None, None)

    def test_the_same_name_is_created_again(self, world):
        world.create()
        assert world.abandon()[1]["ok"]
        again = _plan()
        assert not [r for r in again.blocking_reasons if "identity" in r or "already" in r], \
            again.blocking_reasons
        world.create()
        assert manifest.find_by_name(world.repo, "s5")[1]["netbox_id"] == world.dev["id"]

    def test_the_dry_run_says_kept_and_writes_nothing(self, world):
        world.create()
        before = world.created_record()
        dry = onboard.abandon_onboarding(world.repo, "s5", LIST, actor=ACTOR, dry_run=True)
        assert dry["ok"] is True, dry
        assert _step(dry, "netbox")["detail"] == KEPT.format(id=world.dev["id"])
        assert _step(dry, "identity") == {"step": "identity", "ok": True,
                                          "detail": "would release"}
        assert world.removals == [] and world.created_record() == before
        assert manifest.find_by_name(world.repo, "s5")[0], "a dry run released nothing"


class TestTheUndoGivesTheNameBack:
    def test_the_one_decision_run_s_undo_after_create(self, world):
        world.create()
        out = oob_onboard.undo_created(LIST, "s5", ACTOR)
        assert out["ok"] is True and out["remaining"] == [], out
        assert f"netbox: {KEPT.format(id=world.dev['id'])}" in out["undone"]
        assert any(u.startswith("identity: released 's5'") for u in out["undone"]), out
        assert manifest.find_by_name(world.repo, "s5") == (None, None)
        assert world.netbox_held() and world.removals == []


class TestARecordVerifyChangedIsNotKeptAsDone:
    def test_an_active_record_fails_the_step_and_keeps_the_name(self, world):
        world.create()
        world.dev["status"] = {"value": "active", "label": "Active"}
        dry, out = world.abandon()
        nb = _step(out, "netbox")
        assert nb["ok"] is False
        assert nb["detail"] == (f"the Planned record s5 (id {world.dev['id']}) is now Active, "
                                "not Planned: Verify changed it, so it is no longer the record "
                                "Create read and Abandon cannot keep it as done")
        how = [r["how_to_finish"] for r in out["remaining"] if r["step"] == "netbox"]
        assert how == ["set s5's status back to Planned in NetBox and run abandon again, or "
                       "Retire s5"]
        assert out["ok"] is False and out["released"] == ""
        assert manifest.find_by_name(world.repo, "s5")[0], "the name was released"
        assert _step(out, "identity")["ok"] is False
        assert world.removals == [] and world.netbox_held()
        assert dry["ok"] is False, "the preview said it would finish"

    def test_a_hand_made_record_verify_changed_keeps_the_name_too(self, world):
        """A Planned record made by hand (R6's and R7's in Lab 8) is in no created-object
        record, so the release's own references would not hold the name: the step's failure
        does."""
        world.create()
        netbox_guard.forget_created(LIST, "dcim/devices", world.dev["id"])
        assert not netbox_guard.was_created_by_nmas(LIST, "dcim/devices", world.dev["id"])
        world.dev["status"] = {"value": "active", "label": "Active"}
        _dry, out = world.abandon()
        assert _step(out, "netbox")["ok"] is False
        assert _step(out, "identity") == {
            "step": "identity", "ok": False,
            "detail": "not released: the NetBox step did not keep the Planned record as Create "
                      "found it"}
        assert manifest.find_by_name(world.repo, "s5")[0], "the name was released"

    def test_an_unreadable_record_is_a_failed_step(self, world, monkeypatch):
        world.create()
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (False, "NetBox URL and API token are not configured",
                                     None, ""))
        _dry, out = world.abandon()
        nb = _step(out, "netbox")
        assert nb["ok"] is False and "could not be read (NetBox URL and API token" in \
            nb["detail"]
        assert manifest.find_by_name(world.repo, "s5")[0] and world.removals == []


class TestOtherOnboardingsKeepTheRemover:
    """Controls: the kept branch is only for the Planned record Create read."""

    def test_an_entry_with_no_netbox_id_goes_through_the_remover(self, world, monkeypatch):
        monkeypatch.setattr(onboard, "_name_in_netbox", lambda hostname: (False, True))
        monkeypatch.setattr(DE, "read", lambda hostname, **k: DE.NONE)
        world.create(planned=False)
        assert manifest.find_by_name(world.repo, "s5")[1].get("netbox_id") is None, "floor"
        _dry, out = world.abandon()
        assert world.removals and all("netbox_id" not in k for _a, k in world.removals)
        assert _step(out, "netbox") == {"step": "netbox", "ok": False,
                                        "detail": "the remover was called"}

    def test_an_id_verify_wrote_for_a_record_it_made_goes_through_the_remover(self, world,
                                                                              monkeypatch):
        monkeypatch.setattr(onboard, "_name_in_netbox", lambda hostname: (False, True))
        monkeypatch.setattr(DE, "read", lambda hostname, **k: DE.NONE)
        world.create(planned=False)
        identity = manifest.find_by_name(world.repo, "s5")[0]
        manifest.upsert_device(world.repo, identity, "s5", netbox_id=world.dev["id"])
        _dry, out = world.abandon()
        assert world.removals and all(k.get("netbox_id") == world.dev["id"]
                                      for _a, k in world.removals)
        assert _step(out, "netbox")["ok"] is False
