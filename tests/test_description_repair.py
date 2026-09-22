"""Correcting descriptions that were expanded in committed intent.

The parser fix stops new damage. It does not undo what is already committed:
`host_vars` hold `GigabitEthernet3` where the device says `Gi3`, and the
render will keep disagreeing with the device until that is corrected.

The repair is deliberately narrow, and the narrowness is the point. A
description that genuinely differs from the device is **drift** -- a pending
change waiting to be deployed -- and a repair tool that rewrote it would
silently discard somebody's work while claiming to fix formatting.
"""

import pytest

from scripts.nsot_fix_description_ifnames import (SKIP_BEYOND,
                                                  SKIP_NO_DEVICE_TEXT,
                                                  SKIP_NO_INTERFACE,
                                                  classify,
                                                  golden_descriptions,
                                                  golden_interfaces)

CONFIG = """hostname s1
!
interface GigabitEthernet0/2
 description P2P to r1 Gi3 - RIPng
 no switchport
!
interface GigabitEthernet0/3
 description trunk to s2 Gi0/3 - VRRP rides this
!
interface Vlan10
 description hosts
!
end
"""


class TestReadingTheDevicesOwnText:
    def test_descriptions_come_back_verbatim(self):
        found = golden_descriptions(CONFIG)
        assert found["GigabitEthernet0/2"] == "P2P to r1 Gi3 - RIPng"
        assert found["Vlan10"] == "hosts"

    def test_it_does_not_read_through_the_parser(self):
        """The parser is the thing that corrupted this text; reading back
        through it would compare a value against itself."""
        import inspect

        from scripts import nsot_fix_description_ifnames as tool

        source = inspect.getsource(tool.golden_descriptions)
        assert "get_parser" not in source and "parse(" not in source

    def test_a_description_outside_an_interface_is_ignored(self):
        config = "router bgp 65001\n description not an interface\n!\n"
        assert golden_descriptions(config) == {}


