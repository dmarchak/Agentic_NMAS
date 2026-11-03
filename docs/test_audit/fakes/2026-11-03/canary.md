# Tool (e), fakes: the canary (2026-11-03)

`scripts/nmas-test-audit-fakes --root <scratchpad>/te-canary`, CI's interpreter (3.12.3), run
2026-11-03 09:41 UTC. The canary's files are committed in `docs/test_audit/canary/fakes/`, each
stored as `<name>.txt` so pytest never collects them; `tests/test_test_audit_fakes.py` copies
them into a temporary folder under their real names and runs this same check on every run of
the suite.

The canary is a root of its own, outside the repository's tests:

- `tests/fixtures/widget/answers.json`: a planted Widget API's recording, three HTTP entries in
  the Ryu captures' shape (`method`, `path`, `request_body`, `status`, `content_type`, `body`):
  `GET /widgets/1` (200, a widget with `id`, `name`, `size` an integer and `tags` an array),
  `GET /widgets/9` (404, an `error`), `POST /widgets` (201, the created widget).
- `tests/fake_widget.py`: a fake module (its name holds `fake`) with the plants below and
  `Answer`, the HTTP answer they return. Its docstring names the recording's path, which the
  tool must not take for a fake reading it.
- `tests/test_widget_client.py`: a test file using `FakeWidget` and `FakeGadget`, so the
  inventory's "used by" has something to count.

## Plants

| Plant | What it is | Expected | Result |
|---|---|---|---|
| `FakeWidget` | answers each recorded request as the recording does, typed by hand | recorded; compared, 3 requests, no difference | recorded; compared: 3 requests, 0 differing fields |
| `FakeWidgetDrifted` | the same, but the widget read leaves out `tags` and gives `size` as a string | recorded; compared, exactly two differences: `body.tags` (array, absent) and `body.size` (integer, string) | recorded; compared: 3 requests, 2 differing fields: `GET /widgets/1 body.tags` array / absent, `GET /widgets/1 body.size` integer / string |
| `FakeGadget` | a Gadget API's stand-in; no `tests/fixtures/gadget` exists | no recording, saying where it looked | no recording; `looked: tests/fixtures/gadget` |
| `FakeWidgetReplay` | answers from the recording itself (opens `answers.json`) | built from recording, not compared | built from recording (`tests/fixtures/widget/answers.json`); not compared: answers from the recording |
| `Answer` | the module's response class, found by the fake module rule | recorded (by its file's name), no driver | recorded; not compared: no driver |

5 plants, 5 with the state expected; the two expected differences listed and no other; no
difference listed for the matching fake. `FakeWidget`'s docstring, naming the recording, did
not make it "built from recording".

## Shown able to fail

`scripts/nmas-control` runs, each in a throwaway worktree, the worktree's copy of the test
taking the canary's files from the disk (the files are new and not yet in git's index; the
committed test takes them from `tracked()`):

| Run | Break in the worktree's copy of the tool | Result |
|---|---|---|
| baseline | none | 5 passed |
| types | `diff_shapes` does not list a changed type | 2 failed: `test_the_drifted_fake_lists_exactly_its_two_fields_and_the_matching_one_none` (missed `body.size`), `test_the_output_has_its_header_rows_counts_and_no_address` (1 differing row, not 2) |
| keys | `diff_shapes` does not list a key the fake leaves out | 3 failed: the two above (missed `body.tags`), and `test_the_field_rules_on_answers_built_here` (a nested array's missing key) |
