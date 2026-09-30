"""C232, C229: Prometheus's SNMP targets generated from the inventory.

The inventory is the host's `default` list as measured 2026-09-30 (hostname,
role, platform, address; no credential column), the goldens are the REAL fleet
configs (`tests/fixtures/configs/fleet/`), and the running Prometheus is its
REAL `activeTargets` answer for the SNMP pools
(`tests/fixtures/prometheus/targets_static.json`, read-only from the host).
Every "installed" case is a minimal edit of that capture.
"""

import copy
import json
import os
import stat
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "prometheus", "targets_static.json")

#: The host's default list, 2026-09-30: the four switches say `router` (C225)
#: and r6 has no role.
HOST_ROWS = [("s1", "router", "cisco_ios", "10.255.1.21"), ("s2", "router", "cisco_ios", "10.255.1.22"),
             ("s3", "router", "cisco_ios", "10.255.1.23"), ("s4", "router", "cisco_ios", "10.255.1.24"),
             ("r1", "router", "cisco_iosxe", "10.255.1.11"), ("r2", "router", "cisco_iosxe", "10.255.1.12"),
             ("r3", "router", "cisco_iosxe", "10.255.1.13"), ("r4", "router", "cisco_iosxe", "10.255.1.14"),
             ("r6", "", "cisco_iosxe", "10.255.0.32")]


class _Ref:
    name = "Default"
    repo_dir = "/nonexistent"


def _devices(rows=HOST_ROWS):
    return [(_Ref(), {"hostname": h, "role": r, "platform": p, "ip": ip, "device_type": "cisco_ios"})
            for h, r, p, ip in rows]


def _golden(_ref, host):
    """The REAL fleet goldens. r6's golden configures no SNMP (measured on the
    host, 2026-09-30): r2's real config with its `snmp-server` lines removed.
    r7, a device onboarded in a test, is configured: r2's own."""
    r2 = open(os.path.join(FLEET, "r2.cfg"), encoding="utf-8").read()
    if host == "r6":
        return "".join(l for l in r2.splitlines(True) if not l.startswith("snmp-server"))
    if host == "r7":
        return r2
    path = os.path.join(FLEET, f"{host}.cfg")
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def _generated(rows=HOST_ROWS):
    from modules import prometheus_targets as P
    return P.generate(_devices(rows), golden=_golden)


def _names(groups):
    return [g["labels"]["device"] for g in groups]


def _capture():
    return json.load(open(CAPTURE, encoding="utf-8"))["activeTargets"]


FILE_OF_POOL = {"cisco_8000v": "nmas-snmp-cisco_iosxe.json", "cisco_vios_l2": "nmas-snmp-cisco_ios.json",
                "cisco_ipsla": "nmas-snmp-ipsla.json", "lldp": "nmas-snmp-all.json"}


def _installed(generated):
    """The capture as it reads after the install: each pool reads its file,
    its targets are exactly the file's, labelled as generated."""
    out = []
    by_pool = {}
    for t in _capture():
        by_pool.setdefault(t["scrapePool"], t)
    for pool, name in FILE_OF_POOL.items():
        template = by_pool[pool]
        for g in generated["files"][name]:
            t = copy.deepcopy(template)
            ip = g["targets"][0]
            t["discoveredLabels"].update({"__address__": ip,
                                          "__meta_filepath": f"/etc/prometheus/nmas/{name}"})
            t["discoveredLabels"].update(g["labels"])
            t["labels"] = dict(g["labels"], instance=ip, job=pool)
            out.append(t)
    return out


