"""P.7's second generator: telemetry rules, one per device and subscription,
each naming its device (the operator, 2026-10-01: four "gRPC telemetry stream
lost" alerts after the redeploy, and Needs attention said "the rule names no
device").

On the nine REAL fleet configs (the routers declare subscriptions 101 and 102,
the switches none) and the REAL hand-built rule from the ruler capture
(`tests/fixtures/grafana/ruler.json`): the population is the committed
configuration; every rule carries `device` and `subscription`, selects exactly
its stream, and alerts on NoData; the Grafana reader resolves its device from
the label, where the hand-built rule resolves none.
"""

import importlib.machinery
import importlib.util
import json
from types import SimpleNamespace

import pytest
import yaml


def _load():
    loader = importlib.machinery.SourceFileLoader("tel_rules_under_test",
                                                  "scripts/nmas-telemetry-rules")
    spec = importlib.util.spec_from_loader("tel_rules_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


T = _load()
FLEET = "tests/fixtures/configs/fleet"
HOSTS = ["r1", "r2", "r3", "r4", "r5", "s1", "s2", "s3", "s4"]


def _golden(h):
    return open(f"{FLEET}/{h}.cfg", encoding="utf-8").read()


def _expected(golden=None):
    ref = SimpleNamespace(name="Lab")
    return T.expected(population=lambda: [(ref, {"hostname": h}) for h in HOSTS],
                      golden=golden or (lambda r, h: _golden(h)))


class TestThePopulationIsTheCommittedConfiguration:
    def test_the_routers_stream_and_the_switches_do_not(self):
        want, quiet, errors = _expected()
        # Counted from the configs here, not by the code under test.
        for h in HOSTS:
            declared = [l.split()[-1] for l in _golden(h).splitlines()
                        if l.startswith("telemetry ietf subscription ")]
            assert want.get(h, []) == sorted(declared, key=int), h
        assert want["r2"] == ["101", "102"]
        assert quiet == ["r5", "s1", "s2", "s3", "s4"] and errors == []

    def test_an_unreadable_golden_is_an_error_never_a_quiet_device(self):
        def golden(r, h):
            if h == "r3":
                raise OSError("git show failed")
            return _golden(h)
        want, quiet, errors = _expected(golden)
        assert "r3" not in want and "r3" not in quiet
        assert errors == ["r3: its committed golden could not be read (git show failed)"]


class TestTheRuleNamesItsDevice:
    @pytest.fixture
    def doc(self):
        return T.build(_expected()[0], "prom-uid")

    def test_one_rule_per_device_and_subscription(self, doc):
        rules = doc["groups"][0]["rules"]
        pairs = {(r["labels"]["device"], r["labels"]["subscription"]) for r in rules}
        assert pairs == {(h, s) for h in ("r1", "r2", "r3", "r4") for s in ("101", "102")}

    def test_each_selects_exactly_its_stream_and_alerts_on_no_data(self, doc):
        for r in doc["groups"][0]["rules"]:
            d, s = r["labels"]["device"], r["labels"]["subscription"]
            assert r["data"][0]["model"]["expr"] == (
                f'count(last_over_time({{device="{d}", subscription="{s}"}}[90s]))')
            assert r["noDataState"] == "Alerting" and r["execErrState"] == "Alerting"
            assert r["data"][0]["datasourceUid"] == "prom-uid"
            assert d in r["title"] and d in r["annotations"]["summary"]

    def test_the_grafana_reader_resolves_the_device_from_the_label(self, doc):
        from modules.readers.grafana_alerts import _instance_device, device_source
        r = doc["groups"][0]["rules"][0]
        src = device_source(r["labels"], [r["data"][0]["model"]["expr"]])
        assert src["from"] == "label"
        assert _instance_device({"device": "r1", "subscription": "101"}, src) == {
            "device": "r1", "device_from": "label"}

    def test_the_hand_built_rule_resolved_no_device(self):
        # The seam's other side, from the REAL ruler capture: what the four
        # alerts said.
        from modules.readers.grafana_alerts import device_source
        ruler = json.load(open("tests/fixtures/grafana/ruler.json", encoding="utf-8"))
        old = next(r for groups in ruler.values() for g in groups for r in g["rules"]
                   if r["grafana_alert"]["title"] == "gRPC telemetry stream lost")
        exprs = [d["model"].get("expr", "") for d in old["grafana_alert"]["data"]]
        assert "count by (source)" in exprs[0]
        assert device_source(old.get("labels") or {}, exprs)["from"] == "address_or_none"

    def test_the_rendered_file_round_trips(self, doc):
        assert yaml.safe_load(T.render(doc)) == doc


class TestRefusalsAndTheCheck:
    def test_an_empty_population_is_refused(self):
        with pytest.raises(ValueError, match="the population is empty"):
            T.build({}, "prom-uid")

    def test_no_datasource_is_refused(self):
        with pytest.raises(ValueError, match="no Prometheus datasource UID"):
            T.build({"r1": ["101"]}, "")

    def test_the_check_names_each_stream(self):
        code, lines = T.check({("r1", "101"), ("r9", "101")}, {"r1": ["101", "102"]})
        assert code == T.EXIT_STALE
        assert lines == ["current    r1 subscription 101",
                         "MISSING    r1 subscription 102: configured to stream, no rule",
                         "EXTRA      r9 subscription 101: a rule for a stream no committed "
                         "configuration declares"]

    def test_current_is_exit_zero(self):
        assert T.check({("r1", "101")}, {"r1": ["101"]})[0] == T.EXIT_OK

    def test_main_writes_then_checks_current(self, monkeypatch, tmp_path, capsys):
        out = tmp_path / "nmas-telemetry.yaml"
        want = _expected()
        monkeypatch.setattr(T, "expected", lambda: want)
        assert T.main(["--datasource-uid", "prom-uid", "--out", str(out)]) == T.EXIT_OK
        said = capsys.readouterr().out
        assert "wrote 8 rule(s)" in said and "not streaming: s1" in said
        assert 'delete the hand-built rule "gRPC telemetry stream lost"' in said
        assert T.main(["--check", "--out", str(out)]) == T.EXIT_OK
        assert "telemetry rules current for 8 stream(s)" in capsys.readouterr().out

    def test_main_with_an_unreadable_golden_writes_nothing(self, monkeypatch, tmp_path, capsys):
        out = tmp_path / "nmas-telemetry.yaml"
        monkeypatch.setattr(T, "expected", lambda: ({"r1": ["101"]}, [], ["r3: boom"]))
        assert T.main(["--datasource-uid", "prom-uid", "--out", str(out)]) == T.EXIT_UNPROVEN
        assert not out.exists() and "UNPROVEN: r3: boom" in capsys.readouterr().out

    def test_the_datasource_is_read_from_grafana_when_none_is_given(self, monkeypatch,
                                                                    tmp_path, capsys):
        """The operator, 2026-10-01: the host step said `--datasource-uid <...>`."""
        from types import SimpleNamespace
        out = tmp_path / "nmas-telemetry.yaml"
        want = _expected()
        monkeypatch.setattr(T, "expected", lambda: want)
        front = {"defaultDatasource": "Prometheus", "datasources": {
            "Prometheus": {"uid": "efwpn8hr7sfeob", "type": "prometheus"},
            "Loki": {"uid": "lokiuid", "type": "loki"}}}

        class G:
            def is_configured(self):
                return True

            def _get(self, path):
                assert path == "api/frontend/settings"
                return {"ok": True, "response": SimpleNamespace(json=lambda: front)}

        monkeypatch.setattr("modules.integrations.grafana.GrafanaIntegration", G)
        assert T.main(["--out", str(out)]) == T.EXIT_OK
        assert "datasource Prometheus (efwpn8hr7sfeob), read from Grafana" in capsys.readouterr().out
        assert "efwpn8hr7sfeob" in out.read_text()

    def test_two_prometheus_sources_and_no_default_is_refused_naming_them(self):
        from types import SimpleNamespace
        front = {"defaultDatasource": "Loki", "datasources": {
            "Prom A": {"uid": "a1", "type": "prometheus"},
            "Prom B": {"uid": "b2", "type": "prometheus"},
            "Loki": {"uid": "l", "type": "loki"}}}
        g = SimpleNamespace(is_configured=lambda: True, _get=lambda p: {
            "ok": True, "response": SimpleNamespace(json=lambda: front)})
        with pytest.raises(ValueError) as exc:
            T.grafana_datasource(client=g)
        assert "2 Prometheus datasources and none is the default (Prom A a1, Prom B b2)" \
            in str(exc.value)

    def test_the_generated_file_is_never_committed(self):
        import subprocess
        r = subprocess.run(["git", "check-ignore", "-q",
                            "deploy/grafana/provisioning/alerting/nmas-telemetry.yaml"])
        assert r.returncode == 0
