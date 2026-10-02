-- ====================================================================
-- AgriSmart Connect - Product Images Metadata & Audit Log Migration
-- ====================================================================

-- 1. Extend product_images with attribution, license, and source metadata
ALTER TABLE product_images ADD COLUMN IF NOT EXISTS source VARCHAR(100) DEFAULT 'Local Storage';
ALTER TABLE product_images ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE product_images ADD COLUMN IF NOT EXISTS license VARCHAR(100) DEFAULT 'Licensed';
ALTER TABLE product_images ADD COLUMN IF NOT EXISTS attribution TEXT;
ALTER TABLE product_images ADD COLUMN IF NOT EXISTS alt_text VARCHAR(255);

-- 2. Create demo_image_audit_log table for tracking modifications safely
CREATE TABLE IF NOT EXISTS demo_image_audit_log (
    log_id SERIAL PRIMARY KEY,
    produce_id INTEGER NOT NULL REFERENCES farmer_produce(produce_id) ON DELETE CASCADE,
    product_name VARCHAR(150),
    crop_name VARCHAR(100),
    farmer_id INTEGER,
    farmer_email VARCHAR(120),
    old_image TEXT,
    new_image TEXT,
    image_source VARCHAR(100),
    source_url TEXT,
    license VARCHAR(100),
    action VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_demo_image_audit_produce ON demo_image_audit_log(produce_id);
CREATE INDEX IF NOT EXISTS idx_demo_image_audit_created ON demo_image_audit_log(created_at);
