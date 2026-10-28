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
                     r"\b10\.255\.\d|rcn-lab-overview|rcn-lab1-snmp|\bnetwork_syslog\b", re.I)

#: A JOB NAMED in the product (C820: `device_logs.JOB` named the lab's syslog job and the
#: pattern above, which knew no job name, did not see it). A job's name is the collector's
#: configuration's choice (Alloy's, Prometheus's), so a query naming one works on the network
#: that chose it and reads nothing anywhere else. The shape, not a list of names: a `job`
#: matcher holding a literal value (LogQL, PromQL, Alloy's `job = "..."`), or a constant
#: named `JOB` assigned a string. Not a job named: a value built from code (`{`), the
#: selector-needs-a-label wildcards `.+` and `.*`, and a dashboard template variable (`$name`,
#: `${name}`: Grafana fills it at view time from what the data source holds, C964).
JOB_LITERAL = re.compile(r"""\bjob\s*=~?\s*\\?["'`](?P<value>[^"'`\\{]*)|"""
                         r"""\bJOB\s*=\s*["'](?P<constant>[^"']*)["']""")
WILDCARDS = {".+", ".*"}
#: One alternative of a matcher's value that is a template variable: `$name`, or the `$` the
#: value pattern stops at before `{name}`.
TEMPLATE_VARIABLE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?")


def product_jobs() -> set:
    """The job names the PRODUCT declares, so a query naming them is the product's own contract:
    the routing jobs Mercury writes a target file for (`prometheus_targets.ROUTING`, each file
    `nmas-snmp-<kind>.json` read by the job of the same name, docs/PROMETHEUS_TARGETS.md step 2).
    Read from that module, a path independent of the files the scan reads."""
    from modules.prometheus_targets import ROUTING
    return {kind for kind, _rx, _platform in ROUTING}


def names_a_job(line: str, own=None) -> bool:
    """Whether *line* names a job the product does not declare."""
    own = product_jobs() if own is None else own
    for m in JOB_LITERAL.finditer(line):
        value = m.group("value") if m.group("value") is not None else m.group("constant")
        if not value or value in WILDCARDS:
            continue                                  # built from code, empty, or a wildcard
        named = {v for v in value.split("|") if not TEMPLATE_VARIABLE.fullmatch(v)}
        if named - own:
            return True
    return False


def lab_specific(line: str, own=None) -> bool:
    return bool(PATTERN.search(line)) or names_a_job(line, own)
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
    # C663 (2026-10-11) emptied the rest. This one moves to lab/ once CLAUDE.md, which cites
    # `scripts/nmas-host` throughout, names its new home: CLAUDE.md is the operator's to change.
    "scripts/nmas-host": (5, ACCESS, MOVE, "the operator's LAN-or-tunnel host helper"),
    # A one-shot host step naming the old unit and link it removes; removed once it has run on
    # the one host that had them, as Phase 3's spent step was.
    "scripts/host-steps/c663-step3b-topology.sh": (4, LAB_VALUES, REMOVE,
                                                   "renames the renderer's unit and link"),
    # Found by C820's widening (2026-10-16): the job names the lab's collectors chose, written
    # into queries. `device_logs` and the heartbeat rules (C963) measure their job from Loki,
    # and the device dashboard (C964) reads its jobs from the data sources at view time.
    "modules/host_steps.py": (5, LAB_VALUES, GENERIC,
                              "the severity and trap label checks name the lab's syslog and "
                              "trap jobs"),
    "scripts/host-steps/c722-device-label.sh": (10, LAB_VALUES, REMOVE,
                                                "a one-shot host step writing the lab's Alloy "
                                                "configuration and counting its syslog job"),
    "scripts/host-steps/ibn7-severity-trap-label.sh": (14, LAB_VALUES, REMOVE,
                                                       "a one-shot host step writing the lab's "
                                                       "Alloy configuration, its jobs named"),
    "scripts/host-steps/c1836-flask-app-journal.sh": (3, LAB_VALUES, REMOVE,
                                                      "a one-shot host step writing the lab's "
                                                      "Alloy configuration, its new job named"),
    "scripts/host-steps/c794-loki-detected-level-off.sh": (1, LAB_VALUES, REMOVE,
                                                           "a one-shot host step's note of what "
                                                           "it measured in the lab's syslog job"),
}