class TestTheGeneratedFiles:
    def test_each_file_holds_its_population(self):
        g = _generated()
        f = g["files"]
        assert _names(f["nmas-snmp-cisco_iosxe.json"]) == ["r1", "r2", "r3", "r4"]
        assert _names(f["nmas-snmp-cisco_ios.json"]) == ["s1", "s2", "s3", "s4"]
        assert _names(f["nmas-snmp-all.json"]) == ["r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4"]
        assert g["devices"] == 8

    def test_the_ipsla_file_is_the_devices_whose_golden_defines_an_operation(self):
        """Measured: exactly the five the hand-kept `cisco_ipsla` job lists."""
        f = _generated()["files"]["nmas-snmp-ipsla.json"]
        hand_kept = sorted(t["labels"]["instance"] for t in _capture() if t["scrapePool"] == "cisco_ipsla")
        assert _names(f) == ["r1", "r2", "r3", "r4", "s3"]
        assert sorted(g["targets"][0] for g in f) == hand_kept

    def test_the_routing_files_follow_the_goldens_and_the_measured_tables(self):
        """Staged run 5: OSPF-MIB on both platforms, OSPFV3-MIB on IOS-XE
        only, BGP from cbgpPeer2Table; each file the devices whose REAL golden
        runs the protocol (OSPFv3 is spelled `ipv6 router ospf` here)."""
        f = _generated()["files"]
        assert _names(f["nmas-snmp-ospf.json"]) == ["r1", "r2", "r3", "r4", "s3", "s4"]
        assert _names(f["nmas-snmp-ospfv3.json"]) == ["r1", "r2", "r3", "r4"]
        assert _names(f["nmas-snmp-bgp.json"]) == ["r3", "r4"]

    def test_every_target_is_labelled_device_and_role_from_the_inventory(self):
        f = _generated()["files"]
        r3 = next(g for g in f["nmas-snmp-all.json"] if g["labels"]["device"] == "r3")
        assert r3 == {"targets": ["10.255.1.13"], "labels": {"device": "r3", "role": "router"}}

    def test_an_empty_role_is_omitted_and_said_never_invented(self):
        g = _generated(HOST_ROWS + [("r7", "", "cisco_iosxe", "10.255.0.33")])
        r7 = next(x for x in g["files"]["nmas-snmp-all.json"] if x["labels"]["device"] == "r7")
        assert r7["labels"] == {"device": "r7"}
        assert any("r7: no role in the inventory" in n for n in g["notes"])

    def test_a_device_whose_golden_configures_no_snmp_is_not_a_target_and_is_named(self):
        """r6 (the operator, 2026-09-30): a target with no SNMP read as
        "unreachable". Its golden decides, as it does for IP SLA."""
        g = _generated()
        assert all("r6" not in _names(v) for v in g["files"].values())
        assert ("r6: its committed golden configures no SNMP, so it is not a target: it is not "
                "monitored by SNMP") in g["notes"]
        none = _generated(HOST_ROWS + [("r9", "router", "cisco_iosxe", "10.255.0.39")])
        assert "r9: its committed golden does not exist, so it is not a target: it is not " \
               "monitored by SNMP" in none["notes"]

    def test_an_unreadable_golden_stops_the_generation_never_drops_the_device(self):
        from modules import prometheus_targets as P

        def boom(ref, host):
            if host == "s2":
                raise OSError("git show failed")
            return _golden(ref, host)
        with pytest.raises(OSError, match="git show failed"):
            P.generate(_devices(), golden=boom)

    def test_retired_r5_is_not_a_target(self):
        """r5 left the inventory; the hand-kept jobs still scrape it."""
        assert "10.255.1.15" in {t["labels"]["instance"] for t in _capture()}
        all_ips = {g["targets"][0] for g in _generated()["files"]["nmas-snmp-all.json"]}
        assert "10.255.1.15" not in all_ips and "10.255.1.21" in all_ips

    def test_an_address_two_devices_hold_is_neither_and_both_are_named(self):
        rows = HOST_ROWS + [("r9", "router", "cisco_iosxe", "10.255.1.13")]
        g = _generated(rows)
        assert "r3" not in _names(g["files"]["nmas-snmp-all.json"])
        assert any("10.255.1.13 is held by r3" in n and "r9" in n for n in g["notes"])

    def test_a_device_with_no_address_is_named(self):
        g = _generated(HOST_ROWS + [("r8", "router", "cisco_iosxe", "")])
        assert any(n.startswith("r8 in Default: no address") for n in g["notes"])

    def test_the_text_is_deterministic(self):
        from modules import prometheus_targets as P

        a = P.render(_generated()["files"]["nmas-snmp-all.json"])
        b = P.render(list(reversed(_generated()["files"]["nmas-snmp-all.json"]))[::-1])
        assert a == b and a.endswith("\n") and json.loads(a)[0]["labels"]["device"] == "r1"


