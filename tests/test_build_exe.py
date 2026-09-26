"""Unit tests for standalone executable compiler (build_exe.py)."""

import sys
from unittest.mock import patch

from build_exe import build_executable, check_prerequisites, clean_artifacts, main


def test_clean_artifacts(tmp_path):
    """Verify clean_artifacts removes build and dist directories."""
    with patch("build_exe.PROJECT_ROOT", tmp_path):
        build_dir = tmp_path / "build"
        dist_dir = tmp_path / "dist"
        build_dir.mkdir()
        dist_dir.mkdir()
        (build_dir / "temp.txt").write_text("build")
        (dist_dir / "temp.txt").write_text("dist")

        clean_artifacts()
        assert not build_dir.exists()
        assert not dist_dir.exists()


def test_build_executable_missing_spec():
    """Verify build_executable returns False when spec file is missing."""
    assert build_executable("nonexistent.spec", "Missing") is False


def test_build_executable_mock_success(tmp_path):
    """Verify build_executable invokes PyInstaller and reports success."""
    fake_spec = tmp_path / "fake.spec"
    fake_spec.write_text("# spec")
    fake_dist = tmp_path / "dist"
    fake_dist.mkdir()
    fake_bin = fake_dist / "fake"
    fake_bin.write_text("binary")

    with (
        patch("build_exe.PROJECT_ROOT", tmp_path),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        success = build_executable("fake.spec", "fake")
        assert success is True
        assert mock_run.called


def test_check_prerequisites_success():
    """Verify check_prerequisites returns True when PyInstaller is installed."""
    mock_spec = object()
    with patch("build_exe.importlib.util.find_spec", return_value=mock_spec) as mock_find:
        assert check_prerequisites() is True
        mock_find.assert_called_once_with("PyInstaller")


def test_check_prerequisites_missing(capsys):
    """Verify check_prerequisites returns False and prints diagnostic help when missing."""
    with patch("build_exe.importlib.util.find_spec", return_value=None) as mock_find:
        assert check_prerequisites() is False
        mock_find.assert_called_once_with("PyInstaller")

    captured = capsys.readouterr().out
    assert "Missing required build dependency: PyInstaller" in captured
    assert sys.executable in captured
    assert "pip install pyinstaller" in captured
    assert "releases" in captured


def test_main_prerequisites_failure_preserves_artifacts(tmp_path):
    """Verify main halts early and preserves artifacts if pre-flight check fails."""
    build_dir = tmp_path / "build"
    dist_dir = tmp_path / "dist"
    build_dir.mkdir()
    dist_dir.mkdir()
    (dist_dir / "existing_app.exe").write_text("binary")

    with (
        patch("build_exe.PROJECT_ROOT", tmp_path),
        patch("build_exe.check_prerequisites", return_value=False) as mock_preflight,
        patch("build_exe.clean_artifacts") as mock_clean,
    ):
        exit_code = main(["--clean", "--all"])
        assert exit_code == 1
        mock_preflight.assert_called_once()
        mock_clean.assert_not_called()
        assert (dist_dir / "existing_app.exe").exists()


def test_main_clean_only_skips_prerequisites(tmp_path):
    """Verify --clean without build flags cleans artifacts and does not require PyInstaller."""
    build_dir = tmp_path / "build"
    dist_dir = tmp_path / "dist"
    build_dir.mkdir()
    dist_dir.mkdir()

    with (
        patch("build_exe.PROJECT_ROOT", tmp_path),
        patch("build_exe.check_prerequisites") as mock_preflight,
    ):
        exit_code = main(["--clean"])
        assert exit_code == 0
        mock_preflight.assert_not_called()
        assert not build_dir.exists()
        assert not dist_dir.exists()


def test_main_default_fallback_triggers_preflight_and_builds():
    """Verify default invocation falls back to --all, checks prerequisites, and builds both specs."""
    with (
        patch("build_exe.check_prerequisites", return_value=True) as mock_preflight,
        patch("build_exe.build_executable", return_value=True) as mock_build,
    ):
        exit_code = main([])
        assert exit_code == 0
        mock_preflight.assert_called_once()
        assert mock_build.call_count == 2
        mock_build.assert_any_call("gui.spec", "Gui")
        mock_build.assert_any_call("cli.spec", "cli")


def test_main_build_failure_returns_exit_code_one():
    """Verify main returns exit code 1 if any build fails."""
    with (
        patch("build_exe.check_prerequisites", return_value=True),
        patch("build_exe.build_executable", return_value=False),
    ):
        exit_code = main(["--gui"])
        assert exit_code == 1


def test_cli_spec_hiddenimports_includes_main():
    """Verify that cli.spec includes root module 'main' in hiddenimports for server command."""
    from build_exe import PROJECT_ROOT
    spec_path = PROJECT_ROOT / "cli.spec"
    assert spec_path.is_file(), f"Spec file not found at {spec_path}"
    content = spec_path.read_text(encoding="utf-8")
    assert '"main"' in content or "'main'" in content, (
        "cli.spec must include 'main' in hiddenimports"
    )


def test_cli_and_gui_specs_disable_upx():
    """Verify both cli.spec and gui.spec disable UPX to prevent AV false-positive flags."""
    from build_exe import PROJECT_ROOT
    for spec_name in ["cli.spec", "gui.spec"]:
        spec_path = PROJECT_ROOT / spec_name
        assert spec_path.is_file(), f"Spec file not found at {spec_path}"
        content = spec_path.read_text(encoding="utf-8")
        assert "upx=False" in content, f"{spec_name} must explicitly specify upx=False"
        assert "upx=True" not in content, f"{spec_name} must not contain upx=True"

