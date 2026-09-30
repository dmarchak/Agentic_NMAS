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
