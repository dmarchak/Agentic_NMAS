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


def run_post_commit(context: dict) -> None:
    """Fire every hook on a background thread. Returns immediately."""
    with _lock:
        hooks = list(_hooks)
    if not hooks:
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

    threading.Thread(target=_runner, daemon=True, name="nsot-post-commit").start()
