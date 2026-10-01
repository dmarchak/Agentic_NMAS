"""The redesign's landing page (Needs attention) and Help > About, on option A
(approved 2026-09-30), and the `app-pushed` reader behind About's "Pushed"
line and its Needs attention row.

The reader runs against REAL repositories (a bare origin and a clone), so
`git ls-remote`, `cat-file`, `merge-base` and `rev-list` answer as they do on
the host. The landing draws rows built by the real `attention.row()`.
"""

import html as html_mod
import json
import os
import re
import subprocess

import pytest

from modules import attention

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _client():
    import app as A
    return A.app.test_client()


def _text(html):
    return html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))


# ------------------------------------------------------------------ the reader

def _git(cwd, *args):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True,
                         env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                                  GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com"))
    return out.stdout.strip()


@pytest.fixture
def repos(tmp_path):
    """A bare origin with three commits on main, and a clone at the first."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True,
                   capture_output=True)
    shas = []
    for i in range(3):
        (work / "f").write_text(str(i))
        _git(work, "add", "f")
        _git(work, "commit", "-q", "-m", f"c{i}")
        shas.append(_git(work, "rev-parse", "HEAD"))
    _git(work, "push", "-q", "origin", "HEAD:main")
    return {"origin": origin, "work": work, "shas": shas}


class TestTheAppPushedReader:
    def test_at_the_tip(self, repos):
        from modules.readers import app_pushed as P

        v = P.judge(str(repos["work"]), repos["shas"][2])
        assert v["state"] == "at_tip" and v["behind"] == 0
        assert "was the tip of origin/main when last asked" in P.words(v)

    def test_behind_is_counted_when_the_tip_is_here(self, repos):
        from modules.readers import app_pushed as P

        v = P.judge(str(repos["work"]), repos["shas"][0])
        assert v["state"] == "behind" and v["behind"] == 2
        assert P.words(v).startswith("when last asked, the host ran 2 commits behind what was pushed")

    def test_a_tip_this_checkout_has_not_fetched_is_said_never_counted(self, repos, tmp_path):
        from modules.readers import app_pushed as P

        other = tmp_path / "other"
        subprocess.run(["git", "clone", "-q", str(repos["origin"]), str(other)], check=True,
                       capture_output=True)
        (other / "f").write_text("new")
        _git(other, "commit", "-qam", "c3")
        _git(other, "push", "-q", "origin", "HEAD:main")
        v = P.judge(str(repos["work"]), repos["shas"][2])
        assert v["state"] == "behind_unfetched" and v["behind"] is None
        assert "had not fetched" in P.words(v) and "unknown until it is fetched" in P.words(v)

    def test_a_local_commit_is_not_on_the_remote(self, repos):
        from modules.readers import app_pushed as P

        (repos["work"] / "f").write_text("local")
        _git(repos["work"], "commit", "-qam", "local only")
        local = _git(repos["work"], "rev-parse", "HEAD")
        v = P.judge(str(repos["work"]), local)
        assert v["state"] == "not_on_remote" and "was not on origin/main" in P.words(v)

    def test_a_remote_that_cannot_be_asked_raises_never_up_to_date(self, repos):
        from modules.readers import app_pushed as P

        _git(repos["work"], "remote", "set-url", "origin", str(repos["origin"]) + "-missing")
        with pytest.raises(RuntimeError, match="answered nothing"):
            P.judge(str(repos["work"]), repos["shas"][2])

    def test_the_reader_is_declared_and_announces_every_run(self):
        """Every completed check refreshes open pages, changed or not (the
        operator, 2026-10-01: "asked 7 min ago" from a reader asking every
        300 s, because an unchanged answer was not announced)."""
        from modules import invalidation, reader_job
        from modules.readers import app_pushed as P

        assert "modules.readers.app_pushed" in reader_job.DECLARED_MODULES
        assert P.READER.invalidates == ("app_version",) and "app_version" in invalidation.VOCABULARY
        assert P.READER.announce_if is None and P.READER.name not in reader_job.CHANGE_ONLY


# ---------------------------------------------------- the Needs attention row

def _cached(value, at="2026-09-30T10:00:00Z"):
    return {"state": "ok", "doc": {"last_good": {"value": value, "value_at": at},
                                   "stale_after_seconds": 750}}


class TestThePushedRow:
    def _source(self, value, running="a" * 40, monkeypatch=None):
        from routes import health
        monkeypatch.setattr(health, "_COMMIT", running)
        return attention.pushed_source(cached=_cached(value))

    def test_quiet_at_the_tip(self, monkeypatch):
        r = self._source({"running": "a" * 40, "tip": "a" * 40, "state": "at_tip", "behind": 0},
                         monkeypatch=monkeypatch)
        assert r["rows"] == [] and "was the tip of origin/main when last asked" in r["checked"]

    def test_behind_is_a_warning_whose_action_is_the_update_button(self, monkeypatch):
        r = self._source({"running": "a" * 40, "tip": "b" * 40, "state": "behind", "behind": 2,
                          "branch": "main"}, monkeypatch=monkeypatch)
        (row,) = r["rows"]
        assert row["level"] == "warning" and row["what"].startswith("When last asked, the host ran 2 commits behind")
        # The operator, 2026-09-30: the app knows it is behind, so its action
        # is the Update operation, never a terminal command.
        assert row["action"]["open"] == "app_update" and "command" not in row["action"]

    def test_not_on_the_remote_names_no_deploy(self, monkeypatch):
        r = self._source({"running": "a" * 40, "tip": "b" * 40, "state": "not_on_remote",
                          "behind": None}, monkeypatch=monkeypatch)
        (row,) = r["rows"]
        assert row["action"]["known"] is False and "command" not in row["action"]

    def test_a_comparison_for_another_commit_is_not_this_commits(self, monkeypatch):
        r = self._source({"running": "c" * 40, "tip": "b" * 40, "state": "behind", "behind": 5},
                         monkeypatch=monkeypatch)
        assert r["rows"] == [] and "not compared yet" in r["checked"]

    def test_nothing_stored_is_a_source_that_could_not_be_read(self):
        r = attention.pushed_source(cached={"state": "absent", "doc": None,
                                            "why": "no reader has written it"})
        assert r["state"] == "unreadable" and "not compared yet" in r["rows"][0]["cause"]

    def test_it_is_one_of_the_landings_sources(self):
        assert attention.pushed_source in attention.SOURCES

    def test_a_failed_ci_run_names_the_update_page_as_its_remedy(self, monkeypatch):
        # The Update page, never a terminal command (the operator, 2026-09-30):
        # it waits for CI itself when CI is still checking.
        from routes import health
        monkeypatch.setattr(health, "_COMMIT", "a" * 40)
        r = attention.ci_source(cached=_cached({"commit": "a" * 40, "state": "failed",
                                                "sentence": "run 9 failed: 2 tests"}))
        (row,) = r["rows"]
        assert row["level"] == "danger" and row["action"]["open"] == "app_update"
        assert "command" not in row["action"]


# ------------------------------------------------------------- the landing

def _page(rows, sources=None, unreadable=()):
    return {"ok": True, "headline": "", "rows": rows, "unreadable": list(unreadable),
            "sources": sources or [{"source": "reachability", "label": "Reachability", "state": "read",
                                    "read_at": "2026-09-30T10:00:00Z",
                                    "value_at": "2026-09-30T10:00:00Z", "took_ms": 3,
                                    "checked": "9 devices probed", "count": len(rows)}]}


@pytest.fixture
def landing(monkeypatch):
    state = {"page": _page([])}
    monkeypatch.setattr("modules.attention.needs_attention", lambda sources=None: state["page"])
    monkeypatch.setattr("modules.nsot.receipts.read",
                        lambda list_name, device="", limit=50: {"state": "absent", "rows": []})
    return state


class TestTheLanding:
    def test_nothing_wrong_is_one_positive_line_and_the_evidence_one_level_down(self, landing):
        r = _client().get("/v2/")
        html = r.get_data(as_text=True)
        assert r.status_code == 200
        text = _text(html)
        assert "Nothing needs attention" in text and "none reports anything a person must do" in text
        assert '<details class="evidence">' in html and "9 devices probed" in text

    def test_a_row_draws_its_level_cause_devices_and_one_action(self, landing):
        landing["page"] = _page([attention.row(
            source="reachability", key="s3", level="danger", what="s3 is not answering",
            cause="Three probes in a row missed it.", devices=["s3"], since=1790000000,
            action={"label": "Check the device's console", "command": "nmas-host clab -- uptime"})])
        html = _client().get("/v2/").get_data(as_text=True)
        text = _text(html)
        assert "Critical" in text and "s3 is not answering" in text and "Three probes" in text
        assert 'href="/v2/device/s3"' in html and "Open s3" in text
        assert 'x-data="copy" data-copy="nmas-host clab -- uptime"' in html
        assert 'class="att att-danger"' in html

    def test_an_action_with_no_known_remedy_is_drawn_as_such(self, landing):
        landing["page"] = _page([attention.row(source="x", key="k", level="unknown", what="W",
                                               cause="C", action={"label": "No remedy", "known": False})])
        assert 'class="att-label muted"' in _client().get("/v2/").get_data(as_text=True)

    def test_a_source_that_could_not_be_read_is_named(self, landing):
        landing["page"] = _page([], unreadable=["Grafana's alerts"])
        assert "1 could not be read: Grafana's alerts" in _text(_client().get("/v2/").get_data(as_text=True))

    def test_a_secret_a_row_quotes_is_masked(self, landing):
        landing["page"] = _page([attention.row(
            source="job_health", key="k", level="warning", what="a job failed",
            cause="its output: snmp-server community Pl4ntedC0mmunity RO",
            action={"label": "read it"})])
        html = _client().get("/v2/").get_data(as_text=True)
        assert "Pl4ntedC0mmunity" not in html and "snmp-server community" in html

    def test_the_list_refetches_on_every_reader_it_draws_from(self, landing):
        html = _client().get("/v2/attention").get_data(as_text=True)
        for key in ("job_health", "alerts", "freshness", "integration_health", "ci_verdict",
                    "app_version", "reachability", "netbox", "remote", "baselines", "drift"):
            assert f"nmas:{key} from:body" in html, key

    def test_recent_changes_come_from_the_receipts_and_an_unreadable_record_is_said(self, landing,
                                                                                    monkeypatch):
        monkeypatch.setattr("modules.nsot.receipts.read", lambda list_name, device="", limit=50: {
            "state": "ok", "rows": [{"device": "r6", "action": "deploy", "outcome": "deployed",
                                     "at": "2026-09-30T04:10:00Z", "actor": "operator@example.com",
                                     "program_lines": 4}]})
        text = _text(_client().get("/v2/").get_data(as_text=True))
        assert "Deploy r6 · deployed · 4 lines" in text and "by operator@example.com" in text
        monkeypatch.setattr("modules.nsot.receipts.read", lambda list_name, device="", limit=50: {
            "state": "unreadable", "rows": []})
        assert "could not be read. This is not the same as no changes" in \
            _text(_client().get("/v2/").get_data(as_text=True))

    def test_the_sidebar_leads_to_the_landing_and_help(self, landing):
        html = _client().get("/v2/").get_data(as_text=True)
        assert re.search(r'class="nav-item active" href="/v2/" aria-current="page"', html)
        assert 'href="/v2/help/about"' in html


class TestHelpAbout:
    def test_about_draws_each_fact_from_its_one_source(self, monkeypatch):
        from routes import health

        monkeypatch.setattr(health, "_COMMIT", "a" * 40)
        monkeypatch.setattr(health, "version_facts", lambda: {
            "running": "a" * 40, "started_at": "2026-09-30T09:41:00.000Z",
            "version": {"state": "ok", "detail": "running aaaaaaaaaa, the checkout's commit"},
            "ci": {"state": "verified", "sentence": "run 412 passed", "value_at": "2026-09-30T09:50:00Z"}})
        monkeypatch.setattr("modules.reader_job.read_cached", lambda name: _cached(
            {"running": "a" * 40, "tip": "b" * 40, "state": "behind", "behind": 2}))
        text = _text(_client().get("/v2/help/about").get_data(as_text=True))
        assert "aaaaaaaaaa" in text and "run 412 passed" in text
        assert "when last asked, the host ran 2 commits behind what was pushed" in text
        assert "Check again" in text               # always offered (the operator, 2026-09-30)
        assert "the checkout's commit" in text and "Who you are" in text
        assert "the top bar carries no commit" in text

    def test_the_top_bar_carries_no_commit(self, landing):
        from routes import health

        html = _client().get("/v2/").get_data(as_text=True)
        top = html.split('<header class="topbar">')[1].split("</header>")[0]
        assert (health._COMMIT or "zzzz")[:7] not in top

    def test_the_installation_card_refetches_on_its_readers(self):
        html = _client().get("/v2/help/installation").get_data(as_text=True)
        for key in ("ci_verdict", "app_version", "job_health"):
            assert f"nmas:{key} from:body" in html

    def test_health_version_and_about_share_one_composition(self):
        from routes import health
        src = open(os.path.join(ROOT, "routes", "v2.py"), encoding="utf-8").read()
        assert "health.version_facts()" in src
        assert json.loads(_client().get("/health/version").get_data(as_text=True))["running"] == \
            health._COMMIT


class TestThePolicy:
    @pytest.mark.parametrize("url", ["/v2/", "/v2/attention", "/v2/help/about", "/v2/help/installation"])
    def test_strict_and_no_inline_script_or_style(self, url, landing):
        from modules import csp

        r = _client().get(url)
        html = r.get_data(as_text=True)
        assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)
        assert not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html)


# ------------------------------------------------------------- the toast rule

TOAST_CALL = re.compile(r"\b(?:show)?[Tt]oast\w*\s*\(")


def _v2_population():
    """Every v2 template, and every script the v2 frame loads (read from
    base.html's own tags, so a script added there is scanned)."""
    tdir = os.path.join(ROOT, "templates", "v2")
    files = {os.path.join(tdir, n) for n in os.listdir(tdir) if n.endswith(".html")}
    base = open(os.path.join(tdir, "base.html"), encoding="utf-8").read()
    for rel in re.findall(r"filename='(js/[^']+\.js)'", base):
        if "/vendor/" not in rel:
            files.add(os.path.join(ROOT, "static", rel))
    return sorted(files)


class TestTheToastRule:
    """The operator, 2026-09-30 (NSOT_GUI_BRIEF section 6): a toast only
    ANNOUNCES a result the person might miss and links to one that stays; it
    never holds a result, never duplicates one drawn in place, and a failure
    is never toast-only (C84). The v2 screens make no toast call at all, so
    the first one must arrive with this rule in view."""

    def test_no_v2_screen_holds_a_result_in_a_toast(self):
        files = _v2_population()
        assert sum(f.endswith(".js") for f in files) >= 4      # the frame's own scripts
        assert sum(f.endswith(".html") for f in files) >= 8
        found = [f"{os.path.relpath(f, ROOT)}: {m.group(0)}" for f in files
                 for m in TOAST_CALL.finditer(open(f, encoding="utf-8").read())]
        assert found == []

    def test_the_scan_finds_a_toast(self):
        """The control: today's pages' own call, and a planted one, are found."""
        assert TOAST_CALL.search("showToast('Saved', 'success');")
        assert TOAST_CALL.search("NMAS.toast (msg)")
        assert not TOAST_CALL.search("the toast rule, written in a comment")
