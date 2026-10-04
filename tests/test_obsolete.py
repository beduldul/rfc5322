"""Tests for the §4.4 obsolete character classes and rare error paths.

These exercise branches that the main suite does not reach, and pin down the
behaviour of ``obs-ctext``, ``obs-qtext``, ``obs-qp`` and ``obs-dtext``.
"""

from __future__ import annotations

import pytest

from rfc5322 import AddressSyntaxError, is_valid_address, parse_address

# obs-NO-WS-CTL characters that §4.4 permits inside comments and quoted
# strings when strict=False.
OBS_CTL = ["\x01", "\x0b", "\x0c", "\x1f", "\x7f"]


@pytest.mark.parametrize("ch", OBS_CTL)
def test_obs_ctext_in_comment_permissive(ch: str) -> None:
    addr = parse_address(f"(a{ch}b)john@example.com", strict=False)
    assert addr.obsolete is True


@pytest.mark.parametrize("ch", OBS_CTL)
def test_obs_ctext_in_comment_strict_rejected(ch: str) -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address(f"(a{ch}b)john@example.com", strict=True)


@pytest.mark.parametrize("ch", OBS_CTL)
def test_obs_qtext_in_quoted_string_permissive(ch: str) -> None:
    addr = parse_address(f'"a{ch}b"@example.com', strict=False)
    assert addr.obsolete is True


@pytest.mark.parametrize("ch", OBS_CTL)
def test_obs_qtext_strict_rejected(ch: str) -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address(f'"a{ch}b"@example.com', strict=True)


def test_obs_qp_in_quoted_string_permissive() -> None:
    addr = parse_address('"a\\\x01b"@example.com', strict=False)
    assert addr.obsolete is True


def test_obs_qp_strict_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address('"a\\\x01b"@example.com', strict=True)


def test_obs_dtext_in_domain_literal_permissive() -> None:
    addr = parse_address("user@[a\x01b]", strict=False)
    assert addr.obsolete is True


def test_obs_dtext_strict_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("user@[a\x01b]", strict=True)


def test_obs_dtext_quoted_pair_permissive() -> None:
    addr = parse_address("user@[a\\]b]", strict=False)
    assert addr.obsolete is True


def test_obs_fws_leading_wsp_before_crlf_permissive() -> None:
    # obs-FWS = 1*WSP *(CRLF 1*WSP)
    addr = parse_address("john \r\n @example.com", strict=False)
    assert addr.normalized == "john@example.com"


def test_obs_domain_atom_form_permissive() -> None:
    addr = parse_address("user@ example . com", strict=False)
    assert addr.domain == "example.com"


def test_obs_domain_strict_rejected() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("user@ example . com", strict=True)


def test_obs_group_list_leading_commas() -> None:
    addr = parse_address("G:,,;", strict=False)
    assert addr.obsolete is True
    assert addr.group_members == ()


def test_obs_group_list_with_comment() -> None:
    addr = parse_address("G:(c),a@x.com;", strict=False)
    assert addr.is_group is True


def test_obs_addr_list_leading_comma() -> None:
    from rfc5322 import parse_address_list

    out = parse_address_list(",a@x.com", strict=False)
    assert out[0].normalized == "a@x.com"


def test_obs_addr_list_trailing_comma() -> None:
    from rfc5322 import parse_address_list

    out = parse_address_list("a@x.com,", strict=False)
    assert len(out) == 1


def test_obs_phrase_word_and_dot() -> None:
    addr = parse_address("John Q. Public <j@x.com>", strict=False)
    assert addr.display_name == "John Q. Public"


def test_illegal_char_in_comment() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("(a\x00b)john@example.com", strict=False)


def test_illegal_char_in_quoted_string() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address('"a\x00b"@example.com', strict=False)


def test_illegal_char_in_domain_literal() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("user@[a\x00b]", strict=False)


def test_unterminated_comment() -> None:
    with pytest.raises(AddressSyntaxError, match="unterminated comment"):
        parse_address("(abc john@example.com")


def test_unterminated_quoted_string() -> None:
    with pytest.raises(AddressSyntaxError, match="unterminated quoted-string"):
        parse_address('"abc@example.com')


def test_unterminated_domain_literal() -> None:
    with pytest.raises(AddressSyntaxError, match="unterminated domain-literal"):
        parse_address("user@[abc")


def test_trailing_backslash_in_comment() -> None:
    with pytest.raises(AddressSyntaxError, match="trailing backslash"):
        parse_address("(abc\\")


def test_bare_crlf_in_comment_illegal() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("(a\rb)john@example.com", strict=False)


def test_group_not_closed_returns_none_then_error() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("G:a@x.com")


def test_group_member_invalid_rolls_back() -> None:
    with pytest.raises(AddressSyntaxError):
        parse_address("G:a@x.com, ;", strict=True)


def test_is_valid_handles_group_and_errors() -> None:
    assert is_valid_address("G:a@x.com;") is True
    assert is_valid_address("G:a@x.com") is False


# ---------------------------------------------------------------------------
# Regressions found by the differential fuzz harness (fuzz/).
#
# Invariant: an input accepted only under ``strict=False`` must report
# ``obsolete is True``.  These inputs are valid per §4.4 (obs-local-part,
# obs-domain, obs-FWS, obs-mbox-list) but the parser previously parsed them
# without setting the flag.
# ---------------------------------------------------------------------------

OBSOLETE_ONLY = [
    "user. name@x.com",          # obs-local-part: word "." word with CFWS
    "user .name@x.com",          # obs-local-part
    "john@example\r\n .com",     # obs-domain: atom *("." atom)
    "user@ex .ample.com",        # obs-domain
    'user."quoted"@example.com',  # obs-local-part: dot-atom / quoted-string mix
]


@pytest.mark.parametrize("text", OBSOLETE_ONLY)
def test_obsolete_flag_set_when_only_valid_permissively(text: str) -> None:
    addr = parse_address(text, strict=False)
    assert addr.obsolete is True
    with pytest.raises(AddressSyntaxError):
        parse_address(text, strict=True)


def test_obsolete_flag_group_trailing_comma() -> None:
    # group-list -> mailbox-list -> obs-mbox-list: "a@b.com," is *("," [mailbox]).
    addr = parse_address("Group: a@b.com,;", strict=False)
    assert addr.obsolete is True
    with pytest.raises(AddressSyntaxError):
        parse_address("Group: a@b.com,;", strict=True)


def test_obsolete_flag_false_for_modern_list() -> None:
    from rfc5322 import parse_address_list

    modern = parse_address_list("a@b.com, c@d.com", strict=False)
    assert all(a.obsolete is False for a in modern)


# ---------------------------------------------------------------------------
# obs-mbox-list (§3.4) — was documented "complete" but not implemented.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [",a@x.com", "a@x.com,", ",a@x.com,", ",,a@x.com", "a@x.com, b@y.com"],
)
def test_obs_mbox_list_permissive(text: str) -> None:
    from rfc5322 import parse_mailbox_list

    out = parse_mailbox_list(text, strict=False)
    assert out
    assert out[0].normalized == "a@x.com"


@pytest.mark.parametrize("text", [",a@x.com", "a@x.com,", ",,a@x.com"])
def test_obs_mbox_list_strict_rejected(text: str) -> None:
    from rfc5322 import parse_mailbox_list

    with pytest.raises(AddressSyntaxError):
        parse_mailbox_list(text, strict=True)
