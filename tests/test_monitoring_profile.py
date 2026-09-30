"""P.9 step (a): the monitoring profile's document and its ONE merge.

The intents are REAL: r2's parsed from its real fleet config by the real
parser, and r6's SNMP skeleton as committed on the host (2026-09-30:
`snmp: {communities: [], hosts: [], settings: []}`). The profile's values are
r2's own, as the fleet agrees on them, so "no fleet device changes" and "r6
inherits" are both measured on the same document.
"""

import copy
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")


def _parsed(host):
    from modules.nsot.parsers.cisco_iosxe import CiscoIosXeParser

    text = open(os.path.join(FLEET, f"{host}.cfg"), encoding="utf-8").read()
    out = CiscoIosXeParser().parse(text)
    out = dict(out.get("host_vars", out))
    # As COMMITTED: names, never values (`write_committed` refuses `secrets:`).
    out["secret_refs"] = sorted((out.pop("secrets", None) or {}).keys())
    return out


R2 = _parsed("r2")
R6_SNMP = {"communities": [], "hosts": [], "settings": []}


def _profile():
    return {"version": 1, "sections": {
        "snmp": {"source": "prometheus", "data": {"snmp": copy.deepcopy(R2["snmp"])}},
        "ntp": {"source": "setting", "data": {"ntp_servers": ["192.0.2.123"]}},
        "telemetry": {"source": "telegraf", "platforms": ["cisco_iosxe"],
                      "data": {"telemetry": copy.deepcopy(R2["telemetry"])}},
        "ip_sla": {"roles": ["router"], "policy": "gateway"},
    }}


def _r6():
    intent = copy.deepcopy(R2)
    intent["hostname"] = "r6"
    intent["snmp"] = copy.deepcopy(R6_SNMP)
    intent["ntp_servers"] = []
    intent["telemetry"] = []
    return intent


class TestTheDocument:
    def test_a_good_profile_has_no_problems(self):
        from modules.nsot import profile as P
        assert P.problems(_profile()) == []

    def test_every_problem_is_named_at_once(self):
        from modules.nsot import profile as P

        bad = {"version": 2, "sections": {"snmp": {"data": {}}, "dns": {"data": {"x": 1}},
                                          "ip_sla": {"policy": "everything", "data": {"ip_sla": []}},
                                          "ntp": {"platforms": "cisco_ios", "data": {"ntp_servers": ["x"]}}}}
        got = P.problems(bad)
        assert any("version is 2" in p for p in got)
        assert "snmp: no data" in got
        assert any("'dns' is not a profile section" in p for p in got)
        assert any("ip_sla.policy must be one of gateway, peers, none" in p for p in got)
        assert any("ip_sla holds a policy, never data" in p for p in got)
        assert "ntp.platforms must be a list of names" in got


class TestTheMerge:
    def test_a_fleet_device_holding_the_profiles_values_is_unchanged(self):
        """The acceptance's first half: nothing a device holds moves."""
        from modules.nsot import profile as P

        intent = copy.deepcopy(R2)
        intent["ntp_servers"] = ["192.0.2.123"]
        assert P.effective(intent, _profile(), "cisco_iosxe", "router") == intent

    def test_r6s_empty_skeleton_inherits_the_profile(self):
        """The second half: an empty value is not a value, so r6 inherits."""
        from modules.nsot import profile as P

        eff = P.effective(_r6(), _profile(), "cisco_iosxe", "router")
        assert eff["snmp"] == R2["snmp"] and eff["ntp_servers"] == ["192.0.2.123"]
        assert eff["telemetry"] == R2["telemetry"] and len(R2["telemetry"]) == 2

    def test_the_device_wins_where_it_holds_a_value_and_it_is_an_override(self):
        from modules.nsot import profile as P

        intent = _r6()
        intent["ntp_servers"] = ["192.0.2.200"]
        eff = P.effective(intent, _profile(), "cisco_iosxe", "router")
        assert eff["ntp_servers"] == ["192.0.2.200"]
        assert P.overrides(intent, _profile(), "cisco_iosxe", "router") == [
            {"section": "ntp", "path": "ntp_servers", "profile": ["192.0.2.123"], "device": ["192.0.2.200"]}]
        assert P.overrides(_r6(), _profile(), "cisco_iosxe", "router") == []

    def test_platforms_and_roles_scope_a_section(self):
        from modules.nsot import profile as P

        on_ios = P.effective(_r6(), _profile(), "cisco_ios", "switch")
        assert on_ios.get("telemetry") in (None, [])                       # IOS-XE only
        assert set(P.sections_for(_profile(), "cisco_iosxe", "router")) == {"snmp", "ntp", "telemetry"}
        assert "ip_sla" not in P.sections_for(_profile(), "cisco_iosxe", "router")   # a policy, never merged

    def test_an_exclusion_with_its_reason_keeps_the_section_out(self):
        from modules.nsot import profile as P

        intent = _r6()
        intent["profile_exclude"] = [{"section": "snmp", "reason": "polled by another collector here"}]
        eff = P.effective(intent, _profile(), "cisco_iosxe", "router")
        assert eff["snmp"] == R6_SNMP
        assert P.excluded(intent) == {"snmp": "polled by another collector here"}

    def test_the_merge_never_changes_its_inputs(self):
        from modules.nsot import profile as P

        doc, intent = _profile(), _r6()
        before = (copy.deepcopy(doc), copy.deepcopy(intent))
        P.effective(intent, doc, "cisco_iosxe", "router")
        assert (doc, intent) == before


