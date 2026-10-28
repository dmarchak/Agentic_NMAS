"""modules/redact.py

Redaction at the **provider boundary**: the last thing that happens before a
payload leaves this process for a model API.

Why here, and not at the golden-config reader. The agent has a whole tool set,
and the readers are not the only source of secrets:

* ``show running-config`` over SSH returns the same SNMP communities and the
  same ``username … password`` lines as the stored golden;
* backups, drift diffs, `show tech`, and any free-form command a user asks the
  agent to run all carry them too;
* a future tool inherits the problem the day it is written.

Redacting at each reader is N places that must each remember. Redacting where
the request is built is one place that cannot be bypassed by adding a tool —
the same reasoning that put the deploy guards in ``prepare_for_deploy()``
rather than in each caller.

**This is not at-rest masking.** Golden configs stay verbatim on disk and in
git: masking them would make ``golden/`` depend on ``data/key.key``, which is
not in the repository, so a private remote would hold configs nobody could
restore a network from. See ``docs/NSOT_MULTINETWORK_AUDIT.md`` §E.

What it cannot do: it redacts values this installation **knows**. A password
typed into a chat message, or one on a device that was never extracted, is not
in the credential store and cannot be matched. Rotation is what makes an
unknown secret harmless; this makes a known one stop travelling.
"""

import logging
import re
import threading
import time

log = logging.getLogger(__name__)

#: Below this length a value is too likely to occur in ordinary config text.
#: Redacting "RO" or "cisco" would corrupt the payload into uselessness while
#: protecting nothing an attacker could not guess. Matches
#: ``hostvars.MIN_CHECKABLE_SECRET``, which draws the line for the same reason.
MIN_REDACTABLE = 8

#: What continues a token around a secret's value: a letter, a digit or `_` (the rule
#: `hostvars._TOKEN_CHAR` applies to intent). A secret that is a part of a longer word has not
#: actually appeared; one bounded by anything else has (C1629): inside a URL's path or
#: userinfo, a file path, a dotted or hyphenated name (`tftp://host/<secret>.cfg`,
#: `flash:/<secret>/`, `cfg.<secret>.bak`). `-`, `.`, `$` and `/` were token characters
#: until 2026-10-24, and such a secret stayed in clear.
_TOKEN_CHAR = r"[A-Za-z0-9_]"

PLACEHOLDER = "<redacted:{label}>"

#: **Positional** redaction: the token that occupies a secret's syntactic slot,
#: whatever its length and whether or not this installation has ever seen it.
#:
#: Value-based redaction alone was measured against the live fleet and covered
#: almost nothing: 14 of 18 stored secrets fall under the 8-character floor —
#: every SNMP community (6 chars) and every plaintext router password (7). The
#: floor cannot simply be lowered, because redacting a 6-character string
#: wherever it appears would corrupt ordinary config text. Position is the
#: discriminator the length never was: ``community X RO`` tells you X is a
#: secret no matter what X is.
#:
#: It also covers what the store has never seen — a device not yet onboarded,
#: a list not yet extracted, a password typed into chat — which value-based
#: redaction cannot reach by construction.
#:
#: The captured value, shared by every pattern below so the rule is stated once.
#:
#: A value cannot begin with these. Found in a real log line:
#:
#:     show running-config | include snmp-server community [in /home/…:2613]
#:
#: An operator *searching* for the community — no value present — and the token
#: the pattern ate was the log formatter's own ``[in``. Masking it corrupted
#: the line without protecting anything. A config keyword named with nothing
#: after it is a mention, not a setting, and the next token belongs to someone
#: else.
#
#: A value MAY be a placeholder already there (C743, 2026-10-13). Refusing every `<` made a
#: second pass backtrack: on `secret 9 <redacted:x>` the optional type number was given up and
#: `9` taken as the value, and on `snmp-server host <ip> version 2c <redacted:x>` the optional
#: clauses were given up and `version` taken. The greedy match now lands on the placeholder,
#: which `_replace` leaves alone, so masking twice changes nothing; the archive steps' check
#: (mask again, compare) reported a leak on every typed secret line until then.
_VALUE = r"((?![\[\]|>(){}])(?!<(?!(?:redacted|missing-secret)[:>]))\S+)"

