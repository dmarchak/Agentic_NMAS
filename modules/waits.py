"""The wait registry: every sleep, timed wait and deadline in the product, declared (the
operator's standing rule R3, 2026-11-14: "no fixed waits. Every check takes only as long as it
needs ... Make it mechanical: a wait registry. Every sleep, settle, grace or timeout in the code
declares what it waits for and why. A test fails on an undeclared one.").

**One entry per function that waits**, keyed ``<path>::<function's qualified name>``
(``<module>`` at module level), as tests/test_wait_registry.py finds them: a call to a sleep, a
timed ``wait``/``join(timeout=)``, or a deadline. Each entry is
``{"waits_for", "why", "basis", "early", "constants"}``:

- *waits_for*: what it waits for, in a sentence;
- *why*: why that long;
- *basis* (one of `BASES`): ``measured`` (a measurement, its date in *why*), ``device timer``
  (read from the device's configuration), ``setting`` (a value a person sets, its name in
  *why*), ``reasoned`` (reasoned, not measured: *why* says from what), ``cadence`` (a
  background loop's interval: it waits for nothing but its next pass), ``caller`` (its length
  is its caller's argument: the caller's bound is the caller's own), ``measured each run`` (a
  bound computed from the run's own measurement) or ``unclassified`` (the full wait, safe by
  default: R3's rule for anything not classified);
- *early*: True when the wait ends as soon as what it waits for holds (a poll), False when it
  always runs its full length;
- *constants*: the constants its waits' lengths are named by.

**What is not here**: a bound on one call (``subprocess.run(timeout=)``, an HTTP client's
``timeout``) bounds a call that ends when it answers, and is not in the scan's population; the
lab tooling under ``lab/`` and the shell scripts are not scanned. tests/test_wait_registry.py
states what the scan assumes.

No side effects on import.
"""

BASES = ("measured", "device timer", "setting", "reasoned", "cadence", "caller",
         "measured each run", "unclassified")


def _w(waits_for: str, why: str, basis: str, early: bool, constants=()) -> dict:
    return {"waits_for": waits_for, "why": why, "basis": basis, "early": early,
            "constants": tuple(constants)}


