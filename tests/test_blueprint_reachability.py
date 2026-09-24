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
"""

import re

import pytest

from tests.js_source import with_loaded_scripts

#: Blueprints with no route referenced by the rendered page, and why that is
#: tolerated for now. **Entries must leave as they are built**, exactly like
#: `KNOWN_DEAD` in `test_no_unreachable_ui.py` — an allowlist that only grows
#: is a place findings go to be forgotten.
KNOWN_UNREACHABLE = {}

#: Route modules that exist to serve the GUI. A blueprint serving only the AI
#: agent or an external caller is out of scope; naming them here keeps the
#: check about the interface rather than about every route in the app.
#:
#: `identity` is deliberately ABSENT rather than allowlisted. `/identity/status`
#: is a read-only diagnostic meant to be reached directly -- "a diagnostic that
#: hides behind identity is useless when identity breaks" -- so the GUI not
#: calling it is its design, not a gap. `KNOWN_UNREACHABLE` is for gaps to
#: close; putting a diagnostic there would imply somebody should close it.
GUI_BLUEPRINTS = ("templatize", "templates", "deploy", "golden", "remote",
                  "inventory", "monitoring_stack", "topology_view", "onboard")


@pytest.fixture(scope="module")
def rendered():
    import app as nmas

    return with_loaded_scripts(nmas.app.test_client().get("/").get_data(as_text=True))


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
        """An empty page would make every blueprint look unreachable."""
        assert len(rendered) > 100_000

    def test_the_check_finds_reachable_ones(self, rendered):
        """If this cannot see a blueprint the GUI *does* call, every result
        below is meaningless."""
        groups = _routes_by_blueprint()
        assert _reachable(groups.get("golden", []), rendered)
        assert _reachable(groups.get("deploy", []), rendered)
        assert _reachable(groups.get("monitoring_stack", []), rendered)

    def test_no_new_unreachable_blueprint(self, rendered):
        groups = _routes_by_blueprint()
        unreachable = []
        for name in GUI_BLUEPRINTS:
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


class TestTheTemplatizeGapIsClosed:
    """It was twelve routes with zero references, measured 2026-09-23.

    The asymmetry that made it serious: Deploy plan READS committed intent
    and has had a button since Stage 1.5, so the interface could push a
    change toward a target it had no way to set.
    """

    def test_templatize_is_now_referenced(self, rendered):
        assert "/templatize" in rendered

    def test_the_editor_reads_committed_intent(self, rendered):
        assert "/templatize/committed/" in rendered

    def test_the_editor_previews_before_committing(self, rendered):
        """The requirement that makes a text editor usable rather than
        merely honest."""
        assert "/preview" in rendered

    def test_the_intent_editor_route_exists(self):
        import app as nmas

        posts = [str(r) for r in nmas.app.url_map.iter_rules()
                 if "POST" in (r.methods or set())
                 and str(r).startswith("/templatize/committed/")]
        assert posts, "no POST route for editing committed intent"

    def test_both_halves_of_the_loop_are_reachable(self, rendered):
        """Edit intent -> see the plan -> deploy. The loop the deploy path
        assumed and nobody could exercise."""
        assert "/templatize/committed/" in rendered
        assert "/deploy/plan" in rendered
