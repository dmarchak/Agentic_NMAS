"""An app version's plain test run, in the container harness, on its network's controller Python
(C2854; the operator's replan of 2026-11-09: "Minimal Publish: a person's review plus the plain
test run's pass").

**Where the app's code runs (the operator's decision C2635, 2026-11-07).** Never in Mercury's
process or its job sandbox: `run` starts a fresh container of the harness's app test image,
`mercury-harness-apptest:4.34-py<python>` (tests/containers/apptest/Dockerfile: the harness's
controller image, Ryu 4.34 on that Python, with pytest at the version measured for it), and
reads what pytest printed. The container is held to the harness's conditions
(tests/containers/compose.yml) and closer: no network at all (`--network none`, where the
harness's services share one internal network), not privileged, every capability dropped, none
added, no-new-privileges, a read-only root with a small tmpfs for /tmp, the harness's
unprivileged uid 10001, a process limit, and the app's folder and the app SDK
(modules/apps/sdk, on PYTHONPATH as the controller's drop-in puts it) mounted read-only. pytest
runs with no cache (`-p no:cacheprovider`), no bytecode (`-B` and PYTHONDONTWRITEBYTECODE), no
ini file of the app's (`-c /dev/null`: the app's listed tests are collected by pytest's own
rules, never the app's), and exactly the manifest's listed test files.

**The answer** is ``{"ok", "passed", "failed", "errors", "skipped", "python", "python_seen",
"seconds", "content_sha256", "output", "error", "command"}`` (``seconds``: the `docker run`'s
wall time, None when it did not finish). ``ok`` only when pytest exited 0, at least
one test ran, the summary's counts parsed, nothing was skipped (an app's tests may not skip: the
app allowlist takes pytest's `raises` alone), the interpreter pytest reported is the one asked
for, and the folder's content hash after the run is the hash before it. ``content_sha256`` is
recomputed from the folder's bytes by the apply script's own `folder_hash`
(`modules/apps/channel.script()`), the hash a Published version is pinned to, so the caller
binds the pass to exactly what was tested. ``output`` is the last `OUTPUT_TAIL` characters of
what the container printed, masked by `modules.redact.redact_text` before it is cut. A timeout
(the container killed by its name), docker absent, docker not answering, the image not built,
a folder or test list refused: each is ``ok: False`` with ``error`` naming which, never an
exception.

**The docker seam.** Every docker invocation goes through *runner(argv, timeout_s)*, which
returns an object with ``returncode``, ``stdout`` and ``stderr`` (bytes or text) and may raise
`subprocess.TimeoutExpired` or `OSError`; the default is `subprocess.run` over an argv list,
never a shell string.

Nothing here parses an address (the container has no network), so there is no IPv4 or IPv6
case to give.
"""

import logging
import os
import re
import secrets
import stat
import subprocess
import time

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SDK = os.path.join(ROOT, "modules", "apps", "sdk")
IMAGE = "mercury-harness-apptest:4.34-py{python}"
APP_MOUNT = "/app"
SDK_MOUNT = "/opt/mercury-sdk"
#: The harness's unprivileged account (tests/containers/ryu/Dockerfile's `ryu`, uid 10001).
USER = "10001:10001"
UID = 10001
#: The harness's process limit for each service (tests/containers/compose.yml).
PIDS_LIMIT = "64"
TMPFS = "/tmp:size=16m"
#: How much of the container's output the answer keeps, after masking.
OUTPUT_TAIL = 4000
#: The bound on one app's test run, `docker run` to its exit. Measured 2026-11-09 on the laptop,
#: images built: 24 runs (Lab 9's three apps and the worked app, tests/fixtures/apps/
#: dns_overrides, 3 to 17 tests each, three times on Python 3.5 and on 3.9) took 0.48 to 0.57 s
#: (each answer's `seconds`), and the first run by hand 0.74 s; pytest itself reported 0.01 to
#: 0.02 s, so the container's start is the run. 2.5x the slowest is 1.85 s, rounded up to 5 s
#: for a loaded machine's container start (as scripts/nmas-harness's READY_BOUND_S is), until
#: CI's harness job, whose self-check prints each run's seconds, measures its own.
BOUND_S = 5.0
#: `docker image inspect` and `docker kill`: measured 2026-11-09 on the laptop at 0.02 s and,
#: killing a running test container at its bound, 0.13 s; 2.5x is under 1 s, rounded up to 5 s
#: for a daemon busy building an image.
DOCKER_BOUND_S = 5.0
VERSION = re.compile(r"^[0-9]+\.[0-9]+$")
#: pytest's header line, from 6.1.2 to 8.4.2: "platform linux -- Python 3.5.10, pytest-6.1.2, ..."
_HEADER = re.compile(r"^platform \S+ -- Python ([0-9]+\.[0-9]+)\.[0-9]+", re.M)
#: pytest's closing summary line: "==== 1 failed, 2 passed in 0.05s ====", "==== no tests ran in
#: 0.01s ====", "==== 3 passed in 65.12s (0:01:05) ====".
_SUMMARY = re.compile(r"^=+ (?P<body>.+?) in [0-9.]+s(?: \([0-9:]+\))? =+$")
_TERM = re.compile(r"^(?P<n>[0-9]+) (?P<kind>passed|failed|errors?|skipped|xfailed|xpassed|"
                   r"deselected|warnings?|rerun)$")


