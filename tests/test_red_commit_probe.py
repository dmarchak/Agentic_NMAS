"""P.4 step 4 acceptance, the red-commit test: this commit is meant to FAIL CI.

It exists so `nmas-deploy` can be shown refusing a commit CI has not passed:
pending while the run is in progress, failed once it completes, and `--offline`
failing here. The commit that follows reverts it. It is an ordinary failed
assertion rather than a collection error, so the run fails for the stated
reason and the rest of the suite still runs.
"""


def test_this_commit_is_deliberately_red():
    assert False, "P.4 step 4 red-commit probe: CI must fail on this commit"
