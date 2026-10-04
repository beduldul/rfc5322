"""Differential fuzz test: this parser vs. independent references.

This is the adversarial-evidence half of the project.  It runs a seeded,
deterministic corpus (hand-written cases + byte-level mutants) through three
references and asserts that the parser never *crashes* and that the only
divergences present are ones the RFC explains.

Running it
----------
``pytest`` runs the fast, hermetic part by default: the corpus is exercised
against the two always-available CPython references (``email.utils.parseaddr``
and ``email.headerregistry.Address``) and the parser is checked for internal
consistency.  ``email_validator`` is an optional dev-only dependency; when it
is importable (``uv run --with email-validator pytest``) it is included too.

The corpus is small enough (a few thousand inputs, sub-second) to live in the
normal test run; the full 4000-mutant sweep is available via
``python -m fuzz.run`` and in CI.

Determinism
-----------
Every corpus entry derives from ``SEED`` via :class:`random.Random`, so the
same seed yields byte-for-byte the same inputs and the same counts.  A failure
prints the offending input as a literal plus the seed, so it is reproducible
with ``python -m fuzz.run --replay '<input>'``.
"""

from __future__ import annotations

import contextlib

import pytest

from fuzz.corpus import generate, handwritten
from fuzz.references import (
    StdlibAddress,
    StdlibParseaddr,
    default_references,
)
from fuzz.report import (
    AGREE,
    OURS_ACCEPT_REF_REJECT,
    OURS_REJECT_REF_ACCEPT,
    _classify,
    _parser_verdict,
    run,
)

SEED = 5322
# Keep the in-pytest corpus modest so the suite stays fast; the CI job and
# `python -m fuzz.run` use the full 4000-mutant sweep.
TEST_MUTANTS = 1500


@pytest.fixture(scope="module")
def corpus() -> list[tuple[str, str]]:
    return generate(seed=SEED, n_mutants=TEST_MUTANTS)


# ---------------------------------------------------------------------------
# 1. The parser must never crash or contradict itself.
# ---------------------------------------------------------------------------


def test_parser_never_raises_unexpected(corpus: list[tuple[str, str]]) -> None:
    """A differential corpus must never provoke an unexpected exception."""
    from rfc5322 import AddressSyntaxError, parse_address

    for _, text in corpus:
        with contextlib.suppress(AddressSyntaxError):
            parse_address(text)
        # Any other exception type fails the test by propagating.


def test_is_valid_matches_parse_address(corpus: list[tuple[str, str]]) -> None:
    from rfc5322 import AddressSyntaxError, is_valid_address, parse_address

    for _, text in corpus:
        predicate = is_valid_address(text)
        try:
            parse_address(text)
            parsed = True
        except AddressSyntaxError:
            parsed = False
        assert predicate == parsed, f"inconsistent verdict for {text!r}"


# ---------------------------------------------------------------------------
# 2. Divergences must be the *known* ones, not new surprises.
# ---------------------------------------------------------------------------


def test_no_new_divergence_classes(corpus: list[tuple[str, str]]) -> None:
    """Every divergence class must already be documented in the reporter.

    The reporter's ``EXPECTED_DIVERGENCES`` lists one rationale per
    ``(reference, category)`` pair.  If a reference produces a category that
    has no rationale, this test fails — that is how a genuine regression
    becomes red CI instead of a silently-accepted count.
    """
    from fuzz.report import EXPECTED_DIVERGENCES

    references = default_references()
    for ref in references:
        for _, text in corpus:
            ours = _parser_verdict(text)
            verdict = ref.parse(text)
            category = _classify(ours, verdict)
            if category == AGREE:
                continue
            assert (ref.name, category) in EXPECTED_DIVERGENCES, (
                f"undocumented divergence: reference={ref.name} "
                f"category={category} input={text!r}"
            )


def test_stdlib_parseaddr_is_lenient(corpus: list[tuple[str, str]]) -> None:
    """The README's central claim, measured: parseaddr accepts inputs the RFC forbids.

    We require the *count* to be substantial and non-zero; the exact number is
    reported in the README and by ``python -m fuzz.run``.
    """
    ref = StdlibParseaddr()
    reject_ref_accept = 0
    for _, text in corpus:
        ours = _parser_verdict(text)
        verdict = ref.parse(text)
        if _classify(ours, verdict) == OURS_REJECT_REF_ACCEPT:
            reject_ref_accept += 1
    assert reject_ref_accept > 0, "expected parseaddr to accept RFC-invalid input"


def test_stdlib_parseaddr_mangles_valid_input(corpus: list[tuple[str, str]]) -> None:
    """parseaddr also *rejects* valid RFC 5322 input it cannot represent."""
    ref = StdlibParseaddr()
    accept_ref_reject = 0
    for _, text in corpus:
        ours = _parser_verdict(text)
        verdict = ref.parse(text)
        if _classify(ours, verdict) == OURS_ACCEPT_REF_REJECT:
            accept_ref_reject += 1
    assert accept_ref_reject > 0, "expected parseaddr to reject valid RFC input"


# ---------------------------------------------------------------------------
# 3. Pinned, deterministic counts (the measured evidence).
# ---------------------------------------------------------------------------


def test_measured_counts_are_stable() -> None:
    """Pin the measured counts for the full corpus so drift is visible.

    The numbers come from ``python -m fuzz.run --seed 5322 --mutants 4000``.
    They are assertions about *stability*, not about quality: if a parser or
    reference change moves them, the test fails and the README must be
    updated to match reality.
    """
    pytest.importorskip(
        "email_validator",
        reason="pinned counts include the email_validator reference; "
        "run under `uv run --with email-validator pytest`",
    )
    report = run(seed=SEED, n_mutants=4000, max_examples=0)
    counts = {r.name: dict(r.counts) for r in report.per_reference}
    assert report.corpus_size == 4160
    assert counts["stdlib.parseaddr"][AGREE] == 2554
    assert counts["stdlib.parseaddr"][OURS_REJECT_REF_ACCEPT] == 1360
    assert counts["stdlib.parseaddr"][OURS_ACCEPT_REF_REJECT] == 105
    assert counts["stdlib.headerregistry"][AGREE] == 3727
    assert counts["email_validator"][AGREE] == 3325


# ---------------------------------------------------------------------------
# 4. Regression tests for the bugs the harness found (see tests/test_obsolete).
# ---------------------------------------------------------------------------


def test_differential_caught_group_trailing_comma_flag() -> None:
    """Bug found by the harness: 'Group: a@b.com,;' parsed without obsolete flag."""
    from rfc5322 import parse_address

    addr = parse_address("Group: a@b.com,;", strict=False)
    assert addr.obsolete is True


def test_differential_caught_obs_local_part_flag() -> None:
    """Bug found by the harness: obs-local-part accepted but not flagged."""
    from rfc5322 import parse_address

    assert parse_address("user. name@x.com", strict=False).obsolete is True


def test_handwritten_corpus_is_nonempty() -> None:
    assert len(handwritten()) >= 150


def test_references_are_available() -> None:
    assert StdlibParseaddr().parse("a@b.com").accepted is True
    assert StdlibAddress().parse("a..b@b.com").accepted is False
