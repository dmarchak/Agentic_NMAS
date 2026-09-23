"""Phase 2: reach the device, and diagnose when you cannot.

**Reaching the device is what verifies the management interface.** There is
no earlier moment at which that can be established — the name is checked for
spelling and never against the device, because the device did not exist when
the config was generated.

So the three states are not two:

* `answered` is a fact about the device;
* `answered_but_refused_the_credential` rules out the interface and the
  address, because something is there;
* `did_not_answer` **proves nothing about why**, and must not be recorded as
  "wrong interface". Same distinction as `inconclusive` is to `failed`.
"""

import json
import os

import pytest

dukpy = pytest.importorskip("dukpy")

from modules.nsot.onboard import (ANSWERED, DID_NOT_ANSWER,  # noqa: E402
                                  REFUSED_CREDENTIAL)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    from modules.nsot import manifest as _m, repo as _repo
    from modules.nsot.repo import GoldenItem, adopt_identity

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
    identity = adopt_identity(repo_dir, GoldenItem("bp1", "", "203.0.113.31"))
    _m.upsert_device(repo_dir, identity, "bp1", mgmt_ip="203.0.113.31",
                     platform="cisco_iosxe", pending=True)
    return repo_dir


def _verify(repo, *, online, reach=None, **kw):
    from modules.nsot.onboard import verify_device

    if reach is None:
        def reach(*a, **k):
            return "bp1#"
    return verify_device(repo, "bp1", "probe", online=online, reach=reach,
                         interface="GigabitEthernet2", **kw)


class TestVerificationIsAFactAboutTheDevice:

    def test_reaching_it_is_the_verification(self, repo):
        out = _verify(repo, online=lambda ip: True)
        assert out["state"] == ANSWERED
        assert out["answered"] is True
        assert out["causes"] == [], "a success must not offer causes"

    def test_silence_is_recorded_as_silence(self, repo):
        """**Not 'wrong interface'.** Failing to reach proves nothing about
        why; recording a cause as the outcome would be the classifier
        reading a connection failure as a device verdict."""
        out = _verify(repo, online=lambda ip: False)
        assert out["state"] == DID_NOT_ANSWER
        assert out["answered"] is False
        assert "did_not_answer" == out["state"]
        assert "interface" not in out["state"]

    def test_something_answering_rules_two_causes_out(self, repo):
        """A device that refuses the credential has proved its interface and
        its address. Offering the interface as a cause there would send the
        operator to the console for a question already answered."""
        def _refuse(*a, **k):
            raise RuntimeError("Authentication to device failed")

        out = _verify(repo, online=lambda ip: True, reach=_refuse)
        assert out["state"] == REFUSED_CREDENTIAL
        assert len(out["causes"]) == 1
        assert "credential" in out["causes"][0]["cause"]

    def test_a_broken_check_is_not_a_verdict(self, repo):
        """If the reachability check itself raises, that is not evidence
        about the device — a check that did not run has not passed."""
        def _boom(ip):
            raise OSError("no raw socket")

        out = _verify(repo, online=_boom)
        assert out["state"] == DID_NOT_ANSWER
        assert "check itself failed" in out["error"]


class TestItDiagnosesRatherThanFails:

    def test_the_interface_is_named_first(self, repo):
        """It is the only cause nothing before this moment could catch."""
        out = _verify(repo, online=lambda ip: False)
        assert "GigabitEthernet2" in out["causes"][0]["cause"]

    def test_every_cause_carries_a_command_that_settles_it(self, repo):
        out = _verify(repo, online=lambda ip: False)
        assert len(out["causes"]) >= 3
        for c in out["causes"]:
            assert c["command"], c
            assert c["why"], c
            assert c["where"], c
        assert any("show ip interface brief" == c["command"]
                   for c in out["causes"])

    def test_the_recovery_command_names_the_real_path(self, repo):
        """An operator reading this is already having a bad day, so the
        command is given with the actual repo path rather than a
        placeholder."""
        from modules.nsot.onboard import stage_bootstrap_credential

        stage_bootstrap_credential(repo, "bp1", "OneTimeValue123456789")
        out = _verify(repo, online=lambda ip: False)
        assert out["recovery"]["available"] is True
        assert repo in out["recovery"]["command"]
        assert "staged_bootstrap_credential" in out["recovery"]["command"]

    def test_no_staged_credential_says_so_rather_than_offering_one(self, repo):
        out = _verify(repo, online=lambda ip: False)
        assert out["recovery"]["available"] is False
        assert out["recovery"]["note"]

    def test_the_recovery_command_does_not_contain_the_secret(self, repo):
        """It prints the value; it must not BE the value. A diagnostic that
        copies the secret it recovers is a second place the secret lives."""
        from modules.nsot.onboard import stage_bootstrap_credential

        stage_bootstrap_credential(repo, "bp1", "OneTimeValue123456789")
        out = _verify(repo, online=lambda ip: False)
        assert "OneTimeValue123456789" not in json.dumps(out)


