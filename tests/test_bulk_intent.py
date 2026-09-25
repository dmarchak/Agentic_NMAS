"""NSOT_PLAN P.1b: one structured change to N devices' intent, ONE commit.

Real fleet intent (the parsers over the fleet fixtures, in the OLD logging
shape the committed intent has), a real config repo, and the P.1 move as the
change. The render is the real template render with a stub secret lookup.
"""

import copy
import os

import pytest

from modules.nsot import bulk_intent as BI
from modules.nsot import roundtrip
from modules.nsot.parsers import get_parser

FLEET = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")
OLD_SETTINGS = ["trap critical", "origin-id hostname",
                "source-interface Loopback0"]
BLOCK = {"trap": "notifications", "origin_id": "hostname",
         "source_interface": "Loopback0", "hosts": ["10.255.1.10"],
         "heartbeat": 300}
P1_MOVE = [
    {"path": ["logging", "settings"], "before": OLD_SETTINGS, "after": []},
    {"path": ["logging", "hosts"], "before": ["10.255.1.10"], "after": []},
    {"path": ["logging", "syslog"], "before": BI.ABSENT, "after": BLOCK},
]


def _platform(name):
    return "cisco_iosxe" if name.startswith("r") else "cisco_ios"


def _old_shape_intent(name):
    """What the committed intent looks like today: parsed, then the syslog
    block folded back into settings/hosts (the pre-P.1 shape)."""
    with open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8") as fh:
        hv = get_parser(_platform(name)).parse(fh.read())
    hv["logging"].pop("syslog", None)
    hv["logging"]["settings"] = list(OLD_SETTINGS)
    hv["logging"]["hosts"] = ["10.255.1.10"]
    hv.pop("secrets", None)
    return hv


def _render(host, hv):
    text = roundtrip.render(hv, _platform(host), secret_lookup=lambda r: "x")
    return text, True, []


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from modules.nsot import hostvars, repo as R
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost",
                            "nsot_device_tag_retention": 50,
                        }.get(key, default))
    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda c: None)
    repo = str(list_dir / "config_repo")
    R.init_repo(repo)
    for name in ("s1", "s2", "r1", "r3"):
        hostvars.write_committed(repo, _old_shape_intent(name))
    R.save_host_vars("Lab", ["s1", "s2", "r1", "r3"], message="host_vars: seed")
    return repo, hostvars, R


def _plan(repo, devices, steps=P1_MOVE, render=_render):
    return BI.plan(repo, devices, steps, render=render, summary="syslog block")


class TestTheHeadlineIsTheClaim:
    def test_the_p1_move_is_one_group_across_both_platforms(self, lab):
        repo, _hv, _R = lab
        r = _plan(repo, ["s1", "s2", "r1", "r3"])
        assert r["ok"] and r["refused"] == []
        assert r["headline"] == "4 device(s), 1 group(s)"
        g = r["groups"][0]
        assert "logging trap notifications" in g["added"]
        assert "logging trap critical" in g["removed"]
        assert "event manager applet NMAS-HEARTBEAT" in g["added"]

    def test_a_divergent_render_is_a_second_group_in_the_headline(self, lab):
        """Same change, one device renders it differently: 2 groups, and the
        headline says so rather than a detail below it."""
        repo, _hv, _R = lab

        def odd(host, hv):
            text, d, r = _render(host, hv)
            if host == "r3" and (hv["logging"].get("syslog")):
                text += "\nlogging buffered 8192\n"
            return text, d, r
        r = _plan(repo, ["s1", "s2", "r1", "r3"], render=odd)
        assert r["headline"] == "4 device(s), 2 group(s)"
        assert [g["devices"] for g in r["groups"]] == [["r1", "s1", "s2"], ["r3"]]


