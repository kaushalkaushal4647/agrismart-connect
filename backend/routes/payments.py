"""
routes/payments.py
Payment routes for AgriSmart Connect — Razorpay integration + legacy payout routes.

New Razorpay endpoints:
  POST /api/payment/create-order  — create Razorpay Order from internal order_id
  POST /api/payment/verify        — verify HMAC signature + confirm payment
  POST /api/payment/refund        — initiate refund
  GET  /api/payment/<order_id>    — get payment details (preserved)

Legacy endpoints (preserved):
  GET  /api/payments/payouts      — list farmer payouts (admin)
  PUT  /api/payments/payouts/<id>/settle — mark payout settled (admin)

Security rules:
  - Amount ALWAYS fetched from database — never trusted from request body
  - Order ownership verified before creating Razorpay order
  - HMAC-SHA256 signature verified server-side before confirming any payment
  - RAZORPAY_KEY_SECRET never returned to frontend
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from auth_middleware import token_required, roles_required
    from config import Config
    from services.razorpay_service import (
        create_razorpay_order,
        verify_payment_signature,
        fetch_payment,
        create_refund
    )
    from services.payment_service import confirm_payment_and_settle
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.auth_middleware import token_required, roles_required
    from backend.config import Config
    from backend.services.razorpay_service import (
        create_razorpay_order,
        verify_payment_signature,
        fetch_payment,
        create_refund
    )
    from backend.services.payment_service import confirm_payment_and_settle

payments_bp = Blueprint('payments', __name__)
logger = logging.getLogger('agrismart.payments')


# ─────────────────────────────────────────────────────────────────────────────
# RAZORPAY — PUBLIC KEY & CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route('/key', methods=['GET'])
def get_payment_key():
    """Return public Razorpay Key ID and payment mode (safe for frontend)."""
    return jsonify({
        'key_id': Config.RAZORPAY_KEY_ID,
        'payment_mode': Config.PAYMENT_MODE,
        'currency': 'INR'
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# RAZORPAY — CREATE ORDER
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route('/create-order', methods=['POST'])
@token_required
def create_payment_order():
    """
    Create a Razorpay Order for an existing internal order.

    Request body: { "order_id": 105 }

    Steps:
      1. Authenticate user.
      2. Fetch order from DB — verify it belongs to this user.
      3. Verify order is in payment-pending state.
      4. Read total_amount from DB (NEVER from request body).
      5. Create Razorpay Order via SDK.
      6. Store razorpay_order_id in razorpay_orders table.
      7. Return only safe data to frontend (no KEY_SECRET).
    """
    user_id = request.current_user['user_id']
    data = request.get_json() or {}
    order_id = data.get('order_id')

    if not order_id:
        return jsonify({'success': False, 'message': 'order_id is required.'}), 400

    try:
        # ── 1. Fetch and validate order ownership ──────────────────────────
        order = fetch_one("""
            SELECT o.order_id, o.total_amount, o.payment_status, o.order_status,
                   b.user_id AS buyer_user_id
            FROM orders o
            JOIN buyers b ON o.buyer_id = b.buyer_id
            WHERE o.order_id = %s;
        """, (order_id,))

        if not order:
            return jsonify({'success': False, 'message': 'Order not found.'}), 404

        # Security: ensure this order belongs to the requesting user
        if order['buyer_user_id'] != user_id and request.current_user.get('role') != 'admin':
            logger.warning(
                f"[Payment] User {user_id} attempted to pay Order #{order_id} "
                f"belonging to user {order['buyer_user_id']} — REJECTED."
            )
            return jsonify({'success': False, 'message': 'Access denied.'}), 403

        # ── 2. Verify order state ──────────────────────────────────────────
        if order['payment_status'] == 'paid':
            return jsonify({
                'success': False,
                'message': 'This order has already been paid.'
            }), 409

        if order['order_status'] == 'cancelled':
            return jsonify({
                'success': False,
                'message': 'Cannot pay for a cancelled order.'
            }), 409

        # ── 3. Amount from DB (never from frontend) ────────────────────────
        total_inr   = float(order['total_amount'])
        amount_paise = int(round(total_inr * 100))

        if amount_paise <= 0:
            return jsonify({'success': False, 'message': 'Order amount must be greater than zero.'}), 400

        # ── 4. Create Razorpay Order ───────────────────────────────────────
        rzp_order = create_razorpay_order(
            amount_paise=amount_paise,
            internal_order_id=order_id
        )
        razorpay_order_id = rzp_order['id']

        # ── 5. Persist razorpay_order_id in DB ────────────────────────────
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO razorpay_orders (order_id, razorpay_order_id, amount_paise, currency, status)
                VALUES (%s, %s, %s, 'INR', 'CREATED')
                ON CONFLICT (order_id) DO UPDATE
                    SET razorpay_order_id = EXCLUDED.razorpay_order_id,
                        amount_paise      = EXCLUDED.amount_paise,
                        status            = 'CREATED',
                        updated_at        = NOW();
            """, (order_id, razorpay_order_id, amount_paise))

        logger.info(
            f"[Payment] Razorpay Order created for internal_order={order_id} "
            f"razorpay_order={razorpay_order_id} amount=₹{total_inr}"
        )

        # ── 6. Return safe response (NO KEY_SECRET) ───────────────────────
        return jsonify({
            'success': True,
            'order_id':          order_id,
            'razorpay_order_id': razorpay_order_id,
            'amount':            amount_paise,   # paise
            'amount_inr':        total_inr,      # display
            'currency':          'INR',
            'key_id':            Config.RAZORPAY_KEY_ID,
            'payment_mode':      Config.PAYMENT_MODE
        }), 200

    except Exception as e:
        err_str = str(e)
        logger.error(f"[Payment] create-order error: {err_str}", exc_info=True)
        if 'Authentication failed' in err_str or 'REPLACE' in Config.RAZORPAY_KEY_ID:
            msg = 'Razorpay Authentication Failed: Please update RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in your .env file with your real Razorpay Test API keys from https://dashboard.razorpay.com/app/keys.'
        else:
            msg = f'Failed to create payment order: {err_str}'
        return jsonify({'success': False, 'message': msg}), 500


