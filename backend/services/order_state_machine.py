"""
backend/services/order_state_machine.py
Central Order State Machine, Transition Validator, and Audit Logger for AgriSmart Connect.
Enforces strict role permissions, atomic event logging in order_events,
and multi-hub logistics side-effects.
"""

import random
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from services.inventory_service import complete_sale, release_reservation
    from services.hub_routing_service import determine_order_route
    from services.notification_service import notify_order_status_event
    from services.settlement_service import execute_order_settlements
    from config import Config
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.services.inventory_service import complete_sale, release_reservation
    from backend.services.hub_routing_service import determine_order_route
    from backend.services.notification_service import notify_order_status_event
    from backend.services.settlement_service import execute_order_settlements
    from backend.config import Config

logger = logging.getLogger('agrismart.statemachine')

# Canonical State Constants
STATE_PAYMENT_PENDING         = 'PAYMENT_PENDING'
STATE_PAYMENT_SUCCESS         = 'PAYMENT_SUCCESS'
STATE_ORDER_CONFIRMED         = 'ORDER_CONFIRMED'
STATE_FARMER_ACCEPTED         = 'FARMER_ACCEPTED'
STATE_FARMER_PREPARING        = 'FARMER_PREPARING'
STATE_READY_FOR_PICKUP        = 'READY_FOR_PICKUP'
STATE_PICKUP_ASSIGNED         = 'PICKUP_ASSIGNED'
STATE_PICKED_UP               = 'PICKED_UP'
STATE_IN_TRANSIT_TO_HUB       = 'IN_TRANSIT_TO_HUB'
STATE_ARRIVED_AT_HUB          = 'ARRIVED_AT_HUB'
STATE_HUB_QC                  = 'HUB_QC'
STATE_HUB_ACCEPTED            = 'HUB_ACCEPTED'
STATE_HUB_TRANSFER_REQUIRED   = 'HUB_TRANSFER_REQUIRED'
STATE_IN_TRANSIT_TO_NEXT_HUB  = 'IN_TRANSIT_TO_NEXT_HUB'
STATE_ARRIVED_AT_NEXT_HUB     = 'ARRIVED_AT_NEXT_HUB'
STATE_ASSIGNED_TO_DELIVERY    = 'ASSIGNED_TO_DELIVERY'
STATE_OUT_FOR_DELIVERY        = 'OUT_FOR_DELIVERY'
STATE_DELIVERY_OTP_VERIFICATION = 'DELIVERY_OTP_VERIFICATION'
STATE_DELIVERED               = 'DELIVERED'
STATE_SETTLEMENT_PROCESSING   = 'SETTLEMENT_PROCESSING'
STATE_SETTLED                 = 'SETTLED'

# Exception States
STATE_PAYMENT_FAILED          = 'PAYMENT_FAILED'
STATE_FARMER_REJECTED         = 'FARMER_REJECTED'
STATE_OUT_OF_STOCK            = 'OUT_OF_STOCK'
STATE_ORDER_CANCELLED         = 'ORDER_CANCELLED'
STATE_PICKUP_FAILED           = 'PICKUP_FAILED'
STATE_QC_FAILED               = 'QC_FAILED'
STATE_HUB_REJECTED            = 'HUB_REJECTED'
STATE_TRANSFER_FAILED         = 'TRANSFER_FAILED'
STATE_DELIVERY_FAILED         = 'DELIVERY_FAILED'
STATE_CUSTOMER_UNAVAILABLE    = 'CUSTOMER_UNAVAILABLE'
STATE_REFUND_PENDING          = 'REFUND_PENDING'
STATE_REFUNDED                = 'REFUNDED'
STATE_PAYOUT_FAILED           = 'PAYOUT_FAILED'

