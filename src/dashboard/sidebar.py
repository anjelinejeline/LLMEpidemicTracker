import streamlit as st

def render_sidebar(df):
    """Render species multi-select filter and raw JSON export downloader."""
    unique_species = df["species"].unique()
    selected_species = st.sidebar.multiselect(
        "Filter by species", 
        options=unique_species, 
        default=unique_species
    )

    json_file = df.to_json(orient="records", indent=4, date_format="iso").encode("utf-8")
    st.sidebar.download_button(
        label="Download raw json", 
        data=json_file, 
        file_name="wnv_alerts.json"
    )
    
    return selected_species



