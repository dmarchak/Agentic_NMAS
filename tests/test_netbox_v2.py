"""Source of truth › NetBox on v2 (cutover blocker 2, 2026-10-10), through the real app on a
temporary store (tests/test_settings_v2's `networks`). The sync is replaced at its edge as the
token round-trip test replaces it (a plan of one device to create); everything between (the
job, the preview component, the one-shot token, the master switch, the import's result) is the
real code. A job's thread runs inline here, so each answer is there when the test reads it.
"""

import json
import os
import re

import pytest

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

PLAN = {"creates": [{"endpoint": "dcim/devices", "name": "r9", "id": -2, "payload": {}}],
        "updates": [], "deletes": [], "create_count": 1, "update_count": 0,
        "delete_count": 0, "creates_by_type": {"dcim/devices": 1}, "updates_by_type": {},
        "deletes_by_type": {}}
#: A removal dry run's cascade that NetBox answered for every delete, taking nothing more (the
#: shape `netbox_cascade.collateral` returns). A dry run with none was never asked (B9).
PROVEN = {"taken": [], "foreign": [], "unproven": [], "proven": True}


class _Inline:
    def __init__(self, target=None, **_k):
        self.target = target

    def start(self):
        self.target()


@pytest.fixture
def nb(networks, monkeypatch, tmp_path):
    import modules.netbox_client as nbc
    from modules import device, netbox_guard

    device.write_devices_csv([{"hostname": "r9", "ip": "192.0.2.9"}],
                             str(networks["dir"] / "lists" / "branch" / "devices.csv"))
    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://192.0.2.8", "token": "t"})
    for name in ("_CREATED_IDS_FILE", "_MODIFIED_FILE", "_ADOPTED_FILE", "_REMOVALS_FILE"):
        monkeypatch.setattr(netbox_guard, name, str(tmp_path / f"{name.strip('_').lower()}"))
    switch = {"on": False}
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: switch["on"])

    def write_settings(changes, actor=""):
        switch["on"] = bool(changes.get("netbox_allow_writes", switch["on"]))
        return {"ok": True}
    monkeypatch.setattr("modules.settings_schema.write_settings", write_settings)
    plan = {"value": PLAN}
    sent = []

    def sync(name, devs, dry_run=False, **k):
        if not dry_run:
            sent.append(name)
        return {"plan": plan["value"]}
    monkeypatch.setattr(nbc, "sync_list_to_netbox", sync)
    monkeypatch.setattr(nbc, "set_sync_running", lambda *a, **k: None)
    monkeypatch.setattr(nbc, "sync_status_with_results", lambda: {"lists": {"Branch": {
        "timestamp": "2026-10-10T05:00:00Z", "result": {
            "level": "success", "happened": {"summary": "1 object created in NetBox for Branch."},
            "did_not": {"items": []}}}}})
    monkeypatch.setattr("modules.netbox_jobs.threading.Thread", _Inline)
    monkeypatch.setattr("modules.netbox_ops.threading.Thread", _Inline)
    return {"switch": switch, "plan": plan, "sent": sent}


def _post(n, path, data=None):
    r = n["client"].post(path, data=data or {}, headers={"HX-Request": "true"})
    return r, re.sub(r"\s+", " ", r.get_data(as_text=True))


def _job(html):
    return re.search(r'/v2/netbox/job/([0-9a-f]{32})', html).group(1)


