"""No device is known to the product by name, except where declared (the operator, 2026-10-19,
CLAUDE.md's device-lifecycle rule: a device enters only by onboarding and leaves only by
retirement, identified by its NetBox ID, its name a label).

This check scans the PRODUCT (the scope of tests/test_lab_specifics.py: modules, routes, app.py,
templates, the app's scripts, deploy and the shipped manual) for a lab device's name, by the
names' shape: ``r<n>``, ``s<n>``, ``h<n>``, ``br<n>``, and the throwaways ``tw-…``, ``bp-…`` and
``probe-r<n>…``. Each file holding one is in ``INVENTORY`` with its number of such lines, its kind
and what the names are there for, and the table is EXACT both ways, as test_lab_specifics' is:
- a file not in it that gains a name fails: a device written into the product by name;
- a file whose count grows fails (declare the new line, or do not write it);
- a file whose count shrinks fails until its number is lowered, so the inventory says what is
  left;
- an entry naming a file with no such line fails (a ghost).

The kinds, and what each is for:
- ``PROVENANCE``: a measurement names the device it was taken on. Kept: where a measured fact
  came from is part of the fact.
- ``HISTORY``: a dated incident or finding names the device it happened on. Kept, as history.
- ``EXAMPLE``: an example, a usage line, a placeholder. To become an example name (``edge1``),
  never a lab device's: the operator, 2026-10-19 ("comments and examples become example names").
- ``RECORD``: a record of past exceptions, keyed by the device each was recorded on. Kept.
- ``LOGIC``: code that names the lab's devices. To be removed: a device the product knows by
  name is the thing this check exists to stop.
- ``NOT_A_DEVICE``: a token of a device's shape that is not one (a CSS class, a local variable,
  the S3 provider in a form the shape rules below do not see).

**What it does not see:**
- Upper-case names (``R1``): ``R<n>`` is the concurrency audit's and the review rounds' numbering
  throughout the code, so an upper-case device name in the product is not caught.
- A name built at run time, or logic keyed on a name's shape (``startswith('s')``).

**The S3 provider is told from the switch s3 by its forms:** an IAM action or an ARN (``s3:Get…``,
``arn:aws:s3``), a URL (``s3://``), an attribute of a client (``s3.bucket``), a client named
``"s3"`` (``client("s3"``, ``name = "s3"``), and ``s3-archive``. Any other ``s3`` is counted.
"""

import os
import re
import subprocess

from tests.test_lab_specifics import ROOT, SCOPE

#: A lab device's name, by shape: not part of a longer word, identifier, path, attribute, CSS class
#: (``sc-h2``) or HTML tag (``<h2>``), and not followed by more of an identifier.
NAME = re.compile(r"(?<![A-Za-z0-9_.$/<#&-])(?:[rsh][0-9]{1,2}|br[0-9]{1,2}|"
                  r"tw-[a-z0-9]+(?:-[a-z0-9]+)*|bp-[a-z0-9]+(?:-[a-z0-9]+)*|probe-r[0-9][a-z]?)"
                  r"(?![A-Za-z0-9_])")
#: The S3 provider's forms, blanked before NAME is matched.
PROVIDER = re.compile(r"\bs3(?=\.[A-Za-z_]|:[^\s]|://|\s*=\s*S3|=\{|-archive)|"
                      r"(?<=client\()\s*\"s3\"|(?<=name = )\"s3\"|\"s3\"(?=,\s*endpoint_url)|"
                      r"arn:aws:s3")

PROVENANCE, HISTORY, EXAMPLE = "provenance", "history", "example"
RECORD, LOGIC, NOT_A_DEVICE = "record", "logic", "not a device"
KINDS = (PROVENANCE, HISTORY, EXAMPLE, RECORD, LOGIC, NOT_A_DEVICE)


def names(line: str) -> list:
    """The device names *line* holds, the S3 provider's forms set aside."""
    return NAME.findall(PROVIDER.sub(" ", line))


def _tracked(root, scope):
    files = subprocess.run(["git", "-C", root, "ls-files", "--", *scope],
                           capture_output=True, text=True, check=True).stdout.split()
    for f in files:
        if "/vendor/" in f:
            continue
        try:
            with open(os.path.join(root, f), encoding="utf-8") as fh:
                yield f, fh.read()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue


def scan(root=ROOT, scope=SCOPE) -> dict:
    """``{path: lines}`` for every tracked product file naming a device."""
    out = {}
    for f, text in _tracked(root, scope):
        n = sum(1 for line in text.splitlines() if names(line))
        if n:
            out[f] = n
    return out


