# rfc5322

[![CI](https://github.com/beduldul/rfc5322/actions/workflows/ci.yml/badge.svg)](https://github.com/beduldul/rfc5322/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rfc5322.svg)](https://pypi.org/project/rfc5322/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Coverage: 99%](https://img.shields.io/badge/coverage-99%25-brightgreen.svg)](https://github.com/beduldul/rfc5322)
[![Ruff](https://img.shields.io/badge/lint-ruff-clean-brightgreen.svg)](https://github.com/astral-sh/ruff)

**Python's stdlib `email.utils.parseaddr` is not RFC 5322 conformant — it silently
accepts invalid addresses and mangles valid ones. `rfc5322` is a compliant,
dependency-free, spec-tested alternative.**

A hand-written recursive-descent parser for the RFC 5322 `address` grammar
(§3.2–§3.4) **plus every obsolete §4.4 production**. Zero runtime dependencies,
stdlib only, no regexes used for grammar recognition.

**Status:** v1.0.1 — 288 tests passing, 99% coverage, CI green on Python 3.12 and
3.13, MIT licensed. Published on PyPI as `rfc5322`.

```python
>>> from rfc5322 import is_valid_address
>>> is_valid_address("a..b@example.com")          # stdlib says this is fine
False
```

## Why this exists

`email.utils.parseaddr` is a pragmatic header-scanner, not a grammar. It is
lenient where the RFC is strict, and lossy where the RFC is precise. Every row
below was executed against CPython 3.12:

| Input | `email.utils.parseaddr` | `rfc5322` |
|---|---|---|
| `a..b@example.com` | `('', 'a..b@example.com')` — accepts a forbidden empty atom | rejected: `expected '@' in addr-spec (offset 1)` |
| `user@[192.0.2.1]` | `('', '')` — **mangles** a valid domain literal | accepted, `domain == '[192.0.2.1]'` |
| `a@b@c.com` | `('', '')` — returns nothing, no error | rejected: `unexpected trailing input '@c.com' (offset 3)` |
| `a@example.com, b@example.com` | `('', '')` — a list is not one address | rejected; use `parse_address_list` |
| `(comment)john@example.com` | `('comment', 'john@example.com')` — leaks the comment into the display name | accepted, `comments == ('comment',)`, `display_name is None` |
| `John Q. Public <j@x.com>` | `('John Q. Public', 'j@x.com')` — accepts an obsolete §4.4 phrase by default | rejected in strict mode; accepted with `strict=False` and flagged `obsolete` |

The stdlib's contract is "best effort"; this package's contract is "the ABNF,
or an error with the byte offset". Divergences are locked down by the
`TestStdlibDivergence` test class.

## Install

```sh
pip install rfc5322
```

To track `main` instead of a release:

```sh
# From GitHub (latest main):
pip install "git+https://github.com/beduldul/rfc5322.git"
# or with uv:
uv pip install "git+https://github.com/beduldul/rfc5322.git"
```

From a clone (editable, with dev tools):

```sh
git clone https://github.com/beduldul/rfc5322.git
cd rfc5322
uv venv && uv pip install -e ".[dev]"
```

Requires Python 3.12+. No runtime dependencies.

## Usage

```python
from rfc5322 import (
    parse_address, is_valid_address, parse_address_list, parse_mailbox_list,
    AddressSyntaxError,
)

# 1. A plain valid address, with a display name and CFWS comments.
addr = parse_address("John Doe (boss) <john.doe@example.com>")
addr.local_part    # 'john.doe'
addr.domain        # 'example.com'
addr.display_name  # 'John Doe'
addr.comments      # ('boss',)
addr.normalized    # 'john.doe@example.com'

# 2. A quoted local part — quotes are stripped, quoted-pairs decoded.
parse_address('"john doe"@example.com').local_part   # 'john doe'
parse_address('"a\\"b"@example.com').local_part      # 'a"b'

# 3. Obsolete §4.4 syntax is rejected by default, opt in explicitly.
is_valid_address('user."quoted"@example.com')                       # False
obs = parse_address('user."quoted"@example.com', strict=False)
obs.local_part, obs.obsolete                                        # ('user.quoted', True)

# 4. Invalid input raises with the exact offset and a caret excerpt.
try:
    parse_address("a..b@example.com")
except AddressSyntaxError as exc:
    print(exc)
    # expected '@' in addr-spec (offset 1)
    #   a..b@example.com
    #    ^
```

### CLI

```sh
$ python -m rfc5322 'John Doe <john@example.com>'
VALID: local_part='john' domain='example.com'
  normalized=john@example.com
  display_name='John Doe'

$ python -m rfc5322 --permissive 'user."q"@x.com'
VALID: local_part='user.q' domain='x.com'
  normalized=user.q@x.com
  (used obsolete §4.4 syntax)

$ python -m rfc5322 'a..b@x.com'; echo "exit=$?"
INVALID: expected '@' in addr-spec (offset 1)
  a..b@x.com
   ^
exit=1
```

Exit status: `0` valid, `1` invalid, `2` usage error. `-p` / `--permissive`
enables the obsolete productions. Installing the package also provides a
`rfc5322` console script with the same behaviour.

## API

| Function | Purpose |
|---|---|
| `parse_address(text, *, strict=True) -> Address` | Parse one `address` (mailbox or group). Raises `AddressSyntaxError`. |
| `is_valid_address(text, *, strict=True) -> bool` | Non-raising predicate. |
| `parse_address_list(text, *, strict=True) -> tuple[Address, ...]` | Parse an `address-list`. |
| `parse_mailbox_list(text, *, strict=True) -> tuple[Address, ...]` | Parse a `mailbox-list` (groups rejected). |

`Address` is a frozen, slotted dataclass — inputs are never mutated, every
function returns new immutable objects.

| `Address` field | Meaning |
|---|---|
| `local_part` | Decoded local part (quotes removed, `quoted-pair` decoded). |
| `domain` | Domain; a domain literal keeps its `[` `]` brackets. |
| `display_name` | Decoded `phrase` for `name-addr`/`group`, else `None`. |
| `comments` | Every CFWS comment, decoded, in source order. |
| `source` | The original input string. |
| `is_group` / `group_members` | Group flag and member addresses. |
| `obsolete` | `True` if a §4.4 production was required to accept the input. |
| `normalized` | Canonical `local@domain`, or `name:members;` for a group. |

`AddressSyntaxError` is a `ValueError` subclass carrying `position` and a
caret-annotated excerpt of the offending input.

## RFC coverage

| RFC 5322 section | Productions | Status |
|---|---|---|
| §3.2.1 | `quoted-pair`, `obs-qp` | complete |
| §3.2.2 | `FWS`, `obs-FWS` | complete |
| §3.2.3 | `CFWS`, `comment`, `ccontent`, `ctext`, `obs-ctext`, `atom`, `dot-atom`, `dot-atom-text` | complete |
| §3.2.4 | `quoted-string`, `qcontent`, `qtext`, `obs-qtext` | complete |
| §3.2.5 | `word`, `phrase`, `obs-phrase` | complete |
| §3.4 | `address`, `mailbox`, `name-addr`, `angle-addr`, `group`, `display-name`, `mailbox-list`, `address-list`, `group-list`, `obs-addr-list`, `obs-group-list`, `obs-mbox-list` | complete |
| §3.4.1 | `addr-spec`, `local-part`, `domain`, `domain-literal`, `dtext`, `obs-local-part`, `obs-domain`, `obs-route`, `obs-angle-addr`, `obs-dtext` | complete |
| §2.1.1 | 998-character line limit | enforced |
| RFC 5321 §4.5.3.1 | 64-char local part, 255-char domain | enforced |
| RFC 1035 §2.3.4 | 63-char DNS label | enforced |

A production-by-production mapping (production → section → implementation
method → tests) lives in [`compliance.md`](compliance.md).

## How this differs from `email.utils`

- **It rejects instead of guessing.** `parseaddr` returns `('', '')` for many
  malformed inputs and never raises; `rfc5322` raises `AddressSyntaxError` with
  the byte offset, or returns `False` from `is_valid_address`.
- **It preserves information the stdlib discards.** Comments are decoded into
  `Address.comments` rather than leaked into the display name; domain literals
  are kept (`[192.0.2.1]`) instead of being reduced to an empty string.
- **It distinguishes modern from obsolete syntax.** Obsolete §4.4 forms are
  accepted only under `strict=False`, and every such parse sets
  `Address.obsolete = True`, so callers can audit legacy mail.
- **It validates lists.** `parse_address_list` / `parse_mailbox_list` handle
  §3.4 comma lists (including the `obs-*-list` forms), which `parseaddr` cannot
  represent at all.
- **It enforces length limits** from RFC 5322 §2.1.1, RFC 5321 and RFC 1035,
  which the stdlib does not check.

## Limitations

Honest list — this parses *addresses*, not messages:

- **No MIME/header parsing.** §3.6 fields (`Received`, `Date`, `Message-ID`,
  `fields`/`trace`/`optional-field`) are out of scope.
- **No message body or MIME multipart parsing.**
- **No §4.5–§4.7 obsolete message syntax** (`obs-date`, `obs-received`,
  `obs-message-id`). Only the §4.4 addressing productions are implemented.
- **No semantic/DNS validation.** No MX lookup, no existence check — a
  syntactically valid domain need not exist.
- **Domain-literal contents are not interpreted.** `[IPv6:...]` is validated as
  `dtext` only; IPv4/IPv6 well-formedness is **not** checked. That belongs to a
  network layer.
- **ASCII only. No IDN/IDNA and no SMTPUTF8 (RFC 6531).** Non-ASCII input is
  rejected, because the RFC 5322 grammar is ASCII-only.
- **Length limits are stricter than the raw ABNF.** The 998/64/255/63 limits
  are an extra semantic pass; the pure grammar alone would accept longer input.
- **`group` `normalized` output is canonical, not byte-identical** to the input
  (display names are decoded but not re-quoted).

## Differential testing

The comparison table above is hand-written, so it is exactly the kind of
evidence that collapses when probed. `fuzz/` is a **seeded differential
harness** that checks the claim mechanically against three references:

| Reference | What it is | DNS? |
|---|---|---|
| `email.utils.parseaddr` | the stdlib scanner the claim is about | no |
| `email.headerregistry.Address(addr_spec=…)` | CPython's strict addr-spec parser | no |
| `email_validator` | the widely-used third-party validator | **disabled** |

`email_validator` performs DNS/MX lookups by default; the harness passes
`check_deliverability=False` so the comparison is **syntax only** and never
touches the network. `email_validator` is a **dev/test-only** dependency
(`uv run --with email-validator`, or the `[fuzz]` extra) — the package itself
still has zero runtime dependencies.

The corpus is **4160 inputs** (160 hand-written + 4000 byte-level mutants),
generated with `random.Random(5322)`. Re-run it deterministically with:

```sh
uv run --with email-validator python -m fuzz.run --seed 5322 --mutants 4000
uv run --with email-validator python -m fuzz.run --replay '<input>'   # reproduce one failure
```

Measured results (seed 5322, CPython 3.12):

| Reference | agree | we reject / it accepts | we accept / it rejects | both accept, output differs |
|---|---:|---:|---:|---:|
| `email.utils.parseaddr` | 2554 | **1360** | **105** | 141 |
| `email.headerregistry.Address` | 3727 | 177 | 196 | 60 |
| `email_validator` | 3325 | 70 | 754 | 11 |

**What the numbers mean.** They are not a scoreboard. Against `parseaddr` the
harness confirms the central claim: it accepts 1360 RFC-invalid inputs the
parser rejects (`a..b@example.com`, `.user@example.com`, `a b@example.com`,
`@example.com`, `"unbalanced@x.com`, …) and returns `('', '')` for 105 valid
ones it cannot represent (domain literals `user@[192.0.2.1]`, CFWS comments,
groups). Against `headerregistry` the parser agrees on 89.6% and the residual
divergences are its scope limits (it rejects groups, comments and bare
display names) plus length/ASCII policy. Against `email_validator` the parser
agrees on 79.9%; **the 754 "we accept / it rejects" cases are not parser
bugs** — `email_validator` deliberately rejects domain literals (§3.4.1),
CFWS comments (§3.2.3), quoted local parts and single-label domains, and it
applies IDNA/deliverability semantics that RFC 5322 does not.

**Bugs the harness found (fixed).** Adversarial fuzzing found three real
defects, all in the same family — inputs accepted only under `strict=False`
that did **not** set `Address.obsolete`, violating the documented invariant:

1. `user. name@x.com` (obs-local-part, §4.4) parsed with `obsolete=False`.
2. `john@example\r\n .com` (obs-domain, §4.4) parsed with `obsolete=False`.
3. `Group: a@b.com,;` (obs-mbox-list, §3.4) parsed with `obsolete=False`, and
   `parse_mailbox_list` did not implement `obs-mbox-list` at all despite the
   coverage table claiming it complete.

Each has a regression test in `tests/test_obsolete.py`. The pinned counts are
asserted in `tests/test_differential.py`, so a future change that shifts them
turns CI red rather than being silently absorbed.

## Development

```sh
uv venv
uv pip install -e ".[dev]"
.venv/bin/python -m pytest --cov=rfc5322 --cov-report=term-missing
.venv/bin/ruff check .
```

Current status: **288 tests passing, 99% statement coverage, ruff clean.**
See [`PROOF.txt`](PROOF.txt) for the verbatim run and [`CONTRIBUTING.md`](CONTRIBUTING.md)
before opening a PR.

## License

MIT — see [LICENSE](LICENSE).
