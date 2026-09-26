"""P.3 step 8: the agent reads devices and never changes one; it does not
commit, edit its own code, write its own standing rules, or answer its own
questions.

The agent is an on-call responder (feature audit, decision 1): it triages
with reads and PROPOSES a change as an ordinary plan a person confirms. A chat
that can push config is itself a device path no identity gate covers, since
the gate sees one person start a conversation and nothing of what the model
then sends.

None of the 24 removed tools had a test; this file names them to pin their
absence. The 19 Jenkins tools are P.4's.
"""

import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "modules", "ai_assistant.py")

REMOVED = [
    "restore_golden_config", "restore_pre_change_snapshot",
    "run_ansible_playbook", "save_ansible_playbook", "list_ansible_playbooks",
    "save_golden_config", "finalize_verified_config_change", "log_change",
    "read_app_file", "patch_app_file", "restart_server", "git_commit",
    "update_network_kb", "update_global_kb", "save_lab_note", "query_ccie_kb",
    "write_report", "report_begin", "report_append", "report_finish",
    "set_variable", "delete_variable", "update_compliance_policy", "set_collector_ip",
]


def _tool_names():
    import modules.ai_assistant as ai
    return {t["name"] for t in ai.TOOLS}


class TestTheToolList:
    def test_none_of_the_removed_tools_is_offered(self):
        assert set(REMOVED) & _tool_names() == set()

    def test_the_read_tools_are_still_there(self):
        """Floor and anchors: an empty tool list satisfies the test above."""
        names = _tool_names()
        assert len(names) >= 40, len(names)
        for anchor in ("get_running_config", "read_golden_config", "detect_config_drift",
                       "request_approval", "execute_command", "nsot_get_device_context"):
            assert anchor in names, anchor

    def test_no_dispatch_branch_remains_for_a_removed_tool(self):
        tree = ast.parse(open(SRC, encoding="utf-8").read())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "execute_tool")
        dispatched = {c.comparators[0].value for c in ast.walk(fn)
                      if isinstance(c, ast.Compare) and isinstance(c.left, ast.Name)
                      and c.left.id == "name" and isinstance(c.comparators[0], ast.Constant)}
        assert len(dispatched) >= 40, len(dispatched)
        assert set(REMOVED) & dispatched == set(), set(REMOVED) & dispatched

    def test_no_execute_tool_offers_a_mode(self):
        import modules.ai_assistant as ai
        for t in ai.TOOLS:
            if t["name"].startswith("execute_"):
                props = t["input_schema"]["properties"]
                assert "mode" not in props, t["name"]
                assert "mode" not in t["input_schema"]["required"], t["name"]
                assert "READ-ONLY" in t["description"], t["name"]


class TestTheAgentMayOnlyRead:
    @pytest.mark.parametrize("cmd", ["show running-config", "sh ip int br",
                                     "sho clock", "ping 192.0.2.1",
                                     "traceroute 192.0.2.1", "dir flash:",
                                     "show run | include snmp"])
    def test_reads_are_allowed(self, cmd):
        from modules.ai_assistant import _read_only_refusal
        assert _read_only_refusal([cmd]) == ""

    @pytest.mark.parametrize("cmd", ["reload", "delete flash:x.bin", "clear ip bgp *",
                                     "write erase", "copy run start",
                                     "configure terminal", "", "   "])
    def test_anything_else_is_refused(self, cmd):
        from modules.ai_assistant import _read_only_refusal
        out = _read_only_refusal([cmd])
        assert out.startswith("REFUSED"), (cmd, out)

    def test_config_mode_is_refused_by_name(self):
        from modules.ai_assistant import _read_only_refusal
        assert "config mode was removed" in _read_only_refusal(["show clock"], "config")

    def test_a_line_break_cannot_smuggle_a_second_command(self):
        from modules.ai_assistant import _read_only_refusal
        assert _read_only_refusal(["show clock\nreload"]).startswith("REFUSED")

    def test_one_bad_command_in_a_list_refuses_the_list(self):
        from modules.ai_assistant import _read_only_refusal
        assert _read_only_refusal(["show clock", "reload"]).startswith("REFUSED")

    def test_every_execute_branch_checks_before_it_connects(self):
        """The refusal is the FIRST statement of each execute branch, so no
        device session is opened for a refused command."""
        tree = ast.parse(open(SRC, encoding="utf-8").read())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "execute_tool")
        found = {}
        for node in ast.walk(fn):
            if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                    and isinstance(node.test.left, ast.Name) and node.test.left.id == "name"
                    and isinstance(node.test.comparators[0], ast.Constant)
                    and node.test.comparators[0].value.startswith("execute_")):
                first = node.body[0]
                found[node.test.comparators[0].value] = (
                    isinstance(first, ast.Assign)
                    and "_read_only_refusal" in ast.unparse(first.value))
        assert found == {"execute_command": True, "execute_commands_on_device": True,
                         "execute_command_on_multiple_devices": True}, found


class TestNoReplyIsAutoAnswered:
    def test_the_canned_answer_is_gone_from_the_code(self):
        """Parsed, not grepped: a comment explaining the removal may quote it."""
        tree = ast.parse(open(SRC, encoding="utf-8").read())
        strings = [n.value for n in ast.walk(tree)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        assert not [s for s in strings if s.strip().lower().startswith("yes, please continue")]
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "_AUTO_CONTINUE_RE" not in names and "auto_continues" not in names

    def test_the_truncation_continue_is_kept(self):
        """Control: continuing a reply the token limit CUT OFF is not answering
        a question, and stays."""
        src = open(SRC, encoding="utf-8").read()
        assert "Your previous response was cut off by the token limit." in src
