"""
Farmer management and produce listing routes.
Allows farmers to manage profiles, post produce batches, track reservations,
and view earnings and payouts.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from auth_middleware import token_required, roles_required
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.auth_middleware import token_required, roles_required

farmers_bp = Blueprint('farmers', __name__)


def _get_farmer_id_for_user(user_id: int):
    """Helper to get farmer_id from current authenticated user."""
    profile = fetch_one("SELECT farmer_id FROM farmer_profiles WHERE user_id = %s;", (user_id,))
    return profile['farmer_id'] if profile else None


@farmers_bp.route('/profile', methods=['GET'])
@token_required
@roles_required('farmer', 'admin')
def get_farmer_profile():
    """Retrieve full farmer profile along with operational summary statistics."""
    user_id = request.current_user['user_id']
    try:
        farmer = fetch_one("""
            SELECT fp.*, u.name, u.phone, u.email, u.created_at AS user_registered_at
            FROM farmer_profiles fp
            JOIN users u ON fp.user_id = u.user_id
            WHERE fp.user_id = %s;
        """, (user_id,))

        if not farmer:
            return jsonify({'error': 'Not Found', 'message': 'Farmer profile not found.'}), 404

        farmer_id = farmer['farmer_id']

        # Produce metrics
        metrics = fetch_one("""
            SELECT 
                COUNT(produce_id) AS total_listings,
                COALESCE(SUM(available_quantity_kg), 0) AS total_available_kg,
                COALESCE(SUM(reserved_quantity_kg), 0) AS total_reserved_kg,
                COALESCE(SUM(sold_quantity_kg), 0) AS total_sold_kg
            FROM farmer_produce
            WHERE farmer_id = %s AND status NOT IN ('cancelled', 'expired');
        """, (farmer_id,))

        # Financial metrics from farmer_payouts
        finances = fetch_one("""
            SELECT 
                COALESCE(SUM(CASE WHEN payout_status = 'paid' THEN net_amount ELSE 0 END), 0) AS paid_earnings,
                COALESCE(SUM(CASE WHEN payout_status IN ('pending', 'processing') THEN net_amount ELSE 0 END), 0) AS pending_earnings
            FROM farmer_payouts
            WHERE farmer_id = %s;
        """, (farmer_id,))

        return jsonify({
            'status': 'success',
            'profile': farmer,
            'summary': {**metrics, **finances}
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/profile', methods=['PUT'])
@token_required
@roles_required('farmer')
def update_farmer_profile():
    """Update farmer farm details and geographic coordinates."""
    user_id = request.current_user['user_id']
    data = request.get_json() or {}

    farm_name = data.get('farm_name')
    village = data.get('village')
    district = data.get('district')
    state = data.get('state')
    farm_size = data.get('farm_size')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    address = data.get('address')

    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE farmer_profiles
                SET farm_name = COALESCE(%s, farm_name),
                    village = COALESCE(%s, village),
                    district = COALESCE(%s, district),
                    state = COALESCE(%s, state),
                    farm_size = COALESCE(%s, farm_size),
                    latitude = COALESCE(%s, latitude),
                    longitude = COALESCE(%s, longitude),
                    address = COALESCE(%s, address)
                WHERE user_id = %s
                RETURNING *;
            """, (farm_name, village, district, state, farm_size, latitude, longitude, address, user_id))
            updated = dict(cur.fetchone())

        return jsonify({'status': 'success', 'message': 'Profile updated successfully.', 'profile': updated}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/produce', methods=['GET'])
@token_required
@roles_required('farmer', 'admin')
def get_farmer_produce():
    """Retrieve all produce batches listed by the authenticated farmer."""
    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)
    if not farmer_id:
        return jsonify({'error': 'Not Found', 'message': 'Farmer profile not found.'}), 404

    try:
        listings = fetch_all("""
            SELECT fp.produce_id, fp.farmer_id, fp.crop_id, fp.variety_id,
                   c.crop_name, c.category AS crop_category,
                   v.variety_name,
                   fp.expected_quantity_kg, fp.available_quantity_kg,
                   fp.reserved_quantity_kg, fp.sold_quantity_kg,
                   fp.minimum_price_per_kg, fp.harvest_date,
                   fp.quality_grade, fp.status,
                   fp.latitude, fp.longitude,
                   h.hub_id, h.hub_name, h.district AS hub_district,
                   fp.created_at, fp.updated_at
            FROM farmer_produce fp
            JOIN crops c ON fp.crop_id = c.crop_id
            LEFT JOIN varieties v ON fp.variety_id = v.variety_id
            LEFT JOIN hubs h ON fp.preferred_hub_id = h.hub_id
            WHERE fp.farmer_id = %s
            ORDER BY fp.harvest_date ASC, fp.created_at DESC;
        """, (farmer_id,))

        return jsonify({'status': 'success', 'produce': listings}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/produce', methods=['POST'])
@token_required
@roles_required('farmer')
def add_farmer_produce():
    """
    Post a new crop/produce batch for demand-matching.
    Enforces minimum required quantity, price floor, and future/current harvest date.
    """
    user_id = request.current_user['user_id']
    farmer = fetch_one("SELECT * FROM farmer_profiles WHERE user_id = %s;", (user_id,))
    if not farmer:
        return jsonify({'error': 'Not Found', 'message': 'Farmer profile not found.'}), 404

    farmer_id = farmer['farmer_id']
    data = request.get_json() or {}

    crop_id = data.get('crop_id')
    variety_id = data.get('variety_id')
    expected_quantity_kg = data.get('expected_quantity_kg')
    available_quantity_kg = data.get('available_quantity_kg', expected_quantity_kg)
    minimum_price_per_kg = data.get('minimum_price_per_kg')
    harvest_date = data.get('harvest_date')
    quality_grade = data.get('quality_grade', 'Grade A')
    preferred_hub_id = data.get('preferred_hub_id')

    # Fallback to farmer's registered coordinates if not specified per listing
    latitude = data.get('latitude', farmer.get('latitude'))
    longitude = data.get('longitude', farmer.get('longitude'))

    # Validation
    if not all([crop_id, expected_quantity_kg, minimum_price_per_kg, harvest_date]):
        return jsonify({
            'error': 'Bad Request',
            'message': 'crop_id, expected_quantity_kg, minimum_price_per_kg, and harvest_date are required.'
        }), 400

    try:
        expected_qty = float(expected_quantity_kg)
        avail_qty = float(available_quantity_kg)
        price_per_kg = float(minimum_price_per_kg)

        if expected_qty <= 0 or avail_qty <= 0 or price_per_kg <= 0:
            return jsonify({'error': 'Bad Request', 'message': 'Quantities and price must be greater than zero.'}), 400

        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO farmer_produce (
                    farmer_id, crop_id, variety_id,
                    expected_quantity_kg, available_quantity_kg, reserved_quantity_kg, sold_quantity_kg,
                    minimum_price_per_kg, harvest_date, quality_grade,
                    latitude, longitude, preferred_hub_id, status
                )
                VALUES (%s, %s, %s, %s, %s, 0.00, 0.00, %s, %s, %s, %s, %s, %s, 'available')
                RETURNING produce_id, farmer_id, crop_id, variety_id,
                          expected_quantity_kg, available_quantity_kg, minimum_price_per_kg,
                          harvest_date, quality_grade, status, created_at;
            """, (
                farmer_id, crop_id, variety_id,
                expected_qty, avail_qty,
                price_per_kg, harvest_date, quality_grade,
                latitude, longitude, preferred_hub_id
            ))
            new_produce = dict(cur.fetchone())

        return jsonify({
            'status': 'success',
            'message': 'Produce batch successfully listed for matching!',
            'produce': new_produce
        }), 201

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/produce/<int:produce_id>', methods=['PUT'])
@token_required
@roles_required('farmer')
def update_farmer_produce(produce_id):
    """Edit produce batch details before full reservation."""
    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)
    data = request.get_json() or {}

    try:
        # Check ownership and status
        produce = fetch_one("SELECT * FROM farmer_produce WHERE produce_id = %s AND farmer_id = %s;", (produce_id, farmer_id))
        if not produce:
            return jsonify({'error': 'Not Found', 'message': 'Produce not found or not owned by you.'}), 404

        if produce['status'] in ('sold', 'cancelled'):
            return jsonify({'error': 'Bad Request', 'message': f"Cannot edit produce in '{produce['status']}' status."}), 400

        minimum_price_per_kg = data.get('minimum_price_per_kg', produce['minimum_price_per_kg'])
        available_quantity_kg = data.get('available_quantity_kg', produce['available_quantity_kg'])
        harvest_date = data.get('harvest_date', produce['harvest_date'])
        quality_grade = data.get('quality_grade', produce['quality_grade'])
        preferred_hub_id = data.get('preferred_hub_id', produce['preferred_hub_id'])

        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE farmer_produce
                SET minimum_price_per_kg = %s,
                    available_quantity_kg = %s,
                    harvest_date = %s,
                    quality_grade = %s,
                    preferred_hub_id = %s
                WHERE produce_id = %s
                RETURNING *;
            """, (minimum_price_per_kg, available_quantity_kg, harvest_date, quality_grade, preferred_hub_id, produce_id))
            updated = dict(cur.fetchone())

        return jsonify({'status': 'success', 'message': 'Produce updated successfully.', 'produce': updated}), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/produce/<int:produce_id>', methods=['DELETE'])