class TestOnlyTheExpansionIsCorrected:
    def test_an_expanded_description_is_corrected(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2",
             "description": "P2P to r1 GigabitEthernet3 - RIPng"}]}
        found = classify(committed, CONFIG)["fix"]
        assert found == [("GigabitEthernet0/2",
                          "P2P to r1 GigabitEthernet3 - RIPng",
                          "P2P to r1 Gi3 - RIPng")]

    def test_real_drift_is_left_alone(self):
        """Somebody edited intent and has not deployed it yet. Rewriting it
        would discard the change."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": "NEW purpose"}]}
        assert classify(committed, CONFIG)["fix"] == []

    def test_drift_that_also_contains_an_expansion_is_left_alone(self):
        """The subtle case: both an expansion AND a real edit. Correcting it
        would half-apply a repair over somebody's pending change."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2",
             "description": "P2P to r1 GigabitEthernet3 - OSPF now"}]}
        assert classify(committed, CONFIG)["fix"] == []

    def test_a_matching_description_is_not_touched(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": "P2P to r1 Gi3 - RIPng"}]}
        assert classify(committed, CONFIG)["fix"] == []

    def test_an_interface_the_device_does_not_have_is_skipped(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet9/9", "description": "x GigabitEthernet3"}]}
        assert classify(committed, CONFIG)["fix"] == []

    def test_an_interface_with_no_description_is_skipped(self):
        committed = {"interfaces": [{"name": "GigabitEthernet0/2"}]}
        assert classify(committed, CONFIG)["fix"] == []

    def test_an_empty_description_is_not_confused_with_a_missing_one(self):
        """`""` is a description the operator set; `None` is absence."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": ""}]}
        found = classify(committed, CONFIG)
        assert found["fix"] == []
        # The device HAS a description and intent says empty. That is a real
        # difference -- intent asking for the description to be removed -- so
        # it is SKIP_BEYOND, not "the device has none".
        assert found["skip"][0][3] == SKIP_BEYOND

    def test_the_interface_is_matched_canonically(self):
        """The header was expanded legitimately, so both sides must agree on
        which interface is which."""
        committed = {"interfaces": [
            {"name": "Gi0/2", "description": "P2P to r1 GigabitEthernet3 - RIPng"}]}
        assert classify(committed, CONFIG)["fix"][0][0] == "Gi0/2"


class TestItTouchesNothingButDescriptions:
    def test_no_other_field_is_returned(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2",
             "description": "P2P to r1 GigabitEthernet3 - RIPng",
             "ipv4": "10.0.0.1 255.255.255.0", "no_switchport": True}]}
        assert len(classify(committed, CONFIG)["fix"]) == 1

    def test_the_writer_only_assigns_description(self):
        import inspect

        from scripts import nsot_fix_description_ifnames as tool

        body = inspect.getsource(tool.main)
        assignments = [l for l in body.splitlines()
                       if "entry[" in l and "=" in l and "==" not in l]
        assert assignments, "no assignment found; the test is checking nothing"
        for line in assignments:
            assert '"description"' in line, line


class TestOnTheRealFleetFixtures:
    """The fixtures are the sanitized real devices, so this is the shape the
    live repair will meet."""

    @pytest.mark.parametrize("host", ["s1", "r1"])
    def test_an_expanded_committed_intent_is_detected(self, host):
        import io
        import os

        from modules.nsot import ifnames
        from modules.nsot.parsers import get_parser

        path = os.path.join("tests", "fixtures", "configs", "fleet",
                            f"{host}.cfg")
        config = io.open(path, encoding="utf-8").read()
        platform = "cisco_ios" if host.startswith("s") else "cisco_iosxe"
        parsed = get_parser(platform).parse(config)

        # Reconstruct what the OLD parser committed: descriptions expanded.
        damaged = {"interfaces": []}
        for entry in parsed.get("interfaces") or []:
            text = entry.get("description")
            if text is None:
                continue
            damaged["interfaces"].append({
                "name": entry["name"],
                "description": ifnames._LINE_RE.sub(
                    lambda m: ifnames.canonical(f"{m.group(1)}{m.group(2)}"),
                    text)})

        found = classify(damaged, config)["fix"]
        assert found, f"{host} has no expanded description to repair"
        for _name, have, want in found:
            assert have != want
            assert want in config, "the correction is not the device's own text"


class TestSkipsAreFindings:
    """A skip is not a quiet no-op.

    The dangerous case is a description carrying BOTH expansion damage and a
    real edit: correcting it would half-apply a repair over somebody's pending
    change, and skipping it silently makes "nothing was skipped" and
    "something was skipped" the same output.
    """

    def test_real_drift_is_reported_not_merely_omitted(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": "NEW purpose"}]}
        found = classify(committed, CONFIG)
        assert found["fix"] == []
        assert found["skip"] == [("GigabitEthernet0/2", "NEW purpose",
                                  "P2P to r1 Gi3 - RIPng", SKIP_BEYOND)]

    def test_the_mixed_case_is_reported(self):
        """Expansion damage AND an edit on the same line."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2",
             "description": "P2P to r1 GigabitEthernet3 - OSPF now"}]}
        found = classify(committed, CONFIG)
        assert found["fix"] == []
        assert found["skip"][0][3] == SKIP_BEYOND

    def test_an_interface_absent_from_the_device_is_reported(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet9/9", "description": "ghost"}]}
        assert classify(committed, CONFIG)["skip"][0][3] == SKIP_NO_INTERFACE

    def test_already_correct_entries_are_counted(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": "P2P to r1 Gi3 - RIPng"},
            {"name": "Vlan10", "description": "hosts"}]}
        found = classify(committed, CONFIG)
        assert found["correct"] == 2
        assert found["fix"] == [] and found["skip"] == []