# Legacy status aliases mapping to Canonical States
STATUS_NORMALIZE_MAP = {
    'placed': STATE_PAYMENT_PENDING,
    'confirmed': STATE_ORDER_CONFIRMED,
    'farmer_assigned': STATE_FARMER_ACCEPTED,
    'collecting': STATE_IN_TRANSIT_TO_HUB,
    'at_hub': STATE_ARRIVED_AT_HUB,
    'quality_checked': STATE_HUB_ACCEPTED,
    'packed': STATE_ASSIGNED_TO_DELIVERY,
    'out_for_delivery': STATE_OUT_FOR_DELIVERY,
    'delivered': STATE_DELIVERED,
    'cancelled': STATE_ORDER_CANCELLED,
}

# Allowed Next Transitions
VALID_TRANSITIONS: Dict[str, List[str]] = {
    STATE_PAYMENT_PENDING: [
        STATE_PAYMENT_SUCCESS, STATE_PAYMENT_FAILED, STATE_ORDER_CANCELLED
    ],
    STATE_PAYMENT_SUCCESS: [
        STATE_ORDER_CONFIRMED, STATE_REFUND_PENDING
    ],
    STATE_ORDER_CONFIRMED: [
        STATE_FARMER_ACCEPTED, STATE_FARMER_REJECTED, STATE_OUT_OF_STOCK, STATE_ORDER_CANCELLED
    ],
    STATE_FARMER_ACCEPTED: [
        STATE_FARMER_PREPARING, STATE_READY_FOR_PICKUP, STATE_ORDER_CANCELLED
    ],
    STATE_FARMER_PREPARING: [
        STATE_READY_FOR_PICKUP, STATE_OUT_OF_STOCK, STATE_ORDER_CANCELLED
    ],
    STATE_READY_FOR_PICKUP: [
        STATE_PICKUP_ASSIGNED, STATE_PICKED_UP, STATE_PICKUP_FAILED, STATE_ORDER_CANCELLED
    ],
    STATE_PICKUP_ASSIGNED: [
        STATE_PICKED_UP, STATE_PICKUP_FAILED, STATE_ORDER_CANCELLED
    ],
    STATE_PICKED_UP: [
        STATE_IN_TRANSIT_TO_HUB, STATE_ARRIVED_AT_HUB, STATE_PICKUP_FAILED
    ],
    STATE_IN_TRANSIT_TO_HUB: [
        STATE_ARRIVED_AT_HUB, STATE_PICKUP_FAILED
    ],
    STATE_ARRIVED_AT_HUB: [
        STATE_HUB_QC, STATE_HUB_ACCEPTED, STATE_HUB_REJECTED
    ],
    STATE_HUB_QC: [
        STATE_HUB_ACCEPTED, STATE_QC_FAILED, STATE_HUB_REJECTED
    ],
    STATE_HUB_ACCEPTED: [
        STATE_HUB_TRANSFER_REQUIRED, STATE_ASSIGNED_TO_DELIVERY, STATE_OUT_FOR_DELIVERY
    ],
    STATE_HUB_TRANSFER_REQUIRED: [
        STATE_IN_TRANSIT_TO_NEXT_HUB, STATE_TRANSFER_FAILED
    ],
    STATE_IN_TRANSIT_TO_NEXT_HUB: [
        STATE_ARRIVED_AT_NEXT_HUB, STATE_TRANSFER_FAILED
    ],
    STATE_ARRIVED_AT_NEXT_HUB: [
        STATE_HUB_QC, STATE_HUB_ACCEPTED, STATE_ASSIGNED_TO_DELIVERY, STATE_OUT_FOR_DELIVERY
    ],
    STATE_ASSIGNED_TO_DELIVERY: [
        STATE_OUT_FOR_DELIVERY, STATE_DELIVERY_FAILED
    ],
    STATE_OUT_FOR_DELIVERY: [
        STATE_DELIVERY_OTP_VERIFICATION, STATE_DELIVERED, STATE_DELIVERY_FAILED, STATE_CUSTOMER_UNAVAILABLE
    ],
    STATE_DELIVERY_OTP_VERIFICATION: [
        STATE_DELIVERED, STATE_DELIVERY_FAILED, STATE_CUSTOMER_UNAVAILABLE
    ],
    STATE_DELIVERED: [
        STATE_SETTLEMENT_PROCESSING, STATE_SETTLED
    ],
    STATE_SETTLEMENT_PROCESSING: [
        STATE_SETTLED, STATE_PAYOUT_FAILED
    ],
    STATE_SETTLED: [],
    # Exception Transitions
    STATE_FARMER_REJECTED: [STATE_REFUND_PENDING, STATE_REFUNDED],
    STATE_OUT_OF_STOCK: [STATE_REFUND_PENDING, STATE_REFUNDED],
    STATE_ORDER_CANCELLED: [STATE_REFUND_PENDING, STATE_REFUNDED],
    STATE_QC_FAILED: [STATE_REFUND_PENDING, STATE_REFUNDED],
    STATE_HUB_REJECTED: [STATE_REFUND_PENDING, STATE_REFUNDED],
    STATE_TRANSFER_FAILED: [STATE_IN_TRANSIT_TO_NEXT_HUB, STATE_REFUND_PENDING],
    STATE_DELIVERY_FAILED: [STATE_OUT_FOR_DELIVERY, STATE_REFUND_PENDING],
    STATE_CUSTOMER_UNAVAILABLE: [STATE_OUT_FOR_DELIVERY, STATE_REFUND_PENDING],
    STATE_REFUND_PENDING: [STATE_REFUNDED],
    STATE_REFUNDED: [],
    STATE_PAYOUT_FAILED: [STATE_SETTLEMENT_PROCESSING, STATE_SETTLED],
    STATE_PAYMENT_FAILED: []
}

