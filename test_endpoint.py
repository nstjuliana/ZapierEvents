#!/usr/bin/env python3
"""
Test the /events endpoint with authentication.
"""

import requests
import json

# API details
url = "https://mmghecrjr5.execute-api.us-east-1.amazonaws.com/events"
api_key = "sk_GJQjTTzgIHonQfR4cUMf0_3B_pu5Q5Ww"

# Test data
test_payload = {
    "event_type": "test.event",
    "payload": {
        "message": "Hello World",
        "timestamp": "2025-11-10T20:35:00Z"
    },
    "metadata": {
        "source": "test-script",
        "version": "1.0"
    }
}

# Headers
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

print("Testing POST /events endpoint...")
print(f"URL: {url}")
print(f"API Key: {api_key[:10]}...")
print(f"Payload: {json.dumps(test_payload, indent=2)}")
print()

try:
    response = requests.post(url, headers=headers, json=test_payload)

    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print()

    if response.status_code == 201:
        print("SUCCESS! Event created successfully.")
        print("Response:")
        print(json.dumps(response.json(), indent=2))
    else:
        print("ERROR!")
        print("Response:")
        try:
            print(json.dumps(response.json(), indent=2))
        except:
            print(response.text)

except Exception as e:
    print(f"REQUEST FAILED: {str(e)}")
