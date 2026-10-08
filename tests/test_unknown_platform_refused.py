"""C452: a device whose platform the tool does not know is refused, never read as
`cisco_ios` (the operator's decision, 2026-10-04: "remove the cisco_ios default
now: an unknown platform refuses, naming the device and what it reported").

Measured before the fix (read in the code, and the host's inventory read-only):
`platform.platform_for_device()` returned `cisco_ios` for any row with no
platform whose `device_type` was not one of five Cisco drivers, `get_parser()`
returned IOS's parser for any platform, and `templates_repo._platform_slug()`
bound an unknown platform to `cisco_ios`'s template. So a FortiGate in a CSV
list would have been parsed as IOS and recorded as an IOS golden. No device on
the host reached it: all 9 rows carry an explicit platform.

What these tests hold:
- the resolver answers "" for an unknown platform, and nothing defaults it;
- `save_golden()`, the one write path for goldens, refuses that device ALONE,
  naming it, what its row says and what it reports, and records nothing for it;
- the platform `save_golden()` resolved is what the manifest records;
- the session driver is never `cisco_ios` by default either;
- the shape: no dialect literal is a fallback anywhere in the product's code,
  the excused sites named and only shrinking (C453).
"""

import ast
import csv
import json
import os
import pathlib

import pytest

from tests.source_index import tracked
from tests.test_onboard_pending import repo  # noqa: F401  (the fixture)

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: What the FortiGate says it is, as the platform-facts store keeps it (C426's
#: shape: the first sysDescr line, the image, the object id).
FORTI_DESCR = "FortiGate-60F v7.2.8,build1639,240313 (GA.M)"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A list with two devices: r1 (cisco_ios, known) and fw1 (a FortiGate's
    driver, no platform)."""
    from modules.device import DEVICE_CSV_FIELDS
    from modules.nsot import repo as R

    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    with open(list_dir / "devices.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=DEVICE_CSV_FIELDS)
        writer.writeheader()
        writer.writerow({"hostname": "r1", "device_type": "cisco_ios", "ip": "192.0.2.1",
                         "role": "router"})
        writer.writerow({"hostname": "fw1", "device_type": "fortinet", "ip": "192.0.2.2",
                         "role": "firewall"})
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.readers.platform_facts.facts", lambda: (
        {"fw1": {"descr": FORTI_DESCR, "image": "", "object_id": "1.3.6.1.4.1.12356.101.1.60"}},
        "2026-10-04T23:00:00Z", ""))
    repo = str(list_dir / "config_repo")
    R.init_repo(repo)
    return {"repo": repo, "list_dir": list_dir}


def _save(items):
    from modules.nsot import repo as R
    return R.save_golden("lab", [R.GoldenItem(*i) for i in items],
                         source="test", actor="test", allow_new=True)


class TestTheResolverHasNoDefault:
    def test_an_unknown_driver_is_unknown(self):
        from modules.nsot.platform import platform_for_device
        assert platform_for_device({"hostname": "fw1", "device_type": "fortinet"}) == ""

    def test_a_row_with_nothing_is_unknown(self):
        from modules.nsot.platform import platform_for_device
        assert platform_for_device({}) == ""

    def test_require_platform_refuses_naming_the_device_and_its_row(self, lab):
        from modules.nsot.platform import UnknownPlatform, require_platform
        with pytest.raises(UnknownPlatform) as refused:
            require_platform({"hostname": "fw1", "device_type": "fortinet"})
        words = str(refused.value)
        assert "fw1" in words and "device_type 'fortinet'" in words
        assert FORTI_DESCR in words, "the refusal names what the device reports"

    def test_a_device_that_reports_nothing_says_so(self, lab, monkeypatch):
        from modules.nsot.platform import unknown_words
        monkeypatch.setattr("modules.readers.platform_facts.facts", lambda: ({}, "", ""))
        assert "reports nothing yet" in unknown_words({"hostname": "fw9"})

    def test_a_known_device_resolves(self):
        from modules.nsot.platform import require_platform
        assert require_platform({"hostname": "r1", "device_type": "cisco_xe"}) == "cisco_iosxe"


class TestNoGoldenFromADeviceTheToolDoesNotUnderstand:
    def test_the_unknown_device_is_refused_alone(self, lab):
        out = _save([("r1", "hostname r1\n", "192.0.2.1"),
                     ("fw1", "config system global\n set hostname fw1\nend\n", "192.0.2.2")])
        assert out["ok"], out
        assert out["changed"] == ["r1"]
        refused = {r["device"]: r for r in out["refused"]}
        assert set(refused) == {"fw1"}
        assert refused["fw1"]["kind"] == "platform"
        why = refused["fw1"]["reason"]
        assert "fw1" in why and "device_type 'fortinet'" in why and FORTI_DESCR in why
        assert "Nothing was recorded for it" in why

    def test_nothing_is_written_for_it(self, lab):
        from modules.nsot import manifest
        _save([("fw1", "config system global\nend\n", "192.0.2.2")])
        assert not os.path.exists(os.path.join(lab["repo"], "golden", "fw1.cfg"))
        names = {e.get("name") for e in manifest.load(lab["repo"])["devices"].values()}
        assert "fw1" not in names, "a refused device must not get a manifest entry"

    def test_a_save_of_only_unknown_devices_fails_naming_them(self, lab):
        out = _save([("fw1", "config system global\nend\n", "192.0.2.2")])
        assert out["ok"] is False
        assert "fw1" in out["error"] and FORTI_DESCR in out["error"]

    def test_the_resolved_platform_is_what_the_manifest_records(self, lab):
        """An item with no platform of its own: the inventory row's, recorded."""
        from modules.nsot import manifest
        _save([("r1", "hostname r1\n", "192.0.2.1")])
        entries = [e for e in manifest.load(lab["repo"])["devices"].values()
                   if e.get("name") == "r1"]
        assert [e.get("platform") for e in entries] == ["cisco_ios"]


class TestTheSessionDriverHasNoDefault:
    def test_an_unknown_platform_with_no_driver_is_refused(self, lab):
        from modules.nsot.platform import UnknownPlatform, netmiko_type_for_device
        with pytest.raises(UnknownPlatform):
            netmiko_type_for_device({"hostname": "x1"})

    def test_a_known_platform_with_no_driver_takes_its_mapped_one(self, monkeypatch):
        from modules.nsot.platform import netmiko_type_for_device
        monkeypatch.setattr("modules.settings_schema.get_setting", lambda key, default=None: {
            "platform_map": {"cisco-ios-xe": {"netmiko_device_type": "cisco_xe"}}}.get(key, default))
        assert netmiko_type_for_device({"hostname": "r2", "platform": "cisco_iosxe"}) == "cisco_xe"

    def test_a_row_s_own_driver_is_kept(self):
        from modules.nsot.platform import netmiko_type_for_device
        assert netmiko_type_for_device({"device_type": "fortinet"}) == "fortinet"


# ── The shape: no dialect literal is a fallback ─────────────────────────────

DIALECT_LITERALS = {"cisco_ios", "cisco_iosxe", "cisco_xe", "cisco-ios", "cisco-ios-xe"}

#: Sites that default a SESSION DRIVER (not a dialect) to a Cisco one: C453, found
#: by this scan the day C452 was fixed and registered under the sweep rule. All five
#: fixed 2026-10-05 (a driver from the row or the plan's dialect, else refused or
#: "unknown"); empty, and it stays so.
EXCUSED = set()


def _fallbacks(path: pathlib.Path, source: str):
    """``[(kind, lineno, code)]``: a dialect literal as `x or "<d>"`, as a `.get`
    default, as a bare `return`, or as a parameter default. Parsed, never grepped."""
    def lit(node):
        return isinstance(node, ast.Constant) and node.value in DIALECT_LITERALS

    out = []
    for node in ast.walk(ast.parse(source)):
        kind = ""
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and lit(node.values[-1]):
            kind = "or-default"
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in ("get", "setdefault", "pop") and len(node.args) >= 2
              and lit(node.args[1])):
            kind = ".get default"
        elif isinstance(node, ast.Return) and node.value is not None and lit(node.value):
            kind = "return literal"
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(lit(d) for d in node.args.defaults + [d for d in node.args.kw_defaults if d]):
                kind = "param default"
        if kind:
            out.append((kind, node.lineno, ast.unparse(node)[:100]))
    return out


