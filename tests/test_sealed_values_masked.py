"""C1685 (the operator, 2026-10-25): a sealed value is a secret's own form, so the mask hides
it as it hides the clear one. A raw host read of the settings file printed the Anthropic
key's `enc:v1:` Fernet token whole; `redact_positional` (and so `redact_text`,
`redact_egress` and every surface built on them) now masks a sealed value by its shape:

- `enc:v1:<token>` keeps its prefix (the line still says it holds a sealed value);
- a bare Fernet token (an inventory's encrypted credential column) is masked whole;
- masking twice changes nothing; a short look-alike is not a token.
"""
from cryptography.fernet import Fernet

from modules import redact


def _token(n=1):
    return Fernet(Fernet.generate_key()).encrypt(b"x" * n).decode()


def test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token():
    t = _token(40)
    line = f'  "anthropic_api_key": "enc:v1:{t}",'
    out = redact.redact_positional(line)
    assert t not in out and out == '  "anthropic_api_key": "enc:v1:<redacted:sealed>",'


def test_the_shortest_bare_fernet_token_is_masked_whole():
    t = _token(1)
    assert len(t) == 100, len(t)
    assert redact.redact_positional(f"r1,{t},ok") == "r1,<redacted:sealed>,ok"


def test_masking_twice_changes_nothing_and_a_look_alike_is_left():
    once = redact.redact_positional(f"x enc:v1:{_token()} y {_token()}")
    assert redact.redact_positional(once) == once
    assert redact.redact_positional("commit gAAAAAbcdef is short") == "commit gAAAAAbcdef is short"


def test_the_egress_mask_hides_a_sealed_value_too():
    t = _token(8)
    sent = redact.egress_payload({"messages": [{"content": f"the key is enc:v1:{t}"}]},
                                 values={})
    assert t not in str(sent) and "enc:v1:<redacted:sealed>" in str(sent)