#: Each entry captures (prefix, secret, suffix); only the middle is replaced.
_POSITIONAL = (
    ("snmp_community", re.compile(
        r"(?i)\b(snmp-server\s+community\s+)" + _VALUE + r"()")),
    # `snmp-server host <ip> [vrf X] [traps|informs] [version {1|2c|3 [auth|
    # noauth|priv]}] <community>`. The optional clauses have to be spelled
    # out, because the pattern that only knew about `version` masked the wrong
    # token on the trap/inform forms and left the community in the clear:
    #
    #   snmp-server host <ip> traps version 2c secretcomm
    #     -> snmp-server host <ip> <redacted:snmp_community> version 2c secretcomm
    #
    # Masking a keyword while publishing the secret beside it is worse than
    # not masking at all — the line looks handled.
    ("snmp_community", re.compile(
        r"(?i)\b(snmp-server\s+host\s+\S+"
        r"(?:\s+vrf\s+\S+)?"
        r"(?:\s+(?:traps|informs))?"
        r"(?:\s+version\s+\S+(?:\s+(?:auth|noauth|priv))?)?"
        r"\s+)" + _VALUE + r"()")),
    # `privilege N` and `algorithm-type X` are both optional, may appear in
    # either order, and either may be absent. The first version allowed only
    # `privilege N`, so
    #     username admin privilege 15 algorithm-type scrypt secret <pw>
    # — the exact line the credential rotation sends — matched nothing and the
    # live password would have reached the log in clear. Caught by a test that
    # generates a password and asserts the redactor can mask it, before any
    # device was touched.
    ("user_password", re.compile(
        r"(?i)\b(username\s+\S+"
        r"(?:\s+(?:privilege\s+\d+|algorithm-type\s+\S+))*"
        r"\s+(?:password|secret)\s+(?:\d+\s+)?)" + _VALUE + r"()")),
    ("enable_secret", re.compile(
        r"(?i)^(\s*enable\s+(?:password|secret)\s+(?:\d+\s+)?)" + _VALUE + r"()",
        re.M)),
    ("key_string", re.compile(
        r"(?i)\b(key-string\s+(?:\d+\s+)?)" + _VALUE + r"()")),
    # `pre-shared-key`, in every documented form (C2074, 2026-10-28;
    # tests/test_redact_ios_shapes.py): an ISAKMP keyring's `pre-shared-key {address <IPv4>
    # [<mask>] | address ipv6 <prefix> | ipv6 <prefix> | hostname <name>} key [N] <k>`, and an
    # IKEv2 keyring peer's `pre-shared-key [local|remote] [0|6] {<k> | hex <hex>}`. The first
    # form of this rule knew only `address <IPv4> key`: it masked the mask, the IPv6 prefix or
    # `hostname`, and IKEv2's `local`, type or `hex`, and printed the key. The value is never
    # one of those keywords (a one-digit key is the value, never a type).
    ("pre_shared_key", re.compile(
        r"(?i)\b(pre-shared-key[ \t]+"
        r"(?:(?:address[ \t]+(?:ipv6[ \t]+)?\S+(?:[ \t]+\S+)?|(?:ipv6|hostname)[ \t]+\S+)"
        r"[ \t]+key[ \t]+|key[ \t]+|(?:local|remote)[ \t]+)?(?:[0-9][ \t]+)?(?:hex[ \t]+)?)"
        r"(?!(?:address|hostname|ipv6|local|remote|hex)\b)" + _VALUE + r"()")),
    ("shared_key", re.compile(
        r"(?i)\b((?:tacacs-server|radius-server)\s+key\s+(?:\d+\s+)?)" + _VALUE + r"()")),
    # C2074 (2026-10-28): the IOS credential shapes still in clear after C745, each found so by a
    # planted line (tests/test_redact_ios_shapes.py holds every form), bound by C745's three
    # rules below (`[ \t]` between tokens, a one-digit type, every shape named by its carrier).
    # A server's key on its host line: `radius-server host <host> [auth-port N] [acct-port N]
    # [timeout N] [retransmit N] … key [0|6|7] <k>`, `tacacs-server host <host> [port N]
    # [timeout N] [single-connection] key [0|7] <k>`, and an AAA group's `server-private <IPv4|
    # IPv6> [auth-port N] [acct-port N] … key [0|7] <k>`. The options between the host and
    # `key` are many and differ by release, so they are not spelled out: any tokens, and the
    # LAST `key` on the line with a value after it is the carrier (a test user named `key`
    # keeps its name; the key after it is masked).
    ("server_host_key", re.compile(
        r"(?i)\b((?:(?:radius|tacacs)-server[ \t]+host|server-private)[ \t]+\S+"
        r"(?:[ \t]+\S+)*[ \t]+key[ \t]+(?:[0-9][ \t]+)?)" + _VALUE + r"()")),
    # A RADIUS dynamic-authorization client's key (`aaa server radius dynamic-author`):
    # `client <host> [vrf X] server-key [0|7] <k> [vrf X]`, or a `server-key [0|7] <k>` line.
    # Named by its carrier (a client, or the line's start), so a word such as
    # `console-server-key` is never read as one.
    ("dynamic_author_key", re.compile(
        r"(?im)((?:^[ \t]*|\bclient[ \t]+\S+(?:[ \t]+vrf[ \t]+\S+)?[ \t]+)"
        r"server-key[ \t]+(?:[0-9][ \t]+)?)" + _VALUE + r"()")),
    # A RADIUS server block's `pac key [0|6|7] <k>`, a line of its own. Leading its line, so a
    # host line's `… pac key <k>` is `server_host_key`'s alone (two rules reading one value
    # would name it twice to the parsers and the config check).
    ("pac_key", re.compile(
        r"(?im)^([ \t]*pac[ \t]+key[ \t]+(?:[0-9][ \t]+)?)" + _VALUE + r"()")),
    # `key config-key password-encrypt <k>`: the master key type 6 passwords are encrypted
    # with. Before `server_key`, which refuses `config-key` too, so an indented line keeps its
    # keyword and loses its value whichever runs first.
    ("config_key", re.compile(
        r"(?i)\b(key[ \t]+config-key[ \t]+password-encrypt[ \t]+)" + _VALUE + r"()")),
    # `ip nhrp authentication <s>` and `ipv6 nhrp authentication <s>` (an NHRP network's
    # string, DMVPN over IPv4 or IPv6).
    ("nhrp_authentication", re.compile(
        r"(?i)\b(ip(?:v6)?[ \t]+nhrp[ \t]+authentication[ \t]+)" + _VALUE + r"()")),
    # An IKEv2 profile's `authentication {local|remote} pre-share key [0|6] <k>` (its keyring's
    # `pre-shared-key` lines are `pre_shared_key`'s; `pre-share` with no `key` names none).
    ("ikev2_pre_share_key", re.compile(
        r"(?i)\b(authentication[ \t]+(?:local|remote)[ \t]+pre-share[ \t]+key[ \t]+"
        r"(?:[0-9][ \t]+)?)" + _VALUE + r"()")),
    # An OSPF virtual link's keys: `area <id> virtual-link <router-id> [authentication …]
    # [hello-interval N] … {authentication-key [0|7] <k> | message-digest-key N md5 [0|7] <k>}`
    # (an interface's are `ospf_key`'s, named by `ip ospf`). The last carrier on the line.
    ("ospf_virtual_link_key", re.compile(
        r"(?i)\b(area[ \t]+\S+[ \t]+virtual-link[ \t]+\S+(?:[ \t]+\S+)*[ \t]+"
        r"(?:authentication-key|message-digest-key[ \t]+\d+[ \t]+md5)[ \t]+(?:[0-9][ \t]+)?)"
        + _VALUE + r"()")),
    # OSPFv3's IPsec keys, named by `ipsec spi N` wherever it is configured (an interface's
    # `ipv6 ospf` or `ospfv3`, an area's, a virtual link's): `authentication ipsec spi N
    # {md5|sha1} [0|7] <key>`, and `encryption ipsec spi N esp {des|3des|aes-cbc
    # {128|192|256}} [0|7] <key> {md5|sha1} [0|7] <key>`, whose two keys are each masked
    # (`esp null` has the authentication key only). The authentication rule's prefix holds
    # the encryption key as one token, masked or not, so either rule may run first.
    ("ospfv3_ipsec_encryption_key", re.compile(
        r"(?i)\b(encryption[ \t]+ipsec[ \t]+spi[ \t]+\d+[ \t]+esp[ \t]+"
        r"(?:3des|des|aes-cbc[ \t]+\d+)[ \t]+(?:[0-9][ \t]+)?)" + _VALUE + r"()")),
    ("ospfv3_ipsec_authentication_key", re.compile(
        r"(?i)\b((?:authentication[ \t]+ipsec[ \t]+spi[ \t]+\d+"
        r"|encryption[ \t]+ipsec[ \t]+spi[ \t]+\d+[ \t]+esp[ \t]+"
        r"(?:null|(?:3des|des|aes-cbc[ \t]+\d+)[ \t]+(?:[0-9][ \t]+)?\S+))"
        r"[ \t]+(?:md5|sha1)[ \t]+(?:[0-9][ \t]+)?)" + _VALUE + r"()")),
    # A server block's key written as digits alone with no type (`radius server <name>`,
    # `tacacs server <name>`, an ISAKMP client group): by its line alone it is a key chain's
    # `key <N>`, an ID, which `server_key` refuses. Told apart by its block: the header at a
    # line's start, its indented children, and a child `key <digits>` ending its line. Seen
    # only where the text holds the block (a configuration, a log, typed words); a caller
    # masking one line at a time cannot tell it from a key chain's ID, and leaves it.
    ("server_block_key", re.compile(
        r"(?im)^((?:(?:tacacs|radius)[ \t]+server"
        r"|crypto[ \t]+isakmp[ \t]+client[ \t]+configuration[ \t]+group)[ \t]+\S+[ \t]*\r?\n"
        r"(?:[ \t]+[^\n]*\n)*?[ \t]+key[ \t]+)(\d+)(?=[ \t]*\r?$)()")),
    # C745 (2026-10-28): the IOS credential shapes this table did not know, each found in
    # clear by a planted line (tests/test_redact_ios_shapes.py holds every form). Three rules
    # bind them all:
    #   * `[ \t]`, never `\s`, between a shape's tokens, so a match never crosses a line: a
    #     `\s+` after an optional number reads ` key 1\n  key-string 7 X` as the number 1 and
    #     the value `key-string`;
    #   * an encryption type is ONE digit (`[0-9][ \t]+`: IOS's 0, 6 and 7), so a numeric
    #     clear value (`authentication-key 12345678`) is the value, never a type;
    #   * every shape names its carrier, never a bare `authentication-key`: NTP's
    #     `ntp authentication-key 1 md5 <k>` read by a bare rule gives the key number as the
    #     type and masks `md5`, leaving the key in clear (the trap C1845 named). NTP has its
    #     own rule, after the key number and the algorithm.
    # `ip ospf authentication-key [0|7] <k>` and `ip ospf message-digest-key N md5 [0|7] <k>`
    # (an interface's OSPF keys; `ip ospf authentication key-chain <name>` names a chain, no
    # secret, and is left alone).
    ("ospf_key", re.compile(
        r"(?i)\b(ip[ \t]+ospf[ \t]+(?:authentication-key|message-digest-key[ \t]+\d+[ \t]+md5)"
        r"[ \t]+(?:[0-9][ \t]+)?)" + _VALUE + r"()")),
    # `neighbor <IPv4|IPv6|peer-group> password [0|7] <pw>` (BGP; `mpls ldp neighbor <ip>
    # password` is the same shape and masked by it).
    ("neighbor_password", re.compile(
        r"(?i)\b(neighbor[ \t]+\S+[ \t]+password[ \t]+(?:[0-9][ \t]+)?)" + _VALUE + r"()")),
    # `snmp-server user <user> <group> [remote <host> [udp-port N] [vrf X]] v3 [encrypted] auth
    # {md5|sha} <auth> [priv {des|3des|aes {128|192|256}} <priv>]`: the clauses spelled out, as
    # the trap host's are, so a user or group named `auth` or `sha` is never read as the
    # keyword. The privacy rule's prefix holds the authentication value (masked or not) as
    # one token, so either rule may run first. AES's key size is required, as IOS requires
    # it: optional, `priv aes 128` with nothing after read the size as the value.
    ("snmp_user_auth", re.compile(
        r"(?i)\b(snmp-server[ \t]+user[ \t]+\S+[ \t]+\S+"
        r"(?:[ \t]+remote[ \t]+\S+(?:[ \t]+udp-port[ \t]+\d+)?(?:[ \t]+vrf[ \t]+\S+)?)?"
        r"[ \t]+v3(?:[ \t]+encrypted)?[ \t]+auth[ \t]+(?:md5|sha)[ \t]+)" + _VALUE + r"()")),
    ("snmp_user_priv", re.compile(
        r"(?i)\b(snmp-server[ \t]+user[ \t]+\S+[ \t]+\S+"
        r"(?:[ \t]+remote[ \t]+\S+(?:[ \t]+udp-port[ \t]+\d+)?(?:[ \t]+vrf[ \t]+\S+)?)?"
        r"[ \t]+v3(?:[ \t]+encrypted)?[ \t]+auth[ \t]+(?:md5|sha)[ \t]+\S+"
        r"[ \t]+priv[ \t]+(?:3des|des|aes[ \t]+\d+)[ \t]+)" + _VALUE + r"()")),
    # `crypto isakmp key [0|6] <k> {address <ip> [<mask>] | address ipv6 <prefix> | hostname
    # <name>}`. The value is never `address` or `hostname`: a one-digit key read as a type
    # would otherwise mask the keyword and print the key.
    ("isakmp_key", re.compile(
        r"(?i)\b(crypto[ \t]+isakmp[ \t]+key[ \t]+(?:[0-9][ \t]+)?)"
        r"(?!(?:address|hostname)\b)" + _VALUE + r"()")),
    # A bare `key [0|6|7] <k>` leading its line: a `tacacs server` or `radius server` block's
    # key, an ISAKMP client group's. Indented, as a block's child prints, or unindented with
    # its type (a program's line stripped, `key 7 <hex>`): an unindented `key <word>` is as
    # often a name or prose (the break-glass preview's operand "key fingerprint" was masked
    # by the first form of this rule), and `key chain <name>` and `key config-key …` lead
    # unindented lines. Never a key chain's `key <N>` (a line that is the number alone, its
    # ID), nor an assignment (`    key = …`, a traceback's source line in a log). A server key
    # that is digits alone, typed with no type number, is a key chain's line by its shape, and
    # one beginning `=` an assignment's, so neither is masked here (the digits alone are
    # `server_block_key`'s, inside a server block). Nor an indented `key config-key …`, whose
    # value is `config_key`'s (C2074).
    ("server_key", re.compile(
        r"(?im)^((?:[ \t]+key[ \t]+(?!\d+\s*$|=|config-key\b)(?:[0-9][ \t]+)?"
        r"|key[ \t]+[067][ \t]+))" + _VALUE + r"()")),
    # `standby [N] authentication [text] <s>`, `vrrp N authentication text <s>`, `glbp N
    # authentication text <s>`: the first-hop protocols' clear strings. Their `md5 key-string`
    # forms are `key_string`'s; `md5 key-chain <name>` names a chain and is left alone.
    ("fhrp_authentication", re.compile(
        r"(?i)\b((?:standby|vrrp|glbp)(?:[ \t]+\d+)?[ \t]+authentication[ \t]+"
        r"(?:text[ \t]+|(?!(?:md5|text)\b)))" + _VALUE + r"()")),
    # `ntp authentication-key N <algorithm> [7] <k> [7]`: IOS prints the type AFTER the value
    # (`ntp authentication-key 1 md5 104D000A0618 7`); a type before it is read too.
    ("ntp_key", re.compile(
        r"(?i)\b(ntp[ \t]+authentication-key[ \t]+\d+[ \t]+\S+[ \t]+(?:[0-9][ \t]+)?)"
        + _VALUE + r"()")),
    ("line_password", re.compile(
        r"(?i)^(\s*password\s+(?:\d+\s+)?)" + _VALUE + r"()", re.M)),
    # `ip http client password [0|7] <secret>` (C477, 2026-10-07): the password `line_password`
    # names only at a line's start, so this one passed every mask and reached intent verbatim.
    ("http_client_password", re.compile(
        r"(?i)\b(ip\s+http\s+client\s+password\s+(?:\d+\s+)?)" + _VALUE + r"()")),
    ("ppp_password", re.compile(
        r"(?i)\b(ppp\s+(?:chap|pap)\s+(?:password|sent-username\s+\S+\s+password)\s+(?:\d+\s+)?)" + _VALUE + r"()")),
    # A URL's user part (C476, 2026-10-05: `https://<user>:<secret>@<host>` in an error left
    # this function unchanged). Any scheme with `user:secret@` loses the whole user part; an
    # http(s) or ftp URL with a user and no password loses it too, because a token is often
    # sent as the user alone. `ssh://git@host` keeps `git`, a name and no secret.
    ("url_userinfo", re.compile(
        r"(\b[a-zA-Z][a-zA-Z0-9+.-]*://)([^/\s:@\"'<>]+:[^/\s@\"'<>]+)(@)")),
    ("url_userinfo", re.compile(
        r"(?i)(\b(?:https?|ftps?)://)([^/\s:@\"'<>]+)(@)")),
    # A SEALED value (C1685, the operator, 2026-10-25: a host read printed the settings file's
    # `enc:v1:` Fernet token, the Anthropic key sealed): ciphertext is a secret's own form, so
    # it is masked as the clear value is, by its shape. One rule, the token's: the settings
    # store's `enc:v1:` prefix and an inventory's encrypted column (`devices.csv`) hold the
    # same Fernet token, so `enc:v1:` is kept and the token after it masked. A Fernet token is
    # version 0x80 and a timestamp, base64url, so it begins `gAAAAA`, and is at least 100
    # characters with its padding (a 16-byte block, an IV and an HMAC; the shortest, one byte
    # sealed, measured 100: `gAAAAA`, 92 more, `==`).
    ("sealed", re.compile(r"(?<![A-Za-z0-9_-])()(gAAAAA[A-Za-z0-9_-]{80,}={0,2})()")),
)

