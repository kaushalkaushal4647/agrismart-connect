"""
AgriSmart Connect - AI Logistics and Route Optimization Routes.
Blueprint: logistics_bp (/api/logistics)
Provides endpoints for:
- Logistics Dashboard KPIs & AI Alerts
- Crop Demand Predictions (XGBoost)
- Farmer -> Hub AI Recommendations
- Google OR-Tools Delivery Route Optimization
- Tamil Nadu Map Unified Geospatial Data
"""

from datetime import date
from flask import Blueprint, request, jsonify

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from auth_middleware import token_required, roles_required
    from services.demand_ml_engine import DemandPredictionEngine
    from services.logistics_optimizer import LogisticsOptimizer, haversine_km
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.auth_middleware import token_required, roles_required
    from backend.services.demand_ml_engine import DemandPredictionEngine
    from backend.services.logistics_optimizer import LogisticsOptimizer, haversine_km

logistics_bp = Blueprint('logistics', __name__)


@logistics_bp.route('/dashboard', methods=['GET'])
def get_logistics_dashboard():
    """Aggregate high-level logistics metrics and live AI intelligence alerts."""
    try:
        # Total registered farmers
        farmers_stat = fetch_one("SELECT COUNT(*) AS total_farmers FROM farmer_profiles;")
        total_farmers = farmers_stat['total_farmers'] if farmers_stat else 0

        # Active hubs
        hubs_stat = fetch_one("SELECT COUNT(*) AS active_hubs, COALESCE(SUM(capacity_kg), 0) AS total_capacity FROM hubs WHERE status = 'active';")
        active_hubs = hubs_stat['active_hubs'] if hubs_stat else 0
        total_capacity = float(hubs_stat['total_capacity'] or 0.0)

        # Orders & deliveries today
        orders_stat = fetch_one("""
            SELECT 
                COUNT(*) AS total_orders,
                COALESCE(SUM(CASE WHEN order_date::date = CURRENT_DATE THEN 1 ELSE 0 END), 0) AS today_orders,
                COALESCE(SUM(CASE WHEN order_status IN ('placed', 'confirmed', 'at_hub', 'packed', 'out_for_delivery') THEN 1 ELSE 0 END), 0) AS pending_deliveries
            FROM orders;
        """)

        # Hub Inventory in kg
        inv_stat = fetch_one("SELECT COALESCE(SUM(available_quantity_kg), 0) AS current_inventory_kg FROM hub_inventory WHERE status = 'available';")
        current_inventory_kg = float(inv_stat['current_inventory_kg'] or 0.0)

        # Aggregated predicted demand across major TN hubs for tomorrow
        pred_stat = fetch_one("SELECT COALESCE(SUM(predicted_demand_kg), 0) AS total_predicted_demand FROM demand_predictions WHERE target_date >= CURRENT_DATE;")
        total_demand = float(pred_stat['total_predicted_demand'] or 3200.0)

        # Live AI Inventory & Shortage Alerts
        alerts = LogisticsOptimizer.get_hub_inventory_intelligence()

        return jsonify({
            'status': 'success',
            'overview': {
                'total_farmers': total_farmers,
                'active_hubs': active_hubs,
                'total_capacity_kg': total_capacity,
                'today_orders': orders_stat['today_orders'] if orders_stat else 0,
                'pending_deliveries': orders_stat['pending_deliveries'] if orders_stat else 0,
                'current_inventory_kg': current_inventory_kg,
                'predicted_demand_kg': total_demand
            },
            'alerts': alerts[:8]
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@logistics_bp.route('/demand', methods=['GET'])
def get_demand_predictions():
    """Retrieve demand predictions filterable by crop, district, and date."""
    crop_id = request.args.get('crop_id', type=int)
    district = request.args.get('district', default='Namakkal')

    try:
        if crop_id:
            prediction = DemandPredictionEngine.predict_demand(crop_id, district)
            return jsonify({'status': 'success', 'predictions': [prediction]}), 200

        predictions = DemandPredictionEngine.get_district_demand_summary(district)
        return jsonify({'status': 'success', 'district': district, 'predictions': predictions}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@logistics_bp.route('/inventory-alerts', methods=['GET'])
def get_inventory_alerts():
    """Retrieve AI shortage, surplus, and optimal stock alerts across all collection hubs."""
    hub_id = request.args.get('hub_id', type=int)
    try:
        alerts = LogisticsOptimizer.get_hub_inventory_intelligence(hub_id)
        return jsonify({'status': 'success', 'alerts': alerts}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@logistics_bp.route('/farmer/<int:farmer_id>/recommendations', methods=['GET'])
def get_farmer_recommendations(farmer_id):
    """Recommend optimal collection hubs for a farmer based on distance, capacity, and demand."""
    crop_id = request.args.get('crop_id', default=1, type=int)
    quantity_kg = request.args.get('quantity_kg', default=200.0, type=float)

    try:
        recommendations = LogisticsOptimizer.recommend_hubs_for_farmer(farmer_id, crop_id, quantity_kg)
        return jsonify({'status': 'success', 'recommendation': recommendations}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@logistics_bp.route('/recommendations', methods=['GET'])
def get_all_farmer_hub_recommendations():
    """
    Admin-facing endpoint: list AI-matched farmer-hub recommendations across all active farmers.
    Returns top N matches sorted by match score.
    """
    limit = request.args.get('limit', default=12, type=int)

    try:
        # Fetch active farmers with location data
        farmers = fetch_all("""
            SELECT fp.farmer_id, u.name AS farmer_name, fp.district AS farm_district,
                   fp.latitude, fp.longitude
            FROM farmer_profiles fp
            JOIN users u ON fp.user_id = u.user_id
            WHERE fp.latitude IS NOT NULL AND fp.longitude IS NOT NULL
            LIMIT 30;
        """)

        # Fetch available hubs
        hubs = fetch_all("""
            SELECT hub_id, hub_name, district, latitude, longitude, capacity_kg
            FROM hubs
            WHERE status = 'active' AND latitude IS NOT NULL
            LIMIT 20;
        """)

        import math
        def haversine(lat1, lon1, lat2, lon2):
            if None in (lat1, lon1, lat2, lon2):
                return 999
            R = 6371.0
            dlat = math.radians(float(lat2) - float(lat1))
            dlon = math.radians(float(lon2) - float(lon1))
            a = math.sin(dlat/2)**2 + math.cos(math.radians(float(lat1))) * math.cos(math.radians(float(lat2))) * math.sin(dlon/2)**2
            return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a)), 1)

        recs = []
        for farmer in farmers[:limit]:
            if not hubs:
                break
            best_hub = min(hubs, key=lambda h: haversine(
                farmer.get('latitude'), farmer.get('longitude'),
                h.get('latitude'), h.get('longitude')
            ))
            dist = haversine(farmer.get('latitude'), farmer.get('longitude'),
                             best_hub.get('latitude'), best_hub.get('longitude'))
            recs.append({
                'farmer_name': farmer.get('farmer_name', 'Farmer'),
                'farm_district': farmer.get('farm_district', 'Tamil Nadu'),
                'hub_name': best_hub.get('hub_name', 'Hub'),
                'hub_district': best_hub.get('district'),
                'distance_km': dist,
                'match_score': max(0, round(100 - (dist / 5), 1))
            })

        recs.sort(key=lambda x: x['distance_km'])
        return jsonify({'status': 'success', 'recommendations': recs[:limit]}), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@logistics_bp.route('/recommend-hub', methods=['GET'])
def recommend_hub_for_crop():
    """
    Suggest the best nearby collection hub for a farmer's crop listing.
    Used by the farmer product registration form.
    Query params: crop_id, district
    """
    crop_id = request.args.get('crop_id', type=int)
    district = request.args.get('district', default='Namakkal', type=str)

    try:
        # Find hubs in the farmer's district or nearby
        hubs = fetch_all("""
            SELECT hub_id, hub_name, district, latitude, longitude, capacity_kg, current_inventory_kg
            FROM hubs
            WHERE status = 'active'
              AND (LOWER(district) = LOWER(%s) OR district IS NOT NULL)
            ORDER BY LOWER(district) = LOWER(%s) DESC, hub_name ASC
            LIMIT 5;
        """, (district, district))

        if not hubs:
            return jsonify({'status': 'success', 'recommended_hub': None}), 200

        # Pick the hub with most available capacity in farmer's district first
        best = hubs[0]
        for h in hubs:
            available = float(h.get('capacity_kg') or 1000) - float(h.get('current_inventory_kg') or 0)
            best_avail = float(best.get('capacity_kg') or 1000) - float(best.get('current_inventory_kg') or 0)
            if available > best_avail:
                best = h

        return jsonify({
            'status': 'success',
            'recommended_hub': {
                'hub_id': best['hub_id'],
                'hub_name': best['hub_name'],
                'district': best['district'],
                'distance_km': 'Nearby'
            }
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@logistics_bp.route('/allocate-farmer', methods=['POST'])
@token_required
def allocate_farmer_produce_to_hub():
    """Assign or override a produce batch to a specific collection hub."""
    data = request.get_json() or {}
    produce_id = data.get('produce_id')
    hub_id = data.get('hub_id')

    if not produce_id or not hub_id:
        return jsonify({'error': 'Bad Request', 'message': 'produce_id and hub_id are required.'}), 400

    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE farmer_produce
                SET preferred_hub_id = %s
                WHERE produce_id = %s
                RETURNING produce_id, preferred_hub_id, status;
            """, (hub_id, produce_id))
            updated = cur.fetchone()

        if not updated:
            return jsonify({'error': 'Not Found', 'message': f'Produce #{produce_id} not found.'}), 404

        return jsonify({
            'status': 'success',
            'message': 'Produce batch successfully allocated to collection hub.',
            'allocation': dict(updated)
        }), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@logistics_bp.route('/optimize-route', methods=['POST'])
def optimize_delivery_route():
    """
    Run Google OR-Tools route optimization for deliveries assigned to a hub.
    Input JSON: { "hub_id": 4, "order_ids": [10, 11, 12], "vehicle_capacity_kg": 1200 }
    """
    data = request.get_json() or {}
    hub_id = data.get('hub_id')
    order_ids = data.get('order_ids', [])
    vehicle_capacity_kg = float(data.get('vehicle_capacity_kg', 1200.0))

    if not hub_id:
        # Default to Namakkal or first active hub
        first_hub = fetch_one("SELECT hub_id FROM hubs WHERE status = 'active' ORDER BY hub_id ASC LIMIT 1;")
        hub_id = first_hub['hub_id'] if first_hub else 1

    try:
        if not order_ids:
            # Auto-select pending orders assigned to this hub or within district
            orders = fetch_all("""
                SELECT order_id FROM orders
                WHERE (hub_id = %s OR hub_id IS NULL)
                  AND order_status IN ('placed', 'confirmed', 'at_hub', 'packed')
                ORDER BY order_date DESC
                LIMIT 8;
            """, (hub_id,))
            order_ids = [o['order_id'] for o in orders]

        # If still no orders, grab any active orders to demonstrate route optimization
        if not order_ids:
            all_orders = fetch_all("SELECT order_id FROM orders ORDER BY order_id DESC LIMIT 5;")
            order_ids = [o['order_id'] for o in all_orders]

        if not order_ids:
            return jsonify({
                'status': 'error',
                'message': 'No orders available to optimize routes for this hub.'
            }), 400

        result = LogisticsOptimizer.optimize_delivery_route(hub_id, order_ids, vehicle_capacity_kg)
        return jsonify({'status': 'success', 'route': result}), 200

    except Exception as e:
        return jsonify({'error': 'Optimization Error', 'message': str(e)}), 500


@logistics_bp.route('/routes', methods=['GET'])
def list_routes():
    """List all created routes with their stops."""
    try:
        routes = fetch_all("""
            SELECT r.*, h.hub_name, h.district AS hub_district
            FROM routes r
            JOIN hubs h ON r.hub_id = h.hub_id
            ORDER BY r.created_at DESC
            LIMIT 15;
        """)

        for r in routes:
            stops = fetch_all("""
                SELECT * FROM route_stops
                WHERE route_id = %s
                ORDER BY stop_sequence ASC;
            """, (r['route_id'],))
            r['stops'] = stops

        return jsonify({'status': 'success', 'routes': routes}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@logistics_bp.route('/map-data', methods=['GET'])
def get_map_data():
    """
    Consolidated geospatial layer data for Tamil Nadu interactive map:
    - Registered Farmers with crop summaries
    - Planned Collection Hubs with capacity & inventory
    - Active Delivery Stops
    - Optimized Route Polylines
    """
    district_filter = request.args.get('district')
    crop_filter = request.args.get('crop')

    try:
        # 1. Hubs
        hubs_query = """
            SELECT hub_id, hub_name, district, taluk, town, address,
                   latitude, longitude, capacity_kg, 
                   COALESCE(current_inventory_kg, 0) AS current_inventory_kg,
                   daily_processing_capacity_kg, workers, delivery_radius_km, is_demo
            FROM hubs
            WHERE status = 'active'
        """
        hubs_params = []
        if district_filter:
            hubs_query += " AND LOWER(district) = LOWER(%s)"
            hubs_params.append(district_filter)

        hubs = fetch_all(hubs_query, tuple(hubs_params) if hubs_params else None)

        # 2. Farmers with supply summaries
        farmers_query = """
            SELECT fp.farmer_id, fp.user_id, fp.farm_name, fp.village, fp.taluk,
                   fp.district, fp.latitude, fp.longitude, fp.farm_size, fp.crop_types,
                   u.name AS farmer_name,
                   COALESCE(SUM(p.available_quantity_kg), 0) AS total_available_kg,
                   COUNT(p.produce_id) AS active_batches_count
            FROM farmer_profiles fp
            JOIN users u ON fp.user_id = u.user_id
            LEFT JOIN farmer_produce p ON fp.farmer_id = p.farmer_id AND p.status IN ('available', 'ACTIVE')
            WHERE fp.latitude IS NOT NULL AND fp.longitude IS NOT NULL
        """
        farmers_params = []
        if district_filter:
            farmers_query += " AND LOWER(fp.district) = LOWER(%s)"
            farmers_params.append(district_filter)

        farmers_query += " GROUP BY fp.farmer_id, fp.user_id, fp.farm_name, fp.village, fp.taluk, fp.district, fp.latitude, fp.longitude, fp.farm_size, fp.crop_types, u.name"
        farmers = fetch_all(farmers_query, tuple(farmers_params) if farmers_params else None)

        # 3. Delivery stops (orders currently in fulfillment)
        stops_query = """
            SELECT o.order_id, o.order_status, o.delivery_address,
                   o.delivery_latitude, o.delivery_longitude, o.total_amount,
                   u.name AS customer_name,
                   h.hub_name, h.hub_id
            FROM orders o
            JOIN buyers b ON o.buyer_id = b.buyer_id
            JOIN users u ON b.user_id = u.user_id
            LEFT JOIN hubs h ON o.hub_id = h.hub_id
            WHERE o.delivery_latitude IS NOT NULL
              AND o.delivery_longitude IS NOT NULL
              AND o.order_status NOT IN ('delivered', 'cancelled')
            LIMIT 25;
        """
        delivery_stops = fetch_all(stops_query)

        # 4. Recent route for visualization
        recent_route = fetch_one("""
            SELECT r.*, h.hub_name, h.latitude AS hub_lat, h.longitude AS hub_lon
            FROM routes r
            JOIN hubs h ON r.hub_id = h.hub_id
            ORDER BY r.created_at DESC LIMIT 1;
        """)
        route_stops = []
        if recent_route:
            route_stops = fetch_all("""
                SELECT stop_sequence, customer_name, delivery_address, latitude, longitude, quantity_kg
                FROM route_stops
                WHERE route_id = %s
                ORDER BY stop_sequence ASC;
            """, (recent_route['route_id'],))

        return jsonify({
            'status': 'success',
            'hubs': hubs,
            'farmers': farmers,
            'deliveries': delivery_stops,
            'active_route': {
                'meta': recent_route,
                'stops': route_stops
            } if recent_route else None
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@logistics_bp.route('/locations', methods=['GET'])
def list_locations():
    """List Tamil Nadu districts and towns."""
    district = request.args.get('district')
    try:
        if district:
            locs = fetch_all("""
                SELECT * FROM locations
                WHERE LOWER(district) = LOWER(%s)
                ORDER BY village_or_town ASC;
            """, (district,))
        else:
            locs = fetch_all("""
                SELECT DISTINCT district FROM locations ORDER BY district ASC;
            """)
        return jsonify({'status': 'success', 'locations': locs}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500
