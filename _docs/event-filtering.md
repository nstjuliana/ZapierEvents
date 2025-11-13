# Event Filtering & Search Documentation

## Overview

The Event Filtering & Search feature provides powerful query capabilities for the `GET /events` endpoint, allowing you to filter events by payload fields, metadata, dates, and other attributes using various comparison operators.

**Key Features:**
- Filter by any payload or metadata field
- Support for nested JSON paths (e.g., `payload.customer.email`)
- Multiple comparison operators (eq, gt, gte, lt, lte, ne, contains, startswith)
- Date range filtering (created_after/before, delivered_after/before)
- Combine multiple filters with AND logic
- Backward compatible with existing `status`, `limit`, and `cursor` parameters

---

## Query Syntax

### Basic Syntax

```
GET /events?field=value
GET /events?field[operator]=value
```

### Field Paths

Fields can be specified using dot notation for nested JSON structures:

- **Top-level fields**: `status`, `event_type`, `created_at`
- **Payload fields**: `payload.order_id`, `payload.amount`
- **Metadata fields**: `metadata.source`, `metadata.version`
- **Nested paths**: `payload.customer.email`, `metadata.billing.country`

### Reserved Parameters

These parameters are **not** treated as filters and have special meaning:

- `status` - Filter by delivery status (uses efficient database index)
- `limit` - Maximum number of results (default: 50, max: 100)
- `cursor` - Pagination cursor (not supported with custom filters)

---

## Supported Operators

### Equality Operators

| Operator | Syntax | Description | Example |
|----------|--------|-------------|---------|
| `eq` | `?field=value` | Exact match (default) | `?payload.order_id=12345` |
| `ne` | `?field[ne]=value` | Not equal | `?status[ne]=failed` |

### Comparison Operators

| Operator | Syntax | Description | Example |
|----------|--------|-------------|---------|
| `gt` | `?field[gt]=value` | Greater than | `?payload.amount[gt]=100` |
| `gte` | `?field[gte]=value` | Greater than or equal | `?payload.amount[gte]=100` |
| `lt` | `?field[lt]=value` | Less than | `?payload.amount[lt]=1000` |
| `lte` | `?field[lte]=value` | Less than or equal | `?payload.amount[lte]=1000` |

### String Operators

| Operator | Syntax | Description | Example |
|----------|--------|-------------|---------|
| `contains` | `?field[contains]=text` | String contains substring | `?payload.email[contains]=@gmail.com` |
| `startswith` | `?field[startswith]=prefix` | String starts with prefix | `?event_type[startswith]=order.` |

### Date Filters

Special date filter parameters that work with ISO 8601 timestamps:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `created_after` | Events created after this date | `?created_after=2024-01-15T00:00:00Z` |
| `created_before` | Events created before this date | `?created_before=2024-01-16T00:00:00Z` |
| `delivered_after` | Events delivered after this date | `?delivered_after=2024-01-15T10:00:00Z` |
| `delivered_before` | Events delivered before this date | `?delivered_before=2024-01-16T00:00:00Z` |

---

## Examples

### Basic Filtering

```bash
# Filter by exact payload field value
GET /events?payload.order_id=12345

# Filter by metadata field
GET /events?metadata.source=ecommerce

# Filter by event type
GET /events?event_type=order.created
```

### Numeric Comparisons

```bash
# Find events with amount >= 100
GET /events?payload.amount[gte]=100

# Find events with amount < 50
GET /events?payload.amount[lt]=50

# Find events with amount between 100 and 1000
GET /events?payload.amount[gte]=100&payload.amount[lte]=1000
```

### String Operations

```bash
# Find events with email containing "gmail"
GET /events?payload.customer.email[contains]=gmail

# Find events with event type starting with "order."
GET /events?event_type[startswith]=order.

# Find events NOT in failed status
GET /events?status[ne]=failed
```

### Nested Path Filtering

```bash
# Filter by nested customer email
GET /events?payload.customer.email=user@example.com

# Filter by deeply nested billing country
GET /events?payload.billing.address.country=US

# Filter by nested metadata
GET /events?metadata.tracking.campaign_id=summer-2024
```

### Date Filtering

```bash
# Events created after a specific date
GET /events?created_after=2024-01-15T00:00:00Z

# Events created in a date range
GET /events?created_after=2024-01-15T00:00:00Z&created_before=2024-01-16T00:00:00Z

# Events delivered today
GET /events?delivered_after=2024-01-15T00:00:00Z&delivered_before=2024-01-16T00:00:00Z
```

### Combining Filters

```bash
# Multiple filters (AND logic)
GET /events?status=delivered&payload.amount[gte]=50&metadata.source=api

# Status filter + custom filters
GET /events?status=pending&payload.order_id=12345

# Date + payload filters
GET /events?created_after=2024-01-15T00:00:00Z&payload.status=failed
```

### Complex Real-World Examples

