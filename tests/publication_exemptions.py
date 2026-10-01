"""Lines the publication check (`test_nothing_personal_is_published.py`) excuses.

ONE LINE per entry, keyed on the sha256 of the stripped line (its first 12
hex characters), with the reason and the rules it is excused from. An edited
line loses its entry and is read again; an entry whose line is gone fails the
check (no ghosts). The pattern is never narrowed to make room for a line: a
line is excused, by name, with why.

Written 2026-09-29 by classifying every finding across the tracked repository
after the real values were replaced; nothing here is the homelab, the operator
or a credential. A NEW test address should be a documentation address
(192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24, 2001:db8::/32), which needs no
entry.
"""

REASONS = {
    "VRNETLAB": "vrnetlab's internal management address (the .15 host, its gateway .2, its resolver .3), the same inside every container: quoted device output, not the homelab",
    "CAPTURE": "a captured device config or show output: vrnetlab's internal management network, a classful network statement, or a 10/8 route; not the homelab",
    "FIXTURE_LOG": "the suite's own fixture address, quoted from the app log",
    "EXAMPLE": "an example address in a form placeholder, a parser comment or an AI prompt example; not the homelab",
    "INVENTED": "an invented test address (new tests use documentation addresses instead)",
    "INVENTED_PATH": "an invented home directory in a test, naming no person",
    "SSH_FORM": "git's SSH URL form (the git user at GitHub's host, then owner/repo), GitHub's account, not a person's address",
    "VENDOR": "Cisco's own call-home address, printed by IOS-XE in the captured config",
}

