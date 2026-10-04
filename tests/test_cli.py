"""Tests for the ``python -m rfc5322`` command line entry point."""

from __future__ import annotations

import pytest

from rfc5322.__main__ import main


def test_cli_valid_simple(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["user@example.com"]) == 0
    out = capsys.readouterr().out
    assert "VALID" in out
    assert "local_part='user'" in out


def test_cli_valid_with_display_name(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["John Doe <john@example.com>"]) == 0
    assert "display_name='John Doe'" in capsys.readouterr().out


def test_cli_group(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["G:a@x.com, b@y.com;"]) == 0
    out = capsys.readouterr().out
    assert "VALID group" in out
    assert "a@x.com" in out


def test_cli_comments_reported(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["(c)john@example.com"]) == 0
    assert "comments=['c']" in capsys.readouterr().out


def test_cli_invalid(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["a..b@example.com"]) == 1
    assert "INVALID" in capsys.readouterr().err


def test_cli_permissive_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--permissive", 'user."q"@example.com']) == 0
    out = capsys.readouterr().out
    assert "obsolete" in out


def test_cli_permissive_short_flag() -> None:
    assert main(["-p", 'user."q"@example.com']) == 0


def test_cli_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "usage" in capsys.readouterr().err


def test_cli_usage_error_too_many(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["a@b.com", "c@d.com"]) == 2
    assert "usage" in capsys.readouterr().err
