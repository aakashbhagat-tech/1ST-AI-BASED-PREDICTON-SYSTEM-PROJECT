"""
Real-time Data Ingestion Manager
Handles streaming data from multiple sources: APIs, message queues, sensors, etc.
"""

from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RealtimeDataIngestionManager:
    """
    Manages real-time data ingestion from various sources.
    Supports: APIs, WebSockets, Kafka, files, sensors, etc.
    """
    
    def __init__(self, buffer_size: int = 1000):
        self.sources = {}  # Track active data sources
        self.data_buffer = defaultdict(list)  # Buffer ingested data by source
        self.buffer_size = buffer_size
        
    def register_source(self, source_id: str):
        """Register a new data source"""
        self.sources[source_id] = {
            "registered_at": datetime.now(),
            "status": "active",
            "data_points_received": 0
        }
        logger.info(f"Source registered: {source_id}")
        
    def unregister_source(self, source_id: str):
        """Unregister a data source"""
        if source_id in self.sources:
            del self.sources[source_id]
            logger.info(f"Source unregistered: {source_id}")
    
    def ingest_data(self, source_id: str, data_point: Dict[str, Any]):
        """
        Ingest a single data point from a source.
        
        Expected data format:
        {
            "zone_id": "Z01",
            "timestamp": "2024-03-27T10:30:00",
            "current_demand": 45,
            "available_vehicles": 12,
            "trip_count": 23,
            "metadata": {...}
        }
        """
        if source_id not in self.sources:
            self.register_source(source_id)
        
        # Add ingestion timestamp
        data_point["ingested_at"] = datetime.now().isoformat()
        data_point["source"] = source_id
        
        # Store in buffer
        self.data_buffer[source_id].append(data_point)
        
        # Maintain buffer size limit
        if len(self.data_buffer[source_id]) > self.buffer_size:
            self.data_buffer[source_id].pop(0)
        
        # Update stats
        self.sources[source_id]["data_points_received"] += 1
        self.sources[source_id]["last_update"] = datetime.now().isoformat()
        
        logger.info(f"Ingested data point from {source_id}: {data_point.get('zone_id', 'unknown')}")
    
    def ingest_batch(self, source_id: str, data_points: List[Dict[str, Any]]):
        """Ingest multiple data points at once"""
        for point in data_points:
            self.ingest_data(source_id, point)
    
    def get_latest_data(self, source_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get latest N data points from a source"""
        return self.data_buffer[source_id][-limit:] if source_id in self.data_buffer else []
    
    def get_source_stats(self, source_id: str) -> Dict[str, Any]:
        """Get statistics for a specific source"""
        if source_id not in self.sources:
            return {}
        return self.sources[source_id]
    
    def get_all_sources(self) -> Dict[str, Any]:
        """Get all registered sources and their stats"""
        return self.sources
    
    def aggregate_demand(self) -> Dict[str, Any]:
        """
        Aggregate real-time demand data across all sources.
        Returns city-wide demand summary.
        """
        aggregated = defaultdict(lambda: {"total_demand": 0, "total_vehicles": 0, "zones": {}})
        
        for source_id, data_points in self.data_buffer.items():
            if data_points:
                latest = data_points[-1]  # Last data point
                zone_id = latest.get("zone_id", "unknown")
                
                aggregated[zone_id]["total_demand"] += latest.get("current_demand", 0)
                aggregated[zone_id]["total_vehicles"] += latest.get("available_vehicles", 0)
                aggregated[zone_id]["zones"][source_id] = {
                    "demand": latest.get("current_demand", 0),
                    "timestamp": latest.get("timestamp")
                }
        
        return dict(aggregated)
