# Public release readiness

**A milestone AFTER Phase 7 (the operator, 2026-10-12; Phase 7's order is unchanged). Scoped,
not built: nothing here is started until Phase 7 closes.** It sits beside
[NSOT_STAGE10_PLAN.md](NSOT_STAGE10_PLAN.md) (Stage 10, a release other people can install and
use), which already governs delivery, sign-in, roles, the first-run wizard and the
lab-specifics rule (its 6.0). This document holds what that plan does not: what makes Mercury
Cisco-only and lab-shaped today, item by item, and what a public release needs instead. Where
the two overlap, Stage 10's plan governs and this one points to it.

Each section says what is specific today, what release needs, and a rough size (small: a day
or less; medium: days; large: a week or more).

---

## a. Path…: a vendor-neutral hop lookup

**Today.** Topology's Path… (board D, C693, `modules/path_trace.py`) asks each routed hop
`show ip cef <destination>` through the reads engine and parses IOS CEF output (`parse_cef`).
It reads IPv4 only, and only on Cisco IOS and IOS-XE: any other platform's hop would read as
"not understood" and stop the branch.

**Release needs.**
- **One interface:** `next_hops(device, destination) -> [{address, interface, source}]`, the
  trace's only question of a device. The trace, the owner map, the layer-2 drawing and the
  record stay as they are.
- **Adapters chosen by the device's NetBox platform** (the platform map Mercury already keeps,
  `modules/platform_maps.py`):
  - **CEF for Cisco** (today's code, moved behind the interface);
  - **a generic SNMP adapter** over IP-FORWARD-MIB (`inetCidrRouteTable`), with Mercury's own
    longest-prefix match over the table it reads: any device that answers the standard MIB;
  - **room for OpenConfig AFT over gNMI** (`/network-instances/.../afts`), where a device
    streams its forwarding table.
- **Each hop labelled with its source:** the forwarding table (CEF, AFT) or the routing table
  (IP-FORWARD-MIB is the RIB), said on the card, since a RIB answer is a claim about routing,
  not about what the hardware forwards.
- **Optional, later:** Batfish's "intended vs live path", the same question asked of the
  committed intent, drawn beside the live trace.
- IPv6 through the same interface (`show ipv6 cef`, `inetCidrRouteTable` covers both).

**Size:** medium for the interface and the SNMP adapter; gNMI and Batfish each medium again.

## b. Every other Cisco-specific assumption (a survey; nothing changed)

Surveyed 2026-10-12 by reading the code. The only config dialects are `cisco_ios` and
`cisco_iosxe` (`DIALECTS` in `modules/nsot/platform.py`); there is no generic path anywhere.
208 of 529 test files and 66 of 203 docs mention Cisco or IOS, and the operational fixtures are
IOS captures.

| Area | What is Cisco-specific today (main files) | Vendor-neutral approach | Size |
|---|---|---|---|
| CLI reads and parsers | About 40 `show` strings across about 25 modules: the pipeline's routing reads and parsers (`modules/pipeline.py`), CDP/LLDP/OSPF/BGP parsers (`modules/topology.py`), `show version`/`show inventory` and a hard-coded manufacturer "Cisco" in `modules/netbox_client.py`, restarts' `show version` regexes (`modules/restarts.py`), `| include`/`| section` filters, IOS prompts and the single trailing `end` (`modules/config_read.py`, `modules/connection.py`) | A per-platform driver holding each read and its parser behind named questions ("neighbours", "uptime and last reload", "running config"); structured sources first (OpenConfig over gNMI or NETCONF, then SNMP standard MIBs), CLI parsers (TextFSM, Genie, ttp) per vendor as the fallback | Large |
| The command policy | `modules/readonly_commands.py` encodes IOS exec grammar: `show`/`sh`, IOS ping and traceroute options, IOS pipe modifiers, IOS file systems, IOS abbreviation matching; Tier 2's commands and their measured prompts (`modules/nsot/privileged.py`); the AI's prompts say "IOS" | The policy's SHAPE (an allowlist of whole commands, each argument one token of its shape) stays; each tier becomes a per-platform table with its grammar and prompts, measured per platform like Tier 2's | Medium |
| Deploy, verify, save, rollback | `IOS_ERROR_PATTERN` (`% Invalid…`), Netmiko `send_config_set` (implicit `configure terminal` … `end`), merge-only with `no <line>` rollback, sections from IOS indentation (`modules/nsot/sections.py`), the dangerous-line patterns, `write memory` and a `show startup-config` read-back, verify's management regexes | A driver contract: push a candidate, report errors, save, read back, and roll back; on platforms with candidate configs and commit-confirmed (Junos, IOS-XR, EOS), use them, which is safer than line negation; NAPALM's `load_merge_candidate`/`commit_config`/`rollback` is the nearest existing shape | Large |
| Removal shapes and authorised lines | 23 removal shapes, the unremovable and management lists, numbered ACLs and virtual interfaces as IOS regexes (`modules/nsot/removal.py`); measurements keyed `cisco_ios`/`cisco_iosxe` (`removal_measured.json`, `platform_defaults.json`) | Removal is per platform by nature: the measured-shape approach generalises (a probe per platform, scripts/nmas-removal-probe), and platforms with a structured config (OpenConfig, a candidate diff) remove by path instead of by line | Large |
| ZTP, bootstrap, onboarding | `render_bootstrap` has only Cisco branches (`modules/nsot/bootstrap_config.py`: `ip domain name`, `crypto key generate rsa`, `username … secret`); IOS-XE AutoInstall over DHCP options 12, 66 and 67 (`modules/nsot/ztp.py`); Kea's `ciscopnp` vendor class (`modules/dhcp_discovery.py`); IOS character checks, vty checks and credential syntax in onboarding, adopt and rotation | A bootstrap template per platform (the render already refuses an unknown one); each platform's own zero-touch path (Arista ZTP, Juniper ZTP, generic DHCP option 66/67 with a per-platform file); vendor classes per platform in the discovery reader | Large |
| SNMP and telemetry | About 20 Cisco OIDs in `modules/snmp_collector.py` (CISCO-PROCESS-MIB, memory pools, trap OIDs); the exporter's `cisco_bgp_peer2` module (CISCO-BGP4-MIB) and the IP SLA job; `Cisco_IOS_XE_*` YANG metric names in History › Query, panels and the device dashboard; `TELEMETRY_PLATFORMS = ["cisco_iosxe"]` | Standard MIBs first (HOST-RESOURCES-MIB, BGP4-V2, OSPF-MIB, IF-MIB, already used for OSPF); OpenConfig paths for streamed telemetry; vendor modules only where no standard exists, chosen by platform | Medium |
| Platform identification and templates | `cisco_*` tables in about 15 modules; the default platform map (`modules/settings_schema.py`); the parsers' registry and about 60 IOS handler regexes (`modules/nsot/parsers/`); the shipped templates (`modules/nsot/templates/cisco_ios`, `cisco_iosxe`, `_common.j2`) | The platform map already decides a device's dialect from NetBox; each new platform adds a parser (config → intent), templates (intent → config) and its tables, in one registry rather than scattered `cisco_*` dicts | Large (per platform) |
| Interface names, normalisation, masking, reload | IOS interface abbreviations (`modules/nsot/ifnames.py`); IOS ephemeral lines in golden normalisation (`modules/nsot/normalize.py`, duplicated in the pipeline and drift); IOS secret patterns (`modules/redact.py`, about 12); the reload's `[confirm]` prompt and `show boot` (`modules/device_reload.py`, `reload_op.py`) | Each becomes a per-platform table in the same registry; masking adds each platform's secret grammar, and a platform without its masking table is refused before any config is shown | Medium |

**Recommended order:** the registry and driver contract first (one place a platform plugs
in), then a second platform end to end (Arista EOS is the nearest: CLI-shaped, with eAPI and
OpenConfig), only then the long tail.

## c. Packaging

**Today.** One install: a host virtual environment (`/opt/mercury-venv`) built from
`requirements.lock`, systemd units rendered from `deploy/systemd/` by
`scripts/nmas-render-units`, updates through `scripts/nmas-deploy` and the root-owned updater
in `deploy/update/`, and psycopg's `libpq` from the host's apt package (`python3-psycopg`).

**Release needs** (Stage 10's section 1 is the design; these are the gaps):
- **A container image as the main release form:** Python 3.12, the locked libraries
  (`requirements.lock`, hash-checked), `libpq` from the base image's packages (psycopg loads
  it), no build tools; the web, worker and ZTP responder as one image with three commands.
- **The venv install for bare metal**, kept: the same lock, `libpq` from the distribution,
  the systemd units rendered as today. One lock serves both.
- What ties today's install to this host: the venv path, the unit names, the updater's
  root-owned layout and `data/lab_hosts.json` (read by the unit renderer); each becomes a
  setting or a default in the image.

**Size:** medium (Stage 10 section 1 already sizes the image, the Compose file and the
install script).

## d. Licensing for distribution

**Today** (`docs/THIRD_PARTY.json`, held to the repository by
`tests/test_third_party_inventory.py`): 77 Python packages, mostly MIT (35), BSD (22) and
Apache-2.0 (13); copyleft ones are psycopg (LGPL-3.0-only), paramiko and scp (LGPL-2.1-or-later),
bidict and certifi (MPL-2.0); 13 vendored entries: the front-end libraries (MIT, 0BSD,
Apache-2.0 OR MIT), the IBM Plex fonts (OFL-1.1) and the generated SNMP modules. The LGPL decisions rest on "used unmodified, installed
separately" and, for psycopg, on **"Mercury is not distributed"**: a public release ends that.

**Release needs:**
- **The image's notices:** every bundled package's licence file in the image (pip installs
  them; the build collects them into one `THIRD_PARTY` directory and a generated
  `THIRD_PARTY.md` from `THIRD_PARTY.json`), the IBM Plex fonts' OFL text, Apache NOTICE files
  where a package has one.
- **LGPL (psycopg, paramiko, scp):** shipped unmodified as installed packages, replaceable in
  the image (a user can install another version into the same environment); state that, and
  offer their source (a written offer, or the exact upstream release archives published beside
  the image). Re-decide psycopg's entry, whose reasoning was "not distributed".
- **MPL-2.0 (bidict, certifi):** file-level; unmodified, so only the notice and a pointer to
  the source.
- **What the image adds beyond Python:** `libpq` (the PostgreSQL licence), the base image's
  own packages (their licence files ship with them), and anything bundled by Stage 10's
  Compose profiles under their own images.
- **The generated SNMP modules** (`deploy/snmp_exporter/routing-modules.yml`, recorded as
  LicenseRef-MIB-derived): they carry the MIBs' DESCRIPTION text; decide keep (IETF Trust BSD
  terms; Cisco's MIB terms read) or regenerate without help text.
- **Not part of this:** packages the lab alone uses (the lab hosts' dhcpcd, BSD-2-Clause,
  approved 2026-10-12 as a lab-image package) are not Mercury's dependencies.

**Size:** small to medium (mostly the image build's notice step and one review).

## e. Lab-shaped rows already registered, moved here

The register keeps each row (its *Count* is the one statement of what is open); each listed
here has its "When" set to this milestone, so it is found in one place.

| Row | What is lab-shaped |
|---|---|
| C336 | Names the lab-specifics check cannot see: the break-glass download named `rcn-breakglass-…`, job health's commands naming the lab |
| C13 | Syslog names a device only through the NMAS host's hand-kept `/etc/hosts` |

Listed here for the release check but **kept in their phases**, because each is a defect on
this installation too, and moving them would defer a fix the operator placed earlier:

| Row | Kept in | Why it matters for release |
|---|---|---|
| C663 | Now | The product's lab knowledge (the Lab settings group, the startup sync, lab-startup rows): the release must hold none of it (Stage 10's 6.0) |
| C329 | Phase 3 | The drift check reads only the selected network: a single-network assumption |
| C396 | Phase 2 | Restore's apply derives its list: a write path that must carry its network |
| C333 | Phase 3 | A rotation's persist chain still needs the lab's target |

**Hard-coded lab addresses:** none known in the product. `tests/test_no_ip_literals.py` keeps
IPv4 literals out of `modules/nsot/`, `modules/integrations/` and `routes/`, and
`tests/test_nothing_personal_is_published.py` holds the publication denylist; the release adds
`modules/` and `scripts/` outside the lab tooling to the literal check.

**Size:** each row its own; the literal check's widening is small.

---

## f. Device-login two-factor authentication (a release feature; not started)

The operator, 2026-10-12: registered here, not built now. Today a person and Mercury both log in
to a device with the same kind of local credential (a password Mercury holds and rotates).
Release adds a second factor for PEOPLE and keeps Mercury's own access key-based:

- **AAA with an OTP server.** Devices authenticate logins through RADIUS or TACACS+ against an
  OTP-capable server (FreeRADIUS with TOTP, privacyIDEA, or Duo's RADIUS proxy). The AAA lines
  (servers, groups, `login authentication` lists with a local fallback for when the server is
  unreachable) are rendered through the management profile like every other management line,
  previewed, confirmed and verified; a change to them is a change to the path the tool reaches a
  device on, so it carries its own repair route (docs/LESSONS.md, "changing-the-path-to-the-device").
- **A RADIUS (or TACACS+) integration card with its health** in Settings › Integrations, as the
  other integrations have: configured or not, answering or not, and a Needs attention row when
  it stops answering (devices then fall back to local accounts, which the row says).
- **People** log in with password plus OTP. **Mercury's own service account** logs in with an
  SSH key restricted to Mercury's address (no OTP: a scheduled job cannot type one), so
  rotation, verify and every read keep working unattended.
- **ZTP and first boot are unaffected:** a device boots with the bootstrap credential and
  Mercury's key; AAA arrives with the management profile's first deploy, after Verify.
- **The RADIUS shared secret** is a secret like the others: entered by a person, stored
  encrypted, masked on the way out, and rotated like any other credential (C724's schedule
  applies to it).

**Size:** large (the integration, the profile's AAA section with its fallback and repair route,
key-based service login, the secret's rotation, and a lab OTP server to prove it).

---

## g. The key that opens every stored secret, and the break-glass record's cost (not started)

The operator, 2026-10-13: registered here for after Phase 7.

- **A TPM-bound key.** Today `data/key.key` is a file the service reads at start (owner-only,
  0600), so anything that can read the service user's files, or an image of the disk, holds
  the key beside the secrets it opens. Release seals the key to the host's TPM (systemd-creds
  or tpm2-tools), unsealed for the service at start, so a copied disk or backup image does not
  open the store; the break-glass record (`modules/breakglass.py`, which escrows the key) stays
  the recovery path when the TPM or the host is lost. Until then the lab's interim is to keep the
  key off the nightly VM image (a separate virtual disk excluded from the backup), proposed
  2026-10-13.
- **The break-glass record's scrypt cost to N=2^17.** The record is an offline target, so its
  passphrase derivation should cost more than N=2^15 (about 100 ms on a laptop today):
  N=2^17 (r=8, p=1) is about four times that and 128 MiB of memory (so `maxmem` rises above
  it), still under a second. A record written at the old cost must still open: the envelope
  already records its cost (`breakglass.py`, the `scrypt` field), but the reader derives with
  the module's constant (`_SCRYPT`), so the reader changes to take the envelope's.

**Size:** medium (the TPM path with a fallback for a host without one; the scrypt change is
small, its compatibility test the main part).
