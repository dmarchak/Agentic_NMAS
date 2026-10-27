"""A fake HTTP layer for the SDN driver tests (not a test module): a session that answers from a
list or from captured fixtures and keeps every request it was sent, and a clock the test moves.
No socket is opened."""
import json
import os

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "sdn", "ryu")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


class Clock:
    """A monotonic clock that moves only when told (or by `step` per read)."""

    def __init__(self, start=1000.0, step=0.0):
        self.now, self.step = start, step

    def __call__(self):
        self.now += self.step
        return self.now


class Response:
    def __init__(self, status=200, body="", content_type="application/json", headers=None,
                 chunks=None, on_chunk=None):
        self.status_code = status
        self.headers = dict(headers or {})
        if content_type is not None:
            self.headers.setdefault("Content-Type", content_type)
        data = body.encode("utf-8") if isinstance(body, str) else body
        self._chunks = chunks if chunks is not None else ([data] if data else [])
        self._on_chunk = on_chunk
        self.closed = False

    def iter_content(self, chunk_size=1):
        for chunk in self._chunks:
            if self._on_chunk:
                self._on_chunk()
            yield chunk

    def close(self):
        self.closed = True


def captured(entry):
    """A Response from one captured answer (rest_no_switch.json, rest_with_peer.json)."""
    return Response(entry["status"], entry["body"], entry["content_type"])


class Session:
    """Answers each request with the next of *answers* (a Response, an exception to raise, or
    a callable taking the request), and keeps what it was sent."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.sent = []

    def request(self, method, url, **kwargs):
        request = dict(kwargs, method=method, url=url)
        self.sent.append(request)
        if not self.answers:
            raise AssertionError(f"no answer left for {method} {url}")
        answer = self.answers.pop(0)
        if callable(answer) and not isinstance(answer, Response):
            answer = answer(request)
        if isinstance(answer, BaseException):
            raise answer
        return answer


class Routes(Session):
    """Answers by (method, path, body text) from captured entries; the path is the URL's after
    *base*."""

    def __init__(self, entries, base):
        super().__init__()
        self.base = base
        self.table = {(e["method"], e["path"], e["request_body"]): e for e in entries}

    def request(self, method, url, **kwargs):
        self.sent.append(dict(kwargs, method=method, url=url))
        assert url.startswith(self.base), (url, self.base)
        data = kwargs.get("data")
        key = (method, url[len(self.base):], data.decode("utf-8") if data else None)
        if key not in self.table:
            raise AssertionError(f"no captured answer for {key}")
        return captured(self.table[key])
