# The container harness's recordings

Real Ryu 4.34 reading real Open vSwitch, in the container harness (tests/containers/compose.yml,
`scripts/nmas-harness`): none of it is typed.

| File | How it was made | What is real, what was chosen |
|---|---|---|
| `ovs-userspace-ryu-4.34-py3.5.json` | `scripts/nmas-harness record --python 3.5 --out tests/fixtures/sdn/harness/ovs-userspace-ryu-4.34-py3.5.json`, 2026-11-07 ~04:16 UTC on the development laptop: Ryu 4.34 on Python 3.5.10 (python:3.5-slim, tests/containers/ryu/constraints-3.5.txt) with `ofctl_rest`, `rest_topology` and the harness's 1.0-and-1.3 pin, reading Ubuntu 24.04's Open vSwitch 3.3.9 on its userspace datapath (two bridges, datapath ids 3 and 4, tests/containers/ovs/bridges.conf), through `tests/containers/record_answers.py` in the runner. Each answer's status and body text as Ryu sent it, keyed by path. | All of it is Ryu's and OVS's, but for **one edit, stated in the file's `_edit`**: `/stats/tablefeatures/3` keeps the first two and the last of OVS's 254 tables (13 MB a switch whole; the others differ only by their id and their NEXT_TABLES), re-serialised by `json.dumps`. The bridges, their port names and numbers, and the port held down are the harness's choice; the dummy ports' addresses (aa:55:aa:55:00:xx) are OVS's, and each bridge's own port's is random per run. |

Read by `tests/fixtures/sdn/ryu_recorded.py` (`RecordedRyu(HARNESS)`), so the tests run
Mercury's real Ryu driver on these answers with no socket: `tests/test_sdn_port_health.py` (T9)
and `tests/test_sdn_table_placement.py` (T10).

**To make it again,** the same command; the harness's images build from
tests/containers/ (network access is needed once, to pull the base images and Ryu's packages).
**Still to make, at the lab:** the ProCurve's own `tablefeatures` answer (the design's section
9); until it is a fixture, the ProCurve's tables are its platform profile's
(`modules/platforms/profiles/aruba_os_switch.yml`, C2601).
