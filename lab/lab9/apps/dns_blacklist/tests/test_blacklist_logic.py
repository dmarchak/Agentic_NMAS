"""blacklist_logic over plain data: the verdict read, the decision and the fail mode, the cache,
the lookups in flight, the steering flows, and the config. Plain functions and asserts, Python
3.5 and Mercury's alike. The verdict service is never reached: each answer is given in the
shape `mercury_app.egress` answers in (``{"ok", "status", "body", "error"}``).

**The two measured answers (2026-11-10, docs/STANDING_APPROVAL_LOG.md).** `BAD_BODY` is the
answer recorded for `malware.testcategory.com`, with the fields the record kept (it elides
the flags and the Question, which the app does not read). The record for `example.com` kept
only that it answered "its real addresses, with no Comment", so `GOOD_BODY`'s addresses are
documentation ones and its TTL a placeholder: the app reads of it only that it is not 0.0.0.0
with Extended DNS Error 16.
"""

try:
    from mercury_app.testing import covers
except ImportError:                     # run with no SDK on the path (the gate reads the import)
    def covers(*_names):
        return lambda test: test

import blacklist_logic as L

BAD_BODY = {"Status": 0, "Answer": [{"name": "malware.testcategory.com", "type": 1, "TTL": 60,
                                     "data": "0.0.0.0"}],
            "Comment": ["EDE(16): Censored"]}
GOOD_BODY = {"Status": 0, "Answer": [{"name": "example.com", "type": 1, "TTL": 120,
                                      "data": "198.51.100.34"},
                                     {"name": "example.com", "type": 1, "TTL": 120,
                                      "data": "198.51.100.35"}]}
#: The SDK's own words for a destination that does not answer in time.
TIMED_OUT = {"ok": False, "status": 0, "body": None,
             "error": "verdict_service did not answer (timed out)"}


def ok(body):
    return {"ok": True, "status": 200, "body": body, "error": ""}


def config(**given):
    got, problems = L.parse_config(given)
    assert problems == [], problems
    return got


PAGE = {"ipv4": "192.0.2.80", "ipv6": "2001:db8::80"}


@covers("a bad site is blocked, over IPv4 and IPv6")
def test_the_measured_bad_answer_is_bad_and_a_bad_name_is_answered_or_dropped():
    verdict, ttl, why = L.read_verdict(ok(BAD_BODY))
    assert (verdict, ttl, why) == (L.BAD, 60, "")
    assert L.decide(verdict, config(block_page=PAGE)) == L.ANSWER
    assert L.decide(verdict, config(block_page={"ipv6": "2001:db8::80"})) == L.ANSWER
    assert L.decide(verdict, config()) == L.DROP
    assert L.decide(verdict, config(fail_mode="closed")) == L.DROP


@covers("a good site is allowed")
def test_the_measured_good_answer_is_good_and_allowed():
    verdict, ttl, why = L.read_verdict(ok(GOOD_BODY))
    assert (verdict, ttl, why) == (L.GOOD, 120, "")
    assert L.decide(verdict, config(block_page=PAGE)) == L.ALLOW
    assert L.decide(verdict, config(fail_mode="closed")) == L.ALLOW


def test_bad_needs_both_marks_and_a_body_given_as_text_is_read():
    no_comment = {"Status": 0, "Answer": BAD_BODY["Answer"]}
    no_sinkhole = dict(GOOD_BODY, Comment=["EDE(16): Censored"])
    assert L.read_verdict(ok(no_comment))[0] == L.GOOD
    assert L.read_verdict(ok(no_sinkhole))[0] == L.GOOD
    text = ('{"Status":0,"Answer":[{"name":"malware.testcategory.com","type":1,"TTL":60,'
            '"data":"0.0.0.0"}],"Comment":["EDE(16): Censored"]}')
    assert L.read_verdict(ok(text)) == (L.BAD, 60, "")
    nxdomain = {"Status": 3, "Authority": [{"name": "invalid", "type": 6, "TTL": 900}]}
    assert L.read_verdict(ok(nxdomain)) == (L.GOOD, 900, "")


@covers("no verdict follows the fail mode")
def test_an_answer_not_read_is_unknown_and_says_why():
    cases = [(TIMED_OUT, "timed out"),
             ({"ok": False, "status": 503, "body": "", "error": "verdict_service answered 503"},
              "503"),
             (ok("<html>not json</html>"), "not JSON"),
             (ok(["a", "list"]), "not a JSON object"),
             (ok({"Answer": []}), "no Status"),
             (ok({"Status": "0"}), "no Status"),
             (ok({"Status": 0, "Answer": {"data": "0.0.0.0"}}), "not lists"),
             (ok({"Status": 2}), "Status 2"),
             ("not a mapping", "not a mapping")]
    for answer, words in cases:
        verdict, ttl, why = L.read_verdict(answer)
        assert verdict == L.UNKNOWN and ttl is None and words in why, (answer, why)


