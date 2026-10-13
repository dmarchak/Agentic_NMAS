"""E19's lease lifetimes (modules/dhcp_lifetimes.py, scripts/nmas-kea-lifetimes; the operator's
decisions 2026-10-13: pool 4 h, reserved 7 days, management 7 days, T1/T2 at 50%/80%).

The fixtures are Kea's two main files as the NMAS host held them on 2026-10-13, after the subnet
move (C529) and board L's discovery classes: the global lifetime and fixed timers, the IPv4
discovery classes inline, the subnets through Mercury's include.
"""

import importlib.machinery
import importlib.util
import json
import os
import re

import pytest

from modules import dhcp_lifetimes as L
from modules import dhcp_subnets as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEA = os.path.join(ROOT, "tests", "fixtures", "kea")


def _main(name: str, folder) -> tuple:
    """The captured main file placed in *folder*, its includes pointed there: ``(path, text)``."""
    with open(os.path.join(KEA, name), encoding="utf-8") as fh:
        text = fh.read().replace("/etc/kea/", str(folder) + "/")
    (folder / "nmas").mkdir(exist_ok=True)
    path = str(folder / ("kea-dhcp4.conf" if "dhcp4" in name else "kea-dhcp6.conf"))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path, text


def _as_kea_reads(text: str, classes: list) -> dict:
    """The candidate as Kea would read it: comments dropped, the classes include given the
    classes file's list, the subnets include an empty list."""
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    text = re.sub(r'<\?include "[^"]*classes[46]\.json"\?>', json.dumps(classes), text)
    text = re.sub(r'<\?include "[^"]*"\?>', "[]", text)
    return json.loads(text)


class TestTheMainFiles:
    def test_ipv4_moves_its_classes_out_adds_the_reserved_class_and_computes_its_timers(
            self, tmp_path):
        main, text = _main("kea-dhcp4-moved.conf", tmp_path)
        p = L.plan(text, main, "IPv4")
        assert p["state"] == "change", p["refused"]
        assert p["classes_file"] == str(tmp_path / "nmas" / "classes4.json")
        names = [c["name"] for c in p["classes"]]
        assert names == ["nmas-discovery-pnp", "nmas-discovery", L.RESERVED]
        # The discovery classes are carried over exactly as Kea's file held them.
        before = _as_kea_reads(text, [])["Dhcp4"]["client-classes"]
        assert p["classes"][:2] == before
        dhcp4 = _as_kea_reads(p["candidate"], p["classes"])["Dhcp4"]
        assert {k: dhcp4.get(k) for k in L.globals_wanted("IPv4")} == L.globals_wanted("IPv4")
        assert "renew-timer" not in dhcp4 and "rebind-timer" not in dhcp4
        assert dhcp4["client-classes"][-1] == {"name": L.RESERVED, "test": "member('KNOWN')",
                                               "valid-lifetime": 7 * 86400}
        # Nothing else in the file moved.
        rest = {k: v for k, v in dhcp4.items() if k not in L.globals_wanted("IPv4")
                and k != "client-classes"}
        old = {k: v for k, v in _as_kea_reads(text, [])["Dhcp4"].items()
               if k not in L.globals_wanted("IPv4") and k not in ("client-classes",
                                                                   "renew-timer", "rebind-timer")}
        assert rest == old

    def test_ipv6_gains_the_include_and_its_preferred_lifetimes(self, tmp_path):
        main, text = _main("kea-dhcp6-moved.conf", tmp_path)
        p = L.plan(text, main, "IPv6")
        assert p["state"] == "change", p["refused"]
        assert p["classes"] == [{"name": L.RESERVED, "test": "member('KNOWN')",
                                 "valid-lifetime": 7 * 86400,
                                 "preferred-lifetime": int(3.5 * 86400)}]
        dhcp6 = _as_kea_reads(p["candidate"], p["classes"])["Dhcp6"]
        assert dhcp6["valid-lifetime"] == 4 * 3600 and dhcp6["preferred-lifetime"] == 2 * 3600
        assert (dhcp6["t1-percent"], dhcp6["t2-percent"]) == (0.5, 0.8)
        assert "renew-timer" not in dhcp6
        assert p["candidate"].index('"client-classes"') < p["candidate"].index('"subnet6"')

    @pytest.mark.parametrize("name,family", [("kea-dhcp4-moved.conf", "IPv4"),
                                             ("kea-dhcp6-moved.conf", "IPv6")])
    def test_the_installed_candidate_is_done(self, tmp_path, name, family):
        main, text = _main(name, tmp_path)
        p = L.plan(text, main, family)
        with open(p["classes_file"], "w", encoding="utf-8") as fh:
            fh.write(S.dump(p["classes"]))
        again = L.plan(p["candidate"], main, family)
        assert again["state"] == "done", again
        assert again["candidate"] == p["candidate"]

    def test_a_timer_not_alone_on_its_line_is_refused(self, tmp_path):
        main, text = _main("kea-dhcp6-moved.conf", tmp_path)
        text = text.replace('"renew-timer": 15768000,', '"renew-timer": 15768000, "x": 1,')
        p = L.plan(text, main, "IPv6")
        assert p["state"] == "refused" and "not alone on its line" in p["refused"]

    def test_a_timer_that_ends_its_map_is_refused(self, tmp_path):
        main, text = _main("kea-dhcp4-moved.conf", tmp_path)
        text = text.replace('"rebind-timer": 27594000,', '"rebind-timer": 27594000')
        p = L.plan(text, main, "IPv4")
        assert p["state"] == "refused" and "ends its map" in p["refused"]


