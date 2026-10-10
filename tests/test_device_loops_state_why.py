"""OPERATIONS ACROSS DEVICES RUN CONCURRENTLY; a serial one states why (the
operator's standing rule, 2026-09-29, after C188 measured Save All at 101 s
read one device after another and 40.9 s at once).

- READS across devices run concurrently by default. A serial read loop is a
  defect unless it states why.
- WRITES across devices run concurrently only where nothing depends on
  order. The deploy batch is sequential ON PURPOSE: its circuit breaker
  stops a bad change after the first device it breaks, and a concurrent push
  would reach the whole fleet before anything could notice. The ordering IS
  the safety.
- Any sequential multi-device operation states why, the way a green toast
  must (`test_results_are_drawn.GREEN_TOASTS`).

What is mechanised, and what cannot be:
- `SCANNED`: every loop that calls the device layer DIRECTLY (an SSH open or
  a command sent) in the program and its scripts, found by parsing, exact
  both ways. Each is `sequential` with its stated reason, `one_device` (a
  loop over one device's commands or retries, not across devices), or
  `unstated` (registered as C199 with the class the rule gives it).
- `SURVEYED`: loops the scan CANNOT see, because the per-device work sits
  behind a call (`run_batch` through `run_one`, the startup check through
  `check`, the freshness reader through HTTP to Oxidized, NetBox REST per
  object). Found by the 2026-09-29 survey, the weaker form: a list only as
  complete as the survey that made it, and it says so.
"""

import ast
import os

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: A call to one of these opens a session to a device or sends it a command.
DEVICE_IO = {"get_persistent_connection", "with_temp_connection", "open_ssh",
             "ConnectHandler", "run_device_command", "verify_device_connection",
             "is_device_online", "_read_running", "send_command", "send_config_set",
             "send_command_timing"}

KINDS = {"sequential", "one_device", "unstated"}

_ONE_RUN = ("one device per run: `routes/deploy.py` `_deploy_one` hands the pipeline ONE "
            "device, and the batch above it is sequential for its circuit breaker")

#: (file, function) -> (kind, why). Exact both ways against the scan.
SCANNED = {
    # (run_chat.execute_tool's loop left 2026-10-08: the `execute_command*` tools read through
    # the reads engine, concurrent across devices by `fanout.read_each`; C548, R5.)
    ("modules/bulk_ops.py", "_run_single_enable_command"): (
        "one_device", "answers one device's interactive prompts"),
    ("modules/nsot/reload_op.py", "read_device.read"): (
        "one_device", "the image files ONE device's `show version` and `show boot` name, each "
                      "a `dir` on that device's one session (Reload's preview, P.14)"),
    ("modules/bulk_ops.py", "BulkOperationManager._execute_worker.worker"): (
        "one_device", "a worker draining the bulk queue; several run at once, so the "
                      "operation IS concurrent (5 or 3 workers)"),
    ("modules/pipeline.py", "_stage_pre_snapshot"): ("sequential", _ONE_RUN),
    ("modules/pipeline.py", "_stage_post_snapshot"): ("sequential", _ONE_RUN),
    ("modules/pipeline.py", "_capture_failure_state"): ("sequential", _ONE_RUN),
    ("modules/pipeline.py", "_stage_rollback"): ("sequential", _ONE_RUN),
    ("modules/nsot/credential_rotation.py", "push_rotation"): (
        "one_device", "the rotation's commands on the one session it verifies on"),
    ("app.py", "ai_device_context._warm"): (
        "sequential", "C202: every open goes through the persistent pool, which holds ONE "
                      "lock across open_ssh, so concurrent opens would queue on it"),
    ("app.py", "configure_interfaces"): (
        "sequential", "C202: persistent-pool sessions, opened under the pool's one lock, so "
                      "concurrency would queue on it"),
    ("app.py", "configure_networks"): (
        "sequential", "C202: persistent-pool sessions, opened under the pool's one lock, as "
                      "configure_interfaces"),
    ("scripts/netmiko_timing_probe.py", "main"): (
        "one_device", "a timing probe comparing two modes on one device: overlapping "
                      "them would measure each against the other"),
    ("scripts/nmas-capture-output", "capture.work"): (
        "one_device", "the commands captured on one device's session"),
}

