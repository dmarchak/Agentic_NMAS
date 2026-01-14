"""
Unit tests for device module functions.

Run with: python -m pytest tests/test_device.py -v
"""

import unittest
from unittest.mock import patch, mock_open, MagicMock
import sys
import os
import tempfile
import csv

# Add parent directory to path to import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.device import load_saved_devices, write_devices_csv


class TestDevice(unittest.TestCase):
    """Test cases for device module functions."""

    def test_load_saved_devices_nonexistent_file(self):
        """Test loading devices from non-existent file returns empty list."""
        result = load_saved_devices("/nonexistent/path/devices.csv")
        self.assertEqual(result, [])

    def test_write_devices_csv(self):
        """Test writing devices to CSV file."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            temp_file = f.name

        try:
            devices = [
                {
                    "hostname": "Router1",
                    "device_type": "cisco_ios",
                    "ip": "192.168.1.1",
                    "username": "admin",
                    "password": "encrypted_pass",
                    "secret": "encrypted_secret"
                },
                {
                    "hostname": "Switch1",
                    "device_type": "cisco_ios",
                    "ip": "192.168.1.2",
                    "username": "admin",
                    "password": "encrypted_pass2",
                    "secret": "encrypted_secret2"
                }
            ]

            # Write devices
            write_devices_csv(devices, temp_file)

            # Read back and verify
            with open(temp_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                loaded_devices = list(reader)

            self.assertEqual(len(loaded_devices), 2)
            self.assertEqual(loaded_devices[0]['hostname'], 'Router1')
            self.assertEqual(loaded_devices[1]['hostname'], 'Switch1')
            self.assertEqual(loaded_devices[0]['ip'], '192.168.1.1')
            self.assertEqual(loaded_devices[1]['ip'], '192.168.1.2')

        finally:
            # Cleanup
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_load_saved_devices_from_csv(self):
        """Test loading devices from a CSV file."""
        # Create a temporary CSV file with test data
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['hostname', 'device_type', 'ip', 'username', 'password', 'secret'])
            writer.writeheader()
            writer.writerow({
                'hostname': 'TestRouter',
                'device_type': 'cisco_ios',
                'ip': '10.0.0.1',
                'username': 'test',
                'password': 'encrypted',
                'secret': 'encrypted'
            })
            temp_file = f.name

        try:
            # Load devices
            devices = load_saved_devices(temp_file)

            # Verify
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]['hostname'], 'TestRouter')
            self.assertEqual(devices[0]['ip'], '10.0.0.1')
            self.assertEqual(devices[0]['username'], 'test')

        finally:
            # Cleanup
            if os.path.exists(temp_file):
                os.remove(temp_file)


if __name__ == '__main__':
    unittest.main()
