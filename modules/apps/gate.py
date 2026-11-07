"""A controller app's gate: the job gate's ONE verdict (`modules/jobs/gate.py`) with two checks
around it (the SDN platform design rev. 6, section 11a, item 3: `mercury app check` and an
app's Publish call this one function, so the two cannot drift, T24).

The checks, in order (`APP_CHECKS`):
1. `manifest`: `manifest.yml` is valid (`modules/apps/manifest.load_manifest`), its `name` is
   the spec card's, the card's `kind` is `app`, and every test the manifest names is a
   `test_*.py` file in the folder's top level, where the gate's runner reads tests (a test the
   manifest names that the gate never runs would look checked and not be);
2. to 8. the job gate's checks (`modules.jobs.gate.CHECKS`), over the app folder's Python
   modules and tests, exactly as for a job;
9. `reconcile`: the reconcile test (T16: connect, disconnect, reconnect with another owner's
   flows) in the container harness. **Not run until the harness lands with P2a**, and a check
   not run is not passed, so an app's verdict cannot pass before then: a pass without it would
   be a wrong thing looking right.
"""

import os

from modules.apps.manifest import MANIFEST, load_manifest
from modules.jobs import gate as job_gate, runner, spec as spec_card
from modules.jobs.base import ContractError

APP_CHECKS = ("manifest",) + job_gate.CHECKS + ("reconcile",)
RECONCILE_NOT_RUN = "not run: the container harness lands with P2a"

RULES = {
    "manifest": f"{MANIFEST} is valid, names the app the spec card names, and every test it "
                "lists is a test_*.py file in the folder's top level.",
    **job_gate.RULES,
    "reconcile": "The reconcile test (T16) passes in the container harness: the app is "
                 "connected, disconnected and reconnected with another owner's flows, and "
                 "adds or removes only the difference.",
}
ACTIONS = {
    "manifest": f"Correct each field named in {MANIFEST}.",
    **job_gate.ACTIONS,
    "reconcile": "Run `mercury app check` again once the container harness (P2a) is "
                 "installed: until it runs, the app's verdict cannot pass.",
}


def _manifest_check(folder: str) -> job_gate.Check:
    try:
        manifest = load_manifest(folder)
    except ContractError as exc:
        return job_gate.Check("manifest", False, f"{MANIFEST} is refused", ACTIONS["manifest"],
                              tuple(exc.problems))
    problems = []
    try:
        card = spec_card.load_spec(folder)
    except ContractError:
        card = None                         # the spec check names its problems
    if card is not None:
        if card.kind != "app":
            problems.append(f"{spec_card.SPEC}'s kind is {card.kind!r}, and an app's card says "
                            "kind: app")
        if card.name != manifest.name:
            problems.append(f"{MANIFEST}'s name {manifest.name!r} is not {spec_card.SPEC}'s "
                            f"{card.name!r}: one app, one name")
    for test in manifest.tests:
        base = os.path.basename(test)
        if "/" in test or not base.startswith(runner.TEST_PREFIX) or not base.endswith(".py"):
            problems.append(f"tests: {test!r} is not a {runner.TEST_PREFIX}*.py file in the "
                            "folder's top level, where the gate's runner reads tests")
        elif not os.path.isfile(os.path.join(folder, test)):
            problems.append(f"tests: {test!r} is not in the folder")
    if problems:
        return job_gate.Check("manifest", False, f"{len(problems)} problems with {MANIFEST}",
                              ACTIONS["manifest"], tuple(problems))
    return job_gate.Check("manifest", True, f"{MANIFEST}: {manifest.name} {manifest.version}",
                          "")


def check(folder, *, marks=(), changed_lines: dict = None) -> job_gate.Verdict:
    """The app gate's verdict on *folder* (see the module's docstring); *marks* and
    *changed_lines* are the job gate's."""
    folder = str(folder)
    manifest = _manifest_check(folder)
    inner = job_gate.check(folder, marks=marks, changed_lines=changed_lines)
    reconcile = job_gate.Check("reconcile", False, RECONCILE_NOT_RUN, ACTIONS["reconcile"])
    return job_gate.Verdict(folder, [manifest, *inner.checks, reconcile], inner.timings,
                            inner.run, inner.mutation)
