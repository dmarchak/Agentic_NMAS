"""A READ that names a list which does not exist is refused, naming it.

Register C51. 24 GETs resolved their paths through
`config.get_list_data_dir()`, which calls `os.makedirs()`, so asking about a
list that does not exist brought it into existence: `lists/<typo>/`, with
whatever the route then wrote into it. And an empty answer is the worse half
of that: `/onboard/pending?list_name=<typo>` reading "none pending" is a
statement about a list nobody has, in the words of a statement about one
they do.

So the refusal is made ONCE, here, before any view runs and so before
anything resolves a path. The list arrives in the three places the routes
read it from (measured: the `list_name` and `list` query parameters, and a
`list_name` path converter), and `test_reads_create_no_list.py` sweeps every
GET for the PROPERTY, so a route taking a list some other way is found
rather than assumed away.

Writes are not this hook's business. A POST naming a list that does not
exist is judged by its own route: onboarding refuses through
`_target_list()`, and creating a list is a write that SHOULD make one.
"""

import logging

from flask import jsonify, request

log = logging.getLogger(__name__)

#: Where a GET carries a list name. Measured from the routes, not assumed;
#: the sweep is what keeps this honest.
QUERY_KEYS = ("list_name", "list")
PATH_KEYS = ("list_name",)


def named_list(req) -> str:
    """The list a request names, or ``""`` when it names none (the route then
    reads the active list, whose directory exists)."""
    for key in QUERY_KEYS:
        value = (req.args.get(key) or "").strip()
        if value:
            return value
    for key in PATH_KEYS:
        value = str((req.view_args or {}).get(key) or "").strip()
        if value:
            return value
    return ""


def install(app) -> None:
    @app.before_request
    def _refuse_a_read_of_an_unknown_list():
        if request.method not in ("GET", "HEAD"):
            return None
        name = named_list(request)
        if not name:
            return None
        from modules.nsot.listref import exists

        if exists(name):
            return None
        log.info("list_param: refused a read of unknown list %r (%s)",
                 name, request.path)
        return jsonify({
            "ok": False, "unknown_list": name,
            "error": (f"There is no device list named {name!r}. Nothing was "
                      "read and nothing was created. This is not the same as "
                      "an empty list: check the name."),
        }), 404
