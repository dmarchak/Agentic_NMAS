# Stage 10: a release other people can install and use

**SCOPED 2026-09-30 (the operator), not built.** It comes after Stage 9, once functionality,
appearance, features and known defects are finished. The part other installs depend on,
identity, roles and running with nothing in front, is **Stage 9's item 9.I**, so the
operator's lab runs that way first (section 11). The plan's entry is in
[NSOT_PLAN.md](NSOT_PLAN.md) ("STAGE 10"). No earlier Stage 10 was recorded anywhere; this
is the first.

**What it produces:** a clean public version that someone else can download, install and
use to manage their own network, in a SEPARATE, NEW public GitHub repository holding only
what is needed. Once it exists, the operator makes this repository private, because its
history holds personal details.
- Going private stops new viewers. It does not reach copies already cloned or cached (the
  public history has been public since at least 2026-04-13, C39; nothing has been forked so
  far).
- If the instructor needs the original for grading, the operator adds them as a collaborator.

**The design principle: THE INSTALLER CHOOSES.** How people reach the program and how they
sign in are theirs to choose. The operator's Cloudflare tunnel and Access are a PERSONAL
way of reaching one install, not part of the design. Others will connect on their LAN,
over a VPN, behind their own reverse proxy, or through a tunnel, so **the program must be
secure on its own, with nothing in front of it.**

**Goals:**
- installable by someone without much Linux knowledge;
- a first-run wizard that guides them through everything;
- secure by default however it is reached.

**The facts this rests on** were measured the day it was scoped, by two read-only surveys
of the repository (identity; lab-specific pieces), with the counts quoted below.

---

## 1. Delivery: a Docker container is the primary route

**Recommendation.** Container images are the one artefact built. Docker Compose runs them.
One install script installs Docker if it is missing and starts the stack. A VM image is an
optional convenience, after the container route works.

### 1.1 One artefact

**Images:**
- **`nmas`**, the application. Python, the pinned lock, the app served by a production
  server (section 4), no build tools.
- **The ZTP TFTP responder** is the same image with a different command. It needs different
  networking (1.4), so it runs as its own service in the Compose file. It is not a second
  image.
- **nginx**, the official image, not built here: the only container facing the network
  (4.1).
- **The web tier and the worker tier (10.W, the target architecture):** the web container
  runs gunicorn with many workers and holds no background job; the worker container runs
  device work from a job queue; Redis carries the queue and the announcements, and a
  database holds the state 10.W moves out of files. One image, three commands (web,
  worker, the ZTP responder).

**The VM image** is a small Linux system with Docker and the same Compose file
preinstalled, for people who do not want to install Docker. It holds the same containers
and nothing else to maintain: its build runs the install script on a minimal cloud image
(an OVA and a qcow2).
- **Cost:** one CI job and a boot test per release.
- **Recommendation:** build it after the acceptance run (section 9) passes on the container
  route, never before. Otherwise it doubles the surface while the first route is unproven.

### 1.2 The install script

**What it does:**
1. checks the OS and architecture;
2. installs Docker from Docker's own repository if it is missing;
3. creates the directory and volumes;
4. writes the Compose file and an `.env` with the chosen image tag;
5. pulls the images, verifying their signatures (8.3);
6. starts the stack;
7. prints the address and the one-time setup code (5.1).

**How it earns trust:**
- short (under about 150 lines) and readable;
- published with its SHA-256 checksum;
- published with **the manual steps it performs**, as a page anyone can follow instead;
- `--dry-run` prints every command without running any;
- it never pipes a download into a shell itself;
- the published instruction is download, check the sum, read, run.

**Cost:** small to write. It is tested by the acceptance run, and by a CI job that runs it
on fresh Ubuntu LTS and Debian VMs.

### 1.3 Data outside the container

Everything the program keeps lives in volumes, so an update or a rebuilt container never
loses anything. Measured, today's `data/` and its neighbours:

| Volume | What | Why it is separate |
|---|---|---|
| `nmas-key` | `key.key` (the Fernet key), `secret.key` (the session key) | Losing it loses every stored credential. **The wizard makes its backup explicit** (5, step 4) |
| `nmas-data` | settings, credential profiles, `devices.csv` and `source.json` per list, the NetBox provenance records, the audit trails (reveal, terminal, receipts, inventory edits, update requests, break-glass exports), reader caches | The state of the program |
| `nmas-repos` | each list's `config_repo` (git: goldens, intent, templates, tags) | The record; pushed to a remote the installer chooses |
| `nmas-logs` | `logs/device_manager.log` | Diagnosis (the run history's log lines) |
| `nmas-tftp` | the TFTP root | ZTP's served files |

- The key goes in a volume of its own so a backup can include or exclude it on purpose.
  Its escrow in the break-glass record (section 6) stays the recovery path.
- **Measured, what must change:** `config.DATA_DIR` already derives every path (C32's
  rule, tested). The key paths and the logs directory need the same treatment, a
  prerequisite, not a redesign.

### 1.4 Networking, per feature

| Feature | Port | Docker networking | What it means for someone's network |
|---|---|---|---|
| Web, Socket.IO | 443 (and 80 for the redirect and ACME) | published by the nginx container (4.1); the web container is on the Compose network only | The only port a browser needs |
| SSH to devices | outbound 22 | bridge (outbound NAT) | The container reaches the management network through the host's routing; nothing to open |
| SNMP polls, NetBox, Grafana, Prometheus, Loki, Oxidized, Kea's control agent | outbound | bridge | Same |
| SNMP traps | UDP 1162 (per-list port) | published | Devices send traps to the HOST's address |
| NetFlow | UDP 9996 (per-list port) | published | Same |
| Syslog | UDP 514 | **not the app's**: the bundled rsyslog/Alloy/Loki path (1.5), or the installer's own | The app only queries Loki |
| ZTP TFTP | UDP 69, plus ephemeral data ports | **host networking** for the responder service only | TFTP's data transfer uses a fresh port per transfer, which port mapping does not follow. The responder must answer from the address option 67 names |
| DHCP (bundled Kea) | UDP 67 | **host networking** for Kea | DHCP relies on broadcasts, which do not cross Docker's default bridge. A relay (option 82 / giaddr) on the device segment removes the need for L2 adjacency |
| D4's broadcast DNS check | UDP 53, broadcast | host networking (the responder's service) | Measures that nothing on the ZTP segment answers DNS |

**Recommendation:**
- Bridge networking for the app.
- Host networking for exactly two optional services, the ZTP responder and bundled Kea,
  both behind a Compose profile (`ztp`) that is off by default.
- The docs say plainly: turning ZTP on gives two containers the host's network, and the
  host must sit on, or be relayed to, the device segment.
- **C247 is fixed here:** the responder's interface becomes a setting, never the lab's
  `enp6s19`.

### 1.5 What is bundled

Both routes must work: an optional bundled container, or connecting to one the installer
already runs. Every integration is already optional in code ("not configured" is a state,
never an error; measured over `modules/integrations/`, 10 clients).

| Service | Bundled? | Recommendation |
|---|---|---|
| **NetBox** | optional profile | NetBox's own compose (netbox-docker) is five services (NetBox, worker, PostgreSQL, Redis, housekeeping). Bundle it behind a `netbox` profile; most organisations that want a source of truth already run one, so the default is **connect**. NMAS's writes need its own token (SERVICE_ACCOUNTS.md) |
| **Grafana, Prometheus, Loki (+ Alloy)** | optional profile `monitoring`, one profile for all four | They only make sense together. Bundled with the provisioned `nmas-device` dashboard, the generated scrape targets (a shared volume, C232) and P.7's generated rules. The exporter (`snmp_exporter` with the generated modules) comes with them |
| **Oxidized** | optional profile | Needed by the rotation's persist chain and freshness. **Bundled with its web interface bound to the Compose network only**, never published (C143's lesson, closed by construction) |
| **Kea** | optional profile `ztp` | Host networking (1.4). The reservation fragment is a shared volume Kea includes. The AppArmor lesson (D1) does not arise in the container |
| **Proxmox, S3/MinIO, the topology service** | never bundled | Proxmox is the operator's lab; S3 is a destination the installer names; the topology service is external by design |
| **Authentik** | **never bundled** | Section 2.3 |

- **Cost:** each bundled service is a Compose block, its provisioning, a version pin, and a
  test that the app reaches it.
- **Ongoing:** upstream image updates, tracked by a scheduled CI job that opens a
  version-bump change. **Recommendation:** release 1 bundles the monitoring profile and
  Oxidized, the two a new install most needs to see value. NetBox and Kea are connect-first,
  with profiles once the acceptance run passes.

### 1.6 Updates in Docker

An update is pulling a new image and recreating the container.
- **The app container never gets Docker's control socket.** Access to it is root on the
  host, the thing the root-owned updater exists to avoid (docs/UPDATE.md).
- **Recommendation: the same design, translated.**
  1. The app writes a REQUEST into a small volume it shares with nothing else, exactly as
     today's `data/update/requests/`.
  2. **A host-side, root-owned helper**, installed by the install script and started by a
     systemd path unit watching that directory as today (`deploy/update/nmas-update`'s
     rules, one to one), acts on the request:
     - it validates the request as a request;
     - it re-asks CI itself: **an image is a release only if CI built, signed and published
       it from a green run**, and the helper verifies the signature and digest;
     - it pulls by digest;
     - it records the running digest;
     - it runs `docker compose up -d` for the app service only;
     - it confirms by identity (a new container, `/health` reporting the target version);
     - it rolls back to the recorded digest within the measured bound;
     - it writes the outcome where the app reads it.
  3. The helper runs every program by absolute path and self-tests before each run (C246).
     It holds the Compose file's path and nothing else.
- **Where there is no helper** (an install that declined it, or the VM image before it is
  set up), the Update button shows **the one command**, with a copy button:
  `sudo nmas-update <version>`. The preview, the CI verdict, the host steps and the outcome
  are the same page either way.
- **Kept, every rule the current updater follows:** CI-verified releases only; a preview; a
  person confirms (the `confirm` gate, now also a role, section 3); a version that does not
  come up is rolled back; the outcome is shown; every run recorded.
- **Rejected:** Watchtower-style automatic updates (no preview, no person), and a helper
  container with the socket behind a socket proxy. Filtering the Docker API is subtle, and
  the helper's whole job is one command that needs no API filter.