class TestPromotionOnlyOnAnAnswer:

    def test_a_device_that_answered_is_promoted(self, repo):
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import verify_and_promote

        out = verify_and_promote(repo, "bp1", "probe", actor="t",
                                 online=lambda ip: True,
                                 reach=lambda *a, **k: "bp1#",
                                 username="admin", password="rotated")
        assert out["ok"] is True, out
        assert out["promoted"] is True
        assert _m.pending_devices(repo) == []

    def test_a_device_that_did_not_answer_stays_pending(self, repo):
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import verify_and_promote

        out = verify_and_promote(repo, "bp1", "probe",
                                 online=lambda ip: False,
                                 username="admin", password="rotated")
        assert out["ok"] is False
        assert out["promoted"] is False
        assert len(_m.pending_devices(repo)) == 1, \
            "a device that never answered was promoted"


# ---------------------------------------------------------------------------
# The banner, executed
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def banner_js():
    """`pendingBannerHtml` and `pendingAgeText`, lifted from the page."""
    import re as _re

    import app as nmas

    page = nmas.app.test_client().get("/").get_data(as_text=True)
    out = []
    for name in ("pendingAgeText", "pendingBannerHtml"):
        start = page.index(f"function {name}(")
        depth, i, seen = 0, page.index("{", start), False
        while i < len(page):
            if page[i] == "{":
                depth += 1
                seen = True
            elif page[i] == "}":
                depth -= 1
                if seen and depth == 0:
                    break
            i += 1
        out.append(page[start:i + 1])
    return "\n".join(out)


def _banner(js, data):
    return dukpy.evaljs(js + f"\npendingBannerHtml({json.dumps(data)});")


def _row(name="bp1", state="in_flight", age=60):
    return {"name": name, "mgmt_ip": "203.0.113.31", "state": state,
            "age_seconds": age, "onboarded_at": "2026-09-23T10:00:00Z"}


class TestTheBannerDistinguishesErrorFromEmpty:
    """**The banner's own wrong-and-looks-right state**: rendering "no
    pending devices" because the query failed — a reassuring sentence
    produced by a broken read.

    Same correction as the drift panel's "all 9 device(s) clean" over a
    ten-device inventory, and the agent panel's disabled read returning
    `[]`. A device may be waiting and invisible, which is the one thing this
    banner exists to prevent.
    """

    def test_a_failed_query_says_so(self, banner_js):
        html = _banner(banner_js, {"ok": False, "error": "manifest unreadable"})
        assert "could not be read" in html
        assert "manifest unreadable" in html
        assert "alert-danger" in html

    def test_a_failed_query_says_it_is_not_the_same_as_none(self, banner_js):
        html = " ".join(_banner(banner_js,
                                {"ok": False, "error": "x"}).split())
        assert "not</em> the same as none being pending" in html

    def test_a_missing_payload_is_an_error_not_an_empty_list(self, banner_js):
        """`undefined` must not fall through to the empty branch."""
        for bad in (None, {}, {"pending": []}):
            html = _banner(banner_js, bad)
            assert "could not be read" in html, bad

    def test_genuinely_empty_renders_nothing(self, banner_js):
        """The control. A banner that always drew something would pass every
        test above and be ignored within a week."""
        assert _banner(banner_js, {"ok": True, "pending": []}) == ""


class TestTheBannerIsActionable:

    def test_in_flight_is_listed_quietly(self, banner_js):
        html = _banner(banner_js, {"ok": True, "pending": [_row()]})
        assert "alert-secondary" in html
        assert "overdue" not in html and "stale" not in html

    def test_overdue_is_flagged(self, banner_js):
        html = _banner(banner_js,
                       {"ok": True, "pending": [_row(state="overdue",
                                                     age=90000)]})
        assert "alert-warning" in html
        assert "overdue" in html

    def test_stale_offers_abandon_inline(self, banner_js):
        """A state an operator cannot leave from the screen that shows it is
        one they will learn to ignore."""
        html = _banner(banner_js,
                       {"ok": True, "pending": [_row(state="stale",
                                                     age=999999)]})
        assert "Abandon" in html
        assert "onboardAbandon" in html

    def test_abandon_is_NOT_offered_on_a_fresh_device(self, banner_js):
        """Offering a destructive action beside a five-minute-old device
        invites it to be used."""
        html = _banner(banner_js, {"ok": True, "pending": [_row()]})
        assert "Abandon" not in html

    def test_every_row_offers_verify(self, banner_js):
        for state in ("in_flight", "overdue", "stale"):
            html = _banner(banner_js,
                           {"ok": True, "pending": [_row(state=state)]})
            assert "onboardVerify" in html, state

    def test_the_age_is_shown_not_just_the_state(self, banner_js):
        html = _banner(banner_js, {"ok": True,
                                   "pending": [_row(age=7200)]})
        assert "2 hours" in html

    def test_the_unverified_interface_is_stated(self, banner_js):
        """The honest version of the guarantee that could not be made at
        plan time."""
        html = " ".join(_banner(banner_js,
                                {"ok": True, "pending": [_row()]}).split())
        assert "unverified" in html
        assert "never against the device" in html

    def test_the_name_is_escaped(self, banner_js):
        html = _banner(banner_js,
                       {"ok": True,
                        "pending": [_row(name="<script>alert(1)</script>")]})
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
