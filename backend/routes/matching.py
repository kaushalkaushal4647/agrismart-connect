"""
Dynamic Matching API routes for AgriSmart Connect.
Invokes the matching engine to pair buyer demand with verified farmer produce.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify

try:
    from services.matching_engine import MatchingEngine
    from database import fetch_one
except ImportError:
    from backend.services.matching_engine import MatchingEngine
    from backend.database import fetch_one

matching_bp = Blueprint('matching', __name__)


@matching_bp.route('/find', methods=['GET', 'POST'])
def find_matching_produce():
    """
    Execute matching engine algorithm on arbitrary demand parameters.
    Returns ranked farmer produce batches and multi-farmer quantity allocations.
    """
    if request.method == 'GET':
        data = request.args
    else:
        data = request.get_json() or {}

    crop_id = data.get('crop_id')
    required_quantity_kg = data.get('required_quantity_kg') or data.get('quantity')
    required_date = data.get('required_date') or datetime.now().date().isoformat()
    variety_id = data.get('variety_id')
    max_price_per_kg = data.get('max_price_per_kg') or data.get('max_price')
    buyer_lat = data.get('latitude') or data.get('lat')
    buyer_lon = data.get('longitude') or data.get('lon')
    max_distance_km = data.get('max_distance_km', 150.0)

    if not all([crop_id, required_quantity_kg]):
        return jsonify({
            'error': 'Bad Request',
            'message': 'crop_id and required_quantity_kg are required.'
        }), 400

    try:
        engine = MatchingEngine()
        result = engine.find_matches(
            crop_id=int(crop_id),
            required_quantity_kg=float(required_quantity_kg),
            required_date=required_date,
            variety_id=int(variety_id) if variety_id else None,
            max_price_per_kg=float(max_price_per_kg) if max_price_per_kg else None,
            buyer_lat=float(buyer_lat) if buyer_lat else None,
            buyer_lon=float(buyer_lon) if buyer_lon else None,
            max_distance_km=float(max_distance_km)
        )

        return jsonify({
            'status': 'success',
            'matching_result': result,
            'matches': result.get('allocated_batches', [])
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@matching_bp.route('/<int:demand_id>', methods=['GET'])
def match_demand_by_id(demand_id):
    """Run matching engine for an existing demand record in the database."""
    try:
        demand = fetch_one("SELECT * FROM demand_records WHERE demand_id = %s;", (demand_id,))
        if not demand:
            return jsonify({'error': 'Not Found', 'message': 'Demand record not found.'}), 404

        engine = MatchingEngine()
        result = engine.find_matches(
            crop_id=demand['crop_id'],
            required_quantity_kg=float(demand['required_quantity_kg']),
            required_date=demand['required_date'],
            variety_id=demand['variety_id'],
            buyer_lat=float(demand['latitude']) if demand['latitude'] else None,
            buyer_lon=float(demand['longitude']) if demand['longitude'] else None
        )

        return jsonify({
            'status': 'success',
            'demand_id': demand_id,
            'matching_result': result
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500
