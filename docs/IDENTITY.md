# Identity: built-in local accounts first, central identity as optional connectors (design)

**Design only** (the operator, 2026-11-05). Nothing here is built until both labs are done, with
one exception already decided: the single-user local provider (provider (a) of
[LAB9_SDN_GAP.md](LAB9_SDN_GAP.md) section 5, decision 1) is built straight after the final SDN
lab's hardware sitting ([OFFLINE_OPERATION.md](OFFLINE_OPERATION.md) section 1, amended
2026-11-05). This note designs that provider as the first slice of the release's local accounts,
so it is never thrown away.

**What it changes in the earlier designs.**
- [OFFLINE_OPERATION.md](OFFLINE_OPERATION.md) section 1.3 made Keycloak the product's identity.
  Under the operator's amendment of 2026-11-05, Mercury's own local accounts are the default and
  the first sign-in option. Keycloak becomes an optional bundled identity provider (section 6).
  OFFLINE_OPERATION's smart-card, CRL-grace and "verified person" rules (1.4, 1.5) are kept and
  move into Mercury's own connectors (section 5).
- OFFLINE_OPERATION 1.6 proposed an `Actor-Method:` trailer beside an unchanged
  `Actor-Verified:`. This design instead gives `Actor-Verified:` one value per method (section 4),
  as [NSOT_STAGE10_PLAN.md](NSOT_STAGE10_PLAN.md) section 2.6 first proposed and LAB9_SDN_GAP's
  `Actor-Verified: local` assumes.
- NSOT_STAGE10_PLAN section 2.2(a), the in-app local accounts that 2.2's header note marks
  superseded, is restored as the default and extended (TOTP and WebAuthn, roles, recovery).
- [EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md) section 10.1 (Keycloak per instance) is amended
  by section 7 below.

**The principle it serves:** Mercury functions 100% locally, and online features are optional
extras ([PHASE8_PLAN.md](PHASE8_PLAN.md) section 0, "Standing design principle"). Its first
registered break is C2520: verified identity is Cloudflare Access only.

---

## 0. The need

- **The problem.** A network team must know who changed which device, and must be able to sign
  in when the link to the outside world is down. The moments when a network is broken are the
  moments its management tool is needed most. A tool whose sign-in depends on a cloud service
  is read-only exactly then. Government and closed networks have no route to such a service at
  all.
- **How established tools meet it.** Network management systems sold into enterprises and
  government ship a local user database as the first and always-available method, and add
  external sources as options in an ordered list: TACACS+ or RADIUS, LDAP or Active Directory,
  SAML or OIDC single sign-on, and smart-card (CAC/PIV) client certificates. A local
  administrator stays as the fallback when the external source is down. Roles are mapped from
  directory groups.
- **How Mercury meets it, and where it improves on it.**
  - Local accounts are on every install, need nothing outside the host, and are the first
    option on the sign-in page.
  - Every external source is optional and off until configured. Mercury speaks the standards
    itself (LDAP over TLS, X.509, OIDC, SAML), so no identity product is required.
  - Every record names who acted AND how they were verified (`Actor-Verified:`), readable in
    History. Most tools log the user name and not the method.
  - The roles are the gates Mercury already has (191 declared endpoints, each of one kind), so
    a role cannot drift from what the code enforces.
  - Recovery is a recorded break-glass account and a host-root command, never a hidden
    default account.

---

## 1. Where identity stands today (measured)

The full measurement is OFFLINE_OPERATION sections 1.1 (what `modules/identity.py` does) and 1.2
(every caller). In short, and re-read on 2026-11-05:

- **One verifier.** `identify()` verifies Cloudflare Access's signed assertion
  (`Cf-Access-Jwt-Assertion`, RS256, `aud`, `iss`, keys fetched from the team's certs URL) AND
  a trusted raw socket peer (`cf_access_trusted_peers`). With no internet the first key fetch
  fails, every request is `verifier_unavailable`, and every gated action is refused.
- **The gates.** `modules/route_gates.py` declares 191 mutating endpoints, counted on
  2026-11-05 by the `_g(` calls in `GATES`, by kind:

  | Kind | Endpoints |
  |---|---|
  | `configure` | 88 |
  | `not_device` | 36 |
  | `confirm` | 29 |
  | `approve` | 23 |
  | `reveal` | 10 |
  | `publish_remote` | 5 |

  `SOCKET_GATES` is empty (the `break_glass` socket events left with the terminal). `enforce()`
  calls `identity.require(request, kind, operation)` for every kind but `not_device`.
- **Two answers, no roles.** `may()` asks `require_identity_for_<kind>` (is anyone verified)
  and `require_person_for_<kind>` with `service_may()` reading `service_allowed_operations`
  (is it a person, or a service allowed this operation). Every verified person may do every
  kind (`access_scope()`'s docstring says so).
- **The trailer.** `actor_verification()` returns `access`, `host-shell`, `policy` or `none`.
  History's `VERIFIED_WORDS` (`modules/history_sources.py`) draws each, and an absent trailer
  as "before verification was recorded".
- **What Access absorbs** (C248; NSOT_STAGE10_PLAN 4.2): the app runs Werkzeug's development
  server (`allow_unsafe_werkzeug=True`, `app.py` line 656), binds `0.0.0.0` by default
  (`FLASK_HOST`, `modules/config.py` line 555), has no CSRF token, accepts any Socket.IO origin
  (`cors_allowed_origins="*"`, `app.py` line 106), has no rate limit and no TLS. C248's row
  cites older line numbers for the same three sites.

---

## 2. The shape: providers behind one interface

### 2.1 The interface

As NSOT_STAGE10_PLAN 2.1 proposed: each provider implements `authenticate(request) -> Identity`,
a sign-in flow, a sign-out, and a test. `identify()` stays the one entry point every caller
already uses, and asks the session first.

- **A sign-in creates a Mercury session** (3.5), whatever the provider. Every later request is
  verified by that session, so OIDC, SAML, LDAP and certificates are consulted at sign-in, not
  on every request. The exception is Cloudflare Access while it stays a per-request assertion
  (section 8, and the migration in section 9).
- **`Identity` keeps its fields** and gains `provider` (the method), `account` (the Mercury
  account it resolved to), `groups` and `roles`. `is_identified` stays "verified AND the peer
  is the expected one".

### 2.2 Which providers run

- **Local accounts are always on.** They cannot be turned off, because they hold the
  break-glass account (3.8). An admin may hide the passphrase form for everyone but the
  break-glass account once a connector is working (a decision, section 12).
- **Each connector runs when its settings are complete**, measured as `is_configured()`
  measures Access today: all required values set, else the connector is not offered and the
  Sign-in settings say which value is missing.
- **Several connectors may be on at once.** The sign-in page lists them in a fixed order:
  local accounts, then certificate, then Active Directory, then OIDC, then SAML. A person
  chooses one. This replaces OFFLINE_OPERATION 1.8's "both configured is refused": that rule
  was right for two verifiers of the same per-request header, and is wrong for sign-in methods a
  person chooses between.

### 2.3 The peer condition, per install kind

OFFLINE_OPERATION ("What it must not break") requires two independent conditions: a verified
credential AND a trusted peer. NSOT_STAGE10_PLAN 2.6 instead says local and OIDC sessions do not
use the peer list. This design keeps the peer condition for every provider, with its value set by
the install kind:

| Install kind | The expected peer | Why |
|---|---|---|
| Single-user laptop (provider (a)) | loopback only (`127.0.0.1` or `::1`), and the app binds loopback | nothing on the LAN can reach the sign-in form at all |
| The release (Docker, NSOT_STAGE10_PLAN 4.1) | the bundled nginx's fixed Compose address only | the one listener; the client address is read from exactly one hop |
| With Cloudflare Access as the front door | the tunnel connector's address, as today | unchanged |

An empty list still trusts nobody. This amends NSOT_STAGE10_PLAN 2.6's trusted-peers row
(section 12, decision 7).

---

## 3. Built-in local accounts (the default)

### 3.1 From provider (a) to the release's accounts

Provider (a) is this section with one account, a loopback bind and no second factor required.
The store, the hashing, the session, the CSRF tokens and the `Actor-Verified: local` value are the
release's, so building the release adds accounts, roles and factors to a working path rather than
replacing it.

- **Store:** `data/identity/accounts.json`, owner-only from creation (`config.open_secure`),
  locked across processes and replaced atomically (`modules/filestore.py`: `PathLock`,
  `write_atomic`, `read_json_for_write`), so an unreadable store refuses writes (CLAUDE.md,
  "Several people, tabs and worker processes are assumed"). Where the installation has its
  records PostgreSQL ([NSOT_PHASE4_RECORDS_POSTGRES.md](NSOT_PHASE4_RECORDS_POSTGRES.md)), the
  store may move there later, expand then contract.
- **An account holds:** an immutable user name (the actor), a display name, the passphrase
  hash, its second factors, its role, its linked external identities (section 4.2), whether it
  is the break-glass account, and its state (active, disabled).

### 3.2 Passphrases: argon2id

- **Parameters: argon2id, t=3 iterations, p=4 lanes, m=64 MiB, a 16-byte salt and a 32-byte
  tag.** This is RFC 9106 section 4's "second recommended option", for hosts without 2 GiB to
  spend per hash, and it is argon2-cffi's default (`argon2.profiles.RFC_9106_LOW_MEMORY`).
  - **Why not RFC 9106's first option** (t=1, m=2 GiB, p=4): GOVERNMENT_PROFILE section 1
    runs several installations per node, each budgeted modestly. 2 GiB per concurrent sign-in
    would be most of an installation's memory.
  - **Why not OWASP's minimum** (m=19 MiB, t=2, p=1): 64 MiB costs an attacker more per guess,
    and the hash runs only at sign-in.
  - **The bound:** the hash's time on the smallest supported tier is measured (Measurements,
    section 10), and the parameters are lowered only with that measurement beside them.
  - **Rehash on parameter change:** `check_needs_rehash()` after every successful sign-in,
    which is when the cleartext is available.
- **Policy (NIST SP 800-63B-4, section 3.1.1.2):** at least 15 characters (the floor for a
  password used as a single factor), no composition rules, no forced rotation, a check against
  a shipped list of common and breached passphrases, and every printable character and space
  allowed. NSOT_STAGE10_PLAN 2.2(a)'s 12 characters predates 800-63B-4.
- **Never logged, never returned, never stored in clear**, as `identify()` holds for tokens
  today. A passphrase change ends every other session of that account.

### 3.3 Second factors: TOTP and WebAuthn

- **TOTP (RFC 6238):**
  - 30-second steps; one step back accepted for delay, as section 5.2 recommends. The clock
    tolerance is a measured setting on edge kits (OFFLINE_OPERATION, "Measurements still
    owed": TOTP clock tolerance).
  - A code is accepted once: the last accepted step is stored, and a replay is refused
    ("MUST NOT accept the second attempt", section 5.2).
  - The seed is stored encrypted under `data/key.key` (`secrets_store`), shown once at
    enrolment as a QR code drawn by the page, never sent anywhere.
- **WebAuthn (passkeys and security keys):**
  - Through py_webauthn; user verification required; the relying-party ID is the
    installation's host name.
  - Attestation is not checked against an online metadata service, so enrolment works
    offline. An organisation that requires attested keys names the allowed authenticator
    models as a list (a later option).
- **Recovery codes:** ten single-use codes, hashed like passphrases, shown once at enrolment.
- **Who must have one:** every account except provider (a)'s loopback-only single user
  (recommended; section 12). A card sign-in (5.2) is already two factors (the card and its
  PIN), and a connector's own MFA belongs to the connector.

### 3.4 The roles, mapped onto today's gates

Three roles. NSOT_STAGE10_PLAN 3.1's four (installation administrator, and per network a
network administrator, operator and viewer) arrive later. `admin` here is its installation
administrator, holding every network, and its network administrator role splits out when
per-network roles are built. NSOT_AUTHORIZATION section 4's approver stays a permission of the
administrator, as Stage 10 3.1 reconciled it.

**`may()` asks three questions, in order.** The first two are unchanged; the third is new:
1. Is anyone verified? (`require_identity_for_<kind>`)
2. Is it a person, or a service allowed this operation? (`require_person_for_<kind>`,
   `service_allowed_operations`)
3. Does their role hold this kind on this endpoint?

A gate-off setting (`require_identity_for_<kind>` set false) still opens its kind to anyone, as
today, and the Security posture panel says so. On a US Government profile the twelve
`require_*` settings are locked on, like the marking (GOVERNMENT_PROFILE 2.3; a decision,
section 12).

| Gate kind (endpoints, 2026-11-05) | viewer | operator | admin | Notes |
|---|---|---|---|---|
| A GET (never gated by the table) | yes | yes | yes | a GET that reveals gates itself as `reveal` |
| `not_device` (36) | yes | yes | yes | each re-read in 9.I (NSOT_STAGE10_PLAN 3.3); one that changes Mercury's own state moves to `configure` |
| `confirm` (29) | no | yes | yes | except the endpoints the table marks `admin` (`update.apply`, `update.step_done`) |
| `approve` (23) | no | no | yes, never on a revision they authored | after the `approve` split (NSOT_AUTHORIZATION section 3), `author` is the operator's |
| `configure` (88) | no | no | yes | Stage 10's per-network split later gives network-scope settings to the network administrator |
| `reveal` (10) | no | no | yes | the break-glass export too |
| `publish_remote` (5) | no | no | yes | |
| Accounts, roles, sign-in settings (new `configure` endpoints) | no | no | yes | the last active admin cannot be removed, demoted or disabled (refused by name) |

- **Where the role lives:** a `role` column in the gate table, defaulting from the kind as
  above, with the exceptions named per endpoint. A test holds the table exact both ways, as
  P.3's does (`tests/test_route_gates.py`).
- **Services** keep `require_person_for_*` and `service_allowed_operations` unchanged. When
  NSOT_STAGE10_PLAN 2.5's API tokens replace Cloudflare service tokens, a token carries a role
  too, and question 3 applies to it.
- **Visible, not hidden:** a control the role does not allow stays drawn, disabled, saying
  "requires operator" (NSOT_STAGE10_PLAN 3.6), drawn from `may()` as every gated control is
  today (`modules/preview_confirm.py`, `control_gate`).

### 3.5 Sessions and CSRF

- **Server-side sessions.** The cookie holds only an opaque random id; the session record
  (account, provider, roles at sign-in, created, last seen, the peer, a CSRF token) is in
  `data/identity/sessions.json` under the same lock and atomic replace as the accounts.
- **The cookie:** `__Host-mercury_session`, `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, no
  `Domain`. The `__Host-` prefix stops a sibling subdomain from overwriting it (OWASP's CSRF
  Prevention Cheat Sheet). `Lax` rather than `Strict` because an OIDC or SAML callback is a
  top-level cross-site navigation that must carry the session.
  - On the loopback laptop install there is no TLS. Whether a browser keeps a `Secure` cookie
    from `http://127.0.0.1` is **not verified**; the build measures it in each supported
    browser and, if refused, drops the prefix and `Secure` for the loopback kind only, naming
    it on the posture panel.
- **Lifetimes:** an idle timeout of 1 hour and an absolute lifetime of 12 hours by default,
  inside NIST SP 800-63B-4's AAL2 guidance (inactivity no more than 1 hour, overall no more
  than 24 hours). The session id rotates at sign-in and at every role or factor change.
