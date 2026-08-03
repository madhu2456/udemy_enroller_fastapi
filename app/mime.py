"""Register MIME types missing from CPython's builtin table (python:3.11-slim has no /etc/mime.types)."""

import mimetypes


def register_extra_mimetypes() -> None:
    for ext, typ in (
        (".woff2", "font/woff2"), (".woff", "font/woff"), (".ttf", "font/ttf"),
        (".otf", "font/otf"), (".eot", "application/vnd.ms-fontobject"), (".webp", "image/webp"),
    ):
        mimetypes.add_type(typ, ext)
