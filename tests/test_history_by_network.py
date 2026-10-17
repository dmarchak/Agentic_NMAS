"""A network's History shows its own records, never another network's (C1028, W2's B6).

W2 walk, a network with no devices, drew Default's persist and rotation rows for all nine of
Default's devices (the operator, W2 step 38, screenshot 30). The page passed its inventory as
``members or None``, so an EMPTY inventory meant "no filter", and the rotation record (one file
for the installation, its rows naming a device and no network, C361) kept every row.

The class: a store every network shares whose rows name a device and no network
(`history_sources.SHARED_BY_DEVICE`) is the network's only through the network's own devices
(`_ours`, an inventory that is always a set). An empty network has none of those rows; an
inventory that cannot be read has none either, and says so (absent and unreadable differ).

On the real app, over a temporary store with four networks (tests/test_settings_v2's
`networks`): Default holds r1 and r2 and the shared records about them; Branch holds none.
"""

import ast
import inspect
import json
import os
import re
import time

import pytest

from modules import history_sources as HS
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

NOW = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
#: What the shared records draw: a persist, a rotation, an acknowledgement, each about r1 or r2.
SHARED_WORDS = ("Persisted: the startup config carries", "Rotation: rotated",
                "Acknowledged: r1&#39;s rotation row")


@pytest.fixture
def shared(networks):  # noqa: F811
    """Default's two devices, and a record of each kind every network shares about them."""
    from modules import device

    device.write_devices_csv([{"hostname": "r1", "ip": "192.0.2.51"},
                              {"hostname": "r2", "ip": "192.0.2.52"}],
                             str(networks["dir"] / "lists" / "default" / "devices.csv"))
    rows = [{"at": NOW, "phase": "persist", "device": "r1", "state": "persisted",
             "failed_stage": "", "actor": "a@example.invalid", "stages": [], "via": "test"},
            {"at": NOW, "phase": "rotate", "device": "r2", "state": "rotated",
             "failed_stage": "", "actor": "a@example.invalid", "stages": [], "via": "test"}]
    (networks["dir"] / "rotation_audit.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (networks["dir"] / "acknowledgements.jsonl").write_text(json.dumps(
        {"row": "jobs:rotation:r1", "kind": "jobs/rotation", "by": "a@example.invalid",
         "why": "known", "at": NOW, "devices": ["r1"], "what": "r1's rotation row"}) + "\n",
        encoding="utf-8")
    return networks


def _timeline_of(n, network, path="/v2/history/timeline"):
    r = n["client"].get(f"{path}?list={network}&since=")
    assert r.status_code == 200, (network, r.status_code)
    return re.sub(r"\s+", " ", r.get_data(as_text=True))


class TestAnEmptyNetworkKeepsNoneOfAnother_s:
    def test_the_records_are_default_s_where_its_devices_are(self, shared):
        """The control: the planted records are drawn where they belong."""
        html = _timeline_of(shared, "Default")
        for words in SHARED_WORDS:
            assert words in html, words

    @pytest.mark.parametrize("path", ["/v2/history", "/v2/history/timeline"])
    def test_a_network_with_no_devices_draws_none_of_them(self, shared, path):
        """W2's B6: W2 walk (0 devices) drew Default's persists and rotations."""
        html = _timeline_of(shared, "Branch", path)
        drawn = [w for w in SHARED_WORDS if w in html]
        assert drawn == [], f"Branch, with no devices, drew another network's records: {drawn}"

    def test_an_unreadable_inventory_says_so_and_draws_none_of_them(self, shared, monkeypatch):
        """Absent and unreadable are different: the page says the inventory could not be read,
        and draws no shared row, since which are this network's cannot be told."""
        from modules import device

        real = device.load_saved_devices

        def broken(path=None, *a, **kw):
            if path and os.sep + "branch" + os.sep in str(path):
                raise OSError("devices.csv: permission denied")
            return real(path, *a, **kw)
        monkeypatch.setattr(device, "load_saved_devices", broken)
        html = _timeline_of(shared, "Branch")
        assert "inventory could not be read" in html and "permission denied" in html
        assert [w for w in SHARED_WORDS if w in html] == []


class TestTheShape:
    def test_the_shared_check_keeps_nothing_for_no_devices(self):
        assert HS._ours({"device": "", "inventory": set()}, "r1") is False
        assert HS._ours({"device": "", "inventory": {"r1"}}, "r1") is True
        assert HS._ours({"device": "r1", "inventory": set()}, "r1") is True, "a device's own view"

    def test_every_source_is_given_the_network_s_devices_as_a_set(self, shared, monkeypatch):
        """`timeline` builds ONE context for every source: its inventory is the members passed
        (``[]`` stays empty), else read from the network; never None, which read as everyone."""
        from modules.nsot import listref

        seen = []
        monkeypatch.setattr(HS, "SOURCES", {"probe": lambda ctx: seen.append(ctx) or HS._out()})
        HS.timeline(listref.resolve("Branch"), members=[])
        HS.timeline(listref.resolve("Branch"))
        HS.timeline(listref.resolve("Default"))
        assert [c["inventory"] for c in seen] == [set(), set(), {"r1", "r2"}]

    def test_each_shared_store_s_source_asks_ours_and_only_they_do(self):
        """A store every network shares, its rows naming no network, is DECLARED with why
        (`SHARED_BY_DEVICE`), and its source tells the network's rows by `_ours`; a source that
        asks `_ours` is declared. Parsed, so a new source of a shared store is either declared
        or found."""
        tree = ast.parse(inspect.getsource(HS))
        asks = {}
        for fn in tree.body:
            if isinstance(fn, ast.FunctionDef):
                names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
                asks[fn.name] = names
        # A host-key window's summaries are read by its helper, inside `host_keys`.
        asks["host_keys"] = asks["host_keys"] | asks["_host_key_window_summaries"]
        users = {name for name, used in asks.items()
                 if "_ours" in used and not name.startswith("_")}
        assert users == set(HS.SHARED_BY_DEVICE), (users, set(HS.SHARED_BY_DEVICE))
        for name in ("rotation", "acknowledgements"):
            assert "_mine" not in asks[name], f"{name} reads a shared store: it asks _ours"
        assert len(HS.SHARED_BY_DEVICE) >= 5 and set(HS.SHARED_BY_DEVICE) <= set(HS.SOURCES)

    def test_the_page_passes_its_inventory_as_read(self):
        """``members or None`` made an empty inventory "no filter": the page passes what it
        read, and None only for an inventory that could not be read."""
        import textwrap

        from routes import v2

        fn = ast.parse(textwrap.dedent(inspect.getsource(v2._history_timeline))).body[0]
        passed = [k.value for c in ast.walk(fn) if isinstance(c, ast.Call)
                  for k in c.keywords if k.arg == "members"]
        assert len(passed) == 1 and isinstance(passed[0], ast.Name) \
            and passed[0].id == "members", [ast.unparse(p) for p in passed]
