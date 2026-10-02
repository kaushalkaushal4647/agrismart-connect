"""
backend/routes/orders.py
Comprehensive Order Management, State Machine & Fulfillment Pipeline for AgriSmart Connect.
Integrates Multi-Hub Routing, Dynamic Assignment, Farmer Actions,
Hub Quality Inspection, Inter-Hub Transfer, Delivery OTP Handshake, and Multi-Party Settlements.
"""

from flask import Blueprint, request, jsonify

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from auth_middleware import token_required, roles_required
    from services.inventory_service import reserve_produce, release_reservation, complete_sale
    from services.order_state_machine import (
        transition_order_state,
        get_order_tracking_timeline,
        canonical_status,
        STATE_PAYMENT_PENDING,
        STATE_PAYMENT_SUCCESS,
        STATE_ORDER_CONFIRMED,
        STATE_FARMER_ACCEPTED,
        STATE_FARMER_REJECTED,
        STATE_FARMER_PREPARING,
        STATE_READY_FOR_PICKUP,
        STATE_PICKUP_ASSIGNED,
        STATE_PICKED_UP,
        STATE_IN_TRANSIT_TO_HUB,
        STATE_ARRIVED_AT_HUB,
        STATE_HUB_QC,
        STATE_HUB_ACCEPTED,
        STATE_HUB_REJECTED,
        STATE_HUB_TRANSFER_REQUIRED,
        STATE_IN_TRANSIT_TO_NEXT_HUB,
        STATE_ARRIVED_AT_NEXT_HUB,
        STATE_ASSIGNED_TO_DELIVERY,
        STATE_OUT_FOR_DELIVERY,
        STATE_DELIVERED,
        STATE_ORDER_CANCELLED
    )
    from services.hub_routing_service import determine_order_route
    from config import Config
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.auth_middleware import token_required, roles_required
    from backend.services.inventory_service import reserve_produce, release_reservation, complete_sale
    from backend.services.order_state_machine import (
        transition_order_state,
        get_order_tracking_timeline,
        canonical_status,
        STATE_PAYMENT_PENDING,
        STATE_PAYMENT_SUCCESS,
        STATE_ORDER_CONFIRMED,
        STATE_FARMER_ACCEPTED,
        STATE_FARMER_REJECTED,
        STATE_FARMER_PREPARING,
        STATE_READY_FOR_PICKUP,
        STATE_PICKUP_ASSIGNED,
        STATE_PICKED_UP,
        STATE_IN_TRANSIT_TO_HUB,
        STATE_ARRIVED_AT_HUB,
        STATE_HUB_QC,
        STATE_HUB_ACCEPTED,
        STATE_HUB_REJECTED,
        STATE_HUB_TRANSFER_REQUIRED,
        STATE_IN_TRANSIT_TO_NEXT_HUB,
        STATE_ARRIVED_AT_NEXT_HUB,
        STATE_ASSIGNED_TO_DELIVERY,
        STATE_OUT_FOR_DELIVERY,
        STATE_DELIVERED,
        STATE_ORDER_CANCELLED
    )
    from backend.services.hub_routing_service import determine_order_route
    from backend.config import Config

