# Contributing to rfc5322

Thanks for taking the time to contribute. This project aims to be a small,
correct, dependency-free implementation of the RFC 5322 address grammar.

## Ground rules

- **Correctness first.** Any change to the grammar must cite the RFC 5322
  (or RFC 5234 / RFC 5321 / RFC 1035) production it implements.
- **No runtime dependencies.** The package must stay pure-stdlib. Test-only
  dependencies are fine.
- **No regular expressions for grammar recognition.** The parser is
  hand-written recursive descent on purpose; keep it that way.
- **Do not weaken tests.** If a test looks wrong, explain why in the PR and
  change it deliberately — never delete or `skip` a test to get green.

## Development setup

```sh
git clone https://github.com/beduldul/rfc5322.git
cd rfc5322
uv venv
uv pip install -e ".[dev]"
```

## Before you open a PR

Run the same checks CI runs:

```sh
.venv/bin/ruff check .
.venv/bin/python -m pytest --cov=rfc5322 --cov-report=term-missing
```

Both must pass. New behaviour needs tests; bug fixes need a regression test
that fails before the fix and passes after.

## Coverage expectations

- Every ABNF production reachable from `address` must have at least one test.
- New productions must be added to `compliance.md` (production → section →
  implementation → tests) and to the coverage table in `README.md`.
- Keep statement coverage at or above 95%.

## Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):
`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `perf:`.

## Reporting bugs

Please include:

1. The exact input string (use a Python repr so control characters survive).
2. What you expected, and the RFC production that justifies it.
3. What actually happened, including the full `AddressSyntaxError` message.
4. Your Python version.

## Scope

This library parses **addresses**, not messages. MIME, message headers,
message bodies, DNS/MX resolution, IDN/IDNA and SMTPUTF8 are explicitly out of
scope — see the Limitations section of the README before filing a feature
request.
