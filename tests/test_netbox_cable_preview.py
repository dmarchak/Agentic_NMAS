"""C1220: a NetBox import preview plans the cables the import makes, one per CDP/LLDP link.

Both ends of a link report it, so the import's cable pass (`netbox_client._sync_list_to_netbox_impl`)
meets each link twice, and `_ensure_cable` looks the cable up by either end, as either side,
before it creates one: the real run finds the cable the first pass made and creates one. The
dry run looked the planned cable up through its own matcher (`netbox_guard.params_match`), which
could not match ``termination_a_id``/``termination_b_id`` against the planned cable's
``a_terminations``/``b_terminations``, so it planned a second cable for every link, and the
preview a person confirms said more than the import sends ("what is confirmed is what is sent").

Through the whole import (`sync_list_to_netbox`), dry and real, on tests/fake_netbox.py, which
answers a cable lookup by its terminations and refuses a second cable on a cabled termination,
as NetBox does. The neighbours are the real parser over real captures
(tests/fixtures/operational/s1__ and s3__show_cdp_neighbors_detail.txt); the other end of each
link is the same capture with the device it names changed (a minimal edit: no capture of s2's or
s4's side was taken). The goldens are the fleet's (tests/fixtures/configs/fleet/).
"""

import os

import pytest

from tests.fake_netbox import FakeNetBox

HERE = os.path.dirname(os.path.abspath(__file__))
OPS = os.path.join(HERE, "fixtures", "operational")
FLEET = os.path.join(HERE, "fixtures", "configs", "fleet")
AUTHORITY = "test: declared by the test (C155)"


def _capture(name):
    with open(os.path.join(OPS, f"{name}__show_cdp_neighbors_detail.txt"), encoding="utf-8") as fh:
        return fh.read()


def _seen_from(capture, seen, by):
    """The other end's capture: the same link, naming the device *by* instead of *seen*."""
    assert f"Device ID: {seen}.rcn.lab" in capture, "floor: the capture names the neighbour"
    return capture.replace(f"Device ID: {seen}.rcn.lab", f"Device ID: {by}.rcn.lab")


#: Each device's CDP view: s1 sees s2 on Gi0/3 (and s2 sees s1), s3 sees s4 (and s4 sees s3).
CDP = {"s1": _capture("s1"), "s2": _seen_from(_capture("s1"), "s2", "s1"),
       "s3": _capture("s3"), "s4": _seen_from(_capture("s3"), "s4", "s3")}


@pytest.fixture
def importer(monkeypatch, tmp_path):
    """``run(hosts, dry)``: the whole import of *hosts* on a fresh fake NetBox, every one online,
    each with its fleet golden and its CDP view; returns (cables planned or created, the fake)."""
    import modules.netbox_client as nbc
    from modules import netbox_guard

    def golden(ip, list_name=""):
        host = {d["ip"]: d["hostname"] for d in _devices(list(CDP))}[ip]
        with open(os.path.join(FLEET, f"{host}.cfg"), encoding="utf-8") as fh:
            return {"text": fh.read(), "refused": ""}

    monkeypatch.setattr("modules.goldens._golden_record", golden)
    monkeypatch.setattr(nbc, "_fetch_neighbors_live",
                        lambda dev: nbc._parse_cdp_neighbors(CDP[dev["hostname"]]))
    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9",
                                                           "token": "t"})
    monkeypatch.setattr(nbc, "_SYNC_STATUS_FILE", str(tmp_path / "netbox_sync_status.json"))
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)

    def run(hosts, dry):
        fake = FakeNetBox()
        monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: fake)
        monkeypatch.setattr(nbc, "_managed_tag_ids", {})
        devs = _devices(hosts)
        out = nbc.sync_list_to_netbox("probe-cables", devs,
                                      status_cache={d["ip"]: True for d in devs},
                                      dry_run=dry, authority="" if dry else AUTHORITY)
        assert out.get("ok") and not out.get("failed"), (out.get("error"), out.get("failed"))
        if dry:
            assert fake.posts == [], "a dry run wrote to NetBox"
            return (out["plan"]["creates_by_type"].get("dcim/cables", 0), fake, out)
        return fake.created_counts().get("dcim/cables", 0), fake, out
    return run


def _devices(hosts):
    return [{"hostname": h, "ip": f"192.0.2.{20 + i}", "platform": "cisco_ios", "role": "switch"}
            for i, h in enumerate(sorted(hosts))]


class TestAPreviewPlansOneCablePerLink:
    def test_two_neighbours_plan_the_one_cable_the_import_makes(self, importer):
        planned, _fake, dry = importer(["s1", "s2"], dry=True)
        made, fake, _out = importer(["s1", "s2"], dry=False)
        assert made == 1 and len(fake.objects("dcim/cables")) == 1, \
            "floor: the real import makes one cable for the one link"
        assert planned == made, (f"the preview plans {planned} cable(s) for one link and the "
                                 f"import makes {made}: {dry['plan']['creates_by_type']}")

    def test_two_different_links_are_two_cables(self, importer):
        """The control: a second, different link (s3 to s4) is a second cable, in the preview
        and in the import, so the lookup did not merge links that share nothing."""
        planned, _fake, _dry = importer(["s1", "s2", "s3", "s4"], dry=True)
        made, fake, _out = importer(["s1", "s2", "s3", "s4"], dry=False)
        assert made == 2 and len(fake.objects("dcim/cables")) == 2
        assert planned == 2


class TestTheFakeAnswersCablesAsNetBoxDoes:
    """The shared fake is the expectation the dry run is compared with, so it must answer a
    cable by its ends and refuse a second cable on a cabled termination, as NetBox does."""

    def _cable(self, fake, a, b):
        return fake.post("http://nb.invalid/api/dcim/cables/", json={
            "a_terminations": [{"object_type": "dcim.interface", "object_id": a}],
            "b_terminations": [{"object_type": "dcim.interface", "object_id": b}]})

    def test_a_cable_is_found_by_either_end_on_its_own_side(self):
        fake = FakeNetBox()
        cable = self._cable(fake, 11, 12).json()

        def ids(**params):
            return [c["id"] for c in fake.get("http://nb.invalid/api/dcim/cables/",
                                              params=params).json()["results"]]
        assert ids(termination_a_id=11) == [cable["id"]]
        assert ids(termination_b_id=12) == [cable["id"]]
        assert ids(termination_a_id=12) == [] and ids(termination_b_id=11) == []
        assert ids(termination_a_id=13) == []

    def test_a_second_cable_on_a_cabled_termination_is_refused(self):
        fake = FakeNetBox()
        assert self._cable(fake, 11, 12).status_code == 201
        again = self._cable(fake, 12, 11)
        assert again.status_code == 400 and len(fake.objects("dcim/cables")) == 1
        assert self._cable(fake, 13, 14).status_code == 201, "a different link is accepted"


class TestTheDryRunMatcherFindsAPlannedCable:
    def test_by_either_end_and_nothing_else(self):
        from modules.netbox_guard import params_match

        cable = {"id": -7,
                 "a_terminations": [{"object_type": "dcim.interface", "object_id": -3}],
                 "b_terminations": [{"object_type": "dcim.interface", "object_id": 42}]}
        assert params_match(cable, {"termination_a_id": -3})
        assert params_match(cable, {"termination_b_id": 42})
        assert not params_match(cable, {"termination_a_id": 42})
        assert not params_match(cable, {"termination_b_id": -3})
        assert not params_match({"id": 1, "name": "Gi1"}, {"termination_a_id": -3}), \
            "an object with no ends is no cable"
