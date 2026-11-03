# Tool (e), fakes: the repository (2026-11-03)

**The run:** `scripts/nmas-test-audit-fakes --out raw.tsv --inventory inventory.tsv`, 2026-11-03
09:41 UTC (03:41 at UTC−6), in CI's interpreter (3.12.3), on the checkout at `ec8a7cf8` with
uncommitted edits by other writers in the tree.

**What it lists:** fakes, and what differs between each compared fake and its recording. It
classifies nothing: whether a fake, or a difference, matters is the independent reviewer's call.

**The canary passed first** (`canary.md`): 5 of 5 plants with the state expected, the 2 planted
differences listed and no other.

**The rows:**
- `raw.tsv`: each difference;
- `inventory.tsv`: each fake's row (where it is, how it was found, the service and why, what it
  stands for, what uses it).

**Parsed:** 887 files under `tests/`, none failing to parse.

**Fakes found:** 111.
- **By name:** 82, whose name holds fake, stub or dummy.
- **By the fake-module rule:** 29, every top-level class and public function of
  `tests/console_fakes.py`, `tests/fake_netbox.py`, `tests/oob_fake_steps.py`,
  `tests/sdn_fakes.py` and `tests/fixtures/fake_geckodriver.py`.

## The inventory by state

| State | Fakes |
|---|---:|
| built from recording | 18 |
| recorded | 30 |
| no recording | 63 |
| all | 111 |

| Service (as the tool named it) | built from recording | recorded | no recording |
|---|---:|---:|---:|
| Ryu controller REST (ofctl_rest) | 2 | 11 | 0 |
| device CLI over SSH (Netmiko) | 0 | 6 | 0 |
| console server | 0 | 6 | 0 |
| Kea Control Agent | 3 | 3 | 0 |
| Loki HTTP API | 5 | 0 | 0 |
| Prometheus HTTP API | 3 | 0 | 0 |
| Grafana HTTP API | 2 | 0 | 0 |
| NetBox REST API | 1 | 1 | 0 |
| Proxmox VE API | 0 | 1 | 0 |
| GitHub | 0 | 1 | 0 |
| mutmut | 0 | 1 | 0 |
| Anthropic API | 0 | 0 | 3 |
| PostgreSQL (psycopg) | 0 | 0 | 1 |
| geckodriver (WebDriver) | 0 | 0 | 1 |
| a recording no service folder holds (`tests/fixtures/path/cef_fleet.json`, `tests/fixtures/configs/fleet/s3.cfg`) | 2 | 0 | 0 |
| none named | 0 | 0 | 58 |

- **Anthropic API, no recording:** `FakeBatches` (tests/test_ai_batch.py), `_fake_batches`
  (tests/test_sdn_classify_cases.py) and `_FakeMessages` (tests/test_provider_redaction.py).
  - **Where it looked:** `tests/fixtures/ai_cases`, `ai_calibration` and `blind_sets`, for a
    provider's own answer (an object with `stop_reason` and `content`, or
    `processing_status`). None holds one.
  - **What those folders hold instead:** the model's recorded answers as the product parsed
    them.
- **None named (58):** no service word in the name, file or bases, and no
  `tests/fixtures/<word>` folder for a word of the name.
  - 10 are `tests/oob_fake_steps.py`'s stand-ins for product functions.
  - Most of the rest are functions nested in a test or fixture (`client._fake`, `fake_run`,
    `_stub`).
  - Each is listed in `inventory.tsv` with what it is patched over, where that was found.

## Compared

8 fakes were driven with their recordings' requests, 180 requests in all.

| Fake | Requests | Differing fields | Of which |
|---|---:|---:|---|
| `FakeNetBox` (tests/fake_netbox.py), against `netbox/console_shapes.json` | 7 | 0 | |
| `Routes` (tests/sdn_fakes.py), against the 8 Ryu captures of HTTP entries | 51 | 0 | |
| `Replay` (tests/sdn_fakes.py), the same | 51 | 9 | 9 writes (POST) raised `AssertionError`: it answers reads only |
| `FakeRyu` (tests/sdn_fakes.py), the same, seeded from each capture | 51 | 23 | see below |
| `FakeConn` (tests/test_ssh_sessions.py), against r2's 4 captures in `operational/` (its prompt is `r2#`) | 4 | 4 | each answer 2 lines, not the recorded text (21 to 34 lines) |
| `FakeConn` (tests/test_session_write_guard.py), the same | 4 | 4 | each answer 1 line, not the recorded text |
| `FakeKea` (tests/test_ztp_relayed.py), against the 6 recorded Control Agent answers in `kea/`, built with empty reservation files | 6 | 78 | see below |
| `FakeKea` (tests/test_ztp_reservations.py), the same | 6 | 80 | see below |

**Differences: 198 rows** over 6 fakes (a field differing in several answers of one recording is
one row).

**`FakeRyu`'s 23:**
- **11 raised:**
  - port stats (read in every Lab 8 capture and in `rest_with_peer.json`) and switch
    description: `AssertionError`;
  - a dpid of `abc`: `ValueError`;
  - a write to a switch it does not hold, and a write to an unknown path: `KeyError`.
