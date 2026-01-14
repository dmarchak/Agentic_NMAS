"""
Unit tests for utility functions.

Run with: python -m pytest tests/test_utils.py -v
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.utils import make_device_filename


class TestUtils(unittest.TestCase):
    """Test cases for utility functions."""

    @patch('modules.utils.time.strftime')
    def test_make_device_filename(self, mock_strftime):
        """Test device filename generation."""
        # Mock the timestamp
        mock_strftime.return_value = "13204513JAN26"

        result = make_device_filename("Router1")

        # Verify format
        self.assertEqual(result, "Router1_13204513JAN26.txt")
        # Verify strftime was called with correct format
        mock_strftime.assert_called_once_with("%d%H%M%b%y")

    @patch('modules.utils.time.strftime')
    def test_make_device_filename_special_chars(self, mock_strftime):
        """Test filename with hostname containing special characters."""
        mock_strftime.return_value = "01120000JAN26"

        result = make_device_filename("SW-Core-01")

        # Should include the special characters
        self.assertEqual(result, "SW-Core-01_01120000JAN26.txt")

    @patch('modules.utils.time.strftime')
    def test_make_device_filename_empty_hostname(self, mock_strftime):
        """Test filename generation with empty hostname."""
        mock_strftime.return_value = "15143000DEC25"

        result = make_device_filename("")

        # Should still work with empty hostname
        self.assertEqual(result, "_15143000DEC25.txt")


if __name__ == '__main__':
    unittest.main()