class TestWriting:
    def test_files_are_0644_whatever_the_umask_and_unchanged_ones_untouched(self, tmp_path):
        from modules import prometheus_targets as P

        old = os.umask(0o077)
        try:
            out = P.write(str(tmp_path), _generated())
        finally:
            os.umask(old)
        assert len(out["changed"]) == 7 and out["unchanged"] == []
        for name in out["changed"]:
            assert stat.S_IMODE(os.stat(tmp_path / name).st_mode) == 0o644
        inode = os.stat(tmp_path / "nmas-snmp-all.json").st_ino
        again = P.write(str(tmp_path), _generated())
        assert again["changed"] == [] and len(again["unchanged"]) == 7
        assert os.stat(tmp_path / "nmas-snmp-all.json").st_ino == inode
        assert not [n for n in os.listdir(tmp_path) if n.startswith(".nmas-")]

    def test_a_file_for_a_platform_no_device_has_is_emptied_never_deleted(self, tmp_path):
        from modules import prometheus_targets as P

        (tmp_path / "nmas-snmp-cisco_nxos.json").write_text('[{"targets": ["192.0.2.1"]}]\n')
        (tmp_path / "unrelated.json").write_text("keep")
        out = P.write(str(tmp_path), _generated())
        assert "nmas-snmp-cisco_nxos.json" in out["changed"]
        assert json.loads((tmp_path / "nmas-snmp-cisco_nxos.json").read_text()) == []
        assert (tmp_path / "unrelated.json").read_text() == "keep"

    def test_a_missing_directory_is_refused_naming_the_install(self, tmp_path):
        from modules import prometheus_targets as P

        with pytest.raises(FileNotFoundError, match="PROMETHEUS_TARGETS.md"):
            P.write(str(tmp_path / "absent"), _generated())


class TestTheCheck:
    def test_the_host_today_is_four_jobs_on_static_targets(self):
        from modules import prometheus_targets as P

        r = P.compare(_generated(), _capture())
        assert not r["ok"]
        assert r["static"] == ["cisco_8000v", "cisco_ipsla", "cisco_vios_l2", "lldp"]

    def test_installed_and_current_matches(self):
        from modules import prometheus_targets as P

        g = _generated()
        r = P.compare(g, _installed(g))
        # The routing files are read by no job until the operator adds the
        # jobs (PROMETHEUS_TARGETS.md): said, and not a mismatch.
        assert r["ok"] and r["static"] == [] and r["drift"] == []
        assert r["unread"] == ["nmas-snmp-bgp.json", "nmas-snmp-ospf.json", "nmas-snmp-ospfv3.json"]

    def test_a_device_onboarded_since_the_file_is_named_missing(self):
        from modules import prometheus_targets as P

        before = _generated()
        after = _generated(HOST_ROWS + [("r7", "router", "cisco_iosxe", "10.255.0.33")])
        r = P.compare(after, _installed(before))
        assert not r["ok"]
        assert any(d.startswith("cisco_8000v: r7 (10.255.0.33) is in the inventory and not scraped")
                   for d in r["drift"])

    def test_a_retired_device_still_scraped_is_named_extra(self):
        from modules import prometheus_targets as P

        g = _generated()
        active = _installed(g)
        r5 = copy.deepcopy(next(t for t in active if t["scrapePool"] == "lldp"))
        r5["labels"] = {"instance": "10.255.1.15", "job": "lldp", "device": "r5", "role": "router"}
        r = P.compare(g, active + [r5])
        assert "lldp: 10.255.1.15 is scraped and is in no inventory (labelled r5)" in r["drift"]

    def test_a_label_that_differs_names_both(self):
        from modules import prometheus_targets as P

        g = _generated()
        active = _installed(g)
        for t in active:
            if t["labels"]["instance"] == "10.255.1.21":
                t["labels"]["role"] = "switch"
        r = P.compare(g, active)
        assert any("10.255.1.21 is labelled" in d and "'switch'" in d and "'router'" in d
                   for d in r["drift"])

    def test_no_snmp_pool_at_all_is_not_a_match(self):
        from modules import prometheus_targets as P

        r = P.compare(_generated(), [])
        assert r["ok"] is False and r["pools"] == []


