# MoveWise AI MVP Scope Document

## Overview
Based on the original MoveWise AI Product Requirements Document (PRD), this document outlines the **adjusted scope** for the standalone local demo MVP. 

To ensure a foolproof demonstration that does not rely on active cloud infrastructure, network connectivity, or external GCP services, the architecture has been condensed into a fully self-contained Streamlit application.

## In Scope (Delivered in this Demo)
- **Data Simulation**: Programmatic generation of fake city zones (using real coordinate baseline), historical demand data mimicking real-world peaks, and predictive forecasting logic using mathematical heuristics.
- **FastAPI Backend Service**: A decoupled REST API with `/predict` and `/ingest` endpoints providing the foundation for real data integration.
- **Dockerization**: Containerized environment using Docker and Docker Compose for easy deployment to Cloud Run or generic VM.
- **Dashboard Interface**: A Streamlit frontend that serves as the internal operational tool.
- **Showcase Web UI**: A highly polished, standalone HTML/JS/CSS frontend for judge presentations.
- **KPI Summary Cards**: Real-time aggregation of total predicted demand, average trips per zone, hotspot identification, and fleet allocation sizes.
- **Interactive Heatmap**: Visualizations displaying predicted demand intensity across zones.

## Out of Scope (Omitted from this Demo)
- **Live Cloud Data Pipelines**: Integration with active BigQuery or GCS buckets is replaced by the Mock Ingestion endpoint.
- **Production Graph AI Model**: The heavy Graph Neural Network remains a simulated heuristic within the Python logic.
- **Real-Time Dispatch**: Automated vehicle dispatching remains a theoretical recommendation.

## Technical Stack
- **Frontend / App Engine**: Streamlit
- **Data Manipulation**: Pandas, NumPy
- **Spatial Visualization**: PyDeck
