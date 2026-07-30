import json
import pandas as pd
import streamlit as st

def render_details(df_filter):
    """Renders the article information"""

    st.subheader("Alert summary")
    st.markdown("*Select a row below to unpack and read individual text articles on the right.*")

    # Dataframe and details panels 
    col1, col2 = st.columns([3, 2]) 

    with col1:
        # Displaying unflattened summary data (with article counts)
        event = st.dataframe(
            df_filter[["pub_date", "country", "species", "article_count"]],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config = {
                "pub_date":"Publication Date",
                "country": "Country",
                "species": "Species",
                "article_count":"Number of relevant news"

            }
        )

    with col2:
        st.subheader("LLM reasoning")
        
        selected_rows = event.get("selection", {}).get("rows", [])
        
        if selected_rows:
            selected_index = selected_rows[0]
            selected_row = df_filter.iloc[selected_index]
            
            # If a row is selected display additional information 
            reasonings = json.loads(selected_row["evidence_reasonings"]) if isinstance(selected_row["evidence_reasonings"], str) else selected_row["evidence_reasonings"]
            sources = json.loads(selected_row["source"]) if isinstance(selected_row["source"], str) else selected_row["source"] 
            urls = json.loads(selected_row["url"]) if isinstance(selected_row["url"], str) else selected_row["url"] 
            full_texts = json.loads(selected_row["full_text_en"]) if isinstance(selected_row["full_text_en"], str) else selected_row["full_text_en"]
            article_ids = selected_row["article_ids"]
            
            for i, art_id in enumerate(article_ids):
                st.markdown(f"### Article {i+1} (EIOS ID: `{art_id}`)")
                
                reasoning_text = reasonings.get(str(art_id))
                source = sources.get(str(art_id))
                url = urls.get(str(art_id))
                full_text = full_texts.get(str(art_id))

                if source is None:
                    source = "N/A"
                
                if url is None:
                    url = "N/A"
                
                if full_text is None:
                    full_text = "N/A"
                
                st.markdown("**LLM reasoning**")
                st.info(reasoning_text)

                st.markdown("**Source**")
                if str(source).strip() in ["", "N/A"] or pd.isna(source):
                    st.warning("No source for this article.")
                else:
                    st.write(source)

                st.markdown("**Url**")
                if str(url).strip() in ["", "N/A"] or pd.isna(url):
                    st.warning("No url available for this article.")
                else:
                    st.write(url)
                
                st.markdown("**Full text (EN)**")
                if str(full_text).strip() in ["", "N/A"] or pd.isna(full_text):
                    st.warning("No full text available for this article.")
                else:
                    st.write(full_text)
                    
                st.divider() 

            
        else:
            st.info("Select any alert row in the table to unpack its nested news and analysis here.")
