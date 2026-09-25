"""OPEN_FINDINGS C6 item 2: NetBox objects NMAS creates from a CODE-defined
spec, and never updates.

A changed spec never reaches a NetBox that already holds the object, and a
failed create used to be logged at DEBUG while the caller quietly skipped the
field: a write that failed with nothing saying so.
"""

import logging

import pytest

from modules import netbox_client as nc


class _Resp:
    def __init__(self, results):
        self._r = results

    def raise_for_status(self):
        pass

    def json(self):
        return {"results": self._r}


class _Session:
    """GET-only fake: answers list queries from a table keyed on the query."""

    def __init__(self, table, fail=()):
        self.table, self.fail = table, set(fail)

    def get(self, url, params=None, timeout=None):
        path = url.split("/api/", 1)[1]
        key = (path, tuple(sorted((params or {}).items())))
        if path in self.fail:
            raise ConnectionError("refused")
        return _Resp(self.table.get(key, []))


def _cf(**over):
    obj = {"name": "os_version", "label": "OS Version",
           "type": {"value": "text", "label": "Text"},
           "object_types": ["dcim.device"],
           "description": nc._CUSTOM_FIELDS["os_version"]["description"]}
    obj.update(over)
    return obj


def _table(cf=None, tags=None):
    t = {}
    if cf is not None:
        t[("extras/custom-fields/", (("name", "os_version"),))] = [cf]
    for slug, obj in (tags or {}).items():
        t[("extras/tags/", (("slug", slug),))] = [obj]
    return t


def _all_tags(**over):
    tags = {slug: {"slug": slug, **spec}
            for slug, spec in nc._seeded_tag_specs().items()}
    tags.update(over)
    return tags


def _by_name(report):
    return {o["name"]: o for o in report["objects"]}


class TestTheComparison:
    def test_the_scan_covers_every_code_defined_spec(self):
        """Floor: 1 custom field + nmas-managed + static-route + 6 protocols."""
        r = nc.seeded_spec_status(_Session(_table(_cf(), _all_tags())), "b")
        assert len(r["objects"]) == 9
        assert {o["state"] for o in r["objects"]} == {"current"}

    def test_a_moved_spec_is_reported_with_both_operands(self):
        tags = _all_tags(**{"nmas-managed": {"slug": "nmas-managed",
                                             "name": "nmas-managed",
                                             "color": "ff0000"}})
        cf = _cf(object_types=["dcim.device", "virtualization.virtualmachine"])
        got = _by_name(nc.seeded_spec_status(_Session(_table(cf, tags)), "b"))
        assert got["nmas-managed"]["state"] == "differs"
        assert got["nmas-managed"]["fields"] == [
            {"field": "color", "code": "00bcd4", "netbox": "ff0000"}]
        assert got["os_version"]["state"] == "differs"
        assert got["os_version"]["fields"][0]["field"] == "object_types"

    def test_absent_and_unreadable_are_named_not_current(self):
        s = _Session(_table(None, _all_tags()), fail={"extras/custom-fields/"})
        got = _by_name(nc.seeded_spec_status(s, "b"))
        assert got["os_version"]["state"] == "unreadable"
        s = _Session(_table(None, {}))
        got = _by_name(nc.seeded_spec_status(s, "b"))
        assert got["os_version"]["state"] == "absent"
        assert got["ospf"]["state"] == "absent"


class TestAFailedDefinitionWriteIsVisible:
    def test_a_failed_custom_field_create_warns_and_reaches_the_notes(
            self, monkeypatch, caplog):
        nc._custom_fields_ensured.discard("os_version")
        nc._drain_ensure_failures()
        monkeypatch.setattr(nc, "_nb_first", lambda *a, **k: None)

        def refuse(*a, **k):
            raise RuntimeError("HTTP 400 object_types invalid")
        monkeypatch.setattr(nc, "_nb_post", refuse)
        with caplog.at_level(logging.WARNING, logger=nc.log.name):
            assert nc._ensure_custom_field(None, "b", "os_version") is False
        assert any("could not be written" in r.message
                   and r.levelno >= logging.WARNING for r in caplog.records)
        notes = nc._drain_ensure_failures()
        assert notes and "os_version" in notes[0]
        assert nc._drain_ensure_failures() == [], "drained, not repeated"

    def test_the_sync_summary_carries_the_notes(self):
        """Wired, not only collected: the summary is where a person sees it."""
        import inspect
        src = inspect.getsource(nc._sync_list_to_netbox_impl)
        assert "provisioning_notes + _drain_ensure_failures()" in src
        # Anchored on the first device WRITE, not on prose: an earlier
        # version compared against the first "for ", which a comment holds.
        assert "_upsert_device(" in src, "floor: the anchor exists"
        assert src.index("_drain_ensure_failures()") < src.index(
            "_upsert_device("), \
            "stale failures from an earlier sync must be cleared first"
