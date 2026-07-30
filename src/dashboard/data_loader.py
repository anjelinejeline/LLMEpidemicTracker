import os
import json
import pandas as pd
import streamlit as st
from urllib.parse import quote_plus
from pymongo import MongoClient, DESCENDING

# Uncomment this section if data are loaded from a local folder 
# # Outer function (Runs on every user interaction/refresh)
# def load_and_process_data():
#     alerts_path = "results/alerts.jsonl"
    
#     # Get the file's last modified timestamp as our cache key
#     mtime = os.path.getmtime(alerts_path) if os.path.exists(alerts_path) else 0.0
    
#     # Pass the timestamp to the cached worker function
#     return _cached_load_and_process(mtime)

# # Inner function (Cached)
# @st.cache_data()
# def _cached_load_and_process(timestamp):
#     alerts_path = "results/alerts.jsonl"
#     centroids_path = "src/dashboard/country_centroids.csv"
    
#     with open(alerts_path, "r") as f:
#         df_alerts = pd.read_json(f, lines=True)
    
#     with open(centroids_path, "r") as f:
#         df_centroids = pd.read_csv(f)

#     df_alerts["pub_date"] = pd.to_datetime(df_alerts["pub_date"]).dt.date
    
#     df_alerts_mapped = pd.merge(
#         df_alerts, 
#         df_centroids, 
#         left_on="iso2_code", 
#         right_on="iso_alpha2", 
#         how="inner"
#     )
#     return df_alerts_mapped

# MongoDB conncetion
@st.cache_resource
def get_mongo_collection():
    with open("secrets/config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    mongo_uri = (
        f"mongodb://{config['MONGO_USERNAME']}:"
        f"{quote_plus(config['MONGO_PASSWORD'])}"
        f"@{config['MONGO_HOST']}:{config['MONGO_PORT']}"
        f"/{config['MONGO_DB']}"
    )
    client = MongoClient(mongo_uri)
    return client[config["MONGO_DB"]]["alerts"]


# Outer function: fetches only the latest document _id as a lightweight cache key
def load_and_process_data():
    try:
        collection = get_mongo_collection()
        # Find the single most recent record sorted by _id (or updated_at / pub_date)
        latest_doc = collection.find_one({}, sort=[("_id", DESCENDING)], projection={"_id": 1})
        
        # Convert ObjectId to string to use as Streamlit's cache key
        cache_key = str(latest_doc["_id"]) if latest_doc else "empty_db"
    except Exception:
        cache_key = "db_error"

    # Streamlit compares 'cache_key'. If it hasn't changed, it returns the cached DataFrame instantly.
    return _cached_load_and_process(cache_key)


# Inner function: cached data loading step
@st.cache_data()
def _cached_load_and_process(cache_key):
    collection = get_mongo_collection()
    
    # Query all records, excluding raw MongoDB _id from the DataFrame output
    alerts_cursor = collection.find({}, {"_id": 0})
    alerts_list = list(alerts_cursor)

    if not alerts_list:
        return pd.DataFrame()

    df_alerts = pd.DataFrame(alerts_list)

    # Load country centroids
    centroids_path = "src/dashboard/country_centroids.csv"
    df_centroids = pd.read_csv(centroids_path)

    # Convert date format
    df_alerts["pub_date"] = pd.to_datetime(df_alerts["pub_date"]).dt.date

    # Merge with spatial coordinates
    df_alerts_mapped = pd.merge(
        df_alerts,
        df_centroids,
        left_on="iso2_code",
        right_on="iso_alpha2",
        how="inner"
    )
    return df_alerts_mapped