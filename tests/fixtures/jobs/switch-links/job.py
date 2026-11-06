"""A read job, a fixture of the job gate's tests (tests/test_job_gate.py): each switch the
controller reports, with the number of links leaving it, and which are busy."""

from modules.jobs import Job, JobInputs, JobMeta, Scope


def link_counts(switches, links):
    """`{dpid: links leaving it}`, every switch named, a link from elsewhere not counted."""
    counts = {s["dpid"]: 0 for s in switches}
    for link in links:
        dpid = link["src"]["dpid"]
        if dpid in counts:
            counts[dpid] += 1
    return counts


def label(count, busy):
    """A switch's state: busy past *busy* links, isolated with none, otherwise ok."""
    if count > busy:
        return "busy"
    if count == 0:
        return "isolated"
    return "ok"


class SwitchLinks(Job):
    meta = JobMeta(name="switch-links", version="1.0.0",
                   summary="Each switch with its link count, and which are busy.",
                   permission="read",
                   scope=Scope(object_types=["dcim.device"], roles=["openflow-switch"]))

    class Inputs(JobInputs):
        busy: int = 2

    def run(self, ctx, inputs):
        switches = ctx.controller.switches()
        links = ctx.controller.links()
        if not switches["ok"] or not links["ok"]:
            ctx.output.log("the controller did not answer")
            return
        counts = link_counts(switches["switches"], links["links"])
        rows = [[dpid, n, label(n, inputs.busy)] for dpid, n in sorted(counts.items())]
        ctx.output.table("switch links", ["dpid", "links", "state"], rows)
