# Third-party development tools and their licences

**The rule (the operator's standing decision, 2026-11-03, clarified the same day).**
- **Approved whatever their licence, copyleft included:** OS packages, and development-only
  tools that are never shipped with Mercury or its release. Examples are act, its runner images,
  linters, test tools, and Firefox and geckodriver for the browser tests. Each is recorded here
  with its licence.
- **The copyleft clause covers only what is shipped.** Anything shipped in Mercury or its release
  (those are `docs/THIRD_PARTY.json`'s, and the manual's Third-party page) comes to the
  operator, as does any copyleft licence (GPL, LGPL, AGPL, SSPL, MPL) on anything shipped.

**Each licence is read from the tool's own release or package metadata, never from memory**, and
the row says where it was read and when.

| Tool | Used for | Licence, and where it was read | Shipped? | How approved |
|---|---|---|---|---|
| act (nektos/act) 0.2.89 | running `.github/workflows/*.yml` locally (workstream 0, local CI; docs/LOCAL_CI.md) | MIT: the LICENSE file inside the release's own `act_Linux_x86_64.tar.gz` (sha256 `0191d6f1...24c0`, which matches the release asset's published digest), read 2026-11-03 | no | approved by the rule (dev-only) |
| act's runner image, `catthehacker/ubuntu:act-24.04` (index digest `sha256:c58e2b36...ff43`, image version 20260815) | the base of the local CI runner's job image | its build files: MIT (the catthehacker/docker_images repository's LICENCE, read through GitHub's licence API, 2026-11-03). The image carries no licence label (its config's labels, read from Docker Hub). Its contents are Ubuntu 24.04's OS packages, most of them GPL or LGPL, and software installed outside dpkg, among it Node.js | no | approved by the rule (dev-only; the image's GPL OS packages included) |
| the runner image's base, Ubuntu 24.04 | the OS inside the job image | per package, each under its own licence. Measured on the laptop 2026-11-03 from the local `ubuntu:24.04` image: 92 packages installed; of the 94 copyright files in `/usr/share/doc`, 84 name the GPL or the LGPL | no | approved by the rule (OS packages) |
| Firefox 158.0.1 | the browser tests, inside the job image (deploy/local-ci/runner.Dockerfile) | MPL 2.0: its own licence page, `chrome/toolkit/content/global/license.html` in the release's `omni.ja` (Firefox's about:license), read 2026-11-03 from the release tarball whose sha256 matches Mozilla's SHA256SUMS | no | approved by the rule (dev-only) |
| geckodriver 0.37.1 | the browser tests' WebDriver, inside the job image | MPL 2.0: the mozilla/geckodriver repository's licence, read through GitHub's licence API, 2026-11-03 | no | approved by the rule (dev-only) |
| Docker's default seccomp profile (moby/profiles `seccomp/v0.1.0`, `default.json`, sha256 `01536f1d...1e28`) | the base the jobs' seccomp profile is derived from on the host (`nmas-local-ci seccomp-profile`) | Apache 2.0: the moby/profiles repository's licence, read through GitHub's licence API, 2026-11-03. The repository holds an excerpt of it as a test fixture (tests/fixtures/act/seccomp-default-excerpt.json) | no | approved by the rule (dev-only) |
| Docker Engine (Ubuntu's `docker.io` package, with `containerd` and `runc`) | running act's containers on the host | Apache 2.0, and Expat for its bundled tini: the package's `/usr/share/doc/docker.io/copyright`, read on the laptop 2026-11-03 (29.1.3-0ubuntu4.1); the host's own copy is read by the host step | no | approved by the rule (an OS package) |
| python3-yaml (Ubuntu's package) | the root-owned runner reading the workflows (standard library otherwise) | Expat (MIT): the package's `/usr/share/doc/python3-yaml/copyright`, read on the laptop 2026-11-03 (6.0.3-1build1) | no | approved by the rule (an OS package) |

**Already in use, to be listed by a survey** (each tool's licence read from its own package
metadata, never from memory):
- the test tools pytest, pytest-xdist, coverage and mutmut;
- uv, which compiles requirements.lock;
- the browser tests' Selenium.