#: Already redacted, or a marker — replacing these again would nest markers.
_ALREADY = re.compile(r"^<(?:redacted|missing-secret)[:>]")


def redact_positional(text: str) -> str:
    """Mask whatever occupies a secret position, regardless of length.

    Structure-preserving: ``snmp-server community`` and the trailing ``RO`` both
    survive, so the model still sees what the line *is*. Idempotent — a token
    that is already a placeholder is left alone.
    """
    if not text:
        return text

    def _sub(label):
        def _replace(match):
            token = match.group(2)
            if _ALREADY.match(token):
                return match.group(0)
            return match.group(1) + PLACEHOLDER.format(label=label) + match.group(3)
        return _replace

    for label, pattern in _POSITIONAL:
        text = pattern.sub(_sub(label), text)
    return text


def replace_positional_values(text: str, replace) -> str:
    """Each value in a secret position replaced by ``replace(label, value, prefix)``: the same
    positions `redact_positional` masks, for a caller that keeps the value elsewhere (the
    parsers turn it into a secret reference, C477). A placeholder, or a `__secret__:` marker
    already in the position, is left alone."""
    if not text:
        return text

    def _sub(label):
        def _replace(match):
            token = match.group(2)
            if _ALREADY.match(token) or token.startswith("__secret__:"):
                return match.group(0)
            return match.group(1) + replace(label, token, match.group(1)) + match.group(3)
        return _replace

    for label, pattern in _POSITIONAL:
        text = pattern.sub(_sub(label), text)
    return text


