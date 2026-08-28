"""commands.py

Shared SSH command execution logic for Cisco IOS devices.

`run_device_command` is the single entry point used by every part of the app
that needs to send a command to a device.  It routes each command to either
Netmiko's prompt-based `send_command` (which handles --More-- pagination
automatically) or timing-based `send_command_timing` (used for slow or
output-heavy commands such as `show crypto`, `show ip bgp`, etc. that confuse
Netmiko's prompt-detection regex).  Falls back to timing on any prompt-based
timeout, then cleans up duplicate trailing prompts and null bytes in the output.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Commands that have historically caused Netmiko prompt-detection timeouts on
# some platforms (crypto/VPN state lookups, BGP table scans, NHRP queries) or
# produce output that confuses the prompt-regex.  Prompt-based send_command is
# still tried first (it's ~2-3x faster when it works, e.g. on containerlab
# nodes), but with a short read_timeout so a platform where it genuinely
# fails falls back to send_command_timing quickly instead of stalling for
# the full default read_timeout.
_PROMPT_PROBE_TIMEOUT = 10

_TIMING_PREFIXES = (
    "show crypto",
    "show ip nhrp",
    "show ip bgp",
    "show ip ospf",
    "show mpls",
    "show interfaces",
    "show ip interface",
    "show version",
    "show inventory",
    "show environment",
    "show processes",
    "show platform",
)

# Extra read_timeout (seconds) for commands that genuinely take a long time
# to produce output even with timing-based reads.
_SLOW_TIMEOUT = 120


def run_device_command(conn, command: str, adaptive_mode: bool = True,
                       read_timeout: int = 60) -> str:
    """
    Execute a command on a Cisco device and return the output.

    Uses send_command (prompt-based) for show/more/dir commands so that
    paginated output (--More--) is handled automatically and the call returns
    as soon as the device prompt reappears — no fixed timer needed.

    Commands in _TIMING_PREFIXES are still tried prompt-based first (fast on
    platforms where it works), but with a short probe timeout so a platform
    where prompt detection genuinely fails falls back to send_command_timing
    quickly instead of stalling for the full read_timeout.

    For config-mode commands (no recognisable prompt terminator) also uses
    send_command_timing.

    Args:
        conn:         Netmiko connection object
        command:      IOS command to execute
        adaptive_mode: unused — kept for back-compat (always prompt-based now)
        read_timeout: seconds to wait for prompt (default 60)

    Returns:
        Command output as a string with duplicate prompts removed
    """
    logger.debug(f'Executing command: {command}')
    cmd = command.strip()
    cmd_lower = cmd.lower()

    # Commands known on some platforms to cause prompt-detection failures.
    # Still tried prompt-based first (see use_prompt_based below), just with
    # a short leash so a platform where it fails falls back quickly.
    known_slow = any(cmd_lower.startswith(p) for p in _TIMING_PREFIXES)

    # Prefer send_command (prompt-based, handles --More-- automatically) for
    # show/more/dir/ping/traceroute commands — including known_slow ones,
    # since on many platforms (e.g. containerlab nodes) prompt detection
    # works fine and is 2-3x faster than the fixed-delay timing path.
    use_prompt_based = (
        cmd_lower.startswith("show")
        or cmd_lower.startswith("more")
        or cmd_lower.startswith("dir")
        or cmd_lower.startswith("ping")
        or cmd_lower.startswith("traceroute")
        or cmd_lower.startswith("do show")
    )

    # Give inherently slow commands extra time on the timing-based fallback.
    effective_timeout = max(
        read_timeout,
        _SLOW_TIMEOUT if known_slow else read_timeout,
    )
    # known_slow commands get a short prompt-based probe timeout so a
    # platform where prompt detection genuinely fails doesn't stall for the
    # full read_timeout before falling back to timing-based.
    prompt_timeout = _PROMPT_PROBE_TIMEOUT if known_slow else read_timeout

    try:
        if use_prompt_based:
            # send_command waits for the prompt, strips --More-- pages,
            # and never times out on continuously-streaming output.
            output = conn.send_command(
                cmd,
                read_timeout=prompt_timeout,
                strip_prompt=True,
                strip_command=True,
            )
        else:
            # Timing-based: config commands (no recognisable prompt terminator).
            output = conn.send_command_timing(
                cmd,
                read_timeout=effective_timeout,
                strip_prompt=True,
                strip_command=True,
            )
    except Exception as exc:
        # If prompt-based times out (e.g. unusual prompt), retry with timing.
        logger.warning(
            "run_device_command: prompt-based read failed (%s), retrying with timing", exc
        )
        output = conn.send_command_timing(
            cmd,
            read_timeout=effective_timeout,
            strip_prompt=True,
            strip_command=True,
        )

    # Remove leading null/control characters occasionally injected by IOS
    output = output.lstrip("\x00").lstrip("^@")

    # Collapse repeated identical prompts at the end (belt-and-suspenders)
    lines = output.splitlines()
    while (
        len(lines) > 1
        and lines[-1].strip() == lines[-2].strip()
        and lines[-1].strip().endswith(("#", ">"))
    ):
        lines.pop()

    result = "\n".join(lines)
    logger.debug(f'Command completed, output length: {len(result)} chars')
    return result
