"""utils.py

Shared utility helpers for the Network Device Manager.

Currently provides `make_device_filename`, which generates a compact
timestamped filename (e.g. "R1_12153012APR26.txt") used for device
output downloads.  Additional stateless helpers that don't belong in
any specific feature module should go here.
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


def error_text(exc: BaseException) -> str:
    """An exception as a sentence that is never empty.

    `str(exc)` is "" for an exception raised with no message, and
    `cryptography.fernet.InvalidToken` is exactly that: R1's bulk reload
    recorded probe-r1a as `failed` with the error "", logged nothing, and the
    screen said "sent" (C152). A failure must always say at least what it was.
    """
    text = str(exc).strip()
    name = type(exc).__name__
    return f"{name}: {text}" if text and name not in text else (text or name)

