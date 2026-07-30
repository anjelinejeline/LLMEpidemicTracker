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
logger.propagate = False 

formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)d]: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

if logger.hasHandlers():
    logger.handlers.clear()

file_handler = RotatingFileHandler(
    "results/wn_alert_log.log",  
    maxBytes=5 * 1024 * 1024,    # 5 MB
    backupCount=99999                
)
file_handler.setFormatter(formatter) 
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)  
logger.addHandler(console_handler)


def daily_job():
    logger.info("Starting scheduled daily epidemiology run.")
    
    # Target yesterday's date window
    today = datetime.now()
    target_day = today - timedelta(days=1) 
    
    start_str = target_day.strftime("%Y-%m-%d")
    end_str = target_day.strftime("%Y-%m-%d")

    queries = [
        {"iso": country, "start": start_str, "end": end_str, "disease": "WestNileDisease"}
        for country in ["IT", "GR", "ES", "HU", "DE"]
    ]
      
    try:
        logger.info(f"Triggering pipeline with active queries for date: {start_str}.")
        classified_records, alerts = run_pipeline(queries)
    except (TypeError, Exception):
        logger.warning("Daily run skipped or pipeline failed", exc_info=True)
        logger.info("Scheduler daemon remains active. Waiting for the next scheduled run.")
        return 

    # Save classified records (JSONL + MongoDB) 
    if classified_records:
        # Local JSONL storage
        classified_file = "results/classified_records.jsonl" 
        try:
            with open(classified_file, "a", encoding="utf-8") as f:
                for article_id, classification in classified_records.items():
                    record = {"id": article_id, **classification}
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.info(f"Appended {len(classified_records)} new records to classified_records.jsonl.")
        except Exception:
            logger.exception("Failed to write classified records to disk!")

        # MongoDB storage 
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
        logger.warning(f"No new classified records returned for {start_str}.")
    
    # Save alerts (JSONL + MongoDB)
    if alerts:
        # Local JSONL storage
        alerts_file = "results/alerts.jsonl"
        try:
            with open(alerts_file, "a", encoding="utf-8") as f:
                for alert in alerts:
                    f.write(json.dumps(alert, ensure_ascii=False) + "\n")
            logger.info(f"Appended {len(alerts)} daily aggregated alerts to alerts.jsonl.")
        except Exception:
            logger.exception("Failed to write daily alerts to disk!")

        # MongoDB storage
        try:
            for alert in alerts:
                alerts_collection.insert_one(alert.copy())
            logger.info(f"Inserted {len(alerts)} alerts into MongoDB collection.")
        except Exception:
            logger.exception("Failed to insert daily alerts into MongoDB collection.")
    else:
        logger.warning(f"No daily alerts generated for {start_str}.")


if __name__ == "__main__":
    # Run once immediately upon start
    daily_job()
    
    # Schedule to run every day at midnight
    schedule.every().day.at("00:00").do(daily_job)
    
    logger.info("Scheduler daemon started. Waiting for next execution at 00:00.")
    while True:
        schedule.run_pending()
        time.sleep(1)
    