# Role Authorization Map for Transitions
ROLE_PERMISSIONS: Dict[str, List[str]] = {
    STATE_PAYMENT_SUCCESS: ['admin', 'gateway', 'system', 'consumer', 'retailer', 'restaurant'],
    STATE_ORDER_CONFIRMED: ['admin', 'system', 'gateway'],
    STATE_FARMER_ACCEPTED: ['farmer', 'admin'],
    STATE_FARMER_REJECTED: ['farmer', 'admin'],
    STATE_FARMER_PREPARING: ['farmer', 'admin'],
    STATE_READY_FOR_PICKUP: ['farmer', 'admin'],
    STATE_PICKUP_ASSIGNED: ['admin', 'hub_operator', 'hub_staff', 'hub_manager', 'delivery_partner'],
    STATE_PICKED_UP: ['delivery_partner', 'admin'],
    STATE_IN_TRANSIT_TO_HUB: ['delivery_partner', 'admin'],
    STATE_ARRIVED_AT_HUB: ['delivery_partner', 'hub_operator', 'hub_staff', 'hub_manager', 'admin'],
    STATE_HUB_QC: ['hub_operator', 'hub_staff', 'hub_manager', 'admin'],
    STATE_HUB_ACCEPTED: ['hub_operator', 'hub_staff', 'hub_manager', 'admin'],
    STATE_HUB_REJECTED: ['hub_operator', 'hub_staff', 'hub_manager', 'admin'],
    STATE_HUB_TRANSFER_REQUIRED: ['hub_operator', 'hub_staff', 'hub_manager', 'admin', 'system'],
    STATE_IN_TRANSIT_TO_NEXT_HUB: ['delivery_partner', 'hub_operator', 'hub_staff', 'hub_manager', 'admin'],
    STATE_ARRIVED_AT_NEXT_HUB: ['delivery_partner', 'hub_operator', 'hub_staff', 'hub_manager', 'admin'],
    STATE_ASSIGNED_TO_DELIVERY: ['hub_operator', 'hub_staff', 'hub_manager', 'admin'],
    STATE_OUT_FOR_DELIVERY: ['delivery_partner', 'hub_operator', 'hub_staff', 'admin'],
    STATE_DELIVERY_OTP_VERIFICATION: ['delivery_partner', 'admin'],
    STATE_DELIVERED: ['delivery_partner', 'admin', 'system'],
    STATE_SETTLEMENT_PROCESSING: ['admin', 'system'],
    STATE_SETTLED: ['admin', 'system'],
    STATE_ORDER_CANCELLED: ['consumer', 'retailer', 'restaurant', 'admin', 'farmer'],
    STATE_REFUND_PENDING: ['admin', 'system'],
    STATE_REFUNDED: ['admin', 'system', 'gateway']
}


