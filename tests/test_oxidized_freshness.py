"""The Oxidized freshness comparison: the gate, the signal, the way through.

Two properties were named **before** the code was written, and both are
asserted here rather than reasoned about:

1. **The gate's own wrong-and-looks-right state** is *"the comparison could
   not run and the sanitiser wrote anyway"*. Every way that can happen is a
   refusal, never a pass — `TestTheComparisonCouldNotRunIsARefusal`.
2. **The noise floor.** The gate compares the **raw** Oxidized config, not the
   sanitiser's output. `TestItComparesTheRawConfigNotTheSanitisedOne` shows
   both halves: the sanitised artefact really would fire for ever (the control
   that proves the problem is real), and the raw one does not.

And a third the design had to defend against by construction: an
authorisation that outlives what it authorised —
`TestAnAuthorisationCoversOneDivergenceOnly`.
"""

import json
import os

import pytest

from modules.nsot import freshness

FLEET = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")

OLD = "2026-09-20T10:00:00+00:00"
NEW = "2026-09-24T10:00:00+00:00"

BASE = """hostname r9
!
interface GigabitEthernet2
 ip address 10.255.0.32 255.255.255.0
!
router ospf 1
 network 10.255.0.0 0.0.0.255 area 0
!
end
"""


def _read(name):
    with open(os.path.join(FLEET, name), encoding="utf-8") as fh:
        return fh.read()


def _sanitised(text, kind="switch"):
    """What `oxidized-to-config.sh` writes, in miniature.

    Its own header, the re-injected `no shutdown`, and the re-issued RSA key.
    Faithful to the three transformations that matter for this question, which
    is all this needs to be: it is here to show that comparing the sanitiser's
    OUTPUT is the wrong comparison, not to reimplement the sanitiser.
    """
    out = ["!", "! r9 - from Oxidized HEAD abc1234", "!"]
    for line in text.splitlines():
        out.append(line)
        if line.strip().startswith("ip address"):
            out.append(" no shutdown")
    if kind == "switch":
        out += ["!", "ip domain-name rcn.lab",
                "crypto key generate rsa modulus 2048", "ip ssh version 2"]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------


class TestItComparesTheRawConfigNotTheSanitisedOne:
    """The noise floor, both halves.

    A gate pointed at the sanitiser's output fires on the sanitiser's own
    rules — permanently, on every device, from the first run. It would be
    switched off within a week, which is how the drift checker came to be off
    for 24 days.
    """

    def test_the_sanitised_output_really_would_fire_forever(self):
        """THE CONTROL. Without this the claim is theoretical.

        If this ever passes as *equivalent*, the argument for comparing the
        raw config has evaporated and this module should be revisited — not
        quietly left pointing at whichever artefact is handy.
        """
        from modules.nsot import roundtrip

        raw = _read("s1.cfg")
        result = roundtrip.configs_equivalent(raw, _sanitised(raw))
        assert not result["equal"], (
            "the sanitised output no longer differs from its own input — the "
            "reason this gate compares the raw config has changed")
        injected = [ln for ln in result["only_right"]
                    if "no shutdown" in ln or "crypto key generate" in ln]
        assert injected, ("the differences are not the sanitiser's own "
                          "injections, so this control is measuring something "
                          "else")

    def test_a_provenance_header_alone_would_have_fired_too(self):
        """MEASURED, and the measurement corrected the design twice.

        First claim: *the header is free, `strip_for_diff` drops comments.*
        Wrong — it drops bare `!` and keeps `! text`.

        Second claim, after measuring: *the golden's own header fires.* Also
        wrong, and in the more interesting direction — `! Golden config — …`
        is in `DIFF_PREFIXES`, so NMAS's own header was handled. What is not
        handled is **Oxidized's** metadata header: the side this project does
        not write, and therefore the side nobody had a prefix list for.

        Without `strip_provenance_comments()` the gate fires on that line for
        every device on every run — the noise floor, arriving inside the
        artefact chosen to avoid it.
        """
        from modules.nsot import roundtrip

        raw = _read("s1.cfg")
        from_oxidized = "! Oxidized: node s1 model ios 2026-09-24\n" + raw
        assert not roundtrip.configs_equivalent(raw, from_oxidized)["equal"], (
            "strip_for_diff now drops foreign comment lines — if that is "
            "deliberate, strip_provenance_comments() may be redundant; it is "
            "not a reason to stop applying it without checking")
        row = freshness.compare_device("l", "s1", raw, OLD, from_oxidized, NEW)
        assert row["verdict"] == freshness.MATCH

    def test_nmas_own_header_was_already_handled(self):
        """The half that was fine, pinned so the distinction survives."""
        from modules.nsot import roundtrip

        raw = _read("s1.cfg")
        golden = "! Golden config — s1 (10.255.1.1)\n" + raw
        assert roundtrip.configs_equivalent(raw, golden)["equal"]

    def test_the_raw_config_against_its_own_golden_is_a_match(self):
        raw = _read("r1.cfg")
        row = freshness.compare_device("l", "r1", raw, OLD, raw, NEW)
        assert row["verdict"] == freshness.MATCH
        assert row["verdict"] not in freshness.BLOCKING


