"""The Overview shows the difference between a device's golden and its INTENT,
and the profile commit its intent inherits (the operator, 2026-09-30: r6 read
"Drift: clean", which compares the device with its golden, while its golden
carried `cdp run` that its effective intent no longer had; and "Committed
intent e2703d7, 5 d ago" read as unchanged while the profile had changed what r6
should run that day).

On `test_profile_apply`'s lab: r2's REAL config and its committed intent, and r6
in its real shape (r2's without SNMP or the discovery flags). r6's golden is then
given `cdp run`, the line r6 holds on the host.
"""
import pytest

from tests.test_profile_apply import lab  # noqa: F401  (the fixture)


def _ref():
    from modules.nsot import listref
    return listref.resolve("Lab")


def _dev(host):
    return {"hostname": host, "ip": "203.0.113.16" if host == "r6" else "203.0.113.12",
            "platform": "cisco_iosxe", "device_type": "cisco_xe"}


def _page(lab, monkeypatch, host="r6"):  # noqa: F811
    """The real Overview route, the device found in the lab's list (whose
    inventory the lab holds in memory, not in a devices.csv)."""
    from modules import device_page
    monkeypatch.setattr(device_page, "find_device", lambda name, ref=None: (_ref(), _dev(name)))
    return lab["client"].get(f"/v2/device/{host}/overview").get_data(as_text=True)


def _give_r6(lab, line):  # noqa: F811
    from modules.nsot.repo import GoldenItem, save_golden
    save_golden("Lab", [GoldenItem("r6", lab["r6"] + line, "203.0.113.16", platform="cisco_iosxe")],
                source="capture", actor="t", baseline=False)


class TestTheIntentRow:
    def test_a_golden_at_its_intent_is_ok(self, lab):  # noqa: F811
        from modules import device_page
        row = device_page.intent_check(_ref(), _dev("r2"))
        assert row["name"] == "Intent" and row["state"] == "ok", row
        assert not row["on_device"] and not row["in_intent"]

    def test_a_line_only_the_device_has_is_named(self, lab):  # noqa: F811
        from modules import device_page
        _give_r6(lab, "cdp run\n")
        row = device_page.intent_check(_ref(), _dev("r6"))
        assert row["state"] == "warn", row
        assert row["on_device"] == ["cdp run"] and row["in_intent"] == []
        assert "on the device that intent does not have" in row["text"]

    def test_drift_clean_and_intent_differing_are_both_drawn(self, lab, monkeypatch):  # noqa: F811
        _give_r6(lab, "cdp run\n")
        html = _page(lab, monkeypatch)
        assert "on the device, not in intent:" in html and "<code>cdp run</code>" in html

    def test_no_golden_is_unknown_never_ok(self, lab):  # noqa: F811
        from modules import device_page
        row = device_page.intent_check(_ref(), _dev("r9"))
        assert row["state"] == "unknown"


class TestTheProfileItInherits:
    def test_the_profile_commit_is_drawn_beside_the_intent_commit(self, lab, monkeypatch):  # noqa: F811
        from modules import device_page
        from modules.nsot import profile_propose as pp
        assert pp.apply("Lab", pp.propose("Lab")["hash"], "op@example.invalid")["outcome"] == "committed"
        rec = device_page.records(_ref(), _dev("r6"))
        assert rec["intent"]["sha"] and rec["profile"]["sha"] and rec["profile"]["sha"] != rec["intent"]["sha"]
        html = _page(lab, monkeypatch)
        assert "Inherits" in html and rec["profile"]["sha"] in html

    def test_no_profile_draws_no_inherits_line(self, lab, monkeypatch):  # noqa: F811
        from modules import device_page
        assert device_page.records(_ref(), _dev("r6"))["profile"] == {}
        html = _page(lab, monkeypatch)
        assert "<dt>Inherits</dt>" not in html
