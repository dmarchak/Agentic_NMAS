# P.8 — per-network settings: the design

Written 2026-10-04 for the operator's decision (the away queue's item 6). **A design only;
nothing is built.** It builds on what P.8 already decided (NSOT_PLAN, "P.8 — Per-list
settings", 2026-09-28 and 2026-09-30: which keys are per network, the NetBox split, the four
states, group inheritance) and adds what that section did not have: a re-measured inventory,
the migration, every reader it touches, and how the OBSERVE screens and the Grafana roles
depend on it. The measurements are a read-only survey of the code at `34006be`.

## 0. The recommendation, in five lines

1. **Zero-copy migration:** today's global file IS the Default layer. A list's own store
   starts empty, so every list inherits as groups and nothing changes on the day it lands.
2. **The schema declares each key's scope and group,** and a test refuses a key without one.
   The schema becomes the one table, rather than a list in a document.
3. **A page's network is carried in its URL** (`?list=`, already validated by
   `routes/list_param.py`). It defaults to the viewer's own active list, which is
   CONCURRENCY_AUDIT R3's option A. P.8 and R3 are decided together.
4. **Integration clients are built FOR a list.** A reader that serves every list loops them,
   and a cache is keyed by the integration group's identity (one Grafana serving three
   networks is read once).
5. **Build in nine steps (section 6), in this order:** the store and resolver first, the v2
   Settings page last. The page needs a mockup and sign-off.

## 1. What moves per network (re-measured)

P.8's decision of 2026-09-28 counted 129 keys. The schema now holds 143. Re-measured, with
the decided split applied:

| Group (inherits as one) | Keys | Decided |
|---|---|---|
| Grafana connection | `grafana_url`, `grafana_token`, `grafana_token_expires`, `grafana_verify_tls` | per network |
| Grafana roles | `grafana_fleet_dashboard_uid`, `grafana_device_dashboard_uid`, `grafana_device_variable`, `grafana_device_variable_value`, `grafana_history_datasource_uid`, `metrics_live_retention_days` | per network (the last two added by C406 on 2026-10-04, declared global until this lands) |
| Prometheus | `prometheus_url`, the auth keys, `prometheus_verify_tls`, `prometheus_targets_dir` | per network |
| Loki | `loki_url`, the auth keys, `loki_verify_tls`, `loki_selector_template` | per network |
| Oxidized | `oxidized_url`, `oxidized_username`, `oxidized_password`, `oxidized_node_identity`, `oxidized_router_db` | per network |
| Kea and ZTP | `kea_url`, the auth keys, `kea_services`, `kea_verify_tls`, `kea_ztp_fragment`, `kea_dhcp4_config`, `kea_writable_subnets` (new) | per network |
| Topology service | `topology_service_url`, `_type`, `_token`, `_verify_tls` | per network (P.11 retires it) |
| Lab (containerlab) | `clab_host`, `clab_configs_dir`, `clab_launch_patch`, `clab_labs`, `clab_sync_script`, `clab_declared_unmapped` (already keyed by list inside its value) | per network |
| Monitoring profile connectors | `syslog_*` (5), `ntp_servers`, `telemetry_receiver`, `snmp_trap_host`, `snmp_exporter_config`, `snmp_exporter_auth` | per network |
| Archive | `s3_*` (7) | per network |
| Deploy tuning | `verify_settle_windows`, `deploy_max_workers`, `deploy_verify_failure_limit`, `nsot_device_tag_retention`, `nsot_config_read_timeout` | per network, each its own group of one |
| NetBox scope | `netbox_scope` (new, default derived from the list's name), `netbox_excluded_vrfs` | per network |
| Others | `tftp_server_ip`, `settings_not_applicable`, the reachability miss threshold (new key; today `return 3` in `modules/readers/reachability.py` `miss_threshold`, "THE ONE PLACE") | per network |
| **Global** | the NetBox connection (5), `platform_map`, `platform_default_netmiko_type`, `role_map`, `proxmox_*` (8), identity (`cf_access_*`, `require_*`, `service_allowed_operations`), `flask_*`, `tftp_root`, AI and agent keys, `wf_*`, git author | host-wide |

**What the survey corrected** (each its own small decision, section 7):
- **`yang_push_script` is read:** `modules/nsot/credential_rotation.py` (`_yang_push_consumer`).
  P.8 lists it as "read by nothing".
- **Twelve keys have a form and no runtime reader:** `collector_trap_enabled`,
  `collector_netflow_enabled`, `collector_syslog_enabled`, `monitoring_identity_mode`,
  `monitoring_identity_field`, `monitoring_prom_label`, `monitoring_strip_port`,
  `promql_device_up`, `promql_cpu`, `promql_interface_oper` (all only in
  `routes/settings_integrations.py`), and `grafana_embed_mode` and `prometheus_cpu_query`
  (schema only). A setting the form shows and nothing reads is a control that does nothing:
  the wrong thing looking right.
- **Promised and not in the schema:** `netbox_scope`, `kea_writable_subnets` and saved
  queries.
- **"A configured dashboard UID Grafana no longer holds is a Needs attention row":** not
  built. `uid_gone` is only a page state (`modules/device_page.py`).

## 2. The store and the resolver

- **The schema declares, per key, `scope` (`network` or `host`) and `group`** (a name shared
  by keys that inherit together). A test parses the schema and refuses a key with neither.
  The population is every declared key, with a floor at today's 143.
- **One store per list:** `data/lists/<slug>/settings.json`, written only through the
  existing write path (`write_settings`, extended with a list). It is held under
  `filestore.PathLock`, replaced by `write_atomic`, read for writing by `read_json_for_write`
  (an unreadable store refuses writes), and owner-only from creation (`config.open_secure`).
  Secrets go through the secrets store, keyed by (list, key).
- **One resolver:** `list_setting(ref, key) -> (value, origin)`, where origin is one of the
  four decided states: set here, not applicable here, inherited from Default, unset
  everywhere. The group rule lives in this function and nowhere else: setting any key of a
  group makes the whole group local.
- **`get_setting(key)` refuses a network-scoped key** once its readers are threaded (step 4).
  Until then it reads the Default layer, as today. The refusal is the property's check: a
  reader that forgot its list fails a test, not a person.
- **The five per-list files fold into the store** (`collector_config.json`, `remote.json`,
  `source.json`, `drift_state.json`'s settings part, and the manifest's lab), one per commit.
  None is folded before the store exists.

## 3. The migration: none, by construction

The global `user_settings.json` already holds today's network values, and today's network is
the Default list. So **the global file's network-scoped keys are Default's layer.** A list's
store starts empty and inherits Default as groups. On the day P.8 lands:

- nothing is copied and nothing is moved, so nothing can be lost or half-moved;
- every page and job reads the same values as the day before, because the resolver answers
  "inherited from Default" with Default's value;
- a second network sets its own groups on its own Settings page.

**What the version bump does:** it declares the scopes and seeds no values (a version bump
seeds only what it declares). `ratify()` records the change.

**Rejected:** copying Default's values into every list's store at migration. It doubles every
secret, makes a later change to Default not reach a list that never chose it, and turns
nobody-decided into somebody-decided, which is C31's distinction.

**One edge, decided by the rule already made:** Default's "deliberately none"
(`settings_not_applicable`) does not inherit. After the bump, a second list whose group
Default declared not applicable reads "unset here", and job health judges that list's guards
on its own.

## 4. Every reader it touches

From the survey (file and function; "list?" says whether the reading function already has its
list):

**Already has its list (it only switches to `list_setting`):**
- `freshness.check(list_name)` and `oxidized_fetch.request(list_name)` (the Oxidized client);
- `credential_rotation.clab_target_for(list_name, …)` and `sync_targets(list_name)`;
- `retire.plan(list_name, …)`;
- `nsot/archive.py` `s3_archive_hook(context)`, whose context carries `list_name`;
- `pipeline.py` (`ctx.list_name`): `nsot_config_read_timeout`;
- `routes/deploy.py` `_measure_unchanged(list_name, …)`.

**Its caller has the list, one level up (threading it is a signature change):**
- `monitoring_coverage._expected_columns` (from `fleet(ref)`);
- `profile_propose.connector_value` (from `propose(list_name)`);
- `device_page.device_dashboard_settings()`. The route `_monitoring_ctx(ref, dev)` holds
  `ref` and does not pass it;
- `onboard.syslog_baseline()` (from `build_plan(…, list_name)`);
- `ztp.write_reservations` and `ztp.plan_check` (from onboarding's `list_name`);
- `convergence.window_for()` (the pipeline's `ctx.list_name`);
- `repo._prune_device_tags` (from `save_golden(list_name)`);
- `oxidized_fetch.node_for()`;
- `credential_rotation`'s timeout read (from `_rotate(list_name)`).

**No list anywhere on the path (the integration client is built for one):**
- every `IntegrationClient` (`modules/integrations/base.py` reads `url_key` and
  `<name>_verify_tls` itself; `__init__` takes no list; the registry builds `cls()`): Grafana,
  Prometheus, Loki, Oxidized, Kea, topology, NetBox's monitor;
- `device_page.fleet_dashboard_uid()` and `fleet_monitoring()`;
- `panels.history_store()` and `panels.live_seconds()`;
- `device_logs.for_device(dev)`, which builds `LokiIntegration()`;
- `neighbours.for_device(ref, dev)`, which holds `ref` and uses the global Prometheus;
- `prometheus_targets.target_dir()` and its four callers;
- `netbox_client.excluded_vrfs()`;
- `nsot/deploy.py`'s `deploy_max_workers`, and `CircuitBreaker`'s `deploy_verify_failure_limit`
  (the plan carries no list; it gains one);
- `config.TFTP_SERVER_IP`, a module constant read at import. It becomes a function of a list.

**Readers that serve every list** (each loops `lists()` and asks with that list's client):
- `adjacencies`, `restarts`, `reachability`, `freshness` and `lab-startup` already loop lists,
  and only their clients change;
- `grafana-alerts`, `grafana-dashboards`, `coverage-reporting`, `platform-facts` and
  `integrations` read one global integration today. They loop the distinct integration
  groups, keyed by the group's identity (its URL and credential reference), so one Grafana
  serving three networks is read once and its value shared;
- `credential-health` reads each network's tokens.

**One output for every list, outside NMAS:**
- the ZTP responder (one fragment for every list's ZTP devices);
- Oxidized's one `router.db`;
- the Prometheus targets directory;
- the heartbeat rules.

Each becomes per network by a list label or a per-list file. That is P.7's generator work,
built on this store and not inside P.8.

**A latent false claim that P.8 removes:** Needs attention resolves each Grafana alert against
the ACTIVE list. With two lists, an alert for the other list's device would read "NOT in the
inventory". The fix: resolve across every list, and use the list label once P.7's rules carry
one.

## 5. The OBSERVE screens and the Grafana roles

**How a page knows its network today:** only implicitly, through the installation-wide active
list (`data/device_lists.json` `current_list`). No dashboard, Grafana or Loki setting reader
accepts a list. Concurrency R3 records that one person's switch moves every other person's
pages.

**Recommended:**
- **The network is carried in the URL** of every OBSERVE page:
  - `/v2/monitoring?list=<name>`, and the same for Logs, DHCP, Topology and Questions.
  - The parameter is already validated by `routes/list_param.py`. With none, the page shows
    the viewer's own active list (R3's option A, per session) and says which network it
    shows.
  - A link copied to a colleague shows the same network, because a shareable saved view
    (section 13) needs exactly that.
- **The Grafana roles are per network** (decided 2026-09-30):
  - The Monitoring page's default is that network's `grafana_fleet_dashboard_uid`.
  - A device page reads its device's list's `grafana_device_dashboard_uid` and variable. The
    route already holds `ref`, so this is one argument.
  - Both settings stay empty by default, and the page says so (CLAUDE.md, the roles table).
- **The `grafana-dashboards` cache is keyed by the Grafana group,** and each network's page
  reads the entry for its own group. Two networks on one Grafana share one read. Two
  Grafanas are two reads.
- **"A configured UID Grafana no longer holds" becomes a Needs attention row** naming the
  network, the setting and the UID. It is built with step 8, from the same cache. Today it is
  a page state only.
- **The history store (C406) is per network:** `grafana_history_datasource_uid` names a
  datasource in that network's Grafana, and `metrics_live_retention_days` is that network's
  Prometheus retention.
- **The Logs, DHCP and Topology pages are not built** (the sidebar links go to the index).
  Each is built after P.8, and each reads only its network's Loki, Kea or graph. The Questions
  page's saved views are stored per network.
- **What looks right and is wrong** (CLAUDE.md, "never let a wrong thing look like a working
  thing"): list A's Grafana panels drawn on list B's device, with every check passing. Two
  things make it visible:
  - every OBSERVE page names its network in its header, from the same value its reads used;
  - a test plants two lists with different Grafana URLs and asserts that each page's requests
    go to its own.

## 6. The build, in order

1. **Scopes in the schema,** with the test refusing an undeclared key. No behaviour changes.
   **BUILT 2026-10-04** as `modules/settings_scope.py`, beside the schema: all 143 keys with
   their scope (network, host, retiring, dead) and group. `tests/test_settings_scope.py`
   holds every declared setting to one row and keeps each network credential in a group with
   its URL. The twelve form-only keys are `retiring` until decision 3's check outside the app
   is done.
2. **The store and the resolver,** with Default as the global layer. Every reader is
   unchanged and reads the same values. **BUILT 2026-10-04** as `modules/list_settings.py`:
   - `resolve(list, key)` answers `(value, origin)`. A host-wide key is the global value.
     For the Default network, the global file is its layer. For another list, its own value,
     else Default's as inherited, except that a group set here is this list's own (its other
     keys read their schema default, never Default's), and "not applicable here" stops the
     lookup.
   - `secret()` decrypts.
   - `write()` refuses host-wide keys. Default's write goes through `write_settings`. Another
     list's write goes to `data/lists/<slug>/settings.json`, validated, locked across
     processes, replaced whole (0600), its secrets encrypted. An unreadable store refuses and
     is kept.
   - Nothing reads it yet; step 3 gives the integration clients a list.
3. **Integration clients built for a list.** Reads may derive the active list; writes carry
   theirs. **BUILT 2026-10-04:**
   - Every client takes `list_name` (`get_integration(name, list_name=…)`) and reads only
     through the base class's `_setting` and `_secret`, which resolve through `list_settings`.
   - `save_config` for a list writes that list's store.
   - `tests/test_integrations_read_for_a_list.py` parses `modules/integrations/` and refuses a
     direct `get_setting` or `get_secret` outside the base class, so a later client cannot
     read past its list.
   - No caller passes a list yet; that is step 4.
4. **Thread the list** through the "one level up" call sites, then make `get_setting` refuse
   a network key. **4a BUILT 2026-10-05:** every direct read of a network key now has one of
   two shapes.
   - **For a list it carries:** `list_settings.value(list_name, key)`. An empty list raises
     `NoListCarried`, its own type, so no `except ValueError` turns it into a fallback.
     Converted: the deploy batch (its breaker limit and worker count, carried from the route
     to `run_batch`), the pipeline's settle windows, failure capture and rollback read-back
     (through `_list_of(ctx)`), a rotation's capture and its lab target, the startup
     verifiers (whose list is now required), onboarding's syslog block, tag pruning, the S3
     archive (the commit's own network's client and keys), and the deploy's unchanged-measure.
   - **The Default network's, by name:** `list_settings.default_layer(key)`. Each call site
     is in `tests/test_network_settings_read_for_a_list.py`'s exact inventory, which only
     shrinks:
     - the one-output-for-every-list consumers (the ZTP fragment and responder, Oxidized's
       router.db and helper, the Prometheus targets directory: P.7);
     - reads paired with a client still built for no list (steps 5 and 8);
     - the SSH layer, which holds no list (C462).

   `clab_declared_unmapped` is reclassified as host-wide. It is one table keyed by list,
   written by retire; step 9 folds it. `run_sync` no longer falls back to the global script.
   **Left for 4b:** `get_setting` refusing a network key, the 16 computed-key reads (the
   Settings form, attention, identity), and the integration clients still built for no
   list.
5. **Readers loop lists;** caches are keyed by group identity.
6. **Grafana alerts resolved across lists** (the latent false claim).
7. **The v2 Settings page per network.** It draws each value with its origin (set here,
   inherited, not applicable, unset). This is a new screen, so it needs a mockup and the
   operator's sign-off before it is built.
8. **OBSERVE carries its network in the URL;** the Grafana roles are per network; the UID-gone
   row is built.
9. **Fold the five per-list files into the store,** one per commit.

**Forecast:** P.8's own estimate was 10 to 15 commits, from C104's readers and C158's write
sites, each a cross-cutting pass over one property. This plan is nine steps. Steps 3, 4 and
5 are each likely two or three commits, so 13 to 16, with about as many register rows
(7.1's rate). The forecast's basis is a finished cross-cutting pass, not a screen.

## 7. Decisions for the operator

**DECIDED 2026-10-04 (the operator), all five; build P.8 after the current queue, starting
from this document:**
1. **Default = the global file, no migration:** yes.
2. **A page's network is carried in its URL:** yes. This also decides CONCURRENCY_AUDIT R3:
   **the URL is authoritative.** The session only remembers the last network, as the default
   when a URL names none, so two tabs on two networks never collide.
3. **Retire the twelve form-only settings:** yes. First check that nothing outside the app
   reads them (scripts, host jobs, lab tooling). Record each retirement in CUTOVER.
4. **`yang_push_script` is global:** yes. It is Lab 2's NETCONF demo, so it is added to
   Stage 10's lab-tooling inventory (NSOT_STAGE10_PLAN 6.0b).
5. **Several Grafanas per network are supported, one shared Grafana is the default.**

The questions as put:

1. **The Default layer is the global file** (zero-copy migration). Recommended. The
   alternative is a copy at migration, rejected in section 3.
2. **A page's network:** carried in the URL, defaulting to the viewer's own active list.
   Recommended, decided together with R3's per-session half (option A).
3. **The twelve form-only keys:** retire them with C171's dead keys (recommended), or wire
   each to a reader. A setting that does nothing should not be drawn.
4. **`yang_push_script`:** it is read, so P.8's "read by nothing" list loses it. Decide its
   scope: it names a host script, so recommended global.
5. **One Grafana with a folder per network, or one Grafana per network:** the group rule
   supports both. Recommended: support both, document the folder case as the common
   enterprise one, and key every cache by the group's identity.

**Not decided here** (P.8's open question, unchanged): per-instance and tenant NetBox scope
(C174).
