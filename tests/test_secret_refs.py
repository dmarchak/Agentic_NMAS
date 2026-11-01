"""C235 (board H-S, approved 2026-11-01): the secret references a device's committed intent names,
and setting a value for one, write-only.

The world is the intent editor's (tests/test_intent_editor.py `world`: the network `lab`, s4's
committed intent); s4's intent gains an account `lab` here. Values are made up.
"""

import json
import logging
import subprocess

import pytest

from modules import credentials
from modules.nsot import secret_refs as SR
from tests.test_intent_editor import world  # noqa: F401 - the fixture

TYPED = "Lab-Not-Real-7"
INTENT = {"users": [{"name": "nmas", "privilege": 15, "secret_ref": "user_nmas_secret"},
                    {"name": "lab", "privilege": 15, "secret_ref": "user_lab_secret"}],
          "secret_refs": ["snmp_community_ro"]}


@pytest.fixture
def intent(tmp_path, monkeypatch):
    """s4's intent as INTENT, and the test's own credential store."""
    monkeypatch.setattr(SR, "_intent", lambda list_name, host: INTENT)
    monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "credential_profiles.json"))
    return INTENT


def _key(ref):
    return credentials.template_secret_key("lab", "s4", ref)


def test_the_listing_names_each_reference_and_its_state_never_a_value(world, intent):  # noqa: F811
    credentials.set_template_secret(_key("user_nmas_secret"), "9 $9$S$NotReal", "hash",
                                    list_name="lab")
    got = SR.listing("lab", "s4", signs_in_as="nmas")
    rows = {r["ref"]: r for r in got["refs"]}
    assert rows["user_nmas_secret"]["state"] == "device_form"
    assert rows["user_nmas_secret"]["settable"] is False
    assert "changes by Rotate only" in rows["user_nmas_secret"]["why_not"]
    assert rows["user_lab_secret"]["state"] == "none"
    assert rows["user_lab_secret"]["for"] == "account lab, privilege 15"
    assert rows["snmp_community_ro"]["state"] == "none"
    assert got["counts"] == {"device_form": 1, "typed": 0, "held": 0, "none": 2}
    assert "NotReal" not in json.dumps(got)


def test_a_value_is_stored_typed_and_its_set_recorded_and_committed_without_it(
        world, intent, monkeypatch):  # noqa: F811
    # A handler of the test's own, put on the list directly: `Logger.addHandler` gives every
    # handler the masking filter (redact.py), which masks a stored value, so caplog would pass a
    # module that logged it. This asks what the module says, not what the net catches.
    said = []
    raw = logging.Handler()
    raw.emit = lambda record: said.append(record.getMessage())
    monkeypatch.setattr(SR.log, "handlers", SR.log.handlers + [raw])
    monkeypatch.setattr(SR.log, "level", logging.DEBUG)
    got = SR.set_value("lab", "s4", "user_lab_secret", TYPED, TYPED,
                       "Blind runs: the temporary lab account", actor="op@example.invalid",
                       signs_in_as="nmas")
    assert got["ok"] and got["record"]["ok"] and got["record"]["commit"], got
    assert credentials.get_template_secret(_key("user_lab_secret")) == TYPED
    assert credentials.template_secret_kind(_key("user_lab_secret")) == "plaintext"
    assert SR.listing("lab", "s4")["counts"]["typed"] == 1
    repo = SR._repo("lab")
    shown = subprocess.run(["git", "-C", repo, "show", "HEAD"], capture_output=True,
                           text=True, check=True).stdout
    assert "A value set for user_lab_secret on s4" in shown
    assert "Actor: op@example.invalid" in shown
    assert said and "user_lab_secret" in said[-1]
    assert TYPED not in shown and TYPED not in json.dumps(got) and TYPED not in "\n".join(said)


@pytest.mark.parametrize("ref,value,again,reason,failing", [
    ("user_lab_secret", TYPED, "Other-1", "why", "the two match"),
    ("user_lab_secret", "has space", "has space", "why", "one token a CLI accepts"),
    ("user_lab_secret", "", "", "why", "the two match"),
    ("user_ghost_secret", TYPED, TYPED, "why", "named in intent"),
    ("user_nmas_secret", TYPED, TYPED, "why", "not Mercury's own account"),
    ("user_lab_secret", TYPED, TYPED, "  ", "a reason"),
], ids=["differ", "space", "empty", "not-named", "managed", "no-reason"])
def test_each_check_refuses_by_name_and_nothing_is_stored(world, intent, ref, value,  # noqa: F811
                                                          again, reason, failing):
    with pytest.raises(SR.Refused) as exc:
        SR.set_value("lab", "s4", ref, value, again, reason, actor="op@example.invalid",
                     signs_in_as="nmas")
    assert f"{failing}:" in str(exc.value) and "Nothing was written" in str(exc.value)
    assert credentials.template_secret_kind(_key(ref)) == ""
    if value:
        assert value not in str(exc.value)
