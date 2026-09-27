"""P.6 measurement 1: the configless launch patch, tested against the REAL script.

vrnetlab always gives a C8000v a day-0 config (a CVAC ISO, attached with
`-cdrom`), and its watchdog restarts a VM after 300 quiet console spins.
`patch-configless.py` removes both for the probe's own copy. Its claims are
checked structurally (AST) on the patched real script, never by searching the
text, because the patch's own comments quote what it changes.
"""

import ast
import hashlib
import importlib.machinery
import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "launch", "c8000v-launch-adopted.py")
PATCHER = os.path.join(ROOT, "docs", "bootstrap-probe", "patches", "patch-configless.py")
MEASURED_SHA = "e483dd2475b505bda4b2a95e5e26468971f05f856394f49849917e4cb15a8484"


def _patcher():
    loader = importlib.machinery.SourceFileLoader("patch_configless", PATCHER)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _real():
    with open(FIXTURE, encoding="utf-8") as fh:
        return fh.read()


def _method(tree, name):
    found = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    assert found, f"no method {name} in the launch script"
    return found[0]


def _parents(tree):
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


def _is_cdrom_extend(node):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "extend"
            and any(isinstance(a, ast.List) and any(isinstance(e, ast.Constant) and e.value == "-cdrom"
                                                     for e in a.elts) for a in node.args))


def _calls(fn, attr):
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == attr and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"]


def test_the_fixture_is_the_script_that_was_measured():
    with open(FIXTURE, "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == MEASURED_SHA


class TestTheRealScriptBeforeThePatch:
    """What the unmodified adopted script does: the reading that answered
    prediction 1 before anything booted. Floors, so the checks below can fail."""

    def test_it_always_attaches_the_config_iso(self):
        tree = ast.parse(_real())
        parents = _parents(tree)
        extends = [n for n in ast.walk(_method(tree, "__init__")) if _is_cdrom_extend(n)]
        assert extends
        assert not isinstance(parents[parents[extends[0]]], ast.If), \
            "the unpatched script already attaches -cdrom conditionally"

    def test_its_watchdog_restarts_a_quiet_vm(self):
        spin = _method(ast.parse(_real()), "bootstrap_spin")
        assert _calls(spin, "stop") and _calls(spin, "start")


class TestThePatchedScript:
    @pytest.fixture(scope="class")
    def tree(self):
        return ast.parse(_patcher().patch(_real()))

    def test_it_compiles(self):
        compile(_patcher().patch(_real()), "launch.py", "exec")

    def test_the_config_iso_is_attached_only_in_install_mode(self, tree):
        parents = _parents(tree)
        extends = [n for n in ast.walk(_method(tree, "__init__")) if _is_cdrom_extend(n)]
        assert len(extends) == 1
        guard = parents[parents[extends[0]]]
        assert isinstance(guard, ast.If)
        assert ast.unparse(guard.test) == "self.install_mode"

    def test_the_watchdog_never_restarts_the_vm(self, tree):
        spin = _method(tree, "bootstrap_spin")
        assert not _calls(spin, "stop") and not _calls(spin, "start")

    def test_the_console_wait_accepts_ios_xe_s_own_prompt(self, tree):
        spin = _method(tree, "bootstrap_spin")
        consts = {n.value for n in ast.walk(spin) if isinstance(n, ast.Constant) and isinstance(n.value, bytes)}
        assert {b"Press RETURN to get started", b"initial configuration dialog",
                b"CVAC-4-CONFIG_DONE"} <= consts

    def test_the_prompt_marks_the_vm_running_and_releases_the_console(self, tree):
        spin = _method(tree, "bootstrap_spin")
        branch = [n for n in ast.walk(spin) if isinstance(n, ast.If)
                  and "ridx in (2, 3)" in ast.unparse(n.test)]
        assert len(branch) == 1
        body = ast.unparse(ast.Module(body=branch[0].body, type_ignores=[]))
        assert "self.running = True" in body and "self.scrapli_tn.close()" in body
        assert "self.mode != 'controller'" in ast.unparse(branch[0].test), \
            "controller mode uses indices 2 and 3 for its own patterns"


# The image's disks, read from / inside r6's container (2026-09-26): the Cisco
# base (Aug 28 00:56, no backing file) and the overlay the image's install step
# saved "do wr" into (Aug 28 01:06, backed by the base). A third file there,
# <base>-overlay-overlay.qcow2, was dated the day it was read: vrnetlab creates
# it at start in the container's own layer, so a FIRST start sees only these two.
BASE = "c8000v-universalk9_8G_serial.17.06.01a.qcow2"
INSTALL_OVERLAY = "c8000v-universalk9_8G_serial.17.06.01a-overlay.qcow2"


class _Reached(Exception):
    """Raised by the stub vrnetlab.VM: the disk the script hands to vrnetlab."""


def _construct(source, listing, install_mode):
    """Run the script's C8000v_vm.__init__ up to vrnetlab's constructor, on a
    fake root. Only the class is executed (never the module, whose top level
    alters the logging module), with a fake `os` recording every removal."""
    import logging
    import re
    import types

    tree = ast.parse(source)
    cls = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "C8000v_vm"]
    assert len(cls) == 1

    class VM:
        def __init__(self, *args, **kwargs):
            raise _Reached(kwargs.get("disk_image"))

    removed = []
    files = {"/" + e for e in listing}
    fake_os = types.SimpleNamespace(
        listdir=lambda path: list(listing),
        rename=lambda a, b: None,
        remove=lambda path: (removed.append(path), files.discard(path)),
        path=types.SimpleNamespace(isfile=lambda p: p in files, exists=lambda p: p in files))
    ns = {"vrnetlab": types.SimpleNamespace(VM=VM), "os": fake_os, "re": re,
          "logging": logging, "logger": logging.getLogger("test_configless_patch")}
    exec(compile(ast.Module(body=cls, type_ignores=[]), "launch.py", "exec"), ns)
    with pytest.raises(_Reached) as reached:
        ns["C8000v_vm"]("bp-ztp-a", "admin", "admin", "scrapli", install_mode=install_mode)
    return reached.value.args[0], removed