- **8 content types:** `text/html` where Ryu answered `text/html; charset=UTF-8`, and
  `text/html` where Ryu answered `text/plain` to a malformed write.
- **1 status:** a malformed write, Ryu 500, the fake 200.
- **2 bodies:** Ryu's HTML 404 text and its traceback, where the fake's is empty.
- **1 type:** `GET /stats/flow/1 body.1[].match.dl_vlan`, Ryu a string, the fake an integer.

**`FakeKea` (tests/test_ztp_relayed.py), 78:**
- 71 keys of Kea's answers it does not hold (`config-get`'s `Dhcp4` settings, `hash`, and in
  the dhcp6 answer `Dhcp6`);
- 2 keys it holds that Kea's answer does not (`user-context.mercury-ztp`, and `Dhcp4` in the
  dhcp6 answer);
- 2 arrays empty where Kea's have elements (`subnet4[].option-data`, `leases`);
- 3 commands raised `AssertionError` (`version-get` for both services, `lease6-get-all`).

**`FakeKea` (tests/test_ztp_reservations.py), 80:**
- 75 keys it does not hold;
- 1 it holds that Kea's does not (`Dhcp4` in the dhcp6 answer);
- 1 array empty (`leases`);
- 3 commands raised `AssertionError`, as above.

## Recorded, not compared (22)

- **No driver (20):**
  - the six `tests/console_fakes.py` classes (socket servers);
  - seven `tests/sdn_fakes.py` members: `Clock`, `Response`, `captured`, `ryu_action`,
    `with_flows`, `ryu_switch`, `ryu_collection`;
  - `FakeSession` (tests/test_device_reload.py): it has no `send_command`;
  - `FakeProxmox` (tests/test_job_health.py): the one Proxmox recording is a token read, which
    none of its methods answers;
  - `fake_kea` (tests/test_kea_m5_helper.py), a function;
  - `FakeMutmut` (tests/test_nmas_mutation.py), inside a test;
  - `_fake_github` (tests/test_remote_setup_v2.py), a function, and the GitHub recordings are
    CI job lists;
  - the two `fake_netmiko` fixtures.
- **`Session` (tests/sdn_fakes.py):** it answers what a test hands its constructor
  (`*answers`), and the generic driver hands it nothing.
- **`test_open_ssh_floors_every_read_before_the_session_logs_in.Fake`**
  (tests/test_session_reads_wait_for_the_device.py): defined inside a function, not reachable
  without running it.

## Limits, as the tool states them

- **The inventory is by name:** a class or function whose name holds fake, stub or dummy, and a
  fake module's top-level members.
  - A stand-in named otherwise (`_Conn`, `_Resp`, a lambda handed to `monkeypatch.setattr`) is
    not seen.
  - A helper in a fake module is listed though it may stand for nothing (`ryu_action`,
    `with_flows`).
- **The service is a word list:** its name's words (and their adjacent pairs), its file's for a
  member found by the fake-module rule alone, its bases, a method name, or a
  `tests/fixtures/<word>` folder.
  - A word can name the wrong service: `Clock` in `sdn_fakes.py` is put with Ryu by its file's
    name.
  - A fake naming none is "none named".
- **"Built from recording" means its body reads a recording:** a string constant naming a
  `fixtures` folder, or a module-level name, an imported `tests.` name or an enclosing
  function's local that reaches one.
  - A fake that reads a recording for some answers and builds others is in this state too, and
    those other answers are not compared (`inventory.tsv`'s "typed literals" counts the dict
    displays each builds).
  - A parameter of an enclosing function is not followed.
- **Comparison needs a driver:**
  - **The drivers:** Ryu HTTP entries (`FakeRyu`, `Replay`, `Routes`, and any class with
    `request` constructible with no arguments); CLI text (a class with `send_command` and
    `find_prompt`); Kea (a class with `command`); and `FakeNetBox` against
    `console_shapes.json`.
  - **Not asked:** NetBox's `cables.json` and `device_records.json`; the Ryu recordings holding
    one answer and no request (`flow_stats_empty.json` and the other two empty renders); the
    device transcripts, endpoints, tier2, RIP and reload captures.
- **What is compared:**
  - status and content type, by value;
  - a JSON body, by shape: keys present and JSON types, recursively;
  - an array's elements merged, so a key in only some elements is not told apart;
  - a dict keyed by data (a dpid), read as keys;
  - a text answer, by its line count when the text differs, never printing it.

  Values are not compared.
- **A driver's seed is the tests' seed:**
  - `FakeRyu` is seeded from the capture's own reads (through the product's `flow_from_ryu`);
  - `FakeNetBox` as tests/test_console_path.py seeds it;
  - the ZTP `FakeKea`s with empty reservation files.

  A difference that comes from the seed (an empty `leases` array) is listed as any other.
- **The CLI driver picks captures by the fake's prompt** (`r2#`: r2's 4 captures) and asks each
  by a command read from the file's name.