- **Cost:** moderate. The helper is today's updater with `git` replaced by `docker compose
  pull/up`. The design and its tests exist; the new parts are signature verification and
  the digest record.

---

## 2. Sign-in: the installer chooses the identity source

### 2.1 Pluggable

The gates already ask two questions in one place: `identity.require(request, kind,
operation)`, called by `route_gates.enforce()` for every non-GET endpoint (120 in the
table) and by `socket_gated()`. The change:
- **"Who is this"** is answered by the configured PROVIDER.
- **"What may they do"** is answered by the role map (section 3).

`Identity` keeps its shape (actor, kind person/service, verified, outcome) and gains:
- `provider`;
- `groups`;
- `roles`, per scope.

The providers implement one interface: `authenticate(request) -> Identity`, a login flow,
a logout, a test. **Recommendation:** the interface is Stage 9 (9.I) work, and the
Cloudflare verification becomes one provider behind it, unchanged in behaviour.

### 2.2 Providers, in priority order

**(a) LOCAL ACCOUNTS: built in, always available, the default.**
- **Passwords:**
  - hashed with argon2id;
  - the policy follows NIST SP 800-63B: 12 characters at least, no composition rules, a
    check against a list of common passwords, no forced rotation.
- **Two-factor:** TOTP (RFC 6238) with recovery codes, required for installation
  administrators. WebAuthn later.
- **Sessions:**
  - server-side, the cookie holding only an opaque id;
  - `Secure`, `HttpOnly`, `SameSite=Lax`;
  - an idle timeout and an absolute lifetime;
  - rotated at login;
  - revocable from the user screen.
- **Lockout and rate limiting:**
  - per account and per source address;
  - exponential back-off rather than a hard lock, so a lockout cannot be turned into a
    denial of service against an administrator;
  - every lock and failed burst recorded.

**This REVERSES a recorded decision.** [NSOT_AUTHORIZATION.md](NSOT_AUTHORIZATION.md)
(2026-09-26) rejected an in-app user table: "owning passwords and MFA, and a second
identity source". That was right for one install with Cloudflare in front. It is wrong
for software other people install with nothing in front. Someone on a LAN without an
identity provider must still be able to sign in securely, and local accounts are the only
source every install has. **The cost it named is real and is now accepted:**
- password storage;
- MFA;
- lockout;
- a reset path, done by an installation administrator; no email is assumed.

That document gets a header note pointing here.

**(b) GENERIC OIDC**, for Authentik, Keycloak, Microsoft Entra ID, AD FS (2016 and later
speaks OIDC), Okta and Google.
- One standard implementation, never provider-specific code:
  - discovery from the issuer URL;
  - the authorization code flow with PKCE;
  - the ID token validated (signature against the published keys, `iss`, `aud`, `exp`,
    nonce);
  - the groups claim named in settings.
- A library (Authlib) rather than hand-rolled JWT handling for this flow.
- The Test sign-in button (section 5) shows the claims that came back, so the groups
  mapping is set from what the provider really sends.

**(c) LDAP / Active Directory**, for on-premises AD, OpenLDAP and FreeIPA, over LDAPS
only.
- **Cost:** ldap3, a bind account, a user search, group membership including nested groups
  on AD, certificate validation, and a test directory in CI (Samba AD or OpenLDAP in a
  container). About a third of OIDC's size again, and a second path to keep secure.
- **Recommendation: Stage 10, after OIDC, and only when a real user needs it.** An
  organisation with AD already reaches the program through OIDC:
  - Entra ID for AD synced to the cloud;
  - AD FS on premises;
  - Authentik or Keycloak fronting AD.

  So LDAP serves only an AD with none of those. Stated in the docs as "use OIDC; LDAP
  planned".

**SAML: not planned** unless there is demand. Every IdP listed also speaks OIDC.

**Cloudflare Access: an optional provider, never assumed.** Today's verification (RS256
against the team's certs, `aud` and `iss`, the trusted-peer check) moves behind the
interface unchanged. It is useful for anyone who already fronts the program with Access,
and it is never the default.

### 2.3 Authentik is a separate server

Authentik is a documented, recommended option and never a dependency. It is a server, a
worker and PostgreSQL (with Redis in older releases), about 1 to 2 GB of memory: too heavy
to force on a small install. The docs carry a tested recipe: Authentik as the OIDC provider,
the NMAS application in it, group names mapped to roles.

### 2.4 The break-glass local administrator

It exists whatever provider is chosen, is created by the wizard (step 1), and works when
the provider is down or misconfigured.
- Its password and TOTP are set at creation.
- **Every use is recorded and flagged:** a Needs attention row names the use, when and from
  where.
- It can be disabled for sign-in except from a named address, and it is never a daily
  account.
- This is distinct from today's **break-glass RECORD** (the sealed file escrowing
  credentials and `key.key`, section 6), which stays the recovery path for devices and the
  key.

### 2.5 Service identities

Cloudflare service tokens (`service:<client-id>`) are how automation authenticates today.
They are replaced by **API tokens** issued in the app:
- scoped to a role on a network, never installation-wide by default;
- hashed at rest;
- shown once;
- expiring;
- listed with their last use.

`service_allowed_operations` becomes the token's role.

### 2.6 The blast radius, measured 2026-09-30

| What reads identity today | Where (count) | What changes |
|---|---|---|
| Cloudflare JWT verification | `identity.identify()` (8 callers in 7 files), `_actor_from_claims`, `certs_url`, the JWKS client | Becomes the Cloudflare provider; `identify()` asks the configured provider |
| Trusted peers | `trusted_peers()`, `peer_address()` (2 callers); `cf_access_trusted_peers` | Part of the Cloudflare provider only. Local and OIDC sessions do not use it |
| The gates | `route_gates.enforce()` over 120 endpoints (configure 35, approve 19, confirm 16, publish_remote 5, reveal 4, not_device 41); 3 socket events; 11 inline `require()` calls (remote 5, onboard 4, freshness 1, identity 1) plus `outbound`'s reveal | Unchanged in shape; `may()` answers from roles and scope (section 3) |
| The acting identity | `request_actor()`, 35 calls in 13 files; `viewer()` 3; `g.nmas_identity` read directly in 10 places | Unchanged callers; the value it returns gains provider, role and scope |
| `Actor-Verified:` trailer | written once, `repo.git()` via `actor_verification()`: `access`, `host-shell`, `none` | New values name the source: `local`, `oidc`, `ldap`, `access` (Cloudflare), `api-token`, `break-glass`, `host-shell`, `none`. A new trailer, `Actor-Role:`, records the role and scope the actor held (3.6) |
| Records that store an actor | 20 record files (reveal, terminal, receipts, inventory edits, update requests, the NetBox modification, created, adopted and removal records, break-glass exports, onboarding runs, rotation audit and result, retry log, approval queue, template approvals, freshness authorisations, remote, device holds, the S3 archive's metadata, adopt) | Each gains `provider`, `role` and `scope` beside `actor`, one helper, the way `Actor-Verified` is written once |
| Reveal | 4 gated endpoints plus `?reveal=1`; `reveal_audit.jsonl` | A role (3.3) plus the grant; recorded as today |
| Break-glass export | `/breakglass/export`, gate `reveal`, a person required | Unchanged; requires the installation administrator (3.3) |
| Host-shell actors | `getpass.getuser()` in 12 scripts | In a container, a host script becomes `docker compose exec`, and its actor is the host user named on the command line, still `host-shell` |
| Posture panel | `posture()`, `may()` | Shows the provider, its test result and the role map instead of the Cloudflare values |
| Settings | 21 keys (5 `cf_access_*`, 12 `require_*`, `service_allowed_operations`, and 3 related) | The provider's settings join them; `require_person_for_*` survives as "a person, never a token" |
| Tests | 81 files mention identity; `conftest`'s autouse fixture patches `identify()` once | The one seam: the fixture patches the provider instead, and `real_identity` tests meet each provider |

---

## 3. Roles: two layers

The layers line up with P.8's split of installation-wide and per-network settings. Today
every gate asks only "is this a verified person?".

### 3.1 The roles

**INSTALLATION-WIDE:**
- **INSTALLATION ADMINISTRATOR:**
  - creates and deletes networks;
  - manages users, tokens and role assignments;
  - configures sign-in, HTTPS and the shared (global) integrations;
  - runs updates;
  - owns the break-glass account.
- **At least one must always exist.** Removing, demoting or disabling the last one is
  refused by name.

**PER NETWORK (a network is a device list, P.8):**
- **NETWORK ADMINISTRATOR:** that network's settings and access. They may grant operator
  or viewer on their own network, and never on another or installation-wide.
- **OPERATOR:** deploy, restore, rotate, onboard, adopt, capture, persist and retire on
  that network.
- **VIEWER:** sees everything on that network and changes nothing. Previews that write
  nothing are viewing.

**Reconciled with the recorded AUTHZ decision** (viewer, operator, approver,
administrator, and grants):
- AUTHZ's administrator splits into the two administrator roles.
- Its operator and viewer map directly.
- **Its approver becomes a PERMISSION the network administrator holds**, approving a
  template (per-network library). It is not a fifth role, because a delegated network's
  administrator is who judges its templates.
- **Separation of duties per artifact stays exactly as decided:** the author of a template
  revision may not approve it, from verified attribution only.
- The `approve` split into `author` and `approve` is still required, and happens in 9.I.
- `reveal` and `publish_remote` stay GRANTS: a network administrator holds them on their
  network by default, and an installation administrator can withdraw them.

### 3.2 Does an installation administrator hold every network?

**Recommendation: yes by default, every action recorded with the role it used**
(`installation-admin (implicit)`). A setting, `strict_network_access`, makes the
installation administrator grant themselves a network role as an explicit, recorded step
first. The strict setting is for installs where the installation administrator is IT and
the networks belong to customers or branches.

### 3.3 Every gate's role and scope

The mapping, by gate kind, with the per-endpoint classification done in 9.I (the table
gains a scope column, and a test holds it exact both ways, as P.3's did):

| Kind | Endpoints | Required |
|---|---|---|
| `confirm` | 16 | OPERATOR on the target network |
| `approve` (splits) | 19 | `author`: OPERATOR. `approve` (template approval): NETWORK ADMINISTRATOR, never the revision's author. Approval-queue items hand off to a preview, so their confirm needs OPERATOR |
| `configure` | 35 | Each endpoint classified: installation-scope (global settings, integrations, users, sign-in) needs INSTALLATION ADMINISTRATOR; network-scope (the network's settings, inventory, role edits) needs NETWORK ADMINISTRATOR |
| `reveal` | 4 (+`?reveal=1`) | NETWORK ADMINISTRATOR with the reveal grant; the break-glass export needs INSTALLATION ADMINISTRATOR |
| `publish_remote` | 5 | NETWORK ADMINISTRATOR (the remote is the network's record) |
| `not_device` | 41 | VIEWER on the network. Each is re-read in 9.I: a not_device route that changes the tool's own state (the removal-probe style exceptions) is classified by what it changes |
| `break_glass` (socket) | 3 | Retires with the terminal (7.8) |
| Updates | `update.apply` | INSTALLATION ADMINISTRATOR |

### 3.4 From the organisation's groups

Where the provider has groups (OIDC's groups claim, LDAP group membership), a mapping
assigns roles:
- a group to INSTALLATION ADMINISTRATOR;
- a group to a role on one network;
- evaluated at every sign-in, so a person removed from a group loses the role at their next
  session. Session lifetime bounds the lag, and the docs say so.

For local accounts, roles are set by hand on the user screen. The two can mix: a local
break-glass administrator alongside OIDC users.

### 3.5 The AI agent has a role

The agent is an identity like any other: `agent:<name>`, provider `internal`.
- **Its default role is VIEWER plus `author`** (it may propose a plan, never confirm one).
- Anything more requires a person's approval, through the approval queue, as today.
- This is where Stage 8.3's allowlist ENFORCEMENT lives. The agent's limits sit in the same
  table as everyone's, so a new tool cannot inherit permission by being added.
- AUTHZ's rule stands: the agent may only author.

### 3.6 Visible, not hidden; recorded

**Visible:** a control a person's role does not allow stays on screen, disabled, saying
what it needs ("requires Operator on this network"). Hiding it makes a missing permission
look like a missing feature (AUTHZ's rule, Stage 7's pattern 6, drawn from `may`).

**Recorded:** every action records who did it AND the role and scope they held:
- in the commit (`Actor-Role: operator@<network>`);
- in the receipt;
- in each record file named in 2.6.

A later role change never rewrites what was held.

---

## 4. Secure without anything in front

### 4.1 HTTPS built in: gunicorn behind nginx (Stage 9's 9.S)

**The operator's decision (2026-09-30): nginx, in front of gunicorn**, part of the product
(not something the installer supplies), designed and first run in the operator's lab as
Stage 9's item 9.S ([NSOT_PLAN.md](NSOT_PLAN.md)). This replaces the Caddy first written
here. The nginx container publishes 443 and 80; the web container is on the Compose
network only. TLS in three modes:
- **first run (default):** a certificate generated on first run (a self-signed CA whose
  root the wizard offers to download);
- **own certificate:** the installer supplies a certificate and key (a volume);
- **ACME:** where the install has a public name, through a certbot companion (nginx has no
  ACME client of its own), HTTP-01 or DNS-01.

Nginx also carries the request limits, sign-in rate limiting, the security headers (the
CSP stays the app's), the static assets under the app's cache rules, and WebSocket
proxying (C189). **It is defence in depth, never the app's security**: the app keeps its
own rate limits, CSRF tokens and gates.

**The one change to a pinned rule:** today no `X-Forwarded-For` is read and no ProxyFix
is installed (pinned by tests). Behind the bundled proxy the app must read the client
address from exactly one hop: the proxy's fixed Compose address, never any other peer. The
test is rewritten to pin that, including a forged header from anywhere else being ignored.

### 4.2 Hardening: what Cloudflare Access absorbed, measured

| Today | Where | Recommendation |
|---|---|---|
| Werkzeug's development server (`allow_unsafe_werkzeug=True`) | app.py:4253 | Phase 2 (9.S): gunicorn with ONE `gthread` worker, since about 19 background threads run in the web process. Phase 3 (10.W, before the release): a web tier with no background work, and a worker tier running device work from a queue |
| Bound to 0.0.0.0 by default | config.py:450 | The app binds loopback (the Compose network in the release); nginx is the one listener |
| No CSRF protection on any route | (absent) | A CSRF token for every state-changing request from a session (the header form fits the fetch/htmx pages), plus `SameSite=Lax` cookies. **C248 records whether this is live exposure behind Access today** |
| Socket.IO accepts any origin | app.py:141 | The configured origin only |
| No rate limiting | (absent) | Sign-in, token use and every gated POST rate-limited per identity and per address |
| No TLS, no HSTS | (absent) | 4.1; HSTS once HTTPS is established |
| No `X-Frame-Options` | (absent) | CSP's `frame-ancestors 'none'` already covers HTML (csp.py); the header is added for older browsers |
| Session cookie (for two legacy fields) | app.py:720-760 | Replaced by the server-side session (2.2) |
| SNMP traps and NetFlow accepted from anyone | the collectors bind 0.0.0.0 | An allowlist of sources (the inventory's addresses by default), since v2c traps carry no authentication |
| The AI provider key in `.env` | `.env` | Unchanged in kind; the wizard asks, and the AI is OFF by default (section 7) |

**The inventory's own rule:** a test lists every place that assumes something in front
(each row above), exact both ways, so the next one is found by the suite rather than by an
exposure.

---

## 5. The first-run wizard

It reuses the existing Settings screens and the in-app manual (brief section 10), never a
second set. The wizard is a SEQUENCE over the screens that exist, each step marked done
when its screen's own check passes.

### 5.1 The first-run lock

Until the break-glass administrator exists, the app serves only the wizard, and only to a
browser holding the **one-time setup code**. The install script prints the code, and
`docker compose logs nmas` shows it again. Without it, anyone on the LAN who reached a
fresh install first could claim it. The code expires when step 1 completes.

### 5.2 The steps

1. **Create the break-glass administrator:** name, password, TOTP enrolled and verified.
2. **Choose the sign-in provider:** local, OIDC or (when built) LDAP.
   - A **Test sign-in** step shows the returned claims.
   - The **group-to-role mapping** is set from those claims.
   - The step is refused until a test sign-in maps someone to installation administrator,
     so the install cannot be locked out by its own configuration. Break-glass remains
     either way.
3. **HTTPS:** keep the generated certificate (download its root), supply one, or use ACME.
4. **The encryption key:**
   - generated;
   - what it protects, in words;
   - **back it up now**: a download of the key, or of a sealed break-glass record escrowing
     it (section 6);
   - the step is not done until the person confirms a copy exists somewhere other than
     this machine.

   The key is shown or downloaded once; later downloads are a recorded reveal.
5. **Integrations:** NetBox, Grafana, Prometheus, Loki, Oxidized, Kea, each either **the
   bundled container** (chosen at install) or **a Test connection** to the installer's own
   (today's Settings > Integrations cards and their live Test button).
6. **The first network:** name it, choose its inventory source (local or NetBox), assign
   its roles.
7. **Devices:** onboarding (the wizard), adoption, or a NetBox import, each today's
   operation.
8. **Backups:** the list repositories' remote (C223's publication), where `data/` is backed
   up, and a restore test. The NetBox backup (P.2) where NetBox is bundled.

The wizard can be left and resumed. Each step is also its Settings screen afterwards.

---

## 6. What comes out, or becomes optional

### 6.0 The standing rule, and the check (the operator, 2026-10-02)

The release contains nothing that exists only because of the operator's lab or personal
setup. **From 2026-10-02 the rule applies when a thing is WRITTEN, so this stage is a check,
not an archaeology dig:** anything lab- or person-specific either lives in the lab-tooling
area outside the product (`lab/`, below), or is an OPTIONAL integration that is off unless
configured (and documented as such), or is a value in the local, gitignored configuration
(`data/`). Never a hard-coded assumption in the product.

- **The check**: `tests/test_lab_specifics.py` scans the product (its code, its scripts,
  `deploy/` and the manual it ships) for the lab's names and values (containerlab, clab,
  vrnetlab, the lab's name, the course code, the lab's dashboard UIDs, its 10.255.x
  addresses). Every file holding one is in its `INVENTORY` with the count of such lines, a
  category and a disposition, EXACT both ways: a new file, a grown count, a shrunk count not
  lowered, and a ghost each fail. Measured 2026-10-02: **45 files, 369 lines.** That table
  is the code half of this inventory; it is not repeated here.
- **Acceptance**: the release tree holds no line the check finds, and every item below has
  its disposition carried out.

### 6.0a The lab-tooling area: `lab/` at the repository root (recommended)

Lab tooling is person-run, talks to the product only as an outside client through its
normal read-only API, and the product never names it. **Recommended: `lab/` in this
repository**, excluded from the release by the release's explicit include list, rather than
its own repository: it shares CI, the publication check and the test harness, and a second
repository would duplicate those or run without them. The lab-specifics check refuses the
product importing from `lab/`. The first member is the lab redeploy script (queued after History and the
Coverage redraw; its pre-flight approved by the operator 2026-10-02), with its own README for
the containerlab specifics. **Its devices come from what the person onboarded, never from the
containerlab topology** (the operator's correction, 2026-10-02): the lab tooling's own
configuration names which managed devices a redeploy covers (rcn-lab1: r1 to r4 and s1 to s4;
r6 is its own lab), and the script checks them against the product's inventory, refusing a
device the product does not manage. It needs two read-only answers from the product: "can
this network be recovered now?" and the declared list of boot-generated differences; the manual's "Recovering and redeploying" section
describes the generic procedure. `scripts/oxidized-to-config.sh`, `scripts/nmas-clab-targets`
and `scripts/nmas-host` move there (a host step each: the host's symlinks and units point at
`scripts/`).

### 6.0b The full inventory, by category

| Category | Item | Disposition |
|---|---|---|
| Lab platforms | containerlab: clab-sync (`oxidized-to-config.sh`), its map (`nmas-clab-targets`, `/clab/sync_targets`), the lab-startup check (C303: `modules/lab_startup.py`, its reader, its Needs attention rows), the persist chain's startup-file stages, `clab_*` settings, `manifest.clab_lab`, retire's startup step, the r5.cfg topology reading (C320) | **Optional lab integration** (off unless `clab_host` is set; documented), out of the release |
| Lab platforms | vrnetlab's boot behaviour (console replay, the injected user, the RW community) in `bootstrap_config.py` and `onboard.py`; the launch patches and probe topologies | **Generic**: a declared deployment profile ("this platform replays its startup over a console", "this deployment injects a user"), vrnetlab one profile among others; the patches and topologies move to `lab/` |
| Lab platforms | Proxmox (`integrations/proxmox.py`, image jobs, ZFS rows) | **Optional integration**, out of the release (as 6 says) |
| Lab demos | `yang_push_script`, the setting naming Lab 2's NETCONF demo script, read by `credential_rotation._yang_push_consumer` (added 2026-10-04, the operator's P.8 decision 4: global, and lab tooling) | **Move to `lab/`**; the setting and its reader leave the product |
| Lab platforms | the lab host and `scripts/nmas-host`, `nmas-lab-tunnel`, `data/lab_hosts.json` | **Move to `lab/`** |
| The operator's access | Cloudflare Access and the tunnel (`identity.py`'s verification, 5 settings) | **Optional identity provider** (2.2) |
| The operator's access | the break-glass laptop workflow as written | **Rewritten generic** (6's row) |
| The lab's specifics | addresses (10.255.x in `deploy/rsyslog/`, the P.1 change record, examples), hostnames r1 to r6 and s1 to s4 in examples, the ZTP segment (subnet 255), the lab and course names, the dashboard UIDs (`rcn-lab-overview`, `rcn-lab1-snmp`), Oxidized's layout (router.db, its group names) | **Local configuration** (gitignored) or **removed**; defaults neutral |
| Hardware workarounds | s3's slow clock (per-device heartbeat windows), vIOS timings and bounds (the 35 s connect bound from s3's 13.7 s, the 120 s config-read bound, the reachability miss threshold of 3, IP SLA's measured CPU cost) | **Keep the general mechanism; make each tuning a setting or a measurement per install**, its measured value the lab's local configuration |
| The operator's records | the findings register, the write-up and its notes, the staged-run instructions, the lab runbooks and probe documents | **Stay in this repository, out of the release** |
| Defaults, fixtures, docs | settings defaults holding the lab's values (`clab_configs_dir`, `netbox_excluded_vrfs = ["clab-mgmt"]`), test fixtures holding the lab's configs and addresses, docs that work only with the lab's values | **Neutral defaults**; fixtures ship sanitised (6's tests note); docs rewritten for an installer |

**A note for what comes after this stage: SDN controller support (NSOT_PLAN P.19, recorded
2026-10-02).** Its LAB is course-specific: the CSCI 5280 Mininet and controller VMs, their
names and their runbooks belong in `lab/` with the rest of this table's lab rows. Its PRODUCT
support is not: controller drivers ride on 12's platform layer, generalised to an API-driven
model, and ship like any other platform.

The table in 6 below is the first inventory (2026-09-30), kept: 6.0b supersedes its
dispositions where they differ (containerlab is an optional integration while the lab uses
it, and out of the release).

The inventory, measured 2026-09-30 over 863 tracked files.

| Group | What | In the release |
|---|---|---|
| **containerlab** | `routes/clab.py` (`/clab/sync_targets`); `credential_rotation.clab_target_for()`, `run_sync()`, `verify_startup_file()`, `verify_startup_applies()`; `scripts/oxidized-to-config.sh`, `nmas-clab-targets`, `nmas-check-startup-applies`; settings `clab_host`, `clab_sync_script`, `clab_configs_dir`, `clab_launch_patch`, `clab_labs`, `clab_declared_unmapped`; job health's `clab-sync` row and `sync_owner_rows` | **Out.** The persist chain's startup-file stages become "the device saved and read back its own startup config" (the native persist, `nmas-persist-native`'s shape), which every real device supports |
| **vrnetlab** | the launch patches (`docs/bootstrap-probe/patches/`), 10 probe topologies (`*.clab.yml`), their configs; `tests/fixtures/launch/`, `test_configless_patch.py`, `test_probe_topologies.py` | **Out** (the lab repository) |
| **Lab hosts** | `scripts/nmas-host`, `nmas-lab-tunnel`, `data/lab_hosts.json` and its 4 readers, `scripts/nmas-render-units` and the `@…@` templates | **Out**; the Compose file replaces the units |
| **Host systemd and sudoers** | 13 files in `deploy/systemd/` (heartbeat check, NetBox backup and restore test, startup check, updater path and service, ZTP responder); the sudoers rule for `nmas-oxidized-cred`; the cron line for NetBox retention; `nmas-deploy`, `nmas-update-check`, `nmas-lock-from-host`; job health's systemctl and journalctl reads (6 modules) | **Replaced:** timers become the app's own reader jobs or a scheduler container; the updater becomes 1.6's helper; job health reads container health and the app's own job records instead of systemd. `nmas-oxidized-cred`'s job (rewriting Oxidized's router.db) becomes a shared volume with the bundled Oxidized, or Oxidized's API |
| **Cloudflare** | `identity.py`'s verification, 5 settings, the User-Agent note, the tunnel docs | **Optional provider** (2.2) |
| **Proxmox and B2** | `integrations/proxmox.py`, `image_jobs`, `zfs_rows`, `VM_IMAGES.md`; the rclone/B2 destination in the NetBox backup | **Out**: the operator's own infrastructure |
| **The break-glass laptop workflow as written** | `scripts/nmas-breakglass` (a sealed file on a laptop, `verify --live` over SSH, the console on the containerlab host) | **Kept in substance, rewritten:** the browser export (`/breakglass`) stays the way to make the record; the docs describe keeping it offline without naming a laptop, a USB path or a lab |
| **Names of the operator's infrastructure** | `rcn-lab1` in 6 modules as defaults (breakglass, settings_schema, panels, job_health, credential_rotation, prometheus_targets); `rcn-lab-overview` and `rcn-lab1-snmp` dashboard defaults; `clab-mgmt` as `netbox_excluded_vrfs`'s default; `10.255.x` in 3 code files; `enp6s19` (C247) | **Neutral defaults** (empty, or the bundled dashboard's UID); a test refuses the lab's names in the release tree |
| **Docs** | 44 in `docs/`: 11 product, 20 design records, 13 lab | **Product only**, rewritten for an installer (DEPLOY_LINUX becomes the Docker install; UPDATE describes the helper) |

**The tests:** 259 test files. About 81 touch a lab concept; about 44 use the fleet's real
configs.
- The fleet configs are the parsers' and the deploy path's ground truth, sanitised. They
  ship, with the lab's names replaced by the sanitiser (C71's placeholder work, done once,
  in the sanitiser).
- The tests of removed pieces go with them.

---

## 7. Prerequisites

### 7.1 Stage 9 items REQUIRED before release

| Item | Why it cannot ship without it |
|---|---|
| **9.I: identity, roles, HTTPS, hardening** | The whole of sections 2 to 4 |
| **C249 SNMPv3** | Every device must run a community today. A release that supports only v2c pushes every installer into the exposure C39/C141/C139 manage. SNMPv3 (authPriv) in the collector, the poll route, the monitoring profile, the generated exporter modules and onboarding |
| **C143 (6.1), oxidized-web exposed** | Closed by construction in the bundled Oxidized (1.5); the docs say how to close it for an installer's own |
| **C39/C141, the published community** | The product ships NO community, default or example, and the wizard refuses `public` |
| **C139, the rotation and its consumers** | The rotation must work against the bundled and connected consumers without the lab's sudo helper |
| **C248, nothing in front** | Section 4 |
| **Stage 8.3, the agent's enforced allowlist** | Or the AI ships OFF by default and its tab says why. **Recommendation:** off by default in release 1 whatever 8.3's state, because it sends device text to a third party and needs the installer's own key |
| **E5, roles** | Section 3 |
| **C71, the sanitiser's placeholders** | The shipped fixtures |
| **C100, NMAS's own NetBox account** | The docs and the wizard ask for a token of NMAS's own, never a person's |

**Not required:**
- E3 (`transport input` on the operator's routers: device configuration, not product);
- C44 (a manual pull bypassing the gate: there is no pull in a container);
- B9 (the operator's backup key);
- E6 (the device as witness: a later capability).

### 7.2 Supported platforms

**Stated:** Cisco IOS and IOS-XE, measured on vIOS and Catalyst 8000V (emulated), plus
Arista EOS once section 12's second vendor is proven. Real hardware is untested and the
statement says so.

**How a platform is added** (the multi-vendor story, docs/ARCHITECTURE.md "one parser module per
platform"):
1. a parser module in `modules/nsot/parsers/`;
2. a template directory;
3. a `platform_map` entry;
4. the removal-probe measurements for its `no` forms (Mode B allows only a measured shape);
5. sanitised real configs as fixtures;
6. the verify readers' captures (real `show` output, never typed).

The release's CONTRIBUTING guide lists exactly this. **Section 12 replaces this list**
with a platform DEFINITION (data) and the pipeline that proves it (12.4).

---

### 7.3 From Stage 7, REQUIRED before release

| Item | Why it cannot ship without it |
|---|---|
| **Bulk onboarding** (NSOT_STAGE7_PLAN 17, the operator, 2026-10-04) | An enterprise brings a whole fleet in at once, from a CSV, a spreadsheet or NetBox: one at a time is not a product for it |

| **Support tiers per device** (NSOT_STAGE7_PLAN 18.1 to 18.4; added by the operator 2026-10-04) | An enterprise's first import is a mixed fleet. Without tiers the release refuses most of it, or reads it as the wrong platform (C452, whose default is already removed). The pieces: the tier as data capped by the platform; every screen's tier-aware actions; MONITORED and MANAGED ELSEWHERE; CONFIG BACKED UP through Oxidized's models; the platform measured at onboarding. FULLY MANAGED for another vendor stays section 12's platform layer |
| **Licences and third-party use** (8.2a; the operator, 2026-10-04: "build the check now, the audit at the end") | A public release redistributes every component it ships. One without a recorded source and a redistributable licence, or a file that is not ours to give, makes the release unlawful to copy |
| **The name: a trademark search** (the operator, 2026-10-04: the product is "Mercury Network Automation Platform", "Mercury" for short) | Before the public release, a search for "Mercury Network Automation Platform" in the software classes (Nice classes 9 and 42), recorded with its date and where it was searched. And the README notes the name's origin: a nod to the first place the author worked as a network engineer |
| **Rename the internals to Mercury** (the operator, 2026-10-04: house-cleaning, close to the public release, NOT before) | Today's internal names stay `nmas`: modules, scripts, services (`nmas-update`, `nmas-deploy`), paths, settings keys, the `NMAS_*` environment variables. Done near the release as ONE planned change: its own inventory (a scan of every `nmas` name), host steps for every host-installed file and service renamed, with old names kept as aliases for one release and then removed. The user-facing name moves first and separately (NSOT_STAGE7_PLAN 19) |

## 8. The repository

### 8.1 A fresh curated export

Never a fork, and never a copy with history, so no past commit carries personal details.
- **An export script with an ALLOWLIST of paths** (never a denylist) builds the tree.
- The publication check (`test_nothing_personal_is_published.py`) and the stage guard run
  on the result before its first commit.
- The first commit is the whole tree, with no history.

**Included:**
- the code and tests;
- the Dockerfile(s) and the Compose file;
- the install script, with its checksum published per release;
- the in-app manual;
- the install docs;
- a licence;
- CI.

**Excluded:**
- the write-up and its notes;
- the findings register;
- the plans and design records;
- the lab runbooks and probes;
- CLAUDE.md (a development-process file for this workspace);
- anything personal.

**The export procedure (the operator, 2026-10-04: this repository goes PRIVATE; the official
release is a NEW public repository, its first commit with NO history).** Each step's check
refuses the export:
1. **Build the tree from the allowlist,** at a named commit of this repository whose CI
   passed, into a fresh folder. Excluded on top of the list above:
   - `lab/` and every lab-tooling path (6.0b);
   - `data/`, `tests/fixtures/` content beyond what the shipped tests need (sanitised,
     6.0b);
   - the `.claude/` workspace settings.
2. **The publication check** on the tree: `test_nothing_personal_is_published.py` against the
   denylist, and the stage guard. Zero findings, or no export.
3. **The licence audit** (8.2a):
   - the inventory check passes on the tree;
   - every item on its audit list is closed;
   - the project's own licence file is chosen and present (8.2);
   - NOTICE is generated from `docs/THIRD_PARTY.json` (every third-party component's
     notice and licence text);
   - an SBOM (CycloneDX) is generated from the lock and the vendored entries.
4. **The suite** runs on the tree as the new repository's CI will run it: fresh clone, CI's
   command.
5. **Nothing non-redistributable:** a scan of the TREE for images, licence files, keys,
   MIBs and captured device files (the release has no history, so the tree is all there is).
6. **One commit, pushed to the new public repository.** Its message names this repository's
   source commit, never its history.
7. **The next release** repeats 1 to 6 from a later commit of this repository, as a NEW
   commit on the public one (the public history is the releases). Fixes flow as 8.4 says.

This repository's own history, which still holds what was removed (ccie_kb/, early lab
values), never leaves: it is private.

### 8.2 The licence

| Licence | Effect | Trade-off |
|---|---|---|
| **Apache-2.0** | Permissive, with an explicit patent grant | Anyone may ship it closed, including a hosted service |
| MIT | Permissive, shortest | No patent grant |
| GPL-3.0 | Copyleft for distributed copies | A hosted service need not share changes |
| AGPL-3.0 | Copyleft including network use | Strongest "improvements come back"; some organisations refuse AGPL software outright |

**Recommendation: Apache-2.0**, for the goal as stated (other people install and use it).
It is the most widely accepted in network-operations tooling (NetBox is Apache-2.0), and
compatible with every measured dependency: Flask (BSD), Netmiko (MIT), Paramiko (LGPL,
used as a library), Alpine and htmx (MIT/BSD), pysnmp (BSD). **Choose AGPL-3.0 instead**
if the operator wants every hosted improvement returned.

**One check before choosing:** the institution's policy on capstone work, which may assign
or constrain the rights.

### 8.2a Licences and third-party use: a release gate (the operator, 2026-10-04)

**Required before release (7.3).** The check is built now; the audit runs at the end.

**1. One inventory of everything third-party:** `THIRD_PARTY.md`, or a data file it is
generated from. Each entry records the component's source, its version and its licence.
- the Python packages, from the lock;
- the vendored JavaScript: htmx, Alpine's CSP build, the Socket.IO client, uPlot;
- icons and fonts;
- vendored configuration: `deploy/snmp_exporter/` modules and the Grafana dashboards;
- anything else copied in.

**2. A CI check, now:**
- every dependency's licence is on an approved list;
- every vendored file has a recorded source and licence.

A new one without an entry fails. It catches, for example, the topology icon set the day it
is added.

**BUILT 2026-10-04:** `docs/THIRD_PARTY.json` (the inventory; the release export places it at its root) and
`tests/test_third_party_inventory.py` (the check; CI runs it with the suite).
- **Python packages:** 71, from the lock and the requirements files, each licence an SPDX
  expression read by a person from the package's declared metadata.
- **Vendored files:** 13 entries, claimed by glob: the front-end packages, CodeMirror,
  Bootstrap, and the MIB-derived snmp_exporter modules.
- **Approved:** 0BSD, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, MIT, OFL-1.1, PSF-2.0, and
  public domain.
- **Reviewed, each with its reason:**
  - LGPL-2.1-or-later: paramiko and scp, unmodified installed libraries;
  - MPL-2.0: bidict and certifi;
  - the MIB-derived help text.
- **The audit list it carries:**
  - `ccie_kb/`, REMOVED 2026-10-04 (the operator: v1 leftovers, believed summarised from Cisco sources); it stays in this repository's history, which the release export does not carry (8.1);
  - the Grafana dashboard fixtures';
  - the captured device configurations;
  - the MIB help text;
  - three missing licence files (alpinejs-csp, CodeMirror, Bootstrap);
  - the history.

**3. At release:**
- **The project's own licence**, the operator's decision. 8.2 recommends Apache-2.0. Its
  compatibility is re-read against the inventory: a copyleft dependency (GPL, LGPL, AGPL)
  decides what the release may be and how it is linked.
- **A NOTICE**, the third-party attribution file.
- **An SBOM**, in CycloneDX or SPDX.
- **Confirmation that nothing non-redistributable is in the repository or its history:**
  Cisco images, proprietary MIBs, and captured device files beyond what the fixtures need.
  The history is public and is not rewritten, so a find there is a decision about the release
  repository (8.1's curated export), never a rewrite of this one.

**Excluded by design:** lab tooling that uses Cisco images ships no images. The lab's
containerlab topologies name images the person supplies; the release carries no image, licence
file or key for one.

### 8.3 CI in the release repository

- The suite, confined as today (CI already requires the loopback namespace).
- The publication check.
- The images:
  - built on every commit;
  - scanned (Trivy for the image, pip-audit for the lock) with a failing threshold;
  - an SBOM attached;
  - **signed with cosign keyless (GitHub's OIDC)**;
  - pushed to GitHub's container registry only from a green run on a tag.

  The update helper verifies exactly that signature (1.6).
- The install script run on fresh Ubuntu LTS and Debian VMs, reaching the wizard's first
  step over HTTPS.

### 8.4 How fixes flow afterwards

**Recommendation: the release repository becomes the ONLY development repository at
cut-over.**
- Two repositories carrying one program means every fix is made twice or synced by a
  script that must re-curate, and a sync that forgets the allowlist publishes something.
  Two owners of one fact, the project's recurring defect.
- **This repository is frozen and made private** as the historical record (the write-up,
  the register, the history), readable by collaborators.
- **The operator's lab-specific tooling** (containerlab sync, launch patches, probe
  topologies, lab runbooks, `nmas-host`) moves to a small PRIVATE lab repository that
  depends on the release. The lab then runs the released images like any installer, with
  its own Compose overrides.
- **The design records that should outlive the course** (the plan's reasoning, the
  patterns) can be published later as a sanitised design document, a separate decision.

### 8.5 This repository goes private: what breaks first, and the order (the operator, 2026-10-04)

**Not flipped yet.** Each piece below is built and tested, THEN the operator makes the
repository private, THEN an Update is verified end to end.

**Measured 2026-10-05 (read-only):**
- **CI usage**, from the last 100 runs (2026-10-02 to 10-05, via `nmas-ci-log`'s token):
  - about 45 runs a day;
  - 11.7 billed minutes a run (three jobs of about 4.3 minutes, each rounded up), so about
    530 minutes a day;
  - 16 of the 100 runs cancelled.
  
  A private repository's free 2,000 minutes would last about **4 days**. C440 (never cancel
  on main) keeps every run.
- **The host's GitHub reads:**
  - **The fetch is ALREADY over SSH:** origin is `github-nmas:<account>/<repo>`, an ssh
    alias with `IdentityFile ~/.ssh/nmas_repo` and `IdentitiesOnly yes`. The root updater
    fetches as the checkout's owner (`runuser`), and so does the `app-pushed` reader.
  - **Every API read** is unauthenticated, through one function: `nmas-deploy`'s
    `github_get`. The endpoints are `actions/runs` and `actions/runs/<id>/jobs`. Its callers:
    `nmas-deploy --wait`; the root updater's copy of it (`/usr/local/lib/nmas-update/`); the
    `app-pushed` and `ci-verdict` readers; the Update page.
- **The Proxmox host's room:** 40 CPUs (load about 17.6), 58 GB of memory available, 244 GB
  free on `local-lvm` and 416 GB on the ZFS pool. The lab VM (100) holds 80 GB.

**1. A self-hosted runner, so CI costs no minutes.**
- **Recommended: a small VM on the Proxmox host,** not the laptop. The laptop is off when
  the operator is away, and the Update button refuses a commit CI has not passed, so a
  sleeping runner would stop every update.
- **The VM:**
  - Ubuntu 24.04, CI's image family; 8 vCPU, 16 GB, 60 GB on `local-lvm`;
  - a CPU weight below the lab VM's (`cpuunits`), so a suite run never starves the lab: s3
    is CPU-starved already (C93);
  - its own VLAN address, with no route to the lab's device networks. Like the CI it
    replaces, it reaches only GitHub and the package mirrors.
- **What the suite expects of it, as CI's image provides today:**
  - Python 3.12.3, the host's interpreter, built as `scripts/nmas-ci-env` builds it;
  - the loopback namespace: `kernel.apparmor_restrict_unprivileged_userns=0`, set once on
    the VM;
  - Firefox and a geckodriver from outside any snap (`tests/browser.py`);
  - promtool, unpacked as ci.yml does.
- **Three runner instances on the VM,** one per shard, so the three jobs run at once, as
  today. `runs-on: [self-hosted, nmas]` replaces `ubuntu-24.04`.
- **Ephemeral:** each job starts from a clean workspace (`--ephemeral`, re-registered by a
  systemd unit after each job), so no run inherits another's files.
- **A self-hosted runner only on a PRIVATE repository.** On a public one, any fork's pull
  request runs code on it.
- **Parity (C349): the result must stay equal to today's.**
  - Before switching, the same commit runs on both (`ubuntu-24.04` and the VM). The counts
    per shard must be equal: passed, skipped, and which tests skipped.
  - `scripts/nmas-env-facts --annotate` records both environments.
  - A test that skips on one and runs on the other is a parity finding, never ignored.
- **Its failure is visible:** a queued run with no runner is the CI-ci-refused row's
  "waiting for a runner", naming the runner.

**2. The host reads GitHub with credentials, never printed.**
- **The fetch:** a READ-ONLY deploy key on the repository. If `nmas_repo` is already one
  (the operator checks: Settings › Deploy keys), nothing changes. Otherwise a new ed25519
  key, owner-only, installed by name, and the alias pointed at it.
- **The API:** a fine-grained token, this repository only, with Actions: read (and
  Metadata: read, which GitHub requires).
  - **Stored** owner-only at `/etc/nmas/github-actions-read.token`, mode 0640, root and the
    app's group, because both the root updater and the app's readers read it. It is never
    in an argument, never logged, never printed.
  - **`github_get` reads it** and sends it only as the Authorization header to
    `api.github.com`, refusing a redirect elsewhere, as `nmas-ci-log` does today.
  - **One function changes,** so the updater's installed copy changes with it: a
    `Host-Step-After` reinstalls it.
- **The Update page says plainly** when the key or the token is missing, refused (401 or
  403) or near expiry. P.21's credential-health reader gains the token: its expiry from the
  `github-authentication-token-expiration` header, warning at 30 days and danger at 7. A
  missing or refused one is a Needs attention row naming where to renew it and where the
  new value goes.
- **Host steps in full, each read first and refusing unless the state is the expected one:**
  install the token file; verify `github_get` answers 200 with it; verify the updater's copy
  matches.

**3. `nmas-ci-log`** already reads a fine-grained Actions-read token
(`~/.config/nmas/github-actions-read.token`, owner-only), sent only in the header. On a
private repository the same token works if it covers this repository: the operator checks
its repository list. It expires 2026-12-30.

**4. The order:**
1. The runner: VM, the three instances, and parity proven on one commit.
2. The deploy key: the fetch proven from the host as the checkout's owner.
3. The token: `github_get` with it, the reader's row, the updater's copy reinstalled.
4. **Then the operator flips the repository to private.**
5. Verified end to end: a commit, the runner's green run, the host's Update page offering
   it, an Update, the version shown.

`nmas-ci-log` is proven after the flip too.

**5. The public release is an export (8.1's procedure),** and the publication and licence
checks are its gate.

**What breaks if the order is skipped:**
- CI stops at the minutes limit, so nothing new can deploy.
- The host's API reads return 404, so the Update page cannot say whether a commit passed and
  refuses every update. That is safe, and it is the failure the order prevents.

---

## 9. Acceptance

**The claim:** someone else installs it on a clean machine with the install script and the
wizard, following only the published docs. They reach it directly on their own network,
with no tunnel or proxy. They sign in with a provider of their choice, and they manage a
small test network without help.

**How the test is run:**
- **The tester** is someone other than the operator, who has not seen the program: a
  classmate or the instructor. The operator watches and does not speak. Every point where
  the tester stops, asks or guesses is written down as it happens, with the time; each is a
  finding.
- **The machine:** a fresh VM, the latest Ubuntu LTS minimal (a second run on Debian), with
  nothing installed, on the tester's LAN.
- **The network:** a small published test topology. Two IOS-XE routers and one IOS switch,
  as a containerlab file in the RELEASE's `examples/`, clearly labelled as an example, never
  the operator's lab. Real devices instead where the tester has them.

**The tasks, in order, each timed:**
1. install with the script;
2. complete the wizard with local accounts;
3. sign in over HTTPS directly on the LAN;
4. switch sign-in to OIDC against a test Authentik, mapping a group to Operator on the
   network;
5. onboard or adopt the three devices;
6. capture their goldens;
7. make one intent change and deploy it through the preview;
8. restore one device to a baseline;
9. run an update through the Update button to a newer signed image;
10. back up and restore `data/` onto a second fresh machine, and show the credentials still
    decrypt.

**Pass:** every task completed from the published docs without help, and nothing recorded
as a finding is severity A. **The automated half**, in CI on every release: tasks 1 to 3
and 9 scripted against a fresh VM, with a real browser for the wizard (the browser harness
exists).

---

## 10. Size, and dependencies

**Estimated from finished stages of the same kind** (the project's rule; an unfinished
stage's numbers only show the part that went to plan):
- **9.S** (gunicorn behind nginx): 25 to 45 commits, from P.3's 20, plus two host steps.
- **9.I** is closest to P.3 (a gate over every endpoint: 20 commits, 13 h 41 min to
  complete) and 7.1 (an operation made whole across the app: 69 commits, 20 h 41 min).
  It is several of each: providers, sessions, roles over 120 endpoints, the records,
  HTTPS, hardening, the production server. **Estimate: 90 to 150 commits, 35 to 60 hours**,
  with findings at the measured rate of about one per commit.
- **Stage 10 proper** (images, Compose, install script, the update helper, the wizard, the
  extraction and export, CI, the docs, the acceptance run): **no finished stage of this
  kind exists**, so the range is wide. **Estimate: 70 to 130 commits, 30 to 55 hours**,
  plus the acceptance run and the findings it produces, which cannot be sized in advance.
- **With multi-vendor (section 12):**
  - Stage 10 grows by the second vendor, to **110 to 210 commits**;
  - Stage 9 gains 9.P, the platform layer (60 to 110);
  - Stage 8 gains 8.10, the AI authoring pipeline (30 to 60), outside the release's
    critical path.
- **Check both against actuals when each closes**, as 7.1 and 7.2 were checked.

**Dependencies:**
- **Stage 9 complete**, with 9.I first among its items for this purpose, and the required
  list in 7.1.
- **P.8** (per-list settings): a network role is scoped to what P.8 makes a network.
- **Stage 7** complete: the wizard reuses its Settings screens and manual (brief section
  10), and every control draws from `may`.
- **Stage 8.3:** the agent's role (3.5), or the AI off by default.
- **The AUTHZ decision:** superseded in part (2.2, 3.1), its separation of duties kept.

---

## 11. The Stage 9 part, and the operator's lab

**9.I: identity, roles and running with nothing in front.** It is placed in Stage 9 so the
operator's lab moves to it and is tested on the operator first, before Stage 10 depends on
it. Its steps are in [NSOT_PLAN.md](NSOT_PLAN.md) (Stage 9, item 9.I).
- It contains: the provider interface; local accounts; generic OIDC; both role layers; the
  `approve` split; API tokens; the records' role and scope; built-in HTTPS; the hardening
  in 4.2; the production server.
- It does not contain LDAP (Stage 10, on demand), the container delivery or the wizard.

**The operator's lab moves sign-in to Authentik via OIDC.** The Cloudflare tunnel stays,
only as transport.
- **One login across NMAS, Grafana and NetBox**, all three OIDC clients of the same
  Authentik:
  - NMAS by 9.I's generic OIDC;
  - Grafana by its `[auth.generic_oauth]`, with `role_attribute_path` mapping an Authentik
    group to Editor for the people who author dashboards;
  - NetBox by its python-social-auth OIDC backend (`REMOTE_AUTH_BACKEND`), with group sync.
  - One Authentik session serves all three: a person signs in once.
- **Cloudflare Access, while it stays in front:** point Access's own identity provider at
  Authentik (Access supports generic OIDC). The Access prompt and the apps' logins then
  share the Authentik session instead of being two logins. Once 9.I is proven, the operator
  decides whether Access stays as defence in depth for the lab or is removed from the NMAS
  hostname.
- **Grafana's embedding and `auth.proxy`:** the Stage 7 plan's `auth.proxy` design was
  written for an iframe embed. **Measured 2026-09-30: neither exists in the code.** The
  device page draws panels itself from Grafana's `api/ds/query` with the NMAS's own
  service token, as Viewer, and no user's identity crosses to Grafana. So with OIDC:
  - **NMAS keeps its service token** for what it draws: no auth.proxy, and no user identity
    to forward;
  - **people author dashboards in Grafana directly**, signed in by Grafana's own OIDC login,
    the same Authentik session;
  - **if an iframe embed is ever built,** it rides Grafana's own OIDC session (the browser
    already holds it), which needs `allow_embedding`, `cookie_samesite = none` over HTTPS
    and the CSP's `frame-src` naming Grafana's origin (the four prerequisites measured
    2026-09-29). `auth.proxy` is NOT used for it. It would make the NMAS an identity
    asserter that must proxy every Grafana request. It could coexist with generic_oauth
    (Grafana matches both to one user by email), but it adds a trust path for nothing the
    OIDC session does not already give.
  - The Stage 7 plan's `auth.proxy` line gets a note pointing here.
- **NMAS's service accounts are unchanged by SSO:** its NetBox token (C100's own account)
  and its Grafana token are machine identities, never a person's session.

---

## 12. Multi-vendor: a platform layer, platforms as data, and the AI assistant adding them

**SCOPED 2026-09-30 (the operator), not built. This replaces the operator's first
multi-vendor message of the same day.**

The program is built around Cisco IOS and IOS-XE, and few networks are Cisco-only. The goal
is not for the project to hand-build every vendor. It is:
- a framework;
- one proven second vendor;
- a pipeline through which a person, or the AI assistant, adds further platforms on
  request.

### 12.1 What is Cisco-specific today, measured 2026-09-30

Beyond the per-platform parsers and templates, from a read-only survey of the code.

| Area | Where (measured) | Verdict |
|---|---|---|
| **Verify's commands and readers** | `pipeline.py`: about 31 distinct show commands outside the parsers (`show bgp all summary`, `show ip ospf neighbor`, `show ip route summary`, `show interfaces \| include …`, `show ip interface brief`); readers keyed on IOS headers and column positions (`_parse_rip_sources`, `_parse_bgp_summary`, `_parse_route_total`, `_parse_ospf_neighbor_rows`); `convergence.IOS_BGP_DEFAULT_HOLD` | **Platform** for the commands and readers. The JUDGING (`golden_state.judge_device`, the settle windows) is generic once readers return normalised facts |
| **Mode B's removal** | `removal.py`: the `no` grammar (`_negate`, `negation_program`), 13 IOS regex shapes, `UNREMOVABLE`, `MANAGEMENT_GLOBAL`; `removal_measured.json` keyed `by_dialect` (10 measured shapes on IOS, 9 on IOS-XE) | **Platform.** The measure-per-dialect record is already the right shape |
| **Rotation and adoption** | `credential_rotation.rotation_commands` (`username U … algorithm-type scrypt secret P`, `no username U` first when a `password` entry exists: the coexistence rule measured on IOS-XE 17.6), the type-9 hash, `CONFIRM_PROMPT`; `adopt.local_login_verdict` (AAA and vty method lists), `reversible_credentials` | **Platform** for the command program, the hash forms and the login model. The staging, held-session verify and record chain is generic |
| **Persist, save, reload** | `save_config()` (3 calls, already dispatched by Netmiko's driver); `startup_carries` reading `show startup-config` and the literal "startup-config is not present"; `device_reload`'s `[confirm]` and `Save? [yes/no]`; `bulk_ops._INTERACTIVE_COMMANDS` | **Platform** for the prompts, the startup read-back and file names. The save call is already abstracted |
| **Bootstrap and ZTP** | `bootstrap_config.py`: `CONSOLE_REPLAYED`, `VRNETLAB_INJECTS_USER`, `DOMAIN_KEYWORD`, `GENERATES_SSH_KEY`, `RESERVED_INTERFACES`, `LAYER2_PLATFORMS`, and whole IOS bodies in `render_bootstrap`'s two branches; `ztp.AUTOINSTALL_PATIENCE` (IOS-XE AutoInstall), option 67 naming `{hostname}.cfg` | **Platform**, and already declared as sets keyed by dialect. The TFTP responder is generic |
| **Refusal and error detection, sessions** | `IOS_ERROR_PATTERN` (`% Invalid`, `% Incomplete`, `% Ambiguous`…), 11 references in 6 files; `.enable()` assumed on every write path; `verify_device_connection` defaulting to `cisco_ios`; `device_type` 89 times in 16 files; `_count_vty_lines` | **Platform** (the error vocabulary, the privilege model, the prompts) |
| **Drift normalisation, nesting, ordering** | `normalize.IOS_EPHEMERAL_PREFIXES`, the self-signed pki blocks, the banner openers, **and four more copies of the ephemeral list** (C250); `sections.chains` (nesting by indentation); `roundtrip`'s ordered and unordered IOS sections; `ifnames.INTERFACE_PREFIXES` (15 IOS names); `readonly_commands` (verbs and `\|` modifiers) | **Platform** for every table. The indentation model is platform at the GRAMMAR level (IOS-family only; Junos braces or set form would break it). The five copies are **incidental** |
| **SNMP, telemetry, monitoring** | `CISCO-BGP4-MIB` (`cbgpPeer2Table`) beside the standard OSPF-MIB and OSPFV3-MIB; `cpmCPU*` and `ciscoMem*`; the Cisco trap map; the dashboard's `cempMemPool*`, `rttMon*`, `Cisco_IOS_XE_*` telemetry; `panels.TELEMETRY_METRIC`; the EEM heartbeat applet; `monitoring_coverage.CHECKS` | **Platform** for the MIBs, the telemetry, EEM and the coverage patterns. **The monitoring profile is incidental**: it is already data in the `host_vars` shape |
| **Topology** | `topology.py`: `show cdp neighbors detail`, `show lldp neighbors detail`, `show ip ospf neighbor detail`, `show ip bgp summary`, DMVPN from config | **Platform** for the reads; `build_*_topology` over normalised neighbours is generic |
| **Merge, dangerous lines, rollback** | `merge_commands` (the ancestor chain, one `exit` per level, never `end`); `_DANGEROUS_PATTERNS`; `rollback_commands` (negation with `no`, `no no X`); the NETCONF path hard-coding `Cisco-IOS-XE-native` | **Platform** for mode navigation, negation and the NETCONF payload. The dangerous list is **incidental** (a table generic code reads) |
| **Keying** | `platform.py`'s three namespaces, `platform_map` (driver, template directory, transport, `supports_netconf`), the parser `REGISTRY`; 77 literal dialect names in 20 files, about 11 behavioural branches | **Incidental**: the keying is generic, only the values are Cisco |

**The existing seeds of a capability declaration:**
- `platform_map`;
- bootstrap's sets;
- `removal_measured.json`;
- `PLATFORM_FOLDS`;
- `onboard.BLOCKED_PENDING_MEASUREMENT`;
- the parser `REGISTRY`.

The design gathers them into one definition per platform, rather than starting over.

### 12.2 A platform layer with declared capabilities

**One interface every platform satisfies,** each operation a capability the platform
DECLARES:

| Capability | What it is |
|---|---|
| `parse` / `render` | config to `host_vars` and back (today's parsers and templates) |
| `push` | line-merge (IOS) or candidate-commit (EOS, Junos, IOS-XR) |
| `save` | a command, or implicit in a commit |
| `facts` | interfaces, neighbours (LLDP/CDP), routing adjacencies, routes, as NORMALISED records |
| `remove` | a line or stanza by the platform's removal grammar |
| `rotate` | the credential program, its hash forms, its verify |
| `bootstrap` | the day-0 config and how it is delivered (ZTP's form) |
| `errors`, `prompts` | the refusal vocabulary, and the prompts and their answers |
| `rollback` | computed (negation) or NATIVE (the platform's own) |

**Use the stronger mechanism where the platform has it.** Where a platform has a candidate
configuration with native commit, diff and rollback (Arista EOS configuration sessions,
Junos, IOS-XR), the engine uses it, which is a stronger guarantee than line-merge and a
computed undo.
- **The confirmed program is still what is sent:** for a candidate platform, what the
  person confirms is the device's own candidate DIFF. At apply the engine loads the
  candidate again, compares the diff's hash with the confirmed one, and commits only if
  they are identical. The deploy contract (Phase 3c) holds unchanged.
- **Commit-confirmed** (a commit that rolls itself back unless confirmed within N minutes)
  is a native answer to "the repair path travels over the thing being changed". A change
  that cuts the tool off from the device is undone BY THE DEVICE. The engine uses it
  wherever it is declared.

**Degrade visibly.** An operation a platform cannot do is drawn unavailable with the
reason ("Rotation is not available on EOS: not measured"), never silently skipped. It is
the same rule as a panel folding for a missing source, and every capability is drawn from
the declaration through `may`'s disabled-with-reason pattern.

### 12.3 Platforms defined as DATA, not code: the key design choice

A platform is a **declarative definition**: one YAML document per platform, validated by a
schema, never containing executable code. The program's own tested ENGINE executes
definitions.

**What a definition holds** (all data):
- **Identity:** its name, vendor, OS family and the version range it was measured on, with
  its Netmiko driver and NAPALM driver where one exists.
- **Its capabilities,** each `measured`, `not_measured` or `unsupported`, with the evidence
  of each measurement.
- **Config grammar:**
  - which grammar family (below);
  - comment and ephemeral lines (the one list C250 wants);
  - unrenderable blocks;
  - ordered and unordered sections;
  - interface name canonicalisation.
- **Removal:** the negation form, and the measured removal shapes with their results (today's
  `removal_measured.json`, per platform).
- **Facts:** for each fact, the command, a parsing template (TextFSM or TTP) and the mapping
  from the template's fields to the normalised record. Or `napalm: <getter>` where NAPALM
  provides it (12.5).
- **Refusals:** error patterns; the prompts and their answers.
- **The read-only allowlist:** verbs and output modifiers (C61's rule, per platform).
- **Rotation:** the credential program as a Jinja template in the sandboxed environment, the
  hash forms, and the coexistence rules as flags.
- **Bootstrap:** its template, the delivery form, and its flags (console-replayed, injects a
  user, generates an SSH key).
- **Monitoring:** which MIBs and telemetry paths answer each monitored quantity (CPU, memory,
  BGP peers). Standard first (12.5).

**What genuinely needs ENGINE code**, becoming capabilities definitions switch on:
- **grammar families:** indentation-nested (IOS, EOS, NX-OS: today's `sections` model),
  brace-nested (Junos, and IOS-XR's hierarchy), `set` form (Junos, VyOS);
- **transports:** CLI line-merge with ancestor chains and `exit` (today's), a candidate
  session with diff, commit and rollback (native or via NAPALM), NETCONF where declared;
- **rollback strategies:** computed negation (today's, with its provenance guard), or the
  platform's native rollback and commit-confirmed;
- **the probes:** the removal probe and the bootstrap probe runners (one each, driven by the
  definition);
- **rotation's held-session verify, the TFTP/ZTP server, verify's judge, the merge program's
  consistency checks.**

**Re-expressible as data today:**
- the error patterns;
- the ephemeral and unrenderable lines;
- the ordering policy;
- the interface names;
- the read-only allowlist;
- the removal shapes and their measurements;
- the bootstrap flags;
- the prompts;
- the dangerous-line list;
- the monitoring MIB map;
- every fact command and its reader.

The readers become TextFSM templates plus a field mapping. The ntc-templates package,
already installed as Netmiko's dependency, carries templates for these commands on many
vendors.

**Needs engine code:** the grammar model, the merge program, negation provenance, the
transports and the probes.

**Safety of data:**
- templates run in Jinja's sandboxed environment;
- a definition's regexes run under a time bound (or RE2), so a crafted pattern cannot hang
  the engine;
- a definition cannot name a module, a function or a file path.

### 12.4 The pipeline that adds a platform, which the AI assistant can drive

The pipeline is a PRODUCT feature a person can run step by step; the assistant is one
author of it (Stage 8 item 8.10).

1. **Capture.** On request ("add support for <platform>"), the author collects real output
   from a device of that platform, READ-ONLY. Before a definition exists there is no
   read-only allowlist for that platform, so **the author proposes the capture command list
   and a person approves it before anything is sent** (C61: a first word is not a command,
   and output modifiers differ per vendor). Captures are stored as fixtures, hash-pinned,
   masked as today, never hand-typed.
2. **Draft.** The author writes the definition from those captures.
3. **Prove.** The definition must parse the captures correctly and ROUND-TRIP the device's
   own configuration: render it back and compare depth-aware against THE DEVICE'S OUTPUT,
   never only against itself. The BGP address-family flattening once passed a round-trip
   while both parse and render were wrong. Every reader is also run against a capture of a
   BROKEN state (a minimal edit of a real capture, the fixture rule) and must say broken.
4. **Approve.** A person reviews and approves, recorded with who and why, like a template
   approval. The review shows the EVIDENCE (the captures, the coverage report, the
   broken-state results), not only the YAML. **The assistant never enables a platform on its
   own**: approval is a person's gate (`approve`, the network administrator's permission,
   section 3), and the assistant's role cannot hold it.
5. **Enable in tiers.**
   - **READ features** (inventory, capture and goldens, drift, monitoring, topology) are
     enabled from proven captures.
   - **WRITE features** (deploy, removal, rotation, bootstrap, persist) are enabled only
     after their behaviour is MEASURED on a sandbox device of that platform: P.10's sandbox,
     never production.
   - Every capability defaults to "not measured, so not allowed", the rule
     `removal_measured.json` already applies.
6. **Versioned and reversible.** An approved definition is committed (`platform:` commits,
   its hash in every commit and receipt that used it as a `Platform-Definition:` trailer),
   so a wrong one is traced to what it touched and reverted. It can be contributed to the
   public release repository by a pull request carrying its captures.

**The minimum campaign for a new platform:**
1. Captures from at least two devices in different roles: the running config, and every fact
   command's output in a healthy state.
2. A capture of each fact in a broken state (an adjacency down, an interface down), made on
   the sandbox.
3. The error outputs for an invalid, an incomplete and an ambiguous command; the save and
   reload prompts.
4. Parse and round-trip coverage against the device: 100%, or every unmodelled line
   acknowledged.
5. For each write capability wanted:
   - the removal probe per shape;
   - the bootstrap probe (a throwaway boots the generated config);
   - rotation with its verify and a forced failure;
   - persist and reload;

   all on the sandbox.
6. A real-device acceptance run of each enabled operation.

**How a subtly wrong definition is caught:**
- the device is the judge: round-trips and removals are read back from the device;
- broken-state captures, so a reader that calls everything healthy fails;
- the tiers, so an untested write path is not reachable;
- the person's review of the evidence;
- after enabling, drift, freshness and verify keep reading the device, and the definition's
  hash on every commit makes the blast radius of a wrong one findable.

**The limits, stated:**
- it needs a reachable device of the platform and a read-only credential;
- write support needs a sandbox of the same platform and software version;
- behaviour differs across software versions, so a definition carries the version range it
  was measured on, and a device outside it is `not_measured`;
- the assistant cannot measure what it cannot reach;
- a platform with a grammar family the engine lacks needs engine code first, and the
  pipeline says so rather than drafting around it.

### 12.5 Standards first

**SNMP:** IF-MIB (interfaces), OSPF-MIB and OSPFV3-MIB (already standard here), ENTITY-MIB
(inventory) and LLDP-MIB cross vendors.
- **BGP4-MIB is IPv4-only**, which is why the IPv6 sessions need `CISCO-BGP4-MIB`. The
  vendor-neutral answer for both families is OpenConfig telemetry.
- **CPU and memory have no universal MIB** (HOST-RESOURCES-MIB on some platforms), so they
  stay a per-definition mapping.

**OpenConfig and gNMI** give vendor-neutral telemetry on Arista, Juniper, Nokia and newer
Cisco.
- **Recommendation:** TELEMETRY through OpenConfig paths (gNMI dial-in, collected by gnmic
  into Prometheus) as the default for every platform that supports it, replacing the
  `Cisco_IOS_XE_*` paths on IOS-XE too, so one dashboard serves all.
- **CONFIGURATION through OpenConfig: not now.** Model coverage is incomplete per vendor,
  and the NSoT's `host_vars` model is its own; the templates stay.

**NAPALM:** use it in the engine for platforms it supports (EOS, Junos, IOS-XR, NX-OS, IOS)
behind two capabilities:
- its **getters** for facts (`get_facts`, `get_interfaces`, `get_lldp_neighbors`,
  `get_bgp_neighbors`), normalised already;
- its **candidate transport** (`load_merge_candidate`, `compare_config`, `commit_config`,
  `rollback`) for candidate platforms.

**Not for IOS's deploy path:** NAPALM's IOS driver emulates a candidate by copying a file
and running `configure replace` or a merge, a different guarantee from the byte-for-byte
confirmed line program this tool measures. IOS keeps its line-merge path. A definition
declares, per capability, `napalm` or `commands`.

### 12.6 The second vendor, built by hand: Arista EOS (cEOS)

**Recommendation: yes, Arista EOS, as the operator proposed.**
- **Lighter than any other option:** cEOS-lab is a native container in containerlab, roughly
  1 to 1.5 GB of memory and little CPU at rest, against a VM per node for vIOS or C8000v. It
  suits a host that is CPU-bound (P.10: the containerlab VM keeps about 17 of 24 vCPUs busy,
  the host at load about 18 on 20 cores).
- **It exercises what differs from IOS:**
  - configuration sessions (a candidate, diff, commit, abort, and `commit timer`:
    commit-confirmed);
  - structured output (`show … | json`, and eAPI);
  - OpenConfig and gNMI.
- **Its CLI grammar is IOS-like** (indentation, `no` negation, `write memory`). This is its
  advantage and its limit: the first proof is cheap because the grammar family exists, and
  it does NOT prove a second grammar family.

**What the lab needs:**
- the cEOS-lab image (free, after registering with Arista; lab use only), imported into
  Docker on the clab host;
- a small topology linked into the existing lab (two cEOS nodes on a branch segment, the
  r6 shape);
- management reachability;
- the syslog and SNMP configuration;
- Oxidized's `eos` model;
- a NetBox platform slug;
- a sandbox pair for the write measurements (P.10);
- later, EOS's ZTP, which fetches its config by HTTP rather than TFTP.

**Costs:**
- the definition and its captures;
- the candidate transport (via NAPALM's EOS driver);
- JSON fact templates;
- gNMI telemetry;
- the removal, bootstrap and rotation campaigns;
- an acceptance run.

**The third platform THROUGH the AI pipeline, as the pipeline's acceptance test.**
**Recommendation: Junos, as cRPD (Juniper's containerised routing stack) or vJunos**:
- a real test of the brace/set grammar family, which EOS does not prove;
- cRPD is light, but routing-only (no interfaces of its own to configure);
- vJunos is a full device and a VM;
- the choice is the operator's, on the day, against the host's measured capacity.

**The release does not wait for the third platform.**

### 12.7 Scope and placement, keeping the release shippable

**The release ships with:**
- the platform layer and the definition format;
- IOS and IOS-XE re-expressed as definitions (the existing behaviour, every test green);
- EOS proven end to end;
- the pipeline, documented and usable by a person.

The AI authoring of definitions and the third platform follow.

| Piece | Placement | Why | Rough size |
|---|---|---|---|
| **9.P, the platform layer and definition format;** IOS and IOS-XE re-expressed as definitions; C250 closed by it | **Stage 9**, after or beside 9.I | A refactor of the running program is proven on the operator's fleet before a release depends on it, the same reason 9.I is in Stage 9 | 60 to 110 commits (about 31 show commands, about 80 call sites, 11 branches, the five copies; closest finished kind: the verify family and Phase 3a) |
| **The second vendor (EOS)** | **Early Stage 10**, before the images are finalised | Needs 9.P and the lab's cEOS nodes; its write tier needs P.10's sandbox | 40 to 80 commits, plus the lab work |
| **8.10, the AI authoring pipeline** | **Stage 8 by subject, RUN after 9.P and P.10's sandbox exist**, and after the agent's first real tool runs (8.4) | The agent's work (8.3's authority model decides what it may run); it cannot precede the framework it writes for | 30 to 60 commits |
| **The third platform through the pipeline** | After 8.10, not a release blocker | The pipeline's acceptance test | Measured when it runs |

**Effect on Stage 10's size:** Stage 10 proper grows by the second vendor, from 70 to 130
commits to **110 to 210**. 9.P adds 60 to 110 commits to Stage 9, and 8.10 adds 30 to 60
to Stage 8 (outside the release's critical path).

**Dependencies:**
- 9.P depends on the parsers' and templates' existing tests (they become its acceptance) and
  on the verify family's captures;
- the second vendor depends on 9.P, the lab's cEOS nodes and P.10's sandbox;
- 8.10 depends on 9.P, P.10's sandbox, 8.3 (the agent's enforced authority) and 8.4 (the
  agent's first real runs);
- the release depends on 9.P and the second vendor, never on 8.10.

---

## 13. AI providers: configured at once, switched at will

**SCOPED 2026-09-30 (the operator, with the same day's update).** The design is Stage 8's item
8.11 ([NSOT_PLAN.md](NSOT_PLAN.md)):
- any number of provider configurations (Anthropic, OpenAI and Azure OpenAI, Gemini, xAI,
  any OpenAI-compatible endpoint, local models through Ollama or vLLM);
- selected by the person using the assistant in one click, with a per-user default;
- configured only by an installation administrator;
- restricted per network by policy, shown unavailable with the reason;
- every reply labelled with the model version that produced it;
- tools only for a model that passed the evaluation;
- the gates model-independent.

**Stage 10's part:**
- **The first-run wizard gains a provider step:** configure one or more, a Test per
  configuration, and the evaluation run that decides whether a model may use the agent's
  tools. Skippable: the assistant stays off until one is configured.
- **The documentation:** where each provider sends data (hosted: which company and region;
  local: nothing leaves), stated neutrally, and the local route highlighted for air-gapped
  networks.
- **The release ships the AI OFF by default** (7.1): a provider is the installer's choice,
  never assumed.
