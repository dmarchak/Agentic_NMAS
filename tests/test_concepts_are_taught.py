"""Stage 7.0 (4), acceptance criterion 3: the nine concepts, taught at the point of action, on v2.

NSOT_STAGE7_PLAN.md section 4. "Teach at the point of action" is an acceptance criterion, not a
principle: each concept has a named screen, the screen marks its explanation with
``data-concept="<name>"`` (an attribute, because a text search would match the concept's name in
prose), and a test renders the screen against a real state and asserts the marked element is
present, non-empty and not hidden, and that its words are the concept's.

**Every screen here is a v2 page or card (P7-03, 2026-10-15).** Until then the harness drew four
of the nine through today's JavaScript (the onboarding banner, the template editor's badge, the
preview component) and held five PENDING. Today's pages go at cutover, so the harness now asks the
real v2 routes, through the test client, on the labs their own tests build (a real capture, real
intent, real commits and tags, the real NetBox removal dry run against the fake NetBox); a
response must be a v2 route's (`/v2/...`), drawn under the strict policy.

The nine names are read from the plan's own table as well, and must match: a harness and a
document that disagree about what is taught is the same defect as a document asserting what the
code no longer does. It already happened once: the plan's `approval-binds-a-set` described
approval scheme 2, and since P.5 an approval binds the TEMPLATE, never a device set.

**The control** (in the suite, `TestTheCheckCanFail`): the real Overview with its marker taken
out, its marker on an empty element, and its marker on a hidden one, each refused by the same
check every concept runs, naming the concept.
"""

import os
import re
from typing import NamedTuple

import pytest

# Each concept's screen is drawn on the lab its own v2 test builds. Four labs share the fixture
# name `lab`; each is imported under its own name here (pytest registers a fixture by the name
# it is imported as), and the few lines of each test's own setup are repeated below.
from tests.test_approvals_record import lab as approvals_lab  # noqa: F401
from tests.test_device_deploy_v2 import deploy  # noqa: F401
from tests.test_golden_repo import lab as golden_lab  # noqa: F401
from tests.test_intent_ops import lab as intent_lab  # noqa: F401
from tests.test_profile_apply import lab  # noqa: F401 (deploy's lab)
from tests.test_settings_v2 import networks  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(ROOT, "docs", "NSOT_STAGE7_PLAN.md")


class Screen(NamedTuple):
    #: fn(request) -> (the v2 URL asked, the HTML it answered)
    render: object
    where: str
    #: Phrases the marked element says (whitespace-folded, case kept): the concept, not only a
    #: marker. A marker moved onto the wrong sentence fails here.
    says: tuple


def _get(client, url):
    from modules import csp
    r = client.get(url)
    assert r.status_code == 200, (url, r.status_code, r.get_data(as_text=True)[:400])
    assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY, url
    return url, r.get_data(as_text=True)


# ---- the screens -------------------------------------------------------------------------

def _overview(request):
    """The device page's Overview: Committed intent and Golden, each with its source, and the
    card's foot naming which is the record and which the target."""
    d = request.getfixturevalue("deploy")
    return _get(d["client"], "/v2/device/r2/overview")


def _deploy_card(request):
    """The device page's Deploy card (7.3, board 5), on test_device_deploy_v2's lab: r2 holds
    `load-interval 30` its intent lacks (the residue), and the dangerous `shutdown` has its
    reason, so the confirm is offered, bound to the program's hash."""
    d = request.getfixturevalue("deploy")
    return _get(d["client"], "/v2/device/r2/deploy?back=overview&dz::0=the+link+is+being+retired")


def _device_history(request):
    """The device page's History tab: r2's golden commits (its real capture, then the deploy
    lab's edited golden), each a timeline row whose record opens under it."""
    d = request.getfixturevalue("deploy")
    return _get(d["client"], "/v2/device/r2/history")


def _pending_page(request):
    """A pending device's page: r7 onboarded (phase 1, through the manifest's own write) and
    never reached."""
    from modules.nsot import manifest
    d = request.getfixturevalue("deploy")
    manifest.upsert_device(d["repo"], "uid:r7", "r7", "192.0.2.7", platform="cisco_iosxe",
                           pending=True, address_source="static")
    return _get(d["client"], "/v2/device/r7")