#: (path, line hash) -> (reason key, rules excused)
EXEMPT = {
    # CLAUDE.md
    ('CLAUDE.md', 'a126bf59a559'): ('VRNETLAB', ('address',)),
    ('CLAUDE.md', '41fddedeca84'): ('VRNETLAB', ('address',)),
    ('CLAUDE.md', '78d35b5cb4c8'): ('VRNETLAB', ('address',)),
    ('CLAUDE.md', 'd70a0a321f4c'): ('VRNETLAB', ('address',)),
    # app.py
    ('app.py', '5e26ffc61b4b'): ('EXAMPLE', ('address',)),
    # docs/NSOT_WRITEUP.md
    ('docs/NSOT_WRITEUP.md', '65d73a3b391d'): ('VRNETLAB', ('address',)),
    # docs/NSOT_WRITEUP_NOTES.md
    ('docs/NSOT_WRITEUP_NOTES.md', '6ddf6399503e'): ('VRNETLAB', ('address',)),
    ('docs/NSOT_WRITEUP_NOTES.md', '83d4b9123c9f'): ('VRNETLAB', ('address',)),
    ('docs/NSOT_WRITEUP_NOTES.md', '25715794b34e'): ('VRNETLAB', ('address',)),
    ('docs/NSOT_WRITEUP_NOTES.md', '453247b4e56d'): ('VRNETLAB', ('address',)),
    ('docs/NSOT_WRITEUP_NOTES.md', '691ae00f5397'): ('VRNETLAB', ('address',)),
    ('docs/NSOT_WRITEUP_NOTES.md', 'e65637a37ac0'): ('VRNETLAB', ('address',)),
    ('docs/NSOT_WRITEUP_NOTES.md', 'c197b94492e2'): ('VRNETLAB', ('address',)),
    ('docs/NSOT_WRITEUP_NOTES.md', '3fe23aaf744c'): ('VRNETLAB', ('address',)),
    ('docs/NSOT_WRITEUP_NOTES.md', '5e27570dfa0f'): ('VRNETLAB', ('address',)),
    ('docs/NSOT_WRITEUP_NOTES.md', '90a9938fc540'): ('VRNETLAB', ('address',)),
    # docs/OPEN_FINDINGS.md
    ('docs/OPEN_FINDINGS.md', 'd61da30d6e24'): ('FIXTURE_LOG', ('address',)),
    ('docs/OPEN_FINDINGS.md', '22925f26679b'): ('FIXTURE_LOG', ('address',)),
    ('docs/OPEN_FINDINGS.md', '07623b5e97d7'): ('CAPTURE', ('address',)),
    ('docs/OPEN_FINDINGS.md', '27d3c4ac05f6'): ('VRNETLAB', ('address',)),
    # docs/P6_ZTP_PROBE.md
    ('docs/P6_ZTP_PROBE.md', '3b43d8de0cb6'): ('VRNETLAB', ('address',)),
    ('docs/P6_ZTP_PROBE.md', '2f31694af734'): ('VRNETLAB', ('address',)),
    # docs/PHASE2_DHCP.md
    ('docs/PHASE2_DHCP.md', '1dc599275d51'): ('VRNETLAB', ('address',)),
    ('docs/PHASE2_DHCP.md', 'eeb1506b2887'): ('VRNETLAB', ('address',)),
    # docs/R6_PHASE1.md
    ('docs/R6_PHASE1.md', '2677c75621ed'): ('VRNETLAB', ('address',)),
    # modules/ai_assistant.py
    ('modules/ai_assistant.py', '35696ba8fb1d'): ('EXAMPLE', ('address',)),
    ('modules/ai_assistant.py', '9fe2f79b7fde'): ('EXAMPLE', ('address',)),
    ('modules/ai_assistant.py', 'ba463ca407c2'): ('EXAMPLE', ('address',)),
    ('modules/ai_assistant.py', '7a2ecb6a5b8e'): ('EXAMPLE', ('address',)),
    ('modules/ai_assistant.py', '283f8c3aca96'): ('EXAMPLE', ('address',)),
    ('modules/ai_assistant.py', '62a692c54974'): ('EXAMPLE', ('address',)),
    # modules/ccie_kb.py
    ('modules/ccie_kb.py', 'adc881f38e9d'): ('EXAMPLE', ('address',)),
    ('modules/ccie_kb.py', 'c14c46b254c4'): ('EXAMPLE', ('address',)),
    # modules/netbox_client.py
    ('modules/netbox_client.py', 'd1303c000c65'): ('VRNETLAB', ('address',)),
    ('modules/netbox_client.py', '87f6e9899581'): ('VRNETLAB', ('address',)),
    ('modules/netbox_client.py', 'b7806a81965b'): ('EXAMPLE', ('address',)),
    ('modules/netbox_client.py', '576e67ac5e4c'): ('EXAMPLE', ('address',)),
    # modules/settings_schema.py
    ('modules/settings_schema.py', 'ebaf09b7354d'): ('VRNETLAB', ('address',)),
    # modules/topology.py
    ('modules/topology.py', '51693aea93bf'): ('EXAMPLE', ('address',)),
    ('modules/topology.py', '3214ceaba330'): ('EXAMPLE', ('address',)),
    # scripts/nmas-deploy
    ('scripts/nmas-deploy', '3da57d97c7c9'): ('SSH_FORM', ('email',)),
    # scripts/nmas-netbox-census
    ('scripts/nmas-netbox-census', 'e625d15292b6'): ('VRNETLAB', ('address',)),
    # scripts/nmas-netbox-deletions
    ('scripts/nmas-netbox-deletions', 'b5cc5f4f77fd'): ('VRNETLAB', ('address',)),
    # scripts/nmas-netbox-ip-provenance
    ('scripts/nmas-netbox-ip-provenance', '1cb7da624bd7'): ('VRNETLAB', ('address',)),
    ('scripts/nmas-netbox-ip-provenance', 'ddb890db45ab'): ('VRNETLAB', ('address',)),
    # scripts/nmas-netbox-repair-addresses
    ('scripts/nmas-netbox-repair-addresses', '45a4094e3ca8'): ('VRNETLAB', ('address',)),
    ('scripts/nmas-netbox-repair-addresses', 'bdd2d1a33609'): ('VRNETLAB', ('address',)),
    ('scripts/nmas-netbox-repair-addresses', 'ab78c9b98441'): ('VRNETLAB', ('address',)),
    # templates/index.html
    ('templates/index.html', '4545fc99b761'): ('EXAMPLE', ('address',)),
    ('templates/index.html', '367e90d50fbd'): ('EXAMPLE', ('address',)),
    ('templates/index.html', '58607bdbcc7f'): ('EXAMPLE', ('address',)),
    ('templates/index.html', '60097d7392bb'): ('EXAMPLE', ('address',)),
    ('templates/index.html', '9dd46217fee0'): ('EXAMPLE', ('address',)),
    ('templates/index.html', 'c08087506e93'): ('EXAMPLE', ('address',)),
    ('templates/index.html', '80badbb869fd'): ('EXAMPLE', ('address',)),
    ('templates/index.html', '2c71ce76c4fc'): ('EXAMPLE', ('address',)),
    ('templates/index.html', 'e10071bf559c'): ('EXAMPLE', ('address',)),
    # tests/fixtures/configs/fleet/r1.cfg
    ('tests/fixtures/configs/fleet/r1.cfg', '25715794b34e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r1.cfg', '4554dea76cef'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r1.cfg', '1ef15544fd6e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r1.cfg', 'a5b73e35b275'): ('VENDOR', ('email',)),
    ('tests/fixtures/configs/fleet/r1.cfg', 'f1eeba711c88'): ('VENDOR', ('email',)),
    # tests/fixtures/transcripts/r1/ (C281: r1's real channel transcripts)
    ('tests/fixtures/transcripts/r1/show_running-config.txt', 'a5b73e35b275'): ('VENDOR', ('email',)),
    ('tests/fixtures/transcripts/r1/show_running-config.txt', 'f1eeba711c88'): ('VENDOR', ('email',)),
    ('tests/fixtures/transcripts/r1/show_startup-config.txt', 'a5b73e35b275'): ('VENDOR', ('email',)),
    ('tests/fixtures/transcripts/r1/show_startup-config.txt', 'f1eeba711c88'): ('VENDOR', ('email',)),
    # tests/fixtures/configs/fleet/r2.cfg
    ('tests/fixtures/configs/fleet/r2.cfg', '25715794b34e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r2.cfg', '4554dea76cef'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r2.cfg', '1ef15544fd6e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r2.cfg', 'a5b73e35b275'): ('VENDOR', ('email',)),
    ('tests/fixtures/configs/fleet/r2.cfg', 'f1eeba711c88'): ('VENDOR', ('email',)),
    # tests/fixtures/configs/fleet/r3.cfg
    ('tests/fixtures/configs/fleet/r3.cfg', '25715794b34e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r3.cfg', '9531629e6bb1'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r3.cfg', '1ef15544fd6e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r3.cfg', '9dddeac51b9f'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r3.cfg', '044a388a1528'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r3.cfg', 'a5b73e35b275'): ('VENDOR', ('email',)),
    ('tests/fixtures/configs/fleet/r3.cfg', 'f1eeba711c88'): ('VENDOR', ('email',)),
    # tests/fixtures/configs/fleet/r4.cfg
    ('tests/fixtures/configs/fleet/r4.cfg', '25715794b34e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r4.cfg', '9531629e6bb1'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r4.cfg', '1ef15544fd6e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r4.cfg', '9dddeac51b9f'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r4.cfg', '044a388a1528'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r4.cfg', 'a5b73e35b275'): ('VENDOR', ('email',)),
    ('tests/fixtures/configs/fleet/r4.cfg', 'f1eeba711c88'): ('VENDOR', ('email',)),
    # tests/fixtures/configs/fleet/r5.cfg
    ('tests/fixtures/configs/fleet/r5.cfg', '25715794b34e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r5.cfg', '1ef15544fd6e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/fleet/r5.cfg', 'a5b73e35b275'): ('VENDOR', ('email',)),
    ('tests/fixtures/configs/fleet/r5.cfg', 'f1eeba711c88'): ('VENDOR', ('email',)),
    # tests/fixtures/configs/fleet/s1.cfg
    ('tests/fixtures/configs/fleet/s1.cfg', '4554dea76cef'): ('CAPTURE', ('address',)),
    # tests/fixtures/configs/fleet/s2.cfg
    ('tests/fixtures/configs/fleet/s2.cfg', '4554dea76cef'): ('CAPTURE', ('address',)),
    # tests/fixtures/configs/r1_c8000v.cfg
    ('tests/fixtures/configs/r1_c8000v.cfg', '25715794b34e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/r1_c8000v.cfg', '4554dea76cef'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/r1_c8000v.cfg', '1ef15544fd6e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/configs/r1_c8000v.cfg', 'a5b73e35b275'): ('VENDOR', ('email',)),
    ('tests/fixtures/configs/r1_c8000v.cfg', 'f1eeba711c88'): ('VENDOR', ('email',)),
    # tests/fixtures/configs/s1_vios_l2.cfg
    ('tests/fixtures/configs/s1_vios_l2.cfg', '4554dea76cef'): ('CAPTURE', ('address',)),
    # tests/fixtures/launch/c8000v-launch-adopted.py
    ('tests/fixtures/launch/c8000v-launch-adopted.py', '25715794b34e'): ('CAPTURE', ('address',)),
    ('tests/fixtures/launch/c8000v-launch-adopted.py', '418338bf7240'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/r1__show_ip_interface.txt
    ('tests/fixtures/operational/r1__show_ip_interface.txt', '623c97531dc3'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/r1__show_ip_interface_brief.txt
    ('tests/fixtures/operational/r1__show_ip_interface_brief.txt', 'ad12df682f8e'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/r1__show_ip_protocols.txt
    ('tests/fixtures/operational/r1__show_ip_protocols.txt', 'b0d56c1d2839'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/r1__show_ip_route_connected.txt
    ('tests/fixtures/operational/r1__show_ip_route_connected.txt', 'dce7999d2fd6'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/r1__show_lldp_neighbors_detail.txt
    ('tests/fixtures/operational/r1__show_lldp_neighbors_detail.txt', '4959e9033714'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/r3__show_interfaces_include_line_protocol_internet_address.txt
    ('tests/fixtures/operational/r3__show_interfaces_include_line_protocol_internet_address.txt', '623c97531dc3'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/r3__show_ip_interface.txt
    ('tests/fixtures/operational/r3__show_ip_interface.txt', '623c97531dc3'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/r3__show_ip_interface_brief.txt
    ('tests/fixtures/operational/r3__show_ip_interface_brief.txt', 'ad12df682f8e'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/r3__show_ip_route_connected.txt
    ('tests/fixtures/operational/r3__show_ip_route_connected.txt', '14d1ede57362'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/r3__show_lldp_neighbors_detail.txt
    ('tests/fixtures/operational/r3__show_lldp_neighbors_detail.txt', '4959e9033714'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/s1__show_interfaces_include_line_protocol_internet_address.txt
    ('tests/fixtures/operational/s1__show_interfaces_include_line_protocol_internet_address.txt', '52a444f92f5d'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/s1__show_ip_interface.txt
    ('tests/fixtures/operational/s1__show_ip_interface.txt', '52a444f92f5d'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/s1__show_ip_interface_brief.txt
    ('tests/fixtures/operational/s1__show_ip_interface_brief.txt', '1c2d77dffff6'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/s1__show_ip_protocols.txt
    ('tests/fixtures/operational/s1__show_ip_protocols.txt', 'b0d56c1d2839'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/s1__show_ip_route_connected.txt
    ('tests/fixtures/operational/s1__show_ip_route_connected.txt', 'c3f35bb9b981'): ('CAPTURE', ('address',)),
    ('tests/fixtures/operational/s1__show_ip_route_connected.txt', '1ee292969b7d'): ('CAPTURE', ('address',)),
    ('tests/fixtures/operational/s1__show_ip_route_connected.txt', '1ee73549552e'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/s1__show_lldp_neighbors_detail.txt
    ('tests/fixtures/operational/s1__show_lldp_neighbors_detail.txt', 'a2e3d21ca9f1'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/s3__show_ip_interface.txt
    ('tests/fixtures/operational/s3__show_ip_interface.txt', '623c97531dc3'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/s3__show_ip_interface_brief.txt
    ('tests/fixtures/operational/s3__show_ip_interface_brief.txt', '84bab8ca0bac'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/s3__show_ip_route_connected.txt
    ('tests/fixtures/operational/s3__show_ip_route_connected.txt', '06e3a4b3e5d6'): ('CAPTURE', ('address',)),
    ('tests/fixtures/operational/s3__show_ip_route_connected.txt', '1ee292969b7d'): ('CAPTURE', ('address',)),
    ('tests/fixtures/operational/s3__show_ip_route_connected.txt', '3df061570391'): ('CAPTURE', ('address',)),
    # tests/fixtures/operational/s3__show_lldp_neighbors_detail.txt
    ('tests/fixtures/operational/s3__show_lldp_neighbors_detail.txt', '4959e9033714'): ('CAPTURE', ('address',)),
    # tests/payload_providers.py
    ('tests/payload_providers.py', '5b7e7d75c9fb'): ('VRNETLAB', ('address',)),
    # tests/test_bgp_hold_watch.py
    ('tests/test_bgp_hold_watch.py', 'aa384372a7d4'): ('INVENTED', ('address',)),
    ('tests/test_bgp_hold_watch.py', 'df6e6b6b53ef'): ('INVENTED', ('address',)),
    # tests/test_configless_patch.py
    ('tests/test_configless_patch.py', '5f827c09f481'): ('INVENTED_PATH', ('home',)),
    ('tests/test_configless_patch.py', '1b90223d274e'): ('INVENTED_PATH', ('home',)),
    # tests/test_deploy_batch.py
    ('tests/test_deploy_batch.py', '87bbf6075987'): ('INVENTED', ('address',)),
    ('tests/test_deploy_batch.py', '88b8619445b9'): ('INVENTED', ('address',)),
    ('tests/test_deploy_batch.py', 'ccdc9051cd36'): ('INVENTED', ('address',)),
    ('tests/test_deploy_batch.py', 'c64944fb135d'): ('INVENTED', ('address',)),
    ('tests/test_deploy_batch.py', '6d17c8935f22'): ('INVENTED', ('address',)),
    ('tests/test_deploy_batch.py', 'ba163a630d06'): ('INVENTED', ('address',)),
    ('tests/test_deploy_batch.py', '8ece651c2de0'): ('INVENTED', ('address',)),
    ('tests/test_deploy_batch.py', '90d10df300b6'): ('INVENTED', ('address',)),
    # tests/test_deploy_plan_apply_seam.py
    ('tests/test_deploy_plan_apply_seam.py', 'c4884151e7cd'): ('INVENTED', ('address',)),
    # tests/test_deploy_safety.py
    ('tests/test_deploy_safety.py', 'fedeb72c8dda'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '671226a47cea'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', 'aca11bcbf466'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', 'd61c51eb4a5b'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', 'cc3e27437a06'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', 'b23f9ead59d2'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '08f5b94a4191'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '0ebd48e9f337'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '7f2b5140564f'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', 'd3e72cd7c0ce'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '8ece651c2de0'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', 'b025729949ba'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '8d8c873e1e39'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '2e05b1ecd557'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '6fe37d95438e'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '588aea4ac8f6'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '28e4f75245f9'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '081e6c175260'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', 'aa6375c6c4e4'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', '4cd8fe23af77'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', 'c382cbbbf1d1'): ('INVENTED', ('address',)),
    ('tests/test_deploy_safety.py', 'e939ba29a311'): ('INVENTED', ('address',)),
    # tests/test_description_repair.py
    ('tests/test_description_repair.py', '26ba3f4222ef'): ('INVENTED', ('address',)),
    # tests/test_import_skips_are_named.py
    ('tests/test_import_skips_are_named.py', '16962d08a1ec'): ('INVENTED', ('address',)),
    ('tests/test_import_skips_are_named.py', '4899db25f29d'): ('INVENTED', ('address',)),
    # tests/test_intent_editor.py
    ('tests/test_intent_editor.py', 'c606ebc87650'): ('INVENTED', ('address',)),
    ('tests/test_intent_editor.py', 'ddbc6e00bfc7'): ('INVENTED', ('address',)),
    ('tests/test_intent_editor.py', '2ee4e949feb2'): ('INVENTED', ('address',)),
    ('tests/test_intent_editor.py', 'bbdc66ceec96'): ('INVENTED', ('address',)),
    ('tests/test_intent_editor.py', 'e82fb2805790'): ('INVENTED', ('address',)),
    ('tests/test_intent_editor.py', 'ef1b919ddf87'): ('INVENTED', ('address',)),
    # tests/test_masked_lines_not_compared.py
    ('tests/test_masked_lines_not_compared.py', '946d64f2ee89'): ('INVENTED', ('address',)),
    ('tests/test_masked_lines_not_compared.py', 'cde71a4bc272'): ('INVENTED', ('address',)),
    ('tests/test_masked_lines_not_compared.py', '61060a7a2257'): ('INVENTED', ('address',)),
    ('tests/test_masked_lines_not_compared.py', '20cd6af05b17'): ('INVENTED', ('address',)),
    ('tests/test_masked_lines_not_compared.py', '899ab01b6639'): ('INVENTED', ('address',)),
    ('tests/test_masked_lines_not_compared.py', '7eea070be2aa'): ('INVENTED', ('address',)),
    # tests/test_netbox_cascade.py
    ('tests/test_netbox_cascade.py', '0ce2f11e51d6'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_cascade.py', 'a1aba4b17dc0'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_cascade.py', '221636a74212'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_cascade.py', '84039352a2aa'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_cascade.py', '40dd625818b3'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_cascade.py', '402a97924a53'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_cascade.py', 'd6eea5c31407'): ('VRNETLAB', ('address',)),
    # tests/test_netbox_census.py
    ('tests/test_netbox_census.py', '30a2d52dbdaf'): ('INVENTED', ('address',)),
    ('tests/test_netbox_census.py', '37547ed2ec84'): ('INVENTED', ('address',)),
    ('tests/test_netbox_census.py', '0519b24cbf54'): ('INVENTED', ('address',)),
    # tests/test_netbox_ip_scoping.py
    ('tests/test_netbox_ip_scoping.py', '6ddf6399503e'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', 'c97a7b98aa51'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', '74a72df71513'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', '8e5971d80c3a'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', '35e3ed785597'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', '3bc7fa3e3047'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', 'e1729a275925'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', '428038d86d73'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', '76598d4353fe'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', 'd4793356ecc2'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', '57ee56f767cf'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', '5552aa250df0'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', '360b94a444f2'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_ip_scoping.py', 'e1439bac9574'): ('VRNETLAB', ('address',)),
    # tests/test_netbox_update_provenance.py
    ('tests/test_netbox_update_provenance.py', '588f1212556d'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_update_provenance.py', 'fab327aa8e9a'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_update_provenance.py', '0c22907d2ded'): ('VRNETLAB', ('address',)),
    ('tests/test_netbox_update_provenance.py', '47a530bae07f'): ('VRNETLAB', ('address',)),
    # tests/test_new_container_programs.py
    ('tests/test_new_container_programs.py', '5d01c1890c0a'): ('INVENTED', ('address',)),
    ('tests/test_new_container_programs.py', '53ec8038b797'): ('INVENTED', ('address',)),
    # tests/test_no_pattern_kill.py
    ('tests/test_no_pattern_kill.py', '1f97a9a3e4a6'): ('INVENTED', ('address',)),
    ('tests/test_no_pattern_kill.py', '3b7b469000d7'): ('INVENTED', ('address',)),
    ('tests/test_no_pattern_kill.py', '7218c882618d'): ('INVENTED', ('address',)),
    # tests/test_no_unreachable_ui.py
    ('tests/test_no_unreachable_ui.py', 'e9082b6ec214'): ('INVENTED', ('address',)),
    ('tests/test_no_unreachable_ui.py', '796240fafc7c'): ('INVENTED', ('address',)),
    # tests/test_normalize_equivalence.py
    ('tests/test_normalize_equivalence.py', '4554dea76cef'): ('INVENTED', ('address',)),
    ('tests/test_normalize_equivalence.py', '4f7bba8eeb4e'): ('INVENTED', ('address',)),
    ('tests/test_normalize_equivalence.py', '5b410e369e4a'): ('INVENTED', ('address',)),
    # tests/test_nsot_remote.py
    ('tests/test_nsot_remote.py', 'bfaae587b689'): ('SSH_FORM', ('email',)),
    # tests/test_onboard_snmp.py
    ('tests/test_onboard_snmp.py', 'ac9ab8567d24'): ('INVENTED', ('address',)),
    # tests/test_other_readers_real_output.py
    ('tests/test_other_readers_real_output.py', 'fbc4be37cf05'): ('VRNETLAB', ('address',)),
    # tests/test_oxidized_freshness.py
    ('tests/test_oxidized_freshness.py', '846114f67778'): ('INVENTED', ('address',)),
    # tests/test_parsers_cisco_ios.py
    ('tests/test_parsers_cisco_ios.py', 'e2cc45c9f8ca'): ('INVENTED', ('address',)),
    # tests/test_pipeline.py
    ('tests/test_pipeline.py', 'd8e521899eea'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'e4b11e25c45f'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'b727b62f5377'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '086184d5a794'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '5a76dda6a43e'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '9190eb60f8f9'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'a7b4a2ac3acf'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '08c6843fdc22'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'df302fac222f'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '80e1396356db'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '549d7a5a08b8'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '71013ff66e05'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'd6d3b60d47ac'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '5ade088226c2'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '297ec216691d'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'bc80dd647de2'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'c31f05e18919'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'a5d3c3b7944e'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '6139e66ab57f'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '3f98077b6c7b'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'b9cc5e931b46'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'b235a1da02f1'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '293ffdbe554a'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'e8114156af58'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'd09dd5fc12f1'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '79761899ddf0'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '757233740869'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'ca0d4ffae0ce'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'c08a766960ec'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '932b63392d74'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '4e3ab67eb3d6'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'df8e8f1bd465'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'fcdb06e4ed65'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'ef8d2cb6ad38'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '7b117b0b0e42'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '3bf9f2faf49c'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'a100c6d944c3'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'b08b7c098b9c'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '5124f6ed2e9d'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '63744670e8b0'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'e9efd623df74'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '96f356bcd469'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'e3038f9adbea'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'a7383aebb106'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'ab20825ed547'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '7f2b5140564f'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '8ece651c2de0'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '7256f35acb7d'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '09bfa5bd888e'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '78c4bb67d3cc'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '64d1d821a800'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '95ef2e786e50'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '502d5bc3fcfd'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'f87738a875d4'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '78ae08040791'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '331d1e113af7'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '2e3e5165b5c8'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '0ebd48e9f337'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'ccdc9051cd36'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'e2cda6cf3163'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '982212b39c4c'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '81847dd59147'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '66e166067c9c'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '7a4a258178e7'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', 'bce42896950a'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '598c07462d84'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '96fef41dc149'): ('INVENTED', ('address',)),
    ('tests/test_pipeline.py', '33edd56fc2a9'): ('INVENTED', ('address',)),
    # tests/test_preview_diff_is_section_aware.py
    ('tests/test_preview_diff_is_section_aware.py', 'cdbcc38f07a5'): ('INVENTED', ('address',)),
    ('tests/test_preview_diff_is_section_aware.py', 'b94c63ec0e07'): ('INVENTED', ('address',)),
    ('tests/test_preview_diff_is_section_aware.py', 'c32de0c44bed'): ('INVENTED', ('address',)),
    ('tests/test_preview_diff_is_section_aware.py', '402ee2d7d39b'): ('INVENTED', ('address',)),
    ('tests/test_preview_diff_is_section_aware.py', '19348d6ea967'): ('INVENTED', ('address',)),
    ('tests/test_preview_diff_is_section_aware.py', '76491206d0e1'): ('INVENTED', ('address',)),
    ('tests/test_preview_diff_is_section_aware.py', '9d68dcc8444a'): ('INVENTED', ('address',)),
    ('tests/test_preview_diff_is_section_aware.py', 'a66c09467f07'): ('INVENTED', ('address',)),
    ('tests/test_preview_diff_is_section_aware.py', '682d28af2ed6'): ('INVENTED', ('address',)),
    ('tests/test_preview_diff_is_section_aware.py', '36ba1b86b249'): ('INVENTED', ('address',)),
    # tests/test_preview_reads_repo_golden.py
    ('tests/test_preview_reads_repo_golden.py', '7242117cd000'): ('INVENTED', ('address',)),
    # tests/test_provider_redaction.py
    ('tests/test_provider_redaction.py', '0debd19e9bcc'): ('INVENTED', ('address',)),
    ('tests/test_provider_redaction.py', 'c0a09d5ba7b1'): ('INVENTED', ('address',)),
    ('tests/test_provider_redaction.py', '004066eafe9a'): ('INVENTED', ('address',)),
    # tests/test_removal.py
    ('tests/test_removal.py', 'c53386323dad'): ('INVENTED', ('address',)),
    # tests/test_removal_pipeline.py
    ('tests/test_removal_pipeline.py', '42953e068bfd'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', 'a6694fccd839'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', '76996e7c9a72'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', 'f9b5b84a40e3'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', '25161b839f95'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', 'aa23c1c51bbc'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', '6ca853db55b5'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', '64d1d821a800'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', '61485c5dd3a5'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', 'da625bac900c'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', '1be0a0f8db1c'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', 'd3437babf474'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', 'b4f70e13097d'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', 'a575c475de07'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', '26d78e692dae'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', '96fdd31e5b8d'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', 'c1ed127d624b'): ('INVENTED', ('address',)),
    ('tests/test_removal_pipeline.py', '78ae08040791'): ('INVENTED', ('address',)),
    # tests/test_removal_probe.py
    ('tests/test_removal_probe.py', '1ea856da7516'): ('INVENTED', ('address',)),
    # tests/test_reveal_and_log_redaction.py
    ('tests/test_reveal_and_log_redaction.py', '8ffe31f17bf5'): ('INVENTED_PATH', ('home',)),
    # tests/test_rotation_reports_the_boot_file.py
    ('tests/test_rotation_reports_the_boot_file.py', '94b6b00bab18'): ('INVENTED_PATH', ('home',)),
    ('tests/test_rotation_reports_the_boot_file.py', '56d53765a934'): ('INVENTED_PATH', ('home',)),
    ('tests/test_rotation_reports_the_boot_file.py', '69a0f99171dc'): ('INVENTED_PATH', ('home',)),
    ('tests/test_rotation_reports_the_boot_file.py', 'ee8d50161eed'): ('INVENTED_PATH', ('home',)),
    # tests/test_setting_not_applicable.py
    ('tests/test_setting_not_applicable.py', '9930f78bd903'): ('INVENTED_PATH', ('home',)),
    # tests/test_startup_safety_composite.py
    ('tests/test_startup_safety_composite.py', 'd58133d1a62c'): ('INVENTED', ('address',)),
    ('tests/test_startup_safety_composite.py', '0b0681f03363'): ('INVENTED', ('address',)),
    # tests/test_store_integrity_c158_c160.py
    ('tests/test_store_integrity_c158_c160.py', '089c13fc0ba1'): ('INVENTED', ('address',)),
    ('tests/test_store_integrity_c158_c160.py', '7b0cdff27a72'): ('INVENTED', ('address',)),
    # tests/test_syslog_block.py
    ('tests/test_syslog_block.py', 'caed4d780f5d'): ('INVENTED', ('address',)),
}
