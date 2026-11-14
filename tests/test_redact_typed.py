"""What a person types is masked by its clause's shape (C2340; `redact.redact_typed`).

The egress shapes took the one word after "password" or "secret" as its value, so prose sent
the value: "the password is X" went out as "the password <redacted> X" (measured 2026-11-03 by
P7's case builder: 15 of 18 prose shapes sent their value). `redact_typed` masks, after a
secret word and up to its clause's end, the value's slots and every credential-shaped token,
and leaves a pasted configuration line's other words, an address and a URL's own mask alone.
The values here are invented.
"""
import pytest

from modules import redact

V = "Wk7pQ2zR9vLx"


@pytest.mark.parametrize("typed", [
    f"set the lab account's password to {V}",
    f"the password is {V}",
    "the password is hunter",
    f"password: {V}",
    f"password:{V}",
    f"password={V}",
    f"password = {V}",
    f"the enable secret is {V}",
    f"secret: {V}",
    f"my password was {V} yesterday",
    f"passwd {V}",
    f"pwd {V}",
    f"pw {V}",
    f"the password for r2 is {V}",
    "the password for r2 is hunter",
    f"passphrase {V}",
    f"api key {V}",
    f"api-key={V}",
    f"token {V}",
    f"token={V}",
    f"snmp community is {V}, read only",
    f"PASSWORD IS {V}",
    # In no value slot: masked by its shape alone (letters with digits).
    f"my password for the lab account was changed yesterday from {V}",
])
def test_a_secret_written_in_prose_never_leaves(typed):
    out = redact.redact_typed(typed, values={})
    secret = "hunter" if "hunter" in typed else V
    assert secret not in out, out
    assert "<redacted:" in out


def test_the_shapes_the_egress_mask_alone_let_through_are_measured():
    """The premise, kept: these prose shapes leave `redact_egress` with their value; it is
    the reason `redact_typed` exists (if the egress mask learns them, this says so). It learned
    `password: <x>` on 2026-11-14 (`egress_labelled`, show output's own label form: Tier 1's
    review of the AI's reads), so that one is masked now and the other four still leave."""
    leaked = [s for s in (f"the password is {V}", f"passwd {V}",
                          f"api key {V}", f"the password for r2 is {V}")
              if V in redact.redact_egress(s, values={})]
    assert len(leaked) == 4, leaked
    assert V not in redact.redact_egress(f"password: {V}", values={})


@pytest.mark.parametrize("line,kept", [
    (f"snmp-server community {V} RO", " RO"),
    ("neighbor 192.0.2.2 password 7 0822455D0A16", "password 7 "),
    ("neighbor 2001:db8::2 password 7 0822455D0A16", "neighbor 2001:db8::2 password 7 "),
    ("username admin privilege 15 secret 9 $9$abcdefghijklmn$opqrstuvwxyz0123456789", "secret 9 "),
])
def test_a_pasted_configuration_line_keeps_its_other_words(line, kept):
    out = redact.redact_typed(line, values={})
    assert kept in out, out
    assert "typed_secret" not in out, out


@pytest.mark.parametrize("address", ["192.0.2.9", "2001:db8::9", "[2001:db8::9]"])
def test_an_address_after_a_secret_word_is_kept(address):
    out = redact.redact_typed(f"the secret at {address} is unchanged", values={})
    assert address in out, out


def test_a_url_s_user_part_is_the_egress_mask_s_whole():
    planted = "fatal: https://x-access-token:SeCrEt-Tok3n@example.invalid/o/r.git denied"
    out = redact.redact_typed(planted, values={})
    assert "SeCrEt-Tok3n" not in out and "x-access-token" not in out
    assert "<redacted:url_userinfo>" in out, out


@pytest.mark.parametrize("prose", [
    "no service password-encryption on r2",
    "rotate the passwords next week",
    "the token bucket rate is 10 kbps",
])
def test_a_word_only_like_a_secret_word_masks_little(prose):
    """A hyphenated word is not a secret word; plain prose after one loses at most its first
    value slot, never the clause's other plain words."""
    out = redact.redact_typed(prose, values={})
    assert out == prose or out.count("<redacted:") <= 2, out


def test_it_is_idempotent_and_ends_its_clause():
    for s in (f"the password is {V}, and r2 answers on 192.0.2.1.",
              f"password: {V}; the rest stays", f"the password for r2 is {V}"):
        once = redact.redact_typed(s, values={})
        assert redact.redact_typed(once, values={}) == once
    out = redact.redact_typed(f"the password is {V}, and the uplink is Gi0/1.", values={})
    assert out.endswith(", and the uplink is Gi0/1."), out


def test_a_commit_message_never_keeps_a_prose_secret():
    """A typed commit line is pushed to the list's remote and never rewritten."""
    from modules.nsot import repo
    out = repo.masked_message(f"Why: set the lab account's password to {V}\n\nSource: test")
    assert V not in out and out.endswith("\n\nSource: test"), out


def test_the_assistant_s_gap_record_never_keeps_a_prose_secret(monkeypatch, tmp_path):
    from modules.ai import assistant
    monkeypatch.setattr(assistant, "_gaps_path", lambda: str(tmp_path / "manual_gaps.jsonl"))
    row = assistant.record_gap(f"why is the password for r2 is {V} refused", screen="",
                               state="not_covered", actor="evaluation:test")
    assert V not in row["question"]
    assert V not in (tmp_path / "manual_gaps.jsonl").read_text()


def test_the_typed_paths_use_it():
    """Each place a person's typed words leave the host or are pushed masks them with
    `redact_typed`: the gateway's typed parts, the assistant's ranking and gap record, a
    commit message, and the two boxes that draw a masked question back."""
    import inspect

    from modules.ai import assistant, gateway
    from modules.nsot import repo
    from routes import intent_v2, v2
    assert "redact.redact_typed(" in inspect.getsource(gateway.mask_typed)
    assert "redact.redact_typed(" in inspect.getsource(repo.masked_message)
    assert inspect.getsource(assistant).count("redact.redact_typed(") == 2
    assert "redact.redact_typed(" in inspect.getsource(intent_v2)
    assert "redact.redact_typed(" in inspect.getsource(v2)
