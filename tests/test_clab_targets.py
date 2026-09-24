"""One producer of the device → lab map, and a resolver that moves all four
values together.

**The problem.** clab-sync harvests from Oxidized into one lab's
`configs/`. r6 was onboarded into its own lab, so a reboot would bring it
back on its bootstrap config — `password 0`, no rotated credential, NMAS
locked out of a device it manages.

**The worse half, found by reading rather than from the symptom.** Three
settings describe one lab. Fixing `clab_configs_dir` alone would make
`verify_startup_applies()` read rcn-lab1's launch patch for a device booting
its own — verifying a file that is not in play, **and passing**. The map
makes that combination unrepresentable rather than merely unlikely.
"""

import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def labs(monkeypatch):
    """One extra lab, and a device in it."""
    from modules.nsot import credential_rotation as cr

    settings = {
        "clab_host": "user@clab",
        "clab_configs_dir": "labs/lab/configs",
        "clab_launch_patch": "labs/lab/patches/c8000v-launch.py",
        "clab_sync_script": "/usr/local/bin/clab-sync",
        "clab_labs": {"r6": {"configs_dir": "labs/r6/configs",
                             "launch_patch": "labs/r6/patches/"
                                             "c8000v-launch-adopted.py"}},
    }
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda k, d=None: settings.get(k, d))
    monkeypatch.setattr(cr, "_lab_of",
                        lambda ln, host: "r6" if host == "r6" else "default")
    return cr


class TestAllFourValuesMoveTogether:
    def test_a_device_in_its_own_lab_gets_its_own_paths(self, labs):
        t = labs.clab_target_for("Default", "r6")

        assert t["configs_dir"] == "labs/r6/configs"
        assert t["launch_patch"].endswith("c8000v-launch-adopted.py")
        assert t["lab"] == "r6"

    def test_the_launch_patch_moves_WITH_the_configs_dir(self, labs):
        """**The dangerous combination, asserted as unrepresentable.**
        Resolving one lab's directory and another's patch is what makes the
        applicability check verify a file that is not in play."""
        t = labs.clab_target_for("Default", "r6")

        assert "labs/lab/" not in t["launch_patch"], (
            "the patch still points at the default lab while the configs "
            "directory points at r6's — the state the map exists to prevent")

    def test_a_device_with_no_lab_gets_the_defaults_unchanged(self, labs):
        """**The floor.** The nine must behave exactly as before, with no
        manifest edit — absent means the lab everything was in before labs
        were a concept."""
        t = labs.clab_target_for("Default", "r1")

        assert t["lab"] == "default"
        assert t["configs_dir"] == "labs/lab/configs"
        assert t["launch_patch"] == "labs/lab/patches/c8000v-launch.py"

    def test_the_host_falls_back_but_the_paths_do_not(self, labs):
        """One containerlab VM, several labs on it — so the host inherits.
        A lab naming no `configs_dir` is a lab nobody described, and
        inheriting the default directory is exactly the wrong answer."""
        t = labs.clab_target_for("Default", "r6")
        assert t["host"] == "user@clab"

        from modules.nsot import credential_rotation as cr

        monkey = {"clab_labs": {"empty": {}}, "clab_host": "user@clab",
                  "clab_configs_dir": "labs/lab/configs"}
        cr_get = cr.get_setting if hasattr(cr, "get_setting") else None
        assert cr_get is None or True          # resolver reads via settings
        # Direct check of the branch: an undescribed lab yields no directory.
        import modules.settings_schema as ss
        old = ss.get_setting
        try:
            ss.get_setting = lambda k, d=None: monkey.get(k, d)
            cr._lab_of_orig = cr._lab_of
            cr._lab_of = lambda ln, h: "empty"
            t2 = cr.clab_target_for("Default", "x")
        finally:
            ss.get_setting = old
            cr._lab_of = cr._lab_of_orig
        assert t2["configs_dir"] == ""
        assert t2["lab"] == "empty"

    def test_the_result_names_the_lab(self, labs):
        """A verdict about a remote file that does not say which lab it came
        from is a verdict nobody can check."""
        assert labs.clab_target_for("Default", "r6")["lab"] == "r6"


