"""Import shim for `scripts/nmas-check-startup-applies` (not a test module).

Loaded by path because the script's filename carries hyphens, matching its
siblings. Pointing the tests at the file that actually runs keeps them from
drifting from it.
"""

import importlib.machinery
import importlib.util
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "scripts", "nmas-check-startup-applies")
_loader = importlib.machinery.SourceFileLoader("nmas_check_startup_applies", _PATH)
_module = importlib.util.module_from_spec(
    importlib.util.spec_from_loader("nmas_check_startup_applies", _loader))
_loader.exec_module(_module)

check_one = _module.check_one
main = _module.main
