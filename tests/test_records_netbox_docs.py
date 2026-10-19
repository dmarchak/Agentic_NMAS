"""Mercury's NetBox bookkeeping on the records database (K31 part 3: three DOCUMENT stores, each one
document for the installation), against a REAL PostgreSQL shaped as host step 6a makes it
(tests/pg_instance.py; skipped with its reason here, a failure in CI).

What NMAS created (half of Remove's `tagged AND recorded`), modified and adopted, written and read
through `netbox_guard`'s own functions (`record_created`, `recorded_objects`, `get_created`,
`record_modified`, `read_modified`, `record_adopted`, `get_adopted`). Each keeps its contract on a
database that does not answer: an unreadable created record is refused on a write (never read as
"owns nothing" and saved over), and a read says it could not be read.
"""

import os

import pytest

from modules import netbox_guard as G
from modules import records_docs
from modules import records_migrate as RM
from tests.test_records_restarts import db, pg  # noqa: F401 (the server and the settings)


@pytest.fixture
def nb(db, tmp_path, monkeypatch):
    for attr, name in (("_CREATED_IDS_FILE", "netbox_created_ids.json"),
                       ("_MODIFIED_FILE", "netbox_modified.json"),
                       ("_ADOPTED_FILE", "netbox_adopted.json")):
        monkeypatch.setattr(G, attr, str(tmp_path / name))
    return db


def _move(store):
    return RM.move(RM.plan(store=store)["fingerprint"], "alex@example.com", "access", store=store)


def _adopt(network, n):
    got = G.record_adopted(network, f"r{n}", [("dcim/devices", 100 + n, f"r{n}")],
                           actor="alex@example.com", reason="it existed before adoption",
                           authority="netbox")
    assert got["ok"], got


def test_the_three_are_document_stores_kept_once():
    for store in ("netbox_created", "netbox_modified", "netbox_adopted"):
        assert records_docs.is_doc_store(store)
        assert records_docs.store_of(store).shape is dict


class TestTheCreatedRecord:
    def test_the_move_keeps_what_was_created_and_new_objects_land_in_the_table(self, nb):
        G.record_created("Default", "dcim/devices", 1, "r1")
        G.record_created("Branch", "dcim/devices", 2, "b1")
        assert _move("netbox_created")["ok"]
        assert G.recorded_objects("Default") == ([("dcim/devices", 1, "r1")], "")
        G.record_created("Default", "ipam/ip-addresses", 3, "192.0.2.1/32")
        assert ("ipam/ip-addresses", 3, "192.0.2.1/32") in G.recorded_objects("Default")[0]
        assert [e["id"] for e in G.get_created("Branch")["dcim/devices"]] == [2], "kept apart"
        assert RM.check(store="netbox_created")["ok"]

    def test_the_move_back_writes_the_record_to_its_file(self, nb):
        G.record_created("Default", "dcim/devices", 1, "r1")
        assert _move("netbox_created")["ok"]
        G.record_created("Default", "dcim/devices", 4, "r4")
        back = RM.move_back(RM.plan(store="netbox_created")["fingerprint"], "alex@example.com",
                            "access", store="netbox_created")
        assert back["ok"], back["steps"]
        ids = sorted(e[1] for e in G.recorded_objects("Default")[0])
        assert ids == [1, 4] and os.path.exists(G._CREATED_IDS_FILE)


class TestTheAdoptedAndModifiedRecords:
    def test_adoptions_on_the_database_are_read_back_per_list(self, nb):
        _adopt("Default", 1)
        assert _move("netbox_adopted")["ok"]
        _adopt("Branch", 2)
        assert G.get_adopted("Default") == ([("dcim/devices", 101, "r1", "r1")], "")
        assert G.get_adopted("Branch")[0][0][1] == 102

    def test_a_modification_on_the_database_is_read_back(self, nb):
        G.record_modified("Default", "dcim/devices", 7, {"serial": ["", "X1"]}, name="r7",
                          actor="alex@example.com")
        assert _move("netbox_modified")["ok"]
        data, why = G.read_modified()
        assert why is None and data, (data, why)


class TestADatabaseThatDoesNotAnswer:
    @pytest.fixture
    def down(self, nb):
        for store in ("netbox_created", "netbox_modified", "netbox_adopted"):
            nb["values"][f"records_store_{store}"] = "postgres"
        nb["values"]["records_db_port"] = 1
        return nb

    def test_a_created_record_that_cannot_be_read_refuses_a_write(self, down):
        with pytest.raises(G.CreatedRecordUnreadable):
            G._load_created_for_write()

    def test_reads_say_unreadable_never_owns_nothing(self, down):
        held, why = G.recorded_objects("Default")
        assert held == [] and "could not be read" in why
        assert G.read_modified()[0] is None
        assert "could not be read" in G.get_adopted("Default")[1]

    def test_an_adoption_that_cannot_be_kept_says_so(self, down):
        got = G.record_adopted("Default", "r1", [("dcim/devices", 1, "r1")],
                               actor="a", reason="it existed before", authority="netbox")
        assert got["ok"] is False and got["error"]
        assert not os.path.exists(G._ADOPTED_FILE), "nothing fell back to the file"
