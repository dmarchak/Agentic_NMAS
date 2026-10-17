"""C148 (7.3's first item): seed intent, the path from onboarded to deployable.

Onboarding commits a bootstrap-shaped intent, a deploy needs full intent, and
extract, review, commit had no screen, its commit refusing anything without a
verified person. So no onboarded device could be deployed to from the
interface: the tool did it once (r6), through the commit route before P.3
gated it. Seed intent is one operation: previewed from the COMMITTED golden,
confirmed by a hash of the document and the golden, parsed again at apply,
committed as exactly the seeded files by the verified person.

The fixture is r2's REAL configuration as its golden, with the committed
intent onboarding writes (probe-r1a's measured shape).

The preview and result models are read through the v2 device page's Seed intent… card
(`/v2/device/<name>/seed` and its confirm; `tests/v2_card_models.py`): today's JSON routes,
POST /templatize/seed/preview and /apply, and their client, nmas_seed.js, left at 7.8
(2026-10-17, P7-24). v2 seeds one device per card; what the card draws is
tests/test_device_seed_v2.py's.
"""

import os
import subprocess

import pytest

from tests.conftest import TEST_PERSON
from tests.test_intent_match import R2
from tests.v2_card_models import spying, the_one

LIST = "Lab"
#: A real IOS line the parser does not model (measured: it lands in `unmodeled`).
UNMODELLED = "alias exec shr show running-config"
BOOTSTRAP = {"bootstrap": {"source": "static"}, "hostname": "r2",
             "logging": {}, "secret_refs": ["user_admin_password"], "unmodeled": []}


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def lab(tmp_path, monkeypatch):
    return _on_v2(build_seed_lab(monkeypatch, tmp_path), monkeypatch)


def _on_v2(lab, monkeypatch):
    """*lab* served on the v2 device page: test_device_seed_v2's own setting-up (its network
    known, r2 its inventory)."""
    from tests.test_device_seed_v2 import _serve
    return _serve(lab, monkeypatch)


def build_seed_lab(monkeypatch, tmp_path, intent=None, unmodelled=""):
    """The real app, list 'Lab' holding r2: its real config as the committed
    golden, and ONLY onboarding's bootstrap as its committed intent (or
    *intent*). *unmodelled* is a line added to the golden that the parser does
    not model, so a seed the template cannot reproduce is reachable. Also the v2 seed card's
    lab (tests/test_device_seed_v2.py) and others'."""
    import yaml

    import app as A
    from modules.nsot import templates_repo
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars

    list_dir = tmp_path / "lab"
    repo = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: LIST)
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost"}.get(key, default))
    captured = open(R2, encoding="utf-8").read()
    if unmodelled:
        captured = captured.replace("\nend", f"\n{unmodelled}\nend", 1)
    templates_repo.seed_templates(repo)
    save_golden(LIST, [GoldenItem("r2", captured, "203.0.113.12", platform="cisco_iosxe")],
                source="onboarding", actor="t", allow_new=True, baseline=False)
    with open(os.path.join(repo, "host_vars", "r2.yml"), "w", encoding="utf-8") as fh:
        fh.write(yaml.safe_dump(intent or BOOTSTRAP, sort_keys=True))
    assert save_host_vars(LIST, ["r2"], actor="t", source="onboarding")["ok"]
    device = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
              "platform": "cisco_iosxe"}
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(device)])
    return {"client": A.app.test_client(), "repo": repo, "captured": captured,
            "device": device}


def _preview(lab, device="r2"):
    """``{"preview": <model>}``: the preview model the v2 Seed card is drawn from
    (`device_actions.seed_card`'s third argument, masked), through GET
    /v2/device/<name>/seed; the card's HTML is kept as ``lab["preview_html"]``."""
    from modules import device_actions

    with spying(device_actions, "seed_card") as calls:
        r = lab["client"].get(f"/v2/device/{device}/seed")
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    lab["preview_html"] = r.get_data(as_text=True)
    args, _kw = the_one(calls, "seed_card")
    return {"preview": args[2]}


