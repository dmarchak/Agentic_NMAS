"""C1644: what `onboard.commit_step` (Create's one commit) writes, field by field.

Mutation run #41 mutated the function whole for the first time and left 43 open VERDICT
survivors, none of them the code wrong: nothing pinned which list the commit lands in, the
commit's subject, `Actor:` and `Source:`, the minted identity's record, the manifest entry's MAC,
reservation and role, the bootstrap record's `mac` and `platform_mgmt_interface`, a failed
commit's reason, or the return when the commit names no sha. Each is pinned here through the
real function, on a real repository (`tests/test_onboard_plan.py`'s `lab`), with a plan built
by `build_plan` itself.
"""

import logging
import os

import pytest

from modules.nsot import onboard
from tests.test_onboard_plan import lab  # noqa: F401 - the fixture

ACTOR = "t@example.com"
MAC = "aa:bb:cc:00:02:40"
RESERVED = "192.0.2.40"


class _Kea:
    @staticmethod
    def reservation_for(_mac):
        return {"state": "reserved", "address": RESERVED, "source": "config", "error": ""}


def _dhcp_plan(**over):
    """A DHCP plan: a MAC, its Kea reservation and a role, the three the manifest records."""
    args = dict(hostname="bp-dhcp-a", platform="cisco_iosxe", list_name="probe", secret="S",
                manager_interface="Gi2", mgmt_interface="Gi1", kea=_Kea(), role="router",
                address_source="dhcp", mgmt_mac=MAC)
    args.update(over)
    return onboard.build_plan(**args)


@pytest.fixture
def strict_lists(lab, monkeypatch):  # noqa: F811 - the fixture
    """The `lab` list, found ONLY by its own name: any other name (None among them) is refused,
    so a commit that asked for another list's folder fails instead of landing in this one."""
    from modules.config import get_list_data_dir
    here = get_list_data_dir("probe")

    def by_name(name):
        if name != "probe":
            raise KeyError(f"no list {name!r}")
        return here

    monkeypatch.setattr("modules.config.get_list_data_dir", by_name)
    monkeypatch.setattr("modules.config.list_data_path", by_name)
    return os.path.join(here, "config_repo")


def test_the_commit_lands_in_the_plan_s_own_list_and_names_who_why_and_where(strict_lists):
    from modules.nsot import repo as R
    plan = _dhcp_plan()
    sha = onboard.commit_step(plan, actor=ACTOR)
    assert sha and R.git(strict_lists, "rev-parse", "HEAD")[1].strip().startswith(sha[:7])
    body = R.git(strict_lists, "log", "-1", "--format=%B")[1]
    lines = body.splitlines()
    assert lines[0] == "onboarding: bp-dhcp-a", body
    assert f"Actor: {ACTOR}" in lines, body
    assert "Source: onboarding" in lines, body


def test_the_manifest_entry_carries_the_mac_the_reservation_and_the_role(strict_lists):
    from modules.nsot import manifest
    plan = _dhcp_plan()
    assert (plan.mgmt_mac, plan.reservation_address, plan.role) == (MAC, RESERVED, "router"), \
        "floor: the plan carries all three"
    onboard.commit_step(plan, actor=ACTOR)
    entry = manifest.find_by_name(strict_lists, "bp-dhcp-a")[1]
    assert (entry["mgmt_mac"], entry["reserved_address"], entry["role"]) == (
        MAC, RESERVED, "router"), entry
    assert entry["address_source"] == "dhcp" and entry["verified_at"] is None


def test_the_bootstrap_record_carries_the_mac_and_the_platform_s_interface(strict_lists):
    from modules.nsot import hostvars
    plan = _dhcp_plan()
    assert plan.platform_mgmt_interface, "floor: the plan names the platform's interface"
    onboard.commit_step(plan, actor=ACTOR)
    boot = hostvars.read_committed(strict_lists, "bp-dhcp-a")["bootstrap"]
    assert boot["mac"] == MAC, boot
    assert boot["platform_mgmt_interface"] == plan.platform_mgmt_interface, boot
    assert "gateway_route" not in boot, "a new record routes by the key's absence (C1606)"


def test_the_minted_identity_is_logged_with_the_device_s_name_and_address(strict_lists,
                                                                         caplog):
    """The one place an identity is minted says which device and address it minted it for
    (`repo.adopt_identity`'s record), the identity the manifest then holds."""
    from modules.nsot import manifest
    plan = _dhcp_plan(address_source="static", mgmt_mac="", mgmt_ip="192.0.2.31",
                      mgmt_mask="255.255.255.0")
    assert plan.mgmt_ip == "192.0.2.31", "floor"
    with caplog.at_level(logging.INFO, logger="modules.nsot.repo"):
        onboard.commit_step(plan, actor=ACTOR)
    identity = manifest.find_by_name(strict_lists, "bp-dhcp-a")[0]
    assert identity, "floor: the identity was recorded"
    said = [r.getMessage() for r in caplog.records if r.name == "modules.nsot.repo"
            and "adopting" in r.getMessage()]
    assert said == [f"repo: adopting bp-dhcp-a (192.0.2.31) as {identity}"], said


@pytest.mark.parametrize("answer,reason", [
    ({"ok": False, "error": "the repository's lock is held by another process"},
     "the repository's lock is held by another process"),
    ({"ok": False}, "the commit did not succeed"),
    ({"ok": False, "error": ""}, "the commit did not succeed"),
], ids=["its-own-reason", "no-reason", "an-empty-reason"])
def test_a_failed_commit_raises_with_the_commit_s_own_reason(strict_lists, monkeypatch, answer,
                                                            reason):
    monkeypatch.setattr("modules.nsot.repo.save_host_vars", lambda *a, **k: dict(answer))
    with pytest.raises(RuntimeError) as got:
        onboard.commit_step(_dhcp_plan(), actor=ACTOR)
    assert str(got.value) == reason


def test_a_commit_that_names_no_sha_returns_an_empty_one(strict_lists, monkeypatch):
    monkeypatch.setattr("modules.nsot.repo.save_host_vars", lambda *a, **k: {"ok": True})
    got = onboard.commit_step(_dhcp_plan(), actor=ACTOR)
    assert got == "" and isinstance(got, str)
