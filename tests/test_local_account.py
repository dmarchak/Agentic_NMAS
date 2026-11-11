"""The installation's one local account (modules/local_account.py; C2520's first step, the
operator 2026-11-10 at the Lab 9 sitting: on the laptop kit no request was a verified person,
so the NSOT export's commit, Draft, Run its tests, Publish and every AI call a person starts
refused).

What is held here: it is off by default; it is refused unless Mercury listens on loopback only;
a sign-in succeeds only with the account's name and password and fails otherwise, each failure
making the next attempt wait longer; a signed-in request is a person verified as
``local-account``, never ``access``, and the export's commit takes it where it refused before;
the access proxy's answer comes first and is unchanged; the session ends by idleness and with a
new password; a sign-in must show it came from Mercury's own page; and the password is in no
log line, no response and no file.
"""

import json
import logging
import os
import stat

import pytest

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

#: These tests are about identity: each meets the real `identify()`, where no access proxy is
#: configured, so nobody is identified unless the local account signs them in.
pytestmark = pytest.mark.real_identity

NAME = "lab-admin"
PW = "correct horse battery staple 42"
WRONG = "wrong horse battery staple 99"
ORIGIN = {"Origin": "http://localhost", "HX-Request": "true"}
SIGN_IN = "/v2/settings/installation/local-account/sign-in"
SIGN_OUT = "/v2/settings/installation/local-account/sign-out"
CARD = "/v2/settings/installation/local-account"
#: Every header a proxy writes or carries, typed here: a request holding one, even empty, is
#: not this machine's own.
PROXY_HEADERS = ["X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "Forwarded",
                 "X-Real-IP", "X-Client-IP", "True-Client-IP", "CF-Connecting-IP",
                 "Cf-Access-Jwt-Assertion", "Via"]


def _on(monkeypatch, host="127.0.0.1", setting=True, account=True):
    """The three conditions, each as the test asks: the setting, the bind address, the account."""
    from modules import config
    from modules import local_account as LA
    from modules.settings_schema import write_settings

    monkeypatch.setattr(config, "FLASK_HOST", host)
    if setting:
        assert write_settings({LA.SETTING: True}, actor="test")["ok"]
    if account:
        LA.set_password(NAME, PW)
    return LA


def _sign_in(n, name=NAME, password=PW, headers=ORIGIN):
    r = n["client"].post(SIGN_IN, data={"name": name, "password": password}, headers=headers)
    return r, r.get_data(as_text=True)


def _who(n):
    return n["client"].get("/v2/who").get_data(as_text=True)


class _Asked:
    """A request as the session reader takes it: this machine's peer, and the cookie (if any)
    a response set."""

    def __init__(self, cookie):
        self.cookies = {"mercury_local_account": cookie} if cookie else {}
        self.environ = {"REMOTE_ADDR": "127.0.0.1"}
        self.remote_addr = "127.0.0.1"
        self.headers = {}


def _request_with(n, response):
    from modules import local_account as LA

    set_cookie = response.headers.get("Set-Cookie", "")
    value = set_cookie.split(";", 1)[0].split("=", 1)[1] if set_cookie.startswith(LA.COOKIE) else ""
    return _Asked(value)


class TestOffByDefault:
    def test_nothing_is_offered_and_nobody_is_signed_in(self, networks, monkeypatch):
        LA = _on(monkeypatch, setting=False)
        st = LA.state()
        assert st["enabled"] is False and "local_account_enabled is off" in st["why"]
        r, body = _sign_in(networks)
        assert r.status_code == 403 and "local sign-in is off" in body
        assert "Set-Cookie" not in r.headers
        assert 'data-identified="no"' in _who(networks)

    def test_the_setting_s_default_is_off(self):
        from modules.settings_schema import DEFAULTS

        assert DEFAULTS["local_account_enabled"] is False

    def test_a_cookie_is_ignored_while_the_setting_is_off(self, networks, monkeypatch):
        LA = _on(monkeypatch)
        r, _ = _sign_in(networks)
        assert r.status_code == 200 and 'data-identified="yes"' in _who(networks)
        from modules.settings_schema import write_settings
        assert write_settings({LA.SETTING: False}, actor="test")["ok"]
        assert 'data-identified="no"' in _who(networks)


