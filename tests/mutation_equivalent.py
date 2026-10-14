"""Equivalent mutants: mutations no test can or should kill, each with its reason (docs/TESTING.md,
"Mutation testing"). Added to BY HAND only, after a person has read the mutant and judged it;
never by a tool. (Not a test module.)

An entry names the function, the line as it is (`was`), the line as the mutant has it (`now`),
and why the change cannot be observed. mutmut's mutant numbers move whenever the function
changes, so an entry is matched by the function and the two lines, never by a number."""

EQUIVALENT = [
    {"function": "modules.nsot.hostvars.assert_no_secret_values",
     "was": '"value-checked", name, MIN_CHECKABLE_SECRET)',
     "now": '"value-checked", MIN_CHECKABLE_SECRET)',
     "why": "a log.debug line's arguments: no behaviour reads a debug message (one-off pass, "
            "2026-10-14)"},
    {"function": "modules.nsot.hostvars.assert_no_secret_values",
     "was": 'log.debug("hostvars: %s is shorter than %d characters — not "',
     "now": 'log.debug("XXhostvars: %s is shorter than %d characters — not XX"',
     "why": "a log.debug line's text: no behaviour reads a debug message (one-off pass, "
            "2026-10-14)"},
]
