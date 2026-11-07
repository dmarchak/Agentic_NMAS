"""A recorded Ryu (not a test module): Ryu 4.34's REST answers from the masked capture
`tests/fixtures/lab9_captures/2026-11-06/ryu-rest.txt` (its README says how it was masked),
answering exactly the paths that capture recorded and nothing else. Every value comes from that
file when it is read; none is written here.

The recorded paths (Ryu's `ofctl_rest` and `rest_topology`):
- `GET /stats/switches`: the connected datapath ids, as integers;
- `GET /v1.0/topology/links`: the links, one entry per direction;
- `GET /stats/desc/<dpid>` and `GET /stats/portdesc/<dpid>`: per switch, the dpid in decimal as
  Ryu takes it and answers it (`{"<dpid>": ...}`).

`RecordedRyu(HARNESS)` answers the container harness's recording instead (real Ryu 4.34 and real
Open vSwitch, `scripts/nmas-harness record`), which adds `/stats/tablefeatures/<dpid>`.

**A path not recorded raises `UnrecordedPath`, naming the method and the path** (and a
non-GET raises the same way: the recording holds only reads). `get(path)` answers the parsed
JSON (a fresh copy each time); `session()` is an HTTP session for Mercury's real Ryu driver
(`modules/sdn/drivers/ryu.RyuDriver`, given as `session=`), so a job's controller reads in a
unit test come through the driver that serves them for real; `driver()` builds that driver.
No socket is opened.
"""

import copy
import json
import os

CAPTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "lab9_captures", "2026-11-06", "ryu-rest.txt")
#: The base URL the driver is given: a documentation name that resolves nowhere.
BASE_URL = "http://controller.example.invalid:8080"
SECTIONS = {"switches": "/stats/switches", "links": "/v1.0/topology/links",
            "desc": "/stats/desc/{}", "portdesc": "/stats/portdesc/{}"}


class UnrecordedPath(LookupError):
    """A request the recording holds no answer for, naming its method and path."""


def parse_capture(text: str) -> dict:
    """`{path: answer}` from a capture of `### <section>[ <dpid>]` headers, each followed by
    one line of JSON. A header naming no known section, or a body that is not JSON, raises
    ValueError naming its line."""
    answers, header, header_line = {}, None, 0
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("### "):
            header, header_line = line[4:].split(), number
            continue
        if not line.strip():
            continue
        if not header or header[0] not in SECTIONS or len(header) > 2:
            raise ValueError(f"line {header_line or number}: {' '.join(header or [])!r} is not "
                             f"one of the recorded sections {sorted(SECTIONS)}")
        path = SECTIONS[header[0]]
        if "{}" in path:
            if len(header) != 2 or not header[1].isdigit():
                raise ValueError(f"line {header_line}: {header[0]} names its dpid in decimal")
            path = path.format(header[1])
        try:
            answers[path] = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"line {number}: the answer to {path} is not JSON ({exc})") from None
        header = None
    return answers


class _Response:
    """What the driver reads of a `requests` response."""

    def __init__(self, body: bytes):
        self.status_code = 200
        self.headers = {"Content-Type": "application/json; charset=UTF-8"}
        self._body = body

    def iter_content(self, chunk_size=1):
        yield self._body

    def close(self):
        pass


class _Session:
    def __init__(self, recorded: "RecordedRyu"):
        self.recorded = recorded

    def request(self, method, url, **_kwargs):
        if not url.startswith(BASE_URL):
            raise UnrecordedPath(f"{method} {url}: not this recording's controller ({BASE_URL})")
        answer = self.recorded.answer(method, url[len(BASE_URL):])
        return _Response(json.dumps(answer).encode("utf-8"))


#: The container harness's recording (scripts/nmas-harness record): real Ryu 4.34 on Python 3.5
#: reading real Open vSwitch 3.3 on its userspace datapath (tests/fixtures/sdn/harness/README.md).
HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harness",
                       "ovs-userspace-ryu-4.34-py3.5.json")


def parse_harness(text: str) -> dict:
    """`{path: answer}` from a harness recording (`{path: {"status", "body"}}`, plus `_edit`);
    an answer that was not a 200 raises ValueError naming its path, since this fake answers
    only what the controller answered with a body."""
    out = {}
    for path, answer in json.loads(text).items():
        if path.startswith("_"):
            continue
        if answer.get("status") != 200:
            raise ValueError(f"{path} was answered {answer.get('status')}, not 200")
        out[path] = json.loads(answer["body"])
    return out


class RecordedRyu:
    """Ryu's recorded answers; `sent` keeps every `(method, path)` asked, in order."""

    def __init__(self, capture: str = CAPTURE):
        with open(capture, encoding="utf-8") as fh:
            text = fh.read()
        self._answers = parse_harness(text) if capture.endswith(".json") else parse_capture(text)
        self.sent = []

    @property
    def paths(self) -> list:
        return sorted(self._answers)

    def answer(self, method: str, path: str):
        self.sent.append((method, path))
        if method != "GET" or path not in self._answers:
            raise UnrecordedPath(f"{method} {path} was not recorded; the recording answers GET "
                                 f"on {', '.join(self.paths)}")
        return copy.deepcopy(self._answers[path])

    def get(self, path: str):
        return self.answer("GET", path)

    def dpids(self) -> list:
        """The recorded switches' datapath ids, as `/stats/switches` answered them."""
        return list(self.get("/stats/switches"))

    def session(self) -> _Session:
        return _Session(self)

    def driver(self):
        """Mercury's Ryu driver reading this recording."""
        from modules.sdn.drivers.base import Connection
        from modules.sdn.drivers.ryu import RyuDriver

        return RyuDriver(Connection(url=BASE_URL), session=self.session())
