"""NSOT_PLAN P.1: Grafana heartbeat rules generated from the NetBox inventory."""

import importlib.machinery
import importlib.util
import re

import pytest
import yaml


def _load():
    loader = importlib.machinery.SourceFileLoader(
        "hb_rules_under_test", "scripts/nmas-heartbeat-rules")
    spec = importlib.util.spec_from_loader("hb_rules_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


H = _load()
FLEET = {**{f"r{i}": "cisco_iosxe" for i in range(1, 7)},
         **{f"s{i}": "cisco_ios" for i in range(1, 5)}}

#: s3's line as rsyslog wrote it (measured, /var/log/network, 2026-09-22),
#: with the heartbeat message in place of the traceback -- the SHAPE is the
#: measured part: `<ts> <host> <seq>: <host>: <msg>`.
LINE = ("Sep 25 16:34:44 {h} 39: {h}: *Sep 25 16:34:44.799: "
        "%HA_EM-5-LOG: NMAS-HEARTBEAT: NMAS-HEARTBEAT")


class TestOneRulePerDevice:
    def test_every_device_has_exactly_one_rule(self):
        doc = H.build(FLEET, "loki-uid", 300)
        assert sorted(H.devices_in(doc)) == sorted(FLEET)
        uids = [r["uid"] for r in doc["groups"][0]["rules"]]
        assert len(uids) == len(set(uids)) == 10
        assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,40}", u) for u in uids)

    def test_silence_is_alerting_not_fine(self):
        """A silent device yields no series; NoData must fire."""
        for rule in H.build(FLEET, "loki-uid", 300)["groups"][0]["rules"]:
            assert rule["noDataState"] == "Alerting"
            assert rule["execErrState"] == "Alerting"

    def test_the_window_is_per_dialect(self):
        doc = H.build({"r2": "cisco_iosxe", "s4": "cisco_ios"}, "uid", 300)
        w = {r["labels"]["device"]: r["data"][0]["relativeTimeRange"]["from"]
             for r in doc["groups"][0]["rules"]}
        assert w == {"r2": 750, "s4": 999}

    @pytest.mark.parametrize("dialect", sorted(H.HEARTBEAT_RATE))
    def test_one_missed_is_quiet_and_two_missed_fire_at_the_MEASURED_spread(
            self, dialect):
        """The property, against each platform's measured real intervals:
        one missed heartbeat (two real intervals, at their longest) stays
        inside the window; two missed (three, at their shortest) fall
        outside."""
        _rate, (lo, hi), _where = H.HEARTBEAT_RATE[dialect]
        w = H.window_seconds(300, dialect)
        assert 2 * hi < w < 3 * lo, (dialect, w, lo, hi)

    def test_one_window_for_every_platform_would_fail(self):
        """Why it is per dialect: 2.5 x 300 s is quiet on one missed r2
        heartbeat and ALERTS on one missed s4 heartbeat."""
        _r, (lo, hi), _w = H.HEARTBEAT_RATE["cisco_ios"]
        assert 2 * hi > 750

    def test_an_unmeasured_dialect_is_refused_not_defaulted(self):
        with pytest.raises(ValueError, match="no measured heartbeat rate"):
            H.build({"n1": "nxos"}, "uid", 300)


class TestTheHostMatchIsAnchored:
    def test_r1_matches_its_own_line_and_not_r10s(self):
        pat = re.compile(H.host_pattern("r1"))
        assert pat.search(LINE.format(h="r1"))
        assert not pat.search(LINE.format(h="r10"))
        assert not pat.search(LINE.format(h="br1"))

    def test_a_dot_in_a_name_is_literal(self):
        pat = re.compile(H.host_pattern("sw.a"))
        assert pat.search(LINE.format(h="sw.a"))
        assert not pat.search(LINE.format(h="swxa"))


