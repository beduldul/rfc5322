"""Adapters over the independent reference parsers.

Three references are used, each with an explicit, documented contract so a
disagreement can be attributed to a *behaviour*, not to an accident of how the
adapter was written.

``StdlibParseaddr``
    ``email.utils.parseaddr`` — the exact function the README claims is
    non-conformant.  "Accepts" means it returned a non-empty address.  This is
    the stdlib's own contract ("best effort"): an input it mangles to
    ``('', '')`` is a rejection.

``StdlibAddress``
    ``email.headerregistry.Address(addr_spec=...)`` — CPython's *modern*
    addr-spec parser.  This is a stricter, independent-in-implementation
    oracle for the ``addr-spec`` production only (it cannot represent groups,
    comments or a bare display name).  "Accepts" means no exception.

``EmailValidator``
    The third-party ``email_validator`` package.  It performs DNS/MX lookups
    **by default**; the adapter passes ``check_deliverability=False`` so the
    comparison is *syntax only* and never touches the network.  This is
    stated here and repeated in the README because it is the single easiest
    way to accidentally make this comparison non-hermetic.

Each adapter returns a small :class:`Verdict` so the reporter does not need to
know whether a reference signals rejection via exception or empty string.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from email.headerregistry import Address as _HeaderAddress
from email.utils import parseaddr as _parseaddr


@dataclass(frozen=True, slots=True)
class Verdict:
    """The outcome of running one reference over one input.

    Attributes
    ----------
    accepted:
        ``True`` if the reference accepted the input as an address.
    normalised:
        The reference's normalised address, or ``None`` when it rejected or
        produced nothing.  Used for the "both accept, different output"
        category.
    detail:
        Human-readable note (exception type/message) for the report.
    """

    accepted: bool
    normalised: str | None = None
    detail: str = ""


class Reference:
    """Base class for a named reference implementation."""

    name: str = "reference"

    def parse(self, text: str) -> Verdict:  # pragma: no cover - overridden
        raise NotImplementedError


class StdlibParseaddr(Reference):
    """``email.utils.parseaddr`` — lenient, never raises, lossy."""

    name = "stdlib.parseaddr"

    def parse(self, text: str) -> Verdict:
        name, addr = _parseaddr(text)
        accepted = addr != ""
        # parseaddr silently drops the address for inputs it cannot handle.
        return Verdict(
            accepted=accepted,
            normalised=addr if accepted else None,
            detail=f"parseaddr -> ({name!r}, {addr!r})",
        )


class StdlibAddress(Reference):
    """``email.headerregistry.Address`` addr-spec oracle (strict, modern)."""

    name = "stdlib.headerregistry"

    def parse(self, text: str) -> Verdict:
        try:
            addr = _HeaderAddress(addr_spec=text)
        except Exception as exc:  # noqa: BLE001 - reference boundary
            return Verdict(accepted=False, detail=f"{type(exc).__name__}")
        return Verdict(accepted=True, normalised=addr.addr_spec)


class EmailValidator(Reference):
    """``email_validator`` with DNS/MX lookups explicitly disabled.

    ``check_deliverability=False`` is mandatory: without it the library
    performs live DNS queries and the comparison would depend on network
    state, not on RFC 5322 syntax.
    """

    name = "email_validator"

    def __init__(self) -> None:
        try:
            import email_validator as _ev
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "email_validator is not installed; run with "
                "`uv run --with email-validator` (it is a dev/test-only dep)."
            ) from exc
        self._ev = _ev

    def parse(self, text: str) -> Verdict:
        try:
            # check_deliverability=False -> syntax only, no DNS/MX lookup.
            info = self._ev.validate_email(text, check_deliverability=False)
        except Exception as exc:  # noqa: BLE001 - reference boundary
            return Verdict(accepted=False, detail=type(exc).__name__)
        normalised = getattr(info, "normalized", None) or getattr(
            info, "email", None
        )
        return Verdict(accepted=True, normalised=normalised)


def default_references(*, include_email_validator: bool = True) -> list[Reference]:
    """Return the reference list, optionally skipping ``email_validator``.

    The harness degrades gracefully: if ``email_validator`` is not installed
    (e.g. a bare ``pytest`` run without ``uv --with``), the other two
    references still run.
    """
    refs: list[Reference] = [StdlibParseaddr(), StdlibAddress()]
    if include_email_validator:
        with contextlib.suppress(RuntimeError):
            refs.append(EmailValidator())
    return refs
