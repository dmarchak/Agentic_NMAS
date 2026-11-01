"""C2031: a secret a person typed is replaced in the store by the form the device made of it.

Intent compares a `username` line by its text, and a device re-hashes a typed secret with a salt
of its own, so the Intent check would differ for good after any typed account (and refuse every
later deploy to the device). A rotation already stores the device's own hash for the managed
account (`credential_rotation._commit`); `capture_typed_secrets` does the same for every
account intent holds with a typed value, from the configuration captured after a verified
deploy (the pipeline's stage 8.5). The values here are made up: no real secret or hash.
"""

import json

import pytest

from modules import credentials
from modules.nsot import credential_rotation as CR

LIST, HOST = "Default", "r2"
IP = "192.0.2.11"
TYPED = "Typed-Not-Real-1"
DEVICE_FORM = "9 $9$NotRealSalt$NotRealHashValueForTestsOnly"
INTENT = {"users": [{"name": "lab", "privilege": 15, "secret_kind": "secret",
                     "secret_ref": "user_lab_secret"},
                    {"name": "admin", "privilege": 15, "secret_kind": "secret",
                     "secret_ref": "user_admin_secret"}]}


@pytest.fixture(autouse=True)
def _own_store(tmp_path, monkeypatch):
    """Each test's own credential store: a value set here never reaches another test (where the
    masking would treat it as a known secret)."""
    monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "credential_profiles.json"))


def _key(ref):
    return credentials.template_secret_key(LIST, HOST, ref)


def _running(lab_line):
    return ("hostname r2\n" + (lab_line + "\n" if lab_line else "")
            + "username admin privilege 15 secret 9 $9$AdminSalt$AdminNotReal\n")


def test_a_typed_secret_is_replaced_by_the_device_s_own_form():
    credentials.set_template_secret(_key("user_lab_secret"), TYPED, "plaintext", list_name=LIST)
    got = CR.capture_typed_secrets(LIST, HOST, INTENT,
                                   _running(f"username lab privilege 15 secret {DEVICE_FORM}"))
    assert got == [{"account": "lab", "ref": "user_lab_secret", "captured": True, "why": ""}]
    assert credentials.get_template_secret(_key("user_lab_secret")) == DEVICE_FORM
    assert credentials.template_secret_kind(_key("user_lab_secret")) == "hash"


def test_a_rotation_s_hash_is_left_as_it_is():
    credentials.set_template_secret(_key("user_admin_secret"), "9 $9$Kept$KeptNotReal", "hash",
                                    list_name=LIST)
    assert CR.capture_typed_secrets(LIST, HOST, INTENT, _running("")) == []
    assert credentials.get_template_secret(_key("user_admin_secret")) == "9 $9$Kept$KeptNotReal"


@pytest.mark.parametrize("line,why", [
    ("", "the device holds no line for it"),
    (f"username lab privilege 15 secret 0 {TYPED}", "is not in a form it produced"),
], ids=["absent", "type-0"])
def test_nothing_is_captured_unless_the_device_made_the_value(line, why):
    credentials.set_template_secret(_key("user_lab_secret"), TYPED, "plaintext", list_name=LIST)
    (got,) = CR.capture_typed_secrets(LIST, HOST, INTENT, _running(line))
    assert got["captured"] is False and why in got["why"]
    assert credentials.get_template_secret(_key("user_lab_secret")) == TYPED
    assert credentials.template_secret_kind(_key("user_lab_secret")) == "plaintext"


def test_no_value_is_returned_or_logged(caplog):
    caplog.set_level("DEBUG")
    credentials.set_template_secret(_key("user_lab_secret"), TYPED, "plaintext", list_name=LIST)
    got = CR.capture_typed_secrets(LIST, HOST, INTENT,
                                   _running(f"username lab privilege 15 secret {DEVICE_FORM}"))
    said = json.dumps(got) + caplog.text
    assert TYPED not in said and "NotRealHash" not in said


class TestThePipelineCapturesOnlyWhatDeployedAndVerified:
    """Stage 8.5 runs after verify and skips a rolled-back or failed device; the capture rides
    the same loop, so it happens for exactly the devices whose golden is recorded."""

    def _ctx(self, **kw):
        from tests.test_pipeline import _ctx
        ctx = _ctx(device_ips=[IP], selected_devices=[{"ip": IP, "hostname": "R1"}], **kw)
        ctx.post_snapshots = {IP: {"running_config": "hostname R1\n"}}
        return ctx

    def test_a_verified_device_is_captured(self, monkeypatch):
        from modules import pipeline as P
        from modules.nsot import repo
        seen = []
        monkeypatch.setattr(P, "_capture_typed_secrets",
                            lambda ctx, repo, host, running: seen.append((host, running)))
        # The stage parks each capture on disk for a crashed batch; not this test's subject.
        monkeypatch.setattr(repo, "stage_post_deploy", lambda *a, **k: None)
        ctx = self._ctx()
        ctx.defer_golden = True
        P._stage_save_golden(ctx)
        assert seen == [("R1", "hostname R1\n")]

    @pytest.mark.parametrize("field", ["rolled_back_ips", "deploy_failures"])
    def test_a_rolled_back_or_failed_device_is_not(self, monkeypatch, field):
        from modules import pipeline as P
        monkeypatch.setattr(P, "_capture_typed_secrets",
                            lambda *a, **k: pytest.fail("captured for a device not verified"))
        ctx = self._ctx()
        setattr(ctx, field, [IP] if field == "rolled_back_ips" else [{"ip": IP, "reason": "x"}])
        P._stage_save_golden(ctx)

    def test_a_failure_is_said_never_raised(self, monkeypatch):
        from modules import pipeline as P
        from modules.nsot import hostvars
        monkeypatch.setattr(hostvars, "committed_at_head",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("planted")))
        ctx = self._ctx()
        P._capture_typed_secrets(ctx, "/nonexistent", "R1", "hostname R1\n")
        assert ctx.secrets_captured["R1"] == [{"captured": False,
                                               "why": "not captured (OSError)"}]
