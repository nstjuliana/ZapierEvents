#!/usr/bin/env python3
"""
Test the API key authorizer directly.
"""

import json

# Test event for authorizer
authorizer_event = {
    "headers": {
        "authorization": "Bearer sk_GJQjTTzgIHonQfR4cUMf0_3B_pu5Q5Ww"
    },
    "methodArn": "arn:aws:execute-api:us-east-1:971422717446:mmghecrjr5/*/POST/events"
}

print("Authorizer test event:")
print(json.dumps(authorizer_event, indent=2))
print()

# For now, let's just check if we can import the authorizer
import sys
sys.path.append('src')

try:
    from auth.authorizer import lambda_handler
    print("Authorizer imported successfully")

    # Test locally
    result = lambda_handler(authorizer_event, {})
    print("Authorizer result:")
    print(json.dumps(result, indent=2))

except Exception as e:
    print(f"Error: {str(e)}")

