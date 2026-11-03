# Third-party development tools and their licences

**The rule (the operator's standing decision, 2026-11-03, clarified the same day).**
- **Approved whatever their licence, copyleft included:** OS packages, and development-only
  tools that are never shipped with Mercury or its release. Examples are act, its runner images,
  linters, test tools, and Firefox and geckodriver for the browser tests. Each is recorded here
  with its licence.
- **The copyleft clause covers only what is shipped.** Anything shipped in Mercury or its release
  (those are `docs/THIRD_PARTY.json`'s, and the manual's Third-party page) comes to the
  operator, as does any copyleft licence (GPL, LGPL, AGPL, SSPL, MPL) on anything shipped.

| Tool | Used for | Licence | Shipped? | How approved |
|---|---|---|---|---|
| act (nektos/act) | running `.github/workflows/*.yml` locally (workstream 0, local CI) | to be read from its own release in the compatibility survey | no | approved by the rule (dev-only) |
| act's runner image(s) | the containers act runs the jobs in, and the derived image with Firefox and geckodriver (the operator's answer 2 for local CI) | to be read per image and its base packages | no | approved by the rule (dev-only; the image's GPL OS packages included) |
| Firefox and geckodriver | the browser tests | MPL 2.0 | no | approved by the rule (dev-only), 2026-11-03 |

**Already in use, to be listed by a survey** (each tool's licence read from its own package
metadata, never from memory):
- the test tools pytest, pytest-xdist, coverage and mutmut;
- uv, which compiles requirements.lock;
- the browser tests' Selenium.
