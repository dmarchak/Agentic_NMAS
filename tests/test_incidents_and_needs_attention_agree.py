"""Needs attention and Troubleshooting › Incidents agree, from tonight's real stores (C3699,
C3700, C3701; the operator, 2026-11-14: "Fix so both pages derive from one source: an open
incident that needs a person ⇔ a Needs attention row linking to it (acknowledged ones shown as
acknowledged on both). Add a test of that invariant in both directions, from tonight's real
stores").

**The stores:** tests/fixtures/incidents_agree/default-2026-11-14T1725Z.json, Default's heal
incidents, step log and decisions and the alerts reader's firing instances as the NMAS host held
them at 2026-11-14 17:25 UTC, read by Mercury's own reads (the capture script keeps ids, states,
times, keys and Mercury's words; every configuration line left out, masked by `redact_text`, a
person's address and each lab address replaced). Two disagreements were in them:
- r7's two lost streams (101, 102) fired on Needs attention with no open incident: their
  incident `hi-126fa0771352` was closed at can't fix four seconds after it opened (the rule
  before C2813), and the alert, once an episode, never sighted it again (C3699);
- r6's `hi-22823de626cc` read "needs a person" on Incidents for six days, its record closed
  "withdrawn: r6 read back at its golden" (C3700), with no Needs attention row.

**The invariant, both directions** (`agreement`): every open incident the Incidents list says
needs a person is linked by a Needs attention row (one row of its own if no other names it),
and every row linking an incident links one that is open and needs a person. Needs attention's
rows here are the two sources that link incidents, as Mercury composes them: self-healing's
(`heal_source` over the captured decisions and step log) and the lost stream's row as Grafana's
source drew it tonight (its action and devices as read from the host), with the two linking
steps and `_incidents_agree`. **What it cannot see, stated:** the rest of Needs attention's
sources link no incident (they are not read here), and an acknowledgement of a Grafana row is
keyed on the alert, not the incident.
"""
import json
import os

import pytest

from tests.test_heal_policy import confirm
from tests.test_sdn_connections import networks  # noqa: F401  (a fixture)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "incidents_agree",
                       "default-2026-11-14T1725Z.json")
NET = "Default"
#: The lost streams' row as Grafana's source drew it on the host at 17:20 UTC (its id, action
#: and devices, from Needs attention's own answer; tonight's only firing alerts).
STREAM_ROW = {"id": "grafana:incident:nmas-tel-r7-101:2026-11-08T21:30:50Z", "source": "grafana",
              "kind": "incident", "level": "warning", "devices": ["r7"],
              "networks": {"r7": [NET]},
              "what": "r7: 2 telemetry streams lost (101, 102)",
              "action": {"device": "r7", "open": "resubscribe", "subs": ["101", "102"],
                         "label": "Re-subscribe r7's telemetry (101, 102)"}}
OLD_R7, R6, R4 = "hi-126fa0771352", "hi-22823de626cc", "hi-431eaa1fa107"


def load() -> dict:
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def stores(networks, monkeypatch):  # noqa: F811
    """Default with self-healing in dry run, tonight's stores in place: the incidents in their
    own store's file (the triggers write it), the step log and decisions through their reads."""
    from modules import attention as A
    from modules import neighbours as N
    from modules.heal import decisions as HD
    from modules.heal import incidents, steplog
    from modules.heal import triggers as T
    from modules.nsot import blast_radius as BR

    fx = load()
    confirm(NET, heal_mode="dry_run")
    devices = sorted({i["device"] for i in fx["incidents"] if i.get("device")})
    monkeypatch.setattr(A, "_device_networks", lambda: {d: [NET] for d in devices})
    monkeypatch.setattr(A, "_inventory", lambda: ((set(devices), {}), ""))
    monkeypatch.setattr(N, "committed_intents", lambda repo: ({}, ""))
    monkeypatch.setattr(BR, "host_networks", lambda: [])
    os.makedirs(os.path.dirname(incidents.path(NET)), exist_ok=True)
    with open(incidents.path(NET), "w", encoding="utf-8") as fh:
        json.dump({"version": incidents.VERSION, "incidents": fx["incidents"]}, fh)
    monkeypatch.setattr(steplog, "incidents", lambda net: {
        "state": "ok", "error": "", "entries": fx["steplog"] if net == NET else []})
    monkeypatch.setattr(HD, "decisions", lambda net: fx["decisions"] if net == NET else [])
    # The alerts' episodes as the host's cursor held them: both seen when they began.
    from modules.evidence_pack import alert_key, firing
    seen = sorted(alert_key(i) for i in firing(fx["alerts"]))
    T._move(lambda d: d.setdefault("seen", {}).__setitem__("grafana-alerts", seen))
    return fx


def listed() -> dict:
    from modules import incidents_list
    return incidents_list.rows(NET)


def attention_rows(fx) -> list:
    """Needs attention's rows that link incidents, composed as `needs_attention` composes them
    (the heal source's own links, the stream rows' links, then `_incidents_agree`)."""
    from modules import attention as A

    got = A.heal_source(got=fx["decisions"])
    rows = [dict(r) for r in got["rows"]] + [json.loads(json.dumps(STREAM_ROW))]
    for r in rows:
        r.setdefault("networks", {d: [NET] for d in r.get("devices") or []})
    A._link_stream_incidents(rows)
    return A._incidents_agree(rows, NET)


def agreement(fx) -> dict:
    """Both directions: open incidents needing a person with no row linking them, and rows
    linking an incident that is not open needing a person."""
    rows = listed()["rows"]
    needs = {r["id"] for r in rows if not r["resolved"] and r["state"] == "needs_person"}
    links = {}
    for top in attention_rows(fx):
        for r in [top] + list(top.get("folded") or []):
            iid = (r.get("incident_page") or {}).get("id")
            if iid:
                links.setdefault(iid, []).append(r["id"])
    return {"needs": needs, "links": links,
            "unlinked": sorted(needs - set(links)),
            "wrong_links": sorted(set(links) - needs)}


