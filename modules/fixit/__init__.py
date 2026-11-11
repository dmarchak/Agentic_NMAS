"""AI troubleshooting on the incident's page (board recurring-fixes v2; MERCURY_CHARTER, "The
fix-it path"): what an incident's page remembers of the fixes tried in it.

`incident` (the first part, no AI, nothing drawn): the incident's own record, one document per
incident holding only what no other store owns (each proposal, and each choice a person made:
Cancel, Hand over, the save), and what is DERIVED from it and from the operations' own run
records each time it is asked: the attempts, the incident's AI cost, whether a proposal repeats
one that already failed, the list's "cancelled" state and where the fix that resolved it came
from. It starts nothing: no AI call, no device hold, no job, no notification.
"""
