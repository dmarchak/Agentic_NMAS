"""The model a v2 device-action card is drawn from, read through the card's real route.

Today's device-action JSON routes (/persist/*, /rotate/*, /retire/*, /templatize/seed/*,
/templatize/revert/* and /templatize/retry/*) returned the preview and result models as JSON,
and their tests read those. They left at 7.8 (2026-10-17, P7-24); each device page's Actions
draws the same models server-side (`modules/device_actions.py`'s card builders). A test of a
property of the model now reads the model the v2 route hands its card builder, so it holds for
the route a person uses: `spying(device_actions, "persist_card")` records each call's
arguments while the request runs, and the test takes the model from them.
"""

from contextlib import contextmanager
from unittest import mock


@contextmanager
def spying(module, name):
    """Record ``(args, kwargs)`` of every call to ``module.name`` inside the block; the real
    function still runs, so the route answers as it does for a person."""
    calls = []
    real = getattr(module, name)

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    with mock.patch.object(module, name, spy):
        yield calls


def the_one(calls, name):
    """The one call recorded, or a failure naming how many there were."""
    assert len(calls) == 1, f"{name} was called {len(calls)} time(s), not once"
    return calls[0]
