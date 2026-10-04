"""CLI: ``python -m rfc5322 "<address>"``.

Exit status 0 on a valid address, 1 on invalid, 2 on usage error.
``--permissive`` enables §4.4 obsolete productions.
"""

from __future__ import annotations

import sys

from .parser import AddressSyntaxError, parse_address


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    strict = True
    if args and args[0] in ("-p", "--permissive"):
        strict = False
        args.pop(0)
    if len(args) != 1:
        print("usage: python -m rfc5322 [--permissive] <address>", file=sys.stderr)
        return 2
    raw = args[0]
    try:
        addr = parse_address(raw, strict=strict)
    except AddressSyntaxError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    if addr.is_group:
        print(f"VALID group: display_name={addr.display_name!r}")
        for m in addr.group_members:
            print(f"  member: {m.normalized}")
    else:
        print(f"VALID: local_part={addr.local_part!r} domain={addr.domain!r}")
        print(f"  normalized={addr.normalized}")
        if addr.display_name is not None:
            print(f"  display_name={addr.display_name!r}")
    if addr.comments:
        print(f"  comments={list(addr.comments)!r}")
    if addr.obsolete:
        print("  (used obsolete §4.4 syntax)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
