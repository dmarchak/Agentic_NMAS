"""A blueprint the interface never calls is a feature that does not exist.

`test_no_unreachable_ui.py` catches a JavaScript function with no caller.
This catches the same shape one level up: a whole route module the rendered
page never reaches.

Measured 2026-09-23: `routes/templatize.py` has twelve routes and the string
`/templatize` appears **zero times** in the rendered page. Extract, review,
commit, **edit** and revert committed intent — the operations Phase 3c calls
the only legitimate way to change what a device should look like — are
reachable by `curl` and by nothing else.

The asymmetry is what makes it serious rather than untidy: "Deploy plan"
*reads* committed intent and has a button, so the interface can push a change
toward a target it has no way to set.

"The rendered page" is the interface's pages (tests/interface_pages.py): v2's, by the links
between them, and today's while they exist. Until P7-19 (2026-10-15) it was today's index
alone, so removing it would have made every blueprint unreachable at once.
"""

import re

import pytest

from tests import interface_pages

#: Blueprints with no route referenced by the rendered page, and why that is
#: tolerated for now. **Entries must leave as they are built**, exactly like
#: `KNOWN_DEAD` in `test_no_unreachable_ui.py` — an allowlist that only grows
#: is a place findings go to be forgotten.
KNOWN_UNREACHABLE = {
    "console_ztp_v2": "reached only from Add device's review, a POST answer the page walk does "
                      "not render; leaves when the pending page carries the console card (C1575)",
}

#: Route modules that exist to serve the GUI. A blueprint serving only the AI
#: agent or an external caller is out of scope; naming them here keeps the
#: check about the interface rather than about every route in the app.
#:
#: `identity` is deliberately ABSENT rather than allowlisted. `/identity/status`
#: is a read-only diagnostic meant to be reached directly -- "a diagnostic that
#: hides behind identity is useless when identity breaks" -- so the GUI not
#: calling it is its design, not a gap. `KNOWN_UNREACHABLE` is for gaps to
#: close; putting a diagnostic there would imply somebody should close it.
#:
#: Today's blueprints are named; v2's are found, by property: a blueprint with a route
#: under `/v2/` serves v2's interface (`_gui_blueprints`), so a new one is checked the
#: commit it lands.
GUI_BLUEPRINTS = ("templatize", "templates", "deploy", "golden", "remote",
                  "inventory", "onboard")


def _gui_blueprints() -> tuple:
    found = {name for name, paths in _routes_by_blueprint().items()
             if any(p.startswith("/v2/") for p in paths)}
    return tuple(GUI_BLUEPRINTS) + tuple(sorted(found - set(GUI_BLUEPRINTS)))


@pytest.fixture(scope="module")
def rendered():
    return interface_pages.corpus()


def _routes_by_blueprint():
    import app as nmas

    groups = {}
    for rule in nmas.app.url_map.iter_rules():
        if not rule.endpoint or "." not in rule.endpoint:
            continue
        blueprint = rule.endpoint.split(".", 1)[0]
        groups.setdefault(blueprint, []).append(str(rule))
    return groups


def _reachable(paths, page):
    """Is any of these paths referenced, in any form?

    Compares the prefix before the first converter, so a dynamic URL built as
    `'/golden/history/' + host` still counts. A blueprint reached only
    through a path this cannot see would be a FALSE finding, which is why the
    prefix is deliberately short.
    """
    for path in paths:
        stem = re.split(r"<", path)[0].rstrip("/")
        if stem and stem in page:
            return True
    return False


class TestEveryGuiBlueprintIsReachable:
    def test_the_page_rendered(self, rendered):
        """An empty page would make every blueprint look unreachable. The floor is v2's
        pages alone: 3,774,798 bytes with their scripts on 2026-10-15."""
        assert len(interface_pages.v2_corpus()) > 3_000_000
        assert len(rendered) >= len(interface_pages.v2_corpus())

    def test_the_check_finds_reachable_ones(self, rendered):
        """If this cannot see a blueprint the GUI *does* call, every result
        below is meaningless. Read on v2's pages alone (until P7-19, golden and deploy on
        today's index)."""
        groups = _routes_by_blueprint()
        v2 = interface_pages.v2_corpus()
        assert _reachable(groups.get("device_v2", []), v2)
        assert _reachable(groups.get("intent_v2", []), v2)

    def test_v2_s_blueprints_are_in_the_population(self):
        """Found by their routes, so the population cannot silently be today's list: 17
        blueprints with a route under /v2/ on 2026-10-15."""
        found = set(_gui_blueprints()) - set(GUI_BLUEPRINTS)
        assert len(found) >= 15 and {"v2", "device_v2", "intent_v2"} <= found, sorted(found)

    def test_no_new_unreachable_blueprint(self, rendered):
        groups = _routes_by_blueprint()
        unreachable = []
        for name in _gui_blueprints():
            paths = groups.get(name)
            if not paths:
                continue
            if not _reachable(paths, rendered):
                unreachable.append(name)
        new = set(unreachable) - set(KNOWN_UNREACHABLE)
        assert not new, (
            f"{sorted(new)} serve the GUI and the GUI never calls them. "
            f"Give each an entry point, or record it in KNOWN_UNREACHABLE "
            f"with the reason.")

    def test_the_allowlist_has_no_stale_entries(self, rendered):
        """An entry that is now reachable must leave, or the allowlist stops
        describing anything."""
        groups = _routes_by_blueprint()
        stale = [name for name in KNOWN_UNREACHABLE
                 if _reachable(groups.get(name, []), rendered)]
        assert not stale, f"reachable now, remove from KNOWN_UNREACHABLE: {stale}"

    def test_every_entry_gives_a_reason(self):
        for name, reason in KNOWN_UNREACHABLE.items():
            assert len(reason) > 40, name


class TestTheIntentLoopIsReachable:
    """The templatize gap: twelve routes with zero references, measured 2026-09-23.

    The asymmetry that made it serious: Deploy plan READS committed intent
    and has had a button since Stage 1.5, so the interface could push a
    change toward a target it had no way to set.

    Read on v2's pages since P7-19 (2026-10-15): the device page's Intent tab edits intent in
    place (routes/intent_v2.py, board H) and its Actions menu plans a deploy. Until then these
    pinned today's editor on the index (`/templatize/committed/`, `/deploy/plan`), which goes
    with P7-23 and stays reached meanwhile by the route-reachability check.
    """

    @pytest.fixture(scope="class")
    def v2(self):
        return interface_pages.v2_corpus()

    def test_the_intent_tab_opens_the_editor(self, v2):
        assert "/v2/device/r3/intent/edit" in v2

    def test_the_editor_checks_before_committing(self, v2):
        """The requirement that makes a text editor usable rather than
        merely honest: the edit is checked (rendered and compared) as it is typed."""
        assert "/v2/device/r3/intent/check" in v2

    def test_the_intent_editor_route_exists(self):
        import app as nmas

        posts = [str(r) for r in nmas.app.url_map.iter_rules()
                 if "POST" in (r.methods or set())
                 and str(r) == "/v2/device/<name>/intent/commit"]
        assert posts, "no POST route for committing edited intent"

    def test_both_halves_of_the_loop_are_reachable(self, v2):
        """Edit intent -> see the plan -> deploy. The loop the deploy path
        assumed and nobody could exercise."""
        assert "/v2/device/r3/intent/commit" in v2
        assert "/v2/device/r3/deploy" in v2