def _label_for(key: str) -> str:
    """``campus:r1:snmp_community_ro`` → ``snmp_community_ro``.

    The model is told a secret is *there* and what kind it is, which is what it
    needs to reason about the config. It is not told the value.
    """
    return key.rsplit(":", 1)[-1] or "secret"


_cache = {"values": None, "at": 0.0}
_cache_lock = threading.Lock()

#: Seconds a built table is reused. Short enough that a rotation or a new
#: extraction is picked up promptly; long enough that a burst of log records
#: does not decrypt the credential store once per line.
CACHE_TTL = 30.0


#: Values held in memory for ONE operation and never in any store (adopt's
#: supplied credential, 2026-09-29): consulted like the stored ones for as
#: long as the operation runs, never cached, never written.
_transient: dict = {}
_transient_lock = threading.Lock()


class transient_secret:
    """``with transient_secret(value, "adopt:supplied"):`` redacts *value* for
    the block's duration. For a secret the tool must not store: the stores feed
    the table, so a value nobody stored would otherwise never be redacted."""

    def __init__(self, value: str, label: str = "transient"):
        self.value, self.label = value or "", label

    def __enter__(self):
        # The same floor as the stores' values: a short value redacted by
        # value corrupts every line that happens to contain it. What keeps a
        # short one out of a log is that no path formats it into a message.
        if self.value and len(self.value) >= MIN_REDACTABLE:
            with _transient_lock:
                _transient[self.value] = self.label
        return self

    def __exit__(self, *exc):
        with _transient_lock:
            _transient.pop(self.value, None)
        return False


