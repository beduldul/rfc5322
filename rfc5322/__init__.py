"""RFC 5322 conformant email address parser (pure stdlib)."""

from .parser import (
    Address,
    AddressSyntaxError,
    is_valid_address,
    parse_address,
    parse_address_list,
    parse_mailbox_list,
)

__all__ = [
    "Address",
    "AddressSyntaxError",
    "parse_address",
    "is_valid_address",
    "parse_address_list",
    "parse_mailbox_list",
]

__version__ = "1.0.1"
