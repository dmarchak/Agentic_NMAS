"""C476: a URL's user part (`scheme://user:secret@host`) is masked wherever text is masked.

`redact.redact_text` left `https://<user>:<secret>@<host>` unchanged: its positional rules knew
configuration shapes, and its value rules catch only secrets this installation holds. Measured
on the host the same day (read-only): no stored setting, record, golden, log or git remote
carried such a URL, so nothing had leaked; the rule is for the next one.

One positional rule (`url_userinfo`) now masks the whole user part of any URL carrying a
secret, and the user alone of an http(s)/ftp URL, where a token is often sent as the user.
`ssh://git@host` keeps `git`.

"Every caller" is held two ways:
- every masking entry point in the code is asked to mask a planted URL, through its own call
  shape (text, a payload, a log record, a report, a NetBox context, a scrubbed result);
- the population: every function in app.py, modules/ and routes/ whose name says it masks,
  redacts or scrubs is in that list, or named here with why it never handles free text. A
  masking function added later fails until it is placed.
"""

import ast
import logging
import pathlib

import pytest

from modules import redact
from tests.source_index import track_all, tracked

PLANTED = "fatal: https://x-access-token:SeCrEt-Tok3n@example.invalid/o/r.git denied"
SECRET = "SeCrEt-Tok3n"


class TestTheRule:
    @pytest.mark.parametrize("text, kept", [
        ("https://admin:pw@192.0.2.5:3000/api", "@192.0.2.5:3000/api"),
        ("http://u:p@loki.example.invalid/x", "@loki.example.invalid/x"),
        ("smb://svc:hunter22@files.example.invalid/share", "@files.example.invalid/share"),
        ("https://ghp_ABCDEFGH1234@example.invalid/o/r", "@example.invalid/o/r"),
        ('{"loki_url": "https://u:p@loki.example.invalid"}', "@loki.example.invalid"),
    ])
    def test_the_user_part_is_masked(self, text, kept):
        out = redact.redact_positional(text)
        assert "<redacted:url_userinfo>" + kept in out, out
        assert redact.redact_positional(out) == out, "idempotent"

    @pytest.mark.parametrize("text", [
        "ssh://git@example.invalid/o/r",            # a name, no secret
        "git@example.invalid:o/r.git",              # no scheme: the SCP form, a name
        "https://example.invalid/a@b",         # an @ in the path
        "mailto:someone@example.invalid",      # no //
    ])
    def test_a_url_with_no_secret_is_left_alone(self, text):
        assert redact.redact_positional(text) == text


def _log_record_masked() -> str:
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, PLANTED, None, None)
    redact.RedactingFilter().filter(rec)
    return rec.getMessage()


def _adopt_scrub() -> str:
    from modules.nsot.adopt import _scrub
    return repr(_scrub({"reason": PLANTED, "steps": [{"detail": PLANTED}]}, ["other"]))


def _adopt_scrub_plan() -> str:
    from modules.nsot.adopt import _scrub_plan
    out = {"gates": [{"detail": PLANTED, "state": "fail"}]}
    _scrub_plan(out, ["other"])
    return repr(out)


#: Every masking entry point, called through its own shape, with the planted URL.
ENTRY_POINTS = {
    "modules/redact.py:redact_positional": lambda: redact.redact_positional(PLANTED),
    "modules/redact.py:redact_text": lambda: redact.redact_text(PLANTED, values={}),
    "modules/redact.py:redact_payload": lambda: repr(redact.redact_payload(
        {"a": [PLANTED, (PLANTED,)]}, values={})),
    "modules/redact.py:RedactingFilter": _log_record_masked,
    "modules/outbound.py:mask_payload": lambda: repr(
        __import__("modules.outbound", fromlist=["x"]).mask_payload({"e": PLANTED})),
    "modules/reader_job.py:_redacted": lambda: __import__(
        "modules.reader_job", fromlist=["x"])._redacted(PLANTED),
    "modules/netbox_guard.py:_redact": lambda: __import__(
        "modules.netbox_guard", fromlist=["x"])._redact(PLANTED),
    "modules/netbox_guard.py:_redact_leaves": lambda: repr(__import__(
        "modules.netbox_guard", fromlist=["x"])._redact_leaves({"k": [PLANTED]})),
    "modules/nsot/credential_rotation.py:_mask_line": lambda: __import__(
        "modules.nsot.credential_rotation", fromlist=["x"])._mask_line(PLANTED),
    "modules/netbox_client.py:masked_context": lambda: repr(__import__(
        "modules.netbox_client", fromlist=["x"]).masked_context({"running_config": PLANTED})),
    "modules/netbox_context_mask.py:masked": lambda: repr(__import__(
        "modules.netbox_context_mask", fromlist=["x"]).masked({"running_config": PLANTED})),
    "modules/netbox_client.py:_sanitise_config": lambda: __import__(
        "modules.netbox_client", fromlist=["x"])._sanitise_config(PLANTED),
    "modules/nsot/adopt.py:_masked": lambda: repr(__import__(
        "modules.nsot.adopt", fromlist=["x"])._masked([PLANTED])),
    "modules/nsot/adopt.py:_scrub": _adopt_scrub,
    "modules/nsot/adopt.py:_scrub_plan": _adopt_scrub_plan,
    "modules/breakglass_export.py:_scrub": lambda: __import__(
        "modules.breakglass_export", fromlist=["x"])._scrub(PLANTED, "a-passphrase"),
}

