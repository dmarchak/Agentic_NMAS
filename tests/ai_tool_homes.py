"""Each AI tool's person-facing home in Mercury (C3718; the operator's principle, 2026-11-14:
"the AI may only use Mercury itself ... A capability the AI needs that has no person-facing home
in Mercury is a finding ... not an AI-only tool"). Not a test module: tests/test_ai_tool_homes.py
holds it against the code.

**The AI's tools**, by family (`tools`, read from the code's own declarations, never typed here):

- ``command``: the device reads by Mercury's command families (`router_reads.COMMAND_OPS`);
- ``own``: Mercury's own reads of a device in scope (`fixit_reads.OWN`);
- ``local``: Mercury's own reads on its host for a lost stream (`fixit_reads.LOCAL`);
- ``step``: the plan engine's step kinds (`plan_engine.STEP_KINDS`);
- ``catalog``: the catalog's operations a proposal names (`heal.catalog.CATALOG`).

**`HOMES`**: ``{(family, tool): {"endpoint", "via", "where"}}``, the v2 route or control a
person uses for the same thing (*endpoint*, a Flask endpoint name), and the module both call
(*via*); *where* is the module that imports *via* on the person's side when it is not the
endpoint's own (the device page's model behind its tab, say).

**`MISSING`**: ``{(family, tool): "C<n>: why"}``, the tools with no person-facing home, or only
part of one, each naming its register row. It only shrinks (tests/ratchet_lists.py): a tool
gains a home, and leaves it.
"""

#: Each AI tool's person-facing home.
HOMES = {
    # The device's reads: Show commands, one engine (`modules.nsot.reads`) for a person's read
    # and the AI's (`router_reads.run`), the allowlist deciding the whole command for both.
    ("command", "show"): {"endpoint": "reads_v2.show_commands_run", "via": "modules.nsot.reads"},
    ("command", "show_config"): {"endpoint": "reads_v2.show_commands_run",
                                 "via": "modules.nsot.reads"},
    ("command", "ping"): {"endpoint": "reads_v2.show_commands_run", "via": "modules.nsot.reads"},
    ("command", "traceroute"): {"endpoint": "reads_v2.show_commands_run",
                                "via": "modules.nsot.reads"},
    # Mercury's own reads of a device: its device page's tabs, by the same readers.
    ("own", "intent"): {"endpoint": "device_v2.intent", "via": "modules.nsot.intent_match",
                        "where": "modules.device_page"},
    ("own", "golden"): {"endpoint": "device_v2.golden_reveal", "via": "modules.nsot.repo"},
    ("own", "neighbours"): {"endpoint": "device_v2.neighbours", "via": "modules.neighbours"},
    ("own", "history"): {"endpoint": "device_v2.history", "via": "modules.history_sources"},
    # The plan engine's steps: each the operation's own confirm, a person's control.
    ("step", "dhcp-reservation"): {"endpoint": "dhcp_v2.reservation_confirm",
                                   "via": "modules.dhcp_reservations"},
    ("step", "intent-description"): {"endpoint": "intent_v2.commit",
                                     "via": "modules.nsot.intent_edit"},
    # The general intent change: the Intent tab's commit; the deploy step: Deploy…'s confirm,
    # by the same planner and apply (`routes.deploy`).
    ("step", "intent-edit"): {"endpoint": "intent_v2.commit", "via": "modules.nsot.intent_edit"},
    ("step", "intent-deploy"): {"endpoint": "device_v2.deploy_confirm", "via": "routes.deploy"},
    # The saved reusable actions (Gate 1b), one family: a person approves one as a step of the
    # incident's plan, by the plan engine (its own button on the interface view is not built).
    ("step", "saved action"): {"endpoint": "fixit_v2.approve", "via": "modules.plan_engine"},
    ("catalog", "saved action"): {"endpoint": "saved_plans_v2.save_action",
                                  "via": "modules.nsot.saved_plans"},
    ("step", "ztp-create"): {"endpoint": "onboard_v2.create", "via": "modules.nsot.onboard"},
    ("step", "telemetry-resubscribe"): {"endpoint": "resubscribe_v2.confirm",
                                        "via": "modules.heal.resubscribe"},
    ("step", "telemetry-readd"): {"endpoint": "resubscribe_v2.readd",
                                           "via": "modules.heal.resubscribe"},
    ("step", "telemetry-collector-resubscribe"): {"endpoint": "resubscribe_v2.close_confirm",
                                                  "via": "modules.heal.resubscribe"},
    # A built-in command plan (C3757, path 2; G7's recovery the first): its home is its
    # incident's card, where a person approves the incident's plan by its hash, the AI's
    # proposal and a person's reaching one engine (the plan engine's step, through the plan's
    # declaration, `catalog.PlanStep.apply`).
    ("step", "errdisable-recover"): {"endpoint": "fixit_v2.approve",
                                     "via": "modules.plan_engine"},
    # The lost stream's ladder (17215a95, the operator 2026-11-16): its two later rungs are
    # built-in command plans, and the collector close alone a catalog operation approved only
    # as a step of its incident's plan ("a plan step with the same guards"), so each one's home
    # is that card, as the recovery's is.
    ("step", "telemetry-subscription-recreate"): {"endpoint": "fixit_v2.approve",
                                                  "via": "modules.plan_engine"},
    ("step", "telemetry-stack-restart"): {"endpoint": "fixit_v2.approve",
                                          "via": "modules.plan_engine"},
    ("step", "telemetry-collector-close"): {"endpoint": "fixit_v2.approve",
                                            "via": "modules.plan_engine"},
    ("catalog", "telemetry-collector-close"): {"endpoint": "fixit_v2.approve",
                                               "via": "modules.plan_engine"},
    # The catalog's operations: Re-subscribe's card, the one a person confirms.
    ("catalog", "telemetry-resubscribe"): {"endpoint": "resubscribe_v2.confirm",
                                           "via": "modules.heal.resubscribe"},
    ("catalog", "telemetry-readd"): {"endpoint": "resubscribe_v2.readd",
                                              "via": "modules.heal.resubscribe"},
    ("catalog", "telemetry-collector-resubscribe"): {"endpoint": "resubscribe_v2.close_confirm",
                                                     "via": "modules.heal.resubscribe"},
}

