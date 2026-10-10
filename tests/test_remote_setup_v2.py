"""History › Remote set-up on v2 (C631, 2026-10-10): connecting a network's existing remote, the
write probe, what a first push would publish and its typed acknowledgement, and automatic
pushing, through the real app on a temporary store (tests/test_settings_v2's `networks`).

The acts are `modules/nsot/remote.py`'s own (adopt, verify, first_push_preview, acknowledge,
enable_auto_push). What reaches GitHub is replaced at its edge: `remote.verify`'s checks and the
history scan's result, shaped as the module tests shape them; nothing here leaves the host.
"""

import json
import re

import pytest

from modules.nsot import remote as R
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

BASE = "/v2/history/remote/setup"
FP = "fp-0123456789ab"


def _post(n, path, data):
    r = n["client"].post(path, data=data, headers={"HX-Request": "true"})
    return r, re.sub(r"\s+", " ", r.get_data(as_text=True))


def _get(n, path):
    r = n["client"].get(path)
    return r, re.sub(r"\s+", " ", r.get_data(as_text=True))


GOOD = {"list": "Branch", "ssh_alias": "github-branch", "owner": "acct",
        "repo": "branch-config", "branch": "main", "key_path": "~/.ssh/branch_deploy"}


def _connected(n):
    r, html = _post(n, f"{BASE}/connect", GOOD)
    assert r.status_code == 200 and "Connected:" in html, html
    return html


@pytest.fixture
def scan(monkeypatch):
    """The history scan's result as `scan_history_secrets` returns it: one live community
    on two devices, one hash (never gated); and git's counts."""
    got = {"rows": [{"device": "r1", "kind": "snmp_community", "recoverable": True,
                     "distinct": 1, "live": 2, "dead": 0},
                    {"device": "r1", "kind": "secret_hash", "recoverable": False,
                     "distinct": 3, "live": 3, "dead": 0}],
           "blobs_scanned": 4, "gated_kinds": ["snmp_community"],
           "live_values": [{"kind": "snmp_community", "fingerprint": FP, "recoverable": True,
                            "devices": ["r1", "r2"], "at_head": ["r1"]}]}
    monkeypatch.setattr(R, "scan_history_secrets", lambda *a, **k: got)
    monkeypatch.setattr(R, "_blobs_of_golden", lambda *a, **k: {})
    monkeypatch.setattr(R, "snmp_access_modes", lambda *a, **k: {})
    monkeypatch.setattr(R, "_run", lambda *a, **k: type(
        "P", (), {"stdout": "7\n", "stderr": "", "returncode": 0})())
    return got


class TestTheCard:
    def test_history_s_header_opens_it_and_with_no_remote_it_is_the_connect_form(self, networks):
        from modules.nsot import listref

        _r, page = _get(networks, "/v2/history")
        assert "Set up the remote…" in page and 'id="remote-setup"' in page
        r, card = _get(networks, f"{BASE}?list=Branch")
        assert r.status_code == 200 and "Remote set-up" in card and "Connect" in card
        assert "never edits the host's SSH configuration" in card
        for words in (w for _s, w in R.SETUP_SHAPES.values()):
            assert words.replace("'", "&#39;") in card
        assert listref.exists("Branch")

    def test_an_unknown_network_is_refused_by_name_before_anything_resolves(self, networks):
        """The list guard (C51) answers it, before the route: nothing read, nothing made."""
        r, html = _get(networks, f"{BASE}?list=Nowhere")
        assert r.status_code == 404 and "There is no device list named 'Nowhere'" in html
        assert r.headers["Content-Type"].startswith("application/json")
        assert not (networks["dir"] / "lists" / "nowhere").exists()


class TestConnect:
    def test_a_good_remote_is_recorded_and_its_facts_drawn(self, networks):
        html = _connected(networks)
        assert "acct/branch-config · main" in html and "github-branch" in html
        assert "never passed" in html and "Push refuses until it has" in html
        saved = json.loads((networks["dir"] / "lists" / "branch" / "remote.json").read_text())
        assert saved["owner"] == "acct" and saved["managed_by_nmas"] is False

    def test_an_alias_read_as_an_ssh_option_is_refused_and_nothing_written(self, networks):
        r, html = _post(networks, f"{BASE}/connect", dict(GOOD, ssh_alias="-oProxyCommand=x"))
        assert r.status_code == 409 and "Not done:" in html and "ssh alias" in html
        assert not (networks["dir"] / "lists" / "branch" / "remote.json").exists()

    def test_a_second_connect_is_refused(self, networks):
        _connected(networks)
        r, html = _post(networks, f"{BASE}/connect", GOOD)
        assert r.status_code == 409 and "already has a remote" in html

    def test_a_form_without_a_network_is_refused_its_name_escaped(self, networks):
        r, html = _post(networks, f"{BASE}/connect", dict(GOOD, list="Nowhere<b>x</b>"))
        assert r.status_code == 404 and "there is no network" in html
        assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html


