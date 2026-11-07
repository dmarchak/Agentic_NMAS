"""What an app's tests import from the app SDK (C2644, C2652; the operator's decision 8 of
2026-11-07, option (a)): the SDK's fixtures, the recorded Ryu, and `covers` and `refused`,
written for the oldest controller Python the app check knows, 3.5 (no f-strings, no variable
annotations, no `:=`, no positional-only parameters, no asynchronous generators), on the
standard library alone. An app's tests run in the container harness on its network's controller
Python, whose image holds neither pydantic nor Mercury, so this never imports `modules.jobs`:
where `modules.jobs.testing` and `modules.jobs.authoring` lean on the job contract's pydantic
models, this checks the same contract by hand, in the same words (tests/
test_app_sdk_testing.py holds the two to the same answers on the same inputs).

- **`@covers("<example name>", ...)`** marks a test as covering spec.yml's examples (a no-op
  at run time; the gate reads the names from the source, so each is a string literal);
- **`with refused(match=None, kind=ContractError):`** passes when the block raises *kind*, its
  message matching *match* when one is given, and fails naming what it expected and what
  happened (pytest's own `raises` is the other block an app's tests may use);
- **the fixtures a test asks for by name** (`FIXTURES`, given by `fixture_for(name, modules)`,
  which the app's fixed `conftest.py` calls under pytest):
  - `ryu`: the recorded Ryu (`RecordedRyu`), Ryu 4.34's REST answers from the masked capture
    `tests/fixtures/lab9_captures/2026-11-06/ryu-rest.txt`, or the container harness's
    recording (`RecordedRyu(HARNESS)`); a path not recorded raises `UnrecordedPath`, naming it;
  - `netbox(job=None, objects=None)`: a `FakeNetBox` over *objects* (`{object_type: [object,
    ...]}`). Without *objects* it raises, naming the masked export it will default to
    (`tests/fixtures/lab9_netbox/`, P1b, not in the repository yet): an empty NetBox would
    pass a test that reads nothing;
  - `ctx`: a job's plan-mode context, which an app has none of: an app's folder holds no Job
    class, so it is refused in `modules.jobs.testing`'s own words. This is the one fixture
    whose answer differs by design: given a job, `modules.jobs.testing` builds the context on
    Mercury's Python, and this refuses, naming where a job's context is.

`RecordedRyu` here is the one parser of the recordings: `tests/fixtures/sdn/ryu_recorded.py`
extends it with Mercury's Ryu driver for a job's tests.

Nothing here parses an address (the recording's datapath ids are integers, its paths text), so
there is no IPv4 or IPv6 case to give.
"""

import copy
import json
import os
import re

__all__ = ["CAPTURE", "ContractError", "FakeNetBox", "FIXTURES", "HARNESS", "Raised",
           "RecordedRyu", "UnrecordedPath", "covers", "ctx", "fixture", "fixture_for",
           "job_class_in", "netbox", "parse_capture", "parse_harness", "refused", "ryu"]

#: The repository this file sits in: modules/apps/sdk/mercury_app/ is four folders down.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))))
#: The masked Ryu capture `ryu()` reads, and the container harness's recording.
CAPTURE = os.path.join(_ROOT, "tests", "fixtures", "lab9_captures", "2026-11-06",
                       "ryu-rest.txt")
HARNESS = os.path.join(_ROOT, "tests", "fixtures", "sdn", "harness",
                       "ovs-userspace-ryu-4.34-py3.5.json")
#: The masked NetBox export `netbox()` will read (P1b), relative to the repository.
NETBOX_EXPORT = os.path.join("tests", "fixtures", "lab9_netbox")
#: The recorded paths (Ryu's `ofctl_rest` and `rest_topology`).
SECTIONS = {"switches": "/stats/switches", "links": "/v1.0/topology/links",
            "desc": "/stats/desc/{}", "portdesc": "/stats/portdesc/{}"}
#: How much of a refused value a refusal quotes (`modules.jobs.base.QUOTE_MAX`).
QUOTE_MAX = 80
#: Where the job contract's classes are defined, read by name: never imported here.
_JOB_BASE = "modules.jobs.base"


class ContractError(ValueError):
    """A contract refused: `what` was refused, and `problems` holds one line per field, each
    naming the field, the value and the rule (`modules.jobs.base.ContractError`'s shape)."""

    def __init__(self, what, problems):
        self.what = what
        self.problems = list(problems)
        super().__init__("%s refused: %s" % (what, "; ".join(self.problems)))


