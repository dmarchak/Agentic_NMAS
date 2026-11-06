"""What a job's unit tests import from the SDK (the SDN platform design rev. 6, section 11a, item
2): `covers`, the marker that maps a test to a spec card's acceptance example, and
`refused`, the SDK's expected-refusal block. `raises` is the same block under pytest's name:
Mercury's runner (`modules/jobs/runner.py`) offers it as `pytest.raises`, so a job's tests run
unchanged under pytest and under the runner, and the runner never imports pytest.

- **`@covers("<example name>", ...)`** is a no-op at run time: it checks each name is a
  non-empty string and returns the test unchanged. The gate reads the names from the test's
  source (`modules/jobs/gate.py`, the examples check), so a name must be written as a string
  literal.
- **`with refused(match=None, kind=ContractError):`** passes when the block raises *kind*
  (by default `ContractError`, which `ChangeRefused` and `ScopeError` extend: every refusal
  the SDK gives), its message matching the regular expression *match* when one is given.
  A block that raises nothing, or something else, fails the test, naming what it expected and
  what happened.
- **`with raises(SomeError, match=None):`**, or `raises(SomeError, func, *args)`, is
  pytest's form of the same: the subset of `pytest.raises` a job's tests may use.
"""

import re

from modules.jobs.base import ContractError

__all__ = ["covers", "raises", "refused", "Raised"]


def covers(*examples):
    """Mark a test as covering the spec card's examples named (a no-op at run time)."""
    bad = [e for e in examples if not isinstance(e, str) or not e.strip()]
    if not examples or bad:
        raise TypeError(f"covers names one or more examples, each a non-empty string; given "
                        f"{examples!r}")

    def mark(test):
        return test
    return mark


class Raised:
    """What an expected refusal caught: `type` and `value`, as pytest's ExceptionInfo
    offers them, and `match(regex)`."""

    def __init__(self):
        self.type = None
        self.value = None

    def match(self, regex) -> bool:
        if self.value is None or not re.search(regex, str(self.value)):
            raise AssertionError(f"the refusal's message {str(self.value)!r} does not match "
                                 f"{regex!r}")
        return True


class _Expect:
    """A block that must raise *kind* (a class or a tuple of classes)."""

    def __init__(self, kind, match, words: str):
        kinds = kind if isinstance(kind, tuple) else (kind,)
        if not kinds or not all(isinstance(k, type) and issubclass(k, BaseException)
                                for k in kinds):
            raise TypeError(f"{words} names exception classes, not {kind!r}")
        self.kinds, self.match, self.words = kinds, match, words
        self.raised = Raised()

    def _names(self) -> str:
        return " or ".join(k.__name__ for k in self.kinds)

    def __enter__(self) -> Raised:
        return self.raised

    def __exit__(self, kind, value, _tb):
        if kind is None:
            raise AssertionError(f"DID NOT RAISE {self._names()}: {self.words} expected the "
                                 "block to raise it, and it raised nothing")
        if not issubclass(kind, self.kinds):
            return False                    # another exception: the test fails with it
        if self.match is not None and not re.search(self.match, str(value)):
            raise AssertionError(f"{self.words} caught {kind.__name__} {str(value)!r}, which "
                                 f"does not match {self.match!r}")
        self.raised.type, self.raised.value = kind, value
        return True


def refused(match=None, kind=ContractError):
    """A block that must be refused (see the module's docstring)."""
    return _Expect(kind, match, "refused()")


def raises(expected, *args, match=None, **kwargs):
    """pytest.raises' subset: a block, or `raises(Error, func, *args, **kwargs)`."""
    expect = _Expect(expected, match, "pytest.raises()")
    if not args:
        if kwargs:
            raise TypeError(f"pytest.raises() takes match= only as a block, not "
                            f"{sorted(kwargs)}")
        return expect
    func, rest = args[0], args[1:]
    with expect:
        func(*rest, **kwargs)
    return expect.raised
