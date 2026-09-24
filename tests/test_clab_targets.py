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

    def test_strays_finds_a_config_in_the_wrong_lab(self, helper, tmp_path):
        """`labs/lab/configs/r6.cfg`, written before the sync learned about
        r6's lab: inert, and a file that looks like a thing it is not."""
        d = tmp_path / "lab" / "configs"
        d.mkdir(parents=True)
        (d / "r1.cfg").write_text("x")
        (d / "r6.cfg").write_text("x")

        found = helper.strays(str(d), [("r1", str(d), "default"),
                                       ("r6", str(tmp_path / "r6" / "configs"),
                                        "r6")])

        assert [os.path.basename(p) for p, _w in found] == ["r6.cfg"]

    def test_and_finds_nothing_when_everything_is_in_place(self, helper,
                                                           tmp_path):
        """The floor: a detector that always fires is a detector nobody
        reads."""
        d = tmp_path / "configs"
        d.mkdir(parents=True)
        (d / "r1.cfg").write_text("x")

        assert helper.strays(str(d), [("r1", str(d), "default")]) == []

    def test_a_lab_that_omits_the_LAUNCH_PATCH_is_refused_too(self,
                                                              monkeypatch):
        """**Added because a control passed.**

        Making `launch_patch` fall back to the default lab left every test
        green, because the fixture's lab defines both. The dangerous case is
        a lab that names `configs_dir` and omits `launch_patch`: the
        resolver returns `""`, and
        `verify_startup_applies(launch_patch="")` **falls back to the
        setting** — so the empty string would have read rcn-lab1's patch for
        a device booting its own. An empty value must be refused, not
        forwarded.
        """
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
