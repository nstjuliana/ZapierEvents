#!/usr/bin/env python3
"""
Simple script to generate an API key for testing.
"""

import os
import sys
import secrets
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError

# Set environment variables
os.environ['EVENTS_TABLE_NAME'] = 'triggers-api-dev-events'
os.environ['API_KEYS_TABLE_NAME'] = 'triggers-api-dev-api-keys'
os.environ['AWS_REGION'] = 'us-east-1'

# Add src to path
sys.path.append('src')

from auth.api_key import hash_api_key

def generate_and_store_key():
    # Generate API key
    key_suffix = secrets.token_urlsafe(32)[:32]
    api_key = f"sk_{key_suffix}"

    print(f"Generated API Key: {api_key}")
    print("   WARNING: Store this key securely! It will not be shown again.")
    print()

    # Hash the key
    print("Hashing API key with bcrypt...")
    hashed_key = hash_api_key(api_key)
    print("   Key hashed successfully")
    print()

    # Store in DynamoDB
    print("Storing hashed key in DynamoDB...")
    try:
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('triggers-api-dev-api-keys')

        key_id = f"key_{api_key[3:11]}"  # Skip 'sk_' prefix, take next 8 chars
        now = datetime.now(timezone.utc).isoformat()

        table.put_item(
            Item={
                'key_id': key_id,
                'api_key_hash': hashed_key,
                'description': 'Test API Key for Events',
                'environment': 'dev',
                'created_at': now,
                'is_active': True,
                'last_used_at': None,
                'usage_count': 0
            }
        )

        print("   Key stored successfully")
        print()
        print("API Key Generation Complete!")
        print(f"   Key ID: {key_id}")
        print()
        print("Use the API key above in your Authorization header:")
        print(f"   Authorization: Bearer {api_key}")
        print()
        print("The plaintext key has been displayed for the last time.")

    except Exception as e:
        print(f"Error storing key: {str(e)}")
        return None

    return api_key

if __name__ == '__main__':
    generate_and_store_key()
