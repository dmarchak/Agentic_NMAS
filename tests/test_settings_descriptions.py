"""Every setting's one-line description (the week plan of 2026-11-23, Stage 5).

- **The source:** `modules/settings_schema.DESCRIPTIONS` holds exactly one line for every
  key `settings_schema.DEFAULTS` declares, drawn or not (a later screen draws it), none for a
  key the schema does not declare; each line is plain: one sentence, short, no key, module or
  finding names.
- **Every drawn setting:** on every Settings screen (Installation's tabs, Default's and a
  network's tabs, the cards and forms they load, a group's switch preview), each setting drawn
  carries its description from the source, never an empty one and never other words: each
  `data-setting` is a declared key whose text is its line; each form field named by a key has
  its line on that page; and the keys the screens' own tables declare (every generic card's
  group, every Installation card's fields and secret, the access gates, the record stores, the
  self-healing stops) are each drawn with theirs.

Through the real app, routes and templates, on `test_settings_v2`'s temporary store.
"""

import html
import re

import pytest

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

#: A drawn description: the span `_macros.setting_desc` draws.
_DRAWN = re.compile(r'<span class="set-desc" data-setting="([^"]*)">([^<]*)</span>')
#: A form control and the name it sends.
_CONTROL = re.compile(r'<(?:input|select|textarea)\b[^>]*\bname="([a-z0-9_]+)"')
#: A settings key's shape inside prose: the descriptions are read by people, not by code.
_KEY_SHAPE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")
#: The longest line a description may be: one line under the setting at the card's width.
LONGEST = 130


def _defaults() -> dict:
    from modules.settings_schema import DEFAULTS
    return DEFAULTS


class TestTheSource:
    def test_every_declared_key_has_exactly_one_non_empty_description(self):
        from modules.settings_schema import DESCRIPTIONS, describe

        declared = set(_defaults())
        assert len(declared) > 200, "the population: every key DEFAULTS declares"
        missing = sorted(k for k in declared if not describe(k).strip())
        assert not missing, f"declared keys with no description: {missing}"
        stray = sorted(set(DESCRIPTIONS) - declared)
        assert not stray, f"descriptions of keys the schema does not declare: {stray}"

    def test_an_undeclared_key_describes_as_empty(self):
        from modules.settings_schema import describe

        assert describe("no_such_setting_anywhere") == ""

    def test_each_line_is_plain_and_one_line(self):
        """Every description, each judged by every check below; the failures named by key."""
        from modules.settings_schema import DESCRIPTIONS

        assert len(DESCRIPTIONS) > 200, "the population: a line for every declared key"
        bad = {}
        for key, text in sorted(DESCRIPTIONS.items()):
            why = [w for ok, w in (
                (text == text.strip() and "\n" not in text, "one line, no padding"),
                (len(text) <= LONGEST, f"{len(text)} characters, longer than {LONGEST}"),
                (text[:1].isupper() or text[:1].isdigit(), "starts a sentence"),
                (text.endswith((".", "?")), "ends as a sentence"),
                (not _KEY_SHAPE.search(text), "names an internal key"),
                ("`" not in text and ".py" not in text, "names code"),
                (not re.search(r"\bC\d{2,}\b", text), "names a register row"),
            ) if not ok]
            if why:
                bad[key] = (why, text)
        assert not bad, f"descriptions that are not one plain line: {bad}"


def _pages(client) -> dict:
    """Every Settings screen and the cards and forms it loads, ``{path: html}``."""
    from flask import url_for

    import app as A
    from modules import installation_settings as I
    from modules import settings_page as P

    with A.app.test_request_context():
        paths = [url_for("settings_v2.installation", tab=t) for t, _ in I.TABS]
        for net in ("Default", "Branch", "Lab-3", "Remote"):
            paths += [url_for("settings_v2.network", list_name=net, tab=t) for t, _ in P.TABS]
        paths += [url_for("settings_v2.install_replace_form", name=n)
                  for n, c in I.CARDS.items() if c["secret"]]
        paths += [url_for("settings_v2.records_replace_form"),
                  url_for("settings_v2.local_account_card"),
                  url_for("settings_v2.group_preview", list_name="Lab-3", group="grafana",
                          to="own"),
                  url_for("settings_v2.group_preview", list_name="Branch", group="grafana",
                          to="inherit")]
    out = {}
    for path in paths:
        r = client.get(path)
        assert r.status_code == 200, f"{path}: {r.status_code}"
        out[path] = r.get_data(as_text=True)
    return out


@pytest.fixture
def pages(networks):  # noqa: F811 (the fixture imported above)
    return _pages(networks["client"])


def _drawn(page: str) -> dict:
    return {k: html.unescape(t) for k, t in _DRAWN.findall(page)}


class TestEveryDrawnSettingIsDescribed:
    def test_each_description_drawn_is_its_key_s_line_from_the_source(self, pages):
        from modules.settings_schema import DESCRIPTIONS

        seen = 0
        for path, page in pages.items():
            for key, text in _DRAWN.findall(page):
                seen += 1
                assert key in _defaults(), f"{path}: a description for {key!r}, not a setting"
                assert html.unescape(text).strip(), f"{path}: {key}'s description is empty"
                assert html.unescape(text) == DESCRIPTIONS[key], f"{path}: {key}'s words"
        assert seen > 100, f"the floor: {seen} descriptions drawn across the Settings screens"

    def test_every_field_named_by_a_setting_carries_its_description(self, pages):
        undescribed = {}
        fields = 0
        for path, page in pages.items():
            drawn = _drawn(page)
            for name in set(_CONTROL.findall(page)) & set(_defaults()):
                fields += 1
                if name not in drawn:
                    undescribed.setdefault(path, []).append(name)
        assert fields > 50, f"the floor: {fields} setting fields across the Settings screens"
        assert not undescribed, f"fields drawn with no description: {undescribed}"

    def test_every_key_the_screens_declare_is_drawn_with_its_description(self, pages):
        from modules import identity, records_db
        from modules import installation_settings as I
        from modules import settings_page as P
        from modules.heal_page import GUARD_ROWS
        from modules.settings_scope import group_keys

        declared = set()
        for tab in ("integrations", "network"):
            for g in P.tab_groups(tab):
                declared.update(group_keys(g))
        for c in I.CARDS.values():
            declared.update(f["key"] for f in c["fields"])
            declared.update(x[0] for x in (c["secret"], c["with_id"]) if x)
        declared.update(f"require_{w}_for_{a}" for w in ("identity", "person")
                        for a in identity.GATED_ACTIONS)
        declared.update(f"records_store_{s}" for s in records_db.STORES)
        declared.update(k for _label, keys, _fmt in GUARD_ROWS for k in keys)
        declared.update(("netbox_allow_writes", "ai_hosted", "ai_background", "platform_map",
                         "platform_default_netmiko_type", "records_db_host",
                         "records_db_password", "local_account_enabled", "heal_mode",
                         "heal_kinds_auto", "heal_kinds_propose", "heal_notify_team",
                         "heal_notify_events", "heal_stopped", "sdn_controllers",
                         "network_stage", "code_repository", "code_review",
                         "ai_device_state_class", "cf_access_team_domain",
                         "cf_access_jwks_ttl", "service_allowed_operations"))
        assert len(declared) > 150, f"the floor: {len(declared)} keys the screens declare"
        drawn = set()
        for page in pages.values():
            drawn.update(k for k, t in _drawn(page).items() if t.strip())
        assert not sorted(declared - drawn), \
            f"declared on a Settings screen, drawn with no description: {sorted(declared - drawn)}"
