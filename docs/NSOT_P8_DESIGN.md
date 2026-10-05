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
   **4b BUILT 2026-10-05, refused by PARSING rather than at run time.** A run-time refusal
   in `get_setting` would cut the 84 places across 48 test files that inject settings by
   patching it, and it sees nothing a parse cannot. `tests/test_network_settings_read_for_a_list.py`
   checks two things:
   - no global reader (`get_setting`, `get_secret`, by name, by an alias scoped to the
     function that imports it, or as an attribute) is given a literal network key outside
     the settings machinery;
   - every call with a computed key is in an exact inventory, read by hand.

   The parse found what the first survey missed. Two wrappers hid literal keys
   (`attention._setting`, `host_helpers._setting`); they are now Default-layer reads.
   `monitoring_coverage` and `profile_propose` passed `get_setting` as an injectable
   default. `fleet(ref)` and `propose(list_name)` now default to their own list, and
   `expected()` to the Default layer (step 5). The general Settings form reads the Default
   layer by name, as it writes the global file (step 7). The integration clients built for
   no list keep reading the global file, which is the Default network's layer.
5. **Readers loop lists;** caches are keyed by group identity. **5a BUILT 2026-10-05:**
   - `modules/integration_groups.py`: which network's layer supplies a group for each list
     (Default, the list's own, or none if not applicable), and the distinct configurations.
   - `reader_job`: a reader declares `per_group` and `read_for(list)`, and reads each
     configuration once:
     - Default's under its own name, through its own `read`, so a single-network
       installation is unchanged;
     - another network's as `name@id`.
     Each store has its own last good value, failing streak and liveness row.
     `read_cached_for(name, list)` gives a list its own.
   - The two Grafana readers (dashboards; alerts with the Prometheus its bands read) are per
     configuration.
   - Needs attention draws each other network's alerts as a source of its own ("Grafana
     alerts (Branch)"), its rows keyed apart, declared, cleared and acknowledged as the base
     source's.

   **5b BUILT 2026-10-05:**
   - The readers whose value is keyed by DEVICE across every list (adjacencies, restarts,
     platform facts) ask each Prometheus configuration once, through
     `integration_groups.merged`, and merge by device. Default's is asked exactly as before.
   - coverage-reporting reads per configuration (Prometheus with Loki, and that network's
     heartbeat interval). The coverage grid, which already reads its network's settings
     since 4b, reads its network's report.
   - credential-health tracks each other network's own Grafana token, by the expiry declared
     in that network's settings.

   **Left:**
   - the integrations reader (the status bar) still probes Default's clients. A per-network
     status belongs with step 7's Settings page and step 8's network-carrying pages.
   - the pages that pair a cache with Default's settings (Monitoring, a device's Monitoring
     tab and Checks) move with step 8.
