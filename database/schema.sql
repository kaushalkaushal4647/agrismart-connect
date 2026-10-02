-- ====================================================================
-- AgriSmart Connect - Complete Relational PostgreSQL Schema
-- Database: agrismart
-- Author: AgriSmart Core Engineering Team
-- ====================================================================

-- Enable UUID extension if needed in future
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ====================================================================
-- AUTOMATIC TIMESTAMP TRIGGER FUNCTION
-- ====================================================================
CREATE OR REPLACE FUNCTION update_timestamp_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ====================================================================
-- 1. USERS TABLE
-- Primary identity store for all actors (farmers, buyers, hub operators, etc.)
-- ====================================================================
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(30) NOT NULL CHECK (role IN (
        'farmer',
        'consumer',
        'restaurant',
        'retailer',
        'delivery_partner',
        'admin',
        'hub_operator'
    )),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trigger_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- ====================================================================
-- 2. FARMER PROFILES TABLE
-- 1-to-1 extension of users for agricultural producers
-- ====================================================================
CREATE TABLE IF NOT EXISTS farmer_profiles (
    farmer_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    farm_name VARCHAR(120),
    village VARCHAR(100),
    district VARCHAR(100),
    state VARCHAR(100),
    latitude NUMERIC(10, 6),
    longitude NUMERIC(10, 6),
    farm_size NUMERIC(10, 2) CHECK (farm_size IS NULL OR farm_size >= 0),
    address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trigger_farmer_profiles_updated_at
BEFORE UPDATE ON farmer_profiles
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- ====================================================================
-- 3. BUYERS TABLE
-- 1-to-1 extension of users for consumers, restaurants, and retailers
-- ====================================================================
CREATE TABLE IF NOT EXISTS buyers (
    buyer_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    buyer_type VARCHAR(30) NOT NULL CHECK (buyer_type IN ('consumer', 'restaurant', 'retailer')),
    business_name VARCHAR(150),
    address TEXT,
    village VARCHAR(100),
    district VARCHAR(100),
    latitude NUMERIC(10, 6),
    longitude NUMERIC(10, 6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trigger_buyers_updated_at
BEFORE UPDATE ON buyers
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- ====================================================================
-- 4. CROPS TABLE
-- Catalog of agricultural crops
-- ====================================================================
CREATE TABLE IF NOT EXISTS crops (
    crop_id SERIAL PRIMARY KEY,
    crop_name VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- 5. VARIETIES TABLE
-- Specific varieties/cultivars per crop (e.g. Hybrid, Desi, Cherry)
-- ====================================================================
CREATE TABLE IF NOT EXISTS varieties (
    variety_id SERIAL PRIMARY KEY,
    crop_id INTEGER NOT NULL REFERENCES crops(crop_id) ON DELETE CASCADE,
    variety_name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT unique_crop_variety UNIQUE (crop_id, variety_name)
);

-- ====================================================================
-- 6. HUBS TABLE
-- Local collection, aggregation, quality-check, and dispatch centers
-- ====================================================================
CREATE TABLE IF NOT EXISTS hubs (
    hub_id SERIAL PRIMARY KEY,
    hub_name VARCHAR(120) NOT NULL,
    address TEXT NOT NULL,
    village VARCHAR(100),
    district VARCHAR(100) NOT NULL,
    latitude NUMERIC(10, 6) NOT NULL,
    longitude NUMERIC(10, 6) NOT NULL,
    capacity_kg NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (capacity_kg >= 0),
    operating_start TIME NOT NULL DEFAULT '06:00:00',
    operating_end TIME NOT NULL DEFAULT '20:00:00',
    status VARCHAR(30) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'maintenance')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trigger_hubs_updated_at
BEFORE UPDATE ON hubs
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- ====================================================================
-- 7. FARMER PRODUCE TABLE
-- Available / upcoming harvest listings submitted by farmers
-- ====================================================================
CREATE TABLE IF NOT EXISTS farmer_produce (
    produce_id SERIAL PRIMARY KEY,
    farmer_id INTEGER NOT NULL REFERENCES farmer_profiles(farmer_id) ON DELETE CASCADE,
    crop_id INTEGER NOT NULL REFERENCES crops(crop_id) ON DELETE RESTRICT,
    variety_id INTEGER REFERENCES varieties(variety_id) ON DELETE SET NULL,
    expected_quantity_kg NUMERIC(10, 2) NOT NULL CHECK (expected_quantity_kg >= 0),
    available_quantity_kg NUMERIC(10, 2) NOT NULL CHECK (available_quantity_kg >= 0),
    reserved_quantity_kg NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (reserved_quantity_kg >= 0),
    sold_quantity_kg NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (sold_quantity_kg >= 0),
    minimum_price_per_kg NUMERIC(10, 2) NOT NULL CHECK (minimum_price_per_kg >= 0),
    harvest_date DATE NOT NULL,
    quality_grade VARCHAR(20) DEFAULT 'Grade A',
    latitude NUMERIC(10, 6),
    longitude NUMERIC(10, 6),
    preferred_hub_id INTEGER REFERENCES hubs(hub_id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'available' CHECK (status IN (
        'available',
        'partially_reserved',
        'reserved',
        'sold',
        'expired',
        'cancelled'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_produce_quantities_sum 
        CHECK (available_quantity_kg + reserved_quantity_kg + sold_quantity_kg <= expected_quantity_kg * 1.5)
);

CREATE TRIGGER trigger_farmer_produce_updated_at
BEFORE UPDATE ON farmer_produce
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- ====================================================================
-- 8. DEMAND RECORDS TABLE
-- Direct buyer requirements and bulk B2B demand entries
-- ====================================================================
CREATE TABLE IF NOT EXISTS demand_records (
    demand_id SERIAL PRIMARY KEY,
    buyer_id INTEGER NOT NULL REFERENCES buyers(buyer_id) ON DELETE CASCADE,
    crop_id INTEGER NOT NULL REFERENCES crops(crop_id) ON DELETE RESTRICT,
    variety_id INTEGER REFERENCES varieties(variety_id) ON DELETE SET NULL,
    required_quantity_kg NUMERIC(10, 2) NOT NULL CHECK (required_quantity_kg > 0),
    required_date DATE NOT NULL,
    latitude NUMERIC(10, 6),
    longitude NUMERIC(10, 6),
    buyer_type VARCHAR(30) NOT NULL CHECK (buyer_type IN ('consumer', 'restaurant', 'retailer')),
    source VARCHAR(30) NOT NULL DEFAULT 'portal' CHECK (source IN ('portal', 'recurring', 'b2b_contract', 'manual')),
    status VARCHAR(30) NOT NULL DEFAULT 'open' CHECK (status IN (
        'open',
        'partially_matched',
        'matched',
        'fulfilled',
        'cancelled'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trigger_demand_records_updated_at
BEFORE UPDATE ON demand_records
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- ====================================================================
-- 9. ORDERS TABLE
-- High-level purchase transaction record
-- ====================================================================
CREATE TABLE IF NOT EXISTS orders (
    order_id SERIAL PRIMARY KEY,
    buyer_id INTEGER NOT NULL REFERENCES buyers(buyer_id) ON DELETE RESTRICT,
    hub_id INTEGER REFERENCES hubs(hub_id) ON DELETE SET NULL,
    order_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivery_address TEXT NOT NULL,
    delivery_latitude NUMERIC(10, 6),
    delivery_longitude NUMERIC(10, 6),
    subtotal NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (subtotal >= 0),
    delivery_fee NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (delivery_fee >= 0),
    platform_fee NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (platform_fee >= 0),
    total_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (total_amount >= 0),
    payment_status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (payment_status IN (
        'pending',
        'paid',
        'failed',
        'refunded',
        'partially_refunded'
    )),
    order_status VARCHAR(30) NOT NULL DEFAULT 'placed' CHECK (order_status IN (
        'placed',
        'confirmed',
        'farmer_assigned',
        'collecting',
        'at_hub',
        'quality_checked',
        'packed',
        'out_for_delivery',
        'delivered',
        'cancelled'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trigger_orders_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- ====================================================================
-- 10. ORDER ITEMS TABLE
-- Individual produce line-items allocated to farmers within an order
-- ====================================================================
CREATE TABLE IF NOT EXISTS order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    produce_id INTEGER REFERENCES farmer_produce(produce_id) ON DELETE SET NULL,
    crop_id INTEGER NOT NULL REFERENCES crops(crop_id) ON DELETE RESTRICT,
    variety_id INTEGER REFERENCES varieties(variety_id) ON DELETE SET NULL,
    farmer_id INTEGER NOT NULL REFERENCES farmer_profiles(farmer_id) ON DELETE RESTRICT,
    quantity_kg NUMERIC(10, 2) NOT NULL CHECK (quantity_kg > 0),
    price_per_kg NUMERIC(10, 2) NOT NULL CHECK (price_per_kg >= 0),
    subtotal NUMERIC(10, 2) NOT NULL CHECK (subtotal >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- 11. HUB INVENTORY TABLE
-- Batches physically aggregated in hubs post collection
-- ====================================================================
CREATE TABLE IF NOT EXISTS hub_inventory (
    inventory_id SERIAL PRIMARY KEY,
    hub_id INTEGER NOT NULL REFERENCES hubs(hub_id) ON DELETE CASCADE,
    produce_id INTEGER REFERENCES farmer_produce(produce_id) ON DELETE SET NULL,
    crop_id INTEGER NOT NULL REFERENCES crops(crop_id) ON DELETE RESTRICT,
    variety_id INTEGER REFERENCES varieties(variety_id) ON DELETE SET NULL,
    available_quantity_kg NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (available_quantity_kg >= 0),
    reserved_quantity_kg NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (reserved_quantity_kg >= 0),
    sold_quantity_kg NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (sold_quantity_kg >= 0),
    quality_grade VARCHAR(20) DEFAULT 'Grade A',
    harvest_date DATE,
    expected_expiry_date DATE,
    status VARCHAR(30) NOT NULL DEFAULT 'available' CHECK (status IN (
        'available',
        'reserved',
        'dispatched',
        'surplus',
        'spoiled'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trigger_hub_inventory_updated_at
BEFORE UPDATE ON hub_inventory
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- ====================================================================
-- 12. QUALITY CHECKS TABLE
-- Physical inspection logs recorded by hub operators upon arrival
-- ====================================================================
CREATE TABLE IF NOT EXISTS quality_checks (
    quality_check_id SERIAL PRIMARY KEY,
    inventory_id INTEGER REFERENCES hub_inventory(inventory_id) ON DELETE SET NULL,
    hub_id INTEGER NOT NULL REFERENCES hubs(hub_id) ON DELETE CASCADE,
    inspector_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    actual_weight_kg NUMERIC(10, 2) NOT NULL CHECK (actual_weight_kg >= 0),
    quality_grade VARCHAR(20) NOT NULL,
    rejected_quantity_kg NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (rejected_quantity_kg >= 0),
    remarks TEXT,
    inspection_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- 13. DELIVERIES TABLE
-- Dispatch coordinates from collection hubs to buyers
-- ====================================================================
CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL UNIQUE REFERENCES orders(order_id) ON DELETE CASCADE,
    hub_id INTEGER NOT NULL REFERENCES hubs(hub_id) ON DELETE RESTRICT,
    delivery_partner_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    pickup_time TIMESTAMPTZ,
    delivery_time TIMESTAMPTZ,
    delivery_address TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'assigned' CHECK (status IN (
        'assigned',
        'picked_up',
        'in_transit',
        'delivered',
        'failed',
        'cancelled'
    )),
    tracking_reference VARCHAR(100) UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trigger_deliveries_updated_at
BEFORE UPDATE ON deliveries
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- ====================================================================
-- 14. PAYMENTS TABLE
-- Buyer transaction receipts and platform revenue splits
-- ====================================================================
CREATE TABLE IF NOT EXISTS payments (
    payment_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL UNIQUE REFERENCES orders(order_id) ON DELETE CASCADE,
    buyer_amount NUMERIC(10, 2) NOT NULL CHECK (buyer_amount >= 0),
    delivery_fee NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (delivery_fee >= 0),
    platform_fee NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (platform_fee >= 0),
    farmer_amount NUMERIC(10, 2) NOT NULL CHECK (farmer_amount >= 0),
    payment_method VARCHAR(50) NOT NULL DEFAULT 'UPI',
    transaction_reference VARCHAR(100) UNIQUE,
    payment_status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (payment_status IN (
        'pending',
        'paid',
        'failed',
        'refunded',
        'partially_refunded'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- 15. FARMER PAYOUTS TABLE
-- Earnings disbursement records payable to farmers per fulfilled batch
-- ====================================================================
CREATE TABLE IF NOT EXISTS farmer_payouts (
    payout_id SERIAL PRIMARY KEY,
    farmer_id INTEGER NOT NULL REFERENCES farmer_profiles(farmer_id) ON DELETE CASCADE,
    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    gross_amount NUMERIC(10, 2) NOT NULL CHECK (gross_amount >= 0),
    platform_fee NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (platform_fee >= 0),
    other_deductions NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (other_deductions >= 0),
    net_amount NUMERIC(10, 2) NOT NULL CHECK (net_amount >= 0),
    payout_status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (payout_status IN (
        'pending',
        'processing',
        'paid',
        'failed'
    )),
    payout_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_net_amount_math 
        CHECK (net_amount = gross_amount - platform_fee - other_deductions)
);

-- ====================================================================
-- 16. NOTIFICATIONS TABLE
-- Real-time & in-app alerts for users
-- ====================================================================
CREATE TABLE IF NOT EXISTS notifications (
    notification_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title VARCHAR(150) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(50) NOT NULL DEFAULT 'system',
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- 17. REVIEWS TABLE
-- Buyer feedback on farmers, produce quality, and fulfillment
-- ====================================================================
CREATE TABLE IF NOT EXISTS reviews (
    review_id SERIAL PRIMARY KEY,
    buyer_id INTEGER NOT NULL REFERENCES buyers(buyer_id) ON DELETE CASCADE,
    order_id INTEGER REFERENCES orders(order_id) ON DELETE SET NULL,
    farmer_id INTEGER REFERENCES farmer_profiles(farmer_id) ON DELETE SET NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- 18. DEMAND FORECASTS TABLE
-- Historical and projected crop demand for intelligent supply-planning
-- ====================================================================
CREATE TABLE IF NOT EXISTS demand_forecasts (
    forecast_id SERIAL PRIMARY KEY,
    crop_id INTEGER NOT NULL REFERENCES crops(crop_id) ON DELETE CASCADE,
    variety_id INTEGER REFERENCES varieties(variety_id) ON DELETE SET NULL,
    location VARCHAR(150) NOT NULL,
    forecast_date DATE NOT NULL,
    predicted_quantity_kg NUMERIC(10, 2) NOT NULL CHECK (predicted_quantity_kg >= 0),
    confidence NUMERIC(5, 2) DEFAULT 0.80 CHECK (confidence >= 0 AND confidence <= 1.00),
    model_version VARCHAR(50) DEFAULT 'v1.0-moving-average',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- PERFORMANCE INDEXES
-- Optimized for search, matching engine, and relationship joins
-- ====================================================================
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

CREATE INDEX IF NOT EXISTS idx_farmer_profiles_user_id ON farmer_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_buyers_user_id ON buyers(user_id);
CREATE INDEX IF NOT EXISTS idx_buyers_buyer_type ON buyers(buyer_type);

CREATE INDEX IF NOT EXISTS idx_varieties_crop_id ON varieties(crop_id);

CREATE INDEX IF NOT EXISTS idx_farmer_produce_farmer_id ON farmer_produce(farmer_id);
CREATE INDEX IF NOT EXISTS idx_farmer_produce_crop_id ON farmer_produce(crop_id);
CREATE INDEX IF NOT EXISTS idx_farmer_produce_variety_id ON farmer_produce(variety_id);
CREATE INDEX IF NOT EXISTS idx_farmer_produce_harvest_date ON farmer_produce(harvest_date);
CREATE INDEX IF NOT EXISTS idx_farmer_produce_status ON farmer_produce(status);

-- Composite Index specifically for matching engine query:
CREATE INDEX IF NOT EXISTS idx_produce_matching 
ON farmer_produce(crop_id, variety_id, status, harvest_date);

CREATE INDEX IF NOT EXISTS idx_demand_records_crop_id ON demand_records(crop_id);
CREATE INDEX IF NOT EXISTS idx_demand_records_required_date ON demand_records(required_date);
CREATE INDEX IF NOT EXISTS idx_demand_records_status ON demand_records(status);

CREATE INDEX IF NOT EXISTS idx_orders_buyer_id ON orders(buyer_id);
CREATE INDEX IF NOT EXISTS idx_orders_order_status ON orders(order_status);
CREATE INDEX IF NOT EXISTS idx_orders_payment_status ON orders(payment_status);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_produce_id ON order_items(produce_id);
CREATE INDEX IF NOT EXISTS idx_order_items_farmer_id ON order_items(farmer_id);

CREATE INDEX IF NOT EXISTS idx_hub_inventory_hub_id ON hub_inventory(hub_id);
CREATE INDEX IF NOT EXISTS idx_hub_inventory_crop_id ON hub_inventory(crop_id);

CREATE INDEX IF NOT EXISTS idx_quality_checks_hub_id ON quality_checks(hub_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_order_id ON deliveries(order_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_partner_id ON deliveries(delivery_partner_id);

CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_farmer_payouts_farmer_id ON farmer_payouts(farmer_id);
CREATE INDEX IF NOT EXISTS idx_farmer_payouts_order_id ON farmer_payouts(order_id);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_reviews_farmer_id ON reviews(farmer_id);
CREATE INDEX IF NOT EXISTS idx_reviews_buyer_id ON reviews(buyer_id);
