"""
AgriSmart Connect - Prototype Seed Data Generator (Tamil Nadu Ecosystem).
Populates 5 crops, 12 varieties, 3 key collection hubs, 10 demo farmers,
5 demo restaurants, 3 demo retailers, 20 demo consumers, admin, hub operator,
and realistic farmer produce batches located strictly within Tamil Nadu, India.
"""

import sys
from pathlib import Path
from datetime import date, timedelta
import psycopg
from werkzeug.security import generate_password_hash

# Ensure backend directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
from init_db import init_database
from database import get_db_cursor, fetch_one, execute_query


def check_and_prepare_database():
    """Verify PostgreSQL server is online, and create tables if needed."""
    server_conn_info = Config.get_postgres_server_conn_string()
    target_conn_info = Config.get_db_conn_string()

    print(f"[*] Checking PostgreSQL connection on {Config.DB_HOST}:{Config.DB_PORT}...")
    try:
        with psycopg.connect(server_conn_info, autocommit=True, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (Config.DB_NAME,))
                exists = cur.fetchone()
    except Exception as e:
        print("\n" + "=" * 65)
        print(" [-] CANNOT CONNECT TO POSTGRESQL SERVER")
        print("=" * 65)
        print(f"Error: {e}\n")
        sys.exit(1)

    if not exists:
        print(f"[*] Database '{Config.DB_NAME}' not found. Initializing now...")
        init_database()
    else:
        try:
            with psycopg.connect(target_conn_info, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
                    count = cur.fetchone()[0]
                    if count == 0:
                        print("[*] Database exists but tables are empty. Running schema.sql...")
                        init_database()
        except Exception as e:
            print(f"[*] Initializing database schema: {e}")
            init_database()


def seed_database():
    print("=" * 65)
    print(" AgriSmart Connect - Tamil Nadu Prototype Data Seeder")
    print("=" * 65)

    check_and_prepare_database()

    default_password = generate_password_hash("Password@123")

    with get_db_cursor(commit=True) as cur:
        # 1. SEED CROPS
        print("[*] Seeding Tamil Nadu Crops...")
        crops_data = [
            ("Tomato", "Vegetables", "Fresh red field and greenhouse tomatoes"),
            ("Onion", "Vegetables", "Pungent culinary small shallots and bellary onions"),
            ("Potato", "Tubers", "High starch Nilgiris and processing potatoes"),
            ("Green Chilli", "Spices", "Spicy hot cooking chillies from G4 and Jwala selections"),
            ("Cabbage", "Vegetables", "Crisp leafy green and hybrid cabbages")
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
            crop_ids[name] = row['crop_id']

        # 2. SEED VARIETIES
        print("[*] Seeding Tamil Nadu Varieties...")
        varieties_data = [
            ("Tomato", ["Hybrid Tomato (Shivam)", "Desi Tomato (Nattu Thakkali)", "Roma Tomato", "Cherry Tomato"]),
            ("Onion", ["Chinna Vengayam (Sambar Shallot)", "Bellary Red Onion", "White Onion"]),
            ("Potato", ["Ooty Mountain Potato", "Kufri Jyoti", "Baby Potato"]),
            ("Green Chilli", ["G4 Hot Chilli", "Jwala Chilli"]),
            ("Cabbage", ["Golden Acre", "Green Savoy"])
        ]
        variety_ids = {}
        for crop_name, v_list in varieties_data:
            c_id = crop_ids[crop_name]
            for v_name in v_list:
                cur.execute("""
                    INSERT INTO varieties (crop_id, variety_name, description)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (crop_id, variety_name) DO NOTHING
                    RETURNING variety_id, variety_name;
                """, (c_id, v_name, f"Standard commercial grade {v_name}"))
                res = cur.fetchone()
                if not res:
                    cur.execute("SELECT variety_id FROM varieties WHERE crop_id = %s AND variety_name = %s;", (c_id, v_name))
                    res = cur.fetchone()
                variety_ids[v_name] = res['variety_id']

        # 3. SEED KEY REGIONAL COLLECTION HUBS (TAMIL NADU)
        print("[*] Seeding Key Tamil Nadu Regional Collection Hubs...")
        hubs_data = [
            ("Salem Collection & Processing Hub (PLANNED)", "Attur Bypass Road, Suramangalam APMC", "Suramangalam", "Salem", 11.6643, 78.1460, 50000.0, "Salem", "Salem", 7000.0, 15, 50.0),
            ("Namakkal Agro-Logistics Center (PLANNED)", "Mohanur Road Farmer Aggregation Complex", "Mohanur", "Namakkal", 11.2189, 78.1674, 45000.0, "Namakkal", "Namakkal", 6000.0, 14, 45.0),
            ("Erode Central Turmeric & Veg Hub (PLANNED)", "Perundurai SIPCOT Agri Zone", "Perundurai", "Erode", 11.2750, 77.5833, 55000.0, "Perundurai", "Erode", 7500.0, 16, 50.0)
        ]
        hub_ids = []
        for name, addr, vil, dist, lat, lon, cap, taluk, town, daily_cap, wrk, rad in hubs_data:
            cur.execute("SELECT hub_id FROM hubs WHERE hub_name = %s;", (name,))
            row = cur.fetchone()
            if row:
                cur.execute("""
                    UPDATE hubs
                    SET address = %s, village = %s, district = %s, latitude = %s, longitude = %s,
                        capacity_kg = %s, taluk = %s, town = %s, daily_processing_capacity_kg = %s,
                        workers = %s, delivery_radius_km = %s, status = 'active', is_demo = TRUE
                    WHERE hub_id = %s;
                """, (addr, vil, dist, lat, lon, cap, taluk, town, daily_cap, wrk, rad, row['hub_id']))
                hub_ids.append(row['hub_id'])
            else:
                cur.execute("""
                    INSERT INTO hubs (
                        hub_name, address, village, district, latitude, longitude,
                        capacity_kg, taluk, town, daily_processing_capacity_kg, workers, delivery_radius_km,
                        status, is_demo
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', TRUE)
                    RETURNING hub_id;
                """, (name, addr, vil, dist, lat, lon, cap, taluk, town, daily_cap, wrk, rad))
                hub_ids.append(cur.fetchone()['hub_id'])

        # 4. SEED PLATFORM ADMIN, HUB OPERATOR, AND DELIVERY PARTNER
        print("[*] Seeding Admin, Hub Operator & Delivery Partner...")
        cur.execute("""
            INSERT INTO users (name, phone, email, password_hash, role, is_active)
            VALUES 
            ('System Super Admin', '9000000001', 'admin@demo.com', %s, 'admin', TRUE),
            ('Salem Hub Operator', '9000000002', 'hub@demo.com', %s, 'hub_operator', TRUE),
            ('TN Express Logistics Delivery', '9000000003', 'delivery@demo.com', %s, 'delivery_partner', TRUE)
            ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, role = EXCLUDED.role;
        """, (default_password, default_password, default_password))

        # 5. SEED 10 DEMO FARMERS WITH TAMIL NADU PROFILES
        print("[*] Seeding 10 Tamil Nadu Demo Farmers...")
        farmers = [
            ("Demo Farmer 001 - Selvam R", "9800000001", "farmer@demo.com", "Namakkal Agro Harvest Demo Farm", "Mohanur", "Namakkal", "Tamil Nadu", 11.2189, 78.1674, 8.5, hub_ids[1], "Tomato, Onion"),
            ("Demo Farmer 002 - Suresh J", "9800000002", "suresh@demo.com", "Palacode Red Soil Farms", "Palacode", "Dharmapuri", "Tamil Nadu", 12.3083, 78.0778, 12.0, hub_ids[0], "Tomato, Chilli"),
            ("Demo Farmer 003 - Anandan S", "9800000003", "anand@demo.com", "Perundurai Organic Acres", "Perundurai", "Erode", "Tamil Nadu", 11.2750, 77.5833, 6.0, hub_ids[2], "Tomato, Cabbage"),
            ("Demo Farmer 004 - Vignesh M", "9800000004", "vikas@demo.com", "Pollachi Grove Plantations", "Pollachi", "Coimbatore", "Tamil Nadu", 10.6586, 77.0089, 15.0, hub_ids[2], "Coconut, Banana"),
            ("Demo Farmer 005 - Santhosh G", "9800000005", "santosh@demo.com", "Attur Green Valley Agro", "Attur", "Salem", "Tamil Nadu", 11.5978, 78.5997, 10.0, hub_ids[0], "Tomato, Onion"),
            ("Demo Farmer 006 - Duraisamy P", "9800000006", "dnyan@demo.com", "Mohanur Riverbed Farms", "Mohanur", "Namakkal", "Tamil Nadu", 11.2189, 78.1674, 7.5, hub_ids[1], "Tomato, Onion"),
            ("Demo Farmer 007 - Balan D", "9800000007", "baban@demo.com", "Oddanchatram Hill Agro", "Oddanchatram", "Dindigul", "Tamil Nadu", 10.4856, 77.7472, 9.0, hub_ids[1], "Tomato, Chilli"),
            ("Demo Farmer 008 - Pandian K", "9800000008", "pandu@demo.com", "Melur Cauvery Feeder Farm", "Melur", "Madurai", "Tamil Nadu", 10.0275, 78.3347, 11.5, hub_ids[1], "Rice, Banana"),
            ("Demo Farmer 009 - Thangavel G", "9800000009", "tuka@demo.com", "Aravakurichi Drumstick Estate", "Aravakurichi", "Karur", "Tamil Nadu", 10.7717, 77.9083, 5.0, hub_ids[1], "Moringa, Onion"),
            ("Demo Farmer 010 - Manikandan C", "9800000010", "mahadev@demo.com", "Kovilpatti Black Soil Agro", "Kovilpatti", "Thoothukudi", "Tamil Nadu", 9.1722, 77.8694, 14.0, hub_ids[1], "Moringa, Chilli"),
        ]
        farmer_ids = []
        for name, phone, email, farm_name, vil, dist, st, lat, lon, fsize, hid, crops in farmers:
            cur.execute("""
                INSERT INTO users (name, phone, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, %s, 'farmer', TRUE)
                ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
                RETURNING user_id;
            """, (name, phone, email, default_password))
            uid = cur.fetchone()['user_id']

            cur.execute("""
                INSERT INTO farmer_profiles (
                    user_id, farm_name, village, taluk, district, state,
                    latitude, longitude, farm_size, address, current_hub_id, crop_types, status, is_demo
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', TRUE)
                ON CONFLICT (user_id) DO UPDATE SET
                    farm_name = EXCLUDED.farm_name,
                    village = EXCLUDED.village,
                    taluk = EXCLUDED.taluk,
                    district = EXCLUDED.district,
                    state = EXCLUDED.state,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    current_hub_id = EXCLUDED.current_hub_id,
                    is_demo = TRUE
                RETURNING farmer_id;
            """, (uid, farm_name, vil, vil, dist, st, lat, lon, fsize, f"{vil}, {dist}, Tamil Nadu", hid, crops))
            farmer_ids.append(cur.fetchone()['farmer_id'])

        # 6. SEED 5 DEMO RESTAURANTS (TAMIL NADU)
        print("[*] Seeding 5 Tamil Nadu Demo Restaurants...")
        restaurants = [
            ("Saravana Bhavan Salem", "9700000001", "restaurant@demo.com", "Five Roads Junction, Suramangalam", "Suramangalam", "Salem", 11.6680, 78.1420),
            ("Demo Restaurant - Spice Route", "9700000002", "spiceroute@demo.com", "Avinashi Road, Peelamedu", "Peelamedu", "Coimbatore", 11.0267, 77.0261),
            ("Demo Restaurant - Pandian Thali House", "9700000003", "panchavati@demo.com", "Mattuthavani Terminal Complex", "Mattuthavani", "Madurai", 9.9252, 78.1198),
            ("Demo Restaurant - The Urban Chef", "9700000004", "urbanchef@demo.com", "Pondy Bazaar, T. Nagar", "T. Nagar", "Chennai", 13.0418, 80.2341),
            ("Demo Restaurant - Dindigul Food Palace", "9700000005", "foodpalace@demo.com", "Salai Road, Clock Tower", "Dindigul Town", "Dindigul", 10.3673, 77.9803)
        ]
        for name, phone, email, addr, vil, dist, lat, lon in restaurants:
            cur.execute("""
                INSERT INTO users (name, phone, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, %s, 'restaurant', TRUE)
                ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
                RETURNING user_id;
            """, (name, phone, email, default_password))
            uid = cur.fetchone()['user_id']
            cur.execute("""
                INSERT INTO buyers (user_id, buyer_type, business_name, address, village, district, latitude, longitude)
                VALUES (%s, 'restaurant', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    business_name = EXCLUDED.business_name,
                    address = EXCLUDED.address,
                    village = EXCLUDED.village,
                    district = EXCLUDED.district,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude;
            """, (uid, name, addr, vil, dist, lat, lon))

        # 7. SEED 3 DEMO RETAILERS (TAMIL NADU)
        print("[*] Seeding 3 Tamil Nadu Demo Retailers...")
        retailers = [
            ("Demo Retailer - Kongu Fresh", "9600000001", "retailer@demo.com", "Gandhiji Road, Market Center", "Erode Fort", "Erode", 11.3420, 77.7190),
            ("Demo Retailer - Salem Farm Mart", "9600000002", "kisanmart@demo.com", "Meyyanur Main Road", "Meyyanur", "Salem", 11.6700, 78.1350),
            ("Demo Retailer - Subhiksha Supermarket", "9600000003", "subhiksha@demo.com", "Gandhi Market Complex", "Gandhi Market", "Tiruchirappalli", 10.7905, 78.7047)
        ]
        for name, phone, email, addr, vil, dist, lat, lon in retailers:
            cur.execute("""
                INSERT INTO users (name, phone, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, %s, 'retailer', TRUE)
                ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
                RETURNING user_id;
            """, (name, phone, email, default_password))
            uid = cur.fetchone()['user_id']
            cur.execute("""
                INSERT INTO buyers (user_id, buyer_type, business_name, address, village, district, latitude, longitude)
                VALUES (%s, 'retailer', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    business_name = EXCLUDED.business_name,
                    address = EXCLUDED.address,
                    village = EXCLUDED.village,
                    district = EXCLUDED.district,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude;
            """, (uid, name, addr, vil, dist, lat, lon))

        # 8. SEED 20 DEMO CONSUMERS (ACROSS TAMIL NADU)
        print("[*] Seeding 20 Tamil Nadu Demo Consumers...")
        tn_consumers = [
            ("Kavitha Consumer", "Plot 12, Mohanur Main Road", "Mohanur", "Namakkal", 11.2201, 78.1685),
            ("Demo Consumer - Priya K", "Flat 201, Kongu Enclave, Gandhipuram", "Gandhipuram", "Coimbatore", 11.0183, 76.9639),
            ("Demo Consumer - Rajesh V", "Flat 102, Shanthi Colony, Anna Nagar", "Anna Nagar", "Chennai", 13.0850, 80.2100),
            ("Demo Consumer - Sneha J", "No. 45, Melur Main Road, K.K. Nagar", "K.K. Nagar", "Madurai", 9.9212, 78.1482),
            ("Demo Consumer - Aditya N", "No. 8, Salai Road, Thillai Nagar", "Thillai Nagar", "Tiruchirappalli", 10.8284, 78.6874),
            ("Demo Consumer - Meenakshi S", "Flat 304, Brindavan Road, Fairlands", "Fairlands", "Salem", 11.6750, 78.1450),
            ("Demo Consumer - Karthik T", "No. 19, Perundurai Road", "Erode Town", "Erode", 11.3320, 77.7120),
            ("Demo Consumer - Divya D", "No. 72, Medical College Road", "Thanjavur Town", "Thanjavur", 10.7750, 79.1280),
            ("Demo Consumer - Anand M", "No. 15, Trivandrum Road, Palayamkottai", "Palayamkottai", "Tirunelveli", 8.7180, 77.7420),
            ("Demo Consumer - Ananya M", "No. 33, Chittoor Bus Stand Road, Katpadi", "Katpadi", "Vellore", 12.9780, 79.1380),
            ("Demo Consumer - Saravanan R", "No. 61, Dharapuram Road", "Rayapet", "Tiruppur", 11.1120, 77.3480),
            ("Demo Consumer - Deepa B", "No. 10, Market Road", "Oddanchatram", "Dindigul", 10.4850, 77.7480),
            ("Demo Consumer - Naveen S", "No. 24, Main Bazaar", "Aravakurichi", "Karur", 10.7720, 77.9100),
            ("Demo Consumer - Thenmozhi S", "No. 40, Main Road", "Kovilpatti", "Thoothukudi", 9.1750, 77.8720),
            ("Demo Consumer - Vignesh P", "No. 5, Commercial Road", "Ooty", "The Nilgiris", 11.4120, 76.7020),
            ("Demo Consumer - Subhashini G", "No. 88, Bangalore Road", "Hosur", "Krishnagiri", 12.7380, 77.8280),
            ("Demo Consumer - Gunasekaran S", "No. 12, Pennagaram Road", "Dharmapuri Town", "Dharmapuri", 12.1250, 78.1600),
            ("Demo Consumer - Karpagam P", "No. 22, GST Road", "Maduranthakam", "Chengalpattu", 12.5130, 79.8880),
            ("Demo Consumer - Ramesh C", "No. 31, Alangudi Road", "Pudukkottai Town", "Pudukkottai", 10.3850, 78.8200),
            ("Demo Consumer - Deepalakshmi M", "No. 9, Pattamangala Street", "Mayiladuthurai", "Mayiladuthurai", 11.1100, 79.6550)
        ]
        for idx, (cname, addr, vil, dist, lat, lon) in enumerate(tn_consumers, 1):
            cemail = "consumer@demo.com" if idx == 1 else f"consumer{idx}@demo.com"
            cphone = f"95000000{idx:02d}"
            cur.execute("""
                INSERT INTO users (name, phone, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, %s, 'consumer', TRUE)
                ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
                RETURNING user_id;
            """, (cname, cphone, cemail, default_password))
            uid = cur.fetchone()['user_id']
            cur.execute("""
                INSERT INTO buyers (user_id, buyer_type, business_name, address, village, district, latitude, longitude)
                VALUES (%s, 'consumer', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    business_name = EXCLUDED.business_name,
                    address = EXCLUDED.address,
                    village = EXCLUDED.village,
                    district = EXCLUDED.district,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude;
            """, (uid, cname, addr, vil, dist, lat, lon))

        # 9. SEED REALISTIC FARMER PRODUCE BATCHES (TAMIL NADU)
        print("[*] Seeding Tamil Nadu Farmer Produce Batches...")
        today = date.today()
        produce_samples = [
            (farmer_ids[0], crop_ids["Tomato"], variety_ids["Hybrid Tomato (Shivam)"], 500.0, 500.0, 25.0, today + timedelta(days=2), "Grade A", hub_ids[1], 11.2189, 78.1674, "Namakkal Field Hybrid Tomatoes", "conventional"),
            (farmer_ids[1], crop_ids["Tomato"], variety_ids["Hybrid Tomato (Shivam)"], 300.0, 300.0, 24.5, today + timedelta(days=1), "Grade A", hub_ids[0], 12.3083, 78.0778, "Dharmapuri Palacode Fresh Tomatoes", "conventional"),
            (farmer_ids[2], crop_ids["Tomato"], variety_ids["Desi Tomato (Nattu Thakkali)"], 250.0, 250.0, 28.0, today + timedelta(days=3), "Grade A", hub_ids[2], 11.2750, 77.5833, "Perundurai Country Desi Tomatoes", "organic"),
            (farmer_ids[3], crop_ids["Onion"], variety_ids["Chinna Vengayam (Sambar Shallot)"], 1200.0, 1200.0, 48.0, today + timedelta(days=5), "Grade A", hub_ids[2], 10.6586, 77.0089, "Pollachi Red Sambar Shallots", "conventional"),
            (farmer_ids[4], crop_ids["Onion"], variety_ids["Chinna Vengayam (Sambar Shallot)"], 800.0, 800.0, 50.0, today + timedelta(days=2), "Grade A", hub_ids[0], 11.5978, 78.5997, "Attur Valley Small Onions", "organic"),
            (farmer_ids[5], crop_ids["Potato"], variety_ids["Ooty Mountain Potato"], 1500.0, 1500.0, 42.0, today + timedelta(days=4), "Grade A", hub_ids[1], 11.2189, 78.1674, "Ooty Mountain Harvest Potatoes", "organic"),
            (farmer_ids[6], crop_ids["Green Chilli"], variety_ids["G4 Hot Chilli"], 180.0, 180.0, 45.0, today + timedelta(days=1), "Grade A", hub_ids[1], 10.4856, 77.7472, "Oddanchatram G4 Spicy Chillies", "conventional"),
            (farmer_ids[7], crop_ids["Cabbage"], variety_ids["Golden Acre"], 400.0, 400.0, 20.0, today + timedelta(days=3), "Grade A", hub_ids[1], 10.0275, 78.3347, "Melur Golden Acre Cabbage", "conventional"),
            (farmer_ids[8], crop_ids["Tomato"], variety_ids["Roma Tomato"], 350.0, 350.0, 28.0, today + timedelta(days=4), "Grade A", hub_ids[1], 10.7717, 77.9083, "Karur Roma Salad Tomatoes", "conventional"),
            (farmer_ids[9], crop_ids["Potato"], variety_ids["Baby Potato"], 600.0, 600.0, 32.0, today + timedelta(days=2), "Grade A", hub_ids[1], 9.1722, 77.8694, "Kovilpatti Golden Baby Potatoes", "conventional")
        ]

        for fid, cid, vid, exp_kg, avail_kg, price, hdate, grade, hid, plat, plon, pname, org in produce_samples:
            cur.execute("""
                INSERT INTO farmer_produce (
                    farmer_id, crop_id, variety_id, product_name, category, unit, min_order_quantity_kg,
                    expected_quantity_kg, available_quantity_kg, reserved_quantity_kg, sold_quantity_kg,
                    minimum_price_per_kg, harvest_date, expected_availability_date, quality_grade,
                    latitude, longitude, preferred_hub_id, organic_status, moderation_status, status, is_demo
                )
                VALUES (%s, %s, %s, %s, 'Vegetables', 'kg', 2.0, %s, %s, 0.00, 0.00, %s, %s, %s, %s, %s, %s, %s, %s, 'APPROVED', 'available', TRUE)
                ON CONFLICT DO NOTHING;
            """, (fid, cid, vid, pname, exp_kg, avail_kg, price, hdate, hdate, grade, plat, plon, hid, org))

    print("\n" + "=" * 65)
    print(" Tamil Nadu Prototype Seed Data Loaded Successfully!")
    print("=" * 65)
    print(" Demo Accounts Ready (Password: 'Password@123'):")
    print("  - Farmer:         farmer@demo.com")
    print("  - Consumer:       consumer@demo.com")
    print("  - Restaurant:     restaurant@demo.com")
    print("  - Retailer:       retailer@demo.com")
    print("  - Hub Operator:   hub@demo.com")
    print("  - Delivery:       delivery@demo.com")
    print("  - Super Admin:    admin@demo.com")
    print("=" * 65)


if __name__ == '__main__':
    seed_database()