#: Loops the scan cannot see (the work is behind a call). (file, function)
#: -> (kind, why), from the 2026-09-29 survey.
SURVEYED = {
    ("modules/nsot/deploy.py", "run_batch"): (
        "sequential", "the circuit breaker: `CircuitBreaker` stops the batch after the "
                      "first device a bad change breaks, and `max_workers()` says vIOS-L2 "
                      "has few vty lines; a concurrent branch exists behind "
                      "`deploy_max_workers` (default 1)"),
    ("modules/netbox_client.py", "remove_list_from_netbox._run"): (
        "sequential", "`_REMOVAL_ORDER`: terminations before tunnels, contained objects "
                      "before containers, so referential integrity holds"),
    ("modules/netbox_client.py", "_sync_list_to_netbox_impl"): (
        "sequential", "WRITES whose order matters (the operator's decision on C199, "
                      "2026-09-29): shared objects (sites, VLANs, prefixes, VRFs) are "
                      "created on first encounter, so concurrent devices would race to "
                      "create one and duplicate it (C133), and the cable pass needs every "
                      "device's interfaces first"),
    ("modules/netbox_client.py", "sync_all_lists_to_netbox"): (
        "sequential", "lists share NetBox objects as devices do, created on first "
                      "encounter, so concurrent lists would race to create them (C199's "
                      "decision)"),
    ("scripts/nmas-check-startup-applies", "main"): (
        "sequential", "every read is an ssh to ONE host, the lab VM, not to the devices: a "
                      "burst of them meets sshd's MaxStartups (10 unauthenticated by "
                      "default), so serial is the safe default for a single target"),
    ("scripts/oxidized-to-config.sh", "reconcile and diff loops"): (
        "sequential", "reads over ssh to ONE host, the lab VM (MaxStartups, as "
                      "nmas-check-startup-applies), before a single commit; a person reads "
                      "the diff in the order it prints"),
    ("scripts/nmas-netbox-repair-addresses", "walk / plan / apply"): (
        "sequential", "not a loop over network devices: one NetBox's records, a one-off "
                      "repair run by hand whose writes read back one by one"),
    ("scripts/nmas-netbox-status-reset", "_plan / apply"): (
        "sequential", "not a loop over network devices: one NetBox's records, a one-off "
                      "correction run by hand"),
    ("scripts/nmas-netbox-mask-context", "main"): (
        "sequential", "not a loop over network devices: one NetBox's records, each write "
                      "read back before the next"),
    ("scripts/nmas-netbox-untagged", "main"): (
        "sequential", "not a loop over network devices: one NetBox's recorded objects, a "
                      "one-off audit run by hand"),
}


def _files():
    yield from tracked("modules", "routes", suffix=".py")
    yield os.path.join(ROOT, "app.py")
    scripts = os.path.join(ROOT, "scripts")
    for f in sorted(os.listdir(scripts)):
        if os.path.isfile(os.path.join(scripts, f)):
            yield os.path.join(scripts, f)


def _calls(node) -> set:
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
            if name in DEVICE_IO:
                out.add(name)
    return out


def scan_source(text: str, rel: str) -> set:
    """``{(rel, qualified function)}`` for every loop in *text* that calls
    the device layer directly."""
    found = set()

    def visit(node, qual):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(ch, qual + [ch.name])
                continue
            if isinstance(ch, (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp,
                               ast.DictComp, ast.GeneratorExp)) and _calls(ch):
                found.add((rel, ".".join(qual) or "<module>"))
            visit(ch, qual)

    visit(ast.parse(text), [])
    return found


def scan() -> tuple:
    found, parsed = set(), 0
    for path in _files():
        try:
            text = open(path, encoding="utf-8").read()
            found |= scan_source(text, os.path.relpath(path, ROOT))
            parsed += 1
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue                      # a shell script is not Python
    return found, parsed


