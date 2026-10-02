"""
backend/routes/delivery.py
Delivery Partner Logistics, Dispatch Station & Geofenced Tracking for AgriSmart Connect.
Tracks pickup, transit to hub, hub arrival geofencing, inter-hub trunking,
and final customer delivery handoff with OTP verification.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from auth_middleware import token_required, roles_required
    from services.geofence_service import record_partner_location
    from services.order_state_machine import (
        transition_order_state,
        canonical_status,
        STATE_PICKED_UP,
        STATE_IN_TRANSIT_TO_HUB,
        STATE_ARRIVED_AT_HUB,
        STATE_HUB_ACCEPTED,
        STATE_IN_TRANSIT_TO_NEXT_HUB,
        STATE_ARRIVED_AT_NEXT_HUB,
        STATE_OUT_FOR_DELIVERY,
        STATE_DELIVERED
    )
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.auth_middleware import token_required, roles_required
    from backend.services.geofence_service import record_partner_location
    from backend.services.order_state_machine import (
        transition_order_state,
        canonical_status,
        STATE_PICKED_UP,
        STATE_IN_TRANSIT_TO_HUB,
        STATE_ARRIVED_AT_HUB,
        STATE_HUB_ACCEPTED,
        STATE_IN_TRANSIT_TO_NEXT_HUB,
        STATE_ARRIVED_AT_NEXT_HUB,
        STATE_OUT_FOR_DELIVERY,
        STATE_DELIVERED
    )

delivery_bp = Blueprint('delivery', __name__)
_epod_store = {}


# ─────────────────────────────────────────────────────────────────────────────
# 1. LIST DELIVERIES & DISPATCH SCHEDULE
# ─────────────────────────────────────────────────────────────────────────────

@delivery_bp.route('', methods=['GET'])
@token_required
@roles_required('delivery_partner', 'admin', 'hub_operator', 'hub_staff', 'hub_manager')
def list_deliveries():
    """Retrieve deliveries list with items manifest, hub details, and OTP state."""
    user = request.current_user
    user_id = user['user_id']
    role = user['role']

    try:
        query = """
            SELECT d.*, o.order_date, o.order_status, o.total_amount, o.delivery_address,
                   o.source_hub_id, o.destination_hub_id, o.requires_hub_transfer,
                   o.delivery_otp,
                   b.business_name, u_b.name AS buyer_name, u_b.phone AS buyer_phone,
                   h.hub_name, h.address AS hub_address, h.district AS hub_district,
                   h.latitude AS hub_lat, h.longitude AS hub_lng,
                   h_dst.hub_name AS dest_hub_name, h_dst.district AS dest_hub_district,
                   u_dp.name AS driver_name,
                   COALESCE(SUM(oi.quantity_kg), 0) AS total_weight_kg,
                   COUNT(oi.order_item_id) AS items_count,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'order_item_id', oi.order_item_id,
                               'crop_name', c.crop_name,
                               'variety_name', v.variety_name,
                               'quantity_kg', oi.quantity_kg,
                               'price_per_kg', oi.price_per_kg,
                               'subtotal', oi.subtotal,
                               'quality_grade', p.quality_grade,
                               'farmer_name', u_f.name,
                               'farm_name', fp.farm_name,
                               'farmer_phone', u_f.phone,
                               'farmer_district', fp.district
                           )
                       ) FILTER (WHERE oi.order_item_id IS NOT NULL),
                       '[]'::json
                   ) AS items
            FROM deliveries d
            JOIN orders o ON d.order_id = o.order_id
            JOIN buyers b ON o.buyer_id = b.buyer_id
            JOIN users u_b ON b.user_id = u_b.user_id
            JOIN hubs h ON d.hub_id = h.hub_id
            LEFT JOIN hubs h_dst ON o.destination_hub_id = h_dst.hub_id
            LEFT JOIN users u_dp ON d.delivery_partner_id = u_dp.user_id
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            LEFT JOIN crops c ON oi.crop_id = c.crop_id
            LEFT JOIN varieties v ON oi.variety_id = v.variety_id
            LEFT JOIN users u_f ON oi.farmer_id = u_f.user_id
            LEFT JOIN farmer_profiles fp ON u_f.user_id = fp.user_id
            LEFT JOIN farmer_produce p ON oi.produce_id = p.produce_id
        """
        params = []
        if role == 'delivery_partner':
            query += " WHERE d.delivery_partner_id = %s OR d.delivery_partner_id IS NULL"
            params.append(user_id)

        query += """
            GROUP BY d.delivery_id, o.order_id, b.buyer_id, u_b.user_id, h.hub_id, h_dst.hub_id, u_dp.user_id
            ORDER BY d.created_at DESC;
        """

        deliveries = fetch_all(query, tuple(params) if params else None)

        for d in deliveries:
            d['buyer_otp'] = d.get('delivery_otp') or str((d['delivery_id'] * 317 + 1234) % 9000 + 1000)
            d['epod'] = _epod_store.get(d['delivery_id'])
            # Canonical status normalization for clean UI rendering
            d['canonical_status'] = canonical_status(d.get('order_status'))

        return jsonify({'status': 'success', 'deliveries': deliveries}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# 2. CLAIM DELIVERY RUN
# ─────────────────────────────────────────────────────────────────────────────

@delivery_bp.route('/<int:delivery_id>/claim', methods=['PUT'])
@token_required
@roles_required('delivery_partner')
def claim_delivery(delivery_id):
    """Driver accepts and assigns a delivery run to themselves."""
    user_id = request.current_user['user_id']
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE deliveries
                SET delivery_partner_id = %s, status = 'assigned'
                WHERE delivery_id = %s AND (delivery_partner_id IS NULL OR delivery_partner_id = %s)
                RETURNING delivery_id, order_id, status, delivery_partner_id;
            """, (user_id, delivery_id, user_id))
            updated = cur.fetchone()

        if not updated:
            return jsonify({'error': 'Conflict', 'message': 'Delivery already claimed by another partner.'}), 409

        # Update order routes
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE order_routes
                SET delivery_partner_id = %s
                WHERE order_id = %s AND delivery_partner_id IS NULL;
            """, (user_id, updated['order_id']))

        return jsonify({'status': 'success', 'message': 'Delivery run claimed.', 'delivery': dict(updated)}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# 3. GPS LOCATION UPDATE & GEOFENCING
# ─────────────────────────────────────────────────────────────────────────────

@delivery_bp.route('/location', methods=['POST'])
@token_required
@roles_required('delivery_partner')
def update_partner_location():
    """
    Log live driver location during active delivery and evaluate proximity to regional hubs.
    """
    user_id = request.current_user['user_id']
    data = request.get_json() or {}

    lat = data.get('latitude')
    lon = data.get('longitude')
    order_id = data.get('order_id')
    speed = float(data.get('speed_kmh') or 0.0)
    heading = float(data.get('heading') or 0.0)

    if lat is None or lon is None:
        return jsonify({'error': 'Bad Request', 'message': 'latitude and longitude are required.'}), 400

    try:
        res = record_partner_location(
            partner_id=user_id,
            latitude=float(lat),
            longitude=float(lon),
            order_id=order_id,
            speed_kmh=speed,
            heading=heading
        )
        return jsonify({'status': 'success', **res}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# 4. STATUS TRANSITION WITH OTP & GEOFENCE HOOK
# ─────────────────────────────────────────────────────────────────────────────

@delivery_bp.route('/<int:delivery_id>/status', methods=['PUT'])
@token_required
@roles_required('delivery_partner', 'admin')
def update_delivery_status(delivery_id):
    """
    Progress delivery state through central state machine.
    """
    user = request.current_user
    data = request.get_json() or {}
    new_status = data.get('status', '').strip().lower()

    deliv = fetch_one("SELECT * FROM deliveries WHERE delivery_id = %s;", (delivery_id,))
    if not deliv:
        return jsonify({'error': 'Not Found', 'message': 'Delivery record not found.'}), 404

    order_id = deliv['order_id']
    pod_data = data.get('pod') or {}
    otp = data.get('otp') or pod_data.get('otp')

    try:
        if new_status == 'picked_up':
            res = transition_order_state(order_id, STATE_PICKED_UP, user['user_id'], user['role'], notes='Picked up by delivery partner')
        elif new_status == 'in_transit':
            res = transition_order_state(order_id, STATE_IN_TRANSIT_TO_HUB, user['user_id'], user['role'], notes='In transit to hub')
        elif new_status in ('delivered', 'complete'):
            res = transition_order_state(order_id, STATE_DELIVERED, user['user_id'], user['role'], otp=otp, notes=pod_data.get('notes', 'Delivered'))
            _epod_store[delivery_id] = {
                'otp_verified': True,
                'verified_at': datetime.now().strftime('%d %b %Y, %I:%M %p'),
                'notes': pod_data.get('notes', '').strip(),
                'signature': pod_data.get('signature', ''),
                'photo': pod_data.get('photo', '')
            }
        else:
            # Direct canonical state update
            res = transition_order_state(order_id, new_status.upper(), user['user_id'], user['role'], otp=otp, notes=data.get('notes'))

        updated_deliv = fetch_one("SELECT * FROM deliveries WHERE delivery_id = %s;", (delivery_id,))
        return jsonify({
            'status': 'success',
            'message': f"Delivery #{delivery_id} progressed.",
            'delivery': updated_deliv,
            'state_machine': res
        }), 200

    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


# ─────────────────────────────────────────────────────────────────────────────
# 5. DRIVER EARNINGS
# ─────────────────────────────────────────────────────────────────────────────

@delivery_bp.route('/my-payouts', methods=['GET'])
@delivery_bp.route('/earnings', methods=['GET'])
@token_required
@roles_required('delivery_partner', 'admin')
def get_my_payouts():
    """Retrieve driver earnings history and payout breakdown."""
    user_id = request.current_user['user_id']
    try:
        payouts = fetch_all("""
            SELECT dp.*, d.delivery_address, d.delivery_time, d.status AS delivery_status,
                   o.total_amount, o.order_date
            FROM delivery_payouts dp
            JOIN deliveries d ON dp.delivery_id = d.delivery_id
            JOIN orders o ON dp.order_id = o.order_id
            WHERE dp.delivery_partner_id = %s
            ORDER BY dp.created_at DESC;
        """, (user_id,))

        total_earned = sum(float(p['total_payout']) for p in payouts if p['payout_status'] == 'paid')
        pending = sum(float(p['total_payout']) for p in payouts if p['payout_status'] in ('pending', 'processing'))

        # Also check settlements ledger
        settlements = fetch_all("""
            SELECT s.*, o.order_date
            FROM settlements s
            JOIN orders o ON s.order_id = o.order_id
            WHERE s.beneficiary_id = %s AND s.beneficiary_type = 'DELIVERY_PARTNER'
            ORDER BY s.created_at DESC;
        """, (user_id,))

        return jsonify({
            'status': 'success',
            'payouts': payouts,
            'settlements': settlements,
            'metrics': {
                'total_earned': total_earned,
                'pending_disbursement': pending,
                'trips_completed': len([p for p in payouts if p['payout_status'] == 'paid'])
            }
        }), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500
