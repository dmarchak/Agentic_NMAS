# Testing this configuration repository

This repository holds a network's **data**, not code: each device's golden configuration
(`golden/`), its intent (`host_vars/`), the templates that render intent into configuration
(`templates/`), the monitoring profile (`profiles/`) and the DHCP records (`dhcp/`). Mercury, the
tool that manages the network, writes every change here as a commit. The tests that apply to this
repository are therefore checks of the data, run by Mercury's own code.

## What runs, and when

`.github/workflows/nmas-config-check.yml` runs on every push and pull request that touches
`golden/`, `host_vars/`, `templates/`, `profiles/` or `dhcp/` (and by hand, from the Actions tab).
It checks out this repository and the **Mercury release named in `.nsot/nmas-pin`** (a public
repository and an exact commit), installs that release's pinned requirements, and runs its
`scripts/nmas-config-check` over the whole repository: the same check Mercury runs before every
commit it makes here. Mercury's own unit tests, its coverage tool and the test of this check live
in Mercury's repository (its `docs/TESTING.md`), and run in its CI; this repository needs no test
code of its own.

## What the check proves

- **YAML and schema:** every intent file parses and holds only the keys Mercury's schema knows; a
  top-level key no template reads and Mercury does not read fails (it would render nothing,
  silently).
- **Templates:** every template parses, and the bindings file is readable.
- **Render:** each device's intent renders through its template (a value the template reads and
  the intent lacks refuses the render, naming it); the render holds nothing a device's CLI cannot
  take.
- **Goldens:** each golden is one configuration, saved by Mercury's rule; how it departs from the
  intent is reported (Intent-Match), never failed, since a device can be ahead of its intent.
- **Secrets:** no plaintext secret and no password hash, by its shape, in any file but the
  goldens; nothing found is ever printed.

## The template coverage line

A whole-repository check reports **which templates some device's render reached** (each device's
template and every template it imports) and which none did:
"Templates rendered by some device: N of M; not rendered: ...". It is information, never a
failure: a template no device renders is either dead or bound to a platform no device has, and a
person decides which.

## Reading a run

The run's **job summary** says PASS or FAIL, the failure count, the device count, the
Intent-Match line and the template coverage. The full report is the run's
`nmas-config-check` artifact (`nmas-config-check.json`: every result, with its check, file and
line). A failure
names the check, the file and the line; fix the file in Mercury (or here, if Mercury is not in
use) and push again.
