# Offline operation: an installation with no internet and no GitHub (design)

**FUTURE, post-cutover: not Phase 7 work, and nothing here is built.** The operator's request,
2026-10-16: government sectors may not host their documents on public services, so an
installation must run, sign people in, and be updated with no internet and no GitHub.
**Development stays on GitHub**: the repository, its CI and the developer's tools are
unchanged. This note concerns only how an INSTALLATION runs and is updated. Identity
(section 1) carries the operator's decision of the same day; the rest is this note's
recommendation. It is one of six notes written together: [SITES_DESIGN](SITES_DESIGN.md),
[FLOWS_DESIGN](FLOWS_DESIGN.md), [EDGE_ARCHITECTURE](EDGE_ARCHITECTURE.md),
[IPAM_IMPORT_DESIGN](IPAM_IMPORT_DESIGN.md) and
[BRINGUP_FROM_DOCUMENTS](BRINGUP_FROM_DOCUMENTS.md). EDGE_ARCHITECTURE's offline
prerequisites (local authentication, updates, packages) point here rather than designing them
twice.

**What already runs offline** (measured in the code, section 5): every network's repository is
local (`config_repo/` per list, `modules/nsot/repo.py`), a network with no remote is supported
(`remote.auto_push_decision` answers "no remote configured" and pushes nothing), NetBox,
Grafana, Prometheus, Loki, Kea, MinIO and Mercury's PostgreSQL are self-hosted services named
by settings that default to empty, the browser loads nothing from another origin (the v2
pages' CSP is `connect-src 'self'` in `modules/csp.py`, and front-end libraries are vendored
under `static/js/vendor/`), and Phase 8's built-in model is local by design
([PHASE8_PLAN](PHASE8_PLAN.md) section 10.4). What does NOT run offline is the subject of this
note: sign-in, updates, packages, and two readers that ask GitHub whatever is configured.

---

## 1. Identity: Keycloak per instance (the operator's decision, 2026-10-16)

### 1.1 What `modules/identity.py` does today (measured)

Mercury has no sign-in of its own. It trusts Cloudflare Access's signed assertion and the
socket peer it arrived from.

| Function | What it does |
|---|---|
| `identify(request)` | The one verification. Refuses `not_configured` unless `is_configured()`; `no_header` without `Cf-Access-Jwt-Assertion`; asks `_get_jwks_client()` for the signing key by the token's `kid`; `jwt.decode` with RS256 only, `aud` = `cf_access_aud`, `iss` = `https://<team>`, `exp`, `iat`, `aud` and `iss` required, 30 s leeway. A `PyJWKClientError` is split by asking the client for its key set again: a fetch that fails is `verifier_unavailable`, a `kid` not in a set that was fetched is `invalid_token`. Then `_actor_from_claims`, then the peer check. Never raises, never logs a value. |
| `_actor_from_claims(claims)` | Person when `email` is set (the actor IS the email), service when `common_name` is set (`service:<client id>`), nobody otherwise. |
| `_get_jwks_client()` | A `PyJWKClient` for `certs_url()`, `https://<team>/cdn-cgi/access/certs`, with `cache_keys=True`, `lifespan=max(ttl, 300)`, `timeout=10`, rebuilt when the team changes or the TTL passes. |
| `jwks_ttl()` | `cf_access_jwks_ttl`, bounded 300 to 86400 s, default 3600 (C621). |
| `trusted_peers()`, `peer_address(request)` | The raw `REMOTE_ADDR` must be in `cf_access_trusted_peers`. No `X-Forwarded-For`, no ProxyFix (pinned by tests). An empty list trusts nobody. |
| `REQUIRED_ACCESS_VALUES`, `missing_access_values()`, `is_configured()` | All three of team, AUD and peers must be set, or every request is `not_configured`, naming what is unset. |
| `Identity` | `actor`, `email`, `kind` (person or service), `service_id`, `verified`, `outcome`, `reason`, `peer`, `peer_trusted`; `is_identified` = verified AND peer trusted; `audit()` for a record. |
| `may(ident, action, operation)`, `require(request, action, operation)` | The two gates: `require_identity_for_<action>` and `require_person_for_<action>` (both default True), with `service_may()` reading `service_allowed_operations`. |
| `request_actor()` | The gate-verified actor on `flask.g`, else `unauthenticated`. |
| `viewer(request)` | Who is LOOKING (a GET is never gated): the gate's identity, else one `identify()` per request kept on `flask.g`. Draws; authorises nothing. |
| `actor_verification(actor)` | The value of the `Actor-Verified:` trailer: `access` when a gate verified this same actor in this request (or a job carried it), `host-shell` for a CLI on the host (the gate was never installed), `none` otherwise. |
| `verified_identity()`, `carried(ident)` | Carry a request's verified identity into a job's thread, so the job's commits read `access`. |
| `service_label()`, `posture()`, `_setting_origin()` | The audit's label for a service token; the Security posture panel (every gate, its value and where it came from). |

**Offline today:** the certs endpoint is Cloudflare's. With no internet, the first fetch fails,
so every request is `verifier_unavailable`, every gated action is refused (both gate families
default True), and `viewer()` draws everyone as unauthenticated. A process that had fetched
keys keeps them for at most the TTL (at most a day), and a restart empties the cache. Cloudflare
Access itself needs the internet to sign anyone in, so it cannot be the identity of an offline
installation at all.

### 1.2 Every caller of the verified identity

Counted by searching `app.py`, `modules/`, `routes/` and `scripts/` for each function called
through the module (2026-10-16):

| Function | Sites | Callers | What depends on it |
|---|---|---|---|
| `identify` | 43 | `modules/preview_confirm.py`; `routes/` `netbox_safety`, `remote_v2`, `device_v2`, `settings_v2`, `templates_v2`, `breakglass`, `identity`, `golden`, `v2`, `deploy` | the routes that decide for themselves (a GET that may reveal, a confirm bound to a person) |
| `require` | 17 | `modules/route_gates.py` (`enforce`, `socket_gated`: every mutating endpoint and gated socket event), `modules/outbound.py` (`config_text`: every reveal), `routes/` `remote`, `v2`, `device_v2`, `onboard_v2`, `onboard`, `adopt_v2` | every gate |
| `request_actor` | 94 | about 30 route modules, `app.py`, `modules/host_keys.py`, `modules/nsot/device_ops.py` | the `Actor:` of every commit and record a request makes |
| `actor_verification` | 6 | `modules/nsot/repo.py` (`with_actor_verification`, which adds the trailer to every NSoT commit naming an `Actor:`), `routes/settings_v2.py` (`_verified`), `routes/attention.py`, `routes/credential_profiles_v2.py` | History's `Actor-Verified:` (`tests/test_actor_verified_trailer.py`) |
| `verified_identity`, `carried` | 9 and 6 | `modules/deploy_job.py`, `modules/nsot/capture_job.py`, `rotate_op.py`, `reload_op.py`, `scheduled_rotation.py`; `routes/` `device_v2`, `credential_profiles_v2`, `rotate`, `v2`, `adopt_v2` | a job's commits reading `access` |
| `viewer` | 7 | `modules/network_choice.py`; `routes/` `device_v2`, `network_v2`, `v2`, `update`, `operations` | every v2 page's drawn viewer |
| `may`, `posture`, `is_configured`, `service_label`, `trusted_peers` | 5, 2, 1, 3, 1 | `modules/installation_settings.py` (the Access card), `modules/preview_confirm.py`, `modules/outbound.py`, `routes/identity.py` (`/identity/status`), `routes/device_v2.py` | controls that consult the gate; the Security posture panel |

