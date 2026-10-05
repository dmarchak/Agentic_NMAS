"""P.8 step 5: a reader serving every network reads each distinct configuration ONCE.

Two lists are two networks, and an integration inherits as a group: a list that sets none of
Grafana's keys uses Default's Grafana, a list that sets one owns its own, and a list may
declare it not applicable. A reader that read only the installation's (Default's) Grafana
drew Default's alerts and dashboards for every network (NSOT_P8_DESIGN section 4). Now each
distinct configuration is read once, stored apart (Default's under the reader's own name,
unchanged), and a page asks for its own network's.
"""

import json

import pytest

from modules import integration_groups as IG
from modules import reader_job as R


@pytest.fixture
def networks(tmp_path, monkeypatch):
    """Four networks: Default; Branch with its own Grafana; Lab-3 inheriting Default's;
    Shop declaring Grafana not applicable."""
    from modules import config, device
    from modules import list_settings as L

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
    settings = tmp_path / "user_settings.json"
    settings.write_text(json.dumps({"grafana_url": "http://192.0.2.10:3000"}), encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(settings))
    registry = tmp_path / "device_lists.json"
    registry.write_text(json.dumps({"current_list": "Default", "lists": {
        "Default": "default", "Branch": "branch", "Lab-3": "lab-3", "Shop": "shop"}}),
        encoding="utf-8")
    monkeypatch.setattr(device, "DEVICE_LISTS_CONFIG", str(registry))
    assert L.write("Branch", {"grafana_url": "http://192.0.2.60:3000"})["ok"]
    shop = tmp_path / "lists" / "shop"
    shop.mkdir(parents=True)
    (shop / "settings.json").write_text(json.dumps(
        {"values": {}, "not_applicable": {"grafana": {"by": "t", "why": "no Grafana here"}}}),
        encoding="utf-8")
    return tmp_path


def _reader(name="test-per-network"):
    calls = []

    def read():
        calls.append("Default")
        return {"from": "Default"}

    def read_for(list_name):
        calls.append(list_name)
        return {"from": list_name}

    r = R.Reader(name=name, what="a test reader", endpoints=("x",), interval_seconds=60,
                 interval_basis="a test", read=read, invalidates=("alerts",),
                 per_group=("grafana",), read_for=read_for)
    return r, calls


@pytest.mark.usefixtures("networks")
class TestTheConfigurations:
    def test_each_network_maps_to_the_layer_that_supplies_its_grafana(self):
        assert IG.group_id("grafana", "Default") == "default"
        assert IG.group_id("grafana", "Branch") == "branch"
        assert IG.group_id("grafana", "Lab-3") == "default"
        assert IG.group_id("grafana", "Shop") is None

    def test_the_distinct_configurations_and_who_uses_them(self):
        assert IG.groups(("grafana",)) == [
            {"id": "default", "lists": ["Default", "Lab-3"], "list": "Default"},
            {"id": "branch", "lists": ["Branch"], "list": "Branch"}]

    def test_two_groups_together_are_default_only_when_both_are(self):
        assert IG.combined_id(("grafana", "prometheus"), "Lab-3") == "default"
        assert IG.combined_id(("grafana", "prometheus"), "Branch") == "branch+default"
        assert IG.combined_id(("grafana", "prometheus"), "Shop") is None


@pytest.mark.usefixtures("networks")
class TestTheReaderReadsEachOnce:
    def test_one_read_per_configuration_each_stored_apart(self):
        r, calls = _reader()
        R.run_once(r)
        assert calls == ["Default", "Branch"], "each configuration read once, Lab-3 shares"
        value = lambda got: got["doc"]["last_good"]["value"]          # noqa: E731
        assert value(R.read_cached(r.name)) == {"from": "Default"}
        assert value(R.read_cached(f"{r.name}@branch")) == {"from": "Branch"}

    def test_a_page_reads_its_own_networks_value(self):
        r, _calls = _reader()
        R._REGISTRY[r.name] = r
        try:
            R.run_once(r)
            value = lambda n: R.read_cached_for(r.name, n)["doc"]["last_good"]["value"]  # noqa: E731
            assert value("Branch") == {"from": "Branch"}
            assert value("Lab-3") == {"from": "Default"}, "an inheriting network shares Default's"
            got = R.read_cached_for(r.name, "Shop")
            assert got["state"] == "not_applicable" and "Shop" in got["why"]
        finally:
            R.unregister(r.name)

    def test_each_configuration_has_its_own_liveness_row(self):
        r, _calls = _reader()
        R.run_once(r)
        units = {row["unit"] for row in R.health_rows(population=[r])}
        assert units == {f"reader:{r.name}", f"reader:{r.name}@branch"}

    def test_a_reader_with_no_groups_is_unchanged(self):
        """The control: a reader that declares no groups runs once, under its own name."""
        calls = []
        r = R.Reader(name="test-one-store", what="a test reader", endpoints=("x",),
                     interval_seconds=60, interval_basis="a test",
                     read=lambda: calls.append(1) or {"v": 1}, invalidates=("alerts",))
        R.run_once(r)
        assert calls == [1]
        assert R.read_cached("test-one-store")["doc"]["last_good"]["value"] == {"v": 1}


