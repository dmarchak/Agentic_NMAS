"""Built for large fleets (CLAUDE.md, the operator, 2026-10-04): a screen listing devices or
results leads with a summary, groups and collapses, offers filter and search, and never draws
one long expanded list; per-device detail opens on expand.

The mechanised part: every v2 page, rendered with test_scale's realistic 900-device fleet as
the active list, names at most `LIMIT` of the fleet's devices OUTSIDE a closed `<details>`.
A page that draws them all, expanded, is a long list. The population is every argument-free
v2 GET page plus one device page, read from the app's URL map, so a page added later is
checked without being listed here.

Today's gaps are named exactly in `EXCUSED`, each with why and where its fix is owed, and the
list only shrinks: an excused page that no longer violates fails until it is removed.

The scan is shown able to find its case: a planted page listing every device expanded is
found, and the same list inside a closed `<details>` is not. A dropdown's options are a closed
control, never a drawn list.

What it assumes stays true: a page whose list comes from query parameters (a batch's selection)
is rendered without them, so its long-list case is checked by that page's own tests; the
summary, the grouping and the search are the rule's other half, not mechanised here.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures.fleet_scale import build_fleet  # noqa: E402
from tests.test_profile_apply import lab  # noqa: E402,F401 (the fixture)

FLEET = build_fleet(900)
#: More than this many of the fleet's devices drawn expanded is a long list. A page that groups
#: and collapses, or shows a filtered page of results, stays well under it.
LIMIT = 50

#: Pages that draw a long expanded list today: {path: why, and where the fix is owed}. Only
#: shrinks (`test_every_excused_page_still_violates`).
EXCUSED = {
    "/v2/devices": "every row drawn; 7.4's revised Devices board (summary, groups, paging) is "
                   "owed (C450, NSOT_STAGE7_PLAN 15.1 B)",
    "/v2/devices/table": "the same list, redrawn on a filter (C450)",
    "/v2/monitoring/coverage": "the grid draws every device; owed with 7.4's large-fleet rule "
                               "(C450)",
    "/v2/monitoring/coverage/table": "the same grid, redrawn (C450)",
}

NAMES = re.compile(r"\b(?:cor|edg|acc|dis)\d{4}\b")
CLOSED_DETAILS = re.compile(r"<details(?![^>]*\bopen\b)[^>]*>.*?</details>", re.S | re.I)


def expanded_devices(html: str) -> set:
    """The fleet's device names a page draws OUTSIDE a closed <details>, in its body."""
    body = html.split("<body", 1)[-1]
    body = re.sub(r"<script\b.*?</script>", "", body, flags=re.S | re.I)
    body = CLOSED_DETAILS.sub("", body)
    # A dropdown's options are a closed control (a filter), never a drawn list.
    body = re.sub(r"<select\b.*?</select>", "", body, flags=re.S | re.I)
    return set(NAMES.findall(body))


def _pages(app) -> list:
    out = []
    for rule in app.url_map.iter_rules():
        if "GET" not in rule.methods or rule.arguments or not rule.rule.startswith("/v2"):
            continue
        out.append(rule.rule)
    return sorted(set(out)) + [f"/v2/device/{FLEET[0]['hostname']}"]


@pytest.fixture
def fleet(lab, monkeypatch):
    rows = [dict(d) for d in FLEET]
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [dict(r) for r in rows])
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(r) for r in rows])
    return lab


def test_the_planted_long_list_is_found_and_a_collapsed_one_is_not():
    items = "".join(f"<li>{d['hostname']}</li>" for d in FLEET)
    assert len(expanded_devices(f"<body><ul>{items}</ul></body>")) == 900
    assert expanded_devices(f"<body><details><summary>900 devices</summary><ul>{items}</ul>"
                            "</details></body>") == set()
    assert len(expanded_devices(f"<body><details open><ul>{items}</ul></details></body>")) == 900


def test_no_page_draws_a_long_expanded_list(fleet):
    import app as A

    client = A.app.test_client()
    pages = _pages(A.app)
    assert len(pages) >= 15, f"the population shrank: {pages}"
    found = {}
    for path in pages:
        r = client.get(path)
        if not (r.content_type or "").startswith("text/html"):
            continue
        shown = expanded_devices(r.get_data(as_text=True))
        if len(shown) > LIMIT and path not in EXCUSED:
            found[path] = len(shown)
    assert found == {}, ("pages drawing more than %d of 900 devices expanded (summarise, group "
                         "and collapse, or page and filter): %s" % (LIMIT, found))


def test_every_excused_page_still_violates(fleet):
    import app as A

    client = A.app.test_client()
    fixed = [p for p in EXCUSED
             if len(expanded_devices(client.get(p).get_data(as_text=True))) <= LIMIT]
    assert fixed == [], f"fixed: take them out of EXCUSED, the list only shrinks: {fixed}"