def _with_transient(values: dict) -> dict:
    with _transient_lock:
        if not _transient:
            return values
        return {**values, **_transient}


def invalidate_cache() -> None:
    """Drop the cached table — call after writing a secret."""
    with _cache_lock:
        _cache["values"] = None
        _cache["at"] = 0.0


def known_secret_values() -> dict:
    """``{value: label}`` for every secret this installation holds. Cached.

    **Every list**, not the active one: a payload is redacted for what it
    contains, and which network a secret belongs to does not change whether it
    should leave the process. Same reasoning as
    ``hostvars.assert_no_secret_values()`` — a guard narrowed by list fails
    open when the narrowing is wrong.
    """
    with _cache_lock:
        if (_cache["values"] is not None
                and time.monotonic() - _cache["at"] < CACHE_TTL):
            return _with_transient(_cache["values"])

    out = {}
    try:
        from modules.credentials import get_template_secret, list_template_secrets
        for entry in list_template_secrets():
            value = get_template_secret(entry["name"])
            if value and len(value) >= MIN_REDACTABLE:
                out[value] = _label_for(entry["name"])
    except Exception as exc:                  # noqa: BLE001
        # Counted, not just logged. An unreadable credential store means
        # secrets are NOT being redacted, and the filter never raises — so
        # without this, health() reports "healthy" while the table is empty.
        _note_failure(exc)
        log.error("redact: could not read template secrets (%s) — "
                  "payload will NOT be redacted for them", exc)

    # Device credentials never pass through the template-secret store, and
    # `show running-config` is not the only way they surface: a failed login
    # message or a connection error can echo one back.
    try:
        from modules.credentials import device_credential_values
        for value, label in device_credential_values().items():
            if value and len(value) >= MIN_REDACTABLE:
                out.setdefault(value, label)
    except Exception as exc:                  # noqa: BLE001
        log.debug("redact: device credentials unavailable (%s)", exc)

    with _cache_lock:
        _cache["values"] = out
        _cache["at"] = time.monotonic()
    return _with_transient(out)


def _compile(values: dict):
    """One alternation, longest first, so a longer secret wins over a prefix."""
    if not values:
        return None, {}
    ordered = sorted(values, key=len, reverse=True)
    pattern = re.compile(
        f"(?<!{_TOKEN_CHAR})(" + "|".join(re.escape(v) for v in ordered)
        + f")(?!{_TOKEN_CHAR})")
    return pattern, values


