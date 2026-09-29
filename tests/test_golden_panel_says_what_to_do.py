"""The Device tab's golden panel says what to DO (the operator, 2026-09-28).

1. The legacy-store notice stated a state and a condition for clearing it,
   and no action, while the tool knew r5 was retired. Each legacy-only file
   now carries its state and ONE action, decided from the record: a retired
   device (a `Retired-Device:` commit) has residue to delete; a device in the
   inventory is captured; anything else is neither, and is not called safe.
2. The Baselines table collapses to the newest row that can be re-applied,
   the rest behind a toggle, never cut (it stopped at ten, silently, and the
   host has twelve).
3. Each row says what its commit recorded it EARNED, and the twelve that
   predate that say "not recorded", never implying fine. A WITHDRAWN baseline
   (the newest on the host held r2 broken by hand for C70) is refused by the
   restore wherever the ref is read, drawn with its reason and the commands
   that delete it, and drawn as deleted once its tag is gone.
"""

import json
import os

import pytest

from modules.nsot import repo as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = "Lab"
INVENTORY = [{"hostname": "r1", "ip": "203.0.113.1", "platform": "cisco_ios"},
             {"hostname": "r2", "ip": "203.0.113.2", "platform": "cisco_ios"}]


def _commit(repo, msg):
    R.git(repo, "add", "-A", "--", "golden", ".nsot")
    R.git(repo, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q",
          "--allow-empty", "-m", msg)
    return R.git(repo, "rev-parse", "HEAD")[1].strip()


def _tag(repo, name, sha):
    R.git(repo, "-c", "user.name=t", "-c", "user.email=t@x", "tag", "-a", name,
          "-m", f"network baseline {name}", sha)


def build_golden_panel_lab(monkeypatch, tmp_path):
    """A real repository with baselines in every state (not recorded, earned,
    withdrawn, withdrawn and deleted), and a legacy store holding a retired
    device (r5) and one nobody knows (r9). The payload check's provider too."""
    import app as A
    from modules.nsot import record_exceptions

    list_dir = tmp_path / "lab"
    repo = str(list_dir / "config_repo")
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    # A module that imported the function by name keeps its own binding;
    # LISTS_DIR is read at call time by every caller (CLAUDE.md's rule).
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: LIST)
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.device.load_saved_devices", lambda p: [dict(d) for d in INVENTORY])
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(d) for d in INVENTORY])
    R.init_repo(repo)
    for d in INVENTORY:
        with open(os.path.join(repo, "golden", f"{d['hostname']}.cfg"), "w") as fh:
            fh.write(f"hostname {d['hostname']}\n")
    shas = {}
    shas["old"] = _commit(repo, "golden: baseline via save_all\n\nSource: save_all\nActor: t")
    _tag(repo, "baseline/20260921T000000Z", shas["old"])
    with open(os.path.join(repo, "golden", "r1.cfg"), "a") as fh:
        fh.write("! the deleted one\n")
    shas["deleted"] = _commit(repo, "golden: baseline via save_all\n\nSource: save_all")
    with open(os.path.join(repo, "golden", "r1.cfg"), "a") as fh:
        fh.write("! earned\n")
    shas["earned"] = _commit(repo, "golden: 2 device(s) via save_all\n\nSource: save_all\n"
                                   "Intent-Match: yes (2 of 2)\nBaseline: earned")
    _tag(repo, "baseline/20260926T000000Z", shas["earned"])
    with open(os.path.join(repo, "golden", "r2.cfg"), "a") as fh:
        fh.write("! broken by hand\n")
    shas["withdrawn"] = _commit(repo, "golden: baseline via save_all\n\nSource: save_all")
    _tag(repo, "baseline/20260927T000000Z", shas["withdrawn"])
    # r5's golden, then its retirement removing it, as nmas-retire does.
    with open(os.path.join(repo, "golden", "r5.cfg"), "w") as fh:
        fh.write("hostname r5\ninterface Loopback0\n ip address 192.0.2.5 255.255.255.255\n")
    shas["r5_golden"] = _commit(repo, "golden: r5\n\nSource: capture")
    R.git(repo, "rm", "-q", "--", "golden/r5.cfg")
    _commit(repo, "retire: r5 -- outside our boundary\n\nRetired-Device: r5\nSource: retire")
    monkeypatch.setattr(record_exceptions, "WITHDRAWN_BASELINES", {
        shas["withdrawn"]: {"list": LIST, "tag": "baseline/20260927T000000Z",
                            "finding": "C70", "decided": "2026-09-28", "by": "the operator",
                            "why": "it records r2 broken by hand"},
        shas["deleted"]: {"list": LIST, "tag": "baseline/20260922T000000Z",
                          "finding": "C70", "decided": "2026-09-28", "by": "the operator",
                          "why": "a planted deletion"},
    })
    legacy = list_dir / "golden_configs"
    legacy.mkdir(parents=True)
    for host, ip in (("r5", "203.0.113.5"), ("r9", "203.0.113.9")):
        (legacy / f"{host}.cfg").write_text(
            f"! Golden config — {host} ({ip})\nhostname {host}\n"
            "interface Loopback0\n ip address 192.0.2.5 255.255.255.255\n",
            encoding="utf-8")
    return {"client": A.app.test_client(), "repo": repo, "shas": shas,
            "legacy": str(legacy)}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    return build_golden_panel_lab(monkeypatch, tmp_path)