class _Resp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


LOADED = os.path.join(ROOT, "tests", "fixtures", "prometheus", "status_config.json")
RUNTIME = os.path.join(ROOT, "tests", "fixtures", "prometheus", "runtimeinfo.json")
#: The host's reload, from its runtimeinfo (the install's, 2026-09-30).
RELOADED = "2026-09-30T17:31:27Z"


def _at(iso):
    from modules import prometheus_targets as P
    return P._epoch(iso)


def _loaded_yaml():
    """The config Prometheus LOADED after the install (read-only, the host)."""
    return json.load(open(LOADED, encoding="utf-8"))["data"]["yaml"]


def _static_yaml():
    """The same config as it read BEFORE the install: each SNMP job's
    `file_sd_configs` put back as the addresses it listed (a minimal edit of
    the real config; the addresses are the static capture's)."""
    import yaml

    doc = yaml.safe_load(_loaded_yaml())
    by_pool = {}
    for t in _capture():
        by_pool.setdefault(t["scrapePool"], []).append(t["labels"]["instance"])
    for job in doc["scrape_configs"]:
        if job.get("file_sd_configs"):
            del job["file_sd_configs"]
            job["static_configs"] = [{"targets": sorted(by_pool[job["job_name"]])}]
    return yaml.safe_dump(doc)


def _runtime(**over):
    data = json.load(open(RUNTIME, encoding="utf-8"))["data"]
    data.update(over)
    return data


class _Prom:
    """Prometheus's three read-only answers: the discovered targets, the
    LOADED config, and when and whether it was loaded."""

    def __init__(self, active=None, configured=True, fail="", config=None, runtime=None,
                 config_fail=""):
        self.active, self.configured, self.fail = active, configured, fail
        self.config = _loaded_yaml() if config is None else config
        self.runtime = _runtime() if runtime is None else runtime
        self.config_fail = config_fail
        self.asked = []

    def is_configured(self):
        return self.configured

    def _get(self, path, **params):
        self.asked.append(path)
        if path == "api/v1/targets":
            assert params == {"state": "active"}
            if self.fail:
                return {"ok": False, "error": self.fail}
            return {"ok": True, "response": _Resp({"data": {"activeTargets": self.active}})}
        if path == "api/v1/status/config":
            if self.config_fail:
                return {"ok": False, "error": self.config_fail}
            return {"ok": True, "response": _Resp({"data": {"yaml": self.config}})}
        assert path == "api/v1/status/runtimeinfo", path
        return {"ok": True, "response": _Resp({"data": self.runtime})}


