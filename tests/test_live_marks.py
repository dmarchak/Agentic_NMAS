"""A person's Right / Wrong mark survives a live refresh on every page that draws one (C2810's
harness, the operator's requirement: "its harness checks must cover scroll, focus, open
disclosures, input text and Right/Wrong marks on every live page"; the charter's "Human-facing
means human-readable", rule 6), and C2841's one measurement.

The mark control (`templates/v2/_heal_mark.html`, board H artboard C) is drawn under a dry-run
record's History row (`history_sources.heal`, `_timeline.html`): on History and on the device
page's History tab. Needs attention's dry-run row draws none (its action names the record on
History). On test_device_v2's lab (network Lab, r3), with Lab marked lab and in dry run, the
record is a REAL decision: a configuration change from outside Mercury sighted into r3's
incident, settled on its departure and decided by the real decision (`decide.run`, its sources
tests/test_heal_decide.py's `Fake`), so it stands on its would-heal (C2813).

- **The mark kept:** each page, in a real browser, its record opened and scrolled to the
  middle; Right pressed; the page's live keys fired; the mark is recorded (the POST reached the
  app, `decisions.find`) and still drawn as marked, the region never replaced.
- **C2841 (two of the operator's four Right marks never posted):** the record opened and the
  pointer on Right; a later decision on r3 lands and a live refresh merges it in; then the press
  at the place the person aimed. Measured both ways the later decision comes:
  - a later incident of r3 held (W2's and W4's shape before C2813: r8's drift trigger opened a
    second incident): its row arrives above the open record, in the window, and pushes it down;
  - the same incident decided again, held (C2813's standing incident sent back by another
    change): the record's row is a new row (its id is the hash of its newest time and words),
    and its Right is no longer drawn.
"""
import time

import pytest

from tests.test_device_v2 import lab  # noqa: F401 - the fixture
from tests.test_heal_decide import GOLDEN, ROUTE4, Fake, iso
from tests.test_swaps_in_a_browser import READY, SETTLED, served  # noqa: F401

#: C1522: these pages' readers write their stores; each test keeps them in its own folder.
pytestmark = pytest.mark.usefixtures("reader_stores_in_tmp")

NET, HOST = "Lab", "r3"


def _incident():
    from modules.heal import incidents as I
    return next(i for i in I.read(NET)["incidents"]
                if i["state"] in I.OPEN_STATES and i["device"] == HOST)


def _change(at, n):
    """A configuration change from outside Mercury on r3 at *at* (the logs-tail step's trigger)."""
    from modules.heal import incidents as I
    I.sight(NET, HOST, {"kind": "config_change", "key": f"cfg:{n}", "epoch": at, "at": iso(at),
                        "source": "logs-tail", "attribution": {"by": "outside"},
                        "person": {"user": "alice", "words": "the account alice on vty0"},
                        "words": "CONFIG_I"}, now=at)


def _decide(running, at, **fake):
    """Settle r3's watching incident on *running*'s departure and run the real decision."""
    from modules.drift_check import departure, drift_diff
    from modules.heal import decide as DC
    from modules.heal import incidents as I
    I.settle(NET, _incident()["id"], {"state": "persisted", "words": "two reads",
                                      "operands": {"departure": departure(
                                          drift_diff(GOLDEN, running, HOST))}}, at - 5)
    (d,) = DC.run(NET, now=at, sources=Fake(running, **fake))["decided"]
    return d