6. **Grafana alerts resolved across lists** (the latent false claim). **BUILT 2026-10-05:** `attention._inventory()` reads every registered list; a labelled device of any network is found, and an address two networks reuse names both devices and decides neither (`tests/test_alerts_across_networks.py`). The list label on the rules waits for P.7.
7. **The v2 Settings page per network.** It draws each value with its origin (set here,
   inherited, not applicable, unset). This is a new screen, so it needs a mockup and the
   operator's sign-off before it is built. **A to E APPROVED 2026-10-05 (the operator).** The
   GLOBAL settings were then drawn for sign-off, F to H (canvas v41), before anything is built:
   - F: installation-wide settings, labelled as applying to every network;
   - G: Default as the base layer, each group naming who inherits it (a count, expanded for
     the names, at 20 networks). Changing a value others inherit warns first, naming them,
     and the result says which networks changed;
   - H: one navigation, a scope bar (Installation, Default, a network) with a network picker
     that leads with the networks that differ from Default.

   **7a BUILT 2026-10-05** (`routes/settings_v2.py`, `modules/settings_page.py`,
   `templates/v2/settings.html` and its fragments; `/v2/settings/network/<list>`, the sidebar's
   Settings): a network's cards on two tabs (Integrations, Network), each with its state, every
   field's origin and its three-way choice opening the switch's preview in place of the card
   (A, B, C, I, J2); the mode's banner and its previewed switch (J1); Default's cards counting
   who inherits, with own, not configured and not applicable apart (D, G); the scope bar and
   its picker, standalone networks first (H). A switch is `configure`-gated, previewed,
   confirmed against its fingerprint and recorded (section 8). The manual: Screens > Settings
   and How it works > "Inherit or stand alone" with its diagram. **Left:** Installation (F,
   still today's page, linked from the scope bar); saving one field of a group, and Default's
   change with G's warning naming who inherits it (today's page); the picker's search; board
   I's creation form (the accepted v1 gap); NetBox scope as a group (no `netbox_scope` key yet).

   **F to J APPROVED 2026-10-05 (the operator)**, as redrawn for optional inheritance
   (canvas v45; section 8): inherit or standalone per network and per group, the previewed
   switches J1 and J2, G's counts and H's mode bar. The v1 gap stands for now: a new network
   is created on today's page, starts as inheriting, and its v2 Settings offers the switch at
   once, until v2 can create networks (board I's form is built then).

   Point 4 (decided in F to H): the 12 retiring form-only settings are gone from v2, and
   today's page keeps them until cutover. The two recorded v1 exceptions (the Grafana and
   Proxmox tokens' declared expiries) are shown: Grafana's on each network's Grafana card,
   Proxmox's on Installation's Proxmox card. Their v1 fields leave at cutover.

   Boards A to D, drawn 2026-10-05 (the canvas, v38, page "P.8 Settings per network"):
   - A: a network's Integrations tab, one card per group with its origin;
   - B: making a group the network's own, as a preview, a confirm and a result;
   - C: declaring a group not applicable, and going back to inheriting, which says what is
     deleted;
   - D: Default's view, naming who inherits each group.
8. **OBSERVE carries its network in the URL;** the Grafana roles are per network; the UID-gone
   row is built. **Its screen details drawn 2026-10-05, FOR SIGN-OFF** (the canvas, v39,
   board E):
   - Monitoring names its network in the header, with a selector;
   - a device page reads its device's network;
   - a gone dashboard is a Needs attention row with its action and how it clears.

   **APPROVED with A to E. 8a BUILT 2026-10-05:** the device page and the Monitoring page
   read one network's Grafana end to end: its role settings (`device_dashboard_settings`,
   `fleet_dashboard_uid`, the link address), its configuration's stored dashboards
   (`_cached(…, list)`), and every live ask (`device_page.grafana_client(list)`, built once
   per request and passed down; the variable-values cache is keyed by network). A device
   page passes its device's list. Monitoring passes the active list until 8b carries it in
   the URL. **8a2 BUILT 2026-10-05:** a range is judged and served by its network's stores,
   `panels.Stores(live, history, why)` read together by `panels.stores(datasources, list)`.
   A PromQL range check without them is refused; only the one-hour probes build a request
   without them, since every live store keeps at least a day. The Default-layer inventory
   loses panels' two reads. **8b BUILT 2026-10-05 (boards A and B):**
   - `/v2/monitoring?list=<name>` shows that network. `list_param` has already refused a
     list nobody has. With no `list`, the page shows the active list.
   - Every link the page draws carries the network: the dashboard menu, the range, the
     panels' own requests and the live refresh.
   - The title names the network ("Monitoring · Branch"). A Network menu opens each
     network's page. A line under the toolbar says whose fleet dashboard it is and whose
     Grafana it reads ("from Default's Grafana, which Lab-3 inherits").
   - A device's Monitoring tab says the same for its device's network, with no menu.
   - A network that declared Grafana not applicable says so, never "not read yet".
   - Coverage's title names the active list it shows.

   **8c BUILT 2026-10-05 (board E, C):** the grafana-dashboards reader, for each Grafana
   configuration, checks every network that reads it:
   - it takes each configured role UID and the layer that supplies it;
   - it asks Grafana live about any UID its listing lacks (rule 11), each UID once;
   - it stores the answers.

   `attention.dashboard_roles_source` draws a warning per layer and UID. The row names the
   networks, the setting, the UID, the Grafana and where to choose another. If Grafana could
   not be asked, the row is Unknown. A stored check whose setting has since changed is not
   drawn, and the reader's own failure is job health's row.

   **Left:**
   - Coverage's `?list=`: its batch Apply writes to the list it shows, so the list must
     reach the apply and its confirm first.
   - With no `list`, the default is the installation-wide active list. The per-session
     default is R3's other half (CONCURRENCY_AUDIT), and the sidebar's network chip shows
     the active list until then.
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

