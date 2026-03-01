"""Page 6: Portfolio Management — Add/edit/remove/import positions."""

import io

import pandas as pd
import streamlit as st

from data.database import (
    add_position, delete_position, get_positions, update_position,
)
from data.market_data import validate_ticker


def render():
    st.header("Portfolio Management")

    tab_edit, tab_add, tab_import = st.tabs(["Edit Positions", "Add Position", "CSV Import"])

    # --- Tab 1: Edit existing positions ---
    with tab_edit:
        positions = get_positions()
        if positions.empty:
            st.info("No positions yet. Add one below or import from CSV.")
        else:
            st.caption(f"{len(positions)} positions")

            edited = st.data_editor(
                positions[["id", "ticker", "name", "units", "cost_basis",
                          "purchase_date", "sector", "asset_class", "currency",
                          "target_weight", "notes"]],
                column_config={
                    "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                    "ticker": st.column_config.TextColumn("Ticker", width="small"),
                    "name": st.column_config.TextColumn("Name", width="medium"),
                    "units": st.column_config.NumberColumn("Units", format="%.4f"),
                    "cost_basis": st.column_config.NumberColumn("Cost Basis", format="%.2f"),
                    "purchase_date": st.column_config.TextColumn("Purchase Date"),
                    "sector": st.column_config.SelectboxColumn(
                        "Sector",
                        options=[
                            "Equity - Global", "Equity - US", "Equity - Europe",
                            "Equity - Emerging", "Fixed Income", "Real Estate",
                            "Commodities", "Cash", "Alternative", "Other",
                        ],
                    ),
                    "asset_class": st.column_config.SelectboxColumn(
                        "Asset Class",
                        options=["Equity", "Fixed Income", "Real Estate",
                                 "Commodity", "Cash", "Alternative"],
                    ),
                    "currency": st.column_config.SelectboxColumn(
                        "Currency", options=["EUR", "USD", "GBP", "CHF"],
                    ),
                    "target_weight": st.column_config.NumberColumn(
                        "Target %", format="%.1f", min_value=0, max_value=100
                    ),
                    "notes": st.column_config.TextColumn("Notes"),
                },
                hide_index=True,
                use_container_width=True,
                key="positions_editor",
            )

            col_save, col_del = st.columns([1, 1])
            with col_save:
                if st.button("Save Changes", type="primary", use_container_width=True):
                    count = 0
                    for _, row in edited.iterrows():
                        orig = positions[positions["id"] == row["id"]]
                        if orig.empty:
                            continue
                        orig_row = orig.iloc[0]
                        changes = {}
                        for col in ["ticker", "name", "units", "cost_basis",
                                    "purchase_date", "sector", "asset_class",
                                    "currency", "target_weight", "notes"]:
                            new_val = row[col]
                            old_val = orig_row[col]
                            if pd.isna(new_val) and pd.isna(old_val):
                                continue
                            if new_val != old_val:
                                changes[col] = new_val
                        if changes:
                            update_position(int(row["id"]), **changes)
                            count += 1
                    if count:
                        st.success(f"Updated {count} position(s)")
                        st.rerun()
                    else:
                        st.info("No changes detected")

            with col_del:
                del_id = st.number_input(
                    "Delete position by ID", min_value=0, step=1, value=0,
                    help="Enter the ID of the position to delete"
                )
                if st.button("Delete", type="secondary", use_container_width=True):
                    if del_id > 0:
                        if delete_position(int(del_id)):
                            st.success(f"Deleted position {del_id}")
                            st.rerun()
                        else:
                            st.error(f"Position {del_id} not found")

    # --- Tab 2: Add new position ---
    with tab_add:
        with st.form("add_position_form"):
            st.subheader("Add New Position")
            col1, col2 = st.columns(2)
            with col1:
                ticker = st.text_input("Ticker Symbol", placeholder="IWDA.AS")
                name = st.text_input("Name", placeholder="iShares MSCI World")
                units = st.number_input("Units", min_value=0.0, step=0.01, format="%.4f")
                cost_basis = st.number_input("Total Cost Basis (EUR)", min_value=0.0, step=0.01)
            with col2:
                purchase_date = st.date_input("Purchase Date")
                sector = st.selectbox("Sector", [
                    "Equity - Global", "Equity - US", "Equity - Europe",
                    "Equity - Emerging", "Fixed Income", "Real Estate",
                    "Commodities", "Cash", "Alternative", "Other",
                ])
                asset_class = st.selectbox("Asset Class", [
                    "Equity", "Fixed Income", "Real Estate",
                    "Commodity", "Cash", "Alternative",
                ])
                currency = st.selectbox("Currency", ["EUR", "USD", "GBP", "CHF"])

            target_weight = st.slider("Target Weight (%)", 0.0, 100.0, 0.0, 0.5)
            notes = st.text_area("Notes", max_chars=500)

            submitted = st.form_submit_button("Add Position", type="primary")
            if submitted:
                if not ticker:
                    st.error("Ticker is required")
                elif units <= 0:
                    st.error("Units must be greater than 0")
                else:
                    with st.spinner("Validating ticker..."):
                        info = validate_ticker(ticker.upper())
                    if info is None:
                        st.error(f"Ticker '{ticker}' not found on Yahoo Finance")
                    else:
                        add_position(
                            ticker=ticker.upper(),
                            name=name or ticker.upper(),
                            units=units,
                            cost_basis=cost_basis,
                            purchase_date=str(purchase_date),
                            sector=sector,
                            asset_class=asset_class,
                            currency=currency,
                            target_weight=target_weight if target_weight > 0 else None,
                            notes=notes,
                        )
                        st.success(
                            f"Added {ticker.upper()} — "
                            f"last price: {info['last_price']:.2f} {info['currency']}"
                        )
                        st.rerun()

    # --- Tab 3: CSV Import ---
    with tab_import:
        st.subheader("Import from CSV")
        st.caption(
            "CSV must have columns: ticker, name, units, cost_basis, "
            "purchase_date, sector, asset_class. Optional: currency, target_weight, notes"
        )

        sample = pd.DataFrame({
            "ticker": ["IWDA.AS", "EIMI.AS"],
            "name": ["iShares MSCI World", "iShares EM"],
            "units": [100.0, 50.0],
            "cost_basis": [8000.0, 2000.0],
            "purchase_date": ["2024-01-15", "2024-03-01"],
            "sector": ["Equity - Global", "Equity - Emerging"],
            "asset_class": ["Equity", "Equity"],
        })
        st.download_button(
            "Download template CSV",
            sample.to_csv(index=False),
            "portfolio_template.csv",
            "text/csv",
        )

        uploaded = st.file_uploader("Upload CSV", type=["csv"])
        if uploaded is not None:
            try:
                df = pd.read_csv(uploaded)
                required = {"ticker", "units", "cost_basis", "purchase_date"}
                missing = required - set(df.columns)
                if missing:
                    st.error(f"Missing columns: {', '.join(missing)}")
                else:
                    st.dataframe(df, use_container_width=True)
                    if st.button("Import All", type="primary"):
                        count = 0
                        for _, row in df.iterrows():
                            add_position(
                                ticker=str(row["ticker"]).upper(),
                                name=str(row.get("name", row["ticker"])),
                                units=float(row["units"]),
                                cost_basis=float(row["cost_basis"]),
                                purchase_date=str(row["purchase_date"]),
                                sector=str(row.get("sector", "Other")),
                                asset_class=str(row.get("asset_class", "Equity")),
                                currency=str(row.get("currency", "EUR")),
                                target_weight=float(row["target_weight"]) if "target_weight" in row and pd.notna(row.get("target_weight")) else None,
                                notes=str(row.get("notes", "")),
                            )
                            count += 1
                        st.success(f"Imported {count} positions")
                        st.rerun()
            except Exception as e:
                st.error(f"Error reading CSV: {e}")


render()
