"""C154 (R1, 2026-09-28): Deploy Plan on an onboarded device answered
"An unexpected error occurred. Please check the logs."

Two defects, one screen:
- the plan treated "committed intent exists" as "a model exists". probe-r1a's
  committed intent is only onboarding's bootstrap (C148), so the plan RENDERED
  it and the template raised `UndefinedError: 'dict object' has no attribute
  'services'` (measured in the host's app log);
- the shared exception handler answered every such crash with that one
  sentence, carried the real reason as `detail`, and nothing drew `detail`.
"""

import pytest

#: probe-r1a's committed intent, as the host holds it (its top-level keys).
BOOTSTRAP_ONLY = {"bootstrap": {"source": "static"}, "hostname": "probe-r1a",
                  "logging": {}, "secret_refs": ["user_admin_password"], "unmodeled": []}
CAPTURE = ("hostname probe-r1a\n"
           "username admin privilege 15 secret 9 $9$abcdefghijklmnop\n"
           "interface GigabitEthernet2\n ip address 10.255.0.33 255.255.255.0\nend\n")


def test_the_rule_matches_the_measured_shapes():
    from modules.nsot.hostvars import is_bootstrap_only

    assert is_bootstrap_only(BOOTSTRAP_ONLY)
    assert not is_bootstrap_only({"hostname": "r1", "interfaces": [], "routing": {}})
    assert not is_bootstrap_only(None)


@pytest.fixture
def planned(monkeypatch):
    """The REAL `_artifact_for`, only its storage reads stubbed, rendering
    through the real packaged template (where the host's crash came from)."""
    import routes.deploy as rd
    from modules.nsot import approval, hostvars, templates_repo

    monkeypatch.setattr(rd, "_repo_for", lambda ln: "/nonexistent")
    monkeypatch.setattr(rd, "_captured_record",
                        lambda repo, h: {"text": CAPTURE, "refused": ""})
    # The plan reads the list's OWN inventory (C215).
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [
        {"hostname": "probe-r1a", "ip": "10.255.0.33", "platform": "cisco_iosxe"}])
    monkeypatch.setattr(templates_repo, "template_for_device",
                        lambda repo, h, p: "cisco_iosxe/base.j2")
    monkeypatch.setattr(templates_repo, "templates_dir", lambda repo: "")
    monkeypatch.setattr(approval, "is_approved", lambda repo, t: True)
    monkeypatch.setattr(hostvars, "rolled_back_note", lambda *a, **k: None)
    monkeypatch.setattr(hostvars, "read_committed", lambda repo, h: dict(BOOTSTRAP_ONLY))
    return rd


def test_a_bootstrap_only_intent_is_refused_with_its_reason_not_rendered(planned):
    from modules.nsot.hostvars import BOOTSTRAP_ONLY_REASON

    (artifact, _captured, _device), err = planned._artifact_for("probe-r1", "probe-r1a")
    assert err == ""
    assert artifact.bootstrap and not artifact.deployable
    assert BOOTSTRAP_ONLY_REASON in artifact.blocking_reasons, artifact.blocking_reasons
    assert "Seed intent" in BOOTSTRAP_ONLY_REASON and "Device page" in BOOTSTRAP_ONLY_REASON


def test_the_shared_handler_names_what_was_attempted_and_what_failed():
    """Every route behind the global handler, at once. The planted
    credential stays masked (it goes out over HTTP), and an exception with
    no message still says what it was."""
    import app as nmas
    from cryptography.fernet import InvalidToken

    with nmas.app.test_request_context("/deploy/plan", method="POST",
                                       headers={"Accept": "application/json"}):
        body, status = nmas.handle_exception(
            ValueError("bad line: username admin secret 0 Hunter2Secret"))
        err = body.get_json()["error"]
        assert status == 500
        assert err.startswith("POST /deploy/plan failed with an unexpected error: ValueError"), err
        assert "Hunter2Secret" not in err and "check the logs" not in err
        body, _ = nmas.handle_exception(InvalidToken())
        assert body.get_json()["error"].endswith(": InvalidToken")
