"""
Crops and Varieties catalog routes.
Provides catalog access for farmers listing produce and buyers creating demand.
"""

from flask import Blueprint, request, jsonify
try:
    from database import fetch_all, fetch_one, execute_query, get_db_cursor
    from auth_middleware import token_required, roles_required
except ImportError:
    from backend.database import fetch_all, fetch_one, execute_query, get_db_cursor
    from backend.auth_middleware import token_required, roles_required

crops_bp = Blueprint('crops', __name__)


@crops_bp.route('', methods=['GET'])
def get_crops():
    """Retrieve all active crops catalog."""
    try:
        crops = fetch_all("""
            SELECT c.crop_id, c.crop_name, c.category, c.description, c.is_active,
                   COUNT(v.variety_id) AS varieties_count
            FROM crops c
            LEFT JOIN varieties v ON c.crop_id = v.crop_id AND v.is_active = TRUE
            WHERE c.is_active = TRUE
            GROUP BY c.crop_id
            ORDER BY c.crop_name ASC;
        """)
        return jsonify({'status': 'success', 'crops': crops}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@crops_bp.route('/<int:crop_id>/varieties', methods=['GET'])
def get_crop_varieties(crop_id):
    """Retrieve all varieties for a specific crop."""
    try:
        varieties = fetch_all("""
            SELECT variety_id, crop_id, variety_name, description, is_active
            FROM varieties
            WHERE crop_id = %s AND is_active = TRUE
            ORDER BY variety_name ASC;
        """, (crop_id,))
        return jsonify({'status': 'success', 'crop_id': crop_id, 'varieties': varieties}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@crops_bp.route('', methods=['POST'])
@token_required
@roles_required('admin')
def add_crop():
    """Add a new crop to the master catalog (Admin only)."""
    data = request.get_json() or {}
    crop_name = data.get('crop_name', '').strip()
    category = data.get('category', '').strip()
    description = data.get('description', '').strip()

    if not crop_name or not category:
        return jsonify({'error': 'Bad Request', 'message': 'crop_name and category are required.'}), 400

    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO crops (crop_name, category, description)
                VALUES (%s, %s, %s)
                RETURNING crop_id, crop_name, category, description, is_active, created_at;
            """, (crop_name, category, description))
            crop = dict(cur.fetchone())

        return jsonify({'status': 'success', 'message': 'Crop added successfully.', 'crop': crop}), 201
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@crops_bp.route('/<int:crop_id>/varieties', methods=['POST'])
@token_required
@roles_required('admin')
def add_variety(crop_id):
    """Add a new variety to an existing crop (Admin only)."""
    data = request.get_json() or {}
    variety_name = data.get('variety_name', '').strip()
    description = data.get('description', '').strip()

    if not variety_name:
        return jsonify({'error': 'Bad Request', 'message': 'variety_name is required.'}), 400

    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO varieties (crop_id, variety_name, description)
                VALUES (%s, %s, %s)
                RETURNING variety_id, crop_id, variety_name, description, is_active;
            """, (crop_id, variety_name, description))
            variety = dict(cur.fetchone())

        return jsonify({'status': 'success', 'message': 'Variety added successfully.', 'variety': variety}), 201
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500
