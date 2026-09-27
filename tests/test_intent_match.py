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
