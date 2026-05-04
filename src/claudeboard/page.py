from __future__ import annotations

from importlib.resources import files

PAGE: bytes = files("claudeboard").joinpath("static/index.html").read_bytes()