class TestTheJobHealthRow:
    def test_no_prometheus_no_row(self):
        from modules import prometheus_targets as P
        assert P.health_rows(_Prom(configured=False), _generated()) == []

    def test_could_not_ask_is_unknown_never_ok(self):
        from modules import prometheus_targets as P

        (row,) = P.health_rows(_Prom(fail="connection refused"), _generated())
        assert row["state"] == "unknown" and "connection refused" in row["detail"]

    def test_before_the_install_names_the_loaded_config_and_the_install(self):
        from modules import prometheus_targets as P

        (row,) = P.health_rows(_Prom(_capture(), config=_static_yaml()), _generated(),
                               directory="", now=_at(RELOADED) + 3600)
        assert row["state"] == "mismatch" and row["unit"] == "prometheus-targets"
        assert ("4 SNMP job(s) do not read the generated targets in the config Prometheus "
                f"has LOADED (cisco_8000v, cisco_ipsla, cisco_vios_l2, lldp), loaded {RELOADED}"
                in row["detail"])
        assert row["action"]["reference"] == "docs/PROMETHEUS_TARGETS.md"

    def test_drift_with_no_directory_names_the_setting_never_a_command(self):
        """The operator's rule: no console step. With no directory set the
        NMAS regenerates nothing, and the action is the Settings field."""
        from modules import prometheus_targets as P

        after = _generated(HOST_ROWS + [("r7", "router", "cisco_iosxe", "10.255.0.33")])
        (row,) = P.health_rows(_Prom(_installed(_generated())), after, directory="",
                               now=_at(RELOADED) + 3600)
        assert row["state"] == "mismatch" and "r7" in row["detail"]
        assert "no targets directory is set" in row["detail"]
        assert "Targets directory" in row["action"]["label"] and "command" not in row["action"]

    def test_no_row_names_a_console_command(self):
        """Every action this row can carry, from its source: none is a command."""
        src = open(os.path.join(ROOT, "modules", "prometheus_targets.py"), encoding="utf-8").read()
        body = src[src.index("# ------------------------------------------------------- the job-health row"):]
        assert '"command"' not in body
        assert "reference" in body                     # the floor: actions exist

    def test_matching_is_ok_with_its_notes(self):
        from modules import prometheus_targets as P

        g = _generated()
        (row,) = P.health_rows(_Prom(_installed(g)), g, directory="", now=_at(RELOADED) + 3600)
        assert row["state"] == "ok" and "4 SNMP job(s) scrape exactly" in row["detail"]
        assert "r6: its committed golden configures no SNMP" in row["detail"]
        assert "the NMAS does not regenerate them (no targets directory is set)" in row["detail"]

    def test_the_states_are_ones_needs_attention_draws(self):
        from modules import attention
        assert "mismatch" in attention._JOB_STATES and "unknown" in attention._JOB_STATES

    def test_job_health_carries_the_row(self, monkeypatch):
        from modules import job_health

        monkeypatch.setattr("modules.prometheus_targets.health_rows",
                            lambda client=None, generated=None: [{"unit": "prometheus-targets",
                                                                  "state": "mismatch",
                                                                  "max_age_minutes": 0}])
        assert {"unit": "prometheus-targets", "state": "mismatch", "max_age_minutes": 0} in \
            job_health.prometheus_target_rows()


class TestTheScript:
    def test_the_dry_run_writes_nothing_and_the_docs_install_names_every_file(self, tmp_path):
        env = dict(os.environ, NMAS_DATA_DIR=str(tmp_path))
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "nmas-prometheus-targets")],
                           capture_output=True, text=True, env=env, timeout=60)
        # An empty store holds no device: refused, never an empty file written.
        assert r.returncode == 2 and "of the 0 device(s) in the inventory, none is configured for SNMP" in r.stderr
        doc = open(os.path.join(ROOT, "docs", "PROMETHEUS_TARGETS.md"), encoding="utf-8").read()
        for name in FILE_OF_POOL.values():
            assert name in doc


class TestTheLoadedConfig:
    def test_the_real_loaded_config_reads_the_four_generated_files(self):
        from modules import prometheus_targets as P

        jobs = P.loaded_jobs(_loaded_yaml())
        snmp = {j: (v["files"], v["interval"]) for j, v in jobs.items() if v["snmp"]}
        assert snmp == {"cisco_8000v": (["nmas-snmp-cisco_iosxe.json"], 30),
                        "cisco_vios_l2": (["nmas-snmp-cisco_ios.json"], 30),
                        "cisco_ipsla": (["nmas-snmp-ipsla.json"], 30),
                        "lldp": (["nmas-snmp-all.json"], 60)}
        assert jobs["node"]["static"] and not jobs["node"]["snmp"]

    def test_durations(self):
        from modules import prometheus_targets as P
        assert [P.seconds(d) for d in ("30s", "1m", "1h30m", "500ms")] == [30, 60, 5400, 0.5]
        assert P.seconds("", 7) == 7