def names_in(root, path) -> set:
    """The names *path* holds (for the inventory's words)."""
    with open(os.path.join(root, path), encoding="utf-8") as fh:
        return {n for line in fh.read().splitlines() for n in names(line)}


def problems(found: dict, inventory: dict) -> list:
    out = []
    for f, n in sorted(found.items()):
        if f not in inventory:
            out.append(f"{f}: {n} line(s) naming a device and no inventory entry: a device is "
                       "known to the product by its NetBox ID, never its name; use an example "
                       "name (edge1), or declare the line's kind")
        elif n > inventory[f][0]:
            out.append(f"{f}: {n} line(s) naming a device, the inventory says {inventory[f][0]}: "
                       "a new one was written")
        elif n < inventory[f][0]:
            out.append(f"{f}: {n} line(s) naming a device, the inventory says {inventory[f][0]}: "
                       "lower its number (the inventory says what is left)")
    for f in sorted(set(inventory) - set(found)):
        out.append(f"{f}: in the inventory and names no device: remove its entry")
    return out


#: ``path: (lines, kind, what the names are there for)``. Measured 2026-10-19.
INVENTORY = {
    "deploy/config-repo/nmas-config-check.yml": (1, PROVENANCE, "a measurement names the device it was taken on: r2"),
    "deploy/grafana/build_nmas_device.py": (4, PROVENANCE, "a measurement names the device it was taken on: r3, s1"),
    "deploy/grafana/nmas-device.json": (1, PROVENANCE, "a measurement names the device it was taken on: r3"),
    "deploy/rsyslog/10-network-devices.conf": (1, HISTORY, "a dated incident or finding names the device it happened on: r6"),
    "deploy/snmp_exporter/generator.yml": (4, PROVENANCE, "a measurement names the device it was taken on: r1, r3, s3"),
    "docs/manual/how-it-works/retire.md": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r5"),
    "modules/alert_bands.py": (1, PROVENANCE, "a measurement names the device it was taken on: s3"),
    "modules/attention.py": (8, HISTORY, "a dated incident or finding names the device it happened on: r2, r6, s2, s3, tw-ztp-a"),
    "modules/bgp_summary.py": (3, PROVENANCE, "a measurement names the device it was taken on: r3, r4"),
    "modules/commands.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2"),
    "modules/config_read.py": (5, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1, r2"),
    "modules/connection.py": (10, PROVENANCE, "a measurement names the device it was taken on: r1, r2, r4, s1, s3, s4"),
    "modules/credentials.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1"),
    "modules/device_list.py": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s1"),
    "modules/device_logs.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s3"),
    "modules/device_page.py": (4, HISTORY, "a dated incident or finding names the device it happened on: r6"),
    "modules/device_serials.py": (1, PROVENANCE, "a measurement names the device it was taken on: r1, r2, r3, r4, r6"),
    "modules/dhcp_page.py": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: h1, h2"),
    "modules/drained.py": (3, PROVENANCE, "a measurement names the device it was taken on: r2, s1, s2"),
    "modules/drift_check.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r3"),
    "modules/goldens.py": (1, PROVENANCE, "a measurement names the device it was taken on: s1"),
    "modules/heartbeat_windows.py": (1, PROVENANCE, "a measurement names the device it was taken on: s3"),
    "modules/history_sources.py": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2, s3"),
    "modules/host_keys.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1"),
    "modules/in_flight.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2"),
    "modules/integrations/kea.py": (1, HISTORY, "a dated incident or finding names the device it happened on: h4"),
    "modules/inventory_edit.py": (2, HISTORY, "a dated incident or finding names the device it happened on: r6"),
    "modules/job_health.py": (5, HISTORY, "a dated incident or finding names the device it happened on: bp-ztp-a, r2, r6, s1"),
    "modules/monitoring_coverage.py": (4, HISTORY, "a dated incident or finding names the device it happened on: r1, r2, r6, s1, s2, s4"),
    "modules/neighbours.py": (2, PROVENANCE, "a measurement names the device it was taken on: r1, s3"),
    "modules/netbox_client.py": (6, PROVENANCE, "a measurement names the device it was taken on: r1, r2, r3, s1, s2, s3"),
    "modules/netbox_context_mask.py": (1, PROVENANCE, "a measurement names the device it was taken on: r5"),
    "modules/netbox_guard.py": (1, HISTORY, "a dated incident or finding names the device it happened on: r6"),
    "modules/nsot/adopt.py": (1, PROVENANCE, "a measurement names the device it was taken on: r2"),
    "modules/nsot/bootstrap_config.py": (4, PROVENANCE, "a measurement names the device it was taken on: r1, s1, s3"),
    "modules/nsot/bulk_intent.py": (2, PROVENANCE, "a measurement names the device it was taken on: r2, r6"),
    "modules/nsot/config_check.py": (2, PROVENANCE, "a measurement names the device it was taken on: r2"),
    "modules/nsot/credential_rotation.py": (15, PROVENANCE, "a measurement names the device it was taken on: probe-r1a, r1, r2, s1"),
    "modules/nsot/decline.py": (1, HISTORY, "a dated incident or finding names the device it happened on: r6, s3"),
    "modules/nsot/deploy.py": (1, PROVENANCE, "a measurement names the device it was taken on: r6"),
    "modules/nsot/device_ops.py": (4, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2, s3, s4"),
    "modules/nsot/expected_effects.py": (1, PROVENANCE, "a measurement names the device it was taken on: r1, s3"),
    "modules/nsot/golden_state.py": (3, PROVENANCE, "a measurement names the device it was taken on: r1, s1, s3"),
    "modules/nsot/hooks.py": (2, HISTORY, "a dated incident or finding names the device it happened on: r5, s3"),
    "modules/nsot/hostvars.py": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: probe-r1a, r2"),
    "modules/nsot/intent_edit.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s4"),
    "modules/nsot/intent_match.py": (4, PROVENANCE, "a measurement names the device it was taken on: r2"),
    "modules/nsot/ip_sla_policy.py": (10, PROVENANCE, "a measurement names the device it was taken on: r1, r2, s2, s3, s4"),
    "modules/nsot/logging_path.py": (1, PROVENANCE, "a measurement names the device it was taken on: r1"),
    "modules/nsot/migrate.py": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1"),
    "modules/nsot/normalize.py": (7, PROVENANCE, "a measurement names the device it was taken on: r1, r2, r3, r4, r5, r6, s5"),
    "modules/nsot/onboard.py": (3, HISTORY, "a dated incident or finding names the device it happened on: probe-r1b, r6"),
    "modules/nsot/persist_op.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2"),
    "modules/nsot/platform_defaults.json": (11, PROVENANCE, "a measurement names the device it was taken on: r1, r2, r6, s1, s3"),
    "modules/nsot/platform_defaults.py": (2, PROVENANCE, "a measurement names the device it was taken on: s2"),
    "modules/nsot/privileged.py": (3, PROVENANCE, "a measurement names the device it was taken on: r2, r4, s1"),
    "modules/nsot/profile.py": (4, HISTORY, "a dated incident or finding names the device it happened on: r1, r6"),
    "modules/nsot/profile_propose.py": (5, PROVENANCE, "a measurement names the device it was taken on: r1, r4, r6"),
    "modules/nsot/reads.py": (1, PROVENANCE, "a measurement names the device it was taken on: s3"),
    "modules/nsot/receipts.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2"),
    "modules/nsot/record_exceptions.py": (22, RECORD, "a record of past exceptions keyed by the device they were recorded on: bp-ztp-a, probe-r1a, r1, r2, r3, r4, r5, r6, s1, s2, s3, s4"),
    "modules/nsot/recreate.py": (1, HISTORY, "a dated incident or finding names the device it happened on: r1, s3"),
    "modules/nsot/remote.py": (1, HISTORY, "a dated incident or finding names the device it happened on: r6"),
    "modules/nsot/removal.py": (9, PROVENANCE, "a measurement names the device it was taken on: r1, r2, r3, r6, s1, s2, s4"),
    "modules/nsot/removal_measured.json": (39, PROVENANCE, "a measurement names the device it was taken on: r2, r3, s1, s4"),
    "modules/nsot/repo.py": (5, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1, r2"),
    "modules/nsot/retire.py": (4, PROVENANCE, "a measurement names the device it was taken on: r5"),
    "modules/nsot/scheduled_rotation.py": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1, r2, s1"),
    "modules/nsot/seed.py": (2, PROVENANCE, "a measurement names the device it was taken on: r2, r6"),
    "modules/nsot/startup_check.py": (1, PROVENANCE, "a measurement names the device it was taken on: s1"),
    "modules/nsot/templates_repo.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s3"),
    "modules/nsot/tftp_once.py": (1, PROVENANCE, "a measurement names the device it was taken on: r2, s1"),
    "modules/nsot/verify_scope.py": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1, r3, r4"),
    "modules/nsot/ztp.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s6"),
    "modules/nsot/ztp_responder.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2"),
    "modules/panels.py": (4, PROVENANCE, "a measurement names the device it was taken on: r2, s1, s3, s4"),
    "modules/path_trace.py": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r3, r5"),
    "modules/pipeline.py": (17, HISTORY, "a dated incident or finding names the device it happened on: r1, r2, r3, r4, s1, s2, s3, tw-ztp-a"),
    "modules/preview_confirm.py": (3, HISTORY, "a dated incident or finding names the device it happened on: r5, s3"),
    "modules/prometheus_targets.py": (5, HISTORY, "a dated incident or finding names the device it happened on: r5, r6"),
    "modules/readers/adjacencies.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r3, r4"),
    "modules/readers/adjacency_log.py": (3, PROVENANCE, "a measurement names the device it was taken on: r1, r2, r3, r4, s3, s4"),
    "modules/readers/baseline_usability.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s1"),
    "modules/readers/grafana_alerts.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s4"),
    "modules/readers/reachability.py": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2, s3"),
    "modules/readers/restarts.py": (3, PROVENANCE, "a measurement names the device it was taken on: r6, s3"),
    "modules/readers/topology_graph.py": (6, PROVENANCE, "a measurement names the device it was taken on: r4, r5, r6, s3"),
    "modules/redact.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1"),
    "modules/restarts.py": (7, PROVENANCE, "a measurement names the device it was taken on: r3, r6, s3, s4"),
    "modules/reveal_audit.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1"),
    "modules/settings_schema.py": (2, PROVENANCE, "a measurement names the device it was taken on: r6, s3"),
    "modules/topology_layout.py": (2, NOT_A_DEVICE, "a local variable named r2 (a radius squared), not a device: r2"),
    "modules/topology_page.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r5"),
    "modules/utils.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: probe-r1a"),
    "routes/deploy.py": (2, HISTORY, "a dated incident or finding names the device it happened on: r2, r6"),
    "routes/golden.py": (5, PROVENANCE, "a measurement names the device it was taken on: r2, s3"),
    "routes/templates.py": (1, PROVENANCE, "a measurement names the device it was taken on: s1"),
    "routes/templatize.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s4"),
    "scripts/hooks/claude-no-raw-config-reads": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s1"),
    "scripts/host-steps/c788-loki-writer-rotate.sh": (3, NOT_A_DEVICE, "the S3 provider (Loki's s3: key, a client variable), not the switch: s3"),
    "scripts/host-steps/c789-snmptrapd-at-boot.sh": (1, PROVENANCE, "a measurement names the device it was taken on: s1"),
    "scripts/host-steps/phase7-mode-on.sh": (1, HISTORY, "the operating mode's standing lab fact (nothing staged on the CPU-starved switch): s3"),
    "scripts/nmas-adopt-recover": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r7"),
    "scripts/nmas-breakglass": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1"),
    "scripts/nmas-bulk-intent": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1, s1, s2"),
    "scripts/nmas-capture-output": (3, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1, r3, s1"),
    "scripts/nmas-check-credential": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1"),
    "scripts/nmas-config-read": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s1"),
    "scripts/nmas-heartbeat-rules": (14, PROVENANCE, "a measurement names the device it was taken on: r1, r10, s1, s3, s4"),
    "scripts/nmas-netbox-deletions": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r3"),
    "scripts/nmas-netbox-ip-provenance": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r3"),
    "scripts/nmas-netbox-mask-context": (3, PROVENANCE, "a measurement names the device it was taken on: r5"),
    "scripts/nmas-netbox-repair-addresses": (3, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1, r3, r5"),
    "scripts/nmas-netbox-status-reset": (5, PROVENANCE, "a measurement names the device it was taken on: r6, s1"),
    "scripts/nmas-netbox-untagged": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r3"),
    "scripts/nmas-persist-credential": (4, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2"),
    "scripts/nmas-persist-native": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: bp-ztp-a"),
    "scripts/nmas-removal-probe": (6, PROVENANCE, "a measurement names the device it was taken on: r1, r2, r3, r4, r6, s4"),
    "scripts/nmas-retire": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r5"),
    "scripts/nmas-rotate-credential": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2"),
    "scripts/nmas-rotation-recover": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2"),
    "scripts/nmas-stage-guard": (1, HISTORY, "a dated incident or finding names the device it happened on: r6"),
    "scripts/nmas-tftp-once": (1, PROVENANCE, "a measurement names the device it was taken on: r2, s1"),
    "scripts/nmas-tier2-probe": (2, NOT_A_DEVICE, "local variables h0 and h1, not devices: h0, h1"),
    "scripts/nsot_first_runs.py": (4, LOGIC, "a one-time script's fleet lists, from the first runs (2026-09): r1, r2, r3, r4, r5, s1, s2, s3, s4"),
    "scripts/nsot_fix_description_ifnames.py": (2, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r1"),
    "scripts/nsot_metric_diff.py": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r3"),
    "templates/v2/_credential_profiles.html": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2, s1"),
    "templates/v2/_history_ask_logs.html": (1, NOT_A_DEVICE, "the severity CSS classes s3 and s4, not devices: s3, s4"),
    "templates/v2/_restore.html": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: r2"),
    "templates/v2/_sc_pick.html": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s1"),
    "templates/v2/_sc_result.html": (1, EXAMPLE, "an example, usage line or placeholder uses a lab device's name: s2"),
    "templates/v2/ip_sla.html": (1, PROVENANCE, "a measurement names the device it was taken on: s3"),
}


class TestTheInventoryIsExact:
    def test_the_scan_finds_something(self, tmp_path):
        """The floor, on a PLANTED tree, so it holds as the product's count falls: a tracked
        file in scope keying logic on a device's name is found once; the S3 provider's forms, an
        HTML heading, a CSS class, the same name outside the scope, in an untracked file and in
        a vendored file are not."""
        for rel, text in (("modules/x.py", 'a = 1\nif host == "r6":\n    pass\n'),
                          ("modules/s3.py", 'c = boto3.client("s3", endpoint_url=u)\n'
                                            'b = s3.bucket\nA = "s3:GetObject"\n'
                                            'R = "arn:aws:s3:::mercury"\nU = f"s3://{b}"\n'),
                          ("templates/t.html", '<h2>Heading</h2><span class="sc-h2"></span>\n'),
                          ("modules/untracked.py", 'X = ["s1"]\n'),
                          ("docs/notes.md", "measured on s3\n"),
                          ("static/js/vendor/lib.js", "// r1\n")):
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text(text, encoding="utf-8")
        git = ["git", "-C", str(tmp_path)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["add", "modules/x.py", "modules/s3.py", "templates/t.html",
                              "docs/notes.md", "static/js/vendor/lib.js"], check=True)
        assert scan(root=str(tmp_path)) == {"modules/x.py": 1}

    def test_every_line_naming_a_device_is_declared_exactly(self):
        assert problems(scan(), INVENTORY) == []

    def test_every_entry_says_its_kind_and_what_it_is(self):
        for f, (n, kind, what) in INVENTORY.items():
            assert n > 0 and kind in KINDS and len(what) >= 8, f


class TestTheCheckCanFail:
    def test_a_new_file_a_grown_file_a_shrunk_file_and_a_ghost_are_each_named(self):
        inv = {"a.py": (2, HISTORY, "x" * 8), "b.py": (3, HISTORY, "x" * 8),
               "gone.py": (1, HISTORY, "x" * 8)}
        out = problems({"a.py": 3, "b.py": 1, "new.py": 1}, inv)
        assert len(out) == 4
        assert "new.py: 1 line(s) naming a device and no inventory entry" in out[2]
        assert "a new one was written" in out[0] and "lower its number" in out[1]
        assert "gone.py: in the inventory and names no device" in out[3]

    def test_the_shape_finds_each_kind_of_name_and_not_its_neighbours(self):
        for hit, want in (('if host == "r6":', ["r6"]), ("measured on s3.", ["s3"]),
                          ("(s1 and s4)", ["s1", "s4"]), ("h7 on VLAN 10", ["h7"]),
                          ("tw-ztp-a", ["tw-ztp-a"]), ("bp-ztp-a's lease", ["bp-ztp-a"]),
                          ("probe-r1a", ["probe-r1a"]), ("br1 later", ["br1"]),
                          ('"s3": the switch', ["s3"]), ("r10", ["r10"])):
            assert names(hit) == want, hit
        for miss in ("s3_endpoint", 'boto3.client("s3", endpoint_url=x)', "arn:aws:s3:::loki",
                     "s3.bucket", '"s3:PutObject"', "s3://bucket/key", "s3-archive", "<h2>",
                     "sc-h2", "R6 of the audit", "cr1", "r100", "golden/r1.cfg", "$r1", "ipv6",
                     "sha256", "x509", "r2d2"):
            assert names(miss) == [], miss
