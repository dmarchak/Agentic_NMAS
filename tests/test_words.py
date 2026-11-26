"""The one home for joining names into a sentence (`modules/words.series`), which the Settings,
Needs attention, device and Devices sentences share (Stage 5, 2026-11-25)."""
def series(*a, **k):
    """`words.series`, imported when called (a tree without it fails each test, red)."""
    from modules.words import series as s
    return s(*a, **k)


def test_one_two_and_many_names_read_as_a_sentence():
    assert series([]) == ""
    assert series(["a"]) == "a"
    assert series(["a", "b"]) == "a and b"
    assert series(["a", "b", "c"]) == "a, b and c"


def test_past_most_the_rest_are_counted_and_one_more_is_named():
    assert series(["a", "b", "c", "d"], 3) == "a, b, c and d"
    assert series(["a", "b", "c", "d", "e"], 3) == "a, b, c and 2 more"
    assert series(["a", "b", "c", "d", "e"]) == "a, b, c, d and e"


def test_the_four_sentences_use_it_and_keep_no_join_of_their_own():
    import inspect

    from modules import attention, device_list, device_page, settings_page
    for mod, fn in ((settings_page, "sentence"), (device_page, "sentence"),
                    (device_list, "sentence"), (attention, "sentence")):
        src = inspect.getsource(getattr(mod, fn))
        assert "series(" in src, mod.__name__
        assert '" and " +' not in src, f"{mod.__name__}.{fn} joins names itself"


def test_lower_start_lowers_a_plain_word_never_the_products_name_or_an_acronym():
    """A reason continuing a sentence after a colon (Stage 5 step 4): the incident page drew
    "It needs a person: mercury cannot fix this yet" from a first letter lowered by hand."""
    from modules.brand import PRODUCT_SHORT
    from modules.words import lower_start
    assert lower_start("Tried to put back the line") == "tried to put back the line"
    assert lower_start("Its fix ran") == "its fix ran"
    for same in (f"{PRODUCT_SHORT} cannot fix this yet", "BGP is down", "R1 reloaded",
                 "NetBox refused", "AI investigating", "already lower", "", "X"):
        assert lower_start(same) == same, same
    assert lower_start(None) == ""


def test_no_module_lowers_a_first_letter_by_hand():
    """The shape, not its members: every first letter lowered for a sentence's continuation
    goes through `words.lower_start`; seven did it by hand (the incident page, the incidents
    list twice, one with `.replace(" mercury", " Mercury")` over its result, a restart's
    reason, two run steppers, Needs attention twice). Parsed from the source, with a planted
    case and a floor on the files read."""
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # A first letter lowered and the rest joined back on, never a lowercase comparison.
    hand = re.compile(r"\[(?:0|:1)\]\.lower\(\)\s*\+\s*[\w.'\"\[\]()]*\[1:\]")
    read, found = 0, []
    for top in ("modules", "routes"):
        for dirpath, _dirs, files in os.walk(os.path.join(root, top)):
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, root)
                read += 1
                if rel == os.path.join("modules", "words.py"):
                    continue
                with open(path, encoding="utf-8") as fh:
                    found += [f"{rel}:{i}" for i, line in enumerate(fh, 1)
                              if hand.search(line)]
    assert read > 300, f"the scan read {read} files"
    assert found == [], f"a first letter lowered by hand; use words.lower_start: {found}"
    assert hand.search('waits = waits[:1].lower() + waits[1:]')
    assert hand.search('label[0].lower() + label[1:]')
