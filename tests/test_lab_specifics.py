"""Nothing lab- or person-specific in the product, except where declared
(the operator, 2026-10-02: the public release must contain nothing that exists
only because of the operator's lab or personal setup, and Stage 10 must be a
check, not an archaeology dig).

The standing rule (CLAUDE.md, Conventions): anything lab- or person-specific
lives in the lab-tooling area outside the product, or is an OPTIONAL
integration that is off unless configured, or is a value in the local,
gitignored configuration, never a hard-coded assumption in the product.

This check scans the PRODUCT (modules, routes, app.py, templates, the app's
own scripts, scripts/ and deploy/) for the lab's names and values:
containerlab, clab, vrnetlab, the lab's name (rcn-lab), the course code, the
lab's dashboard UIDs and its addresses (10.255.x). Every file that holds one is
in ``INVENTORY`` with the number of such lines, its category and its Stage 10
disposition, and that table is EXACT both ways:
- a file not in it that gains a line fails (a new lab-specific assumption,
  written without being declared);
- a file whose count grows fails (declare the new line, or do not write it);
- a file whose count shrinks fails until its number is lowered, so the
  inventory always says what is left;
- an entry naming a file with no such line fails (a ghost).
Stage 10's acceptance: the release tree holds no line this check finds (the optional
lab integrations are off unless configured, and out of the release).
The rest of the inventory (access setup, records, fixtures, hardware tuning)
is docs/NSOT_STAGE10_PLAN.md section 6.0b, which points here for the code.
"""

import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERN = re.compile(r"containerlab|\bclab\b|\bclab[_-]|vrnetlab|\brcn[-_]|csci\s?5840|"
                     r"\b10\.255\.\d|rcn-lab-overview|rcn-lab1-snmp", re.I)
#: The product: its code and the manual it ships (docs/manual). The project's
#: records (the register, the write-up, plans, runbooks) stay in this
#: repository and out of the release (NSOT_STAGE10_PLAN 6.0b), so they are
#: not scanned.
SCOPE = ("modules", "routes", "app.py", "templates", "static/js", "scripts", "deploy",
         "config_templates", "docs/manual")

# Dispositions: the operator's four (2026-10-02).
OPTIONAL = "optional lab integration (off unless configured; documented; out of the release)"
MOVE = "move to the lab-tooling area (lab/), out of the product"
GENERIC = "make generic (the mechanism stays; the lab's name or value goes)"
REMOVE = "remove"

LAB_PLATFORM = "lab platform"
LAB_VALUES = "the lab's specifics"
HARDWARE = "hardware-specific workaround"
ACCESS = "the operator's access setup"

