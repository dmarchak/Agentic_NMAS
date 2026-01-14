"""
Unit tests for quick actions module.

Run with: python -m pytest tests/test_quick_actions.py -v
"""

import unittest
import sys
import os
import tempfile
import json

# Add parent directory to path to import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.quick_actions import load_quick_actions, save_quick_actions


class TestQuickActions(unittest.TestCase):
    """Test cases for quick actions functions."""

    def test_load_quick_actions_nonexistent_file(self):
        """Test loading from non-existent file returns empty dict."""
        # Mock the QUICK_ACTIONS_FILE to a non-existent path
        with unittest.mock.patch('modules.quick_actions.QUICK_ACTIONS_FILE', '/nonexistent/actions.json'):
            result = load_quick_actions()
            self.assertEqual(result, {})

    def test_save_and_load_quick_actions(self):
        """Test saving and loading quick actions."""
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_file = f.name

        try:
            test_actions = {
                "global": [
                    {"command": "show version", "label": "Version"},
                    {"command": "show ip interface brief", "label": "IP Brief"}
                ]
            }

            # Mock the file path and save
            with unittest.mock.patch('modules.quick_actions.QUICK_ACTIONS_FILE', temp_file):
                save_quick_actions(test_actions)

                # Load and verify
                loaded = load_quick_actions()

            self.assertEqual(loaded, test_actions)
            self.assertEqual(len(loaded["global"]), 2)
            self.assertEqual(loaded["global"][0]["command"], "show version")

        finally:
            # Cleanup
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_save_quick_actions_creates_valid_json(self):
        """Test that saved actions are valid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_file = f.name

        try:
            test_actions = {
                "global": [
                    {"command": "show running-config", "label": "Running Config"}
                ]
            }

            with unittest.mock.patch('modules.quick_actions.QUICK_ACTIONS_FILE', temp_file):
                save_quick_actions(test_actions)

            # Manually read the file and verify it's valid JSON
            with open(temp_file, 'r') as f:
                loaded_json = json.load(f)

            self.assertEqual(loaded_json, test_actions)

        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)


if __name__ == '__main__':
    unittest.main()