@pytest.mark.usefixtures("networks")
def test_needs_attention_shows_every_networks_grafana_alerts():
    """A page that read only Default's alerts store would drop Branch's own Grafana's alerts
    while every check passed. Each configuration is its own source, named for its networks,
    with its rows keyed apart."""
    import os
    import time

    from modules import attention as A

    def store(name, group):
        os.makedirs(os.path.dirname(R.store_path(name)), exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        doc = {"endpoints": ["x"], "last_attempt": {"at": stamp, "ok": True},
               "last_good": {"value_at": stamp, "value": {
                   "rules": [], "instances": [], "stalled_groups": [
                       {"group": group, "last_evaluation": "never", "interval_seconds": 60}]}}}
        with open(R.store_path(name), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    store("grafana-alerts", "Default rules")
    store("grafana-alerts@branch+default", "Branch rules")
    results = [s() for s in A._with_every_configuration([A.grafana_source])]
    labels = [r["label"] for r in results]
    assert labels == ["Grafana alerts", "Grafana alerts (Branch)"], labels
    ids = [row["id"] for r in results for row in r["rows"]]
    assert "grafana:stalled:Default rules" in ids
    assert "grafana@branch+default:stalled:Branch rules" in ids, ids


@pytest.mark.usefixtures("networks")
def test_a_per_device_read_asks_each_configuration_once_and_merges():
    """Adjacencies, restarts and platform facts key their value by device across every list:
    each Prometheus configuration is asked once (Default's exactly as before, ``""``), and the
    answers merge. Here Prometheus is Default's for all four networks, so it is asked once."""
    asked = []

    def fetch(list_name):
        asked.append(list_name)
        return True, {f"dev-{list_name or 'default'}": 1}

    assert IG.merged("prometheus", fetch) == (True, {"dev-default": 1})
    assert asked == [""], asked

    asked.clear()
    assert IG.merged("grafana", fetch) == (True, {"dev-default": 1, "dev-Branch": 1})
    assert asked == ["", "Branch"], "Branch's own configuration asked with Branch's client"


@pytest.mark.usefixtures("networks")
def test_another_networks_own_grafana_token_is_tracked():
    from modules import list_settings as L
    from modules.readers import credential_health as CH

    assert L.write("Branch", {"grafana_token": "branch-token",
                              "grafana_token_expires": "2026-12-31"})["ok"]
    (entry,) = CH.grafana_other_networks(0)
    assert entry["id"] == "grafana_token@branch"
    assert entry["label"].startswith("Grafana API token (Branch)")
    assert entry["expires_at"] and entry["expires_at"].startswith("2026-12-31"), entry


def _store_dashboards(name, *uids):
    """A stored grafana-dashboards read holding *uids*, as the reader writes it."""
    import os
    import time

    os.makedirs(os.path.dirname(R.store_path(name)), exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    value = {"datasources": [], "dashboards": {
        u: {"uid": u, "title": u, "variables": [], "panels": []} for u in uids}}
    with open(R.store_path(name), "w", encoding="utf-8") as fh:
        json.dump({"endpoints": ["x"], "last_attempt": {"at": stamp, "ok": True},
                   "last_good": {"value_at": stamp, "value": value}}, fh)


class _NoLiveAsk:
    """A Grafana that must not be asked: every UID these tests choose is in the stored read."""

    def _get(self, *a, **k):
        raise AssertionError(f"asked Grafana live: {a}")


@pytest.mark.usefixtures("networks")
class TestAPageReadsItsOwnNetworksGrafana:
    """P.8 step 8 (board E): list A's dashboards drawn on list B's device is the wrong thing
    that looks right, every check passing. Each page reads its network's role setting, its
    network's stored read, and asks its network's Grafana."""

    @pytest.fixture(autouse=True)
    def _two_grafanas(self, networks):
        from modules import list_settings as L

        _store_dashboards("grafana-dashboards", "nmas-device", "rcn-lab-overview")
        _store_dashboards("grafana-dashboards@branch", "branch-device", "branch-overview")
        assert L.write("Default", {"grafana_device_dashboard_uid": "nmas-device",
                                   "grafana_fleet_dashboard_uid": "rcn-lab-overview"})["ok"]
        assert L.write("Branch", {"grafana_device_dashboard_uid": "branch-device",
                                  "grafana_fleet_dashboard_uid": "branch-overview"})["ok"]

    def test_each_networks_client_is_its_own_grafana(self):
        from modules import device_page as DP

        assert DP.grafana_client("Branch").url == "http://192.0.2.60:3000"
        assert DP.grafana_client("Default").url == "http://192.0.2.10:3000"
        assert DP.grafana_client("Lab-3").url == "http://192.0.2.10:3000", "Lab-3 inherits"

    def test_a_device_page_draws_its_devices_network(self):
        from modules import device_page as DP

        m = DP.monitoring({"hostname": "br-r1", "ip": "192.0.2.61"}, "Branch",
                          client=_NoLiveAsk())
        assert m["network"] == "Branch" and m["settings"]["uid"] == "branch-device"
        assert m["dashboard"]["uid"] == "branch-device", m.get("state")
        assert {d["uid"] for d in m["offered"] + m["not_offered"]} == {
            "branch-device", "branch-overview"}, "only Branch's Grafana's dashboards are listed"
        # The control: Default's device, the same code, Default's Grafana.
        m = DP.monitoring({"hostname": "s1", "ip": "192.0.2.21"}, "Default", client=_NoLiveAsk())
        assert m["dashboard"]["uid"] == "nmas-device"

    def test_the_fleet_page_draws_its_network(self):
        from modules import device_page as DP

        m = DP.fleet_monitoring("Branch", client=_NoLiveAsk())
        assert (m["network"], m["default"], m["grafana_url"]) == (
            "Branch", "branch-overview", "http://192.0.2.60:3000")
        assert [d["uid"] for d in m["offered"]] == ["branch-device", "branch-overview"]
        assert DP.fleet_monitoring("Lab-3", client=_NoLiveAsk())["default"] == "rcn-lab-overview"

    def test_each_page_says_whose_grafana_it_read(self):
        """A network inheriting Default's Grafana says so; one that declared Grafana not
        applicable says that, never "not read yet", which would wait forever."""
        from modules import device_page as DP

        assert [DP.grafana_whose(n) for n in ("Default", "Branch", "Lab-3", "Shop")] == [
            "Default", "Branch", "Default", None]
        for m in (DP.fleet_monitoring("Shop", client=_NoLiveAsk()),
                  DP.monitoring({"hostname": "sh-r1"}, "Shop", client=_NoLiveAsk())):
            assert m["state"] == "not_applicable" and "Shop declared Grafana not applicable" in \
                m["why"], m

    def test_a_reader_not_imported_yet_still_answers_per_network(self, monkeypatch):
        """Asked before its module was imported, a reader's groups were unknown and Default's
        store answered for Branch."""
        import sys

        name, module = "grafana-dashboards", "modules.readers.grafana_dashboards"
        __import__(module)
        kept = R._REGISTRY.pop(name)
        monkeypatch.delitem(sys.modules, module)
        try:
            got = R.read_cached_for(name, "Branch")
            assert set(got["doc"]["last_good"]["value"]["dashboards"]) == {
                "branch-device", "branch-overview"}
        finally:
            R._REGISTRY[name] = kept


@pytest.mark.usefixtures("networks")
def test_each_network_judges_a_range_by_its_own_stores():
    """The history store (C406) and the live retention are a network's own: Default's 90 days
    with no history must refuse 91 days while Branch's 30 days with its lake serves 400."""
    from modules import list_settings as L
    from modules import panels

    ds = [{"uid": "prom", "type": "prometheus", "name": "prometheus", "is_default": True},
          {"uid": "lake", "type": "prometheus", "name": "Lake", "is_default": False}]
    assert L.write("Branch", {"metrics_live_retention_days": 30,
                              "grafana_history_datasource_uid": "lake"})["ok"]
    branch, default = panels.stores(ds, "Branch"), panels.stores(ds, "Default")
    assert (branch.live, branch.history["uid"]) == (30 * 86400, "lake")
    assert (default.live, default.history) == (90 * 86400, None)
    panels.check_range(400 * 86400, "prometheus", branch)
    with pytest.raises(panels.RangeRefused, match="the live store keeps 90 days"):
        panels.check_range(91 * 86400, "prometheus", default)
    assert panels.limit_words(branch).endswith("reads the history store Lake")
    with pytest.raises(TypeError):
        panels.check_range(91 * 86400, "prometheus")


class _Grafana:
    """A Grafana holding *held*; every live ask for one UID is counted."""

    def __init__(self, held):
        self.held, self.asked = set(held), []

    def _get(self, path, **_k):
        uid = path.rsplit("/", 1)[-1]
        self.asked.append(uid)
        if uid in self.held:
            return {"ok": True, "response": _Answer({"dashboard": {"title": uid}})}
        return {"ok": False, "status": 404, "error": "HTTP 404"}


class _Answer:
    def __init__(self, doc):
        self.doc = doc

    def json(self):
        return self.doc


@pytest.mark.usefixtures("networks")
class TestAMissingDashboardIsARow:
    """P.8 step 8c (board E, C): a network's dashboard setting naming a dashboard its Grafana
    does not hold is a Needs attention row naming the network, the setting and the UID, with
    the action and how it clears. Concluded from Grafana's LIVE answer, asked by the reader."""

    @pytest.fixture(autouse=True)
    def _settings(self, networks):
        from modules import list_settings as L

        assert L.write("Default", {"grafana_fleet_dashboard_uid": "rcn-lab-overview",
                                   "grafana_device_dashboard_uid": "nmas-device"})["ok"]
        assert L.write("Branch", {"grafana_fleet_dashboard_uid": "branch-overview"})["ok"]

    def _store(self, gid, roles_):
        import os
        import time

        name = IG.store_name("grafana-dashboards", gid)
        os.makedirs(os.path.dirname(R.store_path(name)), exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(R.store_path(name), "w", encoding="utf-8") as fh:
            json.dump({"endpoints": ["x"], "last_attempt": {"at": stamp, "ok": True},
                       "last_good": {"value_at": stamp, "value": {"roles": roles_}}}, fh)

    def test_the_reader_checks_each_networks_roles_live(self):
        from modules.readers import grafana_dashboards as GD

        g = _Grafana(held={"nmas-device"})
        held, why = GD.roles({"nmas-device": {}}, g, "")
        assert why == "" and g.asked == ["rcn-lab-overview"], "only the UID the list lacks"
        got = {(r["list"], r["role"]): (r["uid"], r["from"], r["state"]) for r in held}
        assert got == {("Default", "fleet"): ("rcn-lab-overview", "Default", "absent"),
                       ("Default", "device"): ("nmas-device", "Default", "present"),
                       ("Lab-3", "fleet"): ("rcn-lab-overview", "Default", "absent"),
                       ("Lab-3", "device"): ("nmas-device", "Default", "present")}
        held, _ = GD.roles({}, _Grafana(held={"branch-overview"}), "Branch")
        # Branch set a role, so it owns the roles group: its device UID is the schema's empty
        # default, never Default's, and nothing is asked about it.
        assert [(r["role"], r["from"], r["state"]) for r in held] == [("fleet", "Branch", "found")]

    def test_one_row_per_setting_naming_every_network(self):
        from modules import attention as A
        from modules.readers import grafana_dashboards as GD

        held, _ = GD.roles({"nmas-device": {}}, _Grafana(held=set()), "")
        self._store("default", held)
        res = A.dashboard_roles_source()
        (r,) = res["rows"]
        assert r["id"] == "dashboards:default:Default:grafana_fleet_dashboard_uid:rcn-lab-overview"
        assert r["what"] == "Default and Lab-3's fleet dashboard is missing from its Grafana"
        assert "grafana_fleet_dashboard_uid names rcn-lab-overview (set in Default's settings, " \
               "which Lab-3 inherit), and http://192.0.2.10:3000 answered" in r["cause"]
        assert r["action"]["label"].startswith("Choose Default and Lab-3's fleet dashboard in "
                                               "Settings › Integrations › Grafana")
        assert r["clears"]["ways"] == ["resolves"] and r["level"] == "warning"
        assert "branch" in res["checked"].lower(), "Branch's store unread is said, not a row"

    def test_the_row_leaves_when_the_setting_moves(self):
        from modules import attention as A
        from modules import list_settings as L
        from modules.readers import grafana_dashboards as GD

        held, _ = GD.roles({"nmas-device": {}}, _Grafana(held=set()), "")
        self._store("default", held)
        assert len(A.dashboard_roles_source()["rows"]) == 1
        assert L.write("Default", {"grafana_fleet_dashboard_uid": "nmas-fleet"})["ok"]
        assert A.dashboard_roles_source()["rows"] == []

    def test_could_not_ask_is_unknown_never_missing(self):
        from modules import attention as A

        self._store("default", [{"list": "Default", "setting": "grafana_fleet_dashboard_uid",
                                 "role": "fleet", "uid": "rcn-lab-overview", "from": "Default",
                                 "state": "unknown", "error": "timed out"}])
        (r,) = A.dashboard_roles_source()["rows"]
        assert r["kind"] == "unconfirmed" and r["level"] == "unknown" and "timed out" in r["cause"]


def test_coverage_reporting_reads_per_network():
    from modules.readers import coverage_reporting

    assert coverage_reporting.READER.per_group == ("prometheus", "loki")


def test_the_grafana_readers_read_per_network():
    """The two Grafana readers declare their configuration, so Default's stays as it was and
    another network's Grafana is read with that network's client."""
    from modules.readers import grafana_alerts, grafana_dashboards

    assert grafana_dashboards.READER.per_group == ("grafana",)
    assert grafana_alerts.READER.per_group == ("grafana", "prometheus")
    assert callable(grafana_dashboards.READER.read_for)
    assert callable(grafana_alerts.READER.read_for)


@pytest.fixture
def standalone(networks):
    """Networks plus Remote, standalone: its Grafana NOT configured, its Prometheus its own,
    and its Loki chosen to inherit Default's."""
    from modules import device
    from modules import list_settings as L

    registry = networks / "device_lists.json"
    doc = json.loads(registry.read_text(encoding="utf-8"))
    doc["lists"]["Remote"] = "remote"
    registry.write_text(json.dumps(doc), encoding="utf-8")
    p = networks / "lists" / "remote"
    p.mkdir(parents=True)
    (p / "settings.json").write_text(json.dumps({
        "values": {"prometheus_url": "http://192.0.2.70:9090"}, "not_applicable": {},
        "mode": "standalone", "groups": {"loki": "inherit"}}), encoding="utf-8")
    assert L.mode("Remote") == L.STANDALONE and device.DEVICE_LISTS_CONFIG
    return networks


@pytest.mark.usefixtures("standalone")
class TestAStandaloneNetworksReaders:
    """NSOT_P8_DESIGN section 8, step 5: a standalone network gets its own configuration,
    never Default's store; a configuration with no URL is NOT CONFIGURED, never a reader
    failing every interval; Default's counts name only who chose to inherit."""

    def test_a_standalone_group_is_its_own_configuration_even_with_nothing_set(self):
        assert IG.group_id("grafana", "Remote") == "remote", "it shared Default's store"
        assert IG.group_id("prometheus", "Remote") == "remote"
        assert IG.group_id("loki", "Remote") == "default", "its group chose to inherit"

    def test_a_configuration_with_no_url_is_not_read(self):
        r, calls = _reader()
        R.run_once(r)
        assert "Remote" not in calls, "a Grafana with no URL was asked"
        assert not __import__("os").path.exists(R.store_path(f"{r.name}@remote"))
        units = {row["unit"] for row in R.health_rows(population=[r])}
        assert f"reader:{r.name}@remote" not in units, "a not-configured Grafana is a job row"

    def test_a_page_asking_for_it_hears_not_configured(self):
        r, _calls = _reader()
        R._REGISTRY[r.name] = r
        try:
            got = R.read_cached_for(r.name, "Remote")
            assert got["state"] == "not_configured", got
            assert "Grafana is not configured for Remote" in got["why"]
        finally:
            R.unregister(r.name)

    def test_its_own_configured_group_is_read_with_its_client(self):
        asked = []

        def fetch(list_name):
            asked.append(list_name)
            return True, {f"dev-{list_name or 'default'}": 1}

        assert IG.merged("prometheus", fetch) == (True, {"dev-default": 1, "dev-Remote": 1})
        assert asked == ["", "Remote"]
        asked.clear()
        # Grafana: Remote's is not configured, so it is not asked; Branch's is.
        IG.merged("grafana", fetch)
        assert asked == ["", "Branch"], asked

    def test_who_inherits_names_only_the_networks_that_chose_to(self):
        who = IG.who("grafana")
        assert who["inherit"] == ["Lab-3"]
        assert who["own"] == ["Branch"]
        assert who["not_configured"] == ["Remote"]
        assert who["not_applicable"] == ["Shop"]
        assert IG.who_inherits("loki") == ["Branch", "Lab-3", "Remote", "Shop"]
        assert "Remote" in IG.who("loki")["standalone"]
