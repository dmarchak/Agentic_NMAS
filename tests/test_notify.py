"""Notifications, board H's H7 (docs/HEAL_TO_INTENT.md section 10): the SMTP relay sender and
its test send, the delivery log and the `notify`/`failed` row; the egress mask on everything
sent; the generic signed webhook; the verification codes.

No test touches a network: the relay's classes and the webhook's POST are fakes handed in
through the modules' attributes, and every store is under the test's own folder. Secret
values here are placeholders made for the test.
"""

import email
import email.policy
import json
import smtplib
import types

import pytest
import requests

from modules import credentials, redact
from modules.notify import addresses, delivery, message, relay, teams, webhook

RELAY_PW = "Relay-Placeholder-Pw-77"
HOOK_SECRET = "Hook-Signing-Placeholder-0123456789"
DEVICE_PW = "Planted-Device-Secret-42"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Every notification store under *tmp_path*; settings from a dict over the defaults; the
    relay's classes, the webhook's POST and the retry wait faked."""
    from modules import config, settings_schema

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "credential_profiles.json"))
    values = {}
    real = settings_schema.get_setting
    monkeypatch.setattr(settings_schema, "get_setting",
                        lambda key, default=None: values[key] if key in values
                        else real(key, default))
    e = types.SimpleNamespace(settings=values, smtp=[], posts=[], waits=[], tmp=tmp_path,
                              smtp_fail=[], post_status=[])

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, context=None):
            self.host, self.port, self.timeout, self.context = host, port, timeout, context
            self.calls, self.sent, self.login_args = [], [], None
            e.smtp.append(self)

        def ehlo(self):
            self.calls.append("ehlo")

        def starttls(self, context=None):
            self.calls.append("starttls")

        def login(self, user, password):
            self.login_args = (user, password)

        def send_message(self, msg):
            if e.smtp_fail:
                raise e.smtp_fail.pop(0)
            self.sent.append(msg.as_bytes())

        def quit(self):
            self.calls.append("quit")

        def close(self):
            self.calls.append("close")

    class FakeSSL(FakeSMTP):
        implicit = True

    def fake_post(url, data=None, headers=None, timeout=None, allow_redirects=True):
        e.posts.append({"url": url, "data": data, "headers": dict(headers or {}),
                        "timeout": timeout, "allow_redirects": allow_redirects})
        if e.post_status:
            status = e.post_status.pop(0)
            if isinstance(status, Exception):
                raise status
            return types.SimpleNamespace(status_code=status)
        return types.SimpleNamespace(status_code=204)

    monkeypatch.setattr(relay, "SMTP", FakeSMTP)
    monkeypatch.setattr(relay, "SMTP_SSL", FakeSSL)
    monkeypatch.setattr(webhook, "POST", fake_post)
    monkeypatch.setattr(delivery, "SLEEP", e.waits.append)
    return e


def _relay(e, host="smtp.example.com", tls="starttls", user="mercury"):
    e.settings.update(notify_smtp_host=host, notify_smtp_tls=tls, notify_smtp_username=user,
                      notify_smtp_from="mercury@example.com")
    credentials.set_notify_secret("relay", RELAY_PW)


def _verified(team, dest):
    code = teams.issue_code(team, dest, by="alex")
    assert teams.confirm_code(team, dest, code, by="alex")["ok"]
    teams.set_enabled(team, dest, True, by="alex")


def _team_with_email(address="ops@example.com", verified=True):
    team = teams.add_team("Network ops", by="alex")["team"]
    dest = teams.add_email(team, address, by="alex")["destination"]
    if verified:
        _verified(team, dest)
    return team, dest


def _team_with_webhook(url="https://hooks.example.com/mercury", verified=True):
    team = teams.add_team("Webhooks", by="alex")["team"]
    dest = teams.add_webhook(team, url, HOOK_SECRET, by="alex")["destination"]
    if verified:
        _verified(team, dest)
    return team, dest


def _event(**over):
    ev = {"incident": "inc-0001", "event": "cant_fix", "network": "Default", "device": "r2",
          "kind": "ospf.interface", "outcome": "could not fix: the adjacency stays down",
          "detected": "OSPF adjacency r2-r3 down", "detected_at": "2026-11-03T18:00:00Z",
          "steps": [{"what": "re-read r2", "result": "drift: 1 unit"}],
          "todo": "check the link", "link": "/v2/history?kind=notifications"}
    ev.update(over)
    return ev


def _mail(raw: bytes):
    return email.message_from_bytes(raw, policy=email.policy.default)


# ── Step 1: the relay, the test send, the delivery log, notify/failed ─────────────────────


class TestNothingConfiguredNothingSent:
    def test_the_defaults_set_no_relay(self):
        from modules.settings_schema import DEFAULTS
        assert DEFAULTS["notify_smtp_host"] == "" and DEFAULTS["notify_smtp_tls"] == "starttls"
        assert DEFAULTS["notify_link_base"] == "" and DEFAULTS["notify_smtp_from"] == ""

    def test_no_team_named_sends_nothing_and_logs_nothing(self, env):
        got = delivery.deliver_event(_event(), [])
        assert got == {"ok": True, "sent": 0, "failed": 0, "deliveries": [], "error": ""}
        assert env.smtp == [] and env.posts == [] and delivery.read_log()["state"] == "absent"

    def test_a_team_with_no_relay_set_is_refused_once_and_not_retried(self, env):
        team, _dest = _team_with_email()
        got = delivery.deliver_event(_event(), [team])
        assert got["sent"] == 0 and got["deliveries"][0]["outcome"] == "refused"
        rows = delivery.read_log()["rows"]
        assert len(rows) == 1 and rows[0]["final"] and env.waits == []
        assert "notify_smtp_host is empty" in rows[0]["error"] and env.smtp == []

    def test_an_unverified_or_off_destination_receives_no_event(self, env):
        _relay(env)
        team = teams.add_team("Ops", by="alex")["team"]
        teams.add_email(team, "a@example.com", by="alex")
        off = teams.add_email(team, "b@example.com", by="alex")["destination"]
        code = teams.issue_code(team, off, by="alex")
        teams.confirm_code(team, off, code, by="alex")        # verified, never turned on
        assert delivery.deliver_event(_event(), [team])["deliveries"] == []
        assert env.smtp == []


class TestTheRelay:
    def test_starttls_is_required_and_the_login_uses_the_stored_password(self, env):
        _relay(env)
        team, _dest = _team_with_email()
        assert delivery.deliver_event(_event(), [team])["sent"] == 1
        conn = env.smtp[0]
        assert (conn.host, conn.port, conn.calls[:3]) == ("smtp.example.com", 587,
                                                          ["ehlo", "starttls", "ehlo"])
        assert conn.login_args == ("mercury", RELAY_PW) and conn.timeout == delivery.SEND_TIMEOUT_S
        assert not hasattr(conn, "implicit")

    def test_implicit_tls_opens_the_ssl_class_and_no_starttls(self, env):
        _relay(env, tls="implicit")
        env.settings["notify_smtp_port"] = 465
        team, _ = _team_with_email()
        delivery.deliver_event(_event(), [team])
        assert env.smtp[0].implicit and "starttls" not in env.smtp[0].calls
        assert env.smtp[0].context is not None

    @pytest.mark.parametrize("host", ["2001:db8::25", "[2001:db8::25]", "192.0.2.25"])
    def test_a_relay_at_an_ipv6_or_ipv4_address_is_sent_to(self, env, host):
        _relay(env, host=host)
        team, _ = _team_with_email()
        assert delivery.deliver_event(_event(), [team])["sent"] == 1
        assert env.smtp[0].host == host.strip("[]")

    @pytest.mark.parametrize("host", ["192.0.2.25", "2001:db8::25", "smtp.example.com"])
    def test_plain_smtp_off_loopback_is_refused_naming_the_host(self, env, host):
        _relay(env, host=host, tls="none")
        team, _ = _team_with_email()
        got = delivery.deliver_event(_event(), [team])
        assert got["deliveries"][0]["outcome"] == "refused" and env.smtp == []
        assert "not this host's loopback" in delivery.read_log()["rows"][0]["error"]

    @pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
    def test_plain_smtp_to_loopback_is_allowed(self, env, host):
        _relay(env, host=host, tls="none")
        team, _ = _team_with_email()
        assert delivery.deliver_event(_event(), [team])["sent"] == 1
        assert "starttls" not in env.smtp[0].calls

    def test_a_follow_up_threads_under_the_incident_s_first_message(self, env):
        _relay(env)
        team, _ = _team_with_email()
        delivery.deliver_event(_event(), [team])
        delivery.deliver_event(_event(event="cleared", outcome="cleared"), [team])
        first, second = (_mail(c.sent[0]) for c in env.smtp)
        assert first["Message-ID"] == "<incident.inc-0001@example.com>"
        assert first["In-Reply-To"] is None
        assert second["In-Reply-To"] == second["References"] == first["Message-ID"]
        assert second["Message-ID"] != first["Message-ID"]

    def test_the_message_says_facts_first_then_the_link(self, env):
        _relay(env)
        env.settings["notify_link_base"] = "https://mercury.example"
        team, _ = _team_with_email()
        delivery.deliver_event(_event(), [team])
        msg = _mail(env.smtp[0].sent[0])
        body = msg.get_content()
        assert msg["Subject"] == "[Mercury] r2 on Default: could not fix"
        assert msg["To"] == "ops@example.com" and msg["Auto-Submitted"] == "auto-generated"
        order = [body.index(w) for w in ("Outcome:", "Detected:", "What Mercury tried:",
                                         "What to do:", "Open in Mercury: https://mercury."
                                         "example/v2/history?kind=notifications")]
        assert order == sorted(order)

    def test_with_no_link_base_the_link_is_the_path_and_says_so(self, env):
        _relay(env)
        team, _ = _team_with_email()
        delivery.deliver_event(_event(), [team])
        body = _mail(env.smtp[0].sent[0]).get_content()
        assert "Open in Mercury: /v2/history?kind=notifications (the address Mercury is " \
               "reached by is not set: notify_link_base)" in body


class TestAnEventCarriesOnlyItsFields:
    def test_configuration_lines_under_another_name_are_refused(self):
        with pytest.raises(ValueError, match="not lines"):
            message.check_event(_event(lines=["ip access-list extended X"]))

    def test_a_step_with_another_field_is_refused(self):
        with pytest.raises(ValueError, match="a step carries only"):
            message.check_event(_event(steps=[{"what": "x", "result": "y", "config": "z"}]))

    @pytest.mark.parametrize("link", ["https://evil.example/", "/v1/x", "//evil.example/v2/"])
    def test_a_link_off_mercury_is_refused(self, link):
        with pytest.raises(ValueError, match="not a Mercury page"):
            message.check_event(_event(link=link))

    def test_a_header_break_in_a_field_becomes_a_space(self):
        facts = message.check_event(_event(device="r2\r\nBcc: x@example.com"))
        assert "\r" not in facts["device"] and "\n" not in facts["device"]

    def test_a_test_or_code_is_never_sent_as_an_incident_event(self, env):
        with pytest.raises(ValueError, match="sent by its own call"):
            delivery.deliver_event(_event(event="verification"), [])


class TestRetriesAndTheLog:
    def test_a_failed_attempt_is_retried_and_each_attempt_is_a_row(self, env):
        _relay(env)
        team, dest = _team_with_email()
        env.smtp_fail[:] = [smtplib.SMTPServerDisconnected("gone"), OSError("reset")]
        got = delivery.deliver_event(_event(), [team])
        assert got["sent"] == 1 and got["deliveries"][0]["attempts"] == 3
        rows = list(reversed(delivery.read_log()["rows"]))
        assert [(r["attempt"], r["outcome"], r["final"]) for r in rows] == [
            (1, "failed", False), (2, "failed", False), (3, "sent", True)]
        assert env.waits == [delivery.RETRY_WAIT_S] * 2
        assert {r["recipient"] for r in rows} == {"…@example.com"}
        assert all(r["duration_s"] >= 0 and r["of"] == 3 for r in rows)
        assert teams.read()["teams"][team]["destinations"][dest]["last"]["outcome"] == "sent"

    def test_three_failures_are_the_last_failure_and_raise_the_row(self, env):
        from modules import attention
        _relay(env)
        team, dest = _team_with_email()
        env.smtp_fail[:] = [OSError("refused")] * 3
        got = delivery.deliver_event(_event(), [team])
        assert got == dict(got, ok=False, sent=0, failed=1)
        assert len(delivery.read_log()["rows"]) == 3 and len(env.waits) == 2
        rows = attention.notify_source()["rows"]
        assert len(rows) == 1 and rows[0]["kind"] == "failed" and rows[0]["level"] == "danger"
        assert rows[0]["event"] == got["deliveries"][0]["id"] and rows[0]["acknowledge"]
        assert "…@example.com" in rows[0]["what"] and "OSError: refused" in rows[0]["cause"]
        assert rows[0]["action"]["href"] == "/v2/history?kind=notifications"
        assert dest in rows[0]["id"]

    def test_the_next_success_clears_the_row_and_turning_it_off_does_too(self, env):
        from modules import attention
        _relay(env)
        team, dest = _team_with_email()
        env.smtp_fail[:] = [OSError("refused")] * 3
        delivery.deliver_event(_event(), [team])
        assert attention.notify_source()["rows"]
        assert delivery.send_test(team, dest, by="alex")["ok"]
        assert attention.notify_source()["rows"] == []
        env.smtp_fail[:] = [OSError("refused")] * 3
        delivery.deliver_event(_event(), [team])
        assert attention.notify_source()["rows"]
        teams.set_enabled(team, dest, False, by="alex")
        assert attention.notify_source()["rows"] == []

    def test_the_failure_is_acknowledged_with_a_reason_for_that_delivery(self, env):
        from modules import acknowledgements as ACK
        from modules import attention
        _relay(env)
        team, _dest = _team_with_email()
        env.smtp_fail[:] = [OSError("refused")] * 3
        delivery.deliver_event(_event(), [team])
        (r,) = attention.notify_source()["rows"]
        got = attention.acknowledge(r["id"], r["event"], "the relay was down for its upgrade",
                                    by="op@example.com", verified="access")
        assert got["ok"], got
        (entry,) = [e for e in ACK.read()["rows"] if e["row"] == r["id"]]
        assert entry["kind"] == "notify/failed" and entry["event"] == r["event"]

    def test_an_unreadable_teams_store_is_its_own_row_never_none(self, env):
        from modules import attention
        (env.tmp / "notify_teams.json").write_text("{not json")
        got = attention.notify_source()
        assert got["rows"][0]["kind"] == "unreadable"

    def test_the_test_send_is_one_attempt_recorded_with_who_asked(self, env):
        _relay(env)
        team, dest = _team_with_email(verified=False)
        env.smtp_fail[:] = [OSError("refused")]
        got = delivery.send_test(team, dest, by="alex")
        assert not got["ok"] and got["attempts"] == 1 and env.waits == []
        row = delivery.read_log()["rows"][0]
        assert (row["event"], row["by"], row["final"]) == ("test", "alex", True)
        assert delivery.send_test(team, dest, by="alex")["ok"]
        assert "A test send from Mercury" in _mail(env.smtp[-1].sent[0]).get_content()

    def test_a_test_send_names_who_asked(self, env):
        team, dest = _team_with_email(verified=False)
        with pytest.raises(teams.Refused, match="names the person"):
            delivery.send_test(team, dest, by="")

    def test_the_log_is_owner_only(self, env):
        import os
        import stat
        _relay(env)
        team, _ = _team_with_email()
        delivery.deliver_event(_event(), [team])
        for name in ("notify_deliveries.jsonl", "notify_teams.json"):
            assert stat.S_IMODE(os.stat(env.tmp / name).st_mode) == 0o600, name


class TestHistoryDrawsTheLog:
    def _ctx(self, device=""):
        return {"ref": types.SimpleNamespace(name="Default"), "device": device, "limit": 50,
                "members": None, "since": None, "until": None}

    def test_each_attempt_is_a_notification_row_on_its_network_and_device(self, env):
        from modules import history_sources as H
        _relay(env)
        team, dest = _team_with_email()
        env.smtp_fail[:] = [OSError("refused")]
        delivery.deliver_event(_event(), [team])
        delivery.send_test(team, dest, by="alex")
        events = H.notifications(self._ctx())["events"]
        assert [e["kind"] for e in events] == ["notification"] * 3
        assert events[0]["devices"] == [] and events[0]["who"] == "alex"
        assert events[-1]["outcome"] == "failed" and events[-1]["marks"] == ["not delivered"]
        assert events[-1]["devices"] == ["r2"]
        device_rows = H.notifications(self._ctx(device="r2"))["events"]
        assert len(device_rows) == 2 and all(e["devices"] == ["r2"] for e in device_rows)
        other = H.notifications({**self._ctx(), "ref": types.SimpleNamespace(name="Branch")})
        assert len(other["events"]) == 1         # the test send, the installation's own
        assert H.SOURCE_KINDS["notifications"] == ("notification",)
        assert H.KIND_FILTERS["notifications"] == ("notification",)


# ── Step 2: the egress mask on everything sent ────────────────────────────────────────────


def _risky_event():
    return _event(steps=[
        {"what": "snmp-server community PlantedComm99 RO", "result": "removed"},
        {"what": "neighbor 192.0.2.1 password 7 0822455D0A16", "result": "kept"},
        {"what": "neighbor 2001:db8::2 password 7 0822455D0A17", "result": "kept"},
        {"what": f"login failed for {DEVICE_PW}", "result": "said"},
        {"what": "a hash $9$PlantedHashValue11 was seen mid-line", "result": "said"}])


PLANTED = ("PlantedComm99", "0822455D0A16", "0822455D0A17", DEVICE_PW, RELAY_PW, HOOK_SECRET,
           "PlantedHashValue11")


class TestTheEgressMask:
    def test_nothing_an_email_carries_holds_a_secret(self, env):
        credentials.set_controller_credential("default/ctl", username="u", password=DEVICE_PW)
        _relay(env)
        team, _ = _team_with_email()
        assert delivery.deliver_event(_risky_event(), [team])["sent"] == 1
        raw = env.smtp[0].sent[0]
        decoded = _mail(raw).get_content() + str(_mail(raw)["Subject"])
        for value in PLANTED:
            assert value.encode() not in raw and value not in decoded, value
        assert "<redacted:" in decoded and "192.0.2.1" in decoded and "2001:db8::2" in decoded

    def test_nothing_a_webhook_carries_holds_a_secret(self, env):
        credentials.set_controller_credential("default/ctl", username="u", password=DEVICE_PW)
        team, _ = _team_with_webhook()
        assert delivery.deliver_event(_risky_event(), [team])["sent"] == 1
        post = env.posts[-1]
        sent = post["data"] + json.dumps(post["headers"]).encode() + post["url"].encode()
        for value in PLANTED:
            assert value.encode() not in sent, value
        assert b"<redacted:" in post["data"]

    def test_with_the_redaction_table_unreadable_a_send_carrying_its_secret_is_refused(
            self, env, monkeypatch):
        """The backstop: the known values' table read as nothing (a credential store that would
        not open), and a step quoting the send's own secret. Nothing leaves."""
        monkeypatch.setattr(redact, "known_secret_values", lambda: {})
        _relay(env)
        mail_team, _ = _team_with_email()
        hook_team, _ = _team_with_webhook()
        got = delivery.deliver_event(_event(steps=[
            {"what": f"echo {RELAY_PW}", "result": f"echo {HOOK_SECRET}"}]),
            [mail_team, hook_team])
        assert [d["outcome"] for d in got["deliveries"]] == ["refused", "refused"]
        assert env.smtp == [] and env.posts == []
        errors = " ".join(r["error"] for r in delivery.read_log()["rows"])
        assert "carried the relay's password" in errors and "carried the webhook's" in errors

    def test_the_subject_is_masked_too(self, env):
        credentials.set_controller_credential("default/ctl", username="u", password=DEVICE_PW)
        _relay(env)
        team, _ = _team_with_email()
        delivery.deliver_event(_event(device=DEVICE_PW), [team])
        raw = env.smtp[0].sent[0]
        assert DEVICE_PW not in str(_mail(raw)["Subject"]) and DEVICE_PW.encode() not in raw
        assert "<redacted:" in str(_mail(raw)["Subject"])

    def test_a_secret_split_by_the_body_s_encoding_is_still_found(self, env, monkeypatch):
        """Quoted-printable breaks a long line at 76 characters, and a value across the break
        is not in the bytes as itself: the backstop reads the decoded text too."""
        monkeypatch.setattr(redact, "known_secret_values", lambda: {})
        _relay(env)
        team, _ = _team_with_email()
        for pad in range(60, 80):
            got = delivery.deliver_event(_event(steps=[
                {"what": "x" * pad + RELAY_PW, "result": "y"}]), [team])
            assert got["deliveries"][0]["outcome"] == "refused", pad
        assert env.smtp == []

    def test_the_tls_context_verifies_the_relay_s_certificate(self, env):
        import ssl
        _relay(env, tls="implicit")
        team, _ = _team_with_email()
        delivery.deliver_event(_event(), [team])
        ctx = env.smtp[0].context
        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname

    def test_a_relay_error_quoting_its_password_is_masked_in_the_log(self, env):
        _relay(env)
        team, _ = _team_with_email()
        env.smtp_fail[:] = [smtplib.SMTPAuthenticationError(535, f"bad {RELAY_PW}".encode())] * 3
        delivery.deliver_event(_event(), [team])
        logged = json.dumps(delivery.read_log()["rows"])
        assert RELAY_PW not in logged and "<redacted:notify-relay-password>" in logged

    def test_the_secrets_are_stored_by_reference_and_never_in_clear(self, env):
        team, dest = _team_with_webhook()
        _relay(env)
        store = (env.tmp / "notify_teams.json").read_text()
        creds = (env.tmp / "credential_profiles.json").read_text()
        for value in (HOOK_SECRET, RELAY_PW):
            assert value not in store and value not in creds
        held = teams.read()["teams"][team]["destinations"][dest]
        assert held["secret_ref"] == f"webhook/{dest}"
        assert credentials.get_notify_secret(f"webhook/{dest}") == HOOK_SECRET
        drawn = teams.public(held)
        assert drawn["secret_set"] is True and HOOK_SECRET not in json.dumps(drawn)
        assert "secret_ref" not in drawn and "code" not in drawn

    def test_a_stored_notification_secret_is_masked_by_value_everywhere(self, env):
        _relay(env)
        assert redact.redact_text(f"x {RELAY_PW} y") == "x <redacted:notify-relay-password> y"
        _team_with_webhook()
        assert HOOK_SECRET not in redact.redact_text(f"x {HOOK_SECRET} y")

    def test_removing_a_webhook_clears_its_secret(self, env):
        team, dest = _team_with_webhook()
        teams.remove_destination(team, dest, by="alex")
        assert not credentials.notify_secret_set(f"webhook/{dest}")

    def test_a_blank_secret_is_refused_never_an_erase(self, env):
        credentials.set_notify_secret("relay", RELAY_PW)
        with pytest.raises(ValueError, match="not empty"):
            credentials.set_notify_secret("relay", "")
        assert credentials.get_notify_secret("relay") == RELAY_PW
        with pytest.raises(ValueError, match="not relay or webhook"):
            credentials.set_notify_secret("../x", "y" * 20)


