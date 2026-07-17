"""Static safety checks for container entrypoint logging."""

from pathlib import Path


def test_entrypoint_does_not_log_database_configuration_values():
    entrypoint = Path(__file__).resolve().parents[1] / "docker-entrypoint.sh"
    echo_lines = [
        line for line in entrypoint.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("echo ")
    ]

    for line in echo_lines:
        assert "$DB_URL" not in line
        assert "$DB_PATH" not in line
        assert "$DB_DIR" not in line
