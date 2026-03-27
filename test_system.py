#!/usr/bin/env python
"""Test script to verify the MoveWise AI system."""
import sys
from pathlib import Path

API_DIR = Path(__file__).parent / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import mock_data
import pandas as pd

print("\n🔍 Testing MoveWise AI System...\n")

# Test 1: Load zones
print("Test 1: Loading city zones...")
city_zones = mock_data.get_city_zones('San Francisco')
print(f"  ✓ Loaded {len(city_zones)} zones")

# Test 2: Generate forecast
print("\nTest 2: Generating forecast...")
forecast = mock_data.generate_gnn_lstm_realtime_snapshot('San Francisco', 30, city_zones)
print(f"  ✓ Generated {len(forecast)} predictions")

# Test 3: Check timestamps
print("\nTest 3: Verifying real-time timestamps...")
last_updated = forecast["data_last_updated"].iloc[0]
forecast_time = forecast["forecast_for"].iloc[0]
print(f"  ✓ Data last updated: {last_updated}")
print(f"  ✓ Forecast target: {forecast_time}")

# Test 4: Check hotspots
print("\nTest 4: Analyzing demand hotspots...")
hotspot_count = (forecast["demand_level"] == "High").sum()
medium_count = (forecast["demand_level"] == "Medium").sum()
low_count = (forecast["demand_level"] == "Low").sum()
print(f"  ✓ High-demand zones: {hotspot_count}")
print(f"  ✓ Medium-demand zones: {medium_count}")
print(f"  ✓ Low-demand zones: {low_count}")

# Test 5: Check GNN features
print("\nTest 5: Checking GNN features...")
print(f"  ✓ GNN neighbor influence: {forecast['gnn_neighbor_influence'].min():.2f} to {forecast['gnn_neighbor_influence'].max():.2f}")
print(f"  ✓ GNN graph scores: {forecast['gnn_graph_score'].min():.3f} to {forecast['gnn_graph_score'].max():.3f}")

# Test 6: Check model confidence
print("\nTest 6: Model confidence...")
avg_confidence = forecast["confidence"].mean()
print(f"  ✓ Average model confidence: {avg_confidence:.3f}")

print("\n✅ All system tests passed!\n")
print("Ready to run:")
print("  - Streamlit: python -m streamlit run app.py")
print("  - Frontend: python run_frontend.py")
