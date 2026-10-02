# Needs attention

The landing page answers one question: does anything need you?

## What it shows {#what-it-shows}

- **When nothing is wrong**, one line says so, and what was checked is one level down, each
  source with the age of its value.
- **When something is wrong**, one row per thing, worst first: what it is, which devices,
  since when, the cause, and the ONE action that deals with it. A source that did not answer,
  or whose value is older than it promised, is itself a row.
- **Recent changes**: the last deploys and restores, from their receipts.

## Where the rows come from {#sources}

Background readers keep each source's value: job health (the host's scheduled checks), drift,
approvals, pending onboardings, rollback blocks, Grafana's alerts (a device's heartbeat
stopping is one), Oxidized freshness, integrations, reachability, routing adjacencies,
baselines, the remote's publication, the lab's startup files and the app's own version. A
reader that finishes announces it, and the page redraws in place.
