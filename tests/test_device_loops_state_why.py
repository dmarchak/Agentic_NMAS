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
    ("modules/ai_assistant.py", "run_chat.execute_tool"): (
        "one_device", "the `execute_command*` tools retry one device's session once and "
                      "run a list of commands on it"),
    ("modules/bulk_ops.py", "_run_single_enable_command"): (
        "one_device", "answers one device's interactive prompts"),
    ("modules/bulk_ops.py", "BulkOperationManager._execute_worker.worker"): (
        "one_device", "a worker draining the bulk queue; several run at once, so the "
                      "operation IS concurrent (5 or 3 workers)"),
    ("modules/pipeline.py", "_stage_pre_snapshot"): ("sequential", _ONE_RUN),
    ("modules/pipeline.py", "_stage_post_snapshot"): ("sequential", _ONE_RUN),
    ("modules/pipeline.py", "_capture_failure_state"): ("sequential", _ONE_RUN),
    ("modules/pipeline.py", "_stage_rollback"): ("sequential", _ONE_RUN),
    ("modules/nsot/credential_rotation.py", "push_rotation"): (
        "one_device", "the rotation's commands on the one session it verifies on"),
    ("app.py", "refresh_hostnames"): (
        "unstated", "C199: a READ per device (a session each, then `find_prompt`), "
                    "should be concurrent"),
    ("app.py", "ai_device_context._warm"): (
        "unstated", "C199: opens a pooled session per device in a background thread; "
                    "should be concurrent, or retired with the pool warm-up"),
    ("app.py", "configure_interfaces"): (
        "unstated", "C199: a READ per device for the Configure tab; should be concurrent "
                    "(the Configure forms are decision 2's track)"),
    ("app.py", "configure_networks"): (
        "unstated", "C199: a READ per device for the Configure tab, as "
                    "configure_interfaces"),
    ("scripts/nmas-golden-state", "read_fleet"): (
        "unstated", "C199: a READ per device (one session each); should be concurrent"),
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
    ("modules/nsot/freshness.py", "check"): (
        "unstated", "C199: a READ, one Oxidized GET per device (measured 4 ms each)"),
    ("modules/nsot/startup_check.py", "run_check"): (
        "unstated", "C199: a READ, an SSH session and two shows per device, hourly"),
    ("modules/netbox_client.py", "_sync_list_to_netbox_impl"): (
        "unstated", "C199: WRITES to NetBox per device; the cable pass follows the "
                    "upserts so both ends exist, and shared objects (site, VRF, prefix) "
                    "are created on first use, so order may matter: to be decided"),
    ("modules/netbox_client.py", "sync_all_lists_to_netbox"): (
        "unstated", "C199: one list after another, \"sequentially\" with no reason given"),
    ("routes/onboard.py", "pending"): (
        "unstated", "C199: a READ, two Kea calls per pending ZTP device"),
    ("scripts/nmas-heartbeat-rules", "main"): (
        "unstated", "C199: a READ, two Loki queries per device, hourly"),
    ("scripts/nmas-check-startup-applies", "main"): (
        "unstated", "C199: a READ, ssh to the lab host per device"),
    ("scripts/oxidized-to-config.sh", "reconcile and diff loops"): (
        "unstated", "C199: reads per device over ssh to the lab host; the commit after "
                    "them is one"),
    ("scripts/nmas-netbox-repair-addresses", "walk / plan / apply"): (
        "unstated", "C199: NetBox reads, then writes, one device after another"),
    ("scripts/nmas-netbox-status-reset", "_plan / apply"): (
        "unstated", "C199: NetBox reads, then writes"),
    ("scripts/nmas-netbox-mask-context", "main"): (
        "unstated", "C199: a NetBox write and read-back per device"),
    ("scripts/nmas-netbox-untagged", "main"): (
        "unstated", "C199: a NetBox read per recorded object"),
}


def _files():
    for d in ("modules", "routes"):
        for base, _dirs, names in os.walk(os.path.join(ROOT, d)):
            for f in sorted(names):
                if f.endswith(".py"):
                    yield os.path.join(base, f)
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
        assert ("app.py", "refresh_hostnames") in found
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

    def test_the_surveyed_files_exist(self):
        """A survey entry naming a file that is gone is a ghost."""
        for path, _fn in SURVEYED:
            assert os.path.exists(os.path.join(ROOT, path)), path

    def test_the_deploy_batch_stays_sequential_for_its_breaker(self):
        """The one ordering that IS the safety: the default must not drift to
        concurrent without this test being read."""
        from modules.settings_schema import DEFAULTS

        assert DEFAULTS.get("deploy_max_workers", 1) == 1
