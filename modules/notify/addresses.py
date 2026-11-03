"""What a notification may be sent to: an email address, a relay host, a webhook URL.

IPv4 and IPv6 alike (CLAUDE.md's IPv6 rule): a relay or a webhook at an IPv6 address works,
and an email address may carry an address literal (``[192.0.2.1]``, ``[IPv6:2001:db8::1]``).
Plain transport (SMTP without TLS, a webhook over http) is allowed only to this host's
loopback, where no network carries it (docs/HEAL_TO_INTENT.md section 10).
"""

import ipaddress
import re
from urllib.parse import urlsplit

_LOCAL = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_NAME = re.compile(rf"(?:{_LABEL}\.)+[A-Za-z]{{2,63}}|localhost")


def _ip(text: str):
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def is_loopback(host: str) -> bool:
    """Whether *host* is this host's loopback: ``localhost``, 127.0.0.0/8 or ``::1``
    (brackets allowed). A name other than ``localhost`` is never loopback here: what it
    resolves to is not this check's to trust."""
    host = (host or "").strip().strip("[]").lower()
    if host == "localhost":
        return True
    ip = _ip(host)
    return bool(ip and ip.is_loopback)


def check_host(host: str) -> str:
    """A relay's host: a DNS name or an IPv4 or IPv6 address (brackets dropped). Raises
    ValueError naming what it was given."""
    text = (host or "").strip()
    bare = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    if _ip(bare):
        return str(_ip(bare))
    if len(bare) <= 253 and _NAME.fullmatch(bare):
        return bare.lower()
    raise ValueError(f"the relay's host {host!r} is not a DNS name or an IPv4 or IPv6 address")


def check_email(address: str) -> str:
    """An email address one recipient is, or ValueError naming it. One address, no display
    name, nothing a header could be split on; its domain a name or an address literal."""
    text = (address or "").strip()
    if not text or any(c in text for c in "\r\n\t ,;<>\"()\\\x00"):
        raise ValueError(f"{address!r} is not one email address (no spaces, separators or "
                         "line breaks)")
    local, at, domain = text.rpartition("@")
    if not at or not local or len(local) > 64 or not _LOCAL.fullmatch(local):
        raise ValueError(f"{address!r} is not an email address: its part before @ is not one")
    if domain.startswith("[") and domain.endswith("]"):
        inner = domain[1:-1]
        literal = inner[5:] if inner[:5].lower() == "ipv6:" else inner
        ip = _ip(literal)
        if ip is None or (ip.version == 6) != (inner[:5].lower() == "ipv6:"):
            raise ValueError(f"{address!r}: its address literal is not [IPv4] or [IPv6:...]")
        return f"{local}@[{'IPv6:' if ip.version == 6 else ''}{ip}]"
    if len(domain) > 253 or not _NAME.fullmatch(domain):
        raise ValueError(f"{address!r} is not an email address: {domain!r} is not a domain")
    return f"{local}@{domain.lower()}"


def email_domain(address: str) -> str:
    """The address masked to its domain, as the delivery log keeps it: ``…@example.com``."""
    return "…@" + (address or "").rpartition("@")[2]


def check_webhook_url(url: str) -> str:
    """A webhook's URL: https, or http only to this host's loopback; a host (a name, IPv4, or
    IPv6 in brackets); no user or password in it (a URL is drawn and logged, so a credential
    in it would be too). Raises ValueError naming the comparison made."""
    text = (url or "").strip()
    if not text or any(c in text for c in " \r\n\t\x00"):
        raise ValueError(f"{url!r} is not one URL")
    parts = urlsplit(text)
    try:
        host = parts.hostname
        _port = parts.port              # raises on a port that is not one
    except ValueError as exc:
        raise ValueError(f"{url!r} is not a URL: {exc}") from exc
    if parts.scheme not in ("https", "http") or not host:
        raise ValueError(f"{url!r} is not an https URL with a host")
    if parts.username or parts.password:
        raise ValueError("a webhook URL carries no user or password: the receiver's secret is "
                         "the signing secret, typed on its own")
    if parts.scheme == "http" and not is_loopback(host):
        raise ValueError(f"{url!r} is plain http to {host}, which is not this host's loopback: "
                         "a webhook off this host is https")
    if _ip(host) is None and not _NAME.fullmatch(host):
        raise ValueError(f"{url!r}: its host {host!r} is not a DNS name or an address")
    return text


def url_host(url: str) -> str:
    """The URL's host, as the delivery log keeps a webhook (never its path, which may be a
    receiver's token)."""
    try:
        host = urlsplit(url or "").hostname or ""
    except ValueError:
        return ""
    return f"[{host}]" if ":" in host else host
