"""Run the corpus against every reference and bucket the divergences.

For each reference the reporter classifies every input into exactly one of
four buckets:

``agree``
    Both the parser and the reference accept, or both reject.
``ours_reject_ref_accept`` (category **a**)
    This parser rejects, the reference accepts.
``ours_accept_ref_reject`` (category **b**)
    This parser accepts, the reference rejects.
``both_accept_diff_output`` (category **c**)
    Both accept but normalise to different strings.

The buckets are *not* a scorecard.  A divergence is only evidence for the
README's central claim once it has been triaged against the RFC: some
references are stricter than RFC 5322 by design (``email_validator`` rejects
domain literals, comments and single-label domains), and some obsolete syntax
is optional, so "both accept" is a legitimate disagreement with no winner.

``EXPECTED_DIVERGENCES`` records the divergences that are known and understood,
keyed by ``(reference, category)``, with the RFC section that settles them.
The differential test asserts that no *unexpected* divergence class appears, so
a real regression is red CI rather than a silently-ignored count.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from rfc5322 import AddressSyntaxError, parse_address

from .corpus import generate
from .references import Reference, Verdict, default_references

# Category labels used throughout the report.
AGREE = "agree"
OURS_REJECT_REF_ACCEPT = "ours_reject_ref_accept"
OURS_ACCEPT_REF_REJECT = "ours_accept_ref_reject"
BOTH_ACCEPT_DIFF_OUTPUT = "both_accept_diff_output"

CATEGORIES = (AGREE, OURS_REJECT_REF_ACCEPT, OURS_ACCEPT_REF_REJECT,
              BOTH_ACCEPT_DIFF_OUTPUT)


@dataclass(frozen=True, slots=True)
class Divergence:
    """One concrete disagreement, with both verdicts for inspection."""

    category: str
    text: str
    ours: Verdict
    reference: Verdict
    corpus_category: str


@dataclass
class ReferenceReport:
    """Counts and examples for one reference."""

    name: str
    counts: Counter = field(default_factory=Counter)
    examples: dict[str, list[Divergence]] = field(default_factory=dict)

    def add(self, div: Divergence, *, max_examples: int = 5) -> None:
        self.counts[div.category] += 1
        if div.category == AGREE:
            return
        bucket = self.examples.setdefault(div.category, [])
        if len(bucket) < max_examples:
            bucket.append(div)


@dataclass
class Report:
    """The full differential result: one :class:`ReferenceReport` per ref."""

    corpus_size: int
    seed: int
    per_reference: list[ReferenceReport] = field(default_factory=list)
    elapsed: float = 0.0

    def total(self, category: str) -> int:
        """Sum a category's count across all references."""
        return sum(r.counts[category] for r in self.per_reference)


# ---------------------------------------------------------------------------
# Known / expected divergences (keyed by reference name + category)
# ---------------------------------------------------------------------------

