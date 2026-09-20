"""Unit tests for Sysmon Hashes parsing. Synthetic values only."""

from raven.parsers.hash_utils import parse_hashes

SHA256 = "AB" * 32
MD5 = "CD" * 16
IMPHASH = "EF" * 16
NONE = {"sha256": None, "md5": None, "imphash": None}


def test_all_three_algorithms():
    text = f"SHA256={SHA256},MD5={MD5},IMPHASH={IMPHASH}"
    assert parse_hashes(text) == {"sha256": SHA256, "md5": MD5, "imphash": IMPHASH}


def test_only_sha256():
    assert parse_hashes(f"SHA256={SHA256}") == {"sha256": SHA256, "md5": None, "imphash": None}


def test_order_and_case_do_not_matter_and_values_become_upper_case():
    lower = SHA256.lower()
    assert parse_hashes(f"imphash={IMPHASH.lower()},sha256={lower}")["sha256"] == SHA256
    assert parse_hashes(f"imphash={IMPHASH.lower()},sha256={lower}")["imphash"] == IMPHASH


def test_other_algorithms_are_ignored():
    text = f"SHA1={'12' * 20},SHA256={SHA256}"
    assert parse_hashes(text) == {"sha256": SHA256, "md5": None, "imphash": None}


def test_wrong_length_or_non_hex_is_not_extracted():
    assert parse_hashes("SHA256=ABCD") == NONE
    assert parse_hashes(f"SHA256={'Z' * 64}") == NONE
    assert parse_hashes(f"MD5={'A' * 31}") == NONE


def test_first_valid_value_wins():
    other = "12" * 32
    assert parse_hashes(f"SHA256={SHA256},SHA256={other}")["sha256"] == SHA256
    assert parse_hashes(f"SHA256=BAD,SHA256={other}")["sha256"] == other


def test_empty_or_missing():
    assert parse_hashes(None) == NONE
    assert parse_hashes("") == NONE
    assert parse_hashes("no equals sign here") == NONE


def test_spaces_around_parts_are_tolerated():
    assert parse_hashes(f" SHA256 = {SHA256} , MD5={MD5}")["sha256"] == SHA256
