"""C3330: an integration's error says what happened (modules/integrations/base.py, `_get`).

The incident (2026-11-12): every failed read of `logs-tail` said "Could not connect to
http://127.0.0.1:3100" while Loki listened and answered /ready: the reads were TIMING OUT, and
urllib3's Retry turned each read timeout into a MaxRetryError whose reason is the
ReadTimeoutError, which requests raises as a ConnectionError. Held here with planted exceptions
of the real types, raised where the session's GET raises them:

- a read timeout, bare (requests' ReadTimeout) or wrapped by Retry (ConnectionError around
  MaxRetryError around ReadTimeoutError), reads "Loki did not answer within 5 s (<path>)";
- a refused connection (ConnectionError around MaxRetryError around NewConnectionError) and
  a connect timeout read as they are: only the refused one "Could not connect";
- each is "not answering" (reader_job rule 14), and the Loki readers' error carries the words
  once, never "could not be asked ... did not answer" with the path twice.
"""

import pytest
import requests
from urllib3.connection import HTTPConnection
from urllib3.exceptions import (ConnectTimeoutError, MaxRetryError, NewConnectionError,
                                ReadTimeoutError)

from modules.integrations import base
from modules.integrations.loki import LokiIntegration

URL = "http://192.0.2.7:3100"
PATH = "loki/api/v1/query_range"


def _pool():
    return HTTPConnection("192.0.2.7", 3100)


def read_timeout_retried():
    """What requests raises when urllib3's Retry gives up on a read timeout (the incident)."""
    inner = ReadTimeoutError(None, f"/{PATH}", "Read timed out. (read timeout=5.0)")
    return requests.exceptions.ConnectionError(MaxRetryError(None, f"/{PATH}", reason=inner))


def refused():
    inner = NewConnectionError(_pool(), "Failed to establish a new connection: [Errno 111] "
                                        "Connection refused")
    return requests.exceptions.ConnectionError(MaxRetryError(None, f"/{PATH}", reason=inner))


def connect_timeout():
    inner = ConnectTimeoutError(_pool(), "Connection to 192.0.2.7 timed out.")
    return requests.exceptions.ConnectTimeout(MaxRetryError(None, f"/{PATH}", reason=inner))


class _Session:
    def __init__(self, exc):
        self.exc = exc

    def get(self, *a, **kw):
        raise self.exc


def _ask(exc):
    client = LokiIntegration()
    client.timeout = 5.0
    client._session = _Session(exc)                     # noqa: SLF001 (the session's GET)
    return client


@pytest.fixture
def loki_url(monkeypatch):
    monkeypatch.setattr(LokiIntegration, "url", property(lambda self: URL))


@pytest.mark.parametrize("exc", [read_timeout_retried(),
                                 requests.exceptions.ReadTimeout("read timed out")],
                         ids=["retried", "bare"])
def test_a_read_timeout_says_loki_did_not_answer_within_its_bound(loki_url, exc):
    got = _ask(exc)._get(PATH)                          # noqa: SLF001
    assert got["error"] == f"Loki did not answer within 5 s ({PATH})", got
    assert got["not_answering"] is True and got["timed_out"] is True
    assert "Could not connect" not in got["error"]


def test_a_refused_connection_still_says_could_not_connect(loki_url):
    got = _ask(refused())._get(PATH)                    # noqa: SLF001
    assert got["error"] == f"Could not connect to {URL}"
    assert got["not_answering"] is True and not got.get("timed_out")


def test_a_connect_timeout_is_a_timeout_too(loki_url):
    got = _ask(connect_timeout())._get(PATH)            # noqa: SLF001
    assert got["error"].startswith("Loki did not answer within 5 s")


def test_the_cause_is_read_through_each_wrapper():
    assert base.timed_out(read_timeout_retried()) is True
    assert base.timed_out(refused()) is False
    assert base.timed_out(requests.exceptions.ConnectionError("reset by peer")) is False


def test_the_loki_readers_say_it_once(loki_url, monkeypatch):
    from modules.readers.logs_summary import _Loki

    loki = _Loki("")
    loki.client = _ask(read_timeout_retried())
    with pytest.raises(RuntimeError) as got:
        loki.ask(PATH, query="{job=\"x\"}")
    assert str(got.value) == f"Loki did not answer within 5 s ({PATH})"
