"""Settings › Installation's Replace… (`installation_settings.replace_secret`), the irreversible
tier's write path for a card's secret (docs/TESTING.md, "The deploy bar"), held to its contract
step by step: the check, the token id's form, the id written as the person, the secret sealed,
the record of names, the Test as the person, and each refusal's words naming what it compared.
Its collaborators are replaced by recorders, so each step is seen: what was written, with whom,
and what was returned. Written from tier run #63's survivors in this function (2026-10-25).
"""
import pytest

from modules import installation_settings as I

TOKEN_ID = "mercury@pve!Mercury-RO_1.x"


@pytest.fixture
def seen(monkeypatch):
    log = {"settings": [], "secrets": [], "records": [], "tests": [], "write_ok": True,
           "secret_ok": True}

    def write_settings(values, actor=None):
        log["settings"].append((values, actor))
        return {"ok": log["write_ok"], "error": "the settings file is locked by another write"}

    def set_secret(key, value):
        log["secrets"].append((key, value))
        return log["secret_ok"]

    def record(entry):
        log["records"].append(entry)
        return dict(entry, recorded=True)

    def test_card(name, client=None, actor=""):
        log["tests"].append((name, client, actor))
        return {"state": "answering"}

    monkeypatch.setattr("modules.settings_schema.write_settings", write_settings)
    monkeypatch.setattr("modules.secrets_store.set_secret", set_secret)
    monkeypatch.setattr(I, "_record", record)
    monkeypatch.setattr(I, "test_card", test_card)
    return log


def _refusal(name, form, **kw):
    with pytest.raises(I.Refused) as got:
        I.replace_secret(name, form, "operator@example.com", "assertion", **kw)
    return str(got.value)


def test_a_card_with_no_secret_refuses_naming_it(seen):
    assert _refusal("author", {}) == "Commit author holds no secret"
    assert seen["secrets"] == [] and seen["settings"] == []


@pytest.mark.parametrize("value", ["", "   ", "two words", "tab\there", "café"])
def test_an_empty_or_spaced_or_non_ascii_secret_refuses_with_its_words(seen, value):
    assert _refusal("ai", {"anthropic_api_key": value}) == (
        "the new api key is empty or holds a space or a character a token never has; nothing "
        "was replaced")
    assert seen["secrets"] == [] and seen["records"] == []


def test_a_token_id_not_of_its_form_refuses_naming_it(seen):
    assert _refusal("proxmox", {"proxmox_token_secret": "s3cr3t-value",
                                "proxmox_token_id": ""}) == (
        "Token id '' is not a Proxmox token id (user@realm!name); nothing was replaced")
    assert seen["settings"] == [] and seen["secrets"] == []


def test_the_id_is_written_as_the_person_then_the_secret_sealed(seen):
    out = I.replace_secret("proxmox", {"proxmox_token_secret": "s3cr3t-value",
                                       "proxmox_token_id": TOKEN_ID},
                           "operator@example.com", "assertion", client="CLIENT")
    assert seen["settings"] == [({"proxmox_token_id": TOKEN_ID}, "operator@example.com")]
    assert seen["secrets"] == [("proxmox_token_secret", "s3cr3t-value")]
    assert out["ok"] is True and out["tested"] == {"state": "answering"}
    assert out["recorded"] is True and out["fields"] == ["proxmox_token_id",
                                                         "proxmox_token_secret"]


def test_an_id_write_the_settings_refuse_is_said_in_their_words(seen):
    seen["write_ok"] = False
    assert _refusal("proxmox", {"proxmox_token_secret": "s3cr3t-value",
                                "proxmox_token_id": TOKEN_ID}) == \
        "the settings file is locked by another write"
    assert seen["secrets"] == []


@pytest.mark.parametrize("card,form,words", [
    ("ai", {"anthropic_api_key": "sk-new-value"},
     "the secrets store refused the new api key; nothing was replaced"),
    ("proxmox", {"proxmox_token_secret": "s3cr3t-value", "proxmox_token_id": TOKEN_ID},
     "the secrets store refused the new token secret; its id was written, the secret was "
     "not"),
])
def test_a_secret_the_store_refuses_says_what_was_and_was_not_written(seen, card, form, words):
    seen["secret_ok"] = False
    assert _refusal(card, form) == words
    assert seen["records"] == [] and seen["tests"] == []


def test_the_record_names_the_person_and_the_fields_never_the_value(seen):
    I.replace_secret("ai", {"anthropic_api_key": "sk-new-value"}, "operator@example.com",
                     "assertion")
    (entry,) = seen["records"]
    assert entry == {"kind": "card_replace", "card": "ai", "actor": "operator@example.com",
                     "actor_verified": "assertion", "fields": ["anthropic_api_key"]}
    assert "sk-new-value" not in repr(entry)


def test_the_test_runs_as_the_person_on_the_client_given(seen):
    out = I.replace_secret("ai", {"anthropic_api_key": "sk-new-value"},
                           "operator@example.com", "assertion", client="CLIENT")
    assert seen["tests"] == [("ai", "CLIENT", "operator@example.com")]
    assert out["ok"] is True and out["card"] == "ai" and out["kind"] == "card_replace"
