# MoveWise AI

MoveWise AI is now configured as a standalone Streamlit app for urban mobility demand forecasting.

## Run locally

```bash
cd movewise-ai
pip install -r requirements.txt
streamlit run app.py
```

## Port setup

- Streamlit app: `http://127.0.0.1:8501` (default `streamlit run app.py`)
- API server: `http://127.0.0.1:8000` (`uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload`)
- Frontend static UI: `http://127.0.0.1:5500` (`cd frontend && python -m http.server 5500`)

WebSocket link:
- `frontend/script.js` now auto-connects to `127.0.0.1:8000` when frontend runs on localhost.
- You can override API host with query param, for example:
  - `http://127.0.0.1:5500/?api=127.0.0.1:8000`

## What changed

- Docker deployment files were removed.
- GCS deployment files were removed.
- The dashboard now shows timestamps for changing data, including:
  - data last updated
  - forecast target time
  - hotspot table refresh time
  - KPI refresh time

## App behavior

- Forecasts are generated from local mock data in [`api/mock_data.py`](c:\Users\sk860\OneDrive\Desktop\HACKATHON\movewise-ai\api\mock_data.py).
- Each refresh regenerates hotspot rankings and fleet recommendations with a fresh timestamp.
- The Streamlit dashboard is the primary entrypoint.
