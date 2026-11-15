"""No page waits, part two: what Needs attention and Incidents compute per request (C3788).

tests/test_no_page_waits.py walks every page with the integrations counted; this file counts
the work two pages do on a request once the background holds their values, the measure the
operator asked for beside it ("Add the routes to test_no_page_waits' timing check with a
server-time bound", 2026-11-15). It is its own file because it draws the pages through the
incident lab's client, which the walk's file does not use (tests/test_presence_only.py reads a
file that draws pages as a UI test file throughout).
"""
import pytest

from tests.test_heal_decide import lab  # noqa: F401  (the fixture `client` builds on)
from tests.test_incident_page import client  # noqa: F401  (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)


# ── C3788: what Needs attention and Incidents compute per request ───────────────────────────
#
# The operator, 2026-11-15: both pages took about 10 s on the host (Incidents 8 to 10 s: its
# list built per request, 90% of it the AI cost estimate reading the record of AI calls 24 to
# 26 times; Needs attention 2 to 10 s: the held value masked per request, and the background's
# recompute building the same list). "Add the routes to test_no_page_waits' timing check with
# a server-time bound": the bound is the WORK a request does, counted (CLAUDE.md: performance
# tests assert on work or growth, never wall-clock; C1741), the work the host's profile timed:
# a request builds no incidents list while one is held, reads the AI calls record's window for
# no estimate while the record is unchanged, and masks no held value twice.

class TestTheHeldPages:
    @pytest.fixture
    def held_lab(self, client, monkeypatch):  # noqa: F811
        """The incidents list's lab, its fixtures planted, the stores held as on the host (a
        test session otherwise computes on every read, `attention_store.COMPUTE_ON_READ`)."""
        from modules import attention_store, incidents_list
        from tests.test_incidents_list_v2 import _load, plant
        plant([_load(n) for n in ("healed", "failed", "busy")])
        monkeypatch.setattr(attention_store, "COMPUTE_ON_READ", False)
        monkeypatch.setattr(incidents_list, "_held", {}, raising=False)
        built = []
        real = incidents_list.rows
        monkeypatch.setattr(incidents_list, "rows",
                            lambda network: built.append(network) or real(network))
        return built

    def test_incidents_builds_its_list_once_then_draws_it_held(self, client,  # noqa: F811
                                                               held_lab):
        from tests.test_incident_page import NET
        for _ in range(3):
            assert client.get(f"/v2/incidents?list={NET}").status_code == 200
        assert held_lab == [NET], f"the list built per request: {held_lab}"

    def test_a_change_announced_builds_it_again(self, client, held_lab):  # noqa: F811
        from modules import invalidation
        from tests.test_incident_page import NET
        client.get(f"/v2/incidents?list={NET}")
        invalidation._changed(("drift",), "the test")
        client.get(f"/v2/incidents?list={NET}")
        assert held_lab == [NET, NET], held_lab

    def test_a_held_list_never_outlives_its_bound(self, client, held_lab,  # noqa: F811
                                                  monkeypatch):
        from modules import incidents_list
        from tests.test_incident_page import NET
        client.get(f"/v2/incidents?list={NET}")
        monkeypatch.setattr(incidents_list, "HOLD_S", 0.0)
        client.get(f"/v2/incidents?list={NET}")
        assert held_lab == [NET, NET], held_lab

    def test_the_background_s_list_is_the_one_the_page_draws(self, client,  # noqa: F811
                                                            held_lab):
        # Needs attention's recompute hands its list over (`attention._incidents_listed`).
        from modules import attention
        from modules.nsot import listref
        from tests.test_incident_page import NET
        with listref.computing_for(NET):
            attention._incidents_listed(NET)
        client.get(f"/v2/incidents?list={NET}")
        assert held_lab == [NET], f"the page built its own: {held_lab}"

    def test_the_estimate_reads_the_calls_record_once_per_change(self, monkeypatch,
                                                                 tmp_path):
        from modules.ai import background, calls
        monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
        monkeypatch.setattr(background, "_measured", {})
        calls.record({"id": "ai-0000000000000b01", "feature": "fixit_troubleshoot",
                      "verdict": "ok", "cost_usd": 0.03})
        windows = []
        real = calls.rows_since
        monkeypatch.setattr(calls, "rows_since", lambda start: windows.append(start)
                            or real(start))
        for _ in range(25):                         # the host's Incidents page: 24 to 26
            background.measured_cost("fixit_troubleshoot")
        assert len(windows) == 1, f"the record's window read {len(windows)} times"
        calls.record({"id": "ai-0000000000000b02", "feature": "fixit_troubleshoot",
                      "verdict": "ok", "cost_usd": 0.05})
        background.measured_cost("fixit_troubleshoot")
        assert len(windows) == 2, "a new row is read"

    def test_needs_attention_masks_each_held_value_once(self, monkeypatch):
        from modules import attention_store, outbound
        monkeypatch.setattr(attention_store, "COMPUTE_ON_READ", False)
        monkeypatch.setattr(attention_store, "_masked", {})
        masks = []
        real = outbound.mask_payload
        # The mask recurses through the value: only a whole page's mask is counted.
        monkeypatch.setattr(outbound, "mask_payload", lambda p, *a, **k: (
            masks.append(1) if isinstance(p, dict) and "rows" in p else None) or real(p, *a, **k))
        n = attention_store._net("Masked")
        n.value = {"ok": True, "rows": [{"what": "a row"}], "badge": None}
        for _ in range(3):
            assert attention_store.read_masked("Masked")["rows"] == [{"what": "a row"}]
        assert len(masks) == 1, f"masked {len(masks)} times for one held value"
        n.value = {"ok": True, "rows": [{"what": "a new row"}], "badge": None}
        assert attention_store.read_masked("Masked")["rows"] == [{"what": "a new row"}]
        assert len(masks) == 2
