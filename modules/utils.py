"""utils.py

Small helper utilities used by the web app. Keep this module tiny so
that common helpers (like filename generation) are easy to locate and
unit-test.
"""

import time


def make_device_filename(hostname: str) -> str:
    """Generate a short timestamped filename for device output/downloads.

    The timestamp uses a compact format (day-hour-minute-month-year)
    so filenames are stable and sortable while remaining human
    readable.
    """
    timestamp = time.strftime("%d%H%M%b%y").upper()  # DayHourMinuteMonthYear
    return f"{hostname}_{timestamp}.txt"
