"""The test suite must not write into the app log of the checkout it runs in.

Importing `app` attaches a file handler for `logs/device_manager.log` to the
root logger. Measured on the host 2026-09-26: a suite run in the live checkout
on 2026-09-23 left 24 fixture ERRORs in that log, and the log is the channel
`nmas-netbox-modified` counts recorder failures from (register C5, C26).
`tests/conftest.py` takes the handler back off; this pins it.
"""

import logging


def _app_log_handlers():
    return [h for h in logging.getLogger().handlers
            if getattr(h, "baseFilename", "").endswith("device_manager.log")]


def test_no_root_handler_writes_the_app_log():
    assert _app_log_handlers() == []


def test_the_app_did_attach_one():
    """Control: the check above is not passing because the app never made a
    handler. `app.file_handler` exists whenever the app is not in debug."""
    import app
    handler = getattr(app, "file_handler", None)
    assert handler is not None
    assert handler.baseFilename.endswith("device_manager.log")
    assert handler not in logging.getLogger().handlers