class TestContentDecidesAndTimeIsContext:
    """*"Oxidized is newer"* fires constantly and means nothing on its own."""

    def test_same_content_newer_oxidized_is_not_a_finding(self):
        """The normal case: Oxidized polls, so its copy is almost always newer."""
        row = freshness.compare_device("l", "r9", BASE, OLD, BASE, NEW)
        assert row["verdict"] == freshness.MATCH

    def test_differs_and_oxidized_newer_is_the_finding(self):
        changed = BASE.replace("network 10.255.0.0 0.0.0.255 area 0",
                               "network 10.255.0.0 0.0.0.255 area 1")
        row = freshness.compare_device("l", "r9", BASE, OLD, changed, NEW)
        assert row["verdict"] == freshness.UNAPPROVED
        assert row["verdict"] in freshness.BLOCKING
        assert row["only_right"], "the finding must name what differs"

    def test_differs_and_golden_newer_is_a_poll_race(self):
        changed = BASE.replace("area 0", "area 1")
        row = freshness.compare_device("l", "r9", changed, NEW, BASE, OLD)
        assert row["verdict"] == freshness.POLL_RACE
        assert row["verdict"] not in freshness.BLOCKING

    def test_a_poll_race_still_says_what_it_costs(self):
        """It does not block, and it is never silent.

        The file about to be written predates an approved change, so the next
        redeploy loses it. Self-correcting at the next poll, which is why it
        is not a refusal — and worth a sentence, which is why it is not a
        shrug.
        """
        changed = BASE.replace("area 0", "area 1")
        row = freshness.compare_device("l", "r9", changed, NEW, BASE, OLD)
        assert "predates the approved change" in row["reason"]


class TestTheComparisonCouldNotRunIsARefusal:
    """Named before the code was written. Five causes, five refusals."""

    def test_no_golden_is_inconclusive_and_blocks(self):
        """A device the gate could not check is not a device it passed.

        A pending device is exactly this: onboarded, in the manifest, and with
        no golden until phase 2 captures one.
        """
        row = freshness.compare_device("l", "r9", None, "", BASE, NEW)
        assert row["verdict"] == freshness.INCONCLUSIVE
        assert row["verdict"] in freshness.BLOCKING
        assert "no golden" in row["reason"]

    def test_an_unreadable_oxidized_copy_is_inconclusive(self):
        row = freshness.compare_device("l", "r9", BASE, OLD, None, NEW)
        assert row["verdict"] == freshness.INCONCLUSIVE

    def test_differs_with_an_unreadable_timestamp_blocks(self):
        """*Golden newer* is the only benign reading, and it needs proving."""
        changed = BASE.replace("area 0", "area 1")
        row = freshness.compare_device("l", "r9", changed, "not a date",
                                       BASE, NEW)
        assert row["verdict"] == freshness.INCONCLUSIVE
        assert "timeline" in row["reason"]

    def test_the_control_parseable_times_reach_a_verdict(self):
        """THE CONTROL for the one above: it is the time that is missing.

        Without this, a compare_device() that refused everything would satisfy
        the refusal test and leave the module with no acceptance at all.
        """
        changed = BASE.replace("area 0", "area 1")
        row = freshness.compare_device("l", "r9", changed, NEW, BASE, OLD)
        assert row["verdict"] == freshness.POLL_RACE

    def test_a_broken_comparator_is_inconclusive_not_a_match(self, monkeypatch):
        from modules.nsot import roundtrip

        def _boom(*_a, **_k):
            raise RuntimeError("section parse failed")

        monkeypatch.setattr(roundtrip, "configs_equivalent", _boom)
        row = freshness.compare_device("l", "r9", BASE, OLD, BASE, NEW)
        assert row["verdict"] == freshness.INCONCLUSIVE

    def test_an_empty_population_refuses(self, monkeypatch, tmp_path):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr(freshness, "_goldens", lambda _l: {})
        result = freshness.check("l", supplied={})
        assert result["ok"] is False
        assert "vacuously" in result["error"]