def scan(root=ROOT, scope=SCOPE) -> dict:
    """``{path: lines}`` for every tracked product file holding a lab name or value."""
    files = subprocess.run(["git", "-C", root, "ls-files", "--", *scope],
                           capture_output=True, text=True, check=True).stdout.split()
    out, own = {}, product_jobs()
    for f in files:
        if "/vendor/" in f:
            continue
        try:
            with open(os.path.join(root, f), encoding="utf-8") as fh:
                text = fh.read()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        n = sum(1 for line in text.splitlines() if lab_specific(line, own))
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
    def test_the_scan_finds_something(self, tmp_path):
        """The floor, on a PLANTED tree: C663 takes the product's count to nothing, so a floor
        on the product would have to fall to zero, where a scan that reads nothing also sits.
        A tracked file in scope with one lab line is found and counted; the same line outside
        the scope, in an untracked file and in a vendored file is not."""
        for rel, text in (("modules/x.py", "a = 1\n# the clab-sync job\n"),
                          # C820's shape: a constant naming a collector's job, as device_logs
                          # held the lab's, and a query naming one.
                          ("modules/logs.py", 'JOB = "site_syslog"\nQ = \'{job="site_syslog"}\'\n'
                                              "S = f'{{job=\"{JOB}\"}}'\n"),
                          ("modules/untracked.py", "# containerlab\n"),
                          ("docs/notes.md", "rcn-lab1\n"),
                          ("static/js/vendor/lib.js", "// vrnetlab\n")):
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text(text, encoding="utf-8")
        git = ["git", "-C", str(tmp_path)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["add", "modules/x.py", "modules/logs.py", "docs/notes.md",
                              "static/js/vendor/lib.js"], check=True)
        assert scan(root=str(tmp_path)) == {"modules/x.py": 1, "modules/logs.py": 2}

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

    def test_a_named_job_is_found_in_each_shape_and_a_built_one_is_not(self):
        """C820: the scan knew no job name, so `JOB = "network_syslog"` in device_logs passed."""
        own = {"ospf", "ospfv3", "bgp"}
        for hit in ('JOB = "network_syslog"', "JOB = 'site_syslog'", '{job="site_syslog"}',
                    'up{job=~"cisco_8000v|cisco_vios_l2", device="r1"}',
                    'labels = { job = "snmptrapd", host = "$HOSTLABEL" }',
                    '{job=~\\".*snmptrapd\\", device=~\\".+\\"}',
                    "{job=`site_syslog`}", 'up{job=~"ospf|lldp"}',
                    # C964: a template variable beside a name still names the name.
                    '{job=~"$syslog_job|site_syslog"}'):
            assert names_a_job(hit, own) and lab_specific(hit, own), hit
        for miss in ('{job=~".+"}', '{job=~".*", device="r1"}', "f'{{job=\"{JOB}\"}}'",
                     'up{job=~"ospf|ospfv3|bgp"}', 'data-job="{{ job }}"', 'job="", run=None',
                     "SOME_JOB = 'x'", "the job is measured from Loki",
                     # C964: a dashboard variable, filled by Grafana from the data source.
                     '{job=~"$syslog_job"} |~ `\\d+: $device: `', '{job=~"${syslog_job}"}',
                     'SYSLOG = \'{job=~\\"$syslog_job\\"}\''):
            assert not names_a_job(miss, own), miss

    def test_the_products_own_jobs_come_from_the_targets_it_writes(self):
        assert product_jobs() == {"ospf", "ospfv3", "bgp"}