@covers("no verdict follows the fail mode")
def test_fail_open_forwards_and_fail_closed_blocks_an_unknown():
    assert L.decide(L.UNKNOWN, config()) == L.ALLOW
    assert L.decide(L.UNKNOWN, config(fail_mode="open", block_page=PAGE)) == L.ALLOW
    assert L.decide(L.UNKNOWN, config(fail_mode="closed")) == L.DROP
    assert L.decide(L.UNKNOWN, config(fail_mode="closed", block_page=PAGE)) == L.ANSWER


@covers("no verdict follows the fail mode")
def test_a_lookup_past_its_deadline_is_decided_unknown_and_a_late_answer_waits_for_nobody():
    pending = L.Pending()
    assert pending.start("example.com", "q1", 100.0, 2.0) == L.Pending.ASK
    assert pending.start("example.com", "q2", 100.5, 2.0) == L.Pending.JOINED
    assert pending.expired(101.9) == []
    assert pending.expired(102.0) == [("example.com", ["q1", "q2"])]
    assert pending.finish("example.com") == [] and pending.size() == 0


def test_the_lookups_in_flight_are_bounded():
    pending = L.Pending(max_lookups=2, max_waiting=2)
    assert pending.start("a.example", 1, 0.0, 2.0) == L.Pending.ASK
    assert pending.start("b.example", 2, 0.0, 2.0) == L.Pending.ASK
    assert pending.start("c.example", 3, 0.0, 2.0) == L.Pending.FULL
    assert pending.start("a.example", 4, 0.0, 2.0) == L.Pending.JOINED
    assert pending.start("a.example", 5, 0.0, 2.0) == L.Pending.FULL
    assert pending.finish("a.example") == [1, 4]
    assert pending.start("c.example", 3, 0.0, 2.0) == L.Pending.ASK


@covers("a verdict is cached for the lesser of its TTL and the cap")
def test_a_verdict_is_kept_for_the_lesser_of_its_ttl_and_the_cap():
    cache = L.Cache(max_entries=10, ttl_cap_s=90)
    assert cache.put("example.com", L.GOOD, 120, 1000.0) == 90
    assert cache.put("malware.testcategory.com", L.BAD, 60, 1000.0) == 60
    assert cache.get("example.com", 1089.9) == L.GOOD
    assert cache.get("example.com", 1090.0) is None
    assert cache.get("malware.testcategory.com", 1059.9) == L.BAD
    assert cache.get("malware.testcategory.com", 1060.0) is None and cache.size() == 0


@covers("a verdict is cached for the lesser of its TTL and the cap")
def test_no_ttl_takes_the_cap_a_zero_ttl_is_not_kept_and_an_unknown_is_held_briefly():
    cache = L.Cache(max_entries=10, ttl_cap_s=300)
    assert cache.put("a.example", L.GOOD, None, 0.0) == 300
    assert cache.put("b.example", L.GOOD, 0, 0.0) == 0 and cache.get("b.example", 0.0) is None
    assert cache.put("c.example", L.UNKNOWN, None, 0.0) == L.UNKNOWN_HOLD_S
    assert cache.get("c.example", L.UNKNOWN_HOLD_S - 0.1) == L.UNKNOWN
    assert cache.get("c.example", L.UNKNOWN_HOLD_S) is None


def test_the_cache_is_bounded_dropping_the_expired_then_the_oldest():
    cache = L.Cache(max_entries=2, ttl_cap_s=300)
    cache.put("short.example", L.GOOD, 5, 0.0)
    cache.put("long.example", L.GOOD, 300, 0.0)
    cache.put("new.example", L.BAD, 300, 10.0)          # short.example has expired: it goes
    assert cache.get("long.example", 10.0) == L.GOOD and cache.size() == 2
    cache.put("newer.example", L.BAD, 300, 11.0)        # none expired: the oldest goes
    assert cache.get("long.example", 11.0) is None
    assert cache.get("new.example", 11.0) == L.BAD and cache.size() == 2


def test_the_verdict_path_asks_for_json_and_takes_only_a_parsed_name():
    assert L.verdict_path("malware.testcategory.com") == \
        "/dns-query?name=malware.testcategory.com&type=A"
    assert L.VERDICT_ACCEPT == "application/dns-json"
    for bad in ("example.com&type=TXT", "a..example", "", "Example.com", "x" * 64 + ".example"):
        try:
            L.verdict_path(bad)
        except ValueError as exc:
            assert "not a name" in str(exc)
        else:
            assert False, bad