class TestEveryDeviceLandsInExactlyOneBucket:
    """*"all 9 clean"* over a ten-device fleet reads identically to the truth."""

    def _list(self, monkeypatch, tmp_path, goldens):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        store = {}
        for name, (text, at) in goldens.items():
            path = tmp_path / f"{name}.cfg"
            path.write_text(text, encoding="utf-8")
            store[name] = {"hostname": name, "path": str(path), "saved_at": at}
        monkeypatch.setattr(freshness, "_goldens", lambda _l: store)

    def test_counts_reconcile_against_the_population(self, monkeypatch, tmp_path):
        self._list(monkeypatch, tmp_path,
                   {"r1": (BASE, OLD), "r2": (BASE, OLD)})
        report = freshness.check("l", supplied={"r1": BASE, "r2": BASE,
                                                "r3": BASE})
        assert report["population"] == 3
        assert report["checked"] == 3
        assert sum(report["counts"].values()) == 3
        # r3 has no golden: named, in a bucket, and blocking.
        assert report["blocked"] == ["r3"]

    def test_a_shortfall_is_reported_as_a_defect(self):
        """A verdict missing makes the whole report a defect, not a pass.

        Exercised against `reconcile()` directly with a row removed, because a
        reconciliation tested only through the loop that feeds it is tested by
        a loop that never drops anything — the shape that let "all 9 clean"
        stand over a ten-device fleet.
        """
        report = {"ok": True, "devices": [
            {"device": "r1", "verdict": freshness.MATCH},
            {"device": "r2", "verdict": freshness.MATCH}]}
        result = freshness.reconcile(report, ["r1", "r2", "r3"])
        assert result["ok"] is False
        assert "r3" in result["defect"]

    def test_the_control_a_complete_report_reconciles(self):
        """Without this, a reconcile() that refused everything would pass."""
        report = {"ok": True, "devices": [
            {"device": "r1", "verdict": freshness.MATCH},
            {"device": "r2", "verdict": freshness.MATCH}]}
        result = freshness.reconcile(report, ["r1", "r2"])
        assert result["ok"] is True
        assert result["counts"][freshness.MATCH] == 2

    def test_a_device_whose_comparison_raises_still_gets_a_bucket(
            self, monkeypatch, tmp_path):
        self._list(monkeypatch, tmp_path, {"r1": (BASE, OLD)})
        real = freshness.compare_device

        def _raise(list_name, hostname, *a, **k):
            if hostname == "r1":
                raise RuntimeError("boom")
            return real(list_name, hostname, *a, **k)

        monkeypatch.setattr(freshness, "compare_device", _raise)
        report = freshness.check("l", supplied={"r1": BASE})
        assert report["checked"] == 1
        assert report["blocked"] == ["r1"]

    def test_the_scan_finds_something(self, monkeypatch, tmp_path):
        """A floor. An all-inconclusive run would satisfy every refusal test."""
        self._list(monkeypatch, tmp_path,
                   {"r1": (BASE, OLD), "r2": (BASE, OLD)})
        report = freshness.check("l", supplied={"r1": BASE, "r2": BASE})
        assert report["counts"][freshness.MATCH] == 2, (
            "no device reached a positive verdict — a suite of 'nothing is "
            "wrong' assertions cannot tell a healthy system from an absent one")


