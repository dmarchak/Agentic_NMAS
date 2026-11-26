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
