"""
backend/services/hub_routing_service.py
Dynamic Multi-Hub Assignment and Routing Engine for AgriSmart Connect.
Determines optimal aggregation hubs and inter-hub transfer routes across Tamil Nadu.
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple

try:
    from database import fetch_all, fetch_one, get_db_cursor
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor

logger = logging.getLogger('agrismart.routing')

# Tamil Nadu District Center Coordinates (for fallback when precise GPS is missing)
DISTRICT_COORDINATES = {
    'Chennai': (13.0827, 80.2707),
    'Chengalpattu': (12.6841, 79.9836),
    'Coimbatore': (11.0168, 76.9558),
    'Cuddalore': (11.7480, 79.7714),
    'Dharmapuri': (12.1211, 78.1582),
    'Dindigul': (10.3673, 77.9803),
    'Erode': (11.3410, 77.7172),
    'Kallakurichi': (11.7384, 78.9639),
    'Kanchipuram': (12.8342, 79.7036),
    'Kanyakumari': (8.0883, 77.5385),
    'Karur': (10.9601, 78.0766),
    'Krishnagiri': (12.5186, 78.2137),
    'Madurai': (9.9252, 78.1198),
    'Mayiladuthurai': (11.1075, 79.6524),
    'Nagapattinam': (10.7656, 79.8424),
    'Namakkal': (11.2189, 78.1674),
    'Nilgiris': (11.4102, 76.6950),
    'Perambalur': (11.2342, 78.8820),
    'Pudukkottai': (10.3833, 78.8001),
    'Ramanathapuram': (9.3639, 78.8395),
    'Ranipet': (12.9298, 79.3326),
    'Salem': (11.6643, 78.1460),
    'Sivaganga': (9.8433, 78.4809),
    'Tenkasi': (8.9594, 77.3160),
    'Thanjavur': (10.7870, 79.1378),
    'Theni': (10.0104, 77.4768),
    'Thoothukudi': (8.7642, 78.1348),
    'Tiruchirappalli': (10.7905, 78.7047),
    'Trichy': (10.7905, 78.7047),
    'Tirunelveli': (8.7139, 77.7567),
    'Tirupathur': (12.4958, 78.5678),
    'Tiruppur': (11.1085, 77.3411),
    'Tiruvallur': (13.1432, 79.9074),
    'Tiruvannamalai': (12.2253, 79.0747),
    'Tiruvarur': (10.7725, 79.6365),
    'Vellore': (12.9165, 79.1325),
    'Viluppuram': (11.9401, 79.4861),
    'Virudhunagar': (9.5680, 77.9624),
}


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two GPS points in kilometers."""
    R = 6371.0  # Earth's radius in kilometers
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


def get_active_hubs() -> List[Dict[str, Any]]:
    """Fetch all operating hubs that are active and not full or temporarily closed."""
    sql = """
        SELECT hub_id, hub_code, hub_name, district, city, address,
               latitude, longitude, geofence_radius, service_radius,
               daily_capacity, current_capacity, status, cold_storage_available,
               storage_capabilities, supported_products
        FROM hubs
        WHERE status IN ('ACTIVE', 'active')
        ORDER BY hub_id ASC;
    """
    return fetch_all(sql)


