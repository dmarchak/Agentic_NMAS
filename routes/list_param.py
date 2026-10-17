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
`_target_list()`, and creating a list is a write that SHOULD make one. The
one exception is a v2 write whose ADDRESS names its page's network (W2's A1,
`_refuse_a_v2_write_on_a_network_that_is_gone`): that name is the page's,
written in by `routes/page_network`, and a network deleted since the page
drew must not let the write fall through to another network.
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


#: Where a WRITE's form carries the network it acts on.
FORM_KEYS = ("list",)


def submitted_list(req) -> tuple:
    """``(name, refusal)``: the network a write acts on (C838). The one its SUBMITTED FORM
    names, which is the network the page drew; else the page's address's; else the active
    one. A form and an address naming two different networks is refused, naming both, and so
    is a name no network has: a write never lands on a network nobody chose."""
    form = ""
    for key in FORM_KEYS:
        form = (req.form.get(key) or "").strip()
        if form:
            break
    url = named_list(req)
    if form and url and form != url:
        return "", (f"the form names the network {form!r} and the page's address names "
                    f"{url!r}: which one is meant cannot be told, so nothing was changed")
    name = form or url
    from modules.nsot import listref
    if not name:
        return listref.active().name, ""
    if not listref.exists(name):
        return "", f"there is no network named {name[:60]!r}: nothing was changed"
    return name, ""


def named_lists(req) -> list:
    """EVERY list a request names, its query's then its path's, each once. `named_list` returns
    the first only, and the guard that asked it alone let ``/v2/settings/network/<deleted>
    ?list=Default`` draw a deleted network's settings, the query's name passing for both (W2,
    2026-10-16: the picker had reloaded that path with Default's name)."""
    out = []
    for value in [req.args.get(k) for k in QUERY_KEYS] + \
            [(req.view_args or {}).get(k) for k in PATH_KEYS]:
        value = str(value or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def _refuse_a_v2_write_on_a_network_that_is_gone():
    """A v2 write whose ADDRESS names a network nobody has is refused before its view (W2's A1).

    Every request a v2 page makes names the page's network in its address
    (`routes/page_network`), and `listref.active()` reads it there. A network deleted since the
    page drew would otherwise read as no network at all, and the write would land on the
    person's own choice or the installation's: a different network from the one the page
    showed. A write's FORM is still its own route's business (C838's `submitted_list`, and
    creating a network names one that does not exist yet)."""
    from modules.nsot.listref import PAGE_ROUTES_OUTSIDE_V2

    if not (request.path.startswith("/v2/") or request.endpoint in PAGE_ROUTES_OUTSIDE_V2):
        return None
    from modules.nsot.listref import exists

    # The address's network, and the network a v2 PATH names (C1029: Settings' cards post to
    # `/v2/settings/network/<list_name>/...`, whose path names the network and so carries no
    # `?list=`; a deleted network's switch and mode wrote its folder again).
    names = [(request.args.get("list") or "").strip()]
    if request.path.startswith("/v2/"):
        names += [str((request.view_args or {}).get(k) or "").strip() for k in PATH_KEYS]
    name = next((n for n in names if n and not exists(n)), "")
    if not name:
        return None
    log.info("list_param: refused a write naming unknown network %r (%s)", name, request.path)
    return jsonify({
        "ok": False, "unknown_list": name,
        "error": _gone_words(name) + " Nothing was changed, here or in any other network.",
    }), 404


def _gone_words(name: str) -> str:
    """Why *name* is no network: deleted (when, and where its data is), or never one."""
    from modules import network_admin

    gone = network_admin.deletion(name)
    if gone:
        return (f"{name!r} was deleted{' at ' + gone['at'] if gone.get('at') else ''}; its "
                f"data is at {gone['folder']}.")
    return f"There is no network named {name!r}, the one this page was drawn for."


#: GET pages that draw a DELETED network themselves, rather than being refused here (C1029):
#: endpoint -> why. Each says when it was deleted and where its data is, with no actions.
DRAWS_ITS_DELETED_NETWORK = {
    "settings_v2.network": "a network's Settings page: where its delete was done, and where a "
                           "page drawn before it, or a link to it, leads",
}


def install(app) -> None:
    @app.before_request
    def _refuse_a_read_of_an_unknown_list():
        if request.method not in ("GET", "HEAD"):
            return _refuse_a_v2_write_on_a_network_that_is_gone()
        from modules.nsot.listref import exists

        name = next((n for n in named_lists(request) if not exists(n)), "")
        if not name:
            return None
        if request.endpoint in DRAWS_ITS_DELETED_NETWORK and \
                name == str((request.view_args or {}).get("list_name") or "").strip():
            from modules import network_admin

            if network_admin.is_deleted(name):
                return None
        log.info("list_param: refused a read of unknown list %r (%s)",
                 name, request.path)
        return jsonify({
            "ok": False, "unknown_list": name,
            "error": (f"There is no device list named {name!r}. Nothing was "
                      "read and nothing was created. This is not the same as "
                      "an empty list: check the name."),
        }), 404