class TestRefusals:
    def test_a_drifted_before_state_is_refused_with_both_operands(self, lab):
        repo, hostvars, R = lab
        doc = hostvars.read_committed(repo, "s2")
        doc["logging"]["settings"] = ["trap errors", "origin-id hostname",
                                      "source-interface Loopback0"]
        hostvars.write_committed(repo, doc)
        R.save_host_vars("Lab", ["s2"], message="host_vars: s2 drift")
        r = _plan(repo, ["s1", "s2", "r1"])
        assert [x["device"] for x in r["refused"]] == ["s2"]
        mm = r["refused"][0]["mismatched"][0]
        assert mm["path"] == "logging.settings"
        assert mm["expected"] == OLD_SETTINGS and mm["has"][0] == "trap errors"
        assert r["headline"] == "2 device(s), 1 group(s), 1 refused"

    def test_an_empty_logging_block_like_r6s_is_refused(self, lab):
        repo, hostvars, R = lab
        doc = hostvars.read_committed(repo, "r3")
        doc["logging"] = {"hosts": [], "settings": []}
        hostvars.write_committed(repo, doc)
        R.save_host_vars("Lab", ["r3"], message="host_vars: r3 like r6")
        r = _plan(repo, ["r1", "r3"])
        assert [x["device"] for x in r["refused"]] == ["r3"]

    def test_a_key_the_change_does_not_name_is_irrelevant(self, lab):
        """`console` exists on the switches and not on the routers; the
        change does not mention it, so it neither refuses nor moves."""
        repo, hostvars, R = lab
        # Floors: the case exists in the fixtures, in both directions.
        assert "console" in hostvars.read_committed(repo, "s1")["logging"]
        assert "console" not in hostvars.read_committed(repo, "r1")["logging"]
        r = _plan(repo, ["s1", "r1"])
        assert not r["refused"] and len(r["accepted"]) == 2
        assert BI.apply("Lab", repo, ["s1", "r1"], P1_MOVE, r["hash"],
                        render=_render, summary="x", actor="t")["ok"]
        assert "console" in hostvars.read_committed(repo, "s1")["logging"]
        assert "console" not in hostvars.read_committed(repo, "r1")["logging"]

    def test_an_unknown_path_refuses_the_whole_change(self, lab):
        repo, _hv, _R = lab
        r = _plan(repo, ["s1"], steps=[{"path": ["loging", "settings"],
                                        "before": [], "after": []}])
        assert r["ok"] is False and "loging.settings" in r["error"]
        assert r["accepted"] == [] and r["refused"] == []

    def test_a_hand_formatted_file_is_refused_not_reformatted(self, lab):
        repo, hostvars, _R = lab
        path = hostvars.committed_path(repo, "s1")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("# a note somebody left\n")
        r = _plan(repo, ["s1", "s2"])
        assert [x["device"] for x in r["refused"]] == ["s1"]
        assert "hand-formatted" in r["refused"][0]["reason"]
        assert r["refused"][0]["mismatched"] == [], "its before-state matched"

    def test_every_reason_is_reported_not_the_first(self, lab):
        """Measured on the live repo: r6 was refused as hand-formatted and
        its empty logging went unreported."""
        repo, hostvars, R = lab
        doc = hostvars.read_committed(repo, "r3")
        doc["logging"] = {"hosts": [], "settings": []}
        hostvars.write_committed(repo, doc)
        with open(hostvars.committed_path(repo, "r3"), "a") as fh:
            fh.write("# hand-written\n")
        R.save_host_vars("Lab", ["r3"], message="host_vars: r3 like r6")
        refused = _plan(repo, ["r3"])["refused"][0]
        assert "hand-formatted" in refused["reason"]
        assert "not what the change expects" in refused["reason"]
        assert {m["path"] for m in refused["mismatched"]} == {
            "logging.settings", "logging.hosts"}

    def test_a_result_the_gate_refuses_is_refused(self, lab):
        repo, _hv, _R = lab
        partial = copy.deepcopy(P1_MOVE)
        partial[2]["after"] = {**BLOCK, "heartbeat": 0}
        r = _plan(repo, ["s1"], steps=partial)
        assert r["refused"] and "heartbeat" in r["refused"][0]["reason"]

    def test_eligibility_refuses_by_name(self, lab):
        repo, _hv, _R = lab
        r = BI.plan(repo, ["s1", "gone"], P1_MOVE, render=_render,
                    eligible=lambda h: "not in inventory" if h == "gone" else "")
        assert [x["device"] for x in r["refused"]] == ["gone"]