def _approve_card(request):
    """Templates › Approve… on test_templates_v2's lab: s1's capture reproduces the template
    once its unmodelled line is acknowledged in its committed intent, so the card offers the
    approval and says what it covers."""
    import app as A
    from modules.nsot import approve_op
    from tests.test_approvals_record import REL
    from tests.test_template_approval import QUANTUM, _ack_doc, _commit_intent, _config

    repo = request.getfixturevalue("approvals_lab")
    mp = request.getfixturevalue("monkeypatch")
    mp.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    caps = {"s1": _config("s1") + QUANTUM}
    mp.setattr("modules.nsot.approve_op._capture", lambda _repo, name: caps.get(name))
    lines = approve_op.check("Lab", REL)["results"][0]["unacknowledged"]
    _commit_intent(repo, "s1", _ack_doc("s1", lines))
    return _get(A.app.test_client(), f"/v2/templates/approve?list=Lab&path={REL}")


def _revert_card(request):
    """The device page's Revert intent (board 11) on test_intent_ops' lab: r2's real config
    seeded as intent, then two edits, A and B, and a rollback block standing on A."""
    from modules import config
    from tests.test_intent_ops import _note

    lab_ = request.getfixturevalue("intent_lab")
    mp = request.getfixturevalue("monkeypatch")
    lab_["applicability"] = "blocking"
    mp.setattr("routes.templatize.note_applicability",
               lambda ln, h, has_intent=None: lab_["applicability"])
    mp.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    device = dict(lab_["device"], username="admin")
    mp.setattr("modules.device.load_saved_devices", lambda path=None: [dict(device)])
    for mod in ("modules.inventory", "modules.inventory.source_config"):
        mp.setattr(mod + ".get_list_data_dir", config.get_list_data_dir)
    _note(lab_, "blocking")
    return _get(lab_["client"], "/v2/device/r2/revert")


def _baselines_tab(request):
    """History › Baselines, from the REAL judgement (`baseline_usability.read`) of a real
    repository whose Save All earned a baseline (test_history_v2's lab), stored as the reader
    stores it."""
    import types

    import app as A
    from modules import reader_job
    from modules.nsot import repo as R
    from modules.readers import baseline_usability
    from tests.test_golden_repo import _seed
    from tests.test_history_v2 import R2

    repo = request.getfixturevalue("golden_lab")
    mp = request.getfixturevalue("monkeypatch")
    _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12", platform="cisco_ios"),
                  R.GoldenItem("s4", R2.replace("hostname r2", "hostname s4"), "203.0.113.24",
                               platform="cisco_ios")],
          source="save_all", actor="test-person@example.invalid")
    value = baseline_usability.read(lists=["Lab"], previous={})
    assert value["lists"]["Lab"].get("baselines"), value
    mp.setattr(reader_job, "read_cached", lambda name: {"doc": {"last_good": {
        "value_at": "2026-10-15T03:00:00Z", "value": value}}} if name == "baseline-usability"
        else {})
    ref = types.SimpleNamespace(name="Lab", repo_dir=repo, data_dir=os.path.dirname(repo),
                                csv_path=os.path.join(os.path.dirname(repo), "devices.csv"))
    mp.setattr("modules.nsot.listref.active", lambda: ref)
    mp.setattr("modules.device.load_saved_devices",
               lambda *a, **k: [{"hostname": "r2"}, {"hostname": "s4"}])
    return _get(A.app.test_client(), "/v2/history?tab=baselines")


class _Inline:
    def __init__(self, target=None, **_k):
        self.target = target

    def start(self):
        self.target()


def _netbox_remove(request):
    """Source of truth › NetBox › Remove…'s preview card, through the REAL removal dry run and
    cascade query against the fake NetBox (NMAS created and tagged r6; a site it recorded
    carries no tag, so it is left alone)."""
    import modules.netbox_client as nbc
    from modules import netbox_guard
    from tests import payload_providers as P

    n = request.getfixturevalue("networks")
    mp = request.getfixturevalue("monkeypatch")
    tmp = request.getfixturevalue("tmp_path")
    for name in ("_CREATED_IDS_FILE", "_MODIFIED_FILE", "_ADOPTED_FILE", "_REMOVALS_FILE"):
        mp.setattr(netbox_guard, name, str(tmp / f"{name.strip('_').lower()}"))
    mp.setattr(netbox_guard, "writes_allowed", lambda: True)
    mp.setattr(nbc, "set_sync_running", lambda *a, **k: None)
    mp.setattr("modules.netbox_jobs.threading.Thread", _Inline)
    mp.setattr("modules.netbox_ops.threading.Thread", _Inline)
    nb = P._netbox_behind(mp)
    tag = [{"slug": netbox_guard.MANAGED_TAG_SLUG, "name": netbox_guard.MANAGED_TAG}]
    dev = nb.seed("dcim/devices", {"name": "r6", "tags": tag})
    site = nb.seed("dcim/sites", {"name": "branch", "slug": "branch", "tags": []})
    netbox_guard.record_created("Branch", "dcim/devices", dev["id"], "r6")
    netbox_guard.record_created("Branch", "dcim/sites", site["id"], "branch")
    r = n["client"].post("/v2/netbox/preview", data={"operation": "remove", "list": "Branch"},
                         headers={"HX-Request": "true"})
    job = re.search(r"/v2/netbox/job/([0-9a-f]{32})", r.get_data(as_text=True)).group(1)
    return _get(n["client"], f"/v2/netbox/job/{job}")