def redact_text(text: str, values: dict = None) -> str:
    """Redact *text* both ways: by known value, and by syntactic position.

    The two are complementary and neither subsumes the other. Value-based
    catches a secret wherever it appears — in prose, a diff, an error message —
    but only if this installation holds it and it clears the length floor.
    Positional catches anything in a secret's slot, including secrets never
    extracted and secrets too short to match safely, but only where the
    surrounding syntax is recognised.

    Positional runs first so that value-based cannot re-wrap a placeholder.
    """
    if not text:
        return text
    text = redact_positional(text)

    values = known_secret_values() if values is None else values
    pattern, table = _compile(values)
    if pattern is None:
        return text
    return pattern.sub(
        lambda m: PLACEHOLDER.format(label=table.get(m.group(1), "secret")), text)


def redact_payload(payload, values: dict = None):
    """Walk a request payload and redact every string in it.

    Structure-preserving: dicts, lists, tuples and strings. Anything else is
    returned unchanged, so a client object or a number passes through.

    The table is resolved **once** per call and threaded down, because a deep
    payload would otherwise decrypt the whole credential store per string.
    """
    values = known_secret_values() if values is None else values

    def _walk(node):
        if isinstance(node, str):
            return redact_text(node, values)
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        if isinstance(node, tuple):
            return tuple(_walk(v) for v in node)
        return node

    return _walk(payload)


# ---------------------------------------------------------------------------
# The egress boundary (C1654): what leaves the host, never what Mercury stores
# ---------------------------------------------------------------------------

#: The shapes `redact_text` leaves in clear because its positions are anchored where a
#: configuration puts them (C1654, measured 2026-10-24: a log line quoting `enable secret 9
#: $9$…` mid-line, a bare `$1$…` hash; and a key or password with no carrier `_POSITIONAL`
#: names, such as a peer's `password 7 <hex>` or `key 1 md5 <x>` in prose. C745's shapes, the
#: neighbor password, OSPF and NTP keys and SNMPv3 users among them, are `_POSITIONAL`'s since
#: 2026-10-28, as are C2074's, a server's key on its host line and an OSPF virtual link's
#: among them, so a placeholder here keeps their label). Applied ONLY to a payload leaving the
#: host (Phase 8's gateway), never to a golden or a store, so it may over-mask: a word after
#: "password" in prose is masked too, which costs the model a word and leaks nothing.
#: Addresses and hostnames are never masked. Each entry captures (prefix, secret, suffix).
_EGRESS = (
    # A secret or password anywhere on a line, an optional type number before it.
    ("egress_password", re.compile(
        r"(?i)\b((?:secret|password)\s+(?:\d+\s+)?)" + _VALUE + r"()")),
    # `key N <x>` anywhere (authentication-key, message-digest-key, key 7, ntp's
    # authentication-key N md5 <x>), an optional algorithm and type before the value.
    ("egress_key", re.compile(
        r"(?i)\b(key\s+\d+\s+(?:(?:md5|sha\S*|hmac-\S+)\s+)?(?:\d+\s+)?)" + _VALUE + r"()")),
    # SNMPv3 `auth <md5|sha…> <x>` and `priv <des|3des|aes [N]> <x>`.
    ("egress_snmp_auth", re.compile(
        r"(?i)\b(auth\s+(?:md5|sha\S*)\s+)" + _VALUE + r"()")),
    ("egress_snmp_priv", re.compile(
        r"(?i)\b(priv\s+(?:des|3des|aes)(?:\s+\d+)?\s+)" + _VALUE + r"()")),
    # A hash-shaped token wherever it stands: crypt's $1$ (MD5), $5$ (SHA-256), and IOS's $8$
    # (PBKDF2), $9$ (scrypt), $14$ (the type 5 successor).
    ("egress_hash", re.compile(
        r"()(?<![A-Za-z0-9_$])(\$(?:1|5|8|9|14)\$[^\s'\"<>]+)()")),
)


def redact_egress(text: str, values: dict = None) -> str:
    """Mask *text* for a payload leaving the host (C1654): `redact_text` (by position and by
    known value), then every secret, password and key value anywhere on a line, SNMPv3's
    auth and priv values, and every hash-shaped token. Idempotent: a placeholder is left
    alone. Never applied to what Mercury stores (goldens stay verbatim)."""
    if not text:
        return text
    text = redact_text(text, values)

    def _sub(label):
        def _replace(match):
            token = match.group(2)
            if _ALREADY.match(token):
                return match.group(0)
            return match.group(1) + PLACEHOLDER.format(label=label) + match.group(3)
        return _replace

    for label, pattern in _EGRESS:
        text = pattern.sub(_sub(label), text)
    return text


def egress_payload(payload, values: dict = None):
    """`redact_egress` over every string of a payload (dicts, lists, tuples), the table of
    known values resolved once, as `redact_payload` does."""
    values = known_secret_values() if values is None else values

    def _walk(node):
        if isinstance(node, str):
            return redact_egress(node, values)
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        if isinstance(node, tuple):
            return tuple(_walk(v) for v in node)
        return node

    return _walk(payload)


def contains_known_secret(payload) -> list:
    """Labels of any known secret present in *payload*. For tests and audits."""
    values = known_secret_values()
    found = []

    def _walk(node):
        if isinstance(node, str):
            for value, label in values.items():
                if re.search(f"(?<!{_TOKEN_CHAR})" + re.escape(value)
                             + f"(?!{_TOKEN_CHAR})", node):
                    found.append(label)
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v)

    _walk(payload)
    return sorted(set(found))