def default_runner(argv, timeout_s):
    """`subprocess.run` over the argv list, output captured, bounded by *timeout_s*."""
    return subprocess.run(argv, capture_output=True, timeout=timeout_s, check=False)


def image(python: str) -> str:
    return IMAGE.format(python=python)


def docker_command(folder: str, python: str, tests, name: str) -> list:
    """The `docker run` argv for *tests* (paths relative to *folder*) on *python*, in a
    container named *name* (its identity, for `docker kill` at the bound)."""
    return ["docker", "run", "--rm", "--pull", "never", "--name", name,
            "--privileged=false", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--user", USER, "--pids-limit", PIDS_LIMIT, "--tmpfs", TMPFS,
            "--mount", f"type=bind,src={folder},dst={APP_MOUNT},readonly",
            "--mount", f"type=bind,src={SDK},dst={SDK_MOUNT},readonly",
            "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", f"PYTHONPATH={APP_MOUNT}:{SDK_MOUNT}",
            "-e", "HOME=/tmp", "-w", APP_MOUNT, "--entrypoint", "python", image(python),
            "-B", "-m", "pytest", "-p", "no:cacheprovider", "-c", "/dev/null",
            "--rootdir", APP_MOUNT, "--color=no", "-rfE", "--", *tests]


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _mask(text: str) -> str:
    from modules.redact import redact_text

    return redact_text(text or "") or ""


def parse_counts(output: str):
    """``{"passed", "failed", "errors", "skipped", "other": {kind: n}}`` from pytest's last
    summary line in *output*, or None when no summary line parses."""
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    for line in reversed(lines):
        found = _SUMMARY.match(line)
        if not found:
            continue
        counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "other": {}}
        body = found.group("body")
        if body == "no tests ran":
            return counts
        for term in body.split(", "):
            t = _TERM.match(term)
            if not t:
                return None
            n, kind = int(t.group("n")), t.group("kind")
            if kind in ("error", "errors"):
                counts["errors"] += n
            elif kind in ("passed", "failed", "skipped"):
                counts[kind] += n
            elif not kind.startswith("warning"):
                counts["other"][kind] = counts["other"].get(kind, 0) + n
        return counts
    return None


def _tests_problem(folder: str, tests) -> str:
    if not tests:
        return "the manifest lists no tests: a run of nothing is not a pass"
    for test in tests:
        if not isinstance(test, str) or not test:
            return f"the test {test!r} is not a path"
        norm = os.path.normpath(test).replace(os.sep, "/")
        if os.path.isabs(test) or norm == ".." or norm.startswith("../") or norm != test:
            return f"the test {test!r} is not a plain path inside the app's folder"
        if not os.path.basename(norm).startswith("test_") or not norm.endswith(".py"):
            return f"the test {test!r} is not a test_*.py file"
        if not os.path.isfile(os.path.join(folder, test)):
            return f"the test {test!r} is not a file in {folder}"
    return ""


def _readable_problem(folder: str) -> str:
    """Why the container's account (uid 10001, neither owner nor group) cannot read *folder*,
    or ""."""
    for root, dirs, files in os.walk(folder):
        for name in [""] + dirs + files:
            path = os.path.join(root, name) if name else root
            st = os.lstat(path)
            need = (stat.S_IROTH | stat.S_IXOTH) if stat.S_ISDIR(st.st_mode) else stat.S_IROTH
            if st.st_mode & need != need:
                return (f"{os.path.relpath(path, folder)} in {folder} is mode "
                        f"{stat.filemode(st.st_mode)}: the test container's account (uid {UID}) "
                        f"cannot read it")
    return ""


def _hash(folder: str):
    """``(sha256, "")`` or ``("", why)``: the apply script's `folder_hash` of *folder*."""
    from modules.apps import channel

    try:
        return channel.script().folder_hash(folder), ""
    except Exception as exc:   # the script's Refused, or the folder unreadable
        return "", f"the content hash of {folder} could not be computed: {exc}"


def _answer(python, sha, command, **fields) -> dict:
    out = {"ok": False, "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
           "python": python, "python_seen": "", "seconds": None, "content_sha256": sha,
           "output": "",
           "error": "", "command": list(command)}
    out.update(fields)
    if not out["ok"]:
        log.warning("app test run of %s on Python %s: %s", sha[:12] or "?", python, out["error"])
    return out


def _docker_error(said, what: str) -> str:
    text = _mask((_text(said.stderr) or _text(said.stdout)).strip())
    return f"docker could not {what} (exit {said.returncode}): {text[-800:] or 'it said nothing'}"


