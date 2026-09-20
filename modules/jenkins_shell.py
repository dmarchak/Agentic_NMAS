"""jenkins_shell.py

One place that knows whether generated Jenkins pipelines use Windows ``bat``
steps or POSIX ``sh`` steps.

Every pipeline generator in this codebase hardcoded ``bat`` plus Windows-only
spellings (``2>NUL``, ``modules\\check_runner.py``) because development is on
Windows. The deployment target is Ubuntu, where those steps fail. The step
shell is now a setting, and these helpers supply the matching null device and
path separator so a pipeline is internally consistent.

The default stays ``bat``, so an existing Jenkins job regenerates byte for byte
identically until the operator changes the setting.
"""

import logging

log = logging.getLogger(__name__)

_VALID = ("bat", "sh")


def step_shell() -> str:
    """Return the configured Jenkins step keyword: ``bat`` or ``sh``."""
    try:
        from modules.settings_schema import get_setting
        value = (get_setting("jenkins_step_shell", "bat") or "bat").strip().lower()
    except Exception:                         # noqa: BLE001 - settings must never break generation
        return "bat"
    return value if value in _VALID else "bat"


def is_posix() -> bool:
    return step_shell() == "sh"


def null_device() -> str:
    """Shell spelling of the null device for the configured step shell."""
    return "/dev/null" if is_posix() else "NUL"


def script_path(path: str) -> str:
    """Render a repo-relative script path for the configured step shell.

    Windows ``bat`` steps in a Groovy single-quoted string need the backslash
    doubled; POSIX ``sh`` uses forward slashes as-is.
    """
    posix = path.replace("\\", "/")
    return posix if is_posix() else posix.replace("/", "\\\\")


def install_deps_step(packages: str = "netmiko") -> str:
    """The 'Install deps' step body, matching the configured shell."""
    return (f"{step_shell()} 'pip install {packages} --quiet 2>{null_device()} "
            f"|| echo {packages} already installed'")


def python_step(script: str, args: str = "") -> str:
    """A step that runs a repo script with the configured shell."""
    tail = f" {args}" if args else ""
    return f"{step_shell()} 'python {script_path(script)}{tail}'"