class TestEverySerialDeviceLoopStatesWhy:
    def test_the_scan_is_exactly_the_declared_set(self):
        found, parsed = scan()
        assert parsed >= 170, parsed          # 191 measured, 2026-09-29
        new = sorted(found - set(SCANNED))
        assert new == [], (
            f"a loop over devices calls the device layer and is declared nowhere: {new}. "
            "A READ across devices runs concurrently; anything else states why here.")
        ghosts = sorted(set(SCANNED) - found)
        assert ghosts == [], f"declared and no longer found: {ghosts}"

    def test_the_scan_finds_something(self):
        found, _ = scan()
        assert ("app.py", "configure_interfaces") in found
        assert ("modules/pipeline.py", "_stage_rollback") in found
        assert len(found) >= 12

    def test_a_planted_serial_read_is_found(self):
        planted = ("def read_them(devices):\n"
                   "    for d in devices:\n"
                   "        with_temp_connection(d, lambda c: c.send_command('show clock'))\n")
        assert scan_source(planted, "x.py") == {("x.py", "read_them")}
        concurrent = ("def read_them(devices, pool):\n"
                      "    return [pool.submit(one, d) for d in devices]\n")
        assert scan_source(concurrent, "x.py") == set()

    def test_every_declaration_has_a_kind_and_a_reason(self):
        for table in (SCANNED, SURVEYED):
            for key, (kind, why) in table.items():
                assert kind in KINDS, key
                assert len(why.split()) >= 5, key
                if kind == "unstated":
                    assert why.startswith("C199"), key
                if kind == "sequential" and "C202" in why:
                    assert "lock" in why, key

    def test_the_surveyed_files_exist(self):
        """A survey entry naming a file that is gone is a ghost."""
        for path, _fn in SURVEYED:
            assert os.path.exists(os.path.join(ROOT, path)), path

    def test_the_deploy_batch_stays_sequential_for_its_breaker(self):
        """The one ordering that IS the safety: the default must not drift to
        concurrent without this test being read."""
        from modules.settings_schema import DEFAULTS

        assert DEFAULTS.get("deploy_max_workers", 1) == 1


class TestTheConvertedReadsRunAtOnce:
    """The READ loops the rule converted (2026-09-29): each through the one
    helper, `modules.fanout.read_each`, and gone from the declared serial set."""

    # modules/nsot/freshness.py's Oxidized read was converted too, and removed in Phase 3.
    CONVERTED = [("modules/nsot/startup_check.py", "read_each(lambda lr: check(lr[1])"),
                 ("app.py", "read_each(lambda d: with_temp_connection(d, get_hostname)"),
                 ("scripts/nmas-golden-state", "read_each(one, devices"),
                 ("routes/onboard.py", "read_each(_ztp.progress, ztp_rows"),
                 ("scripts/nmas-heartbeat-rules", "read_each(lambda h: gaps_from(")]

    def test_each_uses_the_helper(self):
        for path, call in self.CONVERTED:
            src = open(os.path.join(ROOT, path), encoding="utf-8").read()
            assert call in src, (path, call)

    def test_none_is_still_declared_serial(self):
        declared = {p for p, _f in set(SCANNED) | set(SURVEYED)}
        assert not declared & {"modules/nsot/startup_check.py",
                               "scripts/nmas-golden-state", "routes/onboard.py",
                               "scripts/nmas-heartbeat-rules"}

    def test_the_helper_runs_at_once_keeps_order_and_isolates_a_failure(self):
        import threading
        import time

        from modules.fanout import Failed, read_each

        state, mu = {"now": 0, "peak": 0}, threading.Lock()

        def slow(i):
            with mu:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            try:
                time.sleep(0.05 * (5 - i))            # the first finishes last
                if i == 2:
                    raise TimeoutError("unreachable")
                return i * 10
            finally:
                with mu:
                    state["now"] -= 1

        got = read_each(slow, range(5))
        assert state["peak"] == 5, "every read in flight at once"
        assert [g if not isinstance(g, Failed) else "F" for g in got] == [0, 10, "F", 30, 40]
        assert "TimeoutError: unreachable" == str(got[2])
        assert read_each(slow, []) == []
