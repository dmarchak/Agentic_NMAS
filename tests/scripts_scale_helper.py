"""What one request for a v2 page costs, per fleet size. Shared by `test_scale.py`.

Separate from the test module so the measurement is a function anybody can call: two
copies of a measurement is how they come to disagree. Until P7-19 (2026-10-15) it rendered
today's index (`/`), which goes at cutover; `scripts/nmas-scale-report` still measures that
page with its own copy (a finding of P7-19).

**Per-device work, measured as what moves with the fleet** (criterion 11, "no per-device
work per request"), for one request after a warm one:

- ``children``: processes started (`git` and anything else), counted at `subprocess.Popen`;
- ``opens``: files opened under the network's folder (a golden, intent, the manifest);
- ``loads``: reads of the inventory (`load_saved_devices`), counted by the caller's loader;
- ``connects``: socket connects (a device session, or any other), counted at the socket;
- ``calls``: Python function calls (`cProfile`'s count), the CPU work no I/O count sees:
  a loop over the whole inventory to draw one device's page reads no file per device and
  still costs one pass per device (measured 2026-10-15 on the device page);
- ``bytes``: the answer's size.

Nothing here writes into `data/lists/`: the caller's lab is under a temporary folder.
"""

import builtins
import cProfile
import os
import pstats
import socket
import subprocess
from unittest import mock


def golden_for(device: dict) -> str:
    """A small, parseable configuration for a fleet device: its hostname and a loopback."""
    _a, _b, c, d = device["ip"].split(".")
    return (f"hostname {device['hostname']}\n!\ninterface Loopback0\n"
            f" ip address 10.{int(c) - 100}.{d}.1 255.255.255.255\n!\nend\n")


def commit_goldens(list_name: str, devices: list) -> dict:
    """One commit of a golden for each device the fleet does not mark `no_golden`."""
    from modules.nsot.repo import GoldenItem, save_golden

    items = [GoldenItem(d["hostname"], golden_for(d), d["ip"], platform=d["platform"])
             for d in devices if d.get("_scale_state") != "no_golden"]
    out = save_golden(list_name, items, source="onboarding", actor="t", allow_new=True,
                      baseline=False)
    assert out.get("ok"), out
    return out


def measure(client, path: str, list_dir: str, loads: dict) -> dict:
    """One request for *path*, after a warm one, and what it cost (the module docstring)."""
    client.get(path)                                   # warm: templates, caches
    counts = {"children": 0, "opens": 0, "connects": 0}
    loads["n"] = 0
    real_init, real_open = subprocess.Popen.__init__, builtins.open
    real_connect = socket.socket.connect
    prefix = os.path.realpath(list_dir) + os.sep

    def popen_init(self, *a, **k):
        counts["children"] += 1
        return real_init(self, *a, **k)

    def counting_open(file, *a, **k):
        if isinstance(file, (str, os.PathLike)) and \
                os.path.realpath(os.fspath(file)).startswith(prefix):
            counts["opens"] += 1
        return real_open(file, *a, **k)

    def connect(self, *a, **k):
        counts["connects"] += 1
        return real_connect(self, *a, **k)

    profile = cProfile.Profile()
    with mock.patch.object(subprocess.Popen, "__init__", popen_init), \
         mock.patch.object(builtins, "open", counting_open), \
         mock.patch.object(socket.socket, "connect", connect):
        profile.enable()
        try:
            r = client.get(path)
        finally:
            profile.disable()
    assert r.status_code == 200, (path, r.status_code)
    return dict(counts, loads=loads["n"], calls=pstats.Stats(profile).total_calls,
                bytes=len(r.get_data()))
