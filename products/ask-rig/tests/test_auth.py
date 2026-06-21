"""Unit tests for auth primitives (pure stdlib crypto)."""
from __future__ import annotations

import pytest

from app.auth import hash_password, hash_token, new_token, verify_password


def test_hash_password_deterministic_with_same_salt():
    h1, salt = hash_password("hunter2")
    h2, _ = hash_password("hunter2", salt)
    assert h1 == h2


def test_hash_password_different_salt_differs():
    h1, s1 = hash_password("hunter2")
    h2, s2 = hash_password("hunter2")
    assert s1 != s2 and h1 != h2  # salts random → hashes differ


def test_verify_password():
    h, salt = hash_password("correct horse")
    assert verify_password("correct horse", h, salt) is True
    assert verify_password("wrong", h, salt) is False


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        hash_password("")


def test_new_token_hash_matches():
    raw, h = new_token()
    assert raw != h
    assert hash_token(raw) == h
    assert len(h) == 64  # sha256 hex


def test_token_unguessable_uniqueness():
    raws = {new_token()[0] for _ in range(50)}
    assert len(raws) == 50