# ── Step 3: the generic signed webhook ────────────────────────────────────────────────────


class TestTheSignedWebhook:
    def test_the_post_is_signed_over_the_timestamp_and_the_exact_body(self, env):
        team, _ = _team_with_webhook()
        delivery.deliver_event(_event(), [team])
        post = env.posts[-1]
        h = post["headers"]
        assert post["allow_redirects"] is False and post["timeout"] == delivery.SEND_TIMEOUT_S
        assert h["Content-Type"] == "application/json" and h["X-Mercury-Event"] == "cant_fix"
        assert h["X-Mercury-Signature"].startswith("sha256=")
        now = int(h["X-Mercury-Timestamp"])
        assert webhook.verify(HOOK_SECRET, h["X-Mercury-Timestamp"], post["data"],
                              h["X-Mercury-Signature"], now=now) == (True, "")
        body = json.loads(post["data"])
        assert {k: body[k] for k in ("incident", "network", "device", "kind", "event")} == {
            "incident": "inc-0001", "network": "Default", "device": "r2",
            "kind": "ospf.interface", "event": "cant_fix"}
        assert body["steps"] == [{"what": "re-read r2", "result": "drift: 1 unit"}]
        assert body["link"].endswith("/v2/history?kind=notifications")

    def test_a_receiver_refuses_a_changed_body_another_timestamp_or_an_old_one(self):
        body = b'{"a":1}'
        sig = webhook.signature(HOOK_SECRET, "1000", body)
        assert webhook.verify(HOOK_SECRET, "1000", body, sig, now=1000)[0]
        assert not webhook.verify(HOOK_SECRET, "1000", b'{"a":2}', sig, now=1000)[0]
        assert not webhook.verify(HOOK_SECRET, "1001", body, sig, now=1001)[0]
        assert not webhook.verify("another-secret-of-length", "1000", body, sig, now=1000)[0]
        assert webhook.verify(HOOK_SECRET, "1000", body, sig, now=1300)[0]
        ok, why = webhook.verify(HOOK_SECRET, "1000", body, sig, now=1301)
        assert not ok and "300 s window" in why
        assert not webhook.verify(HOOK_SECRET, "1000", body, sig, now=699)[0]
        assert not webhook.verify(HOOK_SECRET, "10.5", body, sig, now=10)[0]

    def test_a_non_2xx_answer_is_a_failure_and_retried(self, env):
        team, _ = _team_with_webhook()
        env.post_status[:] = [500, requests.ConnectionError("reset"), 202]
        got = delivery.deliver_event(_event(), [team])
        assert got["sent"] == 1 and len(env.posts) == 3
        errors = [r["error"] for r in reversed(delivery.read_log()["rows"])]
        assert "HTTP 500" in errors[0] and "ConnectionError" in errors[1] and errors[2] == ""

    def test_a_webhook_whose_secret_is_gone_is_refused_and_not_posted(self, env):
        team, dest = _team_with_webhook()
        credentials.clear_notify_secret(f"webhook/{dest}")
        got = delivery.deliver_event(_event(), [team])
        assert got["deliveries"][0]["outcome"] == "refused" and env.posts == []

    def test_the_log_keeps_the_webhook_s_host_never_its_path(self, env):
        team, _ = _team_with_webhook(url="https://[2001:db8::10]:8443/hook/T0KEN")
        delivery.deliver_event(_event(), [team])
        assert env.posts[-1]["url"] == "https://[2001:db8::10]:8443/hook/T0KEN"
        assert delivery.read_log()["rows"][0]["recipient"] == "[2001:db8::10]"
        assert "T0KEN" not in (env.tmp / "notify_deliveries.jsonl").read_text()

    def test_only_the_generic_format_is_built(self, env):
        team = teams.add_team("x", by="alex")["team"]
        with pytest.raises(teams.Refused, match="later work"):
            teams.add_webhook(team, "https://hooks.example.com/", HOOK_SECRET, by="alex",
                              fmt="slack")

    def test_a_short_signing_secret_is_refused(self, env):
        team = teams.add_team("x", by="alex")["team"]
        with pytest.raises(teams.Refused, match="at least 16"):
            teams.add_webhook(team, "https://hooks.example.com/", "short", by="alex")


