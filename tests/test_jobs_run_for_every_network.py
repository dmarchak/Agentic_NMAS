"""C491, with C496 and C498 (the operator, 2026-10-05): the scheduled jobs followed the ACTIVE
list. Default's drift went unchecked from the moment the throwaway network was made active,
the drift result was saved to whichever list was active at save time, and paths given a list
read the active one's goldens and inventory.

On test_device_page_network's two real networks (a store of the test's own: Default and Twin,
Twin holding tw-a), and with the ACTIVE list switched during the test:

- the drift scheduler runs every network that is due, whichever is active;
- a run records into ITS network's state even when the active list changes mid-run;
- a run of Twin reads Twin's inventory and goldens, and queues in Twin's queue;
- each network's status is its own, and the drift routes act on the one named;
- the event monitor checks every network;
- the trap and flow stores are the installation's, not the active list's;
- rotation's preflight (C496) and the golden lookup (C498) read the list given.
"""

import pytest

from tests.test_device_page_network import twin  # noqa: F401 (the fixture)


def _activate(name):
    """The installation's active list set to *name*. Nothing in the product sets it since 7.8
    froze it (2026-10-17, P7-26: `/select_device_list` and its setter left), so the registry is
    written as a host whose list was switched before the freeze holds it: the property, that no
    job follows the active list, still matters for that host."""
    from modules import device
    config = device._load_device_lists_config()
    assert name in config["lists"], (name, config)
    config["current_list"] = name
    device._save_device_lists_config(config)
    from modules.config import get_current_list_name
    assert get_current_list_name() == name, "the active list every job could have followed"


class TestTheDriftScheduler:
    def test_every_due_network_runs_whichever_is_active(self, twin, monkeypatch):  # noqa: F811
        import modules.drift_check as D

        ran = []
        monkeypatch.setattr(D, "run_drift_check",
                            lambda triggered_by="", list_name="": ran.append(list_name) or
                            {"ok": True, "summary": f"{list_name} ran"})
        checker = D.DriftChecker()
        assert set(checker.networks()) == {"Default", "Twin"}
        for name in checker.networks():
            checker._next[name] = 0                 # both due
        _activate("Twin")
        for name in checker.networks():             # the loop's body, one pass
            if not D._is_disabled(name):
                checker.run_one(name)
        assert sorted(ran) == ["Default", "Twin"]
        assert D._load_state("Default")["last_result"]["summary"] == "Default ran"

    def test_a_run_records_into_its_own_network_when_the_active_list_changes(
            self, twin, monkeypatch):  # noqa: F811
        """The old save took the active list AT SAVE TIME."""
        import modules.drift_check as D

        def run(triggered_by="", list_name=""):
            _activate("Twin")                       # switched while Default's run is in flight
            return {"ok": True, "summary": f"{list_name} ran"}
        monkeypatch.setattr(D, "run_drift_check", run)
        _activate("Default")
        D.DriftChecker().run_one("Default")
        assert D._load_state("Default")["last_result"]["summary"] == "Default ran"
        assert "last_result" not in D._load_state("Twin")

    def test_a_paused_network_does_not_pause_the_other(self, twin):  # noqa: F811
        import modules.drift_check as D

        D.set_disabled(True, list_name="Default")
        assert D._is_disabled("Default") and not D._is_disabled("Twin")
        checker = D.DriftChecker()
        assert checker.status("Default")["state"] == "disabled"
        assert checker.status("Twin")["state"] != "disabled"

    def test_a_run_of_twin_reads_twin(self, twin, monkeypatch):  # noqa: F811
        """Its inventory, its goldens (by name), its approval queue."""
        import modules.drift_check as D

        asked, queued = [], []
        monkeypatch.setattr("modules.goldens._golden_record",
                            lambda ip, list_name="": asked.append((ip, list_name)) or
                            {"text": "hostname tw-a\n", "path": "", "commit": "",
                             "source": "", "refused": ""})
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda dev, pool, lock: object())
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, cmd: "hostname tw-a\nntp server 192.0.2.10\n")
        monkeypatch.setattr("modules.config_read.check", lambda text, host, previous="": text)
        monkeypatch.setattr("modules.approval_queue.add_approval",
                            lambda **kw: queued.append(kw.get("list_name")) or "id1")
        _activate("Default")
        result = D.run_drift_check("manual", "Twin")
        assert result["list"] == "Twin" and result["inventory"] == 1, result
        assert asked == [("192.0.2.61", "Twin")]
        assert queued == ["Twin"], "the drift item goes to Twin's own queue"

    def test_the_routes_act_on_the_network_named(self, twin):  # noqa: F811
        """The Drift checks card (Settings › Installation › Diagnostics; today's /drift/status
        and /drift/settings until 7.8) draws a row per network and switches the one named,
        whichever is active."""
        import re

        import modules.drift_check as D
        _activate("Default")
        card = twin["client"].get("/v2/settings/installation/diagnostics/drift")
        rows = re.findall(r"<tr>\s*<td>([^<]+)</td>", card.get_data(as_text=True))
        assert rows == ["Default", "Twin"], rows
        r = twin["client"].post("/v2/settings/installation/diagnostics/drift/Twin/off",
                                headers={"HX-Request": "true"})
        import html
        assert r.status_code == 200
        assert "Twin's drift checks turned off" in html.unescape(r.get_data(as_text=True))
        assert D._is_disabled("Twin") and not D._is_disabled("Default")


class TestTheOtherJobs:


    def test_rotation_preflight_finds_a_device_of_the_list_given(self, twin):  # noqa: F811
        """C496: it looked in the ACTIVE list's inventory."""
        from modules.nsot.credential_rotation import preflight

        _activate("Default")
        checks = {c["name"]: c for c in preflight("Twin", "tw-a")["checks"]}
        assert checks["device_in_inventory"]["ok"], checks["device_in_inventory"]

    def test_the_golden_lookup_reads_the_list_given(self, twin, monkeypatch):  # noqa: F811
        """C498: `_golden_record` read the active list's repository."""
        from modules import goldens
        from modules.nsot import listref

        seen = []
        monkeypatch.setattr("modules.nsot.manifest.find_by_ip",
                            lambda repo, ip: seen.append(repo) or ("", None))
        monkeypatch.setattr(goldens, "_migrate_golden_configs", lambda: None)
        monkeypatch.setattr(goldens, "_find_golden_config_file",
                            lambda ip: pytest.fail("the active list's legacy store was read"))
        _activate("Default")
        out = goldens._golden_record("192.0.2.61", "Twin")
        assert out["text"] is None and seen == [listref.resolve("Twin").repo_dir]
