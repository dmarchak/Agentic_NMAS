"""C3957 (the operator's decision 4, 2026-11-18): is a saved fix's command plan refused on a
switch its SDN controller manages? Offline, nothing pressed on any device: the switch is
tests/test_command_plan.py's fake (s1's captures, its committed golden), its inventory row
made controller-managed by either mark modules/sdn/authority.py reads (``platform`` ``openflow
via lab-ctl``, or ``device_type`` ``openflow`` with no platform; PHASE8_PLAN 17.1 S12), the
network holding that controller's connection, as tests/test_sdn_authority.py plants them.

Measured 2026-11-18 at the runner a saved fix's press runs (`fixit_v2.fix_with_script`'s job
calls `command_plan_run.run`; the real preview, policy and pipeline on the fake switch):
refused, nothing sent, for both marks. The refusal is the raw-line rule's (command_policy: no
measured shapes for the device's platform), not the authority rule's; the route's own gate
does not refuse it (`fixit_v2.fix_with_script` is in neither `authority.DIRECT` nor
`NOT_DIRECT`, tests/test_sdn_authority.py's open failure; C3957). The control: the same run on
the same switch as a direct device sends its plan.
"""
import pytest

from modules.sdn import authority as A
from tests import test_command_plan as TCP
from tests.test_command_plan import NET, VALUES, go, lab  # noqa: F401 (the fixture)

CONTROLLER = "lab-ctl"
DIRECT_ROW = {"hostname": "s1", "ip": "192.0.2.11", "device_type": "cisco_ios"}
MARKS = {
    "platform names its controller": dict(DIRECT_ROW, platform=f"openflow via {CONTROLLER}"),
    "device type openflow": dict(DIRECT_ROW, device_type="openflow", platform=""),
}


def _run(lab, monkeypatch, row):  # noqa: F811
    from modules.nsot import command_plan_run as CR

    class Model(TCP.Model):
        def device(self, host):
            return dict(row) if host == self.name else {}

    monkeypatch.setattr(A, "_connections", lambda network: [{"name": CONTROLLER}])
    monkeypatch.setattr("modules.device.load_saved_devices", lambda *_a, **_k: [dict(row)])

    def sleep(s):
        lab["t"] += float(s)
    src = CR.Sources(NET, clock=lambda: lab["t"], sleep=sleep, model=Model())
    return go(lab, dict(VALUES), sources=src)


@pytest.mark.parametrize("mark", sorted(MARKS))
def test_the_runner_sends_nothing_to_a_controller_managed_switch(lab, monkeypatch, mark):  # noqa: F811
    row = MARKS[mark]
    assert A.of(dict(row), NET)["kind"] == "controller", "floor: the switch is managed"
    rec = _run(lab, monkeypatch, row)
    assert lab["sw"].batches == [], (
        f"sent to a controller-managed switch: {lab['sw'].batches}; the run's outcome "
        f"{rec['outcome']}: {rec.get('why')}")
    assert rec["outcome"] == "refused" and "Nothing was sent" in str(rec.get("why")), rec
    assert [s["step"] for s in rec["steps"] if s["result"] == "refused"] == ["approve"]


def test_the_control_the_same_run_on_a_direct_switch_sends_its_plan(lab, monkeypatch):  # noqa: F811
    """The harness reaches the send: the same switch, direct, is recovered."""
    assert A.of(dict(DIRECT_ROW), NET)["kind"] == "direct"
    rec = _run(lab, monkeypatch, DIRECT_ROW)
    assert rec["outcome"] == "done", rec.get("why")
    assert lab["sw"].batches == [["interface GigabitEthernet1/0", " shutdown", " no shutdown"]]
