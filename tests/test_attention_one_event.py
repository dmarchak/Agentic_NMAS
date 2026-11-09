"""One change, one row on Needs attention (C2806; the operator, H11 W1, 2026-11-08: "link them
as one event"). In every H11 walk one change on a device drew two Critical rows: self-healing's
(a proposal, a can't-fix or a hold, the item with the person's action on it) and the drift
check's "<device> has drifted from its golden", each looking like the whole story.

- **The drift row folds into the heal row** of the same device and network: drawn "Also: …"
  in it, its id kept for the record, the heal row's action unchanged.
- **Which heal row leads** when a device has two: a proposal, then a can't-fix, then a hold.
- **What does not fold:** another device's drift, the same device on another network, a hold
  naming several devices (a fleet hold), and a dry-run record, which still attaches to the
  drift row (C2817), the drift row staying the item to act on.
- **What follows the drift row:** a row attached to it (a queued drift item) moves with it to
  the heal row, never giving its action.
- **The count** is the page's: one row.
"""
import time

from modules import attention as A
from tests.test_needs_attention import _panel

NOW = time.time()
NET = "Default"


def _drift(host="r3", lst=NET):
    return A.row(source="drift", kind="drifted", key=f"{lst}:drifted:{host}", level="danger",
                 what=f"{host} has drifted from its golden", cause="differs by 2 lines",
                 action={"label": "Capture it, or put it back", "open": "drift",
                         "device": host, "list": lst},
                 devices=[host], since=NOW - 300, operands={"list": lst})


def _heal(kind, host="r3", lst=NET, key="hd-0000000000a1", devices=None):
    level = "warning" if kind == "held" else "danger"
    return A.row(source="heal", kind=kind, key=key, level=level,
                 what=f"{host}: a line was added. Mercury has a fix: it needs your decision",
                 cause="a fix that needs a person",
                 action={"label": f"Review the fix for {host}", "open": "heal_proposal",
                         "list": lst, "decision": key, "device": host},
                 devices=devices or [host], since=NOW - 290, event=key,
                 operands={"list": lst, "decision": key})


def _queued(host="r3", lst=NET):
    # The approvals source's own shape for a queued drift item (`approvals_source`).
    return A.row(source="approvals", kind="pending", key=f"q-{host}", level="warning",
                 what="An approval is waiting: capture the golden",
                 cause="queued by the drift check; nothing is done until a person approves it",
                 action={"label": f"Capture {host}'s golden from its History tab, which "
                                  "closes this; or let it expire",
                         "href": f"/v2/device/{host}?tab=history"},
                 devices=[host], operands={"kind": "capture", "list": lst},
                 attach_to=f"drift:{lst}:drifted:{host}")


def _page(monkeypatch, *rows):
    src = lambda: A.source_result("drift", "Drift", read_at=NOW, took_ms=1,  # noqa: E731
                                  rows=list(rows), checked="read")
    monkeypatch.setattr(A, "SOURCES", (src,))
    return A.needs_attention()


class TestOneChangeOneRow:
    def test_a_proposal_takes_its_device_s_drift_row(self, monkeypatch):
        page = _page(monkeypatch, _drift(), _heal("proposal"))
        (r,) = page["rows"]
        assert (r["source"], r["kind"]) == ("heal", "proposal")
        assert r["action"]["open"] == "heal_proposal", "the heal row keeps its own action"
        assert [(x["id"], x["what"]) for x in r["attached"]] == [
            (f"drift:{NET}:drifted:r3", "r3 has drifted from its golden")]
        assert "Also: r3 has drifted from its golden" in _panel(page)

    def test_a_cant_fix_and_a_hold_each_take_it(self, monkeypatch):
        for kind in ("cant_fix", "held"):
            (r,) = _page(monkeypatch, _drift(), _heal(kind))["rows"]
            assert (r["kind"], [x["source"] for x in r["attached"]]) == (kind, ["drift"])

    def test_a_proposal_leads_a_cant_fix_and_a_hold(self, monkeypatch):
        # The proposal in the middle, so neither the first nor the last row seen leads by place.
        page = _page(monkeypatch, _heal("held", key="hd-h"), _drift(),
                     _heal("proposal", key="hd-p"), _heal("cant_fix", key="hi-c"))
        lead = next(r for r in page["rows"] if r["attached"])
        assert (lead["kind"], len(page["rows"])) == ("proposal", 3)

    def test_the_count_is_the_page_s(self, monkeypatch):
        page = _page(monkeypatch, _drift(), _heal("proposal"))
        assert page["headline"] == "1 thing(s) need attention"


class TestWhatDoesNotFold:
    def test_another_device_s_drift_stays_its_own_row(self, monkeypatch):
        page = _page(monkeypatch, _drift("r4"), _heal("proposal", host="r3"))
        assert len(page["rows"]) == 2 and not any(r["attached"] for r in page["rows"])

    def test_the_same_name_on_another_network_stays_its_own_row(self, monkeypatch):
        page = _page(monkeypatch, _drift(lst="lab9"), _heal("proposal", lst=NET))
        assert len(page["rows"]) == 2

    def test_a_fleet_hold_folds_no_device_s_drift(self, monkeypatch):
        page = _page(monkeypatch, _drift("r3"),
                     _heal("held", host="r3", devices=["r3", "r4", "r6"]))
        assert len(page["rows"]) == 2

    def test_a_dry_run_record_still_attaches_to_the_drift_row(self, monkeypatch):
        mark = _heal("proposal", key="hd-dry")
        mark["kind"] = "would_heal"
        mark["attach_to"] = f"drift:{NET}:drifted:r3"
        (r,) = _page(monkeypatch, _drift(), mark)["rows"]
        assert (r["source"], [x["id"] for x in r["attached"]]) == ("drift", [mark["id"]])


class TestWhatFollows:
    def test_a_row_attached_to_the_drift_row_moves_with_it_never_giving_its_action(
            self, monkeypatch):
        (r,) = _page(monkeypatch, _drift(), _queued(), _heal("proposal"))["rows"]
        assert r["kind"] == "proposal" and r["action"]["open"] == "heal_proposal"
        assert sorted(x["source"] for x in r["attached"]) == ["approvals", "drift"]