class TestWhatKeaRuns:
    def _config(self, family):
        cfg = dict(L.globals_wanted(family))
        cfg["client-classes"] = [L.reserved_class(family)]
        return cfg

    @pytest.mark.parametrize("family", ["IPv4", "IPv6"])
    def test_on_when_kea_runs_every_part(self, family):
        assert L.running(self._config(family), family) == {"state": "on", "missing": []}

    def test_a_fixed_timer_or_a_missing_class_is_named(self):
        cfg = dict(self._config("IPv4"), **{"renew-timer": 15768000})
        cfg["client-classes"] = []
        r = L.running(cfg, "IPv4")
        assert r["state"] == "partial"
        assert any("renew-timer (15768000) beats the computed one" in m for m in r["missing"])
        assert any("no class mercury-reserved" in m for m in r["missing"])


def _tool():
    path = os.path.join(ROOT, "scripts", "nmas-kea-lifetimes")
    loader = importlib.machinery.SourceFileLoader("nmas_kea_lifetimes", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


class TestTheStepsProof:
    """The host step's last check: two snapshots differ only in the lifetimes, timers, the
    reserved class and the subnets' lifetimes."""

    def _snap(self, valid=31536000, classes=None, reservations=("r1",), leases=({"a": 1},),
              subnet_extra=None):
        sub = {"id": 10, "subnet": "10.10.10.0/24", "valid-lifetime": valid,
               **(subnet_extra or {})}
        return {"IPv4": {"config": {"valid-lifetime": valid, "renew-timer": 15768000,
                                    "client-classes": classes or [],
                                    "subnet4": [sub]},
                         "reservations": list(reservations), "leases": list(leases)}}

    def test_only_the_lifetimes_and_the_reserved_class_moved(self):
        a = self._snap()
        b = self._snap(valid=14400, classes=[L.reserved_class("IPv4")])
        del b["IPv4"]["config"]["renew-timer"]
        assert _tool().expected(a, b, 255) == []

    @pytest.mark.parametrize("change,words", [
        (dict(reservations=("r2",)), "IPv4: the reservations differ"),
        (dict(leases=({"a": 2},)), "IPv4: the leases differ"),
        (dict(classes=[{"name": "someone-else"}]), "a client class other than mercury-reserved"),
        (dict(subnet_extra={"pools": [{"pool": "10.10.10.5 - 10.10.10.9"}]}),
         "subnet 10 moved beyond its lifetimes and timers"),
    ])
    def test_anything_else_is_named(self, change, words):
        moved = _tool().expected(self._snap(), self._snap(**change), 255)
        assert any(words in m for m in moved), moved
