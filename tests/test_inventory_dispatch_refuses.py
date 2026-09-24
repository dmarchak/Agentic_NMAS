"""`load_saved_devices()` takes a PATH, and not knowing which list was meant
must never look like an empty fleet.

Twice this week the same shape ended in a silently empty inventory rather than
a refusal: `nmas-netbox-repair-addresses` passed a list **name** where a path
was wanted and reported *"nothing to create"*; and a no-argument call read
`DEVICES_FILE` — `data/Devices.csv`, a pre-lists constant nothing has written
since lists existed — and returned zero rows.

With ~87 call sites the blast radius is the point. Every downstream count is
*honestly* zero, which is the hardest kind of wrong to notice.
"""

import os

import pytest

from modules import device as dev


class TestTheNoArgumentFormResolvesTheActiveList:
    """Not `DEVICES_FILE`. A read may derive the active list; a write may not,
    and this is a read."""

    def test_it_points_at_the_active_list_not_the_legacy_constant(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        resolved = dev.active_devices_file()
        assert resolved.endswith(os.path.join("lab", "devices.csv"))
        assert "Devices.csv" not in resolved, \
            "still resolving the pre-lists installation-wide constant"

    def test_the_legacy_constant_is_no_longer_the_default(self):
        """Pinned by parsing, because the constant still exists for readers."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(dev.load_saved_devices))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "active_devices_file" in names
        assert "DEVICES_FILE" not in names, \
            "the no-argument default is the legacy constant again"

    def test_the_no_argument_form_reads_the_active_list(
            self, tmp_path, monkeypatch):
        list_dir = tmp_path / "lab"
        list_dir.mkdir()
        (list_dir / "devices.csv").write_text(
            "hostname,ip\nr6,203.0.113.32\n", encoding="utf-8")
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        monkeypatch.setattr(dev, "_list_name_for_path", lambda _p: "")
        rows = dev.load_saved_devices()
        assert [r["hostname"] for r in rows] == ["r6"], \
            "the no-argument form returned an empty fleet again"


class TestANameWhereAPathWasWantedRefuses:

    def test_a_bare_list_name_raises(self):
        """The `nmas-netbox-repair-addresses` shape, exactly."""
        with pytest.raises(dev.UnknownDeviceList) as exc:
            dev.load_saved_devices("Default")
        assert "not a path" in str(exc.value)
        assert "empty fleet" in str(exc.value), \
            "the refusal must say what the alternative would have looked like"

    def test_both_casings_refuse(self):
        """`default` and `Default` produced identical empty results, which is
        what showed nothing downstream depended on the argument."""
        for name in ("default", "Default"):
            with pytest.raises(dev.UnknownDeviceList):
                dev.load_saved_devices(name)


class TestACorrECTLYBuiltPathIsNeverRefused:
    """**The floor, and it is the half the first version got wrong.**

    The first refusal fired on any path that named no known list and did not
    exist — and broke twelve tests passing `<tmpdir>/devices.csv`, a correctly
    built path for a directory with no file yet. A list with no devices is a
    real state; onboarding writes that file only at promotion.
    """

    def test_an_absent_csv_at_a_real_path_returns_empty(self, tmp_path):
        assert dev.load_saved_devices(str(tmp_path / "devices.csv")) == []

    def test_an_absent_csv_in_a_nested_path_returns_empty(self, tmp_path):
        nested = tmp_path / "lists" / "somewhere"
        nested.mkdir(parents=True)
        assert dev.load_saved_devices(str(nested / "devices.csv")) == []

    def test_a_relative_csv_name_is_a_path(self, tmp_path, monkeypatch):
        """`devices.csv` with no directory is still a path — refusing it would
        make the guard fire on a caller that is merely terse."""
        monkeypatch.chdir(tmp_path)
        assert dev.load_saved_devices("devices.csv") == []


class TestTheSurveyThatJustifiedTheRefusal:
    """Refusing inside a function with ~87 call sites is only safe because
    none of them can reach the refusal. That is a measurement, and it decays."""

    @staticmethod
    def _sites():
        import ast

        skip = {".git", "node_modules", "__pycache__", "static"}
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        found = []
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in skip]
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    tree = ast.parse(open(path, encoding="utf-8").read())
                except (OSError, SyntaxError, ValueError):
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    label = (getattr(node.func, "id", None)
                             or getattr(node.func, "attr", None))
                    if label != "load_saved_devices":
                        continue
                    rel = os.path.relpath(path, root)
                    found.append((rel, node.lineno, node.args, node.keywords))
        return found

    @classmethod
    def _production_sites(cls):
        """Non-test callers only.

        The first version scanned everything and its single offender was
        **this file's own test**, which passes `"Default"` precisely to
        exercise the refusal. A test that triggers a guard is a mention, not
        a caller — the same distinction `check_removed_definitions.py` had to
        learn, and the seventh time in this project that a scan has matched
        the thing written to explain it.
        """
        return [s for s in cls._sites() if not s[0].startswith("tests" + os.sep)]

    def test_the_scan_finds_the_call_sites(self):
        """**The floor.** Everything below is a property of an empty list
        otherwise, which is what a scan that could not run also produces."""
        sites = self._production_sites()
        assert len(sites) >= 60, (
            f"found {len(sites)} production call sites against a measured 75 "
            "— the scan is matching almost nothing")
        assert any(s[0] == "app.py" for s in sites), \
            "app.py holds most of them; not finding it means the walk is wrong"

    def test_no_call_site_passes_a_bare_name(self):
        """The refusal is unreachable from inside the repo, which is what
        makes it safe rather than brave."""
        import ast

        offenders = []
        for path, lineno, args, _kw in self._production_sites():
            if not args or not isinstance(args[0], ast.Constant):
                continue
            value = args[0].value
            if isinstance(value, str) and "/" not in value \
                    and os.sep not in value and not value.endswith(".csv"):
                offenders.append(f"{path}:{lineno} -> {value!r}")
        assert offenders == [], (
            "these pass a bare name where a path is wanted, and would now "
            f"raise: {offenders}")
