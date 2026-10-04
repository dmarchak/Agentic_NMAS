# Grafana alert state, captured from the lab

Read-only captures of the three endpoints the Grafana reader reads
(`modules/readers/grafana_alerts.py`), taken from the lab's Grafana on
2026-09-28T20:25:30Z by `GrafanaIntegration._get()` on the NMAS host:

| File | Endpoint |
|---|---|
| `ruler.json` | `api/ruler/grafana/api/v1/rules` (each rule's configuration: `for`, labels, queries, no-data and error states) |
| `rules_view.json` | `api/prometheus/grafana/api/v1/rules` (each rule's evaluated state, health, last evaluation, and its instances) |
| `alertmanager.json` | `api/alertmanager/grafana/api/v2/alerts` (the instances Grafana is alerting on, with fingerprint and `startsAt`) |
| `silences.json` | `api/alertmanager/grafana/api/v2/silences` (every silence, with its author, comment, start, end and matchers). Read 2026-09-30 on Grafana 13.2.0 through the same integration: **empty**. No real silence object has been captured; the tests' one is the Alertmanager v2 API's shape, provisional until the staged capture (NSOT_STAGE7_PLAN, "Staged runs") |

**The fleet was quiet at capture**: sixteen rules, every one `inactive` and
healthy, and the Alertmanager held no instance. So every firing case in the
tests is a MINIMAL EDIT of a real piece: a real rule's real instance with its
state changed, and an Alertmanager entry carrying that instance's real labels
in the Alertmanager v2 shape. The pieces are real; the arrangement is
constructed, and each test says which edit it made.

Nothing here is a secret: queries, labels, annotations and the names of the
accounts that last edited each rule. Re-capture with
`scripts/nmas-capture-grafana-alerts --out <dir>` (read-only), never by hand.

## Dashboards (`dashboards/`)

| File | What it is |
|---|---|
| `search.json`, `datasources.json` | `api/search` and the data sources, 2026-09-29 |
| `datasources_api.json` | `api/datasources`, read 2026-10-04 through `GrafanaIntegration._get()` on the NMAS host (read-only), reduced to the fields the reader reads (`uid`, `name`, `type`, `access`, `url`, `isDefault`); the secure-field booleans dropped. Its uids are `datasources.json`'s |
| `rcn-lab1-snmp.json` | the ORIGINAL device dashboard, replaced by `nmas-device` on 2026-09-30. Kept as the panel-FILTERING fixture (8 panels, 4 selecting a device); never this lab's dashboard for either role |
| `rcn-lab-overview.json` | this lab's FLEET dashboard, read 2026-10-01 through `GrafanaIntegration._get("api/dashboards/uid/rcn-lab-overview")` on the NMAS host (read-only). One edit: text panel 20's topology image named the operator's public hostname, replaced by `topology.example.invalid` |
| `nmas-device.json` | this lab's DEVICE dashboard as Grafana returns it after import (data source UIDs filled), read the same way the same day; unedited |

The roles are recorded in CLAUDE.md ("Standing facts about this lab"). A test
that asserts a role uses that role's dashboard.
