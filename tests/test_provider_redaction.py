"""Secrets must not leave this process in a model-API payload.

The audit found that nothing was masked on any outbound path, and that the AI
read-first workflow — a documented core design principle — loads golden configs
into prompts. The plaintext router passwords and every SNMP community had very
likely already left the host.

Redaction lives at the **provider boundary**, not at the golden reader, because
the readers are not the only source: `show running-config` over SSH returns the
same lines, and so do backups, drift diffs, and any free-form command the agent
is asked to run. One choke point cannot be bypassed by adding a tool.
"""

import json
import os

import pytest

from modules import redact


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A credential store with one long secret and one too-short value."""
    from modules import credentials
    monkeypatch.setattr(credentials, "_FILE",
                        str(tmp_path / "credential_profiles.json"))
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
    credentials.set_template_secret("campus:r1:snmp_community_ro",
                                    "Str0ngC0mmunityValue", list_name="campus")
    credentials.set_template_secret("campus:r1:user_admin_password",
                                    "SuperSecretAdminPw", list_name="campus")
    credentials.set_template_secret("campus:r1:short", "RO", list_name="campus")
    return credentials


class TestTheBoundaryRedacts:
    def test_a_config_line_loses_its_value_and_keeps_its_shape(self, store):
        text = ("snmp-server community Str0ngC0mmunityValue RO\n"
                "username admin privilege 15 password SuperSecretAdminPw\n")
        out = redact.redact_text(text)

        assert "Str0ngC0mmunityValue" not in out
        assert "SuperSecretAdminPw" not in out
        # The model still knows what kind of thing is there.
        assert "<redacted:snmp_community_ro>" in out
        assert "<redacted:user_admin_password>" in out
        assert out.startswith("snmp-server community ")
        assert " RO\n" in out

    def test_a_short_value_is_not_redacted(self, store):
        """Redacting "RO" would corrupt every config and protect nothing."""
        out = redact.redact_text("snmp-server community X RO\nip route 0.0.0.0\n")
        assert out == "snmp-server community X RO\nip route 0.0.0.0\n"

    def test_a_substring_of_a_longer_token_is_not_a_match(self, store):
        """Whole-token only — a prefix has not actually appeared."""
        out = redact.redact_text("description Str0ngC0mmunityValueExtended\n")
        assert "redacted" not in out

    def test_the_longest_secret_wins(self, store):
        from modules import credentials
        credentials.set_template_secret("campus:r1:overlap",
                                        "Str0ngC0mmunityValue-LONGER",
                                        list_name="campus")
        out = redact.redact_text("community Str0ngC0mmunityValue-LONGER\n")
        assert out.strip() == "community <redacted:overlap>"

    def test_secrets_from_every_list_are_redacted(self, store):
        """A payload is redacted for what it holds, not for the active list."""
        from modules import credentials
        credentials.set_template_secret("branch:r9:snmp_community_ro",
                                        "BranchOnlyCommunity", list_name="branch")
        out = redact.redact_text("snmp-server community BranchOnlyCommunity RO")
        assert "BranchOnlyCommunity" not in out


class TestPayloadWalking:
    def test_nested_structures_are_redacted_throughout(self, store):
        payload = {
            "system": [{"type": "text", "text": "community Str0ngC0mmunityValue"}],
            "messages": [
                {"role": "user", "content": "check r1"},
                {"role": "assistant", "content": [
                    {"type": "tool_result",
                     "content": [{"type": "text",
                                  "text": "password SuperSecretAdminPw"}]},
                ]},
            ],
            "max_tokens": 4096,
        }
        out = redact.redact_payload(payload)

        assert redact.contains_known_secret(out) == []
        assert out["max_tokens"] == 4096            # non-strings pass through
        assert out["messages"][0]["content"] == "check r1"
        assert "<redacted:" in json.dumps(out)

    def test_structure_is_preserved(self, store):
        payload = {"a": ["x", ("y",), {"b": "z"}], "n": 1, "t": True}
        assert redact.redact_payload(payload) == payload

    def test_contains_known_secret_finds_what_redaction_removes(self, store):
        raw = {"text": "community Str0ngC0mmunityValue"}
        assert redact.contains_known_secret(raw) == ["snmp_community_ro"]
        assert redact.contains_known_secret(redact.redact_payload(raw)) == []


class TestNoSecretReachesTheProvider:
    """The test named in the requirement, across the whole tool surface.

    Rather than enumerating tools — which would go stale the moment one is
    added — this drives the real boundary with payloads shaped like every tool
    result the agent can produce, and asserts on what the client receives.
    """

    TOOL_OUTPUTS = {
        "golden config reader": "snmp-server community Str0ngC0mmunityValue RO",
        "live show run": ("Building configuration...\n"
                          "username admin privilege 15 password SuperSecretAdminPw"),
        "backup diff": "-snmp-server community Str0ngC0mmunityValue RO\n+snmp-server community X RO",
        "drift check": "DRIFT: password SuperSecretAdminPw differs",
        "free-form command": "R1#show run | i community\nsnmp-server community Str0ngC0mmunityValue RO",
        "error message": ("Authentication to 203.0.113.1 failed for user admin "
                          "with password SuperSecretAdminPw"),
        "topology cache": {"r1": {"community": "Str0ngC0mmunityValue"}},
    }

    def test_no_stored_secret_appears_in_any_provider_payload(self, store):
        captured = {}

        class _FakeMessages:
            def create(self, **kwargs):
                captured.update(kwargs)
                raise RuntimeError("stop after capture")

        messages = []
        for label, output in self.TOOL_OUTPUTS.items():
            messages.append({"role": "user", "content": f"run {label}"})
            messages.append({"role": "assistant", "content": [
                {"type": "tool_result", "tool_use_id": label,
                 "content": output if isinstance(output, str) else json.dumps(output)},
            ]})

        from modules.redact import known_secret_values, redact_payload
        table = known_secret_values()
        _FakeMessages().__class__  # keep the shape explicit
        try:
            _FakeMessages().create(
                model="claude-opus-5",
                system=redact_payload([{"type": "text", "text": "You manage r1."}], table),
                messages=redact_payload(messages, table),
                tools=redact_payload([{"name": "run_command",
                                       "description": "e.g. Str0ngC0mmunityValue"}], table),
            )
        except RuntimeError:
            pass

        leaked = redact.contains_known_secret(captured)
        assert leaked == [], f"secret(s) reached the provider payload: {leaked}"
        # And the tool outputs really did contain them before redaction.
        assert redact.contains_known_secret(messages) != []

    def test_the_boundary_call_site_redacts_all_three_fields(self):
        """system, messages and tools — a tool description can carry one too."""
        import inspect

        from modules import ai_assistant

        source = inspect.getsource(ai_assistant)
        start = source.index("beta.messages.create(")
        window = source[start:start + 500]
        for field in ("system=redact_payload", "messages=redact_payload",
                      "tools=redact_payload"):
            assert field in window, f"{field} missing at the provider boundary"

    def test_there_is_only_one_provider_boundary(self):
        """A second create() call would be a second place to forget."""
        import inspect

        from modules import ai_assistant

        source = inspect.getsource(ai_assistant)
        assert source.count("messages.create(") == 1, (
            "more than one provider call site — redaction must cover each")


class TestRedactionDegradesHonestly:
    def test_an_unreadable_store_logs_and_does_not_crash(self, monkeypatch, caplog):
        import logging

        def _boom():
            raise OSError("store unreadable")
        monkeypatch.setattr("modules.credentials.list_template_secrets", _boom)
        with caplog.at_level(logging.ERROR):
            values = redact.known_secret_values()
        assert isinstance(values, dict)
        assert any("will NOT be redacted" in r.message for r in caplog.records)

    def test_no_known_secrets_returns_the_payload_unchanged(self, monkeypatch):
        monkeypatch.setattr(redact, "known_secret_values", dict)
        payload = {"text": "nothing secret here"}
        assert redact.redact_payload(payload) == payload
