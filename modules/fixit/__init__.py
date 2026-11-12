"""AI troubleshooting on the incident's page (board recurring-fixes v2; MERCURY_CHARTER, "The
fix-it path"): what an incident's page remembers of the fixes tried in it.

The parts before the page (no AI call, nothing drawn):
- `incident`: the incident's own record, one document per incident holding only what no other
  store owns (each proposal, and each choice a person made: Cancel, Hand over, the save), and
  what is DERIVED from it and from the operations' own run records each time it is asked: the
  attempts, the incident's AI cost, whether a proposal repeats one that already failed, the
  list's "cancelled" state and where the fix that resolved it came from;
- `policy`: the AI troubleshooting mode (Manual by default) and the per-incident cap ($1.00),
  refusing an attempt that would pass it, naming spent and cap;
- `validate`: a proposal from any source held to the catalog (`modules/heal/catalog.py`), to
  what the incident names, to the heal guards and to committed intent, and flagged when it
  repeats a fix that already failed; code decides, a person approves;
- `proposers`: Mercury's own proposer, its diagnosis's next step as a catalog operation;
- `payload`: what a later AI call would be sent of the incident's record, every person a
  stable label;
- `handover`: the write-up for an engineer, kept as a new version each time, and its send to
  the chosen teams, the one caller of the relay here.

Nothing here calls a model, holds a device, starts a job or opens a session, and nothing in the
heal loop reads it (docs/HEAL_TO_INTENT.md section 12; tests/test_heal_analysis_never_read.py).
"""
