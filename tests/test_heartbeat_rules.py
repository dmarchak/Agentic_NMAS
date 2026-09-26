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
INTERVAL = 300

#: Real inter-arrival ranges from the operator's interval run, 2026-09-25.
MEASURED = {"r2": (299.8, 300.1), "s1": (316.3, 321.9), "s2": (317.4, 321.9),
            "s3": (493.0, 546.2), "s4": (387.8, 414.0)}
LINE = ("Sep 25 16:34:44 {h} 39: {h}: *Sep 25 16:34:44.799: "
        "%HA_EM-5-LOG: NMAS-HEARTBEAT: NMAS-HEARTBEAT")


def _gaps(lo, hi, n=10):
    step = (hi - lo) / (n - 1)
    return [round(lo + i * step, 3) for i in range(n)]


def _arrivals(gaps, start=1_000_000.0):
    out = [start]
    for g in gaps:
        out.append(out[-1] + g)
    return out


class TestTheWindowIsTheDevicesOwn:
    @pytest.mark.parametrize("host", sorted(MEASURED))
    def test_quiet_on_one_miss_firing_on_two_for_each_measured_device(self, host):
        lo, hi = MEASURED[host]
        m = H.measure(_gaps(lo, hi), INTERVAL)
        assert m["basis"] == "measured"
        assert 2 * hi < m["window"] < 3 * lo, (host, m)

    def test_the_per_platform_window_was_wrong_for_three_switches(self):
        """The 999 s vIOS window, against the band each switch needs."""
        for host in ("s1", "s2", "s3"):
            lo, hi = MEASURED[host]
            assert not (2 * hi < 999 < 3 * lo), host
        lo, hi = MEASURED["s4"]
        assert 2 * hi < 999 < 3 * lo, "floor: the one it fitted"

    def test_a_miss_in_the_history_does_not_widen_the_window(self):
        lo, hi = MEASURED["s1"]
        gaps = H.gaps_from(_arrivals(_gaps(lo, hi) + [640.0] + _gaps(lo, hi)))
        assert max(gaps) <= hi + 0.01
        assert H.measure(gaps, INTERVAL)["basis"] == "measured"

    def test_an_inseparable_device_is_named_and_never_false_alarms_on_one_miss(self):
        m = H.measure(_gaps(300.0, 460.0), INTERVAL)
        assert m["basis"] == "inseparable" and m["window"] > 2 * 460
        rule = H.rule_for("sx", "uid", INTERVAL, m)
        assert rule["labels"]["window_basis"] == "inseparable"
        assert "may go unseen" in rule["annotations"]["description"]


class TestANewDeviceGetsAProvisionalRuleNamedAsSuch:
    def test_too_few_gaps_is_provisional_at_the_fleets_slowest_rate(self):
        infos = H.windows({"s3": _gaps(*MEASURED["s3"]), "s1": _gaps(*MEASURED["s1"]),
                           "new": [300.0, 301.0]}, INTERVAL)
        new = infos["new"]
        assert new["basis"] == "provisional"
        assert new["assumed_rate"] == infos["s3"]["rate"], "the SLOWEST measured"
        assert new["window"] > infos["s3"]["window"] * 0.9
        rule = H.rule_for("new", "uid", INTERVAL, new)
        assert rule["labels"]["window_basis"] == "provisional"
        d = rule["annotations"]["description"]
        assert "PROVISIONAL" in d and "ASSUMPTION" in d and "not a measurement" in d

    def test_with_nothing_measured_the_floor_is_named(self):
        infos = H.windows({"new": []}, INTERVAL)
        assert infos["new"]["assumed_rate"] == H.PROVISIONAL_RATE_FLOOR
        assert "no device measured yet" in infos["new"]["rate_source"]

    def test_every_device_has_exactly_one_rule_with_a_valid_uid(self):
        infos = H.windows({h: _gaps(*MEASURED[h]) for h in MEASURED}, INTERVAL)
        rules = H.build(infos, "loki-uid", INTERVAL)["groups"][0]["rules"]
        uids = [r["uid"] for r in rules]
        assert sorted(r["labels"]["device"] for r in rules) == sorted(MEASURED)
        assert len(set(uids)) == len(MEASURED)
        assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,40}", u) for u in uids)
        assert all(r["execErrState"] == "Alerting" for r in rules)

    def test_every_rule_carries_its_basis_and_window(self):
        infos = H.windows({h: _gaps(*MEASURED[h]) for h in MEASURED}, INTERVAL)
        doc = H.build(infos, "loki-uid", INTERVAL)
        for rule in doc["groups"][0]["rules"]:
            assert rule["labels"]["window_basis"] in H.BASES
            assert int(rule["labels"]["window_seconds"]) == \
                rule["data"][0]["relativeTimeRange"]["from"]
            assert rule["noDataState"] == "Alerting"


