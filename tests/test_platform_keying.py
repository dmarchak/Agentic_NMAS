"""Every consumer of a platform key names which keying it expects.

**Three namespaces, and only one is stored.**

* **dialect** — `cisco_ios`, `cisco_iosxe`. The canonical form. The manifest
  records it, the parsers key on it, and so do the template directories and
  `bootstrap_config`.
* **NetBox slug** — `cisco-ios`, `cisco-ios-xe`. An input. `platform_map` is
  keyed on it and NetBox speaks it.
* **Netmiko driver** — `cisco_ios`, `cisco_xe`. A different input, and it
  overlaps the dialect namespace on `cisco_ios`, which is why conflating them
  once made "change device_type to cisco_xe" alter transport.

`platform.py` owns every translation. **There is no `PlatformRef`**, and the
reason is worth stating: `ListRef` exists because a list's name and its slug
are *both stored and compared to each other*. A platform has **one** stored
form and two input formats — a translation problem, not an identity one. The
failure this guards against is an input format reaching a table keyed on the
canonical one, which `assert_dialect()` refuses at the boundary.

Measured once, in `/onboard/platforms`: NetBox slugs looked up in a
dialect-keyed table missed, returned the default, and reported **every**
platform unblocked — including the one stage D blocks.
"""

import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SLUGS = ("cisco-ios", "cisco-ios-xe")
DIALECTS = ("cisco_ios", "cisco_iosxe")
DRIVERS = ("cisco_xe", "cisco_xe_ssh", "cisco_ios_ssh")

#: Every file carrying a platform literal, and **which keying it means**.
#: A file that grows one and is not listed here fails the test below — the
#: point being that "which namespace is this?" is answered once, in writing,
#: rather than inferred from the value by each new reader.
KEYING = {
    "modules/nsot/platform.py":             "both",   # the translator itself
    "modules/nsot/parsers/__init__.py":     "both",   # a registry accepting any input
    "modules/settings_schema.py":           "both",   # platform_map: slug keys, driver values
    "modules/nsot/bootstrap_config.py":     "dialect",
    "modules/nsot/templates_repo.py":       "dialect",
    "modules/nsot/parsers/base.py":         "dialect",
    "modules/nsot/parsers/cisco_ios.py":    "dialect",
    "modules/nsot/parsers/cisco_iosxe.py":  "dialect",
    "modules/nsot/onboard.py":              "dialect",
    "modules/nsot/manifest.py":             "dialect",
    "modules/ai_assistant.py":              "driver",
    "modules/check_runner.py":              "driver",
    "modules/configure.py":                 "driver",
    "modules/connection.py":                "driver",
    "modules/pipeline_builder.py":          "driver",
    "routes/templatize.py":                 "dialect",
    "scripts/netmiko_timing_probe.py":      "driver",
    "scripts/nsot_metric_diff.py":          "dialect",
}


def _literals(path):
    text = io.open(os.path.join(ROOT, path), encoding="utf-8",
                   errors="replace").read()
    found = {"slug": False, "dialect": False, "driver": False}
    for value in SLUGS:
        if re.search(r'["\']' + re.escape(value) + r'["\']', text):
            found["slug"] = True
    for value in DIALECTS:
        if re.search(r'["\']' + re.escape(value) + r'["\']', text):
            found["dialect"] = True
    for value in DRIVERS:
        if re.search(r'["\']' + re.escape(value) + r'["\']', text):
            found["driver"] = True
    return found


def _files_with_platform_literals():
    out = []
    for base in ("modules", "routes", "scripts"):
        for root, _d, files in os.walk(os.path.join(ROOT, base)):
            if "__pycache__" in root:
                continue
            for name in sorted(files):
                if not name.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(root, name), ROOT)
                if any(_literals(rel).values()):
                    out.append(rel.replace(os.sep, "/"))
    return sorted(out)


class TestEveryConsumerDeclaresItsKeying:

    def test_the_scan_finds_something(self):
        """The set-difference rule: `declared - found` is empty when `found`
        is empty, so the floor comes first."""
        assert len(_files_with_platform_literals()) >= 12

    def test_every_file_with_a_platform_literal_is_declared(self):
        undeclared = [f for f in _files_with_platform_literals()
                      if f not in KEYING]
        assert not undeclared, (
            "these carry a platform literal and do not say which keying they "
            "mean — three namespaces overlap on `cisco_ios`, so a reader "
            "cannot tell from the value: " + str(undeclared))

    def test_no_ghosts(self):
        """A declaration for a file that no longer has one is a decision
        about nothing, and hides the day the file grows one back."""
        live = set(_files_with_platform_literals())
        assert [f for f in KEYING if f not in live] == []

    @pytest.mark.parametrize("path,keying", sorted(KEYING.items()))
    def test_the_declaration_matches_what_is_there(self, path, keying):
        found = _literals(path)
        if keying == "dialect":
            assert found["dialect"], f"{path} declares dialect and has none"
            assert not found["slug"], (
                f"{path} declares dialect and contains a NetBox slug — "
                "translate with platform_for_device() instead")
        elif keying == "slug":
            assert found["slug"] and not found["dialect"], path


class TestTheBoundaryRefusesTheWrongNamespace:
    """The failure was silent: a miss returned the default, and in a gate the
    default is "allowed"."""

    def test_a_slug_is_refused(self):
        from modules.nsot.platform import assert_dialect

        with pytest.raises(ValueError) as excinfo:
            assert_dialect("cisco-ios-xe")
        assert "platform_for_device()" in str(excinfo.value)

    def test_a_netmiko_driver_is_refused(self):
        from modules.nsot.platform import assert_dialect

        with pytest.raises(ValueError):
            assert_dialect("cisco_xe")

    def test_a_dialect_passes_through(self):
        from modules.nsot.platform import assert_dialect

        assert assert_dialect("cisco_iosxe") == "cisco_iosxe"

    def test_build_plan_refuses_a_slug(self):
        """The call site that silently opened a gate."""
        from modules.nsot.onboard import build_plan

        with pytest.raises(ValueError):
            build_plan(hostname="r6", platform="cisco-ios-xe",
                       list_name="probe")

    def test_the_route_translates_rather_than_copying_the_map(self):
        from tests.astcheck import calls_in

        from routes import onboard

        assert calls_in(onboard._dialect, "platform_for_device") == 1
        assert calls_in(onboard.platforms, "platform_for_device") == 1

    def test_there_is_one_translation_table(self):
        """A second copy is how the two come to disagree about what
        `cisco-ios` means."""
        import io

        hits = []
        for base in ("modules", "routes"):
            for root, _d, files in os.walk(os.path.join(ROOT, base)):
                if "__pycache__" in root:
                    continue
                for name in files:
                    if not name.endswith(".py"):
                        continue
                    path = os.path.join(root, name)
                    text = io.open(path, encoding="utf-8",
                                   errors="replace").read()
                    if re.search(r'"cisco-ios-xe"\s*:\s*"cisco_iosxe"', text):
                        hits.append(os.path.relpath(path, ROOT))
        assert hits == [os.path.join("modules", "nsot", "platform.py")], hits