#: Rationale for each divergence class that is expected and understood.
EXPECTED_DIVERGENCES: dict[tuple[str, str], str] = {
    ("stdlib.parseaddr", OURS_REJECT_REF_ACCEPT):
        "parseaddr accepts a superset of RFC 5322 (empty atoms, bare specials, "
        "obsolete phrases). These are the README's core claim — evidence FOR it.",
    ("stdlib.parseaddr", OURS_ACCEPT_REF_REJECT):
        "parseaddr returns ('', '') for valid domain-literals, comments and "
        "groups it cannot represent (RFC 5322 §3.4.1 domain-literal, §3.2.3 "
        "CFWS, §3.4 group). Evidence FOR the claim that it mangles valid input.",
    ("stdlib.parseaddr", BOTH_ACCEPT_DIFF_OUTPUT):
        "Both accept; parseaddr strips comments into the display name and "
        "drops brackets. Normalisation differs, both are 'valid'.",
    ("stdlib.headerregistry", OURS_REJECT_REF_ACCEPT):
        "headerregistry is stricter than the raw RFC grammar in places "
        "(e.g. it rejects some obsolete forms this parser accepts only under "
        "strict=False, and vice versa). Triage per example against the RFC.",
    ("stdlib.headerregistry", OURS_ACCEPT_REF_REJECT):
        "headerregistry cannot represent groups, comments or bare display "
        "names (RFC 5322 §3.4 constructs outside addr-spec); rejecting them "
        "is a scope limitation of the reference, not a parser bug.",
    ("stdlib.headerregistry", BOTH_ACCEPT_DIFF_OUTPUT):
        "Both accept; normalisation differs (headerregistry re-quotes).",
    ("email_validator", OURS_REJECT_REF_ACCEPT):
        "email_validator's syntactic layer is looser than RFC 5322 in places "
        "(it normalises before validating). Triage per example.",
    ("email_validator", OURS_ACCEPT_REF_REJECT):
        "email_validator is *not* an RFC 5322 reference: it deliberately "
        "rejects domain literals (§3.4.1), comments/CFWS (§3.2.3) and "
        "single-label domains (RFC 5321 requires a dot). It also does IDNA "
        "and deliverability semantics. Rejections here are expected and are "
        "NOT parser bugs.",
    ("email_validator", BOTH_ACCEPT_DIFF_OUTPUT):
        "email_validator lowercases the domain and normalises the local part; "
        "differences are normalisation, not validity.",
}


def _parser_verdict(text: str) -> Verdict:
    """Run this package's parser in strict mode and return a :class:`Verdict`."""
    try:
        addr = parse_address(text)
    except AddressSyntaxError as exc:
        return Verdict(accepted=False, detail=f"AddressSyntaxError@{exc.position}")
    except Exception as exc:  # noqa: BLE001 - must never crash the harness
        return Verdict(accepted=False, detail=f"UNEXPECTED {type(exc).__name__}")
    return Verdict(accepted=True, normalised=addr.normalized, detail="ok")


def _classify(ours: Verdict, ref: Verdict) -> str:
    if ours.accepted and ref.accepted:
        if ours.normalised == ref.normalised:
            return AGREE
        return BOTH_ACCEPT_DIFF_OUTPUT
    if not ours.accepted and not ref.accepted:
        return AGREE
    if not ours.accepted and ref.accepted:
        return OURS_REJECT_REF_ACCEPT
    return OURS_ACCEPT_REF_REJECT


def run(
    *,
    seed: int,
    n_mutants: int = 4000,
    references: list[Reference] | None = None,
    cases: list[tuple[str, str]] | None = None,
    max_examples: int = 5,
) -> Report:
    """Run the full corpus against every reference and return the report."""
    if cases is None:
        cases = generate(seed=seed, n_mutants=n_mutants)
    if references is None:
        references = default_references()

    reports = [ReferenceReport(name=r.name) for r in references]
    start = time.perf_counter()
    for corpus_category, text in cases:
        ours = _parser_verdict(text)
        for ref, rep in zip(references, reports, strict=True):
            verdict = ref.parse(text)
            category = _classify(ours, verdict)
            rep.add(
                Divergence(
                    category=category,
                    text=text,
                    ours=ours,
                    reference=verdict,
                    corpus_category=corpus_category,
                ),
                max_examples=max_examples,
            )
    elapsed = time.perf_counter() - start
    return Report(
        corpus_size=len(cases), seed=seed, per_reference=reports, elapsed=elapsed
    )


def format_report(report: Report) -> str:
    """Render a human-readable summary of a :class:`Report`."""
    lines = [
        f"corpus: {report.corpus_size} inputs  seed: {report.seed}  "
        f"elapsed: {report.elapsed:.2f}s",
    ]
    for rep in report.per_reference:
        lines.append(f"\n[{rep.name}]")
        for cat in CATEGORIES:
            lines.append(f"  {cat:26} {rep.counts[cat]}")
        for cat, examples in rep.examples.items():
            lines.append(f"  examples ({cat}):")
            for ex in examples:
                lines.append(
                    f"    {ex.text!r:40} ours={ex.ours.accepted} "
                    f"ref={ex.reference.accepted} "
                    f"({ex.reference.detail})"
                )
    return "\n".join(lines)