@covers("only DNS is steered, on edge ports")
def test_udp_53_goes_to_the_controller_on_every_edge_port_for_both_families_and_nothing_else():
    up = {3: set([1, 2, 5]), 4: set([2, 5])}
    links = set([(3, 2, 4, 2), (4, 2, 3, 2)])
    assert L.edge_ports(up, links, 3) == [1, 5] and L.edge_ports(up, links, 4) == [5]
    flows = L.desired_flows(100, L.edge_ports(up, links, 3))
    assert len(flows) == 4
    seen = set()
    for (table, priority, match), (actions, value) in flows.items():
        fields = dict(match)
        assert table == 100 and priority == L.PRIORITY and actions == (L.CONTROLLER,)
        assert sorted(fields) == ["eth_type", "in_port", "ip_proto", "udp_dst"]
        assert fields["ip_proto"] == 17 and fields["udp_dst"] == 53 and L.is_ours(value)
        seen.add((fields["in_port"], fields["eth_type"]))
    assert seen == set([(1, 0x0800), (1, 0x86dd), (5, 0x0800), (5, 0x86dd)])
    # DHCP (67, 68) is never matched, and the link port 2 carries no steering flow.
    assert not any(dict(k[2]).get("udp_dst") in (67, 68) or dict(k[2])["in_port"] == 2
                   for k in flows)


@covers("only DNS is steered, on edge ports")
def test_reconcile_changes_only_the_difference_and_only_the_apps_own_flows():
    want = L.desired_flows(0, [1, 5])
    current = dict(list(want.items())[:3])
    stale = (0, L.PRIORITY, (("eth_type", 0x0800), ("in_port", 2), ("ip_proto", 17),
                             ("udp_dst", 53)))
    current[stale] = ((L.CONTROLLER,), L.cookie(L.PUNT_IPV4))
    other = (0, 5, (("eth_type", 0x0800),))
    current[other] = ((("OTHER", "x"),), 0x4646000000000004)
    diff = L.difference(want, current)
    missing = [k for k in want if k not in current]
    assert [a[0] for a in diff["add"]] == missing and len(missing) == 1
    assert diff["delete"] == [(stale, L.cookie(L.PUNT_IPV4))]
    assert L.difference(want, dict(want)) == {"add": [], "delete": []}


def test_the_config_takes_mercurys_compile_and_fills_the_defaults():
    got = config(switches={"56298109234905574": {"forward_table": 100}},
                 verdict_service={"url": "https://security.cloudflare-dns.com:443"})
    assert L.table_for(got, 56298109234905574) == 100 and L.table_for(got, 3) is None
    assert (got["timeout_s"], got["fail_mode"], got["ttl_cap_s"], got["max_entries"]) == \
        (2.0, "open", 300, 10000)
    assert got["block_ipv4"] is None and got["upstream"] is None
    both = config(default_tables={"forward_table": 0}, block_page=PAGE,
                  upstream={"dpid": "3", "port": 4})
    assert L.table_for(both, 3) == 0 and both["upstream"] == (3, 4)
    assert (both["block_ipv4"], both["block_ipv6"]) == ("192.0.2.80", "2001:db8::80")


def test_the_config_refuses_each_field_by_name():
    cases = [({"verdict_service": {"url": "https://dns.example"}}, "verdict_service.url"),
             ({"verdict_service": {"timeout_s": 11}}, "timeout_s is a number, 0.1 to 10"),
             ({"fail_mode": "maybe"}, "fail_mode is open or closed"),
             ({"cache": {"ttl_cap_s": 0}}, "cache.ttl_cap_s"),
             ({"block_page": {"ipv4": "2001:db8::80"}}, "block_page.ipv4 is a unicast IPv4"),
             ({"block_page": {"ipv6": "192.0.2.80"}}, "block_page.ipv6 is a unicast IPv6"),
             ({"block_page": {"ipv6": "ff02::1"}}, "block_page.ipv6"),
             ({"switches": {"x": {"forward_table": 0}}}, "not a datapath id"),
             ({"switches": {"3": {"forward_table": 300}}}, "0 to 254"),
             ({"upstream": {"dpid": "3"}}, "upstream.port"),
             ({"answer": "everything"}, "not 'answer'")]
    for data, words in cases:
        got, problems = L.parse_config(data)
        assert got is None and any(words in p for p in problems), (data, problems)
    assert L.from_start_config(None)[1] == L.NO_SDK
    assert "was not read: gone" in L.from_start_config({"ok": False, "error": "gone"})[1]
