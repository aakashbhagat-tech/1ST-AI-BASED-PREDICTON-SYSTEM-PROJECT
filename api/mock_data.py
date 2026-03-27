import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Center around a hypothetical city center (e.g., SF coordinates)
CITY_CENTERS = {
    "San Francisco": (37.7749, -122.4194),
    "New York": (40.7128, -74.0060),
    "London": (51.5074, -0.1278)
}

ZONES = [f"Z{i:02d}" for i in range(1, 21)]
CITY_SEEDS = {
    "San Francisco": 1101,
    "New York": 2202,
    "London": 3303,
}
_ZONE_CACHE = {}

def generate_zones(city="San Francisco"):
    if city in _ZONE_CACHE:
        return _ZONE_CACHE[city].copy()

    lat_center, lon_center = CITY_CENTERS.get(city, CITY_CENTERS["San Francisco"])
    rng = np.random.default_rng(CITY_SEEDS.get(city, 9999))

    lats = lat_center + rng.normal(0, 0.04, len(ZONES))
    lons = lon_center + rng.normal(0, 0.04, len(ZONES))
    base_demand = rng.uniform(5, 50, len(ZONES))

    return pd.DataFrame({
        "zone_id": ZONES,
        "lat": lats,
        "lon": lons,
        "base_demand": base_demand
    })
    
def get_city_zones(city="San Francisco"):
    if city not in _ZONE_CACHE:
        _ZONE_CACHE[city] = generate_zones(city)
    return _ZONE_CACHE[city].copy()


def _build_adjacency_matrix(zones_df, k_neighbors=4):
    coords = zones_df[["lat", "lon"]].to_numpy()
    n = len(coords)
    adjacency = np.zeros((n, n), dtype=float)

    for i in range(n):
        dists = np.sqrt(np.sum((coords - coords[i]) ** 2, axis=1))
        nearest = np.argsort(dists)[1 : k_neighbors + 1]
        inv = 1.0 / np.maximum(dists[nearest], 1e-6)
        weights = inv / np.sum(inv)
        adjacency[i, nearest] = weights

    return adjacency


def _top_neighbor_ids(zones_df, adjacency):
    zone_ids = zones_df["zone_id"].tolist()
    neighbors = {}
    for i, zid in enumerate(zone_ids):
        non_zero_idx = np.where(adjacency[i] > 0)[0]
        ordered = non_zero_idx[np.argsort(adjacency[i, non_zero_idx])[::-1]]
        neighbors[zid] = [zone_ids[j] for j in ordered]
    return neighbors


def _temporal_memory_from_history(history_values):
    state = 0.0
    for value in history_values:
        state = 0.72 * state + 0.28 * float(value)
    return state

def generate_historical_demand(zones_df, hours=24):
    """Generate mock historical demand for the last N hours."""
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    times = [now - timedelta(hours=i) for i in range(hours, 0, -1)]
    
    records = []
    for t in times:
        # Peak around 8 AM (hour 8) and 6 PM (hour 18)
        hour_factor = np.sin((t.hour - 6) * (np.pi / 12)) + 1.2
        for _, row in zones_df.iterrows():
            noise = np.random.normal(0, 2)
            demand = max(0, int(row['base_demand'] * hour_factor * 0.5 + noise))
            records.append({
                "timestamp": t,
                "zone_id": row['zone_id'],
                "historical_demand": demand
            })
            
    return pd.DataFrame(records)

