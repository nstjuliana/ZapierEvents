"""
Module: filters.py
Description: Event filtering utilities for query parameter parsing and DynamoDB FilterExpression building.

Provides reusable filtering logic that can be used by multiple endpoints (events, replay, etc.)
to filter events by payload, metadata, dates, and other fields with various operators.

Key Components:
- parse_filter_params(): Extract filter conditions from query parameters
- build_dynamodb_filter(): Build DynamoDB FilterExpression and AttributeValues
- Support for nested JSON paths (payload.customer.email)
- Support for comparison operators (gt, gte, lt, lte, ne, contains, startswith)

Author: Triggers API Team
"""

import re
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from utils.logger import get_logger

logger = get_logger(__name__)


class EventFilter:
    """
    Represents a single filter condition.

    Attributes:
        field: The field path (e.g., 'payload.order_id', 'created_at')
        operator: The comparison operator ('eq', 'gt', 'gte', 'lt', 'lte', 'ne', 'contains', 'startswith')
        value: The value to compare against
        field_type: 'json' for payload/metadata, 'date' for timestamp fields, 'direct' for other fields
    """

    def __init__(self, field: str, operator: str, value: Any):
        self.field = field
        self.operator = operator
        self.value = value
        self.field_type = self._determine_field_type()

    def _determine_field_type(self) -> str:
        """Determine the field type based on the field path."""
        if self.field.startswith(('payload.', 'metadata.')):
            return 'json'
        elif self.field in ('created_at', 'delivered_at', 'created_after', 'created_before', 'delivered_after', 'delivered_before'):
            return 'date'
        else:
            return 'direct'

    def __repr__(self):
        return f"EventFilter(field='{self.field}', operator='{self.operator}', value={self.value})"


def parse_filter_params(query_params: Dict[str, Any]) -> Dict[str, EventFilter]:
    """
    Parse query parameters into EventFilter objects.

    Args:
        query_params: Dictionary of query parameters from the request

    Returns:
        Dictionary mapping field names to EventFilter objects

    Examples:
        >>> parse_filter_params({'payload.order_id': '12345', 'metadata.source[gte]': 'ecommerce'})
        {'payload.order_id': EventFilter(field='payload.order_id', operator='eq', value='12345'),
         'metadata.source': EventFilter(field='metadata.source', operator='gte', value='ecommerce')}
    """
    filters = {}

    # Reserved parameters that should not be treated as filters
    reserved_params = {'status', 'limit', 'cursor'}

    for param_key, param_value in query_params.items():
        # Skip reserved parameters
        if param_key in reserved_params:
            continue

        # Skip None/empty values
        if param_value is None or param_value == '':
            continue

        try:
            field, operator = _parse_param_key(param_key)
            filter_obj = EventFilter(field, operator, param_value)
            filters[field] = filter_obj
        except ValueError as e:
            logger.warning(f"Invalid filter parameter '{param_key}': {e}")
            continue

    return filters


def _parse_param_key(param_key: str) -> Tuple[str, str]:
    """
    Parse a parameter key into field and operator.

    Supports formats:
    - field=value (defaults to 'eq' operator)
    - field[operator]=value

    Args:
        param_key: The parameter key (e.g., 'payload.order_id', 'created_at[gte]')

    Returns:
        Tuple of (field, operator)

    Raises:
        ValueError: If the parameter key format is invalid
    """
    # Check for bracket notation: field[operator]
    bracket_match = re.match(r'^([^[\]]+)\[([^[\]]+)\]$', param_key)

    if bracket_match:
        field = bracket_match.group(1)
        operator = bracket_match.group(2)

        # Validate operator
        valid_operators = {'eq', 'gt', 'gte', 'lt', 'lte', 'ne', 'contains', 'startswith'}
        if operator not in valid_operators:
            raise ValueError(f"Invalid operator '{operator}'. Valid operators: {valid_operators}")

    else:
        # No brackets, default to 'eq' operator
        field = param_key
        operator = 'eq'

    # Validate field name
    if not field or not isinstance(field, str):
        raise ValueError("Field name must be a non-empty string")

    # Validate field format
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', field):
        raise ValueError("Field name contains invalid characters")

    return field, operator