LIVE = {
    "intent-vs-device": Screen(_overview, "the device Overview's foot, under Committed intent "
                               "and Golden", ("what the device runs", "intent is what it should run")),
    "golden-is-a-record": Screen(_device_history, "a golden row of the device's History",
                                 ("a record of what the device ran", "not a target",
                                  "the target is its committed intent")),
    "merge-only": Screen(_deploy_card, "the Deploy card's Left on the device",
                         ("not in its committed intent", "Merge-only leaves each as it is",
                          "Mode B")),
    "confirm-by-hash": Screen(_deploy_card, "the Deploy card's confirm",
                              ("Bound to program", "moves before you confirm, nothing is sent")),
    "approval-binds-the-template": Screen(_approve_card, "Templates › Approve…'s What it covers",
                                          ("The template's text and its", "as they are now",
                                           "revokes the approval")),
    "provenance-limits-remove": Screen(_netbox_remove, "NetBox › Remove…'s What it does not do",
                                       ("limited by provenance", "recorded creating AND",
                                        "did not create")),
    "pending-vs-promoted": Screen(_pending_page, "a pending device's header",
                                  ("not reached yet", "in no inventory")),
    "revert-is-forward": Screen(_revert_card, "Revert intent's What it will not do",
                                ("later intent commit is kept", "takes nothing off",
                                 "Mode B")),
    "baseline-is-earned": Screen(_baselines_tab, "History › Baselines, each baseline's record",
                                 ("Earned: its commit recorded", "It claims: configured",
                                  "does not say the network was working")),
}

#: Concepts whose v2 screen is not built. Only shrinks; empty since P7-03 (2026-10-15).
PENDING = {}
PENDING_CEILING = 0

#: The control's floor: what a marked explanation must carry to count as teaching.
MIN_WORDS = 40
HIDDEN = ("d-none", "display:none", "display: none", " hidden", "x-cloak", "sr-only")