def generate_gnn_lstm_realtime_snapshot(city="San Francisco", horizon_mins=30, zones=None, generated_at=None):
    """
    Hybrid forecaster:
    - LSTM-like temporal memory over historical demand sequence
    - GNN-like spatial smoothing over nearest zone graph
    """
    if generated_at is None:
        generated_at = datetime.now()

    zones_df = zones.copy() if zones is not None else get_city_zones(city)
    zones_df = zones_df.reset_index(drop=True)
    forecast_time = generated_at + timedelta(minutes=horizon_mins)
    hour_factor = np.sin((forecast_time.hour - 6) * (np.pi / 12)) + 1.2
    tick = int(generated_at.timestamp() // 15)

    # Synthetic historical sequence per zone used as temporal context.
    historical_df = generate_historical_demand(zones_df, hours=24)
    history_by_zone = (
        historical_df.sort_values("timestamp")
        .groupby("zone_id")["historical_demand"]
        .apply(list)
        .to_dict()
    )

    local_signal = np.zeros(len(zones_df), dtype=float)
    confidence = np.zeros(len(zones_df), dtype=float)

    for idx, row in zones_df.iterrows():
        seed = CITY_SEEDS.get(city, 9999) + tick + idx * 19
        rng = np.random.default_rng(seed)

        temporal_memory = _temporal_memory_from_history(history_by_zone.get(row["zone_id"], [row["base_demand"]]))
        realtime_wave = 1 + 0.18 * np.sin((generated_at.timestamp() / 24.0) + idx * 0.45)
        pulse = 1.0 + (0.35 if (tick + idx) % 13 == 0 else 0.0)
        noise = rng.uniform(0.94, 1.06)

        base_estimate = row["base_demand"] * hour_factor * 0.6 * realtime_wave * pulse
        local_signal[idx] = max(0.0, (0.62 * temporal_memory) + (0.38 * base_estimate * noise))

        variability = np.std(history_by_zone.get(row["zone_id"], [row["base_demand"]]))
        confidence[idx] = float(np.clip(0.88 - (variability / 80.0), 0.62, 0.93))

    adjacency = _build_adjacency_matrix(zones_df, k_neighbors=4)
    neighbor_ids = _top_neighbor_ids(zones_df, adjacency)
    graph_centrality = adjacency.sum(axis=0)
    neighbor_signal = adjacency @ local_signal
    hybrid_signal = (0.68 * local_signal) + (0.32 * neighbor_signal)

    records = []
    for idx, row in zones_df.iterrows():
        predicted_demand = int(max(0, round(hybrid_signal[idx])))
        recommended_vehicles = max(1, int(round(predicted_demand / 1.5)))

        demand_level = "Low"
        if predicted_demand > 25:
            demand_level = "High"
        elif predicted_demand > 12:
            demand_level = "Medium"

        records.append(
            {
                "zone_id": row["zone_id"],
                "lat": row["lat"],
                "lon": row["lon"],
                "predicted_demand": predicted_demand,
                "demand_level": demand_level,
                "recommended_vehicles": recommended_vehicles,
                "confidence": round(confidence[idx], 3),
                "model_name": "GNN+LSTM",
                "gnn_neighbor_influence": round(float(neighbor_signal[idx]), 2),
                "gnn_graph_score": round(float(graph_centrality[idx]), 3),
                "gnn_neighbors": ",".join(neighbor_ids.get(row["zone_id"], [])),
                "data_last_updated": generated_at.isoformat(),
                "forecast_for": forecast_time.isoformat(),
                "source": "mock_realtime_hybrid",
            }
        )

    df = pd.DataFrame(records)
    return df.sort_values(by="predicted_demand", ascending=False).reset_index(drop=True)


def get_zone_graph_topology(city="San Francisco", k_neighbors=4):
    zones_df = get_city_zones(city).reset_index(drop=True)
    adjacency = _build_adjacency_matrix(zones_df, k_neighbors=k_neighbors)

    nodes = []
    for _, row in zones_df.iterrows():
        nodes.append(
            {
                "zone_id": row["zone_id"],
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "base_demand": float(row["base_demand"]),
            }
        )

    edges = []
    zone_ids = zones_df["zone_id"].tolist()
    for i in range(len(zone_ids)):
        for j in range(len(zone_ids)):
            w = float(adjacency[i, j])
            if w > 0:
                edges.append(
                    {
                        "source": zone_ids[i],
                        "target": zone_ids[j],
                        "weight": round(w, 4),
                    }
                )

    return {"city": city, "nodes": nodes, "edges": edges}
