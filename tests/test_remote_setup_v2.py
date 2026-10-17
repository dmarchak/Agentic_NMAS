"""History › Remote set-up on v2 (C631, 2026-10-10): connecting a network's existing remote, the
write probe, what a first push would publish and its typed acknowledgement, and automatic
pushing, through the real app on a temporary store (tests/test_settings_v2's `networks`).

The acts are `modules/nsot/remote.py`'s own (adopt, verify, first_push_preview, acknowledge,
enable_auto_push). What reaches GitHub is replaced at its edge: `remote.verify`'s checks and the
history scan's result, shaped as the module tests shape them; nothing here leaves the host.
"""

import json
import re

import pytest

from modules.nsot import remote as R
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

BASE = "/v2/history/remote/setup"
FP = "fp-0123456789ab"


def _post(n, path, data):
    r = n["client"].post(path, data=data, headers={"HX-Request": "true"})
    return r, re.sub(r"\s+", " ", r.get_data(as_text=True))


def _get(n, path):
    r = n["client"].get(path)
    return r, re.sub(r"\s+", " ", r.get_data(as_text=True))


GOOD = {"list": "Branch", "ssh_alias": "github-branch", "owner": "acct",
        "repo": "branch-config", "branch": "main", "key_path": "~/.ssh/branch_deploy"}


def _connected(n):
    r, html = _post(n, f"{BASE}/connect", GOOD)
    assert r.status_code == 200 and "Connected:" in html, html
    return html


@pytest.fixture
def scan(monkeypatch):
    """The history scan's result as `scan_history_secrets` returns it: one live community
    on two devices, one hash (never gated); and git's counts."""
    got = {"rows": [{"device": "r1", "kind": "snmp_community", "recoverable": True,
                     "distinct": 1, "live": 2, "dead": 0},
                    {"device": "r1", "kind": "secret_hash", "recoverable": False,
                     "distinct": 3, "live": 3, "dead": 0}],
           "blobs_scanned": 4, "gated_kinds": ["snmp_community"],
           "live_values": [{"kind": "snmp_community", "fingerprint": FP, "recoverable": True,
                            "devices": ["r1", "r2"], "at_head": ["r1"]}]}
    monkeypatch.setattr(R, "scan_history_secrets", lambda *a, **k: got)
    monkeypatch.setattr(R, "_blobs_of_golden", lambda *a, **k: {})
    monkeypatch.setattr(R, "snmp_access_modes", lambda *a, **k: {})
    monkeypatch.setattr(R, "_run", lambda *a, **k: type(
        "P", (), {"stdout": "7\n", "stderr": "", "returncode": 0})())
    return got


class TestTheCard:
    def test_history_s_header_opens_it_and_with_no_remote_it_is_the_connect_form(self, networks):
        from modules.nsot import listref

        _r, page = _get(networks, "/v2/history")
        assert "Set up the remote…" in page and 'id="remote-setup"' in page
        r, card = _get(networks, f"{BASE}?list=Branch")
        assert r.status_code == 200 and "Remote set-up" in card and "Connect" in card
        assert "never edits the host's SSH configuration" in card
        for words in (w for _s, w in R.SETUP_SHAPES.values()):
            assert words.replace("'", "&#39;") in card
        assert listref.exists("Branch")

    def test_an_unknown_network_is_refused_by_name_before_anything_resolves(self, networks):
        """The list guard (C51) answers it, before the route: nothing read, nothing made."""
        r, html = _get(networks, f"{BASE}?list=Nowhere")
        assert r.status_code == 404 and "There is no device list named 'Nowhere'" in html
        assert r.headers["Content-Type"].startswith("application/json")
        assert not (networks["dir"] / "lists" / "nowhere").exists()


