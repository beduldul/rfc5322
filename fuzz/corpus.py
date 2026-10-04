"""Deterministic corpus generator for the differential harness.

Two sources of input strings, both seeded so a run is reproducible:

``handwritten()``
    Curated cases grouped by the RFC 5322 production they exercise: valid
    simple forms, quoted local parts, comments in every legal position,
    nested comments, domain literals, groups, every §4.4 obsolete production,
    display names, and the 64/255/63/998 boundary lengths documented in the
    README.  Plus a matching set of *malformed* forms.

``mutated(n)``
    A byte-level mutation fuzzer.  It takes a hand-written case and applies a
    seeded random sequence of insert / delete / replace / duplicate / swap
    operations over an alphabet biased towards the RFC's structural
    characters (``@ . " ( ) < > [ ] : ; , \\`` and whitespace).  This is how
    the harness reaches inputs nobody thought to write down.

Everything is plain Python — no ``hypothesis`` dependency.  The reason is
reproducibility: a failing input must be reported as a literal string plus a
seed, and ``random.Random(seed)`` gives that with zero extra machinery.
"""

from __future__ import annotations

import random
from collections.abc import Iterator

# Bias mutations towards characters that carry grammar significance so the
# fuzzer explores the parse tree instead of mostly-alphabetic noise.
_MUTATION_ALPHABET = list("abz09@.\"()<>[]:;,\\ \t\r\n!#$%&'*+-/=?^_`{|}~") + [
    "\x00",
    "\x1f",
    "\x7f",
    "é",
    "\u2603",
]

_ATExt = "!#$%&'*+-/=?^_`{|}~ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

# ---------------------------------------------------------------------------
# Hand-written corpus, grouped by category (category -> list of inputs)
# ---------------------------------------------------------------------------

HANDWRITTEN: dict[str, list[str]] = {
    # --- valid -------------------------------------------------------------
    "valid/simple": [
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
    ],
    "valid/quoted-local": [
        '"john doe"@example.com',
        '"a\\"b"@example.com',
        '"a\\\\b"@example.com',
        '""@example.com',
        '" "@example.com',
        '"a.b"@example.com',
        '"a@b"@example.com',
        '"!#$%&"@example.com',
    ],
    "valid/comment-positions": [
        "(comment)john@example.com",
        "john(comment)@example.com",
        "john@(comment)example.com",
        "john@example.com(comment)",
        "(a)(b)john@example.com",
        "john(a)@(b)example.com",
        "(a(b)c)john@example.com",
        "(a(b(c)d)e)john@example.com",
        "()john@example.com",
        "(a\\)b)john@example.com",
        "(a\\\\)john@example.com",
        "(comment with @ sign)john@example.com",
    ],
    "valid/fws": [
        " john@example.com",
        "john@example.com ",
        "john @ example.com",
        "john\t@\texample.com",
        "john\r\n @example.com",
        "john@\r\n example.com",
        "john@example\r\n .com",
        "(a\r\n b)john@example.com",
        '"a\r\n b"@example.com',
    ],
    "valid/domain-literal": [
        "user@[192.0.2.1]",
        "user@[IPv6:2001:db8::1]",
        "user@[IPv6:::1]",
        "user@[]",
        "user@[a b]",
        "user@[a\r\n b]",
    ],
    "valid/display-name": [
        "John Doe <john@example.com>",
        "John Q. Public <j@x.com>",
        '"John Doe" <john@example.com>',
        "John <john@example.com>",
        "<john@example.com>",
        "John Doe (boss) <john@example.com>",
        "John Doe <john@example.com> (boss)",
        "John (a) Doe <john@example.com>",
    ],
    "valid/group": [
        "Group: a@b.com, c@d.com;",
        "Group:;",
        "Group: a@b.com;",
        '"My Group": a@b.com;',
        "A Group: a@b.com, c@d.com;",
        "Group: John <a@b.com>, Jane <c@d.com>;",
        "Group: a@b.com,;",
    ],
    # --- obsolete §4.4 (rejected in strict mode) ---------------------------
    "obsolete/local-part": [
        'user."quoted"@example.com',
        '"quoted".user@example.com',
        '"a"."b"@example.com',
        'a."b".c@example.com',
        '"a".b@example.com',
    ],
    "valid/atext-domain": [
        "user@ex_ample.com",
        "user@exam!ple.com",
    ],
    "obsolete/route": [
        "<@a.com,@b.com:user@c.com>",
        "<@a.com:user@c.com>",
        "Name <@a.com,@b.com:user@c.com>",
    ],
    "obsolete/phrase": [
        "John Q. Public <j@x.com>",
        "A. B. <a@b.com>",
    ],
    "obsolete/lists": [
        ",a@b.com",
        ",,a@b.com",
        "a@b.com,",
        "Group: ,a@b.com;",
    ],
    # --- malformed ---------------------------------------------------------
    "malformed/missing-at": [
        "userexample.com",
        "user",
        "",
        " ",
        "()",
        "(comment)",
    ],
    "malformed/multiple-at": [
        "a@b@c.com",
        "a@@b.com",
        "@@",
        "a@b@",
    ],
    "malformed/unquoted-specials": [
        "a b@example.com",
        "a,b@example.com",
        "a;b@example.com",
        "a:b@example.com",
        "a(b@example.com",
        "a)b@example.com",
        "a<b@example.com",
        "a>b@example.com",
        "a[b@example.com",
        "a\\b@example.com",
        "us er@x.com",
    ],
    "malformed/unbalanced": [
        '"unbalanced@x.com',
        "(unbalanced@x.com",
        "user@[1.2.3.4",
        "user@1.2.3.4]",
        '"a"b"@x.com',
        "(a(b)@x.com",
    ],
    "malformed/dots": [
        "a..b@example.com",
        ".user@example.com",
        "user.@example.com",
        "user@.com",
        "user@example..com",
        "user@x.com.",
        "user@.x.com",
        "user@x..com",
    ],
    "malformed/empty-parts": [
        "@example.com",
        "user@",
        "@",
        "<>",
        "<@x.com>",
    ],
    "malformed/lists": [
        "a@example.com, b@example.com",
        "user@example.com,",
        ",user@example.com",
        "a@b.com,,c@d.com",
    ],
    "malformed/control-and-nonascii": [
        "user\x00@example.com",
        "user@example\x01.com",
        "user@exa\x7fmple.com",
        "usér@example.com",
        "user@exämple.com",
        "\u2603@example.com",
        "user@\u2603.com",
        "user\n@example.com",
        "user@example.com\n",
    ],
    "malformed/trailing": [
        "user@example.com extra",
        "user@example.com>",
        "user@example.com)",
        "user@example.com]",
    ],
    # --- boundary lengths (README-documented 64/255/63/998) ----------------
    "boundary/local-part": [
        "a" * 64 + "@example.com",
        "a" * 65 + "@example.com",
        "a" * 63 + "@example.com",
        '"' + "a" * 62 + '"@example.com',
    ],
    "boundary/label": [
        "user@" + "a" * 63 + ".com",
        "user@" + "a" * 64 + ".com",
    ],
    "boundary/domain": [
        "user@" + ".".join(["a" * 63] * 4) + ".com",  # 255
        "user@" + ".".join(["a" * 63] * 5) + ".com",  # >255
    ],
    "boundary/line": [
        "a" * 900 + "@example.com",
        "a" * 994 + "@example.com",
    ],
}


