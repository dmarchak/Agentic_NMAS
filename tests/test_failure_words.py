"""C1497 (2026-10-21): a deploy whose session failed to open recorded an EMPTY reason, "Pre-snapshot
failed for 1 device(s) — aborting before deploy: <device> (<address>): " and nothing after it,
because the exception carried no message and the stage recorded `str(exc)` alone. Every pipeline
stage that records an exception now says it through `connection.failure_words`: its message, or
its type when it carries none (C1488 found the same for a save).

The real Stage 4 and Stage 7; the device's session is a fake that raises.
"""

import pytest

import modules.pipeline as P
from modules.connection import failure_words
from tests.test_pipeline import _ctx


class _Silent(Exception):
    """What a session that died mid-open can raise: an exception with no message."""


class TestTheWords:
    def test_a_message_is_said_as_it_is(self):
        assert failure_words(TimeoutError("timed out after 35 s")) == "timed out after 35 s"

    def test_no_message_names_the_type(self):
        assert failure_words(_Silent()) == "_Silent (no message)"
        assert failure_words(EOFError("  ")) == "EOFError (no message)"


def _raise(*_a, **_k):
    raise _Silent()


@pytest.mark.parametrize("address", ["192.0.2.31", "2001:db8::31"])
class TestAStageNamesWhatFailed:
    def test_the_pre_snapshot_reason_names_the_type(self, monkeypatch, address):
        monkeypatch.setattr("modules.connection.get_persistent_connection", _raise)
        ctx = _ctx(device_ips=[address], selected_devices=[{"ip": address, "hostname": "R1"}])
        with pytest.raises(P.PipelineStageError) as exc:
            P._stage_pre_snapshot(ctx)
        assert f"R1 ({address}): _Silent (no message)" in str(exc.value)

    def test_the_post_snapshot_reason_names_the_type(self, monkeypatch, address):
        monkeypatch.setattr("modules.connection.get_persistent_connection", _raise)
        ctx = _ctx(device_ips=[address], selected_devices=[{"ip": address, "hostname": "R1"}])
        ctx.push_results = {address: {"ok": True}}
        with pytest.raises(P.PipelineStageError) as exc:
            P._stage_post_snapshot(ctx)
        assert "R1: _Silent (no message)" in str(exc.value)
