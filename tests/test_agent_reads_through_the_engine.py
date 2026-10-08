"""The AI assistant's read tools ask the reads engine (C548, R5; NSOT_PLAN 8.16: "one engine, two
users ... the agent asks the same engine for its evidence, never a session of its own").

The REAL chat loop (`run_chat`) against a fake provider that asks for the read tools, as
`test_no_agent_tool_leaks_a_stored_secret` drives it; the engine runs on test_reads_engine's lab
(real captures at its session seam). What the provider receives is the engine's answer: masked,
a held device named, and the run recorded as "the agent, for <person>".
"""

import json
import sys
import threading
import types
from types import SimpleNamespace as NS

import pytest

from tests.test_reads_engine import DEVICES, Session, lab  # noqa: F401 (the fixture)


def drive(lab, calls_for, actor="op@example.invalid"):  # noqa: F811
    """{tool_use id: the tool_result text the provider receives} for the tool calls given."""
    from modules import ai_assistant as ai

    calls = []

    def create(**kw):
        calls.append(kw)
        if len(calls) == 1:
            return NS(content=[NS(type="tool_use", id=tid, name=name, input=args)
                               for tid, name, args in calls_for],
                      stop_reason="tool_use", usage=NS(input_tokens=1, output_tokens=1))
        return NS(content=[NS(type="text", text="done")], stop_reason="end_turn",
                  usage=NS(input_tokens=1, output_tokens=1))

    client = NS(beta=NS(messages=NS(create=create)))
    stub = types.ModuleType("anthropic")
    stub.RateLimitError = type("RateLimitError", (Exception,), {})
    stub.Anthropic = lambda *a, **k: client
    mp = pytest.MonkeyPatch()
    ai._tool_cache.clear()
    try:
        mp.setitem(sys.modules, "anthropic", stub)
        mp.setattr(ai, "_get_anthropic_client", lambda: client)
        mp.setenv("ANTHROPIC_API_KEY", "PLANTEDEnvZq7x")
        list(ai.run_chat(f"engine-{id(calls)}", "go",
                         lambda: [dict(d, username="u", password="", secret="") for d in DEVICES],
                         {d["ip"]: True for d in DEVICES}, {}, threading.Lock(),
                         force_provider="anthropic", actor=actor, list_name="Lab"))
    finally:
        mp.undo()
        ai._tool_cache.clear()
    assert len(calls) >= 2, "the loop did not reach a second provider call"
    out = {}
    for msg in calls[1]["messages"]:
        for block in msg.get("content") if isinstance(msg.get("content"), list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                out[block.get("tool_use_id")] = json.dumps(block.get("content"))
    return out


@pytest.fixture
def agent(lab, monkeypatch):  # noqa: F811
    session = Session()
    monkeypatch.setattr("modules.connection.with_temp_connection", session)
    lab["session"] = session
    return lab


def test_one_device_s_read_is_the_engine_s_masked_and_recorded(agent):
    from modules.nsot import reads
    got = drive(agent, [("t1", "execute_command",
                         {"ip": "192.0.2.12", "command": "show running-config"})])
    text = got["t1"]
    assert "username admin privilege 15" in text                 # the answer reached the model
    assert "password 0 admin" not in text and "community public" not in text   # masked
    (r,) = reads.runs("Lab")["runs"]
    assert r["by"] == "agent" and reads.actor_words(r) == "the agent, for op@example.invalid"
    assert r["devices"] == ["r2"] and r["purpose"] == "the AI assistant's execute_command"


def test_many_devices_in_one_run_and_a_held_one_named(agent):
    from modules.nsot import device_ops, reads
    with device_ops.hold("Lab", "r3", "deploy", "other@example.invalid"):
        got = drive(agent, [("t1", "execute_command_on_multiple_devices",
                             {"device_ips": ["192.0.2.11", "192.0.2.13"],
                              "command": "show ip interface"})])
    text = got["t1"]
    assert "=== r1 (192.0.2.11) ===" in text and "GigabitEthernet1" in text
    assert "r3 is being deployed to by other@example.invalid" in text
    (r,) = reads.runs("Lab")["runs"]
    assert sorted(r["devices"]) == ["r1", "r3"] and r["results"]["r3"]["state"] == "skipped"
    assert ("show ip interface") in agent["session"].sent and len(agent["session"].sent) == 1


def test_a_write_is_refused_before_any_device(agent):
    from modules.nsot import reads
    got = drive(agent, [("t1", "execute_commands_on_device",
                         {"ip": "192.0.2.12", "commands": ["show clock", "reload"]})])
    assert "REFUSED" in got["t1"] and agent["session"].sent == []
    assert reads.runs("Lab")["runs"] == []        # the tool's own refusal: the engine never asked
