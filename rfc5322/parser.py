"""RFC 5322 conformant email address parser.

Implements the ``addr-spec`` / ``mailbox`` / ``group`` grammar of RFC 5322
sections 3.2 through 3.4, plus the obsolete productions of section 4.4.

The parser is a hand-written recursive-descent parser over the raw character
stream.  It does **not** use :mod:`email.utils` or any regular expression for
grammar recognition; every production is recognised explicitly so that the
obsolete forms can be accepted or rejected independently.

Public API
----------
``parse_address(text, *, strict=True) -> Address``
    Parse a single ``address`` (mailbox or group) and return an immutable
    :class:`Address`.
``is_valid_address(text, *, strict=True) -> bool``
    Convenience predicate that swallows :class:`AddressSyntaxError`.
``parse_address_list(text, *, strict=True) -> tuple[Address, ...]``
    Parse an RFC 5322 ``address-list``.
``parse_mailbox_list(text, *, strict=True) -> tuple[Address, ...]``
    Parse an RFC 5322 ``mailbox-list`` (no groups).

Immutability: :class:`Address` is a frozen, slotted dataclass.  No input is
ever mutated; the parser only reads ``text``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

__all__ = [
    "Address",
    "AddressSyntaxError",
    "parse_address",
    "is_valid_address",
    "parse_address_list",
    "parse_mailbox_list",
]

# ---------------------------------------------------------------------------
# Character classes (RFC 5234 core rules + RFC 5322 terminal productions)
# ---------------------------------------------------------------------------

# RFC 5234 §2.3
_ALPHA: Final = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)
_DIGIT: Final = frozenset("0123456789")
_VCHAR: Final = frozenset(chr(c) for c in range(0x21, 0x7F))
_WSP: Final = frozenset(" \t")
_CRLF: Final = "\r\n"

# RFC 5322 §3.2.3
_ATEXT: Final = frozenset(
    "!#$%&'*+-/=?^_`{|}~"
) | _ALPHA | _DIGIT

# qtext = %d33 / %d35-91 / %d93-126
_QTEXT: Final = frozenset(chr(0x21)) | frozenset(
    chr(c) for c in range(0x23, 0x5C)
) | frozenset(chr(c) for c in range(0x5D, 0x7F))

# ctext = %d33-39 / %d42-91 / %d93-126
_CTEXT: Final = frozenset(chr(c) for c in range(0x21, 0x28)) | frozenset(
    chr(c) for c in range(0x2A, 0x5C)
) | frozenset(chr(c) for c in range(0x5D, 0x7F))

# dtext = %d33-90 / %d94-126  (printable, excluding "[", "]", "\")
_DTEXT: Final = frozenset(chr(c) for c in range(0x21, 0x5B)) | frozenset(
    chr(c) for c in range(0x5E, 0x7F)
)

# obs-NO-WS-CTL = %d1-8 / %d11 / %d12 / %d14-31 / %d127
_OBS_NO_WS_CTL: Final = (
    frozenset(chr(c) for c in range(0x01, 0x09))
    | frozenset(chr(c) for c in (0x0B, 0x0C))
    | frozenset(chr(c) for c in range(0x0E, 0x20))
    | frozenset(chr(0x7F))
)


# RFC 5322 §2.1.1 line length limit (excluding CRLF).
MAX_LINE_LENGTH: Final = 998
# RFC 5321 §4.5.3.1.1 local-part limit.
MAX_LOCAL_PART_LENGTH: Final = 64
# RFC 1035 §2.3.4 / RFC 5321 domain label limit.
MAX_LABEL_LENGTH: Final = 63


class AddressSyntaxError(ValueError):
    """Raised when ``text`` is not a valid RFC 5322 address.

    Subclasses :class:`ValueError` so callers that only guard ``ValueError``
    keep working, while precise callers can catch this type.
    """

    def __init__(self, message: str, *, position: int = 0, text: str = "") -> None:
        self.position = position
        self.text = text
        caret = ""
        if text:
            caret = f"\n  {text}\n  {' ' * position}^"
        super().__init__(f"{message} (offset {position}){caret}")


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Address:
    """An immutable parsed RFC 5322 address.

    Attributes
    ----------
    local_part:
        Semantic local part.  For a ``dot-atom`` this is the literal text; for
        a ``quoted-string`` the surrounding quotes are removed, ``quoted-pair``
        escapes are decoded and folding whitespace is collapsed to one space.
    domain:
        Semantic domain.  A ``dot-atom`` domain is returned without CFWS; a
        ``domain-literal`` is returned including its ``[`` ``]`` brackets.
    display_name:
        Decoded ``phrase`` for ``name-addr`` / ``group``, else ``None``.
    comments:
        Every CFWS comment encountered, in source order, decoded.
    source:
        The exact input string that produced this address.
    is_group:
        ``True`` when the address was a ``group`` production.
    group_members:
        Member addresses when ``is_group`` is ``True`` (empty otherwise).
    obsolete:
        ``True`` when any §4.4 obsolete production was used to accept input.
    """

    local_part: str
    domain: str
    display_name: str | None = None
    comments: tuple[str, ...] = ()
    source: str = ""
    is_group: bool = False
    group_members: tuple[Address, ...] = ()
    obsolete: bool = False

    @property
    def normalized(self) -> str:
        """Return a canonical string for this address.

        For a mailbox this is ``local_part@domain``.  For a group it is the
        canonical ``display-name:member, member;`` form.
        """
        if self.is_group:
            inner = ", ".join(m.normalized for m in self.group_members)
            return f"{self.display_name or ''}:{inner};"
        return f"{self.local_part}@{self.domain}"

    @property
    def addr_spec(self) -> str:
        """Alias for :attr:`normalized` (RFC 5322 §3.4.1 terminology)."""
        return self.normalized


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


@dataclass
class _Mark:
    pos: int
    comments: int
    obsolete: bool
    cfws_events: int


class _Parser:
    """Single-use recursive-descent parser over ``text``."""

    def __init__(self, text: str, *, strict: bool) -> None:
        self.text = text
        self.n = len(text)
        self.pos = 0
        self.strict = strict
        self.comments: list[str] = []
        self.obsolete = False
        self.cfws_events = 0
        self.trailing_cfws = False
        self._last_word_quoted = False

    # -- cursor helpers -----------------------------------------------------

    def _eof(self) -> bool:
        return self.pos >= self.n

    def _peek(self, offset: int = 0) -> str:
        i = self.pos + offset
        return self.text[i] if i < self.n else ""

    def _mark(self) -> _Mark:
        return _Mark(self.pos, len(self.comments), self.obsolete, self.cfws_events)

    def _restore(self, m: _Mark) -> None:
        self.pos = m.pos
        del self.comments[m.comments :]
        self.obsolete = m.obsolete
        self.cfws_events = m.cfws_events

    def _fail(self, message: str) -> AddressSyntaxError:
        return AddressSyntaxError(message, position=self.pos, text=self.text)

    def _expect(self, literal: str) -> None:
        if self.text.startswith(literal, self.pos):
            self.pos += len(literal)
        else:
            raise self._fail(f"expected {literal!r}")

    def _note_obsolete(self, what: str) -> None:
        if self.strict:
            raise self._fail(f"obsolete production {what} rejected in strict mode")
        self.obsolete = True

    # -- §3.2.2 FWS / obs-FWS ----------------------------------------------

    def _parse_fws(self) -> bool:
        """Consume ``FWS`` (or ``obs-FWS`` when non-strict).  Returns consumed."""
        start = self.pos
        while True:
            w = 0
            while self._peek() in _WSP:
                self.pos += 1
                w += 1
            if self.text.startswith(_CRLF, self.pos):
                after = self.pos + 2
                if after < self.n and self.text[after] in _WSP:
                    if w == 0 and not self.strict:
                        # obs-FWS allows WSP before CRLF; strict FWS requires
                        # at least one WSP *after* the CRLF, which we check next.
                        pass
                    self.pos = after
                    continue
                # CRLF not followed by WSP is not a fold; leave it.
                break
            break
        return self.pos != start

    def _at_fold(self) -> bool:
        """True if a CRLF folding sequence starts at the cursor."""
        return self.text.startswith(_CRLF, self.pos) and (
            self.pos + 2 < self.n and self.text[self.pos + 2] in _WSP
        )

    # -- §3.2.3 CFWS / comments --------------------------------------------

    def _parse_comment(self) -> str:
        """Parse one ``comment``; return its decoded content."""
        self._expect("(")
        parts: list[str] = []
        while True:
            if self._eof():
                raise self._fail("unterminated comment")
            ch = self._peek()
            if ch == ")":
                self.pos += 1
                break
            if ch == "(":
                parts.append(self._parse_comment())
                continue
            if ch == "\\":
                parts.append(self._parse_quoted_pair())
                continue
            if ch in _WSP or self._at_fold():
                if self._parse_fws():
                    parts.append(" ")
                continue
            if ch in _CTEXT:
                parts.append(ch)
                self.pos += 1
                continue
            if ch in _OBS_NO_WS_CTL:
                self._note_obsolete("obs-ctext")
                parts.append(ch)
                self.pos += 1
                continue
            raise self._fail("illegal character in comment")
        return "".join(parts)

    def _parse_cfws(self) -> bool:
        """Consume ``CFWS`` (zero or more folds/comments).  Returns consumed."""
        consumed = False
        while True:
            progressed = False
            if self._parse_fws():
                progressed = consumed = True
            if self._peek() == "(":
                self.comments.append(self._parse_comment())
                progressed = consumed = True
            if not progressed:
                break
        if consumed:
            self.cfws_events += 1
        return consumed

    # -- §3.2.1 quoted-pair -------------------------------------------------

    def _parse_quoted_pair(self) -> str:
        """Parse ``"\\" (VCHAR / WSP)`` or obs-qp; return the escaped char."""
        if self._peek() != "\\":
            raise self._fail("expected backslash")
        self.pos += 1
        if self._eof():
            raise self._fail("trailing backslash")
        ch = self._peek()
        if ch in _VCHAR or ch in _WSP:
            self.pos += 1
            return ch
        if ch in _OBS_NO_WS_CTL or ch in ("\r", "\n", "\x00"):
            self._note_obsolete("obs-qp")
            self.pos += 1
            return ch
        raise self._fail("illegal character after backslash")

    # -- §3.2.4 quoted-string ----------------------------------------------

    def _parse_quoted_string(self) -> str:
        """Parse ``quoted-string``; return decoded content without quotes."""
        self._parse_cfws()
        self._expect('"')
        parts: list[str] = []
        while True:
            if self._eof():
                raise self._fail("unterminated quoted-string")
            ch = self._peek()
            if ch == '"':
                self.pos += 1
                break
            if ch == "\\":
                parts.append(self._parse_quoted_pair())
                continue
            if ch in _WSP or self._at_fold():
                if self._parse_fws():
                    parts.append(" ")
                continue
            if ch in _QTEXT:
                parts.append(ch)
                self.pos += 1
                continue
            if ch in _OBS_NO_WS_CTL:
                self._note_obsolete("obs-qtext")
                parts.append(ch)
                self.pos += 1
                continue
            raise self._fail("illegal character in quoted-string")
        self.trailing_cfws = self._parse_cfws()
        return "".join(parts)

    # -- §3.2.3 atoms -------------------------------------------------------

    def _parse_atom(self) -> str:
        """Parse ``atom = [CFWS] 1*atext [CFWS]``."""
        self._parse_cfws()
        start = self.pos
        while self._peek() in _ATEXT:
            self.pos += 1
        if self.pos == start:
            raise self._fail("expected atext")
        text = self.text[start : self.pos]
        self.trailing_cfws = self._parse_cfws()
        return text

    def _parse_dot_atom_text(self) -> str:
        """Parse ``dot-atom-text = 1*atext *("." 1*atext)`` (no CFWS)."""
        start = self.pos
        while self._peek() in _ATEXT:
            self.pos += 1
        if self.pos == start:
            raise self._fail("expected atext")
        while self._peek() == ".":
            dot = self.pos
            self.pos += 1
            seg = self.pos
            while self._peek() in _ATEXT:
                self.pos += 1
            if self.pos == seg:
                self.pos = dot
                break
        return self.text[start : self.pos]

    def _parse_dot_atom(self) -> str:
        """Parse ``dot-atom = [CFWS] dot-atom-text [CFWS]``."""
        self._parse_cfws()
        text = self._parse_dot_atom_text()
        self._parse_cfws()
        return text

    # -- §3.4.1 local-part / domain ----------------------------------------

    def _parse_local_part(self) -> str:
        """Parse ``local-part`` honouring strict/obsolete rules."""
        if not self.strict:
            # obs-local-part = word *("." word)
            self._parse_cfws()
            words: list[str] = []
            quoted = 0
            word = self._parse_word()
            if self._last_word_quoted:
                quoted += 1
            words.append(word)
            while True:
                m = self._mark()
                self._parse_cfws()
                if self._peek() == ".":
                    self.pos += 1
                    try:
                        word = self._parse_word()
                    except AddressSyntaxError:
                        self._restore(m)
                        break
                    if self._last_word_quoted:
                        quoted += 1
                    words.append(word)
                    continue
                self._restore(m)
                break
            # A lone quoted-string is the modern form; mixing words and dots
            # (or multiple quoted strings) is the §4.4 obsolete production.
            if quoted and (len(words) > 1 or quoted > 1):
                self.obsolete = True
            return ".".join(words)
        if self._peek() == '"' or self._looks_like_quoted_string():
            return self._parse_quoted_string()
        return self._parse_dot_atom()

    def _looks_like_quoted_string(self) -> bool:
        m = self._mark()
        try:
            self._parse_cfws()
            return self._peek() == '"'
        finally:
            self._restore(m)

    def _parse_word(self) -> str:
        """``word = atom / quoted-string``."""
        if self._looks_like_quoted_string():
            self._last_word_quoted = True
            return self._parse_quoted_string()
        self._last_word_quoted = False
        return self._parse_atom()

    def _parse_domain_literal(self) -> str:
        """Parse ``domain-literal``; returns text including brackets."""
        self._parse_cfws()
        self._expect("[")
        parts: list[str] = []
        while True:
            if self._eof():
                raise self._fail("unterminated domain-literal")
            ch = self._peek()
            if ch == "]":
                self.pos += 1
                break
            if ch == "\\":
                if self.strict:
                    raise self._fail("quoted-pair in dtext is obs-dtext (strict)")
                self._note_obsolete("obs-dtext")
                parts.append(self._parse_quoted_pair())
                continue
            if ch in _WSP or self._at_fold():
                if self._parse_fws():
                    parts.append(" ")
                continue
            if ch in _DTEXT:
                parts.append(ch)
                self.pos += 1
                continue
            if ch in _OBS_NO_WS_CTL:
                self._note_obsolete("obs-dtext")
                parts.append(ch)
                self.pos += 1
                continue
            raise self._fail("illegal character in domain-literal")
        self._parse_cfws()
        return "[" + "".join(parts) + "]"

    def _parse_domain(self) -> str:
        """Parse ``domain`` honouring strict/obsolete rules."""
        m = self._mark()
        self._parse_cfws()
        if self._peek() == "[":
            self._restore(m)
            return self._parse_domain_literal()
        self._restore(m)
        if not self.strict:
            # obs-domain = atom *("." atom)
            parts = [self._parse_atom()]
            while True:
                m = self._mark()
                self._parse_cfws()
                if self._peek() == ".":
                    self.pos += 1
                    try:
                        parts.append(self._parse_atom())
                        continue
                    except AddressSyntaxError:
                        self._restore(m)
                        break
                self._restore(m)
                break
            return ".".join(parts)
        return self._parse_dot_atom()

    def _parse_addr_spec(self) -> tuple[str, str]:
        """Parse ``addr-spec = local-part "@" domain``."""
        local = self._parse_local_part()
        m = self._mark()
        self._parse_cfws()
        if self._peek() != "@":
            self._restore(m)
            raise self._fail("expected '@' in addr-spec")
        self.pos += 1
        self._restore(m)
        # consume local-part trailing CFWS + '@' + leading CFWS of domain
        self._parse_cfws()
        self._expect("@")
        domain = self._parse_domain()
        return local, domain

    # -- §3.2.5 phrase ------------------------------------------------------

    def _parse_phrase(self) -> str:
        """Parse ``phrase = 1*word`` (obs-phrase when non-strict).

        Words are separated by CFWS; a single space is emitted for any CFWS
        boundary so that ``A  Group`` (or a comment between words) yields the
        display name ``A Group`` rather than ``AGroup``.
        """
        m0 = self._mark()
        words: list[str] = [self._parse_word()]
        while True:
            m = self._mark()
            had_ws = self.trailing_cfws
            self._parse_cfws()
            if self._peek() == '"' or self._peek() in _ATEXT:
                if had_ws:
                    words.append(" ")
                words.append(self._parse_word())
                continue
            if not self.strict and self._peek() == ".":
                self.pos += 1
                self.obsolete = True
                words.append(".")
                self.trailing_cfws = True
                continue
            self._restore(m)
            break
        text = "".join(words).strip()
        if not text:
            self._restore(m0)
            raise self._fail("expected phrase")
        return text

    # -- §3.4.1 angle-addr / obs-route -------------------------------------

    def _parse_angle_addr(self) -> tuple[str, str]:
        """Parse ``angle-addr`` / ``obs-angle-addr``; return (local, domain)."""
        self._parse_cfws()
        self._expect("<")
        self._parse_cfws()
        if self._peek() == "@":
            # obs-angle-addr = [CFWS] "<" obs-route addr-spec ">" [CFWS]
            self._note_obsolete("obs-angle-addr / obs-route")
            while True:
                self._expect("@")
                self._parse_domain()
                self._parse_cfws()
                if self._peek() == ",":
                    self.pos += 1
                    self._parse_cfws()
                    continue
                break
            self._expect(":")
            self._parse_cfws()
        local, domain = self._parse_addr_spec()
        self._parse_cfws()
        self._expect(">")
        self._parse_cfws()
        return local, domain

    # -- §3.4 mailbox / group ----------------------------------------------

    def _parse_mailbox(self, source: str) -> Address:
        """Parse ``mailbox`` (``name-addr`` or bare ``addr-spec``)."""
        if self._peek() == "<" or self._looks_like_angle_addr():
            local, domain = self._parse_angle_addr()
            display = self._pending_display
            self._pending_display = None
            return self._make(source, local, domain, display)
        m = self._mark()
        try:
            display = self._parse_phrase()
        except AddressSyntaxError:
            self._restore(m)
            local, domain = self._parse_addr_spec()
            return self._make(source, local, domain, None)
        m2 = self._mark()
        self._parse_cfws()
        if self._peek() == "<":
            self._restore(m2)
            self._pending_display = display
            local, domain = self._parse_angle_addr()
            self._pending_display = None
            return self._make(source, local, domain, display)
        self._restore(m)
        local, domain = self._parse_addr_spec()
        return self._make(source, local, domain, None)

    def _looks_like_angle_addr(self) -> bool:
        m = self._mark()
        try:
            self._parse_cfws()
            return self._peek() == "<"
        finally:
            self._restore(m)

    def _parse_group(self, source: str) -> Address | None:
        """Parse ``group`` or return ``None`` if the input is not a group."""
        m = self._mark()
        try:
            display = self._parse_phrase()
        except AddressSyntaxError:
            self._restore(m)
            return None
        self._parse_cfws()
        if self._peek() != ":":
            self._restore(m)
            return None
        self.pos += 1
        members: list[Address] = []
        self._parse_cfws()
        if self._peek() == ";":
            self.pos += 1
            self._parse_cfws()
            return self._make_group(source, display, members)
        # group-list = mailbox-list / CFWS / obs-group-list
        if self.strict:
            if self._peek() == ",":
                self._restore(m)
                return None
        else:
            # obs-group-list = 1*([CFWS] ",") [CFWS]
            while True:
                mm = self._mark()
                self._parse_cfws()
                if self._peek() == ",":
                    self.pos += 1
                    self.obsolete = True
                    self._parse_cfws()
                    continue
                self._restore(mm)
                break
            if self._peek() == ";":
                self.pos += 1
                self._parse_cfws()
                return self._make_group(source, display, members)
        while True:
            self._parse_cfws()
            if self._peek() == ";":
                self.pos += 1
                self._parse_cfws()
                break
            if self._eof():
                self._restore(m)
                return None
            member = self._parse_mailbox(self.text)
            members.append(member)
            self._parse_cfws()
            if self._peek() == ",":
                self.pos += 1
                self._parse_cfws()
                if self._peek() == ";" and self.strict:
                    # group-list = mailbox-list / CFWS / obs-group-list; a
                    # trailing comma before ";" is not part of any of these.
                    raise self._fail("trailing comma in group-list")
                continue
            if self._peek() == ";":
                self.pos += 1
                self._parse_cfws()
                break
            self._restore(m)
            return None
        return self._make_group(source, display, members)

    # -- builders -----------------------------------------------------------

    _pending_display: str | None = None

    def _make(
        self, source: str, local: str, domain: str, display: str | None
    ) -> Address:
        return Address(
            local_part=local,
            domain=domain,
            display_name=display,
            comments=tuple(self.comments),
            source=source,
            obsolete=self.obsolete,
        )

    def _make_group(
        self, source: str, display: str, members: list[Address]
    ) -> Address:
        return Address(
            local_part="",
            domain="",
            display_name=display,
            comments=tuple(self.comments),
            source=source,
            is_group=True,
            group_members=tuple(members),
            obsolete=self.obsolete,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _finish(p: _Parser, source: str) -> None:
    p._parse_cfws()
    if not p._eof():
        raise p._fail(f"unexpected trailing input {source[p.pos:]!r}")


def _validate_lengths(addr: Address) -> None:
    """Enforce the practical length limits an RFC 5322 address must satisfy.

    RFC 5322 §2.1.1 caps a line at 998 characters; RFC 5321 §4.5.3.1.1 caps
    the local part at 64 characters and the domain at 255, with each DNS label
    at most 63 (RFC 1035 §2.3.4).  These are the limits the originating issue
    calls out explicitly.
    """
    if len(addr.source) > MAX_LINE_LENGTH:
        raise AddressSyntaxError(
            f"address exceeds {MAX_LINE_LENGTH} characters",
            position=MAX_LINE_LENGTH,
            text=addr.source,
        )
    if addr.is_group:
        for member in addr.group_members:
            _validate_lengths(member)
        return
    if len(addr.local_part) > MAX_LOCAL_PART_LENGTH:
        raise AddressSyntaxError(
            f"local-part exceeds {MAX_LOCAL_PART_LENGTH} characters",
            position=MAX_LOCAL_PART_LENGTH,
            text=addr.source,
        )
    domain = addr.domain
    if domain.startswith("[") and domain.endswith("]"):
        return  # domain-literal: RFC 5322 places no length limit on dtext.
    if len(domain) > 255:
        raise AddressSyntaxError(
            "domain exceeds 255 characters", position=0, text=addr.source
        )
    for label in domain.split("."):
        if len(label) > MAX_LABEL_LENGTH:
            raise AddressSyntaxError(
                f"domain label exceeds {MAX_LABEL_LENGTH} characters",
                position=0,
                text=addr.source,
            )


def _infer_obsolete(text: str, addr: Address) -> Address:
    """Set ``obsolete=True`` when the input is only valid under §4.4.

    ``strict=False`` enables the obsolete productions; a given input may still
    be purely modern.  Rather than guess which production fired, we settle the
    question empirically: if the same text is *rejected* by the strict grammar
    then an obsolete production was required, so the flag must be set.  This
    keeps the documented invariant ``accepted only under strict=False =>
    Address.obsolete is True`` true for every production, including the ones
    that are recognised but do not currently call :meth:`_note_obsolete`.
    """
    if addr.obsolete:
        return addr
    try:
        parse_address(text, strict=True)
    except AddressSyntaxError:
        return replace(addr, obsolete=True)
    return addr


def parse_address(text: str, *, strict: bool = True) -> Address:
    """Parse a single RFC 5322 ``address`` (a mailbox or a group).

    Parameters
    ----------
    text:
        The raw address text.  Must be a :class:`str`.
    strict:
        When ``True`` (default) the §4.4 obsolete productions are rejected.
        When ``False`` they are accepted and :attr:`Address.obsolete` is set.

    Raises
    ------
    TypeError
        If ``text`` is not a :class:`str`.
    AddressSyntaxError
        If ``text`` is not a valid address.
    """
    if not isinstance(text, str):
        raise TypeError(f"address must be str, got {type(text).__name__}")
    if not text.strip():
        raise AddressSyntaxError("empty address", position=0, text=text)
    p = _Parser(text, strict=strict)
    group = p._parse_group(text)
    if group is not None:
        _finish(p, text)
        _validate_lengths(group)
        return group if strict else _infer_obsolete(text, group)
    p = _Parser(text, strict=strict)
    addr = p._parse_mailbox(text)
    _finish(p, text)
    _validate_lengths(addr)
    return addr if strict else _infer_obsolete(text, addr)


def is_valid_address(text: str, *, strict: bool = True) -> bool:
    """Return ``True`` iff ``text`` parses as a single RFC 5322 address."""
    try:
        parse_address(text, strict=strict)
    except (AddressSyntaxError, TypeError):
        return False
    return True


def parse_address_list(text: str, *, strict: bool = True) -> tuple[Address, ...]:
    """Parse an RFC 5322 ``address-list`` (comma-separated addresses)."""
    if not isinstance(text, str):
        raise TypeError(f"address list must be str, got {type(text).__name__}")
    if not text.strip():
        raise AddressSyntaxError("empty address list", position=0, text=text)
    p = _Parser(text, strict=strict)
    out: list[Address] = []
    p._parse_cfws()
    # obs-addr-list = *([CFWS] ",") address *("," [address / CFWS])
    if not strict:
        while True:
            m = p._mark()
            p._parse_cfws()
            if p._peek() == ",":
                p.pos += 1
                p.obsolete = True
                continue
            p._restore(m)
            break
    while True:
        p._parse_cfws()
        if p._eof():
            break
        group = p._parse_group(text)
        if group is not None:
            out.append(group)
        else:
            out.append(p._parse_mailbox(text))
        p._parse_cfws()
        if p._peek() == ",":
            p.pos += 1
            p._parse_cfws()
            if p._eof():
                if strict:
                    raise p._fail("trailing comma in address-list")
                p.obsolete = True
                break
            continue
        break
    _finish(p, text)
    if not strict and _list_requires_obsolete(text, kind="address"):
        out = [replace(a, obsolete=True) for a in out]
    return tuple(out)


def _list_requires_obsolete(text: str, *, kind: str) -> bool:
    """Return ``True`` if ``text`` is not a valid list under the strict grammar.

    Used by the permissive list parsers to decide whether §4.4 syntax was
    required.  ``kind`` is ``"address"`` or ``"mailbox"``.  A strict parse
    never recurses into this probe, so there is no infinite regress.
    """
    fn = parse_address_list if kind == "address" else parse_mailbox_list
    try:
        fn(text, strict=True)
    except AddressSyntaxError:
        return True
    return False


def parse_mailbox_list(text: str, *, strict: bool = True) -> tuple[Address, ...]:
    """Parse an RFC 5322 ``mailbox-list`` (no groups allowed)."""
    if not isinstance(text, str):
        raise TypeError(f"mailbox list must be str, got {type(text).__name__}")
    if not text.strip():
        raise AddressSyntaxError("empty mailbox list", position=0, text=text)
    p = _Parser(text, strict=strict)
    out: list[Address] = []
    p._parse_cfws()
    # obs-mbox-list = *([CFWS] ",") mailbox *("," [mailbox / CFWS])
    if not strict:
        while True:
            m = p._mark()
            p._parse_cfws()
            if p._peek() == ",":
                p.pos += 1
                p.obsolete = True
                continue
            p._restore(m)
            break
    while True:
        p._parse_cfws()
        if p._eof():
            break
        out.append(p._parse_mailbox(text))
        p._parse_cfws()
        if p._peek() == ",":
            p.pos += 1
            p._parse_cfws()
            if p._eof():
                if strict:
                    raise p._fail("trailing comma in mailbox-list")
                p.obsolete = True
                break
            continue
        break
    _finish(p, text)
    if not strict and _list_requires_obsolete(text, kind="mailbox"):
        out = [replace(a, obsolete=True) for a in out]
    return tuple(out)