class TestAnUndescribedInterfaceIsNotASkip:
    """The false skip the loud report exposed on its first run.

    The parser writes `description: ''` for an interface with no description
    line. The device map held only interfaces that HAVE a description, so
    "this interface has no description" was indistinguishable from "this
    interface is not on the device" -- ten false loud skips across the fleet
    fixtures, every one of them wrong.

    A report nobody can trust gets ignored, which would have cost more than
    the silence it replaced.
    """

    CONFIG_WITH_BARE = CONFIG + """interface GigabitEthernet0/9
 no switchport
!
"""

    def test_it_counts_as_already_correct(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/9", "description": ""}]}
        found = classify(committed, self.CONFIG_WITH_BARE)
        assert found["correct"] == 1
        assert found["skip"] == []

    def test_a_wanted_description_the_device_lacks_is_still_a_skip(self):
        """Committed intent asking for a description the device has not got
        is drift to deploy, and must not be silently absorbed."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/9", "description": "please add me"}]}
        found = classify(committed, self.CONFIG_WITH_BARE)
        assert found["skip"][0][3] == SKIP_NO_DEVICE_TEXT

    def test_golden_interfaces_sees_undescribed_ones(self):
        names = golden_interfaces(self.CONFIG_WITH_BARE)
        assert "GigabitEthernet0/9" in names
        assert "GigabitEthernet0/9" not in golden_descriptions(
            self.CONFIG_WITH_BARE)

    def test_the_whole_fleet_reports_no_skips(self):
        """The property your review asked for, on the real shapes: 22 fixes,
        nothing skipped."""
        import io as _io
        import os

        from modules.nsot import ifnames
        from modules.nsot.parsers import get_parser

        fixes = skips = 0
        for host in ("r1", "r2", "r3", "r4", "r5", "s1", "s2", "s3", "s4"):
            path = os.path.join("tests", "fixtures", "configs", "fleet",
                                f"{host}.cfg")
            config = _io.open(path, encoding="utf-8").read()
            platform = "cisco_ios" if host.startswith("s") else "cisco_iosxe"
            parsed = get_parser(platform).parse(config)
            damaged = {"interfaces": []}
            for entry in parsed.get("interfaces") or []:
                text = entry.get("description")
                if text is None:
                    continue
                damaged["interfaces"].append({
                    "name": entry["name"],
                    "description": ifnames._LINE_RE.sub(
                        lambda m: ifnames.canonical(
                            f"{m.group(1)}{m.group(2)}"), text)})
            found = classify(damaged, config)
            fixes += len(found["fix"])
            skips += len(found["skip"])
        assert (fixes, skips) == (22, 0), (fixes, skips)


class TestTheWriteIsOneCommit:
    """Nine commits would make the history describe nine decisions nobody
    took separately."""

    def _main_source(self):
        import inspect

        from scripts import nsot_fix_description_ifnames as tool

        return inspect.getsource(tool.main)

    def _main_tree(self):
        """Parsed, so the COMMENT explaining that it commits once does not
        count as a second call -- which is exactly how this test first
        failed."""
        import ast
        import inspect
        import textwrap

        from scripts import nsot_fix_description_ifnames as tool

        return ast.parse(textwrap.dedent(inspect.getsource(tool.main)))

    def _calls(self, name):
        import ast

        return [node for node in ast.walk(self._main_tree())
                if isinstance(node, ast.Call)
                and getattr(node.func, "attr", getattr(node.func, "id", ""))
                == name]

    def test_save_host_vars_is_called_once(self):
        assert len(self._calls("save_host_vars")) == 1

    def test_it_is_outside_the_per_device_loop(self):
        """Inside the loop it would be one commit per device."""
        import ast

        commit = self._calls("save_host_vars")[0]
        for node in ast.walk(self._main_tree()):
            if not isinstance(node, ast.For):
                continue
            inside = [c for child in node.body for c in ast.walk(child)
                      if c is commit]
            assert not inside, "save_host_vars is inside a loop"

    def test_the_message_names_the_repair(self):
        assert ("host_vars: restore description text (ifname expansion, 1.4)"
                in self._main_source())

    def test_the_devices_are_passed_for_the_trailer(self):
        assert "[h for h, _ in touched]" in self._main_source()

    def test_it_writes_through_the_guarded_writer(self):
        """`write_committed()` carries the secret guards; a direct file write
        would skip them.

        The atomic backup DOES open files, and must: it keeps the previous
        bytes so a failure part-way through can restore them. That is a
        rollback, not a bypass -- so the rule is not "no open()" but "every
        open() here is binary", i.e. it copies bytes and never re-serialises
        a document behind the guards.
        """
        import ast

        source = self._main_source()
        assert "hostvars.write_committed(" in source

        for node in ast.walk(self._main_tree()):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "open"):
                continue
            mode = node.args[1].value if len(node.args) > 1 else "r"
            assert mode in ("rb", "wb"), (
                f"open(..., {mode!r}) in main: committed intent is written "
                f"only by write_committed()")


class TestSkippingChangesTheExitCode:
    """A warning that scrolls past has not warned anybody."""

    def test_the_script_exits_non_zero_when_anything_was_skipped(self):
        import inspect

        from scripts import nsot_fix_description_ifnames as tool

        source = inspect.getsource(tool.main)
        assert source.count("return 2 if skipped else 0") >= 2, (
            "every exit path must carry the skip verdict")


class TestTheWritePathActuallyRuns:
    """The AST tests passed while the script could not run at all.

    `--write` crashed on its only real invocation:

        TypeError: write_committed() takes 2 positional arguments but 3 were given

    Every test around it was structural -- it asserted the SHAPE of the source
    (one call, outside the loop, right message) and every one of those claims
    was true. None of them called the function. A signature was inferred
    instead of read, and no amount of inspecting source text can catch that.

    So this executes the write path end to end against a real repository, and
    asserts the outcome rather than the shape.
    """

    import os as _os
    import subprocess as _subprocess

    @staticmethod
    def _git(repo, *args):
        import os
        import subprocess

        out = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                             text=True, env=dict(
                                 os.environ,
                                 GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@l",
                                 GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@l"))
        assert out.returncode == 0, f"git {args}: {out.stderr}"
        return out.stdout.strip()

    @pytest.fixture
    def repo(self, tmp_path, monkeypatch):
        """Two devices with expanded descriptions, committed for real."""
        import os

        from modules.nsot import hostvars

        list_dir = tmp_path / "lab"
        repo_dir = str(list_dir / "config_repo")
        os.makedirs(os.path.join(repo_dir, "golden"))
        os.makedirs(os.path.join(repo_dir, "host_vars"))
        # init_repo(), not a bare `git init`: it lays down .gitattributes
        # and .gitignore. A raw repo gets those topped up by the first write
        # path that touches it, which would add a SECOND commit inside the
        # run under test and make "exactly one commit" fail for a reason
        # that has nothing to do with the repair.
        from modules.nsot import repo as _repo_mod
        _repo_mod.init_repo(repo_dir)

        for host in ("s1", "s2"):
            with open(os.path.join(repo_dir, "golden", f"{host}.cfg"),
                      "w") as handle:
                handle.write(CONFIG.replace("hostname s1", f"hostname {host}"))
            hostvars.write_committed(repo_dir, {
                "hostname": host,
                "interfaces": [
                    {"name": "GigabitEthernet0/2",
                     "description": "P2P to r1 GigabitEthernet3 - RIPng"},
                    {"name": "Vlan10", "description": "hosts"},
                ]})
        self._git(repo_dir, "add", "-A")
        self._git(repo_dir, "commit", "-m", "seed")

        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(list_dir))
        monkeypatch.setattr("modules.config.get_current_list_name",
                            lambda: "lab")
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "n@l",
                                "nsot_device_tag_retention": 50}.get(key, default))
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
        return {"repo": repo_dir, "before": self._git(repo_dir, "rev-parse", "HEAD")}

    def _run(self, argv):
        import sys

        from scripts import nsot_fix_description_ifnames as tool

        saved = sys.argv
        sys.argv = ["nsot_fix_description_ifnames.py", *argv]
        try:
            return tool.main()
        finally:
            sys.argv = saved

    def test_the_dry_run_changes_nothing(self, repo, capsys):
        assert self._run(["--list", "lab"]) == 0
        assert self._git(repo["repo"], "rev-parse", "HEAD") == repo["before"]
        assert self._git(repo["repo"], "status", "--porcelain", "-uno") == ""

    def test_write_does_not_crash(self, repo):
        """The regression this class exists for."""
        assert self._run(["--list", "lab", "--write"]) == 0

    def test_write_makes_exactly_one_commit(self, repo):
        self._run(["--list", "lab", "--write"])
        count = self._git(repo["repo"], "rev-list", "--count",
                          f"{repo['before']}..HEAD")
        assert count == "1", f"{count} commits; the repair is one decision"

    def test_the_commit_message_names_the_repair(self, repo):
        self._run(["--list", "lab", "--write"])
        subject = self._git(repo["repo"], "log", "-1", "--format=%s")
        assert subject == ("host_vars: restore description text "
                           "(ifname expansion, 1.4)")

    def test_the_commit_names_every_device_in_its_trailers(self, repo):
        self._run(["--list", "lab", "--write"])
        body = self._git(repo["repo"], "log", "-1", "--format=%B")
        assert "Devices: s1,s2" in body

    def test_it_changes_one_file_per_device(self, repo):
        self._run(["--list", "lab", "--write"])
        changed = self._git(repo["repo"], "show", "--name-only",
                            "--format=", "HEAD").split()
        assert sorted(changed) == ["host_vars/s1.yml", "host_vars/s2.yml"]

    def test_the_description_really_changed_on_disk(self, repo):
        from modules.nsot import hostvars

        self._run(["--list", "lab", "--write"])
        document = hostvars.read_committed(repo["repo"], "s1")
        descriptions = {e["name"]: e.get("description")
                        for e in document["interfaces"]}
        assert descriptions["GigabitEthernet0/2"] == "P2P to r1 Gi3 - RIPng"

    def test_nothing_else_in_the_document_moved(self, repo):
        from modules.nsot import hostvars

        self._run(["--list", "lab", "--write"])
        document = hostvars.read_committed(repo["repo"], "s1")
        assert document["hostname"] == "s1"
        assert {e["name"] for e in document["interfaces"]} == {
            "GigabitEthernet0/2", "Vlan10"}
        assert document["interfaces"][1]["description"] == "hosts"

    def test_a_second_run_finds_nothing_to_do(self, repo):
        """Idempotent: the repair is not a change that reapplies forever."""
        self._run(["--list", "lab", "--write"])
        head = self._git(repo["repo"], "rev-parse", "HEAD")
        assert self._run(["--list", "lab", "--write"]) == 0
        assert self._git(repo["repo"], "rev-parse", "HEAD") == head

    def test_the_working_tree_is_clean_afterwards(self, repo):
        self._run(["--list", "lab", "--write"])
        assert self._git(repo["repo"], "status", "--porcelain", "-uno") == ""


class TestTheWriteIsAtomic:
    """A repair that leaves four of nine devices rewritten is worse than one
    that does nothing: the next run reads a half-corrected repository as its
    starting point."""

    def test_a_failure_part_way_through_restores_every_file(
            self, tmp_path, monkeypatch):
        import os

        from modules.nsot import hostvars

        list_dir = tmp_path / "lab"
        repo_dir = str(list_dir / "config_repo")
        os.makedirs(os.path.join(repo_dir, "golden"))
        os.makedirs(os.path.join(repo_dir, "host_vars"))
        from modules.nsot import repo as _repo_mod
        _repo_mod.init_repo(repo_dir)
        for host in ("s1", "s2", "s3"):
            with open(os.path.join(repo_dir, "golden", f"{host}.cfg"),
                      "w") as handle:
                handle.write(CONFIG.replace("hostname s1", f"hostname {host}"))
            hostvars.write_committed(repo_dir, {
                "hostname": host,
                "interfaces": [{"name": "GigabitEthernet0/2",
                                "description":
                                "P2P to r1 GigabitEthernet3 - RIPng"}]})
        TestTheWritePathActuallyRuns._git(repo_dir, "add", "-A")
        TestTheWritePathActuallyRuns._git(repo_dir, "commit", "-m", "seed")

        before = {h: hostvars.read_committed(repo_dir, h)
                  for h in ("s1", "s2", "s3")}

        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(list_dir))
        monkeypatch.setattr("modules.config.get_current_list_name",
                            lambda: "lab")
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "n@l",
                                "nsot_device_tag_retention": 50}.get(key, default))
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)

        # Fail on the second device, after the first has been written.
        real = hostvars.write_committed
        calls = []

        def _explode(repo, host_vars):
            calls.append(host_vars.get("hostname"))
            if len(calls) == 2:
                raise OSError("disk full")
            return real(repo, host_vars)

        monkeypatch.setattr(hostvars, "write_committed", _explode)

        import sys

        from scripts import nsot_fix_description_ifnames as tool

        saved = sys.argv
        sys.argv = ["x", "--list", "lab", "--write"]
        try:
            code = tool.main()
        finally:
            sys.argv = saved

        assert code == 1
        assert len(calls) == 2, "it kept going after the failure"
        for host, document in before.items():
            assert hostvars.read_committed(repo_dir, host) == document, (
                f"{host} was left modified after a failed run")
        assert TestTheWritePathActuallyRuns._git(
            repo_dir, "status", "--porcelain", "-uno") == "", (
            "tracked files were left modified")

    def test_validation_happens_before_any_write(self):
        """Prepared, then written -- not validated as it goes."""
        import inspect

        from scripts import nsot_fix_description_ifnames as tool

        source = inspect.getsource(tool.main)
        validate = source.index("assert_no_secret_values")
        write = source.index("hostvars.write_committed(")
        assert validate < write
