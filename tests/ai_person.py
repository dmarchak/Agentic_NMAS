"""A verified person's request, for tests that press an AI feature by calling it (C1843: the
gateway refuses a person trigger outside a request, and inside one unless it names the request's
verified actor). Not a test module.

`pressed_by(actor)` pushes a request whose identity is the one the gate leaves on ``flask.g``
for a verified person (`route_gates.enforce`), so `identity.request_actor()` answers *actor*.
A test file presses as `PERSON` throughout with an autouse fixture holding it open.
"""
import contextlib

#: The person the AI tests press as.
PERSON = "operator@example.com"


def identity_of(actor: str):
    """The identity the gate verified for *actor*, a person."""
    from modules import identity
    return identity.Identity(actor=actor, email=actor, kind="person", verified=True,
                             outcome="ok", peer_trusted=True)


@contextlib.contextmanager
def pressed_by(actor: str = PERSON):
    """A POST request whose access assertion verified *actor*."""
    import app as APP
    from flask import g

    with APP.app.test_request_context("/", method="POST"):
        g.nmas_identity = identity_of(actor)
        yield