class TestThePage:
    def test_it_draws_every_network_under_the_strict_policy(self, networks, nb):
        from modules import csp
        r = networks["client"].get("/v2/netbox")
        html = re.sub(r"\s+", " ", r.get_data(as_text=True))
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert re.search(r'class="nav-item active" href="/v2/netbox\?list=Default" aria-current="page"',
                         html)
        for name in ("Default", "Branch", "Lab-3", "Remote"):
            assert f"<td>{name}</td>" in html, name
        assert "Writes are <strong>off</strong>" in html and "Import every network…" in html

    def test_each_network_counts_its_devices_from_its_own_source(self, networks, nb,
                                                                  monkeypatch):
        """C933: the count came from devices.csv alone, so a NetBox-sourced network read 0
        with Import into NetBox… disabled ("no devices to import"). Branch is a local list (one
        row in its devices.csv); Remote is NetBox-sourced, its devices served from the inventory
        cache (replaced at that edge: no NetBox here), and has no devices.csv at all."""
        from modules.inventory import source_config

        source_config.save("Remote", {"source": "netbox"})
        assert not (networks["dir"] / "lists" / "remote" / "devices.csv").exists()
        served = [{"hostname": f"nb{i}", "ip": f"192.0.2.{20 + i}"} for i in range(3)]
        monkeypatch.setattr("modules.inventory.load_netbox_devices",
                            lambda name, use_cache=True: (list(served), [], {})
                            if name == "Remote" else ([], [], {}))
        html = re.sub(r"\s+", " ", networks["client"].get("/v2/netbox").get_data(as_text=True))
        rows = dict(re.findall(r"<tr> <td>([^<]+)</td> <td>(.*?)</td>.*?</tr>", html))
        assert rows["Branch"] == "1", rows
        assert rows["Remote"] == '3 <span class="muted small">from NetBox</span>', rows
        remote = re.search(r"<tr> <td>Remote</td>.*?</tr>", html).group(0)
        assert "no devices" not in remote and " disabled" not in remote.split("Remove")[0]

        served.clear()   # NetBox's devices not read yet (or none): said as that, not as a CSV's
        html = re.sub(r"\s+", " ", networks["client"].get("/v2/netbox").get_data(as_text=True))
        remote = re.search(r"<tr> <td>Remote</td>.*?</tr>", html).group(0)
        assert 'disabled title="no devices read from NetBox for this network yet"' in remote

    def test_the_sidebar_no_longer_sends_netbox_to_today_s_page(self, networks, nb):
        html = networks["client"].get("/v2/devices").get_data(as_text=True)
        assert 'data-todays-page="netbox"' not in html


class TestImport:
    def test_preview_then_confirm_with_writes_permitted(self, networks, nb):
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Branch"})
        job = _job(card)
        card = re.sub(r"\s+", " ",
                      networks["client"].get(f"/v2/netbox/job/{job}").get_data(as_text=True))
        assert "create dcim/devices r9" in card and "turn NetBox writes on with this confirm" in card
        assert nb["sent"] == [], "the preview writes nothing"
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm", {"permit_writes": "on"})
        assert r.status_code == 200, html
        assert nb["sent"] == ["Branch"] and nb["switch"]["on"] is True
        done = re.sub(r"\s+", " ", networks["client"].get(f"/v2/netbox/job/{job}").get_data(as_text=True))
        assert "1 object created in NetBox for Branch." in done

    def test_writes_off_and_not_permitted_is_refused_and_nothing_written(self, networks, nb):
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Branch"})
        r, html = _post(networks, f"/v2/netbox/job/{_job(card)}/confirm")
        assert r.status_code == 403 and "NetBox writes are off for every network" in html
        assert nb["sent"] == [] and nb["switch"]["on"] is False

    def test_a_moved_plan_is_refused_and_the_switch_stays_off(self, networks, nb):
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Branch"})
        nb["plan"]["value"] = dict(PLAN, creates=PLAN["creates"] * 2, create_count=2)
        r, html = _post(networks, f"/v2/netbox/job/{_job(card)}/confirm", {"permit_writes": "on"})
        assert r.status_code == 409 and nb["sent"] == [] and nb["switch"]["on"] is False

    def test_a_token_is_used_once(self, networks, nb):
        nb["switch"]["on"] = True
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Branch"})
        job = _job(card)
        assert _post(networks, f"/v2/netbox/job/{job}/confirm")[0].status_code == 200
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
        assert r.status_code == 409 and "not one ready to confirm" in html


class TestRefusals:
    @pytest.mark.parametrize("data,said", [
        ({"operation": "sideways", "list": "Branch"}, "no operation"),
        ({"operation": "import", "list": "Nowhere"}, "there is no network"),
    ])
    def test_a_preview_that_cannot_start_is_refused(self, networks, nb, data, said):
        r, html = _post(networks, "/v2/netbox/preview", data)
        assert r.status_code == 404 and said in html

    def test_a_network_with_no_devices_says_so_in_its_card(self, networks, nb):
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Lab-3"})
        assert "has no devices" in card


