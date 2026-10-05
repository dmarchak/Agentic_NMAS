"""Credential expiry and health (P.21, signed off 2026-10-03): one reader, hourly, METADATA only.

It never reads, logs or returns a credential's value. For each credential it stores where it
lives, where it is renewed and where the new value goes, its expiry or its age, and a state:

- **An exposed expiry** (NetBox's API token, Proxmox's API token, the TLS certificate of the one
  HTTPS service the tool verifies, Grafana's token as DECLARED in Settings): `expired`, `danger`
  within 7 days, `warning` within 30, `ok` within a year, `listed` beyond a year or never (no
  Needs attention row: the operator's decision), `unknown` when it cannot be read, said why.
- **No expiry, an age** (device credentials from the rotation record; SNMP communities from the
  credential store's `last_rotated`): `warning` past 180 days naming Rotate, `ok` within, and
  `listed` when no record says when it was set.
- **A refusal seen** is the integrations reader's (`refused`, every 60 s): the first 401 or 403
  is a danger row at once, naming a declared expiry.

Each service is asked with the app's own credential; a token list is filtered to the tool's
token by the suffix the service shows, never by printing a key.
"""

import time
from datetime import datetime, timezone

from modules import reader_job

INTERVAL_SECONDS = 3600
#: The signed thresholds (2026-10-03).
WARN_DAYS, DANGER_DAYS, LISTED_DAYS, MAX_AGE_DAYS = 30, 7, 365, 180
DAY = 86400.0


def judge_expiry(expires_at, now: float) -> str:
    """The state of an exposed expiry (epoch seconds, or None for never)."""
    if expires_at is None:
        return "listed"
    left = (expires_at - now) / DAY
    if left <= 0:
        return "expired"
    if left <= DANGER_DAYS:
        return "danger"
    if left <= WARN_DAYS:
        return "warning"
    return "ok" if left <= LISTED_DAYS else "listed"


def judge_age(set_at, now: float) -> str:
    """The state of a credential with no expiry, by its age (epoch seconds, or None)."""
    if not set_at:
        return "listed"
    return "warning" if (now - set_at) / DAY > MAX_AGE_DAYS else "ok"


def _iso(epoch) -> str:
    return (datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if epoch else "")


def _entry(cid, label, *, kind, state, why="", expires_at=None, set_at=None, renew_at="",
           put_at="", now=None) -> dict:
    return {"id": cid, "label": label, "kind": kind, "state": state, "why": why,
            "expires_at": _iso(expires_at), "set_at": _iso(set_at),
            "days": (round(((expires_at or 0) - now) / DAY, 1) if expires_at and now else
                     round((now - set_at) / DAY, 1) if set_at and now else None),
            "renew_at": renew_at, "put_at": put_at}


def _parse_time(text: str):
    if not text:
        return None
    text = str(text).strip()
    if len(text) == 10:
        text += "T00:00:00+00:00"
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def netbox(now: float) -> list:
    """NetBox's API token: its `expires`, from the token list the token itself may read,
    picked by its v2 key."""
    from modules.netbox_client import _nb_ready, get_netbox_config

    ok, err, session, base = _nb_ready()
    put = "Settings > Integrations > NetBox, API token"
    renew = "NetBox: Admin > API tokens"
    if not ok:
        return []
    token = get_netbox_config().get("token") or ""
    try:
        r = session.get(base.rstrip("/") + "/api/users/tokens/", params={"limit": 100},
                        timeout=15)
        r.raise_for_status()
        rows = r.json().get("results") or []
    except Exception as exc:                            # noqa: BLE001
        return [_entry("netbox_token", "NetBox API token", kind="expiry", state="unknown",
                       why=f"the token list could not be read: {type(exc).__name__}",
                       renew_at=renew, put_at=put, now=now)]
    # NetBox 4.6 lists a v2 token (`nbt_<key>.<secret>`) by its KEY and never shows any part of
    # its secret (C378, measured on 4.6.9: `key` the 12-character id, `token` null); the
    # tool's row is the one whose key is its own token's.
    key = token[4:].partition(".")[0] if token.startswith("nbt_") and "." in token else ""
    if not key:
        return [_entry("netbox_token", "NetBox API token", kind="expiry", state="unknown",
                       why=("the tool's token is not a v2 token (nbt_<key>.<secret>), and NetBox "
                            "lists tokens by a v2 key, so which listed token is the tool's cannot "
                            "be told"),
                       renew_at=renew, put_at=put, now=now)]
    mine = [t for t in rows if str(t.get("key") or "") == key]
    if len(mine) != 1:
        return [_entry("netbox_token", "NetBox API token", kind="expiry", state="unknown",
                       why=(f"{len(rows)} token(s) readable and {len(mine)} carry the tool's "
                            "key, so which is the tool's cannot be told"),
                       renew_at=renew, put_at=put, now=now)]
    expires = _parse_time(mine[0].get("expires"))
    return [_entry("netbox_token", "NetBox API token", kind="expiry",
                   state=judge_expiry(expires, now), expires_at=expires,
                   why="" if expires else "NetBox records no expiry for it",
                   renew_at=renew, put_at=put, now=now)]


