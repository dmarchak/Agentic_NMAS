"""The nightly mutation run's canary (docs/TESTING.md, "Mutation testing"; not a test module).

Every night mutates these two functions first, beside the changed code, and every one of their
mutants must be KILLED by tests/test_mutation_canary.py. `in_process` is reached only in the
test's own process, and `in_child` only through a child process the test starts, as
config_check's tests reach the check through `scripts/nmas-config-check`. A canary mutant that
survives means the measurement is broken (a child that does not run the mutant, a test the run
never selects, mutants failing each other's tests in reverse): the night fails as "measurement
broken", never as survivors, and no result of it stands. The lesson of the first pass's 129 of
132 (C766), in the other direction."""


def in_process(a: int, b: int) -> int:
    """The sum, or -1 when either is negative."""
    if a < 0 or b < 0:
        return -1
    return a + b


def in_child(a: int, b: int) -> int:
    """Two digits as a number (no comparison, so no boundary mutant is equivalent)."""
    return a * 10 + b


def untested(a: int, b: int) -> int:
    """No test calls this (C1651's second canary, the operator, 2026-11-03): every one of its
    mutants must SURVIVE (or read "no tests"). One killed means the run kills what nothing
    tests (a copy whose every test fails, a selection running the wrong tests), so its kills
    prove nothing: the night fails as "measurement broken". The other direction of the two
    above."""
    if a > b:
        return a - b
    return b - a