class TestThreeStates:
    """The operator's case (2026-09-30): `--check` seconds after the reload
    said "still reads its static targets" while the LOADED config read the
    files. Each state from the host's real answers."""

    def _compare(self, active, config, now, runtime=None, disk=None, generated=None):
        from modules import prometheus_targets as P

        prom = _Prom(active, config=config, runtime=runtime)
        return P.compare(generated or _generated(), active, loaded=P.read_loaded(prom), now=now,
                         disk_mtimes=disk)

    def test_seconds_after_the_reload_is_not_yet_discovered_never_static(self):
        r = self._compare(_capture(), _loaded_yaml(), now=_at(RELOADED) + 8)
        assert r["state"] == "settling" and r["static"] == [] and r["drift"] == []
        s = {x["pool"]: x for x in r["settling"]}
        assert sorted(s) == ["cisco_8000v", "cisco_ipsla", "cisco_vios_l2", "lldp"]
        assert s["cisco_8000v"]["until"] == "2026-09-30T17:31:57Z"
        assert s["lldp"]["until"] == "2026-09-30T17:32:27Z"        # its own interval, 1 m
        assert ("the config was loaded at 2026-09-30T17:31:27Z and Prometheus has not "
                "discovered it yet; ask again after 2026-09-30T17:31:57Z" in s["cisco_8000v"]["because"])

    def test_past_one_interval_the_same_answer_differs_and_names_the_static_targets(self):
        r = self._compare(_capture(), _loaded_yaml(), now=_at(RELOADED) + 31)
        assert r["state"] == "mismatch" and r["static"] == []
        assert r["by_pool"]["cisco_8000v"]["state"] == "differs"
        assert r["by_pool"]["lldp"]["state"] == "settling"          # 60 s for lldp
        assert any("cisco_8000v: reads a generated file AND static targets" in d for d in r["drift"])

    def test_the_edit_not_loaded_is_named_with_the_load_time(self):
        r = self._compare(_capture(), _static_yaml(), now=_at(RELOADED) + 8)
        assert r["state"] == "mismatch"
        assert r["static"] == ["cisco_8000v", "cisco_ipsla", "cisco_vios_l2", "lldp"]
        (line,) = r["by_pool"]["cisco_8000v"]["lines"]
        assert line == ("cisco_8000v: the LOADED config (loaded 2026-09-30T17:31:27Z) lists "
                        "static targets for this job, so the install's edit is not loaded")

    def test_a_failed_reload_is_said(self):
        from modules import prometheus_targets as P

        (row,) = P.health_rows(_Prom(_capture(), config=_static_yaml(),
                                     runtime=_runtime(reloadConfigSuccess=False)),
                               _generated(), directory="", now=_at(RELOADED) + 3600)
        assert "last reload FAILED" in row["detail"] and "promtool check config" in row["detail"]

    def test_installed_and_discovered_matches(self):
        g = _generated()
        r = self._compare(_installed(g), _loaded_yaml(), now=_at(RELOADED) + 5, generated=g)
        assert r["ok"] and r["state"] == "ok"

    def test_an_unreadable_loaded_config_never_blames_the_config(self):
        from modules import prometheus_targets as P

        prom = _Prom(_capture(), config_fail="HTTP 500")
        (row,) = P.health_rows(prom, _generated(), directory="", now=_at(RELOADED) + 8)
        assert row["state"] == "mismatch"
        assert "the loaded config could not be read" in row["detail"]
        assert "whether the install's edit is loaded is not known" in row["detail"]
        assert "api/v1/status/config" in prom.asked

    def test_a_file_just_written_settles_from_the_write(self):
        """The keeper wrote r7's file two seconds ago; Prometheus has not
        re-read it. Anchored on the file, not on a reload an hour old."""
        before = _generated()
        after = _generated(HOST_ROWS + [("r7", "router", "cisco_iosxe", "10.255.0.33")])
        now = _at(RELOADED) + 3600
        r = self._compare(_installed(before), _loaded_yaml(), now=now, generated=after,
                          disk={"nmas-snmp-cisco_iosxe.json": now - 2, "nmas-snmp-all.json": now - 2})
        assert r["by_pool"]["cisco_8000v"]["state"] == "settling"
        assert "nmas-snmp-cisco_iosxe.json was written at" in r["by_pool"]["cisco_8000v"]["lines"][0]
        # The control: the same difference with no recent write differs.
        r2 = self._compare(_installed(before), _loaded_yaml(), now=now, generated=after)
        assert r2["by_pool"]["cisco_8000v"]["state"] == "differs"

    def test_settling_is_quiet_in_needs_attention(self):
        from modules import attention
        from modules import job_health as J

        assert "settling" in J.OK_STATES
        rows = attention.job_health_source(health=lambda: {"jobs": [
            {"unit": "prometheus-targets", "state": "settling", "detail": "ask again after T"}]},
            readers_now=[])["rows"]
        assert rows == []


