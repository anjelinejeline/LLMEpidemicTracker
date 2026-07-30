import streamlit as st

def epioutlook_button():
    with st.container(border=True):
        st.markdown("##### Climate suitability")
        st.write(
            "Explore current and future climate suitability for "
            "**West Nile virus** using the EpiOutlook platform."
        )

        st.link_button(
            "Open EpiOutlook",
            "https://epioutlook.bsc.es/indicators-tab?lang=en",
            type="primary",
            icon=":material/open_in_new:",
            width="content",
        )