# ---------------------------------------------------------------------------
# The log boundary
# ---------------------------------------------------------------------------

class RedactingFilter(logging.Filter):
    """Redact secrets from log records. Attach to the **handler**, not a logger.

    The app log is the third place secrets leave the process, after the model
    API and the HTTP API. It is also the easiest to forget, because nobody
    writes ``log.info(password)`` on purpose — it arrives inside a config dump,
    an exception message, a Netmiko echo, or a diff.

    Attached to the root handler, so it covers every module's own
    ``logging.getLogger(__name__)`` without each having to remember — the same
    reasoning that put redaction at the provider boundary rather than at each
    reader.

    **Fails open, deliberately.** If redaction raises, the record is written
    unredacted rather than dropped. A log that silently loses entries is a
    worse failure than one that occasionally keeps something it should not:
    the first destroys the record of what happened, and this is the file an
    operator reaches for when something has already gone wrong.

    Failing open only stays defensible while the failure is *visible*, so it is
    counted in module state and surfaced by :func:`health` — a one-time log
    line announcing that the log is unreliable is a note written in the medium
    that just became unreliable.
    """

    #: Re-entry guard. The filter calls `known_secret_values()`, which logs on
    #: failure — and that record re-enters the filter, which calls it again.
    #: Unbounded recursion that can hang the process, not merely the tests it
    #: was first seen in. Thread-local because handlers are shared across
    #: threads and a module-level flag would make one thread's redaction
    #: silently skip another's record.
    _local = threading.local()

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(RedactingFilter._local, "active", False):
            # A record emitted from inside redaction — typically a credential
            # store failure. Skip the VALUE lookup, which is what would recurse,
            # but still redact POSITIONALLY: positional needs no store, and the
            # exception text that brought us here can quote a config line or a
            # ciphertext verbatim. The diagnostic survives, and it survives
            # masked.
            try:
                message = record.getMessage()
                cleaned = redact_positional(message)
                if cleaned != message:
                    record.msg = cleaned
                    record.args = ()
                if record.exc_info or record.exc_text:
                    record.exc_text = redact_positional(
                        record.exc_text
                        or logging.Formatter().formatException(record.exc_info))
                    record.exc_info = None
            except Exception:                 # noqa: BLE001
                pass                          # never lose the diagnostic
            return True
        RedactingFilter._local.active = True
        try:
            values = known_secret_values()
            # Format once here so args are interpolated; a secret is far more
            # often in an arg than in the format string.
            message = record.getMessage()
            cleaned = redact_text(message, values)
            if cleaned != message:
                record.msg = cleaned
                record.args = ()
            if record.exc_info:
                # An exception's text can quote a config line verbatim.
                record.exc_text = redact_text(
                    record.exc_text or logging.Formatter().formatException(
                        record.exc_info), values)
                record.exc_info = None
        except Exception as exc:              # noqa: BLE001
            _note_failure(exc)
        finally:
            RedactingFilter._local.active = False
        return True


# ---------------------------------------------------------------------------
# Failure visibility
# ---------------------------------------------------------------------------

#: Redaction fails open, so the only thing standing between that and a silent
#: leak is somebody noticing. Kept as state rather than only a log line,
#: because a log line saying "the log is unreliable" is written in the medium
#: that just became unreliable.
_failures = {"count": 0, "first_at": "", "last_at": "", "last_error": ""}
_failure_lock = threading.Lock()


def _note_failure(exc: Exception) -> None:
    with _failure_lock:
        first = _failures["count"] == 0
        _failures["count"] += 1
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _failures["last_at"] = stamp
        _failures["last_error"] = type(exc).__name__
        if first:
            _failures["first_at"] = stamp
    if first:
        logging.getLogger(__name__).error(
            "redact: log redaction FAILED (%s) — records are being written "
            "UNREDACTED. See redaction health in /identity/status.",
            type(exc).__name__)


def health() -> dict:
    """Is outbound redaction working? For diagnostics and health badges."""
    with _failure_lock:
        failures = dict(_failures)
    handlers = _handler_coverage()
    probe = canary_report()
    return {
        # The canary is the authority: it asks whether a record reaching each
        # handler comes out masked, rather than whether a filter is attached.
        "healthy": (failures["count"] == 0 and handlers["unprotected"] == 0
                    and probe["leaking"] == 0),
        "canary_handlers_checked": probe["handlers"],
        "canary_leaking": probe["leaking"],
        "canary_leaking_detail": probe["leaking_detail"],
        "redaction_failures": failures["count"],
        "first_failure_at": failures["first_at"],
        "last_failure_at": failures["last_at"],
        "last_error": failures["last_error"],
        "log_handlers_total": handlers["total"],
        "log_handlers_unprotected": handlers["unprotected"],
        "unprotected_handler_types": handlers["types"],
    }


def reset_health() -> None:
    """For tests. Never called by the app."""
    with _failure_lock:
        _failures.update({"count": 0, "first_at": "", "last_at": "",
                          "last_error": ""})


# ---------------------------------------------------------------------------
# Handler coverage
# ---------------------------------------------------------------------------

def _all_handlers() -> list:
    """Every handler attached anywhere, root and named loggers alike."""
    seen, out = set(), []
    loggers = [logging.getLogger()]
    manager = logging.getLogger().manager
    loggers += [lg for lg in manager.loggerDict.values()
                if isinstance(lg, logging.Logger)]
    for logger in loggers:
        for handler in getattr(logger, "handlers", []):
            if id(handler) not in seen:
                seen.add(id(handler))
                out.append(handler)
    return out


