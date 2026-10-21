"""netbox_client.py

NetBox IPAM/DCIM sync for the Network Device Manager.

Acts as the bridge that keeps NetBox in sync with the application's device lists:

  - Each device list becomes a NetBox *region* (grouping container) and a same-named
    *site* beneath it (since devices in NetBox must be attached to a site).
  - Every device in a list is scanned via SSH (show version / show inventory) to
    extract model, serial number, platform, and software version, then POSTed to
    NetBox as a device record under its list's region/site.
  - Manufacturers, device-types, and device-roles are created on demand.

NetBox URL and API token are stored in user_settings.json (`netbox_url`,
`netbox_token`, `netbox_verify_tls`).
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import threading
import time
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from modules.config import (
    DATA_DIR,
    get_user_setting,
    set_user_setting,
    list_slug,
)

log = logging.getLogger(__name__)

# Persistent sync status file (last-sync timestamp and per-list summary).
_SYNC_STATUS_FILE = os.path.join(DATA_DIR, "netbox_sync_status.json")
_status_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def get_netbox_config() -> dict:
    """Return the stored NetBox configuration.

    The token is decrypted on read. Values written by builds that predate
    :mod:`modules.secrets_store` were plaintext and are returned as-is until the
    settings migration upgrades them.
    """
    from modules.secrets_store import get_secret
    return {
        "url":        (get_user_setting("netbox_url", "") or "").rstrip("/"),
        "token":      get_secret("netbox_token"),
        "verify_tls": bool(get_user_setting("netbox_verify_tls", True)),
        # Auth header NetBox accepts: "Bearer" (docs format) or "Token" (legacy).
        # Discovered during test_connection() and cached here.
        "auth_scheme": (get_user_setting("netbox_auth_scheme", "Bearer") or "Bearer"),
        # Fail-closed write gate — see modules/netbox_guard.py.
        "allow_writes": bool(get_user_setting("netbox_allow_writes", False)),
    }


# save_netbox_config left with today's Settings modal (7.8, 2026-10-15), its one caller: NetBox's
# settings are saved by Settings › Installation's card (modules/installation_settings.py).


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

def _build_session(token: str, verify_tls: bool,
                   auth_scheme: str = "Bearer") -> requests.Session:
    """Return a requests Session preconfigured for the NetBox REST API.

    `auth_scheme` is the Authorization prefix ("Bearer" or "Token"). NetBox 4.x
    accepts Bearer (as shown in its own docs) and older versions accept Token.
    """
    s = requests.Session()
    scheme = auth_scheme if auth_scheme in ("Bearer", "Token") else "Bearer"
    s.headers.update({
        "Authorization": f"{scheme} {token}",
        "Accept":        "application/json",
        "Content-Type":  "application/json",
    })
    s.verify = verify_tls

    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "POST", "PATCH", "PUT", "DELETE"),
    )
    s.mount("http://",  HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _session_from_config(cfg: dict) -> requests.Session:
    """Build a session from the stored NetBox config."""
    return _build_session(cfg["token"], cfg["verify_tls"], cfg.get("auth_scheme", "Bearer"))


def test_connection(url: str, token: str, verify_tls: bool = True,
                    persist_scheme: bool = True,
                    schemes: tuple = ("Bearer", "Token")) -> tuple[bool, str]:
    """Ping the NetBox status endpoint. Returns (ok, message).

    Tries each auth header in *schemes*: by default Bearer first (NetBox's
    documented format), falling back to the legacy Token header if Bearer is
    rejected. When `persist_scheme` is true and the probe succeeds, the working
    scheme is cached in user settings so every subsequent sync uses it directly.
    The NetBox card's Test (Settings › Installation) passes the one scheme the card
    holds and persists nothing (`NetBoxIntegration.test_now`).
    """
    if not url or not token:
        return False, "NetBox URL and API token are required"

    base = url.rstrip("/")
    last_status = None
    last_err    = None
    reasons = []

    for scheme in schemes:
        try:
            s = _build_session(token, verify_tls, auth_scheme=scheme)
            r = s.get(f"{base}/api/status/", timeout=8)
            if r.status_code == 200:
                data = r.json() if r.content else {}
                version = data.get("netbox-version") or data.get("django-version") or "unknown"
                if persist_scheme:
                    set_user_setting("netbox_auth_scheme", scheme)
                missing = missing_views(s, base)
                if missing:
                    # C468: `api/status/` needs no permission, so a token missing a VIEW the
                    # tool reads passed the Test and failed later, in a sync, by type.
                    return False, (f"Connected to NetBox (version {version}) using {scheme} "
                                   f"auth, but the token cannot read: "
                                   + "; ".join(f"{label} ({why})" for label, why in missing)
                                   + ". Grant view on each (docs/SERVICE_ACCOUNTS.md 1.3)")
                return True, (f"Connected to NetBox (version {version}) using {scheme} auth; "
                              f"every type the tool reads answered ({len(READ_PROBES)})")
            last_status = r.status_code
            reasons.append(refusal_reason(r))
            if r.status_code not in (401, 403):
                # A non-auth failure — don't bother trying the other scheme.
                return False, f"NetBox returned HTTP {r.status_code}: {reasons[-1]}"
        except requests.exceptions.SSLError as exc:
            return False, f"TLS verification failed: {exc}"
        except requests.exceptions.ConnectionError as exc:
            return False, f"Could not connect to {base}: {exc}"
        except Exception as exc:
            last_err = exc

    if last_err:
        return False, f"Connection test failed: {last_err}"
    if last_status in (401, 403):
        # C468: NetBox's own reason, never only "Authentication failed": an expired token, a
        # token for another key, and a source address the token does not allow each need a
        # different repair, and a person could not tell them apart.
        said = next((x for x in reasons if x), "")
        return False, (f"NetBox refused the token (HTTP {last_status}, tried "
                       f"{' and '.join(schemes)}): "
                       f"{said or 'no reason given'}. {refusal_advice(said)}").strip()
    return False, "NetBox connection failed"


#: One row of each type the tool READS (the C100 survey, 2026-10-05; SERVICE_ACCOUNTS 1.3's
#: `nmas-view`). A token missing one passes `api/status/` and fails later, in a sync.
READ_PROBES = (
    ("dcim/devices/", "DCIM › device"), ("dcim/interfaces/", "DCIM › interface"),
    ("dcim/sites/", "DCIM › site"), ("dcim/regions/", "DCIM › region"),
    ("dcim/platforms/", "DCIM › platform"), ("dcim/device-roles/", "DCIM › device role"),
    ("dcim/device-types/", "DCIM › device type"), ("dcim/manufacturers/", "DCIM › manufacturer"),
    ("dcim/cables/", "DCIM › cable"),
    ("ipam/ip-addresses/", "IPAM › IP address"), ("ipam/prefixes/", "IPAM › prefix"),
    ("ipam/vrfs/", "IPAM › VRF"), ("ipam/vlans/", "IPAM › VLAN"), ("ipam/roles/", "IPAM › role"),
    ("extras/tags/", "Extras › tag"), ("extras/custom-fields/", "Extras › custom field"),
    ("extras/config-templates/", "Extras › config template"),
    ("vpn/tunnels/", "VPN › tunnel"), ("vpn/tunnel-terminations/", "VPN › tunnel termination"),
    ("core/object-changes/", "Core › object change"), ("users/tokens/", "Users › token"),
)


def missing_views(session, base: str) -> list:
    """``[(type label, why)]`` for each type in READ_PROBES the token may not read: 401 or
    403 with NetBox's reason. Another failure (a 5xx, an unreachable path) is not a missing
    permission and is not named here."""
    out = []
    for path, label in READ_PROBES:
        try:
            r = session.get(f"{base}/api/{path}", params={"limit": 1}, timeout=8)
        except Exception:                                   # noqa: BLE001
            continue
        if r.status_code in (401, 403):
            out.append((label, refusal_reason(r) or f"HTTP {r.status_code}"))
    return out


def refusal_reason(r) -> str:
    """NetBox's own words for a refusal (its `detail`), masked; "" when it gave none."""
    from modules.redact import redact_text

    try:
        doc = r.json() if getattr(r, "content", b"") else {}
        detail = doc.get("detail") if isinstance(doc, dict) else ""
    except Exception:                                       # noqa: BLE001
        detail = ""
    if not detail:
        detail = (getattr(r, "text", "") or "")[:200]
    return redact_text(str(detail or "").strip())[:300]


def refusal_advice(reason: str) -> str:
    """What to do about a refusal, by NetBox's words. "" when the words are not one of the
    known shapes: the reason itself is then the advice."""
    low = (reason or "").lower()
    if "expired" in low:
        return ("The token has expired: create a new one for the same user and paste it here "
                "(Settings › NetBox).")
    if "source ip" in low or "not permitted to authenticate" in low or "allowed ip" in low:
        return ("The token's Allowed IPs do not include the address NetBox sees for this host "
                "(named above): add it to the token, or clear the field.")
    if "invalid" in low or "not found" in low or "credentials" in low:
        return ("NetBox does not know this token: paste the whole token (`nbt_<key>.<secret>` "
                "for a version 2 token), or create a new one.")
    if "permission" in low:
        return "The token's user lacks a permission NetBox requires for this read."
    return ""


# ---------------------------------------------------------------------------
# Low-level get-or-create helpers
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    """Produce a NetBox-compatible slug (lowercase, hyphens, alnum + underscore)."""
    s = re.sub(r"[^\w\-]+", "-", (name or "").strip().lower()).strip("-_")
    return s or "unnamed"


def _planned_only(params: dict) -> bool:
    """True when a dry run's query filters by one of its own placeholder ids (C1179).

    A dry run gives each object it plans a negative id (`_DryRunPlan.synthetic_id`). Nothing in
    NetBox can be filed under an object that does not exist, and NetBox 4.6.9 answers a negative
    id with 400 (W4, 2026-10-17: Adopt's preview for a network with no site yet), so such a query
    is answered from the plan alone and never sent."""
    from modules import netbox_guard as _guard

    return _guard.is_dry_run() and any(
        isinstance(v, int) and not isinstance(v, bool) and v < 0 for v in params.values())


def _nb_get(session: requests.Session, base: str, path: str, **params) -> list[dict]:
    """GET a NetBox list endpoint, following pagination. Returns all results.

    During a dry run the results also include objects the dry run has already
    pretended to create, so get-or-create behaves as it would in a real run.
    """
    if _planned_only(params):
        from modules import netbox_guard as _guard
        return list(_guard.current_plan().find_virtual(path, params))
    results: list[dict] = []
    url: Optional[str] = f"{base}/api/{path.lstrip('/')}"
    first = True
    while url:
        r = session.get(url, params=params if first else None, timeout=15)
        r.raise_for_status()
        data = r.json()
        results.extend(data.get("results", []))
        url = data.get("next")
        first = False

    from modules import netbox_guard as _guard
    if _guard.is_dry_run():
        results.extend(_guard.current_plan().find_virtual(path, params))
    return results