def _declared(cid, label, setting, *, renew, put, now, list_name: str = "") -> list:
    """A token whose expiry it cannot read itself, by the expiry DECLARED for it in Settings
    (the operator's decisions, 2026-10-03: Grafana's Viewer token; Proxmox's token, not
    widened to read its own record). "never" is a declaration; blank is none yet; a refusal
    is still caught by the integrations probe within a minute."""
    from modules.list_settings import default_layer   # paired with the Default network's clients

    if list_name:     # another network's own configuration (P.8 step 5)
        from modules.list_settings import value as list_value
        declared = (list_value(list_name, setting, "") or "").strip()
    else:
        declared = (default_layer(setting, "") or "").strip()
    if not declared:
        return [_entry(cid, label, kind="expiry", state="listed",
                       why=("no expiry declared yet (" + put + "); a refusal is still caught by "
                            "the integrations probe"),
                       renew_at=renew, put_at=put, now=now)]
    if declared.lower() == "never":
        return [_entry(cid, label + " (declared expiry)", kind="expiry", state="listed",
                       why="declared: it never expires", renew_at=renew, put_at=put, now=now)]
    try:
        expires = _parse_time(declared)
    except ValueError:
        return [_entry(cid, label, kind="expiry", state="unknown",
                       why=f"the declared expiry {declared!r} is not a date (YYYY-MM-DD) or never",
                       renew_at=renew, put_at=put, now=now)]
    return [_entry(cid, label + " (declared expiry)", kind="expiry",
                   state=judge_expiry(expires, now), expires_at=expires, renew_at=renew,
                   put_at=put, now=now)]


def proxmox(now: float) -> list:
    """Proxmox's API token, by its DECLARED expiry: a PVEAuditor token cannot read its own
    record (C380, measured: 403 "Permission check failed"), and it is not widened."""
    from modules.integrations.proxmox import ProxmoxIntegration

    if not ProxmoxIntegration().is_configured():
        return []
    return _declared("proxmox_token", "Proxmox API token", "proxmox_token_expires",
                     renew="Proxmox: Datacenter > Permissions > API Tokens",
                     put="Settings > Integrations > Proxmox VE, token secret and its expiry",
                     now=now)


def _not_after(cert) -> float:
    """A certificate's notAfter, epoch seconds. `not_valid_after_utc` arrived in cryptography 42;
    the host and CI pin 41.0.7, whose `not_valid_after` is naive UTC (C379: AttributeError)."""
    got = getattr(cert, "not_valid_after_utc", None)
    if got is None:
        got = cert.not_valid_after.replace(tzinfo=timezone.utc)
    return got.timestamp()


def tls(now: float) -> list:
    """The TLS certificate of each HTTPS service the tool verifies: its `notAfter`, from the
    handshake itself, verified or not."""
    import socket
    import ssl
    from urllib.parse import urlparse

    from cryptography import x509

    from modules.settings_schema import get_setting

    out = []
    for key, label in (("proxmox_url", "Proxmox"),):
        url = (get_setting(key, "") or "").strip()
        if not url.startswith("https://"):
            continue
        u = urlparse(url)
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        renew = f"{label}: the node's certificate"
        try:
            with socket.create_connection((u.hostname, u.port or 443), timeout=10) as raw:
                with ctx.wrap_socket(raw, server_hostname=u.hostname) as s:
                    der = s.getpeercert(binary_form=True)
            after = _not_after(x509.load_der_x509_certificate(der))
        except Exception as exc:                        # noqa: BLE001
            out.append(_entry(f"tls:{key}", f"{label}'s TLS certificate", kind="expiry",
                              state="unknown", why=f"the handshake could not be read: "
                                                   f"{type(exc).__name__}",
                              renew_at=renew, put_at="nothing in the tool: the service holds it",
                              now=now))
            continue
        out.append(_entry(f"tls:{key}", f"{label}'s TLS certificate", kind="expiry",
                          state=judge_expiry(after, now), expires_at=after, renew_at=renew,
                          put_at="nothing in the tool: the service holds it", now=now))
    return out