class TestTonightsDisagreements:
    def test_r7s_firing_episode_held_only_by_a_closed_incident(self, stores):
        """The measured cause: the alerts' keys are the closed incident's, and no open
        incident holds them."""
        from modules.evidence_pack import alert_key, firing
        from modules.heal import incidents

        old = next(i for i in stores["incidents"] if i["id"] == OLD_R7)
        keys = {f"alert:{alert_key(i)}" for i in firing(stores["alerts"])}
        assert old["state"] == "closed" and old["closed_why"].startswith("cant_fix:")
        assert keys and keys <= incidents._keys(old)
        assert not [i for i in incidents.read(NET)["incidents"]
                    if i.get("state") in incidents.OPEN_STATES and i["device"] == "r7"]

    def test_the_episode_is_sighted_again_into_an_open_incident_once(self, stores):
        from modules.heal import incidents
        from modules.heal import triggers as T

        got = T.from_alerts("grafana-alerts", stores["alerts"])
        assert got["sighted"] == 2, got
        (new,) = [i for i in incidents.read(NET)["incidents"]
                  if i.get("state") in incidents.OPEN_STATES and i["device"] == "r7"]
        assert {t["subscription"] for t in new["triggers"]} == {"101", "102"}
        assert all(OLD_R7 in t["words"] for t in new["triggers"]), "it says why it opened"
        # Held now by an open incident: the next reads sight nothing.
        assert T.from_alerts("grafana-alerts", stores["alerts"])["sighted"] == 0

    def test_an_episode_is_sighted_again_at_most_resight_most_times(self, stores, monkeypatch):
        from modules.heal import incidents
        from modules.heal import triggers as T

        for n in range(T.RESIGHT_MOST + 2):
            T.from_alerts("grafana-alerts", stores["alerts"])
            for i in incidents.read(NET)["incidents"]:
                if i.get("state") in incidents.OPEN_STATES and i["device"] == "r7":
                    incidents.close(NET, i["id"], f"closed by the test, round {n}")
        opened = [i for i in incidents.read(NET)["incidents"]
                  if i["device"] == "r7" and "closed by the test" in (i.get("closed_why") or "")]
        assert len(opened) == T.RESIGHT_MOST, [i["id"] for i in opened]

    def test_r6s_withdrawn_heal_is_cleared_not_waiting_for_a_person(self, stores):
        row = next(r for r in listed()["rows"] if r["id"] == R6)
        assert (row["state"], row["resolved"]) == ("cleared", True), row


class TestTheInvariantBothWays:
    def test_before_the_episode_is_sighted_again(self, stores):
        """On the stores as they were: no row links a resolved incident (the old r7 can't-fix
        row goes), and every incident needing a person is linked (r4's hold by its decision)."""
        got = agreement(stores)
        assert R4 in got["needs"], "the population holds an incident that needs a person"
        assert got["unlinked"] == [] and got["wrong_links"] == [], got
        assert OLD_R7 not in got["links"] and R6 not in got["needs"]
        assert got["links"][R4] == ["heal:hd-9efee321a309"], "linked by its own hold"

    def test_after_it_is_sighted_again(self, stores):
        from modules.heal import triggers as T

        T.from_alerts("grafana-alerts", stores["alerts"])
        got = agreement(stores)
        (r7,) = [i for i in got["needs"] if i not in (R4,)]
        assert got["unlinked"] == [] and got["wrong_links"] == [], got
        assert got["links"][r7] == [STREAM_ROW["id"]], "the lost streams' row opens it"

    def test_an_incident_no_row_names_takes_a_row_of_its_own(self, stores):
        """The other direction by construction: with the hold's row gone (its link removed),
        r4's open incident still has a row, its own, opening its page."""
        from modules import attention as A

        rows = [r for r in attention_rows(stores) if r["id"] != "heal:hd-9efee321a309"]
        again = A._incidents_agree([dict(r, incident_page=None) if r.get("kind") == "incident"
                                    else r for r in rows], NET)
        own = [r for r in again if (r["source"], r["kind"]) == ("heal", "incident")]
        assert [r["incident_page"]["id"] for r in own] == [R4]
        assert own[0]["action"]["href"].endswith(R4) or R4 in own[0]["action"]["href"]


class TestAcknowledgedOnBoth:
    def test_an_acknowledged_hold_is_acknowledged_on_incidents_too(self, stores, monkeypatch):
        from modules import acknowledgements as ACK
        from modules import attention as A
        from modules import incidents_list

        ack = {"row": "heal:hd-9efee321a309", "event": "hd-9efee321a309",
               "by": "operator@example.net", "why": "adopting r4's change tomorrow",
               "at": "2026-11-14T17:30:00Z"}
        monkeypatch.setattr(ACK, "read", lambda: {"state": "ok", "rows": [ack]})
        monkeypatch.setattr(ACK, "current", lambda rows: list(rows))
        page = incidents_list.page(NET, "open")
        (r4,) = [r for g in page["groups"] for r in g["rows"] if r["id"] == R4]
        assert "Acknowledged by" in r4["acknowledged"] and "tomorrow" in r4["acknowledged"]
        shown, acked, _ = A._without_acknowledged(attention_rows(stores),
                                                  ({"state": "ok", "rows": [ack]}, [ack]))
        assert [a["id"] for a in acked] == [ack["row"]]
        assert R4 not in {(r.get("incident_page") or {}).get("id") for r in shown}