WAITS = {
    # ── The heal and its operations ──────────────────────────────────────────────────────
    "modules/heal/act.py::read_symptom": _w(
        "a heal's symptom gone from its reader's store, re-read every POLL_SECONDS until gone "
        "or its kind's bound (SYMPTOM_SECONDS, or the heartbeat's own bound) passes",
        "each bound about 2.5 times what the symptom needs to clear, reasoned from the readers' "
        "intervals (SYMPTOM_SECONDS' comment); a cosmetic heal (R3, `readback_only`) reads it "
        "once and never waits",
        "reasoned", True, ("POLL_SECONDS",)),
    "modules/heal/bounce.py::_held": _w(
        "the device's own revert timer to end, plus WATCH_PAST_S, when the bounce was not "
        "confirmed: the device reverts by itself and the watch reads it",
        "the revert timer the bounce configured on the device (TIMER_MINUTES, the operator's "
        "trial, C2425) and the trial's 3 minutes past it",
        "device timer", False, ("POLL_S",)),
    "modules/heal/bounce.py::_stable": _w(
        "the port to stay up through the network's flap window after the bounce",
        "the per-network setting heal_flap_minutes (10 minutes by default, 600 s): a port that "
        "flaps again inside it is not stable; the full window is waited, then the "
        "transitions read once",
        "setting", False),
    "modules/heal/bounce.py::_verify": _w(
        "the OSPF adjacency on the bounced port to reach FULL, read every POLL_S",
        "within OSPF_FULL_S, 2.5 times OSPF's 40 s default dead interval (reasoned, not "
        "measured)",
        "reasoned", True, ("POLL_S",)),
    "modules/heal/bounce.py::_watch": _w(
        "a new session to the device to open after the bounce, tried every POLL_S",
        "within SETTLE_BOUND_S, 2.5 times the larger measured settle (39 s, IOS's confirm "
        "path; the operator's trial, 2026-11-07, C2424)",
        "measured", True, ("POLL_S",)),
    "modules/heal/detect.py::_loop": _w(
        "the detect runner's next pass, or a wake",
        "PASS_SECONDS, a quarter of the lab's 120 s grace period, so a second read is made "
        "within 30 s of its due time",
        "cadence", True, ("PASS_SECONDS",)),
    "modules/heal/detect.py::stop": _w(
        "the detect runner's thread to end on stop",
        "5 s, reasoned: the thread is woken first and a pass ends quickly; the process stops "
        "either way",
        "reasoned", True),
    "modules/heal/diagnose.py::_read_all": _w(
        "the interval between two reads of an interface's error counters, so a rate is a "
        "difference",
        "DELTA_SECONDS, 10 s, section 19.3's figure; to be measured (H18)",
        "reasoned", False, ("DELTA_SECONDS",)),
    "modules/heal/diagnose_reach.py::_check_hop": _w(
        "the interval between a hop's two counter reads",
        "diagnose's DELTA_SECONDS, the same rate as `_read_all`",
        "reasoned", False, ("DELTA_SECONDS",)),
    "modules/heal/resubscribe.py::_close_and_wait": _w(
        "the device's telemetry connection that read Disconnecting to be gone after the "
        "collector's session was closed, read every GONE_POLL_S",
        "within GONE_BOUND_S, reasoned (the device's TCP stack sees the reset at once; six "
        "polls); the first run's took_s sets it (C3643)",
        "reasoned", True, ("GONE_POLL_S", "GONE_BOUND_S")),
    "modules/heal/resubscribe.py::_held": _w(
        "the device between removing every chosen receiver and adding them back",
        "WAIT_S, the operator's sequence: 13 s on the hand run that brought subscription 102 "
        "back, \"about 10 s\" (2026-11-08, C2838's amendment)",
        "measured", False, ("WAIT_S",)),
    "modules/heal/resubscribe.py::verify": _w(
        "a re-subscribed stream to be back: the device's new connection and the collector's "
        "bytes growing on a new session (every DIRECT_POLL_S), or without the bytes today's "
        "three checks (every POLL_S)",
        "within VERIFY_BOUND_S, 2.5 times the 116 s measured from the re-add to the stream's "
        "data (MEASURED_BACK_S, 2026-11-08); ends as soon as the checks pass",
        "measured", True, ("POLL_S", "DIRECT_POLL_S", "VERIFY_BOUND_S")),
    "modules/heal_notice.py::_cleared": _w(
        "an incident's symptom to stay quiet through the network's flap window before it is "
        "called cleared by itself",
        "the per-network setting heal_flap_minutes (10 minutes by default)",
        "setting", False),
    "modules/heal_notice.py::notice": _w(
        "the incident's diagnosis and analysis threads to finish, each up to its caller's "
        "wait, then one shared follow-up deadline",
        "the caller's diag_wait, wait_s and follow_s; each ends when its thread does",
        "caller", True),
    # ── Deploys and device operations ────────────────────────────────────────────────────
    "modules/pipeline.py::_watch_bgp_hold": _w(
        "BGP's hold time to pass after the push, then one read of the sessions: a session a "
        "change broke without resetting TCP reads Established until it expires (C178)",
        "the hold time configured on the device for each peer (`convergence.bgp_hold_times`, "
        "neighbor then group then process), IOS's 180 s when none is set; skipped for a "
        "program that cannot reach BGP (`verify_scope.bgp_reach`, R3)",
        "device timer", False),
    "modules/nsot/convergence.py::wait_for": _w(
        "a protocol, an interface set or the route table to settle after a push, read every "
        "interval after an initial wait until it holds or the window ends",
        "the check's settle window (`window_for`: the installation's verify_settle_windows, "
        "inherited by every network; OSPF 45 s, BGP 60 s, RIP 90 s by default)",
        "setting", True),
    "modules/nsot/privileged.py::apply.work": _w(
        "a cleared ARP table to fill back to its count before, polled every second",
        "ARP_SETTLE, about 2.5 times the probe's one-second resolution (it measured 0 s at "
        "that resolution; no date kept)",
        "reasoned", True),
    "modules/nsot/privileged.py::send_clear": _w(
        "a cleared BGP session to verify, read every CLEAR_POLL_S",
        "within the plan's bound_s (the operation's measured bound, in its plan)",
        "caller", True, ("CLEAR_POLL_S",)),
    "modules/nsot/privileged.py::send_reset": _w(
        "a reset neighbour table to verify, read every RESET_POLL_S",
        "within the plan's bound_s (the operation's measured bound, in its plan)",
        "caller", True, ("RESET_POLL_S",)),
    "modules/nsot/reload_op.py::_verify_read": _w(
        "a reloaded device's verify read to succeed, with pauses of VERIFY_PAUSES_S",
        "within VERIFY_BOUND_S, the operator's about 3 minutes (2026-11-01)",
        "measured", True),
    "modules/nsot/reload_op.py::_wait_for_ssh": _w(
        "a reloaded device to answer on SSH's port, tried every POLL_S",
        "within its caller's bound",
        "caller", True, ("POLL_S",)),
    "modules/device_reload.py::reload_device": _w(
        "the transport to close after a reload is sent, polled every poll",
        "the caller's poll and count",
        "caller", True),
    "modules/nsot/credential_rotation.py::verify_with_retry": _w(
        "one more proving login after a timeout, and a short backoff between other retries",
        "VERIFY_TIMEOUT_RETRY_S, about 2.5 times the 12 s the in-app verify of a lab switch "
        "took (2026-10-13 00:59 UTC, its constant's comment); the backoff 2 s, then 4 s, "
        "reasoned",
        "measured", False, ("VERIFY_TIMEOUT_RETRY_S",)),
    "modules/nsot/device_ops.py::acquire": _w(
        "a lock holder's record to be written, between probes of it",
        "PROBE_WAIT_S, 20 ms, reasoned: a holder writes its record right after it takes the "
        "lock (C987, CONCURRENCY_AUDIT R26)",
        "reasoned", True, ("PROBE_WAIT_S",)),
    "modules/nsot/fleet_change.py::run_waves": _w(
        "the settle between two waves of a fleet change",
        "the person's settle_s option for that change",
        "setting", False),
    "modules/nsot/logging_path.py::watch": _w(
        "each device's logging-path token to arrive in Loki, read every poll",
        "within the caller's wait after the last send",
        "caller", True),
    "modules/nsot/oob_onboard.py::_answering": _w(
        "the new key's settle, then the device to answer on SSH through the relay, tried "
        "every answer_every_s",
        "the onboarding's Timings: settle_until, then answer_bound_s",
        "caller", True),
    "modules/nsot/console_ztp.py::_Console.__init__": _w(
        "a console run's whole bound, as its deadline",
        "the caller's bound_s",
        "caller", True),
    "modules/nsot/console_transport.py::CommandBridge._closed": _w(
        "a closed bridge's exit status",
        "EXIT_WAIT_S, unmeasured: sshd sends the status with the close, so it is normally "
        "there already",
        "reasoned", True, ("EXIT_WAIT_S",)),
    "modules/nsot/ztp.py::dns_answerers": _w(
        "every answer to one broadcast DNS query on the segment",
        "the caller's timeout: every answerer is collected until it ends",
        "caller", False),
    "modules/nsot/ztp_relayed.py::unicast_answers": _w(
        "every answer to one unicast DNS query",
        "the caller's timeout: every answerer is collected until it ends",
        "caller", False),
    "modules/nsot/hooks.py::run_post_commit._runner": _w(
        "a post-commit hook's thread to finish",
        "the hook's own declared timeout",
        "caller", True),
    "modules/nsot/hooks.py::wait_for_hooks": _w(
        "every pending post-commit hook to finish",
        "the caller's timeout",
        "caller", True),
    "modules/connection.py::open_ssh": _w(
        "the pause before the one retry of an SSH connect that failed before anything was "
        "sent (C698)",
        "CONNECT_RETRY_PAUSE_S, 2 s, reasoned: long enough for a transient refusal to pass",
        "reasoned", False, ("CONNECT_RETRY_PAUSE_S",)),
    "modules/connection.py::session_reaper.worker": _w(
        "the idle-session reaper's next pass",
        "the reaper's interval",
        "cadence", False),
    # ── Background loops ─────────────────────────────────────────────────────────────────
    "modules/arrival_watch.py::_loop": _w(
        "the arrival watch's next look", "its interval (`_every`)", "cadence", False),
    "modules/attention_store.py::run": _w(
        "the next source due, or a wake, at least 0.2 s apart so a clock step cannot spin",
        "the soonest source's own cadence", "cadence", True),
    "modules/drift_check.py::DriftChecker._loop": _w(
        "the soonest network's drift check, or a trigger, at least once a minute",
        "each network's own schedule; a minute so a network added is noticed",
        "cadence", True),
    "modules/drift_check.py::DriftChecker.stop": _w(
        "the drift scheduler's thread to end on stop",
        "5 s, reasoned: the thread is triggered first", "reasoned", True),
    "modules/invalidation.py::heartbeat_loop": _w(
        "the next heartbeat to open pages",
        "HEARTBEAT_SECONDS, half the fastest reader's 60 s interval, so \"live updates "
        "stopped\" is drawn within 75 s",
        "cadence", False, ("HEARTBEAT_SECONDS",)),
    "modules/nsot/scheduled_rotation.py::_loop": _w(
        "the rotation timer's next tick",
        "TICK_SECONDS, a twelfth of the shortest (whole-hour) preferred window",
        "cadence", False, ("TICK_SECONDS",)),
    "modules/prometheus_targets.py::_keeper_loop": _w(
        "an inventory change to regenerate the targets, or the backstop; then a debounce",
        "KEEPER_BACKSTOP_SECONDS, the job-health reader's own 300 s interval; "
        "KEEPER_DEBOUNCE_SECONDS so a burst of writes is one regeneration",
        "cadence", True, ("KEEPER_BACKSTOP_SECONDS", "KEEPER_DEBOUNCE_SECONDS")),
    "modules/reader_job.py::_loop": _w(
        "a reader's next run: its interval, or its backoff while its dependency is not "
        "answering (rule 14)",
        "each reader's declared interval and start grace", "cadence", True),
    "modules/reader_job.py::_supervise_loop": _w(
        "the supervisor's next look at the reader threads",
        "SUPERVISE_EVERY_SECONDS, the shortest reader interval (5 s)",
        "cadence", True, ("SUPERVISE_EVERY_SECONDS",)),
    "modules/reader_wakes.py::_after.go": _w(
        "a reader's run in progress to end before a wake runs it, polled every 0.5 s",
        "AFTER_BOUND_S, 2.5 times the slowest reader's measured run (8 to 9 s, 2026-09-28) "
        "rounded up to a minute",
        "measured", True, ("AFTER_BOUND_S",)),
    # ── The AI ───────────────────────────────────────────────────────────────────────────
    "modules/ai/anthropic_adapter.py::send": _w(
        "the provider's asked wait before a retry",
        "the provider's retry-after, refused past MAX_WAIT_S", "reasoned", False),
    "modules/ai/gateway.py::_await_batch": _w(
        "a batch to end, its state read every BATCH_POLL_S",
        "within the batch's bound, which its words name", "reasoned", True,
        ("BATCH_POLL_S",)),
    "modules/ai/presses.py::_Slot.claim": _w(
        "a press's lock to come free, asked every POLL_S",
        "within the caller's wait_s", "caller", True, ("POLL_S",)),
    # ── The SDN controller and its apps ──────────────────────────────────────────────────
    "modules/apps/post_check.py::wait": _w(
        "the switches, the links and every enabled app's /health after a restart",
        "the caller's poll and bound, which the bound's words name", "caller", True),
    "modules/sdn/closed_loop.py::collect_threat_data": _w(
        "the interval between two port reads, so a rate is a difference",
        "the caller's interval", "caller", False),
    "modules/sdn/drivers/base.py::ControllerDriver._http": _w(
        "a controller's answer, retried while the deadline allows",
        "the connection's timeout, or a shorter one given", "caller", True),
    "modules/sdn/drivers/base.py::ControllerDriver._pause": _w(
        "the pause before a retried read", "RETRY_PAUSE, reasoned", "reasoned", False,
        ("RETRY_PAUSE",)),
    "modules/sdn/false_positives.py::read_live": _w(
        "the interval between two passes", "the caller's interval", "caller", False),
    "modules/sdn/flow_ops.py::counters": _w(
        "the interval between two counter samples", "the caller's interval", "caller", False),
    "modules/sdn/flow_ops.py::verify_installed": _w(
        "installed flows and meters to read back, a pause between reads",
        "the caller's reads and pause", "caller", True),
    "modules/sdn/loop.py::schedule": _w(
        "the SDN loop's next pass, or its stop", "the loop's interval", "cadence", True),
    "modules/sdn/openflow_config.py::agent_reads_back": _w(
        "the switch's agent to read the configuration back, VERIFY_READS reads apart",
        "VERIFY_PAUSE, reasoned", "reasoned", True, ("VERIFY_PAUSE",)),
    "modules/sdn/openflow_config.py::seen_by_controller": _w(
        "the controller's switch list to hold the datapath, VERIFY_READS reads apart",
        "VERIFY_PAUSE, reasoned", "reasoned", True, ("VERIFY_PAUSE",)),
    "modules/jobs/mutate.py::run_mutants": _w(
        "a mutation step's whole bound, as its deadline",
        "the per-mutant bound from the run's own baseline times the mutants chosen",
        "measured each run", True),
    "modules/jobs/runner.py::_Watch.__enter__": _w(
        "a job's code bound, as its deadline", "the caller's bound", "caller", True),
    # ── Host helpers and scripts ─────────────────────────────────────────────────────────
    "deploy/collector/mercury-collector-close::close": _w(
        "a closed session to be gone from `ss`, read every GONE_POLL_S",
        "within the helper's GONE_BOUND_S, reasoned (C3115: the kernel aborts the socket "
        "before `ss -K` returns)",
        "reasoned", True, ("GONE_POLL_S",)),
    "deploy/collector/mercury-collector-close::sleep": _w(
        "the helper's one sleep, for `close`'s read-back", "its caller's (`close`)",
        "caller", False),
    "deploy/controller/mercury-ryu-apply::restart": _w(
        "Ryu to answer after its unit restarts, polled every POLL_S",
        "within UP_BOUND_S, 2.5 times the 30 s within which Ryu answered after its process "
        "started, measured at the controller's reboot test of 2026-11-11",
        "measured", True, ("POLL_S",)),
    "scripts/nmas-ci-dispatch::dispatch": _w(
        "a dispatched run to appear in the runs list, asked every START_POLL_S",
        "for up to START_BOUND_S: run #4's dispatch showed within about 10 s (2026-10-14)",
        "measured", True, ("START_POLL_S",)),
    "scripts/nmas-deploy::_wait_for_ci": _w(
        "the exact sha's CI verdict, asked every WAIT_POLL_S",
        "within WAIT_BOUND_S, which its words name; 110 s keeps a run's calls few",
        "reasoned", True, ("WAIT_POLL_S",)),
    "scripts/nmas-deploy::restart_checkout_units": _w(
        "each restarted unit to run a new main process", "the caller's timeout and interval",
        "caller", True),
    "scripts/nmas-deploy::wait_for_ready": _w(
        "the app's /health to say ready after its restart", "the caller's timeout and interval",
        "caller", True),
    "scripts/nmas-deploy::wait_for_running": _w(
        "the app to answer from a process that restarted", "the caller's timeout and interval",
        "caller", True),
    "scripts/nmas-gate::run_bounded_to_file": _w(
        "the gate's suite process, then a TERM's 10 s grace",
        "the caller's bound (the suite's measured bound)", "caller", True),
    "scripts/nmas-harness::wait_ready": _w(
        "every bridge connected to the controller, read every POLL_S",
        "within READY_BOUND_S, 2.5 times the 4.9 s measured on the laptop (2026-11-07), "
        "rounded up to 20 s", "measured", True, ("POLL_S",)),
    "scripts/nmas-netbox-backup::_Session.close": _w(
        "psql to exit after its COMMIT", "30 s, reasoned: it exits on its input closing",
        "reasoned", True),
    "scripts/nmas-netbox-restore-test::restore_and_count": _w(
        "the scratch postgres to answer pg_isready, then its entrypoint's one restart",
        "1 s polls; then a fixed 2 s for the restart after init, unclassified: the full wait, "
        "safe by default",
        "unclassified", False),
    "scripts/nmas-post-deploy-check::detection_lines": _w(
        "detection's first good read since the start, asked every DETECTION_POLL_SECONDS",
        "detection reads every 5 s", "cadence", True, ("DETECTION_POLL_SECONDS",)),
    "scripts/nmas-pregate::_bounded": _w(
        "a pre-gate step's process, then a 15 s grace after TERM", "the caller's bound_s",
        "caller", True),
    "scripts/nmas-pregate::run_hook": _w(
        "a hook's process", "the caller's bound_s", "caller", True),
    "scripts/nmas-pregate::wait_for_no_gate": _w(
        "a running gate to end before the tests start", "the caller's every_s and bound_s",
        "caller", True),
    "scripts/nmas-tier2-probe::measure": _w(
        "an ARP table, OSPF and BGP to come back after a probe's step, polled every 1 or 2 s",
        "the probe's own bounds: it measures how long each took",
        "reasoned", True),
    "scripts/nmas-workers::hold_full": _w(
        "free memory for the workers, asked every WAIT_EVERY_S", "within the caller's bound_s",
        "caller", True, ("WAIT_EVERY_S",)),
}
