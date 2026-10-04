# Compliance matrix — RFC 5322 address grammar

Maps every ABNF production reachable from `address` to its defining section,
the parser method that implements it, and the tests that exercise it.

Legend: **strict** = accepted in default mode; **obs** = accepted only with
`strict=False` and sets `Address.obsolete`.

## RFC 5234 core rules

| Production | Section | Implementation | Tests |
|---|---|---|---|
| `ALPHA` | RFC 5234 §2.3 | `_ALPHA` | all `SIMPLE_VALID` |
| `DIGIT` | RFC 5234 §2.3 | `_DIGIT` | `1234567890@example.com` |
| `VCHAR` | RFC 5234 §2.3 | `_VCHAR` | `_parse_quoted_pair` tests |
| `WSP` | RFC 5234 §2.3 | `_WSP` | FWS tests |
| `CRLF` | RFC 5234 §2.3 | `_CRLF`, `_parse_fws`, `_at_fold` | `test_fws_*` |

## §3.2.1 — quoted-pair

| Production | Status | Implementation | Tests |
|---|---|---|---|
| `quoted-pair = ("\" (VCHAR / WSP))` | strict | `_parse_quoted_pair` | `test_quoted_escaped_quote_decodes`, `test_quoted_escaped_backslash_decodes` |
| `obs-qp = "\" (%d0 / obs-NO-WS-CTL / LF / CR)` | obs | `_parse_quoted_pair` | `test_obs_qp_*` |

## §3.2.2 — FWS

| Production | Status | Implementation | Tests |
|---|---|---|---|
| `FWS = ([*WSP CRLF] 1*WSP)` | strict | `_parse_fws` | `test_fws_around_at`, `test_fws_fold_*`, `test_fws_tab` |
| `obs-FWS = 1*WSP *(CRLF 1*WSP)` | obs | `_parse_fws` | `test_obs_fws_leading_wsp_before_crlf_permissive` |

## §3.2.3 — CFWS, comments, atoms

| Production | Status | Implementation | Tests |
|---|---|---|---|
| `CFWS = (1*([FWS] comment) [FWS]) / FWS` | strict | `_parse_cfws` | all `test_comment_*`, `test_leading_comment` |
| `comment = "(" *([FWS] ccontent) [FWS] ")"` | strict | `_parse_comment` | `test_comment_*`, `test_nested_comments` |
| `ccontent = ctext / quoted-pair / comment` | strict | `_parse_comment` | `test_comment_with_escaped_paren`, `test_deeply_nested_comments` |
| `ctext = %d33-39 / %d42-91 / %d93-126` | strict | `_CTEXT` | `test_comment_containing_at_sign` |
| `obs-ctext = obs-NO-WS-CTL` | obs | `_parse_comment` | `test_obs_ctext_in_comment_*` |
| `atom = [CFWS] 1*atext [CFWS]` | strict | `_parse_atom` | `test_simple_valid`, phrase tests |
| `dot-atom = [CFWS] dot-atom-text [CFWS]` | strict | `_parse_dot_atom` | `test_addr_spec_parts`, `john.doe@example.com` |
| `dot-atom-text = 1*atext *("." 1*atext)` | strict | `_parse_dot_atom_text` | double/leading/trailing dot rejections |
| `atext` | strict | `_ATEXT` | all `SIMPLE_VALID` |

## §3.2.4 — quoted-string

| Production | Status | Implementation | Tests |
|---|---|---|---|
| `quoted-string = [CFWS] DQUOTE *([FWS] qcontent) [FWS] DQUOTE [CFWS]` | strict | `_parse_quoted_string` | all `QUOTED_VALID` |
| `qcontent = qtext / quoted-pair` | strict | `_parse_quoted_string` | `test_quoted_*` |
| `qtext = %d33 / %d35-91 / %d93-126` | strict | `_QTEXT` | `test_quoted_local_part_keeps_dots` |
| `obs-qtext = obs-NO-WS-CTL` | obs | `_parse_quoted_string` | `test_obs_qtext_*` |

## §3.2.5 — miscellaneous tokens

| Production | Status | Implementation | Tests |
|---|---|---|---|
| `word = atom / quoted-string` | strict | `_parse_word` | `test_name_addr_quoted_display` |
| `phrase = 1*word` | strict | `_parse_phrase` | `test_name_addr_simple`, `test_group_quoted_display` |
| `obs-phrase = word *(word / "." / CFWS)` | obs | `_parse_phrase` | `test_obs_phrase_with_dot`, `test_obs_phrase_word_and_dot` |

