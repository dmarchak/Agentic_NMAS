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

**One parser of the recordings** (C2652): the app SDK's `mercury_app.testing` holds it
(`parse_capture`, `parse_harness`, `RecordedRyu`, `UnrecordedPath`), written for a 3.5
controller's Python so an app's tests read the same answers in the container harness; this
module extends it with what a job's tests need on Mercury's Python: `session()` and `driver()`.

**A path not recorded raises `UnrecordedPath`, naming the method and the path** (and a
non-GET raises the same way: the recording holds only reads). `get(path)` answers the parsed
JSON (a fresh copy each time); `session()` is an HTTP session for Mercury's real Ryu driver
(`modules/sdn/drivers/ryu.RyuDriver`, given as `session=`), so a job's controller reads in a
unit test come through the driver that serves them for real; `driver()` builds that driver.
No socket is opened.
"""

import json
import os

from modules.apps.sdk.mercury_app import testing as _sdk
from modules.apps.sdk.mercury_app.testing import (SECTIONS, UnrecordedPath, parse_capture,
                                                  parse_harness)

__all__ = ["BASE_URL", "CAPTURE", "HARNESS", "RecordedRyu", "SECTIONS", "UnrecordedPath",
           "parse_capture", "parse_harness"]

CAPTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "lab9_captures", "2026-11-06", "ryu-rest.txt")
#: The base URL the driver is given: a documentation name that resolves nowhere.
BASE_URL = "http://controller.example.invalid:8080"
#: The container harness's recording (scripts/nmas-harness record): real Ryu 4.34 on Python 3.5
#: reading real Open vSwitch 3.3 on its userspace datapath (tests/fixtures/sdn/harness/README.md).
HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harness",
                       "ovs-userspace-ryu-4.34-py3.5.json")


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


class RecordedRyu(_sdk.RecordedRyu):
    """Ryu's recorded answers (the SDK's `RecordedRyu`), and Mercury's driver reading them."""

    def __init__(self, capture: str = CAPTURE):
        super().__init__(capture)

    def session(self) -> _Session:
        return _Session(self)

    def driver(self):
        """Mercury's Ryu driver reading this recording."""
        from modules.sdn.drivers.base import Connection
        from modules.sdn.drivers.ryu import RyuDriver

        return RyuDriver(Connection(url=BASE_URL), session=self.session())
