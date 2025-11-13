"""
Module: batch_helpers.py
Description: Utility functions for batch operations.

Provides helper functions for processing large batches of data by splitting
them into smaller chunks and merging results from multiple operations.

Key Components:
- chunk_list(): Split lists into smaller chunks
- validate_batch_size(): Validate batch size constraints

Dependencies: typing
Author: Triggers API Team
"""

from typing import List, TypeVar, Any, Dict

T = TypeVar('T')


def chunk_list(items: List[T], chunk_size: int) -> List[List[T]]:
    """
    Split a list into smaller chunks of specified size.

    Args:
        items: List to split into chunks
        chunk_size: Maximum size of each chunk

    Returns:
        List of chunks, where each chunk is a list of items

    Raises:
        ValueError: If chunk_size is not positive

    Example:
        >>> chunk_list([1, 2, 3, 4, 5], 2)
        [[1, 2], [3, 4], [5]]
    """
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    chunks = []
    for i in range(0, len(items), chunk_size):
        chunks.append(items[i:i + chunk_size])

    return chunks


def validate_batch_size(items: List[Any], max_size: int) -> None:
    """
    Validate that a batch doesn't exceed the maximum allowed size.

    Args:
        items: List of items to validate
        max_size: Maximum allowed batch size

    Raises:
        ValueError: If batch size exceeds maximum

    Example:
        >>> validate_batch_size([1, 2, 3], 5)  # OK
        >>> validate_batch_size([1, 2, 3], 2)  # Raises ValueError
    """
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    if len(items) > max_size:
        raise ValueError(f"batch size cannot exceed {max_size} items")


def merge_batch_results(chunk_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge results from multiple batch operations into a single result.

    This is useful when batch operations are processed in chunks and
    individual results need to be combined.

    Args:
        chunk_results: List of result dictionaries from batch operations

    Returns:
        Merged result dictionary with combined statistics

    Example:
        >>> results = [
        ...     {"successful": 10, "failed": 2, "items": ["a", "b"]},
        ...     {"successful": 8, "failed": 1, "items": ["c", "d"]}
        ... ]
        >>> merge_batch_results(results)
        {"successful": 18, "failed": 3, "items": ["a", "b", "c", "d"]}
    """
    if not chunk_results:
        return {}

    merged = {}
    for result in chunk_results:
        for key, value in result.items():
            if isinstance(value, list):
                # Concatenate lists
                if key not in merged:
                    merged[key] = []
                merged[key].extend(value)
            elif isinstance(value, (int, float)):
                # Sum numeric values
                merged[key] = merged.get(key, 0) + value
            else:
                # For other types, keep the last value (or could raise error)
                merged[key] = value

    return merged