def _handler_coverage() -> dict:
    handlers = _all_handlers()
    unprotected = [h for h in handlers
                   if not any(isinstance(f, RedactingFilter) for f in h.filters)]
    return {"total": len(handlers), "unprotected": len(unprotected),
            "types": sorted({type(h).__name__ for h in unprotected})}


#: A line shaped exactly like a secret-bearing config line, with a value that
#: is not a secret anywhere. Pushed through a handler's own filter chain to ask
#: the only question that matters: *does a record reaching THIS handler come out
#: masked?* Inspecting `handler.filters` answers a weaker question — a filter
#: can be present and disabled, shadowed by an earlier filter returning False,
#: or installed on a handler that was later replaced.
#: One line per secret SHAPE, each with its own token so a failure names which
#: shape leaked rather than only that something did.
#:
#: The `algorithm-type` line is here because its absence was a live gap: the
#: pattern allowed `username X [privilege N] secret <v>` but not an
#: `algorithm-type` clause between them, so the exact line the credential
#: rotation sends matched nothing. A canary that only ever tested the shapes we
#: already handled would not have found it, and will not find the next one —
#: so every shape the tool itself EMITS belongs here.
CANARY_LINES = (
    ("snmp_community", "snmp-server community CanaryTokenA1 RO"),
    ("user_password", "username admin privilege 15 password CanaryTokenB2"),
    ("user_secret_algo",
     "username admin privilege 15 algorithm-type scrypt secret CanaryTokenC3"),
    ("enable_secret", "enable secret 9 CanaryTokenD4"),
    # The trap-host form. Its community sits after optional keywords, and the
    # pattern that only knew about `version` masked `traps` and published the
    # community — a line that LOOKS handled is worse than one that does not.
    ("snmp_trap_host",
     "snmp-server host 203.0.113.10 traps version 2c CanaryTokenE5"),
)
CANARY_TOKENS = {label: line.split()[-1] if label != "snmp_community"
                 else "CanaryTokenA1"
                 for label, line in CANARY_LINES}

#: Kept for callers that want a single representative line.
CANARY_LINE = CANARY_LINES[0][1]
CANARY_TOKEN = "CanaryTokenA1"


def canary(handler) -> dict:
    """Would a secret-bearing record survive *handler*'s filters unmasked?

    Runs the handler's real filter chain over a synthetic record. Never emits:
    the record is built and filtered, not handled, so nothing is written
    anywhere and no canary line appears in any log.
    """
    record = logging.LogRecord(
        name="redact.canary", level=logging.INFO, pathname=__file__, lineno=0,
        msg="\n".join(line for _label, line in CANARY_LINES),
        args=(), exc_info=None)
    try:
        for f in list(handler.filters):
            result = f.filter(record) if hasattr(f, "filter") else f(record)
            if result is False:
                # Dropped before reaching the formatter — nothing to leak here.
                return {"ok": True, "dropped": True,
                        "handler": type(handler).__name__}
        message = record.getMessage()
        leaked = sorted(label for label, token in CANARY_TOKENS.items()
                        if token in message)
        return {"ok": not leaked, "dropped": False,
                "handler": type(handler).__name__,
                "leaked_shapes": leaked,
                "target": _handler_target(handler)}
    except Exception as exc:                  # noqa: BLE001
        return {"ok": False, "dropped": False, "handler": type(handler).__name__,
                "error": type(exc).__name__}


def _handler_target(handler) -> str:
    """Where a handler writes, for a report an operator can act on."""
    for attr in ("baseFilename", "stream"):
        value = getattr(handler, attr, None)
        if isinstance(value, str):
            return value
        name = getattr(value, "name", "")
        if name:
            return str(name)
    return ""


def canary_report() -> dict:
    """Run the canary through every handler. This replaces grepping the log."""
    results = [canary(h) for h in _all_handlers()]
    leaking = [r for r in results if not r["ok"]]
    return {"handlers": len(results), "leaking": len(leaking),
            "leaking_detail": leaking, "results": results}


def install_log_redaction(handler) -> bool:
    """Attach :class:`RedactingFilter` to *handler*. Idempotent."""
    if any(isinstance(f, RedactingFilter) for f in handler.filters):
        return False
    handler.addFilter(RedactingFilter())
    return True


def redact_all_handlers() -> int:
    """Install on **every** handler attached anywhere. Returns how many gained it.

    A filter on the root *logger* would not do: a record emitted by a child
    logger is passed to ancestor **handlers** without ancestor logger filters
    being consulted. Handler filters are the only ones every record must pass.

    And one handler is not enough either. The file handler is created only when
    ``app.debug`` is false; a StreamHandler to stdout — which under systemd is
    the journal — would otherwise carry unredacted records to exactly the place
    an operator greps first.
    """
    return sum(1 for handler in _all_handlers() if install_log_redaction(handler))


_guard_installed = False


def guard_new_handlers() -> bool:
    """Make handlers added *later* inherit the filter. Idempotent.

    Coverage established once at startup decays: a library that calls
    ``addHandler`` after boot, a lazily-imported module, a handler swapped at
    runtime. Rather than documenting "remember to re-run redact_all_handlers",
    the capability is bounded at the point where a handler is attached — the
    same move as ``resolve_identity`` losing the ability to mint.
    """
    global _guard_installed
    if _guard_installed:
        return False

    original = logging.Logger.addHandler

    def addHandler(self, hdlr):                # noqa: N802 - matches stdlib
        try:
            install_log_redaction(hdlr)
        except Exception:                      # noqa: BLE001
            pass                               # never break logging setup
        return original(self, hdlr)

    logging.Logger.addHandler = addHandler
    _guard_installed = True
    return True