class TestTheRuleKeysOnTheDevicesOwnName:
    """Measured 2026-09-25: rsyslog resolved every source address to a name
    except r6's, so the HOSTNAME field differs by device while the device's
    own origin-id field does not. The rule must key on the latter, and the
    two lines below are the real shapes."""

    R2 = ("Sep 25 19:58:40 r2 63: r2: *Sep 25 19:58:39.504: "
          "%HA_EM-5-LOG: NMAS-HEARTBEAT: NMAS-HEARTBEAT")
    R6 = ("Sep 25 19:59:12 10.255.1.16 377: r6: *Sep 25 19:59:12.101: "
          "%HA_EM-5-LOG: NMAS-HEARTBEAT: NMAS-HEARTBEAT")

    def test_both_real_shapes_match_their_own_device(self):
        assert re.search(H.host_pattern("r2"), self.R2)
        assert re.search(H.host_pattern("r6"), self.R6)

    def test_the_rsyslog_hostname_field_alone_never_matches(self):
        """A line whose rsyslog field says r6 and whose origin-id says
        something else is NOT r6's heartbeat: the match is the device
        asserting its own name, not rsyslog's reverse lookup."""
        forged = self.R2.replace("19:58:40 r2 63: r2:", "19:58:40 r6 63: r2:")
        assert not re.search(H.host_pattern("r6"), forged)
        assert re.search(H.host_pattern("r2"), forged)

    def test_without_origin_id_there_is_no_match_so_it_alerts(self):
        """The block's fifth part is what makes the device findable."""
        bare = "Sep 25 19:59:12 10.255.1.16 377: *Sep 25: %HA_EM-5-LOG: NMAS-HEARTBEAT"
        assert not re.search(H.host_pattern("r6"), bare)


class TestRefusals:
    def test_an_empty_inventory_is_refused_not_written(self):
        with pytest.raises(ValueError, match="empty"):
            H.build({}, "loki-uid", 300)

    def test_no_datasource_is_refused(self):
        with pytest.raises(ValueError, match="datasource"):
            H.build({"r1": "cisco_iosxe"}, "", 300)

    @pytest.mark.parametrize("interval", [0, None, 30])
    def test_an_unusable_interval_is_refused(self, interval):
        """Measured: an unset setting read as 0 produced a 60 s window."""
        with pytest.raises(ValueError, match="heartbeat interval"):
            H.build({"r1": "cisco_iosxe"}, "loki-uid", interval)

    def test_an_unusable_name_is_refused(self):
        with pytest.raises(ValueError):
            H.build({'r1"} or vector(1) #': "cisco_iosxe"}, "loki-uid", 300)


def test_the_rendered_file_parses_back_to_the_same_rules():
    doc = H.build(FLEET, "loki-uid", 300)
    text = H.render(doc)
    assert text.startswith("# GENERATED")
    assert yaml.safe_load(text) == doc


class TestThePopulationIsWhoIsToldToHeartbeat:
    """The operator's decision, 2026-09-25: a rule per device whose committed
    intent carries a complete syslog block. NetBox devices without one are
    NAMED as not expected to heartbeat (r5: real, kept in NetBox, retired
    from NMAS) rather than given a rule that alerts for ever."""

    BLOCK = {"trap": "notifications", "origin_id": "hostname",
             "source_interface": "Loopback0", "hosts": ["192.0.2.10"],
             "heartbeat": 300}

    def _world(self, tmp_path, monkeypatch, docs, platforms, netbox):
        import json
        import yaml
        repo = tmp_path / "lab" / "config_repo"
        (repo / "host_vars").mkdir(parents=True)
        (repo / ".nsot").mkdir()
        for name, doc in docs.items():
            (repo / "host_vars" / f"{name}.yml").write_text(
                yaml.safe_dump({"hostname": name, **doc}))
        (repo / ".nsot" / "manifest.json").write_text(json.dumps({
            "devices": {f"uid:{n}": {"name": n, "platform": p}
                        for n, p in platforms.items()}}))
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.device.get_device_lists",
                            lambda: [{"name": "Lab", "filename": "lab"}])
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (True, "", None, "b"))
        monkeypatch.setattr("modules.netbox_client._nb_get",
                            lambda s, b, p: [{"name": n} for n in netbox])

    def test_rules_follow_the_block_and_the_rest_are_named(
            self, tmp_path, monkeypatch):
        self._world(
            tmp_path, monkeypatch,
            docs={"s4": {"logging": {"syslog": self.BLOCK}},
                  "r2": {"logging": {"syslog": self.BLOCK}},
                  "s3": {"logging": {"settings": ["trap critical"],
                                     "hosts": ["192.0.2.10"]}}},
            platforms={"s4": "cisco_ios", "r2": "cisco_iosxe",
                       "s3": "cisco_ios"},
            netbox=["s4", "r2", "s3", "r5"])
        expected, not_expected = H.expected_devices()
        assert expected == {"s4": "cisco_ios", "r2": "cisco_iosxe"}
        assert not_expected == ["r5", "s3"]

    def test_a_partial_block_is_not_told_to_heartbeat(self, tmp_path,
                                                      monkeypatch):
        partial = {**self.BLOCK, "heartbeat": 0}
        self._world(tmp_path, monkeypatch,
                    docs={"s1": {"logging": {"syslog": partial}}},
                    platforms={"s1": "cisco_ios"}, netbox=["s1"])
        expected, not_expected = H.expected_devices()
        assert expected == {} and not_expected == ["s1"]
