import os
import logging
from pymongo import MongoClient, ASCENDING

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stataudit-migration")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "stataudit")

def run_migrations():
    logger.info(f"Connecting to MongoDB at {MONGO_URI}...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    # 1. Sessions Collection TTL Index
    logger.info("Setting up TTL index for 'sessions' collection...")
    db["sessions"].create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    
    # 2. Rate Limits Collection TTL Index
    logger.info("Setting up TTL index for 'rate_limits' collection...")
    db["rate_limits"].create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    
    # 3. Rate Limit Breaches Collection TTL Index
    logger.info("Setting up TTL index for 'rate_limit_breaches' collection...")
    db["rate_limit_breaches"].create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    
    # 4. IP Bans Collection TTL Index
    logger.info("Setting up TTL index for 'ip_bans' collection...")
    db["ip_bans"].create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    
    logger.info("Database migration successfully completed!")

if __name__ == "__main__":
    run_migrations()