- **Revocation:** an account's sessions are listed on its page with their peer and age, and
  each can be ended. Disabling an account ends all of its sessions at once.
- **CSRF: synchronizer tokens (C248).** C248 records that no route carries a CSRF token; they
  arrive with sessions.
  - One token per session, sent by every state-changing request in a header. The page carries
    it once: a `<meta>` tag that Mercury's scripts read, and an `hx-headers` attribute on the
    body that every htmx request inherits. The strict CSP therefore needs no inline script
    (`csp.STRICT_POLICY`).
  - Refused before the route runs, in `route_gates.enforce()`, naming both values' presence
    (never the values): "the request's CSRF token does not match this session's".
  - Defence in depth beside it: `Origin` (and `Sec-Fetch-Site`, OWASP's primary Fetch Metadata
    signal) must name this installation; `SameSite=Lax`.
  - For Cloudflare-Access-only requests during the migration (section 9), which carry no
    Mercury session, the `Origin` check alone applies until they sign into a session.
- **Socket.IO:** `cors_allowed_origins` becomes the installation's own origin (today `"*"`,
  `app.py` line 106), and a connection is accepted only with a valid session cookie.

### 3.6 The first-run administrator

- **The first-run lock** (NSOT_STAGE10_PLAN 5.1): until an admin exists, the app serves only
  the setup screen, and only to a browser holding the one-time setup code the installer
  prints. The code expires when the first admin exists.
- **On the loopback laptop install** the bind already excludes the LAN; the setup code is still
  required, because another local user or a browser tab driven by a hostile page could reach
  loopback.
- **Setup creates two accounts:** the first admin (a named person, with a second factor), and
  the break-glass account (3.8). Provider (a) creates only the first, and its recovery is the
  host command of 3.8.

### 3.7 Lockout and rate limits

- **Back-off, not a hard lock, first.** Per account: after 5 consecutive failures, each further
  attempt waits twice as long as the last, from 1 second up to 15 minutes. Per source address:
  at most 30 failed attempts in 10 minutes across all accounts, then the address waits 15
  minutes. A lockout therefore cannot be turned into a denial of service against an admin
  (NSOT_STAGE10_PLAN 2.2(a)).
- **The hard limit NIST requires:** 100 consecutive failures on one authenticator disables it
  (SP 800-63B-4 section 3.2.2, "no more than 100"). An admin re-enables it, recorded. For the
  break-glass account, re-enabling is the host command of 3.8.
- **Recorded:** every failure burst, back-off and disable, with the account and the peer, in the
  identity audit (4.3), and each disable is a Needs attention row that clears when re-enabled.
- **The same limits wrap every connector's sign-in** (an LDAP bind, a certificate sign-in), so a
  directory account cannot be brute-forced through Mercury.
- These numbers are proposals; the build records them beside a measured sign-in rate, as every
  bound is (CLAUDE.md, "Bounds are about 2.5x a measured time").

### 3.8 Recovery: the break-glass account, never a back door

- **The break-glass account** (NSOT_STAGE10_PLAN 2.4): one per installation, created at setup,
  with a passphrase and a second factor. Its credentials are kept by the organisation's own
  sealed process. It is distinct from today's break-glass RECORD (the sealed device
  credentials and `key.key`).
  - It is admin, never a daily account. Every sign-in raises a Needs attention row naming when
    and from where; the row clears only when an admin acknowledges it with who used it and why.
  - Its sign-in can be restricted to named addresses.
  - It is the one account whose passphrase form is never hidden (2.2).
- **When every admin is locked out:** a host command, `scripts/nmas-identity recover`, run as
  root on the installation's host, re-enables the break-glass account and issues it a new
  one-time passphrase and second-factor enrolment.
  - The host's root login is the authentication; the record reads `Actor-Verified: host-shell`
    with the OS login labelled (`identity.host_actor()`).
  - It raises a Critical Needs attention row until an admin acknowledges it.
  - It is the recovery DECISION in [MANUAL_STEPS.md](MANUAL_STEPS.md)'s terms, not LABOUR.
- **What is never built:** a default or hard-coded account or passphrase; an environment
  variable or setting that skips verification (the existing gate-off settings stay recorded,
  shown on the posture panel, and locked on under the US Government profile); a master
  passphrase; a support or vendor account; a reset by email (no mail relay is assumed).

### 3.9 Fully offline

Local accounts need nothing outside the host: the hash, the TOTP check and WebAuthn's
assertion check are all local computation. TOTP depends on a trustworthy clock, which an edge
kit gets from a local reference (EDGE_ARCHITECTURE section 10.3). The air-gapped acceptance
walk (GOVERNMENT_PROFILE 9.6) signs in by every configured method.

---

## 4. Who acted, how it was verified, and the audit

### 4.1 `Actor-Verified:` per method

Each value names how THIS actor was verified. The existing values keep their meaning, so every
commit already written reads as it does now: `access` has only ever meant Cloudflare Access.

