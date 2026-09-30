"""Security primitives: passwords, JWT, token encryption, OAuth state hashing."""

from __future__ import annotations

import pytest

from app.core import security


def test_password_hash_and_verify():
    hashed = security.hash_password("s3cret-password")
    assert hashed != "s3cret-password"
    assert security.verify_password("s3cret-password", hashed)
    assert not security.verify_password("wrong", hashed)


def test_jwt_roundtrip():
    token = security.create_access_token(42)
    assert security.decode_access_token(token) == 42


def test_jwt_tampered_rejected():
    token = security.create_access_token(42) + "tampered"
    assert security.decode_access_token(token) is None
    assert security.decode_access_token("not-a-token") is None


def test_token_encryption_roundtrip():
    ciphertext = security.encrypt_token("secret-access-token")
    assert ciphertext != "secret-access-token"
    assert security.decrypt_token(ciphertext) == "secret-access-token"


def test_token_decrypt_wrong_key_raises():
    with pytest.raises(ValueError, match="cannot be decrypted"):
        security.decrypt_token("not-valid-ciphertext")


def test_oauth_state_hashing():
    s1 = security.generate_oauth_state()
    s2 = security.generate_oauth_state()
    assert s1 != s2
    # SHA-256 hex digest, deterministic.
    assert security.hash_state(s1) == security.hash_state(s1)
    assert security.hash_state(s1) != security.hash_state(s2)
    assert len(security.hash_state(s1)) == 64