#: ``path: (lines, category, disposition, what it is)``. Measured 2026-10-02.
INVENTORY = {
    "scripts/oxidized-to-config.sh": (73, LAB_PLATFORM, MOVE, "clab-sync: writes containerlab startup files"),
    "scripts/nmas-clab-targets": (22, LAB_PLATFORM, MOVE, "clab-sync's map of devices to labs"),
    "routes/clab.py": (4, LAB_PLATFORM, OPTIONAL, "/clab/sync_targets, the map clab-sync asks for"),
    "routes/__init__.py": (2, LAB_PLATFORM, OPTIONAL, "registers the clab blueprint"),
    "routes/jobs.py": (2, LAB_PLATFORM, OPTIONAL, "clab-sync wakes the lab-startup reader"),
    "modules/lab_startup.py": (14, LAB_PLATFORM, OPTIONAL, "C303: lab startup files against goldens"),
    "modules/readers/lab_startup.py": (3, LAB_PLATFORM, OPTIONAL, "its reader"),
    "modules/attention.py": (6, LAB_PLATFORM, OPTIONAL, "the lab-startup Needs attention rows"),
    "modules/job_health.py": (21, LAB_PLATFORM, OPTIONAL, "clab-sync's job row and lab rows"),
    "modules/settings_scope.py": (3, LAB_PLATFORM, OPTIONAL,
                                  "names the clab_* settings as the per-network lab group "
                                  "(P.8 step 1), and clab_declared_unmapped as host-wide "
                                  "(step 4); they leave with the optional integration"),
    "modules/settings_schema.py": (29, LAB_PLATFORM, OPTIONAL,
                                   "clab_* settings (some default to the lab's paths); "
                                   "netbox_excluded_vrfs defaults to the lab's clab-mgmt"),
    "modules/nsot/credential_rotation.py": (82, LAB_PLATFORM, OPTIONAL,
                                            "the persistence chain's clab-sync and startup-file stages; "
                                            "vrnetlab's injected user (the save and read-back are generic)"),
    # Found by widening the pattern to any rcn- or rcn_ name (2026-10-03, C374: the break-glass
    # file carried the lab's name and `rcn-lab` alone did not see it). The topology renderer is
    # generic (LLDP over Prometheus, drawn as SVG) and carries the lab's name.
    "deploy/topology/rcn-topology.py": (10, LAB_VALUES, GENERIC,
                                        "the topology renderer's name and its RCN_ settings"),
    "modules/host_steps.py": (7, LAB_VALUES, GENERIC, "the renderer's install step, by its name"),
    "routes/topology_view.py": (2, LAB_VALUES, GENERIC, "the renderer's name in its docstring"),
    "static/js/gen/partials__topology_service.1.js": (1, LAB_VALUES, GENERIC,
                                                      "the renderer's name in a message"),
    "templates/index.html": (1, LAB_VALUES, GENERIC, "the renderer's name on the topology tab"),
    "templates/partials/topology_service.html": (2, LAB_VALUES, GENERIC,
                                                 "the renderer's name in its panel"),
    "modules/nsot/rotate_op.py": (1, LAB_PLATFORM, OPTIONAL,
                                  "the stepper's persist step names the chain's clab stages "
                                  "(C370), as credential_rotation runs them"),
    "modules/nsot/bootstrap_config.py": (37, HARDWARE, GENERIC,
                                         "vrnetlab's boot behaviour: console replay, the injected user"),
    "modules/nsot/onboard.py": (9, HARDWARE, GENERIC, "vrnetlab's RW community and injected user"),
    "modules/nsot/retire.py": (6, LAB_PLATFORM, OPTIONAL, "retire's startup-file step"),
    "modules/nsot/manifest.py": (3, LAB_PLATFORM, OPTIONAL, "a device's clab_lab key"),
    "modules/nsot/startup_source.py": (1, LAB_PLATFORM, GENERIC, "what a device would boot (generic)"),
    "modules/nsot/persist_op.py": (2, LAB_PLATFORM, GENERIC, "comments naming the clab chain"),
    "modules/nsot/normalize.py": (2, HARDWARE, GENERIC, "vrnetlab's own lines filtered"),
    "modules/nsot/repo.py": (1, LAB_PLATFORM, GENERIC, "a comment"),
    "modules/nsot/freshness.py": (1, LAB_PLATFORM, GENERIC, "a comment"),
    "modules/nsot/ip_sla_policy.py": (1, LAB_VALUES, GENERIC, "a measured example"),
    "modules/netbox_client.py": (6, LAB_VALUES, GENERIC, "the clab-mgmt VRF exclusion's examples"),
    "modules/breakglass.py": (4, LAB_VALUES, GENERIC, "the lab's name in the record format"),
    "modules/oxidized_fetch.py": (3, LAB_PLATFORM, GENERIC, "comments naming clab-sync"),
    "modules/panels.py": (2, LAB_VALUES, GENERIC, "the lab's dashboard UID in an example"),
    "modules/pipeline.py": (2, LAB_PLATFORM, GENERIC, "comments: containerlab nodes are ephemeral"),
    "modules/prometheus_targets.py": (1, LAB_VALUES, GENERIC, "a lab address in an example"),
    "modules/readers/reachability.py": (1, LAB_PLATFORM, GENERIC, "a comment"),
    "modules/route_gates.py": (1, LAB_PLATFORM, OPTIONAL, "the clab route's gate entry"),
    "scripts/nmas-host": (5, ACCESS, MOVE, "the operator's LAN-or-tunnel host helper"),
    "scripts/nmas-breakglass": (2, LAB_VALUES, GENERIC, "the lab's name"),
    "scripts/nmas-check-startup-applies": (3, LAB_PLATFORM, OPTIONAL, "checks a lab startup file"),
    "scripts/nmas-persist-native": (3, LAB_PLATFORM, GENERIC, "names the clab chain it replaces"),
    "scripts/nmas-rotate-credential": (3, LAB_PLATFORM, OPTIONAL, "runs the clab persistence chain"),
    "scripts/nmas-persist-credential": (1, LAB_PLATFORM, OPTIONAL, "runs the clab persistence chain"),
    "scripts/nmas-netbox-deletions": (1, LAB_VALUES, MOVE, "a one-off repair for the lab's NetBox"),
    "scripts/nmas-netbox-ip-provenance": (2, LAB_VALUES, MOVE, "a one-off repair for the lab's NetBox"),
    "scripts/nmas-netbox-repair-addresses": (3, LAB_VALUES, MOVE, "a one-off repair for the lab's NetBox"),
    "scripts/nmas-stage-guard": (1, LAB_VALUES, GENERIC, "a comment naming the lab's key incident"),
    "scripts/nmas-startup-source": (1, LAB_PLATFORM, GENERIC, "names clab-sync as its consumer"),
    "scripts/nmas-test": (1, LAB_PLATFORM, GENERIC, "a comment"),
    "templates/partials/freshness_signal.html": (1, LAB_PLATFORM, GENERIC, "names a redeploy"),
    "templates/partials/onboard_wizard.html": (3, LAB_PLATFORM, GENERIC, "vrnetlab in help text"),
    "deploy/rsyslog/10-network-devices.conf": (2, LAB_VALUES, MOVE, "the lab's device addresses"),
    "deploy/intent-changes/p1-syslog-block.json": (2, LAB_VALUES, MOVE, "a lab change record"),
}


