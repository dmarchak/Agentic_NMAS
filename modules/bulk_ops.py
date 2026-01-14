"""
Bulk Operations Module

Execute commands on multiple devices simultaneously with progress tracking.
"""

import threading
from typing import List, Dict, Callable
from queue import Queue
import time


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
        max_workers: int = 5
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
                  connections_pool, pool_lock, max_workers),
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
        max_workers: int
    ):
        """Background worker to execute commands on devices."""
        from modules.commands import run_device_command

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

                    # Execute command
                    output = run_device_command(conn, command)

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
