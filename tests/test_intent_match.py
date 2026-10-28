"""C89 (c) and (d): a capture is compared against COMMITTED INTENT.

A capture becomes the golden, so against the golden the comparison is empty
by construction. Against intent it survives: on the host, 8 of 9 devices
matched, and r2 differed by exactly the operator's two lines (measured
2026-09-27). These tests use r2's REAL configuration, committed intent parsed
from it, and the seeded templates, and put the host's exact case through the
deploy plan's own comparison (`build_artifact(...).intent_drift`).
"""

import os
import subprocess

import pytest

from modules.nsot import intent_match as im

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2 = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r2.cfg")


def _broken(text):
    """r2 as the operator left it: OSPFv3 off Gi2, a line the intent lacks."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("interface GigabitEthernet2"):
            inside = True
        elif not line.startswith(" "):
            inside = False
        if inside and line == " ipv6 ospf 1 area 0":
            out.append(" load-interval 30")
            continue
        out.append(line)
    return "\n".join(out) + "\n"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from modules.nsot import hostvars, manifest, templates_repo
    from modules.nsot.parsers import get_parser

    list_dir = tmp_path / "lab"
    repo = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo, "golden"), exist_ok=True)
    os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
    templates_repo.seed_templates(repo)
    manifest.upsert_device(repo, "uid:r2", "r2", "203.0.113.12", platform="cisco_iosxe")
    captured = open(R2, encoding="utf-8").read()
    intent = get_parser("cisco_iosxe").parse(captured)
    secrets = dict(intent.get("secrets") or {})
    hostvars.write_committed(repo, intent)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    # The credential store puts values back at deploy time; here the
    # capture's own parsed values stand in for it (the deploy contract's way).
    monkeypatch.setattr("modules.nsot.hostvars.hydrate_secrets",
                        lambda hv, host, ln="": {**hv, "secrets": dict(secrets)})
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost"}.get(key, default))
    # Committed, not only written: intent is read from HEAD (C104).
    from tests.intent_fixture import commit_intent
    commit_intent(repo)
    return repo, captured


class TestTheComparison:
    def test_the_real_capture_matches_its_intent(self, lab):
        repo, captured = lab
        got = im.intent_match(repo, "Lab", "r2", captured)
        assert got["state"] == "match", got

    def test_the_hosts_exact_case_differs_by_its_two_lines(self, lab):
        repo, captured = lab
        got = im.intent_match(repo, "Lab", "r2", _broken(captured))
        assert got["state"] == "differs"
        assert (got["adds"], got["removes"]) == (1, 1), got
        joined = "\n".join(got["lines"])
        assert "ipv6 ospf 1 area 0" in joined and "load-interval 30" in joined

    # The header r2 printed at 18:53 on the host (its pre-change snapshot),
    # copied verbatim: IOS writes the NVRAM line after every save, so every
    # capture taken after a deploy carries it.
    RAW_HEADER = ("Building configuration...\n\n"
                  "Current configuration : 9029 bytes\n!\n"
                  "! Last configuration change at 18:53:08 UTC Sun Sep 27 2026 by admin\n"
                  "! NVRAM config last updated at 18:53:10 UTC Sun Sep 27 2026 by admin\n!\n")

    def test_a_raw_capture_is_compared_as_it_is_stored(self, lab):
        repo, captured = lab
        result = im.intent_match(repo, "Lab", "r2", self.RAW_HEADER + captured, "cisco_iosxe")
        assert result["state"] == "match", result["lines"]

    def test_the_raw_header_does_not_hide_a_real_departure(self, lab):
        # The operator's break, with the header: the same two lines as
        # without it, and the NVRAM comment is not a third.
        repo, captured = lab
        result = im.intent_match(repo, "Lab", "r2", self.RAW_HEADER + _broken(captured),
                                 "cisco_iosxe")
        assert (result["adds"], result["removes"]) == (1, 1), result["lines"]
        assert not any("NVRAM" in l for l in result["lines"]), result["lines"]

    def test_no_committed_intent_is_unknown_never_a_match(self, lab):
        repo, captured = lab
        got = im.intent_match(repo, "Lab", "r9", captured)
        assert got["state"] == "unknown" and "no committed intent" in got["why"]


class TestTheTrailerAndTheBaseline:
    """Through save_golden, the one place every capture path commits."""

    def _save(self, config, **kw):
        from modules.nsot.repo import GoldenItem, save_golden

        return save_golden("Lab", [GoldenItem("r2", config, "203.0.113.12")],
                           source="save_all", actor="t", inventory_size=1, **kw)

    def _message(self, repo):
        return subprocess.run(["git", "-C", repo, "log", "-1", "--format=%B"],
                              capture_output=True, text=True).stdout

    def test_a_capture_that_departs_is_committed_marked_and_earns_no_baseline(self, lab):
        """(b) refused, (c), (d): recorded, marked, not a baseline."""
        repo, captured = lab
        out = self._save(_broken(captured))
        assert out["ok"] and out["changed"] == ["r2"]
        assert "Intent-Match: no: r2 (+1 -1)" in self._message(repo)
        assert not out["baseline"]
        assert any("r2 does not match its committed intent" in r for r in out["baseline_denied"])

    def test_a_capture_that_matches_says_so_and_earns_the_baseline(self, lab):
        repo, captured = lab
        out = self._save(captured)
        assert "Intent-Match: yes (1 of 1)" in self._message(repo)
        assert out["baseline"].startswith("baseline/") and out["baseline_denied"] == []

    def test_a_device_another_operation_holds_earns_no_baseline_naming_it(self, lab):
        """C2030 (3): a baseline judgement reads committed intent and Mercury's stored
        secrets as of one moment. On 2026-10-28 r3's rotation had stored its new secret and not
        yet committed the intent and golden that render it, and the judgement read r3 as off
        intent. Here r2 is held for a rotation by ANOTHER PROCESS while a Save All judges it:
        the capture is recorded, the baseline is denied naming r2 and its rotation, and the
        decision rides in the commit."""
        pytest.importorskip("fcntl")
        from modules import config
        from tests.test_scheduled_rotation import _held_by_another_process

        repo, captured = lab
        child = _held_by_another_process(config.DATA_DIR, "r2", "rotate",
                                         "rotation@example.invalid", detail="")
        try:
            out = self._save(captured)
        finally:
            child.kill()
            child.wait(5)
        assert not out["baseline"], out
        (why,) = out["baseline_denied"]
        assert why.startswith("r2 is being rotated by rotation@example.invalid, started "), why
        assert why.endswith(f"(process {child.pid}). It may be changing that device's intent "
                            "or Mercury's stored secrets, so this judgement is not of one "
                            "moment; Save All again once it ends"), why
        assert "Baseline: denied: r2 is being rotated by rotation@example.invalid" in \
            self._message(repo)
        again = self._save(captured)
        assert again["baseline"].startswith("baseline/"), "free again: earned"

    def test_holds_that_cannot_be_read_earn_no_baseline_saying_so(self, lab, monkeypatch):
        """Whether a judged device is held elsewhere cannot be told (C988): no baseline, the
        path and its error named."""
        from modules.nsot import device_ops

        def unreadable(*_a, **_k):
            raise device_ops.HoldsUnreadable("/data/device_ops/lab",
                                             PermissionError(13, "Permission denied"))

        monkeypatch.setattr(device_ops, "held_elsewhere", unreadable)
        _repo, captured = lab
        out = self._save(captured)
        assert not out["baseline"]
        assert out["baseline_denied"] == [
            "what is held in Lab could not be read (/data/device_ops/lab: Permission denied), "
            "so whether an operation was changing a judged device's intent or stored secrets "
            "is not known; Save All again"]

    def test_a_device_this_thread_holds_is_judged_as_any_other(self, lab):
        """The judging operation's own hold (a Save holds every device it records until its
        commit) is not another operation: the baseline is earned."""
        from modules.nsot import device_ops

        _repo, captured = lab
        with device_ops.hold("Lab", "r2", "save", "t"):
            out = self._save(captured)
        assert out["baseline"].startswith("baseline/") and out["baseline_denied"] == []

    def test_coverage_is_checked_when_a_save_all_commits(self, lab):
        """C91: a committing Save All with a device skipped took a baseline."""
        repo, captured = lab
        out = self._save(captured, skipped=[{"hostname": "s9", "reason": "offline"}])
        assert not out["baseline"]
        assert any("s9 skipped" in r for r in out["baseline_denied"])


def test_the_trailer_words():
    assert im.trailer({"r1": {"state": "match"}, "r2": {"state": "match"}}) == \
        "Intent-Match: yes (2 of 2)"
    assert im.trailer({"r1": {"state": "match"},
                       "r2": {"state": "differs", "adds": 1, "removes": 1, "reordered": 0},
                       "r9": {"state": "unknown", "why": "no committed intent"}}) == \
        "Intent-Match: no: r2 (+1 -1); r9 (unknown (no committed intent))"
