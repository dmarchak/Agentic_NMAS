import csv
import os
import logging
from typing import Any
from cryptography.fernet import Fernet
from modules.config import KEY_FILE, DEVICES_FILE

logger = logging.getLogger(__name__)

# Fernet instance is created once at module import time and used to
# encrypt/decrypt credential fields stored in the CSV. 


def load_key() -> bytes:
    #Load or generate Fernet key stored at `KEY_FILE`.

    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
    with open(KEY_FILE, "rb") as f:
        return f.read()


fernet = Fernet(load_key())


def decrypt_field(value: str) -> str:
    #Decrypt a Fernet-encrypted CSV field value.
    return fernet.decrypt(value.encode()).decode()


def load_saved_devices(filename: str | None = None) -> list[dict[str, Any]]:
    #Load devices from CSV and return a list of dicts.
    if not filename:
        filename = DEVICES_FILE
    logger.debug("Loading devices from: %s", filename)
    if not os.path.isabs(filename):
        filename = os.path.abspath(filename)
    if not os.path.exists(filename):
        logger.debug("Devices file not found: %s", filename)
        return []
    with open(filename, mode="r", newline="") as f:
        return list(csv.DictReader(f))


def save_device(device: dict, filename: str | None = None) -> None:
    #Add or update a device in the devices CSV (encrypting creds).
    if not filename:
        filename = DEVICES_FILE
    fieldnames = ["hostname", "device_type", "ip", "username", "password", "secret"]
    encrypted = device.copy()
    encrypted["password"] = fernet.encrypt(device["password"].encode()).decode()
    encrypted["secret"] = fernet.encrypt(device["secret"].encode()).decode()

    devices: list[dict] = []
    if os.path.exists(filename):
        with open(filename, mode="r", newline="") as f:
            devices = [row for row in csv.DictReader(f)]
            # replace if exists
            devices = [
                encrypted if row.get("ip") == device.get("ip") else row
                for row in devices
            ]
    if not any(row.get("ip") == device.get("ip") for row in devices):
        devices.append(encrypted)

    with open(filename, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(devices)


def delete_device(ip: str, filename: str | None = None) -> None:
    #Delete a device by IP from the CSV file.
    if not filename:
        filename = DEVICES_FILE
    devices = [d for d in load_saved_devices(filename) if d.get("ip") != ip]
    fieldnames = ["hostname", "device_type", "ip", "username", "password", "secret"]
    with open(filename, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(devices)


def get_device_context(dev: dict, filesystem: str | None = None):
    #Use a temporary connection to build filesystems and file list for device.

    def execute(conn):
        # Filesystems
        fs_output = conn.send_command_timing("dir ?")
        filesystems: list[str] = []
        for line in fs_output.splitlines():
            line = line.strip()
            parts = line.split()
            if parts and parts[0].endswith(":"):
                filesystems.append(parts[0])

        # Default to first filesystem
        fs = filesystem or (filesystems[0] if filesystems else "")

        # Files in selected filesystem
        file_list: list[str] = []
        if fs:
            dir_output = conn.send_command(f"dir {fs}")
            if "No files" not in dir_output and "Error opening" not in dir_output:
                for line in dir_output.splitlines():
                    line = line.strip()
                    if (
                        not line
                        or line.lower().startswith("directory")
                        or "bytes" in line.lower()
                        or "(" in line
                        or ")" in line
                        or line.endswith(":")
                    ):
                        continue
                    parts = line.split()
                    if len(parts) >= 1 and parts[-1] and not parts[-1].endswith(":"):
                        file_list.append(parts[-1])

        return filesystems, file_list, fs

    # Import here to avoid circular imports: modules.connection imports
    # modules.device in other places, load `with_temp_connection`
    # only when needed at runtime.
    from modules.connection import with_temp_connection

    # Run the small `execute` closure using a fresh temporary Netmiko
    # connection provided by `with_temp_connection`. This keeps the
    # device module synchronous and simple to test while delegating
    # connection lifecycle management to the connection module.
    return with_temp_connection(dev, execute)


def write_devices_csv(devices: list[dict], filename: str | None = None) -> None:
    #Write a list of device dicts to the CSV file.
    if not filename:
        filename = DEVICES_FILE
    fieldnames = ["hostname", "device_type", "ip", "username", "password", "secret"]
    with open(filename, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(devices)
