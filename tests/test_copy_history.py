"""The shipped templates' history in mutmut's copy (C1651; tests/copy_history.py): only the
application's own history lookup of a path under the copy's prefix is redirected, to the same
path without it. A network repository's history, a path outside the prefix, and outside a copy
everything, are left as they are."""
from tests.copy_history import copy_prefix, history_in_copy


def _recorder():
    calls = []

    def history(cwd, rel, git=None):
        calls.append((cwd, rel, git))
        return [("c", "d", "b")]
    return history, calls


def test_the_prefix_is_the_copy_s_folder_inside_the_checkout(tmp_path):
    copy = tmp_path / "checkout" / "mutants"
    copy.mkdir(parents=True)
    assert copy_prefix(str(copy), str(tmp_path / "checkout")) == "mutants"
    assert copy_prefix(str(copy), "") == ""
    assert copy_prefix(str(tmp_path / "checkout"), str(tmp_path / "checkout")) == ""
    assert copy_prefix(str(tmp_path / "elsewhere"), str(tmp_path / "checkout")) == ""


def test_only_the_application_s_lookup_under_the_prefix_is_redirected():
    history, calls = _recorder()
    wrapped = history_in_copy(history, "mutants")
    wrapped("/ck", "mutants/modules/nsot/templates/_common.j2")
    wrapped("/ck", "modules/nsot/templates/_common.j2")
    wrapped("/net", "mutants/x.j2", git="list-repo-runner")
    wrapped("/ck", "mutantsX/modules/nsot/templates/_common.j2")
    assert calls == [
        ("/ck", "modules/nsot/templates/_common.j2", None),        # the copy's path, mapped
        ("/ck", "modules/nsot/templates/_common.j2", None),        # already the tracked path
        ("/net", "mutants/x.j2", "list-repo-runner"),              # a network's repository
        ("/ck", "mutantsX/modules/nsot/templates/_common.j2", None),  # not the prefix
    ]


def test_with_no_prefix_nothing_is_redirected():
    history, calls = _recorder()
    history_in_copy(history, "")("/ck", "mutants/modules/nsot/templates/_common.j2")
    assert calls == [("/ck", "mutants/modules/nsot/templates/_common.j2", None)]