def quoted(value):
    """*value* as a refusal quotes it: its repr, cut to `QUOTE_MAX` characters."""
    text = repr(value)
    return text if len(text) <= QUOTE_MAX else text[:QUOTE_MAX - 3] + "..."


# ── covers and refused ───────────────────────────────────────────────────────────────────────

def covers(*examples):
    """Mark a test as covering the spec card's examples named (a no-op at run time)."""
    bad = [e for e in examples if not isinstance(e, str) or not e.strip()]
    if not examples or bad:
        raise TypeError("covers names one or more examples, each a non-empty string; given "
                        "%r" % (examples,))

    def mark(test):
        return test
    return mark


class Raised:
    """What an expected refusal caught: `type` and `value`, as pytest's ExceptionInfo offers
    them, and `match(regex)`."""

    def __init__(self):
        self.type = None
        self.value = None

    def match(self, regex):
        if self.value is None or not re.search(regex, str(self.value)):
            raise AssertionError("the refusal's message %r does not match %r"
                                 % (str(self.value), regex))
        return True


class _Expect:
    """A block that must raise *kind* (a class or a tuple of classes)."""

    def __init__(self, kind, match, words):
        kinds = kind if isinstance(kind, tuple) else (kind,)
        if not kinds or not all(isinstance(k, type) and issubclass(k, BaseException)
                                for k in kinds):
            raise TypeError("%s names exception classes, not %r" % (words, kind))
        self.kinds, self.match, self.words = kinds, match, words
        self.raised = Raised()

    def _names(self):
        return " or ".join(k.__name__ for k in self.kinds)

    def __enter__(self):
        return self.raised

    def __exit__(self, kind, value, _tb):
        if kind is None:
            raise AssertionError("DID NOT RAISE %s: %s expected the block to raise it, and it "
                                 "raised nothing" % (self._names(), self.words))
        if not issubclass(kind, self.kinds):
            return False                    # another exception: the test fails with it
        if self.match is not None and not re.search(self.match, str(value)):
            raise AssertionError("%s caught %s %r, which does not match %r"
                                 % (self.words, kind.__name__, str(value), self.match))
        self.raised.type, self.raised.value = kind, value
        return True


def refused(match=None, kind=ContractError):
    """A block that must be refused (see the module's docstring)."""
    return _Expect(kind, match, "refused()")


# ── the recorded Ryu ─────────────────────────────────────────────────────────────────────────

class UnrecordedPath(LookupError):
    """A request the recording holds no answer for, naming its method and path."""


def parse_capture(text):
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
            raise ValueError("line %d: %r is not one of the recorded sections %s"
                             % (header_line or number, " ".join(header or []),
                                sorted(SECTIONS)))
        path = SECTIONS[header[0]]
        if "{}" in path:
            if len(header) != 2 or not header[1].isdigit():
                raise ValueError("line %d: %s names its dpid in decimal"
                                 % (header_line, header[0]))
            path = path.format(header[1])
        try:
            answers[path] = json.loads(line)
        except ValueError as exc:
            raise ValueError("line %d: the answer to %s is not JSON (%s)"
                             % (number, path, exc)) from None
        header = None
    return answers


def parse_harness(text):
    """`{path: answer}` from a harness recording (`{path: {"status", "body"}}`, plus `_edit`);
    an answer that was not a 200 raises ValueError naming its path, since this fake answers
    only what the controller answered with a body."""
    out = {}
    for path, answer in json.loads(text).items():
        if path.startswith("_"):
            continue
        if answer.get("status") != 200:
            raise ValueError("%s was answered %s, not 200" % (path, answer.get("status")))
        out[path] = json.loads(answer["body"])
    return out


class RecordedRyu:
    """Ryu's recorded answers; `sent` keeps every `(method, path)` asked, in order."""

    def __init__(self, capture=CAPTURE):
        with open(capture, encoding="utf-8") as fh:
            text = fh.read()
        self._answers = parse_harness(text) if capture.endswith(".json") else parse_capture(text)
        self.sent = []

    @property
    def paths(self):
        return sorted(self._answers)

    def answer(self, method, path):
        self.sent.append((method, path))
        if method != "GET" or path not in self._answers:
            raise UnrecordedPath("%s %s was not recorded; the recording answers GET on %s"
                                 % (method, path, ", ".join(self.paths)))
        return copy.deepcopy(self._answers[path])

    def get(self, path):
        return self.answer("GET", path)

    def dpids(self):
        """The recorded switches' datapath ids, as `/stats/switches` answered them."""
        return list(self.get("/stats/switches"))