def _population():
    files = [ROOT / "app.py"] + [pathlib.Path(p) for p in tracked("modules", "routes",
                                                                  suffix=".py", root=ROOT)]
    return [p for p in files if "__pycache__" not in p.parts]


class TestNoDialectLiteralIsAFallback:
    def test_the_scan_reaches_the_product(self):
        assert len(_population()) >= 150, len(_population())

    def test_the_scan_finds_a_planted_default(self):
        planted = ('def f(d, platform="cisco_ios"):\n'
                   '    return d.get("platform", "cisco_iosxe") or "cisco_ios"\n'
                   'def g():\n    return "cisco_xe"\n')
        kinds = {k for k, _l, _c in _fallbacks(pathlib.Path("planted.py"), planted)}
        assert kinds == {"param default", ".get default", "or-default", "return literal"}

    def test_none_outside_the_excused_sites(self):
        found, seen = [], set()
        for path in _population():
            rel = path.relative_to(ROOT).as_posix()
            for kind, lineno, code in _fallbacks(path, path.read_text(encoding="utf-8")):
                if (rel, kind) in EXCUSED:
                    seen.add((rel, kind))
                    continue
                found.append(f"{rel}:{lineno}: {kind}: {code}")
        assert not found, ("a dialect literal is a fallback: an unknown device would be read "
                           "as that platform (C452). Refuse with platform.unknown_words():\n"
                           + "\n".join(found))
        assert seen == EXCUSED, f"an excused site is gone: remove it from EXCUSED: {EXCUSED - seen}"


class TestOnboardingTakesItsDriverFromThePlan:
    """C453: onboarding reached and recorded every device with the C8000v's driver when none
    was given. Now the plan's dialect gives it, through the one mapping, or it is refused."""

    @staticmethod
    def _plan(repo, platform):
        from modules.nsot import manifest as _m
        from modules.nsot.repo import GoldenItem, adopt_identity

        identity = adopt_identity(repo, GoldenItem("bp7", "", "192.0.2.37"))
        _m.upsert_device(repo, identity, "bp7", mgmt_ip="192.0.2.37", platform=platform,
                         pending=True)

    def test_a_plan_reaches_with_its_own_driver(self, repo):  # noqa: F811
        from modules.nsot.onboard import verify_device

        self._plan(repo, "cisco_ios")
        used = []
        out = verify_device(repo, "bp7", "probe", online=lambda ip: True,
                            reach=lambda *a: used.append(a[4]) or "bp7#")
        assert out["answered"] and used == ["cisco_ios"], (out, used)

    def test_a_plan_with_no_platform_is_refused_never_guessed(self, repo):  # noqa: F811
        from modules.nsot.onboard import promote_device, verify_device

        self._plan(repo, "")
        out = verify_device(repo, "bp7", "probe", online=lambda ip: True,
                            reach=lambda *a: pytest.fail("reached with a guessed driver"))
        assert not out["answered"] and "names no platform" in out["error"], out
        res = promote_device(repo, "bp7", "probe", username="admin", password="Rotated-7")
        assert not res["ok"] and "no row is written" in res["error"], res