@token_required
@roles_required('farmer')
def cancel_farmer_produce(produce_id):
    """Cancel a produce listing if no orders have reserved it."""
    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)

    try:
        produce = fetch_one("SELECT * FROM farmer_produce WHERE produce_id = %s AND farmer_id = %s;", (produce_id, farmer_id))
        if not produce:
            return jsonify({'error': 'Not Found', 'message': 'Produce not found.'}), 404

        if produce['reserved_quantity_kg'] > 0 or produce['sold_quantity_kg'] > 0:
            return jsonify({
                'error': 'Conflict',
                'message': 'Cannot cancel produce that has active buyer reservations or fulfilled sales.'
            }), 409

        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE farmer_produce 
                SET status = 'cancelled', available_quantity_kg = 0 
                WHERE produce_id = %s
                RETURNING produce_id, status;
            """, (produce_id,))
            res = dict(cur.fetchone())

        return jsonify({'status': 'success', 'message': 'Produce listing cancelled.', 'produce': res}), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/payouts', methods=['GET'])
@token_required
@roles_required('farmer')
def get_farmer_payouts():
    """Retrieve history of earnings and payouts for this farmer."""
    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)

    try:
        payouts = fetch_all("""
            SELECT p.payout_id, p.order_id, p.gross_amount, p.platform_fee,
                   p.other_deductions, p.net_amount, p.payout_status,
                   p.payout_date, p.created_at,
                   o.order_date, o.order_status
            FROM farmer_payouts p
            JOIN orders o ON p.order_id = o.order_id
            WHERE p.farmer_id = %s
            ORDER BY p.created_at DESC;
        """, (farmer_id,))

        return jsonify({'status': 'success', 'payouts': payouts}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# =============================================================================
# 4. ENHANCED PRODUCT MANAGEMENT & "MY PRODUCTS"
# =============================================================================

@farmers_bp.route('/products', methods=['GET'])
@token_required
@roles_required('farmer', 'admin')
def list_farmer_products():
    """Retrieve all products created by the authenticated farmer with images & status."""
    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)
    if not farmer_id:
        return jsonify({'error': 'Not Found', 'message': 'Farmer profile not found.'}), 404

    try:
        products = fetch_all("""
            SELECT fp.*,
                   c.crop_name, c.category AS crop_category,
                   v.variety_name,
                   h.hub_name, h.district AS hub_district,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'image_id', pi.image_id,
                               'image_url', pi.image_url,
                               'is_primary', pi.is_primary,
                               'display_order', pi.display_order
                           ) ORDER BY pi.display_order ASC, pi.image_id ASC
                       ) FILTER (WHERE pi.image_id IS NOT NULL),
                       '[]'::json
                   ) AS images
            FROM farmer_produce fp
            JOIN crops c ON fp.crop_id = c.crop_id
            LEFT JOIN varieties v ON fp.variety_id = v.variety_id
            LEFT JOIN hubs h ON fp.preferred_hub_id = h.hub_id
            LEFT JOIN product_images pi ON fp.produce_id = pi.produce_id
            WHERE fp.farmer_id = %s
            GROUP BY fp.produce_id, c.crop_name, c.category, v.variety_name, h.hub_name, h.district
            ORDER BY fp.created_at DESC;
        """, (farmer_id,))

        # Backward compatibility aliases
        for p in products:
            p['id'] = p['produce_id']
            p['price_per_kg'] = float(p.get('minimum_price_per_kg') or 0.0)

        return jsonify({'status': 'success', 'products': products}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/products', methods=['POST'])
@token_required
@roles_required('farmer')
def create_farmer_product():
    """
    Register a new agricultural product with all detailed fields:
    product_name, category, variety, description, quantity, unit, price, MOQ,
    harvest_date, expected_availability_date, preferred_hub, organic status, grade, status.
    """
    user_id = request.current_user['user_id']
    farmer = fetch_one("SELECT * FROM farmer_profiles WHERE user_id = %s;", (user_id,))
    if not farmer:
        return jsonify({'error': 'Not Found', 'message': 'Farmer profile not found.'}), 404

    farmer_id = farmer['farmer_id']
    data = request.get_json() or {}

    product_name = data.get('product_name', '').strip()
    crop_id = data.get('crop_id')
    variety_id = data.get('variety_id')
    category = data.get('category', 'Vegetables').strip()
    description = data.get('description', '').strip()
    expected_qty = data.get('expected_quantity_kg')
    available_qty = data.get('available_quantity_kg', expected_qty)
    unit = data.get('unit', 'kg').strip()
    price_per_unit = data.get('minimum_price_per_kg') or data.get('price_per_unit')
    min_order_qty = data.get('min_order_quantity_kg', 1.0)
    harvest_date = data.get('harvest_date')
    expected_avail_date = data.get('expected_availability_date', harvest_date)
    preferred_hub_id = data.get('preferred_hub_id') or farmer.get('current_hub_id')
    organic_status = data.get('organic_status', 'conventional').strip()
    quality_grade = data.get('quality_grade', 'Grade A')
    status = data.get('status', 'ACTIVE').strip()

    if not crop_id or not expected_qty or not price_per_unit or not harvest_date:
        return jsonify({
            'error': 'Bad Request',
            'message': 'crop_id, expected_quantity_kg, minimum_price_per_kg, and harvest_date are required.'
        }), 400

    try:
        exp_qty = float(expected_qty)
        avail_qty = float(available_qty)
        price = float(price_per_unit)
        moq = float(min_order_qty)

        if exp_qty <= 0 or avail_qty <= 0 or price <= 0 or moq <= 0:
            return jsonify({'error': 'Bad Request', 'message': 'Quantities and prices must be greater than zero.'}), 400

        # If product_name not supplied, generate from crop & variety
        if not product_name:
            crop_rec = fetch_one("SELECT crop_name FROM crops WHERE crop_id = %s;", (crop_id,))
            product_name = crop_rec['crop_name'] if crop_rec else 'Fresh Produce'

        lat = data.get('latitude', farmer.get('latitude'))
        lon = data.get('longitude', farmer.get('longitude'))

        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO farmer_produce (
                    farmer_id, crop_id, variety_id, product_name, category, unit, min_order_quantity_kg,
                    expected_quantity_kg, available_quantity_kg, reserved_quantity_kg, sold_quantity_kg,
                    minimum_price_per_kg, harvest_date, expected_availability_date, quality_grade,
                    latitude, longitude, preferred_hub_id, organic_status, description, moderation_status,
                    status, is_demo
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, 0.00, 0.00,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, 'APPROVED',
                    %s, FALSE
                )
                RETURNING produce_id, farmer_id, product_name, available_quantity_kg, minimum_price_per_kg, status, created_at;
            """, (
                farmer_id, crop_id, variety_id, product_name, category, unit, moq,
                exp_qty, avail_qty,
                price, harvest_date, expected_avail_date, quality_grade,
                lat, lon, preferred_hub_id, organic_status, description,
                status
            ))
            new_prod = dict(cur.fetchone())

        return jsonify({
            'status': 'success',
            'message': 'Product registered successfully!',
            'product': new_prod
        }), 201

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/products/<int:produce_id>', methods=['GET'])
@token_required
@roles_required('farmer', 'admin')
def get_single_farmer_product(produce_id):
    """Retrieve details for a single farmer product, verifying ownership."""
    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)

    try:
        product = fetch_one("""
            SELECT fp.*, c.crop_name, c.category AS crop_category, v.variety_name, h.hub_name
            FROM farmer_produce fp
            JOIN crops c ON fp.crop_id = c.crop_id
            LEFT JOIN varieties v ON fp.variety_id = v.variety_id
            LEFT JOIN hubs h ON fp.preferred_hub_id = h.hub_id
            WHERE fp.produce_id = %s AND (fp.farmer_id = %s OR %s = 'admin');
        """, (produce_id, farmer_id, request.current_user['role']))

        if not product:
            return jsonify({'error': 'Not Found', 'message': 'Product not found or unauthorized.'}), 404

        images = fetch_all("""
            SELECT image_id, image_url, is_primary, display_order
            FROM product_images
            WHERE produce_id = %s
            ORDER BY display_order ASC, image_id ASC;
        """, (produce_id,))
        product['images'] = images

        return jsonify({'status': 'success', 'product': product}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/products/<int:produce_id>', methods=['PUT'])
@token_required
@roles_required('farmer', 'admin')
def update_farmer_product_details(produce_id):
    """Update product information, pricing, stock, status (ACTIVE, PAUSED, DRAFT, etc.)."""
    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)
    role = request.current_user['role']
    data = request.get_json() or {}

    try:
        prod = fetch_one("SELECT * FROM farmer_produce WHERE produce_id = %s;", (produce_id,))
        if not prod:
            return jsonify({'error': 'Not Found', 'message': 'Product not found.'}), 404

        # Enforce authorization: only owning farmer or admin can edit
        if role != 'admin' and prod['farmer_id'] != farmer_id:
            return jsonify({'error': 'Forbidden', 'message': 'You can only edit your own products.'}), 403

        product_name = data.get('product_name', prod['product_name'])
        min_price = data.get('minimum_price_per_kg', prod['minimum_price_per_kg'])
        avail_qty = data.get('available_quantity_kg', prod['available_quantity_kg'])
        harvest_date = data.get('harvest_date', prod['harvest_date'])
        quality_grade = data.get('quality_grade', prod['quality_grade'])
        preferred_hub_id = data.get('preferred_hub_id', prod['preferred_hub_id'])
        status = data.get('status', prod['status'])
        description = data.get('description', prod.get('description'))
        min_order_qty = data.get('min_order_quantity_kg', prod.get('min_order_quantity_kg', 1.0))
        organic_status = data.get('organic_status', prod.get('organic_status', 'conventional'))

        # If quantity reduced to 0, reflect SOLD_OUT status
        if float(avail_qty) <= 0 and status in ('available', 'ACTIVE'):
            status = 'SOLD_OUT'

        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE farmer_produce
                SET product_name = %s,
                    minimum_price_per_kg = %s,
                    available_quantity_kg = %s,
                    harvest_date = %s,
                    quality_grade = %s,
                    preferred_hub_id = %s,
                    status = %s,
                    description = %s,
                    min_order_quantity_kg = %s,
                    organic_status = %s
                WHERE produce_id = %s
                RETURNING *;
            """, (
                product_name, min_price, avail_qty, harvest_date, quality_grade,
                preferred_hub_id, status, description, min_order_qty, organic_status,
                produce_id
            ))
            updated = dict(cur.fetchone())

        return jsonify({'status': 'success', 'message': 'Product updated successfully.', 'product': updated}), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/products/<int:produce_id>', methods=['DELETE'])
@token_required
@roles_required('farmer', 'admin')
def delete_farmer_product(produce_id):
    """Archive or cancel farmer product listing."""
    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)
    role = request.current_user['role']

    try:
        prod = fetch_one("SELECT * FROM farmer_produce WHERE produce_id = %s;", (produce_id,))
        if not prod:
            return jsonify({'error': 'Not Found', 'message': 'Product not found.'}), 404

        if role != 'admin' and prod['farmer_id'] != farmer_id:
            return jsonify({'error': 'Forbidden', 'message': 'You can only manage your own products.'}), 403

        if prod['reserved_quantity_kg'] > 0 or prod['sold_quantity_kg'] > 0:
            return jsonify({
                'error': 'Conflict',
                'message': 'Cannot delete product that has active buyer orders or completed reservations.'
            }), 409

        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE farmer_produce
                SET status = 'cancelled', available_quantity_kg = 0
                WHERE produce_id = %s
                RETURNING produce_id, status;
            """, (produce_id,))
            res = dict(cur.fetchone())

        return jsonify({'status': 'success', 'message': 'Product successfully archived/cancelled.', 'product': res}), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# =============================================================================