class TestConnect:
    def test_a_good_remote_is_recorded_and_its_facts_drawn(self, networks):
        html = _connected(networks)
        assert "acct/branch-config · main" in html and "github-branch" in html
        assert "never passed" in html and "Push refuses until it has" in html
        saved = json.loads((networks["dir"] / "lists" / "branch" / "remote.json").read_text())
        assert saved["owner"] == "acct" and saved["managed_by_nmas"] is False

    def test_an_alias_read_as_an_ssh_option_is_refused_and_nothing_written(self, networks):
        r, html = _post(networks, f"{BASE}/connect", dict(GOOD, ssh_alias="-oProxyCommand=x"))
        assert r.status_code == 409 and "Not done:" in html and "ssh alias" in html
        assert not (networks["dir"] / "lists" / "branch" / "remote.json").exists()

    def test_a_second_connect_is_refused(self, networks):
        _connected(networks)
        r, html = _post(networks, f"{BASE}/connect", GOOD)
        assert r.status_code == 409 and "already has a remote" in html

    def test_a_form_without_a_network_is_refused_its_name_escaped(self, networks):
        r, html = _post(networks, f"{BASE}/connect", dict(GOOD, list="Nowhere<b>x</b>"))
        assert r.status_code == 404 and "there is no network" in html
        assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html


class TestTheWriteProbe:
    def test_each_check_is_drawn_masked(self, networks, monkeypatch):
        _connected(networks)
        monkeypatch.setattr(R, "verify", lambda name, **kw: {"ok": False, "checks": [
            {"name": "key_scope", "ok": True, "detail": "Hi acct/branch-config!"},
            {"name": "write_probe", "ok": False,
             "detail": "snmp-server community Sup3rS3cretCommunity RO refused"}]})
        _r, html = _post(networks, f"{BASE}/write-probe", {"list": "Branch"})
        assert "The write probe FAILED" in html and "key_scope" in html and "FAILS" in html
        assert "Sup3rS3cretCommunity" not in html

    def test_a_failed_check_is_drawn_with_its_remedy_masked(self, networks, monkeypatch):
        """C934: the write probe's remedy (`fix`) was dropped, so a failed check said what
        failed and never what to do. The checks are `remote.check_write_probe`'s own words for
        a read-only key, and a passing check's stray `fix` is not drawn."""
        _connected(networks)
        monkeypatch.setattr(R, "verify", lambda name, **kw: {"ok": False, "checks": [
            {"name": "key_is_repo_scoped", "ok": True, "detail": "Hi acct/branch-config!",
             "fix": "a remedy nobody needs"},
            {"name": "write_works", "ok": False,
             "detail": "ERROR: The key you are authenticating with has been marked as read only.",
             "fix": "the deploy key is read-only. Enable 'Allow write access' on it in the "
                    "repository's settings. snmp-server community Sup3rS3cretCommunity RO"}]})
        _r, html = _post(networks, f"{BASE}/write-probe", {"list": "Branch"})
        item = re.search(r"<li>[^<]*<span class=\"badge[^>]*>FAILS</span>.*?</li>", html)
        assert item, html
        assert ("<strong>To fix:</strong> the deploy key is read-only. Enable 'Allow write "
                "access' on it") in item.group(0).replace("&#39;", "'")
        assert "a remedy nobody needs" not in html
        assert "Sup3rS3cretCommunity" not in html


