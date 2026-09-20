"""Small shared helpers for writing files safely.

A file is written to a temporary name next to the target and then renamed over it, so a
failed run never leaves a half-written file and never damages an existing one.
Text is written as UTF-8 with LF line ends on every platform.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path


def write_lines_atomic(path: str | os.PathLike[str], lines: Iterable[str]) -> int:
    """Write lines (each without its line end) to a file and return how many were written."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    count = 0
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            for line in lines:
                handle.write(line)
                handle.write("\n")
                count += 1
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return count


def write_text_atomic(path: str | os.PathLike[str], text: str) -> None:
    """Write a whole text to a file (UTF-8, LF line ends) in one atomic step."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
