"""commands.py

Command execution utilities for Cisco IOS devices.

This module provides shared command execution logic to avoid code duplication
across the application. It handles common patterns like adaptive output reading,
prompt detection, and output cleanup.
"""

import re
import logging

logger = logging.getLogger(__name__)


def run_device_command(conn, command: str, adaptive_mode: bool = True) -> str:
    """
    Execute a command on a Cisco device and return the output.

    Args:
        conn: Netmiko connection object
        command: IOS command to execute
        adaptive_mode: If False, skip adaptive prompt reading (for show/more/dir)

    Returns:
        Command output as a string with duplicate prompts removed

    This function handles:
    - Initial command execution with timing
    - Adaptive reading for commands that need multiple reads
    - Automatic skipping of adaptive mode for show/more/dir commands
    - Cleanup of duplicate prompts at the end of output
    """
    logger.debug(f'Executing command: {command}')

    # Execute the command
    output = conn.send_command_timing(command, read_timeout=120)

    # Remove leading control characters
    if output.startswith("^@"):
        output = output.lstrip("^@")

    # Skip adaptive loop for show/more/dir commands or if explicitly disabled
    skip_adaptive = (
        not adaptive_mode
        or command.strip().lower().startswith("show")
        or command.strip().lower().startswith("more")
        or command.strip().lower().startswith("dir")
    )

    if not skip_adaptive:
        # Adaptive reading: keep reading until we see a prompt
        attempts = 0
        max_attempts = 5

        while not output.endswith(("#", ">")) and attempts < max_attempts:
            more_out = conn.send_command_timing("\n", read_timeout=60)

            # Add new output if it's not just the prompt
            if more_out.strip() and not re.fullmatch(r".*#$", more_out.strip()):
                output += "\n" + more_out

            attempts += 1

            # Break if we found a prompt
            if more_out.endswith(("#", ">")):
                break

    # Collapse repeated identical prompts at the end
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
