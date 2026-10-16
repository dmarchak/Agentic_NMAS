# Edge architecture: a Mercury instance per fly-away kit, under a headquarters manager

**FUTURE: post-cutover, Phase 10 or later.** Nothing here is built, and nothing here is Phase 7
work. It is a design note written on the operator's request of 2026-10-16, judged FUTURE against
[MERCURY_CHARTER](MERCURY_CHARTER.md) ("worth doing, not now: parked, recorded"). Every statement
about today's code names the file it was read from; every statement about the design is a
proposal, and every number it needs is listed under *Measurements still owed*, none taken. It is
the largest of six sibling notes: SITES_DESIGN.md, FLOWS_DESIGN.md, IPAM_IMPORT_DESIGN.md,
BRINGUP_FROM_DOCUMENTS.md and OFFLINE_OPERATION.md, all in `docs/`, cross-referenced by those
names.

**The classified-documents constraint applies throughout.** In the setting this note designs for,
provider documents and values taken from them may be classified. No real document is ever given
to a developer, an AI service or this project, and none is reconstructed from memory. Every
example here is synthetic: node numbers are small invented integers, addresses come only from
192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24 and 2001:db8::/32, and ASNs from 64496 to 64511.
Real formats are taught to Mercury inside the secure environment by headquarters NetOps.

## 1. The case, and the decision that shaped this note