History reads the trailer in `modules/history_sources.py`: `VERIFIED_WORDS` draws `access` as a
plain verified name, `host-shell` as "host login, not verified", `none` as "not verified", and
an absent trailer as "before verification was recorded"; `identity()` counts a value the table
does not name as not verified.

### 1.3 The decision

**Keycloak is the product's identity** (Red Hat's build of Keycloak where FIPS 140-2 mode or
vendor support is required). **The Cloudflare Access verifier becomes an optional
integration, off unless configured.** Mercury still owns no passwords: Keycloak does. This
replaces the in-app local accounts that [NSOT_STAGE10_PLAN](NSOT_STAGE10_PLAN.md) section 2.2(a)
designed, and keeps that section's generic-OIDC shape (2.2(b)) as the one way Mercury verifies
anybody; section 2 of that plan is owed a header note pointing here.

- **One Keycloak per instance**, its users and sessions in the instance's own PostgreSQL
  (1.9). An instance never depends on another instance's Keycloak to sign someone in.
- **Three ways in, in order:**
  1. **Smart card.** X.509 client certificates validated against the organisation's CA, with
     the CRL distributed with the build standard, cached, and a stated grace period (1.4).
     Works offline; the backbone.
  2. **"Log in with HQ".** Brokered to headquarters' Keycloak, when the link is up.
  3. **Local accounts with TOTP, plus one recorded break-glass administrator.** The offline
     fallback.
- **Roles** come from groups in the token (HQ NetOps, kit operator). They select the full
  interface or the reduced operator mode, and who may approve (1.7).
- **History records a person by a stable organisation-wide identifier**, the certificate's
  subject ID, never a local account number, so headquarters recognises the same person in
  every instance (1.5).
- **`identity.py` becomes a pluggable OIDC verifier** using the instance's own Keycloak signing
  keys, which are local and so available offline (1.8).

### 1.4 The three ways in

**1. Smart card (X.509), the backbone.**
- The browser presents the card's certificate in the TLS handshake. The product's reverse proxy
  (nginx, [NSOT_STAGE10_PLAN](NSOT_STAGE10_PLAN.md) section 4.1) terminates TLS, asks for a
  client certificate on Keycloak's sign-in path only, validates the chain against the
  organisation's CA bundle and the CRL, and passes the verified certificate to Keycloak in one
  header. Keycloak trusts that header only from the proxy's own address (section 2), and its
  X.509 authenticator maps the certificate to a user by the organisation's identifier field
  (a principal name in the subject alternative name, or a subject attribute: the organisation
  chooses, headquarters sets it in the build standard).
- **The CRL** travels with the build standard, signed by headquarters, and is installed as a
  file both nginx and Keycloak read; it is never fetched from a distribution point an offline
  kit cannot reach. When the link is up, headquarters' newer CRL arrives with the next
  build-standard pull ([EDGE_ARCHITECTURE](EDGE_ARCHITECTURE.md)).
- **The grace period.** A CRL carries its own `nextUpdate`. Until then it is current. After it,
  card sign-in continues for a stated grace period, with a Needs attention row: "the
  certificate revocation list expired on <date>; card sign-in stops on <date>; load the current
  list from headquarters". Past the grace period, card sign-in is refused in those words and
  the fallback (3) remains. The period is a number headquarters sets from a measurement (the
  longest expected time a kit is offline against the organisation's CRL publication interval),
  never a default in code.

**2. "Log in with HQ" (brokered).**
- The instance's Keycloak lists headquarters' Keycloak as an identity provider. A person who
  chooses it signs in at headquarters (with their card there, or headquarters' own method), and
  the local Keycloak issues its OWN token. Mercury never verifies headquarters' token: it trusts
  exactly one issuer, its own Keycloak.
- The first brokered sign-in links to a local user by the organisation-wide identifier carried
  in headquarters' token, never by email or user name (linking by a name a person can choose is
  how a broker hands one person's account to another).
- When the link is down, this option fails at the redirect, in Keycloak's words, and the
  sign-in page still offers 1 and 3.

**3. Local accounts with TOTP, and one break-glass administrator.**
- A local account is created by headquarters at staging for a named person and carries that
  person's organisation-wide identifier as an attribute, mapped into the token. A local account
  without one names nobody and is refused, as `_actor_from_claims` refuses an assertion with
  neither an email nor a common name today.
- TOTP is required on every local account (RFC 6238, Keycloak's OTP policy). Its clock
  tolerance is a measured setting (Measurements, below), and depends on the trustworthy local
  clock EDGE_ARCHITECTURE lists among its prerequisites.
- **The break-glass administrator** is one recorded account per instance, created at staging,
  its credentials sealed in the organisation's break-glass record (distinct from today's
  break-glass RECORD of device credentials and `key.key`). Every use is recorded and stays a
  Needs attention row until headquarters records who used it and why (1.6). It is never a
  daily account.

### 1.5 What "verified person" means, whichever way in

History must mean the same thing on every instance and for every way in. **A verified person
is a request for which ALL of these held:**

1. **A token issued by THIS instance's Keycloak realm**, its signature verified against that
   realm's published keys, with `iss` (the realm), `aud` (Mercury's client), `exp` and `iat`
   checked, exactly as `identify()` checks Cloudflare's today.
2. **The request arrived from a trusted peer**: the raw socket peer is the reverse proxy's
   address, kept as today's second, independent condition (`peer_trusted`).
3. **The token names a person, not a service**: it carries the organisation-wide identifier
   claim, and Keycloak did not issue it to a service account (client credentials).
4. **The way in is one of the three above**, recorded from the token's authentication-context
   claim (which authenticator ran), so a person signed in by card and by local TOTP are both
   verified and History can still tell them apart.

The **actor** is that organisation-wide identifier, never a Keycloak user id, a local user
name or an email. An email can be reused and a local id differs per instance; the subject ID is
what headquarters already uses to name the person. A display name may be drawn beside it, and
is never what a record compares.

**The one change this makes to History's meaning:** today a verified actor is an email. After
the switch it is an identifier. A commit's `Actor:` before and after the switch names the same
person differently. History draws what each commit says; a recorded alias list (email to
identifier, written once by headquarters at the switch) lets History show one person, and any
comparison of two actors (the separation of duties [NSOT_AUTHORIZATION](NSOT_AUTHORIZATION.md)
section 5 designs, once built) compares identifiers, so an approval queued under the old form
is re-requested rather than compared across forms.

### 1.6 `Actor-Verified:` for each way in

The trailer keeps its three values and their meaning, so every existing commit reads as it
does now: it says WHETHER the gate verified this actor, not how. A new trailer,
`Actor-Method:`, written by the same `repo.with_actor_verification`, says HOW, from the
identity the gate verified; History draws it beside the name. `tests/test_actor_verified_trailer.py`
gains the method for each row below.

| Way in | `Actor:` | `Actor-Verified:` | `Actor-Method:` | History says |
|---|---|---|---|---|
| Smart card | the certificate's subject ID | `access` | `pki` | the name |
| Log in with HQ | the identifier in headquarters' token | `access` | `hq-broker` | the name, "signed in through headquarters" |
| Local account + TOTP | the account's recorded identifier | `access` | `local-totp` | the name, "local sign-in" |
| Break-glass administrator | `break-glass:<instance>` | `access` | `break-glass` | "break-glass account, person not yet named", until headquarters records who |
| Cloudflare Access (optional integration) | the email, as today | `access` | `cloudflare-access` | the name, as today |
| A service (client credentials) | `service:<client id>` | `access` | `service` | as services read today |
| A CLI on the host | as today | `host-shell` | (none) | "host login, not verified" |
| Background work, or an actor the gate did not verify | as today | `none` | (none) | "not verified" |

**The break-glass row is the recommended treatment:** the account passes the person gates
(someone was present and held its password and TOTP), every commit it makes carries a stated
reason, and its Needs attention row clears only when headquarters acknowledges it naming the
person by identifier. The alternative, treating it as a service, would leave an offline kit
with no cards and no TOTP accounts unable to make any change.

### 1.7 Roles from groups

- Keycloak puts the person's groups in the token (a groups claim, named in Mercury's
  configuration once). Headquarters defines the groups in the build standard; the instance's
  Keycloak receives them by card mapping, by the broker, or on the local account.
