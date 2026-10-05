"""C468: Settings › NetBox › Test says NetBox's own reason, and names a missing permission.

The Test turned every 401 and 403 into "Authentication failed — check the API token". An
expired token, a token NetBox does not know, and a source address the token does not allow each
need a different repair, and a person could not tell them apart. And `api/status/` needs no
permission at all, so a token missing a VIEW the tool reads passed the Test and failed later,
in a sync, one type at a time (C100's survey, 2026-10-05). The refusal texts below are NetBox's
own `detail` words as its API returns them.
"""

import pytest

from modules import netbox_client as nc


class _R:
    def __init__(self, status, detail=None, body=None):
        self.status_code = status
        self._doc = body if body is not None else ({"detail": detail} if detail else {})
        self.content = b"x"
        self.text = str(self._doc)

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._doc


class _Session:
    """Answers `api/status/` with *status*, and each read probe 200 unless refused."""

    def __init__(self, status=None, refuse=()):
        self.status = status or _R(200, body={"netbox-version": "4.6.9"})
        self.refuse = dict(refuse)

    def get(self, url, params=None, timeout=None):
        if url.endswith("/api/status/"):
            return self.status
        path = url.split("/api/", 1)[1]
        if path in self.refuse:
            return _R(403, self.refuse[path])
        return _R(200, body={"count": 0, "results": []})


@pytest.fixture
def wire(monkeypatch):
    def _wire(session):
        monkeypatch.setattr(nc, "_build_session", lambda *a, **k: session)
        monkeypatch.setattr(nc, "set_user_setting", lambda *a, **k: None)
    return _wire


@pytest.mark.parametrize("detail, advice", [
    ("Token expired", "has expired"),
    ("Source IP 192.0.2.7 is not permitted to authenticate using this token.", "Allowed IPs"),
    ("Invalid v2 token", "does not know this token"),
])
def test_a_refused_token_says_netboxs_reason_and_what_to_do(wire, detail, advice):
    wire(_Session(status=_R(403, detail)))
    ok, msg = nc.test_connection("http://nb.invalid", "nbt_x.y")
    assert ok is False
    assert detail in msg, msg
    assert advice in msg, msg
    assert "Authentication failed" not in msg


def test_a_token_missing_a_view_is_named_by_type(wire):
    wire(_Session(refuse={"users/tokens/": "You do not have permission to perform this action.",
                          "extras/tags/": "You do not have permission to perform this action."}))
    ok, msg = nc.test_connection("http://nb.invalid", "nbt_x.y")
    assert ok is False, "a token that cannot read what the tool reads passed the Test"
    assert "Users › token" in msg and "Extras › tag" in msg, msg
    assert "Connected to NetBox (version 4.6.9)" in msg


def test_a_token_that_reads_everything_passes(wire):
    """The control: the probes must not refuse a token that can read every type."""
    wire(_Session())
    ok, msg = nc.test_connection("http://nb.invalid", "nbt_x.y")
    assert ok is True, msg
    assert f"every type the tool reads answered ({len(nc.READ_PROBES)})" in msg


def test_the_probes_are_the_types_the_service_account_grants_view_on():
    """READ_PROBES and SERVICE_ACCOUNTS 1.3's `nmas-view` list must not drift apart: each
    probe's type is named there."""
    import os
    import re

    doc = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "docs", "SERVICE_ACCOUNTS.md"), encoding="utf-8").read()
    view = doc[doc.index("**`nmas-view`**"):doc.index("**`nmas-add`**")].lower()
    missing = [label for _p, label in nc.READ_PROBES
               if re.sub(r"^.* › ", "", label).lower() not in view]
    assert missing == [], f"probed but not granted view in SERVICE_ACCOUNTS 1.3: {missing}"