def _nb_first(session: requests.Session, base: str, path: str, **params) -> Optional[dict]:
    """Return the first matching result from a NetBox list query, or None.

    During a dry run, falls back to objects the dry run already pretended to
    create — see :func:`_nb_get`.
    """
    if _planned_only(params):
        from modules import netbox_guard as _guard
        hits = _guard.current_plan().find_virtual(path, params)
        return hits[0] if hits else None
    r = session.get(f"{base}/api/{path.lstrip('/')}", params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    hits = data.get("results", [])
    if not hits:
        from modules import netbox_guard as _guard
        if _guard.is_dry_run():
            hits = _guard.current_plan().find_virtual(path, params)
    return hits[0] if hits else None


def _object_label(payload: dict) -> str:
    """Best human-readable name from a NetBox payload, for previews and logs."""
    # `label` last: a cable has no name, and the import labels one by its two ends (C1344).
    for key in ("name", "address", "prefix", "display", "label"):
        if payload.get(key):
            return str(payload[key])
    return ""


# Managed-tag id cache, keyed by NetBox base URL.
_managed_tag_ids: dict = {}


def _managed_tag_id(session: requests.Session, base: str):
    """Get-or-create the ``nmas-managed`` tag, caching its id per NetBox."""
    from modules.netbox_guard import MANAGED_TAG, MANAGED_TAG_SLUG
    # Only a SUCCESS is cached (register C59). A failure used to be cached as
    # None for the life of the process, so one transient error left every
    # later create untagged until a restart, and only the first was recorded.
    if _managed_tag_ids.get(base):
        return _managed_tag_ids[base]
    tag = _ensure_tag(session, base, MANAGED_TAG, MANAGED_TAG_SLUG, "00bcd4")
    if not tag.get("id"):
        raise RuntimeError(f"NetBox returned no id for the '{MANAGED_TAG}' tag")
    _managed_tag_ids[base] = tag["id"]
    return tag["id"]


def _with_managed_tag(session: requests.Session, base: str,
                      path: str, payload: dict) -> dict:
    """Add ``nmas-managed`` to *payload* when the endpoint supports tags.

    This is how removal later tells NMAS-created objects apart from records a
    human curated by hand.
    """
    from modules.netbox_guard import MANAGED_TAG, is_taggable
    if not is_taggable(path):
        return payload
    # FAIL CLOSED (register C59; the operator's reading). This was "tagging
    # is provenance, not correctness -- never fail a write over it". But the
    # tag IS the safety mechanism: Remove acts only on objects that are
    # tagged AND recorded, so an untagged create is an object NMAS made and
    # can NEVER clean up, and it happened silently, because the create
    # succeeded. A create that cannot be tagged is refused; its caller records
    # the refusal as a write failure, which the summary names.
    try:
        tag_id = _managed_tag_id(session, base)
    except Exception as exc:
        raise RuntimeError(
            f"refusing to create {path.strip('/')} untagged: the "
            f"'{MANAGED_TAG}' tag could not be ensured ({exc}), and an untagged "
            f"object is one Remove can never act on") from exc
    tags = list(payload.get("tags") or [])
    if tag_id not in tags:
        tags.append(tag_id)
    return {**payload, "tags": tags}


def _nb_post(session: requests.Session, base: str, path: str, payload: dict) -> dict:
    """POST a payload to a NetBox endpoint and return the JSON response.

    One of three write chokepoints. Every write is gated on
    ``netbox_allow_writes`` and recorded so removal can tell what NMAS created.
    """
    from modules import netbox_guard as _guard

    endpoint = path.strip("/")
    if _guard.is_dry_run():
        _guard.record_intent("creates", endpoint, payload, name=_object_label(payload))
        # Synthetic id so callers that chain on result["id"] keep working, and
        # the object is remembered so a later get-or-create for the same thing
        # finds it instead of planning a duplicate.
        obj = {**payload, "id": _guard.current_plan().synthetic_id(), "_dry_run": True}
        _guard.current_plan().add_virtual(endpoint, obj)
        return obj

    _guard.assert_writes_allowed(f"POST {endpoint}")
    payload = _with_managed_tag(session, base, path, payload)

    r = session.post(f"{base}/api/{path.lstrip('/')}", json=payload, timeout=20)
    if not r.ok:
        raise RuntimeError(
            f"POST {path} failed ({r.status_code}): {r.text[:300]}"
        )
    obj = r.json()
    _guard.record_created(_guard.get_current_list(), endpoint,
                          obj.get("id"), _object_label(obj) or _object_label(payload))
    return obj


def _nb_patch(session: requests.Session, base: str, path: str, payload: dict) -> dict:
    """PATCH a payload to a NetBox endpoint (id embedded in path).

    One of three write chokepoints — see :func:`_nb_post`.
    """
    from modules import netbox_guard as _guard

    # PATCH paths embed the object id: "dcim/devices/42/".
    parts    = path.strip("/").split("/")
    obj_id   = int(parts[-1]) if parts[-1].isdigit() else None
    endpoint = "/".join(parts[:-1]) if obj_id is not None else path.strip("/")

    if _guard.is_dry_run():
        # READ THE OBJECT, as the real path does (C135). A dry-run PATCH
        # returned only its payload, so a caller that read the returned object
        # next saw fields the payload did not carry as EMPTY: the protocol-tag
        # step then found an untagged device and planned `tags` on eight
        # devices whose tags were already exactly those (measured on the host,
        # every one SETS == HOLDS), a write the real import never makes. The
        # object as NetBox holds it, with the payload over it, is what the
        # real PATCH returns. And the intent records what the payload
        # CHANGES, so the preview can say "changes nothing" for a no-op.
        state, current = (_nb_read_by_id(session, base, endpoint, obj_id)
                          if obj_id else ("unreadable", None))
        changed = _guard.changed_fields(current if state == "ok" else None, payload)
        _guard.record_intent("updates", endpoint, payload, obj_id=obj_id,
                             name=_object_label(payload)
                             or _object_label(current if state == "ok" else {}),
                             changed=changed)
        # Return the object's REAL id, not a synthetic one. An update targets
        # something that already exists, and callers chain child objects off the
        # returned id — handing back a placeholder would orphan them and make the
        # preview plan creates that execution would not perform.
        base_obj = current if state == "ok" else {}
        return {**base_obj, **payload, "id": obj_id, "_dry_run": True}

    _guard.assert_writes_allowed(f"PATCH {endpoint}")

    # READ THE BEFORE-STATE FIRST, here rather than from the caller.
    #
    # An update is the one write NMAS makes that carries no provenance: the
    # `nmas-managed` tag is injected in _nb_post only -- correctly, since the
    # tag means "NMAS created this" and claiming a human's object would make
    # it deletable -- and nothing was recorded either, so for weeks
    # `_ensure_ip_address()` moved one address object between six devices
    # with the tag, the created-id record and the census all silent, because
    # the object never disappeared.
    #
    # Fetched here and not passed in: an optional `before=` argument is how a
    # caller bypasses this by omission, and eleven call sites are eleven
    # chances to forget. An unreadable object records `before_unknown` rather
    # than nothing, because "what changed is unknown" and "nothing changed"
    # must not share an answer.
    before = _nb_get_by_id(session, base, endpoint, obj_id) if obj_id else None

    r = session.patch(f"{base}/api/{path.lstrip('/')}", json=payload, timeout=20)
    if not r.ok:
        raise RuntimeError(
            f"PATCH {path} failed ({r.status_code}): {r.text[:300]}"
        )
    obj = r.json()
    _guard.record_modified(
        _guard.get_current_list(), endpoint, obj_id,
        _guard.changed_fields(before, payload),
        name=_object_label(before or obj) or _object_label(payload),
    )
    return obj


def _ensure_region(session, base: str, name: str) -> dict:
    """Get-or-create a NetBox region named after the device list."""
    slug = _slug(name)
    existing = _nb_first(session, base, "dcim/regions/", slug=slug)
    if existing:
        return existing
    return _nb_post(session, base, "dcim/regions/", {
        "name": name,
        "slug": slug,
        "description": "Created by Network Device Manager — mirrors a device list.",
    })


def _mercury_may_edit(obj: dict, endpoint: str) -> bool:
    """Whether the sync may EDIT an existing object beyond what it always updates: Mercury
    created it, by its tag OR by its created-id record (`_ensure_site`'s rule, explained there;
    removal takes the stricter tagged AND recorded). Used where an edit would otherwise change a
    person's object: a site's region, a prefix's scope (C1010)."""
    from modules import netbox_guard as _guard

    return bool(_guard.has_managed_tag(obj)
                or _guard.was_created_by_nmas(_guard.get_current_list(), endpoint, obj["id"]))


def _ensure_site(session, base: str, name: str, region_id: int,
                 notes: list = None) -> dict:
    """Get-or-create a NetBox site under the given region (same name as region).

    **It re-parents only a site NMAS created.** The previous version moved any
    site whose slug matched, with the comment *"re-parent to the right region
    if someone moved it"* -- so a site a human had deliberately placed was
    silently moved back on the next sync. That is a behaviour nobody chose,
    and it is inconsistent in the direction that matters: removal **refuses**
    to touch an object NMAS did not create, so the tool would decline to
    delete your site while happily moving it.

    Ownership is *tagged OR recorded*, which is deliberately **not** removal's
    *tagged AND recorded*. The two actions differ in blast radius: deleting a
    human's object is unrecoverable, so removal takes the conservative
    conjunction, while declining to re-parent NMAS's own site costs a warning.
    The tag is only ever applied by ``_nb_post``, so a tagged site *was*
    created by NMAS even if the created-id record has since been lost -- which
    happens when a list is deleted and re-created.

    Adoption is unchanged: a site with a matching slug is still used rather
    than duplicated. What changed is that NMAS no longer edits it silently.
    """
    slug = _slug(name)
    existing = _nb_first(session, base, "dcim/sites/", slug=slug)
    if existing:
        current_region = (existing.get("region") or {}).get("id")
        if current_region != region_id:
            if _mercury_may_edit(existing, "dcim/sites"):
                _nb_patch(session, base, f"dcim/sites/{existing['id']}/",
                          {"region": region_id})
                existing["region"] = {"id": region_id}
            else:
                note = (
                    f"site '{existing.get('name') or slug}' is in a different "
                    f"region and Mercury did not create it, so it was left where "
                    f"it is. Devices for this list will be added to it. Move "
                    f"it in NetBox if that is wrong."
                )
                log.warning("netbox: %s", note)
                if notes is not None:
                    notes.append(note)
        return existing
    return _nb_post(session, base, "dcim/sites/", {
        "name":   name,
        "slug":   slug,
        "status": "active",
        "region": region_id,
    })


def _ensure_manufacturer(session, base: str, name: str) -> dict:
    """Get-or-create a manufacturer (vendor) record."""
    name = name or "Cisco"
    slug = _slug(name)
    existing = _nb_first(session, base, "dcim/manufacturers/", slug=slug)
    if existing:
        return existing
    return _nb_post(session, base, "dcim/manufacturers/", {"name": name, "slug": slug})


def _ensure_device_type(session, base: str, model: str, manufacturer_id: int) -> dict:
    """Get-or-create a device-type (model)."""
    model = model or "Generic"
    slug = _slug(model)
    existing = _nb_first(session, base, "dcim/device-types/", slug=slug)
    if existing:
        return existing
    return _nb_post(session, base, "dcim/device-types/", {
        "manufacturer": manufacturer_id,
        "model":        model,
        "slug":         slug,
        "u_height":     1,
    })


def _ensure_device_role(session, base: str, name: str = "Network Device") -> dict:
    """Get-or-create a device-role. Uses the new /dcim/roles/ path on NetBox 4.x,
    falling back to the legacy /dcim/device-roles/ path on 3.x."""
    slug = _slug(name)
    payload = {
        "name":          name,
        "slug":          slug,
        "color":         "2196f3",
        "vm_role":       False,
        "description":   "Default role for devices auto-created by Network Device Manager.",
    }
    # Prefer legacy path — still accepted by NetBox 4.x (aliased).
    try:
        existing = _nb_first(session, base, "dcim/device-roles/", slug=slug)
        if existing:
            return existing
        return _nb_post(session, base, "dcim/device-roles/", payload)
    except requests.exceptions.HTTPError:
        existing = _nb_first(session, base, "dcim/roles/", slug=slug)
        if existing:
            return existing
        return _nb_post(session, base, "dcim/roles/", payload)


# ---------------------------------------------------------------------------
# IPAM helpers — prefixes, interfaces, IP addresses
# ---------------------------------------------------------------------------

# Map of Netmiko driver → NetBox interface type. Keep the list short and
# default to a sensible "other" for unknowns.
_IFTYPE_MAP = {
    "loopback":     "virtual",
    "tunnel":       "virtual",
    "vlan":         "virtual",
    "port-channel": "lag",
    "portchannel":  "lag",
    "gigabitethernet":  "1000base-t",
    "tengigabitethernet": "10gbase-t",
    "fortygigabitethernet": "40gbase-x-qsfpp",
    "hundredgigabitethernet": "100gbase-x-qsfp28",
    "fastethernet": "100base-tx",
    "ethernet":     "1000base-t",
    "serial":       "other",
    "mgmt":         "1000base-t",
    "management":   "1000base-t",
}


def _netbox_iface_type(iface_name: str) -> str:
    """Return the best-matching NetBox interface type for a Cisco iface name."""
    lower = iface_name.lower().lstrip()
    for prefix, nb_type in _IFTYPE_MAP.items():
        if lower.startswith(prefix):
            return nb_type
    return "other"


_IFACE_ABBREV = [
    (re.compile(r"^GigabitEthernet", re.IGNORECASE), "Gi"),
    (re.compile(r"^FastEthernet",    re.IGNORECASE), "Fa"),
    (re.compile(r"^TenGigabitEthernet", re.IGNORECASE), "Te"),
    (re.compile(r"^Serial",   re.IGNORECASE), "Se"),
    (re.compile(r"^Loopback", re.IGNORECASE), "Lo"),
    (re.compile(r"^Vlan",     re.IGNORECASE), "Vl"),
    (re.compile(r"^Port-channel", re.IGNORECASE), "Po"),
    (re.compile(r"^Ethernet", re.IGNORECASE), "Et"),
]


def _shorten_iface_name(name: str) -> str:
    """Abbreviate a full Cisco interface name the same way this app's
    topology.py display layer does (GigabitEthernet0/3 -> Gi0/3), so it can
    be used as an alias key in nb_iface_map. Cisco LLDP commonly reports the
    *local* interface using this abbreviated form in 'Local Intf:'/'Port
    id:' even though the golden config (and CDP's 'Interface:' field) use
    the full name — without this alias, LLDP-only-discovered links fail the
    nb_iface_map lookup and their cable is silently never created."""
    for pattern, abbrev in _IFACE_ABBREV:
        if pattern.match(name):
            return pattern.sub(abbrev, name)
    return name


def _ensure_platform(session, base: str, name: str, manufacturer_id: int) -> dict:
    """Get-or-create a DCIM Platform (OS) record."""
    slug = _slug(name)
    existing = _nb_first(session, base, "dcim/platforms/", slug=slug)
    if existing:
        return existing
    return _nb_post(session, base, "dcim/platforms/", {
        "name":         name,
        "slug":         slug,
        "manufacturer": manufacturer_id,
    })


def _platform_for(session, base: str, name: str, dialect: str, manufacturer_id: int):
    """The DCIM Platform a device of *dialect* is given: the one NetBox holds under a slug
    naming that dialect (`platform.netbox_slugs_for_dialect`), else get-or-create *name*
    (the config text's reading), else None."""
    from modules.nsot.platform import netbox_slugs_for_dialect

    for slug in netbox_slugs_for_dialect(dialect):
        found = _nb_first(session, base, "dcim/platforms/", slug=slug)
        if found:
            return found
    return _ensure_platform(session, base, name, manufacturer_id) if name else None


def _ensure_vrf(session, base: str, name: str, rd: str = "") -> dict:
    """Get-or-create an IPAM VRF."""
    existing = _nb_first(session, base, "ipam/vrfs/", name=name)
    if existing:
        return existing
    payload: dict = {"name": name}
    if rd:
        payload["rd"] = rd
    return _nb_post(session, base, "ipam/vrfs/", payload)


def _ensure_vlan(session, base: str, vid: int, name: str,
                 site_id: Optional[int] = None) -> dict:
    """Get-or-create an IPAM VLAN."""
    params = {"vid": vid}
    if site_id:
        params["site_id"] = site_id
    existing = _nb_first(session, base, "ipam/vlans/", **params)
    if existing:
        return existing
    payload: dict = {"vid": vid, "name": name or f"VLAN{vid}", "status": "active"}
    if site_id:
        payload["site"] = site_id
    return _nb_post(session, base, "ipam/vlans/", payload)


def _ensure_tag(session, base: str, name: str,
                slug: str = "", color: str = "9e9e9e") -> dict:
    """Get-or-create an Extras tag (for device protocol labels, route types, etc.)."""
    slug = slug or _slug(name)
    existing = _nb_first(session, base, "extras/tags/", slug=slug)
    if existing:
        return existing
    return _nb_post(session, base, "extras/tags/", {
        "name":  name,
        "slug":  slug,
        "color": color,
    })


def _ensure_prefix_role(session, base: str, name: str) -> dict:
    """Get-or-create an IPAM prefix role (e.g. Loopback, Point-to-Point, Management)."""
    slug = _slug(name)
    existing = _nb_first(session, base, "ipam/roles/", slug=slug)
    if existing:
        return existing
    return _nb_post(session, base, "ipam/roles/", {"name": name, "slug": slug})


def _infer_prefix_role_name(iface_name: str, prefix: str) -> Optional[str]:
    """Heuristic prefix role from the interface it was seen on and its size —
    matches NetBox best practice of differentiating prefix function (loopback,
    point-to-point link, management) rather than leaving every prefix flat."""
    name_lower = (iface_name or "").lower()
    if name_lower.startswith("loopback"):
        return "Loopback"
    if name_lower.startswith(("management", "mgmt")):
        return "Management"
    try:
        net = ipaddress.ip_network(prefix, strict=False)
        if (net.version == 4 and net.prefixlen in (30, 31)) or \
           (net.version == 6 and net.prefixlen == 127):
            return "Point-to-Point"
    except ValueError:
        pass
    return None


# Custom field definitions this app relies on — created once per NetBox
# instance the first time they're needed. NetBox has no stock field for
# software/OS version; stuffing it only into free-text comments makes it
# unfilterable and unreportable, which is exactly what custom fields exist
# to fix (see NetBox docs — this is the documented pattern for exactly
# this kind of "doesn't fit a stock field" data).
_CUSTOM_FIELDS: dict = {
    "os_version": {
        "label":        "OS Version",
        "type":         "text",
        "object_types": ["dcim.device"],
        "description":  "Software version, e.g. IOS/IOS-XE/NX-OS release string.",
    },
}
_custom_fields_ensured: set = set()   # process-lifetime cache — avoid re-checking every sync

# DEFINITION WRITES THAT FAILED, per sync thread (OPEN_FINDINGS C6 item 2).
# `_ensure_custom_field` used to log a failed create at DEBUG and return
# False, so callers quietly skipped the field: a write that failed with
# nothing anywhere saying so -- the class the modification record exists
# for, on a path it does not cover. Now WARNING, and collected so the sync
# summary's `notes` names it. Thread-local, because two lists can sync at
# once on two threads.
_ensure_failures = threading.local()


def _ensure_failed(what: str, exc) -> None:
    msg = f"{what} could not be written: {exc}"
    log.warning("netbox: %s", msg)
    if not hasattr(_ensure_failures, "items"):
        _ensure_failures.items = []
    _ensure_failures.items.append(msg)


def _drain_ensure_failures() -> list:
    items = list(getattr(_ensure_failures, "items", None) or [])
    _ensure_failures.items = []
    return items


# A WRITE THAT DID NOT LAND, per sync thread (register C8). Twenty write
# paths logged their failure at DEBUG and the sync then reported `failed=0`:
# `failed` counts only devices whose WHOLE upsert raised, so a device whose
# VLAN, cable or primary IP did not land was counted as created or updated,
# and its failures appeared nowhere. That is the number Stage 7.1's
# preview-confirm component draws, so a counter that cannot count failures
# would have been drawn as an assurance. Every write path records here:
# a WARNING, and a structured entry naming the device, the write and the
# error, which the sync summary carries as `write_failures`.
_write_failures = threading.local()
_current_device = threading.local()


# WHAT THE IMPORT DELIBERATELY DOES NOT MODEL, per sync (the operator,
# 2026-09-28). Not a failure and not a refusal: a decision, so the summary
# carries it in its own key and the result draws it as "not imported, on
# purpose", beside the reason. "5 fewer writes" must be explained, never
# silent. `ips_excluded` was counted into `ipam_stats` since the
# excluded-VRF rule and carried into nothing a person reads.
def _skip(ipam_stats: dict, what: str, why: str, device: str, count: int = 1) -> None:
    ipam_stats.setdefault("skipped", []).append(
        {"what": what, "why": why, "device": device, "count": count})


#: Why a default route is not imported as a prefix. NetBox refuses a /0
#: ("Cannot create prefix with /0 mask", measured in (b)'s import on five
#: routers), and it is right to: a default route is a ROUTE, not a block of
#: address space, and NetBox has no object for a route.
DEFAULT_ROUTE_SKIP = ("a default route is a route, not a block of address space, and NetBox "
                      "holds no /0 prefix; the route stays in the golden and in NetBox's "
                      "masked config text")


def merge_skipped(reports) -> list:
    """Several syncs' grouped skips as one: devices united, counts summed."""
    groups: dict = {}
    for report in reports:
        for g in report or []:
            m = groups.setdefault((g["what"], g["why"]),
                                  {"what": g["what"], "why": g["why"], "devices": [], "count": 0})
            m["devices"] = sorted(set(m["devices"]) | set(g.get("devices") or []))
            m["count"] += int(g.get("count") or 0)
    return sorted(groups.values(), key=lambda g: g["what"])


def skipped_report(skipped: list) -> list:
    """Group the skips of one sync by (what, why): ``[{what, why, devices,
    count}]``, devices sorted, so a summary names each class once."""
    groups: dict = {}
    for s in skipped or []:
        g = groups.setdefault((s["what"], s["why"]),
                              {"what": s["what"], "why": s["why"], "devices": [], "count": 0})
        if s.get("device") and s["device"] not in g["devices"]:
            g["devices"].append(s["device"])
        g["count"] += int(s.get("count") or 1)
    for g in groups.values():
        g["devices"].sort()
    return sorted(groups.values(), key=lambda g: g["what"])


def _write_failed(what: str, exc, device: str = "") -> None:
    """Record a NetBox write that did not land. *device* defaults to the
    device the sync is upserting (`_attributed_to`). The error text is
    redacted, because the summary leaves this host."""
    from modules.redact import redact_text

    dev = device or getattr(_current_device, "name", "") or ""
    error = redact_text(str(exc))[:300]
    log.warning("netbox: %s%s could not be written: %s",
                f"{dev}: " if dev else "", what, error)
    if not hasattr(_write_failures, "items"):
        _write_failures.items = []
    _write_failures.items.append({"device": dev, "write": what, "error": error})


def _drain_write_failures() -> list:
    items = list(getattr(_write_failures, "items", None) or [])
    _write_failures.items = []
    return items


class _attributed_to:
    """Attribute every write failure inside the block to *device*."""

    def __init__(self, device: str):
        self.device = device

    def __enter__(self):
        self.previous = getattr(_current_device, "name", "")
        _current_device.name = self.device
        return self

    def __exit__(self, *exc):
        _current_device.name = self.previous
        return False


def write_failure_report(failed_devices: list, write_failures: list) -> dict:
    """The part of a sync summary a person, and 7.1's component, reads as
    the outcome. PURE, so the counting is tested apart from a NetBox.

    * `failed`: devices whose whole upsert raised (unchanged);
    * `write_failures`: every write that did not land, with its device;
    * `partial`: devices that were written, some of whose writes did not land;
    * `complete`: nothing failed at all. `ok` keeps meaning "the sync ran",
      which callers depend on; `complete` is the claim that it all landed.
    """
    whole = {d.get("hostname") for d in failed_devices}
    partial = sorted({w["device"] for w in write_failures
                      if w.get("device") and w["device"] not in whole})
    return {"failed": failed_devices, "write_failures": write_failures,
            "partial": partial,
            "complete": not failed_devices and not write_failures}


def _ensure_custom_field(session, base: str, name: str) -> bool:
    """Get-or-create one of the app's known custom field definitions.

    Returns True if the field exists (already did, or just created) and is
    therefore safe to set via `custom_fields` on object payloads; False if
    creation failed (e.g. older NetBox with a different schema) — callers
    should skip setting that custom field rather than fail the whole sync.
    """
    if name in _custom_fields_ensured:
        return True
    spec = _CUSTOM_FIELDS.get(name)
    if not spec:
        return False
    try:
        existing = _nb_first(session, base, "extras/custom-fields/", name=name)
        if not existing:
            payload = {
                "name":         name,
                "label":        spec["label"],
                "type":         spec["type"],
                "object_types": spec["object_types"],
                "description":  spec.get("description", ""),
            }
            try:
                _nb_post(session, base, "extras/custom-fields/", payload)
            except RuntimeError:
                # Older NetBox (< 4.x) used `content_types`, not `object_types`.
                payload["content_types"] = payload.pop("object_types")
                _nb_post(session, base, "extras/custom-fields/", payload)
        _custom_fields_ensured.add(name)
        return True
    except Exception as exc:
        _ensure_failed(f"custom field '{name}'", exc)
        return False


_TUNNEL_MODE_TO_ENCAP: dict = {
    "gre multipoint": "gre",
    "gre ip":         "gre",
    "gre":            "gre",
    "ipsec ipv4":     "ipsec-transport",
    "ipsec":          "ipsec-transport",
    "ip ip":          "ip-ip",
    "ipv6ip":         "other",
    "vxlan":          "vxlan",
    "l2tp":           "l2tp",
    "mpls":           "other",
}


def _tunnel_encap(tunnel_mode: str) -> str:
    """Map a Cisco tunnel mode string to a NetBox VPN encapsulation value."""
    m = (tunnel_mode or "gre ip").lower().strip()
    for prefix, encap in _TUNNEL_MODE_TO_ENCAP.items():
        if m.startswith(prefix):
            return encap
    return "gre"


def _ensure_vpn_tunnel(session, base: str, name: str,
                       encapsulation: str = "gre",
                       tunnel_id: Optional[int] = None,
                       description: str = "") -> Optional[dict]:
    """Get-or-create a NetBox VPN tunnel (NetBox 3.7+).

    Returns None gracefully if the vpn/tunnels/ endpoint is not available
    (older NetBox versions).
    """
    try:
        existing = _nb_first(session, base, "vpn/tunnels/", name=name)
        if existing:
            return existing
        payload: dict = {
            "name":          name,
            "status":        "active",
            "encapsulation": encapsulation,
        }
        if tunnel_id is not None:
            payload["tunnel_id"] = tunnel_id
        if description:
            payload["description"] = description[:200]
        return _nb_post(session, base, "vpn/tunnels/", payload)
    except Exception as exc:
        _write_failed(f"VPN tunnel {name}", exc)
        return None


def _ensure_tunnel_termination(session, base: str,
                                tunnel_nb_id: int,
                                role: str,
                                interface_id: int) -> Optional[dict]:
    """Get-or-create a VPN tunnel termination linking a tunnel to a DCIM interface."""
    try:
        existing = _nb_first(session, base, "vpn/tunnel-terminations/",
                             tunnel_id=tunnel_nb_id,
                             termination_id=interface_id)
        if existing:
            return existing
        return _nb_post(session, base, "vpn/tunnel-terminations/", {
            "tunnel":           tunnel_nb_id,
            "role":             role,
            "termination_type": "dcim.interface",
            "termination_id":   interface_id,
        })
    except Exception as exc:
        _write_failed(f"tunnel termination ({role})", exc)
        return None


def _ensure_cable(session, base: str,
                  a_type: str, a_id: int,
                  b_type: str, b_id: int, label: str = "") -> Optional[dict]:
    """Get-or-create a DCIM cable between two termination objects.

    Checks both endpoints as either side of an existing cable before
    creating one. CDP/LLDP neighbor relationships are reciprocal — both
    devices report each other — so the cable-wiring pass in
    sync_list_to_netbox processes the same physical link once from each
    direction. Checking only the "a" termination (as this used to) means
    the second, reciprocal pass sees an interface that already has a cable
    *as the b side*, misses it, and attempts a duplicate creation that
    NetBox rejects since that interface is already cabled — a silent,
    unnecessary failure logged on every sync rather than a clean no-op.
    """
    for id_ in (a_id, b_id):
        for side in ("a", "b"):
            existing = _nb_first(session, base, "dcim/cables/",
                                 **{f"termination_{side}_id": id_})
            if existing:
                return existing
    payload = {
        "a_terminations": [{"object_type": f"dcim.{a_type}", "object_id": a_id}],
        "b_terminations": [{"object_type": f"dcim.{b_type}", "object_id": b_id}],
        "status": "connected",
    }
    if label:
        # NetBox's own cable label (100 characters at most): the two ends by name, so the
        # preview, the created record and NetBox's cable list each say which link it is.
        payload["label"] = label[:100]
    try:
        return _nb_post(session, base, "dcim/cables/", payload)
    except RuntimeError as exc:
        _write_failed(f"cable {a_type}:{a_id} -> {b_type}:{b_id}", exc)
        return None


def _ensure_interface(session, base: str, device_id: int,
                      name: str, description: str = "",
                      mac: Optional[str] = None,
                      mtu: Optional[int] = None,
                      enabled: bool = True,
                      speed_mbps: Optional[int] = None,
                      vrf_id: Optional[int] = None,
                      lag_id: Optional[int] = None,
                      mode: Optional[str] = None,
                      untagged_vlan_id: Optional[int] = None,
                      tagged_vlan_ids: Optional[list] = None,
                      duplex: Optional[str] = None,
                      mgmt_only: bool = False,
                      parent_id: Optional[int] = None) -> dict:
    """Get-or-create a DCIM interface, updating physical attributes if changed.

    *parent_id*: a SUBINTERFACE's parent (C1492): the interface is `virtual`, under it."""
    existing = _nb_first(session, base, "dcim/interfaces/",
                         device_id=device_id, name=name)
    iface_type = "virtual" if parent_id else _netbox_iface_type(name)
    payload: dict = {
        "device":      device_id,
        "name":        name,
        "type":        iface_type,
        "description": (description or "")[:200],
        "enabled":     enabled,
        "mgmt_only":   mgmt_only,
    }
    if mac:
        payload["mac_address"] = mac.upper()
    if mtu:
        payload["mtu"] = mtu
    if speed_mbps:
        payload["speed"] = speed_mbps * 1000
    if vrf_id:
        payload["vrf"] = vrf_id
    if lag_id:
        payload["lag"] = lag_id
    if mode:
        payload["mode"] = mode
    if untagged_vlan_id:
        payload["untagged_vlan"] = untagged_vlan_id
    if tagged_vlan_ids:
        payload["tagged_vlans"] = tagged_vlan_ids
    if duplex:
        payload["duplex"] = duplex
    if parent_id:
        payload["parent"] = parent_id

    if existing:
        update: dict = {}
        if (existing.get("description") or "") != payload["description"]:
            update["description"] = payload["description"]
        if (existing.get("type") or {}).get("value") != iface_type:
            update["type"] = iface_type
        if mac and (existing.get("mac_address") or "").upper() != mac.upper():
            update["mac_address"] = mac.upper()
        if mtu and existing.get("mtu") != mtu:
            update["mtu"] = mtu
        if existing.get("enabled") != enabled:
            update["enabled"] = enabled
        # RAISED, NEVER LOWERED (C663 step 3). `mgmt_only` is a NetBox fact a person sets (an
        # environment's own management interface: `device_environment` reads it), so the import
        # marks what its name heuristic recognises and never clears a flag NetBox holds.
        if mgmt_only and not existing.get("mgmt_only"):
            update["mgmt_only"] = True
        if vrf_id and (existing.get("vrf") or {}).get("id") != vrf_id:
            update["vrf"] = vrf_id
        if lag_id and (existing.get("lag") or {}).get("id") != lag_id:
            update["lag"] = lag_id
        if mode and (existing.get("mode") or {}).get("value") != mode:
            update["mode"] = mode
        if untagged_vlan_id and (existing.get("untagged_vlan") or {}).get("id") != untagged_vlan_id:
            update["untagged_vlan"] = untagged_vlan_id
        if tagged_vlan_ids is not None:
            existing_tagged = [v["id"] for v in (existing.get("tagged_vlans") or [])]
            if set(existing_tagged) != set(tagged_vlan_ids):
                update["tagged_vlans"] = tagged_vlan_ids
        if duplex and (existing.get("duplex") or {}).get("value") != duplex:
            update["duplex"] = duplex
        held_parent = existing.get("parent")
        if parent_id and (held_parent.get("id") if isinstance(held_parent, dict)
                          else held_parent) != parent_id:
            update["parent"] = parent_id
        if update:
            try:
                return _nb_patch(session, base,
                                 f"dcim/interfaces/{existing['id']}/", update)
            except RuntimeError as exc:
                # The object exists; the UPDATE did not land (register C8).
                _write_failed(f"update of interface {existing.get('name', existing['id'])}", exc)
                return existing
        return existing
    return _nb_post(session, base, "dcim/interfaces/", payload)


def _say_held_by_decommissioned(session, base: str, ip: str, device_id, hostname: str) -> list:
    """Name each Decommissioning NetBox device whose interface holds *ip* (C1494), as a write
    of *hostname*'s that did not land as it should; returns the records named. One read of the
    address, and one of each other device holding it. A read that fails is said too."""
    try:
        hits = _nb_get(session, base, "ipam/ip-addresses/", address=ip)
    except Exception as exc:                           # noqa: BLE001 - said, never silent
        _write_failed(f"check of who else holds {ip}", exc, hostname)
        return []
    named = []
    for h in hits:
        if (h.get("assigned_object_type") or "") != "dcim.interface":
            continue
        assigned = h.get("assigned_object") or {}
        other = _object_id(assigned.get("device"))
        if other is None:
            iface = _nb_get_by_id(session, base, "dcim/interfaces",
                                  h.get("assigned_object_id")) or {}
            other = _object_id(iface.get("device"))
        if other is None or other == device_id:
            continue
        record = _nb_get_by_id(session, base, "dcim/devices", other) or {}
        if _status_value(record) != "decommissioning":
            continue
        name = record.get("name") or str(other)
        named.append(name)
        _write_failed(f"management address {ip}", RuntimeError(
            f"{h.get('address') or ip} is held by {name} (NetBox device {other}, "
            "Decommissioning), a record retired before retire freed its addresses (C1494); "
            "Mercury has no action that frees it yet, so unassign it from that record in "
            f"NetBox, then import {hostname} again"), hostname)
    return named


def _subinterface_parent(intf: dict) -> str:
    """The parent of a routed dot1Q subinterface (``<parent>.<n>`` carrying ``encapsulation
    dot1Q <vid>``), or "" for any other interface (C1492)."""
    name = intf.get("name") or ""
    if "." not in name or not intf.get("dot1q_tag"):
        return ""
    return name.rsplit(".", 1)[0]


def _object_id(value) -> Optional[int]:
    """An object reference's id: a nested object's, or the id itself."""
    return value.get("id") if isinstance(value, dict) else value


def _site_vlan(session, base: str, site_id, vid: int) -> tuple:
    """``(vlan, why)``: VLAN *vid* in the VLAN groups scoped to site *site_id* (C1492), exactly
    one, never another site's VLAN of the number nor one in no group; else None and why, naming
    the site's groups."""
    try:
        groups = _nb_get(session, base, "ipam/vlan-groups/", scope_type="dcim.site",
                         scope_id=site_id)
    except Exception as exc:                           # noqa: BLE001 - said by the caller
        return None, (f"VLAN groups could not be read ({exc}): Mercury's NetBox token may "
                      "have no view on ipam/vlan-groups (C1424)")
    if not groups:
        return None, f"no VLAN group is scoped to the device's site (site {site_id})"
    names = ", ".join(sorted(g.get("name") or str(g.get("id")) for g in groups))
    hits = []
    for g in groups:
        hits += [v for v in _nb_get(session, base, "ipam/vlans/", group_id=g["id"], vid=vid)
                 if str(v.get("vid")) == str(vid)]
    if len(hits) == 1:
        return hits[0], ""
    if not hits:
        return None, (f"the device's site's VLAN groups ({names}) hold no VLAN {vid}: it is "
                      "never taken from another site or from no group; add it to the site's "
                      "group, then import again")
    return None, (f"the device's site's VLAN groups ({names}) hold {len(hits)} VLANs {vid}: "
                  "none is chosen")


def _subinterface_vlan(session, base: str, nb_intf: dict, intf: dict, device: dict,
                       list_site_id, hostname: str, stats: dict) -> None:
    """Give a written subinterface its VLAN as 802.1Q tagged (C1492): its device's site's
    (`_site_vlan`, the record's own site, which an update never moves, else the list's), in a
    write of its own after the interface, so a refusal leaves the interface and its addresses
    written. Refused by name when the site's groups hold none; already so, nothing written."""
    vid = intf.get("dot1q_tag")
    site_id = _object_id((device or {}).get("site")) or list_site_id
    vlan, why = _site_vlan(session, base, site_id, vid)
    if vlan is None:
        _write_failed(f"VLAN {vid} on {intf['name']}", RuntimeError(why), hostname)
        return
    held_mode = nb_intf.get("mode")
    held_mode = held_mode.get("value") if isinstance(held_mode, dict) else held_mode
    held = sorted(_object_id(v) for v in nb_intf.get("tagged_vlans") or [])
    if held_mode == "tagged" and held == [vlan["id"]]:
        return
    try:
        _nb_patch(session, base, f"dcim/interfaces/{nb_intf['id']}/",
                  {"mode": "tagged", "tagged_vlans": [vlan["id"]]})
        stats["vlans_synced"] = stats.get("vlans_synced", 0) + 1
    except Exception as exc:                           # noqa: BLE001 - said, never silent
        _write_failed(f"VLAN {vid} on {intf['name']} (802.1Q tagged)", exc, hostname)


#: A prefix's site, as NetBox 4.2 and later take it (C1010). NetBox 4.2.0 replaced the `site`
#: foreign key on ipam.Prefix with the generic `scope` (its release notes, "Breaking Changes");
#: 4.6.9's PrefixSerializer has `scope_type` (a content type limited to region, sitegroup, site,
#: location) and `scope_id`, a read-only nested `scope`, and no `site` at all. A `site` key is not
#: refused: the serializer ignores a field it does not declare, so the create succeeded and the
#: prefix carried no site (measured on the host 2026-10-16: all 3 prefixes Mercury created).
#: Mercury therefore needs NetBox 4.2 or later for a prefix's site; on an older one the read-back
#: below names every prefix stored without it as a write that did not land.
PREFIX_SCOPE_TYPE = "dcim.site"


def _prefix_scope(site_id: Optional[int]) -> dict:
    """The fields that put a prefix at *site_id*; ``{}`` with no site. The one place a prefix's
    site is written, for every create and the backfill alike."""
    if site_id is None:
        return {}
    return {"scope_type": PREFIX_SCOPE_TYPE, "scope_id": site_id}


def _prefix_scope_backfill(existing: dict, site_id: Optional[int]) -> dict:
    """The scope an EXISTING prefix is given: the network's site, only when the prefix carries
    no scope at all and Mercury created it (`_mercury_may_edit`). A prefix a person made, or one
    already scoped (to this site or any other place), is left as it is. This is how the prefixes
    created while `site` was sent (C1010) get their site: the next import, previewed and
    confirmed like any other update, recorded with its before by `_nb_patch`."""
    if site_id is None or existing.get("scope_type") or existing.get("scope_id") is not None:
        return {}
    if not _mercury_may_edit(existing, "ipam/prefixes"):
        return {}
    return _prefix_scope(site_id)


def _check_prefix_scope(obj: dict, prefix: str, sent: dict) -> None:
    """Read back what NetBox STORED against the scope sent, and name a difference as a write that
    did not land. NetBox answers a POST or PATCH with the object as saved, so a scope it dropped
    (a NetBox before 4.2, or a field renamed again) shows here instead of passing silently, which
    is how C1010's `site` went unnoticed. A dry run's object is the payload, so it always agrees."""
    if not sent:
        return
    held = {"scope_type": obj.get("scope_type"), "scope_id": obj.get("scope_id")}
    if held != sent:
        _write_failed(
            f"site of prefix {prefix}",
            RuntimeError(f"Mercury sent scope_type={sent['scope_type']}, "
                         f"scope_id={sent['scope_id']}; NetBox stored "
                         f"scope_type={held['scope_type']}, scope_id={held['scope_id']} "
                         "(a prefix's site needs NetBox 4.2 or later)"))


def _ensure_prefix(session, base: str, prefix: str,
                   description: str = "",
                   site_id: Optional[int] = None,
                   vrf_id: Optional[int] = None,
                   role_id: Optional[int] = None) -> dict:
    """Get-or-create an IPAM prefix (network/subnet), at the network's site (C1010)."""
    params: dict = {"prefix": prefix}
    if vrf_id:
        params["vrf_id"] = vrf_id
    existing = _nb_first(session, base, "ipam/prefixes/", **params)
    if existing:
        update: dict = {}
        if role_id and (existing.get("role") or {}).get("id") != role_id:
            update["role"] = role_id
        scope = _prefix_scope_backfill(existing, site_id)
        update.update(scope)
        if update:
            try:
                obj = _nb_patch(session, base, f"ipam/prefixes/{existing['id']}/", update)
            except RuntimeError as exc:
                # The object exists; the UPDATE did not land (register C8).
                _write_failed(f"update of prefix {prefix}", exc)
                return existing
            _check_prefix_scope(obj, prefix, scope)
            return obj
        return existing
    payload: dict = {
        "prefix":      prefix,
        "status":      "active",
        "description": (description or "")[:200],
        **_prefix_scope(site_id),
    }
    if vrf_id is not None:
        payload["vrf"] = vrf_id
    if role_id is not None:
        payload["role"] = role_id
    obj = _nb_post(session, base, "ipam/prefixes/", payload)
    _check_prefix_scope(obj, prefix, _prefix_scope(site_id))
    return obj


class UnscopedAddressLookup(Exception):
    """An address lookup was attempted with no interface to scope it to."""


def excluded_vrfs() -> set:
    """VRF names whose addresses the import does not model, lowercased.

    `netbox_excluded_vrfs`, empty by default (C663: a network with an emulator's
    management VRF names it). Read at call time, so changing the setting takes
    effect without a restart.

    A read that fails RAISES, naming the setting: with an empty default there is
    no value to fall back to that keeps an exclusion the network declared, and
    excluding nothing would model the emulator's plumbing silently. The import
    names the device it was writing as failed, with this reason.
    """
    # The resolver (through `settings_schema.get_setting()`), not `config.get_user_setting()`: the
    # first falls back to the declared DEFAULT, the second reads only the
    # file and returns None for a key no install has ever written.
    try:
        # The Default network's: the sync that asks carries no list down to here yet.
        from modules.list_settings import default_layer
        raw = default_layer("netbox_excluded_vrfs")
    except Exception as exc:                    # noqa: BLE001
        raise RuntimeError(f"netbox_excluded_vrfs could not be read ({exc}), so which VRFs' "
                           "addresses to leave out is unknown; not modelling any") from exc
    if isinstance(raw, str):                    # a hand-edited file
        raw = [p for p in raw.replace(",", " ").split() if p]
    return {str(v).strip().lower() for v in (raw or []) if str(v).strip()}


def _pick_address_object(matches: list, vrf_id: Optional[int]) -> Optional[dict]:
    """Of the objects holding one address on one interface, the one to keep: already in the
    intended VRF first (so nothing changes), then one this tool tagged, then the oldest by id.
    None when there is none."""
    if not matches:
        return None

    def rank(o):
        in_vrf = vrf_id is not None and (o.get("vrf") or {}).get("id") == vrf_id
        tagged = any((t or {}).get("slug") == "nmas-managed" for t in o.get("tags") or [])
        return (not in_vrf, not tagged, o.get("id") or 0)

    return sorted(matches, key=rank)[0]


#: Why an address object is left beside the one kept (C470).
DUPLICATE_ADDRESS_WHY = ("the same address is held more than once on one interface; the sync "
                         "keeps the copy already as intended and never deletes, so remove the "
                         "other copy in NetBox (it is named, with its id)")


def _note_duplicate_address(address_cidr: str, interface_id: int, kept: dict, others: list,
                            stats: Optional[dict]) -> None:
    dev = getattr(_current_device, "name", "") or ""
    names = ", ".join(f"#{o.get('id')} (VRF {(o.get('vrf') or {}).get('name') or 'none'}"
                      f"{', untagged' if not o.get('tags') else ''})" for o in others)
    log.warning("netbox: %s%s held %d times on interface %s: kept #%s, left %s",
                f"{dev}: " if dev else "", address_cidr, 1 + len(others), interface_id,
                (kept or {}).get("id"), names)
    if stats is not None:
        _skip(stats, f"duplicate address {address_cidr}: kept #{(kept or {}).get('id')}, "
                     f"left {names}", DUPLICATE_ADDRESS_WHY, dev)


def _ensure_ip_address(session, base: str, address_cidr: str,
                       interface_id: int,
                       description: str = "",
                       vrf_id: Optional[int] = None,
                       stats: Optional[dict] = None) -> dict:
    """Get-or-create this address **on this interface**.

    **The key is the interface, not the address.** The question is *"does
    this interface already have this address"*, never *"does this address
    exist"* -- because two devices genuinely can hold the same value and
    each instance genuinely belongs to its own device. Every node an
    emulator runs may answer on one address inside its own namespace; the same is true
    behind different VRFs, and in disconnected management networks. One
    value, many interfaces, **each its own object**.

    This used to look up `{"address": cidr}` narrowed by VRF and nothing
    else, and PATCH `assigned_object_id` when the hit sat on another
    interface. Measured on the real NetBox, 2026-09-24: **one object was
    passed between six devices.** All five of the lab's routers carry the identical
    management interface, VRF and address (their emulator's), so
    each import took the object from whoever held it, leaving five routers
    with an unaddressed management interface in NetBox for weeks. Nothing
    reported it: a PATCH neither tags nor records, so the object was
    correctly classified as not NMAS's by both provenance tests, and the
    theft was invisible to every guard because **provenance protects an
    object and this moved a relationship.**

    **VRF narrowing was never the fix**, though it reads like one: r3's
    address is in the emulator's management VRF and so is every other router's, so passing the
    VRF selects the same object.

    The scope used here is the one `_upsert_device`'s `primary_ip4` fallback
    has always used on the read side (`if iface_id in nb_iface_map.values()`)
    -- careful in the place where being wrong picked a wrong primary IP,
    absent from the place where being wrong moved another device's address.

    An address that moves from one interface to another leaves the old
    object where it was. That is not a new class of stale record: **this
    importer never deletes anything**, so an address removed from a config
    already leaves one. A move now behaves like a removal.

    Raises `UnscopedAddressLookup` when `interface_id` is missing, rather
    than falling back to an address-wide match -- the fallback *is* the
    defect, and a caller with no interface has no business claiming an
    address.
    """
    if not interface_id:
        raise UnscopedAddressLookup(
            f"no interface to scope the lookup for {address_cidr} — refusing "
            "to match by address alone")

    # Scoped to the interface, then matched by value in Python: the answer
    # is a handful of rows, and it does not depend on NetBox accepting a
    # particular combination of filter names.
    matches = [obj for obj in _nb_get(session, base, "ipam/ip-addresses/",
                                      interface_id=interface_id)
               if _same_address(obj.get("address"), address_cidr)]
    existing = _pick_address_object(matches, vrf_id)
    if len(matches) > 1:
        # The sync that never settled (C470, 2026-10-05): s1, s2 and s3 each held ONE
        # address twice on one interface (an untagged 2026-08-28 copy with no VRF, and the
        # sync's own copy in VRF Default). Taking the FIRST, the untagged one, the sync asked
        # every run to move it into VRF Default, and NetBox refused it as a duplicate there.
        # Now the copy already as intended is taken, so nothing changes, and the others are
        # NAMED: the importer never deletes, so a person removes them.
        others = [o for o in matches if o is not existing]
        _note_duplicate_address(address_cidr, interface_id, existing, others, stats)

    payload: dict = {
        "address":              address_cidr,
        "status":               "active",
        "description":          (description or "")[:200],
        "assigned_object_type": "dcim.interface",
        "assigned_object_id":   interface_id,
    }
    if vrf_id is not None:
        payload["vrf"] = vrf_id
    if existing:
        # It is already on this interface, so nothing here can move it off
        # another one. Only the description and the VRF can differ.
        needs_update = (
            existing.get("description") != payload["description"]
            or (vrf_id is not None
                and (existing.get("vrf") or {}).get("id") != vrf_id)
        )
        if needs_update:
            try:
                return _nb_patch(session, base,
                                 f"ipam/ip-addresses/{existing['id']}/",
                                 payload)
            except RuntimeError as exc:
                # The object exists; the UPDATE did not land (register C8).
                _write_failed(f"update of IP {address_cidr}", exc)
                return existing
        return existing
    return _nb_post(session, base, "ipam/ip-addresses/", payload)


def _same_address(a: Optional[str], b: Optional[str]) -> bool:
    """Compare two CIDR strings as addresses, not as text.

    `2001:DB8::2/64` and `2001:db8::2/64` are one address; NetBox
    normalises case on write and a config does not.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        return ipaddress.ip_interface(a) == ipaddress.ip_interface(b)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Device-fact collection via SSH
# ---------------------------------------------------------------------------

# show ip interface parsing — walks per-interface stanzas looking for
# "<Interface> is up/down" header and a "Internet address is X.X.X.X/NN" line.
_RE_IFACE_HEADER = re.compile(
    r"^(\S[\w\-/.:]*)\s+is\s+(?:administratively\s+)?(?:up|down)",
    re.MULTILINE,
)
_RE_INET_CIDR    = re.compile(
    r"Internet address is\s+(\d+\.\d+\.\d+\.\d+)/(\d+)",
    re.IGNORECASE,
)
_RE_DESCR        = re.compile(r"^\s*Description:\s*(.+?)\s*$", re.MULTILINE)


def _parse_ip_interfaces(show_ip_interface: str) -> list[dict]:
    """Parse `show ip interface` output into [{name, cidr, description}].

    Returns only interfaces that actually have an IPv4 address assigned.
    """
    if not show_ip_interface:
        return []

    # Split into per-interface blocks by locating header lines.
    results: list[dict] = []
    headers = list(_RE_IFACE_HEADER.finditer(show_ip_interface))
    for idx, hdr in enumerate(headers):
        start = hdr.start()
        end   = headers[idx + 1].start() if idx + 1 < len(headers) else len(show_ip_interface)
        block = show_ip_interface[start:end]
        name  = hdr.group(1)

        m = _RE_INET_CIDR.search(block)
        if not m:
            continue
        ip_str = m.group(1)
        mask_bits = int(m.group(2))
        if not (0 < mask_bits <= 32):
            continue
        try:
            addr = ipaddress.ip_interface(f"{ip_str}/{mask_bits}")
        except ValueError:
            continue

        desc_m = _RE_DESCR.search(block)
        results.append({
            "name":        name,
            "cidr":        str(addr),                           # e.g. 10.0.0.1/24
            "prefix":      str(addr.network),                   # e.g. 10.0.0.0/24
            "description": desc_m.group(1) if desc_m else "",
        })
    return results


# ---------------------------------------------------------------------------
# show interfaces parsing — MAC, MTU, speed/bandwidth, oper/admin state
# ---------------------------------------------------------------------------
_RE_SHIF_HEADER  = re.compile(
    r"^(\S[\w\-/.:]+) is (up|down|administratively down|deleted)", re.MULTILINE
)
_RE_SHIF_LINE_PROTO = re.compile(r"line protocol is (up|down)", re.IGNORECASE)
_RE_SHIF_DESCR   = re.compile(r"^\s+Description:\s*(.+)$", re.MULTILINE)
_RE_SHIF_MAC     = re.compile(
    r"(?:Hardware is.*?,|address is)\s+([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})",
    re.IGNORECASE,
)
_RE_SHIF_BW      = re.compile(r"BW (\d+) Kbit", re.IGNORECASE)
_RE_SHIF_MTU     = re.compile(r"MTU (\d+) bytes", re.IGNORECASE)
_RE_SHIF_SPEED   = re.compile(r"\b(\d+)Mb/s\b", re.IGNORECASE)


def _parse_interfaces_detail(output: str) -> list[dict]:
    """Parse `show interfaces` → [{name, mac, mtu, bandwidth_kbps, speed_mbps,
                                     admin_up, oper_up, description}].
    All fields optional — keys always present, values may be None/empty.
    """
    if not output:
        return []
    results: list[dict] = []
    headers = list(_RE_SHIF_HEADER.finditer(output))
    for idx, hdr in enumerate(headers):
        start = hdr.start()
        end   = headers[idx + 1].start() if idx + 1 < len(headers) else len(output)
        block = output[start:end]
        name  = hdr.group(1)
        admin_state = hdr.group(2)   # "up" | "down" | "administratively down"
        admin_up    = "administratively" not in admin_state and admin_state != "deleted"
        lp_m        = _RE_SHIF_LINE_PROTO.search(block)
        oper_up     = (lp_m.group(1) == "up") if lp_m else admin_up

        mac_m   = _RE_SHIF_MAC.search(block)
        bw_m    = _RE_SHIF_BW.search(block)
        mtu_m   = _RE_SHIF_MTU.search(block)
        spd_m   = _RE_SHIF_SPEED.search(block)
        desc_m  = _RE_SHIF_DESCR.search(block)

        # Normalise Cisco dotted-hex MAC → colon notation
        raw_mac = mac_m.group(1) if mac_m else None
        if raw_mac:
            parts = raw_mac.replace(".", "")
            raw_mac = ":".join(parts[i:i+2] for i in range(0, 12, 2)).upper()

        results.append({
            "name":          name,
            "mac":           raw_mac,
            "mtu":           int(mtu_m.group(1)) if mtu_m else None,
            "bandwidth_kbps": int(bw_m.group(1)) if bw_m else None,
            "speed_mbps":    int(spd_m.group(1)) if spd_m else None,
            "admin_up":      admin_up,
            "oper_up":       oper_up,
            "description":   desc_m.group(1).strip() if desc_m else "",
        })
    return results


# ---------------------------------------------------------------------------
# show vrf parsing
# ---------------------------------------------------------------------------
_RE_VRF_ROW = re.compile(
    r"^\s*(\S+)\s+(\S+)\s+<(\S+)>\s+(\S+)", re.MULTILINE
)
_RE_VRF_SIMPLE = re.compile(r"^\s*(\S+)\s+(\S+|\<not set\>)", re.MULTILINE)


def _parse_vrfs(output: str) -> list[dict]:
    """Parse `show vrf` → [{name, rd}].  RD may be empty."""
    if not output:
        return []
    results: list[dict] = []
    seen: set = set()
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name") or line.lower().startswith("vrf"):
            continue
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        if name.lower() in ("management", "mgmt", "mgmt-vrf", "name", "vrf"):
            continue
        rd = parts[1] if len(parts) > 1 and parts[1] != "<not" else ""
        if name not in seen:
            seen.add(name)
            results.append({"name": name, "rd": rd if rd != "<not" else ""})
    return results


# ---------------------------------------------------------------------------
# show vlan brief parsing
# ---------------------------------------------------------------------------
_RE_VLAN_ROW = re.compile(
    r"^(\d+)\s+([\w\-\.]+)\s+(active|act|act/unsup|suspended|sus)\s*([\w,/\s]*)?$",
    re.MULTILINE | re.IGNORECASE,
)


def _parse_vlans(output: str) -> list[dict]:
    """Parse `show vlan brief` → [{vlan_id, name, ports}]."""
    if not output:
        return []
    results: list[dict] = []
    for m in _RE_VLAN_ROW.finditer(output):
        vid = int(m.group(1))
        if vid in (1002, 1003, 1004, 1005):  # Cisco internal VLANs
            continue
        ports_raw = (m.group(4) or "").strip()
        ports = [p.strip() for p in ports_raw.split(",") if p.strip()] if ports_raw else []
        results.append({
            "vlan_id": vid,
            "name":    m.group(2),
            "ports":   ports,
        })
    return results


def _expand_vlan_list(vlan_str: str) -> list:
    """Expand a Cisco VLAN range string like '10,20-25,30' into a flat list of ints."""
    vlans: list = []
    for part in vlan_str.replace(" ", "").split(","):
        if "-" in part:
            try:
                lo, hi = part.split("-", 1)
                vlans.extend(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        elif part.isdigit():
            vlans.append(int(part))
    return vlans


# ---------------------------------------------------------------------------
# show cdp neighbors detail parsing
# ---------------------------------------------------------------------------
_RE_CDP_ENTRY      = re.compile(r"^-{5,}", re.MULTILINE)
_RE_CDP_DEVICE_ID  = re.compile(r"^Device ID:\s*(\S+)", re.MULTILINE)
_RE_CDP_LOCAL_INTF = re.compile(r"Interface:\s*(\S+),", re.MULTILINE)
_RE_CDP_PORT_ID    = re.compile(r"Port ID \(outgoing port\):\s*(\S+)", re.MULTILINE | re.IGNORECASE)
_RE_CDP_IP         = re.compile(r"IP(?:v4)? [Aa]ddress:\s*(\d+\.\d+\.\d+\.\d+)", re.MULTILINE)
_RE_CDP_PLATFORM   = re.compile(r"Platform:\s*([^,]+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# show lldp neighbors detail parsing
# ---------------------------------------------------------------------------
_RE_LLDP_ENTRY      = re.compile(r"^-{5,}", re.MULTILINE)
_RE_LLDP_SYSNAME    = re.compile(r"^System Name:\s*(\S+)", re.MULTILINE)
_RE_LLDP_LOCAL_INTF = re.compile(r"^Local Intf:\s*(\S+)", re.MULTILINE)
_RE_LLDP_PORT_ID    = re.compile(r"^Port id:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
_RE_LLDP_IP         = re.compile(r"^\s*IP:\s*(\d+\.\d+\.\d+\.\d+)", re.MULTILINE)
_RE_LLDP_SYSDESC    = re.compile(r"System Description:\s*\n\s*(.+)", re.MULTILINE)


def _parse_lldp_neighbors(output: str) -> list[dict]:
    """Parse `show lldp neighbors detail` → the same shape as
    _parse_cdp_neighbors: [{local_iface, remote_hostname, remote_iface,
    remote_ip, remote_platform}], so both can feed the same cable-wiring
    pass in sync_list_to_netbox — a link reported by both protocols on the
    same interface pair is deduplicated there via _ensure_cable's dedup
    check, same as topology.py's build_topology does for the topology tab.

    A neighbor with no System Name TLV (chassis ID / MAC only) is skipped —
    not useful for matching against this app's hostname-keyed device list,
    same as CDP entries with no Device ID are skipped.
    """
    if not output:
        return []
    results: list[dict] = []
    chunks = _RE_LLDP_ENTRY.split(output)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        sys_m  = _RE_LLDP_SYSNAME.search(chunk)
        loc_m  = _RE_LLDP_LOCAL_INTF.search(chunk)
        port_m = _RE_LLDP_PORT_ID.search(chunk)
        if not (sys_m and loc_m and port_m):
            continue
        ip_m   = _RE_LLDP_IP.search(chunk)
        desc_m = _RE_LLDP_SYSDESC.search(chunk)
        results.append({
            "local_iface":      loc_m.group(1),
            "remote_hostname":  sys_m.group(1).split(".")[0],  # strip domain
            "remote_iface":     port_m.group(1),
            "remote_ip":        ip_m.group(1) if ip_m else "",
            "remote_platform":  (desc_m.group(1).strip()[:80] if desc_m else ""),
        })
    return results


def _parse_cdp_neighbors(output: str) -> list[dict]:
    """Parse `show cdp neighbors detail` → [{local_iface, remote_hostname,
       remote_iface, remote_ip, remote_platform}]."""
    if not output:
        return []
    results: list[dict] = []
    # Split on separator lines (----------------)
    chunks = _RE_CDP_ENTRY.split(output)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        dev_m  = _RE_CDP_DEVICE_ID.search(chunk)
        loc_m  = _RE_CDP_LOCAL_INTF.search(chunk)
        port_m = _RE_CDP_PORT_ID.search(chunk)
        if not (dev_m and loc_m and port_m):
            continue
        ip_m   = _RE_CDP_IP.search(chunk)
        plat_m = _RE_CDP_PLATFORM.search(chunk)
        results.append({
            "local_iface":      loc_m.group(1),
            "remote_hostname":  dev_m.group(1).split(".")[0],  # strip domain
            "remote_iface":     port_m.group(1),
            "remote_ip":        ip_m.group(1) if ip_m else "",
            "remote_platform":  (plat_m.group(1).strip() if plat_m else ""),
        })
    return results


# ---------------------------------------------------------------------------
# show ip interface brief — used for quick oper-status snapshot
# ---------------------------------------------------------------------------
_RE_IP_BRIEF = re.compile(
    r"^(\S+)\s+(\d+\.\d+\.\d+\.\d+|unassigned)\s+\S+\s+\S+\s+(up|down|administratively down)",
    re.MULTILINE | re.IGNORECASE,
)


def _parse_ip_brief(output: str) -> dict:
    """Parse `show ip interface brief` → {iface_name: oper_state}."""
    result: dict = {}
    for m in _RE_IP_BRIEF.finditer(output or ""):
        result[m.group(1)] = m.group(3).lower()
    return result


# show version parsing — Cisco IOS / IOS-XE / NX-OS friendly patterns.
_RE_HOSTNAME_CMD  = re.compile(r"^\s*([A-Za-z0-9][\w\-.]*)[#>]", re.MULTILINE)
_RE_IOS_VERSION   = re.compile(r"(?:IOS(?:-XE)?\s+Software.*?Version\s+([\w\.\(\)-]+))", re.IGNORECASE | re.DOTALL)
_RE_NXOS_VERSION  = re.compile(r"^\s*system:\s*version\s+(\S+)", re.IGNORECASE | re.MULTILINE)
_RE_IOS_MODEL     = re.compile(
    r"^\s*[Cc]isco\s+(\S+)\s+.*?(?:processor|with|\(revision)",
    re.MULTILINE,
)
_RE_PROCESSOR_SN  = re.compile(r"[Pp]rocessor (?:board )?ID\s+(\S+)")
_RE_CHASSIS_SN    = re.compile(r"Chassis Serial Number\s*:\s*(\S+)", re.IGNORECASE)
_RE_INV_PID       = re.compile(r'^\s*NAME:\s*"Chassis".*?PID:\s*(\S+)', re.MULTILINE | re.DOTALL)
_RE_INV_SN        = re.compile(r'^\s*NAME:\s*"Chassis".*?SN:\s*(\S+)', re.MULTILINE | re.DOTALL)
_RE_ANY_PID       = re.compile(r'^\s*PID:\s*(\S+)', re.MULTILINE)
_RE_ANY_SN        = re.compile(r'\bSN:\s*(\S+)')


def _parse_device_facts(show_version: str, show_inventory: str) -> dict:
    """Extract vendor/model/serial/version fields from CLI output."""
    facts = {
        "manufacturer": "Cisco",   # all supported device_types are Cisco-flavored
        "model":        "",
        "serial":       "",
        "version":      "",
        "platform":     "",
    }

    if show_version:
        m = _RE_IOS_VERSION.search(show_version)
        if m:
            facts["version"] = m.group(1).strip(",")
            facts["platform"] = "IOS-XE" if "IOS-XE" in show_version or "IOS XE" in show_version else "IOS"
        else:
            m = _RE_NXOS_VERSION.search(show_version)
            if m:
                facts["version"]  = m.group(1)
                facts["platform"] = "NX-OS"

        m = _RE_IOS_MODEL.search(show_version)
        if m:
            facts["model"] = m.group(1)

        m = _RE_PROCESSOR_SN.search(show_version) or _RE_CHASSIS_SN.search(show_version)
        if m:
            facts["serial"] = m.group(1)

    if show_inventory:
        # Prefer the Chassis entry when present.
        m = _RE_INV_PID.search(show_inventory)
        if m:
            facts["model"] = facts["model"] or m.group(1)
        m = _RE_INV_SN.search(show_inventory)
        if m:
            facts["serial"] = facts["serial"] or m.group(1)
        # Fall back to first PID/SN lines in the inventory output.
        if not facts["model"]:
            m = _RE_ANY_PID.search(show_inventory)
            if m:
                facts["model"] = m.group(1)
        if not facts["serial"]:
            m = _RE_ANY_SN.search(show_inventory)
            if m:
                facts["serial"] = m.group(1)

    # Sensible fallback so the device-type entry in NetBox still has a name.
    if not facts["model"]:
        facts["model"] = "Unknown"
    return facts


# `_scan_device()` lived here: 140 lines that opened an SSH session, ran
# `show version` / `show inventory` / `show ip interface brief` and returned
# facts for the NetBox sync. **Nothing called it.** The sync is driven by
# `_scan_device_from_golden()` instead, deliberately -- a golden config works
# for a device that is offline, and importing observed state into the source
# of truth is the wrong direction. Refreshing a golden and re-importing is one
# store and one direction.
#
# Removed in Stage 3.3. Its absence is pinned by
# `tests/test_tab_descriptions_are_true.py`; restoring it means answering why
# NetBox import should depend on device reachability.


def _fetch_neighbors_live(dev: dict) -> list[dict]:
    """Best-effort live fetch of CDP + LLDP neighbors for cable-sync
    enrichment.

    Only called for devices status_cache already reports online — neighbor
    data is learned operational state, not something that exists in a golden
    config, so this is the one piece of the sync that genuinely needs a live
    session even though the rest works from saved configs. A link both
    protocols report on the same interface pair is naturally deduplicated by
    _ensure_cable's existing get-or-create lookup in the cable-wiring pass.
    Returns [] on any failure; never raises — a device that can't be reached
    just doesn't get its cables synced this run, same as it already doesn't
    today.

    Uses conn.send_command directly (not modules.commands.run_device_command)
    — matching topology.py's gather_device_topology, which discovers this
    exact same data reliably. (run_device_command's retry-to-timing fallback,
    which this note used to describe, is gone: C272 sends each command once
    and never re-sends it on its session.) A confused read here fails closed
    (empty string) rather than
    raising, so it wouldn't show up as a sync error — it would just mean
    silently discovering fewer neighbors than the device actually has.
    """
    from modules.connection import get_persistent_connection

    ip = dev.get("ip", "")
    neighbors: list[dict] = []
    try:
        priv_pool: dict = {}
        priv_lock = threading.Lock()
        conn = get_persistent_connection(dev, priv_pool, priv_lock)
        show_cdp = conn.send_command("show cdp neighbors detail", read_timeout=30) or ""
        neighbors.extend(_parse_cdp_neighbors(show_cdp))
        show_lldp = conn.send_command("show lldp neighbors detail", read_timeout=30) or ""
        neighbors.extend(_parse_lldp_neighbors(show_lldp))
    except Exception as exc:
        log.debug("netbox: live neighbor fetch failed for %s: %s", ip, exc)
    return neighbors


# ---------------------------------------------------------------------------
# Running-config interface parser (fallback when show ip interface is incomplete)
# ---------------------------------------------------------------------------

_RE_RC_IFACE_BLOCK = re.compile(
    r"^interface\s+(\S+)(.*?)(?=^interface\s|\Z)", re.MULTILINE | re.DOTALL
)
_RE_RC_IP_ADDR = re.compile(
    r"^\s+ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)",
    re.MULTILINE,
)
_RE_RC_DESCR   = re.compile(r"^\s+description\s+(.+)$", re.MULTILINE)
_RE_RC_SHUTDOWN = re.compile(r"^\s+shutdown\b", re.MULTILINE)


def _parse_interfaces_from_running_config(config: str) -> list[dict]:
    """Extract interface IPs (CIDR) and descriptions from a running-config.

    Used as a supplement when 'show ip interface' times out or returns
    partial output.  Returns only interfaces that have an 'ip address' line.
    Each entry: {name, cidr, prefix, description, admin_up}.
    """
    if not config:
        return []
    results: list[dict] = []
    for m in _RE_RC_IFACE_BLOCK.finditer(config):
        name = m.group(1)
        body = m.group(2)

        ip_m = _RE_RC_IP_ADDR.search(body)
        if not ip_m:
            continue
        try:
            net  = ipaddress.IPv4Network(
                f"{ip_m.group(1)}/{ip_m.group(2)}", strict=False
            )
            addr = ipaddress.ip_interface(f"{ip_m.group(1)}/{net.prefixlen}")
        except ValueError:
            continue

        desc_m   = _RE_RC_DESCR.search(body)
        shutdown = bool(_RE_RC_SHUTDOWN.search(body))
        results.append({
            "name":        name,
            "cidr":        str(addr),
            "prefix":      str(addr.network),
            "description": desc_m.group(1).strip() if desc_m else "",
            "admin_up":    not shutdown,
        })
    return results


# ---------------------------------------------------------------------------
# Config context builder
# ---------------------------------------------------------------------------

# Regex patterns for extracting structured sections from running config
_RE_CFG_IFACE_BLOCK = re.compile(
    r"^(interface\s+\S+.*?)(?=^interface\s|\Z)", re.MULTILINE | re.DOTALL
)
_RE_CFG_ROUTER_BLOCK = re.compile(
    r"^(router\s+\S+.*?)(?=^router\s|^interface\s|\Z)", re.MULTILINE | re.DOTALL
)
_RE_CFG_HOSTNAME = re.compile(r"^hostname\s+(\S+)", re.MULTILINE)
_RE_CFG_BANNER   = re.compile(
    r"^banner\s+\w+\s+\^C.*?\^C", re.MULTILINE | re.DOTALL
)
def _sanitise_config(raw: str) -> str:
    """Mask a running config on its way INTO NetBox (register C95 (a)).

    NetBox is not a deploy source and nobody restores a network from its copy,
    so it is masked at rest, like the modification record (section 13), and
    unlike `golden/`, which must restore a network. This had four private
    patterns of its own, a SECOND redactor, and they missed the fleet: the
    username pattern expected `username <name> secret ...` while every device
    says `username admin privilege 15 secret 9 ...`, and nothing matched
    `snmp-server community`. Measured on the host 2026-09-28: 2 credential-slot
    lines unmasked on every device, in NetBox since the first import. One
    redactor now, `redact.redact_text` (positional AND by known value), the
    one measured at 0 unmasked lines across the fleet."""
    from modules.redact import redact_text

    return redact_text(_RE_CFG_BANNER.sub("banner motd ^C[REMOVED]^C", raw))


def masked_context(ctx: dict) -> dict:
    """A STORED `local_context_data` as the import writes it now (C95 (a)):
    the running config through the one redactor, and the structured SNMP
    communities without their value, every other key untouched.

    For a context no import will reach again (C139: a retired device keeps its
    NetBox record, so the re-import that masked the fleet never touched it).
    Only for a RAW context: `redact_text` is not idempotent over text it
    already masked (it falls back to the next token), so a caller refuses a
    context holding a mask rather than masking it twice."""
    out = dict(ctx or {})
    if out.get("running_config"):
        out["running_config"] = _sanitise_config(out["running_config"])
    snmp = out.get("snmp")
    if isinstance(snmp, dict) and isinstance(snmp.get("communities"), list):
        out["snmp"] = {**snmp, "communities": [
            {k: v for k, v in c.items() if k != "community"} if isinstance(c, dict) else c
            for c in snmp["communities"]]}
    return out


def _build_config_context(hostname: str, ip: str, facts: dict,
                           interfaces: list[dict],
                           vlans: list, vrfs: list,
                           running_config: str,
                           routing_context: Optional[dict] = None) -> dict:
    """Build the JSON payload for NetBox device local_context_data.

    Stores structured extracted data plus the sanitised full running config.
    """
    # NO SYNC TIMESTAMP HERE. It was `"ndm_sync": time.strftime(...)`, which
    # made this field differ on EVERY sync by construction — so the
    # modification record logged a change for every device, every sync, for
    # ever, and `local_context_data`'s hash moved with it.
    #
    # Two reasons, and the second is the stronger. Noise: a log whose every
    # entry reads "the sync ran" teaches the reader to skip it, which is the
    # record's own "somebody turns it off" reached by count instead of bytes,
    # and the next false `offline` goes past unread. And **NetBox already owns
    # this fact** — every object carries `last_updated` — so this was a second
    # copy of somebody else's field. Removing it drops a duplicate rather than
    # losing information, which is the two-owners rule, not a noise fix.
    ctx: dict = {
        "mgmt_ip":        ip,
        "platform":       facts.get("platform", ""),
        "os_version":     facts.get("version", ""),
        "serial":         facts.get("serial", ""),
        "model":          facts.get("model", ""),
    }

    # Structured interface summary (IP interfaces only to keep size manageable)
    ip_ifaces = [i for i in interfaces if i.get("cidr")]
    if ip_ifaces:
        ctx["ip_interfaces"] = [
            {
                "name":    i["name"],
                "address": i["cidr"],
                "vrf":     i.get("vrf_name", "") or "",
                "enabled": i.get("admin_up", True),
            }
            for i in ip_ifaces
        ]

    if vrfs:
        ctx["vrfs"] = [{"name": v["name"], "rd": v.get("rd", "")} for v in vrfs]

    if vlans:
        ctx["vlans"] = [{"id": v["vlan_id"], "name": v["name"]} for v in vlans]

    # Structured routing data (OSPF, BGP, NTP, SNMP) from golden-config parsers
    if routing_context:
        ctx.update(routing_context)

    if running_config:
        ctx["running_config"] = _sanitise_config(running_config)

    return ctx


# ---------------------------------------------------------------------------
# Config Template (NetBox 3.5+ extras/config-templates)
# ---------------------------------------------------------------------------

# Jinja2 template stored in NetBox that renders against local_context_data.
# Variables match what _build_config_context() puts in local_context_data.
_NDM_TEMPLATE_NAME = "NDM Running Config"
_NDM_TEMPLATE_CODE = """\
! ============================================================
! Device : {{ model | default('unknown') }}
! Platform: {{ platform | default('unknown') }}  Version: {{ os_version | default('unknown') }}
! Serial  : {{ serial | default('N/A') }}
! Mgmt IP : {{ mgmt_ip | default('') }}
! ============================================================
{% if running_config is defined and running_config %}
{{ running_config }}
{% else %}
! No running configuration was captured during the last sync.
{% endif %}
""".rstrip("\n")
# ^ NETBOX STRIPS A TRAILING NEWLINE ON WRITE, so the constant is defined as
# what NetBox will actually store rather than as what the literal produces.
#
# Measured: NMAS sent 521 bytes (JSON-serialised) and read back 519 — one
# newline, which is two characters once escaped. `_ensure_config_template`
# already guards its PATCH on `existing != _NDM_TEMPLATE_CODE`, so the guard
# was **permanently true** and the template was rewritten on every sync since
# it was introduced, each time recorded as a change that had not happened.
# A guard that can never be satisfied is worse than no guard, because it makes
# the write look considered.
#
# Deliberately NOT `.strip()` on both sides of the comparison: that would
# paper over any other normalisation NetBox applies, and the point of the
# modification record is that such a thing shows up. Fix the discrepancy that
# was measured; let the record reveal the next one.


def _ensure_config_template(session: requests.Session, base: str) -> Optional[int]:
    """Get-or-create the NDM config template in NetBox.

    Returns the template id, or None if the NetBox version doesn't support
    config-templates (pre-3.5) or if the endpoint fails for any reason.
    """
    try:
        existing = _nb_first(session, base, "extras/config-templates/",
                             name=_NDM_TEMPLATE_NAME)
        if existing:
            # Keep the template code current
            if existing.get("template_code") != _NDM_TEMPLATE_CODE:
                _nb_patch(session, base,
                          f"extras/config-templates/{existing['id']}/",
                          {"template_code": _NDM_TEMPLATE_CODE})
            return existing["id"]

        result = _nb_post(session, base, "extras/config-templates/", {
            "name":           _NDM_TEMPLATE_NAME,
            "description":    "Renders device running config from NDM local_context_data.",
            "template_code":  _NDM_TEMPLATE_CODE,
            "mime_type":      "text/plain",
            "file_extension": "txt",
        })
        log.info("netbox: created config template '%s' (id=%s)",
                 _NDM_TEMPLATE_NAME, result.get("id"))
        return result["id"]
    except Exception as exc:
        # Recorded (register C8): the template is how NetBox renders a
        # device's config, and "skipping" at DEBUG said nothing anywhere.
        _ensure_failed("the config template", exc)
        return None


# ---------------------------------------------------------------------------
# NetBox device upsert
# ---------------------------------------------------------------------------

def _status_value(obj: dict) -> str:
    """A NetBox object's status as its value (``active``, ``decommissioning``), whether NetBox
    answered it as ``{"value", "label"}`` or as the bare value."""
    status = (obj or {}).get("status")
    return (status.get("value") if isinstance(status, dict) else status) or ""


def _existing_device(session, base: str, hostname: str, site_id, serial: str,
                     sharing=None) -> Optional[dict]:
    """The NetBox device this sync updates: by serial only when the serial is UNIQUE, else by
    name and site.

    A serial is never assumed unique (the operator, 2026-10-04: every C8000v of one virtual
    image reports the same serial). Matching r2 by a serial r1 also reports would rename r1's
    record to r2 and overwrite its context, and five devices would collapse into one. So the
    serial is used only when exactly one NetBox device holds it AND no other device the tool
    manages reports it (*sharing*: ``[(list, device)]``, `device_serials.devices_with`);
    otherwise the match is by name, and the refusal is logged naming the devices."""
    if serial:
        from modules import device_serials

        sharing = device_serials.devices_with(serial) if sharing is None else sharing
        others = sorted({d for _l, d in sharing if d and d != hostname})
        # A record set to Decommissioning is a device that left (retire sets it, C1342): a new
        # device reporting its serial (the same machine onboarded again) gets a NEW record.
        held = [d for d in _nb_get(session, base, "dcim/devices/", serial=serial) or []
                if _status_value(d) != "decommissioning"]
        if others or len(held) > 1:
            log.warning("netbox: %s not matched by serial %s: also reported by %s%s; matched "
                        "by name", hostname, serial, ", ".join(others) or "no other device",
                        f", and {len(held)} NetBox devices hold it" if len(held) > 1 else "")
        elif held:
            return held[0]
    return _nb_first(session, base, "dcim/devices/", name=hostname, site_id=site_id)


def _record_by_id(session, base: str, hostname: str, netbox_id) -> dict:
    """The NetBox record a caller named by id (C676: onboarding's Planned record). It must
    still exist and still carry this name; otherwise nothing is written, both named."""
    held = _nb_get(session, base, "dcim/devices/", id=netbox_id) or []
    if not held:
        raise RuntimeError(f"NetBox record {netbox_id}, read as {hostname}'s at onboarding, no "
                           "longer exists: nothing was written")
    if held[0].get("name") != hostname:
        raise RuntimeError(f"NetBox record {netbox_id} was {hostname}'s at onboarding and is "
                           f"now named {held[0].get('name')!r}: nothing was written")
    return held[0]


def _upsert_device(session, base: str, hostname: str, ip: str, facts: dict,
                   interfaces: list[dict],
                   site_id: int, role_id: int,
                   ipam_stats: dict,
                   vlans: Optional[list] = None,
                   vrfs: Optional[list] = None,
                   running_config: str = "",
                   config_template_id: Optional[int] = None,
                   static_routes: Optional[list] = None,
                   protocol_tags: Optional[list] = None,
                   routing_context: Optional[dict] = None,
                   list_vrf_id: Optional[int] = None,
                   status: str = "active",
                   mgmt_prefix_len: int = 0,
                   netbox_id: Optional[int] = None,
                   dialect: str = "") -> dict:
    """Create or update a device in NetBox with full DCIM + IPAM data.

    Syncs: device record, platform, interfaces (with MAC/MTU/speed/state),
    VRFs, VLANs, IPAM prefixes, IP addresses (VRF-aware), primary_ip4/6,
    and local_context_data (sanitised running config + structured facts).
    `ipam_stats` is mutated in place with running counts.
    Returns {"action", "id", "name", "data", "nb_iface_map"}.
    """
    manuf    = _ensure_manufacturer(session, base, facts.get("manufacturer") or "Cisco")
    dev_type = _ensure_device_type(session, base, facts.get("model") or "Unknown", manuf["id"])

    # Platform (OS): a created record's only (an update never sets it, below). The platform
    # NetBox holds under a slug naming the device's dialect first (C1442: the fleet's records
    # read "Cisco IOS XE", slug cisco-ios-xe, while the text's own "IOS-XE" made a second
    # platform and a ZTP router was given "IOS"); the text's name only when NetBox holds none.
    platform_id: Optional[int] = None
    if facts.get("platform") or dialect:
        try:
            plat = _platform_for(session, base, facts.get("platform") or "", dialect,
                                 manuf["id"])
            platform_id = plat["id"] if plat else None
        except Exception as exc:
            _write_failed(f"platform {facts.get('platform') or dialect}", exc, hostname)

    # VRFs (IPAM) — build a name→id map used when assigning IPs later
    vrf_id_map: dict = {}
    for vrf in (vrfs or []):
        try:
            nb_vrf = _ensure_vrf(session, base, vrf["name"], vrf.get("rd", ""))
            vrf_id_map[vrf["name"]] = nb_vrf["id"]
            ipam_stats["vrfs_synced"] = ipam_stats.get("vrfs_synced", 0) + 1
        except Exception as exc:
            _write_failed(f"VRF {vrf['name']}", exc, hostname)

    # VLANs
    for vlan in (vlans or []):
        try:
            _ensure_vlan(session, base, vlan["vlan_id"], vlan["name"], site_id)
            ipam_stats["vlans_synced"] = ipam_stats.get("vlans_synced", 0) + 1
        except Exception as exc:
            _write_failed(f"VLAN {vlan.get('vlan_id')}", exc, hostname)

    # Build device payload
    # Match by serial number first when we have one — it's the actual stable
    # hardware identifier (survives a hostname rename), falling back to
    # name+site so devices with no readable serial still upsert correctly
    # instead of silently creating a duplicate.
    serial = (facts.get("serial") or "")[:50]
    if netbox_id:
        existing = _record_by_id(session, base, hostname, netbox_id)
    else:
        existing = _existing_device(session, base, hostname, site_id, serial)

    # NO `Synced: <timestamp>`. Same reasoning as `ndm_sync` in
    # _build_config_context: it made `comments` differ on every sync by
    # construction, and NetBox's own `last_updated` already carries when the
    # object was written. What remains changes when the platform, the version
    # or the management address changes — which is a fact somebody would want
    # to see change.
    comments = (
        f"Platform: {facts.get('platform') or 'unknown'}  |  "
        f"Version: {facts.get('version') or 'unknown'}  |  "
        f"Mgmt IP: {ip}"
    )

    # Build config context (sanitised running config + structured facts + routing)
    config_ctx = _build_config_context(
        hostname, ip, facts, interfaces or [],
        vlans or [], vrfs or [], running_config or "",
        routing_context=routing_context,
    )

    payload: dict = {
        "name":               hostname,
        "device_type":        dev_type["id"],
        "site":               site_id,
        # CREATE ONLY — see the update allowlist below, which omits it. The
        # default is `active`: onboarding reached the device before this
        # record existed, so it is a lifecycle claim that has been earned.
        "status":             status,
        "serial":             serial,
        "comments":           comments,
        "role":               role_id,
        "device_role":        role_id,
        "local_context_data": config_ctx,
    }
    if platform_id:
        payload["platform"] = platform_id
    if config_template_id:
        payload["config_template"] = config_template_id
    if facts.get("version") and _ensure_custom_field(session, base, "os_version"):
        payload["custom_fields"] = {"os_version": facts["version"]}

    if existing:
        # `status` IS DELIBERATELY ABSENT FROM THIS ALLOWLIST.
        #
        # It used to be set from `status_cache` — the in-memory ping cache —
        # so a single ICMP/TCP attempt that did not answer within five
        # seconds of the sync wrote `offline` into the source of truth as a
        # standing claim. Measured 2026-09-24: NetBox called s1 offline while
        # s1 was answering SSH, and nothing would ever have corrected it.
        #
        # The rule that forbids this already existed, and this escaped it:
        # `_scan_device` was DELETED because *importing observed state into
        # the source of truth is the wrong direction*. A ping result is
        # observed state. A 140-line SSH scanner was removed under that rule
        # while three words on a call site doing the same thing survived —
        # because a rule gets applied to things that have names.
        #
        # A device's status is now whatever a human set, and on create it is
        # `active`, which after this change means *NMAS onboarded this
        # device* rather than *it answered a ping*. Liveness lives in the
        # app's own online/offline badge, which is live when it is read and
        # which nobody mistakes for a stored fact.
        # `platform` and `device_type` ARE ABSENT TOO (the operator's ownership decision,
        # 2026-10-07: NetBox owns a device's identity). The import guessed both from config
        # text, which never says "IOS XE" and never names the model, so every IOS-XE router was
        # written `ios` and every device's type "Unknown", on every sync, and a person's
        # correction in NetBox would have been overwritten by the next one (C557, C559). A
        # create still sets them; an update never does. `role` is absent for the same reason
        # (C665, 2026-10-11): the import wrote every device's role on every sync, an empty one
        # as router, so NetBox's own role, and the kind Mercury now reads from it, would be
        # Mercury's. A create still sets it.
        update = {k: v for k, v in payload.items()
                  if k in ("name", "serial", "comments",
                            "local_context_data", "config_template",
                            "custom_fields")}

        # `role` and `device_role` are ONE field under two names — NetBox 3.x
        # called it `device_role`, 4.x calls it `role` — and the payload sends
        # both so either server accepts it. A server echoes only its own, so
        # the other is ABSENT from the response, which the modification record
        # correctly reports as `before: <unknown>`.
        #
        # The result was an entry for every device on every sync, for ever,
        # reading `device_role: <unknown> → 2` — the fourth churn source, and
        # the worst-looking of them, because `<unknown>` is the shape of a
        # failed read rather than of a no-op.
        #
        # So on an UPDATE, send only the alias this server actually uses.
        # Creates still send both: that is where compatibility matters, and a
        # create is not in the modification record anyway.
        for alias, other in (("device_role", "role"), ("role", "device_role")):
            if alias in update and alias not in existing and other in existing:
                update.pop(alias)
        try:
            device = _nb_patch(session, base, f"dcim/devices/{existing['id']}/", update)
        except RuntimeError:
            update.pop("device_role", None)
            device = _nb_patch(session, base, f"dcim/devices/{existing['id']}/", update)
        action = "updated"
    else:
        try:
            device = _nb_post(session, base, "dcim/devices/", payload)
        except RuntimeError:
            payload.pop("device_role", None)
            device = _nb_post(session, base, "dcim/devices/", payload)
        action = "created"

    device_id = device["id"]

    # ── Protocol tags ──────────────────────────────────────────────────────
    if protocol_tags:
        tag_ids = []
        for proto in protocol_tags:
            try:
                tag = _ensure_tag(session, base, proto.upper(), proto,
                                  _PROTOCOL_TAG_COLORS.get(proto, "9e9e9e"))
                tag_ids.append(tag["id"])
            except Exception as exc:
                _ensure_failed(f"tag '{proto}'", exc)
        if tag_ids:
            try:
                current_tags = [t["id"] for t in (device.get("tags") or [])]
                merged = sorted(set(current_tags + tag_ids))
                # ONLY WRITE WHEN THE SET ACTUALLY CHANGES.
                #
                # This PATCHed unconditionally whenever the device had any
                # protocol tag, and `list(set(...))` hands back an arbitrary
                # order — so every such device logged
                # `tags: [4, 2, 1] → [1, 2, 4]` on every sync: the same three
                # tags, rewritten for nothing, reading as though they had been
                # replaced. A guaranteed no-op write, every sync, for ever.
                #
                # `sorted` makes the value stable; the guard means the write
                # does not happen at all. Comparing unordered in the record
                # would have hidden the entry while the pointless PATCH
                # carried on.
                if set(merged) != set(current_tags):
                    device = _nb_patch(session, base,
                                       f"dcim/devices/{device_id}/",
                                       {"tags": merged})
            except Exception as exc:
                _write_failed("device tags", exc, hostname)

    # ── DCIM interfaces + IPAM ─────────────────────────────────────────────
    mgmt_ip_id: Optional[int] = None
    mgmt_ipv6_id: Optional[int] = None
    loopback_ipv6_id: Optional[int] = None
    first_ipv6_id: Optional[int] = None
    nb_iface_map: dict = {}              # iface_name → nb_id
    deferred_lags: list = []             # (member_name, lag_parent_name) for second pass
    prefix_role_id_cache: dict = {}      # role name → NetBox ipam/roles/ id, this device's sync

    def _prefix_role_id(name: Optional[str]) -> Optional[int]:
        if not name:
            return None
        if name not in prefix_role_id_cache:
            try:
                prefix_role_id_cache[name] = _ensure_prefix_role(session, base, name)["id"]
            except Exception as exc:
                _write_failed(f"prefix role {name}", exc, hostname)
                prefix_role_id_cache[name] = None
        return prefix_role_id_cache[name]

    for intf in (interfaces or []):
        try:
            # Management-only interface — same name heuristic already used for
            # NetBox interface *type* inference, reused here for the mgmt_only flag.
            iface_is_mgmt = intf["name"].lower().lstrip().startswith(("mgmt", "management"))
            # Resolve VRF: use interface-specific VRF if set, else the list-level VRF
            vrf_name = intf.get("vrf_name", "")
            vrf_id: Optional[int] = (vrf_id_map.get(vrf_name) if vrf_name
                                     else list_vrf_id)

            # Switchport mode → NetBox mode value
            sw_mode = intf.get("switchport_mode")
            nb_mode: Optional[str] = None
            if sw_mode == "access":
                nb_mode = "access"
            elif sw_mode in ("trunk", "dot1q-tunnel"):
                nb_mode = "tagged"

            # A ROUTED dot1Q SUBINTERFACE (C1492) is `virtual`, under its parent, and never
            # given an untagged VLAN: NetBox refused that with no 802.1Q mode (400, "Interface
            # mode does not support untagged vlan", 2026-10-21), and the VLAN taken by number
            # at the list's site could be another site's. Its VLAN is set after it is written
            # (`_subinterface_vlan`), from its device's site's VLAN group, or refused by name.
            parent_name = _subinterface_parent(intf)
            parent_id: Optional[int] = None
            if parent_name:
                parent_id = nb_iface_map.get(parent_name) or (_nb_first(
                    session, base, "dcim/interfaces/", device_id=device_id,
                    name=parent_name) or {}).get("id")
                if not parent_id:
                    _write_failed(f"parent of subinterface {intf['name']}", RuntimeError(
                        f"its parent {parent_name} is not in NetBox, so it is not placed "
                        "under it"), hostname)

            # Untagged VLAN (access vlan or dot1q tag)
            untagged_vlan_id: Optional[int] = None
            vlan_vid = None if parent_name else (intf.get("dot1q_tag") or intf.get("access_vlan"))
            if vlan_vid:
                try:
                    nb_vlan = _ensure_vlan(session, base, vlan_vid,
                                          f"VLAN{vlan_vid}", site_id)
                    untagged_vlan_id = nb_vlan["id"]
                    ipam_stats["vlans_synced"] = ipam_stats.get("vlans_synced", 0) + 1
                except Exception as exc:
                    _write_failed(f"VLAN {vlan_vid} on {intf['name']}", exc, hostname)

            # Tagged VLANs for trunk ports (cap at 50 to keep payloads reasonable)
            tagged_vlan_ids: Optional[list] = None
            if intf.get("trunk_vlans"):
                tagged_vlan_ids = []
                for vid in intf["trunk_vlans"][:50]:
                    try:
                        nb_vlan = _ensure_vlan(session, base, vid, f"VLAN{vid}", site_id)
                        tagged_vlan_ids.append(nb_vlan["id"])
                        ipam_stats["vlans_synced"] = ipam_stats.get("vlans_synced", 0) + 1
                    except Exception as exc:
                        # A trunk's VLAN list then lands incomplete (register C8).
                        _write_failed(f"tagged VLAN {vid} on {intf['name']}", exc, hostname)

            nb_intf = _ensure_interface(
                session, base,
                device_id=device_id,
                name=intf["name"],
                description=intf.get("description", ""),
                mac=intf.get("mac"),
                mtu=intf.get("mtu"),
                enabled=intf.get("admin_up", True),
                speed_mbps=intf.get("speed_mbps"),
                vrf_id=vrf_id,
                mode=nb_mode,
                untagged_vlan_id=untagged_vlan_id,
                tagged_vlan_ids=tagged_vlan_ids,
                duplex=intf.get("duplex"),
                mgmt_only=iface_is_mgmt,
                parent_id=parent_id,
            )
            nb_iface_map[intf["name"]] = nb_intf["id"]
            if parent_name:
                _subinterface_vlan(session, base, nb_intf, intf, device, site_id, hostname,
                                   ipam_stats)
            # Alias under the abbreviated form too — LLDP commonly reports
            # local interfaces abbreviated (see _shorten_iface_name) even
            # though the golden config and CDP both use the full name.
            nb_iface_map[_shorten_iface_name(intf["name"])] = nb_intf["id"]
            ipam_stats["interfaces_synced"] = ipam_stats.get("interfaces_synced", 0) + 1

            # Queue LAG membership for deferred second pass
            if intf.get("channel_group") is not None:
                lag_parent = f"Port-channel{intf['channel_group']}"
                deferred_lags.append((intf["name"], lag_parent))

            # Skip IPAM for interfaces without any IP
            if not intf.get("cidr") and not intf.get("secondary_ips") and not intf.get("ipv6_addresses"):
                continue

            # An EXCLUDED VRF's addresses are the emulator's plumbing, not
            # the network. Every node an emulator runs may answer on the same
            # internal management address, so NetBox -- which enforces
            # global uniqueness -- cannot represent five of them, and the
            # one it accepts is a claim that one device has an address all
            # five have. The interface is still modelled; its addresses are
            # not. Counted, never silent: a skip nobody can see is the
            # failure mode this stack is most prone to.
            if vrf_name and vrf_name.lower() in excluded_vrfs():
                ipam_stats["ips_excluded"] = (
                    ipam_stats.get("ips_excluded", 0)
                    + len([c for c in ([intf.get("cidr")]
                                       + list(intf.get("secondary_ips") or [])
                                       + list(intf.get("ipv6_addresses") or []))
                           if c]))
                ipam_stats.setdefault("excluded_vrfs", [])
                if vrf_name not in ipam_stats["excluded_vrfs"]:
                    ipam_stats["excluded_vrfs"].append(vrf_name)
                _skip(ipam_stats, f"addresses in VRF {vrf_name}",
                      "the VRF is excluded (netbox_excluded_vrfs): its addresses describe the "
                      "emulator's plumbing, not the network, and NetBox refuses the duplicates; "
                      "the interface is still modelled",
                      hostname, count=len([c for c in ([intf.get("cidr")]
                                                       + list(intf.get("secondary_ips") or [])
                                                       + list(intf.get("ipv6_addresses") or []))
                                           if c]))
                log.info("netbox: %s %s — addresses not modelled, VRF %r is "
                         "excluded", hostname, intf.get("name"), vrf_name)
                continue

            # Primary IPv4
            if intf.get("cidr"):
                role_id_v4 = _prefix_role_id(_infer_prefix_role_name(intf["name"], intf["prefix"]))
                _ensure_prefix(
                    session, base,
                    prefix=intf["prefix"],
                    description=f"Seen on {hostname} {intf['name']}",
                    site_id=site_id,
                    vrf_id=vrf_id,
                    role_id=role_id_v4,
                )
                ipam_stats["prefixes_synced"] = ipam_stats.get("prefixes_synced", 0) + 1

                nb_ip = _ensure_ip_address(
                    session, base,
                    address_cidr=intf["cidr"],
                    interface_id=nb_intf["id"],
                    description=f"{hostname} {intf['name']}",
                    vrf_id=vrf_id, stats=ipam_stats,
                )
                ipam_stats["ips_synced"] = ipam_stats.get("ips_synced", 0) + 1

                if intf["cidr"].split("/")[0] == ip:
                    mgmt_ip_id = nb_ip["id"]

            # Secondary IPv4 addresses
            for sec_cidr in intf.get("secondary_ips", []):
                try:
                    sec_prefix = str(ipaddress.ip_interface(sec_cidr).network)
                    role_id_sec = _prefix_role_id(_infer_prefix_role_name(intf["name"], sec_prefix))
                    _ensure_prefix(session, base, prefix=sec_prefix,
                                   description=f"Seen on {hostname} {intf['name']} (secondary)",
                                   site_id=site_id, vrf_id=vrf_id, role_id=role_id_sec)
                    _ensure_ip_address(session, base, address_cidr=sec_cidr,
                                       interface_id=nb_intf["id"],
                                       description=f"{hostname} {intf['name']} secondary",
                                       vrf_id=vrf_id, stats=ipam_stats)
                    ipam_stats["ips_synced"] = ipam_stats.get("ips_synced", 0) + 1
                except Exception as exc:
                    _write_failed(f"secondary IP {sec_cidr} on {intf['name']}", exc, hostname)

            # IPv6 addresses — same VRF as the interface's IPv4 side (a device's
            # dual-stack interface shares one VRF) and tracked for primary_ip6,
            # mirroring the IPv4 mgmt_ip_id logic below.
            for v6_cidr in intf.get("ipv6_addresses", []):
                try:
                    v6_net = str(ipaddress.ip_interface(v6_cidr).network)
                    role_id_v6 = _prefix_role_id(_infer_prefix_role_name(intf["name"], v6_net))
                    _ensure_prefix(session, base, prefix=v6_net,
                                   description=f"Seen on {hostname} {intf['name']} (IPv6)",
                                   site_id=site_id, vrf_id=vrf_id, role_id=role_id_v6)
                    nb_ip6 = _ensure_ip_address(session, base, address_cidr=v6_cidr,
                                       interface_id=nb_intf["id"],
                                       description=f"{hostname} {intf['name']} IPv6",
                                       vrf_id=vrf_id, stats=ipam_stats)
                    ipam_stats["ips_synced"] = ipam_stats.get("ips_synced", 0) + 1
                    if first_ipv6_id is None:
                        first_ipv6_id = nb_ip6["id"]
                    if "loopback0" in intf["name"].lower():
                        loopback_ipv6_id = nb_ip6["id"]
                except Exception as exc:
                    _write_failed(f"IPv6 {v6_cidr} on {intf['name']}", exc, hostname)

        except Exception as exc:
            # It went into `ipam_stats["errors"]`, which the summary never
            # copies (it takes only the counts): recorded where nothing read
            # it (register C8). Now a write failure like the rest.
            _write_failed(f"interface {intf.get('name', '?')} and its addresses", exc, hostname)

    # ── LAG membership (second pass — Port-channel must exist first) ───────
    for member_name, lag_parent_name in deferred_lags:
        lag_parent_id = nb_iface_map.get(lag_parent_name)
        member_id     = nb_iface_map.get(member_name)
        if not (lag_parent_id and member_id):
            continue
        try:
            _nb_patch(session, base, f"dcim/interfaces/{member_id}/",
                      {"lag": lag_parent_id})
        except Exception as exc:
            _write_failed(f"LAG membership {member_name} -> {lag_parent_name}", exc, hostname)

    # ── VPN tunnels (NetBox 3.7+ vpn/tunnels/ endpoint) ──────────────────
    for intf in (interfaces or []):
        if not intf["name"].lower().startswith("tunnel"):
            continue
        tun_src  = intf.get("tunnel_source", "")
        tun_dst  = intf.get("tunnel_destination", "")
        tun_mode = intf.get("tunnel_mode", "")
        tun_key  = intf.get("tunnel_key")
        nhrp_id  = intf.get("nhrp_network_id")
        iface_id = nb_iface_map.get(intf["name"])
        if not iface_id:
            continue

        # Build a description from the tunnel params
        desc_parts = []
        if tun_src:
            desc_parts.append(f"src:{tun_src}")
        if tun_dst:
            desc_parts.append(f"dst:{tun_dst}")
        if tun_mode:
            desc_parts.append(tun_mode)
        tun_desc = " | ".join(desc_parts)

        # Determine role: hub = multipoint with no fixed destination (DMVPN hub)
        #                 spoke = has explicit destination (DMVPN spoke or P2P GRE)
        #                 peer  = point-to-point without explicit hub/spoke context
        is_dmvpn = bool(nhrp_id)
        is_multipoint = "multipoint" in tun_mode.lower()
        if is_dmvpn and is_multipoint and not tun_dst:
            role = "hub"
        elif tun_dst:
            role = "spoke"
        else:
            role = "peer"

        encap = _tunnel_encap(tun_mode)
        tun_name = f"{hostname} {intf['name']}"
        try:
            nb_tun = _ensure_vpn_tunnel(
                session, base,
                name=tun_name,
                encapsulation=encap,
                tunnel_id=tun_key,
                description=tun_desc,
            )
            if nb_tun:
                _ensure_tunnel_termination(session, base, nb_tun["id"], role, iface_id)
                ipam_stats["tunnels_synced"] = ipam_stats.get("tunnels_synced", 0) + 1
                log.debug("netbox: tunnel %s (%s) → %s", tun_name, encap, role)
        except Exception as exc:
            _write_failed(f"tunnel {tun_name}", exc, hostname)

    # ── Static routes as IPAM prefixes ────────────────────────────────────
    if static_routes:
        sr_tag_id: Optional[int] = None
        try:
            sr_tag = _ensure_tag(session, base, "static-route", "static-route", "607d8b")
            sr_tag_id = sr_tag["id"]
        except Exception as exc:
            _ensure_failed("tag 'static-route'", exc)

        for route in static_routes:
            # ONE exclusion rule for addresses and routes (2026-09-28). The
            # excluded VRF's addresses were skipped and its static routes were
            # not, so every router's default route in the emulator's VRF
            # (the emulator's own default route) was attempted as a /0 prefix
            # and refused on all five: two readers of one rule, disagreeing.
            rvrf = route.get("vrf") or ""
            if rvrf and rvrf.lower() in excluded_vrfs():
                _skip(ipam_stats, f"static routes in VRF {rvrf}",
                      "the VRF is excluded (netbox_excluded_vrfs): its routes, like its "
                      "addresses, describe the emulator's plumbing, not the network",
                      hostname)
                continue
            if str(route.get("prefix", "")).endswith("/0"):
                _skip(ipam_stats, f"static route {route['prefix']} as a prefix",
                      DEFAULT_ROUTE_SKIP, hostname)
                continue
            try:
                route_vrf_id = vrf_id_map.get(route.get("vrf", "")) if route.get("vrf") else None
                params: dict = {"prefix": route["prefix"]}
                if route_vrf_id:
                    params["vrf_id"] = route_vrf_id
                existing_pf = _nb_first(session, base, "ipam/prefixes/", **params)
                if existing_pf:
                    # Already there; only a missing site is set, on Mercury's own (C1010).
                    scope = _prefix_scope_backfill(existing_pf, site_id)
                    if scope:
                        obj = _nb_patch(session, base,
                                        f"ipam/prefixes/{existing_pf['id']}/", scope)
                        _check_prefix_scope(obj, route["prefix"], scope)
                    continue
                pf: dict = {
                    "prefix":      route["prefix"],
                    "status":      "active",
                    "description": f"Static via {route.get('nexthop', '')} on {hostname}",
                    **_prefix_scope(site_id),
                }
                if route_vrf_id:
                    pf["vrf"] = route_vrf_id
                if sr_tag_id:
                    pf["tags"] = [sr_tag_id]
                obj = _nb_post(session, base, "ipam/prefixes/", pf)
                _check_prefix_scope(obj, route["prefix"], _prefix_scope(site_id))
                ipam_stats["prefixes_synced"] = ipam_stats.get("prefixes_synced", 0) + 1
            except Exception as exc:
                _write_failed(f"static route {route.get('prefix')}", exc, hostname)

    # A RETIRED RECORD HOLDING THIS DEVICE'S ADDRESS is said, naming it (C1494): a device
    # retired before retire unassigned its addresses keeps them, and the next device given the
    # address cannot be given it in NetBox, or holds it twice.
    if ip:
        _say_held_by_decommissioned(session, base, ip, device_id, hostname)

    # Set primary_ip4 from management IP.
    # The strict match during the interface loop only fires when one interface IP
    # equals the device's SSH IP exactly.  If it didn't fire (e.g. the device is
    # managed via a dedicated mgmt network not in the golden config, or the IP is
    # on a subinterface), fall back through progressively looser searches.
    if not mgmt_ip_id and ip:
        try:
            # 1. Search NetBox IPAM for the mgmt IP (any prefix length) in the list VRF
            params: dict = {"address": ip}
            if list_vrf_id:
                params["vrf_id"] = list_vrf_id
            hits = _nb_get(session, base, "ipam/ip-addresses/", **params)
            # Filter to IPs actually assigned to this device
            for h in hits:
                obj_type = h.get("assigned_object_type") or ""
                if obj_type == "dcim.interface":
                    iface_id = h.get("assigned_object_id")
                    if iface_id in nb_iface_map.values():
                        mgmt_ip_id = h["id"]
                        break
            # 2. Fall back to any IP on this device — prefer Loopback0, then first
            if not mgmt_ip_id and nb_iface_map:
                all_hits = _nb_get(session, base, "ipam/ip-addresses/",
                                   device_id=device_id)
                loopback_ip = None
                first_ip    = None
                for h in all_hits:
                    if first_ip is None:
                        first_ip = h["id"]
                    iface_name = (h.get("assigned_object") or {}).get("name", "")
                    if "loopback0" in iface_name.lower():
                        loopback_ip = h["id"]
                        break
                mgmt_ip_id = loopback_ip or first_ip

            # 3. Last resort: the device has no IPs in NetBox at all (golden config has
            #    no addresses, or the SSH IP is on a management network not in the config).
            #    Create the SSH management IP directly from devices.csv as a /32 host
            #    address so the device always has a reachable primary IP.
            if not mgmt_ip_id:
                first_iface_id = next(iter(nb_iface_map.values()), None)
                # THE PREFIX THE DEVICE ACTUALLY HAS, when the caller knows it.
                #
                # A host route is the honest answer when the length is unknown
                # -- a golden with no addresses tells us nothing about the
                # subnet -- but for a DHCP device the LEASE knows, and
                # onboarding now carries it here. Recording a host route for an
                # interface that is really on a /24 is NetBox being wrong about
                # the network, which is the one thing NetBox is for.
                #
                # 0 or absent keeps the /32 last resort: not knowing and
                # guessing are different, and only one of them is honest.
                try:
                    prefix = int(mgmt_prefix_len or 0)
                except (TypeError, ValueError):
                    prefix = 0
                mgmt_cidr = f"{ip}/{prefix if 0 < prefix <= 32 else 32}"
                if not first_iface_id:
                    # `_ensure_ip_address` now refuses an unscoped lookup, so
                    # say WHY rather than letting the refusal reach the debug
                    # log below and read as "the address already existed".
                    log.warning("netbox: %s — no interfaces in NetBox, so the "
                                "management address %s was not created; the "
                                "device will have no primary_ip4",
                                hostname, mgmt_cidr)
                try:
                    nb_mgmt_ip = _ensure_ip_address(
                        session, base,
                        address_cidr=mgmt_cidr,
                        interface_id=first_iface_id,
                        description=f"{hostname} management (device list SSH IP)",
                        vrf_id=list_vrf_id, stats=ipam_stats,
                    )
                    mgmt_ip_id = nb_mgmt_ip["id"]
                    ipam_stats["ips_synced"] = ipam_stats.get("ips_synced", 0) + 1
                    log.info("netbox: %s — no interface IPs found; created mgmt IP %s from device list",
                             hostname, mgmt_cidr)
                except Exception as exc2:
                    _write_failed(f"fallback management IP {mgmt_cidr}", exc2, hostname)
        except Exception as exc:
            _write_failed("primary IP fallback", exc, hostname)

    if mgmt_ip_id and (device.get("primary_ip4") or {}).get("id") != mgmt_ip_id:
        try:
            device = _nb_patch(session, base,
                               f"dcim/devices/{device_id}/",
                               {"primary_ip4": mgmt_ip_id})
        except Exception as exc:
            _write_failed("primary_ip4", exc, hostname)

    # Set primary_ip6 the same way primary_ip4 falls back to Loopback0 (tier 2
    # above) — no exact-SSH-match tier (this app doesn't manage over IPv6) and
    # no synthetic-address tier (unlike v4, a device with no IPv6 configured
    # simply has no primary_ip6, which is correct, not a gap to paper over).
    mgmt_ipv6_id = loopback_ipv6_id or first_ipv6_id
    if mgmt_ipv6_id and (device.get("primary_ip6") or {}).get("id") != mgmt_ipv6_id:
        try:
            device = _nb_patch(session, base,
                               f"dcim/devices/{device_id}/",
                               {"primary_ip6": mgmt_ipv6_id})
        except Exception as exc:
            _write_failed("primary_ip6", exc, hostname)

    return {
        "action":       action,
        "id":           device_id,
        "name":         hostname,
        "data":         device,
        "nb_iface_map": nb_iface_map,
    }


# ---------------------------------------------------------------------------
# Golden-config parsers (used by _scan_device_from_golden)
# ---------------------------------------------------------------------------

def _parse_all_interfaces_from_config(config: str) -> list[dict]:
    """Parse ALL interface blocks from a running/golden config.

    Returns one entry per interface regardless of whether it has an IP.
    Keys: name, cidr, prefix, dhcp, secondary_ips, ipv6_addresses, description,
          mtu, duplex, mac, speed_mbps, bandwidth_kbps, admin_up, oper_up,
          vrf_name, channel_group, switchport_mode, access_vlan,
          trunk_vlans, dot1q_tag.
    """
    results: list[dict] = []
    for m in _RE_RC_IFACE_BLOCK.finditer(config):
        name = m.group(1)
        body = m.group(2)

        # Primary IPv4. `ip address dhcp` holds none the config can say: the lease is the
        # manifest's (C1442, `_lease_onto_interface`).
        cidr = prefix = None
        dhcp = bool(re.search(r"^\s+ip address\s+dhcp\b", body, re.MULTILINE))
        ip_m = _RE_RC_IP_ADDR.search(body)
        if ip_m:
            try:
                net  = ipaddress.IPv4Network(
                    f"{ip_m.group(1)}/{ip_m.group(2)}", strict=False
                )
                addr = ipaddress.ip_interface(f"{ip_m.group(1)}/{net.prefixlen}")
                cidr   = str(addr)
                prefix = str(addr.network)
            except ValueError:
                pass

        # Secondary IPv4 addresses
        secondary_ips: list = []
        for sec in re.finditer(
            r"^\s+ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+secondary",
            body, re.MULTILINE,
        ):
            try:
                snet = ipaddress.IPv4Network(f"{sec.group(1)}/{sec.group(2)}", strict=False)
                secondary_ips.append(
                    str(ipaddress.ip_interface(f"{sec.group(1)}/{snet.prefixlen}"))
                )
            except ValueError:
                pass

        # IPv6 addresses
        ipv6_addresses: list = []
        for v6 in re.finditer(
            r"^\s+ipv6 address\s+([0-9a-fA-F:]+/\d+)", body, re.MULTILINE
        ):
            try:
                ipv6_addresses.append(str(ipaddress.ip_interface(v6.group(1))))
            except ValueError:
                pass

        # VRF assignment
        vrf_m = re.search(
            r"^\s+(?:ip\s+)?vrf\s+forwarding\s+(\S+)", body, re.MULTILINE
        )
        vrf_name = vrf_m.group(1) if vrf_m else ""

        # LAG (channel-group membership)
        lag_m = re.search(r"^\s+channel-group\s+(\d+)", body, re.MULTILINE)
        channel_group = int(lag_m.group(1)) if lag_m else None

        # Switchport mode
        sw_m = re.search(r"^\s+switchport\s+mode\s+(\w+)", body, re.MULTILINE)
        switchport_mode = sw_m.group(1).lower() if sw_m else None

        # Access VLAN
        av_m = re.search(r"^\s+switchport\s+access\s+vlan\s+(\d+)", body, re.MULTILINE)
        access_vlan = int(av_m.group(1)) if av_m else None

        # Trunk VLANs
        tv_m = re.search(
            r"^\s+switchport\s+trunk\s+allowed\s+vlan\s+(.+)", body, re.MULTILINE
        )
        trunk_vlans = _expand_vlan_list(tv_m.group(1)) if tv_m else []

        # Dot1q subinterface tag
        dq_m = re.search(r"^\s+encapsulation\s+dot1[qQ]\s+(\d+)", body, re.MULTILINE)
        dot1q_tag = int(dq_m.group(1)) if dq_m else None

        desc_m   = _RE_RC_DESCR.search(body)
        mtu_m    = re.search(r"^\s+mtu\s+(\d+)", body, re.MULTILINE)
        shutdown = bool(_RE_RC_SHUTDOWN.search(body))

        # Duplex — only present when explicitly configured (not auto-negotiated
        # default), same as mtu/switchport above: extractable from config text
        # because it's a real config directive, unlike MAC/oper-speed which
        # only exist as live hardware state and can't come from a golden config.
        duplex_m = re.search(r"^\s+duplex\s+(full|half|auto)", body, re.MULTILINE | re.IGNORECASE)
        duplex   = duplex_m.group(1).lower() if duplex_m else None

        # Tunnel-specific attributes (only populated for Tunnel interfaces)
        tunnel_source      = ""
        tunnel_destination = ""
        tunnel_mode        = ""
        tunnel_key: Optional[int] = None
        nhrp_network_id: Optional[int] = None
        if name.lower().startswith("tunnel"):
            ts_m = re.search(r"^\s+tunnel source\s+(\S+)", body, re.MULTILINE)
            td_m = re.search(r"^\s+tunnel destination\s+(\S+)", body, re.MULTILINE)
            tm_m = re.search(r"^\s+tunnel mode\s+(.+?)$", body, re.MULTILINE)
            tk_m = re.search(r"^\s+tunnel key\s+(\d+)", body, re.MULTILINE)
            nh_m = re.search(r"^\s+ip nhrp network-id\s+(\d+)", body, re.MULTILINE)
            tunnel_source      = ts_m.group(1) if ts_m else ""
            tunnel_destination = td_m.group(1) if td_m else ""
            tunnel_mode        = tm_m.group(1).strip() if tm_m else ""
            tunnel_key         = int(tk_m.group(1)) if tk_m else None
            nhrp_network_id    = int(nh_m.group(1)) if nh_m else None

        # Auto-generate description for tunnels that don't have one
        raw_desc = desc_m.group(1).strip() if desc_m else ""
        if not raw_desc and name.lower().startswith("tunnel"):
            parts = []
            if tunnel_source:
                parts.append(f"src:{tunnel_source}")
            if tunnel_destination:
                parts.append(f"dst:{tunnel_destination}")
            if tunnel_mode:
                parts.append(tunnel_mode)
            raw_desc = " | ".join(parts)

        results.append({
            "name":               name,
            "cidr":               cidr,
            "prefix":             prefix,
            "dhcp":               dhcp,
            "secondary_ips":      secondary_ips,
            "ipv6_addresses":     ipv6_addresses,
            "description":        raw_desc,
            "mtu":                int(mtu_m.group(1)) if mtu_m else None,
            "duplex":             duplex,
            "mac":                None,
            "speed_mbps":         None,
            "bandwidth_kbps":     None,
            "admin_up":           not shutdown,
            "oper_up":            not shutdown,
            "vrf_name":           vrf_name,
            "channel_group":      channel_group,
            "switchport_mode":    switchport_mode,
            "access_vlan":        access_vlan,
            "trunk_vlans":        trunk_vlans,
            "dot1q_tag":          dot1q_tag,
            "tunnel_source":      tunnel_source,
            "tunnel_destination": tunnel_destination,
            "tunnel_mode":        tunnel_mode,
            "tunnel_key":         tunnel_key,
            "nhrp_network_id":    nhrp_network_id,
        })
    return results


def _parse_facts_from_config(config: str) -> dict:
    """Extract hostname, IOS version, and platform from a running/golden config."""
    facts = {
        "manufacturer": "Cisco",
        "model":        "Unknown",
        "serial":       "",
        "version":      "",
        "platform":     "IOS",
        "hostname":     "",
    }
    m = re.search(r"^version\s+([\d.()A-Za-z]+)", config, re.MULTILINE)
    if m:
        facts["version"] = m.group(1)
    if "IOS XE" in config or "IOS-XE" in config:
        facts["platform"] = "IOS-XE"
    elif "NX-OS" in config or "NXOS" in config:
        facts["platform"] = "NX-OS"
    m = re.search(r"^hostname\s+(\S+)", config, re.MULTILINE)
    if m:
        facts["hostname"] = m.group(1)
    return facts


def _parse_vrfs_from_config(config: str) -> list[dict]:
    """Extract VRF names and route-distinguishers from a running/golden config."""
    vrfs: list[dict] = []
    seen: set = set()

    def _add(name: str, body: str) -> None:
        if name in seen:
            return
        seen.add(name)
        rd_m = re.search(r"^\s+rd\s+(\S+)", body, re.MULTILINE)
        vrfs.append({"name": name, "rd": rd_m.group(1) if rd_m else ""})

    for m in re.finditer(r"^vrf definition\s+(\S+)(.*?)(?=^\S|\Z)",
                         config, re.MULTILINE | re.DOTALL):
        _add(m.group(1), m.group(2))
    for m in re.finditer(r"^ip vrf\s+(\S+)(.*?)(?=^\S|\Z)",
                         config, re.MULTILINE | re.DOTALL):
        _add(m.group(1), m.group(2))
    return vrfs


def _parse_vlans_from_config(config: str) -> list[dict]:
    """Extract VLAN IDs and names from a running/golden config (switch configs)."""
    vlans: list[dict] = []
    seen: set = set()
    for m in re.finditer(r"^vlan\s+(\d+)\s*$(.*?)(?=^\S|\Z)",
                         config, re.MULTILINE | re.DOTALL):
        vid = int(m.group(1))
        if vid in (1002, 1003, 1004, 1005) or vid in seen:
            continue
        seen.add(vid)
        name_m = re.search(r"^\s+name\s+(.+)$", m.group(2), re.MULTILINE)
        vlans.append({
            "vlan_id": vid,
            "name":    name_m.group(1).strip() if name_m else f"VLAN{vid}",
        })
    return vlans


def _parse_static_routes_from_config(config: str) -> list[dict]:
    """Extract static routes from a running/golden config.

    Returns [{prefix, nexthop, distance, vrf}] — suitable for IPAM prefix creation.
    """
    routes: list[dict] = []
    for m in re.finditer(
        r"^ip route\s+(?:vrf\s+(\S+)\s+)?(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)(?:\s+(\d+))?",
        config, re.MULTILINE,
    ):
        vrf_name = m.group(1) or ""
        network  = m.group(2)
        mask     = m.group(3)
        nexthop  = m.group(4)
        distance = int(m.group(5)) if m.group(5) else 1
        try:
            net = ipaddress.IPv4Network(f"{network}/{mask}", strict=False)
            routes.append({
                "prefix":   str(net),
                "nexthop":  nexthop,
                "distance": distance,
                "vrf":      vrf_name,
            })
        except ValueError:
            pass
    return routes


_PROTOCOL_TAG_COLORS = {
    "ospf":  "2196f3",
    "bgp":   "4caf50",
    "mpls":  "ff9800",
    "cdp":   "9c27b0",
    "eigrp": "00bcd4",
    "rip":   "f44336",
}


def _parse_protocol_tags_from_config(config: str) -> list[str]:
    """Detect routing/transport protocols enabled in a config.

    Returns a list of lowercase tag names ("ospf", "bgp", "mpls", …).
    """
    tags: list[str] = []
    checks = [
        ("ospf",  r"^router ospf\s",    re.MULTILINE),
        ("bgp",   r"^router bgp\s",     re.MULTILINE),
        ("mpls",  r"^\s*mpls ip\b",     re.MULTILINE),
        ("cdp",   r"^cdp run\b",        re.MULTILINE),
        ("eigrp", r"^router eigrp\s",   re.MULTILINE),
        ("rip",   r"^router rip\b",     re.MULTILINE),
    ]
    for tag, pattern, flags in checks:
        if re.search(pattern, config, flags):
            tags.append(tag)
    return tags


def _parse_routing_context_from_config(config: str) -> dict:
    """Extract structured OSPF, BGP, NTP, and SNMP data from a config.

    Returns a dict suitable for merging into local_context_data.
    """
    ctx: dict = {}

    # OSPF processes
    ospf_procs = []
    for m in re.finditer(
        r"^router ospf\s+(\d+)(.*?)(?=^router\s|^interface\s|\Z)",
        config, re.MULTILINE | re.DOTALL,
    ):
        body = m.group(2)
        rid_m = re.search(r"^\s+router-id\s+(\S+)", body, re.MULTILINE)
        areas = sorted(set(re.findall(r"\barea\s+(\S+)", body)))
        ospf_procs.append({
            "process_id": int(m.group(1)),
            "router_id":  rid_m.group(1) if rid_m else "",
            "areas":      areas,
        })
    if ospf_procs:
        ctx["ospf"] = ospf_procs

    # BGP
    bgp_m = re.search(
        r"^router bgp\s+(\d+)(.*?)(?=^router\s|^interface\s|\Z)",
        config, re.MULTILINE | re.DOTALL,
    )
    if bgp_m:
        bgp_body = bgp_m.group(2)
        rid_m = re.search(r"^\s+bgp router-id\s+(\S+)", bgp_body, re.MULTILINE)
        neighbors = []
        for nb_m in re.finditer(
            r"^\s+neighbor\s+(\S+)\s+remote-as\s+(\d+)", bgp_body, re.MULTILINE
        ):
            neighbors.append({"peer": nb_m.group(1), "remote_as": int(nb_m.group(2))})
        ctx["bgp"] = {
            "asn":       int(bgp_m.group(1)),
            "router_id": rid_m.group(1) if rid_m else "",
            "neighbors": neighbors,
        }

    # NTP servers
    ntp = re.findall(r"^ntp server\s+(\S+)", config, re.MULTILINE)
    if ntp:
        ctx["ntp_servers"] = ntp

    # SNMP communities / version
    snmp: dict = {}
    for sm in re.finditer(r"^snmp-server community\s+(\S+)\s+(RO|RW)", config, re.MULTILINE):
        # The community is a CREDENTIAL, and this field held it in plaintext
        # (C95). What a community grants is kept; the value is left out, as
        # the operator decided. `running_config` carries the line masked.
        snmp.setdefault("communities", []).append({
            "permission": sm.group(2),
        })
    sv_m = re.search(r"^snmp-server version\s+(\S+)", config, re.MULTILINE)
    if sv_m:
        snmp["version"] = sv_m.group(1)
    if snmp:
        ctx["snmp"] = snmp

    # Tunnels
    tunnels = []
    for m in re.finditer(
        r"^interface\s+(Tunnel\S+)(.*?)(?=^interface\s|\Z)",
        config, re.MULTILINE | re.DOTALL,
    ):
        body = m.group(2)
        ts_m = re.search(r"^\s+tunnel source\s+(\S+)", body, re.MULTILINE)
        td_m = re.search(r"^\s+tunnel destination\s+(\S+)", body, re.MULTILINE)
        tm_m = re.search(r"^\s+tunnel mode\s+(.+?)$", body, re.MULTILINE)
        tk_m = re.search(r"^\s+tunnel key\s+(\d+)", body, re.MULTILINE)
        nh_m = re.search(r"^\s+ip nhrp network-id\s+(\d+)", body, re.MULTILINE)
        tun: dict = {"name": m.group(1)}
        if ts_m:
            tun["source"] = ts_m.group(1)
        if td_m:
            tun["destination"] = td_m.group(1)
        if tm_m:
            tun["mode"] = tm_m.group(1).strip()
        if tk_m:
            tun["key"] = int(tk_m.group(1))
        if nh_m:
            tun["nhrp_network_id"] = int(nh_m.group(1))
        tunnels.append(tun)
    if tunnels:
        ctx["tunnels"] = tunnels

    return ctx


def _committed_manifest(list_name: str = "") -> tuple:
    """``(manifest document, error)``: *list_name*'s manifest committed at HEAD (the active
    list's when none is named), read once per import (C1442: the leased addresses)."""
    from modules.nsot import leased_address

    try:
        if list_name:
            from modules.nsot import listref
            if not listref.exists(list_name):      # resolving a path creates it (C51)
                return {"devices": {}}, ""
            repo = listref.resolve(list_name).repo_dir
        else:
            from modules.goldens import _nsot_repo_dir
            repo = _nsot_repo_dir()
        return leased_address.committed_manifest(repo)
    except Exception as exc:                          # noqa: BLE001 - said, never raised
        return {"devices": {}}, f"the committed manifest could not be read ({exc})"


def _lease_onto_interface(interfaces: list, entry: dict) -> str:
    """Give the device's one ``ip address dhcp`` interface its leased address (C1442), in
    place: the address the manifest recorded from Kea's lease at Verify, with its prefix
    length, through the one helper every reader uses (`leased_address.interface_ipv4`).
    Returns the interface given it, or "" (`leased_address.why_not` says why, logged)."""
    import ipaddress as _ip

    from modules.nsot import leased_address

    shape = [{"name": i.get("name", ""), "vrf": i.get("vrf_name", ""),
              "ipv4": "dhcp" if i.get("dhcp") else (i.get("cidr") or "")}
             for i in interfaces or []]
    if not any(s["ipv4"] == "dhcp" for s in shape):
        return ""
    for intf, iface in zip(interfaces, shape):
        value = leased_address.interface_ipv4(iface, shape, entry) if iface["ipv4"] == "dhcp" \
            else ""
        if value:
            address, mask = value.split()
            lease = _ip.ip_interface(f"{address}/{mask}")
            intf["cidr"], intf["prefix"] = str(lease), str(lease.network)
            return intf.get("name", "")
    log.info("netbox: no leased address placed: %s", leased_address.why_not(shape, entry))
    return ""


def _scan_device_from_golden(dev: dict, list_name: str = "", manifest: dict = None) -> dict:
    """Build a NetBox scan result from the device's saved golden config.

    No SSH session is opened — all data comes from the golden config file.
    This is the only scanner; the SSH one was removed in Stage 3.3 because
    nothing called it.

    *manifest*: the list's committed manifest document (`_committed_manifest`), read once by
    the import; absent, read here. A device whose address Kea leases has its one
    ``ip address dhcp`` interface given that address (C1442).
    """
    from modules.goldens import _golden_record

    ip       = dev.get("ip", "")
    # CSV hostname is authoritative — it reflects the current name (manually set
    # or updated via Refresh Hostnames).  Only fall back to the golden config's
    # IOS hostname command when the CSV entry has no hostname at all.
    csv_hostname = dev.get("hostname", "").strip()

    # The app's own device-role field (router/switch/firewall) — used to give
    # each device a matching NetBox device-role instead of one flat generic
    # role for everything.
    app_role = (dev.get("role") or "router").strip().lower()

    # A PREVIEW OF A DEVICE WITH NO GOLDEN YET (adopt, 7.3): the caller hands
    # the capture it previews. Honoured in a DRY RUN only, so a real import
    # still builds every object from what is COMMITTED (C104), never from a
    # text a caller supplied.
    from modules import netbox_guard as _guard
    if dev.get("preview_config") is not None and _guard.is_dry_run():
        record = {"text": dev["preview_config"], "refused": ""}
    else:
        record = _golden_record(ip, list_name)        # its OWN list's golden (C498)
    golden = record["text"]
    if not golden:
        return {
            "ip":       ip,
            "hostname": csv_hostname or ip,
            "app_role": app_role,
            "error":    (f"golden refused: {record['refused']}" if record["refused"]
                         else "No golden config saved: capture the device first"),
        }

    facts           = _parse_facts_from_config(golden)
    golden_hostname = facts.pop("hostname", "") or ""
    # Prefer the CSV hostname; fall back to the IOS hostname from the config;
    # final fallback is the IP address.
    hostname = csv_hostname or golden_hostname or ip
    # THE DIALECT IS THE INVENTORY'S (C1442): a config text cannot say what it is. The fleet's
    # goldens carry the capture's `! Cisco IOS XE Software` header and read IOS-XE; a capture
    # without it (onboarding's own, a ZTP device's first) read "IOS", and NetBox recorded an
    # IOS-XE router as IOS. The text is still read for a device whose dialect is unknown.
    from modules.nsot.platform import FACT_WORDS, platform_for_device
    dialect = platform_for_device(dev) or ""
    if facts.get("platform") == "IOS" and FACT_WORDS.get(dialect):   # "IOS": the text said none
        facts["platform"] = FACT_WORDS[dialect]
    interfaces      = _parse_all_interfaces_from_config(golden)
    if any(i.get("dhcp") for i in interfaces):
        from modules.nsot import leased_address
        if manifest is None:
            manifest, why = _committed_manifest(list_name)
            if why:
                log.warning("netbox: %s: %s; no leased address placed", hostname, why)
        _lease_onto_interface(interfaces, leased_address.entries_by_name(manifest)
                              .get(hostname.lower()) or {})
    vrfs            = _parse_vrfs_from_config(golden)
    vlans           = _parse_vlans_from_config(golden)
    static_routes   = _parse_static_routes_from_config(golden)
    protocol_tags   = _parse_protocol_tags_from_config(golden)
    routing_context = _parse_routing_context_from_config(golden)

    log.info("netbox: golden-config scan for %s (%s) — %d interfaces, %d static routes, tags: %s",
             hostname, ip, len(interfaces), len(static_routes), protocol_tags)
    return {
        "ip":              ip,
        # CARRIED THROUGH FROM THE CALLER, not parsed. A golden that says
        # `ip address dhcp` cannot tell anyone the subnet -- onboarding asked
        # Kea's lease and put it on the device dict, and this is the only path
        # from there to the NetBox record. Absent means unknown, and NetBox
        # keeps its host-route last resort.
        "mgmt_prefix_len": dev.get("prefix_len") or 0,
        # The NetBox record this device IS, when the caller knows it (onboarding from a
        # Planned record, C676): updated by its id, never matched by name and site.
        "netbox_id":       dev.get("netbox_id"),
        "hostname":        hostname,
        "app_role":        app_role,
        "facts":           facts,
        # The inventory's dialect, for the platform a CREATED record is given (C1442).
        "dialect":         dialect,
        "interfaces":      interfaces,
        "vlans":           vlans,
        "vrfs":            vrfs,
        # Populated separately, live, only for online devices — CDP/LLDP
        # neighbor data is learned operational state, not something that
        # exists in a saved config file no matter how it's parsed. See the
        # neighbor enrichment pass in sync_list_to_netbox.
        "neighbors":       [],
        "running_config":  golden,
        "static_routes":   static_routes,
        "protocol_tags":   protocol_tags,
        "routing_context": routing_context,
    }


# ---------------------------------------------------------------------------
# Cables from LLDP as Prometheus last read it (C1344)
# ---------------------------------------------------------------------------

#: The words every cable that is not made is reported in, by why (C1344): a neighbour is never
#: invented in NetBox, and a link only one end reports is not a cable.
CABLE_WHY = {
    "unmanaged": "{far} is not a managed device of this network: reported, no cable",
    "one_end": "only {by} reports it in LLDP: a cable is made from both ends' reports",
    "no_record": "{far} has no NetBox record yet: import {far} first, then this one again",
    "no_interface": "{dev}'s NetBox record has no interface {port}: import {dev} to add it",
}


def stored_lldp_links(list_name: str, clock=time.time, cached=None) -> dict:
    """The network's LLDP links as the Topology reader last stored them (P.11's reader,
    `readers/topology_graph`: both ends' `lldpRemEntry` as Prometheus scraped them, unioned per
    link and classified). Never a device, never Prometheus per request: the import reads what
    the reader stored, and only while it is within the reader's promise.

    ``{"links": [{a, port_a, b, port_b, kind, reported_by}], "managed": {device: bool},
    "value_at", "error"}``: *error* says why no link is offered (never read, stale, or this
    network not in it), and then *links* is empty, which is not "no links"."""
    import calendar

    from modules import reader_job
    from modules.readers import topology_graph as T

    got = reader_job.read_cached(T.READER_NAME) if cached is None else cached
    good = (got.get("doc") or {}).get("last_good") or {}
    out = {"links": [], "managed": {}, "value_at": good.get("value_at") or "", "error": ""}
    if not good:
        out["error"] = ("the Topology reader has stored no LLDP read yet"
                        + (f" ({got.get('why')})" if got.get("why") else ""))
        return out
    try:
        at = calendar.timegm(time.strptime(good.get("value_at", ""), "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        out["error"] = f"the Topology reader's stored time {good.get('value_at')!r} is not a time"
        return out
    promise = reader_job.page_promise(T.READER)
    if clock() - at > promise:
        out["error"] = (f"the Topology reader's LLDP was last read at {good['value_at']}, more "
                        f"than {promise} s ago")
        return out
    net = ((good.get("value") or {}).get("networks") or {}).get(list_name)
    if net is None:
        out["error"] = f"the Topology reader's last read holds no network {list_name!r}"
        return out
    out["managed"] = {n: bool(v.get("managed")) for n, v in (net.get("nodes") or {}).items()}
    out["links"] = [dict(link) for link in (net.get("layers") or {}).get("physical") or []
                    if not link.get("manager")]
    return out


def _iface_alias_map(interfaces) -> dict:
    """``{name and its abbreviation: NetBox interface id}`` for a device's NetBox interfaces:
    LLDP names a port by its short form (Gi2), the golden and NetBox by its full one."""
    out = {}
    for i in interfaces or []:
        name = i.get("name") or ""
        if name and i.get("id") is not None:
            out.setdefault(name, i["id"])
            out.setdefault(_shorten_iface_name(name), i["id"])
    return out


def lldp_cable_plan(links: list, managed: dict, devices) -> tuple:
    """Which stored LLDP links are cables for *devices* (the names imported now), and which are
    reported instead: ``(cables, not_made)``. A cable is a link BOTH ends report whose ends are
    both managed devices of the network; every other link touching *devices* is reported with
    why (`CABLE_WHY`), never made. Pure: the NetBox half is `_lldp_cable_pass`'s."""
    devices = set(devices)
    cables, not_made = [], []
    for link in links or []:
        a, b = link.get("a", ""), link.get("b", "")
        if not ({a, b} & devices):
            continue
        ends = {"a": a, "port_a": link.get("port_a", ""), "b": b,
                "port_b": link.get("port_b", "")}
        unmanaged = [d for d in (a, b) if not managed.get(d)]
        if unmanaged:
            not_made.append(dict(ends, why=CABLE_WHY["unmanaged"].format(far=unmanaged[0])))
        elif link.get("kind") != "both":
            by = ", ".join(link.get("reported_by") or []) or "one end"
            not_made.append(dict(ends, why=CABLE_WHY["one_end"].format(by=by)))
        else:
            cables.append(ends)
    return cables, not_made


def _cable_words(c: dict) -> str:
    return f"{c['a']} {c['port_a']} to {c['b']} {c['port_b']}"


def _lldp_cable_pass(session, base: str, list_name: str, site_id, device_registry: dict,
                     ipam_stats: dict) -> dict:
    """The import's cables from the Topology reader's stored LLDP (C1344): for every link both
    ends report between two managed devices of the network, at least one of them imported now,
    a cable through `_ensure_cable` (found or created, so recorded as created and listed in the
    preview). An end not imported now is found in NetBox by name at the network's site; one
    NetBox does not hold, or whose interface it does not hold, is reported, never invented.
    Returns ``{"source", "value_at", "error", "cabled", "not_made"}``: *cabled* the links a
    cable holds after this (created now, or already held), *not_made* each other one with why."""
    stored = stored_lldp_links(list_name)
    report = {"source": "the Topology reader's stored LLDP (Prometheus's lldpRemEntry, both "
                        "ends)", "value_at": stored["value_at"], "error": stored["error"],
              "cabled": [], "not_made": []}
    if stored["error"]:
        return report
    cables, report["not_made"] = lldp_cable_plan(stored["links"], stored["managed"],
                                                 device_registry)
    held: dict = {}

    def iface_map(dev: str):
        if dev in device_registry:
            return device_registry[dev].get("nb_iface_map") or {}, ""
        if dev not in held:
            record = _nb_first(session, base, "dcim/devices/", name=dev, site_id=site_id) \
                if site_id is not None else None
            held[dev] = (None if record is None else _iface_alias_map(
                _nb_get(session, base, "dcim/interfaces/", device_id=record["id"])))
        return held[dev], "" if held[dev] is not None else "no_record"

    for c in cables:
        ids, why = {}, ""
        for end, port in (("a", "port_a"), ("b", "port_b")):
            found, missing = iface_map(c[end])
            if missing:
                why = CABLE_WHY["no_record"].format(far=c[end])
                break
            ids[end] = found.get(c[port])
            if not ids[end]:
                why = CABLE_WHY["no_interface"].format(dev=c[end], port=c[port])
                break
        if why:
            report["not_made"].append(dict(c, why=why))
            continue
        try:
            with _attributed_to(c["a"] if c["a"] in device_registry else c["b"]):
                cable = _ensure_cable(session, base, "interface", ids["a"], "interface",
                                      ids["b"], label=_cable_words(c))
            if cable:
                ipam_stats["cables_synced"] = ipam_stats.get("cables_synced", 0) + 1
                report["cabled"].append(c)
        except Exception as exc:                      # noqa: BLE001 (a write that did not land)
            _write_failed(f"cable {_cable_words(c)}", exc, c["a"])
    return report


# ---------------------------------------------------------------------------
# Sync entry points
# ---------------------------------------------------------------------------

def sync_list_to_netbox(list_name: str, devices: list[dict],
                        status_cache: Optional[dict] = None,
                        max_workers: int = 6,
                        dry_run: bool = False, progress_id: str = "",
                        actor: str = "", authority: str = "",
                        cables_from_lldp: bool = False) -> dict:
    """Import a device list into NetBox. Returns a summary dict.

    *progress_id*, when the page supplied one, is where this reports what it
    is doing while it runs (`modules.op_progress`): the requests it has made
    and the device it is on. A 9-device preview makes ~300 requests.

    *cables_from_lldp* (the NetBox page's import, C1344): cables from the Topology reader's
    stored LLDP between managed devices of the network (`_lldp_cable_pass`), reported under
    ``cables``. Off for onboarding's and adoption's own records, whose confirm is not the
    import's preview: a cable is made only through the import's preview and confirm.

    With ``dry_run=True`` no write is issued: reads still hit NetBox, so the
    same code path runs and reports exactly what it *would* create and update.
    That preview is what the confirm modal shows before asking the operator to
    enable writes.

    Writes are attributed to *list_name* so removal can later tell which objects
    NMAS created — see :mod:`modules.netbox_guard`.
    """
    from modules import netbox_guard as _guard

    if dry_run:
        with _guard.dry_run() as plan, _guard.for_list(list_name, actor=actor, authority=authority):
            result = _sync_list_to_netbox_impl(list_name, devices, status_cache, max_workers,
                                               progress_id, cables_from_lldp)
        result["dry_run"] = True
        result["plan"] = plan.summary()
        return result

    if not _guard.writes_allowed():
        return {"ok": False, "blocked": True,
                "error": "NetBox writes are off for every network (Writes allowed, on "
                         "Settings › Installation › Connections, NetBox connection). Review the "
                         "import preview and confirm it with writes permitted."}

    # One NetBox writer per list at a time, across processes (R21): refused, naming the first.
    try:
        with _guard.list_writer(list_name, "import", actor), \
                _guard.for_list(list_name, actor=actor, authority=authority):
            return _sync_list_to_netbox_impl(list_name, devices, status_cache, max_workers,
                                             progress_id, cables_from_lldp)
    except _guard.NetBoxBusy as exc:
        return {"ok": False, "busy": True, "error": f"Not imported: {exc}. Nothing was written."}


def _count_requests(session, progress_id: str) -> None:
    """Count every request this session makes toward *progress_id*: a
    response hook sees each one, whichever helper made it."""
    hooks = getattr(session, "hooks", None)
    if progress_id and isinstance(hooks, dict):
        from modules import op_progress

        hooks.setdefault("response", []).append(
            lambda r, *a, **k: op_progress.tick(progress_id))


def _sync_list_to_netbox_impl(list_name: str, devices: list[dict],
                              status_cache: Optional[dict] = None,
                              max_workers: int = 6, progress_id: str = "",
                              cables_from_lldp: bool = False) -> dict:
    """The sync itself. Always call through :func:`sync_list_to_netbox`."""
    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return {"ok": False, "error": "NetBox URL and API token are not configured"}

    session = _session_from_config(cfg)
    base    = cfg["url"]
    from modules import op_progress
    _count_requests(session, progress_id)
    op_progress.update(progress_id, phase="setting up the region, site and template",
                       devices_total=len(devices), devices_done=0)

    log.info("netbox: starting sync for list '%s' (%d device(s))", list_name, len(devices))

    # Declined edits to objects NMAS does not own. Collected rather than only
    # logged: a refusal nobody reads is the same as no refusal, and the
    # caller renders this.
    provisioning_notes: list = []
    _drain_ensure_failures()     # this sync's failures only
    _drain_write_failures()      # likewise: an aborted sync on this thread leaves none behind

    # Build/refresh the region and site up-front. Device roles are resolved
    # per-device below (router/switch/firewall, matching the app's own
    # device-list role field) rather than one shared generic role for
    # everything — role_id_cache avoids re-resolving the same role per device.
    try:
        region = _ensure_region(session, base, list_name)
        site   = _ensure_site(session, base, list_name, region["id"],
                              notes=provisioning_notes)
    except Exception as exc:
        log.exception("netbox: failed to provision region/site for '%s'", list_name)
        return {"ok": False, "error": f"Failed to set up NetBox region/site: {exc}"}

    _ROLE_DISPLAY_NAMES = {"router": "Router", "switch": "Switch", "firewall": "Firewall"}
    role_id_cache: dict = {}

    def _role_id_for(app_role: str) -> int:
        name = _ROLE_DISPLAY_NAMES.get((app_role or "").lower(), "Network Device")
        if name not in role_id_cache:
            role_id_cache[name] = _ensure_device_role(session, base, name)["id"]
        return role_id_cache[name]

    # Config template — needed for "Render Config" in the NetBox device view.
    # Returns None gracefully on pre-3.5 NetBox instances.
    config_template_id = _ensure_config_template(session, base)

    # List-level VRF — groups all IPs for this list under one VRF in NetBox IPAM.
    # Per-interface VRFs (ip vrf forwarding X) override this on a per-interface basis.
    list_vrf_id: Optional[int] = None
    try:
        list_vrf = _ensure_vrf(session, base, list_name,
                               rd=f"ndm:{_slug(list_name)}")
        list_vrf_id = list_vrf["id"]
        log.info("netbox: list VRF '%s' id=%s", list_name, list_vrf_id)
    except Exception as exc:
        _write_failed(f"list VRF {list_name}", exc)

    # Populate from golden configs — no SSH needed, works for offline devices.
    # The committed manifest, read once: a leased address's interface (C1442).
    manifest, manifest_why = _committed_manifest(list_name)
    if manifest_why:
        log.warning("netbox: %s; no leased address is placed this import", manifest_why)
    scanned: list[dict] = [_scan_device_from_golden(d, list_name, manifest) for d in devices]

    # CDP/LLDP neighbors are learned operational state, not something a
    # golden config file can contain — this is the one piece of the sync
    # that genuinely needs a live session, done only for devices status_cache
    # already reports online, in parallel like the rest of the app's
    # per-device SSH work.
    ip_to_dev = {d.get("ip", ""): d for d in devices}
    online_results = [
        r for r in scanned
        if not r.get("error") and (status_cache or {}).get(r["ip"], False)
    ]
    if online_results:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {
                ex.submit(_fetch_neighbors_live, ip_to_dev[r["ip"]]): r
                for r in online_results if r["ip"] in ip_to_dev
            }
            for fut in as_completed(futs):
                futs[fut]["neighbors"] = fut.result()

    created = 0
    updated = 0
    failed: list[dict] = []
    ipam_stats: dict = {
        "interfaces_synced": 0, "prefixes_synced": 0,
        "ips_synced": 0,
        "vrfs_synced": 1 if list_vrf_id else 0,  # count the list-level VRF
        "vlans_synced": 0, "cables_synced": 0, "tunnels_synced": 0,
        "skipped": [],
    }

    # hostname → {device_id, nb_iface_map} for cable wiring pass
    device_registry: dict = {}

    # SEQUENTIAL ON PURPOSE (the concurrency rule's exception for writes whose
    # order matters; the operator's decision on C199, 2026-09-29). Devices
    # share objects (sites, VLANs, prefixes, VRFs) that are CREATED on first
    # encounter, so two devices written at once would race to create the same
    # object and duplicate it (C133's duplicates, made worse); and the cable
    # pass below needs every device's interfaces to exist first.
    for n_done, result in enumerate(scanned):
        op_progress.update(progress_id, phase="reading and planning each device",
                           devices_done=n_done, current=result.get("hostname", ""))
        if result.get("error"):
            failed.append({"hostname": result["hostname"], "ip": result["ip"], "error": result["error"]})
            continue
        try:
            with _attributed_to(result["hostname"]):
                outcome = _upsert_device(
                    session, base,
                    hostname=result["hostname"],
                    ip=result["ip"],
                    facts=result["facts"],
                    interfaces=result.get("interfaces", []),
                    site_id=site["id"],
                    role_id=_role_id_for(result.get("app_role", "router")),
                    ipam_stats=ipam_stats,
                    vlans=result.get("vlans", []),
                    vrfs=result.get("vrfs", []),
                    running_config=result.get("running_config", ""),
                    config_template_id=config_template_id,
                    static_routes=result.get("static_routes", []),
                    protocol_tags=result.get("protocol_tags", []),
                    routing_context=result.get("routing_context", {}),
                    list_vrf_id=list_vrf_id,
                    mgmt_prefix_len=result.get("mgmt_prefix_len") or 0,
                    netbox_id=result.get("netbox_id"),
                    dialect=result.get("dialect") or "",
                )
                if outcome["action"] == "created":
                    created += 1
                else:
                    updated += 1
                device_registry[result["hostname"]] = {
                    "device_id":    outcome["id"],
                    "nb_iface_map": outcome.get("nb_iface_map", {}),
                    "neighbors":    result.get("neighbors", []),
                }
        except Exception as exc:
            log.exception("netbox: upsert failed for %s", result["hostname"])
            failed.append({"hostname": result["hostname"], "ip": result["ip"], "error": str(exc)})

    op_progress.update(progress_id, phase="cables between devices", devices_done=len(scanned),
                       current="")
    # ── CDP/LLDP → cables (second pass so both endpoints exist) ───────────
    for local_hostname, reg in device_registry.items():
        for cdp in reg.get("neighbors", []):
            remote_hostname = cdp.get("remote_hostname", "")
            if remote_hostname not in device_registry:
                continue   # remote device not in this list — skip
            local_iface  = cdp.get("local_iface", "")
            remote_iface = cdp.get("remote_iface", "")
            if not (local_iface and remote_iface):
                continue
            local_iface_id  = reg["nb_iface_map"].get(local_iface)
            remote_iface_id = device_registry[remote_hostname]["nb_iface_map"].get(remote_iface)
            if not (local_iface_id and remote_iface_id):
                continue
            try:
                with _attributed_to(local_hostname):
                    cable = _ensure_cable(
                        session, base,
                        "interface", local_iface_id,
                        "interface", remote_iface_id,
                    )
                if cable:
                    ipam_stats["cables_synced"] = ipam_stats.get("cables_synced", 0) + 1
            except Exception as exc:
                _write_failed(f"cable {local_iface} -> {remote_hostname}:{remote_iface}",
                              exc, local_hostname)
    cables_report = None
    if cables_from_lldp:
        try:
            cables_report = _lldp_cable_pass(session, base, list_name, site.get("id"),
                                             device_registry, ipam_stats)
        except Exception as exc:                      # noqa: BLE001 (said, never silent)
            log.exception("netbox: the LLDP cable pass failed for '%s'", list_name)
            cables_report = {"source": "the Topology reader's stored LLDP", "value_at": "",
                             "error": f"the cable pass failed: {exc}", "cabled": [],
                             "not_made": []}

    summary = {
        "ok":         True,
        "list":       list_name,
        "region":     region.get("name"),
        "site":       site.get("name"),
        "total":      len(devices),
        "synced":     len([r for r in scanned if not r.get("error")]),
        "created":    created,
        "updated":    updated,
        # `failed` is devices whose whole upsert raised; `write_failures`
        # every write that did not land, `partial` the devices they belong
        # to, and `complete` the claim that everything landed (register C8:
        # this reported failed=0 while twenty write paths failed silently).
        **write_failure_report(failed, _drain_write_failures()),
        "config_template_id": config_template_id,
        "ipam": {
            "interfaces": ipam_stats.get("interfaces_synced", 0),
            "prefixes":   ipam_stats.get("prefixes_synced", 0),
            "ips":        ipam_stats.get("ips_synced", 0),
            "vrfs":       ipam_stats.get("vrfs_synced", 0),
            "vlans":      ipam_stats.get("vlans_synced", 0),
            "cables":     ipam_stats.get("cables_synced", 0),
            "tunnels":    ipam_stats.get("tunnels_synced", 0),
        },
        # What was deliberately not modelled, named per class and device.
        "skipped":    skipped_report(ipam_stats.get("skipped")),
        "notes":      provisioning_notes + _drain_ensure_failures(),
        "timestamp":  time.strftime("%Y-%m-%d %H:%M:%S"),
        "netbox_url": f"{base}/dcim/sites/{site['id']}/",
        "ipam_url":   f"{base}/ipam/prefixes/",
    }
    if cables_report is not None:
        summary["cables"] = cables_report

    # A PREVIEW RECORDS NOTHING (C134). This summary is the RECORD of an
    # import, the one the NetBox page's network row draws as its result and reads
    # back later. The dry run ran this same function, so every import preview
    # overwrote the last real import's record with a claim that an import had
    # happened: measured on the host 2026-09-28, `ok: True, updated 9` stamped
    # at the second of a preview, while nothing was written to NetBox.
    from modules import netbox_guard as _guard

    if not _guard.is_dry_run():
        _record_sync_status(list_name, summary)
    log.info(
        "netbox: sync complete for '%s' — devices created=%d updated=%d failed=%d; "
        "IPAM interfaces=%d prefixes=%d ips=%d vrfs=%d vlans=%d cables=%d tunnels=%d",
        list_name, created, updated, len(failed),
        summary["ipam"]["interfaces"], summary["ipam"]["prefixes"],
        summary["ipam"]["ips"], summary["ipam"]["vrfs"],
        summary["ipam"]["vlans"], summary["ipam"]["cables"],
        summary["ipam"]["tunnels"],
    )
    return summary


_last_delete_failure = threading.local()


def _note_delete_failure(endpoint: str, obj_id, reason: str) -> None:
    from modules.redact import redact_text

    reason = redact_text(reason)[:300]
    log.warning("netbox: DELETE %s/%s refused: %s", endpoint, obj_id, reason)
    _last_delete_failure.reason = reason


def last_delete_failure() -> str:
    """Why the most recent failed `_nb_delete` on this thread failed."""
    return getattr(_last_delete_failure, "reason", "") or "unknown"


def _gone_after_404(session, url: str) -> tuple:
    """``(gone, why)`` after a DELETE answered 404 (C466): read the object back."""
    try:
        back = session.get(url, timeout=15)
    except Exception as exc:                    # noqa: BLE001
        return False, (f"the delete answered 404 and the read-back failed ({type(exc).__name__}), "
                       "so whether it is gone is unknown; the record is kept")
    if back.status_code == 404:
        return True, ""
    if back.ok:
        return False, ("NetBox answered 404 to the delete but still holds the object: its "
                       "delete permission's constraint refused it (C466); kept and recorded")
    return False, (f"the delete answered 404 and the read-back HTTP {back.status_code}, so "
                   "whether it is gone is unknown; the record is kept")


def _nb_delete(session, base: str, path: str, obj_id: int) -> bool:
    """DELETE one NetBox object; True when it is gone (deleted, or a 404 read back as absent:
    a 404 for an object still present is a refusal, C466).

    One of three write chokepoints — see :func:`_nb_post`. Callers are also
    responsible for checking provenance before asking for a delete; this only
    enforces the global gate.
    """
    from modules import netbox_guard as _guard

    endpoint = path.strip("/")
    if _guard.is_dry_run():
        _guard.record_intent("deletes", endpoint, obj_id=obj_id)
        return True

    try:
        _guard.assert_writes_allowed(f"DELETE {endpoint}")
    except _guard.NetBoxWriteBlocked as exc:
        log.warning("netbox: %s", exc)
        return False

    try:
        url = f"{base}/api/{path.lstrip('/')}{obj_id}/"
        r = session.delete(url, timeout=15)
        ok = r.ok
        if r.status_code == 404:
            # C466: NetBox answers 404 both for an object that is gone AND for a delete its
            # constrained permission refused (the object is hidden from the delete, not from a
            # read: view is never constrained). So a 404 is read back: present means REFUSED,
            # kept and recorded; absent means gone; an unreadable answer is not "gone".
            ok, why = _gone_after_404(session, url)
            if not ok:
                _note_delete_failure(endpoint, obj_id, why)
                return False
        if ok:
            _guard.forget_created(_guard.get_current_list(), endpoint, obj_id)
        else:
            # A refused delete (a 409 for a protected object, say) returned
            # False with NO log at all; only an exception was logged, at
            # DEBUG (register C8). Now it says why, and the reason reaches
            # the removal's `failed` list through `_last_delete_failure`.
            _note_delete_failure(endpoint, obj_id,
                                 f"HTTP {r.status_code}: {(getattr(r, 'text', '') or '')[:200]}")
        return ok
    except Exception as exc:
        _note_delete_failure(endpoint, obj_id, str(exc))
        return False


def _nb_read_by_id(session, base: str, endpoint: str, obj_id: int) -> tuple:
    """Fetch one object by id: ``("ok", obj)``, ``("gone", None)`` for a 404
    and nothing else, or ``("unreadable", reason)``.

    GONE AND UNREADABLE ARE DIFFERENT FACTS (register C130). The removal loop
    read this function's old single ``None`` as "already gone" and FORGOT the
    record entry, in the dry run too: a 500, a 403 or a timeout during a
    preview dropped provenance for an object that still existed, leaving it
    tagged and unrecorded, which Remove can never act on, logged at DEBUG.
    """
    try:
        r = session.get(f"{base}/api/{endpoint.strip('/')}/{obj_id}/", timeout=15)
    except Exception as exc:                  # noqa: BLE001
        log.warning("netbox: GET %s/%s failed: %s", endpoint, obj_id, exc)
        return "unreadable", f"the read failed: {exc}"
    if r.status_code == 404:
        return "gone", None
    if not r.ok:
        log.warning("netbox: GET %s/%s returned %s", endpoint, obj_id, r.status_code)
        return "unreadable", f"NetBox answered HTTP {r.status_code}"
    try:
        return "ok", r.json()
    except ValueError as exc:
        return "unreadable", f"NetBox's answer was not JSON: {exc}"


def _nb_get_by_id(session, base: str, endpoint: str, obj_id: int) -> Optional[dict]:
    """Fetch one object by id, or None if it is gone OR unreadable. Only for
    a caller whose None means "unknown" either way (the modification record's
    before-read, which records `before_unknown`). A caller that ACTS on
    absence uses `_nb_read_by_id`, which keeps the two apart."""
    state, obj = _nb_read_by_id(session, base, endpoint, obj_id)
    return obj if state == "ok" else None


#: Removal order, chosen so referential integrity holds: terminations before
#: tunnels, contained objects before containers, site and region last.
#: What a list removal walks, innermost first. **An allowlist, and that is
#: the enforcement.**
#:
#: `extras/tags` IS in the created-object record — NMAS creates the
#: `nmas-managed` tag itself — and is deliberately absent here. **A Remove
#: that deleted its own tag would strip the marking from every object
#: carrying it, and every future Remove would then find nothing to delete**:
#: removal requires tagged AND recorded, so losing the tag makes the whole
#: fleet of NMAS-created objects permanently unremovable and
#: indistinguishable from operator-owned ones.
#:
#: That rule was stated only in `scripts/nmas-netbox-census`'s prose ("the
#: tag definitions themselves; Remove never deletes one") and enforced only
#: by this tuple not mentioning it. `test_netbox_write_gate.py` now pins it,
#: because a rule that lives in one file's docstring and another file's
#: omission is a rule nothing would notice being broken.
_REMOVAL_ORDER = (
    "vpn/tunnels",
    "ipam/ip-addresses",
    "ipam/prefixes",
    "ipam/vlans",
    "dcim/interfaces",
    "dcim/devices",
    "ipam/vrfs",
    "dcim/sites",
    "dcim/regions",
)


#: Objects that belong to ONE device and go when it goes, innermost first.
#: Deliberately short. Everything absent from it -- sites, regions, VRFs,
#: prefixes, VLANs, device types, platforms, manufacturers -- is **shared**,
#: and deleting a shared object to abandon one device would take the other
#: devices in the list with it.
_PER_DEVICE_ORDER = ("ipam/ip-addresses", "dcim/interfaces", "dcim/devices")


def _cascade_preview(session, base: str, planned: list,
                     created: dict, what: str) -> dict:
    """What the DATABASE will take, beyond NMAS's own delete list.

    A removal preview used to be a simulation of NMAS's own loop: it
    enumerated the intent exactly and asked NetBox nothing about the
    consequence. Measured on 2026-09-24 it **listed eight objects while ten
    disappeared** -- the two extra were addresses assigned to an interface
    it deleted, and the database removed them on its behalf. Same rule the
    deploy path keeps and this broke: *what is confirmed is what happens.*

    Never raises. A failure returns `proven: False` with the reason, because
    a preview that could not ask must not render as one that asked and got
    nothing.
    """
    from modules import netbox_cascade

    recorded = {(ep, e.get("id"))
                for ep, entries in (created or {}).items() for e in entries}
    try:
        return netbox_cascade.collateral(session, base, planned, recorded)
    except Exception as exc:                    # noqa: BLE001
        log.warning("netbox: the cascade preview failed for %s: %s", what, exc)
        return {"taken": [], "foreign": [], "proven": False,
                "unproven": [f"the dependents queries did not run: {exc}"]}


def remove_device_from_netbox(list_name: str, hostname: str,
                              dry_run: bool = False, actor: str = "",
                              authority: str = "", netbox_id=None) -> dict:
    """Remove ONE device's NetBox objects, provenance-gated.

    `remove_list_from_netbox` walks everything in the created-id record for a
    list, across `_REMOVAL_ORDER`, which includes the site, the region and
    the VRF. Calling it to abandon a single failed onboarding on a populated
    list would delete **every** NMAS-created object in that list and the
    shared objects the surviving devices depend on.

    So this exists, and it is narrower on purpose: the device, its
    interfaces, its IP addresses, and nothing else. Shared objects are
    reported as **retained**, not skipped -- "skipped" reads as something
    that did not work.

    The provenance rule is unchanged and applied per object: NMAS's own
    created-id record must claim it **and** it must still carry the
    `nmas-managed` tag. Anything failing either test is left alone and named.

    Returns ``{"ok", "deleted", "skipped", "retained", "error"}``.
    """
    from modules import netbox_guard as _guard

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return {"ok": False, "error": "NetBox URL and API token are not configured"}
    if not dry_run and not _guard.writes_allowed():
        return {"ok": False, "blocked": True,
                "error": "NetBox writes are off for every network (Writes allowed, on "
                         "Settings › Installation › Connections, NetBox connection). Run the "
                         "preview and confirm it with writes permitted."}

    session = _session_from_config(cfg)
    base = cfg["url"]

    # BY ID, NEVER BY NAME (C1342): a device of the same name retired before kept its record
    # (Decommissioning, renamed), and a lookup by name could find a record that is not this
    # onboarding's. The id is the one *netbox_id* names (the manifest's), else the one
    # Mercury's created-object record holds for this name (a retired device's entry never
    # matches by name). A record by that name with no id to reach it is named, never deleted.
    if netbox_id in (None, ""):
        mine = [e for e in _guard.live_created(
            (_guard.get_created(list_name, "dcim/devices") or {}).get("dcim/devices") or [])
            if e.get("name") == hostname]
        netbox_id = mine[-1].get("id") if mine else None
    if netbox_id in (None, ""):
        # EXACT name, read only, to say what is there. `test_device_lookup.py` pins this for
        # the import path: a fuzzy hit would name a device that merely resembles this one.
        named = _nb_first(session, base, "dcim/devices/", name=hostname)
        if named is None:
            return {"ok": True, "deleted": [], "skipped": [], "retained": [],
                    "message": f"no device named '{hostname}' in NetBox — nothing "
                               f"to remove"}
        return {"ok": False, "error": (
            f"'{hostname}' (id {named.get('id')}) is not in Mercury's created-object "
            f"record for list '{list_name}', so Mercury will not delete it. "
            f"Remove it in NetBox if that is what you want.")}
    # Gone and unreadable are different facts (C130): only a 404 is "nothing to remove".
    state, device = _nb_read_by_id(session, base, "dcim/devices", int(netbox_id))
    if state == "gone":
        return {"ok": True, "deleted": [], "skipped": [], "retained": [],
                "message": f"NetBox device {netbox_id} ('{hostname}') no longer exists — "
                           f"nothing to remove"}
    if state != "ok":
        return {"ok": False, "error": f"NetBox device {netbox_id} could not be read ({device}): "
                                      "nothing was deleted"}
    if device.get("name") != hostname:
        return {"ok": False, "error": (
            f"NetBox device {netbox_id} is named {device.get('name')!r}, not '{hostname}': "
            f"it is not this device's record, so nothing was deleted")}

    dev_id = device.get("id")
    if not _guard.was_created_by_nmas(list_name, "dcim/devices", dev_id):
        return {"ok": False, "error": (
            f"'{hostname}' (id {dev_id}) is not in Mercury's created-object "
            f"record for list '{list_name}', so Mercury will not delete it. "
            f"Remove it in NetBox if that is what you want.")}
    if not _guard.has_managed_tag(device):
        return {"ok": False, "error": (
            f"'{hostname}' (id {dev_id}) no longer carries the nmas-managed "
            f"tag — treated as operator-owned and left alone.")}

    deleted, skipped, failed = [], [], []

    def _consider(endpoint, obj):
        obj_id = obj.get("id")
        label = obj.get("display") or obj.get("name") or obj.get("address") or ""
        if not _guard.was_created_by_nmas(list_name, endpoint, obj_id):
            skipped.append({"endpoint": endpoint, "id": obj_id, "name": label,
                            "reason": "not in Mercury's created-object record"})
            return
        if not _guard.has_managed_tag(obj):
            skipped.append({"endpoint": endpoint, "id": obj_id, "name": label,
                            "reason": "no nmas-managed tag — operator-owned"})
            return
        if _nb_delete(session, base, f"{endpoint}/", obj_id):
            deleted.append({"endpoint": endpoint, "id": obj_id, "name": label})
            _guard.forget_created(list_name, endpoint, obj_id)
        else:
            # FAILED, not skipped (register C8): a skip is a decision (NMAS
            # did not create it), a failure is an outcome, and one bucket for
            # both drew a refused delete as a deliberate choice.
            failed.append({"endpoint": endpoint, "id": obj_id, "name": label,
                           "reason": last_delete_failure()})

    def _run():
        for endpoint in _PER_DEVICE_ORDER:
            if endpoint == "dcim/devices":
                _consider(endpoint, device)
                continue
            for obj in _nb_get(session, base, f"{endpoint}/", device_id=dev_id):
                _consider(endpoint, obj)

    try:
        if dry_run:
            with _guard.dry_run(), _guard.for_list(list_name, actor=actor, authority=authority):
                _run()
        else:
            # One NetBox writer per list at a time, across processes (R21).
            with _guard.list_writer(list_name, f"removal of {hostname}", actor), \
                    _guard.for_list(list_name, actor=actor, authority=authority):
                _run()
    except _guard.NetBoxBusy as exc:
        return {"ok": False, "busy": True, "error": f"Not removed: {exc}. Nothing was deleted.",
                "deleted": deleted, "skipped": skipped, "failed": failed, "complete": False}
    except Exception as exc:                    # noqa: BLE001
        log.exception("netbox: remove_device_from_netbox failed for %r", hostname)
        return {"ok": False, "error": str(exc), "deleted": deleted,
                "skipped": skipped, "failed": failed, "complete": False}

    # Named, so the operator can see what abandoning one device deliberately
    # did NOT touch. An empty report here would read as "nothing else exists".
    retained = sorted({e for e in _guard.get_created(list_name)
                       if e not in _PER_DEVICE_ORDER})

    log.info("netbox: removed device '%s' from list '%s'%s — %d deleted, "
             "%d skipped", hostname, list_name,
             " (dry run)" if dry_run else "", len(deleted), len(skipped))
    return {"ok": True, "device": hostname, "dry_run": dry_run,
            "deleted": deleted, "skipped": skipped, "retained": retained,
            # A delete NetBox refused, with its reason: an outcome, never a
            # skip (register C8). `complete` is the claim that all landed.
            "failed": failed, "complete": not failed,
            # Only on the preview: after an apply the objects are gone, and
            # the same query would report no consequence for a delete that
            # had one.
            "cascade": (_cascade_preview(session, base, deleted,
                                         _guard.get_created(list_name),
                                         f"device {hostname!r}")
                        if dry_run else None)}


def remove_list_from_netbox(list_name: str, dry_run: bool = False,
                            forget_only: bool = False, actor: str = "",
                            authority: str = "", only=None) -> dict:
    """Remove a device list's objects from NetBox — NMAS-created objects only.

    An object is deleted only when **both** are true:

    * NMAS's own created-id record (``data/netbox_created_ids.json``) says it
      created it for this list, and
    * the object still carries the ``nmas-managed`` tag in NetBox.

    Anything else — a region, site, VRF, or device a human curated by hand — is
    reported as skipped and left alone.

    This previously collected devices with ``site_id=`` and deleted everything
    in the site regardless of origin, then removed the site, region and VRF.
    Against a NetBox populated by hand from a design document that is
    unrecoverable data loss, so provenance is now required.

    Args:
        dry_run: report what would be deleted without deleting anything.
        forget_only: delete nothing; just drop NMAS's record of the list, so
            NetBox keeps every object and NMAS stops claiming ownership.
        only: with *forget_only*, the ``[(endpoint, id), ...]`` to forget and
            nothing else (v2's Stop tracking, bound to its preview: C954).
    """
    from modules import netbox_guard as _guard

    if forget_only:
        # It writes Mercury's record, not NetBox: no master switch, no authority. It is still
        # one writer per list (R21), so an import running for the list is not cut across.
        try:
            with _guard.list_writer(list_name, "stop tracking", actor):
                forgotten = _guard.forget_created(list_name, entries=only)
                _clear_sync_status(list_name)
        except _guard.NetBoxBusy as exc:
            return {"ok": False, "busy": True, "forget_only": True, "list": list_name,
                    "error": f"Not forgotten: {exc}. Mercury's record was not changed."}
        except _guard.CreatedRecordUnreadable as exc:
            return {"ok": False, "forget_only": True, "list": list_name,
                    "error": f"Mercury's created-object record could not be read, so nothing "
                             f"was forgotten: {exc}"}
        log.info("netbox: forgot %d created-object record entr(ies) for list '%s' (nothing "
                 "deleted)", len(forgotten), list_name)
        return {"ok": True, "list": list_name, "forget_only": True, "forgotten": forgotten,
                "devices": 0, "deleted_devices": 0,
                "message": "Mercury no longer tracks these objects. Nothing was deleted from NetBox."}

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return {"ok": False, "error": "NetBox URL and API token are not configured"}

    if not dry_run and not _guard.writes_allowed():
        return {"ok": False, "blocked": True,
                "error": "NetBox writes are off for every network (Writes allowed, on "
                         "Settings › Installation › Connections, NetBox connection). Review the "
                         "removal preview and confirm it with writes permitted."}

    session = _session_from_config(cfg)
    base    = cfg["url"]

    created = _guard.get_created(list_name)
    if not created:
        return {"ok": True, "list": list_name, "devices": 0, "deleted_devices": 0,
                "deleted": [], "skipped": [], "failed": [], "complete": True, "counts": {},
                "message": "Mercury has no record of creating anything in NetBox for this "
                           "list, so there is nothing safe to remove. Objects created "
                           "before this safeguard existed must be removed in NetBox."}

    deleted: list = []
    skipped: list = []
    failed:  list = []
    gone:    list = []
    counts:  dict = {}

    def _run() -> None:
        for endpoint in _REMOVAL_ORDER:
            for entry in list(created.get(endpoint, [])):
                obj_id = entry.get("id")
                name   = entry.get("name", "")
                state, obj = _nb_read_by_id(session, base, endpoint, obj_id)

                if state == "unreadable":
                    # NOT gone (C130): it may still exist. Nothing is deleted
                    # and nothing is forgotten; the removal is incomplete, and
                    # a preview carrying this cannot be confirmed.
                    failed.append({"endpoint": endpoint, "id": obj_id, "name": name,
                                   "reason": f"could not be read, so neither deleted "
                                             f"nor forgotten: {obj}"})
                    continue
                if state == "gone":
                    # NetBox answered 404: already gone, or cascaded by an
                    # earlier device delete. The record entry is dropped only
                    # by a REAL removal: a preview writes nothing (C130).
                    gone.append({"endpoint": endpoint, "id": obj_id, "name": name})
                    if not dry_run:
                        _guard.forget_created(list_name, endpoint, obj_id)
                    continue

                if not _guard.has_managed_tag(obj):
                    skipped.append({"endpoint": endpoint, "id": obj_id,
                                    "name": obj.get("name") or name,
                                    "reason": "no nmas-managed tag — treated as "
                                              "operator-owned"})
                    continue

                if _nb_delete(session, base, f"{endpoint}/", obj_id):
                    deleted.append({"endpoint": endpoint, "id": obj_id,
                                    "name": obj.get("name") or name})
                    counts[endpoint] = counts.get(endpoint, 0) + 1
                else:
                    failed.append({"endpoint": endpoint, "id": obj_id,
                                   "name": obj.get("name") or name,
                                   "reason": last_delete_failure()})

    try:
        if dry_run:
            with _guard.dry_run(), _guard.for_list(list_name, actor=actor, authority=authority):
                _run()
        else:
            # One NetBox writer per list at a time, across processes (R21).
            with _guard.list_writer(list_name, "list removal", actor), \
                    _guard.for_list(list_name, actor=actor, authority=authority):
                _run()
                _clear_sync_status(list_name)
    except _guard.NetBoxBusy as exc:
        return {"ok": False, "busy": True, "error": f"Not removed: {exc}. Nothing was deleted."}
    except Exception as exc:
        log.exception("netbox: remove_list_from_netbox failed for '%s'", list_name)
        return {"ok": False, "error": str(exc)}

    device_count = counts.get("dcim/devices", 0)
    log.info("netbox: removal for list '%s'%s — %d deleted, %d skipped (devices=%d)",
             list_name, " (dry run)" if dry_run else "",
             len(deleted), len(skipped), device_count)

    cascade = (_cascade_preview(session, base, deleted, created,
                                f"list {list_name!r}") if dry_run else None)

    return {
        "ok": True,
        "list": list_name,
        "dry_run": dry_run,
        "deleted": deleted,
        "skipped": skipped,
        # A delete NetBox refused, with its reason: an outcome, never a skip
        # (register C8). `complete` is the claim that everything landed.
        "failed": failed,
        "complete": not failed,
        # Recorded, and NetBox answered 404 (C130): named, not silent. A real
        # removal drops them from the record; a preview only says it would.
        "gone": gone,
        "counts": counts,
        "cascade": cascade,
        # Kept for the existing NetBox tab, which reads both of these.
        "devices": device_count,
        "deleted_devices": device_count,
    }


def _update_sync_status(change, what: str) -> None:
    """THE write of the sync-status file (CONCURRENCY_AUDIT R21): under its lock across
    processes, read, *change(data)*, replaced whole. Its writers shared one ``.tmp`` and the
    spinner flag truncated the file in place, under an in-process lock only. A cache: an
    unreadable file is rebuilt, and a failed write is logged, never raised."""
    from modules.filestore import PathLock, write_atomic

    try:
        with _status_lock, PathLock(lambda: _SYNC_STATUS_FILE):
            data = load_sync_status()
            change(data)
            write_atomic(_SYNC_STATUS_FILE, json.dumps(data, indent=2))
    except Exception as exc:                    # noqa: BLE001
        log.warning("netbox: could not %s in the sync status: %s", what, exc)


def _clear_sync_status(list_name: str) -> None:
    """Drop a list's entry from the persisted sync-status file."""
    def change(data):
        data.get("lists",   {}).pop(list_name, None)
        data.get("running", {}).pop(list_name, None)

    _update_sync_status(change, f"drop {list_name}")


def sync_all_lists_to_netbox(lists_with_devices: list[tuple[str, list[dict]]],
                             status_cache: Optional[dict] = None,
                             dry_run: bool = False, progress_id: str = "",
                             actor: str = "", authority: str = "",
                             cables_from_lldp: bool = False) -> dict:
    """Import multiple device lists sequentially. Each list becomes its own region.

    Sequential on purpose (C199, decided 2026-09-29): lists share NetBox objects
    as devices do (a manufacturer, a platform, the tags), created on first
    encounter, so two lists written at once would race to create them.

    Inherits the write gate and dry-run behaviour of :func:`sync_list_to_netbox`.
    """
    results = []
    overall_ok = True
    for name, devs in lists_with_devices:
        res = sync_list_to_netbox(name, devs, status_cache=status_cache, dry_run=dry_run,
                                  progress_id=progress_id, actor=actor,
                                  authority=authority, cables_from_lldp=cables_from_lldp)
        results.append(res)
        if not res.get("ok"):
            overall_ok = False
    out = {"ok": overall_ok, "results": results,
           "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    if dry_run:
        out["dry_run"] = True
        out["plan"] = _merge_plans(r.get("plan") for r in results)
        # Every list's deliberate skips, so the import-all preview names them
        # as the single-list one does.
        out["skipped"] = merge_skipped(r.get("skipped") for r in results)
    if cables_from_lldp:
        out["cables"] = {r.get("list", ""): r.get("cables") for r in results if r.get("cables")}
    return out


def _merge_plans(plans) -> dict:
    """Combine per-list dry-run plans into one summary."""
    creates, updates, deletes = [], [], []
    for plan in plans:
        if not plan:
            continue
        creates.extend(plan.get("creates", []))
        updates.extend(plan.get("updates", []))
        deletes.extend(plan.get("deletes", []))

    def _counts(items):
        out: dict = {}
        for it in items:
            out[it["endpoint"]] = out.get(it["endpoint"], 0) + 1
        return out

    return {"creates": creates, "updates": updates, "deletes": deletes,
            "create_count": len(creates), "update_count": len(updates),
            "delete_count": len(deletes),
            "creates_by_type": _counts(creates), "updates_by_type": _counts(updates),
            "deletes_by_type": _counts(deletes)}


# ---------------------------------------------------------------------------
# Status persistence (surfaced by the NetBox page, /v2/netbox)
# ---------------------------------------------------------------------------

def _record_sync_status(list_name: str, summary: dict) -> None:
    """Persist the latest sync summary per list to disk."""
    def change(data):
        data.setdefault("lists", {})[list_name] = summary
        data["last_sync"] = summary.get("timestamp")

    _update_sync_status(change, f"record {list_name}'s sync")


def load_sync_status() -> dict:
    """Return the on-disk sync status (empty dict if none yet)."""
    if not os.path.exists(_SYNC_STATUS_FILE):
        return {}
    try:
        with open(_SYNC_STATUS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def sync_status_with_results() -> dict:
    """The stored sync status, each list's summary carrying its RESULT
    (`preview_confirm.netbox_sync_result`, C85), computed on read from the
    stored facts. Not in `load_sync_status()`, which the write path reads and
    would then persist."""
    from modules.preview_confirm import netbox_sync_result

    data = load_sync_status()
    for summary in (data.get("lists") or {}).values():
        if isinstance(summary, dict):
            summary["result"] = netbox_sync_result(summary)
    return data


def set_sync_running(list_name: str, running: bool) -> None:
    """Mark a list's sync as in-progress or done (for UI spinner state)."""
    _update_sync_status(
        lambda data: data.setdefault("running", {}).__setitem__(list_name, bool(running)),
        f"mark {list_name}'s sync {'running' if running else 'done'}")


# ---------------------------------------------------------------------------
# Query API — read-only helpers used by the AI tool layer
# ---------------------------------------------------------------------------

def _nb_ready() -> tuple[bool, str, Any, str]:
    """Return (ok, error_msg, session, base_url) for query calls."""
    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return False, "NetBox URL and API token are not configured", None, ""
    return True, "", _session_from_config(cfg), cfg["url"]


def _compact_device(d: dict) -> dict:
    """Flatten a raw NetBox device record to a compact AI-readable dict."""
    # Some NetBox versions use "display" instead of (or in addition to) "name"
    # on nested objects like device_type and platform — use .get() to avoid KeyError.
    def _name(obj):
        if not isinstance(obj, dict):
            return obj
        return obj.get("name") or obj.get("display") or ""
    def _val(obj):  return obj.get("value") if isinstance(obj, dict) else obj
    return {
        "id":             d.get("id"),
        "name":           d.get("name"),
        "status":         _val(d.get("status")),
        "site":           _name(d.get("site") or {}),
        "role":           _name(d.get("role") or d.get("device_role") or {}),
        "device_type":    _name(d.get("device_type") or {}),
        "platform":       _name(d.get("platform") or {}),
        "serial":         d.get("serial") or "",
        "primary_ip4":    (d.get("primary_ip4") or {}).get("address", ""),
        "primary_ip6":    (d.get("primary_ip6") or {}).get("address", ""),
        "local_context":  d.get("local_context_data") or {},
        "tags":           [t.get("name") for t in (d.get("tags") or [])],
    }


def _compact_interface(i: dict) -> dict:
    def _name(obj): return obj["name"] if isinstance(obj, dict) else obj
    def _val(obj):  return obj.get("value") if isinstance(obj, dict) else obj
    return {
        "name":         i.get("name"),
        "enabled":      i.get("enabled"),
        "type":         _val(i.get("type")),
        "mode":         _val(i.get("mode")),
        "vrf":          _name(i.get("vrf") or {}),
        "lag":          _name(i.get("lag") or {}),
        "mtu":          i.get("mtu"),
        "description":  i.get("description") or "",
        "tagged_vlans": [v.get("vid") for v in (i.get("tagged_vlans") or [])],
        "untagged_vlan": (i.get("untagged_vlan") or {}).get("vid"),
    }


def _resolve_device(session, base: str, name_or_ip: str) -> Optional[dict]:
    """Resolve *name_or_ip* to exactly one NetBox device, or None.

    Exact name first, then IPAM: ``ipam/ip-addresses/?address=`` → the assigned
    interface → its device.

    Deliberately never falls back to a ``q=`` fuzzy search. That fallback took
    the first hit, so asking for "R1" could return "R10" and a template would be
    rendered against, or config pushed to, the wrong device. A clear "not found"
    is the safe answer.
    """
    hit = _nb_first(session, base, "dcim/devices/", name=name_or_ip, limit=1)
    if hit:
        return hit

    # Treat it as an address. Accept a bare host address or one with a prefix.
    candidate = (name_or_ip or "").strip()
    if not candidate:
        return None

    for query in ({"address": candidate}, {"address": candidate.split("/")[0]}):
        try:
            for ip_obj in _nb_get(session, base, "ipam/ip-addresses/", **query):
                assigned = ip_obj.get("assigned_object") or {}
                device = assigned.get("device") or {}
                if device.get("id"):
                    full = _nb_get(session, base, "dcim/devices/", id=device["id"])
                    if full:
                        return full[0]
        except Exception as exc:               # noqa: BLE001
            log.debug("netbox: IPAM lookup for '%s' failed: %s", candidate, exc)

    return None


def netbox_get_device(name_or_ip: str) -> dict:
    """Fetch a single device from NetBox by exact name or by assigned IP address.

    Returns a compact device dict. Never guesses: an ambiguous or partial match
    is reported as not found rather than resolved to the first hit.
    """
    ok, err, session, base = _nb_ready()
    if not ok:
        return {"ok": False, "error": err}
    try:
        hit = _resolve_device(session, base, name_or_ip)
        if not hit:
            return {"ok": False,
                    "error": (f"Device '{name_or_ip}' not found in NetBox by exact name "
                              "or by assigned IP address")}
        return {"ok": True, "device": _compact_device(hit)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def netbox_get_interfaces(name_or_ip: str) -> dict:
    """
    Return all interfaces for a device (by name or primary IP), including
    their assigned IP addresses and VRF.
    """
    ok, err, session, base = _nb_ready()
    if not ok:
        return {"ok": False, "error": err}
    try:
        dev = _resolve_device(session, base, name_or_ip)
        if not dev:
            return {"ok": False,
                    "error": (f"Device '{name_or_ip}' not found in NetBox by exact name "
                              "or by assigned IP address")}
        dev_id = dev["id"]
        ifaces = _nb_get(session, base, "dcim/interfaces/", device_id=dev_id)
        ips    = _nb_get(session, base, "ipam/ip-addresses/", device_id=dev_id)
        ip_by_iface: dict[int, list[str]] = {}
        for ip in ips:
            aif = ip.get("assigned_object")
            if isinstance(aif, dict):
                iid = aif.get("id")
                if iid:
                    ip_by_iface.setdefault(iid, []).append(ip["address"])
        out = []
        for i in ifaces:
            ci = _compact_interface(i)
            ci["ip_addresses"] = ip_by_iface.get(i["id"], [])
            out.append(ci)
        return {"ok": True, "device": dev["name"], "interfaces": out}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def netbox_get_vpn_tunnels(device_name: str = "") -> dict:
    """
    List VPN tunnels from NetBox.  Optionally filter to tunnels that
    involve a specific device (matched against termination descriptions).
    """
    ok, err, session, base = _nb_ready()
    if not ok:
        return {"ok": False, "error": err}
    try:
        params: dict[str, Any] = {"limit": 200}
        if device_name:
            params["q"] = device_name
        tunnels = _nb_get(session, base, "vpn/tunnels/", **params)
        terminations = _nb_get(session, base, "vpn/tunnel-terminations/", **params)
        term_by_tunnel: dict[int, list[dict]] = {}
        for t in terminations:
            tid = (t.get("tunnel") or {}).get("id")
            if tid:
                obj  = t.get("termination") or {}
                term_by_tunnel.setdefault(tid, []).append({
                    "role":    (t.get("role") or {}).get("value"),
                    "ip":      (t.get("outside_ip") or {}).get("address", ""),
                    "device":  obj.get("name") or obj.get("display") or "",
                })
        results = []
        for tn in tunnels:
            results.append({
                "name":         tn.get("name"),
                "status":       (tn.get("status") or {}).get("value"),
                "encapsulation": (tn.get("encapsulation") or {}).get("value")
                                  if isinstance(tn.get("encapsulation"), dict)
                                  else tn.get("encapsulation"),
                "description":  tn.get("description") or "",
                "terminations": term_by_tunnel.get(tn["id"], []),
            })
        return {"ok": True, "tunnels": results}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Seeded definitions: does NetBox still hold what the code defines?
# ---------------------------------------------------------------------------

def _seeded_tag_specs() -> dict:
    """Every tag whose attributes are CODE constants, by slug."""
    from modules.netbox_guard import MANAGED_TAG, MANAGED_TAG_SLUG
    specs = {MANAGED_TAG_SLUG: {"name": MANAGED_TAG, "color": "00bcd4"},
             "static-route": {"name": "static-route", "color": "607d8b"}}
    for proto, color in _PROTOCOL_TAG_COLORS.items():
        specs[proto] = {"name": proto.upper(), "color": color}
    return specs


def _field_value(obj: dict, key: str):
    v = obj.get(key)
    if isinstance(v, dict) and "value" in v:       # NetBox enums
        return v["value"]
    if isinstance(v, list):
        return sorted(str(x) for x in v)
    return v


def seeded_spec_status(session=None, base: str = "") -> dict:
    """Compare every NetBox object NMAS creates from a code-defined spec with
    what NetBox holds now (OPEN_FINDINGS C6 item 2).

    These are create-only: `_ensure_*` makes them once and never updates them,
    so a changed spec never reaches a NetBox that already has the object.

    Per object: ``current``, ``absent`` (created on the next sync that needs
    it), ``differs`` (each field with BOTH operands), or ``unreadable``.
    ``differs`` does not say who moved: the code may have changed since the
    object was created, or somebody edited it in NetBox, and NetBox keeps no
    history to tell which (OPEN_FINDINGS A1). Read-only.
    """
    if session is None:
        ok, err, session, base = _nb_ready()
        if not ok:
            return {"ok": False, "reason": f"NetBox is not reachable: {err}",
                    "objects": []}
    objects = []

    def compare(kind, ident, path, query, spec, keys):
        try:
            found = _nb_first(session, base, path, **query)
        except Exception as exc:                     # noqa: BLE001
            objects.append({"kind": kind, "name": ident, "state": "unreadable",
                            "reason": str(exc)})
            return
        if not found:
            objects.append({"kind": kind, "name": ident, "state": "absent"})
            return
        diffs = []
        for key in keys:
            want = spec.get(key)
            want = sorted(want) if isinstance(want, list) else want
            have = _field_value(found, key)
            if key == "color":
                want, have = str(want).lower(), str(have or "").lower()
            if want != have:
                diffs.append({"field": key, "code": want, "netbox": have})
        objects.append({"kind": kind, "name": ident,
                        "state": "differs" if diffs else "current",
                        "fields": diffs})

    for name, spec in _CUSTOM_FIELDS.items():
        compare("custom field", name, "extras/custom-fields/", {"name": name},
                spec, ("label", "type", "object_types", "description"))
    for slug, spec in _seeded_tag_specs().items():
        compare("tag", slug, "extras/tags/", {"slug": slug}, spec,
                ("name", "color"))
    return {"ok": True, "reason": "", "objects": objects}
