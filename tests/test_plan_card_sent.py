"""The plan card shows exactly what each step sends, from what the step's hash binds
(db800983, the operator, 2026-11-16: "show what each step sends before Approve";
`modules/fixit/plan.py` `sent_of`). The debt pass, 2026-11-18 (docs/FAST_LANE_DEBT.md's row
for db800983).

Per step kind, on the step's own preview as it is handed in (``drawn``):
- **A command plan** (a built-in's key): config mode's entry, the program in order, its exit;
  not saved.
- **The collector's close:** the host's one action naming both ends and the helper, nothing to
  the device; IPv4 and IPv6 ends.
- **A re-subscribe with the collector step:** the host's close first, then the device's lines
  (each removal, then each re-add), in the order run; a Re-add the receiver its re-adds alone.
- **An intent deploy:** entry, program, exit; saved once its verify passes.
- **An intent edit:** its diff, nothing to the device.
- **Any other operation:** what its hash binds instead of lines.
No device, no store.
"""
import pytest

from modules.fixit import plan as PL
from modules.heal import resubscribe as R

PROGRAM = ["interface GigabitEthernet1/0", " shutdown", " no shutdown"]
UNITS = [{"remove": ["telemetry ietf subscription 101", " no receiver ip address"],
          "readd": ["telemetry ietf subscription 101", " receiver ip address 192.0.2.9 57500"]},
         {"remove": ["telemetry ietf subscription 102", " no receiver ip address"],
          "readd": ["telemetry ietf subscription 102", " receiver ip address 192.0.2.9 57500"]}]


def test_a_command_plan_step_is_config_mode_its_program_and_its_exit_not_saved():
    got = PL.sent_of("errdisable-recover", {"program": PROGRAM}, "s1")
    assert got["lines"] == [PL.CONFIG_IN, *PROGRAM, PL.CONFIG_OUT]
    assert (got["device"], got["save"], got["host"]) == ("s1", PL.NOT_SAVED, "")


@pytest.mark.parametrize("remote,local", [("192.0.2.7:57400", "192.0.2.9:57500"),
                                          ("[2001:db8::7]:57400", "[2001:db8::9]:57500")])
def test_the_collectors_close_is_the_hosts_one_action_and_nothing_to_the_device(remote, local):
    got = PL.sent_of(R.CLOSE_KEY, {"close": {"remote": remote, "local": local}}, "r7")
    assert got["lines"] == [] and got["binds"] == "sends nothing to r7"
    assert got["host"] == f"close TCP session {remote} -> {local} (mercury-collector-close)"
    assert got["parts"] == [{"system": "the Mercury host (collector)", "actions": [got["host"]]}]


def test_a_resubscribe_with_the_collector_step_is_the_close_then_the_devices_lines():
    close = {"remote": "192.0.2.7:57400", "local": "192.0.2.9:57500"}
    got = PL.sent_of(R.COLLECTOR_KEY, {"close": close, "units": UNITS}, "r7")
    removals = [ln for u in UNITS for ln in u["remove"]]
    readds = [ln for u in UNITS for ln in u["readd"]]
    assert got["lines"] == removals + readds, "each removal, then each re-add"
    assert [p["system"] for p in got["parts"]] == ["the Mercury host (collector)", "r7"]
    assert got["parts"][1] == {"system": "r7", "lines": removals + readds, "save": PL.NOT_SAVED}
    readd = PL.sent_of(R.READD_KEY, {"units": UNITS}, "r7")
    assert readd["lines"] == readds and readd["host"] == "" and len(readd["parts"]) == 1


def test_an_intent_deploy_is_saved_once_its_verify_passes_and_an_edit_sends_nothing():
    got = PL.sent_of("intent-deploy", {"program": PROGRAM}, "s1")
    assert got["lines"] == [PL.CONFIG_IN, *PROGRAM, PL.CONFIG_OUT]
    assert got["save"] == PL.SAVED_AFTER_VERIFY
    edit = PL.sent_of("intent-edit", {"diff": "- description old\n+ description new"}, "s1")
    assert edit["lines"] == [] and edit["diff"].startswith("- description old")
    assert edit["binds"].startswith("sends nothing to the device")


def test_any_other_operation_says_what_its_hash_binds():
    got = PL.sent_of("bgp-soft-clear", {}, "r2")
    assert got["lines"] == [] and got["binds"] == (
        "its hash binds bgp-soft-clear's parameters, not lines it sends")
