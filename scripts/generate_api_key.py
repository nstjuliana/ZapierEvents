#!/usr/bin/env python3
"""
Script: generate_api_key.py
Description: Generate and store API keys for Triggers API authentication.

This script generates secure API keys, hashes them with bcrypt,
and stores them in the API keys DynamoDB table for use with
the Lambda authorizer.

Usage:
    python scripts/generate_api_key.py [--description "My API Key"] [--environment dev]

Security Note:
    The plaintext API key is shown only once. Store it securely!
    This script requires AWS credentials and access to DynamoDB.
"""

import argparse
import secrets
import sys
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from src.auth.api_key import hash_api_key
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def generate_api_key() -> str:
    """
    Generate a secure random API key.

    Returns:
        API key in format: sk_{base64_encoded_random_bytes}
    """
    # Generate 32 random bytes (256 bits) and encode as URL-safe base64
    random_bytes = secrets.token_bytes(32)
    key_suffix = secrets.token_urlsafe(32)  # 32 bytes = 43 chars, but we'll use 32

    # Format: sk_{32_char_base64}
    api_key = f"sk_{key_suffix[:32]}"  # Ensure exactly 32 chars after sk_

    return api_key


def store_api_key(
    api_key: str,
    hashed_key: str,
    description: str = "Generated API Key",
    environment: str = "dev"
) -> str:
    """
    Store the hashed API key in DynamoDB.

    Args:
        api_key: Plaintext API key (for generating key_id)
        hashed_key: Bcrypt hashed API key
        description: Human-readable description
        environment: Environment tag (dev, staging, prod)

    Returns:
        The key_id that was generated

    Raises:
        ClientError: If DynamoDB operation fails
        ValueError: If table doesn't exist or other configuration issues
    """
    try:
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb', region_name=settings.aws_region)
        table = dynamodb.Table(settings.api_keys_table_name)

        # Generate unique key_id from first 8 chars of API key
        key_id = f"key_{api_key[3:11]}"  # Skip 'sk_' prefix, take next 8 chars

        # Current timestamp
        now = datetime.now(timezone.utc).isoformat()

        # Store in DynamoDB
        table.put_item(
            Item={
                'key_id': key_id,
                'api_key_hash': hashed_key,
                'description': description,
                'environment': environment,
                'created_at': now,
                'is_active': True,
                'last_used_at': None,
                'usage_count': 0
            }
        )

        logger.info(
            "API key stored in DynamoDB",
            key_id=key_id,
            description=description,
            environment=environment,
            table_name=settings.api_keys_table_name
        )

        return key_id

    except ClientError as e:
        logger.error(
            "Failed to store API key in DynamoDB",
            error_code=e.response['Error']['Code'],
            error_message=e.response['Error']['Message'],
            table_name=settings.api_keys_table_name
        )
        raise

    except Exception as e:
        logger.error(
            "Unexpected error storing API key",
            error=str(e),
            table_name=settings.api_keys_table_name
        )
        raise


def main():
    """Main script execution."""
    parser = argparse.ArgumentParser(
        description="Generate and store API keys for Triggers API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/generate_api_key.py
  python scripts/generate_api_key.py --description "Production API Key"
  python scripts/generate_api_key.py --description "Test Key" --environment dev

Security Warning:
  The plaintext API key will be displayed only once.
  Store it securely - it cannot be recovered later!
        """
    )

    parser.add_argument(
        '--description',
        type=str,
        default='Generated API Key',
        help='Human-readable description for the API key'
    )

    parser.add_argument(
        '--environment',
        type=str,
        default='dev',
        choices=['dev', 'staging', 'prod'],
        help='Environment tag for the API key'
    )

    parser.add_argument(
        '--confirm',
        action='store_true',
        help='Confirm generation (prevents accidental key creation)'
    )

    args = parser.parse_args()

    if not args.confirm:
        print("⚠️  WARNING: This will generate a new API key!")
        print("   The plaintext key will be shown only once.")
        print("   Make sure you have AWS credentials configured.")
        print()
        response = input("Continue? (type 'yes' to confirm): ")
        if response.lower() != 'yes':
            print("Cancelled.")
            sys.exit(0)

    try:
        # Generate API key
        api_key = generate_api_key()
        print(f"🔑 Generated API Key: {api_key}")
        print("   ⚠️  WARNING: Store this key securely! It will not be shown again.")
        print()

        # Hash the key
        print("🔒 Hashing API key with bcrypt...")
        hashed_key = hash_api_key(api_key)
        print("   ✅ Key hashed successfully")
        print()

        # Store in DynamoDB
        print("💾 Storing hashed key in DynamoDB...")
        key_id = store_api_key(
            api_key=api_key,
            hashed_key=hashed_key,
            description=args.description,
            environment=args.environment
        )
        print("   ✅ Key stored successfully")
        print()

        # Success message
        print("🎉 API Key Generation Complete!")
        print(f"   Key ID: {key_id}")
        print(f"   Description: {args.description}")
        print(f"   Environment: {args.environment}")
        print()
        print("Use the API key above in your Authorization header:")
        print(f"   Authorization: Bearer {api_key}")
        print()
        print("🔒 The plaintext key has been displayed for the last time.")
        print("   Delete this from your terminal history if possible.")

    except KeyboardInterrupt:
        print("\n❌ Cancelled by user.")
        sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        logger.error("API key generation failed", error=str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