class TestRemove:
    def test_preview_then_remove_is_recorded_and_drawn(self, networks, nb, monkeypatch):
        import modules.netbox_client as nbc
        nb["switch"]["on"] = True
        deleted = [{"endpoint": "dcim/devices", "id": 7, "name": "r9", "reason": ""}]
        monkeypatch.setattr(nbc, "remove_list_from_netbox", lambda name, **k: {
            "ok": True, "deleted": deleted, "skipped": [], "failed": [], "complete": True,
            "dry_run": bool(k.get("dry_run")), "cascade": PROVEN if k.get("dry_run") else None})
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "remove", "list": "Branch"})
        job = _job(card)
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
        assert r.status_code == 200 and "deleted from NetBox for Branch" in html, html
        page = networks["client"].get("/v2/netbox").get_data(as_text=True)
        assert "1 recorded" in page

    def test_the_preview_names_only_the_choices_its_screen_has(self, networks, nb, monkeypatch):
        """C935: v2's removal preview said "'Just stop tracking' is the other choice", a control
        only today's NetBox dialog draws (its `forget_only`), while v2's card had Remove and
        Close. C954 built v2's own: the card draws Stop tracking instead…, a preview of its own,
        and the removal preview names THAT control; today's still names its button."""
        import modules.netbox_client as nbc
        monkeypatch.setattr(nbc, "remove_list_from_netbox", lambda name, **k: {
            "ok": True, "deleted": [{"endpoint": "dcim/devices", "id": 7, "name": "r9"}],
            "skipped": [], "failed": [], "complete": True, "dry_run": True, "cascade": PROVEN})
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "remove", "list": "Branch"})
        card = re.sub(r"\s+", " ", networks["client"].get(
            f"/v2/netbox/job/{_job(card)}").get_data(as_text=True)).replace("&#39;", "'")
        assert "PERMANENTLY deleted" in card, "the preview is not drawn, so this proves nothing"
        assert "Just stop tracking" not in card and "not on v2 yet" not in card
        assert ("'Stop tracking instead…' is the other choice, previewed on its own: it deletes "
                "nothing, and Mercury forgets what it created for this network, so NetBox keeps "
                "every object (with its nmas-managed tag) and Remove can never act on them "
                "again.") in card
        # The control the words name is on the card: a preview of its own, never a confirm.
        form = re.search(r'<form[^>]*hx-post="/v2/netbox/preview\?list=Default"[^>]*>(.*?)</form>',
                         card).group(1)
        assert '<input type="hidden" name="operation" value="forget">' in form
        assert '<input type="hidden" name="list" value="Branch">' in form
        assert '<span class="op-idle">Stop tracking instead…</span>' in form

        r = networks["client"].post("/netbox/safety/remove/preview", json={"list_name": "Branch"})
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        today = json.dumps(r.get_json())
        assert "'Just stop tracking' is the other choice" in today
        assert "Stop tracking instead" not in today


@pytest.fixture
def tracked(nb, monkeypatch, tmp_path):
    """Branch's created record holding three objects Mercury made, each in a FakeNetBox and
    tagged nmas-managed, and Default's one entry, which Branch's Stop tracking must leave.
    Everything from the route to the record is the real code (`remove_list_from_netbox` too);
    NetBox is the fake, so every request it was sent is counted."""
    import modules.netbox_client as nbc
    from modules import netbox_guard as guard
    from tests.fake_netbox import FakeNetBox

    fake = FakeNetBox()
    monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: fake)
    monkeypatch.setattr(nbc, "_managed_tag_ids", {})
    monkeypatch.setattr(nbc, "_SYNC_STATUS_FILE", str(tmp_path / "netbox_sync_status.json"))
    tag = [{"slug": guard.MANAGED_TAG_SLUG, "name": guard.MANAGED_TAG}]
    objs = [("dcim/devices", fake.seed("dcim/devices", {"name": "r9", "tags": tag})),
            ("dcim/interfaces", fake.seed("dcim/interfaces", {"name": "Gi1", "tags": tag})),
            ("ipam/ip-addresses", fake.seed("ipam/ip-addresses",
                                            {"name": "192.0.2.9/24", "tags": tag}))]
    for ep, o in objs:
        guard.record_created("Branch", ep, o["id"], o["name"])
    other = fake.seed("dcim/devices", {"name": "x1", "tags": tag})
    guard.record_created("Default", "dcim/devices", other["id"], "x1")
    return {"fake": fake, "objs": objs, "other": other}


