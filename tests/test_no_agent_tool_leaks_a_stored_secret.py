"""No agent tool hands the model a stored secret (C55, C56, the agent side).

`get_monitoring_config` wrote both SNMP communities in PROSE
(`SNMP community (RW):  <value>`), and the provider boundary masks config
SYNTAX and the values in its redaction table, neither of which that line
was. Measured: both reached the model. The operator's question followed:
do any of the other tools report stored values in prose?

`test_provider_redaction.py` could not have answered it. It drives the
boundary with hand-written tool-output SHAPES, all in config syntax, and
judges a leak by `contains_known_secret()`, which knows only the table's
values: a population the test defined, like B11's sweep before it.

So this drives the REAL loop. `run_chat()` runs against a fake provider that
asks for EVERY tool in the agent's list at once. Each store is planted, as
in `test_no_get_returns_a_stored_secret.py`. What the second provider call
receives (after the boundary's redaction, so exactly what would leave this
host) is searched for every planted value.

Its first run found `read_variables` (`name = value`, in prose); fixed. What
it cannot reach, stated: tools that read a DEVICE ran against a blocked
network with a stub device, so their live output was not exercised. That
output is config syntax, which positional redaction masks, and
`test_provider_redaction.py` pins that shape.
"""

import json
import sys
import threading
import types
from types import SimpleNamespace as NS

import pytest

from tests.test_no_get_returns_a_stored_secret import DEVICE, planted  # noqa: F401

#: Arguments a tool needs to reach a planted value, where a generic guess
#: would not (a fixture that cannot exhibit the case: `read_variables`
#: called with "r1" answers "not set" and prints nothing).
EXPLICIT = {"read_variables": {"key": "snmp_ro_community"}}


def _args_for(tool):
    if tool["name"] in EXPLICIT:
        return dict(EXPLICIT[tool["name"]])
    props = (tool.get("input_schema") or {}).get("properties") or {}
    out = {}
    for name, spec in props.items():
        t, n = spec.get("type"), name.lower()
        if "enum" in spec:
            out[name] = spec["enum"][0]
        elif t == "array":
            out[name] = [DEVICE["ip"]] if ("ip" in n or "device" in n) else ["r1"]
        elif "ip" in n:
            out[name] = DEVICE["ip"]
        elif any(k in n for k in ("hostname", "device", "host")):
            out[name] = "r1"
        elif "command" in n:
            out[name] = "show running-config"
        elif t in ("integer", "number"):
            out[name] = 5
        elif t == "boolean":
            out[name] = False
        else:
            out[name] = "r1"
    return out


def drive(tools):
    """{tool name: the tool_result text the provider receives}."""
    from modules import ai_assistant as ai

    calls = []

    def create(**kw):
        calls.append(kw)
        if len(calls) == 1:
            return NS(content=[NS(type="tool_use", id=f"t{i}", name=t["name"],
                                  input=_args_for(t)) for i, t in enumerate(tools)],
                      stop_reason="tool_use", usage=NS(input_tokens=1, output_tokens=1))
        return NS(content=[NS(type="text", text="done")], stop_reason="end_turn",
                  usage=NS(input_tokens=1, output_tokens=1))

    client = NS(beta=NS(messages=NS(create=create)))
    stub = types.ModuleType("anthropic")          # the SDK is not a test dependency
    stub.RateLimitError = type("RateLimitError", (Exception,), {})
    stub.Anthropic = lambda *a, **k: client
    mp = pytest.MonkeyPatch()
    # The tool-result cache is process-wide and keyed on name and arguments
    # (60 s for get_monitoring_config), so a drive could be served an earlier
    # drive's output: the control first passed for exactly that reason. Each
    # drive measures what the tools produce NOW.
    ai._tool_cache.clear()
    try:
        mp.setitem(sys.modules, "anthropic", stub)
        mp.setattr(ai, "_get_anthropic_client", lambda: client)
        mp.setenv("ANTHROPIC_API_KEY", "PLANTEDEnvZq7x")
        # A fresh session per drive: a shared one carries the previous
        # drive's tool results in its history.
        session = f"leak-sweep-{len(tools)}-{id(calls)}"
        list(ai.run_chat(session, "go",
                         lambda: [dict(DEVICE, device_type="cisco_ios")],
                         {}, {}, threading.Lock(), force_provider="anthropic"))
    finally:
        mp.undo()
        # And after: the control leaves a deliberately leaking result, and
        # the cache is served by /ai/tool_cache_snapshot to any later test.
        ai._tool_cache.clear()
    assert len(calls) >= 2, "the loop did not reach a second provider call"
    names = {f"t{i}": t["name"] for i, t in enumerate(tools)}
    out = {}
    for msg in calls[1]["messages"]:
        for block in msg.get("content") if isinstance(msg.get("content"), list) else []:
            if (isinstance(block, dict) and block.get("type") == "tool_result"
                    and block.get("tool_use_id") in names):
                out[names[block["tool_use_id"]]] = json.dumps(block.get("content"))
    return out


def _leaks(results, values):
    planted_values = {v: s for s, vs in values.items() if not s.startswith("_") for v in vs}
    return sorted({(tool, store) for tool, text in results.items()
                   for v, store in planted_values.items() if v in text})


@pytest.fixture(scope="module")
def results(planted):
    from modules import ai_assistant as ai

    return drive([t for t in ai.TOOLS if t.get("name")])


class TestEveryToolThroughTheRealBoundary:
    def test_every_tool_ran(self, results):
        from modules import ai_assistant as ai

        names = {t["name"] for t in ai.TOOLS if t.get("name")}
        assert len(names) >= 25, len(names)            # 30 measured, 2026-09-27
        assert set(results) == names

    def test_no_tool_hands_the_model_a_planted_value(self, results, planted):
        assert _leaks(results, planted) == []

    def test_read_variables_reached_the_store(self, results):
        """The floor for the one above: the tool that leaked really read the
        planted variable, and now withholds its value."""
        assert "snmp_ro_community" in results["read_variables"]
        assert "withheld" in results["read_variables"]

    def test_the_sweep_can_see_a_leak(self, planted, monkeypatch):
        """The control, through the same loop: a tool made to print a stored
        community in prose is found."""
        from modules import ai_assistant as ai
        from modules import collector_config

        real = collector_config.public_config
        monkeypatch.setattr(collector_config, "public_config", lambda: dict(
            real(), collector_ip=collector_config._load().get("snmp_community_rw")))
        tool = [t for t in ai.TOOLS if t.get("name") == "get_monitoring_config"]
        leaks = _leaks(drive(tool), planted)
        assert leaks == [("get_monitoring_config", "collector_config")]