# 4B. PRODUCT STATUS TOGGLE (ACTIVE / PAUSED / DRAFT / SOLD_OUT)
# =============================================================================

@farmers_bp.route('/products/<int:produce_id>/status', methods=['PATCH'])
@token_required
@roles_required('farmer', 'admin')
def toggle_product_status(produce_id):
    """
    Change the lifecycle status of a farmer product.
    Allowed transitions: DRAFT → ACTIVE, ACTIVE → PAUSED, PAUSED → ACTIVE.
    Admin can force any status.
    """
    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)
    role = request.current_user['role']
    data = request.get_json() or {}

    new_status = data.get('status', '').strip().upper()
    allowed_statuses = {'ACTIVE', 'PAUSED', 'DRAFT', 'SOLD_OUT'}

    if new_status not in allowed_statuses:
        return jsonify({
            'error': 'Bad Request',
            'message': f'Invalid status. Allowed: {", ".join(allowed_statuses)}'
        }), 400

    try:
        prod = fetch_one("SELECT * FROM farmer_produce WHERE produce_id = %s;", (produce_id,))
        if not prod:
            return jsonify({'error': 'Not Found', 'message': 'Product not found.'}), 404

        if role != 'admin' and prod['farmer_id'] != farmer_id:
            return jsonify({'error': 'Forbidden', 'message': 'You can only manage your own products.'}), 403

        with get_db_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE farmer_produce SET status = %s, updated_at = NOW() WHERE produce_id = %s RETURNING produce_id, status;",
                (new_status, produce_id)
            )
            updated = dict(cur.fetchone())

        return jsonify({
            'status': 'success',
            'message': f'Product status updated to {new_status}.',
            'product': updated
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# =============================================================================
# 5. PRODUCT IMAGE MANAGEMENT (UPLOAD, CROPPING, PRIMARY SELECTOR, DELETE)
# =============================================================================

@farmers_bp.route('/products/<int:produce_id>/images', methods=['POST'])
@token_required
@roles_required('farmer', 'admin')
def upload_product_image(produce_id):
    """
    Upload and optimize a product image.
    Supports Base64 canvas data or multipart/form-data upload.
    Generates high-res image and thumbnail via PIL, enforces size < 5MB.
    """
    import base64
    import io
    from pathlib import Path
    from PIL import Image

    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)
    role = request.current_user['role']

    try:
        prod = fetch_one("SELECT * FROM farmer_produce WHERE produce_id = %s;", (produce_id,))
        if not prod:
            return jsonify({'error': 'Not Found', 'message': 'Product not found.'}), 404

        if role != 'admin' and prod['farmer_id'] != farmer_id:
            return jsonify({'error': 'Forbidden', 'message': 'You can only upload images to your own products.'}), 403

        image_bytes = None
        is_primary = False

        if request.is_json:
            data = request.get_json() or {}
            base64_str = data.get('image', '')
            is_primary = bool(data.get('is_primary', False))

            if not base64_str:
                return jsonify({'error': 'Bad Request', 'message': 'Image data is required.'}), 400

            # Strip data URL prefix if present
            if 'base64,' in base64_str:
                base64_str = base64_str.split('base64,')[1]

            image_bytes = base64.b64decode(base64_str)

        elif 'image' in request.files:
            file = request.files['image']
            image_bytes = file.read()
            is_primary = request.form.get('is_primary', 'false').lower() == 'true'

        if not image_bytes:
            return jsonify({'error': 'Bad Request', 'message': 'No image file provided.'}), 400

        # Validate file size (< 5MB)
        if len(image_bytes) > 5 * 1024 * 1024:
            return jsonify({'error': 'Bad Request', 'message': 'Image exceeds 5MB size limit.'}), 400

        # Open and validate image with PIL
        try:
            pil_img = Image.open(io.BytesIO(image_bytes))
            pil_img.verify()
            # Reopen for processing
            pil_img = Image.open(io.BytesIO(image_bytes))
            if pil_img.format not in ('JPEG', 'PNG', 'WEBP'):
                return jsonify({'error': 'Bad Request', 'message': 'Only JPEG, PNG, and WebP images are allowed.'}), 400
        except Exception as img_err:
            return jsonify({'error': 'Bad Request', 'message': f'Invalid image format: {img_err}'}), 400

        # Prepare storage directory
        frontend_dir = Path(__file__).resolve().parent.parent.parent / 'frontend'
        upload_dir = frontend_dir / 'uploads' / 'products'
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique image id
        with get_db_cursor(commit=True) as cur:
            # If this is set as primary or is the first image, handle is_primary
            cur.execute("SELECT COUNT(*) AS img_count FROM product_images WHERE produce_id = %s;", (produce_id,))
            img_count = cur.fetchone()['img_count']
            if img_count == 0:
                is_primary = True

            if is_primary:
                cur.execute("UPDATE product_images SET is_primary = FALSE WHERE produce_id = %s;", (produce_id,))

            timestamp_str = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"prod_{produce_id}_{timestamp_str}.jpg"
            thumb_filename = f"prod_{produce_id}_{timestamp_str}_thumb.jpg"
            filepath = upload_dir / filename
            thumb_path = upload_dir / thumb_filename

            # Resize & optimize
            # Convert RGBA to RGB for saving as JPEG
            if pil_img.mode in ('RGBA', 'P'):
                pil_img = pil_img.convert('RGB')

            # Standard resize (max 1000px dimension)
            pil_img.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
            pil_img.save(filepath, format='JPEG', quality=85, optimize=True)

            # Thumbnail resize (max 300px)
            thumb_img = pil_img.copy()
            thumb_img.thumbnail((300, 300), Image.Resampling.LANCZOS)
            thumb_img.save(thumb_path, format='JPEG', quality=80, optimize=True)

            image_url = f"/uploads/products/{filename}"

            cur.execute("""
                INSERT INTO product_images (produce_id, image_url, storage_path, is_primary, display_order)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING image_id, produce_id, image_url, is_primary, display_order, created_at;
            """, (produce_id, image_url, str(filepath), is_primary, img_count))
            new_img = dict(cur.fetchone())

        return jsonify({
            'status': 'success',
            'message': 'Product image uploaded and optimized successfully.',
            'image': new_img
        }), 201

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/products/<int:produce_id>/images/<int:image_id>', methods=['PUT'])
@token_required
@roles_required('farmer', 'admin')
def set_primary_or_reorder_image(produce_id, image_id):
    """Set an image as primary or change display order."""
    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)
    role = request.current_user['role']
    data = request.get_json() or {}

    try:
        prod = fetch_one("SELECT * FROM farmer_produce WHERE produce_id = %s;", (produce_id,))
        if not prod or (role != 'admin' and prod['farmer_id'] != farmer_id):
            return jsonify({'error': 'Forbidden', 'message': 'Unauthorized to modify images for this product.'}), 403

        is_primary = data.get('is_primary')
        display_order = data.get('display_order')

        with get_db_cursor(commit=True) as cur:
            if is_primary:
                cur.execute("UPDATE product_images SET is_primary = FALSE WHERE produce_id = %s;", (produce_id,))
                cur.execute("UPDATE product_images SET is_primary = TRUE WHERE image_id = %s AND produce_id = %s RETURNING *;", (image_id, produce_id))
            elif display_order is not None:
                cur.execute("UPDATE product_images SET display_order = %s WHERE image_id = %s AND produce_id = %s RETURNING *;", (display_order, image_id, produce_id))
            updated = cur.fetchone()

        return jsonify({'status': 'success', 'message': 'Image preferences updated.', 'image': dict(updated) if updated else None}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/products/<int:produce_id>/images/<int:image_id>', methods=['DELETE'])
@token_required
@roles_required('farmer', 'admin')
def delete_product_image(produce_id, image_id):
    """Remove a product image from database and local storage."""
    user_id = request.current_user['user_id']
    farmer_id = _get_farmer_id_for_user(user_id)
    role = request.current_user['role']

    try:
        prod = fetch_one("SELECT * FROM farmer_produce WHERE produce_id = %s;", (produce_id,))
        if not prod or (role != 'admin' and prod['farmer_id'] != farmer_id):
            return jsonify({'error': 'Forbidden', 'message': 'Unauthorized to modify images.'}), 403

        img_rec = fetch_one("SELECT * FROM product_images WHERE image_id = %s AND produce_id = %s;", (image_id, produce_id))
        if not img_rec:
            return jsonify({'error': 'Not Found', 'message': 'Image record not found.'}), 404

        # Delete physical file if exists
        try:
            if img_rec.get('storage_path') and os.path.exists(img_rec['storage_path']):
                os.remove(img_rec['storage_path'])
        except Exception:
            pass

        with get_db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM product_images WHERE image_id = %s;", (image_id,))
            # If deleted image was primary, set next available image as primary
            if img_rec.get('is_primary'):
                cur.execute("""
                    UPDATE product_images
                    SET is_primary = TRUE
                    WHERE image_id = (SELECT image_id FROM product_images WHERE produce_id = %s ORDER BY display_order ASC LIMIT 1);
                """, (produce_id,))

        return jsonify({'status': 'success', 'message': 'Image deleted successfully.'}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# =============================================================================
# 6. AI FARMER PRODUCT ASSISTANT & AI PRICE INSIGHT
# =============================================================================

@farmers_bp.route('/ai-assist', methods=['POST'])
@token_required
def ai_product_assistant():
    """
    AI Assistant to generate structured product descriptions, suggested categories,
    tags, and missing-information checklist based on crop type and cultivar.
    Enforces strict guardrails: DOES NOT invent organic certificates or health claims.
    """
    data = request.get_json() or {}
    crop_name = data.get('crop_name', '').strip()
    variety = data.get('variety', '').strip()
    grade = data.get('quality_grade', 'Grade A')
    district = data.get('district', 'Namakkal')

    if not crop_name:
        return jsonify({'error': 'Bad Request', 'message': 'crop_name is required.'}), 400

    # Crop templates
    suggestions = {
        'Tomato': {
            'category': 'Vegetables',
            'desc': f"Farm-fresh {variety or 'hybrid'} tomatoes harvested in {district}, Tamil Nadu. Firm, uniformly colored, and sorted to {grade} standards. Suitable for fresh consumption, culinary preparations, and commercial food service.",
            'tags': ['fresh', 'local harvest', 'firm', 'salad-grade', 'tamildadu-grown'],
            'checklist': ['Confirm harvest date within 48 hours', 'Verify minimum order quantity (MOQ)', 'Confirm preferred collection hub']
        },
        'Onion': {
            'category': 'Vegetables',
            'desc': f"Cured and dried {variety or 'shallot'} onions from {district}. Pungent aroma and rich flavor profile, sorted for uniform bulb size and clean outer dry peel.",
            'tags': ['sambar onion', 'cured', 'culinary staple', 'long-shelf-life'],
            'checklist': ['Check curing completeness', 'Specify bulb sizing grade', 'Set moisture-proof packing']
        },
        'Potato': {
            'category': 'Tubers',
            'desc': f"Quality {variety or 'table'} potatoes cultivated in {district}. High starch density, thin skin, free of greening and blemishes, sorted to commercial {grade} specifications.",
            'tags': ['table potato', 'unwashed earth-cured', 'starch-rich'],
            'checklist': ['Ensure free from sprouting/greening', 'Specify bag weight (e.g. 50 kg gunny)']
        },
        'Banana': {
            'category': 'Fruits',
            'desc': f"Wholesome {variety or 'commercial'} bananas grown along river basins in {district}. Harvested at mature green stage for optimal transport without transit bruising.",
            'tags': ['naturally mature', 'fruit bunch', 'nutrient-dense'],
            'checklist': ['Specify bunch cut date', 'Indicate maturity percentage (e.g. 75-80% full)']
        }
    }

    fallback = {
        'category': 'Agricultural Produce',
        'desc': f"Freshly harvested {crop_name} ({variety or 'commercial grade'}) from {district}, Tamil Nadu. Graded to {grade} requirements for local market distribution.",
        'tags': [crop_name.lower(), 'farm-direct', 'fresh harvest'],
        'checklist': ['Specify available quantity in kg', 'Confirm expected harvest timing']
    }

    resp = suggestions.get(crop_name, fallback)
    return jsonify({'status': 'success', 'assistant': resp}), 200


@farmers_bp.route('/price-insight', methods=['GET'])
def get_price_insight():
    """
    Informational AI Price Insight for a crop in Tamil Nadu.
    Returns: current listed average, recent marketplace range, and informational estimated fair range.
    Explicitly labeled as an ESTIMATE.
    """
    crop_name = request.args.get('crop_name', default='Tomato')
    district = request.args.get('district', default='Namakkal')

    # Fetch recent active prices from database
    prices_row = fetch_one("""
        SELECT MIN(minimum_price_per_kg) AS min_price,
               MAX(minimum_price_per_kg) AS max_price,
               AVG(minimum_price_per_kg) AS avg_price,
               COUNT(*) AS listing_count
        FROM farmer_produce fp
        JOIN crops c ON fp.crop_id = c.crop_id
        WHERE LOWER(c.crop_name) = LOWER(%s) AND fp.status IN ('available', 'ACTIVE');
    """, (crop_name,))

    avg_p = float(prices_row['avg_price']) if (prices_row and prices_row['avg_price']) else 35.0
    min_p = float(prices_row['min_price']) if (prices_row and prices_row['min_price']) else round(avg_p * 0.9, 1)
    max_p = float(prices_row['max_price']) if (prices_row and prices_row['max_price']) else round(avg_p * 1.15, 1)

    est_low = round(avg_p * 0.94, 1)
    est_high = round(avg_p * 1.06, 1)

    return jsonify({
        'status': 'success',
        'crop_name': crop_name,
        'district': district,
        'recent_marketplace_range': f"₹{min_p:.1f} - ₹{max_p:.1f} / kg",
        'estimated_fair_range': f"₹{est_low:.1f} - ₹{est_high:.1f} / kg",
        'average_price': round(avg_p, 1),
        'disclaimer': "Informational estimate based on recent regional listings. Farmers retain full autonomy over their pricing."
    }), 200


# =============================================================================
# 7. FARMER PAYOUT PROFILES (BANK ACCOUNT WITHOUT REQUIRING UPI) & EARNINGS
# =============================================================================

@farmers_bp.route('/payout-profile', methods=['GET'])
@token_required
@roles_required('farmer', 'admin')
def get_farmer_payout_settings():
    """Retrieve farmer bank account and optional UPI disbursement profile."""
    user_id = request.current_user['user_id']
    farmer = fetch_one("SELECT farmer_id FROM farmer_profiles WHERE user_id = %s;", (user_id,))
    if not farmer:
        return jsonify({'error': 'Not Found', 'message': 'Farmer profile not found.'}), 404

    from services.settlement_service import get_farmer_payout_profile
    profile = get_farmer_payout_profile(farmer['farmer_id'])
    return jsonify({'status': 'success', 'payout_profile': profile}), 200


@farmers_bp.route('/payout-profile', methods=['POST'])
@token_required
@roles_required('farmer', 'admin')
def update_farmer_payout_settings():
    """
    Configure farmer disbursement details.
    UPI is optional. Bank account (account number + IFSC) is fully supported for direct bank settlements.
    """
    user_id = request.current_user['user_id']
    farmer = fetch_one("SELECT farmer_id, user_id FROM farmer_profiles WHERE user_id = %s;", (user_id,))
    if not farmer:
        return jsonify({'error': 'Not Found', 'message': 'Farmer profile not found.'}), 404

    data = request.get_json() or {}
    acc_holder = data.get('account_holder_name', '').strip() or request.current_user.get('name')
    acc_num = data.get('bank_account_number', '').strip()
    bank_name = data.get('bank_name', 'State Bank of India').strip()
    ifsc = data.get('IFSC', '').strip().upper()
    upi_id = (data.get('UPI_ID') or '').strip()
    upi_available = bool(upi_id)

    if not acc_num or not ifsc:
        return jsonify({
            'error': 'Bad Request',
            'message': 'bank_account_number and IFSC are required for direct bank payout.'
        }), 400

    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO farmer_payout_accounts (
                    farmer_id, account_holder_name, bank_account_number, bank_name,
                    IFSC, UPI_ID, UPI_available, verification_status, payout_provider_reference
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'VERIFIED', %s)
                ON CONFLICT (farmer_id) DO UPDATE
                    SET account_holder_name = EXCLUDED.account_holder_name,
                        bank_account_number = EXCLUDED.bank_account_number,
                        bank_name           = EXCLUDED.bank_name,
                        IFSC                = EXCLUDED.IFSC,
                        UPI_ID              = EXCLUDED.UPI_ID,
                        UPI_available       = EXCLUDED.UPI_available,
                        verification_status = 'VERIFIED',
                        updated_at          = CURRENT_TIMESTAMP;
            """, (
                farmer['farmer_id'], acc_holder, acc_num, bank_name,
                ifsc, upi_id if upi_id else None, upi_available,
                f"DISB-FARMER-{farmer['farmer_id']}"
            ))

        from services.settlement_service import get_farmer_payout_profile
        updated = get_farmer_payout_profile(farmer['farmer_id'])
        return jsonify({
            'status': 'success',
            'message': 'Disbursement payout account verified and saved successfully.',
            'payout_profile': updated
        }), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@farmers_bp.route('/earnings', methods=['GET'])
@token_required
@roles_required('farmer', 'admin')
def get_farmer_earnings_overview():
    """Retrieve full earnings, completed settlements, and pending payouts for farmer."""
    user_id = request.current_user['user_id']
    farmer = fetch_one("SELECT farmer_id FROM farmer_profiles WHERE user_id = %s;", (user_id,))
    if not farmer:
        return jsonify({'status': 'success', 'earnings': {'paid': 0, 'pending': 0, 'settlements': []}}), 200

    farmer_id = farmer['farmer_id']

    # Settlements ledger
    settlements = fetch_all("""
        SELECT s.*, o.order_date, o.order_status
        FROM settlements s
        JOIN orders o ON s.order_id = o.order_id
        WHERE s.beneficiary_id = %s AND s.beneficiary_type = 'FARMER'
        ORDER BY s.created_at DESC;
    """, (user_id,))

    # Payouts
    payouts = fetch_all("""
        SELECT fp.*, o.order_date, o.order_status
        FROM farmer_payouts fp
        JOIN orders o ON fp.order_id = o.order_id
        WHERE fp.farmer_id = %s
        ORDER BY fp.created_at DESC;
    """, (farmer_id,))

    paid_sum = sum(float(p['net_amount']) for p in payouts if p['payout_status'] == 'paid')
    pending_sum = sum(float(p['net_amount']) for p in payouts if p['payout_status'] in ('pending', 'processing'))

    from services.settlement_service import get_farmer_payout_profile
    acc = get_farmer_payout_profile(farmer_id)

    return jsonify({
        'status': 'success',
        'earnings': {
            'total_paid': round(paid_sum, 2),
            'total_pending': round(pending_sum, 2),
            'payout_account': acc,
            'settlements': settlements,
            'payout_records': payouts
        }
    }), 200

