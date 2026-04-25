"""bulk_ops.py

Multi-device parallel command and file-transfer operations.

`BulkOperationManager` fans a single operation out to all selected devices
using a thread-pool worker queue.  Supported modes: enable-mode commands,
config-mode command sets, TFTP upload/download, config download to TFTP,
flash file deletion, and static-route removal.  Each operation is tracked
by a unique ID so the UI can poll for per-device progress and results.
A module-level singleton `bulk_manager` is imported by app.py.
"""

import re
import threading
from typing import List, Dict, Callable
from queue import Queue
import time

# Commands that show interactive confirmation/filename prompts.
# Each entry: (regex, number of extra "\n" replies to send after the command)
# The initial send_command_timing captures the prompt; each "\n" confirms it.
#
# "copy X startup-config" always asks "Destination filename [startup-config]?"
# regardless of source (flash:, nvram:, tftp:, running-config, etc.).
# One Enter accepts the bracketed default.
_INTERACTIVE_COMMANDS = [
    # copy <any-source> startup-config / start
    # Covers: copy run start, copy flash:X start, copy nvram:X startup-config, …
    (re.compile(r'^copy\s+\S+\s+start(up(-config)?)?$', re.I), 1),
    # write memory / wr mem / wr  (no confirmation prompt — just collects output)
    (re.compile(r'^(write\s+mem(ory)?|wr(\s+mem(ory)?)?)$', re.I), 0),
    # write erase / wr erase  — "Continue? [confirm]" prompt requires one Enter
    (re.compile(r'^(write\s+erase|wr\s+erase)$', re.I), 1),
    # erase startup-config / erase nvram: / erase flash: / erase disk:
    (re.compile(r'^erase\s+(startup-config|nvram:|flash:|disk:)', re.I), 1),
    # format flash: / format nvram: / format disk:
    (re.compile(r'^format\s+\S+', re.I), 1),
    # reload (without "in" / "at" — interactive confirm)
    (re.compile(r'^reload\b(?!\s+in\b|\s+at\b)', re.I), 1),
    # crypto key zeroize rsa
    (re.compile(r'^crypto\s+key\s+zeroize', re.I), 1),
]


# Commands that write/erase flash take longer — use a higher read_timeout.
_SLOW_INTERACTIVE = re.compile(
    r'^(write\s+erase|wr\s+erase|erase\s+|format\s+)', re.I
)


def _run_enable_command(conn, command: str) -> str:
    """
    Run a single enable-mode command, automatically answering interactive
    prompts (write erase, erase nvram, reload, crypto key zeroize, …) with Enter.
    Falls back to run_device_command for non-interactive commands.
    """
    from modules.commands import run_device_command
    cmd = command.strip()
    for pattern, extra_enters in _INTERACTIVE_COMMANDS:
        if pattern.match(cmd):
            # Flash/NVRAM erase operations can take 10-30 s; use a longer timeout.
            timeout = 60 if _SLOW_INTERACTIVE.match(cmd) else 30
            output = conn.send_command_timing(cmd, delay_factor=2, read_timeout=timeout)
            for _ in range(extra_enters):
                output += conn.send_command_timing("\n", delay_factor=2, read_timeout=timeout)
            # Final read to collect any completion banner (e.g. "[OK]")
            output += conn.send_command_timing("", delay_factor=3, read_timeout=timeout)
            return output
    return run_device_command(conn, command)