class TestAnAuthorisationCoversOneDivergenceOnly:
    """The sixth wrong-and-looks-right state, designed out rather than fixed.

    A per-device flag would let the NEXT divergence through while the gate
    reported `authorised` — a wrong thing wearing a passing result.
    """

    @pytest.fixture
    def listdir(self, monkeypatch, tmp_path):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        return tmp_path

    def _divergence(self, list_name="l"):
        changed = BASE.replace("area 0", "area 1")
        row = freshness.compare_device(list_name, "r9", BASE, OLD, changed, NEW)
        assert row["verdict"] == freshness.UNAPPROVED
        return changed, row["fingerprint"]

    def test_authorising_lets_that_divergence_through(self, listdir):
        changed, fp = self._divergence()
        assert freshness.authorise("l", "r9", fp, actor="dm@x",
                                   reason="approved at the console")["ok"]
        row = freshness.compare_device("l", "r9", BASE, OLD, changed, NEW)
        assert row["verdict"] == freshness.AUTHORISED
        assert row["verdict"] not in freshness.BLOCKING

    def test_a_different_divergence_on_the_same_device_is_not_covered(self, listdir):
        """THE POINT. Authorising one change must not authorise the next."""
        _changed, fp = self._divergence()
        freshness.authorise("l", "r9", fp, actor="dm@x", reason="ok")
        later = BASE.replace("area 0", "area 2").replace(
            "hostname r9", "hostname r9\nsnmp-server community sneaky RW")
        row = freshness.compare_device("l", "r9", BASE, OLD, later, NEW)
        assert row["verdict"] == freshness.UNAPPROVED, (
            "a second, different divergence was covered by the first "
            "authorisation — the gate is reporting a pass for a change "
            "nobody saw")

    def test_an_authorisation_does_not_cross_lists(self, listdir):
        """Two lists may each hold an `r1`, as the template secrets found."""
        changed, fp = self._divergence("one")
        freshness.authorise("one", "r9", fp, actor="dm@x", reason="ok")
        row = freshness.compare_device("two", "r9", BASE, OLD, changed, NEW)
        assert row["verdict"] == freshness.UNAPPROVED

    def test_it_expires(self, listdir):
        changed, fp = self._divergence()
        freshness.authorise("l", "r9", fp, actor="dm@x", reason="ok", hours=1)
        path = listdir / "l" / freshness.AUTHORISATION_FILE
        records = json.loads(path.read_text())
        records[0]["expires_at"] = "2020-01-01T00:00:00+00:00"
        path.write_text(json.dumps(records))
        row = freshness.compare_device("l", "r9", BASE, OLD, changed, NEW)
        assert row["verdict"] == freshness.UNAPPROVED

    def test_it_refuses_without_an_actor_or_a_reason(self, listdir):
        _changed, fp = self._divergence()
        assert not freshness.authorise("l", "r9", fp, actor="", reason="x")["ok"]
        assert not freshness.authorise("l", "r9", fp, actor="a", reason="")["ok"]
        assert not freshness.authorise("l", "r9", "", actor="a", reason="x")["ok"]

    def test_there_is_no_switch(self):
        """The way through is per-divergence and recorded, or there is none.

        A settings flag or a `--force` would be the drift checker's off switch
        with better manners: one action, no record, and it covers everything
        that comes after it.

        **Parsed, not grepped.** The first version was a substring search and
        matched this module's own paragraph explaining why there is no switch
        — a pattern that can appear in English needs an anchor, and the better
        the comment the more likely it quotes the thing it explains.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(freshness))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
                names.update(a.arg for a in node.args.args)
                names.update(a.arg for a in node.args.kwonlyargs)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.add(node.value)
        assert "authorise" in names, (
            "the way through is not in this module at all — this check would "
            "pass against an empty file")
        for bypass in ("force", "skip_gate", "gate_enabled", "gate_disabled",
                       "bypass", "override"):
            assert bypass not in names, (
                f"{bypass!r} is a real name in the freshness module — the way "
                "through is authorise(), per divergence, recorded")


class TestTimeParsing:
    def test_unparseable_is_none_not_epoch(self):
        assert freshness.parse_time("not a date") is None
        assert freshness.parse_time("") is None

    def test_the_shapes_oxidized_and_git_actually_emit(self):
        assert freshness.parse_time("2026-09-24T10:00:00+01:00") is not None
        assert freshness.parse_time("2026-09-24T10:00:00Z") is not None
        assert freshness.parse_time("2026-09-24 10:00:00 UTC") is not None
        assert freshness.parse_time("2026-09-24 10:00:00 +0100") is not None

    def test_a_trailing_utc_is_not_read_as_naive(self):
        """`%Z` parses "UTC" and returns a NAIVE datetime — the one outcome
        that must not look aware."""
        parsed = freshness.parse_time("2026-09-24 10:00:00 UTC")
        assert parsed.tzinfo is not None
        assert parsed.utcoffset().total_seconds() == 0


class TestTheReadClient:
    def test_an_empty_body_is_a_refusal_not_an_empty_config(self, monkeypatch):
        """Oxidized answers 200 with nothing for a node it never fetched.

        "The device has no configuration" is a claim this client is in no
        position to make — and an empty string compared against a golden is a
        difference in every line.
        """
        from modules.integrations.oxidized import OxidizedIntegration

        client = OxidizedIntegration()
        monkeypatch.setattr(client, "_get", lambda *_a, **_k: {
            "ok": True, "response": type("R", (), {"text": "   \n"})()})
        result = client.fetch_config("r1")
        assert result["ok"] is False
        assert "empty" in result["error"]

    def test_a_node_never_fetched_is_absent_from_the_times(self, monkeypatch):
        from modules.integrations.oxidized import OxidizedIntegration

        client = OxidizedIntegration()
        payload = [{"name": "r1", "time": "2026-09-24 10:00:00 UTC"},
                   {"name": "r2", "time": ""}]
        monkeypatch.setattr(client, "_get", lambda *_a, **_k: {
            "ok": True, "response": type("R", (), {"json": lambda self: payload})()})
        times = client.node_times()
        assert times["times"] == {"r1": "2026-09-24 10:00:00 UTC"}
        assert "r2" not in times["times"], (
            "an unknown time and an epoch are different facts")


class TestTheRoutesOverHttp:
    """Exercised over HTTP, because the seam between a tested render and a
    tested function is where four defects have lived in this project."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        (tmp_path / "lab").mkdir()
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(tmp_path / "lab"))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("modules.agent_timers.save", lambda d: None)
        monkeypatch.setattr(freshness, "_goldens", lambda _l: self._store(tmp_path))

        import app as nmas

        nmas.app.config["TESTING"] = False
        return nmas.app.test_client()

    @staticmethod
    def _store(tmp_path):
        path = tmp_path / "r1.cfg"
        path.write_text(BASE, encoding="utf-8")
        return {"r1": {"hostname": "r1", "path": str(path), "saved_at": OLD}}

    def test_the_route_exists_at_the_path_the_script_calls(self, client):
        """A blueprint route's full path appears nowhere in its source.

        `url_prefix` is applied at registration, so the only authority is the
        url_map — and `nmas-oxidized-freshness` posts to a literal string.
        """
        import app as nmas

        rules = {str(r) for r in nmas.app.url_map.iter_rules()}
        assert "/freshness/gate" in rules
        assert "/freshness/report" in rules
        assert "/freshness/authorise" in rules

    def test_an_empty_gate_request_is_refused_not_passed(self, client):
        resp = client.post("/freshness/gate", json={"configs": {}})
        assert resp.status_code == 400
        assert "vacuously" in resp.get_json()["error"]

    def test_nothing_blocking_is_200(self, client):
        resp = client.post("/freshness/gate", json={"configs": {"r1": BASE}})
        assert resp.status_code == 200
        assert resp.get_json()["blocked"] == []

    def test_something_blocking_is_409(self, client):
        changed = BASE.replace("area 0", "area 1")
        resp = client.post("/freshness/gate", json={"configs": {"r1": changed}})
        assert resp.status_code == 409
        assert resp.get_json()["blocked"] == ["r1"]

    def test_three_outcomes_three_codes(self, client):
        """200 / 409 / 4xx-5xx. *"The fleet has drifted"* and *"I could not
        tell you whether it has"* are the two most different answers this can
        give, and the census already made the mistake of sharing a code."""
        ok = client.post("/freshness/gate", json={"configs": {"r1": BASE}})
        blocked = client.post("/freshness/gate", json={
            "configs": {"r1": BASE.replace("area 0", "area 1")}})
        unproven = client.post("/freshness/gate", json={"configs": {}})
        assert len({ok.status_code, blocked.status_code,
                    unproven.status_code}) == 3

    def test_config_lines_leaving_here_are_redacted(self, client):
        """A difference list carries the same secrets as either config."""
        leaky = BASE.replace("hostname r9",
                             "hostname r9\nsnmp-server community s3cr3tcomm RO")
        resp = client.post("/freshness/gate", json={"configs": {"r1": leaky}})
        assert b"s3cr3tcomm" not in resp.data, (
            "a secret reached the response on a difference line")
        assert b"snmp-server community" in resp.data, (
            "the line was dropped rather than masked — the operator can no "
            "longer see WHAT differs, which is the whole report")

    def test_authorise_requires_an_identity(self, client):
        """403 before 400: identity ahead of input validation."""
        resp = client.post("/freshness/authorise", json={})
        assert resp.status_code == 403