## §3.4 — address, mailbox, group

| Production | Status | Implementation | Tests |
|---|---|---|---|
| `address = mailbox / group` | strict | `parse_address` | `test_group_*`, `test_name_addr_*` |
| `mailbox = name-addr / addr-spec` | strict | `_parse_mailbox` | `test_name_addr_angle_only`, `test_simple_valid` |
| `name-addr = [display-name] angle-addr` | strict | `_parse_mailbox` | `test_name_addr_simple` |
| `angle-addr = [CFWS] "<" addr-spec ">" [CFWS]` | strict | `_parse_angle_addr` | `test_name_addr_angle_only`, `test_comment_before_and_after_angle` |
| `group = display-name ":" [group-list] ";" [CFWS]` | strict | `_parse_group` | `test_group_basic`, `test_group_empty` |
| `display-name = phrase` | strict | `_parse_phrase` | `test_name_addr_quoted_display` |
| `mailbox-list = (mailbox *("," mailbox)) / obs-mbox-list` | strict | `parse_mailbox_list` | `test_mailbox_list_two`, `test_mailbox_list_rejects_group` |
| `address-list = (address *("," address)) / obs-addr-list` | strict | `parse_address_list` | `test_address_list_*` |
| `group-list = mailbox-list / CFWS / obs-group-list` | strict | `_parse_group` | `test_group_basic`, `test_group_empty` |
| `obs-group-list = 1*([CFWS] ",") [CFWS]` | obs | `_parse_group` | `test_obs_group_list_*` |
| `obs-addr-list = *([CFWS] ",") address *("," [address / CFWS])` | obs | `parse_address_list` | `test_obs_addr_list_*` |
| `obs-mbox-list = *([CFWS] ",") mailbox *("," [mailbox / CFWS])` | obs | `parse_mailbox_list` | leading/trailing comma tests |

## §3.4.1 — addr-spec

| Production | Status | Implementation | Tests |
|---|---|---|---|
| `addr-spec = local-part "@" domain` | strict | `_parse_addr_spec` | all `SIMPLE_VALID` |
| `local-part = dot-atom / quoted-string / obs-local-part` | strict | `_parse_local_part` | `test_quoted_*`, `test_addr_spec_parts` |
| `domain = dot-atom / domain-literal / obs-domain` | strict | `_parse_domain` | `test_domain_literal_*`, `test_addr_spec_parts` |
| `domain-literal = [CFWS] "[" *([FWS] dtext) [FWS] "]" [CFWS]` | strict | `_parse_domain_literal` | `test_domain_literal_valid`, `test_empty_domain_literal_is_legal` |
| `dtext = %d33-90 / %d94-126` | strict | `_DTEXT` | `test_domain_literal_valid` |
| `obs-local-part = word *("." word)` | obs | `_parse_local_part` | `test_obs_local_part_*` |
| `obs-domain = atom *("." atom)` | obs | `_parse_domain` | `test_obs_domain_*` |
| `obs-route = obs-domain-list ":"` | obs | `_parse_angle_addr` | `test_obs_route_permissive` |
| `obs-angle-addr = [CFWS] "<" obs-route addr-spec ">" [CFWS]` | obs | `_parse_angle_addr` | `test_obs_route_*` |
| `obs-dtext = obs-NO-WS-CTL / quoted-pair` | obs | `_parse_domain_literal` | `test_obs_dtext_*` |

## Semantic limits (outside the ABNF)

| Rule | Source | Implementation | Tests |
|---|---|---|---|
| Line ≤ 998 chars | RFC 5322 §2.1.1 | `_validate_lengths` | `test_long_line_998_chars`, `test_over_long_line_1000_chars_rejected` |
| local-part ≤ 64 chars | RFC 5321 §4.5.3.1.1 | `_validate_lengths` | `test_max_local_part_length_accepted`, `test_very_long_local_part_rejected` |
| domain label ≤ 63 chars | RFC 1035 §2.3.4 | `_validate_lengths` | `test_label_too_long_rejected` |
| domain ≤ 255 chars | RFC 5321 §4.5.3.1.2 | `_validate_lengths` | `test_long_line_998_chars` |