| Method | `Actor:` | `Actor-Verified:` | History says |
|---|---|---|---|
| Local account | the account's user name | `local` | the name, "local sign-in" |
| Break-glass account | `break-glass:<installation>` | `local` | "break-glass account", and the person once an admin records who |
| Active Directory (LDAP) | the account's `userPrincipalName` | `ldap` | the name, "directory sign-in" |
| Certificate (CAC/PIV) | the certificate's UPN (5.2) | `x509` | the name, "card sign-in" |
| OIDC | the configured claim (for example `preferred_username` or `upn`) | `oidc` | the name, "signed in through <issuer's display name>" |
| SAML | the configured attribute | `saml` | the name, "signed in through <IdP's display name>" |
| Cloudflare Access | the email, as today | `access` | as today |
| A job a verified request started | that person | that person's method, carried (`carried()`) | as above |
| A standing policy | its setter | `policy`, as today | as today |
| A CLI on the host | the labelled OS login | `host-shell`, as today | as today |
| Anything else | as today | `none`, as today | "not verified" |

- **One value for the break-glass account, `local`,** with the actor naming it: the method is
  the passphrase and second factor, and the actor string is what flags it in History and in
  the Needs attention row. The alternative, a `break-glass` value, is a decision (section 12).
- **`api-token` is reserved** for NSOT_STAGE10_PLAN 2.5's API tokens; services verified by
  Cloudflare keep `access`.
- **History reads every new value before any provider writes one:** `VERIFIED_WORDS` gains the
  new words in the release BEFORE the providers ship (section 9), so a rollback never shows a
  bare `local`. An unknown value still counts as not verified (`history_sources.identity()`).

### 4.2 Linking an external identity to an account

