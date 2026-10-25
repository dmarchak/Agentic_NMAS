"""Phase 8's AI gateway (docs/PHASE8_PLAN.md 13.2, 15.12; docs/AI_ANTHROPIC_PLAN.md 3).

Mercury's one way to a model: `gateway.ask` masks what leaves the host, checks the caps
before sending, sends through the provider's adapter, validates the answer against a strict
schema, and records the call. AI proposes; it never confirms (PHASE8_PLAN section 2).
"""
