"""Notifications: the lean first slice of PHASE8_PLAN 20.7 (board H, part H7;
docs/HEAL_TO_INTENT.md section 10).

- `addresses`: what an email address, a relay host and a webhook URL may be, IPv4 and IPv6
  alike, and the loopback rule for plain transport.
- `teams`: the teams store (named groups, each with its recipients and webhooks), each
  destination verified by a code before use and enabled on its own.
- `message`: an incident event put into words and fields, Mercury's facts first, then the
  link; and the egress mask every byte sent passes through.
- `relay`: the SMTP relay sender (Python's `smtplib`: no third-party package).
- `webhook`: the generic signed webhook (HMAC-SHA256 over the timestamp and the body).
- `delivery`: sending to a team's destinations with retries, the delivery log, the test send
  and the verification codes' sends; a last failure is the `notify`/`failed` row.

Nothing is configured by default, so nothing is sent: no relay host, no team.
"""
