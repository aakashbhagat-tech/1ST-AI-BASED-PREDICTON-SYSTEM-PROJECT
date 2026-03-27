from datetime import datetime
from typing import Dict, List, Optional


class RealtimePredictionEngine:
    """
    Blends baseline GNN+LSTM mock predictions with ingested real-time signals.
    """

    def __init__(self, ingestion_manager, mock_data_module):
        self.ingestion_manager = ingestion_manager
        self.mock_data = mock_data_module

    def _baseline(self, city: str, forecast_horizon: int, zones: Optional[List[str]] = None):
        zones_df = self.mock_data.get_city_zones(city)
        if zones:
            zones_df = zones_df[zones_df["zone_id"].isin(zones)]
        return self.mock_data.generate_gnn_lstm_realtime_snapshot(
            city=city,
            horizon_mins=forecast_horizon,
            zones=zones_df,
            generated_at=datetime.now(),
        )

    def _realtime_zone_signals(self) -> Dict[str, Dict[str, float]]:
        aggregated = self.ingestion_manager.aggregate_demand()
        signals: Dict[str, Dict[str, float]] = {}
        for zone_id, values in aggregated.items():
            signals[zone_id] = {
                "demand": float(values.get("total_demand", 0.0)),
                "vehicles": float(values.get("total_vehicles", 0.0)),
            }
        return signals

    def predict(
        self,
        city: str,
        forecast_horizon: int,
        zones: Optional[List[str]] = None,
        realtime_weight: float = 0.35,
    ):
        realtime_weight = max(0.0, min(0.8, float(realtime_weight)))
        baseline_df = self._baseline(city=city, forecast_horizon=forecast_horizon, zones=zones).copy()
        signals = self._realtime_zone_signals()

        realtime_adjusted_count = 0
        for idx, row in baseline_df.iterrows():
            zone_id = row["zone_id"]
            signal = signals.get(zone_id)
            if not signal:
                baseline_df.at[idx, "realtime_adjusted"] = False
                continue

            realtime_adjusted_count += 1
            base_demand = float(row["predicted_demand"])
            base_fleet = float(row["recommended_vehicles"])
            realtime_demand = signal["demand"]
            realtime_fleet = signal["vehicles"] if signal["vehicles"] > 0 else base_fleet

            adjusted_demand = (1.0 - realtime_weight) * base_demand + realtime_weight * realtime_demand
            adjusted_fleet = (1.0 - realtime_weight) * base_fleet + realtime_weight * realtime_fleet

            predicted_demand = max(0, int(round(adjusted_demand)))
            recommended_vehicles = max(1, int(round(adjusted_fleet)))

            demand_level = "Low"
            if predicted_demand > 25:
                demand_level = "High"
            elif predicted_demand > 12:
                demand_level = "Medium"

            baseline_df.at[idx, "predicted_demand"] = predicted_demand
            baseline_df.at[idx, "recommended_vehicles"] = recommended_vehicles
            baseline_df.at[idx, "demand_level"] = demand_level
            baseline_df.at[idx, "realtime_adjusted"] = True

        baseline_df["model_name"] = "GNN+LSTM+Realtime"
        baseline_df["realtime_weight"] = realtime_weight
        baseline_df = baseline_df.sort_values(by="predicted_demand", ascending=False).reset_index(drop=True)
        return baseline_df, realtime_adjusted_count