def find_nearest_eligible_hub(
    lat: float,
    lon: float,
    district_hint: Optional[str] = None,
    require_cold_storage: bool = False,
    exclude_hub_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Find the closest active hub capable of handling the consignment.
    Considers geographic distance, district match, status, capacity, and cold storage.
    """
    all_hubs = get_active_hubs()
    if not all_hubs:
        logger.warning("No active hubs found in database!")
        return None

    eligible_hubs = []
    for h in all_hubs:
        if exclude_hub_id and h['hub_id'] == exclude_hub_id:
            continue
        if require_cold_storage and not h.get('cold_storage_available'):
            continue
        
        # Check capacity
        daily_cap = h.get('daily_capacity') or 1000
        cur_load = h.get('current_capacity') or 0
        if cur_load >= daily_cap:
            logger.info(f"Hub #{h['hub_id']} ({h['hub_name']}) is at maximum capacity ({cur_load}/{daily_cap}). Skipping.")
            continue

        h_lat = float(h['latitude'])
        h_lon = float(h['longitude'])
        dist = haversine_distance_km(lat, lon, h_lat, h_lon)
        
        # District match bonus (subtract effective distance by 25km for preference)
        district_bonus = 0.0
        if district_hint and h.get('district') and district_hint.strip().lower() in h['district'].strip().lower():
            district_bonus = 25.0

        effective_dist = max(0.0, dist - district_bonus)

        eligible_hubs.append({
            'hub': h,
            'distance_km': dist,
            'effective_dist': effective_dist
        })

    if not eligible_hubs:
        # If all eligible had exclusions or capacity, fallback to any active hub closest by physical distance
        fallback = sorted(all_hubs, key=lambda h: haversine_distance_km(lat, lon, float(h['latitude']), float(h['longitude'])))
        return fallback[0] if fallback else None

    # Sort by effective distance
    eligible_hubs.sort(key=lambda x: x['effective_dist'])
    return eligible_hubs[0]['hub']


def determine_order_route(
    order_id: int,
    farmer_id: int,
    buyer_id: int,
    delivery_address: str,
    delivery_lat: Optional[float] = None,
    delivery_lon: Optional[float] = None,
    require_cold_storage: bool = False
) -> Dict[str, Any]:
    """
    Dynamically determine multi-hub route for an order:
    1. Resolve Farmer origin location.
    2. Resolve Buyer destination location.
    3. Select origin Hub near farmer.
    4. Select destination Hub near customer.
    5. If origin == destination: 2 legs (Farmer -> Hub -> Customer).
       If origin != destination: 3 legs (Farmer -> Origin Hub -> Destination Hub -> Customer).
    6. Persist routes in order_routes and update order with source/destination hubs.
    """
    # 1. Fetch farmer location
    farmer = fetch_one("""
        SELECT fp.farmer_id, fp.farm_name, fp.village, fp.district, fp.state,
               fp.latitude, fp.longitude, fp.address, u.name AS farmer_name
        FROM farmer_profiles fp
        JOIN users u ON fp.user_id = u.user_id
        WHERE fp.farmer_id = %s;
    """, (farmer_id,))

    f_lat = float(farmer.get('latitude') or 11.2189) if farmer else 11.2189
    f_lon = float(farmer.get('longitude') or 78.1674) if farmer else 78.1674
    f_district = farmer.get('district') or 'Namakkal' if farmer else 'Namakkal'

    # If farmer coords look like default or missing, check district center
    if (f_lat == 0 or f_lon == 0) and f_district in DISTRICT_COORDINATES:
        f_lat, f_lon = DISTRICT_COORDINATES[f_district]

    # 2. Fetch buyer location
    buyer = fetch_one("""
        SELECT b.buyer_id, b.business_name, b.village, b.district, b.address,
               b.latitude, b.longitude, u.name AS buyer_name
        FROM buyers b
        JOIN users u ON b.user_id = u.user_id
        WHERE b.buyer_id = %s;
    """, (buyer_id,))

    b_district = buyer.get('district') if buyer else 'Chennai'
    b_lat = float(delivery_lat or (buyer.get('latitude') if buyer else None) or 13.0827)
    b_lon = float(delivery_lon or (buyer.get('longitude') if buyer else None) or 80.2707)

    # Detect district from delivery_address if possible
    addr_lower = (delivery_address or '').lower()
    for d_name in DISTRICT_COORDINATES:
        if d_name.lower() in addr_lower:
            b_district = d_name
            if delivery_lat is None or delivery_lon is None:
                b_lat, b_lon = DISTRICT_COORDINATES[d_name]
            break

    # 3. Determine Origin Hub (closest active hub to Farmer)
    source_hub = find_nearest_eligible_hub(
        lat=f_lat,
        lon=f_lon,
        district_hint=f_district,
        require_cold_storage=require_cold_storage
    )

    # 4. Determine Destination Hub (closest active hub to Buyer)
    destination_hub = find_nearest_eligible_hub(
        lat=b_lat,
        lon=b_lon,
        district_hint=b_district,
        require_cold_storage=require_cold_storage
    )

    if not source_hub:
        raise ValueError("No active collection hub available in Tamil Nadu network.")
    if not destination_hub:
        destination_hub = source_hub

    is_multi_hub = (source_hub['hub_id'] != destination_hub['hub_id'])

    # 5. Build route legs
    route_legs = []
    farmer_loc_str = f"{farmer.get('farm_name') or 'Farm'}, {f_district}" if farmer else f"Farm, {f_district}"
    customer_loc_str = delivery_address or f"Customer Address, {b_district}"

    # Leg 1: FARMER_TO_HUB
    leg1_dist = haversine_distance_km(f_lat, f_lon, float(source_hub['latitude']), float(source_hub['longitude']))
    route_legs.append({
        'sequence_number': 1,
        'route_type': 'FARMER_TO_HUB',
        'source_location': farmer_loc_str,
        'destination_location': f"{source_hub['hub_name']} ({source_hub['district']})",
        'source_hub_id': None,
        'destination_hub_id': source_hub['hub_id'],
        'distance_km': leg1_dist,
        'status': 'PENDING'
    })

    if is_multi_hub:
        # Leg 2: HUB_TO_HUB (Inter-hub Transfer)
        leg2_dist = haversine_distance_km(
            float(source_hub['latitude']), float(source_hub['longitude']),
            float(destination_hub['latitude']), float(destination_hub['longitude'])
        )
        route_legs.append({
            'sequence_number': 2,
            'route_type': 'HUB_TO_HUB',
            'source_location': f"{source_hub['hub_name']} ({source_hub['district']})",
            'destination_location': f"{destination_hub['hub_name']} ({destination_hub['district']})",
            'source_hub_id': source_hub['hub_id'],
            'destination_hub_id': destination_hub['hub_id'],
            'distance_km': leg2_dist,
            'status': 'PENDING'
        })

        # Leg 3: HUB_TO_CUSTOMER (Last-mile Delivery)
        leg3_dist = haversine_distance_km(
            float(destination_hub['latitude']), float(destination_hub['longitude']),
            b_lat, b_lon
        )
        route_legs.append({
            'sequence_number': 3,
            'route_type': 'HUB_TO_CUSTOMER',
            'source_location': f"{destination_hub['hub_name']} ({destination_hub['district']})",
            'destination_location': customer_loc_str,
            'source_hub_id': destination_hub['hub_id'],
            'destination_hub_id': None,
            'distance_km': leg3_dist,
            'status': 'PENDING'
        })
    else:
        # Single Hub Leg 2: HUB_TO_CUSTOMER (Last-mile Delivery from Source Hub)
        leg2_dist = haversine_distance_km(
            float(source_hub['latitude']), float(source_hub['longitude']),
            b_lat, b_lon
        )
        route_legs.append({
            'sequence_number': 2,
            'route_type': 'HUB_TO_CUSTOMER',
            'source_location': f"{source_hub['hub_name']} ({source_hub['district']})",
            'destination_location': customer_loc_str,
            'source_hub_id': source_hub['hub_id'],
            'destination_hub_id': None,
            'distance_km': leg2_dist,
            'status': 'PENDING'
        })

    # 6. Save in database
    with get_db_cursor(commit=True) as cur:
        # Clear any prior planned routes for this order if rerouted
        cur.execute("DELETE FROM order_routes WHERE order_id = %s;", (order_id,))
        for leg in route_legs:
            cur.execute("""
                INSERT INTO order_routes (
                    order_id, sequence_number, route_type,
                    source_location, destination_location,
                    source_hub_id, destination_hub_id,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                order_id, leg['sequence_number'], leg['route_type'],
                leg['source_location'], leg['destination_location'],
                leg['source_hub_id'], leg['destination_hub_id'],
                leg['status']
            ))

        # Update order with routing metadata
        cur.execute("""
            UPDATE orders
            SET source_hub_id = %s,
                destination_hub_id = %s,
                hub_id = %s,
                requires_hub_transfer = %s
            WHERE order_id = %s;
        """, (
            source_hub['hub_id'],
            destination_hub['hub_id'],
            source_hub['hub_id'],  # current active hub
            is_multi_hub,
            order_id
        ))

        # Update source hub load
        cur.execute("""
            UPDATE hubs
            SET current_capacity = COALESCE(current_capacity, 0) + 1
            WHERE hub_id = %s;
        """, (source_hub['hub_id'],))

    logger.info(
        f"[Routing] Order #{order_id} assigned route: "
        f"SourceHub='{source_hub['hub_name']}' -> DestinationHub='{destination_hub['hub_name']}' "
        f"(MultiHub={is_multi_hub}, Legs={len(route_legs)})"
    )

    return {
        'order_id': order_id,
        'source_hub': source_hub,
        'destination_hub': destination_hub,
        'requires_transfer': is_multi_hub,
        'legs': route_legs,
        'total_distance_km': sum(l['distance_km'] for l in route_legs)
    }
