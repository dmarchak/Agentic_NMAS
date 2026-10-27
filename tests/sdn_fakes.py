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


#: OXM names to the OpenFlow 1.0 names Ryu's ofctl_v1_3.match_to_str answers with.
_TO_RYU = {"eth_src": "dl_src", "eth_dst": "dl_dst", "eth_type": "dl_type", "vlan_vid": "dl_vlan",
           "ipv4_src": "nw_src", "ipv4_dst": "nw_dst", "ip_proto": "nw_proto",
           "tcp_src": "tp_src", "tcp_dst": "tp_dst", "udp_src": "tp_src", "udp_dst": "tp_dst"}


def ryu_action(a):
    """A normalised action as Ryu's ofctl_v1_3.actions_to_str writes it."""
    kind = a["type"]
    if kind == "OUTPUT":
        return f"OUTPUT:{a['port']}"
    if kind == "METER":
        return f"METER:{a['meter_id']}"
    if kind == "GOTO_TABLE":
        return f"GOTO_TABLE:{a['table_id']}"
    if kind == "SET_FIELD":
        return f"SET_FIELD: {{{a['field']}:{a['value']}}}"
    if kind == "WRITE_ACTIONS":
        return {"WRITE_ACTIONS": [ryu_action(x) for x in a.get("actions") or []]}
    return kind


class FakeRyu(Session):
    """A controller holding a flow table and meters per switch, answering Ryu 4.34's ofctl_rest
    in Ryu's own shapes (the reads as tests/fixtures/sdn/lab8/ captured them) and applying each
    write as Open vSwitch did on the lab's run: an add with an existing table, priority and
    match replaces it; modify-strict replaces that flow's actions and keeps its cookie and
    timeouts; delete-strict removes the flow with exactly that table, priority and match whose
    cookie matches under the mask; meters added and deleted by id.

    *ignore* is a set of write paths answered 200 and NOT applied (a switch that refused what
    the controller sent, which Ryu never reports); *fail* maps a write path to the HTTP status
    it answers instead; *count* is called before each read of meters to move their counters."""

    def __init__(self, base, flows=None, meters=None, features=None, ignore=(), fail=None,
                 count=None, dpids=(1,)):
        super().__init__()
        self.base = base
        self.dpids = list(dpids)
        self.table = {d: [dict(f) for f in (flows or {}).get(d, [])] for d in self.dpids}
        self.meter = {d: {m["meter_id"]: dict(m) for m in (meters or {}).get(d, [])}
                      for d in self.dpids}
        self.features = features if features is not None else {
            "max_meter": 200000, "band_types": ["DROP"],
            "capabilities": ["KBPS", "PKTPS", "BURST", "STATS"], "max_bands": 1, "max_color": 0}
        self.ignore, self.fail, self.count = set(ignore), dict(fail or {}), count
        self.writes = []

    @staticmethod
    def _ryu_flow(f):
        proto = f["match"].get("ip_proto")
        match = {}
        for k, v in f["match"].items():
            name = _TO_RYU.get(k, k)
            if k in ("tcp_src", "tcp_dst", "udp_src", "udp_dst") and proto not in (6, 17):
                name = k
            match[name] = v
        return {"priority": f["priority"], "cookie": f["cookie"],
                "idle_timeout": f.get("idle_timeout", 0), "hard_timeout": f.get("hard_timeout", 0),
                "byte_count": f.get("byte_count", 0), "duration_sec": f.get("duration_sec", 0),
                "duration_nsec": 0, "packet_count": f.get("packet_count", 0), "length": 96,
                "flags": 0, "actions": [ryu_action(a) for a in f.get("actions") or []],
                "match": match, "table_id": f.get("table_id", 0)}

    @staticmethod
    def _key(f):
        from modules.sdn.flow_intent import normal_match
        return (f.get("table_id", 0), f.get("priority", 0),
                json.dumps(normal_match(f.get("match")), sort_keys=True))

    def _answer(self, method, path, body):
        if method == "GET":
            parts = path.strip("/").split("/")
            if path == "/stats/switches":
                return Response(200, json.dumps(self.dpids))
            dpid = int(parts[-1])
            if dpid not in self.dpids:
                return Response(404, "", "text/html")
            if parts[1] == "flow":
                return Response(200, json.dumps({str(dpid): [self._ryu_flow(f)
                                                             for f in self.table[dpid]]}))
            if parts[1] == "meterfeatures":
                return Response(200, json.dumps({str(dpid): [self.features]}))
            if self.count:
                self.count(self)
            if parts[1] == "meterconfig":
                return Response(200, json.dumps({str(dpid): [
                    {"flags": m["flags"], "bands": m["bands"], "meter_id": m["meter_id"]}
                    for m in self.meter[dpid].values()]}))
            if parts[1] == "meter":
                return Response(200, json.dumps({str(dpid): [
                    {"len": 56, "flow_count": 0, "packet_in_count": m.get("packet_in", 0),
                     "byte_in_count": 0, "duration_sec": 1, "duration_nsec": 0,
                     "band_stats": [{"packet_band_count": m.get("dropped", 0),
                                     "byte_band_count": 0}], "meter_id": m["meter_id"]}
                    for m in self.meter[dpid].values()]}))
            raise AssertionError(f"the fake has no read {path}")
        self.writes.append((path, body))
        if path in self.fail:
            return Response(self.fail[path], "", "text/html")
        if path in self.ignore:
            return Response(200, "", "text/html")
        req = json.loads(body)
        dpid = req.pop("dpid")
        table = self.table[dpid]
        if path == "/stats/flowentry/add":
            table[:] = [f for f in table if self._key(f) != self._key(req)]
            table.append(dict(req, packet_count=0, byte_count=0, duration_sec=0))
        elif path == "/stats/flowentry/modify_strict":
            for f in table:
                if self._key(f) == self._key(req):
                    f["actions"] = req.get("actions") or []
        elif path == "/stats/flowentry/delete_strict":
            mask = req.get("cookie_mask", 0)
            table[:] = [f for f in table if not (
                self._key(f) == self._key(req)
                and (f["cookie"] & mask) == (req.get("cookie", 0) & mask))]
        elif path == "/stats/meterentry/add":
            self.meter[dpid][req["meter_id"]] = dict(req)
        elif path == "/stats/meterentry/delete":
            self.meter[dpid].pop(req["meter_id"], None)
        else:
            raise AssertionError(f"the fake has no write {path}")
        return Response(200, "", "text/html")

    def request(self, method, url, **kwargs):
        self.sent.append(dict(kwargs, method=method, url=url))
        assert url.startswith(self.base), (url, self.base)
        data = kwargs.get("data")
        return self._answer(method, url[len(self.base):], data.decode("utf-8") if data else None)


class Replay(Session):
    """Answers each GET from captured entries for its path in the order they were captured
    (a second port read answers the second sample), the last one repeating."""

    def __init__(self, entries, base):
        super().__init__()
        self.base = base
        self.by_path = {}
        for e in entries:
            self.by_path.setdefault(e["path"], []).append(e)

    def request(self, method, url, **kwargs):
        self.sent.append(dict(kwargs, method=method, url=url))
        assert method == "GET" and url.startswith(self.base), (method, url)
        queue = self.by_path.get(url[len(self.base):])
        if not queue:
            raise AssertionError(f"no captured answer for {url}")
        return captured(queue.pop(0) if len(queue) > 1 else queue[0])


def lab8(name):
    """A Lab 8 capture (tests/fixtures/sdn/lab8/, its README says how each was made)."""
    path = os.path.join(os.path.dirname(FIXTURES), "lab8", name)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


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
