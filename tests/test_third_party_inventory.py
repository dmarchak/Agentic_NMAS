"""The release gate's CI half: licences and third-party use (NSOT_STAGE10_PLAN 8.2a, the
operator, 2026-10-04: "build the check now, the audit at the end").

`docs/THIRD_PARTY.json` records every third-party component the repository ships or depends
on, with its source, version and licence. These tests hold it to the repository:
- **every tracked file is claimed,** either by a vendored entry (third-party) or by an
  own glob. A new file nobody claimed fails, so a vendored icon set fails the day it is
  added without an entry;
- **every claim matches a file,** so no entry outlives what it describes;
- **every Python requirement has an entry,** at the lock's version, and no entry lacks a
  requirement;
- **every licence is approved or reviewed** (an SPDX expression: `OR` needs one side
  acceptable, `AND` needs both);
- **the vendored front-end entries agree with `static/js/vendor/MANIFEST.json`** (version
  and tarball), so the two records cannot drift apart;
- **a vendored entry with no licence file beside it carries an audit note,** so the
  release audit lists it.

Each rule is shown able to fail on a planted case. What this cannot check: that a
recorded licence is the component's real one. A person read each from the component's
declared metadata; the release audit re-reads them.
"""

import fnmatch
import json
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "docs" / "THIRD_PARTY.json"
MANIFEST = ROOT / "static" / "js" / "vendor" / "MANIFEST.json"
REQUIREMENT_FILES = ("requirements.lock", "requirements.txt", "requirements-ci.txt",
                     "requirements-test.txt")


def _inventory():
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def _tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True,
                         check=True, timeout=30)
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def _claims(paths, inv):
    """``(unclaimed, used)``: the paths no glob claims, and each glob's matches.
    A vendored glob wins over an own one (`deploy/*` must not swallow a generated
    third-party file under it)."""
    used = {g: [] for g in list(inv["vendored"]) + list(inv["own"])}
    unclaimed = []
    for path in paths:
        hit = next((g for g in inv["vendored"] if fnmatch.fnmatchcase(path, g)), None) or \
            next((g for g in inv["own"] if fnmatch.fnmatchcase(path, g)), None)
        if hit is None:
            unclaimed.append(path)
        else:
            used[hit].append(path)
    return unclaimed, used


def _acceptable(expression, inv):
    """An SPDX expression over the approved and reviewed lists: `A OR B` needs one,
    `A AND B` needs both. Parenthesised forms are refused, not guessed."""
    ok = set(inv["approved"]) | set(inv["reviewed"])
    expression = (expression or "").strip()
    if not expression or "(" in expression:
        return False
    return any(all(term.strip() in ok for term in alt.split(" AND "))
               for alt in expression.split(" OR "))


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements(root=ROOT, files=REQUIREMENT_FILES):
    """``{normalised name: (file, version spec)}``; the lock's pin wins."""
    out = {}
    for name in files:
        for line in (root / name).read_text(encoding="utf-8").splitlines():
            # The compiled lock (section 8.2): a pin ends in a continuation, then hash lines.
            line = line.split("#", 1)[0].strip().rstrip("\\").strip()
            if line.startswith("-"):
                continue
            m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", line)
            if m and _norm(m.group(1)) not in out:
                out[_norm(m.group(1))] = (name, m.group(2).strip())
    return out


class TestEveryFileIsClaimed:
    def test_the_population(self):
        assert len(_tracked()) >= 1000, len(_tracked())

    def test_every_tracked_file_is_claimed(self):
        unclaimed, _used = _claims(_tracked(), _inventory())
        assert not unclaimed, (
            "files no entry in THIRD_PARTY.json claims. A third-party file gets a "
            "`vendored` entry (source, version, licence); a file of this repository's "
            "gets an `own` glob:\n" + "\n".join(unclaimed))

    def test_a_new_vendored_file_is_caught(self):
        """The topology icon set, the day it is added without an entry."""
        unclaimed, _ = _claims(["static/icons/router.svg", "modules/x.py"], _inventory())
        assert unclaimed == ["static/icons/router.svg"]

    def test_a_vendored_claim_wins_over_an_own_one(self):
        _unclaimed, used = _claims(["deploy/snmp_exporter/routing-modules.yml"], _inventory())
        assert used["deploy/snmp_exporter/routing-modules.yml"]
        assert not used["deploy/*"]

    def test_every_claim_matches_a_file(self):
        _unclaimed, used = _claims(_tracked(), _inventory())
        stale = sorted(g for g, hits in used.items() if not hits)
        assert not stale, f"entries that claim no tracked file (remove or correct): {stale}"


