"""
Configuration module for HyDE Lambda
"""
import os
from pymongo import MongoClient
import redis
from typing import Any, Optional


def get_env_var(var_name: str, required: bool = True) -> Optional[str]:
    """Get environment variable with optional requirement check"""
    value = os.getenv(var_name)
    if required and value is None:
        raise ValueError(f"Required environment variable {var_name} is not set")
    return value


# MongoDB Configuration
MONGODB_URI = get_env_var("MONGODB_URI")
DB_NAME = get_env_var("MONGODB_DB_NAME", required=False) or "brace"

# Initialize MongoDB client
mongo_client = MongoClient(MONGODB_URI)
mongo_db = mongo_client[DB_NAME]

# Redis Configuration  
REDIS_HOST = get_env_var("REDIS_HOST", required=False) or "localhost"
REDIS_PORT = int(get_env_var("REDIS_PORT", required=False) or "6379")
REDIS_PASSWORD = get_env_var("REDIS_PASSWORD", required=False)

# Initialize Redis client
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    decode_responses=True
)

# Admin API Key for authentication
ADMIN_API_KEY = get_env_var("ADMIN_API_KEY", required=False)