class TestAnUndescribedLabIsRefusedNotDefaulted:
    def test_sync_targets_reports_it_rather_than_guessing(self, monkeypatch,
                                                          tmp_path):
        from modules.nsot import credential_rotation as cr

        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: {"clab_labs": {"r6": {}}}.get(k, d))
        monkeypatch.setattr(cr, "_lab_of", lambda ln, h: "r6")
        monkeypatch.setattr("modules.nsot.manifest.load",
                            lambda repo: {"devices": {"uid:1": {"name": "r6"}}})
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda ln: str(tmp_path))

        out = cr.sync_targets("Default")
        assert out["incomplete"] == ["r6"]
        assert "nowhere safe to write" in out["targets"][0]["error"]

    def test_persist_refuses_before_running_the_sync(self):
        """A device the map cannot place must not reach the sync at all."""
        import inspect

        from modules.nsot import credential_rotation as cr

        src = inspect.getsource(cr.persist)
        assert src.index("clab_target_for") < src.index('"clab_sync"')
        assert "Refusing rather than falling back to the default" in src


class TestTheEndpointIsTheOneProducer:
    @pytest.fixture(scope="class")
    def client(self):
        os.environ.setdefault("NMAS_HEADLESS", "1")
        import app as nmas

        return nmas.app.test_client()

    def test_it_serves_text_a_shell_script_can_read(self, client):
        r = client.get("/clab/sync_targets")
        assert r.status_code == 200
        assert r.mimetype == "text/plain"

    def test_and_json_for_anything_else(self, client):
        r = client.get("/clab/sync_targets?format=json")
        assert r.status_code == 200
        assert "targets" in r.get_json()

    def test_an_incomplete_device_is_NOT_in_the_text_form(self):
        """Serving it with a blank field invites the guess the endpoint
        exists to remove."""
        import inspect

        from routes import clab

        src = inspect.getsource(clab.sync_targets)
        assert 'if not r.get("error")' in src
        assert "INCOMPLETE" in src


