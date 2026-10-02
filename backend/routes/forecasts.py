"""
Demand prediction and agricultural forecasting routes for AgriSmart Connect.
"""

from flask import Blueprint, request, jsonify

try:
    from database import fetch_all
    from services.demand_engine import DemandPredictionEngine
except ImportError:
    from backend.database import fetch_all
    from backend.services.demand_engine import DemandPredictionEngine

forecasts_bp = Blueprint('forecasts', __name__)


@forecasts_bp.route('', methods=['GET'])
def get_forecasts():
    """Retrieve saved demand predictions and crop projections."""
    crop_id = request.args.get('crop_id', type=int)
    location = request.args.get('location')

    query = """
        SELECT df.*, c.crop_name, c.category
        FROM demand_forecasts df
        JOIN crops c ON df.crop_id = c.crop_id
    """
    params = []
    if crop_id:
        query += " WHERE df.crop_id = %s"
        params.append(crop_id)
    if location:
        query += (" AND" if crop_id else " WHERE") + " df.location ILIKE %s"
        params.append(f"%{location}%")

    query += " ORDER BY df.created_at DESC LIMIT 20;"

    try:
        results = fetch_all(query, tuple(params) if params else None)
        return jsonify({'status': 'success', 'forecasts': results}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@forecasts_bp.route('/predict', methods=['POST'])
def generate_forecast():
    """Calculate moving average demand forecast for a specific crop."""
    data = request.get_json() or {}
    crop_id = data.get('crop_id', 1)
    location = data.get('location', 'Salem')

    try:
        prediction = DemandPredictionEngine.calculate_crop_forecast(int(crop_id), location)
        return jsonify({'status': 'success', 'prediction': prediction}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500
