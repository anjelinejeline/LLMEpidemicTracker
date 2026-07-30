def daily_aggregation(raw_data: dict) -> list:
    aggregated_alerts = {}
    
    for article_id, info in raw_data.items():
        if info.get("outbreak_detected"):
            if info.get("pub_date"):
                pub_day = info["pub_date"].split('T')[0]
            else:
                pub_day = "unknown date"
            
            countries = info.get("countries", [])
            iso_codes = info.get("iso2_codes", [])  
            
            if not countries:
                countries = ["unknown"]
                iso_codes = ["UNK"]
            else:
                while len(iso_codes) < len(countries):
                    iso_codes.append("UNK")

            species_list = info.get("species_affected", [])
            if not species_list:
                species_list = ["unknown"]

            reason = info.get("reasoning", "No reasoning provided by LLM.")
            source = info.get("source", "")
            url = info.get("url", "")
            summary = info.get("en_text", "") # Title + description used by the LLM 
            original_text = info.get("full_text", "")
            translated_text = info.get("full_text_en", "")
           
            for c, iso in zip(countries, iso_codes):
                for s in species_list:
                    alert_key = f"{pub_day}_{c}_{s}"

                    if alert_key not in aggregated_alerts:
                        aggregated_alerts[alert_key] = {
                            "pub_date": pub_day,
                            "country": c,
                            "iso2_code": iso,
                            "species": s,       
                            "article_count": 0,
                            "article_ids": [],
                            "evidence_reasonings": {},
                            "source": {},
                            "url": {},
                            "summary":{},
                            "full_text": {},           
                            "full_text_en": {},
                        }

                    current_alert = aggregated_alerts[alert_key]

                    if article_id not in current_alert["article_ids"]:
                        current_alert["article_count"] += 1
                        current_alert["article_ids"].append(article_id)
                        current_alert["evidence_reasonings"][article_id] = reason
                        current_alert["source"][article_id] = source
                        current_alert["url"][article_id] = url
                        current_alert["summary"][article_id] = summary
                        current_alert["full_text"][article_id] = original_text
                        current_alert["full_text_en"][article_id] = translated_text
                 
    return list(aggregated_alerts.values())