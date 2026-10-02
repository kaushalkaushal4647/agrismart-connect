"""
routes/webhooks.py
Razorpay Webhook handler for AgriSmart Connect.

Security rules enforced:
  1. Raw request body is read FIRST, before any JSON parsing.
  2. X-Razorpay-Signature is verified using RAZORPAY_WEBHOOK_SECRET.
  3. Event ID (x-razorpay-event-id) is checked for idempotency.
  4. Duplicate events return 200 without re-processing.
  5. No stack traces exposed in responses.
"""

import json
import logging
from flask import Blueprint, request, jsonify

try:
    from database import get_db_cursor, fetch_one
    from services.razorpay_service import verify_webhook_signature
    from services.payment_service import confirm_payment_and_settle
    from services.razorpay_route import handle_transfer_webhook, handle_settlement_webhook
except ImportError:
    from backend.database import get_db_cursor, fetch_one
    from backend.services.razorpay_service import verify_webhook_signature
    from backend.services.payment_service import confirm_payment_and_settle
    from backend.services.razorpay_route import handle_transfer_webhook, handle_settlement_webhook

webhooks_bp = Blueprint('webhooks', __name__)
logger = logging.getLogger('agrismart.webhooks')


@webhooks_bp.route('/razorpay', methods=['POST'])
def razorpay_webhook():
    """
    Razorpay Webhook endpoint.

    CRITICAL:
      - Do NOT wrap request.data in try/except before signature check.
      - Raw body must be passed to verify_webhook_signature unchanged.
    """

    # ── STEP 1: Read raw body BEFORE anything else ─────────────────────────
    raw_body = request.get_data()

    # ── STEP 2: Verify webhook signature ───────────────────────────────────
    received_sig = request.headers.get('X-Razorpay-Signature', '')
    if not received_sig:
        logger.warning("[Webhook] Missing X-Razorpay-Signature header.")
        return jsonify({'error': 'Missing signature'}), 400

    if not verify_webhook_signature(raw_body, received_sig):
        logger.error("[Webhook] Signature verification FAILED — request rejected.")
        return jsonify({'error': 'Invalid signature'}), 400

    # ── STEP 3: Parse body ─────────────────────────────────────────────────
    try:
        event_data = json.loads(raw_body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"[Webhook] Failed to parse body: {e}")
        return jsonify({'error': 'Invalid JSON body'}), 400

    event_type = event_data.get('event', 'unknown')
    # Razorpay sends event ID in payload or as header
    event_id = (
        event_data.get('payload', {}).get('payment', {}).get('entity', {}).get('id')
        or request.headers.get('X-Razorpay-Event-Id')
        or event_data.get('created_at', '')
    )
    # Build a composite event_id for idempotency
    idempotency_key = f"{event_type}::{event_id}"

    logger.info(f"[Webhook] Received: event={event_type} key={idempotency_key}")

    # ── STEP 4: Idempotency check ──────────────────────────────────────────
    try:
        with get_db_cursor(commit=True) as cur:
            # Try to insert event record — unique constraint on event_id prevents duplicates
            cur.execute("""
                INSERT INTO webhook_events (event_id, event_type, payload, processed)
                VALUES (%s, %s, %s, FALSE)
                ON CONFLICT (event_id) DO NOTHING
                RETURNING id;
            """, (idempotency_key, event_type, json.dumps(event_data)))
            inserted = cur.fetchone()

            if not inserted:
                logger.info(f"[Webhook] DUPLICATE event {idempotency_key} — skipping.")
                return jsonify({'status': 'duplicate', 'message': 'Event already processed.'}), 200

            # ── STEP 5: Route to event handler ────────────────────────────
            try:
                _handle_event(cur, event_type, event_data)
                # Mark as processed
                cur.execute("""
                    UPDATE webhook_events SET processed = TRUE
                    WHERE event_id = %s;
                """, (idempotency_key,))
                logger.info(f"[Webhook] Successfully processed: {idempotency_key}")

            except Exception as handler_err:
                logger.error(
                    f"[Webhook] Handler error for {event_type}: {handler_err}",
                    exc_info=True
                )
                # Store error but don't expose it in response
                cur.execute("""
                    UPDATE webhook_events SET error_msg = %s
                    WHERE event_id = %s;
                """, (str(handler_err)[:500], idempotency_key))
                # Return 200 so Razorpay doesn't retry on handler bugs
                return jsonify({'status': 'error', 'message': 'Handler failed, logged.'}), 200

    except Exception as e:
        logger.error(f"[Webhook] Database error: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'Database error'}), 500

    return jsonify({'status': 'success', 'event': event_type}), 200


def _handle_event(cur, event_type: str, event_data: dict):
    """Route webhook event to the appropriate handler."""

    payment_entity = (
        event_data.get('payload', {})
        .get('payment', {})
        .get('entity', {})
    )

    if event_type in ('payment.authorized', 'payment.captured'):
        _handle_payment_captured(cur, payment_entity)

    elif event_type == 'payment.failed':
        _handle_payment_failed(cur, payment_entity)

    elif event_type in ('refund.processed', 'refund.failed'):
        _handle_refund_event(cur, event_type, event_data)

    elif event_type in ('transfer.processed', 'transfer.failed'):
        handle_transfer_webhook(event_data)

    elif event_type == 'settlement.processed':
        handle_settlement_webhook(event_data)

    else:
        logger.info(f"[Webhook] Unhandled event type: {event_type} — no action taken.")


def _handle_payment_captured(cur, payment_entity: dict):
    """Handle payment.authorized / payment.captured events."""
    razorpay_payment_id = payment_entity.get('id', '')
    razorpay_order_id   = payment_entity.get('order_id', '')
    amount_paise        = int(payment_entity.get('amount', 0))
    status              = payment_entity.get('status', '')

    if not razorpay_payment_id or not razorpay_order_id:
        logger.warning("[Webhook] payment.captured missing IDs — skipping.")
        return

    # Only process CAPTURED or AUTHORIZED payments
    if status not in ('captured', 'authorized'):
        logger.info(f"[Webhook] Payment {razorpay_payment_id} status={status} — skipping.")
        return

    # Map razorpay_order_id → internal order_id
    cur.execute("""
        SELECT order_id FROM razorpay_orders
        WHERE razorpay_order_id = %s;
    """, (razorpay_order_id,))
    row = cur.fetchone()
    if not row:
        logger.warning(
            f"[Webhook] razorpay_order_id={razorpay_order_id} not found in razorpay_orders."
        )
        return

    internal_order_id = row['order_id']

    # Check if already confirmed (idempotent guard)
    cur.execute("""
        SELECT payment_status FROM orders WHERE order_id = %s;
    """, (internal_order_id,))
    order_row = cur.fetchone()
    if order_row and order_row['payment_status'] == 'paid':
        logger.info(
            f"[Webhook] Order #{internal_order_id} already paid — skipping duplicate capture."
        )
        return

    result = confirm_payment_and_settle(
        cur=cur,
        internal_order_id=internal_order_id,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_order_id=razorpay_order_id,
        razorpay_signature='',  # Webhook doesn't carry checkout signature
        amount_paise=amount_paise
    )
    logger.info(
        f"[Webhook] Order #{internal_order_id} confirmed via webhook: {result}"
    )


def _handle_payment_failed(cur, payment_entity: dict):
    """Handle payment.failed event."""
    razorpay_payment_id = payment_entity.get('id', '')
    razorpay_order_id   = payment_entity.get('order_id', '')
    error_desc          = payment_entity.get('error_description', 'Payment failed')

    logger.warning(
        f"[Webhook] Payment FAILED: {razorpay_payment_id} order={razorpay_order_id} "
        f"reason={error_desc}"
    )

    # Look up our order
    cur.execute("""
        SELECT order_id FROM razorpay_orders
        WHERE razorpay_order_id = %s;
    """, (razorpay_order_id,))
    row = cur.fetchone()
    if not row:
        return

    internal_order_id = row['order_id']

    # Update razorpay_payments if record exists
    cur.execute("""
        INSERT INTO razorpay_payments (
            order_id, razorpay_order_id, razorpay_payment_id,
            amount_paise, status, failure_reason
        )
        VALUES (%s, %s, %s, 0, 'FAILED', %s)
        ON CONFLICT (razorpay_payment_id) DO UPDATE
            SET status = 'FAILED', failure_reason = EXCLUDED.failure_reason, updated_at = NOW();
    """, (internal_order_id, razorpay_order_id, razorpay_payment_id, error_desc))

    # Update razorpay_orders
    cur.execute("""
        UPDATE razorpay_orders SET status = 'ATTEMPTED', updated_at = NOW()
        WHERE order_id = %s;
    """, (internal_order_id,))


def _handle_refund_event(cur, event_type: str, event_data: dict):
    """Handle refund.processed / refund.failed events."""
    refund_entity = (
        event_data.get('payload', {})
        .get('refund', {})
        .get('entity', {})
    )
    razorpay_refund_id  = refund_entity.get('id', '')
    razorpay_payment_id = refund_entity.get('payment_id', '')
    new_status          = 'PROCESSED' if event_type == 'refund.processed' else 'FAILED'

    cur.execute("""
        UPDATE refunds
        SET status = %s, razorpay_refund_id = %s, updated_at = NOW()
        WHERE razorpay_payment_id = %s AND status NOT IN ('PROCESSED');
    """, (new_status, razorpay_refund_id, razorpay_payment_id))

    logger.info(
        f"[Webhook] Refund {event_type}: refund_id={razorpay_refund_id} "
        f"payment={razorpay_payment_id} status={new_status}"
    )
