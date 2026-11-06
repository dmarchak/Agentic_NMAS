"""A write job, a fixture of the job gate's tests (tests/test_job_gate.py): plans one flow per
switch sending ARP to the controller at a priority given, at most `limit` switches."""

from modules.jobs import ContractError, Job, JobInputs, JobMeta, Scope

ARP = 0x0806
HIGHEST = 65535


def arp_flow(priority):
    """The flow a switch is given: ARP to the controller at *priority*."""
    if priority < 1 or priority > HIGHEST:
        raise ContractError("arp-guard's priority", [
            f"priority is 1 to {HIGHEST}, not {priority}"])
    return {"priority": priority, "match": {"eth_type": ARP},
            "actions": [{"type": "OUTPUT", "port": "CONTROLLER"}]}


class ArpGuard(Job):
    meta = JobMeta(name="arp-guard", version="1.0.0",
                   summary="Send each switch's ARP to the controller at a given priority.",
                   permission="write", max_changes=8,
                   scope=Scope(object_types=["dcim.device"], roles=["openflow-switch"]))

    class Inputs(JobInputs):
        priority: int
        limit: int = 8

    def run(self, ctx, inputs):
        answer = ctx.controller.switches()
        if not answer["ok"]:
            raise ContractError("arp-guard", [f"the controller did not answer: "
                                              f"{answer['error']}"])
        flow = arp_flow(inputs.priority)
        planned = 0
        for switch in sorted(answer["switches"], key=lambda s: s["dpid"]):
            if planned >= inputs.limit:
                break
            ctx.changes.flow(switch["dpid"], "add_flow", flow=flow)
            planned += 1
        ctx.output.log(f"{planned} flows planned")
