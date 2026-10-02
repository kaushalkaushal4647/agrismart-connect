"""
AgriSmart Connect - Cloud Seed Script (Neon / any DATABASE_URL)
Seeds the cloud Neon database with Tamil Nadu demo data directly
using DATABASE_URL without needing local Postgres admin access.
"""

import sys
from pathlib import Path

# Ensure backend is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'backend'))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent / '.env', override=True)

from database import init_pool, get_db_cursor
from config import Config

print("=" * 65)
print(" AgriSmart Connect - Neon Cloud Database Seeder")
print(" Using:", Config.get_db_conn_string()[:60] + "...")
print("=" * 65)

# Init pool and wait for connection (Neon cold-starts in ~2s)
pool = init_pool()
pool.open(wait=True)

# ─────────────────────────────────────────────────────────────
# Import the actual seed function after pool is ready
# ─────────────────────────────────────────────────────────────
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

DEFAULT_PASSWORD = generate_password_hash("Password@123")


with get_db_cursor(commit=True) as cur:

    # ── 1. CROPS ────────────────────────────────────────────────
    print("[*] Seeding crops...")
    crops_data = [
        ("Tomato",      "Vegetables", "Fresh red field and greenhouse tomatoes"),
        ("Onion",       "Vegetables", "Pungent culinary small shallots and bellary onions"),
        ("Potato",      "Tubers",     "High starch Nilgiris and processing potatoes"),
        ("Green Chilli","Spices",     "Spicy hot cooking chillies"),
        ("Cabbage",     "Vegetables", "Crisp leafy green and hybrid cabbages"),
        ("Brinjal",     "Vegetables", "Purple and green varieties of eggplant"),
        ("Banana",      "Fruits",     "Robusta and Nendran banana bunches"),
        ("Mango",       "Fruits",     "Alphonso, Banganapalli, and Neelam mangoes"),
        ("Coconut",     "Fruits",     "West Coast Tall and Hybrid coconuts"),
        ("Turmeric",    "Spices",     "Erode finger and bulb turmeric"),
    ]
    crop_ids = {}
    for name, cat, desc in crops_data:
        cur.execute("""
            INSERT INTO crops (crop_name, category, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (crop_name) DO UPDATE SET description = EXCLUDED.description
            RETURNING crop_id, crop_name;
        """, (name, cat, desc))
        row = cur.fetchone()
        crop_ids[row['crop_name']] = row['crop_id']
    print(f"    ✓ {len(crop_ids)} crops seeded")

    # ── 2. VARIETIES ─────────────────────────────────────────────
    print("[*] Seeding varieties...")
    varieties_data = {
        "Tomato":       ["Hybrid Tomato (Shivam)", "Desi Tomato (Nattu Thakkali)", "Roma Tomato"],
        "Onion":        ["Bellary Red Onion", "Small Shallot (Sambar Onion)"],
        "Potato":       ["Kufri Jyoti", "Kufri Chandramukhi"],
        "Green Chilli": ["G4 Variety", "Jwala Chilli"],
        "Cabbage":      ["Golden Acre", "Copenhagen Market"],
        "Brinjal":      ["Purple Round Brinjal", "Green Long Brinjal"],
        "Banana":       ["Robusta (Grand Naine)", "Nendran Banana"],
        "Mango":        ["Alphonso (Hapus)", "Banganapalli", "Neelam"],
        "Coconut":      ["West Coast Tall", "Hybrid Dwarf"],
        "Turmeric":     ["Erode Local", "BSR-2 (Finger Turmeric)"],
    }
    variety_ids = {}
    for crop_name, vars_list in varieties_data.items():
        crop_id = crop_ids.get(crop_name)
        if not crop_id:
            continue
        for vname in vars_list:
            cur.execute("""
                INSERT INTO varieties (crop_id, variety_name)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                RETURNING variety_id;
            """, (crop_id, vname))
            row = cur.fetchone()
            if row:
                variety_ids[f"{crop_name}:{vname}"] = row['variety_id']
    print(f"    ✓ Varieties seeded")

    # ── 3. HUBS ────────────────────────────────────────────────
    print("[*] Seeding hubs...")
    # Actual hubs columns: hub_name, address, village, district, latitude, longitude, capacity_kg, status
    hubs_data = [
        ("Koyambedu APMC Hub",   "Koyambedu Market Rd",  "Koyambedu",    "Chennai",         13.0730, 80.2080, 100000),
        ("Coimbatore AgriHub",   "Gandhipuram St",        "Gandhipuram",  "Coimbatore",      11.0168, 76.9558, 80000),
        ("Madurai Central Hub",  "Mattuthavani Rd",       "Mattuthavani", "Madurai",         9.9252,  78.1198, 60000),
        ("Salem Fruits Hub",     "Shevapet Main Rd",      "Shevapet",     "Salem",           11.6543, 78.1460, 50000),
        ("Trichy Logistics Hub", "Chatram Bus Stand Rd",  "Srirangam",    "Tiruchirappalli", 10.7905, 78.7047, 70000),
    ]
    hub_ids = {}
    for name, addr, village, district, lat, lon, cap in hubs_data:
        cur.execute("""
            INSERT INTO hubs (hub_name, address, village, district, latitude, longitude, capacity_kg, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'active')
            ON CONFLICT DO NOTHING
            RETURNING hub_id, hub_name;
        """, (name, addr, village, district, lat, lon, cap))
        row = cur.fetchone()
        if row:
            hub_ids[row['hub_name']] = row['hub_id']
    print(f"    Hubs seeded: {len(hub_ids)}")

    # ── 4. USERS + PROFILES ───────────────────────────────────
    print("[*] Seeding users...")

    # Admin - actual users columns: user_id, name, phone, email, password_hash, role, is_active
    cur.execute("""
        INSERT INTO users (name, email, phone, password_hash, role)
        VALUES ('AgriSmart Admin', 'admin@agrismart.com', '9999000001', %s, 'admin')
        ON CONFLICT (email) DO NOTHING RETURNING user_id;
    """, (DEFAULT_PASSWORD,))

    # Demo Hub Operators
    hub_list = list(hub_ids.items())
    for i, (hname, hid) in enumerate(hub_list[:3]):
        email = f"hub{i+1}@agrismart.com"
        cur.execute("""
            INSERT INTO users (name, email, phone, password_hash, role)
            VALUES (%s, %s, %s, %s, 'hub_operator')
            ON CONFLICT (email) DO NOTHING RETURNING user_id;
        """, (f"Hub Operator {i+1}", email, f"988800000{i+1}", DEFAULT_PASSWORD))

    # Demo Farmers
    farmers = [
        ("Ramu Krishnan",    "ramu@agrismart.com",    "9001000001", "Coimbatore",  "Tomato"),
        ("Selvi Muthusamy",  "selvi@agrismart.com",   "9001000002", "Salem",       "Onion"),
        ("Anand Palanivel",  "anand@agrismart.com",   "9001000003", "Madurai",     "Brinjal"),
        ("Kavitha Rajan",    "kavitha@agrismart.com", "9001000004", "Tirunelveli", "Banana"),
        ("Murugan Pillai",   "murugan@agrismart.com", "9001000005", "Coimbatore",  "Tomato"),
        ("Geetha Nadar",     "geetha@agrismart.com",  "9001000006", "Thoothukudi", "Mango"),
        ("Suresh Thevar",    "suresh@agrismart.com",  "9001000007", "Trichy",      "Coconut"),
        ("Priya Pandian",    "priya@agrismart.com",   "9001000008", "Madurai",     "Turmeric"),
        ("Balan Arumugam",   "balan@agrismart.com",   "9001000009", "Erode",       "Turmeric"),
        ("Velu Gounder",     "velu@agrismart.com",    "9001000010", "Salem",       "Potato"),
    ]
    farmer_user_ids = []
    tn_coords = [
        (11.0168, 76.9558), (11.6543, 78.1460), (9.9252, 78.1198),
        (8.7139, 77.7567),  (11.0168, 76.9558), (8.8053, 78.1462),
        (10.7905, 78.7047), (9.9252, 78.1198),  (11.3410, 77.7172), (11.6543, 78.1460),
    ]
    for name, email, phone, city, crop in farmers:
        cur.execute("""
            INSERT INTO users (name, email, phone, password_hash, role)
            VALUES (%s, %s, %s, %s, 'farmer')
            ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
            RETURNING user_id;
        """, (name, email, phone, DEFAULT_PASSWORD))
        row = cur.fetchone()
        if row:
            farmer_user_ids.append((row['user_id'], name, city, crop))

    # Farmer profiles - actual columns: farmer_id, user_id, farm_name, village, district, state, latitude, longitude, farm_size, address
    hub_id_list = list(hub_ids.values())
    for idx, (uid, name, city, crop) in enumerate(farmer_user_ids):
        lat, lon = tn_coords[idx % len(tn_coords)]
        cur.execute("""
            INSERT INTO farmer_profiles (user_id, farm_name, village, district, state, latitude, longitude, farm_size, address)
            VALUES (%s, %s, %s, %s, 'Tamil Nadu', %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING;
        """, (uid, f"{name}'s Farm", city, city, lat, lon,
              round(2.5 + idx * 0.7, 1), f"{city} District, Tamil Nadu"))

    # Demo Restaurants
    restaurants = [
        ("Saravana Bhavan",   "restaurant@agrismart.com",  "9002000001"),
        ("Murugan Idli Shop", "resto2@agrismart.com",      "9002000002"),
        ("Hotel Tamil Nadu",  "resto3@agrismart.com",      "9002000003"),
    ]
    for name, email, phone in restaurants:
        cur.execute("""
            INSERT INTO users (name, email, phone, password_hash, role)
            VALUES (%s, %s, %s, %s, 'restaurant')
            ON CONFLICT (email) DO NOTHING;
        """, (name, email, phone, DEFAULT_PASSWORD))

    # Demo Retailers
    retailers = [
        ("Nalli Retail Store",    "retailer@agrismart.com",  "9003000001"),
        ("Big Bazaar Coimbatore", "retailer2@agrismart.com", "9003000002"),
    ]
    for name, email, phone in retailers:
        cur.execute("""
            INSERT INTO users (name, email, phone, password_hash, role)
            VALUES (%s, %s, %s, %s, 'retailer')
            ON CONFLICT (email) DO NOTHING;
        """, (name, email, phone, DEFAULT_PASSWORD))

    # Demo Consumers
    for i in range(5):
        cur.execute("""
            INSERT INTO users (name, email, phone, password_hash, role)
            VALUES (%s, %s, %s, %s, 'consumer')
            ON CONFLICT (email) DO NOTHING;
        """, (f"Consumer {i+1}", f"consumer{i+1}@agrismart.com", f"900400000{i+1}", DEFAULT_PASSWORD))

    print(f"    ✓ Users seeded")

    # ── 5. FARMER PRODUCE LISTINGS ─────────────────────────────
    print("[*] Seeding farmer produce listings...")
    today = date.today()
    produce_entries = [
        ("Tomato",       "Hybrid Tomato (Shivam)",    0, 28.50, 500, "premium"),
        ("Onion",        "Bellary Red Onion",          1, 22.00, 800, "standard"),
        ("Brinjal",      "Purple Round Brinjal",       2, 18.00, 300, "premium"),
        ("Banana",       "Robusta (Grand Naine)",      3, 35.00, 1000, "standard"),
        ("Mango",        "Alphonso (Hapus)",           4, 120.00, 200, "premium"),
        ("Coconut",      "West Coast Tall",            5, 15.00, 2000, "standard"),
        ("Turmeric",     "Erode Local",                6, 85.00, 400, "premium"),
        ("Potato",       "Kufri Jyoti",                7, 20.00, 600, "standard"),
        ("Tomato",       "Desi Tomato (Nattu Thakkali)",8, 24.00, 400, "standard"),
        ("Green Chilli", "G4 Variety",                 9, 55.00, 150, "premium"),
    ]

    # Actual farmer_produce columns: farmer_id (FK to farmer_profiles.farmer_id), crop_id, variety_id,
    # expected_quantity_kg, available_quantity_kg, reserved_quantity_kg, sold_quantity_kg,
    # minimum_price_per_kg, harvest_date, quality_grade, latitude, longitude, preferred_hub_id, status
    hub_id_list = list(hub_ids.values()) if hub_ids else [None]
    for i, (crop_name, var_name, farmer_idx, price, qty, grade) in enumerate(produce_entries):
        farmer_idx = farmer_idx % len(farmer_user_ids)
        farmer_uid = farmer_user_ids[farmer_idx][0]
        crop_id = crop_ids.get(crop_name)
        if not crop_id:
            continue
        var_id = variety_ids.get(f"{crop_name}:{var_name}")
        hub_id = hub_id_list[i % len(hub_id_list)]
        lat, lon = tn_coords[i % len(tn_coords)]

        cur.execute("""
            INSERT INTO farmer_produce (
                farmer_id, crop_id, variety_id,
                expected_quantity_kg, available_quantity_kg, reserved_quantity_kg, sold_quantity_kg,
                minimum_price_per_kg, harvest_date, quality_grade,
                latitude, longitude, preferred_hub_id, status
            ) VALUES (
                (SELECT farmer_id FROM farmer_profiles WHERE user_id = %s LIMIT 1),
                %s, %s, %s, %s, 0, 0, %s, %s, %s, %s, %s, %s, 'available'
            )
            ON CONFLICT DO NOTHING;
        """, (farmer_uid, crop_id, var_id, qty, qty, price,
              today - timedelta(days=2), grade, lat, lon, hub_id))

    print(f"    {len(produce_entries)} produce listings seeded")

print()
print("=" * 65)
print(" ✅ AgriSmart Neon Database Seeded Successfully!")
print(" Credentials (all users): Password@123")
print(" Admin:       admin@agrismart.com")
print(" Farmer:      ramu@agrismart.com")
print(" Restaurant:  restaurant@agrismart.com")
print(" Retailer:    retailer@agrismart.com")
print(" Consumer:    consumer1@agrismart.com")
print("=" * 65)
