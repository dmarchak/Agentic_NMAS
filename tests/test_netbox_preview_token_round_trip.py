"""The NetBox import's confirmation survives the trip: a REAL preview's token,
driven into the REAL confirm (2026-09-28).

The operator: "This confirmation has expired or was already used", repeatedly,
5 seconds after a preview. Measured on the host, the token was issued and
never found: the import previews wrapped their whole response in
`outbound.mask_payload`, which masks by KEY, and `token` is a secret key name.
So since C77's sweep every import preview sent `<redacted:token>`, and the
import could not be confirmed at all. Each half was tested alone (the preview
for secrets, the apply for tokens); nothing drove one into the other, the
`/deploy/plan` -> `/deploy/apply` seam lesson again.

Today's NetBox tab, whose routes this drove, left at 7.8 (2026-10-17). v2's NetBox
page keeps the token on the server, in the preview job's record, and masks the
preview it draws (`netbox_jobs.start_preview`): the same seam, so it is driven the
same way, through v2's preview and confirm routes (tests/test_netbox_v2.py's `nb`).
"""

import re

import pytest

from tests.test_netbox_v2 import _job, _post, nb  # noqa: F401 (nb: the fixture)
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

PLAN = {"creates": [{"endpoint": "dcim/devices", "name": "r9", "id": -2, "payload": {}}],
        "updates": [], "deletes": [], "create_count": 1, "update_count": 0,
        "delete_count": 0, "creates_by_type": {"dcim/devices": 1}, "updates_by_type": {},
        "deletes_by_type": {}}


@pytest.fixture
def every_network(nb, monkeypatch):
    """The all-networks import's sync, faked at the same edge as one network's."""
    import modules.netbox_client as nbc

    def sync_all(items, dry_run=False, **k):
        if not dry_run:
            nb["sent"].append("every network")
        return {"plan": nb["plan"]["value"]}
    monkeypatch.setattr(nbc, "sync_all_lists_to_netbox", sync_all)
    return nb


@pytest.mark.parametrize("op", ["import", "import_all"])
def test_the_token_a_preview_holds_confirms_the_import(networks, every_network, op):
    from modules import netbox_jobs

    every_network["switch"]["on"] = True
    _r, card = _post(networks, "/v2/netbox/preview", {"operation": op, "list": "Branch"})
    job = _job(card)
    held = netbox_jobs.read(job)
    assert held["state"] == "previewed", held
    assert held["token"] and not held["token"].startswith("<redacted"), \
        "the confirmation was masked where it is kept"
    r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
    assert r.status_code == 200, html
    assert every_network["sent"] == ["Branch" if op == "import" else "every network"]
    assert netbox_jobs.read(job)["state"] == "imported"


def test_the_preview_is_still_masked(networks, nb, monkeypatch):
    """The fix moved the mask, it did not remove it: a planted secret in the
    preview is masked in the card drawn; only the kept token passes intact."""
    import modules.preview_confirm as pc
    from modules import netbox_jobs

    real = pc.netbox_import_preview

    def planted(d, confirm, **k):
        p = real(d, confirm, **k)
        p["what"]["summary"] += " snmp-server community PlantedC0mmunity RO"
        return p

    monkeypatch.setattr(pc, "netbox_import_preview", planted)
    _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Branch"})
    job = _job(card)
    card = re.sub(r"\s+", " ", networks["client"].get(f"/v2/netbox/job/{job}").get_data(
        as_text=True))
    assert "snmp-server community" in card, "the planted line is not drawn, so this proves nothing"
    assert "PlantedC0mmunity" not in card
    assert "PlantedC0mmunity" not in str(netbox_jobs.read(job)["preview"])
    assert not netbox_jobs.read(job)["token"].startswith("<redacted")
