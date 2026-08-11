import logging
import numpy as np
import pandas as pd
import torch
from joblib import Parallel, delayed
from tqdm import tqdm
from transformers import pipeline

logger = logging.getLogger("wn_alert_logger")

# Initialize local Hugging Face translation model once
default_translator = pipeline(
    "translation",
    model="Helsinki-NLP/opus-mt-mul-en",
    device=0 if torch.cuda.is_available() else -1,
)


def translate_summary(
    df: pd.DataFrame, translator=default_translator
) -> pd.DataFrame:
    """Takes a DataFrame of EIOS items, detects if they are non-English,

    and translates the combined Title + Description to English.
    """
    df = df.copy()
    df.columns = df.columns.str.lower()

    # Clean strings
    df["title"] = df["title"].fillna("").astype(str)
    df["description"] = df["description"].fillna("").astype(str)

    # Combine raw text reliably
    df["original_text"] = (
        df["title"].str.strip() + " " + df["description"].str.strip()
    ).str.strip()

    # Normalize language ISO code
    df["languageiso"] = df["languageiso"].fillna("").str.lower()
    is_english = df["languageiso"].eq("en")

    # Set up baseline for English text
    df["en_text"] = np.where(is_english, df["original_text"], "")

    # Identify row masks needing translation
    mask_translate = (~is_english) & df["original_text"].ne("")

    if mask_translate.sum() > 0:

        def safe_translate(text):
            if not isinstance(text, str) or not text.strip():
                return None
            try:
                res = translator(str(text), max_length=512, truncation=True)
                return res[0]["translation_text"]
            except Exception:
                # Keep the pipeline running, just log a quiet warning
                logger.warning(
                    "Summary translation failed for a row; skipping."
                )
                return None

        # Apply progress bar tracking over rows
        tqdm.pandas(desc="Translating articles")
        df["translated_text"] = None
        df.loc[mask_translate, "translated_text"] = df.loc[
            mask_translate, "original_text"
        ].progress_apply(safe_translate)

        # Fallback to translated text if English baseline wasn't set
        df["en_text"] = np.where(
            df["en_text"].ne(""), df["en_text"], df["translated_text"]
        )

    df["en_text"] = df["en_text"].fillna("").str.strip()

    return df


# Define a function to translate the summaries in parallel
def parallel_translate_summaries(
    df: pd.DataFrame, num_chunks: int, n_jobs: int = -1
) -> pd.DataFrame:
    """Translate the summaries  in parallel."""

    num_chunks = min(len(df), num_chunks)

    indices = np.array_split(df.index, num_chunks)

    results = Parallel(n_jobs=n_jobs)(
        delayed(translate_summary)(df.loc[idx]) for idx in indices
    )

    return pd.concat(results)


# Define a function to translate the full text of an article
def translate_full_text(full_text: str, translator=default_translator) -> str:
    """Translate the full text of an article."""
    if not full_text or str(full_text).strip() == "":
        return ""
    try:
        res = translator(str(full_text), max_length=512, truncation=True)
        return res[0]["translation_text"]
    except Exception:
        # Fallback: return original text if translation fails to keep the pipeline running
        logger.warning(
            "Failed to translate full text; falling back to original raw text."
        )
        return str(full_text)


# Define a function to translate the full texts in parallel
def _translate_task(text_id: str, full_text: str):
    return text_id, {
        "original": full_text,
        "translated": translate_full_text(full_text),
    }


def parallel_translate_full_texts(full_texts: dict, n_jobs: int = -1) -> dict:
    """Translate a dictionary of full texts in parallel."""
    translated_results = dict(
        Parallel(n_jobs=n_jobs, prefer="threads")(
            delayed(_translate_task)(text_id, full_text)
            for text_id, full_text in tqdm(
                full_texts.items(), desc="Parallel Translation"
            )
        )
    )
    return translated_results