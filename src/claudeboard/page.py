"""The static HTML page served at `/` — actual content lives in static/index.html."""

from __future__ import annotations

from importlib.resources import files

PAGE: bytes = files("claudeboard").joinpath("static/index.html").read_bytes()