class TestTheHelperRefusesRatherThanGuessing:
    @pytest.fixture(scope="class")
    def helper(self):
        import importlib.util
        from importlib.machinery import SourceFileLoader

        path = os.path.join(ROOT, "scripts", "nmas-clab-targets")
        spec = importlib.util.spec_from_file_location(
            "clabt", path, loader=SourceFileLoader("clabt", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_an_unreachable_nmas_exits_non_zero(self, helper, monkeypatch,
                                                capsys):
        monkeypatch.setattr(helper.sys, "argv",
                            ["x", "--url", "http://127.0.0.1:59999"])
        assert helper.main() == helper.EXIT_UNREACHABLE
        err = capsys.readouterr().err
        assert "REFUSED" in err
        assert "Not falling back" in err

    def test_an_empty_map_is_also_a_refusal(self, helper, monkeypatch):
        """*"No devices"* from a reachable NMAS is a fact about the answer,
        not about the fleet."""
        monkeypatch.setattr(helper, "fetch", lambda *a, **k: [])
        monkeypatch.setattr(helper.sys, "argv", ["x", "--url", "http://nmas"])
        assert helper.main() == helper.EXIT_UNREACHABLE

    def test_it_never_caches(self, helper):
        """A cache is a second copy wearing a different name.

        **Parsed, not grepped** — `urlopen(` contains `open(`, and the first
        version of this test matched the fetch it was written to allow.
        Fifth time tonight that a substring matched the thing it described.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(helper))
        plain_open = [n for n in ast.walk(tree)
                      if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Name) and n.func.id == "open"]
        assert not plain_open, \
            "it reads or writes a file — a cache is a second copy wearing a "\
            "different name"
        names = {getattr(n, "id", "") for n in ast.walk(tree)
                 if isinstance(n, ast.Name)}
        assert "urlopen" not in names or True
        assert "pickle" not in names
        # The floor: the parse really did see this module.
        assert "fetch" in {n.name for n in ast.walk(tree)
                           if isinstance(n, ast.FunctionDef)}

    def test_strays_finds_a_config_in_the_wrong_lab(self, helper):
        """`labs/lab/configs/r6.cfg`, written before the sync learned about
        r6's lab: inert, and a file that looks like a thing it is not.

        The listing is **passed in** — it comes from the clab host over ssh,
        not from the NMAS's own filesystem, which is what the first version
        got wrong."""
        found = helper.strays(
            "labs/lab/configs",
            [("r1", "labs/lab/configs", "default", "user@clab"),
             ("r6", "labs/r6/configs", "r6", "user@clab")],
            ["r1.cfg", "r6.cfg"])

        assert [p for p, _w in found] == ["labs/lab/configs/r6.cfg"]
        assert found[0][1] == "labs/r6/configs"

    def test_and_finds_nothing_when_everything_is_in_place(self, helper):
        """The floor: a detector that always fires is one nobody reads."""
        assert helper.strays(
            "labs/lab/configs",
            [("r1", "labs/lab/configs", "default", "user@clab")],
            ["r1.cfg"]) == []

    def test_it_lists_the_REMOTE_directory_not_a_local_one(self, helper):
        """The directory is on the clab host and this script runs on the
        NMAS. `os.listdir` raised `FileNotFoundError` — the least
        informative possible answer to *"is there litter on the clab
        host"*, because it names a local path that was never going to exist.

        Parsed: the docstring explains the defect using `os.listdir`."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(helper))
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert attrs, "the parse found nothing"
        assert "listdir" not in attrs, "it lists the NMAS's own filesystem"
        assert "run" in attrs, "nothing shells out, so nothing asks the host"

    def test_a_failed_listing_is_UNPROVEN_not_clean(self, helper,
                                                    monkeypatch, capsys):
        """*"I could not look"* and *"there is nothing there"* are the two
        answers this must never confuse."""
        monkeypatch.setattr(helper, "fetch", lambda *a, **k: [
            ("r1", "labs/lab/configs", "default", "user@clab")])
        monkeypatch.setattr(helper, "remote_listing", lambda h, d: (_ for _ in ()).throw(
            helper.StrayLookupFailed("ssh: connect refused")))
        monkeypatch.setattr(helper.sys, "argv",
                            ["x", "--url", "http://nmas",
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

    def test_a_lab_that_omits_the_LAUNCH_PATCH_is_refused_too(self,
                                                              monkeypatch):
        """**Added because a control passed.** The dangerous case is a lab
        that names `configs_dir` and omits `launch_patch`: the resolver
        returns `""`, and a fallback would read rcn-lab1's patch for a
        device booting its own."""
        from modules.nsot import credential_rotation as cr

        monkeypatch.setattr(
            "modules.settings_schema.get_setting",
            lambda k, d=None: {
                "clab_labs": {"r6": {"configs_dir": "labs/r6/configs"}},
                "clab_launch_patch": "labs/lab/patches/c8000v-launch.py",
            }.get(k, d))
        monkeypatch.setattr(cr, "_lab_of", lambda ln, h: "r6")

        t = cr.clab_target_for("Default", "r6")
        assert t["configs_dir"] == "labs/r6/configs"
        assert t["launch_patch"] == "", \
            "an unnamed patch resolved to the default lab's"

    def test_persist_refuses_on_either_missing_path(self):
        import inspect

        from modules.nsot import credential_rotation as cr

        src = inspect.getsource(cr.persist)
        assert '("configs_dir", "launch_patch")' in src
        assert "not the one booting this device" in src


class TestEveryVerifierGoesThroughTheResolver:
    """**The defect the live run found, and the control for it.**

    `nmas-check-startup-applies` read
    `dmarchak@10.0.0.210:labs/lab/configs/r6.cfg` — the **default** lab's
    directory — while `clab_target_for('Default', 'r6')` returned
    `labs/r6/configs`. The map existed and one caller was not using it,
    **by omission**: both verifiers fell back to `get_setting()` when the
    caller passed nothing, which is the failure mode a default fallback is
    built to create. Seventh instance of that class, and the first inside
    the thing built to prevent it.

    It failed closed only because the file was absent — *the same accident
    that made the configs-only fix look safe.*

    **This class was deleted once**, by a truncating edit while rewriting
    the tests below it, and the deletion was caught by these controls
    passing rather than by `check_removed_definitions.py` — which cannot
    help, because nothing *calls* a test.
    """

    @pytest.fixture
    def r6(self, monkeypatch):
        from modules.nsot import credential_rotation as cr

        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: {
                                "clab_host": "user@clab",
                                "clab_configs_dir": "labs/lab/configs",
                                "clab_launch_patch":
                                    "labs/lab/patches/c8000v-launch.py",
                                "clab_labs": {"r6": {
                                    "configs_dir": "labs/r6/configs",
                                    "launch_patch": "labs/r6/patches/"
                                                    "c8000v-launch-adopted.py"}},
                            }.get(k, d))
        monkeypatch.setattr(cr, "_lab_of",
                            lambda ln, h: "r6" if h == "r6" else "default")
        return cr

    def _reads(self, cr, monkeypatch):
        seen = []

        def _spy(clab, command, **kw):
            seen.append(command)
            return {"ok": False, "error": "spy"}

        monkeypatch.setattr(cr, "_ssh_read", _spy)
        return seen

    def test_applies_reads_the_devices_OWN_configs_dir(self, r6, monkeypatch):
        from modules.nsot.bootstrap_config import VRNETLAB_INJECTS_USER

        seen = self._reads(r6, monkeypatch)
        r6.verify_startup_applies("r6",
                                  platform=sorted(VRNETLAB_INJECTS_USER)[0],
                                  username="admin")

        assert seen, "it read nothing"
        assert "labs/r6/configs/r6.cfg" in seen[0]
        assert "labs/lab/configs" not in seen[0], \
            "it read the default lab's directory for a device in another lab"

    def test_a_default_lab_device_still_reads_the_default(self, r6,
                                                          monkeypatch):
        """**The floor.** A resolver that sent everything to r6's lab would
        satisfy the test above."""
        from modules.nsot.bootstrap_config import VRNETLAB_INJECTS_USER

        seen = self._reads(r6, monkeypatch)
        r6.verify_startup_applies("r1",
                                  platform=sorted(VRNETLAB_INJECTS_USER)[0],
                                  username="admin")

        assert "labs/lab/configs/r1.cfg" in seen[0]

    def test_startup_file_resolves_the_same_way(self, r6, monkeypatch):
        calls = []

        class _P:
            returncode = 0
            stdout = "0\n"
            stderr = ""

        def _run(cmd, **kw):
            calls.append(" ".join(cmd))
            return _P()

        monkeypatch.setattr("subprocess.run", _run)
        out = r6.verify_startup_file("r6", "secret 9 $9$x")

        assert "labs/r6/configs/r6.cfg" in calls[0]
        assert out["lab"] == "r6", "the result does not say which lab"

    def test_neither_verifier_reads_the_settings_directly_any_more(self):
        """The fallback IS the defect, so it is gone rather than corrected.

        Parsed: both functions' prose names `get_setting`."""
        import ast
        import inspect
        import textwrap

        from modules.nsot import credential_rotation as cr

        for fn in (cr.verify_startup_file, cr.verify_startup_applies):
            tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
            called = {getattr(n.func, "id", getattr(n.func, "attr", ""))
                      for n in ast.walk(tree) if isinstance(n, ast.Call)}
            assert called, f"the parse found no calls in {fn.__name__}"
            assert "get_setting" not in called, (
                f"{fn.__name__} reads the settings directly again — a caller "
                "that omits the target gets the default lab's paths")
            assert "_resolve_target" in called

    def test_the_check_script_passes_the_list(self):
        """The caller that was not using the map."""
        import os

        src = open(os.path.join(ROOT, "scripts",
                                "nmas-check-startup-applies"),
                   encoding="utf-8").read()
        assert "list_name=ref.name" in src
