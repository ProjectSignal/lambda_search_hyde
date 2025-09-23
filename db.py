# Minimal db.py for HyDE Lambda
from config import mongo_client, mongo_db, redis_client
from logging_config import setup_logger

logger = setup_logger(__name__)

# MongoDB client setup - using configured client from config.py
client = mongo_client
db = mongo_db

# Redis client setup - using configured client from config.py
r = redis_client

# MongoDB collections actually used by HyDE
searchOutputCollection = db["searchOutput"]
users_collection = db["user"]

# Create only the essential indexes that HyDE actually needs
searchOutputCollection.create_index([
    ("userId", 1),
    ("createdAt", -1)
])