class TestAddresses:
    @pytest.mark.parametrize("url", ["https://hooks.example.com/x", "https://192.0.2.10/x",
                                     "https://[2001:db8::10]:8443/x", "http://127.0.0.1:9000/x",
                                     "http://[::1]:9000/x", "http://localhost/x"])
    def test_a_webhook_url_https_or_plain_to_loopback(self, url):
        assert addresses.check_webhook_url(url) == url

    @pytest.mark.parametrize("url,why", [
        ("http://192.0.2.10/x", "not this host's loopback"),
        ("http://[2001:db8::10]/x", "not this host's loopback"),
        ("http://hooks.example.com/x", "not this host's loopback"),
        ("https://user:pw@hooks.example.com/x", "no user or password"),
        ("ftp://hooks.example.com/x", "not an https URL"),
        ("https://hooks.example.com:99999/x", "is not a URL"),
        ("https://hooks.example.com/a b", "not one URL")])
    def test_a_webhook_url_refused_names_why(self, url, why):
        with pytest.raises(ValueError, match=why):
            addresses.check_webhook_url(url)

    @pytest.mark.parametrize("given,kept", [
        ("Ops@Example.COM", "Ops@example.com"), ("noc@[192.0.2.7]", "noc@[192.0.2.7]"),
        ("noc@[IPv6:2001:DB8::7]", "noc@[IPv6:2001:db8::7]")])
    def test_an_email_address_ipv4_and_ipv6_literals(self, given, kept):
        assert addresses.check_email(given) == kept

    @pytest.mark.parametrize("bad", ["a@example.com\r\nBcc: x@example.org",
                                     "a@example.com, c@example.org", "Name <a@example.com>",
                                     "noc@[2001:db8::7]", "noc@[IPv6:192.0.2.7]",
                                     "@example.com", "a@", "a@b"])
    def test_anything_but_one_address_is_refused(self, bad):
        with pytest.raises(ValueError):
            addresses.check_email(bad)

    @pytest.mark.parametrize("host,loop", [("127.0.0.1", True), ("127.9.9.9", True),
                                           ("::1", True), ("[::1]", True),
                                           ("localhost", True), ("192.0.2.1", False),
                                           ("2001:db8::1", False), ("loopback.example", False)])
    def test_loopback(self, host, loop):
        assert addresses.is_loopback(host) is loop