# ── NetBox ───────────────────────────────────────────────────────────────────────────────────

class FakeNetBox:
    """NetBox's objects by type, read within a job's scope when *meta* is given (an app's is
    never scoped: its tests give none)."""

    def __init__(self, objects, meta=None):
        self._objects = copy.deepcopy(objects or {})
        self._meta = meta

    def _check(self, call, object_type):
        if self._meta is not None:
            self._meta.scope.check(call, object_type)

    def get(self, object_type, **filters):
        self._check("netbox.get(%r)" % (object_type,), object_type)
        return [copy.deepcopy(o) for o in self._objects.get(object_type, [])
                if all(o.get(k) == v for k, v in filters.items())]

    def one(self, object_type, object_id):
        self._check("netbox.one(%r, %r)" % (object_type, object_id), object_type)
        for o in self._objects.get(object_type, []):
            if o.get("id") == object_id:
                return copy.deepcopy(o)
        raise LookupError("the fixture holds no %s with id %r" % (object_type, object_id))


# ── the fixtures a test asks for by name ─────────────────────────────────────────────────────

def _is_base(cls, name):
    return getattr(cls, "__module__", None) == _JOB_BASE and getattr(cls, "__name__", None) \
        == name


def _is_job_class(value):
    """Whether *value* is a subclass of the job contract's `Job` (and not `Job` itself), read
    from its classes' names, since the contract is never imported here."""
    return isinstance(value, type) and not _is_base(value, "Job") \
        and any(_is_base(c, "Job") for c in value.__mro__)


def _meta(job, helper):
    if any(_is_base(c, "JobMeta") for c in type(job).__mro__):
        return job
    if _is_job_class(job):
        return job.meta
    raise ContractError("the fixture %s" % helper, ["job is the folder's Job class or its "
                                                    "JobMeta, not %s" % quoted(job)])


def job_class_in(modules):
    """The one `Job` subclass defined in *modules*; refused, naming what was found, when there
    is not exactly one (an app's folder holds none)."""
    names = set(getattr(m, "__name__", None) for m in modules)
    found = []
    for m in modules:
        for value in vars(m).values():
            if _is_job_class(value) and value.__module__ in names and value not in found:
                found.append(value)
    if len(found) != 1:
        raise ContractError("the folder's job", [
            "the fixtures need exactly one Job class in the folder's modules (%s); found %d"
            % (", ".join(sorted(n for n in names if n)), len(found))
            + (": %s" % ", ".join(c.__name__ for c in found) if found else "")])
    return found[0]


def ryu(job=None):
    """The recorded Ryu (`RecordedRyu`); *job* is not needed."""
    return RecordedRyu()


def ctx(job, **fixtures):
    """A job's plan-mode context, which an app's tests have none of: refused, naming where a
    job's is (see the module's docstring)."""
    _meta(job, "ctx")
    raise ContractError("the fixture ctx", [
        "a job's plan-mode context is modules.jobs.testing's, on Mercury's Python; an app's "
        "tests take ryu and netbox"])


def netbox(job=None, objects=None):
    """A `FakeNetBox` over *objects* (`{object_type: [object, ...]}`), within *job*'s scope
    when *job* is given (see the module's docstring for the export it will default to)."""
    if objects is None:
        raise LookupError("the masked NetBox export (%s/, P1b) is not in this repository yet: "
                          "give the objects, netbox(job, objects={...})" % NETBOX_EXPORT)
    return FakeNetBox(objects, _meta(job, "netbox") if job is not None else None)


#: A test parameter's name -> the helper giving it, each called with the folder's job class.
FIXTURES = {"ctx": ctx, "ryu": ryu, "netbox": netbox}


def fixture(name, job):
    """What the test parameter *name* is given, for the folder's *job* class (None for an
    app). An unknown name is refused, naming the fixtures there are."""
    if name not in FIXTURES:
        raise LookupError("no fixture named %r: a job's test may ask for %s"
                          % (name, ", ".join(sorted(FIXTURES))))
    return FIXTURES[name](job)


def fixture_for(name, modules):
    """`fixture(name, job)` for the job class in *modules* (the folder's own modules, as pytest
    imported them): a fixture that needs no job (`ryu`) is given without one; one that needs
    it raises `job_class_in`'s refusal, naming what was found."""
    try:
        job, missing = job_class_in(modules), None
    except ContractError as exc:
        job, missing = None, exc
    try:
        return fixture(name, job)
    except ContractError:
        if missing is not None:
            raise missing from None
        raise
