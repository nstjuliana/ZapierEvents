"""
Module: settings.py
Description: Application configuration using pydantic-settings.

Configures all application settings from environment variables with
validation and defaults. Supports .env files for local development.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application settings
    app_name: str = Field(default="Zapier Triggers API", description="Application name")
    app_version: str = Field(default="0.2.5", description="Application version")
    log_level: str = Field(default="INFO", description="Logging level")

    # AWS settings
    aws_region: str = Field(default="us-east-1", description="AWS region")
    stage: str = Field(default="dev", description="Deployment stage")

    # DynamoDB settings
    events_table_name: str = Field(
        ...,
        description="Name of the DynamoDB events table"
    )
    api_keys_table_name: str = Field(
        ...,
        description="Name of the DynamoDB API keys table"
    )

    # SQS settings
    inbox_queue_url: str = Field(
        ...,
        description="URL of the SQS inbox queue for failed deliveries"
    )

    # Delivery settings
    zapier_webhook_url: str = Field(
        ...,
        description="Zapier webhook URL for push delivery"
    )
    delivery_timeout: int = Field(
        default=10,
        ge=1,
        le=30,
        description="HTTP timeout in seconds for delivery attempts"
    )

    # Security settings
    bcrypt_work_factor: int = Field(
        default=13,
        ge=10,
        le=16,
        description="bcrypt work factor for API key hashing"
    )

    @field_validator('events_table_name', 'api_keys_table_name')
    @classmethod
    def validate_table_names(cls, v: str) -> str:
        """Validate DynamoDB table names."""
        if not v or not isinstance(v, str):
            raise ValueError("Table name must be a non-empty string")

        # Allow alphanumeric, hyphens, underscores
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError(
                "Table name must contain only letters, numbers, hyphens, and underscores"
            )

        return v

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a valid logging level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of: {', '.join(valid_levels)}")
        return v.upper()


# Global settings instance
settings = Settings()