class TestApplyIsOneShotAndOneCommit:
    def test_one_commit_names_the_devices_and_the_refused(self, lab):
        repo, hostvars, R = lab
        doc = hostvars.read_committed(repo, "r3")
        doc["logging"] = {"hosts": [], "settings": []}
        hostvars.write_committed(repo, doc)
        R.save_host_vars("Lab", ["r3"], message="host_vars: r3 like r6")
        before = R.git(repo, "rev-list", "--count", "HEAD")[1]
        preview = _plan(repo, ["s1", "s2", "r1", "r3"])
        out = BI.apply("Lab", repo, ["s1", "s2", "r1", "r3"], P1_MOVE,
                       preview["hash"], render=_render,
                       summary="syslog block (P.1)", actor="t@example.com")
        assert out["ok"], out
        assert int(R.git(repo, "rev-list", "--count", "HEAD")[1]) == int(before) + 1
        _rc, body, _e = R.git(repo, "log", "-1", "--format=%s%n%b")
        assert "3 device(s), 1 group(s)" in body
        assert "Devices: r1,s1,s2" in body and "Refused: r3" in body
        _rc, files, _e = R.git(repo, "show", "--name-only", "--format=", "HEAD")
        assert sorted(files.split()) == ["host_vars/r1.yml", "host_vars/s1.yml",
                                         "host_vars/s2.yml"]
        assert hostvars.read_committed(repo, "s1")["logging"]["syslog"] == BLOCK

    def test_a_file_that_moved_since_the_preview_refuses_everything(self, lab):
        repo, hostvars, R = lab
        preview = _plan(repo, ["s1", "s2"])
        doc = hostvars.read_committed(repo, "s2")
        doc["ntp_servers"] = ["192.0.2.1"]
        hostvars.write_committed(repo, doc)
        R.save_host_vars("Lab", ["s2"], message="host_vars: s2 ntp")
        out = BI.apply("Lab", repo, ["s1", "s2"], P1_MOVE, preview["hash"],
                       render=_render, summary="x", actor="t")
        assert out["ok"] is False and "changed since you previewed" in out["error"]
        assert "syslog" not in hostvars.read_committed(repo, "s1")["logging"] \
            or not hostvars.read_committed(repo, "s1")["logging"]["syslog"]

    def test_uncommitted_intent_would_ride_along_so_it_refuses(self, lab):
        repo, hostvars, _R = lab
        preview = _plan(repo, ["s1"])
        with open(hostvars.committed_path(repo, "r3"), "a") as fh:
            fh.write("mtu: 9000\n")
        out = BI.apply("Lab", repo, ["s1"], P1_MOVE, preview["hash"],
                       render=_render, summary="x", actor="t")
        assert out["ok"] is False and "uncommitted" in out["error"]

    def test_one_device_reverts_alone_from_the_shared_commit(self, lab):
        """The CLAUDE.md correction, pinned: revert reads and writes only the
        device's own file, so a shared commit does not couple devices."""
        repo, hostvars, R = lab
        preview = _plan(repo, ["s1", "s2"])
        assert BI.apply("Lab", repo, ["s1", "s2"], P1_MOVE, preview["hash"],
                        render=_render, summary="syslog block",
                        actor="t")["ok"]
        out = hostvars.revert_intent_change(repo, "s1")
        assert out["ok"], out
        assert hostvars.read_committed(repo, "s1")["logging"]["settings"] == OLD_SETTINGS
        assert hostvars.read_committed(repo, "s2")["logging"]["syslog"] == BLOCK


class TestTheRoutes:
    def test_the_list_is_carried_never_inferred(self):
        import app as nmas
        r = nmas.app.test_client().post("/templatize/bulk/preview", json={
            "devices": ["s1"], "steps": P1_MOVE})
        assert r.status_code == 400 and "list_name is required" in r.get_json()["error"]

    def test_an_unknown_list_is_refused_and_not_created(self, tmp_path,
                                                        monkeypatch):
        import app as nmas
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        r = nmas.app.test_client().post("/templatize/bulk/preview", json={
            "list_name": "Nope", "devices": ["s1"], "steps": P1_MOVE})
        assert r.status_code == 400 and "no device list named" in r.get_json()["error"]
        # The registry seeds its own `default` list on first read (pre-
        # existing behaviour); what must not exist is the MISTYPED one.
        assert not any(n.lower() == "nope" for n in os.listdir(tmp_path))

    def test_the_shipped_p1_change_file_is_the_tested_change(self):
        """The file an operator runs is the change these tests prove."""
        import json
        with open("deploy/intent-changes/p1-syslog-block.json") as fh:
            shipped = json.load(fh)["steps"]
        assert [{"path": s["path"], "before": s["before"], "after": s["after"]}
                for s in shipped] == P1_MOVE
