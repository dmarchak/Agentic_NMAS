"""History draws every reveal the reveal record holds (C837; the operator, 2026-10-15): one
source, `history_sources.reveals` (C818's `log_reveals`, extended), filed under the one kind
filter ``reveals``.

On test_capture's lab (r2's REAL configuration committed as its golden), each reveal is made
by its own writer: the golden version on v2, the golden version and diff behind ``?reveal=1``,
the bootstrap config on v2 (its render stood in; the record is the route's), the ZTP
responder's served config (`ztp_responder.record`), and a log line's record in the shape
`log_reveal.reveal` writes (its own route is driven in tests/test_log_reveal.py). Then:

- each is a row: who, when, which object (the device, the commit, the line), the reason where
  the kind records one, and how the person was identified; never the value;
- a record carrying value-like fields (a planted value under `config`, `text`, `value`,
  `secret`, `password`, `line`) never draws one, and an unknown kind is still drawn;
- another network's reveal is not drawn; one that names no network is drawn by its device's
  name, and says so; the kinds left to another source (`REVEALS_ELSEWHERE`) are not drawn.
"""

import json
import subprocess
from types import SimpleNamespace

import pytest

from tests.test_device_capture_v2 import lab  # noqa: F401 (the fixture)

PLANTED = "Pl4ntedRev3alValue"
WHO = "test-person@example.invalid"


@pytest.fixture
def audit(tmp_path, monkeypatch):
    from modules import reveal_audit
    where = tmp_path / "reveal_audit.jsonl"
    monkeypatch.setattr(reveal_audit, "_path", lambda: str(where))
    return where


def _ctx(device="", members=None, name="Lab"):
    return {"ref": SimpleNamespace(name=name), "device": device, "limit": 50, "since": None,
            "members": members}