class TestLoopbackOnly:
    @pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.10", "::", "2001:db8::10"])
    def test_it_is_refused_where_mercury_listens_beyond_loopback(self, networks, monkeypatch,
                                                                 host):
        LA = _on(monkeypatch, host=host)
        st = LA.state()
        assert st["enabled"] is False and host in st["why"] and "loopback only" in st["why"]
        r, body = _sign_in(networks)
        assert r.status_code == 403 and "local sign-in is off" in body
        assert "Set-Cookie" not in r.headers
        # The effect: nothing was checked or counted, and nobody is signed in.
        assert LA._attempts() == {} and LA.wait_s() == 0
        assert LA.session_of(_request_with(networks, r)) == {}

    @pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
    def test_loopback_addresses_of_both_families_are_taken(self, networks, monkeypatch, host):
        assert _on(monkeypatch, host=host).state()["enabled"] is True

    def test_it_is_off_where_an_access_proxy_is_configured(self, networks, monkeypatch):
        """A proxy on the same machine makes every proxied request's peer a loopback address:
        with one configured, identity is the proxy's alone."""
        LA = _on(monkeypatch)
        from modules import identity

        assert LA.state()["enabled"] is True
        monkeypatch.setattr(identity, "is_configured", lambda: True)
        st = LA.state()
        assert st["enabled"] is False and "an access proxy is configured" in st["why"]
        r, body = _sign_in(networks)
        assert r.status_code == 403 and "local sign-in is off" in body
        assert "Set-Cookie" not in r.headers and LA._attempts() == {}

    @pytest.mark.parametrize("value", ["198.51.100.9", ""], ids=["a value", "sent empty"])
    @pytest.mark.parametrize("header", PROXY_HEADERS)
    def test_a_request_a_proxy_relayed_is_not_this_machine_s_own(self, networks, monkeypatch,
                                                                header, value):
        """Each header a proxy writes, with a value and sent EMPTY: its presence is the test,
        so an empty one is refused as a full one is."""
        LA = _on(monkeypatch)
        r, body = _sign_in(networks, headers=dict(ORIGIN, **{header: value}))
        assert r.status_code == 403 and "did not come from this machine" in body
        assert "Set-Cookie" not in r.headers and LA._attempts() == {}
        # A session a relayed request carries is not taken either.
        ok, _ = _sign_in(networks)
        asked = _request_with(networks, ok)
        secret = networks["client"].application.secret_key
        assert LA.session_of(asked, secret)["name"] == NAME
        asked.headers = {header: value}
        assert LA.session_of(asked, secret) == {}

    def test_the_headers_refused_are_the_ones_listed_here(self):
        """The list by a path of its own (typed here, never read from the code), so a header
        dropped from the code's list fails by name."""
        from modules import identity

        assert sorted(h.lower() for h in identity.PROXY_WRITTEN_HEADERS) == sorted(
            h.lower() for h in PROXY_HEADERS)

    @pytest.mark.parametrize("value", ["203.0.113.4", "", "   "])
    @pytest.mark.parametrize("header", PROXY_HEADERS)
    def test_a_header_present_is_carried_whatever_it_holds(self, networks, header, value):
        from modules import identity

        app = networks["client"].application
        with app.test_request_context("/v2/", headers={header: value}):
            assert identity.carries_proxy_header(identity_request()) is True
        with app.test_request_context("/v2/", headers={"X-Requested-With": "x", "Accept": "*/*"}):
            assert identity.carries_proxy_header(identity_request()) is False

    def test_a_peer_that_is_not_this_machine_is_not_signed_in(self, networks, monkeypatch):
        LA = _on(monkeypatch)
        r = networks["client"].post(SIGN_IN, data={"name": NAME, "password": PW}, headers=ORIGIN,
                                    environ_base={"REMOTE_ADDR": "192.0.2.77"})
        assert r.status_code == 403 and "did not come from this machine" in r.get_data(as_text=True)
        assert "Set-Cookie" not in r.headers
        assert LA.wait_s() == 0, "the password was not even checked"