def build_dynamodb_filter(filters: Dict[str, EventFilter]) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Build DynamoDB FilterExpression and ExpressionAttributeValues from EventFilter objects.

    Args:
        filters: Dictionary of EventFilter objects

    Returns:
        Tuple of (filter_expression, attribute_values)
        filter_expression: DynamoDB FilterExpression string or None if no filters
        attribute_values: Dictionary of attribute values for the expression

    Examples:
        >>> filters = {'payload.order_id': EventFilter('payload.order_id', 'eq', '12345')}
        >>> build_dynamodb_filter(filters)
        ('payload.#order_id = :payload_order_id_val', {':payload_order_id_val': '12345'})
    """
    if not filters:
        return None, {}

    conditions = []
    attribute_values = {}
    attribute_names = {}

    for filter_obj in filters.values():
        condition, attr_vals, attr_names = _build_single_condition(filter_obj)

        if condition:
            conditions.append(condition)
            attribute_values.update(attr_vals)
            attribute_names.update(attr_names)

    if not conditions:
        return None, {}

    # Combine all conditions with AND
    filter_expression = ' AND '.join(conditions)

    return filter_expression, attribute_values


def _build_single_condition(filter_obj: EventFilter) -> Tuple[str, Dict[str, Any], Dict[str, str]]:
    """
    Build a single DynamoDB condition for one filter.

    Args:
        filter_obj: The EventFilter to convert

    Returns:
        Tuple of (condition_string, attribute_values, attribute_names)
    """
    field = filter_obj.field
    operator = filter_obj.operator
    value = filter_obj.value

    # Generate unique attribute names and values to avoid conflicts
    attr_name = _field_to_attr_name(field)
    attr_value_key = f":{attr_name}_val"

    if filter_obj.field_type == 'json':
        # For JSON fields (payload/metadata), we need to check if the field exists
        # and then apply the condition. Since DynamoDB stores these as JSON strings,
        # we can't directly query nested paths, so we'll use a simpler approach:
        # just check for existence and let the application layer handle filtering.

        # For now, we'll create a condition that always evaluates to true for JSON fields
        # The actual filtering will be done after scanning the data
        return "attribute_exists(event_id)", {}, {}  # This is a placeholder

    elif filter_obj.field_type == 'date':
        # Handle date fields
        if operator in ('eq', 'gt', 'gte', 'lt', 'lte', 'ne'):
            # Convert value to datetime if it's a string
            if isinstance(value, str):
                try:
                    # Assume ISO format
                    parsed_value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    if parsed_value.tzinfo is None:
                        parsed_value = parsed_value.replace(tzinfo=timezone.utc)
                except ValueError:
                    raise ValueError(f"Invalid date format for {field}: {value}")
            else:
                parsed_value = value

            condition = f"#{attr_name} {operator} {attr_value_key}"
            attr_names = {f"#{attr_name}": field}
            attr_values = {attr_value_key: parsed_value.isoformat()}
            return condition, attr_values, attr_names

        else:
            raise ValueError(f"Operator '{operator}' not supported for date fields")

    else:
        # Direct field access
        if operator == 'eq':
            condition = f"#{attr_name} = {attr_value_key}"
        elif operator == 'ne':
            condition = f"#{attr_name} <> {attr_value_key}"
        elif operator == 'gt':
            condition = f"#{attr_name} > {attr_value_key}"
        elif operator == 'gte':
            condition = f"#{attr_name} >= {attr_value_key}"
        elif operator == 'lt':
            condition = f"#{attr_name} < {attr_value_key}"
        elif operator == 'lte':
            condition = f"#{attr_name} <= {attr_value_key}"
        elif operator == 'contains':
            condition = f"contains(#{attr_name}, {attr_value_key})"
        elif operator == 'startswith':
            # DynamoDB doesn't have a direct startswith function, but we can use begins_with
            condition = f"begins_with(#{attr_name}, {attr_value_key})"
        else:
            raise ValueError(f"Unsupported operator '{operator}' for field type '{filter_obj.field_type}'")

        attr_names = {f"#{attr_name}": field}
        attr_values = {attr_value_key: value}
        return condition, attr_values, attr_names


def _field_to_attr_name(field: str) -> str:
    """Convert a field name to a DynamoDB attribute name (replace dots with underscores)."""
    return field.replace('.', '_')


def apply_filters_to_events(events: list, filters: Dict[str, EventFilter]) -> list:
    """
    Apply filters to events that cannot be handled by DynamoDB (JSON path filtering).

    This function is called after retrieving events from DynamoDB to apply
    filtering on JSON fields (payload, metadata) and complex conditions.

    Args:
        events: List of Event objects
        filters: Dictionary of EventFilter objects

    Returns:
        Filtered list of events
    """
    if not filters:
        return events

    filtered_events = []

    for event in events:
        if _event_matches_filters(event, filters):
            filtered_events.append(event)

    return filtered_events


def _event_matches_filters(event, filters: Dict[str, EventFilter]) -> bool:
    """
    Check if an event matches all the given filters.

    Args:
        event: Event object
        filters: Dictionary of EventFilter objects

    Returns:
        True if the event matches all filters, False otherwise
    """
    for filter_obj in filters.values():
        if not _event_matches_filter(event, filter_obj):
            return False
    return True


def _event_matches_filter(event, filter_obj: EventFilter) -> bool:
    """
    Check if an event matches a single filter.

    Args:
        event: Event object
        filter_obj: EventFilter object

    Returns:
        True if the event matches the filter, False otherwise
    """
    field = filter_obj.field
    operator = filter_obj.operator
    value = filter_obj.value

    # Get the field value from the event
    field_value = _get_field_value(event, field)
    if field_value is None:
        return False

    # Apply the operator
    if operator == 'eq':
        return field_value == value
    elif operator == 'ne':
        return field_value != value
    elif operator == 'gt':
        return field_value > value
    elif operator == 'gte':
        return field_value >= value
    elif operator == 'lt':
        return field_value < value
    elif operator == 'lte':
        return field_value <= value
    elif operator == 'contains':
        if isinstance(field_value, str):
            return str(value) in field_value
        return False
    elif operator == 'startswith':
        if isinstance(field_value, str):
            return field_value.startswith(str(value))
        return False
    else:
        return False


def _get_field_value(event, field: str) -> Any:
    """
    Extract a field value from an event, supporting nested paths.

    Args:
        event: Event object
        field: Field path (e.g., 'payload.order_id', 'metadata.source')

    Returns:
        The field value, or None if not found
    """
    parts = field.split('.')
    current = event

    for part in parts:
        if hasattr(current, part):
            current = getattr(current, part)
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None

    return current
