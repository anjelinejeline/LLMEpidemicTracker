import streamlit as st

def render_chart_and_map(df, selected_species):
    # Main panel
    df["pub_month"] = df["pub_date"].apply(lambda x: x.strftime("%Y-%m"))

    counts = (
        df.explode("article_ids")
        .groupby(["pub_month", "species"])
        .size()
        .reset_index(name="count")
        .pivot(
            index="pub_month",
            columns="species",
            values="count",
        )
        .fillna(0)
    )

    st.subheader("Number of relevant news over time")

    st.bar_chart(counts)


    start_bound = df["pub_date"].min()
    end_bound = df["pub_date"].max()

    st.subheader("Temporal coverage")

    selected_date = st.date_input(
        label="Select a date",
        value=end_bound,                 
        min_value=start_bound,          
        max_value=end_bound              
    )

    # Apply filters
    df_filter = df[
        (df["pub_date"] == selected_date) & 
        (df["species"].isin(selected_species))
    ]

    # Map
    if not df_filter.empty:
        df_filter["point_size"] = df_filter["article_count"] * 50
        st.map(
            data=df_filter, 
            latitude="latitude", 
            longitude="longitude", 
            size="point_size", 
            color="#ff0000",
            zoom=3  # Locks the zoom level to a continental scale
        )
    else:
        # Create a fallback dataframe centered in Europe (e.g., Germany/Poland area)
        # so st.map still renders a map of Europe even with no data points.
        fallback_data = [{"latitude": 51.1657, "longitude": 10.4515}]
        
        st.map(
            data=fallback_data,
            zoom=3
        )
        st.info("No records found for the selected filters.")
        
    return df_filter