def _target(d, name="r2"):
    return next(t for t in d["preview"]["what"]["targets"] if t["name"] == name)


def _apply(lab, confirmations):
    """``(status, {"result": <model>})``: v2's confirm, POST /v2/device/<name>/seed/confirm,
    for the one device in *confirmations*, carrying its list; the model is the one the result
    card is drawn from (`device_actions.seed_result_card`'s third argument, masked), and the
    card's HTML is kept as ``lab["result_html"]``."""
    from modules import device_actions

    ((device, h),) = confirmations.items()
    with spying(device_actions, "seed_result_card") as calls:
        r = lab["client"].post(f"/v2/device/{device}/seed/confirm",
                               data={"list": LIST, "hash": h})
    lab["result_html"] = r.get_data(as_text=True)
    args, _kw = the_one(calls, "seed_result_card")
    return r.status_code, {"result": args[2]}


def _secret_values():
    """r2's real secret values, from the parser (independent of the route)."""
    from modules.nsot.parsers import get_parser
    parsed = get_parser("cisco_iosxe").parse(open(R2, encoding="utf-8").read())
    return [v for v in (parsed.get("secrets") or {}).values() if len(v) >= 4]


class TestThePreview:
    def test_it_shows_the_document_against_the_bootstrap_and_every_gate(self, lab):
        d = _preview(lab)
        t = _target(d)
        assert t["state"] == "seedable" and t["selectable"] and t["select_data"]["hash"]
        assert t["select_data"]["list"] == LIST, "the list rides to the apply"
        gates = {g["name"]: g["state"] for g in d["preview"]["targets"][0]["gates"]}
        assert gates == {"committed golden": "pass", "no full intent to replace": "pass",
                         "no other operation holds this device": "at_apply",
                         "golden unchanged since this preview": "at_apply"}
        ops = {o["name"]: o["value"] for o in d["preview"]["targets"][0]["operands"]}
        assert ops["committed intent now"] == "only the bootstrap onboarding wrote"
        assert ops["from golden"] == _git(lab["repo"], "log", "-1", "--format=%H",
                                          "--", "golden")[:12]
        html = lab["preview_html"]
        committed = html[html.index("<h3>What will be committed"):html.index("<h3>Reproduced")]
        assert "interfaces:" in committed and '<span class="op-del">-bootstrap:' in committed
        assert "Nothing is sent to any device" in html[html.index("What it will not do"):]

    def test_it_writes_nothing(self, lab):
        head, status = _git(lab["repo"], "rev-parse", "HEAD"), _git(lab["repo"], "status",
                                                                     "--porcelain")
        _preview(lab)
        assert _git(lab["repo"], "rev-parse", "HEAD") == head
        assert _git(lab["repo"], "status", "--porcelain") == status

    def test_no_secret_value_leaves(self, lab):
        import json

        values = _secret_values()
        assert values, "the floor: r2's real config carries secrets"
        d = _preview(lab)
        text = lab["preview_html"] + json.dumps(d)
        assert not [v for v in values if v in text]

    def test_a_device_with_full_intent_is_shown_and_not_selectable(self, lab):
        code, out = _apply(lab, {"r2": _target(_preview(lab))["select_data"]["hash"]})
        assert code == 200 and out["result"]["level"] in ("success", "partial")
        t = _target(_preview(lab))
        assert t["state"] == "has_intent" and not t["selectable"]
        assert "edit it instead" in t["why_not"]

    # test_no_devices_names_what_it_left_out_when_everything_has_intent left with POST
    # /templatize/seed/preview (P7-24): its form with no devices named (every device of the
    # list without full intent) was the route's own, and no page sent it (nmas_seed.js's
    # previewSeed had no caller once today's device page left, P7-22). v2 seeds one device per
    # card; a device with full intent is not offered, said above.

    def test_a_device_with_no_golden_says_capture_it_first(self, lab, monkeypatch):
        other = {"hostname": "r9", "ip": "203.0.113.19", "platform": "cisco_iosxe"}
        monkeypatch.setattr("modules.nsot.restore._devices_of",
                            lambda ln: [dict(lab["device"]), other])
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path=None: [dict(lab["device"], username="admin"),
                                               dict(other, username="admin")])
        t = _target(_preview(lab, "r9"), "r9")
        assert t["state"] == "unseedable" and not t["selectable"]
        assert "capture it first" in t["why_not"]