class TestTheFilesOnDisk:
    def _row(self, tmp_path, record, now_offset=10, write=True, active=None):
        from modules import prometheus_targets as P

        g = _generated()
        if write:
            P.write(str(tmp_path), g)
            old = _at(RELOADED)
            for n in os.listdir(tmp_path):
                os.utime(tmp_path / n, (old, old))
        (row,) = P.health_rows(_Prom(active or _installed(g)), g, directory=str(tmp_path),
                               now=_at(RELOADED) + now_offset, record=record)
        return row

    def test_current_files_and_prometheus_read_ok_naming_the_last_run(self, tmp_path):
        row = self._row(tmp_path, {"at": RELOADED, "reason": "the app started", "ok": True},
                        now_offset=3600)
        assert row["state"] == "ok"
        assert f"regenerated by the NMAS into {tmp_path}, last run {RELOADED} (the app started)" \
            in row["detail"]

    def test_a_failed_regeneration_is_named_with_its_error(self, tmp_path):
        (tmp_path / "nmas-snmp-all.json").write_text("[]\n")
        row = self._row(tmp_path, {"at": RELOADED, "reason": "r7: devices.csv was written",
                                   "ok": False, "error": "PermissionError: denied"}, write=False)
        assert row["state"] == "mismatch"
        assert "nmas-snmp-all.json: differs from what the inventory generates now" in row["detail"]
        assert "failed: PermissionError: denied" in row["detail"]
        assert "command" not in row["action"]

    def test_files_behind_a_recent_run_are_settling(self, tmp_path):
        (tmp_path / "nmas-snmp-all.json").write_text("[]\n")
        row = self._row(tmp_path, {"at": RELOADED, "reason": "backstop", "ok": True},
                        now_offset=60, write=False)
        assert row["state"] == "settling" and "regenerates them by" in row["detail"]

    def test_files_behind_and_no_run_for_longer_than_the_backstop_is_a_stopped_keeper(self, tmp_path):
        (tmp_path / "nmas-snmp-all.json").write_text("[]\n")
        row = self._row(tmp_path, {"at": RELOADED, "reason": "backstop", "ok": True},
                        now_offset=3600, write=False)
        assert row["state"] == "mismatch" and "so it is not running" in row["detail"]

    def test_an_unreadable_record_is_unknown_never_a_run_that_did_not_happen(self, tmp_path):
        (tmp_path / "nmas-snmp-all.json").write_text("[]\n")
        row = self._row(tmp_path, {"unreadable": "ValueError: x"}, write=False)
        assert row["state"] == "unknown" and "unreadable" in row["detail"]


