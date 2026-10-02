-- ====================================================================
-- AgriSmart Connect - Multi-Hub Marketplace, Logistics, Payment & Settlement Migration
-- NextGen Harvest Team
-- Database: agrismart
-- Additive only: Zero data loss — ensures backward and forward compatibility.
-- ====================================================================

-- 1. Relax/Extend Users Role Check Constraint
DO $$
BEGIN
    ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
    ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (
        role IN (
            'farmer', 'consumer', 'restaurant', 'retailer',
            'delivery_partner', 'admin', 'hub_operator',
            'hub_staff', 'hub_manager'
        )
    );
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- Add assigned_hub_id to users for hub-level permissions
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS assigned_hub_id INTEGER REFERENCES hubs(hub_id) ON DELETE SET NULL;

-- 2. Enhance HUBS Table with Multi-Hub Attributes
ALTER TABLE hubs
    ADD COLUMN IF NOT EXISTS hub_code VARCHAR(50),
    ADD COLUMN IF NOT EXISTS city VARCHAR(100),
    ADD COLUMN IF NOT EXISTS pincode VARCHAR(20),
    ADD COLUMN IF NOT EXISTS geofence_radius NUMERIC(10, 2) DEFAULT 500.00,
    ADD COLUMN IF NOT EXISTS service_radius NUMERIC(10, 2) DEFAULT 50.00,
    ADD COLUMN IF NOT EXISTS daily_capacity INT DEFAULT 1000,
    ADD COLUMN IF NOT EXISTS current_capacity INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS operating_hours VARCHAR(100) DEFAULT '06:00 AM - 08:00 PM',
    ADD COLUMN IF NOT EXISTS cold_storage_available BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS storage_capabilities JSONB DEFAULT '{"cold_storage": false, "ripening_chamber": false, "ambient_dry": true}'::jsonb,
    ADD COLUMN IF NOT EXISTS supported_products TEXT DEFAULT 'Vegetables, Fruits, Tubers, Spices, Grains',
    ADD COLUMN IF NOT EXISTS manager_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL;

-- Relax hubs status constraint to support ACTIVE, INACTIVE, FULL, TEMPORARILY_CLOSED
DO $$
BEGIN
    ALTER TABLE hubs DROP CONSTRAINT IF EXISTS hubs_status_check;
    ALTER TABLE hubs ADD CONSTRAINT hubs_status_check CHECK (
        status IN (
            'active', 'inactive', 'maintenance',
            'ACTIVE', 'INACTIVE', 'FULL', 'TEMPORARILY_CLOSED'
        )
    );
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- Populate hub_code and defaults if null
UPDATE hubs SET hub_code = 'HUB-' || UPPER(SUBSTRING(COALESCE(district, 'TN') FROM 1 FOR 3)) || '-' || LPAD(hub_id::text, 2, '0')
WHERE hub_code IS NULL;

