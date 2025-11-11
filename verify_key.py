#!/usr/bin/env python3

import sys
sys.path.append('src')
from auth.api_key import verify_api_key

# Test the API key against the stored hash
api_key = 'sk_GJQjTTzgIHonQfR4cUMf0_3B_pu5Q5Ww'
stored_hash = 'pbkdf2_sha256$100000$f6657c1e2f5fa64e9d842add1e599df9befb52824f672918bd34fcd1e64b5f9a$fb514bcead43fcaf6578577e39e9efc19a085748d4d23e918f129ff0dfc3f7c1'

result = verify_api_key(api_key, stored_hash)
print(f'API key verification: {result}')