#: The AI's tools with no person-facing home, or only part of one, each with its row. Only
#: shrinks (tests/ratchet_lists.py).
MISSING = {
    ("local", "collector_sessions"): "C3720: shown to a person only inside the re-subscribe "
                                     "card's collector step, as the one session it closes",
    ("local", "stream_series"): "C3720: a person sees the stream's series only as Grafana's "
                                "panels, by other code",
    ("own", "metrics"): "C3721: the Monitoring tab draws Grafana's panels; the AI reads "
                        "Prometheus and Loki by its own queries",
    ("own", "logs"): "C3721: the Logs tab reads `device_logs.for_device`; the AI reads Loki by "
                     "the evidence pack's own query",
}


def tools() -> list:
    """Every AI tool, ``(family, tool)``, read from the code's own declarations."""
    from modules import plan_engine
    from modules.ai import fixit_reads, router_reads
    from modules.heal import catalog

    out = [("command", op.name) for op in router_reads.COMMAND_OPS]
    out += [("own", name) for name, _w, _c in fixit_reads.OWN]
    out += [("local", op.name) for op in fixit_reads.LOCAL]
    # The saved reusable actions' keys are people's (`nsot.saved_plans`): one family each way,
    # declared by the code (`saved_plans.FAMILY`), its members never named here.
    from modules.nsot import saved_plans

    saved = set(catalog.saved_actions())
    out += [("step", key) for key in plan_engine.STEP_KINDS if key not in saved]
    out += [("catalog", key) for key in catalog.CATALOG]
    out += [("step", saved_plans.FAMILY), ("catalog", saved_plans.FAMILY)]
    return out


def undeclared(found=None) -> list:
    """The AI tools neither in `HOMES` nor in `MISSING` (all of `tools` by default)."""
    return [t for t in (tools() if found is None else found)
            if t not in HOMES and t not in MISSING]
