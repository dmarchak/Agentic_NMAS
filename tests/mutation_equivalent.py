"""Equivalent mutants: mutations no test can or should kill, each with its reason (docs/TESTING.md,
"Mutation testing"). Added to BY HAND only, after a person has read the mutant and judged it;
never by a tool. (Not a test module.)

An entry names the function, the line as it is (`was`), the line as the mutant has it (`now`),
and why the change cannot be observed. mutmut's mutant numbers move whenever the function
changes, so an entry is matched by the function and the two lines, never by a number. Several
mutants of one line with one reason are written as one `_each` call; each is still its own
entry. A logging call's arguments are never mutated at all (one rule, in
scripts/nmas_mutation.py's `classify`), so no entry here is about one."""


def _each(function: str, was: str, nows: tuple, why: str) -> list:
    return [{"function": function, "was": was, "now": now, "why": why} for now in nows]


EQUIVALENT = [
    # ── The first pass (2026-10-14), re-run serially; its real survivors are killed by
    # tests/test_dhcp_subnets.py and tests/test_hostvars_secrets.py (docs/TESTING.md).
    *_each("modules.dhcp_subnets.pool_span",
           'parts = [x.strip() for x in re.split(r"\\s*-\\s*", text or "") if x.strip()]',
           ('parts = [x.strip() for x in re.split(r"\\s*-\\s*", text or "XXXX") if x.strip()]',),
           "an empty pool's stand-in has no dash and no slash, so it reaches the same refusal, "
           "which names the text as given"),
    *_each("modules.dhcp_subnets.pool_span",
           "n = ipaddress.ip_network(parts[0], strict=False)",
           ("n = ipaddress.ip_network(parts[0], strict=None)",),
           "ipaddress tests `if strict:`, and None is as false as False"),
    *_each("modules.dhcp_subnets.pool_span",
           'raise ValueError(f"{text!r} is not a pool")', ("raise ValueError(None)",),
           "every caller (dhcp_subnets._pools_of, dhcp_discovery, readers/ztp_discovery) catches "
           "the ValueError and skips the pool; none reads its words"),
    *_each("modules.dhcp_subnets._pools_of",
           'out.append(pool_span(p.get("pool", "")))',
           ('out.append(pool_span(p.get("pool", None)))',
            'out.append(pool_span(p.get("pool", )))',
            'out.append(pool_span(p.get("pool", "XXXX")))'),
           "a pool entry with no `pool` is skipped whatever stands in for it: none of these "
           "reads as a pool, so each raises the ValueError that skips it"),
    *_each("modules.nsot.hostvars._looks_hashed",
           'text = (value or "").strip()', ('text = (value or "XXXX").strip()',),
           "an empty value's stand-in is one token with no hash prefix: False, as for ''"),
    *_each("modules.nsot.hostvars._looks_hashed",
           "parts = text.split(None, 1)",
           ("parts = text.split(None, )", "parts = text.rsplit(None, 1)",
            "parts = text.split(None, 2)"),
           "these differ only for a value of three or more tokens, and an IOS hash is one "
           "token after its type: no stored value has the shape that tells them apart"),
    # ── config_check._check_device: the first full night (2026-10-14, laptop, serial, canary
    # killed). Its real survivors that let a bad repository pass are killed by the tests under
    # "What must not PASS" in tests/test_config_check.py; the rest stay open in the record.
    *_each("modules.nsot.config_check._check_device",
           'for line in _unsendable_lines(rendered.replace(MASK, "x")):',
           ('for line in _unsendable_lines(rendered.replace(MASK, "XXxXX")):',
            'for line in _unsendable_lines(rendered.replace(MASK, "X")):'),
           "the mask's stand-in is printable either way, and the lint flags only bytes outside "
           "0x20-0x7E"),
    *_each("modules.nsot.config_check._check_device",
           'text = _read(run.repo, rel) or ""', ('text = _read(run.repo, rel) or "XXXX"',),
           "the text is read only to find the line an unread key starts on, and the stand-in "
           "for an unreadable file has no such line either: no line, as for ''"),
    *_each("modules.nsot.config_check._check_device",
           'f"({src[\'from\']}): {exc}", rel, None, device=device, files=files)',
           ('f"({src[\'from\']}): {exc}", rel, device=device, files=files)',),
           "the `None` dropped is the `line` argument, whose default is None"),
    *_each("modules.nsot.config_check._check_device",
           'else f"through the built-in {src[\'template\']} ({src.get(\'why\', \'\')})")',
           ('else f"through the built-in {src[\'template\']} ({src.get(\'why\', None)})")',
            'else f"through the built-in {src[\'template\']} ({src.get(\'why\', )})")',
            'else f"through the built-in {src[\'template\']} ({src.get(\'why\', \'XXXX\')})")'),
           "a default never read: templates_repo.render_source gives every built-in source "
           "its `why`, and this line is reached only for a built-in source"),
    *_each("modules.nsot.config_check._check_device",
           "dangerous = []", ("dangerous = None",),
           "set only when the authorisation patterns are unavailable, and read only by "
           "`if dangerous:`, where [] and None are both false"),
    *_each("modules.nsot.config_check._check_device",
           "effective = profile.effective(intent, profile_doc, platform, role) if profile_doc \\",
           ("effective = profile.effective(intent, profile_doc, platform, role) if (profile_doc) "
            "or True \\",),
           "with no profile, profile.effective returns the intent unchanged (sections_for of no "
           "document is empty): applying it or not gives the same intent"),
    # ── dhcp_exclusions.plan: the first night's preview on the laptop (2026-10-14, C770's
    # code); its real survivors are killed by tests/test_dhcp_exclusions.py's
    # TestWhatThePreviewIsAndWhatItsConfirmBinds.
    *_each("modules.dhcp_exclusions.plan",
           '"record": _unstamped(p["record"])},',
           ('"XXrecordXX": _unstamped(p["record"])},', '"RECORD": _unstamped(p["record"])},'),
           "the record is still hashed, under another key: the confirm binds the same content"),
    *_each("modules.dhcp_exclusions.plan",
           'sort_keys=True, default=str).encode("utf-8")).hexdigest()',
           ('sort_keys=False, default=str).encode("utf-8")).hexdigest()',
            'sort_keys=None, default=str).encode("utf-8")).hexdigest()',
            'default=str).encode("utf-8")).hexdigest()'),
           "key order: the preview and its confirm build the hashed dict down one code path, in "
           "one order, so both hash the same bytes"),
    *_each("modules.dhcp_exclusions.plan",
           'sort_keys=True, default=str).encode("utf-8")).hexdigest()',
           ('sort_keys=True, default=str).encode("UTF-8")).hexdigest()',),
           "the same codec by another name"),
    *_each("modules.dhcp_exclusions.plan",
           'sort_keys=True, default=str).encode("utf-8")).hexdigest()',
           ('sort_keys=True, default=None).encode("utf-8")).hexdigest()',
            'sort_keys=True, ).encode("utf-8")).hexdigest()'),
           "never called: every hashed value is JSON already (Kea's JSON, the record's strings; "
           "the one value YAML could read as a datetime, an exclusion's `at`, is left out by "
           "_unstamped)"),
    *_each("modules.dhcp_exclusions.plan",
           "_plan(list_name, s, p, kea, intent, record, D, S)",
           ("_plan(list_name, s, p, kea, None, record, D, S)",),
           "_plan never reads its `intent` argument"),
    # ── reachability.probe: the nightly run's first walk (2026-10-14), serial; its real
    # survivors (the bounds, the address, a sub-millisecond answer) are killed by
    # tests/test_reachability_reader.py's TestTheProbe.
    *_each("modules.readers.reachability.probe",
           'response = ping(ip, timeout=2, unit="ms")',
           ('response = ping(ip, timeout=2, unit="XXmsXX")',
            'response = ping(ip, timeout=2, unit="MS")',
            "response = ping(ip, timeout=2, unit=None)",
            "response = ping(ip, timeout=2, )"),
           "the answer is only tested for > 0, and a unit changes its scale, never its sign: "
           'ping3 (4.0.4) multiplies by 1000 when unit == "ms" and otherwise answers seconds'),
    *_each("modules.readers.reachability.probe",
           "if response and response > 0:", ("if response or response > 0:",),
           "ping3 answers None, False or a float >= 0: on None the mutant raises TypeError, "
           "which the except catches and falls to TCP exactly as the original does; on False, "
           "0.0 or a positive float both lines decide alike"),
    *_each("modules.readers.reachability.probe",
           "if response and response > 0:", ("if response and response >= 0:",),
           "the two differ only at response == 0, where `response and` has already decided "
           "False"),
    # ── Night #10 (2026-10-15, run 38702510441): the list registry's migration, killed by
    # tests/test_list_folder_migration.py but for these two (C824).
    *_each("modules.device._migrate_to_folder_structure",
           'current = config.get("current_list", "Default")',
           ('current = config.get("current_list", "default")',
            'current = config.get("current_list", "DEFAULT")'),
           "`current` is used only through get_list_data_dir, which resolves through list_slug, "
           "and list_slug lowercases first: every case of Default names the folder `default`"),
]