class TestOneOwner:
    def test_a_value_equal_to_the_profiles_is_dropped_and_a_different_one_kept(self):
        from modules.nsot import profile as P

        intent = copy.deepcopy(R2)
        intent["ntp_servers"] = ["192.0.2.200"]
        stripped = P.strip_inherited(intent, _profile(), "cisco_iosxe", "router")
        assert stripped["snmp"] == {k: ([] if isinstance(v, list) else v) for k, v in R2["snmp"].items()}
        assert stripped["ntp_servers"] == ["192.0.2.200"]                  # an override stays
        # and the stripped intent still renders to the same effective intent
        assert P.effective(stripped, _profile(), "cisco_iosxe", "router")["snmp"] == R2["snmp"]


class TestTheCommittedDocument:
    def _repo(self, tmp_path):
        import subprocess

        repo = tmp_path / "config_repo"
        repo.mkdir()
        for cmd in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", str(repo), *cmd], check=True)
        (repo / "README").write_text("x\n")
        subprocess.run(["git", "-C", str(repo), "add", "README"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
        return repo

    def _commit(self, repo, text):
        import subprocess

        (repo / "profiles").mkdir(exist_ok=True)
        (repo / "profiles" / "monitoring.yml").write_text(text)
        subprocess.run(["git", "-C", str(repo), "add", "profiles/monitoring.yml"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "profile"], check=True)

    def test_no_profile_is_none(self, tmp_path):
        from modules.nsot import profile as P
        assert P.read_committed(str(self._repo(tmp_path))) is None

    def test_the_committed_profile_is_read_and_a_working_edit_ignored(self, tmp_path):
        import yaml

        from modules.nsot import profile as P

        repo = self._repo(tmp_path)
        self._commit(repo, yaml.safe_dump(_profile()))
        (repo / "profiles" / "monitoring.yml").write_text("version: 1\nsections: {}\n")   # uncommitted
        assert P.read_committed(str(repo)) == _profile()

    def test_a_broken_profile_is_refused_never_read_as_none(self, tmp_path):
        from modules.nsot import profile as P

        repo = self._repo(tmp_path)
        self._commit(repo, "version: 1\nsections: {dns: {data: {x: 1}}}\n")
        with pytest.raises(P.ProfileRefused, match="'dns' is not a profile section"):
            P.read_committed(str(repo))


class TestTheProfilesSecret:
    def test_the_profiles_refs_join_the_devices_so_hydration_asks_for_them(self):
        from modules.nsot import profile as P

        intent = _r6()
        intent["secret_refs"] = ["user_admin_secret"]
        eff = P.effective(intent, _profile(), "cisco_iosxe", "router")
        assert eff["secret_refs"] == ["snmp_community_ro", "user_admin_secret"]

    def test_the_device_value_wins_then_the_networks(self, monkeypatch):
        from modules import credentials
        from modules.nsot import hostvars

        store = {credentials.profile_secret_key("Default", "snmp_community_ro"): "network-value-1",
                 credentials.template_secret_key("Default", "r2", "snmp_community_ro"): "r2-override-1"}
        monkeypatch.setattr(credentials, "get_template_secret", lambda k: store.get(k, ""))
        refs = {"secret_refs": ["snmp_community_ro"]}
        assert hostvars.hydrate_secrets(refs, "r6", "Default")["secrets"] == {"snmp_community_ro": "network-value-1"}
        assert hostvars.hydrate_secrets(refs, "r2", "Default")["secrets"] == {"snmp_community_ro": "r2-override-1"}
        assert credentials.profile_secret_key("Default", "snmp_community_ro").endswith(":@profile:snmp_community_ro")
