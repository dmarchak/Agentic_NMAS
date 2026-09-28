"""The running commit's CI verdict as a reader job: the fifth instance of
modules/reader_job.py, and the status bar's version item.

**One implementation of each answer** (the operator, 2026-09-28: two
implementations of "what is running" is the pattern this project keeps
removing):
- WHAT IS RUNNING is `routes.health._COMMIT`, what this process loaded, as
  `/health` serves it to `nmas-deploy`;
- WHETHER IT IS THE CHECKOUT'S COMMIT is `job_health.version_rows()` (C129),
  read from the job-health reader's stored value, never computed again;
- ITS CI VERDICT is `ci_verdict()` in `scripts/nmas-deploy`, the gate the
  deploy itself runs, including C170's walk. This reader LOADS that script
  and calls it; there is no second copy of the verdict logic.

**Why a reader.** The verdict needs GitHub, an outside service, so it is
never asked on a page load (rule 1). GitHub's unauthenticated API allows
60 requests an hour per address, shared with `nmas-deploy` on the same host.
A verdict costs one request, and up to eleven when it walks back through
commits with no run (C170), so every 15 min bounds this reader to about four
requests an hour typically and 44 at worst.

The value names the commit it judged. A process that restarted onto a new
commit before the next read shows that its commit is not judged yet, never
the previous commit's verdict as its own.
"""

import importlib.machinery
import importlib.util
import os
import threading

from modules import reader_job

INTERVAL_SECONDS = 900
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-deploy")

_loaded = None
_mu = threading.Lock()


def deploy_script():
    """`scripts/nmas-deploy`, loaded once as a module: the ONE implementation
    of the CI verdict. It has no side effects at import (a `__main__` guard)."""
    global _loaded
    with _mu:
        if _loaded is None:
            loader = importlib.machinery.SourceFileLoader("nmas_deploy_script", SCRIPT)
            spec = importlib.util.spec_from_loader("nmas_deploy_script", loader)
            mod = importlib.util.module_from_spec(spec)
            loader.exec_module(mod)
            _loaded = mod
        return _loaded


def state_of(mod, code) -> str:
    """The script's exit code, in the words its constants name."""
    return {mod.OK: "verified", mod.CI_REFUSED: "failed", mod.COULD_NOT_ASK: "could_not_ask",
            mod.CI_PENDING: "pending", mod.CI_CANCELLED: "cancelled"}.get(code, f"code {code}")


def read(commit=None, verdict=None) -> dict:
    from routes import health

    commit = health._COMMIT if commit is None else commit
    if not commit:
        raise RuntimeError(f"the loaded commit is unknown: {health._COMMIT_ERROR}")
    mod = deploy_script()
    code, sentence = (verdict or mod.ci_verdict)(ROOT, commit)
    return {"commit": commit, "code": code, "state": state_of(mod, code), "sentence": sentence}


READER = reader_job.register(reader_job.Reader(
    name="ci-verdict",
    what="the running commit's CI verdict, by nmas-deploy's own gate, for the status bar",
    endpoints=("GitHub Actions runs for the running commit (and its ancestors when it has none)",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("GitHub allows 60 unauthenticated requests an hour per address, shared with "
                    "nmas-deploy; a verdict costs 1, up to 11 walking back (C170), so every "
                    "15 min is about 4 an hour and 44 at worst"),
    read=read,
    invalidates=("ci_verdict",),
    remedy="Read the error above: it names what could not be asked",
    window="the verdict at the read, for the commit named in the value",
))