class TestEveryLicenceIsAcceptable:
    def test_python_and_vendored(self):
        inv = _inventory()
        bad = [f"python {k}: {v['licence']}" for k, v in inv["python"].items()
               if not _acceptable(v.get("licence"), inv)]
        bad += [f"vendored {g}: {v['licence']}" for g, v in inv["vendored"].items()
                if not _acceptable(v.get("licence"), inv)]
        assert not bad, ("licences neither approved nor reviewed. Approving one is the "
                         "operator's decision, recorded with its reason:\n" + "\n".join(bad))

    @pytest.mark.parametrize("expression, ok", [
        ("MIT", True), ("GPL-3.0-only", False), ("MIT OR GPL-3.0-only", True),
        ("MIT AND GPL-3.0-only", False), ("", False), ("(MIT OR BSD-3-Clause)", False),
        ("LGPL-2.1-or-later", True),
    ])
    def test_the_expression_rule(self, expression, ok):
        assert _acceptable(expression, _inventory()) is ok


class TestEveryRequirementHasAnEntry:
    def test_each_requirement_is_recorded(self):
        inv, reqs = _inventory(), _requirements()
        missing = sorted(set(reqs) - set(inv["python"]))
        assert not missing, (f"requirements with no THIRD_PARTY.json entry (record each "
                             f"one's source, version and licence): {missing}")

    def test_no_entry_lacks_a_requirement(self):
        stale = sorted(set(_inventory()["python"]) - set(_requirements()))
        assert not stale, f"python entries no requirements file names: {stale}"

    def test_the_lock_s_versions_are_the_recorded_ones(self):
        inv = _inventory()
        # A requirement with no entry at all is the test above's; this one compares.
        wrong = [f"{k}: lock {spec.lstrip('=')}, recorded {inv['python'][k]['version']}"
                 for k, (src, spec) in _requirements().items()
                 if src == "requirements.lock" and k in inv["python"]
                 and inv["python"][k]["version"] != spec.lstrip("=")]
        assert not wrong, "a locked version changed without its entry:\n" + "\n".join(wrong)

    def test_a_new_requirement_is_caught(self, tmp_path):
        for name in REQUIREMENT_FILES:
            (tmp_path / name).write_text((ROOT / name).read_text(encoding="utf-8"),
                                         encoding="utf-8")
        with open(tmp_path / "requirements.txt", "a", encoding="utf-8") as fh:
            fh.write("\nleftpad-gpl==1.0\n")
        known = set(_inventory()["python"])
        assert (set(_requirements(tmp_path)) - known) - (set(_requirements()) - known) \
            == {"leftpad-gpl"}


class TestVendoredEntriesAgreeWithTheManifest:
    def test_versions_and_sources(self):
        inv = _inventory()
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        wrong = []
        for rel, rec in manifest.items():
            path = f"static/js/vendor/{rel}"
            glob = next((g for g in inv["vendored"] if fnmatch.fnmatchcase(path, g)), None)
            if glob is None:
                wrong.append(f"{path}: in MANIFEST.json, claimed by no vendored entry")
                continue
            entry = inv["vendored"][glob]
            if entry["version"] != rec["version"] or entry["source"] != rec["tarball"]:
                wrong.append(f"{path}: MANIFEST {rec['version']} {rec['tarball']}, "
                             f"THIRD_PARTY {entry['version']} {entry['source']}")
        assert not wrong, "\n".join(wrong)

    def test_each_named_licence_file_exists(self):
        missing = [v["licence_file"] for v in _inventory()["vendored"].values()
                   if v.get("licence_file") and not (ROOT / v["licence_file"]).is_file()]
        assert not missing, missing

    def test_a_licence_taken_outside_the_registry_is_held_to_its_hash(self):
        """Alpine's licence comes from its repository at the release's tag (its packages carry
        none; the operator's decision, 2026-10-05), so no registry integrity covers it: its
        entry records the source and the sha256, and the file must still be that file."""
        import hashlib
        held = {v["licence_file"]: v["licence_sha256"] for v in _inventory()["vendored"].values()
                if v.get("licence_sha256")}
        assert "static/js/vendor/alpinejs-csp/LICENSE.md" in held
        for path, digest in held.items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
            entry = next(v for v in _inventory()["vendored"].values()
                         if v.get("licence_file") == path)
            assert entry.get("licence_source"), path

    def test_an_entry_without_a_licence_file_is_on_the_audit(self):
        bare = [g for g, v in _inventory()["vendored"].items()
                if not v.get("licence_file") and not v.get("audit")]
        assert not bare, f"no licence file beside them and no audit note: {bare}"
