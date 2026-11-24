"""C3886 (the operator's ruling of 2026-11-23): the reads engine's placeholder carries a short
keyed fingerprint of the secret (`redact.KEYED_PLACEHOLDER`), so two answers compared tell
different secrets apart, and the secret is never shown. Every other caller keeps the plain
placeholder."""
import re

from modules import redact

LINE = "snmp-server community {} RO\nusername admin privilege 15 secret 9 {}\n"
KEYED = re.compile(r"<redacted:([a-z_]+):([0-9a-f]{8})>")


def _keyed(text, values=None):
    return redact.redact_text(text, {} if values is None else values, keyed=True)


def test_the_same_value_draws_the_same_fingerprint():
    a = _keyed(LINE.format("Comm2Ready", "$9$abc$def"))
    b = _keyed(LINE.format("Comm2Ready", "$9$abc$def"))
    assert a == b and len(KEYED.findall(a)) == 2, a


def test_a_different_value_draws_a_different_fingerprint():
    a = KEYED.findall(_keyed(LINE.format("Comm2Ready", "$9$abc$def")))
    b = KEYED.findall(_keyed(LINE.format("Comm2Drift", "$9$abc$xyz")))
    assert [lab for lab, _ in a] == [lab for lab, _ in b]
    assert all(x[1] != y[1] for x, y in zip(a, b)), (a, b)


def test_a_known_value_is_fingerprinted_too():
    secret = "LongEnoughSecret1"
    out = _keyed(f"description reached with {secret} today\n", {secret: "device_password"})
    assert secret not in out and KEYED.search(out), out
    assert KEYED.search(out).group(1) == "device_password"


def test_the_value_is_never_drawn_and_keyed_is_idempotent():
    out = _keyed(LINE.format("Comm2Ready", "$9$abc$def"))
    assert "Comm2Ready" not in out and "$9$abc$def" not in out
    assert _keyed(out) == out


def test_a_run_salts_its_fingerprints_by_itself_and_each_secret_s_label():
    """C4237 (the final review's MEDIUM 1): *keyed* given a run's id salts each fingerprint by
    the run and the secret's label: one run, one value, one label, one fingerprint; another run
    another; and a community and an enable secret holding one value never draw the same."""
    same = "SharedValue9"
    text = f"snmp-server community {same} RO\nenable password 0 {same}\n"
    a = KEYED.findall(redact.redact_text(text, {}, keyed="run-a"))
    a2 = KEYED.findall(redact.redact_text(text, {}, keyed="run-a"))
    b = KEYED.findall(redact.redact_text(text, {}, keyed="run-b"))
    assert len(a) == 2 and len({lab for lab, _ in a}) == 2, a
    assert a == a2, (a, a2)
    assert a[0][1] != a[1][1], f"two fields sharing a value drew one fingerprint: {a}"
    assert all(x[1] != y[1] for x, y in zip(a, b)), (a, b)


def test_the_fingerprint_is_keyed(monkeypatch):
    """Not a digest of the value alone: a different installation key draws a different one."""
    import hashlib
    first = redact.fingerprint("Comm2Ready")
    assert len(first) == 8 and first != hashlib.sha256(b"Comm2Ready").hexdigest()[:8]
    monkeypatch.setattr(redact, "_fingerprint_key", lambda: b"another installation's key")
    assert redact.fingerprint("Comm2Ready") != first


def test_a_diff_line_is_fingerprinted_as_the_line_it_carries():
    a = _keyed("+enable secret 9 $9$abcdefg$hij\n")       # masked only as the line it carries
    b = _keyed("+enable secret 9 $9$zyxwvut$hij\n")
    assert KEYED.search(a) and KEYED.search(b) and a != b, (a, b)


def test_unkeyed_callers_keep_the_plain_placeholder():
    out = redact.redact_text(LINE.format("Comm2Ready", "$9$abc$def"), {})
    assert "<redacted:snmp_community>" in out and not KEYED.search(out), out


def test_the_engine_mask_is_keyed_only_when_asked():
    """Only a run that compares two of its own answers asks (`reads.run`'s *keyed*, the heal
    confirm's save check); every other run keeps the plain placeholder (the review's MEDIUM 2:
    Show commands groups and compares answers by their text)."""
    from modules.discovery import masked
    text = LINE.format("Comm2Ready", "$9$abc$def")
    assert KEYED.search(masked(text, {}, "cisco_ios", keyed=True))
    plain = masked(text, {}, "cisco_ios")
    assert not KEYED.search(plain) and "<redacted:snmp_community>" in plain, plain


def test_trailing_spaces_draw_the_same_fingerprint():
    """A value running to its line's end, read once with the line's trailing spaces and once
    without, is one value (the review's LOW 4: a false "fail")."""
    # A server key runs to its line's end, so its capture takes the trailing spaces with it.
    assert KEYED.search(_keyed("tacacs-server key Abc123xyz\n")).group(2) == \
        KEYED.search(_keyed("tacacs-server key Abc123xyz   \n")).group(2)


def test_no_application_key_creates_none(tmp_path, monkeypatch):
    """A read writes nothing: with no application key, a random key for the process; none
    is made."""
    from modules import config
    missing = tmp_path / "absent.key"
    monkeypatch.setattr(config, "KEY_FILE", str(missing))
    assert len(redact.fingerprint("Comm2Ready")) == 8
    assert not missing.exists()
