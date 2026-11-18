"""C646: `nmas-deploy` runs through the link DEPLOY_LINUX tells the operator to make
(`ln -sf ~/python/Agentic_NMAS/scripts/nmas-deploy ~/bin/nmas-deploy`).

Its `__main__` block finds the checkout to import `modules.app_interpreter`. Found from
`abspath(__file__)`, a run through the link looked in the link's folder's parent, found no
`modules`, and crashed before doing anything (measured on the host, 2026-10-10). Run here
through a link in another folder, the script reaches its own argument parser.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_it_runs_through_a_link_in_another_folder(tmp_path):
    link = tmp_path / "bin" / "nmas-deploy"
    link.parent.mkdir()
    link.symlink_to(os.path.join(ROOT, "scripts", "nmas-deploy"))
    r = subprocess.run([sys.executable, str(link), "--help"], capture_output=True, text=True,
                       timeout=60, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr[-600:]
    assert "usage: nmas-deploy" in r.stdout
    assert "ModuleNotFoundError" not in r.stderr


def test_its_backup_window_helper_loads_through_the_link(tmp_path):
    """C3851: loaded through the link, the backup-window guard finds `nmas-tier2-probe` beside
    the checkout's copy, not beside the link (it raised FileNotFoundError on every fast-lane
    deploy through ~/bin, measured on the host 2026-11-16)."""
    import datetime
    import importlib.machinery
    import importlib.util
    link = tmp_path / "bin" / "nmas-deploy"
    link.parent.mkdir()
    link.symlink_to(os.path.join(ROOT, "scripts", "nmas-deploy"))
    loader = importlib.machinery.SourceFileLoader("nmas_deploy_through_link", str(link))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    assert mod.__file__ == str(link)
    utc = datetime.timezone.utc
    # 03:00 America/Denver (MST, UTC-7) is inside 02:30 to 03:30; 00:00 is not.
    inside = datetime.datetime(2026, 11, 18, 10, 0, tzinfo=utc).timestamp()
    outside = datetime.datetime(2026, 11, 18, 7, 0, tzinfo=utc).timestamp()
    assert mod.in_backup_window(inside) is True
    assert mod.in_backup_window(outside) is False
    assert mod.backup_window_words(outside).startswith("02:30 to 03:30 America/Denver (09:30")