class TestTheDiskItBootsFrom:
    """The config ISO is not the only day-0 config: the install overlay's NVRAM
    holds the one the image build saved. A configless boot needs the BASE disk
    and a run-time overlay created fresh from it."""

    LISTING = ["bin", BASE, INSTALL_OVERLAY, "tftpboot"]      # a first start

    def test_unpatched_it_boots_the_install_overlay(self):
        # The reading that found it, and the floor the next test needs.
        disk, removed = _construct(_real(), self.LISTING, install_mode=False)
        assert disk == "/" + INSTALL_OVERLAY and removed == []

    def test_patched_it_boots_the_base_with_the_install_overlay_removed(self):
        disk, removed = _construct(_patcher().patch(_real()), self.LISTING, install_mode=False)
        assert disk == "/" + BASE
        assert removed == ["/" + INSTALL_OVERLAY], "exactly the install overlay, nothing else"

    def test_install_mode_removes_nothing(self):
        disk, removed = _construct(_patcher().patch(_real()), [BASE, INSTALL_OVERLAY], install_mode=True)
        assert disk == "/" + BASE and removed == []

    def test_an_image_with_no_install_overlay_removes_nothing(self):
        disk, removed = _construct(_patcher().patch(_real()), ["bin", BASE], install_mode=False)
        assert disk == "/" + BASE and removed == []


class TestItRefuses:
    def test_a_script_already_patched(self):
        patcher = _patcher()
        with pytest.raises(patcher.Refused, match="already patched"):
            patcher.patch(patcher.patch(_real()))

    @pytest.mark.parametrize("index", range(6))
    def test_a_missing_anchor_by_name(self, index):
        patcher = _patcher()
        name, anchor, _ = patcher.EDITS[index]
        with pytest.raises(patcher.Refused, match=name):
            patcher.patch(_real().replace(anchor, ""))

    def test_a_duplicated_anchor(self):
        patcher = _patcher()
        name, anchor, _ = patcher.EDITS[0]
        with pytest.raises(patcher.Refused, match="found 2"):
            patcher.patch(_real() + anchor)

    @pytest.mark.parametrize("path", ["/home/x/labs/lab/patches/c8000v-launch.py",
                                      "/home/x/labs/r6/patches/c8000v-launch-adopted.py"])
    def test_a_production_labs_own_file(self, path):
        with pytest.raises(SystemExit, match="refusing"):
            _patcher().main([path])

    def test_without_write_it_writes_nothing(self, tmp_path, capsys):
        copy = tmp_path / "c8000v-launch-configless.py"
        copy.write_text(_real())
        assert _patcher().main([str(copy)]) == 0
        assert copy.read_text() == _real()
        assert "diff only" in capsys.readouterr().out
