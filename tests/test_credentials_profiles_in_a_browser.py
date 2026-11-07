"""Credentials › Profiles in a real browser, with the real stylesheet, on the real page (the
operator's walk, 2026-11-07).

**The read-only account's form** (board H's artboard N; H28): each label sits by its own field
("'Account name' beside the heading, 'Password' beside the field that holds the name, inviting a
password typed into the visible name field"), at 1280 and at a phone's column:
- every label's `for` names a field of the form, and every visible field has one label;
- each field is beside its label (on the label's line, to its right) or under it (below it,
  starting within its column), and no other label is nearer to it;
- a planted cell before the first label (the shape of the defect: a heading in the label column)
  is found by the same check, so a passing check is not a check that cannot fail.

**Credential profiles' table:** its "Gives its login to" column holds its words a few to a
line at 1280, never one word a line (C2610's class: a words column squeezed by its neighbours).
"""

import pytest

from tests.test_read_only_account import DEPLOY_PW, RO_PW

#: For each label of the form: its words, its `for`, whether that names a field of the form, and
#: the label's and the field's rectangles; then whether each is beside or under its own, and the
#: label nearest each field. One script, so the check and the planted case measure alike.
MEASURE = """
var form = document.querySelector('#cred-read form');
if (!form) { return null; }
var labels = Array.prototype.slice.call(form.querySelectorAll('label'));
var fields = Array.prototype.slice.call(
  form.querySelectorAll('input:not([type=hidden]), select, textarea'));
function box(el) { var r = el.getBoundingClientRect();
  return {l: r.left, r: r.right, t: r.top, b: r.bottom, cx: (r.left + r.right) / 2,
          cy: (r.top + r.bottom) / 2}; }
function placed(lb, fb) {
  var sameLine = fb.t < lb.b && fb.b > lb.t;
  if (sameLine && fb.l >= lb.r - 1) { return 'beside'; }
  if (fb.t >= lb.b - 1 && Math.abs(fb.l - lb.l) <= 24) { return 'under'; }
  return 'neither'; }
function gap(lb, fb) { var dx = Math.max(0, fb.l - lb.r, lb.l - fb.r);
  var dy = Math.max(0, fb.t - lb.b, lb.t - fb.b); return Math.sqrt(dx * dx + dy * dy); }
var out = {labels: [], fields: []};
labels.forEach(function (lab) {
  var f = lab.htmlFor ? document.getElementById(lab.htmlFor) : null;
  var row = {words: lab.textContent.trim().slice(0, 40), for: lab.htmlFor || '',
             inForm: !!(f && form.contains(f) && fields.indexOf(f) >= 0), placed: ''};
  if (row.inForm) { row.placed = placed(box(lab), box(f)); }
  out.labels.push(row);
});
fields.forEach(function (f) {
  var own = labels.filter(function (l) { return l.htmlFor === f.id; });
  var fb = box(f), nearest = '', best = 1e9;
  labels.forEach(function (l) { var d = gap(box(l), fb);
    if (d < best - 0.5) { best = d; nearest = l.htmlFor; } });
  out.fields.push({name: f.name, id: f.id, labels: own.length, nearest: nearest});
});
return out;
"""


def _wrong(got: dict) -> list:
    """Each way the form's labels and fields are not paired, in words; empty when every label
    sits by its own field."""
    out = []
    for lab in got["labels"]:
        if not lab["inForm"]:
            out.append(f"label {lab['words']!r}: its for={lab['for']!r} names no field of the form")
        elif lab["placed"] == "neither":
            out.append(f"label {lab['words']!r}: its field #{lab['for']} is neither beside nor "
                       "under it")
    for f in got["fields"]:
        if f["labels"] != 1:
            out.append(f"field {f['name']!r}: {f['labels']} labels name it, not one")
        elif f["nearest"] != f["id"]:
            out.append(f"field {f['name']!r}: the label nearest it is #{f['nearest']}'s, not its "
                       "own")
    return out


@pytest.fixture
def page(tmp_path, monkeypatch):
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules import credentials
    from tests.test_sdn_connections import make_networks

    make_networks(tmp_path, monkeypatch)
    credentials.save_profile("default", "admin", DEPLOY_PW, "")
    credentials.save_profile("role:router", "netops", "Deploy-Pass-7720", "")
    credentials.set_read_account("role:router", "mercury-ro", RO_PW,
                                 actor="operator@example.com", verified="access")
    import app as A
    with browser.Served(A.app) as served:
        yield served


