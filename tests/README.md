# Test Suite

This directory contains unit tests for the Network Device Manager application.

## Running Tests

### Run all tests:
```bash
python -m pytest tests/ -v
```

### Run specific test file:
```bash
python -m pytest tests/test_utils.py -v
```

### Run with coverage report:
```bash
python -m pytest tests/ --cov=modules --cov-report=html
```

### Run only unit tests:
```bash
python -m pytest tests/ -m unit -v
```

## Test Files

- `test_utils.py` - Tests for utility functions (filename generation, etc.)
- `test_device.py` - Tests for device management functions
- `test_quick_actions.py` - Tests for quick actions persistence

## Writing New Tests

1. Create a new file starting with `test_`
2. Import unittest and required modules
3. Create test class inheriting from `unittest.TestCase`
4. Write test methods starting with `test_`
5. Use assertions to verify expected behavior

Example:
```python
import unittest

class TestMyFeature(unittest.TestCase):
    def test_my_function(self):
        result = my_function()
        self.assertEqual(result, expected_value)
```

## Test Coverage

Current test coverage focuses on:
- ✅ Utility functions
- ✅ Device CSV operations
- ✅ Quick actions JSON operations
- ⏳ Connection management (requires mocking)
- ⏳ Command execution (requires mocking)

## Future Tests

Planned test additions:
- Mock Netmiko connections for testing SSH operations
- Integration tests with test devices
- WebSocket/SocketIO tests for terminal sessions
- Flask route tests with test client