class TestPublication:
    def test_it_draws_counts_and_fingerprints_never_a_value(self, networks, scan):
        _connected(networks)
        _r, html = _post(networks, f"{BASE}/publication", {"list": "Branch"})
        assert "A first push to acct/branch-config (main) would publish" in html
        assert f'<td class="mono">{FP}</td>' in html and "r1, r2" in html
        assert "exactly: snmp_community" in html
        assert f'name="shown" value="{FP}"' in html
        assert "secret_hash 3" in html, "a hash is counted, never gated"

    def test_the_wrong_words_are_refused_naming_both(self, networks, scan):
        _connected(networks)
        r, html = _post(networks, f"{BASE}/acknowledge",
                        {"list": "Branch", "typed": "yes", "shown": FP})
        assert r.status_code == 409 and "&#39;yes&#39;" in html and "&#39;snmp_community&#39;" in html
        assert R.load_remote("Branch").get("acknowledged_secrets") is None

    def test_the_right_words_record_what_was_shown(self, networks, scan):
        _connected(networks)
        r, html = _post(networks, f"{BASE}/acknowledge",
                        {"list": "Branch", "typed": "snmp_community", "shown": FP})
        assert r.status_code == 200 and "Acknowledged:" in html, html
        ack = R.load_remote("Branch")["acknowledged_secrets"]
        assert ack["kinds"] == ["snmp_community"] and FP in ack["values"]

    def test_the_card_lists_each_acknowledged_secret_by_fingerprint(self, networks, scan):
        """The acknowledgement stays reviewable (the operator, 2026-10-01): each value by kind,
        fingerprint and the devices it is in, escaped, never the value. Today's Remote card drew
        them; it left at 7.8 (2026-10-17), and the set-up card had drawn the kinds alone. One
        recorded before fingerprints says so rather than reading as nothing acknowledged."""
        _connected(networks)
        _post(networks, f"{BASE}/acknowledge",
              {"list": "Branch", "typed": "snmp_community", "shown": FP})
        R.update_remote("Branch", lambda c: c["acknowledged_secrets"]["values"][FP].__setitem__(
            "devices", ["r1", "<r2>"]))
        _r, card = _get(networks, f"{BASE}?list=Branch")
        acked = card.split("<dt>Acknowledged</dt>", 1)[1].split("</dd>", 1)[0]
        assert "snmp_community" in acked and FP in acked, acked
        assert "r1, &lt;r2&gt;" in acked and "<r2>" not in acked, acked
        R.update_remote("Branch", lambda c: c["acknowledged_secrets"].pop("values"))
        _r, card = _get(networks, f"{BASE}?list=Branch")
        acked = card.split("<dt>Acknowledged</dt>", 1)[1].split("</dd>", 1)[0]
        assert "recorded before secrets had fingerprints" in acked, acked

    def test_a_value_not_shown_is_refused(self, networks, scan):
        _connected(networks)
        r, html = _post(networks, f"{BASE}/acknowledge",
                        {"list": "Branch", "typed": "snmp_community", "shown": "fp-other"})
        assert r.status_code == 409 and "changed after the card was drawn" in html
        assert R.load_remote("Branch").get("acknowledged_secrets") is None


class TestAutoPush:
    def test_it_is_offered_only_after_a_push_and_then_turns_on(self, networks):
        html = _connected(networks)
        assert "Turn on automatic pushing" not in html
        r, html = _post(networks, f"{BASE}/auto-push", {"list": "Branch"})
        assert r.status_code == 409 and "only after a successful push" in html
        R.update_remote("Branch", lambda c: c.__setitem__(
            "last_push", {"at": "2026-10-10T03:00:00Z", "by": "test-person@example.invalid"}))
        _r, card = _get(networks, f"{BASE}?list=Branch")
        assert "Turn on automatic pushing" in card
        r, html = _post(networks, f"{BASE}/auto-push", {"list": "Branch"})
        assert r.status_code == 200 and "Automatic pushing is on" in html
        assert R.load_remote("Branch")["auto_push"] is True


def test_history_s_header_names_uncommitted_paths_never_today_s_git_tab(networks):
    """C637: the header said "see today's Git tab"; it names the paths itself."""
    from modules.nsot import listref

    from routes.v2 import _history_remote

    ref = listref.resolve("Default")
    import os
    import subprocess
    os.makedirs(ref.repo_dir, exist_ok=True)
    subprocess.run(["git", "init", "-q", ref.repo_dir], check=True)
    for n in range(7):
        with open(os.path.join(ref.repo_dir, f"f{n}.txt"), "w") as fh:
            fh.write("x")
    import app as A
    with A.app.test_request_context("/v2/history"):
        got = _history_remote(ref)
    # The expectation by git's own count, independent of the header's code.
    status = subprocess.run(["git", "-C", ref.repo_dir, "status", "--porcelain"],
                            capture_output=True, text=True, check=True).stdout.splitlines()
    assert len(status) >= 7 and got["dirty"] == len(status)
    assert got["dirty_paths"] == [line[3:] for line in status][:5]
    _r, page = _get(networks, "/v2/history")
    assert "today&#39;s Git tab" not in page and "today's Git tab" not in page


# ---------------------------------------------------------------------------
# C1016: a failed Verify draws each failed check's own remedy
# ---------------------------------------------------------------------------

