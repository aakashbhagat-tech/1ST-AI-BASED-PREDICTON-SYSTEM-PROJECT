# MoveWise AI - Startup Guide

## Prerequisites
- Python 3.10+
- Install dependencies: `pip install -r requirements.txt`

## Running the Application

### Option 1: Streamlit Dashboard (Recommended)
```bash
python -m streamlit run app.py
```
- Opens at http://localhost:8501
- Provides real-time demand forecasting dashboard
- Features GNN+LSTM hybrid model with hotspot timestamps
- Auto-refresh with configurable intervals

### Option 2: HTML Frontend (Legacy)
```bash
python run_frontend.py
```
- Opens at http://localhost:8000
- Static HTML frontend with Leaflet maps
- Modern glass-panel design

### Option 3: Run Both
Open two terminals:

**Terminal 1 - Streamlit:**
```bash
python -m streamlit run app.py
```

**Terminal 2 - Frontend:**
```bash
python run_frontend.py
```

## Features
- Real-time demand hotspot predictions
- GNN-based spatial smoothing
- LSTM-based temporal memory
- Configurable forecast horizons (15, 30, 60 minutes)
- Auto-refresh with live timestamps
- Interactive demand heatmaps
- Fleet optimization recommendations

## API Endpoints
The application includes a FastAPI backend (optional):
```bash
python api/main.py
```
- Available at http://localhost:8000/api
- POST /predict/realtime - Get realtime predictions

## Troubleshooting
- Clear Streamlit cache: `streamlit cache clear`
- Check port availability: 8000 (frontend), 8501 (streamlit), 8000 (api)
- Verify all dependencies: `pip install -r requirements.txt --upgrade`
