"""Register C51: a GET must not create the list it names.

`GET /onboard/pending?list_name=<name>` resolved its repository through
`config.get_list_data_dir()`, which calls `os.makedirs()`, so asking about a
list that does not exist (a typo included) brought `lists/<name>/` into
existence. C33's sweep (`test_reads_write_nothing.py`) could not see it: its
population was the ARGUMENT-FREE GETs, and with no argument these routes
read the active list, whose directory already exists. **A population chosen
by what is easy to call, not by the property.** The property is "a read
creates nothing", and a list name is an argument.

So this sweep calls EVERY GET, with an unknown list name in every place a
list name can arrive: the query parameters the routes read (`list_name`,
`list`) and any path converter. Other converters get a placeholder. The
check is narrow on purpose: the unknown list's directory must not exist
afterwards. Broader writes are C33's.

Built in Stage 7.0, whose harness it belongs to (the confirmed gate list).
"""

import os
import shutil
import socket

import pytest

UNKNOWN = "zz-c51-unknown-list"

#: GETs that still create the list they are asked about, each with the
#: reason it is tolerated. It must not grow, and a fixed route must leave.
KNOWN_CREATORS = {}


def _fill(rule):
    """A concrete URL for *rule*: every converter filled, the unknown list
    name in every argument whose name says it is a list."""
    url = rule.rule
    for arg in rule.arguments:
        conv = rule._converters[arg].__class__.__name__.lower()   # noqa: SLF001
        if "list" in arg or arg in ("slug",):
            value = UNKNOWN
        elif "integer" in conv:
            value = "1"
        else:
            value = "zz"
        url = url.replace(f"<{arg}>", value)
        for prefix in ("string", "path", "int", "float", "uuid", "any"):
            url = url.replace(f"<{prefix}:{arg}>", value)
    return url + f"?list_name={UNKNOWN}&list={UNKNOWN}"


def _remove_store(store):
    """Remove the worker's store before restoring it, and if something wrote into it
    DURING the removal, fail naming what was left and every live thread (C163's
    measurement). It removed with `ignore_errors=True`, so the race surfaced only later, as
    `FileExistsError` on the restore, here and in every later fixture in the worker
    (2026-10-05: twice in an hour, 47 and 3 errors), with the writer unnamed."""
    shutil.rmtree(store, ignore_errors=True)
    if not os.path.exists(store):
        return
    left = sorted(os.path.relpath(os.path.join(d, f), store)
                  for d, _sub, files in os.walk(store) for f in files)
    raise AssertionError(
        f"C163: the store could not be removed; something wrote into it during the removal. "
        f"Left ({len(left)}): {left[:40]}. Live threads: {_threads()}")


def _threads():
    """Every live thread but the main one: its name, class and target (C163)."""
    import threading
    return sorted(f"{t.name} ({type(t).__name__}, target "
                  f"{getattr(getattr(t, '_target', None), '__qualname__', '?')})"
                  for t in threading.enumerate() if t is not threading.main_thread())


@pytest.fixture(scope="module")
def creators():
    """{rule: url} for every GET that left the unknown list's directory.

    The store is copied before and restored after, as C33's sweep does: the
    GETs write other things (C33's KNOWN_WRITERS), and a module fixture must
    not leave them for the tests after it."""
    import app as A
    from modules import config

    original_connect = socket.socket.connect

    def _no_network(*a, **k):
        raise OSError("tests do not touch a network")

    store = config.DATA_DIR
    original = os.path.join(os.path.dirname(store), os.path.basename(store) + ".c51")
    shutil.copytree(store, original)
    socket.socket.connect = _no_network
    client = A.app.test_client()
    client.get("/")
    target = os.path.join(config.LISTS_DIR, config.list_slug(UNKNOWN))
    found, swept = {}, []
    try:
        for rule in sorted(A.app.url_map.iter_rules(), key=lambda r: r.rule):
            if "GET" not in (rule.methods or ()) or rule.endpoint == "static":
                continue
            url = _fill(rule)
            swept.append(rule.rule)
            shutil.rmtree(target, ignore_errors=True)
            try:
                client.get(url)
            except Exception:                  # noqa: BLE001
                pass                           # a crash is not this test's finding
            if os.path.exists(target):
                found[rule.rule] = url
    finally:
        socket.socket.connect = original_connect
        _remove_store(store)
        try:
            shutil.copytree(original, store)
        except (shutil.Error, OSError) as exc:
            # The race's other half (C163, 2026-10-05): the removal succeeded, and something
            # created `lists/default` in the store DURING the restore. Name who was alive.
            raise AssertionError(f"C163: the store's restore collided with a writer ({exc}). "
                                 f"Live threads: {_threads()}") from exc
        shutil.rmtree(original, ignore_errors=True)
    found["_swept"] = swept
    return found


def test_the_sweep_covers_the_gets_with_arguments(creators):
    """Floor: C33 swept the argument-free GETs; this one exists for the rest.
    A sweep that reached none of them would pass by construction."""
    import app as A

    with_args = [r for r in A.app.url_map.iter_rules()
                 if "GET" in (r.methods or ()) and r.arguments and r.endpoint != "static"]
    assert len(with_args) >= 20, len(with_args)
    assert len(creators["_swept"]) >= 100, len(creators["_swept"])


def test_no_get_creates_the_list_it_names(creators):
    new = sorted(set(creators) - {"_swept"} - set(KNOWN_CREATORS))
    assert new == [], (
        "these GETs create the list they were asked about "
        f"(lists/{UNKNOWN}/ exists afterwards): {new}")


def test_no_fixed_creator_stays_listed(creators):
    ghosts = sorted(set(KNOWN_CREATORS) - set(creators))
    assert ghosts == [], f"these no longer create a list: remove them: {ghosts}"


# ── the refusal itself ──────────────────────────────────────────────────────

@pytest.fixture
def client():
    import app as A

    c = A.app.test_client()
    c.get("/")
    return c


class TestTheRefusal:
    def test_an_unknown_list_is_refused_by_name(self, client):
        """Not an empty listing: "none pending" for a mistyped list is a claim
        about a list nobody has, in the words of one about a list they do."""
        r = client.get(f"/onboard/pending?list_name={UNKNOWN}")
        body = r.get_json()
        assert r.status_code == 404
        assert body["ok"] is False and body["unknown_list"] == UNKNOWN
        assert UNKNOWN in body["error"] and "not the same as an empty list" in body["error"]

    def test_the_path_converter_form_is_refused_too(self, client):
        r = client.get(f"/inventory/source/{UNKNOWN}")
        assert r.status_code == 404 and r.get_json()["unknown_list"] == UNKNOWN

    def test_the_list_parameter_form_is_refused_too(self, client):
        r = client.get(f"/remote/status?list={UNKNOWN}")
        assert r.status_code == 404 and r.get_json()["unknown_list"] == UNKNOWN

    def test_a_real_list_still_reads(self, client):
        """The control that the refusal is not a closed gate: the default
        list, by display name AND by slug, answers normally."""
        for name in ("Default", "default"):
            r = client.get(f"/onboard/pending?list_name={name}")
            assert r.status_code == 200, (name, r.get_json())

    def test_no_argument_reads_the_active_list(self, client):
        assert client.get("/onboard/pending").status_code == 200

    def test_a_write_is_not_this_hooks_business(self):
        """A POST naming a list is judged by its own route (onboarding refuses
        through `_target_list()`; creating a list SHOULD make one)."""
        from routes import list_param

        src = open(list_param.__file__, encoding="utf-8").read()
        assert 'request.method not in ("GET", "HEAD")' in src