## 8. Inheritance is optional (the operator, 2026-10-05; boards F to J redrawn FOR SIGN-OFF)

**The operator's notes on F to H:** the design is good, but inheritance must be OPTIONAL. A
remote site may run its own monitoring and connections entirely apart from Default's, and must
never silently pick up Default's values. Nothing below is built until the redraw is signed off.

**The model:**
- **A network chooses**, at creation and later:
  - **Inherits from Default:** today's behaviour, and the state of every network that exists.
  - **Standalone:** nothing is inherited. A value it does not set is UNSET, "not configured
    for this network", never filled from Default.
- **Each integration group chooses too:** inherit, its own, or not applicable. A remote site
  may run its own Grafana and Prometheus and share the central NetBox. The network's choice is
  only the starting default for its groups.
- **Switching is previewed, confirmed by a person and recorded**, in both directions:
  - inherit to standalone shows exactly what becomes unconfigured ("Grafana, Loki and Kea are
    inherited from Default today; after this they are not configured here");
  - standalone to inherit shows what it would pick up.
- **G's "inherited by" lists only** the networks and groups that chose to inherit.

**A gap the model leaves:** today a list is created only on today's page (v1), which may gain
no capability. Until v2 can create one, a new list starts as Inherits from Default, as now,
and its Settings page offers the choice at once. The redraw draws the v2 creation form, so the
choice is there from the first moment once it is built.

**What changes in the code already built (P.8 steps 1 to 8):**

1. **Step 1, the scopes (`modules/settings_scope.py`): no change.** The groups are already
   declared, and each network credential is already grouped with its URL. The per-group choice
   uses exactly these group names.

2. **Step 2, the store and the resolver (`modules/list_settings.py`). BUILT 2026-10-05**
   (boards F to J approved that day), as below. Two things the build added: `write()` had
   rebuilt the store with only its values and declarations, so it now keeps the mode and the
   choices; and the record is the list's `settings_record.jsonl` (0600), which keeps a removed
   value as it was stored (a secret encrypted), so going back can restore it. The group
   labels and each group's URL key are in `settings_scope.py` (`GROUP_LABELS`, `URL_KEYS`).
   - **The store** gains two optional keys:
     - `"mode": "inherit" | "standalone"` (absent means inherit, so every existing list keeps
       today's behaviour, and nothing is migrated);
     - `"groups": {"<group>": "inherit" | "own"}`, a group's explicit choice (absent means it
       follows the mode).
     `not_applicable` is unchanged; it stays the third choice for a group.
   - **`resolve()` gains a state:** `NOT_CONFIGURED = "not configured for this network"`.
     The order becomes:
     1. host-wide;
     2. Default;
     3. not applicable;
     4. set here;
     5. a group of this list's own: a key of it is set here, OR its choice is `own`, OR the
        network is standalone and the group did not choose `inherit`. Such a group's unset
        key reads its SCHEMA default, never Default's. With nothing of the group set it says
        `NOT_CONFIGURED`; with something set, today's `UNSET_HERE`. This is the same rule a
        group set here follows today: the operator's point 5;
     6. otherwise `INHERITED` (or `UNSET_EVERYWHERE`).

     A standalone network's group that chose `inherit` reads Default's, exactly as today.
   - **`secret()` needs no change of rule:** it returns Default's secret only when the origin
     is `INHERITED`, and a standalone group never is. A test holds it.
   - **New writes, each through the existing locked, atomic `write` path:**
     - `set_mode(list, mode, actor, confirm)`;
     - `set_group(list, group, choice, actor, confirm)`.
     Each is previewed (`preview_mode`, `preview_group`), confirmed by the preview's hash
     against the store as it stands at apply, and recorded: who, when, from what to what, and
     what it changed.
     Each gets its routes and their declarations (`route_gates.py`; `invalidation.py`,
     `settings`).

3. **Step 3, the integration clients:** no change. They read through `list_settings`, so a
   standalone group's client is simply not configured: no URL, so `is_configured()` is
   false.

4. **Step 4, the network-key reads:** no change. Every read already carries its list, and
   resolves as above.

5. **Step 5, readers per configuration (`modules/integration_groups.py`, `reader_job.py`).
   BUILT 2026-10-05**, as below. `integration_groups.groups()` leaves an unconfigured
   configuration out, so every reader, liveness row and fleet-wide merge skips it at once;
   `who(group)` gives board G every bucket (inherit, own, not configured, not applicable,
   standalone, unreadable) and `who_inherits(group)` its count.
   - `group_id()` returns the list's own slug for a standalone or `own` group even when
     nothing is set, never `default`. So a standalone network never shares Default's
     configuration or its store.
   - **A configuration with no URL is NOT CONFIGURED, never a failure.** Today a reader would
     try it and fail every interval, raising a job-health row. Now `reader_job` skips it and
     `read_cached_for()` answers `{"state": "not_configured"}` with the network named, as
     `not_applicable` does.
   - **New `who_inherits(group)`:** the networks whose group resolves to Default's. G's count
     and its names read only this, and standalone or own groups are listed apart.

6. **Step 6, alerts across networks:** no change. It reads every list's devices, not settings.

7. **Step 7, the Settings page (A to E approved, not built):**
   - each group card's origin chip gains "not configured for this network";
   - the card's three-way control (inherit / its own / not applicable) replaces board C's
     single "Go back to inheriting", and its preview is the new switch preview;
   - the network header carries the network's choice (boards I and J).

8. **Step 8, the OBSERVE pages (built). BUILT 2026-10-05:** the not-configured state below,
   on both pages, with the network's Settings as its link; `grafana_whose()` needed no change
   (it already names the network for its own group), and the dashboard-settings row skips an
   unconfigured configuration through `integration_groups.groups()` (step 5).
   - `device_page.grafana_whose()` returns the network's own name for a standalone network;
   - the Monitoring page and a device's tab gain a `not_configured` state, "Grafana is not
     configured for Branch-B", with Settings as its action, beside `not_applicable`;
   - `attention.dashboard_roles_source` skips a not-configured configuration.

**The tests, each shown able to fail:**
- **`tests/test_list_settings.py`:**
  - a standalone network's unset key reads its schema default, never Default's (the value
    and the secret);
  - a standalone network's group that chose `inherit` reads Default's;
  - a list with no `mode` behaves exactly as today (every existing case unchanged: the
    regression);
  - `own` with nothing set is `NOT_CONFIGURED`;
  - `not applicable` still stops the lookup.
- **The switch:**
  - `preview_mode` names exactly the groups inherited today that become unconfigured, and the
    reverse names what would be picked up, with Default's values masked;
  - a confirm whose store moved is refused naming both;
  - the record is written;
  - a viewer who may not confirm is refused.
- **`tests/test_readers_per_network.py`:**
  - a standalone network gets its own configuration, never Default's store;
  - a configuration with no URL is skipped and answers `not_configured`, with no
    job-health failure;
  - `who_inherits` excludes standalone and own groups.
- **The pages:** a standalone network's Monitoring page and a device tab say "not configured
  for this network" (`tests/test_fleet_monitoring.py`, `tests/test_readers_per_network.py`),
  and the dashboard-settings row skips it.
- **A planted control for the property itself:** a standalone network whose read is wired to
  Default's (the old fallback) must fail the value test, the secret test and the reader test.
