"""CLI entry point: ``ctmchain`` exists, reports its version and explains itself."""

from __future__ import annotations

import pytest

from controlm_chain_admin import __version__
from controlm_chain_admin.cli import main


def test_version_flag_prints_package_version_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange / Act
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    # Assert
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"ctmchain {__version__}"


def test_no_arguments_prints_help_and_exits_with_usage_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Act
    code = main([])

    # Assert
    out = capsys.readouterr().out
    assert code == 2
    assert "usage: ctmchain" in out
    assert "Control-M" in out


def test_unknown_command_exits_with_usage_code(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["frobnicate"])

    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_version_is_semver_like() -> None:
    major, minor, patch = __version__.split(".")[:3]
    assert major.isdigit() and minor.isdigit() and patch[:1].isdigit()