def _baselines(lab):
    d = lab["client"].get("/golden/baselines").get_json()
    assert d["ok"], d
    return {b["tag"]: b for b in d["baselines"]}


class TestEachBaselineSaysWhatItEarned:
    def test_the_decision_is_read_from_its_commit(self, lab):
        b = _baselines(lab)
        assert b["baseline/20260926T000000Z"]["decision"] == "earned"
        assert b["baseline/20260926T000000Z"]["intent_match"] == "yes (2 of 2)"
        old = b["baseline/20260921T000000Z"]
        assert old["decision"] == "unrecorded"
        assert "nothing says every device was at its committed intent" in old["decision_detail"]

    def test_every_baseline_is_carried_none_cut(self, lab):
        assert len(_baselines(lab)) == 4, "three tags and one deletion"


class TestAWithdrawnBaseline:
    def test_it_is_drawn_withdrawn_with_the_commands_that_delete_it(self, lab):
        w = _baselines(lab)["baseline/20260927T000000Z"]
        assert w["withdrawn"]["why"] == "it records r2 broken by hand" and not w["deleted"]
        (cmd,) = w["delete_commands"]
        assert "tag -d baseline/20260927T000000Z && " in cmd
        assert "push origin --delete refs/tags/baseline/20260927T000000Z" in cmd

    def test_a_deleted_one_is_drawn_where_it_was(self, lab):
        d = _baselines(lab)["baseline/20260922T000000Z"]
        assert d["deleted"] and d["commit"] == lab["shas"]["deleted"]

    @pytest.mark.parametrize("route", ["/golden/restore/preview", "/golden/restore/apply"])
    def test_both_restore_routes_refuse_it_and_send_nothing(self, lab, route):
        r = lab["client"].post(route, json={"ref": "baseline/20260927T000000Z",
                                            "devices": ["r2"], "confirmations": {"r2": "x"}})
        assert r.status_code == 409, r.get_data(as_text=True)[:300]
        out = r.get_json()
        assert out["withdrawn"]["tag"] == "baseline/20260927T000000Z"
        assert "nothing was sent" in out["error"]

    def test_the_control_a_current_baseline_is_not_refused(self, lab):
        r = lab["client"].post("/golden/restore/preview",
                               json={"ref": "baseline/20260926T000000Z", "devices": ["r2"]})
        assert r.status_code != 409, r.get_data(as_text=True)[:300]

    def test_the_device_chooser_does_not_offer_it(self, lab):
        refs = [p["ref"] for p in R.device_restore_points(lab["repo"], "r2")]
        assert "baseline/20260926T000000Z" in refs
        assert "baseline/20260927T000000Z" not in refs

    def test_the_host_record_is_a_full_sha(self):
        from modules.nsot.record_exceptions import WITHDRAWN_BASELINES
        sha, w = next(iter(WITHDRAWN_BASELINES.items()))
        assert len(sha) == 40 and w["tag"] == "baseline/20260927T154517Z"


