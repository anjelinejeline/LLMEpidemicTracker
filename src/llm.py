import os
import logging
import subprocess
import random
import gc
import shutil
from tqdm.auto import tqdm
import torch
import pandas as pd
import matplotlib.pyplot as plt
import json
from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from vllm import LLM, SamplingParams
from vllm.sampling_params import GuidedDecodingParams

logger = logging.getLogger("wn_alert_logger")

# Create only required HF cache dirs
os.makedirs("/scratch/panelan/hf_cache", exist_ok=True)
os.makedirs("/scratch/panelan/hf_cache/hub", exist_ok=True)


# HuggingFace environment
os.environ["HF_HOME"] = "/scratch/panelan/hf_cache"
os.environ["HF_HUB_CACHE"] = "/scratch/panelan/hf_cache/hub"
os.environ["HF_HUB_DISABLE_XET"] = "1"


os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# Enforce deterministic scheduling for reproducibility
# https://docs.vllm.ai/en/latest/usage/reproducibility/
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"


# Pydantic schema
class ArticleClassification(BaseModel):
    event_date: Optional[str] = Field(
        None, description="The event date mentioned in text (YYYY-MM-DD), or null if missing."
    )
    label: Literal["outbreak_alert", "epi_summary", "other"] = Field(
        description="Classification category based strictly on epidemiological host rules."
    )
    outbreak_detected: bool = Field(
        description="True ONLY if day_label is outbreak_alert, otherwise False."
    )
    countries: List[str] = Field(
        description="List of full country names explicitly found in the text."
    )
    iso2_codes: List[str] = Field(
        description="List of 2-letter ISO codes matching the identified countries."
    )
    species_affected: List[Literal["human", "horse", "bird", "other_animal"]] = Field(
        description="Array of host types impacted. Empty array [] if only mosquitoes test positive."
    )
    reasoning: str = Field(
        description="A strict brief justification, capped tightly under 10 words."
    )

# Prompt
llm_prompt = """

You are an epidemiologist classifying West Nile virus articles.

Return ONE JSON object.

Article:
{article_text}

---

SCOPE RULE (VERY IMPORTANT):
Only consider West Nile virus (WNV).

If the article is about ANY other disease → classify as "other".

---

CLASSIFICATION RULES (apply in order):

1) If there are NO human or animal infections mentioned
(only mosquito traps/pools/surveillance, no infected humans/animals, research on climate change etc):
→ label = "other"
→ outbreak_detected = false
→ species_affected = []
→ STOP

2) If the article is a surveillance report, statistics table, or seasonal summary:
→ label = "epi_summary"
→ outbreak_detected = false
*CRITERIA*: This includes reports capturing multi-national data, seasonal comparisons, or tracking cumulative statistics across multiple countries.
*EXAMPLE*: "WNV in Europe 2022: EU countries reported 292 cases across Italy (228), Greece (59), and Austria (2)." This is an epi_summary

3) If there are confirmed or suspected active, localized spikes, unexpected cases, or emergency notifications:
→ label = "outbreak_alert"
→ outbreak_detected = true
*CRITERIA*: Tone features real-time concern, unexpected increases, or immediate localized threats in a country/region.
*EXAMPLE*: "In recent weeks, increasingly alarming news has spread about the increase in cases of West Nile Disease in our country. The cases reported in Italy by the National Reference Center for WND, at the Zooprophylactic Institute, have risen to 230..." This must be an outbreak_alert with outbreak_detected = true.

1) If there are NO human or animal infections mentioned
(only mosquito traps/pools/surveillance, no infected humans/animals):
→ classify = "other"
→ outbreak_detected = false
→ species_affected = []
→ STOP

2) If the article is a surveillance report, statistics, or seasonal summary:
→ classify = "epi_summary"

3) If there are confirmed or suspected human/animal cases:
→ classify = "outbreak_alert"

---

CRITICAL RULES:
- outbreak_detected = true ONLY if the text explicitly mentions cases, infections or outbreak.
- If only research, modelling, risk, or discussion → outbreak_detected = false
- Mosquito-only positivity WITHOUT human/animal cases is ALWAYS "other" → outbreak_detected = false
- ONLY extract information explicitly stated in the text.
- Do NOT infer, assume, or generalize.
- Do NOT guess countries or species if not explicitly mentioned.
- If unsure, return empty list [] and false.
- If no specific event date is mentioned in the text, set "event_date" to null.
- Reason must be maximum 10 words, do not exceed 10 words under any circumstance

Return ONLY valid JSON.

JSON:"""


class EIOSClassifier:
    def __init__(self, batch_size:int = 64, model_checkpoint: str =  "anjelinejeline/Qwen2.5-14B-Instruct-epi"):
        self.model_checkpoint = model_checkpoint
        self.batch_size = batch_size

        # Guided decoding schema setup
        guided_schema = ArticleClassification.model_json_schema()
        self.sampling_params = SamplingParams(
            temperature=0.0, 
            max_tokens=300,
            guided_decoding=GuidedDecodingParams(
                json=guided_schema, 
                backend="lm-format-enforcer"
            )
        )

    def classify(self, data:list) -> list:
        """
        Classify the news using the defined llm
        """
        if not data:
            return []
        
        model_prompts = []
        active_ids = []
    
        for item in data:
            formatted_prompt = llm_prompt.format(
                article_text=item["en_text"]
            )
            model_prompts.append(formatted_prompt)
            active_ids.append(item["id"])
        
        llm_results = {}
        all_outputs = []

        try:
            # Load current model into GPU VRAM
            logger.info(f"Loading {self.model_checkpoint} onto GPU VRAM.")
            llm = LLM(
                model=self.model_checkpoint,
                max_model_len=1024, 
                dtype="float16",
                enforce_eager=True,
                gpu_memory_utilization=0.85,
                trust_remote_code=True,
                download_dir="/scratch/panelan/hf_cache",
                seed=8012026
            )

            # Generate in batches
            for i in tqdm(range(0, len(model_prompts), self.batch_size), desc="Classifying with vLLM", leave=False):
                batch_prompts = model_prompts[i:i + self.batch_size]
                batch_outputs = llm.generate(batch_prompts, self.sampling_params)
                all_outputs.extend(batch_outputs)

            # Parse outputs
            for idx, output in enumerate(all_outputs):
                article_id = active_ids[idx]
                raw_output = output.outputs[0].text.strip()
                try:
                    llm_results[article_id] = json.loads(raw_output)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse LLM JSON for article {article_id}.")
                    llm_results[article_id] = {
                        "error": "Invalid JSON",
                        "raw": raw_output
                    }
                    
            logger.info(f"Completed extraction batch for {self.model_checkpoint}.")

        except Exception as e:
            logger.exception(f"Critical error executing {self.model_checkpoint}.")
            for article_id in active_ids:
                llm_results[article_id] = {"error": str(e)}

        finally:
            logger.info("Flushing GPU VRAM to ensure clean scheduling cycles.")
            if 'llm' in locals():
                del llm
            gc.collect()
            torch.cuda.empty_cache()

        
        # Add info from the raw data 
        lookup = {
            article["id"]: {
            "pub_date" : article.get("pubdate"),
            "en_text" : article.get("en_text"),
            "source": article.get("source", {}),
            "url": article.get("url", {})
            }
            for article in data
            }
        
        for article_id, result in llm_results.items():
            info = lookup.get(article_id) 
            result["pub_date"] = info.get("pub_date") 
            result["en_text"] = info.get("en_text") 
            result["source"] = info.get("source")
            result["url"] = info.get("url")

        return llm_results






