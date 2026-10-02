"""
Quality Checks and Hub Operations API routes for AgriSmart Connect.
Provides digital intake, weighing inspection, quality grading, and packing queues.
"""

from datetime import datetime, date, timedelta
from flask import Blueprint, request, jsonify

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from auth_middleware import token_required, roles_required
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.auth_middleware import token_required, roles_required

quality_bp = Blueprint('quality', __name__)


@quality_bp.route('', methods=['POST'])
@token_required
@roles_required('hub_operator', 'admin')
def record_quality_check():
    """
    Record arrival inspection for farmer produce batch at the collection hub.
    Logs actual weight, quality grade, rejected quantity, and updates inventory/order status.
    """
    inspector_id = request.current_user['user_id']
    data = request.get_json() or {}

    hub_id = data.get('hub_id')
    order_id = data.get('order_id')
    produce_id = data.get('produce_id')
    actual_weight_kg = data.get('actual_weight_kg')
    quality_grade = data.get('quality_grade', 'Grade A')
    rejected_quantity_kg = data.get('rejected_quantity_kg', 0.0)
    remarks = data.get('remarks', '')

    if not all([hub_id, actual_weight_kg, quality_grade]):
        return jsonify({
            'error': 'Bad Request',
            'message': 'hub_id, actual_weight_kg, and quality_grade are required.'
        }), 400

    try:
        weight = float(actual_weight_kg)
        rejected = float(rejected_quantity_kg)
        accepted_weight = max(0.0, weight - rejected)

        with get_db_cursor(commit=True) as cur:
            # 1. Insert into quality_checks table
            cur.execute("""
                INSERT INTO quality_checks (
                    hub_id, inspector_id, actual_weight_kg,
                    quality_grade, rejected_quantity_kg, remarks
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING quality_check_id, actual_weight_kg, quality_grade, rejected_quantity_kg, inspection_time;
            """, (hub_id, inspector_id, weight, quality_grade, rejected, remarks))
            qc_record = dict(cur.fetchone())

            # 2. If produce_id provided, add to hub_inventory
            if produce_id:
                cur.execute("SELECT * FROM farmer_produce WHERE produce_id = %s;", (produce_id,))
                p = cur.fetchone()
                if p:
                    expiry_date = date.today() + timedelta(days=7)
                    cur.execute("""
                        INSERT INTO hub_inventory (
                            hub_id, produce_id, crop_id, variety_id,
                            available_quantity_kg, reserved_quantity_kg, sold_quantity_kg,
                            quality_grade, harvest_date, expected_expiry_date, status
                        )
                        VALUES (%s, %s, %s, %s, %s, 0.00, 0.00, %s, %s, %s, 'available')
                        RETURNING inventory_id;
                    """, (hub_id, produce_id, p['crop_id'], p['variety_id'], accepted_weight, quality_grade, p['harvest_date'], expiry_date))
                    inv = cur.fetchone()
                    qc_record['inventory_id'] = inv['inventory_id']

                    # Link inventory_id in quality_check
                    cur.execute("UPDATE quality_checks SET inventory_id = %s WHERE quality_check_id = %s;", (inv['inventory_id'], qc_record['quality_check_id']))

            # 3. If tied to an order, advance order status to 'quality_checked'
            if order_id:
                cur.execute("""
                    UPDATE orders 
                    SET order_status = 'quality_checked' 
                    WHERE order_id = %s;
                """, (order_id,))

        return jsonify({
            'status': 'success',
            'message': 'Quality check recorded successfully.',
            'quality_check': qc_record
        }), 201

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@quality_bp.route('/<int:hub_id>/queue', methods=['GET'])
@token_required
@roles_required('hub_operator', 'admin')
def get_hub_operational_queue(hub_id):
    """
    Retrieve live operational queues for a collection hub:
    - Incoming farmer consignments
    - Packing queue (quality checked orders ready to pack)
    - Ready for dispatch (packed orders awaiting delivery driver)
    """
    try:
        # Incoming farmer produce
        incoming = fetch_all("""
            SELECT fp.produce_id, fp.crop_id, c.crop_name, v.variety_name,
                   fp.expected_quantity_kg, fp.available_quantity_kg,
                   fp.reserved_quantity_kg, fp.harvest_date, fp.quality_grade,
                   fp_prof.farm_name, u.name AS farmer_name, u.phone AS farmer_phone
            FROM farmer_produce fp
            JOIN crops c ON fp.crop_id = c.crop_id
            LEFT JOIN varieties v ON fp.variety_id = v.variety_id
            JOIN farmer_profiles fp_prof ON fp.farmer_id = fp_prof.farmer_id
            JOIN users u ON fp_prof.user_id = u.user_id
            WHERE fp.preferred_hub_id = %s
              AND fp.status IN ('available', 'partially_reserved', 'reserved')
            ORDER BY fp.harvest_date ASC;
        """, (hub_id,))

        # Orders at hub needing packing or inspection
        orders_queue = fetch_all("""
            SELECT o.order_id, o.order_date, o.order_status, o.total_amount,
                   b.business_name, u.name AS buyer_name, u.phone AS buyer_phone,
                   d.status AS delivery_status, d.tracking_reference
            FROM orders o
            JOIN buyers b ON o.buyer_id = b.buyer_id
            JOIN users u ON b.user_id = u.user_id
            LEFT JOIN deliveries d ON o.order_id = d.order_id
            WHERE o.hub_id = %s
              AND o.order_status IN ('placed', 'confirmed', 'collecting', 'at_hub', 'quality_checked', 'packed')
            ORDER BY o.order_date ASC;
        """, (hub_id,))

        # Recent quality checks
        recent_qc = fetch_all("""
            SELECT qc.*, u.name AS inspector_name
            FROM quality_checks qc
            JOIN users u ON qc.inspector_id = u.user_id
            WHERE qc.hub_id = %s
            ORDER BY qc.inspection_time DESC
            LIMIT 15;
        """, (hub_id,))

        return jsonify({
            'status': 'success',
            'hub_id': hub_id,
            'incoming_produce': incoming,
            'orders_queue': orders_queue,
            'recent_quality_checks': recent_qc
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@quality_bp.route('/orders/<int:order_id>/pack', methods=['PUT'])
@token_required
@roles_required('hub_operator', 'admin')
def pack_order(order_id):
    """Mark an order as packed and ready for delivery partner pickup."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE orders
                SET order_status = 'packed'
                WHERE order_id = %s
                RETURNING order_id, order_status;
            """, (order_id,))
            updated = cur.fetchone()

        return jsonify({'status': 'success', 'message': f'Order #{order_id} packed and queued for dispatch.', 'order': dict(updated)}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500
