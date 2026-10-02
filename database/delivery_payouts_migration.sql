-- ====================================================================
-- AgriSmart Connect - Delivery Partner Payouts Migration
-- ====================================================================

CREATE TABLE IF NOT EXISTS delivery_payouts (
    payout_id SERIAL PRIMARY KEY,
    delivery_partner_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    delivery_id INTEGER NOT NULL REFERENCES deliveries(delivery_id) ON DELETE CASCADE,
    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    base_fare NUMERIC(10, 2) NOT NULL DEFAULT 50.00,
    distance_km NUMERIC(6, 2) NOT NULL DEFAULT 0.00,
    cargo_weight_kg NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    bonus_incentive NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    total_payout NUMERIC(10, 2) NOT NULL CHECK (total_payout >= 0),
    payout_status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (payout_status IN (
        'pending',
        'processing',
        'paid',
        'failed'
    )),
    payout_date TIMESTAMPTZ,
    transaction_ref VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_delivery_payouts_partner ON delivery_payouts(delivery_partner_id);
CREATE INDEX IF NOT EXISTS idx_delivery_payouts_status ON delivery_payouts(payout_status);
CREATE INDEX IF NOT EXISTS idx_delivery_payouts_order ON delivery_payouts(order_id);

-- Populate payouts for existing completed deliveries if any
INSERT INTO delivery_payouts (
    delivery_partner_id, delivery_id, order_id, base_fare,
    distance_km, cargo_weight_kg, total_payout, payout_status, payout_date, transaction_ref
)
SELECT 
    d.delivery_partner_id,
    d.delivery_id,
    d.order_id,
    60.00 AS base_fare,
    7.5 AS distance_km,
    45.0 AS cargo_weight_kg,
    COALESCE(p.delivery_fee, 80.00) AS total_payout,
    'paid' AS payout_status,
    CURRENT_TIMESTAMP,
    'DISB-DRV-' || d.delivery_id
FROM deliveries d
LEFT JOIN payments p ON d.order_id = p.order_id
WHERE d.status = 'delivered' AND d.delivery_partner_id IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM delivery_payouts dp WHERE dp.delivery_id = d.delivery_id
);
