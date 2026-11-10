"""A heal's change record, downloaded (C2773; board H, artboards C and K, "Download the change
record (.md)"): the markdown `modules/heal/change_record.py` made, kept in the incident's ``act``
row of the step log, served by `routes/heal_proposal_v2.change_record_md` and linked from
History's heal row (`history_sources.heal`'s ``heal_record``, `templates/v2/_timeline.html`).
Through the real app on test_heal_decide's lab, every row written by the code's own writers (the
act, the decision, `steplog.record_act` with `change_record.build_action`'s record). No device,
no network.

- **Served:** the exact markdown the step log keeps, as text/markdown with an attachment
  filename naming the device and the incident; for a heal to intent and for an action (H23).
- **No record, no download:** a dry run and a heal refused before its program are a 404 naming
  why, and their History row draws no link.
- **Unknown:** an incident the step log does not hold, an id out of shape, and a network Mercury
  does not hold are each a 404 naming it.
- **Masked:** a secret-shaped line in a stored record (a row written unmasked) never comes back.
- **The row:** History's heal row draws the link only when the record was made.
"""

import json
import os

import pytest

from tests.test_heal_act import FakeAct, act, decided
from tests.test_heal_action_records import act_result, bounce_decision
from tests.test_heal_decide import GOLDEN, ROUTE4, ROUTE6, T0
from tests.test_heal_decide import lab  # noqa: F401  (the fixture, named by each test below)
from tests.test_heal_mark_and_held import _event, _timeline, dry_run
from tests.test_heal_triggers import _Lazy
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

A, SL = _Lazy("act"), _Lazy("steplog")
SECRET = "snmp-server community S3cretRO RO"
INCIDENT = "hi-0c41e70a5b2d"
LINK = "Download the change record (.md)"


@pytest.fixture(autouse=True)
def no_host_addresses(monkeypatch):
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])


@pytest.fixture
def client(lab):
    import app as APP

    APP.app.config["TESTING"] = True
    return APP.app.test_client()


def _url(incident, network="Default"):
    return f"/v2/network/{network}/heal/incident/{incident}/change-record.md"


def _kept(incident):
    """The change record the step log's act row keeps for *incident*, as written."""
    (row,) = [r for r in SL.read("Default")["rows"]
              if r.get("row") == "act" and r.get("incident") == incident]
    return row["records"]["change_record"]


def _action(outcome="bounced"):
    """An action's decision and act rows as the act writes them, its record made by
    `change_record.build_action` over that decision and result."""
    from modules.heal import change_record

    d = bounce_decision(incident=INCIDENT)
    result = act_result(outcome)
    result["records"]["change_record"] = change_record.build_action(
        "Default", d, result, at="2026-11-03T10:00:05Z")
    assert result["records"]["change_record"]["state"] == "made"
    SL.record_decision("Default", d, T0)
    SL.record_act("Default", d, result, by="self-healing (policy set by op)", now=T0 + 5)
    return d


class TestServed:
    @pytest.mark.parametrize("route", [ROUTE4, ROUTE6])
    def test_a_heal_s_exact_stored_record_with_its_filename(self, client, route):
        got, _src, d = act(GOLDEN + route)
        assert got["outcome"] == "healed", got["words"]
        kept = _kept(d["incident"])
        assert kept["state"] == "made"
        before = SL.read("Default")
        r = client.get(_url(d["incident"]))
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.mimetype == "text/markdown"
        assert r.get_data(as_text=True) == kept["markdown"], "the record exactly as kept"
        assert r.headers["Content-Disposition"] == (
            f'attachment; filename="change-record-edge-b-{d["incident"]}.md"')
        assert SL.read("Default") == before, "the download leaves the step log as it was"

    def test_an_action_s_record_is_served_too(self, client):
        d = _action()
        before = SL.read("Default")
        r = client.get(_url(INCIDENT))
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_data(as_text=True) == _kept(INCIDENT)["markdown"]
        assert r.headers["Content-Disposition"] == (
            f'attachment; filename="change-record-{d["device"]}-{INCIDENT}.md"')
        assert SL.read("Default") == before, "the download leaves the step log as it was"

    def test_the_download_writes_nothing(self, client, lab):
        _action()

        def tree():
            return sorted((p, os.path.getsize(os.path.join(p, f)))
                          for p, _d, fs in os.walk(lab) for f in fs)

        before = tree()
        assert client.get(_url(INCIDENT)).status_code == 200
        assert client.get(_url(INCIDENT, network="Nowhere")).status_code == 404
        assert tree() == before, "a read writes nothing and creates no network"