-- 3. Relax ORDERS table status constraints and add routing & OTP columns
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS source_hub_id INTEGER REFERENCES hubs(hub_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS destination_hub_id INTEGER REFERENCES hubs(hub_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS delivery_otp VARCHAR(10),
    ADD COLUMN IF NOT EXISTS delivery_otp_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS delivery_otp_attempts INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS delivery_otp_verified BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS requires_hub_transfer BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
    ADD COLUMN IF NOT EXISTS cancellation_reason TEXT,
    ADD COLUMN IF NOT EXISTS current_route_sequence INT DEFAULT 1;

DO $$
BEGIN
    ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_order_status_check;
    -- We allow both legacy and all new state machine statuses
    ALTER TABLE orders ADD CONSTRAINT orders_order_status_check CHECK (
        order_status IN (
            'placed', 'confirmed', 'farmer_assigned', 'collecting',
            'at_hub', 'quality_checked', 'packed', 'out_for_delivery',
            'delivered', 'cancelled',
            'PAYMENT_PENDING', 'PAYMENT_SUCCESS', 'ORDER_CONFIRMED',
            'FARMER_ACCEPTED', 'FARMER_PREPARING', 'READY_FOR_PICKUP',
            'PICKUP_ASSIGNED', 'PICKED_UP', 'IN_TRANSIT_TO_HUB',
            'ARRIVED_AT_HUB', 'HUB_QC', 'HUB_ACCEPTED', 'HUB_TRANSFER_REQUIRED',
            'IN_TRANSIT_TO_NEXT_HUB', 'ARRIVED_AT_NEXT_HUB', 'ASSIGNED_TO_DELIVERY',
            'OUT_FOR_DELIVERY', 'DELIVERY_OTP_VERIFICATION', 'DELIVERED',
            'SETTLEMENT_PROCESSING', 'SETTLED',
            'PAYMENT_FAILED', 'FARMER_REJECTED', 'OUT_OF_STOCK',
            'ORDER_CANCELLED', 'PICKUP_FAILED', 'QC_FAILED', 'HUB_REJECTED',
            'TRANSFER_FAILED', 'DELIVERY_FAILED', 'CUSTOMER_UNAVAILABLE',
            'REFUND_PENDING', 'REFUNDED', 'PAYOUT_FAILED'
        )
    );
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_payment_status_check;
    ALTER TABLE orders ADD CONSTRAINT orders_payment_status_check CHECK (
        payment_status IN (
            'pending', 'paid', 'failed', 'refunded', 'partially_refunded',
            'PENDING', 'SUCCESS', 'FAILED', 'REFUND_PENDING', 'REFUNDED'
        )
    );
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- 4. ORDER EVENTS TABLE (Full Audit Timeline)
CREATE TABLE IF NOT EXISTS order_events (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    previous_status VARCHAR(60),
    new_status VARCHAR(60) NOT NULL,
    actor_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    actor_role VARCHAR(50),
    location VARCHAR(255),
    latitude NUMERIC(10, 6),
    longitude NUMERIC(10, 6),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_order_events_order_id ON order_events(order_id);
CREATE INDEX IF NOT EXISTS idx_order_events_timestamp ON order_events(timestamp);

-- 5. ORDER ROUTES TABLE (Multi-Leg Journey Management)
CREATE TABLE IF NOT EXISTS order_routes (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    sequence_number INTEGER NOT NULL,
    route_type VARCHAR(50) NOT NULL, -- 'FARMER_TO_HUB', 'HUB_TO_HUB', 'HUB_TO_CUSTOMER'
    source_location TEXT,
    destination_location TEXT,
    source_hub_id INTEGER REFERENCES hubs(hub_id) ON DELETE SET NULL,
    destination_hub_id INTEGER REFERENCES hubs(hub_id) ON DELETE SET NULL,
    delivery_partner_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'ASSIGNED', 'IN_TRANSIT', 'COMPLETED', 'FAILED'
    started_at TIMESTAMPTZ,
    arrived_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_order_routes_order ON order_routes(order_id);
CREATE INDEX IF NOT EXISTS idx_order_routes_partner ON order_routes(delivery_partner_id);

-- 6. HUB TRANSFERS TABLE (Inter-Hub Movement)
CREATE TABLE IF NOT EXISTS hub_transfers (
    transfer_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    source_hub_id INTEGER NOT NULL REFERENCES hubs(hub_id) ON DELETE RESTRICT,
    destination_hub_id INTEGER NOT NULL REFERENCES hubs(hub_id) ON DELETE RESTRICT,
    delivery_partner_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'TRANSFER_CREATED', -- 'TRANSFER_CREATED', 'READY_FOR_TRANSFER', 'PICKED_UP_FROM_HUB', 'IN_TRANSIT', 'ARRIVED_DESTINATION_HUB', 'RECEIVED', 'TRANSFER_FAILED'
    pickup_time TIMESTAMPTZ,
    departure_time TIMESTAMPTZ,
    arrival_time TIMESTAMPTZ,
    received_time TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_hub_transfers_order ON hub_transfers(order_id);
CREATE INDEX IF NOT EXISTS idx_hub_transfers_src ON hub_transfers(source_hub_id);
CREATE INDEX IF NOT EXISTS idx_hub_transfers_dst ON hub_transfers(destination_hub_id);

-- 7. HUB STAFF TABLE
CREATE TABLE IF NOT EXISTS hub_staff (
    id SERIAL PRIMARY KEY,
    hub_id INTEGER NOT NULL REFERENCES hubs(hub_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    staff_role VARCHAR(50) DEFAULT 'STAFF', -- 'STAFF', 'INSPECTOR', 'MANAGER'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_hub_staff UNIQUE(hub_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_hub_staff_hub ON hub_staff(hub_id);
CREATE INDEX IF NOT EXISTS idx_hub_staff_user ON hub_staff(user_id);

-- 8. FARMER PAYOUT ACCOUNTS (Bank Account / UPI Optional)
CREATE TABLE IF NOT EXISTS farmer_payout_accounts (
    id SERIAL PRIMARY KEY,
    farmer_id INTEGER NOT NULL UNIQUE REFERENCES farmer_profiles(farmer_id) ON DELETE CASCADE,
    account_holder_name VARCHAR(150) NOT NULL,
    bank_account_number VARCHAR(50) NOT NULL,
    bank_name VARCHAR(100) DEFAULT 'State Bank of India',
    IFSC VARCHAR(20) NOT NULL,
    UPI_ID VARCHAR(100),
    UPI_available BOOLEAN NOT NULL DEFAULT FALSE,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'VERIFIED',
    payout_provider_reference VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_farmer_payout_acc_farmer ON farmer_payout_accounts(farmer_id);

-- 9. MULTI-PARTY SETTLEMENTS LEDGER
CREATE TABLE IF NOT EXISTS settlements (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    beneficiary_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    beneficiary_name VARCHAR(150),
    beneficiary_type VARCHAR(50) NOT NULL, -- 'FARMER', 'DELIVERY_PARTNER', 'HUB', 'PLATFORM', 'OTHER'
    amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
    settlement_type VARCHAR(50) NOT NULL, -- 'FARMER_PAYOUT', 'DELIVERY_FEE', 'HUB_COMMISSION', 'PLATFORM_FEE', 'OTHER'
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'PROCESSING', 'PAID', 'FAILED'
    payout_reference VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_settlements_order ON settlements(order_id);
CREATE INDEX IF NOT EXISTS idx_settlements_beneficiary ON settlements(beneficiary_id);
CREATE INDEX IF NOT EXISTS idx_settlements_status ON settlements(status);

-- 10. DELIVERY PARTNER LOCATIONS (Live Active Trip GPS)
CREATE TABLE IF NOT EXISTS delivery_partner_locations (
    id SERIAL PRIMARY KEY,
    delivery_partner_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    order_id INTEGER REFERENCES orders(order_id) ON DELETE SET NULL,
    latitude NUMERIC(10, 6) NOT NULL,
    longitude NUMERIC(10, 6) NOT NULL,
    speed_kmh NUMERIC(5, 2) DEFAULT 0.0,
    heading NUMERIC(5, 2) DEFAULT 0.0,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_partner_locations ON delivery_partner_locations(delivery_partner_id, timestamp);

-- 11. DELIVERY EARNINGS TABLE
CREATE TABLE IF NOT EXISTS delivery_earnings (
    id SERIAL PRIMARY KEY,
    delivery_partner_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    order_id INTEGER REFERENCES orders(order_id) ON DELETE CASCADE,
    delivery_fee NUMERIC(10, 2) NOT NULL DEFAULT 50.00,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'ELIGIBLE', 'PROCESSING', 'PAID', 'FAILED'
    payout_reference VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_delivery_earnings_partner ON delivery_earnings(delivery_partner_id);
CREATE INDEX IF NOT EXISTS idx_delivery_earnings_order ON delivery_earnings(order_id);

-- 12. ENHANCE NOTIFICATIONS TABLE
ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS order_id INTEGER REFERENCES orders(order_id) ON DELETE SET NULL;
