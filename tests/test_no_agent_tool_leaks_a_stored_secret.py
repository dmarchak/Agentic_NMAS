"""No agent tool hands the model a stored secret (C55, C56, the agent side).

Its subject left with the AI family (D15, 2026-10-14): there is no agent and no tool. The file
stays only because CLAUDE.md cites it, and CLAUDE.md is the operator's; it is deleted in the
commit after the operator's paste removes the citation. Until then it skips, saying why. The
sweep it ran is in git history at tag `pre-remove/ai-family`.
"""

import pytest

pytest.skip("the AI family left (D15): no agent tool exists; deleted once CLAUDE.md's citation "
            "is pasted away", allow_module_level=True)
