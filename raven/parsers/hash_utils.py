"""Parsing of the Sysmon Hashes field, for example "SHA256=AB12...,IMPHASH=CD34...".

Only SHA256, MD5 and IMPHASH are extracted. Other algorithms (for example SHA1) stay in the
original text, which the normalizer keeps in hashes_raw. A value that is not hexadecimal or has
the wrong length is not extracted (it is never guessed or repaired). Extracted values are upper case.
"""

from __future__ import annotations

import re

_ALGORITHMS = {
    "SHA256": ("sha256", 64),
    "MD5": ("md5", 32),
    "IMPHASH": ("imphash", 32),
}
_HEX = re.compile(r"^[0-9A-Fa-f]+$")


def parse_hashes(text: str | None) -> dict[str, str | None]:
    """Return {"sha256": ..., "md5": ..., "imphash": ...}; a missing or invalid value is None."""
    result: dict[str, str | None] = {"sha256": None, "md5": None, "imphash": None}
    if not text:
        return result
    for part in text.split(","):
        name, separator, value = part.partition("=")
        if not separator:
            continue
        algorithm = _ALGORITHMS.get(name.strip().upper())
        if algorithm is None:
            continue
        field, length = algorithm
        value = value.strip()
        if result[field] is None and len(value) == length and _HEX.match(value):
            result[field] = value.upper()
    return result
