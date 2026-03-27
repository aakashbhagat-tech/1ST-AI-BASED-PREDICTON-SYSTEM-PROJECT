import asyncio
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

try:
    from . import mock_data
    from .data_ingestion import RealtimeDataIngestionManager
    from .realtime_predictor import RealtimePredictionEngine
except ImportError:
    import mock_data
    from data_ingestion import RealtimeDataIngestionManager
    from realtime_predictor import RealtimePredictionEngine

app = FastAPI(
    title="MoveWise AI API",
    description="Urban Mobility Demand Forecasting API (mock-data mode)",
    version="3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8501",
        "http://localhost:8501",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ingestion_manager = RealtimeDataIngestionManager()
realtime_engine = RealtimePredictionEngine(ingestion_manager=ingestion_manager, mock_data_module=mock_data)


class PredictionRequest(BaseModel):
    city: str
    forecast_horizon: int = 30
    zones: Optional[List[str]] = None
    realtime_weight: float = 0.35


class PredictionResponse(BaseModel):
    zone_id: str
    lat: float
    lon: float
    predicted_demand: int
    demand_level: str
    recommended_vehicles: int
    confidence: float = 0.7
    model_name: str = "GNN+LSTM"
    realtime_adjusted: bool = False
    gnn_neighbor_influence: float = 0.0
    gnn_graph_score: float = 0.0
    gnn_neighbors: str = ""


class IngestionRequest(BaseModel):
    source: str
    data_points: List[dict]


def _predict(city: str, forecast_horizon: int, zones: Optional[List[str]] = None) -> List[dict]:
    result = mock_data.generate_gnn_lstm_realtime_snapshot(
        city=city,
        horizon_mins=forecast_horizon,
        generated_at=datetime.now(),
    )
    if zones:
        result = result[result["zone_id"].isin(zones)]
    return result.to_dict(orient="records")


@app.on_event("startup")
async def startup_event():
    print("=" * 60)
    print("MoveWise AI API - Starting Up")
    print("Mode: Mock data forecasting (ML training removed)")
    print("=" * 60)


@app.get("/")
def read_root():
    return {
        "message": "MoveWise AI API v3.0 - GNN+LSTM Hybrid Mock Forecasting",
        "status": "active",
        "features": ["REST API", "WebSocket Streaming", "GNN+LSTM Hybrid Predictions"],
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "mode": "mock",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/predict", response_model=List[PredictionResponse])
def predict_demand_endpoint(request: PredictionRequest):
    try:
        return _predict(
            city=request.city,
            forecast_horizon=request.forecast_horizon,
            zones=request.zones,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Prediction error: {exc}")


@app.post("/predict/realtime", response_model=List[PredictionResponse])
def predict_realtime_endpoint(request: PredictionRequest):
    try:
        result_df, _ = realtime_engine.predict(
            city=request.city,
            forecast_horizon=request.forecast_horizon,
            zones=request.zones,
            realtime_weight=request.realtime_weight,
        )
        return result_df.to_dict(orient="records")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Realtime prediction error: {exc}")


@app.post("/predict/zone/{zone_id}", response_model=PredictionResponse)
def predict_zone_demand(zone_id: str, city: str = "San Francisco", forecast_horizon: int = 30):
    try:
        predictions = _predict(city=city, forecast_horizon=forecast_horizon, zones=[zone_id])
        if not predictions:
            raise HTTPException(status_code=404, detail=f"Zone not found: {zone_id}")
        return predictions[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ingest")
def ingest_data(request: IngestionRequest):
    ingestion_manager.ingest_batch(request.source, request.data_points)
    return {
        "status": "success",
        "message": f"Ingested {len(request.data_points)} points from {request.source}",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/model/info")
def get_model_info():
    return {
        "message": "Hybrid mock inference enabled.",
        "model_available": True,
        "mode": "mock_hybrid",
        "model_name": "GNN+LSTM",
    }


@app.get("/realtime/status")
def realtime_status():
    sources = ingestion_manager.get_all_sources()
    aggregated = ingestion_manager.aggregate_demand()
    return {
        "status": "active",
        "active_sources": len(sources),
        "zones_with_realtime_signal": len(aggregated),
        "sources": sources,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/graph/topology")
def graph_topology(city: str = "San Francisco", k_neighbors: int = 4):
    if k_neighbors < 1:
        k_neighbors = 1
    if k_neighbors > 8:
        k_neighbors = 8
    return mock_data.get_zone_graph_topology(city=city, k_neighbors=k_neighbors)


@app.post("/ingest/mock-tick")
def ingest_mock_tick(city: str = "San Francisco", horizon: int = 30, source: str = "mock_tick"):
    snapshot = _predict(city=city, forecast_horizon=horizon)
    now_iso = datetime.now().isoformat()
    points = []
    for row in snapshot:
        points.append(
            {
                "zone_id": row["zone_id"],
                "lat": row["lat"],
                "lon": row["lon"],
                "current_demand": row["predicted_demand"],
                "available_vehicles": row["recommended_vehicles"],
                "timestamp": now_iso,
            }
        )
    ingestion_manager.ingest_batch(source, points)
    return {
        "status": "success",
        "source": source,
        "ingested_points": len(points),
        "city": city,
        "timestamp": now_iso,
    }


@app.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        city = websocket.query_params.get("city", "San Francisco")
        horizon = int(websocket.query_params.get("horizon", "30"))
        interval = int(websocket.query_params.get("interval", "15"))
        if interval < 15:
            interval = 15

        while True:
            prediction_df, realtime_adjusted_count = realtime_engine.predict(
                city=city,
                forecast_horizon=horizon,
                realtime_weight=0.35,
            )
            prediction_data = prediction_df.to_dict(orient="records")
            total_demand = sum(zone["predicted_demand"] for zone in prediction_data)
            high_hotspots = sum(1 for zone in prediction_data if zone["demand_level"] == "High")
            total_fleet = sum(zone["recommended_vehicles"] for zone in prediction_data)
            avg_confidence = (
                sum(float(zone.get("confidence", 0.7)) for zone in prediction_data) / len(prediction_data)
                if prediction_data
                else 0.7
            )

            message = {
                "timestamp": datetime.now().isoformat(),
                "zones": prediction_data,
                "kpis": {
                    "total_demand": total_demand,
                    "hotspots": high_hotspots,
                    "fleet": total_fleet,
                    "confidence": round(avg_confidence * 100.0, 1),
                },
                "update_interval": interval,
                "update_interval_unit": "seconds",
                "mode": "mock_hybrid",
                "model_name": "GNN+LSTM+Realtime",
                "realtime_adjusted_zones": realtime_adjusted_count,
            }
            await websocket.send_json(message)
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        print("Client disconnected from stream")
    except Exception as exc:
        print(f"WebSocket error: {exc}")
        await websocket.close(code=1011)


@app.websocket("/ws/ingest")
async def ingest_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        source_id = websocket.query_params.get("source", "unknown")
        ingestion_manager.register_source(source_id)
        while True:
            data = await websocket.receive_json()
            ingestion_manager.ingest_data(source_id, data)
    except WebSocketDisconnect:
        ingestion_manager.unregister_source(source_id)
    except Exception as exc:
        print(f"Ingestion WebSocket error: {exc}")
        await websocket.close(code=1011)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