orders_bp = Blueprint('orders', __name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. CREATE ORDER
# ─────────────────────────────────────────────────────────────────────────────

@orders_bp.route('', methods=['POST'])
@token_required
@roles_required('consumer', 'restaurant', 'retailer', 'admin', 'delivery_partner', 'farmer', 'hub_operator', 'hub_staff')
def create_order():
    """
    Place a new agricultural order with multi-hub routing and inventory reservation.
    """
    user_id = request.current_user['user_id']
    user_role = request.current_user['role']
    data = request.get_json() or {}

    buyer = fetch_one("SELECT * FROM buyers WHERE user_id = %s;", (user_id,))
    if not buyer:
        delivery_addr = data.get('delivery_address') or 'Customer Address, Tamil Nadu'
        user_name = request.current_user.get('name') or 'Customer'
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO buyers (user_id, buyer_type, business_name, address, village, district)
                VALUES (%s, 'consumer', %s, %s, 'Local Area', 'Chennai')
                ON CONFLICT (user_id) DO NOTHING;
            """, (user_id, user_name, delivery_addr))
        buyer = fetch_one("SELECT * FROM buyers WHERE user_id = %s;", (user_id,))

    buyer_id = buyer['buyer_id']
    items = data.get('items', [])
    if not items:
        return jsonify({'error': 'Bad Request', 'message': 'At least one produce item is required to place an order.'}), 400

    delivery_address = data.get('delivery_address', buyer.get('address') or 'Customer Address, Tamil Nadu')
    delivery_lat = data.get('delivery_latitude', buyer.get('latitude'))
    delivery_lon = data.get('delivery_longitude', buyer.get('longitude'))
    demand_id = data.get('demand_id')

    try:
        with get_db_cursor(commit=True) as cur:
            subtotal = 0.0
            validated_items = []
            primary_farmer_id = None

            # 1. Validate & reserve inventory atomically
            for item in items:
                raw_pid = item.get('produce_id') if item.get('produce_id') is not None else item.get('id')
                if raw_pid is None:
                    return jsonify({'error': 'Bad Request', 'message': 'Each item must have a valid produce_id.'}), 400
                produce_id = int(raw_pid)
                qty = float(item.get('quantity_kg', 0))

                if qty <= 0:
                    continue

                cur.execute("""
                    SELECT fp.produce_id, fp.farmer_id, fp.crop_id, fp.variety_id,
                           fp.minimum_price_per_kg, fp.preferred_hub_id
                    FROM farmer_produce fp
                    WHERE fp.produce_id = %s
                    FOR UPDATE;
                """, (produce_id,))
                meta = cur.fetchone()
                if not meta:
                    return jsonify({'error': 'Not Found', 'message': f'Produce #{produce_id} not found.'}), 404

                reserve_produce(cur, produce_id, qty)
                price = float(item.get('price_per_kg', meta['minimum_price_per_kg']))
                line_total = round(qty * price, 2)
                subtotal += line_total

                if not primary_farmer_id:
                    primary_farmer_id = meta['farmer_id']

                validated_items.append({
                    'produce_id': produce_id,
                    'farmer_id': meta['farmer_id'],
                    'crop_id': meta['crop_id'],
                    'variety_id': meta['variety_id'],
                    'quantity_kg': qty,
                    'price_per_kg': price,
                    'subtotal': line_total
                })

            subtotal = round(subtotal, 2)
            delivery_fee = float(data.get('delivery_fee', 65.0))
            commission_pct = Config.PLATFORM_COMMISSION_PERCENT
            platform_fee = round(subtotal * commission_pct / 100, 2)
            total_amount = round(subtotal + delivery_fee + platform_fee, 2)

            # 2. Insert Orders Record with canonical initial state
            cur.execute("""
                INSERT INTO orders (
                    buyer_id, delivery_address, delivery_latitude, delivery_longitude,
                    subtotal, delivery_fee, platform_fee, total_amount, payment_status, order_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                RETURNING *;
            """, (
                buyer_id, delivery_address, delivery_lat, delivery_lon,
                subtotal, delivery_fee, platform_fee, total_amount, STATE_PAYMENT_PENDING
            ))
            order = dict(cur.fetchone())
            order_id = order['order_id']

            # 3. Insert Order Items
            for vi in validated_items:
                cur.execute("""
                    INSERT INTO order_items (
                        order_id, produce_id, crop_id, variety_id, farmer_id,
                        quantity_kg, price_per_kg, subtotal
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    order_id, vi['produce_id'], vi['crop_id'], vi['variety_id'], vi['farmer_id'],
                    vi['quantity_kg'], vi['price_per_kg'], vi['subtotal']
                ))

            # 4. Insert draft Delivery record
            tracking_ref = f"AGRI-DEL-{order_id}-{int(order['order_date'].timestamp())}"
            cur.execute("""
                INSERT INTO deliveries (
                    order_id, hub_id, delivery_address, status, tracking_reference
                )
                VALUES (%s, %s, %s, 'assigned', %s)
                ON CONFLICT (order_id) DO NOTHING;
            """, (order_id, order.get('hub_id') or 101, delivery_address, tracking_ref))

            # 5. Insert Payment Ledger Record
            tx_ref = f"TXN-PAY-{order_id}"
            cur.execute("""
                INSERT INTO payments (
                    order_id, buyer_amount, delivery_fee, platform_fee,
                    farmer_amount, payment_method, transaction_reference, payment_status
                )
                VALUES (%s, %s, %s, %s, %s, 'UPI', %s, 'pending')
                ON CONFLICT (order_id) DO NOTHING;
            """, (order_id, total_amount, delivery_fee, platform_fee, subtotal, tx_ref))

            # 6. Audit initial state event
            cur.execute("""
                INSERT INTO order_events (
                    order_id, previous_status, new_status, actor_id, actor_role, location, notes
                )
                VALUES (%s, NULL, %s, %s, %s, %s, 'Order created awaiting customer payment');
            """, (order_id, STATE_PAYMENT_PENDING, user_id, user_role, delivery_address))

            # 7. Matched demand update if applicable
            if demand_id:
                cur.execute("UPDATE demand_records SET status = 'matched' WHERE demand_id = %s;", (demand_id,))

        # 8. Dynamic Hub Route Computation
        if primary_farmer_id:
            try:
                determine_order_route(
                    order_id=order_id,
                    farmer_id=primary_farmer_id,
                    buyer_id=buyer_id,
                    delivery_address=delivery_address,
                    delivery_lat=delivery_lat,
                    delivery_lon=delivery_lon
                )
            except Exception as routing_err:
                logger.warning(f"Initial routing computation deferred: {routing_err}")

        # In DEMO_MODE: auto-confirm order for instant walkthrough if requested
        auto_pay = data.get('auto_confirm_demo', False) or (Config.DEMO_MODE and data.get('payment_method') == 'DEMO_INSTANT')
        if auto_pay:
            transition_order_state(
                order_id=order_id,
                target_status=STATE_PAYMENT_SUCCESS,
                actor_id=user_id,
                actor_role='system',
                notes='Demo mode: simulated instantaneous payment success'
            )
            transition_order_state(
                order_id=order_id,
                target_status=STATE_ORDER_CONFIRMED,
                actor_id=user_id,
                actor_role='system',
                notes='Order confirmed by platform'
            )

        return jsonify({
            'status': 'success',
            'message': 'Order successfully created and inventory reserved!',
            'order_id': order_id,
            'order': {
                'order_id': order_id,
                'total_amount': total_amount,
                'subtotal': subtotal,
                'delivery_fee': delivery_fee,
                'platform_fee': platform_fee,
                'order_status': STATE_ORDER_CONFIRMED if auto_pay else STATE_PAYMENT_PENDING,
                'payment_status': 'paid' if auto_pay else 'pending'
            },
            'items_count': len(validated_items),
            'total_amount': total_amount,
            'payment_status': 'paid' if auto_pay else 'pending',
            'order_status': STATE_ORDER_CONFIRMED if auto_pay else STATE_PAYMENT_PENDING
        }), 201

    except Exception as e:
        logger.error(f"create_order failed: {e}", exc_info=True)
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# 2. LIST ORDERS (ROLE FILTERED)
# ─────────────────────────────────────────────────────────────────────────────

@orders_bp.route('', methods=['GET'])
@token_required
def list_orders():
    """List orders accessible by authenticated user role."""
    user = request.current_user
    user_id = user['user_id']
    role = user['role']

    try:
        if role in ('admin',):
            orders = fetch_all("""
                SELECT o.*, b.business_name, u.name AS buyer_name, u.phone AS buyer_phone,
                       h_src.hub_name AS source_hub_name, h_dst.hub_name AS dest_hub_name,
                       h_cur.hub_name AS current_hub_name,
                       d.status AS delivery_status, d.tracking_reference,
                       u_dp.name AS driver_name
                FROM orders o
                JOIN buyers b ON o.buyer_id = b.buyer_id
                JOIN users u ON b.user_id = u.user_id
                LEFT JOIN hubs h_src ON o.source_hub_id = h_src.hub_id
                LEFT JOIN hubs h_dst ON o.destination_hub_id = h_dst.hub_id
                LEFT JOIN hubs h_cur ON o.hub_id = h_cur.hub_id
                LEFT JOIN deliveries d ON o.order_id = d.order_id
                LEFT JOIN users u_dp ON d.delivery_partner_id = u_dp.user_id
                ORDER BY o.order_date DESC;
            """)
        elif role in ('hub_operator', 'hub_staff', 'hub_manager'):
            # Only orders routed through their authorized hub
            assigned_hub = user.get('assigned_hub_id')
            query = """
                SELECT o.*, b.business_name, u.name AS buyer_name,
                       h_src.hub_name AS source_hub_name, h_dst.hub_name AS dest_hub_name,
                       h_cur.hub_name AS current_hub_name,
                       d.status AS delivery_status, d.tracking_reference
                FROM orders o
                JOIN buyers b ON o.buyer_id = b.buyer_id
                JOIN users u ON b.user_id = u.user_id
                LEFT JOIN hubs h_src ON o.source_hub_id = h_src.hub_id
                LEFT JOIN hubs h_dst ON o.destination_hub_id = h_dst.hub_id
                LEFT JOIN hubs h_cur ON o.hub_id = h_cur.hub_id
                LEFT JOIN deliveries d ON o.order_id = d.order_id
            """
            if assigned_hub:
                query += " WHERE o.hub_id = %s OR o.source_hub_id = %s OR o.destination_hub_id = %s"
                orders = fetch_all(query + " ORDER BY o.order_date DESC;", (assigned_hub, assigned_hub, assigned_hub))
            else:
                orders = fetch_all(query + " ORDER BY o.order_date DESC;")

        elif role == 'farmer':
            farmer = fetch_one("SELECT farmer_id FROM farmer_profiles WHERE user_id = %s;", (user_id,))
            if not farmer:
                return jsonify({'status': 'success', 'orders': []}), 200

            orders = fetch_all("""
                SELECT DISTINCT o.*, b.business_name, u.name AS buyer_name,
                                h_src.hub_name AS source_hub_name, h_dst.hub_name AS dest_hub_name,
                                d.status AS delivery_status
                FROM orders o
                JOIN order_items oi ON o.order_id = oi.order_id
                JOIN buyers b ON o.buyer_id = b.buyer_id
                JOIN users u ON b.user_id = u.user_id
                LEFT JOIN hubs h_src ON o.source_hub_id = h_src.hub_id
                LEFT JOIN hubs h_dst ON o.destination_hub_id = h_dst.hub_id
                LEFT JOIN deliveries d ON o.order_id = d.order_id
                WHERE oi.farmer_id = %s
                ORDER BY o.order_date DESC;
            """, (farmer['farmer_id'],))
        elif role == 'delivery_partner':
            orders = fetch_all("""
                SELECT o.*, b.business_name, u.name AS buyer_name, u.phone AS buyer_phone,
                       h_src.hub_name AS source_hub_name, h_dst.hub_name AS dest_hub_name,
                       d.status AS delivery_status, d.tracking_reference
                FROM orders o
                JOIN deliveries d ON o.order_id = d.order_id
                JOIN buyers b ON o.buyer_id = b.buyer_id
                JOIN users u ON b.user_id = u.user_id
                LEFT JOIN hubs h_src ON o.source_hub_id = h_src.hub_id
                LEFT JOIN hubs h_dst ON o.destination_hub_id = h_dst.hub_id
                WHERE d.delivery_partner_id = %s OR d.delivery_partner_id IS NULL
                ORDER BY o.order_date DESC;
            """, (user_id,))
        else:
            # Buyer role (consumer, restaurant, retailer)
            buyer = fetch_one("SELECT buyer_id FROM buyers WHERE user_id = %s;", (user_id,))
            if not buyer:
                return jsonify({'status': 'success', 'orders': []}), 200

            orders = fetch_all("""
                SELECT o.*, h_src.hub_name AS source_hub_name, h_dst.hub_name AS dest_hub_name,
                       h_cur.hub_name AS current_hub_name,
                       d.status AS delivery_status, d.tracking_reference
                FROM orders o
                LEFT JOIN hubs h_src ON o.source_hub_id = h_src.hub_id
                LEFT JOIN hubs h_dst ON o.destination_hub_id = h_dst.hub_id
                LEFT JOIN hubs h_cur ON o.hub_id = h_cur.hub_id
                LEFT JOIN deliveries d ON o.order_id = d.order_id
                WHERE o.buyer_id = %s
                ORDER BY o.order_date DESC;
            """, (buyer['buyer_id'],))

        return jsonify({'status': 'success', 'orders': orders}), 200

    except Exception as e:
        logger.error(f"list_orders failed: {e}", exc_info=True)
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# 3. GET SINGLE ORDER & TRACKING TIMELINE
# ─────────────────────────────────────────────────────────────────────────────

@orders_bp.route('/<int:order_id>', methods=['GET'])
@token_required
def get_order(order_id):
    """Retrieve complete order details."""
    data = get_order_tracking_timeline(order_id)
    if not data or not data.get('order'):
        return jsonify({'error': 'Not Found', 'message': 'Order not found.'}), 404
    return jsonify({'status': 'success', **data}), 200


@orders_bp.route('/<int:order_id>/tracking', methods=['GET'])
def get_public_order_tracking(order_id):
    """Retrieve order tracking timeline for customer portal."""
    data = get_order_tracking_timeline(order_id)
    if not data or not data.get('order'):
        return jsonify({'error': 'Not Found', 'message': 'Order not found.'}), 404
    return jsonify({'status': 'success', **data}), 200


@orders_bp.route('/<int:order_id>/events', methods=['GET'])
@token_required
def get_order_events(order_id):
    """Retrieve full audit log trail of state transitions for an order."""
    events = fetch_all("""
        SELECT oe.*, u.name AS actor_name, u.role AS actor_account_role
        FROM order_events oe
        LEFT JOIN users u ON oe.actor_id = u.user_id
        WHERE oe.order_id = %s
        ORDER BY oe.timestamp ASC;
    """, (order_id,))
    return jsonify({'status': 'success', 'order_id': order_id, 'events': events}), 200


# ─────────────────────────────────────────────────────────────────────────────
# 4. WORKFLOW TRANSITION ENDPOINTS (STRICT ROLE CONTROL)
# ─────────────────────────────────────────────────────────────────────────────

@orders_bp.route('/<int:order_id>/accept', methods=['POST'])
@token_required
@roles_required('farmer', 'admin')
def farmer_accept_order(order_id):
    """Farmer accepts order for harvesting and fulfillment."""
    user = request.current_user
    data = request.get_json() or {}
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_FARMER_ACCEPTED,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes', 'Farmer accepted order allocation')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/reject', methods=['POST'])
@token_required
@roles_required('farmer', 'admin')
def farmer_reject_order(order_id):
    """Farmer rejects order -> initiates automatic refund workflow."""
    user = request.current_user
    data = request.get_json() or {}
    reason = data.get('reason') or data.get('notes') or 'Produce unavailable / harvest delayed'
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_FARMER_REJECTED,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=f"Farmer rejected order: {reason}"
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/prepare', methods=['POST'])
@token_required
@roles_required('farmer', 'admin')
def farmer_prepare_order(order_id):
    """Farmer marks order as being harvested and packaged."""
    user = request.current_user
    data = request.get_json() or {}
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_FARMER_PREPARING,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes', 'Farmer harvesting and preparing crate')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/ready', methods=['POST'])
@token_required
@roles_required('farmer', 'admin')
def farmer_ready_order(order_id):
    """Farmer marks produce ready for logistics pickup at the farm."""
    user = request.current_user
    data = request.get_json() or {}
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_READY_FOR_PICKUP,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes', 'Crates packaged and ready at farm gate')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/pickup', methods=['POST'])
@token_required
@roles_required('delivery_partner', 'admin')
def delivery_pickup_order(order_id):
    """Delivery driver picks up order from the farmer's field."""
    user = request.current_user
    data = request.get_json() or {}
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_PICKED_UP,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes', 'Driver collected shipment from farm')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/transit', methods=['POST'])
@token_required
@roles_required('delivery_partner', 'admin')
def delivery_transit_order(order_id):
    """Delivery driver starts journey towards aggregation hub."""
    user = request.current_user
    data = request.get_json() or {}
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_IN_TRANSIT_TO_HUB,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes', 'In transit to aggregation hub')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/arrived-hub', methods=['POST'])
@token_required
@roles_required('delivery_partner', 'hub_operator', 'hub_staff', 'hub_manager', 'admin')
def delivery_arrived_hub(order_id):
    """Driver arrives at collection hub or hub staff accepts physical arrival."""
    user = request.current_user
    data = request.get_json() or {}
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_ARRIVED_AT_HUB,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes', 'Vehicle arrived at collection hub receiving bay')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/qc/start', methods=['POST'])
@token_required
@roles_required('hub_operator', 'hub_staff', 'hub_manager', 'admin')
def hub_qc_start(order_id):
    """Hub staff starts digital weighing and quality inspection."""
    user = request.current_user
    data = request.get_json() or {}
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_HUB_QC,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes', 'Digital inspection and weighing commenced')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/qc/accept', methods=['POST'])
@token_required
@roles_required('hub_operator', 'hub_staff', 'hub_manager', 'admin')
def hub_qc_accept(order_id):
    """Hub staff certifies produce quality. Automatically routes to transfer or dispatch."""
    user = request.current_user
    data = request.get_json() or {}
    weight = data.get('weight_kg')
    grade = data.get('quality_grade', 'Grade A')
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_HUB_ACCEPTED,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=f"QC Certified: {grade} ({weight} kg verified)" if weight else f"QC Certified: {grade}",
            metadata={'actual_weight_kg': weight, 'quality_grade': grade}
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/qc/reject', methods=['POST'])
@token_required
@roles_required('hub_operator', 'hub_staff', 'hub_manager', 'admin')
def hub_qc_reject(order_id):
    """Hub rejects produce during inspection -> starts refund."""
    user = request.current_user
    data = request.get_json() or {}
    reason = data.get('reason', 'Quality check failed (spoilage / grade mismatch)')
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_HUB_REJECTED,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=f"Hub QC Rejected: {reason}"
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/transfer', methods=['POST'])
@token_required
@roles_required('hub_operator', 'hub_staff', 'hub_manager', 'delivery_partner', 'admin')
def hub_transfer_dispatch(order_id):
    """Dispatch shipment on inter-hub transfer vehicle towards destination hub."""
    user = request.current_user
    data = request.get_json() or {}
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_IN_TRANSIT_TO_NEXT_HUB,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes', 'Transferred to regional trunk-line carrier')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/receive-transfer', methods=['POST'])
@token_required
@roles_required('hub_operator', 'hub_staff', 'hub_manager', 'delivery_partner', 'admin')
def hub_receive_transfer(order_id):
    """Destination hub receives inter-hub transfer shipment."""
    user = request.current_user
    data = request.get_json() or {}
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_ARRIVED_AT_NEXT_HUB,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes', 'Inter-hub shipment arrived at destination facility')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/assign-delivery', methods=['POST'])
@token_required
@roles_required('hub_operator', 'hub_staff', 'hub_manager', 'admin')
def assign_last_mile(order_id):
    """Hub staff assigns order to last-mile delivery partner."""
    user = request.current_user
    data = request.get_json() or {}
    partner_id = data.get('delivery_partner_id')
    with get_db_cursor(commit=True) as cur:
        if partner_id:
            cur.execute("UPDATE deliveries SET delivery_partner_id = %s WHERE order_id = %s;", (partner_id, order_id))
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_ASSIGNED_TO_DELIVERY,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes', 'Assigned for last-mile delivery')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/out-for-delivery', methods=['POST'])
@token_required
@roles_required('delivery_partner', 'admin', 'hub_operator', 'hub_staff')
def out_for_delivery(order_id):
    """Driver departs from final hub with order. Handshake OTP generated and sent to customer."""
    user = request.current_user
    data = request.get_json() or {}
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_OUT_FOR_DELIVERY,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes', 'Driver departed hub. Handshake OTP generated.')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'State Error', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/deliver', methods=['POST'])
@token_required
@roles_required('delivery_partner', 'admin')
def complete_delivery(order_id):
    """
    Complete delivery by verifying customer OTP.
    Finalizes inventory sale and generates multi-party settlement ledger.
    """
    user = request.current_user
    data = request.get_json() or {}
    provided_otp = data.get('otp') or (data.get('pod') or {}).get('otp')

    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=STATE_DELIVERED,
            actor_id=user['user_id'],
            actor_role=user['role'],
            otp=provided_otp,
            notes=data.get('notes', 'Order handed over to customer with OTP verification')
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({'error': 'Delivery Verification Failed', 'message': str(e)}), 400


@orders_bp.route('/<int:order_id>/status', methods=['PUT'])
@token_required
def update_order_status_generic(order_id):
    """
    Generic state update endpoint preserved for UI button compatibility.
    Validates transition through central state machine.
    """
    user = request.current_user
    data = request.get_json() or {}
    raw_status = data.get('order_status') or data.get('status')
    if not raw_status:
        return jsonify({'error': 'Bad Request', 'message': 'order_status is required.'}), 400

    target = canonical_status(raw_status)
    try:
        res = transition_order_state(
            order_id=order_id,
            target_status=target,
            actor_id=user['user_id'],
            actor_role=user['role'],
            notes=data.get('notes'),
            otp=data.get('otp')
        )
        # Fetch updated order
        order = fetch_one("SELECT * FROM orders WHERE order_id = %s;", (order_id,))
        return jsonify({'status': 'success', 'order': order, **res}), 200
    except Exception as e:
        return jsonify({'error': 'Transition Failed', 'message': str(e)}), 400
