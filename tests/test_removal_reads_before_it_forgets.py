"""C130: a removal forgets a record entry only for an object NetBox says is
GONE, and a preview forgets nothing.

`_nb_get_by_id` returned `None` for a 404 AND for a failed read (a 500, a 403,
a timeout), logging at DEBUG, and the removal loop read `None` as "already
gone" and dropped the record entry, in the dry run as well as the real run.
So one NetBox hiccup during a PREVIEW made an object that still exists tagged
and unrecorded: Remove needs both, so it could never act on it again, and
nothing said so. Found preparing R2 (7.1's NetBox run), before it ran.

Driven through the real `remove_list_from_netbox` against a FakeNetBox that
answers 500 for one recorded object, and through the preview adapter that
draws the result.
"""

import pytest

from tests.fake_netbox import FakeNetBox, FakeResponse

LIST = "probe-c130"


class _Flaky(FakeNetBox):
    """Answers HTTP 500 for the objects named in `broken`."""

    def __init__(self):
        super().__init__()
        self.broken = set()

    def get(self, url, params=None, timeout=None):
        endpoint, obj_id = self._parse(url)
        if (endpoint, obj_id) in self.broken:
            return FakeResponse({"detail": "server error"}, 500)
        return super().get(url, params=params, timeout=timeout)


@pytest.fixture
def world(monkeypatch):
    from modules import netbox_guard as guard
    import modules.netbox_client as nbc

    nb = _Flaky()
    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9",
                                                           "token": "t"})
    monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: nb)
    monkeypatch.setattr(nbc, "_managed_tag_ids", {})
    monkeypatch.setattr(guard, "writes_allowed", lambda: True)
    monkeypatch.setattr(guard, "assert_writes_allowed", lambda *a: None)
    tag = [{"slug": guard.MANAGED_TAG_SLUG, "name": guard.MANAGED_TAG}]
    ok = nb.seed("dcim/devices", {"name": "p1", "tags": tag})
    flaky = nb.seed("dcim/devices", {"name": "p2", "tags": tag})
    guard.record_created(LIST, "dcim/devices", ok["id"], "p1")
    guard.record_created(LIST, "dcim/devices", flaky["id"], "p2")
    guard.record_created(LIST, "dcim/devices", 9999, "p3-already-gone")
    nb.broken.add(("dcim/devices", flaky["id"]))
    yield nb, ok, flaky
    guard.forget_created(LIST)


def _recorded_ids():
    from modules import netbox_guard as guard

    return sorted(e["id"] for e in guard.get_created(LIST, "dcim/devices")["dcim/devices"])


def test_a_preview_forgets_nothing(world):
    from modules.netbox_client import remove_list_from_netbox

    nb, ok, flaky = world
    before = _recorded_ids()
    out = remove_list_from_netbox(LIST, dry_run=True)
    assert _recorded_ids() == before, "the preview wrote the created-object record"
    assert [o["id"] for o in out["gone"]] == [9999], "the 404 is named, not silent"
    assert [o["id"] for o in out["failed"]] == [flaky["id"]]
    assert "could not be read" in out["failed"][0]["reason"]
    assert "HTTP 500" in out["failed"][0]["reason"]


def test_a_real_removal_forgets_the_gone_and_keeps_the_unreadable(world):
    from modules.netbox_client import remove_list_from_netbox

    nb, ok, flaky = world
    out = remove_list_from_netbox(LIST)
    assert [o["id"] for o in out["deleted"]] == [ok["id"]]
    assert out["complete"] is False, "an unreadable object is not a complete removal"
    # The control: the 404 IS forgotten by a real removal. The unreadable one
    # is kept, because it may still exist.
    assert _recorded_ids() == [flaky["id"]]


def test_the_preview_names_it_and_cannot_be_confirmed(world):
    from modules.netbox_client import remove_list_from_netbox
    from modules.preview_confirm import netbox_removal_preview

    nb, ok, flaky = world
    d = remove_list_from_netbox(LIST, dry_run=True)
    p = netbox_removal_preview(dict(d, writes_allowed=True, plan_hash="ab"),
                               {"may": True, "statement": "You are confirming as p."})
    assert p["what"]["targets"][0]["selectable"] is False
    assert p["what"]["summary"].startswith("This removal cannot be confirmed")
    kinds = [i["kind"] for i in p["what_not"]["items"]]
    assert kinds[0] == "unreadable" and "gone" in kinds
    gates = {g["name"]: g["state"] for g in p["targets"][0]["gates"]}
    assert gates["every recorded object read from NetBox"] == "fail"


def test_a_clean_preview_is_confirmable(world):
    """The floor: with every object readable, the gate passes and the target
    can be selected (a preview that always refused would pass the tests above)."""
    from modules.netbox_client import remove_list_from_netbox
    from modules.preview_confirm import netbox_removal_preview

    nb, ok, flaky = world
    nb.broken.clear()
    d = remove_list_from_netbox(LIST, dry_run=True)
    p = netbox_removal_preview(dict(d, writes_allowed=True, plan_hash="ab"),
                               {"may": True, "statement": "You are confirming as p."})
    assert p["what"]["targets"][0]["selectable"] is True
    gates = {g["name"]: g["state"] for g in p["targets"][0]["gates"]}
    assert gates["every recorded object read from NetBox"] == "pass"
