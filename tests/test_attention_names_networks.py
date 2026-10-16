"""C493 (the operator, 2026-10-05): Needs attention under Default showed another network's
device rows without naming the network, so tw-ztp-a's heartbeat and not-monitored rows read as
Default's. With C488's Needs attention half: one cause (a device whose committed configuration
has no heartbeat) is ONE row, the not-monitored one.

On two real networks (Default, and Branch made through the real create path, C931), each
holding a device, through the real page (`/v2/attention`):

- every row naming a device names each device's network in its meta line, from the row's own
  source where it says (job health's coverage rows), else from every network's inventory
  (reachability); a name two networks hold is said as either, never guessed;
- each "Open <device>" button and each row's action address keeps its device's network
  (``list=``), so following it never lands in the active network;
- Grafana's heartbeat floor naming a device known not to be monitored for its heartbeat is
  folded into that device's not-monitored row, and keeps standing for a device it alone names.
"""

import html as _html
import re
import time

import pytest

from tests.test_network_born_a_repository import _create, store  # noqa: F401 (the fixture)

HOST_A, HOST_B = "r1", "tw-ztp-a"


def _device(host, address):
    return {"hostname": host, "ip": address, "device_type": "cisco_ios", "role": "router",
            "username": "u", "password": "enc-a", "secret": "enc-b"}


@pytest.fixture
def two(store):  # noqa: F811
    """Default holds r1; Branch, created on v2, holds tw-ztp-a. Default stays active."""
    from modules import device
    from modules.nsot import listref

    _create(store, "Branch")
    device.write_devices_csv([_device(HOST_A, "192.0.2.11")], listref.resolve("Default").csv_path)
    device.write_devices_csv([_device(HOST_B, "192.0.2.12")], listref.resolve("Branch").csv_path)
    assert listref.active().name == "Default"
    return store


def _coverage_rows():
    """The real monitoring-coverage check over both networks' real inventories: neither device
    has a committed golden, and the network uses Loki, so each lacks syslog and its heartbeat."""
    from modules import monitoring_coverage as M

    return M.rows(get=lambda k, d="": {"loki_url": "http://192.0.2.5:3100"}.get(k, d),
                  golden=lambda ref, host: "", keeper={}, record=False,
                  profile=lambda ref, dev: {"profile": False, "applies": set(),
                                            "excluded": {}, "error": ""})


def _grafana(rules=()):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {"state": "ok", "doc": {"last_good": {"value_at": now, "value": {
        "rules": list(rules), "instances": [], "counts": {}}}}}


def _reachability(*hosts):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    devs = {h: {"hostname": h, "address": f"192.0.2.{20 + i}", "answering": False,
                "since": now, "consecutive_misses": 3, "threshold": 3, "claim": "TCP 22"}
            for i, h in enumerate(hosts)}
    return {"state": "ok", "doc": {"last_good": {"value_at": now, "value": {
        "devices": devs, "counts": {"not_answering": len(hosts)}}}}}


def _page(client, monkeypatch, *sources):
    from modules import attention

    monkeypatch.setattr(attention, "SOURCES", tuple(sources))
    r = client.get("/v2/attention")
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    text = _html.unescape(r.get_data(as_text=True))
    return text, attention.needs_attention(sources=list(sources))


def _article(text, row_id):
    m = re.search(r'<article class="att[^"]*" data-attention-row="' + re.escape(row_id)
                  + r'">.*?</article>', text, re.S)
    assert m, f"no row {row_id!r} on the page"
    return re.sub(r"\s+", " ", m.group(0))


def _meta(article):
    return re.search(r'<p class="att-meta">(.*?)</p>', article).group(1)