- **HQ NetOps** draws the full interface and may hold `approve`; **kit operator** draws the
  reduced, plain-language operator mode ([EDGE_ARCHITECTURE](EDGE_ARCHITECTURE.md)) and never
  holds `approve`. These map onto the roles of [NSOT_AUTHORIZATION](NSOT_AUTHORIZATION.md)
  section 4 (viewer, operator, approver, administrator) and Stage 10's section 3.4 (groups to
  roles, evaluated at every sign-in, so a person removed from a group loses the role at their
  next session; the session lifetime bounds the lag).
- The gates gain one question after today's two: is anyone verified
  (`require_identity_for_<kind>`), is it a person (`require_person_for_<kind>`), and **does
  their role hold this kind**. `may()` stays the one place all three are answered.

### 1.8 `identity.py` as a pluggable verifier

- **One interface**, as [NSOT_STAGE10_PLAN](NSOT_STAGE10_PLAN.md) section 2.1 proposed:
  `authenticate(request) -> Identity`, plus sign-in, sign-out and a test. `identify()` stays
  the single entry point all 43 direct call sites and both gate paths already use, and
  dispatches to the configured verifier. `Identity` keeps its fields and gains `method`,
  `groups` and `org_id`.
- **The Keycloak verifier** is an OIDC relying party: authorization code flow with PKCE,
  through a library rather than hand-rolled handling (Stage 10 2.2(b) names Authlib; a new
  package is a licence decision, the operator's). The ID token is verified as 1.5 says. The
  session is server-side, its cookie an opaque id (`Secure`, `HttpOnly`, `SameSite=Lax`,
  rotated at sign-in), and Keycloak's back-channel logout ends it.
- **The signing keys are the instance's own**, fetched from its Keycloak on the host and cached
  under today's bounded rule (`jwks_ttl()`, 300 s to a day, an unknown `kid` refreshing the set
  once). They need no internet.
- **A key set that cannot be fetched**, offline or not, is today's `verifier_unavailable` and
  keeps today's split: a fetch that fails is the verifier's health, a `kid` missing from a set
  that WAS fetched is a bad token. With a local Keycloak the fetch fails only when Keycloak is
  down. Then sessions already verified continue to their end (the session holds what was
  verified at sign-in, and the cached keys verify a refresh until the TTL), no new sign-in is
  possible (Keycloak IS the sign-in), and the refusal says "this instance's sign-in service is
  not answering", with a Needs attention row from job health. For the optional Cloudflare
  verifier, an unreachable certs endpoint is the same outcome, and offline it is permanent:
  that verifier is for installations with the internet.
- **Which verifier runs is measured, not chosen by a new setting:** Keycloak's when its realm is
  configured, Cloudflare's when its three values are set (as `is_configured()` already decides),
  and BOTH configured is refused by name, never resolved by precedence. Neither is
  `not_configured`, as today.
- **Services** use Keycloak's client-credentials grant; the bearer token is verified the same
  way and its service-account marker makes `kind` service. `service_allowed_operations` is
  unchanged.
- **The trusted-peer condition stays,** its list naming the reverse proxy's address instead of
  the tunnel connector's. Stage 10 4.1's one-hop rule (the client address from the proxy's
  fixed address only) applies unchanged.
- **New routes** (sign-in callback, sign-out) are GETs or posts declared in
  `modules/route_gates.py` and `modules/invalidation.py`, as every route is. The sign-in page
  is Keycloak's own, themed; any new Mercury screen (a "signed out" page) needs its mockup and
  sign-off first.

### 1.9 Keycloak's storage, licence and build