class TestTheLegacyStoreSaysWhatToDo:
    def test_each_file_carries_its_state_and_one_action(self, lab):
        d = lab["client"].get("/golden/legacy_store").get_json()
        by = {e["hostname"]: e for e in d["only_legacy"]}
        assert by["r5"]["state"] == "retired"
        assert by["r5"]["action"].endswith(f"rm {os.path.join(lab['legacy'], 'r5.cfg')}")
        # What survives, where, and what is lost: the operator's removal rule.
        sha = lab["shas"]["r5_golden"][:7]
        assert "survives in the repository as golden/r5.cfg" in by["r5"]["action"]
        assert f"git show {sha}" in by["r5"]["action"]
        assert "loses nothing but the copy" in by["r5"]["action"]

    def test_the_migrations_verbatim_backup_is_the_survival_it_names_first(self, lab):
        """The host's case: the migration committed each legacy file verbatim."""
        legacy = os.path.join(lab["legacy"], "r5.cfg")
        backup = os.path.join(lab["repo"], ".nsot", "migration-backup")
        os.makedirs(backup, exist_ok=True)
        with open(legacy, encoding="utf-8") as fh, \
                open(os.path.join(backup, "golden_configs-r5.cfg"), "w", encoding="utf-8") as out:
            out.write(fh.read())
        R.git(lab["repo"], "add", "-f", "--", ".nsot/migration-backup/golden_configs-r5.cfg")
        R.git(lab["repo"], "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q",
              "-m", "migration: backup")
        by = {e["hostname"]: e for e in
              lab["client"].get("/golden/legacy_store").get_json()["only_legacy"]}
        assert "survives VERBATIM" in by["r5"]["action"]
        assert "golden_configs-r5.cfg" in by["r5"]["action"] and "rm " in by["r5"]["action"]

    def test_a_file_whose_lines_are_nowhere_else_is_kept_not_deleted(self, lab):
        with open(os.path.join(lab["legacy"], "r5.cfg"), "a", encoding="utf-8") as fh:
            fh.write("snmp-server location only-here\n")
        by = {e["hostname"]: e for e in
              lab["client"].get("/golden/legacy_store").get_json()["only_legacy"]}
        assert "differs from all 1 committed version(s)" in by["r5"]["action"]
        assert "Keep a copy" in by["r5"]["action"] and "rm " not in by["r5"]["action"]
        assert by["r9"]["state"] == "unknown" and "nothing here says it is safe" in by["r9"]["action"]

    def test_a_device_still_managed_is_captured_not_deleted(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [
            *INVENTORY, {"hostname": "r9", "ip": "203.0.113.9"}])
        by = {e["hostname"]: e for e in
              lab["client"].get("/golden/legacy_store").get_json()["only_legacy"]}
        assert by["r9"]["state"] == "managed" and "Capture it" in by["r9"]["action"]
        assert "rm " not in by["r9"]["action"]


def _js(fn_names):
    from tests.payload_render import lift, shipped
    src = shipped("partials__golden_repo.1.js")
    return "\n".join(lift(src, n) for n in fn_names)


FNS = ("_gEsc", "_gWhen", "_gBaselineClaim", "_gBaselineCoverage", "_gCredWarning",
       "_gBaselineDecision", "_gBaselineRow", "_gBaselineUsable", "_gToggle",
       "_gBaselinesHtml")


