"""C2299 (board FC phase 2 (a), PHASE8_PLAN 22.2): a device's Secret references read its committed
intent with the committed intent layers it takes merged under it, so a reference a layer names is
listed, settable and resolved as the device's own are.

The world is the intent editor's (tests/test_intent_editor.py `world`: the network `lab`, s4's
committed intent in a real repository), with a layer committed into it and s4's inventory row
given its tags. Values are made up.

- **No layer:** the listing is s4's own references, and the inventory is not read for it.
- **A tag layer s4 carries** naming `user_lab_secret`: listed with what it is for, and Set
  value… stores it for s4.
- **A tag s4 does not carry:** its reference is not listed, and setting it is refused by name.
- **Two tags disagreeing:** Set value… is refused naming the merge, and nothing is stored.
"""

import os
import subprocess

import pytest
import yaml

from modules import credentials
from modules.nsot import secret_refs as SR
from tests.test_intent_editor import world  # noqa: F401 - the fixture

TYPED = "Lab-Not-Real-7"
LAB = {"users": [{"name": "lab", "privilege": 15, "secret_kind": "secret",
                  "secret_ref": "user_lab_secret"}]}


def _commit_layer(name, doc):
    repo = SR._repo("lab")
    os.makedirs(os.path.join(repo, "layers"), exist_ok=True)
    with open(os.path.join(repo, "layers", name), "w", encoding="utf-8") as fh:
        fh.write(yaml.safe_dump(doc))
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    for args in (("add", "--", f"layers/{name}"), ("commit", "-q", "-m", f"layer {name}")):
        subprocess.run(["git", "-C", repo, *args], check=True, env=env, capture_output=True)


@pytest.fixture
def s4(world, tmp_path, monkeypatch):  # noqa: F811
    """s4's row tagged blind-lab (every read counted), and the test's own credential store."""
    monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "credential_profiles.json"))
    got = {"tags": ["blind-lab"], "asked": 0}

    def row_of(list_name, host):
        got["asked"] += 1
        return {"hostname": host, "_tags": list(got["tags"])}
    monkeypatch.setattr("modules.nsot.profile._row_of", row_of)
    return got


def _key(ref):
    return credentials.template_secret_key("lab", "s4", ref)


def test_no_layer_lists_the_devices_own_and_reads_no_inventory(s4):
    refs = {r["ref"] for r in SR.listing("lab", "s4")["refs"]}
    assert "user_lab_secret" not in refs
    assert s4["asked"] == 0, "a network with no layer reads no inventory for the card"


def test_a_device_with_no_committed_intent_takes_no_layers_reference(s4):
    """s9 is in the inventory with no committed intent: nothing renders for it, so a layer
    names nothing for it to hold."""
    _commit_layer("tag-blind-lab.yml", LAB)
    assert SR.listing("lab", "s9")["refs"] == []


def test_a_tag_layers_reference_is_listed_and_set_for_the_device(s4):
    _commit_layer("tag-blind-lab.yml", LAB)
    rows = {r["ref"]: r for r in SR.listing("lab", "s4")["refs"]}
    assert rows["user_lab_secret"]["for"] == "account lab, privilege 15"
    assert rows["user_lab_secret"]["state"] == "none" and rows["user_lab_secret"]["settable"]
    got = SR.set_value("lab", "s4", "user_lab_secret", TYPED, TYPED,
                       "Blind runs: the temporary lab account", actor="op@example.invalid")
    assert got["ok"], got
    assert credentials.get_template_secret(_key("user_lab_secret")) == TYPED


def test_a_tag_the_device_does_not_carry_names_nothing_for_it(s4):
    s4["tags"] = []
    _commit_layer("tag-blind-lab.yml", LAB)
    assert "user_lab_secret" not in {r["ref"] for r in SR.listing("lab", "s4")["refs"]}
    with pytest.raises(SR.Refused) as exc:
        SR.set_value("lab", "s4", "user_lab_secret", TYPED, TYPED, "why",
                     actor="op@example.invalid")
    assert "named in intent" in str(exc.value)
    assert not credentials.get_template_secret(_key("user_lab_secret")), "nothing stored"


def test_two_tags_disagreeing_refuse_the_set_by_name_and_store_nothing(s4):
    s4["tags"] = ["blind-lab", "other"]
    _commit_layer("tag-blind-lab.yml", {"banner_motd": "a", **LAB})
    _commit_layer("tag-other.yml", {"banner_motd": "b"})
    with pytest.raises(SR.Refused) as exc:
        SR.set_value("lab", "s4", "user_lab_secret", TYPED, TYPED, "why",
                     actor="op@example.invalid")
    assert "cannot be merged" in str(exc.value) and "banner_motd" in str(exc.value)
    assert "Nothing was written" in str(exc.value)
    assert not credentials.get_template_secret(_key("user_lab_secret")), "nothing stored"