class TestTheApply:
    def test_it_commits_the_previewed_document_as_the_person(self, lab):
        from modules.nsot import hostvars

        d = _preview(lab)
        golden_sha = _git(lab["repo"], "log", "-1", "--format=%H", "--", "golden")[:12]
        before = _git(lab["repo"], "rev-parse", "HEAD")
        code, out = _apply(lab, {"r2": _target(d)["select_data"]["hash"]})
        assert code == 200 and out["result"]["level"] in ("success", "partial"), out
        assert _git(lab["repo"], "diff", "--name-only", before, "HEAD").split() == \
            ["host_vars/r2.yml"]
        msg = _git(lab["repo"], "log", "-1", "--format=%B")
        assert "Source: seed" in msg and f"Seeded-From: r2@{golden_sha}" in msg
        assert f"Actor: {TEST_PERSON}" in msg and "Actor-Verified: access" in msg
        text, _ = hostvars.committed_at_head(lab["repo"], "r2")
        doc = hostvars.from_yaml(text)
        assert not hostvars.is_bootstrap_only(doc) and doc["interfaces"]
        # What was committed is the document the preview drew, line for line:
        # its added and context lines (a bootstrap line kept, `hostname: r2`,
        # is context, not an addition).
        assert [l[1:] for l in d["preview"]["targets"][0]["program"]["lines"]
                if l[:1] in ("+", " ")] == text.splitlines()

    def test_the_secrets_move_into_the_credential_store(self, lab):
        from modules.credentials import get_template_secret, template_secret_key
        from modules.nsot.parsers import get_parser

        refs = sorted(get_parser("cisco_iosxe").parse(lab["captured"]).get("secrets") or {})
        assert refs, "the floor: r2 has secrets"
        _apply(lab, {"r2": _target(_preview(lab))["select_data"]["hash"]})
        assert all(get_template_secret(template_secret_key(LIST, "r2", r)) for r in refs)

    def test_the_device_is_then_planned_toward_its_intent_not_refused(self, lab, monkeypatch):
        """The loop's middle: before the seed the plan refuses with the
        bootstrap reason; after it, that refusal is gone."""
        import routes.deploy as rd
        from modules import device
        from modules.nsot import approval
        from modules.nsot.hostvars import BOOTSTRAP_ONLY_REASON

        monkeypatch.setattr(device, "load_saved_devices", lambda p: [dict(lab["device"])])
        monkeypatch.setattr(device, "get_current_device_list", lambda: (LIST, "x.csv"))
        monkeypatch.setattr(approval, "is_approved", lambda repo, t: True)
        (before, _c, _d), _err = rd._artifact_for(LIST, "r2")
        assert BOOTSTRAP_ONLY_REASON in before.blocking_reasons
        _apply(lab, {"r2": _target(_preview(lab))["select_data"]["hash"]})
        (after, _c, _d), err = rd._artifact_for(LIST, "r2")
        assert err == "" and not after.bootstrap
        assert BOOTSTRAP_ONLY_REASON not in after.blocking_reasons, after.blocking_reasons

    def test_a_golden_that_moved_is_refused_and_nothing_commits(self, lab):
        from modules.nsot.repo import GoldenItem, save_golden

        h = _target(_preview(lab))["select_data"]["hash"]
        save_golden(LIST, [GoldenItem("r2", lab["captured"].replace(
            "hostname r2", "hostname r2\nbanner motd ^moved^", 1), "203.0.113.12",
            platform="cisco_iosxe")], source="capture", actor="t", allow_new=False,
            baseline=False)
        head = _git(lab["repo"], "rev-parse", "HEAD")
        code, out = _apply(lab, {"r2": h})
        target = out["result"]["targets"][0]
        assert target["outcome"] == "moved" and h in target["reason"]
        assert _git(lab["repo"], "rev-parse", "HEAD") == head
        assert out["result"]["level"] == "failed"

    def test_intent_committed_after_the_preview_is_never_replaced(self, lab):
        """The seed hash covers the document and the golden, and neither moves
        when somebody commits intent in between: only the apply's own look at
        the committed intent stops the seed from overwriting it."""
        from modules.nsot.repo import save_host_vars

        h = _target(_preview(lab))["select_data"]["hash"]
        path = os.path.join(lab["repo"], "host_vars", "r2.yml")
        # The parser's whole document: an intent the templates cannot render is refused at
        # commit (C725), and a hand-typed three-key one does not render.
        from modules.nsot.hostvars import to_yaml
        from modules.nsot.parsers import get_parser
        full = to_yaml(get_parser("cisco_iosxe").parse("hostname r2\n"))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(full)
        assert save_host_vars(LIST, ["r2"], actor="t", paths=["host_vars/r2.yml"])["ok"]
        head = _git(lab["repo"], "rev-parse", "HEAD")
        _code, out = _apply(lab, {"r2": h})
        target = out["result"]["targets"][0]
        assert target["outcome"] == "refused" and "full committed intent now" in target["reason"]
        assert _git(lab["repo"], "rev-parse", "HEAD") == head
        assert open(path, encoding="utf-8").read() == full

    def test_a_held_device_is_refused_by_the_lock(self, lab):
        """Held from ANOTHER thread: the lock is re-entrant for its holder."""
        import threading

        from modules.nsot import device_ops

        h = _target(_preview(lab))["select_data"]["hash"]
        taken, done = threading.Event(), threading.Event()

        def hold():
            held, _ = device_ops.acquire_many(LIST, ["r2"], "deploy", "someone@example.com")
            taken.set()
            done.wait(10)
            device_ops.release_many(LIST, held)

        t = threading.Thread(target=hold)
        t.start()
        try:
            assert taken.wait(10)
            _code, out = _apply(lab, {"r2": h})
        finally:
            done.set()
            t.join(10)
        target = out["result"]["targets"][0]
        assert target["outcome"] == "busy" and "someone@example.com" in target["reason"]

    # test_no_list_named_commits_nothing (POST /templatize/seed/apply with no list, 400) left
    # with the route (P7-24): v2's confirm refuses a confirm without its list or hash, committing
    # nothing, in tests/test_device_seed_v2.py (TestTheConfirm's
    # test_a_confirm_without_its_list_or_hash_is_refused).

    def test_a_failed_commit_puts_the_file_back_and_says_so(self, lab, monkeypatch):
        import modules.nsot.repo as repo_mod

        on_disk = os.path.join(lab["repo"], "host_vars", "r2.yml")
        before = open(on_disk, encoding="utf-8").read()
        h = _target(_preview(lab))["select_data"]["hash"]
        monkeypatch.setattr(repo_mod, "save_host_vars",
                            lambda *a, **k: {"ok": False, "error": "commit failed: planted"})
        _code, out = _apply(lab, {"r2": h})
        assert out["result"]["targets"][0]["outcome"] == "failed"
        assert "planted" in out["result"]["targets"][0]["reason"]
        assert out["result"]["level"] == "failed"
        assert open(on_disk, encoding="utf-8").read() == before
        assert _git(lab["repo"], "status", "--porcelain", "--", "host_vars") == ""


