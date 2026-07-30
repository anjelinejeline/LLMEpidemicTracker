import json 
import pandas as pd 
import logging
from pymongo import MongoClient
from urllib.parse import quote_plus
from src.eios_client import  EIOSClient, parallel_fetch_countries, parallel_fetch_full_texts
from src.translator import parallel_translate_summaries, parallel_translate_full_texts
from src.llm import EIOSClassifier
from src.alert import daily_aggregation


logger = logging.getLogger("wn_alert_logger")

def load_config():
    with open("secrets/config.json", "r") as f:
        return json.load(f)

def run_pipeline(queries):
    logger.info("Loading EIOS configurations.")
    config=load_config()

    # Initialize the eios_client
    eios_client = EIOSClient(
        base_url=config["EIOS_BASE_URL"],
        api_version=config["EIOS_API_VERSION"],
        tenant_id=config["EIOS_TENANT_ID"],
        client_id=config["EIOS_CLIENT_ID"],
        client_secret=config["EIOS_CLIENT_SECRET"],
        scope=config["EIOS_SCOPE"]
    )

    # Fetch the data
    logger.info(f"Fetching raw data from EIOS for {len(queries)} active queries.")
    df_raw = parallel_fetch_countries(eios_client, queries)

    if df_raw.empty:
        logger.warning("Pipeline stop: No articles found for these queries today.")
        return None

    # Translate the summaries 
    num_articles = len(df_raw)
    logger.info(f"Translating {num_articles} article summaries to English.")
    df_en = parallel_translate_summaries(df_raw, num_chunks=3, n_jobs=-1)

    # Process the metadata
    df_en["source_name"] = df_en["source"].apply(lambda x: x.get("name") if isinstance(x, dict) else None)
    df_en["url"] = df_en["source"].apply(lambda x: x.get("url") if isinstance(x, dict) else None)
    df_en = df_en[["id", "pubdate", "en_text", "source_name", "url"]]
    df_en.rename(columns={"source_name": "source"},inplace=True)
    translated_records = df_en.to_dict(orient="records")

    # Classify with vLLM
    logger.info(f"Running vLLM classification (Qwen2.5-14B) on {len(translated_records)} translated summaries.")
    classifier = EIOSClassifier(batch_size=64, model_checkpoint="anjelinejeline/Qwen2.5-14B-Instruct-epi")
    classified_records = classifier.classify(translated_records)

    # Fetch the full-texts 
    article_ids = list(classified_records.keys())
    logger.info(f"Retrieving full HTML texts for {len(article_ids)} classified articles.")
    full_texts = parallel_fetch_full_texts(eios_client, list(classified_records.keys()))
    
    # Translate 
    logger.info("Translating retrieved full texts in parallel.")
    translated_full_texts = parallel_translate_full_texts(full_texts, n_jobs=-1)
    
    # Inject the full-texts into the classified_records
    for article_id, article_data in classified_records.items():
        text_data = translated_full_texts.get(article_id)
        if text_data:
            article_data["full_text"] = text_data["original"]
            article_data["full_text_en"] = text_data["translated"]
        else:
            article_data["full_text"] = ""
            article_data["full_text_en"] = ""

    # Aggregate
    logger.info("Aggregating classified records to generate alerts.")
    alerts = daily_aggregation(classified_records)

    logger.info("Pipeline processing completed successfully.")
    return classified_records, alerts
    



