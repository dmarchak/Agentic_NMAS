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
    # ── Night #12 (2026-10-15, run 38726986751): F3's role filter, killed by
    # tests/test_history_ask_logs.py's TestARolesDevices but for these three (C833).
    *_each("modules.history_logq._devices_of_role",
           'return sorted(d.get("hostname", "") for d in rows',
           ('return sorted(d.get("hostname", None) for d in rows',
            'return sorted(d.get("hostname", ) for d in rows',
            'return sorted(d.get("hostname", "XXXX") for d in rows'),
           "the same comprehension keeps a row only `if d.get(\"hostname\")`, so every row it "
           "keeps has a hostname and the default is never returned"),
    # ── Lab 7 (b)'s mutation sample (2026-10-17, the laptop, serial, canary killed): the
    # confirm-by-hash and one-shot binding. Its survivors that matter are killed by the tests
    # whose docstrings name "Lab 7 (b)"; these cannot be observed. A plan or preview hash is
    # compared only with one the same code computes in the same release (the NetBox tokens
    # live in one process's memory; the persist and reload hashes are recomputed at apply), so
    # a change that alters every hash alike, and decides nothing, is not a behaviour.
    *_each("modules.netbox_authz.compute_plan_hash",
           "}, sort_keys=True))",
           ("}, sort_keys=None))", "}, ))", "}, sort_keys=False))"),
           "the dict is a literal whose keys are written in one fixed order, and every dict "
           "inside it passes through `_normalize`, which rebuilds it sorted: unsorted, the "
           "text is still one function of the plan"),
    *_each("modules.netbox_authz.compute_plan_hash",
           '"kind":     kind,', ('"XXkindXX":     kind,', '"KIND":     kind,'),
           "a key's spelling is a constant of the hashed text: every plan's hash moves alike"),
    *_each("modules.netbox_authz.compute_plan_hash",
           '"endpoint": entry.get("endpoint", ""),',
           ('"XXendpointXX": entry.get("endpoint", ""),',
            '"ENDPOINT": entry.get("endpoint", ""),'),
           "a key's spelling is a constant of the hashed text: every plan's hash moves alike"),
    *_each("modules.netbox_authz.compute_plan_hash",
           '"endpoint": entry.get("endpoint", ""),',
           ('"endpoint": entry.get("endpoint", None),', '"endpoint": entry.get("endpoint", ),',
            '"endpoint": entry.get("endpoint", "XXXX"),'),
           "the stand-in for an entry with no endpoint is one constant either way, so two plans "
           "hash apart exactly when they did"),
    *_each("modules.netbox_authz.compute_plan_hash",
           '"name":     entry.get("name", ""),',
           ('"XXnameXX":     entry.get("name", ""),', '"NAME":     entry.get("name", ""),'),
           "a key's spelling is a constant of the hashed text: every plan's hash moves alike"),
    *_each("modules.netbox_authz.compute_plan_hash",
           '"name":     entry.get("name", ""),',
           ('"name":     entry.get("name", None),', '"name":     entry.get("name", ),',
            '"name":     entry.get("name", "XXXX"),'),
           "the stand-in for an entry with no name is one constant either way, so two plans "
           "hash apart exactly when they did"),
    *_each("modules.netbox_authz.compute_plan_hash",
           '"id":       _normalize(entry.get("id")),',
           ('"XXidXX":       _normalize(entry.get("id")),',
            '"ID":       _normalize(entry.get("id")),'),
           "a key's spelling is a constant of the hashed text: every plan's hash moves alike"),
    *_each("modules.netbox_authz.compute_plan_hash",
           '"payload":  _normalize(entry.get("payload") or {}),',
           ('"XXpayloadXX":  _normalize(entry.get("payload") or {}),',
            '"PAYLOAD":  _normalize(entry.get("payload") or {}),'),
           "a key's spelling is a constant of the hashed text: every plan's hash moves alike"),
    *_each("modules.netbox_authz.compute_plan_hash",
           'digest.update(item.encode("utf-8"))', ('digest.update(item.encode("UTF-8"))',),
           "codec names are case-insensitive: the same codec, the same bytes"),
    *_each("modules.netbox_authz.compute_plan_hash",
           'digest.update(b"\\x1e")', ('digest.update(b"XX\\x1eXX")', 'digest.update(b"\\x1E")'),
           "`\\x1E` is the same byte; a longer constant separates the entries as well, since "
           "each entry is JSON text, which never holds a raw 0x1e"),
    *_each("modules.netbox_authz._normalize",
           'return "<new>"', ('return "XX<new>XX"', 'return "<NEW>"'),
           "the placeholder is one constant for every synthetic id either way"),
    *_each("modules.netbox_authz.consume_token",
           "_remember(_spent, token, dict(entry, used_at=now))",
           ("_remember(_spent, token, dict(used_at=now))",),
           "a spent entry is read only by `_refusal`, for its `used_at`"),
    *_each("modules.netbox_authz.consume_token",
           'return False, _refusal(now, spent, expired), ""',
           ('return False, _refusal(now, spent, expired), "XXXX"',),
           "the plan hash of a refusal is read by nothing: `netbox_ops.authorize`, the one "
           "caller, raises on `not ok` before it reads the hash"),
    *_each("modules.netbox_authz.consume_token",
           'return False, "This confirmation was issued for a different operation.", ""',
           ('return False, "This confirmation was issued for a different operation.", "XXXX"',),
           "the plan hash of a refusal is read by nothing: `netbox_ops.authorize`, the one "
           "caller, raises on `not ok` before it reads the hash"),
    *_each("modules.netbox_authz.consume_token",
           'return False, "This confirmation was issued for a different device list.", ""',
           ('return False, "This confirmation was issued for a different device list.", '
            '"XXXX"',),
           "the plan hash of a refusal is read by nothing: `netbox_ops.authorize`, the one "
           "caller, raises on `not ok` before it reads the hash"),
    *_each("modules.netbox_authz.consume_token",
           'return True, "", entry["plan_hash"]', ('return True, "XXXX", entry["plan_hash"]',),
           "the error of a token that passed is read by nothing: `netbox_ops.authorize` reads "
           "it only when `ok` is False"),
    *_each("modules.netbox_authz.issue_token",
           "token = secrets.token_urlsafe(32)",
           ("token = secrets.token_urlsafe(None)", "token = secrets.token_urlsafe(33)"),
           "`token_urlsafe(None)` takes `secrets.DEFAULT_ENTROPY`, 32 bytes (CPython 3.12); 33 "
           "bytes is one byte MORE entropy: neither weakens the token"),
    *_each("modules.netbox_authz.issue_token",
           '"issued_at":  now,', ('"XXissued_atXX":  now,', '"ISSUED_AT":  now,'),
           "`_refusal`, the only reader, falls back to `expires_at - ttl`, the same instant"),
    *_each("modules.netbox_authz.issue_token",
           'return {"token": token, "expires_in": ttl, "plan_hash": plan_hash}',
           ('return {"token": token, "expires_in": ttl, "XXplan_hashXX": plan_hash}',
            'return {"token": token, "expires_in": ttl, "PLAN_HASH": plan_hash}'),
           "`netbox_ops.authorization_for`, the one caller, reads only `token` and "
           "`expires_in`; it computed the plan hash itself"),
    *_each("modules.netbox_authz.verify_plan_unchanged",
           'return True, ""', ('return True, "XXXX"',),
           "`netbox_ops.authorize`, the one caller, reads the error only when the plan moved"),
    *_each("modules.nsot.deploy.plan_batch",
           'fresh_hash = hashlib.sha256(fresh.encode("utf-8")).hexdigest()[:16]',
           ('fresh_hash = hashlib.sha256(fresh.encode("UTF-8")).hexdigest()[:16]',),
           "codec names are case-insensitive: the same codec, the same bytes"),
    *_each("modules.nsot.onboard.abandon_fingerprint",
           'shown = [[s.get("step", ""), bool(s.get("ok")), s.get("detail", "")]',
           ('shown = [[s.get("step", None), bool(s.get("ok")), s.get("detail", "")]',
            'shown = [[s.get("step", ), bool(s.get("ok")), s.get("detail", "")]',
            'shown = [[s.get("step", "XXXX"), bool(s.get("ok")), s.get("detail", "")]',
            'shown = [[s.get("step", ""), bool(s.get("ok")), s.get("detail", None)]',
            'shown = [[s.get("step", ""), bool(s.get("ok")), s.get("detail", )]',
            'shown = [[s.get("step", ""), bool(s.get("ok")), s.get("detail", "XXXX")]'),
           "the stand-in for a step with no name or no words is one constant either way, and "
           "the preview and the confirm compute it alike (every step `_abandon_onboarding` "
           "writes carries both)"),
    *_each("modules.nsot.onboard.abandon_fingerprint",
           'return hashlib.sha256(json.dumps([shown, bool(dry.get("ok")), dry.get("error", "")])',
           ('return hashlib.sha256(json.dumps([shown, bool(dry.get("ok")), '
            'dry.get("error", None)])',
            'return hashlib.sha256(json.dumps([shown, bool(dry.get("ok")), dry.get("error", )])',
            'return hashlib.sha256(json.dumps([shown, bool(dry.get("ok")), '
            'dry.get("error", "XXXX")])'),
           "the stand-in for a dry run with no error is one constant either way, so two dry "
           "runs fingerprint apart exactly when they did"),
    *_each("modules.nsot.persist_op.row_checks",
           '"username": row.get("username", "admin")}, sort_keys=True).encode()).hexdigest()[:16]',
           ('"username": row.get("username", "admin")}, sort_keys=None).encode())'
            '.hexdigest()[:16]',
            '"username": row.get("username", "admin")}, ).encode()).hexdigest()[:16]',
            '"username": row.get("username", "admin")}, sort_keys=False).encode())'
            '.hexdigest()[:16]'),
           "the hashed dict is a literal whose keys are written in one fixed order: unsorted, "
           "the text is still one function of the row"),
    *_each("modules.nsot.persist_op.row_checks",
           '"username": row.get("username", "admin")}, sort_keys=True).encode()).hexdigest()[:16]',
           ('"XXusernameXX": row.get("username", "admin")}, sort_keys=True).encode())'
            '.hexdigest()[:16]',
            '"USERNAME": row.get("username", "admin")}, sort_keys=True).encode())'
            '.hexdigest()[:16]',
            '"username": row.get("username", None)}, sort_keys=True).encode()).hexdigest()[:16]',
            '"username": row.get("username", )}, sort_keys=True).encode()).hexdigest()[:16]',
            '"username": row.get("username", "XXadminXX")}, sort_keys=True).encode())'
            '.hexdigest()[:16]',
            '"username": row.get("username", "ADMIN")}, sort_keys=True).encode())'
            '.hexdigest()[:16]',
            '"username": row.get("username", "admin")}, sort_keys=True).encode())'
            '.hexdigest()[:17]'),
           "a key's spelling, and the stand-in for a row with no username, are constants of "
           "the hashed text; one more hex digit is the same hash, longer: persist and Save "
           "recompute it with the same code, so every hash moves alike and none decides "
           "differently"),
    *_each("modules.nsot.persist_op.row_checks",
           '"list": list_name, "device": hostname, "ip": row.get("ip", ""),',
           ('"XXlistXX": list_name, "device": hostname, "ip": row.get("ip", ""),',
            '"LIST": list_name, "device": hostname, "ip": row.get("ip", ""),',
            '"list": list_name, "XXdeviceXX": hostname, "ip": row.get("ip", ""),',
            '"list": list_name, "DEVICE": hostname, "ip": row.get("ip", ""),',
            '"list": list_name, "device": hostname, "XXipXX": row.get("ip", ""),',
            '"list": list_name, "device": hostname, "IP": row.get("ip", ""),',
            '"list": list_name, "device": hostname, "ip": row.get("ip", None),',
            '"list": list_name, "device": hostname, "ip": row.get("ip", ),',
            '"list": list_name, "device": hostname, "ip": row.get("ip", "XXXX"),'),
           "a key's spelling, and the stand-in for a row with no address, are constants of the "
           "hashed text: every hash moves alike"),
    *_each("modules.nsot.persist_op.row_checks",
           '"device_type": row.get("device_type", ""),',
           ('"XXdevice_typeXX": row.get("device_type", ""),',
            '"DEVICE_TYPE": row.get("device_type", ""),',
            '"device_type": row.get("device_type", None),',
            '"device_type": row.get("device_type", ),',
            '"device_type": row.get("device_type", "XXXX"),'),
           "a key's spelling, and the stand-in for a row with no driver (which the plan "
           "refuses anyway), are constants of the hashed text: every hash moves alike"),
    *_each("modules.nsot.reload_op.judge",
           '"departs": departs}, sort_keys=True)',
           ('"departs": departs}, sort_keys=None)', '"departs": departs}, )',
            '"departs": departs}, sort_keys=False)', '"XXdepartsXX": departs}, sort_keys=True)',
            '"DEPARTS": departs}, sort_keys=True)'),
           "the fingerprinted dict is a literal whose keys are written in one fixed order, and "
           "a key's spelling is a constant of its text: preview and run compute it alike"),
    *_each("modules.nsot.reload_op.judge",
           'shown = json.dumps({"running": _h(running), "startup": _h(startup),',
           ('shown = json.dumps({"XXrunningXX": _h(running), "startup": _h(startup),',
            'shown = json.dumps({"RUNNING": _h(running), "startup": _h(startup),',
            'shown = json.dumps({"running": _h(running), "XXstartupXX": _h(startup),',
            'shown = json.dumps({"running": _h(running), "STARTUP": _h(startup),'),
           "a key's spelling is a constant of the fingerprinted text: preview and run compute "
           "it alike"),
    *_each("modules.nsot.reload_op.judge",
           '"image": _IMAGE.search(reads.get("version", "") or "") and',
           ('"XXimageXX": _IMAGE.search(reads.get("version", "") or "") and',
            '"IMAGE": _IMAGE.search(reads.get("version", "") or "") and',
            '"image": _IMAGE.search(reads.get("version", None) or "") and',
            '"image": _IMAGE.search(reads.get("version", ) or "") and',
            '"image": _IMAGE.search(reads.get("version", "XXXX") or "") and',
            '"image": _IMAGE.search(reads.get("version", "") or "XXXX") and'),
           "a key's spelling is a constant of the fingerprinted text; with no `show version` "
           "read, every stand-in (None, '', 'XXXX') names no image, as '' does"),
    *_each("modules.nsot.reload_op.judge",
           '"running_hash": _h(running)}',
           ('"XXrunning_hashXX": _h(running)}', '"RUNNING_HASH": _h(running)}',
            '"running_hash": _h(None)}'),
           "`running_hash` is read by nothing (no module, route or template names it); the "
           "running config is bound through the fingerprint"),
    *_each("modules.nsot.reload_op.run",
           'step("read", False, f"it could not be read: {exc}")',
           ('step("read", None, f"it could not be read: {exc}")',),
           "`step` stores `bool(ok)`, and bool(None) is False"),
    *_each("modules.nsot.reload_op.run",
           'step("read", False, f"it moved since the preview (previewed {fingerprint}, "',
           ('step("read", None, f"it moved since the preview (previewed {fingerprint}, "',),
           "`step` stores `bool(ok)`, and bool(None) is False"),
    *_each("modules.nsot.reload_op.run",
           'step("read", False, "a gate fails now: " + "; ".join(',
           ('step("read", None, "a gate fails now: " + "; ".join(',),
           "`step` stores `bool(ok)`, and bool(None) is False"),
    *_each("modules.nsot.reload_op.run",
           'step("window", False, got.get("error", "not recorded") + ": nothing was sent")',
           ('step("window", None, got.get("error", "not recorded") + ": nothing was sent")',),
           "`step` stores `bool(ok)`, and bool(None) is False"),
    *_each("modules.nsot.reload_op.run",
           'step("verify", False, f"it answers on SSH\'s port and could not be read: {exc}")',
           ('step("verify", None, f"it answers on SSH\'s port and could not be read: {exc}")',),
           "`step` stores `bool(ok)`, and bool(None) is False"),
    *_each("modules.nsot.reload_op.run",
           'step("verify", False, f"it runs something else: {len(same.get(\'only_left\') or [])} "',
           ('step("verify", None, f"it runs something else: '
            '{len(same.get(\'only_left\') or [])} "',),
           "`step` stores `bool(ok)`, and bool(None) is False"),
    # ── Lab 7 (b): masking. Its survivors that matter are killed by the tests whose
    # docstrings name "Lab 7 (b)" in tests/test_provider_redaction.py and
    # tests/test_previews_mask_secrets.py.
    *_each("modules.redact._compile",
           "ordered = sorted(values, key=len, reverse=True)",
           ("ordered = sorted(values, key=None, reverse=True)",
            "ordered = sorted(values, reverse=True)"),
           "the order matters only between two secrets one of which is a PREFIX of the other "
           "(literal alternatives can both match at one position only then), and reverse "
           "lexicographic order puts every extension before its prefix, as longest-first "
           "does; shown on the planted `!` extension, which kills the shortest-first mutants"),
    *_each("modules.redact.redact_text",
           'lambda m: PLACEHOLDER.format(label=table.get(m.group(1), "secret")), text)',
           ('lambda m: PLACEHOLDER.format(label=table.get(m.group(1), None)), text)',
            'lambda m: PLACEHOLDER.format(label=table.get(m.group(1), )), text)',
            'lambda m: PLACEHOLDER.format(label=table.get(m.group(1), "XXsecretXX")), text)',
            'lambda m: PLACEHOLDER.format(label=table.get(m.group(1), "SECRET")), text)'),
           "the pattern is the alternation of the table's own keys, escaped, so what it "
           "matched is always a key and the default label is never used"),
    # ── Lab 7 (b), the second sample (2026-10-18): the deploy gates and the credential reads.
    # Its real survivors are killed by the tests whose docstrings or comments name "Lab 7 (b),
    # the second sample" (docs/TESTING.md, each file's row).
    *_each("modules.nsot.authorisation.reason_problem",
           'reason, line = entry.get("reason") or "", entry.get("line") or ""',
           ('reason, line = entry.get("reason") or "", entry.get("line") or "XXXX"',),
           "the line's stand-in changes only the words of a refusal for an entry with no line, "
           "and the two callers that pass an empty line (attention, restarts) read only whether "
           "there is a problem; the copy test cannot fire on it, since a reason flattening to "
           "'xxxx' is one word and refused as too short either way"),
    *_each("modules.nsot.authorisation.reason_problem",
           "if _flat(reason) in (_flat(line), _flat(key(line))):",
           ("if _flat(reason) in (_flat(None), _flat(key(line))):",
            "if _flat(reason) in (_flat(line), _flat(None)):",
            "if _flat(reason) in (_flat(line), _flat(key(None))):"),
           "the two operands are one value for every caller: an authorisation's line is already "
           "its key (normalise), and the key of a key is itself (redact_positional, measured on "
           "a community, a type-9 account, an enable secret and a bare line); every other caller "
           "passes its own words, which hold no secret position, so key(line) is the line "
           "stripped, and _flat strips. Dropping either operand (None, or key(None), flattens to "
           "'', which the empty-reason test before it has already answered) leaves the other"),
    *_each("modules.nsot.deploy.assert_credentials_unchanged",
           'held = getattr(artifact, "capture_credentials", None) or {}',
           ('held = getattr(artifact, "capture_credentials", ) or {}',),
           "a default never read: the guard's two callers hand it a RenderArtifact "
           "(prepare_device), whose dataclass field defaults to {}, or a RestoreTarget, whose "
           "property always answers; neither lacks the attribute"),
    *_each("modules.nsot.deploy.assert_credentials_unchanged",
           "f\"refusing to {operation} {getattr(artifact, 'device', '?')}: it would \"",
           ("f\"refusing to {operation} {getattr(artifact, 'device', None)}: it would \"",
            "f\"refusing to {operation} {getattr(artifact, 'device', )}: it would \"",
            "f\"refusing to {operation} {getattr(artifact, 'device', 'XX?XX')}: it would \""),
           "a default never read: both callers' artifacts (RenderArtifact, RestoreTarget) "
           "carry `device` as a required field"),
    *_each("modules.nsot.authorisation.fingerprint",
           'body = {"commands": list(commands),',
           ('body = {"XXcommandsXX": list(commands),',),
           "a key's spelling is a constant of the hashed text: the preview and the apply's "
           "recompute both call this one function, so every hash moves alike"),
    # The credential reads.
    *_each("modules.credentials.resolve",
           'def resolve(mgmt_ip: str, role: str = "", site: str = "",',
           ('def resolve(mgmt_ip: str, role: str = "XXXX", site: str = "",',
            'def resolve(mgmt_ip: str, role: str = "", site: str = "XXXX",'),
           "a caller that names no role or site (adoption, onboarding) gets the step skipped by "
           "'' and, by the stand-in, a lookup of `role:XXXX` or `site:XXXX`, which finds a "
           "profile only if a person named one after the stand-in itself; no store does"),
    *_each("modules.credentials.resolve",
           'credential_list: str = "") -> dict:',
           ('credential_list: str = "XXXX") -> dict:',),
           "a caller that names no designated list gets the step skipped by '' and, by the "
           "stand-in, a read of the folder of a network named XXXX, which holds a devices.csv "
           "only if a network was named after the stand-in itself"),
    *_each("modules.credentials.resolve",
           '"password": decrypt_value(override.get("password", "")),',
           ('"password": decrypt_value(override.get("password", None)),',
            '"password": decrypt_value(override.get("password", )),',
            '"password": decrypt_value(override.get("password", "XXXX")),'),
           "a default never read: the overrides' one writer, set_device_override, writes "
           "`password` and `secret` on every override, '' when none was given"),
    *_each("modules.credentials.resolve",
           '"secret":   decrypt_value(override.get("secret", "")),',
           ('"secret":   decrypt_value(override.get("secret", None)),',
            '"secret":   decrypt_value(override.get("secret", )),',
            '"secret":   decrypt_value(override.get("secret", "XXXX")),'),
           "a default never read: the overrides' one writer, set_device_override, writes "
           "`password` and `secret` on every override, '' when none was given"),
    *_each("modules.credentials._from_profile",
           'return (p.get("username", ""),',
           ('return (p.get("username", None),', 'return (p.get("username", ),',
            'return (p.get("username", "XXXX"),'),
           "a default never read: the line before returns None for a profile with no username"),
    *_each("modules.credentials._from_profile",
           'decrypt_value(p.get("password", "")),',
           ('decrypt_value(p.get("password", None)),', 'decrypt_value(p.get("password", )),',
            'decrypt_value(p.get("password", "XXXX")),'),
           "a default never read: the profiles' one writer, save_profile, writes `password` "
           "and `secret` on every profile"),
    *_each("modules.credentials._from_profile",
           'decrypt_value(p.get("secret", "")))',
           ('decrypt_value(p.get("secret", None)))', 'decrypt_value(p.get("secret", )))',
            'decrypt_value(p.get("secret", "XXXX")))'),
           "a default never read: the profiles' one writer, save_profile, writes `password` "
           "and `secret` on every profile"),
    *_each("modules.credentials._from_credential_list",
           'with open(path, newline="", encoding="utf-8") as fh:',
           ('with open(path, newline=None, encoding="utf-8") as fh:',
            'with open(path, newline="", encoding=None) as fh:',
            'with open(path, encoding="utf-8") as fh:',
            'with open(path, newline="", ) as fh:',
            'with open(path, newline="", encoding="UTF-8") as fh:'),
           "devices.csv is ASCII with no line break inside a field (Fernet tokens are "
           "URL-safe base64; names, addresses and usernames are printable ASCII, the CLI's "
           "rule), so every codec and newline mode named reads the same rows"),
    *_each("modules.credentials._from_credential_list",
           'if (row.get("ip") or "").strip() == mgmt_ip:',
           ('if (row.get("ip") or "XXXX").strip() == mgmt_ip:',),
           "the line runs only for a non-empty mgmt_ip (the guard above), which neither '' "
           "nor 'XXXX' (no address) equals: a row with no address matches nothing either way"),
    *_each("modules.credentials._from_credential_list",
           'return (row.get("username", ""), password, secret)',
           ('return (row.get("username", None), password, secret)',
            'return (row.get("username", ), password, secret)',
            'return (row.get("username", "XXXX"), password, secret)'),
           "a default never read: csv.DictReader gives every row every column of the header, "
           "and devices.csv's header (device.py) carries username, password and secret"),
    *_each("modules.credentials.get_template_secret",
           'return decrypt_value(entry.get("value", "")) if entry else ""',
           ('return decrypt_value(entry.get("value", None)) if entry else ""',
            'return decrypt_value(entry.get("value", )) if entry else ""',
            'return decrypt_value(entry.get("value", "XXXX")) if entry else ""'),
           "a default never read: the template secrets' one writer, set_template_secret, "
           "writes `value` on every entry"),
    *_each("modules.credentials._load",
           'with open(_FILE, encoding="utf-8") as fh:',
           ('with open(_FILE, encoding=None) as fh:', 'with open(_FILE, ) as fh:',
            'with open(_FILE, encoding="UTF-8") as fh:'),
           "the store is written by _save as json.dumps with its default ensure_ascii, so "
           "every byte is ASCII and every codec named reads it alike"),
    *_each("modules.nsot.deploy.render_for_deploy",
           'template_name: str = "base.j2") -> str:',
           ('template_name: str = "XXbase.j2XX") -> str:',
            'template_name: str = "BASE.J2") -> str:'),
           "a default never read: every caller (prepare_device, routes.deploy's two, "
           "profile_apply's two, template_bring's two) passes template_name"),
    *_each("modules.nsot.deploy.render_for_deploy",
           'return (host_vars.get("secrets") or {}).get(name, "")',
           ('return (host_vars.get("secrets") or {}).get(name, None)',
            'return (host_vars.get("secrets") or {}).get(name, )'),
           "the renderer reads the lookup with `if value:` (roundtrip.render, `_secret`), and "
           "None is as false as '': a name held nowhere falls to its own backstop either way"),
    # ── Out-of-band ZTP, O1 to O3 (LAB9_PLAN.md section 8; the run of 2026-10-22, on demand,
    # serial, canary killed). Every other survivor there is killed by a test naming it.
    *_each("modules.nsot.console_profiles.check_template",
           'if "{" in PLACEHOLDER.sub("", line) or "}" in PLACEHOLDER.sub("", line):',
           ('if "{" in PLACEHOLDER.sub("XXXX", line) or "}" in PLACEHOLDER.sub("", line):',
            'if "{" in PLACEHOLDER.sub("", line) or "}" in PLACEHOLDER.sub("XXXX", line):'),
           "the placeholders are replaced only to look for a brace left over, and the stand-in "
           "holds no brace: the same lines are refused"),
    *_each("modules.nsot.console_profiles.canonical",
           'return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()',
           ('return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()',
            'return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=None).encode()',
            'return json.dumps(data, sort_keys=True, separators=(",", ":"), ).encode()'),
           "validate hashes only a profile it has accepted, and every string it accepts (each text "
           "field, pattern, command and template line printable ASCII; keys known; parameter "
           "names [a-z_]) is ASCII, so escaping non-ASCII changes no byte"),
    *_each("modules.nsot.console_profiles.load",
           'with open(path, encoding="utf-8") as fh:',
           ('with open(path, encoding=None) as fh:', 'with open(path, ) as fh:',
            'with open(path, encoding="UTF-8") as fh:'),
           "a profile that loads is ASCII throughout (validate refuses any other character in "
           "every string), and ASCII reads alike in UTF-8, its other spelling, and any "
           "ASCII-compatible locale default; a non-ASCII file is refused either way"),
    # ── Out-of-band ZTP, O2 (the transports and the driver loop; the run of 2026-10-22, on
    # demand, serial, canary killed). Every other survivor there is killed by a test naming it.
    *_each("modules.nsot.console_transport.run_plan",
           "decision = session.feed(data, now) if data else session.tick(now)",
           ("decision = session.feed(data, now) if (data) or True else session.tick(now)",),
           "an empty read fed is a tick: ConsoleSession.feed with no bytes adds no text and "
           "decides at the same time from the same state, exactly as tick does"),
    *_each("modules.nsot.console_transport.ConsoleTransport.close",
           "self._opened = False", ("self._opened = None",),
           "the flag is only ever tested for truth (`if self._opened`, `if not self._opened`), "
           "and None is as false as False"),
    *_each("modules.nsot.console_transport.RawTcp._disconnect",
           "self._chan = self._ssh = self._sock = None",
           ('self._chan = self._ssh = self._sock = ""',),
           "the three are cleared only after their values were taken to be closed, and none is "
           "read again before `_connect` sets them anew: `close` disconnects once (only while "
           "open), a failed `open` once, and `read` and `write` refuse a closed transport "
           "before asking for its pipe"),
    # ── Out-of-band ZTP, O6a (the console survey; run #16 of 2026-10-22, on demand, at
    # 6dc78592). Every other survivor there is killed by a test in tests/test_console_ztp.py
    # naming the behaviour, or is listed open in the register.
    *_each("modules.nsot.console_ztp._target",
           'def _target(list_name: str, device_id, profile_name: str, *, session=None, base: str = "",',
           ('def _target(list_name: str, device_id, profile_name: str, *, session=None, base: str = "XXXX",',),
           "the default is never used: both callers (survey_preview, kickstart_preview) pass "
           "their own base, always"),
    *_each("modules.nsot.console_ztp._target",
           '"transport": None, "profile": None}',
           ('"transport": None, "XXprofileXX": None}', '"transport": None, "PROFILE": None}'),
           'out["profile"] is assigned on every path before the first return (it follows the '
           "profile's own checks), and every reader takes the dict by key: a key named "
           "otherwise beside it is never read"),
    *_each("modules.nsot.console_ztp._target",
           'refuse("path", path.get("error") or path.get("why") or "no console path")',
           ('refuse("path", path.get("error") or path.get("why") or "XXno console pathXX")',
            'refuse("path", path.get("error") or path.get("why") or "NO CONSOLE PATH")'),
           "the stand-in is unreachable: console_path.read_console_path returns `path`, or "
           "`no_path` with its why (the empty port query's words, or each gap's, and a device "
           "with ports and no path has at least one gap), or `unreadable` with its error, "
           "every one of them non-empty"),
    *_each("modules.nsot.console_ztp._survey_phases",
           'verdict = V.survey(console.attach_state, "", profile)',
           ('verdict = V.survey(console.attach_state, None, profile)',
            'verdict = V.survey(console.attach_state, "XXXX", profile)'),
           "on this path nothing was read: console_survey.blank_check reads '' and None alike "
           "(`text.splitlines() if text else []`), and 'XXXX' holds no startup-config entry, "
           "so each gives the same unknown check, the same reason and the same verdict"),
    *_each("modules.nsot.console_ztp.survey_run",
           "values=values)", ("values=None)", ")"),
           "the values given to survey_preview reach only its masked program (`_masked_program`), "
           "which survey_run never reads: it takes the refusals, hash, device, port, path, "
           "profile and transport, and masks its own record with the values through `_Console` "
           "and `_finish`"),
    *_each("modules.nsot.console_ztp.survey_run",
           "console = None", ('console = ""',),
           "survey_run never reads `console`: it is only bound again, to the `_Console` handed "
           "to `_survey_phases`"),
]
