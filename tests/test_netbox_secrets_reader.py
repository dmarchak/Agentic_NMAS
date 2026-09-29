"""The netbox-secrets reader and its Needs attention row (the operator,
2026-09-29): a credential NetBox holds in a device's stored config context is
a live exposure in a shared system, and retire now proceeds past one NMAS
never wrote. So something must keep it in front of a person.

Built on r5's REAL config in the stored-context shape the live NetBox held
(tests/test_netbox_mask_context.py's fixture); the judgement is the
secret-storage checker's own scan.
"""

import json

import pytest

from modules import attention, reader_job
from modules.readers import netbox_secrets as NS
from tests.fake_netbox import FakeNetBox
from tests.test_netbox_mask_context import COMMUNITY, _device, _record


@pytest.fixture
def netbox(monkeypatch):
    import modules.netbox_client as nbc
    from modules import netbox_guard

    fake = FakeNetBox()
    fake.seed("dcim/devices", _device(i=9, name="r5"))
    fake.seed("dcim/devices", _device(i=3, name="r3", ctx={}))
    state = {"record": (_record(), None)}
    monkeypatch.setattr(nbc, "_nb_ready", lambda: (True, "", fake, "http://127.0.0.1:9"))
    monkeypatch.setattr(netbox_guard, "read_modified", lambda: state["record"])
    return {"fake": fake, "state": state}


def _cached(value):
    """A reader store as `reader_job.read_cached` returns it, from a real read."""
    return {"state": "ok", "doc": {"last_good": {"value": value, "value_at": "2026-09-29T12:00:00Z"},
                                   "stale_after_seconds": 3 * NS.INTERVAL_SECONDS}}


class TestTheRead:
    def test_it_finds_the_held_credential_and_names_no_value(self, netbox):
        v = NS.read()
        assert v["configured"] is True and v["scanned"] == 2
        (d,) = v["devices"]
        assert d["name"] == "r5" and d["id"] == 9 and d["slots"] and d["communities"] == 1
        assert d["wrote"] == "2026-09-25T06:17:34Z", "the record says NMAS wrote it"
        assert COMMUNITY not in json.dumps(v), "slots and counts only, never a value"

    def test_a_context_nmas_never_wrote_says_so(self, netbox):
        netbox["state"]["record"] = ({}, None)
        (d,) = NS.read()["devices"]
        assert d["wrote"] == "" and d["record_unreadable"] == ""

    def test_not_configured_is_stated_never_an_empty_answer(self, monkeypatch):
        import modules.netbox_client as nbc

        monkeypatch.setattr(nbc, "_nb_ready", lambda: (False, "NetBox URL and API token are "
                                                                "not configured", None, ""))
        v = NS.read()
        assert v["configured"] is False and "not configured" in v["why"]

    def test_a_netbox_that_cannot_be_read_raises(self, netbox):
        """So the failure is the reader's job-health row, never "none held"."""
        netbox["fake"].get = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("refused"))
        with pytest.raises(ConnectionError):
            NS.read()

    def test_it_is_a_declared_reader(self):
        assert "modules.readers.netbox_secrets" in reader_job.DECLARED_MODULES
        assert any(r.name == "netbox-secrets" for r in reader_job.readers())


class TestTheRow:
    def test_a_context_nmas_wrote_offers_the_mask(self, netbox):
        out = attention.netbox_secrets_source(cached=_cached(NS.read()))
        (row,) = out["rows"]
        assert row["level"] == "danger" and row["what"] == "NetBox holds a credential for r5"
        assert "nmas-netbox-mask-context --device r5 --apply" in json.dumps(row["action"])
        assert COMMUNITY not in json.dumps(out)
        assert "2 NetBox device(s) scanned, 1 holding a credential" in out["checked"]

    def test_a_context_nmas_never_wrote_says_remove_it_in_netbox(self, netbox):
        netbox["state"]["record"] = ({}, None)
        (row,) = attention.netbox_secrets_source(cached=_cached(NS.read()))["rows"]
        assert "somebody's data" in row["cause"]
        assert "in NetBox by hand" in row["action"]["label"]

    def test_an_unreadable_record_is_unknown_never_an_action_it_cannot_back(self, netbox):
        netbox["state"]["record"] = (None, "not readable JSON")
        (row,) = attention.netbox_secrets_source(cached=_cached(NS.read()))["rows"]
        assert "cannot be told" in row["cause"] and row["action"]["known"] is False

    def test_nothing_held_is_no_row_and_says_what_was_looked_at(self, netbox):
        netbox["fake"].store["dcim/devices"][0]["local_context_data"] = {}
        out = attention.netbox_secrets_source(cached=_cached(NS.read()))
        assert out["rows"] == [] and "0 holding a credential" in out["checked"]

    def test_no_stored_value_is_a_failed_read_never_nothing_held(self):
        out = attention.netbox_secrets_source(cached={"state": "missing", "why": "never ran",
                                                      "doc": {}})
        assert out["state"] == "unreadable" and "not read yet: never ran" in json.dumps(out)
        assert out["rows"] == [] or out["rows"][0]["level"] != "ok"

    def test_it_is_a_source_of_the_page(self):
        assert attention.netbox_secrets_source in attention.SOURCES