class TestAMovedRateIsANamedState:
    def _installed(self, **windows):
        return {h: (w, b, "uid") for h, (w, b) in windows.items()}

    def test_current(self):
        fresh = H.windows({"s1": _gaps(*MEASURED["s1"])}, INTERVAL)
        code, lines = H.check(self._installed(s1=(fresh["s1"]["window"], "measured")),
                              fresh, {"s1"})
        assert code == H.EXIT_OK and lines[0].startswith("current")

    def test_a_moved_rate_is_STALE_RATE_with_the_numbers(self):
        """s3's rate varies; a window from yesterday's rate stops fitting."""
        fresh = H.windows({"s3": _gaps(600.0, 640.0)}, INTERVAL)
        code, lines = H.check(self._installed(s3=(1250, "measured")), fresh, {"s3"})
        assert code == H.EXIT_STALE
        assert lines[0].startswith("STALE RATE s3") and "600.0-640.0" in lines[0]

    def test_provisional_ready_and_still_provisional(self):
        fresh = H.windows({"a": _gaps(*MEASURED["s1"]), "b": [300.0]}, INTERVAL)
        code, lines = H.check(self._installed(a=(1364, "provisional"),
                                              b=(1364, "provisional")),
                              fresh, {"a", "b"})
        assert code == H.EXIT_STALE
        assert any(l.startswith("PROVISIONAL READY a") for l in lines)
        assert any(l.startswith("provisional b") for l in lines)

    def test_still_provisional_alone_does_not_fail(self):
        fresh = H.windows({"b": [300.0]}, INTERVAL)
        code, _ = H.check(self._installed(b=(1364, "provisional")), fresh, {"b"})
        assert code == H.EXIT_OK

    def test_a_measured_device_gone_quiet_is_named(self):
        fresh = H.windows({"s1": []}, INTERVAL)
        code, lines = H.check(self._installed(s1=(800, "measured")), fresh, {"s1"})
        assert code == H.EXIT_STALE and lines[0].startswith("UNMEASURABLE s1")

    def test_the_population_in_both_directions(self):
        fresh = H.windows({"s1": _gaps(*MEASURED["s1"])}, INTERVAL)
        code, lines = H.check(self._installed(r5=(750, "measured")), fresh, {"s1"})
        assert code == H.EXIT_STALE
        assert any(l.startswith("MISSING    s1") for l in lines)
        assert any(l.startswith("EXTRA      r5") for l in lines)

    def test_installed_reads_back_what_build_wrote(self):
        import yaml
        infos = H.windows({h: _gaps(*MEASURED[h]) for h in MEASURED}, INTERVAL)
        doc = yaml.safe_load(H.render(H.build(infos, "uid", INTERVAL)))
        got = H.installed(doc)
        assert {h: got[h][:2] for h in got} == {
            h: (infos[h]["window"], infos[h]["basis"]) for h in infos}


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

    def test_the_query_is_a_raw_regex(self):
        assert "|~ `" in H.query_for("r1")