```bash
# Find all failed high-value orders from ecommerce
GET /events?status=failed&payload.amount[gte]=1000&metadata.source=ecommerce

# Find all Gmail users who placed orders today
GET /events?payload.customer.email[contains]=@gmail.com&created_after=2024-01-15T00:00:00Z&event_type=order.created

# Find all events from a specific campaign that haven't been delivered
GET /events?metadata.campaign_id=summer-2024&status[ne]=delivered

# Find events with specific order status and amount range
GET /events?payload.status=processing&payload.amount[gte]=100&payload.amount[lt]=500
```

---

## Technical Implementation

### Architecture

The filtering system is implemented as a **reusable utility** that can be used by multiple endpoints:

1. **Query Parameter Parsing** (`utils/filters.py`)
   - `parse_filter_params()` - Extracts filter conditions from query string
   - `EventFilter` class - Represents individual filter conditions
   - Supports nested JSON paths and operator parsing

2. **DynamoDB Integration** (`storage/dynamodb.py`)
   - `list_events()` method accepts optional `filters` parameter
   - Applies filters after retrieving events from database
   - Handles both status-based GSI queries and custom filters

3. **Handler Integration** (`handlers/events.py`)
   - `GET /events` endpoint parses all query parameters
   - Passes filter conditions to DynamoDB client
   - Maintains backward compatibility

### Filter Processing Flow

```
1. Request: GET /events?payload.order_id=12345&status=pending
   ↓
2. Handler parses query_params: {'payload.order_id': '12345', 'status': 'pending'}
   ↓
3. parse_filter_params() extracts filters: {'payload.order_id': EventFilter(...)}
   (status is reserved, not included in filters)
   ↓
4. DynamoDB list_events() called with:
   - status='pending' (uses GSI for efficiency)
   - filters={'payload.order_id': EventFilter(...)}
   ↓
5. Events retrieved from DynamoDB
   ↓
6. apply_filters_to_events() filters in-memory for JSON fields
   ↓
7. Filtered results returned
```

### Field Type Detection

The system automatically detects field types:

- **JSON fields**: Fields starting with `payload.` or `metadata.`
  - Filtered in-memory after deserialization
  - Supports nested paths
  
- **Date fields**: `created_at`, `delivered_at`, `created_after`, `created_before`, etc.
  - Parsed as ISO 8601 timestamps
  - Supports comparison operators
  
- **Direct fields**: All other fields (e.g., `status`, `event_type`)
  - Can use DynamoDB FilterExpression when possible
  - Fallback to in-memory filtering

### Performance Considerations

1. **Status Filtering**: When used alone, leverages DynamoDB GSI for efficient queries
2. **JSON Field Filtering**: Requires fetching events and filtering in-memory
   - System fetches up to 3x the requested limit (max 300) to account for filtered results
   - May consume more read capacity units
3. **Combined Filters**: Status filter uses GSI, then custom filters applied in-memory
4. **Pagination**: Cursor-based pagination is disabled when custom filters are used

---

## Limitations

### Current Limitations

1. **Pagination with Filters**: Cursor-based pagination (`cursor` parameter) is not supported when custom filters are used. The system will return results but won't provide a cursor for the next page.

2. **Performance**: JSON field filtering requires scanning/querying the database and filtering in-memory, which:
   - May be slower for large datasets
   - Consumes more read capacity units
   - Fetches more data than requested to account for filtered-out results

3. **Complex Queries**: The system uses AND logic for all filters. OR logic and more complex query structures are not currently supported.

4. **Index Usage**: Only the `status` field uses database indexes efficiently. Other filters are applied after data retrieval.

### Future Enhancements

Potential improvements for future versions:

- **GSI Support**: Create Global Secondary Indexes for commonly filtered fields
- **OR Logic**: Support for OR conditions between filters
- **Advanced Operators**: `in`, `between`, `regex` operators
- **Cursor Support**: Proper pagination cursors with filters
- **Query Optimization**: Smarter fetching strategies based on filter types

---

## Best Practices

### 1. Use Status Filter When Possible

```bash
# ✅ Efficient - uses database index
GET /events?status=pending

# ⚠️ Less efficient - requires in-memory filtering
GET /events?payload.status=pending
```

### 2. Combine Status with Custom Filters

```bash
# ✅ Efficient - status uses index, then filters in-memory
GET /events?status=delivered&payload.amount[gte]=100

# ⚠️ Less efficient - no index usage
GET /events?payload.amount[gte]=100
```

### 3. Use Specific Field Paths

```bash
# ✅ Specific and clear
GET /events?payload.order_id=12345

# ⚠️ Less specific
GET /events?order_id=12345  # Won't match if order_id is nested
```

### 4. Limit Result Sets

```bash
# ✅ Reasonable limit
GET /events?status=pending&limit=50

# ⚠️ Large limit may be slow with filters
GET /events?payload.amount[gte]=100&limit=100
```

### 5. Date Format

