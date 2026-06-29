from __future__ import annotations

import pandas as pd
import streamlit as st

from .config import load_settings
from .storage import SQLiteRepository


def run_dashboard() -> None:
    settings = load_settings()
    repository = SQLiteRepository(settings.database_path)
    repository.initialize()

    st.set_page_config(page_title="Bitfinex Lending Bot", layout="wide")
    st.title("Bitfinex Lending Bot")

    wallets = pd.DataFrame(repository.latest_wallets(100))
    offers = pd.DataFrame(repository.latest_offers(100))
    events = pd.DataFrame(repository.latest_events(100))
    risk = repository.latest_risk_decision()

    metric_columns = st.columns(3)
    metric_columns[0].metric("Wallet Rows", len(wallets))
    metric_columns[1].metric("Tracked Offers", len(offers))
    metric_columns[2].metric("Events", len(events))

    risk_columns = st.columns(3)
    if risk is None:
        risk_columns[0].metric("Current Exposure", "0.00%")
        risk_columns[1].metric("Risk Mode", "SAFE")
        risk_columns[2].metric("Last Rejection", "No risk decision")
    else:
        exposure_percent = float(risk.get("exposure_ratio", "0")) * 100
        last_rejection = risk["reason"] if risk.get("allowed") == "0" else "None"
        risk_columns[0].metric("Current Exposure", f"{exposure_percent:.2f}%")
        risk_columns[1].metric("Risk Mode", risk.get("mode", "SAFE"))
        risk_columns[2].metric("Last Rejection", last_rejection)

    tab_wallets, tab_offers, tab_events = st.tabs(["Wallets", "Funding Offers", "Events"])
    with tab_wallets:
        st.dataframe(wallets, use_container_width=True, hide_index=True)
    with tab_offers:
        st.dataframe(offers, use_container_width=True, hide_index=True)
    with tab_events:
        st.dataframe(events, use_container_width=True, hide_index=True)
