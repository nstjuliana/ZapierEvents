# Event Filtering Quick Reference

## Quick Syntax Guide

### Basic Format
```
GET /events?field=value
GET /events?field[operator]=value
```

### Operators

| Operator | Example | Description |
|----------|---------|-------------|
| `eq` | `?field=value` | Equal (default) |
| `ne` | `?field[ne]=value` | Not equal |
| `gt` | `?field[gt]=100` | Greater than |
| `gte` | `?field[gte]=100` | Greater than or equal |
| `lt` | `?field[lt]=100` | Less than |
| `lte` | `?field[lte]=100` | Less than or equal |
| `contains` | `?field[contains]=text` | Contains substring |
| `startswith` | `?field[startswith]=prefix` | Starts with |

### Date Filters

| Parameter | Example |
|-----------|---------|
| `created_after` | `?created_after=2024-01-15T00:00:00Z` |
| `created_before` | `?created_before=2024-01-16T00:00:00Z` |
| `delivered_after` | `?delivered_after=2024-01-15T10:00:00Z` |
| `delivered_before` | `?delivered_before=2024-01-16T00:00:00Z` |

### Common Examples

```bash
# Exact match
GET /events?payload.order_id=12345

# Numeric comparison
GET /events?payload.amount[gte]=100

# String contains
GET /events?payload.email[contains]=@gmail.com

# Multiple filters
GET /events?status=delivered&payload.amount[gte]=50

# Date range
GET /events?created_after=2024-01-15T00:00:00Z&created_before=2024-01-16T00:00:00Z

# Nested path
GET /events?payload.customer.email=user@example.com
```

### Reserved Parameters (Not Filters)

- `status` - Delivery status filter (uses database index)
- `limit` - Max results (default: 50, max: 100)
- `cursor` - Pagination cursor (disabled with custom filters)

### Tips

✅ **Use status filter for performance**
```bash
GET /events?status=pending&payload.amount[gte]=100
```

✅ **Combine filters with AND logic**
```bash
GET /events?status=delivered&metadata.source=api&payload.amount[gte]=50
```

✅ **Use ISO 8601 for dates**
```bash
GET /events?created_after=2024-01-15T00:00:00Z
```

⚠️ **Pagination cursors disabled with custom filters**

For complete documentation, see [`event-filtering.md`](event-filtering.md)

