"""
backend/services/geofence_service.py
GPS Telemetry and Hub Geofencing Detection for AgriSmart Connect.
Monitors driver proximity to regional hubs during active trips.
"""

import math
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from services.hub_routing_service import haversine_distance_km
    from config import Config
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.services.hub_routing_service import haversine_distance_km
    from backend.config import Config

logger = logging.getLogger('agrismart.geofence')


def record_partner_location(
    partner_id: int,
    latitude: float,
    longitude: float,
    order_id: Optional[int] = None,
    speed_kmh: float = 0.0,
    heading: float = 0.0
) -> Dict[str, Any]:
    """
    Log driver GPS coordinate during active transit and evaluate hub geofences.
    """
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO delivery_partner_locations (
                delivery_partner_id, order_id, latitude, longitude, speed_kmh, heading, timestamp
            )
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING id, timestamp;
        """, (partner_id, order_id, latitude, longitude, speed_kmh, heading))
        rec = cur.fetchone()

    # Check proximity to all active hubs
    hubs = fetch_all("""
        SELECT hub_id, hub_code, hub_name, district, latitude, longitude,
               COALESCE(geofence_radius, 500.0) AS geofence_radius_m
        FROM hubs
        WHERE status IN ('ACTIVE', 'active');
    """)

    geofence_alert = None
    closest_hub = None
    min_dist_m = float('inf')

    for h in hubs:
        h_lat = float(h['latitude'])
        h_lon = float(h['longitude'])
        dist_km = haversine_distance_km(latitude, longitude, h_lat, h_lon)
        dist_m = dist_km * 1000.0

        if dist_m < min_dist_m:
            min_dist_m = dist_m
            closest_hub = h

        fence_radius = float(h.get('geofence_radius_m') or Config.GEOFENCE_RADIUS_METERS)
        if dist_m <= fence_radius:
            geofence_alert = {
                'within_geofence': True,
                'hub_id': h['hub_id'],
                'hub_code': h['hub_code'],
                'hub_name': h['hub_name'],
                'district': h['district'],
                'distance_meters': round(dist_m, 1),
                'message': f"You appear to have reached {h['hub_name']}. Please confirm arrival with the hub terminal."
            }
            break

    return {
        'location_id': rec['id'],
        'recorded_at': rec['timestamp'].isoformat() if hasattr(rec['timestamp'], 'isoformat') else str(rec['timestamp']),
        'closest_hub': {
            'hub_name': closest_hub['hub_name'] if closest_hub else None,
            'distance_meters': round(min_dist_m, 1) if closest_hub else None
        },
        'geofence_alert': geofence_alert
    }