def run(folder, python, *, tests, timeout_s, runner=None) -> dict:
    """Run exactly *tests* (the manifest's list, relative to *folder*) from the staged *folder*
    on the controller Python *python* (major.minor) in a fresh container, bounded by
    *timeout_s* seconds; the answer is in the module's docstring."""
    runner = runner or default_runner
    python = str(python or "")
    if not VERSION.match(python):
        return _answer(python, "", [], error=f"the controller's Python is major.minor (such as "
                                             f"3.5), not {python!r}")
    folder = os.path.realpath(os.fspath(folder))
    if not os.path.isdir(folder):
        return _answer(python, "", [], error=f"{folder} is not a folder")
    if "," in folder or "," in SDK:
        return _answer(python, "", [], error=f"{folder} holds a comma, which docker's --mount "
                                             "cannot take in a path")
    tests = list(tests or [])
    why = _tests_problem(folder, tests)
    if why:
        return _answer(python, "", [], error=why)
    sha, why = _hash(folder)
    if why:
        return _answer(python, "", [], error=why)
    why = _readable_problem(folder) or _readable_problem(SDK)
    if why:
        return _answer(python, sha, [], error=why)
    name = f"mercury-apptest-{secrets.token_hex(6)}"
    command = docker_command(folder, python, tests, name)
    want = image(python)

    try:
        said = runner(["docker", "image", "inspect", "--format", "{{.Id}}", want],
                      DOCKER_BOUND_S)
    except FileNotFoundError:
        return _answer(python, sha, command, error="docker is not installed here (no `docker` "
                                                    "on PATH), so the app's tests cannot run")
    except subprocess.TimeoutExpired:
        return _answer(python, sha, command, error=f"docker did not answer `docker image "
                                                    f"inspect {want}` within {DOCKER_BOUND_S:g} s")
    except OSError as exc:
        return _answer(python, sha, command, error=f"docker could not be started: {exc}")
    if said.returncode != 0:
        said_text = _text(said.stderr) + _text(said.stdout)
        if "No such image" in said_text or "no such image" in said_text:
            return _answer(python, sha, command, error=(
                f"the test image {want} is not built: `scripts/nmas-harness test --python "
                f"{python} --app <folder>` builds it"))
        return _answer(python, sha, command, error=_docker_error(said, f"inspect {want}"))

    try:
        started = time.monotonic()
        said = runner(command, timeout_s)
        seconds = round(time.monotonic() - started, 2)
    except subprocess.TimeoutExpired as exc:
        partial = _text(exc.stdout) + _text(exc.stderr)
        try:
            killed = runner(["docker", "kill", name], DOCKER_BOUND_S)
            how = ("killed" if killed.returncode == 0 else
                   f"not killed: `docker kill {name}` exited {killed.returncode}, "
                   f"{_mask(_text(killed.stderr).strip())[-300:]}")
        except (OSError, subprocess.TimeoutExpired) as kill_exc:
            how = f"not killed: `docker kill {name}` raised {kill_exc}"
        return _answer(python, sha, command, output=_mask(partial)[-OUTPUT_TAIL:], error=(
            f"the test run passed its bound of {timeout_s:g} s: container {name} {how}"))
    except FileNotFoundError:
        return _answer(python, sha, command, error="docker is not installed here (no `docker` "
                                                    "on PATH), so the app's tests cannot run")
    except OSError as exc:
        return _answer(python, sha, command, error=f"docker could not be started: {exc}")

    stdout, stderr = _text(said.stdout), _text(said.stderr)
    masked = _mask(stdout + (("\n" + stderr) if stderr.strip() else ""))
    output = masked[-OUTPUT_TAIL:]
    if said.returncode in (125, 126, 127):
        return _answer(python, sha, command, output=output,
                       error=_docker_error(said, f"run the container of {want}"))
    seen = _HEADER.search(stdout)
    python_seen = seen.group(1) if seen else ""
    counts = parse_counts(stdout)
    after, why = _hash(folder)
    fields = {"output": output, "python_seen": python_seen, "seconds": seconds}
    if counts is not None:
        fields.update(passed=counts["passed"], failed=counts["failed"],
                      errors=counts["errors"], skipped=counts["skipped"])
    if why or after != sha:
        error = why or (f"the folder's content hash moved during the run: {sha} before, "
                        f"{after} after, so what passed is not what is pinned")
    elif python_seen != python:
        error = (f"pytest reported Python {python_seen or 'nothing'} (its header), the "
                 f"network's controller Python is {python}")
    elif counts is None:
        error = (f"pytest's summary line did not parse (pytest exited {said.returncode}), "
                 "so its counts are unknown")
    elif counts["passed"] + counts["failed"] + counts["errors"] == 0:
        error = (f"no test ran (pytest exited {said.returncode}): collecting nothing is not "
                 "a pass")
    elif counts["skipped"] or counts["other"]:
        kinds = dict(counts["other"], **({"skipped": counts["skipped"]}
                                         if counts["skipped"] else {}))
        error = ("; ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
                 + ": a test that did not run as written is not a pass")
    elif said.returncode != 0 or counts["failed"] or counts["errors"]:
        error = (f"pytest exited {said.returncode}: {counts['failed']} failed, "
                 f"{counts['errors']} errors, {counts['passed']} passed")
    else:
        return _answer(python, sha, command, ok=True, **fields)
    return _answer(python, sha, command, error=error, **fields)