- Every sign-in, by any method, resolves to one Mercury account; the role is the account's.
- **An external identity links by its immutable identifier, never by a name or email** a person
  can choose (OFFLINE_OPERATION 1.4's broker rule):
  - Active Directory: `objectGUID`;
  - OIDC: the issuer and `sub` together;
  - SAML: the IdP's entity ID and a persistent `NameID`;
  - certificate: the UPN from a CA on the allowed list, with the issuer and serial recorded at
    each sign-in (5.2);
  - Cloudflare Access: the verified email, as today.
- **Accounts for external identities** are created at first sign-in with the role their groups
  map to (5.1, 5.3), or refused with "no group of yours maps to a Mercury role" when none
  does. With no group mapping configured, an admin creates the account and links it first.
- **The actor across a migration:** a person who signed in by Access (email) and later by a
  local account (user name) is two actor strings. The account records both, so History draws
  one person, and the separation-of-duties comparison compares accounts, not strings
  (OFFLINE_OPERATION 1.5's alias list, kept).

### 4.3 The identity audit

- **What is recorded:** every sign-in and sign-out, every failure burst, back-off and disable,
  every passphrase or factor change, every account created, linked, disabled or role-changed,
  every session ended by an admin, and every change to the sign-in settings. Each names the
  actor, the method, the peer and the result.
- **Where:** an append-only `data/identity/audit.jsonl`, owner-only, masked at rest (no
  passphrase, code, token, assertion or certificate body; a certificate is named by issuer,
  serial and SHA-256 fingerprint). It is backed up with `data/`.
- **Shown in History** as a Sign-in source beside the existing ones (`modules/history_sources.py`).
  A new History tab is a new screen: its mockup and sign-off come first (CLAUDE.md).

---

## 5. Connectors to central identity, each optional

All are off until configured, and removing one breaks no core function (PHASE8_PLAN section 0).
Each lives behind the provider interface of 2.1, is listed on the sign-in page only when its
settings are complete, and has a Test button on Settings › Sign-in that shows what came back
(the claims, the groups, the certificate fields) so the mapping is set from what the source
really sends (NSOT_STAGE10_PLAN 2.2(b)). In air-gapped mode every connector's destination must
be on the installation's allow-list (GOVERNMENT_PROFILE 9.1).

### 5.1 Active Directory (LDAP)

NSOT_STAGE10_PLAN 2.2(c) placed LDAP after OIDC, "only when a real user needs it". A government
enclave's own AD, with no OIDC front, is that user (section 7), so it is designed here.

- **Transport: LDAPS (port 636) or StartTLS on 389, never plain LDAP.** The server certificate
  is validated against the installation's CA bundle (GOVERNMENT_PROFILE 9.5); a TLS failure
  refuses, naming the server and what failed. There is no setting for cleartext.
- **The bind account:** read-only, its DN a setting, its passphrase in Mercury's credential store
  (`secrets_store`, encrypted under `data/key.key`), typed by the operator into the masked field
  on Settings › Sign-in, never shown again, never logged or returned.
- **Signing in:**
  1. Bind as the service account; search the user base for the configured attribute
     (`sAMAccountName` or `userPrincipalName`) equal to what the person typed, with every
     filter special character escaped (Microsoft's "Search Filter Syntax" table: `*`, `(`,
     `)`, `\`, NUL, `/`).
  2. Exactly one entry or a refusal ("no such directory user", the same words for "several").
  3. Bind as that entry's DN with the typed passphrase, over the same TLS. An empty passphrase
     is refused before any bind, because an empty simple bind is an unauthenticated bind,
     which a server may answer as success. The passphrase is never stored.
- **Nested groups:** membership in each MAPPED group is asked with
  `LDAP_MATCHING_RULE_IN_CHAIN`, OID `1.2.840.113556.1.4.1941`, which "walks the chain of
  ancestry in objects all the way to the root". Base scope on the user's DN with the filter
  `(memberOf:1.2.840.113556.1.4.1941:=<group DN>)`, one query per mapped group. Microsoft warns
  that the subtree form "may be more processor intensive" on high fan-out, so the cost is
  bounded by the number of mapped groups, never by how many groups the person is in.
- **Groups to roles:** by group DN (a CN is not unique), highest role wins, evaluated at every
  sign-in; a person removed from a group loses the role at their next session, and the
  session lifetime (3.5) bounds the lag (NSOT_STAGE10_PLAN 3.4).
- **Offline:** an enclave's AD is on the enclave, so it works with no internet. When the
  directory is down, the connector says so on the sign-in page and local accounts remain.

### 5.2 X.509 client certificates (CAC/PIV)

- **Where TLS terminates.** Mercury has no TLS of its own today (C248; section 1). A client
  certificate needs a TLS listener that asks for one, so this connector depends on
  NSOT_STAGE10_PLAN 4.1's bundled nginx (Stage 9's 9.S):
  - nginx asks for a certificate on the certificate sign-in path only
    (`ssl_verify_client optional`), so other pages do not prompt for a card;
  - it verifies the chain against the configured bundle (`ssl_trusted_certificate`, which is
    not sent to clients, unlike `ssl_client_certificate`), at the depth the bundle needs
    (`ssl_verify_depth`, default 1), and revocation against the local CRL file (`ssl_crl`);
  - it passes `$ssl_client_verify` and `$ssl_client_escaped_cert` in headers it overwrites on
    every request;
  - Mercury reads those headers only from nginx's fixed address (2.3), and from any other peer
    ignores them (the forged-header test).
  - Keycloak's reverse-proxy guide says the same of its own lookup: a forged client-certificate
    header "can be used for authentication" if misconfigured, and "TLS passthrough is
    recommended as a more secure option". Passthrough to a Mercury TLS listener is the
    alternative, at the cost of a second TLS configuration (a decision, section 12).
  - Mercury re-checks what nginx checked: the issuer is on the allowed list, the CRL is
    current, and the serial is not in it. Doing so uses `cryptography`'s CRL API
    (`load_der_x509_crl`, `is_signature_valid`, `get_revoked_certificate_by_serial_number`,
    `next_update_utc` since 42.0.0). Today's pin is `cryptography==41.0.7`, so the build needs
    a lock change.
- **The CA bundle is configurable:** an admin loads the organisation's roots and issuing CAs,
  for example the DoD PKI's, as a file; each CA's subject and SHA-256 fingerprint are drawn for
  checking. Only issuing CAs marked "may sign people in" are accepted, and an optional list of
  certificate-policy OIDs may be required (Keycloak's "Validate Certificate Policy" is the
  same idea).
- **Revocation, offline first:**
  - **CRL (the default):** a local file, loaded by an admin, carried in the release bundle or,
    on an edge kit, in the build standard (OFFLINE_OPERATION 1.4). It is never fetched from
    the certificate's distribution point, which an offline install cannot reach.
  - **Its freshness rule:** a CRL is current until its `nextUpdate`. Past it, certificate
    sign-in is refused in plain words ("the revocation list expired on <date>; load the
    current list"), unless the installation has set a grace period. The grace defaults to
    zero, and a site sets it with a reason from its own measurement (OFFLINE_OPERATION 1.4 and
    its "Measurements still owed"). Keycloak's own option for this, "CRL abort if non updated",
    is described as recommended.
  - **Ahead of expiry:** a Needs attention row appears when less than a quarter of the CRL's
    `thisUpdate` to `nextUpdate` interval remains, naming the date sign-in stops. It clears
    when a newer CRL is loaded.
  - **OCSP (optional):** only when its responder is a configured destination (on the air-gap
    allow-list). Fail-closed: a responder that does not answer is not a pass, and a current
    CRL then decides. nginx's `ssl_ocsp` (1.19.0 and later) supports only `http://` responders,
    and needs a `resolver`.
- **The identity from the certificate:**
  - **Default: the UPN in the subject alternative name's otherName**, type
    `1.3.6.1.4.1.311.20.2.3` (`szOID_NT_PRINCIPAL_NAME`). It is read with `cryptography`'s
    `SubjectAlternativeName` extension, by keeping the `OtherName` entries of that type and
    decoding the DER `UTF8String`.
  - **On a DoD CAC's PIV Authentication certificate**, that UPN is built from the EDIPI and ends
    in `@mil`, according to secondary sources (an AWS whitepaper, vendor notes and a DoD-hosted
    page that did not load). **Not verified against a DoD source.**
  - The account is linked by that UPN (4.2), only from an allowed issuing CA. The issuer,
    serial and fingerprint are recorded at each sign-in.
  - An installation may also pin an account to its certificate's issuer and serial at first
    sign-in. This is the "strong" style of mapping idmanagement.gov's Windows smart-card guide
    lists (`X509IssuerSerial`, `X509SKI`, `X509SHA1PublicKey`), at the cost of a re-link each
    time a card is reissued (a decision, section 12).
  - Alternatives, chosen in settings: the SAN email (`rfc822Name`), or the subject's CN by an
    anchored pattern.
- **The card's PIN never reaches Mercury:** the browser and the operating system's middleware
  ask for it. A card sign-in is two factors, so no TOTP is asked on top.

### 5.3 OIDC as a relying party

The NSOT_STAGE10_PLAN 2.2(b) design, unchanged in substance:
- discovery from the issuer URL;
- the authorization code flow with PKCE;
- the ID token's signature checked against the issuer's keys (cached under today's
  `jwks_ttl()` bound, an unknown `kid` refreshing once), with `iss`, `aud`, `exp`, `iat` and
  `nonce` checked;
- the groups claim named in settings, mapped to roles as in 5.1;
- the client secret held in `secrets_store`.

The issuer's tokens are not kept past sign-in: the Mercury session holds what was verified. An
on-site issuer (an organisation's own Keycloak, AD FS or the bundled one of section 6) keeps it
offline. Through it an edge kit reaches "Log in with HQ" when the link is up.

### 5.4 SAML as a relying party

For organisations whose identity provider offers only SAML.
- SP-initiated sign-in. The response or assertion must be signed by the configured IdP
  certificate, with the audience, recipient, `NotOnOrAfter` and `InResponseTo` checked, and
  each assertion ID kept until it expires so a replay is refused.
- The linking identifier is a persistent `NameID`; the actor and groups are configured
  attributes.
- **Built after OIDC, when an installation needs it** (recommended, section 12): every
  identity provider in NSOT_STAGE10_PLAN 2.2(b)'s list also speaks OIDC, and SAML's XML
  signature handling is the most error-prone path here.

### 5.5 The libraries a build would use

A shipped library's licence is the operator's to approve (CLAUDE.md, Phase 7 operating mode,
stop 3), each recorded in `docs/THIRD_PARTY.json` when approved. Read from PyPI and the
projects' licence files on 2026-11-05.

| Need | Library | Licence | Notes |
|---|---|---|---|
| argon2id | argon2-cffi 25.1.0 | MIT | its default parameters are 3.2's |
| TOTP | pyotp 2.10.0 | MIT | |
| WebAuthn | webauthn (py_webauthn) 3.0.1 | BSD-3-Clause | |
| OIDC | Authlib 1.9.4 | BSD-3-Clause | named by NSOT_STAGE10_PLAN 2.2(b) |
| LDAP, option 1 | python-ldap 3.4.8 | the python-ldap licence (PyPI classifier: Python Software Foundation License) | wraps the OpenLDAP client libraries, an OS package |
| LDAP, option 2 | ldap3 2.9.1 | **LGPL-3.0, a copyleft licence** | pure Python; NSOT_STAGE10_PLAN 2.2(c) named it |
| SAML, option 1 | pysaml2 7.5.5 | Apache-2.0 (its `LICENSE`; PyPI's licence field is empty) | calls the `xmlsec1` program, an OS package |
| SAML, option 2 | python3-saml 1.16.0 | MIT | needs `xmlsec` 1.3.18 (MIT) and the `libxmlsec1` library; its last release was 2023-10-09 |
| X.509, CRL, OCSP | cryptography (already shipped) | Apache-2.0 or BSD-3-Clause (in THIRD_PARTY.json) | 41.0.7 today; CRL `next_update_utc` needs 42.0.0 and OCSP's 43.0.0 |
| TLS and client certificates | nginx (already NSOT_STAGE10_PLAN 4.1's) | its licence is read with 8.2a's audit | |

No CSRF, session or rate-limit library is proposed: each is a few dozen lines over the stores
of 3.1, and a library would bring its own session model beside Mercury's.

---

## 6. An optional bundled identity provider

**What it is for:** single sign-on across Mercury, NetBox and Grafana on one installation, for an
organisation that has no identity provider of its own. It is never required: Mercury's own
accounts and connectors cover sign-in without it.
- Mercury reaches it as an OIDC provider (5.3).
- Grafana documents Keycloak through its generic OAuth provider, with roles from
  `role_attribute_path`; the page marks only Team Sync as an Enterprise feature.
- NetBox documents single sign-on through python-social-auth; its page names no Keycloak or
  OIDC backend (**not verified** which backend fits).

**The comparison.** Every cell is from the vendor's current documentation, read on 2026-11-05
(sources below the table). The versions shown on those pages were Keycloak 26.8.1 and authentik
2026.8.

| | Keycloak | authentik |
|---|---|---|
| **Footprint** | One server container (`quay.io/keycloak/keycloak`) and PostgreSQL, which can be a database in the installation's `mercury-postgres` (OFFLINE_OPERATION 1.9). Sizing guide: "base memory usage for a Pod including caches of Realm data and 10,000 cached sessions is 1250 MB of RAM"; heap is 70% of the container's limit, plus about 300 MB non-heap; 1 vCPU per 15 password sign-ins a second. [K1] | A server container (the server and an embedded outpost), a worker container, and PostgreSQL [A2]. Redis was removed in 2025.10 [A6]. Host minimum: "at least 2 CPU cores and 2 GB of RAM" [A1]. |
| **Air-gapped install** | No air-gapped guide found. The container guide names nothing fetched at start-up; providers are added at image build [K4]. FIPS mode's jars must be carried in (below). Its phone-homes are **not verified**. | An official air-gapped guide [A3]. Four outbound defaults must be turned off: update checks (`AUTHENTIK_DISABLE_UPDATE_CHECK`), start-up analytics, error reporting ("opt-in, but the installation guides enable it"), and Gravatar avatars (set to initials). |
| **CAC (client certificates)** | In the open-source server: the X.509 authenticator [K2]. The identity comes from the SAN otherName (UPN), the SAN email, the subject's CN, a subject or issuer DN pattern, the serial, or the thumbprint. CRL from a file (relative to `conf/`) or a URL, with "CRL abort if non updated" (recommended); OCSP with a fail-open option and a responder override; certificate-policy OIDs. Behind a proxy through the `x509cert-lookup` SPI, with an `nginx` provider [K3]. | Client certificate authentication is an **Enterprise** feature [A4][A5]. The mTLS stage accepts "a smart card, PIV card, or hardware token", and maps the subject, CN or email to the user name or email [A7]. CRL and OCSP are not mentioned on its page, and the UPN is not among its mapping attributes (**not verified** further). |
| **FIPS** | FIPS 140-2 mode: `--features=fips`, and `--fips-mode=strict` for approved mode, on a FIPS-enabled host. The validated BouncyCastle FIPS jars "are not shipped with Keycloak" and are added by the installer; OpenJDK 21 is recommended [K5]. Red Hat's build is the supported route (its terms **not verified**; OFFLINE_OPERATION 1.9). | **Enterprise Plus only** on the enterprise-features page: "Auditable FIPS-compliant deployments to meet FedRAMP requirements" [A4]. The pricing page's FAQ says the Enterprise tier, which conflicts [A5]. |
| **Licence** | Apache-2.0 [K6]. | MIT, except `authentik/enterprise/`, under its own licence, and `website/` under CC BY-SA 4.0 [A8]. Enterprise costs $5 per user per month; Enterprise Plus starts at $20,000 a year [A5]. |

**Recommendation: Keycloak**, for the government fit. Its CAC support, CRL file and FIPS mode are
in the Apache-2.0 server, and it can share the installation's PostgreSQL. authentik is the easier
administration (the operator's premise, not measured here). Its client certificates need a paid
licence and its FIPS mode needs the top tier, so it is a documented alternative for commercial
installs that need neither. Adopting either is a shipped licence, so it is the operator's.

**Sources read on 2026-11-05:**
- [K1] https://www.keycloak.org/high-availability/single-cluster/concepts-memory-and-cpu-sizing
- [K2] https://www.keycloak.org/docs/latest/server_admin/index.html ("X.509 client certificate user authentication"; the page shows version 26.8.1)
- [K3] https://www.keycloak.org/server/reverseproxy
- [K4] https://www.keycloak.org/server/containers
- [K5] https://www.keycloak.org/server/fips
- [K6] https://github.com/keycloak/keycloak/blob/main/LICENSE.txt
- [A1] https://docs.goauthentik.io/install-config/install/docker-compose/
- [A2] https://docs.goauthentik.io/core/architecture/
- [A3] https://docs.goauthentik.io/install-config/air-gapped/
- [A4] https://docs.goauthentik.io/enterprise/enterprise-features/
- [A5] https://goauthentik.io/pricing
- [A6] https://docs.goauthentik.io/releases/2025.10/ (from a search result's summary; the page itself was not opened)
- [A7] https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/mtls/
- [A8] https://github.com/goauthentik/authentik/blob/main/LICENSE
- Grafana: https://grafana.com/docs/grafana/latest/setup-grafana/configure-access/configure-authentication/keycloak/
- NetBox: https://netboxlabs.com/docs/netbox/administration/authentication/overview/

---

## 7. The edge note

A node runs one installation per network stack: unclassified, secret and colourless, each with
nothing shared ([GOVERNMENT_PROFILE.md](GOVERNMENT_PROFILE.md) section 1; EDGE_ARCHITECTURE 9.1,
amended 2026-11-04). Each installation's footprint is budgeted and modest (GOVERNMENT_PROFILE 1,
item 3).

- **So the default on a node is built-in accounts, or the network's own AD and CAC.** Each
  enclave has its own directory and PKI, so each installation's connector points at its own
  enclave's: the AD of 5.1 and the CA bundle and CRL of 5.2.
- **Never a bundled identity provider in each stack.** Keycloak's sizing guide's base figure is
  about 1.25 GB per instance [K1], so three stacks would spend several gigabytes on sign-in
  alone, and three more servers would need patching. An organisation that wants single sign-on
  runs its identity provider once per enclave, outside Mercury, and each installation reaches
  it by OIDC (5.3).
- **"Log in with HQ"** (OFFLINE_OPERATION 1.4) becomes the OIDC connector pointed at
  headquarters' issuer, offered when the link is up. When the link is down, it says so and the
  local methods remain.
- This amends EDGE_ARCHITECTURE 10.1's "Keycloak, one per instance"; roles from groups and the
  reduced operator mode selected by a group (EDGE_ARCHITECTURE 11) are unchanged, with the
  group coming from the account's mapping.

---

## 8. Cloudflare Access: an optional front door

- **Access stays as an optional provider,** off unless its three values are set, with today's
  verification unchanged behind the interface (RS256 against the team's keys, `aud`, `iss`, the
  trusted peer). It is useful for an installation that already fronts Mercury with Access.
- **It is never the only verified identity:** local accounts are always on, and with Access
  configured a person may still sign in locally. During the migration (section 9) an Access
  assertion verifies a request on its own, as today. Afterwards it signs the person into a
  Mercury session like any other method. In both, the role comes from the Mercury account its
  email links to.
- **Removing it breaks nothing:** with its settings cleared, its option leaves the sign-in page,
  `identify()` makes no request to its certs URL, and every core function signs in locally.
- **What must be true to close C2520 when built:**
  1. An installation with no Cloudflare values and no route out signs a person in with a local
     account, and every gate kind their role holds passes, with `Actor-Verified: local`.
  2. `identify()` contacts no public host unless a configured connector names one. In
     air-gapped mode the outbound door refuses even that before any lookup
     (GOVERNMENT_PROFILE 9.1).
  3. The final SDN lab's laptop install signs in on loopback and makes a write (an SDN
     proposal's confirm) recorded `Actor-Verified: local`, and its gate-off settings are back
     on.
  4. With Access configured on the NMAS host, today's sign-in and every existing History row
     read exactly as before.
  5. The tests of section 10 are green, each shown red first, and the air-gapped acceptance
     walk (GOVERNMENT_PROFILE 9.6) includes sign-in by every configured method.
  6. The manual has a Sign-in page and its How it works page (CLAUDE.md, "The manual covers
     every screen and operation").

---

## 9. The migration from Access-only identity: expand, then contract

The rule (CLAUDE.md, "Stored data changes expand, then contract"): a release adds the new shape
and keeps the old readable, and only a later release removes the old, so a rollback stays safe.

1. **Release N-1 (read-ahead):** History's `VERIFIED_WORDS` learns `local`, `ldap`, `x509`,
   `oidc`, `saml` and `api-token`. Nothing writes them yet. A rollback from N to N-1 then draws
   every new commit correctly.
2. **Release N (expand):**
   - the provider interface, with Access as its first provider, behaviour unchanged;
   - local accounts and sessions, and the CSRF tokens on every session request;
   - the role question in `may()`, with every existing verified person mapped to `admin`, so
     nothing anyone can do today is taken away by the upgrade;
   - the accounts store, created empty. On an installation already behind Access, the first
     admin and the break-glass account are created from an Access-verified session (Access is
     the setup proof there; no setup code), and the admin account links the person's Access
     email.
   - New settings are declared with defaults reproducing today's behaviour (CLAUDE.md
     Conventions): Access stays configured where it is.
3. **Release N+1 (contract):**
   - an Access assertion signs the person into a Mercury session instead of verifying each
     request, so one session model and one CSRF rule apply everywhere;
   - the "every verified person is admin" mapping is replaced by the roles the admin has
     assigned, which is the operator's act on that release;
   - provider (a)'s loopback exception has nothing left to except: a local sign-in is a
     verification, not an exemption (section 12, decision 20).
- **Rollback from N to N-1:** the `data/identity/` stores are new files N-1 never reads, and
  Access still verifies as before, so N-1 runs as it did.

---

## 10. What the tests must hold (each shown red, then green, when built)

**The gate and the provider seam:**
1. With no Access values and an account signed in locally, every gate kind its role holds
   passes and every other refuses, naming the role it needs. Red today: everything refuses
   `not_configured`.
2. The role table is exact both ways: every endpoint in `GATES` has a role, and every role row
   names a declared endpoint (the shape of `tests/test_route_gates.py`).
3. Removing, demoting or disabling the last active admin is refused by name.
4. `identify()` makes no outbound request with no connector configured. It runs under the
   harness's network guard (`tests/test_network_guard.py`) with a planted connector that would
   connect, and the guard sees it.
5. The peer condition: a valid session cookie from a peer outside the install kind's expected
   list is not identified; an empty list trusts nobody.

**Passphrases, factors, lockout:**

6. The stored hash is argon2id with 3.2's parameters; a hash with older parameters is rehashed
   at the next sign-in; a 14-character or listed passphrase is refused.
7. TOTP: a code one step old passes, two steps old fails, and the same code twice fails the
   second time.
8. WebAuthn: an assertion for another relying-party ID, or with user verification absent, is
   refused (fixtures captured from a real authenticator, not typed).
9. Back-off doubles per account and per address; 100 consecutive failures disable the
   authenticator; each disable is a Needs attention row that clears on re-enable.

**Sessions and CSRF:**

10. The cookie carries `__Host-`, `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/` and no
    `Domain` (or the loopback kind's measured form).
11. The session id changes at sign-in and at a role change; idle and absolute expiry each end a
    session.
12. A state-changing request without the session's CSRF token, or with another session's, is
    refused before its route runs. So is one whose `Origin` is not the installation's, and a
    Socket.IO connection from another origin.

**Recovery:**

13. No code path signs anyone in without a verified credential: a scan for a default account,
    a hard-coded passphrase, or a setting that skips `identify()`, with a planted case it finds.
14. `nmas-identity recover` refuses without root, records `host-shell`, and raises the Critical
    row.

**History and records:**

15. `tests/test_actor_verified_trailer.py` gains each row of 4.1. Every commit already in a
    repository reads as before, and an unknown value counts as not verified.
16. The identity audit holds no passphrase, code, token, assertion or certificate body: a scan
    of it after a scripted sign-in by every method.

**Connectors:**

17. LDAP: a plain-LDAP URL is refused by the settings; a server certificate from an
    unconfigured CA is refused; an empty passphrase never binds; a filter character in the
    user name is escaped. Nested membership is found through two levels, against a test
    directory in a container, never a live one (CLAUDE.md, "No test touches a live network").
18. X.509, against a lab CA only, never a real card:
    - a certificate from an issuer not marked for sign-in is refused;
    - a revoked serial is refused;
    - a CRL past `nextUpdate` is refused, and accepted within a set grace with its row shown;
    - the UPN is read from a captured PIV-shaped otherName;
    - the client-certificate header from any peer but the proxy's is ignored.
19. OIDC: another issuer, another audience, an expired token, a forged `kid`, a missing or
    replayed nonce, and a missing groups claim are each refused with their outcome. An
    unreachable key set is `verifier_unavailable`, and a `kid` missing from a fetched set is
    `invalid_token` (today's split, kept).
20. SAML (when built): an unsigned assertion, one for another audience, an expired one, and a
    replayed ID are each refused.
21. The air-gapped acceptance walk (GOVERNMENT_PROFILE 9.6) signs in by every configured
    method with zero logged outbound attempts.

**Measurements owed before the numbers are final:**
- the argon2id hash's time and memory on the smallest tier;
- whether each supported browser keeps a `Secure`, `__Host-` cookie from `http://127.0.0.1`;
- the sign-in rate the back-off numbers are set against;
- an enclave CRL's size and load time (OFFLINE_OPERATION, "Measurements still owed").

---

## 11. The estimate

In agent-days, at the measured ratio of about 1.3 hours of wall time and about 4M weighted
tokens per agent-day. Each new screen's board and sign-off is inside its line. LAB9_SDN_GAP's 1.5
days for provider (a) is the first slice of lines 1 and 2.

| # | Work | Agent-days |
|---|---|---|
| 1 | The provider interface; `Identity` gains provider, account, groups, roles; the conftest seam moves to the provider; Access behind it unchanged | 1.5 |
| 2 | Local accounts: the store, argon2id, sessions, CSRF and Socket.IO origin, sign-in and sign-out routes, the first-run setup | 2.5 |
| 3 | TOTP with recovery codes (0.75); WebAuthn (1.0) | 1.75 |
| 4 | Roles in `may()`, the gate table's role column, the Users screen (board, manual) | 1.5 |
| 5 | Break-glass account, `nmas-identity recover`, lockout and rate limits, the identity audit and History's Sign-in source | 1.5 |
| 6 | `Actor-Verified:` values, History's words a release ahead, the migration steps | 0.75 |
| 7 | Active Directory connector, with a test directory in a container | 2.0 |
| 8 | X.509 connector: nginx's client-certificate path, the header rule, the CA bundle and CRL screens, freshness rows, OCSP, UPN extraction, the lab CA's fixtures | 2.5 |
| 9 | OIDC connector | 1.5 |
| 10 | SAML connector (when an installation needs it) | 2.0 |
| 11 | The bundled Keycloak option: its container on `mercury-postgres`, the recipe for NetBox and Grafana, the docs | 2.0 |
| | **Total** | **19.5** (about 25 h and about 78M weighted tokens) |

- **Not counted:** Stage 9's 9.S (gunicorn behind nginx, TLS), which line 8 needs and C248
  owns; the per-network roles of NSOT_STAGE10_PLAN 3.1; API tokens (2.5).
- **Without SAML and the bundled option** (lines 10 and 11, each optional): 15.5 agent-days.
- **Overrun:** plan for up to about 1.7 times, the ratio B4's estimate carries (LAB9_SDN_GAP
  section 5: 6.0 agent-days, up to about 10 at the last stage's overrun), so about 33
  agent-days. A threat to a date is reported as soon as it can be seen.

---

## 12. Decisions for the operator

One line each, with the recommendation.

1. **argon2id parameters:** t=3, m=64 MiB, p=4 (RFC 9106's second option, argon2-cffi's default).
   Recommended.
2. **Passphrase floor:** 15 characters on every account (NIST SP 800-63B-4). Recommended.
3. **Second factor:** required on every account but provider (a)'s loopback single user.
   Recommended.
4. **`Actor-Verified:` one value per method** (`local`, `ldap`, `x509`, `oidc`, `saml`,
   `access`), replacing OFFLINE_OPERATION 1.6's `Actor-Method:`. Recommended.
5. **Break-glass's value:** `local`, with the actor `break-glass:<installation>` flagging it,
   rather than its own value. Recommended.
6. **Three roles now** (viewer, operator, admin), with Stage 10's per-network roles later.
   Recommended.
7. **The peer condition for every provider,** with its list set by the install kind (2.3),
   amending NSOT_STAGE10_PLAN 2.6. Recommended.
8. **Session lifetimes:** 1 hour idle, 12 hours absolute. Recommended.
9. **Lockout numbers:** back-off after 5 failures, 1 s doubling to 15 min, 30 per address per
   10 minutes, disable at 100. Recommended, pending the measured sign-in rate.
10. **`require_*` gate-off settings locked on under the US Government profile.** Recommended.
11. **Hiding the passphrase form** (break-glass excepted) once a connector works: an admin's
    choice, off by default. Recommended.
12. **Where card TLS terminates:** the bundled nginx with a header trusted only from its address,
    rather than passthrough. Recommended.
13. **CRL grace default:** zero (refuse at `nextUpdate`), a site setting its own with a reason.
    Recommended.
14. **Certificate pinning to issuer and serial:** off by default (UPN from an allowed CA), on as
    a site's choice. Recommended.
15. **LDAP library:** python-ldap (PSF-style licence) over ldap3 (LGPL-3.0, copyleft).
    Recommended; either is the operator's licence decision.
16. **SAML library:** pysaml2 (Apache-2.0) over python3-saml (MIT, last released 2023).
    Recommended. SAML is built only when an installation needs it.
17. **Licences to approve when built:** argon2-cffi (MIT), pyotp (MIT), webauthn (BSD-3-Clause),
    Authlib (BSD-3-Clause), and decisions 15 and 16's choices; `cryptography` 41.0.7 to at
    least 43.0.0 is a lock change, not a new licence.
18. **The bundled identity provider:** Keycloak, optional; authentik documented as an
    alternative. Recommended; adopting it is a shipped licence (Apache-2.0).
19. **The edge default:** built-in accounts or the enclave's own AD and CAC, never a bundled
    identity provider per stack (section 7). Recommended.
20. **CLAUDE.md's identity line** ("a verified access assertion AND a trusted peer; no
    localhost exemption") is amended when Release N ships, to "a verified sign-in (a local
    account or a configured connector) AND the expected peer; no localhost exemption". Lines
    to paste are given then. Recommended.

---

## 13. What could not be verified

Each is marked in place as well.
- **The DoD CAC UPN's format** (EDIPI-based, ending `@mil`): only secondary sources were found.
  The DoD CIO memo returned 403 and the cyber.mil page did not load.
- **Keycloak's phone-homes** in an air-gapped install: no vendor statement found either way.
- **authentik's mTLS stage:** whether it checks CRL or OCSP, or maps a UPN. Its page mentions
  neither. Its release (a search summary said 2025.6, preview) is not stated on the current
  page.
- **authentik's FIPS tier:** the enterprise-features page and the pricing FAQ disagree.
- **Red Hat's build of Keycloak:** its subscription terms and current FIPS status.
- **NetBox's single-sign-on backend for Keycloak or generic OIDC:** its page names neither.
- **Grafana OSS:** that the Keycloak recipe needs no Enterprise licence (only Team Sync is
  marked Enterprise).
- **A `Secure` cookie on `http://127.0.0.1`** in each supported browser.
- **An empty simple bind answered as success by AD** (stated from the LDAP standard's
  unauthenticated bind, not read here).
- **`cryptography`'s chain-verification API** for client certificates (the reference page read
  was truncated before it). The design relies on nginx for chain building and on the CRL API,
  which was verified.
- **authentik's Redis removal** (2025.10): read from a search result's summary of the release
  notes, not from the page itself.