def _held(network):
    from modules import netbox_guard as guard
    return sorted((ep, e["id"]) for ep, rows in guard.get_created(network).items() for e in rows)


def _sent_nothing(fake):
    return not (fake.deletes or fake.posts or fake.patches)


def _forget_card(networks):
    _r, card = _post(networks, "/v2/netbox/preview", {"operation": "forget", "list": "Branch"})
    job = _job(card)
    html = networks["client"].get(f"/v2/netbox/job/{job}").get_data(as_text=True)
    return job, re.sub(r"\s+", " ", html).replace("&#39;", "'")


class TestStopTracking:
    """C954: v2's Stop tracking, the Remove card's second choice. It deletes nothing in NetBox
    and has Mercury forget what it created for the network: previewed from Mercury's created
    record, confirmed by a verified person by the hash of exactly those entries, done through
    today's one path (`netbox_ops.remove`'s `forget_only`), recorded in the removal record."""

    def test_the_preview_says_what_it_does_with_its_counts(self, networks, nb, tracked):
        before = _held("Branch")
        job, card = _forget_card(networks)
        assert "Stop tracking in NetBox: Branch" in card
        assert ("Deletes nothing in NetBox. Mercury forgets 3 object(s) it created for Branch, "
                "which keep their nmas-managed tag in NetBox and which Remove can never act on "
                "again.") in card
        for ep, o in tracked["objs"]:
            assert f"<li>forget {ep} #{o['id']} {o['name']}</li>" in card, (ep, o)
        assert ("<dt>By type</dt><dd>dcim/devices 1, dcim/interfaces 1, "
                "ipam/ip-addresses 1</dd>") in card
        assert "<dt>Deletes in NetBox</dt><dd>0</dd>" in card
        assert ("Where the data survives: NetBox keeps every object. Mercury's created-object "
                "record (netbox_created_ids.json) drops these 3 entries") in card
        assert "x1" not in card, "another network's entry is not this network's to forget"
        # Its confirm: one button, no writes switch (nothing is sent to NetBox).
        assert '<span class="op-idle">Stop tracking</span>' in card
        assert "turn NetBox writes on with this confirm" not in card
        assert f'hx-post="/v2/netbox/job/{job}/confirm?list=Default"' in card
        # A preview changes nothing anywhere.
        assert _held("Branch") == before and _sent_nothing(tracked["fake"])

    def test_a_long_list_leads_with_its_count_and_collapses(self, networks, nb, tracked):
        """CLAUDE.md, large fleets: 3 lines are drawn open; 30 collapse under their count."""
        from modules import netbox_guard as guard
        _job_id, card = _forget_card(networks)
        assert "<details" not in card.split("What Mercury forgets")[1].split("By type")[0]
        for i in range(27):
            guard.record_created("Branch", "dcim/interfaces", 500 + i, f"Gi{i + 2}")
        _job_id, card = _forget_card(networks)
        assert ('<details class="set-details" data-keep="preview-program-netbox_forget-Branch">'
                '<summary class="small">30 record entr(ies) forgotten: show each</summary>') in card
        assert "Mercury forgets 30 object(s)" in card

    def test_confirm_forgets_exactly_those_and_deletes_nothing(self, networks, nb, tracked):
        from modules import netbox_guard as guard
        from tests.conftest import TEST_PERSON
        job, _card = _forget_card(networks)
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
        html = html.replace("&#39;", "'")
        assert r.status_code == 200, html
        assert ("Mercury forgot 3 object(s) it created for Branch. Nothing was deleted from "
                "NetBox") in html
        assert _held("Branch") == [], "Branch's entries are forgotten"
        assert _held("Default") == [("dcim/devices", tracked["other"]["id"])], \
            "another network's record is untouched"
        # Nothing reached NetBox: the fake recorded no DELETE (nor any write), every object is
        # still there, and the master switch was neither needed nor turned on.
        assert tracked["fake"].deletes == [] and _sent_nothing(tracked["fake"])
        for ep, o in tracked["objs"]:
            assert o in tracked["fake"].store[ep]
        assert nb["switch"]["on"] is False
        # The removal record names who, and each entry forgotten.
        row = guard.read_removals("Branch")["rows"][0]
        assert row["forget_only"] is True and row["ok"] is True and row["deleted"] == []
        assert row["actor"] == TEST_PERSON
        assert sorted((o["endpoint"], o["id"]) for o in row["forgotten"]) == \
            sorted((ep, o["id"]) for ep, o in tracked["objs"])
        page = networks["client"].get("/v2/netbox").get_data(as_text=True)
        assert "1 recorded" in page

    def test_a_record_that_moved_is_refused_and_nothing_forgotten(self, networks, nb, tracked):
        from modules import netbox_guard as guard
        job, _card = _forget_card(networks)
        guard.record_created("Branch", "dcim/interfaces", 99, "Gi9")   # an import, meanwhile
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
        html = html.replace("&#39;", "'")
        assert r.status_code == 409, html
        assert ("Mercury's record of what it created for Branch changed since the preview: the "
                "preview's entries hashed ") in html
        assert "the record's 4 entries now hash " in html and ": preview again. Nothing was " \
            "forgotten, and nothing was sent to NetBox." in html
        assert len(_held("Branch")) == 4, "nothing was forgotten"
        assert _sent_nothing(tracked["fake"])
        assert guard.read_removals("Branch")["rows"] == []

    def test_only_the_confirmed_entries_are_forgotten(self, networks, nb, tracked):
        """The forget is handed the confirmed set, so an entry recorded after the check is kept
        (the hash check and the forget share one writer's hold; this is the narrower seam)."""
        from modules import netbox_ops
        (ep0, o0), (ep1, o1), (ep2, o2) = tracked["objs"]
        out = netbox_ops.remove("Branch", {"forget_only": True}, "ops@example.com",
                                only=[(ep0, o0["id"]), (ep1, o1["id"])])
        assert out["ok"] and sorted((o["endpoint"], o["id"]) for o in out["forgotten"]) == \
            sorted([(ep0, o0["id"]), (ep1, o1["id"])])
        assert _held("Branch") == [(ep2, o2["id"])]

    def test_a_non_person_is_refused(self, networks, nb, tracked, monkeypatch):
        from modules import identity
        job, _card = _forget_card(networks)
        svc = identity.Identity(actor="service:abc.access", kind="service",
                                service_id="abc.access", verified=True, outcome="ok",
                                peer="198.51.100.7", peer_trusted=True, header_present=True)
        monkeypatch.setattr(identity, "identify", lambda _r: svc)
        r = networks["client"].post(f"/v2/netbox/job/{job}/confirm",
                                    headers={"HX-Request": "true"})
        assert r.status_code == 403, r.get_data(as_text=True)[:400]
        assert len(_held("Branch")) == 3 and _sent_nothing(tracked["fake"])

    def test_a_confirm_is_used_once(self, networks, nb, tracked):
        job, _card = _forget_card(networks)
        assert _post(networks, f"/v2/netbox/job/{job}/confirm")[0].status_code == 200
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
        assert r.status_code == 409 and "not one ready to confirm" in html

    def test_another_writer_on_the_network_refuses_it(self, networks, nb, tracked):
        """One NetBox writer per network (R21): an import holding Branch refuses Stop tracking,
        naming it, and nothing is forgotten."""
        import _thread
        import threading

        from modules import netbox_guard as guard
        job, _card = _forget_card(networks)
        holding, release, done = threading.Event(), threading.Event(), threading.Event()

        def hold():
            try:
                with guard.list_writer("Branch", "list import", "someone@example.com"):
                    holding.set()
                    release.wait(10)
            finally:
                done.set()
        # The fixture makes threading.Thread run inline (`_Inline`); this holder must not.
        _thread.start_new_thread(hold, ())
        try:
            assert holding.wait(10)
            r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
        finally:
            release.set()
            done.wait(10)
        assert r.status_code == 409, html
        assert "list import by someone@example.com is writing Branch" in html
        assert len(_held("Branch")) == 3

    def test_nothing_recorded_offers_nothing_to_confirm(self, networks, nb, tracked):
        from modules import netbox_guard as guard
        guard.forget_created("Branch")
        _job_id, card = _forget_card(networks)
        assert ("Mercury's record holds nothing it created in NetBox for Branch: there is "
                "nothing to forget.") in card
        assert "Nothing to confirm: Mercury's record holds nothing for Branch." in card
        assert '<span class="op-idle">Stop tracking</span>' not in card