def _head(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def every_kind(lab, audit, monkeypatch):  # noqa: F811
    """One reveal of every kind, each by its writer."""
    from modules import reveal_audit
    from modules.nsot import ztp_responder
    c, sha = lab["client"], _head(lab["repo"])
    assert c.post("/v2/device/r2/golden/reveal", data={"ref": sha}).status_code == 200
    assert c.get(f"/golden/version/r2?reveal=1&list_name=Lab&ref={sha}").status_code == 200
    assert c.get(f"/golden/diff/r2?reveal=1&list_name=Lab&a={sha}&b={sha}").status_code == 200
    monkeypatch.setattr("modules.nsot.onboard.bootstrap_artifact", lambda repo_dir, host: {
        "ok": True, "hostname": host, "config": f"hostname {host}\nsecret 0 {PLANTED}\nend\n"})
    assert c.post("/v2/onboard/r2/bootstrap", data={"list_name": "Lab"}).status_code == 200
    assert ztp_responder.record("192.0.2.40", "r2-confg", {
        "serve": True, "device": "r2", "list": "Lab",
        "config": f"secret 0 {PLANTED}\n".encode()})["recorded"]
    # log_reveal.reveal's record, its fields as it writes them (masked reason, no line).
    stream = {"device": "r2", "job": "network_syslog"}
    assert reveal_audit.record(
        actor=WHO, kind="person", what="log_line", target="r2",
        detail=f"{json.dumps(stream, sort_keys=True)} at 1760000000000000001", peer="192.0.2.5",
        extra={"list": "Lab", "stream": stream, "ns": "1760000000000000001",
               "line_at": "2025-10-09T08:53:20.000000001Z", "shown_sha256": "a" * 64,
               "reason": "check the community this change set"})["recorded"]
    rows = reveal_audit.read()["rows"]
    assert PLANTED not in json.dumps(rows), "a writer put the value in the record"
    return rows


class TestEveryKindIsARow:
    def test_who_when_which_and_the_reason_never_the_value(self, every_kind, lab):  # noqa: F811
        from modules import history_sources as HS
        got = HS.reveals(_ctx())
        assert got["errors"] == []
        whats = [e["what"] for e in got["events"]]
        sha = _head(lab["repo"])
        assert whats == [
            "Log line revealed: r2 at 2025-10-09 08:53:20 UTC",
            "Bootstrap config served to r2 over TFTP",
            "Bootstrap config revealed: r2",
            f"Golden diff revealed: r2, {sha}..{sha}",
            f"Golden config revealed: r2 at {sha[:10]}",
            f"Golden config revealed: r2 at {sha[:10]}"], whats
        for e in got["events"]:
            assert e["kind"] == "reveal" and e["devices"] == ["r2"], e
            assert e["at"].startswith("20") and e["who"], e
        by = {e["what"]: e for e in got["events"]}
        log_line = by["Log line revealed: r2 at 2025-10-09 08:53:20 UTC"]
        assert log_line["detail"] == "check the community this change set"
        assert dict(log_line["record"])["Reason"] == "check the community this change set"
        assert 'job="network_syslog"' in dict(log_line["record"])["Line"]
        golden = got["events"][-1]
        assert golden["who"] == WHO and dict(golden["record"])["Version"] == sha
        assert dict(golden["record"])["Verified"] == "person"
        served = by["Bootstrap config served to r2 over TFTP"]
        assert served["who"] == "ztp:192.0.2.40" and "sha256 " in dict(served["record"])[
            "What was served"]
        assert PLANTED not in json.dumps(got)

    def test_the_one_timeline_files_them_under_reveals(self, every_kind, audit):
        from modules import history_sources as HS
        ref = SimpleNamespace(name="Lab", repo_dir=str(audit.parent),
                              data_dir=str(audit.parent))
        got = HS.timeline(ref, kinds=["reveals"])
        assert [e["kind"] for e in got["events"]] == ["reveal"] * 6
        assert "reveal" in HS.KIND_FILTERS["reveals"]

    def test_another_network_s_are_not_drawn_and_a_device_tab_draws_its_own(self, every_kind):
        from modules import history_sources as HS
        assert HS.reveals(_ctx(name="Other"))["events"] == []
        assert HS.reveals(_ctx(device="r1"))["events"] == []
        assert len(HS.reveals(_ctx(device="r2"))["events"]) == 6


class TestNothingButNamedFields:
    def test_a_value_like_field_is_never_drawn_and_an_unknown_kind_is(self, audit):
        from modules import history_sources as HS, reveal_audit
        assert reveal_audit.record(
            actor=WHO, kind="person", what="something_new", target="r2", detail="d",
            extra={"list": "Lab", "config": PLANTED, "text": PLANTED, "value": PLANTED,
                   "secret": PLANTED, "password": PLANTED, "line": PLANTED})["recorded"]
        got = HS.reveals(_ctx())
        assert [e["what"] for e in got["events"]] == ["Something new revealed: r2"]
        assert PLANTED not in json.dumps(got), "a value-like field was drawn"

    def test_a_secret_shaped_target_or_reason_is_masked_on_the_way_out(self, audit):
        from modules import history_sources as HS, reveal_audit
        assert reveal_audit.record(
            actor=WHO, kind="person", what="golden_config", target="r2",
            detail=f"snmp-server community {PLANTED} RO",
            extra={"list": "Lab", "reason": f"username x password 0 {PLANTED}"})["recorded"]
        assert PLANTED not in json.dumps(HS.reveals(_ctx()))


class TestNetworksAndOtherSources:
    def test_a_record_naming_no_network_is_drawn_by_its_device_and_says_so(self, audit):
        from modules import history_sources as HS, reveal_audit
        # The shape every golden reveal had before C837 named the network.
        reveal_audit.record(actor=WHO, kind="person", what="golden_config", target="r2",
                            detail="0123456789abcdef", peer="192.0.2.5")
        mine = HS.reveals(_ctx(members={"r2"}))["events"]
        assert [e["what"] for e in mine] == ["Golden config revealed: r2 at 0123456789"]
        assert dict(mine[0]["record"])["Network"].startswith("not recorded")
        assert HS.reveals(_ctx(members={"r1"}))["events"] == [], \
            "a device of no network of this list was drawn by a guess"

    def test_the_kinds_left_elsewhere_are_not_drawn(self, audit):
        from modules import history_sources as HS, reveal_audit
        for what in HS.REVEALS_ELSEWHERE:
            reveal_audit.record(actor=WHO, kind="person", what=what, target="r2",
                                detail="list=Lab", extra={"list": "Lab"})
        assert HS.reveals(_ctx())["events"] == []

    def test_an_unreadable_record_is_said(self, audit):
        from modules import history_sources as HS
        audit.mkdir()
        got = HS.reveals(_ctx())
        assert got["events"] == [] and got["errors"][0].startswith(
            "the reveal record could not be read:")