class TestTheGateCanActuallyReachItsOwnFinding:
    """Found by a negative control aimed at something else.

    The first version read Oxidized's timestamps **only on the signal path**,
    so on the gate path every differing device came back `inconclusive`: the
    gate could never say *"a change nobody approved"*, and could never tell one
    from a poll race. It would have refused every difference, benign ones
    included — which is exactly how a gate comes to be switched off.

    It blocked either way, so no test asserting a refusal could see it. What
    saw it was forcing an unknown timestamp to read as a poll race and finding
    that the route test asserting **409** broke, when that test should not have
    depended on a timestamp at all.
    """

    @pytest.fixture
    def listdir(self, monkeypatch, tmp_path):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        path = tmp_path / "r1.cfg"
        path.write_text(BASE, encoding="utf-8")
        monkeypatch.setattr(freshness, "_goldens", lambda _l: {
            "r1": {"hostname": "r1", "path": str(path), "saved_at": OLD}})
        monkeypatch.setattr(
            "modules.nsot.credential_rotation.sync_targets",
            lambda _l: {"ok": True, "targets": [
                {"hostname": "r1", "oxidized_node": "r1"}]})
        return tmp_path

    def _with_oxidized(self, monkeypatch, times):
        from modules.integrations.oxidized import OxidizedIntegration

        monkeypatch.setattr(OxidizedIntegration, "is_configured", lambda _s: True)
        monkeypatch.setattr(OxidizedIntegration, "node_times",
                            lambda _s: {"ok": True, "times": times})

    def test_the_gate_reports_unapproved_when_the_time_is_known(
            self, listdir, monkeypatch):
        self._with_oxidized(monkeypatch, {"r1": NEW})
        report = freshness.check("l", supplied={
            "r1": BASE.replace("area 0", "area 1")})
        assert report["counts"][freshness.UNAPPROVED] == 1, (
            "the gate cannot reach its own finding — every difference is "
            "inconclusive, so it refuses benign poll races too")

    def test_the_gate_reports_a_poll_race_when_the_golden_is_newer(
            self, listdir, monkeypatch):
        self._with_oxidized(monkeypatch, {"r1": OLD})
        path = listdir / "r1.cfg"
        path.write_text(BASE.replace("area 0", "area 1"), encoding="utf-8")
        monkeypatch.setattr(freshness, "_goldens", lambda _l: {
            "r1": {"hostname": "r1", "path": str(path), "saved_at": NEW}})
        report = freshness.check("l", supplied={"r1": BASE})
        assert report["counts"][freshness.POLL_RACE] == 1
        assert report["blocked"] == [], "a poll race is not a refusal"

    def test_without_oxidized_a_difference_is_inconclusive_and_says_why(
            self, listdir, monkeypatch):
        """Not a pass, and not silently 'unapproved' either.

        With no index there are no timestamps, so the tool genuinely cannot
        tell an unapproved change from a race. It says so, names the cause,
        and blocks — a one-line settings fix rather than a mystery.
        """
        from modules.integrations.oxidized import OxidizedIntegration

        monkeypatch.setattr(OxidizedIntegration, "is_configured", lambda _s: False)
        report = freshness.check("l", supplied={
            "r1": BASE.replace("area 0", "area 1")})
        assert report["counts"][freshness.INCONCLUSIVE] == 1
        assert report["blocked"] == ["r1"]
        assert any("not configured" in e for e in report["errors"])

    def test_the_node_name_is_used_not_the_hostname(self, listdir, monkeypatch):
        """Oxidized's index is keyed on the node name, which `router.db` may
        set to the management IP rather than the hostname."""
        monkeypatch.setattr(
            "modules.nsot.credential_rotation.sync_targets",
            lambda _l: {"ok": True, "targets": [
                {"hostname": "r1", "oxidized_node": "10.255.1.11"}]})
        self._with_oxidized(monkeypatch, {"10.255.1.11": NEW})
        report = freshness.check("l", supplied={
            "r1": BASE.replace("area 0", "area 1")})
        assert report["counts"][freshness.UNAPPROVED] == 1


