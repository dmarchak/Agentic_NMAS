#!/usr/bin/env python3
"""First real runs of the NSoT deploy path against the reference lab.

Run this **on the NMAS**, from the repository root. It performs the four runs in
increasing order of blast radius and stops at the first failure.

    python3 scripts/nsot_first_runs.py 1          # preview only, all nine devices
    python3 scripts/nsot_first_runs.py 2          # single-device deploy, S4
    python3 scripts/nsot_first_runs.py 3 --force-rollback
    python3 scripts/nsot_first_runs.py 4          # mixed-platform batch of three

Run 1 is read-only and opens no session. Runs 2 and 4 write to devices and
prompt first. Run 3 deliberately breaks something to exercise rollback and
requires ``--force-rollback`` on top of the prompt.

Nothing here touches R1–R5 unless explicitly named: R5 is the PE and R3/R4 carry
BGP, so they stay out of runs 1–4 except as preview subjects.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SWITCHES = ["s1", "s2", "s3", "s4"]
ROUTERS = ["r1", "r2", "r3", "r4", "r5"]
ALL_DEVICES = ROUTERS + SWITCHES

#: Run 2/3 target. Gi0/1 on S4 is unused — `negotiation auto` only, no
#: switchport config, no address, no protocol — so a description touches no
#: forwarding path.
TARGET_DEVICE = "s4"
TARGET_INTERFACE = "GigabitEthernet0/1"


def _rule(title=""):
    print("\n" + "=" * 78)
    if title:
        print(title)
        print("=" * 78)


def _confirm(prompt: str) -> bool:
    print(f"\n{prompt}")
    return input("Type YES to proceed: ").strip() == "YES"


# ---------------------------------------------------------------------------
# Run 1 — preview only
# ---------------------------------------------------------------------------

def run_preview() -> int:
    """Build a render artifact for every device. Opens no session."""
    from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
    from modules.config import get_current_list_name, get_list_data_dir
    from modules.device import get_current_device_list, load_saved_devices
    from modules.nsot import approval, templates_repo
    from modules.nsot.render_artifact import build_artifact

    _rule("RUN 1 — preview only, all devices (read-only, no sessions opened)")

    list_name = get_current_list_name()
    repo = os.path.join(get_list_data_dir(list_name), "config_repo")
    templates_repo.seed_templates(repo)

    _name, csv_path = get_current_device_list()
    inventory = {d.get("hostname", ""): d for d in load_saved_devices(csv_path)}
    goldens = {e["hostname"]: e for e in _list_golden_configs()}

    print(f"list: {list_name}    devices in inventory: {len(inventory)}    "
          f"golden configs: {len(goldens)}")

    rows, problems = [], []
    for hostname in sorted(inventory) or ALL_DEVICES:
        entry = goldens.get(hostname)
        if entry is None:
            rows.append({"device": hostname, "template": "-", "deployable": False,
                         "why": "no golden config", "coverage": 0.0,
                         "unmodeled": "-", "approved": False})
            problems.append(f"{hostname}: no golden config")
            continue

        captured = _load_golden_config_file(entry["device_ip"]) or ""
        device = inventory.get(hostname, {})
        platform = device.get("device_type", "cisco_ios")
        template = templates_repo.template_for_device(repo, hostname, platform)

        artifact = build_artifact(hostname, captured, platform, template=template)
        approved = approval.is_approved(repo, template,
                                        {hostname: artifact.host_vars})
        if approved:
            artifact = build_artifact(hostname, captured, platform,
                                      template=template, template_approved=True,
                                      host_vars=artifact.host_vars)

        rows.append({
            "device": hostname,
            "template": template,
            "deployable": artifact.deployable,
            "why": "; ".join(artifact.blocking_reasons)[:60] or "-",
            "coverage": artifact.report.get("modeled_coverage", 0.0),
            "unmodeled": artifact.report.get("unmodeled", 0),
            "approved": approved,
        })
        if not artifact.deployable:
            problems.append(f"{hostname}: {'; '.join(artifact.blocking_reasons)}")

    _rule()
    print(f"{'device':8} {'template':26} {'deploy':>7} {'appr':>5} "
          f"{'cover':>7} {'unmod':>6}  why")
    print("-" * 78)
    for row in rows:
        print(f"{row['device']:8} {row['template'][:26]:26} "
              f"{str(row['deployable']):>7} {str(row['approved']):>5} "
              f"{row['coverage']:6.1f}% {str(row['unmodeled']):>6}  {row['why']}")

    deployable = sum(1 for r in rows if r["deployable"])
    print("-" * 78)
    print(f"{deployable}/{len(rows)} deployable")

    if problems:
        print("\nBlocking issues:")
        for problem in problems:
            print(f"  - {problem}")
        print("\nRun 1 is NOT clean. Do not proceed to run 2.")
        return 1

    print("\nRun 1 clean.")
    return 0


# ---------------------------------------------------------------------------
# Runs 2-4 — these reach devices
# ---------------------------------------------------------------------------

def _plan_and_report(hostnames: list) -> dict:
    """Build the deploy plan and print the per-device diff."""
    from routes.deploy import _artifact_for
    from modules.config import get_current_list_name
    from modules.nsot.deploy import merge_diff, prepare_device

    list_name = get_current_list_name()
    plan = {}
    for hostname in hostnames:
        built, error = _artifact_for(list_name, hostname)
        if built is None:
            print(f"  {hostname}: UNAVAILABLE — {error}")
            continue
        artifact, captured, device = built
        prepared = prepare_device(artifact)
        diff = merge_diff(prepared["config"], captured)

        print(f"\n  {hostname} ({device.get('device_type')}) via {artifact.template}")
        print(f"    will add ({len(diff['to_add'])}):")
        for line in diff["to_add"][:20]:
            print(f"      + {line}")
        print(f"    will NOT remove ({len(diff['removal_warnings'])}):")
        for line in diff["removal_warnings"][:20]:
            print(f"      ! {line}")
        plan[hostname] = {"artifact": artifact, "captured": captured,
                          "device": device, "diff": diff}
    return plan


def run_single_deploy(force: bool = False) -> int:
    """Run 2 — one interface description on S4."""
    _rule(f"RUN 2 — single-device deploy: {TARGET_DEVICE} {TARGET_INTERFACE} description")
    print("This WRITES to a device.")

    print("\nPre-deploy plan:")
    plan = _plan_and_report([TARGET_DEVICE])
    if TARGET_DEVICE not in plan:
        return 1

    if not force and not _confirm(f"Deploy to {TARGET_DEVICE}?"):
        print("Aborted by operator.")
        return 1

    from routes.deploy import _deploy_one
    from modules.config import get_current_list_name

    entry = {"artifact": plan[TARGET_DEVICE]["artifact"],
             "fresh": plan[TARGET_DEVICE]["captured"]}
    started = time.time()
    result = _deploy_one(entry, get_current_list_name(),
                         {TARGET_DEVICE: plan[TARGET_DEVICE]["device"]})
    elapsed = time.time() - started

    _rule("RESULT")
    print(json.dumps(result, indent=2, default=str))
    print(f"\nelapsed: {elapsed:.1f}s")
    print(f"golden commit: {result.get('golden_commit', '(none)')}")
    if result.get("pending_convergence"):
        print("not-yet-converged:")
        for note in result["pending_convergence"]:
            print(f"  {note}")
    return 0 if result.get("outcome") == "deployed" else 1


def run_rollback_demo(force: bool = False) -> int:
    """Run 3 — deliberately fail verification and show rollback."""
    _rule(f"RUN 3 — deliberate rollback on {TARGET_DEVICE}")
    print("This WRITES to a device and DELIBERATELY breaks verification.")
    print("It shuts the OSPF-bearing port during the settle window so the")
    print("neighbour count drops, verify fails, and rollback restores.")

    if not force:
        print("\nRefusing without --force-rollback.")
        return 1
    if not _confirm(f"Deliberately fail verification on {TARGET_DEVICE}?"):
        print("Aborted by operator.")
        return 1

    print("\nNot yet implemented as an automated run — see the note below.")
    print("The safe manual sequence is:")
    print(f"  1. capture `show run interface {TARGET_INTERFACE}` on {TARGET_DEVICE}")
    print("  2. start the deploy from the UI")
    print("  3. during the settle window, shut the OSPF-bearing port")
    print("  4. observe verify fail, rollback run, and startup re-saved")
    print("  5. re-capture and compare against step 1")
    return 1


def run_mixed_batch(force: bool = False) -> int:
    """Run 4 — one C8000v and two vIOS-L2, trivial change."""
    devices = ["r2", "s3", "s4"]
    _rule(f"RUN 4 — mixed-platform batch: {', '.join(devices)}")
    print("This WRITES to devices.")

    from modules.nsot.deploy import transport_for
    print("\nTransport decisions (made before any connection):")
    from modules.device import get_current_device_list, load_saved_devices
    _name, csv_path = get_current_device_list()
    inventory = {d.get("hostname"): d for d in load_saved_devices(csv_path)}
    netconf_attempts = 0
    for hostname in devices:
        platform = (inventory.get(hostname) or {}).get("_platform", "") or \
            (inventory.get(hostname) or {}).get("device_type", "")
        transport = transport_for(platform)
        print(f"  {hostname:4} platform={platform:14} transport={transport}")
        if transport == "netconf":
            netconf_attempts += 1
    print(f"\nNETCONF attempts planned against switches: "
          f"{sum(1 for h in devices if h.startswith('s') and transport_for((inventory.get(h) or {}).get('device_type','')) == 'netconf')}")

    print("\nPre-deploy plan:")
    plan = _plan_and_report(devices)
    if not force and not _confirm(f"Deploy to {', '.join(devices)}?"):
        print("Aborted by operator.")
        return 1

    from modules.nsot.deploy import CircuitBreaker, plan_batch, run_batch
    from routes.deploy import _capture_hash, _deploy_one
    from modules.config import get_current_list_name

    artifacts = [plan[h]["artifact"] for h in plan]
    confirmed = {h: _capture_hash(plan[h]["captured"]) for h in plan}
    fresh = {h: plan[h]["captured"] for h in plan}
    rows = {h: plan[h]["device"] for h in plan}

    batch = plan_batch(artifacts, confirmed, fresh)
    report = run_batch(batch,
                       lambda e: _deploy_one(e, get_current_list_name(), rows),
                       CircuitBreaker())

    _rule("RESULT")
    print(f"workers: {report['workers']} (1 = sequential)")
    for row in report["results"]:
        print(f"  {row['device']:4} {row['outcome']:20} {row.get('reason','')[:50]}")
    commits = {r.get("golden_commit") for r in report["results"]
               if r.get("golden_commit")}
    print(f"\ngolden commits: {commits or '(none)'}")
    print(f"every device accounted for: {report['total'] == len(plan)}")
    return 0 if not report["by_outcome"].get("failed") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=int, choices=[1, 2, 3, 4])
    parser.add_argument("--force-rollback", action="store_true",
                        help="required for run 3, which deliberately breaks verification")
    parser.add_argument("--yes", action="store_true",
                        help="skip the interactive confirmation (use with care)")
    args = parser.parse_args()

    if args.run == 1:
        return run_preview()
    if args.run == 2:
        return run_single_deploy(force=args.yes)
    if args.run == 3:
        return run_rollback_demo(force=args.force_rollback)
    return run_mixed_batch(force=args.yes)


if __name__ == "__main__":
    sys.exit(main())
