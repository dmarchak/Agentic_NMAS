"""commands.py

Command execution utilities for Cisco IOS devices.

This module provides shared command execution logic to avoid code duplication
across the application. It handles common patterns like adaptive output reading,
prompt detection, and output cleanup.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Commands that consistently cause Netmiko prompt-detection timeouts because
# they are slow (crypto/VPN state lookups, BGP table scans, NHRP queries) or
# produce output that confuses the prompt-regex.  These are sent via
# send_command_timing directly — no failed-prompt-attempt overhead.
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

    Commands in _TIMING_PREFIXES are routed directly to send_command_timing
    to avoid Netmiko prompt-detection failures on slow or output-heavy commands.

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

    # Commands known to cause prompt-detection failures go straight to timing.
    use_timing_direct = any(cmd_lower.startswith(p) for p in _TIMING_PREFIXES)

    # Prefer send_command (prompt-based, handles --More-- automatically)
    # for remaining show/more/dir/ping/traceroute commands.
    use_prompt_based = (
        not use_timing_direct
        and (
            cmd_lower.startswith("show")
            or cmd_lower.startswith("more")
            or cmd_lower.startswith("dir")
            or cmd_lower.startswith("ping")
            or cmd_lower.startswith("traceroute")
            or cmd_lower.startswith("do show")
        )
    )

    # Give inherently slow commands extra time.
    effective_timeout = max(
        read_timeout,
        _SLOW_TIMEOUT if use_timing_direct else read_timeout,
    )

    try:
        if use_prompt_based:
            # send_command waits for the prompt, strips --More-- pages,
            # and never times out on continuously-streaming output.
            output = conn.send_command(
                cmd,
                read_timeout=read_timeout,
                strip_prompt=True,
                strip_command=True,
            )
        else:
            # Timing-based: crypto/bgp/nhrp/ospf/etc. and config commands.
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
