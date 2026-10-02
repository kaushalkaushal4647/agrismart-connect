"""
razorpay_service.py
Low-level Razorpay SDK wrapper for AgriSmart Connect.
Uses razorpay Python SDK v2.x.
All direct calls to the Razorpay SDK are isolated here.
"""

import logging
logger = logging.getLogger('agrismart.razorpay')


def _get_client():
    """Return an authenticated Razorpay client (SDK v2)."""
    try:
        from config import Config
    except ImportError:
        from backend.config import Config
    import razorpay
    return razorpay.Client(auth=(Config.RAZORPAY_KEY_ID, Config.RAZORPAY_KEY_SECRET))


# ─────────────────────────────────────────────────────────────────────────────
# ORDER CREATION
# ─────────────────────────────────────────────────────────────────────────────

def create_razorpay_order(amount_paise: int, internal_order_id: int,
                          currency: str = 'INR') -> dict:
    """
    Create a Razorpay Order object server-side.

    Args:
        amount_paise: Total amount in paise (1 INR = 100 paise).
        internal_order_id: Our PostgreSQL orders.order_id — used as receipt.
        currency: ISO 4217 code (default: INR).

    Returns:
        Razorpay order dict including 'id' (razorpay_order_id).
    """
    client = _get_client()
    data = {
        'amount': int(amount_paise),
        'currency': currency,
        'receipt': f'agri-order-{internal_order_id}',
        'notes': {
            'internal_order_id': str(internal_order_id),
            'platform': 'AgriSmartConnect'
        }
    }
    rzp_order = client.order.create(data=data)
    logger.info(
        f"[Razorpay] Order created: rzp_order_id={rzp_order['id']} "
        f"internal_order_id={internal_order_id} amount={amount_paise}p"
    )
    return rzp_order


# ─────────────────────────────────────────────────────────────────────────────
# SIGNATURE VERIFICATION (SDK v2 utility)
# ─────────────────────────────────────────────────────────────────────────────

def verify_payment_signature(razorpay_order_id: str,
                              razorpay_payment_id: str,
                              razorpay_signature: str) -> bool:
    """
    Verify HMAC-SHA256 payment signature using Razorpay SDK v2 utility.

    Uses razorpay_order_id FROM OUR DATABASE — not blindly from browser.
    Message: razorpay_order_id + '|' + razorpay_payment_id
    Key: RAZORPAY_KEY_SECRET

    Returns:
        True if valid, False if tampered/invalid.
    """
    client = _get_client()
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id':   razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature':  razorpay_signature
        })
        logger.info(
            f"[Razorpay] Signature VALID: order={razorpay_order_id} "
            f"payment={razorpay_payment_id}"
        )
        return True
    except Exception as e:
        logger.warning(
            f"[Razorpay] Signature INVALID: order={razorpay_order_id} "
            f"payment={razorpay_payment_id} — {e}"
        )
        return False


def verify_webhook_signature(raw_body: bytes, received_signature: str) -> bool:
    """
    Verify incoming webhook request using Razorpay SDK v2 utility.
    Must be called on RAW body before any JSON parsing.

    Returns:
        True if genuine, False if rejected.
    """
    try:
        from config import Config
    except ImportError:
        from backend.config import Config

    client = _get_client()
    try:
        client.utility.verify_webhook_signature(
            raw_body.decode('utf-8'),
            received_signature,
            Config.RAZORPAY_WEBHOOK_SECRET
        )
        return True
    except Exception as e:
        logger.warning(f"[Razorpay] Webhook signature INVALID: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PAYMENT FETCH (server-side status verification)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_payment(razorpay_payment_id: str) -> dict:
    """Fetch payment details from Razorpay to server-side confirm status."""
    client = _get_client()
    payment = client.payment.fetch(razorpay_payment_id)
    logger.info(
        f"[Razorpay] Fetched payment {razorpay_payment_id}: "
        f"status={payment.get('status')}"
    )
    return payment


# ─────────────────────────────────────────────────────────────────────────────
# REFUND
# ─────────────────────────────────────────────────────────────────────────────

def create_refund(razorpay_payment_id: str, amount_paise: int,
                  reason: str = 'Customer requested refund') -> dict:
    """
    Initiate a refund via Razorpay SDK v2.

    Args:
        razorpay_payment_id: The captured payment to refund.
        amount_paise: Amount to refund in paise.
        reason: Reason for refund (stored in notes).

    Returns:
        Razorpay refund object.
    """
    client = _get_client()
    refund = client.payment.refund(razorpay_payment_id, {
        'amount': int(amount_paise),
        'notes': {
            'reason': reason,
            'platform': 'AgriSmartConnect'
        }
    })
    logger.info(
        f"[Razorpay] Refund created: refund_id={refund['id']} "
        f"payment={razorpay_payment_id} amount={amount_paise}p"
    )
    return refund