class TestTheShippedTable:
    def _draw(self, lab):
        import dukpy
        payload = lab["client"].get("/golden/baselines").get_json()["baselines"]
        return dukpy.evaljs(_js(FNS) + "\n_gBaselinesHtml(" + json.dumps(payload) + ")")

    def test_it_collapses_to_the_newest_usable_row_and_hides_the_rest(self, lab):
        html = self._draw(lab)
        shown, older = html.split("data-baselines-older", 1)
        # The withdrawn newest row is SHOWN beside the one that would be used.
        assert "baseline/20260927T000000Z" in shown and "baseline/20260926T000000Z" in shown
        assert "baseline/20260921T000000Z" in older and "baseline/20260922T000000Z" in older
        assert "Show 1 older baseline(s)" in html and "Show withdrawn (1)" in html
        # The deleted row sits behind the withdrawn toggle, not among the older.
        withdrawn = html[html.index("data-baselines-withdrawn>"):]
        assert "baseline/20260922T000000Z" in withdrawn
        assert "baseline/20260922T000000Z" not in html[:html.index("data-baselines-withdrawn>")]

    def test_the_rows_say_what_they_are(self, lab):
        html = self._draw(lab)
        assert 'data-baseline-row="withdrawn"' in html and "not offered for re-apply" in html
        assert "push origin --delete" in html
        assert 'data-baseline-row="deleted"' in html and "stays in history" in html
        assert 'data-baseline-decision="earned"' in html
        assert 'data-baseline-decision="unrecorded"' in html and "decision not recorded" in html
        # The credential column stays on every re-applicable row.
        assert html.count("credentials current") == 2
        # A withdrawn row offers no re-apply.
        withdrawn = html[html.index('data-baseline-row="withdrawn"'):]
        withdrawn = withdrawn[:withdrawn.index("</tr>")]
        assert "confirmBaselineRestore" not in withdrawn

    def test_a_withdrawn_row_is_one_line_with_its_reasoning_on_hover(self, lab):
        html = self._draw(lab)
        row = html[html.index('data-baseline-row="withdrawn"'):]
        row = row[:row.index("</tr>")]
        visible = row.split('title="Withdrawn by the operator: it records r2 broken by hand"', 1)[1]
        assert "withdrawn</span> 2026-09-28 (C70)" in visible
        assert "it records r2 broken by hand" not in visible, "the reasoning is on hover only"
        assert "loses only the restore point" in row and "<details" in row

    def test_when_none_can_be_reapplied_it_is_said_once(self, lab):
        import dukpy
        payload = lab["client"].get("/golden/baselines").get_json()["baselines"]
        for b in payload:
            if not b.get("deleted") and not b.get("withdrawn"):
                b["credential_stale"] = ["s1"]
        html = dukpy.evaljs(_js(FNS) + "\n_gBaselinesHtml(" + json.dumps(payload) + ")")
        assert html.count("No stored baseline can be re-applied") == 1
        head = html[:html.index("data-baselines-older")]
        # The newest kept row is shown, with the withdrawn row above it.
        assert "baseline/20260926T000000Z" in head and "baseline/20260921T000000Z" not in head

    def test_the_panel_no_longer_cuts_at_ten(self):
        from tests.payload_render import shipped
        assert ".slice(0, 10)" not in shipped("partials__golden_repo.3.js")


