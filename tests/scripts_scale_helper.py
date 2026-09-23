"""Render `/` against a synthetic fleet. Shared by `test_scale.py`.

Separate from the test module so the measurement is a function anybody can
call — `scripts/nmas-scale-report` does the same thing for a human, and two
copies of a measurement is how they come to disagree.
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures.fleet_scale import build_fleet


def render_sizes(sizes):
    """``{size: {"bytes": int, "loads": int}}`` for one render at each size."""
    import app as nmas
    from modules import device as device_mod

    out = {}
    client = nmas.app.test_client()
    for size in sizes:
        fleet = build_fleet(size)
        calls = {"n": 0}

        def _loader(filename=None, _fleet=fleet, _calls=calls):
            _calls["n"] += 1
            return list(_fleet)

        with mock.patch.object(device_mod, "load_saved_devices", _loader), \
             mock.patch("app.load_saved_devices", _loader):
            body = client.get("/").get_data()
        out[size] = {"bytes": len(body), "loads": calls["n"]}
    return out
