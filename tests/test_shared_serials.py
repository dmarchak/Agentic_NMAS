"""A serial is never assumed unique (the operator, 2026-10-04; C449).

Every C8000v of one virtual image reports the same serial: r1 to r4 and r6 all carry
`license udi pid C8000V sn <one value>` in their goldens, unchanged across redeploys. Two
rules: anything that matches a device by serial refuses when more than one device reports
it (the NetBox sync matched by serial FIRST, so r2's sync would have renamed r1's record to
r2 and overwritten its context); and nothing else keys a device on its serial. A shared
serial is information in job health, never a Needs attention row.

On the fleet's REAL captures (tests/fixtures/configs/fleet, the serial redacted to one value
as captured: five routers report it, the four switches state none).
"""

import ast
import os

import pytest

from modules import device_serials as DS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
NAMES = sorted(n[:-4] for n in os.listdir(FLEET) if n.endswith(".cfg"))


@pytest.fixture
def fleet(monkeypatch):
    """One list whose committed goldens are the fleet's real captures."""
    from modules.nsot import repo as R

    monkeypatch.setattr(R, "list_goldens", lambda list_name: [
        {"hostname": n, "rel": f"golden/{n}.cfg", "path": f"/x/golden/{n}.cfg"} for n in NAMES])
    monkeypatch.setattr(R, "committed_golden", lambda repo, rel: {
        "text": open(os.path.join(FLEET, os.path.basename(rel)), encoding="utf-8").read(),
        "refused": ""})
    return [("Default", "/x")]


def test_the_fleets_real_captures_share_one_serial(fleet):
    assert len(NAMES) >= 9, "the fixture shrank"
    shared = DS.shared(fleet)
    assert len(shared) == 1, shared
    (sn, devs), = shared.items()
    assert sorted(d for _l, d in devs) == ["r1", "r2", "r3", "r4", "r5"]
    assert DS.serial_of(open(os.path.join(FLEET, "s1.cfg"), encoding="utf-8").read()) == ""


def test_job_health_says_it_as_information_never_a_row(fleet):
    from modules import attention as A
    from modules import job_health as J

    rows = J.serial_rows(shared=DS.shared(fleet))
    assert [r["state"] for r in rows] == ["shared"]
    assert "5 devices report one serial" in rows[0]["headline"]
    assert "a fault on real hardware" in rows[0]["headline"]
    res = A.job_health_source(health=lambda: {"jobs": rows})
    assert res["rows"] == [], "a shared serial became a Needs attention row"
    assert "5 devices report one serial" in res["checked"]
    assert J.serial_rows(shared={}) == []


class TestTheNetBoxMatch:
    @pytest.fixture
    def nb(self, monkeypatch):
        from modules import netbox_client as N

        r1 = {"id": 1, "name": "r1", "serial": "SN1"}
        r2 = {"id": 2, "name": "r2", "serial": ""}
        holders = {"SN1": [r1], "TWICE": [r1, r2]}
        monkeypatch.setattr(N, "_nb_get", lambda s, b, p, **q: list(holders.get(q.get("serial"), [])))
        monkeypatch.setattr(N, "_nb_first", lambda s, b, p, **q:
                            {"r1": r1, "r2": r2}.get(q.get("name")))
        return N

    def test_a_shared_serial_never_takes_another_devices_record(self, nb):
        got = nb._existing_device(None, "b", "r2", 1, "SN1",
                                  sharing=[("Default", "r1"), ("Default", "r2")])
        assert got["name"] == "r2", "r2's sync matched r1's record by a shared serial"

    def test_a_serial_two_netbox_devices_hold_is_not_used(self, nb):
        got = nb._existing_device(None, "b", "r2", 1, "TWICE", sharing=[("Default", "r2")])
        assert got["name"] == "r2"

    def test_a_unique_serial_still_matches_a_renamed_device(self, nb):
        got = nb._existing_device(None, "b", "r1-renamed", 1, "SN1",
                                  sharing=[("Default", "r1-renamed")])
        assert got["id"] == 1, "a unique serial should follow a device across a rename"


def test_nothing_else_looks_a_device_up_by_serial():
    """The shape, not the members: a call passing a `serial=` keyword (a lookup by serial)
    lives only in the one guarded matcher."""
    allowed = {("modules/netbox_client.py", "_existing_device")}
    found = []
    for top in ("modules", "routes"):
        for d, _s, files in os.walk(os.path.join(ROOT, top)):
            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(d, f)
                rel = os.path.relpath(path, ROOT)
                tree = ast.parse(open(path, encoding="utf-8").read())
                for fn in ast.walk(tree):
                    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    for node in ast.walk(fn):
                        if isinstance(node, ast.Call) and any(
                                k.arg == "serial" for k in node.keywords):
                            if (rel, fn.name) not in allowed:
                                found.append(f"{rel}:{node.lineno} in {fn.name}")
    assert found == [], f"a device looked up by serial outside the guarded matcher: {found}"
