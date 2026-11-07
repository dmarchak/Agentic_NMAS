"""A controller app's gate: ONE verdict on an app's folder, which `mercury app check` and an
app's Publish call (the SDN platform design rev. 6, section 11a, item 3, and revision 7,
section 11c.6; T24: the two cannot drift, because there is one function).

**It runs no app code** (C2635, the operator, 2026-11-07): an app is a Ryu controller app, not
a job, and its tests run in the container harness, never in Mercury's job sandbox. The checks,
in order (`APP_CHECKS`, the job gate's names with two around them):
1. `manifest`: `manifest.yml` is valid (`modules/apps/manifest.load_manifest`), its `name` is
   the spec card's, the card's `kind` is `app`, and every test it names is a `test_*.py` file
   at the folder's root or in its `tests/` subfolder (C2636, `runner.test_location_problem`),
   and present. Passed, it lists each network destination the manifest declares (`egress`),
   for the reviewer;
2. `spec`: the spec card, as the job gate reads it;
3. `static`: the APP allowlist (`modules/apps/allowlist.py`), not the job's: every module and
   test parsed as the controller's MEASURED Python (*python*: the network's record,
   `modules/sdn/controller_runtime.target`, which the CLI's `--network` and Publish pass) and
   walked, refusing grammar and standard-library names that version lacks; passed, it lists
   each egress call it read and the version it checked against, with where that was
   measured. A version not known (none recorded, unreadable, no network named) is "can't
   tell", and the check FAILS on it, never passes and never assumes one;
4. `tests`, 7. `mutation`, 8. `survivors`, 9. `reconcile`: they need the app's code run, so
   each says "not run: app tests run in the container harness, which lands with P2a" and
   fails until the harness runs them. A check not run is not passed, so an app's verdict
   cannot pass before then: a pass without them would be a wrong thing looking right;
5. `examples` and 6. `asserts`: the job gate's, read from the source (`@covers` and the
   asserts), over the app's tests wherever they sit.
"""

import os

from modules.apps import allowlist
from modules.apps.manifest import MANIFEST, load_manifest
from modules.discovery import PYTHON_READ
from modules.jobs import gate as job_gate, runner, spec as spec_card
from modules.jobs.base import ContractError

APP_CHECKS = ("manifest",) + job_gate.CHECKS + ("reconcile",)
#: The checks that need the app's code run, and what each says until the harness runs it.
HARNESS_CHECKS = ("tests", "mutation", "survivors", "reconcile")
HARNESS_NOT_RUN = ("not run: app tests run in the container harness, which lands with P2a")

RULES = {
    "manifest": f"{MANIFEST} is valid, names the app the spec card names, lists each test as "
                "a test_*.py file at the folder's root or in tests/, and declares every "
                "network destination the app reaches (egress), which the check lists.",
    **job_gate.RULES,
    "static": "Every module and test of the app parses as the Python its network's controller "
              "runs apps on, as measured and recorded for the network (never assumed), uses "
              "no grammar, module or name that version lacks, and passes the app allowlist: "
              "imports only of the app's own "
              f"modules, ryu, the app SDK ({allowlist.SDK}) and the standard library's data "
              "modules (in tests, also pytest's raises and modules.jobs' covers and refused); "
              "no network, process, file or interpreter module; the network reached only by "
              f"{allowlist.SDK}.egress, its destination a string literal the manifest "
              "declares; and the job allowlist's builtin, dunder and except rules.",
    "tests": "The app's tests pass in the container harness, on the controller's Python; "
             "never in the job sandbox.",
    "mutation": "The app's code is mutated and every mutant run, in the container harness.",
    "survivors": "Every mutant the app's tests did not notice is killed by a new test, or "
                 "marked equivalent by the reviewer, a person, with a reason.",
    "reconcile": "The reconcile test (T16) passes in the container harness: the app is "
                 "connected, disconnected and reconnected with another owner's flows, and "
                 "adds or removes only the difference.",
}
#: What clears a check the harness runs, until it is installed.
HARNESS_ACTION = ("Run `mercury app check` again once the container harness (P2a) is "
                  "installed: an app's code runs there, never in the job sandbox, and until "
                  "it runs, the app's verdict cannot pass.")
