"""Every v2 screen is in the signed-off registry (tests/signed_off_screens.py; the operator,
2026-10-02: "no new screen or tab without a mockup and my sign-off"). The population is
the code's own: every template under `templates/v2/` that extends the frame, and every tab
in `routes/device_v2.TABS`. Exact both ways, with floors, and the UNSIGNED list only
shrinks. Its control: a planted page template is found.
"""

import os
import re

from tests import signed_off_screens as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(ROOT, "templates", "v2")
EXTENDS = re.compile(r'^\{%-?\s*extends\s+"v2/base\.html"', re.M)


def pages(folder=V2):
    out = set()
    for name in sorted(os.listdir(folder)):
        if name.endswith(".html") and not name.startswith("_"):
            if EXTENDS.search(open(os.path.join(folder, name), encoding="utf-8").read()):
                out.add(name)
    return out


def tabs():
    from routes import device_v2
    return {f"tab:{key}" for key, _label in device_v2.TABS}


def test_every_screen_is_registered_and_nothing_else():
    population = pages() | tabs()
    assert len(pages()) >= 12 and len(tabs()) >= 8, (pages(), tabs())   # the floors
    registered = set(R.SIGNED_OFF) | set(R.UNSIGNED)
    missing, ghosts = population - registered, registered - population
    assert not missing, ("a v2 screen with no entry: it needs a mockup and the operator's "
                         f"sign-off, entered in tests/signed_off_screens.py: {sorted(missing)}")
    assert not ghosts, f"entries for screens that no longer exist: {sorted(ghosts)}"
    assert not set(R.SIGNED_OFF) & set(R.UNSIGNED)


def test_each_entry_names_when_and_where():
    for key, (date, where) in R.SIGNED_OFF.items():
        assert re.fullmatch(r"20\d\d-\d\d-\d\d", date), key
        assert len(where.split()) >= 4, key
    for key, (why, next_step) in R.UNSIGNED.items():
        assert why.strip() and next_step.strip(), key


def test_the_unsigned_list_only_shrinks():
    assert len(R.UNSIGNED) <= R.UNSIGNED_CEILING


def test_a_planted_page_is_found(tmp_path):
    """The control: a page template nobody registered is in the population."""
    for name in os.listdir(V2):
        if name.endswith(".html"):
            (tmp_path / name).write_text(open(os.path.join(V2, name), encoding="utf-8").read())
    (tmp_path / "planted.html").write_text('{% extends "v2/base.html" %}\n')
    (tmp_path / "_fragment.html").write_text('{% extends "v2/base.html" %}\n')
    found = pages(str(tmp_path))
    assert "planted.html" in found and "_fragment.html" not in found
