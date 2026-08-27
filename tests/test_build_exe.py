"""Unit tests for standalone executable compiler (build_exe.py)."""

from unittest.mock import patch
from build_exe import build_executable, clean_artifacts


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

    with patch("build_exe.PROJECT_ROOT", tmp_path), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        success = build_executable("fake.spec", "fake")
        assert success is True
        assert mock_run.called
