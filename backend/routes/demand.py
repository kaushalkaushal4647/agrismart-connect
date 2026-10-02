"""
Demand records management routes for AgriSmart Connect.
Enables consumers, restaurants, and retailers to post immediate or recurring requirements.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from auth_middleware import token_required, roles_required
    from services.matching_engine import MatchingEngine
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.auth_middleware import token_required, roles_required
    from backend.services.matching_engine import MatchingEngine

demand_bp = Blueprint('demand', __name__)


def _get_buyer_id_for_user(user_id: int):
    """Retrieve buyer_id associated with the authenticated user."""
    b = fetch_one("SELECT buyer_id, buyer_type, latitude, longitude FROM buyers WHERE user_id = %s;", (user_id,))
    return b


@demand_bp.route('', methods=['POST'])
@token_required
@roles_required('consumer', 'restaurant', 'retailer', 'admin')
def create_demand():
    """
    Submit a new agricultural demand requirement (consumer order or B2B recurring requirement).
    Optionally triggers dynamic matching immediately.
    """
    user_id = request.current_user['user_id']
    buyer = _get_buyer_id_for_user(user_id)
    if not buyer:
        return jsonify({'error': 'Not Found', 'message': 'Buyer profile not found for this user.'}), 404

    buyer_id = buyer['buyer_id']
    buyer_type = buyer['buyer_type']
    data = request.get_json() or {}

    crop_id = data.get('crop_id')
    variety_id = data.get('variety_id')
    required_quantity_kg = data.get('required_quantity_kg')
    required_date = data.get('required_date')
    source = data.get('source', 'portal')
    auto_match = data.get('auto_match', True)

    lat = data.get('latitude', buyer.get('latitude'))
    lon = data.get('longitude', buyer.get('longitude'))

    if not all([crop_id, required_quantity_kg, required_date]):
        return jsonify({
            'error': 'Bad Request',
            'message': 'crop_id, required_quantity_kg, and required_date are required.'
        }), 400

    try:
        req_qty = float(required_quantity_kg)
        if req_qty <= 0:
            return jsonify({'error': 'Bad Request', 'message': 'Quantity must be greater than zero.'}), 400

        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO demand_records (
                    buyer_id, crop_id, variety_id, required_quantity_kg,
                    required_date, latitude, longitude, buyer_type, source, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'open')
                RETURNING demand_id, buyer_id, crop_id, variety_id,
                          required_quantity_kg, required_date, buyer_type, source, status, created_at;
            """, (buyer_id, crop_id, variety_id, req_qty, required_date, lat, lon, buyer_type, source))
            demand_record = dict(cur.fetchone())

        # Execute instant matching if requested
        matching_results = None
        if auto_match:
            engine = MatchingEngine()
            matching_results = engine.find_matches(
                crop_id=crop_id,
                required_quantity_kg=req_qty,
                required_date=required_date,
                variety_id=variety_id,
                buyer_lat=float(lat) if lat else None,
                buyer_lon=float(lon) if lon else None
            )

        return jsonify({
            'status': 'success',
            'message': 'Demand requirement created successfully.',
            'demand': demand_record,
            'match_preview': matching_results
        }), 201

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@demand_bp.route('', methods=['GET'])
@token_required
def list_demands():
    """List demand records. Buyers see their own; Admins and Hub Operators see all."""
    user = request.current_user
    user_id = user['user_id']
    role = user['role']

    try:
        if role in ('admin', 'hub_operator'):
            demands = fetch_all("""
                SELECT d.*, c.crop_name, v.variety_name,
                       b.business_name, u.name AS buyer_name, u.phone AS buyer_phone
                FROM demand_records d
                JOIN crops c ON d.crop_id = c.crop_id
                LEFT JOIN varieties v ON d.variety_id = v.variety_id
                JOIN buyers b ON d.buyer_id = b.buyer_id
                JOIN users u ON b.user_id = u.user_id
                ORDER BY d.created_at DESC;
            """)
        else:
            buyer = _get_buyer_id_for_user(user_id)
            if not buyer:
                return jsonify({'status': 'success', 'demands': []}), 200

            demands = fetch_all("""
                SELECT d.*, c.crop_name, v.variety_name
                FROM demand_records d
                JOIN crops c ON d.crop_id = c.crop_id
                LEFT JOIN varieties v ON d.variety_id = v.variety_id
                WHERE d.buyer_id = %s
                ORDER BY d.created_at DESC;
            """, (buyer['buyer_id'],))

        return jsonify({'status': 'success', 'demands': demands}), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@demand_bp.route('/<int:demand_id>', methods=['GET'])
@token_required
def get_demand(demand_id):
    """Retrieve details and live matching recommendations for a specific demand record."""
    try:
        demand = fetch_one("""
            SELECT d.*, c.crop_name, v.variety_name,
                   b.business_name, b.address, b.district,
                   u.name AS buyer_name, u.phone AS buyer_phone
            FROM demand_records d
            JOIN crops c ON d.crop_id = c.crop_id
            LEFT JOIN varieties v ON d.variety_id = v.variety_id
            JOIN buyers b ON d.buyer_id = b.buyer_id
            JOIN users u ON b.user_id = u.user_id
            WHERE d.demand_id = %s;
        """, (demand_id,))

        if not demand:
            return jsonify({'error': 'Not Found', 'message': 'Demand record not found.'}), 404

        # Run live matching for this demand
        engine = MatchingEngine()
        match_plan = engine.find_matches(
            crop_id=demand['crop_id'],
            required_quantity_kg=float(demand['required_quantity_kg']),
            required_date=demand['required_date'],
            variety_id=demand['variety_id'],
            buyer_lat=float(demand['latitude']) if demand['latitude'] else None,
            buyer_lon=float(demand['longitude']) if demand['longitude'] else None
        )

        return jsonify({
            'status': 'success',
            'demand': demand,
            'match_plan': match_plan
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500
