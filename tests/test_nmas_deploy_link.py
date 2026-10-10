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
