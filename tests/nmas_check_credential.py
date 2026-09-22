"""Import shim for `scripts/nmas-check-credential` (not a test module).

The script's filename carries hyphens, matching its siblings, so it cannot be
imported directly. Loading it by path keeps the tests pointed at the file that
actually runs rather than at a copy that could drift from it.
"""

import importlib.util
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "scripts", "nmas-check-credential")
_spec = importlib.util.spec_from_loader(
    "nmas_check_credential",
    importlib.machinery.SourceFileLoader("nmas_check_credential", _PATH))
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

ACCEPTED = _module.ACCEPTED
REFUSED = _module.REFUSED
INCONCLUSIVE = _module.INCONCLUSIVE
check = _module.check
