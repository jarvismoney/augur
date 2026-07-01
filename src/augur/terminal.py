"""Minimal ANSI styling with graceful degradation.

Colour is enabled only when writing to a TTY and ``NO_COLOR`` is unset, and can
be forced on/off by the CLI. Everything funnels through :func:`style` so the
rest of the code never hard-codes escape sequences.
"""

from __future__ import annotations

import os
import sys

_CODES = {
    "reset": "0",
    "bold": "1",
    "dim": "2",
    "italic": "3",
    "underline": "4",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
    "gray": "90",
    "bright_red": "91",
    "bright_green": "92",
    "bright_yellow": "93",
    "bright_blue": "94",
    "bright_cyan": "96",
}

# Tri-state: None => auto-detect, True/False => forced by the CLI.
_forced: bool | None = None


def set_color(enabled: bool | None) -> None:
    """Force colour on (True), off (False), or auto-detect (None)."""
    global _forced
    _forced = enabled


def color_enabled(stream=None) -> bool:
    if _forced is not None:
        return _forced
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("AUGUR_FORCE_COLOR"):
        return True
    stream = stream or sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)())


def style(text: str, *names: str, stream=None) -> str:
    """Wrap ``text`` in the given style names if colour is enabled."""
    if not names or not color_enabled(stream):
        return text
    codes = ";".join(_CODES[n] for n in names if n in _CODES)
    if not codes:
        return text
    return f"\033[{codes}m{text}\033[0m"


# Convenience shortcuts -------------------------------------------------------

def bold(text: str) -> str:
    return style(text, "bold")


def dim(text: str) -> str:
    return style(text, "dim")


def green(text: str) -> str:
    return style(text, "green")


def red(text: str) -> str:
    return style(text, "red")


def yellow(text: str) -> str:
    return style(text, "yellow")


def cyan(text: str) -> str:
    return style(text, "cyan")


def gray(text: str) -> str:
    return style(text, "gray")


def heading(text: str) -> str:
    return style(text, "bold", "cyan")