def scan(root=ROOT, scope=SCOPE) -> dict:
    """``{path: lines}`` for every tracked product file holding a lab name or value."""
    files = subprocess.run(["git", "-C", root, "ls-files", "--", *scope],
                           capture_output=True, text=True, check=True).stdout.split()
    out = {}
    for f in files:
        if "/vendor/" in f:
            continue
        try:
            with open(os.path.join(root, f), encoding="utf-8") as fh:
                text = fh.read()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        n = sum(1 for line in text.splitlines() if PATTERN.search(line))
        if n:
            out[f] = n
    return out


def problems(found: dict, inventory: dict) -> list:
    out = []
    for f, n in sorted(found.items()):
        if f not in inventory:
            out.append(f"{f}: {n} lab-specific line(s) and no inventory entry: move it to lab "
                       "tooling, make it an optional integration or a local setting, or declare it")
        elif n > inventory[f][0]:
            out.append(f"{f}: {n} lab-specific line(s), the inventory says {inventory[f][0]}: a new "
                       "one was written")
        elif n < inventory[f][0]:
            out.append(f"{f}: {n} lab-specific line(s), the inventory says {inventory[f][0]}: "
                       "lower its number (the inventory says what is left)")
    for f in sorted(set(inventory) - set(found)):
        out.append(f"{f}: in the inventory and holds no lab-specific line: remove its entry")
    return out


class TestTheInventoryIsExact:
    def test_the_scan_finds_something(self):
        found = scan()
        assert len(found) >= 40 and sum(found.values()) >= 300, found

    def test_every_lab_specific_line_is_declared_exactly(self):
        assert problems(scan(), INVENTORY) == []

    def test_every_entry_says_what_and_where_it_goes(self):
        for f, (n, cat, disp, what) in INVENTORY.items():
            assert n > 0 and cat in (LAB_PLATFORM, LAB_VALUES, HARDWARE, ACCESS), f
            assert disp in (OPTIONAL, MOVE, GENERIC, REMOVE) and len(what) >= 8, f


class TestTheCheckCanFail:
    def test_a_new_file_a_grown_file_a_shrunk_file_and_a_ghost_are_each_named(self):
        inv = {"a.py": (2, LAB_VALUES, GENERIC, "x" * 8), "b.py": (3, LAB_VALUES, GENERIC, "x" * 8),
               "gone.py": (1, LAB_VALUES, GENERIC, "x" * 8)}
        out = problems({"a.py": 3, "b.py": 1, "new.py": 1}, inv)
        assert len(out) == 4
        assert "new.py: 1 lab-specific line(s) and no inventory entry" in out[2]
        assert "a new one was written" in out[0] and "lower its number" in out[1]
        assert "gone.py: in the inventory and holds no lab-specific line" in out[3]

    def test_the_pattern_finds_each_kind_and_not_its_neighbours(self):
        for hit in ("containerlab deploy", "clab-sync", "clab_host", "vrnetlab's launch",
                    "rcn-lab1", "CSCI 5840", "10.255.0.10", "rcn-lab-overview"):
            assert PATTERN.search(hit), hit
        for miss in ("disclaimer", "clabber", "10.2.55.1", "192.0.2.10", "nmas-device"):
            assert not PATTERN.search(miss), miss