class TestWhatTheTemplateDoesNotModel:
    """An unmodelled line round-trips verbatim (100%) and still blocks a
    deploy until acknowledged, so the seed says so and still seeds."""

    @pytest.fixture
    def partial(self, tmp_path, monkeypatch):
        return _on_v2(build_seed_lab(monkeypatch, tmp_path, unmodelled=UNMODELLED),
                      monkeypatch)

    def test_the_preview_names_the_line_and_stays_selectable(self, partial):
        d = _preview(partial)
        assert _target(d)["selectable"]
        item = next(i for i in d["preview"]["what_not"]["items"]
                    if i["kind"] == "not_reproduced")
        assert f"unmodelled: {UNMODELLED}" in item["lines"]
        assert "does not fully model" in item["text"] and "unmodeled_ack" in item["text"]

    def test_the_result_is_partial_and_names_it(self, partial):
        _code, out = _apply(partial, {"r2": _target(_preview(partial))["select_data"]["hash"]})
        r = out["result"]
        assert r["level"] == "partial" and r["targets"][0]["outcome"] == "seeded"
        assert UNMODELLED in r["targets"][0]["checks"]["issues"]
        assert any(i["kind"] == "not_reproduced" for i in r["did_not"]["items"])

    def test_a_fully_modelled_device_is_success(self, lab):
        _code, out = _apply(lab, {"r2": _target(_preview(lab))["select_data"]["hash"]})
        assert out["result"]["level"] == "success"


