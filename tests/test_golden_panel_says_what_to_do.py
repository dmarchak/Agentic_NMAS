"""The Device tab's golden panel says what to DO (the operator, 2026-09-28).

1. The legacy-store notice stated a state and a condition for clearing it,
   and no action, while the tool knew r5 was retired. Each legacy-only file
   now carries its state and ONE action, decided from the record: a retired
   device (a `Retired-Device:` commit) has residue to delete; a device in the
   inventory is captured; anything else is neither, and is not called safe.
2. Today's Baselines table collapsed to the newest row that could be re-applied,
   never cut (it had stopped at ten, silently, and the host has twelve). It left
   at 7.8 (2026-10-17): History › Baselines draws every baseline the
   `baseline-usability` reader judged, one line each.
3. Each baseline says what its commit recorded it EARNED, and the twelve that
   predate that say "not recorded", never implying fine. A WITHDRAWN baseline
   (the newest on the host held r2 broken by hand for C70) is refused by the
   restore wherever the ref is read, and judged with its reason.
"""

import json
import os

import pytest

from modules.nsot import repo as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = "Lab"
INVENTORY = [{"hostname": "r1", "ip": "203.0.113.1", "platform": "cisco_ios"},
             {"hostname": "r2", "ip": "203.0.113.2", "platform": "cisco_ios"}]
#: Every device's account at every baseline; `rotate_r1()` moves r1's after them.
ACCOUNT = "username admin privilege 15 secret 9 $9$Zq7baselinehash$abcdefghijklmnop"
ROTATED = "username admin privilege 15 secret 9 $9$Zq7rotatedhash$qrstuvwxyz012345"


def rotate_r1(repo):
    """A rotation committed after every baseline (C315's provider): each one
    now predates r1's credential, so the panel's stale and guarded lists hold
    r1, the state the payload check's fixture had never reached."""
    path = os.path.join(repo, "golden", "r1.cfg")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace(ACCOUNT, ROTATED))
    return _commit(repo, "golden: r1 credential rotation\n\nSource: rotation\nActor: t")


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
            fh.write(f"hostname {d['hostname']}\n{ACCOUNT}\n")
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
    """Each baseline as History › Baselines draws it: the `baseline-usability` reader's
    judgement (today's /golden/baselines, which the Baselines panel read, left at 7.8)."""
    from modules.readers import baseline_usability as BU

    v = BU.read(lists=[LIST], previous={})["lists"][LIST]
    assert "error" not in v, v
    return {b["tag"]: b for b in v["baselines"]}


class TestEachBaselineSaysWhatItEarned:
    def test_the_decision_is_read_from_its_commit(self, lab):
        b = _baselines(lab)
        assert b["baseline/20260926T000000Z"]["decision"] == "earned"
        old = b["baseline/20260921T000000Z"]
        assert old["decision"] == "unrecorded"
        assert "nothing says every device was at its committed intent" in old["decision_detail"]

    def test_every_baseline_is_carried_none_cut(self, lab):
        assert set(_baselines(lab)) == {"baseline/20260921T000000Z", "baseline/20260926T000000Z",
                                        "baseline/20260927T000000Z"}, "three tags, none cut"


class TestAWithdrawnBaseline:
    def test_it_is_judged_withdrawn_with_its_reason_and_never_usable(self, lab):
        w = _baselines(lab)["baseline/20260927T000000Z"]
        assert w["withdrawn"] and w["withdrawn_why"] == "it records r2 broken by hand"
        assert not w["usable"]

    def test_the_restore_refuses_it_wherever_the_ref_is_read_and_sends_nothing(self, lab):
        """THE restore plan (every preview: a device's Restore from…, History's Re-apply…) and
        the apply's own targets (`restore.build_targets`, which the restore job runs) each refuse
        it by name. Today's two routes over them left at 7.8 (2026-10-17)."""
        from modules.nsot.restore import WithdrawnBaseline, build_targets
        from routes.golden import restore_plan

        for call in (lambda: restore_plan(LIST, "baseline/20260927T000000Z", ["r2"]),
                     lambda: build_targets(LIST, "baseline/20260927T000000Z", ["r2"])):
            with pytest.raises(WithdrawnBaseline) as got:
                call()
            assert got.value.record["tag"] == "baseline/20260927T000000Z"
            assert "nothing was sent" in str(got.value)

    def test_the_control_a_current_baseline_is_not_refused(self, lab):
        from routes.golden import restore_plan

        plan = restore_plan(LIST, "baseline/20260926T000000Z", ["r2"])   # raises nothing
        assert plan["preview"]["what"], plan

    def test_the_device_chooser_does_not_offer_it(self, lab):
        refs = [p["ref"] for p in R.device_restore_points(lab["repo"], "r2")]
        assert "baseline/20260926T000000Z" in refs
        assert "baseline/20260927T000000Z" not in refs

    def test_the_host_record_is_a_full_sha(self):
        from modules.nsot.record_exceptions import WITHDRAWN_BASELINES
        sha, w = next(iter(WITHDRAWN_BASELINES.items()))
        assert len(sha) == 40 and w["tag"] == "baseline/20260927T154517Z"


class TestTheLegacySurvivalCheck:
    """What a legacy file's removal would lose, said with where it survives (C176): the one
    check retire uses for a device's file in the deprecated store. Its route and card left at
    7.8 (2026-10-12); the check moved to `modules/nsot/retire.py` with its only user."""

    def _surv(self, lab, host):
        from modules.nsot import retire
        return retire.legacy_survives("lab", host, os.path.join(lab["legacy"], f"{host}.cfg"))

    def test_a_file_whose_golden_holds_it_survives_and_says_where(self, lab):
        # What survives, where, and what is lost: the operator's removal rule.
        s = self._surv(lab, "r5")
        sha = lab["shas"]["r5_golden"][:7]
        assert s["state"] == "survives"
        assert "survives in the repository as golden/r5.cfg" in s["words"]
        assert f"git show {sha}" in s["words"] and "loses nothing but the copy" in s["words"]

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
        s = self._surv(lab, "r5")
        assert s["state"] == "survives" and "survives VERBATIM" in s["words"]
        assert "golden_configs-r5.cfg" in s["words"]

    def test_a_file_whose_lines_are_nowhere_else_is_lost_if_deleted(self, lab):
        with open(os.path.join(lab["legacy"], "r5.cfg"), "a", encoding="utf-8") as fh:
            fh.write("snmp-server location only-here\n")
        s = self._surv(lab, "r5")
        assert s["state"] == "lost"
        assert "differs from all 1 committed version(s)" in s["words"]
        r9 = self._surv(lab, "r9")
        assert r9["state"] == "lost" and "never held golden/r9.cfg" in r9["words"]


# Today's Baselines panel and its renderer (the collapsed table, the withdrawn and deleted rows,
# "said once") left at 7.8 (2026-10-17, P7-21), with their tests. History › Baselines draws the
# reader's rows, one line each with why under it (tests/test_history_v2.py), and Needs
# attention says "no stored baseline can be re-applied" once (below).


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

    def test_the_removal_is_a_plan_item(self):
        plan = open(os.path.join(ROOT, "docs", "NSOT_STAGE7_PLAN.md"), encoding="utf-8").read()
        assert "The legacy golden store (`golden_configs/`) and the header-scan fallback" in plan
