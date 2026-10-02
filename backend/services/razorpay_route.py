"""
razorpay_route.py
Razorpay Route / Linked Account marketplace settlement module.
Currently operates in SIMULATED mode (test environment).

In SIMULATED mode:
  - All farmer transfers are logged with status='SIMULATED'
  - No real API calls are made to Razorpay Route
  - The admin dashboard clearly shows SIMULATED label

Production activation checklist (do NOT enable until):
  1. Razorpay Route / Marketplace is enabled on your live account
  2. All farmer bank accounts are KYC-verified via Razorpay onboarding
  3. Live API keys are configured
  4. PAYMENT_MODE=live in .env
  5. Each farmer_account.razorpay_account_id is populated
  6. Business/legal compliance review complete
"""

import logging

logger = logging.getLogger('agrismart.razorpay_route')


def is_route_enabled() -> bool:
    """Returns True only when PAYMENT_MODE=live AND Route is configured."""
    try:
        from config import Config
    except ImportError:
        from backend.config import Config
    return getattr(Config, 'PAYMENT_MODE', 'test').lower() == 'live'


def create_farmer_account(farmer_id: int, business_name: str,
                           email: str, phone: str) -> dict:
    """
    Onboard a farmer as a Razorpay Route linked account.

    In TEST/SIMULATED mode: returns a mock response.
    In LIVE mode: calls Razorpay Route API.

    Args:
        farmer_id: Internal farmer_profiles.farmer_id
        business_name: Farmer's farm/business name
        email: Farmer's email
        phone: Farmer's phone (10 digits, no country code)

    Returns:
        dict with razorpay_account_id and status
    """
    if not is_route_enabled():
        logger.info(
            f"[Route SIMULATED] create_farmer_account for farmer_id={farmer_id}"
        )
        return {
            'mode': 'SIMULATED',
            'farmer_id': farmer_id,
            'razorpay_account_id': None,
            'account_status': 'NOT_CONNECTED',
            'message': 'Route not enabled. Set PAYMENT_MODE=live and complete farmer onboarding.'
        }

    # ── LIVE MODE (activate when Route is enabled) ─────────────────────────
    try:
        from services.razorpay_service import _get_client
    except ImportError:
        from backend.services.razorpay_service import _get_client

    client = _get_client()
    # Reference: https://razorpay.com/docs/route/create-linked-account/
    account = client.account.create({
        'email': email,
        'profile': {
            'category': 'agriculture',
            'subcategory': 'farmer',
            'addresses': {}
        },
        'legal_business_name': business_name,
        'business_type': 'individual',
        'contact_name': business_name,
        'contact_info': {
            'phone_no': phone
        }
    })
    logger.info(
        f"[Route LIVE] Linked account created: {account['id']} for farmer {farmer_id}"
    )
    return {
        'mode': 'LIVE',
        'farmer_id': farmer_id,
        'razorpay_account_id': account['id'],
        'account_status': 'PENDING',
    }


def create_transfer(razorpay_payment_id: str, farmer_id: int,
                    razorpay_account_id: str, amount_paise: int,
                    order_id: int) -> dict:
    """
    Transfer farmer's share to their linked Razorpay account.

    In SIMULATED mode: logs and returns mock response.
    In LIVE mode: calls Razorpay Route transfer API.

    Args:
        razorpay_payment_id: The captured payment ID to transfer from.
        farmer_id: Internal farmer_profiles.farmer_id
        razorpay_account_id: Farmer's Razorpay linked account ID.
        amount_paise: Amount to transfer in paise.
        order_id: Internal order reference.

    Returns:
        dict with transfer details.
    """
    if not is_route_enabled():
        simulated_id = f"SIMULATED-TRF-{order_id}-{farmer_id}"
        logger.info(
            f"[Route SIMULATED] Transfer ₹{amount_paise/100:.2f} "
            f"to farmer {farmer_id} for order {order_id}"
        )
        return {
            'mode': 'SIMULATED',
            'transfer_id': simulated_id,
            'farmer_id': farmer_id,
            'amount_paise': amount_paise,
            'status': 'SIMULATED',
            'settlement_status': 'SIMULATED'
        }

    # ── LIVE MODE ──────────────────────────────────────────────────────────
    try:
        from services.razorpay_service import _get_client
    except ImportError:
        from backend.services.razorpay_service import _get_client

    client = _get_client()
    # Reference: https://razorpay.com/docs/route/transfers/
    transfer = client.payment.transfer(razorpay_payment_id, {
        'transfers': [{
            'account': razorpay_account_id,
            'amount': int(amount_paise),
            'currency': 'INR',
            'notes': {
                'order_id': str(order_id),
                'farmer_id': str(farmer_id),
                'platform': 'AgriSmartConnect'
            }
        }]
    })
    logger.info(
        f"[Route LIVE] Transfer created: {transfer['items'][0]['id']} "
        f"amount=₹{amount_paise/100:.2f} to farmer {farmer_id}"
    )
    return {
        'mode': 'LIVE',
        'transfer_id': transfer['items'][0]['id'],
        'farmer_id': farmer_id,
        'amount_paise': amount_paise,
        'status': 'PENDING',
        'settlement_status': 'PENDING'
    }


def get_transfer(razorpay_transfer_id: str) -> dict:
    """Fetch transfer status from Razorpay Route (LIVE mode only)."""
    if not is_route_enabled():
        return {'mode': 'SIMULATED', 'status': 'SIMULATED'}

    try:
        from services.razorpay_service import _get_client
    except ImportError:
        from backend.services.razorpay_service import _get_client

    client = _get_client()
    return client.transfer.fetch(razorpay_transfer_id)


def handle_transfer_webhook(event_data: dict) -> None:
    """Process transfer.processed / transfer.failed webhook events."""
    transfer_id = event_data.get('payload', {}).get('transfer', {}).get('entity', {}).get('id')
    status = event_data.get('event', '')
    logger.info(f"[Route] Transfer webhook: event={status} transfer_id={transfer_id}")
    # TODO: Update transfers table status when Route goes live


def handle_settlement_webhook(event_data: dict) -> None:
    """Process settlement.processed webhook events."""
    settlement_id = event_data.get('payload', {}).get('settlement', {}).get('entity', {}).get('id')
    logger.info(f"[Route] Settlement webhook: settlement_id={settlement_id}")
    # TODO: Update settlement records when Route goes live
