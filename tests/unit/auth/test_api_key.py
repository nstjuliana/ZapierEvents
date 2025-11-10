"""
Module: test_api_key.py
Description: Unit tests for API key hashing and validation.

Tests passlib-based bcrypt hashing, verification functions,
and error handling for API key authentication.
"""

import pytest

from src.auth.api_key import hash_api_key, verify_api_key, needs_rehash


class TestApiKeyHashing:
    """Test cases for API key hashing and verification."""

    def test_hash_api_key_success(self):
        """Test successful API key hashing."""
        api_key = "sk_test123456789012345678901234567890"
        hashed = hash_api_key(api_key)

        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed.startswith("$2b$")  # bcrypt format
        assert hashed != api_key  # Should be hashed

    def test_hash_api_key_invalid_input(self):
        """Test hash_api_key with invalid inputs."""
        invalid_inputs = ["", None, "   ", 123]

        for invalid_input in invalid_inputs:
            with pytest.raises(ValueError):
                hash_api_key(invalid_input)

    def test_verify_api_key_success(self):
        """Test successful API key verification."""
        api_key = "sk_test123456789012345678901234567890"
        hashed = hash_api_key(api_key)

        assert verify_api_key(api_key, hashed) is True

    def test_verify_api_key_failure(self):
        """Test API key verification with wrong keys."""
        api_key = "sk_test123456789012345678901234567890"
        hashed = hash_api_key(api_key)

        wrong_keys = [
            "sk_wrong123456789012345678901234567890",
            "sk_test123456789012345678901234567891",  # One char different
            "",
            None,
            "not_an_api_key"
        ]

        for wrong_key in wrong_keys:
            assert verify_api_key(wrong_key, hashed) is False

    def test_verify_api_key_invalid_hash(self):
        """Test verify_api_key with invalid hash format."""
        api_key = "sk_test123456789012345678901234567890"

        invalid_hashes = [
            "",
            None,
            "not_a_hash",
            "$2b$invalid",
            "plain_text_hash"
        ]

        for invalid_hash in invalid_hashes:
            assert verify_api_key(api_key, invalid_hash) is False

    def test_verify_api_key_different_keys(self):
        """Test that different API keys produce different hashes."""
        key1 = "sk_test111111111111111111111111111111"
        key2 = "sk_test222222222222222222222222222222"

        hash1 = hash_api_key(key1)
        hash2 = hash_api_key(key2)

        assert hash1 != hash2
        assert verify_api_key(key1, hash1) is True
        assert verify_api_key(key2, hash2) is True
        assert verify_api_key(key1, hash2) is False
        assert verify_api_key(key2, hash1) is False

    def test_needs_rehash_current_hash(self):
        """Test needs_rehash with current work factor."""
        api_key = "sk_test123456789012345678901234567890"
        hashed = hash_api_key(api_key)

        # Should not need rehash with current settings
        assert needs_rehash(hashed) is False

    def test_needs_rehash_old_work_factor(self):
        """Test needs_rehash with old work factor hash."""
        # Manually create a hash with lower work factor (simulating old hash)
        from passlib.hash import bcrypt

        api_key = "sk_test123456789012345678901234567890"
        # Create hash with work factor 10 (lower than our default 13)
        old_hash = bcrypt.hash(api_key, rounds=10)

        # Should need rehash
        assert needs_rehash(old_hash) is True

    def test_needs_rehash_invalid_hash(self):
        """Test needs_rehash with invalid hash formats."""
        invalid_hashes = [
            "",
            None,
            "not_a_hash",
            "plain_text",
            "$invalid$format"
        ]

        for invalid_hash in invalid_hashes:
            # Should return True for invalid hashes (they need "rehashing")
            assert needs_rehash(invalid_hash) is True

    def test_hash_consistency(self):
        """Test that hashing the same key multiple times produces different hashes."""
        # bcrypt includes salt, so same input should produce different hashes
        api_key = "sk_test123456789012345678901234567890"

        hash1 = hash_api_key(api_key)
        hash2 = hash_api_key(api_key)

        assert hash1 != hash2  # Different due to salt
        assert verify_api_key(api_key, hash1) is True
        assert verify_api_key(api_key, hash2) is True

    def test_api_key_format_validation(self):
        """Test that various API key formats work."""
        valid_keys = [
            "sk_12345678901234567890123456789012",  # 32 chars after prefix
            "sk_short",
            "sk_" + "a" * 50,  # Long key
            "sk_test-key_123"  # With special chars (should work)
        ]

        for api_key in valid_keys:
            hashed = hash_api_key(api_key)
            assert verify_api_key(api_key, hashed) is True

    def test_timing_attack_resistance(self):
        """Test that verification is timing-resistant."""
        # This is hard to test directly, but we can verify that
        # wrong keys of different lengths are handled consistently
        api_key = "sk_test123456789012345678901234567890"
        hashed = hash_api_key(api_key)

        wrong_keys = [
            "sk_wrong",
            "sk_wrong123456789012345678901234567890",
            "sk_wrong1234567890123456789012345678901234567890"
        ]

        # All should return False without timing differences
        for wrong_key in wrong_keys:
            assert verify_api_key(wrong_key, hashed) is False