def canonical_status(status_str: str) -> str:
    """Normalize status string to canonical uppercase state."""
    if not status_str:
        return STATE_PAYMENT_PENDING
    s = status_str.strip()
    # Check lowercase alias
    if s.lower() in STATUS_NORMALIZE_MAP:
        return STATUS_NORMALIZE_MAP[s.lower()]
    return s.upper()


def generate_delivery_otp() -> str:
    """Generate secure 4-digit Delivery Handshake OTP."""
    return f"{random.randint(1000, 9999)}"


def transition_order_state(
    order_id: int,
    target_status: str,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    notes: Optional[str] = None,
    location: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    otp: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Execute validated order state transition:
    1. Lock order row.
    2. Check current status and validate transition path.
    3. Verify actor role permissions.
    4. Validate OTP if transitioning to DELIVERED.
    5. Update order record, delivery record, inventory.
    6. Record immutable audit log in order_events.
    7. Emit notifications to relevant actors.
    """
    target = canonical_status(target_status)
    role_norm = (actor_role or 'system').lower()
    if role_norm == 'hub_operator':
        role_norm = 'hub_staff'

    with get_db_cursor(commit=True) as cur:
        # 1. Fetch current order with row lock
        cur.execute("""
            SELECT o.*, b.user_id AS buyer_user_id,
                   d.delivery_id, d.delivery_partner_id,
                   h1.hub_name AS src_hub_name, h2.hub_name AS dst_hub_name
            FROM orders o
            JOIN buyers b ON o.buyer_id = b.buyer_id
            LEFT JOIN deliveries d ON o.order_id = d.order_id
            LEFT JOIN hubs h1 ON o.source_hub_id = h1.hub_id
            LEFT JOIN hubs h2 ON o.destination_hub_id = h2.hub_id
            WHERE o.order_id = %s
            FOR UPDATE;
        """, (order_id,))
        order = cur.fetchone()
        if not order:
            raise ValueError(f"Order #{order_id} not found.")

        current = canonical_status(order['order_status'])

        # Idempotency: if already at target status, return success
        if current == target:
            logger.info(f"[State Machine] Order #{order_id} already in status {target}. No-op.")
            return {
                'success': True,
                'message': f"Order #{order_id} is already in status '{target}'.",
                'order_id': order_id,
                'current_status': target
            }

        # 2. Validate state transition allowed
        allowed_targets = VALID_TRANSITIONS.get(current, [])
        # In demo mode, admin / system or forced progression allows advancing sequentially
        is_admin_or_system = role_norm in ('admin', 'system')
        if target not in allowed_targets and not is_admin_or_system:
            raise ValueError(
                f"Invalid order state transition from '{current}' to '{target}'. "
                f"Allowed next states: {', '.join(allowed_targets) if allowed_targets else 'None (Terminal State)'}"
            )

        # 3. Verify actor role permission
        required_roles = ROLE_PERMISSIONS.get(target, ['admin', 'system'])
        if role_norm not in required_roles and not is_admin_or_system:
            # Check hub staff aliases
            if 'hub_staff' in required_roles and role_norm in ('hub_staff', 'hub_operator', 'hub_manager'):
                pass
            else:
                raise PermissionError(
                    f"User with role '{role_norm}' is not authorized to set order status to '{target}'. "
                    f"Authorized roles: {', '.join(required_roles)}"
                )

        # 4. OTP verification if finalizing delivery
        if target == STATE_DELIVERED:
            expected_otp = order.get('delivery_otp')
            if not expected_otp:
                # Fallback to generated OTP from delivery_id
                expected_otp = str((order.get('delivery_id', order_id) * 317 + 1234) % 9000 + 1000)

            # Check provided OTP
            provided_otp = str(otp or '').strip()
            if not is_admin_or_system:
                if not provided_otp:
                    raise ValueError(f"Delivery Handshake OTP is required to mark order delivered.")
                if provided_otp != expected_otp:
                    cur.execute("UPDATE orders SET delivery_otp_attempts = COALESCE(delivery_otp_attempts, 0) + 1 WHERE order_id = %s;", (order_id,))
                    raise ValueError(f"Invalid Delivery OTP code '{provided_otp}'. Please request code from customer.")

            cur.execute("UPDATE orders SET delivery_otp_verified = TRUE WHERE order_id = %s;", (order_id,))

        # 5. Side-effects execution per status
        # A. ORDER_CONFIRMED: Determine dynamic hub route
        if target in (STATE_ORDER_CONFIRMED, STATE_PAYMENT_SUCCESS):
            cur.execute("UPDATE orders SET payment_status = 'paid' WHERE order_id = %s;", (order_id,))
            cur.execute("UPDATE payments SET payment_status = 'paid' WHERE order_id = %s;", (order_id,))
            
            # Find primary farmer from order_items
            cur.execute("SELECT farmer_id FROM order_items WHERE order_id = %s LIMIT 1;", (order_id,))
            fi = cur.fetchone()
            if fi:
                determine_order_route(
                    order_id=order_id,
                    farmer_id=fi['farmer_id'],
                    buyer_id=order['buyer_id'],
                    delivery_address=order['delivery_address'],
                    delivery_lat=float(order['delivery_latitude']) if order.get('delivery_latitude') else None,
                    delivery_lon=float(order['delivery_longitude']) if order.get('delivery_longitude') else None
                )

        # B. READY_FOR_PICKUP: Ensure delivery task is active and hub is assigned
        if target == STATE_READY_FOR_PICKUP:
            cur.execute("""
                UPDATE order_routes
                SET status = 'ASSIGNED'
                WHERE order_id = %s AND sequence_number = 1;
            """, (order_id,))
            cur.execute("""
                UPDATE deliveries
                SET status = 'assigned'
                WHERE order_id = %s;
            """, (order_id,))

        # C. PICKED_UP: Mark farm leg in transit
        if target == STATE_PICKED_UP:
            cur.execute("""
                UPDATE deliveries
                SET status = 'picked_up', pickup_time = CURRENT_TIMESTAMP
                WHERE order_id = %s;
            """, (order_id,))
            cur.execute("""
                UPDATE order_routes
                SET status = 'IN_TRANSIT', started_at = CURRENT_TIMESTAMP
                WHERE order_id = %s AND sequence_number = 1;
            """, (order_id,))

        # D. ARRIVED_AT_HUB: Mark farm leg completed
        if target == STATE_ARRIVED_AT_HUB:
            cur.execute("""
                UPDATE order_routes
                SET status = 'COMPLETED', arrived_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP
                WHERE order_id = %s AND sequence_number = 1;
            """, (order_id,))

        # E. HUB_ACCEPTED: Check if multi-hub transfer is needed
        if target == STATE_HUB_ACCEPTED:
            # Refresh order routing
            cur.execute("SELECT source_hub_id, destination_hub_id, requires_hub_transfer FROM orders WHERE order_id = %s;", (order_id,))
            route_meta = cur.fetchone()
            if route_meta and route_meta.get('requires_hub_transfer') and route_meta.get('source_hub_id') != route_meta.get('destination_hub_id'):
                target = STATE_HUB_TRANSFER_REQUIRED
                # Create transfer task if not exists
                cur.execute("""
                    INSERT INTO hub_transfers (order_id, source_hub_id, destination_hub_id, status)
                    VALUES (%s, %s, %s, 'TRANSFER_CREATED')
                    ON CONFLICT DO NOTHING;
                """, (order_id, route_meta['source_hub_id'], route_meta['destination_hub_id']))
                cur.execute("""
                    UPDATE order_routes
                    SET status = 'ASSIGNED'
                    WHERE order_id = %s AND sequence_number = 2;
                """, (order_id,))
            else:
                target = STATE_ASSIGNED_TO_DELIVERY

        # F. IN_TRANSIT_TO_NEXT_HUB
        if target == STATE_IN_TRANSIT_TO_NEXT_HUB:
            cur.execute("""
                UPDATE hub_transfers
                SET status = 'IN_TRANSIT', departure_time = CURRENT_TIMESTAMP
                WHERE order_id = %s;
            """, (order_id,))
            cur.execute("""
                UPDATE order_routes
                SET status = 'IN_TRANSIT', started_at = CURRENT_TIMESTAMP
                WHERE order_id = %s AND sequence_number = 2;
            """, (order_id,))

        # G. ARRIVED_AT_NEXT_HUB
        if target == STATE_ARRIVED_AT_NEXT_HUB:
            cur.execute("""
                UPDATE hub_transfers
                SET status = 'ARRIVED_DESTINATION_HUB', arrival_time = CURRENT_TIMESTAMP
                WHERE order_id = %s;
            """, (order_id,))
            cur.execute("""
                UPDATE order_routes
                SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
                WHERE order_id = %s AND sequence_number = 2;
            """, (order_id,))

        # H. OUT_FOR_DELIVERY: Generate OTP
        if target == STATE_OUT_FOR_DELIVERY:
            new_otp = generate_delivery_otp()
            cur.execute("""
                UPDATE orders
                SET delivery_otp = %s,
                    delivery_otp_expires_at = CURRENT_TIMESTAMP + INTERVAL '12 hours'
                WHERE order_id = %s;
            """, (new_otp, order_id))
            cur.execute("""
                UPDATE deliveries
                SET status = 'in_transit'
                WHERE order_id = %s;
            """, (order_id,))
            # Last-mile route leg
            cur.execute("""
                UPDATE order_routes
                SET status = 'IN_TRANSIT', started_at = CURRENT_TIMESTAMP
                WHERE order_id = %s AND route_type = 'HUB_TO_CUSTOMER';
            """, (order_id,))

        # I. DELIVERED: Execute sale completion and multi-party settlement ledger
        if target == STATE_DELIVERED:
            cur.execute("SELECT produce_id, quantity_kg FROM order_items WHERE order_id = %s;", (order_id,))
            items = cur.fetchall()
            for it in items:
                if it.get('produce_id'):
                    complete_sale(cur, it['produce_id'], float(it['quantity_kg']))

            cur.execute("""
                UPDATE deliveries
                SET status = 'delivered', delivery_time = CURRENT_TIMESTAMP
                WHERE order_id = %s;
            """, (order_id,))
            cur.execute("""
                UPDATE order_routes
                SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
                WHERE order_id = %s AND route_type = 'HUB_TO_CUSTOMER';
            """, (order_id,))

            # Generate multi-party settlements
            execute_order_settlements(cur, order_id)
            target = STATE_SETTLED

        # J. CANCELLATION & REJECTION: Release inventory
        if target in (STATE_ORDER_CANCELLED, STATE_FARMER_REJECTED, STATE_OUT_OF_STOCK, STATE_HUB_REJECTED):
            cur.execute("SELECT produce_id, quantity_kg FROM order_items WHERE order_id = %s;", (order_id,))
            items = cur.fetchall()
            for it in items:
                if it.get('produce_id'):
                    release_reservation(cur, it['produce_id'], float(it['quantity_kg']))

            cur.execute("UPDATE deliveries SET status = 'cancelled' WHERE order_id = %s;", (order_id,))
            cur.execute("UPDATE order_routes SET status = 'FAILED' WHERE order_id = %s;", (order_id,))

            # If payment was already collected, flag for refund
            if order.get('payment_status') == 'paid':
                target = STATE_REFUND_PENDING

        # Update order table
        cur.execute("""
            UPDATE orders
            SET order_status = %s,
                rejection_reason = COALESCE(%s, rejection_reason),
                cancellation_reason = COALESCE(%s, cancellation_reason),
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = %s;
        """, (
            target,
            notes if target in (STATE_FARMER_REJECTED, STATE_HUB_REJECTED, STATE_QC_FAILED) else None,
            notes if target == STATE_ORDER_CANCELLED else None,
            order_id
        ))

        # 6. Insert immutable audit record in order_events
        import json
        meta_json = json.dumps(metadata) if metadata else None
        cur.execute("""
            INSERT INTO order_events (
                order_id, previous_status, new_status, actor_id, actor_role,
                location, latitude, longitude, notes, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, timestamp;
        """, (
            order_id, current, target, actor_id, actor_role,
            location, latitude, longitude, notes, meta_json
        ))
        event = cur.fetchone()

    # 7. Post-commit notifications (outside lock)
    notify_order_status_event(
        order_id=order_id,
        new_status=target,
        hub_name=order.get('src_hub_name'),
        destination_hub_name=order.get('dst_hub_name'),
        notes=notes
    )

    logger.info(f"[State Machine] Order #{order_id} advanced from '{current}' to '{target}' by {actor_role} #{actor_id}.")

    return {
        'success': True,
        'order_id': order_id,
        'previous_status': current,
        'new_status': target,
        'event_id': event['id'],
        'timestamp': event['timestamp'].isoformat() if hasattr(event['timestamp'], 'isoformat') else str(event['timestamp'])
    }


def get_order_tracking_timeline(order_id: int) -> Dict[str, Any]:
    """
    Retrieve full tracking history, current state, dynamic routes, and delivery OTP for buyer/admin tracking.
    """
    order = fetch_one("""
        SELECT o.*, b.business_name, u.name AS buyer_name, u.phone AS buyer_phone,
               h1.hub_name AS source_hub_name, h1.district AS source_hub_district,
               h2.hub_name AS dest_hub_name, h2.district AS dest_hub_district,
               d.status AS delivery_status, d.tracking_reference,
               u_dp.name AS driver_name, u_dp.phone AS driver_phone
        FROM orders o
        JOIN buyers b ON o.buyer_id = b.buyer_id
        JOIN users u ON b.user_id = u.user_id
        LEFT JOIN hubs h1 ON o.source_hub_id = h1.hub_id
        LEFT JOIN hubs h2 ON o.destination_hub_id = h2.hub_id
        LEFT JOIN deliveries d ON o.order_id = d.order_id
        LEFT JOIN users u_dp ON d.delivery_partner_id = u_dp.user_id
        WHERE o.order_id = %s;
    """, (order_id,))

    if not order:
        return {}

    # Order Items
    items = fetch_all("""
        SELECT oi.*, c.crop_name, v.variety_name,
               fp.farm_name, u.name AS farmer_name, u.phone AS farmer_phone
        FROM order_items oi
        JOIN crops c ON oi.crop_id = c.crop_id
        LEFT JOIN varieties v ON oi.variety_id = v.variety_id
        JOIN farmer_profiles fp ON oi.farmer_id = fp.farmer_id
        JOIN users u ON fp.user_id = u.user_id
        WHERE oi.order_id = %s;
    """, (order_id,))

    # Order Events Timeline
    events = fetch_all("""
        SELECT oe.*, u.name AS actor_name
        FROM order_events oe
        LEFT JOIN users u ON oe.actor_id = u.user_id
        WHERE oe.order_id = %s
        ORDER BY oe.timestamp ASC;
    """, (order_id,))

    # Order Routes (Legs)
    routes = fetch_all("""
        SELECT r.*, 
               h_src.hub_name AS src_hub_name,
               h_dst.hub_name AS dst_hub_name
        FROM order_routes r
        LEFT JOIN hubs h_src ON r.source_hub_id = h_src.hub_id
        LEFT JOIN hubs h_dst ON r.destination_hub_id = h_dst.hub_id
        WHERE r.order_id = %s
        ORDER BY r.sequence_number ASC;
    """, (order_id,))

    # Settlements breakdown (if settled)
    settlements = fetch_all("""
        SELECT settlement_type, beneficiary_name, beneficiary_type, amount, status
        FROM settlements
        WHERE order_id = %s;
    """, (order_id,))

    return {
        'order': order,
        'items': items,
        'events': events,
        'routes': routes,
        'settlements': settlements,
        'is_multi_hub': bool(order.get('requires_hub_transfer')),
        'delivery_otp': order.get('delivery_otp')
    }
