"""The device state egress class and its per-network switch (board H, artboard N; H28;
docs/HEAL_TO_INTENT.md 19.5, the operator's N20; `modules/ai/egress_classes.py`,
`routes/ai_classes_v2.py`), on three networks' settings in this test's own folder, through the
real settings writer, record and routes; no device, no provider.

- **Off by default** on every network, saying why; the read loop then refuses every device state
  read, naming the class;
- **Turn on** needs a verified person and a reason of at least three words, written with who, how
  verified, when and why, and recorded in the network's settings record; the loop's reads are then
  allowed; a reason of two words, a service, and a marked network are refused with nothing
  written;
- **each network's own**: Default on turns no other network on;
- **fails closed**: the switch set true with no record of who turned it on is off; an unreadable
  setting is off; a classification marking is off whatever the switch says;
- **Turn off** is one press, effective at once, recorded; off already writes nothing;
- **the card** on the Network tab draws the four classes, Turn on… opens the reason in place, and
  the routes answer in place, a service refused 403.
"""

import json
import os

import pytest

from modules import identity
from modules import list_settings as L
from modules.ai import egress_classes as E
from modules.ai import read_loop as RL
from tests.test_sdn_connections import make_networks

REASON = "lab ten analysis reads"
NET = "Branch"


@pytest.fixture
def nets(tmp_path, monkeypatch):
    root = make_networks(tmp_path, monkeypatch)
    from modules import config
    monkeypatch.setattr(config, "get_list_data_dir",
                        lambda name: str(root / "lists" / config.list_slug(name)))
    return root


def _record(network):
    from modules.config import list_data_path
    path = os.path.join(list_data_path(network), L.RECORD)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _on(network=NET, reason=REASON, **kw):
    spec = dict(actor="op@example.com", actor_verified="access", person=True)
    spec.update(kw)
    return E.turn_on_device_state(network, reason, **spec)


# The read loop's check, on one planted device state operation (read_loop's own shape).
FAMILY = RL.ReadFamily(name="planted", transport="http", egress_class="device_state",
                       operations=(RL.Operation("topology", args={},
                                                sends=(("GET", "/v1.0/topology/switches"),)),),
                       run=lambda op, args, requests, scope: "answered")


def _loop_verdict(network):
    (got,) = RL.check(FAMILY, [{"op": "topology", "args": {}, "why": "to see it",
                                "hypothesis": "it shows the cause"}],
                      network=network, scope={})
    return got


def test_off_by_default_on_every_network_and_the_loop_refuses_naming_it(nets):
    for network in ("Default", "Branch", "Lab-3"):
        got = E.device_state_allowed(network)
        assert got == {"allowed": False, "why": (
            "off by default, and no admin has turned it on (ai_device_state_class is false)")}
    v = _loop_verdict(NET)
    assert v["verdict"] == "refused"
    assert v["reason"] == ("the device state class is off for Branch: off by default, and no "
                           "admin has turned it on (ai_device_state_class is false)")


def test_turn_on_writes_who_and_why_records_it_and_the_loop_then_allows(nets):
    out = _on()
    assert out["ok"] and not out["nothing"] and out["recorded"]
    assert E.device_state_allowed(NET) == {"allowed": True, "why": ""}
    on = L.value(NET, E.DEVICE_STATE_ON, {})
    assert on["by"] == "op@example.com" and on["actor_verified"] == "access"
    assert on["reason"] == REASON and on["at"].endswith("Z")
    (entry,) = _record(NET)
    assert entry["kind"] == "ai_device_state_on" and entry["reason"] == REASON
    assert entry["actor"] == "op@example.com" and entry["group"] == "ai_device_state"
    assert _loop_verdict(NET)["verdict"] == "allowed"
    # On already: nothing written again, and said.
    again = _on()
    assert again["nothing"] and "already on for Branch" in again["words"]
    assert len(_record(NET)) == 1


@pytest.mark.parametrize("kw,said", [
    (dict(reason="two words"), "a reason of at least 3 words turns device state on, and the "
                               "reason given has 2; nothing was changed"),
    (dict(reason="   "), "a reason of at least 3 words turns device state on, and the reason "
                         "given has 0; nothing was changed"),
    (dict(person=False), "turning the device state class on is an admin's decision, made by a "
                         "verified person, and this request is not one (actor op@example.com, "
                         "verified access)"),
    (dict(actor_verified="none"), "turning the device state class on is an admin's decision, "
                                  "made by a verified person, and this request is not one "
                                  "(actor op@example.com, verified none)"),
])
def test_turn_on_is_refused_with_nothing_written(nets, kw, said):
    with pytest.raises(E.DeviceStateRefused) as exc:
        _on(**kw)
    assert str(exc.value) == said
    assert E.device_state_allowed(NET)["allowed"] is False and not _record(NET)
    assert L.value(NET, E.DEVICE_STATE_SETTING, False) is False


def test_a_marked_network_is_refused_on_and_off_whatever_its_switch(nets, monkeypatch):
    _on()
    monkeypatch.setattr(E, "classification_marking", lambda network: "CUI")
    assert E.device_state_allowed(NET) == {"allowed": False, "why": (
        "Branch carries the classification marking 'CUI', which forces AI off")}
    with pytest.raises(E.DeviceStateRefused) as exc:
        _on(network="Lab-3")
    assert "carries the classification marking 'CUI'" in str(exc.value)


def test_each_network_its_own_default_on_turns_no_other_on(nets):
    _on(network="Default")
    assert E.device_state_allowed("Default")["allowed"] is True
    assert E.device_state_allowed("Branch")["allowed"] is False
    assert E.device_state_allowed("Lab-3")["allowed"] is False