class TestOnlyTheSeededFileIsCommitted:
    """C175: `save_host_vars` stages the whole `host_vars` tree by default, so
    another device's uncommitted edit rides along under this commit's name.
    The seed stages its own files."""

    def _plant(self, lab):
        from modules.nsot.repo import save_host_vars

        other = os.path.join(lab["repo"], "host_vars", "s1.yml")
        with open(other, "w", encoding="utf-8") as fh:
            fh.write("hostname: s1\ninterfaces: []\n")
        assert save_host_vars(LIST, ["s1"], actor="t", paths=["host_vars/s1.yml"])["ok"]
        with open(other, "a", encoding="utf-8") as fh:
            fh.write("description: somebody's unreviewed edit\n")

    def test_another_devices_uncommitted_edit_stays_uncommitted(self, lab):
        self._plant(lab)
        before = _git(lab["repo"], "rev-parse", "HEAD")
        _apply(lab, {"r2": _target(_preview(lab))["select_data"]["hash"]})
        assert _git(lab["repo"], "diff", "--name-only", before, "HEAD").split() == \
            ["host_vars/r2.yml"]
        assert "host_vars/s1.yml" in _git(lab["repo"], "status", "--porcelain")

    def test_the_fixture_can_exhibit_the_case(self, lab):
        """The control: staging the TREE (what every writer did before C175's
        fix) carries the planted edit, so the tests of the fix are not passing
        on a fixture that could not show it."""
        self._plant(lab)
        before = _git(lab["repo"], "rev-parse", "HEAD")
        _git(lab["repo"], "add", "-A", "host_vars")
        _git(lab["repo"], "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q",
             "-m", "a tree-staging commit")
        assert "host_vars/s1.yml" in _git(lab["repo"], "diff", "--name-only", before,
                                         "HEAD").split()


class TestTheResultAndTheScreen:
    def test_the_result_names_the_commit_and_what_the_template_misses(self, lab):
        _code, out = _apply(lab, {"r2": _target(_preview(lab))["select_data"]["hash"]})
        commit = _git(lab["repo"], "rev-parse", "HEAD")
        html = lab["result_html"]
        assert commit[:12] in html[html.index("<h3>Recorded"):] and "Source: seed" in html
        t = out["result"]["targets"][0]
        assert t["checks"]["ran"] and t["checks"]["statements"][0].startswith("template: ")

    def test_the_device_page_offers_it(self, lab):
        """v2's device page's Actions menu (today's device page's Seed intent button until it
        left at 7.8, P7-22)."""
        menu = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "templates", "v2", "_actions_menu.html"), encoding="utf-8").read()
        assert "('Seed intent…', 'seed', 'seeding')" in menu

    def test_the_old_routes_are_gone(self, lab):
        """Phase 3's four, and today's two seed routes (7.8, 2026-10-17, P7-24)."""
        c = lab["client"]
        for method, url in (("post", "/templatize/extract/r2"), ("post", "/templatize/commit/r2"),
                            ("get", "/templatize/staged"), ("get", "/templatize/rendered/r2"),
                            ("post", "/templatize/seed/preview"),
                            ("post", "/templatize/seed/apply")):
            assert getattr(c, method)(url, json={"list_name": LIST}).status_code == 404, url
