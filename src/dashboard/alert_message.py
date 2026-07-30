import pandas as pd
import streamlit as st
from datetime import date

def render_alert_message(df):
    """If the publication date is within the last 24 hours display an alert message for the user """
    today = date.today()
    yesterday = today - pd.Timedelta(days=1)

    # If the latest date in the data is yesterday, count those rows
    new_outbreaks_df = df[df["pub_date"] == yesterday]
    new_outbreaks_count = len(new_outbreaks_df)

    # 3. Display
    if new_outbreaks_count > 0:
        st.warning(
            f"**POTENTIAL NEW OUTBREAKS DETECTED:** There are {new_outbreaks_count} new alerts published yesterday ({yesterday})!"
        )
    else:
        st.success(
            f"No new alerts published yesterday ({yesterday}). (Latest data: {df['pub_date'].max()})"
        )



