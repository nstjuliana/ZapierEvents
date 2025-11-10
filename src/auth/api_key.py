"""
Module: api_key.py
Description: API key hashing and validation.

Provides functions for hashing API keys with PBKDF2-SHA256 and
validating keys against stored hashes. Uses standard library
hashlib for secure password hashing with configurable parameters.

Key Components:
- hash_api_key(): Hash plain API keys with PBKDF2-SHA256
- verify_api_key(): Verify plain keys against PBKDF2 hashes
- needs_rehash(): Check if hash needs updating
- PBKDF2 parameters: 100k iterations, 256-bit salt/key

Dependencies: hashlib, secrets, typing
Author: Triggers API Team
"""

import hashlib
import secrets
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Use PBKDF2-SHA256 for API key hashing (secure, no length limits)
# Parameters chosen for good security while being fast enough for API usage
PBKDF2_ITERATIONS = 100000  # High iteration count for security
PBKDF2_SALT_LENGTH = 32     # 256-bit salt
PBKDF2_KEY_LENGTH = 32      # 256-bit derived key
PBKDF2_ALGORITHM = 'pbkdf2_sha256'  # Hash format identifier


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using PBKDF2-SHA256.

    Generates a secure PBKDF2 hash of the provided API key.
    The hash includes salt and iteration parameters for verification.

    Args:
        api_key: Plain text API key to hash

    Returns:
        Hashed API key string in format: pbkdf2_sha256$iterations$salt$hash

    Raises:
        ValueError: If api_key is empty or invalid
        TypeError: If api_key is not a string

    Example:
        >>> hashed = hash_api_key("sk_abc123xyz")
        >>> print(hashed)
        'pbkdf2_sha256$100000$...'
    """
    if not api_key or not isinstance(api_key, str):
        raise ValueError("api_key must be a non-empty string")

    if not api_key.strip():
        raise ValueError("api_key cannot be only whitespace")

    try:
        # Generate a random salt
        salt = secrets.token_bytes(PBKDF2_SALT_LENGTH)

        # Derive key using PBKDF2
        key = hashlib.pbkdf2_hmac(
            'sha256',
            api_key.encode('utf-8'),
            salt,
            PBKDF2_ITERATIONS,
            dklen=PBKDF2_KEY_LENGTH
        )

        # Format: algorithm$iterations$salt$hash
        salt_hex = salt.hex()
        key_hex = key.hex()

        hashed_key = f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_hex}${key_hex}"

        logger.info(
            "API key hashed successfully",
            key_length=len(api_key),
            hash_length=len(hashed_key)
        )

        return hashed_key

    except Exception as e:
        logger.error(
            "Failed to hash API key",
            error=str(e)
        )
        raise


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """
    Verify an API key against its PBKDF2 hash.

    Compares a plain text API key against a stored PBKDF2 hash
    by re-computing the hash with the same parameters.

    Args:
        plain_key: Plain text API key from request
        hashed_key: Stored hashed API key from database

    Returns:
        True if key matches hash, False otherwise

    Raises:
        ValueError: If either key is empty or invalid
        TypeError: If keys are not strings

    Example:
        >>> hashed = hash_api_key("sk_abc123xyz")
        >>> verify_api_key("sk_abc123xyz", hashed)
        True
        >>> verify_api_key("wrong_key", hashed)
        False
    """
    if not plain_key or not isinstance(plain_key, str):
        logger.warning("Invalid plain API key provided for verification")
        return False

    if not hashed_key or not isinstance(hashed_key, str):
        logger.warning("Invalid hashed API key provided for verification")
        return False

    try:
        # Parse the hash format: pbkdf2_sha256$iterations$salt$hash
        parts = hashed_key.split('$')
        if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
            logger.warning("Invalid hash format for verification")
            return False

        algorithm = parts[0]
        iterations_str = parts[1]
        salt_hex = parts[2]
        expected_key_hex = parts[3]

        # Parse parameters
        try:
            iterations = int(iterations_str)
            salt = bytes.fromhex(salt_hex)
        except (ValueError, TypeError):
            logger.warning("Invalid hash parameters")
            return False

        # Re-compute the hash
        computed_key = hashlib.pbkdf2_hmac(
            'sha256',
            plain_key.encode('utf-8'),
            salt,
            iterations,
            dklen=PBKDF2_KEY_LENGTH
        )

        # Use constant-time comparison to prevent timing attacks
        computed_key_hex = computed_key.hex()
        is_valid = secrets.compare_digest(computed_key_hex, expected_key_hex)

        if is_valid:
            logger.info("API key verification successful")
        else:
            logger.warning("API key verification failed")

        return is_valid

    except Exception as e:
        logger.error(
            "Error during API key verification",
            error=str(e)
        )
        return False


def needs_rehash(hashed_key: str) -> bool:
    """
    Check if a hashed API key needs rehashing.

    Determines if the hash was created with deprecated parameters
    and should be updated to current standards.

    Args:
        hashed_key: Stored hashed API key to check

    Returns:
        True if key needs rehashing, False otherwise

    Example:
        >>> needs_rehash("pbkdf2_sha256$50000$...")
        True   # Old iteration count
        >>> needs_rehash("pbkdf2_sha256$100000$...")
        False  # Current iteration count
    """
    if not hashed_key or not isinstance(hashed_key, str):
        return False

    try:
        # Parse the hash format: pbkdf2_sha256$iterations$salt$hash
        parts = hashed_key.split('$')
        if len(parts) != 4 or parts[0] != PBKDF2_ALGORITHM:
            # Unknown format - needs rehashing
            return True

        iterations_str = parts[1]

        # Check if iterations are below current standard
        try:
            iterations = int(iterations_str)
            return iterations < PBKDF2_ITERATIONS
        except (ValueError, TypeError):
            # Invalid iteration count - needs rehashing
            return True

    except Exception:
        # If we can't parse the hash, it definitely needs updating
        return True
