"""
AgriSmart Connect - Tamil Nadu Demo Data Migration & Cleanup Script.
Remaps all non-Tamil Nadu demo accounts, hubs, farmers, buyers, orders, deliveries,
and route stops to authentic Tamil Nadu geographic locations and coordinates.
Strictly preserves real user accounts (e.g. Kaushal MK, manish, auto test accounts).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from database import get_db_cursor, fetch_all, fetch_one

def run_migration():
    print("=" * 70)
    print(" AgriSmart Connect - Tamil Nadu Geographic Migration & Cleanup")
    print("=" * 70)

    with get_db_cursor(commit=True) as cur:
        # ─────────────────────────────────────────────────────────────
        # 1. CANONICALIZE TAMIL NADU COLLECTION HUBS
        # ─────────────────────────────────────────────────────────────
        print("\n[Step 1] Canonicalizing 15 Tamil Nadu Regional Collection Hubs...")
        
        # Check canonical hubs
        cur.execute("""
            SELECT hub_id, hub_name, district, latitude, longitude 
            FROM hubs 
            WHERE latitude BETWEEN 8.0 AND 13.6 AND longitude BETWEEN 76.0 AND 80.5
            ORDER BY hub_id ASC;
        """)
        tn_hubs = cur.fetchall()
        
        # If no TN hubs exist, populate them
        if not tn_hubs:
            from seed_tamilnadu_data import seed_tamilnadu_database
            seed_tamilnadu_database()
            cur.execute("""
                SELECT hub_id, hub_name, district, latitude, longitude 
                FROM hubs 
                WHERE latitude BETWEEN 8.0 AND 13.6 AND longitude BETWEEN 76.0 AND 80.5
                ORDER BY hub_id ASC;
            """)
            tn_hubs = cur.fetchall()

        # Map each unique hub name to its canonical (lowest) hub_id
        canonical_hub_map = {}  # hub_name -> canonical_hub_id
        district_to_hub_id = {}
        for h in tn_hubs:
            name = h['hub_name']
            dist = h['district']
            if name not in canonical_hub_map:
                canonical_hub_map[name] = h['hub_id']
            if dist not in district_to_hub_id:
                district_to_hub_id[dist] = canonical_hub_map[name]

        canonical_ids = list(canonical_hub_map.values())
        print(f"  Canonical TN Hub IDs ({len(canonical_ids)}): {canonical_ids}")

        # Default fallback hubs in key districts
        namakkal_hub_id = district_to_hub_id.get('Namakkal', canonical_ids[0])
        salem_hub_id = district_to_hub_id.get('Salem', canonical_ids[0])
        erode_hub_id = district_to_hub_id.get('Erode', canonical_ids[0])
        coimbatore_hub_id = district_to_hub_id.get('Coimbatore', canonical_ids[0])
        dindigul_hub_id = district_to_hub_id.get('Dindigul', canonical_ids[0])

        # Get all hubs that are NOT canonical
        cur.execute("SELECT hub_id, hub_name, district FROM hubs WHERE NOT (hub_id = ANY(%s));", (canonical_ids,))
        non_canonical_hubs = cur.fetchall()
        print(f"  Found {len(non_canonical_hubs)} non-canonical / duplicate / non-TN hubs to remap.")

        # Remap foreign keys for each non-canonical hub
        for old_h in non_canonical_hubs:
            old_id = old_h['hub_id']
            name = old_h['hub_name']
            dist = old_h.get('district')

            # Determine best target canonical hub
            if name in canonical_hub_map:
                target_id = canonical_hub_map[name]
            elif dist in district_to_hub_id:
                target_id = district_to_hub_id[dist]
            elif 'Nashik' in name:
                target_id = namakkal_hub_id
            elif 'Baramati' in name:
                target_id = erode_hub_id
            elif 'Pune' in name:
                target_id = salem_hub_id
            else:
                target_id = namakkal_hub_id

            # Remap farmer_produce
            cur.execute("UPDATE farmer_produce SET preferred_hub_id = %s WHERE preferred_hub_id = %s;", (target_id, old_id))
            # Remap farmer_profiles
            cur.execute("UPDATE farmer_profiles SET current_hub_id = %s WHERE current_hub_id = %s;", (target_id, old_id))
            # Remap orders
            cur.execute("UPDATE orders SET hub_id = %s WHERE hub_id = %s;", (target_id, old_id))
            # Remap deliveries
            cur.execute("UPDATE deliveries SET hub_id = %s WHERE hub_id = %s;", (target_id, old_id))
            # Remap routes
            cur.execute("UPDATE routes SET hub_id = %s WHERE hub_id = %s;", (target_id, old_id))
            # Handle hub_inventory: check for conflict before updating
            cur.execute("SELECT inventory_id, crop_id, variety_id, quality_grade FROM hub_inventory WHERE hub_id = %s;", (old_id,))
            inv_rows = cur.fetchall()
            for inv in inv_rows:
                cur.execute("""
                    SELECT inventory_id FROM hub_inventory 
                    WHERE hub_id = %s AND crop_id = %s AND variety_id IS NOT DISTINCT FROM %s AND quality_grade = %s;
                """, (target_id, inv['crop_id'], inv['variety_id'], inv['quality_grade']))
                if cur.fetchone():
                    # Consolidate stock
                    cur.execute("""
                        UPDATE hub_inventory h1
                        SET available_quantity_kg = h1.available_quantity_kg + h2.available_quantity_kg
                        FROM hub_inventory h2
                        WHERE h1.hub_id = %s AND h2.inventory_id = %s
                          AND h1.crop_id = h2.crop_id
                          AND h1.variety_id IS NOT DISTINCT FROM h2.variety_id
                          AND h1.quality_grade = h2.quality_grade;
                    """, (target_id, inv['inventory_id']))
                    cur.execute("DELETE FROM hub_inventory WHERE inventory_id = %s;", (inv['inventory_id'],))
                else:
                    cur.execute("UPDATE hub_inventory SET hub_id = %s WHERE inventory_id = %s;", (target_id, inv['inventory_id']))

        # Now safely delete non-canonical hubs
        if non_canonical_hubs:
            cur.execute("DELETE FROM hubs WHERE NOT (hub_id = ANY(%s));", (canonical_ids,))
            print(f"  [OK] Successfully cleaned up {len(non_canonical_hubs)} duplicate/non-TN hubs.")

        # ─────────────────────────────────────────────────────────────
        # 2. MIGRATE DEMO FARMERS TO TAMIL NADU
        # ─────────────────────────────────────────────────────────────
        print("\n[Step 2] Migrating Demo Farmers to Tamil Nadu...")

        # Mapping of Maharashtra demo farmers to Tamil Nadu
        farmer_tn_mapping = {
            'suresh@demo.com': {
                'name': 'Demo Farmer - Suresh J',
                'farm_name': 'Palacode Red Soil Farms',
                'village': 'Palacode',
                'taluk': 'Palacode',
                'district': 'Dharmapuri',
                'lat': 12.3083, 'lon': 78.0778,
                'crops': 'Tomato, Chilli',
                'hub_id': salem_hub_id
            },
            'anand@demo.com': {
                'name': 'Demo Farmer - Anandan S',
                'farm_name': 'Perundurai Organic Acres',
                'village': 'Perundurai',
                'taluk': 'Perundurai',
                'district': 'Erode',
                'lat': 11.2750, 'lon': 77.5833,
                'crops': 'Tomato, Cabbage, Chilli',
                'hub_id': erode_hub_id
            },
            'vikas@demo.com': {
                'name': 'Demo Farmer - Vignesh M',
                'farm_name': 'Pollachi Grove Plantations',
                'village': 'Pollachi',
                'taluk': 'Pollachi',
                'district': 'Coimbatore',
                'lat': 10.6586, 'lon': 77.0089,
                'crops': 'Coconut, Banana',
                'hub_id': coimbatore_hub_id
            },
            'santosh@demo.com': {
                'name': 'Demo Farmer - Santhosh G',
                'farm_name': 'Attur Green Valley Agro',
                'village': 'Attur',
                'taluk': 'Attur',
                'district': 'Salem',
                'lat': 11.5978, 'lon': 78.5997,
                'crops': 'Tomato, Onion',
                'hub_id': salem_hub_id
            },
            'dnyan@demo.com': {
                'name': 'Demo Farmer - Duraisamy P',
                'farm_name': 'Mohanur Riverbed Farms',
                'village': 'Mohanur',
                'taluk': 'Namakkal',
                'district': 'Namakkal',
                'lat': 11.2189, 'lon': 78.1674,
                'crops': 'Tomato, Onion',
                'hub_id': namakkal_hub_id
            },
            'baban@demo.com': {
                'name': 'Demo Farmer - Balan D',
                'farm_name': 'Oddanchatram Hill Agro',
                'village': 'Oddanchatram',
                'taluk': 'Oddanchatram',
                'district': 'Dindigul',
                'lat': 10.4856, 'lon': 77.7472,
                'crops': 'Tomato, Onion, Chilli',
                'hub_id': dindigul_hub_id
            },
            'pandu@demo.com': {
                'name': 'Demo Farmer - Pandian K',
                'farm_name': 'Melur Cauvery Feeder Farm',
                'village': 'Melur',
                'taluk': 'Melur',
                'district': 'Madurai',
                'lat': 10.0275, 'lon': 78.3347,
                'crops': 'Banana, Rice',
                'hub_id': district_to_hub_id.get('Madurai', namakkal_hub_id)
            },
            'tuka@demo.com': {
                'name': 'Demo Farmer - Thangavel G',
                'farm_name': 'Aravakurichi Drumstick Estate',
                'village': 'Aravakurichi',
                'taluk': 'Aravakurichi',
                'district': 'Karur',
                'lat': 10.7717, 'lon': 77.9083,
                'crops': 'Moringa, Onion',
                'hub_id': district_to_hub_id.get('Karur', namakkal_hub_id)
            },
            'mahadev@demo.com': {
                'name': 'Demo Farmer - Manikandan C',
                'farm_name': 'Kovilpatti Black Soil Agro',
                'village': 'Kovilpatti',
                'taluk': 'Kovilpatti',
                'district': 'Thoothukudi',
                'lat': 9.1722, 'lon': 77.8694,
                'crops': 'Moringa, Chilli',
                'hub_id': district_to_hub_id.get('Thoothukudi', namakkal_hub_id)
            }
        }

        for email, info in farmer_tn_mapping.items():
            cur.execute("SELECT user_id FROM users WHERE email = %s;", (email,))
            u = cur.fetchone()
            if u:
                uid = u['user_id']
                cur.execute("UPDATE users SET name = %s WHERE user_id = %s;", (info['name'], uid))
                cur.execute("""
                    UPDATE farmer_profiles
                    SET farm_name = %s, village = %s, taluk = %s, district = %s, state = 'Tamil Nadu',
                        latitude = %s, longitude = %s, crop_types = %s, current_hub_id = %s,
                        status = 'ACTIVE', is_demo = TRUE, address = %s
                    WHERE user_id = %s;
                """, (
                    info['farm_name'], info['village'], info['taluk'], info['district'],
                    info['lat'], info['lon'], info['crops'], info['hub_id'],
                    f"{info['village']}, {info['taluk']} Taluk, {info['district']} District, Tamil Nadu",
                    uid
                ))
                # Also update their produce batches coordinates & hub
                cur.execute("""
                    UPDATE farmer_produce
                    SET latitude = %s, longitude = %s, preferred_hub_id = %s, is_demo = TRUE
                    WHERE farmer_id = (SELECT farmer_id FROM farmer_profiles WHERE user_id = %s);
                """, (info['lat'], info['lon'], info['hub_id'], uid))
                print(f"  [OK] Migrated farmer {email} -> {info['district']}, Tamil Nadu")

        # Also ensure primary farmer farmer@demo.com is strictly Namakkal
        cur.execute("UPDATE users SET name = 'Demo Farmer 001 - Selvam R' WHERE email = 'farmer@demo.com';")
        cur.execute("""
            UPDATE farmer_profiles 
            SET district = 'Namakkal', taluk = 'Namakkal', village = 'Mohanur', state = 'Tamil Nadu',
                latitude = 11.2189, longitude = 78.1674, is_demo = TRUE,
                address = 'Mohanur Road, Namakkal District, Tamil Nadu',
                current_hub_id = %s
            WHERE user_id = (SELECT user_id FROM users WHERE email = 'farmer@demo.com');
        """, (namakkal_hub_id,))

        # ─────────────────────────────────────────────────────────────
        # 3. MIGRATE DEMO BUYERS (RESTAURANTS, RETAILERS, CONSUMERS)
        # ─────────────────────────────────────────────────────────────
        print("\n[Step 3] Migrating Demo Buyers to Tamil Nadu...")

        buyers_tn_mapping = {
            # Restaurants
            'restaurant@demo.com': {
                'name': 'Saravana Bhavan Salem',
                'business_name': 'Saravana Bhavan Salem',
                'address': 'Five Roads Junction, Suramangalam',
                'village': 'Suramangalam',
                'district': 'Salem',
                'lat': 11.6680, 'lon': 78.1420
            },
            'spiceroute@demo.com': {
                'name': 'Demo Restaurant - Spice Route',
                'business_name': 'Spice Route Highway Diner',
                'address': 'Avinashi Road, Peelamedu',
                'village': 'Peelamedu',
                'district': 'Coimbatore',
                'lat': 11.0267, 'lon': 77.0261
            },
            'panchavati@demo.com': {
                'name': 'Demo Restaurant - Pandian Thali House',
                'business_name': 'Pandian Thali House',
                'address': 'Mattuthavani Terminal Complex',
                'village': 'Mattuthavani',
                'district': 'Madurai',
                'lat': 9.9252, 'lon': 78.1198
            },
            'urbanchef@demo.com': {
                'name': 'Demo Restaurant - The Urban Chef',
                'business_name': 'The Urban Chef Kitchen',
                'address': 'Pondy Bazaar, T. Nagar',
                'village': 'T. Nagar',
                'district': 'Chennai',
                'lat': 13.0418, 'lon': 80.2341
            },
            'foodpalace@demo.com': {
                'name': 'Demo Restaurant - Dindigul Food Palace',
                'business_name': 'Dindigul Food Palace',
                'address': 'Salai Road, Near Clock Tower',
                'village': 'Dindigul Town',
                'district': 'Dindigul',
                'lat': 10.3673, 'lon': 77.9803
            },
            # Retailers
            'retailer@demo.com': {
                'name': 'Demo Retailer - Kongu Fresh',
                'business_name': 'Kongu Fresh Daily Mart',
                'address': 'Gandhiji Road, Market Center',
                'village': 'Erode Fort',
                'district': 'Erode',
                'lat': 11.3420, 'lon': 77.7190
            },
            'kisanmart@demo.com': {
                'name': 'Demo Retailer - Salem Farm Mart',
                'business_name': 'Salem Fresh Vegetable Mart',
                'address': 'Meyyanur Main Road',
                'village': 'Meyyanur',
                'district': 'Salem',
                'lat': 11.6700, 'lon': 78.1350
            },
            'subhiksha@demo.com': {
                'name': 'Demo Retailer - Subhiksha Supermarket',
                'business_name': 'Subhiksha Supermarket',
                'address': 'Gandhi Market Complex',
                'village': 'Gandhi Market',
                'district': 'Tiruchirappalli',
                'lat': 10.7905, 'lon': 78.7047
            },
            # Direct Consumer 1
            'consumer@demo.com': {
                'name': 'Kavitha Consumer',
                'business_name': 'Kavitha Consumer',
                'address': 'Plot 12, Mohanur Main Road',
                'village': 'Mohanur',
                'district': 'Namakkal',
                'lat': 11.2201, 'lon': 78.1685
            }
        }

        # Consumers 2 to 20 across Tamil Nadu cities
        tn_consumer_profiles = [
            ("consumer2@demo.com", "Demo Consumer - Priya K", "Flat 201, Kongu Enclave, Gandhipuram", "Gandhipuram", "Coimbatore", 11.0183, 76.9639),
            ("consumer3@demo.com", "Demo Consumer - Rajesh V", "Flat 102, Shanthi Colony, Anna Nagar", "Anna Nagar", "Chennai", 13.0850, 80.2100),
            ("consumer4@demo.com", "Demo Consumer - Sneha J", "No. 45, Melur Main Road, K.K. Nagar", "K.K. Nagar", "Madurai", 9.9212, 78.1482),
            ("consumer5@demo.com", "Demo Consumer - Aditya N", "No. 8, Salai Road, Thillai Nagar", "Thillai Nagar", "Tiruchirappalli", 10.8284, 78.6874),
            ("consumer6@demo.com", "Demo Consumer - Meenakshi S", "Flat 304, Brindavan Road, Fairlands", "Fairlands", "Salem", 11.6750, 78.1450),
            ("consumer7@demo.com", "Demo Consumer - Karthik T", "No. 19, Perundurai Road", "Erode Town", "Erode", 11.3320, 77.7120),
            ("consumer8@demo.com", "Demo Consumer - Divya D", "No. 72, Medical College Road", "Thanjavur Town", "Thanjavur", 10.7750, 79.1280),
            ("consumer9@demo.com", "Demo Consumer - Anand M", "No. 15, Trivandrum Road, Palayamkottai", "Palayamkottai", "Tirunelveli", 8.7180, 77.7420),
            ("consumer10@demo.com", "Demo Consumer - Ananya M", "No. 33, Chittoor Bus Stand Road, Katpadi", "Katpadi", "Vellore", 12.9780, 79.1380),
            ("consumer11@demo.com", "Demo Consumer - Saravanan R", "No. 61, Dharapuram Road", "Rayapet", "Tiruppur", 11.1120, 77.3480),
            ("consumer12@demo.com", "Demo Consumer - Deepa B", "No. 10, Market Road", "Oddanchatram", "Dindigul", 10.4850, 77.7480),
            ("consumer13@demo.com", "Demo Consumer - Naveen S", "No. 24, Main Bazaar", "Aravakurichi", "Karur", 10.7720, 77.9100),
            ("consumer14@demo.com", "Demo Consumer - Thenmozhi S", "No. 40, Main Road", "Kovilpatti", "Thoothukudi", 9.1750, 77.8720),
            ("consumer15@demo.com", "Demo Consumer - Vignesh P", "No. 5, Commercial Road", "Ooty", "The Nilgiris", 11.4120, 76.7020),
            ("consumer16@demo.com", "Demo Consumer - Subhashini G", "No. 88, Bangalore Road", "Hosur", "Krishnagiri", 12.7380, 77.8280),
            ("consumer17@demo.com", "Demo Consumer - Gunasekaran S", "No. 12, Pennagaram Road", "Dharmapuri Town", "Dharmapuri", 12.1250, 78.1600),
            ("consumer18@demo.com", "Demo Consumer - Karpagam P", "No. 22, GST Road", "Maduranthakam", "Chengalpattu", 12.5130, 79.8880),
            ("consumer19@demo.com", "Demo Consumer - Ramesh C", "No. 31, Alangudi Road", "Pudukkottai Town", "Pudukkottai", 10.3850, 78.8200),
            ("consumer20@demo.com", "Demo Consumer - Deepalakshmi M", "No. 9, Pattamangala Street", "Mayiladuthurai", "Mayiladuthurai", 11.1100, 79.6550)
        ]

        for email, name, addr, vil, dist, lat, lon in tn_consumer_profiles:
            buyers_tn_mapping[email] = {
                'name': name,
                'business_name': name,
                'address': addr,
                'village': vil,
                'district': dist,
                'lat': lat, 'lon': lon
            }

        for email, binfo in buyers_tn_mapping.items():
            cur.execute("SELECT user_id FROM users WHERE email = %s;", (email,))
            u = cur.fetchone()
            if u:
                uid = u['user_id']
                cur.execute("UPDATE users SET name = %s WHERE user_id = %s;", (binfo['name'], uid))
                cur.execute("""
                    UPDATE buyers
                    SET business_name = %s, address = %s, village = %s, district = %s,
                        latitude = %s, longitude = %s
                    WHERE user_id = %s;
                """, (binfo['business_name'], binfo['address'], binfo['village'], binfo['district'], binfo['lat'], binfo['lon'], uid))
                print(f"  [OK] Migrated buyer {email} -> {binfo['district']}, Tamil Nadu")

        # ─────────────────────────────────────────────────────────────
        # 4. MIGRATE DEMO ORDERS, DELIVERIES, AND ROUTE STOPS
        # ─────────────────────────────────────────────────────────────
        print("\n[Step 4] Migrating Demo Orders, Deliveries, and Route Stops...")

        # Update orders referencing buyers to match the buyer's new Tamil Nadu coordinates & address
        cur.execute("""
            UPDATE orders o
            SET delivery_address = b.address || ', ' || b.district || ', Tamil Nadu',
                delivery_latitude = b.latitude,
                delivery_longitude = b.longitude
            FROM buyers b
            WHERE o.buyer_id = b.buyer_id
              AND (o.delivery_latitude NOT BETWEEN 8.0 AND 13.6 OR o.delivery_longitude NOT BETWEEN 76.0 AND 80.5);
        """)

        # Update delivery@demo.com buyer profile if present
        cur.execute("""
            UPDATE buyers
            SET district = 'Namakkal', village = 'Mohanur', address = 'Mohanur Agro Logistics Depot, Namakkal, Tamil Nadu',
                latitude = 11.2189, longitude = 78.1674
            WHERE user_id = (SELECT user_id FROM users WHERE email = 'delivery@demo.com');
        """)

        # Fallback update for any remaining orders with NULL, 0.0 or outside TN
        cur.execute("""
            UPDATE orders
            SET delivery_address = COALESCE(NULLIF(delivery_address, ''), 'Plot 12, Mohanur Road, Namakkal, Tamil Nadu'),
                delivery_latitude = 11.2201,
                delivery_longitude = 78.1685,
                hub_id = %s
            WHERE delivery_latitude IS NULL 
               OR delivery_longitude IS NULL 
               OR delivery_latitude < 8.0 
               OR delivery_latitude > 13.6 
               OR delivery_longitude < 76.0 
               OR delivery_longitude > 80.5;
        """, (namakkal_hub_id,))

        # Update deliveries to match orders
        cur.execute("""
            UPDATE deliveries d
            SET delivery_address = o.delivery_address,
                hub_id = o.hub_id
            FROM orders o
            WHERE d.order_id = o.order_id;
        """)

        # Update route stops
        cur.execute("""
            UPDATE route_stops rs
            SET customer_name = u.name,
                delivery_address = o.delivery_address,
                latitude = o.delivery_latitude,
                longitude = o.delivery_longitude
            FROM orders o
            JOIN buyers b ON o.buyer_id = b.buyer_id
            JOIN users u ON b.user_id = u.user_id
            WHERE rs.order_id = o.order_id;
        """)

        # Fallback update for any route stops still outside TN or NULL
        cur.execute("""
            UPDATE route_stops
            SET customer_name = 'Demo Consumer - Kavitha',
                delivery_address = 'Plot 12, Mohanur Road, Namakkal, Tamil Nadu',
                latitude = 11.2201,
                longitude = 78.1685
            WHERE latitude IS NULL 
               OR longitude IS NULL 
               OR latitude < 8.0 
               OR latitude > 13.6 
               OR longitude < 76.0 
               OR longitude > 80.5;
        """)

        # ─────────────────────────────────────────────────────────────
        # 5. VERIFICATION QUERY WITHIN TRANSACTION
        # ─────────────────────────────────────────────────────────────
        cur.execute("SELECT count(*) as c FROM hubs WHERE NOT (latitude BETWEEN 8.0 AND 13.6 AND longitude BETWEEN 76.0 AND 80.5);")
        bad_hubs = cur.fetchone()['c']

        cur.execute("SELECT count(*) as c FROM farmer_profiles WHERE NOT (latitude BETWEEN 8.0 AND 13.6 AND longitude BETWEEN 76.0 AND 80.5);")
        bad_farmers = cur.fetchone()['c']

        cur.execute("SELECT count(*) as c FROM buyers WHERE NOT (latitude BETWEEN 8.0 AND 13.6 AND longitude BETWEEN 76.0 AND 80.5) AND latitude IS NOT NULL;")
        bad_buyers = cur.fetchone()['c']

        cur.execute("SELECT count(*) as c FROM orders WHERE NOT (delivery_latitude BETWEEN 8.0 AND 13.6 AND delivery_longitude BETWEEN 76.0 AND 80.5);")
        bad_orders = cur.fetchone()['c']

        cur.execute("SELECT count(*) as c FROM route_stops WHERE NOT (latitude BETWEEN 8.0 AND 13.6 AND longitude BETWEEN 76.0 AND 80.5);")
        bad_stops = cur.fetchone()['c']

        print("\n" + "=" * 70)
        print(" MIGRATION VERIFICATION AUDIT")
        print("=" * 70)
        print(f"  Non-TN Hubs:           {bad_hubs}")
        print(f"  Non-TN Farmers:        {bad_farmers}")
        print(f"  Non-TN Buyers:         {bad_buyers}")
        print(f"  Non-TN Orders:         {bad_orders}")
        print(f"  Non-TN Route Stops:    {bad_stops}")
        print("=" * 70)

        if bad_hubs == 0 and bad_farmers == 0 and bad_buyers == 0 and bad_orders == 0 and bad_stops == 0:
            print(" [SUCCESS] All demo data has been successfully relocated to Tamil Nadu!")
        else:
            print(" [WARNING] Some non-TN rows remain. Check details above.")


if __name__ == '__main__':
    run_migration()