# ─────────────────────────────────────────────────────────────────────────────
# RAZORPAY — VERIFY PAYMENT
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route('/verify', methods=['POST'])
@token_required
def verify_payment():
    """
    Verify Razorpay payment signature and confirm the order.

    Request body:
    {
        "razorpay_payment_id": "pay_xxx",
        "razorpay_order_id":   "order_xxx",
        "razorpay_signature":  "abc123...",
        "order_id":            105
    }

    CRITICAL:
      - Signature is verified using razorpay_order_id from OUR DATABASE,
        not blindly from the request body.
      - Amount is re-fetched from DB — never from request.
      - If signature fails → 400, log security event, do not confirm order.
    """
    user_id = request.current_user['user_id']
    data = request.get_json() or {}

    razorpay_payment_id = data.get('razorpay_payment_id', '').strip()
    razorpay_order_id   = data.get('razorpay_order_id', '').strip()
    razorpay_signature  = data.get('razorpay_signature', '').strip()
    order_id            = data.get('order_id')

    if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature, order_id]):
        return jsonify({
            'success': False,
            'message': 'Missing required fields: razorpay_payment_id, razorpay_order_id, razorpay_signature, order_id.'
        }), 400

    try:
        # ── 1. Verify order ownership ──────────────────────────────────────
        order = fetch_one("""
            SELECT o.order_id, o.total_amount, o.payment_status,
                   b.user_id AS buyer_user_id
            FROM orders o
            JOIN buyers b ON o.buyer_id = b.buyer_id
            WHERE o.order_id = %s;
        """, (order_id,))

        if not order:
            return jsonify({'success': False, 'message': 'Order not found.'}), 404

        if order['buyer_user_id'] != user_id and request.current_user.get('role') != 'admin':
            logger.warning(
                f"[Payment] Verify: User {user_id} attempted to verify Order #{order_id} "
                f"belonging to user {order['buyer_user_id']} — REJECTED."
            )
            return jsonify({'success': False, 'message': 'Access denied.'}), 403

        if order['payment_status'] == 'paid':
            return jsonify({
                'success': True,
                'message': 'Payment already confirmed.',
                'order_id': order_id
            }), 200

        # ── 2. Verify razorpay_order_id matches our DB record ──────────────
        rzp_rec = fetch_one("""
            SELECT razorpay_order_id, amount_paise
            FROM razorpay_orders
            WHERE order_id = %s;
        """, (order_id,))

        if not rzp_rec:
            return jsonify({
                'success': False,
                'message': 'No Razorpay order found for this internal order.'
            }), 404

        db_razorpay_order_id = rzp_rec['razorpay_order_id']
        amount_paise         = rzp_rec['amount_paise']

        # Use OUR stored razorpay_order_id for signature generation — not the one from browser
        if db_razorpay_order_id != razorpay_order_id:
            logger.warning(
                f"[Payment] SECURITY: razorpay_order_id mismatch for order #{order_id}. "
                f"DB={db_razorpay_order_id} Request={razorpay_order_id}"
            )
            return jsonify({
                'success': False,
                'message': 'Payment validation failed. Order ID mismatch.',
                'error_code': 'ORDER_ID_MISMATCH'
            }), 400

        # ── 3. Verify HMAC-SHA256 signature ───────────────────────────────
        is_valid = verify_payment_signature(
            razorpay_order_id=db_razorpay_order_id,  # from DB
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature
        )

        if not is_valid:
            logger.error(
                f"[Payment] SIGNATURE VERIFICATION FAILED — Order #{order_id} "
                f"payment={razorpay_payment_id}. Possible payment tampering!"
            )
            return jsonify({
                'success': False,
                'message': 'Payment verification failed. Invalid signature.',
                'error_code': 'SIGNATURE_MISMATCH'
            }), 400

        # ── 4. Confirm payment in DB (transactional) ───────────────────────
        with get_db_cursor(commit=True) as cur:
            result = confirm_payment_and_settle(
                cur=cur,
                internal_order_id=order_id,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_order_id=db_razorpay_order_id,
                razorpay_signature=razorpay_signature,
                amount_paise=amount_paise
            )

        logger.info(
            f"[Payment] ✅ Order #{order_id} CONFIRMED — "
            f"gross=₹{result['gross_inr']} commission=₹{result['commission_inr']} "
            f"farmer=₹{result['farmer_inr']} settlement=SIMULATED"
        )

        return jsonify({
            'success':            True,
            'message':            f"Payment verified! Order #{order_id} is confirmed.",
            'order_id':           order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'gross_amount':       result['gross_inr'],
            'commission':         result['commission_inr'],
            'farmer_amount':      result['farmer_inr'],
            'settlement_status':  result['settlement_status'],
            'payment_mode':       Config.PAYMENT_MODE
        }), 200

    except Exception as e:
        logger.error(f"[Payment] verify error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Payment verification failed due to server error.'}), 500


# ─────────────────────────────────────────────────────────────────────────────
# RAZORPAY — REFUND
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route('/refund', methods=['POST'])
@token_required
def initiate_refund():
    """
    Initiate a Razorpay refund for a captured payment.

    Request body:
    {
        "order_id": 105,
        "reason": "Customer request"
    }

    Rules:
      - Only CAPTURED payments can be refunded.
      - Idempotent: duplicate refund requests for same order are rejected.
      - Partial refunds not supported in this version.
    """
    user_id = request.current_user['user_id']
    data = request.get_json() or {}
    order_id = data.get('order_id')
    reason = data.get('reason', 'Customer requested refund')

    if not order_id:
        return jsonify({'success': False, 'message': 'order_id is required.'}), 400

    try:
        # Verify ownership
        order = fetch_one("""
            SELECT o.order_id, o.payment_status, o.order_status,
                   b.user_id AS buyer_user_id
            FROM orders o
            JOIN buyers b ON o.buyer_id = b.buyer_id
            WHERE o.order_id = %s;
        """, (order_id,))

        if not order:
            return jsonify({'success': False, 'message': 'Order not found.'}), 404

        if order['buyer_user_id'] != user_id and request.current_user.get('role') != 'admin':
            return jsonify({'success': False, 'message': 'Access denied.'}), 403

        if order['payment_status'] != 'paid':
            return jsonify({
                'success': False,
                'message': f"Cannot refund — payment status is '{order['payment_status']}'."
            }), 409

        if order['order_status'] == 'delivered':
            return jsonify({
                'success': False,
                'message': 'Cannot refund an already delivered order.'
            }), 409

        # Check for existing refund
        existing_refund = fetch_one("""
            SELECT id, status FROM refunds WHERE order_id = %s;
        """, (order_id,))

        if existing_refund and existing_refund['status'] not in ('FAILED',):
            return jsonify({
                'success': False,
                'message': f"Refund already {existing_refund['status']} for this order."
            }), 409

        # Get razorpay_payment_id
        rzp_payment = fetch_one("""
            SELECT razorpay_payment_id, amount_paise
            FROM razorpay_payments
            WHERE order_id = %s AND status = 'CAPTURED';
        """, (order_id,))

        if not rzp_payment:
            # Fallback to payments table
            rzp_payment = fetch_one("""
                SELECT razorpay_payment_id,
                       CAST(buyer_amount * 100 AS BIGINT) AS amount_paise
                FROM payments
                WHERE order_id = %s AND payment_status = 'paid';
            """, (order_id,))

        if not rzp_payment or not rzp_payment.get('razorpay_payment_id'):
            return jsonify({
                'success': False,
                'message': 'No captured Razorpay payment found for this order.'
            }), 404

        razorpay_payment_id = rzp_payment['razorpay_payment_id']
        amount_paise        = int(rzp_payment['amount_paise'])

        # Create Razorpay refund
        rzp_refund = create_refund(
            razorpay_payment_id=razorpay_payment_id,
            amount_paise=amount_paise,
            reason=reason
        )

        # Record in DB
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO refunds (
                    order_id, razorpay_payment_id, razorpay_refund_id,
                    amount_paise, reason, status
                )
                VALUES (%s, %s, %s, %s, %s, 'PROCESSING')
                ON CONFLICT (razorpay_refund_id) DO NOTHING;
            """, (order_id, razorpay_payment_id, rzp_refund.get('id'), amount_paise, reason))

            # Update order status
            cur.execute("""
                UPDATE orders
                SET payment_status = 'refunded', order_status = 'cancelled'
                WHERE order_id = %s;
            """, (order_id,))

        logger.info(
            f"[Payment] Refund initiated for Order #{order_id} "
            f"refund_id={rzp_refund.get('id')} amount=₹{amount_paise/100:.2f}"
        )

        return jsonify({
            'success':         True,
            'message':         f"Refund of ₹{amount_paise/100:.2f} initiated for Order #{order_id}.",
            'order_id':        order_id,
            'razorpay_refund_id': rzp_refund.get('id'),
            'amount':          amount_paise / 100,
            'status':          'PROCESSING'
        }), 200

    except Exception as e:
        logger.error(f"[Payment] refund error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Refund initiation failed.'}), 500


# ─────────────────────────────────────────────────────────────────────────────
# GET PAYMENT STATUS (preserved from original)
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route('/<int:order_id>', methods=['GET'])
@token_required
def get_payment_details(order_id):
    """Retrieve detailed payment receipt and fee breakdown for an order."""
    try:
        payment = fetch_one("""
            SELECT p.*, o.order_date, o.order_status,
                   b.business_name, u.name AS buyer_name, u.email AS buyer_email,
                   ro.razorpay_order_id, ro.status AS rzp_order_status
            FROM payments p
            JOIN orders o ON p.order_id = o.order_id
            JOIN buyers b ON o.buyer_id = b.buyer_id
            JOIN users u ON b.user_id = u.user_id
            LEFT JOIN razorpay_orders ro ON p.order_id = ro.order_id
            WHERE p.order_id = %s;
        """, (order_id,))

        if not payment:
            return jsonify({'error': 'Not Found', 'message': 'Payment record not found for this order.'}), 404

        return jsonify({'status': 'success', 'payment': payment}), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# LEGACY: simulate payment (preserved for non-Razorpay flows)
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route('', methods=['POST'])
@token_required
def process_payment():
    """
    Record payment confirmation for an order (legacy/simulation fallback).
    In prototype, simulates gateway webhook or UPI payment confirmation.
    """
    data = request.get_json() or {}
    order_id = data.get('order_id')
    payment_method = data.get('payment_method', 'UPI')
    tx_ref = data.get('transaction_reference', f"TXN-{order_id}-{int(datetime.now().timestamp())}")

    if not order_id:
        return jsonify({'error': 'Bad Request', 'message': 'order_id is required.'}), 400

    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE payments
                SET payment_status = 'paid',
                    payment_method = %s,
                    transaction_reference = %s
                WHERE order_id = %s
                RETURNING *;
            """, (payment_method, tx_ref, order_id))
            payment = cur.fetchone()

            if not payment:
                return jsonify({'error': 'Not Found', 'message': 'Payment record not found.'}), 404

            cur.execute("UPDATE orders SET payment_status = 'paid' WHERE order_id = %s;", (order_id,))

        return jsonify({
            'status': 'success',
            'message': 'Payment recorded successfully.',
            'payment': dict(payment)
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# FARMER PAYOUTS (preserved from original)
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route('/payouts', methods=['GET'])
@token_required
@roles_required('admin')
def list_all_payouts():
    """List all farmer payouts across the platform (Admin only)."""
    try:
        payouts = fetch_all("""
            SELECT p.*, fp.farm_name, u.name AS farmer_name, u.phone AS farmer_phone,
                   o.order_date, o.order_status
            FROM farmer_payouts p
            JOIN farmer_profiles fp ON p.farmer_id = fp.farmer_id
            JOIN users u ON fp.user_id = u.user_id
            JOIN orders o ON p.order_id = o.order_id
            ORDER BY p.created_at DESC;
        """)
        return jsonify({'status': 'success', 'payouts': payouts}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@payments_bp.route('/payouts/<int:payout_id>/settle', methods=['PUT'])
@token_required
@roles_required('admin')
def settle_payout(payout_id):
    """Admin marks a pending or processing farmer payout as paid (disbursed)."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE farmer_payouts
                SET payout_status = 'paid',
                    payout_date = CURRENT_TIMESTAMP
                WHERE payout_id = %s
                RETURNING *;
            """, (payout_id,))
            payout = cur.fetchone()

            if not payout:
                return jsonify({'error': 'Not Found', 'message': 'Payout record not found.'}), 404

        return jsonify({
            'status': 'success',
            'message': f"Payout #{payout_id} marked as PAID.",
            'payout': dict(payout)
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# DELIVERY PARTNER PAYOUTS
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route('/delivery-payouts', methods=['GET'])
@token_required
@roles_required('admin')
def list_delivery_payouts():
    """List all delivery partner payouts across the platform (Admin only)."""
    try:
        payouts = fetch_all("""
            SELECT dp.*, u.name AS partner_name, u.phone AS partner_phone, u.email AS partner_email,
                   d.delivery_address, d.delivery_time, d.status AS delivery_status,
                   o.total_amount, o.order_date
            FROM delivery_payouts dp
            JOIN users u ON dp.delivery_partner_id = u.user_id
            JOIN deliveries d ON dp.delivery_id = d.delivery_id
            JOIN orders o ON dp.order_id = o.order_id
            ORDER BY dp.created_at DESC;
        """)
        return jsonify({'status': 'success', 'payouts': payouts}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@payments_bp.route('/delivery-payouts/<int:payout_id>/settle', methods=['PUT'])
@token_required
@roles_required('admin')
def settle_delivery_payout(payout_id):
    """Admin marks a delivery partner payout as paid (disbursed)."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE delivery_payouts
                SET payout_status = 'paid',
                    payout_date = CURRENT_TIMESTAMP,
                    transaction_ref = COALESCE(transaction_ref, 'DISB-DRV-' || %s)
                WHERE payout_id = %s
                RETURNING *;
            """, (payout_id, payout_id))
            payout = cur.fetchone()

            if not payout:
                return jsonify({'error': 'Not Found', 'message': 'Delivery payout record not found.'}), 404

        return jsonify({
            'status': 'success',
            'message': f"Delivery Payout #{payout_id} marked as PAID.",
            'payout': dict(payout)
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# FARMER PAYMENT ACCOUNT (Route readiness)
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route('/farmer-account/<int:farmer_id>', methods=['GET'])
@token_required
def get_farmer_account(farmer_id):
    """Get farmer's Razorpay linked account status."""
    try:
        account = fetch_one("""
            SELECT fa.*, fp.farm_name, u.name, u.email
            FROM farmer_accounts fa
            JOIN farmer_profiles fp ON fa.farmer_id = fp.farmer_id
            JOIN users u ON fp.user_id = u.user_id
            WHERE fa.farmer_id = %s;
        """, (farmer_id,))

        if not account:
            return jsonify({
                'status': 'success',
                'account': {
                    'farmer_id': farmer_id,
                    'account_status': 'NOT_CONNECTED',
                    'kyc_status': 'PENDING',
                    'mode': Config.PAYMENT_MODE
                }
            }), 200

        return jsonify({'status': 'success', 'account': account}), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN PAYMENT DASHBOARD SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route('/admin/summary', methods=['GET'])
@token_required
@roles_required('admin')
def admin_payment_summary():
    """Return aggregated payment metrics for admin dashboard."""
    try:
        summary = fetch_one("""
            SELECT
                COUNT(DISTINCT o.order_id)                           AS total_orders,
                COUNT(DISTINCT CASE WHEN o.payment_status = 'paid'
                      THEN o.order_id END)                           AS paid_orders,
                COUNT(DISTINCT CASE WHEN o.payment_status = 'failed'
                      THEN o.order_id END)                           AS failed_orders,
                COALESCE(SUM(o.total_amount)
                    FILTER (WHERE o.payment_status = 'paid'), 0)     AS gross_sales,
                COALESCE(SUM(p.commission_amount)
                    FILTER (WHERE o.payment_status = 'paid'), 0)     AS total_commission,
                COALESCE(SUM(p.farmer_amount)
                    FILTER (WHERE o.payment_status = 'paid'), 0)     AS total_farmer_amount,
                COUNT(DISTINCT t.id)
                    FILTER (WHERE t.status = 'SIMULATED')            AS simulated_transfers,
                COUNT(DISTINCT r.id)                                  AS total_refunds
            FROM orders o
            LEFT JOIN payments p   ON o.order_id = p.order_id
            LEFT JOIN transfers t  ON o.order_id = t.order_id
            LEFT JOIN refunds r    ON o.order_id = r.order_id;
        """)

        return jsonify({
            'status': 'success',
            'payment_mode': Config.PAYMENT_MODE,
            'commission_percent': Config.PLATFORM_COMMISSION_PERCENT,
            'summary': summary
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500