class TestNoRecordNoDownload:
    def test_a_dry_run_is_a_404_naming_why(self, client):
        d = dry_run()
        before = SL.read("Default")
        r = client.get(_url(d["incident"]))
        text = r.get_data(as_text=True)
        assert r.status_code == 404 and "has no change record" in text and "dry run" in text
        assert SL.read("Default") == before, "a refused download writes nothing"

    def test_a_heal_refused_before_its_program_is_a_404_with_its_words(self, client):
        d = decided(GOLDEN + ROUTE4)
        got = A.act_one("Default", d["id"], now=T0 + 5,
                        sources=FakeAct(GOLDEN + ROUTE4, read_error="timed out"))
        assert got["outcome"] == "refused"
        before = SL.read("Default")
        r = client.get(_url(d["incident"]))
        text = r.get_data(as_text=True)
        assert r.status_code == 404 and "has no change record" in text
        assert "refused before its program was computed" in text
        assert SL.read("Default") == before, "a refused download writes nothing"


class TestUnknown:
    def test_an_incident_the_step_log_does_not_hold(self, client):
        act(GOLDEN + ROUTE4)
        before = SL.read("Default")
        r = client.get(_url("hi-000000000000"))
        assert r.status_code == 404
        assert "holds no incident hi-000000000000" in r.get_data(as_text=True)
        assert SL.read("Default") == before, "a refused download writes nothing"

    def test_an_id_out_of_shape(self, client):
        before = SL.read("Default")
        r = client.get(_url("hd-1"))
        assert r.status_code == 404 and "'hd-1' is no self-healing incident id" in \
            r.get_data(as_text=True)
        assert SL.read("Default") == before, "a refused download writes nothing"

    def test_a_network_mercury_does_not_hold(self, client):
        """Refused before the handler by the app's list guard (routes/list_param.py), naming
        it; the handler's own check stands behind it."""
        before = SL.read("Default")
        r = client.get(_url(INCIDENT, network="Nowhere"))
        assert r.status_code == 404 and "no device list named 'Nowhere'" in \
            r.get_data(as_text=True)
        assert SL.read("Default") == before, "a refused download writes nothing"


class TestMasked:
    def test_a_secret_in_a_stored_record_never_comes_back(self, client):
        from modules.heal import steplog

        markdown = f"# Change record: edge-b\n\n## Implementation\n\n    {SECRET}\n"
        os.makedirs(os.path.dirname(steplog._path("Default")), exist_ok=True)
        with open(steplog._path("Default"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"row": "act", "incident": INCIDENT, "device": "edge-b",
                                 "decision": "hd-1", "outcome": "healed", "mode": "auto",
                                 "at": "2026-11-03T10:00:00Z", "epoch": T0, "steps": [],
                                 "records": {"change_record": {
                                     "state": "made", "markdown": markdown,
                                     "words": "made"}}}) + "\n")
        r = client.get(_url(INCIDENT))
        text = r.get_data(as_text=True)
        assert r.status_code == 200 and "## Implementation" in text
        assert "S3cretRO" not in text, "masked again on the way out"
        with open(steplog._path("Default"), encoding="utf-8") as fh:
            assert "S3cretRO" in fh.read(), \
                "masked on the way out only: the step log as it was written is left unchanged"


class TestTheRow:
    def test_a_healed_row_draws_the_link(self, lab):
        _got, _src, d = act(GOLDEN + ROUTE4)
        e = _event()
        assert e["heal_record"] == {"list": "Default", "incident": d["incident"]}
        html = _timeline(e)
        assert LINK in html and f'href="{_url(d["incident"])}"' in html

    def test_an_action_s_row_draws_the_link(self, lab):
        _action()
        e = _event()
        assert e["heal_record"] == {"list": "Default", "incident": INCIDENT}
        html = _timeline(e)
        assert LINK in html and f'href="{_url(INCIDENT)}"' in html

    def test_a_dry_run_row_draws_none(self, lab):
        dry_run()
        e = _event()
        assert "heal_record" not in e and LINK not in _timeline(e)

    def test_a_refused_heal_s_row_draws_none(self, lab):
        d = decided(GOLDEN + ROUTE4)
        A.act_one("Default", d["id"], now=T0 + 5,
                  sources=FakeAct(GOLDEN + ROUTE4, read_error="timed out"))
        e = _event()
        assert "heal_record" not in e and LINK not in _timeline(e)