REMOVE_BUTTON = '<span class="op-idle">Remove</span>'


def _remove_card(networks):
    """A removal previewed through the route: the job runs inline, so its card holds the preview
    (whitespace collapsed), with the job's id read from the store (a card that offers no
    confirm carries no job address)."""
    from modules import netbox_jobs
    _r, card = _post(networks, "/v2/netbox/preview", {"operation": "remove", "list": "Branch"})
    jobs = [n[:-5] for n in os.listdir(netbox_jobs._dir())
            if netbox_jobs.read(n[:-5]).get("operation") == "remove"]
    newest = max(jobs, key=lambda j: os.path.getmtime(netbox_jobs._path(j)))
    return newest, card.replace("&#39;", "'")


class TestRemoveNeedsWhatTheDeletesTake:
    """B9 (C932, raised to B by the operator in W2): Remove from NetBox was offered over a
    preview whose cascade read said `not_reached` (the raw token drawn): what the deletes take
    with them could not be established, and the card still drew Remove, as it drew it on
    `pv.confirm.may` alone. Through the real removal dry run and cascade query against the fake
    NetBox (`tracked`): a type whose cascade is measured offers Remove; one that is not
    (a prefix, `netbox_cascade.UNMEASURED`) offers none, says why in words naming the comparison
    and its operands, offers Read again, and a confirm posted without the card is refused."""

    def _prefix(self, tracked):
        from modules import netbox_guard as guard
        tag = [{"slug": guard.MANAGED_TAG_SLUG, "name": guard.MANAGED_TAG}]
        pfx = tracked["fake"].seed("ipam/prefixes", {"prefix": "192.0.2.0/24",
                                                     "name": "192.0.2.0/24", "tags": tag})
        guard.record_created("Branch", "ipam/prefixes", pfx["id"], "192.0.2.0/24")
        return pfx

    def test_a_reached_cascade_offers_remove_and_it_runs(self, networks, nb, tracked):
        job, card = _remove_card(networks)
        assert "PERMANENTLY deleted" in card, "the preview is not drawn, so this proves nothing"
        assert REMOVE_BUTTON in card and "Remove is not offered" not in card
        assert "asked: nothing beyond the list above goes with them" in card
        nb["switch"]["on"] = True
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
        assert r.status_code == 200, html
        assert sorted(tracked["fake"].deletes) == sorted((ep, o["id"]) for ep, o in tracked["objs"])

    def test_a_cascade_not_reached_offers_no_remove_and_says_why_in_words(self, networks, nb,
                                                                           tracked):
        self._prefix(tracked)
        job, card = _remove_card(networks)
        assert "PERMANENTLY deleted" in card, "the preview is not drawn, so this proves nothing"
        assert REMOVE_BUTTON not in card, "Remove offered over a cascade nobody established"
        assert "not_reached" not in card and "not_applicable" not in card, "a raw token drawn"
        assert "not established" in card
        # The comparison and its operands: every delete's consequence must be established, how
        # many deletes, how many could not be, and why.
        assert ("Remove is not offered:</strong> what NetBox's database takes with each of the "
                "4 delete(s) must be established, and 1 answer(s) could not be: ipam/prefixes: "
                "what a delete takes with it has not been measured on this NetBox. Not "
                "established is not the same as nothing.") in card, card
        again = re.search(r'<div class="notice notice-warn set-result".*?</div></div>', card).group(0)
        # The page's network on the address (C1022); the network read again is the form's.
        assert 'hx-post="/v2/netbox/preview?list=Default"' in again
        assert '<input type="hidden" name="operation" value="remove">' in again
        assert '<input type="hidden" name="list" value="Branch">' in again
        assert '<span class="op-idle">Read again</span>' in again
        assert '<span class="op-idle">Stop tracking instead…</span>' in card, \
            "the choice that deletes nothing stays"
        # A confirm posted without the card is refused, naming why, and nothing is deleted.
        nb["switch"]["on"] = True
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
        assert r.status_code == 409, html
        assert "that preview cannot be confirmed: what NetBox's database takes" in html.replace(
            "&#39;", "'")
        assert tracked["fake"].deletes == []

    def test_read_again_previews_anew(self, networks, nb, tracked):
        """Read again is a new preview: once the cause has gone (here Mercury no longer records
        the prefix), it offers Remove."""
        from modules import netbox_guard as guard
        pfx = self._prefix(tracked)
        _job, card = _remove_card(networks)
        assert REMOVE_BUTTON not in card
        guard.forget_created("Branch", "ipam/prefixes", pfx["id"])
        _job, card = _remove_card(networks)
        assert REMOVE_BUTTON in card and "Remove is not offered" not in card

    def test_an_unreadable_object_offers_no_remove_either(self, networks, nb, tracked,
                                                           monkeypatch):
        """C932 as it was registered: a preview that says "cannot be confirmed" because a
        recorded object could not be read drew Remove."""
        import modules.netbox_client as nbc
        monkeypatch.setattr(nbc, "remove_list_from_netbox", lambda name, **k: {
            "ok": True, "list": name, "skipped": [], "complete": True, "dry_run": True,
            "deleted": [{"endpoint": "dcim/devices", "id": 7, "name": "r9"}], "cascade": PROVEN,
            "failed": [{"endpoint": "dcim/interfaces", "id": 8, "name": "Gi1",
                        "reason": "NetBox answered 500"}]})
        _job, card = _remove_card(networks)
        assert "This removal cannot be confirmed" in card
        assert REMOVE_BUTTON not in card
        assert ("Remove is not offered:</strong> every object Mercury recorded for Branch must "
                "be read from NetBox, and 1 could not be (not gone, and not forgotten).") in card


