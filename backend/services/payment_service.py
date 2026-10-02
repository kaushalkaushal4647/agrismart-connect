"""
payment_service.py
Post-payment business logic for AgriSmart Connect.
Called after Razorpay signature is verified or webhook payment.captured fires.
Uses PostgreSQL transactions — all-or-nothing.
"""

import logging
from decimal import Decimal

logger = logging.getLogger('agrismart.payment_service')


def _get_commission_percent():
    try:
        from config import Config
    except ImportError:
        from backend.config import Config
    return float(getattr(Config, 'PLATFORM_COMMISSION_PERCENT', 10.0))


def confirm_payment_and_settle(cur, internal_order_id: int,
                                razorpay_payment_id: str,
                                razorpay_order_id: str,
                                razorpay_signature: str,
                                amount_paise: int) -> dict:
    """
    Execute all DB updates after a payment is verified/captured.
    Must be called inside an open psycopg cursor with commit=True transaction.

    Steps:
      1. Update razorpay_orders status → PAID
      2. Upsert razorpay_payments row with CAPTURED status
      3. Update payments table (existing row) with Razorpay IDs + settlement calc
      4. Update orders.payment_status → 'paid', order_status → 'confirmed'
      5. Reduce inventory exactly once (idempotent via CAPTURED status check)
      6. Build farmer settlement breakdown (SIMULATED in test mode)
      7. Insert transfers rows per farmer (SIMULATED)
      8. Return summary dict

    Returns:
        dict with keys: order_id, razorpay_payment_id, gross_inr,
                        commission_inr, farmer_inr, settlement_status
    """
    commission_pct = _get_commission_percent()
    gross_inr = round(amount_paise / 100, 2)
    commission_inr = round(gross_inr * commission_pct / 100, 2)
    farmer_inr = round(gross_inr - commission_inr, 2)

    # ── 1. Update razorpay_orders ──────────────────────────────────────────
    cur.execute("""
        UPDATE razorpay_orders
        SET status = 'PAID', updated_at = NOW()
        WHERE order_id = %s AND razorpay_order_id = %s;
    """, (internal_order_id, razorpay_order_id))

    # ── 2. Upsert razorpay_payments ────────────────────────────────────────
    cur.execute("""
        INSERT INTO razorpay_payments (
            order_id, razorpay_order_id, razorpay_payment_id,
            razorpay_signature, amount_paise, status
        )
        VALUES (%s, %s, %s, %s, %s, 'CAPTURED')
        ON CONFLICT (razorpay_payment_id) DO UPDATE
            SET status = 'CAPTURED', updated_at = NOW();
    """, (internal_order_id, razorpay_order_id,
          razorpay_payment_id, razorpay_signature, amount_paise))

    # ── 3. Update existing payments ledger row ─────────────────────────────
    cur.execute("""
        UPDATE payments SET
            razorpay_order_id   = %s,
            razorpay_payment_id = %s,
            razorpay_signature  = %s,
            payment_status      = 'paid',
            payment_method      = 'Razorpay',
            gross_amount        = %s,
            commission_percent  = %s,
            commission_amount   = %s,
            farmer_amount       = %s,
            settlement_status   = 'SIMULATED',
            transaction_reference = %s
        WHERE order_id = %s;
    """, (
        razorpay_order_id, razorpay_payment_id, razorpay_signature,
        gross_inr, commission_pct, commission_inr, farmer_inr,
        razorpay_payment_id, internal_order_id
    ))

    # ── 4. Update order statuses ───────────────────────────────────────────
    cur.execute("""
        UPDATE orders
        SET payment_status = 'paid',
            order_status   = 'confirmed'
        WHERE order_id = %s
          AND payment_status != 'paid';  -- idempotent guard
    """, (internal_order_id,))

    # ── 5. Reduce inventory (idempotent) ───────────────────────────────────
    # Only reduce if order was NOT previously confirmed (guard against duplicate webhooks)
    cur.execute("""
        SELECT COUNT(*) AS already_settled
        FROM transfers
        WHERE order_id = %s;
    """, (internal_order_id,))
    row = cur.fetchone()
    already_settled = (row['already_settled'] if row else 0) > 0

    if not already_settled:
        # Fetch order items and reduce produce inventory
        cur.execute("""
            SELECT oi.produce_id, oi.quantity_kg, oi.farmer_id, oi.subtotal
            FROM order_items oi
            WHERE oi.order_id = %s AND oi.produce_id IS NOT NULL;
        """, (internal_order_id,))
        items = cur.fetchall()

        for item in items:
            produce_id   = item['produce_id']
            qty          = float(item['quantity_kg'])
            farmer_id    = item['farmer_id']
            item_gross   = float(item['subtotal'])
            item_comm    = round(item_gross * commission_pct / 100, 2)
            item_farmer  = round(item_gross - item_comm, 2)

            # Atomically move reserved → sold (prevent double-deduction)
            cur.execute("""
                UPDATE farmer_produce
                SET reserved_quantity_kg = reserved_quantity_kg - %s,
                    sold_quantity_kg     = sold_quantity_kg     + %s,
                    updated_at           = NOW()
                WHERE produce_id = %s
                  AND reserved_quantity_kg >= %s;
            """, (qty, qty, produce_id, qty))

            # ── 6 & 7. Insert SIMULATED transfer per farmer ────────────────
            cur.execute("""
                INSERT INTO transfers (
                    razorpay_payment_id, order_id, farmer_id,
                    amount_paise, status, settlement_status
                )
                VALUES (%s, %s, %s, %s, 'SIMULATED', 'SIMULATED')
                ON CONFLICT DO NOTHING;
            """, (
                razorpay_payment_id, internal_order_id, farmer_id,
                int(item_farmer * 100)
            ))

            logger.info(
                f"[PaymentService] Farmer {farmer_id} settlement: "
                f"gross=₹{item_gross} commission=₹{item_comm} "
                f"farmer=₹{item_farmer} [SIMULATED]"
            )

    logger.info(
        f"[PaymentService] Order #{internal_order_id} CONFIRMED — "
        f"gross=₹{gross_inr} commission=₹{commission_inr} "
        f"farmer_total=₹{farmer_inr} settlement=SIMULATED"
    )

    return {
        'order_id':             internal_order_id,
        'razorpay_payment_id':  razorpay_payment_id,
        'gross_inr':            gross_inr,
        'commission_pct':       commission_pct,
        'commission_inr':       commission_inr,
        'farmer_inr':           farmer_inr,
        'settlement_status':    'SIMULATED',
        'already_settled':      already_settled
    }
