# Third-party development tools and their licences

**The rule (the operator's standing decision, 2026-11-03).** A development-only tool that is not
shipped with Mercury or its release is approved, and recorded here with its licence, when:
- **it is permissively licensed** (MIT, BSD, Apache 2.0); or
- **it is an OS package.**

Examples are act, its runner images, linters and test tools.

**These come to the operator:**
- anything shipped in Mercury or its release (those are `docs/THIRD_PARTY.json`'s, and the
  manual's Third-party page);
- any copyleft licence (GPL, LGPL, AGPL, SSPL) on anything.

**A weak copyleft licence such as MPL 2.0 is read as copyleft** under "any copyleft licence on
anything": it is listed for the operator's decision.

| Tool | Used for | Licence | Shipped? | How approved |
|---|---|---|---|---|
| act (nektos/act) | running `.github/workflows/*.yml` locally (workstream 0, local CI) | to be confirmed in the compatibility survey | no | pending the survey |
| act's runner image(s) | the containers act runs the jobs in | to be confirmed in the survey, each image and its base | no | pending the survey |

**Already in use, to be listed by a survey** (each tool's licence read from its own package
metadata, never from memory):
- the test tools pytest, pytest-xdist, coverage and mutmut;
- uv, which compiles requirements.lock;
- the browser tests' Selenium.

**For the operator's decision under this rule:** Firefox and geckodriver, which the browser
tests use, are published under MPL 2.0, a weak copyleft licence.
