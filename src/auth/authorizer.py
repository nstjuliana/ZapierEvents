"""
Module: authorizer.py
Description: Lambda authorizer for API key authentication.

Validates API keys from Authorization header and returns
IAM policies for API Gateway. Queries DynamoDB for stored
API key hashes and verifies them using bcrypt.

Key Components:
- lambda_handler(): Main Lambda authorizer function
- generate_policy(): Creates IAM policy documents
- API key extraction from Bearer tokens
- DynamoDB lookup and hash verification
- 5-minute caching via methodArn

Dependencies: boto3, os, typing
Author: Triggers API Team
"""

import boto3
import os
from typing import Dict, Any, Optional

from src.auth.api_key import verify_api_key
from src.utils.logger import get_logger

logger = get_logger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda authorizer handler for API key validation.

    Extracts API key from Authorization header, validates against
    stored hashes in DynamoDB, and returns IAM policy.

    The authorizer caches results for 5 minutes using the methodArn
    to reduce DynamoDB calls and improve performance.

    Args:
        event: API Gateway authorizer event
        context: Lambda context object

    Returns:
        IAM policy document allowing or denying access

    Example Event:
        {
            "headers": {"authorization": "Bearer sk_abc123..."},
            "methodArn": "arn:aws:execute-api:us-east-1:123456789/api/POST/events"
        }
    """
    try:
        # Extract API key from Authorization header
        token = _extract_api_key(event)

        if not token:
            logger.warning("No API key provided in request")
            return generate_policy('anonymous', 'Deny', event['methodArn'])

        # Validate API key against stored hashes
        if _validate_api_key(token):
            logger.info("API key authentication successful")
            return generate_policy('authenticated-user', 'Allow', event['methodArn'])
        else:
            logger.warning("API key authentication failed")
            return generate_policy('anonymous', 'Deny', event['methodArn'])

    except Exception as e:
        logger.error(
            "Unexpected error in authorizer",
            error=str(e),
            method_arn=event.get('methodArn', 'unknown')
        )
        # Deny access on any error for security
        return generate_policy('anonymous', 'Deny', event['methodArn'])


def _extract_api_key(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract API key from Authorization header.

    Supports Bearer token format: "Authorization: Bearer <api_key>"

    Args:
        event: API Gateway authorizer event

    Returns:
        API key string if found, None otherwise
    """
    headers = event.get('headers', {})
    auth_header = headers.get('authorization', headers.get('Authorization', ''))

    if not auth_header:
        return None

    # Handle Bearer token format
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()  # Remove 'Bearer ' prefix
        if token:
            return token

    # Handle direct API key (fallback)
    if auth_header and not auth_header.startswith('Bearer '):
        return auth_header.strip()

    return None


def _validate_api_key(api_key: str) -> bool:
    """
    Validate API key against stored hashes in DynamoDB.

    Queries the API keys table and verifies the provided key
    against all stored hashes. Uses Phase 1 simplification of
    scanning the table (not optimal for production scale).

    Args:
        api_key: Plain text API key to validate

    Returns:
        True if key is valid, False otherwise
    """
    table_name = os.environ.get('API_KEYS_TABLE_NAME')
    if not table_name:
        logger.error("API_KEYS_TABLE_NAME environment variable not set")
        return False

    try:
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)

        # Scan for API keys (Phase 1: simple but not scalable)
        # In production, would use key_id lookup or GSI
        response = table.scan(
            ProjectionExpression='api_key_hash'
        )

        # Check against all stored hashes
        for item in response.get('Items', []):
            stored_hash = item.get('api_key_hash')
            if stored_hash and verify_api_key(api_key, stored_hash):
                return True

        # Continue scanning if there are more items
        while response.get('LastEvaluatedKey'):
            response = table.scan(
                ProjectionExpression='api_key_hash',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )

            for item in response.get('Items', []):
                stored_hash = item.get('api_key_hash')
                if stored_hash and verify_api_key(api_key, stored_hash):
                    return True

        return False

    except Exception as e:
        logger.error(
            "Error validating API key against DynamoDB",
            error=str(e),
            table_name=table_name
        )
        return False


def generate_policy(principal_id: str, effect: str, resource: str) -> Dict[str, Any]:
    """
    Generate IAM policy document for API Gateway.

    Creates a policy document that allows or denies access to
    the API Gateway resource. Used by Lambda authorizers.

    Args:
        principal_id: Identifier for the principal (user/API key)
        effect: "Allow" or "Deny"
        resource: API Gateway method ARN

    Returns:
        IAM policy document dictionary

    Example:
        >>> policy = generate_policy('user123', 'Allow', 'arn:aws:...')
        >>> policy['policyDocument']['Statement'][0]['Effect']
        'Allow'
    """
    policy = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': effect,
                'Resource': resource
            }]
        }
    }

    # Add context for additional user information (optional)
    if effect == 'Allow':
        policy['context'] = {
            'userId': principal_id,
            'authenticated': 'true'
        }

    return policy