@pytest.fixture
def real_import(networks, monkeypatch, tmp_path):
    """Branch's r9 with a committed golden, and NetBox the fake: the import is the real one,
    from the route through `netbox_jobs`, `netbox_ops` and `sync_list_to_netbox` to the fake's
    writes, its threads run inline. The person is the one the app's identity names."""
    import modules.netbox_client as nbc
    from modules import device, netbox_guard
    from modules.nsot import repo as R
    from tests.fake_netbox import FakeNetBox

    cfg = open(os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet", "r2.cfg"),
               encoding="utf-8").read().replace(
        "hostname r2", "hostname r9")
    device.write_devices_csv([{"hostname": "r9", "ip": "192.0.2.9"}],
                             str(networks["dir"] / "lists" / "branch" / "devices.csv"))
    assert R.save_golden("Branch", [R.GoldenItem("r9", cfg, "192.0.2.9", platform="cisco_ios")],
                         source="capture", actor="test@example.invalid", allow_new=True)["ok"]
    fake = FakeNetBox()
    # The custom field the import sets on a device, already defined, as on a NetBox that has
    # been imported into before: a preview of an import that would CREATE it marks it ensured
    # in the process (`_custom_fields_ensured`), so the confirm's recomputed plan lacks the
    # create and is refused as moved (found writing this test; registered, not fixed here).
    fake.seed("extras/custom-fields", {"name": "os_version"})
    monkeypatch.setattr(nbc, "_custom_fields_ensured", set())
    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://192.0.2.8", "token": "t"})
    monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: fake)
    monkeypatch.setattr(nbc, "_managed_tag_ids", {})
    monkeypatch.setattr(nbc, "_SYNC_STATUS_FILE", str(tmp_path / "netbox_sync_status.json"))
    for name in ("_CREATED_IDS_FILE", "_MODIFIED_FILE", "_ADOPTED_FILE", "_REMOVALS_FILE"):
        monkeypatch.setattr(netbox_guard, name, str(tmp_path / f"{name.strip('_').lower()}"))
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    monkeypatch.setattr("modules.netbox_jobs.threading.Thread", _Inline)
    monkeypatch.setattr("modules.netbox_ops.threading.Thread", _Inline)
    return fake


