# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] — 2026-10-04

### Changed

- Documentation only: the install instructions now point at PyPI, and the PyPI
  badge was added.

## [1.0.0] — 2026-10-04

### Added

- `parse_address(text, *, strict=True)` — parses a single RFC 5322 `address`
  (mailbox or group), returning an immutable `Address`.
- `is_valid_address(text, *, strict=True)` — non-raising predicate.
- `parse_address_list(...)` and `parse_mailbox_list(...)` for §3.4 lists.
- Full ABNF coverage of §3.2–§3.4: `atext`, `dot-atom-text`, `quoted-string`,
  `quoted-pair`, `comment` (incl. nesting), `FWS` (incl. folding), `phrase`,
  `angle-addr`, `group`, `domain-literal` (IPv4/IPv6-shaped).
- §4.4 obsolete productions behind `strict=False`: `obs-local-part`,
  `obs-domain`, `obs-FWS`, `obs-ctext`, `obs-qtext`, `obs-qp`, `obs-dtext`,
  `obs-route`/`obs-angle-addr`, `obs-phrase`, `obs-group-list`, `obs-addr-list`.
  Use of any of these sets `Address.obsolete = True`.
- Semantic length enforcement: 998-char line (RFC 5322 §2.1.1), 64-char
  local part and 255-char domain (RFC 5321 §4.5.3.1), 63-char DNS labels
  (RFC 1035 §2.3.4).
- `AddressSyntaxError` carrying the byte offset and a caret-annotated excerpt.
- `python -m rfc5322 [--permissive] <address>` CLI with exit codes 0/1/2.
- `compliance.md` mapping every production to its section, implementation
  method and tests.
- Test suite of 263 cases at 98% statement coverage, including a
  `TestStdlibDivergence` class documenting where `email.utils.parseaddr`
  disagrees with RFC 5322.

### Notes

- No runtime dependencies; pure Python standard library.
- No regular expressions are used for grammar recognition.

[1.0.1]: https://github.com/beduldul/rfc5322/releases/tag/v1.0.1
[1.0.0]: https://github.com/beduldul/rfc5322/releases/tag/v1.0.0
