"""
backend/services/settlement_service.py
Multi-Party Settlement Ledger and Payout Service for AgriSmart Connect.
Splits customer payment into Farmer, Delivery Partner, Hub, and Platform settlements.
Supports farmers without UPI via verified bank accounts.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from config import Config
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.config import Config

logger = logging.getLogger('agrismart.settlement')


def mask_bank_account(acc_num: Optional[str]) -> str:
    """Mask sensitive bank account number: e.g. 'XXXX XXXX 1234'."""
    if not acc_num:
        return 'Not Configured'
    clean = str(acc_num).replace(' ', '').replace('-', '')
    if len(clean) <= 4:
        return f"XXXX {clean}"
    last4 = clean[-4:]
    return f"XXXX XXXX {last4}"


def get_farmer_payout_profile(farmer_id: int) -> Dict[str, Any]:
    """Retrieve bank account and UPI details for farmer, masking sensitive numbers for display."""
    sql = """
        SELECT fpa.*, u.name AS farmer_name, u.phone AS farmer_phone
        FROM farmer_profiles fp
        JOIN users u ON fp.user_id = u.user_id
        LEFT JOIN farmer_payout_accounts fpa ON fp.farmer_id = fpa.farmer_id
        WHERE fp.farmer_id = %s;
    """
    row = fetch_one(sql, (farmer_id,))
    if not row:
        return {'farmer_id': farmer_id, 'has_account': False}

    has_acc = bool(row.get('bank_account_number'))
    raw_acc = row.get('bank_account_number') or ''
    return {
        'farmer_id': farmer_id,
        'has_account': has_acc,
        'account_holder_name': row.get('account_holder_name') or row.get('farmer_name'),
        'bank_name': row.get('bank_name') or 'State Bank of India',
        'masked_account_number': mask_bank_account(raw_acc),
        'IFSC': row.get('IFSC') or 'SBIN0001234',
        'UPI_ID': row.get('UPI_ID'),
        'UPI_available': bool(row.get('UPI_available') and row.get('UPI_ID')),
        'verification_status': row.get('verification_status') or 'VERIFIED',
        'payout_provider_reference': row.get('payout_provider_reference') or f"PAYOUT-FARMER-{farmer_id}"
    }


def execute_order_settlements(cur, order_id: int) -> List[Dict[str, Any]]:
    """
    Generate multi-party settlement ledger records upon successful delivery:
    1. Farmer produce amount
    2. Delivery Partner trip earnings
    3. Origin Hub handling fee
    4. Destination Hub handling fee (if inter-hub transfer occurred)
    5. Platform commission
    """
    # Fetch order and payment data
    cur.execute("""
        SELECT o.*, p.buyer_amount, p.delivery_fee AS payment_delivery_fee,
               p.platform_fee AS payment_platform_fee, p.farmer_amount AS payment_farmer_amount,
               h1.hub_name AS src_hub_name, h2.hub_name AS dst_hub_name
        FROM orders o
        LEFT JOIN payments p ON o.order_id = p.order_id
        LEFT JOIN hubs h1 ON o.source_hub_id = h1.hub_id
        LEFT JOIN hubs h2 ON o.destination_hub_id = h2.hub_id
        WHERE o.order_id = %s;
    """, (order_id,))
    order = cur.fetchone()
    if not order:
        raise ValueError(f"Order #{order_id} not found for settlement.")

    # Prevent duplicate settlement generation
    cur.execute("SELECT COUNT(*) AS count FROM settlements WHERE order_id = %s;", (order_id,))
    existing = cur.fetchone()
    if existing and existing['count'] > 0:
        logger.info(f"[Settlement] Order #{order_id} already has settlement ledger entries.")
        cur.execute("SELECT * FROM settlements WHERE order_id = %s;", (order_id,))
        return [dict(r) for r in cur.fetchall()]

    # Fetch order items to calculate farmer shares
    cur.execute("""
        SELECT oi.*, fp.farmer_id, fp.user_id AS farmer_user_id, u.name AS farmer_name
        FROM order_items oi
        JOIN farmer_profiles fp ON oi.farmer_id = fp.farmer_id
        JOIN users u ON fp.user_id = u.user_id
        WHERE oi.order_id = %s;
    """, (order_id,))
    items = cur.fetchall()

    subtotal = float(order['subtotal'])
    delivery_fee = float(order['delivery_fee'])
    platform_commission_pct = Config.PLATFORM_COMMISSION_PERCENT
    platform_fee = round(subtotal * platform_commission_pct / 100.0, 2)
    hub_fee_unit = Config.DEFAULT_HUB_FEE

    settlement_records = []

    # 1. FARMER SETTLEMENTS (per farmer)
    farmer_shares = {}
    for it in items:
        f_id = it['farmer_id']
        f_user_id = it['farmer_user_id']
        f_name = it['farmer_name']
        line_total = float(it['subtotal'])
        if f_id not in farmer_shares:
            farmer_shares[f_id] = {
                'user_id': f_user_id,
                'name': f_name,
                'gross': 0.0
            }
        farmer_shares[f_id]['gross'] += line_total

    for f_id, data in farmer_shares.items():
        f_gross = round(data['gross'], 2)
        f_comm = round(f_gross * platform_commission_pct / 100.0, 2)
        f_net = round(f_gross - f_comm, 2)
        ref = f"SETTLE-FARMER-{f_id}-ORD-{order_id}"

        cur.execute("""
            INSERT INTO settlements (
                order_id, beneficiary_id, beneficiary_name, beneficiary_type,
                amount, settlement_type, status, payout_reference, notes, processed_at
            )
            VALUES (%s, %s, %s, 'FARMER', %s, 'FARMER_PAYOUT', 'PAID', %s, %s, CURRENT_TIMESTAMP)
            RETURNING *;
        """, (order_id, data['user_id'], data['name'], f_net, ref, f"Farmer harvest payout for order #{order_id} (Gross ₹{f_gross} - Comm ₹{f_comm})"))
        settlement_records.append(dict(cur.fetchone()))

        # Also insert or update farmer_payouts table for backward compatibility
        cur.execute("""
            INSERT INTO farmer_payouts (
                farmer_id, order_id, gross_amount, platform_fee,
                other_deductions, net_amount, payout_status, payout_date
            )
            VALUES (%s, %s, %s, %s, 0.00, %s, 'paid', CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING;
        """, (f_id, order_id, f_gross, f_comm, f_net))

    # 2. DELIVERY PARTNER SETTLEMENT
    cur.execute("""
        SELECT d.delivery_id, d.delivery_partner_id, u.name AS driver_name
        FROM deliveries d
        LEFT JOIN users u ON d.delivery_partner_id = u.user_id
        WHERE d.order_id = %s;
    """, (order_id,))
    deliv = cur.fetchone()

    total_weight = sum(float(it.get('quantity_kg') or 0) for it in items)
    base_fare = Config.DEFAULT_DELIVERY_BASE_FARE
    driver_payout = max(round(delivery_fee * 0.9, 2), round(base_fare + (total_weight * 1.5), 2))

    if deliv and deliv.get('delivery_partner_id'):
        dp_id = deliv['delivery_partner_id']
        dp_name = deliv.get('driver_name') or 'Delivery Partner'
        ref_d = f"SETTLE-DRV-{dp_id}-ORD-{order_id}"

        cur.execute("""
            INSERT INTO settlements (
                order_id, beneficiary_id, beneficiary_name, beneficiary_type,
                amount, settlement_type, status, payout_reference, notes, processed_at
            )
            VALUES (%s, %s, %s, 'DELIVERY_PARTNER', %s, 'DELIVERY_FEE', 'PAID', %s, %s, CURRENT_TIMESTAMP)
            RETURNING *;
        """, (order_id, dp_id, dp_name, driver_payout, ref_d, f"Trip earnings for order #{order_id} ({total_weight} kg cargo)"))
        settlement_records.append(dict(cur.fetchone()))

        # Record in delivery_earnings
        cur.execute("""
            INSERT INTO delivery_earnings (
                delivery_partner_id, order_id, delivery_fee, status, payout_reference, paid_at
            )
            VALUES (%s, %s, %s, 'PAID', %s, CURRENT_TIMESTAMP);
        """, (dp_id, order_id, driver_payout, ref_d))

    # 3. HUB HANDLING SETTLEMENT (Origin Hub)
    if order.get('source_hub_id'):
        cur.execute("SELECT hub_id, hub_name, manager_id FROM hubs WHERE hub_id = %s;", (order['source_hub_id'],))
        h1 = cur.fetchone()
        if h1:
            h_ref1 = f"SETTLE-HUB-{h1['hub_id']}-ORD-{order_id}"
            cur.execute("""
                INSERT INTO settlements (
                    order_id, beneficiary_id, beneficiary_name, beneficiary_type,
                    amount, settlement_type, status, payout_reference, notes, processed_at
                )
                VALUES (%s, %s, %s, 'HUB', %s, 'HUB_COMMISSION', 'PAID', %s, %s, CURRENT_TIMESTAMP)
                RETURNING *;
            """, (order_id, h1.get('manager_id'), f"{h1['hub_name']} Aggregation Hub", hub_fee_unit, h_ref1, f"Aggregation & QC processing allocation for order #{order_id}"))
            settlement_records.append(dict(cur.fetchone()))

    # Destination Hub Handling (if multi-hub transfer took place)
    if order.get('requires_hub_transfer') and order.get('destination_hub_id') and order['destination_hub_id'] != order.get('source_hub_id'):
        cur.execute("SELECT hub_id, hub_name, manager_id FROM hubs WHERE hub_id = %s;", (order['destination_hub_id'],))
        h2 = cur.fetchone()
        if h2:
            h_ref2 = f"SETTLE-HUB-TRANSFER-{h2['hub_id']}-ORD-{order_id}"
            cur.execute("""
                INSERT INTO settlements (
                    order_id, beneficiary_id, beneficiary_name, beneficiary_type,
                    amount, settlement_type, status, payout_reference, notes, processed_at
                )
                VALUES (%s, %s, %s, 'HUB', %s, 'HUB_COMMISSION', 'PAID', %s, %s, CURRENT_TIMESTAMP)
                RETURNING *;
            """, (order_id, h2.get('manager_id'), f"{h2['hub_name']} Destination Hub", round(hub_fee_unit * 0.75, 2), h_ref2, f"Destination hub sorting & staging allocation for order #{order_id}"))
            settlement_records.append(dict(cur.fetchone()))

    # 4. PLATFORM FEE SETTLEMENT
    cur.execute("SELECT user_id, name FROM users WHERE role = 'admin' LIMIT 1;")
    admin_usr = cur.fetchone()
    admin_id = admin_usr['user_id'] if admin_usr else None
    ref_p = f"SETTLE-PLATFORM-ORD-{order_id}"

    cur.execute("""
        INSERT INTO settlements (
            order_id, beneficiary_id, beneficiary_name, beneficiary_type,
            amount, settlement_type, status, payout_reference, notes, processed_at
        )
        VALUES (%s, %s, 'AgriSmart Connect Platform', 'PLATFORM', %s, 'PLATFORM_FEE', 'PAID', %s, %s, CURRENT_TIMESTAMP)
        RETURNING *;
    """, (order_id, admin_id, platform_fee, ref_p, f"Platform service commission ({platform_commission_pct}%)"))
    settlement_records.append(dict(cur.fetchone()))

    logger.info(f"[Settlement] Order #{order_id} settled with {len(settlement_records)} multi-party ledger records.")
    return settlement_records


def get_all_settlements(limit: int = 50, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve multi-party settlement ledger entries for admin oversight."""
    params = []
    sql = """
        SELECT s.*, o.total_amount AS order_total, o.order_date
        FROM settlements s
        JOIN orders o ON s.order_id = o.order_id
    """
    if status_filter:
        sql += " WHERE s.status = %s"
        params.append(status_filter.upper())

    sql += " ORDER BY s.created_at DESC LIMIT %s;"
    params.append(limit)

    return fetch_all(sql, tuple(params))