The case (the operator's former job):

- a fleet of identical fly-away kits, each a Cisco switch, a Cisco 8000v, a Palo Alto firewall
  and a geostationary satellite uplink at 500 to 800 ms round-trip time;
- a stable headquarters management network;
- on-site operators who must manage their kit while disconnected and while bringing its
  satellite link up. Headquarters approves changes, but operators must act before help can be
  reached;
- kit operators far less trained than headquarters NetOps: everything they touch is as simple as
  possible, in plain words, with every hard decision made in advance by headquarters;
- an IPAM kept in an Excel spreadsheet (IPAM_IMPORT_DESIGN.md);
- a provider data sheet per kit for its first connection, one document holding the values for
  many sites, each site identified by a node number (BRINGUP_FROM_DOCUMENTS.md).

**The decision (the operator, 2026-10-16): each kit is its own network on its own Mercury
instance, under a headquarters manager.** An earlier request made the kits sites within one
network. Once it was clear that kit operators must manage their kit while disconnected, that
shape could not stand: a network's operations run where its Mercury runs, and a kit cut off from
headquarters would be cut off from its own control plane. SITES_DESIGN.md keeps the multi-site
capability for any single instance (headquarters' own management network among them) and points
here for the kit fleet.

## 2. A full instance per kit, compared with a lighter edge agent

Two shapes were weighed.

| Question | A lighter edge agent (headquarters' Mercury drives it) | A full Mercury instance per kit (chosen) |
|---|---|---|
| Who previews, confirms, verifies and rolls back | Headquarters' Mercury; the agent relays commands | The kit's own instance, the same code as headquarters' |
| A change while the satellite is down | Impossible, or a second, reduced change path on the agent | The ordinary path: preview, confirm, apply, verify, rollback, record (`modules/preview_confirm.py`, `modules/pipeline.py`) |
| Verify and rollback across a 500 to 800 ms link that can drop mid-change | Yes: the controller-side rollback (`pipeline._stage_rollback`) would have to cross the link it may have just cut | Never: they run on the kit's LAN |
| Where the kit's history lives while offline | Queued on the agent, or lost | The kit's own repository, the system of record already (`modules/nsot/archive.py`'s module docstring: "Git is the system of record") |
| Device credentials | Held at headquarters and sent down, or duplicated on the agent | Held on the kit only; headquarters never holds them |
| What an operator sees with no link | Whatever the agent was given | Every local screen, in the reduced operator mode (section 11) |
| Cost | One control plane to run and patch | A full stack per kit (Mercury, its repository, its records database, NetBox and the monitoring stack as configured), patched one release at a time, and headquarters reading kits one release behind (section 10.6) |

**Why the full instance was chosen.** The deciding requirement is the first row: kit operators
must act before help can be reached, and the operations that make a change safe (the preview the
confirm is bound to, the verify, the rollback, the record) must therefore run where the devices
are. An agent that can only relay would either refuse every offline change, which the case
forbids, or grow a second change path with its own preview and rollback, which is the "two entry
points share one code path" rule (CLAUDE.md, "One owner per piece of state; one home per action")
broken by design. A full instance reuses every safety the product already has. Its cost, the stack
per kit and the version skew, is accepted and designed for (sections 4 and 10.6); the kit's
hardware sizing is a measurement owed.

## 3. A kit's identity: its node number

Each kit's node number is part of its identity: set at staging at headquarters, signed with
headquarters' key, and shown prominently on every screen of the kit's instance (beside the
network's name in the scope bar, `templates/v2/_settings_scope.html` being where a network's
scope is drawn today). **The operator never types it.** Everything node-scoped reads it from the
signed identity: the document extraction's node region (BRINGUP_FROM_DOCUMENTS.md), the staged
IPAM plan (IPAM_IMPORT_DESIGN.md), the kit's branch name (section 8.4) and its registry row at
the manager (section 7.5). A kit whose identity does not verify against headquarters' public key
refuses every node-scoped operation, saying so in plain words with a code to call in.

## 4. The central build standard

A headquarters instance holds the build standard in a central repository that kits pull from, a
read-only fetch separate from the kit's own publication (section 8.4):

- templates (today each network's library is `config_repo/templates/`, approval keyed on the
  import closure: `modules/nsot/templates_repo.py`, `modules/nsot/approval.py`);
- the monitoring profile (docs/MONITORING_PROFILE.md);
- base intent (`host_vars/`, `modules/nsot/hostvars.py`);
- bring-up profiles (section 12), provider parser profiles (BRINGUP_FROM_DOCUMENTS.md) and IPAM
  mapping profiles (IPAM_IMPORT_DESIGN.md);
- the standard playbooks (section 6.1);
- the organisation CA's certificate revocation list for smart-card sign-in (section 10.1).

Every item is signed by headquarters and verified on the kit before use (section 10.2). A kit
takes a new build standard as a change of its own, previewed: what moves, which devices it would
touch, and whether any committed intent departs from it.

## 5. What crosses the link

The satellite is expensive, slow and intermittent. What crosses it is decided by size and by
whether losing it would lose a record.

### 5.1 Small summaries, pushed often

The subordinate pushes, as it changes and on a heartbeat: health rollups (counts by state per
device class), its Needs attention rows (`modules/attention.py`), inventory, change records (the
receipts `modules/nsot/receipts.py` writes) and goldens (its repository's commits). Each is the
value a reader already stores (`modules/reader_job.py` keeps `last_good` with `value_at`), sent as
a delta when the manager acknowledged the previous one.

### 5.2 Bulky data, pulled on demand and bounded

Flows (FLOWS_DESIGN.md, sampled at satellite sites), logs (Loki, through
`modules/integrations/loki.py`) and detailed metrics (Prometheus, `modules/integrations/prometheus.py`)
stay on the kit. The manager asks for them, naming a window and a ceiling in bytes; the kit
answers within the ceiling and says when it truncated ("a read returning exactly its page size is
truncated", CLAUDE.md, Measurement and testing).

### 5.3 When the link is down

The manager shows each kit's last-known state with its age, in the shape the readers already
use: `reader_job` keeps the last good value when a read fails, and `remote_publication.status_for`
returns the value with `value_at` and `stale_after_seconds`. A stale summary is drawn as stale,
never green (the header strip's rule, `templates/v2/_strip.html`: "older than the … s its reader
promises").

### 5.4 Records before bulky data

When the link returns, the kit sends in this order: commits and tags (section 8), change records,
the emergency-change branch (section 6.3), then summaries, and only then anything bulky the
manager asked for. A link that drops again mid-catch-up has then lost no record.

## 6. Three kinds of change

### 6.1 Standard: headquarters-signed playbooks, runnable offline

A standard change is a playbook headquarters signed, with bounded inputs (each input's type and
the set or range it may take), runnable on the kit with no link. Its precedent in this repository
is docs/STANDING_APPROVAL_LOG.md: a standing authority under which decisions are taken without
asking again, each recorded as one line. That log is a document; a standard change needs the
machine form: the playbook, its input bounds and headquarters' signature, verified on the kit
(section 10.2) before the preview is drawn. The run is the ordinary lifecycle
(`modules/preview_confirm.py`'s six parts; `modules/pipeline.py`'s stages), confirmed by the kit
operator, with the playbook's identity and signature in the hash and in the receipt. Inputs
outside the bounds make it an emergency change (6.3).

### 6.2 Normal: approved at headquarters, carried out locally

A normal change is previewed and approved at headquarters, then sent down the upstream connection
(section 7) and carried out by the kit's instance: its own preview, re-rendered on the kit and
compared with the approved program byte for byte ("What is confirmed is what is sent",
`tests/test_deploy_contract.py`), its own verify and its own rollback. Verify and rollback never
cross the satellite. The record reads "by the manager, approved by <person>" (section 7.6).

### 6.3 Emergency: offline, with a reason, reviewed later

An emergency change is made on the kit with no approval reachable: a stated reason, the ordinary
local preview, verify and rollback, and a mark for headquarters review. **Emergency changes go on
the kit's own git branch.** On reconnect, headquarters merges it (accepts) or orders a revert,
which the kit then carries out as a normal change. Conflicts between the emergency branch and
anything headquarters sent meanwhile are shown, never auto-resolved: the same stance as
`archive._push_locked` today, which on a rejected push records "resolve the divergence manually;
Mercury will not force-push".

## 7. Manager and subordinate nodes

### 7.1 A strict hierarchy, authority flowing down

Each node has at most one manager, and a manager may itself be managed (headquarters, regional,
kit). The manager may view, query and modify a subordinate. A subordinate may never view, query
or modify its manager.

### 7.2 Connection direction is separate from authority

The subordinate dials out and holds one mutually authenticated connection, which works through
NAT and the kit firewall; the manager sends its requests down it. **Nothing is opened into a kit.**
Reachability is the deploying team's choice: the product documents only its own port and TLS
certificate, the proxy headers it trusts and from which addresses, and the upstream-manager
connection's outbound port, protocol and pinned certificate (OFFLINE_OPERATION.md).

### 7.3 The only upward messages

The subordinate holds no credential for the manager's interface. Its only upward messages are a
fixed, validated set:

- **heartbeat:** alive, version, measured RTT and loss;
- **reports of its own data:** summaries, Needs attention, change records (section 5);
- **a request to be tested** (the callback in check 8 below).

Anything else is refused by the manager and recorded, naming the message kind and the node.

### 7.4 On the subordinate: the Upstream manager card

A card, "Upstream manager", in Settings › Installation › Connections. Today that tab holds the
Records database card and the NetBox connection, Proxmox, Commit author and Server cards
(`modules/installation_settings.CARDS`, drawn by `templates/v2/settings_installation.html`; Test
and Replace… through `test_card` and `replace_secret`). It is counted in the header's
Integrations item: the strip (`templates/v2/_strip.html`, served by `routes/device_v2.strip`)
draws "Integrations n of m" from the integration health reader
(`modules/readers/integration_health.py`), which probes every class in
`modules/integrations.REGISTRY`. The upstream manager becomes one more registered integration,
optional and off unless configured.

The strip today has four states: not probed, stale, some down or refusing a credential, and all
answering. A kit that is offline by design (bringing its link up, or between passes) needs a
fifth: **link down, expected**, drawn as information with its age, never as "down" in warning
colour (section 8.2 is the same distinction for the repository).

Its Test checks, in order, each with a PASS line or the place to look:

1. **DNS:** the manager's name resolves (from the kit's own resolver).
2. **TCP reach:** names a refusal (something answered and refused: the manager's port or a
   firewall rule) or a timeout (nothing answered: the satellite link, routing or the kit
   firewall's outbound rule), and where to look for each.
3. **TLS** with the manager's pinned certificate: the fingerprint expected and the one offered.
4. **Clock offset** against the manager, with the bound it is judged against (identity depends on
   the clock: section 10.3).
5. **Mutual trust:** this node is enrolled and not revoked.
6. **Path MTU** across the tunnel.
7. **Measured RTT and loss**, which set the node's own time limits (section 13.1).
8. **A manager-initiated callback:** the manager sends a request down the connection and the kit
   reports it arrived, testing the manager-to-kit direction the kit cannot test alone.

The Test's answer is kept (who, when, each check) and readable later, as the Records database
card's is (`installation_settings.records_card`).

### 7.5 On the manager: the Subordinate nodes page

A new screen, so it needs a mockup and sign-off before it is built (CLAUDE.md, "No new screen or
tab without a mockup"), and leads with counts by link state for a large fleet (CLAUDE.md, "Built
for large fleets").

- **Enrolment only, never discovery.** A one-time code is issued at headquarters; the node
  presents it with its certificate; the page shows the node's certificate fingerprint; a person
  approves. This is the deliberate-trust idea of C906's host keys (`modules/host_keys.py`) taken
  one step further. Today a device's SSH key is **kept on first contact** (trust on first use,
  recorded with who and when), and only a *change* needs a person's reviewed re-key
  (`modules/nsot/rekey_op.py`) or a planned window declared before it. Enrolment has no first-use
  trust: the first contact itself waits for a person.
- **A registry row per node:** node number, name, site, fingerprint, version, last heard, link
  state, RTT, emergency changes awaiting review.
- **Revocation** cuts a node off at once (its certificate refused on the next handshake, its
  connection closed) and queues a wipe for when it next connects (section 10.5 states what a wipe
  can and cannot protect).

### 7.6 A manager's change runs on the subordinate

A manager's change runs on the subordinate through its own preview, verify and local rollback,
recorded as "by the manager, approved by <person>". The manager never connects to a kit's devices
directly, and never holds their credentials. Today a commit records `Actor:` and
`Actor-Verified:` (`modules/nsot/repo.with_actor_verification`, values from
`identity.actor_verification`: `access`, `host-shell` or `none`). A manager's change needs a value
of its own naming both the manager node and the approving person, verified by the manager's
signature on the request; the vocabulary is OFFLINE_OPERATION.md's to settle with the new
verifier.

### 7.7 A subordinate refuses only for safety

Decision (the operator, 2026-10-16): a subordinate may refuse a manager's change for safety only,
queueing it and reporting why; never for preference. Safety means:

- **a device held by a local operation** (`modules/nsot/device_ops.py`: one operation per device
  across processes, refused by name). The device hold stays a refusal, never a queue; what is
  queued is the manager's *request*, visible on both ends with the hold's words;
- **a bring-up in progress** (section 12);
- **a change that would cut its own link**: a change to the path the kit reaches its manager on,
  judged by the same reasoning as Reload's blast radius (section 13.2) applied to the uplink
  devices, and by CLAUDE.md's rule that a change to the path the tool reaches a device on needs a
  repair route independent of that path.

## 8. Local-first repositories and catch-up

**Today, the local repository is the system of record and the remote a copy.**
`modules/nsot/archive.push_hook` is a post-commit hook (registered by `register_default_hooks`,
run on a background thread with a 30 s timeout by `modules/nsot/hooks.py`) that never holds the
repository lock and never delays or rolls back a commit. It pushes HEAD, read once under
`remote.publish_lock`, to the list's branch, then exactly the tags named for that save and any
`pending_tags` an earlier hook could not send. Before pushing it asks
`remote.auto_push_decision`: if the commit introduces a gated secret kind nobody acknowledged, or
raises an acknowledged count, the push is **held** and recorded (`remote.record_push_held`) until
a person re-acknowledges.

`modules/readers/remote_publication.py` answers "is it published?" every 120 s and after each
commit (`refresh_hook`), comparing HEAD with `git ls-remote` of the remote's branch (bounded at
`LS_REMOTE_TIMEOUT_S = 10`). Its states are `in_sync`, `ahead`, `remote_ahead`, `diverged`,
`no_branch` and `not_asked`, with `record_unreadable` beside any of them. `describe` turns an
unheld `ahead` red once its oldest commit has waited `UNPUSHED_DANGER_S`, five reader intervals
(600 s, ten minutes), because on the host a commit pushes within seconds.

For kits offline for days, four changes:

### 8.1 Automatic catch-up

When the reader finds the remote reachable again and the repository `ahead` with no hold, it
pushes, with back-off, instead of waiting for the next commit or a person's Push now. It pushes
through the same `push_hook` path under the same `publish_lock`, so there is still one publisher
per repository, and the acknowledgement gate still decides first. A held push is never sent by
catch-up.

### 8.2 An expected-offline state

When the upstream-manager link check (section 7.4) says the link is down, "N commits waiting for
the link (oldest <age>)" is information, not a fault; only a reachable remote that still refuses
the push is red. Today's ten-minute red is right for headquarters and wrong for a kit. The
`UNPUSHED_DANGER_S` judgement stays as it is for any network whose link is not known to be down,
so the lab behaves exactly as now.

### 8.3 The remote is headquarters' own git server

The remote is headquarters' self-hosted git server (Gitea, Forgejo or GitLab, or the headquarters
Mercury), not GitHub. `remote.remote_url` already builds an SSH remote from an alias
(`<ssh_alias>:<owner>/<repo>`), so any SSH git server can be pushed to. **What assumes GitHub
today**, read in `modules/nsot/remote.py`:

- `_adopt_locked` records `"provider": "github"` on every adopted remote;
- `SETUP_SHAPES` validates the owner and repository name by GitHub's rules (an owner of at most
  39 characters of letters, digits and hyphens);
- `check_key_scope` establishes that the deploy key is scoped to one repository by reading
  GitHub's SSH greeting (`Hi owner/repo!` against `Hi username!`); another server's greeting
  differs, and the check would refuse;
- `check_private` establishes privacy by anonymous HTTPS requests to `api.github.com` and
  `github.com`, and **refuses when it cannot run them** ("no outbound HTTPS?");
- `push` refuses unless `verified_at` is set, which `verify` sets only when every check passes
  and the write probe ran; `enable_auto_push` refuses until a push has succeeded.

The consequence, followed through the code: **on an installation that cannot reach github.com,
`check_private` always fails, so `verified_at` is never set, so `push` always refuses, so
`enable_auto_push` can never be turned on.** A kit's repository could not be published to
headquarters at all today. The design gives `remote.json` a provider with its own checks: for a
headquarters server, privacy is established by that server's own answer to an anonymous request
(its address taken from the record, inside the enclave), and key scope by a read and a write
probe against a second repository the key must not reach. Which checks each server type can
support is a measurement owed.

### 8.4 No shared branch between a kit and headquarters

Each kit pushes its own branch (or its own repository; `remote.json` already carries `branch`)
and headquarters merges, so `diverged` cannot arise from ordinary offline work. The kit's pull of
the build standard (section 4) is a separate read-only fetch from the central repository, never a
pull into the kit's own branch.

**A network with a GitHub remote and a reliable link (the lab, today) behaves exactly as now.**

## 9. Classified networks

### 9.1 The marking and the export point

A network may carry a classification marking. A marked network refuses any destination outside
its enclave, checked **at the point of export**, the way the publication gate already holds
secrets: `remote.scan_history_secrets` counts each live secret by kind and salted fingerprint,
`remote.acknowledgement_covers` compares that with what a person acknowledged, and
`archive._push_locked` holds the push when it does not cover it. The classification check is
simpler and stricter: it asks of each destination whether it is inside the enclave (an allowlist
headquarters signs with the build standard), not what the content holds, because a classified
network's every byte is in scope.

### 9.2 Extracted values inherit their source's classification

Once a value from a classified document is in intent, it is in the rendered goldens, in every
later commit and in every copy of the repository. So the marking is the network's, applied to its
repository as a whole, never to individual values; and a network becomes marked before the first
classified value is committed, never after.

### 9.3 Every path by which data leaves a host today

Surveyed in the code on 2026-10-16, so that none is missed. "App" paths are the program's own and
can carry the export check; "host" paths are configuration outside the program, which the check
cannot see and the deploying team must audit.

| # | Path | Where in the code | What leaves | Kind |
|---|---|---|---|---|
| 1 | Automatic git push after each commit | `modules/nsot/archive.push_hook`, `_push_locked` | the branch at HEAD and named tags: goldens **verbatim**, intent, templates | app |
| 2 | A person's Push now | `modules/nsot/remote.push`, `_push_locked` (`--follow-tags`, then `refs/notes/*`) | the same, plus notes | app |
| 3 | The remote's verification | `remote.check_key_scope` (`ssh -T`), `check_read` (`ls-remote`), `check_write_probe` (an empty-tree orphan commit pushed, its ref deleted) | an SSH greeting, ref names, one empty commit object | app |
| 4 | The privacy check | `remote.check_private` | anonymous HTTPS to `api.github.com` and `github.com`, naming the owner and repository | app |
| 5 | The publication reader | `modules/readers/remote_publication.py` (`ls-remote` every 120 s and after each commit); `archive.unpushed_tool_tags` (`ls-remote --tags`) | ref names only | app |
| 6 | The golden archive | `archive.s3_archive_hook` through `modules/integrations/s3_archive.py` (`put_golden`) | changed goldens, **masked** (docs/SECRETS.md, "The golden archive is masked"), with commit, source and actor as object metadata | app |
| 7 | NetBox writes | `modules/netbox_client.py` (its write chokepoints) | device records, interfaces, addresses, provenance | app |
| 8 | Integration reads | `modules/integrations/` (Grafana, Prometheus, Loki, Kea, Proxmox; `base.IntegrationClient.session`) | query terms: device names, selectors, time ranges | app |
| 9 | Device sessions | `modules/connection.py` (`open_ssh`); `pipeline._push_via_netconf`, `_push_via_netmiko` | configuration lines and credentials, to the device | app |
| 10 | Boot files and ZTP | `modules/nsot/tftp_once.py`; `modules/nsot/ztp_responder.py` | a device's boot configuration, to that device | app |
| 11 | Browsers | `modules/outbound.config_text` (masked unless a verified person reveals, recorded first in `reveal_audit`); `outbound.mask_payload` (previews); `modules/breakglass_export.py` (a sealed record, built in memory) | configuration text, previews, the break-glass record | app |
| 12 | Identity's key fetch | `modules/identity._get_jwks_client` (`certs_url`) | a request to the access proxy's certificate endpoint; no network data | app |
| 13 | The CI verdict and updates | `modules/readers/ci_verdict.py` (loads `scripts/nmas-deploy`'s `ci_verdict`); `modules/update_op.py` | requests to GitHub naming commits; no network data (OFFLINE_OPERATION.md) | app |
| 14 | Connector tests | `modules/integrations/monitoring_profile.py` (`sntp_answers`, a TCP connect to the telemetry receiver) | an SNTP request, a TCP handshake | app |
| 15 | Device logs to Loki | `deploy/rsyslog/10-network-devices.conf` files each device's syslog under `/var/log/network/`; Alloy, configured on the host, ships them to Loki ("The app only queries Loki", docs/NSOT_STAGE10_PLAN.md) | every device log line | host |
| 16 | NetBox backups | `scripts/nmas-netbox-backup` | NetBox's database, media and configuration, gpg-encrypted to a public key, by rsync to the hypervisor and dailies off-box by rclone | host |
| 17 | VM images | the hypervisor's nightly backup of the NMAS VM (read, never written, by `modules/integrations/proxmox.py`) | the whole disk, `data/key.key` included | host |

Two that do not leave: the records database is checked to be on a loopback address by its Test
(`modules/records_db.TEST_STEPS`, "loopback"), and Kea's reservations are files in Kea's own
configuration folder on the host (`modules/dhcp_reservations.py`). **No AI or cloud model is
called today:** the AI family left on 2026-10-14 (D15, named in
`modules/installation_settings.py`'s `TABS` comment), and Phase 8 brings back a local responder
(docs/PHASE8_PLAN.md). A marked network refuses any cloud model when one exists; the local model
is BRINGUP_FROM_DOCUMENTS.md's.

## 10. Offline prerequisites

Identity, updates and packages are designed in OFFLINE_OPERATION.md; this section names what the
edge design needs from them and does not design them again.

### 10.1 Local authentication

Decided (the operator, 2026-10-16), designed in OFFLINE_OPERATION.md: Keycloak is the product's
identity, one per instance, on the instance's own PostgreSQL. Three ways in, in order:

1. smart-card X.509 client certificates against the organisation's CA, the CRL distributed with
   the build standard (section 4), cached, with a grace period; this works offline;
2. a brokered "Log in with HQ" to headquarters' Keycloak when the link is up;
3. local TOTP accounts plus one recorded break-glass admin, offline.

Roles come from the token's groups (HQ NetOps, kit operator) and select the full interface or the
reduced operator mode (section 11), and who may approve. History records a person by a stable
organisation-wide identifier (the certificate's subject ID), so headquarters recognises the same
person in every instance. The Cloudflare Access verifier becomes an optional integration, off
unless configured.

**Every place that relies on the access-proxy identity today**, found by parsing every non-test
Python file for calls to `modules/identity.py`'s functions (44 files; `app.py` imports
`request_actor` and calls nothing). Each must mean the same thing whichever verifier is in front:

| Where | What it relies on |
|---|---|
| `modules/identity.py` itself | `identify` verifies `Cf-Access-Jwt-Assertion` against the team's keys (`certs_url`, `_get_jwks_client`) and the raw socket peer (`trusted_peers`); settings `cf_access_team_domain`, `cf_access_aud`, `cf_access_trusted_peers`, `cf_access_jwks_ttl`, `cf_access_service_labels` (`modules/settings_schema.py`) |
| `modules/route_gates.py` (`enforce`, `socket_gated`) | `identity.require` before every mutating route and gated socket event, by gate kind (`reveal`, `approve`, `confirm`, `publish_remote`, `configure`, `break_glass`: `identity.GATED_ACTIONS`) |
| `modules/preview_confirm.py` (`confirm_part`, `control_gate`) | `identify` and `may`: who is confirming, and every gated control drawn disabled with its reason |
| `modules/nsot/repo.py` (`with_actor_verification`) | `actor_verification`: every commit's `Actor-Verified:` trailer (`access`, `host-shell`, `none`) |
| Jobs a gated request starts: `modules/deploy_job.py`, `modules/nsot/capture_job.py`, `modules/nsot/reload_op.py`, `modules/nsot/rotate_op.py`, `routes/adopt_v2.py`, `routes/credential_profiles_v2.py`, `routes/rotate.py`, `routes/device_v2.py`, `routes/v2.py` | `verified_identity` and `carried`: the verified person carried into the job's thread |
| `modules/outbound.py` (`config_text`) | `require(…, "reveal")`, and `service_label` for the reveal record |
| `modules/host_keys.py` (`who`), `modules/nsot/device_ops.py` (`hold_device`) | `request_actor`: who kept a key, who holds a device |
| `modules/installation_settings.py` (`access_view`), `routes/identity.py` (`status`) | `posture`, `may`, `is_configured`, `trusted_peers`: the Access and identity tab and the status route |
| `modules/network_choice.py` (`for_request`), `routes/operations.py` (`viewer_key`), `routes/network_v2.py`, `routes/update.py` | `viewer`: the per-person network choice and who is looking |
| Recorded actors in routes: `routes/attention.py`, `breakglass.py`, `bulk_intent_v2.py`, `deploy.py`, `dhcp_v2.py`, `golden.py`, `intent_v2.py`, `netbox_safety.py`, `netbox_v2.py`, `onboard.py`, `onboard_v2.py`, `persist.py`, `privileged_v2.py`, `reads_v2.py`, `remote.py`, `remote_v2.py`, `restarts.py`, `retire.py`, `settings_v2.py`, `templates.py`, `templates_v2.py`, `templatize.py`, `topology_v2.py` | `request_actor`, `identify` or `require`: the verified actor written into receipts, records and commits |

### 10.2 Signature verification of approvals

The kit holds headquarters' public key, delivered at staging, and verifies every signed item
before use: its own identity (section 3), the build standard and its playbooks (section 4), a
normal change's approval (section 6.2), and the manager's requests (section 7.6). Which signature
format (signed git tags and commits, or detached signatures over the release bundle
OFFLINE_OPERATION.md designs) is decided there; the edge design needs one verifier, used at every
one of those points.

### 10.3 A trustworthy local clock

Identity depends on the clock offline: TOTP codes, certificate validity, the CRL's grace period.
So do planned-restart windows (`modules/restarts.py`), receipts and the expected-offline ages of
section 8.2. A kit with no link has no network time, so it needs a local reference (GPS), and the
Upstream manager card's check 4 compares it with the manager's when the link is up.

### 10.4 Local break-glass and rotation

Both already run on the instance: the break-glass record is built to open during an outage
without the application's stores (`modules/breakglass.py`, "deliberately dumb and independent";
`modules/breakglass_export.py`), and rotation is a local operation (`modules/nsot/rotate_op.py`,
`modules/nsot/credential_rotation.py`). The edge design adds only that a rotation's record
crosses the link with the other records (section 5.4), and never the value.

### 10.5 Encryption at rest, and remote wipe

`data/key.key` opens every secret (CLAUDE.md, Key architecture) and sits on the same disk as the
encrypted `devices.csv`, so a lost kit's disk yields its credentials. Encryption at rest, with a
key that is not on the disk, is therefore the protection for a kit that can be lost; the queued
wipe of section 7.5 runs only if the kit connects again, so it protects a kit that is found and
reconnected by someone else, not one that never reconnects. Both are stated on the Subordinate
nodes page beside Revoke.

### 10.6 Headquarters reading kits one release behind

A fleet is never upgraded at once. The heartbeat carries the kit's version; the manager accepts
reports from its own release and the one before, and refuses an older one by name ("node 7 runs
<version>; this manager reads <version> and <version>"). Updates themselves are
OFFLINE_OPERATION.md's.

## 11. Two audiences, two depths

Headquarters NetOps sees the full Mercury. The kit operator sees a reduced, plain-language mode,
**selected by the token's group** (section 10.1), never by a switch a person can flip:

- status;
- the guided bring-up (section 12);
- the standard playbooks (section 6.1);
- emergency changes with a reason (section 6.3);
- "Call headquarters with code <X>" wherever a decision is not theirs.

No jargon on the operator's screens, and every error says what to do next. The reduced mode is a
selection of screens the full interface already has, drawn with fewer words of evidence (CLAUDE.md,
"The screen answers the person's question; the evidence is one level down"), not a second
interface: each of its screens is a signed-off v2 screen. Who may approve follows the same token
groups through `identity.may`'s successor (OFFLINE_OPERATION.md).

## 12. The guided bring-up

Power, modem lock, link, routing, the tunnel to headquarters: each step a real read with a PASS
line or a plain next step, drawn on the one stepper (`modules/run_stepper.py`). Every read goes
through Mercury's read-only paths (`modules/readonly_commands.py`'s allowlist) or the Upstream
manager card's checks; nothing is a terminal step (CLAUDE.md, "No terminal steps"). The modem is
not a Mercury platform, so its step is a checklist the operator ticks against the values
BRINGUP_FROM_DOCUMENTS.md extracted. While a bring-up runs, the kit refuses a manager's change for
safety (section 7.7).

## 13. The satellite case

Five parts of the earlier request's item 7 fit one kit's instance or the fleet. Each states the
measurement it needs.

### 13.1 Time limits from each link's measured RTT

**Today, bounds are global numbers, each derived once.** `modules/connection.CONNECT_TIMEOUT_S` is
35 s, "2.5 times the slowest connect measured", with the recorded follow-up "per platform, and per
network once P.8 exists"; `remote_publication.LS_REMOTE_TIMEOUT_S` is 10 s from one 0.99 s sample
on the host; the post-commit push hook is registered with 30 s (`archive.register_default_hooks`);
`connection.is_device_online` probes with 2 s; `reload_op.wait_bound` is 2.5 times a platform's
measured boot.

On a kit, devices are on its LAN, so device bounds are unchanged. What crosses the satellite is
the upstream connection, the git remote (section 8) and the manager's pulls (section 5.2), and
those take their bounds from **the link's own measured RTT and loss** (the Upstream manager
card's check 7, refreshed by every heartbeat), by CLAUDE.md's rule: about 2.5 times a measured
time, written beside it, and a firing bound naming what ran. The 10 s `ls-remote` bound, set from
a LAN sample, is re-derived from a measurement on the kit's link; an SSH git exchange needs
several round trips before any data moves, so a fixed LAN-derived bound would fire on a healthy
satellite link. Per-site bounds within one instance (headquarters reaching its own remote sites)
are SITES_DESIGN.md's; this note supplies the per-link measurement they would use.

### 13.2 Holding back alerts behind a dead uplink

**One "unreachable" row, not a row per device behind it.** Reload's preview already answers
"what else goes down": `modules/nsot/blast_radius.radius` builds a graph from committed intent's
IPv4 subnets and this host's own addresses, and returns every device reachable with a device
present and unreachable without it (gate 6 of `modules/nsot/reload_op.py`). Two places use the
same reasoning:

- **On the manager:** when a kit's heartbeat stops, every row its last report held goes stale
  together. They fold into one Needs attention row: what is wrong ("node 7 not heard from since
  <time>"), the action ("check the kit's link; the kit's own operator can still work"), and how it
  clears (the next heartbeat), as CLAUDE.md's Needs attention rule requires. The kit's devices are
  never polled from headquarters, so there is nothing per device to suppress there.
- **On a kit, or any instance with remote sites:** when the reachability reader
  (`modules/readers/reachability.py`, consecutive misses against a threshold, one miss never
  "offline") finds a device unanswering, the rows of every device in its blast radius fold under
  it, named as consequences rather than separate faults.

`blast_radius` states its own limits, and they matter here: "a device with no committed intent is
no node", routing may not follow every link, and a switch carrying a subnet at layer 2 with no
address in it is not seen. **A firewall whose intent Mercury does not model (section 13.5) is no
node, so everything behind it reads `unknown`, never "none".** Folding must use `unknown` as
"cannot say", never as "independent". The measurement owed: a kit's committed intent run through
`radius` for each of its three devices, compared with the outage actually observed when each is
restarted.

### 13.3 Device-side rollback

**Today's rollback is controller-side.** `pipeline._stage_rollback` builds an undo program from
the run's own pre-change copy (`_pre_change`, `nsot/deploy.rollback_commands`) and sends it
through config mode (`_restore_config`, `send_config_set`, merge). Deploys are merge-only, and
`modules/nsot/deploy.py` says "``configure replace`` is a documented future option, not built".
One device-side property exists already: since C501 the push does not save, and
`pipeline._stage_save_startup` writes running to startup only after verify passed, so until then
the device's startup still holds its configuration from before the change.

On a kit, the controller is on the kit's LAN, so a normal or emergency change's rollback never
crosses the satellite (section 6). A device-side rollback is still needed where the controller
could lose the device mid-change: a change to the path the instance reaches the device on, and
any instance reaching remote sites over a link that can drop (SITES_DESIGN.md). Two device-side
forms on IOS-XE, each to be measured on the platform before it is relied on:

- **`configure replace <file> time <minutes>`**, with the archive feature: the device reverts
  unless the controller sends `configure confirm` in time. This is a replace, not a merge, so it
  needs the exact intended file and the Mode B rules for anything it would remove
  (`modules/nsot/removal.py`);
- **a scheduled reload** (`reload in <minutes>`), cancelled after verify, which leans on C501's
  unsaved startup: coarser (an outage instead of a revert), but it needs no archive feature.

Whichever is used, the confirm timer becomes part of the program the person confirms (in the
hash and the receipt), the bound is 2.5 times the measured verify time, and a confirm that cannot
be sent in time is recorded as the device having reverted itself, verified by reading it back.

### 13.4 Polling and log volume per site

On a kit, polling and logs stay on its LAN: the reachability reader's 5 s probe
(`reachability.INTERVAL_SECONDS`), the SNMP scrape the monitoring profile generates
(`modules/prometheus_targets.py`), and syslog to the kit's own collector
(`deploy/rsyslog/10-network-devices.conf`). None of it crosses the satellite. What does is the
upward traffic (section 5) and the instance's own readers that reach the remote: the publication
reader's `ls-remote` every 120 s (section 8), and the CI verdict reader's requests every 900 s
(`ci_verdict.INTERVAL_SECONDS`; offline, OFFLINE_OPERATION.md replaces it). So the budget per site
is a budget for summaries, heartbeats and bounded pulls: each with an interval set from the
link's measured cost, and a bytes-per-hour figure per site shown on the Subordinate nodes page.
Sampled flow export is FLOWS_DESIGN.md's.

### 13.5 PAN-OS as a new platform

The kit's firewall is a Palo Alto device. Mercury knows two config dialects today, and refuses
any other by name (C452: there is no default dialect).

**Where platforms are keyed in the code:**

- `modules/nsot/platform.py`: `DIALECTS = frozenset({"cisco_ios", "cisco_iosxe"})`,
  `_DERIVED_FROM_DEVICE_TYPE` (five Cisco Netmiko drivers), `_FROM_NETBOX_SLUG`,
  `platform_for_device`, `require_platform` (raising `UnknownPlatform`) and
  `netmiko_type_for_dialect`;
- `modules/platform_maps.py`: the `platform_map` setting edited on Settings › Installation ›
  Platforms and roles, with `TRANSPORTS = ("ssh", "netconf")`;
- `modules/nsot/parsers/`: one parser per dialect (`cisco_ios.py`, `cisco_iosxe.py`);
- `tests/test_platform_keying.py`: the exact inventory of platform literals, and which keying
  each means;
- `modules/pipeline.py`: `IOS_ERROR_PATTERN`, `_push_via_netconf` and `_push_via_netmiko`, and the
  snapshot reads (`_ROUTING_READS`, `_INTERFACES_READ`), all IOS commands;
- `modules/readonly_commands.py`: an allowlist of IOS verbs and output modifiers;
- `modules/nsot/remote.SECRET_SHAPES` and `modules/redact.py`'s `_POSITIONAL`: IOS secret shapes,
  so a PAN-OS golden's secrets would be neither counted by the publication gate nor masked by
  position;
- `modules/host_keys.py`: SSH host keys only; an HTTPS API needs a pinned TLS certificate record
  of its own, under the same deliberate-trust rules.

**PAN-OS's model, and what it changes.** PAN-OS edits a candidate configuration and makes it
running only on a commit, which runs as an asynchronous job; its XML API (and a REST API for
policies and objects) is the programmatic path, authenticated by an API key generated from a
username and password, and configuration and commit locks exist. That maps onto Mercury's
lifecycle more naturally than IOS does: the preview is the candidate's difference from running,
the apply is the edit plus a commit, and a failed verify reverts by loading the previous running
configuration and committing again. Each step is a measurement owed on a real PAN-OS version
before design detail is written: the API's exact difference output, the commit job's states and
timings, whether a commit-confirm timer exists on the deployed version (no such timer is assumed
here), and how a partial or failed commit reports. The API key is a credential, stored and
rotated as device credentials are, never printed. Merge-only and Mode B carry over: a PAN-OS
`delete` is a removal, selected unit by unit with a reason.

## 14. The fleet, at headquarters

The earlier request's item 6 (a read-only All-networks scope) is SITES_DESIGN.md's for one
instance. At fleet level the same rule holds, read across and write within: the manager's fleet
overview and merged Needs attention (with a node column, building on C493) are drawn from the
subordinates' reports (section 5.1); a query across kits (Show commands, for instance) is sent to
each kit and run there with that kit's own credential, the manager never holding one; and every
change goes to exactly one kit's instance, through section 6.

## What it touches

- **Repository and publication:** `modules/nsot/archive.py` (catch-up through the same push
  path), `modules/nsot/remote.py` (a provider in `remote.json`, provider-specific checks replacing
  the GitHub-only `check_private` and `check_key_scope` for other servers, a per-kit branch),
  `modules/readers/remote_publication.py` (the expected-offline state beside
  `UNPUSHED_DANGER_S`), `modules/nsot/hooks.py` (unchanged contract).
- **Identity and records:** `modules/identity.py` and every place in section 10.1's table, through
  OFFLINE_OPERATION.md's verifier; `modules/nsot/repo.py`'s `Actor-Verified:` vocabulary for a
  manager's change; `modules/nsot/receipts.py` and `modules/records_db.py` for change records that
  cross the link.
- **New:** the upstream connection (subordinate) and the subordinate registry (manager), each a
  module with one owner; an Upstream manager integration in `modules/integrations/REGISTRY`; a
  card in `modules/installation_settings.CARDS`; a fifth strip state in `templates/v2/_strip.html`;
  the Subordinate nodes page (mockup and sign-off first); the reduced operator mode; signed
  playbooks and their verifier; the classification marking and its export check at each "app"
  path of section 9.3.
- **Operations:** `modules/pipeline.py` (a device-side rollback timer in the program),
  `modules/nsot/deploy.py` (`configure replace` built, under the Mode B rules),
  `modules/nsot/blast_radius.py` (reused for folding rows), `modules/attention.py` (the folded
  rows), `modules/readers/reachability.py`.
- **Platforms:** every file in section 13.5's list, for PAN-OS.
- **Settings and docs:** new settings in `modules/settings_schema.py` and docs/SETTINGS.md; the
  manual pages for each new screen and operation (`docs/manual/`). docs/MERCURY_CHARTER.md's
  sources-of-truth table was amended by the operator on 2026-10-16: intent is owned by the
  network's git repository, its remote chosen by the deploying team (GitHub in the lab, an
  internal server for kits).

## Tests it needs

- Catch-up pushes only with no hold, through `publish_lock`, with back-off; a held commit is never
  sent by catch-up; a planted held commit proves it.
- Expected-offline: `ahead` with the link known down is information at any age; with the link up
  and the push refused it is red; a network with no upstream manager keeps today's ten-minute red
  exactly (the lab's behaviour pinned).
- Provider checks: a headquarters-server remote verifies with no route to github.com; a GitHub
  remote keeps today's five checks byte for byte.
- The classification export check refuses each "app" path of section 9.3 for a destination outside
  the enclave, with a planted case per path and a floor on the number of paths, so a new export
  path added without the check fails.
- Upward messages: anything outside the fixed set is refused and recorded; a subordinate request
  for any manager route fails.
- Enrolment: no node is accepted before a person approves its fingerprint; revocation refuses the
  next handshake; a wipe is queued and runs on reconnect only.
- Safety refusals: a held device, a bring-up and a link-cutting change each queue a manager's
  change with its reason; a preference never does.
- Folding: a device's blast-radius rows fold under it; an `unknown` radius never suppresses a row.
- Device-side rollback: the timer is in the confirmed hash; a missed confirm is recorded as a
  device-side revert after a read-back.
- PAN-OS: added to `tests/test_platform_keying.py`'s inventory; its secret shapes counted by the
  publication scan and masked by `redact`; fixtures from real captures (CLAUDE.md, "Fixtures are
  real captures"), never typed.
- Every new check shown able to fail, and every new screen clicked in a real browser
  (`tests/test_manual.py`, `tests/test_v2_layout_in_a_browser.py`).

## What it must not break

- **The local repository stays the system of record:** no hook blocks or rolls back a commit; no
  force-push, ever; the acknowledgement gate decides before any push, automatic or not.
- **A network with a GitHub remote and a reliable link behaves exactly as now**, the lab included.
- **One operation per device, refused by name, never queued** (`modules/nsot/device_ops.py`): a
  queued manager's request is a separate thing and never holds a device.
- **What is confirmed is what is sent**, re-rendered and compared on the kit for a normal change.
- **Merge-only and Mode B**: `configure replace` and PAN-OS deletes enter only through the removal
  rules.
- **Secrets masked on the way out, and no credential printed**: an API key, a TOTP seed and a
  provider value stay secrets everywhere.
- **The headquarters manager never connects to a kit's devices and never holds their
  credentials.**
- **A single-network instance with no manager** shows nothing new: no Upstream manager card unless
  configured, and no fifth strip state.

## Measurements still owed

None is taken now. Each names its method and where it runs.

1. **The satellite link's RTT and loss over a day**, and git's `ls-remote` and a typical push over
   it: timed from a kit (or a link emulator set to 500 to 800 ms and the measured loss) to the
   headquarters git server; sets section 13.1's bounds.
2. **Bytes per hour of the upward traffic** (heartbeats, summaries, change records) for one kit at
   steady state and after a week offline: counted on the kit's upstream interface in a staging run.
3. **What each headquarters git server type can prove** (anonymous-read refusal, SSH greeting, key
   scope): one probe per server type (Gitea, Forgejo, GitLab) in a headquarters test environment.
4. **The kit's hardware sizing for a full instance** (Mercury, NetBox, the records database, the
   monitoring stack, Keycloak), and with the Phase 8 local model beside it: memory, CPU and disk
   at idle and during a deploy, on candidate kit hardware.
5. **Blast radius against reality:** `blast_radius.radius` for each of a kit's three devices,
   compared with the outage observed when each is restarted, on a lab kit.
6. **IOS-XE device-side rollback:** `configure replace … time` and `reload in` on a C8000v, the
   revert's timing and what it leaves, on r2 (never s3, never in 08:30 to 09:10 UTC).
7. **PAN-OS's API and commit model** on the deployed version: the difference output, commit job
   states and timings, commit-confirm availability, failed-commit reporting; on a licensed lab
   firewall image.
8. **Clock drift of a kit with no GPS fix** over the longest expected offline period, against
   TOTP's and the CRL grace period's tolerances: on candidate kit hardware.
9. **Upgrade skew:** a manager one release ahead reading a kit's reports, in a two-instance
   staging setup.

## Dependencies on the other four notes

And on the sixth, which joined the batch on the same day.

- **SITES_DESIGN.md (before this note):** multi-site within one instance, the All-networks scope's
  read-across, write-within rule (section 14), per-site time limits and device-side rollback for
  an instance reaching remote sites (sections 13.1, 13.3), and the site label the summaries carry.
- **FLOWS_DESIGN.md (before this note):** the flow store each kit keeps locally, sampled export at
  satellite sites, and the bounded pull of section 5.2.
- **IPAM_IMPORT_DESIGN.md (before this note):** kit staging at headquarters, the signed mapping
  profiles in the build standard (section 4), and the staged plan the node identity scopes.
- **BRINGUP_FROM_DOCUMENTS.md (after this note; it needs this one):** the node-scoped extraction
  reads section 3's signed identity; its proposed change is a standard or emergency change
  (section 6); the modem checklist is section 12's step.
- **OFFLINE_OPERATION.md (beside this note):** local authentication (section 10.1), signature
  format (10.2), updates and packages with no internet, the CI verdict's replacement (section
  13.4), and the product's reachability documentation (section 7.2).
