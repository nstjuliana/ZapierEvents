"""
Module: metrics.py
Description: CloudWatch custom metrics publishing.

Publishes application metrics to CloudWatch for monitoring
event ingestion rates, delivery success, and API performance.

Key Components:
- MetricsClient: CloudWatch metrics client
- put_metric(): Publish individual metrics
- Graceful error handling for metrics failures
- Structured logging for metric operations

Dependencies: boto3, typing, logger
Author: Triggers API Team
"""

import boto3
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class MetricsClient:
    """CloudWatch metrics client."""

    def __init__(self, namespace: str = "TriggersAPI"):
        """
        Initialize metrics client.

        Args:
            namespace: CloudWatch metrics namespace
        """
        self.namespace = namespace
        self.cloudwatch = boto3.client('cloudwatch')

        logger.info(
            "Metrics client initialized",
            namespace=namespace
        )

    def put_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = 'Count',
        dimensions: Optional[dict] = None
    ) -> None:
        """
        Publish a metric to CloudWatch.

        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Metric unit (Count, Seconds, etc.)
            dimensions: Optional metric dimensions
        """
        try:
            metric_data = {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit
            }

            if dimensions:
                metric_data['Dimensions'] = [
                    {'Name': k, 'Value': v}
                    for k, v in dimensions.items()
                ]

            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=[metric_data]
            )

            logger.debug(
                "Metric published to CloudWatch",
                metric_name=metric_name,
                value=value,
                unit=unit,
                dimensions=dimensions,
                namespace=self.namespace
            )

        except Exception as e:
            # Don't fail request if metrics fail
            logger.warning(
                "Failed to publish metric",
                metric_name=metric_name,
                value=value,
                error=str(e),
                namespace=self.namespace
            )
