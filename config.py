"""Configuration module for HyDE Lambda."""

import os
from typing import Any, Optional

# Load .env file for local development only (not needed in Lambda)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available in Lambda environment, which is fine
    pass


def get_env_var(var_name: str, required: bool = True) -> Optional[str]:
    """Get environment variable with optional requirement check"""
    value = os.getenv(var_name)
    if required and value is None:
        raise ValueError(f"Required environment variable {var_name} is not set")
    return value


# External API configuration (replaces direct MongoDB access)
SEARCH_API_BASE_URL = get_env_var("SEARCH_API_BASE_URL")
SEARCH_API_KEY = get_env_var("SEARCH_API_KEY", required=False) or get_env_var("ADMIN_API_KEY", required=False)
SEARCH_API_TIMEOUT = float(get_env_var("SEARCH_API_TIMEOUT", required=False) or 10)

# Redis Configuration (Upstash REST)
UPSTASH_REDIS_REST_URL = get_env_var("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = get_env_var("UPSTASH_REDIS_REST_TOKEN")

# Initialize Upstash Redis client
from upstash_redis import Redis as UpstashRedis

redis_client = UpstashRedis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)

# Admin API Key for compatibility with legacy callers
ADMIN_API_KEY = get_env_var("ADMIN_API_KEY", required=False)
