-- ====================================================================
-- AgriSmart Connect - Tamil Nadu Logistics & AI Marketplace Migration
-- Database: agrismart
-- Additive only: Zero data loss — does NOT drop existing tables.
-- ====================================================================

-- 1. LOCATIONS TABLE (Tamil Nadu Administrative & Agrarian Places)
CREATE TABLE IF NOT EXISTS locations (
    location_id SERIAL PRIMARY KEY,
    state VARCHAR(100) NOT NULL DEFAULT 'Tamil Nadu',
    district VARCHAR(100) NOT NULL,
    taluk VARCHAR(100),
    village_or_town VARCHAR(100) NOT NULL,
    latitude NUMERIC(10, 6) NOT NULL,
    longitude NUMERIC(10, 6) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_locations_district ON locations(district);
CREATE INDEX IF NOT EXISTS idx_locations_taluk ON locations(taluk);
CREATE INDEX IF NOT EXISTS idx_locations_village ON locations(village_or_town);

-- 2. ENHANCE HUBS TABLE
ALTER TABLE hubs
    ADD COLUMN IF NOT EXISTS taluk VARCHAR(100),
    ADD COLUMN IF NOT EXISTS town VARCHAR(100),
    ADD COLUMN IF NOT EXISTS daily_processing_capacity_kg NUMERIC(12, 2) DEFAULT 5000.00,
    ADD COLUMN IF NOT EXISTS workers INT DEFAULT 12,
    ADD COLUMN IF NOT EXISTS delivery_radius_km NUMERIC(8, 2) DEFAULT 45.00,
    ADD COLUMN IF NOT EXISTS current_inventory_kg NUMERIC(12, 2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS is_demo BOOLEAN DEFAULT TRUE;

-- 3. ENHANCE FARMER PROFILES TABLE
ALTER TABLE farmer_profiles
    ADD COLUMN IF NOT EXISTS taluk VARCHAR(100),
    ADD COLUMN IF NOT EXISTS water_availability VARCHAR(50) DEFAULT 'Canal / Borewell',
    ADD COLUMN IF NOT EXISTS crop_types TEXT,
    ADD COLUMN IF NOT EXISTS expected_harvest_date DATE,
    ADD COLUMN IF NOT EXISTS current_hub_id INTEGER REFERENCES hubs(hub_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'ACTIVE',
    ADD COLUMN IF NOT EXISTS is_demo BOOLEAN DEFAULT FALSE;

-- 4. ENHANCE FARMER PRODUCE / PRODUCTS TABLE
ALTER TABLE farmer_produce
    ADD COLUMN IF NOT EXISTS product_name VARCHAR(120),
    ADD COLUMN IF NOT EXISTS category VARCHAR(50) DEFAULT 'Vegetables',
    ADD COLUMN IF NOT EXISTS unit VARCHAR(20) DEFAULT 'kg',
    ADD COLUMN IF NOT EXISTS min_order_quantity_kg NUMERIC(10, 2) DEFAULT 1.00,
    ADD COLUMN IF NOT EXISTS expected_availability_date DATE,
    ADD COLUMN IF NOT EXISTS organic_status VARCHAR(30) DEFAULT 'conventional',
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS moderation_status VARCHAR(30) DEFAULT 'APPROVED',
    ADD COLUMN IF NOT EXISTS is_demo BOOLEAN DEFAULT FALSE;

-- Ensure farmer_produce status check constraint accommodates all required states
DO $$
BEGIN
    ALTER TABLE farmer_produce DROP CONSTRAINT IF EXISTS farmer_produce_status_check;
    ALTER TABLE farmer_produce ADD CONSTRAINT farmer_produce_status_check CHECK (
        status IN (
            'available', 'partially_reserved', 'reserved', 'sold', 'expired', 'cancelled',
            'DRAFT', 'PENDING_REVIEW', 'ACTIVE', 'OUT_OF_STOCK', 'PAUSED', 'SOLD_OUT', 'REJECTED'
        )
    );
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- 5. PRODUCT IMAGES TABLE
CREATE TABLE IF NOT EXISTS product_images (
    image_id SERIAL PRIMARY KEY,
    produce_id INTEGER NOT NULL REFERENCES farmer_produce(produce_id) ON DELETE CASCADE,
    image_url TEXT NOT NULL,
    storage_path TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    display_order INTEGER NOT NULL DEFAULT 0,
    source VARCHAR(100) DEFAULT 'Local Storage',
    source_url TEXT,
    license VARCHAR(100) DEFAULT 'Licensed',
    attribution TEXT,
    alt_text VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_product_images_produce ON product_images(produce_id);
CREATE INDEX IF NOT EXISTS idx_product_images_primary ON product_images(produce_id, is_primary);

-- 6. DELIVERY ROUTES TABLE (For OR-Tools Optimization)
CREATE TABLE IF NOT EXISTS routes (
    route_id SERIAL PRIMARY KEY,
    hub_id INTEGER NOT NULL REFERENCES hubs(hub_id) ON DELETE CASCADE,
    delivery_partner_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    total_distance_km NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    estimated_time_minutes INTEGER NOT NULL DEFAULT 0,
    vehicle_capacity_kg NUMERIC(10, 2) NOT NULL DEFAULT 1000.00,
    capacity_used_kg NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    delivery_count INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL DEFAULT 'PLANNED' CHECK (status IN ('PLANNED', 'ASSIGNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 7. ROUTE STOPS TABLE
CREATE TABLE IF NOT EXISTS route_stops (
    stop_id SERIAL PRIMARY KEY,
    route_id INTEGER NOT NULL REFERENCES routes(route_id) ON DELETE CASCADE,
    order_id INTEGER REFERENCES orders(order_id) ON DELETE SET NULL,
    stop_sequence INTEGER NOT NULL,
    customer_name VARCHAR(100),
    delivery_address TEXT NOT NULL,
    latitude NUMERIC(10, 6) NOT NULL,
    longitude NUMERIC(10, 6) NOT NULL,
    quantity_kg NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ARRIVED', 'DELIVERED', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_route_stops_route_id ON route_stops(route_id);

-- 8. DEMAND PREDICTIONS TABLE (XGBoost Demand Forecaster Store)
CREATE TABLE IF NOT EXISTS demand_predictions (
    prediction_id SERIAL PRIMARY KEY,
    crop_id INTEGER NOT NULL REFERENCES crops(crop_id) ON DELETE CASCADE,
    district VARCHAR(100) NOT NULL,
    target_date DATE NOT NULL,
    predicted_demand_kg NUMERIC(10, 2) NOT NULL,
    confidence NUMERIC(5, 2) NOT NULL DEFAULT 0.85,
    demand_level VARCHAR(20) NOT NULL DEFAULT 'MEDIUM' CHECK (demand_level IN ('LOW', 'MEDIUM', 'HIGH')),
    is_simulated BOOLEAN NOT NULL DEFAULT FALSE,
    model_type VARCHAR(50) DEFAULT 'XGBoost-Reg',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_demand_predictions_query ON demand_predictions(crop_id, district, target_date);

-- 9. LOGISTICS RECOMMENDATIONS TABLE (Farmer-Hub Matching Store)
CREATE TABLE IF NOT EXISTS logistics_recommendations (
    recommendation_id SERIAL PRIMARY KEY,
    farmer_id INTEGER REFERENCES farmer_profiles(farmer_id) ON DELETE CASCADE,
    produce_id INTEGER REFERENCES farmer_produce(produce_id) ON DELETE CASCADE,
    hub_id INTEGER REFERENCES hubs(hub_id) ON DELETE CASCADE,
    distance_km NUMERIC(10, 2) NOT NULL,
    recommended_reason TEXT NOT NULL,
    priority_level VARCHAR(20) DEFAULT 'NORMAL',
    status VARCHAR(30) DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_logistics_rec_farmer ON logistics_recommendations(farmer_id);
CREATE INDEX IF NOT EXISTS idx_logistics_rec_hub ON logistics_recommendations(hub_id);
