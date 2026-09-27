#!/usr/bin/env python3
"""Unified CLI entrypoint for Udemy Enroller."""

import sys


def configure_stream_encoding() -> None:
    """Configure standard I/O streams with UTF-8 encoding and error replacement."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


configure_stream_encoding()

from app.cli.main import app  # noqa: E402

if __name__ == "__main__":
    app()
