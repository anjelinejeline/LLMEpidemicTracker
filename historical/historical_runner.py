import os 
import time
import json
from datetime import datetime, timedelta
from src.pipeline import run_pipeline
import schedule 
import logging
from logging.handlers import RotatingFileHandler
from urllib.parse import quote_plus                 
from pymongo import MongoClient   


os.makedirs("results", exist_ok=True)

with open("secrets/config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# Connect to MongoDB
mongo_uri = (
    f"mongodb://{config['MONGO_USERNAME']}:"
    f"{quote_plus(config['MONGO_PASSWORD'])}"
    f"@{config['MONGO_HOST']}:{config['MONGO_PORT']}"
    f"/{config['MONGO_DB']}"
)

mongo_client = MongoClient(mongo_uri) 
mongo_db = mongo_client[config["MONGO_DB"]]

# Create collections if missing
existing_collections = mongo_db.list_collection_names()   

if "classified_records" not in existing_collections:
    mongo_db.create_collection("classified_records")

if "alerts" not in existing_collections:
    mongo_db.create_collection("alerts")

classified_collection = mongo_db["classified_records"]    
alerts_collection = mongo_db["alerts"]    

# Define the logger
logger = logging.getLogger("wn_alert_logger")
logger.setLevel(logging.INFO)
logger.propagate = False  # Prevents logs from bubbling up to the root logger

formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)d]: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

if logger.hasHandlers():
    logger.handlers.clear()

# Setup the rotating file handler
file_handler = RotatingFileHandler(
    "results/wn_alert_log.log",  
    maxBytes=5 * 1024 * 1024,    # 5 MB
    backupCount=99999                
)
file_handler.setFormatter(formatter) 
logger.addHandler(file_handler)

# Setup the console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)  
logger.addHandler(console_handler)


def run_historical_backfill():

    # Target countries
    countries = ["IT", "GR", "ES", "HU", "DE"]
    
    # Define boundaries (Jan 1, 2018 -> 2 days before the scheduler/runner.py is launched)
    start_date = datetime(2018, 1, 1)
    end_boundary = datetime(2026, 7, 26)

    # Define chunk size (30 days is ideal)
    chunk_size = timedelta(days=30)
    
    current_pointer = start_date
    logger.info(f"Starting historical backfill: {start_date.strftime('%Y-%m-%d')} to {end_boundary.strftime('%Y-%m-%d')}.")
    
    while current_pointer < end_boundary:
        chunk_end = min(current_pointer + chunk_size, end_boundary)
            
        start_str = current_pointer.strftime("%Y-%m-%d")
        end_str = chunk_end.strftime("%Y-%m-%d")

        logger.info(f"Processing batch: {start_str} to {end_str}")

        queries = [
            {"iso": country, "start": start_str, "end": end_str, "disease": "WestNileDisease"}
            for country in countries
        ]

        try:
            logger.info("Triggering pipeline with active queries.")
            classified_records, alerts = run_pipeline(queries)
        except (TypeError, Exception):
            # Catches both unpacking errors (if run_pipeline returns None) and crashes
            logger.warning(f"Skipping batch {start_str} to {end_str}", exc_info=True)
            current_pointer = chunk_end
            time.sleep(3)
            continue

        # Save classified records (JSONL + MongoDB)
        if classified_records:
            # Local JSONL Storage
            classified_file = "results/classified_records.jsonl" 
            try:
                with open(classified_file, "a", encoding="utf-8") as f:
                    for article_id, classification in classified_records.items():
                        record = {"id": article_id, **classification}
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                logger.info(f"Appended {len(classified_records)} new records to classified_records.jsonl.")
            except Exception:
                logger.exception("Failed to write classified records to disk!")

            # MongoDB Storage 
            try: 
                for article_id, classification in classified_records.items():
                    record = {"_id": article_id, **classification}
                    classified_collection.update_one(
                        {"_id": article_id},
                        {"$set": record},
                        upsert=True
                    )
                logger.info(f"Inserted/updated {len(classified_records)} classified records in MongoDB.")
            except Exception:
                logger.exception("Failed to insert classified records into MongoDB collection.")     
        else:
            logger.warning(f"No new classified records returned for batch {start_str} to {end_str}.")
        
        # Save alerts (JSONL + MongoDB) -
        if alerts:
            # Local JSONL Storage
            alerts_file = "results/alerts.jsonl"
            try:
                with open(alerts_file, "a", encoding="utf-8") as f:
                    for alert in alerts:
                        f.write(json.dumps(alert, ensure_ascii=False) + "\n")
                logger.info(f"Appended {len(alerts)} alerts to alerts.jsonl.")
            except Exception:
                logger.exception("Failed to write daily alerts to disk!")

            # MongoDB Storage
            try:
                for alert in alerts:
                    alerts_collection.insert_one(alert.copy())
                logger.info(f"Inserted {len(alerts)} alerts into MongoDB collection.")
            except Exception:
                logger.exception("Failed to insert daily alerts into MongoDB collection.")
        else:
            logger.warning(f"No daily alerts generated for batch {start_str} to {end_str}.")

        # Advance pointer to the next time window on every iteration
        current_pointer = chunk_end
        
        # API delay
        time.sleep(3)

    logger.info("Historical backfill finished.")


if __name__ == "__main__":
    run_historical_backfill()
