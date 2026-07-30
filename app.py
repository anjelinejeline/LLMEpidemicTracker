import time
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# Import all dashboard elements from src.dashboard
from src.dashboard.data_loader import load_and_process_data
from src.dashboard.alert_message import render_alert_message
from src.dashboard.sidebar import render_sidebar
from src.dashboard.chart_and_map import render_chart_and_map
from src.dashboard.view_details import render_details
from src.dashboard.container import epioutlook_button  


# Refresh every 15 minutes * 60 seconds * 1000 milliseconds = 900000
st_autorefresh(interval=15 * 60 * 1000, key="quarter_hour_heartbeat")

# Page configuration
st.set_page_config(
    page_title="LLMEpidemic Tracker | WNV Prototype",
    layout="wide", 
    initial_sidebar_state="auto"
)

st.title("LLMEpidemic Tracker:")
st.markdown("**Prototype** · LLM-powered **West Nile** Alert System ")


# Load the data
df = load_and_process_data()

# Display the alert message 
render_alert_message(df)
 
# Define the sidebar
selected_species = render_sidebar(df)

# Display the bar chart and map
df_filter = render_chart_and_map(df, selected_species)

# Display a button to connect  to EpiOutlook
epioutlook_button()

# Display the details
render_details(df_filter) 