# ---------------------------------------------------------------------------
# The signal's render, executed
# ---------------------------------------------------------------------------

dukpy = pytest.importorskip("dukpy")


def _lift(page, *names):
    """Pull whole function bodies out of the shipped page source."""
    out = []
    for name in names:
        start = page.index(f"function {name}(")
        depth, i, seen = 0, page.index("{", start), False
        while i < len(page):
            if page[i] == "{":
                depth += 1
                seen = True
            elif page[i] == "}":
                depth -= 1
                if seen and depth == 0:
                    break
            i += 1
        out.append(page[start:i + 1])
    return "\n".join(out)


@pytest.fixture(scope="module")
def signal_js():
    """`freshnessSignalHtml`, from **the source the browser executes**.

    Read through `with_loaded_scripts`, so this follows the §0b extraction
    into `static/js/gen/` rather than passing by finding nothing in a template
    that no longer holds the script.
    """
    from tests.js_source import with_loaded_scripts

    import app as nmas

    page = with_loaded_scripts(
        nmas.app.test_client().get("/").get_data(as_text=True))
    # A stub DOM: duktape has no document, and `_freshEscape` uses one.
    stub = """
    var document = { createElement: function () {
      return { set textContent(v) { this._t = v === null || v === undefined
                 ? '' : String(v); },
               get innerHTML() { return this._t
                 .replace(/&/g, '&amp;').replace(/</g, '&lt;')
                 .replace(/>/g, '&gt;'); } };
    } };
    """
    return stub + _lift(page, "_freshEscape", "freshnessSignalHtml") + """
    var _FRESH_VERDICTS = {
      match: ['bg-success', 'approved'],
      poll_race: ['bg-info', 'poll race'],
      authorised: ['bg-warning', 'authorised'],
      unapproved: ['bg-danger', 'UNAPPROVED'],
      inconclusive: ['bg-secondary', 'inconclusive'] };
    """


