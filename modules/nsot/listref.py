"""nsot/listref.py — a device list, resolved once and carried.

**Three defects in this project had one shape**: a function was told which
list to work on, and then asked a global which list was current.

1. The pipeline called ``get_current_list_name()`` at three points *after* the
   push, including the golden commit. That function reads a file on disk, so
   switching lists during a 45-90s convergence window committed one network's
   captures into another's repository.
2. ``plan_restore()`` took ``list_name``, used it for the repo, and read its
   devices from ``get_current_device_list()``.
3. ``check_right_repository()`` compared ``slug == list_name`` — ``'default'``
   against ``'Default'`` — so every adopted list failed its own uniqueness
   check, reporting itself as the other list that already owns the repository.

The first two are "asked again later". The third is subtler and is why this
is a **type** rather than a convention: a list has *two* names. The operator
sees ``Default``; the directory is ``default``. Passing "the list name" as a
string leaves every caller to decide which one it meant, and a comparison
between the two is always false.

A ``ListRef`` carries both, plus the paths derived from them, so there is
nothing left to re-derive and nothing to confuse. Passing one through a
function signature makes "which list" a parameter rather than ambient state.

**Resolution happens in one place.** Two derivations existed:
``get_current_device_list()`` reads a registry (``lists`` in the device-lists
config) and falls back to ``list_slug(name)``; ``get_list_data_dir()`` calls
``list_slug(name)`` directly, ignoring the registry. They agree today because
the migration writes ``lists[name] = list_slug(name)`` — but "they agree
today" is how the other three started.
"""

import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)


class UnknownList(Exception):
    """No list answers to this name or slug."""


@dataclass(frozen=True)
class ListRef:
    """A device list, resolved. Frozen: a carried reference cannot drift.

    ``name`` is what the operator sees. ``slug`` is the directory. They are
    different strings and comparing one to the other is always false, which
    is the bug this type exists to make unrepresentable.
    """

    name: str
    slug: str
    data_dir: str
    repo_dir: str
    csv_path: str

    def __str__(self) -> str:                  # pragma: no cover - display
        return self.name

    def matches(self, other) -> bool:
        """Same list? Compares IDENTITY, not either of the two names.

        ``check_right_repository()`` asked ``slug == list_name`` and got
        ``'default' != 'Default'``. Resolving both sides to a real directory
        answers "is this the same list", which is the question, rather than
        "do these two strings match", which was never it.
        """
        if other is None:
            return False
        if isinstance(other, ListRef):
            return os.path.realpath(self.data_dir) == os.path.realpath(
                other.data_dir)
        try:
            return self.matches(resolve(str(other)))
        except UnknownList:
            return False


def _registry() -> dict:
    """``{display name: slug}`` from the device-lists config, or ``{}``."""
    try:
        from modules.device import _load_device_lists_config

        config = _load_device_lists_config() or {}
        lists = config.get("lists") or {}
        return {name: slug for name, slug in lists.items()
                if isinstance(slug, str) and not slug.endswith(".csv")}
    except Exception as exc:                   # noqa: BLE001
        log.warning("listref: could not read the device-list registry: %s", exc)
        return {}


def _build(name: str, slug: str) -> ListRef:
    """One accessor for the directory: ``config.get_list_data_dir()``.

    A first version joined ``LISTS_DIR`` with the registry's slug and fell
    back to the accessor. That is a SECOND derivation of the thing this
    module exists to derive once — and it broke immediately: a caller that
    had overridden `get_list_data_dir` still got the real directory, so a
    uniqueness check enumerated the wrong parent and found no rival to
    refuse.

    Everything else in the app reaches a list's files through that accessor,
    so a ref built any other way describes a directory the rest of the app is
    not using. The registry's job here is only to map slug to display name.
    """
    from modules.config import get_list_data_dir, list_slug

    data_dir = get_list_data_dir(name)
    derived = list_slug(name)
    if slug and slug != derived:
        # The registry and `list_slug()` disagree. The app cannot honour both
        # -- `get_current_device_list()` reads the registry while everything
        # else derives -- so this is a real inconsistency, not a preference.
        log.warning("listref: registry slug %r for list %r does not match the "
                    "derived slug %r; the rest of the app derives, so that is "
                    "what this ref uses", slug, name, derived)
    return ListRef(name=name, slug=derived, data_dir=data_dir,
                   repo_dir=os.path.join(data_dir, "config_repo"),
                   csv_path=os.path.join(data_dir, "devices.csv"))


def resolve(name: str) -> ListRef:
    """A ``ListRef`` for *name*, which may be a display name OR a slug.

    Accepting both is deliberate. Callers receive a list identifier from a
    request parameter, a config file or another module, and which of the two
    names it is has never been consistent — that inconsistency is defect 3.
    Refusing a slug would move the bug rather than remove it.
    """
    from modules.config import list_slug

    if isinstance(name, ListRef):
        return name
    text = (name or "").strip()
    if not text:
        raise UnknownList("no list name given")

    registry = _registry()
    if text in registry:
        return _build(text, registry[text])

    # A slug was passed. Find the display name that owns it, so the ref is
    # complete either way -- a caller given only a slug still gets the name
    # to show, and one given only a name still gets the directory.
    for display, slug in registry.items():
        if slug == text:
            return _build(display, slug)

    # Unregistered: derive, and say so. Not an error -- a list can exist on
    # disk before the registry catches up -- but worth a line, because a
    # silently derived slug is how two directories for one list appear.
    derived = list_slug(text)
    if registry:
        log.info("listref: '%s' is not in the device-list registry; "
                 "deriving slug '%s'", text, derived)
    return _build(text, derived)


def active() -> ListRef:
    """The currently selected list.

    **Named so that reading ambient state is visible at the call site.** The
    three defects above all looked like ordinary calls; `ListRef.active()`
    reads as a deliberate act, and a function that already holds a `ListRef`
    calling it is obviously wrong.
    """
    from modules.config import get_current_list_name

    return resolve(get_current_list_name())


def coerce(value) -> ListRef:
    """A ``ListRef`` from a ``ListRef``, a name, a slug, or nothing.

    The migration seam: a route that still receives a string can hand it
    straight to a function that wants a ref, and a function that wants a ref
    can accept one from a caller not yet converted.
    """
    if isinstance(value, ListRef):
        return value
    if value:
        return resolve(value)
    return active()
