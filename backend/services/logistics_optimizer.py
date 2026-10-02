"""
AgriSmart Connect - AI Logistics Optimization Engine.
Integrates:
1. Multi-criteria Farmer-to-Hub Matching (Haversine distance, hub capacity, crop demand).
2. Hub Inventory & Shortage/Overstock Intelligence.
3. Perishable Crop Priority (FEFO / Freshness Decay scoring).
4. Google OR-Tools Delivery Route Optimization (Capacitated VRP).
"""

import math
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False

from database import fetch_all, fetch_one, get_db_cursor
from services.demand_ml_engine import DemandPredictionEngine

logger = logging.getLogger('agrismart.logistics_opt')


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometers."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 999.0
    r = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(r * c, 2)


PERISHABILITY_FACTORS = {
    'Tomato': {'shelf_days': 5, 'priority_weight': 1.5, 'type': 'high'},
    'Banana': {'shelf_days': 6, 'priority_weight': 1.4, 'type': 'high'},
    'Green Chilli': {'shelf_days': 7, 'priority_weight': 1.2, 'type': 'medium'},
    'Cabbage': {'shelf_days': 8, 'priority_weight': 1.2, 'type': 'medium'},
    'Moringa': {'shelf_days': 5, 'priority_weight': 1.4, 'type': 'high'},
    'Onion': {'shelf_days': 30, 'priority_weight': 0.8, 'type': 'low'},
    'Potato': {'shelf_days': 45, 'priority_weight': 0.7, 'type': 'low'},
    'Coconut': {'shelf_days': 60, 'priority_weight': 0.6, 'type': 'low'},
    'Rice': {'shelf_days': 365, 'priority_weight': 0.4, 'type': 'low'}
}