def _open(b, served, width, profile):
    """The page at *width*, the form opened on *profile*'s row by its own control."""
    b._call("POST", f"/session/{b.session}/window/rect", {"width": max(width, 500),
                                                            "height": 1000})
    b.go(served.url("/v2/credentials/profiles?list=Default"))
    b.wait_for("return !!document.querySelector('#cred-read')", 15)
    if width < 480:
        # Firefox's narrowest window is wider than a phone: the page held to its column, as
        # tests/test_board_shots.py holds it (the media queries are the same below 640).
        b.js(f"document.documentElement.style.maxWidth = '{width}px'; return 1")
    b.js(f"document.querySelector('[data-read-account=\"{profile}\"] a.btn').click(); return 1")
    b.wait_for("return !!document.querySelector('#cred-read input[name=password]')", 15)


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("profile,fields", [("default", ["username", "password"]),
                                            ("role:router", ["password"])])
def test_each_label_sits_by_its_own_field(page, width, profile, fields):
    """Set (a name and a password) on default, Replace (a password, the name kept) on
    role:router."""
    from tests import browser
    with browser.Browser() as b:
        _open(b, page, width, profile)
        got = b.js(MEASURE)
    assert got is not None, "the form did not open"
    assert [f["name"] for f in got["fields"]] == fields
    assert len(got["labels"]) == len(fields), got["labels"]
    assert _wrong(got) == [], got


def test_the_check_finds_a_cell_planted_before_the_first_label(page):
    """The defect's shape: something taking the label column before the first label shifts
    every label beside the next pair's field. The same measure finds it."""
    from tests import browser
    with browser.Browser() as b:
        _open(b, page, 1280, "default")
        b.js("var s = document.createElement('span'); s.textContent = 'planted';"
             "var f = document.querySelector('#cred-read form');"
             "f.insertBefore(s, f.querySelector('label')); return 1")
        got = b.js(MEASURE)
    assert _wrong(got), got


#: Each "Gives its login to" cell of Credential profiles' table: its words, and the lines they
#: are drawn on (the text's line boxes, grouped by their top).
COVERS = """
var table = document.querySelector('#cred-profiles table');
if (!table) { return null; }
var heads = Array.prototype.map.call(table.querySelectorAll('thead th'),
                                     function (th) { return th.textContent.trim(); });
var col = heads.indexOf('Gives its login to');
var out = {col: col, cells: []};
table.querySelectorAll('tbody tr').forEach(function (tr) {
  var td = tr.children[col];
  var range = document.createRange(); range.selectNodeContents(td);
  var tops = {};
  Array.prototype.forEach.call(range.getClientRects(), function (r) {
    if (r.width > 0) { tops[Math.round(r.top)] = 1; } });
  out.cells.push({words: td.textContent.trim().split(/\\s+/).length,
                  lines: Object.keys(tops).length, width: td.getBoundingClientRect().width,
                  text: td.textContent.trim().slice(0, 60)});
});
return out;
"""


def test_gives_its_login_to_holds_its_words_a_few_to_a_line_at_1280(page):
    from tests import browser
    with browser.Browser() as b:
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
        b.go(page.url("/v2/credentials/profiles?list=Default"))
        b.wait_for("return !!document.querySelector('#cred-profiles table')", 15)
        # The region as an action redraws it in place: Rotation policy… pressed on default's
        # row opens its form under the table, which is drawn again by the swap.
        b.js("document.querySelector('#cred-profiles a[href*=\"policy\"][href*=\"default\"]')"
             ".click(); return 1")
        b.wait_for("return !!document.querySelector('#cred-profiles #rp-state')", 15)
        # Its neighbours at their longest, as a lab's draw them: a rotation policy on, naming
        # its devices, its scope, what is due and when next, and a long account name.
        b.js("document.querySelectorAll('#cred-profiles td[data-rotation-policy]').forEach("
             "function (td) { td.querySelector('.small').textContent = ' · 11 devices (9 "
             "outside its scope), 11 due, next 2026-11-08T02:00:00Z, every 30 days between "
             "00:00 and 24:00 UTC, at most every due device'; });"
             "document.querySelectorAll('#cred-profiles tbody td.mono').forEach("
             "function (td) { td.textContent = 'automation-service-account'; }); return 1")
        got = b.js(COVERS)
        opened = b.js("return document.querySelector('#cp-pol-h').textContent")
    assert opened == "Rotation policy for default", opened
    assert got and got["col"] == 1 and len(got["cells"]) == 2, got
    for cell in got["cells"]:
        assert cell["words"] >= 4, ("a cell of a few words, so one word a line would show", cell)
        assert cell["lines"] * 3 <= cell["words"] + 2, ("three words or so a line", got)