def _render(js, data):
    return dukpy.evaljs(js + f"\nfreshnessSignalHtml({json.dumps(data)});")


class TestTheSignalRenders:
    """What lands on screen, not what the endpoint carries.

    Three guards in one feature each hid the same data in this project, and
    every server test passed at each stage — the boundary kept being drawn
    above the last remaining guard.
    """

    def test_a_failed_query_is_not_rendered_as_nothing_diverged(self, signal_js):
        """The panel's own wrong-and-looks-right state.

        `ok: false` must not draw the clean message. Same correction as the
        pending banner, and as *"all 9 clean"* over a ten-device fleet.
        """
        html = _render(signal_js, {"ok": False, "error": "Oxidized unreachable"})
        assert "could not run" in html
        assert "not</em> the same as" in html or "not the same as" in html
        assert "matches the approved config" not in html

    def test_the_control_a_clean_report_says_so(self, signal_js):
        """Without this, a renderer that always warned would pass the above."""
        html = _render(signal_js, {
            "ok": True, "summary": "2 of 2 checked", "devices": [
                {"device": "r1", "verdict": "match"},
                {"device": "r2", "verdict": "match"}]})
        assert "matches the approved config" in html
        assert "could not run" not in html

    def test_an_unapproved_device_is_named_with_what_differs(self, signal_js):
        html = _render(signal_js, {
            "ok": True, "summary": "", "devices": [{
                "device": "r3", "verdict": "unapproved",
                "reason": "Oxidized's copy is newer",
                "only_right": ["router ospf 1 :: network 10.0.0.0 area 9"],
                "only_left": [], "fingerprint": "abcdef0123456789ff"}]})
        assert "r3" in html
        assert "UNAPPROVED" in html
        assert "area 9" in html
        assert "abcdef0123456789" in html, (
            "the fingerprint is how an authorisation names THIS divergence")

    def test_the_renderer_has_a_caller_outside_itself(self):
        """`loadOnboardPending` shipped with its only callers inside the banner
        it drew, so the banner could appear only after using a control that
        appeared only once it had. A renderer whose callers are its own
        children is unreachable."""
        from tests.js_source import read_shipped

        js = read_shipped(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static", "js", "gen", "partials__freshness_signal.1.js"))
        assert "DOMContentLoaded" in js and "loadFreshnessSignal" in js


# ---------------------------------------------------------------------------
# The caller's reading of the exit code
# ---------------------------------------------------------------------------

SANITISER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "patches", "oxidized-to-config.sh.new")


