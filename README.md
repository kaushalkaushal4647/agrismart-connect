# AgriSmart Connect - Demand-Matched Agricultural Marketplace

AgriSmart Connect is a specialized agricultural supply-demand matching platform built with **Flask**, **Psycopg 3**, and **PostgreSQL**.

Unlike generic e-commerce platforms, AgriSmart Connect coordinates farmer supply with local buyer demand (consumers, restaurants, retailers) and manages physical aggregation, quality inspection, and dispatch via regional collection hubs.

---

## 1. Relational Database Architecture (18 Tables)

The database `agrismart` is defined in [`database/schema.sql`](database/schema.sql). Below is a complete breakdown of every table, its purpose, and relationships:

### Core Identity & Profiles
1. **`users`**: Central credentials and identity table. Enforces unique `phone` and `email`. Stores hashed passwords and assigns one of 7 roles (`farmer`, `consumer`, `restaurant`, `retailer`, `delivery_partner`, `admin`, `hub_operator`).
2. **`farmer_profiles`**: 1-to-1 extension of `users` (`user_id` FK). Stores farm location (village, district, state, latitude, longitude), farm size, and physical address.
3. **`buyers`**: 1-to-1 extension of `users` (`user_id` FK). Distinguishes `consumer`, `restaurant`, and `retailer`. Stores business name, delivery address, and geographic coordinates.

### Agricultural Catalog & Supply
4. **`crops`**: Master crop catalog (e.g. Tomato, Potato, Onion, Rice) with category and descriptions.
5. **`varieties`**: Sub-cultivars per crop (e.g. Hybrid, Desi, Roma, Cherry) linked via FK `crop_id`.
6. **`farmer_produce`**: Farmer crop listings with `expected_quantity_kg`, `available_quantity_kg`, `reserved_quantity_kg`, `sold_quantity_kg`, `harvest_date`, `minimum_price_per_kg`, `quality_grade`, and `preferred_hub_id`.
   - *Inventory safety*: A `CHECK` constraint guarantees that `available + reserved + sold` does not exceed the allowed batch limit.

### Hub Operations & Demand
7. **`hubs`**: Regional aggregation centers. Contains physical location (`latitude`, `longitude`, `district`), operating hours (`operating_start`, `operating_end`), and capacity in kg.
8. **`demand_records`**: Open requirements submitted by buyers or recurring B2B contracts (e.g. 100 kg Hybrid Tomato needed by Friday). Tracks status (`open`, `partially_matched`, `matched`, `fulfilled`).

### Orders & Line Items
9. **`orders`**: Transaction header linking `buyer_id` and assigned `hub_id`. Tracks total amount, `subtotal`, `delivery_fee`, `platform_fee`, `payment_status`, and `order_status` (`placed`, `confirmed`, `collecting`, `at_hub`, `quality_checked`, `packed`, `out_for_delivery`, `delivered`).
10. **`order_items`**: Produce lines allocated to specific farmers (`farmer_id`, `produce_id`, `crop_id`, `variety_id`), maintaining exact kg and unit price.

### Hub Quality & Logistics
11. **`hub_inventory`**: In-hub stock physically received from farmers. Tracks batch grades, harvest date, and expected expiry to prevent spoilage.
12. **`quality_checks`**: Quality audit logs recorded by hub inspectors upon arrival (actual weight vs expected, quality grade, rejected kg, remarks).
13. **`deliveries`**: Hub-to-buyer dispatch records assigned to a delivery partner (`pickup_time`, `delivery_time`, `tracking_reference`, `status`).

### Financials & Feedback
14. **`payments`**: Buyer payment records with revenue distribution: `buyer_amount`, `delivery_fee`, `platform_fee`, and `farmer_amount`.
15. **`farmer_payouts`**: Payout ledger per farmer per order (`gross_amount`, `platform_fee`, `other_deductions`, `net_amount`, `payout_status`).
16. **`notifications`**: Targeted system notifications for farmers, buyers, and hub operators.
17. **`reviews`**: Ratings (1 to 5 stars) and comments on produce and fulfillment.
18. **`demand_forecasts`**: Time-series demand predictions by crop, variety, and location for intelligent planning.

---

## 2. Quickstart & Setup Guide

### Step 1: PostgreSQL Installation
If you do not already have PostgreSQL installed on Windows:

**Option A: Using winget (PowerShell as Administrator)**
```powershell
winget install PostgreSQL.PostgreSQL
```

**Option B: Official Graphical Installer**
Download and run the Windows installer from [PostgreSQL Official Downloads](https://www.postgresql.org/download/windows/).
- Keep the default port: `5432`
- Remember the password you set for the `postgres` superuser (e.g. `postgres` or your personal password).

### Step 2: Configure Environment Variables
Check the `.env` file in the project root:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=agrismart
DB_USER=postgres
DB_PASSWORD=your_postgres_password_here
FLASK_PORT=5000
```
> If your `postgres` password is not `postgres`, change `DB_PASSWORD` to your actual password.

### Step 3: Initialize the Database
Run the automated initialization script from the project root:
```powershell
python backend/init_db.py
```
This script will:
1. Connect to PostgreSQL.
2. Automatically create the database `agrismart` if it does not exist.
3. Apply [`database/schema.sql`](database/schema.sql) to instantiate all 18 tables, triggers, and indexes.
4. Verify all 18 tables in the public schema and display them.

### Step 4: Run the Flask API Server
Start the development server:
```powershell
python backend/app.py
```

### Step 5: Test Endpoints
Open another terminal or browser:
- **Service Health**: [http://localhost:5000/api/health](http://localhost:5000/api/health)
- **Database Test**: [http://localhost:5000/api/db-test](http://localhost:5000/api/db-test)

Using PowerShell:
```powershell
Invoke-RestMethod -Uri http://localhost:5000/api/health
Invoke-RestMethod -Uri http://localhost:5000/api/db-test
```

---

## 3. How to Verify in pgAdmin 4

1. Open **pgAdmin 4** from your Start menu.
2. Enter your master password to unlock pgAdmin.
3. In the left navigation pane, expand **Servers** -> **PostgreSQL**.
4. Expand **Databases** -> you will see **`agrismart`**.
5. Expand **`agrismart`** -> **Schemas** -> **public** -> **Tables**.
6. You will see all 18 tables listed:
   - `users`, `farmer_profiles`, `buyers`, `crops`, `varieties`, `hubs`, `farmer_produce`, `demand_records`, `orders`, `order_items`, `hub_inventory`, `quality_checks`, `deliveries`, `payments`, `farmer_payouts`, `notifications`, `reviews`, `demand_forecasts`.
7. Right-click any table (e.g., `farmer_produce`) and select **View/Edit Data** -> **First 100 Rows** to see columns, types, and constraints.
