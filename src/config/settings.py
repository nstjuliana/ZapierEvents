"""
Module: settings.py
Description: Application configuration using pydantic-settings.
"""

from pydantic import Field
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
    app_version: str = Field(default="0.1.0", description="Application version")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # AWS settings
    aws_region: str = Field(default="us-east-1", description="AWS region")
    stage: str = Field(default="dev", description="Deployment stage")


# Global settings instance
settings = Settings()