class TestEveryDeviceRowNamesItsNetwork:
    def test_each_networks_not_monitored_row_names_its_own_network(self, two, monkeypatch):
        from modules import attention

        rows = _coverage_rows()
        text, page = _page(two["client"], monkeypatch,
                           lambda: attention.job_health_source(health=lambda: {"jobs": rows}))
        a = _article(text, f"job_health:monitoring:{HOST_A}")
        b = _article(text, f"job_health:monitoring:{HOST_B}")
        assert _meta(a).startswith(f"{HOST_A} in Default "), _meta(a)
        assert _meta(b).startswith(f"{HOST_B} in Branch "), _meta(b)
        # The device's own button opens it in its own network.
        assert f'/v2/device/{HOST_B}?list=Branch">Open {HOST_B}' in b, b
        assert f'/v2/device/{HOST_A}?list=Default">Open {HOST_A}' in a, a
        # Its action (Propose the network's profile) is the network's, named.
        assert "Propose Branch&#39;s monitoring profile" in b or "Propose Branch's" in b

    def test_a_row_across_two_networks_names_each_devices_network(self, two, monkeypatch):
        """Reachability says no network: each device is placed from the inventories."""
        from modules import attention

        text, page = _page(two["client"], monkeypatch,
                           lambda: attention.reachability_source(_reachability(HOST_A, HOST_B)))
        row = next(r for r in page["rows"] if r["source"] == "reachability")
        assert row["networks"] == {HOST_A: ["Default"], HOST_B: ["Branch"]}
        meta = _meta(_article(text, "reachability:not-answering"))
        assert meta.startswith(f"{HOST_A} (Default), {HOST_B} (Branch) "), meta

    def test_a_name_two_networks_hold_is_said_as_either_and_opens_in_neither(
            self, two, monkeypatch):
        from modules import attention, device
        from modules.nsot import listref

        device.write_devices_csv([_device(HOST_B, "192.0.2.12"), _device(HOST_A, "192.0.2.13")],
                                 listref.resolve("Branch").csv_path)
        text, _page_ = _page(two["client"], monkeypatch,
                             lambda: attention.reachability_source(_reachability(HOST_A)))
        art = _article(text, "reachability:not-answering")
        assert _meta(art).startswith(f"{HOST_A} (Branch or Default) "), _meta(art)
        assert f'/v2/device/{HOST_A}">Open {HOST_A}' in art, art

    def test_the_sources_own_network_decides_a_name_two_networks_hold(self, two, monkeypatch):
        """Coverage knows which network's r1 it judged: the row says that one, never "either"."""
        from modules import attention, device
        from modules import monitoring_coverage as M
        from modules import prometheus_targets as P
        from modules.nsot import listref

        device.write_devices_csv([_device(HOST_B, "192.0.2.12"), _device(HOST_A, "192.0.2.13")],
                                 listref.resolve("Branch").csv_path)
        rows = M.rows(devices=[(ref, d) for ref, d in P.inventory(["Branch"])
                               if d["hostname"] == HOST_A],
                      get=lambda k, d="": {"loki_url": "http://192.0.2.5:3100"}.get(k, d),
                      golden=lambda ref, host: "", keeper={}, record=False,
                      profile=lambda ref, dev: {"profile": False, "applies": set(),
                                                "excluded": {}, "error": ""})
        text, _p = _page(two["client"], monkeypatch,
                         lambda: attention.job_health_source(health=lambda: {"jobs": rows}))
        art = _article(text, f"job_health:monitoring:{HOST_A}")
        assert _meta(art).startswith(f"{HOST_A} in Branch "), _meta(art)
        assert f'/v2/device/{HOST_A}?list=Branch">Open {HOST_A}' in art, art

    def test_a_row_whose_action_is_an_address_keeps_its_network(self, two, monkeypatch):
        """An approval names its device's History tab: the address carries the network."""
        from modules import attention

        item = {"id": "a1", "action_type": "update_golden_config", "device_hostname": HOST_A,
                "description": "drift on r1", "context": "", "created_ts": time.time()}
        text, page = _page(two["client"], monkeypatch,
                           lambda: attention.approvals_source(read=lambda: ([item], "")))
        row = next(r for r in page["rows"] if r["source"] == "approvals")
        assert row["action"]["href"] == f"/v2/device/{HOST_A}?tab=history&list=Default"
        assert _meta(_article(text, "approvals:a1")).startswith(f"{HOST_A} in Default ")


class TestOneCauseIsOneRow:
    def test_the_heartbeat_floor_folds_into_the_not_monitored_row(self, two, monkeypatch):
        """C488's Needs attention half: no heartbeat configured, so no rule, is one row."""
        from modules import attention

        rows = _coverage_rows()
        text, page = _page(two["client"], monkeypatch,
                           lambda: attention.job_health_source(health=lambda: {"jobs": rows}),
                           lambda: attention.grafana_source(_grafana()))
        assert not [r for r in page["rows"] if r["kind"] == "heartbeat-floor"], \
            "the floor stood as a second row about the same cause"
        mine = [r for r in page["rows"] if r["id"].startswith("job_health:monitoring:")]
        assert any(x["what"].endswith("have no heartbeat rule Grafana shows")
                   for r in mine for x in r["attached"]), mine
        assert len(page["rows"]) == 2, [r["id"] for r in page["rows"]]

    def test_the_floor_still_stands_for_a_device_it_alone_names(self, two, monkeypatch):
        """Only the device known not monitored leaves the floor: r1 is monitored (a golden with
        the heartbeat and logging), has no rule, and stays named."""
        from modules import attention

        rows = [r for r in _coverage_rows() if r["device"] == HOST_B]
        text, page = _page(two["client"], monkeypatch,
                           lambda: attention.job_health_source(health=lambda: {"jobs": rows}),
                           lambda: attention.grafana_source(_grafana()))
        floor = [r for r in page["rows"] if r["kind"] == "heartbeat-floor"]
        assert len(floor) == 1 and floor[0]["devices"] == [HOST_A], floor
        assert f"Not counted here: {HOST_B}" in floor[0]["cause"], floor[0]["cause"]
        assert floor[0]["networks"] == {HOST_A: ["Default"]}
