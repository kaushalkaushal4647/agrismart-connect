"""
backend/services/notification_service.py
Real-time In-App Notification System for AgriSmart Connect.
Generates dynamic notifications for Farmers, Buyers, Delivery Partners, and Hub Operators.
"""

import logging
from typing import Dict, Any, List, Optional

try:
    from database import fetch_all, fetch_one, get_db_cursor
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor

logger = logging.getLogger('agrismart.notifications')


def create_notification(
    user_id: int,
    title: str,
    message: str,
    notif_type: str = 'order_update',
    order_id: Optional[int] = None
) -> Dict[str, Any]:
    """Insert a new user notification."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO notifications (user_id, title, message, type, order_id, is_read, created_at)
                VALUES (%s, %s, %s, %s, %s, FALSE, CURRENT_TIMESTAMP)
                RETURNING notification_id, user_id, title, message, type, order_id, is_read, created_at;
            """, (user_id, title, message, notif_type, order_id))
            notif = dict(cur.fetchone())
            logger.info(f"[Notification] User #{user_id}: {title}")
            return notif
    except Exception as e:
        logger.error(f"[Notification] Failed to create notification: {e}", exc_info=True)
        return {}


def notify_order_status_event(
    order_id: int,
    new_status: str,
    hub_name: Optional[str] = None,
    destination_hub_name: Optional[str] = None,
    notes: Optional[str] = None
) -> None:
    """
    Trigger notifications to appropriate actors (buyer, farmer, hub staff, driver)
    based on the state machine event.
    """
    try:
        # Fetch buyer and farmer user IDs
        order = fetch_one("""
            SELECT o.order_id, o.delivery_otp, b.user_id AS buyer_user_id,
                   h1.hub_name AS src_hub_name, h2.hub_name AS dst_hub_name,
                   d.delivery_partner_id
            FROM orders o
            JOIN buyers b ON o.buyer_id = b.buyer_id
            LEFT JOIN hubs h1 ON o.source_hub_id = h1.hub_id
            LEFT JOIN hubs h2 ON o.destination_hub_id = h2.hub_id
            LEFT JOIN deliveries d ON o.order_id = d.order_id
            WHERE o.order_id = %s;
        """, (order_id,))

        if not order:
            return

        buyer_user_id = order['buyer_user_id']
        driver_user_id = order.get('delivery_partner_id')
        active_hub = hub_name or order.get('src_hub_name') or 'Regional Agro Hub'
        dest_hub = destination_hub_name or order.get('dst_hub_name') or 'Destination Hub'

        # Fetch farmers associated with this order
        farmers = fetch_all("""
            SELECT DISTINCT fp.user_id AS farmer_user_id
            FROM order_items oi
            JOIN farmer_profiles fp ON oi.farmer_id = fp.farmer_id
            WHERE oi.order_id = %s;
        """, (order_id,))

        # Notification templates based on user requirement
        if new_status in ('PAYMENT_SUCCESS', 'ORDER_CONFIRMED', 'confirmed'):
            create_notification(
                user_id=buyer_user_id,
                title="Payment Successful",
                message=f"Payment received! Your order #{order_id} has been confirmed.",
                notif_type="order_confirmed",
                order_id=order_id
            )
            for f in farmers:
                create_notification(
                    user_id=f['farmer_user_id'],
                    title="New Order Received",
                    message=f"New purchase order #{order_id} received for your harvest. Please review and accept.",
                    notif_type="farmer_order",
                    order_id=order_id
                )

        elif new_status in ('FARMER_ACCEPTED', 'farmer_accepted'):
            create_notification(
                user_id=buyer_user_id,
                title="Order Accepted by Farmer",
                message=f"The farmer has accepted your order #{order_id} and is preparing the harvest.",
                notif_type="order_accepted",
                order_id=order_id
            )

        elif new_status in ('FARMER_REJECTED', 'farmer_rejected'):
            create_notification(
                user_id=buyer_user_id,
                title="Order Rejected by Farmer",
                message=f"Your order #{order_id} could not be fulfilled by the farmer. A refund has been automatically initiated.",
                notif_type="order_refund",
                order_id=order_id
            )

        elif new_status in ('FARMER_PREPARING', 'farmer_preparing'):
            create_notification(
                user_id=buyer_user_id,
                title="Harvest Preparation in Progress",
                message=f"Farmer is packaging and grading your produce for order #{order_id}.",
                notif_type="order_preparing",
                order_id=order_id
            )

        elif new_status in ('READY_FOR_PICKUP', 'ready_for_pickup'):
            create_notification(
                user_id=buyer_user_id,
                title="Order Ready for Farm Pickup",
                message=f"Order #{order_id} is packaged at the farm and ready for logistics pickup.",
                notif_type="ready_pickup",
                order_id=order_id
            )

        elif new_status in ('PICKED_UP', 'picked_up'):
            create_notification(
                user_id=buyer_user_id,
                title="Produce Picked Up from Farm",
                message=f"Logistics partner has picked up your produce for order #{order_id}.",
                notif_type="order_picked_up",
                order_id=order_id
            )

        elif new_status in ('ARRIVED_AT_HUB', 'arrived_at_hub'):
            create_notification(
                user_id=buyer_user_id,
                title="Arrived at Collection Hub",
                message=f"Your order #{order_id} has arrived at {active_hub} for quality inspection.",
                notif_type="hub_arrival",
                order_id=order_id
            )

        elif new_status in ('HUB_ACCEPTED', 'hub_accepted'):
            create_notification(
                user_id=buyer_user_id,
                title="Quality Check Passed",
                message=f"Your order #{order_id} passed rigorous quality grading at {active_hub}.",
                notif_type="hub_qc_pass",
                order_id=order_id
            )

        elif new_status in ('HUB_TRANSFER_REQUIRED', 'IN_TRANSIT_TO_NEXT_HUB'):
            create_notification(
                user_id=buyer_user_id,
                title="Inter-Hub Transfer",
                message=f"Your order #{order_id} is moving from {active_hub} to {dest_hub}.",
                notif_type="hub_transfer",
                order_id=order_id
            )

        elif new_status in ('ARRIVED_AT_NEXT_HUB',):
            create_notification(
                user_id=buyer_user_id,
                title="Arrived at Destination Hub",
                message=f"Your order #{order_id} has arrived at {dest_hub} for last-mile sorting.",
                notif_type="dest_hub_arrival",
                order_id=order_id
            )

        elif new_status in ('OUT_FOR_DELIVERY', 'out_for_delivery'):
            otp_str = order.get('delivery_otp') or "1234"
            create_notification(
                user_id=buyer_user_id,
                title="Out for Delivery",
                message=f"Your order #{order_id} is out for delivery! Give Handshake OTP '{otp_str}' to the driver upon delivery.",
                notif_type="out_for_delivery",
                order_id=order_id
            )

        elif new_status in ('DELIVERED', 'delivered'):
            create_notification(
                user_id=buyer_user_id,
                title="Order Delivered",
                message=f"Your order #{order_id} has been delivered successfully. Enjoy fresh harvest!",
                notif_type="order_delivered",
                order_id=order_id
            )
            for f in farmers:
                create_notification(
                    user_id=f['farmer_user_id'],
                    title="Harvest Delivered & Payout Processing",
                    message=f"Produce from order #{order_id} was successfully delivered. Payout settlement initiated.",
                    notif_type="payout_settlement",
                    order_id=order_id
                )
            if driver_user_id:
                create_notification(
                    user_id=driver_user_id,
                    title="Trip Completed & Earning Credited",
                    message=f"Delivery for order #{order_id} marked complete. Trip earnings added to your ledger.",
                    notif_type="driver_earning",
                    order_id=order_id
                )

        elif new_status in ('ORDER_CANCELLED', 'cancelled'):
            create_notification(
                user_id=buyer_user_id,
                title="Order Cancelled",
                message=f"Order #{order_id} was cancelled. {notes or ''}",
                notif_type="order_cancelled",
                order_id=order_id
            )

    except Exception as e:
        logger.error(f"[Notification] Error in notify_order_status_event: {e}", exc_info=True)


def get_user_notifications(user_id: int, limit: int = 30) -> List[Dict[str, Any]]:
    """Retrieve in-app notifications for user, ordered newest first."""
    sql = """
        SELECT notification_id, title, message, type, order_id, is_read, created_at
        FROM notifications
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s;
    """
    return fetch_all(sql, (user_id, limit))


def mark_notification_read(notification_id: int, user_id: int) -> bool:
    """Mark a notification as read."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE notifications
            SET is_read = TRUE
            WHERE notification_id = %s AND user_id = %s;
        """, (notification_id, user_id))
        return cur.rowcount > 0


def mark_all_notifications_read(user_id: int) -> int:
    """Mark all unread notifications as read for a user."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE notifications
            SET is_read = TRUE
            WHERE user_id = %s AND is_read = FALSE;
        """, (user_id,))
        return cur.rowcount
