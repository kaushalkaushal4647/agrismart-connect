-- ====================================================================
-- AgriSmart Connect - Payment Migration (Razorpay Integration)
-- Run once against existing 'agrismart' database.
-- Additive only: ALTER TABLE ADD COLUMN IF NOT EXISTS, CREATE TABLE IF NOT EXISTS
-- Zero data loss — does NOT drop or truncate any existing table.
-- ====================================================================

-- ====================================================================
-- 1. ALTER existing payments table — add Razorpay columns
-- ====================================================================
ALTER TABLE payments
    ADD COLUMN IF NOT EXISTS razorpay_order_id  VARCHAR(100),
    ADD COLUMN IF NOT EXISTS razorpay_payment_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS razorpay_signature  VARCHAR(500),
    ADD COLUMN IF NOT EXISTS currency            VARCHAR(10)   DEFAULT 'INR',
    ADD COLUMN IF NOT EXISTS gross_amount        NUMERIC(10,2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS commission_percent  NUMERIC(5,2)  DEFAULT 10.00,
    ADD COLUMN IF NOT EXISTS commission_amount   NUMERIC(10,2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS settlement_status   VARCHAR(30)   DEFAULT 'SIMULATED'
        CHECK (settlement_status IN ('SIMULATED','PENDING','PROCESSING','PROCESSED','FAILED'));

-- ====================================================================
-- 2. RAZORPAY ORDERS — links internal order_id to Razorpay order_id
-- ====================================================================
CREATE TABLE IF NOT EXISTS razorpay_orders (
    id                SERIAL PRIMARY KEY,
    order_id          INTEGER NOT NULL UNIQUE REFERENCES orders(order_id) ON DELETE CASCADE,
    razorpay_order_id VARCHAR(100) NOT NULL UNIQUE,
    amount_paise      BIGINT NOT NULL,
    currency          VARCHAR(10) NOT NULL DEFAULT 'INR',
    status            VARCHAR(30) NOT NULL DEFAULT 'CREATED'
        CHECK (status IN ('CREATED','ATTEMPTED','PAID','EXPIRED')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_razorpay_orders_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_razorpay_orders_updated_at'
    ) THEN
        CREATE TRIGGER trigger_razorpay_orders_updated_at
        BEFORE UPDATE ON razorpay_orders
        FOR EACH ROW EXECUTE FUNCTION update_razorpay_orders_updated_at();
    END IF;
END; $$;

-- ====================================================================
-- 3. RAZORPAY PAYMENTS — one record per verified payment
-- ====================================================================
CREATE TABLE IF NOT EXISTS razorpay_payments (
    id                   SERIAL PRIMARY KEY,
    order_id             INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE RESTRICT,
    razorpay_order_id    VARCHAR(100) NOT NULL,
    razorpay_payment_id  VARCHAR(100) NOT NULL UNIQUE,
    razorpay_signature   VARCHAR(500),
    amount_paise         BIGINT NOT NULL,
    currency             VARCHAR(10) NOT NULL DEFAULT 'INR',
    status               VARCHAR(30) NOT NULL DEFAULT 'CREATED'
        CHECK (status IN ('CREATED','AUTHORIZED','CAPTURED','FAILED','REFUNDED')),
    failure_reason       TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_razorpay_payments_updated_at'
    ) THEN
        CREATE TRIGGER trigger_razorpay_payments_updated_at
        BEFORE UPDATE ON razorpay_payments
        FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();
    END IF;
END; $$;

-- ====================================================================
-- 4. WEBHOOK EVENTS — idempotency store
-- ====================================================================
CREATE TABLE IF NOT EXISTS webhook_events (
    id           SERIAL PRIMARY KEY,
    event_id     VARCHAR(100) NOT NULL UNIQUE,
    event_type   VARCHAR(100) NOT NULL,
    payload      JSONB,
    processed    BOOLEAN NOT NULL DEFAULT FALSE,
    error_msg    TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_event_id ON webhook_events(event_id);
CREATE INDEX IF NOT EXISTS idx_webhook_events_processed ON webhook_events(processed);

-- ====================================================================
-- 5. FARMER ACCOUNTS — Razorpay Route / linked account readiness
-- ====================================================================
CREATE TABLE IF NOT EXISTS farmer_accounts (
    id                  SERIAL PRIMARY KEY,
    farmer_id           INTEGER NOT NULL UNIQUE REFERENCES farmer_profiles(farmer_id) ON DELETE CASCADE,
    razorpay_account_id VARCHAR(100),
    account_status      VARCHAR(30) NOT NULL DEFAULT 'NOT_CONNECTED'
        CHECK (account_status IN ('NOT_CONNECTED','PENDING','ACTIVE','SUSPENDED')),
    kyc_status          VARCHAR(30) NOT NULL DEFAULT 'PENDING'
        CHECK (kyc_status IN ('PENDING','SUBMITTED','VERIFIED','REJECTED')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_farmer_accounts_updated_at'
    ) THEN
        CREATE TRIGGER trigger_farmer_accounts_updated_at
        BEFORE UPDATE ON farmer_accounts
        FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();
    END IF;
END; $$;

-- ====================================================================
-- 6. TRANSFERS — Route/marketplace settlement ledger
-- ====================================================================
CREATE TABLE IF NOT EXISTS transfers (
    id                   SERIAL PRIMARY KEY,
    razorpay_payment_id  VARCHAR(100),
    order_id             INTEGER REFERENCES orders(order_id) ON DELETE SET NULL,
    farmer_id            INTEGER REFERENCES farmer_profiles(farmer_id) ON DELETE SET NULL,
    razorpay_transfer_id VARCHAR(100),
    amount_paise         BIGINT NOT NULL,
    status               VARCHAR(30) NOT NULL DEFAULT 'SIMULATED'
        CHECK (status IN ('SIMULATED','PENDING','PROCESSING','PROCESSED','FAILED','REVERSED')),
    settlement_status    VARCHAR(30) NOT NULL DEFAULT 'SIMULATED'
        CHECK (settlement_status IN ('SIMULATED','PENDING','SETTLED','FAILED')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transfers_order_id     ON transfers(order_id);
CREATE INDEX IF NOT EXISTS idx_transfers_farmer_id    ON transfers(farmer_id);
CREATE INDEX IF NOT EXISTS idx_transfers_payment_id   ON transfers(razorpay_payment_id);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_transfers_updated_at'
    ) THEN
        CREATE TRIGGER trigger_transfers_updated_at
        BEFORE UPDATE ON transfers
        FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();
    END IF;
END; $$;

-- ====================================================================
-- 7. REFUNDS — refund tracking table
-- ====================================================================
CREATE TABLE IF NOT EXISTS refunds (
    id                  SERIAL PRIMARY KEY,
    order_id            INTEGER REFERENCES orders(order_id) ON DELETE SET NULL,
    razorpay_payment_id VARCHAR(100) NOT NULL,
    razorpay_refund_id  VARCHAR(100) UNIQUE,
    amount_paise        BIGINT NOT NULL,
    reason              TEXT,
    status              VARCHAR(30) NOT NULL DEFAULT 'REQUESTED'
        CHECK (status IN ('REQUESTED','PROCESSING','PROCESSED','FAILED')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refunds_order_id ON refunds(order_id);
CREATE INDEX IF NOT EXISTS idx_refunds_payment_id ON refunds(razorpay_payment_id);

-- ====================================================================
-- 8. Indexes for new columns on payments
-- ====================================================================
CREATE INDEX IF NOT EXISTS idx_payments_rzp_order_id   ON payments(razorpay_order_id);
CREATE INDEX IF NOT EXISTS idx_payments_rzp_payment_id ON payments(razorpay_payment_id);
CREATE INDEX IF NOT EXISTS idx_razorpay_orders_order_id ON razorpay_orders(order_id);

-- ====================================================================
-- Done
-- ====================================================================
-- Tables created/altered:
--   payments (altered)
--   razorpay_orders (new)
--   razorpay_payments (new)
--   webhook_events (new)
--   farmer_accounts (new)
--   transfers (new)
--   refunds (new)
-- ====================================================================