def grafana(now: float) -> list:
    """Grafana's token, by the expiry DECLARED when it was entered (the operator's decision:
    a Viewer token cannot read its own)."""
    from modules.list_settings import default_layer_secret   # the Default network's Grafana

    if not default_layer_secret("grafana_token"):
        return []
    return _declared("grafana_token", "Grafana API token", "grafana_token_expires",
                     renew="Grafana: Administration > Service accounts",
                     put="Settings > Integrations > Grafana, API token and its expiry", now=now)


def device_ages(now: float) -> list:
    """Each managed device's login credential, by its last rotation (the rotation record);
    a device with no record of one is listed, no row."""
    from modules.nsot import credential_rotation as cr
    from modules.job_health import known_devices

    names, _why = known_devices()
    last = {}
    for r in cr.rotation_records():
        if r.get("phase") == "rotate" and str(r.get("state", "")).startswith("rotated"):
            try:
                last[r.get("device")] = _parse_time(r.get("at"))
            except ValueError:
                continue
    out = []
    for device in sorted(names):
        at = last.get(device)
        out.append(_entry(f"device:{device}", f"{device}'s login credential", kind="age",
                          state=judge_age(at, now), set_at=at,
                          why="" if at else "no rotation is recorded, so its age is not known",
                          renew_at=f"Rotate credential on {device}'s page",
                          put_at="the rotation records it", now=now))
    return out


def community_ages(now: float) -> list:
    """Each SNMP community the tool holds, by when it was last set (the credential store)."""
    from modules import credentials

    out = []
    for s in credentials.list_template_secrets():
        if "snmp_community" not in s.get("name", ""):
            continue
        at = s.get("last_rotated")
        where = s.get("device") or "the profile"
        out.append(_entry(f"secret:{s['name']}", f"SNMP community ({s.get('list')}, {where})",
                          kind="age", state=judge_age(at, now), set_at=at,
                          why="" if at else "the store records no time it was set",
                          renew_at="change it in intent and deploy it, then set it in the store",
                          put_at="the credential store (template secrets)", now=now))
    return out


def grafana_other_networks(now: float) -> list:
    """Each OTHER network's own Grafana token (P.8 step 5): one entry per configuration,
    named for the networks that use it, by the expiry declared in that network's settings."""
    from modules import integration_groups as IG
    from modules import list_settings as L

    out = []
    for g in IG.groups(("grafana",)):
        if g["id"] == IG.DEFAULT_GROUP or not L.secret(g["list"], "grafana_token"):
            continue
        out += _declared(f"grafana_token@{g['id']}",
                         f"Grafana API token ({', '.join(g['lists'])})", "grafana_token_expires",
                         renew="Grafana: Administration > Service accounts",
                         put=f"Settings > {g['list']} > Integrations > Grafana, its expiry",
                         now=now, list_name=g["list"])
    return out


SOURCES = (netbox, proxmox, tls, grafana, grafana_other_networks, device_ages, community_ages)


def read(now: float = None) -> dict:
    """``{"credentials": [...], "errors": [...]}``: every credential's metadata and state. One
    source that raises is said, never a shorter list read as complete."""
    now = time.time() if now is None else now
    creds, errors = [], []
    for fn in SOURCES:
        try:
            creds += fn(now)
        except Exception as exc:                        # noqa: BLE001
            errors.append(f"{fn.__name__}: {type(exc).__name__}: {exc}")
    return {"credentials": creds, "errors": errors,
            "thresholds": {"warning_days": WARN_DAYS, "danger_days": DANGER_DAYS,
                           "listed_beyond_days": LISTED_DAYS, "max_age_days": MAX_AGE_DAYS}}


READER = reader_job.register(reader_job.Reader(
    name="credential-health",
    what="each credential's expiry or age, metadata only, never a value (P.21)",
    endpoints=("NetBox: GET /api/users/tokens/", "Proxmox: GET /access/users/<user>/token/<id>",
               "the TLS handshake of each HTTPS service the tool verifies",
               "this host: the rotation record and the credential store's metadata"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("an expiry moves by days and an age by months; hourly names one 7 days "
                    "ahead with hours to spare, and a refusal is the integrations reader's, "
                    "every 60 s"),
    read=read,
    invalidates=("credential_health",),
    remedy="Read the error above: it names which source could not be read",
    window="each credential's metadata at the read",
))