#: Functions whose names say mask, redact or scrub but never take free text, each with why.
NOT_FREE_TEXT = {
    "modules/secrets_store.py:mask": "draws dots for a set field; it is given a setting's key",
    "modules/nsot/credential_rotation.py:masked_commands": "builds the masked rotation "
        "commands from a username and a privilege",
    "modules/nsot/credential_rotation.py:masked_command": "the same, one command",
    "modules/nsot/credential_rotation.py:_redact_value": "prints a `username ... secret` "
        "line's FORM, the value dropped: given only those lines",
    "modules/nsot/adopt.py:masked_program": "builds the masked adoption program from a username",
    "modules/nsot/adopt.py:owner_program_masked": "builds the owner's masked program",
    "modules/nsot/render_artifact.py:contains_mask": "a test for a mask, it masks nothing",
    "modules/nsot/render_artifact.py:assert_no_mask": "refuses a mask, it masks nothing",
    "modules/nsot/roundtrip.py:_masked_pair": "compares two lines, it masks nothing",
    "modules/ai_assistant.py:_mask_to_cidr": "a netmask to a prefix length, not a secret",
    "modules/nsot/retire.py:_mask_facts": "says what retire does about NetBox's credentials",
    "modules/netbox_context_mask.py:mask_one": "writes NetBox through `masked`, tested above",
    "modules/nsot/profile_apply.py:_masked_rows": "a nested helper over redact_positional",
    "modules/redact.py:install_log_redaction": "attaches RedactingFilter, tested above",
    "modules/redact.py:redact_all_handlers": "attaches RedactingFilter to every handler",
    "routes/identity.py:_redaction_health": "reports the filter's health",
    "modules/nsot/render_artifact.py:MaskedContentError": "an exception a mask raises",
    "modules/nsot/parsers/base.py:_redact_secret_echoes": "turns captured secret values into "
        "references inside INTENT, not masking for display; intent's own gap is C477",
    "modules/nsot/parsers/base.py:_redact": "the same, its inner helper (C477)",
    "modules/ai_assistant.py:_sanitize_for_api": "drops orphaned tool results from a chat "
        "history: the message structure, not its text",
    "modules/ai_assistant.py:_sanitize_trailing_tool_use": "repairs unmatched tool calls in a "
        "chat history: the structure, not the text",
    "modules/config_git.py:_sanitise_hostname": "a hostname made safe for a file name",
    "modules/netbox_guard.py:sanitise_modified": "rewrites NetBox's record through "
        "`_redact_leaves`, tested above",
}


@pytest.mark.parametrize("name", sorted(ENTRY_POINTS))
def test_every_masking_entry_point_masks_a_url_s_user_part(name):
    out = ENTRY_POINTS[name]()
    assert SECRET not in out and "x-access-token" not in out, (name, out)
    assert "<redacted:url_userinfo>" in out, (name, out)


def _masking_functions() -> set:
    import os

    # Relative to the working directory (the checkout), as the names below are.
    files = [pathlib.Path(os.path.relpath(p))
             for p in tracked("app.py", "modules", "routes", suffix=".py", root=".")]
    out = set()
    for p in files:
        if "__pycache__" in p.parts:
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and any(
                    w in n.name.lower() for w in ("mask", "redact", "scrub", "saniti")):
                out.add(f"{p.as_posix()}:{n.name}")
    return out


def test_every_masking_function_is_tested_or_says_why_not():
    found = _masking_functions()
    assert len(found) >= 30, f"the population shrank: {len(found)}"
    unplaced = sorted(found - set(ENTRY_POINTS) - set(NOT_FREE_TEXT))
    assert unplaced == [], ("a function that masks, redacts or scrubs: add it to ENTRY_POINTS "
                            "with a planted URL, or to NOT_FREE_TEXT saying why: " + str(unplaced))
    gone = sorted((set(ENTRY_POINTS) | set(NOT_FREE_TEXT)) - found)
    assert gone == [], f"named here and no longer defined: {gone}"


def test_a_planted_masking_function_is_found(tmp_path, monkeypatch):
    (tmp_path / "modules").mkdir()
    (tmp_path / "routes").mkdir()
    (tmp_path / "app.py").write_text("def scrub_errors(t):\n    return t\n", encoding="utf-8")
    track_all(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _masking_functions() == {"app.py:scrub_errors"}