Always use ISO 8601 format with timezone:

```bash
# ✅ Correct format
GET /events?created_after=2024-01-15T00:00:00Z

# ⚠️ May not parse correctly
GET /events?created_after=2024-01-15
```

---

## Error Handling

### Invalid Filter Parameters

Invalid filter parameters are **silently ignored** with a warning logged:

```bash
# Invalid operator - ignored
GET /events?payload.order_id[invalid]=12345
# Result: Returns all events (filter ignored)

# Invalid field format - ignored  
GET /events?payload..order_id=12345
# Result: Returns all events (filter ignored)
```

### Missing Fields

If a filter references a field that doesn't exist in events, those events are excluded:

```bash
# Only events with payload.customer.email will be returned
GET /events?payload.customer.email[contains]=gmail
# Events without this field are filtered out
```

### Type Mismatches

Type mismatches in comparisons result in events being filtered out:

```bash
# String comparison on numeric field - may not work as expected
GET /events?payload.amount[contains]=100
# Use numeric operators instead: payload.amount[gte]=100
```

---

## API Response Format

Filtered results return the same format as regular list events:

```json
[
  {
    "event_id": "evt_abc123xyz456",
    "event_type": "order.created",
    "payload": {
      "order_id": "12345",
      "amount": 99.99,
      "customer": {
        "email": "user@example.com"
      }
    },
    "metadata": {
      "source": "ecommerce"
    },
    "status": "delivered",
    "created_at": "2024-01-15T10:30:01Z",
    "delivered_at": "2024-01-15T10:30:02Z",
    "delivery_attempts": 1,
    "message": "Event retrieved successfully"
  }
]
```

---

## Integration with Other Features

### Replay Endpoint (Future)

The filtering system is designed to be reusable. Future replay functionality can leverage the same filtering:

```bash
# Future: Replay all failed events matching criteria
POST /events/replay?status=failed&payload.amount[gte]=1000
# Internally calls list_events() with filters, then replays each event
```

### Bulk Operations (Future)

Any bulk operation can reuse the filtering logic:

```bash
# Future: Delete all events matching criteria
DELETE /events?status=failed&created_before=2024-01-01T00:00:00Z
```

---

## Troubleshooting

### No Results Returned

**Possible causes:**
1. Filters are too restrictive
2. Field path doesn't match event structure
3. Type mismatch in comparison

**Solution:** Remove filters one by one to identify the issue

### Slow Performance

**Possible causes:**
1. Large dataset with JSON field filtering
2. No status filter to use database index
3. Very large limit value

**Solution:** 
- Add `status` filter when possible
- Reduce `limit` value
- Use more specific filters to reduce result set

### Unexpected Results

**Possible causes:**
1. Field path typo
2. Operator not supported for field type
3. Date format incorrect

**Solution:** Check field paths match your event structure and use correct operators

---

## Code Examples

### Python Client Example

```python
import requests

# Basic filtering
response = requests.get(
    "https://api.example.com/events",
    params={
        "status": "pending",
        "payload.order_id": "12345"
    }
)

# Complex filtering
response = requests.get(
    "https://api.example.com/events",
    params={
        "status": "delivered",
        "payload.amount[gte]": "100",
        "metadata.source": "ecommerce",
        "created_after": "2024-01-15T00:00:00Z",
        "limit": "50"
    }
)
```

### cURL Examples

```bash
# Simple filter
curl "https://api.example.com/events?payload.order_id=12345"

# Multiple filters
curl "https://api.example.com/events?status=delivered&payload.amount[gte]=100&limit=10"

# Date range
curl "https://api.example.com/events?created_after=2024-01-15T00:00:00Z&created_before=2024-01-16T00:00:00Z"
```

### JavaScript/Node.js Example

```javascript
const axios = require('axios');

// Basic filtering
const response = await axios.get('https://api.example.com/events', {
  params: {
    status: 'pending',
    'payload.order_id': '12345'
  }
});

// Complex filtering with operators
const response = await axios.get('https://api.example.com/events', {
  params: {
    status: 'delivered',
    'payload.amount[gte]': '100',
    'metadata.source': 'ecommerce',
    created_after: '2024-01-15T00:00:00Z',
    limit: 50
  }
});
```

---

## Summary

The Event Filtering & Search feature provides powerful, flexible querying capabilities for events. While it has some performance limitations for large datasets, it enables powerful debugging, auditing, and business intelligence use cases without requiring infrastructure changes.

**Key Takeaways:**
- ✅ Use `status` filter when possible for best performance
- ✅ Combine multiple filters with AND logic
- ✅ Support for nested JSON paths and various operators
- ✅ Backward compatible with existing parameters
- ⚠️ Pagination cursors disabled with custom filters
- ⚠️ JSON field filtering requires in-memory processing

For questions or issues, refer to the main API documentation or check the codebase in `src/utils/filters.py` and `src/handlers/events.py`.