- **PostgreSQL: the instance already has one.** `deploy/postgres/docker-compose.yml` runs
  `mercury-postgres` (PostgreSQL 18, NetBox's image pinned by digest), published on loopback
  port 5433 only, with Mercury's own database and role
  ([NSOT_PHASE4_RECORDS_POSTGRES](NSOT_PHASE4_RECORDS_POSTGRES.md) section 6).
  **Recommended:** Keycloak gets its own database and role in that server (one PostgreSQL to
  patch, one backup), never Mercury's role. Its database joins the records backup and its
  restore test (that document's section 4); deleting or rotating a backup stays the operator's.
- **Licence:** Keycloak is published under Apache-2.0, **to confirm from its own terms** before
  it is adopted (a new third-party licence is the operator's decision, recorded in
  `docs/THIRD_PARTY.json`).
- **Red Hat's build of Keycloak** (for FIPS 140-2 mode and vendor support): its availability,
  subscription terms and FIPS mode on the chosen platform are **to confirm**.

### 1.10 The lab proof, without real cards

- Keycloak in a container on the lab's Mercury host, on `mercury-postgres`.
- A lab CA (software only) issuing client certificates to test users, a CRL from it, and a
  certificate it has revoked; each loaded into a browser profile, never a real card.
- A second Keycloak as "headquarters", brokered from the first.
- The walk: sign in by certificate, by brokered login, by local TOTP and by break-glass; read
  each commit's `Actor:`, `Actor-Verified:` and `Actor-Method:` in History; revoke a
  certificate and load the new CRL; let a CRL pass `nextUpdate` and then the grace period; stop
  "headquarters" and sign in again; stop the local Keycloak and watch a session continue and a
  new sign-in refused by name.

---

## 2. Reachability is the deploying team's choice

How people reach an instance (a VPN, a jump network, a tunnel, a LAN) is the deploying team's
choice, not Mercury's. **The product documents only what it needs:**

- **Its listening port and its TLS certificate:** nginx's 443 (and 80 for the redirect), in the
  three certificate modes of [NSOT_STAGE10_PLAN](NSOT_STAGE10_PLAN.md) section 4.1.
- **Which proxy headers it trusts, and from which addresses:** the client address
  (`X-Forwarded-For`, one hop) and Keycloak's client-certificate header, each only from the
  proxy's own address; from any other peer both are ignored, and a forged one is a test case.
- **The upstream-manager connection** ([EDGE_ARCHITECTURE](EDGE_ARCHITECTURE.md)): its outbound
  port, protocol and the manager's pinned certificate. A kit dials out, so nothing is opened into
  a kit.

### 2.1 Moving the tunnel tooling to `lab/` (a step for later)

The `cloudflared` tunnel itself is not in the repository (its ingress rules live on the tunnel
host). What in the repository exists for it, measured 2026-10-16:

| What | Where | Disposition |
|---|---|---|
| The LAN-or-tunnel host helper | `scripts/nmas-host` | **moves to `lab/`** (already `MOVE` in `tests/test_lab_specifics.py`'s `INVENTORY`, 5 lines, category "the operator's access setup") |
| Port forwards to lab nodes | `scripts/nmas-lab-tunnel` | **moves to `lab/`** (Stage 10 6.0b's "Lab hosts" row; no line of it matches the lab-specifics pattern, so it is not in `INVENTORY`) |
| Their tests | `tests/test_nmas_host.py`, and `tests/test_no_pattern_kill.py` (which runs `scripts/nmas-lab-tunnel` by path) | repointed at `lab/` |
| The agent hook that recognises host commands | `scripts/hooks/claude-no-host-writes` | repointed at the new path |
| Cloudflare Access verification and its settings | `modules/identity.py`; `cf_access_*` in `modules/settings_schema.py`, `modules/settings_scope.py`, `modules/installation_settings.py` (`ACCESS_CARD_KEYS`) | **stays in the product as the optional verifier** (1.8), off unless configured; its settings already default to empty |

**What the lab-specifics inventory then says:** `scripts/` is in the check's `SCOPE` and `lab/`
is not, so after the move the `scripts/nmas-host` entry names a file that no longer exists and
fails as a ghost; it is deleted in the same commit, and `INVENTORY` then holds the remaining
entries only (today: `modules/host_steps.py` and four one-shot host steps). The move needs, in
order: CLAUDE.md naming the new paths (the operator's paste; CLAUDE.md cites `scripts/nmas-host`
throughout), a host step for any symlink on the host, then the move commit. Stage 10 6.0b's
"The operator's access" row then reads "optional integration, off unless configured" rather than
"optional identity provider".

---

## 3. Updates

### 3.1 What runs today (measured)

**`scripts/nmas-deploy`** (the terminal deploy), in `_deploy()`:
1. refuses local edits and `.git` files owned by another user;
2. `git fetch --quiet origin`, **unconditionally, with or without `--offline`**;
3. the target is `origin/main` (or `--to`, which must be on `origin/main`), and must be a
   fast-forward of HEAD;
4. the gate: `ci_verdict()` or, with `--offline`, `offline_verdict()`;
5. refuses when it cannot restart (`can_restart`), when a device is held or the holds are
   unreadable (`_operations`, asking `/health/operations` on loopback), or when the target's
   venv is unbuilt (`venv_plan`);
6. fast-forwards, swaps the venv link, restarts, and confirms by identity through `/health` on
   loopback (`wait_for_running`), then prints the host steps.

**The CI gate, `ci_verdict(repo, target, get=github_get)`:** reads `owner/repo` from the origin
URL (`slug_of`), asks `https://api.github.com/repos/<owner>/<repo>/actions/runs?head_sha=...`
(`github_get`, unauthenticated, 10 s), keeps the runs of `.github/workflows/ci.yml`, and
decides by `verdict_of_runs` (pending, cancelled, the latest conclusive run). A commit with no
run walks back up to `WALK_BOUND` (10) ancestors to the nearest with a run and passes only when
the trees are identical or every changed path matches that green commit's `paths-ignore`
(`ignored_patterns`, `only_ignored`). Anything it cannot ask is exit 2, never a pass. GitHub
allows 60 unauthenticated calls an hour per address, shared with the readers below (C678).

**What `--offline` does** (`offline_verdict`, `offline_forecast`; `tests/test_nmas_deploy.py`
`TestOffline`): makes a `--shared --no-checkout` clone of the repository in a temporary
directory, checks out the TARGET, prints the forecast (this host's last `--offline` duration
from `data/deploy_audit.jsonl`), and runs the WHOLE suite there through the target's
`scripts/nmas-test --allow-unconfined` (in parallel only when the installed pytest-xdist matches
the target's pin, `parallel_available`), with this interpreter. Pass deploys; failure or a fired
bound is exit 3. The audit row records `gate: offline`.

**What `--offline` skips:** only the GitHub question (`ci_verdict`, so no api.github.com call)
and `--wait`. **It does not skip** the `git fetch origin` (an unreachable origin raises in
`git()` before any gate), the requirement that the target is on `origin/main`, the restart,
holds and venv checks, or the host-step report. So `--offline` already works against ANY
reachable origin (an internal git server, or a bare repository on the host), and needs the
venv's test tools installed (`requirements-test.txt` is part of the venv identity,
`VENV_INPUTS`).

**The Update available chip and the Update button:**
- `modules/readers/app_pushed.py` (`judge`, `read`, every 300 s): `git ls-remote origin
  refs/heads/main` on the application's checkout, a `git fetch origin main` when the tip is not
  local, and `enrich()`, which asks CI's verdict for each commit between through `_verdict()`,
  `nmas-deploy`'s own `ci_verdict` loaded by `modules/readers/ci_verdict.py`.
- `modules/readers/ci_verdict.py` (`read`, every 900 s): the running commit's verdict for the
  status bar, and `failed_steps()`, one more GitHub call for a failed run's jobs.
- `modules/update_op.py` reads those stored values (no page load asks GitHub), and the confirm
  writes a request file.
- **The root updater, `deploy/update/nmas-update`** (`update()`): fetches origin, requires the
  target on `origin/main`, and re-derives the verdict through its own root-owned copy of the
  gate (`/usr/local/lib/nmas-update/nmas-deploy`), calling `gate.ci_verdict` with **no offline
  path**. On an installation without GitHub the Update button can never update: every request
  is refused at "CI re-checked for the target".
- **Both readers run whatever is configured** (`modules/reader_job.py` `DECLARED_MODULES`
  starts every declared reader; there is no switch), so an installation without GitHub has two
  readers failing every interval, each a job-health row.

### 3.2 Two questions, separated

Today one answer serves two questions. The design separates them:
1. **Where the code comes from:** `origin`, any git URL (already true: `git fetch origin` names
   no host).
2. **Who vouches for a commit:** a VERDICT SOURCE. Today: GitHub Actions' API, or the local
   suite (`--offline`). Added: a **signed verdict** that travels with the code.

**The signed verdict.** The CI that ran the suite signs a statement "commit `<sha>` passed
`<workflow>` at `<time>`, run `<id>`" and publishes it as an annotated, signed tag (or a git
note) in the same repository: it arrives with `git fetch`, and is checked with no network. The
signature is git's own SSH signing (`gpg.format=ssh`, verified against an allowed-signers file),
so OpenSSH, already on the host, is the only tool: no new package. The CI's public key is
installed root-owned beside the updater's copy of the gate, so a commit or a request can never
supply the key that vouches for it. `ci_verdict` gains this source behind the same exit codes,
and the docs-only walk is unchanged in rule: a commit with no signed verdict passes only on an
identical tree or ignored paths since the nearest commit that HAS one.

### 3.3 Option A: an internal git server with internal CI

- `origin` is the organisation's server: Gitea or Forgejo (with Actions), GitLab (with GitLab
  CI), or a plain git server with Jenkins.
- Its CI runs the same workflow steps on a runner the organisation controls, and as its last
  step signs and pushes the verdict tag (3.2). The tag is the verdict, whichever CI made it, so
  `nmas-deploy`, the updater and both readers need no adapter per CI product. An API adapter
  per product (Forgejo's and Gitea's Actions APIs, GitLab's pipelines, Jenkins' commit statuses)
  is the alternative, and is not recommended: four adapters, four rate limits and four
  credentials, against one signature check.
- The readers work unchanged in shape: `ls-remote origin` asks the internal server, and the
  verdict is read from the fetched tag. The 60-an-hour GitHub allowance no longer applies.

### 3.4 Option B: a signed release bundle carried across

For an enclave that cannot reach even an internal server from the build side:
- **The bundle**, built by the release CI: a `git bundle` of the release commit's history, its
  signed verdict tag, the wheelhouse (section 4), the container images it pins (`docker save`,
  by digest), and a manifest of every file's sha256, the manifest itself signed with the release
  key.
- **The import**, a host step (and later an Update-page operation with preview and record):
  verify the manifest's signature against the root-owned release key, verify every file's
  sha256, `git bundle verify`, then fetch the bundle into a bare repository on the host that the
  checkout's `origin` names. From there it is Option A: the same fetch, the same signed verdict,
  the same updater.
- **Refused by name:** a bundle whose manifest signature fails, any file whose hash differs, a
  bundle that is not a fast-forward of what runs, and a release commit with no signed verdict.
  The verdict is checked before any deploy, and again by the root updater, as today.

### 3.5 Recommendation

Build the signed verdict first: it serves A and B, and GitHub too (development keeps GitHub
Actions, which can sign the same tag). Then the bundle importer. Keep `--offline` as the third
source, for an installation with neither (it already works against any reachable origin), and
give the root updater the same three sources, choosing by what is configured, never by a
fallback that tries GitHub first.

---

## 4. Packages and images

**Today (measured):** `scripts/host-steps/venv-1-build.sh` builds `/opt/mercury-venv-<id>`
(the id from `requirements.lock` and `requirements-test.txt`, `VENV_INPUTS`), first checking
that `https://pypi.org/simple/pip/` and `https://files.pythonhosted.org/` answer, then `pip
install --require-hashes --no-deps -r requirements.lock` and `pip install --no-deps -r
requirements-test.txt`. `scripts/nmas-ci-env` and CI's workflow install the same three files the
same way (`requirements-ci.txt` too). The lock pins 55 distributions with 725 sha256 hashes
(several per distribution: one per published file). **`requirements-test.txt` and
`requirements-ci.txt` carry no hashes**, so two of the venv's distributions (pytest-xdist and
execnet) are pinned by version only.

**Offline, the hashes already do the work.** `--require-hashes` refuses any file whose sha256 is
not in the lock, whatever served it, so the source can change without trusting it:
- **A wheel bundle with the release (recommended):** release CI runs `pip download --no-deps
  --require-hashes -r requirements.lock` for the host's platform (CPython 3.12, x86_64 Linux) into
  a wheelhouse, shipped in the bundle (3.4) or beside the release on the internal server. The
  build becomes `pip install --no-index --find-links <wheelhouse> --require-hashes --no-deps -r
  requirements.lock`. `requirements-test.txt` and `requirements-ci.txt` gain hashes first (the
  lock's own `uv pip compile --generate-hashes`), which changes the venv identity once, as any
  lock change does.
- **Or an internal package mirror**, named by `PIP_INDEX_URL`; the lock's hashes still decide.
  Candidates (devpi, a repository manager) are new third-party software, the operator's licence
  decision.
- `venv-1-build.sh`'s index check becomes "the configured index or wheelhouse answers", naming
  which, and a distribution with no wheel for the host's platform (an sdist that needs a
  compiler) is named before the bundle is cut, never discovered offline.

**Beyond pip**, each needs the same treatment (an internal mirror, or files in the bundle checked
by hash):
- **The interpreter and system libraries:** Ubuntu's Python 3.12.3 and `libpq5`, from an apt
  mirror of the same Ubuntu release ([NSOT_CI](NSOT_CI.md) section 3 recorded why a PyPI mirror
  alone cannot reproduce the host).
- **Container images:** `mercury-postgres` is already pinned by digest; NetBox's, Keycloak's and
  the other services' images come from an internal registry or as `docker save` archives in the
  bundle, loaded and checked by digest.
- **The Phase 8 model file:** already designed for this ([PHASE8_PLAN](PHASE8_PLAN.md) section
  10.4: an operator-supplied file, sha256-checked).
- **Front-end libraries:** vendored in the repository already (`static/js/vendor/MANIFEST.json`
  with each file's sha256); `scripts/nmas-vendor`, which fetches them from the npm registry, is
  development tooling.

---

## 5. Every other outbound call: the survey

**The search** (2026-10-16): every file `git ls-files` lists under `app.py`, `telnetlib.py`,
`modules/`, `routes/`, `scripts/`, `deploy/` and `lab/` (449 files, vendored files left out),
each line outside a comment matched against: `requests.Session|get|post|put|patch|delete(`,
`session.get|post|put|patch|delete(`, `session().get|post(`, an integration client's `._get(`,
`urlopen(`, `boto3.client(`, `psycopg.connect(`, `create_connection`, `socket.socket(` and
`.sendto(`, `ConnectHandler(` and `paramiko.Transport(`, `ping(`, `git` with `ls-remote`,
`fetch`, `push` or `pull`, an `ssh -o` argv, and `curl -`/`wget`. Then `smtplib`, `http.client`,
`httpx`, webhook, mail and model-provider names, which found nothing.

**The floor: 188 matching lines in 85 files.** Every one of the 85 files is placed in a row
below. Read by hand, a few lines are not calls: three docstrings in `modules/attention.py`, a
table entry in `scripts/nmas-check-secret-storage`, the hook `scripts/hooks/claude-no-host-writes`
(it recognises commands; it makes none), and three reads that send no packet (`topology_graph`'s
interface `ioctl`, `blast_radius`'s and `dhcp_discovery`'s `psutil` reads). The rows group call
sites by caller and destination: **36 rows**.

**`modules/outbound.py` is not a network module:** it masks configuration text on its way out
of a response (`config_text`, `mask_payload`, `no_store`), and makes no connection.

### 5.1 The application (product)

| # | Caller (file: function) | Destination | Purpose | Off when not configured? / offline replacement |
|---|---|---|---|---|
| 1 | `modules/identity.py`: `identify`, `_get_jwks_client` | `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs` | Access signing keys | Off: `is_configured()` refuses before any fetch while the three `cf_access_*` values are unset (default empty). Replaced by the local Keycloak's keys (1.8). |
| 2 | `modules/readers/ci_verdict.py`: `read`, `failed_steps` (through `scripts/nmas-deploy` `github_get`) | `api.github.com` | the status bar's CI verdict | **NOT off**: a declared reader, run every 900 s whatever is configured. Replaced by the signed verdict (3.2). |
| 3 | `modules/readers/app_pushed.py`: `judge`, `read`, `enrich` → `_verdict` | the application checkout's `origin` (ls-remote, fetch); `api.github.com` | the Update chip and preview | **NOT off**: run every 300 s whatever is configured. `origin` becomes the internal server or the bundle's bare repository; the verdict the signed tag. |
| 4 | `modules/nsot/remote.py`: `check_key_scope` (`ssh -T`), `check_read`, `check_write_probe`, `check_right_repository`, `_push_locked` | a list's git remote | verify and publish a network's history | Off: refused "has no remote configured" without `remote.json`. **GitHub-shaped:** `check_key_scope` expects GitHub's "Hi owner/repo!" greeting and `adopt` records `provider: "github"`; an internal server needs those made provider-aware ([EDGE_ARCHITECTURE](EDGE_ARCHITECTURE.md)). |
| 5 | `modules/nsot/remote.py`: `check_private` | `api.github.com/repos/<owner>/<repo>`, `github.com/<owner>/<repo>.git/info/refs` | "the repository is private" by anonymous probe | Off with no remote. **Offline it fails closed** (it refuses when the probe cannot run), so verification cannot pass without the internet: needs a per-provider privacy check. |
| 6 | `modules/nsot/archive.py`: `push_hook`, `_push_locked`, `unpushed_tool_tags` | a list's git remote | auto-push after a commit | Off: `auto_push_decision` needs a remote AND `auto_push`. |
| 7 | `modules/readers/remote_publication.py`: `judge` | each list's remote (ls-remote) | is the history published | Off per list: `no_remote` when the repository has no origin and no `remote.json`. |
| 8 | `modules/integrations/s3_archive.py`: `client` (and `archive.s3_archive_hook`) | the S3 endpoint (MinIO) | golden archive | Off: `is_configured()` needs `s3_endpoint` and `s3_bucket` (both default empty). On-premises. |
| 9 | `modules/netbox_client.py` (`_build_session` and its GET, POST, PATCH, DELETE), `modules/integrations/netbox.py`, `device_netbox.py`, `nsot/device_environment.py`, `netbox_context_mask.py`, `readers/credential_health.py` (tokens) | NetBox | inventory and IPAM | Off: `netbox_url` and the token default empty; a local-CSV network never asks. On-premises. |
| 10 | `modules/integrations/prometheus.py` and its callers: `alert_bands`, `neighbours`, `drained`, `prometheus_targets`, `history_promq`, `readers/` `topology_graph`, `adjacencies`, `coverage_reporting`, `platform_facts`, `restarts` | Prometheus | metrics | Off: `_get` answers "Not configured" without `prometheus_url` (default empty). On-premises. |
| 11 | `modules/integrations/loki.py` and its callers: `logs_page`, `device_logs`, `history_logq`, `host_steps`, `nsot/logging_path`, `readers/` `logs_summary`, `coverage_reporting` | Loki | logs | Off without `loki_url`. On-premises. |
| 12 | `modules/integrations/grafana.py` (`query`, `test_connection`), `device_page.py`, `readers/grafana_dashboards.py`, `readers/grafana_alerts.py` | Grafana | dashboards, alerts, panel queries | Off without `grafana_url`. On-premises. |
| 13 | `modules/integrations/kea.py`: `command` (and the DHCP readers and pages) | Kea's Control Agent | DHCP and ZTP reservations | Off without `kea_url`. On-premises. |
| 14 | `modules/integrations/proxmox.py`: `_get`; `readers/credential_health.py`: `tls` | Proxmox's API; its TLS certificate | the lab's hypervisor | Off: `is_configured()` needs every Proxmox setting; `tls()` skips a URL that is not https. Lab infrastructure ([NSOT_STAGE10_PLAN](NSOT_STAGE10_PLAN.md) 6.0b: out of the release). |
| 15 | `modules/records_db.py`: `connect`, `loopback` (`getaddrinfo`) | Mercury's PostgreSQL (loopback 5433) | records | Off: `records_db_host` empty keeps every store on its files. On the host. |
| 16 | `modules/integrations/monitoring_profile.py`: `sntp_answers`, `tcp_accepts` | the configured NTP servers; the telemetry, syslog and trap receivers | the monitoring profile's Test | Off per value: each probe runs only when its setting is set (`ntp_servers`, `telemetry_receiver`, `syslog_host`, `snmp_trap_host` default empty). On-premises. |
| 17 | `modules/connection.py` (`ConnectHandler`, `read_host_key`, the TCP 22 check), `telnetlib.py`, `modules/nsot/reload_op.py` (the return poll), `modules/readers/reachability.py` (ICMP, TCP 22) | the managed devices | the product's purpose | Inherent: the devices are the network being managed, on the organisation's network. Nothing to replace. |
| 18 | `modules/nsot/ztp_responder.py`, `modules/nsot/tftp_once.py` | devices on the ZTP or TFTP segment | serve a configuration to a device that asks | Inherent, on the managed segment; runs only when a person starts a transfer or the responder unit is installed. |
| 19 | `modules/nsot/ztp.py`: `dns_answerers` | broadcast DNS on the ZTP segment | prove nothing answers a configless device's DNS | Inherent, on the managed segment; asked for a ZTP reservation's posture only. |
| 20 | `modules/readers/topology_graph.py`, `modules/nsot/blast_radius.py`, `modules/dhcp_discovery.py` | none (this host's interfaces) | local reads | No packet leaves the host. |

### 5.2 The product's scripts on the host

| # | Caller | Destination | Purpose | Off when not configured? / offline replacement |
|---|---|---|---|---|
| 21 | `scripts/nmas-deploy`: `_deploy` (`git fetch origin`), `ci_verdict` → `github_get`; `_operations`, `_health` | `origin`; `api.github.com`; the app on loopback | the terminal deploy | The GitHub call is skipped by `--offline` only (3.1). Replaced by the signed verdict; `origin` the internal server or bundle repository. |
| 22 | `deploy/update/nmas-update`: `update` (fetch), `gate.ci_verdict`; `/health` | `origin`; `api.github.com`; loopback | the Update button's root half | **No offline path today** (3.1). Same replacement. |
| 23 | `scripts/host-steps/venv-1-build.sh` | `pypi.org`, `files.pythonhosted.org` | build the venv | Not optional: every release whose lock changes needs it. Replaced by the wheelhouse or mirror (section 4). |
| 24 | the other `scripts/host-steps/*.sh` that match, except row 29's (venv switch, swap, undo and rollback; the Loki, MinIO, PostgreSQL and topology steps; `lab/clab-sync/host-step-c663.sh`) | `127.0.0.1` only (the app's `/health`, Loki's 3100, MinIO's 9000, PostgreSQL's 5433, the retired topology service's 8088). `phase7-mode-on.sh`'s three matches are text it feeds the hook, not calls | one-off host steps | On the host. Nothing to replace. |
| 25 | `scripts/nmas-netbox-backup` (run by `nmas-netbox-backup.service`) | the hypervisor over SSH; an rclone remote | NetBox backup copies | Off per destination: `NMAS_BACKUP_PROXMOX_TARGET` and `NMAS_BACKUP_RCLONE_REMOTE` empty skip each. The off-box copy is a cloud bucket in this lab; offline, an on-premises target only. |
| 26 | `scripts/nmas-heartbeat-rules`, `nmas-telemetry-rules`, `nmas-integration-accounts`, `nmas-netbox-census`, `nmas-netbox-untagged`, `nmas-netbox-role-kinds-admin`, `nmas-capture-grafana-alerts` | Grafana, Loki, NetBox (through the app's clients or their URLs) | operator-run tools | Need the service's URL to do anything. On-premises. |
| 27 | `scripts/nmas-job-finished` (`nmas-job-finished@.service`) | the app on loopback (`NMAS_URL`, default `http://127.0.0.1:5000`) | job health now | On the host. |
| 28 | `scripts/nmas-tftp-once`, `scripts/nmas-ztp-responder` | devices | entry points of rows 18 | Inherent. |
| 29 | `scripts/host-steps/c725-config-pipeline.sh` (its check "the pinned commit is on GitHub"), and the workflow it installs into a network's config repository, `deploy/config-repo/nmas-config-check.yml` | `api.github.com`; GitHub Actions on the config repository, checking out the pinned Mercury commit from the public repository | the config repository's own CI (C725) | Runs only where a network's remote is on GitHub and the step was run. Offline: the same workflow on the internal CI (3.3), its pin naming the internal copy of the application repository; the host step's check asks that server. |

### 5.3 Development and lab tooling (stays on GitHub; never part of an installation)

| # | Caller | Destination | Purpose |
|---|---|---|---|
| 30 | `scripts/nmas-ci-log` | `api.github.com` | read failing CI runs (development) |
| 31 | `scripts/nmas-ci-dispatch` (curl, token on standard input) | `api.github.com` | dispatch, re-run, cancel runs (development) |
| 32 | `scripts/nmas-gate` (with `--push`, and `nmas-ci-log`) | GitHub | the commit gate's push (development) |
| 33 | `scripts/nmas-ci-env` | PyPI | build CI's environment on a developer machine (development) |
| 34 | `scripts/nmas-vendor` | `registry.npmjs.org` | vendor front-end libraries into the repository (development) |
| 35 | `scripts/nmas-host`, `scripts/nmas-lab-tunnel` | the lab hosts, by LAN or tunnel | the operator's access (lab; moves to `lab/`, 2.1) |
| 36 | `scripts/netmiko_timing_probe.py`, `scripts/nmas-tier2-probe`, `lab/clab-sync/clab-targets` | lab devices and the lab host | measurement probes and lab sync (lab) |

**Not off when unconfigured (the survey's finding):** rows 2 and 3, the `ci-verdict` and
`app-pushed` readers, ask GitHub (and the checkout's `origin`) on every installation, every 900 s
and 300 s, with no switch; and rows 21 to 23 need GitHub or PyPI to update at all (`--offline`
removes only row 21's GitHub call). Rows 4 and 5 are off without a remote, but with an internal
remote they fail on GitHub-shaped checks, and row 29 ties a network's config-repository CI to
GitHub and to the public application repository. Every other row is off until its setting is
set, or is the managed network itself, or never leaves the host.

---

## What it touches

- `modules/identity.py` (the verifier interface; the Keycloak verifier; Cloudflare as an optional
  verifier; `Identity` gains `method`, `groups`, `org_id`); `modules/route_gates.py` and
  `modules/invalidation.py` (the sign-in routes); `modules/nsot/repo.py`
  (`with_actor_verification` adds `Actor-Method:`); `modules/history_sources.py` (the method's
  words, the alias list); `modules/settings_schema.py`, `modules/installation_settings.py`,
  `modules/settings_scope.py` (the realm's settings, the Access card as an optional integration).
- The roles: `may()` and the role map ([NSOT_AUTHORIZATION](NSOT_AUTHORIZATION.md)).
- `scripts/nmas-deploy` (`ci_verdict` gains the signed-verdict source), `deploy/update/nmas-update`
  (the same sources), `modules/readers/ci_verdict.py`, `modules/readers/app_pushed.py`,
  `modules/update_op.py` (the bundle import as an operation).
- `scripts/host-steps/venv-1-build.sh`, `scripts/nmas-ci-env`, `requirements-test.txt`,
  `requirements-ci.txt` (hashes), the release CI (the wheelhouse and the bundle).
- `modules/nsot/remote.py` (`check_key_scope`, `check_private`, `adopt`'s provider), shared with
  EDGE_ARCHITECTURE; `deploy/config-repo/nmas-config-check.yml` and its host step (the pin
  naming the internal copy of the application repository).
- `deploy/` (Keycloak's container and its database in `mercury-postgres`; nginx's client
  certificate settings); `lab/` (the moved tooling, the lab CA, the two Keycloaks);
  `tests/test_lab_specifics.py` (`INVENTORY`).
- The manual: a page for sign-in (each way in, the CRL row, break-glass) and the Update page's
  verdict sources, with their How it works pages.

## Tests it needs

- **Verified person:** a token from another realm, another audience, an expired one, a forged
  `kid`, a service account, a token with no organisation identifier, and an untrusted peer,
  each refused with its outcome; the key set unreachable gives `verifier_unavailable`, a `kid`
  missing from a fetched set gives `invalid_token` (today's split, kept).
- **The verifier is measured:** Keycloak configured, Cloudflare configured, both (refused by
  name), neither (`not_configured`).
- **`Actor-Verified:` and `Actor-Method:`** for every row of 1.6, in
  `tests/test_actor_verified_trailer.py`, and History's words for each.
- **Roles:** a kit operator refused `approve`; a person removed from a group loses the role at
  the next session.
- **The proxy headers:** the client-certificate header and `X-Forwarded-For` honoured from the
  proxy's address only; a forged header from any other peer ignored.
- **The CRL:** current, past `nextUpdate` within the grace period (signs in, the row shows),
  past the grace period (refused in plain words, local sign-in still offered), a revoked
  certificate refused. Against the lab CA only.
- **The signed verdict:** a good signature passes; a wrong key, a tag on another commit, an
  unsigned tag and a missing tag refuse with exit 2's meaning; the docs-only walk over signed
  verdicts; the root updater uses only its own installed key.
- **The bundle:** a tampered file, a bad manifest signature, a non-fast-forward bundle and a
  release with no verdict each refused by name before anything moves.
- **Packages:** an install from a wheelhouse with `--no-index` succeeds; a wheel whose hash is
  not in the lock is refused; the build names a distribution with no wheel for the platform.
- **The survey keeps its floor:** a test that runs this note's search and fails on a file it
  does not place (the shape of `tests/test_lab_specifics.py`'s exact inventory), and a planted
  `urlopen` in a temporary file that it finds.
- **No reader asks GitHub when GitHub is not the verdict source.**
- Each new check shown able to fail.

## What it must not break

- **Two independent conditions,** a verified token AND a trusted peer: no verifier may drop the
  peer check, and an empty peer list still trusts nobody.
- **Nothing logged that identifies:** the token, the claims, the identifier and the certificate
  stay out of the log, as `identify()` holds today.
- **History's meaning:** every existing commit reads exactly as now (`access`, `host-shell`,
  `none`, absent); a new value never reads as verified by accident (`identity()` counts an
  unknown value as not verified).
- **Every gate stays in the table,** gated before input; `request_actor()` stays the only
  source of a recorded actor; a job's commits keep `access` through `carried()`.
- **No commit reaches the host unverified:** `nmas-deploy` and the updater keep exit 2 for
  "could not ask", never a pass; the docs-only walk keeps its rule; HEAD never moves past the
  target.
- **The lock decides every file:** `--require-hashes --no-deps` stays on every install, whatever
  the source.
- **Development on GitHub** is unchanged: CI, the gate, `nmas-ci-log`, `nmas-ci-dispatch`. A
  network with a GitHub remote and the lab's Cloudflare access behave exactly as now while
  configured so.
- **Device access stays through the tool only:** nothing in the reachability design opens a path
  to a device.

## Measurements still owed

Each is taken later, none now.

- **CRL fetch and size:** the organisation's CRL size and publication interval, and the time to
  load it into nginx and Keycloak. Method: time the load of a CRL of that size from the lab CA,
  scaled to the real size. Where: the lab's Mercury host, then a kit-sized host.
- **The CRL grace period:** the longest time a kit is expected offline, against the CRL's
  `nextUpdate` interval. Method: the organisation's records of link outages, and the CRL's own
  dates. Where: headquarters, inside the secure environment.
- **TOTP clock tolerance:** the drift of a kit's clock over its longest offline period, with and
  without the GPS clock. Method: compare the host clock with a reference at reconnect, over a
  multi-day disconnect. Where: a lab host with its time source removed.
- **Keycloak's memory on the small tier:** resident memory idle and during a burst of sign-ins,
  on the smallest supported host. Method: the container's memory statistics across a scripted
  sign-in run. Where: the lab, on a host sized like the small tier.
- **Keycloak's start time and PostgreSQL's added load** on `mercury-postgres`. Method: time to
  ready after a restart; query counts per sign-in. Where: the lab's Mercury host.
- **The `--offline` suite's duration on the target hardware** (it is the gate when no verdict
  arrives). Method: `offline_forecast`'s own record after a run. Where: a kit-sized host.
- **The wheelhouse's size and completeness:** whether every lock entry has a wheel for CPython
  3.12 x86_64 Linux. Method: `pip download --no-deps --require-hashes -r requirements.lock
  --only-binary=:all:` into an empty folder and list what fails. Where: release CI.
- **The bundle's size** (git history, wheelhouse, images), against what can be carried. Method:
  build one release bundle. Where: release CI.
- **Which claims Keycloak's chosen version issues** for the authentication method, the groups
  and a service account. Method: decode a token from each way in. Where: the lab's Keycloak.

## Dependencies on the other four notes

- **[EDGE_ARCHITECTURE](EDGE_ARCHITECTURE.md)** depends on this note for its offline
  prerequisites: local authentication (section 1), updates (3) and packages (4). This note
  depends on it for the upstream-manager connection (section 2), the build standard that carries
  the CRL, the groups and the signed verdict key, the trustworthy local clock (TOTP), the reduced
  operator mode the kit-operator group selects, and the provider-aware git remote checks (rows 4
  and 5).
- **[SITES_DESIGN](SITES_DESIGN.md):** none directly; its site and network scopes are what the
  role map's per-network roles are scoped by.
- **[FLOWS_DESIGN](FLOWS_DESIGN.md):** its flow store is one more on-premises service whose
  images and packages follow section 4, and whose outbound calls join section 5's survey when
  built.
- **[IPAM_IMPORT_DESIGN](IPAM_IMPORT_DESIGN.md)** and
  **[BRINGUP_FROM_DOCUMENTS](BRINGUP_FROM_DOCUMENTS.md):** their signed mapping and parser
  profiles travel with the build standard, verified the same way as the release (3.2); the
  bring-up's model file follows section 4; and every commit they make records the person by the
  identifier of section 1.5.
