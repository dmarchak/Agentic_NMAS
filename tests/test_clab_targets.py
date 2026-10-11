"""The lab's own device → lab map, read by `lab/clab-sync/clab-targets`.

**The problem.** The sync once wrote into one lab's `configs/`. r6 was
onboarded into its own lab, so a reboot would bring it back on its bootstrap
config — `password 0`, no rotated credential, NMAS locked out of a device it
manages.

C663 moved the map out of Mercury: it is the lab's file
(`data/lab_targets/<network>.tsv`), and the product holds no lab setting, no
resolver and no endpoint for it. What stays here is the helper's own
behaviour: it refuses rather than guesses, groups by destination, and accounts
for every device and every file.
"""

import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestTheHelperRefusesRatherThanGuessing:
    @pytest.fixture(scope="class")
    def helper(self):
        import importlib.util
        from importlib.machinery import SourceFileLoader

        path = os.path.join(ROOT, "lab", "clab-sync", "clab-targets")
        spec = importlib.util.spec_from_file_location(
            "clabt", path, loader=SourceFileLoader("clabt", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_an_unreadable_map_exits_non_zero(self, helper, monkeypatch, capsys, tmp_path):
        """C663: the map is the lab's own file; one that cannot be read is a refusal naming it,
        never a default directory."""
        missing = tmp_path / "no-map.tsv"
        monkeypatch.setattr(helper.sys, "argv",
                            ["x", "--list", "Default", "--map", str(missing)])
        assert helper.main() == helper.EXIT_UNREACHABLE
        err = capsys.readouterr().err
        assert f"REFUSED — the lab's map could not be read ({missing})" in err
        assert "Not falling back" in err

    def test_the_default_map_is_the_network_s_file_beside_the_checkout(self, helper):
        assert helper.map_path("Default") == os.path.join(ROOT, "data", "lab_targets",
                                                          "Default.tsv")
        assert helper.map_path("a b/c").endswith(os.path.join("lab_targets", "a_b_c.tsv"))

    def test_an_empty_map_is_also_a_refusal(self, helper, monkeypatch):
        """*"No devices"* from a readable map is a fact about the answer,
        not about the fleet."""
        monkeypatch.setattr(helper, "load", lambda *a, **k: [])
        monkeypatch.setattr(helper.sys, "argv", ["x", "--list", "Default", "--map", "m"])
        assert helper.main() == helper.EXIT_UNREACHABLE

    def test_it_never_caches(self, helper):
        """A cache is a second copy wearing a different name.

        **Parsed, not grepped**. Since C663 the map IS a file, the lab's own, so exactly one
        `open` is allowed: in `load`, reading. Nothing else opens a file; nothing is written
        or pickled."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(helper))
        opens = []
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and \
                        n.func.id == "open":
                    mode = n.args[1].value if len(n.args) > 1 and \
                        isinstance(n.args[1], ast.Constant) else "r"
                    opens.append((fn.name, mode))
        assert opens == [("load", "r")], opens
        names = {getattr(n, "id", "") for n in ast.walk(tree)
                 if isinstance(n, ast.Name)}
        assert "pickle" not in names and "urlopen" not in names
        # The floor: the parse really did see this module.
        assert "load" in {n.name for n in ast.walk(tree)
                          if isinstance(n, ast.FunctionDef)}

    def test_strays_finds_a_config_in_the_wrong_lab(self, helper):
        """`labs/lab/configs/r6.cfg`, written before the sync learned about
        r6's lab: inert, and a file that looks like a thing it is not.

        The listing is **passed in** — it comes from the clab host over ssh,
        not from the NMAS's own filesystem, which is what the first version
        got wrong."""
        found = helper.strays(
            "labs/lab/configs",
            [("r1", "labs/lab/configs", "default", "user@clab", "cisco_iosxe", "r1"),
             ("r6", "labs/r6/configs", "r6", "user@clab", "cisco_iosxe", "r6")],
            ["r1.cfg", "r6.cfg"])

        assert [p for p, _w in found] == ["labs/lab/configs/r6.cfg"]
        assert found[0][1] == "labs/r6/configs"

    def test_and_finds_nothing_when_everything_is_in_place(self, helper):
        """The floor: a detector that always fires is one nobody reads."""
        assert helper.strays(
            "labs/lab/configs",
            [("r1", "labs/lab/configs", "default", "user@clab", "cisco_ios", "r1")],
            ["r1.cfg"]) == []

    def test_it_lists_the_REMOTE_directory_not_a_local_one(self, helper):
        """The directory is on the clab host and this script runs on the
        NMAS. `os.listdir` raised `FileNotFoundError` — the least
        informative possible answer to *"is there litter on the clab
        host"*, because it names a local path that was never going to exist.

        Parsed: the docstring explains the defect using `os.listdir`."""
        import ast
        import inspect

        # SCOPED TO THE STRAY PATH. `--reconcile` lists a LOCAL directory
        # deliberately -- the sanitizer's own output, on the NMAS -- so a
        # module-wide assertion would forbid the correct thing to make a
        # point about a different function.
        tree = ast.parse(inspect.getsource(helper.remote_listing))
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert attrs, "the parse found nothing"
        assert "listdir" not in attrs, "it lists the NMAS's own filesystem"
        assert "run" in attrs, "nothing shells out, so nothing asks the host"

    def test_and_reconcile_is_the_only_LOCAL_listing(self, helper):
        """The two modes ask different machines, and each says which."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(helper))
        local = {n.name for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef)
                 and "listdir" in ast.dump(n)}
        assert local == {"_reconcile"}, (
            f"something other than --reconcile lists the NMAS's own "
            f"filesystem: {sorted(local)}")

    def test_a_failed_listing_is_UNPROVEN_not_clean(self, helper,
                                                    monkeypatch, capsys):
        """*"I could not look"* and *"there is nothing there"* are the two
        answers this must never confuse."""
        monkeypatch.setattr(helper, "load", lambda *a, **k: [
            ("r1", "labs/lab/configs", "default", "user@clab", "cisco_ios", "r1")])
        monkeypatch.setattr(helper, "remote_listing", lambda h, d: (_ for _ in ()).throw(
            helper.StrayLookupFailed("ssh: connect refused")))
        monkeypatch.setattr(helper.sys, "argv",
                            ["x", "--list", "Default", "--map", "m",
                             "--stray", "labs/lab/configs"])

        assert helper.main() == helper.EXIT_UNREACHABLE
        err = capsys.readouterr().err
        assert "REFUSED" in err
        assert "not the same as finding no litter" in err

    def test_no_host_in_the_map_is_a_named_refusal(self, helper):
        """An older NMAS serves three columns. That is a fact about the
        answer, not about the clab host."""
        with pytest.raises(helper.StrayLookupFailed) as err:
            helper.remote_listing("", "labs/lab/configs")
        assert "no clab host" in str(err.value)




class TestThePlatformIsCarriedNotInferred:
    """**The second gap the sanitizer's shape revealed.**

    `oxidized-to-config.sh` line 62: `ROUTERS="r1 r2 r3 r4 r5"`, and line
    153: `case " $ROUTERS " in *" $n "*) kind=router ;; *) kind=switch ;;`.
    So r6 would have been sanitised **as a switch** — wrong rules, silently,
    because the list was current when it was written.

    *"Coverage inherited, not designed"* for the third time, and the third
    found by adding one member.

    **A column, not a per-device ask**, for three reasons:

    * the sync iterates the fleet once, so one answer is one consistent
      snapshot — per-device asks can straddle a change and leave half the
      run sanitised under one map and half under another;
    * a per-device ask is N chances to become unreachable **mid-run**, and a
      partial map is worse than none: some devices written, some not, with
      the failure per-device instead of at the top;
    * the agreed design is that an unreachable NMAS **stops the run**. That
      is a single decision at the top with one ask, and N decisions with N.

    **And the dialect, asserted** — `platform_map` and NetBox are keyed on
    slugs (`cisco-ios-xe`), the parsers and templates on dialects
    (`cisco_iosxe`). A slug reaching a consumer keyed on the dialect is a
    lookup that misses, and the sanitizer's `case` default is a **device
    kind** — the same silently-opening gate one layer out.
    """







    def test_the_helper_reads_five_columns_ignores_a_sixth_and_survives_three(self, ):
        """Phase 3: an NMAS before step 3 served Oxidized's node as a sixth column; the helper
        reads five, so it reads either."""
        import importlib.util
        import os as _os
        from importlib.machinery import SourceFileLoader

        path = _os.path.join(ROOT, "lab", "clab-sync", "clab-targets")
        spec = importlib.util.spec_from_file_location(
            "clabt2", path, loader=SourceFileLoader("clabt2", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = _os.path.join(d, "Default.tsv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("r6\tlabs/r6/configs\tr6\tuser@clab\tcisco_iosxe\tr6\n"
                         "old\tlabs/lab/configs\tdefault\n")
            rows = mod.load(path)

        assert rows[0] == ("r6", "labs/r6/configs", "r6", "user@clab",
                           "cisco_iosxe")
        assert rows[1] == ("old", "labs/lab/configs", "default", "", ""), \
            "a three-column row from an older NMAS must not raise"


class TestEveryDeviceAndEveryFileIsAccountedFor:
    """**The population question, asked in both directions.**

    The sanitizer's own list and the NMAS's map are two statements about the
    same fleet by two owners — until tonight, a hardcoded
    `ROUTERS="r1 r2 r3 r4 r5"` and a manifest. When they disagree, iterating
    one and letting the difference fall out silently is the shape that lost
    r6 three times over.

    Three buckets, every device and every file in exactly one — the drift
    checker's rule, applied to the sync.
    """

    @pytest.fixture(scope="class")
    def helper(self):
        import importlib.util
        import os as _os
        from importlib.machinery import SourceFileLoader

        path = _os.path.join(ROOT, "lab", "clab-sync", "clab-targets")
        spec = importlib.util.spec_from_file_location(
            "clabt3", path, loader=SourceFileLoader("clabt3", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    ROWS = [("r1", "labs/lab/configs", "default", "user@clab", "cisco_iosxe", "r1"),
            ("r6", "labs/r6/configs", "r6", "user@clab", "cisco_iosxe", "r6")]

    def test_a_missing_output_BLOCKS_and_a_stray_file_does_not(
            self, helper, tmp_path, capsys):
        """**A gate that stops the sync for a stray file gets bypassed.**

        Both exited 3, so a caller doing `--reconcile … || exit 2` refused
        to sync because somebody left a file behind — which is not a reason
        to stop. The two findings are different claims: *"a device will not
        be updated and nothing else reports it"* is blocking; *"here is a
        file nobody mapped"* is worth knowing.
        """
        for name in ("r1.cfg", "r6.cfg", "ghost.cfg"):
            (tmp_path / name).write_text("x")

        assert helper._reconcile(str(tmp_path), self.ROWS) == helper.EXIT_OK
        assert "do not block" in capsys.readouterr().out

        (tmp_path / "r6.cfg").unlink()
        assert helper._reconcile(str(tmp_path), self.ROWS) == \
            helper.EXIT_MISSING_OUTPUT

    def test_strict_makes_an_unmapped_file_block_too(self, helper, tmp_path):
        """For a caller that wants it — rather than making every caller live
        with the stricter reading."""
        for name in ("r1.cfg", "r6.cfg", "ghost.cfg"):
            (tmp_path / name).write_text("x")

        assert helper._reconcile(str(tmp_path), self.ROWS) == helper.EXIT_OK
        assert helper._reconcile(str(tmp_path), self.ROWS, strict=True) == \
            helper.EXIT_MISSING_OUTPUT

    def test_a_mapped_device_with_no_file_is_NAMED(self, helper, tmp_path,
                                                    capsys):
        """*"The sanitizer produced nothing for these"* — otherwise the
        device is simply absent, which is the state r6 was in."""
        (tmp_path / "r1.cfg").write_text("x")

        rc = helper._reconcile(str(tmp_path), self.ROWS)

        out = capsys.readouterr().out
        assert "NO FILE" in out and "r6" in out
        assert rc != helper.EXIT_OK

    def test_a_file_the_map_does_not_account_for_is_NAMED(self, helper,
                                                          tmp_path, capsys):
        for name in ("r1.cfg", "r6.cfg", "ghost.cfg"):
            (tmp_path / name).write_text("x")

        helper._reconcile(str(tmp_path), self.ROWS)

        out = capsys.readouterr().out
        assert "unmapped" in out and "ghost" in out
        assert "not deleted from here" in out, \
            "an unmapped file must not read as something to remove"

    def test_agreement_is_a_clean_exit(self, helper, tmp_path, capsys):
        """**The floor.** A reconciler that always complained would be one
        nobody reads."""
        for name in ("r1.cfg", "r6.cfg"):
            (tmp_path / name).write_text("x")

        assert helper._reconcile(str(tmp_path), self.ROWS) == helper.EXIT_OK
        out = capsys.readouterr().out
        assert "produced : 2" in out
        assert "NO FILE" not in out and "unmapped" not in out

    def test_nothing_produced_is_a_REFUSAL_not_a_clean_run(self, helper,
                                                            tmp_path, capsys):
        """*"Nothing to ship"* is a fact about the sanitizer's output, not
        about the fleet — and a sync that shipped nothing and exited 0 is
        the vacuous pass one more time."""
        rc = helper._reconcile(str(tmp_path), self.ROWS)

        assert rc == helper.EXIT_UNREACHABLE
        assert "not about the fleet" in capsys.readouterr().err

    def test_a_missing_directory_says_it_is_LOCAL(self, helper, tmp_path,
                                                   capsys):
        """`--stray` reaches the clab host and this does not. Saying so
        stops the next person debugging the wrong machine."""
        rc = helper._reconcile(str(tmp_path / "nope"), self.ROWS)

        assert rc == helper.EXIT_UNREACHABLE
        assert "does not reach the clab host" in capsys.readouterr().err

    def test_the_totals_are_checked(self, helper):
        """Every mapped device in exactly one bucket, asserted rather than
        assumed — a bucket that swallowed one would otherwise be a rounding
        difference."""
        import inspect

        src = inspect.getsource(helper._reconcile)
        assert "DEFECT" in src
        assert "accounted != len(mapped)" in src


class TestGroupingIsByDestination:
    """One line per `configs_dir`, so the caller's unit of work can be a
    **lab** rather than a device — which is how `--stray` already thinks
    about it, and which makes a failure *"this lab was not updated"*."""

    @pytest.fixture(scope="class")
    def helper(self):
        import importlib.util
        import os as _os
        from importlib.machinery import SourceFileLoader

        path = _os.path.join(ROOT, "lab", "clab-sync", "clab-targets")
        spec = importlib.util.spec_from_file_location(
            "clabt4", path, loader=SourceFileLoader("clabt4", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_devices_sharing_a_destination_are_one_line(self, helper,
                                                        monkeypatch, capsys):
        monkeypatch.setattr(helper, "load", lambda *a, **k: [
            ("r1", "labs/lab/configs", "default", "user@clab", "cisco_iosxe"),
            ("s1", "labs/lab/configs", "default", "user@clab", "cisco_ios"),
            ("r6", "labs/r6/configs", "r6", "user@clab", "cisco_iosxe")])
        monkeypatch.setattr(helper.sys, "argv",
                            ["x", "--list", "Default", "--map", "m", "--group"])

        assert helper.main() == helper.EXIT_OK
        lines = capsys.readouterr().out.strip().splitlines()

        assert len(lines) == 2, f"expected one line per destination: {lines}"
        assert lines[0] == "labs/lab/configs\tuser@clab\tr1 s1"
        assert lines[1] == "labs/r6/configs\tuser@clab\tr6"


class TestADeclaredFileIsADecisionNotAGap:
    """A retired device's frozen startup config is DECLARED unmapped, with
    who and why, so `--reconcile` reports it as a decision instead of as
    unmapped for ever (which teaches people to ignore that line)."""

    @pytest.fixture(scope="class")
    def helper(self):
        import importlib.util
        import os as _os
        from importlib.machinery import SourceFileLoader

        path = _os.path.join(ROOT, "lab", "clab-sync", "clab-targets")
        spec = importlib.util.spec_from_file_location(
            "clabt4", path, loader=SourceFileLoader("clabt4", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    ROWS = [("r1", "labs/lab/configs", "default", "u@c", "cisco_iosxe", "r1")]

    def test_declared_is_reported_with_its_reason_and_not_as_unmapped(
            self, helper, tmp_path, capsys):
        for name in ("r1.cfg", "r5.cfg", "ghost.cfg"):
            (tmp_path / name).write_text("x")
        code = helper._reconcile(str(tmp_path), self.ROWS, declared={
            "r5": "ISP PE, retired from NMAS (op, 2026-09-25)"})
        out = capsys.readouterr().out
        assert code == helper.EXIT_OK
        assert "declared : 1" in out and "r5: ISP PE" in out
        assert "unmapped : 1 — ghost" in out, "undeclared still named"

    def test_strict_does_not_block_on_a_declared_file(self, helper, tmp_path):
        for name in ("r1.cfg", "r5.cfg"):
            (tmp_path / name).write_text("x")
        assert helper._reconcile(str(tmp_path), self.ROWS, strict=True,
                                 declared={"r5": "retired"}) == helper.EXIT_OK

    def test_a_declaration_on_a_mapped_device_is_a_conflict(
            self, helper, tmp_path, capsys):
        (tmp_path / "r1.cfg").write_text("x")
        code = helper._reconcile(str(tmp_path), self.ROWS,
                                 declared={"r1": "retired"})
        assert code == helper.EXIT_MISSING_OUTPUT
        assert "CONFLICT" in capsys.readouterr().err

    def test_load_collects_declarations(self, helper, tmp_path):
        path = tmp_path / "Default.tsv"
        path.write_text("r1\tlabs/lab/configs\tdefault\tu@c\tcisco_iosxe\tr1\n"
                        "# DECLARED-UNMAPPED\tr5\tdefault\tISP PE (op, today)\n")
        declared = {}
        rows = helper.load(str(path), declared=declared)
        assert [r[0] for r in rows] == ["r1"]
        assert declared == {"r5": "ISP PE (op, today)"}

    def test_device_mode_reads_six_column_rows(self, helper, monkeypatch,
                                               capsys):
        """`--device` unpacked three columns from six-column rows and raised
        on the first one."""
        monkeypatch.setattr(helper, "load", lambda *a, **k: list(self.ROWS))
        monkeypatch.setattr("sys.argv", ["x", "--list", "Default", "--map", "m", "--device", "r1"])
        assert helper.main() == helper.EXIT_OK
        assert "r1\tlabs/lab/configs\tdefault" in capsys.readouterr().out
