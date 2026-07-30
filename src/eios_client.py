import requests
import logging
from datetime import datetime
import time
import pandas as pd
from joblib import Parallel, delayed

logger = logging.getLogger("wn_alert_logger")

# Define the client class
class EIOSClient:

    def __init__(
        self,
        base_url,
        api_version,
        tenant_id,
        client_id,
        client_secret,
        scope,
    ):
        self.base_url = base_url
        self.api_version = api_version
        self.filter_url = f"{base_url}/api/v{api_version}/Items/filter"

        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope

        self._token = None

    # Authorization
    def get_token(self):
        token_url = (
            f"https://login.microsoftonline.com/"
            f"{self.tenant_id}/oauth2/v2.0/token"
        )

        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }

        r = requests.post(token_url, data=payload)
        r.raise_for_status()

        self._token = r.json()["access_token"]
        return self._token

    def headers(self):
        if not self._token:
            self.get_token()

        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    # Filter items by country and disease
    def get_filtered_items(
        self,
        country_iso: str,
        disease: str,
        time_since: str,
        time_until: str | None = None,
        limit: int = 100,
    ):

        if time_until is None:
            time_until = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        all_items = []
        start = 0

        while True:

            query = {
                "rules": [
                    {
                        "name": "filterDate",
                        "operator": "dateRange",
                        "property": "processedOnDate",
                        "value": {
                            "gte": time_since,
                            "lte": time_until,
                        },
                    },
                    {
                        "operator": "in",
                        "property": "countriesIso",
                        "value": [country_iso],
                    },
                    {
                        "name": "categories-1",
                        "operator": "in",
                        "property": "categories",
                        "value": [f"cat:{disease}"],
                    },
                ],
                "groups": [
                    {
                        "name": "includeSourcesGroup",
                        "operator": "or",
                        "rules": [],
                        "groups": [
                            {
                                "name": "sourceFiltersGroup",
                                "operator": "and",
                                "rules": [
                                    {
                                        "name": "sourceSubjects",
                                        "operator": "in",
                                        "property": "source.subject",
                                        "value": [
                                            "General News",
                                            "Medical",
                                            "Agriculture",
                                            "European News",
                                            "Medical Official",
                                            "Financial News",
                                            "Official",
                                            "undefined",
                                            "Environment",
                                            "EU Institutions",
                                            "NGO",
                                            "Nuclear",
                                            "REC",
                                            "Technology",
                                            "Science",
                                        ],
                                    },
                                    {
                                        "name": "duplicatesSourceFiltersRule",
                                        "operator": "equals",
                                        "property": "isDuplicate",
                                        "value": False,
                                    },
                                ],
                                "groups": [],
                            }
                        ],
                    }
                ],
                "operator": "and",
                "start": start,
                "limit": limit,
                "sorts": [
                    {
                        "property": "processedOnDate",
                        "direction": "desc",
                    }
                ],
            }

            r = requests.post(self.filter_url, headers=self.headers(), json=query)
            r.raise_for_status()

            data = r.json()

            items = data.get("result", [])
            total = data.get("count", 0)

            all_items.extend(items)

            start += limit

            if start >= total:
                break

        return all_items

    # Get the full text 
    def get_full_text(self, article_id: str):
        full_text_url = f"{self.base_url}/api/v{self.api_version}/Items/{article_id}"

        r = requests.get(full_text_url, headers=self.headers())
        r.raise_for_status()

        res = r.json()
        return res

# Define a function to retrieve data by country and disease
def fetch_country(client:EIOSClient, country_iso:str, time_since:str, time_until:str | None = None, disease: str = "WestNileDisease") -> list:
    """
    Retrieve data from EIOS by country and disease
    """
    time.sleep(0.1)  
    try:
        items = client.get_filtered_items(
            country_iso=country_iso,
            disease=disease,
            time_since=time_since,
            time_until=time_until
        )
        return items
    except Exception:
        # Fallback: log a warning and return empty list to keep the pipeline running
        logger.warning(f"Error fetching data from EIOS for country {country_iso}.")
        return []

# Define a function to fetch data in parallel
def parallel_fetch_countries(client:EIOSClient, query_list:list, n_jobs: int=-1) -> pd.DataFrame:
    """
    Fetch multiple country in parallel
    Accepts a list of dictionaries containing string parameters.
    Example query_list:
      [
        {"iso": "IT", "start": "2026-04-01", "end": "2026-04-08", disease = "WestNileDisease"},
        {"iso": "FR", "start": "2026-04-05", "end": "2026-04-12", disease = "WestNileDisease"}
      ]
    """

    results = Parallel(n_jobs=n_jobs, prefer="threads")(
        delayed(fetch_country)(
            client,
            item["iso"],
            item["start"],
            item["end"],
            item["disease"]
        )
        for item in query_list
    )
    
    # Flatten and return a DataFrame for the next pipeline steps
    flat_results = [article for sublist in results for article in sublist]
    df_raw = pd.DataFrame(flat_results)
    
    if not df_raw.empty:
        df_raw = df_raw.drop_duplicates(subset=["id"])
        
    return df_raw

# Define a function to fetch the full-text 
def fetch_full_text(client,article_id:str):
    """
    Fetch the full text giving the article id 
    """
    time.sleep(0.1)
    try:
        res = client.get_full_text(article_id=article_id)
        item = {
            article_id: res["fullText"]
            }
        return item
        
    except Exception:
        # Fallback: log a warning and return empty list to keep the pipeline running
        logger.warning(f"Error fetching full text from EIOS for {article_id}.")
        return []

def parallel_fetch_full_texts(client, article_ids: list, n_jobs: int = -1) -> dict:
    """
    Fetch full texts for a list of article IDs in parallel.
    """
    results = Parallel(n_jobs=n_jobs, prefer="threads")(
        delayed(fetch_full_text)(client=client, article_id=aid)
        for aid in article_ids
    )
    
    # Merge list of dicts into one single dictionary
    full_texts_dict = {}
    for d in results:
        full_texts_dict.update(d)
        
    return full_texts_dict