class TestNoUsableBaselineIsANeedsAttentionRow:
    """The operator (2026-09-28): the fleet had no usable baseline and the
    panel said it twelve times without saying it once."""

    def test_the_reader_judges_each_baseline_and_names_the_usable_one(self, lab):
        from modules.readers import baseline_usability as BU

        v = BU.read(lists=[LIST], previous={})["lists"][LIST]
        assert v["usable"] == "baseline/20260926T000000Z" and v["count"] == 3
        judged = {b["tag"]: b for b in v["baselines"]}
        assert judged["baseline/20260927T000000Z"]["withdrawn"]
        assert not judged["baseline/20260927T000000Z"]["usable"]

    def test_it_recomputes_only_when_head_or_the_tags_move(self, lab, monkeypatch):
        from modules.readers import baseline_usability as BU

        first = BU.read(lists=[LIST], previous={})
        calls = []
        monkeypatch.setattr(BU, "judge", lambda *a: calls.append(a) or {})
        again = BU.read(lists=[LIST], previous=first)
        assert calls == [] and again == first, "nothing moved: the stored answer stands"
        _tag(lab["repo"], "baseline/20260928T000000Z", lab["shas"]["earned"])
        BU.read(lists=[LIST], previous=first)
        assert len(calls) == 1, "a new tag is a new question"

    def _cached(self, value):
        return {"state": "ok", "doc": {"last_good": {
            "value": {"lists": {LIST: value}}, "value_at": "2026-09-28T20:00:00Z"}}}

    def _none_usable(self):
        return {"usable": "", "count": 2, "baselines": [
            {"tag": "baseline/20260927T154517Z", "withdrawn": True, "stale": []},
            {"tag": "baseline/20260925T201032Z", "withdrawn": False, "stale": ["s1"]}]}

    def test_none_usable_is_one_row_naming_the_newest_and_the_remedy(self):
        from modules.attention import _baseline_usability_row

        out = _baseline_usability_row(LIST, cached=self._cached(self._none_usable()))
        (r,) = out["rows"]
        assert r["what"] == "No stored baseline can be re-applied"
        assert "baseline/20260925T201032Z" in r["cause"] and "s1" in r["cause"]
        assert "Withdrawn: baseline/20260927T154517Z" in r["cause"]
        assert "Save All" in r["action"]["label"]

    def test_a_usable_baseline_is_no_row(self):
        from modules.attention import _baseline_usability_row

        out = _baseline_usability_row(LIST, cached=self._cached(
            {"usable": "baseline/x", "count": 1, "baselines": []}))
        assert out["rows"] == [] and "baseline/x can be re-applied" in out["checked"]

    def test_the_row_appears_when_no_decision_is_recorded_yet(self, monkeypatch):
        """The host's state: no `Baseline:` decision in any commit. The first
        version returned before asking, so the row could never be drawn."""
        from modules import attention, reader_job

        monkeypatch.setattr("modules.config.get_current_list_name", lambda: LIST)
        monkeypatch.setattr(reader_job, "read_cached",
                            lambda name: self._cached(self._none_usable()))
        res = attention.baseline_source(log_fn=lambda: "")
        assert [r["what"] for r in res["rows"]] == ["No stored baseline can be re-applied"]


class TestANoticeSaysWhatToDoOrIsNotDrawn:
    """The operator's addendum to the presentation rule (2026-09-28): "can be
    retired" stated a conclusion and stopped. Scheduled work is a plan item
    (7.8), never a notice."""

    def _card(self, payload):
        import dukpy
        from tests.payload_render import lift, shipped
        src = shipped("partials__golden_repo.3.js")
        js = lift(shipped("partials__golden_repo.1.js"), "_gEsc") + "\n" + lift(src, "_gLegacyStoreCard")
        return dukpy.evaljs(js + "\n_gLegacyStoreCard(" + json.dumps(payload) + ")")

    def test_a_retirable_store_draws_nothing(self):
        assert self._card({"ok": True, "legacy_files": 8, "only_legacy": [],
                           "retirable": True}) == ""

    def test_a_store_holding_a_sole_copy_draws_each_action(self, lab):
        payload = lab["client"].get("/golden/legacy_store").get_json()
        html = self._card(payload)
        assert 'data-legacy-state="retired"' in html and "rm " in html
        assert 'data-legacy-state="unknown"' in html and "Find out what it was" in html

    def test_the_removal_is_a_plan_item(self):
        plan = open(os.path.join(ROOT, "docs", "NSOT_STAGE7_PLAN.md"), encoding="utf-8").read()
        assert "The legacy golden store (`golden_configs/`) and the header-scan fallback" in plan