def _element(html: str, name: str):
    """(opening tag, text) of the FIRST element marked `data-concept="name"`, or (None, "")
    when absent. Depth-counted, so a marked element holding nested elements yields all of its
    text."""
    m = re.search(r'<(\w+)\b[^>]*\bdata-concept="%s"[^>]*>' % re.escape(name), html)
    if not m:
        return None, ""
    tag, depth = m.group(1), 1
    for t in re.finditer(r"<(/?)(%s)\b[^>]*>" % tag, html[m.end():]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            inner = html[m.end():m.end() + t.start()]
            return m.group(0), " ".join(re.sub(r"<[^>]+>", " ", inner).split())
    return m.group(0), ""


def taught(html: str, name: str) -> list:
    """What is wrong with *name*'s teaching on this page; empty when it is taught."""
    import html as _h
    tag, text = _element(html, name)
    if not tag:
        return [f"no element is marked data-concept={name!r}"]
    text = _h.unescape(text)
    wrong = []
    if len(text) < MIN_WORDS:
        wrong.append(f"{name!r} is marked on {len(text)} character(s): {text!r}")
    wrong += [f"{name!r} is marked on a hidden element ({h.strip()}): {tag}"
              for h in HIDDEN if h in tag]
    return wrong


def _plan_concepts() -> list:
    text = open(PLAN, encoding="utf-8").read()
    section = text[text.index("## 4. The nine concepts"):text.index("## 5.")]
    return re.findall(r"^\|\s*`([a-z-]+)`\s*\|", section, re.M)


class TestTheNine:
    def test_nine_concepts_live_or_pending(self):
        assert len(LIVE) + len(PENDING) == 9
        assert not set(LIVE) & set(PENDING)

    def test_the_plan_names_the_same_nine(self):
        """Both directions, with the floor the table's size gives."""
        names = _plan_concepts()
        assert len(names) == 9, names
        assert set(names) == set(LIVE) | set(PENDING)

    def test_pending_only_shrinks(self):
        assert len(PENDING) == PENDING_CEILING


class TestEachIsTaughtOnV2:
    @pytest.mark.parametrize("name", sorted(LIVE))
    def test_marked_non_empty_visible_and_saying_it(self, name, request):
        url, html = LIVE[name].render(request)
        assert url.startswith("/v2/"), f"{name}: {url} is not a v2 page"
        wrong = taught(html, name)
        assert wrong == [], f"{LIVE[name].where}: {wrong}"
        text = " ".join(_element(html, name)[1].split())
        import html as _h
        text = _h.unescape(text)
        missing = [w for w in LIVE[name].says if w not in text]
        assert missing == [], f"{LIVE[name].where} does not say {missing}: {text!r}"

    def test_the_approval_card_says_what_it_does_not_cover(self, request):
        """The second half of approval-binds-the-template, in the approval module's own words
        (the operator: without it the newer scheme reads as weaker than the old)."""
        import html as _h
        from modules.nsot import approval
        _url, html = _approve_card(request)
        said = " ".join(_h.unescape(_element(html, "approval-binds-the-template")[1]).split())
        assert approval.DOES_NOT_COVER[:40] in said, said

    def test_the_removal_names_what_it_leaves_alone(self, request):
        """provenance-limits-remove names WHAT is skipped, not only the rule: the site NMAS
        recorded without its tag, with why, and the database's cascade it did not create."""
        import html as _h
        _url, html = _netbox_remove(request)
        text = " ".join(_h.unescape(re.sub(r"<[^>]+>", " ", html)).split())
        assert "Left alone (1)" in text and "branch" in text, text[:2000]


def _marked_names() -> set:
    """Every concept v2 can mark: a marker written in a v2 template (`data-concept="x"`), and
    an explanation the preview-confirm builder puts in a preview's `explain`
    (`"concept": "x"`), which the v2 preview parts (`_preview_parts.html`) mark the same way."""
    from tests.source_index import tracked
    text = "".join(open(p, encoding="utf-8").read()
                   for p in tracked("templates/v2", suffix=".html"))
    names = set(re.findall(r'data-concept="([a-z-]+)"', text))
    builder = open(os.path.join(ROOT, "modules", "preview_confirm.py"), encoding="utf-8").read()
    return names | set(re.findall(r'"concept":\s*"([a-z-]+)"', builder))


class TestPendingHasNoGhosts:
    def test_a_pending_concept_with_a_marker_must_leave(self):
        ghosts = sorted(set(PENDING) & _marked_names())
        assert ghosts == [], f"marked now: move to LIVE with a real-state render: {ghosts}"

    def test_every_live_marker_is_in_v2s_source(self):
        """The floor for the check above: the scan finds a marker in both places it looks."""
        marked = _marked_names()
        assert set(LIVE) <= marked, sorted(set(LIVE) - marked)
        assert "provenance-limits-remove" in marked and "intent-vs-device" in marked


class TestTheCheckCanFail:
    """The control: a planted v2 page missing one concept, or carrying it on nothing, or
    hidden, is refused by the same check, naming the concept."""

    NAME = "intent-vs-device"

    def test_the_real_page_passes(self, request):
        _url, html = _overview(request)
        assert taught(html, self.NAME) == []

    def test_a_page_missing_the_concept_fails(self, request):
        _url, html = _overview(request)
        planted = html.replace(f' data-concept="{self.NAME}"', "")
        assert planted != html, "floor: the real page carried the marker"
        assert taught(planted, self.NAME) == [
            f"no element is marked data-concept={self.NAME!r}"]

    def test_a_marker_on_nothing_fails(self, request):
        _url, html = _overview(request)
        planted = re.sub(r'(<p class="card-foot" data-concept="%s">)[^<]*' % self.NAME,
                         r"\1See the manual.", html)
        assert planted != html
        assert taught(planted, self.NAME) and "character(s)" in taught(planted, self.NAME)[0]

    def test_a_hidden_marker_fails(self, request):
        _url, html = _overview(request)
        planted = html.replace(f'class="card-foot" data-concept="{self.NAME}"',
                               f'class="card-foot" hidden data-concept="{self.NAME}"')
        assert planted != html
        assert any("hidden" in w for w in taught(planted, self.NAME))
