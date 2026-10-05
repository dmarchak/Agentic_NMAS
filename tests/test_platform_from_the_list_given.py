"""C495 (the operator, 2026-10-05, blocking the throwaway session): editing tw-ztp-a's intent
on v2 (`?list=throwaway`) was refused "the tool does not know its platform … Its inventory
row says no platform and no device_type", while its row in throwaway holds `cisco_iosxe` and
`cisco_xe` (measured on the host). The editor's preview took the platform from
`routes.templates._platform_for`, whose `_row_for` read the ACTIVE list (Default, no
tw-ztp-a), and the refusal described a row that was never found. Bulk intent's render did the
same.

On test_device_page_network's two real networks (Default active and empty; Twin holds tw-a):

- the platform is read from the list given, and the active list's absence of the device
  changes nothing;
- a list without the row is said as such, naming the list, never as a row that names no
  platform;
- the editor's preview and bulk intent's render pass their list (one call each, by AST).
"""

from tests.test_device_page_network import twin  # noqa: F401 (the fixture)


def test_the_platform_is_read_from_the_list_given(twin):  # noqa: F811
    from routes.templates import _platform_for
    assert _platform_for("tw-a", "Twin") == "cisco_iosxe"
    assert _platform_for("tw-a") == "", "the active list (Default) holds no tw-a"


def test_a_list_without_the_row_says_so_naming_it(twin):  # noqa: F811
    from routes.templates import unknown_platform_words
    words = unknown_platform_words("tw-a", "Default")
    assert "no row in Default's inventory" in words
    assert "says no platform" not in words


def test_a_row_that_names_no_platform_is_still_said_as_such(twin, monkeypatch):  # noqa: F811
    from routes import templates
    monkeypatch.setattr(templates, "_row_for", lambda h, l="": {"hostname": h})
    assert "says no platform and no device_type" in templates.unknown_platform_words("tw-a",
                                                                                     "Twin")


def test_the_editor_and_bulk_intent_pass_their_list():
    import ast
    import inspect
    import textwrap

    from modules.nsot import intent_edit
    from routes import templatize

    def platform_calls(fn):
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        return [c for c in ast.walk(tree) if isinstance(c, ast.Call)
                and getattr(c.func, "id", "") == "_platform_of_host"]

    for fn in (intent_edit.preview, templatize._bulk_render_and_eligible):
        calls = platform_calls(fn)
        assert calls, fn.__name__
        assert all(len(c.args) == 2 and getattr(c.args[1], "id", "") == "list_name"
                   for c in calls), fn.__name__
