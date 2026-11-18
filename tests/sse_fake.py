"""A provider answer as the server-sent events the Anthropic adapter reads (7b0bb884, the
operator's 2026-11-16 decision: every send is streamed, `anthropic_adapter._read_stream`).

The fakes in the AI tests were written for a whole-answer JSON body; the adapter now posts with
``stream=True`` and reads the body's events. `events(body)` turns a whole-answer body
(``content``, ``stop_reason``, ``usage``, ``model``, ``id``) into the event sequence a real
stream sends for it (message_start with the input usage, one start/delta/stop per content block,
message_delta with the stop reason and the output usage, message_stop), and `lines(body)` into
the ``event:``/``data:`` lines `iter_lines` yields. `StreamingResponse` is a response whose
200 body streams and whose other statuses answer ``json()`` as before. Fixtures stay real
captures: the body given is the capture; only its transport is streamed."""

import json

#: The usage keys a stream reports in message_start (input and cache) and in message_delta
#: (output), as the API sends them.
START_USAGE = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def events(body: dict) -> list:
    """The stream's events for whole-answer *body*, in order."""
    body = dict(body or {})
    usage = dict(body.get("usage") or {})
    start = {k: v for k, v in body.items() if k not in ("content", "usage", "stop_reason",
                                                         "stop_sequence")}
    start.update(content=[], stop_reason=None,
                 usage={**{k: usage[k] for k in START_USAGE if k in usage}, "output_tokens": 0})
    out = [{"type": "message_start", "message": start}]
    for i, block in enumerate(body.get("content") or []):
        block = dict(block)
        kind = block.get("type") or "text"
        if kind == "text":
            out.append({"type": "content_block_start", "index": i,
                        "content_block": {"type": "text", "text": ""}})
            out.append({"type": "content_block_delta", "index": i,
                        "delta": {"type": "text_delta", "text": block.get("text") or ""}})
        elif kind == "thinking":
            out.append({"type": "content_block_start", "index": i,
                        "content_block": {"type": "thinking", "thinking": ""}})
            out.append({"type": "content_block_delta", "index": i,
                        "delta": {"type": "thinking_delta",
                                  "thinking": block.get("thinking") or ""}})
            if block.get("signature"):
                out.append({"type": "content_block_delta", "index": i,
                            "delta": {"type": "signature_delta",
                                      "signature": block["signature"]}})
        else:
            out.append({"type": "content_block_start", "index": i, "content_block": block})
        out.append({"type": "content_block_stop", "index": i})
    out.append({"type": "message_delta",
                "delta": {"stop_reason": body.get("stop_reason"),
                          "stop_sequence": body.get("stop_sequence")},
                "usage": {"output_tokens": usage.get("output_tokens", 0)}})
    out.append({"type": "message_stop"})
    return out


def lines(body: dict) -> list:
    """`events(body)` as the byte lines a streamed response's `iter_lines` yields."""
    out = []
    for ev in events(body):
        out += [f"event: {ev['type']}".encode(), f"data: {json.dumps(ev)}".encode(), b""]
    return out


class StreamingResponse:
    """A provider response: a 200 streams its *body* as events; another status answers
    ``json()`` with its body (an error body) as the API does before any stream."""

    def __init__(self, status, body=None, headers=None, text="", raw_lines=None):
        self.status_code, self._body, self.text = status, body, text
        self.headers = dict(headers or {})
        self._lines = raw_lines
        self.closed = False

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def iter_lines(self, chunk_size=None):
        if self._lines is not None:
            yield from self._lines
        elif self._body is None:
            # A 200 that is no stream (an HTML page from a proxy): its text, line by line.
            yield from (line.encode() for line in (self.text or "").splitlines())
        else:
            yield from lines(self._body)

    def close(self):
        self.closed = True
