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
        assert _names(f["nmas-snmp-cisco_iosxe.json"]) == ["r1", "r2", "r3", "r4", "r6"]
        assert _names(f["nmas-snmp-cisco_ios.json"]) == ["s1", "s2", "s3", "s4"]
        assert _names(f["nmas-snmp-all.json"]) == ["r1", "r2", "r3", "r4", "r6", "s1", "s2", "s3", "s4"]
        assert g["devices"] == 9

    def test_the_ipsla_file_is_the_devices_whose_golden_defines_an_operation(self):
        """Measured: exactly the five the hand-kept `cisco_ipsla` job lists."""
        f = _generated()["files"]["nmas-snmp-ipsla.json"]
        hand_kept = sorted(t["labels"]["instance"] for t in _capture() if t["scrapePool"] == "cisco_ipsla")
        assert _names(f) == ["r1", "r2", "r3", "r4", "s3"]
        assert sorted(g["targets"][0] for g in f) == hand_kept

    def test_every_target_is_labelled_device_and_role_from_the_inventory(self):
        f = _generated()["files"]
        r3 = next(g for g in f["nmas-snmp-all.json"] if g["labels"]["device"] == "r3")
        assert r3 == {"targets": ["10.255.1.13"], "labels": {"device": "r3", "role": "router"}}

    def test_an_empty_role_is_omitted_and_said_never_invented(self):
        g = _generated()
        r6 = next(x for x in g["files"]["nmas-snmp-all.json"] if x["labels"]["device"] == "r6")
        assert r6["labels"] == {"device": "r6"}
        assert any("r6: no role in the inventory" in n for n in g["notes"])

    def test_retired_r5_is_not_a_target(self):
        """r5 left the inventory; the hand-kept jobs still scrape it."""
        assert "10.255.1.15" in {t["labels"]["instance"] for t in _capture()}
        all_ips = {g["targets"][0] for g in _generated()["files"]["nmas-snmp-all.json"]}
        assert "10.255.1.15" not in all_ips and "10.255.0.32" in all_ips

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
        assert len(out["changed"]) == 4 and out["unchanged"] == []
        for name in out["changed"]:
            assert stat.S_IMODE(os.stat(tmp_path / name).st_mode) == 0o644
        inode = os.stat(tmp_path / "nmas-snmp-all.json").st_ino
        again = P.write(str(tmp_path), _generated())
        assert again["changed"] == [] and len(again["unchanged"]) == 4
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
        assert r["ok"] and r["static"] == [] and r["drift"] == [] and r["unread"] == []

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


class _Prom:
    def __init__(self, active=None, configured=True, fail=""):
        self.active, self.configured, self.fail = active, configured, fail

    def is_configured(self):
        return self.configured

    def _get(self, path, **params):
        assert path == "api/v1/targets" and params == {"state": "active"}
        if self.fail:
            return {"ok": False, "error": self.fail}
        return {"ok": True, "response": _Resp({"data": {"activeTargets": self.active}})}


class TestTheJobHealthRow:
    def test_no_prometheus_no_row(self):
        from modules import prometheus_targets as P
        assert P.health_rows(_Prom(configured=False), _generated()) == []

    def test_could_not_ask_is_unknown_never_ok(self):
        from modules import prometheus_targets as P

        (row,) = P.health_rows(_Prom(fail="connection refused"), _generated())
        assert row["state"] == "unknown" and "connection refused" in row["detail"]

    def test_the_host_today_names_the_static_jobs_and_the_install(self):
        from modules import prometheus_targets as P

        (row,) = P.health_rows(_Prom(_capture()), _generated())
        assert row["state"] == "mismatch" and row["unit"] == "prometheus-targets"
        assert "4 SNMP job(s) still read their hand-kept static targets" in row["detail"]
        assert row["action"]["reference"] == "docs/PROMETHEUS_TARGETS.md"

    def test_drift_after_the_install_gives_the_regenerate_command(self):
        from modules import prometheus_targets as P

        after = _generated(HOST_ROWS + [("r7", "router", "cisco_iosxe", "10.255.0.33")])
        (row,) = P.health_rows(_Prom(_installed(_generated())), after)
        assert row["state"] == "mismatch" and "r7" in row["detail"]
        assert row["action"]["command"] == "scripts/nmas-prometheus-targets --write /etc/prometheus/nmas"

    def test_matching_is_ok_with_its_notes(self):
        from modules import prometheus_targets as P

        g = _generated()
        (row,) = P.health_rows(_Prom(_installed(g)), g)
        assert row["state"] == "ok" and "4 SNMP job(s) scrape exactly" in row["detail"]
        assert "r6: no role" in row["detail"]

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
        assert r.returncode == 2 and "holds no device" in r.stderr
        doc = open(os.path.join(ROOT, "docs", "PROMETHEUS_TARGETS.md"), encoding="utf-8").read()
        for name in FILE_OF_POOL.values():
            assert name in doc