def handwritten() -> list[tuple[str, str]]:
    """Return every hand-written case as ``(category, text)`` pairs."""
    return [(cat, text) for cat, texts in HANDWRITTEN.items() for text in texts]


# ---------------------------------------------------------------------------
# Mutation fuzzer
# ---------------------------------------------------------------------------


def _mutate_once(rng: random.Random, text: str) -> str:
    """Apply exactly one random mutation to ``text``."""
    op = rng.randrange(5)
    chars = list(text)
    if op == 0 or not chars:  # insert
        i = rng.randrange(len(chars) + 1)
        chars.insert(i, rng.choice(_MUTATION_ALPHABET))
    elif op == 1:  # delete
        del chars[rng.randrange(len(chars))]
    elif op == 2:  # replace
        chars[rng.randrange(len(chars))] = rng.choice(_MUTATION_ALPHABET)
    elif op == 3:  # duplicate a run
        i = rng.randrange(len(chars))
        j = min(len(chars), i + rng.randint(1, 4))
        chars[i:i] = chars[i:j]
    else:  # swap two characters
        if len(chars) >= 2:
            i, j = rng.sample(range(len(chars)), 2)
            chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def mutated(
    n: int,
    *,
    seed: int,
    bases: list[str] | None = None,
    max_mutations: int = 3,
) -> list[tuple[str, str]]:
    """Generate ``n`` seeded mutants of the hand-written corpus.

    Returns ``(category, text)`` pairs where the category records the base
    case so a failure can be traced back to a known production.  A fixed
    ``seed`` makes the output byte-for-byte reproducible.
    """
    rng = random.Random(seed)
    if bases is None:
        bases = [text for _, text in handwritten() if text]
    out: list[tuple[str, str]] = []
    for _ in range(n):
        text = rng.choice(bases)
        k = rng.randint(1, max_mutations)
        for _ in range(k):
            text = _mutate_once(rng, text)
        out.append(("mutated", text))
    return out


def generate(*, seed: int, n_mutants: int = 4000) -> list[tuple[str, str]]:
    """The full corpus: hand-written cases plus ``n_mutants`` seeded mutants."""
    return handwritten() + mutated(n_mutants, seed=seed)


def corpus_size(*, seed: int, n_mutants: int = 4000) -> int:
    """Total number of inputs ``generate`` will yield (before de-duplication)."""
    return len(handwritten()) + n_mutants


def dedupe(cases: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drop duplicate texts, keeping the first category seen."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for cat, text in cases:
        if text not in seen:
            seen.add(text)
            out.append((cat, text))
    return out


def iter_texts(cases: list[tuple[str, str]]) -> Iterator[str]:
    """Yield just the texts from ``(category, text)`` pairs."""
    for _, text in cases:
        yield text