def _gate_case_block():
    """The sanitiser's own `case $gate_rc in … esac`, lifted verbatim.

    The shipped source, not a paraphrase — the defect was in this block and a
    reimplementation of it would have passed at every stage.
    """
    src = open(SANITISER, encoding="utf-8").read()
    start = src.index("case $gate_rc in")
    end = src.index("esac", start) + len("esac")
    return src[start:end]


class TestOnlyOneIsDriftedAndOnlyZeroIsClean:
    """Measured 2026-09-24: the helper was not on PATH, the shell returned
    **127**, and the run printed

        ./oxidized-to-config.sh: line 380: nmas-oxidized-freshness: command not found
        REFUSED - one or more devices carry a change nobody approved.

    The helper defines 0/1/2 precisely to keep *"the fleet has drifted"* apart
    from *"I could not tell you whether it has"*, and the caller collapsed it
    one line later with `elif [ $gate_rc -ne 0 ]` — **at the only place an
    exit code is actually read.** A missing binary reported as unapproved
    drift sends the operator to look at their devices.

    Third instance of two outcomes of different severity sharing a report,
    after the census's missing baseline exiting 1 and *"Not a git repo, or
    nothing to commit"*.
    """

    @staticmethod
    def _run(code):
        import shutil
        import subprocess

        bash = shutil.which("bash")
        if not bash:
            pytest.skip("bash not available")
        script = ('FRESH="${FRESH:-nmas-oxidized-freshness}"\n'
                  'gate_rc="$1"\n' + _gate_case_block() + '\necho CLEAN\n')
        proc = subprocess.run([bash, "-c", script, "_", str(code)],
                              capture_output=True, text=True, timeout=30)
        return proc.returncode, proc.stdout + proc.stderr

    def test_zero_proceeds(self):
        rc, out = self._run(0)
        assert rc == 0 and "CLEAN" in out

    def test_one_is_the_only_code_reported_as_drift(self):
        rc, out = self._run(1)
        assert rc == 1
        assert "change nobody approved" in out

    def test_two_is_could_not_ask(self):
        rc, out = self._run(2)
        assert rc == 2
        assert "could not run" in out
        assert "nobody approved" not in out

    def test_127_names_the_missing_helper_and_is_not_drift(self):
        """THE MEASURED FAILURE. A missing binary is never a finding about a
        device, and the generic could-not-ask message would send the reader to
        the NMAS, which is fine."""
        rc, out = self._run(127)
        assert rc == 2
        assert "not installed or not on PATH" in out
        assert "nmas-oxidized-freshness" in out
        assert "nobody approved" not in out, (
            "a missing helper is being reported as unapproved drift — this is "
            "the 2026-09-24 failure exactly")

    def test_an_undefined_code_is_could_not_ask_and_names_itself(self):
        """The helper defines three codes; a fourth means something went wrong
        that neither end anticipated, which is the definition of could-not-ask
        rather than of drift."""
        rc, out = self._run(3)
        assert rc == 2
        assert "exit 3" in out
        assert "nobody approved" not in out

    def test_every_outcome_is_distinguishable_from_the_others(self):
        """The floor: three codes must produce three readings. A block that
        printed one message for everything would satisfy several assertions
        above by accident."""
        seen = {code: self._run(code) for code in (0, 1, 2, 127)}
        assert len({rc for rc, _ in seen.values()}) == 3, \
            "clean / drifted / could-not-ask must not share an exit status"
        assert len({out for _, out in seen.values()}) == 4, \
            "127 must say something 2 does not, or naming it bought nothing"
