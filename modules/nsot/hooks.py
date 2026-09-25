"""nsot/hooks.py

Post-commit callbacks: S3 archive, git push, README regeneration.

Hooks run on a **background thread with short timeouts**. They never hold the
repo lock and never delay the commit response. Git is the system of record; an
archive or push failure is logged and surfaced on the integration badge, but it
can never block or roll back a commit that has already happened.
"""

import logging
import threading

log = logging.getLogger(__name__)

_hooks: list = []
_lock = threading.Lock()

DEFAULT_HOOK_TIMEOUT = 30


def register(name: str, func, timeout: int = DEFAULT_HOOK_TIMEOUT) -> None:
    """Register a post-commit callback ``func(context) -> dict``."""
    with _lock:
        if any(h["name"] == name for h in _hooks):
            return
        _hooks.append({"name": name, "func": func, "timeout": timeout})
    log.debug("hooks: registered post-commit hook '%s'", name)


def unregister(name: str) -> None:
    with _lock:
        _hooks[:] = [h for h in _hooks if h["name"] != name]


def registered() -> list:
    with _lock:
        return [h["name"] for h in _hooks]


def ensure_default_hooks() -> list:
    """Register push and archive if this process has not already.

    **Registration follows the repo module being used, not the app starting.**
    It used to live in `app.py`, which meant a commit made by any process
    without Flask -- a CLI repair script, a cron job, a test harness -- found
    an empty registry and pushed nothing. Measured: a fresh interpreter
    reports `[]` until `app` is imported.

    The 1.4 repair commit went in that way and stayed local while the Remote
    card accurately reported the last thing that HAD been published. The card
    was right; the commit never reached the hook.

    Importing lazily, because `archive` imports `remote`, which imports
    settings and credentials -- a module-level import here would make every
    consumer of `hooks` pull that chain in.
    """
    try:
        from modules.nsot.archive import register_default_hooks

        register_default_hooks()
    except Exception as exc:                  # noqa: BLE001
        # Deliberately not swallowed: a registry that cannot be filled is the
        # silent-failure shape this function exists to remove.
        log.error("hooks: could not register default post-commit hooks: %s",
                  exc)
    return registered()


def _report_empty_registry(context: dict) -> None:
    """A commit that could have been published and was not must say so.

    Reached only when registration itself failed, since
    :func:`ensure_default_hooks` runs first. Silence here would recreate the
    exact defect: a repository with a configured remote, a commit made, and
    nothing anywhere recording that it never went out.
    """
    list_name = context.get("list_name") or ""
    if not list_name:
        return
    try:
        from modules.nsot import remote as _remote

        if not _remote.load_remote(list_name):
            return                             # no remote: nothing to publish
        reason = ("no post-commit hooks are registered, so commit "
                  f"{(context.get('sha') or '')[:12]} was NOT pushed. The "
                  "repository has a remote configured; this is a defect, not "
                  "a configuration choice.")
        log.error("hooks: %s", reason)
        _remote.record_push_failure(list_name, actor="post-commit",
                                    reason=reason)
    except Exception as exc:                  # noqa: BLE001
        log.error("hooks: empty registry and could not report it: %s", exc)


def run_post_commit(context: dict) -> None:
    """Fire every hook on a background thread. Returns immediately."""
    ensure_default_hooks()
    with _lock:
        hooks = list(_hooks)
    if not hooks:
        _report_empty_registry(context)
        return

    def _runner():
        for hook in hooks:
            result = {"ok": False, "error": "did not run"}
            done = threading.Event()

            def _call(h=hook):
                nonlocal result
                try:
                    result = h["func"](context) or {"ok": True}
                except Exception as exc:      # noqa: BLE001
                    result = {"ok": False, "error": str(exc)}
                finally:
                    done.set()

            worker = threading.Thread(target=_call, daemon=True,
                                      name=f"nsot-hook-{hook['name']}")
            worker.start()
            if not done.wait(timeout=hook["timeout"]):
                # The thread is daemonised; it cannot hold up the process.
                log.warning("hooks: '%s' exceeded %ss — continuing",
                            hook["name"], hook["timeout"])
                continue
            if result.get("ok"):
                log.info("hooks: '%s' ok%s", hook["name"],
                         f" — {result['message']}" if result.get("message") else "")
            else:
                log.warning("hooks: '%s' failed: %s", hook["name"],
                            result.get("error", "unknown"))

    runner = threading.Thread(target=_runner, daemon=True,
                              name="nsot-post-commit")
    with _lock:
        _pending.append(runner)
    _ensure_exit_join()
    runner.start()


# A SHORT-LIVED PROCESS MUST NOT EXIT UNDER ITS OWN PUSH.
#
# Hooks run on daemon threads so they never block a commit, and a daemon
# thread dies with its process. Measured 2026-09-25: `nmas-retire` committed
# r5's retirement (3592113) and exited, and the push hook died with it: the
# remote stayed one commit behind and nothing recorded a failure. The same
# shape as the 1.4 repair commit, from a cause the registry fix did not reach.
# So a process that fired hooks JOINS them at exit, bounded, and says on
# stderr which did not finish -- never silently.
_pending: list = []
_EXIT_JOIN_SECONDS = 90
_exit_join_registered = False


def _ensure_exit_join() -> None:
    global _exit_join_registered
    with _lock:
        if _exit_join_registered:
            return
        _exit_join_registered = True
    import atexit
    atexit.register(wait_for_hooks)


def wait_for_hooks(timeout: float = _EXIT_JOIN_SECONDS) -> list:
    """Join every hook runner this process started. Returns the names of any
    still running when *timeout* ran out, after saying so on stderr."""
    import sys
    import time

    deadline = time.monotonic() + timeout
    with _lock:
        runners = list(_pending)
    for runner in runners:
        runner.join(max(0.0, deadline - time.monotonic()))
    unfinished = [r.name for r in runners if r.is_alive()]
    if unfinished:
        msg = (f"nsot: post-commit hooks still running at exit after "
               f"{timeout:.0f}s ({', '.join(unfinished)}) -- the commit is "
               "local and may not have been pushed")
        log.error(msg)
        print(msg, file=sys.stderr)
    return unfinished