# ── Step 4: verification codes ────────────────────────────────────────────────────────────


class TestVerificationCodes:
    def test_an_unverified_destination_cannot_be_turned_on(self, env):
        team, dest = _team_with_email(verified=False)
        with pytest.raises(teams.Refused, match="not verified"):
            teams.set_enabled(team, dest, True, by="alex")

    def test_a_code_sent_by_email_verifies_and_is_kept_nowhere(self, env):
        import re
        _relay(env)
        team, dest = _team_with_email(verified=False)
        got = delivery.send_code(team, dest, by="alex")
        assert got["ok"] and got["expires_in_s"] == teams.CODE_TTL_S and "code" not in got
        body = _mail(env.smtp[0].sent[0]).get_content()
        code = re.search(r"Mercury verification code: (\d{6})", body).group(1)
        for name in ("notify_teams.json", "notify_deliveries.jsonl"):
            assert code not in (env.tmp / name).read_text(), name
        assert delivery.read_log()["rows"][0]["event"] == "verification"
        assert delivery.confirm_code(team, dest, code, by="alex")["ok"]
        held = teams.read()["teams"][team]["destinations"][dest]
        assert held["verified_by"] == "alex" and "code" not in held
        assert teams.set_enabled(team, dest, True, by="alex")["enabled"]

    def test_a_code_reaches_a_webhook_in_its_signed_body(self, env):
        team, dest = _team_with_webhook(verified=False)
        assert delivery.send_code(team, dest, by="alex")["ok"]
        post = env.posts[-1]
        assert post["headers"]["X-Mercury-Event"] == "verification"
        code = json.loads(post["data"])["outcome"].rsplit(" ", 1)[1]
        assert len(code) == teams.CODE_DIGITS and code.isdigit()
        assert teams.confirm_code(team, dest, code, by="alex")["ok"]

    def test_a_wrong_code_spends_a_try_and_the_last_try_spends_the_code(self, env):
        team, dest = _team_with_email(verified=False)
        code = teams.issue_code(team, dest, by="alex")
        wrong = "000000" if code != "000000" else "111111"
        for left in range(teams.CODE_TRIES - 1, 0, -1):
            assert teams.confirm_code(team, dest, wrong, by="alex")["error"] == \
                f"the code was wrong: {left} tries left"
        assert "no tries are left" in teams.confirm_code(team, dest, wrong, by="alex")["error"]
        assert "no code is waiting" in teams.confirm_code(team, dest, code, by="alex")["error"]

    def test_an_expired_code_is_refused_naming_both_times(self, env):
        team, dest = _team_with_email(verified=False)
        code = teams.issue_code(team, dest, by="alex", now=1000)
        got = teams.confirm_code(team, dest, code, by="alex", now=1000 + teams.CODE_TTL_S + 1)
        assert not got["ok"] and "expired at 1970-01-01T00:31:40Z" in got["error"]
        assert teams.confirm_code(team, dest, code, by="alex", now=1001)["error"].startswith(
            "no code is waiting")

    def test_a_code_in_time_verifies_with_spaces_typed(self, env):
        team, dest = _team_with_email(verified=False)
        code = teams.issue_code(team, dest, by="alex", now=1000)
        typed = f" {code[:3]} {code[3:]} "
        assert teams.confirm_code(team, dest, typed, by="alex", now=1000 + 60)["ok"]

    def test_a_new_code_replaces_the_last(self, env):
        team, dest = _team_with_email(verified=False)
        first = teams.issue_code(team, dest, by="alex")
        second = teams.issue_code(team, dest, by="alex")
        if first != second:
            assert not teams.confirm_code(team, dest, first, by="alex")["ok"]
        assert teams.confirm_code(team, dest, second, by="alex")["ok"]

    def test_the_code_survives_the_egress_mask(self):
        assert message.mask("Mercury verification code: 123456") == \
            "Mercury verification code: 123456"


class TestTheTeamsStore:
    def test_a_duplicate_team_or_destination_is_refused(self, env):
        team, _ = _team_with_email(verified=False)
        with pytest.raises(teams.Refused, match="exists"):
            teams.add_team("network OPS", by="alex")
        with pytest.raises(teams.Refused, match="already has"):
            teams.add_email(team, "OPS@example.com", by="alex")

    def test_an_unreadable_store_refuses_writes(self, env):
        from modules import filestore
        (env.tmp / "notify_teams.json").write_text("{not json")
        with pytest.raises(filestore.StoreUnreadable):
            teams.add_team("x", by="alex")
        got = delivery.deliver_event(_event(), ["abc"])
        assert not got["ok"] and "could not be read" in got["error"] and env.smtp == []

    def test_a_removed_team_named_receives_nothing(self, env):
        assert teams.deliverable(["0123456789ab"]) == []
