# deploy/topology/ (retired)

This folder held the topology service's renderer, `nmas-topology.py`, installed on the host
as `/usr/local/bin/nmas-topology.py` and run by `nmas-topology.service`. OBSERVE › Topology,
over Mercury's own `topology-graph` reader, replaced it, and the renderer left the repository
at 7.8 (2026-10-12). The host step `scripts/host-steps/topology-service-removal.sh` removes
the unit and the link; the Update page's `topology-renderer-gone` check reads done once both
are gone (docs/CUTOVER.md, "The topology service itself").

The folder stays only while CLAUDE.md's host-step rule names `deploy/topology/` among the
host-installed paths. Once that rule's list drops it, this file, the folder's entry in
`scripts/nmas-host-step-check` (`HOST_STEP_PATHS`, `STEP_CHECKS`) and the retired registry
entry in `modules/host_helpers.py` go together.