class BulkOperationManager:
    """Manages execution of operations on multiple devices."""

    def __init__(self):
        self.active_operations = {}
        self.lock = threading.Lock()

    def execute_bulk_command(
        self,
        devices: List[Dict],
        command: str,
        connection_factory: Callable,
        connections_pool: Dict,
        pool_lock: threading.Lock,
        max_workers: int = 5,
        command_mode: str = "enable"
    ) -> str:
        """
        Execute a command on multiple devices in parallel.

        Args:
            devices: List of device dictionaries
            command: Command to execute
            connection_factory: Function to get device connection
            connections_pool: Shared connections pool
            pool_lock: Lock for connections pool
            max_workers: Maximum parallel workers
            command_mode: "enable" for exec commands, "config" for configuration commands

        Returns:
            str: Operation ID for tracking progress
        """
        operation_id = f"bulk_{int(time.time() * 1000)}"

        # Initialize operation tracking
        with self.lock:
            self.active_operations[operation_id] = {
                "status": "running",
                "total": len(devices),
                "completed": 0,
                "failed": 0,
                "results": []
            }

        # Start background thread to execute operation
        thread = threading.Thread(
            target=self._execute_worker,
            args=(operation_id, devices, command, connection_factory,
                  connections_pool, pool_lock, max_workers, command_mode),
            daemon=True
        )
        thread.start()

        return operation_id

    def _execute_worker(
        self,
        operation_id: str,
        devices: List[Dict],
        command: str,
        connection_factory: Callable,
        connections_pool: Dict,
        pool_lock: threading.Lock,
        max_workers: int,
        command_mode: str = "enable"
    ):
        """Background worker to execute commands on devices."""
        # Create work queue
        work_queue = Queue()
        for device in devices:
            work_queue.put(device)

        # Worker thread function
        def worker():
            while not work_queue.empty():
                try:
                    device = work_queue.get(timeout=1)
                except:
                    break

                result = {
                    "ip": device["ip"],
                    "hostname": device["hostname"],
                    "status": "pending",
                    "output": "",
                    "error": None
                }

                try:
                    # Get connection
                    conn = connection_factory(device, connections_pool, pool_lock)

                    # Execute command based on mode
                    if command_mode == "config":
                        # Parse commands - split by semicolon for multiple commands
                        config_commands = [cmd.strip() for cmd in command.split(';') if cmd.strip()]
                        output = conn.send_config_set(
                            config_commands, read_timeout=60, cmd_verify=False
                        )
                    elif command_mode == "tftp_upload":
                        # TFTP upload - handle interactive prompts
                        # command format: "tftp_server|filename"
                        parts = command.split("|")
                        tftp_server = parts[0]
                        filename = parts[1]
                        output = self._execute_tftp_upload(conn, tftp_server, filename)
                    elif command_mode == "tftp_download":
                        # TFTP download - handle interactive prompts
                        # command format: "tftp_server|filename|dest_filename"
                        parts = command.split("|")
                        tftp_server = parts[0]
                        filename = parts[1]
                        dest_filename = parts[2] if len(parts) > 2 else filename
                        output = self._execute_tftp_download(conn, tftp_server, filename, dest_filename, device)
                    elif command_mode == "config_download":
                        # Config download - download startup or running config
                        # command format: "tftp_server|config_type"
                        parts = command.split("|")
                        tftp_server = parts[0]
                        config_type = parts[1]
                        output = self._execute_config_download(conn, tftp_server, config_type, device)
                    elif command_mode == "delete_file":
                        # Delete file from flash:
                        # command is just the filename
                        output = self._execute_delete_file(conn, command)
                    elif command_mode == "remove_static_routes":
                        # Remove all non-VRF static routes
                        output = self._execute_remove_static_routes(conn)
                    else:
                        # Enable mode - handles interactive prompts automatically
                        output = _run_enable_command(conn, command)

                    result["status"] = "success"
                    result["output"] = output

                    with self.lock:
                        self.active_operations[operation_id]["completed"] += 1

                except Exception as e:
                    result["status"] = "failed"
                    result["error"] = str(e)

                    with self.lock:
                        self.active_operations[operation_id]["failed"] += 1

                finally:
                    # Add result
                    with self.lock:
                        self.active_operations[operation_id]["results"].append(result)

                work_queue.task_done()

        # Start worker threads
        threads = []
        for _ in range(min(max_workers, len(devices))):
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            threads.append(t)

        # Wait for all workers to complete
        for t in threads:
            t.join()

        # Mark operation as complete
        with self.lock:
            self.active_operations[operation_id]["status"] = "completed"

    def _execute_tftp_upload(self, conn, tftp_server: str, filename: str) -> str:
        """Execute TFTP upload with interactive prompt handling."""
        # Match the working device page logic exactly
        output = conn.send_command_timing("copy tftp: flash:")
        output += conn.send_command_timing(tftp_server)
        output += conn.send_command_timing(filename)
        output += conn.send_command_timing(filename)
        output += conn.send_command_timing("\n")
        return output

    def _execute_tftp_download(self, conn, tftp_server: str, filename: str, dest_filename: str, device: Dict) -> str:
        """Execute TFTP download with interactive prompt handling."""
        # Use device hostname to create unique filename on TFTP server
        hostname = device.get("hostname", device.get("ip", "device"))
        remote_filename = f"{hostname}_{dest_filename}"

        output = conn.send_command_timing("copy flash: tftp:")
        output += conn.send_command_timing(filename)
        output += conn.send_command_timing(tftp_server)
        output += conn.send_command_timing(remote_filename)
        output += conn.send_command_timing("\n")
        return output

    def _execute_config_download(self, conn, tftp_server: str, config_type: str, device: Dict) -> str:
        """Execute config download (startup or running) to TFTP server."""
        hostname = device.get("hostname", device.get("ip", "device"))

        if config_type == "running":
            # copy running-config tftp:
            remote_filename = f"{hostname}_running-config"
            output = conn.send_command_timing("copy running-config tftp:", delay_factor=2)
        else:
            # copy startup-config tftp:
            remote_filename = f"{hostname}_startup-config"
            output = conn.send_command_timing("copy startup-config tftp:", delay_factor=2)

        # Respond to "Address or name of remote host" prompt
        output += conn.send_command_timing(tftp_server, delay_factor=2)
        # Respond to "Destination filename" prompt
        output += conn.send_command_timing(remote_filename, delay_factor=2)
        # Confirm any additional prompts
        output += conn.send_command_timing("\n", delay_factor=2)
        return output

    def _execute_delete_file(self, conn, filename: str) -> str:
        """Execute delete file from flash: with confirmation handling."""
        # delete flash:filename
        output = conn.send_command_timing(f"delete flash:{filename}")
        # Confirm the filename prompt
        output += conn.send_command_timing("\n")
        # Confirm the delete prompt [confirm]
        output += conn.send_command_timing("\n")
        return output

    def _execute_remove_static_routes(self, conn) -> str:
        """Remove all static routes from device config, preserving VRF routes."""
        # Get running config to find static routes
        running_config = conn.send_command("show running-config | include ^ip route")

        # Parse out lines that start with "ip route" but do NOT contain "vrf"
        routes_to_remove = []
        for line in running_config.splitlines():
            stripped = line.strip()
            if stripped.startswith("ip route") and "vrf" not in stripped:
                routes_to_remove.append(stripped)

        if not routes_to_remove:
            return "No static routes found to remove (VRF routes preserved)."

        # Build negation commands
        negate_commands = [f"no {route}" for route in routes_to_remove]

        # Send config commands to remove the routes
        output = conn.send_config_set(negate_commands, read_timeout=60, cmd_verify=False)
        output += f"\n\nRemoved {len(routes_to_remove)} static route(s)."
        return output

    def get_operation_status(self, operation_id: str) -> Dict:
        """
        Get the status of a bulk operation.

        Args:
            operation_id: Operation ID

        Returns:
            dict: Operation status and results
        """
        with self.lock:
            return self.active_operations.get(operation_id, {
                "status": "not_found",
                "total": 0,
                "completed": 0,
                "failed": 0,
                "results": []
            }).copy()

    def clear_operation(self, operation_id: str):
        """Remove operation from tracking."""
        with self.lock:
            self.active_operations.pop(operation_id, None)


# Global instance
bulk_manager = BulkOperationManager()
