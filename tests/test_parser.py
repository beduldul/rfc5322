"""Test suite for the RFC 5322 address parser.

Organised by RFC 5322 section, mirroring the acceptance criteria of the
originating issue.  Contains well over 150 individual assertions across
parametrised cases.

Where the stdlib :func:`email.utils.parseaddr` is known to disagree with
RFC 5322, a test documents the discrepancy (see ``TestStdlibDivergence``).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from rfc5322 import (
    Address,
    AddressSyntaxError,
    is_valid_address,
    parse_address,
    parse_address_list,
    parse_mailbox_list,
)

# ---------------------------------------------------------------------------
# §3.2.5 / §3.4.1 — simple addr-spec
# ---------------------------------------------------------------------------

SIMPLE_VALID = [
    "user@example.com",
    "user@example",
    "a@b.co",
    "john.doe@example.com",
    "user+tag@example.com",
    "user-name@example.com",
    "user_name@example.com",
    "user%name@example.com",
    "user&name@example.com",
    "user'name@example.com",
    "user/name@example.com",
    "user=name@example.com",
    "user?name@example.com",
    "user^name@example.com",
    "user`name@example.com",
    "user{name}@example.com",
    "user|name@example.com",
    "user~name@example.com",
    "user!name@example.com",
    "user#name@example.com",
    "user$name@example.com",
    "user*name@example.com",
    "1234567890@example.com",
    "a.b.c.d.e.f@example.com",
    "x@y.z",
    "USER@EXAMPLE.COM",
    "u@sub.domain.example.co.uk",
]


@pytest.mark.parametrize("text", SIMPLE_VALID)
def test_simple_valid(text: str) -> None:
    addr = parse_address(text)
    assert addr.normalized == text
    assert addr.is_group is False
    assert addr.display_name is None


def test_addr_spec_parts() -> None:
    addr = parse_address("john.doe@example.com")
    assert addr.local_part == "john.doe"
    assert addr.domain == "example.com"
    assert addr.addr_spec == "john.doe@example.com"


def test_address_is_frozen() -> None:
    addr = parse_address("a@b.com")
    with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
        addr.local_part = "mutated"  # type: ignore[misc]


def test_address_is_hashable() -> None:
    assert len({parse_address("a@b.com"), parse_address("a@b.com")}) == 1


# ---------------------------------------------------------------------------
# §3.2.4 — quoted-string local parts
# ---------------------------------------------------------------------------

QUOTED_VALID = [
    '"john doe"@example.com',
    '"john..doe"@example.com',
    '""@example.com',
    '" "@example.com',
    '"a b c"@example.com',
    '"john@doe"@example.com',
    '"john\\"doe"@example.com',
    '"john\\\\doe"@example.com',
    # The exact example from RFC 5322 §3.4.1: a single quoted-string whose
    # content contains escaped quotes, a backslash and an unescaped space.
    '"very.(),:;<>[]\\".VERY.\\"very@\\\\ \\"very\\".unusual"@strange.example.com',
    '"much.more unusual"@example.com',
    '"a.b"@example.com',
    '"..."@example.com',
    '"\\a"@example.com',
]


@pytest.mark.parametrize("text", QUOTED_VALID)
def test_quoted_valid(text: str) -> None:
    assert is_valid_address(text)


def test_quoted_local_part_decodes() -> None:
    assert parse_address('"john doe"@example.com').local_part == "john doe"


def test_quoted_local_part_keeps_dots() -> None:
    assert parse_address('"john..doe"@example.com').local_part == "john..doe"


def test_quoted_escaped_quote_decodes() -> None:
    assert parse_address('"john\\"doe"@example.com').local_part == 'john"doe'


def test_quoted_escaped_backslash_decodes() -> None:
    assert parse_address('"john\\\\doe"@example.com').local_part == "john\\doe"


def test_quoted_empty_local_part() -> None:
    assert parse_address('""@example.com').local_part == ""


def test_quoted_space_local_part() -> None:
    assert parse_address('" "@example.com').local_part == " "


# ---------------------------------------------------------------------------
# §3.2.3 — CFWS and comments
# ---------------------------------------------------------------------------


def test_leading_comment() -> None:
    addr = parse_address("(comment)john@example.com")
    assert addr.local_part == "john"
    assert addr.comments == ("comment",)


def test_trailing_comment() -> None:
    addr = parse_address("john@example.com(comment)")
    assert addr.domain == "example.com"
    assert addr.comments == ("comment",)


def test_comment_between_parts() -> None:
    addr = parse_address("(a)john(b)@(c)example.com(d)")
    assert addr.local_part == "john"
    assert addr.domain == "example.com"
    assert addr.comments == ("a", "b", "c", "d")


def test_nested_comments() -> None:
    addr = parse_address("(outer(inner)rest)john@example.com")
    assert addr.comments == ("outerinnerrest",)


def test_deeply_nested_comments() -> None:
    addr = parse_address("(a(b(c)d)e)john@example.com")
    assert addr.comments == ("abcde",)


def test_comment_with_escaped_paren() -> None:
    addr = parse_address("(a\\)b)john@example.com")
    assert addr.comments == ("a)b",)


def test_comment_with_escaped_backslash() -> None:
    addr = parse_address("(a\\\\b)john@example.com")
    assert addr.comments == ("a\\b",)


def test_multiple_comments_ordering() -> None:
    addr = parse_address("(1)john(2)@(3)example.com(4)")
    assert addr.comments == ("1", "2", "3", "4")


def test_comment_only_before_at() -> None:
    assert parse_address("john(comment)@example.com").comments == ("comment",)


def test_trailing_cfws_is_valid() -> None:
    # RFC 5322 §3.2.3: addr-spec = local-part "@" domain, and both dot-atom
    # and domain-literal permit trailing [CFWS].  So "user @x.com " is legal.
    addr = parse_address("user @example.com ")
    assert addr.normalized == "user@example.com"


def test_empty_domain_literal_is_legal() -> None:
    # domain-literal = [CFWS] "[" *([FWS] dtext) [FWS] "]" [CFWS]
    # dtext is zero-or-more, so "[]" is a valid domain-literal.
    assert parse_address("user@[]").domain == "[]"


def test_empty_comment() -> None:
    addr = parse_address("()john@example.com")
    assert addr.comments == ("",)


def test_comment_containing_at_sign() -> None:
    addr = parse_address("(a@b)john@example.com")
    assert addr.local_part == "john"
    assert addr.comments == ("a@b",)


# ---------------------------------------------------------------------------
# §3.2.2 — folding whitespace
# ---------------------------------------------------------------------------


def test_fws_around_at() -> None:
    addr = parse_address("john @ example.com")
    assert addr.normalized == "john@example.com"


def test_fws_fold_before_at() -> None:
    addr = parse_address("john\r\n @example.com")
    assert addr.normalized == "john@example.com"


def test_fws_fold_after_at() -> None:
    addr = parse_address("john@\r\n example.com")
    assert addr.normalized == "john@example.com"


def test_fws_multiple_folds() -> None:
    addr = parse_address("john\r\n @\r\n example.com")
    assert addr.normalized == "john@example.com"


def test_fws_tab() -> None:
    assert parse_address("john\t@\texample.com").normalized == "john@example.com"


def test_fws_fold_inside_comment() -> None:
    addr = parse_address("(a\r\n b)john@example.com")
    assert addr.comments == ("a b",)


def test_fws_fold_inside_quoted_string() -> None:
    addr = parse_address('"a\r\n b"@example.com')
    assert addr.local_part == "a b"


# ---------------------------------------------------------------------------
# §3.4.1 — domain literals
# ---------------------------------------------------------------------------

DOMAIN_LITERAL_VALID = [
    "user@[192.0.2.1]",
    "user@[192.168.1.1]",
    "user@[IPv6:2001:db8::1]",
    "user@[IPv6:2001:db8:85a3::8a2e:370:7334]",
    "postmaster@[IPv6:2001:db8:85a3::8a2e:370:7334]",
    "user@[127.0.0.1]",
    "user@[10.0.0.1]",
    "user@[IPv6:::1]",
    "user@[example]",
]


@pytest.mark.parametrize("text", DOMAIN_LITERAL_VALID)
def test_domain_literal_valid(text: str) -> None:
    assert is_valid_address(text)


def test_domain_literal_keeps_brackets() -> None:
    addr = parse_address("user@[192.0.2.1]")
    assert addr.domain == "[192.0.2.1]"
    assert addr.local_part == "user"


def test_domain_literal_ipv6() -> None:
    assert parse_address("user@[IPv6:2001:db8::1]").domain == "[IPv6:2001:db8::1]"


def test_domain_literal_with_fws() -> None:
    assert parse_address("user@[ 192.0.2.1 ]").domain == "[ 192.0.2.1 ]"


# ---------------------------------------------------------------------------
# §3.4 — mailbox / name-addr / group
# ---------------------------------------------------------------------------


def test_name_addr_simple() -> None:
    addr = parse_address("John Doe <john@example.com>")
    assert addr.display_name == "John Doe"
    assert addr.normalized == "john@example.com"


def test_name_addr_quoted_display() -> None:
    addr = parse_address('"John Doe" <john@example.com>')
    assert addr.display_name == "John Doe"


def test_name_addr_angle_only() -> None:
    addr = parse_address("<john@example.com>")
    assert addr.display_name is None
    assert addr.normalized == "john@example.com"


def test_name_addr_with_comments() -> None:
    addr = parse_address("John Doe (comment) <john@example.com>")
    assert addr.display_name == "John Doe"
    assert addr.comments == ("comment",)


def test_name_addr_inside_angle_comment() -> None:
    addr = parse_address("John <(c)john@example.com>")
    assert addr.display_name == "John"
    assert addr.comments == ("c",)


def test_group_basic() -> None:
    addr = parse_address("A Group:user1@a.com, user2@b.com;")
    assert addr.is_group is True
    assert addr.display_name == "A Group"
    assert [m.normalized for m in addr.group_members] == ["user1@a.com", "user2@b.com"]


def test_group_empty() -> None:
    addr = parse_address("Group:;")
    assert addr.is_group is True
    assert addr.group_members == ()


def test_group_single_member() -> None:
    addr = parse_address("Friends:alice@example.com;")
    assert len(addr.group_members) == 1


def test_group_quoted_display() -> None:
    addr = parse_address('"My Group":a@b.com;')
    assert addr.display_name == "My Group"


def test_group_members_with_display_names() -> None:
    addr = parse_address("Team:Alice <a@x.com>, Bob <b@y.com>;")
    assert addr.display_name == "Team"
    assert [m.display_name for m in addr.group_members] == ["Alice", "Bob"]


def test_group_normalized() -> None:
    addr = parse_address("G:a@x.com, b@y.com;")
    assert addr.normalized == "G:a@x.com, b@y.com;"


def test_group_with_trailing_comment() -> None:
    addr = parse_address("G:a@x.com;(c)")
    assert addr.comments == ("c",)


# ---------------------------------------------------------------------------
# §3.4 — address lists
# ---------------------------------------------------------------------------


def test_address_list_two() -> None:
    out = parse_address_list("a@x.com, b@y.com")
    assert [a.normalized for a in out] == ["a@x.com", "b@y.com"]


def test_address_list_three() -> None:
    out = parse_address_list("a@x.com,b@y.com,c@z.com")
    assert len(out) == 3


def test_address_list_with_group() -> None:
    out = parse_address_list("G:a@x.com;, b@y.com")
    assert out[0].is_group
    assert out[1].normalized == "b@y.com"


def test_address_list_with_names() -> None:
    out = parse_address_list("Alice <a@x.com>, Bob <b@y.com>")
    assert [a.display_name for a in out] == ["Alice", "Bob"]


def test_mailbox_list_two() -> None:
    out = parse_mailbox_list("a@x.com, b@y.com")
    assert len(out) == 2


def test_mailbox_list_rejects_group() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_mailbox_list("G:a@x.com;")


def test_address_list_single() -> None:
    assert len(parse_address_list("a@x.com")) == 1


def test_address_list_trailing_comma_strict_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address_list("a@x.com,", strict=True)


def test_address_list_leading_comma_obsolete() -> None:
    out = parse_address_list(", a@x.com", strict=False)
    assert out[0].normalized == "a@x.com"


# ---------------------------------------------------------------------------
# §4.4 — obsolete addressing (permissive mode)
# ---------------------------------------------------------------------------

OBS_LOCAL_PART = [
    'user."quoted"@example.com',
    '"quoted".user@example.com',
    '"a"."b"@example.com',
    'a."b".c@example.com',
]

OBS_DOMAIN = [
    "user@example.com.",
    "user@[192.0.2.1]",
]


@pytest.mark.parametrize("text", OBS_LOCAL_PART)
def test_obs_local_part_permissive(text: str) -> None:
    addr = parse_address(text, strict=False)
    assert addr.obsolete is True


@pytest.mark.parametrize("text", OBS_LOCAL_PART)
def test_obs_local_part_strict_rejected(text: str) -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address(text, strict=True)


def test_obs_local_part_value() -> None:
    assert parse_address('user."quoted"@example.com', strict=False).local_part == "user.quoted"


def test_obs_local_part_both_quoted() -> None:
    assert parse_address('"a"."b"@example.com', strict=False).local_part == "a.b"


def test_obs_domain_atom_form() -> None:
    # obs-domain = atom *("." atom); atoms may carry CFWS.
    addr = parse_address("user@ example.com", strict=False)
    assert addr.domain == "example.com"


def test_obs_phrase_with_dot() -> None:
    addr = parse_address("John Q. Public <j@x.com>", strict=False)
    assert addr.display_name == "John Q. Public"


def test_obs_phrase_with_dot_strict_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("John Q. Public <j@x.com>", strict=True)


def test_obs_route_rejected_strict() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("<@a.com,@b.com:user@example.com>", strict=True)


def test_obs_route_permissive() -> None:
    addr = parse_address("<@a.com,@b.com:user@example.com>", strict=False)
    assert addr.normalized == "user@example.com"
    assert addr.obsolete is True


def test_obs_group_list_permissive() -> None:
    addr = parse_address("G:,,,;", strict=False)
    assert addr.is_group is True
    assert addr.obsolete is True


def test_obs_group_list_strict_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("G:,,,;", strict=True)


def test_obsolete_flag_false_for_modern() -> None:
    assert parse_address("a@b.com").obsolete is False


def test_obsolete_flag_false_for_quoted_local() -> None:
    assert parse_address('"a"@b.com').obsolete is False


# ---------------------------------------------------------------------------
# Edge cases: lengths, empty parts, unusual but legal
# ---------------------------------------------------------------------------


def test_max_local_part_length_accepted() -> None:
    local = "a" * 64
    assert parse_address(f"{local}@example.com").local_part == local


def test_long_line_998_chars() -> None:
    # A 998-character line must be parseable (RFC 5322 §2.1.1).  The domain is
    # kept within the 255-character DNS limit; the display-name phrase makes up
    # the remainder of the line.
    local = "a" * 64
    domain = ".".join(["d" * 63, "d" * 63, "d" * 63, "com"])  # 195 chars
    prefix = f" <{local}@{domain}>"  # 1 space + <> + 1 @
    phrase = "N" * (998 - len(prefix))
    text = f"{phrase}{prefix}"
    assert len(text) == 998
    addr = parse_address(text)
    assert addr.local_part == local
    assert addr.domain == domain


def test_over_long_line_1000_chars_rejected() -> None:
    local = "a" * 900
    domain = "b" * 100 + ".com"
    text = f"{local}@{domain}"
    assert len(text) > 998
    with pytest.raises(AddressSyntaxError):
        parse_address(text)


def test_very_long_local_part_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("a" * 65 + "@example.com")


def test_label_too_long_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("user@" + "d" * 64 + ".com")


def test_single_char_local_and_domain() -> None:
    assert parse_address("a@b").normalized == "a@b"


def test_many_labels() -> None:
    text = "user@" + ".".join(["a"] * 30 + ["com"])
    assert is_valid_address(text)


def test_quoted_string_with_all_specials() -> None:
    text = '"very.(),:;<>\\"@[]\\\\ long"@example.com'
    assert is_valid_address(text)


def test_comment_before_and_after_angle() -> None:
    addr = parse_address("(a) <john@example.com> (b)")
    assert addr.comments == ("a", "b")


# ---------------------------------------------------------------------------
# Invalid inputs — must raise
# ---------------------------------------------------------------------------

INVALID_STRICT = [
    "",
    " ",
    "   ",
    "@",
    "@example.com",
    "user@",
    "user",
    "user@@example.com",
    "user@example.com@example.com",
    "a..b@example.com",
    ".a@example.com",
    "a.@example.com",
    "..@example.com",
    "user@.example.com",
    "user@example..com",
    "user@example.com.",
    "user@example.com..",
    "user name@example.com",
    '"unbalanced@example.com',
    'unbalanced"@example.com',
    '""@',
    "<",
    ">",
    "<>",
    "<@>",
    "<john@example.com",
    "john@example.com>",
    "a@b@c",
    "a@@b",
    "a@b.",
    "a@.b",
    "a b@c",
    "a@b c",
    "(unterminated john@example.com",
    "(a(b)john@example.com",
    '"a\\"@example.com',
    "a\x00b@example.com",
    "a\x01b@example.com",
    "a@b\x00.com",
    "a@b\x1f.com",
    "user@[unterminated",
    "user@]",
    "user@[a\\]",
    "G:",
    "G:a@x.com",
    ":a@x.com;",
    ",a@x.com",
    "a@x.com,",
    "a@x.com,,b@y.com",
    "a@x.com;",
]


@pytest.mark.parametrize("text", INVALID_STRICT)
def test_invalid_strict(text: str) -> None:
    assert is_valid_address(text, strict=True) is False
    with pytest.raises(AddressSyntaxError):
        parse_address(text, strict=True)


INVALID_ANY_MODE = [
    "",
    "@",
    "user@",
    "@example.com",
    "user",
    "a..b@example.com",
    ".a@example.com",
    "a.@example.com",
    "user@.example.com",
    "user@example..com",
    "<john@example.com",
    "john@example.com>",
    "a@b@c",
    "(unterminated john@example.com",
    '"unbalanced@example.com',
    "user name@example.com",
    "a\x00b@example.com",
]


@pytest.mark.parametrize("text", INVALID_ANY_MODE)
def test_invalid_both_modes(text: str) -> None:
    assert is_valid_address(text, strict=False) is False


def test_control_char_in_local_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("a\x0bb@example.com")


def test_del_char_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("a\x7fb@example.com")


def test_bare_crlf_not_fold_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("john@example.com\r\n")


def test_crlf_without_wsp_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("john\r\nexample.com")


def test_type_error_on_non_string() -> None:
    with pytest.raises(TypeError):
        parse_address(123)  # type: ignore[arg-type]


def test_is_valid_returns_false_on_non_string() -> None:
    assert is_valid_address(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Exception quality
# ---------------------------------------------------------------------------


def test_error_has_position() -> None:
    try:
        parse_address("a..b@example.com")
    except AddressSyntaxError as exc:
        assert exc.position >= 0
    else:  # pragma: no cover
        pytest.fail("expected AddressSyntaxError")


def test_error_is_value_error_subclass() -> None:
    assert issubclass(AddressSyntaxError, ValueError)


def test_error_message_includes_offset() -> None:
    with pytest.raises(AddressSyntaxError, match="offset"):
        parse_address("a..b@example.com")


# ---------------------------------------------------------------------------
# Immutability / no input mutation
# ---------------------------------------------------------------------------


def test_input_string_not_mutated() -> None:
    text = "john@example.com"
    parse_address(text)
    assert text == "john@example.com"


def test_group_members_are_addresses() -> None:
    addr = parse_address("G:a@x.com;")
    assert all(isinstance(m, Address) for m in addr.group_members)


# ---------------------------------------------------------------------------
# Sanity comparison with the stdlib (documents divergence)
# ---------------------------------------------------------------------------


class TestStdlibDivergence:
    """The stdlib parser is lax; these document where it disagrees."""

    @staticmethod
    def _stdlib(text: str) -> tuple[str, str]:
        from email.utils import parseaddr

        return parseaddr(text)

    def test_stdlib_accepts_double_dot(self) -> None:
        # RFC 5322 forbids "a..b"; stdlib happily accepts it.
        assert self._stdlib("a..b@example.com") == ("", "a..b@example.com")
        assert is_valid_address("a..b@example.com") is False

    def test_stdlib_strips_comment_differently(self) -> None:
        name, addr = self._stdlib("(comment)john@example.com")
        assert addr == "john@example.com"
        # stdlib keeps the comment text as the display name; we preserve it
        # separately as a decoded comment and report no display name.
        assert parse_address("(comment)john@example.com").comments == ("comment",)
        assert parse_address("(comment)john@example.com").display_name is None
        assert name == "comment"