ACTIONS = {
    "manifest": f"Correct each field named in {MANIFEST}.",
    **job_gate.ACTIONS,
    "static": f"Remove each use named: an app imports ryu, {allowlist.SDK} and the standard "
              "library's data modules, and reaches the network only by "
              f"{allowlist.SDK}.egress(\"<a destination {MANIFEST} declares>\", ...).",
    **{name: HARNESS_ACTION for name in HARNESS_CHECKS},
}
#: What clears a `static` check that cannot tell which Python to check against.
PYTHON_ACTION = ("Name the app's network (`mercury app check <folder> --network <network>`). "
                 "Its controller's Python is the network's record, measured by the controller "
                 f"host's interpreter read (`{PYTHON_READ}`); a network whose record holds "
                 "none cannot be checked until that read records it.")


def _manifest_check(folder: str):
    """`(manifest or None, the manifest check)`."""
    try:
        manifest = load_manifest(folder)
    except ContractError as exc:
        return None, job_gate.Check("manifest", False, f"{MANIFEST} is refused",
                                    ACTIONS["manifest"], tuple(exc.problems))
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
        where = runner.test_location_problem(test)
        if where:
            problems.append(f"tests: {where}")
        elif not os.path.isfile(os.path.join(folder, *test.split("/"))):
            problems.append(f"tests: {test!r} is not in the folder")
    if problems:
        return manifest, job_gate.Check("manifest", False, f"{len(problems)} problems with "
                                                           f"{MANIFEST}", ACTIONS["manifest"],
                                        tuple(problems))
    egress = tuple(e.words() for e in manifest.egress) or (
        "egress: none declared, so the app reaches no network destination of its own",)
    return manifest, job_gate.Check("manifest", True, f"{MANIFEST}: {manifest.name} "
                                                      f"{manifest.version}, "
                                                      f"{len(manifest.egress)} egress "
                                                      "destinations", "", egress)


def _harness(name: str) -> job_gate.Check:
    return job_gate.Check(name, False, HARNESS_NOT_RUN, ACTIONS[name])


def _static_check(sources, manifest, python):
    found = allowlist.check(sources, manifest.egress_names() if manifest is not None else None,
                            python=python)
    if found.python:
        # Can't tell: the version-dependent checks could not run, so the check fails on that,
        # and names whatever else the walk refused.
        action = PYTHON_ACTION + (f" Then: {ACTIONS['static']}" if found.problems else "")
        return job_gate.Check("static", False, found.python, action, tuple(found.problems))
    if found.problems:
        return job_gate.Check("static", False, f"{len(found.problems)} uses refused",
                              ACTIONS["static"], tuple(found.problems)
                              + (f"checked against {found.target.words}",))
    version = ".".join(str(n) for n in found.target.version)
    if found.target.provisional:
        version += " (provisional)"
    return job_gate.Check("static", True, f"{len(sources.job)} modules and "
                                          f"{len(sources.tests)} test files allowed on Python "
                                          f"{version}, {len(found.egress)} egress calls", "",
                          tuple(found.egress) + (f"checked against {found.target.words}",))


def check(folder, *, python=None, marks=(), changed_lines: dict = None) -> job_gate.Verdict:
    """The app gate's verdict on *folder* (see the module's docstring). *python* is the
    controller's Python to check against (`python_versions.as_target`'s: the network's
    `controller_runtime.target`, or `(3, 5)`); None, the default, is not known, so `static`
    says "can't tell" and fails. *marks* and *changed_lines* are the job gate's, kept for
    Publish's one call: they are the mutation step's, which the harness runs."""
    del marks, changed_lines                # the harness's, once it lands
    folder = str(folder)
    manifest, manifest_check = _manifest_check(folder)
    card, spec = job_gate.spec_check(folder)
    by_name = {"manifest": manifest_check, "spec": spec}
    try:
        sources = runner.load_sources(folder)
    except ContractError as exc:
        by_name["static"] = job_gate.Check("static", False, "the folder is refused",
                                           job_gate.FOLDER_ACTION, tuple(exc.problems))
        why = "the folder's files are refused"
        for name in ("examples", "asserts"):
            by_name[name] = job_gate.not_run(name, why, "static")
    else:
        by_name["static"] = _static_check(sources, manifest, python)
        tests = []
        for file, tree in job_gate.parsed_tests(sources).items():
            found, _problems = runner.collect(tree, file)
            tests.extend(found)
        by_name["examples"] = job_gate.examples_check(card, tests)
        by_name["asserts"] = job_gate.asserts_check(sources, len(tests))
    for name in HARNESS_CHECKS:
        by_name[name] = _harness(name)
    return job_gate.Verdict(folder, [by_name[name] for name in APP_CHECKS], {})