class TestSignIn:
    def test_the_account_s_name_and_password_sign_in(self, networks, monkeypatch):
        LA = _on(monkeypatch)
        r, body = _sign_in(networks)
        assert r.status_code == 200 and r.headers.get("HX-Refresh") == "true"
        cookie = r.headers["Set-Cookie"]
        assert cookie.startswith(LA.COOKIE + "=")
        assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
        assert f"Signed in as <strong>{NAME}</strong> (local account, kit)" in body
        who = _who(networks)
        assert 'data-identified="yes"' in who and NAME in who
        assert "with this installation&#39;s local account" in who

    def test_a_signed_in_request_is_a_person_verified_as_local_account(self, networks,
                                                                       monkeypatch):
        LA = _on(monkeypatch)
        from modules import identity

        app = networks["client"].application
        value = LA.issue(LA.account(), app.secret_key)
        with app.test_request_context("/v2/", headers={"Cookie": f"{LA.COOKIE}={value}"},
                                      environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            actor = identity.request_actor()
            assert actor == NAME
            assert identity.actor_verification(actor) == "local-account"
            ident = identity.request_identity()
            assert ident.kind == "person" and ident.is_identified
            assert identity.may(ident, "confirm")[0] and identity.may(ident, "approve")[0]
        with app.test_request_context("/v2/", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            assert identity.request_actor() == identity.UNVERIFIED
            assert identity.actor_verification(identity.UNVERIFIED) == "none"

    def test_the_record_s_label_names_the_local_account(self):
        from modules.history_sources import VERIFIED_WORDS
        from modules.inventory_edit import actor_label

        assert actor_label(NAME, "local-account") == f"{NAME} (local account, kit)"
        assert VERIFIED_WORDS["local-account"] == "local account, kit"

    def test_a_wrong_password_or_name_does_not(self, networks, monkeypatch):
        LA = _on(monkeypatch)
        r, body = _sign_in(networks, password=WRONG)
        assert r.status_code == 401 and "Not signed in" in body
        assert "Set-Cookie" not in r.headers and 'data-identified="no"' in _who(networks)
        assert LA.check("someone-else", PW, now=LA._attempts()["until"] + 1)["ok"] is False

    def test_sign_out_clears_the_session(self, networks, monkeypatch):
        _on(monkeypatch)
        _sign_in(networks)
        assert 'data-identified="yes"' in _who(networks)
        r = networks["client"].post(SIGN_OUT, headers=ORIGIN)
        assert r.status_code == 200 and r.headers.get("HX-Refresh") == "true"
        assert 'data-identified="no"' in _who(networks)


class TestTheWaitAfterAFailure:
    def test_each_failure_makes_the_next_attempt_wait_longer(self, networks, monkeypatch):
        LA = _on(monkeypatch)
        t = 1_000_000.0
        first = LA.check(NAME, WRONG, now=t)
        assert first["ok"] is False and first["wait_s"] == LA.BACKOFF_S
        # Inside the wait even the right password is refused, unchecked.
        soon = LA.check(NAME, PW, now=t + 1)
        assert soon["ok"] is False and "too soon" in soon["why"] and soon["wait_s"] == 1
        second = LA.check(NAME, WRONG, now=t + LA.BACKOFF_S + 0.1)
        assert second["wait_s"] == LA.BACKOFF_S * 2
        third = LA.check(NAME, WRONG, now=t + 100)
        assert third["wait_s"] == LA.BACKOFF_S * 4
        # Past the wait the right password signs in, and the count starts again.
        assert LA.check(NAME, PW, now=t + 1000)["ok"] is True
        assert LA.check(NAME, WRONG, now=t + 2000)["wait_s"] == LA.BACKOFF_S

    def test_the_wait_never_passes_its_maximum(self, networks, monkeypatch):
        LA = _on(monkeypatch)
        t = 2_000_000.0
        for _ in range(12):
            got = LA.check(NAME, WRONG, now=t)
            t += got["wait_s"] + 1
        assert got["wait_s"] == LA.BACKOFF_MAX_S

    def test_the_form_says_the_wait_through_the_route(self, networks, monkeypatch):
        _on(monkeypatch)
        _sign_in(networks, password=WRONG)
        r, body = _sign_in(networks)                       # the right password, too soon
        assert r.status_code == 401 and "too soon after a failed sign-in" in body
        assert "Set-Cookie" not in r.headers


class TestTheSession:
    def test_it_ends_by_idleness_and_by_age(self, networks, monkeypatch):
        LA = _on(monkeypatch)
        secret, t = b"a-test-secret", 3_000_000.0
        value = LA.issue(LA.account(), secret, now=t)
        assert LA.read(value, secret, now=t + LA.IDLE_S - 5)["name"] == NAME
        assert LA.read(value, secret, now=t + LA.IDLE_S + 5) == {}
        kept = LA.issue(LA.account(), secret, now=t + LA.MAX_S - 10, issued=t)
        assert LA.read(kept, secret, now=t + LA.MAX_S - 5)["name"] == NAME
        assert LA.read(kept, secret, now=t + LA.MAX_S + 5) == {}

    def test_a_session_in_use_has_its_last_seen_time_written_again(self, networks, monkeypatch):
        """Idleness is counted from the last use: a request carrying a session last seen more
        than the refresh interval ago is answered with the cookie written again, its issue
        time kept."""
        LA = _on(monkeypatch)
        import time as _time

        from flask import Response

        from modules import identity
        from routes import settings_v2

        app = networks["client"].application
        now = _time.time()

        def answered(value):
            """The Set-Cookie a request carrying *value* is answered with, or ""."""
            with app.test_request_context("/v2/", headers={"Cookie": f"{LA.COOKIE}={value}"},
                                          environ_base={"REMOTE_ADDR": "127.0.0.1"}):
                assert identity.identify(identity_request()).actor == NAME
                return settings_v2._local_session_seen(Response("ok")).headers.get(
                    "Set-Cookie", "")

        old = LA.issue(LA.account(), app.secret_key, now=now - LA.REFRESH_S - 30,
                       issued=now - 600)
        again = answered(old)
        assert again.startswith(LA.COOKIE + "=") and "HttpOnly" in again
        assert "SameSite=Strict" in again
        got = LA.read(again.split(";", 1)[0].split("=", 1)[1], app.secret_key)
        assert abs(got["issued"] - (now - 600)) < 2 and got["seen"] >= now - 2
        # One just seen is not written again.
        assert answered(LA.issue(LA.account(), app.secret_key, now=now)) == ""

    def test_another_secret_or_a_new_password_ends_it(self, networks, monkeypatch):
        LA = _on(monkeypatch)
        value = LA.issue(LA.account(), b"a-test-secret", now=10.0)
        assert LA.read(value, b"another-secret", now=11.0) == {}
        assert LA.read(value + "x", b"a-test-secret", now=11.0) == {}
        LA.set_password(NAME, PW + " changed")
        assert LA.read(value, b"a-test-secret", now=11.0) == {}

    def test_it_is_flask_s_own_signing_and_never_flask_s_session(self, networks, monkeypatch):
        """Signed by Flask's session signing with the app's secret, under this module's own
        salt: Flask's session signer does not verify this cookie, and a value Flask's session
        signer made, holding the very same fields, is not a local session."""
        import time

        LA = _on(monkeypatch)
        app = networks["client"].application
        value = LA.issue(LA.account(), app.secret_key)
        assert LA.read(value, app.secret_key)["name"] == NAME
        flask_s = app.session_interface.get_signing_serializer(app)
        verified, _payload = flask_s.loads_unsafe(value)
        assert verified is False, "Flask's session signer verified the local account's cookie"
        now = int(time.time())
        forged = flask_s.dumps({"n": NAME, "k": LA.key_id(LA.account()), "i": now, "s": now})
        assert LA.read(forged, app.secret_key) == {}
        # No secret, no session: nothing is issued and nothing is read.
        assert LA.read(value, b"") == {} and LA.read(value, None) == {}
        with pytest.raises(ValueError):
            LA.issue(LA.account(), b"")

    def test_a_sign_in_must_show_it_came_from_mercury_s_own_page(self, networks, monkeypatch):
        _on(monkeypatch)
        for headers in ({}, {"Origin": "http://evil.example"},
                        {"Sec-Fetch-Site": "cross-site", "Origin": "http://localhost"},
                        {"Referer": "http://evil.example/page"}):
            r, body = _sign_in(networks, headers=headers)
            assert r.status_code == 403 and "refused" in body, headers
            assert "Set-Cookie" not in r.headers
        r, _ = _sign_in(networks, headers={"Referer": "http://localhost/v2/settings"})
        assert r.status_code == 200


class TestWhatAsksForAVerifiedPerson:
    def test_the_export_s_commit_refuses_signed_out_and_takes_the_local_account(
            self, networks, monkeypatch):
        """`export_op.apply` refused "none" on the kit (the Lab 9 sitting). Signed in, the same
        call gets past that check to its next one (the form's hash)."""
        LA = _on(monkeypatch)
        from modules import identity
        from modules.nsot import export_op

        app = networks["client"].application

        def commit():
            actor = identity.request_actor()
            return export_op.apply("Default", "not-a-hash", actor=actor,
                                   actor_verified=identity.actor_verification(actor))

        with app.test_request_context("/v2/", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            assert commit()["error"] == "an NSOT export is committed by a verified person"
        value = LA.issue(LA.account(), app.secret_key)
        with app.test_request_context("/v2/", headers={"Cookie": f"{LA.COOKIE}={value}"},
                                      environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            out = commit()
            assert "verified person" not in out["error"]
            assert "carries no preview hash" in out["error"]

    def test_the_access_proxy_s_answer_comes_first_and_is_unchanged(self, networks,
                                                                    monkeypatch):
        LA = _on(monkeypatch)
        from modules import identity

        proxy = identity.Identity(actor="person@example.com", email="person@example.com",
                                  kind="person", verified=True, outcome="ok", peer="192.0.2.5",
                                  peer_trusted=True, verification="access")
        app = networks["client"].application
        # A request carrying a valid local session: alone, it is the local account's.
        value = LA.issue(LA.account(), app.secret_key)
        asked = {"headers": {"Cookie": f"{LA.COOKIE}={value}"},
                 "environ_base": {"REMOTE_ADDR": "127.0.0.1"}}
        with app.test_request_context("/v2/", **asked):
            assert identity.identify(identity_request()).verification == "local-account"
        # The same request once the proxy identifies someone: the proxy's answer, whole.
        monkeypatch.setattr(identity, "_identify_access", lambda request: proxy)
        with app.test_request_context("/v2/", **asked):
            got = identity.identify(identity_request())
            assert got is proxy and got.verification == "access"
            assert identity.request_actor() == "person@example.com"
            assert identity.actor_verification("person@example.com") == "access"
            assert identity.actor_verification(NAME) == "none"

    def test_a_commit_made_signed_in_reads_local_account_never_access(self, networks,
                                                                      monkeypatch, tmp_path):
        """The record every operation's commit leaves (a DHCP confirm's among them: its commit
        goes through this same choke point): the account's name, verified as local-account."""
        import subprocess

        LA = _on(monkeypatch)
        from modules.nsot import repo as R

        repo = str(tmp_path / "config_repo")
        R.init_repo(repo)
        (tmp_path / "config_repo" / "f").write_text("x\n")
        R.git(repo, "add", "f")
        app = networks["client"].application
        value = LA.issue(LA.account(), app.secret_key)
        with app.test_request_context("/v2/", headers={"Cookie": f"{LA.COOKIE}={value}"},
                                      environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            rc, _, err = R.git(repo, "commit", "-m", f"t\n\nSource: dhcp\nActor: {NAME}\n")
        assert rc == 0, err
        message = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%B"],
                                 capture_output=True, text=True, check=True).stdout
        assert f"Actor: {NAME}" in message
        assert "Actor-Verified: local-account" in message
        assert "Actor-Verified: access" not in message


class TestAJobStartedSignedIn:
    """A job carries how the person who started it was verified, read once at the hand-over
    (`identity.carried`), into every commit it makes: local-account for the local account,
    never access (the operator, 2026-11-10)."""

    def _signed_in(self, networks, LA):
        app = networks["client"].application
        value = LA.issue(LA.account(), app.secret_key)
        return app.test_request_context("/v2/", headers={"Cookie": f"{LA.COOKIE}={value}"},
                                        environ_base={"REMOTE_ADDR": "127.0.0.1"})

    def test_a_job_s_commit_records_local_account(self, networks, monkeypatch, tmp_path):
        """Through the one starter every job uses (`capture_job.start`, C686): the commit the
        job makes in its own thread names the account and says local-account."""
        import subprocess

        LA = _on(monkeypatch)
        from modules import identity
        from modules.nsot import capture_job
        from modules.nsot import repo as R

        monkeypatch.setattr(capture_job, "_announce", lambda job_id, ok: None)
        repo = str(tmp_path / "config_repo")
        R.init_repo(repo)

        def work(job_id):
            (tmp_path / "config_repo" / "f").write_text("x\n")
            R.git(repo, "add", "f")
            rc, _, err = R.git(repo, "commit", "-m", f"t\n\nSource: save\nActor: {NAME}\n")
            assert rc == 0, err
            return {"same": identity.actor_verification(NAME),
                    "other": identity.actor_verification("somebody-else"),
                    "message": subprocess.run(["git", "-C", repo, "log", "-1", "--format=%B"],
                                              capture_output=True, text=True,
                                              check=True).stdout}

        with self._signed_in(networks, LA):
            job = capture_job.start("Default", "a save", NAME, work, kind="save")
        assert capture_job.wait(job, 10)
        got = capture_job.get(job)
        assert got["state"] == "done", got["error"]
        assert got["payload"]["same"] == "local-account"
        assert got["payload"]["other"] == "none"
        assert "Actor-Verified: local-account" in got["payload"]["message"]
        assert "Actor-Verified: access" not in got["payload"]["message"]

    def test_the_rotation_job_carries_local_account(self, networks, monkeypatch):
        """A job handed the identity by name (`rotate_op.start`'s *ident*, as the deploy, the
        reload, the adoption and an approved heal hand theirs): the same carrier."""
        LA = _on(monkeypatch)
        from modules import identity
        from modules.nsot import capture_job
        from modules.nsot import rotate_op as RO

        monkeypatch.setattr(capture_job, "_announce", lambda job_id, ok: None)
        with self._signed_in(networks, LA):
            ident = identity.verified_identity()
        assert ident is not None and ident.verification == "local-account"
        seen = {}

        def work(list_name, hostname, *, actor, fingerprint):
            seen["same"] = identity.actor_verification(NAME)
            seen["other"] = identity.actor_verification("someone@example.com")
            return {"ok": True}

        job = RO.start("Default", "r2", actor=NAME, fingerprint="f", ident=ident, work=work)
        assert capture_job.wait(job, 10)
        assert seen == {"same": "local-account", "other": "none"}

    def test_the_kind_is_read_once_at_the_hand_over(self):
        """What the job carries is the kind the identity stated when it was handed over: a
        change to the object afterwards changes nothing, one that stated nothing carries
        none, and a block inside another gives the outer one's kind back when it ends."""
        import types

        from modules import identity

        who = types.SimpleNamespace(is_identified=True, actor=NAME, kind="person",
                                    verification="local-account")
        unsaid = types.SimpleNamespace(is_identified=True, actor=NAME, kind="person")
        with identity.carried(who):
            who.verification = "access"
            assert identity.actor_verification(NAME) == "local-account"
            with identity.carried(unsaid):
                unsaid.verification = "access"
                assert identity.actor_verification(NAME) == "none"
            with identity.carried(None):
                pass
            assert identity.actor_verification(NAME) == "local-account"


class TestHowAnIdentityWasVerifiedFailsClosed:
    """`identity.verification_of`: an identity that does not say how it was established is
    ``none``, never ``access`` (the operator, 2026-11-10)."""

    @pytest.mark.parametrize("stated", [None, "", " ", "ACCESS", "access ", "host-shell",
                                        "policy", "none", 7, True, ["access"]],
                             ids=repr)
    def test_one_that_does_not_say_how_is_none(self, stated):
        import types

        from modules import identity

        who = types.SimpleNamespace(is_identified=True, actor=NAME, kind="person")
        if stated is not None:
            who.verification = stated
        assert identity.verification_of(who) == "none"
        # Carried into a job, and inside a request: the record says none, whoever it names.
        with identity.carried(who):
            assert identity.actor_verification(NAME) == "none"
        from flask import Flask, g

        with Flask(__name__).test_request_context("/"):
            g.nmas_identity = who
            assert identity.actor_verification(NAME) == "none"

    @pytest.mark.parametrize("stated", ["access", "local-account"])
    def test_one_that_says_is_recorded_as_it_says(self, stated):
        import types

        from modules import identity

        who = types.SimpleNamespace(is_identified=True, actor=NAME, kind="person",
                                    verification=stated)
        assert identity.verification_of(who) == stated
        with identity.carried(who):
            assert identity.actor_verification(NAME) == stated
            assert identity.actor_verification("somebody-else") == "none"

    def test_the_name_chip_claims_nothing_for_one_that_does_not_say(self, networks, monkeypatch):
        """Drawn through the page's own code (`device_v2._who`): the chip names the person and
        says nothing of how, where the identity did not say (it read "through Cloudflare
        Access" for anything that was not the local account)."""
        import types

        from flask import g

        from routes import device_v2

        app = networks["client"].application
        unsaid = types.SimpleNamespace(is_identified=True, actor="operator@example.invalid",
                                       kind="person", peer="192.0.2.5")
        with app.test_request_context("/v2/"):
            g.nmas_identity = unsaid
            assert device_v2._who()["how"] == ""
        with app.test_request_context("/v2/"):
            g.nmas_identity = types.SimpleNamespace(**vars(unsaid), verification="access")
            assert device_v2._who()["how"] == "through Cloudflare Access"

    def test_every_identified_identity_the_product_builds_says_how(self):
        """Parsed: each `Identity(...)` built with ``outcome="ok"`` in the product passes
        ``verification=``. The proxy's path and the local account's are the two; a third that
        does not say would be recorded by the class's default."""
        import ast

        from tests.source_index import tracked

        def built(source):
            out = []
            for node in ast.walk(ast.parse(source)):
                if not (isinstance(node, ast.Call)
                        and getattr(node.func, "attr", getattr(node.func, "id", "")) == "Identity"):
                    continue
                kw = {k.arg: k.value for k in node.keywords}
                ok = kw.get("outcome")
                if isinstance(ok, ast.Constant) and ok.value == "ok":
                    out.append((node.lineno, "verification" in kw))
            return out

        # The planted case: one that says and one that does not.
        assert built('Identity(actor=a, outcome="ok")\n'
                     'I.Identity(actor=a, outcome="ok", verification=V)\n'
                     'Identity(outcome="no_header")\n') == [(1, False), (2, True)]
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        found = {}
        for path in tracked("app.py", "modules", "routes", suffix=".py"):
            with open(path, encoding="utf-8") as fh:
                for line, says in built(fh.read()):
                    found[f"{os.path.relpath(path, root)}:{line}"] = says
        assert len(found) >= 2, found
        assert sorted({k.split(":")[0] for k in found}) == ["modules/identity.py",
                                                            "modules/local_account.py"], found
        assert all(found.values()), [k for k, says in found.items() if not says]


def identity_request():
    from flask import request

    return request


class TestThePasswordIsNowhere:
    def test_not_in_a_log_line_a_response_or_a_file(self, networks, monkeypatch, caplog):
        caplog.set_level(logging.DEBUG)
        _on(monkeypatch)
        r, body = _sign_in(networks)
        bodies = [body, networks["client"].get(CARD).get_data(as_text=True), _who(networks)]
        assert r.status_code == 200
        bad, bad_body = _sign_in(networks, password=WRONG)
        assert bad.status_code == 401
        bodies += [bad_body, str(dict(bad.headers))]
        for text in bodies + [caplog.text, str(dict(r.headers))]:
            assert PW not in text and WRONG not in text
        for name in os.listdir(networks["dir"]):
            path = os.path.join(networks["dir"], name)
            if os.path.isfile(path):
                data = open(path, "rb").read()
                assert PW.encode() not in data and WRONG.encode() not in data, name

    def test_the_account_s_file_holds_a_hash_and_is_owner_only(self, networks, monkeypatch):
        LA = _on(monkeypatch)
        path = os.path.join(networks["dir"], LA.FILE)
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        doc = json.load(open(path, encoding="utf-8"))
        assert sorted(doc) == ["hash", "name", "salt", "scrypt", "set_at"]
        assert len(bytes.fromhex(doc["hash"])) == 32 and len(bytes.fromhex(doc["salt"])) == 16
        first = doc["hash"]
        LA.set_password(NAME, PW)
        assert json.load(open(path, encoding="utf-8"))["hash"] != first, "a new salt each time"

    @pytest.mark.parametrize("name, password, why", [
        ("", PW, "not an account name"), ("unverified", PW, "not an account name"),
        ("service:x", PW, "not an account name"), (NAME, "2brief4it", "shorter than")])
    def test_a_name_or_password_out_of_shape_is_refused(self, networks, monkeypatch, name,
                                                        password, why):
        LA = _on(monkeypatch, account=False)
        with pytest.raises(LA.Refused) as exc:
            LA.set_password(name, password)
        assert why in str(exc.value) and password not in str(exc.value)
        assert LA.account() == {}


class TestTheChipAndTheCard:
    def test_the_chip_links_to_the_sign_in_and_signing_in_there_names_the_person(
            self, networks, monkeypatch):
        LA = _on(monkeypatch)
        who = _who(networks)
        assert '<a class="who who-none"' in who
        assert 'href="/v2/settings/installation?tab=access#card-local-account"' in who
        page = networks["client"].get("/v2/settings/installation?tab=access").get_data(as_text=True)
        assert f'id="card-local-account" hx-get="{CARD}' in page
        card = networks["client"].get(CARD).get_data(as_text=True)
        assert 'name="password"' in card and 'type="password"' in card
        r, _ = _sign_in(networks)
        # The effect: the response's cookie is a session of the account's.
        assert LA.session_of(_request_with(networks, r),
                             networks["client"].application.secret_key)["name"] == NAME
        assert 'data-identified="yes"' in _who(networks)

    def test_with_no_account_the_chip_and_the_card_say_why_and_a_press_signs_nobody_in(
            self, networks, monkeypatch):
        LA = _on(monkeypatch, account=False)
        who = _who(networks)
        assert "<button" in who and "Local sign-in is not offered: no account is set" in who
        card = networks["client"].get(CARD).get_data(as_text=True)
        assert "Local sign-in is not offered here: no account is set" in card
        assert 'name="password"' not in card
        r, body = _sign_in(networks)
        assert r.status_code == 403 and "local sign-in is off" in body
        # The effect: no account was made, nothing was counted, nobody is signed in.
        assert LA.account() == {} and LA._attempts() == {}
        assert LA.session_of(_request_with(networks, r)) == {}

    def test_beyond_loopback_the_chip_is_as_it_was_and_a_press_checks_nothing(
            self, networks, monkeypatch):
        LA = _on(monkeypatch, host="0.0.0.0", setting=False)
        who = _who(networks)
        assert "Local sign-in" not in who and "Click to check again." in who
        from modules.settings_schema import write_settings
        assert write_settings({LA.SETTING: True}, actor="test")["ok"]
        card = networks["client"].get(CARD).get_data(as_text=True)
        assert "Local sign-in is not offered here" in card and "0.0.0.0" in card
        assert 'name="password"' not in card
        r, _ = _sign_in(networks)
        assert r.status_code == 403
        # The effect: the account's password was not even checked.
        assert LA._attempts() == {} and LA.session_of(_request_with(networks, r)) == {}


class TestTheCommand:
    def _main(self, argv, answers):
        import importlib.machinery
        import importlib.util

        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "scripts", "nmas-local-account")
        loader = importlib.machinery.SourceFileLoader("nmas_local_account", path)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(mod)
        said = iter(answers)
        return mod.main(argv, ask=lambda prompt: next(said))

    def test_it_sets_the_account_from_two_matching_entries(self, networks, monkeypatch, capsys):
        LA = _on(monkeypatch, account=False)
        assert self._main(["set-password", NAME], [PW, PW]) == 0
        out = capsys.readouterr().out
        assert LA.account()["name"] == NAME and PW not in out
        assert "local sign-in: possible, as " + NAME in out

    def test_clear_removes_the_account_and_ends_its_sessions(self, networks, monkeypatch,
                                                             capsys):
        LA = _on(monkeypatch)
        value = LA.issue(LA.account(), b"a-test-secret", now=10.0)
        assert self._main(["clear"], []) == 0
        assert "cleared: the account is removed" in capsys.readouterr().out
        assert LA.account() == {} and LA.read(value, b"a-test-secret", now=11.0) == {}
        assert self._main(["clear"], []) == 0
        assert "nothing to clear" in capsys.readouterr().out

    def test_two_entries_that_differ_write_nothing(self, networks, monkeypatch, capsys):
        LA = _on(monkeypatch, account=False)
        assert self._main(["set-password", NAME], [PW, WRONG]) == 1
        out = capsys.readouterr().out
        assert LA.account() == {} and "the two entries differ" in out
        assert PW not in out and WRONG not in out