@pytest.fixture
def marks(lab, tmp_path, monkeypatch):  # noqa: F811
    """Lab marked lab and in dry run, r3's would-heal decided; the mark POSTs counted. The
    network's heal store under this test's folder (`config.list_data_path`, which the lab
    leaves pointing at the shared store), and the installation's own stores too
    (`config.DATA_DIR`): History draws the rows every network shares that name r3 (the
    break-glass exports, reveals, rotations, settings), and the session's held what earlier
    tests wrote, so what these pages drew depended on which tests ran first.

    In place of those, the shape they had, planted: two identical records of r3 (a break-glass
    record exported twice in one second) between the dry-run record and the decision that
    follows it. Rows between the two put the record's next row above it, not after it; two
    identical rows drew one id twice (measured 2026-11-09, 96 files of the gate's browser3
    shard before this file: "7 new, show them" for one new row, and Right drawn twice, the
    first copy hidden)."""
    import app as A
    from modules import breakglass as bg
    from tests.test_heal_policy import confirm, mark
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr("modules.config.DATA_DIR", str(data))
    for target, value in (("modules.restarts.explained_by", lambda d, n, now: None),
                          ("modules.nsot.device_ops.holder", lambda n, d: None),
                          ("modules.change_windows.holding", lambda now=None, given=None: None),
                          ("modules.heal.detect.wake", lambda: None),
                          ("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])):
        monkeypatch.setattr(target, value)
    mark(NET)
    confirm(NET, heal_mode="dry_run")
    now = time.time()
    _change(now - 600, 1)
    d = _decide(GOLDEN + ROUTE4, now - 400)
    assert d["outcome"] == "would_heal", d
    for _ in range(2):
        bg.record_export(str(data), list_name=NET, path="/dev/shm/nmas-breakglass.bg",
                         key_fingerprint="ab12", actor="alex@example.com", at=now - 200,
                         devices=[{"hostname": HOST, "username": "nmas", "password": "x"}])
    posts = []
    view = A.app.view_functions["heal_proposal_v2.mark"]

    def counted(**kw):
        posts.append(kw.get("decision_id"))
        return view(**kw)
    monkeypatch.setitem(A.app.view_functions, "heal_proposal_v2.mark", counted)
    return {"decision": d["decision"], "posts": posts, "now": now}


def _card(decision):
    return f"document.getElementById('heal-mark-{decision}')"


def _open(b, decision):
    """The record's row opened and scrolled to the middle of the window."""
    b.js(f"var c = {_card(decision)}; c.closest('details.tl-row').open = true;"
         " c.scrollIntoView({block: 'center'}); return 1")
    b.wait_for(f"var c = {_card(decision)}; return !!c && c.offsetParent !== null", 10)


def _keys(b):
    """Every live key the page's regions hear."""
    return b.js("var k = {}; document.querySelectorAll('[hx-trigger*=\"nmas:\"]').forEach("
                "function (r) { (r.getAttribute('hx-trigger').match(/nmas:[a-z_]+/g) || [])"
                ".forEach(function (x) { k[x.slice(5)] = 1; }); }); return Object.keys(k)")


def _refresh(b):
    b.js("window.__settled = 0; document.addEventListener('htmx:afterSettle', function () {"
         " window.__settled++; }); return 1")
    for key in _keys(b):
        b.js("htmx.trigger(document.body, 'nmas:' + arguments[0]); return 1", key)
    b.wait_for(f"return window.__settled > 0 && {SETTLED}", 20)
    b.wait_for(f"return {SETTLED}", 20)


def _press_at(b, x, y):
    """A real press (WebDriver's pointer actions) at viewport *x*, *y*, where the person aimed."""
    b._call("POST", f"/session/{b.session}/actions", {"actions": [{
        "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
        "actions": [{"type": "pointerMove", "duration": 0, "x": int(x), "y": int(y),
                     "origin": "viewport"},
                    {"type": "pointerDown", "button": 0}, {"type": "pointerUp", "button": 0}]}]})
    b._call("DELETE", f"/session/{b.session}/actions")


RIGHT = "button[hx-vals*=yes]"
PAGES = ["/v2/history", "/v2/device/r3?tab=history"]


@pytest.mark.parametrize("url", PAGES)
def test_a_right_mark_is_recorded_and_kept_through_a_live_refresh(served, marks, url):  # noqa: F811
    from modules.heal import decisions
    srv, b = served
    did = marks["decision"]
    b.go(srv.url(url))
    b.wait_for(READY + f" && !!{_card(did)}", 20)
    _open(b, did)
    region = b.js(f"var r = {_card(did)}.closest('[hx-trigger*=\"nmas:\"]');"
                  " window.__region = r; return r ? (r.id || r.tagName) : ''")
    assert region, f"{url}: the record is drawn in no live region"
    b.click(f"#heal-mark-{did} {RIGHT}")
    b.wait_for(f"return /Marked right by you/.test({_card(did)}.textContent) && {SETTLED}", 15)
    assert marks["posts"] == [did], f"{url}: the press sent {marks['posts']}"
    assert (decisions.find(NET, did).get("mark") or {}).get("right") is True
    _refresh(b)
    got = b.js(f"var c = {_card(did)}; return {{marked: !!c && /Marked right by/.test("
               "c.textContent), open: !!c && c.closest('details.tl-row').open,"
               " same: document.contains(window.__region),"
               f" drawn: document.querySelectorAll('[id=\"heal-mark-{did}\"]').length}}")
    assert got == {"marked": True, "open": True, "same": True, "drawn": 1}, f"{url}: {got}"
    # And a fresh load draws it as marked, by the person, never as unmarked.
    b.go(srv.url(url))
    b.wait_for(READY + f" && !!{_card(did)}", 20)
    assert b.js(f"return /Marked right by /.test({_card(did)}.textContent)"), url


def _later_held(marks, same_incident):
    """A later decision on r3, held (guard 4: its golden departs from intent): in the same
    incident (C2813's standing incident sent back to watching by another change), or in a later
    incident (before C2813 the first closed at its decision, so the next change opened another)."""
    from modules.heal import incidents as I
    now = time.time()
    if not same_incident:
        I.close(NET, _incident()["id"], "decided (an incident closed at its decision, before "
                                        "C2813)", now=now - 30)
    _change(now - 20, 2)
    d = _decide(GOLDEN + ROUTE4, now - 10, state="departs")
    assert d["outcome"] == "held", d
    return d


def _move_to(b, x, y):
    """The person's pointer moved onto viewport *x*, *y* (aiming), nothing pressed."""
    b._call("POST", f"/session/{b.session}/actions", {"actions": [{
        "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
        "actions": [{"type": "pointerMove", "duration": 0, "x": int(x), "y": int(y),
                     "origin": "viewport"}]}]})


@pytest.mark.parametrize("same_incident", [False, True], ids=["a later incident held",
                                                              "the same incident held"])
@pytest.mark.parametrize("url", PAGES)
def test_c2841_right_pressed_as_a_later_decision_lands_is_recorded(served, marks, url,  # noqa: F811
                                                                   same_incident):
    """The conditions in C2841's row: the dry-run record opened and the pointer on Right; a
    later decision of r3 (held) is recorded and a live refresh merges it in; the press lands
    where the person aimed. It must reach the app and be drawn as marked. Before the fix the
    later incident's row was drawn above the record in the window, Right moved 38 px down and
    the press landed on the record's step log; with the same incident, Right was not drawn at
    all once the incident's newest outcome was held (measured 2026-11-09, both pages).

    With rows between the record and the later decision (`marks`' two identical break-glass
    records): the incident's next row was drawn above the record, hidden, holding the first
    `#heal-mark-…` of the page, so Right's answer went there; and the second identical record
    was drawn again as new on every refresh, "2 new" for one (measured 2026-11-09)."""
    from modules.heal import decisions
    srv, b = served
    did = marks["decision"]
    b.go(srv.url(url))
    b.wait_for(READY + f" && !!{_card(did)}", 20)
    _open(b, did)
    aim = b.js(f"var r = {_card(did)}.querySelector('{RIGHT}').getBoundingClientRect();"
               " return {x: r.left + r.width / 2, y: r.top + r.height / 2}")
    _move_to(b, aim["x"], aim["y"])
    _later_held(marks, same_incident)
    _refresh(b)
    moved = b.js(f"var c = {_card(did)}; var r = c ? c.querySelector('{RIGHT}') : null;"
                 " if (!r) return null; var box = r.getBoundingClientRect();"
                 " return Math.abs(box.top + box.height / 2 - arguments[0])", aim["y"])
    assert moved is not None and moved < 1, f"{url}: Right is gone or moved: {moved}"
    _press_at(b, aim["x"], aim["y"])
    b.wait_for(f"return /Marked right by you/.test(({_card(did)} || {{}}).textContent || '')"
               f" && {SETTLED}", 15)
    assert marks["posts"] == [did], f"{url}: the press sent {marks['posts']}"
    assert (decisions.find(NET, did).get("mark") or {}).get("right") is True
    # The later decision's row was held, not lost: counted, and drawn when asked.
    if not same_incident:
        said = b.js("return (document.querySelector('.live-new button') || {}).textContent || ''")
        assert said == "1 new, show them", f"{url}: {said!r}"
    # Drawn again from the server, the record still carries its mark.
    b.go(srv.url(url))
    b.wait_for(READY + f" && !!{_card(did)}", 20)
    assert b.js(f"return /Marked right by /.test({_card(did)}.textContent)"), url


def test_an_incident_decided_again_still_draws_its_dry_run_s_mark(marks):
    """C2841's second half, without a browser: History's row for an incident whose newest
    decision is held after its dry run still carries the dry run's Right / Wrong (Needs
    attention still asks for it)."""
    import types

    from modules import history_sources as HS
    _later_held(marks, same_incident=True)
    ctx = {"ref": types.SimpleNamespace(name=NET), "device": "", "limit": 50, "since": None,
           "until": None, "members": None, "inventory": {HOST}}
    (e,) = [x for x in HS.heal(ctx)["events"]]
    assert e["outcome"] == "held"
    assert e["heal_mark"] == {"list": NET, "decision": marks["decision"], "unreadable": "",
                              "mark": None}, e.get("heal_mark")