def test_the_switch_alone_is_not_in_force(nets):
    """A hand edit of the switch with no record of who turned it on, or one whose reason is
    under three words, is off: fails closed."""
    assert L.write(NET, {E.DEVICE_STATE_SETTING: True}, actor="hand")["ok"]
    got = E.device_state_allowed(NET)
    assert got == {"allowed": False, "why": (
        "ai_device_state_class is true, but ai_device_state_on names no one, so the switch is "
        "not in force: an admin turns it on from Settings with a reason")}
    assert L.write(NET, {E.DEVICE_STATE_ON: {"by": "x", "reason": "two words"}}, actor="hand")["ok"]
    assert "names a reason of fewer than three words" in E.device_state_allowed(NET)["why"]


def test_an_unreadable_setting_is_off(nets, monkeypatch):
    _on()

    def broken(*a, **kw):
        raise L.ListSettingsUnreadable("the file could not be read (ValueError)")
    monkeypatch.setattr(L, "value", broken)
    assert E.device_state_allowed(NET) == {"allowed": False, "why": (
        "Branch's ai_device_state_class could not be read (ListSettingsUnreadable), so it is off")}


def test_turn_off_is_at_once_recorded_and_off_again_writes_nothing(nets):
    _on()
    out = E.turn_off_device_state(NET, actor="op@example.com", actor_verified="access",
                                  person=True)
    assert out["ok"] and not out["nothing"] and out["recorded"]
    assert "no read answer leaves the host for this network from now on" in out["words"]
    assert E.device_state_allowed(NET)["allowed"] is False
    assert L.value(NET, E.DEVICE_STATE_ON, {}) == {}
    kinds = [e["kind"] for e in _record(NET)]
    assert kinds == ["ai_device_state_on", "ai_device_state_off"]
    assert _record(NET)[1]["before"]["reason"] == REASON
    again = E.turn_off_device_state(NET, actor="op@example.com", actor_verified="access",
                                    person=True)
    assert again["nothing"] and len(_record(NET)) == 2


def test_the_class_cannot_be_written_by_a_generic_card(nets):
    """Cardless: no generic Settings card draws or saves it (`settings_scope.CARDLESS`), and it
    is each network's own (`OWN_ONLY`)."""
    from modules import settings_scope as S
    assert "ai_device_state" in S.CARDLESS and "ai_device_state" in S.OWN_ONLY
    assert S.scope_of(E.DEVICE_STATE_SETTING) == (S.NETWORK, "ai_device_state")


# ── The card and its routes ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client(nets):
    import app as A
    return A.app.test_client()


BASE = "/v2/settings/network/Branch/ai-classes"


def _device_state_row(client):
    html = client.get("/v2/settings/network/Branch?tab=network").get_data(as_text=True)
    assert 'id="ai-classes"' in html and "What AI may send" in html
    for key in ("allowed", "topology", "device_state", "configuration"):
        assert f'data-ai-class="{key}"' in html
    return html.split('data-ai-class="device_state"', 1)[1].split("</tr>", 1)[0]


def test_the_network_tab_draws_the_class_off_then_on_once_turned_on(client):
    """The card draws the four classes, device state off with Turn on…; pressed on, the class
    is in force and the card draws it on with Turn off (behaviour, not presence)."""
    row = _device_state_row(client)
    assert ">off<" in row and "Turn on…" in row and "Turn off" not in row
    assert client.post(f"{BASE}/device-state/on", data={"reason": REASON}).status_code == 200
    assert E.device_state_allowed(NET)["allowed"] is True
    row = _device_state_row(client)
    assert ">on<" in row and "Turn off" in row


def test_turn_on_from_the_card_then_turn_off(client):
    form = client.get(f"{BASE}/device-state/on").get_data(as_text=True)
    assert 'name="reason"' in form and "Turn device state on for Branch" in form
    r = client.post(f"{BASE}/device-state/on", data={"reason": REASON})
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html[:300]
    assert "Device state turned on for Branch by test-person@example.invalid" in html
    assert "Recorded in Branch's settings record" in html and REASON in html
    assert E.device_state_allowed(NET)["allowed"] is True
    r = client.post(f"{BASE}/device-state/off")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Device state turned off for Branch" in html
    assert E.device_state_allowed(NET)["allowed"] is False


def test_a_short_reason_is_refused_in_place_keeping_what_was_typed(client):
    r = client.post(f"{BASE}/device-state/on", data={"reason": "because yes"})
    html = r.get_data(as_text=True)
    assert r.status_code == 409 and "Not changed:" in html
    assert "the reason given has 2" in html and 'value="because yes"' in html
    assert E.device_state_allowed(NET)["allowed"] is False


@pytest.mark.real_identity
def test_a_service_is_refused_and_nothing_is_written(client, monkeypatch):
    from modules.settings_schema import write_settings
    assert write_settings({"require_person_for_configure": False})["ok"]
    svc = identity.Identity(actor="service:ci", kind="service", service_id="ci", verified=True,
                            outcome="ok", peer="127.0.0.1", peer_trusted=True)
    monkeypatch.setattr(identity, "identify", lambda _request: svc)
    r = client.post(f"{BASE}/device-state/on", data={"reason": REASON})
    assert r.status_code == 403 and "Not changed:" in r.get_data(as_text=True)
    assert E.device_state_allowed(NET)["allowed"] is False and not _record(NET)


def test_an_unknown_network_is_refused(client):
    """Refused before the route, by the list guard (`routes/list_param.py`), naming it."""
    r = client.post("/v2/settings/network/Nowhere/ai-classes/device-state/on",
                    data={"reason": REASON})
    assert r.status_code == 404
    assert "There is no network named 'Nowhere'" in r.get_data(as_text=True)
    # Nothing was written anywhere: no network's class moved, and no record was made.
    assert E.device_state_allowed(NET)["allowed"] is False and not _record(NET)