DEFAULT = dict(GOOD, list="Default", ssh_alias="github-default", repo="default-config",
               key_path="~/.ssh/default_deploy")
TARGET = f"{DEFAULT['owner']}/{DEFAULT['repo']}"


def _fake_github(monkeypatch, *, greeting=f"Hi {TARGET}! You've successfully authenticated.",
                 ls_remote=(0, ""), origin="", have_commit=True, ancestor=True, root="",
                 http=None, init=0, commit="c0ffee", push=0):
    """The edges `remote`'s checks reach, as tests/test_nsot_remote.py fakes them: `_run`
    answering each command by what it is (ssh's greeting, ls-remote, the application's own
    origin, git's ancestry, the probe repository's commands), and `urlopen` answering the two
    anonymous endpoints by code (``http``; an exception makes the probe unrunnable). The
    defaults are a remote every check passes."""
    import types
    import urllib.error
    import urllib.request

    def P(stdout="", stderr="", rc=0):
        return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=rc)

    def run(args, **_kw):
        a = list(args)
        if a[0] == "ssh":
            return P(greeting, "", 1)
        sub = a[3] if a[:2] == ["git", "-C"] else a[1]
        if sub == "ls-remote":
            rc, refs = ls_remote
            return P(refs, "" if rc == 0 else "fatal: could not read", rc)
        if sub == "remote":
            return P(origin)
        if sub == "cat-file":
            return P(rc=0 if have_commit else 1)
        if sub == "merge-base":
            return P(rc=0 if ancestor else 1)
        if sub == "rev-list":
            return P(root)
        if sub == "init":
            return P(rc=init)
        if sub == "hash-object":
            return P("4b825dc642cb6eb9a060e54bf8d69288fbee4904\n")
        if sub == "commit-tree":
            return P(commit, "" if commit else "fatal: empty ident name not allowed")
        if sub == "push":
            return P("", "" if push == 0 else "ERROR: The key you are authenticating with has "
                                                  "been marked as read only.", push)
        raise AssertionError(f"an unexpected command: {a}")

    monkeypatch.setattr(R, "_run", run)
    codes = http or {"api": 404, "git": 401}

    def urlopen(request, **_kw):
        url = request.full_url
        code = codes["api" if "api.github.com" in url else "git"]
        if isinstance(code, Exception):
            raise code
        if code == 200:
            return type("R", (), {"status": 200, "__enter__": lambda s: s,
                                  "__exit__": lambda *a: False})()
        raise urllib.error.HTTPError(url, code, "no", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def _failed_with_fixes(card: str) -> dict:
    """{check name: the "To fix:" words drawn under it} from a card's failed checks, parsed
    from the list items, unescaped."""
    from html import unescape

    return {name: unescape(fix).strip() for name, fix in re.findall(
        r"<li>(?:(?!</li>).)*?<code>(\w+)</code>(?:(?!</li>).)*?"
        r"<strong>To fix:</strong> ((?:(?!</li>).)*?)(?:</span>)?\s*</li>", card)}


def _history_verify(n) -> str:
    _r, html = _get(n, "/v2/history/remote")
    m = re.search(r'<div class="hist-remote-said bad" id="remote-last-verify">.*?</div>', html)
    assert m, "History draws no failed Verify"
    return m.group(0)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Every way a read-only check Verify runs can fail, each produced through the real check by
# the fakes above, with the words its remedy must carry (written here, independent of the
# check's code) and how to call the check alone for the whole remedy.
READ_ONLY_FAILURES = {
    "no greeting": (dict(greeting="Permission denied (publickey)."),
                    "key_authenticates", "does not authenticate. Check the key at",
                    lambda c, n: R.check_key_scope(c)),
    "an account-wide key": (dict(greeting="Hi acct! You've successfully authenticated."),
                            "key_is_repo_scoped", "Use a deploy key scoped to acct/default-config",
                            lambda c, n: R.check_key_scope(c)),
    "another repository's key": (dict(greeting="Hi acct/some-other-repo! hello"),
                                 "key_matches_repo", "scoped to acct/some-other-repo",
                                 lambda c, n: R.check_key_scope(c)),
    "an unreadable repository": (dict(ls_remote=(128, "")), "read_works",
                                 "cannot read the repository", lambda c, n: R.check_read(c)),
    "a public repository": (dict(http={"api": 200, "git": 401}), "repository_is_private",
                            "Make it private before pushing", lambda c, n: R.check_private(c)),
    "an unrunnable privacy probe": (dict(http={"api": OSError("no dns"), "git": 401}),
                                    "repository_is_private", "Refusing: an unverified privacy",
                                    lambda c, n: R.check_private(c)),
    "this application's repository": (dict(origin=f"https://github.com/{TARGET}.git"),
                                      "not_the_application_repo", "own source repository",
                                      lambda c, n: R.check_right_repository(c, "Default", n)),
    "an unrelated history": (dict(ls_remote=(0, "deadbeef" * 5 + "\trefs/heads/main\n"),
                                  have_commit=False, ancestor=False, root="cafebabe\n"),
                             "repository_is_empty_or_related", "Pushing would interleave",
                             lambda c, n: R.check_right_repository(c, "Default", n)),
}


class TestAFailedVerifyDrawsItsFix:
    """C1016: a failed Verify drew each check's name and detail and never its remedy, so a
    PUBLIC repository's card showed two HTTP codes and not "Make it private before pushing".
    Through the real routes and templates: POST /remote/verify (History's button), then
    History's remote card as any redraw draws it, from the list's record."""

    def _verify(self, n, monkeypatch, fakes):
        _r, html = _post(n, f"{BASE}/connect", DEFAULT)
        assert "Connected:" in html, html
        _fake_github(monkeypatch, **fakes)
        r = n["client"].post("/remote/verify", json={"list": "Default"})
        assert r.status_code == 200
        return r.get_json()

    @pytest.mark.parametrize("case", sorted(READ_ONLY_FAILURES))
    def test_each_read_only_check_s_failure_draws_its_remedy(self, networks, monkeypatch,
                                                             case):
        fakes, name, words, alone = READ_ONLY_FAILURES[case]
        out = self._verify(networks, monkeypatch, fakes)
        assert [c["name"] for c in out["checks"] if not c["ok"]] == [name], out
        config = R.load_remote("Default")
        expected = alone(config, R.os.path.join(networks["dir"], "lists", "default",
                                                "config_repo")).get("fix") or ""
        assert words in expected, "the check's own remedy carries the words"
        drawn = _failed_with_fixes(_history_verify(networks))
        assert drawn == {name: _norm(expected)}, drawn
        # The button's own words carry it too, before the redraw replaces them.
        js = _failed_words(out)
        assert f"{name}" in js and f"To fix: {expected}" in js

    def test_another_list_s_repository_and_an_unreadable_list_draw_their_remedies(
            self, networks, monkeypatch):
        """not_another_lists_repo's two failures: a list already pushing there, and a list
        whose record cannot be read."""
        assert R.adopt("Branch", ssh_alias="b", owner="acct", repo="default-config")["ok"]
        self._verify(networks, monkeypatch, {})
        drawn = _failed_with_fixes(_history_verify(networks))
        assert list(drawn) == ["not_another_lists_repo"]
        assert "already pushes to acct/default-config. Two networks must not share" in \
            drawn["not_another_lists_repo"]
        (networks["dir"] / "lists" / "branch" / "remote.json").write_text("{not json",
                                                                         encoding="utf-8")
        networks["client"].post("/remote/verify", json={"list": "Default"})
        drawn = _failed_with_fixes(_history_verify(networks))
        assert "Whether it already pushes to acct/default-config cannot be told" in \
            drawn["not_another_lists_repo"]


def _failed_words(out: dict) -> str:
    """History's button's words for Verify's JSON answer, from the shipped script."""
    import dukpy
    from tests.payload_render import shipped

    return dukpy.evaljs("var window = {};\n" + shipped("nmas_history.js")
                        + f"\nwindow.NMAS_HISTORY.remoteOutcome('verify', 200, "
                        + json.dumps(out) + ").words")


WRITE_FAILURES = {
    "no probe repository": (dict(init=1), "check that git runs here"),
    "no probe commit": (dict(commit=""), "a local fault, not a permission one"),
    "a read-only key": (dict(push=1), "Enable 'Allow write access'"),
}


class TestOneDefinitionOfEachRemedy:
    """Each remedy is defined once, where its check decides the failure (`fix` in
    `modules/nsot/remote.py`), and both cards draw that string: the set-up card's write probe
    and History's last Verify."""

    @pytest.mark.parametrize("case", sorted(WRITE_FAILURES))
    def test_both_cards_draw_the_write_probe_s_remedy_from_the_check(self, networks,
                                                                     monkeypatch, case):
        fakes, words = WRITE_FAILURES[case]
        _r, html = _post(networks, f"{BASE}/connect", DEFAULT)
        _fake_github(monkeypatch, **fakes)
        expected = _norm(R.check_write_probe(R.load_remote("Default")).get("fix") or "")
        assert words in expected
        _r, setup = _post(networks, f"{BASE}/write-probe", {"list": "Default"})
        on_setup = _failed_with_fixes(setup)
        on_history = _failed_with_fixes(_history_verify(networks))
        assert on_setup == on_history == {"write_works": expected}, (on_setup, on_history)

    def test_every_failed_check_carries_a_remedy(self):
        """The shape, parsed: every result `remote.py` builds with ``"ok": False`` and a check
        ``"name"`` carries a ``"fix"``, so no failure can reach a card without one."""
        found = _failing_check_results(_source("modules/nsot/remote.py"))
        assert len(found) >= 13, f"the scan found {len(found)}: too few to be the checks"
        missing = [line for line, has_fix in found if not has_fix]
        assert not missing, f"failed checks with no remedy at remote.py lines {missing}"

    def test_the_scan_finds_a_failure_without_a_remedy(self):
        planted = 'def check_x(c):\n    return {"ok": False, "name": "x", "detail": "d"}\n'
        assert _failing_check_results(planted) == [(2, False)]

    def test_no_remedy_is_written_a_second_time(self):
        """Anchored on each remedy's literal words in `remote.py`, parsed and cut at its
        sentence and clause marks: none appears in a template, a script, a route or another
        module, where a second copy would drift."""
        import os

        from tests import source_index

        home = os.path.join(source_index.ROOT, "modules", "nsot", "remote.py")
        phrases = _remedy_phrases(_source(home))
        assert "Make it private before pushing" in phrases, phrases
        assert len(phrases) >= 15, phrases
        others = [p for p in source_index.tracked("templates", suffix=".html")
                  + source_index.tracked("static/js", suffix=".js", recursive=False)
                  + source_index.tracked("routes", suffix=".py", recursive=False)
                  + source_index.tracked("modules", "app.py", suffix=".py")
                  if p != home]
        assert len(others) > 100 and any(p.endswith("_history_remote.html") for p in others)
        twice = {(phrase, path) for path in others for phrase in phrases
                 if phrase in _source(path)}
        assert not twice, twice

    def test_the_phrase_scan_finds_a_planted_copy(self):
        planted = ('def check_x(c):\n    return {"ok": False, "name": "x", '
                   '"fix": f"{c} is public. Make it private before pushing."}\n')
        assert "Make it private before pushing" in _remedy_phrases(planted)


def _source(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _remedy_phrases(source: str) -> set:
    """The literal words of every ``"fix"`` value in *source*, parsed, cut at sentence and
    clause marks, each piece of 20 characters or more."""
    import ast

    phrases = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if not (isinstance(k, ast.Constant) and k.value == "fix"):
                continue
            for part in ast.walk(v):
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    for piece in re.split(r"[.:;?!(),—]", part.value):
                        if len(piece.strip()) >= 20:
                            phrases.add(piece.strip())
    return phrases


def _failing_check_results(source: str) -> list:
    """[(line, carries a fix)] for each dict literal with ``"ok": False`` and a ``"name"``."""
    import ast

    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value: v for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant)}
        ok = keys.get("ok")
        if "name" in keys and isinstance(ok, ast.Constant) and ok.value is False:
            out.append((node.lineno, "fix" in keys))
    return sorted(out)
