"""commands.py

Shared SSH command execution logic for Cisco IOS devices.

`run_device_command` is the single entry point used by every part of the app
that needs to send a command to a device. A read (show, more, dir, ping,
traceroute) goes through Netmiko's prompt-based `send_command`, which handles
--More-- pagination; anything else through `send_command_timing`. Each is sent
ONCE: a read that does not finish, or whose reply holds an echoed command or
the session's own prompt, raises, and its session is never read again (C272,
`config_read.SPENT_ATTR`). It used to fall back to a timing read on the same
session, which returned two outputs stitched into one (C271).
"""

import re
import logging

logger = logging.getLogger(__name__)

# The 10 s prompt "probe" and its list of slow commands are gone (C272,
# 2026-10-01): a probe that ran out re-sent the command on the same session,
# which still carried the first command's output. Every read now waits once,
# with the config read's measured bound, and is never re-sent.

#: A whole configuration: read once, never retried on its session, and judged
#: before it is returned (modules/config_read.py).
CONFIG_READS = ("show running-config", "show startup-config")


def _usable_prompt(conn) -> str:
    """The session's base prompt, made usable before a read (C272).

    After a push the prompt read as `^@` (NUL bytes) on the deploy's own
    session, so a prompt-based read could never see it end (2026-09-30
    23:54, 2026-10-01 01:14). It is read again once (`set_base_prompt`, one
    newline, before the command is sent); still unusable, the read is
    refused rather than waited out. A session that names no prompt (a test's
    fake) is read as it is."""
    from modules import config_read

    prompt = getattr(conn, "base_prompt", None)
    if prompt is None or config_read.USABLE_PROMPT.fullmatch(prompt or ""):
        return prompt or ""
    try:
        prompt = conn.set_base_prompt()
    except Exception as exc:                              # noqa: BLE001
        raise config_read.UnreliableRead("the device", [
            f"the session's prompt reads as {getattr(conn, 'base_prompt', '')!r} and could "
            f"not be read again ({type(exc).__name__}: {exc})"]) from None
    if not config_read.USABLE_PROMPT.fullmatch(prompt or ""):
        raise config_read.UnreliableRead("the device", [
            f"the session's prompt reads as {prompt!r} even after reading it again"])
    return prompt


def run_device_command(conn, command: str, adaptive_mode: bool = True,
                       read_timeout: int = 60) -> str:
    """
    Execute a command on a Cisco device and return the output.

    Uses send_command (prompt-based) for show/more/dir commands so that
    paginated output (--More--) is handled automatically and the call returns
    as soon as the device prompt reappears — no fixed timer needed.

    A show command is sent ONCE and waited for (the config read's bound,
    120 s by default), never re-sent on its session, and its reply refused
    (`UnreliableRead`) when it holds an echoed command or the session's own
    prompt; a session whose prompt reads as NUL bytes is asked for it again
    first, and refused if it still does (C272). A configuration read is also
    judged as one configuration (C271).

    For config-mode commands (no recognisable prompt terminator) uses
    send_command_timing, sent once.

    Args:
        conn:         Netmiko connection object
        command:      IOS command to execute
        adaptive_mode: unused — kept for back-compat (always prompt-based now)
        read_timeout: seconds to wait for prompt (default 60)

    Returns:
        Command output as a string with duplicate prompts removed
    """
    from modules import config_read

    logger.debug(f'Executing command: {command}')
    if config_read.spent(conn):
        # Never a second command on a channel that may still carry the
        # first's output (C272): the caller opens a new session.
        raise config_read.UnreliableRead("the device", [
            f"this session is not read again: {config_read.spent(conn)}"])
    try:
        return _run(conn, command, read_timeout)
    except Exception as exc:
        config_read.spend(conn, f"{command.strip()!r} on it ended in "
                                f"{type(exc).__name__}: {str(exc)[:200]}")
        raise


def _run(conn, command: str, read_timeout: int) -> str:
    """One send of *command* on *conn* (`run_device_command`'s body)."""
    cmd = command.strip()
    cmd_lower = cmd.lower()

    if cmd_lower in CONFIG_READS:
        # A configuration is never read twice on one session (the operator,
        # 2026-10-01). The fallback below re-sends the command after a
        # timeout; for r2's capture the first command's output was still
        # arriving, so the retry returned the config, the prompt and echoed
        # command, and the config again, and it was nearly recorded. ONE read,
        # waited for with the config bound, then judged on its evidence (a
        # second `end`, a prompt, an echoed command): a stitched text raises
        # `UnreliableRead`, whoever the caller (modules/config_read.py).
        from modules import config_read

        _usable_prompt(conn)
        output = conn.send_command(cmd, read_timeout=max(read_timeout, config_read.read_timeout()),
                                   strip_prompt=True, strip_command=True)
        return config_read.check((output or "").lstrip("\x00"), "", strict=False)

    use_prompt_based = (
        cmd_lower.startswith("show")
        or cmd_lower.startswith("more")
        or cmd_lower.startswith("dir")
        or cmd_lower.startswith("ping")
        or cmd_lower.startswith("traceroute")
        or cmd_lower.startswith("do show")
    )

    if use_prompt_based:
        # ONE read, never resent on its session (C272, the operator, 2026-10-01;
        # C271's rule for every command). It used to probe 10 s, then re-send
        # the command with `send_command_timing` on the SAME session, which
        # still carried the first command's output: a slow device answered
        # two outputs read as one, and verify's own reads (`show ip ospf`,
        # `show ip bgp`, `show interfaces`) took that path. The bound is the
        # config read's, measured: `write memory` leaves an emulated device
        # slow for tens of seconds, and verify reads right after a push and a
        # save. A read that does not finish raises; a reply that holds an
        # echoed command or the session's own prompt raises `UnreliableRead`.
        from modules import config_read

        prompt = _usable_prompt(conn)
        output = conn.send_command(
            cmd,
            read_timeout=max(read_timeout, config_read.read_timeout()),
            strip_prompt=True,
            strip_command=True,
        )
        output = (output or "").lstrip("\x00")
        bad = config_read.output_problems(output, prompt)
        if bad:
            logger.error("run_device_command: %r: %s: %s", cmd, config_read.UNRELIABLE,
                         "; ".join(bad))
            raise config_read.UnreliableRead(prompt or "the device", bad)
    else:
        # Timing-based: config commands (no recognisable prompt terminator).
        # Sent once; nothing here re-sends it.
        output = conn.send_command_timing(
            cmd,
            read_timeout=read_timeout,
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