class TestTheKeeper:
    def test_the_default_directory_is_empty_so_nothing_is_written(self):
        from modules import prometheus_targets as P
        from modules.settings_schema import DEFAULTS

        assert DEFAULTS["prometheus_targets_dir"] == "" and P.target_dir() == ""
        assert P.sync("a test") == {"state": "not_managed"}
        assert P.last_sync() == {}

    def test_a_run_writes_and_records(self, tmp_path):
        from modules import prometheus_targets as P

        rec = P.sync("r7: devices.csv was written", directory=str(tmp_path), generate_fn=_generated)
        assert rec["ok"] and rec["devices"] == 8 and len(rec["changed"]) == 7
        assert P.last_sync()["reason"] == "r7: devices.csv was written"
        again = P.sync("backstop", directory=str(tmp_path), generate_fn=_generated)
        assert again["changed"] == [] and len(again["unchanged"]) == 7

    def test_an_empty_inventory_is_refused_and_recorded(self, tmp_path):
        from modules import prometheus_targets as P

        rec = P.sync("x", directory=str(tmp_path), generate_fn=lambda: _generated(rows=[]))
        assert rec["ok"] is False and "scrape nothing" in rec["error"]
        assert os.listdir(tmp_path) == [] and P.last_sync()["ok"] is False

    def test_a_missing_directory_is_recorded_as_a_failure(self, tmp_path):
        from modules import prometheus_targets as P

        rec = P.sync("x", directory=str(tmp_path / "absent"), generate_fn=_generated)
        assert rec["ok"] is False and "PROMETHEUS_TARGETS.md" in rec["error"]

    def test_a_sender_wakes_the_keeper_only_where_it_runs(self, monkeypatch):
        from modules import prometheus_targets as P

        monkeypatch.setitem(P._keeper, "reasons", [])
        monkeypatch.setitem(P._keeper, "event", __import__("threading").Event())
        monkeypatch.setitem(P._keeper, "thread", None)
        P.inventory_changed("nowhere")
        assert P._keeper["reasons"] == [] and not P._keeper["event"].is_set()
        monkeypatch.setitem(P._keeper, "thread", object())
        P.inventory_changed("default: devices.csv was written")
        assert P._keeper["reasons"] == ["default: devices.csv was written"]
        assert P._keeper["event"].is_set()

    def test_every_devices_csv_write_is_a_sender(self, tmp_path, monkeypatch):
        from modules import device, prometheus_targets as P

        sent = []
        monkeypatch.setattr(P, "inventory_changed", sent.append)
        path = tmp_path / "lab" / "devices.csv"
        path.parent.mkdir()
        device.write_devices_csv([{"hostname": "r7", "ip": "192.0.2.7"}], str(path))
        device.delete_device("192.0.2.7", str(path))
        assert sent == ["lab: devices.csv was written"] * 2

    def test_the_keeper_starts_with_the_app_and_not_on_import(self):
        import ast

        src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "_start_background_daemons")
        assert "start_keeper" in ast.unparse(fn)
        from modules import prometheus_targets as P
        assert P._keeper["thread"] is None             # importing app started nothing

    def test_the_settings_card_offers_the_directory(self):
        from modules.integrations.prometheus import PrometheusIntegration

        assert "prometheus_targets_dir" in PrometheusIntegration.plain_keys
        spec = open(os.path.join(ROOT, "static", "js", "gen", "partials__settings_integrations.1.js"),
                    encoding="utf-8").read()
        assert "key: 'prometheus_targets_dir', label: 'Targets directory'" in spec


class TestTheScriptsReport:
    def _script(self):
        from importlib.machinery import SourceFileLoader
        return SourceFileLoader("nmas_prometheus_targets",
                                os.path.join(ROOT, "scripts", "nmas-prometheus-targets")).load_module()

    def test_not_yet_discovered_exits_3_and_says_when(self, capsys):
        from modules import prometheus_targets as P

        r = P.check(_Prom(_capture()), _generated(), directory="", now=_at(RELOADED) + 8)
        assert self._script()._report_check(r) == 3
        out = capsys.readouterr().out
        assert "NOT YET DISCOVERED (nothing is wrong yet)" in out and "ask again after" in out
        assert "static targets (docs" not in out and "NOT LOADED" not in out

    def test_the_edit_not_loaded_exits_1_naming_the_loaded_config(self, capsys):
        from modules import prometheus_targets as P

        r = P.check(_Prom(_capture(), config=_static_yaml()), _generated(), directory="",
                    now=_at(RELOADED) + 8)
        assert self._script()._report_check(r) == 1
        out = capsys.readouterr().out
        assert "NOT LOADED: the config Prometheus has loaded does not read the generated files" in out
        assert f"loaded config: loaded {RELOADED}" in out