class LogisticsOptimizer:
    """Core mathematical optimization and matching algorithms."""

    @classmethod
    def recommend_hubs_for_farmer(
        cls,
        farmer_id: int,
        crop_id: int,
        quantity_kg: float,
        harvest_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        AI Farmer-to-Hub allocation scoring based on:
        - Haversine distance from farm to hub
        - Hub available storage capacity
        - Predicted crop demand at the hub's district
        - Perishable crop priority
        """
        farmer = fetch_one("SELECT * FROM farmer_profiles WHERE farmer_id = %s;", (farmer_id,))
        if not farmer or farmer.get('latitude') is None:
            # Fallback coordinates (Namakkal)
            f_lat, f_lon = 11.2189, 78.1674
            farmer_district = 'Namakkal'
        else:
            f_lat, f_lon = float(farmer['latitude']), float(farmer['longitude'])
            farmer_district = farmer.get('district', 'Namakkal')

        crop = fetch_one("SELECT crop_name FROM crops WHERE crop_id = %s;", (crop_id,))
        crop_name = crop['crop_name'] if crop else 'Vegetables'
        perish_meta = PERISHABILITY_FACTORS.get(crop_name, {'shelf_days': 7, 'priority_weight': 1.0, 'type': 'medium'})

        hubs = fetch_all("""
            SELECT hub_id, hub_name, district, taluk, town, latitude, longitude,
                   capacity_kg, COALESCE(current_inventory_kg, 0) AS current_inventory_kg,
                   delivery_radius_km, status
            FROM hubs
            WHERE status = 'active';
        """)

        ranked_hubs = []
        for h in hubs:
            h_lat, h_lon = float(h['latitude']), float(h['longitude'])
            dist = haversine_km(f_lat, f_lon, h_lat, h_lon)
            total_cap = float(h['capacity_kg'] or 40000.0)
            curr_inv = float(h['current_inventory_kg'] or 0.0)
            avail_cap = max(0.0, total_cap - curr_inv)

            # Demand prediction in hub district
            pred = DemandPredictionEngine.predict_demand(crop_id, h['district'])
            demand_kg = pred['predicted_demand_kg']

            # Scoring algorithm:
            # Distance penalty (closer is better)
            distance_score = max(0.0, 100.0 - (dist * 1.5))
            # Capacity score (has enough room for this batch)
            capacity_score = 100.0 if avail_cap >= quantity_kg else (avail_cap / quantity_kg * 100.0 if quantity_kg else 50.0)
            # Demand bonus (places with shortage need produce more)
            demand_score = min(100.0, (demand_kg / 300.0) * 80.0)

            total_score = (distance_score * 0.45) + (capacity_score * 0.25) + (demand_score * 0.30)
            if dist > float(h['delivery_radius_km'] or 50.0) * 1.5:
                total_score *= 0.6  # Out of primary delivery radius penalty

            reason_parts = [f"{dist} km away"]
            if avail_cap >= quantity_kg:
                reason_parts.append(f"{int(avail_cap):,} kg capacity available")
            else:
                reason_parts.append(f"Tight capacity ({int(avail_cap)} kg left)")

            if pred['demand_level'] == 'HIGH':
                reason_parts.append(f"High {crop_name} demand (+{int(demand_kg)} kg forecast)")
            else:
                reason_parts.append(f"Steady {crop_name} demand")

            if perish_meta['type'] == 'high' and dist <= 30.0:
                reason_parts.append("Optimal for perishable dispatch (fast transit)")

            ranked_hubs.append({
                'hub_id': h['hub_id'],
                'hub_name': h['hub_name'],
                'district': h['district'],
                'town': h.get('town') or h.get('taluk') or h['district'],
                'distance_km': dist,
                'available_capacity_kg': round(avail_cap, 2),
                'total_capacity_kg': total_cap,
                'demand_kg': demand_kg,
                'demand_level': pred['demand_level'],
                'score': round(total_score, 1),
                'recommendation_reason': ". ".join(reason_parts) + ".",
                'is_top_match': False
            })

        # Sort descending by score
        ranked_hubs.sort(key=lambda x: x['score'], reverse=True)
        if ranked_hubs:
            ranked_hubs[0]['is_top_match'] = True

        top_choice = ranked_hubs[0] if ranked_hubs else None

        return {
            'farmer_id': farmer_id,
            'crop_id': crop_id,
            'crop_name': crop_name,
            'quantity_kg': quantity_kg,
            'top_recommendation': top_choice,
            'all_hubs': ranked_hubs[:6]
        }

    @classmethod
    def get_hub_inventory_intelligence(cls, hub_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Calculates current inventory vs incoming scheduled supply vs predicted demand.
        Flags predicted shortages or overstocks for each hub and crop.
        """
        hub_filter = "WHERE h.status = 'active'"
        params = []
        if hub_id:
            hub_filter += " AND h.hub_id = %s"
            params.append(hub_id)

        hubs = fetch_all(f"""
            SELECT h.hub_id, h.hub_name, h.district, h.capacity_kg
            FROM hubs h
            {hub_filter}
            ORDER BY h.hub_id ASC;
        """, tuple(params) if params else None)

        crops = fetch_all("SELECT crop_id, crop_name FROM crops WHERE is_active = TRUE ORDER BY crop_id ASC;")

        alerts = []
        for h in hubs:
            hid = h['hub_id']
            dist = h['district']

            for c in crops:
                cid = c['crop_id']
                cname = c['crop_name']

                # Current stock in hub
                stock_row = fetch_one("""
                    SELECT COALESCE(SUM(available_quantity_kg), 0) AS curr_kg
                    FROM hub_inventory
                    WHERE hub_id = %s AND crop_id = %s AND status = 'available';
                """, (hid, cid))
                curr_stock = float(stock_row['curr_kg']) if stock_row else 0.0

                # Expected incoming farmer supply allocated to this hub
                supply_row = fetch_one("""
                    SELECT COALESCE(SUM(available_quantity_kg), 0) AS incoming_kg
                    FROM farmer_produce
                    WHERE preferred_hub_id = %s AND crop_id = %s AND status IN ('available', 'ACTIVE');
                """, (hid, cid))
                incoming_supply = float(supply_row['incoming_kg']) if supply_row else 0.0

                # Demand prediction for tomorrow
                pred = DemandPredictionEngine.predict_demand(cid, dist)
                pred_demand = pred['predicted_demand_kg']

                total_expected_supply = curr_stock + incoming_supply
                net_balance = round(total_expected_supply - pred_demand, 2)

                if net_balance < -50.0:
                    status = 'SHORTAGE'
                    alert_level = 'HIGH' if net_balance < -150.0 else 'MEDIUM'
                    shortage_kg = abs(net_balance)
                    message = (
                        f"{cname} shortage predicted at {h['hub_name']}. "
                        f"Forecast demand: {int(pred_demand)} kg vs supply: {int(total_expected_supply)} kg. "
                        f"Deficit: {int(shortage_kg)} kg."
                    )
                    action = f"Request additional {int(shortage_kg)} kg supply from nearby registered farmers."
                elif net_balance > 250.0:
                    status = 'OVERSTOCK'
                    alert_level = 'MEDIUM'
                    message = (
                        f"Excess {cname} inventory at {h['hub_name']}. "
                        f"Expected supply: {int(total_expected_supply)} kg exceeds predicted demand of {int(pred_demand)} kg."
                    )
                    action = "Promote via wholesale buyer demand matching or redirect incoming batches."
                else:
                    status = 'OPTIMAL'
                    alert_level = 'NORMAL'
                    message = f"{h['hub_name']} has balanced {cname} inventory."
                    action = "Maintain standard automated fulfillment."

                alerts.append({
                    'hub_id': hid,
                    'hub_name': h['hub_name'],
                    'district': dist,
                    'crop_id': cid,
                    'crop_name': cname,
                    'current_stock_kg': curr_stock,
                    'expected_supply_kg': incoming_supply,
                    'total_available_kg': total_expected_supply,
                    'predicted_demand_kg': pred_demand,
                    'net_balance_kg': net_balance,
                    'status': status,
                    'alert_level': alert_level,
                    'message': message,
                    'action': action,
                    'is_simulated': pred.get('is_simulated', True)
                })

        return alerts

    @classmethod
    def calculate_perishable_priority(cls, produce_id: int) -> Dict[str, Any]:
        """Calculates freshness priority and shelf-life status (FEFO)."""
        produce = fetch_one("""
            SELECT fp.produce_id, fp.crop_id, fp.harvest_date, fp.available_quantity_kg,
                   c.crop_name
            FROM farmer_produce fp
            JOIN crops c ON fp.crop_id = c.crop_id
            WHERE fp.produce_id = %s;
        """, (produce_id,))

        if not produce:
            return {'priority': 'NORMAL', 'reason': 'Unknown produce batch'}

        cname = produce['crop_name']
        hdate = produce['harvest_date']
        today = date.today()

        days_since_harvest = (today - hdate).days if isinstance(hdate, date) else 0
        perish_info = PERISHABILITY_FACTORS.get(cname, {'shelf_days': 7, 'type': 'medium'})
        shelf_days = perish_info['shelf_days']

        days_remaining = max(0, shelf_days - max(0, days_since_harvest))

        if days_since_harvest >= 2 and perish_info['type'] == 'high':
            priority = 'HIGH'
            reason = f"{cname} batch harvested {days_since_harvest} days ago. Shelf life: ~{days_remaining} days left. Priority dispatch required."
        elif days_since_harvest == 0:
            priority = 'NORMAL'
            reason = f"Harvested today. Optimal freshness grade."
        else:
            priority = 'MEDIUM' if days_remaining <= 3 else 'NORMAL'
            reason = f"Harvested {days_since_harvest} days ago. Freshness intact."

        return {
            'produce_id': produce_id,
            'crop_name': cname,
            'days_since_harvest': days_since_harvest,
            'days_remaining': days_remaining,
            'priority': priority,
            'reason': reason
        }

    @classmethod
    def optimize_delivery_route(
        cls,
        hub_id: int,
        order_ids: List[int],
        vehicle_capacity_kg: float = 1200.0
    ) -> Dict[str, Any]:
        """
        Vehicle Routing Problem (VRP) optimization using Google OR-Tools.
        Minimizes total travel distance from hub through consumer stops and back.
        """
        hub = fetch_one("SELECT * FROM hubs WHERE hub_id = %s;", (hub_id,))
        if not hub:
            raise ValueError(f"Hub #{hub_id} not found.")

        hub_lat = float(hub['latitude'])
        hub_lon = float(hub['longitude'])

        # Fetch orders with delivery locations
        placeholders = ','.join(['%s'] * len(order_ids))
        orders = fetch_all(f"""
            SELECT o.order_id, o.delivery_address, o.delivery_latitude, o.delivery_longitude,
                   u.name AS customer_name,
                   COALESCE(SUM(oi.quantity_kg), 10.0) AS total_weight_kg
            FROM orders o
            JOIN buyers b ON o.buyer_id = b.buyer_id
            JOIN users u ON b.user_id = u.user_id
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.order_id IN ({placeholders})
            GROUP BY o.order_id, o.delivery_address, o.delivery_latitude, o.delivery_longitude, u.name;
        """, tuple(order_ids))

        if not orders:
            raise ValueError("No valid orders provided for route optimization.")

        # Prepare locations array: index 0 is Hub, indices 1..N are stops
        locations = [(hub_lat, hub_lon, 'HUB Depot: ' + hub['hub_name'], None, 0.0)]
        for o in orders:
            o_lat = float(o['delivery_latitude']) if o.get('delivery_latitude') is not None else (hub_lat + 0.04)
            o_lon = float(o['delivery_longitude']) if o.get('delivery_longitude') is not None else (hub_lon + 0.03)
            weight = float(o.get('total_weight_kg') or 10.0)
            locations.append((o_lat, o_lon, o['delivery_address'], o['order_id'], weight, o['customer_name']))

        num_locations = len(locations)

        # Build distance matrix (in integer meters for OR-Tools solver)
        distance_matrix = []
        for i in range(num_locations):
            row = []
            for j in range(num_locations):
                if i == j:
                    row.append(0)
                else:
                    d_km = haversine_km(locations[i][0], locations[i][1], locations[j][0], locations[j][1])
                    row.append(int(d_km * 1000))  # in meters
            distance_matrix.append(row)

        demands = [0] + [int(loc[4]) for loc in locations[1:]]

        route_sequence = []
        total_distance_meters = 0

        # Solve using Google OR-Tools
        if HAS_ORTOOLS and num_locations > 1:
            try:
                manager = pywrapcp.RoutingIndexManager(num_locations, 1, 0)
                routing = pywrapcp.RoutingModel(manager)

                def distance_callback(from_index, to_index):
                    from_node = manager.IndexToNode(from_index)
                    to_node = manager.IndexToNode(to_index)
                    return distance_matrix[from_node][to_node]

                transit_callback_index = routing.RegisterTransitCallback(distance_callback)
                routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

                # Add capacity constraint
                def demand_callback(from_index):
                    from_node = manager.IndexToNode(from_index)
                    return demands[from_node]

                demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
                routing.AddDimensionWithVehicleCapacity(
                    demand_callback_index,
                    0,  # null capacity slack
                    [int(vehicle_capacity_kg)],
                    True,  # start cumul to zero
                    'Capacity'
                )

                search_parameters = pywrapcp.DefaultRoutingSearchParameters()
                search_parameters.first_solution_strategy = (
                    routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
                )

                solution = routing.SolveWithParameters(search_parameters)

                if solution:
                    index = routing.Start(0)
                    while not routing.IsEnd(index):
                        node = manager.IndexToNode(index)
                        route_sequence.append(node)
                        previous_index = index
                        index = solution.Value(routing.NextVar(index))
                        total_distance_meters += routing.GetArcCostForVehicle(previous_index, index, 0)
                    route_sequence.append(manager.IndexToNode(index))
            except Exception as e:
                logger.error(f"OR-Tools solver exception: {e}. Falling back to nearest neighbor.")
                route_sequence = []

        # Heuristic Nearest-Neighbor Fallback if OR-Tools didn't produce sequence
        if not route_sequence:
            unvisited = list(range(1, num_locations))
            curr = 0
            route_sequence = [0]
            while unvisited:
                next_node = min(unvisited, key=lambda x: distance_matrix[curr][x])
                total_distance_meters += distance_matrix[curr][next_node]
                route_sequence.append(next_node)
                unvisited.remove(next_node)
                curr = next_node
            total_distance_meters += distance_matrix[curr][0]
            route_sequence.append(0)

        total_distance_km = round(total_distance_meters / 1000.0, 2)
        # Estimated time: 35 km/h average rural/urban speed + 8 min per delivery drop
        num_stops = len(locations) - 1
        est_minutes = int((total_distance_km / 35.0) * 60.0) + (num_stops * 8)

        total_weight_kg = sum(demands)
        capacity_used_pct = round((total_weight_kg / vehicle_capacity_kg) * 100.0, 1)

        # Build ordered stop details
        stops_result = []
        seq = 1
        for node in route_sequence:
            loc = locations[node]
            if node == 0 and seq == 1:
                # Depot start
                stops_result.append({
                    'sequence': 0,
                    'type': 'DEPOT_START',
                    'name': hub['hub_name'],
                    'address': hub['address'],
                    'latitude': loc[0],
                    'longitude': loc[1],
                    'quantity_kg': 0,
                    'status': 'DEPARTED'
                })
            elif node != 0:
                stops_result.append({
                    'sequence': seq,
                    'type': 'CUSTOMER_DELIVERY',
                    'order_id': loc[3],
                    'customer_name': loc[5],
                    'address': loc[2],
                    'latitude': loc[0],
                    'longitude': loc[1],
                    'quantity_kg': loc[4],
                    'status': 'PENDING'
                })
                seq += 1

        # Persist generated route into database
        route_id = None
        try:
            with get_db_cursor(commit=True) as cur:
                cur.execute("""
                    INSERT INTO routes (
                        hub_id, total_distance_km, estimated_time_minutes,
                        vehicle_capacity_kg, capacity_used_kg, delivery_count, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'PLANNED')
                    RETURNING route_id;
                """, (hub_id, total_distance_km, est_minutes, vehicle_capacity_kg, total_weight_kg, num_stops))
                route_id = cur.fetchone()['route_id']

                for st in stops_result:
                    if st['type'] == 'CUSTOMER_DELIVERY':
                        cur.execute("""
                            INSERT INTO route_stops (
                                route_id, order_id, stop_sequence, customer_name,
                                delivery_address, latitude, longitude, quantity_kg, status
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING');
                        """, (
                            route_id, st['order_id'], st['sequence'], st['customer_name'],
                            st['address'], st['latitude'], st['longitude'], st['quantity_kg']
                        ))
        except Exception as e:
            logger.error(f"Could not persist optimized route: {e}")

        return {
            'route_id': route_id,
            'hub_id': hub_id,
            'hub_name': hub['hub_name'],
            'total_distance_km': total_distance_km,
            'estimated_time_minutes': est_minutes,
            'total_weight_kg': total_weight_kg,
            'vehicle_capacity_kg': vehicle_capacity_kg,
            'capacity_used_percent': capacity_used_pct,
            'delivery_count': num_stops,
            'route_sequence': route_sequence,
            'stops': stops_result,
            'algorithm': 'Google OR-Tools VRP' if HAS_ORTOOLS else 'Nearest-Neighbor Heuristic'
        }