def _now_iso():
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _timeline(networks, network):
    html = networks["client"].get(f"/v2/history/timeline?list={network}&since=").get_data(
        as_text=True)
    return re.sub(r"\s+", " ", html)


class TestTheImportIsInHistory:
    """B8 (W2): the operator's import (9 of 9 at 22:53:18Z) was on no History timeline; the
    timeline had no NetBox source at all. An import confirmed on the NetBox page is now a row of
    its network's timeline, read from the job's own record: who confirmed it, when, and its
    counts in the NetBox page's own words; never on another network's. A Remove and a Stop
    tracking are rows too, from the removal record."""

    def test_an_import_is_on_its_network_s_timeline_and_no_other(self, networks, real_import):
        from modules import history_sources as HS
        from modules import netbox_jobs
        from modules.nsot import listref

        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import",
                                                          "list": "Branch"})
        job = _job(card)
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
        assert r.status_code == 200, html
        assert real_import.posts, "the import wrote nothing, so this proves nothing"
        done = netbox_jobs.read(job)
        assert done["state"] == "imported", done
        assert done.get("actor") == "test-person@example.invalid", done
        assert "previewed_by" in done, done
        said = done["results"]["Branch"]["happened"]["summary"]
        assert said.startswith("1 of 1 device(s) imported into NetBox (1 created"), said

        rows = [e for e in HS.timeline(listref.resolve("Branch"))["events"]
                if e["kind"] == "netbox"]
        assert len(rows) == 1, rows
        e = rows[0]
        assert e["what"] == "NetBox import: " + said
        assert e["who"] == "test-person@example.invalid" and e["at"] == done["at"]
        assert e["outcome"] == "success" and ("Started", done["started_at"]) in e["record"]

        page = _timeline(networks, "Branch")
        assert "NetBox import: " + said in page.replace("&#39;", "'"), page
        assert 'data-kind="netbox"' in page
        other = _timeline(networks, "Default")
        assert 'data-kind="netbox"' not in other and "NetBox import" not in other

    def test_the_kind_filter_keeps_it_and_leaves_it_out(self, networks, real_import):
        from modules import history_sources as HS
        from modules.nsot import listref

        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import",
                                                          "list": "Branch"})
        assert _post(networks, f"/v2/netbox/job/{_job(card)}/confirm")[0].status_code == 200
        ref = listref.resolve("Branch")
        kinds = {e["kind"] for e in HS.timeline(ref, kinds=["netbox"])["events"]}
        assert kinds == {"netbox"}
        assert all(e["kind"] != "netbox" for e in HS.timeline(ref, kinds=["commits"])["events"])

    def test_a_record_from_before_the_confirmer_was_named_says_so(self, networks, real_import):
        """The operator's own import (W2, 22:53:18Z) was recorded before the job named who
        confirmed it: its `actor` is who previewed it, and the row says that, not that they
        imported it."""
        from modules import history_sources as HS
        from modules import netbox_jobs
        from modules.nsot import listref

        os.makedirs(netbox_jobs._dir(), exist_ok=True)
        with open(netbox_jobs._path("a" * 32), "w", encoding="utf-8") as fh:
            json.dump({"operation": "import", "list": "Branch", "state": "imported",
                       "outcome": "done", "actor": "unauthenticated", "at": _now_iso(),
                       "results": {}}, fh)
        rows = [e for e in HS.timeline(listref.resolve("Branch"))["events"]
                if e["kind"] == "netbox"]
        assert [e["who"] for e in rows] == [
            "unauthenticated (who previewed it: this record predates naming who confirmed it)"]
        assert rows[0]["what"] == "NetBox import: it ended and recorded no result"

    def test_a_removal_and_a_stop_tracking_are_rows_too(self, networks, real_import):
        from modules import history_sources as HS
        from modules import netbox_guard as guard
        from modules.nsot import listref

        guard.record_removal("Branch", "alex@example.invalid", {
            "ok": True, "complete": True, "deleted": [{"endpoint": "dcim/devices", "id": 7,
                                                       "name": "r9"}]})
        guard.record_removal("Branch", "sam@example.invalid", {
            "ok": True, "forgotten": [{"endpoint": "dcim/sites", "id": 3, "name": "branch"}]},
            forget_only=True)
        guard.record_removal("Default", "pat@example.invalid", {"ok": True, "deleted": []})
        rows = [(e["who"], e["what"]) for e in HS.timeline(listref.resolve("Branch"))["events"]
                if e["kind"] == "netbox"]
        assert ("alex@example.invalid",
                "NetBox removal: 1 object(s) deleted from NetBox for Branch.") in rows, rows
        assert any(who == "sam@example.invalid" and what.startswith(
            "NetBox: stopped tracking: Mercury forgot 1 object(s)") for who, what in rows), rows
        assert len(rows) == 2, "Default's removal is not Branch's"