class TestTheWriteProbe:
    def test_each_check_is_drawn_masked(self, networks, monkeypatch):
        _connected(networks)
        monkeypatch.setattr(R, "verify", lambda name, **kw: {"ok": False, "checks": [
            {"name": "key_scope", "ok": True, "detail": "Hi acct/branch-config!"},
            {"name": "write_probe", "ok": False,
             "detail": "snmp-server community Sup3rS3cretCommunity RO refused"}]})
        _r, html = _post(networks, f"{BASE}/write-probe", {"list": "Branch"})
        assert "The write probe FAILED" in html and "key_scope" in html and "FAILS" in html
        assert "Sup3rS3cretCommunity" not in html


class TestPublication:
    def test_it_draws_counts_and_fingerprints_never_a_value(self, networks, scan):
        _connected(networks)
        _r, html = _post(networks, f"{BASE}/publication", {"list": "Branch"})
        assert "A first push to acct/branch-config (main) would publish" in html
        assert f'<td class="mono">{FP}</td>' in html and "r1, r2" in html
        assert "exactly: snmp_community" in html
        assert f'name="shown" value="{FP}"' in html
        assert "secret_hash 3" in html, "a hash is counted, never gated"

    def test_the_wrong_words_are_refused_naming_both(self, networks, scan):
        _connected(networks)
        r, html = _post(networks, f"{BASE}/acknowledge",
                        {"list": "Branch", "typed": "yes", "shown": FP})
        assert r.status_code == 409 and "&#39;yes&#39;" in html and "&#39;snmp_community&#39;" in html
        assert R.load_remote("Branch").get("acknowledged_secrets") is None

    def test_the_right_words_record_what_was_shown(self, networks, scan):
        _connected(networks)
        r, html = _post(networks, f"{BASE}/acknowledge",
                        {"list": "Branch", "typed": "snmp_community", "shown": FP})
        assert r.status_code == 200 and "Acknowledged:" in html, html
        ack = R.load_remote("Branch")["acknowledged_secrets"]
        assert ack["kinds"] == ["snmp_community"] and FP in ack["values"]

    def test_a_value_not_shown_is_refused(self, networks, scan):
        _connected(networks)
        r, html = _post(networks, f"{BASE}/acknowledge",
                        {"list": "Branch", "typed": "snmp_community", "shown": "fp-other"})
        assert r.status_code == 409 and "changed after the card was drawn" in html
        assert R.load_remote("Branch").get("acknowledged_secrets") is None


class TestAutoPush:
    def test_it_is_offered_only_after_a_push_and_then_turns_on(self, networks):
        html = _connected(networks)
        assert "Turn on automatic pushing" not in html
        r, html = _post(networks, f"{BASE}/auto-push", {"list": "Branch"})
        assert r.status_code == 409 and "only after a successful push" in html
        R.update_remote("Branch", lambda c: c.__setitem__(
            "last_push", {"at": "2026-10-10T03:00:00Z", "by": "test-person@example.invalid"}))
        _r, card = _get(networks, f"{BASE}?list=Branch")
        assert "Turn on automatic pushing" in card
        r, html = _post(networks, f"{BASE}/auto-push", {"list": "Branch"})
        assert r.status_code == 200 and "Automatic pushing is on" in html
        assert R.load_remote("Branch")["auto_push"] is True


def test_history_s_header_names_uncommitted_paths_never_today_s_git_tab(networks):
    """C637: the header said "see today's Git tab"; it names the paths itself."""
    from modules.nsot import listref

    from routes.v2 import _history_remote

    ref = listref.resolve("Default")
    import os
    import subprocess
    os.makedirs(ref.repo_dir, exist_ok=True)
    subprocess.run(["git", "init", "-q", ref.repo_dir], check=True)
    for n in range(7):
        with open(os.path.join(ref.repo_dir, f"f{n}.txt"), "w") as fh:
            fh.write("x")
    import app as A
    with A.app.test_request_context("/v2/history"):
        got = _history_remote(ref)
    # The expectation by git's own count, independent of the header's code.
    status = subprocess.run(["git", "-C", ref.repo_dir, "status", "--porcelain"],
                            capture_output=True, text=True, check=True).stdout.splitlines()
    assert len(status) >= 7 and got["dirty"] == len(status)
    assert got["dirty_paths"] == [line[3:] for line in status][:5]
    _r, page = _get(networks, "/v2/history")
    assert "today&#39;s Git tab" not in page and "today's Git tab" not in page
