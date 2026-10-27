"""Networks a test registers (C1903). A read of something kept per network names a network the
device-list registry holds: `listref.network_id` raises for a name no network answers to, never
answering empty. A test whose network is a name of its own registers it here, beside those the
registry the app reads already holds (the installation's Default when it holds none), as New
network… would. (Not a test module.)"""

import json
import os


def register(monkeypatch, folder, *names) -> str:
    """Register *names* in a registry file in *folder*, beside the networks the app's current
    registry holds, the app reading it from now on in this test. Returns the file's path."""
    from modules import device
    from modules.config import list_slug

    doc = {"current_list": "Default", "lists": {"Default": "default"}}
    if os.path.exists(device.DEVICE_LISTS_CONFIG):
        with open(device.DEVICE_LISTS_CONFIG, encoding="utf-8") as fh:
            doc = json.load(fh)
    doc.setdefault("lists", {}).update({name: list_slug(name) for name in names})
    path = os.path.join(str(folder), "device_lists_registered.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    monkeypatch.setattr("modules.device.DEVICE_LISTS_CONFIG", path)
    # A registered network's folder, should anything resolve one, is the test's own, never the
    # session's store (tests/conftest.py refuses a test that leaves one there).
    monkeypatch.setattr("modules.config.LISTS_DIR", os.path.join(str(folder), "lists"))
    return path
