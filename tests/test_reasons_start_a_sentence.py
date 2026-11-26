"""A reason drawn after a full stop starts its sentence with a capital (Stage 5 step 6, the
survey's plain-language rubric: Monitoring said "... have not been read yet. its reader has not
run yet"). Reasons are made lowercase on purpose, because most are drawn after a colon
("Couldn't load: <why>"); where a template draws one right after a bold sentence's full stop,
it goes through the `capital` filter (`words.capital`), which capitalises a plain first word
and leaves a file name or key it begins with alone.

- The helper: a plain lowercase first word is capitalised; a path, a key, an already capital
  word and an empty value are unchanged.
- The shape is constrained, not the members listed: every template expression drawn right after
  `.</strong> ` whose value is a reason (a `why`, `error` or `reason`) passes through
  `| capital`; the scan's population has a floor, and a planted template without it is found.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates", "v2")
#: A reason drawn as a sentence's start: right after a bold sentence's full stop, an expression
#: naming a `why`, an `error` or a `reason`.
SITE = re.compile(r"\.</strong> \{\{ ([^}]*\b[a-z_]*(?:why|error|reason)[a-z_]*\b[^}]*)\}\}")
#: The sites measured 2026-11-26: thirteen, in six templates.
MEASURED_SITES = 13


def _unfiltered(text: str) -> list:
    return [m.group(1).strip() for m in SITE.finditer(text)
            if not re.search(r"\|\s*capital\s*$", m.group(1).strip())]


def _scan() -> tuple:
    sites, bare = 0, []
    for name in sorted(os.listdir(TEMPLATES)):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(TEMPLATES, name), encoding="utf-8") as fh:
            text = fh.read()
        sites += len(SITE.findall(text))
        bare += [f"{name}: {expr}" for expr in _unfiltered(text)]
    return sites, bare


def test_a_plain_first_word_is_capitalised_and_nothing_else_moves():
    from modules import words
    assert words.capital("its reader has not run yet") == "Its reader has not run yet"
    assert words.capital("no export: export it first") == "No export: export it first"
    # A hyphenated word and a contraction are plain words too (Jinja's capitalize, which these
    # sites used, capitalised them: "Re-subscribed; ...").
    assert words.capital("re-subscribed; the stream did not come back") == \
        "Re-subscribed; the stream did not come back"
    assert words.capital("it's done") == "It's done"
    assert words.capital("r3's logs") == "r3's logs"
    # A whole sentence stored in capitals reads in sentence case; one acronym stays.
    assert words.capital("THE RECEIVER IS REMOVED") == "The receiver is removed"
    assert words.capital("BGP") == "BGP"
    for same in ("user_settings.json: torn", "records_db could not be read", "It is read",
                 "/var/lib/x is missing", "", "HTTP 500"):
        assert words.capital(same) == same, same
    assert words.capital(None) == ""


def test_every_reason_after_a_full_stop_goes_through_capital():
    sites, bare = _scan()
    assert sites >= MEASURED_SITES, \
        f"the scan found {sites} sites, under the {MEASURED_SITES} measured"
    assert bare == [], ("a reason drawn after a full stop starts lowercase; pipe it through "
                        f"`| capital`: {bare}")


#: A page's own banner for a background read not read yet, or whose stored value cannot be
#: read, in the words each page wrote for itself before `not_read_yet` and `read_unreadable`.
OWN_BANNER = re.compile(r"<p>The [\w' -]+ reader (?:has not read|'s store cannot be read)")


def test_no_page_says_a_reader_has_not_read_in_words_of_its_own():
    """Stage 5 step 6: five pages said "The <X> reader has not read <product> yet" and "The
    <X> reader's store cannot be read", each its own way, naming the reader and a product
    (Kea, Prometheus); each now draws the macros' plain words. A planted banner is found."""
    own, macros = [], 0
    for name in sorted(os.listdir(TEMPLATES)):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(TEMPLATES, name), encoding="utf-8") as fh:
            text = fh.read()
        own += [name for _m in OWN_BANNER.finditer(text)]
        macros += len(re.findall(r"\{\{ (?:not_read_yet|read_unreadable)\(", text))
    assert macros >= 10, f"the macros are drawn at {macros} sites, under the 10 measured"
    assert own == [], f"a banner in words of its own; use not_read_yet/read_unreadable: {own}"
    assert OWN_BANNER.search('<p>The DHCP reader has not read Kea yet')


#: Jinja's own `capitalize`, which lowers every letter after the first.
CAPITALIZE = re.compile(r"\|\s*capitalize\b")


def test_no_page_uses_jinjas_capitalize_which_lowers_the_rest():
    """Jinja's `capitalize` upper-cases the first letter and LOWERS the rest, so a name after it
    is mangled (a person's reason, "Prometheus is not configured for Lab" → "... for lab", a
    person's name in a stop's words). Thirty v2 sites used it; each uses `capital`
    (`words.capital`), which touches only a plain lowercase first word. A planted use is found."""
    sites, found = 0, []
    for name in sorted(os.listdir(TEMPLATES)):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(TEMPLATES, name), encoding="utf-8") as fh:
            text = fh.read()
        sites += len(re.findall(r"\|\s*capital\b", text))
        found += [name for _m in CAPITALIZE.finditer(text)]
    assert sites >= 30, f"`capital` is drawn at {sites} sites, under the 30 measured"
    assert found == [], f"Jinja's capitalize lowers names after the first letter: {found}"
    assert CAPITALIZE.search("{{ fb.why | capitalize }}")
    from modules import words
    assert words.capital("prometheus is not configured for Lab") == \
        "Prometheus is not configured for Lab"


def test_a_planted_bare_reason_is_found_and_a_filtered_one_is_not():
    planted = ('<p><strong>Not read.</strong> {{ g.why }}</p>'
               '<p><strong>Not read.</strong> {{ (g.error or "none") | capital }}</p>'
               '<p><strong>Read:</strong> {{ g.why }}</p>')
    assert _unfiltered(planted) == ["g.why"]
