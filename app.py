from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import time
from urllib import request, error

import pandas as pd
import pydeck as pdk
import streamlit as st

API_DIR = Path(__file__).parent / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import mock_data


st.set_page_config(
    page_title="MoveWise AI",
    layout="wide",
)

st.markdown(
    """
    <style>
        .metric-card {
            background: #f6f8fb;
            border: 1px solid #d7dfeb;
            border-radius: 14px;
            padding: 16px;
        }
        .metric-value {
            font-size: 28px;
            font-weight: 700;
            color: #12355b;
            line-height: 1.1;
        }
        .metric-label {
            font-size: 13px;
            color: #4c6278;
            margin-top: 6px;
        }
        .metric-stamp {
            font-size: 11px;
            color: #6a7e92;
            margin-top: 8px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def format_ts(value: datetime) -> str:
    return value.strftime("%d %b %Y, %I:%M:%S %p")


@st.cache_data(show_spinner=False)
def load_base_data(city: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    zones = mock_data.get_city_zones(city)
    historical = mock_data.generate_historical_demand(zones)
    return zones, historical


def render_metric_card(label: str, value: str, timestamp_label: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-value">{value}</div>
            <div class="metric-label">{label}</div>
            <div class="metric-stamp">{timestamp_label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fetch_realtime_prediction(api_base_url: str, city: str, horizon: int, realtime_weight: float):
    payload = {
        "city": city,
        "forecast_horizon": horizon,
        "realtime_weight": realtime_weight,
    }
    req = request.Request(
        f"{api_base_url.rstrip('/')}/predict/realtime",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=4) as response:
        data = json.loads(response.read().decode("utf-8"))
    return pd.DataFrame(data)


st.title("MoveWise AI")
st.subheader("Standalone Streamlit mobility forecast dashboard")
st.caption("Hybrid GNN+LSTM mock inference with real-time updates in Streamlit.")

st.sidebar.header("Live forecast controls")
city = st.sidebar.selectbox("City", list(mock_data.CITY_CENTERS.keys()))
horizon = st.sidebar.selectbox(
    "Forecast horizon",
    [15, 30, 60],
    format_func=lambda minutes: f"Next {minutes} minutes",
)
st.sidebar.caption(
    "Use Refresh forecast to regenerate the changing hotspot and fleet data with the latest timestamp."
)
auto_refresh = st.sidebar.toggle("Auto-refresh live data", value=True)
refresh_interval_seconds = st.sidebar.selectbox(
    "Auto-refresh interval",
    [5, 10, 15, 30, 60],
    index=2,
    format_func=lambda seconds: f"Every {seconds} seconds",
)
use_api_realtime = st.sidebar.toggle("Use API realtime predictor", value=True)
api_base_url = st.sidebar.text_input("API base URL", value="http://127.0.0.1:8000")
realtime_weight = st.sidebar.slider("Realtime signal weight", 0.0, 0.8, 0.35, 0.05)
refresh = st.sidebar.button("Refresh forecast", type="primary", use_container_width=True)

if "forecast_state" not in st.session_state:
    st.session_state.forecast_state = {}

zones_df, historical_df = load_base_data(city)
city_center = mock_data.CITY_CENTERS[city]

should_refresh = (
    auto_refresh
    or refresh
    or st.session_state.forecast_state.get("city") != city
    or st.session_state.forecast_state.get("horizon") != horizon
)

if should_refresh:
    generated_at = datetime.now()
    with st.spinner("Refreshing live hotspot forecast..."):
        time.sleep(0.8)
        data_source = "local-mock"
        try:
            if use_api_realtime:
                forecast_df = fetch_realtime_prediction(
                    api_base_url=api_base_url,
                    city=city,
                    horizon=horizon,
                    realtime_weight=realtime_weight,
                ).copy()
                data_source = "api-realtime"
            else:
                forecast_df = mock_data.generate_gnn_lstm_realtime_snapshot(
                    city=city,
                    horizon_mins=horizon,
                    zones=zones_df,
                    generated_at=generated_at,
                ).copy()
        except (error.URLError, TimeoutError, ValueError, OSError):
            forecast_df = mock_data.generate_gnn_lstm_realtime_snapshot(
                city=city,
                horizon_mins=horizon,
                zones=zones_df,
                generated_at=generated_at,
            ).copy()
            data_source = "local-mock-fallback"

    forecast_time = generated_at + timedelta(minutes=horizon)
    if "forecast_for" not in forecast_df.columns:
        forecast_df["forecast_for"] = forecast_time.isoformat()
    if "data_last_updated" not in forecast_df.columns:
        forecast_df["data_last_updated"] = generated_at.isoformat()
    if "confidence" not in forecast_df.columns:
        forecast_df["confidence"] = 0.7
    if "model_name" not in forecast_df.columns:
        forecast_df["model_name"] = "GNN+LSTM"
    if "realtime_adjusted" not in forecast_df.columns:
        forecast_df["realtime_adjusted"] = False

    forecast_df["generated_at"] = generated_at
    forecast_df["forecast_for_text"] = pd.to_datetime(forecast_df["forecast_for"]).dt.strftime("%d %b %Y, %I:%M:%S %p")
    forecast_df["data_last_updated_text"] = pd.to_datetime(forecast_df["data_last_updated"]).dt.strftime("%d %b %Y, %I:%M:%S %p")

    st.session_state.forecast_state = {
        "city": city,
        "horizon": horizon,
        "generated_at": generated_at,
        "forecast_time": forecast_time,
        "forecast_df": forecast_df,
        "historical_df": historical_df,
        "data_source": data_source,
    }

state = st.session_state.forecast_state
forecast_df = state["forecast_df"]
historical_df = state["historical_df"]
generated_at = state["generated_at"]
forecast_time = state["forecast_time"]
data_source = state.get("data_source", "local-mock")

st.success(f"Forecast ready for {city}. Last refresh: {format_ts(generated_at)}")

info_col1, info_col2, info_col3 = st.columns(3)
info_col1.caption(f"Data last updated: {format_ts(generated_at)}")
info_col2.caption(f"Forecast target time: {format_ts(forecast_time)}")
info_col3.caption(f"Prediction source: {data_source}")

total_demand = int(forecast_df["predicted_demand"].sum())
avg_demand = forecast_df["predicted_demand"].mean()
hotspots = int((forecast_df["demand_level"] == "High").sum())
total_fleet = int(forecast_df["recommended_vehicles"].sum())
avg_confidence = float(forecast_df.get("confidence", pd.Series([0.7])).mean()) * 100.0
stamp = f"Updated {format_ts(generated_at)}"

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    render_metric_card("Total predicted trips", f"{total_demand}", stamp)
with col2:
    render_metric_card("High-demand zones", f"{hotspots}", stamp)
with col3:
    render_metric_card("Recommended fleet size", f"{total_fleet}", stamp)
with col4:
    render_metric_card("Average trips per zone", f"{avg_demand:.1f}", stamp)
with col5:
    render_metric_card("Avg model confidence", f"{avg_confidence:.1f}%", "Model: GNN+LSTM")

st.markdown("---")

col_map, col_table = st.columns([2, 1])

with col_map:
    st.subheader("Demand heatmap")
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=forecast_df,
        get_position="[lon, lat]",
        get_fill_color="[220, 70 + predicted_demand * 4, 60, 170]",
        get_radius="120 + predicted_demand * 12",
        pickable=True,
    )

    view_state = pdk.ViewState(
        latitude=city_center[0],
        longitude=city_center[1],
        zoom=11.2,
        pitch=35,
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={
            "text": (
                "Zone: {zone_id}\n"
                "Predicted demand: {predicted_demand}\n"
                "Recommended vehicles: {recommended_vehicles}\n"
                "Last updated: {data_last_updated_text}\n"
                "Forecast for: {forecast_for_text}"
            )
        },
    )
    st.pydeck_chart(deck, use_container_width=True)

with col_table:
    st.subheader("Top hotspots")
    hotspots_df = forecast_df.loc[
        :,
        [
            "zone_id",
                "predicted_demand",
                "demand_level",
                "recommended_vehicles",
                "gnn_neighbor_influence",
                "gnn_graph_score",
                "realtime_adjusted",
                "data_last_updated_text",
                "forecast_for_text",
            ],
    ].head(8)
    st.dataframe(
        hotspots_df.rename(
            columns={
                "zone_id": "Zone",
                "predicted_demand": "Predicted demand",
                "demand_level": "Demand level",
                "recommended_vehicles": "Vehicles",
                "gnn_neighbor_influence": "GNN influence",
                "gnn_graph_score": "Graph score",
                "realtime_adjusted": "Realtime adjusted",
                "data_last_updated_text": "Last updated",
                "forecast_for_text": "Forecast for",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

st.markdown("---")

st.subheader("GNN Graph Signals")
graph_col1, graph_col2 = st.columns(2)
with graph_col1:
    st.caption("Top graph-influence zones (higher means stronger neighbor impact)")
    st.dataframe(
        forecast_df[["zone_id", "gnn_neighbor_influence", "gnn_graph_score", "gnn_neighbors"]]
        .sort_values(by="gnn_neighbor_influence", ascending=False)
        .head(10)
        .rename(
            columns={
                "zone_id": "Zone",
                "gnn_neighbor_influence": "Neighbor influence",
                "gnn_graph_score": "Graph score",
                "gnn_neighbors": "Neighbor zones",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
with graph_col2:
    st.caption("Graph score distribution by zone")
    st.bar_chart(
        forecast_df.sort_values(by="gnn_graph_score", ascending=False).set_index("zone_id")["gnn_graph_score"],
        use_container_width=True,
    )

st.markdown("---")

st.subheader("Historical vs predicted trend")
selected_zone = st.selectbox("Zone", forecast_df["zone_id"].tolist())
zone_history = historical_df[historical_df["zone_id"] == selected_zone].copy()
zone_history = zone_history.rename(columns={"timestamp": "Time", "historical_demand": "Demand"})

zone_prediction = int(
    forecast_df.loc[forecast_df["zone_id"] == selected_zone, "predicted_demand"].iloc[0]
)
prediction_point = pd.DataFrame([{"Time": forecast_time, "Demand": zone_prediction}])
combined_df = pd.concat([zone_history[["Time", "Demand"]], prediction_point], ignore_index=True)
combined_df = combined_df.set_index("Time")

trend_col1, trend_col2 = st.columns([3, 1])
with trend_col1:
    st.line_chart(combined_df["Demand"], use_container_width=True)
with trend_col2:
    st.caption(f"Selected zone: {selected_zone}")
    st.caption(f"Trend updated: {format_ts(generated_at)}")
    st.caption(f"Prediction point time: {format_ts(forecast_time)}")
    st.caption(f"Predicted demand: {zone_prediction}")

if auto_refresh:
    st.caption(f"Live mode active. Next update in {refresh_interval_seconds} seconds.")
    time.sleep(refresh_interval_seconds)
    st.rerun()