class TestRefusals:
    INFO = {"basis": "measured", "window": 800, "lo": 300, "hi": 301, "n": 9,
            "rate": 1.0}

    def test_an_empty_population_is_refused_not_written(self):
        with pytest.raises(ValueError, match="empty"):
            H.build({}, "uid", INTERVAL)

    def test_no_datasource_is_refused(self):
        with pytest.raises(ValueError, match="datasource"):
            H.build({"r1": self.INFO}, "", INTERVAL)

    @pytest.mark.parametrize("interval", [0, None, 30])
    def test_an_unusable_interval_is_refused(self, interval):
        with pytest.raises(ValueError, match="heartbeat interval"):
            H.build({"r1": self.INFO}, "uid", interval)

    def test_an_unusable_name_is_refused(self):
        with pytest.raises(ValueError):
            H.build({'r1"} or vector(1) #': self.INFO}, "uid", INTERVAL)

    def test_no_loki_refuses_rather_than_guessing(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["x", "--datasource-uid", "u"])
        monkeypatch.delenv("NMAS_LOKI_URL", raising=False)
        monkeypatch.setattr(H, "_loki_url", lambda arg: "")
        assert H.main() == H.EXIT_UNPROVEN
        assert "refuses to write one" in capsys.readouterr().out


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
        assert expected == {"s4", "r2"}
        assert not_expected == ["r5", "s3"]

    def test_a_partial_block_is_not_told_to_heartbeat(self, tmp_path,
                                                      monkeypatch):
        partial = {**self.BLOCK, "heartbeat": 0}
        self._world(tmp_path, monkeypatch,
                    docs={"s1": {"logging": {"syslog": partial}}},
                    platforms={"s1": "cisco_ios"}, netbox=["s1"])
        expected, not_expected = H.expected_devices()
        assert expected == set() and not_expected == ["s1"]


class TestOnlyTheHeartbeatLineCounts:
    """Measured 2026-09-25: silencing s4 by removing its applet's timer logged
    `%HA_EM-4-FMPD_NO_EVENT: No event configured for applet NMAS-HEARTBEAT`,
    and the substring query counted it as a heartbeat -- a 73 s gap, and s4
    INSEPARABLE. The alert rules share the query, so a broken applet's own
    error read as a sign of life. Both lines below are the real shapes."""

    BEAT = ("Sep 25 21:21:22 s4 63: s4: *Sep 25 04:22:37.786: "
            "%HA_EM-5-LOG: NMAS-HEARTBEAT: NMAS-HEARTBEAT")
    NOT_A_BEAT = ("Sep 25 21:22:35 s4 64: s4: *Sep 25 04:23:34.016 UTC: "
                  "%HA_EM-4-FMPD_NO_EVENT: No event configured for applet NMAS-HEARTBEAT")

    def _regexes(self, query):
        return re.findall(r"\|~ `([^`]*)`", query)

    def test_the_heartbeat_matches_and_the_error_naming_the_applet_does_not(self):
        pats = self._regexes(H.query_for("s4"))
        assert len(pats) == 2, pats
        assert all(re.search(p, self.BEAT) for p in pats)
        assert not all(re.search(p, self.NOT_A_BEAT) for p in pats)
        # ...and the bare marker, which the old query relied on, is in both.
        assert H.MARKER in self.BEAT and H.MARKER in self.NOT_A_BEAT

    def test_the_severity_digit_is_free(self):
        """Changing the applet's priority must not silently stop every match."""
        pat = re.compile(H.HEARTBEAT_LINE)
        assert pat.search(self.BEAT.replace("HA_EM-5-LOG", "HA_EM-6-LOG"))

    def test_the_rule_uses_the_same_anchored_query(self):
        rule = H.rule_for("s4", "uid", 300, {"basis": "measured", "window": 900,
                                             "lo": 390, "hi": 430, "n": 40, "rate": 0.75})
        assert H.HEARTBEAT_LINE in yaml.safe_dump(rule, width=10_000)


class TestAConfigurationChangeIsNotAMeasurement:
    """Re-entering the applet restarts its timer, so the gap spanning the
    change lands between one and two intervals: under the long-gap cut, and
    enough to widen the band until one miss overlaps two."""

    def test_a_gap_spanning_a_config_change_is_excluded(self):
        arrivals = _arrivals(_gaps(390, 430) + [700.0] + _gaps(390, 430))
        restart_gap_end = arrivals[11]
        with_restart = H.gaps_from(arrivals)
        assert 700.0 in with_restart, "the fixture must exhibit the case"
        assert H.measure(with_restart, 300)["basis"] == "inseparable"
        cleaned = H.gaps_from(arrivals, config_events=[restart_gap_end - 100])
        assert 700.0 not in cleaned
        assert H.measure(cleaned, 300)["basis"] == "measured"

    def test_a_config_change_outside_every_gap_excludes_nothing(self):
        arrivals = _arrivals(_gaps(390, 430))
        assert H.gaps_from(arrivals, config_events=[arrivals[0] - 1000]) == H.gaps_from(arrivals)

    def test_the_config_query_is_anchored_to_the_device(self):
        q = H.config_query_for("s4")
        assert H.host_pattern("s4") in q and "CONFIG_I" in q
