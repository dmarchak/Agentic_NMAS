"""The SMTP relay sender: a minimal client on Python's standard `smtplib`, so there is no new
third-party package or licence (docs/HEAL_TO_INTENT.md section 10).

It sends through the installation's relay (`notify_smtp_*`): host, port, TLS required
(STARTTLS or implicit; plain only to a relay on this host's loopback), a username, and a
password a person typed, held by the credential store under ``relay`` and read only here, at
the send, for the login. Certificates are verified (`ssl.create_default_context`). A relay at
an IPv6 address works as at an IPv4 one.

Nothing is sent when the relay's host is empty (the default): `config()` refuses, naming it.
"""

import email.policy
import email.utils
import logging
import smtplib
import ssl
from email.message import EmailMessage

from modules.notify import addresses, message

log = logging.getLogger(__name__)

#: The classes a send opens, module attributes so a test hands in a fake (no test touches a
#: live network).
SMTP = smtplib.SMTP
SMTP_SSL = smtplib.SMTP_SSL
TLS_MODES = ("starttls", "implicit", "none")


class NotConfigured(ValueError):
    """The relay's settings refuse a send, and why."""


def config() -> dict:
    """The relay's settings, checked: ``{"host", "port", "tls", "username", "sender",
    "password_set"}``, or `NotConfigured` naming the setting and its value. The password's
    presence only, never its value."""
    from modules import credentials
    from modules.settings_schema import get_setting

    raw_host = (get_setting("notify_smtp_host", "") or "").strip()
    if not raw_host:
        raise NotConfigured("no relay is set (notify_smtp_host is empty), so no email is sent")
    try:
        host = addresses.check_host(raw_host)
    except ValueError as exc:
        raise NotConfigured(str(exc)) from exc
    tls = get_setting("notify_smtp_tls", "starttls") or "starttls"
    if tls not in TLS_MODES:
        raise NotConfigured(f"notify_smtp_tls is {tls!r}, not one of {', '.join(TLS_MODES)}")
    if tls == "none" and not addresses.is_loopback(host):
        raise NotConfigured(f"notify_smtp_tls is none and the relay {host} is not this host's "
                            "loopback: plain SMTP is allowed only to a relay on loopback")
    sender = (get_setting("notify_smtp_from", "") or "").strip()
    try:
        sender = addresses.check_email(sender)
    except ValueError as exc:
        raise NotConfigured(f"notify_smtp_from: {exc}") from exc
    return {"host": host, "port": int(get_setting("notify_smtp_port", 587) or 587), "tls": tls,
            "username": (get_setting("notify_smtp_username", "") or "").strip(),
            "sender": sender, "password_set": credentials.notify_secret_set("relay")}


def thread_ids(incident: str, sender: str, *, first: bool, token: str) -> dict:
    """The threading headers (section 10: a follow-up carries In-Reply-To and References, so
    mail clients thread it): an incident's first message has the incident's own id; each
    later one its own, replying to the first."""
    domain = sender.rpartition("@")[2].strip("[]") or "mercury.invalid"
    root = f"<incident.{incident}@{domain}>"
    if first:
        return {"Message-ID": root}
    return {"Message-ID": f"<incident.{incident}.{token}@{domain}>", "In-Reply-To": root,
            "References": root}


def build(facts: dict, to: str, cfg: dict, *, first: bool, token: str,
          sent_at: float = None) -> EmailMessage:
    """One message to one recipient: the subject and text through the egress mask (the
    email's one mask), the threading headers. The other header values are Mercury's own and
    shaped: two checked addresses, a date, ids built from the incident's checked id."""
    msg = EmailMessage(policy=email.policy.SMTP)
    msg["From"] = cfg["sender"]
    msg["To"] = addresses.check_email(to)
    msg["Subject"] = message.mask(message.subject(facts))
    msg["Date"] = email.utils.formatdate(sent_at, usegmt=True)
    for k, v in thread_ids(facts["incident"], cfg["sender"], first=first, token=token).items():
        msg[k] = v
    msg["Auto-Submitted"] = "auto-generated"
    # Quoted-printable: 7-bit safe through any relay, whatever a field holds (a relay without
    # 8BITMIME takes it as it is).
    msg.set_content(message.mask(message.text(facts, sent_at=sent_at)), cte="quoted-printable")
    return msg


def send(msg: EmailMessage, cfg: dict, *, timeout: float) -> None:
    """Send *msg* through the relay *cfg* names; raises what the relay or the connection
    raised (the caller records it masked). The password is read here and nowhere else, and
    the message's bytes are refused before connecting if they carry it."""
    from modules import credentials

    password = credentials.get_notify_secret("relay") if cfg.get("username") else ""
    # The bytes as sent, and the text decoded from them (a body may be quoted-printable or
    # base64, where a value is not found as itself).
    sent = msg.as_bytes() + b"\n" + msg.get_content().encode("utf-8") + b"\n" + \
        str(msg["Subject"]).encode("utf-8")
    if message.carries_secret(sent, [password]):
        raise NotConfigured("the message carried the relay's password, so it was not sent")
    context = ssl.create_default_context()
    if cfg["tls"] == "implicit":
        conn = SMTP_SSL(cfg["host"], cfg["port"], timeout=timeout, context=context)
    else:
        conn = SMTP(cfg["host"], cfg["port"], timeout=timeout)
    try:
        conn.ehlo()
        if cfg["tls"] == "starttls":
            # Required: a relay that does not offer it raises SMTPNotSupportedError, and
            # nothing is sent in clear.
            conn.starttls(context=context)
            conn.ehlo()
        if cfg.get("username"):
            conn.login(cfg["username"], password)
        conn.send_message(msg)
    finally:
        try:
            conn.quit()
        except (smtplib.SMTPException, OSError):
            conn.close()
